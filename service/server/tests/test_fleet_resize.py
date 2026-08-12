"""Fleet resize — the slot target must be adjustable BY THE USER on a live
fleet (owner ask 2026-08-08), with drain-not-dump semantics on shrink:

- raise: n_runs updates, plan cap re-checked, and the supervisor's existing
  growth loop fills toward the new target on its next pass.
- lower: excess slots retire only AS THEY EMPTY — a live position is never
  touched. Drained slots are DELETED (not state='closed': closed is the
  user-stop verdict and deliberately never refills) so a later raise can
  recreate them.
"""

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
import fleet_supervisor as fs
from routes import create_app

from test_fleet_supervision import SupervisionBase


def _live(fleet_id):
    return [m for m in fp.list_members(fleet_id)
            if m["status"] in ("running", "armed", "paused")]


class ResizeApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO users (email, password_hash, created_at) "
                    "VALUES ('r@x.com','x','2026-01-01T00:00:00Z')")
        uid = cur.lastrowid
        cur.execute("INSERT INTO agents (name, token_hash, cash, user_id, "
                    "created_at) VALUES ('resize','th',100000,?, "
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

    def _fleet(self, n=2):
        return self.client.post("/api/fleets", headers=self.h, json={
            "n_runs": n, "total_budget_usd": 2000.0}).json()["id"]

    def _events(self, fid):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT event_type FROM fleet_events "
                        "WHERE fleet_id = ?", (fid,))
            return [r["event_type"] for r in cur.fetchall()]
        finally:
            conn.close()

    def test_fleet_payload_carries_the_recommendation(self):
        fid = self._fleet(n=2)
        r = self.client.get(f"/api/fleets/{fid}")
        self.assertEqual(r.status_code, 200, r.text)
        # $2,000 budget -> 20 viable slots, clamped to the professional plan
        # cap (10) — recommending above the cap only ever leads to a denial
        # (live 2026-08-12: the dialog said 25 to a plan capped at 10).
        self.assertEqual(r.json()["fleet"]["recommended_max_n_runs"], 10)

    def test_raise_updates_target_and_journals(self):
        fid = self._fleet(n=2)
        r = self.client.put(f"/api/fleets/{fid}/size", headers=self.h,
                            json={"n_runs": 4})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(int(fp.get_fleet(fid)["n_runs"]), 4)
        self.assertIn("size_changed", self._events(fid))

    def test_lower_updates_target(self):
        fid = self._fleet(n=3)
        r = self.client.put(f"/api/fleets/{fid}/size", headers=self.h,
                            json={"n_runs": 1})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(int(fp.get_fleet(fid)["n_runs"]), 1)

    def test_same_size_is_a_noop(self):
        fid = self._fleet(n=2)
        r = self.client.put(f"/api/fleets/{fid}/size", headers=self.h,
                            json={"n_runs": 2})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertNotIn("size_changed", self._events(fid))

    def test_bounds_rejected(self):
        fid = self._fleet(n=2)
        for bad in (0, 26):
            r = self.client.put(f"/api/fleets/{fid}/size", headers=self.h,
                                json={"n_runs": bad})
            self.assertEqual(r.status_code, 400, f"{bad}: {r.text}")

    def test_raise_beyond_plan_cap_403(self):
        fid = self._fleet(n=2)
        r = self.client.put(f"/api/fleets/{fid}/size", headers=self.h,
                            json={"n_runs": 11})  # professional cap is 10
        self.assertEqual(r.status_code, 403, r.text)
        self.assertEqual(int(fp.get_fleet(fid)["n_runs"]), 2)

    def test_lower_never_needs_the_plan_cap(self):
        # A downgade mid-flight must still allow shrinking an oversized fleet.
        fid = self._fleet(n=3)
        with patch("entitlements.plan_code_for_user", return_value="pro"):
            r = self.client.put(f"/api/fleets/{fid}/size", headers=self.h,
                                json={"n_runs": 2})
        self.assertEqual(r.status_code, 200, r.text)

    def test_stopped_fleet_409(self):
        fid = self._fleet(n=2)
        fp._set_status(fid, (fp.STATUS_DRAFT,), fp.STATUS_STOPPED, "user_stop")
        r = self.client.put(f"/api/fleets/{fid}/size", headers=self.h,
                            json={"n_runs": 3})
        self.assertEqual(r.status_code, 409, r.text)


class ResizeDrainTests(SupervisionBase):
    def test_raise_grows_slots_on_next_pass(self):
        # A fully-deployed fleet has zero headroom, so growth after a raise
        # correctly waits for freed budget — give it marked gains to fund
        # the new slot within this pass.
        fleet_id = self._built_fleet(n=2)
        fp.set_fleet_size(fleet_id, 3)
        with self._set_equity_loss(fleet_id, -0.5):   # equity 150% of budget
            fs.supervise_fleet(fp.get_fleet(fleet_id))
        self.assertEqual(len(fs._slots(fleet_id)), 3,
                         "growth loop must fill toward the raised target")

    def test_lower_drains_emptied_slot_instead_of_rebuilding(self):
        fleet_id = self._built_fleet(n=3)
        fp.set_fleet_size(fleet_id, 2)
        self._orphan_slot(fleet_id, 0)      # one slot loses its run
        fs.supervise_fleet(fp.get_fleet(fleet_id))
        self.assertEqual(len(fs._slots(fleet_id)), 2,
                         "the emptied excess slot must be removed, not rebuilt")
        self.assertEqual(len(_live(fleet_id)), 2,
                         "live members must be untouched by the drain")

    def test_lower_never_touches_live_positions(self):
        fleet_id = self._built_fleet(n=3)
        before = {m["id"] for m in _live(fleet_id)}
        fp.set_fleet_size(fleet_id, 1)
        fs.supervise_fleet(fp.get_fleet(fleet_id))
        after = {m["id"] for m in _live(fleet_id)}
        self.assertEqual(before, after,
                         "no live run may be stopped by a resize")
        self.assertEqual(len(fs._slots(fleet_id)), 3,
                         "occupied slots survive until they empty")

    def _orphan_slot(self, fleet_id, slot_index=0):
        slot_runs = {s["slot_index"]: s.get("current_run_id")
                     for s in fs._slots(fleet_id)}
        run_id = slot_runs[slot_index]
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM trading_runs WHERE id = ?", (run_id,))
        cur.execute("UPDATE fleet_slots SET current_run_id = NULL, "
                    "state = 'active' WHERE fleet_id = ? AND slot_index = ?",
                    (fleet_id, slot_index))
        conn.commit()
        conn.close()


if __name__ == "__main__":
    unittest.main()


class RecommendedSlotsTests(unittest.TestCase):
    def test_recommendation_math(self):
        # One viable slot per $100 of budget (fee-hurdle evidence), clamped
        # to the fleet bounds.
        self.assertEqual(fp.recommended_max_slots(1000.0), 10)
        self.assertEqual(fp.recommended_max_slots(250.0), 2)
        self.assertEqual(fp.recommended_max_slots(50.0), 1)   # never below 1
        self.assertEqual(fp.recommended_max_slots(10_000.0), 25)  # bounds cap
