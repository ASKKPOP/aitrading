"""Automation test-run gate preview ("would this have executed?").

preview_rule_execution applies the worker's exact gate chain (shared
evaluate_execution_gates) to an already-computed analysis, plus a read-only
cash/position feasibility check. It must never write: no signals row, no
position, no cash change.
"""

from __future__ import annotations

import json
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

import automation
import database
from routes import create_app

BUY_ANALYSIS = {
    "symbol": "BTC",
    "market": "crypto",
    "analysts": {"technical": {"brief": "t", "data": {"sigma_daily_pct": 2.5,
                                                      "current_price": 100.0}}},
    "decision": {"action": "buy", "confidence": 0.9, "entry": 100.0, "report": "r"},
}


class GatePreviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())
        resp = self.client.post(
            "/api/claw/agents/selfRegister",
            json={"name": "preview", "password": "pw123", "initial_balance": 100000.0})
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

    def _signal_count(self):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) AS n FROM signals WHERE agent_id = ?",
                        (self.agent_id,))
            return cur.fetchone()["n"]
        finally:
            conn.close()

    def test_would_execute_happy_path(self):
        out = automation.preview_rule_execution(self._config(), BUY_ANALYSIS)
        self.assertTrue(out["would_execute"])
        self.assertIsNone(out["skip_reason"])
        self.assertAlmostEqual(out["quantity"], 5.0)  # $500 / $100
        self.assertEqual(self._signal_count(), 0)  # preview never trades

    def test_auto_execute_off(self):
        out = automation.preview_rule_execution(self._config(auto_execute=0), BUY_ANALYSIS)
        self.assertFalse(out["would_execute"])
        self.assertEqual(out["skip_reason"], "auto_execute off")

    def test_confidence_below_threshold(self):
        out = automation.preview_rule_execution(
            self._config(min_confidence=0.95), BUY_ANALYSIS)
        self.assertFalse(out["would_execute"])
        self.assertIn("below threshold", out["skip_reason"])

    def test_hold_decision(self):
        analysis = dict(BUY_ANALYSIS)
        analysis["decision"] = {"action": "hold", "confidence": 0.9, "entry": 100.0}
        out = automation.preview_rule_execution(self._config(), analysis)
        self.assertFalse(out["would_execute"])
        self.assertEqual(out["skip_reason"], "decision is 'hold'")

    def test_sell_without_position(self):
        analysis = dict(BUY_ANALYSIS)
        analysis["decision"] = {"action": "sell", "confidence": 0.9, "entry": 100.0}
        out = automation.preview_rule_execution(self._config(), analysis)
        self.assertFalse(out["would_execute"])
        self.assertEqual(out["skip_reason"], "no long position to sell")

    def test_insufficient_cash(self):
        out = automation.preview_rule_execution(
            self._config(size_usd=1_000_000.0), BUY_ANALYSIS)
        self.assertFalse(out["would_execute"])
        self.assertIn("insufficient cash", out["skip_reason"])

    def test_worker_and_preview_agree(self):
        """The refactored run_rule and the preview must give the same verdict
        for the same analysis — that is the whole point of sharing the chain."""
        config = self._config()
        preview = automation.preview_rule_execution(config, BUY_ANALYSIS)
        with patch("analysis_agents.run_analysis", return_value=BUY_ANALYSIS):
            run = automation.run_rule(config)
        self.assertTrue(preview["would_execute"])
        self.assertTrue(run["executed"])
        self.assertIsNone(run["skip_reason"])


class StreamGatesEventTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.app = create_app()
        self.client = TestClient(self.app)
        resp = self.client.post(
            "/api/claw/agents/selfRegister",
            json={"name": "gates-stream", "password": "pw123",
                  "initial_balance": 100000.0})
        assert resp.status_code == 200, resp.text
        self.agent_id = resp.json()["agent_id"]
        self.token = resp.json()["token"]
        resp = self.client.post(
            "/api/automation/configs",
            json={"symbol": "BTC", "market": "crypto", "auto_execute": True,
                  "min_confidence": 0.5, "size_usd": 500, "interval_minutes": 60},
            headers={"Authorization": f"Bearer {self.token}"})
        assert resp.status_code == 200, resp.text
        self.config_id = resp.json()["id"]

    def tearDown(self):
        self.tmp.cleanup()

    def _stream(self, body):
        with self.client.stream("POST", "/api/analysis/run/stream", json=body,
                                headers={"Authorization": f"Bearer {self.token}"}) as res:
            assert res.status_code == 200, res.read()
            lines = [ln for ln in res.iter_lines() if ln.startswith("data: ")]
        return [json.loads(ln[6:]) for ln in lines]

    def test_stream_emits_gates_verdict_for_own_config(self):
        with patch("routes_analysis.run_analysis",
                   side_effect=lambda *a, **k: dict(BUY_ANALYSIS)):
            payloads = self._stream({"symbol": "BTC", "market": "crypto",
                                     "config_id": self.config_id})
        kinds = [p["event"] for p in payloads]
        self.assertIn("gates", kinds)
        self.assertEqual(kinds[-1], "result")
        self.assertLess(kinds.index("gates"), kinds.index("result"))
        gates = next(p for p in payloads if p["event"] == "gates")
        self.assertTrue(gates["would_execute"])
        self.assertAlmostEqual(gates["quantity"], 5.0)

    def test_no_gates_event_without_config_id(self):
        with patch("routes_analysis.run_analysis",
                   side_effect=lambda *a, **k: dict(BUY_ANALYSIS)):
            payloads = self._stream({"symbol": "BTC", "market": "crypto"})
        self.assertNotIn("gates", [p["event"] for p in payloads])

    def test_foreign_config_id_emits_no_gates(self):
        with patch("routes_analysis.run_analysis",
                   side_effect=lambda *a, **k: dict(BUY_ANALYSIS)):
            payloads = self._stream({"symbol": "BTC", "market": "crypto",
                                     "config_id": self.config_id + 999})
        self.assertNotIn("gates", [p["event"] for p in payloads])
        self.assertEqual(payloads[-1]["event"], "result")


if __name__ == "__main__":
    unittest.main()
