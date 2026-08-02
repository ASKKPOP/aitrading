"""Tier feature gates (Henry, 2026-08-02) — the shape of the paid tiers.

Junior: spot-only (no futures market_type, no leverage), system default AI
only, no one-off AI Analyst. Pro: those unlock, but N-symbol Full Auto
fleets are Professional+. All gates are ALWAYS-ON (not behind
ENTITLEMENTS_ENFORCED), like the fleet-size gate before them.
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


class TierFeatureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        # Deliberately NOT setting ENTITLEMENTS_ENFORCED: these gates must
        # hold with the flag off (prod runs with it off).
        os.environ.pop("ENTITLEMENTS_ENFORCED", None)
        self.probe = patch("routes_runs._probe_price", return_value=100.0)
        self.probe.start()
        self.client = TestClient(create_app())
        resp = self.client.post(
            "/api/claw/agents/selfRegister",
            json={"name": "tier-agent", "password": "pw123",
                  "initial_balance": 100000.0})
        self.token = resp.json()["token"]
        self.agent_id = resp.json()["agent_id"]
        self.user_id = self._link_user()

    def tearDown(self):
        self.probe.stop()
        self.tmp.cleanup()

    def _h(self):
        return {"Authorization": f"Bearer {self.token}"}

    def _link_user(self):
        from utils import hash_password
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            database.begin_write_transaction(cur)
            cur.execute("INSERT INTO users (email, password_hash) "
                        "VALUES ('tier@test.dev', ?)",
                        (hash_password("testpass123"),))
            user_id = cur.lastrowid
            cur.execute("UPDATE agents SET user_id = ? WHERE id = ?",
                        (user_id, self.agent_id))
            conn.commit()
            return user_id
        finally:
            conn.close()

    def _user_h(self):
        r = self.client.post("/api/users/login",
                             json={"email": "tier@test.dev",
                                   "password": "testpass123"})
        self.assertEqual(r.status_code, 200, r.text)
        return {"Authorization": f"Bearer {r.json()['token']}"}

    def _create_run(self, **overrides):
        payload = {"symbol": "BTC", "market": "crypto", "max_bet_usd": 100.0}
        payload.update(overrides)
        return self.client.post("/api/runs", json=payload, headers=self._h())

    # ── Junior is spot-only ────────────────────────────────────────────

    def test_junior_cannot_create_leveraged_run(self):
        # Leveraged SPOT is refused for everyone by the #129 guard (400), so
        # the tier gate is exercised on the representable combination:
        # a leveraged futures book.
        with patch("entitlements.plan_code_for_user", return_value="junior"):
            resp = self._create_run(market_type="futures", leverage=5)
        self.assertEqual(resp.status_code, 403)
        self.assertIn("spot-only", resp.json()["detail"])

    def test_junior_cannot_create_futures_run(self):
        with patch("entitlements.plan_code_for_user", return_value="junior"):
            resp = self._create_run(market_type="futures")
        self.assertEqual(resp.status_code, 403)

    def test_junior_can_create_spot_run(self):
        with patch("entitlements.plan_code_for_user", return_value="junior"):
            resp = self._create_run()
        self.assertEqual(resp.status_code, 200, resp.text)

    def test_junior_cannot_edit_draft_into_futures(self):
        with patch("entitlements.plan_code_for_user", return_value="junior"):
            run_id = self._create_run().json()["id"]
            resp = self.client.put(
                f"/api/runs/{run_id}",
                json={"symbol": "BTC", "market": "crypto",
                      "max_bet_usd": 100.0, "market_type": "futures",
                      "leverage": 3},
                headers=self._h())
        self.assertEqual(resp.status_code, 403)

    def test_pro_can_create_leveraged_run(self):
        with patch("entitlements.plan_code_for_user", return_value="pro"):
            resp = self._create_run(market_type="futures", leverage=5)
        self.assertEqual(resp.status_code, 200, resp.text)

    def test_unlinked_agent_unaffected_by_spot_gate(self):
        # Agent-native principals keep their existing create behavior — the
        # tier gate names junior only (runs are still gated at /start).
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            database.begin_write_transaction(cur)
            cur.execute("UPDATE agents SET user_id = NULL WHERE id = ?",
                        (self.agent_id,))
            conn.commit()
        finally:
            conn.close()
        resp = self._create_run(market_type="futures", leverage=5)
        self.assertEqual(resp.status_code, 200, resp.text)

    # ── AI Analyst is Pro+ ─────────────────────────────────────────────

    def test_junior_analyst_job_denied(self):
        with patch("entitlements.plan_code_for_user", return_value="junior"):
            resp = self.client.post(
                "/api/analysis/jobs",
                json={"symbol": "BTC", "market": "crypto"}, headers=self._h())
        self.assertEqual(resp.status_code, 403)
        self.assertIn("AI Analyst", resp.json()["detail"])

    def test_junior_analyst_run_denied(self):
        with patch("entitlements.plan_code_for_user", return_value="junior"):
            resp = self.client.post(
                "/api/analysis/run",
                json={"symbol": "BTC", "market": "crypto"}, headers=self._h())
        self.assertEqual(resp.status_code, 403)

    def test_pro_analyst_job_allowed(self):
        with patch("entitlements.plan_code_for_user", return_value="pro"), \
             patch("analysis_jobs.start_job",
                   return_value={"job_id": 1, "status": "running"}):
            resp = self.client.post(
                "/api/analysis/jobs",
                json={"symbol": "BTC", "market": "crypto"}, headers=self._h())
        self.assertEqual(resp.status_code, 200, resp.text)

    # ── changing the AI is Pro+ ────────────────────────────────────────

    def test_junior_cannot_repoint_llm_target(self):
        h = self._user_h()
        with patch("entitlements.plan_code_for_user", return_value="junior"):
            resp = self.client.put(
                "/api/users/settings/api/llm",
                json={"api_key": "sk-own-key",
                      "config": {"provider": "openai", "model": "gpt-4o"}},
                headers=h)
        self.assertEqual(resp.status_code, 403)
        self.assertIn("default AI", resp.json()["detail"])

    def test_pro_can_repoint_llm_target(self):
        h = self._user_h()
        with patch("entitlements.plan_code_for_user", return_value="pro"):
            resp = self.client.put(
                "/api/users/settings/api/llm",
                json={"api_key": "sk-own-key",
                      "config": {"provider": "openai", "model": "gpt-4o"}},
                headers=h)
        self.assertEqual(resp.status_code, 200, resp.text)

    def test_junior_other_targets_unaffected(self):
        h = self._user_h()
        with patch("entitlements.plan_code_for_user", return_value="junior"):
            resp = self.client.put(
                "/api/users/settings/api/alerts",
                json={"config": {"email_enabled": "true"}}, headers=h)
        self.assertEqual(resp.status_code, 200, resp.text)

    # ── fleets are Professional+ ───────────────────────────────────────

    def test_pro_fleet_denied_professional_allowed(self):
        from entitlements import PLAN_LIMITS, check_fleet_create
        self.assertEqual(PLAN_LIMITS["pro"]["max_fleet_size"], 0)
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            with patch("entitlements.plan_code_for_user", return_value="pro"):
                deny = check_fleet_create(cur, self.agent_id, 3)
            self.assertIsNotNone(deny)
            with patch("entitlements.plan_code_for_user",
                       return_value="professional"):
                self.assertIsNone(check_fleet_create(cur, self.agent_id, 3))
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
