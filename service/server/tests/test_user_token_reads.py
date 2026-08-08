"""My Trading reads must work with a web-login (user) token.

Prod 2026-08-08: the 내 트레이딩 page called GET /api/positions,
/api/signals/following and /api/strategies with the browser's USER token,
but all three authorized only agent (claw_) tokens — so every card rendered
(0) for every web user while the account's agent held 5 open positions.
The page's "tolerate individual failures" made the 401 look like emptiness.

Fix: those three READ endpoints also resolve a user token to that user's
agent. Write paths stay agent-token-only.
"""

import os
import secrets
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


def _mk_user_with_agent(email="owner@t.dev", agent_name="owner-agent"):
    """A web user, their session token, and the agent their signup created."""
    conn = database.get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("INSERT INTO users (email, password_hash) VALUES (?, 'x')",
                    (email,))
        user_id = cur.lastrowid
        token = secrets.token_urlsafe(24)
        cur.execute("INSERT INTO user_tokens (user_id, token, expires_at) "
                    "VALUES (?, ?, '2030-01-01T00:00:00Z')", (user_id, token))
        cur.execute("INSERT INTO agents (name, user_id) VALUES (?, ?)",
                    (agent_name, user_id))
        agent_id = cur.lastrowid
        conn.commit()
        return user_id, token, agent_id
    finally:
        conn.close()


def _mk_position(agent_id, symbol="ADBE"):
    conn = database.get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO positions (agent_id, symbol, market, side, quantity,"
            " entry_price, opened_at) VALUES (?, ?, 'us-stock', 'long', 1.5,"
            " 100.0, '2026-08-08T00:00:00Z')", (agent_id, symbol))
        conn.commit()
    finally:
        conn.close()


class UserTokenReadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())
        self.user_id, self.token, self.agent_id = _mk_user_with_agent()

    def tearDown(self):
        self.tmp.cleanup()

    def _h(self, token=None):
        return {"Authorization": f"Bearer {token or self.token}"}

    def test_user_token_reads_own_agent_positions(self):
        _mk_position(self.agent_id, symbol="ADBE")
        resp = self.client.get("/api/positions", headers=self._h())
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        rows = body if isinstance(body, list) else body.get("positions", [])
        self.assertEqual([r["symbol"] for r in rows], ["ADBE"])

    def test_user_token_reads_following(self):
        resp = self.client.get("/api/signals/following", headers=self._h())
        self.assertEqual(resp.status_code, 200, resp.text)

    def test_user_token_reads_strategies(self):
        resp = self.client.get("/api/strategies", headers=self._h())
        self.assertEqual(resp.status_code, 200, resp.text)

    def test_agent_token_still_reads_positions(self):
        # The claw-token contract is unchanged.
        reg = self.client.post(
            "/api/claw/agents/selfRegister",
            json={"name": "claw-agent", "password": "pw123",
                  "initial_balance": 100000.0})
        self.assertEqual(reg.status_code, 200, reg.text)
        claw = reg.json()["token"]
        resp = self.client.get("/api/positions", headers=self._h(claw))
        self.assertEqual(resp.status_code, 200, resp.text)

    def test_garbage_token_still_401(self):
        for path in ("/api/positions", "/api/signals/following",
                     "/api/strategies"):
            resp = self.client.get(path, headers=self._h("claw_nonsense"))
            self.assertEqual(resp.status_code, 401, path)

    def test_user_without_agent_still_401(self):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("INSERT INTO users (email, password_hash) "
                        "VALUES ('noagent@t.dev', 'x')")
            uid = cur.lastrowid
            lonely = secrets.token_urlsafe(24)
            cur.execute("INSERT INTO user_tokens (user_id, token, expires_at) "
                        "VALUES (?, ?, '2030-01-01T00:00:00Z')", (uid, lonely))
            conn.commit()
        finally:
            conn.close()
        resp = self.client.get("/api/positions", headers=self._h(lonely))
        self.assertEqual(resp.status_code, 401)

    def test_write_paths_stay_agent_only(self):
        # A browser session must not gain agent-API writes it never had.
        resp = self.client.post("/api/strategies", headers=self._h(),
                                json={"name": "x", "description": "y"})
        self.assertEqual(resp.status_code, 401)


if __name__ == "__main__":
    unittest.main()
