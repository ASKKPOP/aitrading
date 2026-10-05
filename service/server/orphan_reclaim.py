"""Positions no run owns — the daemon's job, not the owner's.

A position ends up unowned two legitimate ways: a run releases `run_id` on
stop (run_engine: "close it by hand"), or a manual terminal fill never had one.
Both are by design. What was missing is anyone LOOKING at the result.

Live 2026-07-28 on prod, three consequences of leaving them:

  * position 13 (SOL long) sat unowned with NO stop for eight days at −5.6%.
    Nothing was watching it and nothing ever would have been.
  * position 67 (SOLUSDT short) sat +$7.29 in profit with no exit plan.
  * both permanently deleted their symbol from the fleet's universe — the
    build path refuses a symbol an unowned position holds ("runs never adopt a
    book they did not open; attribution would be wrong"), so SOLUSDT survived
    every gate and was still skipped, slot after slot.

That last one compounds: every orphan removes a symbol forever.

What this does NOT do is invent a view. The decision to close is the desk's,
taken through the same analysis path a run uses, so an orphan is treated
exactly like a position the fleet holds. The only thing done unilaterally is
PROTECTION — attaching the account's default stop to a position that has none
is strictly safer than leaving it bare, and it is what the SL/TP watcher
already expects to find.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from database import begin_write_transaction, get_db_connection

logger = logging.getLogger(__name__)

RECLAIM_EXIT = "exit"
RECLAIM_PROTECT = "protect"
RECLAIM_HOLD = "hold"


def enabled() -> bool:
    """Default OFF. This path closes positions; it ships dark and is turned on
    deliberately, the same way every other money-moving loop here did."""
    return os.getenv("ORPHAN_RECLAIM_ENABLED", "false").strip().lower() in (
        "1", "true", "yes", "on")


def min_age_minutes() -> int:
    """Grace period before an unowned position is considered abandoned.

    A run's stop releases run_id BEFORE the replacement is built, so a freshly
    released position is normal for a few minutes and must not be touched."""
    try:
        return max(5, int(os.getenv("ORPHAN_RECLAIM_AFTER_MIN", "120")))
    except ValueError:
        return 120


def default_stop_frac() -> float:
    """Protective stop attached to a bare orphan, as a fraction of entry."""
    try:
        return min(0.5, max(0.005, float(
            os.getenv("ORPHAN_DEFAULT_STOP_FRAC", "0.05") or 0.05)))
    except ValueError:
        return 0.05


def _age_minutes(opened_at: "str | None", now_iso: str) -> float:
    """Minutes between two ISO stamps. Compares the first 19 characters so a
    microsecond tail or a trailing Z cannot break the parse — the same
    convention run_feedback uses for exactly this reason."""
    if not opened_at:
        return 0.0
    from datetime import datetime
    try:
        a = datetime.strptime(opened_at[:19], "%Y-%m-%dT%H:%M:%S")
        b = datetime.strptime(now_iso[:19], "%Y-%m-%dT%H:%M:%S")
    except (ValueError, TypeError):
        return 0.0
    return max(0.0, (b - a).total_seconds() / 60.0)


def find_orphans(agent_id: "int | None" = None) -> list[dict[str, Any]]:
    """Unowned, non-zero positions old enough to be considered abandoned.

    `run_id IS NULL` is the whole definition of unowned — run_engine sets it
    on every terminal, and the manual paths never set it at all."""
    from run_engine import _now_iso
    now = _now_iso()
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        sql = ("SELECT * FROM positions WHERE run_id IS NULL AND quantity != 0")
        params: tuple = ()
        if agent_id is not None:
            sql += " AND agent_id = ?"
            params = (agent_id,)
        cursor.execute(sql, params)
        rows = [dict(r) for r in cursor.fetchall()]
    except Exception:  # noqa: BLE001 — a sweep must never break the worker
        logger.debug("orphan scan failed", exc_info=True)
        return []
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass
    floor = min_age_minutes()
    managed = _module_managed_agents()
    if managed is None:
        return []
    return [r for r in rows
            if r.get("agent_id") not in managed
            and _age_minutes(r.get("first_opened_at") or r.get("opened_at"), now) >= floor]


def _module_managed_agents() -> "set[int] | None":
    """The accounts the trend module trades, while that module is running:
    its dedicated agent and every enrolled trend account (Plan 32). None
    when the module is on and its enrolment cannot be read — the sweep then
    sits this pass out rather than guess which rows are the module's.

    Its positions carry run_id NULL by design — no run owns them, the module
    does, with its own stop (1.5×ATR, judged on the daily close) kept in
    platform_settings rather than on the row. To this sweep that looked
    "unowned and unprotected", so it attached the account's 5% stop and the
    SL/TP watcher closed on it intraday: prod 2026-09-18, the module's XRP
    short was taken out at 1.3423 by this job, not by its own rule, and both
    positions open on 2026-10-05 carried such stops. With the module switched
    off nobody manages those rows and they are orphans again."""
    try:
        import trend_module
        if not trend_module.module_enabled():
            return set()
        managed = {trend_module._agent_id()}
    except Exception:  # noqa: BLE001 — never break the sweep
        return set()
    try:
        import trend_accounts
        return managed | {int(a["agent_id"]) for a in trend_accounts._read()}
    except ValueError:      # stored value does not validate: enrols nobody
        return managed
    except Exception:  # noqa: BLE001
        logger.warning("orphan sweep: trend accounts unreadable — skipping "
                       "this pass", exc_info=True)
        return None


def decide(position: dict[str, Any], read_desk=None) -> dict[str, Any]:
    """What to do with one orphan. The direction call is the DESK's.

    An unprotected position is protected regardless of the read — that is not
    a market view, it is the missing safety net, and it costs nothing if the
    desk turns out to be right about direction.
    """
    side = (position.get("side") or "").lower()
    bare = position.get("stop_loss") is None and position.get("take_profit") is None
    verdict = None
    if read_desk is not None:
        try:
            verdict = read_desk(position)
        except Exception:  # noqa: BLE001 — an unreadable desk is a HOLD, never
            verdict = None  # an exit: we do not close on a guess

    # The desk reading the opposite way is the only thing that closes a
    # position here. Same rule the runs use: a long book cannot express a
    # bearish read, so holding it is the position being wrong, not waiting.
    if verdict in ("sell", "short") and side in ("long", "buy"):
        return {"action": RECLAIM_EXIT, "reason": "desk reads against a long orphan"}
    if verdict in ("buy", "long") and side in ("short", "sell"):
        return {"action": RECLAIM_EXIT, "reason": "desk reads against a short orphan"}
    if bare:
        return {"action": RECLAIM_PROTECT,
                "reason": "unowned and unprotected — attaching a stop"}
    return {"action": RECLAIM_HOLD, "reason": "protected; desk has not turned"}


def protect(position: dict[str, Any]) -> bool:
    """Attach a protective stop to a bare orphan. Returns True when written.

    Measured from the CURRENT MARK when the position is underwater, not from
    entry. An entry-relative stop on a losing position is not protection — it
    sits on the wrong side of the mark and the SL/TP watcher fills it at once.

    Live 2026-07-28, my own bug: position 13 (SOL long, entry 77.442) was
    -5.4% when the first sweep ran. A 5% stop off ENTRY put the trigger at
    73.5699 while the mark was 73.134 — already through it. The watcher closed
    the position 31 seconds later for -$25.72. Correct outcome for an eight-day
    abandoned position, but it was a liquidation dressed as a safety net.

    Anchoring on min(entry, mark) for a long — max for a short — keeps the stop
    a full `frac` away on the losing side whatever the position is worth now.
    """
    try:
        entry = float(position.get("entry_price") or 0)
    except (TypeError, ValueError):
        return False
    if entry <= 0:
        return False
    frac = default_stop_frac()
    side = (position.get("side") or "").lower()
    try:
        mark = float(position.get("current_price"))
    except (TypeError, ValueError):
        mark = entry            # no mark: entry is the only anchor we have
    if mark <= 0:
        mark = entry
    if side in ("long", "buy"):
        stop = min(entry, mark) * (1 - frac)
    else:
        stop = max(entry, mark) * (1 + frac)
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        begin_write_transaction(cursor)
        # Only fill a NULL — never move a stop somebody already set.
        cursor.execute(
            "UPDATE positions SET stop_loss = ? WHERE id = ? AND stop_loss IS NULL",
            (stop, position["id"]))
        conn.commit()
        return True
    except Exception:  # noqa: BLE001
        logger.debug("orphan protect failed for %s", position.get("id"), exc_info=True)
        return False
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass


def sweep(read_desk=None, execute=None, blocking=None) -> dict[str, Any]:
    """One pass. Returns counters; never raises.

    The desk is consulted ONLY for an orphan that is currently refusing a
    fleet slot. Every orphan gets protection; only a blocking one is worth an
    LLM call, because only a blocking one has a cost that closing would
    recover.
    """
    out = {"scanned": 0, "protected": 0, "exited": 0, "held": 0,
           "skipped": 0, "blocking": 0}
    if not enabled():
        return {**out, "disabled": True}
    out["ghosts_deleted"] = _delete_ghost_rows()
    blocked = blocking_symbols() if blocking is None else blocking
    if not isinstance(blocked, dict):        # a bare set from a caller/test
        blocked = {s: 0 for s in blocked}
    for pos in find_orphans():
        out["scanned"] += 1
        is_blocking = (pos.get("symbol") or "") in blocked
        if is_blocking:
            out["blocking"] += 1
        reader = None
        if is_blocking and read_desk is not None:
            cached = recent_verdict(str(pos.get("symbol") or ""))
            if cached is not None:
                out["cached"] = out.get("cached", 0) + 1
                reader = lambda _p, _v=cached: _v          # noqa: E731
            else:
                _fid = blocked.get(str(pos.get("symbol") or "")) or 0

                def reader(p, _rd=read_desk, _f=_fid):     # noqa: F811
                    v = _rd(p)
                    journal_verdict(p, v, fleet_id=_f)
                    return v
        try:
            verdict = decide(pos, read_desk=reader)
        except Exception:  # noqa: BLE001
            out["skipped"] += 1
            continue
        action = verdict["action"]
        if action == RECLAIM_PROTECT:
            out["protected"] += 1 if protect(pos) else 0
        elif action == RECLAIM_EXIT:
            if execute is None:
                out["skipped"] += 1
                continue
            try:
                execute(pos, verdict)
                out["exited"] += 1
            except Exception:  # noqa: BLE001
                logger.warning("orphan exit failed for %s", pos.get("id"),
                               exc_info=True)
                out["skipped"] += 1
        else:
            out["held"] += 1
    return out


def _delete_ghost_rows() -> int:
    """Plan 24 fix 2 residue: an unowned position row at exactly zero
    quantity carries no risk and no decision content — it is bookkeeping
    debris (live 2026-08-12: agent 6 held a 0E-8 USDKRW row that every
    monitoring query tripped over). Owned rows are left alone: a run's own
    zero row is the run engine's to manage."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        begin_write_transaction(cursor)
        cursor.execute(
            "DELETE FROM positions WHERE run_id IS NULL AND quantity = 0")
        n = cursor.rowcount
        conn.commit()
        return max(0, int(n or 0))
    except Exception:  # noqa: BLE001 — hygiene must never break the sweep
        logger.debug("ghost-row cleanup failed", exc_info=True)
        return 0
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass


