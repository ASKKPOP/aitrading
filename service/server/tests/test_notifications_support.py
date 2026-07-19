"""Member notification centre + member ⇄ administrator chat
(notifications.py, routes_support.py, and the alerts.py bridge)."""
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

        self.user_id, self.member = self._make_user()

    def tearDown(self):
        self.tmp.cleanup()

    def _make_user(self, email: str = "member@x.com", password: str = "memberpass1"):
        from utils import hash_password
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO users (email, password_hash) VALUES (?, ?)",
                    (email, hash_password(password)))
        user_id = cur.lastrowid
        conn.commit()
        conn.close()
        r = self.client.post("/api/users/login", json={"email": email, "password": password})
        assert r.status_code == 200, r.text
        return user_id, {"Authorization": f"Bearer {r.json()['token']}"}


class TestNotificationPrefs(_Base):
    def test_defaults_are_all_enabled_in_app_only(self):
        r = self.client.get("/api/notifications/settings", headers=self.member)
        self.assertEqual(r.status_code, 200)
        cats = {c["key"]: c for c in r.json()["categories"]}
        self.assertEqual(set(cats), {"trade", "risk", "watch", "support", "announcement",
                                     # Trading Runs (Plan 10 D8)
                                     "auto_trading_reports", "auto_trading_safety"})
        self.assertTrue(all(c["enabled"] for c in cats.values()))
        self.assertFalse(cats["trade"]["email"])
        self.assertFalse(cats["trade"]["sms"])
        # run categories default email ON (that is their point); SMS off
        self.assertTrue(cats["auto_trading_reports"]["email"])
        self.assertFalse(cats["auto_trading_reports"]["sms"])
        self.assertTrue(cats["auto_trading_safety"]["email"])

    def test_legacy_alert_optin_seeds_trade_email_default(self):
        # A member who enabled email on the old Alerts card keeps email
        # delivery for trade/risk/watch without re-opting in.
        self.client.put("/api/users/settings/api/alerts", headers=self.member,
                        json={"config": {"email_enabled": "true", "sms_enabled": "false",
                                         "phone": "+821012345678"}})
        cats = {c["key"]: c for c in
                self.client.get("/api/notifications/settings",
                                headers=self.member).json()["categories"]}
        self.assertTrue(cats["trade"]["email"])
        self.assertTrue(cats["risk"]["email"])
        self.assertFalse(cats["trade"]["sms"])
        # Admin-originated categories keep their own catalog defaults.
        self.assertTrue(cats["support"]["email"])

    def test_update_switches_persists(self):
        r = self.client.put("/api/notifications/settings", headers=self.member,
                            json={"categories": {"trade": {"enabled": False, "email": True}}})
        self.assertEqual(r.status_code, 200)
        cats = {c["key"]: c for c in
                self.client.get("/api/notifications/settings",
                                headers=self.member).json()["categories"]}
        self.assertFalse(cats["trade"]["enabled"])
        self.assertTrue(cats["trade"]["email"])
        # Untouched categories are unchanged.
        self.assertTrue(cats["risk"]["enabled"])

    def test_unknown_category_rejected(self):
        r = self.client.put("/api/notifications/settings", headers=self.member,
                            json={"categories": {"nope": {"enabled": True}}})
        self.assertEqual(r.status_code, 400)

    def test_settings_require_auth(self):
        self.assertEqual(self.client.get("/api/notifications/settings").status_code, 401)
        self.assertEqual(self.client.get("/api/notifications").status_code, 401)

    def test_disabled_alerts_target_does_not_re_optin_email(self):
        # Regression: a member who turned the 'alerts' target OFF must not have
        # its email_enabled inherited as a per-category default. _load_target
        # filters on enabled = 1, matching the pre-refactor s.enabled = 1 join.
        self.client.put("/api/users/settings/api/alerts", headers=self.member,
                        json={"config": {"email_enabled": "true", "sms_enabled": "true",
                                         "phone": "+821012345678"}})
        # Now disable the whole alerts target.
        self.client.put("/api/users/settings/api/alerts", headers=self.member,
                        json={"enabled": False})
        cats = {c["key"]: c for c in
                self.client.get("/api/notifications/settings",
                                headers=self.member).json()["categories"]}
        self.assertFalse(cats["trade"]["email"])
        self.assertFalse(cats["risk"]["email"])
        self.assertFalse(cats["trade"]["sms"])


