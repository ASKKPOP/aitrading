"""Trading Runs scheduler engine (Plan 10, Phase 2).

Driven by tasks.trading_run_loop. Responsibilities per tick:

  1. CONTROL PASS (cheap, zero-LLM): arm -> running when start conditions
     fire; finish `stopping` runs that hold no run-owned position; nothing
     here calls an LLM.
  2. DISPATCH: due running runs execute one cycle each on a DEDICATED
     ThreadPoolExecutor (never asyncio.to_thread's shared default pool — four
     30-90s LLM calls there would starve the SL/TP watcher), bounded by
     RUN_CYCLE_CONCURRENCY.

Exactly-once model (the Phase 2 blocker fix):
  * The lease claim is its own SHORT COMMITTED transaction on a fresh
    connection, executed at slot acquisition (not scan time), and it
    atomically increments cycle_seq + stamps last_cycle_at. MySQL's
    REPEATABLE READ + autocommit=False makes a long-held claim both a lock
    hazard and a stale-read hazard (commit 73f4573 bug class) — so the claim
    commits before any analysis begins.
  * client_order_id = "run:{id}:cyc:{seq}" is UNIQUE on signals: the same
    seq can never trade twice.
  * The trade transaction re-reads the lease (fence) and the run status —
    a zombie claimant whose lease was reclaimed, or a run stopped mid-cycle,
    aborts before money moves.
  * A worker that crashes mid-cycle leaves last_cycle_at stamped, so the run
    simply waits for its next due window; the reclaimer then runs a FRESH
    cycle under a new seq. At-most-once per due window, exactly-once per seq.
  * Lease TTL (RUN_LEASE_TTL, default 300s) exceeds the worst-case cycle
    (semaphore wait is excluded — the claim happens after the slot).

Kill switch: AUTO_TRADING_ENABLED (default false — the feature ships dark
and is enabled per environment).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import socket
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import trading_runs
from database import begin_write_transaction, get_db_connection
from trading_runs import (
    STATUS_ARMED,
    STATUS_PAUSED,
    STATUS_RUNNING,
    STATUS_STOPPED,
    STATUS_STOPPING,
    TS_FMT,
    _emit_event,
    emit_telemetry_event,
)

logger = logging.getLogger(__name__)

WORKER_IDENTITY = f"{socket.gethostname()}:{os.getpid()}"

_executor: Optional[ThreadPoolExecutor] = None
_semaphore: Optional[asyncio.Semaphore] = None
_in_flight: set[int] = set()


def _now_dt() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now_dt().strftime(TS_FMT)


def _iso_in(seconds: int) -> str:
    return (_now_dt() + timedelta(seconds=seconds)).strftime(TS_FMT)


def auto_trading_enabled() -> bool:
    return os.getenv("AUTO_TRADING_ENABLED", "false").strip().lower() in (
        "1", "true", "yes", "on")


def _lease_ttl() -> int:
    try:
        return max(120, int(os.getenv("RUN_LEASE_TTL", "300")))
    except ValueError:
        return 300


def _concurrency() -> int:
    try:
        return max(1, int(os.getenv("RUN_CYCLE_CONCURRENCY", "4")))
    except ValueError:
        return 4


def _get_executor() -> ThreadPoolExecutor:
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(max_workers=_concurrency(),
                                       thread_name_prefix="run-cycle")
    return _executor


def _get_semaphore() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(_concurrency())
    return _semaphore


def _mark_staleness_max() -> int:
    """Mark age beyond which stop evaluation FAILS CLOSED. Default 3× the
    position-refresh interval (prod ships 300s) with a 900s floor — a frozen
    price is indistinguishable from a fresh one without this."""
    try:
        base = int(os.getenv("POSITION_REFRESH_INTERVAL", "300"))
    except ValueError:
        base = 300
    try:
        return int(os.getenv("RUN_MARK_STALENESS_MAX", str(max(900, base * 3))))
    except ValueError:
        return max(900, base * 3)


def _flatten_timeout() -> int:
    try:
        return max(300, int(os.getenv("RUN_FLATTEN_TIMEOUT", "3600")))
    except ValueError:
        return 3600


def _armed_timeout() -> int:
    try:
        return max(3600, int(os.getenv("RUN_ARMED_TIMEOUT", str(7 * 86400))))
    except ValueError:
        return 7 * 86400


def _stop_eval_failure_limit() -> int:
    try:
        return max(1, int(os.getenv("RUN_STOP_EVAL_FAILURES", "5")))
    except ValueError:
        return 5


# ── run P&L (fee-inclusive average-cost replay; ledger is the truth) ──────

def compute_run_pnl(run: dict) -> dict:
    """Replay the run's attributed signals with the EXACT leg math of
    execute_paper_trade (fees included — the fee-exclusive trade_stats
    precedent fires max_loss late by ~0.2%/round-trip on churny runs).
    Run exclusivity (D4) guarantees no other writer commingles the tuple's
    position, so average-cost replay is exact."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """SELECT side, entry_price, quantity, fee_usd FROM signals
               WHERE run_id = ? AND message_type = 'operation' ORDER BY id""",
            (run["id"],))
        legs = [dict(r) for r in cursor.fetchall()]
        cursor.execute(
            """SELECT quantity, entry_price, current_price, price_updated_at
               FROM positions
               WHERE agent_id = ? AND market = ? AND symbol = ? AND run_id = ?""",
            (run["agent_id"], run["market"], run["symbol"], run["id"]))
        pos = cursor.fetchone()
        pos = dict(pos) if pos else None
    finally:
        conn.close()

    qty = 0.0
    avg = 0.0
    realized = 0.0
    for leg in legs:
        side = leg["side"]
        p = float(leg["entry_price"] or 0)
        q = float(leg["quantity"] or 0)
        fee = float(leg["fee_usd"] or 0)
        if side == "buy":
            avg = (avg * qty + p * q) / (qty + q) if qty + q > 0 else p
            qty += q
            realized -= fee
        elif side == "sell":
            realized += (p - avg) * min(q, qty) - fee
            qty -= min(q, qty)
        elif side == "short":
            held = -qty  # current short size
            avg = (avg * held + p * q) / (held + q) if held + q > 0 else p
            qty -= q
            realized -= fee
        elif side == "cover":
            held = -qty
            realized += (avg - p) * min(q, held) - fee
            qty += min(q, held)
    unrealized = 0.0
    mark_age_ok = True
    if pos and float(pos["quantity"] or 0) != 0:
        mark = pos["current_price"]
        if mark is not None:
            pq = float(pos["quantity"])
            entry = float(pos["entry_price"] or 0)
            unrealized = (float(mark) - entry) * pq if pq > 0 \
                else (entry - float(mark)) * (-pq)
        updated = pos.get("price_updated_at")
        if mark is None or not updated or _age_seconds(updated) > _mark_staleness_max():
            mark_age_ok = False
    return {"realized": realized, "unrealized": unrealized,
            "total": realized + unrealized, "trades": len(legs),
            "position": pos, "mark_age_ok": mark_age_ok}


def _age_seconds(ts: str) -> float:
    try:
        then = datetime.strptime(ts, TS_FMT).replace(tzinfo=timezone.utc)
        return (_now_dt() - then).total_seconds()
    except Exception:  # noqa: BLE001
        return float("inf")


# ── stop-condition evaluation (every scan, running AND paused) ─────────────

def _evaluate_stop(run: dict) -> Optional[str]:
    """Return a stop reason string when a stop event fired, None otherwise.
    Raises on evaluation FAILURE (stale marks, unreadable state) — the
    caller treats failure as fail-closed (pause entries + alert), the
    inverse of the codebase's fail-open telemetry convention."""
    conditions = json.loads(run.get("stop_conditions_json") or "{}")
    pnl = compute_run_pnl(run)
    pos = pnl["position"]
    has_position = bool(pos and float(pos["quantity"] or 0) != 0)

    # Synthetic liquidation (D5): a v1 short's loss can exceed 100% of the
    # escrowed collateral (cover credit goes negative past 2x entry) — force
    # the stop at ~100% collateral loss regardless of configured conditions.
    if has_position and float(pos["quantity"]) < 0 and pnl["mark_age_ok"]:
        entry = float(pos["entry_price"] or 0)
        mark = float(pos["current_price"] or 0)
        if entry > 0 and mark >= 2 * entry:
            return "synthetic_liquidation"

    at = conditions.get("at_time")
    if at and at <= _now_iso():
        return "stop_event:at_time"
    mt = conditions.get("max_trades")
    if mt and pnl["trades"] >= int(mt):
        return "stop_event:max_trades"

    needs_pnl = ("max_loss_usd" in conditions or "profit_target_usd" in conditions)
    if needs_pnl and has_position and not pnl["mark_age_ok"]:
        raise RuntimeError(
            f"marks stale beyond {_mark_staleness_max()}s — refusing to evaluate "
            "P&L stops on frozen prices")
    # max_loss wins ties (safety first — Plan 10 D3).
    ml = conditions.get("max_loss_usd")
    if ml is not None and pnl["total"] <= -float(ml):
        return "stop_event:max_loss"
    pt = conditions.get("profit_target_usd")
    if pt is not None and pnl["total"] >= float(pt):
        return "stop_event:profit_target"

    pc = conditions.get("price_cross")
    if pc:
        price = None
        if has_position and pnl["mark_age_ok"] and pos.get("current_price") is not None:
            price = float(pos["current_price"])
        elif not has_position:
            try:
                from price_fetcher import get_price_from_market
                fetched = get_price_from_market(run["symbol"], None, run["market"])
                price = float(fetched) if fetched is not None else None
            except Exception:  # noqa: BLE001
                price = None
        if price is not None:
            if pc.get("direction") == "above" and price >= float(pc["price"]):
                return "stop_event:price_cross"
            if pc.get("direction") == "below" and price <= float(pc["price"]):
                return "stop_event:price_cross"
    return None


