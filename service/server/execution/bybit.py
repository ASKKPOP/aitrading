"""
execution/bybit.py — BybitBroker (spot, v5 unified API).

Demo:  https://api-demo.bybit.com   (demo trading environment — real API,
                                     demo funds; Plan 19 shadow strategy A)
Live:  https://api.bybit.com

Auth: X-BAPI-API-KEY / X-BAPI-TIMESTAMP / X-BAPI-RECV-WINDOW headers plus
X-BAPI-SIGN = hex(HMAC-SHA256(timestamp + api_key + recv_window + payload))
where payload is the JSON body (POST) or the query string (GET).

Without credentials every submit_order returns OrderStatus.REJECTED.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time

import httpx

from execution.base import Broker, Order, OrderStatus, split_symbol

_logger = logging.getLogger(__name__)

_DEMO_BASE = os.getenv("BYBIT_DEMO_BASE_URL", "https://api-demo.bybit.com").rstrip("/")
_LIVE_BASE = os.getenv("BYBIT_LIVE_BASE_URL", "https://api.bybit.com").rstrip("/")

_RECV_WINDOW = "5000"

_SIDE_MAP = {
    "buy":   "Buy",
    "sell":  "Sell",
    "short": "Sell",
    "cover": "Buy",
}

# Bybit v5 orderStatus → our lifecycle. New/PartiallyFilled stay pollable.
_STATUS_MAP = {
    "FILLED": OrderStatus.FILLED,
    "PARTIALLYFILLED": OrderStatus.PARTIAL_FILL,
    "NEW": OrderStatus.SUBMITTED,
    "CREATED": OrderStatus.SUBMITTED,
    "CANCELLED": OrderStatus.CANCELLED,
    "PARTIALLYFILLEDCANCELED": OrderStatus.CANCELLED,
    "DEACTIVATED": OrderStatus.CANCELLED,
    "REJECTED": OrderStatus.REJECTED,
}


class BybitBroker(Broker):
    """Submits spot market orders to Bybit's v5 API.

    Args:
        key/secret: Bybit API credentials.
        sandbox:    True = demo-trading environment; False = live.
    """

    def __init__(self, key: str, secret: str, sandbox: bool = True):
        self._key = key
        self._secret = secret
        self._base = _DEMO_BASE if sandbox else _LIVE_BASE

    @property
    def broker_name(self) -> str:
        return "bybit"

    def _has_credentials(self) -> bool:
        return bool(self._key and self._secret)

    def _headers(self, payload: str) -> dict:
        ts = str(int(time.time() * 1000))
        sig = hmac.new(
            self._secret.encode(),
            (ts + self._key + _RECV_WINDOW + payload).encode(),
            hashlib.sha256,
        ).hexdigest()
        return {
            "X-BAPI-API-KEY": self._key,
            "X-BAPI-TIMESTAMP": ts,
            "X-BAPI-RECV-WINDOW": _RECV_WINDOW,
            "X-BAPI-SIGN": sig,
            "Content-Type": "application/json",
        }

    @staticmethod
    def _pair(symbol: str) -> str:
        base, quote = split_symbol(symbol)
        return f"{base}{quote}"

    async def submit_order(self, order: Order, cursor=None) -> Order:
        if not self._has_credentials():
            order.status = OrderStatus.REJECTED
            order.error_message = "bybit API key/secret not configured"
            return order

        body = json.dumps({
            "category": "spot",
            "symbol": self._pair(order.symbol),
            "side": _SIDE_MAP.get(order.side, "Buy"),
            "orderType": "Market",
            # Without marketUnit, a spot market BUY's qty means QUOTE currency
            # and the venue would spend `quantity` USDT instead of buying
            # `quantity` coins — the platform sizes in base units, so pin it.
            "marketUnit": "baseCoin",
            "qty": f"{order.quantity:.8f}",
        }, separators=(",", ":"))

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{self._base}/v5/order/create",
                    headers=self._headers(body),
                    content=body,
                )
        except httpx.RequestError as exc:
            order.status = OrderStatus.REJECTED
            order.error_message = f"network error: {exc}"
            return order

        data = _safe_json(resp)
        if resp.status_code == 200 and data.get("retCode") == 0:
            order.broker_order_id = str((data.get("result") or {}).get("orderId", ""))
            # v5 create returns no fill state — the reconciler settles it.
            order.status = OrderStatus.SUBMITTED
            _logger.info("[BybitBroker] submitted %s %s x%s for agent %s → %s",
                         order.side, order.symbol, order.quantity,
                         order.agent_id, order.broker_order_id)
        else:
            order.status = OrderStatus.REJECTED
            order.error_message = str(data.get("retMsg") or resp.text)
            _logger.warning("[BybitBroker] rejected %s %s for agent %s: %s",
                            order.side, order.symbol, order.agent_id,
                            order.error_message)
        return order

    async def get_order_status(self, broker_order_id: str, symbol: str = ""):
        if not self._has_credentials() or not broker_order_id:
            return None
        # Recent orders live under realtime; older ones move to history.
        for endpoint in ("/v5/order/realtime", "/v5/order/history"):
            query = f"category=spot&orderId={broker_order_id}"
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.get(
                        f"{self._base}{endpoint}?{query}",
                        headers=self._headers(query),
                    )
            except httpx.RequestError as exc:
                _logger.debug("[BybitBroker] status lookup failed for %s: %s",
                              broker_order_id, exc)
                return None
            data = _safe_json(resp)
            rows = ((data.get("result") or {}).get("list")) or []
            if resp.status_code == 200 and data.get("retCode") == 0 and rows:
                row = rows[0]
                status = _STATUS_MAP.get(
                    str(row.get("orderStatus", "")).upper(), OrderStatus.SUBMITTED)
                filled = _to_float(row.get("cumExecQty"))
                return {
                    "status": status,
                    "filled_qty": filled,
                    "avg_price": _to_float(row.get("avgPrice")),
                }
        return None

    async def cancel_order(self, broker_order_id: str) -> bool:
        # Bybit cancel requires the symbol alongside the order id — same
        # interface limitation as Binance; the reconciler treats it as
        # "cannot cancel" rather than guessing a pair.
        _logger.warning("[BybitBroker] cancel_order called without symbol context — skipping")
        return False

    async def get_broker_positions(self) -> list[dict]:
        if not self._has_credentials():
            return []
        query = "accountType=UNIFIED"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{self._base}/v5/account/wallet-balance?{query}",
                    headers=self._headers(query),
                )
            data = _safe_json(resp)
            if resp.status_code != 200 or data.get("retCode") != 0:
                return []
            positions = []
            for acct in (data.get("result") or {}).get("list") or []:
                for coin in acct.get("coin") or []:
                    total = _to_float(coin.get("walletBalance")) or 0.0
                    if total > 0:
                        positions.append({"symbol": coin.get("coin", ""),
                                          "qty": total, "side": "long"})
            return positions
        except Exception:  # noqa: BLE001
            _logger.exception("[BybitBroker] get_broker_positions failed")
            return []


def _safe_json(resp) -> dict:
    try:
        data = resp.json()
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _to_float(value):
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
