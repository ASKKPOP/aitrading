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


class PasswordResetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())

    def tearDown(self) -> None:
        self.tmp.cleanup()

    _NEW_PASSWORD = "brand-new-pass"

    def _forgot(self, email: str = _EMAIL) -> None:
        with patch("secrets.randbelow", return_value=_FIXED_CODE):
            resp = self.client.post("/api/users/forgot-password", json={"email": email})
        assert resp.status_code == 200, resp.text

    # --- /api/users/forgot-password ---

    def test_forgot_password_unknown_email_still_succeeds(self) -> None:
        resp = self.client.post(
            "/api/users/forgot-password", json={"email": "nobody@example.com"}
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json().get("success"))

    def test_forgot_password_cooldown_same_for_unknown_email(self) -> None:
        # The cooldown 429 must not reveal whether the email is registered.
        self.client.post("/api/users/forgot-password", json={"email": "nobody@example.com"})
        resp = self.client.post("/api/users/forgot-password", json={"email": "nobody@example.com"})
        self.assertEqual(resp.status_code, 429)

    def test_forgot_password_cooldown_enforced(self) -> None:
        _register_user(self.client)
        self.client.post("/api/users/forgot-password", json={"email": _EMAIL})
        resp = self.client.post("/api/users/forgot-password", json={"email": _EMAIL})
        self.assertEqual(resp.status_code, 429)

    # --- /api/users/reset-password ---

    def test_reset_password_success_and_login(self) -> None:
        _register_user(self.client)
        self._forgot()
        resp = self.client.post(
            "/api/users/reset-password",
            json={"email": _EMAIL, "code": _FIXED_CODE_STR, "new_password": self._NEW_PASSWORD},
        )
        self.assertEqual(resp.status_code, 200, resp.text)

        # Old password no longer works; new one does.
        old = self.client.post("/api/users/login", json={"email": _EMAIL, "password": _PASSWORD})
        self.assertEqual(old.status_code, 401)
        new = self.client.post(
            "/api/users/login", json={"email": _EMAIL, "password": self._NEW_PASSWORD}
        )
        self.assertEqual(new.status_code, 200, new.text)

    def test_reset_password_invalidates_existing_sessions(self) -> None:
        user = _register_user(self.client)
        self._forgot()
        resp = self.client.post(
            "/api/users/reset-password",
            json={"email": _EMAIL, "code": _FIXED_CODE_STR, "new_password": self._NEW_PASSWORD},
        )
        self.assertEqual(resp.status_code, 200)
        me = self.client.get(
            "/api/users/me", headers={"Authorization": f"Bearer {user['token']}"}
        )
        self.assertEqual(me.status_code, 401)

    def test_reset_password_wrong_code_rejected(self) -> None:
        _register_user(self.client)
        self._forgot()
        resp = self.client.post(
            "/api/users/reset-password",
            json={"email": _EMAIL, "code": "000000", "new_password": self._NEW_PASSWORD},
        )
        self.assertEqual(resp.status_code, 400)

    def test_reset_password_without_code_rejected(self) -> None:
        _register_user(self.client)
        resp = self.client.post(
            "/api/users/reset-password",
            json={"email": _EMAIL, "code": _FIXED_CODE_STR, "new_password": self._NEW_PASSWORD},
        )
        self.assertEqual(resp.status_code, 400)

    def test_reset_password_short_password_rejected(self) -> None:
        _register_user(self.client)
        self._forgot()
        resp = self.client.post(
            "/api/users/reset-password",
            json={"email": _EMAIL, "code": _FIXED_CODE_STR, "new_password": "short"},
        )
        self.assertEqual(resp.status_code, 422)

    def test_signup_code_cannot_reset_password(self) -> None:
        # A registration code lives in a different namespace than reset codes.
        _register_user(self.client)
        _send_code(self.client)  # registration-namespace code
        resp = self.client.post(
            "/api/users/reset-password",
            json={"email": _EMAIL, "code": _FIXED_CODE_STR, "new_password": self._NEW_PASSWORD},
        )
        self.assertEqual(resp.status_code, 400)

    def test_reset_password_unknown_email_rejected_generically(self) -> None:
        # No account: the code was stored but never delivered; even with the
        # right code the reset must fail with the generic 'Invalid code'.
        self._forgot("nobody@example.com")
        resp = self.client.post(
            "/api/users/reset-password",
            json={"email": "nobody@example.com", "code": _FIXED_CODE_STR,
                  "new_password": self._NEW_PASSWORD},
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["detail"], "Invalid code")

    def test_reset_password_attempts_capped(self) -> None:
        _register_user(self.client)
        self._forgot()
        for _ in range(5):  # MAX_CODE_ATTEMPTS wrong tries
            resp = self.client.post(
                "/api/users/reset-password",
                json={"email": _EMAIL, "code": "000000", "new_password": self._NEW_PASSWORD},
            )
            self.assertEqual(resp.status_code, 400)
        resp = self.client.post(
            "/api/users/reset-password",
            json={"email": _EMAIL, "code": _FIXED_CODE_STR, "new_password": self._NEW_PASSWORD},
        )
        self.assertEqual(resp.status_code, 429)


if __name__ == "__main__":
    unittest.main()
