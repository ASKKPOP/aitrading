"""Plan 21 P4 — daily desk brief + monthly process review.

Adapted from the hermes work-package's routine bundles (pre-market /
after-close / monthly-performance-review) into Sooppiy's shape:

- **Daily brief** — one localized notification per auto-trading member
  (anyone owning an active run), anchored at ``DESK_BRIEF_UTC_HOUR``. It
  leads with market posture (crypto composite, regime, F&G, 24h hot-issue
  count) plus a light activity line. P&L numbers stay run_reports' job —
  this is the desk's weather report, not a statement.
- **Monthly process review** — on the 1st (UTC), an English email to admins
  with 30-day aggregates and the recurring patterns that are BASE_SKILLS
  candidates (the owner's decisions-become-skills loop, closed by mail).

Both are deterministic — zero LLM cost. Send-once markers live in
platform_settings so restarts never double-send. Fail-soft everywhere: a
brief problem must never touch trading paths.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from database import get_db_connection

logger = logging.getLogger(__name__)

TS_FMT = "%Y-%m-%dT%H:%M:%SZ"

_DAILY_MARKER = "desk_brief_last_date"
_MONTHLY_MARKER = "desk_review_last_month"


def desk_brief_enabled() -> bool:
    return os.getenv("DESK_BRIEF_ENABLED", "true").strip().lower() in (
        "1", "true", "yes", "on")


def _brief_hour() -> int:
    try:
        return max(0, min(23, int(os.getenv("DESK_BRIEF_UTC_HOUR", "21"))))
    except ValueError:
        return 21


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.strftime(TS_FMT)


# ── market context ─────────────────────────────────────────────────────────

def gather_market_context() -> dict[str, Any]:
    """Regime + composite + F&G + 24h hot-issue count, each fail-soft."""
    ctx: dict[str, Any] = {"score": None, "zone": None, "regime": None,
                           "fng": None, "hot24": 0}
    try:
        import regime
        snap = regime.evaluate_market_regime(persist=False) or {}
        ctx["regime"] = snap.get("regime")
        ctx["fng"] = snap.get("fng_value")
        comp = snap.get("crypto_composite") or {}
        ctx["score"] = comp.get("score")
        ctx["zone"] = comp.get("zone")
    except Exception:  # noqa: BLE001
        logger.debug("desk_brief: regime unavailable", exc_info=True)
    try:
        cutoff = _iso(_now() - timedelta(hours=24))
        conn = get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) AS n FROM hot_issues "
                        "WHERE created_at > ?", (cutoff,))
            ctx["hot24"] = int(cur.fetchone()["n"] or 0)
        finally:
            conn.close()
    except Exception:  # noqa: BLE001
        pass
    return ctx


def _recipients() -> list[int]:
    """User ids owning at least one active trading run."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT DISTINCT a.user_id AS uid FROM trading_runs t
               JOIN agents a ON a.id = t.agent_id
               WHERE t.status = 'active' AND a.user_id IS NOT NULL""")
        return [int(r["uid"]) for r in cur.fetchall()]
    finally:
        conn.close()


def _user_activity(user_id: int) -> dict[str, int]:
    cutoff = _iso(_now() - timedelta(hours=24))
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT COUNT(*) AS n FROM trading_runs t
               JOIN agents a ON a.id = t.agent_id
               WHERE t.status = 'active' AND a.user_id = ?""", (user_id,))
        active_runs = int(cur.fetchone()["n"] or 0)
        cur.execute(
            """SELECT COUNT(*) AS n FROM run_events e
               JOIN trading_runs t ON t.id = e.run_id
               JOIN agents a ON a.id = t.agent_id
               WHERE a.user_id = ? AND e.event_type = 'decision'
                 AND e.ts > ?""", (user_id, cutoff))
        decisions24 = int(cur.fetchone()["n"] or 0)
        return {"active_runs": active_runs, "decisions24": decisions24}
    finally:
        conn.close()


def send_daily_briefs(now: Optional[datetime] = None) -> int:
    """Send today's brief to every eligible member once. Returns sent count."""
    now = now or _now()
    if now.hour < _brief_hour():
        return 0
    from platform_settings import get_setting, set_setting
    today = now.strftime("%Y-%m-%d")
    if get_setting(_DAILY_MARKER) == today:
        return 0
    # Claim the marker BEFORE sending: a crash mid-send drops the remainder
    # for a day rather than double-mailing everyone on restart.
    set_setting(_DAILY_MARKER, today, updated_by="desk_brief")
    ctx = gather_market_context()
    from notifications import notify_i18n
    sent = 0
    for uid in _recipients():
        try:
            act = _user_activity(uid)
            notify_i18n(uid, "auto_trading_reports", "desk_brief_daily", {
                "score": "—" if ctx["score"] is None else ctx["score"],
                "zone": ctx["zone"] or "—",
                "regime": ctx["regime"] or "—",
                "fng": "—" if ctx["fng"] is None else ctx["fng"],
                "hot24": ctx["hot24"],
                "active_runs": act["active_runs"],
                "decisions24": act["decisions24"],
            }, link="/automation")
            sent += 1
        except Exception:  # noqa: BLE001
            logger.warning("desk_brief: send failed for user %s", uid,
                           exc_info=True)
    logger.info("desk_brief: sent %d daily briefs", sent)
    return sent


