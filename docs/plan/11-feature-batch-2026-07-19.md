# Plan 11 — Feature batch 2026-07-19

Henry's request (2026-07-19), 5 parts + F6 added mid-session. Implementation order
chosen for risk: small → large. Each feature landed as its own commit on `main`.

**STATUS: all shipped and deployed 2026-07-19** — prod image `20260719-plan11`,
main@0403b6d, alembic 0025. Verified live on sooppiy.com (see §Ship).
F6 (desktop top bar) was requested after this plan was written; it is documented
in the commit `7ffdc4c` rather than below.

## F3b — Mobile landing header fix (small)

`service/frontend/src/pages/MarketingPage.tsx:656-669` header is a single non-wrapping
flex row with zero media queries → on phones the logo + 5 language pills + 로그인 +
가입하기 overflow (see user screenshot). Fix: inject a `<style>` block with classes +
`@media (max-width: 640px)`; on mobile show **only 가입하기** (per request "keep only
one"), hide 로그인, compact the language pills.

## F1 — Top-5 symbol universe for 완전위임/간편 (medium)

Facts: runs = single user symbol (no AI). Automation agent mode picks via
`agent_planner._allowed_symbols` (`agent_planner.py:44-50`): scanner top-8 + majors,
cap 12. Simple mode pills are static `SIMPLE_COINS=['BTC','ETH','SOL','SCANNER']`
(`AutomationPage.tsx:57`).

Build:
- `top_symbols.py` (new, small): rank by 24h volume from OKX SWAP tickers
  (`crypto_feed.fetch_tickers`, `volCcy24h`) + StockTwits mention counts when scanner
  data available; intersect with priceable universe (Hyperliquid availability from
  `routes_market.py` helpers); return top 5; cached ~5 min.
- `agent_planner._allowed_symbols` → use top-5 (majors fallback on fetch failure).
- New `GET /api/markets/top-symbols` → `[{symbol, vol_24h}]`.
- Simple mode pills become dynamic top-5 (+ fallback to old list when endpoint empty).
- `'SCANNER'` sentinel resolution unchanged (scanner already ranks by volume).

## F2 — Per-user AI model config + usage cost (medium-large)

Facts: per-user provider/model/key already exists (`user_api_settings` target `llm`,
Settings UI card in `SettingsPage.tsx:334-459`). NO usage tracking anywhere;
`llm_client.py` discards `resp.usage`. All calls go through `generate_text`
(`llm_client.py:258`). Owner gating precedent: `routes_guide.py:33-37`
(`DOCS_OWNER_EMAILS`, default info@askkpop.com).

Build:
- Migration `0024_llm_usage` + `database.py` mirror: `llm_usage(id, user_id, agent_id,
  provider, model, tier, prompt_tokens, completion_tokens, cost_usd, source
  ['user'|'system'], created_at)`. Monthly-query index `(user_id, created_at)`.
- Capture usage in `_generate_openai_compatible` / `_generate_anthropic`; record row in
  `generate_text` (source = 'user' when LlmContext came from a user key, else
  'system'; carry user_id/agent_id on LlmContext).
- Static price table $/1M tokens per known model, else 0 → cost estimate.
- `GET /api/users/settings/llm-usage` → current-month + last-6-months aggregates for
  the user; `system` block included only when the caller's email ∈ DOCS_OWNER_EMAILS.
- SettingsPage: usage panel atop the llm API card — model in use, month tokens,
  est. cost; owner additionally sees system-wide totals.

## F3a — Zenix-style /positions rebuild (large, frontend-heavy)

Facts: `pages/PositionsPage.tsx` = one flat table over `GET /api/positions`
(`routes_trading.py:648`); response drops `side`, `stop_loss`, `take_profit` even
though DB has them. Open/filled orders: `broker_orders` via `GET /api/execution/orders`
(`routes_execution.py:232`). No trades table — filled broker_orders ≈ trade log.
Zenix template (from ~/Programming/src/ga `BottomTabs.tsx`): plain HTML tables, tabs
[포지션|미체결 주문|주문 내역|거래 내역], multi-line cells (진입가/마크가 stacked),
right-aligned mono numerics, pnl sign coloring, 지정가/시장가 close buttons.

Build:
- Backend: add `side`, `stop_loss`, `take_profit`, `value` (qty*price) to
  `/api/positions` items. Confirm close endpoint (market close = existing sell/close
  trade route) and wire cancel for pending broker orders (exists in routes_execution).
- Frontend: rebuild PositionsPage with zenix layout adapted to this app's inline-style
  system: tabs 포지션(N) / 미체결 주문(N) / 주문 내역 / 거래 내역; positions columns
  계약(symbol+롱/숏)·가격(진입가/현재가)·가치(value/qty)·손익(+%,TP/SL)·청산(시장가).
  Spot-like assets (no side) render holdings-style columns. i18n via existing lang system.

## F4 — Persistent AI analysis memory (medium)

Facts: `agent_memory` table (0008) with embedding + cosine search exists
(`routes_memory.py`) but is NOT read/written by analysis. Prompt-injection precedent:
`_guidelines_block` (`analysis_agents.py:325`), resolved via
`services.guidelines_for_agent` and threaded through `run_analysis`.

Build (mirror the guidelines pattern):
- Write: after `_run_analysis_inner` builds its result, distill 0-2 durable insights
  (brief-tier LLM, JSON out) and store into `agent_memory` with metadata
  `{kind:'analysis_insight', symbol, market}`; skip when near-duplicate (cosine > .92
  vs recent same-symbol rows). Cap rows per agent (reuse quota).
- Read: `_memory_block()` — top-K (≤5) memories for the agent scored by recency +
  symbol match (embedding search when available), injected into decision & verify
  prompts alongside guidelines. Runs (`run_engine`) and jobs inherit automatically
  since both call `run_analysis`.
- Flag `ANALYSIS_MEMORY_ENABLED` (default on).

## F5 — Social collection service (large)

Facts: only StockTwits today (`analysis_sources.py:53`). Worker pattern:
`tasks.py:1578` registry, role `research`, env-interval loops. Retention precedents:
time-window prune (`tasks.py:240`) and row-cap prune (`psych_feed.py:589`).
`.env.example:67-71` already stubs social creds. No raw-posts table.

Build:
- Migration `0025_social_feed` + mirror: `social_posts(id, platform ['x'|'facebook'],
  region, topic, post_id, author, text, engagement_json, posted_at, created_at)`
  unique(platform, post_id); `social_snapshots(id, snapshot_key, summary_json,
  created_at)`.
- `social_feed.py`: `SOCIAL_FEED_ENABLED` gate; official APIs only (X API v2 recent
  search via `X_BEARER_TOKEN`; Facebook Graph API via `FACEBOOK_ACCESS_TOKEN` +
  page/keyword config) — no scraping (ToS). Region routing: SEA topics → facebook,
  else → X. Topics = top-5 symbols (F1) + majors. Each 30-min cycle
  (`SOCIAL_REFRESH_INTERVAL=1800`): fetch → upsert posts → aggregate per-symbol
  sentiment (keyword/vader-style base score + optional brief-tier LLM summary capped
  per cycle) → write snapshot → prune posts older than 7 days
  (`SOCIAL_RAW_RETENTION_DAYS=7`).
- Analysis wiring: `_gather_sentiment` (`analysis_agents.py:132`) merges latest
  social snapshot payload.
- `social_feed_loop` registered in `BACKGROUND_TASK_REGISTRY` + ROLES(research).

## Ship

ruff F + pytest + tsc (CI mirrors) → push → gh run watch → deploy EC2 per
docs/plan/09 procedure (tarball + docker, alembic upgrade head, publish dist to
/usr/share/nginx/sooppiy) → verify prod ≥2×.
