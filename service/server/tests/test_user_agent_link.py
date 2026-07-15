"""POST /api/users/agent — auto-provisioned agent linked to a human user."""

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
from routes import create_app


_FIXED_CODE = 42000
_FIXED_CODE_STR = f"{_FIXED_CODE:06d}"


class UserAgentLinkTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _register_user(self, email: str) -> str:
        with patch("secrets.randbelow", return_value=_FIXED_CODE):
            self.client.post("/api/users/send-code", json={"email": email})
        resp = self.client.post(
            "/api/users/register",
            json={"email": email, "code": _FIXED_CODE_STR, "password": "hunter2"},
        )
        assert resp.status_code == 200, resp.text
        return resp.json()["token"]

    def test_requires_auth(self) -> None:
        resp = self.client.post("/api/users/agent")
        self.assertEqual(resp.status_code, 401)

    def test_creates_agent_on_first_call(self) -> None:
        token = self._register_user("trader.one@example.com")
        resp = self.client.post("/api/users/agent", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["created"])
        self.assertEqual(data["name"], "traderone")
        self.assertTrue(data["token"])

        # the returned claw token actually works against an agent endpoint
        me = self.client.get(
            "/api/claw/agents/me", headers={"Authorization": f"Bearer {data['token']}"}
        )
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["name"], "traderone")
        self.assertEqual(float(me.json()["cash"]), 100000.0)

    def test_second_call_reuses_agent(self) -> None:
        token = self._register_user("reuse@example.com")
        first = self.client.post("/api/users/agent", headers={"Authorization": f"Bearer {token}"}).json()
        second = self.client.post("/api/users/agent", headers={"Authorization": f"Bearer {token}"}).json()
        self.assertTrue(first["created"])
        self.assertFalse(second["created"])
        self.assertEqual(first["agent_id"], second["agent_id"])

    def test_name_collision_gets_suffix(self) -> None:
        # occupy the name 'dup' with a standalone agent
        resp = self.client.post(
            "/api/claw/agents/selfRegister",
            json={"name": "dup", "password": "pw", "initial_balance": 1000.0},
        )
        assert resp.status_code == 200, resp.text
        token = self._register_user("dup@example.com")
        data = self.client.post("/api/users/agent", headers={"Authorization": f"Bearer {token}"}).json()
        self.assertEqual(data["name"], "dup-2")

    def test_agents_isolated_per_user(self) -> None:
        t1 = self._register_user("a@example.com")
        t2 = self._register_user("b@example.com")
        a1 = self.client.post("/api/users/agent", headers={"Authorization": f"Bearer {t1}"}).json()
        a2 = self.client.post("/api/users/agent", headers={"Authorization": f"Bearer {t2}"}).json()
        self.assertNotEqual(a1["agent_id"], a2["agent_id"])


if __name__ == "__main__":
    unittest.main()
