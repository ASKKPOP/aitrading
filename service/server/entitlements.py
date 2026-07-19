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
PLAN_LIMITS: dict[Optional[str], dict[str, Any]] = {
    None: {"max_concurrent_runs": 0, "max_bet_usd": 0.0,
           "sms_allowed": False, "daily_llm_ticks": 0},
    "junior": {"max_concurrent_runs": 1, "max_bet_usd": 100.0,
               "sms_allowed": False, "daily_llm_ticks": 100},
    "pro": {"max_concurrent_runs": 3, "max_bet_usd": 1_000.0,
            "sms_allowed": False, "daily_llm_ticks": 300},
    "professional": {"max_concurrent_runs": 10, "max_bet_usd": 10_000.0,
                     "sms_allowed": True, "daily_llm_ticks": 1_000},
    "enterprise": {"max_concurrent_runs": 25, "max_bet_usd": 100_000.0,
                   "sms_allowed": True, "daily_llm_ticks": 5_000},
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
    the OpEx attack surface). Counts today's decision events across the
    OWNING USER's runs. Only market-eligible cycles emit decisions, so
    skipped cycles never consume budget."""
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
           WHERE a.user_id = ? AND re.event_type = 'decision' AND re.ts >= ?""",
        (user_id, day_start))
    used = int(cursor.fetchone()["n"] or 0)
    if used >= budget:
        return f"daily analysis budget exhausted ({used}/{budget} cycles today)"
    return None
