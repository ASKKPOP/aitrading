"""AI trading automation (Target 3).

Executes user-configured rules: on each tick, every enabled + due rule runs the
multi-agent analysis (analysis_agents.run_analysis). If the rule has auto_execute
on, the decision is BUY or SELL, and confidence >= min_confidence, the fill is
routed by the rule's account_type (see execution/gateway.py):

  simulator — platform ledger only (signals row + position + cash, same ledger
              as a manual trade, signal_type 'automation').
  shadow    — platform ledger is authoritative (run by simulation); when a
              gateway is configured the order is also sent to the broker's
              SANDBOX and the fill drift is journalled. No real money.
  live      — the real order goes to the user's configured trading gateway and
              the broker is authoritative; the ledger mirrors what filled.

Safety invariants:
  - live requires a configured gateway with usable credentials. Without one the
    rule is REFUSED with a message, never silently simulated — a fake fill that
    looks real is worse than no fill.
  - In live, the platform ledger is written only after the broker accepted the
    order, so a rejected order never produces a platform position.
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
import markets
import trend_accounts

logger = logging.getLogger(__name__)

VALID_MARKETS = markets.automatable_markets()
EXECUTABLE_ACTIONS = ("buy", "sell", "short", "cover")


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
                        take_profit: Optional[float] = None,
                        run_id: Optional[int] = None,
                        client_order_id: Optional[str] = None,
                        leverage: float = 1.0,
                        fence=None) -> tuple[Optional[int], Optional[str]]:
    """Execute a simulator trade with the same ledger as a manual signal:
    signals row (signal_type='automation') + position update + cash update.
    On buys, stop_loss/take_profit (from the risk gate) are registered on the
    position row in the same transaction so the SL/TP watcher can act on them.
    Returns (signal_id, None) on success or (None, reason) when skipped.

    Trading Runs (Plan 10): when run_id is given the signals row carries the
    run attribution + fee, the position row is stamped with the owning run,
    and a 'trade' run_event rides THIS transaction (a committed trade can
    never be missing from the journal). client_order_id ("run:{id}:cyc:{seq}")
    is checked pre-insert on this fresh connection AND enforced by a UNIQUE
    index — exactly-once per cycle even across worker crashes. `fence` is an
    optional callable(cursor) -> Optional[str] evaluated inside the
    transaction; a non-None return aborts (zombie-claimant protection)."""
    # Per-market rate (2026-07-28). The flat TRADE_FEE_RATE charged a crypto
    # taker fee to grain futures and FX majors; fee_rate() falls back to it for
    # any market with no entry, so an unknown market is unchanged.
    from fees import fee_rate
    from services import _reserve_signal_id, _update_position_from_signal
    from routes_shared import get_position_snapshot, run_scope_sql

    if side not in EXECUTABLE_ACTIONS:
        return None, f"action '{side}' is not executable"
    if quantity <= 0 or price <= 0:
        return None, "invalid quantity/price"
    # Isolated-margin leverage (2026-07-23): margin = notional / L. L=1 is the
    # prior fully-funded model and every formula below reduces to it exactly.
    lev = float(leverage or 1.0)
    if lev < 1.0:
        lev = 1.0
    # Platform-wide futures block (owner 2026-11-20). The ledger refuses too;
    # checking here returns a clean skip reason instead of a logged traceback.
    from futures_policy import order_refusal
    futures_refusal = order_refusal(market, side, lev, symbol=symbol)
    if futures_refusal:
        return None, futures_refusal

    rate = fee_rate(market)
    trade_value = price * quantity
    fee = trade_value * rate
    now = _now_iso()

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        begin_write_transaction(cursor)

        if fence is not None:
            fence_reason = fence(cursor)
            if fence_reason:
                conn.rollback()
                return None, fence_reason
        # Futures block, run shape: a market_type='futures' run that was
        # already running when the switch went on never passes start_run
        # again, and the ledger cannot see market_type — refuse its opens
        # here, inside the transaction. Closes are not affected.
        if run_id is not None and side in ("buy", "short"):
            cursor.execute("SELECT market, market_type FROM trading_runs WHERE id = ?",
                           (run_id,))
            run_row = cursor.fetchone()
            if run_row:
                run_refusal = order_refusal(run_row["market"], side, lev,
                                            market_type=run_row["market_type"],
                                            cursor=cursor)
                if run_refusal:
                    conn.rollback()
                    return None, run_refusal
        # Plan 32: on a dedicated trend account only the trend rule opens.
        fenced = trend_accounts.entry_fence(cursor, agent_id, side,
                                            client_order_id)
        if fenced:
            conn.rollback()
            return None, fenced
        if client_order_id:
            cursor.execute("SELECT id FROM signals WHERE client_order_id = ?",
                           (client_order_id,))
            if cursor.fetchone():
                conn.rollback()
                return None, "duplicate client_order_id (cycle already executed)"

        short_entry: Optional[float] = None
        long_entry: Optional[float] = None
        # Closes return the escrowed MARGIN (notional/L) using the POSITION's
        # own leverage, not the caller's — the source of truth for what was
        # posted at open. Defaults to 1 (fully-funded) for legacy rows.
        pos_lev = 1.0

        def _read_pos_leverage() -> float:
            scope, scope_args = run_scope_sql(run_id)
            cursor.execute(
                "SELECT leverage FROM positions WHERE agent_id = ? AND "
                "market = ? AND symbol = ?" + scope,
                (agent_id, market, symbol, *scope_args))
            r = cursor.fetchone()
            try:
                return max(1.0, float(r["leverage"])) if r and r["leverage"] else 1.0
            except (KeyError, TypeError, ValueError):
                return 1.0

        if side == "sell":
            pos = get_position_snapshot(cursor, agent_id, market, symbol, None, run_id)
            current_qty = float(pos["quantity"]) if pos else 0.0
            if current_qty <= 0:
                conn.rollback()
                return None, "no long position to sell"
            quantity = min(quantity, current_qty)
            trade_value = price * quantity
            fee = trade_value * rate
            if pos["entry_price"] is not None:
                long_entry = float(pos["entry_price"])
            pos_lev = _read_pos_leverage()

        if side == "cover":
            # Close (part of) a short book (negative quantity rows).
            pos = get_position_snapshot(cursor, agent_id, market, symbol, None, run_id)
            current_qty = float(pos["quantity"]) if pos else 0.0
            if current_qty >= 0:
                conn.rollback()
                return None, "no short position to cover"
            quantity = min(quantity, -current_qty)
            trade_value = price * quantity
            fee = trade_value * rate
            short_entry = float(pos["entry_price"] or 0)
            if short_entry <= 0:
                conn.rollback()
                return None, "short position entry price missing"
            pos_lev = _read_pos_leverage()

        if side in ("buy", "short"):
            # Shorts escrow the notional as collateral — same debit as a buy
            # (matches the manual signal executor's cash model).
            cursor.execute("SELECT cash FROM agents WHERE id = ?", (agent_id,))
            row = cursor.fetchone()
            cash = row["cash"] if row else 0
            # Only the margin (notional/L) + fee is debited on open.
            margin_due = trade_value / lev
            if cash < margin_due + fee:
                conn.rollback()
                return None, f"insufficient cash (${cash:.2f} < ${margin_due + fee:.2f})"

        # Realized P&L stamp for closing legs: net of THIS leg's fee against
        # the book's average entry. Buys/shorts leave pnl NULL (nothing
        # realized yet) — the /assets and trades views read signals.pnl.
        realized_pnl: Optional[float] = None
        exit_price: Optional[float] = None
        if side == "sell":
            exit_price = price
            if long_entry is not None:
                realized_pnl = (price - long_entry) * quantity - fee
        elif side == "cover":
            exit_price = price
            realized_pnl = (short_entry - price) * quantity - fee

        signal_id = _reserve_signal_id(cursor)
        cursor.execute(
            """
            INSERT INTO signals
            (signal_id, agent_id, message_type, market, signal_type, symbol, token_id, outcome,
             side, entry_price, quantity, content, timestamp, created_at, executed_at,
             run_id, client_order_id, fee_usd, pnl, exit_price)
            VALUES (?, ?, 'operation', ?, 'automation', ?, NULL, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (signal_id, agent_id, market, symbol, side, price, quantity,
             content, int(datetime.now(timezone.utc).timestamp()), now, now,
             run_id, client_order_id, fee, realized_pnl, exit_price),
        )
        _update_position_from_signal(agent_id, symbol, market, side, quantity, price, now,
                                     cursor=cursor, run_id=run_id, leverage=lev)
        # Every positions statement below is scoped to the same book this trade
        # wrote — several runs may hold a position on one agent+market+symbol.
        pos_scope, pos_scope_args = run_scope_sql(run_id)
        if run_id is not None and side in ("buy", "short"):
            # Stamp run ownership on the (possibly just-created) position row so
            # watcher closes attribute to this run even after stop-with-hold.
            # The fill price doubles as a fresh mark (a just-traded position
            # must not read as stale to the fail-closed stop evaluator).
            cursor.execute(
                """UPDATE positions
                   SET current_price = ?, price_updated_at = ?
                   WHERE agent_id = ? AND market = ? AND symbol = ?""" + pos_scope,
                (price, now, agent_id, market, symbol, *pos_scope_args),
            )
        if side == "short" and (stop_loss is not None or take_profit is not None):
            # Short exits are inverted (SL above entry / TP below). NEVER
            # LOOSEN mirrored: a lower stop and a lower target are tighter
            # for a short, so re-shorts take min() of existing vs new.
            cursor.execute(
                """SELECT stop_loss, take_profit FROM positions
                   WHERE agent_id = ? AND market = ? AND symbol = ?""" + pos_scope,
                (agent_id, market, symbol, *pos_scope_args))
            row = cursor.fetchone()
            existing_sl = row["stop_loss"] if row else None
            existing_tp = row["take_profit"] if row else None
            new_sl = min(x for x in (existing_sl, stop_loss) if x is not None) \
                if (existing_sl is not None or stop_loss is not None) else None
            new_tp = min(x for x in (existing_tp, take_profit) if x is not None) \
                if (existing_tp is not None or take_profit is not None) else None
            cursor.execute(
                """UPDATE positions
                   SET stop_loss = ?, take_profit = ?,
                       exit_policy = COALESCE(exit_policy, 'v1')
                   WHERE agent_id = ? AND market = ? AND symbol = ?""" + pos_scope,
                (new_sl, new_tp, agent_id, market, symbol, *pos_scope_args),
            )
        if side == "buy":
            if stop_loss is not None or take_profit is not None:
                # NEVER LOOSEN an existing exit level: a re-buy previously
                # overwrote a ratcheted trailing stop with the fresh fixed-pct
                # level, destroying locked-in protection (panel risk lens).
                # Computed in Python — SQLite MAX(a,b) vs MySQL GREATEST differ.
                cursor.execute(
                    """SELECT stop_loss, take_profit FROM positions
                       WHERE agent_id = ? AND market = ? AND symbol = ?""" + pos_scope,
                    (agent_id, market, symbol, *pos_scope_args))
                row = cursor.fetchone()
                existing_sl = row["stop_loss"] if row else None
                existing_tp = row["take_profit"] if row else None
                new_sl = max(x for x in (existing_sl, stop_loss) if x is not None) \
                    if (existing_sl is not None or stop_loss is not None) else None
                new_tp = max(x for x in (existing_tp, take_profit) if x is not None) \
                    if (existing_tp is not None or take_profit is not None) else None
                cursor.execute(
                    """UPDATE positions
                       SET stop_loss = ?, take_profit = ?,
                           exit_policy = COALESCE(exit_policy, 'v1')
                       WHERE agent_id = ? AND market = ? AND symbol = ?""" + pos_scope,
                    (new_sl, new_tp, agent_id, market, symbol, *pos_scope_args),
                )
            # Open a long: debit MARGIN = notional/L (L=1 ⇒ full notional).
            cursor.execute("UPDATE agents SET cash = cash - ? WHERE id = ?",
                           (trade_value / lev + fee, agent_id))
        elif side == "short":
            # Open a short: escrow MARGIN = notional/L.
            cursor.execute("UPDATE agents SET cash = cash - ? WHERE id = ?",
                           (trade_value / lev + fee, agent_id))
        elif side == "cover":
            # Return escrowed margin (short_entry×qty/L) + short P&L
            # (short_entry−price)×qty − fee. At L=1 this is exactly the old
            # (2×short_entry − price)×qty − fee collateral formula.
            cover_credit = (short_entry * quantity / pos_lev
                            + (short_entry - price) * quantity - fee)
            cursor.execute("UPDATE agents SET cash = cash + ? WHERE id = ?", (cover_credit, agent_id))
        else:
            # Close a long: return margin (long_entry×qty/L) + P&L
            # (price−long_entry)×qty − fee. At L=1 this is trade_value − fee.
            sell_credit = (float(long_entry or 0) * quantity / pos_lev
                           + (price - float(long_entry or 0)) * quantity - fee)
            cursor.execute("UPDATE agents SET cash = cash + ? WHERE id = ?", (sell_credit, agent_id))
        if run_id is not None:
            # Trade event rides THIS transaction — never fail-soft (Plan 10 D6).
            from trading_runs import _emit_event
            _emit_event(cursor, run_id, "trade",
                        {"signal_id": signal_id, "side": side, "symbol": symbol,
                         "market": market, "quantity": quantity, "price": price,
                         "fee_usd": fee, "client_order_id": client_order_id})
        conn.commit()
        return signal_id, None
    except Exception as exc:  # noqa: BLE001
        conn.rollback()
        logger.exception("automation paper trade failed: %s", exc)
        return None, str(exc)
    finally:
        conn.close()


