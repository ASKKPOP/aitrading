"""Integration tests for backtest runs API (/api/backtest/runs)."""
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


def _create_agent(name: str = "bt-agent", token_raw: str = "tok-bt") -> tuple[int, str]:
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


def _create_strategy(agent_id: int, name: str = "Test Strategy") -> int:
    conn = database.get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO strategies (agent_id, name) VALUES (?, ?)",
        (agent_id, name),
    )
    strategy_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return strategy_id


_RUN_BODY = {
    "start_at": "2024-01-01T00:00:00Z",
    "end_at": "2024-12-31T00:00:00Z",
    "initial_cash": 100000.0,
}


class TestCreateBacktestRun(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())
        self.agent_id, self.token = _create_agent()

    def tearDown(self):
        self.tmp.cleanup()

    def _auth(self):
        return {"Authorization": f"Bearer {self.token}"}

    def test_create_run_returns_201(self):
        resp = self.client.post("/api/backtest/runs", json=_RUN_BODY, headers=self._auth())
        self.assertEqual(resp.status_code, 201)

    def test_create_run_returns_run_id(self):
        resp = self.client.post("/api/backtest/runs", json=_RUN_BODY, headers=self._auth())
        body = resp.json()
        self.assertIn("run_id", body)
        self.assertIsInstance(body["run_id"], int)

    def test_create_run_requires_auth(self):
        resp = self.client.post("/api/backtest/runs", json=_RUN_BODY)
        self.assertEqual(resp.status_code, 401)

    def test_create_run_rejects_negative_cash(self):
        body = {**_RUN_BODY, "initial_cash": -500.0}
        resp = self.client.post("/api/backtest/runs", json=body, headers=self._auth())
        self.assertEqual(resp.status_code, 422)

    def test_create_run_rejects_zero_cash(self):
        body = {**_RUN_BODY, "initial_cash": 0.0}
        resp = self.client.post("/api/backtest/runs", json=body, headers=self._auth())
        self.assertEqual(resp.status_code, 422)

    def test_create_run_accepts_optional_strategy_id(self):
        strategy_id = _create_strategy(self.agent_id)
        body = {**_RUN_BODY, "strategy_id": strategy_id}
        resp = self.client.post("/api/backtest/runs", json=body, headers=self._auth())
        self.assertEqual(resp.status_code, 201)

    def test_create_run_accepts_optional_market_and_symbol(self):
        body = {**_RUN_BODY, "market": "us-stock", "symbol": "AAPL"}
        resp = self.client.post("/api/backtest/runs", json=body, headers=self._auth())
        self.assertEqual(resp.status_code, 201)


class TestGetBacktestRun(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())
        self.agent_id, self.token = _create_agent()

    def tearDown(self):
        self.tmp.cleanup()

    def _auth(self):
        return {"Authorization": f"Bearer {self.token}"}

    def _create(self):
        resp = self.client.post("/api/backtest/runs", json=_RUN_BODY, headers=self._auth())
        return resp.json()["run_id"]

    def test_get_run_returns_200(self):
        run_id = self._create()
        resp = self.client.get(f"/api/backtest/runs/{run_id}", headers=self._auth())
        self.assertEqual(resp.status_code, 200)

    def test_get_run_has_expected_fields(self):
        run_id = self._create()
        resp = self.client.get(f"/api/backtest/runs/{run_id}", headers=self._auth())
        body = resp.json()
        for field in ("run_id", "status", "config", "created_at"):
            self.assertIn(field, body, f"missing field: {field}")

    def test_get_run_config_matches_request(self):
        run_id = self._create()
        resp = self.client.get(f"/api/backtest/runs/{run_id}", headers=self._auth())
        cfg = resp.json()["config"]
        self.assertEqual(cfg["start_at"], _RUN_BODY["start_at"])
        self.assertEqual(cfg["end_at"], _RUN_BODY["end_at"])

    def test_get_run_404_for_missing(self):
        resp = self.client.get("/api/backtest/runs/99999", headers=self._auth())
        self.assertEqual(resp.status_code, 404)

    def test_get_run_404_for_other_agent(self):
        run_id = self._create()
        _, other_token = _create_agent("other-a", "tok-other-a")
        resp = self.client.get(
            f"/api/backtest/runs/{run_id}",
            headers={"Authorization": f"Bearer {other_token}"},
        )
        self.assertEqual(resp.status_code, 404)

    def test_get_run_status_is_valid_value(self):
        run_id = self._create()
        resp = self.client.get(f"/api/backtest/runs/{run_id}", headers=self._auth())
        status = resp.json()["status"]
        self.assertIn(status, ("pending", "running", "completed", "failed"))

    def test_get_completed_run_has_result(self):
        # TestClient runs BackgroundTasks synchronously, so the run completes immediately.
        run_id = self._create()
        resp = self.client.get(f"/api/backtest/runs/{run_id}", headers=self._auth())
        body = resp.json()
        if body["status"] == "completed":
            result = body.get("result")
            self.assertIsNotNone(result)
            self.assertIn("summary", result)


