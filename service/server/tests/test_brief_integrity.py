"""Plan 21 P2 — brief integrity: the desk is told its frozen brief's age.

The :496026 incident class was a stale research brief whose levels the desk
read as current. The contract (ported from the hermes work-package's
data-freshness rule): the fleet thesis snapshot carries the research row's
authorship time (`as_of`), and the light decision prompt renders an explicit
age line with a fresh / aging / STALE label. No `as_of` (manual runs,
pre-P2 fleets) renders nothing — never a wrong number.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
import fleet_planner
import run_engine
from routes import create_app

TS_FMT = "%Y-%m-%dT%H:%M:%SZ"


def _iso_hours_ago(hours: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime(TS_FMT)


class FreshnessLineTests(unittest.TestCase):
    def test_fresh_brief(self):
        line = run_engine._thesis_freshness_line({"as_of": _iso_hours_ago(1.0)})
        self.assertIn("Thesis brief age:", line)
        self.assertIn("(fresh)", line)

    def test_aging_brief(self):
        line = run_engine._thesis_freshness_line({"as_of": _iso_hours_ago(12.0)})
        self.assertIn("aging", line)
        self.assertNotIn("STALE", line)

    def test_stale_brief(self):
        line = run_engine._thesis_freshness_line({"as_of": _iso_hours_ago(48.0)})
        self.assertIn("STALE", line)
        self.assertIn("48.0h", line)

    def test_missing_or_malformed_renders_nothing(self):
        self.assertEqual(run_engine._thesis_freshness_line({}), "")
        self.assertEqual(run_engine._thesis_freshness_line({"as_of": None}), "")
        self.assertEqual(
            run_engine._thesis_freshness_line({"as_of": "not-a-time"}), "")
        self.assertEqual(run_engine._thesis_freshness_line("not-a-dict"), "")

    def test_future_stamp_renders_nothing(self):
        future = (datetime.now(timezone.utc) + timedelta(hours=5)).strftime(TS_FMT)
        self.assertEqual(run_engine._thesis_freshness_line({"as_of": future}), "")


class SnapshotProvenanceTests(unittest.TestCase):
    def test_compose_run_settings_stamps_as_of(self):
        thesis = {
            "symbol": "BTC", "market": "crypto", "market_type": "futures",
            "direction": "long", "confidence": 0.6, "expected_move_pct": 2.5,
            "horizon_hours": 48, "thesis": "t", "invalidation": "below x",
            "batch_id": "b1", "planner": "llm",
            "created_at": "2026-08-01T00:00:00Z",
        }
        cfg = fleet_planner.compose_run_settings(
            thesis, 1000.0, {"risk_appetite": "balanced"})
        self.assertEqual(cfg["thesis"]["as_of"], "2026-08-01T00:00:00Z")

    def test_compose_run_settings_tolerates_missing_created_at(self):
        thesis = {
            "symbol": "BTC", "market": "crypto", "market_type": "futures",
            "direction": "long", "confidence": 0.6, "expected_move_pct": 2.5,
            "horizon_hours": 48, "thesis": "t", "invalidation": "below x",
        }
        cfg = fleet_planner.compose_run_settings(
            thesis, 1000.0, {"risk_appetite": "balanced"})
        self.assertIsNone(cfg["thesis"]["as_of"])


class LightPromptRendersAgeTests(unittest.TestCase):
    """The line must actually reach the LLM — wiring, not just the helper."""

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
            json={"name": "p2-agent", "password": "pw123",
                  "initial_balance": 100000.0})
        assert resp.status_code == 200, resp.text
        self.token = resp.json()["token"]

    def tearDown(self):
        self.probe.stop()
        os.environ.pop("AUTO_TRADING_ENABLED", None)
        self.tmp.cleanup()

    def _light_run_with_thesis(self, thesis: dict) -> int:
        h = {"Authorization": f"Bearer {self.token}"}
        run_id = self.client.post(
            "/api/runs", json={"symbol": "BTC", "market": "crypto",
                               "max_bet_usd": 500.0}, headers=h).json()["id"]
        assert self.client.post(f"/api/runs/{run_id}/start",
                                headers=h).status_code == 200
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT config_snapshot_json FROM trading_runs "
                        "WHERE id = ?", (run_id,))
            cfg = json.loads(cur.fetchone()["config_snapshot_json"] or "{}")
            cfg["cycle_mode"] = "light"
            cfg["thesis"] = thesis
            database.begin_write_transaction(cur)
            cur.execute("UPDATE trading_runs SET config_snapshot_json = ?, "
                        "created_via = 'fleet' WHERE id = ?",
                        (json.dumps(cfg), run_id))
            conn.commit()
        finally:
            conn.close()
        return run_id

    def _prompt_for(self, thesis: dict) -> str:
        seen = {}

        def cap(prompt, **kw):
            seen["p"] = prompt
            return '{"action":"hold","confidence":0.5}'

        run_id = self._light_run_with_thesis(thesis)
        with patch("llm_client.generate_text", side_effect=cap), \
             patch("price_fetcher.get_price_from_market", return_value=100.0), \
             patch("price_fetcher.get_daily_candles", return_value=[]):
            run_engine.run_cycle(run_id)
        return seen.get("p", "")

    def test_stale_brief_labeled_in_prompt(self):
        prompt = self._prompt_for({
            "direction": "long", "expected_move_pct": 2.0,
            "invalidation": "below the recent range",
            "as_of": _iso_hours_ago(72.0),
        })
        self.assertIn("Thesis brief age:", prompt)
        self.assertIn("STALE", prompt)

    def test_no_as_of_no_line(self):
        prompt = self._prompt_for({
            "direction": "long", "expected_move_pct": 2.0,
            "invalidation": "below the recent range",
        })
        self.assertIn("Thesis:", prompt)  # the brief itself still renders
        self.assertNotIn("Thesis brief age:", prompt)


if __name__ == "__main__":
    unittest.main()
