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

## Open falsifier (pre-registered — judge the fix by this)

Over the **first 50 post-deploy decisions**: buy/short rate must exceed the
0.1% two-week baseline AND slots must stay replenished. If the desk still
holds 100% with the honest rail in place, the tier change FAILED — report
it as failed in these terms and revert `stop_loss_frac_of_bet`. Second
watch: with real stops now reachable, loss benches must engage (repeated
same-symbol losses would indict the cap ordering, though loss benches are
protected by design). P&L verdict comes only after closed trades exist.
