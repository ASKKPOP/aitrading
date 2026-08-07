"""
execution/coinbase.py — CoinbaseBroker (Advanced Trade, spot).

Coinbase runs no live-parallel sandbox for Advanced Trade, so the non-live
construction posts to the venue's own preview endpoint
(/api/v3/brokerage/orders/preview) against the LIVE host (Plan 19 shadow
strategy B): auth, product and size are checked, nothing can fill, and the
answer is VALIDATED or REJECTED — never a fill.

Auth is the odd one out among our venues. Every other adapter signs the request
with an HMAC of a shared secret; Coinbase wants a short-lived ES256 JWT bearer
token whose `uri` claim binds it to ONE method + host + path, so a token is
minted per request and expires 120s later:

    header  {"kid": <key name>, "nonce": <random hex>}
    payload {"sub": <key name>, "iss": "cdp", "nbf": now,
             "exp": now + 120, "uri": "POST api.coinbase.com/api/v3/..."}

The stored `secret` is therefore an EC private key in PEM form, not a shared
secret. Ed25519 keys are NOT accepted here — the key must be created with
ECDSA, which is why the connect form says so.

Symbols: Coinbase quotes its main books in USD while the platform's crypto feed
quotes USDT, so USDT and USDC map onto USD when forming the product id
(BTCUSDT -> BTC-USD). A pair Coinbase does not list is rejected by the venue,
never silently substituted for a different book.

Spot only: there is nothing to short, so short/cover map onto sell/buy the same
way the other spot venues do.

Without credentials every submit_order returns OrderStatus.REJECTED.
"""
from __future__ import annotations

import json
import logging
import os
import secrets
import time
import uuid
from typing import Optional
from urllib.parse import urlparse

import httpx

from execution.base import Broker, Order, OrderStatus, split_symbol

_logger = logging.getLogger(__name__)

_BASE = os.getenv("COINBASE_BASE_URL", "https://api.coinbase.com").rstrip("/")
# The JWT `uri` claim carries the bare host, and it must match the host the
# request actually goes to — derive it rather than hardcoding, so overriding
# the base URL can never mint a token for a host we are not calling.
_HOST = urlparse(_BASE).netloc or "api.coinbase.com"

_API_PREFIX = "/api/v3/brokerage"

_SIDE_MAP = {
    "buy":   "BUY",
    "sell":  "SELL",
    "short": "SELL",
    "cover": "BUY",
}

# Coinbase's books are USD-quoted; the platform's feed speaks USDT.
_QUOTE_MAP = {"USDT": "USD", "USDC": "USD"}

_STATUS_MAP = {
    "FILLED":    OrderStatus.FILLED,
    "OPEN":      OrderStatus.SUBMITTED,
    "PENDING":   OrderStatus.SUBMITTED,
    "QUEUED":    OrderStatus.SUBMITTED,
    "CANCELLED": OrderStatus.CANCELLED,
    "EXPIRED":   OrderStatus.CANCELLED,
    "FAILED":    OrderStatus.REJECTED,
}


