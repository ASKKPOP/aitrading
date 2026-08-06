# Sooppiy Automation — 30-min Monitoring Log

Recurring analysis of the live auto-trading fleet on prod (sooppiy.com), every 30 min until **2026-08-01 10:00**.
Data source: prod MySQL (`trading_runs`, `positions`, `automation_runs`) + `sooppiy-worker` stdout over SSH. Snapshot state carried in `automation-snapshot.json`.

Cron job `112644a9` (`13,43 * * * *`). Ground-truth flags on prod image `20260731-tiersplit`:
`AUTO_TRADING_ENABLED=true · RUN_AI_ONLY_ORDERS=true · RUN_AI_ORDER_PARAMS=apply · DECISION_ROUTING_ENABLED=true · LIQ_REFLEX=true · FLEET_ENABLED=true · FLEET_CYCLE_MODE=full`.

---

## Cycle 1 — 2026-07-31 ~08:30Z (baseline)

**Live book:** Fleet 23, 6 running runs, all freshly rotated in ~1h ago (`cycle_seq=4`), each just opened a position on signals 216–219:

| run | symbol | market | side | realized | peak | note |
|-----|--------|--------|------|----------|------|------|
| 852 | USDKRW | spot | — | 0.00 | — | no fill yet |
| 853 | NZDUSD | spot | long | −0.24 | −0.24 | entry friction |
| 854 | HYPEUSDT | futures | short | −0.44 | −0.44 | entry friction |
| 856 | BTCUSDT | futures | short | −0.47 | −0.47 | entry friction |
| 857 | HG (copper) | spot | long | −0.05 | −0.13 | entry friction |
| 859 | KAITOUSDT | spot | long | −0.41 | −0.41 | entry friction |

Cohort is too young to judge exits — realized is pure entry/fee friction, `peak≈realized` (nothing captured yet). The desk **is** taking both directions (2 shorts, 3 longs across futures+spot), which is the intended fleet behavior.

### 1. Working well / per plan
- **Engine healthy:** `[TradingRuns] tick due=4 dispatched=4 stops_fired=0 eval_failures=0`. Dispatching cleanly, no eval failures.
- **RUN AI is the only order source** and is executing (signals 216–219 → positions opened). Decision routing + fleet + AI order params all live.
- **Liquidation Defense Daemon (Plan 16) is live and correct:** `[Liquidation] escalations=1 worst=T1 measured=6/6` — measuring all 6 positions, escalating 1 at the mildest tier T1, **no reflex action needed, zero errors**. Live behavior matches the Plan-16 doc's T0–T3 tier vocabulary.

### 2. Lost / profit + why (RUN AI reading)
- **Lifetime (130 runs w/ realized): −$466.14.** Gross win **+$820.57** vs gross loss **−$1286.72** → **profit factor 0.64** (losing $1.57 for every $1 won).
- **The rotated-out cohort (stopped ~4h ago) tells the story: 15 losers vs 1 winner** (ETH +1.52). Losses cluster at uniform **−0.45 / −0.90** — the signature of fixed-size stops firing, i.e. death by many small symmetric cuts. This is the *same* profit-leak shape flagged before (fees + stops dominating, winners not run).
- **BUT** I cannot yet audit *why* each entry was taken: the RUN AI "read" (action/confidence/rationale/route) is **not journaled to any queryable table** — `run_events` and `run_reports` are empty; worker stdout only prints `run N executed signal M`. Entry-quality diagnosis needs the `signals` table rationale → **cycle 2 action.**

### 3. What we missed / others
- **Decision-reasoning journaling gap** — losses are not auditable from the DB. High priority: without it, "modify the RUN AI reading algorithm" is guesswork.
- **Orphan/zombie position hygiene:**
  - Position 67 SOLUSDT short (agent 6, opened **2026-07-27**, ~4 days) — `[OrphanReclaim] scanned=1 held=1 blocking=1`: reclaim *sees* it but is stuck **holding** (blocking). Dead capital for 4 days.
  - Position 80 BTCUSDT long **qty=0** (agent 37) — a zombie row, not even scanned by reclaim.

