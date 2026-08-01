"""Resting (limit) orders for the spot/futures terminals.

The paper ledger fills market orders instantly; this module adds the missing
GTC limit order: a row in `resting_orders` that a worker tick fills through
`automation.execute_paper_trade` — the same executor, fees and position
bookkeeping as every other fill — once the live price crosses the limit.

Semantics (deliberately minimal — a terminal feature, not a matching engine):
- buy / cover fill when market <= limit; sell / short fill when market >= limit.
- An order that is immediately fillable at placement is REFUSED with
  `would_fill_immediately` — the terminal's market button is one click away,
  and refusing beats surprising the user with an instant "limit" fill.
- Fills execute at the observed market price (which satisfies the limit), at
  the order's leverage (clamped 1..10 at placement; the spot terminal never
  sends it, so spot stays at the fully-funded 1x) — identical to the
  terminals' market orders.
- stop_loss / take_profit ride the order and are registered on the position by
  the executor at fill time (never-loosen semantics live there).
- Exactly-once across crashes: every fill carries
  client_order_id = "resting:{id}" and the signals UNIQUE index dedupes; a
  crashed 'filling' claim is safely retried later.

Affordability is checked at FILL time by the executor (cash can change while
an order rests); a fill refused for cash/position reasons marks the order
`rejected` with the executor's reason.

Kill switch: RESTING_ORDERS_ENABLED (default on). The tick is a no-op when the
table has no open rows, so the loop costs nothing until someone uses the
feature.

SIMULATOR-ONLY BY DESIGN: fills go through the paper executor and NEVER route
to the live execution gateway (service/server/execution/). Manual terminal
trades are simulator-only today and resting orders inherit exactly that
boundary. If live routing is ever wanted here, it must go through
execution/gateway.py deliberately — do not widen this module quietly. (Real
gateway testing is planned; this boundary is part of its verification.)
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Optional

from database import begin_write_transaction, get_db_connection

# Crypto only: the terminals trade crypto, and one batched OKX tickers call
# prices every open order. Other markets need a per-symbol quote fan-out —
# add them when a terminal exists for them, not before.
SUPPORTED_MARKETS = ("crypto",)
VALID_SIDES = ("buy", "sell", "short", "cover")
MAX_OPEN_PER_AGENT = 50
MAX_QUANTITY = 1_000_000
# A 'filling' claim older than this is a crashed worker — retry it (the
# client_order_id makes the retry exactly-once).
STALE_FILLING_SECONDS = 600


def _clamp_leverage(v: Any) -> float:
    # Same clamp as the realtime endpoint's validator (routes_models): 1×…10×,
    # invalid/absent ⇒ 1× (the fully-funded legacy fill).
    try:
        v = float(v or 1.0)
    except (TypeError, ValueError):
        return 1.0
    return max(1.0, min(10.0, v))


def resting_orders_enabled() -> bool:
    return os.getenv("RESTING_ORDERS_ENABLED", "true").strip().lower() in (
        "1", "true", "yes", "on")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ─────────────────────────── placement / cancel / list ───────────────────────

def place_resting_order(agent_id: int, market: str, side: str, symbol: str,
                        quantity: float, limit_price: float,
                        market_price: Optional[float],
                        stop_loss: Optional[float] = None,
                        take_profit: Optional[float] = None,
                        leverage: Any = None,
                        content: str = "") -> tuple[Optional[dict], Optional[str]]:
    """Validate and insert an open resting order.

    Returns (order_dict, None) or (None, reason). `market_price` is the live
    price used for the immediate-fill refusal and TP/SL sanity; None skips
    those checks (quote outage must not block cancels, but placement without a
    quote is refused — a limit against an unknown market is a coin flip).
    """
    market = (market or "").strip().lower()
    side = (side or "").strip().lower()
    symbol = (symbol or "").strip().upper()
    if market not in SUPPORTED_MARKETS:
        return None, f"market '{market}' does not support resting orders yet"
    if side not in VALID_SIDES:
        return None, f"invalid side '{side}'"
    if not symbol:
        return None, "symbol required"
    try:
        quantity = float(quantity)
        limit_price = float(limit_price)
    except (TypeError, ValueError):
        return None, "invalid quantity/price"
    if not (0 < quantity <= MAX_QUANTITY):
        return None, "invalid quantity"
    if limit_price <= 0:
        return None, "invalid limit price"
    if market_price is None or market_price <= 0:
        return None, "live price unavailable — try again"
    leverage = _clamp_leverage(leverage)

    # Refuse orders that would fill on the next tick: the user wanted a limit,
    # not a market order in disguise.
    if side in ("buy", "cover") and market_price <= limit_price:
        return None, "would_fill_immediately"
    if side in ("sell", "short") and market_price >= limit_price:
        return None, "would_fill_immediately"

    # TP/SL only make sense on opening sides, validated against the LIMIT
    # price (the eventual fill is at or better).
    if (stop_loss is not None or take_profit is not None) and side not in ("buy", "short"):
        return None, "stop_loss/take_profit only apply to buy/short"
    for name, val in (("stop_loss", stop_loss), ("take_profit", take_profit)):
        if val is not None:
            try:
                val = float(val)
            except (TypeError, ValueError):
                return None, f"invalid {name}"
            if val <= 0:
                return None, f"invalid {name}"
    if side == "buy":
        if stop_loss is not None and float(stop_loss) >= limit_price:
            return None, "stop_loss must be below the limit price for a buy"
        if take_profit is not None and float(take_profit) <= limit_price:
            return None, "take_profit must be above the limit price for a buy"
    if side == "short":
        if stop_loss is not None and float(stop_loss) <= limit_price:
            return None, "stop_loss must be above the limit price for a short"
        if take_profit is not None and float(take_profit) >= limit_price:
            return None, "take_profit must be below the limit price for a short"

    now = _now_iso()
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        begin_write_transaction(cursor)
        cursor.execute(
            "SELECT COUNT(*) AS n FROM resting_orders WHERE agent_id = ? AND status = 'open'",
            (agent_id,))
        if cursor.fetchone()["n"] >= MAX_OPEN_PER_AGENT:
            conn.rollback()
            return None, f"open-order cap reached ({MAX_OPEN_PER_AGENT})"
        cursor.execute(
            """INSERT INTO resting_orders
               (agent_id, market, symbol, side, quantity, limit_price, leverage,
                stop_loss, take_profit, status, content, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?, ?)""",
            (agent_id, market, symbol, side, quantity, limit_price, leverage,
             stop_loss, take_profit, content or "", now, now))
        order_id = cursor.lastrowid
        conn.commit()
    finally:
        conn.close()
    return {
        "id": order_id, "market": market, "symbol": symbol, "side": side,
        "quantity": quantity, "limit_price": limit_price, "leverage": leverage,
        "stop_loss": stop_loss, "take_profit": take_profit,
        "status": "open", "created_at": now,
    }, None


def cancel_resting_order(agent_id: int, order_id: int) -> tuple[bool, str]:
    """Cancel one of the agent's own OPEN orders.

    The status-guarded UPDATE is the fence: rowcount 0 means the order is
    missing, foreign, or already filled/cancelled — reported distinctly so the
    UI can tell 'too late, it filled' from 'not yours'.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        begin_write_transaction(cursor)
        cursor.execute(
            """UPDATE resting_orders SET status = 'cancelled', updated_at = ?
               WHERE id = ? AND agent_id = ? AND status = 'open'""",
            (_now_iso(), order_id, agent_id))
        if cursor.rowcount == 1:
            conn.commit()
            return True, "cancelled"
        cursor.execute(
            "SELECT status, agent_id FROM resting_orders WHERE id = ?", (order_id,))
        row = cursor.fetchone()
        conn.rollback()
        if not row or row["agent_id"] != agent_id:
            return False, "not_found"
        return False, f"not_open:{row['status']}"
    finally:
        conn.close()


