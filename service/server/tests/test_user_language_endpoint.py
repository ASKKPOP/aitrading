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


def _send_code(client: TestClient, email: str) -> None:
    with patch("secrets.randbelow", return_value=_FIXED_CODE):
        resp = client.post("/api/users/send-code", json={"email": email})
    assert resp.status_code == 200, resp.text


def _register_user(client: TestClient, email: str, password: str = "hunter2") -> dict:
    _send_code(client, email)
    resp = client.post(
        "/api/users/register",
        json={"email": email, "code": _FIXED_CODE_STR, "password": password},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


class UserLanguageEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_put_language_updates_and_login_echoes(self) -> None:
        user = _register_user(self.client, "l2@example.com")
        token = user["token"]

        resp = self.client.put(
            "/api/users/language",
            headers={"Authorization": f"Bearer {token}"},
            json={"lang": "ja"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["lang"], "ja")

        me = self.client.get("/api/users/me", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["lang"], "ja")

        login = self.client.post(
            "/api/users/login",
            json={"email": "l2@example.com", "password": "hunter2"},
        )
        self.assertEqual(login.status_code, 200)
        self.assertEqual(login.json()["lang"], "ja")

    def test_put_language_rejects_unknown(self) -> None:
        user = _register_user(self.client, "l3@example.com")
        token = user["token"]

        resp = self.client.put(
            "/api/users/language",
            headers={"Authorization": f"Bearer {token}"},
            json={"lang": "xx"},
        )
        # Unknown normalizes to 'en' — never a 500.
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["lang"], "en")

    def test_put_language_requires_auth(self) -> None:
        resp = self.client.put("/api/users/language", json={"lang": "ja"})
        self.assertEqual(resp.status_code, 401)


if __name__ == "__main__":
    unittest.main()
