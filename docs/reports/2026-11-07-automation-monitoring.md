# Automation monitoring — 2026-11-07 (UTC day) — daily 24h sweep

Newest-first. Authority for rules/access/traps: `HANDOFF-automation-monitoring.md`.
This is the **first run of the persistent daily scheduled task** (owner 2026-11-07).

## 24h sweep — 2026-11-07T15:14:13Z (KST day 2026-11-07 = 11-06T15:00Z → 11-07T15:00Z)

Prod clock anchored `SELECT UTC_TIMESTAMP()` = 2026-11-07 15:14:13. Image on both
containers `sooppiy-backend:20261107-drop-authlib` (95e50b3; origin/main 287d688 is one
docs commit ahead). Trading set re-derived (fleets active/running/building ∪ runs cycled
in 24 h ∪ trend_events agents) = **exactly {6, 60}**; agent 63 (trend module) has 0 runs,
0 positions, 0 `trend_events`, 12 "scanned 5, signals 0" cycles.

### 1. P&L — dollars first (n stated)

| window | agent 6 (info) | agent 60 (forevery1969) | combined | n fills | open uPNL | pnl_audit |
|---|---|---|---|---|---|---|
| **KST day 11-07** (11-06T15Z→11-07T15Z) | **$0.00** | **$0.00** | **$0.00** | **0** | 0 positions → $0 | no closes |
| UTC day 11-06 | **−0.68** (LINK 126294 arm:10 cover 14:46Z) | **−2.00** (MCD 126922 flatten 14:30Z) | **−2.68** | 2 | — | ledger −2.68 = adapt −2.68, `ok`, EXIT 0 |
| UTC day 11-07 (00Z→15:14Z) | 0.00 | 0.00 | 0.00 | 0 | — | prints no row (zero closes) |

With / without the largest contributor (UTC 11-06): −2.68 / −0.68 — sign unchanged.
Fees in the KST day: $0 (no legs). Win rate / payoff ratio: undefined (0 trips). Cash
check: agent 6 `agents.cash` 9891.72 (unchanged from the 11-06 analysis end), agent 60
9995.95. Cross-check routes: (a) `pnl_audit` ledger replay, (b) `signals` fills by
`created_at`, (c) `trading_runs.realized_pnl_usd` of runs stopped in-window (−1.51 = LINK
run whole life, of which −0.68 landed on 11-06 and −0.83 on 11-05) — all three agree.

**Verdict in profit-or-loss terms:** a $0 day on both books, produced by a desk that
could not decide, not by a desk that decided to stay flat. 255 of 255 agent-6 decisions
and 29 of 29 agent-60 decisions were `hold`; **251 and 27 of them carried no LLM
verdict at all** (`decided_by` scaffold, or rule with `fallback_reason` "no llm response").
Not an improvement; see §5.

### 2. Agent A — AI-authored outcomes (cross-checked §4)

