"""User-owned LLM calls require the user's own AI setting.

Owner policy (2026-07-31): system-level calls run on the admin console AI;
a user who configured AI in Settings runs on that; a user WITHOUT an AI
setting is not supported — their calls resolve to no provider instead of
falling back to the platform admin/env AI. The user-facing assistant tier
is exempt and stays on the platform default.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
import llm_client
from llm_client import LlmContext, reset_llm_context, resolve_provider, set_llm_context


class UserAiRequired(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self._saved_env = {}
        for k in ("LLM_PROVIDER", "LLM_MODEL", "ANTHROPIC_API_KEY",
                  "LOCAL_LLM_BASE_URL", "LOCAL_LLM_MODEL"):
            self._saved_env[k] = os.environ.pop(k, None)
        os.environ["ANTHROPIC_API_KEY"] = "test-key"
        from platform_settings import set_setting
        for tier in ("brief", "decision"):
            set_setting(f"llm_{tier}_provider", "local")
            set_setting(f"llm_{tier}_model", "gpt-oss:20b")
        llm_client.invalidate_admin_llm_settings_cache()

    def tearDown(self):
        for k, v in self._saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        llm_client.invalidate_admin_llm_settings_cache()
        self.tmp.cleanup()

    def _resolve(self, ctx, tier):
        token = set_llm_context(ctx)
        try:
            return resolve_provider(tier=tier)
        finally:
            reset_llm_context(token)

    def test_unconfigured_user_gets_no_provider(self):
        """A user-owned call with no user provider must NOT fall back to the
        admin console AI or the env key chain."""
        ctx = LlmContext(source="rule", user_id=42, agent_id=7)
        for tier in ("brief", "decision"):
            assert self._resolve(ctx, tier) is None, tier

    def test_agent_only_context_is_user_owned(self):
        ctx = LlmContext(source="rule", agent_id=7)
        assert self._resolve(ctx, "decision") is None

    def test_configured_user_runs_their_ai(self):
        ctx = LlmContext(provider="anthropic", api_key="sk-user", source="user",
                         user_id=42, agent_id=7)
        ap = self._resolve(ctx, "decision")
        assert ap is not None and ap.spec.name == "anthropic"
        assert ap.api_key == "sk-user"

    def test_run_llm_tiers_still_apply(self):
        """Run-config llm_tiers is explicit owner config; a listed tier works,
        an unlisted tier still refuses the platform fallback."""
        ctx = LlmContext(source="rule", user_id=42, agent_id=7,
                         tier_providers={"brief": {"provider": "local",
                                                   "model": "gpt-oss:20b"}})
        ap = self._resolve(ctx, "brief")
        assert ap is not None and ap.spec.name == "local"
        assert self._resolve(ctx, "decision") is None

    def test_assistant_tier_stays_on_platform_default(self):
        ctx = LlmContext(source="user", user_id=42)
        ap = self._resolve(ctx, "assistant")
        assert ap is not None  # platform env anthropic key

    def test_system_calls_unaffected(self):
        """No user identity in context -> admin console AI as before."""
        ap = resolve_provider(tier="brief")
        assert ap is not None and ap.spec.name == "local"
        assert ap.model == "gpt-oss:20b"


if __name__ == "__main__":
    unittest.main()