# equity telemetry: on-change with a heartbeat — NOT a blind 10s cadence
# (marks only move every poll interval; identical rows are pure prune load)
_last_equity: dict[int, tuple[float, float]] = {}  # run_id -> (total, monotime)


def _equity_heartbeat_seconds() -> int:
    try:
        return max(30, int(os.getenv("RUN_EQUITY_HEARTBEAT", "60")))
    except ValueError:
        return 60


def _maybe_emit_equity(run: dict, pnl: dict) -> None:
    import time as _time
    try:
        total = round(float(pnl.get("total") or 0), 6)
        prev = _last_equity.get(run["id"])
        now_mono = _time.monotonic()
        if prev is not None and prev[0] == total \
                and now_mono - prev[1] < _equity_heartbeat_seconds():
            return
        _last_equity[run["id"]] = (total, now_mono)
        emit_telemetry_event(run["id"], "equity",
                             {"realized": round(float(pnl.get("realized") or 0), 6),
                              "unrealized": round(float(pnl.get("unrealized") or 0), 6),
                              "total": total, "trades": pnl.get("trades")})
    except Exception:  # noqa: BLE001
        pass


def _cache_realized_pnl(run_id: int, realized: float) -> None:
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        begin_write_transaction(cursor)
        cursor.execute("UPDATE trading_runs SET realized_pnl_usd = ? WHERE id = ?",
                       (realized, run_id))
        conn.commit()
    except Exception:  # noqa: BLE001
        logger.debug("realized_pnl cache write failed for run %s", run_id, exc_info=True)
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass


def _manual_halt_blocks(agent_id: int, market: str) -> bool:
    """Exits bypass every gate EXCEPT a manual breaker HALT (the watcher's
    convention, risk_engine 'exits only reduce risk')."""
    try:
        from risk_engine import _is_halted
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            return bool(_is_halted(cursor, agent_id, market, include_auto=False))
        finally:
            conn.close()
    except Exception:  # noqa: BLE001
        return False


def _flatten_run(run: dict) -> tuple[bool, Optional[str]]:
    """Close the run-owned position via the watcher-convention exit path.
    Fill price is the last mark (same as watcher closes — the staleness
    caveat is surfaced in the UI, not hidden here). Idempotent via the
    'run:{id}:flatten' client_order_id."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """SELECT quantity, current_price FROM positions
               WHERE agent_id = ? AND market = ? AND symbol = ? AND run_id = ?
                 AND quantity != 0""",
            (run["agent_id"], run["market"], run["symbol"], run["id"]))
        pos = cursor.fetchone()
    finally:
        conn.close()
    if not pos:
        return True, None
    qty = float(pos["quantity"])
    mark = pos["current_price"]
    if mark is None:
        return False, "no mark price to flatten at"
    if _manual_halt_blocks(run["agent_id"], run["market"]):
        return False, "manual breaker halt blocks exits"
    from automation import execute_paper_trade
    side = "cover" if qty < 0 else "sell"
    signal_id, skip = execute_paper_trade(
        run["agent_id"], run["symbol"], run["market"], side, abs(qty), float(mark),
        content=f"Trading run #{run['id']} flatten on stop",
        run_id=run["id"], client_order_id=f"run:{run['id']}:flatten")
    if signal_id:
        return True, None
    if skip and "duplicate client_order_id" in skip:
        return True, None  # a prior attempt already flattened
    return False, skip


# ── control pass (sync, zero-LLM) ──────────────────────────────────────────

def _start_condition_fires(run: dict) -> bool:
    """Evaluate an armed run's start condition. Strictly-validated JSON was
    stored at create time; any read/parse problem here means STAY ARMED
    (fail closed — never 'start now')."""
    try:
        cond = json.loads(run.get("start_condition_json") or "{}")
    except Exception:  # noqa: BLE001
        return False
    ctype = cond.get("type")
    if ctype == "at_time":
        return str(cond.get("at") or "9999") <= _now_iso()
    if ctype == "window":
        try:
            from schedule import in_window
            return in_window(cond.get("schedule"), datetime.now(timezone.utc))
        except Exception:  # noqa: BLE001
            return False
    if ctype == "price_cross":
        try:
            from price_fetcher import get_price_from_market
            price = get_price_from_market(run["symbol"], None, run["market"])
        except Exception:  # noqa: BLE001
            return False
        if price is None:
            return False
        if cond.get("direction") == "above":
            return float(price) >= float(cond.get("price") or 0)
        return float(price) <= float(cond.get("price") or float("inf"))
    return False


def _transition_row(cursor, run: dict, target: str, reason: str,
                    clear_active_key: bool = False) -> bool:
    """Guarded status flip inside the caller's transaction + journal event."""
    sets = "status = ?, status_reason = ?"
    args: list = [target, reason]
    if clear_active_key:
        sets += ", active_key = NULL, stopped_at = ?"
        args.append(_now_iso())
    cursor.execute(f"UPDATE trading_runs SET {sets} WHERE id = ? AND status = ?",
                   (*args, run["id"], run["status"]))
    if cursor.rowcount != 1:
        return False
    _emit_event(cursor, run["id"], "run_status",
                {"from": run["status"], "to": target, "reason": reason})
    return True


def _simple_transition(run: dict, target: str, reason: str,
                       clear_active_key: bool = False,
                       extra_sets: str = "", extra_args: tuple = ()) -> bool:
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        begin_write_transaction(cursor)
        sets = "status = ?, status_reason = ?"
        args: list = [target, reason]
        if clear_active_key:
            sets += ", active_key = NULL, stopped_at = ?"
            args.append(_now_iso())
            # Mirror of trading_runs._transition: release any position the run
            # still holds back to the unowned book, so the owner can still
            # close it by hand. `run_id` marks an ACTIVE run's book now that
            # sibling runs share a symbol, and every non-run reader filters on
            # `run_id IS NULL`.
            cursor.execute(
                "UPDATE positions SET run_id = NULL WHERE run_id = ? AND agent_id = ?",
                (run["id"], run["agent_id"]))
        if extra_sets:
            sets += ", " + extra_sets
            args.extend(extra_args)
        cursor.execute(f"UPDATE trading_runs SET {sets} WHERE id = ? AND status = ?",
                       (*args, run["id"], run["status"]))
        ok = cursor.rowcount == 1
        if ok:
            _emit_event(cursor, run["id"], "run_status",
                        {"from": run["status"], "to": target, "reason": reason})
        conn.commit()
        return ok
    finally:
        conn.close()


