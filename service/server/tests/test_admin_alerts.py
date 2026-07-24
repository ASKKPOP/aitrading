"""Operator subscription alerts (admin_alerts.notify_admins + /api/admin/settings/alerts)
and the per-user trading-mode rollup surfaced on /api/admin/users."""
from __future__ import annotations

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


class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())
        from admin_auth import create_admin
        create_admin("root@test.com", "rootpass123", "superadmin")
        r = self.client.post("/api/admin/login",
                             json={"email": "root@test.com", "password": "rootpass123"})
        self.admin = {"Authorization": f"Bearer {r.json()['token']}"}
        # These env vars are the fallback for the alert recipient settings; pop
        # them so a developer's real .env can't make an "unconfigured" case send.
        self._saved_env = {k: os.environ.pop(k, None)
                           for k in ("ADMIN_ALERT_EMAIL", "ADMIN_ALERT_PHONE")}

    def tearDown(self):
        for k, v in self._saved_env.items():
            if v is not None:
                os.environ[k] = v
        self.tmp.cleanup()


class NotifyAdminsTests(_Base):
    def test_both_channels_fire_when_configured(self):
        from platform_settings import set_setting
        set_setting("admin_alert_email", "ops@x.com")
        set_setting("admin_alert_phone", "+12025550123")
        import admin_alerts
        with patch("alerts._send_email", return_value=True) as em, \
                patch("alerts._send_sms", return_value=True) as sm:
            out = admin_alerts.notify_admins("New request", "body line")
        self.assertEqual(out["channels"], ["email", "sms"])
        em.assert_called_once()
        sm.assert_called_once()
        # subject is prefixed and the email goes to the configured address
        to_email, subject, _body = em.call_args[0]
        self.assertEqual(to_email, "ops@x.com")
        self.assertTrue(subject.startswith("[Sooppiy] "))

    def test_unconfigured_sends_nothing(self):
        import admin_alerts
        with patch("alerts._send_email", return_value=True) as em, \
                patch("alerts._send_sms", return_value=True) as sm:
            out = admin_alerts.notify_admins("S", "B")
        self.assertEqual(out["channels"], [])
        em.assert_not_called()
        sm.assert_not_called()

    def test_only_email_configured(self):
        from platform_settings import set_setting
        set_setting("admin_alert_email", "ops@x.com")
        import admin_alerts
        with patch("alerts._send_email", return_value=True) as em, \
                patch("alerts._send_sms", return_value=True) as sm:
            out = admin_alerts.notify_admins("S", "B")
        self.assertEqual(out["channels"], ["email"])
        em.assert_called_once()
        sm.assert_not_called()

    def test_sender_exception_is_swallowed(self):
        from platform_settings import set_setting
        set_setting("admin_alert_email", "ops@x.com")
        set_setting("admin_alert_phone", "+12025550123")
        import admin_alerts
        with patch("alerts._send_email", side_effect=RuntimeError("smtp down")), \
                patch("alerts._send_sms", return_value=True):
            out = admin_alerts.notify_admins("S", "B")  # must not raise
        # email raised → dropped; sms still delivered
        self.assertEqual(out["channels"], ["sms"])


class AlertSettingsApiTests(_Base):
    def test_requires_admin(self):
        self.assertIn(self.client.get("/api/admin/settings/alerts").status_code, (401, 403))
        self.assertIn(self.client.put("/api/admin/settings/alerts", json={}).status_code,
                      (401, 403))

    def test_get_shape(self):
        r = self.client.get("/api/admin/settings/alerts", headers=self.admin)
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIn("admin_alert_email", body)
        self.assertIn("value", body["admin_alert_email"])

    def test_put_saves_both(self):
        r = self.client.put("/api/admin/settings/alerts", headers=self.admin,
                            json={"admin_alert_email": "ops@x.com",
                                  "admin_alert_phone": "+12025550123"})
        self.assertEqual(r.status_code, 200, r.text)
        from platform_settings import get_setting
        self.assertEqual(get_setting("admin_alert_email"), "ops@x.com")
        self.assertEqual(get_setting("admin_alert_phone"), "+12025550123")

    def test_put_rejects_bad_email(self):
        r = self.client.put("/api/admin/settings/alerts", headers=self.admin,
                            json={"admin_alert_email": "notanemail", "admin_alert_phone": ""})
        self.assertEqual(r.status_code, 400)

    def test_put_rejects_bad_phone(self):
        r = self.client.put("/api/admin/settings/alerts", headers=self.admin,
                            json={"admin_alert_email": "", "admin_alert_phone": "call-me"})
        self.assertEqual(r.status_code, 400)

    def test_empty_clears(self):
        from platform_settings import get_setting, set_setting
        set_setting("admin_alert_email", "ops@x.com")
        r = self.client.put("/api/admin/settings/alerts", headers=self.admin,
                            json={"admin_alert_email": "", "admin_alert_phone": ""})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(get_setting("admin_alert_email"), "")


class TradingModeRollupTests(_Base):
    def _user_with_rules(self, email: str, agent_name: str, account_types: list[str]) -> int:
        from utils import hash_password
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO users (email, password_hash) VALUES (?, ?)",
                    (email, hash_password("pw12345678")))
        uid = cur.lastrowid
        cur.execute("INSERT INTO agents (name, user_id) VALUES (?, ?)", (agent_name, uid))
        aid = cur.lastrowid
        for i, at in enumerate(account_types):
            cur.execute(
                "INSERT INTO automation_configs (agent_id, symbol, account_type) VALUES (?, ?, ?)",
                (aid, f"SYM{i}", at))
        conn.commit()
        conn.close()
        return uid

    def _mode_for(self, uid: int):
        r = self.client.get("/api/admin/users?limit=200", headers=self.admin)
        self.assertEqual(r.status_code, 200, r.text)
        for u in r.json()["users"]:
            if u["id"] == uid:
                return u.get("trading_mode")
        raise AssertionError(f"user {uid} not in admin users listing")

    def test_live_beats_shadow_and_simulator(self):
        uid = self._user_with_rules("a@x.com", "agentA", ["simulator", "shadow", "live"])
        self.assertEqual(self._mode_for(uid), "live")

    def test_legacy_real_counts_as_live(self):
        uid = self._user_with_rules("b@x.com", "agentB", ["real"])
        self.assertEqual(self._mode_for(uid), "live")

    def test_shadow_beats_simulator(self):
        uid = self._user_with_rules("c@x.com", "agentC", ["simulator", "shadow"])
        self.assertEqual(self._mode_for(uid), "shadow")

    def test_all_simulator(self):
        uid = self._user_with_rules("d@x.com", "agentD", ["simulator", "simulator"])
        self.assertEqual(self._mode_for(uid), "simulator")

    def test_no_rules_is_none(self):
        uid = self._user_with_rules("e@x.com", "agentE", [])
        self.assertIsNone(self._mode_for(uid))


if __name__ == "__main__":
    unittest.main()
