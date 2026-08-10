"""Translate the login-gated guide documents into every UI language.

Usage (from repo root):
    .venv/bin/python docs/design/_gen_doc_translations.py            # all gaps
    .venv/bin/python docs/design/_gen_doc_translations.py --only guide,smart
    .venv/bin/python docs/design/_gen_doc_translations.py --dry-run

Why this exists
---------------
The docs rail shipped 13 groups, of which exactly one (`market-hours`) existed
in all six languages. Everything else was en/ko, and `gateway` was Korean
ONLY — so an English reader of "Live Trading Gateway" was served a Korean
document by DocsPage's `docs[0]` last-resort fallback. The alert, error and
email catalogues were all complete; the long-form documentation was the one
surface where choosing Bahasa Indonesia still gave you English.

How it translates
-----------------
TEXT NODES ONLY. The document is parsed, every user-visible NavigableString is
collected, translated in batches, and written back into the SAME tree. The
model never sees or emits markup, so it cannot unbalance a tag, drop a table
row or invent a style block — the failure mode that makes "translate this HTML"
prompts unusable on a 54KB document.

Skipped: <script>, <style>, <code>, <pre>, and anything that is pure
punctuation, digits or a bare identifier — a ticker, a P&L figure and a config
key must survive translation byte-for-byte.

Batches are validated on COUNT: n strings in, n strings out, or the batch is
split and retried, and a batch that still fails keeps its source text. A
partially-translated document is a real outcome here and is strictly better
than a corrupted one — the untranslated remainder reads as the source language,
which is exactly what the reader got before this script existed.

Provenance
----------
Output is machine-authored and pending native review, the same standing caveat
carried by notifications_i18n and i18n_errors_data. Each generated file records
that in an HTML comment so a reviewer can tell hand-written copy from this.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "service" / "server"))

from analysis_agents import LANG_NAMES  # noqa: E402
from llm_client import generate_text, llm_configured  # noqa: E402

DOCS = REPO / "docs"

# Markup vs text. The capturing group makes str.split alternate
# text, markup, text, markup, … so a span's kind is its index parity.
# Comments and doctype are matched first so a `>` inside them cannot end a tag.
_TOKEN = re.compile(r"(<!--.*?-->|<![^>]*>|<[^>]*>)", re.S)
_TAG_NAME = re.compile(r"<\s*(/?)\s*([a-zA-Z][a-zA-Z0-9]*)")

# group -> (preferred source doc, its language). English first where it exists:
# it is the language these documents were drafted in, so it is the shortest
# path to the target. `gateway` has only ever existed in Korean.
SOURCES: dict[str, tuple[str, str]] = {
    # owner_only groups (2026-07-29): operator material, English-only until
    # Henry asked for full localization. Same pipeline, same caveats.
    "ops-keys": ("design/api-keys-reference-en.html", "en"),
    "architecture": ("12-system-architecture-report.html", "en"),
    "extensions": ("reports/2026-07-25-extension-e1-e2-analysis.html", "en"),
    "guide": ("design/ai-trading-guide-en.html", "en"),
    "gateway": ("design/live-trading-gateway-guide.html", "ko"),
    "smart": ("design/smart-trading-features-en.html", "en"),
    "top10": ("research/parameters/2-ai-trading-parameters-en.html", "en"),
    "hybrid": ("research/parameters/2-hybrid-strategy-en.html", "en"),
    "decisions": ("design/decisions-guide-en.html", "en"),
    "how-it-works": ("design/how-ai-trading-works-en.html", "en"),
    "automation": ("design/automation-page-guide-en.html", "en"),
    "liq-defense": ("plan/16-liquidation-defense-daemon.html", "en"),
    "trading-skills": ("plan/20-trading-skills.html", "en"),
    "desk-rag": ("plan/22-desk-retrieval-rag.html", "en"),
    "desk-learning": ("plan/22-phase3-learning-to-profit.html", "en"),
}

# Markdown-sourced groups: the build converts these to HTML, so translate the
# markdown and let build_guide_content.py render it through the same shell.
MD_SOURCES: dict[str, tuple[str, str]] = {
    "psych-report": ("research/parameters/2-chart-vs-human-psychology-report-en.md", "en"),
    "framework": ("research/parameters/2-hybrid-strategy-framework.md", "en"),
    "backtest-report": ("research/parameters/3-phase4-backtest-report.md", "en"),
}

# Where each generated file lands: group -> (template, is_markdown).
OUT_PATTERN: dict[str, str] = {
    "ops-keys": "design/api-keys-reference-{lang}.html",
    "architecture": "12-system-architecture-report-{lang}.html",
    "extensions": "reports/2026-07-25-extension-e1-e2-analysis-{lang}.html",
    "guide": "design/ai-trading-guide-{lang}.html",
    "gateway": "design/live-trading-gateway-guide-{lang}.html",
    "smart": "design/smart-trading-features-{lang}.html",
    "top10": "research/parameters/2-ai-trading-parameters-{lang}.html",
    "hybrid": "research/parameters/2-hybrid-strategy-{lang}.html",
    "decisions": "design/decisions-guide-{lang}.html",
    "how-it-works": "design/how-ai-trading-works-{lang}.html",
    "automation": "design/automation-page-guide-{lang}.html",
    "liq-defense": "plan/16-liquidation-defense-daemon-{lang}.html",
    "trading-skills": "plan/20-trading-skills-{lang}.html",
    "desk-rag": "plan/22-desk-retrieval-rag-{lang}.html",
    "desk-learning": "plan/22-phase3-learning-to-profit-{lang}.html",
    "psych-report": "research/parameters/2-chart-vs-human-psychology-report-{lang}.md",
    "framework": "research/parameters/2-hybrid-strategy-framework-{lang}.md",
    "backtest-report": "research/parameters/3-phase4-backtest-report-{lang}.md",
}

# Languages each group already publishes (from build_guide_content.SOURCES).
EXISTING: dict[str, set[str]] = {
    "ops-keys": {"en"},
    "architecture": {"en"},
    "extensions": {"en"},
    "guide": {"en", "ko"},
    "gateway": {"ko"},
    "smart": {"en", "ko"},
    "top10": {"en", "ko"},
    "hybrid": {"en", "ko"},
    "decisions": {"en", "ko", "ja", "th", "vi"},
    "how-it-works": {"en"},
    "automation": {"en"},
    "liq-defense": {"en"},
    "trading-skills": {"en"},
    "psych-report": {"en", "ko"},
    "framework": {"en", "ko"},
    "backtest-report": {"en", "ko"},
    "desk-rag": {"en"},
    "desk-learning": {"en"},
}

SKIP_PARENTS = {"script", "style", "pre", "samp", "kbd"}
# `code` is conditional, not absolute. Skipping it wholesale is right for
# `RUN_AI_ROUTING` and wrong for `<code>계정(account)</code>` — the Korean
# gateway guide uses <code> for UI field labels, so a blanket skip left a
# Korean word sitting in the middle of the Indonesian, Japanese, Thai,
# Vietnamese AND English translations. An identifier is ASCII; prose is not.
CONDITIONAL_SKIP = {"code"}
_NON_ASCII = re.compile(r"[^\x00-\x7f]")
# Hangul surviving into a non-Korean document means the model echoed the input
# instead of translating it. Cheap to detect, so it is worth a repair pass.
_HANGUL = re.compile(r"[가-힣]")
# Languages that render in their own script. For these, a Latin string that
# came back untouched is an echo no matter how short it is.
_NATIVE_SCRIPT = {
    "ko": re.compile(r"[가-힣]"),
    "ja": re.compile(r"[぀-ヿ一-鿿]"),
    "th": re.compile(r"[฀-๿]"),
}
# A bare `&` that is not already an entity. The model decodes `&amp;` in the
# text it is handed and returns a literal `&`, which splices back as invalid
# markup — `guide-id` shipped `Fear & Greed` inside an SVG <text> where every
# other language had `Fear &amp; Greed`. Browsers tolerated it; XML did not.
_BARE_AMP = re.compile(r"&(?!(?:[a-zA-Z][a-zA-Z0-9]{1,31}|#\d{1,7}|#[xX][0-9a-fA-F]{1,6});)")
BANNER = ("<!-- machine-translated from {src} by "
          "docs/design/_gen_doc_translations.py — pending native review -->\n")

BATCH_CHARS = 1800
MAX_WORKERS = 6


def _translatable(text: str) -> bool:
    """Is this string worth a model call?

    A ticker (`BTCUSDT`), a number (`-$1,099`), a config key
    (`RUN_AI_ROUTING`) and a lone bullet must come through untouched — sending
    them costs tokens and invites the model to "helpfully" localize a symbol
    that the product matches on literally.
    """
    s = text.strip()
    if len(s) < 2:
        return False
    if not re.search(r"[A-Za-z가-힣぀-ヿ一-鿿]", s):
        return False          # punctuation / digits only
    if re.fullmatch(r"[A-Z0-9_.:\-/]+", s):
        return False          # SCREAMING_IDENTIFIER, ticker, path
    return True


def _is_echo(src: str, out: str, lang: str) -> bool:
    """Did the model hand this string back instead of translating it?

    Hangul surviving into a non-Korean document is the unambiguous case, and
    it was the only case the first repair pass checked — which is why a
    Korean-source document came out clean while `STAGE 3 → STAGE 4` sat
    beside `ステージ1 → ステージ2` in the Japanese one, and ten of fifteen
    gateway sub-headings stayed English in Thai and Vietnamese. Those are
    echoes too; they just echo English, which no script test can see.

    So the real signal is simpler: the output is byte-identical to the input.
    Retrying costs a call and, after the attempts run out, the source is kept
    anyway — the same outcome as not checking. The false positives are
    strings that SHOULD come back unchanged (a journal title, a proper noun),
    and paying a couple of calls to re-confirm those is the cheaper mistake.
    """
    if _HANGUL.search(out) and lang != "ko":
        return True
    if out.strip() != src.strip():
        return False
    # Identical. Only meaningful if there was something to translate: pure
    # punctuation, digits or a bare ticker is legitimately invariant.
    words = re.findall(r"[A-Za-z]{2,}", src)
    if not words:
        return False
    native = _NATIVE_SCRIPT.get(lang)
    if native:
        # ja/th render in their own script, so ANY Latin word that came back
        # untouched is an echo. Requiring two words here missed `STAGE 3`,
        # which sat beside `ステージ1` in the Japanese top-10 document.
        return not native.search(out)
    # vi/id/en share the Latin alphabet, so "unchanged" is only suspicious
    # once there is a phrase rather than a single word.
    return len(words) >= 2


def _chunks(items: list[str]) -> list[list[int]]:
    """Index batches capped by character budget, so one batch is one call."""
    out: list[list[int]] = []
    cur: list[int] = []
    size = 0
    for i, s in enumerate(items):
        if cur and size + len(s) > BATCH_CHARS:
            out.append(cur)
            cur, size = [], 0
        cur.append(i)
        size += len(s)
    if cur:
        out.append(cur)
    return out


def _translate_batch(strings: list[str], lang: str, depth: int = 0) -> list[str]:
    """n in, n out — or split and retry, and finally give back the source.

    The count check is the whole safety story: the caller substitutes
    positionally, so a model that merges two list items or helpfully drops an
    empty one would silently shift every later string into the wrong element.
    """
    name = LANG_NAMES[lang]
    prompt = (
        f"Translate each string in this JSON array into {name}.\n"
        "This is documentation for a retail algorithmic-trading product. Keep "
        "the register plain and instructional.\n"
        "RULES:\n"
        f"- Return ONLY a JSON array of exactly {len(strings)} strings, in the "
        "same order. No prose, no markdown fence.\n"
        "- Preserve leading and trailing whitespace of each string.\n"
        "- Do NOT translate: ticker symbols, code identifiers, environment "
        "variable names, numbers, currency amounts, or the product name "
        "Sooppiy.\n"
        "- Keep any markdown syntax (**, `, #, |, -) exactly where it is.\n"
        "- A string that is already in the target language comes back "
        "unchanged.\n\n"
        + json.dumps(strings, ensure_ascii=False)
    )
    text = generate_text(prompt, max_tokens=4000, temperature=0.1, tier="brief")
    if text:
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if match:
            try:
                got = json.loads(match.group(0))
                if isinstance(got, list) and len(got) == len(strings):
                    return [str(g) for g in got]
            except json.JSONDecodeError:
                pass
    if len(strings) > 1 and depth < 4:
        mid = len(strings) // 2
        return (_translate_batch(strings[:mid], lang, depth + 1)
                + _translate_batch(strings[mid:], lang, depth + 1))
    print(f"      ! batch of {len(strings)} kept as source", file=sys.stderr)
    return strings


def _translate_all(strings: list[str], lang: str) -> list[str]:
    """Translate, then verify and repair.

    A count-checked batch can still come back wrong: with a long array the
    model sometimes ECHOES entries rather than translating them, which passes
    every structural check because the shape is right. That is not theoretical
    — the first full run left 71 Korean fragments in the Japanese gateway
    guide and 56 in the Indonesian one, including SVG diagram labels, while
    reporting zero failed batches.

    Hangul in a non-Korean document is unambiguous evidence of an echo, so
    those entries are re-sent — alone, where a single string cannot hide in a
    crowd — until the document is clean or the retries run out.
    """
    out = list(strings)
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(_translate_batch, [strings[i] for i in idx], lang): idx
                   for idx in _chunks(strings)}
        for future, idx in futures.items():
            for pos, value in zip(idx, future.result()):
                out[pos] = value
    if lang == "ko":
        return out
    for attempt in range(3):
        stale = [i for i, v in enumerate(out) if _is_echo(strings[i], v, lang)]
        if not stale:
            break
        print(f"      repair {attempt + 1}: {len(stale)} untranslated")
        # One string per call: an echo happens when an entry is lost in a
        # long array, so retrying it in another long array repeats the bug.
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            futures = {pool.submit(_translate_batch, [strings[i]], lang): i
                       for i in stale}
            for future, i in futures.items():
                out[i] = future.result()[0]
    left = sum(1 for i, v in enumerate(out) if _is_echo(strings[i], v, lang))
    if left:
        print(f"      ! {left} string(s) came back unchanged", file=sys.stderr)
    return out


def translate_html(source: str, lang: str) -> str:
    """Splice translations into the ORIGINAL source; never re-serialize it.

    The obvious implementation — parse with BeautifulSoup, replace_with(), and
    str(soup) — silently destroys these documents. html.parser lower-cases
    attribute NAMES, and SVG attributes are case-sensitive: every `viewBox`
    came back as `viewbox`, every `refX` as `refx`, `markerWidth` as
    `markerwidth`. The tag counts still matched perfectly, which is why a
    structural diff called it clean, and all five inline pipeline diagrams
    would have shipped unscaled and arrow-less.

    So the markup is never rebuilt. The source is split into markup spans
    (`<...>`, comments, doctype) and text spans; only text spans are sent to
    the model and substituted back. Everything between `<` and `>` — casing,
    attribute order, whitespace, self-closing slashes — survives byte-for-byte
    because it is never parsed in the first place.
    """
    parts = _TOKEN.split(source)          # even = text, odd = markup
    skip_depth = 0
    in_code = 0
    idx: list[int] = []
    payload: list[str] = []
    for i, part in enumerate(parts):
        if i % 2:                          # markup: track the no-translate zones
            tag = _TAG_NAME.match(part)
            if tag and not part.rstrip().endswith("/>"):
                name = tag.group(2).lower()
                step = -1 if tag.group(1) else 1
                if name in SKIP_PARENTS:
                    skip_depth = max(0, skip_depth + step)
                elif name in CONDITIONAL_SKIP:
                    in_code = max(0, in_code + step)
            continue
        if skip_depth or not _translatable(part):
            continue
        # Inside <code>: translate prose, leave identifiers alone.
        if in_code and not _NON_ASCII.search(part):
            continue
        idx.append(i)
        payload.append(part)
    if not payload:
        return source
    print(f"      {len(payload)} text nodes")
    for i, value in zip(idx, _translate_all(payload, lang)):
        # Re-escape any `&` the model decoded on its way through. Same for
        # `<`: a text span cannot legally contain one, and a decoded `&lt;`
        # glues itself to the next tag — `health &lt; 0.60` came back as
        # `< 0.60</text>`, one invalid markup token, in ja/vi/id.
        parts[i] = _BARE_AMP.sub("&amp;", value).replace("<", "&lt;")
    out = "".join(parts)
    # `lang` is the one attribute we do rewrite, by targeted substitution on
    # the opening <html> tag alone.
    return re.sub(r"(<html\b[^>]*?)\slang=([\"'])[^\"']*\2",
                  rf"\1 lang=\g<2>{lang}\g<2>", out, count=1)


def translate_markdown(source: str, lang: str) -> str:
    """Markdown travels as lines, not nodes.

    Fenced code blocks and table separator rows (`|---|`) are held out: the
    first is code, the second is layout that a translator would happily turn
    into prose and break the table.
    """
    lines = source.split("\n")
    idx, payload = [], []
    fenced = False
    for i, line in enumerate(lines):
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if fenced or re.fullmatch(r"\s*\|?[\s:|-]+\|?\s*", line):
            continue
        if _translatable(line):
            idx.append(i)
            payload.append(line)
    if not payload:
        return source
    print(f"      {len(payload)} lines")
    for i, value in zip(idx, _translate_all(payload, lang)):
        lines[i] = value
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="comma-separated group names")
    ap.add_argument("--langs", help="comma-separated target languages")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not args.dry_run and not llm_configured():
        sys.exit("no LLM provider configured — set a key in .env")

    groups = {**SOURCES, **MD_SOURCES}
    wanted = set(args.only.split(",")) if args.only else set(groups)
    targets = set(args.langs.split(",")) if args.langs else set(LANG_NAMES)

    jobs = []
    for group, (rel, src_lang) in groups.items():
        if group not in wanted:
            continue
        for lang in sorted(targets):
            if lang in EXISTING.get(group, set()):
                continue
            jobs.append((group, rel, src_lang, lang))

    print(f"{len(jobs)} document(s) to generate")
    for group, rel, src_lang, lang in jobs:
        out_rel = OUT_PATTERN[group].format(lang=lang)
        print(f"  {group:16} {src_lang} -> {lang:3} {out_rel}")
        if args.dry_run:
            continue
        src_path = DOCS / rel
        if not src_path.exists():
            print(f"      ! source missing: {src_path}", file=sys.stderr)
            continue
        source = src_path.read_text(encoding="utf-8")
        # The banner is an HTML comment either way: markdown passes raw HTML
        # through, and build_guide_content renders these into the same shell.
        if out_rel.endswith(".md"):
            out = BANNER.format(src=rel) + translate_markdown(source, lang)
        else:
            out = BANNER.format(src=rel) + translate_html(source, lang)
        out_path = DOCS / out_rel
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(out, encoding="utf-8")
        print(f"      wrote {out_path.stat().st_size:,} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