def _alert_run(run: dict, kind: str, title: str, body: str, dedupe: str) -> None:
    try:
        from alerts import send_alert
        send_alert(run["agent_id"], kind, title, body, dedupe_key=dedupe)
    except Exception:  # noqa: BLE001
        logger.debug("run alert failed (run %s)", run["id"], exc_info=True)


def control_pass() -> dict:
    """Zero-LLM control work, every scan:
      * armed: fire start conditions; time out ancient armed runs
      * running/paused: evaluate stop conditions (pause blocks entries, not
        stops or the clock); FAIL CLOSED on evaluation errors/stale marks
      * stopping: flatten (watcher-convention) or hold; bounded retry then
        the explicit stopped(positions_held) terminal
    Every active run is first checked for its `active_key` (see
    _guard_active_key) — a run that lost its exclusivity lock must not trade.
    Returns counters for logs."""
    out = {"armed_started": 0, "stopping_finished": 0, "stops_fired": 0,
           "eval_failures": 0, "keys_healed": 0, "keys_conflicted": 0}
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM trading_runs WHERE status IN (?, ?, ?, ?)",
            (STATUS_ARMED, STATUS_RUNNING, STATUS_PAUSED, STATUS_STOPPING))
        runs = [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()

    for run in runs:
        try:
            if not _guard_active_key(run, out):
                continue
            if run["status"] == STATUS_ARMED:
                _control_armed(run, out)
            elif run["status"] in (STATUS_RUNNING, STATUS_PAUSED):
                _control_active(run, out)
            elif run["status"] == STATUS_STOPPING:
                _control_stopping(run, out)
        except Exception:  # noqa: BLE001
            logger.warning("control pass failed for run %s", run["id"], exc_info=True)
    return out


def _guard_active_key(run: dict, out: dict) -> bool:
    """An active run MUST hold `active_key` — that UNIQUE row is the only
    thing keeping one agent+market+symbol+filter_key to a single run. Runs
    that differ in strategy shape may share a symbol (they hold separate
    `positions` rows); two runs with the SAME shape would race one signal
    with two books, so exactly one of them may hold the key.

    `start_run` is the only writer and `-> stopped` the only clearer, so a
    NULL key here means the row was written outside the state machine (a raw
    DB edit, a half-applied migration, a restore). Reclaim the key when the
    tuple is free; when another run already owns it this run is the genuine
    duplicate and must stop trading. Returns False when the caller should
    skip the run this scan.

    `stopping` is exempt: it takes no entries and only flattens its own
    run-owned position, so letting it finish is safer than stranding it.

    A run that was already active when the filter key shipped holds the legacy
    `agent:market:symbol` form. It is upgraded here rather than left alone:
    a legacy key can never collide with a new-format one, so a genuinely
    duplicate run would otherwise start alongside it. Migration 0027 does the
    same rewrite in bulk — this covers databases that do not run alembic."""
    if run["status"] == STATUS_STOPPING:
        return True
    key = trading_runs._active_key(run["agent_id"], run["market"], run["symbol"],
                                   trading_runs.run_filter_key(run))
    existing = run.get("active_key")
    if existing == key:
        return True
    if existing:
        # Legacy (or otherwise stale) key: claim the correctly-formatted one.
        # Losing the race means a live run already holds this exact strategy
        # slot, so fall through to the duplicate handling below.
        if _reclaim_active_key(run, key, from_key=existing):
            run["active_key"] = key
            return True
        out["keys_conflicted"] += 1
        return _halt_duplicate(run)
    if not _reclaim_active_key(run, key, from_key=None):
        out["keys_conflicted"] += 1
        return _halt_duplicate(run)
    out["keys_healed"] += 1
    logger.warning("run %s was active without an exclusivity key — "
                   "reclaimed %s", run["id"], key)
    run["active_key"] = key
    return True


def _reclaim_active_key(run: dict, key: str, from_key: Optional[str]) -> bool:
    """Claim `key` for this run, conditional on its key still being `from_key`
    (None meaning NULL). False when the UNIQUE index says another live run
    already holds this exact agent+market+symbol+filter slot."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        begin_write_transaction(cursor)
        if from_key is None:
            cursor.execute(
                "UPDATE trading_runs SET active_key = ? WHERE id = ? AND active_key IS NULL",
                (key, run["id"]))
        else:
            cursor.execute(
                "UPDATE trading_runs SET active_key = ? WHERE id = ? AND active_key = ?",
                (key, run["id"], from_key))
        conn.commit()
        return cursor.rowcount == 1
    except Exception:  # noqa: BLE001 — UNIQUE(active_key): another run owns it
        try:
            conn.rollback()
        except Exception:  # noqa: BLE001
            pass
        return False
    finally:
        conn.close()


def _halt_duplicate(run: dict) -> bool:
    """Stop (armed) or pause (running) a run whose strategy slot is taken.
    Always returns False — the caller must skip this run."""
    # armed -> paused is not a legal transition; armed -> stopped is. The
    # stopped branch reuses clear_active_key purely to stamp stopped_at.
    if run["status"] == STATUS_ARMED:
        halted = _simple_transition(run, STATUS_STOPPED, "duplicate_active_key",
                                    clear_active_key=True)
    else:
        halted = _simple_transition(run, STATUS_PAUSED, "duplicate_active_key",
                                    extra_sets="paused_reason = ?",
                                    extra_args=("duplicate_active_key",))
    if halted:
        _alert_run(run, "run_stopped",
                   f"Run #{run['id']} halted: duplicate active run",
                   (f"Another run with the same settings already owns "
                    f"{run['symbol']} ({run['market']}) for this agent, so this "
                    "one was halted before it could race the same signal."),
                   dedupe=f"run:{run['id']}:dup_key")
    return False


def _control_armed(run: dict, out: dict) -> None:
    # Plan 14 §6.7 depth (3): armed runs stay ARMED under an account master
    # hold (armed→paused is an illegal transition and would bypass the start
    # condition on resume). The hold blocks the start here — and suspends the
    # armed-timeout clock, so a long hold cannot silently expire the run
    # ("reversible" must stay true).
    try:
        if _master_held(run["agent_id"]):
            return
    except Exception:  # noqa: BLE001 — fail closed: no start under uncertainty
        return
    started = run.get("started_at")
    if started and _age_seconds(started) > _armed_timeout():
        if _simple_transition(run, STATUS_STOPPED, "armed_timeout",
                              clear_active_key=True):
            _alert_run(run, "run_stopped", f"Run #{run['id']} timed out while armed",
                       (f"Start condition for {run['symbol']} never fired within "
                        f"{_armed_timeout() // 3600}h — the run was stopped."),
                       dedupe=f"run:{run['id']}:armed_timeout")
        return
    if _start_condition_fires(run):
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            begin_write_transaction(cursor)
            if _transition_row(cursor, run, STATUS_RUNNING, "start_condition_fired"):
                out["armed_started"] += 1
            conn.commit()
        finally:
            conn.close()


def _control_active(run: dict, out: dict) -> None:
    """Stop-condition evaluation for running AND paused runs."""
    try:
        reason = _evaluate_stop(run)
        pnl = compute_run_pnl(run)
        _cache_realized_pnl(run["id"], pnl["realized"])
        try:
            from run_reports import evaluate_thresholds
            evaluate_thresholds(run, pnl)
        except Exception:  # noqa: BLE001 — reporting must never block safety
            logger.debug("threshold hook failed (run %s)", run["id"], exc_info=True)
        _maybe_emit_equity(run, pnl)
        # healthy evaluation resets the failure counter
        if int(run.get("consecutive_errors") or 0) > 0:
            conn = get_db_connection()
            try:
                cursor = conn.cursor()
                begin_write_transaction(cursor)
                cursor.execute(
                    "UPDATE trading_runs SET consecutive_errors = 0 WHERE id = ?",
                    (run["id"],))
                conn.commit()
            finally:
                conn.close()
    except Exception as exc:  # noqa: BLE001 — FAIL CLOSED
        out["eval_failures"] += 1
        failures = int(run.get("consecutive_errors") or 0) + 1
        if failures >= _stop_eval_failure_limit():
            # persistent failure escalates to stop — never an infinite
            # pause<->resume livelock
            if _simple_transition(run, STATUS_STOPPING, "stop_eval_failed",
                                  extra_sets="consecutive_errors = ?, stopped_at = ?",
                                  extra_args=(failures, _now_iso())):
                _alert_run(run, "run_stopped", f"Run #{run['id']} stopped: cannot evaluate stops",
                           f"{failures} consecutive stop-evaluation failures "
                           f"({exc}) — stopping for safety.",
                           dedupe=f"run:{run['id']}:eval_stop")
            return
        if run["status"] == STATUS_RUNNING:
            if _simple_transition(run, STATUS_PAUSED, "stop_eval_failed",
                                  extra_sets="consecutive_errors = ?, paused_reason = ?",
                                  extra_args=(failures, "stop_eval_failed")):
                _alert_run(run, "run_stopped", f"Run #{run['id']} paused: stop check failed",
                           f"Stop-condition evaluation failed ({exc}); entries are "
                           "paused until evaluation recovers.",
                           dedupe=f"run:{run['id']}:eval_pause")
        else:
            conn = get_db_connection()
            try:
                cursor = conn.cursor()
                begin_write_transaction(cursor)
                cursor.execute(
                    "UPDATE trading_runs SET consecutive_errors = ? WHERE id = ?",
                    (failures, run["id"]))
                conn.commit()
            finally:
                conn.close()
        return

    if reason is None:
        # auto-recovery: a run we paused for eval failures resumes once
        # evaluation is healthy again (user pauses stay paused)
        if run["status"] == STATUS_PAUSED and run.get("paused_reason") == "stop_eval_failed":
            _simple_transition(run, STATUS_RUNNING, "stop_eval_recovered",
                               extra_sets="paused_reason = NULL", extra_args=())
        return

    out["stops_fired"] += 1
    emit_telemetry_event(run["id"], "alert", {"stop_reason": reason})
    _alert_run(run, "run_stopped", f"Run #{run['id']} stop event: {reason}",
               f"{run['symbol']} ({run['market']}) hit {reason} — "
               + ("flattening position." if run.get("stop_flatten") else
                  "holding position under the SL/TP watcher."),
               dedupe=f"run:{run['id']}:{reason}")
    if _simple_transition(run, STATUS_STOPPING, reason,
                          extra_sets="stopped_at = ?", extra_args=(_now_iso(),)):
        # finish in the SAME scan when possible (flatten or position-less stop)
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM trading_runs WHERE id = ?", (run["id"],))
            fresh = cursor.fetchone()
        finally:
            conn.close()
        if fresh is not None:
            _control_stopping(dict(fresh), out)


# ── auto-restart after a goal-reached stop ────────────────────────────────
# A run that finished its job is cloned and restarted with identical settings,
# so the board never goes idle after a win.
#
# ONLY goal-reached reasons qualify, deliberately:
#   * max_loss / synthetic_liquidation / stop_eval_failed are PROTECTIVE — a
#     restart re-enters the setup that just lost money and turns a one-time
#     loss cap into a repeating loss.
#   * user_stop must stay stopped, or the Stop button resurrects its own run.
#   * at_time / price_cross would re-fire on the very next scan (the deadline
#     is still past, the price still beyond the line) — an instant stop loop.
# That leaves the two reasons whose condition genuinely resets on a fresh run:
# profit_target (P&L back to 0) and max_trades (trade count back to 0).
_RESTARTABLE_STOP_REASONS = frozenset({
    "stop_event:profit_target",
    "stop_event:max_trades",
})


def _auto_restart_enabled() -> bool:
    return os.getenv("RUN_AUTO_RESTART", "true").strip().lower() in ("1", "true", "yes")


def _maybe_auto_restart(run: dict) -> None:
    """Clone a goal-reached run and start the clone, carrying over settings,
    start condition, stop conditions and the flatten flag verbatim.

    Best-effort: any failure (entitlement denial, a conflicting rule, a
    position that reappeared) leaves the original stopped — the safe
    direction — and is logged rather than raised, because this runs inside
    the control pass and must never wedge the scan."""
    reason = run.get("status_reason") or ""
    if reason not in _RESTARTABLE_STOP_REASONS or not _auto_restart_enabled():
        return
    # Plan 14: fleet members NEVER auto-restart — the fleet's slot replacement
    # is the ONLY replacement mechanism. A clone would trade the same symbol
    # with fleet-sized budget outside N, outside the rails, and re-clone on
    # every profit_target hit (the round-2 QA double-deploy critical).
    if run.get("fleet_id") or (run.get("created_via") or "user") == "fleet":
        return
    # Plan 14 §6.7: a held account must not spawn new active runs.
    try:
        if _master_held(run["agent_id"]):
            return
    except Exception:  # noqa: BLE001
        return
    try:
        from trading_runs import create_run, start_run
        settings = json.loads(run.get("config_snapshot_json") or "{}")
        if not settings.get("symbol"):
            return
        new_id = create_run(
            run["agent_id"], settings,
            json.loads(run.get("start_condition_json") or '{"type": "manual"}'),
            json.loads(run.get("stop_conditions_json") or "{}"),
            bool(run.get("stop_flatten")),
        )
        start_run(new_id, run["agent_id"])
    except Exception as exc:  # noqa: BLE001 — never break the control pass
        logger.warning("auto-restart of run %s failed: %s", run["id"], exc)
        return
    emit_telemetry_event(run["id"], "alert",
                         {"auto_restart_run_id": new_id, "stop_reason": reason})
    _alert_run(run, "custom",
               f"Run #{run['id']} reached its goal — restarted as #{new_id}",
               f"{run['symbol']} ({run['market']}) hit {reason}; a new run with "
               "the same settings is live.",
               dedupe=f"run:{run['id']}:auto_restart")


def _control_stopping(run: dict, out: dict) -> None:
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """SELECT id FROM positions
               WHERE agent_id = ? AND market = ? AND symbol = ?
                 AND run_id = ? AND quantity != 0""",
            (run["agent_id"], run["market"], run["symbol"], run["id"]))
        has_position = cursor.fetchone() is not None
    finally:
        conn.close()

    if not has_position:
        if _simple_transition(run, STATUS_STOPPED,
                              run.get("status_reason") or "stop_complete",
                              clear_active_key=True):
            out["stopping_finished"] += 1
            _cache_realized_pnl(run["id"], compute_run_pnl(run)["realized"])
            _maybe_auto_restart(run)
        return

    if not run.get("stop_flatten"):
        # hold: the position stays under the SL/TP watcher, and the stop
        # releases its run_id back to the unowned book — a finished run must
        # not keep the owner from closing by hand. Realized P&L up to the stop
        # is already cached on the run.
        if _simple_transition(run, STATUS_STOPPED, "positions_held",
                              clear_active_key=True):
            out["stopping_finished"] += 1
        return

    ok, why = _flatten_run(run)
    if ok:
        if _simple_transition(run, STATUS_STOPPED,
                              run.get("status_reason") or "stop_complete",
                              clear_active_key=True):
            out["stopping_finished"] += 1
            # reconcile the display cache AFTER the flatten leg landed
            _cache_realized_pnl(run["id"], compute_run_pnl(run)["realized"])
            _maybe_auto_restart(run)
        return
    # bounded retry, then the explicit terminal — a stop can never wedge
    stopping_since = run.get("stopped_at")
    if not stopping_since:
        # self-heal older rows that entered stopping without a stamp
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            begin_write_transaction(cursor)
            stopping_since = _now_iso()
            cursor.execute("UPDATE trading_runs SET stopped_at = ? WHERE id = ?",
                           (stopping_since, run["id"]))
            conn.commit()
        finally:
            conn.close()
    emit_telemetry_event(run["id"], "gate_skip",
                         {"stage": "flatten", "reason": why})
    if stopping_since and _age_seconds(stopping_since) > _flatten_timeout():
        if _simple_transition(run, STATUS_STOPPED, "positions_held",
                              clear_active_key=True):
            out["stopping_finished"] += 1
            _alert_run(run, "run_stopped",
                       f"Run #{run['id']} stopped with positions held",
                       f"Flatten stayed blocked ({why}) past "
                       f"{_flatten_timeout() // 60}min — the position remains "
                       "open under the SL/TP watcher.",
                       dedupe=f"run:{run['id']}:positions_held")


def due_run_ids() -> list[int]:
    """Running runs whose per-run interval has elapsed (interval lives in the
    config snapshot; the comparison is done in Python — dual-dialect date
    math is deliberately avoided)."""
    now = _now_dt()
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, config_snapshot_json, last_cycle_at FROM trading_runs "
            "WHERE status = ?", (STATUS_RUNNING,))
        rows = [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()
    due: list[int] = []
    for row in rows:
        try:
            cfg = json.loads(row.get("config_snapshot_json") or "{}")
            interval_min = max(5, int(cfg.get("interval_minutes") or 60))
            last = row.get("last_cycle_at")
            if not last:
                due.append(row["id"])
                continue
            last_dt = datetime.strptime(last, TS_FMT).replace(tzinfo=timezone.utc)
            if now - last_dt >= timedelta(minutes=interval_min):
                due.append(row["id"])
        except Exception:  # noqa: BLE001
            logger.warning("due-check failed for run %s", row.get("id"), exc_info=True)
    return due


# ── the cycle (sync; runs on the dedicated executor) ───────────────────────

def _claim(run_id: int) -> Optional[dict]:
    """Lease claim: own short committed transaction; atomically increments
    cycle_seq and stamps last_cycle_at. Predicate allows expiry-reclaim and
    owner renewal. Returns the fresh run row on success, None when another
    worker owns the lease or the run left `running`."""
    now = _now_iso()
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        begin_write_transaction(cursor)
        cursor.execute(
            """UPDATE trading_runs
               SET claimed_by = ?, claim_expires_at = ?, cycle_seq = cycle_seq + 1,
                   last_cycle_at = ?
               WHERE id = ? AND status = ?
                 AND (claim_expires_at IS NULL OR claim_expires_at < ? OR claimed_by = ?)""",
            (WORKER_IDENTITY, _iso_in(_lease_ttl()), now, run_id, STATUS_RUNNING,
             now, WORKER_IDENTITY),
        )
        claimed = cursor.rowcount == 1
        conn.commit()
        if not claimed:
            return None
        cursor.execute("SELECT * FROM trading_runs WHERE id = ?", (run_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _release(run_id: int) -> None:
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        begin_write_transaction(cursor)
        cursor.execute(
            """UPDATE trading_runs SET claimed_by = NULL, claim_expires_at = NULL
               WHERE id = ? AND claimed_by = ?""",
            (run_id, WORKER_IDENTITY))
        conn.commit()
    except Exception:  # noqa: BLE001
        logger.debug("lease release failed for run %s", run_id, exc_info=True)
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass


def _fence(run_id: int):
    """Fencing predicate evaluated INSIDE the trade transaction: the lease
    must still be ours and unexpired, and the run must still be running
    (a stop pressed during the in-flight cycle prevents the trade)."""
    def _check(cursor) -> Optional[str]:
        from database import using_mysql
        query = ("SELECT status, claimed_by, claim_expires_at FROM trading_runs "
                 "WHERE id = ?")
        if using_mysql():
            query += " FOR UPDATE"  # row-lock the lease for the txn's duration
        try:
            cursor.execute(query, (run_id,))
        except Exception:  # noqa: BLE001
            return "fence: run row unreadable"
        row = cursor.fetchone()
        if not row:
            return "fence: run vanished"
        if row["status"] != STATUS_RUNNING:
            return f"fence: run is {row['status']}"
        if row["claimed_by"] != WORKER_IDENTITY:
            return "fence: lease reclaimed by another worker"
        if (row["claim_expires_at"] or "") < _now_iso():
            return "fence: lease expired"
        return None
    return _check


def _master_held(agent_id: int) -> bool:
    """Plan 14 §6.7: account-level master hold — the zero-cost pre-gate. A
    held account cannot trade even if an individual object was missed by the
    hold fan-out. Fail CLOSED on lookup errors (money gate)."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT u.ai_automation_state AS s FROM users u "
            "JOIN agents a ON a.user_id = u.id WHERE a.id = ?", (agent_id,))
        row = cursor.fetchone()
        if row is None:
            return False  # unlinked agent — no user-level hold exists
        return (row["s"] or "active") == "held"
    finally:
        conn.close()


