"""Plan 19 — regional venue adapters + gateway rails.

Contract under test, per adapter: reject-without-credentials, never raise on
expected errors, correct symbol mapping, and the two silent-100x traps (a
market BUY sized in quote currency instead of base). Gateway rails: the live
allowlist refuses (never downgrades), the new-venue notional cap refuses
(never resizes), journal shadow makes NO network call, and dry-run shadow
records accepted/rejected — never a fake fill.

All HTTP is faked by patching httpx.AsyncClient; any request the test did not
expect fails the test (a mocked suite must not quietly hit live venues).
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
from routes_shared import utc_now_iso_z


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ── HTTP fake ─────────────────────────────────────────────────────────────────

class _FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text or (json.dumps(payload) if payload is not None else "")

    def json(self):
        if self._payload is None:
            raise ValueError("no json body")
        return self._payload


class _FakeClient:
    """Stands in for httpx.AsyncClient. `responder(method, url, kwargs)` maps a
    request to a _FakeResponse; anything unexpected raises AssertionError so a
    missing mock can never fall through to a live venue."""

    def __init__(self, responder, calls):
        self._responder = responder
        self._calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def _do(self, method, url, **kwargs):
        self._calls.append((method, url, kwargs))
        resp = self._responder(method, url, kwargs)
        if resp is None:
            raise AssertionError(f"unexpected {method} {url}")
        if isinstance(resp, Exception):
            raise resp
        return resp

    async def get(self, url, **kwargs):
        return await self._do("GET", url, **kwargs)

    async def post(self, url, **kwargs):
        return await self._do("POST", url, **kwargs)

    async def delete(self, url, **kwargs):
        return await self._do("DELETE", url, **kwargs)


def _patch_http(responder):
    """Patch httpx.AsyncClient with a fake; returns (patcher, calls list)."""
    calls: list = []
    patcher = patch("httpx.AsyncClient",
                    lambda *a, **kw: _FakeClient(responder, calls))
    return patcher, calls


def _mk_order(symbol="BTCUSDT", side="buy", qty=0.5, price=100.0):
    from execution.base import Order
    return Order(agent_id=1, symbol=symbol, market="crypto", side=side,
                 quantity=qty, price=price)


def _make_ec_pem() -> str:
    """A throwaway P-256 key. Coinbase signs with ES256, so its adapter cannot
    be exercised with a string stand-in the way the HMAC venues can."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    return ec.generate_private_key(ec.SECP256R1()).private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()


_EC_PEM = _make_ec_pem()


def _new_adapters():
    from execution.bybit import BybitBroker
    from execution.coinbase import CoinbaseBroker
    from execution.cryptocom import CryptocomBroker
    from execution.kraken import KrakenBroker
    from execution.kucoin import KucoinBroker
    from execution.okx import OKXBroker
    from execution.upbit import UpbitBroker
    return [
        BybitBroker(key="", secret=""),
        OKXBroker(key="", secret="", passphrase=""),
        KrakenBroker(key="", secret=""),
        CryptocomBroker(key="", secret=""),
        UpbitBroker(key="", secret=""),
        KucoinBroker(key="", secret="", passphrase=""),
        CoinbaseBroker(key="", secret=""),
    ]


# ── Adapter contract ──────────────────────────────────────────────────────────

class VenueContractTests(unittest.TestCase):
    def test_no_credentials_rejects_without_network(self):
        patcher, calls = _patch_http(lambda m, u, k: None)
        with patcher:
            for adapter in _new_adapters():
                from execution.base import OrderStatus
                order = _run(adapter.submit_order(_mk_order()))
                self.assertIs(order.status, OrderStatus.REJECTED, adapter.broker_name)
                self.assertIn("not configured", order.error_message or "",
                              adapter.broker_name)
        self.assertEqual(calls, [], "credential-less submit must not touch the network")

    def test_network_error_rejects_never_raises(self):
        import httpx
        from execution.base import OrderStatus
        from execution.bybit import BybitBroker
        from execution.coinbase import CoinbaseBroker
        from execution.kucoin import KucoinBroker
        from execution.okx import OKXBroker
        adapters = [BybitBroker(key="k", secret="s"),
                    OKXBroker(key="k", secret="s", passphrase="p"),
                    KucoinBroker(key="k", secret="s", passphrase="p"),
                    CoinbaseBroker(key="kn", secret=_EC_PEM)]
        patcher, _ = _patch_http(
            lambda m, u, k: httpx.ConnectError("boom", request=None))
        with patcher:
            for adapter in adapters:
                order = _run(adapter.submit_order(_mk_order()))
                self.assertIs(order.status, OrderStatus.REJECTED, adapter.broker_name)
                self.assertIn("network error", order.error_message or "")

    def test_status_lookup_none_credentials(self):
        patcher, calls = _patch_http(lambda m, u, k: None)
        with patcher:
            for adapter in _new_adapters():
                self.assertIsNone(_run(adapter.get_order_status("x", symbol="BTCUSDT")),
                                  adapter.broker_name)
        self.assertEqual(calls, [])

    def test_symbol_mappers(self):
        from execution.bybit import BybitBroker
        from execution.cryptocom import CryptocomBroker
        from execution.kraken import KrakenBroker
        from execution.kucoin import KucoinBroker
        from execution.okx import OKXBroker
        from execution.upbit import UpbitBroker
        self.assertEqual(BybitBroker._pair("BTC/USDT"), "BTCUSDT")
        self.assertEqual(OKXBroker._inst_id("BTCUSDT"), "BTC-USDT")
        self.assertEqual(KrakenBroker._pair("BTCUSDT"), "XBTUSDT")
        self.assertEqual(KrakenBroker._pair("BTC"), "XBTUSD")
        self.assertEqual(KrakenBroker._pair("ETHUSD"), "ETHUSD")
        self.assertEqual(CryptocomBroker._instrument("SOLUSDT"), "SOL_USDT")
        self.assertEqual(UpbitBroker._market("BTCUSDT"), "KRW-BTC")
        self.assertEqual(KucoinBroker._pair("XRPUSDT"), "XRP-USDT")


