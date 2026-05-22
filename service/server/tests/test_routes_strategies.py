"""Integration tests for /api/strategies endpoints + signal strategy linkage + leaderboard badge."""
from __future__ import annotations

import hashlib
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
from routes import create_app
from routes_shared import utc_now_iso_z


def _create_agent(name: str = "strat-agent", token_raw: str = "tok-strat") -> tuple[int, str]:
    token_hash = hashlib.sha256(token_raw.encode()).hexdigest()
    conn = database.get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO agents (name, token, token_hash, cash) VALUES (?, NULL, ?, 100000.0)",
        (name, token_hash),
    )
    agent_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return agent_id, token_raw


class StrategyCRUDTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())
        self.agent_id, self.token = _create_agent()
        self.auth = {"Authorization": f"Bearer {self.token}"}

    def tearDown(self):
        self.tmp.cleanup()

    def test_create_strategy_returns_201(self):
        resp = self.client.post(
            "/api/strategies",
            json={"name": "Mean Reversion", "description": "Buy dips"},
            headers=self.auth,
        )
        self.assertEqual(resp.status_code, 201)

    def test_create_strategy_returns_id_and_name(self):
        resp = self.client.post(
            "/api/strategies",
            json={"name": "Momentum Alpha"},
            headers=self.auth,
        )
        body = resp.json()
        self.assertIn("strategy_id", body)
        self.assertEqual(body["name"], "Momentum Alpha")

    def test_create_strategy_requires_name(self):
        resp = self.client.post(
            "/api/strategies",
            json={"description": "no name here"},
            headers=self.auth,
        )
        self.assertEqual(resp.status_code, 422)

    def test_create_strategy_without_auth_returns_401(self):
        resp = self.client.post(
            "/api/strategies",
            json={"name": "Ghost Strategy"},
        )
        self.assertEqual(resp.status_code, 401)

    def test_list_strategies_returns_empty_on_fresh_db(self):
        resp = self.client.get("/api/strategies", headers=self.auth)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["strategies"], [])

    def test_list_strategies_shows_created_strategy(self):
        self.client.post(
            "/api/strategies",
            json={"name": "Trend Following"},
            headers=self.auth,
        )
        resp = self.client.get("/api/strategies", headers=self.auth)
        strategies = resp.json()["strategies"]
        self.assertEqual(len(strategies), 1)
        self.assertEqual(strategies[0]["name"], "Trend Following")

    def test_list_strategies_requires_auth(self):
        resp = self.client.get("/api/strategies")
        self.assertEqual(resp.status_code, 401)

    def test_get_strategy_returns_detail(self):
        create_resp = self.client.post(
            "/api/strategies",
            json={"name": "MACD Cross", "description": "Classic MACD crossover"},
            headers=self.auth,
        )
        strategy_id = create_resp.json()["strategy_id"]
        resp = self.client.get(f"/api/strategies/{strategy_id}", headers=self.auth)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["name"], "MACD Cross")
        self.assertEqual(resp.json()["description"], "Classic MACD crossover")

    def test_get_nonexistent_strategy_returns_404(self):
        resp = self.client.get("/api/strategies/9999", headers=self.auth)
        self.assertEqual(resp.status_code, 404)

    def test_update_strategy_name_returns_200(self):
        create_resp = self.client.post(
            "/api/strategies",
            json={"name": "Old Name"},
            headers=self.auth,
        )
        strategy_id = create_resp.json()["strategy_id"]
        resp = self.client.put(
            f"/api/strategies/{strategy_id}",
            json={"name": "New Name"},
            headers=self.auth,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["name"], "New Name")

    def test_deactivate_strategy_hides_from_list(self):
        create_resp = self.client.post(
            "/api/strategies",
            json={"name": "Deactivate Me"},
            headers=self.auth,
        )
        strategy_id = create_resp.json()["strategy_id"]
        # Deactivate
        self.client.delete(f"/api/strategies/{strategy_id}", headers=self.auth)
        # Should not appear in list
        resp = self.client.get("/api/strategies", headers=self.auth)
        names = [s["name"] for s in resp.json()["strategies"]]
        self.assertNotIn("Deactivate Me", names)

    def test_strategy_defaults_not_validated(self):
        resp = self.client.post(
            "/api/strategies",
            json={"name": "Unvalidated"},
            headers=self.auth,
        )
        self.assertFalse(resp.json()["backtest_validated"])

    def test_create_strategy_with_config_json(self):
        resp = self.client.post(
            "/api/strategies",
            json={
                "name": "Configured Strategy",
                "config": {"symbols": ["AAPL", "MSFT"], "lookback_days": 90},
            },
            headers=self.auth,
        )
        self.assertEqual(resp.status_code, 201)
        body = resp.json()
        self.assertIn("config", body)


