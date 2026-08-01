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
    # The member-facing distillation of the E1/E2 analysis and the order
    # decision pipeline: how a decision becomes an order, and which parts
    # the AI owns. Published in all five UI languages — the first group
    # that is, which is why DocsPage no longer forces ko-or-en.
    {"key": "decisions-ko", "src": "design/decisions-guide-ko.html", "kind": "html",
     "lang": "ko", "group": "decisions", "title": "자동매매는 어떻게 판단하는가"},
    {"key": "decisions-en", "src": "design/decisions-guide-en.html", "kind": "html",
     "lang": "en", "group": "decisions", "title": "How your fleet decides to trade"},
    {"key": "decisions-ja", "src": "design/decisions-guide-ja.html", "kind": "html",
     "lang": "ja", "group": "decisions", "title": "自動売買はどう判断するのか"},
    {"key": "decisions-th", "src": "design/decisions-guide-th.html", "kind": "html",
     "lang": "th", "group": "decisions", "title": "ระบบเทรดอัตโนมัติตัดสินใจอย่างไร"},
    {"key": "decisions-vi", "src": "design/decisions-guide-vi.html", "kind": "html",
     "lang": "vi", "group": "decisions", "title": "Hệ thống giao dịch tự động quyết định thế nào"},
    # The Plan-17-era pipeline explainer (2026-07-31): the nine-station loop,
    # who authors what, the Order Intent rendered as an end-user card, a cycle
    # as a real prompt/answer conversation, and the 10-agent production
    # verification. Member-facing sibling of docs/plan/18 — same content, the
    # raw JSON block replaced by the intent-card visualization and the
    # engineering cross-links removed (they cannot resolve inside the guide).
    {"key": "how-it-works-en", "src": "design/how-ai-trading-works-en.html", "kind": "html",
     "lang": "en", "group": "how-it-works", "title": "How AI Automated Trading Works"},
    # Engineering analysis behind the smart-routing + hot-issue features. Kept
    # owner_only alongside architecture: it carries file-level implementation
    # plans, LLM cost modelling and merge sequencing. The member-facing version
    # of this material is the `smart` group.
    # Market hours in the member's own clock. Generated by
    # docs/design/_gen_market_hours_guide.py — every number comes from
    # markets.is_session_open(), so regenerate after any session-calendar
    # change rather than editing the HTML.
    {"key": "market-hours-en", "src": "design/market-hours-en.html", "kind": "html",
     "lang": "en", "group": "market-hours", "title": "When your markets are open"},
    {"key": "market-hours-ko", "src": "design/market-hours-ko.html", "kind": "html",
     "lang": "ko", "group": "market-hours", "title": "내 시장은 언제 열리나요"},
    {"key": "market-hours-ja", "src": "design/market-hours-ja.html", "kind": "html",
     "lang": "ja", "group": "market-hours", "title": "あなたの市場が開く時間"},
    {"key": "market-hours-th", "src": "design/market-hours-th.html", "kind": "html",
     "lang": "th", "group": "market-hours", "title": "ตลาดของคุณเปิดเมื่อไหร่"},
    {"key": "market-hours-vi", "src": "design/market-hours-vi.html", "kind": "html",
     "lang": "vi", "group": "market-hours", "title": "Thị trường của bạn mở khi nào"},
    {"key": "market-hours-id", "src": "design/market-hours-id.html", "kind": "html",
     "lang": "id", "group": "market-hours", "title": "Kapan pasar Anda buka"},
    {"key": "extension-e1-e2-en", "src": "reports/2026-07-25-extension-e1-e2-analysis.html",
     "kind": "html", "lang": "en", "group": "extensions",
     "title": "E1 Decision Routing & E2 Hot-Issue Daemon — Design Analysis", "owner_only": True},
    # Plan 16 as built and armed on prod (PRs #127/#130/#132). Owner-gated for
    # the same reason as `extensions`: file-level implementation detail, env
    # flags and the live book's positions are operator material.
    {"key": "liq-defense-en", "src": "plan/16-liquidation-defense-daemon.html",
     "kind": "html", "lang": "en", "group": "liq-defense",
     "title": "Plan 16 — Liquidation Defense Daemon", "owner_only": True},
    # Plan 20 as shipped (PR #179): the skills registry, its zero-LLM
    # selection, the four prompt injection sites and the admin CRUD. Owner-
    # gated for the same reason as `liq-defense`: prompt-engineering detail,
    # env behaviour and the admin API are operator material.
    {"key": "trading-skills-en", "src": "plan/20-trading-skills.html",
     "kind": "html", "lang": "en", "group": "trading-skills",
     "title": "Plan 20 — Trading Skills: How It Works", "owner_only": True},
]

