"""Plan 06 A2 — live confluence calibration from run telemetry."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import calibration
import database
from routes import create_app


class CalibrationTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        calibration._CACHE["payload"] = None
        calibration._CACHE["at"] = 0.0
        self.client = TestClient(create_app())
        resp = self.client.post(
            "/api/claw/agents/selfRegister",
            json={"name": "cal-agent", "password": "pw123", "initial_balance": 100000.0})
        assert resp.status_code == 200
        body = resp.json()
        self.agent_id = body["agent_id"]
        self.token = body["token"]
        self._sig_seq = 500000

    def tearDown(self):
        self.tmp.cleanup()

    def _signal(self, side, price, qty, ts, symbol="BTC"):
        self._sig_seq += 1
        conn = database.get_db_connection()
        conn.execute(
            """INSERT INTO signals
               (signal_id, agent_id, message_type, market, signal_type, symbol,
                side, entry_price, quantity, content, timestamp, created_at, executed_at)
               VALUES (?, ?, 'operation', 'crypto', 'automation', ?, ?, ?, ?, 'cal', 0, ?, ?)""",
            (self._sig_seq, self.agent_id, symbol, side, price, qty, ts, ts))
        conn.commit()
        conn.close()
        return self._sig_seq

    def _tag_run(self, signal_id, buy_confluence):
        conn = database.get_db_connection()
        conn.execute(
            """INSERT INTO automation_runs
               (config_id, agent_id, ran_at, action, confidence, executed, skip_reason,
                signal_id, report, confluence_json)
               VALUES (1, ?, '2026-07-16T00:00:00Z', 'buy', 0.7, 1, NULL, ?, 'r', ?)""",
            (self.agent_id, signal_id,
             json.dumps({"confluence": {"buy_confluence": buy_confluence}})))
        conn.commit()
        conn.close()

    def _round_trip(self, confluence, win, idx, symbol="BTC"):
        """One tagged buy resolved by one sell (win or loss)."""
        t0 = f"2026-07-01T{idx:02d}:00:00Z"
        t1 = f"2026-07-01T{idx:02d}:30:00Z"
        sig = self._signal("buy", 100.0, 1.0, t0, symbol=symbol)
        self._tag_run(sig, confluence)
        self._signal("sell", 110.0 if win else 90.0, 1.0, t1, symbol=symbol)

    def test_buckets_from_resolved_trades(self):
        for i, win in enumerate([True, True, False]):
            self._round_trip(4, win, i)
        for i, win in enumerate([False, True]):
            self._round_trip(2, win, i + 10)
        payload = calibration.build_live_calibration()
        self.assertTrue(payload["available"])
        self.assertEqual(payload["total_resolved"], 5)
        b4 = payload["buckets"]["4"]
        self.assertEqual((b4["trades"], b4["wins"]), (3, 2))
        self.assertAlmostEqual(b4["hit_rate"], 2 / 3, places=3)
        self.assertIsNotNone(b4["wilson_lb"])
        b2 = payload["buckets"]["2"]
        self.assertEqual((b2["trades"], b2["wins"]), (2, 1))

    def test_untagged_and_unresolved_ignored(self):
        # untagged round trip
        self._signal("buy", 100.0, 1.0, "2026-07-01T01:00:00Z")
        self._signal("sell", 120.0, 1.0, "2026-07-01T01:30:00Z")
        # tagged but never sold (unresolved)
        sig = self._signal("buy", 100.0, 1.0, "2026-07-01T02:00:00Z", symbol="ETH")
        self._tag_run(sig, 5)
        payload = calibration.build_live_calibration()
        self.assertFalse(payload["available"])
        self.assertEqual(payload["total_resolved"], 0)

    def test_prior_requires_min_trades(self):
        for i in range(3):
            self._round_trip(4, True, i)
        calibration._CACHE["payload"] = None
        self.assertIsNone(calibration.calibration_prior(4))  # 3 < PRIOR_MIN_TRADES
        for i in range(3, 6):
            self._round_trip(4, i % 2 == 0, i)
        calibration._CACHE["payload"] = None
        prior = calibration.calibration_prior(4)
        self.assertIsNotNone(prior)
        self.assertEqual(prior["trades"], 6)
        self.assertEqual(prior["confluence"], 4)
        self.assertIsNone(calibration.calibration_prior(None))
        self.assertIsNone(calibration.calibration_prior(6))  # no bucket

    def test_endpoint_serves_table(self):
        self._round_trip(3, True, 1)
        calibration._CACHE["payload"] = None
        resp = self.client.get("/api/risk/calibration",
                               headers={"Authorization": f"Bearer {self.token}"})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("buckets", body)
        self.assertEqual(body["buckets"]["3"]["trades"], 1)
        self.assertEqual(self.client.get("/api/risk/calibration").status_code, 401)


if __name__ == "__main__":
    unittest.main()
