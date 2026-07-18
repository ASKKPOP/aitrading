"""Plan 06 C3 — consultation chat + rule handoff (LLM mocked; no live calls)."""

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

import consult
import database
from routes import create_app

_NO_LLM_ENV = {k: "" for k in (
    "LLM_PROVIDER", "LLM_MODEL", "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY", "XAI_API_KEY", "GROK_API_KEY", "DASHSCOPE_API_KEY",
    "QWEN_API_KEY", "GLM_API_KEY", "ZHIPUAI_API_KEY", "OPENROUTER_API_KEY",
)}


class ConsultTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())
        body = self.client.post(
            "/api/claw/agents/selfRegister",
            json={"name": "consultee", "password": "pw123", "initial_balance": 100000.0}).json()
        self.agent_id = body["agent_id"]
        self.token = body["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def tearDown(self):
        self.tmp.cleanup()

    def _session(self, symbol="BTCUSDT"):
        r = self.client.post("/api/analysis/chat/sessions", headers=self.headers,
                             json={"symbol": symbol, "market": "crypto"})
        return r.json()["id"]


class SessionTests(ConsultTestCase):
    def test_create_read_list_delete(self):
        sid = self._session()
        r = self.client.get(f"/api/analysis/chat/sessions/{sid}", headers=self.headers)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["session"]["symbol"], "BTCUSDT")
        self.assertEqual(r.json()["messages"], [])
        listed = self.client.get("/api/analysis/chat/sessions", headers=self.headers).json()
        self.assertEqual(len(listed["sessions"]), 1)
        self.assertEqual(self.client.delete(f"/api/analysis/chat/sessions/{sid}",
                                            headers=self.headers).status_code, 200)
        self.assertEqual(self.client.get(f"/api/analysis/chat/sessions/{sid}",
                                         headers=self.headers).status_code, 404)

    def test_auth_and_isolation(self):
        sid = self._session()
        self.assertEqual(self.client.get("/api/analysis/chat/sessions").status_code, 401)
        other = self.client.post("/api/claw/agents/selfRegister",
                                 json={"name": "other", "password": "pw123",
                                       "initial_balance": 1000.0}).json()
        oh = {"Authorization": f"Bearer {other['token']}"}
        # another agent cannot read or delete my session
        self.assertEqual(self.client.get(f"/api/analysis/chat/sessions/{sid}", headers=oh).status_code, 404)
        self.assertEqual(self.client.delete(f"/api/analysis/chat/sessions/{sid}", headers=oh).status_code, 404)
        self.assertEqual(self.client.get("/api/analysis/chat/sessions", headers=oh).json()["sessions"], [])

    def test_bad_market_rejected(self):
        r = self.client.post("/api/analysis/chat/sessions", headers=self.headers,
                             json={"symbol": "BTC", "market": "forex"})
        self.assertEqual(r.status_code, 400)


