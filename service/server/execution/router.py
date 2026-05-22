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

import asyncio
import logging
from typing import Optional

from execution.base import Broker, ExecutionMode, Order, OrderStatus

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# DB helpers (keep imports local to avoid circular deps)
# ---------------------------------------------------------------------------

def _get_active_broker_account(agent_id: int) -> Optional[dict]:
    from database import get_db_connection
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """SELECT * FROM broker_accounts
           WHERE agent_id = ? AND is_active = 1
           ORDER BY updated_at DESC LIMIT 1""",
        (agent_id,),
    )
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


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
            signal_id, leader_id, token_id, outcome, created_at, filled_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            order.agent_id, order.symbol, order.market, order.side,
            order.quantity, order.price, order.status.value,
            order.execution_mode.value, order.broker,
            order.broker_order_id, order.error_message,
            order.signal_id, order.leader_id, order.token_id, order.outcome,
            order.created_at or utc_now_iso_z(),
            order.filled_at,
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
        from execution.ibkr import IBKRBroker
        return IBKRBroker()

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

        account = _get_active_broker_account(agent_id)
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
