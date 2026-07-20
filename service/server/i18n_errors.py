"""Localization of user-facing API error messages.

Every route raises English — `HTTPException(detail=...)`, `ValueError`,
`StartConflict`. Translating at each of the ~290 raise sites would mean
threading a language through call chains that have no business knowing about
one, so instead the translation happens once, at the exception-handler
boundary in routes.py, keyed by the exact English message.

Consequences worth knowing:

* Raise sites stay untouched. Adding a new error needs no i18n work.
* An untranslated message falls through as English rather than failing.
* Messages built with an f-string are matched by pattern: the interpolated
  values are captured and re-inserted into the translation, so
  `f"Symbol {sym} not found"` localizes without knowing `sym` up front.

The catalogue itself lives in i18n_errors_data.py.
"""

from __future__ import annotations

import re
from typing import Optional

from analysis_agents import normalize_lang
from i18n_errors_data import MESSAGES

# `normalize_lang` already owns the supported set (ko/en/ja/th/vi) and the
# unknown -> en fallback; there must not be a second list to drift from it.

# ── pattern index ──────────────────────────────────────────────────────────
# Catalogue keys containing "{}" came from f-strings. Compile each into a
# regex once at import so lookup stays O(exact) for the common case and only
# falls back to a scan for the interpolated minority.

_EXACT: dict[str, dict[str, str]] = {}
_PATTERNS: list[tuple[re.Pattern[str], dict[str, str]]] = []

for _en, _variants in MESSAGES.items():
    if "{}" in _en:
        _rx = "(.*?)".join(re.escape(part) for part in _en.split("{}"))
        _PATTERNS.append((re.compile(f"^{_rx}$", re.DOTALL), _variants))
    else:
        _EXACT[_en] = _variants


def translate(text: str, lang: str) -> str:
    """English `text` rendered in `lang`, or unchanged if untranslated.

    Never raises: a bad pattern or a placeholder-count mismatch returns the
    English original. An error message is the worst possible place to throw.
    """
    lang = normalize_lang(lang)
    if lang == "en" or not text:
        return text

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
            # ValueError covers a stray brace in the translation. Any
            # malformed template loses to the English original.
            return text
    return text


def lang_from_request(headers) -> str:
    """Preferred language for a request, from the Accept-Language header.

    The frontend sends a bare code (the top-bar selection); browsers send a
    weighted list. Both parse the same way — take the first tag we support,
    in q-order, and fall back to English.
    """
    return _parse_accept_language(headers.get("accept-language"))


def _parse_accept_language(header: Optional[str]) -> str:
    if not header:
        return "en"
    tags: list[tuple[float, int, str]] = []
    for i, part in enumerate(header.split(",")):
        piece = part.strip()
        if not piece:
            continue
        tag, _, params = piece.partition(";")
        quality = 1.0
        for param in params.split(";"):
            key, _, value = param.strip().partition("=")
            if key.strip() == "q":
                try:
                    quality = float(value)
                except ValueError:
                    quality = 0.0
        # `i` keeps the sort stable at equal q, preserving header order.
        tags.append((-quality, i, tag.strip()))

    for _, _, tag in sorted(tags):
        if tag == "*":
            continue
        code = normalize_lang(tag)
        # normalize_lang maps anything unknown to "en", which would make the
        # first unsupported tag win over a supported one later in the list.
        if code != "en" or tag.lower().split("-")[0] == "en":
            return code
    return "en"
