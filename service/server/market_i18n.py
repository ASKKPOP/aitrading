"""Response-layer localization for the /financial-events free-text — and, on
the same two tiers, the desk-cycle free text behind /automation/ai-analysis.

The market-intel caches (and the snapshot rows behind them) stay English — one
shared entry per payload, exactly like /api/market-intel/regime. The desk
journal stays English for the same reason plus one more: its reports are the
corpus desk_memory retrieves from, and a corpus that changes language with the
reader's setting is a corpus that no longer matches its own past. Translation
happens per request on the way out, keyed by the request's Accept-Language.

Two tiers of free text:

* Strings the platform itself authors (macro explanations, news-category
  labels, the stock factor phrases) resolve through the deterministic
  MARKET_PHRASES catalogue — no model call, no drift, native-review quality.
* External or model-authored strings (Alpha Vantage headlines, the LLM stock
  summary) have no catalogue entry, so they use a cached LLM translation. The
  request path is CACHE-ONLY — it never makes a blocking model call. A cache
  miss returns the English original immediately and schedules a background
  thread to translate + populate the cache, so the same string localizes on a
  later request (the page polls every 60s). Each unique string is translated
  once per language and reused across users and snapshot refreshes.

  This matters because the model is remote and slow: translating a dozen news
  headlines inline once hung the /financial-events news endpoint past the
  gateway timeout, and Promise.all on the frontend turned that into a blank
  board for every non-English viewer. English-now / localized-soon keeps the
  endpoint fast and the board always populated.

Everything here is fail-soft: no path raises, and no path blocks on the model.
Localizing a dashboard must never be able to 500 — or hang — a market-data
endpoint.
"""

from __future__ import annotations

import copy
import hashlib
import os
import re
import threading
from collections import OrderedDict
from typing import Any, Optional

from analysis_agents import LANG_NAMES, normalize_lang
from cache import get_json, set_json
from desk_i18n_data import DESK_PHRASES
from llm_client import (
    LlmContext,
    generate_text,
    llm_configured,
    reset_llm_context,
    set_llm_context,
)
from market_i18n_data import MARKET_PHRASES

# Tier C translation is pinned to a dedicated provider/model — deliberately NOT
# the platform's live gpt-oss, which is both slow (~16s/call) and the SPOF for
# every trading decision. Claude Sonnet answers in ~5s over the Anthropic API,
# a separate resource that never competes with the trading daemon. Overridable
# by env for ops (an empty MARKET_I18N_PROVIDER falls back to default resolution).
_XLATE_PROVIDER = os.getenv("MARKET_I18N_PROVIDER", "anthropic").strip().lower()
_XLATE_MODEL = os.getenv("MARKET_I18N_MODEL", "claude-sonnet-5").strip()


def _warm_enabled() -> bool:
    """Whether cache-miss external strings (Tier C) get LLM-translated at all.

    ON by default now that translation runs on a dedicated model (Claude Sonnet,
    see _XLATE_PROVIDER) rather than the trading gpt-oss — so it no longer risks
    the SPOF, only Anthropic API tokens. MARKET_I18N_LLM_WARM=0 is the cost
    kill-switch. Tiers A (enum labels, frontend) and B (our own catalogue) need
    no model and are always on; only external, model-authored free text
    (Alpha Vantage headlines, the AI stock summary) is gated here and degrades
    to its English original when off or on a translation failure."""
    return os.getenv("MARKET_I18N_LLM_WARM", "true").strip().lower() in {"1", "true", "yes", "on"}

# ── catalogue index (exact + interpolated), built once at import ────────────
# Two catalogues, one index: MARKET_PHRASES is the market-intel free text,
# DESK_PHRASES the desk-cycle gate-skip reasons. They are kept in separate data
# modules because they are separate surfaces, but the matcher and the Tier-C
# fallback behind them are the same, so there is one lookup rather than two.
_EXACT: dict[str, dict[str, str]] = {}
_PATTERNS: list[tuple[re.Pattern[str], dict[str, str]]] = []
for _en, _variants in {**MARKET_PHRASES, **DESK_PHRASES}.items():
    if "{}" in _en:
        _rx = "(.*?)".join(re.escape(part) for part in _en.split("{}"))
        _PATTERNS.append((re.compile(f"^{_rx}$", re.DOTALL), _variants))
    else:
        _EXACT[_en] = _variants

