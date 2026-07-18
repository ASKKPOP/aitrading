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
        self.assertEqual(set(cats), {"trade", "risk", "watch", "support", "announcement"})
        self.assertTrue(all(c["enabled"] for c in cats.values()))
        self.assertFalse(cats["trade"]["email"])
        self.assertFalse(cats["trade"]["sms"])

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

    def test_broadcast_is_audited(self):
        self.client.post("/api/admin/notifications/broadcast", headers=self.admin,
                         json={"title": "Hello"})
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT action FROM admin_audit_log WHERE action = 'notifications.broadcast'")
        rows = cur.fetchall()
        conn.close()
        self.assertEqual(len(rows), 1)


if __name__ == "__main__":
    unittest.main()
