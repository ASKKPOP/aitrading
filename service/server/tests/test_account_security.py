"""Account security (sub-project B) — phone verification, SMS password reset,
signup language choice, welcome email.

Spec: docs/superpowers/specs/2026-08-05-account-security-design.md
All external delivery (Twilio SMS, Resend/SendGrid email) is mocked.
"""

from __future__ import annotations

import os
import secrets as _secrets
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


def _mk_user(db, email="u@t.dev", lang="en"):
    conn = db.get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("INSERT INTO users (email, password_hash, lang) VALUES (?, 'x', ?)",
                    (email, lang))
        user_id = cur.lastrowid
        token = _secrets.token_urlsafe(24)
        cur.execute("INSERT INTO user_tokens (user_id, token, expires_at) "
                    "VALUES (?, ?, '2030-01-01T00:00:00Z')", (user_id, token))
        conn.commit()
        return user_id, token
    finally:
        conn.close()


class PhoneVerificationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        from routes import create_app
        self.client = TestClient(create_app())
        self.user_id, self.token = _mk_user(database, lang="ko")

    def tearDown(self):
        self.tmp.cleanup()

    def _h(self):
        return {"Authorization": f"Bearer {self.token}"}

    def test_send_code_validates_e164(self):
        r = self.client.post("/api/users/phone/send-code",
                             json={"phone": "01012345678"}, headers=self._h())
        self.assertEqual(r.status_code, 400)

    def test_send_and_verify_flow(self):
        with patch("routes_users._send_sms", return_value=True) as sms:
            r = self.client.post("/api/users/phone/send-code",
                                 json={"phone": "+821012345678"}, headers=self._h())
        self.assertEqual(r.status_code, 200, r.text)
        to_number, body = sms.call_args.args
        self.assertEqual(to_number, "+821012345678")
        code = "".join(ch for ch in body if ch.isdigit())[:6]
        self.assertEqual(len(code), 6)
        self.assertIn("Sooppiy", body)  # branded, Korean template for lang=ko
        r = self.client.post("/api/users/phone/verify",
                             json={"code": code}, headers=self._h())
        self.assertEqual(r.status_code, 200, r.text)
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT phone, phone_verified_at FROM users WHERE id = ?",
                        (self.user_id,))
            row = dict(cur.fetchone())
            cur.execute("SELECT config_json FROM user_api_settings "
                        "WHERE user_id = ? AND target = 'alerts'", (self.user_id,))
            cfg = cur.fetchone()
        finally:
            conn.close()
        self.assertEqual(row["phone"], "+821012345678")
        self.assertTrue(row["phone_verified_at"])
        import json as _json
        self.assertEqual(_json.loads(dict(cfg)["config_json"]).get("phone"),
                         "+821012345678")
        me = self.client.get("/api/users/me", headers=self._h()).json()
        self.assertEqual(me["phone"], "+821012345678")
        self.assertTrue(me["phone_verified"])

    def test_send_code_409_when_taken(self):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("INSERT INTO users (email, password_hash, phone, "
                        "phone_verified_at) VALUES ('o@t.dev', 'x', "
                        "'+821099998888', '2026-01-01T00:00:00Z')")
            conn.commit()
        finally:
            conn.close()
        with patch("routes_users._send_sms", return_value=True):
            r = self.client.post("/api/users/phone/send-code",
                                 json={"phone": "+821099998888"}, headers=self._h())
        self.assertEqual(r.status_code, 409)

    def test_send_code_cooldown(self):
        with patch("routes_users._send_sms", return_value=True):
            self.client.post("/api/users/phone/send-code",
                             json={"phone": "+821012345678"}, headers=self._h())
            r = self.client.post("/api/users/phone/send-code",
                                 json={"phone": "+821012345678"}, headers=self._h())
        self.assertEqual(r.status_code, 429)

    def test_verify_wrong_code_400(self):
        with patch("routes_users._send_sms", return_value=True):
            self.client.post("/api/users/phone/send-code",
                             json={"phone": "+821012345678"}, headers=self._h())
        r = self.client.post("/api/users/phone/verify",
                             json={"code": "000000"}, headers=self._h())
        self.assertEqual(r.status_code, 400)

    def test_verify_alerts_config_preserves_existing_keys(self):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("INSERT INTO user_api_settings (user_id, target, enabled, "
                        "config_json) VALUES (?, 'alerts', 1, "
                        "'{\"sms_consent\": true, \"phone\": \"+820000000000\"}')",
                        (self.user_id,))
            conn.commit()
        finally:
            conn.close()
        with patch("routes_users._send_sms", return_value=True) as sms:
            self.client.post("/api/users/phone/send-code",
                             json={"phone": "+821012345678"}, headers=self._h())
        code = "".join(ch for ch in sms.call_args.args[1] if ch.isdigit())[:6]
        self.client.post("/api/users/phone/verify", json={"code": code},
                         headers=self._h())
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT config_json FROM user_api_settings "
                        "WHERE user_id = ? AND target = 'alerts'", (self.user_id,))
            import json as _json
            cfg = _json.loads(dict(cur.fetchone())["config_json"])
        finally:
            conn.close()
        self.assertEqual(cfg["phone"], "+821012345678")
        self.assertTrue(cfg["sms_consent"])


class SmsPasswordResetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        from routes import create_app
        self.client = TestClient(create_app())
        self.user_id, self.token = _mk_user(database, email="sms@t.dev", lang="ja")
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("UPDATE users SET phone = '+818011112222', "
                        "phone_verified_at = '2026-01-01T00:00:00Z' WHERE id = ?",
                        (self.user_id,))
            conn.commit()
        finally:
            conn.close()

    def tearDown(self):
        self.tmp.cleanup()

    def test_forgot_sms_generic_for_unknown_phone(self):
        with patch("routes_users._send_sms", return_value=True) as sms:
            r1 = self.client.post("/api/users/forgot-password-sms",
                                  json={"phone": "+818011112222"})
            r2 = self.client.post("/api/users/forgot-password-sms",
                                  json={"phone": "+818099990000"})
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r1.json(), r2.json())     # identical bodies — no probing
        self.assertEqual(sms.call_count, 1)        # only the real, verified phone

    def test_reset_by_sms_happy_path_kills_sessions(self):
        with patch("routes_users._send_sms", return_value=True) as sms:
            self.client.post("/api/users/forgot-password-sms",
                             json={"phone": "+818011112222"})
        code = "".join(ch for ch in sms.call_args.args[1] if ch.isdigit())[:6]
        r = self.client.post("/api/users/reset-password-sms",
                             json={"phone": "+818011112222", "code": code,
                                   "new_password": "brandnewpw1"})
        self.assertEqual(r.status_code, 200, r.text)
        # old token dead
        me = self.client.get("/api/users/me",
                             headers={"Authorization": f"Bearer {self.token}"})
        self.assertEqual(me.status_code, 401)
        # new password logs in
        login = self.client.post("/api/users/login",
                                 json={"email": "sms@t.dev",
                                       "password": "brandnewpw1"})
        self.assertEqual(login.status_code, 200, login.text)

    def test_reset_sms_wrong_code(self):
        with patch("routes_users._send_sms", return_value=True):
            self.client.post("/api/users/forgot-password-sms",
                             json={"phone": "+818011112222"})
        r = self.client.post("/api/users/reset-password-sms",
                             json={"phone": "+818011112222", "code": "000000",
                                   "new_password": "brandnewpw1"})
        self.assertEqual(r.status_code, 400)

    def test_unverified_phone_never_receives_reset(self):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("UPDATE users SET phone_verified_at = NULL WHERE id = ?",
                        (self.user_id,))
            conn.commit()
        finally:
            conn.close()
        with patch("routes_users._send_sms", return_value=True) as sms:
            r = self.client.post("/api/users/forgot-password-sms",
                                 json={"phone": "+818011112222"})
        self.assertEqual(r.status_code, 200)
        sms.assert_not_called()


class SignupLangAndWelcomeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        from routes import create_app
        self.client = TestClient(create_app())

    def tearDown(self):
        self.tmp.cleanup()

    def test_chosen_lang_stored_and_welcome_sent(self):
        import routes_users
        sent = {}

        def fake_send_code(email, code, lang, purpose='signup'):
            sent['code'] = code
            sent['lang'] = lang
            return True

        with patch.object(routes_users, "send_verification_code_email",
                          side_effect=fake_send_code):
            r = self.client.post("/api/users/send-code",
                                 json={"email": "l@t.dev", "lang": "th"})
            self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(sent['lang'], 'th')

        with patch.object(routes_users, "send_welcome_email",
                          return_value=True) as welcome:
            r = self.client.post("/api/users/register",
                                 json={"email": "l@t.dev", "code": sent['code'],
                                       "password": "longenough1", "lang": "th"})
            self.assertEqual(r.status_code, 200, r.text)
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT lang FROM users WHERE email = 'l@t.dev'")
            self.assertEqual(dict(cur.fetchone())["lang"], "th")
        finally:
            conn.close()
        welcome.assert_called_once()
        self.assertEqual(welcome.call_args.args, ("l@t.dev", "th"))

    def test_invalid_lang_falls_back_to_guess(self):
        import routes_users
        sent = {}

        def fake_send_code(email, code, lang, purpose='signup'):
            sent['code'] = code
            sent['lang'] = lang
            return True

        with patch.object(routes_users, "send_verification_code_email",
                          side_effect=fake_send_code):
            self.client.post("/api/users/send-code",
                             json={"email": "g@t.dev", "lang": "xx"})
        self.assertIn(sent['lang'], {"en", "ko", "ja", "th", "vi", "id"})

    def test_welcome_failure_does_not_fail_signup(self):
        import routes_users
        sent = {}

        def fake_send_code(email, code, lang, purpose='signup'):
            sent['code'] = code
            return True

        with patch.object(routes_users, "send_verification_code_email",
                          side_effect=fake_send_code):
            self.client.post("/api/users/send-code",
                             json={"email": "w@t.dev", "lang": "en"})
        with patch.object(routes_users, "send_welcome_email",
                          side_effect=RuntimeError("mail down")):
            r = self.client.post("/api/users/register",
                                 json={"email": "w@t.dev", "code": sent['code'],
                                       "password": "longenough1", "lang": "en"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIn("token", r.json())

    def test_welcome_templates_all_langs(self):
        from email_i18n import welcome_email, welcome_email_text
        for lang in ("en", "ko", "ja", "th", "vi", "id"):
            subject, html = welcome_email(lang)
            self.assertTrue(subject and "<" in html)
            self.assertIn("sooppiy.com", html)
            self.assertTrue(welcome_email_text(lang))


if __name__ == "__main__":
    unittest.main()
