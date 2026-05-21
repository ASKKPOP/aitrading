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


_FIXED_CODE = 42000  # secrets.randbelow returns this → code "042000"
_FIXED_CODE_STR = f"{_FIXED_CODE:06d}"
_EMAIL = "test@example.com"
_PASSWORD = "hunter2"


def _register_agent(client: TestClient, name: str = "ag1", password: str = "pw") -> dict:
    resp = client.post(
        "/api/claw/agents/selfRegister",
        json={"name": name, "password": password, "initial_balance": 100000.0},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _send_code(client: TestClient, email: str = _EMAIL) -> None:
    with patch("secrets.randbelow", return_value=_FIXED_CODE):
        resp = client.post("/api/users/send-code", json={"email": email})
    assert resp.status_code == 200, resp.text


def _register_user(
    client: TestClient,
    email: str = _EMAIL,
    password: str = _PASSWORD,
    code: str = _FIXED_CODE_STR,
) -> dict:
    _send_code(client, email)
    resp = client.post(
        "/api/users/register",
        json={"email": email, "code": code, "password": password},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


class UserRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())

    def tearDown(self) -> None:
        self.tmp.cleanup()

    # --- /api/users/send-code ---

    def test_send_code_success(self) -> None:
        resp = self.client.post("/api/users/send-code", json={"email": _EMAIL})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json().get("success"))

    def test_send_code_cooldown_enforced(self) -> None:
        self.client.post("/api/users/send-code", json={"email": _EMAIL})
        resp = self.client.post("/api/users/send-code", json={"email": _EMAIL})
        self.assertEqual(resp.status_code, 429)

    def test_send_code_invalid_email_rejected(self) -> None:
        resp = self.client.post("/api/users/send-code", json={"email": "not-an-email"})
        self.assertEqual(resp.status_code, 422)

    # --- /api/users/register ---

    def test_register_success(self) -> None:
        data = _register_user(self.client)
        self.assertIn("token", data)
        self.assertIn("user_id", data)

    def test_register_wrong_code_rejected(self) -> None:
        _send_code(self.client)
        resp = self.client.post(
            "/api/users/register",
            json={"email": _EMAIL, "code": "000000", "password": _PASSWORD},
        )
        self.assertEqual(resp.status_code, 400)

    def test_register_without_sending_code_rejected(self) -> None:
        resp = self.client.post(
            "/api/users/register",
            json={"email": _EMAIL, "code": _FIXED_CODE_STR, "password": _PASSWORD},
        )
        self.assertEqual(resp.status_code, 400)

    def test_register_duplicate_email_rejected(self) -> None:
        _register_user(self.client)
        # Need a fresh code for the second attempt
        _send_code(self.client, "test@example.com")
        resp = self.client.post(
            "/api/users/register",
            json={"email": _EMAIL, "code": _FIXED_CODE_STR, "password": "other"},
        )
        self.assertEqual(resp.status_code, 400)

    # --- /api/users/login ---

    def test_login_success(self) -> None:
        _register_user(self.client)
        resp = self.client.post(
            "/api/users/login",
            json={"email": _EMAIL, "password": _PASSWORD},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("token", body)
        self.assertEqual(body["email"], _EMAIL)

    def test_login_wrong_password_rejected(self) -> None:
        _register_user(self.client)
        resp = self.client.post(
            "/api/users/login",
            json={"email": _EMAIL, "password": "wrong"},
        )
        self.assertEqual(resp.status_code, 401)

    def test_login_unknown_email_rejected(self) -> None:
        resp = self.client.post(
            "/api/users/login",
            json={"email": "nobody@example.com", "password": _PASSWORD},
        )
        self.assertEqual(resp.status_code, 401)

    # --- /api/users/me ---

    def test_get_me_requires_auth(self) -> None:
        resp = self.client.get("/api/users/me")
        self.assertEqual(resp.status_code, 401)

    def test_get_me_success(self) -> None:
        user = _register_user(self.client)
        resp = self.client.get(
            "/api/users/me",
            headers={"Authorization": f"Bearer {user['token']}"},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["id"], user["user_id"])
        self.assertEqual(body["email"], _EMAIL)

    def test_get_me_invalid_token_rejected(self) -> None:
        resp = self.client.get(
            "/api/users/me",
            headers={"Authorization": "Bearer bogus"},
        )
        self.assertEqual(resp.status_code, 401)

    # --- /api/users/points ---

    def test_get_points_requires_auth(self) -> None:
        resp = self.client.get("/api/users/points")
        self.assertEqual(resp.status_code, 401)

    def test_get_points_success(self) -> None:
        user = _register_user(self.client)
        resp = self.client.get(
            "/api/users/points",
            headers={"Authorization": f"Bearer {user['token']}"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("points", resp.json())


if __name__ == "__main__":
    unittest.main()
