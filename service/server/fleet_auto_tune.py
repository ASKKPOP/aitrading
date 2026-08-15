"""Continuous AI auto-tuning of a fleet's slot count and take-profit goal.

Owner, 2026-08-12: *"add by AI (automatically by analysis)"* — the Edit-fleet
**profit goal %** and **slot count** should be set by the AI's own analysis,
not typed by the user. The slot side already had an AI recommendation
(`fleet_planner.recommended_max_slots`); this job rides the scheduler tick and
keeps each live fleet's:

  * **slots** at that recommendation (`budget / fee-viable slot size`), so the
    fleet auto-scales as the daily compound grows or shrinks its budget, and
  * **take-profit goal** at a value DERIVED FROM THE FLEET'S OWN REALIZED EDGE
    — "bank when you have earned roughly HORIZON days of your demonstrated
    rate." A fleet with a stronger measured edge banks at a higher gain; a
    fleet with no positive edge yet is left alone (we do not invent a target
    off noise).

AI-first (memory `decisions-become-skills` / `trading-decisions-belong-to-sooppiy-ai`):
this is the PATH that lets the sooppiy AI set fleet config from measured
performance instead of a user click — not a rail that hard-codes an outcome.
It only ever moves allocation config (slot target, goal %); it never touches a
live position — `set_fleet_size` drains empty slots only, and the goal is a
threshold, not a protective rail. Continuous but throttled, and can never fail
a trading tick. Kill-switch: FLEET_AUTO_TUNE=0.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

from database import get_db_connection
from fleet_planner import (
    _NON_TERMINAL,
    emit_fleet_event,
    recommended_max_slots,
    set_fleet_size,
    set_profit_target,
)

logger = logging.getLogger(__name__)

# Re-tune at most this often (seconds). Continuous, but a fleet's slots/goal
# do not need to move every 30-second tick — that would only churn writes.
_INTERVAL_S = float(os.environ.get("FLEET_AUTO_TUNE_INTERVAL_S", "1800") or 1800)

# The goal is "bank ~HORIZON days of the fleet's demonstrated rate". Longer
# horizon ⇒ higher bank-and-restart target ⇒ profit compounds longer before
# recycling.
_HORIZON_DAYS = float(os.environ.get("FLEET_AUTO_TUNE_HORIZON_DAYS", "14") or 14)

# The derived goal is clamped to a sane band (well inside the hard
# profit_target_goal_bounds). A fleet is not asked to bank at under 5% (fees
# churn) nor to sit on a >30% target it may never reach.
_GOAL_LO, _GOAL_HI = 0.05, 0.30

# Do not derive a goal off too little history — noise, not edge.
_MIN_AGE_DAYS = float(os.environ.get("FLEET_AUTO_TUNE_MIN_AGE_DAYS", "1") or 1)
_MIN_CLOSED_RUNS = int(os.environ.get("FLEET_AUTO_TUNE_MIN_RUNS", "5") or 5)

# Below this the goal move is not worth a write.
_MIN_GOAL_DELTA = 0.005

_last_run_epoch: Optional[float] = None


def _enabled() -> bool:
    return os.environ.get("FLEET_AUTO_TUNE", "1").strip().lower() not in (
        "0", "false", "no", "off")


def _age_days(started_at: Optional[str], created_at: Optional[str],
              now: datetime) -> Optional[float]:
    """Days since the fleet began trading (started_at, else created_at)."""
    stamp = started_at or created_at
    if not stamp:
        return None
    try:
        t = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None
    return max(0.0, (now - t).total_seconds() / 86400.0)


def recommended_profit_goal_frac(budget: float, realized: float,
                                 age_days: Optional[float],
                                 closed_runs: int) -> Optional[float]:
    """The AI-derived take-profit goal as a fraction of budget, from the
    fleet's own realized edge over its life. Returns None when there is not
    enough evidence (young fleet, too few closed runs) or no positive edge —
    in those cases the caller leaves the existing goal untouched rather than
    inventing a target off noise."""
    if budget <= 0 or age_days is None or age_days < _MIN_AGE_DAYS:
        return None
    if closed_runs < _MIN_CLOSED_RUNS:
        return None
    if realized <= 0:
        # No demonstrated edge yet — do not set a bank-and-restart target.
        return None
    rate_per_day = realized / age_days
    projected = rate_per_day * _HORIZON_DAYS
    goal = projected / budget
    return max(_GOAL_LO, min(_GOAL_HI, goal))


def auto_tune_fleets() -> list[dict[str, Any]]:
    """Set each non-terminal fleet's slot target to the AI slot recommendation
    and its take-profit goal to the edge-derived value. Returns the fleets
    that actually changed. Per-fleet failures are isolated — one fleet's cap
    rejection never aborts the batch."""
    now = datetime.now(timezone.utc)
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        placeholders = ", ".join("?" for _ in _NON_TERMINAL)
        cur.execute(
            f"""SELECT f.id, f.agent_id, f.n_runs, f.total_budget_usd,
                       f.profit_target_frac, f.user_size_cap,
                       f.started_at, f.created_at,
                       COALESCE((SELECT SUM(r.realized_pnl_usd) FROM trading_runs r
                                 WHERE r.fleet_id = f.id), 0) AS realized,
                       (SELECT COUNT(*) FROM trading_runs r
                        WHERE r.fleet_id = f.id
                          AND r.realized_pnl_usd IS NOT NULL
                          AND r.realized_pnl_usd <> 0) AS closed_runs
                FROM fleets f
                WHERE f.status IN ({placeholders})""",
            tuple(_NON_TERMINAL))
        rows = [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()

    changed: list[dict[str, Any]] = []
    for row in rows:
        fleet_id = int(row["id"])
        change: dict[str, Any] = {"fleet_id": fleet_id}
        moved = False
        budget = float(row["total_budget_usd"] or 0)

        # --- slots: keep at the AI recommendation for the current budget ---
        try:
            rec_slots = recommended_max_slots(budget)
            cur_slots = int(row["n_runs"])
            # Clamp to the plan's entitlement cap (live 2026-08-12, fleet
            # 32: rec 25 vs cap 10 raised EntitlementDenied every pass — log
            # churn, and the resize never landed). cap==0 means the plan has
            # no fleet entitlement at all (grandfathered fleet): never RAISE,
            # lowering stays allowed.
            import entitlements
            cconn = get_db_connection()
            try:
                _, limits = entitlements.limits_for_agent(
                    cconn.cursor(), int(row["agent_id"]))
            finally:
                cconn.close()
            cap = int(limits.get("max_fleet_size") or 0)
            if cap > 0:
                rec_slots = min(rec_slots, cap)
            elif rec_slots > cur_slots:
                rec_slots = cur_slots
            # The user's own hand outranks the recommendation (owner decision
            # 2026-08-15, after auto-tune undid a user's 25->10 within 27
            # minutes, twice in one day). A resize-API size is a CAP: never
            # raise above it; lowering (the fee-viability shrink) still runs.
            user_cap = row.get("user_size_cap")
            if user_cap is not None and rec_slots > int(user_cap):
                rec_slots = int(user_cap)
            if rec_slots != cur_slots:
                set_fleet_size(fleet_id, rec_slots)
                emit_fleet_event(fleet_id, "auto_tune_slots",
                                 {"from": cur_slots, "to": rec_slots})
                change["slots"] = {"from": cur_slots, "to": rec_slots}
                moved = True
        except Exception:  # noqa: BLE001
            logger.warning("auto-tune slots failed for fleet %s", fleet_id,
                           exc_info=True)

        # --- goal: derive from the fleet's own realized edge ---
        try:
            age = _age_days(row.get("started_at"), row.get("created_at"), now)
            rec_goal = recommended_profit_goal_frac(
                budget, float(row["realized"] or 0), age,
                int(row["closed_runs"] or 0))
            if rec_goal is not None:
                cur_goal = float(row["profit_target_frac"] or 0)
                if abs(rec_goal - cur_goal) >= _MIN_GOAL_DELTA:
                    rec_goal = round(rec_goal, 4)
                    set_profit_target(fleet_id, rec_goal)
                    emit_fleet_event(fleet_id, "auto_tune_goal",
                                     {"from": round(cur_goal, 4),
                                      "to": rec_goal})
                    change["goal"] = {"from": round(cur_goal, 4), "to": rec_goal}
                    moved = True
        except Exception:  # noqa: BLE001
            logger.warning("auto-tune goal failed for fleet %s", fleet_id,
                           exc_info=True)

        if moved:
            changed.append(change)
    return changed


def maybe_tune(now_epoch: Optional[float] = None) -> Optional[dict[str, Any]]:
    """Auto-tune at most once per interval. Returns None when throttled or off.

    `now_epoch` is passed in so the scheduler owns the time source and the
    throttle is testable — run_engine.tick derives it from the same clock it
    already uses for scheduling."""
    global _last_run_epoch
    if not _enabled():
        return None
    if now_epoch is None:
        now_epoch = datetime.now(timezone.utc).timestamp()
    if _last_run_epoch is not None and (now_epoch - _last_run_epoch) < _INTERVAL_S:
        return None
    _last_run_epoch = now_epoch
    changed = auto_tune_fleets()
    if changed:
        logger.info("fleet auto-tune: %s", changed)
    return {"changed": changed}
