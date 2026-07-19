"""Plan 06 Phase I — user LLM settings bridge, model tiering, verification pass."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import llm_client
from llm_client import LlmContext, reset_llm_context, resolve_provider, set_llm_context

_NO_LLM_ENV = {k: "" for k in (
    "LLM_PROVIDER", "LLM_MODEL", "LLM_MODEL_BRIEF", "LLM_MODEL_DECISION",
    "OPENAI_API_KEY", "GEMINI_API_KEY", "XAI_API_KEY", "GROK_API_KEY",
    "DASHSCOPE_API_KEY", "QWEN_API_KEY", "GLM_API_KEY", "ZHIPUAI_API_KEY",
    "OPENROUTER_API_KEY", "ANTHROPIC_API_KEY", "LOCAL_LLM_API_KEY",
    "VERIFY_PROVIDER",
)}


class ContextResolutionTests(unittest.TestCase):
    def setUp(self):
        self._patch = patch.dict(os.environ, _NO_LLM_ENV)
        self._patch.start()

    def tearDown(self):
        self._patch.stop()

    def test_no_keys_no_context_resolves_none(self):
        self.assertIsNone(resolve_provider())

    def test_user_key_enables_provider_without_env(self):
        token = set_llm_context(LlmContext(provider="anthropic", model=None,
                                           api_key="sk-user-123", source="user"))
        try:
            ap = resolve_provider()
            self.assertIsNotNone(ap)
            self.assertEqual(ap.spec.name, "anthropic")
            self.assertEqual(ap.api_key, "sk-user-123")
            self.assertEqual(ap.source, "user")
        finally:
            reset_llm_context(token)

    def test_user_model_beats_tier_default(self):
        token = set_llm_context(LlmContext(provider="anthropic", model="claude-opus-4-8",
                                           api_key="sk-user-123", source="user"))
        try:
            self.assertEqual(resolve_provider(tier="brief").model, "claude-opus-4-8")
            self.assertEqual(resolve_provider(tier="decision").model, "claude-opus-4-8")
        finally:
            reset_llm_context(token)

    def test_user_key_not_applied_to_other_provider(self):
        # Rule picks openai; user's anthropic key must not leak into it.
        token = set_llm_context(LlmContext(provider="openai", model=None,
                                           api_key="sk-anthropic-key", source="rule"))
        try:
            # context key applies because ctx.provider == spec (openai); this is
            # the rule-context path. Now simulate the merge guard instead:
            ap = resolve_provider()
            self.assertEqual(ap.spec.name, "openai")
        finally:
            reset_llm_context(token)
        # The merge guard lives in run_analysis: differing rule provider drops
        # the user's key entirely.
        from analysis_agents import run_analysis  # noqa: F401 — merge tested below

    def test_env_provider_still_works(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-env"}):
            ap = resolve_provider()
            self.assertEqual(ap.spec.name, "openai") if False else None
            # auto-detect order: openai first but no key; anthropic has one
            self.assertEqual(ap.spec.name, "anthropic")
            self.assertEqual(ap.api_key, "sk-env")
            self.assertEqual(ap.source, "auto")


class TierModelTests(unittest.TestCase):
    def setUp(self):
        self._patch = patch.dict(os.environ, {**_NO_LLM_ENV, "ANTHROPIC_API_KEY": "sk-env"})
        self._patch.start()

    def tearDown(self):
        self._patch.stop()

    def test_anthropic_tiers(self):
        """Sonnet + Opus. Briefs feed the trader, so the cheap tier is not a
        saving if it misreads the data (measured: Haiku did, 4/4)."""
        self.assertEqual(resolve_provider(tier="brief").model, "claude-sonnet-5")
        self.assertEqual(resolve_provider(tier="decision").model, "claude-opus-4-8")

    def test_llm_model_overrides_both_tiers(self):
        with patch.dict(os.environ, {"LLM_MODEL": "claude-opus-4-8"}):
            self.assertEqual(resolve_provider(tier="brief").model, "claude-opus-4-8")
            self.assertEqual(resolve_provider(tier="decision").model, "claude-opus-4-8")

    def test_tier_env_overrides_one_tier(self):
        with patch.dict(os.environ, {"LLM_MODEL_BRIEF": "claude-3-5-haiku-latest"}):
            self.assertEqual(resolve_provider(tier="brief").model, "claude-3-5-haiku-latest")
            self.assertEqual(resolve_provider(tier="decision").model, "claude-opus-4-8")

    def test_openai_tiers(self):
        with patch.dict(os.environ, {**_NO_LLM_ENV, "OPENAI_API_KEY": "sk-oai"}):
            self.assertEqual(resolve_provider(tier="brief").model, "gpt-4o-mini")
            self.assertEqual(resolve_provider(tier="decision").model, "gpt-4o")


class UserSettingsBridgeTests(unittest.TestCase):
    """llm_context_for_agent reads the owning user's stored 'llm' settings."""

    def setUp(self):
        import database
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        from database import get_db_connection
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO users (email, password_hash, created_at) VALUES (?, ?, ?)",
                    ("henry@test.io", "x", "2026-01-01T00:00:00Z"))
        self.user_id = cur.lastrowid
        cur.execute(
            "INSERT INTO agents (name, password_hash, token, cash, user_id) VALUES (?, ?, ?, ?, ?)",
            ("bridge-agent", "x", "claw_test_bridge", 1000.0, self.user_id))
        self.agent_id = cur.lastrowid
        cur.execute(
            """INSERT INTO user_api_settings (user_id, target, api_key, config_json, enabled, updated_at)
               VALUES (?, 'llm', 'sk-user-abc', '{"provider": "anthropic", "model": "claude-sonnet-5"}', 1, '2026-01-01T00:00:00Z')""",
            (self.user_id,))
        conn.commit()
        conn.close()

    def tearDown(self):
        self.tmp.cleanup()

    def test_bridge_returns_user_context(self):
        from services import llm_context_for_agent
        ctx = llm_context_for_agent(self.agent_id)
        self.assertIsNotNone(ctx)
        self.assertEqual(ctx.provider, "anthropic")
        self.assertEqual(ctx.model, "claude-sonnet-5")
        self.assertEqual(ctx.api_key, "sk-user-abc")
        self.assertEqual(ctx.source, "user")

    def test_bridge_none_for_unknown_or_unlinked_agent(self):
        from services import llm_context_for_agent
        self.assertIsNone(llm_context_for_agent(None))
        self.assertIsNone(llm_context_for_agent(999999))

    def test_disabled_setting_ignored(self):
        from database import get_db_connection
        conn = get_db_connection()
        conn.execute("UPDATE user_api_settings SET enabled = 0 WHERE user_id = ?", (self.user_id,))
        conn.commit()
        conn.close()
        from services import llm_context_for_agent
        self.assertIsNone(llm_context_for_agent(self.agent_id))

    def test_run_analysis_uses_user_key(self):
        """End-to-end: run_analysis with agent_id resolves the user context so
        llm resolution inside the run sees the user's key (no env keys set)."""
        import analysis_agents
        seen = {}

        def fake_inner(symbol, market, lang, **kwargs):
            ap = resolve_provider()
            seen["provider"] = ap.spec.name if ap else None
            seen["key"] = ap.api_key if ap else None
            seen["source"] = ap.source if ap else None
            return {"decision": {"action": "hold", "confidence": 0.5}}

        with patch.dict(os.environ, _NO_LLM_ENV), \
             patch.object(analysis_agents, "_run_analysis_inner", side_effect=fake_inner):
            analysis_agents.run_analysis("BTC", "crypto", "en", agent_id=self.agent_id)
        self.assertEqual(seen["provider"], "anthropic")
        self.assertEqual(seen["key"], "sk-user-abc")
        self.assertEqual(seen["source"], "user")

    def test_rule_provider_mismatch_drops_user_key(self):
        import analysis_agents
        seen = {}

        def fake_inner(symbol, market, lang, **kwargs):
            ap = resolve_provider()
            seen["resolved"] = ap  # None expected: gemini has no key anywhere
            return {"decision": {"action": "hold", "confidence": 0.5}}

        with patch.dict(os.environ, _NO_LLM_ENV), \
             patch.object(analysis_agents, "_run_analysis_inner", side_effect=fake_inner):
            analysis_agents.run_analysis("BTC", "crypto", "en",
                                         provider="gemini", agent_id=self.agent_id)
        self.assertIsNone(seen["resolved"])


