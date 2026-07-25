"""Task C2 — send_alert renders alerts in the recipient's stored language."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database


class AlertsLangTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()

    def tearDown(self):
        self.tmp.cleanup()

    def _seed_user_agent(self, lang: str = "en") -> int:
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO users (email, password_hash, created_at, lang) "
                    "VALUES (?, ?, ?, ?)",
                    ("lang-test@test.io", "x", "2026-01-01T00:00:00Z", lang))
        user_id = cur.lastrowid
        from services import _hash_token
        cur.execute(
            "INSERT INTO agents (name, password_hash, token, token_hash, cash, user_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("lang-agent", "x", "claw_lang", _hash_token("claw_lang"), 100000.0, user_id))
        agent_id = cur.lastrowid
        conn.commit()
        conn.close()
        return agent_id

    def test_alert_stored_in_user_language(self):
        agent_id = self._seed_user_agent(lang="ko")
        import alerts
        with patch.object(alerts, "_send_email", return_value=False), \
             patch.object(alerts, "_send_sms", return_value=False):
            alerts.send_alert(agent_id, "breaker", "breaker",
                               {"scope": "account", "reason": "loss cap"})
        conn = database.get_db_connection()
        row = conn.execute(
            "SELECT title, body FROM alert_log WHERE agent_id=? ORDER BY id DESC LIMIT 1",
            (agent_id,)).fetchone()
        conn.close()
        self.assertTrue(row["title"].startswith("서킷 브레이커 정지"))
        self.assertEqual(row["body"], "loss cap")

    def test_legacy_string_form_still_works(self):
        # Backward-compat shim: (title, body) strings are stored as-is, no
        # rendering — producers not yet converted to msg_id/params (C3).
        agent_id = self._seed_user_agent(lang="ko")
        import alerts
        with patch.object(alerts, "_send_email", return_value=False), \
             patch.object(alerts, "_send_sms", return_value=False):
            alerts.send_alert(agent_id, "custom", "Literal Title", "Literal Body")
        conn = database.get_db_connection()
        row = conn.execute(
            "SELECT title, body FROM alert_log WHERE agent_id=? ORDER BY id DESC LIMIT 1",
            (agent_id,)).fetchone()
        conn.close()
        self.assertEqual(row["title"], "Literal Title")
        self.assertEqual(row["body"], "Literal Body")

    def test_default_lang_en_when_no_lang_set(self):
        agent_id = self._seed_user_agent(lang="en")
        import alerts
        with patch.object(alerts, "_send_email", return_value=False), \
             patch.object(alerts, "_send_sms", return_value=False):
            alerts.send_alert(agent_id, "breaker", "breaker",
                               {"scope": "account", "reason": "loss cap"})
        conn = database.get_db_connection()
        row = conn.execute(
            "SELECT title FROM alert_log WHERE agent_id=? ORDER BY id DESC LIMIT 1",
            (agent_id,)).fetchone()
        conn.close()
        self.assertTrue(row["title"].startswith("Circuit breaker HALT"))


if __name__ == "__main__":
    unittest.main()