class BuyUnitPinningTests(unittest.TestCase):
    """A spot market BUY sized in quote currency instead of base spends
    `quantity` dollars instead of buying `quantity` coins. These assertions
    are the regression guard for that silent-100x class."""

    def test_bybit_pins_base_coin(self):
        from execution.bybit import BybitBroker
        patcher, calls = _patch_http(
            lambda m, u, k: _FakeResponse(200, {"retCode": 0, "result": {"orderId": "1"}}))
        with patcher:
            _run(BybitBroker(key="k", secret="s").submit_order(_mk_order()))
        body = json.loads(calls[0][2]["content"])
        self.assertEqual(body["marketUnit"], "baseCoin")
        self.assertEqual(body["qty"], "0.50000000")

    def test_okx_pins_base_ccy(self):
        from execution.okx import OKXBroker
        patcher, calls = _patch_http(
            lambda m, u, k: _FakeResponse(200, {"code": "0", "data": [{"sCode": "0", "ordId": "1"}]}))
        with patcher:
            _run(OKXBroker(key="k", secret="s", passphrase="p").submit_order(_mk_order()))
        body = json.loads(calls[0][2]["content"])
        self.assertEqual(body["tgtCcy"], "base_ccy")
        self.assertEqual(body["tdMode"], "cash")


class UpbitOrderShapeTests(unittest.TestCase):
    """Upbit market buys are KRW-cost orders; sells are volume orders. Flipping
    the mapping submits nonsense — these tests fail if ord_type ever swaps."""

    @staticmethod
    def _responder(m, u, k):
        if u.endswith("/ticker"):
            return _FakeResponse(200, [{"trade_price": 1400.0}])
        if u.endswith("/orders"):
            return _FakeResponse(201, {"uuid": "u-1"})
        return None

    def test_market_buy_is_priced_in_krw_cost(self):
        from execution.upbit import UpbitBroker
        patcher, calls = _patch_http(self._responder)
        with patcher:
            order = _run(UpbitBroker(key="k", secret="s").submit_order(
                _mk_order(side="buy", qty=0.5, price=100.0)))
        params = calls[-1][2]["data"]
        self.assertEqual(params["ord_type"], "price")
        self.assertEqual(params["side"], "bid")
        # 0.5 * $100 * 1400 KRW/USD = 70,000 KRW, whole won
        self.assertEqual(params["price"], "70000")
        self.assertNotIn("volume", params)
        self.assertEqual(order.quote_currency, "KRW")
        self.assertEqual(order.fx_rate_usd, 1400.0)

    def test_market_sell_is_volume(self):
        from execution.upbit import UpbitBroker
        patcher, calls = _patch_http(self._responder)
        with patcher:
            _run(UpbitBroker(key="k", secret="s").submit_order(
                _mk_order(side="sell", qty=0.5, price=100.0)))
        params = calls[-1][2]["data"]
        self.assertEqual(params["ord_type"], "market")
        self.assertEqual(params["side"], "ask")
        self.assertEqual(params["volume"], "0.50000000")
        self.assertNotIn("price", params)

    def test_missing_fx_rate_refuses_order(self):
        from execution.base import OrderStatus
        from execution.upbit import UpbitBroker

        def responder(m, u, k):
            if u.endswith("/ticker"):
                return _FakeResponse(500, {"error": {"message": "down"}})
            return None  # the order endpoint must never be reached

        patcher, _ = _patch_http(responder)
        with patcher:
            order = _run(UpbitBroker(key="k", secret="s").submit_order(_mk_order()))
        self.assertIs(order.status, OrderStatus.REJECTED)
        self.assertIn("KRW/USD rate", order.error_message)