class ChatTurnTests(ConsultTestCase):
    def test_turn_persists_both_sides(self):
        sid = self._session()
        with patch.object(consult, "build_context", return_value={"quant": {"rsi": 55}}), \
             patch("llm_client.llm_configured", return_value=True), \
             patch("llm_client.generate_text", return_value="RSI is neutral; I'd wait."), \
             patch("llm_client.active_provider_model", return_value="claude-opus-4-8"):
            r = self.client.post(f"/api/analysis/chat/sessions/{sid}/messages",
                                 headers=self.headers, json={"message": "Should I buy BTC?"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["llm_model"], "claude-opus-4-8")
        msgs = self.client.get(f"/api/analysis/chat/sessions/{sid}",
                               headers=self.headers).json()["messages"]
        self.assertEqual([m["role"] for m in msgs], ["user", "assistant"])
        self.assertEqual(msgs[0]["content"], "Should I buy BTC?")
        self.assertIn("RSI is neutral", msgs[1]["content"])

    def test_history_and_guidelines_in_prompt(self):
        sid = self._session()
        captured = {}

        def fake_gen(prompt, **kw):
            captured["prompt"] = prompt
            captured["system"] = kw.get("system")
            captured["tier"] = kw.get("tier")
            return "noted"

        with patch.object(consult, "build_context", return_value={}), \
             patch.object(consult, "guidelines_for_agent", create=True), \
             patch("services.guidelines_for_agent", return_value="Never trade weekends."), \
             patch("llm_client.llm_configured", return_value=True), \
             patch("llm_client.generate_text", side_effect=fake_gen), \
             patch("llm_client.active_provider_model", return_value="m"):
            self.client.post(f"/api/analysis/chat/sessions/{sid}/messages",
                             headers=self.headers, json={"message": "first"})
            self.client.post(f"/api/analysis/chat/sessions/{sid}/messages",
                             headers=self.headers, json={"message": "second"})
        self.assertIn("Never trade weekends.", captured["prompt"])
        self.assertIn("USER: first", captured["prompt"])       # history carried
        self.assertIn("USER: second", captured["prompt"])      # this turn
        self.assertIn("never execute", captured["system"])     # advisory boundary
        self.assertEqual(captured["tier"], "decision")         # strong tier

    def test_no_llm_reports_unavailable_honestly(self):
        sid = self._session()
        with patch.dict(os.environ, _NO_LLM_ENV):
            r = self.client.post(f"/api/analysis/chat/sessions/{sid}/messages",
                                 headers=self.headers, json={"message": "hi"})
        body = r.json()
        self.assertFalse(body["available"])
        self.assertIsNone(body["llm_model"])
        self.assertIn("unavailable", body["reply"])

    def test_empty_message_rejected(self):
        sid = self._session()
        r = self.client.post(f"/api/analysis/chat/sessions/{sid}/messages",
                             headers=self.headers, json={"message": "   "})
        self.assertEqual(r.status_code, 400)

    def test_session_404_for_unknown(self):
        r = self.client.post("/api/analysis/chat/sessions/99999/messages",
                             headers=self.headers, json={"message": "hi"})
        self.assertEqual(r.status_code, 404)


class ProposeRuleTests(ConsultTestCase):
    def _seed_conversation(self, sid):
        with patch.object(consult, "build_context", return_value={}), \
             patch("llm_client.llm_configured", return_value=True), \
             patch("llm_client.generate_text", return_value="ok"), \
             patch("llm_client.active_provider_model", return_value="m"):
            self.client.post(f"/api/analysis/chat/sessions/{sid}/messages",
                             headers=self.headers, json={"message": "cautious BTC plan please"})

    def test_draft_is_clamped(self):
        sid = self._session()
        self._seed_conversation(sid)
        wild = json.dumps({"symbol": "btcusdt", "market": "forex", "interval_minutes": 1,
                           "min_confidence": 0.05, "size_usd": 9_999_999,
                           "risk_level": "yolo", "rationale": "moon"})
        with patch("llm_client.llm_configured", return_value=True), \
             patch("llm_client.generate_text", return_value=wild):
            r = self.client.post(f"/api/analysis/chat/sessions/{sid}/propose-rule",
                                 headers=self.headers)
        d = r.json()["draft"]
        self.assertEqual(d["symbol"], "BTCUSDT")
        self.assertEqual(d["market"], "crypto")          # invalid market -> crypto
        self.assertEqual(d["interval_minutes"], 15)      # clamped to floor
        self.assertEqual(d["min_confidence"], 0.55)      # clamped to floor
        self.assertEqual(d["size_usd"], 10000.0)         # clamped to ceiling
        self.assertEqual(d["risk_level"], "balanced")    # invalid -> default
        self.assertFalse(d["auto_execute"])              # never pre-armed
        self.assertEqual(d["account_type"], "simulator")

    def test_draft_creates_nothing(self):
        sid = self._session()
        self._seed_conversation(sid)
        good = json.dumps({"symbol": "ETHUSDT", "market": "crypto", "interval_minutes": 120,
                           "min_confidence": 0.7, "size_usd": 300,
                           "risk_level": "stable", "rationale": "cautious"})
        with patch("llm_client.llm_configured", return_value=True), \
             patch("llm_client.generate_text", return_value=good):
            r = self.client.post(f"/api/analysis/chat/sessions/{sid}/propose-rule",
                                 headers=self.headers)
        self.assertEqual(r.json()["draft"]["interval_minutes"], 120)
        # the proposal must NOT have created an automation rule
        rules = self.client.get("/api/automation/configs", headers=self.headers).json()["configs"]
        self.assertEqual(rules, [])

    def test_no_llm_returns_503(self):
        sid = self._session()
        with patch.dict(os.environ, _NO_LLM_ENV):
            r = self.client.post(f"/api/analysis/chat/sessions/{sid}/propose-rule",
                                 headers=self.headers)
        self.assertEqual(r.status_code, 503)

    def test_unparseable_returns_503(self):
        sid = self._session()
        self._seed_conversation(sid)
        with patch("llm_client.llm_configured", return_value=True), \
             patch("llm_client.generate_text", return_value="I cannot do that"):
            r = self.client.post(f"/api/analysis/chat/sessions/{sid}/propose-rule",
                                 headers=self.headers)
        self.assertEqual(r.status_code, 503)


if __name__ == "__main__":
    unittest.main()


class ContextQuantWiringTests(ConsultTestCase):
    """build_context must pull the field quant_crypto actually emits.

    It asked for "rsi"; build_crypto_analysis emits "rsi_14", so the advisor
    was handed rsi=None on every crypto consult.
    """

    FAKE_ANALYSIS = {
        "current_price": 64000.0, "rsi_14": 61.5, "signal": "buy", "signal_score": 2,
        "sigma_daily_pct": 2.1, "funding_rate": 0.0001, "basis_pct": 0.3,
    }

    def test_rsi_reaches_the_advisor(self):
        with patch("quant_crypto.quant_crypto_enabled", return_value=True), \
             patch("quant_crypto.build_crypto_analysis", return_value=self.FAKE_ANALYSIS):
            ctx = consult.build_context(self.agent_id, "BTCUSDT", "crypto")
        quant = ctx.get("quant") or {}
        self.assertEqual(quant.get("rsi_14"), 61.5)
        self.assertNotIn(None, [quant.get("current_price"), quant.get("signal")])

    def test_every_requested_quant_key_exists_upstream(self):
        """Guard against re-introducing a name that quant_crypto never emits."""
        with patch("quant_crypto.quant_crypto_enabled", return_value=True), \
             patch("quant_crypto.build_crypto_analysis", return_value=self.FAKE_ANALYSIS):
            ctx = consult.build_context(self.agent_id, "BTCUSDT", "crypto")
        quant = ctx.get("quant") or {}
        missing = [k for k, v in quant.items() if v is None]
        self.assertEqual(missing, [], f"context keys absent from quant_crypto: {missing}")
