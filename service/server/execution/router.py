"""
execution/router.py — ExecutionRouter + order persistence + reconciler helper.

ExecutionRouter is the single entry point for all trade execution.  It:
  1. Reads the agent's active broker_accounts row.
  2. Based on execution_mode (paper / shadow / live), decides how to route.
  3. Persists every order to broker_orders with status tracking.
  4. In shadow mode, runs both PaperBroker and the real broker, recording drift
     in position_reconciliations.

Order status lifecycle:
    pending → [submit] → submitted | filled | rejected

Shadow mode:
    Platform ledger (PaperBroker) is authoritative.
    Real broker runs in parallel; result stored in position_reconciliations.
    No real money moves until the agent opts in to live mode + accepts T&Cs.
"""
from __future__ import annotations

import logging
from typing import Optional

from execution.base import Broker, ExecutionMode, Order, OrderStatus

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# DB helpers (keep imports local to avoid circular deps)
# ---------------------------------------------------------------------------

def _get_active_broker_account(agent_id: int,
                               market: "str | None" = None) -> Optional[dict]:
    """The agent's active broker account for `market` (most recent first).

    Pre-live TODO #3: several brokers may be active at once — a stock broker
    and a crypto broker side by side. With `market` given, only an account
    whose broker supports that market is returned; none matching -> None,
    which the router lands on the paper ledger (fail-closed: an order is
    never mis-routed to a venue that cannot trade it). market=None keeps the
    legacy most-recent selection for market-blind callers."""
    from database import get_db_connection
    from execution.base import broker_supports_market
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """SELECT * FROM broker_accounts
           WHERE agent_id = ? AND is_active = 1
           ORDER BY updated_at DESC""",
        (agent_id,),
    )
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    for row in rows:
        if broker_supports_market(row.get("broker") or "", market):
            return row
    return None


def _persist_order(order: Order) -> int:
    """Insert a broker_orders row and return its id."""
    from database import get_db_connection
    from routes_shared import utc_now_iso_z
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO broker_orders
           (agent_id, symbol, market, side, quantity, price, status,
            execution_mode, broker, broker_order_id, error_message,
            signal_id, leader_id, token_id, outcome, created_at, filled_at,
            quote_currency, fx_rate_usd)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            order.agent_id, order.symbol, order.market, order.side,
            order.quantity, order.price, order.status.value,
            order.execution_mode.value, order.broker,
            order.broker_order_id, order.error_message,
            order.signal_id, order.leader_id, order.token_id, order.outcome,
            order.created_at or utc_now_iso_z(),
            order.filled_at,
            order.quote_currency, order.fx_rate_usd,
        ),
    )
    db_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return db_id


def _update_order_status(db_id: int, order: Order) -> None:
    from database import get_db_connection
    from routes_shared import utc_now_iso_z
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """UPDATE broker_orders SET status=?, broker_order_id=?,
           error_message=?, filled_at=? WHERE id=?""",
        (
            order.status.value, order.broker_order_id,
            order.error_message,
            utc_now_iso_z() if order.status == OrderStatus.FILLED else None,
            db_id,
        ),
    )
    conn.commit()
    conn.close()