class SignatureTests(unittest.TestCase):
    def test_kraken_signature_documented_vector(self):
        """Kraken's published API-Sign example — an external truth this
        implementation must reproduce byte-for-byte."""
        from execution.kraken import KrakenBroker
        secret = ("kQH5HW/8p1uGOVjbgWA7FunAmGO8lsSUXNsu3eow76sz84Q18fWxnyRz"
                  "BHCd3pd5nE9qa99HAZtuZuj6F1huXg==")
        broker = KrakenBroker(key="key", secret=secret, validate_only=False)
        params = {
            "ordertype": "limit", "pair": "XBTUSD", "price": "37500",
            "type": "buy", "volume": "1.25", "nonce": "1616492376594",
        }
        # urlencode order matters: reproduce the documented postdata exactly.
        postdata, headers = broker._sign("/0/private/AddOrder", dict(
            nonce="1616492376594", ordertype="limit", pair="XBTUSD",
            price="37500", type="buy", volume="1.25"))
        del params
        self.assertEqual(
            headers["API-Sign"],
            "4/dpxb3iT4tp/ZCVEwSnEsLxx0bqyhLpdfOpc6fn7OR8+U"
            "ClSV5n9E6aSS8MPtnRfp32bAb0nmbRn6H8ndwLUQ==",
        )

    def test_bybit_signature_shape(self):
        from execution.bybit import BybitBroker
        b = BybitBroker(key="api-key", secret="secret")
        headers = b._headers('{"a":"1"}')
        ts = headers["X-BAPI-TIMESTAMP"]
        expected = hmac.new(b"secret", (ts + "api-key" + "5000" + '{"a":"1"}').encode(),
                            hashlib.sha256).hexdigest()
        self.assertEqual(headers["X-BAPI-SIGN"], expected)

    def test_okx_signature_shape(self):
        from execution.okx import OKXBroker
        b = OKXBroker(key="k", secret="secret", passphrase="p")
        headers = b._headers("POST", "/api/v5/trade/order", "{}")
        ts = headers["OK-ACCESS-TIMESTAMP"]
        expected = base64.b64encode(hmac.new(
            b"secret", (ts + "POST" + "/api/v5/trade/order" + "{}").encode(),
            hashlib.sha256).digest()).decode()
        self.assertEqual(headers["OK-ACCESS-SIGN"], expected)
        self.assertTrue(ts.endswith("Z") and "T" in ts)

    def test_kucoin_v2_passphrase_is_encrypted(self):
        from execution.kucoin import KucoinBroker
        b = KucoinBroker(key="k", secret="secret", passphrase="pass")
        headers = b._headers("GET", "/api/v1/accounts")
        self.assertNotEqual(headers["KC-API-PASSPHRASE"], "pass",
                            "v2 keys must never transmit the raw passphrase")
        expected = base64.b64encode(hmac.new(b"secret", b"pass",
                                             hashlib.sha256).digest()).decode()
        self.assertEqual(headers["KC-API-PASSPHRASE"], expected)
        self.assertEqual(headers["KC-API-KEY-VERSION"], "2")

    def test_upbit_jwt_query_hash(self):
        from execution.upbit import UpbitBroker
        b = UpbitBroker(key="ak", secret="sk")
        token = b._jwt({"market": "KRW-BTC", "side": "bid"})
        header_b64, payload_b64, sig_b64 = token.split(".")
        pad = lambda s: s + "=" * (-len(s) % 4)  # noqa: E731
        payload = json.loads(base64.urlsafe_b64decode(pad(payload_b64)))
        self.assertEqual(payload["access_key"], "ak")
        self.assertEqual(payload["query_hash_alg"], "SHA512")
        expected_hash = hashlib.sha512(b"market=KRW-BTC&side=bid").hexdigest()
        self.assertEqual(payload["query_hash"], expected_hash)
        expected_sig = base64.urlsafe_b64encode(hmac.new(
            b"sk", f"{header_b64}.{payload_b64}".encode(),
            hashlib.sha256).digest()).rstrip(b"=").decode()
        self.assertEqual(sig_b64, expected_sig)

    def test_cryptocom_signature_shape(self):
        from execution.cryptocom import CryptocomBroker
        b = CryptocomBroker(key="ak", secret="sk")
        env = b._envelope("private/create-order",
                          {"instrument_name": "BTC_USDT", "side": "BUY"})
        params_str = "instrument_nameBTC_USDTsideBUY"
        payload = (f"private/create-order{env['id']}ak{params_str}{env['nonce']}")
        expected = hmac.new(b"sk", payload.encode(), hashlib.sha256).hexdigest()
        self.assertEqual(env["sig"], expected)


# ── Kraken validate-only dry-run ──────────────────────────────────────────────

class KrakenDryRunTests(unittest.TestCase):
    def test_validate_true_sent_and_validated_status(self):
        from execution.base import OrderStatus
        from execution.kraken import KrakenBroker
        patcher, calls = _patch_http(
            lambda m, u, k: _FakeResponse(200, {"error": [], "result": {"descr": {}}}))
        with patcher:
            order = _run(KrakenBroker(key="k", secret=base64.b64encode(b"s").decode(),
                                      validate_only=True).submit_order(_mk_order()))
        self.assertIs(order.status, OrderStatus.VALIDATED)
        sent = parse_qs(calls[0][2]["content"])
        self.assertEqual(sent["validate"], ["true"])
        self.assertEqual(sent["pair"], ["XBTUSDT"])

    def test_live_mode_does_not_send_validate(self):
        from execution.base import OrderStatus
        from execution.kraken import KrakenBroker
        patcher, calls = _patch_http(
            lambda m, u, k: _FakeResponse(200, {"error": [], "result": {"txid": ["T1"]}}))
        with patcher:
            order = _run(KrakenBroker(key="k", secret=base64.b64encode(b"s").decode(),
                                      validate_only=False).submit_order(_mk_order()))
        self.assertIs(order.status, OrderStatus.SUBMITTED)
        self.assertEqual(order.broker_order_id, "T1")
        sent = parse_qs(calls[0][2]["content"])
        self.assertNotIn("validate", sent)


