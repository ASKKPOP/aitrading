"""Unified multi-provider LLM client.

Lets Sooppiy generate text with any of several AI providers instead of only
OpenRouter. Supported providers:

    openai      OpenAI                (api.openai.com)
    gemini      Google Gemini         (OpenAI-compatible endpoint)
    grok        xAI Grok              (api.x.ai)
    qwen        Alibaba Qwen/DashScope(OpenAI-compatible endpoint)
    glm         Zhipu GLM             (OpenAI-compatible endpoint)
    local       Local LLM             (Ollama / LM Studio / vLLM, OpenAI-compatible)
    openrouter  OpenRouter            (kept for backward compatibility)
    anthropic   Anthropic Claude      (native SDK)

Selection (in priority order):
  1. LLM_PROVIDER env (explicit).
  2. Auto-detect: the first provider whose API key env is set.
  3. Disabled -> callers fall back to their own non-LLM summary.

Model: LLM_MODEL overrides everything; otherwise the provider's default (or the
legacy OPENROUTER_MODEL for the openrouter provider). All network calls except
Anthropic go through the OpenAI-compatible Chat Completions API, so one code path
covers OpenAI, Gemini, Grok, Qwen, GLM, local, and OpenRouter.

The openai / anthropic SDKs are imported lazily so this module (and its provider
resolution) can be imported and unit-tested without those packages installed.
"""

from __future__ import annotations

import contextvars
import logging
import os
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# Per-call LLM context (an automation rule's provider choice and/or the owning
# user's stored provider/model/API key). Thread/async safe; falls back to
# env-based selection when unset.
@dataclass(frozen=True)
class LlmContext:
    provider: Optional[str] = None
    model: Optional[str] = None
    api_key: Optional[str] = None
    source: str = "rule"  # 'user' (settings page) | 'rule' (automation config)
    # Usage-metering identity (Plan 11 F2): whose analysis triggered the call.
    user_id: Optional[int] = None
    agent_id: Optional[int] = None


_context_override: contextvars.ContextVar[Optional[LlmContext]] = contextvars.ContextVar(
    "llm_context_override", default=None
)


def set_llm_context(ctx: Optional[LlmContext]):
    """Set (or clear with None) the LLM context for the current call chain.
    Returns the contextvars token so callers can reset."""
    if ctx is not None and ctx.provider:
        ctx = LlmContext(provider=ctx.provider.strip().lower(), model=ctx.model,
                         api_key=ctx.api_key, source=ctx.source,
                         user_id=ctx.user_id, agent_id=ctx.agent_id)
    return _context_override.set(ctx)


def reset_llm_context(token) -> None:
    _context_override.reset(token)


def current_llm_context() -> Optional[LlmContext]:
    """The context in force for this call chain, or None.

    Exists so a nested call can override one field (e.g. the verifier switching
    provider for cross-model independence) while carrying the metering identity
    forward, instead of building a bare context and silently orphaning the
    llm_usage row."""
    return _context_override.get()


def set_provider_override(name: Optional[str]):
    """Back-compat wrapper: provider-only context (automation rules)."""
    return set_llm_context(LlmContext(provider=name, source="rule") if name else None)


def reset_provider_override(token) -> None:
    reset_llm_context(token)


@dataclass(frozen=True)
class ProviderSpec:
    name: str
    key_env: str
    default_base_url: str
    base_url_env: str
    default_model: str
    kind: str = "openai"  # "openai" (compatible) or "anthropic"


# Registry. Order matters for auto-detection.
_PROVIDERS: dict[str, ProviderSpec] = {
    "openai": ProviderSpec(
        "openai", "OPENAI_API_KEY", "https://api.openai.com/v1", "OPENAI_BASE_URL", "gpt-4o-mini"),
    "gemini": ProviderSpec(
        "gemini", "GEMINI_API_KEY", "https://generativelanguage.googleapis.com/v1beta/openai/",
        "GEMINI_BASE_URL", "gemini-2.0-flash"),
    "grok": ProviderSpec(
        "grok", "XAI_API_KEY", "https://api.x.ai/v1", "XAI_BASE_URL", "grok-2-latest"),
    "qwen": ProviderSpec(
        "qwen", "DASHSCOPE_API_KEY", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        "QWEN_BASE_URL", "qwen-plus"),
    "glm": ProviderSpec(
        "glm", "GLM_API_KEY", "https://open.bigmodel.cn/api/paas/v4", "GLM_BASE_URL", "glm-4-plus"),
    "openrouter": ProviderSpec(
        "openrouter", "OPENROUTER_API_KEY", "https://openrouter.ai/api/v1", "OPENROUTER_BASE_URL",
        "openai/gpt-4o-mini"),
    "local": ProviderSpec(
        "local", "LOCAL_LLM_API_KEY", "http://localhost:11434/v1", "LOCAL_LLM_BASE_URL",
        "llama3.1", kind="openai"),
    "anthropic": ProviderSpec(
        "anthropic", "ANTHROPIC_API_KEY", "https://api.anthropic.com", "ANTHROPIC_BASE_URL",
        "claude-sonnet-5", kind="anthropic"),
}

