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
from unittest.mock import patch

from fastapi.testclient import TestClient

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
from routes import create_app

ADMIN = {"Authorization": "Bearer test-admin-token"}


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
        self.env = patch.dict(os.environ, {"ADMIN_TOKEN": "test-admin-token"})
        self.env.start()
        self.client = TestClient(create_app())

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()


class AdminAuthTests(_Base):
    def test_no_token_401(self):
        r = self.client.get("/api/admin/overview")
        self.assertEqual(r.status_code, 401)

    def test_wrong_token_401(self):
        r = self.client.get("/api/admin/overview", headers={"Authorization": "Bearer nope"})
        self.assertEqual(r.status_code, 401)

    def test_disabled_when_env_unset_503(self):
        with patch.dict(os.environ, {"ADMIN_TOKEN": ""}):
            r = self.client.get("/api/admin/overview", headers=ADMIN)
        self.assertEqual(r.status_code, 503)


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

    def test_stale_identity_creates_fresh_user(self):
        import database
        from routes_oauth import _find_or_create_user_from_google

        google_user = {"sub": "g-sub-123", "email": "boss@example.com"}
        # First sign-in: creates user + identity link.
        first_id = _find_or_create_user_from_google(google_user)
        # Simulate the data reset: user deleted, identity row left behind.
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM users WHERE id = ?", (first_id,))
        conn.commit(); conn.close()
        # Second sign-in must NOT return the ghost id.
        second_id = _find_or_create_user_from_google(google_user)
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
        user_id = _find_or_create_user_from_google({"sub": "g-sub-9", "email": "del@example.com"})
        r = self.client.delete(f"/api/admin/users/{user_id}", headers=ADMIN)
        self.assertEqual(r.status_code, 200)
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) AS c FROM oauth_identities WHERE user_id = ?", (user_id,))
        self.assertEqual(cur.fetchone()["c"], 0)
        conn.close()