class VerificationTests(unittest.TestCase):
    def setUp(self):
        self._patch = patch.dict(os.environ, _NO_LLM_ENV)
        self._patch.start()

    def tearDown(self):
        self._patch.stop()

    def test_parse_verification(self):
        from analysis_agents import _parse_verification_json
        ok = _parse_verification_json('{"verdict":"weakened","adjusted_confidence":0.4,"reason":"mixed"}')
        self.assertEqual(ok["verdict"], "weakened")
        self.assertEqual(ok["adjusted_confidence"], 0.4)
        self.assertIsNone(_parse_verification_json('{"verdict":"nonsense"}'))
        self.assertIsNone(_parse_verification_json("no json"))
        clamped = _parse_verification_json('{"verdict":"upheld","adjusted_confidence":7}')
        self.assertEqual(clamped["adjusted_confidence"], 1.0)

    def test_advisory_attaches_but_does_not_change(self):
        from analysis_agents import _apply_verification
        decision = {"action": "buy", "confidence": 0.8}
        v = {"verdict": "rejected", "adjusted_confidence": 0.2, "reason": "r"}
        with patch.dict(os.environ, {"VERIFY_ENABLED": "advisory"}):
            out = _apply_verification(decision, v)
        self.assertEqual(out["action"], "buy")
        self.assertEqual(out["confidence"], 0.8)
        self.assertEqual(out["verification"]["verdict"], "rejected")
        self.assertFalse(out["verification"]["applied"])

    def test_enforce_rejected_forces_hold(self):
        from analysis_agents import _apply_verification
        decision = {"action": "buy", "confidence": 0.8}
        v = {"verdict": "rejected", "adjusted_confidence": 0.2, "reason": "r"}
        with patch.dict(os.environ, {"VERIFY_ENABLED": "enforce"}):
            out = _apply_verification(decision, v)
        self.assertEqual(out["action"], "hold")
        self.assertEqual(out["confidence"], 0.2)
        self.assertTrue(out["verification"]["applied"])

    def test_enforce_weakened_lowers_confidence_only(self):
        from analysis_agents import _apply_verification
        decision = {"action": "sell", "confidence": 0.9}
        v = {"verdict": "weakened", "adjusted_confidence": 0.55, "reason": "r"}
        with patch.dict(os.environ, {"VERIFY_ENABLED": "enforce"}):
            out = _apply_verification(decision, v)
        self.assertEqual(out["action"], "sell")
        self.assertEqual(out["confidence"], 0.55)

    def test_fail_open_no_verification(self):
        from analysis_agents import _apply_verification
        decision = {"action": "buy", "confidence": 0.7}
        out = _apply_verification(decision, None)
        self.assertEqual(out, {"action": "buy", "confidence": 0.7})
        self.assertNotIn("verification", out)

    def test_verify_skipped_when_off_or_unconfigured(self):
        from analysis_agents import _verify_decision
        with patch.dict(os.environ, {"VERIFY_ENABLED": "off"}):
            self.assertIsNone(_verify_decision("BTC", "crypto", {}, {}, {}, "en"))
        # no provider configured -> None even in advisory
        with patch.dict(os.environ, {"VERIFY_ENABLED": "advisory"}):
            self.assertIsNone(_verify_decision("BTC", "crypto", {}, {}, {}, "en"))

    def test_verify_mode_default_advisory(self):
        from analysis_agents import _verify_mode
        self.assertEqual(_verify_mode(), "advisory")
        with patch.dict(os.environ, {"VERIFY_ENABLED": "bogus"}):
            self.assertEqual(_verify_mode(), "advisory")


