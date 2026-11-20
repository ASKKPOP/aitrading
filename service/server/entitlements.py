"""Server-side tier entitlements (Plan 10 D9).

The FIRST backend subscription enforcement in the codebase — gating until
now was frontend-only (App.tsx redirect). PLAN_LIMITS is a deliberate code
dict, not DDL: subscription_plans has no entitlement columns and should not
grow them until the numbers stabilize.

NOTE: the numbers below are PLACEHOLDERS pending Henry's pricing decision
(Plan 10 open question 6). Change them here; everything reads through
limits_for_user / limits_for_agent.

Unlinked agents (agents.user_id IS NULL — the platform's agent-native
principal) have NO subscription and get the zero-entitlement row: barred
from creating/starting runs and from SMS. (Plan 10 open question 9.)
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# plan_code -> entitlements. None key = no active subscription / unlinked agent.
# daily_llm_ticks lowered per Plan 14 §9.2 so the cap actually binds below
# fleet worst cases (the old 1000/5000 never bound at fleet interval floors) —
# still placeholders pending Henry's Q2 confirmation.
PLAN_LIMITS: dict[Optional[str], dict[str, Any]] = {
    None: {"max_concurrent_runs": 0, "max_bet_usd": 0.0,
           "sms_allowed": False, "daily_llm_ticks": 0, "max_fleet_size": 0},
    # SMS enabled on ALL paid tiers (Henry, 2026-07-19); unlinked/no-plan
    # stays SMS-off. Run/bet caps below remain placeholders pending numbers.
    "junior": {"max_concurrent_runs": 1, "max_bet_usd": 100.0,
               "sms_allowed": True, "daily_llm_ticks": 100, "max_fleet_size": 0},
    # max_fleet_size 3 -> 0 (Henry, 2026-08-02): N-symbol Full Auto fleets are
    # Professional+ only; Pro keeps single-run delegation and simple mode.
    "pro": {"max_concurrent_runs": 3, "max_bet_usd": 1_000.0,
            "sms_allowed": True, "daily_llm_ticks": 150, "max_fleet_size": 0},
    "professional": {"max_concurrent_runs": 10, "max_bet_usd": 10_000.0,
                     "sms_allowed": True, "daily_llm_ticks": 400, "max_fleet_size": 10},
    "enterprise": {"max_concurrent_runs": 25, "max_bet_usd": 100_000.0,
                   "sms_allowed": True, "daily_llm_ticks": 2_000, "max_fleet_size": 25},
}


def plan_code_for_user(cursor, user_id: Optional[int]) -> Optional[str]:
    """Active plan code via get_subscription_state (which lazily expires —
    callers that hold a write transaction must commit afterwards)."""
    if not user_id:
        return None
    try:
        from routes_subscriptions import get_subscription_state
        state = get_subscription_state(cursor, user_id) or {}
        sub = state.get("subscription") or {}
        if (sub.get("status") or "") != "active":
            return None
        code = sub.get("plan_code")
        return code if code in PLAN_LIMITS else None
    except Exception:  # noqa: BLE001 — fail CLOSED: no verifiable plan, no entitlements
        logger.warning("plan lookup failed for user %s", user_id, exc_info=True)
        return None


def limits_for_user(cursor, user_id: Optional[int]) -> dict[str, Any]:
    return dict(PLAN_LIMITS[plan_code_for_user(cursor, user_id)])


def limits_for_agent(cursor, agent_id: int) -> tuple[Optional[int], dict[str, Any]]:
    """(owning user_id, limits) for an agent; unlinked agents get zeros."""
    cursor.execute("SELECT user_id FROM agents WHERE id = ?", (agent_id,))
    row = cursor.fetchone()
    user_id = row["user_id"] if row else None
    return user_id, limits_for_user(cursor, user_id)


def sms_allowed_for_user(cursor, user_id: Optional[int]) -> bool:
    """Tier gate applied INSIDE the send path (a creation-time-only check is
    unenforceable — the send path had zero tier awareness before Plan 10)."""
    try:
        return bool(limits_for_user(cursor, user_id)["sms_allowed"])
    except Exception:  # noqa: BLE001 — SMS is a per-message cost: fail closed
        return False


# ── enforcement (env-gated: ships dark until Henry confirms PLAN_LIMITS) ───

def enforcement_enabled() -> bool:
    """ENTITLEMENTS_ENFORCED gates run/automation plan checks. Default off:
    the numbers above are placeholders and the live automation product must
    not change behavior before the rollout decision (Plan 10 Phase 9).
    NOTE: the SMS tier gate is NOT behind this flag — SMS is a direct
    per-message cost and fails closed from day one."""
    import os
    return os.getenv("ENTITLEMENTS_ENFORCED", "false").strip().lower() in (
        "1", "true", "yes", "on")


def check_run_start(cursor, agent_id: int, max_bet_usd: float) -> Optional[str]:
    """Deny reason (or None) for starting a trading run. Checks: linked user
    with an active plan, concurrent-run headroom, max-bet cap."""
    if not enforcement_enabled():
        return None
    user_id, limits = limits_for_agent(cursor, agent_id)
    if user_id is None:
        return "runs require an agent linked to a user account"
    if limits["max_concurrent_runs"] <= 0:
        return "no active subscription allows auto-trading runs"
    cursor.execute(
        """SELECT COUNT(*) AS n FROM trading_runs tr
           JOIN agents a ON a.id = tr.agent_id
           WHERE a.user_id = ? AND tr.status IN ('armed','running','paused','stopping')""",
        (user_id,))
    active = int(cursor.fetchone()["n"] or 0)
    if active >= int(limits["max_concurrent_runs"]):
        return (f"plan allows {limits['max_concurrent_runs']} concurrent run(s); "
                f"{active} already active")
    if float(max_bet_usd) > float(limits["max_bet_usd"]):
        return (f"plan caps max bet at ${limits['max_bet_usd']:.0f} "
                f"(requested ${float(max_bet_usd):.0f})")
    return None


def check_auto_execute(cursor, agent_id: int) -> Optional[str]:
    """Deny reason (or None) for AUTO-EXECUTING automation rules — the same
    gate the runs engine uses, closing the Plan 10 blocker: without this,
    anyone rejected by run limits just creates an automation rule instead."""
    if not enforcement_enabled():
        return None
    user_id, limits = limits_for_agent(cursor, agent_id)
    if user_id is None:
        return "auto-execution requires an agent linked to a user account"
    if limits["daily_llm_ticks"] <= 0:
        return "no active subscription allows auto-execution"
    return None


def llm_ticks_exhausted(cursor, agent_id: int) -> Optional[str]:
    """Per-tier daily LLM-cycle budget (each analysis cycle is LLM spend —
    the OpEx attack surface). Counts today's decision AND thesis_review
    events across the OWNING USER's runs (Plan 14: thesis reviews used to
    check this budget without ever drawing it down). Only market-eligible
    cycles emit decisions, so skipped cycles never consume budget."""
    if not enforcement_enabled():
        return None
    user_id, limits = limits_for_agent(cursor, agent_id)
    budget = int(limits["daily_llm_ticks"])
    if budget <= 0:
        return "no active subscription allows auto-trading"
    from datetime import datetime, timezone
    day_start = datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00Z")
    cursor.execute(
        """SELECT COUNT(*) AS n FROM run_events re
           JOIN trading_runs tr ON tr.id = re.run_id
           JOIN agents a ON a.id = tr.agent_id
           WHERE a.user_id = ? AND re.event_type IN ('decision', 'thesis_review')
             AND re.ts >= ?""",
        (user_id, day_start))
    used = int(cursor.fetchone()["n"] or 0)
    if used >= budget:
        return f"daily analysis budget exhausted ({used}/{budget} cycles today)"
    return None


# ── Plan 14: fleet gates — ALWAYS-ON, deliberately NOT behind
#    enforcement_enabled(). Fleet LLM spend is a direct per-cycle cost, the
#    same class as the SMS gate (which also bypasses the flag). QA verified
#    prod runs ENTITLEMENTS_ENFORCED=false — flag-gated fleet checks would
#    hand any claw_ token an unmetered 25-run fleet.

def plan_code_for_agent(cursor, agent_id: int) -> Optional[str]:
    """Resolved plan of the agent's owning user (None when unlinked)."""
    cursor.execute("SELECT user_id FROM agents WHERE id = ?", (agent_id,))
    row = cursor.fetchone()
    return plan_code_for_user(cursor, row["user_id"] if row else None)


