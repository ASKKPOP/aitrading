"""Local provider tier defaults: cheap brief head, strong decision head.

With the platform on the local provider and no explicit model anywhere
(no env, no console local model, no per-tier console model), the daemon
defaults to gpt-oss:20b for briefs and gpt-oss:120b for decisions — the
same cheap-brief / strong-decision split the paid providers use. The
console's generic local-model field, when set, pins every tier.
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
from llm_client import resolve_provider


class LocalTierDefaults(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self._saved_env = {}
        for k in ("LLM_PROVIDER", "LLM_MODEL", "LLM_MODEL_BRIEF",
                  "LLM_MODEL_DECISION", "ANTHROPIC_API_KEY",
                  "LOCAL_LLM_BASE_URL", "LOCAL_LLM_MODEL"):
            self._saved_env[k] = os.environ.pop(k, None)
        from platform_settings import set_setting
        for tier in ("brief", "decision"):
            set_setting(f"llm_{tier}_provider", "local")
            set_setting(f"llm_{tier}_model", "")
        set_setting("llm_local_model", "")
        llm_client.invalidate_admin_llm_settings_cache()

    def tearDown(self):
        for k, v in self._saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        llm_client.invalidate_admin_llm_settings_cache()
        self.tmp.cleanup()

    def test_split_by_default(self):
        assert resolve_provider("brief").model == "gpt-oss:20b"
        assert resolve_provider("decision").model == "gpt-oss:120b"

    def test_assistant_tier_default_when_env_local(self):
        os.environ["LLM_PROVIDER"] = "local"
        assert resolve_provider("assistant").model == "gpt-oss:20b"

    def test_console_local_model_pins_every_tier(self):
        from platform_settings import set_setting
        set_setting("llm_local_model", "my-model")
        llm_client.invalidate_admin_llm_settings_cache()
        assert resolve_provider("brief").model == "my-model"
        assert resolve_provider("decision").model == "my-model"

    def test_per_tier_console_model_wins(self):
        from platform_settings import set_setting
        set_setting("llm_decision_model", "gpt-oss:20b")
        llm_client.invalidate_admin_llm_settings_cache()
        assert resolve_provider("decision").model == "gpt-oss:20b"
        assert resolve_provider("brief").model == "gpt-oss:20b"


if __name__ == "__main__":
    unittest.main()