def _open_cost_basis(agent_id: int, market: str, symbol: str, run_id: int) -> float:
    """Deployed (open) cost basis of the run's own position row: |qty| × avg
    entry. The Plan 14 run-budget cap input."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """SELECT quantity, entry_price FROM positions
               WHERE agent_id = ? AND market = ? AND symbol = ? AND run_id = ?""",
            (agent_id, market, symbol, run_id))
        row = cursor.fetchone()
        if not row:
            return 0.0
        return abs(float(row["quantity"] or 0)) * float(row["entry_price"] or 0)
    finally:
        conn.close()


def _fleet_cycle_mode(cfg: dict) -> str:
    """Plan 14 §9.2: fleet members default to the LIGHT cycle profile (one
    decision-tier call) — the lever the fleet cost model rests on. Full
    pipeline is per-run opt-in via config, or globally via env."""
    per_run = (cfg.get("cycle_mode") or "").strip().lower()
    if per_run in ("light", "full"):
        return per_run
    return os.getenv("FLEET_CYCLE_MODE", "light").strip().lower()


# Plan 15 P2: the scalar confidence proved quantized (0.62 pin), so the
# desk also scores four components and CODE computes the conviction the
# gate can eventually trust. Weights are deterministic and documented in
# docs/plan/15-run-ai-reading-algorithm-fix.html §5-A.
CONVICTION_WEIGHTS = {
    "thesis_alignment": 0.35,
    "momentum_quality": 0.25,
    "entry_quality": 0.25,
    "risk_context": 0.15,
}


def compute_conviction(scores: Optional[dict]) -> Optional[float]:
    """Weighted blend of the component scores, or None when the model did
    not produce a complete, valid score set (shadow logging must stay honest
    about absence — never fabricate a midpoint)."""
    if not isinstance(scores, dict):
        return None
    total = 0.0
    for key, weight in CONVICTION_WEIGHTS.items():
        try:
            v = float(scores[key])
        except (KeyError, TypeError, ValueError):
            return None
        if not (0.0 <= v <= 1.0):
            return None
        total += weight * v
    return round(total, 4)


def _conviction_size_scale(value: Optional[float]) -> Optional[float]:
    """Plan 15 rec-2: bet-size scale from conviction (or the scalar when no
    scores exist). Linear 0.45→0.75 mapped to 0.40→1.00, clamped — strictly
    shrink-only so it can never lever up. None disables scaling (no signal,
    or the kill-switch is off)."""
    if os.getenv("RUN_SIZE_BY_CONVICTION", "true").strip().lower() not in {"1", "true", "yes", "on"}:
        return None
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return round(max(0.40, min(1.0, (v - 0.45) / 0.30)), 4)


def _conf_v2_enabled() -> bool:
    """Plan 15 P3: flip the gate from the LLM's scalar confidence to the
    computed conviction. Default OFF — enable only after the shadow period
    shows conviction correlates with outcomes better than the scalar."""
    return os.getenv("RUN_CONF_V2", "false").strip().lower() in {"1", "true", "yes", "on"}


def _light_analysis(run: dict, cfg: dict) -> dict:
    """One decision-tier LLM call (agent_planner-style) replacing ONLY the
    analysis stage of run_cycle. Pre-gates, evaluate_execution_gates, the
    run-budget cap and the trade fence are byte-identical to the full path.
    Returns the same {decision: {action, confidence, entry}} shape."""
    import price_fetcher

    entry = None
    try:
        entry = price_fetcher.get_price_from_market(
            run["symbol"], _now_iso(), run["market"])
    except Exception:  # noqa: BLE001
        entry = None
    if entry is None:
        return {"decision": {}, "analysts": {}, "error": "no price"}

    thesis = (cfg.get("thesis") or {}) if isinstance(cfg.get("thesis"), dict) else {}
    candles_summary = None
    try:
        candles = price_fetcher.get_daily_candles(run["symbol"], run["market"], days=30)
        if candles:
            closes = [c["close"] for c in candles[-10:]]
            candles_summary = {"last10_closes": [round(float(c), 6) for c in closes]}
    except Exception:  # noqa: BLE001
        pass

    # Plan 15 P1 (F1/F4): the naked "confidence: 0.0-1.0" ask produced a
    # quantized output pinned at 0.62 (53% of observed decisions), and the
    # desk had no idea what it held — spot runs emitted unactionable sells.
    # Give it the book and a calibration rubric.
    pos_qty = 0.0
    try:
        pos_qty = _position_quantity(run["agent_id"], run["market"],
                                     run["symbol"], run["id"])
    except Exception:  # noqa: BLE001
        pos_qty = 0.0
    market_type = (run.get("market_type") or "spot").strip().lower()
    if trading_runs.is_futures_book(run.get("market"), market_type):
        inventory_rule = ("Futures book: 'sell' opens or extends a short; "
                          "'buy' covers a short or goes long.")
    elif pos_qty > 0:
        inventory_rule = "'sell' reduces/closes this long; 'buy' adds to it."
    else:
        inventory_rule = ("Spot book with no inventory: 'sell' is NOT available "
                          "(nothing to reduce) — a bearish read means 'hold'.")
    prompt = (
        "You are the trading desk for one symbol. Decide THIS cycle's action.\n"
        f"Symbol: {run['symbol']} ({run['market']}, {market_type}), price now {entry}.\n"
        f"Position in this run's book: {pos_qty} units (negative = short, 0 = flat). "
        f"{inventory_rule}\n"
        f"Thesis: {json.dumps(thesis, default=str)[:800]}\n"
        f"Recent closes: {json.dumps(candles_summary, default=str)[:400]}\n"
        "Calibrate confidence honestly across the full range, two decimals: "
        "0.50 = coin-flip, 0.55 = slight edge, 0.65 = clear thesis+momentum+entry "
        "alignment, 0.75 = strong multi-factor confirmation, 0.85+ = exceptional "
        "setup. Do not default to a habitual value; if your report states a "
        "percentage it MUST equal this number.\n"
        "Also score four components, each 0.00-1.00: thesis_alignment (does "
        "price action still support the thesis?), momentum_quality (strength "
        "and cleanliness of the current move), entry_quality (how good is THIS "
        "price as an entry vs the reference?), risk_context (headroom to "
        "invalidation; 1.0 = very safe).\n"
        'Respond ONLY with JSON: {"action": "buy"|"sell"|"hold", '
        '"confidence": 0.0-1.0, "scores": {"thesis_alignment": 0.0-1.0, '
        '"momentum_quality": 0.0-1.0, "entry_quality": 0.0-1.0, '
        '"risk_context": 0.0-1.0}, "report": "<one sentence>"}'
    )
    text = None
    try:
        from llm_client import generate_text
        text = generate_text(prompt, max_tokens=200, temperature=0.2, tier="decision")
    except Exception:  # noqa: BLE001
        text = None
    action, confidence, report = "hold", 0.0, "light cycle: no LLM verdict"
    scores: Optional[dict] = None
    if text:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                obj = json.loads(m.group(0))
                a = str(obj.get("action") or "").strip().lower()
                if a in ("buy", "sell", "hold"):
                    action = a
                confidence = max(0.0, min(1.0, float(obj.get("confidence") or 0)))
                report = str(obj.get("report") or "")[:500]
                raw_scores = obj.get("scores")
                if isinstance(raw_scores, dict):
                    parsed = {}
                    for k in CONVICTION_WEIGHTS:
                        try:
                            parsed[k] = max(0.0, min(1.0, float(raw_scores[k])))
                        except (KeyError, TypeError, ValueError):
                            parsed = None
                            break
                    scores = parsed
            except (ValueError, TypeError):
                pass
    return {"decision": {"action": action, "confidence": confidence,
                         "entry": entry, "report": report, "scores": scores},
            "analysts": {}}


def _pre_gate_skip(run: dict, cfg: dict) -> Optional[str]:
    """Zero-LLM gates evaluated BEFORE run_analysis — a us-stock run cycling
    all weekend must not burn a multi-agent analysis per tick against a
    guaranteed 'market closed' skip (and skipped cycles don't count against
    tick budgets)."""
    from routes_shared import is_market_open

    # Plan 14 §6.7 depth (1): the account-level master hold, checked before
    # anything costs money or LLM.
    try:
        if _master_held(run["agent_id"]):
            return "account AI automation held by master switch"
    except Exception:  # noqa: BLE001 — money gate: fail closed
        return "master-hold check unavailable"

    if not is_market_open(run["market"]):
        return "market closed"
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT cash FROM agents WHERE id = ?", (run["agent_id"],))
        row = cursor.fetchone()
        if row is None:
            return "agent deleted"
        cash = float(row["cash"] or 0)
        cursor.execute(
            """SELECT id FROM positions
               WHERE agent_id = ? AND market = ? AND symbol = ?
                 AND run_id = ? AND quantity != 0""",
            (run["agent_id"], run["market"], run["symbol"], run["id"]))
        has_position = cursor.fetchone() is not None
    finally:
        conn.close()
    max_bet = float(cfg.get("max_bet_usd") or 0)
    if not has_position and cash < max_bet * 1.001:
        return f"insufficient cash for max bet (${cash:.2f} < ${max_bet:.2f})"

    # daily trade cap (always-on per-run rail)
    cap = int(run.get("max_trades_per_day") or 0)
    if cap > 0:
        day_start = _now_dt().strftime("%Y-%m-%dT00:00:00Z")
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT COUNT(*) AS n FROM signals
                   WHERE run_id = ? AND created_at >= ?""",
                (run["id"], day_start))
            if int(cursor.fetchone()["n"] or 0) >= cap:
                return f"daily trade cap reached ({cap}/day)"
        finally:
            conn.close()

    # per-tier daily LLM budget (env-gated enforcement; Plan 10 D9)
    try:
        from entitlements import llm_ticks_exhausted
        conn = get_db_connection()
        try:
            deny = llm_ticks_exhausted(conn.cursor(), run["agent_id"])
            conn.commit()
        finally:
            conn.close()
        if deny:
            return deny
    except Exception:  # noqa: BLE001 — fail closed on spend gates
        return "entitlement check unavailable"
    return None


