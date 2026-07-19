"""
execution/ibkr.py — IBKRBroker over the Client Portal Web API (CPAPI).

Why CPAPI and not ib_insync/TWS sockets: the socket API needs a desktop TWS
process, a persistent connection and its own asyncio loop, none of which fit a
stateless request path or a server deployment. CPAPI is plain REST, so this
adapter follows the same shape as alpaca.py and binance.py and adds no
dependency beyond httpx.

What the user must run: IBKR's Client Portal Gateway, reachable from this
server and authenticated to their account. Sooppiy stores only the gateway base
URL and the account id — CPAPI has no API key/secret; the gateway session IS
the credential.

    gateway_url — e.g. https://ib-gateway.internal:5000/v1/api
    account_id  — e.g. U1234567 (live) or DU1234567 (paper)

── The paper/live problem, and how it is handled ──────────────────────────────
Alpaca and Binance expose separate sandbox and live HOSTS, so shadow mode can
be pinned to the sandbox by URL. IBKR does not: one gateway, one API, and the
ACCOUNT decides whether an order risks real money. That breaks the guarantee
execution/gateway.py relies on, so this adapter enforces it itself: in paper
(shadow) mode it refuses to submit unless the account id looks like an IBKR
paper account. Refusing to compare is acceptable; silently routing a "shadow"
order to a live account is not.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from execution.base import Broker, Order, OrderStatus

_logger = logging.getLogger(__name__)

# IBKR paper accounts are issued as the live id prefixed with D (U123 → DU123).
# This is the only signal CPAPI gives us about which side of the house we are
# on, so treat anything else as live.
_PAPER_ACCOUNT_PREFIX = "D"

_SIDE_MAP = {"buy": "BUY", "sell": "SELL", "short": "SELL", "cover": "BUY"}

_DEFAULT_TIMEOUT = 15.0


def is_paper_account(account_id: str) -> bool:
    """True when *account_id* is an IBKR paper account."""
    return (account_id or "").strip().upper().startswith(_PAPER_ACCOUNT_PREFIX)


class IBKRBroker(Broker):
    """Submits market orders through an IBKR Client Portal Gateway.

    Args:
        gateway_url: base URL of the Client Portal Gateway, including /v1/api.
        account_id:  IBKR account the orders are placed for.
        paper:       True when the caller intends a non-real-money route
                     (shadow). Submission is refused unless *account_id* is an
                     IBKR paper account, because CPAPI cannot enforce it.
        verify_tls:  False only for a local gateway with a self-signed cert.
    """

    def __init__(self, gateway_url: str = "", account_id: str = "",
                 paper: bool = True, verify_tls: bool = True):
        self._base = (gateway_url or "").rstrip("/")
        self._account = (account_id or "").strip()
        self._paper = paper
        self._verify = verify_tls

    @property
    def broker_name(self) -> str:
        return "ibkr"

    # ── helpers ──────────────────────────────────────────────────────────────

    def _has_credentials(self) -> bool:
        return bool(self._base and self._account)

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT, verify=self._verify)

    def _guard(self, order: Order) -> Optional[Order]:
        """Reject *order* when it must not be sent. Returns the rejected order,
        or None when submission may proceed."""
        if not self._has_credentials():
            order.status = OrderStatus.REJECTED
            order.error_message = (
                "IBKR gateway not configured — set the Client Portal Gateway URL "
                "and account id on the Accounts page"
            )
            return order
        if self._paper and not is_paper_account(self._account):
            # See the module docstring: CPAPI has no sandbox endpoint, so a
            # shadow order here would hit the live account.
            order.status = OrderStatus.REJECTED
            order.error_message = (
                f"refusing to place a shadow order on IBKR account {self._account}: "
                "it is not a paper account (IBKR paper ids start with D), and the "
                "Client Portal API has no sandbox endpoint to fall back to"
            )
            _logger.warning(
                "[IBKRBroker] blocked shadow order on non-paper account %s (agent %s)",
                self._account, order.agent_id,
            )
            return order
        return None

    async def _resolve_conid(self, client: httpx.AsyncClient, symbol: str) -> Optional[str]:
        """Map a symbol to an IBKR contract id. CPAPI orders take conid, not
        symbol, so this lookup is mandatory before every submission."""
        resp = await client.post(
            f"{self._base}/iserver/secdef/search",
            json={"symbol": symbol.upper(), "name": False},
        )
        if resp.status_code != 200:
            return None
        results = resp.json()
        if not isinstance(results, list) or not results:
            return None
        conid = results[0].get("conid")
        return str(conid) if conid is not None else None

    async def _confirm_replies(self, client: httpx.AsyncClient, payload: Any) -> Any:
        """Walk CPAPI's confirmation dialogue.

        Submitting can return a list of questions ("this order exceeds a size
        threshold, proceed?") instead of an order id. Each must be replied to
        before the order actually reaches the market. Bounded so a gateway that
        keeps asking cannot spin forever.
        """
        for _ in range(5):
            if not isinstance(payload, list) or not payload:
                return payload
            first = payload[0]
            if not isinstance(first, dict) or "id" not in first or "message" not in first:
                return payload
            reply_id = first["id"]
            _logger.info("[IBKRBroker] confirming gateway prompt: %s", first.get("message"))
            resp = await client.post(
                f"{self._base}/iserver/reply/{reply_id}",
                json={"confirmed": True},
            )
            if resp.status_code != 200:
                return payload
            payload = resp.json()
        return payload

    # ── Broker ABC ───────────────────────────────────────────────────────────

    async def submit_order(self, order: Order, cursor=None) -> Order:
        blocked = self._guard(order)
        if blocked is not None:
            return blocked

        try:
            async with self._client() as client:
                conid = await self._resolve_conid(client, order.symbol)
                if not conid:
                    order.status = OrderStatus.REJECTED
                    order.error_message = f"no IBKR contract found for symbol {order.symbol}"
                    return order

                body = {"orders": [{
                    "conid": int(conid),
                    "orderType": "MKT",
                    "side": _SIDE_MAP.get(order.side, "BUY"),
                    "quantity": order.quantity,
                    "tif": "DAY",
                }]}
                resp = await client.post(
                    f"{self._base}/iserver/account/{self._account}/orders",
                    json=body,
                )
                if resp.status_code not in (200, 201):
                    order.status = OrderStatus.REJECTED
                    order.error_message = _error_text(resp)
                    _logger.warning("[IBKRBroker] rejected %s %s for agent %s: %s",
                                    order.side, order.symbol, order.agent_id,
                                    order.error_message)
                    return order

                result = await self._confirm_replies(client, resp.json())
        except httpx.RequestError as exc:
            order.status = OrderStatus.REJECTED
            order.error_message = f"gateway unreachable: {exc}"
            _logger.warning("[IBKRBroker] network error for agent %s: %s", order.agent_id, exc)
            return order

        placed = result[0] if isinstance(result, list) and result else result
        if not isinstance(placed, dict) or not placed.get("order_id"):
            order.status = OrderStatus.REJECTED
            order.error_message = f"gateway did not return an order id: {placed}"
            return order

        order.broker_order_id = str(placed["order_id"])
        status = str(placed.get("order_status", "")).lower()
        order.status = OrderStatus.FILLED if status in ("filled", "completed") else OrderStatus.SUBMITTED
        _logger.info("[IBKRBroker] submitted %s %s x%s for agent %s → %s (%s)",
                     order.side, order.symbol, order.quantity, order.agent_id,
                     order.broker_order_id, status or "submitted")
        return order

    async def session_status(self) -> dict:
        """Is the Client Portal Gateway reachable and still authenticated?

        CPAPI sessions expire and the gateway needs periodic re-auth, so a live
        IBKR rule can stop filling without anything in Sooppiy changing. This
        is what surfaces that. Shape:
            {ok, reachable, authenticated, competing, account_id, paper, detail}
        """
        out = {
            "ok": False, "reachable": False, "authenticated": False,
            "competing": False, "account_id": self._account,
            "paper": is_paper_account(self._account), "detail": "",
        }
        if not self._has_credentials():
            out["detail"] = "gateway URL or account id not configured"
            return out
        try:
            async with self._client() as client:
                resp = await client.get(f"{self._base}/iserver/auth/status")
        except httpx.RequestError as exc:
            out["detail"] = f"gateway unreachable: {exc}"
            return out

        out["reachable"] = True
        if resp.status_code != 200:
            out["detail"] = f"auth status returned HTTP {resp.status_code}"
            return out
        try:
            body = resp.json()
        except Exception:  # noqa: BLE001
            out["detail"] = "auth status was not JSON"
            return out
        if not isinstance(body, dict):
            out["detail"] = "unexpected auth status payload"
            return out

        out["authenticated"] = bool(body.get("authenticated"))
        # "competing" means another session grabbed the account — orders from
        # this one will be refused, so it is not healthy even if authenticated.
        out["competing"] = bool(body.get("competing"))
        out["ok"] = out["authenticated"] and not out["competing"]
        if not out["authenticated"]:
            out["detail"] = "gateway session is not authenticated — log in to the Client Portal Gateway again"
        elif out["competing"]:
            out["detail"] = "another session is competing for this account"
        return out

    async def reauthenticate(self) -> bool:
        """Ask the gateway to refresh a lapsed session. Only works while the
        gateway still holds valid cookies; a fully expired login needs a human."""
        if not self._has_credentials():
            return False
        try:
            async with self._client() as client:
                resp = await client.post(f"{self._base}/iserver/reauthenticate", json={})
            return resp.status_code == 200
        except httpx.RequestError as exc:
            _logger.warning("[IBKRBroker] reauthenticate failed: %s", exc)
            return False

    async def cancel_order(self, broker_order_id: str) -> bool:
        if not self._has_credentials():
            return False
        try:
            async with self._client() as client:
                resp = await client.delete(
                    f"{self._base}/iserver/account/{self._account}/order/{broker_order_id}"
                )
            return resp.status_code == 200
        except httpx.RequestError as exc:
            _logger.warning("[IBKRBroker] cancel failed for %s: %s", broker_order_id, exc)
            return False

    async def get_broker_positions(self) -> list[dict]:
        if not self._has_credentials():
            return []
        try:
            async with self._client() as client:
                resp = await client.get(f"{self._base}/portfolio/{self._account}/positions/0")
            if resp.status_code != 200:
                return []
            rows = resp.json()
        except httpx.RequestError as exc:
            _logger.warning("[IBKRBroker] positions fetch failed: %s", exc)
            return []
        if not isinstance(rows, list):
            return []
        out: list[dict] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            qty = float(row.get("position") or 0)
            if qty == 0:
                continue
            out.append({
                "symbol": row.get("contractDesc") or row.get("ticker") or "",
                "qty": abs(qty),
                "side": "long" if qty > 0 else "short",
            })
        return out


def _error_text(resp: httpx.Response) -> str:
    """Human-readable failure text for a non-2xx gateway response.

    The common real failure is an expired session, and CPAPI signals that with
    a bare 401 and an empty body — so falling back to resp.text alone yields
    nothing and the user is told only "rejected". Always name the status, and
    say plainly when it is an auth problem they can fix.
    """
    detail = ""
    try:
        body = resp.json()
        if isinstance(body, dict):
            detail = str(body.get("error") or body.get("message") or body)
        else:
            detail = str(body)
    except Exception:  # noqa: BLE001
        detail = (resp.text or "").strip()

    if resp.status_code in (401, 403):
        return (f"gateway rejected the request as unauthorised (HTTP {resp.status_code}) — "
                f"the Client Portal Gateway session has most likely expired; log in again"
                + (f": {detail}" if detail else ""))
    if detail:
        return f"HTTP {resp.status_code}: {detail}"
    return f"gateway returned HTTP {resp.status_code} with no detail"
