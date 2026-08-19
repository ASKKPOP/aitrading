# Automation monitoring — 2026-08-19 (UTC day), newest-first

Continued from [2026-08-18](2026-08-18-automation-monitoring.md) (day closed
**−$0.94** ledger, check ok; wipe + rebuild of forevery1969, R20/R21/#480/#481
shipped, Plan 27 rejected, churn/exit-discipline track armed).
Targets: **info@askkpop.com — user 5 / agent 6 / fleet 35**;
**forevery1969@gmail.com — user 25 / agent 60 / fleet 37** (us-stock+forex,
EXTREME; us-stock actively monitored only inside NYSE 13:30–20:00Z).

## Cycle 110 — 16:2xZ (anchor 16:26:50): quiet

No new closes or trades. The only event: adapt scored the FIL 1531 loss
(losing_close −5.3337 → size_mult 0.75, conf_bump 0.05) — the feedback
loop reacting to what cycle 109 showed is substantially a phantom
(stale-fill) loss; noted as a secondary R25 consequence: adapt tightens
the NEXT desk on a loss the desk did not really take. Day **−$1.14**;
both books flat; fleet 38 at 0/25. Fence 0; 0 tracebacks. Churn tally
unchanged (a=3 ≈−$3.4, b=5, c=4, d=2).

## Cycle 109 — 16:0xZ (anchor 16:05:00): FIL 1531 −$5.44 flips the day to −$1.14 — but the loss's true author is a STALE FILL; R25 staged

**PROFIT-OR-LOSS FIRST.** One close: FIL 1531 short (375.65 @ 0.6498,
15:28:29Z) desk-closed in full @ 0.6637 at 15:42:57Z — **−$5.44 net**,
flipping day 08-19 from +$4.19 to **−$1.14** (pnl_audit ok). One
14-minute trade erased more than the day's gains. Two subagents
dispatched; they CONVERGED independently on the root cause and the
cross-check refined one claim (below).

1. **Root cause — the stale fill, found by both agents independently:**
   the short filled at 0.6498, the 15:24–25 cached quote (3.5–4 min
   old), while the live tape printed 0.66–0.67 in a +5.1%/minute
   cascade. The position was **−$5.26 the instant it was marked
   honestly**. At the real 15:28 price (~0.667) the identical round
   trip is a small WIN. The recorded loss is substantially feed latency
   converted into phantom adverse P&L. The staleness also blinded the
   ENTRY decision: the desk's own invalidation (0.652) had already been
   breached on the live tape 3 minutes before the fill.
2. **The phantom cascaded through the house brief:** −$5.18 breached
   the loss-floor advisory ($4.18; run_engine.py:4557 — sole consumer
   is the brief renderer, ZERO forced fires ever, #460 still
   unexercised) → the brief told the desk "past the floor … the house
   rule is to CLOSE" → the desk sold the local bottom. Cross-check
   resolution: Agent A called the floor claim invented; Agent B showed
   the breach was REAL and platform-stated — the desk overstated the
   verb ("forces"), not the fact. The cut itself cost a further
   **~$2.4–2.6** vs holding to its own next cycle (the 0.68008 stop
   would NEVER have filled — session high 0.67124 printed in the entry
   minute and price mean-reverted after the exit).
3. **Churn tally: class (a) n=3** (counterfactual sum ≈ −$3.4), with
   the honest caveat that this instance's compulsion came from the
   platform's own advisory line reacting to a phantom number — the
   lesson here is as much R25's as the desk's.
4. **Detector timing is physics, not lateness:** cascade_shock needs
   the move already printed on an hourly bar; even a 60s daemon could
   not have beaten the 15:28:29 fill. The saving control is a
   quote-age check at fill time — **R25 staged** with a binding
   measurement plan (sweep fills for quote-age distribution and
   phantom-P&L population BEFORE any money-path change).
5. **Hygiene:** 1467 (SBUX) + 1523 (EURCAD), both fleet 37, idle-retired
   $0; open positions platform-wide 0; fence 0 all-time; only one trade
   in window. Fleet 38 back to 0/25.

