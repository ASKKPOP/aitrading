"""Daily compounding of a fleet's working capital.

Owner, 2026-08-09: *"make everyday change available money for trading —
increase or decrease balance by profit."*

A fleet allocates every slot from `fleets.total_budget_usd`, which was FIXED
at the seed the fleet was created with (1000). This job recomputes it once per
UTC day to the account's **realized equity** — the agent's `starting_capital`
plus the sum of realized P&L over its runs — so banked profit compounds into
working capital and realized losses shrink it. Both directions, per the owner.

Two invariants make this safe:

1. **REALIZED only, never unrealized.** An open position marked up is not
   money you have; sizing new exposure off paper gains is the deposit-card
   mistake (see memory `profit-is-the-target-every-layer` and the balance
   fix #328). `seed + Σ realized_pnl_usd` is money actually banked.
2. **Open positions are never touched.** Only the allocation budget changes,
   and that budget governs FUTURE builds/allocations — exactly like a fleet
   resize lowers empty slots without draining live positions. Nothing here
   closes, opens, or resizes a position.

Rides the scheduler tick like `desk_memory_ingest`, throttled to once per UTC
day, and can never fail a trading tick. Kill-switch: FLEET_BUDGET_DAILY=0.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Optional

from database import get_db_connection
from fleet_planner import FLEET_BOUNDS, _NON_TERMINAL

logger = logging.getLogger(__name__)

# Below a cent of change is not worth a write against the trading DB.
_MIN_DELTA_USD = 0.01

_last_day: Optional[str] = None


def _enabled() -> bool:
    return os.environ.get("FLEET_BUDGET_DAILY", "1").strip().lower() not in (
        "0", "false", "no", "off")


def _clamp_budget(value: float) -> float:
    lo, hi = FLEET_BOUNDS["total_budget_usd"]
    return max(lo, min(hi, value))


def compound_fleet_budgets() -> list[dict[str, Any]]:
    """Set each non-terminal fleet's budget to seed + realized. Returns the
    fleets that actually changed (empty when nothing moved)."""
    conn = get_db_connection()
    changed: list[dict[str, Any]] = []
    try:
        cur = conn.cursor()
        placeholders = ", ".join("?" for _ in _NON_TERMINAL)
        cur.execute(
            f"""SELECT f.id, f.agent_id, f.total_budget_usd,
                       a.starting_capital AS seed,
                       COALESCE((SELECT SUM(r.realized_pnl_usd)
                                 FROM trading_runs r
                                 WHERE r.agent_id = f.agent_id), 0) AS realized
                FROM fleets f
                JOIN agents a ON a.id = f.agent_id
                WHERE f.status IN ({placeholders})""",
            tuple(_NON_TERMINAL))
        rows = [dict(r) for r in cur.fetchall()]

        for row in rows:
            seed = row.get("seed")
            if seed is None:
                # An agent with no seed on the row cannot be compounded
                # honestly — skip rather than invent a baseline.
                continue
            current = float(row["total_budget_usd"])
            target = _clamp_budget(float(seed) + float(row["realized"] or 0))
            if abs(target - current) < _MIN_DELTA_USD:
                continue
            cur.execute(
                "UPDATE fleets SET total_budget_usd = ? WHERE id = ?",
                (round(target, 2), int(row["id"])))
            changed.append({"fleet_id": int(row["id"]),
                            "from": round(current, 2), "to": round(target, 2),
                            "realized": round(float(row["realized"] or 0), 4)})
        if changed:
            conn.commit()
        return changed
    finally:
        conn.close()


def maybe_compound(today_utc: Optional[str] = None) -> Optional[dict[str, Any]]:
    """Compound at most once per UTC day. Returns None when throttled or off.

    `today_utc` is passed in (never read from the clock here) so the scheduler
    owns the time source and the throttle is testable — the caller supplies
    the UTC date string; run_engine.tick derives it from the same clock it
    already uses for cycle scheduling."""
    global _last_day
    if not _enabled():
        return None
    if today_utc is None:
        from datetime import datetime, timezone
        today_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if today_utc == _last_day:
        return None
    _last_day = today_utc
    changed = compound_fleet_budgets()
    if changed:
        logger.info("fleet budget compounded (%s): %s", today_utc, changed)
    return {"day": today_utc, "changed": changed}