# ── machine-translated bodies (2026-07-29) ─────────────────────────────────
# Until now exactly one group (`market-hours`) existed in all six languages;
# everything else was en/ko and `gateway` was Korean ONLY, so an English reader
# of the gateway guide was served Korean by DocsPage's last-resort fallback.
#
# These entries are generated by docs/design/_gen_doc_translations.py, which
# translates TEXT NODES ONLY so the markup cannot be corrupted. They are
# machine-authored pending native review — the same standing caveat as the
# alert and error catalogues. Titles live here because they are nav copy, not
# document content: the generator never sees them.
#
# Listed as a table rather than 34 more literal dicts: the source path and kind
# are a property of the GROUP, and repeating them per language is how the group
# title and the file it points at drift apart.
_OWNER_GROUPS = {"ops-keys", "architecture", "extensions", "liq-defense",
                 "trading-skills"}
_TRANSLATED_SOURCES = {
    # group: (path template, kind)
    "ops-keys": ("design/api-keys-reference-{lang}.html", "html"),
    "architecture": ("12-system-architecture-report-{lang}.html", "html"),
    "extensions": ("reports/2026-07-25-extension-e1-e2-analysis-{lang}.html", "html"),
    "liq-defense": ("plan/16-liquidation-defense-daemon-{lang}.html", "html"),
    "trading-skills": ("plan/20-trading-skills-{lang}.html", "html"),
    "guide": ("design/ai-trading-guide-{lang}.html", "html"),
    "gateway": ("design/live-trading-gateway-guide-{lang}.html", "html"),
    "smart": ("design/smart-trading-features-{lang}.html", "html"),
    "top10": ("research/parameters/2-ai-trading-parameters-{lang}.html", "html"),
    "hybrid": ("research/parameters/2-hybrid-strategy-{lang}.html", "html"),
    "decisions": ("design/decisions-guide-{lang}.html", "html"),
    "how-it-works": ("design/how-ai-trading-works-{lang}.html", "html"),
    "psych-report": ("research/parameters/2-chart-vs-human-psychology-report-{lang}.md", "md"),
    "framework": ("research/parameters/2-hybrid-strategy-framework-{lang}.md", "md"),
    "backtest-report": ("research/parameters/3-phase4-backtest-report-{lang}.md", "md"),
}
_TRANSLATED_TITLES = {
    # owner_only groups (2026-07-29): the console operator picked a language
    # too. Still owner-gated — localization does not widen the audience.
    "ops-keys": {
        "ko": "API 키 레퍼런스",
        "ja": "APIキー・リファレンス",
        "th": "คู่มืออ้างอิงคีย์ API",
        "vi": "Tài liệu tham chiếu khóa API",
        "id": "Referensi Kunci API"},
    "architecture": {
        "ko": "시스템 아키텍처 & 기술 흐름",
        "ja": "システムアーキテクチャと技術フロー",
        "th": "สถาปัตยกรรมระบบ & โฟลว์ทางเทคนิค",
        "vi": "Kiến trúc hệ thống & luồng kỹ thuật",
        "id": "Arsitektur Sistem & Alur Teknis"},
    "extensions": {
        "ko": "E1 판단 라우팅 & E2 핫이슈 데몬 — 설계 분석",
        "ja": "E1判断ルーティング & E2ホットイシューデーモン — 設計分析",
        "th": "E1 การกำหนดเส้นทางการตัดสินใจ & เดมอนประเด็นร้อน E2 — การวิเคราะห์การออกแบบ",
        "vi": "Định tuyến quyết định E1 & daemon sự kiện nóng E2 — phân tích thiết kế",
        "id": "Perutean Keputusan E1 & Daemon Isu Penting E2 — Analisis Desain"},
    "liq-defense": {
        "ko": "플랜 16 — 청산 방어 데몬",
        "ja": "プラン16 — 清算防衛デーモン",
        "th": "แผน 16 — เดมอนป้องกันการถูกบังคับปิดสถานะ",
        "vi": "Kế hoạch 16 — Daemon phòng vệ thanh lý",
        "id": "Rencana 16 — Daemon Pertahanan Likuidasi"},
    "trading-skills": {
        "ko": "플랜 20 — 트레이딩 스킬: 작동 원리",
        "ja": "プラン20 — トレーディングスキル：その仕組み",
        "th": "แผน 20 — ทักษะการเทรด: หลักการทำงาน",
        "vi": "Kế hoạch 20 — Kỹ năng giao dịch: Cách hoạt động",
        "id": "Rencana 20 — Keterampilan Trading: Cara Kerjanya"},
    "guide": {
        "ja": "AI自動売買パイプライン完全ガイド",
        "th": "คู่มือฉบับสมบูรณ์: ไปป์ไลน์เทรด AI",
        "vi": "Hướng dẫn đầy đủ quy trình giao dịch AI",
        "id": "Panduan Lengkap Pipeline Trading AI"},
    "gateway": {
        "en": "Live Trading Gateway — Complete Guide",
        "ja": "実取引ゲートウェイ完全ガイド",
        "th": "คู่มือฉบับสมบูรณ์: เกตเวย์เทรดจริง",
        "vi": "Hướng dẫn đầy đủ cổng giao dịch thật",
        "id": "Panduan Lengkap Gerbang Trading Live"},
    "smart": {
        "ja": "スマートAIの判断とパーソナル通知",
        "th": "การตัดสินใจของ AI อัจฉริยะ & การแจ้งเตือนส่วนบุคคล",
        "vi": "Quyết định AI thông minh & Cảnh báo cá nhân",
        "id": "Keputusan AI Cerdas & Notifikasi Pribadi"},
    "top10": {
        "ja": "意思決定パラメータ 上位10",
        "th": "พารามิเตอร์การตัดสินใจ 10 อันดับแรก",
        "vi": "Top 10 tham số quyết định",
        "id": "10 Parameter Keputusan Teratas"},
    "hybrid": {
        "ja": "ハイブリッド戦略：チャート × 心理",
        "th": "กลยุทธ์ไฮบริด: กราฟ × จิตวิทยา",
        "vi": "Chiến lược lai: Biểu đồ × Tâm lý",
        "id": "Strategi Hibrida: Grafik × Psikologi"},
    "decisions": {
        "id": "Bagaimana armada Anda memutuskan untuk trading"},
    "how-it-works": {
        "ko": "AI 자동매매는 어떻게 작동하는가",
        "ja": "AI自動売買はどのように動くのか",
        "th": "การเทรดอัตโนมัติด้วย AI ทำงานอย่างไร",
        "vi": "Giao dịch tự động bằng AI hoạt động thế nào",
        "id": "Bagaimana Trading Otomatis AI Bekerja"},
    "psych-report": {
        "ja": "チャート分析 vs 人間心理 — 検証済みの数値",
        "th": "การวิเคราะห์กราฟ vs จิตวิทยามนุษย์ — ตัวเลขที่ตรวจสอบแล้ว",
        "vi": "Phân tích biểu đồ vs Tâm lý con người — Số liệu đã kiểm chứng",
        "id": "Analisis Grafik vs Psikologi Manusia — Angka Terverifikasi"},
    "framework": {
        "ja": "ハイブリッド・フレームワーク — 意思決定スタックとチェックリスト",
        "th": "เฟรมเวิร์กไฮบริด — สแต็กการตัดสินใจ & เช็กลิสต์",
        "vi": "Khung lai — Ngăn xếp quyết định & Danh mục kiểm tra",
        "id": "Kerangka Hibrida — Tumpukan Keputusan & Daftar Periksa"},
    "backtest-report": {
        "ja": "フェーズ4 戦略バックテスト — Go/No-Go 結果",
        "th": "แบ็กเทสต์กลยุทธ์เฟส 4 — ผล Go/No-Go",
        "vi": "Backtest chiến lược Phase-4 — Kết quả Go/No-Go",
        "id": "Backtest Strategi Fase-4 — Hasil Go/No-Go"},
}

