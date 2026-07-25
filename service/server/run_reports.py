"""Trading Runs reporting (Plan 10, Phase 4).

Digest scheduling + P/L threshold triggers + the pending->sent delivery
journal. All EXTERNAL delivery routes through alerts.send_alert — the ONLY
path with the hourly budget, dedupe, and the run_stopped reserve
(notifications.notify has neither and must never carry reports).

Idempotency: a run_reports row is journaled (status 'pending') BEFORE the
external send, then flipped to 'sent'. Plain journal-before-send is
at-most-once — a crash between journal and send would permanently swallow
the report — so a sweep retries pending rows older than RETRY_AFTER_SECONDS.
send_alert's dedupe key (the report row id) makes retries safe: if the
original send actually left, the retry is deduped and the row is marked
sent anyway.

Timezone semantics: report_hour_local is LOCAL to report_tz (zoneinfo).
DST: a spring-forward nonexistent hour fires at the next scan once local
time passes it; the fall-back repeated hour fires once via the
last_report_at day guard.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo

from database import begin_write_transaction, get_db_connection
from trading_runs import TS_FMT, STATUS_PAUSED, STATUS_RUNNING, STATUS_STOPPING

logger = logging.getLogger(__name__)

VALID_FREQUENCIES = ("off", "hourly", "daily", "weekly")
RETRY_AFTER_SECONDS = int(os.getenv("RUN_REPORT_RETRY_AFTER", "600") or 600)

REPORTABLE_STATUSES = (STATUS_RUNNING, STATUS_PAUSED, STATUS_STOPPING)


def _now_dt() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now_dt().strftime(TS_FMT)


def _parse_ts(value: str) -> Optional[datetime]:
    try:
        return datetime.strptime(value, TS_FMT).replace(tzinfo=timezone.utc)
    except Exception:  # noqa: BLE001
        return None


def _local_zone(run: dict) -> ZoneInfo:
    try:
        return ZoneInfo(run.get("report_tz") or "UTC")
    except Exception:  # noqa: BLE001
        return ZoneInfo("UTC")


def digest_due(run: dict, now_utc: Optional[datetime] = None) -> bool:
    """Python-side due check (dual-dialect date SQL deliberately avoided)."""
    freq = (run.get("report_frequency") or "off").lower()
    if freq == "off":
        return False
    now_utc = now_utc or _now_dt()
    last = _parse_ts(run.get("last_report_at") or "")
    if freq == "hourly":
        return last is None or (now_utc - last) >= timedelta(hours=1)
    zone = _local_zone(run)
    local_now = now_utc.astimezone(zone)
    hour = run.get("report_hour_local")
    hour = 8 if hour is None else int(hour)
    if local_now.hour < hour:
        return False
    if freq == "weekly" and local_now.weekday() != 0:  # Monday
        return False
    if last is None:
        return True
    last_local = last.astimezone(zone)
    if freq == "daily":
        return last_local.date() < local_now.date()
    # weekly: not yet reported in this ISO week
    return last_local.isocalendar()[:2] < local_now.isocalendar()[:2]


def _period_stats(run: dict, period_start: str) -> dict[str, Any]:
    import run_engine
    pnl = run_engine.compute_run_pnl(run)
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """SELECT COUNT(*) AS n FROM signals
               WHERE run_id = ? AND message_type = 'operation'
                 AND created_at >= ?""",
            (run["id"], period_start))
        period_trades = int(cursor.fetchone()["n"] or 0)
    finally:
        conn.close()
    return {"pnl": pnl, "period_trades": period_trades}


def queue_digest(run: dict) -> Optional[int]:
    """Journal a pending digest row AND advance last_report_at in the same
    transaction (so a crash cannot double-queue), then return the row id."""
    period_start = run.get("last_report_at") or run.get("started_at") or _now_iso()
    now = _now_iso()
    stats = _period_stats(run, period_start)
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        begin_write_transaction(cursor)
        cursor.execute(
            """INSERT INTO run_reports
               (run_id, user_id, kind, period_start, period_end, pnl, trades,
                status, created_at)
               VALUES (?, ?, 'digest', ?, ?, ?, ?, 'pending', ?)""",
            (run["id"], _owning_user(cursor, run["agent_id"]), period_start, now,
             stats["pnl"]["total"], stats["period_trades"], now))
        report_id = cursor.lastrowid
        cursor.execute(
            "UPDATE trading_runs SET last_report_at = ? WHERE id = ?",
            (now, run["id"]))
        conn.commit()
        return report_id
    except Exception:  # noqa: BLE001
        logger.warning("digest queue failed for run %s", run["id"], exc_info=True)
        try:
            conn.rollback()
        except Exception:  # noqa: BLE001
            pass
        return None
    finally:
        conn.close()


def _owning_user(cursor, agent_id: int) -> Optional[int]:
    cursor.execute("SELECT user_id FROM agents WHERE id = ?", (agent_id,))
    row = cursor.fetchone()
    return row["user_id"] if row else None


def deliver_report(report: dict, run: dict) -> bool:
    """Send one journaled report via send_alert and flip pending -> sent.
    A dedupe-skip means a prior attempt's send actually left — mark sent."""
    from alerts import send_alert

    pnl = float(report.get("pnl") or 0)
    out = send_alert(run["agent_id"], "run_report", "run_report",
                     {"run_id": run["id"], "symbol": run["symbol"], "market": run["market"],
                      "period_start": report.get("period_start"),
                      "period_end": report.get("period_end"),
                      "pnl": f"{pnl:+.2f}",
                      "trades": int(report.get("trades") or 0),
                      "status": run.get("status")},
                     dedupe_key=f"run_report:{report['id']}")
    if out.get("error"):
        return False
    channels = out.get("channels") or []
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        begin_write_transaction(cursor)
        cursor.execute(
            """UPDATE run_reports SET status = 'sent', sent_at = ?, channels_json = ?
               WHERE id = ? AND status = 'pending'""",
            (_now_iso(), json.dumps(channels), report["id"]))
        conn.commit()
        return True
    finally:
        conn.close()


