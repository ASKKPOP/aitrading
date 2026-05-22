"""
execution/binance.py — BinanceBroker (spot only).

Testnet:  https://testnet.binance.vision/api/v3
Live:     https://api.binance.com/api/v3

Auth: X-MBX-APIKEY header + HMAC-SHA256 query-string signature.

Set environment variables:
    BINANCE_KEY         — API key
    BINANCE_SECRET      — API secret
    BINANCE_TESTNET=true — use testnet (default: true)

Without credentials every submit_order returns OrderStatus.REJECTED.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import time
from urllib.parse import urlencode

import httpx

from execution.base import Broker, Order, OrderStatus

_logger = logging.getLogger(__name__)

_TESTNET_BASE = "https://testnet.binance.vision/api/v3"
_LIVE_BASE    = "https://api.binance.com/api/v3"

_SIDE_MAP = {
    "buy":   "BUY",
    "sell":  "SELL",
    "short": "SELL",
    "cover": "BUY",
}


class BinanceBroker(Broker):
    """
    BinanceBroker submits market orders to Binance spot REST API.

    Args:
        key:     Binance API key.
        secret:  Binance API secret.
        testnet: True = testnet endpoint; False = live endpoint.
    """

    def __init__(self, key: str, secret: str, testnet: bool = True):
        self._key     = key
        self._secret  = secret
        self._base    = _TESTNET_BASE if testnet else _LIVE_BASE
        self._testnet = testnet

    @property
    def broker_name(self) -> str:
        return "binance"

    def _has_credentials(self) -> bool:
        return bool(self._key and self._secret)

    def _sign(self, params: dict) -> dict:
        params["timestamp"] = int(time.time() * 1000)
        query = urlencode(params)
        sig = hmac.new(
            self._secret.encode(),
            query.encode(),
            hashlib.sha256,
        ).hexdigest()
        params["signature"] = sig
        return params

    async def submit_order(self, order: Order, cursor=None) -> Order:
        if not self._has_credentials():
            order.status = OrderStatus.REJECTED
            order.error_message = "BINANCE_KEY / BINANCE_SECRET not configured"
            return order

        binance_side = _SIDE_MAP.get(order.side, "BUY")
        # Binance symbols: BTCUSDT (no separator).  If user passes BTC/USDT, normalise.
        symbol = order.symbol.upper().replace("/", "").replace("-", "")

        params = self._sign({
            "symbol":   symbol,
            "side":     binance_side,
            "type":     "MARKET",
            "quantity": f"{order.quantity:.8f}",
        })

        headers = {"X-MBX-APIKEY": self._key}

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{self._base}/order",
                    headers=headers,
                    params=params,
                )
        except httpx.RequestError as exc:
            order.status = OrderStatus.REJECTED
            order.error_message = f"network error: {exc}"
            return order

        if resp.status_code == 200:
            data = resp.json()
            order.broker_order_id = str(data.get("orderId", ""))
            binance_status = data.get("status", "")
            order.status = OrderStatus.FILLED if binance_status == "FILLED" else OrderStatus.SUBMITTED
            if binance_status == "FILLED":
                order.filled_qty = float(data.get("executedQty", order.quantity))
            _logger.info(
                "[BinanceBroker] submitted %s %s x%s for agent %s → %s",
                order.side, symbol, order.quantity, order.agent_id, order.broker_order_id,
            )
        else:
            order.status = OrderStatus.REJECTED
            try:
                body = resp.json()
                order.error_message = body.get("msg") or resp.text
            except Exception:  # noqa: BLE001
                order.error_message = resp.text
            _logger.warning(
                "[BinanceBroker] rejected %s %s for agent %s: %s",
                order.side, symbol, order.agent_id, order.error_message,
            )

        return order

    async def cancel_order(self, broker_order_id: str) -> bool:
        if not self._has_credentials():
            return False
        # We need symbol to cancel on Binance — limitation of the simple interface.
        # For now return False; production use should pass symbol via metadata.
        _logger.warning(
            "[BinanceBroker] cancel_order called without symbol context — skipping"
        )
        return False

    async def get_broker_positions(self) -> list[dict]:
        if not self._has_credentials():
            return []
        params = self._sign({})
        headers = {"X-MBX-APIKEY": self._key}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{self._base}/account",
                    headers=headers,
                    params=params,
                )
            if resp.status_code != 200:
                return []
            balances = resp.json().get("balances", [])
            # Return non-zero balances as synthetic "positions"
            positions = []
            for b in balances:
                free = float(b.get("free", 0))
                locked = float(b.get("locked", 0))
                total = free + locked
                if total > 0:
                    positions.append({
                        "symbol": b["asset"],
                        "qty":    total,
                        "side":   "long",
                    })
            return positions
        except Exception:  # noqa: BLE001
            _logger.exception("[BinanceBroker] get_broker_positions failed")
            return []
