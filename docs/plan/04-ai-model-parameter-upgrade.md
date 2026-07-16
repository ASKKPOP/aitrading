# AI trading model — parameter research deep analysis & modification plan

**Date:** 2026-07-16 · **Version: v2** (v1 draft was adversarially reviewed by a 6-agent verification panel — research fidelity, codebase feasibility, statistics/overfitting, risk management, data availability, product/scope. 9 CRITICAL + 31 MAJOR + 23 MINOR findings; all confirmed findings are folded into this version. Full log in §8.)
**Inputs:** `docs/research/parameters/*` (7 documents, EN+KO, cross-checked — one consistent framework) + full codebase map by 3 exploration agents + live keyless-API verification (curl) of every data dependency.
**Scope:** the AI decision engine driving automated paper trades (`analysis_agents` → `automation` → `risk_engine`) and its read-only twin (`signal_fusion`). NOT real-money execution — Sooppiy remains a signal/copy-trading product with simulator accounts.

---

## 0. Korean executive summary (한국어 요약)

리서치 결론: **심리는 국면(WHEN), 차트는 트리거(WHAT), 거래량+감성은 확인, 변동성은 규모 — 6개 조건 중 4개 이상 겹칠 때만 행동.** 검증된 기대 정확도는 **50–55%**이며, 컨플루언스로 55%를 *넘어서는 것*이 목표다(55–58%는 이 계획의 낙관적 상한이지 리서치 수치가 아님 — 검증 패널 지적으로 정정).

현재 시스템과의 격차: ① 문헌상 1순위 예측 변수(12-1 모멘텀, 200일 MA)가 코드에 없음 ② 국면 필터 없음(심리가 점수에 가산될 뿐) ③ 컨플루언스 게이트 없음 ④ 변동성 사이징 없음 ⑤ 신뢰도 과대 계상(최대 0.95).

v1 초안을 6개 에이전트가 반박 검증한 결과, 구조는 유효하나 중대 결함 다수 확인: 백테스트 불가능한 조건(B4 감성 이력 부재), 시간봉 σ를 일봉 σ로 오용(약 5배 과대 사이징), 재매수 시 트레일링 스톱 파괴, SQLite에서 실행되지 않는 마이그레이션, 통계적으로 무의미한 합격 기준 등. v2는 전부 수정: **얇은 v1 우선**(컨플루언스 표시/API 전용) → 실행 경로 변경은 전부 Phase 4 검증 증거 뒤로. 상세는 §4–§5.

---

## 1. What the research actually says (canonical summary)

| # | Finding | Verified number | Source |
|---|---|---|---|
| 1 | Momentum (12-mo skip-last-month) + trend (200-day MA) are the most verified predictors | GKX 2020 #1 feature family; Brock 1992 buy-days ≈ +12%/yr ann. | RFS 2020, JF 1992 |
| 2 | Technicals informative but never profitable stand-alone | 53–54% win rate best case; profits vanish after costs + snooping correction | LMW 2000, Sullivan 1999 |
| 3 | Sentiment adds real but small information, at extremes and overnight | 50–55% accuracy; ~6bp/SD next-day | Fed FEDS 2023-034, CEPR 2025 |
| 4 | Famous numbers on both sides are folklore | "80%+ patterns" unverifiable; "87.6% Twitter" failed replication | Lachanski & Pav 2017 |
| 5 | Edge = combining many weak signals + risk management | Sharpe 1.35 vs 0.61 (nonlinear vs linear) | GKX 2020 |
| 6 | Realistic expectation: **50–55% directional accuracy**; >55% is the confluence *goal*; distrust >60% without out-of-sample, cost-adjusted, replicated evidence | — | both rounds |

Prescribed architecture: **L1 psychology regime filter** (mode switch + veto, never an additive signal) → **L2 direction engine** (12-1 momentum, 200-day MA, plus 1-month short-term reversal for counter-trend timing) → **L3 trigger + confirmation** (trigger counts only with volume; sentiment can veto) → **L4 size & exit** (size = risk budget ÷ volatility; hard stop, trailing stop, time stop) → act only at **≥4/6 confluence**.

Two honesty notes the panel forced into this section:
- The framework's *linear* 4-of-6 checklist is in tension with finding #5 (GKX's edge is *nonlinear* combination). The checklist is the auditable v1; a learned nonlinear combiner is a possible v2 — this plan implements the checklist and says so.
- The research's Layer-1 quantitative thresholds (VIX 20/30) are themselves labeled unverified in the research's own honesty section. Every regime band in this plan is therefore an **unvalidated placeholder pending Phase 4**, not a verified number.

