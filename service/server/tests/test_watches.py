"""Plan 06 C3 — personal watch functions (metrics mocked; no live calls)."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
import watch_engine
from routes import create_app


class WatchTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())
        resp = self.client.post(
            "/api/claw/agents/selfRegister",
            json={"name": "watcher", "password": "pw123", "initial_balance": 1000.0})
        body = resp.json()
        self.agent_id = body["agent_id"]
        self.token = body["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def tearDown(self):
        self.tmp.cleanup()

    def _create(self, **over):
        body = {"name": "BTC dip", "metric": "price", "symbol": "BTCUSDT",
                "comparator": "below", "threshold": 60000}
        body.update(over)
        return self.client.post("/api/watches", headers=self.headers, json=body)


class CrudTests(WatchTestCase):
    def test_create_list_update_delete(self):
        with patch.object(watch_engine, "resolve_metric", return_value=63000.0):
            r = self._create()
            self.assertEqual(r.status_code, 200, r.text)
            wid = r.json()["id"]
            listed = self.client.get("/api/watches", headers=self.headers).json()
            self.assertEqual(len(listed["watches"]), 1)
            self.assertEqual(listed["watches"][0]["current_value"], 63000.0)
            self.assertIn("price", listed["metrics"])
            up = self.client.put(f"/api/watches/{wid}", headers=self.headers,
                                 json={"name": "BTC deeper dip", "metric": "price",
                                       "symbol": "BTCUSDT", "comparator": "below",
                                       "threshold": 55000})
            self.assertEqual(up.status_code, 200)
        listed = self.client.get("/api/watches", headers=self.headers).json()["watches"]
        self.assertEqual(listed[0]["threshold"], 55000)
        self.assertEqual(self.client.delete(f"/api/watches/{wid}", headers=self.headers).status_code, 200)
        self.assertEqual(self.client.delete(f"/api/watches/{wid}", headers=self.headers).status_code, 404)

    def test_validation(self):
        self.assertEqual(self._create(metric="moon_phase").status_code, 422)
        self.assertEqual(self._create(comparator="equals").status_code, 422)
        self.assertEqual(self._create(cooldown_min=1).status_code, 422)
        self.assertEqual(self._create(name="").status_code, 422)
        # price requires a symbol
        self.assertEqual(self._create(symbol=None).status_code, 400)
        # fear_greed does not
        with patch.object(watch_engine, "resolve_metric", return_value=25.0):
            self.assertEqual(self._create(metric="fear_greed", symbol=None,
                                          comparator="below", threshold=30).status_code, 200)

    def test_auth_required(self):
        self.assertEqual(self.client.get("/api/watches").status_code, 401)
        self.assertEqual(self.client.post("/api/watches", json={
            "name": "x", "metric": "fear_greed", "comparator": "below",
            "threshold": 30}).status_code, 401)

    def test_limit_per_agent(self):
        with patch.object(watch_engine, "resolve_metric", return_value=1.0):
            for i in range(20):
                self.assertEqual(self._create(name=f"w{i}").status_code, 200)
            self.assertEqual(self._create(name="too many").status_code, 400)


class EngineTests(WatchTestCase):
    def test_fires_on_crossing(self):
        self._create(comparator="below", threshold=60000)
        with patch.object(watch_engine, "resolve_metric", return_value=59000.0), \
             patch("alerts.send_alert") as mock_alert:
            result = watch_engine.run_watch_tick()
        self.assertEqual(result["fired"], 1)
        mock_alert.assert_called_once()
        args = mock_alert.call_args[0]
        self.assertEqual(args[1], "custom")
        self.assertEqual(args[2], "watch")
        self.assertEqual(args[3]["name"], "BTC dip")
        self.assertIn("59,000", args[3]["value"])

    def test_no_fire_when_not_crossed(self):
        self._create(comparator="below", threshold=60000)
        with patch.object(watch_engine, "resolve_metric", return_value=63000.0), \
             patch("alerts.send_alert") as mock_alert:
            result = watch_engine.run_watch_tick()
        self.assertEqual(result["fired"], 0)
        mock_alert.assert_not_called()

    def test_missing_metric_never_fires(self):
        """A metric whose source is down must not fire (no fabricated value)."""
        self._create(comparator="below", threshold=60000)
        with patch.object(watch_engine, "resolve_metric", return_value=None), \
             patch("alerts.send_alert") as mock_alert:
            result = watch_engine.run_watch_tick()
        self.assertEqual(result["fired"], 0)
        mock_alert.assert_not_called()

    def test_cooldown_blocks_refire(self):
        self._create(comparator="below", threshold=60000)
        with patch.object(watch_engine, "resolve_metric", return_value=59000.0), \
             patch("alerts.send_alert"):
            self.assertEqual(watch_engine.run_watch_tick()["fired"], 1)
            self.assertEqual(watch_engine.run_watch_tick()["fired"], 0)  # cooling down

    def test_cooldown_expires(self):
        self._create(comparator="below", threshold=60000, cooldown_min=5)
        old = (datetime.now(timezone.utc) - timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
        conn = database.get_db_connection()
        conn.execute("UPDATE user_watches SET last_fired_at = ?", (old,))
        conn.commit()
        conn.close()
        with patch.object(watch_engine, "resolve_metric", return_value=59000.0), \
             patch("alerts.send_alert"):
            self.assertEqual(watch_engine.run_watch_tick()["fired"], 1)

    def test_disabled_watch_skipped(self):
        r = self._create()
        wid = r.json()["id"]
        conn = database.get_db_connection()
        conn.execute("UPDATE user_watches SET enabled = 0 WHERE id = ?", (wid,))
        conn.commit()
        conn.close()
        with patch.object(watch_engine, "resolve_metric", return_value=1.0), \
             patch("alerts.send_alert") as mock_alert:
            result = watch_engine.run_watch_tick()
        self.assertEqual(result["checked"], 0)
        mock_alert.assert_not_called()

    def test_metric_cached_within_tick(self):
        for i in range(3):
            self._create(name=f"w{i}", comparator="above", threshold=1)
        with patch.object(watch_engine, "resolve_metric", return_value=99999.0) as mock_metric, \
             patch("alerts.send_alert"):
            watch_engine.run_watch_tick()
        # 3 watches, same (metric, symbol) -> one fetch
        self.assertEqual(mock_metric.call_count, 1)

    def test_comparators(self):
        self.assertTrue(watch_engine.crosses(10, "above", 5))
        self.assertFalse(watch_engine.crosses(10, "above", 15))
        self.assertTrue(watch_engine.crosses(3, "below", 5))
        self.assertFalse(watch_engine.crosses(7, "below", 5))


if __name__ == "__main__":
    unittest.main()