def _position_quantity(agent_id: int, market: str, symbol: str,
                       run_id: Optional[int]) -> float:
    """Signed position quantity in THIS run's book (negative = short), 0.0
    when flat. Scoped by run_id: a sibling run on the same symbol keeps its
    own row, and reading the combined book would invert the futures
    buy/sell -> short/cover remap."""
    from routes_shared import get_position_snapshot
    conn = get_db_connection()
    try:
        pos = get_position_snapshot(conn.cursor(), agent_id, market, symbol, None, run_id)
        return float(pos["quantity"]) if pos else 0.0
    finally:
        conn.close()


def run_cycle(run_id: int) -> dict:
    """One full cycle: claim -> pre-gates -> analysis -> gates -> trade.
    Sync; called on the dedicated executor. Never raises."""
    result: dict[str, Any] = {"run_id": run_id, "executed": False, "skip_reason": None}
    run = None
    try:
        run = _claim(run_id)
        if run is None:
            result["skip_reason"] = "not claimed (lease held elsewhere or not running)"
            return result
        seq = int(run["cycle_seq"])
        cfg = json.loads(run.get("config_snapshot_json") or "{}")

        # ── Plan 14 §7: feedback pass — zero-LLM, BEFORE pre-gates ─────────
        adapt_state = None
        adapt_params = None
        import run_feedback
        if run_feedback.feedback_enabled(cfg):
            adapt_state = run_feedback.load_state(run)
            pnl = compute_run_pnl(run)
            outcomes = run_feedback.leg_outcomes(
                run, int(adapt_state.get("last_processed_signal_id") or 0))
            adapt_events = run_feedback.ingest_outcomes(adapt_state, outcomes)
            if adapt_state.pop("_reset", None):
                adapt_events.append({"trigger": "state_reset"})
            policy = run_feedback.apply_policy(adapt_state, run, cfg, pnl)
            adapt_events.extend(policy["events"])
            review = run_feedback.maybe_review_thesis(adapt_state, run, cfg, pnl)
            if review:
                emit_telemetry_event(run_id, "thesis_review",
                                     {"cycle": seq, "status": review["status"],
                                      "rationale": review["rationale"]})
                if review["retire"]:
                    policy = {"retire": True, "reason": "thesis_invalidated"}
            if not run_feedback.save_state(run, adapt_state, adapt_events,
                                           WORKER_IDENTITY):
                # lease lost mid-pass: discard adaptation, skip the trade
                result["skip_reason"] = "adapt state fence lost"
                return result
            if policy["retire"]:
                run_feedback.retire_run(run, policy.get("reason") or "adapt")
                result["skip_reason"] = "adapt_retired"
                return result
            if run_feedback.in_cooldown(adapt_state):
                result["skip_reason"] = "adapt loss cooldown"
                emit_telemetry_event(run_id, "gate_skip",
                                     {"cycle": seq, "stage": "adapt",
                                      "reason": "loss cooldown"})
                return result
            adapt_params = run_feedback.effective_gate_params(adapt_state, cfg,
                                                              run_id=run["id"])

        skip = _pre_gate_skip(run, cfg)
        if skip:
            result["skip_reason"] = skip
            emit_telemetry_event(run_id, "gate_skip",
                                 {"cycle": seq, "stage": "pre", "reason": skip})
            _handle_infeasible_skip(run, skip)
            return result

        is_fleet_run = bool(run.get("fleet_id")) or \
            (run.get("created_via") or "user") == "fleet"
        if is_fleet_run and _fleet_cycle_mode(cfg) == "light":
            # Plan 14 §9.2: one decision-tier call — swaps ONLY this stage;
            # everything below (gates, budget cap, fence) is byte-identical.
            analysis = _light_analysis(run, cfg)
        else:
            from analysis_agents import run_analysis
            analysis = run_analysis(run["symbol"], run["market"],
                                    cfg.get("lang") or "en",
                                    provider=cfg.get("provider") or None,
                                    agent_id=run["agent_id"],
                                    llm_tiers=cfg.get("llm_tiers") or None)
        analysts = analysis.get("analysts") if isinstance(analysis.get("analysts"), dict) else {}
        tech_block = analysts.get("technical")
        technical = tech_block.get("data") if isinstance(tech_block, dict) else None
        decision = (analysis.get("decision") or {})
        action = decision.get("action")
        confidence = decision.get("confidence")
        entry = decision.get("entry")
        # Plan 15 P2: conviction is computed HERE from the component scores
        # (shadow next to the legacy scalar in every decision event). P3:
        # when RUN_CONF_V2 is on and a conviction exists, the gate reads it.
        scores = decision.get("scores")
        conviction = compute_conviction(scores)
        use_conviction = _conf_v2_enabled() and conviction is not None
        gate_confidence = conviction if use_conviction else confidence
        size_scale = _conviction_size_scale(
            conviction if conviction is not None else confidence)

        emit_telemetry_event(run_id, "decision",
                             {"cycle": seq, "action": action, "confidence": confidence,
                              "conviction": conviction, "scores": scores,
                              "gate_source": "conviction" if use_conviction else "confidence",
                              "size_scale": size_scale,
                              "entry": entry,
                              "report": (decision.get("report") or "")[:1000]})

        # Futures v1 (Plan 10 D5): the desk decides direction (buy/sell); the
        # futures book translates it. A bearish call with no long to reduce
        # OPENS a short; a bullish call while short COVERS the book instead of
        # buying on top of a negative row. Without this mapping no decision
        # path ever emits 'short', so a futures run could never trade. Spot
        # runs are untouched — a spot 'sell' still only reduces a long.
        if trading_runs.is_futures_book(run.get("market"), run.get("market_type")) \
                and action in ("buy", "sell"):
            pos_qty = _position_quantity(run["agent_id"], run["market"], run["symbol"],
                                         run["id"])
            if action == "sell" and pos_qty <= 0:
                action = "short"
            elif action == "buy" and pos_qty < 0:
                action = "cover"
        elif action == "sell":
            # Plan 15 P1 (F4): a spot 'sell' with an empty book has nothing to
            # reduce. Skip here instead of at the execute stage ("no long
            # position to sell") so the wasted verdict is visible as a gate
            # skip, not an execution failure.
            pos_qty = _position_quantity(run["agent_id"], run["market"], run["symbol"],
                                         run["id"])
            if pos_qty <= 0:
                result["skip_reason"] = "spot sell with no inventory — treated as hold"
                emit_telemetry_event(run_id, "gate_skip",
                                     {"cycle": seq, "stage": "risk",
                                      "reason": result["skip_reason"]})
                return result

        # Plan 14 §7: same-direction re-entry block after a losing close
        # (whipsaw/fee-churn guard) — deterministic, before the gates.
        if adapt_state is not None and \
                run_feedback.blocked_reentry(adapt_state, action):
            result["skip_reason"] = "adapt re-entry blocked after losing close"
            emit_telemetry_event(run_id, "gate_skip",
                                 {"cycle": seq, "stage": "adapt",
                                  "reason": result["skip_reason"]})
            return result

        from automation import evaluate_execution_gates, execute_paper_trade
        # Plan 14 §6.3.2: for fleet-created runs, run_budget_usd is a HARD
        # deployed (open) cost-basis cap enforced at execution — until this,
        # it was validated at creation and then read only by reporting.
        size_usd = cfg.get("max_bet_usd")
        min_confidence = cfg.get("min_confidence")
        if adapt_params is not None:
            size_usd = adapt_params["size_usd"]
            min_confidence = adapt_params["min_confidence"]
        # Plan 15 rec-2 (2026-07-23, Henry-approved): bet size follows stated
        # conviction — "modest long, slight edge only" must not execute a
        # full max_bet. Shrink-only (scale ≤ 1.0), composes with the adapt
        # ladder; kill-switch RUN_SIZE_BY_CONVICTION=0.
        if size_scale is not None and size_usd:
            size_usd = float(size_usd) * size_scale
        if is_fleet_run and cfg.get("run_budget_usd"):
            open_basis = _open_cost_basis(run["agent_id"], run["market"],
                                          run["symbol"], run["id"])
            headroom = float(cfg["run_budget_usd"]) - open_basis
            # Plan 15 overnight (2026-07-23, Henry-approved): floor raised
            # from a flat $10 to max($10, 2% of max_bet) — a $17 headroom on
            # a $5.2k max_bet produced a $17 dust add that burned a cycle and
            # fees for no meaningful exposure.
            headroom_floor = max(10.0, 0.02 * float(cfg.get("max_bet_usd") or 0))
            if action in ("buy", "short") and headroom < headroom_floor:
                result["skip_reason"] = "budget_headroom_skip"
                emit_telemetry_event(run_id, "gate_skip",
                                     {"cycle": seq, "stage": "budget",
                                      "reason": "budget_headroom_skip",
                                      "open_basis": round(open_basis, 2),
                                      "run_budget": cfg["run_budget_usd"]})
                return result
            size_usd = min(float(size_usd or 0), max(headroom, 0.0))
        gate_cfg = {"auto_execute": 1, "account_type": "simulator",
                    "min_confidence": min_confidence,
                    "size_usd": size_usd, "mode": "manual"}
        gates = evaluate_execution_gates(gate_cfg, run["agent_id"], run["symbol"],
                                         run["market"], action, gate_confidence, entry,
                                         None, technical)
        gate = gates.get("gate")
        if gates["skip_reason"] is not None or gate is None:
            result["skip_reason"] = gates["skip_reason"] or "no gate verdict"
            emit_telemetry_event(run_id, "gate_skip",
                                 {"cycle": seq, "stage": "risk",
                                  "reason": result["skip_reason"]})
            return result

        # Plan 15 overnight (2026-07-23): dust guard on the FINAL sized order.
        # The budget-headroom floor upstream only bounds run_budget headroom;
        # the Kelly cap inside the risk engine can still shrink the sized
        # quantity to dust (observed: a $5.18 ZC add, fee half a cent).
        if action in ("buy", "short"):
            sized_notional = float(gate.quantity or 0) * float(entry or 0)
            dust_floor = max(10.0, 0.02 * float(cfg.get("max_bet_usd") or 0))
            if sized_notional < dust_floor:
                result["skip_reason"] = (
                    f"dust order skip (sized ${sized_notional:.2f} "
                    f"< floor ${dust_floor:.2f})")
                emit_telemetry_event(run_id, "gate_skip",
                                     {"cycle": seq, "stage": "risk",
                                      "reason": result["skip_reason"]})
                return result

        # Plan 14 §6.7 depth (2): re-check the master hold immediately before
        # the trade write — a hold landing mid-cycle (past the pre-gate, during
        # the LLM call) turns this cycle into a journaled no-trade skip.
        try:
            if _master_held(run["agent_id"]):
                result["skip_reason"] = "account held (master switch, mid-cycle)"
                emit_telemetry_event(run_id, "gate_skip",
                                     {"cycle": seq, "stage": "master_hold",
                                      "reason": result["skip_reason"]})
                return result
        except Exception:  # noqa: BLE001
            result["skip_reason"] = "master-hold recheck unavailable"
            return result

        client_order_id = f"run:{run_id}:cyc:{seq}"
        signal_id, skip = execute_paper_trade(
            run["agent_id"], run["symbol"], run["market"], action,
            gate.quantity, float(entry),
            content=f"Trading run #{run_id} cycle {seq}",
            stop_loss=gate.stop_loss, take_profit=gate.take_profit,
            run_id=run_id, client_order_id=client_order_id,
            fence=_fence(run_id))
        if signal_id:
            result.update({"executed": True, "signal_id": signal_id})
            _reset_infeasible(run_id)
            # Per-trade alert only when the run opted in (notify_on_trade) —
            # the run_events journal carries the trade either way.
            if run.get("notify_on_trade"):
                try:
                    from alerts import send_alert
                    send_alert(run["agent_id"], "trade_executed",
                               f"{str(action).upper()} {run['symbol']}",
                               (f"Run #{run_id} executed {action} {gate.quantity:.6f} "
                                f"{run['symbol']} @ ${float(entry):.2f} "
                                f"(confidence {confidence})"),
                               dedupe_key=f"run-exec:{signal_id}")
                except Exception:  # noqa: BLE001
                    logger.debug("run trade alert failed (run %s)", run_id)
        else:
            result["skip_reason"] = skip
            emit_telemetry_event(run_id, "gate_skip",
                                 {"cycle": seq, "stage": "execute", "reason": skip})
        return result
    except Exception as exc:  # noqa: BLE001
        logger.exception("run cycle failed (run %s): %s", run_id, exc)
        result["skip_reason"] = f"error: {exc}"
        try:
            emit_telemetry_event(run_id, "gate_skip",
                                 {"stage": "error", "reason": str(exc)[:500]})
        except Exception:  # noqa: BLE001
            pass
        return result
    finally:
        if run is not None:
            _release(run_id)


