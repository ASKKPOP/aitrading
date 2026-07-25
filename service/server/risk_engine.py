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
from fx_rates import to_usd
import markets

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
    # Phase-3 exit toolkit — per-agent opt-in, off by default. Applies only to
    # positions stamped exit_policy='v1' (pre-existing rows are grandfathered).
    "use_trailing": 0,
    "trail_pct": 0.05,
    "time_stop_days": 0,
    # Plan 06 A1 — portfolio-level caps: aggregate deployed notional as % of
    # equity, and max number of concurrently held positions. 0 disables.
    "max_portfolio_exposure_pct": 60.0,
    "max_concurrent_positions": 8,
}
_INT_LIMIT_KEYS = {"use_kelly", "use_trailing", "time_stop_days", "max_concurrent_positions"}


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
        row = dict(row)
        for key in DEFAULT_LIMITS:
            if row.get(key) is not None:
                limits[key] = row[key]
        limits["updated_at"] = row.get("updated_at")
    else:
        limits["updated_at"] = None
    for key in _INT_LIMIT_KEYS:
        limits[key] = int(limits[key])
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
        # Column list built from DEFAULT_LIMITS so newly added limit fields
        # survive every PUT (a hardcoded list silently reset new columns).
        keys = list(DEFAULT_LIMITS)
        cast = [int(current[k]) if k in _INT_LIMIT_KEYS else float(current[k]) for k in keys]
        cursor.execute(
            f"""INSERT INTO risk_limits (agent_id, {', '.join(keys)}, updated_at)
                VALUES (?, {', '.join('?' for _ in keys)}, ?)""",
            (agent_id, *cast, _now_iso()),
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
    if agent_id is not None:
        try:
            from alerts import send_alert
            send_alert(agent_id, "breaker", f"Circuit breaker HALT ({scope})",
                       f"Trading halted: {reason}", dedupe_key=f"breaker:{scope}")
        except Exception:  # noqa: BLE001
            logger.debug("breaker alert failed for %s", scope)
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

def trade_stats(agent_id: int, cursor=None, run_id: Optional[int] = None) -> dict[str, Any]:
    """Replay the agent's executed signals (average-cost basis) to derive
    closed-trade stats: win rate W, payoff ratio R, and today's realized P&L.

    Longs: buy accumulates, sell realizes (price − avg_cost) × qty.
    Shorts: short accumulates, cover realizes (avg_entry − price) × qty.
    Groups by (market, symbol, token_id) so Polymarket outcomes don't mix.

    run_id scopes the replay to a single run's own trades. Kelly's edge is only
    a valid i.i.d. estimate within one strategy/symbol, and pooling an agent's
    whole cross-strategy journal lets one losing run permanently lock every
    fresh run out (the death-spiral). None ⇒ agent-wide (used for the
    account-level daily-loss breaker, which must stay agent-wide).
    """
    own = cursor is None
    if own:
        conn = get_db_connection()
        cursor = conn.cursor()
    try:
        # Most recent N signals, replayed oldest-first. Bounded so the gate
        # stays cheap no matter how long an agent has been trading.
        scope_sql = " AND run_id = ?" if run_id is not None else ""
        params: list = [agent_id]
        if run_id is not None:
            params.append(run_id)
        params.append(TRADE_STATS_MAX_SIGNALS)
        cursor.execute(
            f"""SELECT market, symbol, COALESCE(token_id, '') AS token_id, side,
                      entry_price, quantity, executed_at
               FROM signals
               WHERE agent_id = ? AND executed_at IS NOT NULL
                 AND side IN ('buy', 'sell', 'short', 'cover')
                 AND entry_price IS NOT NULL AND quantity IS NOT NULL{scope_sql}
               ORDER BY executed_at DESC, id DESC
               LIMIT ?""",
            tuple(params),
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
        # Point value and settlement currency are pure functions of the
        # instrument, derived the same way position_currency already was —
        # 1.0/USD for cash markets, 50 for ES, CNY for an A-share.
        multiplier = markets.contract_multiplier(row["market"], row["symbol"])
        currency = markets.position_currency(row["market"], row["symbol"])
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
            # Scale to contract notional, then to USD. These stats feed a single
            # cross-market risk gate, so a CNY A-share PnL and a USD futures PnL
            # cannot be summed in their native units.
            pnl = to_usd(pnl * multiplier, currency)
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
                   quantity: float, price: float,
                   sigma_daily_pct: Optional[float] = None,
                   run_id: Optional[int] = None) -> GateDecision:
    """Run an intended automation order through breaker → limits → vol sizing
    → Kelly. Callers must treat a not-allowed decision as a skip (journal the
    reason). sigma_daily_pct is the 20-day DAILY-return σ in % (never the
    hourly sigma_24h_pct — ~√24 smaller; feeding it here oversizes ~5×).

    run_id scopes the Kelly edge estimate to that run's own closed trades so a
    fresh run isn't gated by the agent's pooled cross-strategy history (the
    death-spiral). The daily-loss breaker stays agent-wide regardless."""
    if not risk_engine_enabled():
        return GateDecision(allowed=True, quantity=quantity)

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Gate by RISK DIRECTION, not by side name: buy/short OPEN risk (full
        # gate); sell/cover REDUCE it. Reducing orders pass the gate, including
        # AUTO-tripped breakers (a panic auto-halt must not trap exits) — only
        # a manual admin HALT stops them. Blocking exits under a daily-loss
        # lockout would trap losing positions with no SL/TP registered.
        # (Previously any non-buy side bypassed everything, so a future 'short'
        # would have opened risk ungated — verification-panel risk lens.)
        if side in ("sell", "cover"):
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

        # ABS(quantity): a short adds risk exposure exactly like a long —
        # signed sums would let shorts *offset* the caps (Plan 06 A3).
        cursor.execute(
            """SELECT COALESCE(SUM(ABS(quantity) * COALESCE(current_price, entry_price)), 0) AS mv
               FROM positions WHERE agent_id = ? AND market = ? AND symbol = ?""",
            (agent_id, market, symbol),
        )
        exposure = float(cursor.fetchone()["mv"] or 0.0)

        # Volatility sizing (Phase 3, VOL_SIZING_ENABLED): the research's L4 —
        # position risk budget ÷ volatility. Per-POSITION budget: existing
        # symbol exposure counts against the target, so repeated ticks can't
        # stack past it. σ missing → reject (entry-null conservatism; the lazy
        # fallback would silently produce a full-equity notional). Only ever
        # shrinks the requested size. Kelly below may shrink further.
        adjustment = None
        try:
            import strategy_config as _scfg
            vol_sizing_on = _scfg.vol_sizing_enabled()
            risk_budget = _scfg.risk_budget_pct() / 100.0
        except Exception:  # noqa: BLE001
            vol_sizing_on, risk_budget = False, 0.005
        if vol_sizing_on:
            if sigma_daily_pct is None or sigma_daily_pct <= 0:
                return GateDecision(
                    allowed=False, quantity=0.0,
                    reason="risk: vol sizing on but daily sigma unavailable — buy rejected")
            equity_now = _equity(cursor, agent_id)
            target_notional = equity_now * risk_budget / (sigma_daily_pct / 100.0)
            headroom = target_notional - exposure
            if headroom < MIN_ORDER_NOTIONAL_USD:
                return GateDecision(
                    allowed=False, quantity=0.0,
                    reason=(f"risk: vol-sizing position target reached "
                            f"(target ${target_notional:.2f}, held ${exposure:.2f})"))
            if headroom < quantity * price:
                adjustment = (f"vol-sizing: ${quantity * price:.2f} → ${headroom:.2f} "
                              f"(σ_daily {sigma_daily_pct:.2f}%, budget {risk_budget * 100:.2f}%)")
                quantity = headroom / price
        # Kelly edge is scoped to THIS run's own journal (agent-wide when
        # run_id is None) — pooling all of an agent's strategies makes W a
        # meaningless average and lets one loser lock out every fresh run.
        kstats = (trade_stats(agent_id, cursor=cursor, run_id=run_id)
                  if run_id is not None else stats)
        if int(limits["use_kelly"]) and kstats["n_trades"] >= KELLY_MIN_TRADES:
            f_star = kelly_fraction(kstats["win_rate"], kstats["payoff_ratio"])
            if f_star is not None:
                if f_star <= 0:
                    return GateDecision(
                        allowed=False, quantity=0.0,
                        reason=(f"risk: kelly no-edge (W={kstats['win_rate']:.2f}, "
                                f"R={kstats['payoff_ratio']:.2f}, f*={f_star:.3f} ≤ 0)"))
                cap_notional = 0.5 * f_star * _equity(cursor, agent_id) - exposure
                if cap_notional < quantity * price:
                    if cap_notional < MIN_ORDER_NOTIONAL_USD:
                        return GateDecision(
                            allowed=False, quantity=0.0,
                            reason=(f"risk: kelly position cap reached "
                                    f"(½f* headroom ${max(cap_notional, 0):.2f})"))
                    kelly_note = (f"kelly: size ${quantity * price:.2f} → ${cap_notional:.2f} "
                                  f"(½f*={0.5 * f_star:.3f}, minus ${exposure:.2f} held)")
                    adjustment = f"{adjustment}; {kelly_note}" if adjustment else kelly_note
                    quantity = cap_notional / price

        # Per-symbol exposure cap (existing notional + this order, post-Kelly).
        max_exposure = float(limits["max_symbol_exposure_usd"])
        if max_exposure > 0 and exposure + quantity * price > max_exposure:
            return GateDecision(
                allowed=False, quantity=0.0,
                reason=(f"risk: symbol exposure limit "
                        f"(${exposure:.2f} held + ${quantity * price:.2f} order "
                        f"> ${max_exposure:.2f} cap)"))

        # Portfolio-level caps (Plan 06 A1) — bound AGGREGATE risk that the
        # per-symbol cap can't see: total deployed notional as % of equity,
        # and the number of concurrently held positions. 0 disables either.
        max_port_pct = float(limits.get("max_portfolio_exposure_pct") or 0)
        max_positions = int(limits.get("max_concurrent_positions") or 0)
        if max_port_pct > 0 or max_positions > 0:
            cursor.execute(
                """SELECT COALESCE(SUM(ABS(quantity) * COALESCE(current_price, entry_price)), 0) AS mv,
                          COALESCE(SUM(CASE WHEN quantity != 0 THEN 1 ELSE 0 END), 0) AS n
                   FROM positions WHERE agent_id = ?""",
                (agent_id,),
            )
            prow = cursor.fetchone()
            port_exposure = float(prow["mv"] or 0.0)
            open_positions = int(prow["n"] or 0)
            if max_positions > 0 and exposure <= 0 and open_positions >= max_positions:
                return GateDecision(
                    allowed=False, quantity=0.0,
                    reason=(f"risk: max concurrent positions reached "
                            f"({open_positions}/{max_positions})"))
            if max_port_pct > 0:
                equity_now = _equity(cursor, agent_id)
                cap_usd = equity_now * max_port_pct / 100.0
                if port_exposure + quantity * price > cap_usd:
                    return GateDecision(
                        allowed=False, quantity=0.0,
                        reason=(f"risk: portfolio exposure limit "
                                f"(${port_exposure:.2f} deployed + ${quantity * price:.2f} order "
                                f"> ${cap_usd:.2f} = {max_port_pct:.0f}% of equity)"))

        limits_sl = float(limits["stop_loss_pct"])
        limits_tp = float(limits["take_profit_pct"])
        if side == "short":
            # Inverted exits (Plan 06 A3): stop ABOVE entry, target BELOW.
            # Executor 'cover' support closes these; watcher handles triggers.
            return GateDecision(
                allowed=True, quantity=quantity, adjustment=adjustment,
                stop_loss=price * (1 + limits_sl) if limits_sl > 0 else None,
                take_profit=price * (1 - limits_tp) if limits_tp > 0 else None,
            )
        if side != "buy":
            return GateDecision(allowed=True, quantity=quantity, adjustment=adjustment)

        return GateDecision(
            allowed=True, quantity=quantity, adjustment=adjustment,
            stop_loss=price * (1 - limits_sl) if limits_sl > 0 else None,
            take_profit=price * (1 + limits_tp) if limits_tp > 0 else None,
        )
    finally:
        conn.close()


# ─────────────────────────── SL/TP watcher ───────────────────────────

def _parse_position_ts(value: Optional[str]) -> Optional[datetime]:
    """Position timestamps exist in two stored formats ('YYYY-MM-DDTHH:MM:SSZ'
    and SQLite's 'YYYY-MM-DD HH:MM:SS') — parse both, assume UTC."""
    if not value:
        return None
    raw = value.strip().replace("Z", "+00:00")
    if " " in raw and "T" not in raw:
        raw = raw.replace(" ", "T")
    try:
        dt = datetime.fromisoformat(raw)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _apply_trailing_stop(cursor, pos: dict[str, Any], price: float,
                         limits: dict[str, Any]) -> bool:
    """Ratchet the stop toward price once the position is in profit ≥ 1×trail;
    once armed, clear take_profit so the trail manages the exit ('let winners
    ride' — the fixed TP otherwise guillotines every trend before the trail
    can work). The ratchet NEVER loosens an existing stop (longs: never lower;
    shorts: never raise). Returns whether a write happened. Only
    exit_policy='v1' rows reach here."""
    trail = float(limits.get("trail_pct") or 0)
    if trail <= 0:
        return False
    entry = float(pos["entry_price"])
    if entry <= 0:
        return False
    existing = pos.get("stop_loss")
    if float(pos["quantity"]) < 0:
        # Short: profit = price falling. Arms at −1×trail; stop trails ABOVE.
        if price > entry * (1 - trail):
            return False
        candidate = price * (1 + trail)
        new_stop = min(candidate, float(existing)) if existing is not None else candidate
        if existing is not None and new_stop >= float(existing) and pos.get("take_profit") is None:
            return False
    else:
        if price < entry * (1 + trail):
            return False  # trail arms at +1×trail profit
        candidate = price * (1 - trail)
        new_stop = max(candidate, float(existing)) if existing is not None else candidate
        if existing is not None and new_stop <= float(existing) and pos.get("take_profit") is None:
            return False  # nothing to change
    cursor.execute(
        "UPDATE positions SET stop_loss = ?, take_profit = NULL WHERE id = ?",
        (new_stop, pos["id"]))
    return True


def run_sltp_watcher_tick() -> dict[str, Any]:
    """Close long positions whose polled price crossed stop_loss/take_profit;
    ratchet trailing stops; time-stop stale losers (Phase 3).

    Reads positions.current_price (maintained by the price-update loop) — no
    external calls. Exits bypass the gate: they only reduce risk.
    Grandfathering: trailing and time stops act ONLY on positions stamped
    exit_policy='v1' AND agents that opted in via risk_limits (use_trailing /
    time_stop_days > 0). Pre-existing positions keep the old fixed SL/TP
    behavior untouched. Effective granularity = the price-poll interval
    (default 900s), not the 30s tick — a known limitation.
    """
    if not risk_engine_enabled():
        return {"checked": 0, "closed": 0}

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """SELECT id, agent_id, symbol, market, quantity, current_price,
                      entry_price, stop_loss, take_profit, exit_policy,
                      first_opened_at, run_id
               FROM positions
               WHERE quantity != 0 AND current_price IS NOT NULL
                 AND (stop_loss IS NOT NULL OR take_profit IS NOT NULL
                      OR exit_policy = 'v1')""")
        rows = [dict(r) for r in cursor.fetchall()]

        # Trailing-stop ratchet pass (before trigger checks, same tick).
        trailed = 0
        limits_cache: dict[int, dict[str, Any]] = {}
        for pos in rows:
            if pos.get("exit_policy") != "v1":
                continue
            agent_id = pos["agent_id"]
            if agent_id not in limits_cache:
                limits_cache[agent_id] = get_risk_limits(agent_id, cursor=cursor)
            limits = limits_cache[agent_id]
            if not int(limits.get("use_trailing") or 0):
                continue
            price = float(pos["current_price"])
            if _apply_trailing_stop(cursor, pos, price, limits):
                trailed += 1
                trail_pct = float(limits["trail_pct"])
                if float(pos["quantity"]) < 0:
                    candidate = price * (1 + trail_pct)
                    pos["stop_loss"] = min(candidate, float(pos["stop_loss"])) \
                        if pos.get("stop_loss") is not None else candidate
                else:
                    candidate = price * (1 - trail_pct)
                    pos["stop_loss"] = max(candidate, float(pos["stop_loss"])) \
                        if pos.get("stop_loss") is not None else candidate
                pos["take_profit"] = None
        if trailed:
            conn.commit()
    finally:
        conn.close()

    from automation import execute_paper_trade

    now = datetime.now(timezone.utc)
    closed = 0
    for pos in rows:
        price = float(pos["current_price"])
        is_short = float(pos["quantity"]) < 0
        trigger = None
        if is_short:
            # Inverted triggers: stop above (price rose), target below (fell).
            if pos["stop_loss"] is not None and price >= float(pos["stop_loss"]):
                trigger = "stop_loss"
            elif pos["take_profit"] is not None and price <= float(pos["take_profit"]):
                trigger = "take_profit"
        else:
            if pos["stop_loss"] is not None and price <= float(pos["stop_loss"]):
                trigger = "stop_loss"
            elif pos["take_profit"] is not None and price >= float(pos["take_profit"]):
                trigger = "take_profit"
        if trigger is None and pos.get("exit_policy") == "v1":
            # Time stop: losers older than time_stop_days are cut ("at ~55%
            # accuracy, cutting losers fast IS the edge"); winners ride.
            # Anchored to first_opened_at, which average-ins never reset.
            limits = limits_cache.get(pos["agent_id"])
            if limits is None:
                limits = get_risk_limits(pos["agent_id"])
            days = int(limits.get("time_stop_days") or 0)
            opened = _parse_position_ts(pos.get("first_opened_at"))
            losing = (price > float(pos["entry_price"])) if is_short \
                else (price < float(pos["entry_price"]))
            if (days > 0 and opened is not None and losing
                    and (now - opened).days >= days):
                trigger = "time_stop"
        if not trigger:
            continue
        signal_id, skip = execute_paper_trade(
            pos["agent_id"], pos["symbol"], pos["market"],
            "cover" if is_short else "sell",
            abs(float(pos["quantity"])), price,
            content=f"risk: {trigger} triggered at {price} (SL/TP watcher)",
            # Plan 10 D4: run ownership lives on the position row, so a
            # stopped-with-hold run still gets its final exit attributed
            # (and the trade event journaled in the same transaction).
            run_id=pos.get("run_id"))
        if signal_id:
            closed += 1
            logger.info("SL/TP watcher closed position %s (%s %s @ %s, %s)",
                        pos["id"], pos["symbol"], pos["market"], price, trigger)
            try:
                from alerts import send_alert
                send_alert(pos["agent_id"], "position_closed",
                           f"{trigger.replace('_', ' ')} — {pos['symbol']}",
                           (f"Watcher closed {pos['symbol']} ({pos['market']}) at "
                            f"${price:.2f} ({trigger})"),
                           dedupe_key=f"close:{signal_id}")
            except Exception:  # noqa: BLE001
                logger.debug("close alert failed for position %s", pos["id"])
        else:
            logger.warning("SL/TP watcher failed to close position %s: %s", pos["id"], skip)
    return {"checked": len(rows), "closed": closed}
