"""
execution/okx.py — OKXBroker (spot, v5 API).

One host for both environments (https://www.okx.com); demo trading is
selected per-request with the `x-simulated-trading: 1` header against a
demo-trading API key (Plan 19 shadow strategy A).

Auth headers: OK-ACCESS-KEY, OK-ACCESS-PASSPHRASE, OK-ACCESS-TIMESTAMP
(ISO-8601 millis, e.g. 2026-07-31T12:00:00.000Z) and
OK-ACCESS-SIGN = base64(HMAC-SHA256(timestamp + method + requestPath + body)).

Without credentials every submit_order returns OrderStatus.REJECTED.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
from datetime import datetime, timezone

import httpx

from execution.base import Broker, Order, OrderStatus, split_symbol

_logger = logging.getLogger(__name__)

_BASE = os.getenv("OKX_BASE_URL", "https://www.okx.com").rstrip("/")

_SIDE_MAP = {
    "buy":   "buy",
    "sell":  "sell",
    "short": "sell",
    "cover": "buy",
}

_STATE_MAP = {
    "filled": OrderStatus.FILLED,
    "partially_filled": OrderStatus.PARTIAL_FILL,
    "live": OrderStatus.SUBMITTED,
    "canceled": OrderStatus.CANCELLED,
    "mmp_canceled": OrderStatus.CANCELLED,
}


class OKXBroker(Broker):
    """Submits spot market orders to OKX's v5 API.

    Args:
        key/secret/passphrase: OKX API credentials (passphrase is set by the
            user at key creation and is part of every request signature).
        sandbox: True = demo trading (x-simulated-trading header); False = live.
    """

    def __init__(self, key: str, secret: str, passphrase: str, sandbox: bool = True):
        self._key = key
        self._secret = secret
        self._passphrase = passphrase
        self._sandbox = sandbox

    @property
    def broker_name(self) -> str:
        return "okx"

    def _has_credentials(self) -> bool:
        return bool(self._key and self._secret and self._passphrase)

    def _headers(self, method: str, path: str, body: str = "") -> dict:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        sig = base64.b64encode(hmac.new(
            self._secret.encode(),
            (ts + method.upper() + path + body).encode(),
            hashlib.sha256,
        ).digest()).decode()
        headers = {
            "OK-ACCESS-KEY": self._key,
            "OK-ACCESS-SIGN": sig,
            "OK-ACCESS-TIMESTAMP": ts,
            "OK-ACCESS-PASSPHRASE": self._passphrase,
            "Content-Type": "application/json",
        }
        if self._sandbox:
            headers["x-simulated-trading"] = "1"
        return headers

    @staticmethod
    def _inst_id(symbol: str) -> str:
        base, quote = split_symbol(symbol)
        return f"{base}-{quote}"

    async def submit_order(self, order: Order, cursor=None) -> Order:
        if not self._has_credentials():
            order.status = OrderStatus.REJECTED
            order.error_message = "okx API key/secret/passphrase not configured"
            return order

        path = "/api/v5/trade/order"
        body = json.dumps({
            "instId": self._inst_id(order.symbol),
            "tdMode": "cash",
            "side": _SIDE_MAP.get(order.side, "buy"),
            "ordType": "market",
            # A market BUY's sz defaults to QUOTE currency on OKX; the platform
            # sizes in base units, so pin the target currency explicitly.
            "tgtCcy": "base_ccy",
            "sz": f"{order.quantity:.8f}",
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
        rows = data.get("data") or []
        row = rows[0] if rows else {}
        if resp.status_code == 200 and data.get("code") == "0" \
                and str(row.get("sCode", "0")) == "0":
            order.broker_order_id = str(row.get("ordId", ""))
            order.status = OrderStatus.SUBMITTED
            _logger.info("[OKXBroker] submitted %s %s x%s for agent %s → %s",
                         order.side, order.symbol, order.quantity,
                         order.agent_id, order.broker_order_id)
        else:
            order.status = OrderStatus.REJECTED
            order.error_message = str(
                row.get("sMsg") or data.get("msg") or resp.text)
            _logger.warning("[OKXBroker] rejected %s %s for agent %s: %s",
                            order.side, order.symbol, order.agent_id,
                            order.error_message)
        return order

    async def get_order_status(self, broker_order_id: str, symbol: str = ""):
        """OKX keys order lookup by (instId, ordId) — symbol is required."""
        if not self._has_credentials() or not broker_order_id or not symbol:
            return None
        path = f"/api/v5/trade/order?instId={self._inst_id(symbol)}&ordId={broker_order_id}"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{_BASE}{path}",
                                        headers=self._headers("GET", path))
        except httpx.RequestError as exc:
            _logger.debug("[OKXBroker] status lookup failed for %s: %s",
                          broker_order_id, exc)
            return None
        data = _safe_json(resp)
        rows = data.get("data") or []
        if resp.status_code != 200 or data.get("code") != "0" or not rows:
            return None
        row = rows[0]
        status = _STATE_MAP.get(str(row.get("state", "")).lower(),
                                OrderStatus.SUBMITTED)
        return {
            "status": status,
            "filled_qty": _to_float(row.get("accFillSz")),
            "avg_price": _to_float(row.get("avgPx")),
        }

    async def cancel_order(self, broker_order_id: str) -> bool:
        # Cancellation needs instId alongside ordId — same interface
        # limitation as Binance/Bybit.
        _logger.warning("[OKXBroker] cancel_order called without symbol context — skipping")
        return False

    async def get_broker_positions(self) -> list[dict]:
        if not self._has_credentials():
            return []
        path = "/api/v5/account/balance"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{_BASE}{path}",
                                        headers=self._headers("GET", path))
            data = _safe_json(resp)
            if resp.status_code != 200 or data.get("code") != "0":
                return []
            positions = []
            for acct in data.get("data") or []:
                for det in acct.get("details") or []:
                    total = _to_float(det.get("cashBal")) or 0.0
                    if total > 0:
                        positions.append({"symbol": det.get("ccy", ""),
                                          "qty": total, "side": "long"})
            return positions
        except Exception:  # noqa: BLE001
            _logger.exception("[OKXBroker] get_broker_positions failed")
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
