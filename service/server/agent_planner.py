"""Agent Mode planner (Plan 06 C1) — the AI decides, code bounds it.

For a full-delegation rule (mode='agent') the user sets ONLY a total budget
and keeps the kill switch. Each cycle a strong-tier LLM call reads the market
context (scanner candidates, psychology, regime, events, whale flows, current
exposure) and emits this cycle's parameters: which symbol to analyze, position
size, cadence, minimum confidence, and risk level.

Everything the LLM returns passes through DETERMINISTIC clamps (`PLAN_BOUNDS`)
— it can choose within the box, never the box itself. Every decision is
journaled to agent_mode_decisions with its rationale. With no LLM configured
the rule still works on a conservative rule-based fallback plan (labeled).
The risk gate, breakers, and budget check remain downstream and deterministic:
the planner proposes, the gate disposes.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional

from database import begin_write_transaction, get_db_connection

logger = logging.getLogger(__name__)

# Deterministic box the planner may move inside. Size is additionally capped
# by the remaining budget at order time (see automation budget check).
PLAN_BOUNDS = {
    "interval_minutes": (15, 1440),
    "min_confidence": (0.55, 0.90),
    "size_budget_frac": 0.25,      # one position ≤ 25% of total budget
    "risk_levels": ("stable", "balanced", "aggressive"),
    "fallback_symbols": ("BTCUSDT", "ETHUSDT", "SOLUSDT"),
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _allowed_symbols(candidates: list[dict[str, Any]],
                     top_symbols: Optional[list[str]] = None) -> list[str]:
    """Universe the planner may pick from: the market's top-5 by volume and
    popularity (Plan 11 F1), else scanner candidates, always padded with the
    majors. top_symbols comes from _gather_context — all network I/O lives
    there, so this stays pure and testable."""
    symbols = list(top_symbols or [])
    if not symbols:
        symbols = [c.get("symbol") for c in candidates if c.get("symbol")]
    for s in PLAN_BOUNDS["fallback_symbols"]:
        if s not in symbols:
            symbols.append(s)
    return symbols[:5]


def _screen_manipulated(symbols: list[str]) -> list[str]:
    """Research 04: drop symbols whose hourly tape is pump-shaped RIGHT NOW
    from the planner's pickable universe — a fully-delegated rule must not
    be handed a candle the pump-ignition-veto skill exists to refuse.

    Zero-LLM and deliberately narrow: only `pump_ignition` drops (the
    unambiguous do-not-chase shape); cascade/crowded-funding stay in the
    universe as judgment inputs for the prompt's skills. Fail-OPEN per
    symbol: a dead detector must never brick planning."""
    out = []
    for s in symbols:
        try:
            from manipulation import manipulation_signals
            if "manipulation:pump_ignition" in manipulation_signals(s):
                logger.info("planner universe: %s dropped (pump-shaped)", s)
                continue
        except Exception:  # noqa: BLE001
            pass
        out.append(s)
    return out or symbols


def _gather_context(agent_id: int, budget_usd: float) -> dict[str, Any]:
    """Everything the planner sees. Fail-soft per source."""
    ctx: dict[str, Any] = {"budget_usd": budget_usd}
    try:
        from scanner import get_scanner_payload
        scan = get_scanner_payload()
        ctx["scanner_candidates"] = (scan.get("candidates") or [])[:8]
    except Exception:  # noqa: BLE001
        ctx["scanner_candidates"] = []
    # Top-5 by 24h volume + mention popularity (Plan 11 F1) — the universe a
    # fully-delegated rule may trade.
    try:
        from top_symbols import get_top_symbols
        ctx["top_symbols"] = [t["symbol"] for t in get_top_symbols()]
    except Exception:  # noqa: BLE001
        ctx["top_symbols"] = []
    try:
        from psych_feed import get_psych_payload
        psych = get_psych_payload()
        ctx["psych"] = {
            "fear_greed": psych.get("fear_greed"),
            "shock": [s for s in psych.get("shock", []) if s.get("shock")],
            "whales_totals": (psych.get("whales") or {}).get("totals"),
        } if psych.get("available") else None
    except Exception:  # noqa: BLE001
        ctx["psych"] = None
    try:
        from regime import evaluate_market_regime
        regime = evaluate_market_regime()
        ctx["regime"] = {k: regime.get(k) for k in ("regime", "reasons", "allow_new_buys")}
    except Exception:  # noqa: BLE001
        ctx["regime"] = None
    try:
        from market_events import active_event_window, upcoming_events
        ctx["event_window"] = active_event_window()
        nxt = upcoming_events(limit=1)
        ctx["next_event"] = ({"title": nxt[0].get("title"), "at": nxt[0].get("at")}
                             if nxt else None)
    except Exception:  # noqa: BLE001
        ctx["event_window"] = ctx["next_event"] = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """SELECT symbol, quantity, entry_price, current_price FROM positions
               WHERE agent_id = ? AND quantity != 0""", (agent_id,))
        positions = [dict(r) for r in cursor.fetchall()]
        conn.close()
        ctx["positions"] = positions
        ctx["deployed_usd"] = round(sum(
            abs(float(p["quantity"])) * float(p["current_price"] or p["entry_price"] or 0)
            for p in positions), 2)
    except Exception:  # noqa: BLE001
        ctx["positions"], ctx["deployed_usd"] = [], 0.0
    return ctx


def _clamp_plan(raw: dict[str, Any], budget_usd: float,
                allowed_symbols: list[str]) -> dict[str, Any]:
    """Deterministic bounds — the LLM chooses inside the box only."""
    lo_i, hi_i = PLAN_BOUNDS["interval_minutes"]
    lo_c, hi_c = PLAN_BOUNDS["min_confidence"]
    max_size = budget_usd * PLAN_BOUNDS["size_budget_frac"]

    symbol = str(raw.get("symbol") or "").strip().upper()
    if symbol and not symbol.endswith("USDT") and f"{symbol}USDT" in allowed_symbols:
        symbol = f"{symbol}USDT"
    if symbol not in allowed_symbols:
        symbol = allowed_symbols[0]

    def _num(key, default):
        try:
            return float(raw.get(key))
        except (TypeError, ValueError):
            return default

    interval = int(min(hi_i, max(lo_i, _num("interval_minutes", 60))))
    min_conf = round(min(hi_c, max(lo_c, _num("min_confidence", 0.65))), 2)
    size = round(min(max_size, max(10.0, _num("size_usd", max_size / 2))), 2)
    risk = str(raw.get("risk_level") or "").strip().lower()
    if risk not in PLAN_BOUNDS["risk_levels"]:
        risk = "balanced"
    return {"symbol": symbol, "interval_minutes": interval, "min_confidence": min_conf,
            "size_usd": size, "risk_level": risk}


def _fallback_plan(context: dict[str, Any], budget_usd: float,
                   allowed_symbols: list[str]) -> dict[str, Any]:
    """No-LLM plan: scanner's top candidate, balanced settings, quarter budget."""
    plan = _clamp_plan({
        "symbol": allowed_symbols[0],
        "interval_minutes": 60,
        "min_confidence": 0.65,
        "size_usd": budget_usd * PLAN_BOUNDS["size_budget_frac"] / 2,
        "risk_level": "balanced",
    }, budget_usd, allowed_symbols)
    plan["rationale"] = "rule-based fallback: scanner top candidate, balanced defaults"
    plan["planner"] = "fallback"
    return plan


