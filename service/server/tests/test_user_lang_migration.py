"""users.lang column exists after init_database() (SQLite mirror of alembic 0031)."""
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
from database import get_db_connection


class TestUserLangMigration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()

    def tearDown(self):
        self.tmp.cleanup()

    def test_users_has_lang_column(self):
        conn = get_db_connection()
        cols = {r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()}
        conn.close()
        assert "lang" in cols


if __name__ == "__main__":
    unittest.main()
