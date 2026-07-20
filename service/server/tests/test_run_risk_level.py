"""Run creation with an exit profile (POST /api/runs, risk_level).

The Automation page's ⓪ 완전 위임 and ① 간편 modes create a TRADING run rather
than an automation rule — a run already carries interval/confidence/size and
cycles on its own, and creating both would deadlock on the start conflict that
refuses a run when an auto-executing rule targets the same symbol.

Simple mode advertises "SL −3% · TP +6%" on its preset cards, which the rule
path used to deliver by expanding risk_level into the agent's risk_limits.
These tests pin that the run path delivers the same thing, so the cards stay
true, and that the preset table is never duplicated client-side.
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
from routes_automation import RISK_LEVEL_PRESETS


def _body(**over) -> dict:
    base = {"symbol": "BTC", "market": "crypto", "market_type": "spot",
            "max_bet_usd": 200.0, "interval_minutes": 240,
            "min_confidence": 0.75}
    base.update(over)
    return base


class RunRiskLevelTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.probe = patch("routes_runs._probe_price", return_value=100.0)
        self.probe.start()
        self.client = TestClient(create_app())
        resp = self.client.post(
            "/api/claw/agents/selfRegister",
            json={"name": "risk-level-agent", "password": "pw123",
                  "initial_balance": 100000.0})
        self.token = resp.json()["token"]
        self.agent_id = resp.json()["agent_id"]
        self.auth = {"Authorization": f"Bearer {self.token}"}

    def tearDown(self):
        self.probe.stop()
        self.tmp.cleanup()

    def test_risk_level_applies_the_matching_exit_profile(self):
        """The advertised SL/TP lands in risk_limits, from the server's table."""
        r = self.client.post("/api/runs", json=_body(risk_level="stable"),
                             headers=self.auth)
        self.assertEqual(r.status_code, 200, r.text)
        preset = RISK_LEVEL_PRESETS["stable"]
        limits = r.json()["risk_limits"]
        self.assertIsNotNone(limits, "risk_level must echo the applied limits")
        self.assertAlmostEqual(limits["stop_loss_pct"], preset["stop_loss_pct"])
        self.assertAlmostEqual(limits["take_profit_pct"], preset["take_profit_pct"])

        # And it is persisted on the agent, not just echoed back.
        got = self.client.get("/api/risk/limits", headers=self.auth).json()["limits"]
        self.assertAlmostEqual(got["stop_loss_pct"], preset["stop_loss_pct"])
        self.assertAlmostEqual(got["take_profit_pct"], preset["take_profit_pct"])

    def test_each_preset_is_distinct_and_reachable(self):
        """All three simple-mode cards map to a real, different profile."""
        seen = []
        for level in ("stable", "balanced", "aggressive"):
            r = self.client.post(
                "/api/runs",
                # A distinct symbol per run: exclusivity is per agent+symbol.
                json=_body(symbol=f"T{level[:3].upper()}", risk_level=level),
                headers=self.auth)
            self.assertEqual(r.status_code, 200, r.text)
            limits = r.json()["risk_limits"]
            seen.append((limits["stop_loss_pct"], limits["take_profit_pct"]))
        self.assertEqual(len(set(seen)), 3, f"presets collapsed: {seen}")

    def test_omitting_risk_level_leaves_limits_untouched(self):
        """The field is optional — the normal create path must not write."""
        before = self.client.get("/api/risk/limits", headers=self.auth).json()["limits"]
        r = self.client.post("/api/runs", json=_body(), headers=self.auth)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIsNone(r.json()["risk_limits"])
        after = self.client.get("/api/risk/limits", headers=self.auth).json()["limits"]
        self.assertEqual(before, after)

    def test_unknown_risk_level_is_refused(self):
        r = self.client.post("/api/runs", json=_body(risk_level="yolo"),
                             headers=self.auth)
        self.assertEqual(r.status_code, 422, r.text)

    def test_run_is_created_as_a_draft_not_an_automation_rule(self):
        """The whole point of the change: a run, and no rule to conflict with."""
        r = self.client.post("/api/runs", json=_body(risk_level="balanced"),
                             headers=self.auth)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["run"]["status"], "draft")

        configs = self.client.get("/api/automation/configs",
                                  headers=self.auth).json()["configs"]
        self.assertEqual(configs, [], "creating a run must not create a rule")

        # With no rule on the symbol, the run starts instead of 409-ing on a
        # conflict it created itself.
        start = self.client.post(f"/api/runs/{r.json()['id']}/start",
                                 headers=self.auth)
        self.assertEqual(start.status_code, 200, start.text)


if __name__ == "__main__":
    unittest.main()
