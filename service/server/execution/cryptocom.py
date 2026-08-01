"""
execution/cryptocom.py — CryptocomBroker (Crypto.com Exchange v1, spot).

UAT sandbox: https://uat-api.3ona.co/exchange/v1   (Plan 19 shadow strategy A)
Live:        https://api.crypto.com/exchange/v1

The API is JSON-RPC-shaped: POST {base}/{method} with a signed envelope.
    sig = hex(HMAC-SHA256(method + id + api_key + params_str + nonce))
where params_str concatenates sorted param keys and values. All param values
are sent as strings so the signed string and the JSON body can never disagree
on number formatting.

Venue quirk this adapter owns: a MARKET BUY takes `notional` (quote amount),
a MARKET SELL takes `quantity` (base amount) — same asymmetry as Upbit. Buys
convert quantity → notional at the decision price; the reconciler reads back
cumulative_quantity for what actually filled.

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

_UAT_BASE  = os.getenv("CRYPTOCOM_UAT_BASE_URL", "https://uat-api.3ona.co/exchange/v1").rstrip("/")
_LIVE_BASE = os.getenv("CRYPTOCOM_LIVE_BASE_URL", "https://api.crypto.com/exchange/v1").rstrip("/")

_SIDE_MAP = {
    "buy":   "BUY",
    "sell":  "SELL",
    "short": "SELL",
    "cover": "BUY",
}

_STATUS_MAP = {
    "FILLED": OrderStatus.FILLED,
    "NEW": OrderStatus.SUBMITTED,
    "PENDING": OrderStatus.SUBMITTED,
    "ACTIVE": OrderStatus.SUBMITTED,
    "PARTIALLY_FILLED": OrderStatus.PARTIAL_FILL,
    "CANCELED": OrderStatus.CANCELLED,
    "EXPIRED": OrderStatus.CANCELLED,
    "REJECTED": OrderStatus.REJECTED,
}


class CryptocomBroker(Broker):
    """Submits spot market orders to Crypto.com Exchange.

    Args:
        key/secret: Crypto.com Exchange API credentials.
        sandbox:    True = UAT environment; False = live.
    """

    def __init__(self, key: str, secret: str, sandbox: bool = True):
        self._key = key
        self._secret = secret
        self._base = _UAT_BASE if sandbox else _LIVE_BASE

    @property
    def broker_name(self) -> str:
        return "cryptocom"

    def _has_credentials(self) -> bool:
        return bool(self._key and self._secret)

    def _envelope(self, method: str, params: dict) -> dict:
        req_id = int(time.time() * 1000)
        nonce = req_id
        params_str = "".join(f"{k}{params[k]}" for k in sorted(params))
        payload = f"{method}{req_id}{self._key}{params_str}{nonce}"
        sig = hmac.new(self._secret.encode(), payload.encode(),
                       hashlib.sha256).hexdigest()
        return {"id": req_id, "method": method, "api_key": self._key,
                "params": params, "nonce": nonce, "sig": sig}

    async def _call(self, method: str, params: dict) -> dict | None:
        body = self._envelope(method, params)
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{self._base}/{method}",
                    content=json.dumps(body, separators=(",", ":")),
                    headers={"Content-Type": "application/json"},
                )
        except httpx.RequestError as exc:
            return {"code": -1, "message": f"network error: {exc}"}
        try:
            data = resp.json()
            return data if isinstance(data, dict) else None
        except Exception:  # noqa: BLE001
            return None

    @staticmethod
    def _instrument(symbol: str) -> str:
        base, quote = split_symbol(symbol)
        return f"{base}_{quote}"

    async def submit_order(self, order: Order, cursor=None) -> Order:
        if not self._has_credentials():
            order.status = OrderStatus.REJECTED
            order.error_message = "cryptocom API key/secret not configured"
            return order

        is_buy = order.side in ("buy", "cover")
        params: dict = {
            "instrument_name": self._instrument(order.symbol),
            "side": _SIDE_MAP.get(order.side, "BUY"),
            "type": "MARKET",
        }
        if is_buy:
            # MARKET BUY is sized in quote notional on this venue.
            params["notional"] = f"{order.quantity * order.price:.2f}"
        else:
            params["quantity"] = f"{order.quantity:.8f}"

        data = await self._call("private/create-order", params)
        if data is None:
            order.status = OrderStatus.REJECTED
            order.error_message = "malformed response from venue"
            return order
        if data.get("code") == 0:
            result = data.get("result") or {}
            order.broker_order_id = str(result.get("order_id", "")) or None
            order.status = OrderStatus.SUBMITTED if order.broker_order_id else OrderStatus.REJECTED
            if order.status is OrderStatus.REJECTED:
                order.error_message = "venue returned no order id"
            else:
                _logger.info("[CryptocomBroker] submitted %s %s x%s for agent %s → %s",
                             order.side, order.symbol, order.quantity,
                             order.agent_id, order.broker_order_id)
        else:
            order.status = OrderStatus.REJECTED
            order.error_message = str(data.get("message") or data.get("code"))
            _logger.warning("[CryptocomBroker] rejected %s %s for agent %s: %s",
                            order.side, order.symbol, order.agent_id,
                            order.error_message)
        return order

    async def get_order_status(self, broker_order_id: str, symbol: str = ""):
        if not self._has_credentials() or not broker_order_id:
            return None
        data = await self._call("private/get-order-detail",
                                {"order_id": broker_order_id})
        if not data or data.get("code") != 0:
            return None
        row = data.get("result") or {}
        status = _STATUS_MAP.get(str(row.get("status", "")).upper(),
                                 OrderStatus.SUBMITTED)
        return {
            "status": status,
            "filled_qty": _to_float(row.get("cumulative_quantity")),
            "avg_price": _to_float(row.get("avg_price")),
        }

    async def cancel_order(self, broker_order_id: str) -> bool:
        if not self._has_credentials() or not broker_order_id:
            return False
        data = await self._call("private/cancel-order",
                                {"order_id": broker_order_id})
        return bool(data and data.get("code") == 0)

    async def get_broker_positions(self) -> list[dict]:
        if not self._has_credentials():
            return []
        data = await self._call("private/user-balance", {})
        if not data or data.get("code") != 0:
            return []
        positions = []
        for acct in (data.get("result") or {}).get("data") or []:
            for bal in acct.get("position_balances") or []:
                total = _to_float(bal.get("quantity")) or 0.0
                if total > 0:
                    positions.append({"symbol": bal.get("instrument_name", ""),
                                      "qty": total, "side": "long"})
        return positions


def _to_float(value):
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