### 4. Monitoring — doc surfaces
- **Plan-16 liquidation daemon HTML:** structurally sound (519 lines, 5-stage algorithm, T0–T3, LIQ_REFLEX) and its described behavior **matches live reality** (escalations/tiers observed). ✔
- **`/docs/how-it-works`:** the URL is **not a real page.** `App.tsx:508` redirects unauthenticated users to `/login` (correct), but `how-it-works` is **not a registered slug** in `DocsPage` — authenticated it silently **falls back to the Guide doc**. The brand-new `docs/plan/18-how-ai-automated-trading-works.html` is **not wired** into the docs system. ✘

### 5. Recommendations
1. **(build, don't hand-fix)** Journal the RUN AI read to a queryable table (action, confidence, route, rationale, chosen stop/target). Everything downstream depends on this being auditable.
2. **(measured)** The profit factor 0.64 + uniform-small-loss cluster points at exit geometry again — but per the base rule I will *not* hand-tune. Cycle 2: pull signals 216–219 rationale and watch the 6 live runs' exits to isolate stop-too-tight vs trailing-never-arms vs fee-hurdle, then propose one tested change.
3. **(hygiene)** Unblock orphan reclaim on the 4-day SOL short and purge the qty=0 BTC zombie.
4. **(docs)** Wire Plan-18 as a real `how-it-works` slug, or the URL stays dead.

_Next cycle fires ~:43/:13. Snapshot written to automation-snapshot.json._

**Owner action mid-cycle:** removed test-data position 67 (SOLUSDT short, agent 6) at owner's instruction. Row backed up in transcript; no FK references. One orphan remains (id 80, agent 37, BTCUSDT qty=0 zombie) — left pending owner's call.

---

## Cycle 2 — 2026-07-31 ~08:47Z (Δ vs cycle 1)

**Book delta:** Lifetime realized **unchanged at −$466.14** — no runs closed in the 19-min gap; the 6 live runs are all still holding cycle-4 positions. SOL orphan delete persisted (gone from book).

### Headline finding — the RUN AI "read" is not journaled anywhere
Chased the decision reasoning across every candidate table: `signals.content` is a **stub** ("Trading run #859 cycle 4"), `signals.exit_price` (target) is **NULL**, and `run_events` / `run_reports` / `automation_runs` are empty for fleet runs. **The AI's reasoning, confidence, and chosen route are not persisted.** The AI's stop/target *do* land on `positions.stop_loss/take_profit` — so params apply — but the *read* itself is un-auditable from the DB. **This is the gating blocker for item 2 ("modify the RUN AI reading algorithm"): you cannot tune what you cannot see.**

### Exit geometry is healthy — the leak is give-back, not bad R:R
Pulled stop/target on all 5 live positions (raw price %, all 3× leverage):

| run | sym | side | stop% raw | tgt% raw | R:R | note |
|-----|-----|------|-----------|----------|-----|------|
| 853 | NZDUSD | long | 1.73 | 4.0 | 2.31 | ok |
| 854 | HYPE | short | 1.40 | 3.0 | 2.14 | **peaked +$2.47, gave it back** |
| 856 | BTC | short | 3.40 | 7.0 | 2.06 | ok |
| 857 | HG | long | **0.50** | 1.2 | 2.40 | stop ×3lev = 1.5% → **noise-tight on copper** |
| 859 | KAITO | long | 2.0 | 4.0 | 2.0 | ok |

- **The AI order params work** — per-instrument stops/targets at a healthy **R:R ~2.0–2.4** (not the old flat 5/10%). So entries aren't the geometry problem.
- **The leak, live:** HYPE (854) peaked **+$2.47** unrealized then round-tripped back to ~breakeven, and the run is **still open** — the trailing lock did **not** bank it. The mechanism exists (`run_engine.py:760 _trailing_lock_hit`, arms only when `peak ≥ activate_usd` from `fleet_planner.py:151`), but the activation floor sits **above** where these small mean-reverting fleet peaks occur, so winners round-trip unbanked. This is exactly the prior-diagnosed pattern.
- **HG stop is noise-tight** (0.5% raw × 3× = 1.5% to stop on copper) — likely to stop on intraday noise before thesis plays out.

### Docs / liquidation
- **Liquidation daemon:** steady `escalations=1 worst=T1 measured=6/6`, no reflex, no errors. ✔
- **Orphan reclaim:** last log line (08:26) predates the 08:37 delete; DB row is gone, so `blocking` clears mechanically — will confirm in cycle 3.

### Recommendation (evidence building, no change yet)
Prior work already **measured-and-rejected** lowering `trail_activate_rr` (full-life-peak replay lies via lookahead) and endorsed a **breakeven ratchet** instead — move the stop to entry after a modest profit (e.g. +0.5R) so a HYPE-style round-trip exits **flat, not at a loss**. `order_params.py:38` hints breakeven logic exists (comment: "breakeven hit rate ~33% instead of 90.9%") — **cycle 3 deep-dive: is the breakeven ratchet actually wired into the fleet stop-eval path, or dormant?** One HYPE data point is not proof; I'll accumulate exit outcomes across cycles before proposing a tested change (base rule: build the daemon path, don't hand-fix).

