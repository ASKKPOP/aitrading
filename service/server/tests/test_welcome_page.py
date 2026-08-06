"""First-run /welcome page backend: the dismissal flag.

The page itself is frontend; what the backend owns is one column
(users.welcome_dismissed_at), one endpoint (POST /api/users/welcome/dismiss)
and one field on /users/me (welcome_dismissed). The endpoint is two-way — the
checkbox on the page can re-enable the welcome page, so {dismissed: false}
must clear the stamp, not be ignored.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database  # noqa: E402
from routes import create_app  # noqa: E402


def _mk_user_with_token(email="welcome@t.dev") -> tuple[int, str]:
    conn = database.get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("INSERT INTO users (email, password_hash, lang) VALUES (?, 'x', 'en')",
                    (email,))
        uid = int(cur.lastrowid)
        token = f"tok-{uid}-welcome"
        expires = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("INSERT INTO user_tokens (user_id, token, expires_at) VALUES (?, ?, ?)",
                    (uid, token, expires))
        conn.commit()
        return uid, token
    finally:
        conn.close()


def _column(uid: int) -> str | None:
    conn = database.get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT welcome_dismissed_at FROM users WHERE id = ?", (uid,))
        return dict(cur.fetchone())["welcome_dismissed_at"]
    finally:
        conn.close()


class WelcomeDismissTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())
        self.uid, token = _mk_user_with_token()
        self.auth = {"Authorization": f"Bearer {token}"}

    def tearDown(self):
        self.tmp.cleanup()

    def _me(self) -> dict:
        r = self.client.get("/api/users/me", headers=self.auth)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def test_dismiss_requires_auth(self):
        r = self.client.post("/api/users/welcome/dismiss", json={})
        self.assertEqual(r.status_code, 401)

    def test_fresh_member_is_not_dismissed(self):
        me = self._me()
        self.assertIn("welcome_dismissed", me)
        self.assertFalse(me["welcome_dismissed"])

    def test_dismiss_stamps_the_column_and_me_reflects_it(self):
        r = self.client.post("/api/users/welcome/dismiss", json={}, headers=self.auth)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json()["welcome_dismissed"])
        self.assertIsNotNone(_column(self.uid))
        self.assertTrue(self._me()["welcome_dismissed"])

    def test_dismiss_is_idempotent(self):
        for _ in range(2):
            r = self.client.post("/api/users/welcome/dismiss", json={"dismissed": True},
                                 headers=self.auth)
            self.assertEqual(r.status_code, 200, r.text)
            self.assertTrue(r.json()["welcome_dismissed"])
        self.assertTrue(self._me()["welcome_dismissed"])

    def test_unticking_the_checkbox_clears_the_stamp(self):
        self.client.post("/api/users/welcome/dismiss", json={}, headers=self.auth)
        r = self.client.post("/api/users/welcome/dismiss", json={"dismissed": False},
                             headers=self.auth)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertFalse(r.json()["welcome_dismissed"])
        self.assertIsNone(_column(self.uid))
        self.assertFalse(self._me()["welcome_dismissed"])


if __name__ == "__main__":
    unittest.main()