## 2. What the system is today (verified codebase map)

Two pipelines share the word "signal": user-published signals (`routes_signals.py` — out of scope) and the AI decision engine (in scope).

**Decision producers:**
- **A. `analysis_agents.run_analysis`** — the only engine that executes. 4 data bundles → 4 LLM analyst briefs → LLM trader decision `{action, confidence, entry, target, stop}` (analysis_agents.py:290–322); falls back to `_rule_based_decision` (:247–265) = action from technical score only, `confidence = clamp(0.5+|score|/20, 0.3, 0.9)`. The LLM's own stop/target are never wired into execution.
- **B. `signal_fusion.fuse_symbol`** — deterministic weighted fusion (0.5/0.3/0.2, psych hard-capped 0.3, thresholds ±0.25, confidence `min(0.95, 0.5+|score|/2)`). Display-only, never executes.
- **C. Technical scorers** — crypto `quant_crypto.build_crypto_analysis` (RSI14, MA5/20/60 on 120 daily closes, σ of hourly returns over 24h (`sigma_24h_pct` — **hourly**, not daily σ), volume_ratio, funding, basis, OI, L/S; buy ≥ +2 / sell ≤ −2); stock `market_intel._build_stock_analysis` (MA5/10/20/60, 5d/20d returns, support/resistance from the last 20 closes; per-day volume is parsed but no volume ratio is computed; buy ≥ +3 / sell ≤ −3).

**Execution path:** `automation.run_rule` (60s tick): auto_execute → simulator-only → action ∈ {buy,sell} (shorts cannot be opened via automation; `sell` against a flat book is rejected) → `min_confidence` (applies to buys AND sells, automation.py:183) → market open → event guard (default off, ±60min) → risk gate (default off: breaker → daily-loss → ½-Kelly → exposure; **anything non-buy bypasses the whole gate**, risk_engine.py:315–316) → paper trade with SL/TP `price·(1±5%/10%)`. Every automated buy **unconditionally overwrites** the position's SL/TP (automation.py:113–119). Position `opened_at` is **reset on every add-on buy** (services.py:295–298). SL/TP watcher (30s) is long-only; `execute_paper_trade` cannot execute `cover`, so it cannot close shorts. Global breaker documented (risk_engine.py:13) but never auto-tripped. `breaker_state` has no expiry/trip-source columns (database.py:1913–1920).

**Deployment reality:** alembic runs **only on MySQL** (`main.py:61–67`); the default SQLite path uses `init_database()`, and no alembic version covers the automation tables. `min_confidence` defaults to 0.65 in **three places**: frontend `AutomationPage.tsx:23` (+ recommendation copy in 5 languages), API `routes_automation.py:31`, schema `database.py:1862`.

**Data layer:** live prices Hyperliquid / AV intraday / Polymarket CLOB. `historical_data.py` (daily OHLCV, yfinance default + AV fallback, Parquet cache) has zero production callers **and a dormant staleness bug** — `_cache_covers` is dead code, so a cached file is returned even when it doesn't cover the requested range. Its AV fallback uses **unadjusted** closes (splits/dividends corrupt long-window momentum); yfinance path uses `auto_adjust=True` (correct). AV free tier is 25 req/day and `TIME_SERIES_DAILY_ADJUSTED` is a premium endpoint — the existing stock pipeline already exceeds a free key. `backtest.py` replays an agent's own recorded signals; Sharpe inflates with trade count (backtest.py:318). Psych feed retains ~20 days of hourly snapshots; OKX liquidation endpoint holds ~24h; OKX L/S ratio history ~180 days; OKX daily candles start 2019-11 (BTC/ETH perps); Yahoo has full 2019+ daily for BTC/ETH; **SOL data starts 2020-04 (Yahoo) / 2020-09 (OKX spot)**. alternative.me F&G full history available via `limit=0` (3,084 rows since 2018-02, verified live).

## 3. Gap analysis — research prescription vs code

