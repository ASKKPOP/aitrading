# 2026-08-08 — automation monitoring (newest first)

Day 2 of the reset book (seed 1000, reset 2026-08-06 ~22:56Z). From today the
corpus-read obligation is in force: the desk carries `_recall_line`, and this
session must search `desk_memory` BEFORE proposing any fix and say what it
returned.

---

## Cycle — 00:59Z · steady state; new runs on distinct slots

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
