"""psych_feed.shock_series + /api/market-intel/shock-history.

shock_history() exists but keeps only rows where shock is True, because its
callers (confluence B5, the regime filter) only care about breaches. A chart
needs the whole sigma line so the 3σ threshold has something to be crossed —
that is what shock_series provides, without changing shock_history's contract.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
import psych_feed
from routes import create_app


def _stamp(hours_ago: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


class ShockSeriesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())
        self._seed()

    def tearDown(self):
        self.tmp.cleanup()

    def _seed(self):
        """Three snapshots: a calm BTC reading, a 3σ breach, and an ETH row."""
        rows = [
            (_stamp(3), [{"symbol": "BTC", "sigma_multiple": 1.1, "volume_ratio": 0.9,
                          "latest_return_pct": 0.2, "shock": False},
                         {"symbol": "ETH", "sigma_multiple": 0.8, "volume_ratio": 1.0,
                          "latest_return_pct": -0.1, "shock": False}]),
            (_stamp(2), [{"symbol": "BTC", "sigma_multiple": 3.4, "volume_ratio": 2.6,
                          "latest_return_pct": -4.1, "shock": True}]),
            (_stamp(1), [{"symbol": "BTC", "sigma_multiple": 1.6, "volume_ratio": 1.2,
                          "latest_return_pct": 0.4, "shock": False}]),
        ]
        conn = database.get_db_connection()
        cur = conn.cursor()
        for created_at, shocks in rows:
            cur.execute(
                "INSERT INTO psych_snapshots (snapshot_key, shock_json, created_at) VALUES (?, ?, ?)",
                ("test", json.dumps(shocks), created_at))
        conn.commit()
        conn.close()

    def test_series_keeps_unflagged_readings(self):
        """The whole line — shock_history would have dropped 3 of these 4."""
        out = psych_feed.shock_series(hours=72)
        btc = out["series"]["BTC"]
        self.assertEqual([p["sigma_multiple"] for p in btc], [1.1, 3.4, 1.6])
        self.assertEqual([p["shock"] for p in btc], [False, True, False])

    def test_threshold_is_reported_so_the_chart_can_draw_it(self):
        out = psych_feed.shock_series(hours=72)
        self.assertEqual(out["threshold_sigma"], psych_feed.SHOCK_SIGMA_MULTIPLE)
        self.assertTrue(out["estimated"], "shock is a liquidation proxy — must stay labelled")

    def test_symbol_filter(self):
        out = psych_feed.shock_series(hours=72, symbol="eth")
        self.assertEqual(list(out["series"].keys()), ["ETH"])

    def test_window_excludes_older_rows(self):
        out = psych_feed.shock_series(hours=2)
        # the 3h-old snapshot (the only ETH row) falls outside a 2h window
        self.assertNotIn("ETH", out["series"])

    def test_empty_window_is_unavailable_not_an_error(self):
        out = psych_feed.shock_series(hours=1)
        self.assertIn("series", out)
        self.assertFalse(out["available"] and not out["series"])

    def test_route_serves_the_series(self):
        r = self.client.get("/api/market-intel/shock-history?hours=72")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["threshold_sigma"], 3.0)
        self.assertIn("BTC", body["series"])

    def test_route_clamps_absurd_windows(self):
        r = self.client.get("/api/market-intel/shock-history?hours=99999")
        self.assertEqual(r.status_code, 200)
        self.assertLessEqual(r.json()["hours"], 720)


if __name__ == "__main__":
    unittest.main()