# Task tiers: analyst briefs are the cheaper tier; the trader decision and the
# verification passes need the strong tier. Providers without an entry use
# their single default_model for both tiers.
# Env overrides: LLM_MODEL (both tiers) > LLM_MODEL_BRIEF / LLM_MODEL_DECISION.
#
# Anthropic brief = Sonnet, not Haiku (Henry's call, 2026-07-17, and the D5
# measurements back it): Haiku produced high-severity false faults on real
# snapshots 4/4 — it read MA20 vs MA200 as a contradiction and called absent
# sentiment disqualifying. Briefs feed the trader, so a brief that misreads
# the data is not a saving.
#
# The 'assistant' tier is the user-facing chat dock. It runs Sonnet rather than
# the decision tier's Opus (Henry's call, 2026-07-18): the assistant explains
# an account it is already handed in full and never places orders, so it does
# not need the trader's reasoning depth — and it answers a human who is waiting.
_TIER_MODELS: dict[str, dict[str, str]] = {
    "anthropic": {"brief": "claude-sonnet-5", "decision": "claude-opus-4-8",
                  "assistant": "claude-sonnet-5"},
    "openai": {"brief": "gpt-4o-mini", "decision": "gpt-4o", "assistant": "gpt-4o-mini"},
}
_TIER_ENV = {"brief": "LLM_MODEL_BRIEF", "decision": "LLM_MODEL_DECISION",
             "assistant": "LLM_MODEL_ASSISTANT"}

# Accept a few friendly aliases for key env vars.
_KEY_ALIASES: dict[str, tuple[str, ...]] = {
    "qwen": ("DASHSCOPE_API_KEY", "QWEN_API_KEY"),
    "glm": ("GLM_API_KEY", "ZHIPUAI_API_KEY"),
    "grok": ("XAI_API_KEY", "GROK_API_KEY"),
    "local": ("LOCAL_LLM_API_KEY",),  # key optional for local
}


def _get_key(spec: ProviderSpec) -> str:
    for env in _KEY_ALIASES.get(spec.name, (spec.key_env,)):
        val = os.getenv(env, "").strip()
        if val:
            return val
    # Local servers often need no real key; use a placeholder so the SDK is happy.
    if spec.name == "local":
        return os.getenv("LOCAL_LLM_API_KEY", "").strip() or "local"
    return ""


@dataclass(frozen=True)
class ActiveProvider:
    spec: ProviderSpec
    api_key: str
    base_url: str
    model: str
    source: str = "server"  # 'user' | 'rule' | 'server' | 'auto'


def _tier_model(spec: ProviderSpec, tier: str) -> str:
    """Model for a task tier: LLM_MODEL > LLM_MODEL_<TIER> > tier table > provider default."""
    model = os.getenv("LLM_MODEL", "").strip()
    if model:
        return model
    tier_env = _TIER_ENV.get(tier)
    if tier_env:
        model = os.getenv(tier_env, "").strip()
        if model:
            return model
    tiered = _TIER_MODELS.get(spec.name, {}).get(tier)
    if tiered:
        return tiered
    if spec.name == "openrouter":
        return os.getenv("OPENROUTER_MODEL", "").strip() or spec.default_model
    if spec.name == "local":
        return os.getenv("LOCAL_LLM_MODEL", "").strip() or spec.default_model
    return spec.default_model


def resolve_provider(tier: str = "decision") -> Optional[ActiveProvider]:
    """Return the active provider config, or None if no provider is usable.

    Resolution order — provider: context (user settings / rule) > LLM_PROVIDER
    env > registry auto-detect. Key: the context's user key (when it belongs to
    the resolved provider) > env key. Model: context model > LLM_MODEL >
    LLM_MODEL_<TIER> > tier table > provider default."""
    ctx = _context_override.get()
    ctx_provider = (ctx.provider or "") if ctx else ""
    env_provider = os.getenv("LLM_PROVIDER", "").strip().lower()
    explicit = ctx_provider or env_provider

    def build(spec: ProviderSpec, source: str) -> Optional[ActiveProvider]:
        key = ""
        key_from_user = False
        # A user's stored key applies only to the provider it was saved for.
        if ctx and ctx.api_key and (not ctx_provider or ctx_provider == spec.name):
            key = ctx.api_key.strip()
            key_from_user = ctx.source == "user"
        if not key:
            key = _get_key(spec)
        if not key and spec.name != "local":
            return None
        if spec.name == "local" and not key:
            key = "local"
        base_url = os.getenv(spec.base_url_env, "").strip() or spec.default_base_url
        model = ""
        if ctx and ctx.model and (not ctx_provider or ctx_provider == spec.name):
            model = ctx.model.strip()
        if not model:
            model = _tier_model(spec, tier)
        if key_from_user:
            source = "user"
        return ActiveProvider(spec=spec, api_key=key, base_url=base_url, model=model, source=source)

    if explicit:
        spec = _PROVIDERS.get(explicit)
        if not spec:
            logger.warning("Unknown LLM provider %r; supported: %s", explicit, ", ".join(_PROVIDERS))
            return None
        source = (ctx.source if ctx_provider and ctx else "server")
        return build(spec, source)

    # Auto-detect: first provider (in registry order) with a key set.
    for spec in _PROVIDERS.values():
        if spec.name == "local":
            continue  # never auto-select local; require explicit LLM_PROVIDER=local
        built = build(spec, "auto")
        if built:
            return built
    return None


