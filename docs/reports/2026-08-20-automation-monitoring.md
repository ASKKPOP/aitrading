# Automation monitoring — 2026-08-20 (UTC day), newest-first

Continued from [2026-08-19](2026-08-19-automation-monitoring.md) (day closed
**−$1.14** ledger; owner diagnosis shipped #494 goal-is-AI's + #495 R26
direction-matched gate + R23 sweeper fence; fleet 38 resized to 7 slots;
FIL stale-fill loss analyzed → R25 staged).
Targets: **info@askkpop.com — user 5 / agent 6 / fleet 38** (7 slots,
$10,012, crypto); **forevery1969@gmail.com — user 25 / agent 60 /
fleet 37** (us-stock+forex, EXTREME; us-stock watched 13:30–20:00Z).

## SHIP — 02:0xZ: R25 fill-mark refresh LIVE as `20260820-r25-markrefresh` (PR #497) — owner-ordered "do fix"

At the execution boundary of run_cycle: cycles older than 45s (every
real cycle — the LLM sits between mark fetch and order) re-fetch the
mark; **opens are refused past 0.75% drift** since the decision mark
(`gate_skip stage=mark_drift` — the FIL 1531 case, +2.6%, would have
been refused instead of filled −$5.26 underwater); **exits always fill
at the fresh mark**; drift ≥0.05% journals `mark_refresh` (fill-time
mark age becomes measurable forward — the data R25's measurement plan
lacked); refetch failure falls back fail-open. Design note recorded
honestly: draft 1 (unconditional refetch) broke 36 tests against the
mocked-entry estate and was replaced by the cycle-age gate, which is
also more correct. Pipeline: fail-before 3/5 on the unfixed engine →
file 63/63 → full suite 4540 + 1349 → CI 5/5 → squash `b50eb1c2` →
deployed, all surfaces 200, rollback `20260819-rag-a7-flat`. Verified
in the running worker, 0 tracebacks.

**Between-ship tape (next cycle dispatches the two-agent law):**
LTC 1556 closed 01:09:57Z by the breakeven ratchet's SECOND live fire —
numbers verified sane at first read (peak +$1.9013, fee-anchored arm
$0.7009, genuinely armed on its own excursion, fired at ~breakeven on
the round-trip; leg −$0.1428, run −$0.30).

## Cycle 120 — 00:4xZ (anchor 00:45:13): micro-window (2 min — displaced cron release), nothing new

No events. LTC 1556 long +$0.95 unrealized. Fence 0; 0 tracebacks.

## Cycle 119 — 00:4xZ (anchor 2026-08-20T00:43:21): R26 POSITIVE PROOF — AAVE BUILT after 7× drops; LTC long opened with cap fire #5

**PROFIT-OR-LOSS FIRST.** 08-19 final **−$1.14**; 08-20 opens −$0.16
(LTC entry fee only). One OPEN trade, no closes → no dispatch. Fence 0;
0 tracebacks.

1. **R26's binding metric is MET, behaviorally:** fleet 38's gen-4 wave
   built **AAVEUSDT 1554** — the symbol the gate refused 7+ times
   yesterday on inverted long-only evidence — plus BNB 1555, LTC 1556,
   LIT 1557. No fleet-38 gate event accompanies the wave, consistent
   with a no-drop pass (events journal drops). Fresh universe names
   (LTC, LIT) also appearing — candidate supply widening. Fleet 37's
   passes keep vetoing only direction-matched LONG theses (TSLA/MRK/
   LLY/ABBV — all long, checked).
2. **First gen-4 trade: LTCUSDT long** 7.46 @ 46.974 ($350 notional,
   5× lev, stop 46.598) — **null_size_cap fire #5** (parsed_null,
   152.7→70.08 margin). Cap ledger: 5 fires (3 parsed_null + 2 absent);
   save/cost measured at close; #473 pair check on 1556's next cycle.
   Notional $350 vs the $52 post-fix median — the 7-slot concentration
   is showing in trade size, as the diagnosis predicted.
3. Routine: AVAX 1538 (gen-3 last) + AUDCAD 1543 + AUDJPY 1544 idle-
   retired, $0 each; EURUSD 1553 built (fleet 37). Loop gap 23:26→00:43
   noted (cron displaced ~1h).

<!-- newest-first -->