class KucoinDryRunTests(unittest.TestCase):
    def test_test_endpoint_and_validated_status(self):
        from execution.base import OrderStatus
        from execution.kucoin import KucoinBroker
        patcher, calls = _patch_http(
            lambda m, u, k: _FakeResponse(200, {"code": "200000", "data": {}}))
        with patcher:
            order = _run(KucoinBroker(key="k", secret="s", passphrase="p",
                                      test_only=True).submit_order(_mk_order()))
        self.assertIs(order.status, OrderStatus.VALIDATED)
        self.assertTrue(calls[0][1].endswith("/api/v1/orders/test"))

    def test_live_uses_real_endpoint(self):
        from execution.base import OrderStatus
        from execution.kucoin import KucoinBroker
        patcher, calls = _patch_http(
            lambda m, u, k: _FakeResponse(200, {"code": "200000", "data": {"orderId": "o1"}}))
        with patcher:
            order = _run(KucoinBroker(key="k", secret="s", passphrase="p",
                                      test_only=False).submit_order(_mk_order()))
        self.assertIs(order.status, OrderStatus.SUBMITTED)
        self.assertTrue(calls[0][1].endswith("/api/v1/orders"))


class CoinbaseTests(unittest.TestCase):
    """Coinbase is the only venue that signs with a per-request ES256 JWT
    instead of an HMAC, and the only one whose books are USD- not USDT-quoted.
    Both are places a wrong assumption is silent rather than loud."""

    def test_product_maps_usdt_onto_usd(self):
        from execution.coinbase import CoinbaseBroker
        # The crypto feed quotes USDT; Coinbase's book is USD. Getting this
        # wrong asks for a product Coinbase does not list.
        self.assertEqual(CoinbaseBroker._product("BTCUSDT"), "BTC-USD")
        self.assertEqual(CoinbaseBroker._product("ETHUSDC"), "ETH-USD")
        self.assertEqual(CoinbaseBroker._product("SOLUSD"), "SOL-USD")
        self.assertEqual(CoinbaseBroker._product("BTC"), "BTC-USD")

    def test_preview_endpoint_and_validated_status(self):
        from execution.base import OrderStatus
        from execution.coinbase import CoinbaseBroker
        patcher, calls = _patch_http(lambda m, u, k: _FakeResponse(200, {"errs": []}))
        with patcher:
            order = _run(CoinbaseBroker(key="kn", secret=_EC_PEM,
                                        preview_only=True).submit_order(_mk_order()))
        self.assertIs(order.status, OrderStatus.VALIDATED)
        self.assertTrue(calls[0][1].endswith("/api/v3/brokerage/orders/preview"))
        # A dry run must never invent a broker order id.
        self.assertIsNone(order.broker_order_id)

    def test_preview_errs_reject_never_validate(self):
        from execution.base import OrderStatus
        from execution.coinbase import CoinbaseBroker
        patcher, _ = _patch_http(
            lambda m, u, k: _FakeResponse(200, {"errs": ["INSUFFICIENT_FUND"]}))
        with patcher:
            order = _run(CoinbaseBroker(key="kn", secret=_EC_PEM,
                                        preview_only=True).submit_order(_mk_order()))
        self.assertIs(order.status, OrderStatus.REJECTED)
        self.assertIn("INSUFFICIENT_FUND", order.error_message or "")

    def test_preview_sends_no_client_order_id(self):
        # The preview endpoint rejects a client_order_id outright.
        from execution.coinbase import CoinbaseBroker
        patcher, calls = _patch_http(lambda m, u, k: _FakeResponse(200, {"errs": []}))
        with patcher:
            _run(CoinbaseBroker(key="kn", secret=_EC_PEM,
                                preview_only=True).submit_order(_mk_order()))
        self.assertNotIn("client_order_id", json.loads(calls[0][2]["content"]))

    def test_live_uses_orders_endpoint_and_carries_client_order_id(self):
        from execution.base import OrderStatus
        from execution.coinbase import CoinbaseBroker
        patcher, calls = _patch_http(lambda m, u, k: _FakeResponse(
            200, {"success": True, "success_response": {"order_id": "o-1"}}))
        with patcher:
            order = _run(CoinbaseBroker(key="kn", secret=_EC_PEM,
                                        preview_only=False).submit_order(_mk_order()))
        self.assertIs(order.status, OrderStatus.SUBMITTED)
        self.assertEqual(order.broker_order_id, "o-1")
        self.assertTrue(calls[0][1].endswith("/api/v3/brokerage/orders"))
        self.assertTrue(json.loads(calls[0][2]["content"])["client_order_id"])

    def test_unsuccessful_create_is_rejected_with_reason(self):
        from execution.base import OrderStatus
        from execution.coinbase import CoinbaseBroker
        patcher, _ = _patch_http(lambda m, u, k: _FakeResponse(
            200, {"success": False,
                  "error_response": {"message": "INVALID_SIZE_PRECISION"}}))
        with patcher:
            order = _run(CoinbaseBroker(key="kn", secret=_EC_PEM,
                                        preview_only=False).submit_order(_mk_order()))
        self.assertIs(order.status, OrderStatus.REJECTED)
        self.assertIn("INVALID_SIZE_PRECISION", order.error_message or "")

    def test_pins_base_size_not_quote_size(self):
        """Same silent-100x trap as bybit/okx: a market BUY sized in USD
        instead of coins spends `quantity` dollars."""
        from execution.coinbase import CoinbaseBroker
        patcher, calls = _patch_http(lambda m, u, k: _FakeResponse(200, {"errs": []}))
        with patcher:
            _run(CoinbaseBroker(key="kn", secret=_EC_PEM,
                                preview_only=True).submit_order(_mk_order()))
        config = json.loads(calls[0][2]["content"])["order_configuration"]
        self.assertEqual(config["market_market_ioc"]["base_size"], "0.50000000")
        self.assertNotIn("quote_size", config["market_market_ioc"])

    def test_short_and_cover_map_onto_spot_sides(self):
        from execution.coinbase import CoinbaseBroker
        patcher, calls = _patch_http(lambda m, u, k: _FakeResponse(200, {"errs": []}))
        with patcher:
            for side, expected in (("buy", "BUY"), ("sell", "SELL"),
                                   ("short", "SELL"), ("cover", "BUY")):
                _run(CoinbaseBroker(key="kn", secret=_EC_PEM, preview_only=True)
                     .submit_order(_mk_order(side=side)))
                self.assertEqual(json.loads(calls[-1][2]["content"])["side"], expected)

    def test_jwt_binds_method_host_and_path(self):
        """The `uri` claim is what stops a token minted for a read being
        replayed against an order. Verify it against the real signature."""
        import jwt as _jwt
        from cryptography.hazmat.primitives import serialization
        from execution.coinbase import CoinbaseBroker
        header_value = CoinbaseBroker(key="kn", secret=_EC_PEM)._auth_header(
            "POST", "/api/v3/brokerage/orders")
        self.assertTrue(header_value.startswith("Bearer "))
        token = header_value.split(" ", 1)[1]
        public_key = serialization.load_pem_private_key(
            _EC_PEM.encode(), password=None).public_key()
        claims = _jwt.decode(token, public_key, algorithms=["ES256"],
                            options={"verify_aud": False})
        self.assertEqual(claims["uri"], "POST api.coinbase.com/api/v3/brokerage/orders")
        self.assertEqual(claims["iss"], "cdp")
        self.assertEqual(claims["sub"], "kn")
        # Short-lived by construction — a leaked token dies in two minutes.
        self.assertEqual(claims["exp"] - claims["nbf"], 120)
        headers = _jwt.get_unverified_header(token)
        self.assertEqual(headers["kid"], "kn")
        self.assertEqual(headers["alg"], "ES256")
        self.assertTrue(headers["nonce"])

    def test_pem_with_escaped_newlines_still_loads(self):
        # A PEM that has been through a form and a JSON column often arrives
        # with its newlines escaped; that must not read as a bad key.
        from execution.coinbase import CoinbaseBroker
        escaped = _EC_PEM.replace("\n", "\\n")
        self.assertIsNotNone(
            CoinbaseBroker(key="kn", secret=escaped)._auth_header("GET", "/x"))

    def test_unusable_private_key_rejects_without_network(self):
        from execution.base import OrderStatus
        from execution.coinbase import CoinbaseBroker
        patcher, calls = _patch_http(lambda m, u, k: None)
        with patcher:
            order = _run(CoinbaseBroker(key="kn", secret="not-a-pem",
                                        preview_only=True).submit_order(_mk_order()))
        self.assertIs(order.status, OrderStatus.REJECTED)
        self.assertEqual(calls, [], "an unusable key must not reach the venue")

    def test_status_lookup_maps_venue_states(self):
        from execution.base import OrderStatus
        from execution.coinbase import CoinbaseBroker
        cases = {
            "FILLED": OrderStatus.FILLED,
            "CANCELLED": OrderStatus.CANCELLED,
            "EXPIRED": OrderStatus.CANCELLED,
            "FAILED": OrderStatus.REJECTED,
        }
        for venue_status, expected in cases.items():
            patcher, _ = _patch_http(lambda m, u, k, s=venue_status: _FakeResponse(
                200, {"order": {"status": s, "filled_size": "0.5",
                                "average_filled_price": "100"}}))
            with patcher:
                out = _run(CoinbaseBroker(key="kn", secret=_EC_PEM)
                           .get_order_status("o-1"))
            self.assertEqual(out["status"], expected, venue_status)
            self.assertEqual(out["filled_qty"], 0.5)
            self.assertEqual(out["avg_price"], 100.0)

    def test_open_with_partial_fill_is_partial_not_submitted(self):
        from execution.base import OrderStatus
        from execution.coinbase import CoinbaseBroker
        patcher, _ = _patch_http(lambda m, u, k: _FakeResponse(
            200, {"order": {"status": "OPEN", "filled_size": "0.2"}}))
        with patcher:
            out = _run(CoinbaseBroker(key="kn", secret=_EC_PEM).get_order_status("o-1"))
        self.assertIs(out["status"], OrderStatus.PARTIAL_FILL)

    def test_open_with_no_fill_is_submitted(self):
        from execution.base import OrderStatus
        from execution.coinbase import CoinbaseBroker
        patcher, _ = _patch_http(lambda m, u, k: _FakeResponse(
            200, {"order": {"status": "OPEN", "filled_size": "0"}}))
        with patcher:
            out = _run(CoinbaseBroker(key="kn", secret=_EC_PEM).get_order_status("o-1"))
        self.assertIs(out["status"], OrderStatus.SUBMITTED)


