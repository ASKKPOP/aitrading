"""Rich alert emails (2026-07-31) — catalogue parity, builders, and the
send_alert email path (extended plain text + branded HTML)."""

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

LANGS = ('en', 'ko', 'ja', 'th', 'vi', 'id')


class CatalogueParityTestCase(unittest.TestCase):
    """Every explanation/glossary/label entry must exist in all 6 languages —
    a missing language silently falls back to English for that member."""

    def test_explain_parity_and_static_text(self):
        from alert_email import EXPLAIN
        self.assertTrue(EXPLAIN)
        for msg_id, variants in EXPLAIN.items():
            self.assertEqual(set(variants), set(LANGS), msg_id)
            for lang, fields in variants.items():
                self.assertEqual(set(fields), {'why', 'next', 'action'},
                                 f"{msg_id}/{lang}")
                for key, text in fields.items():
                    self.assertTrue(text and text.strip(), f"{msg_id}/{lang}/{key}")
                    # Static by design: a format brace here would raise at
                    # render time and knock the email back to the plain body.
                    self.assertNotIn('{', text, f"{msg_id}/{lang}/{key}")

    def test_glossary_parity_and_references(self):
        from alert_email import EXPLAIN, GLOSSARY, GLOSSARY_FOR
        for term_key, variants in GLOSSARY.items():
            self.assertEqual(set(variants), set(LANGS), term_key)
            for lang, (term, definition) in variants.items():
                self.assertTrue(term and definition, f"{term_key}/{lang}")
        for msg_id, term_keys in GLOSSARY_FOR.items():
            self.assertIn(msg_id, EXPLAIN, msg_id)
            for key in term_keys:
                self.assertIn(key, GLOSSARY, f"{msg_id} -> {key}")

    def test_ui_labels_parity(self):
        from alert_email import _UI
        self.assertEqual(set(_UI), set(LANGS))
        en_keys = set(_UI['en'])
        for lang, labels in _UI.items():
            self.assertEqual(set(labels), en_keys, lang)
            for key, text in labels.items():
                self.assertTrue(text and text.strip(), f"{lang}/{key}")

    def test_transactional_copy_parity(self):
        from email_i18n import _CHROME, _COPY
        self.assertEqual(set(_COPY), {'signup', 'reset'})
        for purpose, variants in _COPY.items():
            self.assertEqual(set(variants), set(LANGS), purpose)
            for lang, fields in variants.items():
                self.assertEqual(set(fields),
                                 {'subject', 'heading', 'intro', 'note'},
                                 f"{purpose}/{lang}")
        self.assertEqual(set(_CHROME), set(LANGS))


class DbTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()

    def tearDown(self):
        self.tmp.cleanup()

    def _seed_user_agent(self, lang: str = "en") -> tuple[int, int]:
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO users (email, password_hash, created_at, lang) "
                    "VALUES (?, ?, ?, ?)",
                    ("alert-email@test.io", "x", "2026-01-01T00:00:00Z", lang))
        user_id = cur.lastrowid
        from services import _hash_token
        cur.execute(
            "INSERT INTO agents (name, password_hash, token, token_hash, cash, user_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("alert-email-agent", "x", "claw_ae", _hash_token("claw_ae"),
             100000.0, user_id))
        agent_id = cur.lastrowid
        conn.commit()
        conn.close()
        return user_id, agent_id

    def _seed_running_run(self, agent_id: int) -> int:
        """A running run with one closed round trip: +$10 realized, no fees."""
        import trading_runs
        run_id = trading_runs.create_run(
            agent_id,
            {"symbol": "BTCUSDT", "market": "crypto", "market_type": "futures",
             "max_bet_usd": 100, "interval_minutes": 60, "min_confidence": 0.6},
            {"type": "immediate"}, {"max_loss_usd": 50}, True)
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE trading_runs SET status = 'running' WHERE id = ?",
                    (run_id,))
        for i, (side, price) in enumerate((("buy", 100.0), ("sell", 110.0))):
            cur.execute(
                """INSERT INTO signals (signal_id, agent_id, message_type, market,
                       symbol, side, entry_price, quantity, fee_usd, run_id,
                       timestamp, created_at)
                   VALUES (?, ?, 'operation', 'crypto', 'BTCUSDT', ?, ?, 1.0, 0,
                           ?, ?, ?)""",
                (9000 + i, agent_id, side, price, run_id, 1753900000 + i,
                 "2026-07-30T00:00:00Z"))
        conn.commit()
        conn.close()
        return run_id


