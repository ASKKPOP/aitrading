"""Plan 21 P4 — daily desk brief + monthly process review.

Send-once markers, recipient targeting (active-run owners only), localized
rendering with graceful missing-data placeholders, and the monthly admin
review with its candidate-skill-drafts section.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
import desk_brief
from notifications_i18n import render
from routes import create_app


def _at(hour: int, day: int = 15) -> datetime:
    return datetime(2026, 8, day, hour, 30, tzinfo=timezone.utc)


class _Db(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()

    def tearDown(self):
        self.tmp.cleanup()

    def _user_with_active_run(self) -> int:
        """A registered user whose agent owns one active run."""
        client = TestClient(create_app())
        resp = client.post(
            "/api/claw/agents/selfRegister",
            json={"name": "brief-agent", "password": "pw123",
                  "initial_balance": 10000.0})
        assert resp.status_code == 200, resp.text
        agent_id = resp.json()["agent_id"]
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            database.begin_write_transaction(cur)
            cur.execute("UPDATE agents SET user_id = 77 WHERE id = ?", (agent_id,))
            cur.execute(
                """INSERT INTO trading_runs
                   (agent_id, symbol, market, status, config_snapshot_json,
                    created_at)
                   VALUES (?, 'BTC', 'crypto', 'active', '{}',
                           '2026-08-01T00:00:00Z')""", (agent_id,))
            conn.commit()
        finally:
            conn.close()
        return 77


class DailyBriefTests(_Db):
    def test_not_due_before_hour(self):
        with patch.dict(os.environ, {"DESK_BRIEF_UTC_HOUR": "21"}):
            self.assertEqual(desk_brief.send_daily_briefs(_at(20)), 0)

    def test_sends_once_to_active_run_owner(self):
        uid = self._user_with_active_run()
        sent_to = []
        with patch.dict(os.environ, {"DESK_BRIEF_UTC_HOUR": "21"}), \
             patch("notifications.notify_i18n",
                   side_effect=lambda u, *a, **k: sent_to.append(u) or {}), \
             patch.object(desk_brief, "gather_market_context",
                          return_value={"score": 61.0, "zone": "NEUTRAL",
                                        "regime": "trend", "fng": 55,
                                        "hot24": 2}):
            first = desk_brief.send_daily_briefs(_at(22))
            second = desk_brief.send_daily_briefs(_at(23))
        self.assertEqual(first, 1)
        self.assertEqual(sent_to, [uid])
        self.assertEqual(second, 0, "marker must prevent a same-day resend")

    def test_no_recipients_without_active_runs(self):
        with patch.dict(os.environ, {"DESK_BRIEF_UTC_HOUR": "0"}), \
             patch.object(desk_brief, "gather_market_context",
                          return_value={"score": None, "zone": None,
                                        "regime": None, "fng": None,
                                        "hot24": 0}):
            self.assertEqual(desk_brief.send_daily_briefs(_at(1)), 0)

    def test_catalogue_renders_all_langs(self):
        params = {"score": 61.0, "zone": "NEUTRAL", "regime": "trend",
                  "fng": 55, "hot24": 2, "active_runs": 3, "decisions24": 40}
        for lang in ("en", "ko", "ja", "th", "vi", "id"):
            title, body = render("desk_brief_daily", lang, **params)
            self.assertNotIn("{", title, f"unrendered param in {lang} title")
            self.assertNotIn("{", body, f"unrendered param in {lang} body")
            self.assertIn("61.0", body)

    def test_missing_data_renders_placeholders(self):
        title, body = render("desk_brief_daily", "en", score="—", zone="—",
                             regime="—", fng="—", hot24=0, active_runs=1,
                             decisions24=0)
        self.assertIn("—/100", body)


class MonthlyReviewTests(_Db):
    def test_only_on_the_first(self):
        with patch("admin_alerts.notify_admins") as mock_notify:
            self.assertFalse(desk_brief.send_monthly_review(_at(10, day=15)))
        mock_notify.assert_not_called()

    def test_sends_once_with_skill_drafts_section(self):
        captured = {}

        def fake_notify(subject, body):
            captured["subject"] = subject
            captured["body"] = body
            return {"email": []}

        with patch("admin_alerts.notify_admins", side_effect=fake_notify):
            first = desk_brief.send_monthly_review(_at(10, day=1))
            second = desk_brief.send_monthly_review(_at(11, day=1))
        self.assertTrue(first)
        self.assertFalse(second, "month marker must prevent a resend")
        self.assertIn("process review", captured["subject"].lower())
        self.assertIn("Candidate skill drafts", captured["body"])
        self.assertIn("BASE_SKILLS", captured["body"])

    def test_tick_is_fail_soft(self):
        with patch.object(desk_brief, "send_daily_briefs",
                          side_effect=RuntimeError("boom")), \
             patch.object(desk_brief, "send_monthly_review",
                          side_effect=RuntimeError("boom")):
            out = desk_brief.desk_brief_tick(_at(22))
        self.assertTrue(out["enabled"])

    def test_disabled_kill_switch(self):
        with patch.dict(os.environ, {"DESK_BRIEF_ENABLED": "false"}):
            self.assertEqual(desk_brief.desk_brief_tick(_at(22)),
                             {"enabled": False})


if __name__ == "__main__":
    unittest.main()
