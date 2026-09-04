# 2026-09-04 — Hold-wall fix (zero trades + slot starvation)

**Shipped:** c59730c4 → prod `sooppiy-backend:20260904-hold-wall-fix` (01:08Z).
Owner report: "never trading; slots defined 8 but always 3." Both true.

## Root causes (measured, not guessed)

1. **Hold-wall.** 100% of 1,076 decisions since 08-31 were `hold` (last buy
   decision 08-29 03:55; two-week buy rate ≈0.1%). The desk's own reports
   cited the rail: `max_loss_usd = 2% × max_bet` gave a $6.45 loss budget on
   a $1,074 slot; the 0.70 retire brake left **$4.51 of room — below one
   ordinary day of noise (±1.4–3.6%) at size**. Verified three ways: tier
   code (`fleet_planner.FLEET_BOUNDS`) ↔ DB `stop_conditions_json` ↔ the
   desk's quoted dollar figures matched exactly.
2. **Cooldown starvation.** Each no-prospect switch benched its symbol 12h;
   ~18 concurrent benches (agent 6) collapsed `select_targets` to one
   candidate, which the backtest expectancy gate rejected forever
   (`kept: []` every ~5 min). Fleet 43 additionally had an unreachable
   target: the 08-31 reading of hot-5-MUST dropped every non-tech us-stock
   name, leaving a 5-name universe under an 8-slot fleet.

**Dead hypotheses (named so nobody re-runs them):** the 09-02 three-agent
ship (drought predates it); a provider/model switch (gpt-oss:120b authored
every decision since ≥08-20); stale marks; the `FleetPlanner researched:0
built:0` log line (those counters only apply to researching/building
fleets — normal for active ones).

## Fixes

1. `stop_loss_frac_of_bet` re-tiered 0.015/0.02/0.03/0.04 →
   **0.03/0.05/0.07/0.10** (brake room 2.1–7% of the bet; risk per run
   0.6–7% of the slot).
2. Symbol cooldowns capped at **8 per market** in selection — only
   vary-class benches (idle / no-prospect / desk-refusal, classified via
   `source_run_id → trading_runs.status_reason`) are releasable, oldest
   first; loss, adapt/liquidation and NULL-source benches always exclude.