class TestNotificationFeed(_Base):
    def test_notify_appears_in_feed_and_marks_read(self):
        import notifications
        notifications.notify(self.user_id, "announcement", "Maintenance", "Sunday 02:00 UTC")

        r = self.client.get("/api/notifications", headers=self.member)
        body = r.json()
        self.assertEqual(body["unread"], 1)
        self.assertEqual(body["notifications"][0]["title"], "Maintenance")

        nid = body["notifications"][0]["id"]
        r = self.client.post("/api/notifications/read", headers=self.member, json={"ids": [nid]})
        self.assertEqual(r.json()["marked"], 1)
        self.assertEqual(r.json()["unread"], 0)

    def test_mark_all_read(self):
        import notifications
        for i in range(3):
            notifications.notify(self.user_id, "announcement", f"n{i}", "")
        r = self.client.post("/api/notifications/read", headers=self.member, json={"all": True})
        self.assertEqual(r.json()["marked"], 3)
        self.assertEqual(
            self.client.get("/api/notifications/summary", headers=self.member).json()["unread"], 0)

    def test_read_requires_ids_or_all(self):
        r = self.client.post("/api/notifications/read", headers=self.member, json={})
        self.assertEqual(r.status_code, 400)

    def test_disabled_category_is_not_delivered(self):
        import notifications
        notifications.set_prefs(self.user_id, {"announcement": {"enabled": False}})
        out = notifications.notify(self.user_id, "announcement", "hidden", "")
        self.assertEqual(out.get("skipped"), "disabled")
        self.assertEqual(
            self.client.get("/api/notifications", headers=self.member).json()["unread"], 0)

    def test_unread_only_filter(self):
        import notifications
        notifications.notify(self.user_id, "announcement", "old", "")
        notifications.mark_read(self.user_id)
        notifications.notify(self.user_id, "announcement", "new", "")
        r = self.client.get("/api/notifications?unread_only=true", headers=self.member)
        titles = [n["title"] for n in r.json()["notifications"]]
        self.assertEqual(titles, ["new"])

    def test_feed_is_per_member(self):
        import notifications
        other_id, other = self._make_user("other@x.com", "otherpass1")
        notifications.notify(self.user_id, "announcement", "mine", "")
        self.assertEqual(
            self.client.get("/api/notifications", headers=other).json()["notifications"], [])
        self.assertEqual(notifications.unread_count(other_id), 0)


class TestAlertBridge(_Base):
    def _make_agent(self) -> int:
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO agents (name, token, user_id) VALUES (?, ?, ?)",
                    ("bridge-agent", "claw_bridge", self.user_id))
        agent_id = cur.lastrowid
        conn.commit()
        conn.close()
        return agent_id

    def test_send_alert_mirrors_into_notification_feed(self):
        import alerts
        agent_id = self._make_agent()
        alerts.send_alert(agent_id, "trade_executed", "BUY BTC", "0.1 @ 65000")

        r = self.client.get("/api/notifications", headers=self.member).json()
        self.assertEqual(r["unread"], 1)
        self.assertEqual(r["notifications"][0]["category"], "trade")
        self.assertEqual(r["notifications"][0]["title"], "BUY BTC")

    def test_category_switch_off_blocks_alert_email_and_feed(self):
        import alerts
        import notifications
        agent_id = self._make_agent()
        # Legacy opt-in would have sent email; the category switch overrides it.
        self.client.put("/api/users/settings/api/alerts", headers=self.member,
                        json={"config": {"email_enabled": "true", "phone": ""}})
        notifications.set_prefs(self.user_id, {"trade": {"enabled": False}})

        with patch.object(alerts, "_send_email", return_value=True) as send:
            out = alerts.send_alert(agent_id, "trade_executed", "BUY BTC", "body")
        send.assert_not_called()
        self.assertEqual(out["channels"], ["inapp"])  # alert_log still journals
        self.assertEqual(
            self.client.get("/api/notifications", headers=self.member).json()["unread"], 0)

    def test_category_email_switch_drives_delivery(self):
        import alerts
        import notifications
        agent_id = self._make_agent()
        notifications.set_prefs(self.user_id, {"risk": {"enabled": True, "email": True}})
        with patch.object(alerts, "_send_email", return_value=True) as send:
            out = alerts.send_alert(agent_id, "breaker", "HALT", "daily loss")
        send.assert_called_once()
        self.assertIn("email", out["channels"])


