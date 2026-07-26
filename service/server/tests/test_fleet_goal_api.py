"""The fleet profit goal must be settable BY THE USER from the web service —
at creation and on a live fleet — not only by a back-office edit."""

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

    def test_create_accepts_goal(self):
        r = self.client.post("/api/fleets", headers=self.h, json={
            "n_runs": 2, "total_budget_usd": 2000.0,
            "profit_target_frac": 0.03})
        self.assertEqual(r.status_code, 200, r.text)
        fleet = fp.get_fleet(r.json()["id"])
        self.assertAlmostEqual(float(fleet["profit_target_frac"]), 0.03, places=4)

    def test_create_rejects_out_of_bounds_goal(self):
        r = self.client.post("/api/fleets", headers=self.h, json={
            "n_runs": 2, "total_budget_usd": 2000.0,
            "profit_target_frac": 9.0})
        self.assertEqual(r.status_code, 400, r.text)

    def _fleet(self, goal=None):
        body = {"n_runs": 2, "total_budget_usd": 2000.0}
        if goal is not None:
            body["profit_target_frac"] = goal
        return self.client.post("/api/fleets", headers=self.h,
                                json=body).json()["id"]

    def test_goal_can_be_changed_on_a_live_fleet(self):
        fid = self._fleet(0.02)
        r = self.client.put(f"/api/fleets/{fid}/rails", headers=self.h,
                            json={"profit_target_frac": 0.05})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertAlmostEqual(
            float(fp.get_fleet(fid)["profit_target_frac"]), 0.05, places=4)

    def test_goal_can_be_cleared(self):
        fid = self._fleet(0.02)
        r = self.client.put(f"/api/fleets/{fid}/rails", headers=self.h,
                            json={"profit_target_frac": 0})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIsNone(fp.get_fleet(fid)["profit_target_frac"])

    def test_goal_change_is_validated(self):
        fid = self._fleet(0.02)
        r = self.client.put(f"/api/fleets/{fid}/rails", headers=self.h,
                            json={"profit_target_frac": 7.5})
        self.assertEqual(r.status_code, 400, r.text)

    def test_goal_is_visible_on_the_fleet_read(self):
        fid = self._fleet(0.04)
        r = self.client.get(f"/api/fleets/{fid}", headers=self.h)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertAlmostEqual(
            float(r.json()["fleet"]["profit_target_frac"]), 0.04, places=4)


if __name__ == "__main__":
    unittest.main()