---

## Cycle 3 — 2026-07-31 ~09:00Z — CORRECTION + verified diagnosis

### ⚠️ Correction: the cycle-1/2 "not journaled" headline was wrong (my bug)
`run_events` is **not empty — 39,903 rows, live to 08:56.** My cycles 1–2 filtered on `created_at`; the column is **`ts`**, so the queries errored silently. The RUN AI read is **fully journaled**: `decision` (action, confidence, conviction, sub-scores thesis/momentum/entry/risk), `order_params` (stop/target/route), `order_intent`, `gate_skip` (block reason), `trade` (fee_usd), `equity`. The "add journaling" hard-implement is void — it exists. Retracted in the backlog corrections log.

### Verified "why lost" (from decision events, 24h)
- **Decision mix:** hold **149** (avg conf 0.37), buy 45 (0.68), sell 20 (0.71), retire 1. **69% hold** — cautious desk, not overtrading.
- **No stop-loss / target exits at all.** Terminal reasons: `idle_retired` 16, `user_stop` 11, `desk_retired` 2, `fleet_stop_all` 2. → **Losers are small positions retired/stopped while marginally red**, not stop-outs.
- **Fees are the dominant structural cost:** 32 trades → **$15.58/24h** (~$0.49/trade). With moves this small and mean-reverting, round-trip fees (0.1%/side) routinely exceed the edge. This is the real leak (matches "fees = 74% of the week's loss").
- **Give-back is partly protected:** HG cycle 5 emitted `order_intent: reduce 50%` and sold half — the reduce logic *does* act. My cycle-2 HYPE alarm was a single point, overstated.
- **Inefficiency:** run 831 proposed $14k orders vs a $10k symbol cap for 12 cycles (20+ `gate_skip` "exposure limit"/24h) — wasted analysis, low $ impact.

### Operating-rule change (owner)
HARD recs (high-confidence + low-risk) → implement directly; others → `recommendations-backlog.md`, updated each cycle. **No prod change shipped this cycle by design** — I just corrected a self-error, so the first implementation lands only after the specific code path is verified. Lead candidate: **R1 fee hurdle** (per-market fee table and/or min-edge-vs-fee gate) — next action is to read the existing `RUN_FEE_EDGE_MULTIPLE` / fee-infeasible gate before changing anything.

---

## Cycle 4 — 2026-07-31 ~09:16Z (Δ vs cycle 2/3)

**Book:** lifetime **−466.14 → −466.91** (Δ −$0.77, +1 run). Worker **restarted 09:15** (redeploy/bounce) — liquidation/reclaim daemons reset, next periodic log ~09:30 (reclaim block-clear confirmation deferred to cycle 5). New run **893 USDJPY** rotated in.

### 🔴 Give-back leak REPRODUCED — 3 positions in one cycle (was 1 in cycle 2)
Three live positions hit real high-water marks and banked essentially nothing:

| run | sym | peak P&L | realized now | outcome |
|-----|-----|----------|--------------|---------|
| 859 | KAITOUSDT | **+$9.13** | −0.41 | gave back **100%+** of peak, still open |
| 854 | HYPEUSDT | +$2.47 | **−1.31** | gave back peak **and went negative**, still open |
| 853 | NZDUSD | +$3.22 | +0.23 | gave back 93% of peak, stayed green |

This is no longer a single anecdote — **the dominant profit leak is winners round-tripping unbanked.** A ratchet exists (`risk_engine.py:589`, "in profit ≥ 1×trail") but it is **not protecting these fleet peaks**. Solution direction: understand *why* the existing ratchet doesn't arm on the fleet path, then a **breakeven ratchet** (stop→entry after +XR) so a KAITO +$9.13 peak exits at ~breakeven, not −$0.41.

