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

# Per-call provider override (e.g. an automation rule that wants a specific
# provider). Thread/async safe; falls back to env-based selection when unset.
_provider_override: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "llm_provider_override", default=None
)


def set_provider_override(name: Optional[str]):
    """Set (or clear with None) the provider override for the current context.
    Returns the contextvars token so callers can reset."""
    return _provider_override.set(name.strip().lower() if name else None)


def reset_provider_override(token) -> None:
    _provider_override.reset(token)


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
        "claude-3-5-sonnet-latest", kind="anthropic"),
}

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


def resolve_provider() -> Optional[ActiveProvider]:
    """Return the active provider config, or None if no provider is usable."""
    explicit = _provider_override.get() or os.getenv("LLM_PROVIDER", "").strip().lower()
    model_override = os.getenv("LLM_MODEL", "").strip()

    def build(spec: ProviderSpec) -> Optional[ActiveProvider]:
        key = _get_key(spec)
        if not key and spec.name != "local":
            return None
        base_url = os.getenv(spec.base_url_env, "").strip() or spec.default_base_url
        model = model_override or spec.default_model
        if spec.name == "openrouter" and not model_override:
            model = os.getenv("OPENROUTER_MODEL", "").strip() or spec.default_model
        if spec.name == "local" and not model_override:
            model = os.getenv("LOCAL_LLM_MODEL", "").strip() or spec.default_model
        return ActiveProvider(spec=spec, api_key=key, base_url=base_url, model=model)

    if explicit:
        spec = _PROVIDERS.get(explicit)
        if not spec:
            logger.warning("Unknown LLM_PROVIDER=%r; supported: %s", explicit, ", ".join(_PROVIDERS))
            return None
        return build(spec)

    # Auto-detect: first provider (in registry order) with a key set.
    for spec in _PROVIDERS.values():
        if spec.name == "local":
            continue  # never auto-select local; require explicit LLM_PROVIDER=local
        built = build(spec)
        if built:
            return built
    return None


def llm_configured() -> bool:
    return resolve_provider() is not None


def active_provider_name() -> Optional[str]:
    ap = resolve_provider()
    return ap.spec.name if ap else None


def generate_text(
    prompt: str,
    *,
    system: Optional[str] = None,
    max_tokens: int = 400,
    temperature: float = 0.4,
) -> Optional[str]:
    """Generate text with the active provider. Returns None on any failure so
    callers can fall back to their own deterministic summary."""
    ap = resolve_provider()
    if ap is None:
        return None
    try:
        if ap.spec.kind == "anthropic":
            return _generate_anthropic(ap, prompt, system, max_tokens, temperature)
        return _generate_openai_compatible(ap, prompt, system, max_tokens, temperature)
    except Exception as exc:  # noqa: BLE001 - provider errors must not crash callers
        logger.warning("LLM generation failed (provider=%s): %s", ap.spec.name, exc)
        return None


def _generate_openai_compatible(ap, prompt, system, max_tokens, temperature) -> Optional[str]:
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
    if not resp.choices:
        return None
    content = resp.choices[0].message.content
    return content.strip() if isinstance(content, str) else None


def _generate_anthropic(ap, prompt, system, max_tokens, temperature) -> Optional[str]:
    import anthropic  # lazy import

    client = anthropic.Anthropic(api_key=ap.api_key)
    kwargs = {
        "model": ap.model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        kwargs["system"] = system
    msg = client.messages.create(**kwargs)
    parts = [b.text for b in msg.content if getattr(b, "type", None) == "text"]
    text = "\n".join(parts).strip()
    return text or None
