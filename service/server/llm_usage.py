"""LLM usage metering (Plan 11 F2).

Every generate_text call records one llm_usage row: who (user/agent via the
LlmContext), what (provider/model/tier), how much (prompt/completion tokens),
and an estimated cost from the static price table below. Recording is
fail-soft — a metering problem must never break an LLM call.

Prices are public list prices in USD per 1M tokens (input, output), matched by
longest model-name prefix; unknown models cost 0 and are still counted. The
Settings page labels everything as an estimate.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from database import get_db_connection

logger = logging.getLogger(__name__)

# (model prefix, $ per 1M input tokens, $ per 1M output tokens)
_PRICES: tuple[tuple[str, float, float], ...] = (
    ("claude-opus", 15.0, 75.0),
    ("claude-sonnet", 3.0, 15.0),
    ("claude-haiku", 0.80, 4.0),
    ("gpt-4o-mini", 0.15, 0.60),
    ("gpt-4o", 2.50, 10.0),
    ("gemini-2.0-flash", 0.10, 0.40),
    ("gemini", 0.10, 0.40),
    ("grok", 2.0, 10.0),
    ("qwen-plus", 0.40, 1.20),
    ("qwen", 0.40, 1.20),
    ("glm", 0.60, 0.60),
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Estimated USD cost for one call. Unknown models -> 0 (still metered)."""
    name = (model or "").lower()
    if "/" in name:  # openrouter-style vendor prefix: openai/gpt-4o-mini
        name = name.split("/", 1)[1]
    for prefix, in_per_m, out_per_m in _PRICES:
        if name.startswith(prefix):
            return (prompt_tokens * in_per_m + completion_tokens * out_per_m) / 1_000_000
    return 0.0


def record_usage(*, provider: str, model: str, tier: str, key_source: str,
                 user_id: Optional[int], agent_id: Optional[int],
                 prompt_tokens: int, completion_tokens: int) -> None:
    """Insert one usage row. Fail-soft: log and continue on any error."""
    try:
        cost = estimate_cost(model, prompt_tokens, completion_tokens)
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO llm_usage
               (user_id, agent_id, provider, model, tier, key_source,
                prompt_tokens, completion_tokens, cost_usd, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (user_id, agent_id, provider, model, tier, key_source,
             int(prompt_tokens or 0), int(completion_tokens or 0),
             round(cost, 6), _now_iso()))
        conn.commit()
        conn.close()
    except Exception as exc:  # noqa: BLE001 — metering must never break the call
        logger.warning("llm_usage recording failed: %s", exc)


def _aggregate(cursor, since_iso: str, user_id: Optional[int]) -> dict[str, Any]:
    """Aggregates for rows since `since_iso`; user_id None = all rows (system)."""
    where = "created_at >= ?"
    params: list[Any] = [since_iso]
    if user_id is not None:
        where += " AND user_id = ?"
        params.append(user_id)
    cursor.execute(
        f"""SELECT provider, model, COUNT(*) AS calls,
                   SUM(prompt_tokens) AS prompt_tokens,
                   SUM(completion_tokens) AS completion_tokens,
                   SUM(cost_usd) AS cost_usd
            FROM llm_usage WHERE {where}
            GROUP BY provider, model ORDER BY cost_usd DESC""", params)
    models = []
    total_cost = 0.0
    total_calls = 0
    for row in cursor.fetchall():
        r = dict(row)
        r["cost_usd"] = round(float(r["cost_usd"] or 0), 4)
        r["prompt_tokens"] = int(r["prompt_tokens"] or 0)
        r["completion_tokens"] = int(r["completion_tokens"] or 0)
        total_cost += r["cost_usd"]
        total_calls += int(r["calls"] or 0)
        models.append(r)
    return {"models": models, "total_cost_usd": round(total_cost, 4),
            "total_calls": total_calls}


def _aggregate_by_service(cursor, since_iso: str, user_id: Optional[int]) -> list[dict]:
    """Same window, grouped by `tier` — the service that made the call
    (decision, brief, …) rather than the model that served it."""
    where = "created_at >= ?"
    params: list[Any] = [since_iso]
    if user_id is not None:
        where += " AND user_id = ?"
        params.append(user_id)
    cursor.execute(
        f"""SELECT tier AS service, COUNT(*) AS calls,
                   SUM(cost_usd) AS cost_usd
            FROM llm_usage WHERE {where}
            GROUP BY tier ORDER BY cost_usd DESC""", params)
    return [{"service": r["service"], "calls": int(r["calls"] or 0),
             "cost_usd": round(float(r["cost_usd"] or 0), 4)}
            for r in (dict(x) for x in cursor.fetchall())]


def _month_bounds(now: datetime) -> tuple[datetime, datetime]:
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    nxt = (start.replace(year=start.year + 1, month=1) if start.month == 12
           else start.replace(month=start.month + 1))
    return start, nxt


def project_month_end(spent_usd: float, now: Optional[datetime] = None) -> float:
    """Straight-line run-rate projection of this month's total spend.

    Deliberately naive: spend-to-date scaled by the fraction of the month
    elapsed. It is a run rate, not a forecast — it assumes the rest of the
    month looks like the part already observed, so it swings wildly in the
    first hours of a month. Callers label it as an estimate."""
    now = now or datetime.now(timezone.utc)
    start, nxt = _month_bounds(now)
    elapsed = (now - start).total_seconds()
    total = (nxt - start).total_seconds()
    if elapsed < 3600:  # too little signal — don't extrapolate from minutes
        return round(spent_usd, 4)
    return round(spent_usd * (total / elapsed), 4)


def usage_summary(user_id: Optional[int] = None) -> dict[str, Any]:
    """Current-calendar-month usage aggregates (UTC). user_id None = system-wide."""
    now = datetime.now(timezone.utc)
    month_start = now.strftime("%Y-%m-01T00:00:00Z")
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        out = _aggregate(cursor, month_start, user_id)
        out["services"] = _aggregate_by_service(cursor, month_start, user_id)
    finally:
        conn.close()
    out["month_start"] = month_start
    out["projected_cost_usd"] = project_month_end(out["total_cost_usd"], now)
    return out
