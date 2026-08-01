"""
execution/kucoin.py — KucoinBroker (spot).

KuCoin discontinued its public sandbox; the non-live construction uses the
venue's own order dry-run endpoint (/api/v1/orders/test) against the LIVE
host (Plan 19 shadow strategy B): auth, symbol and size are checked, nothing
can fill, and the answer is VALIDATED or REJECTED.

Auth (key version 2): KC-API-KEY / KC-API-TIMESTAMP(ms) / KC-API-KEY-VERSION
headers plus
    KC-API-SIGN       = base64(HMAC-SHA256(timestamp + METHOD + path + body))
    KC-API-PASSPHRASE = base64(HMAC-SHA256(passphrase))   — encrypted, v2 keys

Without credentials every submit_order returns OrderStatus.REJECTED.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import time
import uuid

import httpx

from execution.base import Broker, Order, OrderStatus, split_symbol

_logger = logging.getLogger(__name__)

_BASE = os.getenv("KUCOIN_BASE_URL", "https://api.kucoin.com").rstrip("/")

_SIDE_MAP = {
    "buy":   "buy",
    "sell":  "sell",
    "short": "sell",
    "cover": "buy",
}


class KucoinBroker(Broker):
    """Submits spot market orders to KuCoin.

    Args:
        key/secret/passphrase: KuCoin API credentials (v2 keys).
        test_only: True = /orders/test dry-run (shadow); False = real orders.
    """

    def __init__(self, key: str, secret: str, passphrase: str, test_only: bool = True):
        self._key = key
        self._secret = secret
        self._passphrase = passphrase
        self._test_only = test_only

    @property
    def broker_name(self) -> str:
        return "kucoin"

    def _has_credentials(self) -> bool:
        return bool(self._key and self._secret and self._passphrase)

    def _headers(self, method: str, path: str, body: str = "") -> dict:
        ts = str(int(time.time() * 1000))
        sign = base64.b64encode(hmac.new(
            self._secret.encode(), (ts + method.upper() + path + body).encode(),
            hashlib.sha256).digest()).decode()
        # v2 keys transmit the passphrase HMAC'd with the secret, never raw.
        passphrase = base64.b64encode(hmac.new(
            self._secret.encode(), self._passphrase.encode(),
            hashlib.sha256).digest()).decode()
        return {
            "KC-API-KEY": self._key,
            "KC-API-SIGN": sign,
            "KC-API-TIMESTAMP": ts,
            "KC-API-PASSPHRASE": passphrase,
            "KC-API-KEY-VERSION": "2",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _pair(symbol: str) -> str:
        base, quote = split_symbol(symbol)
        return f"{base}-{quote}"

    async def submit_order(self, order: Order, cursor=None) -> Order:
        if not self._has_credentials():
            order.status = OrderStatus.REJECTED
            order.error_message = "kucoin API key/secret/passphrase not configured"
            return order

        path = "/api/v1/orders/test" if self._test_only else "/api/v1/orders"
        body = json.dumps({
            "clientOid": uuid.uuid4().hex,
            "side": _SIDE_MAP.get(order.side, "buy"),
            "symbol": self._pair(order.symbol),
            "type": "market",
            "size": f"{order.quantity:.8f}",
        }, separators=(",", ":"))

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(f"{_BASE}{path}",
                                         headers=self._headers("POST", path, body),
                                         content=body)
        except httpx.RequestError as exc:
            order.status = OrderStatus.REJECTED
            order.error_message = f"network error: {exc}"
            return order

        data = _safe_json(resp)
        ok = resp.status_code == 200 and str(data.get("code", "")) == "200000"
        if ok and self._test_only:
            # Dry-run accepted — the venue validated without placing anything.
            order.status = OrderStatus.VALIDATED
            _logger.info("[KucoinBroker] validated %s %s x%s for agent %s",
                         order.side, order.symbol, order.quantity, order.agent_id)
        elif ok:
            order.broker_order_id = str((data.get("data") or {}).get("orderId", ""))
            order.status = OrderStatus.SUBMITTED if order.broker_order_id else OrderStatus.REJECTED
            if order.status is OrderStatus.REJECTED:
                order.error_message = "venue returned no order id"
            else:
                _logger.info("[KucoinBroker] submitted %s %s x%s for agent %s → %s",
                             order.side, order.symbol, order.quantity,
                             order.agent_id, order.broker_order_id)
        else:
            order.status = OrderStatus.REJECTED
            order.error_message = str(data.get("msg") or resp.text)
            _logger.warning("[KucoinBroker] rejected %s %s for agent %s: %s",
                            order.side, order.symbol, order.agent_id,
                            order.error_message)
        return order

    async def get_order_status(self, broker_order_id: str, symbol: str = ""):
        if not self._has_credentials() or not broker_order_id:
            return None
        path = f"/api/v1/orders/{broker_order_id}"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{_BASE}{path}",
                                        headers=self._headers("GET", path))
        except httpx.RequestError as exc:
            _logger.debug("[KucoinBroker] status lookup failed for %s: %s",
                          broker_order_id, exc)
            return None
        data = _safe_json(resp)
        row = data.get("data") or {}
        if resp.status_code != 200 or str(data.get("code", "")) != "200000" or not row:
            return None
        deal_size = _to_float(row.get("dealSize")) or 0.0
        deal_funds = _to_float(row.get("dealFunds")) or 0.0
        if row.get("isActive"):
            status = OrderStatus.PARTIAL_FILL if deal_size > 0 else OrderStatus.SUBMITTED
        elif deal_size > 0:
            # Done with executions — FILLED at the venue-confirmed size; the
            # reconciler's mismatch alert covers a shortfall vs requested.
            status = OrderStatus.FILLED
        elif row.get("cancelExist"):
            status = OrderStatus.CANCELLED
        else:
            status = OrderStatus.REJECTED
        return {
            "status": status,
            "filled_qty": deal_size if deal_size > 0 else None,
            "avg_price": (deal_funds / deal_size) if deal_size > 0 else None,
        }

    async def cancel_order(self, broker_order_id: str) -> bool:
        if not self._has_credentials() or not broker_order_id:
            return False
        path = f"/api/v1/orders/{broker_order_id}"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.delete(f"{_BASE}{path}",
                                           headers=self._headers("DELETE", path))
            data = _safe_json(resp)
            return resp.status_code == 200 and str(data.get("code", "")) == "200000"
        except Exception:  # noqa: BLE001
            return False

    async def get_broker_positions(self) -> list[dict]:
        if not self._has_credentials():
            return []
        path = "/api/v1/accounts?type=trade"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{_BASE}{path}",
                                        headers=self._headers("GET", path))
            data = _safe_json(resp)
            if resp.status_code != 200 or str(data.get("code", "")) != "200000":
                return []
            positions = []
            for row in data.get("data") or []:
                total = _to_float(row.get("balance")) or 0.0
                if total > 0:
                    positions.append({"symbol": row.get("currency", ""),
                                      "qty": total, "side": "long"})
            return positions
        except Exception:  # noqa: BLE001
            _logger.exception("[KucoinBroker] get_broker_positions failed")
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
