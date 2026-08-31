"""Swing-feed crawl-status monitoring on the admin console
(routes_admin_swing_feeds.py). Probes are patched — no live upstream calls."""
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
import routes_admin_swing_feeds as rasf
from routes import create_app


def _fake_fetch_json(url: str, params=None):
    """Deterministic payloads for all six probe URLs."""
    if "yahoo" in url:
        return {"chart": {"result": [{
            "timestamp": [1756400000],
            "indicators": {"quote": [{"close": [16.5]}]},
        }]}}
    if "okx.com" in url:
        return {"data": [["1756425600000", "1", "2", "0.5", "109000", "9"]]}
    if "cnn.io" in url:
        return {"fear_and_greed": {"score": 55.2, "rating": "greed"}}
    if "alternative.me" in url:
        return {"data": [{"value": "61", "value_classification": "Greed"}]}
    if "faireconomy" in url:
        return [
            {"country": "USD", "impact": "High", "title": "CPI"},
            {"country": "USD", "impact": "Low", "title": "noise"},
            {"country": "EUR", "impact": "High", "title": "ECB"},
        ]
    raise AssertionError(f"unexpected probe url {url}")


class AdminSwingFeedStatusTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())
        from admin_auth import create_admin
        create_admin("root@test.com", "rootpass123", "superadmin")
        r = self.client.post("/api/admin/login",
                             json={"email": "root@test.com", "password": "rootpass123"})
        self.admin = {"Authorization": f"Bearer {r.json()['token']}"}
        # each test starts with a cold status cache
        rasf._cache["at"] = 0.0
        rasf._cache["payload"] = None

    def tearDown(self):
        self.tmp.cleanup()

    def test_requires_admin_session(self):
        self.assertEqual(self.client.get("/api/admin/swing-feeds/status").status_code, 401)

    def test_reports_all_six_feeds_ok(self):
        with patch.object(rasf, "_fetch_json", side_effect=_fake_fetch_json):
            r = self.client.get("/api/admin/swing-feeds/status", headers=self.admin)
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(len(body["feeds"]), 6)
        self.assertEqual(body["ok_count"], 6)
        self.assertFalse(body["cached"])
        by_key = {f["feed"]: f for f in body["feeds"]}
        self.assertEqual(
            set(by_key),
            {"price_us", "price_crypto", "macro_regime",
             "sentiment_stock", "sentiment_crypto", "macro_calendar"},
        )
        self.assertIn("VIX 16.5", by_key["macro_regime"]["detail"])
        self.assertIn("CNN F&G 55", by_key["sentiment_stock"]["detail"])
        # only the USD+High rows count as binary events
        self.assertIn("1 high-impact USD events", by_key["macro_calendar"]["detail"])
        for f in body["feeds"]:
            self.assertTrue(f["ok"], f)
            self.assertIsNotNone(f["latency_ms"])

    def test_dead_upstream_is_a_status_row_not_a_500(self):
        def flaky(url, params=None):
            if "okx.com" in url:
                raise TimeoutError("upstream dead")
            return _fake_fetch_json(url, params)

        with patch.object(rasf, "_fetch_json", side_effect=flaky):
            r = self.client.get("/api/admin/swing-feeds/status", headers=self.admin)
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["ok_count"], 5)
        crypto = next(f for f in body["feeds"] if f["feed"] == "price_crypto")
        self.assertFalse(crypto["ok"])
        self.assertIn("TimeoutError", crypto["error"])

    def test_second_call_is_cached_and_refresh_reprobes(self):
        with patch.object(rasf, "_fetch_json", side_effect=_fake_fetch_json) as fetch:
            first = self.client.get("/api/admin/swing-feeds/status", headers=self.admin)
            calls_after_first = fetch.call_count
            second = self.client.get("/api/admin/swing-feeds/status", headers=self.admin)
            self.assertEqual(fetch.call_count, calls_after_first)  # served from cache
            self.assertTrue(second.json()["cached"])
            self.assertFalse(first.json()["cached"])
            third = self.client.get("/api/admin/swing-feeds/status?refresh=true",
                                    headers=self.admin)
            self.assertGreater(fetch.call_count, calls_after_first)
            self.assertFalse(third.json()["cached"])


if __name__ == "__main__":
    unittest.main()
