"""US-stock shorts inside runs and fleets (owner 2026-11-20: "Build it").

A US-stock short lives on a 'margin' book (short-sale): market_type='margin'
is valid only on market 'us-stock', and trading_runs.is_futures_book (the
engine's one "short-capable book" predicate) is True for it, so run_cycle maps
a 'sell' with no long to 'short' and a 'buy' while short to 'cover' — the
same mapping a crypto perp run uses. Research marks a US-stock short thesis
expressible, and the fleet composer gives it a 1x margin run.

Runs with the platform block ON and the shorts switch unset (the production
default after the two-way change).
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
import futures_policy
import markets
import run_engine
import symbol_research
import trading_runs
from routes import create_app


def _analysis(action):
    return {"symbol": "AAPL", "market": "us-stock",
            "analysts": {"technical": {"brief": "t", "data": {
                "sigma_daily_pct": 1.5, "current_price": 100.0}}},
            "decision": {"action": action, "confidence": 0.9, "entry": 100.0,
                         "report": "r"}}


class MarginBookTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.env = patch.dict(os.environ, {"AUTO_TRADING_ENABLED": "true",
                                           "FUTURES_TRADING_BLOCKED": "1"})
        self.env.start()
        os.environ.pop("SHORTS_TRADING_BLOCKED", None)
        self.patches = [patch("routes_runs._probe_price", return_value=100.0),
                        patch.object(markets, "is_market_open", return_value=True),
                        patch("entitlements.check_futures_access", return_value=None)]
        for p in self.patches:
            p.start()
        self.client = TestClient(create_app())
        resp = self.client.post("/api/claw/agents/selfRegister",
                                json={"name": "margin-agent", "password": "pw123",
                                      "initial_balance": 100000.0})
        assert resp.status_code == 200, resp.text
        self.token = resp.json()["token"]
        self.agent_id = resp.json()["agent_id"]

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.env.stop()
        self.tmp.cleanup()

    def _h(self):
        return {"Authorization": f"Bearer {self.token}"}

    def _create(self, **over):
        payload = {"symbol": "AAPL", "market": "us-stock", "market_type": "margin",
                   "max_bet_usd": 500.0}
        payload.update(over)
        return self.client.post("/api/runs", json=payload, headers=self._h())

    def _running(self, **over):
        resp = self._create(**over)
        assert resp.status_code == 200, resp.text
        run_id = resp.json()["id"]
        resp = self.client.post(f"/api/runs/{run_id}/start", headers=self._h())
        assert resp.status_code == 200, resp.text
        return run_id

    def _qty(self):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT quantity FROM positions WHERE agent_id = ? "
                        "AND symbol = 'AAPL'", (self.agent_id,))
            row = cur.fetchone()
            return float(row["quantity"]) if row else 0.0
        finally:
            conn.close()

    def _sides(self, run_id):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT side FROM signals WHERE run_id = ? ORDER BY id", (run_id,))
            return [r["side"] for r in cur.fetchall()]
        finally:
            conn.close()

    def test_margin_is_a_short_capable_book(self):
        self.assertTrue(trading_runs.is_futures_book("us-stock", "margin"))
        self.assertFalse(trading_runs.is_futures_book("us-stock", "spot"))

    def test_margin_sell_opens_a_short_and_buy_covers(self):
        run_id = self._running()
        with patch("analysis_agents.run_analysis", return_value=_analysis("sell")):
            result = run_engine.run_cycle(run_id)
        self.assertTrue(result["executed"], result)
        self.assertLess(self._qty(), 0.0)
        with patch("analysis_agents.run_analysis", return_value=_analysis("buy")):
            result = run_engine.run_cycle(run_id)
        self.assertTrue(result["executed"], result)
        self.assertEqual(self._sides(run_id), ["short", "cover"])
        self.assertEqual(self._qty(), 0.0)

    def test_spot_us_stock_sell_with_no_long_still_skips(self):
        run_id = self._running(market_type="spot")
        with patch("analysis_agents.run_analysis", return_value=_analysis("sell")):
            result = run_engine.run_cycle(run_id)
        self.assertFalse(result["executed"], result)
        self.assertEqual(self._sides(run_id), [])

    def test_margin_only_on_us_stock(self):
        for market, symbol in (("crypto", "BTC"), ("forex", "EURUSD")):
            resp = self._create(market=market, symbol=symbol)
            self.assertIn(resp.status_code, (400, 403, 422), resp.text)
        self.assertIsNotNone(futures_policy.run_refusal("crypto", "margin"))
        self.assertIsNone(futures_policy.run_refusal("us-stock", "margin"))
        self.assertIsNotNone(futures_policy.order_refusal(
            "crypto", "short", market_type="margin"))

    def test_margin_refused_when_long_only_is_re_armed(self):
        with patch.dict(os.environ, {"SHORTS_TRADING_BLOCKED": "1"}):
            self.assertIn("margin", futures_policy.run_refusal("us-stock", "margin"))
            self.assertEqual(futures_policy.thesis_refusal("us-stock", "short"),
                             "futures_blocked")

    def test_margin_leverage_still_refused(self):
        self.assertIn("leveraged", futures_policy.run_refusal("us-stock", "margin", 2.0))

    def test_junior_plan_cannot_open_a_margin_run(self):
        import entitlements
        self.patches[2].stop()
        try:
            with patch.object(entitlements, "_resolved_plan_for_agent",
                              return_value="junior"):
                self.assertIsNotNone(entitlements.check_futures_access(1, "margin", 1.0))
                self.assertIsNone(entitlements.check_futures_access(1, "spot", 1.0))
        finally:
            self.patches[2].start()

    def test_research_marks_a_us_stock_short_expressible(self):
        self.assertEqual(symbol_research.thesis_market_type("us-stock", "short"), "margin")
        self.assertTrue(symbol_research.thesis_is_expressible("us-stock", "short"))
        self.assertEqual(symbol_research.thesis_market_type("crypto", "short"), "futures")
        self.assertEqual(symbol_research.thesis_market_type("us-stock", "long"), "spot")

    def test_fleet_composes_a_us_stock_short_to_a_1x_margin_run(self):
        import fleet_planner as fp
        thesis = {"symbol": "AAPL", "market": "us-stock", "direction": "short",
                  "market_type": "spot",   # an older batch row stored 'spot'
                  "confidence": 0.7, "expected_move_pct": 3.0, "horizon_hours": 12}
        fleet = {"agent_id": self.agent_id, "risk_appetite": "aggressive",
                 "total_budget_usd": 10000, "n_runs": 4}
        s = fp.compose_run_settings(thesis, 2500.0, fleet)
        self.assertEqual((s["market_type"], s["leverage"]), ("margin", 1.0))
        self.assertIsNone(futures_policy.run_refusal(s["market"], s["market_type"],
                                                     s["leverage"]))


if __name__ == "__main__":
    unittest.main()