class TestListBacktestRuns(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())
        self.agent_id, self.token = _create_agent()

    def tearDown(self):
        self.tmp.cleanup()

    def _auth(self):
        return {"Authorization": f"Bearer {self.token}"}

    def test_list_runs_returns_200(self):
        resp = self.client.get("/api/backtest/runs", headers=self._auth())
        self.assertEqual(resp.status_code, 200)

    def test_list_runs_has_runs_key(self):
        resp = self.client.get("/api/backtest/runs", headers=self._auth())
        self.assertIn("runs", resp.json())

    def test_list_runs_empty_for_new_agent(self):
        resp = self.client.get("/api/backtest/runs", headers=self._auth())
        self.assertEqual(resp.json()["runs"], [])

    def test_list_runs_includes_created_run(self):
        self.client.post("/api/backtest/runs", json=_RUN_BODY, headers=self._auth())
        resp = self.client.get("/api/backtest/runs", headers=self._auth())
        self.assertEqual(len(resp.json()["runs"]), 1)

    def test_list_runs_isolates_by_agent(self):
        self.client.post("/api/backtest/runs", json=_RUN_BODY, headers=self._auth())
        _, other_token = _create_agent("other-b", "tok-other-b")
        resp = self.client.get(
            "/api/backtest/runs",
            headers={"Authorization": f"Bearer {other_token}"},
        )
        self.assertEqual(resp.json()["runs"], [])

    def test_list_runs_requires_auth(self):
        resp = self.client.get("/api/backtest/runs")
        self.assertEqual(resp.status_code, 401)

    def test_list_runs_count_grows_with_each_create(self):
        self.client.post("/api/backtest/runs", json=_RUN_BODY, headers=self._auth())
        self.client.post("/api/backtest/runs", json=_RUN_BODY, headers=self._auth())
        resp = self.client.get("/api/backtest/runs", headers=self._auth())
        self.assertEqual(len(resp.json()["runs"]), 2)


class TestDeleteBacktestRun(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())
        self.agent_id, self.token = _create_agent()

    def tearDown(self):
        self.tmp.cleanup()

    def _auth(self):
        return {"Authorization": f"Bearer {self.token}"}

    def _create(self):
        resp = self.client.post("/api/backtest/runs", json=_RUN_BODY, headers=self._auth())
        return resp.json()["run_id"]

    def test_delete_run_returns_204(self):
        run_id = self._create()
        resp = self.client.delete(f"/api/backtest/runs/{run_id}", headers=self._auth())
        self.assertEqual(resp.status_code, 204)

    def test_delete_removes_run_from_list(self):
        run_id = self._create()
        self.client.delete(f"/api/backtest/runs/{run_id}", headers=self._auth())
        resp = self.client.get("/api/backtest/runs", headers=self._auth())
        self.assertEqual(resp.json()["runs"], [])

    def test_delete_run_404_for_missing(self):
        resp = self.client.delete("/api/backtest/runs/99999", headers=self._auth())
        self.assertEqual(resp.status_code, 404)

    def test_delete_run_404_for_other_agent(self):
        run_id = self._create()
        _, other_token = _create_agent("other-c", "tok-other-c")
        resp = self.client.delete(
            f"/api/backtest/runs/{run_id}",
            headers={"Authorization": f"Bearer {other_token}"},
        )
        self.assertEqual(resp.status_code, 404)