for _group, _titles in _TRANSLATED_TITLES.items():
    _pattern, _kind = _TRANSLATED_SOURCES[_group]
    for _lang, _title in _titles.items():
        _entry = {"key": f"{_group}-{_lang}", "src": _pattern.format(lang=_lang),
                  "kind": _kind, "lang": _lang, "group": _group, "title": _title}
        if _group in _OWNER_GROUPS:
            _entry["owner_only"] = True
        SOURCES.append(_entry)


# Nav labels for the docs rail, in every language LANG_NAMES registers.
# ko/en only until 2026-07-29: DocsPage rendered `language === 'ko' ? ko : en`,
# so a ja/th/vi/id member navigated the documentation in English no matter what
# they had selected — including to the groups that DO publish in their
# language. Titles are short and closed, so they belong here rather than in a
# per-document field. ja/th/vi/id are machine-authored pending native review,
# the same standing caveat as the alert and error catalogues.
GROUPS = [
    {"group": "guide", "ko": "완전 가이드", "en": "Full Guide", "ja": "完全ガイド",
     "th": "คู่มือฉบับสมบูรณ์", "vi": "Hướng dẫn đầy đủ", "id": "Panduan Lengkap"},
    {"group": "gateway", "ko": "실거래 게이트웨이", "en": "Live Trading Gateway",
     "ja": "実取引ゲートウェイ", "th": "เกตเวย์เทรดจริง",
     "vi": "Cổng giao dịch thật", "id": "Gerbang Trading Live"},
    {"group": "smart", "ko": "스마트 AI & 알림", "en": "Smart AI & Alerts",
     "ja": "スマートAI & 通知", "th": "AI อัจฉริยะ & การแจ้งเตือน",
     "vi": "AI thông minh & Cảnh báo", "id": "AI Cerdas & Notifikasi"},
    {"group": "top10", "ko": "TOP 10 파라미터", "en": "Top-10 Parameters",
     "ja": "上位10パラメータ", "th": "พารามิเตอร์ 10 อันดับแรก",
     "vi": "Top 10 tham số", "id": "10 Parameter Teratas"},
    {"group": "hybrid", "ko": "하이브리드 전략", "en": "Hybrid Strategy",
     "ja": "ハイブリッド戦略", "th": "กลยุทธ์ไฮบริด",
     "vi": "Chiến lược lai", "id": "Strategi Hibrida"},
    {"group": "framework", "ko": "프레임워크 체크리스트", "en": "Framework Checklists",
     "ja": "フレームワーク・チェックリスト", "th": "เช็กลิสต์เฟรมเวิร์ก",
     "vi": "Danh mục kiểm tra khung", "id": "Daftar Periksa Kerangka"},
    {"group": "psych-report", "ko": "차트 vs 심리 리포트", "en": "Charts vs Psychology",
     "ja": "チャート vs 心理", "th": "กราฟ vs จิตวิทยา",
     "vi": "Biểu đồ vs Tâm lý", "id": "Grafik vs Psikologi"},
    {"group": "backtest-report", "ko": "백테스트 결과", "en": "Backtest Result",
     "ja": "バックテスト結果", "th": "ผลแบ็กเทสต์",
     "vi": "Kết quả backtest", "id": "Hasil Backtest"},
    {"group": "ops-keys", "ko": "API 키 (관리자)", "en": "API Keys (owner)",
     "ja": "APIキー（管理者）", "th": "คีย์ API (ผู้ดูแล)",
     "vi": "Khóa API (quản trị)", "id": "Kunci API (admin)"},
    {"group": "architecture", "ko": "시스템 아키텍처 (관리자)",
     "en": "System Architecture (owner)", "ja": "システムアーキテクチャ（管理者）",
     "th": "สถาปัตยกรรมระบบ (ผู้ดูแล)", "vi": "Kiến trúc hệ thống (quản trị)",
     "id": "Arsitektur Sistem (admin)"},
    {"group": "decisions", "ko": "AI 판단과 주문", "en": "How Decisions Become Orders",
     "ja": "AIの判断と注文", "th": "การตัดสินใจกลายเป็นคำสั่งอย่างไร",
     "vi": "Từ quyết định đến lệnh", "id": "Dari Keputusan ke Order"},
    {"group": "how-it-works", "ko": "AI 자동매매 작동 원리", "en": "How AI Trading Works",
     "ja": "AI自動売買のしくみ", "th": "หลักการทำงานของ AI เทรด",
     "vi": "Cách AI giao dịch vận hành", "id": "Cara Kerja Trading AI"},
    {"group": "market-hours", "ko": "내 시장 개장 시간", "en": "When Your Markets Are Open",
     "ja": "市場の開場時間", "th": "เวลาเปิดตลาดของคุณ",
     "vi": "Giờ mở cửa thị trường", "id": "Jam Buka Pasar Anda"},
    {"group": "extensions", "ko": "확장 설계 분석 (관리자)",
     "en": "Extension Design Analysis (owner)", "ja": "拡張設計分析（管理者）",
     "th": "การวิเคราะห์การออกแบบส่วนขยาย (ผู้ดูแล)",
     "vi": "Phân tích thiết kế mở rộng (quản trị)",
     "id": "Analisis Desain Ekstensi (admin)"},
    {"group": "liq-defense", "ko": "청산 방어 데몬 (관리자)",
     "en": "Liquidation Defense (owner)", "ja": "清算防衛デーモン（管理者）",
     "th": "เดมอนป้องกันการบังคับปิดสถานะ (ผู้ดูแล)",
     "vi": "Daemon phòng vệ thanh lý (quản trị)",
     "id": "Daemon Pertahanan Likuidasi (admin)"},
    {"group": "trading-skills", "ko": "트레이딩 스킬 (관리자)",
     "en": "Trading Skills (owner)", "ja": "トレーディングスキル（管理者）",
     "th": "ทักษะการเทรด (ผู้ดูแล)",
     "vi": "Kỹ năng giao dịch (quản trị)",
     "id": "Keterampilan Trading (admin)"},
]