## 24H SWEEP — 15:3xZ (anchor 15:37:34): fence PASS day 2; R23 confirmed & retired; no_verdict collapsed to 0.63%; fleet 38 gen-2 TRADED

**PROFIT-OR-LOSS FIRST.** 08-18 final **−$0.94**; 08-19 running **+$4.19**
(the −$0.11 move from +4.30 is exactly FIL 1531's entry fee; pnl_audit
check ok both days, resid 0). 17 trades in the 24h tape — every CLOSE
already two-agent-analyzed in cycles 92–95 (KAITO 1462 arc +$4.32, XOM
1426, SUI 1479 +$0.59, UNI 1489 −$0.02); no unanalyzed closes found.

**Adversarial re-proofs (not by absence):**
- **#475 fence: 0 fires in 24h — PASS, day 2** (baseline was 8/1/3/9/day).
- **#480/#481 cap: 2 fires**, both absent-class. Honest ledger: 1479
  closed +$0.591 with the cap COSTING $1.13 forgone; 1481 fenced, $0.
  **R17 re-measure: zero uncapped default-sized entries remain in the
  24h tape** — the default-bet class that authored the SPCX −$35.81 era
  is extinct on this tape; the cap now prices as insurance (both signs
  recorded).
- **R:R rails: 0 floor refusals, 8 ceiling annotations** (no actionable
  ceiling fire in-window).
- **R21 ratchet: 1 fire (1489), epoch baseline VALID** (re-confirmed).
- **R23: 0 dead-run outlook writes across 6h50m** (baseline 13.8/h,
  population 52+). CONFIRMED — retired from active watch to standing.

**Shape stats (24h):** 958 decisions, 98.6% hold; 47 distinct confidence
values, top-3 cluster {0.55/0.58/0.48} = 38.3%; **no_verdict 6/958 =
0.63%** — collapsed from the ~18–23% oversubscription era, with 11
`verdict_salvaged` recoveries doing the absorbing (the parallel
session's salvage rail is working; its residue is the empty-why
authorship gap: **14/65 intents = 21.5%/day baseline** for watch 11).

**Fleet 38 gen-2 traded:** FIL 1531 shorted 375.65 @ 0.6498 on cycle 1
with fully-authored params (no cap fire) — the empty-fleet loop did
NOT repeat; the 14:01Z research wave carried tradeable setups. Loop
watch stands down unless the pattern re-emerges.

**Churn/exit-discipline tally (running):** a=2 (−$0.98) · b=5 (all
green; template validated on 1462's full life) · c=4 (all losers) ·
d=2 (−$0.41/+$0.08) · e/f minor · user-forced=1. No decisive-weight
threshold crossed; the lesson keeps accumulating.

Docs→main batch: PR #493 (cycles 93–108 + this sweep + backlog + Plan 27).

## Cycle 108 — 15:2xZ (anchor 15:26:54): quiet; fleet 38 rebuild wave begins (FIL 1531) — loop watch live

No closes, no trades, no rail fires. Day **+$4.30**; fence 0;
0 tracebacks; R23 **0 dead at 6h40m**.

Fleet 38 built its first second-generation run (FILUSDT 1531, 1/25) —
the fuse-vs-gate LOOP WATCH is now live: if this cohort also holds 12
cycles and retires untradeable, the repeat is the reproduced evidence
for an R-item (cycle 107). Fleet 37 added NOW 1530 (hot-tech roster
name) + UBER 1532; its five 14:03Z us-stock desks still cycling, no
entries. Churn tally unchanged.

## Cycle 107 — 14:5xZ (anchor 14:56:50): FLEET 38 IS EMPTY (0/25) — the $10k fleet self-retired in 5.5h with zero trades

No closes with P&L, no trades, no rail fires. Day **+$4.30**; fence 0;
0 tracebacks; R23 **0 dead at 6h10m**.

UNI 1521 idle-retired at 14:28Z — the last one. Fleet 38's full life:
built 08:58Z, 10 runs across 10 crypto names, **zero trades, $0.00 P&L,
empty by 14:28Z** (status `replenishing:0/25`). Nothing was lost except
LLM cycles (~120 desk decisions all concluding "weak setup"). The 14:01Z
research batch has 5 selectable crypto names, so a rebuild wave may
start; if the new cohort repeats the hold→fuse→gate loop, the repeat
itself becomes the actionable evidence (pure research/LLM burn for $0)
— that would justify an R-item on the pre-gate candidate pool or the
fuse-vs-build interlock. One pass is discipline; a loop is waste.

Fleet 37's five new us-stock desks are cycling (2–3 decisions each,
CRM/ORCL/PYPL/JNJ/V), no entries yet under the EXTREME appetite.

