"""Local reasoning models get a completion-budget floor.

gpt-oss spends completion budget on hidden chain-of-thought BEFORE any
visible content; the small per-call budgets sized for paid instruct models
starve it into empty output (every light cycle read "no LLM verdict" and
forced hold). Local tokens are free — generate_text floors the budget for
the local provider and leaves paid providers' budgets untouched.
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
from llm_client import LlmContext, generate_text, reset_llm_context, set_llm_context


class LocalTokenFloor(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self._saved_env = {}
        for k in ("LLM_PROVIDER", "LLM_MODEL", "ANTHROPIC_API_KEY"):
            self._saved_env[k] = os.environ.pop(k, None)
        os.environ["ANTHROPIC_API_KEY"] = "test-key"
        llm_client.invalidate_admin_llm_settings_cache()
        self.calls = []
        self._real_openai = llm_client._generate_openai_compatible
        self._real_anthropic = llm_client._generate_anthropic

        def fake(ap, prompt, system, max_tokens, temperature):
            self.calls.append((ap.spec.name, max_tokens))
            return "ok", (1, 1)
        llm_client._generate_openai_compatible = fake
        llm_client._generate_anthropic = fake

    def tearDown(self):
        llm_client._generate_openai_compatible = self._real_openai
        llm_client._generate_anthropic = self._real_anthropic
        for k, v in self._saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        llm_client.invalidate_admin_llm_settings_cache()
        self.tmp.cleanup()

    def test_local_floors_small_budgets(self):
        from platform_settings import set_setting
        set_setting("llm_decision_provider", "local")
        set_setting("llm_decision_model", "gpt-oss:20b")
        llm_client.invalidate_admin_llm_settings_cache()
        assert generate_text("p", max_tokens=200, tier="decision") == "ok"
        assert self.calls == [("local", 2000)]

    def test_local_keeps_larger_budgets(self):
        from platform_settings import set_setting
        set_setting("llm_decision_provider", "local")
        llm_client.invalidate_admin_llm_settings_cache()
        generate_text("p", max_tokens=4000, tier="decision")
        assert self.calls == [("local", 4000)]

    def test_paid_provider_budget_untouched(self):
        token = set_llm_context(LlmContext(provider="anthropic", api_key="k",
                                           source="user", user_id=1))
        try:
            generate_text("p", max_tokens=200, tier="decision")
        finally:
            reset_llm_context(token)
        assert self.calls == [("anthropic", 200)]


if __name__ == "__main__":
    unittest.main()