def _alert_gateway_failure(agent_id: int, symbol: str, reason: str) -> None:
    """Tell the user their LIVE rule did not reach the market.

    A live rule that silently stops filling looks identical to a quiet market
    from the outside, so this is the difference between "no signal today" and
    "your broker session expired six hours ago". Deduped per hour so a rule on
    a short interval cannot spam.
    """
    try:
        from alerts import send_alert
        hour = datetime.now(timezone.utc).strftime("%Y%m%d%H")
        send_alert(agent_id, "gateway_down", "gateway_down_live_order_failed",
                   {"symbol": symbol, "reason": reason},
                   dedupe_key=f"gateway_down:{agent_id}:{hour}")
    except Exception:  # noqa: BLE001 — alerting must never break trading
        logger.debug("gateway failure alert failed for agent %s", agent_id)


def _execute_for_account_type(config: dict[str, Any], agent_id: int, symbol: str,
                              market: str, side: str, quantity: float, price: float,
                              stop_loss: Any, take_profit: Any,
                              result: dict[str, Any]) -> tuple[Optional[int], Optional[str]]:
    """Land a fill according to the rule's account_type.

      simulator — platform ledger only (unchanged behaviour).
      shadow    — platform ledger is authoritative, i.e. run by simulation.
                  When a gateway is configured the same order also goes to the
                  broker's SANDBOX and the drift is journalled. No real money.
      live      — the real order goes to the gateway FIRST. The broker is
                  authoritative, so the ledger is only written once the order
                  actually reached the broker; a rejection produces no position.

    Returns (signal_id, skip_reason) exactly like execute_paper_trade.
    """
    from execution.base import OrderStatus
    from execution.gateway import LIVE, SHADOW, normalize_account_type, submit_live, submit_shadow

    mode = normalize_account_type(config.get("account_type"))
    result["execution_mode"] = mode

    # Plan 32: an automation rule does not trade a dedicated trend account —
    # not to open (the ledger fences that) and not to sell the rule's
    # position either. Checked BEFORE any venue: a live order the broker
    # filled and the ledger then refused is a real position nothing on the
    # platform knows about. For a live order, not knowing is a refusal.
    try:
        enrolled = agent_id in trend_accounts.enrolled_ids()
    except Exception:  # noqa: BLE001
        enrolled = None
        logger.warning("trend-account check failed for agent %s", agent_id,
                       exc_info=True)
    if enrolled:
        return None, trend_accounts.FENCED
    if enrolled is None and mode == LIVE:
        return None, "account checks unavailable — live order not sent"
    # Futures block BEFORE any venue: the ledger would refuse this open
    # after a live broker had already filled it.
    from futures_policy import order_refusal
    futures_refusal = order_refusal(market, side, symbol=symbol)
    if futures_refusal:
        return None, futures_refusal
    # A live sell larger than the held long (or a cover larger than the held
    # short) is a NEW short or long at a margin broker, even though the verb
    # reads as a close. Rules trade the unowned book, so check it before the
    # venue. A ledger close of what IS held is untouched.
    if mode == LIVE and side in ("sell", "cover"):
        from futures_policy import futures_blocked
        if futures_blocked():
            from routes_shared import get_position_snapshot
            conn = get_db_connection()
            try:
                pos = get_position_snapshot(conn.cursor(), agent_id, market,
                                            symbol, None, None)
            finally:
                conn.close()
            held = float(pos["quantity"]) if pos else 0.0
            if side == "sell" and quantity > max(held, 0.0) + 1e-9:
                return None, ("futures trading is disabled on this platform "
                              "(spot and US stock only): a live sell larger than "
                              "the held long would open a short at the broker — "
                              "live order not sent")
            if side == "cover" and quantity > max(-held, 0.0) + 1e-9:
                return None, ("futures trading is disabled on this platform "
                              "(spot and US stock only): a live cover larger than "
                              "the held short would open a position at the broker "
                              "— live order not sent")

    if mode == LIVE:
        order = submit_live(agent_id, symbol, market, side, quantity, price)
        result["broker"] = order.broker
        result["broker_order_id"] = order.broker_order_id
        if order.status not in (OrderStatus.FILLED, OrderStatus.SUBMITTED):
            # Nothing reached the market — do not write a platform position.
            reason = order.error_message or order.status.value
            _alert_gateway_failure(agent_id, symbol, reason)
            return None, f"gateway rejected order: {reason}"
        # Broker filled: mirror into the ledger so the UI and SL/TP watcher
        # see the position. Quantity comes from the broker when it reported one
        # (`is not None`, not truthiness — a genuine 0.0 fill must NOT fall back
        # to the requested size and overstate the position); only default to the
        # requested size when the broker gave no fill quantity at all.
        filled = order.filled_qty if order.filled_qty is not None else quantity
        return execute_paper_trade(agent_id, symbol, market, side, filled, price,
                                   stop_loss=stop_loss, take_profit=take_profit)

    signal_id, skip = execute_paper_trade(agent_id, symbol, market, side, quantity,
                                          price, stop_loss=stop_loss,
                                          take_profit=take_profit)
    if mode == SHADOW and signal_id:
        # Best-effort comparison leg; never affects the completed simulation.
        try:
            shadow = submit_shadow(agent_id, symbol, market, side, quantity, price,
                                   ledger_quantity=quantity, signal_id=signal_id)
            if shadow is not None:
                result["shadow_broker"] = shadow.broker
                result["shadow_status"] = shadow.status.value
        except Exception:  # noqa: BLE001
            logger.exception("shadow leg failed for agent %s", agent_id)
    return signal_id, skip