class USRegionTests(unittest.TestCase):
    def test_us_row_recommends_only_us_reachable_venues(self):
        """Without a US row the GLOBAL fallback recommends binance/bybit/okx,
        none of which a US person can open an account on."""
        from execution.base import REGION_VENUES
        self.assertIn("US", REGION_VENUES)
        for blocked in ("binance", "bybit", "okx"):
            self.assertNotIn(blocked, REGION_VENUES["US"])
        self.assertIn("coinbase", REGION_VENUES["US"])

    def test_coinbase_is_a_connectable_broker(self):
        from execution.base import AVAILABLE_BROKERS, BROKER_SPECS
        self.assertIn("coinbase", AVAILABLE_BROKERS)
        spec = BROKER_SPECS["coinbase"]
        self.assertEqual(spec.fields, ("key", "secret"))
        self.assertEqual(spec.shadow, "dry_run")
        # USD-quoted, so no FX capture is forced at fill recording.
        self.assertEqual(spec.quote, "USD")

    def test_router_builds_coinbase_with_mode_derived_preview_flag(self):
        from execution.coinbase import CoinbaseBroker
        from execution.router import _build_real_broker
        for mode, preview in (("shadow", True), ("live", False)):
            built = _build_real_broker({"broker": "coinbase", "credentials_enc": "",
                                        "execution_mode": mode, "agent_id": 1})
            self.assertIsInstance(built, CoinbaseBroker, mode)
            self.assertEqual(built._preview_only, preview, mode)


