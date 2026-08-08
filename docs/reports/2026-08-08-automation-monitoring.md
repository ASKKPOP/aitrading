# 2026-08-08 — automation monitoring (newest first)

Day 2 of the reset book (seed 1000, reset 2026-08-06 ~22:56Z). From today the
corpus-read obligation is in force: the desk carries `_recall_line`, and this
session must search `desk_memory` BEFORE proposing any fix and say what it
returned.

---

## 08:43–09:00Z · owner switched the desk to claude-opus-4-8; A/B begins, stamp shipped

Owner changed agent 6's LLM (Settings page) local → **anthropic /
claude-opus-4-8** with their own key, and ordered a **full HTML comparison
report after 24h** (due ~08-09 08:43Z; spec + baseline in the handoff).
Verified the switch works: `llm_context_for_agent(6)` resolves decision →
anthropic claude-opus-4-8, source **user**, live in the running worker —
settings are read fresh per decision, no restart needed. The
`local gpt-oss:120b` usage rows continuing to appear are PLATFORM calls
(user_id NULL, key_source system — hot-issue daemon etc.), which by the
07-31 policy never borrow a user's AI.

Shipped: decision events now stamp `llm: {provider, model, source}` so the
A/B attributes by stamp, not wall clock. Open observation: successful
user-context and research calls never appear in `llm_usage` — metering gap.

**Pre-Opus baseline (34h):** realized net +0.8947, 138 fills, 70W/31L,
avg win +0.0517 / avg loss −0.0774, equity 1001.0182.

---

## 07:42–08:00Z · research loop wedged in a timeout-less LLM call (owner: "just solving now")

Batch 496159 claimed 07:17:28Z, **0 theses after 25+ min** (a refresh takes
~5), research logs silent, FleetPlanner ticking `claimed:1 researched:0`
every minute. Diagnosis, in order:

1. `grep timeout llm_client.py` → **zero matches.** Both SDK clients are
   constructed bare; the SDK defaults are 600s timeout × automatic retries —
   ONE stalled connection blocks its caller up to ~30 min.
2. Live probe of the active provider (anthropic / claude-sonnet-5) answered
   in **5.7s** — the provider is healthy; the loop is sitting inside a
   stalled call from 07:17. (First probe 404'd — used the OpenAI-compatible
   path against an anthropic provider; probe with the provider's OWN path.)

Fix: `_llm_timeout_seconds()` (env `LLM_TIMEOUT_SECONDS`, default 120,
floor 10) + `timeout=…, max_retries=1` on BOTH constructors. A stalled
request becomes a failed attempt the calling loop retries on its own
schedule; #322's stale-reclaim then recovers the burned claim. Existing
fake clients needed `**client_kw` (my change's footprint, updated).
Fail-before ×3, 3694 pass.

**Book:** equity 1000.9318 (+0.093%), 10/10 running, zero tracebacks, nothing
below −0.99. HYPE re-entered legitimately after cooldown expiry (1009; a
first instance 1008 was desk_retired at cycle 1 without trading — the desk
declined, the rebuild shorted).

### Reproduced: `market news inserted=0 errors=4`, twice (22:55Z and 05:42Z)

Corpus searched first (obligation day 1): no direct prior finding. All 4
errors are the Alpha Vantage free-key daily limit — the news sweep spends
**4 AV calls per 6h refresh (16/day) against the SHARED 25/day key**, so
late-day sweeps fail all-or-nothing. Not fully dead (early-day sweeps
succeed) but crypto was 38h stale because the quota died on it every time.
Consumer that matters: `analysis_agents._gather_news` — the AI Analysis
pipeline reasons on these headlines.

### Fix (AI-FIRST split, owner re-affirmed "decisions by sooppiy AI"):

- **Platform half (quota fairness):** refresh ONE category per sweep,
  stalest first — every category inside ~24h deterministically, 12 AV
  calls/day returned to the price fallbacks sharing the key. FMP news was
  considered and rejected: `fmp_feed` is earnings-only and the owner tier
  is thin.
- **AI half (the decision stays the desk's):** the news payload's
  `last_updated_at` now travels into the analysis data as `as_of`, and the
  news brief states "(newest headline snapshot Nh old)" once ≥2h — the
  ANALYST weighs stale headlines, the platform just stops hiding the age.

Fail-before ×3; fixture needed `time_published` (the tidy-fixture trap,
again); 3691 pass.

**Book:** equity **1000.9036 (+0.090%)**. 10/10 running, zero tracebacks,
nothing below −0.99; 1001 ADBE unchanged at −0.6925 (cycle 21). Seven runs
cycled 00:45–00:59 at distinct minutes 46, 47, 53, 54, 56, 57, 58 — the new
runs 1005/1006 hold their own slots. Fresh decisions 00:46Z and 00:53Z
through the balancefix image. 1007 half-covered its ZEC short at 00:39Z at a
small profit (realized −0.0117 → −0.0017) — the ladder engaging on a young
short. HYPEUSDT cooldown expires 01:05:59Z; proposals after that are
legitimate.

---

## Cycle — 00:35Z · the fleet's first SHORTS exposed a session-query trap

**Book:** equity **1000.8941 (+0.089%)**, cross-check to 0.0001
(seed + realized 0.7447 + unrealized 0.1495). 10/10 running.

### ⚠️ My equity query read 975.59 — the missing 25.28 was every short

Stable across 3 reads, so not a sampling race. Cause: my hand-written
monitoring queries filtered `WHERE quantity > 0`, which **silently excludes
short positions** (negative quantity). Runs 1006 BTCUSDT and 1007 ZECUSDT
opened the fleet's first shorts at 00:22–00:23Z; their margin (12.26 + 13.03
= 25.28) was exactly the "missing" cash. **Production is unaffected** —
`POSITION_VALUE_CASE` uses `ABS(quantity)` with no sign filter, and the
frontend fix (#328) uses `Math.abs`. The defect lived only in session
queries, invisible all day because every position until 00:22Z was long.
Rule recorded in the handoff: position queries use `quantity <> 0`, never
`quantity > 0`.

### Fleet rotation — winners banked, re-entered as shorts

997 BTC +0.1252 and 993 ZEC +0.2627 both `desk_retired`; the planner
re-entered both symbols SHORT (1006, 1007) on fresh theses — direction flip
on re-entry is thesis refresh, not churn. 983 ETHUSDT earlier desk_retired
at −0.0104 → rebuilt long as 1005. None of these are `stop_event:` losses,
so the #324 cooldown correctly does not engage.
