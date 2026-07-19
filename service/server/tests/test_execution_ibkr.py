"""IBKRBroker over the Client Portal Web API.

The load-bearing test here is the shadow guard. Alpaca and Binance separate
paper from live by HOSTNAME, so execution/gateway.py can pin shadow to the
sandbox. IBKR has one API and the ACCOUNT decides whether real money moves, so
the adapter has to refuse a shadow order on a live account itself.
"""
from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _order(symbol: str = "AAPL", side: str = "buy", qty: float = 3):
    from execution.base import Order
    return Order(agent_id=1, symbol=symbol, market="us-stock", side=side,
                 quantity=qty, price=190.0)


class _FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class _FakeClient:
    """Stands in for httpx.AsyncClient, recording calls and replaying scripted
    responses keyed by URL suffix."""

    def __init__(self, routes: dict, recorder: list):
        self._routes = routes
        self._recorder = recorder

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def _match(self, url: str) -> _FakeResponse:
        for suffix, resp in self._routes.items():
            if suffix in url:
                return resp() if callable(resp) else resp
        return _FakeResponse(404, {"error": "no route"})

    async def post(self, url, json=None, **kw):
        self._recorder.append(("POST", url, json))
        return self._match(url)

    async def get(self, url, **kw):
        self._recorder.append(("GET", url, None))
        return self._match(url)

    async def delete(self, url, **kw):
        self._recorder.append(("DELETE", url, None))
        return self._match(url)


class TestPaperAccountDetection(unittest.TestCase):
    def test_d_prefix_is_paper(self):
        from execution.ibkr import is_paper_account
        self.assertTrue(is_paper_account("DU1234567"))
        self.assertTrue(is_paper_account("du1234567"))

    def test_plain_u_account_is_live(self):
        from execution.ibkr import is_paper_account
        self.assertFalse(is_paper_account("U1234567"))

    def test_blank_is_not_paper(self):
        from execution.ibkr import is_paper_account
        self.assertFalse(is_paper_account(""))
        self.assertFalse(is_paper_account(None))


class TestGuards(unittest.TestCase):
    def test_unconfigured_gateway_is_rejected(self):
        from execution.base import OrderStatus
        from execution.ibkr import IBKRBroker
        result = _run(IBKRBroker().submit_order(_order()))
        self.assertEqual(result.status, OrderStatus.REJECTED)
        self.assertIn("not configured", result.error_message)

    def test_shadow_on_a_live_account_is_refused(self):
        """The whole point: a shadow order must never reach a live IBKR account."""
        from execution.base import OrderStatus
        from execution.ibkr import IBKRBroker
        calls: list = []
        broker = IBKRBroker(gateway_url="https://gw:5000/v1/api",
                            account_id="U1234567", paper=True)
        with patch.object(broker, "_client",
                          return_value=_FakeClient({}, calls)):
            result = _run(broker.submit_order(_order()))
        self.assertEqual(result.status, OrderStatus.REJECTED)
        self.assertIn("not a paper account", result.error_message)
        self.assertEqual(calls, [], "no request may be sent to the gateway")

    def test_shadow_on_a_paper_account_is_allowed(self):
        from execution.base import OrderStatus
        from execution.ibkr import IBKRBroker
        calls: list = []
        routes = {
            "/iserver/secdef/search": _FakeResponse(200, [{"conid": 265598}]),
            "/orders": _FakeResponse(200, [{"order_id": "IB-1", "order_status": "Submitted"}]),
        }
        broker = IBKRBroker(gateway_url="https://gw:5000/v1/api",
                            account_id="DU1234567", paper=True)
        with patch.object(broker, "_client", return_value=_FakeClient(routes, calls)):
            result = _run(broker.submit_order(_order()))
        self.assertEqual(result.status, OrderStatus.SUBMITTED)
        self.assertEqual(result.broker_order_id, "IB-1")

    def test_live_on_a_live_account_is_allowed(self):
        from execution.base import OrderStatus
        from execution.ibkr import IBKRBroker
        calls: list = []
        routes = {
            "/iserver/secdef/search": _FakeResponse(200, [{"conid": 265598}]),
            "/orders": _FakeResponse(200, [{"order_id": "IB-9", "order_status": "Filled"}]),
        }
        broker = IBKRBroker(gateway_url="https://gw:5000/v1/api",
                            account_id="U1234567", paper=False)
        with patch.object(broker, "_client", return_value=_FakeClient(routes, calls)):
            result = _run(broker.submit_order(_order()))
        self.assertEqual(result.status, OrderStatus.FILLED)
        self.assertEqual(result.broker_order_id, "IB-9")