# ── Gateway rails (DB-backed) ─────────────────────────────────────────────────

def _create_agent(name="venue-agent", cash=100_000.0) -> int:
    import hashlib as _h
    conn = database.get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO agents (name, token, token_hash, cash) VALUES (?, NULL, ?, ?)",
        (name, _h.sha256(name.encode()).hexdigest(), cash),
    )
    agent_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return agent_id


def _add_account(agent_id, broker, creds: dict, mode="live") -> int:
    from execution.crypto import encrypt_credentials
    conn = database.get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO broker_accounts
           (agent_id, broker, execution_mode, credentials_enc, is_active, created_at, updated_at)
           VALUES (?,?,?,?,1,?,?)""",
        (agent_id, broker, mode, encrypt_credentials(creds),
         utc_now_iso_z(), utc_now_iso_z()),
    )
    account_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return account_id


def _accept_tcs(agent_id, broker) -> None:
    conn = database.get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO broker_live_optins
           (agent_id, broker, tcs_version, ip_address, user_agent, created_at)
           VALUES (?,?,?,?,?,?)""",
        (agent_id, broker, "v1", "127.0.0.1", "test", utc_now_iso_z()),
    )
    conn.commit()
    conn.close()


class _DbTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.agent_id = _create_agent()
        os.environ.pop("LIVE_BROKER_ALLOWLIST", None)
        os.environ.pop("EXECUTION_MAX_ORDER_USD", None)

    def tearDown(self):
        os.environ.pop("LIVE_BROKER_ALLOWLIST", None)
        os.environ.pop("EXECUTION_MAX_ORDER_USD", None)
        self.tmp.cleanup()


