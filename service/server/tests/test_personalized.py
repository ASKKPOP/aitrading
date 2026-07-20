"""Plan 06 C3 — guidelines injection + alert engine (email/SMS channels mocked)."""

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


class PersonalizedTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())
        # human user + linked agent
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO users (email, password_hash, created_at) VALUES (?, ?, ?)",
                    ("henry@test.io", "x", "2026-01-01T00:00:00Z"))
        self.user_id = cur.lastrowid
        cur.execute("INSERT INTO user_tokens (user_id, token, expires_at) "
                    "VALUES (?, 'utok_test', '2030-01-01 00:00:00')",
                    (self.user_id,))
        from services import _hash_token
        cur.execute(
            "INSERT INTO agents (name, password_hash, token, token_hash, cash, user_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("guided-agent", "x", "claw_guided", _hash_token("claw_guided"),
             100000.0, self.user_id))
        self.agent_id = cur.lastrowid
        conn.commit()
        conn.close()
        self.uauth = {"Authorization": "Bearer utok_test"}
        self.aauth = {"Authorization": "Bearer claw_guided"}

    def tearDown(self):
        self.tmp.cleanup()


class GuidelinesTests(PersonalizedTestCase):
    def test_put_get_roundtrip_and_limit(self):
        r = self.client.put("/api/users/guidelines", headers=self.uauth,
                            json={"guidelines": "Avoid weekends. Prefer BTC."})
        self.assertEqual(r.status_code, 200, r.text)
        g = self.client.get("/api/users/guidelines", headers=self.uauth).json()
        self.assertEqual(g["guidelines"], "Avoid weekends. Prefer BTC.")
        too_long = self.client.put("/api/users/guidelines", headers=self.uauth,
                                   json={"guidelines": "x" * 2001})
        self.assertEqual(too_long.status_code, 400)
        self.assertEqual(self.client.get("/api/users/guidelines").status_code, 401)

    def test_guidelines_for_agent(self):
        from services import guidelines_for_agent
        self.client.put("/api/users/guidelines", headers=self.uauth,
                        json={"guidelines": "Never average down."})
        self.assertEqual(guidelines_for_agent(self.agent_id), "Never average down.")
        self.assertIsNone(guidelines_for_agent(999999))
        self.assertIsNone(guidelines_for_agent(None))

    def test_guidelines_injected_into_trader_prompt(self):
        import analysis_agents
        captured = {}

        def fake_generate(prompt, **kwargs):
            captured.setdefault("prompts", []).append(prompt)
            return '{"action":"hold","confidence":0.5,"rationale":"r","report":"rep"}'

        with patch.object(analysis_agents, "llm_configured", return_value=True), \
             patch.object(analysis_agents, "generate_text", side_effect=fake_generate):
            analysis_agents._trader_risk_decision(
                "BTC", "crypto", {"news": "n", "sentiment": "s",
                                  "fundamentals_macro": "f", "technical": "t"},
                {"current_price": 100.0}, {}, "en",
                guidelines="Never trade on Sundays.")
        self.assertTrue(any("Never trade on Sundays." in p for p in captured["prompts"]))
        self.assertTrue(any("never override risk limits" in p for p in captured["prompts"]))

    def test_no_guidelines_no_block(self):
        from analysis_agents import _guidelines_block
        self.assertEqual(_guidelines_block(None), "")
        self.assertEqual(_guidelines_block(""), "")
        self.assertIn("USER GUIDELINES", _guidelines_block("be careful"))


