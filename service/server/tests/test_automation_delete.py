"""Regression: deleting an automation rule that has run history.

Prod (MySQL) enforces the FKs automation_runs.config_id and
agent_mode_decisions.config_id -> automation_configs.id with no ON DELETE
CASCADE, so DELETE /api/automation/configs/{id} raised MySQL error 1451 once a
rule had ever run. SQLite does not enforce the FK, so the bug shipped unseen:
the frontend's 제거 (Remove) button silently did nothing in production.

The endpoint must delete child rows first, then the config, and must not leave
orphaned children behind on SQLite either.
"""

from __future__ import annotations

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


class AutomationDeleteTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())
        resp = self.client.post(
            "/api/claw/agents/selfRegister",
            json={"name": "remover", "password": "pw123", "initial_balance": 100000.0})
        assert resp.status_code == 200
        body = resp.json()
        self.agent_id = body["agent_id"]
        self.headers = {"Authorization": f"Bearer {body['token']}"}

    def tearDown(self):
        self.tmp.cleanup()

    def _create_rule(self) -> int:
        resp = self.client.post(
            "/api/automation/configs", headers=self.headers,
            json={"symbol": "BTC", "market": "crypto", "interval_minutes": 60,
                  "min_confidence": 0.65, "size_usd": 500})
        self.assertEqual(resp.status_code, 200)
        return resp.json()["id"]

    def _count(self, table: str, config_id: int) -> int:
        conn = database.get_db_connection()
        try:
            cursor = conn.cursor()
            if table == "automation_configs":
                cursor.execute("SELECT COUNT(*) AS n FROM automation_configs WHERE id = ?",
                               (config_id,))
            else:
                cursor.execute(f"SELECT COUNT(*) AS n FROM {table} WHERE config_id = ?",  # noqa: S608
                               (config_id,))
            row = cursor.fetchone()
            return list(dict(row).values())[0]
        finally:
            conn.close()

    def test_delete_rule_with_run_history(self):
        config_id = self._create_rule()
        # Simulate the worker having run this rule (the prod trigger) plus an
        # agent-mode decision row — both tables FK automation_configs in MySQL.
        conn = database.get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO automation_runs (config_id, agent_id, action, confidence, executed)"
                " VALUES (?, ?, 'buy', 0.8, 1)", (config_id, self.agent_id))
            cursor.execute(
                "INSERT INTO agent_mode_decisions (config_id, agent_id, decided_at, params_json)"
                " VALUES (?, ?, '2026-07-19T00:00:00', '{}')", (config_id, self.agent_id))
            conn.commit()
        finally:
            conn.close()

        resp = self.client.delete(f"/api/automation/configs/{config_id}", headers=self.headers)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"ok": True})

        self.assertEqual(self._count("automation_configs", config_id), 0)
        # No orphans: children must be gone too (MySQL would refuse the parent
        # delete otherwise; SQLite would silently keep the rows).
        self.assertEqual(self._count("automation_runs", config_id), 0)
        self.assertEqual(self._count("agent_mode_decisions", config_id), 0)

    def test_delete_rule_without_history_still_works(self):
        config_id = self._create_rule()
        resp = self.client.delete(f"/api/automation/configs/{config_id}", headers=self.headers)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self._count("automation_configs", config_id), 0)

    def test_delete_missing_rule_404(self):
        resp = self.client.delete("/api/automation/configs/999999", headers=self.headers)
        self.assertEqual(resp.status_code, 404)

    def test_delete_other_agents_rule_404(self):
        config_id = self._create_rule()
        other = self.client.post(
            "/api/claw/agents/selfRegister",
            json={"name": "intruder", "password": "pw123", "initial_balance": 1000.0}).json()
        resp = self.client.delete(
            f"/api/automation/configs/{config_id}",
            headers={"Authorization": f"Bearer {other['token']}"})
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(self._count("automation_configs", config_id), 1)


if __name__ == "__main__":
    unittest.main()
