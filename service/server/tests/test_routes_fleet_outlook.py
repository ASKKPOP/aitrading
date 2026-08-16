"""Plan 26 Phase 3 — GET /api/fleets/{id}/outlook (read API + i18n).

Shape (slot_index, thesis, outlook, dialog), next_refresh_by cadence
arithmetic (30 vs 60 min), dialog ordering + limit, empty/edge states,
auth parity with sibling fleet endpoints, and the cache-only ko path.
"""

from __future__ import annotations

import json
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
import fleet_planner as fp
import market_i18n
import symbol_research as sr
from routes import create_app

OUTLOOK = {
    "bias": "long",
    "entry": {"kind": "zone", "low": 98.0, "high": 101.0, "trigger": None},
    "exit": {"target_px": 110.0, "stop_ref_px": 92.0, "time_exit": None},
    "invalidation": "daily close below 92 kills the long thesis",
    "horizon_hours": 18,
    "narrative": "Ride the trend; add only inside the zone.",
    "source": "cycle",
}


def _candles(n=60, drift=0.8, volume=5_000_000):
    out, price = [], 100.0
    for i in range(n):
        price *= 1 + drift / 100.0
        out.append({"ts": i, "open": price, "high": price, "low": price,
                    "close": price, "volume": volume})
    return out