class StrategyValidationTests(unittest.TestCase):
    """Tests for the backtest_validated flag and Sharpe recording."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())
        self.agent_id, self.token = _create_agent("val-agent", "tok-val")
        self.auth = {"Authorization": f"Bearer {self.token}"}
        # Create a strategy to work with
        resp = self.client.post(
            "/api/strategies",
            json={"name": "Validation Test"},
            headers=self.auth,
        )
        self.strategy_id = resp.json()["strategy_id"]

    def tearDown(self):
        self.tmp.cleanup()

    def test_mark_strategy_validated_sets_flag(self):
        resp = self.client.post(
            f"/api/strategies/{self.strategy_id}/validate",
            json={"sharpe": 1.42},
            headers=self.auth,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["backtest_validated"])

    def test_mark_strategy_validated_stores_sharpe(self):
        self.client.post(
            f"/api/strategies/{self.strategy_id}/validate",
            json={"sharpe": 2.1},
            headers=self.auth,
        )
        resp = self.client.get(f"/api/strategies/{self.strategy_id}", headers=self.auth)
        self.assertAlmostEqual(resp.json()["last_backtest_sharpe"], 2.1, places=3)

    def test_validate_nonexistent_strategy_returns_404(self):
        resp = self.client.post(
            "/api/strategies/9999/validate",
            json={"sharpe": 1.0},
            headers=self.auth,
        )
        self.assertEqual(resp.status_code, 404)

    def test_validate_other_agents_strategy_returns_404(self):
        """Agent B cannot validate Agent A's strategy."""
        _, other_token = _create_agent("other-val", "tok-other-val")
        resp = self.client.post(
            f"/api/strategies/{self.strategy_id}/validate",
            json={"sharpe": 1.0},
            headers={"Authorization": f"Bearer {other_token}"},
        )
        self.assertEqual(resp.status_code, 404)


class StrategySignalLinkageTests(unittest.TestCase):
    """Signals can reference a strategy_id; the field round-trips correctly."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())
        self.agent_id, self.token = _create_agent("link-agent", "tok-link")
        self.auth = {"Authorization": f"Bearer {self.token}"}
        # Create strategy
        resp = self.client.post(
            "/api/strategies",
            json={"name": "Linked Strategy"},
            headers=self.auth,
        )
        self.strategy_id = resp.json()["strategy_id"]

    def tearDown(self):
        self.tmp.cleanup()

    def test_signals_table_has_strategy_id_column(self):
        """DB column exists after init_database."""
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(signals)")
        cols = {row["name"] for row in cursor.fetchall()}
        conn.close()
        self.assertIn("strategy_id", cols)

    def test_strategy_detail_includes_signal_count(self):
        """GET /api/strategies/{id} shows how many signals reference it."""
        resp = self.client.get(f"/api/strategies/{self.strategy_id}", headers=self.auth)
        self.assertIn("signal_count", resp.json())
        self.assertEqual(resp.json()["signal_count"], 0)


class LeaderboardBadgeTests(unittest.TestCase):
    """Leaderboard entries carry backtest_validated_strategy flag."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())
        self.agent_id, self.token = _create_agent("lb-agent", "tok-lb")
        self.auth = {"Authorization": f"Bearer {self.token}"}

    def tearDown(self):
        self.tmp.cleanup()

    def test_leaderboard_includes_backtest_validated_flag(self):
        resp = self.client.get("/api/profit/history?limit=5")
        self.assertEqual(resp.status_code, 200)
        agents = resp.json().get("top_agents", [])
        # Our agent appears in the leaderboard; flag should be present
        if agents:
            self.assertIn("backtest_validated_strategy", agents[0])

    def test_leaderboard_flag_is_false_without_validated_strategy(self):
        resp = self.client.get("/api/profit/history?limit=5")
        agents = resp.json().get("top_agents", [])
        if agents:
            entry = next((a for a in agents if a["agent_id"] == self.agent_id), None)
            if entry:
                self.assertFalse(entry["backtest_validated_strategy"])

    def test_leaderboard_flag_true_after_validation(self):
        # Create and validate a strategy
        create_resp = self.client.post(
            "/api/strategies",
            json={"name": "Badge Strategy"},
            headers=self.auth,
        )
        strategy_id = create_resp.json()["strategy_id"]
        self.client.post(
            f"/api/strategies/{strategy_id}/validate",
            json={"sharpe": 1.5},
            headers=self.auth,
        )
        resp = self.client.get("/api/profit/history?limit=50")
        agents = resp.json().get("top_agents", [])
        entry = next((a for a in agents if a["agent_id"] == self.agent_id), None)
        self.assertIsNotNone(entry)
        self.assertTrue(entry["backtest_validated_strategy"])


if __name__ == "__main__":
    unittest.main()
