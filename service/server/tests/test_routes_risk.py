"""Risk API routes (Phase 1) — /api/risk/limits, /api/risk/breaker, halt/resume."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
from routes import create_app


class RiskRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())
        resp = self.client.post(
            "/api/claw/agents/selfRegister",
            json={"name": "risk-api-agent", "password": "pw123", "initial_balance": 100000.0},
        )
        assert resp.status_code == 200, resp.text
        self.token = resp.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def tearDown(self) -> None:
        self.tmp.cleanup()

    # ── auth ─────────────────────────────────────────────────────────────

    def test_risk_endpoints_require_auth(self):
        self.assertEqual(self.client.get("/api/risk/limits").status_code, 401)
        self.assertEqual(self.client.put("/api/risk/limits", json={}).status_code, 401)
        self.assertEqual(self.client.get("/api/risk/breaker").status_code, 401)
        self.assertEqual(self.client.post("/api/risk/halt", json={}).status_code, 401)
        self.assertEqual(self.client.post("/api/risk/resume").status_code, 401)

    # ── limits ───────────────────────────────────────────────────────────

    def test_get_limits_returns_defaults(self):
        resp = self.client.get("/api/risk/limits", headers=self.headers)
        self.assertEqual(resp.status_code, 200)
        limits = resp.json()["limits"]
        self.assertEqual(limits["max_daily_loss_usd"], 1000)
        self.assertEqual(limits["max_symbol_exposure_usd"], 10000)
        self.assertEqual(limits["stop_loss_pct"], 0.05)
        self.assertEqual(limits["take_profit_pct"], 0.10)
        self.assertEqual(limits["use_kelly"], 1)

    def test_put_limits_partial_update_persists(self):
        resp = self.client.put(
            "/api/risk/limits",
            json={"max_daily_loss_usd": 250, "use_kelly": False},
            headers=self.headers,
        )
        self.assertEqual(resp.status_code, 200)
        limits = resp.json()["limits"]
        self.assertEqual(limits["max_daily_loss_usd"], 250)
        self.assertEqual(limits["use_kelly"], 0)
        # untouched keys keep their defaults
        self.assertEqual(limits["stop_loss_pct"], 0.05)
        # persisted across reads
        again = self.client.get("/api/risk/limits", headers=self.headers).json()["limits"]
        self.assertEqual(again["max_daily_loss_usd"], 250)
        self.assertEqual(again["use_kelly"], 0)

    def test_put_limits_validation(self):
        resp = self.client.put(
            "/api/risk/limits", json={"stop_loss_pct": 1.5}, headers=self.headers)
        self.assertEqual(resp.status_code, 422)
        resp = self.client.put(
            "/api/risk/limits", json={"max_daily_loss_usd": -5}, headers=self.headers)
        self.assertEqual(resp.status_code, 422)

    # ── breaker ──────────────────────────────────────────────────────────

    def test_halt_and_resume_cycle(self):
        # initial state: normal
        resp = self.client.get("/api/risk/breaker", headers=self.headers)
        self.assertEqual(resp.status_code, 200)
        breaker = resp.json()["breaker"]
        self.assertEqual(breaker["global"]["state"], "normal")
        self.assertEqual(breaker["agent"]["state"], "normal")

        # halt trips the agent scope only
        resp = self.client.post("/api/risk/halt", json={"reason": "stepping away"},
                                headers=self.headers)
        self.assertEqual(resp.status_code, 200)
        breaker = self.client.get("/api/risk/breaker", headers=self.headers).json()["breaker"]
        self.assertEqual(breaker["agent"]["state"], "halted")
        self.assertEqual(breaker["agent"]["reason"], "stepping away")
        self.assertEqual(breaker["global"]["state"], "normal")

        # resume clears it
        resp = self.client.post("/api/risk/resume", headers=self.headers)
        self.assertEqual(resp.status_code, 200)
        breaker = self.client.get("/api/risk/breaker", headers=self.headers).json()["breaker"]
        self.assertEqual(breaker["agent"]["state"], "normal")

    def test_halt_only_affects_own_agent(self):
        other = self.client.post(
            "/api/claw/agents/selfRegister",
            json={"name": "other-agent", "password": "pw123", "initial_balance": 1000.0},
        ).json()
        self.client.post("/api/risk/halt", json={}, headers=self.headers)
        breaker = self.client.get(
            "/api/risk/breaker",
            headers={"Authorization": f"Bearer {other['token']}"},
        ).json()["breaker"]
        self.assertEqual(breaker["agent"]["state"], "normal")


if __name__ == "__main__":
    unittest.main()
