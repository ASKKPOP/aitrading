# Plan 14 — Full Auto Trading ("Fleet Mode"): AI Research → N Runs → Step Trading → Feedback

**Status:** v1 Verified (2026-07-20) — synthesized from a 5-planner design round, then reconciled against **70 findings from 9 QA agents** (9 critical / 38 major / 23 minor; verdicts: 5× sound_with_fixes, 4× flawed → every critical and major finding is folded into this document). The two parallel orchestrator designs the planners produced have been **arbitrated into one**; the losing variants are deleted, not appended.
**Owner:** Henry
**Scope:** A "fleet" layer ON TOP of the deployed Trading Runs subsystem (Plan 10) and Automation engine. Simulated (paper) ledger only. The user configures the number of runs (N) and presses go; the AI researches symbols across all automatable markets, composes and registers N runs at sooppiy.com/automation, each run step-trades on its interval, and every outcome feeds the next step's decision.
**Companion:** `14-full-auto-trading.html` — visual version (flows, charts, tables, diagrams).

---

## 1. Executive summary

Henry's requirements, traced end-to-end:

| # | Requirement | Where it lands |
|---|---|---|
| a | Research high-potential symbols across spot / futures / us-stock / others | `symbol_research.py` global 3-stage funnel (§4) over `markets.automatable_markets()` = crypto, us-stock, futures, forex *(a-stock removed 2026-08-01 per owner — China trading dropped platform-wide)* |
| b | "Expected profit" defined from technical + human/psychology + social + economics + global issues + **government law & policy** + other parameters | 8-factor-family taxonomy (§5) incl. new `policy_feed.py` (Federal Register) and Polymarket geopolitics odds — policy is a first-class Stage-1 factor, not an afterthought |
| c | Analyze and rank AI trading targets | Deterministic EPS composite + fee-adjusted EV/day ranking; one bounded LLM thesis call per refresh (§4.3, §5.3) |
| d | User defines ONLY how many runs | One N stepper; budget **defaults** from tier, risk defaults to balanced, markets default to all — everything else behind an Advanced expander (§9). Deviation surfaced as open question Q1. |
| e | AI creates AND registers the runs (visible at sooppiy.com/automation) | `fleet_planner.py` build pipeline → internal `trading_runs.create_run`/`start_run` → ordinary runs on the /automation page and RunsLivePage (§6) |
| f | STEP TRADING per run, per interval | Unchanged `run_engine.run_cycle` — fleet members are 100% ordinary runs |
| g | Analyze each result (profit/loss) → feed the next step | `run_feedback.py` anti-martingale adaptation ladder + thesis drift + retirement/rotation (§7) |

**Headline reuse finding:** the execution machinery again ~80% exists. Runs (state machine, lease-claimed cycles, per-run books, stop conditions, fee-inclusive P&L, `/ws/runs` telemetry) are deployed; `agent_planner.py` already proves the house pattern — *the LLM proposes inside a deterministic box, code disposes*. What's genuinely new: a global research engine, a fleet orchestration envelope, a per-run feedback controller, and **budget enforcement at execution time** (which QA proved does not exist today — see D5).

What we build (4 new modules, 1 new route file, 1 combined migration):

| Gap | What we add |
| --- | --- |
| Symbol research across markets | `symbol_research.py` — global 3-stage funnel, `research_theses` batches, ≤ 1 batched LLM call/refresh |
| Policy/geopolitics factors | `policy_feed.py` (Federal Register, keyless) + CNN Fear&Greed fetcher; Polymarket odds already ingested |
| Fleet envelope | `fleets` + `fleet_events` + `fleet_slots` + `fleet_candidates` + `fleet_symbol_cooldowns` + `research_batches` tables (+ users/automation_configs master-control columns); `fleet_planner.py` lease-claimed loop |
| N-run registration | Build pipeline via internal `create_run`/`start_run`, per-candidate exclusivity recheck, persisted-by-key allocations |
| Budget actually enforced | `run_budget_usd` becomes a hard **deployed (open) cost-basis** cap inside `run_cycle`'s gate (today it is reporting-only) |
| Outcome → next step | `run_feedback.py` — per-closing-leg W/L ingestion, anti-martingale ladder, cooldowns, thesis review, `adapt_retired` |
| Fleet safety rails | Two-tier drawdown rails (−30% warn+SMS / −40% stop-all+SMS, marked equity, fail-closed), replacement allowlist, no auto-restart for members, supervision watchdog |
| User master control | Account-level hold / resume / remove of ALL AI automation (§6.7) — `POST/GET /api/automation/master`, header switch |
| Product surface | "② Full Auto" mode on AutomationPage, FleetCard, run event-log timeline in RunsLivePage, `GET /api/entitlements/me` |

---

## 2. Reconciliation decisions (binding — the QA arbitration)

The 5-planner round produced **two complete parallel fleet designs and four research topologies**. Per QA (`completeness`, `concurrency`, `codebase-feasibility`, `schema-api` — all flagged this as build-blocking), the following choices are final. Anything in an earlier draft that contradicts this table is dead.

| Axis | DECISION | Killed alternatives |
|---|---|---|
| Orchestrator module | `service/server/fleet_planner.py`, registry key `fleet_planner`, worker role `settlement`, tick 60s | `fleet_orchestrator.py` @20s |
| Fleet tables | `fleets`, `fleet_events`, `fleet_slots`, `fleet_candidates`, `fleet_symbol_cooldowns`, `research_batches` (+`trading_runs.fleet_id`/`created_via`/`adapt_state_json`, `users.ai_automation_state`/`ai_automation_held_at`, `automation_configs.held_by_master`) | `trading_fleets` |
| Research module | `service/server/symbol_research.py` — **platform-GLOBAL** batch loop; factor taxonomy (§5) is its Stage-1 scorer | `fleet_research.py`, `fleet_score.py` as separate modules; per-fleet research passes; `daily_research_passes` entitlement |
| Research persistence | `research_theses` (global batches) + per-fleet `fleet_candidates` (selection journal only, no LLM of its own) | `fleet_candidate_scores` |
| LLM research topology | **One batched call per refresh** over the ≤16 Stage-1 survivors (strict-JSON array of theses), reuse-on-unchanged-inputs; platform OpEx with hard throttle `FLEET_RESEARCH_MAX_LLM_CALLS=2` (1 + 1 retry) per refresh | per-survivor calls (≤16/hr); per-fleet build calls (1+N); per-fleet metered passes |
| Retirement authority | **Run level only**: `run_feedback.py` `adapt_retired`. Fleet layer NEVER self-fires a health rule; it only *reacts to member stop events* | fleet monitor's independent "−10% after ≥5 trades" rule |
| Replacement triggers (per stop reason — the ENUMERATED list is authoritative; any future `stop_event:*` kind must be classified here before shipping) | **Immediate replacement**: `stop_event:max_loss/profit_target/max_trades/at_time/price_cross`, `adapt_retired`. **Deferred**: `stop_eval_failed` ⇒ `slot_waiting`, replaced from the next *healthy* research batch; `synthetic_liquidation` ⇒ 24h symbol cooldown written at liquidation, slot waits, then replaced. **Never replaced**: `user_stop` of a single member ⇒ slot state `closed` = permanent user shrink (Q9 asks Henry to confirm vs backfill); `agent_deleted` ⇒ the whole fleet stops (`stopped('agent_deleted')`) | prose rule "any condition stop"; binary allowlist with undefined excluded-reason slot states; unclassified `price_cross` |
| Replenishment policy | **Perpetual N maintenance (Henry directive 2026-07-20):** the fleet maintains N active members until the user stops it — subject only to the per-reason table above, the drawdown-warning suspension (§6.5.1: no replacements while the warn latch is unacked or the fleet is paused/held), symbol cooldowns, and candidate availability. Count-uncapped; churn alert (not a block) at >8 replacements/day/user; replacement selection costs zero research LLM (global batch). Only two automatic terminals: the −40% rail and `agent_deleted` — the round-4 `equity_floor` terminal is **deleted as dead code** (round 5 proved it re-created the same unreachability: all-dormant with zero active members requires equity < B/2N ≤ 0.5B, but the −40% rail always fires first). Unfundable slots stay `dormant` and re-evaluate every tick | 4/day and 3/day rotation caps; fleet auto-stop on `all_runs_stopped`; unreachable `budget_exhausted` AND unreachable `equity_floor` terminals |
| Fleet size gate | `max_fleet_size` per tier in PLAN_LIMITS: none 0 / junior 0 / pro 3 / professional 10 / enterprise 25 — **always-on**, not behind `enforcement_enabled()` (LLM spend is a direct cost, same class as the SMS gate) | headroom-only gating; enforcement-flag-gated checks |
| Concurrent fleets | **One non-terminal fleet per USER** in v1: `active_fleet_key = 'user:{user_id}'` nullable-UNIQUE (the runs `active_key` trick, resolved at create) + client idempotency key on POST. Per-user is what the §9.2 cost model assumes — a per-agent key would permit several fleets per user via multiple agents | unlimited fleets; per-AGENT uniqueness (contradicted the cost model) |
| Thesis contract | One canonical schema (§4.4), stored at `config_snapshot_json.thesis` (top level) | `conviction`/`expected_gain_pct` variants; `.fleet.thesis` nesting |
| Migration numbers | Assigned at merge time, chained off the then-current head (0027_active_key_filter today; market-expansion lands first). **One combined revision** for all fleet-mode DDL | both hard-coded "0028" claims |
| Frontend mode chip | Keep ⓪ Agent ① Simple ordering; append **"② Full Auto"**. Poll `GET /api/fleets/{id}` at 2s while researching/building, 15s while active | new-⓪ renumbering |
| Drawdown rails (Henry directive 2026-07-20) | **Two-tier on MARKED equity** (one definition, §6.3.0): −30% ⇒ WARNING — SMS+email+in-app, member entries paused, replacements suspended; **episode-latched** so user resume sticks (re-arms on recovery above −25%, plus one fresh warning per additional −5% leg). −40% ⇒ **stop-all flatten** + SMS, **evaluated FIRST** (a gap through both tiers ⇒ one stop-all, one SMS). Rail alert kinds get a **reserved send budget** in `alerts.py` (RUN_STOPPED_RESERVE pattern) so churny days cannot starve the mandatory SMS. Thresholds user-**tightenable only**; stop tier hard-clamped ≤ 0.40 | single `fleet_max_loss_frac` 0.20; level-triggered warning with no latch; shared 10/h alert budget |
| User master control (Henry directive 2026-07-20) | **Account-level kill switch** spanning fleet + all runs + all automation rules across every agent linked to the user: `hold` (reversible, marker-stamped: RUNNING runs → `paused_reason='master_hold'`; **armed runs stay `armed`** — armed→paused is an illegal engine transition, they are blocked by the `_control_armed` account-held guard and their armed-timeout clock is suspended while held; fleet held-marker in its own field, `status_reason` recomputed by the next supervise pass; rules `held_by_master=1`), `resume` (restores only marker-carrying objects; members of a warn-latched fleet convert to `paused_reason='drawdown_warning'`, NOT running — §6.5.1), `remove` (stop-all flatten + disable rules + fleet stopped). One POST action endpoint + one GET state endpoint, hosted in `routes_automation.py` (user-session auth) | per-object-only controls; marker-less hold; pausing armed runs (illegal transition + start-condition bypass on resume) |
| Env vars | `FLEET_ENABLED`, `FLEET_TICK_INTERVAL` (60s), `FLEET_RESEARCH_ENABLED`, `FLEET_RESEARCH_INTERVAL` (3600s, global loop) | per-fleet `FLEET_RESEARCH_INTERVAL=360min` semantics |

