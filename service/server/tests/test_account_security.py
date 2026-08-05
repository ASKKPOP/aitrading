"""Account security (sub-project B) — phone verification, SMS password reset,
signup language choice, welcome email.

Spec: docs/superpowers/specs/2026-08-05-account-security-design.md
All external delivery (Twilio SMS, Resend/SendGrid email) is mocked.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database


class PhoneSchemaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()

    def tearDown(self):
        self.tmp.cleanup()

    def test_phone_columns_exist(self):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("PRAGMA table_info(users)")
            cols = {r["name"] for r in cur.fetchall()}
        finally:
            conn.close()
        self.assertLessEqual({"phone", "phone_verified_at"}, cols)

    def test_phone_unique(self):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("INSERT INTO users (email, password_hash, phone) "
                        "VALUES ('a@t.dev', 'x', '+12025550001')")
            with self.assertRaises(Exception):
                cur.execute("INSERT INTO users (email, password_hash, phone) "
                            "VALUES ('b@t.dev', 'x', '+12025550001')")
            conn.rollback()
            # many NULL phones are fine
            cur.execute("INSERT INTO users (email, password_hash) VALUES ('c@t.dev', 'x')")
            cur.execute("INSERT INTO users (email, password_hash) VALUES ('d@t.dev', 'x')")
            conn.commit()
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