class TestSubmitOrder(unittest.TestCase):
    def _broker(self):
        from execution.ibkr import IBKRBroker
        return IBKRBroker(gateway_url="https://gw:5000/v1/api",
                          account_id="DU1", paper=True)

    def test_unknown_symbol_is_rejected_before_ordering(self):
        from execution.base import OrderStatus
        calls: list = []
        routes = {"/iserver/secdef/search": _FakeResponse(200, [])}
        broker = self._broker()
        with patch.object(broker, "_client", return_value=_FakeClient(routes, calls)):
            result = _run(broker.submit_order(_order(symbol="NOPE")))
        self.assertEqual(result.status, OrderStatus.REJECTED)
        self.assertIn("no IBKR contract", result.error_message)
        self.assertFalse(any("/orders" in c[1] for c in calls))

    def test_order_payload_uses_conid_and_mapped_side(self):
        calls: list = []
        routes = {
            "/iserver/secdef/search": _FakeResponse(200, [{"conid": 265598}]),
            "/orders": _FakeResponse(200, [{"order_id": "X", "order_status": "Submitted"}]),
        }
        broker = self._broker()
        with patch.object(broker, "_client", return_value=_FakeClient(routes, calls)):
            _run(broker.submit_order(_order(side="short", qty=2)))
        order_call = next(c for c in calls if "/orders" in c[1])
        payload = order_call[2]["orders"][0]
        self.assertEqual(payload["conid"], 265598)
        self.assertEqual(payload["side"], "SELL")   # short maps to SELL
        self.assertEqual(payload["orderType"], "MKT")
        self.assertEqual(payload["quantity"], 2)

    def test_confirmation_prompt_is_answered(self):
        """CPAPI answers a submit with a question instead of an order id; the
        order is not live until that is confirmed."""
        from execution.base import OrderStatus
        calls: list = []
        replies = iter([
            _FakeResponse(200, [{"id": "q1", "message": ["Exceeds size threshold"]}]),
            _FakeResponse(200, [{"order_id": "IB-42", "order_status": "Submitted"}]),
        ])
        routes = {
            "/iserver/secdef/search": _FakeResponse(200, [{"conid": 1}]),
            "/orders": lambda: next(replies),
            "/iserver/reply/": lambda: next(replies),
        }
        broker = self._broker()
        with patch.object(broker, "_client", return_value=_FakeClient(routes, calls)):
            result = _run(broker.submit_order(_order()))
        self.assertEqual(result.status, OrderStatus.SUBMITTED)
        self.assertEqual(result.broker_order_id, "IB-42")
        self.assertTrue(any("/iserver/reply/q1" in c[1] for c in calls))

    def test_gateway_error_is_reported_not_raised(self):
        from execution.base import OrderStatus
        calls: list = []
        routes = {
            "/iserver/secdef/search": _FakeResponse(200, [{"conid": 1}]),
            "/orders": _FakeResponse(500, {"error": "gateway exploded"}),
        }
        broker = self._broker()
        with patch.object(broker, "_client", return_value=_FakeClient(routes, calls)):
            result = _run(broker.submit_order(_order()))
        self.assertEqual(result.status, OrderStatus.REJECTED)
        self.assertIn("gateway exploded", result.error_message)

    def test_unreachable_gateway_is_reported_not_raised(self):
        import httpx
        from execution.base import OrderStatus

        class _Boom:
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False
            async def post(self, *a, **k): raise httpx.ConnectError("refused")
        broker = self._broker()
        with patch.object(broker, "_client", return_value=_Boom()):
            result = _run(broker.submit_order(_order()))
        self.assertEqual(result.status, OrderStatus.REJECTED)
        self.assertIn("gateway unreachable", result.error_message)


class TestPositions(unittest.TestCase):
    def test_positions_are_normalised_and_zero_rows_dropped(self):
        from execution.ibkr import IBKRBroker
        calls: list = []
        routes = {"/positions/0": _FakeResponse(200, [
            {"contractDesc": "AAPL", "position": 10},
            {"contractDesc": "TSLA", "position": -4},
            {"contractDesc": "MSFT", "position": 0},
        ])}
        broker = IBKRBroker(gateway_url="https://gw/v1/api", account_id="DU1")
        with patch.object(broker, "_client", return_value=_FakeClient(routes, calls)):
            rows = _run(broker.get_broker_positions())
        self.assertEqual(rows, [
            {"symbol": "AAPL", "qty": 10.0, "side": "long"},
            {"symbol": "TSLA", "qty": 4.0, "side": "short"},
        ])


class TestRouterWiring(unittest.TestCase):
    def test_router_builds_ibkr_from_the_stored_blob(self):
        from execution.router import _build_real_broker
        from execution.crypto import encrypt_credentials
        account = {
            "agent_id": 1, "broker": "ibkr", "execution_mode": "live",
            "credentials_enc": encrypt_credentials({
                "gateway_url": "https://gw:5000/v1/api",
                "account_id": "U777",
                "allow_self_signed": True,
            }),
        }
        broker = _build_real_broker(account)
        self.assertEqual(broker.broker_name, "ibkr")
        self.assertEqual(broker._account, "U777")
        self.assertFalse(broker._paper)      # execution_mode live
        self.assertFalse(broker._verify)     # allow_self_signed honoured

    def test_shadow_mode_builds_a_paper_ibkr_broker(self):
        from execution.base import ExecutionMode
        from execution.gateway import _broker_for
        from execution.crypto import encrypt_credentials
        account = {
            "agent_id": 1, "broker": "ibkr", "execution_mode": "live",
            "credentials_enc": encrypt_credentials({
                "gateway_url": "https://gw:5000/v1/api", "account_id": "U777",
            }),
        }
        broker = _broker_for(account, ExecutionMode.SHADOW)
        self.assertTrue(broker._paper,
                        "shadow must build a paper-intent IBKR broker even when "
                        "the stored account row says live")


