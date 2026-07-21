"""Admin console LLM routing settings (/api/admin/settings/llm) and their
effect on llm_client.resolve_provider precedence:
run llm_tiers > explicit ctx provider > admin console setting > env.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
import llm_client
from llm_client import LlmContext, reset_llm_context, resolve_provider, set_llm_context
from routes import create_app


class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())
        from admin_auth import create_admin
        create_admin("root@test.com", "rootpass123", "superadmin")
        r = self.client.post("/api/admin/login",
                             json={"email": "root@test.com", "password": "rootpass123"})
        self.admin = {"Authorization": f"Bearer {r.json()['token']}"}
        self._saved_env = {}
        for k in ("LLM_PROVIDER", "LLM_MODEL", "ANTHROPIC_API_KEY",
                  "LOCAL_LLM_BASE_URL", "LOCAL_LLM_MODEL"):
            self._saved_env[k] = os.environ.pop(k, None)
        os.environ["ANTHROPIC_API_KEY"] = "test-key"
        llm_client.invalidate_admin_llm_settings_cache()

    def tearDown(self):
        for k, v in self._saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        llm_client.invalidate_admin_llm_settings_cache()
        self.tmp.cleanup()


class AdminLlmSettingsApi(_Base):
    def test_requires_admin(self):
        assert self.client.get("/api/admin/settings/llm").status_code in (401, 403)
        assert self.client.put("/api/admin/settings/llm",
                               json={}).status_code in (401, 403)

    def test_get_shape(self):
        r = self.client.get("/api/admin/settings/llm", headers=self.admin)
        assert r.status_code == 200
        body = r.json()
        assert "llm_local_base_url" in body["settings"]
        assert "local" in body["providers"] and "anthropic" in body["providers"]
        assert body["effective"]["decision"]["provider"] == "anthropic"

    def test_put_saves_and_takes_effect(self):
        r = self.client.put("/api/admin/settings/llm", headers=self.admin, json={
            "local_base_url": "http://100.64.0.7:11434/v1",
            "local_model": "gpt-oss:120b",
            "brief_provider": "local",
            "decision_provider": "anthropic",
            "decision_model": "claude-sonnet-5",
        })
        assert r.status_code == 200
        eff = r.json()["effective"]
        assert eff["brief"] == {"provider": "local", "model": "gpt-oss:120b",
                                "base_url": "http://100.64.0.7:11434/v1"}
        assert eff["decision"]["provider"] == "anthropic"
        assert eff["decision"]["model"] == "claude-sonnet-5"
        # assistant tier untouched by brief/decision settings
        assert eff["assistant"]["provider"] == "anthropic"

    def test_put_rejects_bad_url_and_provider(self):
        r = self.client.put("/api/admin/settings/llm", headers=self.admin,
                            json={"local_base_url": "100.64.0.7:11434"})
        assert r.status_code == 400
        r = self.client.put("/api/admin/settings/llm", headers=self.admin,
                            json={"brief_provider": "no-such"})
        assert r.status_code == 400

    def test_put_clear_resumes_env_fallback(self):
        self.client.put("/api/admin/settings/llm", headers=self.admin,
                        json={"local_base_url": "http://10.0.0.9:11434/v1"})
        os.environ["LOCAL_LLM_BASE_URL"] = "http://env-host:11434/v1"
        r = self.client.put("/api/admin/settings/llm", headers=self.admin,
                            json={"local_base_url": "", "brief_provider": "local"})
        assert r.json()["effective"]["brief"]["base_url"] == "http://env-host:11434/v1"

    def test_omitted_fields_unchanged(self):
        self.client.put("/api/admin/settings/llm", headers=self.admin,
                        json={"local_model": "gpt-oss:120b"})
        r = self.client.put("/api/admin/settings/llm", headers=self.admin,
                            json={"brief_provider": "local"})
        assert r.status_code == 200
        r = self.client.get("/api/admin/settings/llm", headers=self.admin)
        assert r.json()["settings"]["llm_local_model"]["value"] == "gpt-oss:120b"


class AdminLlmSettingsPrecedence(_Base):
    def _save_ab(self):
        self.client.put("/api/admin/settings/llm", headers=self.admin, json={
            "brief_provider": "local", "local_model": "gpt-oss:120b",
            "decision_provider": "anthropic", "decision_model": "claude-sonnet-5"})
        llm_client.invalidate_admin_llm_settings_cache()

    def test_admin_setting_routes_plain_calls(self):
        self._save_ab()
        ap = resolve_provider(tier="brief")
        assert ap.spec.name == "local"
        assert ap.model == "gpt-oss:120b"
        ap = resolve_provider(tier="decision")
        assert ap.model == "claude-sonnet-5"

    def test_explicit_ctx_provider_beats_admin(self):
        self._save_ab()
        token = set_llm_context(LlmContext(provider="anthropic", source="user"))
        try:
            ap = resolve_provider(tier="brief")
        finally:
            reset_llm_context(token)
        assert ap.spec.name == "anthropic"  # user's choice, not admin's local

    def test_run_llm_tiers_beats_admin(self):
        self._save_ab()
        token = set_llm_context(LlmContext(
            tier_providers={"brief": {"provider": "anthropic",
                                      "model": "claude-haiku-4-5"}}))
        try:
            ap = resolve_provider(tier="brief")
        finally:
            reset_llm_context(token)
        assert ap.spec.name == "anthropic"
        assert ap.model == "claude-haiku-4-5"


if __name__ == "__main__":
    unittest.main()
