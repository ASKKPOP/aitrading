"""users.lang is set in the Google OAuth signup path (Task A6)."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
from database import get_db_connection
from routes_oauth import _find_or_create_user_from_google


class OAuthLangTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_new_user_gets_passed_lang(self) -> None:
        _find_or_create_user_from_google({"sub": "g123", "email": "oauthko@example.com"}, lang="ko")

        conn = get_db_connection()
        row = conn.execute("SELECT lang FROM users WHERE email = ?", ("oauthko@example.com",)).fetchone()
        conn.close()
        self.assertEqual(row["lang"], "ko")

    def test_existing_email_user_lang_not_overwritten(self) -> None:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO users (email, password_hash, points, lang) VALUES (?, ?, 0, ?)",
            ("existing@example.com", "hash", "ja"),
        )
        conn.commit()
        conn.close()

        _find_or_create_user_from_google({"sub": "g456", "email": "existing@example.com"}, lang="ko")

        conn = get_db_connection()
        row = conn.execute("SELECT lang FROM users WHERE email = ?", ("existing@example.com",)).fetchone()
        conn.close()
        self.assertEqual(row["lang"], "ja")


if __name__ == "__main__":
    unittest.main()