def _record_reconciliation(
    agent_id: int,
    broker: str,
    paper_order: Order,
    shadow_order: Order,
    error_message: Optional[str] = None,
    status_override: Optional[str] = None,
) -> None:
    from database import get_db_connection
    from routes_shared import utc_now_iso_z
    drift = None
    if (
        paper_order.quantity is not None
        and shadow_order.filled_qty is not None
    ):
        drift = abs(paper_order.quantity - shadow_order.filled_qty)
    status = "ok" if (drift is None or drift < 0.001) else "drift"
    if error_message:
        status = "error"
    # Dry-run shadow (Plan 19): the venue's answer is accepted/rejected, not a
    # fill — the caller names the outcome so it can't be misread as agreement.
    if status_override:
        status = status_override
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO position_reconciliations
           (agent_id, broker, paper_order_id, broker_order_id,
            symbol, paper_qty, broker_qty, drift, status, error_message, recorded_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (
            agent_id, broker,
            paper_order.db_id, shadow_order.broker_order_id,
            paper_order.symbol,
            paper_order.quantity, shadow_order.filled_qty,
            drift, status, error_message,
            utc_now_iso_z(),
        ),
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Broker factory
# ---------------------------------------------------------------------------

def _truthy(value) -> bool:
    """Stored credential flags arrive as JSON, so accept bool or string."""
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


def _build_real_broker(account: dict) -> Broker:
    """Build the real broker for an account row.  Falls back to PaperBroker on error."""
    from execution.paper import PaperBroker

    broker_name = account.get("broker", "")
    creds_enc   = account.get("credentials_enc", "")
    creds: dict = {}
    if creds_enc:
        try:
            from execution.crypto import decrypt_credentials
            creds = decrypt_credentials(creds_enc)
        except ValueError as exc:
            _logger.error("credential decryption failed for agent %s: %s", account["agent_id"], exc)
            return PaperBroker()

    if broker_name == "alpaca":
        from execution.alpaca import AlpacaBroker
        mode = account.get("execution_mode", "shadow")
        return AlpacaBroker(
            key=creds.get("key", ""),
            secret=creds.get("secret", ""),
            paper=(mode != "live"),
        )
    if broker_name == "binance":
        from execution.binance import BinanceBroker
        mode = account.get("execution_mode", "shadow")
        return BinanceBroker(
            key=creds.get("key", ""),
            secret=creds.get("secret", ""),
            testnet=(mode != "live"),
        )
    if broker_name == "ibkr":
        # CPAPI has no key/secret — the gateway session is the credential, so
        # the stored blob carries the gateway URL and account id instead.
        from execution.ibkr import IBKRBroker
        mode = account.get("execution_mode", "shadow")
        return IBKRBroker(
            gateway_url=creds.get("gateway_url", ""),
            account_id=creds.get("account_id", ""),
            paper=(mode != "live"),
            verify_tls=not _truthy(creds.get("allow_self_signed")),
        )
    # Plan 19 venues. sandbox=True means "not live": the venue's test
    # environment for sandbox brokers, the validate-only path for dry-run
    # brokers (kraken/kucoin). Journal-strategy brokers (upbit) are never
    # built in non-live mode — gateway.submit_shadow short-circuits first.
    mode = account.get("execution_mode", "shadow")
    sandbox = mode != "live"
    if broker_name == "bybit":
        from execution.bybit import BybitBroker
        return BybitBroker(key=creds.get("key", ""), secret=creds.get("secret", ""),
                           sandbox=sandbox)
    if broker_name == "okx":
        from execution.okx import OKXBroker
        return OKXBroker(key=creds.get("key", ""), secret=creds.get("secret", ""),
                         passphrase=creds.get("passphrase", ""), sandbox=sandbox)
    if broker_name == "kraken":
        from execution.kraken import KrakenBroker
        return KrakenBroker(key=creds.get("key", ""), secret=creds.get("secret", ""),
                            validate_only=sandbox, account_id=account.get("id"))
    if broker_name == "cryptocom":
        from execution.cryptocom import CryptocomBroker
        return CryptocomBroker(key=creds.get("key", ""), secret=creds.get("secret", ""),
                               sandbox=sandbox)
    if broker_name == "upbit":
        from execution.upbit import UpbitBroker
        return UpbitBroker(key=creds.get("key", ""), secret=creds.get("secret", ""))
    if broker_name == "kucoin":
        from execution.kucoin import KucoinBroker
        return KucoinBroker(key=creds.get("key", ""), secret=creds.get("secret", ""),
                            passphrase=creds.get("passphrase", ""), test_only=sandbox)
    if broker_name == "coinbase":
        from execution.coinbase import CoinbaseBroker
        return CoinbaseBroker(key=creds.get("key", ""), secret=creds.get("secret", ""),
                              preview_only=sandbox)

    return PaperBroker()


# ---------------------------------------------------------------------------
# ExecutionRouter
# ---------------------------------------------------------------------------

class ExecutionRouter:
    """
    Route a signal through the correct broker based on agent config.

    Usage::

        router = ExecutionRouter()
        order = await router.execute(agent_id=42, order=order, cursor=cursor)
    """

    async def execute(self, agent_id: int, order: Order, cursor=None) -> Order:
        from execution.paper import PaperBroker
        from routes_shared import utc_now_iso_z

        # Platform-wide futures block (owner 2026-11-20), before any broker:
        # the live branch below would send the real order first.
        from futures_policy import order_refusal
        futures_refusal = order_refusal(order.market, order.side)
        if futures_refusal:
            order.status = OrderStatus.REJECTED
            order.error_message = futures_refusal
            return order

        account = _get_active_broker_account(agent_id, order.market)
        execution_mode = ExecutionMode(account["execution_mode"]) if account else ExecutionMode.PAPER

        order.execution_mode = execution_mode
        order.created_at = order.created_at or utc_now_iso_z()

        # ── Paper mode (default) ────────────────────────────────────────────
        if execution_mode == ExecutionMode.PAPER:
            order.broker = "paper"
            paper = PaperBroker()
            order = await paper.submit_order(order, cursor=cursor)
            order.db_id = _persist_order(order)
            return order

        # ── Shadow mode ─────────────────────────────────────────────────────
        if execution_mode == ExecutionMode.SHADOW:
            # Paper broker is authoritative
            order.broker = "paper"
            paper = PaperBroker()
            paper_order = await paper.submit_order(order, cursor=cursor)
            paper_order.db_id = _persist_order(paper_order)

            # Real broker runs in background — errors are logged, not raised
            real_broker = _build_real_broker(account)
            shadow_order = Order(
                agent_id=agent_id,
                symbol=order.symbol,
                market=order.market,
                side=order.side,
                quantity=order.quantity,
                price=order.price,
                execution_mode=ExecutionMode.SHADOW,
                broker=real_broker.broker_name,
                signal_id=order.signal_id,
                leader_id=order.leader_id,
                token_id=order.token_id,
                outcome=order.outcome,
                created_at=order.created_at,
            )
            error_msg = None
            try:
                shadow_order = await real_broker.submit_order(shadow_order)
            except Exception as exc:  # noqa: BLE001
                error_msg = str(exc)
                shadow_order.status = OrderStatus.REJECTED
                shadow_order.error_message = error_msg
                _logger.exception("[shadow] broker error for agent %s", agent_id)

            _record_reconciliation(
                agent_id=agent_id,
                broker=real_broker.broker_name,
                paper_order=paper_order,
                shadow_order=shadow_order,
                error_message=error_msg,
            )
            return paper_order

        # ── Live mode ────────────────────────────────────────────────────────
        # Real broker is authoritative; PaperBroker updates the platform ledger too.
        real_broker = _build_real_broker(account)
        order.broker = real_broker.broker_name
        order = await real_broker.submit_order(order)
        order.db_id = _persist_order(order)

        if order.status in (OrderStatus.FILLED, OrderStatus.SUBMITTED):
            # Mirror to paper ledger so UI is consistent
            paper = PaperBroker()
            mirror = Order(
                agent_id=agent_id,
                symbol=order.symbol,
                market=order.market,
                side=order.side,
                quantity=order.quantity,
                price=order.price,
                execution_mode=ExecutionMode.LIVE,
                broker="paper",
                signal_id=order.signal_id,
                leader_id=order.leader_id,
                token_id=order.token_id,
                outcome=order.outcome,
                created_at=order.created_at,
            )
            try:
                await paper.submit_order(mirror, cursor=cursor)
            except Exception:  # noqa: BLE001
                _logger.exception("[live] paper mirror failed for agent %s", agent_id)

        return order


# Module-level singleton — import and reuse everywhere.
execution_router = ExecutionRouter()
