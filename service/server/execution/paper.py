"""
execution/paper.py — PaperBroker.

Wraps _update_position_from_signal from services.py.  All logic stays in
services; this adapter gives it the Broker ABC interface so the rest of the
execution layer can treat paper and real brokers identically.

Orders are fulfilled immediately (synchronous simulation).  A real broker
returns SUBMITTED and waits for a fill event; PaperBroker returns FILLED
at once, which is the existing behaviour.
"""
from __future__ import annotations

import logging
from typing import Optional

from execution.base import Broker, ExecutionMode, Order, OrderStatus

_logger = logging.getLogger(__name__)


class PaperBroker(Broker):
    """Simulated broker — no external API calls, immediate fills."""

    @property
    def broker_name(self) -> str:
        return "paper"

    async def submit_order(self, order: Order, cursor=None) -> Order:
        """
        Delegate to _update_position_from_signal.  The cursor argument is
        forwarded so the caller's transaction stays open (same behaviour as
        before).
        """
        # Import here to avoid circular dependency at module load.
        from services import _update_position_from_signal
        from routes_shared import utc_now_iso_z

        try:
            _update_position_from_signal(
                agent_id=order.agent_id,
                symbol=order.symbol,
                market=order.market,
                action=order.side,
                quantity=order.quantity,
                price=order.price,
                executed_at=order.created_at or utc_now_iso_z(),
                leader_id=order.leader_id,
                cursor=cursor,
                token_id=order.token_id,
                outcome=order.outcome,
            )
            order.status = OrderStatus.FILLED
            order.filled_qty = order.quantity
            order.broker_order_id = f"paper-{order.agent_id}-{order.symbol}"
            _logger.info(
                "[PaperBroker] filled %s %s x%s @ %s for agent %s",
                order.side, order.symbol, order.quantity, order.price, order.agent_id,
            )
        except ValueError as exc:
            order.status = OrderStatus.REJECTED
            order.error_message = str(exc)
            _logger.warning(
                "[PaperBroker] rejected %s %s: %s",
                order.side, order.symbol, exc,
            )
        except Exception as exc:  # noqa: BLE001
            order.status = OrderStatus.REJECTED
            order.error_message = f"unexpected: {exc}"
            _logger.exception("[PaperBroker] unexpected error for agent %s", order.agent_id)

        return order

    async def cancel_order(self, broker_order_id: str) -> bool:
        # Paper orders are immediately filled — nothing to cancel.
        return False

    async def get_broker_positions(self) -> list[dict]:
        # Paper positions live in the DB; the reconciler reads them directly.
        return []
