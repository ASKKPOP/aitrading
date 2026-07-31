"""Response-layer localization for the /financial-events free-text.

The market-intel caches (and the snapshot rows behind them) stay English — one
shared entry per payload, exactly like /api/market-intel/regime. Translation
happens per request on the way out, keyed by the request's Accept-Language.

Two tiers of free text:

* Strings the platform itself authors (macro explanations, news-category
  labels, the stock factor phrases) resolve through the deterministic
  MARKET_PHRASES catalogue — no model call, no drift, native-review quality.
* External or model-authored strings (Alpha Vantage headlines, the LLM stock
  summary) have no catalogue entry, so they fall through to a cached LLM
  translation. Each unique string is translated once per language and reused
  across users and snapshot refreshes via the shared KV cache. A failed,
  dropped, or unconfigured translation falls back to the English original
  rather than blocking the payload — English is always the safe answer.

Everything here is fail-soft: no path raises. Localizing a dashboard must never
be able to 500 a market-data endpoint.
"""

from __future__ import annotations

import copy
import hashlib
import re
from typing import Any, Optional

from analysis_agents import LANG_NAMES, normalize_lang
from cache import get_json, set_json
from llm_client import generate_text, llm_configured
from market_i18n_data import MARKET_PHRASES

# ── catalogue index (exact + interpolated), built once at import ────────────
_EXACT: dict[str, dict[str, str]] = {}
_PATTERNS: list[tuple[re.Pattern[str], dict[str, str]]] = []
for _en, _variants in MARKET_PHRASES.items():
    if "{}" in _en:
        _rx = "(.*?)".join(re.escape(part) for part in _en.split("{}"))
        _PATTERNS.append((re.compile(f"^{_rx}$", re.DOTALL), _variants))
    else:
        _EXACT[_en] = _variants

# Cached LLM translations live under this prefix. A week is long enough that a
# headline stays warm across refreshes, short enough that the catalogue growing
# to cover a phrase eventually wins.
_XLATE_TTL_SECONDS = 7 * 24 * 3600
# Batch size for the numbered translate prompt. Small chunks keep any single
# reply well short of the token ceiling so a long headline can't truncate the
# lines after it (the salvage-partial lesson from the research pipeline).
_BATCH = 8


def _catalogue(text: str, lang: str) -> Optional[str]:
    """Deterministic lookup. Returns the localized string or None on a miss."""
    variants = _EXACT.get(text)
    if variants:
        return variants.get(lang) or text
    for pattern, variants in _PATTERNS:
        match = pattern.match(text)
        if not match:
            continue
        template = variants.get(lang)
        if not template:
            return text
        try:
            return template.format(*match.groups())
        except (IndexError, KeyError, ValueError):
            return text
    return None


def _cache_key(text: str, lang: str) -> str:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    return f"mktxlate:{lang}:{digest}"


def _parse_numbered(reply: str, count: int) -> dict[int, str]:
    """Pull `N. text` lines out of an LLM reply into {index: text}.

    Tolerant of blank lines and stray prose: only lines that start with a
    number and a dot are taken, and an index outside 1..count is dropped.
    """
    out: dict[int, str] = {}
    for line in reply.splitlines():
        m = re.match(r"^\s*(\d+)\s*[.)]\s*(.+?)\s*$", line)
        if not m:
            continue
        idx = int(m.group(1))
        if 1 <= idx <= count:
            out[idx] = m.group(2).strip()
    return out


def _llm_translate_batch(texts: list[str], lang: str) -> dict[str, str]:
    """Translate a de-duplicated batch. Returns {source: translated} for the
    lines that came back cleanly; missing lines are simply absent so the caller
    keeps the English original."""
    if not texts or not llm_configured():
        return {}
    lang_name = LANG_NAMES.get(lang, "English")
    numbered = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(texts))
    prompt = (
        f"You are a professional financial translator. Translate each numbered "
        f"line into {lang_name}. The lines are short phrases from a markets "
        f"dashboard: news headlines, and stock or macro commentary.\n"
        "Rules:\n"
        "- Preserve ticker symbols, numbers, %, $ and proper nouns exactly.\n"
        "- Use natural, concise financial register — not word-for-word.\n"
        "- Return ONLY the translations, one per line, each prefixed with its "
        'number and a period, e.g. "1. ...".\n'
        f"- Output exactly {len(texts)} lines, numbered 1 to {len(texts)}, in "
        "the same order. No preamble, no extra lines.\n\n"
        f"{numbered}\n"
    )
    # ~48 tokens/line covers a headline plus CJK expansion, with headroom.
    max_tokens = min(2400, 80 + 48 * len(texts))
    reply = generate_text(prompt, max_tokens=max_tokens, temperature=0.2, tier="brief")
    if not reply:
        return {}
    parsed = _parse_numbered(reply, len(texts))
    out: dict[str, str] = {}
    for i, source in enumerate(texts):
        translated = parsed.get(i + 1)
        if translated:
            out[source] = translated
    return out


def localize_texts(texts: list[Any], lang: str) -> list[Any]:
    """Localize a list of strings, aligned 1:1 with the input.

    Non-string / empty entries pass through untouched. English is a no-op.
    """
    lang = normalize_lang(lang)
    if lang == "en":
        return list(texts)

    result: list[Any] = list(texts)
    # Collect the strings that need the LLM (catalogue miss, cache miss).
    pending: dict[str, list[int]] = {}
    for i, text in enumerate(texts):
        if not isinstance(text, str) or not text.strip():
            continue
        hit = _catalogue(text, lang)
        if hit is not None:
            result[i] = hit
            continue
        cached = get_json(_cache_key(text, lang))
        if isinstance(cached, str):
            result[i] = cached
            continue
        pending.setdefault(text, []).append(i)

    if pending:
        unique = list(pending.keys())
        for start in range(0, len(unique), _BATCH):
            chunk = unique[start:start + _BATCH]
            translated = _llm_translate_batch(chunk, lang)
            for source in chunk:
                value = translated.get(source)
                if not value:
                    continue  # keep English original; retry on a later request
                set_json(_cache_key(source, lang), value, ttl_seconds=_XLATE_TTL_SECONDS)
                for idx in pending[source]:
                    result[idx] = value
    return result