def prune_equity_events() -> int:
    """Equity-ONLY pruning (decision/trade/state rows are the audit journal
    and are never pruned). v1 simplification of the tiered scheme: full
    resolution for RUN_EQUITY_RETENTION_DAYS (default 7), hard delete
    beyond. Backfill responses carry oldest_retained_seq, so clients treat
    the pruned region as snapshot-reset territory."""
    days = int(os.getenv("RUN_EQUITY_RETENTION_DAYS", "7") or 7)
    cutoff = (_now_dt() - timedelta(days=days)).strftime(TS_FMT)
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        begin_write_transaction(cursor)
        cursor.execute(
            "DELETE FROM run_events WHERE event_type = 'equity' AND ts < ?",
            (cutoff,))
        n = cursor.rowcount or 0
        conn.commit()
        return int(n)
    except Exception:  # noqa: BLE001
        logger.debug("equity prune failed", exc_info=True)
        try:
            conn.rollback()
        except Exception:  # noqa: BLE001
            pass
        return 0
    finally:
        conn.close()


def scheduler_tick() -> dict:
    """Called by tasks.report_scheduler_loop: queue+deliver due digests,
    retry stale pending rows, and prune aged equity telemetry."""
    out = {"queued": 0, "delivered": 0, "retried": 0}
    out["equity_pruned"] = prune_equity_events()
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"""SELECT * FROM trading_runs
                WHERE report_frequency != 'off'
                  AND status IN ({','.join('?' * len(REPORTABLE_STATUSES))})""",
            REPORTABLE_STATUSES)
        runs = [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()

    runs_by_id = {r["id"]: r for r in runs}
    for run in runs:
        try:
            if digest_due(run):
                report_id = queue_digest(run)
                if report_id:
                    out["queued"] += 1
                    report = _get_report(report_id)
                    if report and deliver_report(report, run):
                        out["delivered"] += 1
        except Exception:  # noqa: BLE001
            logger.warning("digest tick failed for run %s", run["id"], exc_info=True)

    # retry sweep: pending rows older than the retry window (crash between
    # journal and send) — dedupe makes double-delivery impossible
    cutoff = (_now_dt() - timedelta(seconds=RETRY_AFTER_SECONDS)).strftime(TS_FMT)
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM run_reports WHERE status = 'pending' AND created_at < ?",
            (cutoff,))
        stale = [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()
    for report in stale:
        run = runs_by_id.get(report["run_id"]) or _get_run_any_status(report["run_id"])
        if not run:
            continue
        try:
            if deliver_report(report, run):
                out["retried"] += 1
        except Exception:  # noqa: BLE001
            logger.warning("report retry failed (report %s)", report["id"],
                           exc_info=True)
    return out


def _get_report(report_id: int) -> Optional[dict]:
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM run_reports WHERE id = ?", (report_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _get_run_any_status(run_id: int) -> Optional[dict]:
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM trading_runs WHERE id = ?", (run_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


# ── P/L threshold triggers (called from the control pass, every scan) ──────

def evaluate_thresholds(run: dict, pnl: dict) -> None:
    """Percent thresholds apply to run P&L relative to the run's capital
    base (run_budget_usd, else max_bet_usd). Fired at most once per rule per
    day via send_alert's dedupe (run:{id}:{rule}:{date}) — the daily key IS
    the hysteresis re-arm. drawdown_threshold_pct needs the equity series
    (Phase 6 journal) and is not evaluated yet. Fail-soft."""
    try:
        cfg = json.loads(run.get("config_snapshot_json") or "{}")
        base = float(cfg.get("run_budget_usd") or cfg.get("max_bet_usd") or 0)
        if base <= 0:
            return
        total = float(pnl.get("total") or 0)
        today = _now_iso()[:10]
        from alerts import send_alert
        loss_pct = run.get("loss_threshold_pct")
        if loss_pct is not None and total <= -(float(loss_pct) / 100.0) * base:
            send_alert(run["agent_id"], "run_threshold", "run_threshold_loss",
                       {"run_id": run["id"], "loss_pct": f"{float(loss_pct):g}",
                        "symbol": run["symbol"], "total": f"{total:+.2f}",
                        "base": f"{base:.0f}"},
                       dedupe_key=f"run:{run['id']}:loss:{today}")
        profit_pct = run.get("profit_threshold_pct")
        if profit_pct is not None and total >= (float(profit_pct) / 100.0) * base:
            send_alert(run["agent_id"], "run_threshold", "run_threshold_profit",
                       {"run_id": run["id"], "profit_pct": f"{float(profit_pct):g}",
                        "symbol": run["symbol"], "total": f"{total:+.2f}",
                        "base": f"{base:.0f}"},
                       dedupe_key=f"run:{run['id']}:profit:{today}")
    except Exception:  # noqa: BLE001
        logger.debug("threshold evaluation failed (run %s)", run.get("id"),
                     exc_info=True)
