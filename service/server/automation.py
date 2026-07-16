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

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from database import begin_write_transaction, get_db_connection

logger = logging.getLogger(__name__)

VALID_MARKETS = ("crypto", "us-stock")
EXECUTABLE_ACTIONS = ("buy", "sell")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _event_guard_blocks() -> Optional[str]:
    """Skip-reason string when EVENT_GUARD_ENABLED and a scheduled macro
    release window (FOMC/CPI/jobs) is active; None otherwise. Fail-open —
    the guard never blocks on its own errors."""
    import os
    if os.getenv("EVENT_GUARD_ENABLED", "false").strip().lower() not in ("1", "true", "yes", "on"):
        return None
    try:
        from market_events import active_event_window
        window = active_event_window()
        if window:
            return (f"event guard: {window['title']} release window active "
                    f"({window['window_start']}–{window['window_end']})")
    except Exception:  # noqa: BLE001
        pass
    return None


# ─────────────────────────── paper-trade executor ───────────────────────────

def execute_paper_trade(agent_id: int, symbol: str, market: str, side: str,
                        quantity: float, price: float, content: str = "AI automation",
                        stop_loss: Optional[float] = None,
                        take_profit: Optional[float] = None) -> tuple[Optional[int], Optional[str]]:
    """Execute a simulator trade with the same ledger as a manual signal:
    signals row (signal_type='automation') + position update + cash update.
    On buys, stop_loss/take_profit (from the risk gate) are registered on the
    position row in the same transaction so the SL/TP watcher can act on them.
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
             content, int(datetime.now(timezone.utc).timestamp()), now, now),
        )
        _update_position_from_signal(agent_id, symbol, market, side, quantity, price, now, cursor=cursor)
        if side == "buy":
            if stop_loss is not None or take_profit is not None:
                cursor.execute(
                    """UPDATE positions SET stop_loss = ?, take_profit = ?
                       WHERE agent_id = ? AND market = ? AND symbol = ?""",
                    (stop_loss, take_profit, agent_id, market, symbol),
                )
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

    # Scanner option (Phase 4): a rule whose symbol is 'SCANNER' analyzes the
    # which-coin scanner's current top candidate instead of a fixed symbol.
    if symbol == "SCANNER":
        try:
            from scanner import top_candidate
            resolved = top_candidate()
        except Exception:  # noqa: BLE001
            resolved = None
        if not resolved:
            result["skip_reason"] = "scanner: no candidates available"
            result.update({"action": None, "confidence": None, "signal_id": None})
            _record_run(config_id, agent_id, result, None)
            return result
        symbol = resolved
        result["scanner_symbol"] = symbol
    action = None
    confidence = None
    report = None
    signal_id = None

    try:
        analysis = run_analysis(symbol, market, config.get("lang") or "en",
                                provider=config.get("provider") or None)

        # Confluence telemetry (Phase 1): record the deterministic condition
        # vector alongside every decision — display/journal only until the
        # Phase-4 flip turns it into a gate. Fail-soft.
        try:
            from confluence import evaluate_confluence
            technical = (analysis.get("technical") or {}).get("data") \
                if isinstance(analysis.get("technical"), dict) else None
            result["confluence"] = evaluate_confluence(symbol, market, analysis=technical)
        except Exception as exc:  # noqa: BLE001
            logger.debug("confluence telemetry unavailable for %s: %s", symbol, exc)

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
        elif _event_guard_blocks():
            # Card 07 — scheduled macro releases spike volatility without a
            # reliable direction; skip new entries inside the release window.
            # Opt-in via EVENT_GUARD_ENABLED (default off).
            result["skip_reason"] = _event_guard_blocks()
        elif not entry or entry <= 0:
            result["skip_reason"] = "no valid price in decision"
        else:
            quantity = float(config.get("size_usd") or 0) / float(entry)
            # Risk gate (Phase 1): breaker → limits → Kelly. No-op unless
            # RISK_ENGINE_ENABLED; rejections are journaled via skip_reason.
            from risk_engine import evaluate_order
            gate = evaluate_order(agent_id, symbol, market, action, quantity, float(entry))
            if not gate.allowed:
                result["skip_reason"] = gate.reason
            else:
                signal_id, skip = execute_paper_trade(
                    agent_id, symbol, market, action, gate.quantity, float(entry),
                    stop_loss=gate.stop_loss, take_profit=gate.take_profit)
                if signal_id:
                    result["executed"] = True
                    if gate.adjustment:
                        logger.info("risk gate adjusted order (config %s): %s",
                                    config_id, gate.adjustment)
                else:
                    result["skip_reason"] = skip
    except Exception as exc:  # noqa: BLE001
        logger.exception("automation rule %s failed: %s", config_id, exc)
        result["skip_reason"] = f"error: {exc}"

    result.update({"action": action, "confidence": confidence, "signal_id": signal_id})
    _record_run(config_id, agent_id, result, report)
    return result


def _record_run(config_id: int, agent_id: int, result: dict[str, Any],
                report: Optional[str]) -> None:
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        begin_write_transaction(cursor)
        confluence_json = None
        if result.get("confluence") is not None:
            try:
                confluence_json = json.dumps(result["confluence"], ensure_ascii=False)
            except (TypeError, ValueError):
                confluence_json = None
        cursor.execute(
            """INSERT INTO automation_runs
               (config_id, agent_id, ran_at, action, confidence, executed, skip_reason,
                signal_id, report, confluence_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (config_id, agent_id, _now_iso(), result.get("action"), result.get("confidence"),
             1 if result["executed"] else 0, result["skip_reason"], result.get("signal_id"),
             report, confluence_json),
        )
        cursor.execute("UPDATE automation_configs SET last_run_at = ? WHERE id = ?", (_now_iso(), config_id))
        conn.commit()
    except Exception:  # noqa: BLE001
        conn.rollback()
        logger.exception("failed to record automation run for config %s", config_id)
    finally:
        conn.close()


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