---

## 3. Architecture overview

```
                    ┌────────────────────────────────────────────────────────┐
                    │ worker.py (role=settlement) — BACKGROUND_TASK_REGISTRY │
                    │  ├─ trading_runs   → run_engine.tick()        [EXISTS] │
                    │  ├─ fleet_planner  → fleet_planner.tick()     [NEW]    │
                    │  ├─ symbol_research→ research refresh loop    [NEW]    │
                    │  ├─ policy_feed    → Federal Register loop    [NEW]    │
                    │  └─ scanner/psych/social/news/whale loops     [EXIST]  │
                    └───────┬──────────────────┬─────────────────────────────┘
   GLOBAL (platform OpEx)   │                  │   PER-USER (tier-metered)
 ┌──────────────────────────▼───┐   ┌──────────▼─────────────────────────────┐
 │ symbol_research.py           │   │ fleet_planner.py                       │
 │  Stage 0 universe (~198)     │   │  claim → RESEARCH-consume → BUILD      │
 │  Stage 1 factor screen (§5)  │   │  → SUPERVISE (breaker/rotation)        │
 │  Stage 2 ONE LLM thesis call │──▶│  FLEET_BOUNDS clamps                   │
 │  research_theses batches     │   │  select_targets(agent, n)              │
 │  select_targets()            │   └──────┬─────────────────────────────────┘
 └──────────────────────────────┘          │ internal create_run/start_run
                                  ┌────────▼──────────────┐
                                  │ trading_runs ordinary  │  run_feedback.py [NEW]
                                  │ runs (fleet_id set)    │◀─ adapt ladder, cooldowns,
                                  │ run_engine cycles      │   thesis review, retire
                                  └────────┬──────────────┘
                                           │
                          routes_fleets.py [NEW] + AutomationPage "② Full Auto"
                          + FleetCard + RunsLivePage event timeline
```

Design stance (inherited from `agent_planner.py`, one level up): **a fleet never trades**. It is a research-consume / build / supervise envelope over ordinary runs, so exclusivity, entitlements, stops, P&L, telemetry, and RunsLivePage come for free. The fleet planner proposes runs; `trading_runs.start_run` + `entitlements.check_run_start` dispose.

---

## 4. Symbol research engine (`symbol_research.py`)

One platform-global loop (`FLEET_RESEARCH_ENABLED`, default off; `FLEET_RESEARCH_INTERVAL` default 3600s, min 900). One batch serves every fleet — LLM cost is O(1 batched call)/refresh flat regardless of user count. Research is platform OpEx like the scanner/market-intel loops, bounded by hard throttles, **never** by user tiers.

### 4.1 Stage 0 — candidate universe (~198 symbols, zero new rate-limit exposure)

Driven by `markets.automatable_markets()` (polymarket/options auto-excluded — QA killed every polymarket reference):

| Market | Source | Size |
|---|---|---|
| crypto | OKX USDT-perp top-50 by 24h volume ∩ Hyperliquid priceable set, ∪ scanner candidates (discovery channel) | ~50 |
| us-stock | `routes_market.US_STOCK_SYMBOLS` (72 — **not** "STOCK_SYMBOLS", QA-corrected) ∪ `market_intel._get_hot_us_stock_symbols()` | ~80 |
| futures | `routes_market.FUTURES_SYMBOLS` (21 roots, all with `FUTURES_MULTIPLIERS`) | 21 |
| forex | `routes_market.FOREX_SYMBOLS` | 30 |

### 4.2 Stage 1 — deterministic factor screen (zero LLM)

**New data primitive:** `price_fetcher.get_daily_candles(symbol, market, days=60)` — Yahoo v8 chart `interval=1d&range=3mo` (the exact call `_get_yahoo_chart_price` already makes, returning OHLCV arrays), crypto via `crypto_feed.fetch_candles`. Cached 6h per (market, symbol) **with per-symbol TTL jitter** so entries don't expire together.

**Rate-limit posture (QA `data-feeds` fixes, all folded):**
- The sweep is **cooldown-aware and subordinate to the money path**: before each fetch, check the Yahoo cooldown — nonzero ⇒ serve cache. Honest scope (QA-corrected): the cooldown dict is **process-local module state**, so this check protects only the same-process money path (the role=all worker); `_probe_price` runs in the API container and a role-split worker holds its own dict. **Cross-process protection comes from the pacing** (next bullet), and `symbol_research` is pinned to the `settlement` worker role so it always shares a process with run cycles and the SL/TP watcher.
- Cold sweep (~148 non-crypto symbols) is **spread across the refresh interval** (~1 call/23s), not a 1s-spaced burst.
- Named test: activate the yahoo cooldown → research loop returns cached candles, zero HTTP calls.
- **Alpha Vantage is never called** from research. Its snapshots are read-only inputs, and every snapshot read carries an **age gate: older than 2× its refresh interval ⇒ factor = None** (coverage shrinkage handles it). This closes the QA finding that dead AV-premium snapshots (`available:True`, no age check) would silently feed a 0.40-weight factor.
- Cross-asset macro tone (QQQ/XLP/GLD/UUP) is computed **from Yahoo daily candles via the same primitive** — the existing `_build_macro_signals` path uses AV `TIME_SERIES_DAILY_ADJUSTED`, which is **premium and dead on the prod free key** (QA-verified). ETF flows and AV stock-analysis snapshots move to v2 ("requires AV premium key").
- News cadence is made honest: `MARKET_NEWS_REFRESH_INTERVAL` → **4h** (4 categories × 6 passes = 24 AV calls/day, exactly fitting the 25/day free cap deterministically instead of first-25-wins). Factor tables state real freshness 4–6h. Per-ticker headlines stay on Finnhub (60/min free).
- StockTwits is read **only through existing snapshot tables** — research adds no second caller against an undocumented rate limit.

The scorer itself is pure functions on snapshots + candles (§5). Hard gates (liquidity floor, ≥30 candles, Hyperliquid-priceable for crypto) drop candidates; scored factors produce the composite; **top-K per market** (4 crypto / 4 us-stock / 2 futures / 2 forex ⇒ ≤ 12–14 survivors) keeps cross-market diversity.

### 4.3 Stage 2 — ONE batched LLM thesis call

One `llm_client.generate_text(tier="decision")` call per refresh over all survivors (compact factor scoreboard + cached headlines + macro/regime/event context in, strict-JSON array out). Hard throttle `FLEET_RESEARCH_MAX_LLM_CALLS=2` per refresh (primary + one retry on parse failure). **Thesis reuse:** a survivor whose Stage-1 inputs are unchanged (same candle date, |Δcomposite| < 0.1σ) keeps its previous thesis — quiet refreshes cost zero LLM.

Per-thesis deterministic clamps (`THESIS_BOUNDS`, the `PLAN_BOUNDS` twin): direction forced long where `supports_short` is false or the book is spot; `expected_move_pct ∈ [0.3, 3 × σ_daily × √horizon_days]`; `horizon_hours ∈ [4, 168]`; `confidence ∈ [0.40, 0.95]`. Parse failure per symbol ⇒ rule-based fallback thesis (`planner='fallback'`): direction = sign(momentum), expected_move = 1.5σ√h, confidence from score percentile. The engine degrades, never blanks. LLM may not introduce symbols absent from the scoreboard.

**Refresh concurrency (QA-corrected — the earlier guard could not work):** `batch_id` is **deterministic per refresh window** — `f"research:{int(now // FLEET_RESEARCH_INTERVAL)}"` — and a one-row `research_batches` sentinel table with `UNIQUE(batch_id)` is inserted **first**; the second concurrent refresher's sentinel INSERT fails and it aborts **before** any LLM call. The Redis lock (`cache.acquire_lock("fleet_research:refresh")`) is a best-effort fast path only: `acquire_lock` returns None when Redis is absent (Redis is optional), so the deterministic sentinel is the guarantee. Named test: dual simulated runners **with Redis absent** ⇒ one batch, one LLM call. (A random per-run batch_id never collides on any unique key — that was the bug.)

### 4.4 Canonical Thesis contract (the ONE schema — producer, builder, and feedback all import it)

```python
# symbol_research.py — the single source both fleet_planner and run_feedback cite
THESIS_SCHEMA = {
  "symbol": str, "market": str, "market_type": "spot|futures",
  "direction": "long|short",
  "confidence": float,          # 0.40–0.95  (the field is 'confidence'; 'conviction' is dead)
  "expected_move_pct": float,   # PERCENT units, e.g. 2.5 == 2.5%  (unit stated in the name's docstring)
  "horizon_hours": float,       # 4–168
  "entry_ref_price": float,     # stamped by fleet_planner AT RUN CREATION from the probe price
  "rationale": str, "sources": dict, "invalidation": str,
  "batch_id": str, "planner": "llm|fallback",
}
# Storage on a member run: config_snapshot_json["thesis"] = {…}   (TOP level, not .fleet.thesis)
```