## Cycle 106 — 14:2xZ (anchor 14:26:56): fleet 37 built 5 us-stock runs at the open (3 hot-tech); fleet 38 down to 1/25; no trades

No closes with P&L, no trades, no rail fires. Day **+$4.30**; fence 0;
0 tracebacks; R23 **0 dead at 5h40m**.

1. **NYSE-open build burst (fleet 37):** CRM, ORCL, PYPL, JNJ, V
   (1525–1529) at 14:03Z — CRM/ORCL/PYPL are US_TECH_HOT_UNIVERSE
   names leading the batch, consistent with the R20 seed's ordering
   guarantee. Fleet 37 at 23 running. First us-stock entries under
   EXTREME appetite now possible — watch closely.
2. **Fleet 38 collapse nearly complete: 1/25** (UNI 1521 alone; SOL
   1518 idle-retired this window, $0). Same explained chain as cycle
   105; the 12:30Z research batch had ZERO selectable crypto, 14:01Z
   has 5 — if a rebuild wave follows, the fuse-vs-gate cycle repeats.
   Still nothing to ship: refusal of weak setups is the law working.
3. Fleet 37 also shed 1459 + CHFJPY 1520 (idle, $0).

## Cycle 105 — 13:5xZ (anchor 13:56:53): fleet 38 has collapsed to 2/25 with zero trades ever — emergent, owner-visible

No closes with P&L (all retires $0, no positions ever held), no rail
fires. Day **+$4.30**; fence 0; 0 tracebacks; R23 **0 dead at 5h10m**.

**The headline: the owner's new $10k crypto fleet is nearly empty.**
Built 09:00Z, 25 slots; by 13:56Z only SOL 1518 + UNI 1521 run. Five
more never-traded idle-retires this window (SUI BTC KAITO ZEC + WLD
overlap), all $0. The full causal chain, each link working as designed:
(1) the desks scored every setup weak and declined entry for 12 straight
cycles — BTC's final read: conviction 0.355, momentum 0.3, entry_quality
0.2, bias flat, "price above entry reference" on a SHORT-archetype
fleet; (2) the 12-cycle idle fuse retired them; (3) replacements are
blocked — the expectancy gate drops AAVE every pass and ETH/FIL/HYPE/VVV
filter pre-gate. **Emergent result: capital fully preserved, fleet
functionally dead.** Not shipping anything — an AI that refuses weak
setups is exercising exactly the discipline the profit law demands, and
forcing entries would be the garbage the owner's rule names. Recorded
prominently because the owner will see an empty fleet: if FILL is the
goal, the lever is pre-gate candidate breadth (universe/direction
filters), not the gates. NYSE open; fleet 37 us-stock in active watch —
no entries yet this window.

## Cycle 104 — 13:2xZ (anchor 13:26:51): quiet; fleet 38 thinning by its own fuse (6/25)

No closes with P&L, no trades, no rail fires. Two more never-traded
fleet-38 idle-retires (WLD 1512, LINK 1516, $0 each — the 12-cycle fuse
reaching the 08:59-built cohort). Fleet 38 now 6/25 running: the
expectancy gate refuses the only replacement candidate (AAVE), so the
fleet shrinks rather than churns — capital preserved, exposure thin.
Fleet 37 at 20. Both books flat; day **+$4.30**. Fence 0; 0 tracebacks;
R23 **0 dead-run writes at 4h40m**. NYSE opened 13:30Z — us-stock
entries possible from next cycle.

## Cycle 103 — 12:5xZ (anchor 12:56:51): quiet

