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
from utils import hash_password


def _raw_token_in_db(agent_id: int) -> str | None:
    """Read agents.token column directly — should always be NULL after the fix."""
    conn = database.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT token FROM agents WHERE id = ?", (agent_id,))
    row = cursor.fetchone()
    conn.close()
    return row["token"] if row else None


class AgentTokenPlaintextStorageTests(unittest.TestCase):
    """Verify that plaintext tokens are never stored in agents.token after security fix."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_registration_does_not_store_plaintext_token(self) -> None:
        resp = self.client.post(
            "/api/claw/agents/selfRegister",
            json={"name": "secure-reg", "password": "pw123"},
        )
        self.assertEqual(resp.status_code, 200)
        agent_id = resp.json()["agent_id"]
        self.assertIsNone(_raw_token_in_db(agent_id))

    def test_login_does_not_store_plaintext_token(self) -> None:
        self.client.post(
            "/api/claw/agents/selfRegister",
            json={"name": "secure-login", "password": "pw123"},
        )
        login_resp = self.client.post(
            "/api/claw/agents/login",
            json={"name": "secure-login", "password": "pw123"},
        )
        self.assertEqual(login_resp.status_code, 200)
        agent_id = login_resp.json()["agent_id"]
        self.assertIsNone(_raw_token_in_db(agent_id))

    def test_returned_token_authenticates_successfully(self) -> None:
        resp = self.client.post(
            "/api/claw/agents/selfRegister",
            json={"name": "auth-test", "password": "pw123"},
        )
        token = resp.json()["token"]
        me = self.client.get(
            "/api/claw/agents/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(me.status_code, 200)

    def test_login_rotates_token(self) -> None:
        """Each login issues a fresh token — old token stops working."""
        reg = self.client.post(
            "/api/claw/agents/selfRegister",
            json={"name": "rotate-test", "password": "pw123"},
        )
        old_token = reg.json()["token"]

        login = self.client.post(
            "/api/claw/agents/login",
            json={"name": "rotate-test", "password": "pw123"},
        )
        new_token = login.json()["token"]

        self.assertNotEqual(old_token, new_token)
        # New token works.
        me = self.client.get("/api/claw/agents/me", headers={"Authorization": f"Bearer {new_token}"})
        self.assertEqual(me.status_code, 200)
        # Old token is invalidated.
        old_me = self.client.get("/api/claw/agents/me", headers={"Authorization": f"Bearer {old_token}"})
        self.assertEqual(old_me.status_code, 401)


class AgentLoginTokenStabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_agent_login_returns_valid_token(self) -> None:
        """Login always returns a usable token (rotation is expected)."""
        self.client.post(
            "/api/claw/agents/selfRegister",
            json={"name": "stable-agent", "password": "password123"},
        )
        login = self.client.post(
            "/api/claw/agents/login",
            json={"name": "stable-agent", "password": "password123"},
        )
        self.assertEqual(login.status_code, 200, login.text)
        token = login.json()["token"]
        self.assertTrue(token)

        me = self.client.get(
            "/api/claw/agents/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(me.status_code, 200, me.text)

    def test_agent_login_issues_token_for_agents_without_hash(self) -> None:
        """Agent with no token_hash gets a fresh token on login."""
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO agents (name, password_hash, token, cash)
            VALUES (?, ?, NULL, 100000.0)
            """,
            ("no-hash-agent", hash_password("password123")),
        )
        conn.commit()
        conn.close()

        login = self.client.post(
            "/api/claw/agents/login",
            json={"name": "no-hash-agent", "password": "password123"},
        )
        self.assertEqual(login.status_code, 200, login.text)
        self.assertTrue(login.json()["token"])

    def test_new_registration_normalizes_agent_name(self) -> None:
        response = self.client.post(
            "/api/claw/agents/selfRegister",
            json={"name": "  normalized-agent  ", "password": "password123"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["name"], "normalized-agent")

        login = self.client.post(
            "/api/claw/agents/login",
            json={"name": "normalized-agent", "password": "password123"},
        )
        self.assertEqual(login.status_code, 200, login.text)

    def test_registration_rejects_normalized_duplicate_of_legacy_spaced_name(self) -> None:
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO agents (name, password_hash, token, cash)
            VALUES (?, ?, NULL, 100000.0)
            """,
            (" legacy-duplicate ", hash_password("password123")),
        )
        conn.commit()
        conn.close()

        response = self.client.post(
            "/api/claw/agents/selfRegister",
            json={"name": "legacy-duplicate", "password": "password123"},
        )

        self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(response.json()["detail"], "Agent name already exists")

    def test_legacy_agent_name_with_spaces_can_login_with_exact_name(self) -> None:
        """Agent with spaced name can login with exact name; token is issued fresh."""
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO agents (name, password_hash, token, cash)
            VALUES (?, ?, NULL, 100000.0)
            """,
            (" legacy-spaced ", hash_password("password123")),
        )
        conn.commit()
        conn.close()

        exact_login = self.client.post(
            "/api/claw/agents/login",
            json={"name": " legacy-spaced ", "password": "password123"},
        )
        trimmed_login = self.client.post(
            "/api/claw/agents/login",
            json={"name": "legacy-spaced", "password": "password123"},
        )

        self.assertEqual(exact_login.status_code, 200, exact_login.text)
        self.assertTrue(exact_login.json()["token"])  # fresh token issued
        self.assertEqual(trimmed_login.status_code, 401, trimmed_login.text)


if __name__ == "__main__":
    unittest.main()