3. Hot-5-MUST re-read per owner clarification 2026-09-04 ("not limit 5 usa
   stock … ex slot 10 then 5 must be tech stock, and then other 5"):
   `_hot_tech_first_us_stock` reorders (top-5 hot tech lead, everything
   else kept below) and `select_targets` **forces** the tech lead for a
   us-stock-only pool. Roster += ASTS, IONQ, OKLO, RKLB, SMR, SPCX.

Verification: 11-test regression file (`tests/test_hold_wall_fixes.py`,
fail-before/pass-after + mutation-checked), two independent subagents
(adversarial reviewer ×2 rounds — found the loss-bench release and the
stale us-stock cap; independent verifier ×2 rounds — caught the untested
forced-lead branch), full suite 5,029 ×2 (worktree + clean clone), local
CI 6/6 jobs green.

## Post-deploy (01:12Z, ~3 min after restart)

- Fleet 44: **8/8 full** (was 3/8 for days) — 5 rotations in one pass,
  `status_reason` cleared.
- Fleet 43: **3/8 and building** (was 0/8) — DE, COP, CVX (non-tech now
  eligible as designed; benched tech rejoins as cooldowns expire).
- New runs carry the widened budgets exactly: BTCUSDT `max_loss 18.75`
  (5% × $375 bet; was 7.50), DE/COP show probation-scaled extreme-tier
  math (16.08 / 45.12 = 10% × scaled bet).

## Follow-up ship (same session): hourly no-prospect switch

Owner order ("Desk analysis each a hour not 3 hours"), confirmed to mean
the switch window: 67df333a → prod `20260904-one-hour-switch` (~02:56Z).
`RUN_NO_PROSPECT_SWITCH_HOURS` 3→1, min decisions 3→2, plus the guard
both verification agents found independently: the light-cycle
"no LLM verdict" scaffold journals `action: hold` and counted toward the
switch — an LLM brownout would have rotated and 12h-benched every flat
slot hourly. Scaffolds now reset the streak (test-pinned, mutation-checked).
Observed live at 02:57Z: all 8 crypto slots switched in lockstep on 4 real
desk holds each (guard confirmed live — reports present), replenishment
rebuilt immediately. Swing fleet 43 exempt from this rail as designed.

## Falsifier interim (03:0xZ, 27/50 decisions on new-rail runs)

0 buys yet — but the hold CHARACTER changed: confidence mode moved to 0.6
(one 0.8) from the old sub-0.56 wall, and sampled reasons are market
calls (F&G 74 greed, crowded longs, fragile rebound off a downtrend) not
rail-impossibility. F&G 74 sits in the caution regime band, so a
hold-heavy tape is at least consistent right now. Verdict stays OPEN
until 50 decisions; if the buy rate is still ≤ baseline then, report
FAILED per the rule below.

## Falsifier v1: FAILED as registered (2026-09-04 ~03:45Z)

The original registration — "first 50 post-deploy decisions must beat the
0.1% buy-rate baseline, else FAILED and revert" — triggered: **52
decisions, 0 buy/short.** Reported plainly, no reframing. The slot-refill
half passed (44: 8/8, 43: 0→4/8, zero starvation loops). Confounds named
by the 5-agent verification: the US market was closed for the entire
window (fleet 43's swing desk cannot enter off-session by design) and
crypto sat in an F&G-74 caution regime; hold reasons shifted from
rail-impossibility to market judgment and confidence rose (mode 0.4→0.6).

**Owner decision (2026-09-04): keep the tiers, re-register (option B).**

## Falsifier v2 (re-registered — same revert consequence)

By **2026-09-05 04:00Z** (24h wall-clock spanning at least one full US
session 13:30–20:00Z and a full crypto day): the desk must author **≥1
buy/short decision** on any fleet run (executed or gate-demoted both count
as "authored"). If not: report FAILED again and revert
`stop_loss_frac_of_bet` to 0.015/0.02/0.03/0.04 without further debate.
P&L verdict still comes only after closed trades exist.

## 5-agent verification (2026-09-04, owner-ordered)

Five independent agents (logic ×17k property trials / risk rails / MySQL+
concurrency / test-mutation 9-of-9 killed / live prod read-only): **5/5
VERIFIED, zero blockers.** Follow-ups it produced: the rule-hold guard
(shipped next, below), a watch on one unexplained 1-in-21 flake of
`test_tech_lead_survives_directional_balance`, expired-cooldown-row purge
(backlog), and two deliberate-design notices for the owner — the fleet
warn/stop rails re-arm daily via budget compounding (extreme tier can now
reach the −30% day-pause in ~4 correlated full-fleet stop-out rounds of
~$700), and the forced hot-5 lead bypasses the directional-balance brake
(a 7-long/1-short us-stock book is possible).

## Follow-up ship: rule-hold guard (full-path outage twin)

Verifier 1 found the scaffold guard covers only the LIGHT path: a
full-pipeline LLM failure journals a rule-engine hold
(`decided_by="rule"`, ordinary report) that still counted toward the
switch. Shipped: the decision emit now journals `decided_by`/
`fallback_reason` (they previously never reached the tape — rule holds
were indistinguishable from desk holds), and `_flat_hold_span` breaks the
streak on `decided_by == "rule"`, twin of the scaffold guard.

---

# JOINT FALSIFIER — panel context + crypto geometry (registered 2026-09-04, BEFORE deploy)

Owner decision: ship both in one deploy. Registered up front, as required,
that **this first window tests BOTH changes together and cannot attribute
between them.** Saying so before the data arrives is the point; a window read
after the fact would be a story, not an experiment.

## What ships together

| change | from | to | kill switch |
|---|---|---|---|
| panel is told the motion it is reviewing | blind re-decision | `proposal_context` in the trader prompt | `PANEL_PROPOSAL_CONTEXT=0` |
| crypto stop cap | 0.5% | 2.5% | `STOP_CAP_PCT_CRYPTO` |
| crypto target cap | 0.3% | 5.0% | `TARGET_PSYCH_CAP_MAP` |

Coupled values deliberately left alone: `RR_FLOOR=0.2` (no longer binding
under 2.5/5.0 — it permits a 0.5% target against a 2.5% stop, so it must
be revisited if the geometry stays) and `RUN_ENTRY_MARK_DRIFT_CAP_PCT=0.5`
(must remain <= the stop cap; 0.5 <= 2.5 is the safe direction).

## What this window overrides, stated plainly

- **Plan 31 D7** registered the next stop-cap window at **0.3%** (narrower).
  This ships 2.5% — 5x the opposite direction. Justification: F31-GEOM's own
  fail condition (">2 geometry-citing retires in 300 decisions") measured
  **215/300**, and its 50-trip requirement measured **0 trips**. The
  sequential-window design is unexecutable because the current window
  produces no data at all. That is a deviation from a registered plan and
  is recorded as one, not smuggled.
- **Plan 30 F-TARGET-CAP** (target-exit share >= 30% over the first 30
  fills) is retired **unfired**: it never reached 30 fills. Reported as
  UNRESOLVED-BY-ZERO-DATA rather than passed or failed.

## The falsifier

**Window 1 (joint), first 50 approved-and-executed crypto entries or 7 days:**

- **PASS** requires BOTH: entries actually occur (the ~0.2% baseline is
  beaten), AND realized expectancy >= 0 net of fees, reported WITH and
  WITHOUT the largest single contributor. If stripping the largest
  contributor flips the sign, the window is INCONCLUSIVE, not a pass.
- **FAIL** on either: expectancy < 0 at n>=50, or a catastrophic early
  reading (expectancy worse than -0.5R, or >=80% panel approval with a
  negative mean) at n>=20.
- **Discrimination check, independent of P&L:** panel approval rate must
  stay well below 100%. A panel approving ~everything has stopped
  reviewing and is rubber-stamping — that fails regardless of expectancy.

**Attribution is deferred, not abandoned.** Because both changes ship at
once, Window 1 cannot say which one moved the number. Both carry
independent kill switches, so Window 2 resolves it:

- If Window 1 FAILS -> set `PANEL_PROPOSAL_CONTEXT=0`, keep the geometry,
  run Window 2. Entries persisting and still losing => the geometry is the
  problem. Entries collapsing back toward zero => the panel context was
  the driver of entry rate and the geometry alone cannot lift it.
- If Window 1 PASSES -> attribution is still owed before either value is
  treated as settled. Run Window 2 the same way to measure the geometry
  alone, or accept explicitly that the pair is being kept as a package.

**Control that tests the anchoring hypothesis directly:** compare realized
expectancy of panel-APPROVED entries against the proposals the panel
REJECTED over the same window (paper-tracked). If both cohorts perform
alike, the context added anchoring rather than information ->
`PANEL_PROPOSAL_CONTEXT=0`, report FAILED in these terms.

Switch timestamp is the container recreation time recorded at deploy; every
`order_discussion` event now carries `proposal_context_chars`, so meetings
before and after the switch are separable on the tape.