if __name__ == "__main__":
    unittest.main()


class AnthropicTemperatureRetryTests(unittest.TestCase):
    """Claude 5-family models reject `temperature`; the client retries without
    it, and REMEMBERS — retrying on every call cost a wasted round-trip each
    time (prod logs: 400s and 200s exactly 1:1, ~2x latency on a 20s+ path)."""

    def setUp(self):
        llm_client._NO_TEMPERATURE_MODELS.clear()

    def tearDown(self):
        llm_client._NO_TEMPERATURE_MODELS.clear()

    def _run(self, first_error: str | None):
        import types
        calls = []

        class FakeBadRequestError(Exception):
            pass

        class FakeMessages:
            def create(self, **kwargs):
                calls.append(kwargs)
                if "temperature" in kwargs and first_error:
                    raise FakeBadRequestError(first_error)
                block = types.SimpleNamespace(type="text", text="ok")
                return types.SimpleNamespace(content=[block])

        class FakeClient:
            def __init__(self, api_key, base_url=None):
                self.messages = FakeMessages()

        fake_mod = types.SimpleNamespace(Anthropic=FakeClient, BadRequestError=FakeBadRequestError)
        from llm_client import _generate_anthropic, ActiveProvider, _PROVIDERS
        ap = ActiveProvider(spec=_PROVIDERS["anthropic"], api_key="k",
                            base_url="https://api.anthropic.com", model="claude-sonnet-5")
        with patch.dict(sys.modules, {"anthropic": fake_mod}):
            out = _generate_anthropic(ap, "hi", None, 100, 0.3)
        return out, calls

    def test_client_gets_the_resolved_base_url(self):
        """The SDK reads ANTHROPIC_BASE_URL from the process env on its own, so a
        stray export in the launching shell would silently redirect every call.
        Passing the resolved base_url explicitly is what keeps ap.base_url
        authoritative — this pins that it is actually handed to the client."""
        import types
        seen = {}

        class FakeBadRequestError(Exception):
            pass

        class FakeMessages:
            def create(self, **kwargs):
                block = types.SimpleNamespace(type="text", text="ok")
                return types.SimpleNamespace(content=[block])

        class FakeClient:
            def __init__(self, api_key, base_url=None):
                seen["base_url"] = base_url
                self.messages = FakeMessages()

        fake_mod = types.SimpleNamespace(Anthropic=FakeClient,
                                         BadRequestError=FakeBadRequestError)
        from llm_client import _generate_anthropic, ActiveProvider, _PROVIDERS
        ap = ActiveProvider(spec=_PROVIDERS["anthropic"], api_key="k",
                            base_url="https://resolved.example.com",
                            model="claude-sonnet-5")
        with patch.dict(sys.modules, {"anthropic": fake_mod}):
            _generate_anthropic(ap, "hi", None, 100, 0.3)
        self.assertEqual(seen["base_url"], "https://resolved.example.com")

    # The generators return (text, (prompt_tokens, completion_tokens)) since
    # usage metering landed (Plan 11 F2); a stub response with no usage object
    # meters as zeros.
    def test_retries_without_temperature(self):
        (text, usage), calls = self._run("`temperature` is deprecated for this model.")
        self.assertEqual(text, "ok")
        self.assertEqual(usage, (0, 0))
        self.assertEqual(len(calls), 2)
        self.assertIn("temperature", calls[0])
        self.assertNotIn("temperature", calls[1])

    def test_no_retry_when_accepted(self):
        (text, usage), calls = self._run(None)
        self.assertEqual(text, "ok")
        self.assertEqual(usage, (0, 0))
        self.assertEqual(len(calls), 1)

    def test_other_errors_propagate(self):
        with self.assertRaises(Exception) as cm:
            self._run("model not found")
        self.assertIn("model not found", str(cm.exception))

    def test_the_refusal_is_remembered_so_the_next_call_costs_one_trip(self):
        """The whole point: learn once, not once per request."""
        _, first = self._run("`temperature` is deprecated for this model.")
        self.assertEqual(len(first), 2)          # learns on the first call
        _, second = self._run("`temperature` is deprecated for this model.")
        self.assertEqual(len(second), 1)         # and never asks again
        self.assertNotIn("temperature", second[0])

    def test_memory_is_per_model_not_global(self):
        """A model that accepts temperature must not be penalised by one that
        does not."""
        import types
        llm_client._NO_TEMPERATURE_MODELS.add("claude-sonnet-5")
        calls = []

        class FakeBadRequestError(Exception):
            pass

        class FakeMessages:
            def create(self, **kwargs):
                calls.append(kwargs)
                block = types.SimpleNamespace(type="text", text="ok")
                return types.SimpleNamespace(content=[block])

        class FakeClient:
            def __init__(self, api_key, base_url=None):
                self.messages = FakeMessages()

        fake_mod = types.SimpleNamespace(Anthropic=FakeClient, BadRequestError=FakeBadRequestError)
        from llm_client import _generate_anthropic, ActiveProvider, _PROVIDERS
        ap = ActiveProvider(spec=_PROVIDERS["anthropic"], api_key="k",
                            base_url="https://api.anthropic.com", model="some-other-model")
        with patch.dict(sys.modules, {"anthropic": fake_mod}):
            _generate_anthropic(ap, "hi", None, 100, 0.3)
        self.assertIn("temperature", calls[0])   # unknown model still tries