class TestGetRunTrades(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())
        self.agent_id, self.token = _create_agent()

    def tearDown(self):
        self.tmp.cleanup()

    def _auth(self):
        return {"Authorization": f"Bearer {self.token}"}

    def _create(self):
        resp = self.client.post("/api/backtest/runs", json=_RUN_BODY, headers=self._auth())
        return resp.json()["run_id"]

    def test_get_trades_returns_200(self):
        run_id = self._create()
        resp = self.client.get(f"/api/backtest/runs/{run_id}/trades", headers=self._auth())
        self.assertEqual(resp.status_code, 200)

    def test_get_trades_has_trades_key(self):
        run_id = self._create()
        resp = self.client.get(f"/api/backtest/runs/{run_id}/trades", headers=self._auth())
        self.assertIn("trades", resp.json())

    def test_get_trades_returns_list(self):
        run_id = self._create()
        resp = self.client.get(f"/api/backtest/runs/{run_id}/trades", headers=self._auth())
        self.assertIsInstance(resp.json()["trades"], list)

    def test_get_trades_404_for_missing(self):
        resp = self.client.get("/api/backtest/runs/99999/trades", headers=self._auth())
        self.assertEqual(resp.status_code, 404)

    def test_get_trades_404_for_other_agent(self):
        run_id = self._create()
        _, other_token = _create_agent("other-d", "tok-other-d")
        resp = self.client.get(
            f"/api/backtest/runs/{run_id}/trades",
            headers={"Authorization": f"Bearer {other_token}"},
        )
        self.assertEqual(resp.status_code, 404)


class TestPromoteBacktestRun(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())
        self.agent_id, self.token = _create_agent()

    def tearDown(self):
        self.tmp.cleanup()

    def _auth(self):
        return {"Authorization": f"Bearer {self.token}"}

    def _create_run(self):
        resp = self.client.post("/api/backtest/runs", json=_RUN_BODY, headers=self._auth())
        return resp.json()["run_id"]

    def test_promote_returns_200(self):
        strategy_id = _create_strategy(self.agent_id)
        run_id = self._create_run()
        resp = self.client.post(
            f"/api/backtest/runs/{run_id}/promote",
            json={"strategy_id": strategy_id},
            headers=self._auth(),
        )
        self.assertEqual(resp.status_code, 200)

    def test_promote_updates_strategy_last_backtest_at(self):
        strategy_id = _create_strategy(self.agent_id)
        run_id = self._create_run()
        self.client.post(
            f"/api/backtest/runs/{run_id}/promote",
            json={"strategy_id": strategy_id},
            headers=self._auth(),
        )
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT last_backtest_at FROM strategies WHERE id=?", (strategy_id,)
        )
        row = cursor.fetchone()
        conn.close()
        self.assertIsNotNone(row["last_backtest_at"])

    def test_promote_sets_backtest_validated_when_sharpe_positive(self):
        # Insert a run with a positive Sharpe in result directly.
        import json as _json
        strategy_id = _create_strategy(self.agent_id)
        conn = database.get_db_connection()
        cursor = conn.cursor()
        result_json = _json.dumps({"summary": {"sharpe_ratio": 1.5}})
        cursor.execute(
            """INSERT INTO backtest_runs
               (agent_id, status, config, result, created_at)
               VALUES (?, 'completed', '{}', ?, ?)""",
            (self.agent_id, result_json, utc_now_iso_z()),
        )
        run_id = cursor.lastrowid
        conn.commit()
        conn.close()

        self.client.post(
            f"/api/backtest/runs/{run_id}/promote",
            json={"strategy_id": strategy_id},
            headers=self._auth(),
        )
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT backtest_validated FROM strategies WHERE id=?", (strategy_id,))
        row = cursor.fetchone()
        conn.close()
        self.assertEqual(row["backtest_validated"], 1)

    def test_promote_404_for_missing_run(self):
        strategy_id = _create_strategy(self.agent_id)
        resp = self.client.post(
            "/api/backtest/runs/99999/promote",
            json={"strategy_id": strategy_id},
            headers=self._auth(),
        )
        self.assertEqual(resp.status_code, 404)

    def test_promote_404_for_missing_strategy(self):
        run_id = self._create_run()
        resp = self.client.post(
            f"/api/backtest/runs/{run_id}/promote",
            json={"strategy_id": 99999},
            headers=self._auth(),
        )
        self.assertEqual(resp.status_code, 404)

    def test_promote_requires_auth(self):
        run_id = self._create_run()
        resp = self.client.post(
            f"/api/backtest/runs/{run_id}/promote",
            json={"strategy_id": 1},
        )
        self.assertEqual(resp.status_code, 401)

    def test_promote_returns_strategy_validation_status(self):
        strategy_id = _create_strategy(self.agent_id)
        run_id = self._create_run()
        resp = self.client.post(
            f"/api/backtest/runs/{run_id}/promote",
            json={"strategy_id": strategy_id},
            headers=self._auth(),
        )
        body = resp.json()
        self.assertIn("strategy_id", body)
        self.assertIn("backtest_validated", body)