n = 2 realized trades (LINK 126294 four fills, MCD 126922 two fills), 284 decisions in the KST
window of which **4 were AI verdicts** (all hold, all with the chair reply unparseable → the
trader's verdict stood). Counterfactuals priced at the actual fills and Hyperliquid 1h/15m candles.

| trade | author | $ | reason (A) | evidence |
|---|---|---|---|---|
| LINK short 8.083 @10.742 (cyc 2, 11-05 16:09Z) | desk sell 0.7 → panel sell 0.62; **size = platform `null_size_cap`** | opens a −1.51 run | Shorted 11 min after `hot_issue psych_shock / regime:panic / price_move −7.8%`, i.e. AFTER the drop, while LINK was already bouncing (16:00 candle 10.805); +1.75 % against within 15 min. The desk's own text cites the "5-sigma shock… reversal" and dismisses it. Its stated "recent positive short record on LINKUSDT" is **false**: 47 LINK closes 10-15→11-05 sum −$0.01. Anti-timing shape, 5th sighting. | 15:58:10Z hot_issue; 16:09:39Z decision/size_clamp |
| LINK cover 50 % @10.887 (cyc 3) | desk `reduce 0.5`; panel `local-fallback` hold 0.55 | **−0.61** (40 % of the run) | Sold the bounce top 25 min after entry ("limit loss… reversal risk"); LINK fell to 10.594 within 25 min — that half held = +0.58. | 16:34:33Z order_intent |
| LINK cover 40 % @10.853 (cyc 12) | desk "avoid a squeeze-driven rally" | −0.19 | Sold a local high again; the squeeze came 18 h later. 3/3 AI exits on this run at local highs. | 20:54:40Z |
| LINK arm `price_above 11.0105 → close 1.0` → fired 11-06 14:46Z @11.018 | AI armed; **level = the house 2.5 % stop cap** (desk wanted 5 %/11.278) | **−0.68** | The arm duplicated the live bracket (`stop_ref_px` is code-enforced from `positions.stop_loss`); fired 0.15 % under the day's high; executor correct — 63 s poll, gap-through 10.964→11.018, slippage $0.018. | 19:51:03Z arm; 14:46:21Z armed_exit |
| LINK, net of AI exits | | −1.51 vs −2.31 full-to-arm | The reductions "saved" $0.80 only relative to the house stop; against the desk's own plan they sold both bounce tops. A struck its own excuse. | |
| MCD buy 0.3218 @277.13 (cyc 7, 53 min before the close) | **chair verb-flip** (trader hold ×5 "lacks positive expectancy"; cyc-7 trader scores 0.3/0.3/0.3, conviction 0.37); size = `null_size_cap` | **−2.00** | Chair amended `action → buy` ("strong bullish momentum, breakout potential") and, by design, dropped `order_intent` + `outlook` → no size, no bracket → clamp 142.84→89.27 and the exact 5 %/10 % bracket the trader rejected five times. Overnight hold was not reasoned: cycles 8–13 were all scaffold/rule (LLM mute). | 20:37:23Z order_discussion, decision `chair.amended [action,…] dropped [order_intent, outlook]`, size_clamp |

**AI-axis verdict (A):** UTC 11-06 **−$2.68**, both losses entries the AI did not size (MCD: an
entry the AI's trader did not propose); ex-MCD −0.68. KST 11-07 **$0.00, and $0 of it is AI
judgment** (1.4 % of decisions were verdicts). The 4 holds' counterfactual at machine size
through 15:00Z: BCH +8.67, AAVE −1.94, BTC +0.52, SUI +1.30 ≈ +$8.6 forgone, **ex-BCH ≈ −0.1 →
inconclusive, one name.** Not verifiable: the trader's pre-amendment verb at MCD cyc 7 (the
tape records only that the chair changed it); the chair/risk prompt text.

### 3. Agent B — algorithm-authored outcomes (cross-checked §4)

| outcome | mechanism | $ | reason (B) | evidence |
|---|---|---|---|---|
| MCD 126922 flatten at the open | **breakeven ratchet** (reason string `trailing_lock`) | **−2.00** | Peak 0.3817 − base(peak_realized −0.0045) ≥ arm 0.1744 → armed; floor ≈ 0.197. Legacy trail `activate_usd 1.43` > peak → could not arm. Mark frozen at 278.04 from 20:57Z to 14:30:19Z (730 identical equity rows), first live print 270.93 = −2.56 % gap → fire on the first print. `ratchet_audit`: full-book, post-fix, in-band. **The gap authored the dollar**; the desk's own invalidation ("below $271") was already breached at the open. | `stop_mechanism` 14:30:50Z |
| MCD entry sizing | `size_clamp null_size_cap` | $89.18 notional | desk gave no size; 0.25 × 357.09. Swing gap sizing respected (R/G cap ≈ $2,465 ≫ $89; loss = 2 % of the $100 overnight R). Under `RUN_NULL_SIZE_REFUSE` (live since 22:49Z 11-06) the entry does not exist → **+2.00 exact**. | 11-05 20:37:23Z |
| LINK entry sizing | `null_size_cap` | $86.82 (desk's own median $20) | same defect; refusal → the run never trades → **+1.51 exact** (whole life). | 11-05 16:09:39Z |
| LINK arm:10 cover | armed-exit executor | −0.68 | slippage 0.068 % = $0.018 on $26.7 — one poll's drift, not the author; the short from 10.742 with LINK at 11.018 is the loss. | 14:46:21Z |
| LINK adapt-retire | `retire_consecutive_losses` 3 → `adapt_retired` + 24 h cooldown | 0 | three losing closes ≥ bound 3: correct per spec; cooldown row to 11-07T16:01Z; **0 LINK runs since** (held). | 16:01:28Z |
| 24 + 2 `idle_retired` | 12-cycle idle fuse + 12 h symbol cooldown | fees $0 | see below | 26 `run_status` rows |

**Algorithm-axis verdict (B):** UTC 11-06 −$2.68 (ledger = adapt, resid 0.00), ex-MCD −0.68;
**both legs are null-size-cap entries → under refusal UTC 11-06 is $0.00.** KST 11-07 $0.00:
0 fills (two independent counts), 0 stops, 0 watcher closes, 0 refusals (no entry attempts),
0 `positions_held`, 0 `stop_hit`. **Nothing shipped on 11-06/07 was exercised.**

**LLM outage (B's measurement):** 999 timeouts by 15:38Z; 45 decision successes vs 944
timeouts 04:12→15:00Z = **95.4 % timeout**; real AI verdicts **4/284 (1.4 %)**. Timeout
config: `LLM_TIMEOUT_SECONDS` unset → 120 s, decision tier 300 s, `max_retries=1`; three
calls per decision (three-agent desk) → up to 900 s wall per decision. Expected P&L of a
normal agent-6 day at the month's rate: 14.2 trips × −$0.058 = **−$0.82/day** (independent
12-day check −$0.86/day; ex-worst day −$0.55). The mute desk "saved" that only in the sense of
§5 #7 of the 11-06 analysis. **Not improvement.**

**Slot churn (B, confirmed CODE by the main session):** 24 agent-6 runs retired idle in 24 h;
**20 of 24 had zero AI verdicts in their whole life.** `run_engine.py:1613` computes
`worked = cycle_seq − closed_market − entry_wake − entry_held`; a no-verdict cycle counts as
"worked", although `_entry_held_cycles`' own docstring (line ~927/969) says an LLM outage must
not author rotation. The outage authored all 24 rotations: 25 builds, 10 research batches
(every logged one `'llm': 0`, planner fallback), 15 symbols benched 12 h at once (hold-wall
pattern), ~850 decision call attempts at a dead host, and 3 `fleet_churn` alerts to the user
blaming "market volatility". Fees $0.

**Fleet 43 (B, confirmed):** `PLAN_LIMITS["pro"]` = 3 concurrent / $1000 max bet / fleet size 0;
`candidate_skipped` ≈ 5,100/day (3.5/min) for 7 weeks; plus 22 "plan caps max bet at $1000".
At the 2026-11-17 expiry, if Stripe does not renew: `plan_code_for_user` → None → limits 0 →
`_enforce_subscriptions` pauses every running run (`subscription_lapsed`) and no slot can build.

### 4. Three-axis verification and the A/B cross-check

**DATA (independent re-derivation).** Fills: `signals` by `created_at` (0 in window; 2 on
UTC 11-06) = `pnl_audit` (−2.68) = Σ`trading_runs.realized_pnl_usd` of in-window stops (−1.51 =
LINK whole life). Decisions: 284 at 15:16Z (A counts 4 + 179 + 68 = 251 of 255 for agent 6, the
main session 4 + 182 + 70 at a minute later — the difference is the query minute, not a
disagreement). Both agents' MCD/LINK figures match the main session's dump to the cent.

**CODE (origin/main AND the running image).** `run_engine.py:7055–7065`: when the chair changes
the verb it pops `order_intent` and `outlook` (A's mechanism, confirmed; a deliberate
2026-09-02 design). `run_engine.py:1613`: `worked` excludes closed-market, entry-wake and
entry-held cycles only (B's mechanism, confirmed). Live worker: `_null_size_refuse_enabled()`
True, `_stop_close_first()` True, `_stop_reentry_fence_min()` 30.0, `_null_size_cap_frac` 0.25.

**ADVERSARY — trying to refute the day's conclusion ("the LLM, not the desk, authored the $0").**
Could the desk have been choosing to hold? No: 251/255 decisions carry `decided_by scaffold`
or `rule + "no llm response"`, and `llm_usage` logs 70 decision calls against 284 decisions ×
3 calls each. Could the outage be weekend scheduling? Not supported (Thu 21Z start; prior one
Fri 12Z → Mon). Could the chair stage be at fault? 1–4 % unparseable on up days (R30 killed).

**A vs B — where they differ, chased.** (1) A's "reductions saved $0.80": B does not credit
it; A struck it itself — accepted as struck (relative to the house stop only). (2) MCD author:
A names the chair verb-flip (entry), B names the gap (exit); both agree the null-size clamp
sized it and refusal removes it (+2.00). Not a disagreement — two-axis attribution (§7c). (3)
B measured 999 timeouts, the main session 967 at 15:21Z — same rate, later cut. (4) A's BCH
counterfactual (+8.67 of +8.6) is a one-name sample; kept as a distribution fact, not a result.

**Rejected under the owner law:** nothing excused a loss; A's "hold was right because nothing
moved" was struck by A (BCH moved −2.4 % in the thesis direction).

**Second-tape reproduction of B's churn finding (main session):** zero-verdict share of
`idle_retired` agent-6 runs per UTC day — 10-31 **12/13**, 11-01 **22/23** (previous outage),
11-06 **15/18**, 11-07 **12/16** (this one); even up days run 6/10–13/15. Reproduced across
two outages → backlog **R31 HARD-READY** (subtract no-verdict cycles from `worked`), not
shipped this run (one code change per sweep under an active outage; see §10).

**Consequence found while cross-checking (new watch W-chair-refuse):** of 281 chair-flipped
entries since 10-05 (chair amended `action` to buy/sell), **232 (83 %) carried no size**
(`defer` 204 / `absent` 28; 181 hit `null_size_cap`) because the flip drops `order_intent` and
the light route defers params. `RUN_NULL_SIZE_REFUSE` will therefore refuse ~83 % of
chair-flipped entries. The 11-06 analysis priced panel-reversed buy→sell trips at −$2.46 /
107, so the sign of this consequence is unknown-to-favourable; **measure on the next tape**
(count `null_size_refused` gate_skips whose decision has `chair.amended ∋ action`). AI-first
lesson if it matters: a chair that changes the verb to an entry must author `size_frac`.

### 5. The platform author of the day: the local LLM host is down (42 h and counting)

| measure | value | route |
|---|---|---|
| `llm_usage` decision calls/hour before | 238–357 (11-05 12Z–20Z) | DB |
| step down | **2026-11-05T21Z** (95 → 2 the next hour) | DB |
| calls/hour since | 1–13 (one 23 at 02Z = the 7110f54 restart burst) | DB |
| worker log timeouts since 04:12Z restart (11 h) | **967** `LLM generation failed (provider=local): Request timed out`, 70–97 every hour | log |
| probe from inside the worker (5-token prompt) | **271 s, timed out, returned None** | live probe |
| agent-6 decisions with no verdict | **251 / 255 (98 %)**; `no_verdict` events only 70 (under-counts) | DB payloads |
| agent-60 decisions with no verdict | 27 / 29 | DB payloads |
| previous outage | 2026-10-30T12Z → 2026-11-02T~10Z (~70 h) | DB |
| chair stage | 4/4 "chair reply unparseable" today vs 1–4 % on up days → symptom, not cause (R30 killed) | DB |
| admin alert on silence | **none exists** (admin_alerts callers: billing, ledger_invariant, desk_brief, subscriptions) | code |

Per-day verdict-less share of decisions (agent 6) since 10-26: 10-27 3 %, 10-29 1 %,
11-03 1 %, 11-05 4 % (up days) vs 10-31 ~100 %, 11-01 ~100 %, 11-06 ~100 %, 11-07 ~100 %
(down days). A step function of host uptime, nothing in between.

The host is a Tailscale address — not the prod box and not this machine — so nothing
here can restart it. Fail-closed held: 0 orders authored on silence. What it "saved" is
only §5 #7 of the 11-06 analysis (not trading agent 6 = +$27.21/month ≈ +$0.8/day); that is
not a result, it is the absence of the product.

### 6. Re-verification ledger (every ship / watch of the previous 36 h)

| item | shipped | on prod? | metric moved? | verdict |
|---|---|---|---|---|
| f545d3e #1 refuse unsized entries (`RUN_NULL_SIZE_REFUSE`) | 11-06 22:49Z | `_null_size_refuse_enabled()` → True in live worker | 0 entry attempts since deploy → `null_size_refused` 0, `null_size_cap` 0 | **NOT YET MEASURABLE**; pre-fix instances: both UTC-11-06 losses (LINK, MCD) were `null_size_cap` entries → counterfactual **+2.68** |
| f545d3e #2 stop hits close at the stop (`STOP_DESK_CLOSE_FIRST`) + 30-min fence | 11-06 22:49Z | `_stop_close_first()` True, `_stop_reentry_fence_min()` 30.0 | 0 watcher stop closes since deploy; `stop_hit` events 0 | **NOT YET MEASURABLE**; falsifier text corrected (`stop_dispatch` → `stop_hit`) |
| f545d3e #3 conviction counted only while holding | 11-06 22:49Z | `held` flag on 178 decisions in-window | 0 `conviction_collapse` closes | NOT YET MEASURABLE (holds trivially) |
| 56e1118 / 95e50b3 deps bump + authlib removal | 11-07 02:07Z / 04:09Z | image `drop-authlib` on both containers; `pip-audit` clean | 0 tracebacks, 0 ModuleNotFoundError, health 200 | **HELD** |
| 7110f54 #4 handoff on `positions_held` | 11-07 02:40Z | `handoff_run_id` column, `orphan_reclaim` task started | 0 `positions_held` stops since deploy; 0 handed-off rows | NOT YET MEASURABLE |
| 7110f54 #5 trend telemetry | 11-07 02:40Z | `trend_events` table exists; module cycles hourly | 0 actions → 0 rows (consistent with "a quiet scan writes nothing") | NOT YET MEASURABLE |
| 08-17 lease-fence watch (`fence: lease expired` ≈ 0/day) | — | — | 0 in 11 h of log | HELD |
| 08-27 ratchet falsifier (`ratchet_audit`) | — | — | 78 fires since 11-01, 2 in-band reduces survived; MCD 126922 full-book post-fix (in-band); 6 shrunken-book CANDIDATES to confirm vs log | HELD (candidates pending) |
| LINK symbol cooldown after adapt-retire | — | `fleet_symbol_cooldowns` until 11-07T16:01Z | no LINK run started after 16:01Z 11-06 | HELD |

### 7. Killed hypotheses (by name)

- **H-chair-dead** ("the chair stage is dead weight; 3 calls/decision wasted") — killed: 1–4 % unparseable on up days, 100 % only when the host is mute.
- **H-LLM-weekend** ("the host dies on a weekend schedule") — not supported: 10-30 (Fri 12Z) → 11-02 (Mon), and 11-05 (Thu 21Z) → open; no clean weekly pattern. Inconclusive, n=2 outages.
- **H-fleet43-planner** ("fleet 43's 3/8 is a planner/candidate-supply defect", open since the 11-06 analysis) — killed: it is the `pro` plan's `max_concurrent_runs = 3`, enforced since 2026-09-15.
- **H-rotation-cost** ("24 idle-retire rotations cost money") — re-refuted: 0 fills on all 26 retired runs; cost is events/research, not fees.

### 8. Health

| check | value |
|---|---|
| containers | worker + backend `20261107-drop-authlib`, up 11 h; admin up |
| prod == origin/main | code identical; main is 1 docs commit ahead (287d688) → not drift |
| alembic | 0057 |
| `MAX(run_events.ts)` | 15:13:41Z at a 15:14:13Z clock |
| tracebacks (worker/backend, since 04:12Z) | 0 / 0; ModuleNotFoundError 0 |
| ERROR lines | 3 (Market Intel news snapshot `errors=1` ×2 — feed, not code) |
| `fence: lease expired` | 0 |
| run cycles/hour | agent 6: 6–15 (8 slots, 30-min cap); agent 60: 1–6 until 22:50Z Friday, then dormant (NYSE closed — by design) |
| LLM no-verdict | agent 6 98 %, agent 60 93 % (§5) |
| fleets | 44 active 8/8, 24 idle-retire rotations in 24 h (`fleet_churn` user alerts ×3 blaming "market volatility"); 43 `replenishing:3/8` (plan cap, R29) |
| `run_events` rows / 24 h | 14,193 (9,028 agent-6 equity rows) + 2,532 fleet-43 `candidate_skipped` |
| LLM spend | $0 paid; 70 decision + 46 brief local calls logged |
| `sooppiy.com/api/health` | 200 |

### 9. Today's solution — and why it is platform, not skill

**Hypothesis:** the operator is not told when the desk goes mute, so outages run for
days (2 outages, ~112 h in 9 days, 0 alerts). **Falsifier:** an admin alert exists and
fired in either outage window → wrong. Checked: `admin_alerts.notify_admins` has four
callers, none about the LLM; `alert_log` carries no LLM-silence kind. **Confirmed.**

**Why not AI-first:** a desk that gets no model answer cannot author a lesson or a
brief line about its own silence — the actor has to be the platform ("the desk cannot
perceive X" pattern, HANDOFF §10). **Money path:** none; reads `run_events`, sends mail.
Counterfactual P&L: $0 direct.

**Shipped this run (gate in §10):** `service/server/llm_silence.py` + `tasks.llm_silence_loop`
(15-min tick, role research): last 120 min of `decision` events; n ≥ 10 and ≥ 80 % mute →
one `notify_admins` email+SMS (console recipients, both set on prod), re-alert every 6 h
while it lasts, one recovery notice under 50 %. `LLM_SILENCE_ALERT=0` kills it.

**Falsifier for the next sweep:** prod is ~99 % mute at deploy time, so `[LlmSilence]`
must appear in the worker log within ~2 min of the container start (loop sleeps 120 s)
and the operator's email/SMS must have been sent (`sent: {'channels': ['email','sms']}`).
No line = the fix FAILED. Thereafter: exactly one re-alert per 6 h while mute; one
recovery notice when the host returns.

**Not solved here (owner items, R28/R29):** the host itself; fleet 43 sized for 8 under a
plan that allows 3 (and expires 2026-11-17 — if the Stripe renewal fails, agent 60's runs
are paused by `subscription_enforcer`).

### 10. Shipping gate record

| gate condition | result |
|---|---|
| evidence reproduces across ≥2 independent readings | two outages (10-30→11-02, 11-05→) seen in `llm_usage` (DB), worker-log timeouts, decision payloads, and a live probe |
| counterfactual P&L at the live mark | not a money path: $0 direct; the alert reads `run_events` and sends mail |
| AI-first or justified | justified: a mute desk cannot perceive its own silence (HANDOFF §10 "observable the desk cannot see") |
| fail-before / pass-after | new test module cannot collect without `llm_silence.py`; Wiring tests fail with `tasks.py` reverted → 28 green after |
| mutation checks | 8/8 caught: rule-branch dropped, re-alert gate removed, space-form ts bound, role-map entry removed, recovery never announced, persistence never saved, failed send still stamps, recovery without alert |
| ruff `F401,F811,F821,F841` (cwd `service`) | clean |
| full pytest (cwd `service/server`, `DB_PATH=/tmp/x.db ALPHA_VANTAGE_API_KEY=demo`) | run 1 (module mutated on disk mid-run by my own mutation tests) 5,435 passed / 1 failed = the exact M5 mutant signature; run 2 on the reviewer-fixed code **5,441 passed, 0 failed, EXIT 0**; run 3 on the final code: **5442 passed, 10 warnings, 1349 subtests passed in 673.81s (0:11:13), EXIT 0** |
| frontend | unchanged — `npm ci && npm run build` not required |
| `pip-audit -r service/constraints.txt --no-deps --disable-pip` | no known vulnerabilities |
| gitleaks | new files: no leaks; commit range re-scanned before push |
| adversarial reviewer | NO BLOCKER ×2; its should-fix #1 (persist state in `platform_settings`), #2 (do not stamp a failed send) and note (no recovery notice without a received alert) folded in |
| independent verifier | VERIFIED ×2 (35 + 32 own scenarios on a real temp DB, MySQL row access read from `database.py:491–510`, mutant caught) |

**Lesson for the pipeline (new trap):** never mutate a module on disk while a full
suite is running in the same tree — run 1's only failure was my M5 mutant, not the code.
Mutation tests go BEFORE the full run, or in a copy.

### 11. Not verified this run

- Why the LLM host stopped answering (no access to the host; only its symptoms).
- The MCD −2.56 % open gap's market cause (n=1, pre-window, not pursued).
- The 6 `ratchet_audit` shrunken-book candidates against the worker log (log only reaches
  back to 04:12Z; all 6 fires predate it).
- Whether the admin email/SMS actually arrives at the recipient (only the sender's accept
  is observable from the box).
- `docker logs --since 24h` covered 11 h (container restarted 04:12Z); event counts from
  the log are for that span only.