No closes, no trades, no rail fires. One replacement build (EURCHF 1524,
fleet 37). 14 decisions; both books flat; day **+$4.30**. Fence 0;
0 tracebacks; R23 **0 dead-run writes at 4h10m**. NYSE opens 13:30Z —
fleet 37's 8 us-stock runs enter active monitoring next cycle.

## Cycle 102 — 12:2xZ (anchor 12:26:50): quiet

No closes, no trades, no rail fires. One never-traded idle-retire
(EURUSD 1509, fleet 37, $0 — routine fuse). 14 decisions; both books
flat; day **+$4.30**. Fence 0; 0 tracebacks; R23 **0 dead-run writes
at 3h40m**. Churn tally unchanged. NYSE opens 13:30Z (next cycle +1).

## Cycle 101 — 11:5xZ (anchor 11:56:47): quiet; fleet-38 fill watch CLOSED — explained by the expectancy gate, working as designed

No closes, no trades, no rail fires. Day **+$4.30**; both books flat.
Fence 0; 0 tracebacks; R23 **0 dead-run writes at 3h10m**.

The cycle-100 fill watch resolves: research is healthy (batch 496427 at
11:21Z, 14 crypto theses / 13 selectable), but every replacement pass
reaches the backtest gate with a candidate pool of exactly **{AAVEUSDT}**
and drops it — `non-positive expectancy −367.51 USD/trade` — seven
identical gate events 09:33→11:53. ETH/FIL/HYPE/VVV never reach the gate
(pre-gate filtering: direction/maturity/ranking). The fleet holds 17
slots WAITING rather than forcing a negative-expectancy build — the
documented two-candidate-pool design (C9), protecting expectancy over
fill. Not a stall; watch closed. Residual question (why the other 4
names filter pre-gate) matters only if the owner wants fuller slots.

## Cycle 100 — 11:2xZ (anchor 11:26:47): quiet

No closes, no trades, no rail fires. One never-traded idle-retire
(NZDUSD 1505, fleet 37, $0 — routine fuse). 14 decisions; both books
flat; day **+$4.30**. Fence 0; 0 tracebacks; R23 metric **0 dead-run
writes at 2h40m**. Fleet 38 still 8/25 (no builds since 09:16 — watch
whether replenish resumes or candidates are thin), fleet 37 at 20.
Churn tally unchanged.

## Cycle 99 — 10:5xZ (anchor 10:56:45): quiet

No closes, no trades, no rail fires, no run churn. 14 decisions, all
holds; 812 equity ticks (worker healthy). Both books flat; day **+$4.30**.
Fence 0; 0 tracebacks; R23 metric **0 dead-run writes at 130 min**.
Churn tally unchanged.

## Cycle 98 — 10:2xZ (anchor 10:26:45): quiet; routine fleet-37 forex rotation

No closes with P&L, no trades, no rail fires. Fleet 37 rotated three
never-traded forex slots (GBPUSD 1500 / GBPCHF 1501 / USDCAD 1502
idle_retired, $0 each — the 12-cycle fuse) and built GBPAUD 1522 +
EURCAD 1523; 21 running. Fleet 38 steady at 8/25, still all-holds.
Both books flat; day **+$4.30**. Fence 0; 0 tracebacks; R23 metric
**0 dead-run writes at 100 min**. Churn tally unchanged.

## Cycle 97 — 09:5xZ (anchor 09:56:46): quiet

No closes, no trades, no rail fires. 17 decisions in window, all holds
(fleet 38's fresh crypto runs sizing up their theses; fleet 38 at 8/25
running, fleet 37 at 22 running). Both books flat. Day holds **+$4.30**.
Fence 0; 0 tracebacks; R23 metric now **0 dead-run writes at 70 min**
post-fence (strengthens the PASS). Churn tally unchanged. Nothing to
analyze, nothing to ship.

## Cycle 96 — 09:1xZ (anchor 09:19:58): R23 metric DECISIVE PASS (32 writes, 0 to dead runs); owner rebuilt as FLEET 38 (agent 6, crypto); no closes