def list_resting_orders(agent_id: int, status: Optional[str] = "open",
                        limit: int = 100) -> list[dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        where = "agent_id = ?"
        args: list[Any] = [agent_id]
        if status:
            where += " AND status = ?"
            args.append(status)
        args.append(max(1, min(int(limit), 200)))
        cursor.execute(
            f"""SELECT id, market, symbol, side, quantity, limit_price,
                       leverage, stop_loss, take_profit, status, reason,
                       signal_id, created_at, updated_at
                FROM resting_orders WHERE {where}
                ORDER BY id DESC LIMIT ?""", args)
        return [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()


# ─────────────────────────── the fill watcher ─────────────────────────────────

def _crossed(side: str, market_price: float, limit_price: float) -> bool:
    if side in ("buy", "cover"):
        return market_price <= limit_price
    return market_price >= limit_price


def _claim(cursor, order_id: int, from_status: str = "open") -> bool:
    cursor.execute(
        """UPDATE resting_orders SET status = 'filling', updated_at = ?
           WHERE id = ? AND status = ?""",
        (_now_iso(), order_id, from_status))
    return cursor.rowcount == 1


def _finish(cursor, order_id: int, status: str, reason: Optional[str] = None,
            signal_id: Optional[int] = None) -> None:
    cursor.execute(
        """UPDATE resting_orders SET status = ?, reason = ?, signal_id = ?,
                  updated_at = ? WHERE id = ?""",
        (status, reason, signal_id, _now_iso(), order_id))


def run_resting_orders_tick() -> dict[str, Any]:
    """One watcher pass: price every open crypto order with a single batched
    OKX tickers call, fill the crossed ones, retry stale 'filling' claims.

    Every fill goes through execute_paper_trade with
    client_order_id='resting:{id}' — the UNIQUE index makes a crash-retry
    exactly-once (a duplicate comes back as an error string; we then look the
    signal up and mark the order filled).
    """
    if not resting_orders_enabled():
        return {"checked": 0, "filled": 0, "rejected": 0}

    from automation import execute_paper_trade
    from crypto_feed import fetch_tickers

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """SELECT id, agent_id, market, symbol, side, quantity, limit_price,
                      leverage, stop_loss, take_profit, status, updated_at
               FROM resting_orders WHERE status IN ('open', 'filling')""")
        rows = [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()
    if not rows:
        return {"checked": 0, "filled": 0, "rejected": 0}

    # Stale-claim recovery: a 'filling' row nobody finished is a crashed tick.
    now = datetime.now(timezone.utc)
    stale: list[dict[str, Any]] = []
    open_rows: list[dict[str, Any]] = []
    for r in rows:
        if r["status"] == "open":
            open_rows.append(r)
            continue
        try:
            age = (now - datetime.strptime(
                str(r["updated_at"])[:19], "%Y-%m-%dT%H:%M:%S"
            ).replace(tzinfo=timezone.utc)).total_seconds()
        except (TypeError, ValueError):
            age = STALE_FILLING_SECONDS + 1
        if age > STALE_FILLING_SECONDS:
            stale.append(r)

    symbols = sorted({r["symbol"] for r in open_rows + stale})
    try:
        tickers = fetch_tickers([f"{s}USDT" for s in symbols])
    except Exception:  # noqa: BLE001 — quote outage: try again next tick
        return {"checked": len(open_rows), "filled": 0, "rejected": 0,
                "error": "tickers_unavailable"}
    price_by_symbol = {
        t["symbol"].removesuffix("USDT"): float(t["last_price"])
        for t in tickers if t.get("last_price")
    }

    filled = rejected = 0
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        for order in open_rows + stale:
            price = price_by_symbol.get(order["symbol"])
            is_stale_retry = order["status"] == "filling"
            if price is None or price <= 0:
                continue
            if not is_stale_retry and not _crossed(order["side"], price, float(order["limit_price"])):
                continue

            begin_write_transaction(cursor)
            if not _claim(cursor, order["id"],
                          from_status="filling" if is_stale_retry else "open"):
                conn.rollback()
                continue  # cancelled (or finished) under us — their fence won
            # For a stale retry the claim is a self-UPDATE ('filling' →
            # 'filling' refreshes updated_at) so a second worker's window
            # re-arms rather than double-claims.
            conn.commit()

            signal_id, err = execute_paper_trade(
                order["agent_id"], order["symbol"], order["market"],
                order["side"], float(order["quantity"]), price,
                content=order.get("content") or f"limit order #{order['id']} (terminal)",
                stop_loss=order["stop_loss"], take_profit=order["take_profit"],
                client_order_id=f"resting:{order['id']}",
                leverage=_clamp_leverage(order.get("leverage")),
            )

            begin_write_transaction(cursor)
            if signal_id is not None:
                _finish(cursor, order["id"], "filled", signal_id=signal_id)
                filled += 1
            elif err and "duplicate client_order_id" in err:
                # Crash-retry of an already-executed fill: recover the signal.
                cursor.execute(
                    "SELECT id FROM signals WHERE client_order_id = ?",
                    (f"resting:{order['id']}",))
                sig = cursor.fetchone()
                _finish(cursor, order["id"], "filled",
                        signal_id=sig["id"] if sig else None)
                filled += 1
            else:
                _finish(cursor, order["id"], "rejected", reason=err or "fill failed")
                rejected += 1
            conn.commit()
    finally:
        conn.close()
    return {"checked": len(open_rows), "filled": filled, "rejected": rejected}