class BuildAlertEmailTestCase(DbTestCase):
    def test_every_explained_msg_id_renders_in_every_language(self):
        from alert_email import (DASHBOARD_URL, EXPLAIN, _UI, build_alert_email)
        user_id, _agent_id = self._seed_user_agent()
        for msg_id in EXPLAIN:
            for lang in LANGS:
                text, html = build_alert_email(msg_id, "T title", "B body",
                                               lang, user_id)
                exp = EXPLAIN[msg_id].get(lang) or EXPLAIN[msg_id]['en']
                ui = _UI[lang]
                for fragment in (exp['why'], exp['next'], exp['action'],
                                 ui['no_runs'], DASHBOARD_URL, "B body"):
                    self.assertIn(fragment, text, f"{msg_id}/{lang}")
                self.assertIn("Sooppiy", html)
                self.assertIn("T title", html)

    def test_unknown_msg_id_still_produces_wrapped_email(self):
        from alert_email import DASHBOARD_URL, build_alert_email
        user_id, _ = self._seed_user_agent()
        text, html = build_alert_email("no_such_msg", "T", "B", "ko", user_id)
        self.assertIn("B", text)
        self.assertIn(DASHBOARD_URL, text)
        self.assertIn("Sooppiy", html)

    def test_snapshot_and_email_show_run_pnl(self):
        from alert_email import build_alert_email, run_status_snapshot
        user_id, agent_id = self._seed_user_agent(lang="ko")
        run_id = self._seed_running_run(agent_id)

        snap = run_status_snapshot(user_id)
        self.assertEqual(snap["count"], 1)
        self.assertEqual(snap["runs"][0]["id"], run_id)
        self.assertAlmostEqual(snap["total"], 10.0, places=2)

        text, html = build_alert_email("fleet_churn", "T", "B", "ko", user_id)
        self.assertIn(f"Run #{run_id} BTCUSDT", text)
        self.assertIn("$+10.00", text)
        self.assertIn("실행 중", text)   # localized run status
        self.assertIn("$+10.00", html)

    def test_snapshot_none_user_is_none(self):
        from alert_email import run_status_snapshot
        self.assertIsNone(run_status_snapshot(None))


class SendAlertEmailPathTestCase(DbTestCase):
    def test_catalogue_alert_sends_rich_email_and_journals_short_body(self):
        import alerts
        user_id, agent_id = self._seed_user_agent(lang="ko")
        captured = {}

        def fake_send(to_email, subject, body, html=None):
            captured.update(to=to_email, subject=subject, body=body, html=html)
            return True

        with patch.object(alerts, "_send_email", side_effect=fake_send), \
             patch.object(alerts, "_send_sms", return_value=False):
            out = alerts.send_alert(agent_id, "fleet_churn", "fleet_churn",
                                    {"fleet_id": 7, "n": 12})
        self.assertIn("email", out["channels"])

        from alert_email import EXPLAIN, GLOSSARY
        from notifications_i18n import render
        ko_title, ko_body = render("fleet_churn", "ko", fleet_id=7, n=12)
        # Email: short body + explanation + glossary, and a branded HTML part.
        self.assertIn(ko_body, captured["body"])
        self.assertIn(EXPLAIN["fleet_churn"]["ko"]["why"], captured["body"])
        self.assertIn(GLOSSARY["member"]["ko"][0], captured["body"])
        self.assertIsNotNone(captured["html"])
        self.assertIn("Sooppiy", captured["html"])
        # Journal: stays the short catalogue body (feed/SMS unchanged).
        conn = database.get_db_connection()
        row = conn.execute(
            "SELECT title, body FROM alert_log WHERE agent_id=? "
            "ORDER BY id DESC LIMIT 1", (agent_id,)).fetchone()
        conn.close()
        self.assertEqual((row["title"], row["body"]), (ko_title, ko_body))

    def test_legacy_string_alert_stays_plain(self):
        import alerts
        _user_id, agent_id = self._seed_user_agent()
        captured = {}

        def fake_send(to_email, subject, body, html=None):
            captured.update(body=body, html=html)
            return True

        with patch.object(alerts, "_send_email", side_effect=fake_send), \
             patch.object(alerts, "_send_sms", return_value=False):
            alerts.send_alert(agent_id, "custom", "Literal Title", "Literal Body")
        self.assertEqual(captured["body"], "Literal Body")
        self.assertIsNone(captured["html"])

    def test_build_failure_falls_back_to_plain_body(self):
        import alerts
        _user_id, agent_id = self._seed_user_agent(lang="ko")
        captured = {}

        def fake_send(to_email, subject, body, html=None):
            captured.update(body=body, html=html)
            return True

        import alert_email
        with patch.object(alerts, "_send_email", side_effect=fake_send), \
             patch.object(alerts, "_send_sms", return_value=False), \
             patch.object(alert_email, "build_alert_email",
                          side_effect=RuntimeError("boom")):
            out = alerts.send_alert(agent_id, "fleet_churn", "fleet_churn",
                                    {"fleet_id": 7, "n": 12})
        self.assertIn("email", out["channels"])
        from notifications_i18n import render
        _t, ko_body = render("fleet_churn", "ko", fleet_id=7, n=12)
        self.assertEqual(captured["body"], ko_body)
        self.assertIsNone(captured["html"])


class TransactionalEmailTestCase(unittest.TestCase):
    def test_signup_and_reset_are_distinct_branded_emails(self):
        from email_i18n import verification_email
        for lang in LANGS:
            s_subject, s_html = verification_email("123456", lang, "signup")
            r_subject, r_html = verification_email("123456", lang, "reset")
            self.assertNotEqual(s_subject, r_subject, lang)
            for html in (s_html, r_html):
                self.assertIn("123456", html)
                self.assertIn("Sooppiy", html)
                self.assertIn("sooppiy.com", html)

    def test_default_purpose_is_signup(self):
        from email_i18n import verification_email
        default_subject, _ = verification_email("000000", "en")
        signup_subject, _ = verification_email("000000", "en", "signup")
        self.assertEqual(default_subject, signup_subject)


if __name__ == "__main__":
    unittest.main()