BLOCKING_REASON = "an open position already exists for this symbol"


def blocking_symbols(within_minutes: int = 180) -> dict:
    """(market, symbol) pairs whose unowned position is refusing a fleet slot.

    The build path already journals this — `candidate_skipped` with
    "an open position already exists for this symbol outside any run — close it
    first". Live on prod it repeated every 60 s for hours: SOLUSDT cleared the
    fee gate AND the expectancy gate on every tick and was refused on every
    tick, holding the fleet at 2/10.

    A skip that repeats forever is not a decision, it is a question nobody
    asked. These are the orphans worth spending an LLM call on: the ones with
    a measurable cost.
    """
    from run_engine import _now_iso
    from datetime import datetime, timedelta
    try:
        cutoff = (datetime.strptime(_now_iso()[:19], "%Y-%m-%dT%H:%M:%S")
                  - timedelta(minutes=max(1, within_minutes))).strftime(
                      "%Y-%m-%dT%H:%M:%SZ")
    except (ValueError, TypeError):
        return {}
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """SELECT fleet_id, payload FROM fleet_events
               WHERE event_type = 'candidate_skipped' AND ts >= ?
               ORDER BY id DESC LIMIT 200""", (cutoff,))
        rows = cursor.fetchall()
    except Exception:  # noqa: BLE001
        return {}
    finally:
        try:
            if conn is not None:
                conn.close()
        except Exception:  # noqa: BLE001
            pass
    import json as _json
    # symbol -> the fleet whose slot it is refusing, so the verdict is
    # journalled against the fleet that actually paid for it.
    out: dict = {}
    for row in rows:
        try:
            p = _json.loads(row["payload"] or "{}")
        except (ValueError, TypeError):
            continue
        if BLOCKING_REASON in str(p.get("reason") or ""):
            sym = p.get("symbol")
            if sym and str(sym) not in out:
                out[str(sym)] = row["fleet_id"]
    return out


