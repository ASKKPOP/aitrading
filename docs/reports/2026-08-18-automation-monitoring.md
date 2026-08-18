# 2026-08-18 — AI-FIRST implementation session

Owner directives this session, verbatim and binding:

> *"must be sooppiy AI know you finding that"*
> *"all implement for sooppiy AI everything we monitoring and analysises"*

A finding that lives only in a ledger is engineering trivia. This session
converted measured findings into things the DESK reads or the rails compute.

## Shipped to prod

| PR | what the desk/rail gained |
|---|---|
| #476 | **(a4)** the recall journal names the chunks that were PASSED OVER |
| #477 | us-stock RAG coverage answered by corpus measurement (no gap) |
| #482 | **(a5)** the desk is told when its recall was a COIN FLIP |
| #483 | (a5) post-ship re-measurement |
| #484 | **the desk is told what its own book has ever actually reached** |
| #485 | breakeven ratchet: baseline + round-trip fee fix |

## The three measurements that mattered

**1. Retrieval slot 2 is a coin flip in 44% of cells.** Live prod corpus, all
16 (market x situation) cells: 7 have the second chunk EXACTLY TIED on score
with a chunk the desk was never shown; 2 more have the head tied. Post-ship
the disclosure fires in **11/16 (69%)** because the 1% band also catches near
ties — recorded so nobody reads 11 vs 7 as a discrepancy. The larger reading:
**retrieval at the margin is nearly flat**, which is evidence FOR learned
weights, and why exploration is cheap here.

**2. `target_pct` is decoration — third independent confirmation.** H6/H7
replayed candles; this replayed the ledger's own peaks
(`peak_pnl_usd / opening notional`, which IS the % price move). n=66 closed
runs that opened a position:

| market | n | never positive | median best | best ever |
|---|---|---|---|---|
| crypto | 26 | 42% | 0.17% | **0.97%** |
| futures | 14 | 50% | 0.03% | 0.20% |
| forex | 13 | 46% | 0.01% | 0.05% |
| us-stock | 13 | 31% | 0.09% | 0.89% |

**42% of closed runs never had a positive moment at all. No closed run has
ever peaked above 1% of notional** — against an authored target median of
**4.80%**. Both bracket prompts said "a level the move can realistically
reach" and gave the desk no number for what it actually reaches.

**RISK STATED, NOT TUNED AWAY:** truthful disclosure may push the desk to
tighter stops, and the expectancy of the tighter band (stop ~0.5-0.6%,
target ~1.1-1.2%) is UNMEASURED. **Gating experiment before any RAIL adopts
the band: replay each entry against its horizon and count, per (stop, target)
pair, how often the STOP is hit BEFORE the target.**

**3. The breakeven ratchet fired at a guaranteed loss.** Re-derived from 4
fires (the cycle-13 spec had 2, and contained a contradiction — it compared
run-cumulative `total` against the floor instead of the baseline-corrected
unrealized). AVAX 1335 pos-2 armed on a peak the PREVIOUS closed position
earned; net effect of the fix **+$0.138914**, exactly the running total those
fires had accumulated. **Fourteen cents** — the defect is structural, not
financial at this book size.

## Traps found (add to the standing list)

- **`fees.fee_rate()` is FLAG-DEPENDENT.** Returns the legacy 0.001 for every
  market unless `FEE_PER_MARKET` is on — `true` on prod, **default false
  off-prod**. A test that simply calls `fee_rate` asserts the OPPOSITE of
  production and passes.
- **`BREAKEVEN_FEE_RATE` unset on prod**, so the market rate binds. Had it
  been set, half the ratchet fix would have been a silent no-op.
- **A wiring grep can be satisfied by a NEIGHBOURING call.** Dropping
  `baseline_pnl` from the ratchet's call left the suite green because the
  TRAILING LOCK three lines above passes one too. Scope wiring greps to the
  call expression, not the enclosing function.
- **`test_recall_is_bounded` counts `"\n- "`** to cap how many past FINDINGS
  reach the prompt. An annotation rendered as a bullet trips it — change the
  line shape, never the guard.

## Process notes, reported rather than smoothed over

Three times the process caught the work rather than the reverse: a
pre-existing budget guard rejected the first (a5) draft; two mutants survived
on the ratchet fix and both were VACUOUS TESTS, not code defects; and a prod
"incident" (0 decisions in 26 min) was a query with a FUTURE timestamp — the
system was fine and the check was wrong.

Also: a NaN guard written during (a5) proved to be dead code (NaN comparisons
are always False, so a NaN score already falls through to silence). It was
DELETED rather than propped up with a test written to justify it.

## Queue, in priority order

1. **Fleet slot ledger over-commits after a resize** — 39.9% over budget, a
   permanent halving of diversification. Blocked on the fee/book-size replay;
   the misleading `replenishing:k/N` status string ships independently.
2. **Empty-why arms** — 131 of 132 carry `why: ""`; one was authored 103s
   AFTER its run stopped, with `position_qty: 0.0`, and still persisted.
3. **Predecessor-run brief line (R16)** — the desk re-enters a symbol it
   retired hours earlier with no reference to it.
4. **Arm starvation** — 132 authored, 2 ever fired; 29% of rail-closed arms
   had their level crossed inside the original horizon. Next measurement:
   what the half-reduce would have realized at the crossing.
5. **Panel fallback governance** — `_order_discussion` fails OPEN, so a path
   labelled "not the AI" has authored 10 closes against HANDOFF §7b. Measured
   as NOT costing money (fallback closes realize better on the mean); argue
   it on governance terms only.
6. **Plan 22 (b)** — needs TWO epsilon-scheme classes at >=30 events and >=3
   pairs; had one. The 08-17 rebuild to 19 runs across four markets should
   widen it.
