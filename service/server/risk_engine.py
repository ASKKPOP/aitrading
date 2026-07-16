"""Risk engine (signal-collection plan Phase 1).

Every automated order passes through the gate before execution:

    signal ── ① Kelly sizing ── ② limit checks ── ③ circuit breaker ──▶ fill / reject

  ① Kelly: f* = W − (1−W)/R from the agent's own closed-trade journal (average-cost
    replay of its signals). Position notional is capped at ½-Kelly × equity. With
    fewer than KELLY_MIN_TRADES closed trades there is no statistical basis, so no
    adjustment is applied. A non-positive f* (no edge) rejects the buy — the
    operator can opt out per agent with use_kelly=0 via PUT /api/risk/limits.
  ② Limits: daily realized loss (UTC day) and per-symbol exposure, from risk_limits
    (per-agent row, defaults if unset).
  ③ Breaker: 'global' scope (system trips, e.g. the Phase-3 3σ shock feed) and
    'agent:<id>' scope (manual HALT via POST /api/risk/halt). Either being
    'halted' rejects the order.

The SL/TP watcher tick closes long positions whose polled current_price crossed
their stop_loss / take_profit. Watcher exits are risk-REDUCING and intentionally
bypass the gate, so a daily-loss lockout or HALT can never trap an open position.

The whole engine is gated behind RISK_ENGINE_ENABLED (default off) per the plan's
phase-isolation principle; when off, the gate is a no-op pass-through.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from database import begin_write_transaction, get_db_connection

logger = logging.getLogger(__name__)

# Minimum closed trades before the journal supports a Kelly estimate.
KELLY_MIN_TRADES = 10
# Journal replay bound — the most recent N executed signals. Keeps the gate
# O(bounded) for hyperactive agents; recent history is what Kelly should
# reflect anyway.
TRADE_STATS_MAX_SIGNALS = 5000
# Below this notional a Kelly-shrunk order is pointless — reject instead.
MIN_ORDER_NOTIONAL_USD = 1.0

DEFAULT_LIMITS = {
    "max_daily_loss_usd": 1000.0,
    "max_symbol_exposure_usd": 10000.0,
    "stop_loss_pct": 0.05,
    "take_profit_pct": 0.10,
    "use_kelly": 1,
}


def risk_engine_enabled() -> bool:
    return os.getenv("RISK_ENGINE_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ─────────────────────────── limits ───────────────────────────

def get_risk_limits(agent_id: int, cursor=None) -> dict[str, Any]:
    """Return the agent's risk limits, falling back to defaults when unset."""
    own = cursor is None
    if own:
        conn = get_db_connection()
        cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM risk_limits WHERE agent_id = ?", (agent_id,))
        row = cursor.fetchone()
    finally:
        if own:
            conn.close()
    limits = dict(DEFAULT_LIMITS)
    limits["agent_id"] = agent_id
    if row:
        for key in DEFAULT_LIMITS:
            if row[key] is not None:
                limits[key] = row[key]
        limits["updated_at"] = row["updated_at"]
    else:
        limits["updated_at"] = None
    limits["use_kelly"] = int(limits["use_kelly"])
    return limits


