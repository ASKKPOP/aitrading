"""AI trading automation (Target 3).

Executes user-configured rules: on each tick, every enabled + due rule runs the
multi-agent analysis (analysis_agents.run_analysis). If the rule has auto_execute
on, the decision is BUY or SELL, and confidence >= min_confidence, a paper trade
is executed on the agent's SIMULATOR account (signals row + position + cash —
same ledger as a manual trade, signal_type 'automation').

Safety invariants:
  - Only account_type='simulator' rules ever execute. 'real' rules run the
    analysis and record the decision, but never place orders (live execution is
    intentionally not wired in this build).
  - us-stock rules skip execution while the US market is closed (analysis still
    runs; the run is recorded with a skip_reason).
  - A sell only executes against an existing long position; a buy requires cash.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from database import begin_write_transaction, get_db_connection

logger = logging.getLogger(__name__)

VALID_MARKETS = ("crypto", "us-stock")
EXECUTABLE_ACTIONS = ("buy", "sell")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ─────────────────────────── paper-trade executor ───────────────────────────

def execute_paper_trade(agent_id: int, symbol: str, market: str, side: str,
                        quantity: float, price: float) -> tuple[Optional[int], Optional[str]]:
    """Execute a simulator trade with the same ledger as a manual signal:
    signals row (signal_type='automation') + position update + cash update.
    Returns (signal_id, None) on success or (None, reason) when skipped."""
    from fees import TRADE_FEE_RATE
    from services import _reserve_signal_id, _update_position_from_signal
    from routes_shared import get_position_snapshot

    if side not in EXECUTABLE_ACTIONS:
        return None, f"action '{side}' is not executable"
    if quantity <= 0 or price <= 0:
        return None, "invalid quantity/price"

    trade_value = price * quantity
    fee = trade_value * TRADE_FEE_RATE
    now = _now_iso()

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        begin_write_transaction(cursor)

        if side == "sell":
            pos = get_position_snapshot(cursor, agent_id, market, symbol, None)
            current_qty = float(pos["quantity"]) if pos else 0.0
            if current_qty <= 0:
                conn.rollback()
                return None, "no long position to sell"
            quantity = min(quantity, current_qty)
            trade_value = price * quantity
            fee = trade_value * TRADE_FEE_RATE

        if side == "buy":
            cursor.execute("SELECT cash FROM agents WHERE id = ?", (agent_id,))
            row = cursor.fetchone()
            cash = row["cash"] if row else 0
            if cash < trade_value + fee:
                conn.rollback()
                return None, f"insufficient cash (${cash:.2f} < ${trade_value + fee:.2f})"

        signal_id = _reserve_signal_id(cursor)
        cursor.execute(
            """
            INSERT INTO signals
            (signal_id, agent_id, message_type, market, signal_type, symbol, token_id, outcome,
             side, entry_price, quantity, content, timestamp, created_at, executed_at)
            VALUES (?, ?, 'operation', ?, 'automation', ?, NULL, NULL, ?, ?, ?, ?, ?, ?, ?)
            """,
            (signal_id, agent_id, market, symbol, side, price, quantity,
             "AI automation", int(datetime.now(timezone.utc).timestamp()), now, now),
        )
        _update_position_from_signal(agent_id, symbol, market, side, quantity, price, now, cursor=cursor)
        if side == "buy":
            cursor.execute("UPDATE agents SET cash = cash - ? WHERE id = ?", (trade_value + fee, agent_id))
        else:
            cursor.execute("UPDATE agents SET cash = cash + ? WHERE id = ?", (trade_value - fee, agent_id))
        conn.commit()
        return signal_id, None
    except Exception as exc:  # noqa: BLE001
        conn.rollback()
        logger.exception("automation paper trade failed: %s", exc)
        return None, str(exc)
    finally:
        conn.close()


# ─────────────────────────── one rule ───────────────────────────

def run_rule(config: dict[str, Any]) -> dict[str, Any]:
    """Run one automation rule: analysis -> (maybe) execute -> record the run."""
    from analysis_agents import run_analysis
    from routes_shared import is_market_open

    config_id = config["id"]
    agent_id = config["agent_id"]
    symbol = config["symbol"]
    market = config["market"]

    result: dict[str, Any] = {"config_id": config_id, "executed": False, "skip_reason": None}
    action = None
    confidence = None
    report = None
    signal_id = None

    try:
        analysis = run_analysis(symbol, market, config.get("lang") or "en",
                                provider=config.get("provider") or None)
        decision = analysis.get("decision") or {}
        action = decision.get("action")
        confidence = decision.get("confidence")
        report = (decision.get("report") or decision.get("rationale") or "")[:4000]
        entry = decision.get("entry")

        if not config.get("auto_execute"):
            result["skip_reason"] = "auto_execute off"
        elif config.get("account_type") != "simulator":
            # Live execution is intentionally not wired — record and skip.
            result["skip_reason"] = "real account execution disabled in this build"
        elif action not in EXECUTABLE_ACTIONS:
            result["skip_reason"] = f"decision is '{action}'"
        elif (confidence or 0) < float(config.get("min_confidence") or 0):
            result["skip_reason"] = f"confidence {confidence} below threshold {config.get('min_confidence')}"
        elif not is_market_open(market):
            result["skip_reason"] = "market closed"
        elif not entry or entry <= 0:
            result["skip_reason"] = "no valid price in decision"
        else:
            quantity = float(config.get("size_usd") or 0) / float(entry)
            signal_id, skip = execute_paper_trade(agent_id, symbol, market, action, quantity, float(entry))
            if signal_id:
                result["executed"] = True
            else:
                result["skip_reason"] = skip
    except Exception as exc:  # noqa: BLE001
        logger.exception("automation rule %s failed: %s", config_id, exc)
        result["skip_reason"] = f"error: {exc}"

    result.update({"action": action, "confidence": confidence, "signal_id": signal_id})

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        begin_write_transaction(cursor)
        cursor.execute(
            """INSERT INTO automation_runs
               (config_id, agent_id, ran_at, action, confidence, executed, skip_reason, signal_id, report)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (config_id, agent_id, _now_iso(), action, confidence,
             1 if result["executed"] else 0, result["skip_reason"], signal_id, report),
        )
        cursor.execute("UPDATE automation_configs SET last_run_at = ? WHERE id = ?", (_now_iso(), config_id))
        conn.commit()
    except Exception:  # noqa: BLE001
        conn.rollback()
        logger.exception("failed to record automation run for config %s", config_id)
    finally:
        conn.close()

    return result


# ─────────────────────────── the tick ───────────────────────────

def run_automation_tick() -> dict[str, Any]:
    """Find all enabled rules that are due (last_run_at + interval <= now) and run them."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM automation_configs WHERE enabled = 1")
        rows = [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()

    # Due-check in Python so it works identically on SQLite / MySQL / Postgres.
    now = datetime.now(timezone.utc)
    due = []
    for cfg in rows:
        last = cfg.get("last_run_at")
        if not last:
            due.append(cfg)
            continue
        try:
            parsed = datetime.fromisoformat(str(last).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            due.append(cfg)
            continue
        interval_s = max(1, int(cfg.get("interval_minutes") or 60)) * 60
        if (now - parsed).total_seconds() >= interval_s:
            due.append(cfg)

    results = [run_rule(cfg) for cfg in due]
    executed = sum(1 for r in results if r["executed"])
    if due:
        logger.info("automation tick: %s due, %s executed", len(due), executed)
    return {"due": len(due), "executed": executed, "results": results}
