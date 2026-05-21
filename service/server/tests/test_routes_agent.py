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


def _register(client: TestClient, name: str = "test-agent", password: str = "pw123") -> dict:
    resp = client.post(
        "/api/claw/agents/selfRegister",
        json={"name": name, "password": password, "initial_balance": 100000.0},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


class AgentRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())

    def tearDown(self) -> None:
        self.tmp.cleanup()

    # --- registration ---

    def test_register_returns_token_and_id(self) -> None:
        data = _register(self.client)
        self.assertIn("token", data)
        self.assertIn("agent_id", data)
        self.assertEqual(data["name"], "test-agent")

    def test_register_duplicate_name_rejected(self) -> None:
        _register(self.client)
        resp = self.client.post(
            "/api/claw/agents/selfRegister",
            json={"name": "test-agent", "password": "other"},
        )
        self.assertEqual(resp.status_code, 400)

    def test_register_empty_name_rejected(self) -> None:
        resp = self.client.post(
            "/api/claw/agents/selfRegister",
            json={"name": "   ", "password": "pw"},
        )
        self.assertEqual(resp.status_code, 400)

    # --- login ---

    def test_login_success(self) -> None:
        _register(self.client, name="login-agent", password="secret")
        resp = self.client.post(
            "/api/claw/agents/login",
            json={"name": "login-agent", "password": "secret"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("token", data)
        self.assertEqual(data["name"], "login-agent")

    def test_login_wrong_password_rejected(self) -> None:
        _register(self.client, name="login-agent2", password="correct")
        resp = self.client.post(
            "/api/claw/agents/login",
            json={"name": "login-agent2", "password": "wrong"},
        )
        self.assertEqual(resp.status_code, 401)

    def test_login_unknown_agent_rejected(self) -> None:
        resp = self.client.post(
            "/api/claw/agents/login",
            json={"name": "nobody", "password": "pw"},
        )
        self.assertEqual(resp.status_code, 401)

    # --- /api/claw/agents/me ---

    def test_get_agent_info_requires_auth(self) -> None:
        resp = self.client.get("/api/claw/agents/me")
        self.assertEqual(resp.status_code, 401)

    def test_get_agent_info_success(self) -> None:
        data = _register(self.client)
        resp = self.client.get(
            "/api/claw/agents/me",
            headers={"Authorization": f"Bearer {data['token']}"},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["id"], data["agent_id"])
        self.assertEqual(body["name"], "test-agent")

    def test_get_agent_info_invalid_token_rejected(self) -> None:
        resp = self.client.get(
            "/api/claw/agents/me",
            headers={"Authorization": "Bearer not-a-real-token"},
        )
        self.assertEqual(resp.status_code, 401)

    # --- /api/claw/agents/me/points ---

    def test_get_agent_points_requires_auth(self) -> None:
        resp = self.client.get("/api/claw/agents/me/points")
        self.assertEqual(resp.status_code, 401)

    def test_get_agent_points_success(self) -> None:
        data = _register(self.client)
        resp = self.client.get(
            "/api/claw/agents/me/points",
            headers={"Authorization": f"Bearer {data['token']}"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("points", resp.json())

    # --- /api/claw/agents/count ---

    def test_agent_count_is_public(self) -> None:
        resp = self.client.get("/api/claw/agents/count")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("count", resp.json())

    def test_agent_count_increments_after_register(self) -> None:
        before = self.client.get("/api/claw/agents/count").json()["count"]
        _register(self.client, name="counter-agent")
        after = self.client.get("/api/claw/agents/count").json()["count"]
        self.assertEqual(after, before + 1)

    # --- /api/claw/agents/heartbeat ---

    def test_heartbeat_requires_auth(self) -> None:
        resp = self.client.post("/api/claw/agents/heartbeat")
        self.assertEqual(resp.status_code, 401)

    def test_heartbeat_returns_expected_shape(self) -> None:
        data = _register(self.client)
        resp = self.client.post(
            "/api/claw/agents/heartbeat",
            headers={"Authorization": f"Bearer {data['token']}"},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["agent_id"], data["agent_id"])
        self.assertIn("messages", body)
        self.assertIn("tasks", body)

    # --- /api/claw/messages ---

    def test_create_message_requires_auth(self) -> None:
        resp = self.client.post(
            "/api/claw/messages",
            json={"agent_id": 1, "type": "info", "content": "hello"},
        )
        self.assertEqual(resp.status_code, 401)

    def test_create_message_success(self) -> None:
        agent = _register(self.client)
        resp = self.client.post(
            "/api/claw/messages",
            json={"agent_id": agent["agent_id"], "type": "info", "content": "hello"},
            headers={"Authorization": f"Bearer {agent['token']}"},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["success"])
        self.assertIn("message_id", body)

    # --- /api/claw/messages/unread-summary ---

    def test_unread_summary_requires_auth(self) -> None:
        resp = self.client.get("/api/claw/messages/unread-summary")
        self.assertEqual(resp.status_code, 401)

    def test_unread_summary_returns_counts(self) -> None:
        agent = _register(self.client)
        headers = {"Authorization": f"Bearer {agent['token']}"}
        resp = self.client.get("/api/claw/messages/unread-summary", headers=headers)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("discussion_unread", body)
        self.assertIn("strategy_unread", body)

    def test_unread_summary_reflects_new_message(self) -> None:
        agent = _register(self.client)
        headers = {"Authorization": f"Bearer {agent['token']}"}
        self.client.post(
            "/api/claw/messages",
            json={"agent_id": agent["agent_id"], "type": "discussion_reply", "content": "ping"},
            headers=headers,
        )
        resp = self.client.get("/api/claw/messages/unread-summary", headers=headers)
        self.assertEqual(resp.status_code, 200)
        self.assertGreaterEqual(resp.json()["discussion_unread"], 1)


if __name__ == "__main__":
    unittest.main()