# ── tier feature gates (Henry, 2026-08-02) — ALWAYS-ON, like the fleet
#    gates, deliberately NOT behind enforcement_enabled(): they define the
#    shape of the paid tiers, not placeholder quota numbers. They key on the
#    RESOLVED plan and deny only the tiers named in the spec, so unlinked /
#    no-plan principals (the agent-native path, already barred from runs,
#    fleets and SMS above) keep their existing behavior.
#
#    Junior:       spot only (no futures market_type, no leverage), system
#                  default AI only, no one-off AI Analyst.
#    Pro:          + futures/leverage, own AI by API key, AI Analyst.
#    Professional: + N-symbol Full Auto fleets (max_fleet_size above).
#    Enterprise:   everything (contract tier).

def _resolved_plan_for_agent(agent_id: int) -> Optional[str]:
    """Plan lookup on a fresh connection. Fail-SOFT to None: these gates deny
    a specific named tier, so an unresolvable plan means 'not that tier' —
    the same shape plan_code_for_user already has."""
    try:
        from database import get_db_connection
        conn = get_db_connection()
        try:
            return plan_code_for_agent(conn.cursor(), agent_id)
        finally:
            conn.close()
    except Exception:  # noqa: BLE001
        logger.warning("plan lookup failed for agent %s", agent_id, exc_info=True)
        return None


