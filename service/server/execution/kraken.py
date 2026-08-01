"""
execution/kraken.py — KrakenBroker (spot REST API).

Kraken has NO spot sandbox. The non-live construction runs the venue's own
AddOrder `validate=true` dry-run against the LIVE endpoint (Plan 19 shadow
strategy B): auth, pair, size and balance are checked, no order is placed,
and the answer is VALIDATED or REJECTED — never a fill.

Auth: API-Key header + API-Sign =
    base64(HMAC-SHA512(path + SHA256(nonce + postdata), base64decode(secret)))

Nonces MUST be monotonic per key — Kraken permanently invalidates a key on
regression, and prod runs a worker plus an API process, so time.time() alone
WILL regress across processes. Nonces come from a DB-backed counter per
broker account (broker_nonces), bumped inside a transaction; the counter
seeds itself from wall-clock ms so it also survives being created fresh.

Without credentials every submit_order returns OrderStatus.REJECTED.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import time
from typing import Optional
from urllib.parse import urlencode

import httpx

from execution.base import Broker, Order, OrderStatus, split_symbol

_logger = logging.getLogger(__name__)

_BASE = os.getenv("KRAKEN_BASE_URL", "https://api.kraken.com").rstrip("/")

_SIDE_MAP = {
    "buy":   "buy",
    "sell":  "sell",
    "short": "sell",
    "cover": "buy",
}

# Kraken's legacy asset renames — the pair must use the venue's spelling.
_ASSET_MAP = {"BTC": "XBT", "DOGE": "XDG"}

_STATUS_MAP = {
    "closed": OrderStatus.FILLED,
    "open": OrderStatus.SUBMITTED,
    "pending": OrderStatus.SUBMITTED,
    "canceled": OrderStatus.CANCELLED,
    "expired": OrderStatus.CANCELLED,
}


def _next_nonce(account_id: Optional[int]) -> int:
    """Monotonic per-account nonce. Bump-then-read inside one transaction so
    two processes can never hand out the same value (InnoDB row lock / SQLite
    database lock). Falls back to wall-clock ms when there is no account row
    to anchor to (unit tests, ad-hoc adapters)."""
    now_ms = int(time.time() * 1000)
    if account_id is None:
        return now_ms
    from database import get_db_connection, using_mysql
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        # MySQL and SQLite spell insert-if-absent differently.
        if using_mysql():
            cursor.execute(
                "INSERT IGNORE INTO broker_nonces (account_id, nonce) VALUES (?, 0)",
                (account_id,),
            )
        else:
            cursor.execute(
                "INSERT OR IGNORE INTO broker_nonces (account_id, nonce) VALUES (?, 0)",
                (account_id,),
            )
        cursor.execute(
            """UPDATE broker_nonces
               SET nonce = CASE WHEN nonce + 1 > ? THEN nonce + 1 ELSE ? END
               WHERE account_id = ?""",
            (now_ms, now_ms, account_id),
        )
        cursor.execute("SELECT nonce FROM broker_nonces WHERE account_id = ?",
                       (account_id,))
        row = cursor.fetchone()
        conn.commit()
        return int(row[0]) if row else now_ms
    finally:
        conn.close()


class KrakenBroker(Broker):
    """Submits spot market orders to Kraken's REST API.

    Args:
        key/secret:    Kraken API credentials (secret is base64).
        validate_only: True = AddOrder validate=true dry-run (shadow);
                       False = real orders (live).
        account_id:    broker_accounts.id anchoring the nonce counter.
    """

    def __init__(self, key: str, secret: str, validate_only: bool = True,
                 account_id: Optional[int] = None):
        self._key = key
        self._secret = secret
        self._validate_only = validate_only
        self._account_id = account_id

    @property
    def broker_name(self) -> str:
        return "kraken"

    def _has_credentials(self) -> bool:
        return bool(self._key and self._secret)

    def _sign(self, path: str, params: dict) -> tuple:
        """Return (postdata, headers) for a private call."""
        postdata = urlencode(params)
        digest = hashlib.sha256((str(params["nonce"]) + postdata).encode()).digest()
        try:
            secret = base64.b64decode(self._secret)
        except Exception:  # noqa: BLE001 — malformed secret signs garbage, venue rejects
            secret = self._secret.encode()
        mac = hmac.new(secret, path.encode() + digest, hashlib.sha512)
        headers = {
            "API-Key": self._key,
            "API-Sign": base64.b64encode(mac.digest()).decode(),
            "Content-Type": "application/x-www-form-urlencoded",
        }
        return postdata, headers

    @staticmethod
    def _pair(symbol: str) -> str:
        base, quote = split_symbol(symbol, default_quote="USD")
        return f"{_ASSET_MAP.get(base, base)}{_ASSET_MAP.get(quote, quote)}"

    async def _private(self, path: str, params: dict) -> Optional[dict]:
        params["nonce"] = _next_nonce(self._account_id)
        postdata, headers = self._sign(path, params)
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(f"{_BASE}{path}", headers=headers,
                                         content=postdata)
        except httpx.RequestError as exc:
            return {"error": [f"network error: {exc}"]}
        try:
            data = resp.json()
            return data if isinstance(data, dict) else None
        except Exception:  # noqa: BLE001
            return None

    async def submit_order(self, order: Order, cursor=None) -> Order:
        if not self._has_credentials():
            order.status = OrderStatus.REJECTED
            order.error_message = "kraken API key/secret not configured"
            return order

        params = {
            "ordertype": "market",
            "type": _SIDE_MAP.get(order.side, "buy"),
            "volume": f"{order.quantity:.8f}",
            "pair": self._pair(order.symbol),
        }
        if self._validate_only:
            params["validate"] = "true"

        data = await self._private("/0/private/AddOrder", params)
        if data is None:
            order.status = OrderStatus.REJECTED
            order.error_message = "malformed response from venue"
            return order
        errors = data.get("error") or []
        if errors:
            order.status = OrderStatus.REJECTED
            order.error_message = "; ".join(str(e) for e in errors)
            _logger.warning("[KrakenBroker] rejected %s %s for agent %s: %s",
                            order.side, order.symbol, order.agent_id,
                            order.error_message)
            return order

        result = data.get("result") or {}
        if self._validate_only:
            # validate=true returns the order description and no txid — the
            # venue accepted the order without placing it.
            order.status = OrderStatus.VALIDATED
            _logger.info("[KrakenBroker] validated %s %s x%s for agent %s",
                         order.side, order.symbol, order.quantity, order.agent_id)
            return order

        txids = result.get("txid") or []
        order.broker_order_id = str(txids[0]) if txids else None
        order.status = OrderStatus.SUBMITTED if order.broker_order_id else OrderStatus.REJECTED
        if order.status is OrderStatus.REJECTED:
            order.error_message = "venue returned no transaction id"
        else:
            _logger.info("[KrakenBroker] submitted %s %s x%s for agent %s → %s",
                         order.side, order.symbol, order.quantity,
                         order.agent_id, order.broker_order_id)
        return order

    async def get_order_status(self, broker_order_id: str, symbol: str = ""):
        if not self._has_credentials() or not broker_order_id:
            return None
        data = await self._private("/0/private/QueryOrders",
                                   {"txid": broker_order_id})
        if not data or data.get("error"):
            return None
        row = (data.get("result") or {}).get(broker_order_id)
        if not isinstance(row, dict):
            return None
        raw = str(row.get("status", "")).lower()
        status = _STATUS_MAP.get(raw, OrderStatus.SUBMITTED)
        filled = _to_float(row.get("vol_exec"))
        # Kraken reports an open order with partial executions as "open" —
        # surface it as a partial fill so the reconciler keeps polling.
        if status is OrderStatus.SUBMITTED and filled and filled > 0:
            status = OrderStatus.PARTIAL_FILL
        return {
            "status": status,
            "filled_qty": filled,
            "avg_price": _to_float(row.get("price")),
        }

    async def cancel_order(self, broker_order_id: str) -> bool:
        if not self._has_credentials() or not broker_order_id:
            return False
        data = await self._private("/0/private/CancelOrder",
                                   {"txid": broker_order_id})
        return bool(data and not data.get("error"))

    async def get_broker_positions(self) -> list[dict]:
        if not self._has_credentials():
            return []
        data = await self._private("/0/private/Balance", {})
        if not data or data.get("error"):
            return []
        positions = []
        for asset, bal in (data.get("result") or {}).items():
            total = _to_float(bal) or 0.0
            if total > 0:
                positions.append({"symbol": asset, "qty": total, "side": "long"})
        return positions


def _to_float(value):
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
