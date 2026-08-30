# Automation monitoring — 2026-08-22 (UTC day), newest-first

Continued from [2026-08-21](2026-08-21-automation-monitoring.md) (day closed
with **ZERO trades — no realized row**; R33 shipped/untested; R28 shipped,
measured harmful, reverted same day; rails flawless throughout).
Targets: **info@askkpop.com — user 5 / agent 6 / fleet 38** (7 slots, ~$10k,
crypto); **forevery1969@gmail.com — user 25 / agent 60 / fleet 37**
(us-stock+forex, EXTREME; us-stock watched 13:30–20:00Z).

## Cycles 205-207 — 01:5xZ / 02:2xZ / 02:5xZ (anchors 01:51:47, 02:21:49, 02:51:50): quiet; **the R28-revert falsification PASSED and is CALLED**

**PROFIT-OR-LOSS FIRST.** Zero trades in all three windows (**44.7h since the
last fill**), no open positions, ledger unchanged. Rails: fence 0, caps 0,
zero rail events at all in cycles 206-207. Fleet 37 held **10/10**; fleet 38
recovered 3/7 → 5/7 as cooldowns expired (R34 behaving as measured).

### R28-revert verdict: VINDICATED (pre-registered test passed)

The pre-registered test (cycle 195): after the 21:11:53Z revert, the
truncation rate must fall back toward the 0.59-2.37% daily band; if it
stayed near 5%, R28 was not the cause and the revert bought nothing.

Result: **57 decisions / 0 truncations** since the revert. Under the
R28-era rate (13/251 = 5.18%), **P(0 in 57) ≈ 0.048 — under the 0.05
line.** Observed post-revert rate: **0%**.

Control worth noting: the #508 A/B was live during BOTH the R28 window
(13 truncations) and the post-revert window (0), so the arms' prompt
composition is common to both windows — the only differential is R28's
~350-char text. **Verdict: the truncation spike is attributed to R28; the
revert did what it claimed.** Called only now, after two earlier verdicts
on R28 had to be walked back for being early — this one waited for the
threshold.

This closes the last open falsification from the 08-21 work. Standing
board: **#508 readout is the sole pending gate**; queued behind it, in
order: desk_record corrections (R30 + staleness), C's cooldown A/B, and
sizing (OFF — precondition failed in the replay experiment).

Docs merged to main this batch: #523 (5-agent debate), #524 (both step-2
experiments). Post-revert counter at the 207 anchor: 57+/0.

## Cycles 203-204 — 00:5xZ / 01:2xZ (anchors 00:51:37, 01:21:45): quiet; **BOTH step-2 experiments COMPLETE** — knee-diff and declined-entry replay

**PROFIT-OR-LOSS FIRST.** Zero trades (43.2h since the last fill), no open
positions, ledger unchanged. Rails clean: fence 0, caps 0, zero salvaged
since the revert; post-revert counter **43 decisions / 0 truncations**
(P(0|43) ≈ 0.10 under the R28-era 5.18% — approaching meaningful, not yet
called). Fleet 37 **10/10**; fleet 38 2-3/7 on the cooldown treadmill (R34).

### EXPERIMENT 1 (knee-diff, E's design) — COMPLETE

Agent 6's actionable decisions per 12h: 11/7 (08-17) → 5/3 (08-18) → 4/1
(08-19) → 2/0 (08-20) → 0/1 (08-21). **Findings:**

1. **No second switch.** After the known 08-18 level-shift (#505), the fall
   to zero was a smooth ~halving per day — no deploy after 08-18 can claim
   the extinction.
2. **`rag-flat-on` (08-20 21:56, DESK_RECALL_FLAT promotion) is
   EXONERATED** — actionable was already 0 for the 12h before it deployed.
   R27 (08-20 08:10) likewise unattributable (last entry predates it; rate
   already ~1/day).
3. **A smooth decay under constant conditions suggests a FEEDBACK LOOP, not
   a switch.** Hypothesis logged (not a finding): each hold cycle writes
   "no positive-expectancy entry" lessons into the journal/recall corpus,
   which recall feeds back into later cycles — holding teaches holding.
   Testable: the decay rate should track corpus growth.

### EXPERIMENT 2 (declined-entry replay, the A-vs-B decider) — COMPLETE, verdict INCONCLUSIVE

Pre-registered H: "the declined book is negative expectancy — the declines
are correct." Population: **25 declined concrete plans** (one per
never-traded run, 08-14 → 08-21T12:00Z), replayed at each plan's OWN
zone/stop/target against actual marks + candles.

| measure | value |
|---|---|
| triggered | 15 of 25 (**10 never reached their entry — declining cost $0**) |
| mean net @ $350 notional | **+$1.87/trade** |
| without the largest (LTC 1558 +$42.26) | **−$1.02/trade — SIGN FLIPS** |
| median | **−$2.27** (the typical declined trade LOST) |
| win rate | 6/15 |
| by bias | long +$5.70 (ALL of it the one LTC rally) · **short −$2.52 → the refused shorts were clearly correct** |

**Verdict: INCONCLUSIVE by pre-registration** (n=15 < 30; sign flips on one
contributor). NOT refuted: the declines are approximately right at the
median; the entire "forfeited profit" is ONE missed LTC rally.

**Known-case reproduced with a correction attached:** run 1577 TRUMP short —
zone entered, stopped at ~1.72 for **−0.86% net**; the −11.6% figure only
materializes with NO stop. The scare number overstated the decline's value;
the decline was still correct.

Caveats recorded: 4/15 replays candle-flagged coarse (understates both
stop-outs and target-hits); mark cadence often 12-25h (9/15 exits at
last-available-mark); stops parsed from invalidation text in 25/25.

### Debate resolution after both experiments

- **B stays right about the INSTRUMENT** (denominator bug, dead-regime tape,
  the 5-pip forex reductio).
- **A is roughly right about the BEHAVIOR** — even reading a broken mirror,
  the desk's declines were near-correct at the median.
- Both true at once: fixing the mirror (after #508) is a CORRECTNESS duty,
  not a profit unlock. The profit constraint sits deeper — candidate
  generation and the platform-set sizing envelope (C's and D's territory).
- **Consensus-plan step 5 (sizing lift) stays OFF** — its precondition
  ("declined book proves +EV") was NOT met.

Plan status: (1) #508 wait — in force · (2) both step-2 experiments —
**DONE** · (3) desk_record corrections — queued behind #508 · (4) cooldown
A/B — queued · (5) sizing — off the table.

## Cycle 202 — 00:2xZ (anchor 00:27:40): quiet; docs batch; the declined-entry replay experiment LAUNCHED

**PROFIT-OR-LOSS FIRST.** Zero trades (42.3h since the last fill), no open
positions, ledger unchanged. Rails: fence 0, caps 0, zero salvaged since the
revert; 1 alert (retire notice). Post-revert counter: **38 decisions / 0
salvaged** — P(0|38) ≈ 0.13 under the R28-era 5.18% rate; strengthening,
not yet conclusive. Fleet 37 9/10; fleet 38 slid 6/7 → 3/7 on another
cooldown wave (R34 behaving as measured).

Per the owner-requested 5-agent debate (below), the consensus step-2
experiment — replay ALL declined entries at their own planned zone/stop/
target against actual subsequent prices — was launched this cycle
(read-only; does not touch #508).

## THE 5-AGENT DEBATE (owner-requested, 2026-08-21 ~23:52Z → 08-22 00:2xZ)

The owner ordered a 5-agent discussion of the zero-trade day. Five agents
argued assigned positions with fresh prod measurements; the main session
cross-checked all five. Full record:

### Positions and what survived cross-check

**A — "the desk is right; no edge; change strategy."** Headline claim
(negative GROSS expectancy, −$126 over 256 closes since 08-12) was **KILLED
by cross-check**: the window pools the extinct default-size-bug cohort —
the authoritative ledger shows 08-12/13/14 = −19.01/−144.40/−17.51 and
08-15→20 = **+5.62**. A's custom replay also disagreed with `pnl_audit` on
which day was best (claimed 08-17 +$19.81; ledger says 08-16 +$5.65) — where
a custom replay diverges from `pnl_audit`, the ledger wins. **Survives:** the
declined TRUMP 1577 short moved **+11.6% AGAINST** the proposed trade
(fresh 18-observation trace) — that single decline was profit-positive.

**B — "the desk is misinformed about itself"** (strongest report):
(1) `desk_record` denominator bug mechanically confirmed (sums every entry
leg; run 1099: ~$10.1k denominator vs ~$9.1k true max concurrent exposure);
record-wide correction 0.169→0.213 median (n=33, 39% multi-entry).
(2) **The disclosure describes a dead tape**: 76% of the record predates
08-18; on the post-08-18 tape a 5h window's best directional excursion has
median **1.32%** (n=198) — 97% of windows exceed the disclosed p75
(0.334%), **45% exceed the disclosed ALL-TIME best (1.44%)**; a
random-direction 5h hold beats the disclosed median best **74% of the
time**. (3) **The forex reductio**: fleet 37's disclosed forex best-ever is
**0.047% ≈ 5 pips** — a threshold EURUSD crosses within single 30-min
cycles. A statistic that calls a routine event impossible is measuring the
platform's own rails (5.3h idle churn, 0.6h desk retires, summed-leg
denominators), not the market. B honestly killed its own censoring claim
(at_time full-horizon runs reached LESS: −0.065% vs +0.217% median —
endogenous close reasons confound both ways) and disclosed the early tell
against itself: the #508 control arm (no line) shows 182 holds / 0 buys —
removing the line has NOT yet restored entries.

**C — "the structure never lets the desk play":** live-locked universe
(10/15 crypto cooled, 1 eligible, gate drops it; 71 of 92 gate evaluations
in 48h kept ZERO); **98.0% of stopped runs (194/198, 7d) died having never
traded**; 41% of builds land within 300s of a cooldown expiry (n=49, min
28s); 24h slot-hour occupancy 60.3% (~$4k crypto capital idle); never-traded
runs consumed 2,062 decision LLM cycles + 3,191 outlook calls in 7d.
Honestly flagged its own counter-signal: fleet 37 at_time runs lived
1,558 min avg and 2 of 3 STILL never traded. Rec: cut never-traded
cooldown 12h→2h **as an A/B only**, requiring a fresh research batch before
same-symbol rebuild.

**D — "economics bind before strategy"** (overturned a standing premise):
**the sizing envelope is PLATFORM-set, not AI-chosen** — deployable margin
caps at **~8.9% of capital** ($9,735 of $110,005; fleet 37's 9 running
slots sum to $5,532 max_bet on a $100k budget); `size_frac` can only shrink
below the cap and measured entries pressed at 50–212% of it (n=5). At 0.17
entries/day, ANY strategy needs **~4.5 years** to reach t≈2 — every
strategy change ships into a measurement dead zone. Entry notional
COLLAPSED $866→$147 avg in one week. Ordering: throughput (scales
learning) → prove edge → then size. Precondition stated: do NOT lift caps
until the edge is shown +EV at current size.

**E — referee:** (1) the shared premise was sloppy — the 41h window as
drawn contains the boundary FIL cover; window definitions must be
re-verified before adopting any report. (2) **The data is a DISCONTINUITY,
not a steady state**: agent 6 traded ~14/day for five days then stopped
~2 days ago; agent 60 was always slow (478 market-closed skips, 6
trades/week) — two diseases pooled into one manufactured mystery. (3) The
cost side nobody counted: ~966 LLM cycles in 41h for ~1 trade — the
platform may be net-negative INCLUDING opex when trading P&L is ~0.
Ranking: **B > D(reframed) > C > A**; A's remedy is the most destructive
action on the least evidence ("R28's mistake at 10x scale"). One action:
wait for #508, and spend the wait on the knee-diff (locate the exact
collapse instant of agent 6's trade rate; diff every desk input across it).

### Resolutions of the disagreements (the findings)

1. **A vs B on the same record:** B wins the argument about the
   INSTRUMENT (window contamination killed A's headline; the forex 5-pip
   reductio stands). BUT B's own control-arm tell repeats today's R28
   lesson: changing what the desk READS does not reliably change what it
   DOES. The record is broken as evidence; that does not yet prove the
   declines are wrong.
2. **C vs E on structure:** both true at different funnel stages — C
   proves the menu is often empty; E proves the kitchen declines even a
   full menu (3 of 4 fresh builds desk-retired at cycle 1). Fixing either
   alone will not produce trades.
3. **D vs A:** the measurement-dead-zone argument defeats
   "strategy-change first" — no strategy can be evaluated at 0.17
   entries/day.

### Consensus plan (all five converge; ranked by expected profit impact)

1. **WAIT for #508** — nothing touches the disclosure, its env var, or
   `desk_record` until the pre-registered readout.
2. **During the wait (read-only): the DECIDING experiment** — replay ALL
   declined entries (n≥30) at their own planned zone/stop/target against
   actual subsequent prices → settles A-vs-B in money terms. Plus E's
   knee-diff of desk inputs at the collapse instant. **(Launched this
   cycle.)**
3. **After #508 reads out, whichever arm wins:** ship the `desk_record`
   corrections (R30 denominator + staleness/live-vol annotation) — a false
   number to the sole decision-maker is wrong regardless of the A/B.
4. **Then C's cooldown A/B** (12h→2h for never-traded retires; new-batch
   requirement; never a blind ship).
5. **Sizing ladder lift LAST, and only if step 2 proves the declined book
   was +EV.**

### Corrections logged against my own reporting during the debate

- A's contaminated window was caught only because the cross-check re-ran
  `pnl_audit` — reaffirms: custom replays never override the ledger.
- The "sizing is the AI's own choice (0.05–0.82)" line carried since cycle
  177 is **partly wrong**: the AI chooses WITHIN a platform envelope of
  ~8.9% of capital, and was pressing the envelope's ceiling (D, n=5).

---

## Phase 1 accountability reading #1 — 11:08Z (31 min of tape after the 10:36Z deploy)

Taken per HANDOFF-SESSION-2026-08-22 §5 (owner re-ordered monitoring "by"
that handoff; the 30-min crons stay deleted — this is a manual reading).

**§5 query, verbatim:** decisions **6** · buy_proposals **3** · panel_kept **0** ·
fills **0**. All 6 decisions are crypto (fleet 38: WLD, TAO, HYPE, CRV, BNB,
DASH); fleet 37 did not fire in the window (`dispatched: 2` per tick). Open
positions: 0. `pnl_audit` has nothing to audit — **no tape for the two-agent
outcome rule this reading.**

**Tripwires (all clean, checked 2×):** image `20260822-redesign-phase1` on
worker+backend; 0 tracebacks since deploy; 0 post-deploy events carry the
`reach_ab` key; `measured-entry-record` (id 44, prio 47) present.

**Honest read of n=3:** the panel demoted all three buy proposals to hold
(WLD 0.68, CRV 0.68, BNB 0.66 conf) — exactly its measured pre-#484 baseline
(2.6% survival). 31 minutes is not a verdict on anything. The crypto
entry-intent trend going INTO the deploy is the relevant context and it is
monotone down, independent of Phase 1: 08-18 **8/166**, 08-19 **5/267**,
08-20 **2/234**, 08-21 **1/235**, 08-22 **1/143** (decision events with
action buy/sell). Fills by day: 10 → 4 → 0 → 0.

**New measured fact (doctrine channel, n=589):** flat-cycle recall
(`DESK_RECALL_FLAT=1`, first fired 2026-08-21T00:24Z) uses a CONSTANT query
per market — `"crypto flat considering entry fee hurdle expected move"`
(`run_engine._recall_query`) with `explore:false` — so its top chunks never
vary: **589/589 flat recalls since 08-21 (100%) inject
`skill:reachable-exits#1` (score 8.14) + `reentry-discipline#5`**, crypto
included. Phase 1 removed the reachability *line* for crypto; the
reachability *lesson* still reaches every crypto flat cycle through recall.
Post-deploy wording confirms the channel is live: TAO outlook "overridden …
unreachable with a viable risk-reward", DASH "target is unreachable within
the remaining horizon" (2 of 6). The query string also still encodes the
DEAD "fee hurdle" theory (§4).

**Hypothesis (pre-registered, NOT a result):** H-RECALL-FLAT — the 08-21
flat-recall switch-on is a *current* entry suppressor for crypto, distinct
from the #413/#414 panel. Supporting: fills went 4 → 0 the day it fired;
100% chunk constancy. Against: entry intent was already falling 8→5→2 before
it fired, so it cannot be the cause of the collapse — at most it is a
remaining brake. **Falsifier:** if crypto entries recover within ~48h of
tape with recall unchanged, H-RECALL-FLAT is dead. **Proving experiment
(if they do not):** flip `DESK_RECALL_FLAT=0` for crypto only (or dedupe
`reachable-exits` out of the flat query) as a pre-registered A/B on entry
intent, never a blind ship. This is the "doctrine-dedupe" item Phase 2 already
owns; no gate was loosened in this reading.

**Next reading:** same §5 query after fleet 37 has fired and ≥1 crypto slot
has cycled twice (≈2–4h); name n; P&L via `pnl_audit` only if fills > 0.

---

## Phase 1 accountability reading #2 — 2026-08-23 00:45Z (14.2h of tape)

Owner re-ordered monitoring ("Always monitoring", ~11:20Z); a 2-hour session
cron now takes this reading. Numbers verified 2× (aggregate query + hourly
buckets summing to the same total).

**§5 query:** decisions **164** · buy_proposals **44** · panel_kept **1** ·
fills **0** · open positions **0**. All 164 decisions are crypto (fleet 38);
fleet 37 is silent because us-stock/forex are closed on Saturday (`gate_skip:
market closed` ×283) — no us-stock/forex evidence exists yet, by construction.
Tripwires clean: image `20260822-redesign-phase1`, 0 tracebacks.

**Panel:** 43 buy→hold, 17 sell→hold, 1 buy→**sell**. Survival 1/44 =
**2.3%** — indistinguishable from the panel's pre-#484 baseline (2.6%).
The one survivor (SUIUSDT 18:38Z, proposed buy 0.73, panel final sell 0.62,
short bias) died at the risk gate: *"spot sell with no inventory — treated
as hold"*. Fleet 38 is spot-only, so a panel that converts a buy into a
short can never yield an entry. **Entries in 14h: 0.**

**Verdict so far (profit-or-loss first):** P&L delta from Phase 1 = **$0**,
because nothing traded. On its own accountability metric (crypto entry
recovery), Phase 1 has **not moved the metric after 14h**; the 48h window
(ends ~08-24T10:36Z) is still open, but the shape is already the one §5
warned about: the remaining suppressor is the panel's own demotion baseline,
not the reachability line that Phase 1 removed.

**H-RECALL-FLAT:** still live and unrefuted (flat recall continues to inject
`reachable-exits#1` on every crypto flat cycle, score 8.20 on SUI). Not yet
confirmed either — 14h without entries is consistent with it AND with the
panel-baseline explanation; the two are not separable by observation. Only
the pre-registered A/B (crypto-only `DESK_RECALL_FLAT=0` or dedupe) separates
them — queued, not shipped.

**Two-agent outcome analysis:** no fills → no tape → not applicable (stated,
not skipped).

**Withdrawn suspicion (logged so nobody re-chases it):** `llm.source="rule"`
on every decision looked like an LLM fallback; it is on 100% of decisions
since 08-12 — a path label, not a regression.

**Next:** the cron continues 2-hourly. First us-stock/forex reading will only
be meaningful after Monday 08-24 open. If crypto entries are still 0 at the
48h mark, report Phase 1 as failed on its own metric, and move H-RECALL-FLAT
+ the panel's spot-short conversion (buy→sell on a spot fleet) to the front of
the Phase 2 queue as a single pre-registered experiment.

---

## Phase 1 accountability reading #3 — 2026-08-23 01:34Z (15.0h of tape; cron cycle)

**§5 query:** decisions **173** · buy_proposals **44** · panel_kept **1** ·
fills **0** · open positions **0**. Δ since reading #2 (00:45Z): +9 decisions
(hourly buckets 00h +5, 01h +4 — cross-checked), **+0 buy proposals**, +1
sell→hold. All crypto; fleet 37 still weekend-closed. Image
`20260822-redesign-phase1`, worker up 15h, 0 tracebacks, 0 desk_record /
trading_skills errors.

**Entries in 15h: 0.** P&L delta from Phase 1: **$0**. Two-agent outcome
analysis: no tape → not applicable.

**H-RECALL-FLAT:** 173/173 post-deploy flat recalls carry
`skill:reachable-exits#1` (100%, unchanged). Unrefuted, unconfirmed; the
48h window (to ~08-24T10:36Z) stays open. Nothing shipped, no gate touched.

**Note on the last hour:** 44 buy proposals in the first 14.2h, 0 in the
last 0.8h with 9 decisions — within noise for a 7-slot fleet; not a trend.

---

## Phase 1 accountability reading #4 — 2026-08-23 03:34Z (17.0h since deploy; cron cycle)

**§5 query:** decisions **173** · buy_proposals **44** · panel_kept **1** ·
fills **0** · open positions **0** — **identical to reading #3.** Zero
decision events in 02h and 03h. Image `20260822-redesign-phase1`, worker up
17h, 0 tracebacks, 0 desk_record/trading_skills errors.

**Why the tape stopped (verified 2×: trading_runs status + fleet_events):**
fleet 38 (crypto, agent 6) received `stop_all {flatten:true}` at
**2026-08-23T01:10:11Z**; all 10 live runs (1691–1700) went `stopping` →
`stopped`, fleet status `stopped`, reason `fleet_stop_all` at 01:10:48Z.
`fleet_stop_all` is by definition the USER's stop (`desk_memory_ingest.py`:
"the user stopped the whole fleet — not the desk's own call"; it is in
`fleet_planner.REPLACE_NEVER`, so the planner will not rebuild). No successor
fleet exists for agent 6. Fleet 38 had 101 runs lifetime, now 0 running.
Fleet 37 (us-stock/forex) is still `active` with 10 running runs, weekend-idle.

**Consequence for the experiment:** the Phase 1 accountability metric is
crypto entry recovery within 48h (to ~08-24T10:36Z). With no crypto fleet
running, that metric is **unmeasurable from 01:10Z onward**. The 14.6h of
crypto tape that exists (10:36Z→01:10Z) says: 44 buy proposals, 1 panel
survivor (converted to a spot short, gate-skipped), **0 entries**, P&L **$0**.
That is not a 48h verdict; it is an inconclusive partial window, and it is
recorded as such. H-RECALL-FLAT: 173/173 (100%) unchanged; likewise
unmeasurable until a crypto fleet runs again.

**Not done, deliberately:** no fleet was restarted or modified — fleets are
the owner's/AI's, not the monitor's. No gate touched. Two-agent outcome
analysis: no fills → not applicable.

