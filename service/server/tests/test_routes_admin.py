"""Admin/manager API — auth gate, overview, account listing, cascade deletes.

Also covers the post-mention notification added alongside (mentions in
top-level strategy/discussion posts notify like reply mentions).
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
from routes import create_app


def _register_agent(client: TestClient, name: str) -> tuple[int, str]:
    r = client.post("/api/claw/agents/selfRegister",
                    json={"name": name, "email": f"{name}@example.com", "password": "testpass123"})
    assert r.status_code == 200, r.text
    body = r.json()
    return body["agent_id"], body["token"]


class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())
        # Admin sessions: real email+password accounts (admin_auth.py).
        from admin_auth import create_admin
        create_admin("admin@test.com", "testpass123", "superadmin")
        r = self.client.post("/api/admin/login",
                             json={"email": "admin@test.com", "password": "testpass123"})
        assert r.status_code == 200, r.text
        global ADMIN
        ADMIN = {"Authorization": f"Bearer {r.json()['token']}"}

    def tearDown(self):
        self.tmp.cleanup()


class AdminAuthTests(_Base):
    def test_no_token_401(self):
        r = self.client.get("/api/admin/overview")
        self.assertEqual(r.status_code, 401)

    def test_wrong_token_401(self):
        r = self.client.get("/api/admin/overview", headers={"Authorization": "Bearer nope"})
        self.assertEqual(r.status_code, 401)

    def test_bad_login_401(self):
        r = self.client.post("/api/admin/login",
                             json={"email": "admin@test.com", "password": "wrong-password"})
        self.assertEqual(r.status_code, 401)


class AdminReadTests(_Base):
    def test_overview_counts(self):
        _register_agent(self.client, "ov-agent")
        r = self.client.get("/api/admin/overview", headers=ADMIN)
        self.assertEqual(r.status_code, 200)
        ov = r.json()["overview"]
        self.assertEqual(ov["agents"], 1)
        self.assertEqual(ov["users"], 0)
        self.assertGreaterEqual(ov["total_sim_cash"], 100000)
        self.assertIn("recent_agents", ov)

    def test_agents_list_and_search(self):
        _register_agent(self.client, "alpha-bot")
        _register_agent(self.client, "beta-bot")
        r = self.client.get("/api/admin/agents", headers=ADMIN)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["total"], 2)
        r = self.client.get("/api/admin/agents?q=alpha", headers=ADMIN)
        body = r.json()
        self.assertEqual(body["total"], 1)
        self.assertEqual(body["agents"][0]["name"], "alpha-bot")

    def test_transactions_and_automation_shapes(self):
        r = self.client.get("/api/admin/transactions", headers=ADMIN)
        self.assertEqual(r.status_code, 200)
        body = r.json()
        for key in ("trades", "points_transactions", "reward_ledger"):
            self.assertIsInstance(body[key], list)
        r = self.client.get("/api/admin/automation", headers=ADMIN)
        self.assertEqual(r.status_code, 200)
        self.assertIn("rules", r.json())
        self.assertIn("runs", r.json())


class AdminDeleteTests(_Base):
    def test_delete_agent_cascades_signals(self):
        agent_id, token = _register_agent(self.client, "doomed-bot")
        r = self.client.post("/api/signals/discussion",
                             json={"title": "hello", "content": "world", "market": "crypto"},
                             headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(r.status_code, 200, r.text)
        r = self.client.delete(f"/api/admin/agents/{agent_id}", headers=ADMIN)
        self.assertEqual(r.status_code, 200)
        deleted = r.json()["deleted"]
        self.assertEqual(deleted["agents"], 1)
        self.assertGreaterEqual(deleted.get("signals.agent_id", 0), 1)
        # gone from listing
        r = self.client.get("/api/admin/agents", headers=ADMIN)
        self.assertEqual(r.json()["total"], 0)

    def test_delete_missing_agent_404(self):
        r = self.client.delete("/api/admin/agents/9999", headers=ADMIN)
        self.assertEqual(r.status_code, 404)


class AdminDeleteFkCascadeTests(_Base):
    """Prod MySQL enforces FKs SQLite ignores — every table holding an FK to
    users/agents must be cleared by the delete cascade, or the final DELETE
    raises IntegrityError 1451 and the endpoint 500s (user_subscriptions hit
    live on 2026-08-02). SQLite won't raise, so assert no orphan rows remain
    instead."""

    def _make_user(self, email: str = "fkdel@example.com") -> int:
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO users (email, password_hash, lang) VALUES (?, 'x', 'en')",
            (email,))
        uid = cur.lastrowid
        conn.commit(); conn.close()
        return uid

    def test_user_delete_clears_subscription_and_support_rows(self):
        uid = self._make_user()
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO user_subscriptions (user_id, plan_code, status) VALUES (?, 'pro', 'active')",
            (uid,))
        cur.execute(
            "INSERT INTO support_threads (user_id, subject, created_at) VALUES (?, 'help', datetime('now'))",
            (uid,))
        tid = cur.lastrowid
        cur.execute(
            "INSERT INTO support_messages (thread_id, sender, body, created_at) VALUES (?, 'user', 'hi', datetime('now'))",
            (tid,))
        conn.commit(); conn.close()
        r = self.client.delete(f"/api/admin/users/{uid}", headers=ADMIN)
        self.assertEqual(r.status_code, 200, r.text)
        conn = database.get_db_connection()
        cur = conn.cursor()
        for table, col, val in (("user_subscriptions", "user_id", uid),
                                ("support_threads", "user_id", uid),
                                ("support_messages", "thread_id", tid),
                                ("users", "id", uid)):
            cur.execute(f"SELECT COUNT(*) AS c FROM {table} WHERE {col} = ?", (val,))
            self.assertEqual(cur.fetchone()["c"], 0, f"orphan rows left in {table}")
        conn.close()

    def test_agent_delete_clears_every_fk_table(self):
        agent_id, _ = _register_agent(self.client, "fk-doomed")
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO backtest_runs (agent_id, config) VALUES (?, '{}')", (agent_id,))
        cur.execute(
            "INSERT INTO chat_sessions (agent_id, market, created_at) VALUES (?, 'crypto', datetime('now'))",
            (agent_id,))
        sid = cur.lastrowid
        cur.execute(
            "INSERT INTO chat_messages (session_id, role, content, created_at) VALUES (?, 'user', 'q', datetime('now'))",
            (sid,))
        cur.execute("INSERT INTO config_profiles (agent_id, name, payload_json) VALUES (?, 'p', '{}')", (agent_id,))
        cur.execute(
            "INSERT INTO reputation_slashes (leader_id, loss_pct, follower_count, points_deducted) VALUES (?, 1.0, 1, 1)",
            (agent_id,))
        cur.execute(
            "INSERT INTO user_watches (agent_id, name, metric, comparator, threshold, created_at) VALUES (?, 'w', 'price', '>', 1, datetime('now'))",
            (agent_id,))
        conn.commit(); conn.close()
        r = self.client.delete(f"/api/admin/agents/{agent_id}", headers=ADMIN)
        self.assertEqual(r.status_code, 200, r.text)
        conn = database.get_db_connection()
        cur = conn.cursor()
        for table, col, val in (("backtest_runs", "agent_id", agent_id),
                                ("chat_messages", "session_id", sid),
                                ("chat_sessions", "agent_id", agent_id),
                                ("config_profiles", "agent_id", agent_id),
                                ("reputation_slashes", "leader_id", agent_id),
                                ("user_watches", "agent_id", agent_id),
                                ("agents", "id", agent_id)):
            cur.execute(f"SELECT COUNT(*) AS c FROM {table} WHERE {col} = ?", (val,))
            self.assertEqual(cur.fetchone()["c"], 0, f"orphan rows left in {table}")
        conn.close()


class PostMentionTests(_Base):
    def test_discussion_post_mention_notifies(self):
        _, alice_token = _register_agent(self.client, "mention-alice")
        _, bob_token = _register_agent(self.client, "mention-bob")
        r = self.client.post("/api/signals/discussion",
                             json={"title": "hey", "content": "ping @mention-alice thoughts?",
                                   "market": "crypto"},
                             headers={"Authorization": f"Bearer {bob_token}"})
        self.assertEqual(r.status_code, 200, r.text)
        r = self.client.get("/api/claw/messages/recent",
                            headers={"Authorization": f"Bearer {alice_token}"})
        self.assertEqual(r.status_code, 200)
        types = [m.get("type") for m in r.json().get("messages", [])]
        self.assertIn("discussion_mention", types)

    def test_self_mention_not_notified(self):
        _, alice_token = _register_agent(self.client, "self-alice")
        r = self.client.post("/api/signals/discussion",
                             json={"title": "note", "content": "reminder for @self-alice",
                                   "market": "crypto"},
                             headers={"Authorization": f"Bearer {alice_token}"})
        self.assertEqual(r.status_code, 200)
        r = self.client.get("/api/claw/messages/recent",
                            headers={"Authorization": f"Bearer {alice_token}"})
        types = [m.get("type") for m in r.json().get("messages", [])]
        self.assertNotIn("discussion_mention", types)


if __name__ == "__main__":
    unittest.main()


class StaleOAuthIdentityTests(_Base):
    """A Google identity whose linked user was deleted must not resurrect the
    ghost user_id — the callback should create a fresh user and re-link."""

    def test_repeat_login_is_not_created(self):
        """created=True routes a member to /getting-started — a returning
        login or an email-link must never count as a first visit."""
        import database
        from routes_oauth import _find_or_create_user_from_google

        google_user = {"sub": "g-sub-repeat", "email": "repeat@example.com"}
        first_id, first_created = _find_or_create_user_from_google(google_user)
        self.assertTrue(first_created)
        again_id, again_created = _find_or_create_user_from_google(google_user)
        self.assertEqual(again_id, first_id)
        self.assertFalse(again_created)
        # Existing email account linking Google for the first time: not new.
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO users (email, password_hash, points, lang) VALUES (?, 'x', 0, 'en')",
            ("linked@example.com",),
        )
        linked_id = cur.lastrowid
        conn.commit(); conn.close()
        got_id, got_created = _find_or_create_user_from_google(
            {"sub": "g-sub-linked", "email": "linked@example.com"})
        self.assertEqual(got_id, linked_id)
        self.assertFalse(got_created)

    def test_stale_identity_creates_fresh_user(self):
        import database
        from routes_oauth import _find_or_create_user_from_google

        google_user = {"sub": "g-sub-123", "email": "boss@example.com"}
        # First sign-in: creates user + identity link.
        first_id, first_created = _find_or_create_user_from_google(google_user)
        self.assertTrue(first_created)
        # Simulate the data reset: user deleted, identity row left behind.
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM users WHERE id = ?", (first_id,))
        conn.commit(); conn.close()
        # Second sign-in must NOT return the ghost id. It creates a FRESH
        # user, so created is True again — this member genuinely is new.
        second_id, second_created = _find_or_create_user_from_google(google_user)
        self.assertTrue(second_created)
        self.assertNotEqual(second_id, first_id)
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT id FROM users WHERE id = ?", (second_id,))
        self.assertIsNotNone(cur.fetchone())
        # And the identity link now points at the fresh user (no duplicates).
        cur.execute("SELECT user_id FROM oauth_identities WHERE provider='google' AND provider_user_id='g-sub-123'")
        rows = cur.fetchall()
        conn.close()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["user_id"], second_id)

    def test_admin_user_delete_cascades_oauth_identity(self):
        import database
        from routes_oauth import _find_or_create_user_from_google
        user_id, _created = _find_or_create_user_from_google({"sub": "g-sub-9", "email": "del@example.com"})
        r = self.client.delete(f"/api/admin/users/{user_id}", headers=ADMIN)
        self.assertEqual(r.status_code, 200)
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) AS c FROM oauth_identities WHERE user_id = ?", (user_id,))
        self.assertEqual(cur.fetchone()["c"], 0)
        conn.close()