An integration test builds a fleet from a real research batch and asserts the feedback loop's drift metric **actually evaluates** (this failed silently in the unreconciled draft).

### 4.5 Expected profit & ranking

```
round_trip_cost_pct = 2 × 0.1 (fees) + spread_proxy_pct(market_class)
ev_pct        = expected_move_pct × confidence − round_trip_cost_pct
ev_per_day    = ev_pct / (horizon_hours / 24)
final_score   = (ev_per_day / realized_vol_daily) × event_penalty × regime_penalty × session_factor
```

Negative-EV theses persist (transparency) but are `selectable=0`. All EPS numbers carry the `psych_feed`-style **"estimated"** labeling — never presented as calibrated probabilities.

`select_targets(cursor, agent_id, n)` — the builder-side selector: latest non-expired batch → drop (agent, market, symbol) with any non-terminal run → drop rows in `fleet_symbol_cooldowns` (the feedback contract — this table now **has DDL**, §8) → per-market diversity cap ceil(n/2) → first n. Batches expire at 2× the refresh interval (`scanner.top_candidate` staleness convention) so a dead loop can't feed stale symbols.

---

## 5. Expected-profit factor model (Stage-1 scorer inside `symbol_research.py`)

8 factor families; every signal reduces to a subscore x_f ∈ [−1, +1] or a multiplicative veto gate. **The scorer makes ZERO external calls** — enforced by a named no-network test (all fetchers monkeypatched to raise; scoring cycle must complete with coverage renormalization), not just review discipline.

| Family | v1 signals (sources all existing unless marked NEW) | Weight profile role |
|---|---|---|
| F1 Technical | 12-1 momentum, MA200 distance, RSI(14) U-shape, volume ratio, realized σ, perp basis (`quant_crypto`, `market_intel`, `scanner`) | 0.30–0.50 by market |
| F2 Psychology | Crypto Fear&Greed (contrarian), regime (VETO+size mult via `_ENTRY_POLICY`), liquidation shock (gate), funding/long-short (contrarian, `factor_snapshots`), **NEW** CNN Fear&Greed for us-stock (unofficial endpoint, fail-soft) | 0.05–0.20 |
| F3 Social | StockTwits tilt + declared bull/bear, mention surges (attention-capped), X/FB dormant behind creds (v2) — **snapshot reads only** | 0.10–0.15 |
| F4 News | AV NEWS_SENTIMENT category snapshots (**honest 4–6h freshness**), sentiment-spike z (our own history), Finnhub per-ticker headlines (LLM stage reads), macro news tone | 0.15–0.30 |
| F5 Economics | FOMC/CPI/NFP event windows (**VETO** ±60m, haircut <24h), FRED series (LLM context), cross-asset tone **via Yahoo candles** (QA fix), DXY/kimchi premium | 0.10–0.40 |
| F6 Geopolitics | Polymarket anticipation odds deltas (fed/tariff/recession/treasury topics — already ingested); GDELT = v2 | ±0.2 nudges |
| F7 Gov/Policy | **NEW `policy_feed.py`** (~150 lines, `market_events.py` pattern): Federal Register API (keyless, official) — agency+term watchlists (SEC/CFTC/Treasury × digital-asset/stablecoin; sector map for equities) → attention flag; *direction* comes only from the LLM thesis reading titles (policy direction is not keyword-scorable — stated honestly). Polymarket regulatory odds (`ANTICIPATION_TOPICS` already covers sec/cftc/regulation/etf) | 0.10 (us-stock/crypto) |
| F8 Flows | Whale exchange flows, OI change, new listings (`whale_feed`, `factor_snapshots`, `scanner`); BTC ETF flows → **v2 (AV premium)** | 0.10 |

Composite: per-market `WEIGHT_PROFILES` (env-overridable constants), missing source ⇒ x_f = **None, never fabricated 0**; renormalize over available families; `rank_score = eps_raw × √coverage` (thin markets compete without fake data); veto gates multiply (event window, regime panic/euphoria, session, shock, exclusivity); fee-hurdle eligibility (`expected_move > 2 legs + slippage`).

**Test plan for this scorer (QA `test-verification` demanded it — it had none):** pure-function tests on synthetic subscores (renormalization with missing families, shrinkage monotonicity, veto zeroing, hurdle boundary); mutations that MUST fail the suite (flip one weight sign, treat None as 0, drop one veto); fail-soft tests for both new fetchers (CNN 404/shape-change → None); the no-network test above.

All weights/constants are **unvalidated priors** — journaled from day one in `factor_scores_json` so the feedback loop can eventually close factor→outcome, walk-forward-tuned later through `backtest_strategy.py`. v2 feeds itemized: X API paid, AV premium, GDELT, Marketaux, economic-calendar surprise deltas, Coinglass, EDGAR/Congress.gov.

---

## 6. Fleet orchestration (`fleet_planner.py`)

### 6.1 Fleet = envelope row owning ordinary runs

Member runs are created through `trading_runs.create_run`/`start_run` **in-process** (typed exceptions drive candidate fallback; no HTTP self-calls). Small refactor: extract `routes_runs._validated_config` into a ValueError-raising `validate_run_payload()` shared by the route (wraps to HTTPException) and the builder (catches as candidate-skip; includes the `_probe_price` check so unpriceable candidates die before a row exists).

State machine: `draft → researching → building → active ⇄ paused → stopping → stopped` (+`status_reason`), lease columns copied from the run protocol (short committed claim transaction — the hard-won exactly-once model; do not invent a second concurrency scheme).

### 6.2 Creation is idempotent and single-fleet (QA critical fix)

- **One non-terminal fleet per USER**: `active_fleet_key = 'user:{user_id}'` nullable-UNIQUE column (user_id resolved from the agent at create; set while status ∉ {stopped}, NULL after) — a real DB constraint on both dialects, exactly the runs `active_key` trick. Per-USER, not per-agent: users own multiple agents, and the §9.2 cost model depends on one fleet per user. Double-click cannot yield 2 fleets / 2N runs / 2× budget, and no racy COUNT is needed.
- POST accepts a client idempotency key stored on the row; the Launch CTA disables on click.
- An agent with no linked user (`agents.user_id` NULL) cannot create a fleet (400, localized) — the key, the master control, and tier gating all resolve through the user.

### 6.3 Budget: allocated by key, enforced at execution (QA criticals D5/D8 — the money-safety core)

**§6.3.0 Definitions (ONE equity, used everywhere — the checker round proved a realized-only refund path lets unrealized losses fund fresh exposure):**
- **Marked equity** = `total_budget_usd + Σ compute_run_pnl['total']` (realized + mark-to-market unrealized) over ALL runs ever attributed to the fleet, **fail-closed** on any open-position member with `mark_age_ok=False`. This single number drives the rails (§6.5.1), replacement funding, and slot dormancy. There is NO realized-only equity anywhere in fleet accounting. Performance: replay `compute_run_pnl` only for non-terminal members; cleanly-stopped members contribute their `realized_pnl_usd` stamped at the stop transition (existing `_cache_realized_pnl` machinery; fall back to replay only if the stamp is missing).
- **`positions_held` zombie tracking (round-5 critical — the engine severs `positions.run_id` at exactly this terminal, so the naive replay sees nothing):** for a fleet member terminating as `stopped('positions_held')`, open quantity and cost basis are reconstructed **from the run's own signals replay** (`signals.run_id` is never cleared) and marked against a **fresh price fetch** for that (market, symbol), with the same staleness fail-closed rule — a missing or stale mark on a zombie is a rail-evaluation **FAILURE**, never `unrealized=0`. At the transition, the slot records the agent's pre-existing unowned quantity for that symbol; the zombie counts as closed when the unowned book returns to ≤ that quantity (the watcher's or the user's closing legs write to the unowned book). Mutation test: delete the reconstruction ⇒ rails must fail stale, not report healthy.
- **Slot** = one of the N persistent budget positions, stored in the `fleet_slots` table (§8): `(fleet_id, slot_index, original_allocation_usd, state active|waiting|dormant|closed, current_run_id)`. Replacements inherit the retired member's `slot_index`; "original slot allocation" = `fleet_slots.original_allocation_usd`, immutable after build. `closed` = permanently vacated by a `user_stop` (§2). **Dormancy is re-evaluated every supervise tick**: `dormant → waiting` when headroom recovers ≥ B/2N — dormancy is never sticky.
- **Headroom** (for funding a replacement) = `marked equity − Σ run_budget_usd of currently active members − Σ reconstructed open cost basis of positions_held zombies occupying slots`. **Within one supervise pass replacements are funded sequentially and headroom is recomputed after each funding** (equivalently: Σ fundings this pass ≤ headroom at pass start) — two slots freed by one market-wide move must not both fund from the same snapshot (named test with mutation: reuse the snapshot, must fail; zombie-basis test: basis Z reduces funding by Z, mutation drops the Z term).
- **Equity-evaluation failure freezes money (round-5):** a tick whose marked-equity evaluation fails (stale zombie or member mark) freezes ALL equity-derived mutations — no replacement funding, no dormancy transitions — journaled once per episode; K=5 consecutive failures escalates per §6.5.1. Test: stale-marked member + freed slot ⇒ no replacement that tick; recovery ⇒ funded next tick.

1. **Allocation persisted at plan time**: after `select_targets`, `allocate_budget` (confidence-weighted, clamped to [B/2N, 2B/N], Σ ≤ B) is journaled as one `allocation` fleet_event mapping **thesis_key → allocation_usd** in a single transaction BEFORE any run is created, and each selected thesis is bound to a `slot_index`. `_do_build` consumes allocations **by key, never positionally** — a crash/resume with a changed conflict set can no longer assign candidate k the allocation computed for candidate j (the 2×B worst case is closed). Skipped candidates' allocations stay unspent unless a journaled re-allocation event reassigns them.
2. **`run_budget_usd` becomes a hard DEPLOYED (open) cost-basis cap** (today it is validated at creation and then read only by reporting — QA-verified; "cumulative" was the wrong adjective — an all-time sum would strangle perpetual stepping). In `run_cycle`'s gate config:
   `size_usd = min(max_bet_usd × size_mult, run_budget_usd − open_cost_basis)` with open basis from the same per-leg replay `compute_run_pnl` does; headroom < min notional ⇒ cycle skipped, journaled `budget_headroom_skip` (renamed — `budget_exhausted` no longer names two things). Applies to fleet-created runs (`created_via='fleet'`); manual runs keep today's semantics (flagged in docs).
