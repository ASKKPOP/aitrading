"""The fleet profit goal is OWNED BY THE AI (owner order 2026-08-19:
"수익 퍼센트 설정 remove, it's defined by sooppiy AI"). The user-facing
paths — fleet creation and the live rails edit — must IGNORE any
profit_target_frac in the request; only the internal
fleet_planner.set_profit_target path (the AI's) may write it."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from fastapi.testclient import TestClient

import database
import fleet_planner as fp
from routes import create_app


class GoalApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO users (email, password_hash, created_at) "
                    "VALUES ('g@x.com','x','2026-01-01T00:00:00Z')")
        uid = cur.lastrowid
        cur.execute("INSERT INTO agents (name, token_hash, cash, user_id, "
                    "created_at) VALUES ('goal','th',100000,?, "
                    "'2026-01-01T00:00:00Z')", (uid,))
        self.agent = {"id": cur.lastrowid, "user_id": uid}
        conn.commit(); conn.close()
        self.plan = patch("entitlements.plan_code_for_user",
                          return_value="professional")
        self.plan.start()
        self.auth = patch("routes_fleets._get_agent_by_token",
                          return_value=self.agent)
        self.auth.start()
        self.client = TestClient(create_app())
        self.h = {"Authorization": "Bearer x"}

    def tearDown(self):
        self.plan.stop(); self.auth.stop(); self.tmp.cleanup()

    def test_create_ignores_user_goal(self):
        """A profit_target_frac in the create body is silently ignored —
        the fleet is born with NO goal (the AI authors one if it wants)."""
        r = self.client.post("/api/fleets", headers=self.h, json={
            "n_runs": 2, "total_budget_usd": 2000.0,
            "profit_target_frac": 0.03})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIsNone(fp.get_fleet(r.json()["id"])["profit_target_frac"])

    def _fleet(self):
        return self.client.post(
            "/api/fleets", headers=self.h,
            json={"n_runs": 2, "total_budget_usd": 2000.0}).json()["id"]

    def test_rails_put_ignores_user_goal(self):
        """PUT /rails with profit_target_frac neither writes the goal nor
        emits a goal_changed event; the loss rails still work."""
        fid = self._fleet()
        r = self.client.put(f"/api/fleets/{fid}/rails", headers=self.h,
                            json={"profit_target_frac": 0.05,
                                  "warn_loss_frac": 0.25})
        self.assertEqual(r.status_code, 200, r.text)
        fleet = fp.get_fleet(fid)
        self.assertIsNone(fleet["profit_target_frac"])
        self.assertAlmostEqual(float(fleet["warn_loss_frac"]), 0.25, places=4)
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) AS n FROM fleet_events WHERE fleet_id = ?"
                    " AND event_type = 'goal_changed'", (fid,))
        n = cur.fetchone()["n"]
        conn.close()
        self.assertEqual(n, 0)

    def test_ai_path_still_writes_the_goal(self):
        """The internal setter (the AI's path) keeps working."""
        fid = self._fleet()
        fp.set_profit_target(fid, 0.04)
        self.assertAlmostEqual(
            float(fp.get_fleet(fid)["profit_target_frac"]), 0.04, places=4)
        r = self.client.get(f"/api/fleets/{fid}", headers=self.h)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertAlmostEqual(
            float(r.json()["fleet"]["profit_target_frac"]), 0.04, places=4)


if __name__ == "__main__":
    unittest.main()
