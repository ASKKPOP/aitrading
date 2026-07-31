"""Resting (limit) orders — placement rules, cancel fencing, and the fill
watcher's money path.

The fills are real ledger writes (execute_paper_trade), so the watcher tests
drive the tick against a live sqlite ledger with a mocked OKX tickers call and
assert cash/position effects, not just row statuses. The engine is
simulator-only by design — one test pins that it never imports the live
execution gateway.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from unittest.mock import patch

from pathlib import Path

from fastapi.testclient import TestClient

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
import resting_orders
from routes import create_app


def _tickers(price_by_symbol):
    return [{"symbol": f"{s}USDT", "last_price": p} for s, p in price_by_symbol.items()]


class _RestingBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())

    def tearDown(self):
        self.tmp.cleanup()

    def _agent(self, name: str = "limit-bot", cash: float = 100_000.0) -> dict:
        r = self.client.post("/api/claw/agents/selfRegister",
                             json={"name": name, "password": "testpass123",
                                   "initial_balance": cash})
        assert r.status_code == 200, r.text
        body = r.json()
        return {"id": body["agent_id"],
                "headers": {"Authorization": f"Bearer {body['token']}"}}

    def _cash(self, agent_id: int) -> float:
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT cash FROM agents WHERE id = ?", (agent_id,))
        cash = cur.fetchone()["cash"]
        conn.close()
        return cash

    def _place(self, headers, **kw):
        body = {"market": "crypto", "side": "buy", "symbol": "BTC",
                "quantity": 0.01, "limit_price": 60_000, **kw}
        return self.client.post("/api/orders", headers=headers, json=body)


class PlacementTests(_RestingBase):
    def _place_at(self, headers, live_price, **kw):
        with patch("crypto_feed.fetch_ticker",
                   return_value={"symbol": "BTCUSDT", "last_price": live_price}):
            return self._place(headers, **kw)

    def test_places_passive_buy(self):
        a = self._agent()
        r = self._place_at(a["headers"], 64_000, limit_price=60_000)
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["status"], "open")
        self.assertEqual(body["limit_price"], 60_000)

    def test_refuses_immediately_fillable_buy(self):
        """A buy limit above the market is a market order in disguise."""
        a = self._agent()
        r = self._place_at(a["headers"], 59_000, limit_price=60_000)
        self.assertEqual(r.status_code, 409, r.text)
        self.assertEqual(r.json()["detail"], "would_fill_immediately")

    def test_refuses_immediately_fillable_short(self):
        a = self._agent()
        r = self._place_at(a["headers"], 64_000, side="short", limit_price=63_000)
        self.assertEqual(r.status_code, 409, r.text)

    def test_places_passive_short_above_market(self):
        a = self._agent()
        r = self._place_at(a["headers"], 64_000, side="short", limit_price=70_000)
        self.assertEqual(r.status_code, 200, r.text)

    def test_tpsl_validated_against_limit_price(self):
        a = self._agent()
        # buy at 60k with SL above the limit → refused
        r = self._place_at(a["headers"], 64_000, limit_price=60_000, stop_loss=61_000)
        self.assertEqual(r.status_code, 422, r.text)
        r = self._place_at(a["headers"], 64_000, limit_price=60_000,
                           stop_loss=57_000, take_profit=66_000)
        self.assertEqual(r.status_code, 200, r.text)

    def test_refuses_without_live_quote(self):
        a = self._agent()
        with patch("crypto_feed.fetch_ticker", side_effect=RuntimeError("OKX down")):
            r = self._place(a["headers"])
        self.assertEqual(r.status_code, 422, r.text)

    def test_unsupported_market_refused(self):
        a = self._agent()
        r = self._place_at(a["headers"], 64_000, market="us-stock")
        self.assertEqual(r.status_code, 422, r.text)

    def test_open_order_cap(self):
        a = self._agent()
        with patch.object(resting_orders, "MAX_OPEN_PER_AGENT", 2):
            self.assertEqual(self._place_at(a["headers"], 64_000).status_code, 200)
            self.assertEqual(self._place_at(a["headers"], 64_000).status_code, 200)
            r = self._place_at(a["headers"], 64_000)
        self.assertEqual(r.status_code, 422)
        self.assertIn("cap", r.json()["detail"])

    def test_requires_auth(self):
        r = self._place({"Authorization": "Bearer nope"})
        self.assertEqual(r.status_code, 401)


class CancelListTests(_RestingBase):
    def _open_order(self, a) -> int:
        with patch("crypto_feed.fetch_ticker",
                   return_value={"symbol": "BTCUSDT", "last_price": 64_000}):
            r = self._place(a["headers"])
        assert r.status_code == 200, r.text
        return r.json()["id"]

    def test_cancel_own_open_order(self):
        a = self._agent()
        oid = self._open_order(a)
        r = self.client.delete(f"/api/orders/{oid}", headers=a["headers"])
        self.assertEqual(r.status_code, 200, r.text)
        listed = self.client.get("/api/orders?status=cancelled", headers=a["headers"]).json()
        self.assertEqual([o["id"] for o in listed["orders"]], [oid])

    def test_cannot_cancel_foreign_order(self):
        owner, thief = self._agent("owner-l"), self._agent("thief-l")
        oid = self._open_order(owner)
        r = self.client.delete(f"/api/orders/{oid}", headers=thief["headers"])
        self.assertEqual(r.status_code, 404)

    def test_cancel_twice_is_409(self):
        a = self._agent()
        oid = self._open_order(a)
        self.client.delete(f"/api/orders/{oid}", headers=a["headers"])
        r = self.client.delete(f"/api/orders/{oid}", headers=a["headers"])
        self.assertEqual(r.status_code, 409)
        self.assertIn("not_open", r.json()["detail"])

    def test_list_defaults_to_open(self):
        a = self._agent()
        self._open_order(a)
        listed = self.client.get("/api/orders", headers=a["headers"]).json()
        self.assertEqual(listed["count"], 1)
        self.assertEqual(listed["orders"][0]["status"], "open")


class WatcherTests(_RestingBase):
    def _open_order(self, a, **kw) -> int:
        with patch("crypto_feed.fetch_ticker",
                   return_value={"symbol": "BTCUSDT", "last_price": 64_000}):
            r = self._place(a["headers"], **kw)
        assert r.status_code == 200, r.text
        return r.json()["id"]

    def test_uncrossed_order_stays_open(self):
        a = self._agent()
        self._open_order(a, limit_price=60_000)
        with patch("crypto_feed.fetch_tickers",
                   return_value=_tickers({"BTC": 63_000})):
            result = resting_orders.run_resting_orders_tick()
        self.assertEqual(result["filled"], 0)
        listed = self.client.get("/api/orders", headers=a["headers"]).json()
        self.assertEqual(listed["count"], 1)

    def test_crossed_buy_fills_and_moves_cash_and_position(self):
        a = self._agent()
        oid = self._open_order(a, limit_price=60_000, quantity=0.01,
                               stop_loss=57_000, take_profit=66_000)
        cash_before = self._cash(a["id"])
        with patch("crypto_feed.fetch_tickers",
                   return_value=_tickers({"BTC": 59_950})):
            result = resting_orders.run_resting_orders_tick()
        self.assertEqual(result["filled"], 1, result)

        # Order row: filled + signal reference.
        filled = self.client.get("/api/orders?status=filled", headers=a["headers"]).json()
        self.assertEqual([o["id"] for o in filled["orders"]], [oid])
        self.assertIsNotNone(filled["orders"][0]["signal_id"])

        # Ledger: cash debited notional+fee at the OBSERVED price, position
        # opened with the order's TP/SL registered.
        pos = self.client.get("/api/positions", headers=a["headers"]).json()
        rows = [p for p in pos["positions"] if p["symbol"] == "BTC"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["side"], "long")
        self.assertAlmostEqual(rows[0]["quantity"], 0.01)
        self.assertAlmostEqual(rows[0]["entry_price"], 59_950)
        self.assertEqual(rows[0]["stop_loss"], 57_000)
        self.assertEqual(rows[0]["take_profit"], 66_000)
        spent = cash_before - self._cash(a["id"])
        self.assertGreater(spent, 59_950 * 0.01)          # notional
        self.assertLess(spent, 59_950 * 0.01 * 1.01)      # + at most 1% fee

    def test_fill_failure_marks_rejected(self):
        """A sell limit with no long book must reject, not crash the tick."""
        a = self._agent()
        self._open_order(a, side="sell", limit_price=70_000, quantity=0.5)
        with patch("crypto_feed.fetch_tickers",
                   return_value=_tickers({"BTC": 71_000})):
            result = resting_orders.run_resting_orders_tick()
        self.assertEqual(result["rejected"], 1, result)
        rej = self.client.get("/api/orders?status=rejected", headers=a["headers"]).json()
        self.assertEqual(rej["count"], 1)
        self.assertIn("no long position", rej["orders"][0]["reason"])

    def test_cancelled_order_never_fills(self):
        a = self._agent()
        oid = self._open_order(a, limit_price=60_000)
        self.client.delete(f"/api/orders/{oid}", headers=a["headers"])
        with patch("crypto_feed.fetch_tickers",
                   return_value=_tickers({"BTC": 59_000})):
            result = resting_orders.run_resting_orders_tick()
        self.assertEqual(result["filled"], 0)
        self.assertEqual(result["rejected"], 0)

    def test_fill_is_exactly_once_across_retries(self):
        """A crash between claim and finish must not double-execute: the
        client_order_id dedupe turns the retry into a recovery."""
        a = self._agent()
        oid = self._open_order(a, limit_price=60_000, quantity=0.01)
        # Simulate the crash: execute the fill, then force the row back to a
        # stale 'filling' claim as a dead worker would leave it.
        with patch("crypto_feed.fetch_tickers",
                   return_value=_tickers({"BTC": 59_950})):
            resting_orders.run_resting_orders_tick()
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE resting_orders SET status='filling', "
                    "updated_at='2020-01-01T00:00:00Z' WHERE id = ?", (oid,))
        conn.commit()
        conn.close()
        cash_after_first = self._cash(a["id"])
        with patch("crypto_feed.fetch_tickers",
                   return_value=_tickers({"BTC": 59_950})):
            result = resting_orders.run_resting_orders_tick()
        self.assertEqual(result["filled"], 1)  # recovered, not re-executed
        self.assertEqual(self._cash(a["id"]), cash_after_first)  # no double debit
        filled = self.client.get("/api/orders?status=filled", headers=a["headers"]).json()
        self.assertEqual(filled["count"], 1)

    def test_kill_switch(self):
        a = self._agent()
        self._open_order(a, limit_price=60_000)
        with patch.dict(os.environ, {"RESTING_ORDERS_ENABLED": "false"}):
            with patch("crypto_feed.fetch_tickers") as mock_fetch:
                result = resting_orders.run_resting_orders_tick()
        self.assertEqual(result, {"checked": 0, "filled": 0, "rejected": 0})
        mock_fetch.assert_not_called()

    def test_quote_outage_leaves_orders_open(self):
        a = self._agent()
        self._open_order(a, limit_price=60_000)
        with patch("crypto_feed.fetch_tickers", side_effect=RuntimeError("down")):
            result = resting_orders.run_resting_orders_tick()
        self.assertEqual(result.get("error"), "tickers_unavailable")
        self.assertEqual(self.client.get("/api/orders", headers=a["headers"]).json()["count"], 1)


class GatewayBoundaryTests(unittest.TestCase):
    def test_engine_never_touches_the_live_gateway(self):
        """Simulator-only is a stated guarantee (real-gateway testing is
        planned): the module must not reference the execution layer."""
        src = (SERVER_DIR / "resting_orders.py").read_text()
        for needle in ("from execution", "import execution", "gateway."):
            self.assertNotIn(f"\n{needle}", src)


if __name__ == "__main__":
    unittest.main()