3. **Replacement budget under perpetual N (Henry directive):** a replacement for slot k is funded with `min(original_allocation_usd[k], headroom)` — both terms from §6.3.0, so **unrealized losses reduce replacement funding exactly like realized ones** (property test with mutation: fund from `realized` instead of `total` — must fail). A slot can never grow past its original allocation. Headroom below the floor B/2N ⇒ the slot goes `dormant` (journaled + alert; re-evaluated every tick per §6.3.0) instead of shrinking silently. **Replacement suspension is STATE-based, not level-based (round-5):** suspended while the warn latch is fired-and-unacked, or the fleet is paused/held (§6.5.1/§6.7); acknowledgment re-enables replacements regardless of the equity level, each funded from then-current headroom. Freed slots wait (`slot_waiting`) meanwhile.
4. **Invariants, property-tested** (restated for perpetual mode): (i) Σ **active** member `run_budget_usd` ≤ `total_budget_usd` at every supervise tick; (ii) per-run open cost basis ≤ `run_budget_usd`; (iii) the −40% rail fires at the FIRST supervise tick where marked-equity loss ≥ `stop_loss_frac × total_budget_usd` — stated honestly: losses beyond 40% **between** discrete ticks (gaps, outages) are possible and no SMS copy may promise otherwise. Mutations (drop the active cap / let a slot grow / skip either rail / realized-only funding) must fail the suite.

### 6.4 Build pipeline

