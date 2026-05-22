"""
execution/alpaca.py — AlpacaBroker.

Wires AITRAD signals to the Alpaca REST API (v2).

Paper sandbox:  https://paper-api.alpaca.markets/v2/orders
Live:           https://api.alpaca.markets/v2/orders

Auth: APCA-API-KEY-ID and APCA-API-SECRET-KEY request headers.

Set environment variables:
    ALPACA_KEY          — API key ID
    ALPACA_SECRET       — API secret key
    ALPACA_PAPER=true   — use paper sandbox (default: true)

Without credentials the broker is instantiated but every submit_order call
returns OrderStatus.REJECTED with a clear error message — safe to use in dev.
"""
from __future__ import annotations

import logging
from typing import Optional

import httpx

from execution.base import Broker, Order, OrderStatus

_logger = logging.getLogger(__name__)

_PAPER_BASE = "https://paper-api.alpaca.markets/v2"
_LIVE_BASE  = "https://api.alpaca.markets/v2"

# Map AITRAD sides to Alpaca order sides.
_SIDE_MAP = {
    "buy":   ("buy",  "long"),
    "sell":  ("sell", "long"),
    "short": ("sell", "short"),
    "cover": ("buy",  "short"),
}


class AlpacaBroker(Broker):
    """
    AlpacaBroker submits market orders to the Alpaca REST API.

    Args:
        key:    Alpaca API key ID.
        secret: Alpaca API secret.
        paper:  True = paper-trading endpoint; False = live endpoint.
    """

    def __init__(self, key: str, secret: str, paper: bool = True):
        self._key    = key
        self._secret = secret
        self._base   = _PAPER_BASE if paper else _LIVE_BASE
        self._paper  = paper

    @property
    def broker_name(self) -> str:
        return "alpaca"

    @property
    def _headers(self) -> dict:
        return {
            "APCA-API-KEY-ID":     self._key,
            "APCA-API-SECRET-KEY": self._secret,
            "Content-Type":        "application/json",
        }

    def _has_credentials(self) -> bool:
        return bool(self._key and self._secret)

    async def submit_order(self, order: Order, cursor=None) -> Order:
        if not self._has_credentials():
            order.status = OrderStatus.REJECTED
            order.error_message = "ALPACA_KEY / ALPACA_SECRET not configured"
            return order

        alpaca_side, position_intent = _SIDE_MAP.get(order.side, ("buy", "long"))

        payload: dict = {
            "symbol":        order.symbol.upper(),
            "qty":           str(order.quantity),
            "side":          alpaca_side,
            "type":          "market",
            "time_in_force": "day",
        }
        if order.side in ("short", "cover"):
            payload["position_intent"] = position_intent

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{self._base}/orders",
                    headers=self._headers,
                    json=payload,
                )
        except httpx.RequestError as exc:
            order.status = OrderStatus.REJECTED
            order.error_message = f"network error: {exc}"
            _logger.warning("[AlpacaBroker] network error for agent %s: %s", order.agent_id, exc)
            return order

        if resp.status_code in (200, 201):
            data = resp.json()
            order.broker_order_id = data.get("id")
            # Alpaca market orders are usually filled near-instantly on paper;
            # we mark them SUBMITTED and the reconciler will confirm fill.
            alpaca_status = data.get("status", "")
            order.status = OrderStatus.FILLED if alpaca_status in ("filled", "partially_filled") else OrderStatus.SUBMITTED
            _logger.info(
                "[AlpacaBroker] submitted %s %s x%s for agent %s → %s",
                order.side, order.symbol, order.quantity, order.agent_id, order.broker_order_id,
            )
        else:
            order.status = OrderStatus.REJECTED
            try:
                body = resp.json()
                order.error_message = body.get("message") or resp.text
            except Exception:  # noqa: BLE001
                order.error_message = resp.text
            _logger.warning(
                "[AlpacaBroker] rejected %s %s for agent %s: %s",
                order.side, order.symbol, order.agent_id, order.error_message,
            )

        return order

    async def cancel_order(self, broker_order_id: str) -> bool:
        if not self._has_credentials():
            return False
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.delete(
                    f"{self._base}/orders/{broker_order_id}",
                    headers=self._headers,
                )
            return resp.status_code in (200, 204)
        except httpx.RequestError:
            return False

    async def get_broker_positions(self) -> list[dict]:
        if not self._has_credentials():
            return []
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{self._base}/positions",
                    headers=self._headers,
                )
            if resp.status_code != 200:
                return []
            positions = []
            for p in resp.json():
                qty = float(p.get("qty", 0))
                positions.append({
                    "symbol": p["symbol"],
                    "qty":    abs(qty),
                    "side":   "long" if qty >= 0 else "short",
                })
            return positions
        except Exception:  # noqa: BLE001
            _logger.exception("[AlpacaBroker] get_broker_positions failed")
            return []