def _infeasible_limit() -> int:
    try:
        return max(2, int(os.getenv("RUN_INFEASIBLE_LIMIT", "10")))
    except ValueError:
        return 10


def _handle_infeasible_skip(run: dict, skip: str) -> None:
    """A run that can never trade must not burn scheduler attention forever:
    agent-deleted stops immediately; insufficient-cash skips are SKIPS, not
    errors — count them separately and auto-pause at the limit (the
    consecutive-error counter never fires on them)."""
    try:
        if skip == "agent deleted":
            _simple_transition(run, STATUS_STOPPED, "agent_deleted",
                               clear_active_key=True)
            return
        if not skip.startswith("insufficient cash"):
            return
        count = int(run.get("consecutive_infeasible") or 0) + 1
        if count >= _infeasible_limit():
            if _simple_transition(run, STATUS_PAUSED, "infeasible",
                                  extra_sets="consecutive_infeasible = ?, paused_reason = ?",
                                  extra_args=(count, "infeasible")):
                _alert_run(run, "run_stopped",
                           f"Run #{run['id']} paused: cannot fund trades",
                           f"{count} consecutive cycles with insufficient cash "
                           "for the configured max bet — paused until funds "
                           "or settings change.",
                           dedupe=f"run:{run['id']}:infeasible")
            return
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            begin_write_transaction(cursor)
            cursor.execute(
                "UPDATE trading_runs SET consecutive_infeasible = ? WHERE id = ?",
                (count, run["id"]))
            conn.commit()
        finally:
            conn.close()
    except Exception:  # noqa: BLE001
        logger.debug("infeasible bookkeeping failed (run %s)", run.get("id"),
                     exc_info=True)