def desk_cooldown_minutes() -> int:
    """How long a desk verdict on one symbol stands before it is re-asked.

    The sweep runs every 15 minutes and the desk read is the FULL four-analyst
    pipeline — measured on prod 2026-07-28: 14 LLM calls, $0.36 for a single
    blocking position. Re-asking every sweep is ~$35/day to keep re-deciding a
    question whose answer barely moves, more than the platform's entire prior
    daily LLM spend. An orphan that has blocked for hours is not urgent."""
    try:
        return max(5, int(os.getenv("ORPHAN_DESK_COOLDOWN_MIN", "60")))
    except ValueError:
        return 60


def recent_verdict(symbol: str) -> "str | None":
    """The last journaled desk verdict for `symbol` inside the cooldown.

    Read back from fleet_events rather than an in-process dict so a worker
    restart does not re-bill the read — and so the daemon's autonomous
    decisions leave an audit trail, which matters more here than for a gate
    that only ever refuses."""
    from run_engine import _now_iso
    from datetime import datetime, timedelta
    try:
        cutoff = (datetime.strptime(_now_iso()[:19], "%Y-%m-%dT%H:%M:%S")
                  - timedelta(minutes=desk_cooldown_minutes())
                  ).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (ValueError, TypeError):
        return None
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """SELECT payload FROM fleet_events
               WHERE event_type = 'orphan_verdict' AND ts >= ?
               ORDER BY id DESC LIMIT 50""", (cutoff,))
        rows = cursor.fetchall()
    except Exception:  # noqa: BLE001
        return None
    finally:
        try:
            if conn is not None:
                conn.close()
        except Exception:  # noqa: BLE001
            pass
    import json as _json
    for row in rows:
        try:
            p = _json.loads(row["payload"] or "{}")
        except (ValueError, TypeError):
            continue
        if str(p.get("symbol") or "") == symbol:
            return str(p.get("verdict") or "") or None
    return None


