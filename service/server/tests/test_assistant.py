"""AI Assistant — full-context profile, privacy, persistence (LLM mocked)."""

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

import assistant
import database
from routes import create_app

_NO_LLM_ENV = {k: "" for k in (
    "LLM_PROVIDER", "LLM_MODEL", "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY", "XAI_API_KEY", "GROK_API_KEY", "DASHSCOPE_API_KEY",
    "QWEN_API_KEY", "GLM_API_KEY", "ZHIPUAI_API_KEY", "OPENROUTER_API_KEY",
)}

SECRET_KEY = "sk-user-SUPERSECRET-must-never-leak"


class AssistantTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())
        body = self.client.post(
            "/api/claw/agents/selfRegister",
            json={"name": "owner", "password": "pw123", "initial_balance": 100000.0}).json()
        self.agent_id = body["agent_id"]
        self.token = body["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
        # link a human user + settings + guidelines
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO users (email, password_hash, trading_guidelines, created_at) "
                    "VALUES (?, ?, ?, ?)",
                    ("henry@test.io", "x", "Never trade weekends.", "2026-01-01T00:00:00Z"))
        self.user_id = cur.lastrowid
        cur.execute("UPDATE agents SET user_id = ? WHERE id = ?", (self.user_id, self.agent_id))
        cur.execute(
            """INSERT INTO user_api_settings (user_id, target, api_key, config_json, enabled, updated_at)
               VALUES (?, 'llm', ?, ?, 1, '2026-01-01T00:00:00Z')""",
            (self.user_id, SECRET_KEY,
             json.dumps({"provider": "anthropic", "model": "claude-opus-4-8"})))
        cur.execute(
            """INSERT INTO positions (agent_id, symbol, market, side, quantity, entry_price,
               current_price, stop_loss, take_profit, opened_at)
               VALUES (?, 'BTC', 'crypto', 'long', 0.5, 60000, 63000, 57000, 66000, '2026-07-01T00:00:00Z')""",
            (self.agent_id,))
        cur.execute(
            """INSERT INTO positions (agent_id, symbol, market, side, quantity, entry_price,
               current_price, opened_at)
               VALUES (?, 'ETH', 'crypto', 'short', -2.0, 3000, 2900, '2026-07-02T00:00:00Z')""",
            (self.agent_id,))
        cur.execute(
            """INSERT INTO automation_configs (agent_id, symbol, market, mode, budget_usd,
               interval_minutes, min_confidence, size_usd, auto_execute, account_type, enabled,
               lang, risk_level)
               VALUES (?, 'AGENT', 'crypto', 'agent', 5000, 60, 0.65, 500, 1, 'simulator', 1, 'en', 'balanced')""",
            (self.agent_id,))
        cur.execute(
            """INSERT INTO automation_runs (config_id, agent_id, ran_at, action, confidence,
               executed, skip_reason, confluence_json)
               VALUES (1, ?, '2026-07-17T00:00:00Z', 'buy', 0.72, 0, 'confidence below', ?)""",
            (self.agent_id, json.dumps({"verify": {"verdict": "weakened", "reason": "mixed",
                                                   "mode": "advisory"},
                                        "confluence": {"buy_confluence": 3}})))
        cur.execute(
            """INSERT INTO user_watches (agent_id, name, metric, comparator, threshold,
               enabled, cooldown_min, created_at)
               VALUES (?, 'Extreme fear', 'fear_greed', 'below', 30, 1, 60, '2026-07-01T00:00:00Z')""",
            (self.agent_id,))
        cur.execute(
            """INSERT INTO alert_log (agent_id, user_id, kind, title, body, channels_json, created_at)
               VALUES (?, ?, 'custom', 'Watch: Extreme fear', 'fired', '["inapp"]', '2026-07-17T01:00:00Z')""",
            (self.agent_id, self.user_id))
        # member/support data: membership (seeded 'pro' plan), points, follow, trade
        cur.execute(
            """INSERT INTO user_subscriptions (user_id, plan_code, status, method, amount_usd,
               started_at, expires_at) VALUES (?, 'pro', 'active', 'manual', 49.0,
               '2026-07-01T00:00:00Z', '2026-08-01T00:00:00Z')""", (self.user_id,))
        cur.execute(
            """INSERT INTO points_transactions (user_id, amount, type, description)
               VALUES (?, -100, 'spend', 'Signal boost')""", (self.user_id,))
        cur.execute(
            """INSERT INTO agents (name, cash, points, created_at)
               VALUES ('leader-agent', 100000, 0, '2026-01-01T00:00:00Z')""")
        self.leader_id = cur.lastrowid
        cur.execute(
            """INSERT INTO subscriptions (leader_id, follower_id, status)
               VALUES (?, ?, 'active')""", (self.leader_id, self.agent_id))
        cur.execute(
            """INSERT INTO signals (signal_id, agent_id, message_type, market, signal_type,
               symbol, side, entry_price, quantity, timestamp, executed_at, created_at)
               VALUES (900001, ?, 'operation', 'crypto', 'trade', 'BTC', 'buy', 60000, 0.5,
               1751328000, '2026-07-01T00:00:00Z', '2026-07-01T00:00:00Z')""", (self.agent_id,))
        conn.commit()
        conn.close()

    def tearDown(self):
        self.tmp.cleanup()