| Layer | Research prescribes | Code today | Gap |
|---|---|---|---|
| L2 direction | 12-1 momentum + 200-day MA + 1-month reversal | Max window: MA60 / 20d return; 120 daily closes | Missing the most-verified predictors; history depth is the binding constraint |
| L1 regime | Psychology switches mode & vetoes | Psych is an additive component (≤0.3) + LLM prose; event guard off | No regime concept |
| L3 confirmation | Volume mandatory; sentiment veto | volume_ratio is one soft input (crypto only) | No hard confirmation gates |
| Confluence | Act only at ≥4/6 | Continuous thresholds; LLM free-form | No confluence counting |
| L4 sizing | Size = risk budget ÷ volatility | Fixed `size_usd`; Kelly cap only | No volatility sizing |
| L4 exits | Hard + trailing + time stops | Fixed-pct SL/TP, long-only | Exit toolkit incomplete |
| Honesty | Expect 50–55%; distrust >60% | Confidence up to 0.90/0.95; presets tuned to that scale | Systematically over-confident |
| Validation | Backtest + OOS re-validation first | Replay-only backtester; `historical_data` orphaned | Cannot validate the strategy today |

**Kept because already right:** psych weight cap + psych-never-trades-alone invariant; event-guard concept; fee-aware replay; ½-Kelly as cap; watcher exits bypassing the gate; `estimated:true` honesty flags.

