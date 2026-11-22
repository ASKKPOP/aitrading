# Automation monitoring — 2026-11-22 (UTC day) — daily 24h sweep

Newest-first. Authority for rules/access/traps: `HANDOFF-automation-monitoring.md`.

## 24h sweep — 2026-11-22T15:13:12Z (KST day 2026-11-22 = 11-21T15:00Z → 11-22T15:00Z, closed)

Prod clock `SELECT UTC_TIMESTAMP()` = 2026-11-22 15:13:12 (on schedule). Image: `.env` = worker = backend =
`sooppiy-backend:20261121-sweep-20261121` (2bb2992). origin/main = 0237437, and 2bb2992..0237437 is 2 lines of notes, so there is
**no code drift** (19 h, under the one-day rule).

**Trading set re-derived = {6} with zero activity.** Active/building fleets: only fleet 54 (agent 6, `replenishing:0/6`). Runs with
`last_cycle_at` in the last 24 h: **none**. Runs started in the last 36 h: **none**. Agent 60 is still not trading. Fleets 43 and 42 are
`stopped` (`fleet_stop_all`), even though `ai_automation_state='active'`. Agent 63 (trend-module) still holds 3 pre-block crypto shorts
and is out of scope.

### 1. P&L — dollars first

| window | agent 6 (info) | agent 60 | combined | n trips | fees |
|---|---|---|---|---|---|
| **KST 11-22** (11-21T15Z→11-22T15Z) | **0.00** | **0.00** | **0.00** | 0 | 0 |
| 24 h (11-21T15:13Z→11-22T15:13Z) | 0.00 | 0.00 | 0.00 | 0 | 0 |
| without the largest contributor | n/a (n = 0) | | | | |
| open uPNL | 0 (no positions) | 0 | 0 | | |

- **Four routes, all $0:** (1) `run_events` `trade` since 11-21T15:00Z = **0** rows, and there are no run_events of any type in the window.
  `MAX(ts)` is still 11-21T04:06:37Z. (2) Agent 6 cash is 9,998.76829614, the same as at the 11-21 sweep. Agent 60 cash is 10,000.00.
  (3) `signals` for agents 6 and 60 in the window = 0 rows. (4) Σ `trading_runs.realized_pnl_usd`: agent 6 = −1.2319 (same as 11-21, so the
  delta is 0) and agent 60 = 0. `pnl_audit --since 2026-11-20` exits 0, has no 11-22 line, and the 11-20/11-21 lines are unchanged.
- **Verdict: a $0 day, and it is the second $0 day in a row. That is not a result. The book has not traded for 35 h** (the last fill
  was 11-21T04:04Z). A zero is neither profit nor evidence. No edge reading is possible at n = 0.

### 2. Per-trade reasons (Agent A / Agent B)

- **Not dispatched, n = 0.** The two-subagent rule applies to "every monitoring cycle/sweep **with tape to analyze**". The window has
  no AI-authored outcome and no algorithm-authored outcome. Two agents would each have reported an empty set. I am stating this rather
  than staging a ritual.

### 3. Experiments (hypothesis → falsifier → result)

**E1. "Long-only can build a long today" (R44 premise, reading 3).** Falsifier: zero buildable long theses.
- DATA (ISO-literal window): 15 research batches in 24 h, about every 90 min, **not hourly**. Every batch has exactly **1 long, GLD
  (us-stock)**, and 17–27 shorts. Totals: 195 us-stock shorts, 200 crypto shorts, 15 longs (all GLD). The last crypto long thesis was
  11-19T23:53:34Z.
- Gate, re-run read-only in a fresh worker process: `backtest_gate.symbol_expectancy('GLD','us-stock')` gives **−727.53 USD/trade over
  6 trades, win 0.167**, so it is `eligible: False`. That is the same figure as 11-21, which fits: no new us-stock session since Friday's bar.
- **Falsifier MET for the 3rd straight reading.** It is Sunday, so us-stock is closed, but the gate refuses GLD regardless. **R44 stays
  STAGED with $0 value.**

**E2. Long-exit policy (5d48cf3), day-2 reading of its pre-registered falsifier.**
- Open automation longs: **0**. Any positive-quantity position on the platform: **0**. Emergency fires, target fires, refused AI sells: 0.
- (a) realized + unrealized since the deploy = $0.00. (b) underwater longs 0 of 0.
- **NOT YET MEASURABLE.** This is the 2nd day with n = 0.

**Killed / not re-run:** none new. Yesterday's kills stand (archetype-short-blocks-longs, planner-tick-counters-prove-stall).

### 4. Three-axis verification