For each thesis from `select_targets` until N members exist:
- **Per-candidate exclusivity recheck inside the start transaction** (QA major): `SELECT … FROM trading_runs WHERE agent_id=? AND market=? AND symbol=? AND status IN (active set) FOR UPDATE` immediately before create/start. The `active_key` UNIQUE is **strategy-level** (agent+market+symbol+filter_key since 0027) and will NOT block a fleet config differing from a user's manual config — the plan no longer claims it does. A user manually starting a run mid-build now loses the race cleanly instead of double-exposing the symbol.
- `fleet_id` and `created_via='fleet'` are **columns on the INSERT** in `create_run` (no separate stamp step — the crash window between create/stamp/start is gone). Resume logic treats members by status: a stamped draft is "start pending", not "done".
- Composition (`_compose_run_config`, pure): short thesis → crypto `market_type='futures'` / futures book / else skip (`supports_short`); interval = max(risk default, per-market floor); **unit conversion at the boundary (QA major): `gain_frac = clamp(expected_move_pct / 100.0, 0.002, 0.50)`** → `profit_target_usd = run_budget × gain_frac` (a 2.5% thesis on $1,000 ⇒ $25 target, not $500; unit property test + mutation of the /100). Stops: `max_loss_usd = run_budget × {stable .05, balanced .10, aggressive .15}`, `profit_target_usd`, `at_time = now + horizon_hours`. `max_bet = min(run_budget × frac[risk], tier max_bet cap, $1M)` — QA showed unclamped values are deterministically rejected by `RunIn`/entitlements at realistic budgets; POST also validates budget-vs-tier×N with a localized 400 **before** any async work.
- **`risk_level` decision (QA major):** fleet runs rely **solely on run-level stop conditions + risk_engine defaults**. We do NOT pass `risk_level` into the internal path (it is silently dropped there today) and we do NOT call `_apply_risk_level` (it mutates the agent-GLOBAL `risk_limits` row, clobbering the user's manual SL/TP preset). The "applies SL/TP exit profile" claim is deleted.
- `_compose_run_config` **explicitly pins `stop_flatten=True`** for every fleet member (QA: it is a required parameter of the internal `create_run` — the API-route default does not apply on the builder path; without it, retired members hold positions and wedge their slots).
- **Per-candidate abort checks** (QA: a hold/stop landing mid-build must not keep creating runs): the same start transaction that rechecks exclusivity also re-reads `fleets.status` and `users.ai_automation_state` — either changed ⇒ abort remaining candidates, journal `build_aborted:master` (or `:fleet_stopped`). Named test: hold lands after candidate 2 of 5 ⇒ exactly 2 runs exist, both then held.
- `StartConflict` ⇒ delete the just-created draft, journal `candidate_skipped`, next candidate (handler scoped to `start_run` only). `EntitlementDenied` ⇒ **delete the in-flight draft** (QA: it leaked), then partial-finish. Unpriceable ⇒ skip. Conflicts are never auto-resolved — `resolve_start_conflicts` stays a human-consent UI action.
- Partial build ≥1 run ⇒ `active` with `status_reason='partial:k/N'`; zero ⇒ `stopped('build_failed')` + notification.
- **Entitlement headroom race fix (QA major):** `check_run_start`'s count-then-insert is unserialized on MySQL (plain BEGIN, REPEATABLE READ, disjoint rows — both concurrent starts pass at limit−1). Fix inside `start_run`'s transaction: acquire a per-user serialization point (`SELECT … FROM users WHERE id=? FOR UPDATE`, or `GET_LOCK('run_start:{user_id}')`; no-op on SQLite where BEGIN IMMEDIATE already serializes) before the COUNT. Dual-dialect test fires two concurrent starts at limit−1 against the MySQL container; exactly one succeeds.

### 6.5 Supervision (`_do_supervise`, zero LLM, every tick)

**Coverage rule (QA: hold created a supervised-money gap; round-5 fixed the scope):** the supervise pass — rails, watchdog, slot bookkeeping, replenishment — runs for **every NON-TERMINAL FLEET, regardless of fleet status (active, paused, warned, held) and regardless of whether any member is currently live** — a fleet whose members have ALL stopped must still replenish (perpetual N) and still be supervised. The "members with money deployed" condition qualifies only what the rails have to protect, never whether supervise runs. Named test: fleet paused (and account held) with open positions crossing −40% ⇒ stop-all flatten + SMS still fire; fleet with zero live members ⇒ replenishment still retried every tick.

1. **Fleet drawdown rails — two-tier on marked equity (§6.3.0), fail-closed (QA criticals + Henry directive 2026-07-20):**
   - **Evaluation order: Tier 2 FIRST.** A gap through both thresholds in one tick produces exactly one stop-all and one SMS; the warning tier is skipped. Property test: any equity path ending ≤ −40% ⇒ exactly one stop-all, regardless of whether −30% was ever observed.
   - **Tier 2 — STOP-ALL at marked equity −40%:** `request_stop(flatten=True)` on every member, fleet → `stopping` → `stopped('breaker')`, SMS + email + in-app. Not resumable; a new fleet requires a fresh launch. Honest wording everywhere (incl. SMS copy): the rail fires at the *first tick observing* ≥40% loss — inter-tick overshoot is possible.
   - **Tier 1 — WARNING at marked equity −30%, episode-latched:** fires on **crossing** while the latch is clear; stamps `warn_latched_at` + `warn_level_frac`. Effects: every running member is paused with `paused_reason='drawdown_warning'` (this is the actual entry-block mechanism — fleet status alone blocks nothing; per-run stops and the SL/TP watcher keep evaluating on paused runs, which the engine already guarantees: "pause blocks entries, not stops"), replacements are suspended (§6.3.3), and `fleets.entry_paused_reason='drawdown_warning'` is set — a **separate column**, so it cannot collide with `replenishing:k/N` / `partial:k/N` in `status_reason`.
   - **User resume = acknowledgment** (`POST /resume-warning`): stamps `warn_acked_at`, **un-pauses ONLY members with `paused_reason='drawdown_warning'`** (marker-disciplined exactly like §6.7 — a user-paused member stays paused; a master-held member's marker is untouched), re-enables replacements — and **sticks**: the latch stays consumed while equity remains in the acknowledged band. Re-arm rules, keyed to `warn_level_frac` = **the level of the last warning sent** (stamped at fire AND at ack — legs work the same whether or not the user has acked): (a) equity recovers above `warn_loss_frac − 5pp` (i.e. −25%) ⇒ latch clears, a future re-crossing warns again; (b) each additional −5pp leg below `warn_level_frac` ⇒ one fresh warning + SMS, re-pause (−35%; **any leg at or beyond `stop_loss_frac` is the Tier-2 stop, not a warning**). Dedupe key = fleet_id + `warn_episode` (a real column, §8 — incremented at each latch), NOT the raw 1h window (which would both spam hourly and swallow a genuine second leg). Named tests: resume at −32% sticks across ticks; oscillation across −30% ⇒ no SMS storm; −35% after an acked −30% ⇒ exactly one new SMS; unacked slide −30%→−35% ⇒ exactly one additional SMS; user-paused member + resume-warning ⇒ stays paused; master-held member + resume-warning ⇒ marker intact.
   - **Rails-edit interactions (round-5 — the PUT is live during a drawdown):** (a) a `PUT /rails` whose new `stop_loss_frac` ≤ the current drawdown returns **409 with a localized "this would stop the fleet immediately" message unless `confirm:true` is passed**, in which case the stop-all executes and is journaled as user-initiated; (b) any `warn_loss_frac` change **rebases the episode latch** — latch cleared, `warn_level_frac` recomputed against the new threshold — so a tightened warning can actually fire. Both in the Phase 4 latch test list.
   - **Warning under master hold (round-5 interleaving):** if Tier 1 latches while the account is held (members carry `master_hold`, none are running), the latch and `entry_paused_reason` stamp anyway; **master resume then converts those members' markers `master_hold` → `drawdown_warning` instead of un-pausing them**, and the resume response/UI states the fleet still needs `/resume-warning`. Named test: hold → equity crosses −30% → master resume ⇒ zero entries until resume-warning.
   - **The SMS says what the user is accepting:** the warning body states positions remain open, stops remain active, and continuing is the user's responsibility.
   - Thresholds are per-fleet columns (`warn_loss_frac` 0.30, `stop_loss_frac` 0.40), user-**tightenable only** (never raised once active; stop tier hard-clamped ≤ 0.40), edited via `PUT /api/fleets/{id}/rails` (§9.1).
   - **Reserved alert budget (QA: the mandatory SMS could be starved):** new kinds `fleet_drawdown_warning` / `fleet_breaker` are added to `ALERT_KINDS` with their **own reserved hourly budget** (the `RUN_STOPPED_RESERVE` pattern, 2/h) — informational fleet alerts (churn, watchdog, `slot_dormant`, `sms_unavailable`) stay in the shared 10/h bucket. Named test: 10 filler external sends this hour ⇒ the −40% SMS still goes out.
   - Any member with an open position and `mark_age_ok=False` ⇒ the rail evaluation is a **FAILURE** (journal `breaker_eval_failed` + alert); K consecutive failures ⇒ pause fleet-wide entries. Named tests: one stale member; all stale; rotated-out losers counted; −40% flattens.
   - SMS reality: Twilio must be live and the user phone-verified — fallback is email + in-app, journaled `sms_unavailable` (never silent). **The email leg is SendGrid** (`alerts.py`), a separate integration from Resend — Phase 6 verifies BOTH keys, not just Twilio.
2. **Member stopped → replacement per the §2 per-reason table** (enumerated list, incl. `price_cross`; §6.5.2 cites the table, never a wildcard). Journal with final P&L. Immediate-replacement reasons replace **on the first supervise pass after the member is terminal AND holds no open position** — concretely: the flatten leg is present *when one was needed* (a clean stop with nothing open produces no flatten leg and is immediately eligible; round-5 caught the two-branch wording wedging exactly this common case). The one occupied-slot exception: `stopped('positions_held')` — the slot stays **occupied**, symbol excluded, its zombie basis tracked by the §6.3.0 replay+fresh-mark mechanism (counted in marked equity AND subtracted from headroom), replacement-eligible only when the unowned book returns to the recorded pre-existing quantity. Deferred/never reasons per §2. Replacement via `select_targets(exclude=non-terminal member symbols ∪ cooldowns)`, budget per §6.3.3, suspended while the warn latch is unacked or the fleet is paused/held. Count-uncapped; churn **alert** >8/day/user (informational).
3. **The fleet never auto-stops for lack of members.** Slots waiting or dormant (no candidates, cooldowns, stale batch, drawdown suspension, no fundable headroom) ⇒ fleet stays `active` with `status_reason='replenishing:k/N'`, retried every tick — dormancy re-evaluates per §6.3.0 and is never sticky. The ONLY automatic terminals: **(a)** the −40% rail (`stopped('breaker')`); **(b)** `stopped('agent_deleted')`. The round-4 `equity_floor` terminal is **deleted** — round 5 proved the redefinition was still dominated by the −40% rail (all-dormant with zero active members ⇒ equity < B/2N ≤ 0.5B < 0.6B), the identical arithmetic bug. A fleet that cannot fund any slot simply idles in `replenishing:0/N` until equity recovers, the rail fires, or the user stops it. Everything else waits for the user's Stop or the master switch.
4. **No auto-restart for members (QA critical):** `run_engine._maybe_auto_restart` gets a guard — runs with `fleet_id` (or `created_via='fleet'`) are never cloned. Test: fleet member stopped on `profit_target` produces no clone. Rotation is the ONLY replacement mechanism; the invisible-clone + rotation double-deploy is closed.
5. **Kill-switch semantics + watchdog (QA major):** `FLEET_ENABLED=off` refuses new fleet builds but **keeps the supervise pass running** for fleets with non-terminal members (the breaker never goes dark while money is deployed). A supervision watchdog fires `alerts.send_alert` if an active fleet's last supervise tick is older than 3× `FLEET_TICK_INTERVAL`. Test: active fleet + dead fleet loop ⇒ alert, member stops still enforced by the run loop.

### 6.6 Feedback-state write fencing (QA major)

`run_feedback.save_state`'s UPDATE carries the same fence as trades: `WHERE id=? AND claimed_by=<worker> AND claim_expires_at >= now` (FOR UPDATE read on MySQL, matching `_fence`); 0 rows ⇒ lease lost ⇒ discard adaptation, skip trade. A zombie claimant can no longer roll `last_processed_signal_id` backwards and double-apply ladder steps. Test simulates the reclaim interleaving.

### 6.7 User-level AI-automation master control (Henry directive 2026-07-20)

One account-wide switch covering **everything AI-automated the user owns, across every agent linked to their user id**: the fleet, all trading runs (fleet-created AND manual), and all enabled `automation_configs` rules.

- `hold` — reversible pause, **marker-stamped** (QA: without markers, resume cannot distinguish master-held from user-paused): **RUNNING** runs → paused with `paused_reason='master_hold'`. **Armed runs stay `armed`** (round-5: armed→paused is an illegal engine transition, and widening it would let resume bypass the start condition) — they are blocked by the `_control_armed` account-held guard, and **their armed-timeout clock is suspended while held** (otherwise a long hold silently expires them, breaking "reversible"). Note the internal API gap (round-5): `pause_run`'s `reason` parameter writes `status_reason`, not `paused_reason` — the pause path is extended to write `paused_reason` via `extra_sets` (the engine's own `stop_eval_failed` precedent), and resume clears it; a test asserts the marker lands in `paused_reason` specifically. Fleet: held-marker in its own field; `status_reason` (e.g. a live `partial:3/5`) is untouched and recomputed by the next supervise pass after resume. Automation rules: `enabled=0` + `held_by_master=1`. Objects the user had already paused/disabled keep their own reasons and are untouched by resume.
- `resume` — restores **only marker-carrying objects**; the fleet resumes replenishment (unless the drawdown-warning latch is active — that requires its own resume, and warn-latched fleets' members convert `master_hold` → `drawdown_warning` instead of waking, §6.5.1).
- `remove` — the hard action: `request_stop(flatten=True)` on every run, fleet → `stopping`→`stopped('user_master_remove')`, all automation rules disabled (rows kept — the journal is the user's audit trail; hard row deletion stays on the existing per-object DELETE endpoints). Confirmation modal required; not reversible.
- Auth & hosting: **user session** (not agent bearer), endpoints in `routes_automation.py` using the same user-session dependency as the subscription routes; fans out over `agents WHERE user_id = ?` synchronously in the route. Fan-out rule (stated inline — there is NO existing "pause-all" precedent in the repo, an earlier draft cited a phantom): iterate objects, apply the transition where legal, return `{object_id: ok|already_stopping|error}` per object without failing the request.
- Journaled per object + one `master_control` event; in-app + email notification summarizing what was held/removed — **including the line that protective exits (SL/TP watcher) stay active and any cycle already executing completes without opening new positions**. The SL/TP watcher is deliberately NOT disabled by `hold` (exits reduce risk — house convention), and this is disclosed in the UI banner and confirmation modal in all 5 languages, not just here.
- Master state is stored per user (`users.ai_automation_state`: `active|held` + timestamp) and enforced at **three depths** (QA: cycle-entry alone leaks): (1) zero-cost pre-gate at cycle/rule entry in `run_cycle`, the fleet loop, and `automation.run_rule`; (2) **re-checked immediately before the trade write** inside the same gate that sizes the order — a hold landing mid-cycle turns the in-flight cycle into a journaled no-trade skip; (3) `_control_armed` will not start armed runs and `_maybe_auto_restart` will not clone stops while the account is held. Tests: hold + manually re-enable one rule ⇒ no trade; hold between pre-gate and trade write ⇒ no trade; armed run under hold does not start; a held manual run stopping on profit_target produces no restart clone.

---

## 7. Step-trading feedback loop (`run_feedback.py`)

Runs at the **start** of every claimed cycle, before pre-gates, before any LLM.

- **Outcome unit** = each closing leg (sell/cover) net of fees, from `compute_run_pnl(per_leg=True)` (extends the existing replay; captures SL/TP-watcher and flatten closes that happen outside cycles; avoids the entry-fee misclassification of naive deltas). Scratch trades count as losses — at 0.1%/leg, churn IS the failure mode.
- **Anti-martingale by construction**: `size_mult` ladder (0.25, 0.5, 0.75, 1.0), 1.0 a HARD ceiling; losses step down only, wins restore ≤1 rung. `effective_size = clamp(max_bet × size_mult, $10, max_bet)` — and now also capped by run-budget headroom (§6.3.2). Property test over all W/L sequences + mandatory mutation (step-up-on-loss must fail the suite). No run-level Kelly/vol-targeting — `risk_engine` already does ½-Kelly and vol sizing downstream; two independent shrink-only layers.
- Losses also: `conf_bump += 0.05` (cap 0.15), cooldown cycles (skip = zero LLM), 30-min same-direction re-entry block (whipsaw/fee-churn guard).
- Drawdown brake: peak−current ≥ 70% of `max_loss_usd` ⇒ retire; ≥35% ⇒ force `size_mult ≤ 0.5`. Intra-position tighten at open loss ≥ 50% of max_bet (covers long-horizon runs with zero closes).
- **Thesis drift** (deterministic): after ≥50% of horizon, drift = signed_move / expected_move; < −0.5 ⇒ one synthetic loss (never retirement alone). Skips on stale marks (`mark_age_ok` fail-closed) — named test.
- **Thesis review** (the only LLM): fires every 3 closes, ≥6h apart, ≤4/day/run — and **`thesis_review` events now count into `llm_ticks_exhausted`** (the event-type filter widens; QA: it gated on the budget without drawing it down). Verdict is monotone-tightening: weakened ⇒ one rung; invalidated ∧ P&L ≤ 0 ⇒ retire (a profitable run with a "broken" thesis only tightens — stopping a winner on LLM say-so violates proposes/disposes). Throttle has a named test (counting stub on `generate_text` across a simulated day).
- **Retirement**: 3 consecutive losing closes, drawdown brake, or invalidated∧losing ⇒ `stopping` with protective reason `adapt_retired` (NOT in `_RESTARTABLE_STOP_REASONS`), honoring `stop_flatten`; writes a `fleet_symbol_cooldowns` row (24h) **in the same transaction** as the adapt event — the rotation path and `select_targets` both read the table (the phantom-table QA finding is closed; test: retire → rotate → same symbol not selectable within window).
- State = one `trading_runs.adapt_state_json` MEDIUMTEXT (validated; corrupt ⇒ reset to conservative 0.5 multiplier + journal). Writes are lease-fenced (§6.6). Every adaptation journals via `_emit_event` inside the state transaction (money-adjacent convention).
- Fleet learning v1 is event-mediated only (cooldown rows + read-only adapt stats); sibling state coupling deferred.
- `RUN_FEEDBACK_ENABLED` default **true for fleet-created runs only** (flag in `config_snapshot_json`); existing manual runs unchanged on deploy.
- **Scope note surfaced to Henry (QA minor):** v1 feeds results into the next step **deterministically** (size/confidence/cooldown/retire). The decision-LLM seeing its own record (`RUN_FEEDBACK_CONTEXT_ENABLED` performance block) ships default-OFF pending A/B observation — see Q3.

---

## 8. Schema & migrations (one combined revision)

Revision number assigned **at merge time** off the then-current head (0027 today; the market-expansion branch lands first; the deploy checklist includes `alembic heads` shows exactly one head). MySQL DDL in alembic + SQLite mirror in `init_database()` (the 0022 convention: `INT NOT NULL AUTO_INCREMENT PRIMARY KEY`, VARCHAR for indexed cols, `NUMERIC(20,8)` money, ISO-8601 VARCHAR timestamps, dup-tolerant ALTERs).

```sql
CREATE TABLE fleets (
  id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  agent_id INTEGER NOT NULL,
  name VARCHAR(80), status VARCHAR(16) NOT NULL DEFAULT 'draft', status_reason VARCHAR(255),
  active_fleet_key VARCHAR(64) NULL,            -- 'user:{user_id}' while non-terminal; UNIQUE (one fleet per USER)
  idempotency_key VARCHAR(64) NULL,
  n_runs INTEGER NOT NULL, total_budget_usd NUMERIC(20,8) NOT NULL,
  risk_appetite VARCHAR(12) NOT NULL DEFAULT 'balanced',
  market_scope_json MEDIUMTEXT,
  warn_loss_frac NUMERIC(20,8) NOT NULL DEFAULT 0.30,   -- tier-1 rail (marked equity)
  stop_loss_frac NUMERIC(20,8) NOT NULL DEFAULT 0.40,   -- tier-2 rail (hard-clamped ≤ 0.40)
  warn_latched_at VARCHAR(32) NULL,             -- §6.5.1 episode latch
  warn_acked_at VARCHAR(32) NULL,               -- user resume = acknowledgment
  warn_level_frac NUMERIC(20,8) NULL,           -- level of the LAST warning sent (stamped at fire AND ack); −5pp legs key off it
  warn_episode INTEGER NOT NULL DEFAULT 0,      -- incremented at each latch; the alert dedupe key (fleet_id + warn_episode)
  entry_paused_reason VARCHAR(24) NULL,         -- 'drawdown_warning' — separate from status_reason (no collision)
  held_by_master INTEGER NOT NULL DEFAULT 0,    -- §6.7 hold marker — its own field, status_reason untouched
  rotation_enabled INTEGER NOT NULL DEFAULT 1,
  build_attempts INTEGER NOT NULL DEFAULT 0, last_event_seq INTEGER NOT NULL DEFAULT 0,
  provider VARCHAR(16), lang VARCHAR(8) NOT NULL DEFAULT 'en',
  claimed_by VARCHAR(64), claim_expires_at VARCHAR(32),
  last_supervise_at VARCHAR(32),                -- watchdog input
  created_at VARCHAR(32) NOT NULL, started_at VARCHAR(32), stopped_at VARCHAR(32),
  UNIQUE KEY uq_fleets_active (active_fleet_key),
  INDEX idx_fleets_agent (agent_id, status), FOREIGN KEY (agent_id) REFERENCES agents(id)
);
CREATE TABLE fleet_events (  -- append-only, run_events shape, seq from fleets.last_event_seq
  id INT NOT NULL AUTO_INCREMENT PRIMARY KEY, fleet_id INTEGER NOT NULL, seq INTEGER NOT NULL,
  ts VARCHAR(32) NOT NULL, event_type VARCHAR(32) NOT NULL, payload MEDIUMTEXT,
  UNIQUE KEY uq_fleet_events (fleet_id, seq), FOREIGN KEY (fleet_id) REFERENCES fleets(id)
);
CREATE TABLE fleet_slots (  -- §6.3.0: persistent slot identity for perpetual-N refund accounting
  id INT NOT NULL AUTO_INCREMENT PRIMARY KEY, fleet_id INTEGER NOT NULL,
  slot_index INTEGER NOT NULL,
  original_allocation_usd NUMERIC(20,8) NOT NULL,   -- immutable after build; the refund cap
  state VARCHAR(12) NOT NULL DEFAULT 'active',      -- active | waiting | dormant | closed (§6.3.0; dormant re-evaluates every tick)
  zombie_baseline_qty NUMERIC(28,10) NULL,          -- positions_held: pre-existing unowned qty recorded at transition (§6.3.0)
  current_run_id INTEGER NULL, updated_at VARCHAR(32) NOT NULL,
  UNIQUE KEY uq_fleet_slots (fleet_id, slot_index), FOREIGN KEY (fleet_id) REFERENCES fleets(id)
);
CREATE TABLE fleet_candidates (  -- per-fleet selection journal (no LLM of its own)
  id INT NOT NULL AUTO_INCREMENT PRIMARY KEY, fleet_id INTEGER NOT NULL,
  thesis_key VARCHAR(80) NOT NULL,             -- batch_id:market:symbol — allocation consumed by key
  slot_index INTEGER NULL,                     -- replacements inherit the retired member's slot
  allocation_usd NUMERIC(20,8), state VARCHAR(16) NOT NULL DEFAULT 'selected',
      -- selected | skipped | built | rotated_in | rotated_out
  run_id INTEGER NULL, created_at VARCHAR(32) NOT NULL,
  INDEX idx_fleet_candidates (fleet_id), FOREIGN KEY (fleet_id) REFERENCES fleets(id)
);
CREATE TABLE research_batches (  -- §4.3 dedupe sentinel: deterministic batch_id, inserted BEFORE any LLM call
  batch_id VARCHAR(48) NOT NULL PRIMARY KEY, created_at VARCHAR(32) NOT NULL
);
CREATE TABLE fleet_symbol_cooldowns (
  id INT NOT NULL AUTO_INCREMENT PRIMARY KEY, agent_id INTEGER NOT NULL,
  market VARCHAR(16) NOT NULL, symbol VARCHAR(20) NOT NULL,
  until_ts VARCHAR(32) NOT NULL, source_run_id INTEGER,
  INDEX idx_symbol_cooldowns (agent_id, market, symbol)
);
CREATE TABLE research_theses (  -- global batches; QA-corrected dual-dialect DDL
  id INT NOT NULL AUTO_INCREMENT PRIMARY KEY, batch_id VARCHAR(48) NOT NULL,
  market VARCHAR(16) NOT NULL, symbol VARCHAR(20) NOT NULL,
  market_type VARCHAR(10) NOT NULL DEFAULT 'spot', direction VARCHAR(8) NOT NULL,
  factor_scores_json MEDIUMTEXT NOT NULL, thesis TEXT, risks TEXT, invalidation TEXT,
  expected_move_pct NUMERIC(20,8), horizon_hours NUMERIC(20,8), confidence NUMERIC(20,8),
  ev_per_day_pct NUMERIC(20,8), final_score NUMERIC(20,8),
  selectable INTEGER NOT NULL DEFAULT 1, planner VARCHAR(16) NOT NULL, llm_model VARCHAR(64),
  created_at VARCHAR(32) NOT NULL, expires_at VARCHAR(32) NOT NULL,
  UNIQUE KEY uq_research_batch_symbol (batch_id, market, symbol),
  INDEX idx_research_batch (batch_id), INDEX idx_research_symbol (market, symbol, created_at)
);
ALTER TABLE trading_runs ADD COLUMN fleet_id INTEGER NULL;         -- no FK, by design
ALTER TABLE trading_runs ADD COLUMN created_via VARCHAR(16) NOT NULL DEFAULT 'user';
ALTER TABLE trading_runs ADD COLUMN adapt_state_json MEDIUMTEXT NULL;
ALTER TABLE users ADD COLUMN ai_automation_state VARCHAR(12) NOT NULL DEFAULT 'active';  -- active|held (§6.7)
ALTER TABLE users ADD COLUMN ai_automation_held_at VARCHAR(32) NULL;
ALTER TABLE automation_configs ADD COLUMN held_by_master INTEGER NOT NULL DEFAULT 0;
CREATE INDEX idx_trading_runs_fleet ON trading_runs (fleet_id);
```

Prune `research_theses` with the two-step-cutoff pattern (MySQL rejects LIMIT-in-IN-subquery).

**FK cascade (QA major — prod MySQL would 500):** `DELETE /api/fleets/{id}` (draft/stopped only) deletes `fleet_events` + `fleet_candidates` + `fleet_slots` in-transaction and NULLs members' `fleet_id`. **And** `routes_admin._delete_agent_cascade` is extended: `fleet_events`/`fleet_candidates`/`fleet_slots` via fleet_id subquery → `fleet_symbol_cooldowns` → `fleets`, before the agents delete. MySQL-shape test asserts agent-delete leaves no orphans.

**Alert kinds:** `ALERT_KINDS`/`ALERT_KIND_CATEGORY` gain `fleet_drawdown_warning`, `fleet_breaker` (reserved budget — §6.5.1) and `fleet_churn`, `fleet_watchdog`, `fleet_slot_dormant`, `fleet_sms_unavailable` (shared budget) — `send_alert` coerces unknown kinds to `custom`, so omitting any of these silently declassifies it.

---

## 9. API, entitlements, frontend

### 9.1 API surface (i18n via boundary translation — raise sites stay English, ~12 new exact messages added to `i18n_errors_data.py` in ko/ja/th/vi + `test_i18n_errors.py` rows; there are no "keys")

Fleet endpoints live in `routes_fleets.py` (**agent bearer auth**, cross-tenant 404); the master endpoints live in `routes_automation.py` (**user-session auth** — the same session dependency the subscription routes use).

```
POST   /api/fleets            {n_runs, total_budget_usd?, risk_appetite?, markets?, provider?, lang?,
                               warn_loss_frac?, stop_loss_frac?, idempotency_key?}
PUT    /api/fleets/{id}       draft-only full replacement (same field set)
PUT    /api/fleets/{id}/rails {warn_loss_frac?, stop_loss_frac?, confirm?} — TIGHTEN-ONLY while non-terminal
                              (mirrors the runs stop-conditions endpoint). Validation in ONE place:
                              0 < warn < stop ≤ 0.40; once active, new values ≤ current. Loosen ⇒ 400 (localized).
                              new stop ≤ current drawdown ⇒ 409 "would stop the fleet now" unless confirm:true (§6.5.1);
                              warn change rebases the episode latch (§6.5.1).
POST   /api/fleets/{id}/start → researching (async; returns immediately)
POST   /api/fleets/{id}/resume-warning        acknowledges the −30% latch (§6.5.1)
GET    /api/fleets | /api/fleets/{id}          (+members, theses, slots, aggregate P&L; poll target)
POST   /api/fleets/{id}/pause|resume|stop      (stop: {flatten:true default} — THE kill switch)
DELETE /api/fleets/{id}       draft/stopped only, children cleaned in-transaction
GET    /api/fleets/{id}/events                 journal replay (?after_seq=&limit=)
GET    /api/entitlements/me   NEW — tier echo {plan, max_fleet_size, max_concurrent_runs, max_bet_usd}
                              (the N stepper must not learn its cap from a 403)
POST   /api/automation/master {action: hold|resume|remove}   USER-SESSION auth (§6.7);
                              fans out over all linked agents; per-object results in the response
GET    /api/automation/master current state {state, held_at, counts}
```

### 9.2 Entitlements & LLM economics (QA criticals folded)

- `PLAN_LIMITS` + `max_fleet_size`: none 0 / junior 0 / pro 3 / professional 10 / enterprise 25. `check_fleet_create` + the fleet-size gate + the per-user BUILD meter are **always-on** (not behind `enforcement_enabled()`) — fleet LLM spend is a direct cost, the same class as the SMS gate that already bypasses the flag. **Replacement has NO enforced meter** — only the >8/day churn alert (the "rotation meter" vocabulary from the killed daily caps is dead; an enforced limiter would contradict perpetual N). Test runs with enforcement on AND off.
- **Prod precondition (QA critical): `ENTITLEMENTS_ENFORCED=1` must be set on prod before `FLEET_ENABLED=1`** — QA verified prod currently runs `ENTITLEMENTS_ENFORCED=false`, which would otherwise hand any `claw_` token an unmetered 25-run fleet. PLAN_LIMITS numbers confirmed by Henry first (Q2).
- Builds metered **per owning user per day**; replacements are count-uncapped (perpetual N, Henry directive) but tracked per user with a churn **alert** at >8/day (fleet_events joined through `agents.user_id`, the `llm_ticks_exhausted` query shape). Replacement selection and create/start/stop/delete churn trigger **zero research LLM** (research is global). One fleet per user (§6.2) removes the many-small-fleets multiplier.
- **Honest cost math (QA: prior math was ~6× off).** A run cycle ≈ 6 LLM calls (4 analyst briefs + trader/risk debate + verify — verified in `analysis_agents.py`), not 1. Worst cases at the old tick caps are cost-negative vs subscription prices. Chosen levers:
  1. **Fleet members default to a light cycle profile** — `FLEET_CYCLE_MODE=light`: one decision-tier call/cycle (agent_planner-style) instead of the 6-call pipeline; full pipeline opt-in per run for professional+. **Light mode swaps ONLY the analysis stage inside `run_cycle`** — pre-gates, `evaluate_execution_gates`, the run-budget cap, and the trade fence are byte-identical (round-5: a separate lightweight cycle function would bypass the budget cap in the default mode for all fleet members). Professional N=10 @60min ⇒ ~240 calls/day ≈ $2.4–7.2/day — viable against $500/mo.
  2. `daily_llm_ticks` placeholder caps lowered so the cap actually binds below fleet worst cases (pro 150 / professional 400 / enterprise 2,000 — Henry confirms, Q2).
  3. Interval defaults stable 240m / balanced 60m / aggressive 30m; floors us-stock 30m (Yahoo constraints — the AV-starvation rationale was stale, QA-corrected), others 15m.
  4. Before defaults ship: measure real per-cycle tokens from prod `llm_usage`.
- Research + adaptation accounting stance (one sentence, no ambiguity): global research = platform OpEx bounded by `FLEET_RESEARCH_MAX_LLM_CALLS`; thesis reviews = counted into `llm_ticks_exhausted`; run cycles = tick-capped per tier.

### 9.3 Frontend (`AutomationPage.tsx` + `RunsLivePage.tsx`)

- **"② Full Auto" chip** appended after ⓪ Agent ① Simple. Panel: **one N stepper** (cap from `/api/entitlements/me`) + Launch CTA. Budget **pre-filled** from tier default (editable), risk appetite + market scope behind an "Advanced" disclosure. Korean naming differentiated from Agent mode's 완전 위임: Agent = "1종목 위임", Full Auto = **"N종목 자동 편성"** (Q1 confirms final copy).
- Progress card while researching/building (2s poll): "Researching → Ranked 12 → Building 3/5 → Active", candidate-skip info lines. **Partial build renders as "Built 3 of 5 — 2 skipped (reasons)"** with a retry affordance disabled while the research batch is unchanged (retries cannot burn LLM).
- FleetCard (active, 15s poll): aggregate P&L, member mini-rows → RunsLivePage links, rotation timeline, **⏹ Stop all (flatten)** + Pause.
- **Client-side `reasonLabel` map** (the RunsLivePage pattern) for every fleet `status_reason` and the new `adapt_retired` run reason, 5 languages — async failures can NEVER surface through `i18n_errors` (no request in flight; QA killed that route).
- **New deliverable (QA: it doesn't exist):** a run **event-log timeline** in RunsLivePage `RunDetail` rendering `adapt` / `thesis_review` / `gate_skip` / status events with localized labels + an adaptation badge (current size_mult, effective confidence). Sized into Phase 5, not assumed.
- **Localization of research rationale (QA: "English-only matches convention" was false — the pipeline localizes today):** factor reasons ship as **machine codes + numeric params** rendered client-side via `tr()` (localizes factor chips for free); thesis prose is generated per-language **on read** for the requesting user's lang (1 cheap call, cached per thesis+lang) **(pending Q6 — Henry may choose English-prose-only)**. Run-level LLM prose already follows `cfg.lang` unchanged.
- Fleet member badge on RunsLivePage; alert strings for `adapt_retired` ship English (existing `_alert_run` machinery is English-only — scoped honestly, not claimed as i18n'd). The −30%/−40% SMS bodies are new copy: short, factual, with the "your responsibility from here" line for the warning tier — 5-language versions via the run-reports `lang` pattern.
- **Master control UI:** a persistent switch in the AutomationPage header (visible in every mode): "AI 자동매매 전체 일시정지 / 해제 / 전체 제거". `remove` requires a typed confirmation. State from `GET /api/automation/master`; while held, every automation card renders a "held by master switch" banner. **The banner and the hold confirmation modal disclose, in all 5 languages: protective exits (stop-loss/take-profit) remain active while held, and any trade cycle already executing completes without opening new positions** (QA: undisclosed watcher activity reads as a broken hold).
- **Drawdown-warning UI:** the FleetCard shows the −30% warned state with the acked level and a "Resume trading (your responsibility)" button wired to `/resume-warning`; the −40% stop renders as terminal with the final equity figure.

---

## 10. Phased build plan (falsifiable gate per phase; ≥2 verification passes + mutation discipline per house rules)

**Phase 0 — Preconditions.** Market-expansion (Plan 13) merges first; `alembic heads` = 1; this doc is the single spec (parallel sessions: check `docs/plan/14-*` before building).

**Phase 1 — Data + research skeleton.** `get_daily_candles` (+cooldown-subordination + jittered TTL), `policy_feed.py`, CNN F&G fetcher, news cadence → 4h, macro tone via Yahoo. `symbol_research.py` Stage 0+1 (universe, gates, factors, composite) + **the combined migration = ALL §8 DDL in one revision** (fleets incl. rails/latch columns, fleet_events, fleet_slots, fleet_candidates, fleet_symbol_cooldowns, research_theses, research_batches, trading_runs columns, `users.ai_automation_state`/`held_at`, `automation_configs.held_by_master`) + loop registered dark.
*Gate:* pure-function tests on synthetic fixtures; snapshot age-gate test; no-network scoring test; cooldown-path test (zero HTTP under active cooldown); **mutations: weight-sign flip, None-as-0, dropped veto — all must fail.** Live provider smokes are a manual pre-deploy checklist, NOT CI gates.

**Phase 2 — Thesis stage + selection.** Batched LLM call + THESIS_BOUNDS + fallback + reuse-on-unchanged; `research_theses` persistence + Redis-lock/UNIQUE(batch_id) refresh guard; `select_targets` with exclusivity/cooldown/diversity.
*Gate:* clamp property tests (garbage LLM in-bounds out); parse-failure→fallback; batch-dedupe under simulated dual runners **with Redis absent (sentinel-only path — the entire point of the fix)**. (The profit-target /100 unit test moved to Phase 3 where `_compose_run_config` exists.)

**Phase 3 — Fleet build + budget enforcement.** Fleet tables now exercised (DDL landed in Phase 1); `fleet_planner` claim/build; `active_fleet_key` (per-user) + idempotency; allocation-by-key journal + slot binding; per-candidate FOR-UPDATE recheck incl. master/fleet-status abort; per-user start serialization; `run_budget_usd` execution cap in `run_cycle`; **`FLEET_CYCLE_MODE=light` — the one-call decision path the §9.2 economics depend on** (QA: it was in no phase; without it the cost model reverts to cost-negative); `_maybe_auto_restart` fleet guard; admin cascade extension.
*Gate:* double-POST ⇒ 1 fleet (per user, across two agents of the same user); crash-after-k + mutated conflict set resume ⇒ Σ active budgets ≤ B; concurrent-starts-at-limit−1 MySQL test; unit test — thesis 2.0% on $1,000 ⇒ profit_target ≈ $20 (**mutation: drop the /100, must fail** — moved from Phase 2, `_compose_run_config` lives here); profit-target stop ⇒ no clone; EntitlementDenied ⇒ no orphan draft; agent-delete ⇒ no FK 500; **light-mode tests: exactly one `generate_text` call (counting stub), `decision` event still fires, AND a light-mode cycle whose open basis exhausts `run_budget_usd` emits `budget_headroom_skip` with no trade (proves the gate/budget/fence path is shared)**. (Replacement/rail property tests live in Phase 4, where that machinery exists.)

**Phase 4 — Feedback + supervision.** `run_feedback.py` (per-leg ingestion, ladder, cooldowns, drift, review, retire) with fenced saves; cooldown table writes; two-tier drawdown rails per §6.5.1 (marked equity, Tier-2-first, episode latch, member-pause mechanism, reserved alert kinds in `ALERT_KINDS`) + watchdog + per-reason replacement table + slot lifecycle.
*Gate:* anti-martingale property + mutation; fence-interleaving test; **rails:** Tier-2-first gap test (path ending ≤ −40% ⇒ exactly one stop-all); latch tests (resume at −32% sticks; oscillation ⇒ no SMS storm; −35% after acked −30% ⇒ one fresh SMS; unacked −30%→−35% ⇒ one fresh SMS; recovery above −25% re-arms; **rails-edit: tighten stop below current drawdown ⇒ 409 without confirm, executes with confirm; warn change rebases the latch and the tightened warning fires**); resume-warning marker discipline (user-paused member stays paused; master-held marker intact); hold→warn→master-resume ⇒ zero entries until resume-warning; member paused at warning still fires its max_loss stop; rails fire for paused AND held fleets with open positions AND replenishment retried for fleets with zero live members; reserved-bucket test (10 fillers ⇒ −40% SMS still sends); stale-mark tests (one stale / all stale / rotated-out losers counted; **equity-eval failure freezes funding + dormancy that tick, resumes on recovery**); **replacement/slots:** clean stop with no open position ⇒ immediately eligible (no flatten leg needed); `stopped('positions_held')` ⇒ slot occupied, zombie basis reconstructed from signals replay + fresh mark counted in equity AND subtracted from headroom (mutations: drop reconstruction ⇒ rails must fail-stale; drop the headroom Z term ⇒ must fail), no replacement until unowned book ≤ recorded baseline; two slots freed in one tick ⇒ sequential funding from recomputed headroom (mutation: reuse snapshot, must fail); replacement suspended while warn latch unacked (member retires at −31% ⇒ no replacement; resume ⇒ replacement next pass, regardless of level); `stop_eval_failed` ⇒ `slot_waiting`, replaced from next healthy batch only; `synthetic_liquidation` ⇒ cooldown row then replacement after expiry; `price_cross` stop ⇒ immediate replacement; dormant slot with recovered headroom ⇒ back to `waiting` next tick (no sticky dormancy, no `equity_floor` terminal — deleted); **budget:** property test over stop/replacement sequences — Σ active ≤ B, slot refund ≤ original allocation, funding uses marked (not realized) equity — mutations, all must fail; thesis-review throttle counted into ticks (counting stub).

**Phase 5 — API + entitlements + frontend + i18n.** `routes_fleets`, `/api/entitlements/me`, **`/api/automation/master` (§6.7 — user-session auth, fan-out, pre-gate check in run_cycle/fleet loop/run_rule)**, always-on fleet gates, per-user meters; Full Auto panel, FleetCard, master-control switch, event timeline, reasonLabel maps, i18n rows.
*Gate:* `tsc` clean; IDOR/401/400 route tests; enforcement on+off gate tests; **master-control tests: hold ⇒ zero trades even if one rule is manually re-enabled; hold between pre-gate and trade write ⇒ no trade; armed run under hold does not start AND stays status `armed` (never paused — illegal transition); armed-timeout clock suspended during hold (multi-day hold ⇒ armed run survives and starts normally after resume when its condition fires); marker lands in `paused_reason` specifically (not only `status_reason` — the pause path extension); held manual run stopping on profit_target ⇒ no restart clone; hold mid-build ⇒ `build_aborted:master` with exactly k runs, all held; resume restores ONLY marker-carrying objects (a user-paused run stays paused; fleet `status_reason` recomputed, not restored stale); remove flattens everything and survives a member racing into `stopping`; agent-bearer token gets 401 on the master endpoint**; rails endpoint tests (loosen attempt ⇒ 400 localized; tighten while active works); `resume-warning` acknowledges the latch; SMS fallback journaled when Twilio unset; `test_i18n_errors.py` rows; `/qa` end-to-end on local dev (throwaway account), both themes.

**Phase 6 — Prod rollout (sooppiy.com, per deploy memory).** Deploy dark → migration (verify `alembic current`) → worker restart → **pre-smoke steps (QA: the smoke as previously written would 403):** (1) set `ENTITLEMENTS_ENFORCED=1` + confirmed PLAN_LIMITS; (2) grant info@askkpop.com pro+ via admin console; (3) `FLEET_RESEARCH_ENABLED=1`, confirm one `research_theses` batch exists; (4) canary allowlist env (`FLEET_AGENT_ALLOWLIST`) so the flag-flip doesn't expose all users; then 2-run crypto fleet smoke, kill-switch verified on prod, `docker logs` `[FleetPlanner]` ticks, `llm_usage` deltas, restore QA account tier. Frontend dist published to container path AND host nginx `/usr/share/nginx/sooppiy`. `gh run list` for CI. **Notification preconditions:** Twilio creds are historically absent on prod — either configure them before enabling fleets or explicitly accept the fallback for the −30%/−40% rails (journaled `sms_unavailable`); **and verify `SENDGRID_API_KEY` separately** — the rails' email leg is SendGrid (`alerts.py`), NOT the Resend integration, and prod has a history of unconfigured mail. The smoke must confirm one actually-delivered SMS **and** one delivered email for a rail alert (or the explicit journaled fallback), not just `channels_json`. Re-verified 2×.

---

## 11. Open questions for Henry

1. **Input set (requirement d):** you asked for N-only. Money safety wants a budget number. v1 proposal: N stepper + tier-defaulted editable budget + everything else defaulted/Advanced. Confirm, or name the default-budget rule you want (e.g. wallet balance × 50%).
2. **Tier numbers:** max_fleet_size 0/0/3/10/25, lowered tick caps 150/400/2,000, churn-alert threshold 8 replacements/day, light cycle mode default — confirm against subscription pricing ($60/$250/$500). *(Rotation daily cap removed per your 2026-07-20 directive: the fleet always maintains N until you stop it.)*
3. **Feedback depth in v1:** deterministic adaptation ships on; the decision-LLM seeing its own record (`RUN_FEEDBACK_CONTEXT_ENABLED`) ships default-OFF pending A/B. Accept, or want it on from day one?
4. Market scope at launch: all five automatable markets, or crypto + us-stock first week?
5. Shorts: fleets may open short theses where the book supports it (crypto-futures, futures) from day one, or long-only until feedback data accumulates?
6. Research thesis language: on-read per-language generation (1 cached cheap call per thesis+lang) vs English prose + localized factor chips only?
7. Agent-mode positioning: keep 완전 위임 beside N종목 자동 편성 with differentiated copy (v1 does this), or fold Agent mode into Fleet as the N=1 case later?
8. v2 feed funding order: X API paid tier / AV premium / Coinglass / GDELT?
9. **Perpetual-N carve-outs (round-5 surfaced — currently decided by the plan, confirm or override):** (a) when you stop ONE member yourself, the slot is permanently closed (fleet runs below N) — or should it backfill with a *different* symbol? (b) There is now NO automatic equity-floor terminal (both attempted definitions were mathematically dominated by the −40% rail): a fleet that can't fund any slot idles in `replenishing:0/N` until recovery, the −40% rail, or your Stop. Accept?

---

## 12. Verification record

- Round 1: 5 planner agents (symbol-research, signal-parameters, fleet-orchestration, feedback-loop, architecture-rollout), each grounded in code reads + web research.
- Round 2: 9 adversarial QA agents over the merged draft — codebase-feasibility, schema/API, data-feeds/rate-limits, risk-safety, concurrency/exclusivity, LLM-cost/entitlements, UX/product, test-verification, completeness. 70 findings (9 critical / 38 major / 23 minor); prod was inspected over SSH during the audit (entitlements flag state verified live).
- Round 3: arbitration — every critical and major finding folded; the two parallel designs collapsed into one; then three Henry directives grafted in (perpetual N, −30/−40 rails, master control).
- Round 4 (2026-07-20): **4 checking agents re-audited the amended document** (self-consistency, code-truth, adversarial-money, buildability) — 42 findings (2 critical / 20 major / 20 minor), all folded: MTM-equity unification, warning latch/episode semantics, Tier-2-first precedence, per-reason replacement table, per-user fleet key, deterministic research batch sentinel, reserved alert budgets, `FLEET_CYCLE_MODE` scheduled into Phase 3, `fleet_slots` persistence, rails API, master-hold markers + three-depth enforcement, SendGrid precondition.
- Round 5 (2026-07-20): **5 QA agents verified the round-4 fixes** (fix-regression, self-consistency, money-safety, code-truth, buildability) — 37 findings (3 critical / 17 major / 17 minor), all folded. The criticals: `positions_held` zombie accounting rested on a false code premise (the engine clears `positions.run_id` at that terminal — replaced with signals-replay + fresh-mark reconstruction, headroom subtraction, and an unowned-book closure baseline); the round-4 `equity_floor` terminal was itself still unreachable (deleted; the −40% rail + `replenishing` idle state carry it); master-hold "pause armed runs" was an illegal engine transition (armed runs stay armed behind the `_control_armed` guard with the timeout clock suspended). Plus: sequential same-tick funding, equity-eval-failure freeze, rails-edit 409/latch-rebase, resume-path marker discipline, hold→warn→master-resume precedence, `price_cross` classification, clean-stop trigger, HTML companion regressions.
- Standing rule: no phase reports green without its mutation pass, and every gate is re-verified at least twice before "done".
