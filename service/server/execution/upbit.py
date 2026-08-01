"""
execution/upbit.py — UpbitBroker (KRW spot market).

Upbit has NO sandbox and NO dry-run: this adapter is only ever constructed
for LIVE routing. Shadow rules on Upbit are journal-only and short-circuit in
gateway.submit_shadow before any adapter is built (Plan 19 shadow strategy C).

Auth: JWT (HS256) carrying access_key + a UUID nonce, plus a SHA512 hash of
the urlencoded request parameters. Hand-rolled — three base64url segments and
an HMAC — to avoid a PyJWT dependency for one venue.

Two venue quirks this adapter owns:
  - Market BUYS are priced in KRW COST (ord_type=price), market SELLS in
    asset volume (ord_type=market). The platform sizes in base units, so a
    buy converts quantity → KRW via the decision price and a live KRW/USD
    rate; the reconciler reads back the actual filled volume.
  - The ledger is USD. Every order records quote_currency="KRW" and the
    fx_rate_usd (KRW per USD, from Upbit's own KRW-USDT book) used at that
    moment — persisted, never recomputed. No rate → the order is REFUSED;
    guessing an FX rate is how ledgers corrupt.

Without credentials every submit_order returns OrderStatus.REJECTED.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import uuid
from urllib.parse import urlencode

import httpx

from execution.base import Broker, Order, OrderStatus, split_symbol

_logger = logging.getLogger(__name__)

_BASE = os.getenv("UPBIT_BASE_URL", "https://api.upbit.com/v1").rstrip("/")


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


class UpbitBroker(Broker):
    """Submits KRW spot market orders to Upbit."""

    def __init__(self, key: str, secret: str):
        self._key = key
        self._secret = secret

    @property
    def broker_name(self) -> str:
        return "upbit"

    def _has_credentials(self) -> bool:
        return bool(self._key and self._secret)

    def _jwt(self, params: dict | None = None) -> str:
        payload = {"access_key": self._key, "nonce": str(uuid.uuid4())}
        if params:
            query = urlencode(params)
            payload["query_hash"] = hashlib.sha512(query.encode()).hexdigest()
            payload["query_hash_alg"] = "SHA512"
        header = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"},
                                    separators=(",", ":")).encode())
        body = _b64url(json.dumps(payload, separators=(",", ":")).encode())
        signing_input = f"{header}.{body}"
        sig = _b64url(hmac.new(self._secret.encode(), signing_input.encode(),
                               hashlib.sha256).digest())
        return f"{signing_input}.{sig}"

    def _headers(self, params: dict | None = None) -> dict:
        return {"Authorization": f"Bearer {self._jwt(params)}"}

    @staticmethod
    def _market(symbol: str) -> str:
        base, _quote = split_symbol(symbol)
        return f"KRW-{base}"  # Upbit is quote-first, and the quote is KRW.

    async def _krw_per_usd(self) -> float | None:
        """KRW per USD from Upbit's own KRW-USDT book (USDT ≈ USD). The rate
        the order actually trades against, not an external reference."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{_BASE}/ticker",
                                        params={"markets": "KRW-USDT"})
            rows = resp.json()
            price = float(rows[0]["trade_price"])
            return price if price > 0 else None
        except Exception:  # noqa: BLE001
            _logger.warning("[UpbitBroker] KRW-USDT rate fetch failed")
            return None

    async def submit_order(self, order: Order, cursor=None) -> Order:
        if not self._has_credentials():
            order.status = OrderStatus.REJECTED
            order.error_message = "upbit API key/secret not configured"
            return order

        side = order.side
        is_buy = side in ("buy", "cover")
        fx = await self._krw_per_usd()
        if fx is None:
            order.status = OrderStatus.REJECTED
            order.error_message = "could not fetch KRW/USD rate — order refused rather than guessing"
            return order
        order.quote_currency = "KRW"
        order.fx_rate_usd = fx

        params: dict = {"market": self._market(order.symbol),
                        "side": "bid" if is_buy else "ask"}
        if is_buy:
            # Market buys are priced in KRW cost. Upbit rejects sub-KRW
            # precision, so round to whole won.
            params["ord_type"] = "price"
            params["price"] = str(int(round(order.quantity * order.price * fx)))
        else:
            params["ord_type"] = "market"
            params["volume"] = f"{order.quantity:.8f}"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(f"{_BASE}/orders",
                                         headers=self._headers(params),
                                         data=params)
        except httpx.RequestError as exc:
            order.status = OrderStatus.REJECTED
            order.error_message = f"network error: {exc}"
            return order

        data = _safe_json(resp)
        if resp.status_code in (200, 201) and data.get("uuid"):
            order.broker_order_id = str(data["uuid"])
            order.status = OrderStatus.SUBMITTED
            _logger.info("[UpbitBroker] submitted %s %s x%s for agent %s → %s",
                         order.side, order.symbol, order.quantity,
                         order.agent_id, order.broker_order_id)
        else:
            order.status = OrderStatus.REJECTED
            err = data.get("error") or {}
            order.error_message = str(err.get("message") or resp.text)
            _logger.warning("[UpbitBroker] rejected %s %s for agent %s: %s",
                            order.side, order.symbol, order.agent_id,
                            order.error_message)
        return order

    async def get_order_status(self, broker_order_id: str, symbol: str = ""):
        if not self._has_credentials() or not broker_order_id:
            return None
        params = {"uuid": broker_order_id}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{_BASE}/order",
                                        headers=self._headers(params),
                                        params=params)
        except httpx.RequestError as exc:
            _logger.debug("[UpbitBroker] status lookup failed for %s: %s",
                          broker_order_id, exc)
            return None
        data = _safe_json(resp)
        if resp.status_code != 200 or not data.get("uuid"):
            return None
        state = str(data.get("state", "")).lower()
        executed = _to_float(data.get("executed_volume")) or 0.0
        # Upbit ends a spent market order in state 'cancel' (the un-spent
        # remainder is cancelled). Executed volume decides what it really was;
        # the reconciler's size-mismatch alert covers any shortfall.
        if state == "done" or (state == "cancel" and executed > 0):
            status = OrderStatus.FILLED
        elif state == "cancel":
            status = OrderStatus.CANCELLED
        else:  # wait / watch
            status = OrderStatus.PARTIAL_FILL if executed > 0 else OrderStatus.SUBMITTED
        trades = data.get("trades") or []
        funds = sum((_to_float(t.get("funds")) or 0.0) for t in trades)
        vol = sum((_to_float(t.get("volume")) or 0.0) for t in trades)
        avg = (funds / vol) if vol > 0 else None  # KRW per unit
        return {"status": status,
                "filled_qty": executed if executed > 0 else _to_float(data.get("executed_volume")),
                "avg_price": avg}

    async def cancel_order(self, broker_order_id: str) -> bool:
        if not self._has_credentials() or not broker_order_id:
            return False
        params = {"uuid": broker_order_id}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.delete(f"{_BASE}/order",
                                           headers=self._headers(params),
                                           params=params)
            return resp.status_code == 200
        except Exception:  # noqa: BLE001
            return False

    async def get_broker_positions(self) -> list[dict]:
        if not self._has_credentials():
            return []
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{_BASE}/accounts",
                                        headers=self._headers())
            rows = resp.json()
            if resp.status_code != 200 or not isinstance(rows, list):
                return []
            positions = []
            for row in rows:
                total = (_to_float(row.get("balance")) or 0.0) + \
                        (_to_float(row.get("locked")) or 0.0)
                if total > 0:
                    positions.append({"symbol": row.get("currency", ""),
                                      "qty": total, "side": "long"})
            return positions
        except Exception:  # noqa: BLE001
            _logger.exception("[UpbitBroker] get_broker_positions failed")
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