class ProfileTests(AssistantTestCase):
    def test_profile_has_everything(self):
        p = assistant.build_user_profile(self.agent_id)
        self.assertEqual(p["identity"]["agent"], "owner")
        self.assertEqual(p["identity"]["email"], "henry@test.io")
        self.assertEqual(len(p["portfolio"]["positions"]), 2)
        self.assertEqual(p["guidelines"], "Never trade weekends.")
        self.assertEqual(len(p["automation_rules"]), 1)
        self.assertEqual(p["automation_rules"][0]["mode"], "agent")
        self.assertEqual(len(p["recent_runs"]), 1)
        self.assertEqual(p["recent_runs"][0]["verify"]["verdict"], "weakened")
        self.assertEqual(p["recent_runs"][0]["buy_confluence"], 3)
        self.assertEqual(len(p["watches"]), 1)
        self.assertEqual(len(p["recent_alerts"]), 1)
        self.assertIn("performance", p)
        self.assertIn("risk_limits", p)
        self.assertIn("breaker", p)

    def test_profile_has_member_support_sections(self):
        """Full member info for support: membership, points, follows, trades."""
        p = assistant.build_user_profile(self.agent_id)
        self.assertEqual(p["membership"]["current"]["plan_code"], "pro")
        self.assertEqual(p["membership"]["current"]["status"], "active")
        self.assertEqual(p["membership"]["current"]["plan_name"], "Pro")
        self.assertEqual(p["recent_points"][0]["amount"], -100)
        self.assertEqual(p["copy_trading"]["following"][0]["leader"], "leader-agent")
        self.assertEqual(p["recent_trades"][0]["symbol"], "BTC")
        self.assertEqual(p["recent_trades"][0]["side"], "buy")

    def test_pnl_math_long_and_short(self):
        p = assistant.build_user_profile(self.agent_id)
        by_symbol = {x["symbol"]: x for x in p["portfolio"]["positions"]}
        # long 0.5 BTC from 60k -> 63k = +1500
        self.assertEqual(by_symbol["BTC"]["side"], "long")
        self.assertAlmostEqual(by_symbol["BTC"]["unrealized_pnl_usd"], 1500.0)
        # short 2 ETH from 3000 -> 2900 = +200 (price fell)
        self.assertEqual(by_symbol["ETH"]["side"], "short")
        self.assertAlmostEqual(by_symbol["ETH"]["unrealized_pnl_usd"], 200.0)
        self.assertAlmostEqual(p["portfolio"]["unrealized_pnl_usd"], 1700.0)
        # deployed = 0.5*63000 + 2*2900
        self.assertAlmostEqual(p["portfolio"]["deployed_usd"], 31500.0 + 5800.0)

    def test_api_key_never_in_profile(self):
        """The assistant learns THAT a key exists, never its value."""
        p = assistant.build_user_profile(self.agent_id)
        blob = json.dumps(p, default=str)
        self.assertNotIn(SECRET_KEY, blob)
        self.assertNotIn("SUPERSECRET", blob)
        self.assertTrue(p["settings"]["llm"]["key_configured"])
        self.assertEqual(p["settings"]["llm"]["provider"], "anthropic")

    def test_profile_endpoint_matches_and_hides_key(self):
        r = self.client.get("/api/assistant/profile", headers=self.headers)
        self.assertEqual(r.status_code, 200)
        self.assertNotIn(SECRET_KEY, r.text)
        self.assertEqual(r.json()["profile"]["identity"]["agent"], "owner")
        self.assertEqual(self.client.get("/api/assistant/profile").status_code, 401)

    def test_profile_is_per_agent(self):
        other = self.client.post("/api/claw/agents/selfRegister",
                                 json={"name": "stranger", "password": "pw123",
                                       "initial_balance": 1000.0}).json()
        p = assistant.build_user_profile(other["agent_id"])
        self.assertEqual(p["identity"]["agent"], "stranger")
        self.assertEqual(p["portfolio"]["positions"], [])
        self.assertNotIn("guidelines", p)