class TestSupportChat(_Base):
    def test_member_sends_and_admin_replies(self):
        r = self.client.post("/api/support/messages", headers=self.member,
                             json={"body": "My automation stopped filling orders."})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()["messages"]), 1)

        threads = self.client.get("/api/admin/support/threads", headers=self.admin).json()
        self.assertEqual(threads["unread_total"], 1)
        thread_id = threads["threads"][0]["id"]
        self.assertEqual(threads["threads"][0]["user_email"], "member@x.com")

        # Opening the thread in the console clears the admin badge.
        detail = self.client.get(f"/api/admin/support/threads/{thread_id}",
                                 headers=self.admin).json()
        self.assertEqual(detail["thread"]["admin_unread"], 0)

        r = self.client.post(f"/api/admin/support/threads/{thread_id}/reply",
                             headers=self.admin, json={"body": "Checking your rule now."})
        self.assertEqual(r.status_code, 200)
        senders = [m["sender"] for m in r.json()["messages"]]
        self.assertEqual(senders, ["user", "admin"])

        # The member gets a support notification and an unread chat badge.
        summary = self.client.get("/api/notifications/summary", headers=self.member).json()
        self.assertEqual(summary["support_unread"], 1)
        self.assertEqual(summary["unread"], 1)
        feed = self.client.get("/api/notifications", headers=self.member).json()
        self.assertEqual(feed["notifications"][0]["category"], "support")

        # Opening the conversation clears the member's badge.
        thread = self.client.get("/api/support/thread", headers=self.member).json()
        self.assertEqual(thread["thread"]["user_unread"], 0)
        self.assertEqual(len(thread["messages"]), 2)

    def test_thread_is_created_empty_on_first_open(self):
        r = self.client.get("/api/support/thread", headers=self.member)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["messages"], [])
        self.assertEqual(r.json()["thread"]["status"], "open")

    def test_empty_message_rejected(self):
        r = self.client.post("/api/support/messages", headers=self.member, json={"body": "   "})
        self.assertEqual(r.status_code, 400)

    def test_members_cannot_read_each_others_threads(self):
        self.client.post("/api/support/messages", headers=self.member, json={"body": "private"})
        _, other = self._make_user("other@x.com", "otherpass1")
        msgs = self.client.get("/api/support/thread", headers=other).json()["messages"]
        self.assertEqual(msgs, [])

    def test_admin_endpoints_require_admin_token(self):
        self.assertEqual(self.client.get("/api/admin/support/threads").status_code, 401)
        # A member session token is not an admin token.
        self.assertEqual(
            self.client.get("/api/admin/support/threads", headers=self.member).status_code, 401)

    def test_close_and_reopen_thread(self):
        self.client.post("/api/support/messages", headers=self.member, json={"body": "hi"})
        tid = self.client.get("/api/admin/support/threads",
                              headers=self.admin).json()["threads"][0]["id"]
        r = self.client.post(f"/api/admin/support/threads/{tid}/status",
                             headers=self.admin, json={"status": "closed"})
        self.assertEqual(r.status_code, 200)
        closed = self.client.get("/api/admin/support/threads?status=closed",
                                 headers=self.admin).json()
        self.assertEqual(len(closed["threads"]), 1)
        # A new member message reopens it.
        self.client.post("/api/support/messages", headers=self.member, json={"body": "still broken"})
        self.assertEqual(
            self.client.get(f"/api/admin/support/threads/{tid}",
                            headers=self.admin).json()["thread"]["status"], "open")

    def test_bad_status_rejected(self):
        self.client.post("/api/support/messages", headers=self.member, json={"body": "hi"})
        tid = self.client.get("/api/admin/support/threads",
                              headers=self.admin).json()["threads"][0]["id"]
        r = self.client.post(f"/api/admin/support/threads/{tid}/status",
                             headers=self.admin, json={"status": "archived"})
        self.assertEqual(r.status_code, 400)

    def test_reply_to_missing_thread_is_404(self):
        r = self.client.post("/api/admin/support/threads/999/reply",
                             headers=self.admin, json={"body": "hello"})
        self.assertEqual(r.status_code, 404)


