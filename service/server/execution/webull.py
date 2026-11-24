"""
execution/webull.py — WebullBroker (Webull OpenAPI, US stocks, 1x).

Production:  https://api.webull.com
Sandbox:     https://api.sandbox.webull.com   (PaperTrade app credentials)

Auth: an App Key + App Secret pair from the Webull Developer Console. Every
request is signed (developer.webull.com/apis/authentication/signature):

    1. query params + the x-app-key / x-timestamp / x-signature-algorithm /
       x-signature-version / x-signature-nonce headers + host, keys sorted,
       joined k=v&k=v (values NOT encoded)                        -> str1
    2. body present: MD5 of the exact body bytes, upper-case hex  -> str2
    3. path + "&" + str1 (+ "&" + str2)                            -> str3
    4. HMAC-SHA1(key = app_secret + "&", msg = quote(str3, safe="")), base64

The secret itself is never sent. The body is serialised once and the SAME
bytes are both hashed and sent — re-serialising (httpx json=) could reorder or
re-space it and break the signature.

Scope (owner rules): US stocks, 1x. Market DAY orders, regular session.
    buy   -> BUY    sell  -> SELL
    short -> SHORT  (a short sale; Webull's side enum is BUY / SELL / SHORT)
    cover -> BUY    (buy-to-cover against the open short)
US-stock shorts follow the platform policy (owner 2026-11-23: "Webull also
allow short for us-stock"): futures_policy decides upstream whether a short
may open (shorts_trading_blocked=on re-arms long-only) — this adapter only
maps the verb. A short sale needs a Webull MARGIN account; a cash account is
refused by Webull itself. Any other verb is refused before any network call;
options/crypto/leverage never reach here (BROKER_MARKETS: us-stock only, and
instrument_type is always EQUITY).

Orders are keyed by OUR client_order_id (Webull's detail and cancel endpoints
take it), so that is what becomes broker_order_id.

Not handled here: production apps with Webull's 2FA token switched on need an
x-access-token created and approved in the Webull app. If the stored blob
carries an "access_token" it is sent; otherwise the venue answers 401 and the
order is REJECTED with that message — never a silent fill.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import quote, urlencode

import httpx

from execution.base import Broker, Order, OrderStatus

_logger = logging.getLogger(__name__)

LIVE_HOST = "api.webull.com"
SANDBOX_HOST = "api.sandbox.webull.com"

_SIGNED_HEADERS = ("x-app-key", "x-timestamp", "x-signature-algorithm",
                   "x-signature-version", "x-signature-nonce")

_SIDE_MAP = {"buy": "BUY", "sell": "SELL", "short": "SHORT", "cover": "BUY"}

_STATUS_MAP = {
    "FILLED": OrderStatus.FILLED,
    "PARTIAL_FILLED": OrderStatus.PARTIAL_FILL,
    "CANCELLED": OrderStatus.CANCELLED,
    "EXPIRED": OrderStatus.CANCELLED,
    "FAILED": OrderStatus.REJECTED,
    "REJECTED": OrderStatus.REJECTED,
}

# Raw venue statuses that confirm an order exists and is alive / is dead.
_LIVE_STATUSES = {"PENDING", "SUBMITTED", "PARTIAL_FILLED", "FILLED"}
_DEAD_STATUSES = {"CANCELLED", "EXPIRED", "FAILED", "REJECTED"}

# Failures where the request provably never left this host. Anything else
# (read timeout, dropped connection) may have placed the order at Webull.
_NOT_SENT = (httpx.ConnectError, httpx.ConnectTimeout, httpx.UnsupportedProtocol,
             httpx.LocalProtocolError, httpx.ProxyError)


def sign_request(app_secret: str, path: str, query: dict, headers: dict,
                 host: str, body: bytes = b"") -> str:
    """Webull OpenAPI request signature (HMAC-SHA1 / MD5 body digest)."""
    items = {str(k): str(v) for k, v in (query or {}).items()}
    for k in _SIGNED_HEADERS:
        items[k] = headers[k]
    items["host"] = host
    str3 = path + "&" + "&".join(f"{k}={items[k]}" for k in sorted(items))
    if body:
        str3 += "&" + hashlib.md5(body).hexdigest().upper()
    mac = hmac.new((app_secret + "&").encode(), quote(str3, safe="").encode(),
                   hashlib.sha1)
    return base64.b64encode(mac.digest()).decode()


def _qty(value: float) -> str:
    """Quantity as a plain decimal string (no exponent, no trailing zeros)."""
    text = f"{float(value):.8f}".rstrip("0").rstrip(".")
    return text or "0"


def _float(value) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class WebullBroker(Broker):
    """Market orders for US equities through the Webull OpenAPI.

    Args:
        key / secret:  App Key / App Secret.
        sandbox:       True = PaperTrade host; False = production.
        account_id:    optional; discovered from /trading/accounts/list when
                       blank (a single account, or the single CASH account —
                       anything ambiguous is refused, never guessed).
        access_token:  optional 2FA token (x-access-token).
    """

    def __init__(self, key: str, secret: str, sandbox: bool = True,
                 account_id: str = "", access_token: str = ""):
        self._key = key or ""
        self._secret = secret or ""
        self._sandbox = sandbox
        self.host = SANDBOX_HOST if sandbox else LIVE_HOST
        self._account_id = (account_id or "").strip()
        self._access_token = (access_token or "").strip()

    @property
    def broker_name(self) -> str:
        return "webull"

    def _has_credentials(self) -> bool:
        return bool(self._key and self._secret)

    # ── transport ─────────────────────────────────────────────────────────
    def _signed(self, path: str, query: Optional[dict], body: Optional[dict]):
        """(url, headers, body_bytes) for one signed request."""
        headers = {
            "x-app-key": self._key,
            "x-timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "x-signature-algorithm": "HMAC-SHA1",
            "x-signature-version": "1.0",
            "x-signature-nonce": uuid.uuid4().hex,
            "x-version": "v3",
        }
        body_bytes = b""
        if body is not None:
            body_bytes = json.dumps(body, separators=(",", ":"),
                                    ensure_ascii=False).encode()
            headers["Content-Type"] = "application/json"
        headers["x-signature"] = sign_request(self._secret, path, query or {},
                                              headers, self.host, body_bytes)
        if self._access_token:
            headers["x-access-token"] = self._access_token
        url = f"https://{self.host}{path}"
        if query:
            # %20, never '+': Webull decodes the query and re-signs the raw values.
            url += "?" + urlencode(query, quote_via=quote)
        return url, headers, body_bytes

    async def _get(self, path: str, query: Optional[dict] = None):
        url, headers, _ = self._signed(path, query, None)
        async with httpx.AsyncClient(timeout=10.0) as client:
            return await client.get(url, headers=headers)

    async def _post(self, path: str, body: dict):
        url, headers, body_bytes = self._signed(path, None, body)
        async with httpx.AsyncClient(timeout=10.0) as client:
            return await client.post(url, headers=headers, content=body_bytes)

    @staticmethod
    def _error_text(resp) -> str:
        try:
            data = resp.json()
            if isinstance(data, dict):
                msg = data.get("message") or data.get("msg")
                code = data.get("error_code") or data.get("code")
                if msg or code:
                    return f"{code}: {msg}" if code and msg else str(msg or code)
        except Exception:  # noqa: BLE001
            pass
        return (resp.text or f"HTTP {resp.status_code}")[:300]

    async def _resolve_account(self) -> tuple[Optional[str], str]:
        """(account_id, error).

        Explicit id → used as-is. Otherwise exactly one account, or exactly
        one CASH account among several (a cash account cannot borrow — the
        1x rule). Two cash accounts, or several margin accounts, are refused:
        the user must name the account."""
        if self._account_id:
            return self._account_id, ""
        resp = await self._get("/trading/accounts/list")
        if resp.status_code != 200:
            return None, f"account lookup failed: {self._error_text(resp)}"
        rows = resp.json()
        if isinstance(rows, dict):
            rows = rows.get("data") or rows.get("accounts") or []
        rows = [r for r in rows if isinstance(r, dict) and r.get("account_id")]
        if len(rows) != 1:
            cash = [r for r in rows if str(r.get("account_type", "")).upper() == "CASH"]
            if len(cash) == 1:
                rows = cash
            else:
                return None, (f"Webull returned {len(rows)} accounts — reconnect "
                              "with the account id to trade")
        self._account_id = str(rows[0]["account_id"])
        return self._account_id, ""

    # ── Broker contract ───────────────────────────────────────────────────
    async def submit_order(self, order: Order, cursor=None) -> Order:
        if not self._has_credentials():
            order.status = OrderStatus.REJECTED
            order.error_message = "Webull app key / secret not configured"
            return order
        side = _SIDE_MAP.get(order.side)
        if side is None:
            order.status = OrderStatus.REJECTED
            order.error_message = (f"Webull gateway trades US stocks at 1x "
                                   f"(buy/sell/short/cover): {order.side!r} "
                                   "orders are not sent")
            return order

        client_order_id = uuid.uuid4().hex  # 32 chars, the documented maximum
        try:
            account_id, err = await self._resolve_account()
        except httpx.RequestError as exc:
            order.status = OrderStatus.REJECTED
            order.error_message = f"network error: {exc}"
            return order
        except (ValueError, TypeError, AttributeError, KeyError) as exc:
            order.status = OrderStatus.REJECTED
            order.error_message = f"unreadable Webull account list: {exc}"
            return order
        if not account_id:
            order.status = OrderStatus.REJECTED
            order.error_message = err
            return order

        if order.side == "cover":
            refusal = await self._cover_refusal(account_id, order)
            if refusal:
                order.status = OrderStatus.REJECTED
                order.error_message = refusal
                _logger.warning("[WebullBroker] cover refused for agent %s: %s",
                                order.agent_id, refusal)
                return order

        body = {
            "account_id": account_id,
            "new_orders": [{
                "client_order_id": client_order_id,
                "combo_type": "NORMAL",
                "symbol": order.symbol.upper(),
                "instrument_type": "EQUITY",
                "market": "US",
                "order_type": "MARKET",
                "quantity": _qty(order.quantity),
                "side": side,
                "time_in_force": "DAY",
                "entrust_type": "QTY",
                "support_trading_session": "CORE",
            }],
        }
        # From here on the order may exist at Webull, so it always carries its
        # id — a refused or unknown order is still traceable by the user.
        order.broker_order_id = client_order_id
        try:
            resp = await self._post("/trading/orders/place", body)
        except _NOT_SENT as exc:
            order.status = OrderStatus.REJECTED
            order.error_message = f"network error: {exc}"
            _logger.warning("[WebullBroker] network error for agent %s: %s",
                            order.agent_id, exc)
            return order
        except httpx.RequestError as exc:
            # The request may have reached Webull before the reply was lost.
            # Ask Webull about OUR client_order_id rather than guessing either
            # way: a hidden live order is as wrong as a phantom ledger fill.
            return await self._settle_unknown(order, exc)

        accepted = False
        if resp.status_code == 200:
            try:
                data = resp.json()
                accepted = isinstance(data, dict) and bool(
                    data.get("order_id") or data.get("client_order_id"))
            except ValueError:
                accepted = False
        if not accepted and (resp.status_code == 200 or resp.status_code >= 500):
            # A 5xx (load balancer, upstream timeout) or a 200 we cannot read
            # says nothing definite about the order — look it up. Only a 4xx is
            # Webull's own refusal.
            return await self._settle_unknown(
                order, f"HTTP {resp.status_code}: {self._error_text(resp)}")
        if accepted:
            order.status = OrderStatus.SUBMITTED  # the reconciler confirms the fill
            _logger.info("[WebullBroker] submitted %s %s x%s for agent %s → %s",
                         order.side, order.symbol, order.quantity,
                         order.agent_id, client_order_id)
        else:
            order.status = OrderStatus.REJECTED
            order.error_message = self._error_text(resp)
            _logger.warning("[WebullBroker] rejected %s %s for agent %s: %s",
                            order.side, order.symbol, order.agent_id,
                            order.error_message)
        return order

    # Seconds to wait before each lookup of an order whose place reply was
    # lost. Order detail is rate-limited to 2 calls / 2 s per app key, and a
    # just-placed order may not be indexed yet — hence more than one try.
    _LOOKUP_DELAYS = (1.1, 2.2, 4.4)

    async def _settle_unknown(self, order: Order, cause) -> Order:
        """The place call ended ambiguously — ask Webull about our id.

        Confirmed live at Webull → SUBMITTED (never FILLED here: the reconciler
        polls SUBMITTED rows and records the broker-confirmed fill size).
        Confirmed dead → REJECTED. Still unknown after every try → REJECTED
        'outcome unknown', id kept, error-logged for the user to check."""
        venue_status = None
        for delay in self._LOOKUP_DELAYS:
            await asyncio.sleep(delay)
            status = await self.get_order_status(order.broker_order_id)
            venue_status = (status or {}).get("venue_status")
            if venue_status in _LIVE_STATUSES or venue_status in _DEAD_STATUSES:
                break
        if venue_status in _LIVE_STATUSES:
            order.status = OrderStatus.SUBMITTED
            _logger.warning("[WebullBroker] place reply lost (%s) but order %s is %s",
                            cause, order.broker_order_id, venue_status)
            return order
        order.status = OrderStatus.REJECTED
        if venue_status in _DEAD_STATUSES:
            order.error_message = f"order {venue_status} at Webull after: {cause}"
        else:
            order.error_message = (
                f"place outcome unknown ({cause}) — Webull did not confirm "
                f"client_order_id {order.broker_order_id}; check your Webull orders")
        _logger.error("[WebullBroker] %s (agent %s)", order.error_message, order.agent_id)
        return order

    async def get_order_status(self, broker_order_id: str, symbol: str = ""):
        if not self._has_credentials() or not broker_order_id:
            return None
        try:
            account_id, _ = await self._resolve_account()
            if not account_id:
                return None
            resp = await self._get("/trading/orders/get", {
                "account_id": account_id, "client_order_id": broker_order_id})
            if resp.status_code != 200:
                return None
            data = resp.json()
            legs = data.get("orders") if isinstance(data, dict) else None
            if not isinstance(legs, list):
                return None
            legs = [o for o in legs if isinstance(o, dict)]
            leg = next((o for o in legs
                        if o.get("client_order_id") == broker_order_id), None)
            # Legs without ids are only trusted when the reply is unambiguous.
            if leg is None and len(legs) == 1 and not legs[0].get("client_order_id"):
                leg = legs[0]
            if leg is None:
                return None
            venue_status = str(leg.get("status") or "").upper()
            return {
                "venue_status": venue_status,
                "status": _STATUS_MAP.get(venue_status, OrderStatus.SUBMITTED),
                "filled_qty": _float(leg.get("filled_quantity")),
                "avg_price": _float(leg.get("filled_price")),
            }
        except (httpx.RequestError, ValueError, TypeError, AttributeError, KeyError) as exc:
            _logger.debug("[WebullBroker] status lookup failed for %s: %s",
                          broker_order_id, exc)
            return None

    async def cancel_order(self, broker_order_id: str) -> bool:
        if not self._has_credentials() or not broker_order_id:
            return False
        try:
            account_id, _ = await self._resolve_account()
            if not account_id:
                return False
            resp = await self._post("/trading/orders/cancel", {
                "account_id": account_id, "client_order_id": broker_order_id})
            return resp.status_code == 200
        except (httpx.RequestError, ValueError, TypeError, AttributeError, KeyError):
            return False

    async def _read_positions(self, account_id: str) -> Optional[list]:
        """Webull's position rows, or None when they could not be read
        (an empty list means "read, and nothing held")."""
        try:
            resp = await self._get("/trading/assets/positions/list",
                                   {"account_id": account_id})
            if resp.status_code != 200:
                return None
            rows = resp.json()
            if isinstance(rows, dict):
                rows = rows.get("data") or rows.get("positions")
            if not isinstance(rows, list):
                return None
            return [r for r in rows if isinstance(r, dict)]
        except (httpx.RequestError, ValueError, TypeError, AttributeError, KeyError):
            return None

    async def _cover_refusal(self, account_id: str, order: Order) -> Optional[str]:
        """Why this cover must not be sent, or None.

        Webull's side enum has no buy-to-cover: a cover is a plain BUY, and a
        BUY with no short behind it OPENS A LONG. The platform's own guard
        reads the ledger, which can disagree with the venue (a short Webull
        rejected after accepting, a short opened by a simulator rule), so ask
        Webull. Webull does not document how a short position is signed, so
        only what holds under any convention is refused: no position in the
        symbol at all, or a cover larger than the position's size. A read
        that fails does not block the cover — refusing every cover then
        could strand a real short — it is logged instead."""
        rows = await self._read_positions(account_id)
        if rows is None:
            _logger.warning("[WebullBroker] cover %s: positions unreadable; "
                            "sending without the venue check", order.symbol)
            return None
        sym = order.symbol.upper()
        held = [abs(_float(r.get("quantity")) or 0.0) for r in rows
                if str(r.get("symbol") or "").upper() == sym]
        size = sum(held)
        if size <= 0:
            return (f"no open Webull position in {sym} to cover — a cover is a "
                    "BUY at Webull and would open a long; order not sent")
        if order.quantity > size + 1e-9:
            return (f"cover of {_qty(order.quantity)} {sym} exceeds the "
                    f"{_qty(size)} held at Webull — the excess BUY would open a "
                    "long; order not sent")
        return None

    async def get_broker_positions(self) -> list[dict]:
        if not self._has_credentials():
            return []
        try:
            account_id, _ = await self._resolve_account()
            if not account_id:
                return []
        except (httpx.RequestError, ValueError, TypeError, AttributeError, KeyError):
            return []
        rows = await self._read_positions(account_id) or []
        out = []
        for p in rows:
            qty = _float(p.get("quantity")) or 0.0
            out.append({"symbol": p.get("symbol"), "qty": abs(qty),
                        "side": "long" if qty >= 0 else "short"})
        return out