**PROFIT-OR-LOSS FIRST.** No closes in the window; day 08-19 holds at
**+$4.30 ledger**. No open positions yet — fleet 38's fresh runs are in
their first cycles.

1. **R23 binding metric: PASS, now decisive.** 33 min post-fence:
   **32 outlook writes total, 0 to dead runs** — the sweeper is
   demonstrably ticking and the old-code expectation for this window was
   ~6 dead-run writes (baseline ~11/h against a GROWN population of 52+
   stopped runs on slots). The fix moved its own metric. Confirm once
   more at the daily sweep, then the watch retires to the standing list.
2. **The fleet-35 stop was a stop-and-rebuild:** FLEET 38 created
   (agent 6, 25 slots, $10,012). Nine crypto runs built by anchor
   (WLD SUI BTC KAITO LINK ZEC SOL BNB UNI 1512–1521); fleet 37
   (agent 60) replenished CHFJPY 1520 + INTU 1511. All-crypto so far —
   R20 hot-tech seed binds only if a us-stock slot appears; watching.
3. **1519 BNB insta-retire, $0:** desk retired at cycle 1 (conviction
   0.47, momentum 0.3) and the replacement chain stopped at one — the
   post-#220-era churn guard shape working; no cost, no repeat.
4. **Watches:** fence **0** ✓; 0 tracebacks; no cap fires; no ratchet
   fires (R21 closed VALIDATED last cycle); R22 no instances; loss
   floor unexercised; SPCX tripwire idle; churn tally unchanged (a=2
   −$0.98, b=5 all green, c=4 all losers, d=2 net ≈−$0.33); empty-why
   authorship watch armed (baseline: 7/17 on 1462, count per-day at
   the sweep); NYSE opens 13:30Z — fleet 37's us-stock runs enter
   active monitoring then.

## Cycle 95 — 08:4xZ (anchor 08:49:11): OWNER STOPPED FLEET 35 — book fully flat; run 1462 ends **+$4.32 lifetime**, harvest template validated; day +$4.30

**PROFIT-OR-LOSS FIRST.** One closed leg: the owner issued `fleet_stop_all`
on fleet 35 at 08:16:57Z (11 runs; the "12" in my first count was events —
1462 emitted two transitions — cross-check resolved arithmetically). The
KAITO 1462 runner flattened 20s later @ 0.33736 — **exactly the prevailing
mark, zero slippage** — for **+$0.5346 true net**; ledger reconciles to
the 5th decimal (adapt 0.5504 = exit-fee-only convention). Run 1462
lifetime: **+$4.3231** (≈+$4.17 fully-net of entry fees). Day 08-19:
**+$4.30 ledger** (pnl_audit ok). Agent 6 now has NO fleet; fleet 37
(agent 60) stays active. Two subagents dispatched, cross-checked, full
agreement after the 11-vs-12 resolution.

1. **The user stop was well-timed at today's mark:** KAITO now trades
   0.3443 — ABOVE the 0.3429 entry — so the runner would be −$0.15
   unrealized vs +$0.55 banked: the stop is **+$0.70 ahead** at this
   instant (mark-now statement, not proof the desk plan — stop 0.3549,
   target 0.295, 32h left — would have lost).
2. **Harvest template: validated end-to-end on a full run life.** Second
   short banked in four covers (0.33904/0.3369/0.33792/0.33736), every
   fill below entry, zero give-backs, forced end still caught the runner
   green. Class (d) gets its SECOND instance and its first WIN: cyc31's
   panel proposed sell at 0.3381 (the worst of the three late marks),
   the desk overrode to hold → +$0.076 ex post. **d-tally: n=2, −$0.41 /
   +$0.08 — the override class is not one-sided.** Final leg class:
   user-forced/none. Running tally: a=2 (−$0.98), b=5 (all green), c=4
   (all losers), d=2 (net ≈−$0.33), e/f minor.