**Plan decision (not research-confirmed — the framework's own B3/S3 prescribe pattern triggers):** we do **not** build classic chart-pattern detection. Rationale: patterns are the family with the weakest stand-alone verification, pattern-completion detection is high-effort/low-testability, and the indicator-score + mandatory-volume gate carries the same class of information (LMW: patterns are "informative", i.e. features). This is a deliberate divergence from research-B3/S3; plan-B3/S3 substitute the indicator trigger.

## 4. Modification plan (v2)

Design rules: deterministic checks live outside the LLM; every execution-path change is env-gated default-off **and stays off until Phase 4 evidence exists**; anything that cannot be env-gated (migrations, UI defaults) ships only in the Phase-4 flip package; every constant lands in `strategy_config.py`; nulls are conservative for *entries* and permissive for *exits*; all thresholds introduced here are placeholders validated (or rejected) in Phase 4.

### Phase 0 — data foundations (~3–4 days)

0.1 **Repair and wire `historical_data.py`:** implement the missing `_cache_covers` staleness check (currently dead code — cached Parquet is returned even when it doesn't cover the request); merge-and-extend refresh. Corpus source decisions (verified live): **yfinance for the backtest corpus** (BTC-USD/ETH-USD full 2019+; already in requirements.txt; always explicit start/end — Yahoo's `range=max` silently downsamples to weekly) and for stock daily history (auto-adjusted closes; the AV fallback is unadjusted and its adjusted endpoint is premium — do not use AV for long-window stock features). **OKX stays the live-feature source**; add pagination to `crypto_feed.fetch_candles` (2 chained calls → 600 daily bars) for live ≥380-close windows. Add a one-off spot-vs-perp daily-close sanity diff to bound the corpus/live basis mismatch.
0.2 **Long-window features** in `quant_crypto` + `market_intel._build_stock_analysis`: `momentum_12_1_pct` (close[-21]/close[-252]−1; crypto calendar-days variant skip 30 / lookback 365), `ma200` + `price_above_ma200`, `golden_cross_state` (MA50>MA200), `reversal_1m_pct` (1-month return, computed now, consumed later — research L2's third component; usage deferred, documented), and **`sigma_daily`** = 20-day daily-return σ for BOTH markets (the existing `sigma_24h_pct` is an HOURLY σ — ~√24 smaller than daily; it must never be used where daily σ is meant). Stock volume ratio (data already parsed, only the ratio is missing).
0.3 **Backtest metrics repair:** Sharpe from a **daily mark-to-market equity curve** (flat days included) × √365 crypto / √252 stocks — not trade-count, not "elapsed time" over per-trade returns. Export the 6 orphaned metrics. Journal a note that promotion metrics change (intentional correction).
0.4 **Historical reconstruction for Phase 4:** backfill `market_events._CALENDAR` with 2019–2025 FOMC/CPI/NFP dates (public record, static — makes B6 fully backtestable); one-shot F&G full-history fetch (`limit=0`, verified 2018-02→present); **start snapshotting now** daily funding/OI/L-S/StockTwits readings into a small table so future re-validation of live-only conditions becomes possible. Elections: add the 2026 US midterm date to the static calendar; other elections documented as out of scope (crypto-centric platform).
0.5 **Stale-doc corrections (project convention):** dated notes in `docs/README.md` + `01-technical-roadmap.md` — CI, pydantic-settings, alembic, broker ABC already landed; this plan's Phase 4 extends `backtest.py` as a second mode rather than the roadmap's package layout (divergence noted there).

**Verify:** fixture unit tests (known momentum/MA200/σ values, hourly-vs-daily σ divergence case); cache-staleness regression test; corpus row counts per asset vs verified listing dates.

### Phase 1 — confluence engine, **display & API only** (~2–3 days)

New module `service/server/confluence.py` — deterministic, no LLM, **no execution-path changes in this phase** (the panel's product lens: the recalibration/migration cluster cannot be env-gated and therefore moves wholesale to the Phase-4 flip).

Buy checklist (plan-B1..B6; intervals half-open, one table, golden-tested):
| # | Condition | Notes |
|---|---|---|
| B1 | price > MA200 | Phase 0.2 |
| B2 | momentum_12_1 > 0 | Phase 0.2 |
| B3 | technical score ≥ buy cutoff **AND volume_ratio ≥ VOLUME_CONFIRM_MIN (1.5, tunable, Phase-4 validated)** | no volume → B3 false, always |
| B4 | sentiment positive **or recovering** (StockTwits tilt ≥ 0, or negative-but-rising vs prior snapshot) AND no negative news z-spike in the symbol's category | live-forward only (no history exists); overnight-window restriction = future work |
| B5 | fear recovering: F&G < 30 AND delta_3d > 0; or shock flagged within 72h now cleared (**requires new `psych_feed.shock_history(hours)` accessor** — snapshots retain ~20d, enough) | F&G leg backtestable; shock leg proxy-only historically |
| B6 | no FOMC/CPI/NFP within EVENT_CONFLUENCE_HOURS (24) | backtestable after 0.4 backfill |

Sell checklist S1–S6 mirrors (S4 euphoria = F&G ≥ 80 **or** [F&G ≥ 75 AND L/S ≥ 2.0] — L/S history is only ~180d, so S4's primary leg is F&G; S5 = shock/policy state **while flagged unresolved** — no 72h expiry; the 72h window belongs to B5's "cleared" branch only; S6 = SL/TP/vol-target hit, always absolute).

- Null semantics: nulls never satisfy a condition; threshold stays /6. **Observability requirement:** the confluence block carries per-condition `null` reasons, and (once execution consumes it in Phase 4) `skip_reason` must name starving conditions — "confluence 2/6 — B4, B5 unavailable: psych feed stale" — so a dead feed is distinguishable from market conditions.
- Veto flags: negative news z-spike ≤ −2 in symbol's category within 24h vetoes buys; active event window vetoes both sides.
- **Prerequisite:** `PSYCH_FEED_ENABLED=on` becomes a documented runtime requirement (B4/B5 read its snapshots).
- Output: `{buy_confluence, sell_confluence, conditions, nulls, vetoes, direction_bias}`. **No probability-formatted "confidence" field.** The count IS the score. An `estimated_accuracy` may be attached ONLY from empirical calibration buckets (realized hit rate per count, Wilson 90% CI, suppressed below n=50 per bucket) — never from an invented linear map.

Product surface (this phase's actual deliverable):
1. `confluence` block in the fusion payload + documented **agent-facing API contract** (fields, nullability, stability promise) — this is the publish-side-wedge deliverable; update `skills/` integration docs.
2. Frontend: confluence display on the Signals Board; decision on signal-card badge / guide.html update → §7 Q2.
3. Telemetry v1 = log the full condition vector with every analysis decision (one line; Phase 4 needs it). The nightly accuracy-rollup job is **deferred until something consumes it**; when built, it monitors only — pre-registered label definition, minimum cell n, Wilson CIs, and **no threshold changes from telemetry without a Phase-4-style re-validation** (multiple-testing discipline).

**Verify:** golden tests per condition incl. boundary values; 30-day snapshot replay comparing counts vs old fusion signals; API contract snapshot test.

### Phase 2 — regime filter, advisory-first (~2 days)

`service/server/regime.py`. **v1 = veto + size multiplier only. The contrarian panic-buy is cut from v1 entirely** (plan decision, recorded: it is the framework's highest-variance rule, it needs its own condition set — fear extreme fading + price > short MA + volume-climax-passed, NOT the trend checklist, which is unsatisfiable in a panic — and it must not precede backtest evidence; the faithful spec is preserved in §9 appendix for a later phase).

| Regime | Trigger (placeholders pending Phase 4) | Effect (when enforcement enabled) |
|---|---|---|
| trend | F&G ∈ [30,70) AND vol percentile < 70 | normal |
| caution | F&G ∈ [20,30) ∪ [70,80), or vol percentile ∈ [70,90) | size × 0.5 |
| panic | F&G < 20, or vol percentile ≥ 90, or unresolved shock | no new buys |
| euphoria | F&G ≥ 80 | no new buys; take-profit advisory |
| event | inside event window | no new entries |

- Vol percentile: today's `sigma_daily` (20-day, daily units — NOT `sigma_24h_pct`) vs a trailing **365-day** distribution (90 days is too few order statistics; bands flicker).
- **Regime transitions are persisted** (regime column on psych_snapshots or a small table): "panic day 0" = first snapshot satisfying the trigger after a non-panic snapshot; survives restarts. Missing/stale psych data → regime `unknown` → treated as caution for entries (conservative), never blocks exits.
- Phase 2 ships **advisory**: regime in fusion/psych payloads + journaled would-have-blocked decisions. Enforcement (`REGIME_FILTER_ENABLED`) exists but stays off until Phase 4.
- **Breaker redesign (prerequisite for any auto-trip):** add `expires_at` + `tripped_by` columns to `breaker_state`; auto-resume clears only `tripped_by='auto'` rows (never a manual admin HALT); auto-trip scope is **per-market** (`market:crypto`), not global; requires 2 consecutive shock readings (single-source OKX $5M/1h fires routinely — one reading is not a tail signal); risk-reducing sells must not be blocked by an auto-trip (reorder the halt check vs the sell bypass, risk_engine.py:308 vs :315). A named worker loop owns resume.

**Verify:** fixture-driven regime transitions incl. restart persistence; breaker trip/resume matrix (auto vs manual × expiry); advisory journal correctness.

### Phase 3 — risk & exit upgrades (~3–4 days)

All default-off; enforcement at Phase 4 flip.

- **Volatility sizing (corrected):** `target_notional = equity × RISK_BUDGET_PCT (0.5%) / sigma_daily_frac`, then subtract existing symbol exposure (mirrors the Kelly path — per-position budget, not per-order), capped by `config.size_usd` (user ceiling) and the Kelly cap, regime multiplier last. `sigma_daily is None → reject buy` (entry-null conservatism). Worked example in code comments: equity $100k, σ_daily 2.45% → target ≈ $20.4k; the old formula fed hourly σ (~0.5%) → $100k, a ~5× oversize that worsened in crashes. `max_symbol_exposure_usd = 0` (disabled) is forbidden while vol sizing is on. Honest note: with ½-Kelly active (W≈0.55, R≈1.0 → cap ≈ $5k on $100k), Kelly usually binds first; vol sizing is the backstop for the first 10 trades and fat-σ days.
- **Trailing stop:** per-agent `use_trailing`/`trail_pct` in `risk_limits` (and fix `put_risk_limits`'s hardcoded 5-column rebuild so new fields survive PUTs). Ratchet in the watcher AND in `execute_paper_trade`: **SL/TP writes never loosen an existing level** (`stop_loss = max(existing, new)` on longs) — otherwise every re-buy destroys the ratchet (automation.py:113–119). Exit hierarchy: once the trail is armed (profit ≥ 1×trail), the fixed TP is removed and the trail manages the exit ("let winners ride" — otherwise TP guillotines everything at +10% and the trail only ever lives in the 5–10% band). Known limitation: `current_price` refresh default is 900s → effective trail granularity ~15min; lower `POSITION_REFRESH_INTERVAL` for crypto or enable the push feed.
- **Time stop:** new `first_opened_at` column, set once at position open, **never updated on add-ins** (`opened_at` is reset by every average-in — services.py:295–298 — so the DCA'd losers the rule targets would never age). Close losers older than `TIME_STOP_DAYS (14)`; winners ride; re-entry cooldown `TIME_STOP_COOLDOWN_HOURS (48)` prevents fee-bleed churn (0.2% round trip per cycle). Timestamp parsing must handle both stored formats.
- **Exit-policy grandfathering:** positions gain an `exit_policy` tag at open; trailing/time-stop behaviors apply **only to positions opened under the policy**. Existing positions are untouched (no mass-close on flip day). Policy for pre-existing positions = §7 Q3 (owner decision).
- **Risk-direction gating (correctness fix):** `evaluate_order` gates by risk direction, not side — `buy`/`short` = opening (full gate), `sell`/`cover` = reducing (bypass). Today `short` would bypass everything (risk_engine.py:315–316); automation can't emit shorts yet, but the manual/agent API path can, and L2's short bias invites adding it later. Automation shorts remain out of scope for v1 (stated); **short-side watcher SL/TP is deferred** — it requires `cover` support + short cash accounting in `execute_paper_trade` (executor surgery, not a watcher query tweak). Documented as a known gap.
- **Exit-permissiveness rule:** position-reducing sells are exempt from any confluence/confidence gate (missing data must never trap a losing position; only the breaker's manual HALT may block exits).

**Verify:** ratchet integration test (buy → ratchet → re-buy → stop did not decrease); time-stop on DCA'd fixture; cooldown; σ-unit fixture; sizing worked examples; put_risk_limits round-trip preserves new fields.

### Phase 4 — validation & the flip package (~4–6 days)

**Strategy backtest** (second mode in `backtest.py`; roadmap divergence noted in 0.5): confluence + regime + Phase-3 sizing/exits over the Phase-0 corpus.

Honest scope table (from live verification — the backtest CANNOT evaluate the full live system):
| Condition | Historically evaluable? |
|---|---|
| B1, B2 | ✅ full |
| B3 | ⚠️ degraded — MA/RSI/volume legs only (funding/basis/OI/L-S have no deep history) |
| B4 | ❌ none (StockTwits/news snapshots are live-only) → **null throughout; validated live-forward only** |
| B5 | ⚠️ F&G leg full (2018+); shock leg = σ+volume proxy reconstructed from OKX 1H history (reaches ≥2020-06) — proxy-only, differs from live proxy+liquidations |
| B6 / event regime | ✅ after the 0.4 calendar backfill |
| S4 | ⚠️ F&G leg only (L/S history ~180d) |

Consequences, stated plainly: with B4 permanently null, historical "≥4/6" is a stricter system than live. The backtest therefore reports BOTH `≥4/6` (deployment-faithful, conservative) and `≥3/5 available` (sensitivity), and **only the historically-evaluated conditions earn default-on**; B4 and the L/S and liquidation legs stay off until ≥6 months of live telemetry (Phase 1 logging) supports them.

- **Per-asset windows** (verified listing dates + 1yr warmup): BTC/ETH signals from 2020-01 (2019 warmup); **SOL signals from ~2021-04** (Yahoo data starts 2020-04). No cross-asset averaging over unequal windows; report each separately.
- Bar-close signals, next-open execution; 0.1%/leg fees; 0.05% slippage placeholder. **Timestamp convention table required per source** (F&G stamps day-start UTC; crypto bars 00:00 UTC vs stock 16:00 ET; every non-price feature lagged to be strictly known at bar close; when in doubt lag one extra bar).
- **Anchored walk-forward, ≥4 folds** (expanding train, fixed test), **14-day purge/embargo** at every boundary (max holding period). Tunables validated: confluence min, F&G bands, vol bands, VOLUME_CONFIRM_MIN, L/S threshold, trail/time-stop params. **Report the number of configurations tried and apply a data-snooping correction** (White's Reality Check or deflated Sharpe — the research canonizes Sullivan 1999; we apply it to ourselves). Last fold untouchable until criteria are frozen in writing.
- **Pre-registered go/no-go (interval-based, not point thresholds):** minimum **400 pooled OOS trades**, else verdict = "insufficient evidence" (not PASS — at 60–250 trades a zero-edge strategy passes a naive 52% bar ~1 time in 3; distinguishing 52% from a coin flip needs ~1,700+ trades, so the accuracy leg uses CIs, not points); directional accuracy **Wilson 90% CI lower bound > 0.50**; profit factor **bootstrap 90% CI lower bound > 1.0**; absolute max-DD budget ≤ 30% (B&H-relative DD is trivially satisfied by any gated strategy — dropped). Always report buy-and-hold per asset alongside. Report the **calibration curve** (hit rate per confluence count, Wilson CIs) and the **condition correlation/agreement matrix** (B1–B3 are all trend measures; honest prior for OOS accuracy is 53–55%, with 55–58% as the optimistic bound).
- Promotion rubric replaces `sharpe > 0`.

**The flip package** (one coordinated deploy, only on PASS — these cannot be env-gated, which is why they live here and not Phase 1):
1. Env flips: `CONFLUENCE_GATE_ENABLED`, `REGIME_FILTER_ENABLED`, `RISK_ENGINE_ENABLED` (all **global** — "per new config" is not implementable with env vars; the runbook + exit-policy grandfathering handles retroactivity).
2. Automation gate switches to **count-based** `min_confluence` (default 4; buys and short-opens gated; position-reducing sells exempt). `min_confidence` is deprecated when the gate is on (journaled per rule) — **no affine confidence migration at all**, eliminating the v1 arithmetic-mismatch class of bugs. Presets become counts: 안정 = 5/6, 균형 = 4/6, 공격 = 4/6 + larger size. `_rule_based_decision` fallback switches to the count (behind the same gate).
3. Default sweep, all three places: frontend `DEFAULT_DRAFT` + 5-language recommendation copy (`AutomationPage.tsx`), API default (`routes_automation.py:31`), schema default (`database.py:1862`); backend guard rejects unreachable thresholds. UI copy explains the honest scale.
4. Data migration dual-pathed: alembic version (MySQL) **plus** versioned one-shot in `init_database()` (SQLite — alembic never runs there and no alembic version covers automation tables).
5. LLM decision remains interpreter/rationale; its emitted confidence is display-only once the count gate governs execution.
6. Runbook: announce → advisory period (regime/confluence journaling visible) → flip → monitor skip_reasons.

**Verify (the plan's own bar):** every number in the go/no-go pre-registered before the OOS fold is opened; two independent reruns of the backtest produce identical results (determinism); flip rehearsal on a staging DB snapshot for both SQLite and MySQL paths.

## 5. Sequencing & estimates

| Phase | Depends on | Size | Live-behavior change |
|---|---|---|---|
| 0 data foundations | — | 3–4 d | none (Sharpe metric display correction, journaled) |
| 1 confluence display/API | 0 | 2–3 d | none (display + agent API only) |
| 2 regime advisory | 1 | 2 d | none (advisory + breaker schema prep) |
| 3 risk/exit code | 0 | 3–4 d | none (default-off) |
| 4 validation + flip | 0–3 | 4–6 d | **everything, once, on evidence** |

Total ≈ 14–19 days. The thin early value (Phase 0–1, ~5–7 days) is itself shippable: agents and users get an honest, documented confluence read via API — the publish-side wedge — with zero execution risk.

## 6. Positioning

This track is the **model-quality track**, sequenced after the roadmap's Phase-1 foundations, which are (contrary to the stale docs) already landed in code: CI workflows, pydantic-settings config, alembic, broker ABC, backtest routes. It runs **parallel to, and does not block**, the undone product-sprint items (public leaderboard landing, anonymous paper-follow, curl registration page) — those touch different files. Whether it runs *before or after* them is the owner's call (§7 Q1). The Phase 4 backtest mode intentionally starts as a second mode in `backtest.py` rather than the roadmap's package layout — recorded as a dated divergence note in the roadmap (task 0.5).

## 7. Open questions for Henry

Resolved in-plan (per verification panel, so your attention isn't spent on them): universe = **crypto-only v1** (BTC/ETH signals from 2020-01, SOL from 2021-04; stocks need a paid AV key or a yfinance stock corpus — follow-up); contrarian panic-buy = **cut from v1** (spec preserved in §9); DVOL = **not v1** (real, free, but 2021-03+ and BTC/ETH only — F&G + realized-vol percentile suffice until Phase 4 says otherwise).

Remaining — genuinely yours:
1. **Priority:** run this track now, or after the product-sprint items (leaderboard/anonymous-follow/registration page)? Phase 0–1 (~1 week, zero execution risk, ships the agent-facing confluence API) could slot in first either way.
2. **Product surface:** should confluence/regime appear on published signal cards and follower UX in v1, and should the public guide.html gain the two new pipeline layers? (Engine API ships regardless; this is about public UI.)
3. **Existing positions at flip:** grandfather all pre-flip positions out of trailing/time stops (recommended; `exit_policy` tag), or advisory-notify then apply after N days?
4. **Deprecating `min_confidence`:** OK to auto-switch migrated rules to `min_confluence=4` with a journaled note per rule, or freeze old rules (keep trading on the legacy path) and require re-creation?

## 8. Verification log (6-agent adversarial panel, 2026-07-16)

| Agent (lens) | Verdict on v1 | Key findings adopted into v2 |
|---|---|---|
| 1 Research fidelity | 0 CRIT / 6 MAJ / 8 MIN | 50–55% not 55–58 (§1); confidence-cap self-contradiction (resolved by count-based gate); contrarian special unsatisfiable as spec'd (cut + faithful spec in §9); 1-month reversal restored (0.2); pattern-skip reframed as plan decision (§3); B4 recovering branch; S5 unresolved-not-72h; F&G bands labeled placeholders; volume/L-S added to tunables; elections noted; sell-side gating; half-open intervals; nonlinear-v2 note |
| 2 Codebase feasibility | 2 CRIT / 5 MAJ / 4 MIN | alembic-never-runs-on-SQLite → dual-path migration (flip pkg #4); B4/B6 history gaps (Phase 4 scope table); `_cache_covers` dead code (0.1); σ unit conflation (0.2, Phase 3); shock_history accessor doesn't exist (B5 note); short-close needs executor surgery (deferred); API/schema 0.65 defaults (flip pkg #3); AV unadjusted-close trap (0.1); v1's code anchors otherwise confirmed accurate |
| 3 Statistics | 2 CRIT / 4 MAJ / 4 MIN — "not approved" | backtest≠live strategy (scope table + dual thresholds + live-forward rule); vacuous go/no-go (400-trade floor, Wilson/bootstrap CIs, ~1,700-trade math cited); condition correlation (matrix + honest 53–55% prior); invented confidence map (replaced by count + empirical calibration only); migration arithmetic (eliminated — no affine migration); walk-forward (≥4 anchored folds, 14d purge, snooping correction); daily-equity-curve Sharpe; 365d vol window; telemetry multiple-testing discipline; timestamp conventions |
| 4 Risk management | 3 CRIT / 8 MAJ / 1 MIN — Phases 2–3 refuted | hourly-σ ~5× oversize (fixed: sigma_daily, None→reject); trail destroyed by re-buy overwrite (never-loosen rule); global breaker blast radius + unsafe auto-resume (per-market scope, 2 readings, expires_at/tripped_by, sells unblocked); sizing placebo/per-order (target semantics + exposure deduction); TP guillotine (trail-armed TP removal); opened_at reset (first_opened_at + cooldown); panic day-counter persistence (regime transitions table); sell-confidence trap (exit exemption); ungated short-open (risk-direction gating); env-flag scoping error (global flip + runbook); put_risk_limits column reset; 900s price staleness noted |
| 5 Data availability | 2 CRIT / 4 MAJ / 2 MIN / 1 PASS | SOL 2019 impossible (per-asset windows); B4/B6 nulls → different backtested system (scope table, calendar backfill, dual thresholds); L/S 180d + liquidations 24h (S4/shock degradation declared); AV premium/25-req reality (yfinance for corpus & stocks); OKX-vs-Yahoo spot/perp mismatch (sanity diff); PSYCH_FEED_ENABLED prerequisite; F&G limit=0 PASS (verified 3,084 rows); DVOL 2021+ BTC/ETH only; yfinance weekly-downsample trap |
| 6 Product & scope | 2 CRIT / 4 MAJ / 4 MIN — "not approved as-is" | recalibration can't be env-gated → moved wholesale to flip package; frontend 0.65 default + 5-language copy would strand new rules (default sweep); thin v1 named (Phase 0–1 shippable alone); product-surface section + skills/ docs + agent API contract; positioning §6 + stale-doc corrections (0.5); existing-position grandfathering (exit_policy); contrarian cut; telemetry consumer-less job deferred; null-starvation observability (skip_reason names starving conditions); open questions rewritten |

Convergent independent confirmations (highest-confidence findings): migration arithmetic error (agents 1, 2, 3, 6 — resolved by eliminating the migration), backtest/live condition-history mismatch (2, 3, 5), hourly-σ unit bug (2, 4), frontend/API/schema default stranding (2, 6), opened_at reset (2, 4).

## 9. Appendix — contrarian panic-buy (deferred spec, research-faithful)

For a later phase, after Phase 4 exists and only with its own validation: trigger = fear extreme **fading** (F&G < 20 with delta_3d > 0, or shock cleared per shock_history) AND price stabilized above short MA (MA5) AND volume climax passed (volume_ratio declining from its spike peak) → mean-reversion **buy at half size**, its own env gate, never via the trend checklist (B1/B2/B4 are false by definition in a panic — requiring them makes the rule dead code, which is how v1 had it).

---

*v2 — all six verification verdicts folded in. Not investment advice; the platform trades simulators only.*
