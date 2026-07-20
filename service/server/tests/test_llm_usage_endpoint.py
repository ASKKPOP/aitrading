"""GET /api/users/settings/llm-usage — the data behind the top-bar AI spend pill.

Covers the two things the pill claims: WHICH model the caller's analysis runs on
(their own if configured, the server's otherwise) and WHOSE totals they may see.
"""

from __future__ import annotations

import json
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


class LlmUsageEndpointTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())

    def tearDown(self):
        self.tmp.cleanup()

    def _user(self, email: str) -> dict:
        from utils import hash_password
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO users (email, password_hash) VALUES (?, ?)",
                    (email, hash_password("testpass123")))
        conn.commit()
        conn.close()
        r = self.client.post("/api/users/login",
                             json={"email": email, "password": "testpass123"})
        assert r.status_code == 200, r.text
        return {"Authorization": f"Bearer {r.json()['token']}"}, r.json()

    def _set_user_llm(self, email: str, provider: str, model: str, api_key: str):
        conn = database.get_db_connection()
        cur = conn.cursor()
        database.begin_write_transaction(cur)
        cur.execute("SELECT id FROM users WHERE email = ?", (email,))
        uid = cur.fetchone()["id"]
        cur.execute(
            "INSERT INTO user_api_settings (user_id, target, api_key, config_json, enabled) "
            "VALUES (?, 'llm', ?, ?, 1)",
            (uid, api_key, json.dumps({"provider": provider, "model": model})))
        conn.commit()
        conn.close()
        return uid

    ENV = {"LLM_PROVIDER": "anthropic", "ANTHROPIC_API_KEY": "sk-server",
           "LLM_MODEL": "", "LLM_MODEL_DECISION": "claude-opus-4-8"}

    def test_reports_the_users_own_model_not_the_server_default(self):
        """A user running their own key saw the SERVER's model here — the one
        number on the pill that must not lie about whose AI is being billed."""
        headers, _ = self._user("own-key@x.com")
        self._set_user_llm("own-key@x.com", "openai", "gpt-4o-mini", "sk-user")
        with patch.dict(os.environ, {**self.ENV, "OPENAI_API_KEY": "sk-server-openai"}):
            body = self.client.get("/api/users/settings/llm-usage", headers=headers).json()
        self.assertEqual(body["active"]["provider"], "openai")
        self.assertEqual(body["active"]["model"], "gpt-4o-mini")
        self.assertEqual(body["active"]["key_source"], "user")

    def test_falls_back_to_the_server_model_when_the_user_configured_nothing(self):
        headers, _ = self._user("no-key@x.com")
        with patch.dict(os.environ, self.ENV):
            body = self.client.get("/api/users/settings/llm-usage", headers=headers).json()
        self.assertEqual(body["active"]["provider"], "anthropic")
        self.assertEqual(body["active"]["model"], "claude-opus-4-8")
        self.assertEqual(body["active"]["key_source"], "system")

    def test_a_user_row_without_a_key_still_reports_system_billing(self):
        """Model preference without a key = the service still pays."""
        headers, _ = self._user("model-only@x.com")
        self._set_user_llm("model-only@x.com", "anthropic", "claude-haiku-4-5", "")
        with patch.dict(os.environ, self.ENV):
            body = self.client.get("/api/users/settings/llm-usage", headers=headers).json()
        self.assertEqual(body["active"]["model"], "claude-haiku-4-5")
        self.assertEqual(body["active"]["key_source"], "system")

    def test_system_totals_are_owner_only(self):
        owner_h, _ = self._user("info@askkpop.com")
        other_h, _ = self._user("member@x.com")
        with patch.dict(os.environ, self.ENV):
            owner = self.client.get("/api/users/settings/llm-usage", headers=owner_h).json()
            other = self.client.get("/api/users/settings/llm-usage", headers=other_h).json()
        self.assertIn("system", owner)
        self.assertNotIn("system", other, "a non-owner must never receive system-wide spend")

    def test_requires_authentication(self):
        self.assertEqual(self.client.get("/api/users/settings/llm-usage").status_code, 401)

    def test_a_settings_lookup_failure_degrades_instead_of_500ing(self):
        """The panel is decoration; a settings-table problem must not take the
        endpoint down. (This path also caught a NameError in the handler's own
        logging — it referenced `logger` in a module that defines `_logger`.)"""
        import routes_users
        headers, _ = self._user("degrade@x.com")
        with patch.dict(os.environ, self.ENV), \
                patch.object(routes_users, "get_db_connection",
                             side_effect=RuntimeError("settings table gone")):
            self.assertIsNone(routes_users._user_llm_settings(1))
        r = self.client.get("/api/users/settings/llm-usage", headers=headers)
        self.assertEqual(r.status_code, 200)

    def test_user_totals_never_include_another_users_spend(self):
        from llm_usage import record_usage
        a_h, _ = self._user("a@x.com")
        b_h, _ = self._user("b@x.com")

        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, email FROM users WHERE email IN ('a@x.com', 'b@x.com')")
        ids = {r["email"]: r["id"] for r in cur.fetchall()}
        conn.close()

        record_usage(provider="anthropic", model="claude-opus-4-8", tier="decision",
                     key_source="system", user_id=ids["a@x.com"], agent_id=None,
                     prompt_tokens=1000, completion_tokens=1000)
        for _ in range(3):
            record_usage(provider="anthropic", model="claude-opus-4-8", tier="decision",
                         key_source="system", user_id=ids["b@x.com"], agent_id=None,
                         prompt_tokens=9000, completion_tokens=9000)

        with patch.dict(os.environ, self.ENV):
            a = self.client.get("/api/users/settings/llm-usage", headers=a_h).json()
            b = self.client.get("/api/users/settings/llm-usage", headers=b_h).json()
        self.assertEqual(a["user"]["total_calls"], 1)
        self.assertEqual(b["user"]["total_calls"], 3)
        self.assertLess(a["user"]["total_cost_usd"], b["user"]["total_cost_usd"])


if __name__ == "__main__":
    unittest.main()
