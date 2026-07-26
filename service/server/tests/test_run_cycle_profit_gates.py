"""Wiring tests for the 2026-07-26 profit-leak gates inside run_cycle.

The pure predicates are unit-tested in test_fee_edge_gate.py and
test_confidence_rank.py; these prove they are actually CONSULTED by the cycle
and produce a journaled gate_skip instead of a trade. Without them the gates
could be deleted from run_cycle and every other test would still pass.
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

import database
import run_engine
from routes import create_app


def _analysis(action="buy", confidence=0.9):
    return {
        "symbol": "BTC", "market": "crypto",
        "analysts": {"technical": {"brief": "t",
                                   "data": {"sigma_daily_pct": 2.5,
                                            "current_price": 100.0}}},
        "decision": {"action": action, "confidence": confidence,
                     "entry": 100.0, "report": "r"},
    }


class RunCycleProfitGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        os.environ["AUTO_TRADING_ENABLED"] = "true"
        # Percentile grading off by default here so the fee tests isolate one
        # gate at a time; the percentile test switches it on explicitly.
        os.environ["RUN_CONF_PERCENTILE"] = "false"
        self.probe = patch("routes_runs._probe_price", return_value=100.0)
        self.probe.start()
        self.client = TestClient(create_app())
        resp = self.client.post(
            "/api/claw/agents/selfRegister",
            json={"name": "gate-agent", "password": "pw123",
                  "initial_balance": 100000.0})
        assert resp.status_code == 200, resp.text
        self.token = resp.json()["token"]
        self.agent_id = resp.json()["agent_id"]

    def tearDown(self):
        self.probe.stop()
        for key in ("AUTO_TRADING_ENABLED", "RUN_CONF_PERCENTILE",
                    "RUN_FEE_EDGE_MULTIPLE", "RUN_CONF_PERCENTILE_MIN_SAMPLES"):
            os.environ.pop(key, None)
        self.tmp.cleanup()

    def _h(self):
        return {"Authorization": f"Bearer {self.token}"}

    def _run(self, **overrides) -> int:
        payload = {"symbol": "BTC", "market": "crypto", "max_bet_usd": 500.0}
        payload.update(overrides)
        run_id = self.client.post("/api/runs", json=payload,
                                  headers=self._h()).json()["id"]
        assert self.client.post(f"/api/runs/{run_id}/start",
                                headers=self._h()).status_code == 200
        return run_id

    def _set_thesis(self, run_id, expected_move_pct):
        """Stamp a thesis into the run's config snapshot, as the fleet does."""
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT config_snapshot_json FROM trading_runs WHERE id = ?",
                        (run_id,))
            cfg = json.loads(cur.fetchone()["config_snapshot_json"] or "{}")
            cfg["thesis"] = {"symbol": "BTC", "expected_move_pct": expected_move_pct}
            database.begin_write_transaction(cur)
            cur.execute("UPDATE trading_runs SET config_snapshot_json = ? WHERE id = ?",
                        (json.dumps(cfg), run_id))
            conn.commit()
        finally:
            conn.close()

    def _skips(self, run_id, stage):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT payload FROM run_events WHERE run_id = ? "
                        "AND event_type = 'gate_skip'", (run_id,))
            return [json.loads(r["payload"]) for r in cur.fetchall()
                    if json.loads(r["payload"]).get("stage") == stage]
        finally:
            conn.close()

    # ── fee/edge gate ──────────────────────────────────────────────────

    def test_thin_expected_move_is_refused_before_the_trade(self):
        run_id = self._run()
        self._set_thesis(run_id, 0.44)        # the ZEC-sized move: < 0.6% hurdle
        with patch("analysis_agents.run_analysis", return_value=_analysis()):
            result = run_engine.run_cycle(run_id)
        self.assertFalse(result["executed"])
        self.assertIn("fee_edge", result["skip_reason"])
        self.assertEqual(len(self._skips(run_id, "fee_edge")), 1,
                         "the refusal must be journaled for the operator")

    def test_fat_expected_move_still_trades(self):
        run_id = self._run()
        self._set_thesis(run_id, 5.0)
        with patch("analysis_agents.run_analysis", return_value=_analysis()):
            result = run_engine.run_cycle(run_id)
        self.assertTrue(result["executed"], result.get("skip_reason"))

    def test_run_without_a_thesis_is_unaffected(self):
        """Manual runs state no expected move and must not be gated."""
        run_id = self._run()
        with patch("analysis_agents.run_analysis", return_value=_analysis()):
            result = run_engine.run_cycle(run_id)
        self.assertTrue(result["executed"], result.get("skip_reason"))

    def test_exit_is_never_fee_gated(self):
        """Closing only reduces risk — a thin move must not trap a position."""
        run_id = self._run()
        self._set_thesis(run_id, 5.0)
        with patch("analysis_agents.run_analysis", return_value=_analysis("buy")):
            self.assertTrue(run_engine.run_cycle(run_id)["executed"])
        self._set_thesis(run_id, 0.01)        # far below the hurdle
        with patch("analysis_agents.run_analysis", return_value=_analysis("sell")):
            result = run_engine.run_cycle(run_id)
        self.assertTrue(result["executed"], result.get("skip_reason"))

    # ── confidence rank gate ───────────────────────────────────────────

    def test_mid_pack_confidence_is_refused_by_rank(self):
        run_id = self._run()
        os.environ["RUN_CONF_PERCENTILE"] = "true"
        os.environ["RUN_CONF_PERCENTILE_MIN_SAMPLES"] = "10"
        conn = database.get_db_connection()
        cur = conn.cursor()
        for i in range(30):                   # history the decision must beat
            cur.execute(
                "INSERT INTO run_events (run_id, seq, event_type, ts, payload)"
                " VALUES (?, ?, 'decision', '2026-01-01T00:00:00Z', ?)",
                (run_id, 5000 + i, json.dumps({"confidence": 0.95})))
        conn.commit()
        conn.close()
        with patch("analysis_agents.run_analysis",
                   return_value=_analysis(confidence=0.60)):
            result = run_engine.run_cycle(run_id)
        self.assertFalse(result["executed"])
        self.assertIn("ranks", result["skip_reason"])
        self.assertEqual(len(self._skips(run_id, "confidence_rank")), 1)


if __name__ == "__main__":
    unittest.main()