class FleetOutlookRouteTests(unittest.TestCase):
    def setUp(self):
        os.environ["RUN_FEE_EDGE_MULTIPLE"] = "0"
        os.environ["FLEET_EXPECTANCY_GATE"] = "false"
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
        resp = self.client.post(
            "/api/claw/agents/selfRegister",
            json={"name": "outlook-route-agent", "password": "pw123",
                  "initial_balance": 100000.0})
        self.token = resp.json()["token"]
        self.agent_id = resp.json()["agent_id"]
        self.auth = {"Authorization": f"Bearer {self.token}"}
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO users (email, password_hash, created_at) "
                    "VALUES ('u@x.com', 'x', '2026-01-01T00:00:00Z')")
        self.user_id = cur.lastrowid
        cur.execute("UPDATE agents SET user_id = ? WHERE id = ?",
                    (self.user_id, self.agent_id))
        conn.commit()
        conn.close()
        market_i18n._MEM_CACHE.clear()

    def tearDown(self):
        os.environ.pop("RUN_FEE_EDGE_MULTIPLE", None)
        os.environ.pop("FLEET_EXPECTANCY_GATE", None)
        market_i18n._MEM_CACHE.clear()
        self.plan.stop()
        self.probe.stop()
        self.tmp.cleanup()

    # ── fixture helpers ────────────────────────────────────────────────────

    def _seed_and_build(self, n=2, budget=2000.0):
        universe = [{"symbol": s, "market": "crypto"}
                    for s in ("AAA", "BBB", "CCC", "DDD", "EEE")]
        with patch.object(sr, "build_universe", return_value=universe), \
             patch.object(sr, "_read_overlays",
                          return_value={"event_window": False,
                                        "regime_blocks_longs": False,
                                        "policy": {}}), \
             patch("cache.acquire_lock", return_value=None):
            sr.refresh_research_batch(
                generate_text=lambda *a, **k: None,
                fetch_candles=lambda s, m: _candles())
        r = self.client.post("/api/fleets",
                             json={"n_runs": n, "total_budget_usd": budget},
                             headers=self.auth)
        self.assertEqual(r.status_code, 200, r.text)
        fleet_id = r.json()["id"]
        r = self.client.post(f"/api/fleets/{fleet_id}/start", headers=self.auth)
        self.assertEqual(r.status_code, 200, r.text)
        fp._do_research(fp.get_fleet(fleet_id))
        fp._do_build(fp.get_fleet(fleet_id))
        return fleet_id

    def _slots(self, fleet_id):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM fleet_slots WHERE fleet_id = ? "
                        "ORDER BY slot_index", (fleet_id,))
            return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

    def _emit(self, run_id, seq, event_type, ts, payload):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO run_events (run_id, seq, event_type, ts, payload)"
                " VALUES (?, ?, ?, ?, ?)",
                (run_id, seq, event_type, ts, json.dumps(payload)))
            conn.commit()
        finally:
            conn.close()

    def _sql(self, stmt, params=()):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute(stmt, params)
            conn.commit()
        finally:
            conn.close()

    # ── shape + cadence arithmetic ─────────────────────────────────────────

    def test_full_shape_and_cadence_30_vs_60(self):
        fleet_id = self._seed_and_build(n=2)
        slots = self._slots(fleet_id)
        self.assertEqual(len(slots), 2, slots)
        run_a = int(slots[0]["current_run_id"])
        run_b = int(slots[1]["current_run_id"])
        # run_b becomes a slow-cadence market (not in the 30-min trio → 60)
        self._sql("UPDATE trading_runs SET market = 'prediction' WHERE id = ?",
                  (run_b,))
        self._emit(run_a, 101, "decision", "2026-08-15T10:00:00Z",
                   {"action": "hold", "confidence": 0.4,
                    "report": "Holding; zone intact.",
                    "plan_adherence": "followed"})
        self._emit(run_a, 102, "outlook", "2026-08-15T10:00:00Z",
                   dict(OUTLOOK))
        self._emit(run_a, 103, "decision", "2026-08-15T10:30:00Z",
                   {"action": "buy", "confidence": 0.7,
                    "report": "Zone tagged; adding."})
        newest = dict(OUTLOOK)
        newest["narrative"] = "Zone filled; trail toward 110."
        # contract update: payload passes through OPAQUELY — the optional
        # "basis" block (and any future key) must arrive intact.
        newest["basis"] = {
            "algo": {"entry_low": 98.0, "entry_high": 101.0,
                     "target_px": 110.0, "stop_ref_px": 92.0,
                     "time_exit": None},
            "verdict": "adjusted",
            "discussion": "Algo levels adopted; target trailed.",
        }
        self._emit(run_a, 104, "outlook", "2026-08-15T10:30:00Z", newest)
        self._emit(run_b, 101, "outlook", "2026-08-15T10:00:00Z",
                   dict(OUTLOOK, source="sweeper"))

        r = self.client.get(f"/api/fleets/{fleet_id}/outlook",
                            headers=self.auth)
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["fleet_id"], fleet_id)
        self.assertEqual([s["slot_index"] for s in body["slots"]],
                         [slots[0]["slot_index"], slots[1]["slot_index"]])

        a = body["slots"][0]
        self.assertEqual(a["run_id"], run_a)
        self.assertEqual(a["market"], "crypto")
        self.assertIsNotNone(a["symbol"])
        self.assertIsNotNone(a["status"])
        self.assertIn("state", a)
        self.assertIsInstance(a["thesis"], dict)
        self.assertIn("direction", a["thesis"])
        self.assertIn("horizon_hours", a["thesis"])
        # newest outlook wins; crypto cadence floor = 30 min
        self.assertEqual(a["outlook"]["narrative"],
                         "Zone filled; trail toward 110.")
        self.assertEqual(a["outlook"]["bias"], "long")
        self.assertEqual(a["outlook"]["basis"], newest["basis"])  # opaque
        self.assertEqual(a["outlook_ts"], "2026-08-15T10:30:00Z")
        self.assertEqual(a["next_refresh_by"], "2026-08-15T11:00:00Z")
        # dialog: chronological, newest last, both kinds folded in
        self.assertEqual([(d["kind"], d["ts"]) for d in a["dialog"]],
                         [("decision", "2026-08-15T10:00:00Z"),
                          ("outlook", "2026-08-15T10:00:00Z"),
                          ("decision", "2026-08-15T10:30:00Z"),
                          ("outlook", "2026-08-15T10:30:00Z")])
        self.assertEqual(a["dialog"][0]["text"], "Holding; zone intact.")
        self.assertEqual(a["dialog"][0]["plan_adherence"], "followed")
        self.assertIsNone(a["dialog"][0]["source"])
        self.assertEqual(a["dialog"][1]["text"], OUTLOOK["narrative"])
        self.assertEqual(a["dialog"][1]["source"], "cycle")
        self.assertIsNone(a["dialog"][1]["plan_adherence"])
        self.assertIsNone(a["dialog"][2]["plan_adherence"])  # absent → null

        b = body["slots"][1]
        self.assertEqual(b["market"], "prediction")
        self.assertEqual(b["outlook_ts"], "2026-08-15T10:00:00Z")
        self.assertEqual(b["next_refresh_by"], "2026-08-15T11:00:00Z")  # +60
        self.assertEqual(b["outlook"]["source"], "sweeper")

    def test_dialog_limit_keeps_newest(self):
        fleet_id = self._seed_and_build(n=1)
        run_id = int(self._slots(fleet_id)[0]["current_run_id"])
        for i in range(5):
            self._emit(run_id, 101 + i, "decision",
                       f"2026-08-15T10:0{i}:00Z", {"report": f"cycle {i}"})
        r = self.client.get(
            f"/api/fleets/{fleet_id}/outlook?dialog_limit=2",
            headers=self.auth)
        self.assertEqual(r.status_code, 200, r.text)
        dialog = r.json()["slots"][0]["dialog"]
        self.assertEqual([d["text"] for d in dialog], ["cycle 3", "cycle 4"])
        # over-cap limit clamps instead of erroring
        r = self.client.get(
            f"/api/fleets/{fleet_id}/outlook?dialog_limit=1000",
            headers=self.auth)
        self.assertEqual(r.status_code, 200, r.text)

    # ── empty / edge states ────────────────────────────────────────────────

    def test_slot_without_run_and_no_outlook_yet(self):
        fleet_id = self._seed_and_build(n=2)
        slots = self._slots(fleet_id)
        self._sql("UPDATE fleet_slots SET current_run_id = NULL WHERE id = ?",
                  (slots[0]["id"],))
        r = self.client.get(f"/api/fleets/{fleet_id}/outlook",
                            headers=self.auth)
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        empty = body["slots"][0]
        self.assertIsNone(empty["run_id"])
        self.assertIsNone(empty["symbol"])
        self.assertIsNone(empty["market"])
        self.assertIsNone(empty["status"])
        self.assertIsNone(empty["thesis"])
        self.assertIsNone(empty["outlook"])
        self.assertEqual(empty["dialog"], [])
        # bound slot, but no outlook/decision events written yet
        bound = body["slots"][1]
        self.assertIsNotNone(bound["run_id"])
        self.assertIsNone(bound["outlook"])
        self.assertIsNone(bound["outlook_ts"])
        self.assertIsNone(bound["next_refresh_by"])
        self.assertEqual(bound["dialog"], [])

    def test_fleet_with_no_slots(self):
        r = self.client.post("/api/fleets",
                             json={"n_runs": 2, "total_budget_usd": 2000.0},
                             headers=self.auth)
        self.assertEqual(r.status_code, 200, r.text)
        fleet_id = r.json()["id"]
        r = self.client.get(f"/api/fleets/{fleet_id}/outlook",
                            headers=self.auth)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json(), {"fleet_id": fleet_id, "slots": []})

    # ── auth parity with sibling fleet endpoints ───────────────────────────

    def test_auth_matches_sibling_endpoints(self):
        fleet_id = self._seed_and_build(n=1)
        # no token → 401
        self.assertEqual(
            self.client.get(f"/api/fleets/{fleet_id}/outlook").status_code, 401)
        # unknown fleet → 404
        self.assertEqual(
            self.client.get("/api/fleets/999999/outlook",
                            headers=self.auth).status_code, 404)
        # other user's agent → cross-tenant 404, same as GET /api/fleets/{id}
        other = self.client.post(
            "/api/claw/agents/selfRegister",
            json={"name": "other-agent", "password": "pw123",
                  "initial_balance": 1000.0}).json()
        other_auth = {"Authorization": f"Bearer {other['token']}"}
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO users (email, password_hash, created_at) "
                    "VALUES ('v@x.com', 'x', '2026-01-01T00:00:00Z')")
        other_user = cur.lastrowid
        cur.execute("UPDATE agents SET user_id = ? WHERE id = ?",
                    (other_user, other["agent_id"]))
        conn.commit()
        conn.close()
        sibling = self.client.get(f"/api/fleets/{fleet_id}",
                                  headers=other_auth).status_code
        mine = self.client.get(f"/api/fleets/{fleet_id}/outlook",
                               headers=other_auth).status_code
        self.assertEqual(sibling, 404)
        self.assertEqual(mine, sibling)

    # ── i18n: cache-only localization, English fallback ────────────────────

    def test_lang_ko_cache_hit_and_english_fallback(self):
        fleet_id = self._seed_and_build(n=1)
        run_id = int(self._slots(fleet_id)[0]["current_run_id"])
        self._emit(run_id, 101, "decision", "2026-08-15T10:00:00Z",
                   {"report": "Holding; zone intact."})
        self._emit(run_id, 102, "outlook", "2026-08-15T10:00:00Z",
                   dict(OUTLOOK))
        # warm ONLY the narrative — the report stays a cache miss
        key = market_i18n._cache_key(OUTLOOK["narrative"], "ko")
        market_i18n._MEM_CACHE[key] = "추세를 타고 존 안에서만 추가."
        with patch.object(market_i18n, "_schedule_warm") as sched:
            r = self.client.get(
                f"/api/fleets/{fleet_id}/outlook?lang=ko",
                headers=self.auth)
        self.assertEqual(r.status_code, 200, r.text)
        slot = r.json()["slots"][0]
        self.assertEqual(slot["outlook"]["narrative"],
                         "추세를 타고 존 안에서만 추가.")
        self.assertEqual(slot["dialog"][1]["text"],
                         "추세를 타고 존 안에서만 추가.")
        # cache miss → English original served, warm queued, never blocking
        self.assertEqual(slot["dialog"][0]["text"], "Holding; zone intact.")
        misses = [s for call in sched.call_args_list for s in call.args[0]]
        self.assertIn("Holding; zone intact.", misses)

    def test_lang_en_is_untouched(self):
        fleet_id = self._seed_and_build(n=1)
        run_id = int(self._slots(fleet_id)[0]["current_run_id"])
        self._emit(run_id, 101, "outlook", "2026-08-15T10:00:00Z",
                   dict(OUTLOOK))
        with patch.object(market_i18n, "localize_texts") as loc:
            r = self.client.get(f"/api/fleets/{fleet_id}/outlook",
                                headers=self.auth)
        self.assertEqual(r.status_code, 200, r.text)
        loc.assert_not_called()
        self.assertEqual(r.json()["slots"][0]["outlook"]["narrative"],
                         OUTLOOK["narrative"])


if __name__ == "__main__":
    unittest.main()
