"""Webull OpenAPI gateway — US stocks, spot (long-only) market orders.

Contract under test:
  - the request signature reproduces Webull's documented test vector exactly
    (developer.webull.com/apis/authentication/signature);
  - the adapter rejects without credentials and never raises on expected
    venue errors (417 business error, network failure);
  - short/cover are refused WITHOUT a network call (spot only — owner rule:
    Webull support is US stocks 1x long only);
  - the signed body bytes are exactly the bytes sent;
  - account discovery: explicit account_id is used as-is, a single account or
    a single CASH account is picked, anything ambiguous is a refusal;
  - shadow pins the sandbox host, live the production host;
  - gateway rails: Webull is a NEW venue — live is refused until it is on
    LIVE_BROKER_ALLOWLIST, and the per-order notional cap applies.

All HTTP is faked; an unexpected request fails the test.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import sys
import unittest
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

SERVER_DIR = Path(__file__).resolve().parents[1]
TESTS_DIR = Path(__file__).resolve().parent
for p in (SERVER_DIR, TESTS_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import database  # noqa: E402
from test_execution_venues import (  # noqa: E402
    _accept_tcs,
    _add_account,
    _DbTestCase,
    _FakeResponse,
    _patch_http,
    _run,
)

ACCT_LIST = "/trading/accounts/list"
PLACE = "/trading/orders/place"
DETAIL = "/trading/orders/get"
CANCEL = "/trading/orders/cancel"
POSITIONS = "/trading/assets/positions/list"
BALANCE = "/trading/assets/balances/get"
# Field names/shape from developer.webull.com "Get Account Balance".
_BALANCE_BODY = {"total_asset_currency": "USD", "total_cash_balance": "485.50",
                 "total_market_value": "250.25", "total_net_liquidation_value": "735.75",
                 "total_unrealized_profit_loss": "-12.40"}


def _order(side="buy", qty=3.0, price=100.0, symbol="AAPL"):
    from execution.base import Order
    return Order(agent_id=1, symbol=symbol, market="us-stock", side=side,
                 quantity=qty, price=price)


def _path(url):
    return urlparse(url).path


def _responder(routes):
    """routes: {path: _FakeResponse | callable(method,url,kwargs)}"""
    def respond(method, url, kwargs):
        r = routes.get(_path(url))
        if callable(r):
            return r(method, url, kwargs)
        return r
    return respond


_ONE_ACCOUNT = _FakeResponse(200, [{"account_id": "ACC1", "account_type": "CASH"}])


def _expected_signature(secret, path, query, headers, body_bytes, host):
    """Independent re-derivation from the published algorithm — used to check
    the adapter's request, not the adapter's own helper."""
    items = dict(query)
    for k in ("x-app-key", "x-timestamp", "x-signature-algorithm",
              "x-signature-version", "x-signature-nonce"):
        items[k] = headers[k]
    items["host"] = host
    s = path + "&" + "&".join(f"{k}={items[k]}" for k in sorted(items))
    if body_bytes:
        s += "&" + hashlib.md5(body_bytes).hexdigest().upper()
    mac = hmac.new((secret + "&").encode(), quote(s, safe="").encode(), hashlib.sha1)
    return base64.b64encode(mac.digest()).decode()


class SignatureVectorTests(unittest.TestCase):
    def test_documented_vector(self):
        from execution.webull import sign_request
        # Every value below is the PUBLISHED sample from Webull's signature
        # docs (developer.webull.com/apis/authentication/signature) — a
        # documentation fixture, not a credential.
        body = b'{"k1":123,"k2":"this is the api request body","k3":true,"k4":{"foo":[1,2]}}'
        sig = sign_request(
            app_secret="0f50a2e853334a9aae1a783bee120c1f",  # gitleaks:allow — Webull docs sample
            path="/trade/place_order",
            query={"a1": "webull", "a2": "123", "a3": "xxx", "q1": "yyy"},
            headers={
                "x-app-key": "776da210ab4a452795d74e726ebd74b6",  # gitleaks:allow — Webull docs sample
                "x-timestamp": "2022-01-04T03:55:31Z",
                "x-signature-algorithm": "HMAC-SHA1",
                "x-signature-version": "1.0",
                "x-signature-nonce": "48ef5afed43d4d91ae514aaeafbc29ba",
            },
            host="api.webull.com",
            body=body,
        )
        self.assertEqual(sig, "kvlS6opdZDhEBo5jq40nHYXaLvM=")


class RegistryTests(unittest.TestCase):
    def test_webull_registered_as_us_stock_venue(self):
        from execution.base import (AVAILABLE_BROKERS, BROKER_MARKETS,
                                    BROKER_SPECS, REGION_VENUES,
                                    broker_supports_market)
        self.assertIn("webull", AVAILABLE_BROKERS)
        spec = BROKER_SPECS["webull"]
        self.assertEqual(spec.fields, ("key", "secret"))
        self.assertEqual(spec.shadow, "sandbox")
        self.assertEqual(spec.quote, "USD")
        self.assertEqual(BROKER_MARKETS["webull"], ("us-stock",))
        self.assertFalse(broker_supports_market("webull", "crypto"))
        self.assertIn("webull", REGION_VENUES["US"])

    def test_every_broker_has_a_connection_guide(self):
        """/accounts shows a "Connection guide" button for every broker; a
        broker without its gwsetup doc would show 'Could not load the guide'."""
        from execution.base import BROKER_SPECS
        content = SERVER_DIR / "guide_content"
        keys = {d.get("key") for d in json.loads(
            (content / "manifest.json").read_text()).get("docs", [])}
        for broker in BROKER_SPECS:
            key = f"gwsetup-{broker}-en"
            self.assertTrue((content / f"{key}.html").exists(), broker)
            self.assertIn(key, keys, broker)

    def test_guide_states_live_and_cap_like_the_gateway(self):
        """Webull is on prod's LIVE_BROKER_ALLOWLIST (2026-11-24): the /accounts
        guide must say live is open and name the $1,000 cap the gateway applies
        to every non-legacy venue, in every language. The generator's legacy
        set must match the gateway's, or the cap sentence lands on the wrong
        brokers."""
        import importlib.util
        from execution.gateway import _LEGACY_LIVE_BROKERS, _max_order_usd_for
        gen_path = SERVER_DIR.parents[1] / "docs" / "design" / "_gen_gateway_setup_guides.py"
        spec = importlib.util.spec_from_file_location("_gen_gw_guides", gen_path)
        gen = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gen)
        self.assertEqual(gen.LEGACY_LIVE, set(_LEGACY_LIVE_BROKERS))
        self.assertIn("webull", gen.LIVE_TODAY)
        self.assertEqual(_max_order_usd_for("webull"), 1000.0)
        content = SERVER_DIR / "guide_content"
        for lang in gen.LANGS:
            html = (content / f"gwsetup-webull-{lang}.html").read_text()
            s = gen.S[lang]
            self.assertIn(s["badge_live"], html, lang)
            self.assertNotIn(s["badge_gated"], html, lang)
            self.assertNotIn(s["mode_live_gated"].format(name="Webull"), html, lang)
            for broker, name in (("webull", "Webull"), ("kraken", "Kraken")):
                page = (content / f"gwsetup-{broker}-{lang}.html").read_text()
                self.assertIn(gen.LIVE_CAP_NOTE[lang].format(name=name).strip(),
                              page, (broker, lang))
        alpaca = (content / "gwsetup-alpaca-en.html").read_text()
        self.assertNotIn("per-order limit applies", alpaca)

    def test_guides_point_paste_step_at_the_create_section(self):
        """'Paste the credentials from step N' must name the section where the
        credentials are created (h_create), in every broker and language. It
        said "step 2" (Availability) on every guide until 2026-11-24."""
        import re
        content = SERVER_DIR / "guide_content"
        # "section", not "step": the line sits in a numbered list whose own
        # item 4 is the terms checkbox (reviewer, 2026-11-24).
        refs = {"en": r"credentials you created in section (\d+)",
                "ko": r"(\d+)번 섹션에서 만든 자격 증명", "ja": r"セクション(\d+)で作成した資格情報",
                "th": r"ข้อมูลรับรองที่สร้างไว้ในหัวข้อ (\d+)",
                "vi": r"thông tin xác thực đã tạo ở mục (\d+)",
                "id": r"kredensial yang dibuat di bagian (\d+)"}
        pages = sorted(content.glob("gwsetup-*-*.html"))
        self.assertGreaterEqual(len(pages), 66)
        for page in pages:
            lang = page.stem.rsplit("-", 1)[1]
            html = page.read_text()
            ref = re.search(refs[lang], html)
            self.assertIsNotNone(ref, page.name)
            create_no = re.search(r'<span class="no">(\d+)</span>[^<]*'
                                  r'(?:Create|만들기|作成|สร้าง|Tạo|Buat)', html)
            self.assertIsNotNone(create_no, page.name)
            self.assertEqual(ref.group(1), create_no.group(1), page.name)

    def test_router_pins_host_by_mode(self):
        from execution.router import _build_real_broker
        from execution.webull import WebullBroker
        for mode, host in (("shadow", "api.sandbox.webull.com"),
                           ("paper", "api.sandbox.webull.com"),
                           ("live", "api.webull.com")):
            b = _build_real_broker({"broker": "webull", "credentials_enc": "",
                                    "execution_mode": mode, "agent_id": 1})
            self.assertIsInstance(b, WebullBroker, mode)
            self.assertEqual(b.host, host, mode)

    def test_connect_request_shapes_blob(self):
        from routes_execution import CreateBrokerAccountRequest
        req = CreateBrokerAccountRequest(broker="webull", api_key="k", api_secret="s")
        self.assertEqual(req.credentials(), {"key": "k", "secret": "s"})
        req = CreateBrokerAccountRequest(broker="webull", api_key="k",
                                         api_secret="s", account_id=" A9 ")
        self.assertEqual(req.credentials(),
                         {"key": "k", "secret": "s", "account_id": "A9"})
        with self.assertRaises(ValueError):
            CreateBrokerAccountRequest(broker="webull", api_key="k").credentials()


class AdapterTests(unittest.TestCase):
    def _broker(self, **kw):
        from execution.webull import WebullBroker
        args = {"key": "appkey", "secret": "appsecret", "sandbox": False}
        args.update(kw)
        b = WebullBroker(**args)
        b._LOOKUP_DELAYS = (0, 0, 0)  # no real sleeping in unit tests
        return b

    def test_no_credentials_rejects_without_network(self):
        from execution.base import OrderStatus
        patcher, calls = _patch_http(lambda m, u, k: None)
        with patcher:
            o = _run(self._broker(key="", secret="").submit_order(_order()))
            st = _run(self._broker(key="", secret="").get_order_status("x"))
        self.assertIs(o.status, OrderStatus.REJECTED)
        self.assertIn("not configured", o.error_message)
        self.assertIsNone(st)
        self.assertEqual(calls, [])

    def test_short_opens_with_SHORT_and_cover_buys_back(self):
        """US-stock shorts at 1x (owner 2026-11-23: "Webull also allow short
        for us-stock"): Webull's side enum is BUY/SELL/SHORT — a short sale is
        SHORT, a cover is a BUY against the open short."""
        from execution.base import OrderStatus
        for side, venue_side in (("short", "SHORT"), ("cover", "BUY")):
            patcher, calls = _patch_http(_responder({
                POSITIONS: _FakeResponse(200, [{"symbol": "AAPL", "quantity": "-2"}]),
                PLACE: _FakeResponse(200, {"client_order_id": "c", "order_id": "W1"})}))
            with patcher:
                o = _run(self._broker(account_id="M1").submit_order(
                    _order(side=side, qty=2.0)))
            self.assertIs(o.status, OrderStatus.SUBMITTED, (side, o.error_message))
            places = [c for c in calls if _path(c[1]) == PLACE]
            leg = json.loads(places[0][2]["content"])["new_orders"][0]
            self.assertEqual(leg["side"], venue_side, side)
            self.assertEqual(leg["instrument_type"], "EQUITY", side)
            self.assertEqual(leg["order_type"], "MARKET", side)
            self.assertNotIn("position_intent", leg, "options-only field")

    # ── balance: the Real view shows the venue's own money ────────────────
    def test_balance_reads_the_named_account(self):
        patcher, calls = _patch_http(_responder({BALANCE: _FakeResponse(200, _BALANCE_BODY)}))
        with patcher:
            bal = _run(self._broker(account_id="M1").get_account_balance())
        self.assertEqual(bal, {"currency": "USD", "cash": 485.5, "market_value": 250.25,
                               "equity": 735.75, "unrealized": -12.4})
        self.assertEqual([c[0].upper() for c in calls], ["GET"], "a balance read is a single GET")
        self.assertEqual(_path(calls[0][1]), BALANCE)
        self.assertEqual(parse_qs(urlparse(calls[0][1]).query)["account_id"], ["M1"])

    def test_balance_rejection_raises_the_venue_reason(self):
        patcher, _ = _patch_http(_responder({BALANCE: _FakeResponse(401, {"message": "bad key"})}))
        with patcher, self.assertRaises(RuntimeError) as cm:
            _run(self._broker(account_id="M1").get_account_balance())
        self.assertIn("401", str(cm.exception))

    def test_balance_without_credentials_never_calls_out(self):
        patcher, calls = _patch_http(lambda m, u, k: None)
        with patcher, self.assertRaises(RuntimeError):
            _run(self._broker(key="", secret="").get_account_balance())
        self.assertEqual(calls, [])

    # ── cover = plain BUY at Webull: never let it open a long ──────────────
    def _cover(self, positions, qty=2.0):
        patcher, calls = _patch_http(_responder({
            POSITIONS: positions,
            PLACE: _FakeResponse(200, {"client_order_id": "c", "order_id": "W1"})}))
        with patcher:
            o = _run(self._broker(account_id="M1").submit_order(
                _order(side="cover", qty=qty)))
        return o, [c for c in calls if _path(c[1]) == PLACE]

    def test_cover_with_nothing_held_at_webull_is_refused(self):
        from execution.base import OrderStatus
        o, places = self._cover(_FakeResponse(200, [{"symbol": "MSFT", "quantity": "-4"}]))
        self.assertIs(o.status, OrderStatus.REJECTED)
        self.assertIn("would open a long", o.error_message)
        self.assertEqual(places, [], "a cover with no short behind it is never sent")

    def test_cover_larger_than_webull_position_is_refused(self):
        from execution.base import OrderStatus
        o, places = self._cover(_FakeResponse(200, [{"symbol": "AAPL", "quantity": "-1"}]),
                                qty=2.0)
        self.assertIs(o.status, OrderStatus.REJECTED)
        self.assertIn("exceeds", o.error_message)
        self.assertEqual(places, [])

    def test_cover_within_position_is_sent_either_sign_convention(self):
        from execution.base import OrderStatus
        for q in ("-3", "3"):  # Webull does not document the short sign
            o, places = self._cover(_FakeResponse(200, [{"symbol": "aapl", "quantity": q}]))
            self.assertIs(o.status, OrderStatus.SUBMITTED, (q, o.error_message))
            self.assertEqual(len(places), 1, q)

    def test_cover_sent_when_positions_unreadable(self):
        """Refusing every cover on a failed read could strand a real short."""
        from execution.base import OrderStatus
        o, places = self._cover(_FakeResponse(503, None, text="unavailable"))
        self.assertIs(o.status, OrderStatus.SUBMITTED, o.error_message)
        self.assertEqual(len(places), 1)

    def test_side_map_is_exactly_the_four_platform_verbs(self):
        """Mutation gap: an alias key ('sell_short' -> SHORT) would send a
        short that no other test names. Pin the whole map."""
        from execution.webull import _SIDE_MAP
        self.assertEqual(_SIDE_MAP, {"buy": "BUY", "sell": "SELL",
                                     "short": "SHORT", "cover": "BUY"})

    def test_unknown_side_refused_without_network(self):
        from execution.base import OrderStatus
        patcher, calls = _patch_http(lambda m, u, k: None)
        with patcher:
            for side in ("buy_to_open", "sell_short_leveraged", ""):
                o = _run(self._broker().submit_order(_order(side=side)))
                self.assertIs(o.status, OrderStatus.REJECTED, side)
        self.assertEqual(calls, [])

    def test_buy_places_signed_market_order(self):
        from execution.base import OrderStatus
        placed = {}

        def place(method, url, kwargs):
            placed.update(kwargs)
            return _FakeResponse(200, {"client_order_id": "c", "order_id": "W1"})

        patcher, calls = _patch_http(_responder({ACCT_LIST: _ONE_ACCOUNT, PLACE: place}))
        with patcher:
            o = _run(self._broker().submit_order(_order(qty=3.0)))
        self.assertIs(o.status, OrderStatus.SUBMITTED, o.error_message)
        self.assertEqual([c[0] for c in calls], ["GET", "POST"])
        method, url, kwargs = calls[1]
        self.assertEqual(urlparse(url).netloc, "api.webull.com")
        self.assertEqual(_path(url), PLACE)
        self.assertNotIn("json", kwargs, "body must be sent as the exact signed bytes")
        body_bytes = kwargs["content"]
        body = json.loads(body_bytes)
        self.assertEqual(body["account_id"], "ACC1")
        (leg,) = body["new_orders"]
        self.assertEqual(leg["symbol"], "AAPL")
        self.assertEqual(leg["side"], "BUY")
        self.assertEqual(leg["order_type"], "MARKET")
        self.assertEqual(leg["quantity"], "3")
        self.assertEqual(leg["instrument_type"], "EQUITY")
        self.assertEqual(leg["market"], "US")
        self.assertEqual(leg["time_in_force"], "DAY")
        self.assertEqual(leg["entrust_type"], "QTY")
        self.assertEqual(leg["support_trading_session"], "CORE")
        self.assertLessEqual(len(leg["client_order_id"]), 32)
        # The reconciler looks the order up by the id we were handed back.
        self.assertEqual(o.broker_order_id, leg["client_order_id"])
        h = kwargs["headers"]
        self.assertEqual(h["x-app-key"], "appkey")
        self.assertNotIn("x-app-secret", h, "the secret must never be sent")
        self.assertEqual(h["x-signature"], _expected_signature(
            "appsecret", PLACE, {}, h, body_bytes, "api.webull.com"))

    def test_sell_maps_to_sell_and_get_is_signed_with_query(self):
        patcher, calls = _patch_http(_responder({
            ACCT_LIST: _ONE_ACCOUNT,
            PLACE: _FakeResponse(200, {"client_order_id": "c", "order_id": "W1"})}))
        with patcher:
            _run(self._broker().submit_order(_order(side="sell", qty=0.5)))
        leg = json.loads(calls[1][2]["content"])["new_orders"][0]
        self.assertEqual(leg["side"], "SELL")
        self.assertEqual(leg["quantity"], "0.5")
        _, url, kwargs = calls[0]
        self.assertEqual(kwargs["headers"]["x-signature"], _expected_signature(
            "appsecret", ACCT_LIST, {}, kwargs["headers"], b"", "api.webull.com"))

    def test_explicit_account_id_skips_discovery(self):
        patcher, calls = _patch_http(_responder({
            PLACE: _FakeResponse(200, {"client_order_id": "c", "order_id": "W1"})}))
        with patcher:
            _run(self._broker(account_id="MINE").submit_order(_order()))
        self.assertEqual(len(calls), 1)
        self.assertEqual(json.loads(calls[0][2]["content"])["account_id"], "MINE")

    def test_discovery_prefers_the_single_cash_account(self):
        patcher, calls = _patch_http(_responder({
            ACCT_LIST: _FakeResponse(200, [
                {"account_id": "M1", "account_type": "MARGIN"},
                {"account_id": "C1", "account_type": "CASH"}]),
            PLACE: _FakeResponse(200, {"client_order_id": "c", "order_id": "W1"})}))
        with patcher:
            _run(self._broker().submit_order(_order()))
        self.assertEqual(json.loads(calls[1][2]["content"])["account_id"], "C1")

    def test_ambiguous_accounts_refuse(self):
        from execution.base import OrderStatus
        patcher, calls = _patch_http(_responder({
            ACCT_LIST: _FakeResponse(200, [
                {"account_id": "C1", "account_type": "CASH"},
                {"account_id": "C2", "account_type": "CASH"}])}))
        with patcher:
            o = _run(self._broker().submit_order(_order()))
        self.assertIs(o.status, OrderStatus.REJECTED)
        self.assertIn("account id", o.error_message)
        self.assertEqual(len(calls), 1, "no order may be placed on a guessed account")

    def test_business_error_rejects(self):
        from execution.base import OrderStatus
        patcher, _ = _patch_http(_responder({
            ACCT_LIST: _ONE_ACCOUNT,
            PLACE: _FakeResponse(417, {"error_code": "ORDER_BUYING_POWER_NOT_ENOUGH",
                                       "message": "insufficient buying power"})}))
        with patcher:
            o = _run(self._broker().submit_order(_order()))
        self.assertIs(o.status, OrderStatus.REJECTED)
        self.assertIn("insufficient buying power", o.error_message)

    def test_network_error_rejects_never_raises(self):
        import httpx
        from execution.base import OrderStatus
        patcher, _ = _patch_http(lambda m, u, k: httpx.ConnectError("boom", request=None))
        with patcher:
            o = _run(self._broker(account_id="A").submit_order(_order()))
            st = _run(self._broker(account_id="A").get_order_status("cid"))
            ok = _run(self._broker(account_id="A").cancel_order("cid"))
            pos = _run(self._broker(account_id="A").get_broker_positions())
        self.assertIs(o.status, OrderStatus.REJECTED)
        self.assertIn("network error", o.error_message)
        self.assertIsNone(st)
        self.assertFalse(ok)
        self.assertEqual(pos, [])

    def test_order_status_mapping(self):
        from execution.base import OrderStatus
        cases = {
            "FILLED": OrderStatus.FILLED, "PARTIAL_FILLED": OrderStatus.PARTIAL_FILL,
            "CANCELLED": OrderStatus.CANCELLED, "FAILED": OrderStatus.REJECTED,
            "SUBMITTED": OrderStatus.SUBMITTED, "PENDING": OrderStatus.SUBMITTED,
        }
        for venue, ours in cases.items():
            seen = {}

            def detail(method, url, kwargs, venue=venue):
                seen["q"] = parse_qs(urlparse(url).query) or {
                    k: [v] for k, v in (kwargs.get("params") or {}).items()}
                return _FakeResponse(200, {"client_order_id": "cid", "orders": [{
                    "client_order_id": "cid", "status": venue,
                    "filled_quantity": "2", "filled_price": "101.5"}]})
            patcher, _ = _patch_http(_responder({DETAIL: detail}))
            with patcher:
                st = _run(self._broker(account_id="A").get_order_status("cid", "AAPL"))
            self.assertIs(st["status"], ours, venue)
            self.assertEqual(st["filled_qty"], 2.0)
            self.assertEqual(st["avg_price"], 101.5)
            self.assertEqual(seen["q"]["client_order_id"], ["cid"])
            self.assertEqual(seen["q"]["account_id"], ["A"])

    def test_cancel_and_positions(self):
        patcher, calls = _patch_http(_responder({
            CANCEL: _FakeResponse(200, {"client_order_id": "cid", "order_id": "W1"}),
            POSITIONS: _FakeResponse(200, [{"symbol": "AAPL", "quantity": "4"},
                                           {"symbol": "TSLA", "quantity": "-1"}])}))
        with patcher:
            self.assertTrue(_run(self._broker(account_id="A").cancel_order("cid")))
            pos = _run(self._broker(account_id="A").get_broker_positions())
        self.assertEqual(json.loads(calls[0][2]["content"]),
                         {"account_id": "A", "client_order_id": "cid"})
        self.assertEqual(pos, [{"symbol": "AAPL", "qty": 4.0, "side": "long"},
                               {"symbol": "TSLA", "qty": 1.0, "side": "short"}])

    # ── review fixes (adversarial pass on cb9d6e54) ─────────────────────────
    def test_lost_place_reply_with_order_at_venue_is_submitted(self):
        """A read timeout AFTER the request was sent must not hide a live
        order: the adapter asks Webull about its own client_order_id."""
        import httpx
        from execution.base import OrderStatus

        def place(m, u, k):
            return httpx.ReadTimeout("timed out", request=None)

        def detail(m, u, k):
            cid = parse_qs(urlparse(u).query)["client_order_id"][0]
            return _FakeResponse(200, {"orders": [{"client_order_id": cid,
                                                   "status": "SUBMITTED"}]})
        patcher, calls = _patch_http(_responder({PLACE: place, DETAIL: detail}))
        with patcher:
            o = _run(self._broker(account_id="A").submit_order(_order()))
        self.assertIs(o.status, OrderStatus.SUBMITTED, o.error_message)
        self.assertEqual([c[0] for c in calls], ["POST", "GET"])
        sent_cid = json.loads(calls[0][2]["content"])["new_orders"][0]["client_order_id"]
        self.assertEqual(o.broker_order_id, sent_cid)

    def test_lost_place_reply_unconfirmed_is_rejected_but_traceable(self):
        import httpx
        from execution.base import OrderStatus
        patcher, _ = _patch_http(_responder({
            PLACE: lambda m, u, k: httpx.ReadTimeout("timed out", request=None),
            DETAIL: _FakeResponse(404, {"message": "not found"})}))
        with patcher:
            o = _run(self._broker(account_id="A").submit_order(_order()))
        self.assertIs(o.status, OrderStatus.REJECTED)
        self.assertIn("outcome unknown", o.error_message)
        self.assertIsNotNone(o.broker_order_id, "the id must be kept for the user to check")

    def test_connect_failure_is_plain_rejection_without_lookup(self):
        import httpx
        from execution.base import OrderStatus
        patcher, calls = _patch_http(_responder({
            PLACE: lambda m, u, k: httpx.ConnectError("refused", request=None)}))
        with patcher:
            o = _run(self._broker(account_id="A").submit_order(_order()))
        self.assertIs(o.status, OrderStatus.REJECTED)
        self.assertIn("network error", o.error_message)
        self.assertEqual(len(calls), 1, "a request that never left needs no lookup")

    def test_http_200_with_error_body_is_rejected(self):
        """A 200 we cannot read is ambiguous: looked up, and refused only when
        Webull does not confirm the order."""
        from execution.base import OrderStatus
        patcher, calls = _patch_http(_responder({
            PLACE: _FakeResponse(200, {"code": "ORDER_REJECTED",
                                       "message": "symbol not tradable"}),
            DETAIL: _FakeResponse(200, {"orders": []})}))
        with patcher:
            o = _run(self._broker(account_id="A").submit_order(_order()))
        self.assertIs(o.status, OrderStatus.REJECTED)
        self.assertIn("symbol not tradable", o.error_message)
        self.assertEqual([c[0] for c in calls], ["POST", "GET", "GET", "GET"])

    def test_5xx_with_order_at_venue_is_submitted_never_filled(self):
        """A 502 can hide a placed order. Found FILLED → still SUBMITTED, so the
        reconciler records the broker-confirmed fill size."""
        from execution.base import OrderStatus

        def detail(m, u, k):
            cid = parse_qs(urlparse(u).query)["client_order_id"][0]
            return _FakeResponse(200, {"orders": [{"client_order_id": cid,
                                                   "status": "FILLED",
                                                   "filled_quantity": "1"}]})
        patcher, _ = _patch_http(_responder({
            PLACE: _FakeResponse(502, None, text="Bad Gateway"), DETAIL: detail}))
        with patcher:
            o = _run(self._broker(account_id="A").submit_order(_order(qty=3)))
        self.assertIs(o.status, OrderStatus.SUBMITTED)

    def test_4xx_is_a_rejection_without_lookup(self):
        from execution.base import OrderStatus
        patcher, calls = _patch_http(_responder({
            PLACE: _FakeResponse(401, {"message": "invalid signature"})}))
        with patcher:
            o = _run(self._broker(account_id="A").submit_order(_order()))
        self.assertIs(o.status, OrderStatus.REJECTED)
        self.assertEqual(len(calls), 1)

    def test_lookup_retries_until_order_is_indexed(self):
        import httpx
        from execution.base import OrderStatus
        seen = []

        def detail(m, u, k):
            seen.append(1)
            if len(seen) < 3:
                return _FakeResponse(200, {"orders": []})
            cid = parse_qs(urlparse(u).query)["client_order_id"][0]
            return _FakeResponse(200, {"orders": [{"client_order_id": cid,
                                                   "status": "SUBMITTED"}]})
        patcher, _ = _patch_http(_responder({
            PLACE: lambda m, u, k: httpx.ReadTimeout("t", request=None), DETAIL: detail}))
        with patcher:
            o = _run(self._broker(account_id="A").submit_order(_order()))
        self.assertIs(o.status, OrderStatus.SUBMITTED)
        self.assertEqual(len(seen), 3)

    def test_empty_leg_never_confirms_an_order(self):
        import httpx
        from execution.base import OrderStatus
        patcher, _ = _patch_http(_responder({
            PLACE: lambda m, u, k: httpx.ReadTimeout("t", request=None),
            DETAIL: _FakeResponse(200, {"orders": [{}]})}))
        with patcher:
            o = _run(self._broker(account_id="A").submit_order(_order()))
        self.assertIs(o.status, OrderStatus.REJECTED)
        self.assertIn("outcome unknown", o.error_message)

    def test_foreign_leg_does_not_match(self):
        patcher, _ = _patch_http(_responder({DETAIL: _FakeResponse(200, {"orders": [
            {"client_order_id": "someone-else", "status": "FILLED"}]})}))
        with patcher:
            self.assertIsNone(_run(self._broker(account_id="A").get_order_status("cid")))

    def test_malformed_responses_never_raise(self):
        patcher, _ = _patch_http(_responder({
            DETAIL: _FakeResponse(200, {"orders": 5}),
            ACCT_LIST: _FakeResponse(200, None, text="<html>oops</html>")}))
        with patcher:
            self.assertIsNone(_run(self._broker(account_id="A").get_order_status("cid")))
            self.assertFalse(_run(self._broker().cancel_order("cid")))

    def test_venue_rejected_status_maps_to_rejected(self):
        from execution.base import OrderStatus
        patcher, _ = _patch_http(_responder({DETAIL: _FakeResponse(200, {"orders": [
            {"client_order_id": "cid", "status": "REJECTED"}]})}))
        with patcher:
            st = _run(self._broker(account_id="A").get_order_status("cid"))
        self.assertIs(st["status"], OrderStatus.REJECTED)

    def test_query_space_sent_as_percent20(self):
        patcher, calls = _patch_http(_responder({DETAIL: _FakeResponse(200, {"orders": []})}))
        with patcher:
            _run(self._broker(account_id="A B").get_order_status("cid"))
        self.assertIn("account_id=A%20B", calls[0][1])

    def test_sandbox_host(self):
        patcher, calls = _patch_http(_responder({
            PLACE: _FakeResponse(200, {"client_order_id": "c", "order_id": "W1"})}))
        with patcher:
            _run(self._broker(account_id="A", sandbox=True).submit_order(_order()))
        self.assertEqual(urlparse(calls[0][1]).netloc, "api.sandbox.webull.com")


class _Env:
    """Set env vars for one block, restoring the previous values after.
    conftest runs the suite with FUTURES_TRADING_BLOCKED=0; the short-path
    tests restore production's switch shape explicitly."""

    def __init__(self, **values):
        self._values = values
        self._saved = {}

    def __enter__(self):
        for k, v in self._values.items():
            self._saved[k] = os.environ.get(k)
            os.environ[k] = v

    def __exit__(self, *exc):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        return False


# Production today: block ON, shorts allowed (owner 2026-11-23).
_PROD_TWO_WAY = {"FUTURES_TRADING_BLOCKED": "1", "SHORTS_TRADING_BLOCKED": "0"}
# The re-arm switch: block ON, shorts blocked -> long-only.
_LONG_ONLY = {"FUTURES_TRADING_BLOCKED": "1", "SHORTS_TRADING_BLOCKED": "1"}


class WebullGatewayTests(_DbTestCase):
    """The order path end to end: rule → gateway → adapter → broker_orders."""

    def _live(self, qty=2.0, price=100.0, side="buy"):
        from execution.gateway import submit_live
        return submit_live(self.agent_id, "AAPL", "us-stock", side, qty, price)

    def test_live_refused_until_allowlisted(self):
        from execution.base import OrderStatus
        from execution.gateway import NOT_ALLOWLISTED, live_refusal_reason
        _add_account(self.agent_id, "webull", {"key": "k", "secret": "s"})
        _accept_tcs(self.agent_id, "webull")
        self.assertEqual(live_refusal_reason(self.agent_id, "live", "us-stock"),
                         NOT_ALLOWLISTED)
        patcher, calls = _patch_http(lambda m, u, k: None)
        with patcher:
            o = self._live()
        self.assertIs(o.status, OrderStatus.REJECTED)
        self.assertEqual(o.error_message, NOT_ALLOWLISTED)
        self.assertEqual(calls, [], "a non-allowlisted venue is never contacted")

    def test_allowlisted_live_reaches_production_and_persists(self):
        from execution.base import OrderStatus
        from execution.gateway import live_refusal_reason
        _add_account(self.agent_id, "webull", {"key": "k", "secret": "s",
                                               "account_id": "ACC1"})
        _accept_tcs(self.agent_id, "webull")
        os.environ["LIVE_BROKER_ALLOWLIST"] = "alpaca,binance,ibkr,webull"
        self.assertIsNone(live_refusal_reason(self.agent_id, "live", "us-stock"))
        patcher, calls = _patch_http(_responder({
            PLACE: _FakeResponse(200, {"client_order_id": "c", "order_id": "W1"})}))
        with patcher:
            o = self._live()
        self.assertIs(o.status, OrderStatus.SUBMITTED, o.error_message)
        self.assertEqual(o.broker, "webull")
        self.assertEqual(urlparse(calls[0][1]).netloc, "api.webull.com")
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT broker, status, broker_order_id FROM broker_orders WHERE id=?",
                    (o.db_id,))
        row = dict(cur.fetchone())
        conn.close()
        self.assertEqual(row["broker"], "webull")
        self.assertEqual(row["status"], "submitted")
        self.assertEqual(row["broker_order_id"], o.broker_order_id)

    def test_gateway_balance_reads_the_production_account(self):
        """Real mode shows the LIVE account's money, so the read goes to the
        production host even though the account row says paper."""
        from execution.gateway import gateway_balances
        _add_account(self.agent_id, "webull", {"key": "k", "secret": "s",
                                               "account_id": "ACC1"})
        patcher, calls = _patch_http(_responder({BALANCE: _FakeResponse(200, _BALANCE_BODY)}))
        with patcher:
            out = gateway_balances(self.agent_id)
        self.assertEqual(len(out), 1)
        self.assertTrue(out[0]["ok"], out[0])
        self.assertEqual((out[0]["broker"], out[0]["equity"], out[0]["cash"]),
                         ("webull", 735.75, 485.5))
        self.assertEqual(urlparse(calls[0][1]).netloc, "api.webull.com")
        self.assertEqual({c[0].upper() for c in calls}, {"GET"}, "read-only")

    def test_gateway_balance_reports_why_it_failed(self):
        from execution.gateway import gateway_balances
        _add_account(self.agent_id, "webull", {"key": "k", "secret": "s",
                                               "account_id": "ACC1"})
        patcher, _ = _patch_http(_responder({BALANCE: _FakeResponse(401, {"message": "bad key"})}))
        with patcher:
            out = gateway_balances(self.agent_id)
        self.assertFalse(out[0]["ok"])
        self.assertIn("401", out[0]["detail"])
        self.assertIsNone(out[0]["equity"])

    def test_new_venue_notional_cap_refuses(self):
        from execution.base import OrderStatus
        _add_account(self.agent_id, "webull", {"key": "k", "secret": "s",
                                               "account_id": "ACC1"})
        os.environ["LIVE_BROKER_ALLOWLIST"] = "webull"
        patcher, calls = _patch_http(lambda m, u, k: None)
        with patcher:
            o = self._live(qty=20.0, price=100.0)  # $2,000 > $1,000 cap
        self.assertIs(o.status, OrderStatus.REJECTED)
        self.assertIn("per-order limit", o.error_message)
        self.assertEqual(calls, [])

    def test_live_us_stock_short_reaches_webull_as_SHORT(self):
        """Shorts allowed (platform default since 2026-11-23): a live us-stock
        short goes to Webull's production host as side SHORT."""
        from execution.base import OrderStatus
        _add_account(self.agent_id, "webull", {"key": "k", "secret": "s",
                                               "account_id": "MARGIN1"})
        os.environ["LIVE_BROKER_ALLOWLIST"] = "webull"
        patcher, calls = _patch_http(_responder({
            PLACE: _FakeResponse(200, {"client_order_id": "c", "order_id": "W1"})}))
        with patcher, _Env(**_PROD_TWO_WAY):
            o = self._live(side="short", qty=1.0)
        self.assertIs(o.status, OrderStatus.SUBMITTED, o.error_message)
        self.assertEqual(urlparse(calls[0][1]).netloc, "api.webull.com")
        self.assertEqual(json.loads(calls[0][2]["content"])["new_orders"][0]["side"],
                         "SHORT")

    def test_live_cover_with_block_off_never_opens_a_long(self):
        """Review of 8b4784f9: with the platform block OFF the automation size
        guard does not run, so the venue check is what stops a cover from
        becoming a long-opening BUY."""
        from execution.base import OrderStatus
        _add_account(self.agent_id, "webull", {"key": "k", "secret": "s",
                                               "account_id": "MARGIN1"})
        os.environ["LIVE_BROKER_ALLOWLIST"] = "webull"
        patcher, calls = _patch_http(_responder({
            POSITIONS: _FakeResponse(200, []),
            PLACE: _FakeResponse(200, {"client_order_id": "c", "order_id": "W1"})}))
        with patcher, _Env(FUTURES_TRADING_BLOCKED="0"):
            o = self._live(side="cover", qty=1.0)
        self.assertIs(o.status, OrderStatus.REJECTED)
        self.assertEqual([_path(c[1]) for c in calls], [POSITIONS])

    def test_shorts_blocked_switch_rearms_long_only_for_webull(self):
        from execution.base import OrderStatus
        _add_account(self.agent_id, "webull", {"key": "k", "secret": "s",
                                               "account_id": "MARGIN1"})
        os.environ["LIVE_BROKER_ALLOWLIST"] = "webull"
        patcher, calls = _patch_http(lambda m, u, k: None)
        with patcher, _Env(**_LONG_ONLY):
            o = self._live(side="short", qty=1.0)
        self.assertIs(o.status, OrderStatus.REJECTED)
        self.assertIn("opening a short", o.error_message)
        self.assertEqual(calls, [], "a blocked short must never reach the venue")

    def test_crypto_short_never_routes_to_webull(self):
        from execution.gateway import submit_live
        _add_account(self.agent_id, "webull", {"key": "k", "secret": "s",
                                               "account_id": "MARGIN1"})
        os.environ["LIVE_BROKER_ALLOWLIST"] = "webull"
        patcher, calls = _patch_http(lambda m, u, k: None)
        with patcher, _Env(**_PROD_TWO_WAY):
            o = submit_live(self.agent_id, "BTCUSDT", "crypto", "short", 0.01, 100.0)
        self.assertNotEqual(o.broker, "webull")
        self.assertEqual(calls, [])

    def test_crypto_order_never_routes_to_webull(self):
        from execution.gateway import NOT_CONFIGURED, submit_live
        _add_account(self.agent_id, "webull", {"key": "k", "secret": "s",
                                               "account_id": "ACC1"})
        os.environ["LIVE_BROKER_ALLOWLIST"] = "webull"
        patcher, calls = _patch_http(lambda m, u, k: None)
        with patcher:
            o = submit_live(self.agent_id, "BTCUSDT", "crypto", "buy", 0.01, 100.0)
        self.assertEqual(o.error_message, NOT_CONFIGURED)
        self.assertEqual(calls, [])

    def test_shadow_pins_sandbox_even_if_account_says_live(self):
        from execution.gateway import submit_shadow
        _add_account(self.agent_id, "webull", {"key": "k", "secret": "s",
                                               "account_id": "ACC1"}, mode="live")
        patcher, calls = _patch_http(_responder({
            PLACE: _FakeResponse(200, {"client_order_id": "c", "order_id": "W1"})}))
        with patcher:
            submit_shadow(self.agent_id, "AAPL", "us-stock", "buy", 2.0, 100.0,
                          ledger_quantity=2.0)
        self.assertEqual(len(calls), 1)
        self.assertEqual(urlparse(calls[0][1]).netloc, "api.sandbox.webull.com")


if __name__ == "__main__":
    unittest.main()
