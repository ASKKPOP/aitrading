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
    return [r for r in rows
            if _age_minutes(r.get("first_opened_at") or r.get("opened_at"), now) >= floor]


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
    """Attach a protective stop to a bare orphan. Returns True when written."""
    try:
        entry = float(position.get("entry_price") or 0)
    except (TypeError, ValueError):
        return False
    if entry <= 0:
        return False
    frac = default_stop_frac()
    side = (position.get("side") or "").lower()
    stop = entry * (1 - frac) if side in ("long", "buy") else entry * (1 + frac)
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


def sweep(read_desk=None, execute=None) -> dict[str, Any]:
    """One pass. Returns counters; never raises."""
    out = {"scanned": 0, "protected": 0, "exited": 0, "held": 0, "skipped": 0}
    if not enabled():
        return {**out, "disabled": True}
    for pos in find_orphans():
        out["scanned"] += 1
        try:
            verdict = decide(pos, read_desk=read_desk)
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


def sweep_interval_seconds() -> int:
    try:
        return max(60, int(os.getenv("ORPHAN_RECLAIM_INTERVAL", "900")))
    except ValueError:
        return 900


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
                out = sweep()
                if out.get("scanned"):
                    logger.info("[OrphanReclaim] %s", out)
        except Exception:  # noqa: BLE001 — a sweep must never kill the worker
            logger.exception("[OrphanReclaim] pass failed")
        await asyncio.sleep(sweep_interval_seconds())
