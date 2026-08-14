"""Owner policy 2026-08-12 — the system default is a fallback, not a wall.

> "user doesn't set LLM then use default local AI by system .env setting;
>  user set LLM then all AI by set LLM"

This supersedes the 2026-07-31 rule, under which a context that NAMED a user or
agent but carried no provider resolved to `None` — never the admin-console
default, never the platform env. That rule made an *absent* LlmContext
load-bearing: `run_engine.run_cycle` deliberately set none, because setting one
(even only to record who to bill) flipped every fleet cycle onto the
"unconfigured user" path and silenced the desk. Shipped as #395 on 2026-08-12,
it produced `"llm": {}` and a forced hold on every cycle; reverted in 7d09628d.

These tests run the REAL resolve_provider. The nine tests that shipped #395 all
patched either generate_text or resolve_provider itself, so not one exercised
the path that broke — 4001 passing tests said nothing about it.
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
        llm_client.invalidate_admin_llm_settings_cache()

    def tearDown(self):
        for k, v in self._saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        llm_client.invalidate_admin_llm_settings_cache()
        self.tmp.cleanup()

    def _console_default(self, provider="local"):
        """Route both tiers to `provider` from the admin console, as prod does."""
        r = self.client.put("/api/admin/settings/llm",
                            json={"brief_provider": provider,
                                  "decision_provider": provider},
                            headers=self.admin)
        assert r.status_code == 200, r.text
        llm_client.invalidate_admin_llm_settings_cache()


class UnconfiguredUserFallsBackToSystemDefault(_Base):
    """"user doesn't set LLM then use default local AI by system .env setting"."""

    def test_named_context_without_a_provider_uses_the_console_default(self):
        """THE REGRESSION TEST. A cycle context names who to bill and picks no
        AI; under the old rule this resolved to None and the desk went silent."""
        self._console_default("local")
        token = set_llm_context(LlmContext(source="rule", user_id=42, agent_id=7))
        try:
            ap = resolve_provider(tier="decision")
        finally:
            reset_llm_context(token)
        self.assertIsNotNone(
            ap, "a named-but-unconfigured context resolved to None — this is the "
                "#395 desk-silence regression")
        self.assertEqual(ap.spec.name, "local")

    def test_agent_only_context_also_falls_back(self):
        """An ownerless (claw) agent names no user but still must not silence."""
        self._console_default("local")
        token = set_llm_context(LlmContext(source="rule", agent_id=7))
        try:
            ap = resolve_provider(tier="decision")
        finally:
            reset_llm_context(token)
        self.assertIsNotNone(ap)
        self.assertEqual(ap.spec.name, "local")

    def test_falls_back_to_env_when_the_console_says_nothing(self):
        """`by system .env setting` — with no console route, LLM_PROVIDER wins."""
        os.environ["LLM_PROVIDER"] = "local"
        token = set_llm_context(LlmContext(source="rule", user_id=42, agent_id=7))
        try:
            ap = resolve_provider(tier="decision")
        finally:
            reset_llm_context(token)
        self.assertIsNotNone(ap)
        self.assertEqual(ap.spec.name, "local")

    def test_no_context_still_resolves_the_same_default(self):
        """Naming the member must not change WHICH provider is chosen."""
        self._console_default("local")
        bare = resolve_provider(tier="decision")
        token = set_llm_context(LlmContext(source="rule", user_id=42, agent_id=7))
        try:
            named = resolve_provider(tier="decision")
        finally:
            reset_llm_context(token)
        self.assertIsNotNone(bare)
        self.assertIsNotNone(named)
        self.assertEqual(bare.spec.name, named.spec.name)
        self.assertEqual(bare.model, named.model)


class AdminSwitchesTheDefaultForEveryone(_Base):
    """The admin console IS the default engine, and switching it switches
    every member who has not set their own AI.

    This is the half the 2026-07-31 rule silently broke: a context naming a
    user or agent skipped the console default entirely and resolved to None, so
    the admin's choice governed system calls only. Now the operator's setting
    is what an unconfigured member actually runs on.
    """

    def test_switching_the_console_switches_an_unconfigured_member(self):
        member = LlmContext(source="rule", user_id=42, agent_id=7)
        os.environ["ANTHROPIC_API_KEY"] = "sk-platform"

        self._console_default("anthropic")
        token = set_llm_context(member)
        try:
            first = resolve_provider(tier="decision")
        finally:
            reset_llm_context(token)
        self.assertEqual(first.spec.name, "anthropic")

        self._console_default("local")          # operator switches it back
        token = set_llm_context(member)
        try:
            second = resolve_provider(tier="decision")
        finally:
            reset_llm_context(token)
        self.assertEqual(second.spec.name, "local",
                         "the console switch did not reach an unconfigured "
                         "member — the admin default is not actually default")

    def test_the_switch_never_overrides_a_member_who_chose_their_own(self):
        """Switching the platform default must not move a user off their AI."""
        os.environ["ANTHROPIC_API_KEY"] = "sk-platform"
        self._console_default("anthropic")
        own = LlmContext(provider="local", source="user", user_id=42)
        token = set_llm_context(own)
        try:
            ap = resolve_provider(tier="decision")
        finally:
            reset_llm_context(token)
        self.assertEqual(ap.spec.name, "local")


class TheSystemDefaultMustBeLocal(_Base):
    """"default AI by system (use default local ai)" — what actually delivers it.

    Auto-detect deliberately skips `local` ("never auto-select local; require
    explicit LLM_PROVIDER=local"), so with the console cleared and LLM_PROVIDER
    unset, resolution lands on the first provider that has a key. On prod that
    is ANTHROPIC_API_KEY — the only provider key in the .env — i.e. a PAID
    provider, not local.

    `LLM_PROVIDER=local` in the .env is therefore the thing that makes the
    system default local, exactly as the owner phrased it ("default local AI by
    system .env setting"). These two tests pin both sides so the difference is
    visible instead of surprising.
    """

    def test_env_local_is_what_makes_the_system_default_local(self):
        os.environ["LLM_PROVIDER"] = "local"
        os.environ["ANTHROPIC_API_KEY"] = "sk-paid"
        token = set_llm_context(LlmContext(source="rule", user_id=42, agent_id=7))
        try:
            ap = resolve_provider(tier="decision")
        finally:
            reset_llm_context(token)
        self.assertEqual(ap.spec.name, "local")

    def test_without_it_an_unconfigured_member_lands_on_the_paid_key(self):
        """Characterisation, not an endorsement: this is the prod exposure.
        No console route + no LLM_PROVIDER + a paid key present => paid."""
        os.environ.pop("LLM_PROVIDER", None)
        os.environ["ANTHROPIC_API_KEY"] = "sk-paid"
        token = set_llm_context(LlmContext(source="rule", user_id=42, agent_id=7))
        try:
            ap = resolve_provider(tier="decision")
        finally:
            reset_llm_context(token)
        self.assertIsNotNone(ap)
        self.assertEqual(
            ap.spec.name, "anthropic",
            "if this ever fails, auto-detect changed — recheck whether the "
            "system default is still reachable without LLM_PROVIDER=local")


class ConfiguredUserWins(_Base):
    """"user set LLM then all AI by set LLM" — their choice beats the default."""

    def test_user_provider_beats_the_console_default(self):
        self._console_default("local")
        os.environ["ANTHROPIC_API_KEY"] = "sk-env"
        token = set_llm_context(LlmContext(provider="anthropic", source="user",
                                           api_key="sk-user", user_id=42))
        try:
            ap = resolve_provider(tier="decision")
        finally:
            reset_llm_context(token)
        self.assertEqual(ap.spec.name, "anthropic")
        self.assertEqual(ap.api_key, "sk-user")

    def test_user_provider_applies_to_every_tier(self):
        """"ALL AI by set LLM" — brief and decision both follow the user."""
        self._console_default("local")
        token = set_llm_context(LlmContext(provider="anthropic", source="user",
                                           api_key="sk-user", user_id=42))
        try:
            brief = resolve_provider(tier="brief")
            decision = resolve_provider(tier="decision")
        finally:
            reset_llm_context(token)
        self.assertEqual(brief.spec.name, "anthropic")
        self.assertEqual(decision.spec.name, "anthropic")

    def test_run_llm_tiers_still_win_over_everything(self):
        """Existing precedence is untouched: run-config llm_tiers is top."""
        self._console_default("local")
        os.environ["ANTHROPIC_API_KEY"] = "sk-env"
        token = set_llm_context(LlmContext(
            source="rule", user_id=42, agent_id=7,
            tier_providers={"decision": {"provider": "anthropic"}}))
        try:
            ap = resolve_provider(tier="decision")
        finally:
            reset_llm_context(token)
        self.assertEqual(ap.spec.name, "anthropic")


if __name__ == "__main__":
    unittest.main()
