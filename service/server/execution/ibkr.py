"""
execution/ibkr.py — IBKRBroker stub.

Interactive Brokers requires the TWS Gateway to be running on a local or
remote host.  This stub satisfies the Broker ABC and returns REJECTED until
a full implementation is provided.

To implement: use the `ib_insync` library against the IB Gateway REST or
socket API.  Set:
    IBKR_GATEWAY_HOST  (default: localhost)
    IBKR_GATEWAY_PORT  (default: 4001)

This is a Phase 2 stretch target — ship Alpaca + Binance first.
"""
from __future__ import annotations

import logging

from execution.base import Broker, Order, OrderStatus

_logger = logging.getLogger(__name__)


class IBKRBroker(Broker):
    """IBKR Gateway stub — not yet implemented."""

    def __init__(self, host: str = "localhost", port: int = 4001):
        self._host = host
        self._port = port

    @property
    def broker_name(self) -> str:
        return "ibkr"

    async def submit_order(self, order: Order, cursor=None) -> Order:
        order.status = OrderStatus.REJECTED
        order.error_message = (
            "IBKRBroker is not yet implemented. "
            "Run TWS Gateway and implement ib_insync integration."
        )
        _logger.warning(
            "[IBKRBroker] submit_order called but broker not implemented for agent %s",
            order.agent_id,
        )
        return order

    async def cancel_order(self, broker_order_id: str) -> bool:
        return False

    async def get_broker_positions(self) -> list[dict]:
        return []
