"""Run-surface user scoping (PR #36 boundary applied to /api/runs).

The fleet monitor is user-scoped, so its member cards may reference runs a
SIBLING agent (same linked user) created. The run read/control routes must
accept those; agents of a different user — and unlinked agents — must keep
404ing exactly as before.
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
import trading_runs
from routes import create_app


class RunsUserScopeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.plan = patch("entitlements.plan_code_for_user",
                          return_value="professional")
        self.plan.start()
        self.probe = patch("routes_runs._probe_price", return_value=100.0)
        self.probe.start()
        self.client = TestClient(create_app())

        def register(name):
            resp = self.client.post(
                "/api/claw/agents/selfRegister",
                json={"name": name, "password": "pw123",
                      "initial_balance": 100000.0})
            body = resp.json()
            return body["agent_id"], {"Authorization": f"Bearer {body['token']}"}

        self.owner_id, self.owner = register("scope-owner")
        self.sibling_id, self.sibling = register("scope-sibling")
        self.stranger_id, self.stranger = register("scope-stranger")
        self.unlinked_id, self.unlinked = register("scope-unlinked")

        conn = database.get_db_connection()
        cur = conn.cursor()
        for email in ("a@x.com", "b@x.com"):
            cur.execute("INSERT INTO users (email, password_hash, created_at) "
                        "VALUES (?, 'x', '2026-01-01T00:00:00Z')", (email,))
        cur.execute("SELECT id FROM users ORDER BY id")
        user_a, user_b = [r["id"] for r in cur.fetchall()]
        cur.execute("UPDATE agents SET user_id = ? WHERE id IN (?, ?)",
                    (user_a, self.owner_id, self.sibling_id))
        cur.execute("UPDATE agents SET user_id = ? WHERE id = ?",
                    (user_b, self.stranger_id))
        conn.commit()
        conn.close()

        resp = self.client.post("/api/runs", headers=self.owner, json={
            "symbol": "BTC", "market": "crypto", "market_type": "spot",
            "max_bet_usd": 100, "interval_minutes": 60,
            "min_confidence": 0.65})
        self.assertEqual(resp.status_code, 200, resp.text)
        self.run_id = resp.json()["id"]

    def tearDown(self):
        self.plan.stop()
        self.probe.stop()
        self.tmp.cleanup()

    def test_sibling_reads_run_snapshot_and_events(self):
        for path in (f"/api/runs/{self.run_id}",
                     f"/api/runs/{self.run_id}/snapshot",
                     f"/api/runs/{self.run_id}/events"):
            resp = self.client.get(path, headers=self.sibling)
            self.assertEqual(resp.status_code, 200, f"{path}: {resp.text}")

    def test_sibling_sees_run_in_list(self):
        runs = self.client.get("/api/runs", headers=self.sibling).json()["runs"]
        self.assertIn(self.run_id, [r["id"] for r in runs])

    def test_sibling_controls_run_as_owner(self):
        resp = self.client.post(f"/api/runs/{self.run_id}/start",
                                headers=self.sibling)
        self.assertEqual(resp.status_code, 200, resp.text)
        # The run stays journalled under its OWNING agent, not the caller.
        run = trading_runs.get_run(self.run_id, self.owner_id)
        self.assertEqual(run["status"], "running")
        resp = self.client.post(f"/api/runs/{self.run_id}/stop",
                                headers=self.sibling, json={"flatten": False})
        self.assertEqual(resp.status_code, 200, resp.text)

    def test_other_user_agent_gets_404(self):
        for method, path in (("get", f"/api/runs/{self.run_id}"),
                             ("get", f"/api/runs/{self.run_id}/snapshot"),
                             ("get", f"/api/runs/{self.run_id}/events"),
                             ("post", f"/api/runs/{self.run_id}/start"),
                             ("delete", f"/api/runs/{self.run_id}")):
            resp = getattr(self.client, method)(path, headers=self.stranger)
            self.assertEqual(resp.status_code, 404, f"{method} {path}")
        runs = self.client.get("/api/runs", headers=self.stranger).json()["runs"]
        self.assertNotIn(self.run_id, [r["id"] for r in runs])

    def test_unlinked_agent_stays_agent_scoped(self):
        # user_id NULL on both sides must never match (NULL != NULL).
        resp = self.client.get(f"/api/runs/{self.run_id}", headers=self.unlinked)
        self.assertEqual(resp.status_code, 404)
        # And the unlinked agent still sees its own runs only.
        runs = self.client.get("/api/runs", headers=self.unlinked).json()["runs"]
        self.assertEqual(runs, [])


if __name__ == "__main__":
    unittest.main()