3. **NEW AUTHORSHIP FINDING — empty-why intents:** 7 of 17 order_intents
   in 1462's life carried `why: ""`, and cyc30 emitted NO intent/outlook
   at all. Three cases proven truncation-linked (`verdict_salvaged
   {kind: truncated}` same-second: cyc11/26/30 — cyc30's reply died
   before the intent section); cyc29 **executed a real trade (reduce
   0.5) with no stated reason**. The truncation/oversubscription
   signature is now touching order authorship, not just verdicts.
   Watch opened: count empty-why intents per day; if the rate holds,
   this becomes an R-item (the salvage rail may need to re-request the
   intent block, not just salvage the verdict).
4. **R23 binding metric — INCONCLUSIVE at 5.5 min, honestly stated:**
   0 dead-run outlook writes since the new worker (08:46:35Z), but also
   0 outlook writes TOTAL — the sweeper likely hasn't ticked yet.
   Exposure went UP (52 stopped runs now bound to slots; fleet 35's
   fresh stops joined the population; old-code baseline ~11/h means
   ~10 expected writes by the 1h mark). Decisive read next cycle.
5. **Watches:** fence **0** (all-time ✓); 0 tracebacks; stop-down hygiene
   clean (0 wedged, 0 orphan positions); no other trades in window;
   loss floor unexercised; R22 no new instances; SPCX tripwire idle;
   watch for an agent-6 fleet REBUILD (stop may precede one — R20
   hot-tech seed applies if us-stock-scoped).

## SHIP — 08:4xZ: R23 sweeper stopped-run fence LIVE as `20260819-r23-sweeperfence` (PR #492)

Pipeline complete, per implement-every-time: fail-before (new test
`test_stopped_run_is_never_swept` failed 3/3 cells on unfixed code — the
unfixed code IS the mutant, so this doubles as the mutation proof) →
pass-after (file 28 ✓, **full suite 4529 + 1349 subtests** in a clean
worktree off origin/main) → ruff clean → CI 5/5 → squash-merged `8d6a62ac`
→ deployed via `scripts/deploy.sh`, all surfaces 200, rollback
`20260819-band-caveat` recorded.

The fix: one terminal-status fence in `_sweep_slot`
([outlook_refresher.py:374](../../service/server/outlook_refresher.py) in
the shipped image) — `STATUS_STOPPED` returns before any work; paused runs
(the legitimate `run_idle` cold path) sweep unchanged, pinned by the
existing test.

**Live verification (3 angles):** (1) fence present in the RUNNING
worker (grep in-container, line 374); (2) 0 tracebacks post-restart;
(3) the single post-deploy dead-run outlook (1492 EURAUD, 08:45:09Z)
**predates the new worker's 08:46:35Z start by 86s** — it was the old
image's final sweep; zero since. In-image pytest run not possible: this
image variant ships without pytest (new runbook note; the local+CI
suites and in-container grep stand in).

**BINDING POST-SHIP METRIC:** outlook writes to stopped runs per hour.
Baseline ≈13.8/h (~7 per half-hour window). Expected ~0 (only the benign
in-flight cycle race remains possible, `source:"cycle"`). Measure from
anchor **2026-08-19T08:46:35Z** at the next cycle and the daily sweep;
if the stream persists, the fix FAILED and must be reported as failed.

## Cycle 94 — 07:4xZ (anchor 07:49:52): catch-up window 23:44→07:49 (loop slept overnight); day +$3.75; R21 FIRST LIVE FIRE = VALID; sweeper waste measured → R23 ships

**PROFIT-OR-LOSS FIRST.** Day 08-19 ledger **+$3.75** (pnl_audit ok, resid
0.00); 08-18 final **−$0.94**. Window realized: AI-authored **+$3.68 true
net** (1479 SUIUSDT +$0.591 full close; 1462 KAITO +$3.09 across three
staged banks), algorithm-authored **−$0.016** (1489 ratchet flatten). Open
book: KAITO remainder short 102.14 @ 0.3429, ≈+$0.48 at mark. No AI-authored
losing leg in the window. Two subagents dispatched and cross-checked; one
disagreement, resolved by evidence (below). Loop gap stated plainly: the
session slept 00:13→07:43Z — no cycles fired; this note covers the full
8-hour tape.