def journal_verdict(position: dict, verdict: "str | None",
                    fleet_id: int = 0) -> None:
    """Record a desk verdict so the cooldown can see it and a human can audit
    why the daemon kept or closed someone's position."""
    try:
        import fleet_planner as fp
        fp.emit_fleet_event(fleet_id, "orphan_verdict",
                            {"symbol": position.get("symbol"),
                             "market": position.get("market"),
                             "side": position.get("side"),
                             "position_id": position.get("id"),
                             "verdict": verdict})
    except Exception:  # noqa: BLE001 — journalling must never block the sweep
        # WARNING, not debug: a failed journal means the cooldown cannot see
        # this verdict and the next sweep re-bills the full desk read. Silent
        # here would be a money leak that looks like normal operation.
        logger.warning("orphan verdict journal failed for %s — the desk read "
                       "will be repeated next sweep", position.get("symbol"),
                       exc_info=True)


def desk_read(position: dict) -> "str | None":
    """Ask the desk which way it reads this symbol RIGHT NOW.

    Same pipeline a run cycle uses (analysis_agents.run_analysis), so an
    orphan is judged exactly like a position the fleet holds — no second,
    weaker opinion path. Returns the action string or None; None is a HOLD,
    never an exit.
    """
    try:
        from analysis_agents import run_analysis
        out = run_analysis(position.get("symbol") or "",
                           position.get("market") or "crypto",
                           agent_id=position.get("agent_id"))
        action = ((out or {}).get("decision") or {}).get("action")
        return str(action).lower() if action else None
    except Exception:  # noqa: BLE001 — an unreadable desk is a HOLD
        logger.debug("desk read failed for %s", position.get("symbol"),
                     exc_info=True)
        return None