# ── monthly process review ─────────────────────────────────────────────────

def _top_reasons(cur, event_type: str, key: str, cutoff: str,
                 limit: int = 5) -> list[tuple[str, int]]:
    cur.execute(
        "SELECT payload FROM run_events WHERE event_type = ? AND ts > ?",
        (event_type, cutoff))
    counts: dict[str, int] = {}
    for row in cur.fetchall():
        try:
            reason = str((json.loads(row["payload"] or "{}")).get(key) or "")
        except Exception:  # noqa: BLE001
            continue
        if reason:
            counts[reason] = counts.get(reason, 0) + 1
    return sorted(counts.items(), key=lambda kv: -kv[1])[:limit]


def monthly_aggregates() -> dict[str, Any]:
    cutoff = _iso(_now() - timedelta(days=30))
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        out: dict[str, Any] = {}
        cur.execute("SELECT COUNT(*) AS n FROM trading_runs WHERE status = 'active'")
        out["runs_active"] = int(cur.fetchone()["n"] or 0)
        cur.execute("SELECT COUNT(*) AS n FROM trading_runs WHERE created_at > ?",
                    (cutoff,))
        out["runs_started_30d"] = int(cur.fetchone()["n"] or 0)
        cur.execute(
            "SELECT COUNT(*) AS n, COALESCE(SUM(realized_pnl_usd), 0) AS pnl "
            "FROM trading_runs WHERE stopped_at > ?", (cutoff,))
        row = cur.fetchone()
        out["runs_stopped_30d"] = int(row["n"] or 0)
        out["realized_pnl_30d"] = round(float(row["pnl"] or 0), 2)
        cur.execute("SELECT COUNT(*) AS n FROM run_events "
                    "WHERE event_type = 'decision' AND ts > ?", (cutoff,))
        out["decisions_30d"] = int(cur.fetchone()["n"] or 0)
        out["gate_skip_reasons"] = _top_reasons(cur, "gate_skip", "reason", cutoff)
        out["stop_reasons"] = _top_reasons(cur, "alert", "stop_reason", cutoff)
        return out
    finally:
        conn.close()


def send_monthly_review(now: Optional[datetime] = None) -> bool:
    now = now or _now()
    if now.day != 1:
        return False
    from platform_settings import get_setting, set_setting
    month = now.strftime("%Y-%m")
    if get_setting(_MONTHLY_MARKER) == month:
        return False
    set_setting(_MONTHLY_MARKER, month, updated_by="desk_brief")
    agg = monthly_aggregates()

    def _fmt_reasons(pairs: list[tuple[str, int]]) -> str:
        return "\n".join(f"  - {r}: {n}×" for r, n in pairs) or "  - none recorded"

    body = (
        f"Sooppiy desk process review — 30 days to {now.strftime('%Y-%m-%d')}\n\n"
        f"Runs: {agg['runs_active']} active now, "
        f"{agg['runs_started_30d']} started, {agg['runs_stopped_30d']} stopped "
        f"(realized P&L of stopped runs: ${agg['realized_pnl_30d']})\n"
        f"Decisions: {agg['decisions_30d']}\n\n"
        f"Top gate-skip reasons:\n{_fmt_reasons(agg['gate_skip_reasons'])}\n\n"
        f"Top stop reasons:\n{_fmt_reasons(agg['stop_reasons'])}\n\n"
        "Candidate skill drafts (decisions-become-skills): every reason above "
        "that recurs across runs is a BASE_SKILLS candidate — if the desk "
        "keeps being stopped or gated for the same cause, the method that "
        "avoids the cause belongs in the catalogue. Review against "
        "service/server/trading_skills.py before adding.\n"
    )
    try:
        from admin_alerts import notify_admins
        notify_admins(f"Desk process review — {month}", body)
        logger.info("desk_brief: monthly review sent for %s", month)
        return True
    except Exception:  # noqa: BLE001
        logger.warning("desk_brief: monthly review send failed", exc_info=True)
        return False


def desk_brief_tick(now: Optional[datetime] = None) -> dict[str, Any]:
    """One scheduler tick: at most one daily send + one monthly send."""
    if not desk_brief_enabled():
        return {"enabled": False}
    now = now or _now()
    result = {"enabled": True, "daily_sent": 0, "monthly": False}
    try:
        result["daily_sent"] = send_daily_briefs(now)
    except Exception:  # noqa: BLE001
        logger.warning("desk_brief: daily tick failed", exc_info=True)
    try:
        result["monthly"] = send_monthly_review(now)
    except Exception:  # noqa: BLE001
        logger.warning("desk_brief: monthly tick failed", exc_info=True)
    return result
