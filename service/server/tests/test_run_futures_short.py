"""Futures runs translate desk direction into the futures book (Plan 10 D5).

Regression: ISSUE-002 — no decision path ever emits 'short' (trader prompt and
rule-based fallback both produce buy|sell|hold), so a futures run's bearish
'sell' with no long position skipped with "no long position to sell" and a
futures run could never trade at all. run_cycle now maps, for futures runs
only: sell with no long -> short (open), buy while short -> cover (close).
Found by /qa on 2026-07-19.
Report: .gstack/qa-reports/qa-report-sooppiy-local-2026-07-19.md
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
import run_engine
from routes import create_app

SELL_ANALYSIS = {
    "symbol": "BTC",
    "market": "crypto",
    "analysts": {"technical": {"brief": "t", "data": {"sigma_daily_pct": 2.5,
                                                      "current_price": 100.0}}},
    "decision": {"action": "sell", "confidence": 0.9, "entry": 100.0, "report": "r"},
}

BUY_ANALYSIS = {
    "symbol": "BTC",
    "market": "crypto",
    "analysts": {"technical": {"brief": "t", "data": {"sigma_daily_pct": 2.5,
                                                      "current_price": 100.0}}},
    "decision": {"action": "buy", "confidence": 0.9, "entry": 100.0, "report": "r"},
}


class FuturesShortMappingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        os.environ["AUTO_TRADING_ENABLED"] = "true"
        self.probe = patch("routes_runs._probe_price", return_value=100.0)
        self.probe.start()
        self.client = TestClient(create_app())
        resp = self.client.post(
            "/api/claw/agents/selfRegister",
            json={"name": "futures-agent", "password": "pw123",
                  "initial_balance": 100000.0})
        assert resp.status_code == 200, resp.text
        self.token = resp.json()["token"]
        self.agent_id = resp.json()["agent_id"]

    def tearDown(self):
        self.probe.stop()
        os.environ.pop("AUTO_TRADING_ENABLED", None)
        self.tmp.cleanup()

    def _h(self):
        return {"Authorization": f"Bearer {self.token}"}

    def _running_run(self, **overrides) -> int:
        payload = {"symbol": "BTC", "market": "crypto", "max_bet_usd": 500.0}
        payload.update(overrides)
        run_id = self.client.post("/api/runs", json=payload,
                                  headers=self._h()).json()["id"]
        resp = self.client.post(f"/api/runs/{run_id}/start", headers=self._h())
        assert resp.status_code == 200, resp.text
        return run_id

    def _signals(self, run_id):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM signals WHERE run_id = ? ORDER BY id", (run_id,))
            return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

    def _position_qty(self):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT quantity FROM positions WHERE agent_id = ? AND symbol = 'BTC'",
                (self.agent_id,))
            row = cur.fetchone()
            return float(row["quantity"]) if row else 0.0
        finally:
            conn.close()

    def test_futures_sell_with_no_long_opens_short(self):
        run_id = self._running_run(market_type="futures")
        with patch("analysis_agents.run_analysis", return_value=SELL_ANALYSIS):
            result = run_engine.run_cycle(run_id)
        self.assertTrue(result["executed"], result)
        signals = self._signals(run_id)
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0]["side"], "short")
        self.assertLess(self._position_qty(), 0.0)

    def test_futures_buy_while_short_covers(self):
        run_id = self._running_run(market_type="futures")
        with patch("analysis_agents.run_analysis", return_value=SELL_ANALYSIS):
            run_engine.run_cycle(run_id)
        self.assertLess(self._position_qty(), 0.0)
        with patch("analysis_agents.run_analysis", return_value=BUY_ANALYSIS):
            result = run_engine.run_cycle(run_id)
        self.assertTrue(result["executed"], result)
        sides = [s["side"] for s in self._signals(run_id)]
        self.assertEqual(sides, ["short", "cover"])
        self.assertEqual(self._position_qty(), 0.0)

    def test_spot_sell_with_no_long_still_skips(self):
        # Plan 15 P1 (F4): the empty-book spot sell now skips BEFORE the risk
        # gates with an explicit hold reason, instead of reaching the execute
        # stage and failing with "no long position to sell".
        run_id = self._running_run()  # market_type defaults to spot
        with patch("analysis_agents.run_analysis", return_value=SELL_ANALYSIS):
            result = run_engine.run_cycle(run_id)
        self.assertFalse(result["executed"], result)
        self.assertIn("spot sell with no inventory", result["skip_reason"] or "")
        self.assertEqual(self._signals(run_id), [])

    def test_spot_sell_with_long_still_reduces(self):
        # The pre-gate hold must NOT block a legitimate sell of a real long.
        run_id = self._running_run()
        with patch("analysis_agents.run_analysis", return_value=BUY_ANALYSIS):
            result = run_engine.run_cycle(run_id)
        self.assertTrue(result["executed"], result)
        self.assertGreater(self._position_qty(), 0.0)
        with patch("analysis_agents.run_analysis", return_value=SELL_ANALYSIS):
            result = run_engine.run_cycle(run_id)
        self.assertTrue(result["executed"], result)
        sides = [s["side"] for s in self._signals(run_id)]
        self.assertEqual(sides, ["buy", "sell"])


if __name__ == "__main__":
    unittest.main()