class AllowlistTests(_DbTestCase):
    def test_new_venue_live_refused_by_default(self):
        from execution.gateway import NOT_ALLOWLISTED, live_refusal_reason
        _add_account(self.agent_id, "bybit", {"key": "k", "secret": "s"})
        _accept_tcs(self.agent_id, "bybit")
        self.assertEqual(live_refusal_reason(self.agent_id, "live"), NOT_ALLOWLISTED)

    def test_allowlisted_venue_passes(self):
        from execution.gateway import live_refusal_reason
        _add_account(self.agent_id, "bybit", {"key": "k", "secret": "s"})
        _accept_tcs(self.agent_id, "bybit")
        os.environ["LIVE_BROKER_ALLOWLIST"] = "alpaca,binance,ibkr,bybit"
        self.assertIsNone(live_refusal_reason(self.agent_id, "live"))

    def test_legacy_broker_unaffected_by_default(self):
        from execution.gateway import live_refusal_reason
        _add_account(self.agent_id, "alpaca", {"key": "k", "secret": "s"})
        _accept_tcs(self.agent_id, "alpaca")
        self.assertIsNone(live_refusal_reason(self.agent_id, "live"))

    def test_empty_allowlist_is_kill_switch(self):
        from execution.gateway import NOT_ALLOWLISTED, live_refusal_reason
        _add_account(self.agent_id, "alpaca", {"key": "k", "secret": "s"})
        _accept_tcs(self.agent_id, "alpaca")
        os.environ["LIVE_BROKER_ALLOWLIST"] = ""
        self.assertEqual(live_refusal_reason(self.agent_id, "live"), NOT_ALLOWLISTED)

    def test_okx_without_passphrase_is_unusable(self):
        from execution.gateway import (NOT_CONFIGURED_NO_CREDS,
                                       live_refusal_reason)
        _add_account(self.agent_id, "okx", {"key": "k", "secret": "s"})
        _accept_tcs(self.agent_id, "okx")
        os.environ["LIVE_BROKER_ALLOWLIST"] = "okx"
        self.assertEqual(live_refusal_reason(self.agent_id, "live"),
                         NOT_CONFIGURED_NO_CREDS)

    def test_okx_with_passphrase_is_usable(self):
        from execution.gateway import live_refusal_reason
        _add_account(self.agent_id, "okx",
                     {"key": "k", "secret": "s", "passphrase": "p"})
        _accept_tcs(self.agent_id, "okx")
        os.environ["LIVE_BROKER_ALLOWLIST"] = "okx"
        self.assertIsNone(live_refusal_reason(self.agent_id, "live"))


class NotionalCapTests(_DbTestCase):
    def _submit(self, qty, price):
        from execution.gateway import submit_live
        return submit_live(self.agent_id, "BTCUSDT", "crypto", "buy", qty, price)

    def test_over_cap_refused_not_resized(self):
        from execution.base import OrderStatus
        _add_account(self.agent_id, "bybit", {"key": "k", "secret": "s"})
        os.environ["LIVE_BROKER_ALLOWLIST"] = "bybit"
        patcher, calls = _patch_http(lambda m, u, k: None)
        with patcher:
            order = self._submit(qty=1.0, price=2000.0)  # $2,000 > $1,000 default
        self.assertIs(order.status, OrderStatus.REJECTED)
        self.assertIn("per-order limit", order.error_message)
        self.assertEqual(order.quantity, 1.0, "cap must refuse, never resize")
        self.assertEqual(calls, [], "refused order must not reach the venue")

    def test_under_cap_reaches_venue(self):
        from execution.base import OrderStatus
        _add_account(self.agent_id, "bybit", {"key": "k", "secret": "s"})
        os.environ["LIVE_BROKER_ALLOWLIST"] = "bybit"
        patcher, calls = _patch_http(
            lambda m, u, k: _FakeResponse(200, {"retCode": 0, "result": {"orderId": "1"}}))
        with patcher:
            order = self._submit(qty=1.0, price=500.0)
        self.assertIs(order.status, OrderStatus.SUBMITTED)
        self.assertEqual(len(calls), 1)

    def test_legacy_broker_has_no_cap(self):
        from execution.base import OrderStatus
        _add_account(self.agent_id, "binance", {"key": "k", "secret": "s"})
        patcher, calls = _patch_http(
            lambda m, u, k: _FakeResponse(200, {"orderId": 9, "status": "FILLED",
                                                "executedQty": "1.0"}))
        with patcher:
            order = self._submit(qty=1.0, price=50_000.0)  # $50k, no cap
        self.assertIs(order.status, OrderStatus.FILLED)
        self.assertEqual(len(calls), 1)

    def test_non_allowlisted_submit_live_refused_at_source(self):
        from execution.base import OrderStatus
        _add_account(self.agent_id, "bybit", {"key": "k", "secret": "s"})
        patcher, calls = _patch_http(lambda m, u, k: None)
        with patcher:
            order = self._submit(qty=0.1, price=100.0)
        self.assertIs(order.status, OrderStatus.REJECTED)
        self.assertEqual(calls, [], "non-allowlisted venue must never be contacted")