- **DATA:** $0 by four independent routes (§1). The research direction counts were re-queried with an ISO `'…T…Z'` literal. A first
  pass compared the varchar `created_at` to `DATE_SUB(UTC_TIMESTAMP(), …)`. It returned the same counts here, but that form is the known
  comparison trap and was not relied on.
- **CODE (running image):** `futures_blocked()` True, `shorts_blocked()` True, `LONG_EXIT_POLICY` unset (so the default is on). The GLD
  gate verdict was computed by the image's own `backtest_gate`.
- **ADVERSARY:**
  - "$0 means the risk rules are working": rejected as a P&L claim. Zero exposure cannot lose, and it cannot earn either.
  - "The worker is dead because MAX(ts) is 35 h old": rejected. Fleet 54 writes `fleet_status` every 30 min (last 14:58:58Z), research
    batches keep landing (last 14:26:59Z), logs show 0 Traceback/ERROR, and 87 local-tier decision LLM calls were logged.
  - "Loosen the gate or the research direction to get trading": rejected on the standing evidence. Dip longs did worse than random
    (11-19), six replications show no entry edge, and GLD's replay is −727.53 per trade.

### 5. Re-verification ledger (since the 11-21 sweep)

| item | evidence on prod now | verdict |
|---|---|---|
| sweep-20261121 deploy (notes image, 2bb2992) | `.env` and both containers on `20261121-sweep-20261121`, up 19 h | **HELD** |
| long-only + long-exit policy (5d48cf3) | `shorts_blocked()` True, 0 shorts opened, 0 longs opened | HELD in code; **never exercised** (n = 0, day 2) |
| WATCH: fleet 54 0 builds by 11-24T15:00Z → tell owner day-7 (11-27) has n = 0 | 0 builds so far; Mon 11-23 us-stock session not yet happened | **NOT YET MEASURABLE**, still on track to trigger |
| R44 long-only research | E1: falsifier met (reading 3) | STAGED, $0 value |
| R45 rebuild after profitable stop | no trips | SOFT, not measurable |
| R37b / R32 / R42 / R43 / R40 / R34 | no trips | unchanged (moot until a book exists) |
| 11-21 trap: deploy retires flat runs as `no_prospect_switched` | no deploy and no runs in the window | n/a |
| agent 60 | fleets 42/43 `stopped` (`fleet_stop_all`), no runs | OPEN (owner) |

### 6. Health

| check | value |
|---|---|
| containers | worker and backend on `20261121-sweep-20261121`, up 19 h. admin up. mysql healthy |
| `MAX(run_events.ts)` | 11-21T04:06:37Z. That is correct for 0 runs. Fleet heartbeat 14:58:58Z |
| Traceback / ERROR (24 h) | worker **0** (11,775 lines), backend **0** (29 lines) |
| local LLM | **176** `LLM generation failed (provider=local): Request timed out` warnings in 24 h. Research batch cadence is about 90 min (15 per day), and one batch (09Z) had only 18 theses instead of 28. No money effect while nothing trades. Not chased |
| fleet 54 | `active`, `replenishing:0/6`. Last `slot_waiting` was 11-21T03:05Z |
| llm_silence | not applicable (no run decisions to judge) |

### 7. Today's solution

- **There was no loss today, so the losing shape is the zero itself.** The platform is now: crypto research is 100 % short because
  direction comes from 5-day momentum in a down-tape, shorts are refused, and the only long (GLD) fails the expectancy gate. **That
  combination cannot trade.** It is the owner's rule working as written. It is not a defect to patch.
- **No change ships.** Every lever that would "make it trade" is a guess that the standing evidence contradicts: loosening the gate,
  overriding the direction, or adding dip longs. AI-first is moot, because the desk is never called: there are no runs to decide on.
- **What is watched, and the trigger:** the existing watch fires at **2026-11-24T15:00Z**, after Monday's us-stock session. If fleet 54
  has still built 0 runs, the next sweep tells the owner plainly that the long-exit-policy day-7 checkpoint (11-27) has **n = 0**. Its
  verdict must then read **NOT MEASURABLE**, never "not refuted". Today adds one fact for that conversation: the crypto side has produced
  **0 long theses since 11-19T23:53Z**, so only us-stock can supply a long, and only one that passes `backtest_gate`.

### 8. Not verified

- Why the research cadence is about 90 min rather than hourly, and whether the 176 local-LLM timeouts cause it. This was not chased
  because there is no money effect at zero exposure.
- Agent 63's short uPNL (out of scope; stored `current_price` may be stale).
- Monday's us-stock research. GLD's gate figure will change only after a new session bar.