def put_risk_limits(agent_id: int, values: dict[str, Any]) -> dict[str, Any]:
    """Upsert the agent's risk limits (only keys present in DEFAULT_LIMITS)."""
    current = get_risk_limits(agent_id)
    for key in DEFAULT_LIMITS:
        if key in values and values[key] is not None:
            current[key] = values[key]
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        begin_write_transaction(cursor)
        cursor.execute("DELETE FROM risk_limits WHERE agent_id = ?", (agent_id,))
        cursor.execute(
            """INSERT INTO risk_limits
               (agent_id, max_daily_loss_usd, max_symbol_exposure_usd,
                stop_loss_pct, take_profit_pct, use_kelly, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (agent_id, float(current["max_daily_loss_usd"]),
             float(current["max_symbol_exposure_usd"]), float(current["stop_loss_pct"]),
             float(current["take_profit_pct"]), int(current["use_kelly"]), _now_iso()),
        )
        conn.commit()
    finally:
        conn.close()
    return get_risk_limits(agent_id)


# ─────────────────────────── circuit breaker ───────────────────────────

def _breaker_row(cursor, scope: str) -> dict[str, Any]:
    cursor.execute("SELECT * FROM breaker_state WHERE scope = ?", (scope,))
    row = cursor.fetchone()
    if row:
        return dict(row)
    return {"scope": scope, "state": "normal", "reason": None,
            "tripped_at": None, "updated_at": None}


def get_breaker(agent_id: Optional[int] = None) -> dict[str, Any]:
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        result = {"global": _breaker_row(cursor, "global")}
        if agent_id is not None:
            result["agent"] = _breaker_row(cursor, f"agent:{agent_id}")
        return result
    finally:
        conn.close()


def _set_breaker(scope: str, state: str, reason: Optional[str],
                 tripped_by: str = "manual",
                 expires_at: Optional[str] = None) -> dict[str, Any]:
    now = _now_iso()
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        begin_write_transaction(cursor)
        cursor.execute("DELETE FROM breaker_state WHERE scope = ?", (scope,))
        cursor.execute(
            """INSERT INTO breaker_state
               (scope, state, reason, tripped_at, updated_at, tripped_by, expires_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (scope, state, reason, now if state == "halted" else None, now,
             tripped_by if state == "halted" else None,
             expires_at if state == "halted" else None),
        )
        conn.commit()
    finally:
        conn.close()
    return {"scope": scope, "state": state, "reason": reason,
            "tripped_by": tripped_by if state == "halted" else None,
            "expires_at": expires_at if state == "halted" else None}


def trip_breaker(reason: str, agent_id: Optional[int] = None, *,
                 scope: Optional[str] = None, tripped_by: str = "manual",
                 expires_at: Optional[str] = None) -> dict[str, Any]:
    """HALT automation — per agent, per market (scope='market:crypto'), or
    globally. Auto-trips must pass tripped_by='auto' + expires_at so the
    auto-resume sweep can clear them; a manual HALT is never auto-cleared."""
    if scope is None:
        scope = f"agent:{agent_id}" if agent_id is not None else "global"
    logger.warning("breaker HALT (%s, by=%s): %s", scope, tripped_by, reason)
    return _set_breaker(scope, "halted", reason, tripped_by=tripped_by, expires_at=expires_at)


def clear_breaker(agent_id: Optional[int] = None, *, scope: Optional[str] = None) -> dict[str, Any]:
    if scope is None:
        scope = f"agent:{agent_id}" if agent_id is not None else "global"
    return _set_breaker(scope, "normal", None)


def resume_expired_auto_breakers() -> int:
    """Clear halted breakers that were AUTO-tripped and have expired.
    Manual halts (tripped_by null/'manual') are never touched. Returns the
    number of scopes resumed. Called from the automation tick (always runs)."""
    now = _now_iso()
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """SELECT scope FROM breaker_state
               WHERE state = 'halted' AND tripped_by = 'auto'
                 AND expires_at IS NOT NULL AND expires_at <= ?""", (now,))
        scopes = [row["scope"] for row in cursor.fetchall()]
    finally:
        conn.close()
    for scope in scopes:
        logger.warning("breaker auto-resume (%s): expiry reached", scope)
        _set_breaker(scope, "normal", None)
    return len(scopes)


def _is_halted(cursor, agent_id: int, market: Optional[str] = None,
               include_auto: bool = True) -> Optional[str]:
    """Return the halt reason when a matching breaker is tripped.
    Scopes checked: global → market:<market> → agent:<id>.
    include_auto=False skips auto-tripped rows — risk-reducing sells pass
    auto-trips (a panic halt must not trap exits); only a manual HALT stops them."""
    scopes = ["global"]
    if market:
        scopes.append(f"market:{market}")
    scopes.append(f"agent:{agent_id}")
    for scope in scopes:
        row = _breaker_row(cursor, scope)
        if row["state"] == "halted":
            if not include_auto and (row.get("tripped_by") or "manual") == "auto":
                continue
            return f"breaker halted ({scope}): {row['reason'] or 'manual halt'}"
    return None


# ─────────────────────────── journal replay ───────────────────────────

