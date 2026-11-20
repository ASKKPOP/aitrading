"""GET /api/runs?active=1 returns only live runs (owner 2026-11-20: the
/automation page hides its make-buttons while anything is live; a live run
must never fall outside the 200-row cap behind newer stopped fleet members)."""

from __future__ import annotations

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


class ActiveRunsFilterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())
        r = self.client.post("/api/claw/agents/selfRegister",
                             json={"name": "active-agent", "password": "pw123",
                                   "initial_balance": 1000})
        self.h = {"Authorization": f"Bearer {r.json()['token']}"}
        self.agent_id = r.json()["agent_id"]

    def tearDown(self):
        self.tmp.cleanup()

    def _insert(self, status, n=1):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            for i in range(n):
                cur.execute("INSERT INTO trading_runs (agent_id, symbol, market, status, "
                            "created_at) VALUES (?, ?, 'crypto', ?, "
                            "'2026-11-20T00:00:00Z')",
                            (self.agent_id, f"S{status}{i}", status))
            conn.commit()
        finally:
            conn.close()

    def test_a_live_run_behind_200_stopped_runs_is_still_listed(self):
        self._insert("running")
        self._insert("stopped", 205)          # newer ids push it past the cap
        everything = self.client.get("/api/runs?limit=200", headers=self.h).json()["runs"]
        self.assertNotIn("running", {r["status"] for r in everything})
        live = self.client.get("/api/runs?active=1&limit=200", headers=self.h).json()["runs"]
        self.assertEqual([r["status"] for r in live], ["running"])

    def test_active_lists_every_live_status_and_no_other(self):
        for st in ("armed", "running", "paused", "stopping", "draft", "stopped"):
            self._insert(st)
        live = self.client.get("/api/runs?active=1", headers=self.h).json()["runs"]
        self.assertEqual(sorted(r["status"] for r in live),
                         ["armed", "paused", "running", "stopping"])


if __name__ == "__main__":
    unittest.main()
