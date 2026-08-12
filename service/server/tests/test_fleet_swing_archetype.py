"""Plan 23 Phase A — the swing archetype homes on the fleet, and the NYSE
calendar learns holidays.

Owner decision 2026-08-11: build the US-stock swing block with BOTH paper and
live capability, sequenced by the plan's promotion pipeline (paper trial →
probation → scale). Phase A is deliberately inert for every existing fleet:
`archetype` defaults 'short' and nothing changes until a fleet is explicitly
created as swing.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from fastapi.testclient import TestClient

import database
import fleet_planner as fp
import markets
from routes import create_app

_ET = ZoneInfo("America/New_York")


class NyseCalendarTests(unittest.TestCase):
    """The session clock was weekday+time only — a swing block that holds
    overnight MUST know full holidays and 13:00-ET half days."""

    def test_full_holiday_is_closed(self):
        # Thanksgiving 2026 — a Thursday, mid-session time
        now = datetime(2026, 11, 26, 12, 0, tzinfo=_ET)
        self.assertFalse(markets.is_session_open("nyse", now))

    def test_observed_holiday_is_closed(self):
        # July 4th 2026 falls Saturday → observed Friday July 3, full close
        now = datetime(2026, 7, 3, 12, 0, tzinfo=_ET)
        self.assertFalse(markets.is_session_open("nyse", now))

    def test_half_day_closes_at_13_et(self):
        # Friday after Thanksgiving 2026: open at 12:59, shut at 13:01
        self.assertTrue(markets.is_session_open(
            "nyse", datetime(2026, 11, 27, 12, 59, tzinfo=_ET)))
        self.assertFalse(markets.is_session_open(
            "nyse", datetime(2026, 11, 27, 13, 1, tzinfo=_ET)))

    def test_ordinary_wednesday_unchanged(self):
        self.assertTrue(markets.is_session_open(
            "nyse", datetime(2026, 11, 18, 12, 0, tzinfo=_ET)))
        self.assertFalse(markets.is_session_open(
            "nyse", datetime(2026, 11, 18, 17, 0, tzinfo=_ET)))

    def test_session_minutes_left_respects_the_half_day(self):
        # 12:00 ET on the half day → ~1 hour left, not 4. (The bisection
        # convention counts the last still-open minute: 59.)
        left = markets.session_minutes_left(
            "us-stock", datetime(2026, 11, 27, 12, 0, tzinfo=_ET))
        self.assertEqual(left, 59)


class ArchetypeBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO users (email, password_hash, created_at) "
                    "VALUES ('s@x.com','x','2026-01-01T00:00:00Z')")
        uid = cur.lastrowid
        cur.execute("INSERT INTO agents (name, token_hash, cash, user_id, "
                    "created_at) VALUES ('swing','th',100000,?, "
                    "'2026-01-01T00:00:00Z')", (uid,))
        self.agent = {"id": cur.lastrowid, "user_id": uid}
        conn.commit(); conn.close()
        self.plan = patch("entitlements.plan_code_for_user",
                          return_value="professional")
        self.plan.start()

    def tearDown(self):
        self.plan.stop(); self.tmp.cleanup()


class CreateFleetArchetypeTests(ArchetypeBase):
    def test_default_is_short_and_unchanged(self):
        fid = fp.create_fleet(self.agent["id"], 2, 2000.0)
        f = fp.get_fleet(fid)
        self.assertEqual(f["archetype"], "short")

    def test_swing_pins_market_scope_to_us_stock(self):
        fid = fp.create_fleet(self.agent["id"], 2, 2000.0,
                              archetype="swing",
                              market_scope=["crypto"])   # ignored on purpose
        import json as _json
        f = fp.get_fleet(fid)
        self.assertEqual(f["archetype"], "swing")
        self.assertEqual(_json.loads(f["market_scope_json"]), ["us-stock"])

    def test_invalid_archetype_refused(self):
        with self.assertRaises(ValueError):
            fp.create_fleet(self.agent["id"], 2, 2000.0, archetype="hyper")

    def test_swing_is_professional_or_enterprise_only(self):
        # Owner (2026-08-12): explicit tier gate, independent of the general
        # fleet gate — even with fleet access granted, a non-Pro/Enterprise
        # plan may not create a swing fleet.
        import trading_runs
        with patch("entitlements.check_fleet_create", return_value=None), \
             patch("entitlements.plan_code_for_user", return_value="pro"):
            with self.assertRaises(trading_runs.EntitlementDenied):
                fp.create_fleet(self.agent["id"], 2, 2000.0,
                                archetype="swing")

    def test_enterprise_plan_may_create_swing(self):
        with patch("entitlements.plan_code_for_user",
                   return_value="enterprise"):
            fid = fp.create_fleet(self.agent["id"], 2, 2000.0,
                                  archetype="swing")
        self.assertEqual(fp.get_fleet(fid)["archetype"], "swing")


class ComposeArchetypeTests(ArchetypeBase):
    def _thesis(self, market="us-stock"):
        return {"symbol": "MSFT", "market": market, "direction": "long",
                "expected_move_pct": 3.0, "horizon_hours": 48,
                "confidence": 0.7, "thesis": "t", "risks": "r",
                "invalidation": "below the recent swing low"}

    def test_swing_settings_stamp_archetype_and_240min(self):
        fid = fp.create_fleet(self.agent["id"], 2, 2000.0, archetype="swing")
        s = fp.compose_run_settings(self._thesis(), 1000.0, fp.get_fleet(fid))
        self.assertEqual(s["archetype"], "swing")
        self.assertEqual(s["interval_minutes"], 240)

    def test_short_fleets_are_byte_identical_to_before(self):
        fid = fp.create_fleet(self.agent["id"], 2, 2000.0)
        s = fp.compose_run_settings(self._thesis("crypto"), 1000.0,
                                    fp.get_fleet(fid))
        self.assertEqual(s["archetype"], "short")
        # balanced default interval for crypto stays what it was
        self.assertEqual(s["interval_minutes"], 60)


class ApiArchetypeTests(ArchetypeBase):
    def setUp(self):
        super().setUp()
        self.auth = patch("routes_fleets._get_agent_by_token",
                          return_value=self.agent)
        self.auth.start()
        self.client = TestClient(create_app())
        self.h = {"Authorization": "Bearer x"}

    def tearDown(self):
        self.auth.stop(); super().tearDown()

    def test_api_creates_swing_fleet_and_reports_archetype(self):
        r = self.client.post("/api/fleets", headers=self.h, json={
            "n_runs": 2, "total_budget_usd": 2000.0, "archetype": "swing"})
        self.assertEqual(r.status_code, 200, r.text)
        fid = r.json()["id"]
        g = self.client.get(f"/api/fleets/{fid}", headers=self.h).json()["fleet"]
        self.assertEqual(g["archetype"], "swing")
        self.assertEqual(g["market_scope"], ["us-stock"])

    def test_api_rejects_unknown_archetype(self):
        r = self.client.post("/api/fleets", headers=self.h, json={
            "n_runs": 2, "total_budget_usd": 2000.0, "archetype": "warp"})
        self.assertEqual(r.status_code, 422)


if __name__ == "__main__":
    unittest.main()