class TurnTests(AssistantTestCase):
    def test_turn_sees_profile_and_persists(self):
        captured = {}

        def fake_gen(prompt, **kw):
            captured["prompt"] = prompt
            captured["system"] = kw.get("system")
            captured["tier"] = kw.get("tier")
            return "You hold BTC long and ETH short; net unrealized +$1,700."

        with patch("llm_client.llm_configured", return_value=True), \
             patch("llm_client.generate_text", side_effect=fake_gen), \
             patch("llm_client.active_provider_model", return_value="claude-sonnet-5"):
            r = self.client.post("/api/assistant/messages", headers=self.headers,
                                 json={"message": "How am I doing?", "lang": "ko"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["llm_model"], "claude-sonnet-5")
        # the prompt carried the account + language, on the assistant tier
        self.assertIn("owner", captured["prompt"])
        self.assertIn("Never trade weekends.", captured["prompt"])
        self.assertIn("USER LANGUAGE: ko", captured["prompt"])
        self.assertIn("never execute", captured["system"])
        self.assertEqual(captured["tier"], "assistant")
        self.assertNotIn(SECRET_KEY, captured["prompt"])   # key never reaches the model
        # persisted
        msgs = self.client.get("/api/assistant", headers=self.headers).json()["messages"]
        self.assertEqual([m["role"] for m in msgs], ["user", "assistant"])

    def test_session_is_singleton_and_persistent(self):
        s1 = self.client.get("/api/assistant", headers=self.headers).json()["session"]
        s2 = self.client.get("/api/assistant", headers=self.headers).json()["session"]
        self.assertEqual(s1["id"], s2["id"])
        self.assertEqual(s1["market"], assistant.ASSISTANT_MARKET)

    def test_assistant_session_hidden_from_consult_list(self):
        """The global assistant must not appear as a consultation session."""
        self.client.get("/api/assistant", headers=self.headers)
        sessions = self.client.get("/api/analysis/chat/sessions",
                                   headers=self.headers).json()["sessions"]
        self.assertTrue(all(s["market"] != assistant.ASSISTANT_MARKET for s in sessions))

    def test_clear_starts_fresh_but_history_is_kept(self):
        """'Clear' now starts a new conversation; the old one is never deleted."""
        with patch("llm_client.llm_configured", return_value=True), \
             patch("llm_client.generate_text", return_value="hi"), \
             patch("llm_client.active_provider_model", return_value="m"):
            self.client.post("/api/assistant/messages", headers=self.headers,
                             json={"message": "hello"})
        old = self.client.get("/api/assistant", headers=self.headers).json()["session"]
        self.assertEqual(self.client.delete("/api/assistant", headers=self.headers).status_code, 200)
        # active conversation is fresh…
        self.assertEqual(self.client.get("/api/assistant", headers=self.headers).json()["messages"], [])
        # …but the old one still exists with its messages intact
        r = self.client.get(f"/api/assistant/sessions/{old['id']}", headers=self.headers)
        self.assertEqual(r.status_code, 200)
        self.assertEqual([m["role"] for m in r.json()["messages"]], ["user", "assistant"])

    def test_history_list_titles_and_counts(self):
        with patch("llm_client.llm_configured", return_value=True), \
             patch("llm_client.generate_text", return_value="hi"), \
             patch("llm_client.active_provider_model", return_value="m"):
            self.client.post("/api/assistant/messages", headers=self.headers,
                             json={"message": "What is my membership status?"})
            self.client.delete("/api/assistant", headers=self.headers)
            self.client.post("/api/assistant/messages", headers=self.headers,
                             json={"message": "Review my risk settings"})
        sessions = self.client.get("/api/assistant/sessions",
                                   headers=self.headers).json()["sessions"]
        self.assertEqual(len(sessions), 2)
        # newest first, titled after the first question, counting both roles
        self.assertEqual(sessions[0]["title"], "Review my risk settings")
        self.assertEqual(sessions[1]["title"], "What is my membership status?")
        self.assertEqual(sessions[0]["message_count"], 2)
        self.assertEqual(sessions[1]["preview"], "What is my membership status?")

    def test_new_session_reuses_empty_current(self):
        """Clearing twice must not pile up blank sessions."""
        self.client.get("/api/assistant", headers=self.headers)
        self.client.delete("/api/assistant", headers=self.headers)
        self.client.delete("/api/assistant", headers=self.headers)
        sessions = self.client.get("/api/assistant/sessions",
                                   headers=self.headers).json()["sessions"]
        self.assertEqual(len(sessions), 1)

    def test_history_is_private_to_the_member(self):
        with patch("llm_client.llm_configured", return_value=True), \
             patch("llm_client.generate_text", return_value="hi"), \
             patch("llm_client.active_provider_model", return_value="m"):
            self.client.post("/api/assistant/messages", headers=self.headers,
                             json={"message": "secret question"})
        mine = self.client.get("/api/assistant", headers=self.headers).json()["session"]
        other = self.client.post(
            "/api/claw/agents/selfRegister",
            json={"name": "intruder", "password": "pw123", "initial_balance": 1000.0}).json()
        other_headers = {"Authorization": f"Bearer {other['token']}"}
        r = self.client.get(f"/api/assistant/sessions/{mine['id']}", headers=other_headers)
        self.assertEqual(r.status_code, 404)
        listed = self.client.get("/api/assistant/sessions", headers=other_headers).json()["sessions"]
        self.assertNotIn(mine["id"], [s["id"] for s in listed])

    def test_no_llm_honest(self):
        with patch.dict(os.environ, _NO_LLM_ENV):
            r = self.client.post("/api/assistant/messages", headers=self.headers,
                                 json={"message": "hi"})
        self.assertFalse(r.json()["available"])
        self.assertIn("unavailable", r.json()["reply"])

    def test_empty_message_and_auth(self):
        r = self.client.post("/api/assistant/messages", headers=self.headers,
                             json={"message": "  "})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.client.get("/api/assistant").status_code, 401)
        self.assertEqual(self.client.post("/api/assistant/messages",
                                          json={"message": "hi"}).status_code, 401)


if __name__ == "__main__":
    unittest.main()