def _reset_infeasible(run_id: int) -> None:
    try:
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            begin_write_transaction(cursor)
            cursor.execute(
                "UPDATE trading_runs SET consecutive_infeasible = 0 "
                "WHERE id = ? AND consecutive_infeasible != 0", (run_id,))
            conn.commit()
        finally:
            conn.close()
    except Exception:  # noqa: BLE001
        pass


def subscription_enforcer_tick() -> dict:
    """Pause (never delete) active runs whose owner's subscription lapsed —
    runs outlive 30-day plans by design; they resume after renewal. No-op
    unless ENTITLEMENTS_ENFORCED (Plan 10 D9)."""
    out = {"paused": 0}
    from entitlements import enforcement_enabled, limits_for_agent
    if not enforcement_enabled():
        return out
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        # armed runs need no enforcement here: their cycles are blocked by
        # the pre-gate budget check the moment they would spend anything
        cursor.execute("SELECT * FROM trading_runs WHERE status = ?",
                       (STATUS_RUNNING,))
        runs = [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()
    for run in runs:
        try:
            conn = get_db_connection()
            try:
                _, limits = limits_for_agent(conn.cursor(), run["agent_id"])
                conn.commit()
            finally:
                conn.close()
            if int(limits["max_concurrent_runs"]) > 0:
                continue
            if _simple_transition(run, STATUS_PAUSED, "subscription_lapsed",
                                  extra_sets="paused_reason = ?",
                                  extra_args=("subscription_lapsed",)):
                out["paused"] += 1
                _alert_run(run, "run_stopped",
                           f"Run #{run['id']} paused: subscription expired",
                           "Your plan lapsed, so the run was paused (positions "
                           "and stops stay managed). Renew to resume.",
                           dedupe=f"run:{run['id']}:sub_lapsed")
        except Exception:  # noqa: BLE001
            logger.warning("subscription enforcement failed for run %s",
                           run["id"], exc_info=True)
    return out


# ── async tick (called by tasks.trading_run_loop) ──────────────────────────

async def _dispatch(run_id: int) -> None:
    sem = _get_semaphore()
    async with sem:
        loop = asyncio.get_running_loop()
        try:
            result = await loop.run_in_executor(_get_executor(), run_cycle, run_id)
            if result.get("executed"):
                print(f"[TradingRuns] run {run_id} executed signal "
                      f"{result.get('signal_id')}")
        finally:
            _in_flight.discard(run_id)


async def tick() -> dict:
    """One scheduler tick: control pass + dispatch of due cycles."""
    if not auto_trading_enabled():
        return {"enabled": False}
    counters = await asyncio.to_thread(control_pass)
    due = await asyncio.to_thread(due_run_ids)
    dispatched = 0
    for run_id in due:
        if run_id in _in_flight:
            continue  # already queued/executing in this process
        _in_flight.add(run_id)
        asyncio.get_running_loop().create_task(_dispatch(run_id))
        dispatched += 1
    counters.update({"enabled": True, "due": len(due), "dispatched": dispatched})
    return counters