class CoinbaseBroker(Broker):
    """Submits spot market orders to Coinbase Advanced Trade.

    Args:
        key:          CDP API key name, e.g. organizations/{org}/apiKeys/{id}.
        secret:       the key's EC private key, PEM-encoded.
        preview_only: True = /orders/preview dry run (shadow); False = real orders.
    """

    def __init__(self, key: str, secret: str, preview_only: bool = True):
        self._key = key
        self._secret = secret
        self._preview_only = preview_only

    @property
    def broker_name(self) -> str:
        return "coinbase"

    def _has_credentials(self) -> bool:
        return bool(self._key and self._secret)

    def _auth_header(self, method: str, path: str) -> Optional[str]:
        """Bearer token for exactly this method+path, or None if the key is
        unusable. A malformed PEM is a credential problem, not a crash."""
        try:
            import jwt
            from cryptography.hazmat.primitives import serialization
        except ImportError:  # pragma: no cover — dependency is in requirements
            _logger.error("[CoinbaseBroker] PyJWT/cryptography not installed")
            return None
        # Pasted keys routinely arrive with the newlines escaped once the blob
        # has been through a form and a JSON column; a PEM without real line
        # breaks will not load.
        pem = self._secret.replace("\\n", "\n").strip()
        try:
            private_key = serialization.load_pem_private_key(pem.encode(), password=None)
        except Exception as exc:  # noqa: BLE001 — any bad key means "unusable"
            _logger.warning("[CoinbaseBroker] private key would not load: %s", exc)
            return None
        now = int(time.time())
        try:
            token = jwt.encode(
                {
                    "sub": self._key,
                    "iss": "cdp",
                    "nbf": now,
                    "exp": now + 120,
                    "uri": f"{method.upper()} {_HOST}{path}",
                },
                private_key,
                algorithm="ES256",
                headers={"kid": self._key, "nonce": secrets.token_hex(16)},
            )
        except Exception as exc:  # noqa: BLE001 — e.g. an Ed25519 key
            _logger.warning("[CoinbaseBroker] could not sign JWT: %s", exc)
            return None
        return f"Bearer {token}"

    @staticmethod
    def _product(symbol: str) -> str:
        base, quote = split_symbol(symbol)
        return f"{base}-{_QUOTE_MAP.get(quote, quote)}"

    async def submit_order(self, order: Order, cursor=None) -> Order:
        if not self._has_credentials():
            order.status = OrderStatus.REJECTED
            order.error_message = "coinbase API key name / private key not configured"
            return order

        path = f"{_API_PREFIX}/orders/preview" if self._preview_only else f"{_API_PREFIX}/orders"
        payload: dict = {
            "product_id": self._product(order.symbol),
            "side": _SIDE_MAP.get(order.side, "BUY"),
            "order_configuration": {
                "market_market_ioc": {"base_size": f"{order.quantity:.8f}"},
            },
        }
        # The preview endpoint takes no client_order_id — sending one 400s.
        if not self._preview_only:
            payload["client_order_id"] = uuid.uuid4().hex

        auth = self._auth_header("POST", path)
        if auth is None:
            order.status = OrderStatus.REJECTED
            order.error_message = "coinbase credentials could not be used to sign the request"
            return order

        body = json.dumps(payload, separators=(",", ":"))
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{_BASE}{path}",
                    headers={"Authorization": auth, "Content-Type": "application/json"},
                    content=body,
                )
        except httpx.RequestError as exc:
            order.status = OrderStatus.REJECTED
            order.error_message = f"network error: {exc}"
            _logger.warning("[CoinbaseBroker] network error for agent %s: %s",
                            order.agent_id, exc)
            return order

        data = _safe_json(resp)
        if resp.status_code != 200:
            order.status = OrderStatus.REJECTED
            order.error_message = _error_text(data) or resp.text
            _logger.warning("[CoinbaseBroker] rejected %s %s for agent %s: %s",
                            order.side, order.symbol, order.agent_id,
                            order.error_message)
            return order

        if self._preview_only:
            # A preview that lists errors is a refusal; an empty errs is the
            # venue saying the order would have been accepted.
            errs = data.get("errs") or []
            if errs:
                order.status = OrderStatus.REJECTED
                order.error_message = "; ".join(str(e) for e in errs)
                _logger.warning("[CoinbaseBroker] preview refused %s %s for agent %s: %s",
                                order.side, order.symbol, order.agent_id,
                                order.error_message)
            else:
                order.status = OrderStatus.VALIDATED
                _logger.info("[CoinbaseBroker] validated %s %s x%s for agent %s",
                             order.side, order.symbol, order.quantity, order.agent_id)
            return order

        if not data.get("success"):
            order.status = OrderStatus.REJECTED
            order.error_message = _error_text(data) or "venue refused the order"
            _logger.warning("[CoinbaseBroker] refused %s %s for agent %s: %s",
                            order.side, order.symbol, order.agent_id,
                            order.error_message)
            return order

        order.broker_order_id = str(
            (data.get("success_response") or {}).get("order_id")
            or data.get("order_id")
            or ""
        )
        if not order.broker_order_id:
            order.status = OrderStatus.REJECTED
            order.error_message = "venue returned no order id"
            return order
        # Market IOC usually fills at once, but the venue reports the fill on
        # the order record — stay SUBMITTED and let the reconciler confirm.
        order.status = OrderStatus.SUBMITTED
        _logger.info("[CoinbaseBroker] submitted %s %s x%s for agent %s → %s",
                     order.side, order.symbol, order.quantity,
                     order.agent_id, order.broker_order_id)
        return order

    async def get_order_status(self, broker_order_id: str, symbol: str = ""):
        if not self._has_credentials() or not broker_order_id:
            return None
        path = f"{_API_PREFIX}/orders/historical/{broker_order_id}"
        auth = self._auth_header("GET", path)
        if auth is None:
            return None
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{_BASE}{path}",
                                        headers={"Authorization": auth})
        except httpx.RequestError as exc:
            _logger.debug("[CoinbaseBroker] status lookup failed for %s: %s",
                          broker_order_id, exc)
            return None
        if resp.status_code != 200:
            return None
        row = (_safe_json(resp).get("order") or {})
        if not row:
            return None
        status = _STATUS_MAP.get(str(row.get("status") or "").upper())
        if status is None:
            return None
        filled = _to_float(row.get("filled_size"))
        # Still working with something already filled is a partial, whatever
        # the venue's coarse status says.
        if status is OrderStatus.SUBMITTED and filled:
            status = OrderStatus.PARTIAL_FILL
        return {
            "status": status,
            "filled_qty": filled if filled else None,
            "avg_price": _to_float(row.get("average_filled_price")),
        }

    async def cancel_order(self, broker_order_id: str) -> bool:
        if not self._has_credentials() or not broker_order_id:
            return False
        path = f"{_API_PREFIX}/orders/batch_cancel"
        auth = self._auth_header("POST", path)
        if auth is None:
            return False
        body = json.dumps({"order_ids": [broker_order_id]}, separators=(",", ":"))
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{_BASE}{path}",
                    headers={"Authorization": auth, "Content-Type": "application/json"},
                    content=body,
                )
            if resp.status_code != 200:
                return False
            results = _safe_json(resp).get("results") or []
            return bool(results) and bool(results[0].get("success"))
        except Exception:  # noqa: BLE001
            return False

    async def get_broker_positions(self) -> list[dict]:
        if not self._has_credentials():
            return []
        path = f"{_API_PREFIX}/accounts"
        auth = self._auth_header("GET", path)
        if auth is None:
            return []
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{_BASE}{path}",
                                        headers={"Authorization": auth})
            if resp.status_code != 200:
                return []
            positions = []
            for row in _safe_json(resp).get("accounts") or []:
                qty = _to_float((row.get("available_balance") or {}).get("value"))
                if qty and qty > 0:
                    positions.append({"symbol": row.get("currency", ""),
                                      "qty": qty, "side": "long"})
            return positions
        except Exception:  # noqa: BLE001
            _logger.exception("[CoinbaseBroker] get_broker_positions failed")
            return []


def _safe_json(resp) -> dict:
    try:
        data = resp.json()
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _error_text(data: dict) -> str:
    """The clearest sentence Coinbase gave us about a refusal."""
    err = data.get("error_response") or {}
    for field in ("message", "error_details", "preview_failure_reason", "error"):
        value = err.get(field) or data.get(field)
        if value:
            return str(value)
    return str(data.get("failure_reason") or "")


def _to_float(value):
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