class ShadowStrategyTests(_DbTestCase):
    def _shadow(self):
        from execution.gateway import submit_shadow
        return submit_shadow(self.agent_id, "BTCUSDT", "crypto", "buy",
                             0.5, 100.0, ledger_quantity=0.5, signal_id=None)

    def _recon_rows(self):
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM position_reconciliations WHERE agent_id=?",
                       (self.agent_id,))
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return rows

    def test_upbit_shadow_is_journal_only_no_network(self):
        _add_account(self.agent_id, "upbit", {"key": "k", "secret": "s"},
                     mode="shadow")
        patcher, calls = _patch_http(lambda m, u, k: None)
        with patcher:
            result = self._shadow()
        self.assertIsNone(result)
        self.assertEqual(calls, [], "journal shadow must make no network call")
        rows = self._recon_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "journal")
        self.assertEqual(rows[0]["broker"], "upbit")
        self.assertIsNone(rows[0]["broker_qty"])

    def test_kraken_shadow_dry_run_records_accepted(self):
        from execution.base import OrderStatus
        _add_account(self.agent_id, "kraken",
                     {"key": "k", "secret": base64.b64encode(b"s").decode()},
                     mode="shadow")
        patcher, calls = _patch_http(
            lambda m, u, k: _FakeResponse(200, {"error": [], "result": {"descr": {}}}))
        with patcher:
            order = self._shadow()
        self.assertIs(order.status, OrderStatus.VALIDATED)
        sent = parse_qs(calls[0][2]["content"])
        self.assertEqual(sent["validate"], ["true"])
        rows = self._recon_rows()
        self.assertEqual(rows[0]["status"], "accepted")

    def test_kraken_shadow_dry_run_records_rejected(self):
        _add_account(self.agent_id, "kraken",
                     {"key": "k", "secret": base64.b64encode(b"s").decode()},
                     mode="shadow")
        patcher, _ = _patch_http(
            lambda m, u, k: _FakeResponse(200, {"error": ["EGeneral:Invalid arguments"]}))
        with patcher:
            self._shadow()
        rows = self._recon_rows()
        self.assertEqual(rows[0]["status"], "rejected")

    def test_kraken_shadow_pins_validate_even_if_account_says_live(self):
        """Endpoint pinning: a shadow rule on an account flipped to live must
        still send validate=true, never a fillable order."""
        _add_account(self.agent_id, "kraken",
                     {"key": "k", "secret": base64.b64encode(b"s").decode()},
                     mode="live")
        patcher, calls = _patch_http(
            lambda m, u, k: _FakeResponse(200, {"error": [], "result": {"descr": {}}}))
        with patcher:
            self._shadow()
        sent = parse_qs(calls[0][2]["content"])
        self.assertEqual(sent["validate"], ["true"])


class KrakenNonceTests(_DbTestCase):
    def test_nonce_is_strictly_increasing_per_account(self):
        from execution.kraken import _next_nonce
        account_id = _add_account(self.agent_id, "kraken",
                                  {"key": "k", "secret": "s"})
        values = [_next_nonce(account_id) for _ in range(5)]
        self.assertEqual(values, sorted(set(values)), "nonces must be strictly increasing")

    def test_nonce_survives_clock_stall(self):
        """Two calls in the same millisecond must still differ — the counter
        outruns a stalled clock instead of repeating it."""
        from execution.kraken import _next_nonce
        account_id = _add_account(self.agent_id, "kraken",
                                  {"key": "k", "secret": "s"})
        with patch("execution.kraken.time.time", return_value=1_700_000_000.0):
            a = _next_nonce(account_id)
            b = _next_nonce(account_id)
        self.assertGreater(b, a)


class FxPersistenceTests(_DbTestCase):
    def test_upbit_live_fill_persists_fx_columns(self):
        from execution.base import OrderStatus
        from execution.gateway import submit_live

        def responder(m, u, k):
            if u.endswith("/ticker"):
                return _FakeResponse(200, [{"trade_price": 1391.5}])
            if u.endswith("/orders"):
                return _FakeResponse(201, {"uuid": "u-9"})
            return None

        _add_account(self.agent_id, "upbit", {"key": "k", "secret": "s"})
        os.environ["LIVE_BROKER_ALLOWLIST"] = "upbit"
        patcher, _ = _patch_http(responder)
        with patcher:
            order = submit_live(self.agent_id, "BTCUSDT", "crypto", "buy",
                                0.001, 100.0)
        self.assertIs(order.status, OrderStatus.SUBMITTED)
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT quote_currency, fx_rate_usd FROM broker_orders WHERE id=?",
                       (order.db_id,))
        row = dict(cursor.fetchone())
        conn.close()
        self.assertEqual(row["quote_currency"], "KRW")
        self.assertEqual(row["fx_rate_usd"], 1391.5)


class RoutesValidationTests(unittest.TestCase):
    def test_okx_requires_passphrase(self):
        from routes_execution import CreateBrokerAccountRequest
        req = CreateBrokerAccountRequest(broker="okx", api_key="k", api_secret="s")
        with self.assertRaises(ValueError) as ctx:
            req.credentials()
        self.assertIn("passphrase", str(ctx.exception))

    def test_okx_with_passphrase_shapes_blob(self):
        from routes_execution import CreateBrokerAccountRequest
        req = CreateBrokerAccountRequest(broker="okx", api_key="k",
                                         api_secret="s", passphrase="p")
        self.assertEqual(req.credentials(),
                         {"key": "k", "secret": "s", "passphrase": "p"})

    def test_kraken_key_secret_only(self):
        from routes_execution import CreateBrokerAccountRequest
        req = CreateBrokerAccountRequest(broker="upbit", api_key="k", api_secret="s")
        self.assertEqual(req.credentials(), {"key": "k", "secret": "s"})

    def test_unknown_broker_rejected(self):
        from routes_execution import CreateBrokerAccountRequest
        with self.assertRaises(Exception):
            CreateBrokerAccountRequest(broker="revolut", api_key="k", api_secret="s")


if __name__ == "__main__":
    unittest.main()