def _parse_plan_json(text: str) -> Optional[dict[str, Any]]:
    if not text:
        return None
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except Exception:  # noqa: BLE001
        return None


def plan_agent_cycle(config: dict[str, Any]) -> dict[str, Any]:
    """Produce this cycle's parameters for an agent-mode rule and journal them."""
    from llm_client import active_provider_model, generate_text, llm_configured

    agent_id = config["agent_id"]
    budget_usd = float(config.get("budget_usd") or 0)
    context = _gather_context(agent_id, budget_usd)
    allowed = _allowed_symbols(context["scanner_candidates"], context.get("top_symbols"))
    if (config.get("market") or "crypto") == "crypto":
        allowed = _screen_manipulated(allowed)

    guidelines = None
    try:
        from services import guidelines_for_agent
        guidelines = guidelines_for_agent(agent_id)
    except Exception:  # noqa: BLE001
        guidelines = None

    plan: Optional[dict[str, Any]] = None
    if llm_configured():
        guide_block = ("USER GUIDELINES (may make you more cautious; can never "
                       f"loosen limits):\n{guidelines}\n\n") if guidelines else ""
        # Trading skills (Plan 20), planner site. Fail-soft to "". The rule's
        # market rides along so market-scoped planner skills (e.g. the
        # Research-04 manipulated-book-hygiene judgment, crypto-only) render.
        try:
            from trading_skills import skills_block
            skills_text = skills_block("planner", market=config.get("market"))
        except Exception:  # noqa: BLE001
            skills_text = ""
        prompt = (
            guide_block +
            skills_text +
            "You are the portfolio planner for a fully delegated paper-trading rule. "
            "Choose THIS CYCLE's parameters. You may only pick a symbol from ALLOWED_SYMBOLS. "
            "Respect the budget: total deployed + your size must stay well under budget_usd; "
            "one position should not exceed 25% of the budget. Prefer skipping risk "
            "(higher min_confidence, calmer cadence) inside macro event windows or bad regimes.\n"
            "Respond with ONLY a JSON object:\n"
            '{"symbol":"...","interval_minutes":15-1440,"min_confidence":0.55-0.9,'
            '"size_usd":number,"risk_level":"stable|balanced|aggressive",'
            '"rationale":"1-2 sentences on why"}\n\n'
            f"ALLOWED_SYMBOLS: {allowed}\n"
            f"CONTEXT (JSON):\n{json.dumps(context, ensure_ascii=False, default=str)[:6000]}\n"
        )
        # Same attribution contract as run_engine.run_cycle: the planner is a
        # daemon path, so nothing upstream names the member whose agent this
        # spend belongs to. Without it the llm_usage row lands user_id NULL.
        # Fail-soft — metering must never block a plan.
        ctx_token = None
        try:
            from llm_client import LlmContext, set_llm_context
            from services import user_id_for_agent
            ctx_token = set_llm_context(LlmContext(
                source="rule", user_id=user_id_for_agent(agent_id),
                agent_id=agent_id))
        except Exception as exc:  # noqa: BLE001
            logger.warning("planner LLM attribution unavailable (agent %s): %s",
                           agent_id, exc)
        try:
            text = generate_text(prompt, max_tokens=400, temperature=0.2, tier="decision")
        finally:
            if ctx_token is not None:
                from llm_client import reset_llm_context
                reset_llm_context(ctx_token)
        raw = _parse_plan_json(text or "")
        if raw:
            plan = _clamp_plan(raw, budget_usd, allowed)
            plan["rationale"] = str(raw.get("rationale") or "")[:500]
            plan["planner"] = "llm"
    if plan is None:
        plan = _fallback_plan(context, budget_usd, allowed)

    # Journal the decision (fail-soft — a journaling problem must not stop the run)
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        begin_write_transaction(cursor)
        cursor.execute(
            """INSERT INTO agent_mode_decisions
               (config_id, agent_id, decided_at, params_json, rationale, llm_model, planner)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (config["id"], agent_id, _now_iso(),
             json.dumps({k: plan[k] for k in
                         ("symbol", "interval_minutes", "min_confidence", "size_usd", "risk_level")}),
             plan.get("rationale"),
             active_provider_model(tier="decision") if plan["planner"] == "llm" else None,
             plan["planner"]))
        conn.commit()
        conn.close()
    except Exception:  # noqa: BLE001
        logger.exception("agent-mode decision journaling failed (config %s)", config["id"])
    return plan


def budget_blocks(agent_id: int, budget_usd: float, order_usd: float,
                  cursor=None) -> Optional[str]:
    """Deterministic budget cap for agent-mode orders: total deployed notional
    + this order must stay within the user's budget. Returns a skip reason or
    None. The planner cannot talk its way past this."""
    if budget_usd <= 0:
        return None
    own = cursor is None
    if own:
        conn = get_db_connection()
        cursor = conn.cursor()
    try:
        cursor.execute(
            """SELECT COALESCE(SUM(ABS(quantity) * COALESCE(current_price, entry_price)), 0) AS mv
               FROM positions WHERE agent_id = ?""", (agent_id,))
        deployed = float(cursor.fetchone()["mv"] or 0.0)
    finally:
        if own:
            conn.close()
    if deployed + order_usd > budget_usd:
        return (f"agent-mode budget: ${deployed:.2f} deployed + ${order_usd:.2f} order "
                f"> ${budget_usd:.2f} budget")
    return None