def exit_enabled() -> bool:
    """Second, separate switch for the CLOSING half.

    Protection can be turned on with no market consequence; closing cannot.
    They are deliberately not the same flag."""
    return os.getenv("ORPHAN_RECLAIM_EXIT", "false").strip().lower() in (
        "1", "true", "yes", "on")


def sweep_interval_seconds() -> int:
    try:
        return max(60, int(os.getenv("ORPHAN_RECLAIM_INTERVAL", "900")))
    except ValueError:
        return 900


def close_orphan(position: dict, verdict: dict) -> None:
    """Close an orphan the desk has turned against.

    Routed through execute_paper_trade — the same executor the runs and the
    SL/TP watcher use — so fees, the ledger and the signal journal all behave
    identically to any other exit. Idempotent via the client_order_id, which
    is what stops a retry double-closing.
    """
    from automation import execute_paper_trade
    qty = abs(float(position.get("quantity") or 0))
    mark = position.get("current_price")
    if qty <= 0 or mark is None:
        raise ValueError("no quantity or no mark to close against")
    side = "cover" if (position.get("side") or "").lower() in ("short", "sell") else "sell"
    signal_id, skip = execute_paper_trade(
        position["agent_id"], position["symbol"], position["market"],
        side, qty, float(mark),
        content=f"Orphan reclaim — {verdict.get('reason') or 'desk turned'}",
        client_order_id=f"orphan:{position['id']}:reclaim")
    if not signal_id and not (skip and "duplicate client_order_id" in str(skip)):
        raise RuntimeError(skip or "close refused")


async def orphan_reclaim_loop() -> None:
    """Registry key 'orphan_reclaim', role 'settlement'.

    PROTECT-only for now, and that is a complete answer rather than half of
    one: attaching a stop hands the position to the SL/TP watcher, which is
    the component that already owns exits and has done since Phase 1. No new
    close path is introduced, so nothing here can liquidate anything the
    watcher would not have.

    Closing on a desk read (orphan_reclaim.decide's RECLAIM_EXIT branch) stays
    dark until the read is wired: sweep() without an `execute` counts those as
    skipped rather than silently dropping them.
    """
    import asyncio

    await asyncio.sleep(11)
    while True:
        try:
            if enabled():
                out = sweep(read_desk=desk_read if exit_enabled() else None,
                            execute=close_orphan if exit_enabled() else None)
                if out.get("scanned"):
                    logger.info("[OrphanReclaim] %s", out)
        except Exception:  # noqa: BLE001 — a sweep must never kill the worker
            logger.exception("[OrphanReclaim] pass failed")
        await asyncio.sleep(sweep_interval_seconds())
