"""Which AI a call runs on, by owner policy.

**Owner policy 2026-08-12 REPLACES the 2026-07-31 rule this file used to pin.**

  > "user doesn't set LLM then use default local AI by system .env setting;
  >  user set LLM then all AI by set LLM"

So an unconfigured user now FALLS BACK to the platform default (admin console,
then env) instead of resolving to None. The three tests below that asserted
None were inverted on 2026-08-12; the rest are unchanged, because the
"configured user wins" half of the policy did not change.

Why it was reversed: the old rule made an ABSENT LlmContext load-bearing.
`run_engine.run_cycle` deliberately set none, and #395 — which set one purely
to record which member the spend belonged to — flipped every fleet cycle onto
the "unconfigured user" path and silenced the desk (`"llm": {}`, forced hold
at confidence 0.0) until it was reverted in 7d09628d.

Cost note, since the old rule existed to prevent this: an unconfigured user's
calls now land on whatever the platform default is. That is free only while
`llm_brief_provider`/`llm_decision_provider` are `local`. Flipping either to a
paid provider spends platform keys on every unconfigured member.

Broader coverage of the new policy lives in test_llm_default_fallback.py.
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

    def test_unconfigured_user_falls_back_to_the_platform_default(self):
        """2026-08-12: a user-owned call with no user provider DOES fall back
        to the admin console AI. Was `is None` under the 2026-07-31 rule."""
        ctx = LlmContext(source="rule", user_id=42, agent_id=7)
        for tier in ("brief", "decision"):
            ap = self._resolve(ctx, tier)
            assert ap is not None, tier
            assert ap.spec.name == "local", tier

    def test_agent_only_context_also_falls_back(self):
        ctx = LlmContext(source="rule", agent_id=7)
        ap = self._resolve(ctx, "decision")
        assert ap is not None and ap.spec.name == "local"

    def test_configured_user_runs_their_ai(self):
        ctx = LlmContext(provider="anthropic", api_key="sk-user", source="user",
                         user_id=42, agent_id=7)
        ap = self._resolve(ctx, "decision")
        assert ap is not None and ap.spec.name == "anthropic"
        assert ap.api_key == "sk-user"

    def test_run_llm_tiers_still_apply(self):
        """Run-config llm_tiers is explicit owner config and still wins for the
        tiers it lists. 2026-08-12: an UNLISTED tier now takes the platform
        default rather than refusing (it asserted `is None` before)."""
        ctx = LlmContext(source="rule", user_id=42, agent_id=7,
                         tier_providers={"brief": {"provider": "local",
                                                   "model": "gpt-oss:20b"}})
        ap = self._resolve(ctx, "brief")
        assert ap is not None and ap.spec.name == "local"
        unlisted = self._resolve(ctx, "decision")
        assert unlisted is not None and unlisted.spec.name == "local"

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