def localize_text(text: Any, lang: str) -> Any:
    return localize_texts([text], lang)[0]


# ── per-payload localizers ─────────────────────────────────────────────────
# Each deep-copies before mutating: the argument is the shared English cache
# object, and mutating it would poison every other language's response.


def localize_news_payload(payload: dict[str, Any], lang: str) -> dict[str, Any]:
    if normalize_lang(lang) == "en" or not isinstance(payload, dict):
        return payload
    payload = copy.deepcopy(payload)
    # Gather every free-text string across categories into one batch so the
    # whole page localizes in as few model calls as the cache allows.
    strings: list[str] = []
    slots: list[tuple[Any, Any]] = []  # (container, key)

    def _collect(container: Any, key: Any) -> None:
        val = container.get(key) if isinstance(container, dict) else None
        if isinstance(val, str) and val.strip():
            strings.append(val)
            slots.append((container, key))

    for section in payload.get("categories") or []:
        if not isinstance(section, dict):
            continue
        _collect(section, "label")
        _collect(section, "description")
        summary = section.get("summary")
        if isinstance(summary, dict):
            _collect(summary, "top_headline")
        for item in section.get("items") or []:
            if isinstance(item, dict):
                _collect(item, "title")
                _collect(item, "summary")

    if strings:
        localized = localize_texts(strings, lang)
        for (container, key), value in zip(slots, localized):
            container[key] = value
    return payload


def localize_macro_payload(payload: dict[str, Any], lang: str) -> dict[str, Any]:
    if normalize_lang(lang) == "en" or not isinstance(payload, dict):
        return payload
    payload = copy.deepcopy(payload)
    strings: list[str] = []
    slots: list[tuple[Any, Any]] = []

    meta = payload.get("meta")
    if isinstance(meta, dict) and isinstance(meta.get("summary"), str) and meta["summary"].strip():
        strings.append(meta["summary"])
        slots.append((meta, "summary"))
    for signal in payload.get("signals") or []:
        if not isinstance(signal, dict):
            continue
        for key in ("label", "explanation"):
            val = signal.get(key)
            if isinstance(val, str) and val.strip():
                strings.append(val)
                slots.append((signal, key))

    if strings:
        localized = localize_texts(strings, lang)
        for (container, key), value in zip(slots, localized):
            container[key] = value
    return payload


def _localize_stock_analysis(item: dict[str, Any], strings: list[str], slots: list[tuple[Any, Any]]) -> None:
    """Queue a single stock analysis dict's free text (summary + factors)."""
    summary = item.get("summary")
    if isinstance(summary, str) and summary.strip():
        strings.append(summary)
        slots.append((item, "summary"))
    for list_key in ("bullish_factors", "risk_factors"):
        factors = item.get(list_key)
        if isinstance(factors, list):
            for i, factor in enumerate(factors):
                if isinstance(factor, str) and factor.strip():
                    strings.append(factor)
                    slots.append((factors, i))
    analysis = item.get("analysis")
    if isinstance(analysis, dict):
        for list_key in ("bullish_factors", "risk_factors"):
            factors = analysis.get(list_key)
            if isinstance(factors, list):
                for i, factor in enumerate(factors):
                    if isinstance(factor, str) and factor.strip():
                        strings.append(factor)
                        slots.append((factors, i))


def localize_featured_stocks_payload(payload: dict[str, Any], lang: str) -> dict[str, Any]:
    if normalize_lang(lang) == "en" or not isinstance(payload, dict):
        return payload
    payload = copy.deepcopy(payload)
    strings: list[str] = []
    slots: list[tuple[Any, Any]] = []
    for item in payload.get("items") or []:
        if isinstance(item, dict):
            _localize_stock_analysis(item, strings, slots)
    if strings:
        localized = localize_texts(strings, lang)
        for (container, key), value in zip(slots, localized):
            container[key] = value
    return payload


def localize_stock_latest_payload(payload: dict[str, Any], lang: str) -> dict[str, Any]:
    if normalize_lang(lang) == "en" or not isinstance(payload, dict):
        return payload
    payload = copy.deepcopy(payload)
    strings: list[str] = []
    slots: list[tuple[Any, Any]] = []
    _localize_stock_analysis(payload, strings, slots)
    if strings:
        localized = localize_texts(strings, lang)
        for (container, key), value in zip(slots, localized):
            container[key] = value
    return payload


def localize_stock_history_payload(payload: dict[str, Any], lang: str) -> dict[str, Any]:
    if normalize_lang(lang) == "en" or not isinstance(payload, dict):
        return payload
    payload = copy.deepcopy(payload)
    strings: list[str] = []
    slots: list[tuple[Any, Any]] = []
    for entry in payload.get("history") or []:
        if isinstance(entry, dict):
            summary = entry.get("summary")
            if isinstance(summary, str) and summary.strip():
                strings.append(summary)
                slots.append((entry, "summary"))
    if strings:
        localized = localize_texts(strings, lang)
        for (container, key), value in zip(slots, localized):
            container[key] = value
    return payload