def trade_stats(agent_id: int, cursor=None) -> dict[str, Any]:
    """Replay the agent's executed signals (average-cost basis) to derive
    closed-trade stats: win rate W, payoff ratio R, and today's realized P&L.

    Longs: buy accumulates, sell realizes (price − avg_cost) × qty.
    Shorts: short accumulates, cover realizes (avg_entry − price) × qty.
    Groups by (market, symbol, token_id) so Polymarket outcomes don't mix.
    """
    own = cursor is None
    if own:
        conn = get_db_connection()
        cursor = conn.cursor()
    try:
        # Most recent N signals, replayed oldest-first. Bounded so the gate
        # stays cheap no matter how long an agent has been trading.
        cursor.execute(
            """SELECT market, symbol, COALESCE(token_id, '') AS token_id, side,
                      entry_price, quantity, executed_at
               FROM signals
               WHERE agent_id = ? AND executed_at IS NOT NULL
                 AND side IN ('buy', 'sell', 'short', 'cover')
                 AND entry_price IS NOT NULL AND quantity IS NOT NULL
               ORDER BY executed_at DESC, id DESC
               LIMIT ?""",
            (agent_id, TRADE_STATS_MAX_SIGNALS),
        )
        rows = list(reversed(cursor.fetchall()))
    finally:
        if own:
            conn.close()

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    books: dict[tuple, dict[str, float]] = {}   # long avg-cost books
    shorts: dict[tuple, dict[str, float]] = {}  # short avg-entry books
    pnls: list[float] = []
    realized_today = 0.0

    for row in rows:
        key = (row["market"], row["symbol"], row["token_id"])
        side = row["side"]
        price = float(row["entry_price"])
        qty = float(row["quantity"])
        if qty <= 0 or price <= 0:
            continue
        pnl = None
        if side == "buy":
            book = books.setdefault(key, {"qty": 0.0, "avg": 0.0})
            new_qty = book["qty"] + qty
            book["avg"] = (book["qty"] * book["avg"] + qty * price) / new_qty
            book["qty"] = new_qty
        elif side == "sell":
            book = books.get(key)
            if not book or book["qty"] <= 0:
                continue  # sell without a tracked long — ignore
            closed = min(qty, book["qty"])
            pnl = (price - book["avg"]) * closed
            book["qty"] -= closed
        elif side == "short":
            book = shorts.setdefault(key, {"qty": 0.0, "avg": 0.0})
            new_qty = book["qty"] + qty
            book["avg"] = (book["qty"] * book["avg"] + qty * price) / new_qty
            book["qty"] = new_qty
        elif side == "cover":
            book = shorts.get(key)
            if not book or book["qty"] <= 0:
                continue
            closed = min(qty, book["qty"])
            pnl = (book["avg"] - price) * closed
            book["qty"] -= closed
        if pnl is not None:
            pnls.append(pnl)
            if str(row["executed_at"]).startswith(today):
                realized_today += pnl

    wins = [p for p in pnls if p > 0]
    losses = [-p for p in pnls if p < 0]
    n = len(pnls)
    win_rate = len(wins) / n if n else 0.0
    avg_win = sum(wins) / len(wins) if wins else 0.0
    avg_loss = sum(losses) / len(losses) if losses else 0.0
    payoff = (avg_win / avg_loss) if avg_loss > 0 else None
    return {"n_trades": n, "win_rate": win_rate, "payoff_ratio": payoff,
            "realized_today": realized_today}


def kelly_fraction(win_rate: float, payoff_ratio: Optional[float]) -> Optional[float]:
    """f* = W − (1−W)/R. None when R is unavailable (no losses yet / no trades)."""
    if payoff_ratio is None or payoff_ratio <= 0:
        return None
    return win_rate - (1.0 - win_rate) / payoff_ratio


def _equity(cursor, agent_id: int) -> float:
    cursor.execute("SELECT cash FROM agents WHERE id = ?", (agent_id,))
    row = cursor.fetchone()
    cash = float(row["cash"]) if row and row["cash"] is not None else 0.0
    cursor.execute(
        """SELECT COALESCE(SUM(quantity * COALESCE(current_price, entry_price)), 0) AS mv
           FROM positions WHERE agent_id = ?""",
        (agent_id,),
    )
    row = cursor.fetchone()
    return cash + float(row["mv"] or 0.0)


# ─────────────────────────── the gate ───────────────────────────

@dataclass
class GateDecision:
    allowed: bool
    quantity: float
    reason: Optional[str] = None          # skip_reason when rejected
    adjustment: Optional[str] = None      # human note when quantity was shrunk
    stop_loss: Optional[float] = None     # SL/TP to register on the position (buys)
    take_profit: Optional[float] = None