# ── Plan 19: per-broker gateway connection guides ───────────────────────────
# Generated by docs/design/_gen_gateway_setup_guides.py (regenerate there, do
# not hand-edit the HTML). One group per broker so DocsPage's one-doc-per-
# group-per-language model holds. These groups are deliberately NOT mapped in
# DocsPage's rail (SLUG_TO_GROUP): their entry point is the Accounts page,
# which opens the doc for the selected broker inline.
_GWSETUP_TITLES = {
    "binance":  {"en": "Connect Binance", "ko": "바이낸스 연결 가이드", "ja": "Binance接続ガイド",
                 "th": "คู่มือเชื่อมต่อ Binance", "vi": "Hướng dẫn kết nối Binance", "id": "Panduan Menghubungkan Binance"},
    "alpaca":   {"en": "Connect Alpaca", "ko": "알파카 연결 가이드", "ja": "Alpaca接続ガイド",
                 "th": "คู่มือเชื่อมต่อ Alpaca", "vi": "Hướng dẫn kết nối Alpaca", "id": "Panduan Menghubungkan Alpaca"},
    "ibkr":     {"en": "Connect Interactive Brokers", "ko": "IBKR 연결 가이드", "ja": "IBKR接続ガイド",
                 "th": "คู่มือเชื่อมต่อ IBKR", "vi": "Hướng dẫn kết nối IBKR", "id": "Panduan Menghubungkan IBKR"},
    "bybit":    {"en": "Connect Bybit", "ko": "바이비트 연결 가이드", "ja": "Bybit接続ガイド",
                 "th": "คู่มือเชื่อมต่อ Bybit", "vi": "Hướng dẫn kết nối Bybit", "id": "Panduan Menghubungkan Bybit"},
    "okx":      {"en": "Connect OKX", "ko": "OKX 연결 가이드", "ja": "OKX接続ガイド",
                 "th": "คู่มือเชื่อมต่อ OKX", "vi": "Hướng dẫn kết nối OKX", "id": "Panduan Menghubungkan OKX"},
    "kraken":   {"en": "Connect Kraken", "ko": "크라켄 연결 가이드", "ja": "Kraken接続ガイド",
                 "th": "คู่มือเชื่อมต่อ Kraken", "vi": "Hướng dẫn kết nối Kraken", "id": "Panduan Menghubungkan Kraken"},
    "cryptocom": {"en": "Connect Crypto.com Exchange", "ko": "Crypto.com 거래소 연결 가이드", "ja": "Crypto.com Exchange接続ガイド",
                  "th": "คู่มือเชื่อมต่อ Crypto.com Exchange", "vi": "Hướng dẫn kết nối Crypto.com Exchange", "id": "Panduan Menghubungkan Crypto.com Exchange"},
    "upbit":    {"en": "Connect Upbit", "ko": "업비트 연결 가이드", "ja": "Upbit接続ガイド",
                 "th": "คู่มือเชื่อมต่อ Upbit", "vi": "Hướng dẫn kết nối Upbit", "id": "Panduan Menghubungkan Upbit"},
    "kucoin":   {"en": "Connect KuCoin", "ko": "쿠코인 연결 가이드", "ja": "KuCoin接続ガイド",
                 "th": "คู่มือเชื่อมต่อ KuCoin", "vi": "Hướng dẫn kết nối KuCoin", "id": "Panduan Menghubungkan KuCoin"},
}
for _broker, _titles in _GWSETUP_TITLES.items():
    GROUPS.append({"group": f"gwsetup-{_broker}", **_titles})
    for _lang, _title in _titles.items():
        SOURCES.append({
            "key": f"gwsetup-{_broker}-{_lang}",
            "src": f"design/gateway-setup-{_broker}-{_lang}.html",
            "kind": "html", "lang": _lang,
            "group": f"gwsetup-{_broker}", "title": _title,
        })

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