def llm_configured() -> bool:
    return resolve_provider() is not None


def active_provider_name() -> Optional[str]:
    ap = resolve_provider()
    return ap.spec.name if ap else None


def active_provider_source() -> Optional[str]:
    """Where the active provider came from: user | rule | server | auto."""
    ap = resolve_provider()
    return ap.source if ap else None


def active_provider_model(tier: str = "decision") -> Optional[str]:
    """The model the given tier would run right now (for payload telemetry)."""
    ap = resolve_provider(tier=tier)
    return ap.model if ap else None


def generate_text(
    prompt: str,
    *,
    system: Optional[str] = None,
    max_tokens: int = 400,
    temperature: float = 0.4,
    tier: str = "decision",
) -> Optional[str]:
    """Generate text with the active provider. Returns None on any failure so
    callers can fall back to their own deterministic summary."""
    ap = resolve_provider(tier=tier)
    if ap is None:
        return None
    try:
        if ap.spec.kind == "anthropic":
            text, usage = _generate_anthropic(ap, prompt, system, max_tokens, temperature)
        else:
            text, usage = _generate_openai_compatible(ap, prompt, system, max_tokens, temperature)
    except Exception as exc:  # noqa: BLE001 - provider errors must not crash callers
        logger.warning("LLM generation failed (provider=%s): %s", ap.spec.name, exc)
        return None
    _record_usage(ap, tier, usage)
    return text


def _record_usage(ap: ActiveProvider, tier: str, usage: tuple[int, int]) -> None:
    """Meter one call (Plan 11 F2). Fail-soft — never breaks the caller."""
    try:
        from llm_usage import record_usage
        ctx = _context_override.get()
        record_usage(
            provider=ap.spec.name, model=ap.model, tier=tier,
            key_source="user" if ap.source == "user" else "system",
            user_id=ctx.user_id if ctx else None,
            agent_id=ctx.agent_id if ctx else None,
            prompt_tokens=usage[0], completion_tokens=usage[1])
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM usage metering failed: %s", exc)


def _usage_tokens(usage) -> tuple[int, int]:
    """(prompt_tokens, completion_tokens) from an SDK usage object; 0s when absent."""
    if usage is None:
        return (0, 0)
    prompt = getattr(usage, "prompt_tokens", None)
    if prompt is None:
        prompt = getattr(usage, "input_tokens", None)
    completion = getattr(usage, "completion_tokens", None)
    if completion is None:
        completion = getattr(usage, "output_tokens", None)
    try:
        return (int(prompt or 0), int(completion or 0))
    except (TypeError, ValueError):
        return (0, 0)


def _generate_openai_compatible(ap, prompt, system, max_tokens, temperature):
    from openai import OpenAI  # lazy import

    client = OpenAI(api_key=ap.api_key, base_url=ap.base_url)
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    resp = client.chat.completions.create(
        model=ap.model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    usage = _usage_tokens(getattr(resp, "usage", None))
    if not resp.choices:
        return None, usage
    content = resp.choices[0].message.content
    return (content.strip() if isinstance(content, str) else None), usage


# Models observed to reject `temperature`, learned on the first 400 and
# remembered for the life of the process (see _generate_anthropic).
_NO_TEMPERATURE_MODELS: set[str] = set()


def _generate_anthropic(ap, prompt, system, max_tokens, temperature):
    import anthropic  # lazy import

    # Pass the resolved base_url explicitly, like the OpenAI-compatible path does.
    # Without it the SDK falls back to reading ANTHROPIC_BASE_URL from the process
    # env itself; that happens to match ap.base_url today, but relying on it means
    # a context-supplied base_url would be silently ignored. Make ap.base_url win.
    client = anthropic.Anthropic(api_key=ap.api_key, base_url=ap.base_url)
    kwargs = {
        "model": ap.model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        kwargs["system"] = system

    # Claude 5-family models reject `temperature` ("deprecated for this
    # model"). The retry below handles that, but retrying on EVERY call means
    # every request pays a wasted round-trip first: prod logs showed 400s and
    # 200s exactly 1:1, i.e. ~2x the latency on a 20s+ fusion path. So we
    # remember which models refuse it and stop asking. Learned at runtime
    # rather than hardcoded, because a model list here would rot.
    if ap.model in _NO_TEMPERATURE_MODELS:
        msg = client.messages.create(**kwargs)
    else:
        try:
            msg = client.messages.create(temperature=temperature, **kwargs)
        except anthropic.BadRequestError as exc:
            if "temperature" not in str(exc):
                raise
            _NO_TEMPERATURE_MODELS.add(ap.model)
            msg = client.messages.create(**kwargs)
    parts = [b.text for b in msg.content if getattr(b, "type", None) == "text"]
    text = "\n".join(parts).strip()
    return (text or None), _usage_tokens(getattr(msg, "usage", None))