1. **R21's first live fire happened and the epoch baseline HELD.** The
   1489 UNIUSDT "trailing_lock" kill (03:16:31Z, −$0.0157) was actually
   the breakeven ratchet — provable only because the parallel session's
   new `stop_mechanism` discriminator event landed (image now
   `20260819-band-caveat`). Cross-check drama: my own brief told Agent A
   the position was "never green"; Agent B refuted it from the equity
   tape (own excursion +$0.0355 ≥ arm $0.02, base = `peak_realized_usd`
   −0.0045 — a genuine peak, no phantom). Fire saved ≈$0.075 vs the live
   mark (n=1). **R21 closes VALIDATED.** New logged dimension: the arm is
   fee-anchored at 0.1%/side vs actual 0.045%/side (2.2× true round
   trip), and on a $10 probe book the fire stops the whole run —
   degenerate-scale watch, not a defect.
2. **Sweeper waste is real and bigger than flagged → R23 ships now.**
   112 outlooks written to stopped runs in 8h (19.8% of ALL outlook
   writes, ≈13.8 LLM calls/hour, zero algo fallbacks), worst case 23h
   post-stop. Root cause verified in code by both Agent B and the main
   session: `outlook_refresher.py:143` treats `status != "running"` as
   sweepable; no stopped-run fence exists. On a ~5× oversubscribed LLM
   this feeds the no_verdict signature directly. Non-money-path fix; per
   implement-every-time it ships this session (pipeline binds).
3. **Churn/exit-discipline tally (watch 8):** class (b) bank-into-strength
   **+4 instances, all green** — 1479's panel-flipped full close (analyst
   sell 0.55 → final 0.71 bank; 0.6497 was the window's exact low; saved
   ≈$2.59 vs holding to mark — the desk's stated reason "negative
   expectancy on further hold" was RIGHT), and 1462's arm:26 (+$1.45) /
   cyc28 (+$1.16, covered below mark) / cyc29 (+$0.48). Zero class (a)
   churn, zero (c) re-entries-against-invalidation (1462 cyc25 re-entry
   was consistent with its own plan — harvest-and-re-enter, fully
   bracketed this time). Minor (f): 1479 cyc8 outlook still said "short"
   while the order flattened; and the desk mis-computed its own net
   (+$0.41 claimed vs +$0.59 actual). Running tally: a=2 (−$0.98 measured),
   b=5 (all validated green), c=4 (all losers), d=1 (~$0.41), e/f minor.
4. **Rail insurance priced honestly (both directions):** null_size_cap
   cost **$1.13 forgone** on the 1479 winner (uncapped +$1.72 vs +$0.59)
   after saving on earlier unsized losers — 4 fires all-time confirmed
   (the 4th, 1481 cyc12, was a zombie-cycle race: idle_retired 03:22:31,
   decision landed 03:23:31, cap fired, execute fence blocked — $0,
   chain worked). 1462's stop_coherence clamp (248→140) forwent ≈$2.93
   on the winning re-entry but enforced the $9.81 loss envelope it
   exists for. arm:26 executed timely at first sub-level poll with a
   favorable fill (−0.28% slippage); hindsight cost $0.50 vs the desk's
   next cycle — machine did what it was armed to do.
5. **New finding (R24 staged):** size-omission is the DEFERRED branch,
   not the light route — 2/2 deferred actionable decisions produced
   `outcome: absent` → cap; 3/3 non-deferred authored params. The
   "AUTHOR IT EVERY TIME" prompt line cannot bind where params are never
   produced. Fix needs design (money-path); gate on more instances.
6. **Watches:** fence **0** ✓ (day 2 post-#475); 0 tracebacks;
   `verdict_salvaged` ×4 in window (parallel session's salvage of
   truncated LLM replies — one salvage fed the live armed exit; watch
   quality); 1479 post-close is an untradeable-thesis slot (15 straight
   holds, R:R rail rejects every bracket at current geometry — idle fuse
   should clear it); R22 no new instances; loss floor unexercised; SPCX
   tripwire idle; #473 no clamp→bigger-request pair (1479 closed instead).

<!-- cycle notes append above this line's predecessor, newest first -->