if __name__ == "__main__":
    unittest.main()


class TestSessionStatus(unittest.TestCase):
    """CPAPI sessions expire, so a live rule can stop filling with nothing on
    our side having changed. session_status is what surfaces that."""

    def _broker(self, account="DU1"):
        from execution.ibkr import IBKRBroker
        return IBKRBroker(gateway_url="https://gw:5000/v1/api", account_id=account)

    def test_unconfigured_reports_not_ok(self):
        from execution.ibkr import IBKRBroker
        st = _run(IBKRBroker().session_status())
        self.assertFalse(st["ok"])
        self.assertFalse(st["reachable"])
        self.assertIn("not configured", st["detail"])

    def test_authenticated_session_is_ok(self):
        routes = {"/iserver/auth/status": _FakeResponse(200, {"authenticated": True, "competing": False})}
        broker = self._broker()
        with patch.object(broker, "_client", return_value=_FakeClient(routes, [])):
            st = _run(broker.session_status())
        self.assertTrue(st["ok"])
        self.assertTrue(st["reachable"])
        self.assertTrue(st["paper"])

    def test_expired_session_is_reported_with_guidance(self):
        routes = {"/iserver/auth/status": _FakeResponse(200, {"authenticated": False})}
        broker = self._broker()
        with patch.object(broker, "_client", return_value=_FakeClient(routes, [])):
            st = _run(broker.session_status())
        self.assertFalse(st["ok"])
        self.assertTrue(st["reachable"], "gateway answered, it is the SESSION that lapsed")
        self.assertIn("log in to the Client Portal Gateway", st["detail"])

    def test_competing_session_is_not_ok_even_when_authenticated(self):
        """Another session holding the account means our orders get refused."""
        routes = {"/iserver/auth/status": _FakeResponse(200, {"authenticated": True, "competing": True})}
        broker = self._broker()
        with patch.object(broker, "_client", return_value=_FakeClient(routes, [])):
            st = _run(broker.session_status())
        self.assertFalse(st["ok"])
        self.assertIn("competing", st["detail"])

    def test_unreachable_gateway_is_reported_not_raised(self):
        import httpx

        class _Boom:
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False
            async def get(self, *a, **k): raise httpx.ConnectError("refused")
        broker = self._broker()
        with patch.object(broker, "_client", return_value=_Boom()):
            st = _run(broker.session_status())
        self.assertFalse(st["ok"])
        self.assertFalse(st["reachable"])
        self.assertIn("unreachable", st["detail"])

    def test_live_account_is_flagged_as_not_paper(self):
        routes = {"/iserver/auth/status": _FakeResponse(200, {"authenticated": True})}
        broker = self._broker(account="U9999")
        with patch.object(broker, "_client", return_value=_FakeClient(routes, [])):
            st = _run(broker.session_status())
        self.assertFalse(st["paper"])


class TestErrorText(unittest.TestCase):
    """An expired session is the commonest live failure and CPAPI signals it
    with a bare 401, so the message must not degrade to just "rejected"."""

    def test_401_names_the_expired_session(self):
        from execution.ibkr import _error_text
        msg = _error_text(_FakeResponse(401, None, text=""))
        self.assertIn("401", msg)
        self.assertIn("session has most likely expired", msg)

    def test_403_is_treated_the_same(self):
        from execution.ibkr import _error_text
        self.assertIn("expired", _error_text(_FakeResponse(403, None, text="")))

    def test_empty_body_still_names_the_status(self):
        from execution.ibkr import _error_text
        self.assertIn("HTTP 500", _error_text(_FakeResponse(500, None, text="")))

    def test_json_detail_is_surfaced_with_status(self):
        from execution.ibkr import _error_text
        msg = _error_text(_FakeResponse(400, {"error": "bad conid"}))
        self.assertIn("bad conid", msg)
        self.assertIn("400", msg)

    def test_submit_surfaces_the_expiry_message(self):
        from execution.base import OrderStatus
        from execution.ibkr import IBKRBroker
        routes = {
            "/iserver/secdef/search": _FakeResponse(200, [{"conid": 1}]),
            "/orders": _FakeResponse(401, None, text=""),
        }
        broker = IBKRBroker(gateway_url="https://gw/v1/api", account_id="DU1", paper=True)
        with patch.object(broker, "_client", return_value=_FakeClient(routes, [])):
            result = _run(broker.submit_order(_order()))
        self.assertEqual(result.status, OrderStatus.REJECTED)
        self.assertIn("expired", result.error_message)