def check_futures_access(agent_id: int, market_type: str,
                         leverage: float) -> Optional[str]:
    """Deny reason (or None) for a non-spot run. Junior is spot-only."""
    # 'margin' (US-stock short-capable book) is gated like futures.
    if market_type not in ("futures", "margin") and float(leverage or 1.0) <= 1.0:
        return None
    if _resolved_plan_for_agent(agent_id) == "junior":
        return ("the Junior plan is spot-only — futures and leverage need "
                "Pro or higher")
    return None


def check_analyst_access(agent_id: int) -> Optional[str]:
    """Deny reason (or None) for the one-off AI Analyst analysis."""
    if _resolved_plan_for_agent(agent_id) == "junior":
        return ("the Junior plan does not include the AI Analyst — "
                "upgrade to Pro or higher")
    return None


def check_llm_change(cursor, user_id: Optional[int]) -> Optional[str]:
    """Deny reason (or None) for repointing the LLM target away from the
    system default (Junior runs on the platform's default AI only)."""
    if plan_code_for_user(cursor, user_id) == "junior":
        return ("the Junior plan uses the system default AI — changing the "
                "AI provider needs Pro or higher")
    return None


def check_fleet_create(cursor, agent_id: int, n_runs: int) -> Optional[str]:
    """Deny reason (or None) for creating/starting a fleet."""
    user_id, limits = limits_for_agent(cursor, agent_id)
    if user_id is None:
        return "fleets require an agent linked to a user account"
    max_fleet = int(limits.get("max_fleet_size") or 0)
    if max_fleet <= 0:
        return "your plan does not include Full Auto fleets"
    if n_runs > max_fleet:
        return f"plan allows a fleet of at most {max_fleet} run(s) (requested {n_runs})"
    return None
