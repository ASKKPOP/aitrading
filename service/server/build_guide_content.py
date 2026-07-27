"""Build the login-gated guide/research content bundle.

Usage:  .venv/bin/python service/server/build_guide_content.py   (from repo root)

Copies the guide + research-parameter documents from docs/ into
service/server/guide_content/ (docs/ is .dockerignore'd — the image only
ships what lives under service/), converting markdown docs to styled HTML.
The output is COMMITTED; run this again whenever a source doc changes.

Requires the local dev extra `markdown` (not a runtime dependency):
    uv pip install markdown
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DOCS = REPO / "docs"
OUT = Path(__file__).resolve().parent / "guide_content"

# key → (source path, kind, lang, group, title)
SOURCES: list[dict] = [
    {"key": "guide-ko", "src": "design/ai-trading-guide.html", "kind": "html", "lang": "ko",
     "group": "guide", "title": "AI 자동매매 완전 가이드"},
    {"key": "guide-en", "src": "design/ai-trading-guide-en.html", "kind": "html", "lang": "en",
     "group": "guide", "title": "Full AI-Trading Pipeline Guide"},
    {"key": "gateway-ko", "src": "design/live-trading-gateway-guide.html", "kind": "html", "lang": "ko",
     "group": "gateway", "title": "실거래 게이트웨이 완전 가이드"},
    {"key": "smart-ko", "src": "design/smart-trading-features-ko.html", "kind": "html", "lang": "ko",
     "group": "smart", "title": "스마트 AI 판단 & 맞춤 알림"},
    {"key": "smart-en", "src": "design/smart-trading-features-en.html", "kind": "html", "lang": "en",
     "group": "smart", "title": "Smart AI Decisions & Personal Alerts"},
    {"key": "top10-en", "src": "research/parameters/2-ai-trading-parameters-en.html", "kind": "html",
     "lang": "en", "group": "top10", "title": "Top-10 Decision Parameters"},
    {"key": "top10-ko", "src": "research/parameters/2-ai-trading-parameters-ko.html", "kind": "html",
     "lang": "ko", "group": "top10", "title": "핵심 파라미터 TOP 10"},
    {"key": "hybrid-en", "src": "research/parameters/2-hybrid-strategy-en.html", "kind": "html",
     "lang": "en", "group": "hybrid", "title": "Hybrid Strategy: Charts × Psychology"},
    {"key": "hybrid-ko", "src": "research/parameters/2-hybrid-strategy-ko.html", "kind": "html",
     "lang": "ko", "group": "hybrid", "title": "하이브리드 전략: 차트 × 심리"},
    {"key": "psych-report-en", "src": "research/parameters/2-chart-vs-human-psychology-report-en.md",
     "kind": "md", "lang": "en", "group": "psych-report", "title": "Chart Analysis vs Human Psychology — Verified Numbers"},
    {"key": "psych-report-ko", "src": "research/parameters/2-chart-vs-human-psychology-report-ko.md",
     "kind": "md", "lang": "ko", "group": "psych-report", "title": "차트 분석 vs 인간 심리 — 검증된 수치"},
    {"key": "framework-en", "src": "research/parameters/2-hybrid-strategy-framework.md",
     "kind": "md", "lang": "en", "group": "framework", "title": "Hybrid Framework — Decision Stack & Checklists"},
    {"key": "framework-ko", "src": "research/parameters/2-hybrid-strategy-framework-ko.md",
     "kind": "md", "lang": "ko", "group": "framework", "title": "하이브리드 프레임워크 — 의사결정 스택 & 체크리스트"},
    {"key": "backtest-report-en", "src": "research/parameters/3-phase4-backtest-report.md",
     "kind": "md", "lang": "en", "group": "backtest-report", "title": "Phase-4 Strategy Backtest — Go/No-Go Result"},
    {"key": "backtest-report-ko", "src": "research/parameters/3-phase4-backtest-report-ko.md",
     "kind": "md", "lang": "ko", "group": "backtest-report", "title": "Phase-4 전략 백테스트 — Go/No-Go 결과"},
    {"key": "api-keys-en", "src": "design/api-keys-reference-en.html", "kind": "html", "lang": "en",
     "group": "ops-keys", "title": "API Keys Reference", "owner_only": True},
    {"key": "architecture-en", "src": "12-system-architecture-report.html", "kind": "html", "lang": "en",
     "group": "architecture", "title": "System Architecture & Technical Flow", "owner_only": True},
    # Engineering analysis behind the smart-routing + hot-issue features. Kept
    # owner_only alongside architecture: it carries file-level implementation
    # plans, LLM cost modelling and merge sequencing. The member-facing version
    # of this material is the `smart` group.
    {"key": "extension-e1-e2-en", "src": "reports/2026-07-25-extension-e1-e2-analysis.html",
     "kind": "html", "lang": "en", "group": "extensions",
     "title": "E1 Decision Routing & E2 Hot-Issue Daemon — Design Analysis", "owner_only": True},
]

GROUPS = [
    {"group": "guide", "ko": "완전 가이드", "en": "Full Guide"},
    {"group": "gateway", "ko": "실거래 게이트웨이", "en": "Live Trading Gateway"},
    {"group": "smart", "ko": "스마트 AI & 알림", "en": "Smart AI & Alerts"},
    {"group": "top10", "ko": "TOP 10 파라미터", "en": "Top-10 Parameters"},
    {"group": "hybrid", "ko": "하이브리드 전략", "en": "Hybrid Strategy"},
    {"group": "framework", "ko": "프레임워크 체크리스트", "en": "Framework Checklists"},
    {"group": "psych-report", "ko": "차트 vs 심리 리포트", "en": "Charts vs Psychology"},
    {"group": "backtest-report", "ko": "백테스트 결과", "en": "Backtest Result"},
    {"group": "ops-keys", "ko": "API 키 (관리자)", "en": "API Keys (owner)"},
    {"group": "architecture", "ko": "시스템 아키텍처 (관리자)", "en": "System Architecture (owner)"},
    {"group": "extensions", "ko": "확장 설계 분석 (관리자)", "en": "Extension Design Analysis (owner)"},
]

_MD_SHELL = """<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
:root{{ --page:#f9f9f7; --card:#fff; --surface:#f1f0ec; --grid:#e1e0d9; --ink:#0b0b0b;
  --ink2:#52514e; --muted:#898781; --accent:#2a78d6; --border:rgba(11,11,11,.1); }}
@media (prefers-color-scheme: dark){{
  :root{{ --page:#0d0d0d; --card:#202020; --surface:#1a1a19; --grid:#2c2c2a; --ink:#fff;
    --ink2:#c3c2b7; --accent:#3987e5; --border:rgba(255,255,255,.1); }} }}
*{{box-sizing:border-box}} body{{margin:0;background:var(--page);color:var(--ink);
  font-family:system-ui,-apple-system,"Segoe UI","Apple SD Gothic Neo",sans-serif;
  line-height:1.65;font-size:14.5px}}
main{{max-width:860px;margin:0 auto;padding:40px 22px 80px}}
h1{{font-size:26px;line-height:1.25;margin:0 0 6px}} h2{{font-size:19px;margin:32px 0 8px;
  padding-top:18px;border-top:1px solid var(--grid)}} h3{{font-size:15px;margin:20px 0 6px}}
p,li{{color:var(--ink2)}} strong{{color:var(--ink)}} a{{color:var(--accent)}}
table{{width:100%;border-collapse:collapse;font-size:13px;background:var(--card);
  border:1px solid var(--border);border-radius:12px;overflow:hidden;margin:12px 0;display:block;overflow-x:auto}}
th{{font-size:10.5px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);
  text-align:left;padding:9px 11px;border-bottom:1px solid var(--grid);background:var(--surface);white-space:nowrap}}
td{{padding:9px 11px;border-bottom:1px solid var(--grid);vertical-align:top;color:var(--ink2)}}
tr:last-child td{{border-bottom:none}}
code{{font-family:ui-monospace,Menlo,monospace;font-size:.9em;background:var(--surface);
  border-radius:4px;padding:1px 5px}}
blockquote{{border-left:3px solid var(--accent);margin:12px 0;padding:8px 14px;
  background:var(--card);border-radius:0 10px 10px 0}}
hr{{border:none;border-top:1px solid var(--grid);margin:24px 0}}
</style></head>
<body><main>
{body}
</main></body></html>
"""


def build() -> dict:
    try:
        import markdown  # dev-only dependency
    except ImportError:
        sys.exit("missing dev dependency: install with `uv pip install markdown`")

    OUT.mkdir(exist_ok=True)
    manifest = {"groups": GROUPS, "docs": []}
    for doc in SOURCES:
        src = DOCS / doc["src"]
        if not src.exists():
            sys.exit(f"source missing: {src}")
        out_path = OUT / f"{doc['key']}.html"
        if doc["kind"] == "html":
            shutil.copyfile(src, out_path)
        else:
            body = markdown.markdown(
                src.read_text(encoding="utf-8"),
                extensions=["tables", "fenced_code"])
            out_path.write_text(
                _MD_SHELL.format(lang=doc["lang"], title=doc["title"], body=body),
                encoding="utf-8")
        entry = {k: doc[k] for k in ("key", "lang", "group", "title")}
        if doc.get("owner_only"):
            entry["owner_only"] = True
        manifest["docs"].append(entry)
        print(f"built {out_path.name} ({out_path.stat().st_size} bytes)")

    (OUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"manifest: {len(manifest['docs'])} docs")
    return manifest


if __name__ == "__main__":
    build()
