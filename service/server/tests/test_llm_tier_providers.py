"""Per-tier LLM provider routing (cost A/B: local briefs + Sonnet decisions).

Covers llm_client.resolve_provider tier overrides and the llm_tiers plumbing
from run config through run_analysis's LlmContext.
"""
import os
from unittest import mock

import pytest

import llm_client
from llm_client import LlmContext, reset_llm_context, resolve_provider, set_llm_context


AB_TIERS = {"brief": {"provider": "local"},
            "decision": {"provider": "anthropic", "model": "claude-sonnet-5"}}


@pytest.fixture(autouse=True)
def _clean_env():
    """Deterministic provider env for every test in this module."""
    saved = {}
    keys = ("LLM_PROVIDER", "LLM_MODEL", "LLM_MODEL_BRIEF", "LLM_MODEL_DECISION",
            "ANTHROPIC_API_KEY", "LOCAL_LLM_BASE_URL", "LOCAL_LLM_MODEL",
            "LOCAL_LLM_API_KEY", "OPENAI_API_KEY")
    for k in keys:
        saved[k] = os.environ.pop(k, None)
    os.environ["ANTHROPIC_API_KEY"] = "test-key"
    llm_client.invalidate_admin_llm_settings_cache()
    yield
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def _with_ctx(ctx, tier):
    token = set_llm_context(ctx)
    try:
        return resolve_provider(tier=tier)
    finally:
        reset_llm_context(token)


def test_brief_tier_routes_to_local():
    os.environ["LOCAL_LLM_MODEL"] = "gpt-oss:120b"
    ap = _with_ctx(LlmContext(tier_providers=AB_TIERS, user_id=1, agent_id=2),
                   tier="brief")
    assert ap.spec.name == "local"
    assert ap.model == "gpt-oss:120b"
    assert ap.base_url == "http://localhost:11434/v1"
    assert ap.api_key == "local"  # no key needed for local


def test_decision_tier_routes_to_anthropic_sonnet():
    ap = _with_ctx(LlmContext(tier_providers=AB_TIERS), tier="decision")
    assert ap.spec.name == "anthropic"
    assert ap.model == "claude-sonnet-5"  # override, NOT the Opus tier default
    assert ap.api_key == "test-key"


def test_unlisted_tier_unaffected():
    """assistant is not in the A/B map -> normal resolution (anthropic default)."""
    ap = _with_ctx(LlmContext(tier_providers=AB_TIERS), tier="assistant")
    assert ap.spec.name == "anthropic"
    assert ap.model == "claude-sonnet-5"  # the normal assistant-tier model


def test_no_context_default_resolution_unchanged():
    ap = resolve_provider(tier="decision")
    assert ap.spec.name == "anthropic"
    assert ap.model == "claude-opus-4-8"


def test_unknown_provider_falls_back():
    ctx = LlmContext(tier_providers={"brief": {"provider": "nonsense"}})
    ap = _with_ctx(ctx, tier="brief")
    assert ap.spec.name == "anthropic"  # fell through to env resolution


def test_missing_key_falls_back():
    """Override to a provider with no key configured -> normal resolution."""
    ctx = LlmContext(tier_providers={"brief": {"provider": "openai"}})
    ap = _with_ctx(ctx, tier="brief")
    assert ap.spec.name == "anthropic"


def test_local_base_url_env_override():
    os.environ["LOCAL_LLM_BASE_URL"] = "http://100.64.0.7:11434/v1"
    ap = _with_ctx(LlmContext(tier_providers=AB_TIERS), tier="brief")
    assert ap.base_url == "http://100.64.0.7:11434/v1"


def test_override_never_uses_user_key():
    """The user's stored key belongs to their provider, not the override's."""
    ctx = LlmContext(provider="anthropic", api_key="user-secret", source="user",
                     tier_providers=AB_TIERS)
    ap = _with_ctx(ctx, tier="brief")
    assert ap.spec.name == "local"
    assert ap.api_key == "local"
    assert "user-secret" not in (ap.api_key or "")


def test_set_llm_context_preserves_tier_providers():
    """The normalization rebuild in set_llm_context must carry tier_providers."""
    token = set_llm_context(LlmContext(provider="Anthropic ",
                                       tier_providers=AB_TIERS))
    try:
        ctx = llm_client.current_llm_context()
        assert ctx.provider == "anthropic"
        assert ctx.tier_providers == AB_TIERS
    finally:
        reset_llm_context(token)


def test_metering_identity_survives_override():
    """generate_text metering must attribute tier-override calls to the run owner."""
    recorded = {}

    def fake_record(**kw):
        recorded.update(kw)

    ctx = LlmContext(tier_providers=AB_TIERS, user_id=7, agent_id=9)
    token = set_llm_context(ctx)
    try:
        ap = resolve_provider(tier="brief")
        with mock.patch("llm_usage.record_usage", side_effect=fake_record):
            llm_client._record_usage(ap, "brief", (100, 50))
    finally:
        reset_llm_context(token)
    assert recorded["user_id"] == 7
    assert recorded["agent_id"] == 9
    assert recorded["provider"] == "local"


def test_run_analysis_threads_llm_tiers(monkeypatch):
    """run_analysis puts llm_tiers on the context seen by the pipeline."""
    import analysis_agents

    seen = {}

    def fake_inner(symbol, market, lang, guidelines=None, progress=None,
                   agent_id=None):
        ctx = llm_client.current_llm_context()
        seen["tiers"] = ctx.tier_providers if ctx else None
        return {"decision": {"action": "hold"}}

    monkeypatch.setattr(analysis_agents, "_run_analysis_inner", fake_inner)
    analysis_agents.run_analysis("BTC", "crypto", "en", llm_tiers=AB_TIERS)
    assert seen["tiers"] == AB_TIERS


def test_run_in_validator_accepts_and_normalizes():
    from routes_runs import RunIn
    data = RunIn(symbol="btc", market="crypto", max_bet_usd=100,
                 llm_tiers={"brief": {"provider": "Local"},
                            "decision": {"provider": "anthropic",
                                         "model": "claude-sonnet-5"}})
    assert data.llm_tiers == {"brief": {"provider": "local"},
                              "decision": {"provider": "anthropic",
                                           "model": "claude-sonnet-5"}}


def test_run_in_validator_rejects_bad_tier_and_provider():
    from routes_runs import RunIn
    with pytest.raises(ValueError):
        RunIn(symbol="btc", market="crypto", max_bet_usd=100,
              llm_tiers={"assistant": {"provider": "local"}})
    with pytest.raises(ValueError):
        RunIn(symbol="btc", market="crypto", max_bet_usd=100,
              llm_tiers={"brief": {"provider": "no-such"}})
