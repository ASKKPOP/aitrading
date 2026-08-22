# Automation monitoring — 2026-08-22 (UTC day), newest-first

Continued from [2026-08-21](2026-08-21-automation-monitoring.md) (day closed
with **ZERO trades — no realized row**; R33 shipped/untested; R28 shipped,
measured harmful, reverted same day; rails flawless throughout).
Targets: **info@askkpop.com — user 5 / agent 6 / fleet 38** (7 slots, ~$10k,
crypto); **forevery1969@gmail.com — user 25 / agent 60 / fleet 37**
(us-stock+forex, EXTREME; us-stock watched 13:30–20:00Z).

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