# Cached LLM translations live under this prefix. A week is long enough that a
# headline stays warm across refreshes, short enough that the catalogue growing
# to cover a phrase eventually wins.
_XLATE_TTL_SECONDS = 7 * 24 * 3600
# Batch size for the numbered translate prompt. Small chunks keep a batch of
# paragraph-length stock summaries well under the token ceiling so the tail
# lines can't truncate (the salvage-partial lesson from the research pipeline).
_BATCH = 5


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


# In-process translation cache. Prod runs Redis-less (get_json/set_json no-op),
# so the shared KV cannot hold a warmed translation between the background
# thread that produces it and the request that should read it — without this the
# whole warm produces nothing. The backend is a single uvicorn worker, so one
# process-local dict is shared by every request and the warm threads. KV is
# still written/read through as a second layer for the day Redis returns (and to
# share across workers then); on prod today that layer is simply inert.
_MEM_CACHE: "OrderedDict[str, str]" = OrderedDict()
_MEM_CACHE_MAX = 5000
_MEM_CACHE_LOCK = threading.Lock()


def _cache_get(key: str) -> Optional[str]:
    with _MEM_CACHE_LOCK:
        val = _MEM_CACHE.get(key)
        if val is not None:
            _MEM_CACHE.move_to_end(key)
            return val
    kv = get_json(key)  # None on a Redis-less prod; a hit warms the mem layer
    if isinstance(kv, str):
        with _MEM_CACHE_LOCK:
            _MEM_CACHE[key] = kv
            _MEM_CACHE.move_to_end(key)
        return kv
    return None


def _cache_put(key: str, val: str) -> None:
    with _MEM_CACHE_LOCK:
        _MEM_CACHE[key] = val
        _MEM_CACHE.move_to_end(key)
        while len(_MEM_CACHE) > _MEM_CACHE_MAX:
            _MEM_CACHE.popitem(last=False)
    set_json(key, val, ttl_seconds=_XLATE_TTL_SECONDS)  # inert without Redis


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
    # Budget the reply by INPUT length, not a flat per-line count: a stock
    # summary is a whole paragraph (~200 output tokens), and a fixed ~48/line
    # ceiling truncated the tail of a summary batch — the model returned the
    # first few lines and dropped the rest, so those summaries never localized.
    # ~1.2x the input character count leaves headroom for CJK expansion.
    max_tokens = min(4096, 200 + int(sum(len(t) for t in texts) * 1.2))
    # Pin to the dedicated translation provider (Sonnet) so this never routes to
    # the trading gpt-oss. source='rule' with no user/agent meters it to the
    # platform. An empty provider leaves default resolution in place.
    token = None
    if _XLATE_PROVIDER:
        token = set_llm_context(LlmContext(
            source="rule", provider=_XLATE_PROVIDER, model=_XLATE_MODEL or None))
    try:
        reply = generate_text(prompt, max_tokens=max_tokens, temperature=0.2, tier="brief")
    finally:
        if token is not None:
            reset_llm_context(token)
    if not reply:
        return {}
    parsed = _parse_numbered(reply, len(texts))
    out: dict[str, str] = {}
    for i, source in enumerate(texts):
        translated = parsed.get(i + 1)
        if translated:
            out[source] = translated
    return out


# Keys whose translation is being warmed right now, so concurrent requests
# (and the 60s poll) don't spawn a second thread for the same string.
_inflight: set[str] = set()
_inflight_lock = threading.Lock()


