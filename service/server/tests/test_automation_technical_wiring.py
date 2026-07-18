"""automation.run_rule must read the technical block from the shape
run_analysis actually returns.

run_analysis returns its per-analyst payloads nested under "analysts":

    {"analysts": {"technical": {"brief": ..., "data": {...}}}, "decision": {...}}

automation.py read ``analysis.get("technical")`` — a key that never exists —
so ``technical`` was always None. Two consequences, both covered here:

  * ``sigma_daily_pct`` never reached ``evaluate_order``. With
    VOL_SIZING_ENABLED the gate rejects on missing sigma, so vol sizing
    rejected 100% of buys.
  * ``evaluate_confluence`` was called with analysis=None, making it refetch
    (crypto) or run without technical data at all (us-stock).
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
from routes import create_app

# The exact shape analysis_agents.run_analysis returns.
REAL_ANALYSIS = {
    "symbol": "BTC",
    "market": "crypto",
    "analysts": {
        "technical": {
            "brief": "t",
            "data": {"sigma_daily_pct": 2.5, "rsi_14": 55.0, "current_price": 100.0},
        },
    },
    "decision": {"action": "buy", "confidence": 0.9, "entry": 100.0, "report": "r"},
}


class AutomationTechnicalWiringTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())
        resp = self.client.post(
            "/api/claw/agents/selfRegister",
            json={"name": "wiring", "password": "pw123", "initial_balance": 100000.0})
        assert resp.status_code == 200, resp.text
        self.agent_id = resp.json()["agent_id"]

    def tearDown(self):
        self.tmp.cleanup()

    def _config(self, **overrides):
        base = {"id": 1, "agent_id": self.agent_id, "symbol": "BTC", "market": "crypto",
                "interval_minutes": 60, "min_confidence": 0.5, "size_usd": 500.0,
                "auto_execute": 1, "account_type": "simulator"}
        base.update(overrides)
        return base

    def test_daily_sigma_reaches_the_risk_gate(self):
        """The gate must receive the sigma the technical analyst produced."""
        import automation

        captured = {}

        def fake_evaluate_order(*args, **kwargs):
            captured.update(kwargs)
            from risk_engine import GateDecision
            return GateDecision(allowed=False, quantity=0.0, reason="stop here")

        with patch("analysis_agents.run_analysis", return_value=REAL_ANALYSIS), \
             patch("risk_engine.evaluate_order", side_effect=fake_evaluate_order):
            automation.run_rule(self._config())

        self.assertEqual(captured.get("sigma_daily_pct"), 2.5)

    def test_confluence_receives_the_technical_payload(self):
        """Confluence must reuse the analysis already computed, not None."""
        import automation

        seen = {}

        def fake_confluence(symbol, market="crypto", *, analysis=None, psych=None):
            seen["analysis"] = analysis
            return {"conditions": {}, "score": 0}

        with patch("analysis_agents.run_analysis", return_value=REAL_ANALYSIS), \
             patch("confluence.evaluate_confluence", side_effect=fake_confluence):
            automation.run_rule(self._config())

        self.assertIsNotNone(seen.get("analysis"))
        self.assertEqual(seen["analysis"].get("sigma_daily_pct"), 2.5)


if __name__ == "__main__":
    unittest.main()