class TestBroadcast(_Base):
    def test_broadcast_reaches_every_opted_in_member(self):
        import notifications
        other_id, other = self._make_user("other@x.com", "otherpass1")
        notifications.set_prefs(other_id, {"announcement": {"enabled": False}})

        r = self.client.post("/api/admin/notifications/broadcast", headers=self.admin,
                             json={"title": "Scheduled maintenance", "body": "Sunday 02:00 UTC"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["targeted"], 2)
        self.assertEqual(r.json()["delivered"], 1)

        self.assertEqual(
            self.client.get("/api/notifications", headers=self.member).json()["unread"], 1)
        self.assertEqual(
            self.client.get("/api/notifications", headers=other).json()["unread"], 0)

    def test_broadcast_to_single_member(self):
        _, other = self._make_user("other@x.com", "otherpass1")
        r = self.client.post("/api/admin/notifications/broadcast", headers=self.admin,
                             json={"title": "Your plan expires soon", "user_id": self.user_id})
        self.assertEqual(r.json()["targeted"], 1)
        self.assertEqual(
            self.client.get("/api/notifications", headers=other).json()["unread"], 0)

    def test_broadcast_requires_title(self):
        r = self.client.post("/api/admin/notifications/broadcast", headers=self.admin,
                             json={"title": "  "})
        self.assertEqual(r.status_code, 400)

    def test_broadcast_link_is_sanitized_to_internal_paths(self):
        # Stored-XSS guard: a hostile link must never reach the feed. Only a
        # single-leading-slash in-app path survives; everything else is dropped.
        cases = {
            "javascript:alert(1)": None,
            "//evil.example.com/x": None,
            "https://evil.example.com/y": None,
            "/support": "/support",
        }
        for i, (link, expected) in enumerate(cases.items()):
            r = self.client.post("/api/admin/notifications/broadcast", headers=self.admin,
                                 json={"title": f"n{i}", "user_id": self.user_id, "link": link})
            self.assertEqual(r.status_code, 200)
        feed = self.client.get("/api/notifications?limit=100", headers=self.member).json()
        by_title = {n["title"]: n["link"] for n in feed["notifications"]}
        for i, (link, expected) in enumerate(cases.items()):
            self.assertEqual(by_title[f"n{i}"], expected, f"link {link!r} not sanitized")


class TestSetPrefsRace(_Base):
    def test_concurrent_first_write_recovers_from_unique_collision(self):
        # Mirrors the support_threads race (commit 73f4573): simulate the losing
        # writer by inserting the 'notifications' row from a second connection
        # right after set_prefs would SELECT-miss. set_prefs must recover, not 500.
        import json as _json
        import notifications
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO user_api_settings
               (user_id, target, api_key, config_json, enabled, updated_at)
               VALUES (?, 'notifications', NULL, ?, 1, ?)""",
            (self.user_id, _json.dumps({"trade": {"enabled": True, "email": True, "sms": False}}),
             "2026-07-18T00:00:00Z"))
        conn.commit()
        conn.close()
        # A brand-new patch on a DIFFERENT category must merge onto the winner's
        # row, not clobber it or raise.
        merged = notifications.set_prefs(self.user_id, {"risk": {"enabled": False}})
        self.assertFalse(merged["risk"]["enabled"])
        self.assertTrue(merged["trade"]["email"])  # winner's write preserved

    def test_mark_read_beyond_500_ids_marks_all(self):
        # 600 unread ids in one call must all be marked — the IN clause is
        # chunked at 500, not truncated (which would silently drop 100).
        import notifications
        for i in range(600):
            notifications.notify(self.user_id, "announcement", f"n{i}", "")
        conn = database.get_db_connection()
        c = conn.cursor()
        c.execute("SELECT id FROM user_notifications WHERE user_id = ? ORDER BY id", (self.user_id,))
        every = [r["id"] for r in c.fetchall()]
        conn.close()
        self.assertEqual(len(every), 600)
        self.assertEqual(notifications.mark_read(self.user_id, every), 600)
        self.assertEqual(notifications.unread_count(self.user_id), 0)

    def test_broadcast_is_audited(self):
        self.client.post("/api/admin/notifications/broadcast", headers=self.admin,
                         json={"title": "Hello"})
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT action FROM admin_audit_log WHERE action = 'notifications.broadcast'")
        rows = cur.fetchall()
        conn.close()
        self.assertEqual(len(rows), 1)


class TestNegativePaths(_Base):
    def test_member_cannot_mark_another_members_notifications_read(self):
        import notifications
        notifications.notify(self.user_id, "announcement", "For A only", external=False)
        r = self.client.get("/api/notifications", headers=self.member)
        target_id = r.json()["notifications"][0]["id"]

        _, other = self._make_user("intruder@x.com", "intruderpass1")
        r = self.client.post("/api/notifications/read",
                             json={"ids": [target_id]}, headers=other)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["marked"], 0)
        r = self.client.get("/api/notifications/summary", headers=self.member)
        self.assertEqual(r.json()["unread"], 1)

    def test_support_endpoints_require_auth(self):
        self.assertEqual(self.client.get("/api/support/thread").status_code, 401)
        self.assertEqual(
            self.client.post("/api/support/messages", json={"body": "hi"}).status_code, 401)

    def test_long_message_and_subject_are_truncated(self):
        r = self.client.post("/api/support/messages",
                             json={"body": "x" * 5000, "subject": "s" * 400},
                             headers=self.member)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()["messages"][-1]["body"]), 4000)
        r = self.client.get("/api/support/thread", headers=self.member)
        self.assertLessEqual(len(r.json()["thread"]["subject"]), 255)

    def test_broadcast_to_unknown_member_is_404(self):
        r = self.client.post("/api/admin/notifications/broadcast",
                             json={"title": "Hello", "user_id": 999999},
                             headers=self.admin)
        self.assertEqual(r.status_code, 404)


if __name__ == "__main__":
    unittest.main()