def _warm(texts: list[str], lang: str) -> None:
    """Translate a set of cache-miss strings and populate the KV cache. Runs off
    the request path (a background thread), so its latency is invisible to the
    caller. Always clears the in-flight marks it set, even on failure."""
    try:
        for start in range(0, len(texts), _BATCH):
            chunk = texts[start:start + _BATCH]
            translated = _llm_translate_batch(chunk, lang)
            for source, value in translated.items():
                if value:
                    _cache_put(_cache_key(source, lang), value)
    finally:
        with _inflight_lock:
            for text in texts:
                _inflight.discard(_cache_key(text, lang))


def _schedule_warm(texts: list[str], lang: str) -> None:
    """Claim the not-yet-in-flight misses and warm them in a daemon thread.
    Split out so tests can drive warming synchronously."""
    claimed: list[str] = []
    with _inflight_lock:
        for text in texts:
            key = _cache_key(text, lang)
            if key not in _inflight:
                _inflight.add(key)
                claimed.append(text)
    if not claimed or not llm_configured():
        # Nothing to do, or no model — release any marks we optimistically set.
        if claimed:
            with _inflight_lock:
                for text in claimed:
                    _inflight.discard(_cache_key(text, lang))
        return
    threading.Thread(target=_warm, args=(claimed, lang), daemon=True).start()


def localize_texts(texts: list[Any], lang: str) -> list[Any]:
    """Localize a list of strings, aligned 1:1 with the input.

    Cache-only and non-blocking: catalogue hits and cached translations resolve
    inline; anything else returns the English original and is queued for a
    background translation that a later request will pick up from cache. Never
    calls the model on the request path. Non-string / empty entries pass
    through untouched; English is a no-op.
    """
    lang = normalize_lang(lang)
    if lang == "en":
        return list(texts)

    result: list[Any] = list(texts)
    misses: list[str] = []  # unique cache-miss strings to warm
    seen: set[str] = set()
    for i, text in enumerate(texts):
        if not isinstance(text, str) or not text.strip():
            continue
        hit = _catalogue(text, lang)
        if hit is not None:
            result[i] = hit
            continue
        cached = _cache_get(_cache_key(text, lang))
        if cached is not None:
            result[i] = cached
            continue
        # Cache miss: keep the English original now, warm it for next time.
        if text not in seen:
            seen.add(text)
            misses.append(text)

    # Warming is gated: without a dedicated translation model, external free
    # text simply stays English rather than loading the trading SPOF.
    if misses and _warm_enabled():
        _schedule_warm(misses, lang)
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


def localize_desk_cycles(cycles: Any, lang: str) -> Any:
    """Localize the free text inside /automation/ai-analysis cycles.

    Two kinds of string live in a cycle, and both come out of the journal in
    English: the gate-skip REASONS the run engine writes (catalogue hits, see
    desk_i18n_data) and the desk's own written REPORT, which the model authors
    and so has no catalogue entry — it takes the cached-translation path like a
    news headline. Cache-only and non-blocking, exactly like the market
    payloads: a first read of a new report shows English and the next poll
    (60s) shows it localized.

    Transition reasons are deliberately NOT touched here. Those are stable
    codes ('stop_event:max_loss', 'created'), and the frontend already renders
    them through its own REASON_TEXT map — translating them server-side would
    turn a code the client can still recognise into prose it cannot.
    """
    if normalize_lang(lang) == "en" or not isinstance(cycles, list):
        return cycles
    cycles = copy.deepcopy(cycles)
    strings: list[str] = []
    slots: list[tuple[Any, Any]] = []

    def _collect(container: Any, key: Any) -> None:
        val = container.get(key) if isinstance(container, dict) else None
        if isinstance(val, str) and val.strip():
            strings.append(val)
            slots.append((container, key))

    for cycle in cycles:
        if not isinstance(cycle, dict):
            continue
        for cell in cycle.get("runs") or []:
            if not isinstance(cell, dict):
                continue
            _collect(cell, "report")
            for skip in cell.get("skips") or []:
                _collect(skip, "reason")

    if strings:
        localized = localize_texts(strings, lang)
        for (container, key), value in zip(slots, localized):
            container[key] = value
    return cycles