def _entitlement_blocks(agent_id: int) -> Optional[str]:
    """In-loop entitlement check on its own short connection (fail-closed:
    an unverifiable plan blocks auto-execution — spend prevention)."""
    try:
        from entitlements import check_auto_execute, enforcement_enabled
        if not enforcement_enabled():
            return None
        conn = get_db_connection()
        try:
            deny = check_auto_execute(conn.cursor(), agent_id)
            conn.commit()
            return deny
        finally:
            conn.close()
    except Exception:  # noqa: BLE001
        return "entitlement check unavailable"


def _gateway_blocks(agent_id: int, account_type: Optional[str],
                    market: Optional[str] = None) -> Optional[str]:
    """Refusal reason for a live rule with no usable trading gateway.

    Fail-closed: if the gateway cannot be inspected we refuse rather than fall
    through, because the alternative is routing real money on an unverified
    configuration. The rule's market rides along so a live rule needs a
    gateway that can trade ITS market (pre-live TODO #3)."""
    try:
        from execution.gateway import live_refusal_reason
        return live_refusal_reason(agent_id, account_type, market=market)
    except Exception:  # noqa: BLE001
        logger.exception("gateway check failed for agent %s", agent_id)
        return "trading gateway check unavailable"


def _agent_budget_blocks(config: dict[str, Any], entry: float) -> Optional[str]:
    """Agent-mode budget check wrapper (fail-closed: an error blocks the buy —
    a budget cap that silently fails open would defeat full delegation)."""
    try:
        from agent_planner import budget_blocks
        order_usd = float(config.get("size_usd") or 0)
        return budget_blocks(config["agent_id"], float(config.get("budget_usd") or 0), order_usd)
    except Exception as exc:  # noqa: BLE001
        logger.exception("agent-mode budget check failed: %s", exc)
        return f"agent-mode budget check unavailable: {exc}"