**Owner decision needed:** (a) restart a crypto fleet so the 48h window can be
re-opened (the clock would restart at the new fleet's first cycle), or
(b) treat the crypto leg of Phase 1 as closed-inconclusive and move to the
Phase 2 queue (ATR bracket replay first). Until one is chosen, the cron will
keep reporting fleet 37 only (meaningful from Monday 08-24 open).

## Phase 1 accountability reading #5 — 2026-08-23 04:55Z

§5 (since 2026-08-22T10:36Z, verified 2×): decisions **173**, buy proposals **44**,
panel kept **1** (final≠hold; 0 with final=buy — the one survivor is the spot-short
gate-skip from reading #3), fills **0**, open positions **0**. P&L **$0**.

Last 2h of `run_events`: 0 decisions; only `equity` 1150 / `gate_skip` 40 /
`outlook` 37 / `hot_issue` 1, all from fleet 37 (us-stock+forex, weekend-closed).
Last event ts 04:55:00Z — the worker is alive. Fleet 38 (crypto) remains
`stopped` since the user's `stop_all` at 01:10Z; 1 active fleet platform-wide.

H-RECALL-FLAT: recall rows 173/173 carry `reachable-exits` — unchanged, still
unmeasurable without a crypto fleet.

Tripwires: image `sooppiy-backend:20260822-redesign-phase1` on both containers;
0 tracebacks / 0 `desk_record`|`trading_skills` mentions in worker logs (3h).
No rollback condition. No change made.

Status: crypto leg of Phase 1 unmeasurable pending owner decision (restart a
crypto fleet, or close the leg as inconclusive → Phase 2). Fleet 37 readings
become meaningful after Monday 08-24 open.

## Phase 1 accountability reading #6 — 2026-08-23 05:11Z (cadence now 30 min)

Cadence changed from 2h to 30 min by owner `/loop 30 min` (cron 7,37 * * * *).

§5 (since 2026-08-22T10:36Z, verified 2× — JSON_EXTRACT and LIKE forms agree):
decisions **177** (+4), buy proposals **47** (+3), panel kept **1** (unchanged),
fills **0**, open positions **0**. P&L **$0**. H-RECALL-FLAT 177/177 recalls carry
`reachable-exits` — still 100%.

**Crypto tape resumed — fleet 39.** The owner created fleet 39 from the UI at
04:56:38Z (agent 6, `active_fleet_key user:5`, idempotency `ui-1787460998722`,
$10,005.35, risk `extreme`, scope crypto+futures+forex, 7 slots, archetype short).
The pending decision is therefore answered: **(a) restart**. The 48h Phase 1
clock for crypto restarts at the first crypto cycle, 05:03:11Z → window ends
~**2026-08-25T05:03Z**. Runs 1701 AUDUSD, 1702 ZC, 1703 EURUSD (forex/futures,
weekend-closed), 1704 DASHUSDT, 1705 LITUSDT, 1706 LINKUSDT, 1707 SOLUSDT.

First crypto cycle (05:03–05:08Z): 4 decisions, all `hold`; 3 buy proposals
(LIT, LINK, DASH) → panel final `hold` 3/3. Same shape as fleet 38's tape:
proposals exist, panel demotes every one.

**Observation to test (not a fix):** the build path logged `candidate_skipped
negative_expectancy: crypto/long is -1.31 over 109 closed runs (mean -0.01/run)`
for DASH, SOL, LINK, LIT at 04:57:5xZ, then the replacement/rotation path
(`backtest_gate context=replacement` → `rotation`) started the same four symbols
at 04:59:00–02Z. Hypothesis H-GATE-SPLIT: the agent-level negative-expectancy
gate is applied in the initial build but not in replacement rotation. Falsifier:
the replacement path consults the same gate and these passed on a different
statistic. Needs code read + replay before any change; logged for the owner.

Tripwires: image `sooppiy-backend:20260822-redesign-phase1` both containers;
0 tracebacks, 0 `desk_record`|`trading_skills` mentions (1h). No rollback
condition. No gate loosened, no fleet touched.

## Phase 1 accountability reading #7 — 2026-08-23 05:41Z

§5 (verified 2×): decisions **182** (+5), buy proposals **52** (+5), panel kept
**1** (unchanged), fills **0**, open positions **0**. P&L **$0**.
H-RECALL-FLAT 182/182 — 100%.

Fleet 39 since its first cycle (05:03Z): 9 decisions, **8 buy proposals → 0 kept
(0/8)**, all 7 runs running. Last 30 min: 5 decisions (LINK 0.57, SOL 0.55,
DASH 0.34, LIT 0.62, LINK 0.62), every one `hold` after the panel. The crypto
48h window (ends ~2026-08-25T05:03Z) is 0.6h old: too early for a verdict, but
the first 8 proposals reproduce the fleet-38 pattern exactly — 0% survival.

Fleet 37 active (weekend-idle), 38 stopped. Tripwires: image unchanged on both
containers, 0 tracebacks, 0 `desk_record`|`trading_skills` mentions (1h).
No change made. H-GATE-SPLIT (reading #6) still open, untested.

## Phase 1 accountability reading #8 — 2026-08-23 06:11Z

§5 (verified 2×): decisions **187** (+5), buy proposals **54** (+2), panel kept
**1** (unchanged), fills **0**, open positions **0**. P&L **$0**.
H-RECALL-FLAT 187/187 — 100%.

Fleet 39 (1.1h into its window): 14 decisions, **10 buy proposals → 0 kept
(0/10)**, 7/7 runs running. Last 30 min: SOL 0.35, DASH 0.71, LIT 0.48,
LINK 0.48, SOL 0.57 — all `hold` after the panel; only 2 of the 5 cycles even
produced a proposal. Note DASH at 0.71 confidence still ended `hold`.

Fleet 37 active (weekend-idle), 38 stopped. Tripwires: image unchanged, 0
tracebacks, 0 `desk_record`|`trading_skills` mentions (1h). No change made.

## Phase 1 accountability reading #9 — 2026-08-23 06:41Z

§5 (verified 2×): decisions **190** (+3), buy proposals **56** (+2), panel kept
**1** (unchanged), fills **0**, open positions **0**. P&L **$0**.
H-RECALL-FLAT 190/190 — 100%.

Fleet 39 (1.6h in): 17 decisions, **12 buy proposals → 0 kept (0/12)**, 7/7
running. Last 30 min: DASH 0.44, LIT 0.71, LINK 0.52 — all `hold` after the
panel. Second 0.71-confidence proposal (LIT, after DASH in #8) demoted.

Fleet 37 active (weekend-idle), 38 stopped. Tripwires: image unchanged, 0
tracebacks, 0 `desk_record`|`trading_skills` mentions (1h). No change made.

## Phase 1 accountability reading #10 — 2026-08-23 07:11Z

§5 (verified 2×): decisions **194** (+4), buy proposals **59** (+3), panel kept
**1** (unchanged), fills **0**, open positions **0**. P&L **$0**.
H-RECALL-FLAT 194/194 — 100%.

Fleet 39 (2.1h in): 21 decisions, **15 buy proposals → 0 kept (0/15)**, 7/7
running. Last 30 min: SOL 0.45, DASH 0.55, LIT 0.65, LINK 0.62 — all `hold`
after the panel.

Fleet 37 active (weekend-idle), 38 stopped. Tripwires: image unchanged, 0
tracebacks, 0 `desk_record`|`trading_skills` mentions (1h). No change made.

## Phase 1 accountability reading #11 — 2026-08-23 07:41Z

§5 (verified 2×): decisions **198** (+4), buy proposals **61** (+2), panel kept
**2** (+1), fills **0**, open positions **0**. P&L **$0**.
H-RECALL-FLAT 198/198 — 100%.

Fleet 39 (2.6h in): 25 decisions, **17 buy proposals → 1 "kept" (1/17)** —
and that one is not an entry. LINKUSDT run 1706 cycle 7 at 07:34:29Z:
proposed `buy` 0.55 → panel final **`sell` 0.63** (outlook bias flipped to
short, target 9.30, entry zone 11.25–11.35) → `order_params deferred/absent` →
`gate_skip stage=risk "spot sell with no inventory — treated as hold"`. This is
the identical shape to fleet 38's sole survivor (reading #3): the only
proposals the panel does not demote to hold are the ones it inverts into a
short that a spot-only run cannot execute. Real entry survival: **0/17**.

The same recall row carried `explore:true` (eps-head-fixed-v1, eps 0.25) and
still injected `skill:reachable-exits#1` at score 8.32 — exploration does not
escape H-RECALL-FLAT either.

Last 30 min: SOL 0.62, DASH 0.66, LIT 0.63 `hold`; LINK as above. Fleet 37
active (weekend-idle), 38 stopped. Tripwires: image unchanged, 0 tracebacks,
0 `desk_record`|`trading_skills` mentions (1h). No change made.

## Phase 1 accountability reading #12 — 2026-08-23 08:11Z

§5 (verified 2×): decisions **202** (+4), buy proposals **64** (+3), panel kept
**2** non-hold / **0** kept-as-buy, fills **0**, open positions **0**. P&L **$0**.
H-RECALL-FLAT 202/202 — 100%.

Fleet 39 (3.1h in): 29 decisions, **20 buy proposals → 0 real entries** (1
spot-short inversion, reading #11). Last 30 min: SOL 0.66, DASH 0.58, LIT 0.60,
LINK 0.57 — all `hold` after the panel.

Fleet 37 active (weekend-idle), 38 stopped. Tripwires: image unchanged, 0
tracebacks, 0 `desk_record`|`trading_skills` mentions (1h). No change made.

## Phase 1 accountability reading #13 — 2026-08-23 08:41Z

§5 (verified 2×): decisions **207** (+5), buy proposals **66** (+2), panel kept
**2** non-hold / **0** as buy, fills **0**, open positions **0**. P&L **$0**.
H-RECALL-FLAT 206/206 recalls carry `reachable-exits` — 100% (recall count is
one below decisions for the first time; see below).

Fleet 39 (3.6h in): 34 decisions, **22 buy proposals → 0 real entries**. Last
30 min: SOL 0.55, LIT 0.55, LINK 0.57, SOL 0.41 `hold`; **DASHUSDT cycle 8
(08:18:27Z) was a no-verdict** — `action: null, confidence: null,
conviction_missing: true, report: ""` → `gate_skip "decision is 'None'"`, and
no recall/outlook/order_discussion row was written for that cycle. Worker log
in the same window: `[Price API] Error fetching DASHUSDT (crypto): hyperliquid
cooldown active for 20.0s`. This is the no-verdict class from the 08-17
precedent; 1/34 fleet-39 cycles so far. Logged, not acted on — one data point.

Fleet 37 active (weekend-idle), 38 stopped. Tripwires: image unchanged, 0
tracebacks, 0 `desk_record`|`trading_skills` mentions (1h). No change made.

## Phase 1 accountability reading #14 — 2026-08-23 09:11Z

§5 (verified 2×): decisions **211** (+4), buy proposals **66** (+0), panel kept
**2** non-hold / **0** as buy, fills **0**, open positions **0**. P&L **$0**.
H-RECALL-FLAT 210/210 — 100%.

Fleet 39 (4.1h in): 38 decisions, **22 buy proposals → 0 real entries**. Last
30 min: DASH 0.71, LIT 0.55, LINK 0.52, SOL 0.53 — all `hold`, and for the
first time no `order_discussion` row at all (the desk itself proposed nothing
this half-hour). No new no-verdict cycle (the #13 DASH row stands at 1/38;
note `JSON_EXTRACT(...) IS NULL` does not count it — JSON null ≠ SQL NULL; use
`JSON_TYPE(...)='NULL'`).

Fleet 37 active (weekend-idle), 38 stopped. Tripwires: image unchanged, 0
tracebacks, 0 `desk_record`|`trading_skills` mentions (1h). No change made.

## Phase 1 accountability reading #15 — 2026-08-23 09:41Z

§5 (verified 2×): decisions **215** (+4), buy proposals **66** (+0), panel kept
**2** non-hold / **0** as buy, fills **0**, open positions **0**. P&L **$0**.
H-RECALL-FLAT 214/214 — 100%. No-verdict cycles (JSON_TYPE='NULL'): **1**.

Fleet 39 (4.6h in): 42 decisions, **22 buy proposals → 0 real entries**. Second
consecutive half-hour with no proposal at all: DASH 0.73, LIT 0.55, LINK 0.47,
SOL 0.53 — all `hold`. DASH's own confidence has drifted 0.34→0.71→0.73 across
the morning without ever producing a proposal the panel kept.

Fleet 37 active (weekend-idle), 38 stopped. Tripwires: image unchanged, 0
tracebacks, 0 `desk_record`|`trading_skills` mentions (1h). No change made.

## Phase 1 accountability reading #16 — 2026-08-23 10:11Z

§5 (verified 2×): decisions **219** (+4), buy proposals **67** (+1), panel kept
**2** non-hold / **0** as buy, fills **0**, open positions **0**. P&L **$0**.
H-RECALL-FLAT 218/218 — 100%. No-verdict 1; `verdict_salvaged` 8 in window.

Fleet 39 (5.1h in): 46 decisions, **23 buy proposals → 0 real entries**. The one
new proposal — DASHUSDT cycle 11, 09:50:27Z — was the strongest of the day:
proposed `buy` **0.74** → panel final `hold` 0.62 (conviction 0.45, entry_quality
0.30; outlook adopted "standing flat bias"). The preceding `verdict_salvaged`
(truncated at 967 chars, tail "…we take the trade now … We buy at market,
setting a 2.4% stop") is the first LLM attempt, not the cause of the demotion;
the completed verdict is the one the panel demoted.

**Structural: idle-retire is draining the crypto slots.** At ~5h flat the
platform retired LINKUSDT (10:03:04Z) and SOLUSDT (10:10:31Z) as
`idle_retired`; the replacement rotation drew **SI** (run 1708) and **HG**
(run 1709) — both futures, both weekend-closed. Fleet 39 is now 2 crypto
(DASH, LIT) + 2 forex + 3 futures; only the 2 crypto runs can decide before
Monday. If DASH/LIT retire on the same clock (~10:00Z + their own idle
timers), the crypto tape ends again — this time by the platform's own rule,
not the user. The Phase 1 crypto window (ends ~2026-08-25T05:03Z) would then
measure nothing. Logged for the owner; no fleet touched.

Fleet 37 active (weekend-idle), 38 stopped. Tripwires: image unchanged, 0
tracebacks, 0 `desk_record`|`trading_skills` mentions (1h). No change made.

## Phase 1 accountability reading #17 — 2026-08-23 10:41Z

**P&L $0 — fills 0, positions 0 (both query forms).** §5 since 10:36Z: decisions 224 (+5), buy proposals 68 (+1), panel kept 2 non-hold / 0 as buy. All 86 panels crypto. Last 30 min: 5 decisions (all hold; 1710 LTC 0.38 ×2, 1704 DASH 0.62, 1705 LIT 0.60, 1711 ASTER 0.58), 1 panel (ASTER buy 0.58 → hold 0.58). H-RECALL-FLAT 223/223 (0 without). no-verdict 1, salvaged 8.

Fleet 39: LIT (1705) idle-retired; replacement ASTERUSDT (1711, crypto/long — the H-GATE-SPLIT recurrence) at 10:26Z. Crypto slots now LTC (1710) + ASTER (1711); SI/HG/ZC/AUDUSD/EURUSD closed until 21:00–22:00Z. Status still "replenishing:7/25" (phantom, H-AUTOTUNE-UNFUNDABLE). Fleet 37 active (weekend-idle), 38 stopped (user); owner decision on the 38 crypto leg still pending.

Tripwires clean: image `20260822-redesign-phase1` both containers, 0 tracebacks. Cause of the flat metric is documented in [2026-08-23-deep-analysis-24h.md](2026-08-23-deep-analysis-24h.md) (PR #545): the record line was not the binding channel. Nothing changed.

## Phase 1 accountability reading #18 — 2026-08-23 11:11Z (quiet)

**P&L $0 — fills 0, positions 0 (both forms).** §5: decisions 227 (+3), buy proposals 68 (+0), panel kept 2 non-hold / 0 as buy; all 86 panels crypto. Last 30 min: 3 decisions, all hold, no panel (1711 ASTER 0.58/0.48, 1710 LTC 0.53). H-RECALL-FLAT 226/226. Fleet 39 unchanged (7 running: LTC, ASTER + 5 weekend-closed); 38 stopped, owner decision pending; 37 active idle. Image `20260822-redesign-phase1`, 0 tracebacks. Nothing changed.

## Phase 1 accountability reading #19 — 2026-08-23 11:41Z (quiet)

**P&L $0 — fills 0, positions 0 (both forms).** §5: decisions 229 (+2), buy proposals 68 (+0), panel kept 2 non-hold / 0 as buy; all 86 panels crypto. Last 30 min: 2 holds (LTC 0.45, ASTER 0.55), no panel. H-RECALL-FLAT 228/228. Fleet 39 unchanged (LTC, ASTER + 5 weekend-closed); 38 stopped, owner decision pending; 37 active idle. Image `20260822-redesign-phase1`, 0 tracebacks. Nothing changed.

## Phase 1 accountability reading #20 — 2026-08-23 12:21Z — FIRST FILL, −$0.58

**P&L −$0.58 net (pnl_audit ledger −0.58, adapt −0.34, delta = open fee, check ok). Fills 2 (1 round trip), positions 0.** §5: decisions 231 (+2), buy proposals 68 (+0), panel kept 3 non-hold / 0 as buy; 87 panels, all crypto. H-RECALL-FLAT 230/230. Tripwires clean (image unchanged, 0 tracebacks).

**The trade (run 1710 LTCUSDT, fleet 39, short archetype):** cycle 5 12:03:03Z desk `sell` 0.53 → panel `sell` 0.66 (first kept non-hold that was actionable). `order_params` **absent** (no order block at all, all 5 cycles) → `null_size_cap` 0.25 × 704.47 = $176 margin, 3× = $529 notional; short 10.108 @ 52.35 (+0.15% drift vs 52.27 mark). Peak +$1.78 net at 12:09Z (low 52.05 on tape). `breakeven_ratchet` fired 12:19:18Z at total −$0.34, cover @ 52.36. Fees $0.476 round trip (0.00045/leg, FEE_PER_MARKET). Replacement CRVUSDT (1712, crypto/short thesis) 4 s later via the per-symbol backtest_gate; bucket gate not involved (build-only).

**Two-agent analysis, cross-checked:**
- *AI-authored (A):* the thesis was the code-authored daily-RSI label (`quant_crypto.py:238`, RSI 76.3 "≥70 sell trigger"); sentiment/news/macro all bullish; 1h RSI 54.9. The desk's "desk memory warns of squeeze risk" is NOT supported by what was recalled (both chunks `skill:reachable-exits`). The desk authored no bracket; its outlook target 50.5 (−3.5%) vs invalidation 52.50 (+0.29%) sat inside 1m noise. Price dipped 0.57% then reversed through the fill; neither target nor invalidation touched; holding to now = net −$0.75 (n=1).
- *Algorithm-authored (B):* arm = qty×mark×0.001×2 = $1.0585 (legacy rate, 2.2× the real round trip); fire = `total − base ≤ round_trip_fee` (run_engine.py:1018-1031) → lock at total +$0.24, best case $0 net. The mark refreshes only every `POSITION_REFRESH_INTERVAL=300` s (prod env confirmed; equity polled every ~64 s but 4 distinct prices in 16 min). Last mark before the fire +$1.12 (cushion $0.88 = 0.17%); LTC moved +0.28% in the next 5 min; the rail first saw price $0.58 below its lock. A tick-level lock → ≈ $0 net, NOT a winner: the only profit lock (`trail.activate_usd` 28.18 = max_loss) is 14× the peak — memory "trail never arms" applies.
- *Cross-check:* no disagreement. Main-session verification: firing condition read in code; `POSITION_REFRESH_INTERVAL=300` on the worker; mark sequence reproduced (0.576×6, 2.02×5, 1.354×5, −0.10).

**Reason (one sentence):** a code-labelled daily-overbought short with no authored bracket dipped 0.57% and reversed; the breakeven rail, evaluated on a 5-minute mark, could not hold $0 against a 0.28% five-minute move, and no rail existed that could have banked the +$1.78.

**Verdict:** loss, small, and structural — not bad luck. Three items for Plan 28 (not shipped, experiments first): (i) breakeven rail needs a price-level lock or a faster mark for open positions — the $0.58 is the poll-granularity cost, n=1; (ii) `absent` order params on the light route × 5/5 cycles — the desk is not emitting the order block on gpt-oss:120b; (iii) arm rate 0.001 vs floor rate 0.00045 inconsistency. Phase 1 metric (crypto *entries*): still 0 kept buys; the one fill is a short. Fleet 38 owner decision pending. Nothing changed.

## Phase 1 accountability reading #21 — 2026-08-23 12:41Z (quiet)

**P&L unchanged −$0.58 — no new fills (§5 fills still 2 = the 1710 round trip), positions 0 (both forms).** §5: decisions 233 (+2), buy proposals 68 (+0), panel kept 3 non-hold / 0 as buy; 88 panels, all crypto. Last 30 min: CRV 1712 cycle 1 proposed `sell` 0.58 → panel `hold` 0.45; ASTER 1711 hold 0.53. The `trade`/`stop_mechanism`/`adapt` rows in the window are the 12:19Z cover already analyzed in #20. H-RECALL-FLAT 232/232. Fleet 39 unchanged (ASTER, CRV + 5 weekend-closed); 38 stopped, owner decision pending; 37 active idle. Image `20260822-redesign-phase1`, 0 tracebacks. Nothing changed.

## Phase 1 accountability reading #22 — 2026-08-23 13:11Z (quiet)

**P&L unchanged −$0.58 — no new fills, positions 0 (both forms).** §5: decisions 235 (+2), buy proposals 69 (+1), panel kept 3 non-hold / 0 as buy; 89 panels, all crypto. Last 30 min: ASTER 1711 proposed `buy` 0.55 → panel `hold` 0.62 (demotion #69, same class); CRV 1712 hold 0.55. H-RECALL-FLAT 234/234. Fleet 39 unchanged; 38 stopped, owner decision pending; 37 active idle. Image `20260822-redesign-phase1`, 0 tracebacks. Nothing changed.

## Phase 1 accountability reading #23 — 2026-08-23 13:41Z (quiet)

**P&L unchanged −$0.58 — no new fills, positions 0 (both forms).** §5: decisions 237 (+2), buy proposals 69 (+0), panel kept 3 non-hold / 0 as buy; 89 panels, all crypto. Last 30 min: 2 holds (CRV 0.48, ASTER 0.46), no panel. H-RECALL-FLAT 236/236. Fleet 39 unchanged; 38 stopped, owner decision pending; 37 active idle. Image `20260822-redesign-phase1`, 0 tracebacks. Nothing changed.

## Phase 1 accountability reading #24 — 2026-08-23 14:11Z (quiet)

**P&L unchanged −$0.58 — no new fills, positions 0 (both forms).** §5: decisions 239 (+2), buy proposals 69 (+0), panel kept 3 non-hold / 0 as buy; 90 panels, all crypto. Last 30 min: CRV 1712 proposed `sell` 0.55 → panel `hold` 0.34 (a short demoted this time); ASTER hold 0.45. H-RECALL-FLAT 238/238. Fleet 39 unchanged; 38 stopped, owner decision pending; 37 active idle. Image `20260822-redesign-phase1`, 0 tracebacks. Nothing changed.

## Phase 1 accountability reading #25 — 2026-08-23 14:41Z (quiet)

**P&L unchanged −$0.58 — no new fills, positions 0 (both forms).** §5: decisions 241 (+2), buy proposals 69 (+0), panel kept 3 non-hold / 0 as buy; 90 panels, all crypto. Last 30 min: 2 holds (CRV 0.45, ASTER 0.54), no panel. H-RECALL-FLAT 240/240. Fleet 39 unchanged; 38 stopped, owner decision pending; 37 active idle. Image `20260822-redesign-phase1`, 0 tracebacks. Nothing changed.

## Phase 1 accountability reading #26 — 2026-08-23 15:11Z (quiet)

**P&L unchanged −$0.58 — no new fills, positions 0 (both forms).** §5: decisions 243 (+2), buy proposals 69 (+0), panel kept 3 non-hold / 0 as buy; 90 panels, all crypto. Last 30 min: CRV 1712 cycle at 14:45Z returned an EMPTY LLM response (`no_verdict {kind: empty, chars: 0}` → hold 0.0; known class since 08-17, 42 lifetime, 2nd in this window); ASTER hold 0.48. H-RECALL-FLAT 242/242. Fleet 39 unchanged; 38 stopped, owner decision pending; 37 active idle. Image `20260822-redesign-phase1`, 0 tracebacks. Nothing changed.

## Phase 1 accountability reading #27 — 2026-08-23 15:41Z

**P&L unchanged −$0.58 — no new fills, positions 0 (both forms).** §5: decisions 246 (+3), buy proposals 70 (+1), panel kept 3 non-hold / 0 as buy; 91 panels, all crypto. Last 30 min: ASTER 1711 `idle_retired` 15:38:15Z (12 cycles, 0 kept) → replacement DOTUSDT 1714 15:38:33Z, whose first cycle proposed `buy` 0.60 → panel `hold` 0.62 (demotion #70, same class). CRV hold 0.55. Run 1713 USDTRY (forex, 15:21Z) belongs to another fleet (not 39). H-RECALL-FLAT 245/245. Fleet 39: CRV + DOT crypto, 5 weekend-closed; 38 stopped, owner decision pending; 37 active. Image `20260822-redesign-phase1`, 0 tracebacks. Nothing changed.

## Phase 1 accountability reading #28 — 2026-08-23 16:11Z — second fill, −$0.51; day −$1.08

**P&L −$1.08 net for the window (pnl_audit ledger −1.08 / adapt −0.61, check ok; 2 round trips). Fills 4, positions 0.** §5: decisions 248 (+2), buy proposals 70 (+0), panel kept 4 non-hold / 0 as buy; 92 panels, all crypto. H-RECALL-FLAT 247/247. Tripwires clean (image unchanged, 0 tracebacks).

**The trade (run 1712 CRVUSDT short, fleet 39):** cycle 8 15:46:22Z desk `sell` 0.57 → panel `sell` 0.58; `order_params` absent (8/8 cycles) → null_size_cap $176 margin, 3× → short 1,584.81 @ 0.3335 ($528). House bracket SL 0.3499 / TP 0.2999; `at_time` 00:19Z. One 300-s mark at 16:09:15Z showed +$1.08 unrealized → breakeven ratchet ARMED (arm $1.055, cushion to lock **0.114%**); next mark 16:14:02Z at 0.33352 (+0.21%) → fired at total −$0.27, cover @ 0.33352. Realized **−$0.507** (gross −$0.03, fees $0.476). Replacement ZROUSDT 1716 at 16:14:09Z.

**Two-agent analysis, cross-checked (no disagreement):**
- *AI-authored (A):* "RSI 78.8" is the DAILY RSI (`quant_crypto.py:150-154`, OKX `bar=1D`); 1h RSI was 53.8, 5m 43 — intraday neutral. The only input that changed between the two demotions (cycles 1, 4) and the accepted cycle 8 was price (−1.7% retrace), which lifted the panel's own entry_quality 0.30→0.71. "Desk memory warns…" = the panel's own cycle-1/4 CRV distillations echoed back via `analysis_memory.memory_block` (`analysis_agents.py:852`) — not independent evidence, not the `recall` chunks. Cycle 7's objection (target unreachable before `at_time`) was dropped in cycle 8 without reason ("revised"). The prose "$0.34 stop / $0.32 target" was never on the book.
- *Algorithm-authored (B):* rails at entry: ratchet (tightest by ~2 orders), max_loss 28.16 (≈0.3511), 0.7 brake (≈0.3458, cycle-only), SL 0.3499, trail 28.16 inert, at_time. Arm scales with the CURRENT mark (`_breakeven_arm_usd`, run_engine.py:890-920) — above 0.34001 the rail would have UN-armed (quirk). Hyperliquid 5m, 14:15–16:10Z: **24/24** candles had a range > the 0.114% cushion; median 5-min range 0.60% ≈ 5× cushion. The floor could only ever be crossed by a margin, never touched.
- *Cross-check:* fire event, cover trade and `realized_pnl_usd −0.5074` verified on prod; my earlier "16:08 spike" reading was the lagged mark — actual high 0.33581 at 15:53Z (A).

**Reason (one sentence):** a daily-RSI label short, accepted on its third proposal only because price had retraced enough to raise the panel's own score, was closed by a breakeven rail whose 0.11% cushion on 300-s marks is a fifth of CRV's median 5-minute bar — so a one-sample paper peak became a guaranteed net loss while the short thesis itself was never tested.

**Verdict:** −$1.08 on the day, two trades, both losses, **both authored by the same rail**, not by price. The Phase 1 crypto-entry metric remains 0 kept buys; both fills were shorts on a short-archetype fleet. Plan 28 additions: (i) the breakeven ratchet on 300-s marks is now reproduced twice today (n=2) — price-level lock or sub-minute marks for open positions, experiment first; (ii) `absent` order block 13/13 cycles on the light route today; (iii) arm rate 0.001 vs floor 0.00045, and arm scaling with mark. Fleet 38 owner decision pending. Nothing changed.

## Phase 1 accountability reading #29 — 2026-08-23 16:41Z

**P&L unchanged −$1.08 — no new fills (§5 fills 4 = the two round trips), positions 0 (both forms).** §5: decisions 250 (+2), buy proposals 72 (+2), panel kept 6 non-hold / 0 as buy; 94 panels, all crypto. Last 30 min: two buy→`sell` INVERSIONS on spot/long runs — ZRO 1716 cycle 1 desk `buy` 0.58 → panel `sell` 0.66; DOT 1714 cycle 3 desk `buy` **0.71** → panel `sell` 0.62 — both `gate_skip "spot sell with no inventory — treated as hold"`. Kept-non-hold count (6) now overstates actionable keeps: 2 fills + 4 unactionable spot-sell inversions. Note: on both cycles `order_params` were `parsed` (ZRO stop 1.25%/target 2.5%; DOT 2.1%/4.5%, trail 2.1/0.2) — `absent` is not universal on the light route; it occurred on the two cycles that filled (1710 c5, 1712 c8). H-RECALL-FLAT 249/249. Fleet 39: DOT + ZRO crypto, 5 weekend-closed (forex opens 21:00Z, CME 22:00Z); 38 stopped, owner decision pending; 37 active. Image `20260822-redesign-phase1`, 0 tracebacks. Nothing changed.

## Phase 1 accountability reading #30 — 2026-08-23 17:11Z (quiet)

**P&L unchanged −$1.08 — no new fills, positions 0 (both forms).** §5: decisions 252 (+2), buy proposals 72 (+0), panel kept 6 non-hold / 0 as buy; 94 panels, all crypto. Last 30 min: 2 holds (ZRO 0.60, DOT 0.58), no panel. H-RECALL-FLAT 251/251. Fleet 39 unchanged; 38 stopped, owner decision pending; 37 active. Image `20260822-redesign-phase1`, 0 tracebacks. Nothing changed.

## Phase 1 accountability reading #31 — 2026-08-23 17:41Z (quiet)

**P&L unchanged −$1.08 — no new fills, positions 0 (both forms).** §5: decisions 254 (+2), buy proposals 73 (+1), panel kept 6 non-hold / 0 as buy; 95 panels, all crypto. Last 30 min: DOT 1714 desk `buy` **0.76** (highest proposal of the window after DASH 0.86) → panel `hold` 0.62 (demotion #73 of 73 long proposals); ZRO hold 0.47. H-RECALL-FLAT 253/253. Fleet 39 unchanged; 38 stopped, owner decision pending; 37 active. Image `20260822-redesign-phase1`, 0 tracebacks. Nothing changed.

## Phase 1 accountability reading #32 — 2026-08-23 18:11Z (quiet)

**P&L unchanged −$1.08 — no new fills, positions 0 (both forms).** §5: decisions 256 (+2), buy proposals 74 (+1), panel kept 6 non-hold / 0 as buy; 96 panels, all crypto. Last 30 min: DOT 1714 desk `buy` 0.63 → panel `hold` 0.44 (74/74 long proposals demoted); ZRO hold 0.48. H-RECALL-FLAT 255/255. Fleet 39 unchanged; 38 stopped, owner decision pending; 37 active. Image `20260822-redesign-phase1`, 0 tracebacks. Nothing changed.

## Phase 1 accountability reading #33 — 2026-08-23 18:41Z (quiet)

**P&L unchanged −$1.08 — no new fills, positions 0 (both forms).** §5: decisions 258 (+2), buy proposals 75 (+1), panel kept 6 non-hold / 0 as buy; 97 panels, all crypto. Last 30 min: DOT 1714 desk `buy` 0.62 → panel `hold` 0.58 (75/75 long proposals demoted; DOT has proposed buy on 4 consecutive panels — 0.71, 0.76, 0.63, 0.62 — all demoted); ZRO hold 0.62. H-RECALL-FLAT 257/257. Fleet 39 unchanged; 38 stopped, owner decision pending; 37 active. Image `20260822-redesign-phase1`, 0 tracebacks. Nothing changed.

## Phase 1 accountability reading #34 — 2026-08-23 19:11Z (quiet)

**P&L unchanged −$1.08 — no new fills, positions 0 (both forms).** §5: decisions 260 (+2), buy proposals 76 (+1), panel kept 6 non-hold / 0 as buy; 98 panels, all crypto. Last 30 min: DOT 1714 desk `buy` 0.62 → panel `hold` 0.62 (5th consecutive DOT buy demoted; 76/76); ZRO hold 0.60. H-RECALL-FLAT 259/259. Fleet 39 unchanged; 38 stopped, owner decision pending; 37 active. Image `20260822-redesign-phase1`, 0 tracebacks. Nothing changed.

## Phase 1 accountability reading #35 — 2026-08-23 19:41Z (quiet)

**P&L unchanged −$1.08 — no new fills, positions 0 (both forms).** §5: decisions 262 (+2), buy proposals 76 (+0), panel kept 6 non-hold / 0 as buy; 98 panels, all crypto. Last 30 min: 2 holds (ZRO 0.48, DOT 0.38), no panel. H-RECALL-FLAT 261/261. Fleet 39 unchanged; forex/CME slots reopen 21:00–22:00Z. 38 stopped, owner decision pending; 37 active. Image `20260822-redesign-phase1`, 0 tracebacks. Nothing changed.

## Phase 1 accountability reading #36 — 2026-08-23 20:11Z (quiet)

**P&L unchanged −$1.08 — no new fills, positions 0 (both forms).** §5: decisions 264 (+2), buy proposals 76 (+0), panel kept 6 non-hold / 0 as buy; 98 panels, all crypto. Last 30 min: 2 holds (ZRO 0.53, DOT 0.56), no panel. H-RECALL-FLAT 263/263. Fleet 39 unchanged; forex opens 21:00Z, CME 22:00Z. 38 stopped, owner decision pending; 37 active. Image `20260822-redesign-phase1`, 0 tracebacks. Nothing changed.

## Phase 1 accountability reading #37 — 2026-08-23 20:41Z (quiet)

**P&L unchanged −$1.08 — no new fills, positions 0 (both forms).** §5: decisions 266 (+2), buy proposals 78 (+2), panel kept 6 non-hold / 0 as buy; 100 panels, all crypto. Last 30 min: ZRO desk `buy` 0.63 → panel `hold` 0.45; DOT desk `buy` 0.67 (6th consecutive DOT buy) → panel `hold` 0.58 — 78/78 long proposals demoted. H-RECALL-FLAT 265/265. Fleet 39 unchanged; forex slots reopen 21:00Z, CME 22:00Z. 38 stopped, owner decision pending; 37 active. Image `20260822-redesign-phase1`, 0 tracebacks. Nothing changed.

## Phase 1 accountability reading #38 — 2026-08-23 21:11Z — forex open

**P&L unchanged −$1.08 — no new fills, positions 0 (both forms).** §5: decisions 279 (+13), buy proposals 78 (+0), panel kept 6 non-hold / 0 as buy; 100 panels, all crypto. Forex opened 21:00Z: 11 forex/fleet-37 runs cycled (all `hold` 0.38–0.58; one `retire` 1666). DOT 1714 `idle_retired` 20:59:12Z after 6 straight demoted buys (0.71/0.76/0.63/0.62/0.62/0.67) — the panel refused the symbol 6 times, then the platform benched it 12h; replacement NZDJPY 1717 (forex). Fleet 39 crypto is down to ZRO alone. H-RECALL-FLAT 278/278. 38 stopped, owner decision pending; 37 active and now live-market. Image `20260822-redesign-phase1`, 0 tracebacks. Nothing changed.

## Phase 1 accountability reading #39 — 2026-08-23 21:41Z (quiet)

**P&L unchanged −$1.08 — no new fills, positions 0 (both forms).** §5: decisions 293 (+14), buy proposals 78 (+0), panel kept 6 non-hold / 0 as buy; 100 panels, all crypto. Forex session active: 14 decisions in 30 min across fleet-37 forex runs + fleet-39 (AUD 0.62, EUR 0.44, NZDJPY 0.58, USDTRY 0.55, ZRO 0.30) — all hold, no panels, no proposals. H-RECALL-FLAT 292/292. Fleet 39 unchanged (ZRO sole crypto); 38 stopped, owner decision pending; 37 active. Image `20260822-redesign-phase1`, 0 tracebacks. Nothing changed.

## Phase 1 accountability reading #40 — 2026-08-23 22:11Z — CME open

**P&L unchanged −$1.08 — no new fills, positions 0 (both forms).** §5: decisions 308 (+15), buy proposals 79 (+1), panel kept 6 non-hold / 0 as buy; panels now 100 crypto + **1 futures**. CME opened 22:00Z: SI 1708 first cycle proposed `buy` **0.77** → panel `hold` 0.34 — the first futures panel of the window, demoted (note: research/06 measured futures demotions as RIGHT — 0/73 targets reached — so this is the market where the panel's caution is evidence-backed). ZRO 1716 idle-retired → FILUSDT 1720. 15 decisions in 30 min (forex+futures+crypto), all hold. H-RECALL-FLAT 307/307. 38 stopped, owner decision pending; 37 active. Image `20260822-redesign-phase1`, 0 tracebacks. Nothing changed.

## Phase 1 accountability reading #41 — 2026-08-23 22:41Z

**P&L unchanged −$1.08 — no new fills, positions 0 (both forms).** §5: decisions 324 (+16), buy proposals 79 (+0), panel kept 6 non-hold / 0 as buy; panels 102 crypto + 1 futures. **H-RECALL-FLAT first exception: 322/323.** The one non-reachable-exits recall (ZC 1702 cycle 37, 22:17:00Z) was an ε-greedy EXPLORATION draw (explore:true, propensity 0.083) that surfaced `skill:measured-entry-record#2` — the Phase 1 skill's first appearance in any desk prompt in the window, and only via exploration; the deterministic head has still picked reachable-exits 322/322. This is live confirmation of Plan 28's recall-ranking diagnosis (pooled IDF buries the new skill; only the explore arm can reach it). Other movement: EURUSD 1703 `desk_retired` 22:12Z; SOLUSDT 1721 new crypto slot (2 sell proposals → hold). Fleet 39 now FIL + SOL crypto, 2 forex, 3 futures. 38 stopped, owner decision pending; 37 active. Image `20260822-redesign-phase1`, 0 tracebacks. Nothing changed.

## Phase 1 accountability reading #42 — 2026-08-23 23:11Z (quiet)

**P&L unchanged −$1.08 — no new fills, positions 0 (both forms).** §5: decisions 336 (+12), buy proposals 80 (+1), panel kept 6 non-hold / 0 as buy; panels 103 crypto + 1 futures + 1 forex. Last 30 min: SOL 1721 `sell` 0.58 → hold 0.66; NZDUSD 1715 first FOREX buy proposal of the window (`buy` 0.54 → hold 0.45, 80/80 demoted — note forex demotions are measured RIGHT in research/06, 21/41 hit their own stop). H-RECALL-FLAT 334/335 (the one exception remains the 22:17Z exploration draw). Fleet 39 unchanged; 38 stopped, owner decision pending; 37 active. Image `20260822-redesign-phase1`, 0 tracebacks. Nothing changed.

## Phase 1 accountability reading #43 — 2026-08-23 23:41Z — third fill, −$0.14; day −$1.22

**P&L −$1.22 net for the window (pnl_audit ledger −1.22 / adapt −0.53, check ok; 3 round trips). Fills 6, positions 0.** §5: decisions 348 (+12), buy proposals 80 (+0), panel kept 7 non-hold / 0 as buy. H-RECALL-FLAT 344/347 — all 3 exceptions are ε-greedy exploration draws (22:17Z ZC surfaced measured-entry-record#2; 23:23Z HG and 23:36Z ZC drew reentry-discipline#5 heads). Tripwires clean.

**The trade (run 1721 SOLUSDT short, fleet 39):** cycle 4 23:19:32Z desk `sell` 0.60 → panel `sell` 0.68. This time the desk DID author a bracket (`parsed`: stop 2.8%≈98.23, target 5.6%≈90.21, trail arm 3%=$14.54, horizon 24h). Short 5.085 @ 95.559 ($486). Peak (polled) +$1.007 armed the ratchet (arm $0.9713); fired 23:29:49Z at total +$0.081 → cover 95.50. Gross **+$0.30**, fees $0.437 → net **−$0.137**. Closed at minute 10 of a 24h plan. Replacement TRUMPUSDT 1723.

**Two-agent analysis, cross-checked (one briefing correction accepted: CRV's arm margin $0.021 was the day's tightest):**
- *AI (A):* daily RSI 83–84 vs 1h 55.7–59.8 — third consecutive daily-label short (LTC 74.9/54.9, CRV 75.8/53.8). Four essentially identical sell proposals; cycle 4 accepted not on new information but on the panel re-scoring its own entry_quality 0.10→0.70 / momentum 0.30→0.80 after a 0.25% dip (CRV self-approval pattern); the verdict was salvaged from a truncated LLM output. Post-cover the authored bracket has touched neither leg; held-to-now +$1.31 net but 23.5h of horizon remain — unresolved. The ratchet also dodged a 95.92 pop 2 min after cover, so "the rail cost money" is not provable on this leg.
- *Algorithm (B), n=3 table:* every arm today was on a fee-scale peak (excursion/arm 1.91×, 1.02×, 1.26×); every fire landed below its lock; **net = −overshoot to 4 decimals in all three** — the loss IS the 64 s-poll/300 s-mark discretization. Counterfactual (a) tick-evaluated lock ≈ $0.00 vs −$1.22. Counterfactual (b) no ratchet, walked per-bracket: LTC RESOLVED **−$2.30** (ratchet saved $1.72), CRV +$4.28 unresolved, SOL +$1.46 unresolved — removal is NOT uniformly better; the clean fix is evaluation cadence. The ratchet runs regardless of an authored trail (SOL's own trail sat 15× higher), has no per-run disable, kill switch `BREAKEVEN_RATCHET` unset on prod (ON at defaults). A adds: the peak tracker itself is stale — tick peak +$2.33 recorded as +$1.01.

**Reason (one sentence):** the desk's fourth identical daily-RSI short self-approved on a 0.25% dip and was then closed at minute 10 of a 24-hour plan by a fee-anchored rail whose polling cadence structurally converts its $0-floor into −overshoot — for the third time today.

**Verdict:** day −$1.22, three trades, three losses, all authored by the ratchet's discretization, not by any thesis (the one resolvable no-ratchet counterfactual was WORSE). n=3 upgrade for Plan 28's rail item: the experiment should target tick/faster lock evaluation, not removal. Phase 1 crypto-entry metric: still 0 kept buys (80/80 demoted). Fleet 38 owner decision pending. Nothing changed.

## Phase 1 accountability reading #44 — 2026-08-24 00:11Z (quiet)

**P&L unchanged −$1.22 — no new fills (§5 fills 6 = the three round trips), positions 0 (both forms).** §5: decisions 362 (+14), buy proposals 80 (+0), panel kept 7 non-hold / 0 as buy; panels 104 crypto + 1 futures + 1 forex. Last 30 min: 14 decisions, all hold, no panels. H-RECALL-FLAT 358/361 (3 exploration exceptions unchanged). Fleet 39 unchanged (FIL, TRUMP crypto); 38 stopped, owner decision pending; 37 active. Image `20260822-redesign-phase1`, 0 tracebacks. Nothing changed.

## Phase 1 accountability reading #45 — 2026-08-24 00:41Z (quiet)

**P&L unchanged −$1.22 — no new fills, positions 0 (both forms).** §5: decisions 373 (+11), buy proposals 80 (+0), panel kept 7 non-hold / 0 as buy; panels 105 crypto + 1 futures + 1 forex. Last 30 min: TRUMP 1723 `sell` 0.49 → panel `hold` 0.57; rest hold. H-RECALL-FLAT 369/372 (3 exploration exceptions). Fleet 39 unchanged; 38 stopped, owner decision pending; 37 active. Image `20260822-redesign-phase1`, 0 tracebacks. Nothing changed.

## Phase 1 accountability reading #46 — 2026-08-24 01:11Z (quiet)

**P&L unchanged −$1.22 — no new fills, positions 0 (both forms).** §5: decisions 385 (+12), buy proposals 81 (+1), panel kept 7 non-hold / 0 as buy; panels 106 crypto + 1 futures + 1 forex. Last 30 min: FIL 1720 desk `buy` 0.57 → panel `hold` 0.58 (81/81 long proposals demoted). H-RECALL-FLAT 381/384. Fleet 39 unchanged; 38 stopped, owner decision pending; 37 active. Image `20260822-redesign-phase1`, 0 tracebacks. Nothing changed.

## Phase 1 accountability reading #47 — 2026-08-24 01:41Z (quiet)

**P&L unchanged −$1.22 — no new fills, positions 0 (both forms).** §5: decisions 397 (+12), buy proposals 81 (+0), panel kept 7 non-hold / 0 as buy; panels 106 crypto + 1 futures + 1 forex. Last 30 min: 12 decisions, all hold, no panels. H-RECALL-FLAT 393/396. Fleet 39 unchanged; 38 stopped, owner decision pending; 37 active. Image `20260822-redesign-phase1`, 0 tracebacks. Nothing changed.

## Phase 1 accountability reading #48 — 2026-08-24 02:11Z (quiet)

**P&L unchanged −$1.22 — no new fills, positions 0 (both forms).** §5: decisions 409 (+12), buy proposals 82 (+1), panel kept 7 non-hold / 0 as buy; panels 108 crypto + 1 futures + 1 forex. Last 30 min: FIL `buy` 0.58 → `hold` 0.44 (82/82 demoted); TRUMP `sell` 0.52 → `hold` 0.58; 1 verdict_salvaged. Two `alert`/run_status pairs = fleet-37 forex rotations, no fills. H-RECALL-FLAT 405/408. Fleet 39 unchanged; 38 stopped, owner decision pending; 37 active. Image `20260822-redesign-phase1`, 0 tracebacks. Nothing changed.

## Phase 1 accountability reading #49 — 2026-08-24 02:41Z (quiet)

**P&L unchanged −$1.22 — no new fills, positions 0 (both forms).** §5: decisions 426 (+17), buy proposals 82 (+0), panel kept 7 non-hold / 0 as buy; panels 109 crypto + 1 futures + 1 forex. Last 30 min: TRUMP `sell` 0.65 → `hold` 0.57; rest hold. Idle-retire continues on the ~5h clock: NZDJPY (02:19:56Z) and AUDUSD (02:28:25Z) out → UNIUSDT 1728 (crypto back to 3 slots) and AUDCAD 1731 in. H-RECALL-FLAT 421/425 (4th exception = another ZC exploration draw 02:35Z). Fleet 38 stopped, owner decision pending; 37 active. Image `20260822-redesign-phase1`, 0 tracebacks. Nothing changed.

## Phase 1 accountability reading #50 — 2026-08-24 02:47Z — SESSION TAKEOVER; new cadence (OWNER: hourly, 3 agents)

**OWNER ORDER (2026-08-24 ~02:45Z, verbatim): "always monitoring with 3 agents each a hours (not 30 min)."** This session takes over the stack from reading #49. Cadence is now HOURLY; every cycle dispatches THREE subagents — A: AI-authored tape, B: algorithm-authored tape, C: profit-solution assessment — then the main session cross-checks all three (owner law §7e). This reading covers ts > 01:41Z (~75 min, overlapping #48–#49 for takeover continuity).

**P&L unchanged −$1.22 — no new fills (signals window count 0; 48h total 6 = the three ratchet round trips), positions 0 (both forms; pnl_audit ledger −1.22 / adapt −0.53, fee-asym −0.69, residual $0.00, 71/71 validated).** §5: decisions 427, buy proposals 82 (+0), panel kept 7 non-hold / **0 as buy** — all 7 kept are sells, latest 08-23 23:19Z. Phase 1 crypto-entry metric unchanged at **0 kept buys / 82 proposals**; the window ends 10:36Z today and the 0→0 verdict is already decisive.

**Agent A (AI tape):** 30 decisions (29 hold, 1 retire), 3 proposals all demoted. FIL 1720 `buy` 0.58 → hold 0.44 (under 200-day MA, long-short 2.91 crowded-long — "no confident entry point"). TRUMP 1723 shorted twice in 27 min — `sell` 0.52 → hold 0.58, then `sell` 0.65 → hold 0.57 WITH a complete authored bracket (entry 2.563 / stop 2.66 / target 2.36, R:R≈2.1); the second demotion's own reasoning ("a short-term correction may precede further upside") is directionally the short's thesis — **track TRUMPUSDT forward price from 2.563 in later readings to score the panel**. AVAX 1730 desk-`retire` 0.55 at cycle 1, 40s after build ("a proper risk-reward bracket cannot be constructed for the long read"). Both TRUMP verdicts were salvaged from ~1KB truncations (action preserved, panel reasoning lost). All routes `light` on ambient flags despite rule_route `full` every time. H-RECALL-FLAT: 421/425 window-total (window 28/30); ALL exceptions carry `explore:true, eps 0.25` — 100% of non-exploration flat recalls got the injected skill.

**Agent B (algo tape):** $0 moved — 0 fills, 0 risk-rail events of any kind. 7 forex idle-retires clustered 02:02–02:31Z (USDKRW, NZDUSD, NZDJPY, AUDUSD, NZDJPY-39, CHFJPY, AUDUSD-39): all never-traded runs whose worked-cycle counters (closed-market cycles excluded, `run_engine.py:453`, threshold 12) crossed in a weekend cluster — rail working as designed. 8 replacements: fleet 37 drew 4 us-stock (SLV, TMO, V, PFE) + AUDCAD; fleet 39 drew UNIUSDT, AVAXUSDT (desk-retired in 40s, above), AUDCAD. Idle-retires window-total: 27. Fleet 37 **10/10** (9 us-stock + AUDCAD); fleet 39 **replenishing 7/25** (ZC, SI, HG futures; FIL, TRUMP, UNI crypto; AUDCAD); fleet 38 stopped (`fleet_stop_all`), owner decision pending. Tripwires CLEAN: 0 tracebacks, 0 desk_record/trading_skills mentions; only pre-existing yfinance forex-symbol noise (n=10). Image `20260822-redesign-phase1`.

**Agent C (profit solutions, cross-checked):** two profit levers exist — everything else is $0 hygiene. Ranked by expected $ per unit risk:
1. **Plan 28 Item 1 offline replay of crypto demotions** (H-TECH; Item 0 ships in parallel, not as a blocker). Gate to the only money-path fix (Item 2, bounded −$150..+$540/30d at current size). Fleet 38 restart NOT required — fleet 39 carries live crypto slots. Decision rule pre-registered in Plan 28; arm-A calibration gate ≥55/68 reproduced holds or the readout is void.
2. **Breakeven-ratchet lock-evaluation cadence** — promote from Plan 28 footnote to numbered item: n=3 proves net = −overshoot (64s-poll/300s-mark discretization); removal REFUTED (LTC counterfactual −$2.30, ratchet saved $1.72). Experiment: census all `breakeven_ratchet` fires, replay 1m candles arm→fire under (a) 60s lock evaluation (b) resting price-level stop; ship only if aggregate delta > 0 surviving strip-largest AND the LTC-class save is preserved. ~+$1.2/day at today's fill rate, but the real value is that this rail taxes 100% of armed fills and would contaminate Item 2's post-ship NET measurement.
3. **Plan 28 Item 3.1 bucket-gate n=fills recount** (flag-gated, table published first) — the gate's crypto/long veto rests on 3 fills with 110/113 of its n being $0 idle-retires; a wrong-denominator breaker sitting in series with any future entry channel.

Plan 28 amendments from this window's evidence: F1/F3/F5 STRENGTHENED (82/82 demotions; kept non-holds 3/3 filled; reading #41 = live proof only ε-greedy reaches new skills, 3/347); ratchet item promoted (n=1→n=3, mechanism proven); Item 0 must also persist order_params status (both filled cycles had `absent` order blocks — intermittent light-route emission, currently invisible); "kept non-hold" overstates actionable keeps (4/7 were unactionable spot-sell inversions) — count kept BUYS only. Nothing killed. Cheap in-window measurements queued for next readings (no LLM, no prod writes): ratchet fire census, H-POOL probe (build-time daily RSI vs direction), order_params absent-rate, runs 1224/1296 no-fill trace, Phase 1 close-out citation share.

**Cross-check verdict:** A/B fully consistent (counts match; 1730 resolved as an AI decision, not a rail fault); no finding excuses a loss; no gate-loosening proposed. Nothing changed on prod. Next reading ~03:47Z.

### Reading #50 addendum — 03:0xZ — five profit-solution probes (read-only, all pre-registered in reading #50)

**Probe 1 — ratchet fire census: lifetime n = 10, not 3.** All `stop_mechanism: breakeven_ratchet` (reason `trailing_lock`), first 08-17T02:23Z, latest 08-23T23:29Z. Full table (run/symbol/side/entry/exit/peak/total-at-fire/arm/exit_fee) is captured in the probe output; the three 08-23 fires are rows 8–10. Arm arithmetic: arm/exit_fee = exactly **2.000** for the four 08-17→18 fires, **2.2222** from 08-19 on (1489, 1556, 1710, 1712, 1721), and one outlier 8.88 (1417 — exit_fee reflects the residual 25% book after partial covers). Data gaps that the replay experiment must handle: **no arm timestamp is recorded anywhere** (only the fire-time snapshot exists — arm time must be reconstructed from candles), and **two fires record peak < arm at fire** (1417, 1712 — peak reset by partials vs arm recompute is not recoverable from events). The lock-cadence replay dataset now exists: 10 episodes, 6 negative-total fires.

**Probe 2 — H-POOL (does the thesis generator build longs into overbought?):** build-time RSI is NOT stored (factor_scores_json has momentum/sma/vol only); reconstructed daily Wilder RSI(14) from OKX 1D candles as-of the last completed candle before build. **n = 121 crypto long runs since 08-13: RSI>70 at build = 69/121 = 57.0%** (>80: 30 runs, mean 70.4). Below the pre-registered 60% line overall — **H-POOL is NOT confirmed on the full window** — but the recent concentration is stark: 08-21 + 08-22 alone = **44/49 = 89.8%**. Raw fact, no interpretation; the Item 1 replay's H-POOL read should split early/late. Full 121-row table + repro script preserved in session scratchpad (rsi_out.tsv, rsi_probe.py). Caveat: the intraday partial candle the generator actually saw is not reconstructible.

**Probe 3 — order block emission: absent is the norm, not a wrinkle.** Since window start, order_params n=429: **absent 314 (73.2%) / defer 104 (24.2%) / parsed 11 (2.6%); route 100% light** (zero full-route rows — no route split exists). Premise correction: of the 3 filled cycles, 1710 and 1712 were `absent` but **SOL 1721 was `parsed`** (trail_arm_pct 3.0) — "both filled cycles had absent blocks" was wrong for the window's third fill. defer filled 0/104. Item 0's snapshot spec should persist outcome + values as planned; the 73% absent rate means null_size_cap sizing is the dominant path, not an edge case.

**Probe 4 — the two historic "kept but unfilled" runs: one real loss path, one DEAD premise.** Run 1224 (VZ, 08-14): the kept buy (final 0.68, intent open $990) died at the execute stage on **`gate_skip "fence: lease expired"`** — a worker run-lease infra fence, not doctrine; no signal row exists. That is a real lost-fill class distinct from panel demotion. Run 1296 (SUI, 08-15): **premise REFUTED — all kept verdicts filled** (signals 1373/1376/1380 + at_time 1383 all present, chain unbroken). Record the refutation by name: "1296 unfilled" is dead; F3's loose end reduces to the 1224 lease-fence class.

**Probe 5 — Phase 1 close-out citation share: the prompt-layer removal TOOK; the RAG layer still serves the doctrine.** Crypto decision events citing 'reachab': before-window 71/497 = **14.3%** → after 5/296 = **1.7%** (the 5 are generic "unreachable target within horizon" phrasing, not the historical-reachability line). Yet `recall` events cite `skill:reachable-exits` chunks as retrieval source in **100% of both windows** (369/369 before, 295/295 after) — the desk stopped writing the line, but the RAG retrieval layer serves the reachable-exits lesson on every crypto recall regardless. Phase 1's final read: the line's removal moved its own citation metric (14.3→1.7%) and still produced 0 kept buys — consistent with the audit's verdict that the doctrine CLASS, of which the recall channel is the surviving member (H-RECALL-FLAT 421/425), suppresses entries, not the one line.

**What this changes in the ranked solutions (no re-rank needed):** #1 (Item 1 replay) gains the H-POOL split requirement (early/late) and keeps its priority; #2 (ratchet cadence replay) now has its full n=10 dataset plus two reconstruction requirements (arm-time from candles; peak<arm anomaly handling); Item 5 (recall ranking) gains direct evidence that the retrieval layer is the last remaining doctrine channel into flat crypto cycles. New defect class logged for the backlog: execute-stage lease-fence lost fill (1224), n=1 lifetime — not actionable at n=1.

## Phase 1 accountability reading #51 — 2026-08-24 03:11Z (quiet; 3-agent cycle)

**P&L unchanged −$1.22 — no new fills (signals 0 since 02:47Z; pnl_audit resid $0.00, 71/71 validated), positions 0 (both forms, table empty).** §5: decisions 435 (+8 at snapshot; A's sweep through 03:15Z saw 10), buy proposals 84 (+2), panel kept 7 non-hold / **0 as buy**; window ends 10:36Z.

**Agent A (AI tape):** 10 decisions (9 hold, 1 retire), 2 demoted buys with reasons: LTC 1732 `buy` 0.58 → hold 0.45 (RSI≈74 overbought, crowded longs, thin liquidity, ~24h run life makes any stop too tight vs daily vol — entry_quality 0.0); UNI 1728 `buy` 0.72 → hold 0.57 (volume 0.08x at $4.50 resistance; desk memory "low volume + high OI + greed>70 precede correction" — and this cycle's recall was an `explore:true` draw of `skill:mean-reversion-guard#0`, the exact memory cited: **the exploration arm plausibly authored this demotion**, first observed instance of the recall layer actively feeding a demotion). **BTCUSDT 1733 desk-retired 44s after build** (conf 0.80): "the stop needed for the short exceeds the $19.70 loss-rail, making any meaningful position size impossible" — build-path feasibility miss, [[exposure-feasibility-build-gate]] class recurrence signal, n=1 this window, $0 cost, pure churn. verdict_salvaged 0. **TRUMPUSDT tracker (demoted short, entry 2.563/stop 2.66/target 2.36): neither leg touched** (Hyperliquid 1m 02:34–03:15Z: high 2.5684, low 2.51, last 2.535); the entry traded through at ~02:35 — a filled short would sit **+1.09% unrealized against the demotion**; score only at leg-touch. H-RECALL-FLAT: scope 10/10 reachable-exits, 0 new exceptions; all 5 lifetime exceptions are `explore:true` (5th at 02:46:42Z, pre-scope) — zero non-exploration exceptions exist. Denominator caveat: A could not reproduce #49's 421/425 without its exact window start; the all-explore exception set is boundary-independent.

**Agent B (algo tape):** 0 fills / 0 positions double-confirmed (both order_intents `hold` with empty compiled steps). 2 idle-retires, both arithmetically verified at exactly 12 workable cycles (ZC 1702: 47−35=12, 03:04:55Z → LTCUSDT 1732; FIL 1720: 12−0=12, 03:11:18Z → BTCUSDT 1733 → desk-retired 44s → ZS 1734). Fleet 37 10/10 unchanged; fleet 39 replenishing 7/25 (SI, HG futures; UNI, TRUMP, LTC crypto; AUDCAD; +ZS incoming); fleet 38 stopped, owner decision pending. Tripwires CLEAN: 0 tracebacks, 0 desk_record/trading_skills, 0 yfinance noise this window. Image `20260822-redesign-phase1`.

**Agent C (solutions delta):** nothing in this hour changes the #50 ranking (demotion denominator thickens to 84/84; ratchet dataset stays n=10). Deliverables: (a) the 10:36Z close-out checklist (final §5 with kept-BUYS headline, citation-share final read + the recall-layer 100% fact, H-RECALL-FLAT tally with every exception named+explore-flagged, pnl_audit window P&L, fleet-38 INCONCLUSIVE by name, order_params final rates, TRUMPUSDT scoring, ops tail, next-session hand-forward); (b) **time-sensitive: archive 1m candles for all 10 ratchet episodes NOW** — the oldest fires (08-17/18) are aging out of feed retrieval windows and this is the lock-cadence replay's only expiring input; (c) Monday 13:30Z us-stock open watch list (first us-stock session on the redesign image, fleet 37 = 9/10 us-stock): does the panel demote us-stock buys at the crypto rate; any armed fill re-exposes the ratchet discretization; bucket-gate vetoes; order_params emission rate.

**Cross-check verdict:** A/B/C fully consistent; every demotion and retire carries its reason; no excuses. The UNI demotion's exploration-drawn skill citation is new evidence FOR Plan 28 Item 5 (the recall channel shapes decisions). Nothing changed on prod. Candle archival dispatched this cycle; next reading ~04:1xZ.

### Reading #51 addendum — 04:0xZ — LOCK-CADENCE REPLAY RAN: the pre-registered hypothesis SPLITS

Full report: [2026-08-24-ratchet-cadence-replay.md](2026-08-24-ratchet-cadence-replay.md) (method, extracted `run_engine.py` semantics with line refs — all 10 census arm values and totals reproduce to 4 decimals; live nets reproduce pnl_audit's −$1.222 exactly). Dataset: the 10-episode 1m archive committed this cycle.

**Refutation to record by name: the "faster lock evaluation" (≤60s cadence) fix is DEAD.** Counterfactual A failed BOTH pre-registered kill conditions: aggregate delta −$0.34 (≤ $0) and 3/9 fires (33%) exit WORSE than live (1712 −$0.60, 1721 −$1.01, 1335 −$0.006). Mechanism: the overshoot is price VELOCITY — crossing 1m bars ranged 0.14–0.51% against a 0.09–0.10% cushion — so a finer clock still fires one sample late; on 1712's V-shape the 300s clock's luck beat the fast clock. (Strip-largest flips the sign to +$0.67 — stated per the outlier rule — but both full-sample kill conditions stand.) Reading #43's n=3 inference "the fix is tick/faster lock evaluation" is thereby corrected by its own experiment.

**What SURVIVES: counterfactual B — a resting price-level stop at the lock level (intrabar fill at breakeven+fee).** Level-fill aggregate **+$3.00, 0/9 worse**; strip-largest (1392) leaves **+$1.78, 0/8 worse**; robust to arming on the 300s grid (+$1.77…+$2.70 across all phases, 0 worse); the three 08-23 fires all convert to −$0.0002. Slippage sensitivity: positive until slip ≥ ~45% of the crossing minute's range (~24% with 1392 stripped). **1556 LTC save preserved under every variant** (exits 00:51–00:59 vs live 01:09:57 at ≈$0.00 vs −$0.30; the no-ratchet −$2.30 path avoided by a wider margin than live's $1.72 save).

Exclusions/flags: **1417 excluded** — its fire is the phantom-baseline bug (fixed by R21), not a cadence loss; under current semantics the rail never fires on that tape. **1392 flagged** (largest positive contributor, window-censored sim phases, pre-fix floor arithmetic) — reported with and without.

**Data-integrity finding (adjudicated by the main session):** the candle archive README's fill-price cross-check PASS was FALSE — prod fills sit 0.03–0.16% outside the OKX candles (12/12 replay-agent check; 3/4 main-session spot-check) — systematic feed basis. The v1 absolute replay was invalid; v2 rebased (difference-in-difference) and validated against actual fire minutes/nets (8/9 bracketed). README corrected in this commit.

**Ship guidance (owner law: implement only on experimental result):** Plan 28's rail item re-scopes from "faster lock evaluation" to **"resting price-level lock — intrabar stop fill at breakeven+fee"**. This is an execution-path build (the simulator currently fills only at 300s marks), with slippage the one unmeasured parameter; the experiment's slip-tolerance bounds (~45%/~24% of crossing-minute range) define the acceptance test for the implementation. Nothing ships this cycle; the design goes to the implementation queue with its replay attached.

## Phase 1 accountability reading #52 — 2026-08-24 04:11Z — THE FIRST KEPT BUY OF THE WINDOW, killed by the mark-drift gate

**P&L unchanged −$1.22 — 0 new fills (signals 0 since 03:15Z, window fills stay 6), positions 0 (both forms), pnl_audit unchanged (resid $0.00, 71/71).** §5: decisions 458 (+23), buy proposals 91 (+7 — a spike vs the ~1/hr weekend trend, all crypto), panel kept 9 (+2). **HEADLINE CHANGE (per the #51 close-out rule): the Phase 1 metric is no longer "0 kept buys" — it is "1 kept buy / 91 proposals, 0 filled, chain stopped at mark_drift."** Panel-doctrine suppression and execution loss are different verdicts; both now exist in the window.

**The kept buy (A+B traces agree end-to-end):** run 1736 LITUSDT (crypto, fleet 39) cycle 1, 03:31:04Z — proposal buy 0.72 → panel final **buy 0.63** (conviction 0.7085, entry_quality 0.71) → decision buy → order_params parsed (size_frac 0.05, lev 3, stop 2.5%, target railed to R:R floor) → order_intent open, machine $772.48, mode=apply → **gate_skip stage=`mark_drift`: "stale mark: moved 0.94% since the decision mark (3.6042 → 3.5703); entry refused — re-decide on fresh data"** (cap 0.75%, R25 rail, `RUN_ENTRY_MARK_DRIFT_CAP_PCT`). Two sharp facts: (1) **the drift was DOWNWARD — favorable to the buy (cheaper entry) — and the direction-blind gate refused anyway**; (2) the pipeline has no re-price-and-retry path, only re-decide, and the 0.63-conf edge did not survive re-derivation (cycle 2: hold 0.44 after LIT's +9.9% pop consumed the entry; cycle 3 hold 0.58). A marginal entry died to a sub-1% favorable drift. n=1 in window — logged as a candidate defect (direction-blind drift gate + no-retry), NOT actioned; next step is a lifetime census of mark_drift refusals with favorable/adverse split and counterfactual walk before any design.

**The other kept verdict:** run 1735 ETHFIUSDT cycle 2, 03:36:29Z — proposal buy 0.74 → panel INVERTED to sell 0.68 → gate_skip stage=`risk` "spot sell with no inventory — treated as hold." The known spot-sell-inversion no-op class (metric noise; C's slotting rule: no re-rank). Kept-row accounting for the close-out: 9 kept = 6 filled (3 round trips ×2 legs… correction: 6 fills = 3 trips; the 7 pre-04:00 keeps include 4 sell-inversions) — final classification table goes in the 10:36Z close-out.

**TRUMPUSDT tracker closes (run retired):** the desk retired 1723 at 04:02Z on an 11-cycle hold streak (conf 0.38, entry_quality 0.2, 0 trades lifetime) — **while its own demoted short was in the money**: post-entry mark path 2.5690→2.4740 (low)→2.5083 (final), neither bracket leg ever touched (stop 2.66 never revisited, target 2.36 never within 4.8%). Counterfactual bounded ≈ +2.1–3.5% unrealized (~$34–56 on machine size), partial credit only per [[forfeited-entry-is-not-forfeited-profit]] — the target was never reached. Mark tracking via this run ends here (run dead).

**Agent B (algo tape):** 3 clean rotations (SI 1708 and HG 1709 idle-retired at cycle 37 → ETHFI 1735, LIT 1736; TRUMP desk-retire executed cleanly → NQ 1737). Fleet 37 10/10 unchanged; fleet 39: UNI, AUDCAD, LTC, ZS, ETHFI, LIT, NQ; fleet 38 stopped (owner decision pending). No lease/fence events (1224 class: 0). Tripwires CLEAN (0 tracebacks, 0 desk_record/trading_skills; yfinance research noise only). Image `20260822-redesign-phase1`.

**Agent A extras:** decisions in scope 21 (18 hold, 1 buy, 1 sell, 1 retire; plan_adherence deviated ×5). 1 verdict_salvaged (truncated 357 chars, salvage worked). H-RECALL-FLAT STANDS: 20/21 recalls carry reachable-exits; the single outlier is `explore:true` (NQ 1737) — zero non-exploration exceptions ever; exploit-arm share remains 100%. **Query trap for future sessions: `ts` stores ISO strings with `T`; a space-form literal ('2026-08-24 03:15:00') matches the WHOLE DAY because 'T' > ' ' — always use the T form.**

**Agent C (solutions delta):** slotting resolved — inversion = noise, mark_drift = new candidate class (census first). Ratchet lever #2 next step is the implementation design doc (files: run_engine.py `_breakeven_floor_hit` L969–1033 + call site + `_flatten_run` fill price; acceptance: replay the 9 episodes with slip ≤ ~24% of crossing-minute range, LTC-save preserved, forward metric = per-fire net vs −overshoot on pnl_audit). **Item 1 replay: launch the calibration arm in the current off-peak — no dependency on the 10:36Z close-out** (input tape frozen; only the final denominator sentence waits). LLM contention managed by serial throttle on the local tier. Close-out checklist gains: kept-row classification table (mandatory), the changed headline, the lock-cadence verdict by name, Item 1 launch status.

**Cross-check verdict:** A/B agree end-to-end on both kept-verdict chains (discussion+decision+intent+gate_skip+positions+equity all reconciled); every outcome carries its reason; the TRUMP retire-in-the-money is stated as bounded opportunity loss, not excused. Nothing changed on prod. Item 1 calibration arm dispatching this cycle; next reading ~05:1xZ.

## Phase 1 accountability reading #53 — 2026-08-24 07:11Z (3h catch-up) — SECOND kept buy dies at mark_drift; the harness-contention experiment resolves

**P&L unchanged −$1.22 — 0 fills (signals 0 since 04:11Z; window 6), positions 0 (book fully flat, both forms), pnl_audit resid $0.00 / 71/71.** §5: decisions 507 (+49), buy proposals 102 (+11), panel kept 10 (+1). **Headline: 2 kept buys / 102 proposals, 0 filled — both stopped at the mark_drift gate.** Two cron slots were missed while the session handled the harness episode below; this reading covers 04:11→07:11Z.

**Kept buy #2 (A+B chains agree end-to-end):** LITUSDT 1736 cycle 4, 04:38:41Z — proposal buy 0.71 → panel **kept buy 0.58** ("2.4× volume overrides overbought RSI"), full bracket authored (stop 1.5%, target 3.1%, 48h), order_intent open $772.48 apply → **gate_skip `mark_drift`: 0.97% > 0.75% cap** (env unset, default; refresh armed at cycle age >45s; prod `run_engine.py:7243-7261`).

**Cross-check disagreement — chased, and the disagreement IS the finding:** A framed the refusal as the #52 defect class again ("mark moved DOWN — favorable, cheaper entry — direction-blind gate"). B framed it as protective: the mark fell **toward the plan's own stop** (3.6979 vs stop 3.68 — 0.5% away instead of the authored 1.5%), so a fill would inherit a bracket priced off a stale mark with compressed geometry; and the desk's own re-decide (cycle 5) chose hold on fresh data — the desk agreed with the refusal. Applying B's geometry test to kept buy #1 (03:31Z) partially transfers: that fill too would have compressed stop distance 2.5%→1.6%. **Verdict: #52's "direction-blind gate defect" framing is DOWNGRADED from candidate-defect to open question.** "Cheaper entry" is not unambiguously favorable when the move is toward the stop. The mark_drift census (lifetime n, drift direction × bracket-geometry split, counterfactual walk of refused entries) remains the right next step and gains a dimension; no design work until it reads out. Both in-window refusals share one more fact: in both, the desk never re-derived the buy — the pipeline still has no re-price path, only re-decide.

**The harness-contention experiment (unplanned, now resolved with a clean series):** the Item 1 calibration harness ran serial LLM calls on the shared local tier 04:38–06:02Z; the supervising agent died to an API 529 but the detached harness kept running; the main session detected the pre-registered cadence breach independently (30-min buckets: **10 before → 8, 8, 6 during (worst −40%) → 10 the bucket the harness was killed, 8–10 since**) and aborted it at 06:02Z. ~17% added LLM load ⇒ −27..40% desk cadence, full recovery within minutes of the kill — **the local tier is saturated at the margin; refuted by name: "tax-free deep off-peak" (the measurement WAS the deepest off-peak) and "all-markets-closed idle windows" (fleet 39 crypto never closes).** Corroborating quality signal: 3/3 verdict_salvaged truncations sit inside the harness window, 0 after (baseline ~1/hr — suggestive, n small). Zero tracebacks, zero LLM error lines; the 04:38:41Z mark_drift refusal fired in the harness's opening minute (a slowed LLM widens the decision→execute interval — plausible contributor, unattributable at n=1, and kept buy #1 predates the harness so the gate binds without contention too).

**Item 1 calibration partial result (before abort): 33/66 — 33/33 raw reproduced, 32/33 strict (one rule-fallback seed excluded), brief-lines 33/33, price-dev median 0.20%. On pace for the ≥55/66 gate; gate NOT yet decidable.** Results checkpointed (repo: docs/reports/data/item1-calibration/results-partial-33.jsonl; box: /tmp/item1/, harness verified dead, remnants intact for resume). **Plan of record (C):** resume the remaining 33 events AFTER the 10:36Z close-out (so the tax stops contaminating the window's own §5 denominator), strictly serial, pre-registered guard = auto-abort on two consecutive 30-min buckets <8 decisions, finish before Monday 13:30Z us-stock open; quantified cost ≈4 fewer proposals, expected realized ≈$0 on a 0-fill desk (counter-argument on record: both kept buys surfaced in taxed/adjacent hours — the tax is small and bounded, not zero). **The full arm set (~1,350 events ≈45h serial) is infeasible on the shared tier** — gated on a prod-box headroom measurement, then a cloud gpt-oss equivalence probe (re-run 10 calibrated events, pass ≥9/10 strict); fail → escalate into the owner's pending second-endpoint/fleet-38 decision.

**Agent A extras:** 49 decisions (48 hold, 1 buy), no retires; panel demotion cluster is uniform overbought-RSI + weak-volume + Greed-73 across all four crypto symbols — the one kept cycle is the one where 2.4× volume broke the weak-volume leg. `llm.source: "rule"` on decisions is the standing baseline (also 285/285 prior 24h), not a degradation artifact. H-RECALL-FLAT: 48/49 reachable-exits; the 1 exception is explore:true — non-exploration exceptions remain 0 lifetime.

**Agent B extras:** no rotations (fleet 37 10/10, fleet 39 = ZS AUDCAD LTC UNI NQ ETHFI LIT, fleet 38 stopped — all unchanged); §5 confound noted for the close-out: 04:38–06:02Z decision counts ran under harness tax. **Standing constraint re-confirmed, not new: fleet 39 `replenishing:7/25` with FleetPlanner `researched: 0, built: 0` every tick — the researcher produces nothing toward the 25-slot target** (known replenish-stall signature; predates the window).

**Cross-check verdict:** every outcome carries its reason; the A/B disagreement on mark_drift was chased to a downgrade rather than averaged; no excuses (the desk's re-decide agreeing with the gate is stated, so no forfeited-profit claim is made). Prod changes this cycle: killing the runaway harness (pre-registered tripwire, evidence above) — nothing else. Next: 10:36Z close-out per the #51+#52+#53 checklist.

## Reading #54 — 2026-08-24 21:5xZ — TWO SHIPS, and the pre-registration for the second

Owner ordered a ten-agent loss analysis after the dashboard showed a losing week, then ordered the desk be given API access to its own reference data. Both are done and live. This reading records what shipped and — more importantly — the falsifiers, because one of the two ships is an entry-side prompt change, which is the exact class that produced #484.

**SHIP 1 — `POSITION_REFRESH_INTERVAL` 300s → 60s (config, prod, reversible).**
Root cause, verified three ways on two symbols/days and re-verified by the main session: `positions.current_price` is written only by the price loop (`tasks.py:685`) on that interval, while the stop/rail scanner polls ~64s — so **77.8% of consecutive equity polls carried an identical mark** (1,344/1,727), 347 of 383 freeze episodes lasting 4–5 polls. Rail trigger bands (ratchet floor, armed-exit level) are **2.1–4.7× narrower than the unobserved mark gap**, so they cannot be landed on and must overshoot; total live-trigger overrun was **$5.32 = 93% of the week's gross loss**. LINK#1 alone: −$2.19 at the armed level vs −$4.11 actual = **$1.91 of pure stale-mark cost**.
**Pre-registered falsifier (UNCHECKED — next session must run it): the consecutive-identical-mark rate must fall from 77.8% to <20%.** If it does not, the interval was not the mechanism and this must be reported FAILED in the same terms. If it falls but give-back-over-peak does not improve, the cause was right and the consequence wrong.

**SHIP 2 — `desk_reference` (#584 + #586, image `20260824-deskref-trips`, flag `DESK_LEDGER_BLOCK=1` ENABLED 21:47Z).**
The desk now reads its own fill ledger on every cycle including FLAT ones: record on this symbol+side, directional record, exit-author record with give-back over peak, hold-time vs outcome, and the real booked round-trip fee. Live output verified on prod before enabling. Trip-level not run-level (#586 fixed a defect where run 1748's two LINK shorts collapsed to one row and were invisible while the run was open — the exact repeat the module exists to prevent).

**PRE-REGISTRATION for ship 2 (H-LEDGER).** Hypothesis: showing the desk its own closed record reduces loss-repeating re-entries and improves selectivity.
- **Primary metric — same-symbol/same-side re-entry within 24h of a losing close.** Baseline this week: **2 of 2** (FIL#1→FIL#2 at 2.17× size 23h later; LINK#1→LINK#2 at 2.00× size 5h23m later), both lost. Falsifier: repeats continue at the same rate over the next ≥5 opportunities → the block failed to move its own metric.
- **Secondary — directional mix.** Baseline 13 of 16 trips short into a tape where every slotted symbol rose.
- **GUARD, and this is the one that matters most: entries must NOT collapse further.** The block truthfully tells the desk "short: 42 profitable of 82, net −$97.82". A desk reading that may simply stop trading. **[[entry-collapse-traced-to-reachability]] / #484 is precisely this failure**: a measured, truthful line shipped into both prompts and was later measured ACTIVELY HARMFUL in crypto (+$145 of suppressed entries over 8 days). **If kept-buy rate or fill count falls below the pre-ship baseline (0 kept buys/102 proposals, 6 fills in the window) over the next 48h of comparable tape, revert the flag** — `DESK_LEDGER_BLOCK=0` and recreate the worker. A fact that suppresses profitable entries is still harmful, and the module's honesty is not a defence.

**Corrections this analysis forced on the standing narrative — recorded by name so no session re-runs them:**
- "The breakeven ratchet authored the week's loss" — **DOWNGRADED**. Replayed at their own authored brackets the 16 entries resolve to −$37.24 vs the actual −$9.01 (2/16 ever touched target, 11 hit their own stop). The exit machinery was the only component ADDING value. The entry direction authored the loss; a stop at ~0.35σ amplified it.
- "The entry gate demands ~12× the real booked fee" — **DEAD, units error** (×3 safety multiple ÷0.25 optimism haircut; the gate reads `fees.fee_rate()` directly). Real defects that survive: the **0.15% `RUN_MIN_EDGE_PCT` noise floor** binds 4 of 5 markets (467 refusals vs 5 fee_edge) and its own docstring admits no evidentiary basis; and `routes_signals.py` + `symbol_research.py` still hardcode the legacy 0.1%/leg, so research EV under-rates every candidate.
- "The demotion wall destroys money" — **NOT REPRODUCED**. All 265 refused crypto proposals walked to −$255 (86 independent clusters, robust across every stop and horizon). But the protection is regime luck (32/32 symbols up), and the wall's own KEPT book lost 5.6× more per trade than what it refused.
- "mark_drift is a direction-blind defect" — **OPEN QUESTION at n=2**, both refused marks had moved toward the plan's own stop; stripping one flips the sign.
- "plan_adherence=deviated entries are worse" — **REFUTED and dangerous to act on**: 71% of actionable decisions are `deviated` and `followed` is overwhelmingly the label for NOT trading (n=5 non-retire). A rule against deviation is a rule against acting.
- **n=16 cannot distinguish skill from noise** (26% of coin-flip weeks are this bad; ~n=45–90 needed). The proposal-level signal (n=444) is real and negative but sits in ONE regime.

**Ops note:** GitHub Actions is BILLING-BLOCKED (all 5 checks fail in 3s; Actions itself operational; annotation names the payment failure). Every job was reproduced locally as merge evidence — 4579 pytest passed, ruff clean, gitleaks 0 in-range, frontend build green; pip-audit could not run locally and is unaffected (no manifest touched). Owner action required to restore CI.

---

## Reading #55 — 2026-08-28T03:25–04:00Z — falsifier harvest after a 3-day monitoring gap

**Monitoring was OFF for ~77 hours** (owner stop order 08-24T21:55Z → owner re-order 08-28T03:2xZ, hourly/3-agent cadence). Four ships landed in that gap from other sessions. This reading is therefore a **falsifier harvest**, not an incremental cycle: every pre-registered falsifier that came due while nobody was watching is settled here, and the ones that are still undecidable are named as undecidable rather than quietly passed.

**Profit first.** All-time trip net across the 4 agents that ever filled: **−$184.65**. Stripping the largest contributor (agent 5, −$187.86, whose entire book is 08-12→08-14 under the pre-redesign logic) leaves **+$3.21** — **the sign flips**, so per the outlier law the all-time verdict is INCONCLUSIVE as a judgement on current logic and is dominated by a three-day window in mid-August. Trailing 24h: **+$0.4417** (5 legs). Trailing 48h: 9 fills. Book is flat right now (0 open position rows); 8 runs running.

### The finding of this reading: 102 of 102 exits at exactly $0.0000

Agent 6 — 53 filled runs, 08-15→08-26 — booked **102 exit legs whose `pnl` is EXACTLY 0.0000** (0 NULLs; verified). Against $4.5207 of entry fees, its trip net is **−$4.52**: a pure fee bleed with zero gross extracted across 102 round trips. This is `_breakeven_floor_hit` (`current <= exit_fee`, best case $0 BY CONSTRUCTION) caught at full scale, and it is the strongest evidence yet for the payoff-ratio diagnosis. The same fingerprint appears in the daily cut: 08-24 and 08-25 together booked 39 exits summing to exactly $0.0000 against ~$2.75 of entry fees. No other agent shows it (agent 5: 0 of 134 zero exits; agents 59/60: 0 of 68) — so it is the rule's fingerprint, not a ledger artefact.

Agents 59 (+$6.98, 59 exits) and 60 (+$0.76, 9 exits) are **net positive** and carry no zero-capped exits.

### FALSIFIER 1 — frozen mark (mine, reading #54): **PASS**

Pre-registered: consecutive-identical-mark rate must fall **77.8% → <20%**, else report FAILED.
**Measured 2.3%** (4 identical of 171 consecutive pairs, 5 runs, 08-26→08-27), median poll gap **62–74 s**, matching `POSITION_REFRESH_INTERVAL=60` plus scan overhead. Per-run: 1825 0.0%, 1894 0.0%, 1895 5.3%, 2001 0.0%, 2019 1.4%.

**Method correction, recorded because the first two passes were both wrong.** Pass 1 filtered equity events by `payload NOT LIKE '%"unrealized": 0.0,%'` and returned 2.4%. Pass 2, unfiltered but bounded by `trades >= 1`, returned **95.7% / 90.1%** — because `trades` is a CUMULATIVE counter, so a run keeps polling at `unrealized: 0.0` long after its position closes, and those flat rows are trivially identical. Neither number is the answer. Pass 3 — the one reported — bounds polls to true open intervals reconstructed from entry→exit leg timestamps in `signals`. **A single green check was wrong here; the disagreement between passes was the finding.** The direct check (`positions.price_updated_at` age) was unavailable: the book is flat, 0 position rows.

### FALSIFIER 2 — H-LEDGER revert guard (mine, reading #54): **NOT TRIPPED, flag stays ON**

Guard: revert if kept-buy rate or fill count falls below the pre-ship baseline (0 kept buys/102 proposals, **6 fills**) over 48h of comparable tape. Measured trailing 48h: **9 fills** (`trade` events), 2455 decisions → 115 order_intent → 9 trades. 9 ≥ 6, so entries did NOT collapse and `DESK_LEDGER_BLOCK=1` stands. The #484 failure mode did not recur.

### FALSIFIER 3 — RATCHET_LOCK_FRAC (#592): **1 of 30 fires — NOT DECIDED**

Pre-registered: over the first 30 fires, median give-back must fall below 100% of peak AND median realized must be positive.
Exactly **one** `stop_mechanism` fire since the 08-27T05:45Z ship — 08-27T10:14:46Z, run 2001, TAOUSDT: `peak 2.2846, arm 0.4486, exit_fee 0.2018, total 1.0877`. New floor = `0.2018 + 0.5 × (2.2846 − 0.2018) = 1.2432`; old floor was `exit_fee = 0.2018`, i.e. **best case $0**. Give-back **52.4% of peak** vs the pre-ship median of 103.1%; realized **+$1.0877** vs a pre-ship median of −$0.0066. Directionally exactly what was designed, and it is the single largest positive leg in the window.
**This does not pass the falsifier.** n=1 of 30. At the observed rate (2 fires / 48h) 30 fires needs **~30 days**. Reported as UNDECIDED; a session that reports #592 as "working" on this evidence is overclaiming.

### FALSIFIER 4 — PANEL_LOCAL_FALLBACK (#591): **0 of 20 — UNTESTED, not passed**

Pre-registered: first 20 fallback meetings ≥80% genuine verdicts. Measured since the 08-26T00:14Z ship: **0 fallback meetings out of 122** `order_discussion` events — no payload contains `local-fallback`. The good reading is that no INFRA panel failure occurred; the honest reading is that **the safety net has never been exercised in production and is therefore unverified**. It cannot be decided by waiting — only by fault injection. `verdict_salvaged` fired 27 times against 122 meetings (**22%**), and `no_verdict` 8 — the truncated-JSON salvage path is carrying a material share of verdicts and deserves its own measurement.

### State verified on prod this cycle

Image `sooppiy-backend:20260827-consol-hconsol` (deployed 08-27T22:30, containers up 5h). `POSITION_REFRESH_INTERVAL=60`, `DESK_LEDGER_BLOCK=1`, `DAY_DIGEST_BRIEF=1` set; `RATCHET_LOCK_FRAC` and `PANEL_LOCAL_FALLBACK` unset, so both run on code defaults (0.5 and ON). Deploys in the gap: `20260825-humanfacts`, `20260825-period-chart`, `20260825-trailfix`, `20260825-daydigest`, `20260826-panelfix`, `20260827-ratchetlock`, `20260827-consol-hconsol`. Worker errors in the last 20 min are benign feed noise only (`RTY`, `NZDJPY` delisted/no data), 0 tracebacks.

**#593 shipped the zero-intelligence control** — the experiment recorded for weeks as "the decisive unrun experiment" is no longer unrun. Verdict, pre-registered on both fill bases: **INCONCLUSIVE** — 57 closed crypto trips (ledger net −$6.60) vs 1,000 symbol+size-matched random draws under identical rails; at the realistic 0.03% basis the AI sits at the **63.7th percentile** of random with CI90 of the mean trip difference including 0. AI entry selection is **not distinguishable from random-with-rails at n=57**. Secondary result, and the actionable one: **even long-only random loses at the current slot size in a rising market**, which is experimental support for the `FLEET_TARGET_SLOTS` consolidation that shipped in the same PR.

### Ops

Reading PRs **#572–#583 remain unmerged** and reading #54 never got a PR. Per [[cycle-notes-must-reach-main-for-rag]] a note enters the desk's corpus only after MERGE→DEPLOY, so **~13 cycles of findings are currently invisible to the AI that is supposed to learn from them.** This is now the largest process defect on the board and needs an owner decision: merge the stack, or declare it archival and stop paying the cost of writing it.

### URGENT — an armed scale-up rests on an experiment that cannot support it

**Verified by inspection this cycle, independently of the agent that raised it.** `research/zi_control_replay.py::simulate_trip` is **exactly homogeneous of degree 1 in `notional`**. Every term is either notional-independent (`entry`, `stop = entry·(1−sgn·STOP_PCT)`, `target`) or exactly linear (`qty = notional/entry`, `fee_floor = 2·FEE_LEG·notional`, `arm = RATCHET_ARM_X·fee_floor`, `pnl = sgn·(cl−entry)·qty`, `floor = fee_floor + RATCHET_FRAC·max(0, peak−fee_floor)`, `gross`, `fees`). Both sides of every exit comparison are linear in notional, so scaling notional by *k* leaves the exit path identical and scales P&L by exactly *k*. An agent confirmed this numerically: 2,000 random trials, worst relative deviation **3.1e-15** (floating-point noise).

**Therefore #593's secondary finding — "even long-only random loses at the current slot size" — cannot support slot consolidation.** It is equally true at every slot size. The replay is mathematically incapable of seeing size. What it actually measured is that the house rails lose at *all* sizes, which argues *against* consolidating, because consolidation multiplies the per-trip loss.

**This violates the owner's own experimental-mindset rule** ("implement ONLY on an experimental result; a fix justified by reasoning is a guess"). The consolidation is not merely unsupported — it is supported by a quantity the experiment could not have measured.

**The live exposure, measured this cycle (`config_snapshot_json.max_bet_usd`, `fleets.total_budget_usd`):**

| Fleet | Budget | Incumbent max_bet | New-run max_bet | Scale-up | State |
|---|---|---|---|---|---|
| 41 (agent 6) | $10,000.00 | $130.39, $267.38 | **$1,125.00** (runs 2106/2107, created 2026-08-28T03:25:23Z / 03:31:30Z) | **4.2×–8.6×** | **ALREADY LIVE** |
| 42 (agent 60) | $100,000.76 | $180.00–$335.34 (4 runs, all created 08-27T12:28–16:25Z) | ~$11,250 at budget/4 | **~40×** | **ARMED**, fires on incumbent turnover, no deadline |

`FLEET_TARGET_SLOTS=4` is set in prod `.env` and is **not** a no-op — it is **half-applied**: `_slot_anchor` binds only at funding time, and the consolidation resize never fires because `n_runs (4) > tgt (4)` is false. Fleet 42 therefore re-anchors silently whenever a slot recycles.

**Agent 6 is the account that booked 102 of 102 exits at exactly $0.0000.** It is now trading at 4–8× size, having re-anchored during this very monitoring session. #592 fixed the geometry that produced those zeros, but that fix stands at **1 of 30 fires** — the size increase is being applied ahead of the evidence that the exit rule works.

**This is an owner decision and was NOT actioned by this session.** The revert, if wanted, is one line — set `FLEET_TARGET_SLOTS` back (or unset it) in `/home/ec2-user/sooppiy/.env` and recreate the worker. Recorded here rather than acted on, per [[never-touch-live-trading-config]].

**Correction to a document in this corpus:** `docs/reports/HANDOFF-ratchet-monitoring-2026-08-27.md` states that `signals.pnl` "deducts only the entry fee". That is **wrong** — it nets the **EXIT** fee only, verified to 6 decimals against the LIT partial covers (signals 1554/1555) and reconciling to `trading_runs.realized_pnl_usd` to the cent. Trip net = `exit.pnl − entry.fee_usd`. The ratchet falsifier's arithmetic depends on this convention.

### RETRACTION — the "102 exits at $0 = the ratchet's $0-by-construction" claim in this reading is WRONG

**Raised by the AI-authorship agent, then verified independently by the main session. The earlier section of reading #55 stands retracted on this point and is superseded by what follows.**

The zeros are an **accounting defect scoped to agent 6**, not the old breakeven rule operating as designed. Two decisive tests:

**Test 1 — the cash never moved.** After 101 closing trades with real fees charged, `agents.cash − agents.starting_capital` for agent 6 is **exactly 0.00000000**. Every other agent moved: 5 → −187.86425815, 59 → +6.97524996, 60 → +0.75744194. A book that completed 101 round trips and paid $4.52 of entry fees cannot have a zero cash delta.

**Test 2 — the same trip carries two different numbers.** The exit mechanism computed real, non-zero P&L at the very timestamp `signals.pnl` recorded 0:

| Run | ts | `stop_mechanism.total` | `signals.pnl` | `fee_usd` |
|---|---|---|---|---|
| 1819 | 08-25T21:07:43Z | **−0.9690271402** | 0.00000000 | 0.05750201 |
| 1820 | 08-25T23:57:23Z | **−0.2566679257** | 0.00000000 | 0.05796958 |
| 1821 | 08-25T23:00:00Z | **+0.0185817133** | 0.00000000 | 0.02333276 |
| 1824 | 08-25T23:27:07Z | **+0.0430472722** | 0.00000000 | 0.04343894 |
| 1825 | 08-26T00:01:30Z | **−0.0408358198** | 0.00000000 | 0.04347906 |

Runs 1821 and 1824 carry **positive** mechanism totals. A rule whose best case is exactly $0 by construction cannot produce a positive total. That single fact kills the ratchet explanation on its own.

**The split is agent-scoped, not time-scoped:** agent 6 → 101 of 101 exit legs exactly 0.00000000; agents 5/59/60 → 0 of 202. Agents 6 and 60 traded the same days (08-18, 08-26) with opposite results, so no deploy window explains it. Agent 6 is user 5, the prod test account.

**Why this correction matters more than the claim it replaces:**
1. **Every P&L figure computed from `signals.pnl` or `trading_runs.realized_pnl_usd` for agent 6 is $0 and false**, including the per-agent table earlier in this reading (agent 6 "−$4.52" is entry fees only; the true figure is unknown and non-zero). Ledger replay of `signals` fills, or the `stop_mechanism` totals, are the only trustworthy sources for that account.
2. **The `insufficient cash` sizing gate cannot bind on an account whose cash never moves.**
3. **It compounds the armed scale-up above.** Fleet 41 — the fleet that re-anchored to $1,125 max_bet during this session — is **agent 6**. The consolidation is scaling the one account whose realized P&L is unmeasurable through the normal fields. Nobody can tell from the standard reports whether that 4–8× is working.

**NOT yet determined — do not assert a cause.** Deployed `automation.py` is byte-identical to `main` and has no arithmetic path to exactly 0.00000000 with a non-zero fee; no `UPDATE signals SET pnl` exists in the repo. **Next probe (pre-registered): replay `execute_paper_trade` against agent 6's book in a shadow and observe the written `pnl` — that separates an agent-scoped data condition from a deploy-scoped one.** Until that runs, the mechanism is unknown.

**Method note for future sessions:** the wrong claim was reached by reading a single column (`signals.pnl`) and inferring a mechanism that fit it. The refutation came from cross-checking a SECOND independent record of the same event (`stop_mechanism.total`) and a THIRD (`agents.cash`). A column that agrees with your hypothesis is not evidence until an independent record of the same event agrees too. This is the third time in one cycle that a first-pass measurement in this reading was wrong (see also the identical-mark rate, which took three passes).

### Three-agent cross-check — where they agreed, where they disagreed, and what the disagreement proved

**AGREED, independently, by two different reconstructions:** the window 08-24→08-28T03:30Z realized **−$10.7289**. Agent A reached it by average-cost replay of 78 raw fills matching `compute_run_pnl`; Agent B reached it by a weighted-average-cost ledger (−$10.7287) *and* by the `adapt` realized stream minus entry fees (−$10.7288). Three routes agreeing to $0.0001. Both matched `trading_runs.realized_pnl_usd` exactly on the only three runs where that column was written correctly (1894, 1895, 2001).

**AGREED: the retraction above is right.** Agent B reached it by a different signature — every zero-P&L row also has `entry_price == exit_price`, and run 1748's raw fills (−$5.0032) match the independent `adapt` telemetry (−$5.0032) while the ledger says $0. Agent B widens the scope: the zeros run from **08-15**, not 08-24, and self-resolved on 08-26/08-27. **True net of the concealed block: −$11.2389, recorded as $0.00.**

**⚠️ THE FINDING THAT OUTRANKS THE REST — #592's own justification may rest on the broken column.** The pre-ship baseline quoted in the ship ("30 fires since 08-01, give-back median 103.1% of peak, median realized −$0.0066") was computed over a period in which `signals.pnl` wrote exactly 0 on ~90% of exit legs. If that baseline came from `signals.pnl`, **it is invalid and the fix's justification needs recomputing.** Neither agent could determine the baseline's source. Agent B's recomputation from raw fills gives a materially different picture: **give-back median 91.2%** (not 103.1%), **trip-net median −$0.0568**, sum −$3.0443, 1 of 20 positive. This does not say #592 was wrong — it says the number it was justified with cannot currently be trusted. **Pre-registered follow-up: recompute the pre-ship baseline from raw fills and state whether the ship's premise survives.**

**DISAGREEMENT, and it is the useful kind — the TAO fire.** This session (and the earlier part of this reading) read `peak` and `total` straight off the `stop_mechanism` payload and reported give-back 52.4%. Agent B shows **the payload's `peak`/`total` are run-cumulative, not baseline-adjusted, so reading give-back straight off it is wrong**; recomputed against the equity mark series the figure is 50.2%. More important, Agent B resolved TAO on Hyperliquid 1-minute candles — the same feed prod fills against — and found:

- Old rule floor price = 253.49/(1−0.0009) = **253.7183**, first breached 10:26 (low 253.48) → **+$0.0001**. New rule actual → **+$0.9868**. Delta **+$0.9867**. The "$0 by construction" defect caught in the act, on real candles.
- **But the 50.2% give-back is coincidence, not control.** The mark went 2.3850 (10:13:36) → 1.1881 (10:14:46) in a single ~70 s tick, straight *through* the 1.2934 floor. The rule does not lock half the peak; **it locks whatever the next poll prints.** The poll caught a wick — 10:15 opened at 255.59 and rose.
- TAO ran to **+$6.05 unrealized by 14:11**. Both rules left $5+ on the table. **The ratchet is a give-back limiter, not a trend-capture mechanism**, and must not be sold as one.

**Correction to this session's earlier framing:** "give-back 52.4% of peak, directionally exactly what was designed" overstated it on two counts — the number was computed off the wrong basis, and the outcome was a poll artifact rather than the rule exercising control.

**The defensible value of #592 is +$3.43, not +$4.30.** Agent B rejected the fire-only counterfactual as biased: 20 of the 21 fires are *selected on "the old rule fired"*, i.e. price had already fallen from peak to the fee floor, so a rule that exits earlier can only look good on that sample — 0 losing cases there is a definitional artifact. Replaying the new rule over **all 33 closed segments (26 armed)** gives **+$3.4296, 16 better / 4 worse**; without the largest +$2.2545, without the top two +$1.1843 — sign never flips. The 4 worse are precisely the winners the new rule cuts early (−$0.8485 against +$4.278 of gain). **So #592 reduces the window's loss by 32% and does not make the book profitable. −$10.73 becomes ≈ −$7.30.**

**Where the money actually went — neither agent puts it on the ratchet.** Two runs are 95% of the block: **1785 INJ −$5.6171** (the desk re-bought 86 minutes after its own stop-out falsified the thesis, `plan_adherence: deviated`; and at 10:03:55 held with the mark already below its own $5.80 invalidation) and **1748 LINK −$5.0032** (shorted an instrument it itself described as "firmly above its moving averages", then re-shorted the identical thesis at 2× notional with confidence raised 0.62→0.68 after six cycles of calling that thesis invalidated). Both are desk-authored. Algorithm-authored stops are **22 of 393 stop reasons (5.6%)**.

**Payoff geometry, controlling for direction (Agent A).** 08-25 was one correlated down-leg — one bet taken 23 times. AI longs (wrong side) 12 runs −$9.0392; AI shorts (right side) 11 runs +$2.8034. The losing side paid **3.0× more per trade than the winning side collected**, with direction called correctly 11 of 23. Forced by geometry: ratchet arm 0.200% vs median desk stop 1.85% ⇒ structural payoff ≈ 0.11. Desk-authored targets: median **5.99%**, actual peak reached median **0.215%**, **target reached 0 of 21**. *Caveat both agents flag and this session endorses: the peak is censored by the ratchet, so "targets were fantasy" and "the ratchet never let them run" cannot be separated without a hold-to-target replay. Both remain live.*

### Two operational facts verified by this session directly

**1. The book has stopped trading.** Last fill anywhere: **2026-08-27T14:11:52Z — 13.6 hours before this reading.** Since then **697 decisions, 666 of them `hold` (95.6%)**, zero fills, zero open positions. Consequence: **no pending falsifier can accrue at all** — #592 needs 29 more fires, #589 needs 18 more, and at the current rate that is never, not "30 days".

**2. The desk does not author size.** Of 2,577 `order_params` events since 08-26, only **63 carry a `size_frac` key at all, and 59 of those are `null`**. Agent B's wider count: 127 null vs 10 authored (92.7% unauthored), and **29 clamps across 33 opening legs — 88% of opens are platform-sized**. R17 `null_size_cap` (0.25 × max_bet) is the real binding constraint, not the stale "13 slots × $769" framing (that config is gone; fleets 39/40 actually ran 25 slots at ~$400). **The clamp is currently saving money** — un-clamped, TAO makes ~+$2.35 instead of +$0.99, but scaling the whole window 2.38× turns −$10.73 into ≈ −$25. Removing a cap on a negative-expectancy book is not an improvement. **The defect is that the desk emits `size_frac: null`.**

### Standing corrections to the backlog, by name

- **"Fees are 27–28% of gross"** — stale. Recomputed 08-15→now: gross +$5.6646 vs fees $9.3998 = **166%** (205% stripping the largest winner).
- **"The 13×$769 sizing deadlock"** — stale; that config no longer exists.
- **"The ZI control's n=57 is a real sample"** — refuted. Its own result file shows `strip_largest/ai = 0.0`: one trip carries 100% of the AI's −$6.60 and the other 56 netted exactly $0.00 — the same concealed-ledger defect. **Effective n ≈ 1.** "AI ≈ random at n=57" is a measurement of the broken column, not of entry quality, and the control needs re-running on healthy accounting.
- **`docs/plan/28-zero-entry-solution-2026-08-23.md` does not exist on any branch** (PR #549 unmerged) — readings citing it cannot be followed as written.

---

## Reading #56 — 2026-08-28T04:13Z — quiet; the throughput decay is the consolidation, not a defect

**Profit first: no change. Zero fills. Last fill anywhere is still `2026-08-27T14:11:52Z` — now 14.0 hours.** 0 open positions, 8 runs running. Realized P&L for the period: **$0.00, on no trades.** No new tape, therefore no three-agent dispatch this cycle (the rule requires tape).

**Hypotheses stated before the data, and their outcomes:**
- **H1 — the book is still not trading.** CONFIRMED. 1 fill event since 08-27T14:11:52Z and it is that fill itself.
- **H2 — fleet 42 has not re-anchored.** CONFIRMED. Its four incumbents are unchanged (`max_bet` $180.00, $269.52, $293.63, $335.34; all created 08-27T12:28–16:25Z). Fleet 41 still carries the two re-anchored runs at **$1,125.00** (2106, 2107). The ~40× scale-up on the $100k book remains **armed and undischarged**.
- **H3 — the mark-refresh fix still holds.** Not measurable this cycle: 0 open positions means no mark series to sample. Recorded as unmeasurable, not as a pass.

### A decay I chased and then refuted — recorded so nobody re-chases it

Decision events fell **51/h → 9/h (−82%)** over eight hours. First read: the engine is grinding to a halt. **That is wrong.** The decay is uniform across every event type — `equity` polls fell 1,434 → 454 (−68%), `gate_skip` 61 → 19, `outlook` 58 → 18, all proportional — so nothing is stalling at the decision stage. It tracks the live-run count exactly:

| hour | runs alive | equity | decisions |
|---|---|---|---|
| 08-27T20 | **35** | 1,434 | 51 |
| 08-27T22 | 30 | 1,365 | 55 |
| 08-28T00 | 22 | 963 | 25 |
| 08-28T02 | 14 | 494 | 9 |
| 08-28T04 | **14** (8 `running`) | 454* | 9 |

Stop reasons since 08-27T20:00Z: **`idle_retired` 28, `desk_retired` 12** — 40 runs retired in 8 hours, and `FLEET_TARGET_SLOTS=4` caps replenishment at 4 per fleet = **8 total**. The fleet is draining from 35 slots to its new target of 8, which is precisely what H-CONSOL was shipped to do. **This is the consolidation working, not a defect, and reporting it as one would have been a manufactured finding.** (*04h is a partial hour.)

**The consequence that IS worth stating:** steady-state cycle volume will settle ~77% below the 08-27 level. Combined with 14 hours of zero fills, **every pending falsifier accrues more slowly than the estimates in reading #55, not faster** — #592 needs 29 more fires, #589 needs 18 more, and at zero fills the answer is "never", not "30 days".

**Ruled out, because it was mine to rule out:** the decay began at **08-27T23:00Z, five hours before this session's deploy** (`20260828-readings`, 03:53Z). The deploy did not cause it.

### Unchanged this cycle

Falsifier status carries forward from reading #55 with no new evidence: frozen-mark **PASS** (77.8% → 2.3%, n=171); H-LEDGER guard **not tripped**, `DESK_LEDGER_BLOCK=1` stands; #592 **1 of 30, undecided**; #591 fail-closed **0 of 20, untested**. Prod healthy on `sooppiy-backend:20260828-readings`; `POSITION_REFRESH_INTERVAL=60`, `DESK_LEDGER_BLOCK=1`, `FLEET_TARGET_SLOTS=4` all set; 0 tracebacks in the worker log; feed noise only.

**Still awaiting an owner decision (unchanged from reading #55):** the armed slot scale-up rests on a replay that is mathematically incapable of measuring size. Revert if wanted: remove `FLEET_TARGET_SLOTS` from `/home/ec2-user/sooppiy/.env` and recreate the worker.

---

## Reading #57 — 2026-08-28T05:13Z — the drought has a structural reason: 5 of 8 slots are in a closed market

**Profit first: no change. Zero fills, zero open positions, $0.00 realized.** Last fill anywhere is still `2026-08-27T14:11:52Z` — **15.0 hours**. No new tape, so no three-agent dispatch. Prod healthy on `sooppiy-backend:20260828-reading56`; all flags unchanged.

**Hypotheses stated before the data:** H1 (still no fills) **CONFIRMED**; H2 (fleet 42 not re-anchored) **CONFIRMED** — its four incumbents are byte-identical to last hour and the ~40× scale-up stays armed; H3 (the drain bottomed at 8 running) **CONFIRMED** — the same 8 run IDs, no turnover in an hour.

### Why nothing is entering — and it is not the gate

The desk is **not being blocked; it is not proposing.** Last 6 hours of `decision` events: **`hold` 96, `retire` 1, and zero `buy` or `short`.** `gate_skip` over the last 3h: **"market closed" 31, "decision is 'hold'" 22** — the second is a consequence of the first, not an independent filter. Only 3 `order_discussion` (panel) events fired in 6 hours, because a panel only convenes on a proposal.

**The structural reason, measured:**

| Market | Slots | Symbols | State at this reading |
|---|---|---|---|
| **us-stock** | **5 of 8** | PFE ×2, QCOM, IBM, MSTR | **all gate-skipping "market closed"** (6–7 skips each in 3h) |
| crypto | 2 | LITUSDT, TRUMPUSDT | open 24/7 |
| forex | 1 | AUDCAD | open |

**H-CONSOL cut the fleet 35 → 8 slots, and 62.5% of the survivors are US equities.** US cash equities trade ~6.5h × 5 days ≈ **19% of the week**, so those five slots are structurally unable to trade for roughly four fifths of elapsed time. At this reading (05:13Z, i.e. 22:13 PDT Thursday) the US session has been shut for over 9 hours and does not reopen for another ~8.3. **Effective live capacity right now is 3 slots, not 8.**

**Crypto — the only 24/7 market, and the market every experiment in this stack is measured on — holds 2 of 8 slots.** The two runs that DID re-anchor to the new $1,125 size (2106, 2107, created 03:25/03:31Z) went to crypto and forex, so the mix improves as incumbents recycle; but the five us-stock incumbents were all created 08-27T14:36–16:25Z and none has turned over.

**Why this matters beyond throughput, stated in profit terms:** the pending falsifiers are all measured on crypto trips. With 2 crypto slots and zero fills in 15h, #592 (29 more fires needed) and #589 (18 more) are not merely slow — **they are being measured on a quarter of the fleet.** Reading #56 recorded that consolidation cut cycle volume ~77%; this reading shows the surviving quarter is further reduced by market hours. The two effects compound and neither was part of H-CONSOL's stated justification.

**This is an observation, not a proposed change.** Widening crypto's share of the slots would raise measurement rate, but it would also apply a **measured-negative crypto expectancy (−3.9 bp/trip)** to more capital, which is the opposite of what the evidence supports. The honest statement is that the current mix throttles *measurement* while the consolidation raises *size* — and both moved without an experiment that could measure either. See the armed-scale-up section in reading #55.

**Unchanged:** frozen-mark falsifier **unmeasurable again** (0 open positions — recorded as unmeasurable, not as a pass); H-LEDGER guard **not tripped**, `DESK_LEDGER_BLOCK=1` stands; #592 **1 of 30**; #591 **0 of 20, untested**. Worker log clean — 0 tracebacks, feed noise only.

---

## Reading #58 — 2026-08-28T06:13Z — quiet; nothing changed

**Profit first: no change. Zero fills, zero open positions, $0.00 realized.** Last fill anywhere is still `2026-08-27T14:11:52Z` — **16.0 hours**. No new tape, so no three-agent dispatch.

Every hypothesis stated before the data was confirmed, and none of them moved: **H1** no fills; **H2** fleet 42's four incumbents unchanged ($180.00, $269.52, $293.63, $335.34) with the ~40× scale-up still armed and undischarged; **H3** the slot mix is identical to reading #57 — 5 us-stock (PFE ×2, QCOM, IBM, MSTR, all still "market closed"), 2 crypto, 1 forex — so effective live capacity remains **3 slots of 8**. Hourly event counts are flat against last hour (equity 472, gate_skip 17, outlook 14, decision 6). Prod healthy on `sooppiy-backend:20260828-reading57`; flags unchanged; worker log clean.

**The one thing that did move — and it settles a mechanism question from reading #56.** `desk_memory` monitoring chunks went **1,456 → 1,459**, newest `2026-08-28T05:16:37Z`, i.e. reading #57 ingested roughly three minutes after its deploy. This **confirms** the corrected model recorded last cycle: ingestion is not triggered by the deploy but by `maybe_ingest` inside a run cycle (`run_engine.py:7754`), with `_last_ingest_epoch` resetting on worker restart so the first post-deploy cycle carries it. The dependency stands: **if the fleet ever stops cycling entirely, notes stop reaching the corpus no matter how often prod is deployed** — and with cycles at ~6/hour that margin is thinner than it was at 51/hour.

**Falsifiers, all carried forward with no new evidence:** frozen-mark **unmeasurable** for the third consecutive cycle (0 open positions — recorded as unmeasurable, never as a pass); H-LEDGER guard **not tripped**, `DESK_LEDGER_BLOCK=1` stands; #592 **1 of 30**; #591 **0 of 20, untested**. At zero fills none of them can accrue.

---

## Reading #59 — 2026-08-28T07:13Z — P0's falsifier PASSES; one claim of mine corrected

**Profit first: no change. Zero fills, zero open positions, $0.00 realized.** Last fill anywhere is still `2026-08-27T14:11:52Z` — **17.0 hours**. No new tape, so no three-agent dispatch.

### P0 accountability — measured, not assumed

P0 (Plan 29) removed `FLEET_TARGET_SLOTS` and restored `n_runs` to 25 on both fleets one hour ago. Its falsifier was: **new runs must be funded at the disarmed size, and `n_runs` must not revert.** Both held.

| Hypothesis (stated before the data) | Result |
|---|---|
| H1 — `n_runs` stays 25, no re-consolidation | **CONFIRMED** — 25 on both fleets across the hour; `FLEET_TARGET_SLOTS` absent from `.env` and from the worker env |
| H2 — new runs funded at the disarmed size | **CONFIRMED** — every run created this hour carries **exactly `180.0`** (fleet 41) or **`1800.01`** (fleet 42). Not $1,125. Not $11,250. |
| H3 — still no fills | **CONFIRMED** |
| H4 — fleet grows toward 25/fleet | **CONFIRMED** — 8 → **31 live runs** (fleet 42: 21, fleet 41: 10) |

Runs created this hour: 2133 AVAXUSDT ($180.00), 2132 AUDJPY ($1,800.01), 2131 RTY ($180.00), 2130 ZB, 2129 TAOUSDT, 2128 HYPEUSDT, 2127 ZC, 2126 UNIUSDT (all $1,800.01). **The ~20× armed scale-up is gone, confirmed by actual funding rather than by config.**

### CORRECTION — "total exposure is unchanged" was wrong about the live book

Reading the P0 entry in Plan 29, this session wrote: *"Total exposure is unchanged (25 × $1,800 ≡ 4 × $11,250 = $45,000)."* That is true of the **fully-built steady state** and **misleading about the actual book**, which was never fully built at 4 slots.

| | Before P0 | After P0 (this reading) |
|---|---|---|
| Live runs | 8 | **31** |
| Σ `max_bet_usd` | ≈ **$3,719** | **$35,371.10** (fleet 42 $31,678.66 / fleet 41 $3,692.44) |

Fleet 42 held only four *legacy* runs at $180–$335 when P0 ran; the $11,250 was what its *next* runs would have received. Restoring `n_runs=25` removed the size spike **and** restored slot count, so the fleet is rebuilding. **Potential deployment rose ~9.5×**, and that consequence was not stated when the change was made.

**Why this is still the right trade, stated with the numbers rather than asserted:** per-trade size fell 6.25×, which is the axis that matters given 9-of-9 adverse exit slippage and superlinear impact; 31 runs is **historically normal** for this platform (08-27 carried **188 runs alive**, and the consolidation to 8 was the anomaly); actual capital at risk right now is **$0** (no open positions); and orders clamp to 0.25 × `max_bet` at R17. **But the honest framing is "size down, count restored", not "exposure unchanged."**

### Load consequence of a 4× run-count increase — checked, clean

| hour | decisions | `no_verdict` | `verdict_salvaged` | equity |
|---|---|---|---|---|
| 04 | 6 | 0 | 0 | 456 |
| 05 | 6 | 0 | 0 | 464 |
| 06 | **17** | **0** | **0** | 621 |
| 07 (partial) | 16 | **0** | **0** | 400 |

Decision volume tracks run count as expected. **Zero `no_verdict` and zero `verdict_salvaged` across the increase** — no LLM oversubscription, which was the live risk given [[admin-local-ai-switch-noop]]'s ~5× contention finding. Worker log: **0 tracebacks in 15 minutes.**

**Falsifiers carried forward, no new evidence:** frozen-mark **unmeasurable** for a fourth consecutive cycle (0 open positions — recorded as unmeasurable, never as a pass); H-LEDGER guard **not tripped**, `DESK_LEDGER_BLOCK=1` stands; #592 **1 of 30**; #591 **0 of 20, untested**. At zero fills none can accrue. Prod healthy on `sooppiy-backend:20260828-p0p1`.

---

## Reading #60 — 2026-08-28T08:13Z — P0 became an experiment: proposals doubled, the panel demoted 100%

**Profit first: no change. Zero fills, zero open positions, $0.00 realized.** Last fill anywhere is still `2026-08-27T14:11:52Z` — **18.0 hours**. No completed trips, so no three-agent dispatch. **But this is not a quiet cycle** — P0 restored slot count and thereby ran an unplanned experiment whose result is unambiguous.

### The experiment P0 accidentally ran

P0 restored `n_runs` to 25, and the supervisor rebuilt the fleet. That multiplied both the decision opportunity and, crucially, the **crypto** slot count:

| | Before P0 | Now |
|---|---|---|
| Live runs | 8 | **35** (fleet 42 at its 25 target, fleet 41 building at 10) |
| Crypto slots | **2** | **14** |
| Market mix | 5 us-stock / 2 crypto / 1 forex | crypto 14 / futures 9 / forex 7 / us-stock 5 |
| Decisions per hour | 6 | **66** (07h) |

**Result on the entry funnel:**

| Window | Panel meetings | Entry proposals | Kept | Rate |
|---|---|---|---|---|
| Prior 24h | 61 | 42 (**1.75/h**) | **1** | **2.4%** |
| Since P0 (~2h) | 9 | 8 (**4.0/h**) | **0** | **0%** |

**Two findings, and they point in opposite directions from each other:**

1. **Capacity DOES move proposals.** The proposal rate rose **2.3×** (1.75/h → 4.0/h) purely from restoring slots, most of them crypto. Reading #57's picture — a desk proposing nothing for six hours — was a consequence of having only 2 crypto slots among 8, not of the desk having gone silent.
2. **The panel is now unambiguously the binding stage.** Every one of the 8 entry proposals was demoted. All four in the most recent hour were `buy`, and all four were flipped to `hold`:

| ts | run | proposed | final |
|---|---|---|---|
| 07:23:48Z | 2126 | buy @ 0.62 | hold @ 0.55 |
| 07:25:01Z | 2123 | buy @ 0.63 | hold @ 0.56 |
| 07:37:43Z | 2121 | buy @ 0.55 | hold @ 0.48 |
| 07:41:27Z | 2126 | buy @ 0.60 | hold @ 0.56 |

Mean confidence is shaved **0.603 → 0.536** across the meetings. This reproduces the 9-day figure independently (342 proposals, 3 kept by a working panel = 0.93%) and matches [[entry-collapse-traced-to-reachability]] (#413/#414, 98.2% of buys demoted).

**Method correction, recorded because it nearly produced a false finding.** A first pass using `payload LIKE '%"action": "buy"%'` on `decision` events reported **zero buy proposals**. That is wrong: the `decision` event records the **FINAL** action, so a demoted buy is stored as `hold`. Proposals are only visible in `order_discussion.proposed.action`. **Any funnel counted off `decision` events alone understates proposals by exactly the panel's demotion rate** — which is ~100%, so it reports the desk as silent when it is in fact proposing and being overruled.

### What this does and does not settle

It **sharpens** Plan 29 rather than changing its conclusion. Capacity was never the constraint on *entries* — 0 fills in 18h stands — but it is a constraint on *proposals*, and the proposal stage is upstream of the real chokepoint. The chokepoint is stage E.

**It does not tell us whether the panel is right to demote.** Two measured facts remain in tension and only a replay can settle them: Plan 29 measured gross edge at **−20.76 bp before any fee** and the 08-25 panel outage produced **−$6.15 with 9 of 22 correct calls still losing** (panel right); while the Phase 1 redesign measured **crypto demotions as wrong, +$145 over 8 days, robust** (panel wrong in crypto specifically). **The fleet is now 14/35 crypto, so this tension is about to be exercised at 7× the previous crypto exposure.** That is the P2/P3 question and it should not be pre-judged from either side.

### Load and falsifiers

At 66 decisions/hour — an **11× increase** over the pre-P0 rate — `no_verdict` **0** and `verdict_salvaged` **0**, worker log 0 tracebacks. No LLM oversubscription at the higher load. Frozen-mark falsifier **unmeasurable** for a fifth consecutive cycle (0 open positions — recorded as unmeasurable, never as a pass); H-LEDGER guard **not tripped**; #592 **1 of 30**; #591 **0 of 20, untested**. Prod healthy on `sooppiy-backend:20260828-reading59`.

---

## Reading #61 — 2026-08-28T09:13Z — nothing changed in kind; the panel sample grew to 13 of 13

**Profit first: no change. Zero fills, zero open positions, $0.00 realized.** Last fill anywhere is still `2026-08-27T14:11:52Z` — **19.0 hours**. No completed trips, so no three-agent dispatch.

All four hypotheses stated before the data were confirmed and none moved: **H1** no fills; **H2** panel keep rate stays 0%; **H3** proposal rate holds (5 this hour vs 4 last); **H4** the fleet keeps building — fleet 42 at its 25 target, fleet 41 now 17 (was 10), **42 runs total**, mix crypto **20** / futures 10 / forex 7 / us-stock 5.

**The one quantity that advanced — the panel sample.** Cumulative since P0 (06:20Z):

| | Value |
|---|---|
| Entry proposals | **13** |
| Kept | **0 (0%)** |
| Proposed confidence range | **0.550 – 0.680** |
| Final action | **`hold` on all 13** (best final confidence 0.620) |

Every proposal is converted to `hold` **regardless of conviction**, including proposals at 0.68 that sit well clear of the 0.57 `min_confidence` gate for an aggressive fleet. This is why the confidence gate never fires: the panel resolves to `hold` upstream of it, so the gate has nothing to evaluate. n=13 at 0% is fully consistent with the 9-day baseline of 342 proposals / 3 kept (0.93%) — **the panel is not behaving unusually; the sample is simply accruing faster now that capacity is restored.** Nothing here is a new finding, and it is not reported as one.

**Health:** 78 decisions in the hour, `no_verdict` 0, `verdict_salvaged` 1, 0 trades, 0 tracebacks. Prod healthy on `sooppiy-backend:20260828-reading60`.

**Falsifiers carried forward, no new evidence:** frozen-mark **unmeasurable** for a sixth consecutive cycle (0 open positions — recorded as unmeasurable, never as a pass); H-LEDGER guard **not tripped**; #592 **1 of 30**; #591 **0 of 20, untested**. At zero fills none can accrue.

---

## Reading #62 — 2026-08-28T10:13Z — quiet; nothing changed

**Profit first: no change. Zero fills, zero open positions, $0.00 realized.** Last fill anywhere is still `2026-08-27T14:11:52Z` — **20.0 hours**. No completed trips, so no three-agent dispatch. Every hypothesis stated before the data was confirmed and none moved.

**Panel sample since P0 advanced to 20 entry proposals, 0 kept (0%)** — 7 proposals this hour, all demoted. At the 9-day baseline keep rate of 0.93% the expected number kept at n=20 is **0.19**, so observing zero is unremarkable (p≈0.83) and is **not** evidence that anything worsened. Recorded only because n is the quantity that will eventually make the panel question decidable.

Fleet 42 holds its 25 target; fleet 41 is 16 (was 17 — normal idle-retire/rebuild churn), **41 runs total**. Health: 78 decisions, `no_verdict` 0, `verdict_salvaged` 1, 0 tracebacks. Prod healthy on `sooppiy-backend:20260828-reading61`.

**Falsifiers carried forward, no new evidence:** frozen-mark **unmeasurable** for a seventh consecutive cycle (0 open positions — recorded as unmeasurable, never as a pass); H-LEDGER guard **not tripped**; #592 **1 of 30**; #591 **0 of 20, untested**.

**Operational note, flagged not acted on.** The deploy cadence rule puts us in mode ① (deploy every cycle) until the first fill, and that trigger has not fired. But the cost side has changed since the rule was set: the fleet now carries **41 live runs producing ~7 proposals/hour**, so each hourly deploy restarts a worker that is materially busier than the 8-run, 0-proposal book the rule was written against. Still correct under the rule as written; worth the owner's attention if the drought continues.

---

## Reading #63 — 2026-08-28T11:13Z — quiet; nothing changed

**Profit first: no change. Zero fills, zero open positions, $0.00 realized.** Last fill anywhere is still `2026-08-27T14:11:52Z` — **21.0 hours**. No completed trips, so no three-agent dispatch. Every hypothesis stated before the data was confirmed and none moved. Fleet 42 at its 25 target, fleet 41 at 17, **42 runs total**. Health: 75 decisions, `no_verdict` 0, `verdict_salvaged` 0, 0 tracebacks. Prod healthy on `sooppiy-backend:20260828-reading62`.

**Panel sample since P0: 24 entry proposals, 0 kept (4 this hour).** Rather than keep reporting a growing zero, here is when it becomes decidable — computed once so future cycles can stop re-deriving it:

| Question | Answer |
|---|---|
| Baseline keep rate (9-day, 342 proposals / 3 kept) | **0.93%** |
| P(0 kept \| n=24) if the rate is unchanged | **0.799** — unremarkable |
| n needed for "0 kept" to be significant at p<0.05 | **321 proposals** |
| Time to reach it at the current ~5 proposals/hour | **≈64 hours ≈ 2.7 days** |

**So the panel-demotion question is not answerable by observation before roughly 2026-08-31**, and every reading until then that reports a growing zero is reporting noise, not a finding. This is the same class of problem as #592 (n=1 of 30) and #591 (0 of 20): **the falsifiers this stack is carrying are all sample-starved, and the drought makes them slower still.** The decidable path remains replay (Plan 29 P2/P3), not accrual.

**Falsifiers carried forward, no new evidence:** frozen-mark **unmeasurable** for an eighth consecutive cycle (0 open positions — recorded as unmeasurable, never as a pass); H-LEDGER guard **not tripped**; #592 **1 of 30**; #591 **0 of 20, untested**.

---

## Reading #64 — 2026-08-28T12:13Z — quiet tape; P2's premise examined and KILLED

**Profit first: no change. Zero fills, zero open positions, $0.00 realized.** Last fill anywhere is still `2026-08-27T14:11:52Z` — **22.0 hours**. No completed trips, so no three-agent dispatch. Fleet 42 at its 25 target, fleet 41 at 17, **42 runs**. Panel since P0: **27 entry proposals, 0 kept** (still far short of the n=321 needed to mean anything — reading #63). Health: 79 decisions, `no_verdict` 2, `verdict_salvaged` 1, 0 tracebacks.

Since reading #63 established that no falsifier here is answerable by waiting, this cycle was spent on **Plan 29 P2** instead. The result is that **P2's stated premise is dead.**

### P2's premise was wrong — the ZI control never used the corrupted column

Plan 29 (and readings #55, #60) carried this claim, sourced from an agent and propagated by this session without independent checking:

> *"The ZI control's n=57 was degenerate — 56 of 57 trips netted exactly $0.00 from the settlement defect ⇒ effective n≈1. Recovering `reset6_bak_signals` unblocks a re-run."*

**Checked against the actual input, `research/ai_trips_20260815_27.json`: FALSE.** The file contains **0 of 57 nets equal to zero**. Every trip carries a real value (min −6.5993, max +6.2438, median −0.0462, 18 positive / 39 negative), and the file's own fields (`entry_px`, `fees_usd`, `notional_usd`) show it was built by **fill-price replay** — it never read `signals.pnl`. **The ZI control was never contaminated by the agent-6 reset, and recovering the backup did not unblock it.** P2 as written is cancelled.

**Where the "degenerate" impression came from — and it is a real methodological trap.** The result file reports `strip_largest: {ai: 0.0, ...}`. That is true, and misleading:

| Robustness test | Total |
|---|---|
| All 57 | **−6.5968** |
| Strip 1 largest-\|·\| | **+0.0025** — sign FLIPS |
| Strip 2 largest (both FIL) | **−6.2413** — negative again |
| Strip 4 largest | **+4.3790** — flips AGAIN |
| 47 small trips only (\|net\| ≤ $1) | **−6.0897**, median **−0.0513** |
| Trimmed mean (drop 3 per tail), scaled to n | **−2.5707** |

The two largest trips are **FILUSDT shorts of nearly equal and opposite size** — run 1531 **−6.5993** and run 1322 **+6.2438**, both agent 6. Stripping only the largest deletes one half of an offsetting pair, which is why the sign flips. Stripping four removes two big losers (INJ −5.6171, LINK −5.0032) and flips it the other way.

**METHOD FINDING, and it applies to every past and future use of the owner's outlier law here: the strip-largest test is not valid when the top contributors offset each other.** A single-strip sign flip is evidence of an offsetting pair, not necessarily of a fragile result. The defensible statement on this cohort is split:

- **The TYPICAL trip is robustly negative** — median −$0.0513, trimmed mean equivalent −$2.5707, and the 47 trips under $1 sum to **−$6.0897** on their own, i.e. nearly the entire book loss comes from the *mass* of ordinary trips, not from outliers.
- **The TOTAL is fragile** — four large trips swing it between −$6.60 and +$4.38 depending on how many are excluded. Any claim about the total alone should be treated as inconclusive.

### What P2 actually needs, restated

The ZI control's verdict stands as originally reported and for a legitimate reason that has nothing to do with data corruption: its own **`mean_trip_diff_CI90` is [−0.3139, +0.4624], which includes 0.** AI entry selection is **not distinguishable from random-with-rails** — and that is a *power* problem, not a *data* problem.

There is a second, independent flaw worth fixing when it is re-run: the arms are **asymmetric**. `ai_nets = [t["net_usd"] for t in cohort]` takes the AI arm from the **real ledger**, while the ZI arm comes from `simulate_trip()`. Real fills carry real slippage and booked fees; simulated trips carry modelled ones. **A correct control simulates BOTH arms through identical rails and differs only in entry selection.** That, plus enough power, is the actual P2 — not a data re-run.

**Corrections to the record, by name:** the "56 of 57 netted exactly $0.00" mechanism is **dead**; "recovering the backup unblocks P2" is **dead**; "effective n≈1" is **half-right** — the total is outlier-sensitive, but the central tendency is not, and the reason is an offsetting pair rather than a settlement defect. This session propagated all three without checking the input file, and they had reached Plan 29 and two readings before this cycle caught them.

**Falsifiers carried forward, no new evidence:** frozen-mark **unmeasurable** for a ninth consecutive cycle; H-LEDGER guard **not tripped**; #592 **1 of 30**; #591 **0 of 20, untested**.

---

## Reading #65 — 2026-08-28T13:13Z — quiet tape; P2 RUN properly, and it converges on the payoff-ratio diagnosis

**Profit first: no change. Zero fills, zero open positions, $0.00 realized.** Last fill anywhere is still `2026-08-27T14:11:52Z` — **23.0 hours**. No completed trips, so no three-agent dispatch. Fleet 42 at its 25 target, fleet 41 at 17, **42 runs**. Panel since P0: **32 entry proposals, 0 kept** (n=321 needed before that means anything — reading #63). Health: 70 decisions, `no_verdict` 0, `verdict_salvaged` 0, 0 tracebacks.

Cycle spent on **Plan 29 P2**, rebuilt to fix the asymmetry reading #64 identified. Script and result committed: `research/zi_control_symmetric.py`, `research/zi_control_symmetric_result_20260828.json`.

### The fix

The original control took the AI arm from the **ledger** (`net_usd`) and the ZI arm from `simulate_trip()` — real fills against modelled ones. The rebuild runs **both arms through identical rails** (same 1.5%/4.5% brackets, same #592 ratchet, same fee and slippage model, same notional) and differs **only in entry selection**. A third arm was added: random entry time but the **AI's own side**, which isolates the value of its directional call from its timing.

Pre-registered before running: **H0 — AI entry selection has no edge over random.** Falsifier: CI90 of the paired mean difference excludes 0 (above → edge; below → worse than random); contains 0 → INCONCLUSIVE, reported as such.

### Result (n=57, 400 draws, realistic 0.03% slippage basis)

| Arm | mean | **median** | trimmed mean | total |
|---|---|---|---|---|
| AI, its actual entries | **−0.3298** | **−0.0119** | −0.1847 | −18.797 |
| ZI — random time, random side | −0.2298 | −0.1353 | −0.1774 | −13.100 |
| ZI — random time, **AI's own side** | −0.2300 | −0.0888 | −0.1455 | −13.108 |

**Paired mean difference −0.1000, CI90 [−0.5221, +0.3288] → INCONCLUSIVE.** Same verdict at the 0.16% basis (CI90 [−0.5591, +0.3270]). The headline is unchanged from the original control, but now for a defensible reason: **AI entry selection is not distinguishable from random-with-rails at n=57**, and the CI is ~0.85 wide against a 0.10 effect — a **power** problem, exactly as reading #64 predicted.

### Three findings the symmetric design exposes that the original could not

**1. The statistics disagree in SIGN, and the disagreement is the finding.** Mean says AI is worse (−0.100); **median says AI is better (+0.1235)**; trimmed mean says they are the same (−0.0073). That pattern is the signature of a **better typical trip with a worse loss tail** — which is precisely Plan 29's payoff-ratio diagnosis (healthy hit rate, broken magnitude), now reproduced by an entirely independent method. *Stated as a directional observation, not a verdict: the median difference carries no CI here and needs its own test before anyone acts on it.*

**2. The AI's directional bias is worth exactly nothing.** The cohort is 40 short / 17 long — a 70% short book. Giving the random arm the AI's **own side** with random timing changes its result by **−0.000150 per trip**. Whatever the desk knows, it is not direction: its side call carries no measurable information once timing is randomised.

**3. The rails lose money for ANY entry.** Random entries through the house structure lose **−0.2298/trip (mean), −0.1353 (median)** at the realistic basis. **Entry selection cannot rescue this**: even a perfect random draw is negative before any question of skill. This is the strongest argument yet that Plan 29's ordering is right — **P3 (payoff geometry) is the job, and entry-side work cannot pay until the rails stop being negative-expectancy on their own.**

### What this does NOT show

It does not show the AI is worse than random — the CI includes zero and this session will not round it. It does not measure size (all figures are per-unit-notional). And n=57 remains the binding limit: at the observed dispersion, separating a 0.10/trip effect needs far more cohort than the live book will produce this year, so **any future ZI work must come from replay depth, not from waiting for fills.**

**Falsifiers carried forward, no new evidence:** frozen-mark **unmeasurable** for a tenth consecutive cycle; H-LEDGER guard **not tripped**; #592 **1 of 30**; #591 **0 of 20, untested**.

---

## Reading #66 — 2026-08-28T14:13Z — 24h flat; P3 rail sweep finds a monotone payoff dial, and it argues against #592

**Profit first: no change. Zero fills, zero open positions, $0.00 realized.** Last fill anywhere is `2026-08-27T14:11:52Z` — **exactly 24.0 hours**. No completed trips, so no three-agent dispatch. 42 runs; panel since P0 **40 entry proposals, 0 kept**; health 75 decisions, `no_verdict` 0, `verdict_salvaged` 3, 0 tracebacks.

### H3 settled by natural test: market hours were a ceiling, not the constraint

The US session opened at 13:30Z. Since then us-stock logged **18 decisions and ZERO "market closed" skips** — those five slots are genuinely live and cycling for the first time in this reading series — and produced **no entries**. Reading #57 correctly identified market hours as a structural ceiling (46% of slot-hours tradeable); this reading shows removing that ceiling changes nothing, because the binding constraint is downstream.

### P3 — rail sweep (committed: `research/rail_sweep.py`, `research/rail_sweep_result_20260828.json`)

Reading #65 measured that **random entries lose −0.23/trip through the house rails**, i.e. the structure is negative before entry skill enters. **Pre-registered H-RAILS:** there exists a (stop, target, ratchet_frac) setting under which random entries are non-negative on this tape. **Falsifier:** no configuration in the grid is non-negative → tape and fee floor dominate and bracket geometry is the wrong target.

**H-RAILS: SUPPORTED — 2 of 42 configurations are non-negative.** 42 configs × 57 trips × 120 draws.

**Two independent monotone gradients, which is why this is structure and not noise:**

| Ratchet lock (avg over all stop/target) | mean | median |
|---|---|---|
| frac 0.0 | **−0.1249** | −0.1632 |
| **frac 0.5 — LIVE (#592 default)** | −0.2167 | −0.0337 |
| frac 0.9 | **−0.2381** | **+0.0032** |

| Target, frac=0 | mean |
|---|---|
| 0.010 | −0.2476 |
| 0.020 | −0.2348 |
| **0.045 — LIVE** | −0.1521 |
| 0.080 | **−0.0072** |

**Live config (stop 0.015 / target 0.045 / frac 0.5): mean −0.1898, median +0.0023.**
**Best (stop 0.015 / target 0.080 / frac 0.0): mean +0.0580, median −0.1556. Delta +0.2478 per trip.**

### The finding that matters: #592's own falsifier measures the wrong quantity

**As the ratchet lock rises, the mean gets monotonically WORSE and the median monotonically BETTER.** That is the payoff-ratio dial made explicit — locking converts a few large winners into many small ones.

#592 (`RATCHET_LOCK_FRAC=0.5`) was shipped with this falsifier: *"median give-back must fall below 100% of peak AND median realized must be POSITIVE."* **Both are median statistics — exactly the quantity a higher lock fraction improves by construction.** The sweep says the lock simultaneously degrades the mean, and **the mean is what compounds.** So **#592 can PASS its own falsifier while making the book lose more money.** That is a defect in the falsifier, not necessarily in the fix, and it should be corrected before its 30-fire verdict is read: **#592's accountability metric must include the mean, not only the median.**

### What this does NOT license — no config change is proposed

1. **No confidence intervals.** Each cell is a well-sampled mean (6,840 simulated trips) but no CI was computed; +0.0580 could still be noise against the cell-to-cell spread.
2. **One window, one regime.** The tape is 12 days (08-15→08-27) heavy in crypto down-legs. A far-target/no-lock configuration is a trend-following profile and will look very different in a chop regime.
3. **Random entries, not the AI's.** The sweep varies rails under zero-intelligence entry; the interaction with actual desk entries is unmeasured.
4. **The winning config has a NEGATIVE median (−0.1556)** — most trips lose, and a few far-target winners carry it. That is a materially different risk profile from what is running, and the owner's own outlier discipline applies to it.

**Required before any rail change ships:** bootstrap CI on the top cells, a second non-overlapping window, and a run using the AI's actual entries rather than random ones. Until those exist this is a **lead, not a result to implement.**

**Falsifiers carried forward:** frozen-mark **unmeasurable** for an eleventh consecutive cycle; H-LEDGER **not tripped**; #592 **1 of 30** (and see above — its metric needs revision); #591 **0 of 20, untested**.

---

## Reading #67 — 2026-08-28T15:13Z — the #66 rail lead is REFUTED on validation

**Profit first: no change. Zero fills, zero open positions, $0.00 realized.** Last fill anywhere is `2026-08-27T14:11:52Z` — **25.0 hours**. No completed trips, so no three-agent dispatch. 42 runs; panel since P0 **43 entry proposals, 0 kept**; health 82 decisions, `no_verdict` 1, `verdict_salvaged` 0, 0 tracebacks.

### P3 validation — and it kills yesterday's lead

Reading #66 reported **H-RAILS: SUPPORTED** and a "best" cell (stop 0.015 / target 0.080 / ratchet frac 0.0) worth **+0.2478/trip** over the live config, while explicitly refusing to ship it until three checks were done. Those checks are now done, committed as `research/rail_validate.py` + result JSON.

**Pre-registered before running:** the lead survives only if its advantage over the live cell holds with **CI90 excluding 0 in BOTH half-windows AND on real entries.** Any failure → regime- or method-specific, must not ship.

| Config | full window | H1 (first half) | H2 (second half) | AI's real entries |
|---|---|---|---|---|
| **LIVE** (0.015/0.045/0.5) | −0.1898 **[−0.2435, −0.1369]** | −0.0747 **[−0.1182, −0.0294]** | −0.2810 **[−0.3173, −0.2428]** | −0.3298 [−0.8101, +0.0834] |
| **"BEST"** (0.015/0.080/0.0) | +0.0580 **[−0.0374, +0.1554]** | **+0.4270** [+0.3384, +0.5157] | **−0.3144** [−0.3732, −0.2543] | −0.2119 [−0.7640, +0.4445] |
| ALT (0.025/0.080/0.0) | +0.0164 [−0.0846, +0.1182] | +0.4368 | −0.3501 | +0.1055 [−0.4002, +0.7288] |

**BEST minus LIVE:** full **+0.2478** (CIs disjoint), H1 **+0.5017** (CIs disjoint), **H2 −0.0334 (CIs OVERLAP — and the sign FLIPS)**, **real entries +0.1179 (CIs OVERLAP)**.

### VERDICT: H-RAILS as supported in reading #66 is REFUTED

1. **The headline was never significant.** The full-window +0.0580 carries **CI90 [−0.0374, +0.1554] — it includes zero.** Reading #66 reported "2 of 42 configurations non-negative" without a CI, and that framing was wrong: a point estimate above zero is not a non-negative configuration.
2. **It is regime-specific, dramatically.** The same cell is **+0.4270 in the first half and −0.3144 in the second** — both with tight, disjoint CIs. A far-target/no-lock bracket is a trend-following profile; it earns in a trending window and bleeds in the other. **Half the tape would have produced the opposite recommendation.**
3. **It does not survive on real entries.** Against the AI's actual entry points the advantage is +0.1179 with overlapping CIs — indistinguishable from the live config.

**The monotone gradients in #66 were real** (lock ↑ → mean ↓, median ↑; wider target → higher mean) **but the magnitude of the winning cell was regime luck, not an edge.** Recorded so no future session re-runs this: **a far target with the ratchet disabled is NOT a proven improvement.**

### What DID survive, and it matters

**The live rails are significantly negative in every window tested** — full [−0.2435, −0.1369], H1 [−0.1182, −0.0294], H2 [−0.3173, −0.2428], all excluding zero. That is now the most robust single fact in this stack: **the current bracket geometry loses money on random entries across both regimes, and we do not yet have a proven better one.** Plan 29's ordering stands; its P3 does not yet have an answer.

**Also unchanged and still owed:** the #66 finding that **#592's falsifier is defined purely on medians** — the exact quantity a higher lock improves by construction, while the mean it degrades is what compounds. That correction is independent of today's refutation and still needs applying before #592's 30-fire verdict is read.

**Falsifiers carried forward:** frozen-mark **unmeasurable** for a twelfth consecutive cycle; H-LEDGER **not tripped**; #592 **1 of 30**; #591 **0 of 20, untested**.

---

## Reading #68 — 2026-08-28T16:13Z — quiet; #592's falsifier corrected and made decidable

**Profit first: no change. Zero fills, zero open positions, $0.00 realized.** Last fill anywhere is `2026-08-27T14:11:52Z` — **26.0 hours**. No completed trips, so no three-agent dispatch. 42 runs; panel since P0 **44 entry proposals, 0 kept**; health 85 decisions, `no_verdict` 0, `verdict_salvaged` 2, 0 tracebacks, 0 `stop_mechanism` fires.

### The one item that survived #67's refutation, now resolved

Reading #66 found that **#592's falsifier is defined purely on medians** — *"median give-back must fall below 100% of peak AND median realized must be POSITIVE"* — while the rail sweep showed the lock fraction moves **median UP and mean DOWN monotonically**. A median-only criterion is therefore biased toward passing by construction, and the mean is what compounds.

**Power analysis on the actual pre-ship fire population (n=20 `stop_mechanism` trip NETs):**

| | value |
|---|---|
| MEAN | **−0.1522** ← what compounds |
| MEDIAN | −0.0568 ← what the falsifier uses |
| SD | 0.2893 |
| positive | **1 of 20** |

| Mean shift to detect (α=.10 one-sided, power .80) | n per arm |
|---|---|
| +0.0500 | 151 |
| **+0.1000** | **38** |
| +0.1522 (reaches break-even) | **16** |
| +0.3000 | 4 |

**CORRECTION to this session's own framing in #66/#67.** Those readings implied the mean might not be decidable at n=30 — carrying forward an n≈690 figure. **That figure belongs to a different population**: it was derived from *all trips* at SD 88.4 bp, whereas the `stop_mechanism` fire subpopulation has SD 0.2893 in dollars and is far tighter. **At n=30 the CI90 half-width on the mean is ±0.0869**, so a mean criterion IS usable — it can resolve any shift of roughly +0.11/fire or larger.

### Corrected falsifier for #592, to be applied when the 30 fires accrue

Replace the median-only test with **both** conditions, and report the interval rather than a binary:

1. **PRIMARY — mean.** Mean realized per fire over the first 30 fires, with bootstrap CI90, compared against the pre-ship mean of **−0.1522** (n=20). **#592 FAILS if the post-ship mean CI90 does not lie above the pre-ship mean.** State the CI; do not reduce it to pass/fail.
2. **SECONDARY — median (the original test), retained but demoted.** Median give-back below 100% of peak and median realized positive. **Passing this alone is NOT sufficient** and must never be reported as #592 working.
3. **Power caveat, stated in advance.** #592's own claimed effect is **+$0.104 per segment** (the two-sided counterfactual, +$3.4296 over 33 segments). Detecting that at 80% power needs **n=38**, so **n=30 gives roughly 70% power for the effect actually claimed.** A null result at n=30 is therefore **INCONCLUSIVE, not FAILED** — and this must be pre-committed now, before the data arrives, so the standard cannot be moved afterwards.

**Current status unchanged: #592 stands at 1 of 30 fires** (zero `stop_mechanism` fires this hour, and none since the drought began). At the current rate this verdict is not reachable; the correction above matters for whenever trading resumes.

**Falsifiers carried forward:** frozen-mark **unmeasurable** for a thirteenth consecutive cycle; H-LEDGER **not tripped**; #591 **0 of 20, untested**.

---

## Reading #69 — 2026-08-28T17:13Z — P1b cancelled (the data already exists) and conviction measured: it predicts NOTHING

**Profit first: no change. Zero fills, zero open positions, $0.00 realized.** Last fill anywhere is `2026-08-27T14:11:52Z` — **27.0 hours**. No completed trips, so no three-agent dispatch. 42 runs; panel since P0 **45 entry proposals, 0 kept**; health 88 decisions, `no_verdict` 0, `verdict_salvaged` 1, 0 tracebacks.

### P1b is CANCELLED — the instrumentation gap does not exist

Plan 29 P1b was written to "persist the desk's confidence on every closed trip", on an agent's report that *"no conviction/confidence score is persisted per closed trip, so I could only sign the direction, not size it."* **That is false.** The link is already there:

- `signals.client_order_id` on every entry is `run:<run_id>:cyc:<n>` — it encodes the run **and the cycle**
- the `decision` event payload carries `cycle`, `confidence`, `conviction`, and four sub-scores (`thesis_alignment`, `momentum_quality`, `entry_quality`, `risk_context`)
- joining on `run_id` + `cycle` recovers all of it

**Coverage: 153 of 153 entry fills carry the `:cyc:` tag — 100%.** Verified 1:1 (no entry matches more than one decision event). **No code change is needed and none was made.**

### The measurement that gap was blocking, now run: conviction has NO predictive power

**First pass, in dollars, looked like a dramatic inversion:**

| conviction | n | mean net $ | total $ | wins |
|---|---|---|---|---|
| low (<0.55) | 7 | **+0.2760** | +1.93 | 4/7 |
| mid (0.55–0.65) | 30 | −0.5780 | −17.34 | 8/30 |
| high (≥0.65) | 37 | **−1.8353** | −67.91 | 8/37 |

Pearson r = **−0.3088**. Monotone, and pointing the wrong way.

**It was a size confound and nothing else.** High-conviction entries carry **~2× the notional** (avg $643.08 vs $327.36 low / $304.21 mid), so they lose twice the dollars at the same rate. Renormalised per unit notional:

| conviction | n | **mean bp** | median bp | wins |
|---|---|---|---|---|
| low (<0.55) | 7 | −17.73 | +11.73 | 4/7 |
| mid | 30 | −24.59 | −9.60 | 8/30 |
| high (≥0.65) | 37 | −18.72 | −9.15 | 8/37 |

**Pearson r (conviction vs bp) = −0.0393 — indistinguishable from zero, n=74.** All three buckets lose 18–25 bp. **Conviction carries no information about per-unit outcome.**

**Independent cross-check:** the overall mean here is **−21.01 bp**, against **−20.76 bp** measured by a completely different route (position-episode fill-price replay, reading #66 lineage). Two methods, same answer.

### Two consequences

**1. "Marginal ≤ average by construction" is REFUTED.** The aggression analysis argued that lowering the conviction bar must admit worse-than-average trades, and therefore that frequency levers are worse than linear. **At n=74 that does not hold**: conviction does not predict per-unit outcome, so the marginal trade is not worse than the average — it is the same. **This does not make aggression good.** The average is −21 bp; more trades at −21 bp is simply more loss, linearly rather than super-linearly. The NO-GO stands, for the original reason.

**2. Sizing amplifies a signal that carries no information.** High-conviction entries get roughly double the notional while conviction predicts nothing about the per-unit result. That adds variance without adding expected return — the worst kind of sizing rule. *Stated as an observed association: this reading did not verify in code that size is explicitly conviction-scaled, and that check should precede any change.*

**Method note:** the dollar-level result (r = −0.31, clean and monotone) was wrong, and only the notional normalisation exposed it. **Any per-trade statistic on this ledger must be normalised by notional before it is interpreted** — the same class of trap as the partial-exit weighting error recorded in reading #64.

**Falsifiers carried forward:** frozen-mark **unmeasurable** for a fourteenth consecutive cycle; H-LEDGER **not tripped**; #592 **1 of 30** (metric corrected in #68); #591 **0 of 20, untested**.

---

## Reading #70 — 2026-08-28T18:13Z — the conviction-sizing check: my #69 framing was wrong, and a shipped flag-gate now has its answer

**Profit first: no change. Zero fills, zero open positions, $0.00 realized.** Last fill anywhere is `2026-08-27T14:11:52Z` — **28.0 hours**. No completed trips, so no three-agent dispatch. 41 runs (fleet 42 at 24, fleet 41 at 17); panel since P0 **48 entry proposals, 0 kept**; health 76 decisions, `no_verdict` 0, `verdict_salvaged` 2, 0 tracebacks.

### The code check reading #69 deferred, now done

#69 observed that high-conviction entries carry ~2× the notional and flagged it as *"sizing amplifies a signal that carries no information — variance without expected return,"* explicitly deferring a code check. **That check reverses the framing.**

`run_engine.py:3147 _conviction_size_scale` (Plan 15 rec-2), live by default via `RUN_SIZE_BY_CONVICTION`:

```
base = max(0.40, min(1.0, (v - 0.45) / 0.30))
# "strictly shrink-only so it can never lever up"
```

Conviction 0.45→0.75 maps to a size scale of **0.40→1.00**. **High conviction is not amplified — low conviction is damped, to as little as 0.40×.** The observed ratio (avg notional $643 high vs $304 mid) is **≈2.1×, against the rule's own range of 1.00/0.40 = 2.5×.** Mechanism confirmed; **my description of it was wrong.**

**And the correction changes the conclusion.** A shrink-only rule on a book whose trades are *uniformly* ≈−21 bp (reading #69: no conviction bucket differs, r = −0.0393) **reduces exposure on a subset without giving up any edge, because there is no edge to give up.** It is **accidentally protective**: removing it would put full size on trades that are no better, and would *increase* the loss. **Do not remove it** — but record that it works for a different reason than its docstring claims.

### A pre-registered gate in the code now has its answer, and the answer is NO

`_conf_v2_enabled` (`RUN_CONF_V2`, default OFF) carries this condition verbatim:

> *"Default OFF — enable only after the shadow period shows conviction correlates with outcomes better than the scalar."*

**Reading #69 is that shadow measurement.** Conviction vs per-unit outcome: **Pearson r = −0.0393, n=74, indistinguishable from zero**, with all three conviction buckets losing 18–25 bp. **The stated enable condition is not met and is not close to met.**

**Recorded decision: `RUN_CONF_V2` stays OFF, now on evidence rather than caution.** Any future session proposing to flip it must first beat r = −0.0393 on a larger sample; this reading is the baseline it has to clear. Verified in prod: both `RUN_SIZE_BY_CONVICTION` and `RUN_CONF_V2` are unset in `.env`, so the code defaults (ON / OFF respectively) are what is running.

**No change was made to either flag.** The live behaviour is already what the evidence supports.

**Falsifiers carried forward:** frozen-mark **unmeasurable** for a fifteenth consecutive cycle; H-LEDGER **not tripped**; #592 **1 of 30** (metric corrected in #68); #591 **0 of 20, untested**.

---

## Reading #71 — 2026-08-28T19:13Z — H3 REFUTED: the fleet is draining, and the treadmill is now quantified

**Profit first: no change. Zero fills, zero open positions, $0.00 realized.** Last fill anywhere is `2026-08-27T14:11:52Z` — **29.0 hours**. No completed trips, so no three-agent dispatch. Panel since P0: **52 entry proposals, 0 kept**. Health: 86 decisions, `no_verdict` 0, `verdict_salvaged` 2, 0 tracebacks.

### H3 (fleet stable) is REFUTED

Live runs fell **41 → 34** in one hour; fleet 42 went **24 → 17** while its target is still 25. Not the churn seen in earlier cycles.

**Cause, measured:** 13 runs stopped (`idle_retired` 12, `desk_retired` 1) against only **6 built**. Retirement is outpacing replenishment roughly 2:1. Both fleets are `active`, targets 25/25, `entry_paused_reason` NULL, `held_by_master` 0 — nothing is paused or held.

**The builder shows the known stall signature** — `[FleetPlanner] tick: {'claimed': 2, 'researched': 0, 'built': 0, 'supervised': 2}` on essentially every tick, with 8 slots of headroom per fleet. That is the [[fleet-replenish-stall-trio]] pattern, though here it is a **partial** stall (~6 builds/hour) rather than the full 0/hour case.

**Theses are NOT the constraint, and this was checked rather than assumed:** SymbolResearch is healthy (`universe 160, survivors 110, persisted 110, llm 110`), **220 fresh theses in the last hour** (us-stock 80, forex 58, crypto 42, futures 40), `market_scope_json` is **NULL on both fleets** so nothing is scope-excluded, and there are **zero** feasibility/exposure/build-gate rejections in the log. Supply is ample; the build *rate* is the limit.

### The treadmill, quantified — the real cost of the drought

| Last 24 hours | |
|---|---|
| Runs **created** | **140** |
| Runs stopped | 107 (of which **`idle_retired` 71**) |
| Runs that **ever filled** | **0** |
| Decision cycles consumed by runs that never traded | **1,134** |

**The platform built 140 runs, ran 1,134 LLM decision cycles, and produced zero trades.** Every run in the window was pure overhead: researched, funded, cycled, retired for never trading, replaced.

This is a **self-reinforcing loop**: no entries → `idle_retired` → rebuild → still no entries. It also explains the drain — idle-retirement fires at ~71/24h while the builder sustains only ~6/hour, so the fleet settles at whatever level those two rates cross, well below the 25/25 target.

**Stated in profit terms, which is what matters:** the loss from the drought is $0.00 realized, but the *cost* is 1,134 decision cycles and 140 run builds spent for nothing. That is the number to quote when the drought is described as "quiet" — it is not quiet, it is expensive and producing nothing. The treadmill was already named as an open item in the Phase 2 queue (docs/research/06); this reading gives it a measured size for the first time.

**No change made.** This is an observation; nothing here justifies touching build rates or retirement thresholds while entry expectancy is −21 bp — building *more* runs that would trade at a loss is not an improvement, and slowing retirement would only hold idle runs longer.

**Falsifiers carried forward:** frozen-mark **unmeasurable** for a sixteenth consecutive cycle; H-LEDGER **not tripped**; #592 **1 of 30**; #591 **0 of 20, untested**.

---

## Reading #72 — 2026-08-28T20:33Z — #71's "builder stall" is RETRACTED; four layers independently refuse to trade

**Profit first: no change. Zero fills, zero open positions, $0.00 realized.** Last fill anywhere is `2026-08-27T14:11:52Z` — **30.4 hours**. No completed trips, so no three-agent dispatch. Health: 89 decisions, `no_verdict` 0, `verdict_salvaged` 2, 0 tracebacks.

### RETRACTION — reading #71's "known stall signature" was wrong

#71 reported `[FleetPlanner] tick: {'claimed': 2, 'researched': 0, 'built': 0}` as *"the [[fleet-replenish-stall-trio]] pattern"*. **That was a false match.** Verified in code (`fleet_planner.py:2015-2029`):

```
if status == STATUS_RESEARCHING:  _do_research(fleet); out["researched"] += 1
elif status == STATUS_BUILDING:   _do_build(fleet);    out["built"] += 1
else:                             supervise_fleet(fleet); out["supervised"] += 1
```

`built` and `researched` **only** increment for fleets in `BUILDING`/`RESEARCHING` status. **Both fleets are `active`**, so they take the third branch — `supervised: 2` — every tick. **`{'researched': 0, 'built': 0, 'supervised': 2}` is the correct, expected output for two active fleets, not a stall.** Replacement runs through `supervise_fleet` and is demonstrably working: **8 `slot_created` events and 5 runs actually created** in the window. This session pattern-matched a remembered failure mode onto a counter that means something different in this state.

### The real reason for the drain — and for days of zero orders

Fleet: **42 → 34 → 24 runs.** This hour **15 retired (idle 10, desk 5) against 5 replaced.** Replacement works but is *slower* than retirement, and the reason is visible in `fleet_events`:

| gate | verdict on the freshest pass |
|---|---|
| `fee_gate` | kept `NG, ZW, GC`; **dropped GBPUSD** — *"fee_infeasible: min_edge: claimed 0.55% × 0.25 realization = 0.14% < 0.15% floor"* |
| `backtest_gate` | kept `ZW, GC`; **dropped NG** — *"non-positive expectancy −140.62 USD/trade over 8 closed trades"* |

**The gates are not broken and are not over-tight — they are keeping most candidates and dropping the ones that fail an explicit arithmetic test.**

### The finding that answers the owner's question

**Four independent layers, each measuring separately, all reach the same conclusion: there is nothing here worth trading.**

1. **`fee_gate`** — rejects candidates whose realizable edge (0.14%) is below the fee-aware floor (0.15%).
2. **`backtest_gate`** — rejects candidates whose replayed expectancy is negative (−140.62 USD/trade).
3. **The desk** — 580 of 2,279 holds cite fee/expectancy: *"lacks a defensible, fee-positive edge at current levels."*
4. **The panel** — **52 entry proposals since P0, 0 kept.**

And this session's own independent measurement agrees: **−21.01 bp per trip**, reproduced by two unrelated methods (conviction-bucket join and position-episode fill-price replay), and **negative in every market before a cent of fees**.

**So "days of zero orders" is not one broken component.** It is four gates, built at different times by different mechanisms, independently arriving at the same arithmetic — the same arithmetic this session verified four ways. **The plumbing is working. The edge is what is missing.**

**This is the honest and uncomfortable statement:** the only ways to produce orders today are to disable a gate, lower the fee floor, or ignore the backtest — and 08-25 already measured what that costs. When the panel failed open, the book took 64 legs and lost **−$6.15**, with **9 of 22 directionally correct calls still losing to fees**. Manufacturing orders is available; profitable orders are not.

**The treadmill cost stands and is the number worth quoting:** in the last 24h, **140 runs built, 1,134 decision cycles consumed, 0 fills.** The drought is not free — it is expensive and producing nothing — but the fix is expectancy (Plan 29 P3), not throughput.

**Falsifiers carried forward:** frozen-mark **unmeasurable** for a seventeenth consecutive cycle; H-LEDGER **not tripped**; #592 **1 of 30**; #591 **0 of 20, untested**.

---

## Reading #73 — 2026-08-28T21:13Z — THREE-AGENT VERIFICATION (owner-ordered). The conclusion survives; most of its evidence does not.

**Profit first: no change. Zero fills, zero open positions, $0.00 realized.** Last fill anywhere is `2026-08-27T14:11:52Z` — **31.0 hours**. 25 runs (fleet 42: 10, fleet 41: 15). Panel since P0: **54 entry proposals, 0 kept.**

**Owner order (2026-08-28), verbatim:** *"we got mistaken many time, So must be verification with 3 agents always, do not missing anymore."* Recorded as binding in [[three-agent-verification-always]]. Three axes were run — **A: DATA** (re-derive every number by a different route), **B: CODE** (verify every behavioural claim against `origin/main` AND the running image), **C: ADVERSARY** (actively refute this session's own conclusion). This reading is their cross-check.

### The central conclusion SURVIVES — on evidence this session did not have

> *"The book has no positive edge; the zero-order state is the system correctly declining it."*

**Survives**, but the load-bearing number changes. Agent C's replay of the **1,072 proposals the panel blocked**, on their own price paths under identical rules (MDE 5.4 bp, all agents, both regimes): net expectancy **−11.35 bp, CI90 [−18.27, −4.42], excluding zero.** The AI's directional calls (−4.98 bp gross) **lose to a random-side control (+1.01) and to always-long (+5.27) on identical price paths**, robust across six exit rules. Overall win rate 53.7% is not significantly different from 50% (p=0.364).

**This replaces −21 bp as the citable figure.** It is a stronger test than anything reported in readings #55–#72.

### REFUTED — "four layers correctly refuse to trade"

| cohort | n | gross bp | median | win% |
|---|---|---|---|---|
| KEPT | 16 | −5.82 | +2.55 | 56.2 |
| DEMOTED | 1,072 | −4.98 | −0.26 | 49.0 |

**KEPT − DEMOTED = −0.84 bp, z = −0.02, p = 0.983.** The gate stack refuses **98.5%** of proposals and what it passes is **statistically indistinguishable from what it blocks**. Reading #72's claim that four independent layers "correctly refuse" is **wrong**: they are right by base rate, not by discrimination.

**LIVE RISK, stated plainly:** a stack with p=0.983 discrimination cannot tell a good candidate from a bad one. **If #592, the consolidation, or any future fix restores a real edge, this same stack will refuse it — and nothing in the current instrumentation would reveal that.** This is now a measured defect, not a suspicion, and it outranks the remaining P3 work.

### Claims by this session that are REFUTED and must not be re-quoted

| claim | verdict |
|---|---|
| "−21.01 bp **per trip**, two methods converge" | **A + C:** a dollar-weighted figure mislabeled. Equal-weighted is **−5.06 bp** (C) / −10.85 bp (A), CI spanning zero, **median +1.36 bp POSITIVE**. The "convergence" compared net-equal-weighted-74 against **gross**-notional-weighted-148 — different quantities |
| "Gross edge negative in **all four markets**" | **A + C:** true of the mean only. **No market is statistically negative** (every CI includes 0); medians are **positive** in crypto (+3.24) and forex (+2.16). Forex flips to +0.09 bp on dropping one episode |
| **"P0 set fleet 41 to exactly $180.00"** | **B, re-verified by this session:** true for **10 of 15** runs. Live range is **$59.40 – $810.23** — the top is **4.5× the reported figure**. Per-slot size is NOT `budget ÷ n_runs`: `allocate_budget` applies a confidence × vol-parity tilt clamped to [0.5×, 2×], legacy slots keep old allocations, and `PROBATION_SIZE_FRAC = 0.33` produces ratios of 0.1485 |
| "Ingest needs a run cycle; if the fleet stops cycling, notes never reach the corpus" | **B:** called from `run_engine.py:7754` inside **`tick()` — the scheduler tick**, which runs regardless of whether any run cycles. The dependency does not exist |
| "The formula cannot produce exactly 0.00000000 with a non-zero fee" | **B:** refuted by **102 actual rows**. Run 1817 true −0.7538 and run 1820 true −0.2568 are both stored as `0E-8` |
| "9 of 9 armed exits adverse, mean 18.9 bp" | **C: 7 of 9.** 18.9 was the mean of \|slippage\| without mapping sign to side. Signed mean **−12.42 bp**, and the sign is **100% mechanically forced** by the trigger geometry — discretization, not adverse selection |
| "08-25 proves trading loses (n=22)" | **C:** ≈**6 independent bets** after collapsing same-direction opens within 2h, and the two clusters **offset** (9 longs −$5.41 vs 10 shorts +$3.79). MDE ≈89 bp. An anecdote, not a measurement |
| "9-day baseline 342 proposals / 3 kept = 0.93%" | **A:** not reproducible — windows give **351–397**, always 3 kept → 0.76–0.85%. Also internally wrong: 3/342 = **0.877%** |
| "1,134 decision cycles" | **A:** not reproducible (1,069–1,226 by definition) |
| "140 runs created in 24h" | **A: 139. B: 188.** Neither reproduces 140 — the agents disagree on window definition |

### The correlated-event strip this session never ran (owner law requires it)

**A:** 71% of the total net loss — **$133.82 of $187.24** — closed inside **three one-hour windows on 2026-08-13**. Stripping them: gross mean −5.06 → **−1.29**; **us-stock flips −12.83 → +26.14**.
**C, independently and wider:** **100.6% of the gross loss falls in the first 2 of 16 days** (08-12/08-13); the remaining 14 days and 80 trips return **+$0.89**. It is also an *agent* split — **agent 5 alone is −$168.54, i.e. 107% of the entire book's loss**; agents 6, 59, 60 are all positive. Crypto post-08-14: **+2.61 bp**, median +3.97, win 58.8%.

**Consequence:** the effective independent n is far below 148, and the loss is a concentration phenomenon, not a uniform absence of edge. **This does NOT reverse the conclusion** — C's n=1,072 test spans both regimes and all agents and still excludes zero — but every per-market and per-window figure in readings #55–#72 must be read as regime-bound.

### Where the agents DISAGREE — recorded, because the disagreement is the finding

1. **The `pnl = 0` mechanism.** This session asserted an **administrative reset** (from `reset6_bak_*`, 174 rows matching by `id`). **B could not determine a mechanism** — no arithmetic path, `execute_paper_trade` is the sole writer, no `UPDATE signals SET pnl` exists, and **`SHOW TRIGGERS` returns NONE** — and reports it **UNRESOLVED** rather than inferring. The backup tables remain strong evidence of an administrative action, but **B is right that this session asserted a cause it had not proven.** Status: agent-scoped (agent 6: 102/102 zeroed; agents 59/60: 0/10), mechanism **open**.
2. **08-25 fail-open scale.** Earlier: "64 legs". **B measures 46 fail-open of 68 `order_discussion` events**, and via the **rule-fallback branch (`no llm response`), NOT the exception branch** — which matters for anyone trying to reproduce it by injecting an exception.
3. **24h run creation:** A 139, B 188.

### Confirmed clean

**No deploy drift** — `automation.py`, `run_engine.py`, `fleet_planner.py`, `fleet_supervisor.py`, `desk_memory_ingest.py` are **md5-identical** between the running image and `origin/main` (`655da8c3`). `_conviction_size_scale` verified shrink-only by executing it across v∈[0,3] × leverage∈{1…100}: **max 1.0**. `simulate_trip` homogeneity re-proved numerically: worst deviation **1.8e-14**. `FLEET_TARGET_SLOTS` absent from `.env` and worker env — with the nuance that `fleet_auto_tune.py:171` and `routes_fleets.py:560` *can* raise `n_runs`, so "unsetting does not restore" is true of the H-CONSOL path only.

### New defect nobody had flagged

**`trading_runs.realized_pnl_usd` is not a usable P&L source** — it is 0 on **519/519** stopped agent-6 runs *and* **378/383** agent-60 runs since 08-15. Any report reading that column sees no loss anywhere. This is broader than the agent-6 anomaly and affects both live agents.

**Falsifiers carried forward:** frozen-mark **unmeasurable** (0 open positions); H-LEDGER **not tripped**; #592 **1 of 30** (metric corrected in #68); #591 **0 of 20, untested**.

---

## Reading #74 — 2026-08-28T22:13Z — THE DROUGHT BROKE. Three agents on n=1, and the selection mechanism is now known.

**Profit first: +$0.108151 net (+3.64 bp on $297.01 notional).** First fill in **31h26m**. The book stands at ≈ **−$187.13**. This trip moves the standing estimate by **+0.045 bp** and refutes nothing.

Run 2208, fleet 42, agent 60, BNBUSDT: short 0.43137255 @ 688.53 (21:38:20Z) → cover @ 687.66 (22:01:01Z), 22m41s, closed by `stop_event:trailing_lock`.

| | value |
|---|---|
| gross | **+12.64 bp** (+$0.375294) |
| round-trip fee | **−8.99 bp** ($0.267143) |
| **net** | **+3.64 bp** (+$0.108151) |
| **fees as share of gross** | **71.2%** |

### THE FINDING — run 2208 was selected because its DIRECTION bypassed the only gate with teeth

Every `backtest_gate` ruling fleet 42 ever made on BNBUSDT: **461 rulings — 459 DROP, 2 KEEP.** Every drop carries the byte-identical reason *"non-positive expectancy −188.48 USD/trade over 5 closed trades"*, unchanged 08-26 → 08-28. **The two KEEPs are 08-28T15:12:55 and 08-28T17:20:01 — the second is run 2208's birth.** The gate reverted to DROP at **22:01:45, 44 seconds after the flatten**, with the same stale figure.

The cause is in the code, not the data:

```python
if direction == "short":
    # The replay engine is LONG-ONLY ... Alien evidence must not veto — fail open
    kept.append(thesis); continue
```

**Short theses are admitted unconditionally and unscored.** BNBUSDT theses are **103 long / 24 short**; longs get scored and dropped, shorts bypass. The two KEEPs align exactly with short batches — and `research:496648` (short) is **verbatim the `batch_id` in run 2208's own config snapshot.**

> **Run 2208 was not selected because it beat the 86 demoted proposals. It was selected because its direction skipped the only gate that discriminates.**

**This is the mechanism behind the short bias.** The ZI control measured the desk's 70%-short tilt as worth **−0.00015/trip — literally nothing**. Now we know why the tilt exists at all: **short is the only direction that can reach a fill.** The bias was never a view; it is a survivorship artifact of a long-only replay engine failing open.

### And the designated safety net for shorts is structurally dead

`backtest_gate` delegates short theses to `fleet_planner._bucket_expectancy_block`, which vetoes on `SUM(trading_runs.realized_pnl_usd)`. Measured on prod: agent 60, crypto/short, stopped, fleet-built = **n=37** (over the min-8 threshold) but `SUM = +0.1766`, computed from **3 non-zero rows out of 37**. Agent 60 overall: **6 of 384** stopped runs have a non-zero value — **98.4% zeros**. `total >= 0` → returns `None` → **allow**.

**The gate cannot veto anything and never will while that column is 98.4% zeros.** Reading #73 recorded `realized_pnl_usd` as *"not a usable P&L source"*. It is worse than that: **it is load-bearing in a live admission gate.**

### #592 — fire n=2 of 30. UNDECIDED.

Both post-ship fires verified #592-attributable **by arithmetic, not by timestamp** (the old floor cannot explain either exit):

| n | run | symbol | net | bp | old rule fires? |
|---|---|---|---|---|---|
| 1 | 2001 | TAOUSDT long | +0.9868 | +44.0 | **No** — old floor 0.2018 vs exit 1.1881 |
| 2 | 2208 | BNBUSDT short | +0.1082 | +3.64 | **No** — old floor 0.267 vs 0.3753 |

**Old-rule counterfactual on this trip**, walked on Hyperliquid 1m candles (the same feed that produced the marks, basis-checked at three points): the old rule holds through 22:02–22:06 while the position is worth **more** (+$0.32 / +$0.37 / +$0.28 net), then fires at **22:07–22:08 for −$0.034 to −$0.073**; its impossible best case is **−$0.0001**. **Delta from #592: +$0.14 to +$0.18.** The "best case exactly $0 by construction" the PR was written to kill is reproduced live.

**Applying the corrected falsifier from #68:** post-ship mean +0.5475 with a bootstrap CI90 of [0.1082, 0.9868] — **degenerate at n=2, it can only return the two observed values, and that interval carries no information.** Median passes but is DEMOTED and passing it alone is not #592 working. **n=2 of 30 decides nothing.** Both fires rank 1 and 2 of all 32, permutation p=0.0020 — but a fire under the new rule is positive **nearly by construction**, so this restates the mechanism rather than testing it.

**Baseline discrepancy — reading #68 needs correcting.** Agent B could not reproduce #68's pre-ship figure of n=20 / mean −0.1522 / SD 0.2893 from any subset. Replaying all 30 telemetry-visible fires gives **n=30 / mean −0.2194 / median −0.0663 / SD 0.3138**, cross-checked against `realized_pnl_usd` on the 3 runs where it is populated. B's figure is *more* negative so the direction is unaffected, but **#68's n=20 subset must be named or corrected.**

### The mark cadence cost more than the trade earned — agreed to the cent by two agents

The #592 floor sat at 0.510951 → trigger price **687.3455**. The equity series polls at ~65s: 21:59:56 gross 0.741891 (above floor), 22:01:01 gross 0.375294 (below). **Price gapped straight through the floor between two polls.** Exiting *at* the floor banks **+$0.243869**; it banked **+$0.108152**. Overrun **−$0.135718 = 125% of what the trade kept.** Agents A and B derived this independently and agree to the cent. **#592 set the lock correctly; the mark cadence gave back more than half of it.**

**Give-back, with the #55 error corrected:** baseline-adjusted **50.29% of peak gross** (payload naive read shows 61.10% — overstated by 10.82pp). Peak **net** 16.43 bp → kept 3.64 bp = **77.8% of peak net surrendered**. P3 stands.

### The hurdle rate — why the median trip cannot pay

| slice | n | gross median | clears own fee | **dead on arrival** |
|---|---|---|---|---|
| all crypto | 87 | +3.24 bp *(CI90 spans zero)* | 34.5% | **65.5%** |
| **simple 1×1 episodes (69% of trips)** | 60 | **−0.16 bp** | **25.0%** | **75.0%** |
| forex | 22 | +2.16 bp (fee 1.60) | 50.0% | 50.0% |

**The median crypto trip is −5.76 bp net by construction.** This trip needed **3.90× the median gross** (70th percentile) to net +3.64 bp.

**New refutation:** reading #73's "medians are positive in crypto and forex" is **not robust**. It survives only through multi-leg episodes (n=27, median +17.61 bp); on the 69% that are one-open/one-close the gross median is **−0.16 bp**.

### The entry was unblocked by sampling variance, not information

Cycles 9 (demoted) and 10 (kept) are 29 minutes apart with **byte-identical `recall` payloads**, the same 9 brief lines, unchanged market read (long/short 2.57, RSI ~66), an **identical `sell 0.58` proposal**, and a price that moved **against** the short (687.8 → 688.5). Only the LLM outputs moved. The desk logged `plan_adherence: "deviated"` — it acted against its own standing trigger, neither of which fired.

**The panel demoted the best trade of the run.** Counterfactual gross at the identical exit: cycle 2 @692.80 = **+74.19 bp (demoted)**; cycle 6, highest conviction 0.60 = +20.90 bp (demoted); **cycle 10 = +12.20 bp — KEPT, rank 4 of 7.** Cycle 9 was demoted at a *higher* final confidence (0.58) than the kept cycle 10 (0.56).

**And the panel is a black box.** `order_discussion` persists **101 bytes** — `{proposed, final}` only, no rationale. It demoted **86 of 86** proposals on 08-28. The most consequential actor in the entry pipeline leaves no reasoning trail. **Highest-leverage instrumentation gap on the board.**

**Power, restated honestly:** reading #73's p=0.983 rests on **n=16 — ~35× underpowered.** Detecting an 8.99 bp edge needs **n_kept ≈ 568 ≈ 16 weeks.** It does not show the panel works or fails; **it shows the test cannot see.** The panel question must be decided by replay — the 1,072 demoted proposals are already the control arm.

### The desk never saw its own position

`interval_minutes: 45`; the position lived **22m41s**; the next desk cycle was due 22 minutes *after* it closed. The exit was **100% algorithmic**, confirmed three ways (no `decision`/`order_intent`/`armed_exit` in the window, while `armed_exit` demonstrably fires elsewhere). Agent A reproduced the ratchet decision exactly from deployed source: of 23 equity samples, **exactly one** satisfies the trigger, and it is the actual fire.

**Configured rails were decorative:** `profit_target_usd` $240 (peak = 0.31% of it), `max_loss_usd` $17.82 (MAE = 0.31%), `trail.activate_usd` $4.75 — **6.3× out of reach, never armed**. The whole trip lived in a **57-cent band, 0.083% of price**, governed by a fee-anchored rail at 0.20% of notional. It captured **3.0% of the desk's own $660 target** and never came within 97% of its $702 stop. *A thesis resolved after 1.4% of its planned range was not validated by the outcome — it was bypassed by it.*

### Sizing chain, reproduced to the cent

`4000.03 slot → ×0.45 aggressive = 1800.01 → ×0.33 PROBATION_SIZE_FRAC = 594.00 → ×0.30 desk size_scale = 178.20 → ×0.25 null_size_cap = 148.50 margin → ×2.0 leverage = $297.00 notional → /688.53 = 0.43137254901960786` — **the filled quantity to the last digit.** 594.00/1800.01 = 0.33000 exactly; no other tier value reproduces it. Probation applies because 2208 is agent 60's only-ever BNBUSDT run.

### Agent disagreements — recorded

1. **Drought length:** A 32h46m41s (entry-to-entry), B **31h26m28s** (fill-to-fill). Both correct for different definitions; **quote fill-to-fill.**
2. **"54 demoted":** this session's figure. A measures **86 of 86 on 08-28**; B could not reproduce 54 from any table. **54 is wrong — use 86.**
3. **Loss concentration:** #73 said 100.6% in 2 of 16 days; C's rebuild gives **88.1%** (−$164.78 of −$187.13) and agent 5 = **−$187.86 = 100.4%** of the book, all other agents **+$0.73** combined.
4. **Panel counts:** raw all-time `order_discussion` = **1,390** (demoted 1,208, kept 104; strict same-action 83). The 1,072/16 used for p=0.983 is a filtered subset — **restate n=16 whenever that p-value is quoted.**
5. **Kept ≠ fill:** 08-26 had 3 kept and 08-27 had 2 kept, yet **zero fills** in that window. Something downstream of the panel also blocks.

### Next measurement, ranked

**#1 — MFE distribution on the 1,072 blocked proposals' own paths.** Measures gross max-favourable-excursion, not terminal gross. It forks the whole program: **if ≥50% reach MFE > 18 bp** (2× round-trip fee) the exit rule is binding and P3 is correctly prioritised; **if <50% and median MFE < 8.99 bp**, no exit rule can pay for itself in crypto, P3 is refuted as top priority, and the lever becomes market mix (forex clears its 1.60 bp hurdle 50% of the time vs crypto's 34.5% at 8.99 bp). Uses existing replay infrastructure, no live risk, **not throughput-gated**.

**#2 — the short-direction bypass.** Now the highest-value *code* finding. The long-only replay engine fails open on shorts, so shorts enter unscored while longs are scored and dropped. Quantifying the cost needs the same MFE replay split by direction.

**#3 — #592 live accrual: explicitly not worth waiting on** (n≈449–568, 13–16 weeks). Decide by replay.

### Deploy cadence — trigger FIRED

Last fill at/before the trigger: run 2019 LITUSDT cover, `2026-08-27T14:11:52Z`. Next: run 2208 BNBUSDT short, `2026-08-28T21:38:20Z`. **Mode ① → mode ②: merge every cycle, deploy only on deploy-worthy content.** This reading qualifies.

**Falsifiers:** frozen-mark — **measurable again next cycle** if a position opens (0 open now); H-LEDGER **not tripped**; #592 **2 of 30**; #591 **0 of 20, untested**.

---

## Reading #75 — 2026-08-28T23:13Z — quiet; reading #68's falsifier baseline CORRECTED

**Profit first: no change. Zero new fills, zero open positions, $0.00 realized this cycle.** The BNBUSDT trip (+$0.108151) remains the only fill; last fill `2026-08-28T22:01:01Z`, 72 minutes ago. Drought resumed. 24 runs (fleet 42: 10, fleet 41: 14); panel 4 proposals, 0 kept; 16 decisions; **0 `stop_mechanism` fires**; 0 tracebacks. No new tape, so no three-agent dispatch.

### Correcting reading #68 — its pre-ship baseline is not reproducible

Reading #68 pre-committed a corrected #592 falsifier using a pre-ship population of **n=20, mean −0.1522, SD 0.2893**. Agent B could not reproduce it from any subset (#74). **This session has now recomputed it independently, and #68 is wrong.**

Pulling **all 32 `stop_mechanism` fires** and splitting at the #592 ship (`2026-08-27T05:45:44Z`, the image build time):

| source | n | mean | median | SD | basis |
|---|---|---|---|---|---|
| **reading #68 (claimed)** | 20 | −0.1522 | −0.0568 | 0.2893 | **not reproducible** |
| Agent B (#74) | **30** | **−0.2194** | −0.0663 | **0.3138** | net trip |
| this session, independent | **30** | −0.2184 | −0.0080 | 0.9506 | **gross at fire** |

**n=30 is confirmed twice; #68's n=20 is wrong.** B and this session agree on n and on the mean to within $0.001 (−0.2194 vs −0.2184).

**The remaining gap between B and this session is net-vs-gross — the same trap that has now bitten this stack three times.** This session computed `total_cum − peak_realized_usd`, i.e. **gross at the fire**; B replayed **net trip**. On the BNB fire that is +0.3753 (gross) against +0.1082 (net) — the divergence is entirely the round-trip fee. **B's net basis is the correct one for a falsifier about realized P&L**, so B's figures are adopted. Recorded because catching it required checking the two post-ship values against each other, not the summary statistics.

### The corrected falsifier, and a useful intermediate readout

Replacing SD 0.2893 with **0.3138** and the comparator −0.1522 with **−0.2194**:

| shift to detect | n (80% power, α=.10 one-sided) |
|---|---|
| +0.0500 | 178 |
| +0.1000 | 44 |
| **+0.104 (#592's claimed effect)** | **41** — reading #68 quoted 38 |
| +0.1500 | 20 |
| **+0.2194 (reach BREAKEVEN)** | **9** |

CI90 half-width at n=30 is **±0.0942** (was quoted as ±0.0869).

**Two consequences, both pre-committed now:**

1. **#68's "n=38 for 80% power" becomes n=41**, so n=30 gives roughly 50% power for the claimed effect. The pre-commitment stands and is reinforced: **a null at n=30 is INCONCLUSIVE, not FAILED.**
2. **A useful intermediate readout exists that #68 missed.** Asking *"did #592 lift ratchet fires to breakeven?"* is a **+0.2194 shift, detectable at n=9** — roughly 7 more fires rather than 28. **This should be read and reported at n=9**, with the same discipline: mean with CI90, median demoted, and a null reported as inconclusive rather than as failure.

**Current tally: n=2 of 30** (TAO +$0.9868, BNB +$0.1082 on the net basis; both verified #592-attributable by arithmetic in #74). Post-ship mean +0.5475 with a **degenerate** bootstrap at n=2 — it can only return the two observed values and carries no information. **Nothing is decided.**

**Falsifiers carried forward:** frozen-mark **unmeasurable** (0 open positions); H-LEDGER **not tripped**; #591 **0 of 20, untested**.

---

## Reading #76 — 2026-08-29T00:13Z — quiet tape; #74's bypass claim CORRECTED and sharpened

**Profit first: no change. Zero new fills, zero open positions, $0.00 realized this cycle.** Last fill remains `2026-08-28T22:01:01Z` — **2.2 hours**. The BNBUSDT trip (+$0.108151) is still the only fill. 24 runs (fleet 42: 10, fleet 41: 14), stable. Panel 2 proposals, **0 kept**. 14 decisions, **0 `stop_mechanism` fires**, 0 tracebacks. No new tape, so no three-agent dispatch.

### CORRECTION to reading #74 — "short is the only direction that can reach a fill" was too strong

#74 concluded from the `backtest_gate` short-bypass that *"short is the only direction that can reach a fill"*. **That overstates it.** Live run directions this cycle: **21 long, 3 short.** Longs are built in quantity, and a long has filled recently (run 2001 TAOUSDT, +$0.9868). The claim as written is refuted by the fleet's own composition.

### The correct statement — the bypass shows up in the FILL RATE, not the fleet mix

| window | direction | runs built | ever filled | **fill rate** |
|---|---|---|---|---|
| all time | long | 866 | 60 | **6.9%** |
| all time | **short** | 186 | 47 | **25.3%** |
| since 08-26 | long | 331 | **1** | **0.3%** |
| since 08-26 | **short** | 74 | 4 | **5.4%** |

**Shorts convert to fills at 3.7× the long rate all-time, and 18× since 08-26.** The built fleet is **82% long** (866 of 1,052) while the filled cohort measured by the ZI control was **70% short** (40 of 57). Those looked contradictory; they are both true, and the fill-rate table is what reconciles them: **most runs are long, most fills are short.**

**Mechanism, established in #74 and unchanged:** `backtest_gate` admits short theses **unconditionally and unscored** because the replay engine is long-only and fails open, while long theses are scored and mostly dropped. The delegated short safety net (`_bucket_expectancy_block`) cannot veto because it reads `SUM(realized_pnl_usd)`, which is **98.4% zeros**.

**Attribution discipline — stated, not glossed.** The code path is verified and the asymmetry is measured, but this reading does **not** claim the bypass explains the full 3.7×–18× gap. Other contributors are plausible and untested: short theses may be generated only under narrower conditions, and the recent 18× rests on **1 long fill out of 331** — a single observation in the denominator's numerator. **The mechanism is established; the magnitude is not attributed.**

**Why this matters more than the earlier framing:** an admission gate that scores one direction and waves the other through is not merely uneven — it means **the measured "short bias" was never a directional view at all.** The ZI control priced that tilt at **−0.00015/trip, indistinguishable from nothing**. A tilt worth nothing, produced by a gate asymmetry rather than by judgement, is a defect in candidate admission, not in the desk.

**Falsifiers carried forward:** frozen-mark **unmeasurable** (0 open positions); H-LEDGER **not tripped**; #592 **2 of 30** — with the **n=9 breakeven readout pre-committed in #75** as the first meaningful checkpoint; #591 **0 of 20, untested**.

---

## Reading #77 — 2026-08-29T02:13Z — THE FROZEN-MARK FALSIFIER IS **FAILED**, not passed. Three agents; four defects found.

**Profit first.** Run 2235 LINKUSDT short is **still open**: entry 11.399, mark 11.396, **+$0.0441 gross**, **−$0.031 net** of the $0.0755 entry fee. No trip outcome is stated. The BNBUSDT trip (+$0.108151) remains the only completed fill since the drought. 30 runs; 14 decisions; 0 `stop_mechanism` fires; 0 tracebacks.

### RETRACTION — this session reported the frozen-mark falsifier as PASS. It is FAILED.

Reading #77's first pass measured run 2235's live position at **3 identical of 26 pairs = 11.5%** against the pre-registered `<20%` threshold and reported **PASS**. **That is wrong on four independent counts**, all established by the adversary agent and accepted here.

**1. It was never statistically a pass.** Wilson CI95 on 3/26 is **[4.0%, 29.0%]** — the 20% threshold sits *inside* it. One-sided `P(X≤3 | n=26, p=0.20) = 0.207`. Rejecting p=0.20 at this rate needs **n=64 pairs**; the cycle had 26. **Reporting PASS from a non-rejection was a basic error.**

**2. The rate is confounded by tick grid, not mark freshness.** Reconstructing the implied tick for all six runs with a live position:

| run | symbol | tick (bp of px) | 66s move SD (ticks) | observed tie rate | **fresh-feed null** |
|---|---|---|---|---|---|
| 1894 | AAVE | 0.79 | 12.4 | 0.0% | 3.2% |
| 1895 | WLD | 0.25 | 85.7 | 5.3% | 0.5% |
| 2019 | LIT | 0.15 | 114.8 | 1.4% | 0.3% |
| **2235** | **LINK** | **0.88** | **6.1** | **9.4%** | **6.6%** |

**A perfectly fresh feed on LINK produces ~6.6% exact ties.** Reading #55's cohort sat on 12–115-tick grids where the null is 0.3–3.2%. **The entire 2.3% → 11.5% "discrepancy" is instrument coarseness, not a real difference** — and this session treated it as a discrepancy worth flagging rather than as the artifact it is.

**3. The instrument has a blind spot exactly where the fix put the defect.** `run_engine.py::_maybe_emit_equity` is **on-change with a heartbeat**: an identical `total` inside `RUN_EQUITY_HEARTBEAT` (default 60s, unset in prod) is **never emitted**. **The falsifier counts identical rows in a stream that deletes identical rows.**

Pre-fix this did not bite: a 300s freeze ÷ 66s emission = 4.5 rows, exactly reading #54's *"347 of 383 freeze episodes lasting 4–5 polls."* **Post-fix the freeze is one 33s tick, always inside the 60s heartbeat — invisible.** The metric was calibrated on a defect large enough to exceed its own blind spot, and the fix pushed the residual into that blind spot.

**4. The decisive direct measurement.** Sampling `positions.price_updated_at` every 6s: refreshes at 01:55:40 / 01:56:41 / 01:57:43 / 01:58:45 / 01:59:46 / 02:00:47 / 02:01:50 → **mean 61.7s (n=6)**. All 7 published marks reached the rail stream (zero skipped), with emission lag drifting monotonically **3→9→14→18→23→28s then resetting on a 35s gap** — the beat signature of a **~33s scan tick** against a 61.7s refresh. `RUN_TICK_INTERVAL` default 30s, unset; logged tick gaps quantise at 33/66/99/132s.

**The quantity the falsifier actually names — the rate at which consecutive rail evaluations act on a mark already seen — is `1 − 33/61.7 = 46.5%` by model and 50% counted directly (7 ties of 14 tick-pairs). The pre-registered `<20%` threshold is FAILED.**

**What IS true, and must not be lost in the retraction:** the fix worked on the *mechanism*. Effective rail resolution went **300s → 61.7s**, a ~2.2× smaller price gap between usable observations. Reading #74's live fire still measured the residual costing **−$0.1357 = 125% of what that trade kept**. **Mechanism improved; metric failed; the reported PASS was measurement error.**

**A cross-agent invalidation, recorded because it cuts both ways.** The algorithm agent argued staleness was refuted by *"0 of 11 short-gap (<50s) pairs identical."* The adversary agent independently ran the same test, then **retracted it**: the dedup makes short-gap ties **structurally impossible**, so the test is vacuous. **That retraction applies to the algorithm agent's argument equally.** Neither the tie rate nor the short-gap test can speak to staleness.

**The metric is the wrong statistic and should be replaced.** #54 quantified the original defect as *"rail trigger bands 2.1–4.7× narrower than the unobserved mark gap"* — a **band-to-gap ratio**, governed by the scan tick (33s, never changed) and the refresh (300→60s), **not by mark identity**. A threshold-crossing rail on a discrete grid overruns by ≈ E[|move| between usable marks]/2 however you count ties. **Replacement metric, pre-registered here: median overrun as a fraction of the band, per fire.** #74 already supplies one observation (overrun $0.1357 against a band the rail intended).

### DEFECT 2 — the desk's authored bracket is discarded on ~24% of entries

Run 2235's desk authored, verbatim: *"A 1.5% stop just above the MA-5 resistance (≈11.57) and a 3% target near recent support (≈11.05) give a clean 2:1 R:R."*

**What is written to `positions` row 481: stop_loss 11.9637 (+4.95%), take_profit 10.2546 (−10.04%).** Verified by exact arithmetic — `11.394 × 1.05 = 11.9637` and `11.394 × 0.90 = 10.2546` — these are `risk_engine.DEFAULT_LIMITS`, a flat 5%/10% for every instrument in every regime.

**Cause:** the desk's bracket replaces the default only when `order_params is not None and order_params.has_exits()`. Cycle 3's `order_params` reads **`"outcome": "absent"`** — the desk stated its levels **in prose only** and emitted no structured params. **Generality: 16 of 67 entries over 7 days (23.9%) got the flat default.**

The R:R is *not* degraded (0.493 vs 0.490, both ~2:1) — **the change is scale: both legs are 3.30× further away.** The desk believes its stop is at 11.57; **it is at 11.9637**, and the tail is 3.3× what it sized for. Cycle 4 *did* emit parsed params (`stop_pct 1.16`), but `stop_pct` is consumed **only on an opening action**, so the tighter stop can never take effect for this position.

### DEFECT 3 — the expectancy gate is not called on the path that builds 95% of runs

Readings #74/#76 attributed the dead short safety net to `SUM(realized_pnl_usd)` being 98.4% zeros. **That mechanism is falsified.** Run 2019 booked **−$0.545** at 00:28:58Z, flipping agent 60's crypto/short bucket from **+$0.1766 (n=37)** — reproducing #74's figure exactly — to **−$0.3685 (n=40)**. **n≥8 and total<0: the veto condition is MET**, and has been continuously since. Yet three crypto/short runs built after the flip — **2235 (+19s), 2238 (+12m42s), 2243 (+64m)** — with **zero `candidate_skipped`**. The 64-minute case rules out a race.

**Root cause:** `_bucket_expectancy_block` has exactly **one** production call site, `fleet_planner.py:1847` inside `_do_build`. **`fleet_supervisor._build_replacement` never calls it — while its own comments claim it does** (*"the expectancy gate so a replacement can't sneak a negative-edge symbol past the bar"*; *"The expectancy gate below cannot catch this class"* — there is no expectancy gate below).

| path | events | share |
|---|---|---|
| `run_started` (gated, `_do_build`) | **52** | 4.9% |
| `rotation` (ungated, replacement) | **1,011** | **95.1%** |

The gate works when called (11 historical `negative_expectancy` skips). **It is simply off the hot path**, and `test_build_gates.py` calls the function directly nine times without ever asserting it is *reached* via the replacement path — **the tests give false assurance.**

### DEFECT 4 — a third stale 0.1% fee site, and this one governs exits

`_breakeven_arm_usd` uses `BREAKEVEN_FEE_RATE = 0.001` (10 bp/leg) while the **booked** fee is `0.00045` (4.5 bp/leg, verified exactly on both fills). **The ratchet arm therefore demands a peak 2.22× the real round trip** ($0.3356 vs $0.1510 on run 2235). Against the measured median crypto gross of **+3.24 bp**, the arm sits at **20 bp of notional ≈ 6× the median trip's entire gross excursion** — a concrete, testable reason the ratchet so rarely arms. Joins `routes_signals.py` and `symbol_research.py`, but unlike those it is **on the exit/money path**.

**Run 2235 currently has no active protective rail of any kind:** `trail.activate` is **26.5× out of reach** (worse than 2208's 6.3×), and the **ratchet is not armed** — peak $0.101 is **3.3× below** the $0.3356 arm. Its only brackets are the platform defaults from Defect 2.

### CORRECTION — the short-fill attribution is a non-sequitur

Reading #76 attributed the long/short fill-rate gap to the `backtest_gate` short bypass. **The causal claim does not hold.**

- `backtest_gate` runs at **fleet composition, before a run exists**. Conditional on being built, longs have **passed** a positive-expectancy screen and shorts were never screened — **the gate should raise the built-long fill rate, not lower it.**
- **`run_engine.py` contains 0 references to `backtest_gate`.** There is no runtime channel.
- **Direction is perfectly collinear with market type**: every short in the book is crypto/futures, every long is spot. **No direction effect is identifiable from this data at all.**
- The **18× collapses**: crypto-only since 08-26 is **6.3×, CI95 [0.76, 53.2], p=0.088 — not significant.** Market mix explains it (442 `market closed` skips on longs, **zero** on shorts).
- Censoring tested and **rejected** (lifetimes 272.7 vs 265.4 min; cycles 10.23 vs 10.00).
- Measured proximate author of a long not filling: the desk's own `hold` (2901 long vs 728 short skips).

**What survives:** the all-time 3.7× is real and well-powered (CI95 [2.60, 5.2], p=8e-12), and **the bypass is a genuine defect on its own terms.** Fix it because it is wrong, not because it explains the fill gap.

### CORRECTION — the panel keeps are noise, and the rate is falling

Two keeps in four hours after a long demote streak looked like a shift. It is not. Keeps 08-22→08-29: **21 of 482 = 4.36%.** The recent pair is **3.66h apart — rank 4 of 6 gaps**; permutation p that some consecutive pair of 7 keeps lands ≤3.66h apart = **0.954**. Last 24h **2/100 = 2.0%** vs prior **5/122 = 4.1%** (Fisher p=0.46); Cochran-Armitage trend **z = −1.57, falling**.

**And "86 of 86 demoted on 08-28" — quoted in #74 and #76 — is stale.** 08-28 finished **1 kept of 93**; the BNB keep is itself an 08-28 event.

**The confidence-delta inference is also dead.** Kept-row Δconfidence: **n=21, mean +0.0086, SD 0.0725, 12 raised / 7 lowered / 2 flat**, sign test p≈0.36. **Run 2235's own 00:49:18Z cycle was DEMOTED with confidence RAISED 0.55 → 0.57** — the identical 0.57, 29 minutes before the keep. **71 of 415 demotions carry a raised confidence.** And the code settles it: *"The panel's decision REPLACES the proposal wholesale — code convenes the meeting and never arbitrates."* `proposed` and `final` are **two independent samples**; the association is correlated by construction and has **zero ex-ante value**.

### THE HIGHEST-LEVERAGE UNTESTED ASSUMPTION

**Every fee figure in this stack comes from a config constant with exactly zero variance** — crypto 0.000450, forex 0.000080, futures/us-stock 0.000050. **No venue-reported fill fee exists in this system.** The 9.0 bp crypto round trip is `2 × 4.5 bp`, the Hyperliquid **taker** rate — the worst case. **Maker is 1.5 bp/side.**

**At maker fees the hurdle is 3 bp, not 9 — and the median crypto trip moves from −5.76 bp "dead by construction" to roughly +0.24 bp, i.e. alive.**

**"65.5% dead on arrival" is not a property of the tape; it is a property of a chosen constant.** The most-quoted number in this stack (−11.35 bp net; median trip −5.76 bp) has **never been tested against the assumption that generates it.**

**Pre-registered next experiment, and it is now the top of the queue:** sweep the 1,072-blocked-proposal replay at **0 / 3 / 9 bp** round trip. **Falsifier: if the sign of the headline flips at maker fees, the "no edge" diagnosis is substantially a modelling artifact and the lever becomes execution style (resting vs taking), not entry or exit logic.** Offline, no live risk, not throughput-gated.

### Also recorded

- The agents' own retractions: the adversary retracted its short-gap staleness test as vacuous, and corrected an 08-25 keep count (67.6% → **0 of 68**, a `LIKE`-spacing error) within its own report.
- **Sizing reproduced bit-exact** for run 2235: slot **$745.20** (not $1,800.01 — confirming #73's tilted-allocation finding) × 0.45 = $335.34, **no probation** (4 prior LINKUSDT runs), × size_scale 0.3696 = $123.94, × `null_size_cap` 0.25 = $83.835, × leverage 2.0 = $167.67 ÷ 11.394 = **14.71563981042654**, the filled quantity to the last binary digit.
- **#54's pre-fix 77.8% baseline REPRODUCED** (76/98 = 77.6%) — unlike #68's, it stands.

---

## Reading #78 — 2026-08-29T04:30Z (hourly; 3 agents dispatched — tape present)

**Hypotheses first:** H1 book flat since LINK 2235 close, zero fills → **REFUTED**
(new entry + partial cover); H2 worker healthy on `20260829-reading77` → held
(0 restarts, 0 tracebacks, 0 error/no_verdict events); H3 #592 tally stays
n=3/30 → held (0 stop_mechanism fires).

Context: this cycle ran alongside the owner-ordered 10-agent profit analysis;
its deliverable is **Plan 30** (`docs/plan/30-aggressive-profit-program-2026-08-29.md`,
PR #620) plus committed fee-sweep artifacts in `research/`. Fee-sweep verdict
(pre-registered in #77, now DECIDED): **NO sign flip at maker/zero fee — gross
−6.14bp CI90 < 0; exit mix 167 stops : 6 targets (28:1)**. Retired numbers list
in Plan 30 §7 (includes the old 4.36% keep baseline — all-time is 84/1,412 = 5.95%).

### Profit-or-loss first

**Window (03:15→04:30Z): +$0.0251 realized cash (all fees paid), +$0.036
unrealized on the open half at window end — total ≈ +$0.061.** One trip: run
2251 (agent 60) LINKUSDT short 8.862 @ 11.359 (panel kept 1 of 8, conf 0.58,
the only keep), half-covered 15 min later at 11.338. Accrual view: +$0.0478
net on the covered half (pro-rated entry fee), fees ate 49% of that leg's
gross. Trip stays net-positive iff the open half exits < ≈11.3596; stop
(11.5336) costs −$0.77, target (10.8525) pays +$2.25. Adversary's frame stands:
a +$0.06 draw from a process measured at −17.89bp/trip mean is variance, not
improvement.

### The load-bearing finding: the PANEL authored the payoff truncation

At 03:55Z the desk proposed **sell 0.77 — its highest-confidence call of the
window (press the short)**; the panel's re-sample flipped it 180° to **buy 0.62
(cover half)**, with a self-refuting rationale ("only moved 0.12% of the
expected 4% move, so the edge is diminishing" — 3% progress toward target, 15
min into a 36h horizon, is not evidence of a dying edge). All three agents
agree on the event data; B's "desk-authored cover" label is corrected — under
the wholesale-replacement mechanism the cover and its rationale are the
panel's. Cost shape: $2.21 of target payoff forfeited on that half for $0.048
banked (46:1). In-window hindsight the flip was right (price chopped back to
~11.353), and inside the measured 28:1 stop:target geometry, banking at 2× fees
is locally defensible — **the root defect remains the unreachable target
(Plan 30 B2), but this window shows the truncation channel is the panel, not
only the ratchet.** Keep-rate mechanism note: demotions-to-hold are not the
only panel action; direction flips against 0.77-confidence proposals now have
a live example.

### Algorithm side (B) — $0 authored, correctly; two structural findings

1. **Zero algorithm exits owed, zero fired** (price 11.334–11.371 never near
   any threshold). The one adapt event was a no-op feedback row.
2. **#77 Defect 4's live cost signature, third instance:** ratchet arm =
   $0.2013 (2.222× the real $0.0906 round trip; BREAKEVEN_FEE_RATE default
   0.001 vs booked 0.00045). Peak excursion $0.1772 paid real fees 1.96× over
   yet never armed; ~$0.10 of the post-cover peak was given back with no
   algorithmic protection.
3. **NEW (D-trail-sizing):** trail `activate_usd 2.68` is computed at BUILD
   time on the full max_bet notional ($670.68), but the desk entered at
   size_frac 0.15 — actual tiering is **13.3×** the runtime ratchet arm, not
   the intended 2×. On desk-fractional entries the #589 falsifier ("trail arms
   on ≥1 of first 20 profit-rail fires") is structurally hard to pass.
   Measurable; carry to the next profit-rail fires.
4. Sizing was desk-authored (size_frac 0.15, no size_clamp event; platform
   only capped leverage 3→2). Brackets are the desk's AUTHORED levels
   (stop_pct 1.6 / target_pct 4.4 off the decision mark — bit-exact
   11.5336/10.8525); this entry took the good path, not #77 Defect 2's 23.9%
   discard path. Minor: desk prose said "stop at 11.55" vs compiled 11.5336
   (0.14% drift between stated plan and executable bracket).
5. Fleet: 3 starts / 3 stops in 75 min (~2.4/h vs prior 20h's 5.9/h). One
   churn signature: run 2250 (LINKUSDT) desk-retired **105 seconds** after
   build (risk_context 0.30); planner rebuilt LINKUSDT 2 minutes later as
   2251, whose desk shorted it 4 minutes after that. n=1, logged not chased.
6. Mark freshness nominal (price_updated_at 22s stale; equity cadence ~66s).

### Re-entry under the ledger line (C) — new pre-registered falsifier

2251 is the third LINKUSDT short in ~26h, entered 66 min after 2235's +$0.29
ratchet close — **on cycle 1** (2235 deliberated 3 cycles), with
`desk_ledger` + `predecessor_run` demonstrably in the prompt but zero textual
reference to the prior win in the decision report. Not the H-LEDGER baseline
pattern (that was re-entry after LOSSES); this is re-entry after a win —
unmeasured. **Pre-registered falsifier F-PRED-CYCLE1: over the next 10
first-cycles that carry predecessor context, does the cycle-1 entry rate
exceed the no-predecessor baseline?** H-LEDGER revert guard: NOT tripped
(fills continue; keep occurred).

### Maker lever — live counterexample for C1's design

On this trip, posting maker at the PROPOSAL price (11.352) would have filled
but net LOST $0.032 vs the taker fill (forfeited +6.2bp favorable drift);
posting at the fill level would have saved ~$0.053 of the $0.068 fees paid.
Plan 30 C1's shadow fill simulator must log drift-forfeit vs adverse-selection
per fill — "maker at signal price" is not free money on tape like this.

### Panel demotions check (observation, not conclusion)

7 demotions in-window: none of the demoted symbols approached the ~4.4% target
band within the window (best: AVAX +0.30% favorable = 1/15th of band; SOL buy
demoted then −0.37% against — demotion right). 75-minute windows cannot judge
36h proposals; the instrument is the MFE replay (Plan 30 B2).

### Falsifier board

- **#592:** n=3/30, 3/3 positive (no new fires). n=9 breakeven readout pending.
- **Frozen-mark:** RETIRED as FAILED (#77); replacement metric (median overrun
  ÷ band width per fire) had zero fires to measure this window.
- **#589 trail:** 0 arms; see D-trail-sizing above — the falsifier may be
  structurally unpassable on fractional entries; re-scope proposed at next fire.
- **H-LEDGER:** guard not tripped. New: F-PRED-CYCLE1 (above).
- **#591 panel fallback:** 1 local-fallback activation in the prior 20h window
  (run 2182); none this window.

**Process:** deploys 20260829-reading77 current; mode ② — this reading is
merged without deploy (no desk-actionable content requiring immediate RAG
ingest; 1 reading pending ingest, staleness bound ~6 cycles). Plan 30 merged
this hour (PR #620). Verdicts above stated profit-first; every outcome carries
its reason; disagreements between agents (cover authorship, realized-P&L
convention) resolved in-text.

---

## Reading #79 — 2026-08-29T05:13Z (hourly; quiet — no trade outcomes, no agent dispatch)

**Hypotheses:** H1 2251's open half still open → held. H2 worker healthy → held
(0 restarts, 0 tracebacks). H3 #592 stays n=3/30 → held (0 fires). H4 keep-rate
drought → held (0 of 5 kept).

**Profit-or-loss first:** 0 fills, $0 realized this window. The open LINKUSDT
half-short (run 2251, 4.431 @ 11.359) swung against: mark 11.383 →
**−$0.106 unrealized**, putting the whole trip at ≈**−$0.081 net** (realized
+$0.025 cash minus the open leg). Reasons, not descriptions: (1) the give-back
from the +$0.177 gross peak now totals ~$0.28 with **zero algorithmic
protection** — the ratchet never armed because the arm demands $0.2013 (2.22×
real fees; #77 Defect 4, same instance as #78, now with the cost realized on
the mark rather than hypothetical); (2) in hindsight-so-far the panel's #78
half-cover banked the only profit this trip has produced — consistent with
C's #78 note that banking early is locally rational inside the broken
geometry; the desk's 0.77 press proposal would currently be −$0.21 worse.
Stop 11.5336 is 1.3% away; max_loss $10.06 and at_time 08-30T03:35Z stand.

**Process:** 24 holds across the fleet; 5 demotions (buy 0.55 / sell 0.57 /
buy 0.57 / sell 0.62 / buy 0.55 — all to hold); one new run 2252 built and
running (draft→running 05:07Z), no stops — treadmill quiet this hour. Mark
freshness nominal (45s). No no_verdict, no errors, no panel fallback.
F-PRED-CYCLE1 counter: run 2252's first cycle produced a demoted buy, not an
entry (counts toward the baseline arm, predecessor-context status to be
classified at tally time). Mode ②: merged without deploy; 2 readings pending
RAG ingest (bound ~6).

---

## Reading #80 — 2026-08-29T06:13Z (hourly; quiet — no trade outcomes, no agent dispatch)

**Hypotheses:** H1 2251 open half survives → held (stop never approached after
the 05:13 adverse print). H2 worker healthy → held (0 restarts/tracebacks).
H3 #592 n=3/30 → held (0 fires). H4 keep drought → held (0 of 6 kept).

**Profit-or-loss first:** 0 fills, $0 realized. The open LINKUSDT half-short
recovered: mark 11.329 → **+$0.133 unrealized**, trip 2251 back to ≈**+$0.158
net**. Reason: LINK retraced without the stop (11.5336) being threatened after
05:13; the adverse excursion peaked between readings. The ratchet REMAINS
unarmed — run peak $0.1581 vs arm $0.2013 (Defect 4) — so the position has now
swung +0.18 → −0.11 → +0.13 with zero algorithmic profit protection at any
point. This trip is becoming the cleanest single-trip exhibit of Defect 4's
cost profile (protection absent precisely through a full round-trip of
give-back and recovery).

**Process:** treadmill resumed at prior pace — 8 builds / 6 stops in the hour
(5 idle_retired, 1 desk_retired: run 2252 lived 17 minutes after its
first-cycle demoted buy; F-PRED-CYCLE1 tally note). Fleet 32→35 running
(agent 60: 18, agent 6: 17). 35 holds + 1 retire; panel 0/6 kept (drought
extends: 1 keep in the last 19 discussions). No errors, no no_verdict, marks
fresh (10s). Mode ②: merged without deploy; 3 readings pending RAG ingest
(bound ~6).

---

## Reading #81 — 2026-08-29T07:47Z (hourly; tape — trip 2251 closed; 3 agents + cross-check)

*(Corpus note: this reading analyzes exit truncation. It is NOT a lesson to
bank gains faster or slower; see the RAG-loop finding below before ingesting
more exit-behavior commentary.)*

**Hypotheses:** H1 2251 resolves or rides → RESOLVED (closed, no stop hit).
H2 worker healthy → held (0 restarts/tracebacks; but 2 desk-output truncations,
below). H3 #592 unchanged → held (0 fires — and see the starvation finding).
H4 keep drought → held (0 of 7; 1 keep in the last 26 discussions).

### Profit-or-loss first

**Trip 2251 (LINKUSDT short 8.862 @ 11.359) closed +$0.1953 net** — verified
to the cent by three routes (leg arithmetic, equity chain, trading_runs).
Window realized +$0.170 (covers 3 and 4). Gross $0.2858; **fees $0.0905 =
31.7% of gross** (2235 was 34.2% — the standing regime). +19.4bp on notional
over 2h58m. The deepest print (11.313 at the covers; 11.290 interim) reached
**9.1% of the way to the desk's own 4.46% target — 91% of the authored thesis
was never approached**; realized = 4.4% of the full-target payoff. Two green
trips in a row (+$0.29, +$0.195) remain right-tail draws from a process
measured at −17.89bp/trip mean — not improvement, per the 08-13 law.

### Exit authorship — corrected twice, and a NEW governance gap (D-INTENT-UNDER-HOLD)

Final attribution of the three cuts (A and C disagreed; the executable
artifacts decide):
- Cover 1 (03:55, half): panel flip of the desk's 0.77 press → panel-authored
  (#78 stands for this leg).
- Cover 2 (06:15, quarter): desk proposed FULL cover (buy 0.58); panel final
  was **hold** — **the trade executed anyway** via the desk's
  `order_intent: reduce 0.5` (`run:2251:cyc:7`).
- Cover 3 (06:38, quarter): panel-less cycle; desk `reduce 0.5` railed to 1.0
  by `dust_remainder_closed` (platform-completed).

**The gap:** panel demotion of the ACTION does not bind the intent compiler
for reduces — a "hold" final still trades when the desk's intent block says
reduce. Both such exits also rode on `verdict_salvaged` TRUNCATED desk outputs
(911/977 chars, gpt-oss light route — 2 salvages in one trip; cycle 8's real
reasoning partly lost). The least-audited channel (salvaged verdict →
intent-under-hold → trade) authored 2 of 3 exits. #78's "the panel is the
truncation channel" is corrected: on the full trip it is 1 of 3 panel,
2 of 3 desk-intent-under-hold. No keep-rate statistic sees this channel.

### The ratchet counterfactual — B and C converged independently to the cent

Correction first (B): `peak_pnl_usd` re-anchors to banked total when flat
(run_engine.py:1371) — the INTRA-trip scoped peak reached **97.2% of the arm**
(closest approach 06:14:46Z, $0.0056 short), on a mark up to 60s old (the true
tape may have crossed unseen). The ratchet never armed; partial covers WIDEN
the miss mechanically (each cover raises the realized baseline while floor_qty
stays at max-book).

**Counterfactual at the corrected fee constant (arm ≈$0.0905): arms 03:50:09Z,
locks, and FIRES 04:04:37Z → trip +$0.0734.** Actual desk exits: +$0.1953.
**Defect 4 SAVED +$0.1219 on this trip — stated plainly.** Both agents
computed this independently and agree to the cent. (Their frac=0 variants
disagree on timing/value — 04:12Z/+$0.043 vs 04:33Z/+$0.007 — noted, sign
identical: every armed variant loses to the desk here.) Consequences:
(1) #79/#80's one-sided "Defect 4 cost exhibit" framing is corrected — the
corrected arm trades give-back insurance for recovery forfeiture, and ONLY the
replay population (including recovery-forfeit paths like this one) can sign
the fix — Plan 30 A1's falsifier is upgraded accordingly; (2) with the arm
2.22× overpriced the ratchet is effectively DORMANT at current book sizes, so
**the #592 tally (n=3/30) is starving by construction** — it cannot decide on
live accrual; replay is the only route (consistent with #75).

### The RAG loop is co-authoring the truncation (C; systemic)

2251's recall stream from cycle 3 onward queried "gave back peak … bank the
gain … take partial profit," and cycle 10's top chunk was
`skill:reachable-exits#1` (score 9.59). The multi-cut exit is NOT new behavior
(20 of 109 all-time trips have ≥2 close legs; a 12-trip mono-close streak
08-25→08-29 just ended) — it is a RETURN, now instruction-driven: the lesson
corpus built from our own give-back monitoring commentary teaches the desk to
cut winners, which structurally prevents the 4.5% winner Plan 29/30 requires.
**Recommendation for owner review: audit what exit-behavior content the
desk_memory ingest serves before deploying more monitoring text** (4 readings
currently pending ingest — the lag is currently protective).

### Other findings

- Desk post-flatten hallucination (cycle 10): narrative claims a held position
  and a "$11.00 reduction arm" — run flat, `armed_order_json` NULL. Harmless
  this window; a re-entry on that world-model would not be.
- Re-entry appetite 2-of-2 post-close cycles: cycle 9 blocked by the 45m
  cooldown gate, cycle 10's fresh sell 0.60 demoted by the panel. The ledger
  line's win recap ("profit across all three closes") is teaching return —
  H-LEDGER watch stays open; 2251 can re-enter when cooldown lapses (run
  retires at_time 08-30T03:35Z; idle-retire cannot touch it — it has trades).
- **F-PRED-CYCLE1 has a design defect:** `predecessor_run` sections are
  universal (24/24 runs), so the registered no-predecessor control arm does
  not exist. Re-based on CONTENT (same-symbol prior trip within 24h). Tally
  8/10 collected; cycle-1 entry rate 1/8.
- Churn: 06h was the day's peak (9 starts/7 stops vs 3–5/h baseline). Two
  retire→rebuild loops re-served rejected candidates: SOL 2239→2261 in 52s;
  ZEC 2240→2264 rebuilt in 31s then desk-killed in 106s (second sub-2-min desk
  kill in ~7h). Paid churn = the candidate-quality constraint made visible.
- Marks: cadence 66–68s, max gap 90s, no stale refusals; frozen-mark aliasing
  present at 9+ points including the trip peak (relevant to the 97.2% near-miss).
- Panel 0/7 kept; one demotion RAISED confidence (FIL sell 0.55 → hold 0.58) — odd, logged.

**Process:** mode ② — merged without deploy (and see the RAG-loop
recommendation above: ingest review before the next deploy). Falsifier board:
#592 n=3/30 STARVING (see above); #589 trail unreachable again (activation
$2.68 = 14× trip P&L; D-trail-sizing stands); F-PRED-CYCLE1 re-based;
H-LEDGER guard not tripped (2 fills, keeps present).

---

## Reading #82 — 2026-08-29T08:14Z (hourly; tape — run 2251 re-entered; 3 agents + cross-check)

**Hypotheses:** H1 flat book with re-entry risk from 2251 → the risk case FIRED
(4th consecutive LINKUSDT short in ~29h, 08:09:44Z). H2 worker healthy → held.
H3 churn 3–6/h → held (2 builds, 0 stops).

### Profit-or-loss first

**OPEN — no trip verdict.** Run 2251 trip 2: short 14.84068 @ 11.299,
$167.7 notional, panel KEPT (sell 0.66 → sell 0.58, the window's only keep of
4). Entry fee −$0.0755 took run-lifetime realized to +$0.1199; at window close
uPNL −$0.089 (worst −$0.148 in the first 4 minutes). In expectation this entry
is net-negative at 1.67× the exposure of the process that produced the wins
(−17.89bp mean × $167.7 ≈ −$0.30). Two right-tail draws do not move a
negative mean.

### The headline: size AND risk geometry were authored by the absent-params path (Defect 2, scope EXTENDED)

Cycle 11's `order_params` came back `deferred: true, outcome: "absent"`. All
three agents converge on the consequences, reconstructed to every digit:

1. **Size $167.7 was authored by nobody.** `null_size_cap` fallback: 0.25 ×
   max_bet × lev 2 (size_clamp 104.06→83.83 margin). Trip 1 was DESK-authored
   at size_frac 0.15 → $100.7. **The 1.67× "escalation" is exactly 0.25/0.15 —
   a fallback constant, not conviction: the desk's own conviction scale FELL
   (0.4209 → 0.3103).** An absent-params re-entry is structurally ~1.7× larger
   than this desk's authored size. The code's own measurement of this class:
   **−$178.71 over 46 runs, 66% losers** (vs +$5.57 desk-sized).
2. **The desk's narrated brackets never compiled.** It reasoned "stop 11.48
   (1.6%), target 10.85, R:R>2"; the book holds the DEFAULT_LIMITS
   **11.8629 / 10.1682 (exactly 5%/10%)** — the enforced stop is 3.1× the
   stated risk ($8.52 vs $2.84 incl fees). Trip 1 of the SAME run on the SAME
   thesis drew the authored path (1.6/4.4). Whether a live entry's risk plan
   exists is currently a lottery.

**Pre-registered judgment standard for this trip:** if it loses, the excess of
the loss over a 0.15-sized, 1.6%-stopped loss belongs to the absent-params
path, not the thesis — that is the reason to record, not "timing."
**Plan 30 A2's scope is extended accordingly: honor-authored-brackets must
also cover size (refuse the open or re-fetch once when deferred params return
absent), decided on the 46-run class replay the code comment already carries.**

### The re-entry mechanics (streak vs edge — and the panel as rate limiter)

- Thesis: the SAME RSI/crowding contrarian case — momentum figures **verbatim
  identical** between demoted cycle 10 and kept cycle 11 ("momentum −63%,
  reversal +33%"), no new catalyst, risk_context DOWN (0.55→0.45), entry
  0.21% lower against a fixed target. The only thing that rose: self-reported
  proposal confidence (0.60→0.66) after two green closes — the streak
  signature. Ledger influence unproven: `desk_ledger` was in the brief but the
  decision text never cites the wins (H-LEDGER original arm stays intact,
  unsupported this cycle).
- **The cooldown had already lapsed at cycle 10 (expired 07:23Z)** — only the
  panel blocked re-entry, and its demote rationale was authored over a PHANTOM
  position ("we keep the position, arm a half-size reduction at $11.00" while
  `position_qty 0.0` — #81's hallucination is in the executed verdict chain).
  The demote→keep pair therefore shows no discrimination; C grades the keep a
  variance-class draw. **Structural point: against a desk that re-proposes
  every eligible cycle, a sampling panel is a rate limiter (expected delay ≈
  1/keep-rate cycles), not a filter.**
- **F-STREAK pre-registered** (new arm; the H-LEDGER loss-re-entry falsifier
  is NOT mutated): next N=10 same-symbol re-entries within 24h of a net-green
  close by the same agent — record cycles-to-re-entry, size ratio,
  params_state, panel verdict, confidence delta, net bp. Hypothesis:
  performance ≤ fleet baseline with elevated frequency on unchanged evidence.
  Refuted if mean net bp > 0 with CI excluding baseline or ≥9/10 positive.
  Interim readout n=5. **This entry is tally #1.**
- Fee/geometry: RT ≈ $0.151; to beat trip 1's +$0.195 the trip needs price
  < 11.276 on full size — a new low below the 11.290 level that rejected the
  fade twice in trip 1. Breakeven win rate vs a desk-managed loss at the modal
  +$0.195 winner: ~95% (fleet baseline ≈46%).

### Rails on the new trip (B; all defaults verified)

Ratchet arm ≈ **$0.335 = a 0.20% favorable move (LINK ≤ ~11.276)** — for the
first time in this run's life the arm is REACHABLE at current size (floor_qty
now 14.84); if it arms, #592 finally accrues a live fire. Trail $2.68 (1.60%)
still unreachable in practice (D-trail-sizing stands). max_loss $10.06 is
shadowed by the 5% default stop (fires first at ≈−$8.25). **at_time
2026-08-30T03:35:37Z still binds — trip 2 has 19h26m of horizon** against a
target needing −3.97%. Realistic exit order: desk cycle exits, then ratchet,
then at_time.

### Fleet / process

2 builds, 0 stops (34 running; 17/17). Both builds same-symbol rebuilds by
agent 6: BTCUSDT 2267 (3rd BTC run since 08-28; its sells demoted twice this
window at risk_context 0.25–0.28) and ZECUSDT 2268 (**5th ZEC build since
08-28 13:04** — the slot churns builds against repeated desk/idle rejections;
paid-churn signature n=3). Worker clean (0 restarts/tracebacks, no
no_verdict). Panel 1 of 4 kept. Mode ②: merged without deploy (RAG ingest
review still recommended before next deploy; 6 readings pending — at the
staleness bound; deploy decision deferred to the ingest-content review, which
the RAG-loop finding (#81) makes the safer default).

---

## Reading #83 — 2026-08-29T09:14Z (hourly; INCIDENT — mark blackout → run stop → fleet freeze; self-resolved under observation; 3 agents + cross-check)

**Profit-or-loss first: no realized loss.** The incident's dollar cost was
≈−$0.33 of hidden unrealized drift on the $167.7 LINK short (mark frozen at
11.302 while the tape moved to ~11.322); no fill occurred; the stop was never
within 4.6%. The real cost was integrity: **for 62 minutes (08:32:23→09:34:25Z)
the book's only open position was invisible to every safety rail, and agent
60's entire 16-run fleet was frozen for 47 of those minutes.** Full
auto-recovery at **09:34:48Z was observed live** — `eval_recovered` (first
production firing ever) resumed 16/16 runs; the mark refreshes every 60s again;
the watcher bracket (11.8629/10.1682) is live. Owner was paged at detection and
sent the all-clear.

### Causal chain (A/B/C converged; every step evidenced to the second)

1. **08:33:26Z** — ONE transient LINKUSDT poll failure (a ~15s Hyperliquid
   rate-limit window; healthy again by 08:37:36 when the desk path fetched
   $11.297 successfully). `_record_price_failure` (tasks.py:115) applied the
   default **3600s per-symbol cooldown on the first failure** — the poller
   skipped LINKUSDT every 60s tick for an hour. The system KNEW the fresh
   price at 08:37 and threw it away (desk fetches don't write position marks).
2. Mark age crossed the **900s** staleness rail at 08:47:23 →
   `_evaluate_stop` fail-closed ("refusing to evaluate P&L stops on frozen
   prices"), 5 consecutive failures (limit 5; DB `consecutive_errors=5`) →
   stopping 08:49:40 with `stop_flatten=0` (deliberate: never price a forced
   exit on untrusted data) → **stopped `positions_held` 08:50:16, releasing
   `positions.run_id → NULL` — the DESIGNED stop-and-hold terminal**, not
   corruption (run_engine.py:1691-1693; 2026-07-26 precedent: forced flattens
   on frozen marks cost −$14.41 across six runs).
3. The same frozen mark made fleet 42's shared `marked_equity` fail every
   ~61s tick (`_zombie_pnl` → None on a stale unowned-book mark); at 5
   consecutive failures `_pause_entries` paused **all 16 running members in
   one second (08:51:52-53)**. Per-fleet scope by construction — agent 6
   untouched.
4. **09:33:26Z cooldown expired → 09:33:46 fetch succeeded → 09:34:48
   `eval_recovered`, 16/16 resumed, 16 cycles dispatched 09:34:57.** The
   recovery path (written after the 2026-07-28 fleet-20 deadlock) passed its
   first real exercise.

**Theories killed with data (C):** the truncated verdict (8 minutes of healthy
cycles sit between it and the failure; different loop entirely); a
deploy/restart (worker up 7h continuously). "Hyperliquid caused it" is HALF
right — the blip was the trigger; **the amplifier was ours.**

### Standing defect register (new; all pipeline-fixable, none fixed this session — read-only honored)

- **D-COOLDOWN-AMPLIFIER (MEDIUM, systemic — will recur):** first-failure
  cooldown 3600s vs 60s poll and 900s staleness rail = one bad tick blinds a
  held symbol 4× past the fail-closed threshold, deterministically stopping
  its run and freezing its fleet; a second failure at retry doubles the
  blackout to 2h (cap 6h). Fix candidates for owner/experiment: open-position
  carve-out (short cooldown for symbols with `quantity != 0`) vs a lower env
  default; pre-registered falsifier: replay this incident's timeline under the
  carve-out — blackout must end < 900s and no stop_eval_failed fires.
- **D-WATCHER-STALENESS (LOW-MEDIUM):** the SL/TP watcher evaluates
  `positions.current_price` with NO mark-age check — during the blackout the
  stop was unenforceable while the engine (correctly) failed closed. The two
  layers disagree on failure philosophy: engine fail-closed, watcher
  silent-open.
- **D-MARK-WRITE-PATH (LOW):** the desk's successful 08:37:36 fetch could
  have ended the incident 55 minutes early if cycle-path prices wrote through
  `price_dispatch.apply_price_update`.
- **Config contradiction (LOW):** `ORPHAN_RECLAIM_EXIT=true` on prod while
  the adjacent .env comment says it stays false — desk-driven orphan closing
  is ARMED, possibly unintentionally. Position 483 becomes reclaim-eligible
  ~10:09Z (120-min floor); with the exit arm on, a desk read may close it once
  LINKUSDT blocks fleet 42's rebuild.
- **Dead rails on stopped runs (by design, now with a live instance):** run
  2251's at_time/max_loss/trail will never evaluate again (`control_pass`
  skips `stopped`); the orphan keeps only its row-level SL/TP.

### Falsifier / tally notes

- **F-STREAK #1 (this trip): the 08:32–09:34 window is UNMEASURABLE**
  (mark stood still) — annotate, not zero. Trip 2 remains open, orphaned,
  bracket-managed.
- #592: no fires (the run that could have armed is stopped; the orphan is
  outside the ratchet's scope — watcher bracket only).
- Mark-refresh falsifier note: the #77-retired metric aside, this incident is
  the strongest evidence yet that mark PLUMBING, not mark cadence, is the
  binding risk.
- H-LEDGER revert guard: not tripped (fills present earlier today; keeps
  present).

**Process:** worker healthy throughout (0 restarts — the incident was pure
data-state); 1 no_verdict; panel 0/5 kept this window. Mode ②: merged without
deploy (docs only; the D-COOLDOWN-AMPLIFIER fix awaits owner sign-off +
replay per the experimental-mindset rule — it is the next ship candidate,
ahead of Plan 30 A-items, since it is the only defect shown to take down half
the fleet).

---

## Reading #84 — 2026-08-29T10:13Z (hourly; quiet post-incident — no trade outcomes, no agent dispatch)

**Hypotheses:** H1 orphan 483 open under watcher, possible reclaim close →
open, NO reclaim action yet (eligible ~10:09:44Z, sweeps every 900s; expected
verdict HOLD since a stop is present). H2 fleet 42 stays resumed → held
(33 running, 0 paused; 30 holds this window). H3 LINKUSDT rebuild refusal →
not yet observable (no candidate_skipped rows in window; 1 new build started).
H4 worker healthy → held (0 restarts/tracebacks; 1 no_verdict).

**Profit-or-loss first:** 0 fills, $0 realized. Orphan 483 (short 14.84 @
11.299) marks fresh again — verified by timestamped logs: the last
`skipped_cooldown` line was 09:32:45Z (blackout tail); since 09:33 the poller
reports `updated=1 failed=0` every 60s; position mark 11.300 at 10:13:46Z
(uPNL ≈ −$0.015). The incident's recovery is durable, not a one-tick fluke.
Panel 0/6 kept (drought: 1 keep in the last ~37 discussions). #592 no fires;
F-STREAK #1 open (frozen-window annotation stands); H-LEDGER guard not
tripped. Mode ②: merged without deploy; D-COOLDOWN-AMPLIFIER fix still the
top ship candidate awaiting owner sign-off.

---

## Reading #85 — 2026-08-29T11:13Z (hourly; quiet — deploy cycle; no trade outcomes, no agent dispatch)

**Context: the owner-ordered ship went live mid-window.** PR #628
(`sooppiy-backend:20260829-targets`, worker up 11:06:51Z, rollback
`20260829-reading77`): reachable-target cap (regime-keyed, crypto base
0.30%), `RR_FLOOR=0.2` env, crypto psych brief line, `PSYCH_WEIGHT_LEVEL=high`,
`target_band` teaching line. Decided by the 1,099-trip target sweep
(artifacts in `research/`); falsifiers pre-registered in Plan 30's execution
log (F-TARGET-CAP: ≥30% target-exit share over the first 30 capped fills,
else FAILED; F-PSYCH-WIRE; F-PSYCH-WEIGHT).

**Hypotheses:** H1 orphan 483 open under watcher → held (mark fresh 11.330,
uPNL −$0.46, 4.7% from the 11.8629 stop; no reclaim action). H2 post-deploy
wiring holds → held on first data: **1 of 1** new-image crypto decisions
(run 2260, 11:11:43Z) journals BOTH `crypto_psych` and `target_band`
(F-PSYCH-WIRE 1/1). H3 worker healthy on the new image → held (0 restarts
since 11:06:51, 0 tracebacks, 0 no_verdict). H4 entry-rate rise → too early
(7 min of post-deploy tape).

**Profit-or-loss first:** 0 fills, $0 realized this window; 31 holds, panel
0/5 kept (drought: 1 keep in ~42 discussions), 2 idle retires, 0
stop_mechanism, 0 `target_cap` events (no entries yet — the F-TARGET-CAP
tally opens with the first capped fill). #592 n=3/30 unchanged (and starving
per #81); F-STREAK #1 (2251 trip 2) untouched — the trip is the orphan.
Mode ②: merged without deploy (the ship itself deployed at 11:06Z).

---

## Reading #86 — 2026-08-29T12:13Z (hourly; tape — FIRST TRIP under the reachable-target regime; 3 agents + cross-check)

**Profit-or-loss first:** window +$0.0073 net on $90.26 notional (+0.81bp) —
one trip, run 2259 TAOUSDT short, entered with the FIRST `target_cap` event
(regime caution) and closed 11 min later by the breakeven ratchet. **Fees
took 91.7% of gross.** A winner, but 22× below the sweep's predicted median
(+17.98bp) — the reasons are the two defects below, not variance alone.
Nothing is validated at n=1.

### What worked (verified to the cent, A+B converged)

- **The clamp fired correctly:** authored target 8.09% → capped per its own
  formula; `target_cap` telemetry exact; the ratchet fire was LEGITIMATE —
  the true peak excursion was **0.243%** (the "0.10%" premise was a
  payload-units misread: peak/total are run-cumulative, entry-fee-netted;
  the rail compares baseline-subtracted gross $0.2193 ≥ arm $0.1803).
- **The desk CITED the new crypto psychology line, contrarian-correctly**
  ("long crowding ~2.2 … sentiment greed is elevated, adding contrarian
  pressure") — the human-factor raise is being consumed on its first
  actionable decision. F-PSYCH-WIRE **27/27 (100%)**. F-PSYCH-WEIGHT
  baseline fixed: grep `$.report` only (whole-payload greps score 27/27
  spuriously); report-text citation rate 1/27 overall, **1/1 actionable**.
- **#592 tally n=4/30, 4/4 positive** (+$0.0073) — but this fire banked only
  **5.3% of its peak** (below), which is how the falsifier can pass while
  the mechanism bleeds.
- **H-LEDGER note:** `realized_pnl_usd` wrote the correct non-zero net for
  2259 — the 98.4%-zeros defect did not bite here.
- Panel: 1/1 kept, confidence RAISED 0.56→0.62 — opposite of the drought
  pattern. **Pre-registered discriminator: ≥4 keeps in the next 20
  discussions = panel dynamics changed (p≈0.03 vs the 5.95% baseline); ≤2 =
  coincidence; 3 = extend to 40.** Context against comfort: this was the
  **9th** near-identical TAO short proposal (7 demoted on run 2238, 1 on
  2259), kept at the LOWEST proposed confidence of the nine — the #82
  rate-limiter signature, entangled with the deploy at n=1.

### Two live defects found on trip #1 (C, confirmed against code + tape)

1. **D-CAP-STOP-LEAK — the clamp is RR_FLOOR-leaky.** `eff_cap = max(cap,
   RR_FLOOR×stop_dist, fee_floor)`: the desk's authored 3.68% stop made the
   effective cap **0.736% = 2.45× the evidence-optimal 0.30%**, and 18/25
   recent authored stops exceed 1.5% (median 2.27% → eff ≈0.45%; up to
   1.6%). The sweep optimized a flat 0.30% against a 1.5% stop; the deployed
   machinery routinely delivers 0.45–1.6% against 2–8% stops. The desk's
   teaching failure (0/2 authored-in-band post-deploy; its report still
   recites the OLD "2:1 R-R" and it sized against a fictitious 2.2:1 payoff
   vs the actual 1:5.9 book bracket) passes straight through the clamp via
   the STOP leg. One stop-out at 3.68% (−$3.40) erases ≈466 wins of this
   trip's size. **The unfixed author is the stop side, which the cap never
   touches.**
2. **Poll overrun gutted the ratchet's own floor (Plan 30 B1, second live
   instance):** designed lock floor $0.1503; the 66s scan exited at $0.0885
   gross — **41% below its own floor**; 89% of the designed keep was lost
   between polls (exit slip 0.068% vs the sweep's modeled 0.03%).
   Refinement of Defect 4: within this SAME fire the arm used the legacy
   0.001/leg rate while the fee floor used the real 0.00045/leg — an
   internal asymmetry with an exact fix surface.

### Exit hierarchy on capped trips (B) + falsifier ruling (C adopted over B)

Ratchet arm 0.20% < capped target 0.45–1.6% < trail/stop — **the ratchet
owns the band; the #589 trail is structurally dead on capped trips**
(activate $3.31 vs max band profit $0.66). B proposed F-TARGET-CAP may need
re-registration; **C's ruling stands: the falsifier is sound for the
geometry the experiment tested** — the sweep modeled this exact ratchet at a
0.30% target and still predicted ~62% target exits; the deviation is the
stop-leak, a defect, not a falsifier flaw. F-TARGET-CAP is read stratified
by `eff_cap_pct` (already in telemetry). **Deciding experiment
(pre-registered): re-run the sweep with per-trip eff = max(0.3,
0.2×authored_stop) drawn from the real stop distribution, 60s polling,
0.068% measured slip — predicted target-share <30% means the ship as
configured fails by construction and the fix is stop-side.**

### Open items

- **Orphan 483 unreclaimed 2h+ past eligibility** (mark fresh, −$0.37;
  watcher bracket live; zero orphan events) — carry forward.
- Next-ship queue by leverage (all owner sign-off + experiment): (1) close
  D-CAP-STOP-LEAK (stop-side design — cap the stop or compute both legs
  coherently; the deciding re-sweep above picks), (2) B1 resting price-level
  lock (two live instances now), (3) the arm fee-rate asymmetry (folded into
  the same replay — #81 showed its sign is not free).
- Fleet: 8 idle retires, 1 desk retire (reason given, fee-aware), 2 builds;
  worker clean; marks fresh. Mode ②: merged without deploy.

---

## Reading #87 — 2026-08-29T13:13Z (hourly; quiet — no trade outcomes, no agent dispatch)

**Hypotheses:** H1 panel discriminator advances → 1 discussion, demoted (buy
0.55 → hold): tally 0 keeps / 1 of the next 20. H2 more capped entries → none
(0 fills, 0 target_cap; F-TARGET-CAP stays 0 target-exits / 1 fill). H3
orphan 483 open, unreclaimed → held (mark fresh, uPNL ≈ −$0.19; ~3h past
reclaim eligibility, zero orphan events — open item ages). H4 worker healthy
→ held (0 restarts/tracebacks/no_verdict).

**Profit-or-loss first:** 0 fills, $0 realized. 16 holds; F-PSYCH-WIRE
16/16 this window (cumulative 100% since deploy). Churn light: 3 idle
retires / 3 builds. #592 n=4/30 unchanged. Mode ②: merged without deploy.

---

## Reading #88 — 2026-08-29T14:13Z (hourly; quiet — no trade outcomes, no agent dispatch)

**Hypotheses:** H1 panel discriminator → 0 keeps / 2 discussions (tally 0/3
of 20). H2 capped fills → none (F-TARGET-CAP 0/1 unchanged). H3 orphan → open,
**adverse drift deepened to ≈−$0.83** (mark 11.355, fresh; 4.3% from the
11.8629 stop). All-time `orphan%` events remain ZERO — consistent with #83-B's
"reclaim verdicts HOLD silently when a stop is present," but silent-HOLD vs
loop-not-running is not yet distinguished; open item ages (~4h past
eligibility). H4 worker healthy → held (0 restarts/tracebacks/no_verdict).

**Profit-or-loss first:** 0 fills, $0 realized; the book's only exposure is
the orphan at −$0.83. 14 holds; churn light (1 idle retire, 2 builds). #592
n=4/30 unchanged. Mode ②: merged without deploy.

---

## Reading #89 — 2026-08-29T15:13Z (hourly; quiet — no trade outcomes, no agent dispatch)

**Profit-or-loss first:** 0 fills, $0 realized. The one exposure moved:
**orphan 483's adverse drift accelerated to ≈−$1.83** (mark 11.422, fresh;
LINK rallying against the orphaned short). The watcher stop 11.8629 sits
3.9% away and caps the loss at ≈−$8.4; per the #83 design review the watcher
is the position's only manager and it is live on fresh marks. Hands stay off
per the constraints — this is the stop-and-hold terminal doing its designed
job; the P&L question is whether the 5%-default stop (Defect 2's width)
gets tested before LINK turns.

**Board:** panel 0/1 (discriminator 0/4 of 20); F-TARGET-CAP 0/1 unchanged
(no capped fills); #592 n=4/30; 17 holds + 1 desk retire; 1 no_verdict
(salvage-class, no cluster); churn light (2 builds). Worker healthy. Mode ②:
merged without deploy.

---

## Reading #90 — 2026-08-29T16:13Z (hourly; quiet — no trade outcomes, no agent dispatch)

**Profit-or-loss first:** 0 fills, $0 realized. Orphan 483 retraced to
≈**−$1.32** (mark 11.388, fresh; the 11.8629 watcher stop was never tested —
peak adverse this stretch was ≈−$1.83 at #89). One flat run expired
`stop_event:at_time` (no position, no P&L). Panel 0/1 — discriminator 0/5 of
20. F-TARGET-CAP 0/1, #592 n=4/30, F-PSYCH-WIRE holding (all decisions
crypto-side carry the lines). 19 holds; 1 build. Worker healthy (0
restarts/tracebacks). Mode ②: merged without deploy.

---

## Reading #91 — 2026-08-29T17:13Z (hourly; quiet — no trade outcomes, no agent dispatch)

**Profit-or-loss first:** 0 fills, $0 realized. Orphan 483 at a new adverse
extreme ≈**−$1.88** (mark 11.426, fresh; watcher stop 11.8629 = 3.8% away,
loss capped ≈−$8.4). Zero panel discussions this hour (no proposals at all —
the drought now shows at the proposal layer, not just keeps); discriminator
holds 0/5 of 20. F-TARGET-CAP 0/1, #592 n=4/30 unchanged. 17 holds, 2 idle
retires, worker healthy. Mode ②: merged without deploy (7th consecutive
docs-only cycle since the 11:06Z ship — RAG ingest of readings #85+ pending
the corpus review from #81; the lag remains deliberately protective).

---

## Reading #92 — 2026-08-29T18:13Z (hourly; quiet — no trade outcomes, no agent dispatch)

**Profit-or-loss first:** 0 fills, $0 realized. Orphan 483 eased to ≈−$1.13
(mark 11.375, fresh; stop untested). **Panel-shift discriminator: 0 keeps of
11** (6 more demotions this hour) — trending toward the "coincidence" verdict
(≤2 of 20); the #86 keep increasingly looks like the 9th-re-proposal
rate-limiter event, not a dynamics change. F-TARGET-CAP still 0/1 — no
capped entries in 6.5h since the first; the entry channel, not the new
geometry, remains the binding constraint (consistent with the whole record).
Churn burst: 10 builds / 7 stops (3 flat at_time expiries, 3 desk retires, 1
idle). #592 n=4/30. Worker healthy. Mode ②: merged without deploy.

---

## Reading #93 — 2026-08-29T19:13Z (hourly; quiet — no trade outcomes, no agent dispatch)

**Profit-or-loss first:** 0 fills, $0 realized. Orphan 483 at a new adverse
extreme ≈**−$2.09** (mark 11.440, fresh; watcher stop 11.8629 = 3.6% away,
loss capped ≈−$8.4). **Panel-shift discriminator 0 keeps of 16** — the
coincidence verdict is effectively locked (even 2 keeps in the final 4 lands
at ≤2/20): the #86 keep was the rate-limiter's 9th re-proposal passing, not
changed panel dynamics. F-TARGET-CAP 0/1 (7.5h without a second capped
entry); #592 n=4/30. 31 holds + 3 desk retires; churn 7 builds / 7 stops
(2 flat at_time expiries). Worker healthy. Mode ②: merged without deploy.

---

## Reading #94 — 2026-08-29T20:13Z (hourly; quiet — no trade outcomes, no agent dispatch)

**Profit-or-loss first:** 0 fills, $0 realized. Orphan 483 ≈**−$2.23** (mark
11.449, fresh; watcher stop 3.5% away, capped ≈−$8.4). Panel-shift
discriminator **0 of 18** — two discussions from the formal coincidence
verdict. F-TARGET-CAP 0/1 (8.5h without a second capped entry); #592 n=4/30.
39 holds + 1 desk retire; churn 4 builds / 4 stops (3 idle). Worker healthy.
Mode ②: merged without deploy.

### Reading #95 — 2026-08-30 ~06:20Z (monitoring RESUMED on owner order; first cycle after the Plan 31 round-2 ship)

**P&L: no trades, so no profit and no loss.** Zero fills platform-wide since
the round-2 deploy (03:15Z) — and zero since the Plan 31 ship (01:48Z) before
that. Open book is the single orphan position 483 (agent 60, LINKUSDT short
−14.84 @ 11.299, run_id NULL, by design — hands off): mark 11.391, uPnL
≈ **−$1.37**. Agent-6 run-level P&L holds at the backfilled 53 runs / −7.1072.

**The finding: the desk is refusing the geometry we mandated, and the pair we
mandated has never been tested as a pair.**
- The house-bracket line is wired and accurate — verified in the live worker
  (`target_policy.prompt_line('crypto')` renders the full stop-cap +
  target-cap + "target below stop is the house design" text) and `target_band`
  is present in the brief keys of live decisions (2/2 sampled).
- Yet **15 of 96 decisions since 03:15Z still say a defensible bracket
  "cannot be constructed under current house limits"**, including run 2333
  which RETIRED the slot for it ("inability to size a viable stop/target
  within house limits"). F31-GEOM's secondary falsifier (>2 geometry-citing
  retires per 300 decisions) is not yet fired but is on that trajectory at
  1 per 96.
- Self-correction, recorded: I first read this as the prompt line making a
  false promise, on the theory that the 0.3% take-profit is a hard exit
  (which would need an 82.2% win rate against a measured 42.7%). REFUTED by
  the code — `risk_engine.py:~628` clears the take-profit once the breakeven
  ratchet arms (~16bp of notional at prod BREAKEVEN_ARM_FEES=1.78), so the
  trail does carry winners past the target and the line is truthful. The
  82.2% figure applies only to trips that never arm.
- What survives: the deployed pair (stop 0.5% + target 0.3%) was assembled
  from two experiments that each measured one half against the OLD other
  half — the 0.30% target sweep ran against 1.5–8% stops, and the stop-cap
  replay truncated losses at 0.5% while leaving winners at their actual
  exits. **The pair has never been replayed as a pair, with the TP-clearing
  and trail mechanics in the loop.** The desk's refusal may be correct.
- Action taken: launched that replay as the deciding experiment (arms:
  deployed 0.5/0.3 · 0.3/0.3 — the D7 arm silently dropped at ship · 1.0/0.3 ·
  0.5 with no TP at all · pre-ship control), pre-registered decision rule,
  every figure to be reported with and without the largest contributor. No
  live change until it reports. Nothing was loosened to manufacture entries.

**Falsifier board.**
- **F31-SHOCK-QUIET: PASS (first real result).** Worker started 03:15:06Z;
  33/33 decisions inside the 60-minute fresh window carried `psych_shock`,
  and only **1 of 63 after it** (04:15:06Z, a boundary-adjacent fire). Against
  the pre-ship saturation of 300/300 cycles, the trigger is de-saturated.
- **F31-SHADOW-CENSUS: UNMEASURABLE, and structurally so.** 0 `regime_shadow`
  events. The census fires only on BUY cycles, and there have been 0 buys —
  so the D3 fix cannot be distinguished from a still-dead path by absence.
  It is gated on exactly the event that is scarce. Deadline 2026-09-01T03:15Z.
- **F31-ARM-NONCRYPTO: PASS (in-container).** crypto arm $16.02, us-stock
  $20.00 (legacy restored), polymarket $20.00 (ratchet re-enabled) per $10k.
- **F31-GEOM / F31-ADDS / F31-ARM / F31-FREEZE: unmeasurable — no tape.**
- **F31-TREND: 0 signals**, 5 symbols scanned every cycle; ADX out of the
  25–40 band on all five, so 0 is the arithmetically correct output.
- **F31-PSYCH-SUB: pending** the next research batch.

**Process health.** Worker on `20260830-20260830-plan31r2`, restarts 0, **0
tracebacks in 3h**. Ledger invariant sweeping clean with the new detector
live: `violations: 0, cash_violations: 0`. Decisions 92 hold / 4 retire
(95.8% hold). Trend module ticking hourly.

Mode ①: flat book — merged and deployed per cadence (no code change this
cycle; note-only merge).

### Reading #96 — 2026-08-30 ~07:00Z — THE PAIR REPLAY VERDICT: geometry is not the lever, and reading #95's self-correction was wrong

**P&L: still no trades, so no profit and no loss.** Orphan 483 ≈ −$1.4. But
this reading changes the program's direction, so it is not a quiet one.

**The experiment launched in #95 reported. H1 is DEAD.** Replay of 68 crypto
trips from their real entry fills over OKX 1m candles, exits filled at the
60s polled mark, peak lagged one bar (prod stamps `peak_pnl_usd` after
`_evaluate_stop`), each run's own max_loss/target/trail/at_time, costs 15.8bp:

| arm | mean net bp | CI90 | wr | payoff | ex-largest |
|---|---|---|---|---|---|
| **A deployed 0.5/0.3** | **−22.76** | [−33.86, −12.63] | .338 | 0.415 | −19.63 |
| B 0.3/0.3 (the dropped D7 arm) | −21.72 | [−31.79, −12.64] | .294 | 0.459 | −18.58 |
| C 1.0/0.3 | −27.61 | [−41.13, −15.05] | .368 | 0.338 | −24.55 |
| D 0.5 / no target at all | −22.98 | [−34.97, −11.43] | .294 | 0.587 | −19.86 |
| E control (pre-ship authored) | −33.00 | [−54.02, −13.94] | .338 | 0.388 | −30.02 |

**Every arm is negative on every basis** (raw, 22.6bp cost, intrabar extremes,
300s marks, entry re-anchored to the OKX book to remove the feed-basis error,
basis ≤20bp subset). No sign flip ex-largest for any modelled arm. Paired
same-trip comparisons all contain zero: A−E +10.24 [−2.62, +23.97], A−B
−1.03, A−C +4.85, A−D +0.23. **A is not vindicated and is not distinguishable
from what it replaced.** No stop/target pair — 0.3, 0.5 or 1.0% stop, with or
without a take-profit — produces positive expectancy. Geometry is not the
lever; the entry-side edge is the only one left.

**The desk's refusal is arithmetically correct.** Impossibility proof: at the
measured 42.7% trip win rate, a 30bp target and 15.8bp round-trip cost, the
largest stop that breaks even is **−5.22bp** — negative. No positive stop
exists. (At literally zero cost one exists at 22.4bp, which is inside the
0.15% noise floor.) Breakeven win rate for the deployed bracket is 82.2%
as a hard cap, 70.7% as actually replayed; achieved 33.8%. The desk saying
"our house limits force a stop larger than the target, eliminating any
positive expectancy" is right, and the refusal is protecting the book.

**Correction to reading #95 — my own, stated plainly.** In #95 I "corrected"
myself into believing `risk_engine.py:~628` clears the take-profit once the
ratchet arms, and therefore that the 82.2%-breakeven reading did not apply.
**That was wrong.** The clearing line lives inside `_apply_trailing_stop`,
gated on `use_trailing` from `risk_limits`; the trigger is `+1×trail_pct`
(default 5%), not the breakeven ratchet. Verified on prod: `risk_limits` has
4 rows (agents 11/22/23/56) and **neither running agent — 6 or 60 — has one**,
so both fall to `DEFAULT_LIMITS.use_trailing = 0` and that branch has never
executed for the live book. The take-profit is never cleared. My #95
correction was the error; the original arithmetic stood. (Sub-agent
bookkeeping note, per the three-agent rule: the replay agent reported
`risk_limits` as having ZERO rows — that specific evidence is false; the
conclusion survives on the corrected evidence above. A right answer resting
on a wrong fact still gets corrected.)

**Two new structural defects, both caused by our own 0.30% cap:**
1. **The trailing lock can never arm under it.** Trail activation is
   2 × (notional × flat BREAKEVEN_FEE_RATE 0.001 × 2) = 40bp, and
   `activate_usd` is frozen per run at composition — on this tape 30–3383bp
   of first-entry notional (median 444bp). With the target capped at 30bp the
   position is closed long before activation: **0 trail exits in arm A**, 2 in
   arm D across 68 trips. The cap silently disabled the trailing lock.
2. **The ratchet's operating band is net-negative by construction.** Arm
   16.02bp, floor 4.5 + 0.5×peak bp; with peak capped at 30bp the ratchet can
   only ever fire with a floor in [12.51, 19.50)bp gross — against a 15.8bp
   cost. Replayed: **25 of 29 ratchet fires under arm A are net-negative**,
   median exit 11.74bp gross = −4.06bp net. The most frequent exit author is,
   under our cap, a loss-making device.

Empirical confirmation: across the 68 trips' 145 exit fills, watcher
`take_profit` exits = **0** (desk 87, run flatten 43, watcher stop 8,
armed_exit 7) — the target has never once fired, all-time.

**Decision this cycle: NO live geometry change.** No arm is positive and none
is distinguishable from another, so flipping the cap either way would be a
change without an experimental result behind it — the exact thing the owner
rule forbids. Leaving the cap ON keeps the desk refusing entries, and with
every geometry negative, **flat is the profit-maximising book**: the cap is
functioning as a de-facto trading halt and that is currently worth more than
any bracket we know how to write. The trend module (item 7) — a different
strategy class with its own falsifier — remains the only live candidate for
positive expectancy.

**Falsifier board.** F31-GEOM: primary still unmeasurable (0 entries), but
its premise is now refuted by replay — recorded. F31-SHOCK-QUIET: PASS
(holding). F31-ARM-NONCRYPTO: PASS. F31-SHADOW-CENSUS: still 0, structurally
gated on buys. F31-TREND: 0 signals, ADX out of band on all 5 symbols.
Worker clean, ledger sweeps 0 violations / 0 cash_violations.

Artifacts: `research/replan30/pair_replay_20260830.py`,
`pair_replay_results_20260830.json` (per-trip rows for every arm),
`fetch_candles_1m.py` (the 9.4MB OKX candle cache was deleted; refetchable).