def evaluate_order(agent_id: int, symbol: str, market: str, side: str,
                   quantity: float, price: float) -> GateDecision:
    """Run an intended automation order through breaker → limits → Kelly.
    Callers must treat a not-allowed decision as a skip (journal the reason)."""
    if not risk_engine_enabled():
        return GateDecision(allowed=True, quantity=quantity)

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Sells reduce risk — they pass the gate, including AUTO-tripped
        # breakers (a panic auto-halt must not trap exits). Only a manual
        # admin HALT stops them. Blocking exits under a daily-loss lockout
        # would trap losing positions with no SL/TP registered.
        if side != "buy":
            halted = _is_halted(cursor, agent_id, market, include_auto=False)
            if halted:
                return GateDecision(allowed=False, quantity=0.0, reason=f"risk: {halted}")
            return GateDecision(allowed=True, quantity=quantity)

        halted = _is_halted(cursor, agent_id, market, include_auto=True)
        if halted:
            return GateDecision(allowed=False, quantity=0.0, reason=f"risk: {halted}")

        limits = get_risk_limits(agent_id, cursor=cursor)
        stats = trade_stats(agent_id, cursor=cursor)

        # Daily max loss — realized P&L (UTC day) from the journal. Blocks new
        # buys; watcher exits and automation sells bypass by design.
        max_daily = float(limits["max_daily_loss_usd"])
        if max_daily > 0 and stats["realized_today"] <= -max_daily:
            return GateDecision(
                allowed=False, quantity=0.0,
                reason=(f"risk: daily loss limit hit "
                        f"(realized today ${stats['realized_today']:.2f} ≤ -${max_daily:.2f})"))

        cursor.execute(
            """SELECT COALESCE(SUM(quantity * COALESCE(current_price, entry_price)), 0) AS mv
               FROM positions WHERE agent_id = ? AND market = ? AND symbol = ?""",
            (agent_id, market, symbol),
        )
        exposure = float(cursor.fetchone()["mv"] or 0.0)

        # Kelly sizing first (plan flow ① — only ever shrinks), so the exposure
        # check below sees the size that would actually be filled. The ½-Kelly
        # cap is a POSITION cap: existing exposure in the symbol counts against
        # it, so repeated ticks can't stack orders past the cap.
        adjustment = None
        if int(limits["use_kelly"]) and stats["n_trades"] >= KELLY_MIN_TRADES:
            f_star = kelly_fraction(stats["win_rate"], stats["payoff_ratio"])
            if f_star is not None:
                if f_star <= 0:
                    return GateDecision(
                        allowed=False, quantity=0.0,
                        reason=(f"risk: kelly no-edge (W={stats['win_rate']:.2f}, "
                                f"R={stats['payoff_ratio']:.2f}, f*={f_star:.3f} ≤ 0)"))
                cap_notional = 0.5 * f_star * _equity(cursor, agent_id) - exposure
                if cap_notional < quantity * price:
                    if cap_notional < MIN_ORDER_NOTIONAL_USD:
                        return GateDecision(
                            allowed=False, quantity=0.0,
                            reason=(f"risk: kelly position cap reached "
                                    f"(½f* headroom ${max(cap_notional, 0):.2f})"))
                    adjustment = (f"kelly: size ${quantity * price:.2f} → ${cap_notional:.2f} "
                                  f"(½f*={0.5 * f_star:.3f}, minus ${exposure:.2f} held)")
                    quantity = cap_notional / price

        # Per-symbol exposure cap (existing notional + this order, post-Kelly).
        max_exposure = float(limits["max_symbol_exposure_usd"])
        if max_exposure > 0 and exposure + quantity * price > max_exposure:
            return GateDecision(
                allowed=False, quantity=0.0,
                reason=(f"risk: symbol exposure limit "
                        f"(${exposure:.2f} held + ${quantity * price:.2f} order "
                        f"> ${max_exposure:.2f} cap)"))

        limits_sl = float(limits["stop_loss_pct"])
        limits_tp = float(limits["take_profit_pct"])
        return GateDecision(
            allowed=True, quantity=quantity, adjustment=adjustment,
            stop_loss=price * (1 - limits_sl) if limits_sl > 0 else None,
            take_profit=price * (1 + limits_tp) if limits_tp > 0 else None,
        )
    finally:
        conn.close()


# ─────────────────────────── SL/TP watcher ───────────────────────────

def run_sltp_watcher_tick() -> dict[str, Any]:
    """Close long positions whose polled price crossed stop_loss/take_profit.

    Reads positions.current_price (maintained by the price-update loop) — no
    external calls. Exits bypass the gate: they only reduce risk.
    """
    if not risk_engine_enabled():
        return {"checked": 0, "closed": 0}

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """SELECT id, agent_id, symbol, market, quantity, current_price,
                      stop_loss, take_profit
               FROM positions
               WHERE quantity > 0 AND current_price IS NOT NULL
                 AND (stop_loss IS NOT NULL OR take_profit IS NOT NULL)""")
        rows = [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()

    from automation import execute_paper_trade

    closed = 0
    for pos in rows:
        price = float(pos["current_price"])
        trigger = None
        if pos["stop_loss"] is not None and price <= float(pos["stop_loss"]):
            trigger = "stop_loss"
        elif pos["take_profit"] is not None and price >= float(pos["take_profit"]):
            trigger = "take_profit"
        if not trigger:
            continue
        signal_id, skip = execute_paper_trade(
            pos["agent_id"], pos["symbol"], pos["market"], "sell",
            float(pos["quantity"]), price,
            content=f"risk: {trigger} triggered at {price} (SL/TP watcher)")
        if signal_id:
            closed += 1
            logger.info("SL/TP watcher closed position %s (%s %s @ %s, %s)",
                        pos["id"], pos["symbol"], pos["market"], price, trigger)
        else:
            logger.warning("SL/TP watcher failed to close position %s: %s", pos["id"], skip)
    return {"checked": len(rows), "closed": closed}