# ─────────────────────────── one rule ───────────────────────────

def _time_stop_cooldown_blocks(agent_id: int, symbol: str, market: str,
                               action: Optional[str]) -> Optional[str]:
    """Skip reason when a recent time-stop exit puts this symbol in cooldown —
    prevents the close→re-enter fee-bleed loop the time stop would otherwise
    manufacture (0.2% round trip per cycle). Buys only; fail-open."""
    if action != "buy":
        return None
    try:
        import strategy_config as scfg
        hours = scfg.time_stop_cooldown_hours()
        if hours <= 0:
            return None
        from datetime import timedelta
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)) \
            .strftime("%Y-%m-%dT%H:%M:%SZ")
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT executed_at FROM signals
                   WHERE agent_id = ? AND market = ? AND symbol = ?
                     AND signal_type = 'automation' AND side = 'sell'
                     AND content LIKE 'risk: time_stop%'
                     AND executed_at >= ?
                   ORDER BY executed_at DESC LIMIT 1""",
                (agent_id, market, symbol, cutoff))
            row = cursor.fetchone()
        finally:
            conn.close()
        if row:
            return (f"time-stop cooldown: {symbol} was time-stopped at "
                    f"{row['executed_at']} (re-entry blocked {hours}h)")
    except Exception:  # noqa: BLE001
        logger.exception("time-stop cooldown check failed (fail-open)")
    return None


def _regime_blocks(regime_read: Optional[dict[str, Any]], action: Optional[str]) -> Optional[str]:
    """Skip reason when the enforced regime forbids this NEW BUY. Sells are
    never regime-blocked (exit-permissiveness rule)."""
    if action != "buy" or not regime_read:
        return None
    if not regime_read.get("enforced"):
        return None  # advisory-only until the Phase-4 flip
    if regime_read.get("allow_new_buys", True):
        return None
    reasons = "; ".join(regime_read.get("reasons") or [])
    return f"regime '{regime_read.get('regime')}' blocks new buys ({reasons})"


def evaluate_execution_gates(config: dict[str, Any], agent_id: int, symbol: str,
                             market: str, action: Optional[str],
                             confidence: Optional[float], entry: Any,
                             regime_read: Optional[dict[str, Any]] = None,
                             technical: Optional[dict[str, Any]] = None,
                             run_id: Optional[int] = None) -> dict[str, Any]:
    """The worker's pre-trade gate chain, side-effect free — shared by run_rule
    and the test-run preview so the two can never drift. Returns
      {skip_reason, gate, regime_size_multiplier}
    skip_reason None => the order may proceed to execution; gate is the
    risk-engine verdict (with sized quantity + SL/TP) when it was consulted."""
    from routes_shared import is_market_open

    out: dict[str, Any] = {"skip_reason": None, "gate": None, "regime_size_multiplier": None}
    if not config.get("auto_execute"):
        out["skip_reason"] = "auto_execute off"
    elif (_gateway_deny := _gateway_blocks(agent_id, config.get("account_type"),
                                           market=config.get("market"))):
        # account_type decides where the fill lands (execution/gateway.py):
        # simulator and shadow always have somewhere to go; live is refused
        # unless the user has actually configured a trading gateway. Never
        # downgrade live to simulation — a fake fill that looks real is worse
        # than no fill.
        out["skip_reason"] = _gateway_deny
    elif (_ent_deny := _entitlement_blocks(agent_id)):
        # Plan 10 D9: in-loop entitlement gate — a lapsed subscription stops
        # existing auto-executing rules too, not just new ones. Env-gated
        # (ENTITLEMENTS_ENFORCED); returns None when enforcement is off.
        out["skip_reason"] = _ent_deny
    elif action not in EXECUTABLE_ACTIONS:
        out["skip_reason"] = f"decision is '{action}'"
    elif (confidence or 0) < float(config.get("min_confidence") or 0):
        out["skip_reason"] = f"confidence {confidence} below threshold {config.get('min_confidence')}"
    elif not is_market_open(market):
        out["skip_reason"] = "market closed"
    elif _event_guard_blocks():
        # Card 07 — scheduled macro releases spike volatility without a
        # reliable direction; skip new entries inside the release window.
        # Opt-in via EVENT_GUARD_ENABLED (default off).
        out["skip_reason"] = _event_guard_blocks()
    elif _time_stop_cooldown_blocks(agent_id, symbol, market, action):
        out["skip_reason"] = _time_stop_cooldown_blocks(agent_id, symbol, market, action)
    elif _regime_blocks(regime_read, action):
        # Phase 2 regime gate — active only when REGIME_FILTER_ENABLED
        # (Phase-4 flip). Blocks new buys in panic/euphoria/event regimes;
        # never blocks sells.
        out["skip_reason"] = _regime_blocks(regime_read, action)
    elif not entry or entry <= 0:
        out["skip_reason"] = "no valid price in decision"
    elif (config.get("mode") or "manual") == "agent" and action == "buy" and (
            _budget_reason := _agent_budget_blocks(config, float(entry))):
        # Deterministic budget cap — the planner proposes, this disposes.
        out["skip_reason"] = _budget_reason
    else:
        quantity = float(config.get("size_usd") or 0) / float(entry)
        if (action == "buy" and regime_read is not None
                and regime_read.get("enforced")):
            multiplier = float(regime_read.get("size_multiplier") or 1.0)
            if multiplier != 1.0:
                quantity *= multiplier
                out["regime_size_multiplier"] = multiplier
        else:
            # Plan 31 item 8: SHADOW (log-only) — when the regime is NOT
            # enforced, journal what the entry policy WOULD have done to
            # this buy (veto / resize / allow) without touching quantity.
            # No-op unless REGIME_SHADOW; enforcement above stays untouched.
            from regime import shadow_gate_check
            shadow = shadow_gate_check(regime_read, market=market,
                                       symbol=symbol, action=action)
            if shadow is not None:
                out["regime_shadow"] = shadow
        # Risk gate: breaker → limits → vol sizing → Kelly. No-op unless
        # RISK_ENGINE_ENABLED; rejections are journaled via skip_reason.
        # σ passed is the DAILY sigma (never sigma_24h_pct — hourly units).
        from risk_engine import evaluate_order
        sigma_daily = technical.get("sigma_daily_pct") if isinstance(technical, dict) else None
        gate = evaluate_order(agent_id, symbol, market, action, quantity, float(entry),
                              sigma_daily_pct=sigma_daily, run_id=run_id)
        out["gate"] = gate
        if not gate.allowed:
            out["skip_reason"] = gate.reason
    return out


def _execution_feasibility(agent_id: int, symbol: str, market: str, side: str,
                           quantity: float, price: float) -> Optional[str]:
    """Read-only mirror of execute_paper_trade's cash/position preconditions,
    for the test-run preview. Returns a skip reason or None.

    Uses the same per-market rate the real fill does — a mirror charging a
    different fee would refuse previews the actual trade would accept."""
    from fees import fee_rate
    from routes_shared import get_position_snapshot

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        if side == "sell":
            pos = get_position_snapshot(cursor, agent_id, market, symbol, None, None)
            if not pos or float(pos["quantity"]) <= 0:
                return "no long position to sell"
        elif side == "cover":
            pos = get_position_snapshot(cursor, agent_id, market, symbol, None, None)
            if not pos or float(pos["quantity"]) >= 0:
                return "no short position to cover"
        elif side in ("buy", "short"):
            cursor.execute("SELECT cash FROM agents WHERE id = ?", (agent_id,))
            row = cursor.fetchone()
            cash = row["cash"] if row else 0
            need = price * quantity * (1 + fee_rate(market))
            if cash < need:
                return f"insufficient cash (${cash:.2f} < ${need:.2f})"
        return None
    finally:
        conn.close()


def preview_rule_execution(config: dict[str, Any], analysis: dict[str, Any]) -> dict[str, Any]:
    """'Would this have executed?' — the worker's gate chain applied to an
    already-computed analysis plus a read-only feasibility check. Never places
    a trade and never writes. Powers the Automation test-run verdict."""
    agent_id = config["agent_id"]
    symbol = (analysis.get("symbol") or config.get("symbol") or "").upper()
    market = analysis.get("market") or config.get("market") or "crypto"

    _analysts = analysis.get("analysts") if isinstance(analysis.get("analysts"), dict) else {}
    _tech_block = (_analysts or {}).get("technical")
    technical = _tech_block.get("data") if isinstance(_tech_block, dict) else None

    regime_read = None
    if market == "crypto":
        try:
            from regime import evaluate_market_regime
            regime_read = evaluate_market_regime()
        except Exception as exc:  # noqa: BLE001
            logger.debug("regime read unavailable in preview: %s", exc)

    decision = analysis.get("decision") or {}
    action = decision.get("action")
    confidence = decision.get("confidence")
    entry = decision.get("entry")

    gates = evaluate_execution_gates(config, agent_id, symbol, market, action,
                                     confidence, entry, regime_read, technical)
    out: dict[str, Any] = {"would_execute": False, "skip_reason": gates["skip_reason"],
                           "action": action, "confidence": confidence}
    gate = gates.get("gate")
    if gates["skip_reason"] is None and gate is not None:
        feasibility = _execution_feasibility(agent_id, symbol, market, action,
                                             gate.quantity, float(entry))
        if feasibility:
            out["skip_reason"] = feasibility
        else:
            out["would_execute"] = True
            out["quantity"] = gate.quantity
            out["stop_loss"] = gate.stop_loss
            out["take_profit"] = gate.take_profit
            if gate.adjustment:
                out["adjustment"] = gate.adjustment
    return out


def run_rule(config: dict[str, Any]) -> dict[str, Any]:
    """Run one automation rule: analysis -> (maybe) execute -> record the run."""
    from analysis_agents import run_analysis

    config_id = config["id"]
    agent_id = config["agent_id"]
    symbol = config["symbol"]
    market = config["market"]

    result: dict[str, Any] = {"config_id": config_id, "executed": False, "skip_reason": None}

    # Plan 32: an auto-executing rule does not trade a dedicated trend
    # account (_execute_for_account_type). Say so before paying for the
    # analysis, every interval, of an order that will be refused.
    if config.get("auto_execute"):
        try:
            fenced = trend_accounts.is_trend_account(agent_id)
        except Exception:  # noqa: BLE001 — the execution-time check stands
            fenced = False
        if fenced:
            result["skip_reason"] = trend_accounts.FENCED
            result.update({"action": None, "confidence": None, "signal_id": None})
            _record_run(config_id, agent_id, result, None)
            return result

    # Platform-wide block (owner 2026-11-20): an auto-executing rule on a
    # market nothing may open on (futures, forex, options, polymarket) is skipped before paying for
    # the analysis, unless the book still holds that symbol: then it runs, so
    # the rule can still close what it holds.
    if config.get("auto_execute"):
        from futures_policy import _norm, blocked_markets
        if _norm(market) in blocked_markets():
            from routes_shared import get_position_snapshot
            conn = get_db_connection()
            try:
                held = get_position_snapshot(conn.cursor(), agent_id, market,
                                             symbol, None, None)
            finally:
                conn.close()
            if not held or abs(float(held["quantity"] or 0)) <= 1e-12:
                result["skip_reason"] = (
                    f"{market} trading is disabled on this platform (spot and "
                    "US stock only) — rule not analysed")
                result.update({"action": None, "confidence": None, "signal_id": None})
                _record_run(config_id, agent_id, result, None)
                return result

    # Agent Mode (Plan 06 C1): the planner picks this cycle's parameters
    # (symbol/size/cadence/confidence/risk level) inside deterministic bounds.
    # The user's budget cap is enforced later, pre-gate. Fail-soft: a planner
    # problem falls back to the rule's stored parameters.
    if (config.get("mode") or "manual") == "agent":
        try:
            from agent_planner import plan_agent_cycle
            plan = plan_agent_cycle(config)
            symbol = plan["symbol"]
            config = dict(config)
            config["min_confidence"] = plan["min_confidence"]
            config["size_usd"] = plan["size_usd"]
            result["agent_plan"] = plan
            # cadence: persist the planner's interval so the due-check uses it
            if plan["interval_minutes"] != config.get("interval_minutes"):
                try:
                    _conn = get_db_connection()
                    _conn.execute(
                        "UPDATE automation_configs SET interval_minutes = ? WHERE id = ?",
                        (plan["interval_minutes"], config_id))
                    _conn.commit()
                    _conn.close()
                except Exception:  # noqa: BLE001
                    logger.debug("agent-mode interval persist failed for %s", config_id)
        except Exception as exc:  # noqa: BLE001
            logger.exception("agent-mode planner failed for config %s: %s", config_id, exc)

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
                                provider=config.get("provider") or None,
                                agent_id=agent_id)

        # Confluence telemetry (Phase 1): record the deterministic condition
        # vector alongside every decision — display/journal only until the
        # Phase-4 flip turns it into a gate. Fail-soft.
        # run_analysis nests the per-analyst payloads under "analysts" — reading
        # a top-level "technical" always yielded None, which starved both the
        # confluence telemetry below and the risk gate's sigma (vol sizing then
        # rejected every buy).
        _analysts = analysis.get("analysts") if isinstance(analysis.get("analysts"), dict) else {}
        _tech_block = _analysts.get("technical")
        technical = _tech_block.get("data") if isinstance(_tech_block, dict) else None
        try:
            from confluence import evaluate_confluence
            result["confluence"] = evaluate_confluence(symbol, market, analysis=technical)
        except Exception as exc:  # noqa: BLE001
            logger.debug("confluence telemetry unavailable for %s: %s", symbol, exc)

        # Live calibration prior (Plan 06 A2): the realized hit rate at this
        # confluence count, from production telemetry. Advisory — journaled
        # alongside the decision, never changes execution.
        try:
            from calibration import calibration_prior
            prior = calibration_prior(
                (result.get("confluence") or {}).get("buy_confluence"))
            if prior is not None:
                result["calibration_prior"] = prior
        except Exception as exc:  # noqa: BLE001
            logger.debug("calibration prior unavailable: %s", exc)

        # Regime read (Phase 2): advisory journal always; a hard entry gate
        # only when REGIME_FILTER_ENABLED (Phase-4 flip). Exits never gated.
        regime_read = None
        if market == "crypto":
            try:
                from regime import evaluate_market_regime
                regime_read = evaluate_market_regime()
                result["regime"] = {k: regime_read[k] for k in
                                    ("regime", "reasons", "allow_new_buys", "size_multiplier")}
            except Exception as exc:  # noqa: BLE001
                logger.debug("regime read unavailable: %s", exc)

        decision = analysis.get("decision") or {}
        action = decision.get("action")
        confidence = decision.get("confidence")
        report = (decision.get("report") or decision.get("rationale") or "")[:4000]
        entry = decision.get("entry")

        # Verification telemetry (Plan 06 D3): journal the verifier's verdict
        # with every run. In enforce mode the decision above already reflects it.
        if decision.get("verification") is not None:
            result["verify"] = decision["verification"]

        gates = evaluate_execution_gates(config, agent_id, symbol, market, action,
                                         confidence, entry, regime_read, technical)
        if gates.get("regime_size_multiplier") is not None:
            result["regime_size_multiplier"] = gates["regime_size_multiplier"]
        if gates.get("regime_shadow") is not None \
                and isinstance(result.get("regime"), dict):
            # Plan 31 item 8: the shadow verdict rides the regime telemetry
            # (automation_runs row via _record_run) so the two-week census of
            # would-be vetoes/sizings is measurable from the DB, not just logs.
            result["regime"]["shadow"] = gates["regime_shadow"]
        gate = gates.get("gate")
        if gates["skip_reason"] is not None or gate is None:
            result["skip_reason"] = gates["skip_reason"]
        else:
            signal_id, skip = _execute_for_account_type(
                config, agent_id, symbol, market, action, gate.quantity,
                float(entry), gate.stop_loss, gate.take_profit, result)
            if signal_id:
                result["executed"] = True
                if gate.adjustment:
                    logger.info("risk gate adjusted order (config %s): %s",
                                config_id, gate.adjustment)
                # Alert (Plan 06 C3) — in-app always; email/SMS per user prefs.
                try:
                    from alerts import send_alert
                    send_alert(agent_id, "trade_executed", "automation_trade_executed",
                               {"action_upper": action.upper(), "symbol": symbol,
                                "action": action, "qty": f"{gate.quantity:.6f}",
                                "entry": f"{float(entry):.2f}", "confidence": confidence},
                               dedupe_key=f"exec:{signal_id}")
                except Exception:  # noqa: BLE001
                    logger.debug("trade alert failed for signal %s", signal_id)
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
        # Telemetry: confluence vector + regime read per decision (Phase 1–2).
        telemetry: dict[str, Any] = {}
        if result.get("confluence") is not None:
            telemetry["confluence"] = result["confluence"]
        if result.get("regime") is not None:
            telemetry["regime"] = result["regime"]
        if result.get("verify") is not None:
            telemetry["verify"] = result["verify"]
        if result.get("calibration_prior") is not None:
            telemetry["calibration_prior"] = result["calibration_prior"]
        if result.get("agent_plan") is not None:
            telemetry["agent_plan"] = result["agent_plan"]
        confluence_json = None
        if telemetry:
            try:
                confluence_json = json.dumps(telemetry, ensure_ascii=False)
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
    # Auto-resume sweep (Phase 2): clear expired AUTO-tripped breakers here —
    # the tick always runs, unlike the risk watcher (gated). Manual HALTs are
    # never touched. Fail-soft.
    try:
        from risk_engine import resume_expired_auto_breakers
        resume_expired_auto_breakers()
    except Exception:  # noqa: BLE001
        logger.exception("auto-breaker resume sweep failed")

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
        # Trading-window schedule (Plan 06 C3): out-of-window rules are not due.
        # Fail-soft — a broken schedule degrades to always-on, never freezes.
        try:
            from schedule import in_window, schedule_from_config
            if not in_window(schedule_from_config(cfg), now):
                continue
        except Exception:  # noqa: BLE001
            pass
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
