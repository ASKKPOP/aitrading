# Plan 25 Phase D — v1 Baseline & First v2 Cohort (2026-08-15)

Phase D opened on owner instruction ("do for Phase D") the night Phase C
went live. This file records the v1 baseline that v2 must beat, the first
v2 cohort, and the one operational incident of the evening. Verdicts are
stated in profit-or-loss terms per the owner's monitoring law.

## v1 baseline — closed fleet runs, prod, measured 2026-08-15 00:2xZ

Raw `trading_runs.realized_pnl_usd` (caveat: the raw column misses forced
flattens — the *judging* pass must cross-check with a `pnl_audit` replay;
these figures set the bar, they are not the final audit):

| market | closed runs | Σ realized | mean / run | wins | ever traded |
|---|---|---|---|---|---|
| us-stock | 122 | −$53.38 | **−$0.44** | 16 (13%) | 39 (32%) |
| forex | 38 | −$6.68 | **−$0.18** | 5 (13%) | 18 (47%) |
| crypto (untouched by plan 25) | 68 | −$101.82 | −$1.50 | 17 | 48 |
| futures (untouched) | 45 | −$19.99 | −$0.44 | 15 | 33 |

All closed fleet runs to date are August (all-time == trailing window).
Every v1 cohort is negative expectancy. **The bar for v2 us-stock: mean
per closed run > −$0.44, with ≥ 8 closed v2 runs; a smaller loss is not
success — the target is positive expectancy** (owner law: minus-profit
logic is garbage).

Two structural v1 facts worth carrying into the comparison: 68% of closed
us-stock v1 runs never traded at all (idle/fee retires — capital parked,
then recycled), and the win rate among all closed runs is 13%.

## First v2 cohort — fleet 34 (forevery1969@gmail.com, user 25 / agent 60)

Created 2026-08-15 00:12:28Z: 10 slots, $100,000, risk `extreme`,
archetype `short`(-horizon), market scope unrestricted. Every run this
fleet builds from batches generated after `20260815-plan25-phase-c` is
v2 by construction; the mechanical fingerprint is a non-null
`psych` subscore in the thesis `factor_scores`.

## Incident: research starvation at fleet start (not a Phase C defect)

Fleet 34 logged `research_empty` ×2 at 00:13–00:14Z. Cause: the latest
research batch (`research:496316`, 20:47Z) had **expired at 22:47Z**, and
the evening's four deploys (phase A/B/vix/C) each restarted the worker
before the hourly research tick could fire — the classic
`researched: 0, built: 0` starvation signature, this time deploy-induced.
The loop refreshes ~5 s after worker start, and the 00:10:23Z refresh was
mid-sweep (paced Yahoo factor screen + LLM theses) while the fleet's
first ticks found only the expired batch. Self-healing by design; the
build outcome is recorded below.

**Design note for a future fix (not urgent):** research batches expire
after 2× the refresh interval, but a deploy both kills any in-flight
refresh and resets the timer — a deploy train longer than the expiry
window guarantees a starvation gap. A cheap remedy would be honoring the
previous batch until a successor *exists* (serve-stale-while-refreshing)
or stamping refresh urgency when the latest batch is already expired.

## Fleet 34 first-build outcome (00:24–00:30Z)

The 00:10:23Z startup refresh completed at **00:24:40Z**: batch
`research:496320`, universe 185, survivors 88, persisted 88, `llm: 84`
(healthy — 0 is the regression tell). The fleet built on the next ticks:

- **v2 fingerprint confirmed at thesis level**: 5/8 sampled us-stock
  theses in the batch carry non-null psych subscores (INTU +1.0, SLV
  +1.0, LLY −1.0, T +0.54, GOOGL −0.5; None for symbols outside tilt
  coverage — honest absence, not zero).
- **First 5 members, all running**: BTCUSDT (futures), ETHUSDT (spot),
  HYPEUSDT, SOLUSDT, ZECUSDT (futures) — all crypto, because at 00:30Z
  the session bias excludes closed NYSE and crypto outranked open forex/
  futures candidates (BTC final_score 1.08). Remaining slots backfill one
  per supervise pass; **us-stock v2 members are expected to build near
  the NYSE open**, and only those runs count toward the v2 us-stock
  cohort.
- Run-level fingerprint path note: the first crypto member's frozen
  snapshot shows an empty `subscores` object (crypto psych is always
  None), so the exact JSON path for the run-level cohort split must be
  confirmed against the first **us-stock** v2 run before the judging
  query is trusted.

Phase D is now in its measurement window: wait for ≥ 8 closed v2
us-stock runs, then judge against the −$0.44/run v1 bar with a
`pnl_audit` cross-check.
