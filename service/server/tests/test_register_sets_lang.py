"""users.lang is set at registration from resolve_signup_lang (Task A3)."""
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
import signup_lang
from database import get_db_connection
from routes import create_app


_FIXED_CODE = 42000  # secrets.randbelow returns this → code "042000"
_FIXED_CODE_STR = f"{_FIXED_CODE:06d}"
_EMAIL = "lang@example.com"
_PASSWORD = "hunter2222"


class RegisterSetsLangTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_register_persists_language_from_geo_country(self) -> None:
        with patch.object(signup_lang, "_geo_country", return_value="KR"):
            with patch("secrets.randbelow", return_value=_FIXED_CODE):
                resp = self.client.post("/api/users/send-code", json={"email": _EMAIL})
            self.assertEqual(resp.status_code, 200, resp.text)

            resp = self.client.post(
                "/api/users/register",
                json={"email": _EMAIL, "code": _FIXED_CODE_STR, "password": _PASSWORD},
            )
        self.assertEqual(resp.status_code, 200, resp.text)

        conn = get_db_connection()
        row = conn.execute("SELECT lang FROM users WHERE email = ?", (_EMAIL,)).fetchone()
        conn.close()
        self.assertEqual(row["lang"], "ko")

    def test_register_defaults_to_en_without_geo_match(self) -> None:
        with patch.object(signup_lang, "_geo_country", return_value=None):
            with patch("secrets.randbelow", return_value=_FIXED_CODE):
                resp = self.client.post("/api/users/send-code", json={"email": _EMAIL})
            self.assertEqual(resp.status_code, 200, resp.text)

            resp = self.client.post(
                "/api/users/register",
                json={"email": _EMAIL, "code": _FIXED_CODE_STR, "password": _PASSWORD},
            )
        self.assertEqual(resp.status_code, 200, resp.text)

        conn = get_db_connection()
        row = conn.execute("SELECT lang FROM users WHERE email = ?", (_EMAIL,)).fetchone()
        conn.close()
        self.assertEqual(row["lang"], "en")


if __name__ == "__main__":
    unittest.main()
