# TODOS

Follow-ups from the signal-collection ship review (2026-07-14, 6 specialists + red team).
Everything blocking was fixed pre-merge; these are the accepted non-blocking items.

## Risk Engine

### Re-validate gate checks inside the fill transaction (TOCTOU)
**Priority:** P2
`evaluate_order` reads breaker/daily-loss/exposure on its own connection before
`execute_paper_trade` fills on another; a watcher close or concurrent rule run can
interleave. Re-check (or perform) the validations inside the fill's write transaction.

### Lock in Kelly all-wins pass-through behavior with a test
**Priority:** P3
An agent with ≥10 closed trades and zero losses gets `payoff_ratio=None` → no Kelly cap.
Intended (no loss data = no estimate), but undocumented — add a gate-level test.

### Incremental trade-stats aggregates
**Priority:** P3
The journal replay is bounded (last 5000 signals) but still O(N) per order. If automation
volume grows, maintain per-agent win/loss/realized-by-day aggregates updated at fill time.

## Signal Feeds (psych / scanner / fusion)

### Extract shared snapshot-store helper
**Priority:** P3
psych_feed and scanner duplicate insert+prune+cache scaffolding (identical TTLs, prune SQL,
fail-soft cache blocks). Phase 6 (whale flows) adds a third feed — factor the helper first.

### Unify σ/volume computation between psych_feed and quant_crypto
**Priority:** P3
`compute_shock_proxy` (window excludes latest hour) and `compute_sigma_and_volume`
(includes it) are near-duplicates with silently divergent windows. Extract one helper with
an explicit include-latest parameter.

### Share framework trigger thresholds across modules
**Priority:** P3
`BASIS_BUY_GAP_PCT = 1.2` is defined in quant_crypto and signal_fusion; RSI 70/30 are bare
literals in quant_crypto but named in signal_fusion. Define once, import everywhere.

### Direct unit tests for psych/quant/sentiment component builders
**Priority:** P3
`_psych_component`/`_quant_component`/`_sentiment_component` value mappings are always
mocked in fusion tests; `fetch_candles`/`fetch_funding_rate`/`fetch_spot_ticker` parsing
has no canned-response tests. Add fixture-based unit tests.

### Store the OKX instrument list once, not per snapshot
**Priority:** P4
scanner_snapshots keeps 500 copies of the ~423-instrument list; only the latest is ever
read (new-listing diff). Move to a single-row table.

## Backend (shared)

### Deduplicate small helpers into utils.py / routes_shared.py
**Priority:** P3
Five copies each of the env-bool parser and Z-suffixed ISO timestamp helper; `_auth` is
copied between routes_automation and routes_risk; symbol⇄instId conversions scattered.
Centralize (utils.py, routes_shared.py, crypto_feed.py respectively).

### Fix pre-existing MySQL-incompatible prune SQL in market_intel
**Priority:** P2
`_prune_market_news_history` / `_prune_macro_signal_history` / `_prune_etf_flow_history` /
`_prune_stock_analysis_history` use the `DELETE … WHERE id NOT IN (SELECT … LIMIT)` pattern
that MySQL rejects (errors 1235/1093) — same bug fixed in psych_feed/scanner this ship, but
these predate it. On MySQL prod, snapshot retention never prunes (inserts succeed; deletes fail).

### Dispatch `_fallback_brief` on a structural marker
**Priority:** P4
The technical-analyst branch matches the prose note "light technical…" — brittle. Add a
`kind` key to gathered data dicts.

### Tests for seed_dev_market_intel and its production guard
**Priority:** P3
The dev seeder (~90 lines) and its `ENVIRONMENT=production` guard have zero coverage.

## Frontend

### Signals-board component tests
**Priority:** P4
No frontend test infrastructure exists. If adopted (Vitest + RTL), cover the page's
loading/collecting/error states first.

### Upgrade vite 5 → 8 (esbuild dev-server advisory)
**Priority:** P3
`npm audit` flags esbuild <=0.24 (GHSA-67mh-4wv8-2f99, dev-server only) via vite 5.
Non-breaking fix doesn't exist — requires the vite 8 major. CI now audits with
`--omit=dev`; do the major bump deliberately with a frontend smoke pass.

## Completed