### Working / docs
- Decision mix (45m): hold 3, sell 3, buy 1 — quiet. Fees $0.60 / 3 trades. Engine healthy.
- Liquidation/reclaim: pending post-restart (~09:30). Zombie position 80 (qty=0) still present.

### Solution candidate promoted → **R6** (give-back / ratchet) now leads R1
Per operating model: **no change this session.** This is analysis identifying the solution; it ships to prod only when the READ-only code deep-dive confirms the mechanism and a test proves the fix. R6 now has 3 fresh data points — the strongest evidence of any candidate.

---

## Cycle 5 — 2026-07-31 ~09:44Z — R6 ROOT-CAUSED

**Book:** lifetime **−466.91 (flat)**, no runs closed. Prod redeployed again → **`20260731-feveni18n`** (financial-events i18n; worker restarted 09:40). Give-back continues: KAITO peaked **+$10.98** (banked −0.41), BTC peak +2.99 (banked −0.47), HYPE frozen −1.31. Liquidation `escalations=1 worst=T1 measured=4/4`, healthy.

### 🎯 Root cause of the give-back leak (the answer to item #2)
Pulled `stop_conditions_json` for the give-back runs:
```
KAITO 859: max_loss_usd 40.58 · trail.activate_usd 40.58   (peak $10.98)
HYPE  854: max_loss_usd 43.48 · trail.activate_usd 43.48   (peak $2.47)
BTC   856: max_loss_usd 34.78 · trail.activate_usd 34.78   (peak $2.99)
```
**The trailing lock arms only when `peak_pnl ≥ activate_usd`, and `activate_usd` = 1× `max_loss_usd` (~$35–43). Fleet peaks are $3–11 — 4–13× below the floor — so it can NEVER arm.** The `risk_engine.py:589` ratchet is gated on the same `1×trail`, so it's dead too. **Confirmed: 0 trailing-lock exit events in 24h.** Winner-protection is structurally non-functional for the entire fleet → every winner round-trips 100%. This is the single dominant profit leak, root-caused to one config relationship (matches memory `fleet-exit-logic-trailing-lock` / `trailing-lock-never-arms`).

### The RUN AI *reading* is not the problem — the *exit config* is
Reads are sane (R:R ~2:1, 69% cautious holds, journaled fully). The loss is: fees + winners that can't lock because the trail floor is set ~10× too high for fleet-sized peaks.

### Fix (R6) — root cause verified, still not shipped
A **breakeven ratchet** armed at a threshold the fleet actually reaches (fraction of `max_loss` or k×round-trip-fee), so a +$10 peak exits ≥breakeven. **Not** naive `trail_activate_rr` lowering (measured-and-rejected). The arm threshold must come from a **backtest**, then implement off `main` + test + deploy. Per operating model + the deploy-safety lesson from this session: **no prod change without owner go and verification.**

---

## Cycle 6 — 2026-07-31 ~10:07Z — R6 backtested & dropped; R7 entry-quality signal

**Book:** lifetime **−466.91 → −465.51 (+$1.40)**. KAITO now **+0.95 realized** (peak 10.98 — banking, not round-tripping to a loss). Liquidation escalated one position to **T2** (from T1; measured 4/4, no reflex). Prod redeployed → `20260731-feveni18nfix`.

### R6 verdict: DROPPED (backtested)
Counterfactual backtest (28 runs, 10,644 equity points): best case +$5 in a narrow band, achieved by saving 3 give-backs (+$26) minus **clipping a real +$20.80 winner (run 125)**. Losses are dominated by **never-positive directional runs (112/104/113 = −$130)** an exit-lock can't help. Reproduces the team's prior rejection. Full: [r6-backtest-result.md](r6-backtest-result.md).

### R7: the gate keys on the wrong scalar (new lead)
Entry-decision features by outcome (28 closed runs):
- **`confidence` is anti-predictive** (losers 0.70/0.66 vs winners 0.60/0.60) — yet it's the gate variable.
- **`conviction` (0.47 vs 0.24) and `momentum_quality` (0.62 vs 0.52) separate winners from losers.** `entry_quality` doesn't.
- `RUN_CONF_V2` (conviction gate) exists but is OFF. **Hypothesis worth a proper per-decision expectancy backtest** before any change — n=28, group means, R6 discipline applies.

### Working / docs
Engine healthy; liquidation daemon live (now T2 on one position — watching). Reads journaled fully. No prod change this session.


