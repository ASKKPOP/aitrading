"""GET /api/markets/top-us-tech (owner 2026-08-31: the simple slot block
needs USA stock): returns the hottest US tech names from the newest research
batch — same roster and hotness algorithm as the fleet's R20-MUST selection —
with a mega-cap fallback when no theses exist."""
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

import database
import symbol_research as sr
from routes import create_app


class TopUsTechTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "t.db")
        database.init_database()
        self.client = TestClient(create_app())

    def tearDown(self):
        self.tmp.cleanup()

    def _thesis(self, cur, sym, mom, batch=1, market="us-stock"):
        cur.execute(
            """INSERT INTO research_theses
               (batch_id, market, symbol, market_type, direction, thesis,
                risks, invalidation, expected_move_pct, horizon_hours,
                confidence, ev_per_day_pct, final_score, selectable, planner,
                factor_scores_json, created_at, expires_at)
               VALUES (?, ?, ?, 'spot', 'long', 't', 'r', 'i', 5.0, 24, 0.7,
                       1.0, 0.5, 1, 'llm', ?, '2026-08-31T00:00:00Z',
                       '2099-01-01T00:00:00Z')""",
            (batch, market, sym,
             json.dumps({"factors": {"mom_2d": mom, "vol_ratio": 1.0}})))

    def test_empty_db_serves_the_fallback(self):
        r = self.client.get("/api/markets/top-us-tech")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["source"], "fallback")
        self.assertEqual(body["symbols"], ["NVDA", "AAPL", "MSFT", "TSLA", "META"])

    def test_research_batch_ranks_tech_by_hotness_and_drops_non_tech(self):
        conn = database.get_db_connection()
        cur = conn.cursor()
        self._thesis(cur, "KO", 9.0)      # non-tech: never a chip
        self._thesis(cur, "NVDA", 2.0)
        self._thesis(cur, "AMD", 5.0)
        self._thesis(cur, "MSFT", 1.0)
        self._thesis(cur, "BTCUSDT", 8.0, market="crypto")
        conn.commit()
        conn.close()
        r = self.client.get("/api/markets/top-us-tech")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["source"], "research")
        self.assertEqual(body["symbols"], ["AMD", "NVDA", "MSFT"])
        for s in body["symbols"]:
            self.assertIn(s, sr.US_TECH_HOT_UNIVERSE)


if __name__ == "__main__":
    unittest.main()