class AlertEngineTests(PersonalizedTestCase):
    def _set_prefs(self, email=True, sms=False, phone=""):
        self.client.put("/api/users/settings/api/alerts", headers=self.uauth,
                        json={"config": {"email_enabled": str(email),
                                         "sms_enabled": str(sms), "phone": phone}})

    def test_inapp_always_journaled_email_on_optin(self):
        import alerts
        self._set_prefs(email=True)
        with patch.object(alerts, "_send_email", return_value=True) as mock_email, \
             patch.object(alerts, "_send_sms", return_value=True) as mock_sms:
            out = alerts.send_alert(self.agent_id, "trade_executed", "BUY BTC", "test body")
        self.assertIn("inapp", out["channels"])
        self.assertIn("email", out["channels"])
        self.assertNotIn("sms", out["channels"])
        mock_email.assert_called_once()
        mock_sms.assert_not_called()
        feed = self.client.get("/api/alerts", headers=self.aauth).json()["alerts"]
        self.assertEqual(len(feed), 1)
        self.assertEqual(feed[0]["kind"], "trade_executed")

    def test_sms_channel_with_phone(self):
        # Plan 10 D9: SMS is tier-gated inside the send path. Without a
        # qualifying plan the switch+phone alone no longer produce SMS.
        import alerts
        self._set_prefs(email=False, sms=True, phone="+821012345678")
        with patch.object(alerts, "_send_sms", return_value=True) as mock_sms:
            out = alerts.send_alert(self.agent_id, "breaker", "HALT", "b")
        self.assertNotIn("sms", out["channels"])
        mock_sms.assert_not_called()
        with patch.object(alerts, "_send_sms", return_value=True) as mock_sms, \
                patch("entitlements.plan_code_for_user", return_value="professional"):
            out = alerts.send_alert(self.agent_id, "breaker", "HALT-2", "b2")
        self.assertIn("sms", out["channels"])
        self.assertEqual(mock_sms.call_args[0][0], "+821012345678")

    def test_default_category_reaches_email_without_optin(self):
        # One switch per category (notifications.py): a category left at its
        # default ON delivers everywhere, so there is no in-app-only state.
        import alerts
        with patch.object(alerts, "_send_email", return_value=True) as mock_email:
            out = alerts.send_alert(self.agent_id, "custom", "t", "b")
        self.assertIn("inapp", out["channels"])
        self.assertIn("email", out["channels"])
        mock_email.assert_called_once()

    def test_category_switched_off_delivers_nothing(self):
        import alerts
        import notifications
        notifications.set_prefs(self.user_id, {"watch": {"enabled": False}})
        with patch.object(alerts, "_send_email", return_value=True) as mock_email:
            out = alerts.send_alert(self.agent_id, "custom", "t", "b")
        self.assertNotIn("email", out["channels"])
        mock_email.assert_not_called()

    def test_dedupe_within_hour(self):
        import alerts
        alerts.send_alert(self.agent_id, "custom", "t", "b", dedupe_key="k1")
        out = alerts.send_alert(self.agent_id, "custom", "t", "b", dedupe_key="k1")
        self.assertEqual(out.get("skipped"), "duplicate")
        feed = self.client.get("/api/alerts", headers=self.aauth).json()["alerts"]
        self.assertEqual(len(feed), 1)

    def test_rate_limit_downgrades_to_inapp(self):
        import alerts
        self._set_prefs(email=True)
        with patch.object(alerts, "_send_email", return_value=True), \
             patch.object(alerts, "RATE_LIMIT_PER_HOUR", 2):
            alerts.send_alert(self.agent_id, "custom", "1", "b")
            alerts.send_alert(self.agent_id, "custom", "2", "b")
            out = alerts.send_alert(self.agent_id, "custom", "3", "b")
        self.assertEqual(out["channels"], ["inapp"])
        self.assertTrue(out["rate_limited"])

    def test_send_alert_fail_soft(self):
        import alerts
        self._set_prefs(email=True)
        with patch.object(alerts, "_send_email", side_effect=OSError("smtp down")):
            out = alerts.send_alert(self.agent_id, "custom", "t", "b")
        self.assertEqual(out["channels"], ["inapp"])  # journaled despite email failure


if __name__ == "__main__":
    unittest.main()
