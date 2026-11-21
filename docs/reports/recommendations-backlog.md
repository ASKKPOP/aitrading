# Sooppiy Automation — Recommendations Backlog

Living doc, appended each 30-min monitoring cycle. Companion to `2026-07-31-automation-monitoring.md`.

**Operating model (owner-set, clarified cycle 3):**
1. **Default mode = monitoring.** Observe prod every 30 min; make no premature changes.
2. **A change is made only when monitoring proves it required.** When it is, it is implemented **on sooppiy.com (prod)**: code → test (fail-before/pass-after) → local ruff+pytest+tsc green → build → **deploy to prod**. Never a local/session-only edit that stops short of prod.
3. **Then keep monitoring** to confirm the deployed change works on prod (or roll back).
4. **Purpose:** extend and fix sooppiy.com trading so it makes profit.

This backlog accrues candidates. Items ship to prod one at a time, verified, only once live evidence makes them clearly required — shipping a thinly-evidenced *trading* change every 30 min would destabilize a live book. Local files under `docs/reports/` are monitoring notes only, never the deliverable.

---

## Status legend
`SHIPPED` · `HARD-READY` (verified, implementing next cycle) · `STAGED` (accruing evidence) · `SOFT` (backlog) · `DROPPED`

---

## Items

### R45 — Fleet rebuilds a symbol seconds after a PROFITABLE stop (vary-on-loss gates on realized<0 only) · **SOFT (2026-11-21 sweep, inconclusive)**
- 11-21: TRUMP 231104 rebuilt 19 s after 231100 (+0.14 lock) → SL −1.07; STRK 231106 rebuilt 46 s after 231098 (+0.12) → SL −1.62. Code: `fleet_supervisor.py:833-845` benches only `stop_event:` closes with realized < 0.
- History replay (fleet runs 10-20→11-21, agents 6/60, ≤300 s after a profitable stop): rebuilds n=205 Σ −10.84 (mean −0.053, ex-largest −7.70) vs control n=319 Σ −2.82 (mean −0.009); **permutation p=0.145 one-sided**, medians +6.1 vs +5.0 bp; 3 worst rebuilds = −8.5 → tail-driven, NOT significant. All short-era; the book is now long-only (a profitable "stop" = the +5 % target).
- *Promote only if* a long-only reading shows rebuilds below control at p < 0.05 AND the sign holds ex-largest. *Ship form:* short cooldown after any stop_event close, platform code (selection — the desk is not the actor).

### R44 — Research ranks directions the platform may not trade; under the long-only block no fleet can build in a downtrend · **STAGED (2026-11-20 sweep, measurement owed)**
- 11-20: `symbol_research.py:922` labels direction by the sign of mom_5d, and the batch keeps the top 8 per market by |score|. `select_targets` then refuses every short (`futures_policy.thesis_refusal`). Batches 498653–498662 (05:21–14:09Z) carried **0 longs**: 8 crypto shorts that were refused, plus 8 us-stock shorts with `selectable=0`. Fleets 51 and 52 ended `build_failed` (20× `research_empty`). The only long since (SLV, 15:13Z) fails `backtest_gate` (−469 USD/trade, n=5). 29/29 major coins had mom_5d < 0 at 06:23Z, so crypto has no long by construction.
- *Hypothesis:* unselectable shorts crowd tradeable us-stock longs out of the top-8. *Measure first:* replay the screen read-only over today's batches and count us-stock symbols with mom_5d ≥ 0 above the liquidity floor, then whether any passes `backtest_gate`. *Falsifier:* zero such symbols, or all fail the gate. Then the fix only saves thesis LLM compute (local, ~$0) and builds nothing.
- *Ship form (platform code; the desk is not the actor in research):* when `futures_blocked()`, rank only long-direction candidates per market. *Counterfactual P&L:* not computable (never traded); prior evidence says such longs carry no entry edge (11-19 buy-low research; 5 replications). Do NOT loosen `backtest_gate` to "get trading".
- **11-21 reading 2 (falsifier MET for the day):** 16 hourly batches since 03:00Z each hold exactly 1 long — GLD (us-stock); 0 crypto longs in 24 h (last 11-19T23Z). Read-only `select_targets(54)`: open-markets scope (Sat: crypto+polymarket) → `[]`; unscoped → GLD, dropped by `backtest_gate` (−727.53 USD/trade, n=6). The ship form would have built nothing. Still STAGED; P&L value of the fix is $0 on both readings.

### R37b — Ratchet arms on a single-sample spike · **SOFT (2026-11-20 sweep, n=9 of 37 fires)**
- 9/37 fires had prior mark < arm, one mark set the peak, and the next ~62 s mark was already under the floor. They netted +0.035 and contained 4 of the 6 ratchet losers (Σ −0.10). Candidate: require two consecutive samples ≥ arm. *Measure first:* the counterfactual over every R37 reading window (it also delays winners). *Falsifier:* Σ ≤ 0 or sign flips ex-largest.

### R43 — Chair amends a trader's stated close to `hold` after the desk's own invalidation printed · **STAGED (2026-11-19 sweep, n=9, measurement owed)**
- 11-19: 9 cycles where final = `hold` while the trader's `order_params.why` said close/cut/reduce (trader verb `buy` in 4, `sell` — R40 ambiguity — in 5). INJ 229944 07:50Z: trader `sell` 0.80 "Stop breach invalidates short; close now." → chair `hold` 0.32 → stopped −0.82 (≈ +0.46 had it closed). Full-close intents n=5 counterfactual **+0.63, +0.17 ex-INJ**. INJ+HYPE+LTC −2.13.
- Opposite reading: 11-17 E1, chair `sell` over a trader cover on a held short, n=32 since 10-01 → covering would have LOST 4.83. Hypothesis that reconciles both: the chair's hold is right in general but wrong once the desk's OWN printed invalidation has crossed.
- *Measure first:* every chair close→hold amendment since 10-01, split by invalidation-crossed; counterfactual close at the decision mark. *Falsifier:* Σ ≤ 0 on the crossed subset, sign flips ex-largest, or n < 15. *Ship form (AI-first):* one chair skill line (needs a catalogue prune + two reviewers), merged with R42's line if both hold.

### R42 — Desk discretionary partial covers destroy money (encode L-1118) · **STAGED (2026-11-18 sweep, 2 readings)**
- **11-19 CORRECTION:** L-1118 was never shown to the desk — monitoring notes are a recall fallback only (HANDOFF §10, 11-19). The 7-day "did the RAG lesson work" falsifier is VOID. H-CUT continues as an observation: post-18:17Z day 1 n=2, Σ(hold − cut) −0.14. Ship path = a skill line, possibly merged with R43.
- E1 (11-18): every agent-6 desk `cyc:` partial cover since 10-01 vs holding the cut size to the trip's own later exits: **n=47, Σ +4.85** (+3.40 ex-largest; Oct +3.72 / Nov +1.13); underwater n=33 +3.03 (+1.58 ex-largest). By COUNT 23/47 — magnitude rule, not frequency. Reading 2 (11-17 E2): blocked reduces, if executed, −2.70 (n=26).
- AI-first step taken: lesson L-1118 written into `2026-11-18-automation-monitoring.md` §7 (RAG corpus on deploy). *Promote* to one decision-prompt line (needs a catalogue prune + two reviewers) only if over the next 7 days desk partials continue at ≥ the baseline rate (47/49 days) AND Σ(hold − cut) > 0. *Kill* H-CUT if Σ(hold − cut) ≤ 0 over those 7 days.
- Trap: rebuild trips with a relative tolerance (|pos| ≤ 1e-5 × trip qty) — fill quantities carry ~2e-8 residue.

### R41 — Breakeven ratchet is blind after a losing partial cover · **STAGED (2026-11-17 sweep, n=1)**
- **11-18:** n=1 more (FIL 226601) AGAINST: blindness worth +0.86 (desk cover + TP beat a position-anchored fire). Tally +1.5 / −0.86 → inconclusive; do not ship.
- `_ratchet_peak_pnl` advances `peak_pnl_usd` only when the run TOTAL beats it while holding (re-anchors only when flat). TRUMP 217302: peak ≈ −0.08 at open; after the desk's losing covers the total sat at −1.38 + uPNL, so the remainder's own +0.37 excursion (10:58Z, arm ≈ 0.30) could not arm the lock. Counterfactual ≈ +1.5 (n=1). R21 (run 1417) is the opposite failure of the opposite anchor — do not flip blindly.
- *Measure first:* every run since 10-01 with a losing partial whose remainder later exceeded the arm; counterfactual P&L of a position-anchored peak. *Falsifier:* Σ < 0 or n < 5.

### R40 — Chair is not told that `sell` ADDS to a short · **STAGED, do-not-ship on P&L (2026-11-17 sweep, n=30)**
- `_three_agent_light_discussion` shows the chair `position N (negative = short)` + `Allowed actions: buy|hold|sell` but not the trader's inventory rule. Since 10-01: 30 `order_params` with `sell` on a held short whose own `why` says close/reduce/cut; 22 blocked `add_limit`, **1 executed as an ADD** (11-05 run 123737).
- Counterfactual of executing the stated reduce at the live marks: **n=26, Σ −2.70** (−0.92 ex-largest; Oct −1.41, Nov −1.30). The mis-send has been P&L-positive, so the fix is not shipped. **Promote** (one chair prompt line, wiring test) on the next instance of a stated reduce executed as an add — that is a risk event, not a P&L bet.
- Related kill (E1, same sweep): chair `sell` overriding a trader's cover on a held short, n=32 since 10-01 — covering would have lost 4.83. Not a money defect.

### R37 — Breakeven-ratchet step-through: fills land below the lock on 60–75 s mark samples · **STAGED (3 readings: 11-11, 11-13/14, 11-17)**
- **11-19 (5th reading):** 1.26 over 58 fires = **$0.022/fire** (0.027, 0.019, 0.028, 0.022) → "worsening" REFUTED; stable ≈ $1.2–1.9/day, 64 % of the ratchet's net; zero execution slippage (53/53).
- **11-18 (4th reading, worse):** Σ(floor − fill) **$1.90 over 67 fires** ($0.028/fire vs 0.019), fill = fire-time mark 67/67 (all sampling); 6 fires below zero gross (Σ −0.447). Largest algorithmic leak (≈55 % of the ratchet's +3.50).
- 11-17: n=36 ratchet closes, Σ(floor − fill gross) **0.70**, 9 net-negative (Σ −0.165), sampling ≈ 62 s with 190–220 s gaps.
- 11-13/14 (n = 26 ratchet closes): Σ(intended floor − fill) = **0.706** = 65 % of the window's +1.09 net; all 6 losers lost to it (ENA 169724 −0.096: peak +0.144 → next sample −0.062). 11-11: 9 net-negative ratchet exits, same mechanism. Platform-only (the desk cannot act in 60 s).
- *Hypothesis:* sampling marks for ratchet-armed positions at ≤ 15 s recovers ≥ 50 % of step-through. Fills must stay at the first sampled price past the floor (never at the floor — that fakes fills). *Falsifier:* a 15 s replay on the 11-11 + 11-13 tapes recovers < 0.3. *Upper-bound counterfactual (exact floor):* +0.71 for this window. Design first (sampler cost, live parity).

### R38 — Desk opens inside the last hour of a run whose horizon is far longer · **SOFT (2026-11-16, n=1)**
- AAVE 169927 shorted 21:33:23Z, 72 h horizon, at_time 22:35:47Z; `_run_expiry_line` was in the brief. Lesson (run-expiry skill, after a prune): "If the run ends before your stated horizon, do not open; hold and let the successor decide." *Measure first:* all entries since 10-01 with run-life < horizon vs > 6 h, net per $ notional. *Falsifier:* short-life entries net ≥ long-life ones.

### R39 — Entitlement denial is retried on every candidate, every tick, forever · **STAGED (2026-11-16 sweep)**
- Fleet 43 (user 25, subscription ended 11-12T22:07Z): 11.8k–17.6k `candidate_skipped`/day + ~2k `backtest_gate`/day; 279,951 fleet_events rows; ~39.5k burned `trading_runs` ids (13 surviving rows in 169928–209416); 1 leaked draft (169250). Code: `fleet_supervisor._build_replacement` generic `except` → `candidate_skipped`, cooldown only for "outside any run".
- Fix: a user-level EntitlementDenied (no subscription / concurrency) breaks the candidate loop and backs off ≥ 30 min; check entitlement BEFORE `create_run`. $0 money path, changes fleet build flow → full gate + two reviewers. *Metric:* fleet 43 `candidate_skipped`/day → ≤ 50. *Falsifier:* a per-candidate deny (max_bet) wrongly blocking a buildable candidate in tests.

### R34 — Desk sizes up at its LOWEST confidence · **STAGED (2026-11-11 daily sweep, n=3)**
- **11-18:** 6 entries at size_frac ≥ 0.3 / conf < 0.7, all won (+2.31, +1.27 ex-ASTER); 7-day n=11 Σ −2.15; cap-0.1 counterfactual ≈ +1.4 total but −0.8 without TRUMP → inconclusive. Confidence carried no outcome information (conf<0.6 out-earned conf≥0.65). **Weakened.**
- 11-17 sweep: +1 (TRUMP 217302 size_frac 0.50 at conf 0.55, $187, **−2.74**) → **n=5, Σ −4.46**; corr(conf, notional) −0.06. Counterfactual cap 0.1 unless conf ≥ 0.7: +2.19 today, ≈ +3.26 over the 5 (+1.07 ex-largest).
- 11-16 sweep: +1 (AAVE 169219 size_frac 0.40 at conf 0.55, +0.393 on a trending tape) → n=4, Σ −1.72; corr(conf, notional) −0.15.
- 11-11: the three size_frac 0.3–0.4 entries (NEAR 151814 $103.8, UNI 152355 $112.8, TRUMP 153039 $124.5) came at chair confidence 0.55–0.6; net −2.11 (without NEAR +0.65). Agents A/B, both days: size does not track confidence.
- Counterfactual at the live mark, cap 0.1 unless conf ≥ 0.7: +1.37 today. **Falsifier:** over 7 days the ≥0.3 entries net ≥ the 0.05–0.1 entries per $ notional. **Promote** (desk sizing skill line, after a catalogue prune) at ≥10 such entries in 7 days with the counterfactual positive with and without the largest.

### R35 — Chair re-enters against the desk's own invalidation · **STAGED, near-ready (2026-11-11, class (c) n=5, all losers)**
- 151814b NEAR: desk outlook 23:41Z "short plan invalidated"; trader proposed BUY 0.65; chair overrode to SELL 0.62 at 3.6435 → −0.379. HANDOFF §8 class (c) was n=4, all losers.
- Lesson (chair skill): "If the desk's own outlook declared the plan invalidated, do not override a reversing trader back into the invalidated direction; hold." **Falsifier:** a class-(c) re-entry that wins. Ship in a run with review budget + catalogue prune (chair prompt = money path).

### R36 — A handed-off position's stop loss is in no run's realized_pnl_usd · **STAGED (2026-11-11)**
- FIL 151804 / BTC 151825 runs show realized −0.008 / −0.020 (entry fee only); their orphan stop closes (−0.47 / −0.49) have run_id NULL. Monitoring side fixed (pnl_audit `orphan`/`all_in`, 2026-11-11). User-visible side (run P&L, agent cash reconciliation) not verified — design first.

### R32 — Breakeven-ratchet arm vs the desk's own bracket · **STAGED → FROZEN 2026-11-20 (book is long-only now; short-book tally k=3 Σ +12.08 over 6 calibrated days does not transfer; re-open after ≥3 calibrated long-only days)**
- **Day 4 (11-17T15Z→11-18T18Z):** n=63, calib median 0.0053 (passes); Δ k=2 +3.96, k=3 +5.69, none +33.97 — falling tape, for. Calibrated tally k=3: +4.06, +2.29, −3.96, +5.69 → ΣΔ +8.08 (+2.39 ex-largest), 3/4 positive, 4/10 days, 0/3 non-trending. STAGED.
- **Evidence:** 11-10: 51/57 agent-6 exits were `breakeven_ratchet` (+1.26 net, fees 52.5 % of gross, median capture 0.154 %), while the desk's 3 trail exits made +1.12; the desk's last verdict before every ratchet fire was sell/hold. Calibrated 1m replay today: Δ k=3 +4.06, k=5 +7.62, none +24.76.
- **Against:** 15m replays 09-20→10-01 (n=50, calib ok): Δ k=3 −13.91, k=5 −13.48; October (n=303, calib poor): Δ k=5 −25.25, none −24.57. Sign follows the tape (trend vs chop), not k. **H-ratchet-arm-too-low killed as a general rule.**
- **Next:** daily calibrated 1m replay via `research/ratchet_arm_replay.py` (HANDOFF §10, 11-10). **Promote** (propose `BREAKEVEN_ARM_FEES = 1.78 × k*` to the owner) only if, over ≥10 sweep-days with median calib error ≤ $0.01, ΣΔ(k*) > 0 with and without the largest day, positive on ≥7/10 days incl. ≥3 non-trending days (|ETH day| < 1.5 %). **Drop** if ΣΔ ≤ 0 over those 10 days.
- **Day 2 (11-11):** 1m replay n=25, every k>1 worse (k=3 −2.24, none −3.67); calib median 0.0116 just fails the ≤$0.01 bar → counts as an uncalibrated day, direction against.
- **Day 3 (11-13→11-16 window):** 1m replay n=26, calib median 0.004 (passes); Δ k=2 +1.17, k=3 +2.29, none +17.88 (ex-largest +15.54). ETH ≈ −2.5 % → **trending** day, for. Tally: 2/10 calibrated days, 0/3 non-trending. Stays STAGED.
- **Not a code ship:** the arm is a prod `.env` knob already set to 1.78 (owner's file; env overrides any code default).

### R33 — Desk stop width inside one hourly range · **SOFT (2026-11-10, n=1)**
- TRUMP 147516: desk stop 1.0 % vs 1.55 % mean 1 h range → −0.206 (= 16 median ratchet wins). Promote to a skill line when ≥5 watcher stops in a week sat inside their symbol's median hourly range and 2× the stop is better in counterfactual.


### R6 — Breakeven ratchet for the give-back leak · **DROPPED (cycle 6, backtested)**
- **Asked to build + verify off `main`. Built the counterfactual backtest first (28 closed runs, 10,644 recorded equity points, 7d, no lookahead). Verdict: do NOT ship.**
- **Numbers:** baseline realized −$57.60. Best arm threshold (0.15–0.25×max_loss) nets **+$5.00 only** — save 3 give-back runs (+$26) minus **one clipped real winner, run 125 +$20.80→−0.18** (−$21). Outside that narrow band net is −$8 to −$31. Floor variations: no change.
- **Why it fails (reproduces the team's prior rejection):** a breakeven stop cannot distinguish a give-back that keeps falling from a winner that dips-then-runs without lookahead, so it scratches real winners (125 peaked +28.76 and closed +20.80 for real). Same reason `trail_activate_rr`/breakeven ratchet were rejected before (`run_engine.py:1776`, `FLEET_BOUNDS` note).
- **What actually loses the money (the redirect):** the top losers **112 (−$70), 104 (−$39), 113 (−$21) = −$130 combined NEVER went positive** — directional losses no exit-lock can help. The give-back is visually dramatic but tiny in dollars.
- **Also spotted:** run 112 realized −$70.13 against a −$66.6 `max_loss` stop — a **stop overshoot** (~$3.5 past the cap). Possible separate slippage/late-eval issue → see R7.
- Backtest script + raw output: `scratchpad/r6_backtest.py`; summary `docs/reports/r6-backtest-result.md`.

### R7 — Losses are dominated by directional losers, not exits · NEW (cycle 6) · **new lead**
- **Evidence:** 3 of the 28-run set's worst losers never went positive (peak ≤ $0.5) and account for −$130 of −$57.60... i.e. the winners partly offset. The lever that moves P&L is **entry/position-selection quality**, not exit-locking. Also the fee hurdle (R1) on the many small losers.
- **Direction (analysis, not yet a change):** measure whether entries that never go positive share a signature (confidence band, route=light, regime, thesis_alignment score) using the `decision` events — if so, that's a gate worth building. Plus revisit R1 fee gate. Also R7b: stop-overshoot on run 112.
- **Cycle 6 first pass (28 closed runs, entry-decision features by outcome):**
  - **`confidence` is ANTI-predictive** — losers 0.70/0.66 vs winners 0.60/0.60 (consistent across never-positive and realized-loss cuts). The gate keys on confidence (`gate_source: confidence`).
  - **`conviction` (0.47 win vs 0.24 loss) and `momentum_quality` (0.62 vs 0.52) ARE predictive.** `entry_quality` is not (slightly inverted). `thesis_alignment` mild.
  - **Hypothesis:** the gate is keyed on the wrong scalar. `RUN_CONF_V2` (conviction gate) is built but OFF (team measured r~0 earlier). My group-mean cut disagrees — worth re-measuring with a proper per-decision backtest (win-rate / expectancy by conviction & momentum deciles) before any flag flip. **n=28, group means — do NOT ship on this; backtest first (R6 discipline).**
- **Next analysis pass:** per-decision expectancy backtest of a conviction/momentum gate vs the confidence gate.
- **Cycle 8 — win-rate/expectancy by bucket (28 closed runs, sharper than cycle-6 means):**
  - **Confidence (gate var) is backwards:** conf<0.60 → 57% win / +$4.07 avg; conf 0.60–0.68 → 50% / −$6.34; **conf≥0.68 → 11% win / −$1.10.** The desk's most-confident entries are its worst.
  - **Conviction predicts EXPECTANCY (not win-rate):** conv<0.30 → 63% win but **−$10.94 avg** (wins pennies, loses dollars — the never-positive directional disasters sit here); conv≥0.45 → 32% win but **+$1.73 avg**.
  - **Lead recommendation:** a **conviction floor / down-size on entries** (block or shrink conv<~0.30) is the most promising lever — it targets the catastrophic-expectancy bucket, unlike the confidence gate which selects the wrong way.
  - **Caveats before any change:** n=28; the −$10.94 is outlier-dominated (112/104/113); conviction is sometimes None (compute_conviction returns None if any of 4 sub-scores absent → gate would need a missing-conviction rule). **Backtest required (R6 discipline): counterfactual of blocking conv<0.30 entries → P&L delta, and confirm the floor actually catches the disasters, not just correlates.**
- **Cycle 9 — conviction-floor backtest: FAILS (verdict).** Per-run counterfactual (28 runs, baseline −$57.60):
  - The cycle-8 signal was an artifact of **missing conviction**: 8 runs have conv=None, netting −$87.52, but that's 2 catastrophes (112 −$70, 104 −$39) + **5 winners** (+$21.6). The 20 runs WITH conviction net **+$29.92**.
  - **Conviction does NOT separate winners from losers where present:** winners avg 0.637 vs losers 0.600; loser 113 (−$20.9, conv 0.640) ≈ winner 119 (+$25.6, conv 0.642). A floor at 0.65 makes it WORSE (−$24.86, blocks the big winners 820/125/119).
  - **Both R6 (exit) and R7 (entry) clean gates fail on backtest** — the desk's catastrophic losses look statistically ordinary at entry.
- **R7' (the one surviving thread) — down-size entries with MISSING conviction.** The 2 catastrophes both have conviction=None (a sub-score absent → sizing falls back to the noisy confidence scalar, per code + memory). Not a predictive gate — **risk management on an incomplete read: cap size when compute_conviction is None**, capping the −$70 tail while keeping proportional upside on that bucket's winners. STILL n=8/2-outlier-driven — needs a size-cap counterfactual before shipping.

### R6-OLD-NOTES — original give-back root cause (kept for reference)
- **Evidence:** cycle 2 HYPE; cycle 4 three positions; cycle 5 KAITO peaked **+$10.98**, BTC +$2.99 — all banked ~nothing. **0 trailing-lock exit events in 24h.**
- **ROOT CAUSE (cycle 5, from `stop_conditions_json`):** the trail arms only when `peak_pnl ≥ activate_usd`, and `activate_usd` is set to **1× `max_loss_usd` (~$35–43)** for every fleet run. Actual fleet peaks are **$3–11 — 4–13× below the floor**, so the trail (`run_engine.py:760`) and the ratchet (`risk_engine.py:589`, gated on `1×trail`) **can never arm.** The winner-protection is structurally dead for the entire fleet. Matches memory `fleet-exit-logic-trailing-lock` + `trailing-lock-never-arms`.
- **Fix direction (must be backtested, off main):** a **breakeven ratchet** that arms at a threshold the fleet actually reaches — e.g. move stop→entry once `peak ≥ k × round-trip-fee` or a small fraction of `max_loss` — so a +$10 peak exits at ≥breakeven, not −$0.41. **NOT** naive lowering of `trail_activate_rr` (measured-and-rejected: full-life-peak replay lies via lookahead; too-low arm clips real winners at breakeven). Threshold must be chosen via backtest replay, not guessed.
- **Status:** root cause verified; fix requires a backtest to pick the arm threshold, then implement off `main` + test (peak-then-reverse exits ≥BE) + deploy. Awaiting owner go on building it. **No prod change this session.**

### R8 — The loss is position-SIZING, not signal · **STRONGEST FINDING (cycle 10)** · new lead
- **Scale test killed R7:** across ALL closed runs, conv_MISSING (11 runs) is net **+$56**, conv_present (81 runs) is net **−$521**. The 3 biggest catastrophes have NORMAL conviction: 83 (−$219, conv 0.57), 76 (−$160, 0.61), 62 (−$144, 0.63) = −$523 ≈ the whole lifetime loss. No entry signal (conf/conviction/missing) distinguishes them. **R6, R7, R7' all fail.**
- **Risk-cap counterfactual (65 runs, baseline −$464.54):** capping per-run `max_loss_usd` at $50 → −$61 (**Δ +$403**); at $100 → −$91 (+$373); at $200 → −$122 (+$343). Monotonic.
- **The tails are the same cohort:** worst 6 runs have max_loss **$1,299–$2,596**; best 6 ALSO have max_loss **$1,697–$2,241** (34 +$203, 65 +$195, 74 +$136). A few large-risk runs ARE the P&L, both directions, and that cohort is net-negative. Fleet cohort (max_loss ~$40) barely registers.
- **Lever:** a per-run `max_loss_usd` ceiling (risk cap). This is the most defensible finding of the session — risk management, not a predictive bet.
- **Honest caveats:** it's a risk/RETURN tradeoff, NOT free money — capping the −$219 tail also caps the +$203 wins proportionally; net gain holds only because the large-risk cohort was net-negative over this sample (~12 large runs, so still modest n). The real question is governance: **should a single run be allowed to risk $1,300–$2,600?** That's an owner policy call, not a pure optimization. Needs: confirm the large cohort is structurally (not just this-sample) net-negative before setting a ceiling.
- **Cycle 11 — historical vs current:** by risk band (all closed): small ≤$100 = 67 runs −$61 · mid = −$15 · **LARGE >$500 = 48 runs −$389 (83% of the loss)**. Large-risk runs span id 34→849, created **through today** — NOT purely legacy. **BUT last 3 days: 41 runs net +$9.42, max risk only $719** (vs historical $2,596). So risk sizing has ALREADY moderated and recent P&L is positive; the −$523 catastrophes are from the earlier high-risk period. **Conclusion: the acute problem (runs risking $2.6k) has largely self-corrected; the current system is ~break-even. A formal per-run max_loss ceiling (~$100–200) would lock in the improvement and prevent regression — modest incremental value now, not an emergency.**

### R6/R9(a) — RE-BACKTEST on larger sample: CONFIRMS DEAD (cycle 17)
- Re-ran R6 on 30 closed runs / 11,654 equity points (was 28), now including KAITO's ~$22 give-back. Baseline −$33.74. Best arm band (0.15–0.25) nets **−$35.76** (worse); clip cost GREW to $68.86 (vs $20.98) — more data = the ratchet clips MORE real winners. KAITO did not tip it positive. **R6 definitively rejected. R9(a) closed.**
- **Net across the whole session:** every signal/exit lever (R6, R7, R7', R9a, R9b) rejected on rigorous backtest/code check. **Only R8 (per-run risk sizing) survives, and it is self-correcting.** The desk's losses are normal directional/give-back moves indistinguishable at entry; there is no cheap gate. This is a mature, converged conclusion, not a to-do list.

### R9 — Add-into-loser on LONGS + fresh give-back case (cycle 15) · NEW · investigate
- **Live event:** KAITO run 859 went +0.57 → **−$10.94** in one cycle. Trace: peaked +$10.98 (c4–5), round-tripped (give-back), then at cyc14 it **BOUGHT 686 @ 1.0996** — adding to a long already below its ~1.13 entry (averaging into the fall) — then sold cyc16 @ 1.0819 when conviction collapsed (0.275, thesis 0.20; confidence 0.78 diverged).
- **Two threads:** (a) fresh large give-back ($22 peak→realized swing) — a data point that should be folded into a **re-run of the R6 backtest** (larger sample now; does the net still say "don't ship"?). (b) **possible add-into-loser gap on LONGS** — memory says PR#79 shipped "no adds into losers" and PR#118 fixed *short* adds being ungated; this LONG add into a falling position suggests the gate may not cover this case. **Check `add_limit`/add-into-loser gate for the long path.**
- **No change; both need a code/backtest pass.** Does NOT overturn R6 on one case — but it's the first live evidence that shifts the give-back cost estimate upward.
- **Cycle 16 — R9(b) add-into-loser gap: RESOLVED, not a bug.** Deployed `run_engine._add_limit_skip` (line 1986) does "Never average into a loser (2026-07-26)" — blocks adds when unrealized<0, cites run 112, and is active (7 add-skips/24h). KAITO's cyc14 add passed because the position wasn't underwater at that instant (effective entry < 1.0996); the loss came from the later fall, not a gate failure. R9(b) dropped. **Only R9(a) remains: re-run the R6 backtest with the larger now-closed sample (KAITO added a ~$22 give-back data point).**

### R1 — Fee hurdle is the dominant structural loss  · STAGED→verifying
- **Evidence (cycle 3):** 24h = 32 trades, **$15.58 fees** (~$0.49/trade). Terminal reasons show **no stop-loss/target exits** — losers are small positions retired/stopped while marginally red, i.e. the move never cleared round-trip fees (0.1%/side). Lifetime realized −$466 with gross-loss/gross-win 1.57×. Matches prior finding "fees were 74% of the week's loss".
- **Proposed:** per-market fee table (flat `TRADE_FEE_RATE` today) **and/or** a pre-trade min-edge gate that suppresses entries whose AI `target_pct` (net of round-trip fee) is below a floor. Memory notes per-market fees "NOT yet done" and that the flat fee makes ~33% of theses / 100% of forex untradeable.
- **Risk:** medium — changes which trades fire. Needs a test proving a below-fee-edge thesis is skipped and an above-edge one passes.
- **Next action:** read the current fee-edge gate (`RUN_FEE_EDGE_MULTIPLE`, fee-infeasible retire in `run_engine.py:809`) to see what's already enforced, then decide table vs gate.

### R2 — Oversized orders repeatedly blocked by symbol exposure cap · SOFT
- **Evidence:** run 831 proposed **$14k–$14.7k** buys against a **$10k** symbol cap across cycles 10–12 (even at `size_scale 0.41`) → 20+ `gate_skip` "exposure limit" in 24h, all wasted LLM cycles.
- **Proposed:** clamp order notional to the remaining cap headroom (trade $10k instead of rejecting), OR structural-retire a run that is capped N cycles running (analogous to idle_retire).
- **Risk:** low-medium. Concentrated on a few large runs; low $ impact but wastes analysis spend.

### R3 — "spot sell with no inventory → hold" wasted cycles · SOFT
- **Evidence:** 5× in 24h. Desk emits a spot `sell` with no position to sell → treated as hold, LLM cycle spent.
- **Proposed:** mask `sell` from the spot action set when inventory=0 (prompt-level or post-parse), so the desk doesn't propose impossible actions.
- **Risk:** low.

### R4 — how-it-works URL not wired · SOFT
- **Evidence:** `/docs/how-it-works` isn't a registered slug → authed falls back to Guide doc; new `docs/plan/18-*.html` unwired.
- **Proposed:** add a `how-it-works` slug + manifest group, or redirect to the correct existing slug.
- **Risk:** none (docs only).

### R5 — qty=0 zombie position (id 80) · SOFT
- **Evidence:** BTCUSDT long qty=0, agent 37, orphan (run_id NULL), ~5h. Harmless but untidy. Owner removed the SOL orphan (id 67); hasn't ruled on this one.
- **Proposed:** delete on owner confirm; separately, have orphan reclaim purge qty=0 rows automatically.
- **Risk:** none.

---

## Corrections log
- **Cycle 3:** Retracted cycle-1/2 headline "RUN AI read is not journaled." FALSE — `run_events` has 39,903 rows; my queries filtered on `created_at` but the column is `ts`, so they errored silently. Decisions ARE fully journaled (`decision` events with action/confidence/conviction/sub-scores; `order_params`; `order_intent`; `gate_skip`; `trade`; `equity`). The proposed "add journaling" hard-implement is void — it already exists.

### R-A — Exposure-feasibility clamp at fleet build · **SHIPPED (2026-08-01, PR #182, image 20260801-expogate)**
- Root cause: fleet 24 ($17k bets × 5×) sized $25–34k orders vs the $10k per-symbol cap → 100% risk blocks → idle-retire → build-parity rebuild = infinite churn (runs 903–906, two laps). Fix: `compose_run_settings` (the ONE builder both build paths share) clamps `max_bet` so max_bet × leverage ≤ the agent's `max_symbol_exposure_usd`; stop/trail scale to the clamped bet; cap 0 disables; limits-read failure fail-softs to the $10k default.
- Verified live twice on prod: fleet-24 shape → max_bet 2000 (fully deployable); fleet-25 shape untouched. 6 tests with genuine fail-before/pass-after.

### R-B — max_loss on the no-stop cash runs · **APPLIED (2026-08-01)**
- Desk (gpt-oss:120b) specified $40 (~4% of the $1k bet) for runs 912 ETH / 915 TSLA; applied to `stop_conditions_json`, shape validated through the deployed validator, effective immediately.

### R9 — Fleet AI auto-tune: entitlement clamp + scope decision · PARKED (2026-08-12, owner paused monitoring to build USA-stock modules)
- **Shipped LIVE:** PR #381, image `20260812-fleetautotune`. `fleet_auto_tune.py` rides the tick and sets each non-terminal fleet's slots = `recommended_max_slots(budget)` and goal = edge-derived (5–30%). Verified working on fleet 29 (agent 6): slots 6→10, goal 20%→5%.
- **OPEN BUG (contained, non-fatal):** the tuner runs on ALL agents' fleets. On fleet 30 (agent 58, $20k budget) `recommended_max_slots` returns 25 but that plan caps at 10 → `set_fleet_size` raises `EntitlementDenied` every ~30 min. Caught by per-fleet try/except (tick survives, fleet 29 unaffected, agent 58's fleet NOT changed — goal block returned None). Pure log noise today, but it recurs.
- **OPEN DECISION (owner's, unanswered — asked 2026-08-12, owner replied "stop all monitoring"):** should the tuner be **(a) scoped to the automation fleet only** (surgical, never overrides another paying user's manual slots/goal), or **(b) platform-wide with a plan-cap clamp** (AI manages every user's fleet)? The fix differs by answer: (a) scope the query; (b) clamp `recommended_max_slots` to the agent's entitlement. Do NOT deploy either until the owner picks — (b) actively changes other users' accounts.
- **Kill-switch if needed meanwhile:** `FLEET_AUTO_TUNE=0` on prod disables the whole tuner.

### R8 — Tail losses are RETIRE/TIME-LIMIT closures of underwater runs, not floor hits · STAGED (2026-08-11, agent 6 / fleet 29)
- **Question from owner:** alert cards show the open-run snapshot persistently red ("활성 런 전체 손익 합계 −1.34"); "why do we keep losing, how do we make plus profit."
- **First: the red card is a work-in-progress mark, not a loss.** Total = seed 1000 + realized +5.97 + open ≈ **1007 net +6/+7 over seed. The book IS net positive.** Winners get banked (leave the open set); small losers linger to their stop → the open snapshot always skews red. Timing artifact of a winning strategy.
- **Profit shape is healthy:** 85 runs, 32 wins (+16.09) vs 39 losses (−10.11), net +5.97; avg win +0.50 vs avg loss −0.26 = **~2:1, +expectancy**. Break-even for 2:1 is a 33% win rate; desk is at ~45%.
- **Finding (evidence, worst 12 losses):** NONE hit the max-loss floor — closed at **7–42% of floor**. Reasons: `adapt_retired` (SI −1.59 @39% of $4.12 floor; KAITO −1.19 @88%; HYPE), `desk_retired` (SOL ×2), `stop_event:at_time` (ADBE −0.73, HG −0.35), `trailing_lock` (ZEC, SOL, ADBE). **The biggest single loss (SI −1.59) was the ADAPT system retiring the run while underwater and dumping the full book far inside its own stop** — the `desk-cannot-see-the-rail-that-retires-it` (#244) pattern, still live.
- **Leverage is NOT the net lever** (checked): 2:1 ratio is scale-invariant; 3×→2× multiplies wins AND losses by 2/3 → net +5.97 → +3.98 (lower). Cutting leverage cuts profit. More size = more net (bounded by risk) — the daily-compound #363 already does this.
- **R:R geometry basically fine:** only 3/85 runs have target<stop. (Withdrew an earlier over-weighted USDKRW lead.)
- **Real lever — AI-FIRST framing (owner corrected 2026-08-11; `decisions-become-skills`):** the fix is a **sooppiy-AI skill/judgment, NOT a platform rail.** Split by who decides today:
  - **`desk_retired`** (SOL ×2) is already the AI choosing `retire` → pure **skill gap**: the exit-verb skill covers `close` but not the `retire` verb; teach the desk that `retire` on a within-stop live thesis is a full-book close with the same cost. Target the win/loss SHAPE, not zero losses.
  - **`adapt_retired` / `at_time`** (SI −1.59, KAITO, ADBE, HG) are **platform-forced with NO desk say** — SI was adapt-dumped while the desk had no vote. AI-first fix = **build the PATH to route that moment to the desk for a hold/reduce/close judgment**, not a platform rule that defers retirement. Build the daemon path, don't patch the row (`trading-decisions-belong-to-sooppiy-ai`, `never-touch-live-trading-config`). Platform only surfaces the situation; judgment is the AI's.
- **Next analysis pass (backtest-first, R6 discipline):** trace the `adapt_retire`/`at_time` close path; of the 39 losses quantify retire/time-driven vs own-stop and the recoverable fraction; then propose the retire-verb skill + the decision-routing path (both AI-first) for owner/desk approval.
- **Self-correction log this investigation:** (1) my monitoring short-P&L sign was inverted — fixed, memory `position-upnl-sign-convention`; (2) "desk ignores its reduce skill / empty why" was wrong — `why` isn't a persisted field, the real reason lives in `report`; (3) "tail = max-loss floor firing" was wrong — floors are $3–5, losses closed at 7–42% of floor; the true cause is retire/time-limit. Reported each plainly.

### R10 — Size-vs-loss-floor coherence · **SHIPPED (2026-08-14, PR #417, image 20260814-solutions-r10-rag)** — add-aware clamp + entry rail line + per-run-type rail
- **Evidence (n=3 in one day, −$118):** SPCX 1159 (stop 6.4% ⇒ $212 at full size vs $44 budget → brake fired at −1.07%, 26 min in), SOL 1099 aggregate (6 tranches made the AI's own $76.7 invalidation unreachable — floor at ~0.7% adverse vs stop at ~1.4%), GC 1186 (1.31% stop ⇒ $27.5 vs ~$13 floor). In every case the platform rail fired FIRST and the AI's authored stop was fiction. #244 gave the desk VISIBILITY of the rail; it still doesn't SIZE against it.
- **AI-first design:** prompt/skill lesson — "worst-case USD at your stop (notional × stop%) must fit the run's REMAINING loss budget; size down until it does." Platform fallback: shrink-only clamp in order-params apply (size_frac ↓ until stop-USD ≤ remaining budget) — composes with existing shrink-only rails (#81/#82).
- **Blocker to resolve first:** skills catalogue is AT CAPACITY (handoff trap 2026-08-06) — needs a merge/drop decision; and the clamp needs the wiring test pattern (brief-line trap).

### R11 — Momentum-chase against the desk's own written invalidation · **SHIPPED (2026-08-14, PR #417)** — last-cycle word line (age-stamped, errored-cycle-proof); owner ordered immediate ship
- QNT 1157 (bought 29 min after itself writing "thesis already invalidated"), INTC 1169 (bought after twice writing the bracket doesn't work), SPCX 1159 (full size into a +34%/5d extended mover). Candidate lesson: "a condition you wrote as invalidation stays binding across cycles unless the thesis is re-derived." Wait for one more day of tape before drafting the skill (2+ cycles rule; catalogue capacity).

### R12 — Event-table spam ~2,500 rows/day · **SHIPPED (2026-08-14, PR #417)** — change-driven + 30-min heartbeat
- Fleet 31 re-emits `fleet_status replenishing` every ~62s (×1,385/day); run 1161's queued flatten retries every ~33s writing `gate_skip` (×1,144 over 10.5h). No P&L impact; dedupe/backoff when convenient.

### R13 — pnl_audit entry-side fee asymmetry · **SHIPPED (2026-08-14, PR #417)** — fee_asym/resid columns
- 08-13 DRIFT flag (−7.38) proven benign to the cent: adapt nets exit-side fees only. Make the tool compute the expected fee asymmetry (or scale tolerance by open-leg fees) so real drift stays loud.

### R14 — Swing universe cannot fill 25 slots · **SHIPPED (2026-08-14, PR #417)** — S&P-100 seed roster, gates untouched (owner chose widen-universe via 'full make solutions')
- Fleet 31 stuck 17/25 all day; gates honestly drop everything (swing_history_thin 42–62 bars; backtest expectancy −72…−502 USD/trade). Options: widen the researched us-stock universe, or lower n_runs. Gates themselves are correct — do NOT loosen them.

### R16 — Cross-run same-symbol memory + desk_retired cooldown · STAGED (2026-08-14 sweep, n=1 pair + prior churn chains)
- **Evidence:** NQ 1184 desk-retired 09:47Z citing "no safe bracket"; fleet rebuilt NQ, and successor 1197 re-longed at a HIGHER price 4h later with zero reference to the predecessor — −2.42 then −2.15 same day. `desk_retired` symbols carry no cooldown (only adapt-retires get 24h); no prompt line carries cross-run same-symbol history (R11 is within-run only). Also the swing-side WMT/UBER/SBUX/PFE instant-rebuild chains (08-13, $0 each).
- **AI-first design:** a predecessor-run brief line at build/first-cycle — "this agent's previous run on {symbol} today: retired ({reason}), P&L {x}" — so the desk re-underwrites with its own history in view. Platform fallback: extend the 24h symbol cooldown to desk_retired (riskier — blocks legitimate re-entries on genuinely changed tape; prefer the brief line first).
- **Gate:** one more day of tape (2+ cycles rule). If the repeat-entry-after-retire shape recurs with losses, ship the brief line.

### W-fence — Execute-stage lease-expired skips deferring exits · WATCH (2026-08-14 sweep)
- 12 lease-expired skips in one day, 11 in market hours, one deferred a desk CLOSE (run 1116 JPM 15:42:44Z; retried next cycle). A fence that can defer an exit points the forbidden direction. Count daily; if closes get deferred again, investigate the claim/lease path.

## Fleet slot ledger over-commits after a resize (found 2026-08-17 cycle 5)

**Evidence.** Fleet 35: budget $10,009.75; 10 filled slots hold $9,999.96;
10 empty slots stamped $400 each. Slot ledger totals **$13,999.96 — 39.9%
over budget**. Headroom $9.79 against a $200 slot floor → `slot_dormant`
every tick (45 events). `replenishing:10/20` for 6h14m and counting.

**Mechanism.** The 25→20 resize (`slot_removed`, 21:36:36Z) drained the
excess slots but did not renormalise the survivors' `original_allocation_usd`.
Replacement funding is `min(slot.original_allocation_usd, headroom)`, so all
50 rotations re-fund at the stale allocation and the over-commitment
perpetuates. `build_fleet` has an under-fill reserve for exactly this state
(its comment cites fleet #26, 3/10 slots holding all $10k); the replacement
path has no equivalent.

**Cost.** 10 theses at 2× their per-slot share instead of 20 at 1× — a
permanent halving of diversification.

**BLOCKED ON THE SAME REPLAY as the ratchet/fee package.** Renormalising
halves book sizes, and small books are where the fee hurdle bites (AVAX
2026-08-17: fees 475% of gross on a $199 book). Required measurement:
realized expectancy of closed trades bucketed by book size against the
per-market fee floor. Do not ship a sizing change before it.

**Shippable independently once the above is decided:** the status string.
`replenishing:k/N` on a fleet with no headroom should read budget-capped.

## Three blocked-order paths (found 2026-08-17 cycle 7) — all BELOW the evidence bar

Runs 1336/1338/1341 each authored a trade that produced no order and were
then `idle_retired` at $0.00. Three distinct causes; none shipped.

1. **Idle-retire vs in-flight cycle.** run 1336: retired 00:27:55Z, cycle 12
   completed 00:29:24Z with a full short (stop $612, target $570), killed by
   `fence: run is stopped`. The fence is right; the idleness verdict ignores
   a dispatched cycle. **All time: 2.** Needs: count of retires with a cycle
   in flight, and the realized outcome of those orders.
2. **`fence: lease expired`** — all time 12. Needs: lease TTL vs p99 cycle
   duration.
3. **Spot `sell` via the discussion path.** run 1338 (`market_type: spot`):
   `order_discussion {proposed: buy 0.65, final: sell 0.58}` → refused as
   "spot sell with no inventory". The light prompt already withholds the verb
   via `can_sell`. **All time: 2** (08-13, 08-17), down from ~33/week before
   the prompt fix. Needs: does the discussion prompt get the same gate. n=1.

## Breakeven ratchet (#449): two PROVEN arithmetic defects — fix specified 2026-08-17 cycle 13

Running total over 2 live fires: **−$0.13891393** (AVAX 1335 pos-2
−$0.14144302, FIL 1358 +$0.00252909). Ceiling is $0.00 net **by design**
(`total ≤ exit_fee` → net = exit_fee − close_fee = 0 at a correct rate), so
judging fires by whether they are green is the wrong test.

**(a) Unit mismatch.** `_breakeven_floor_hit` takes no `baseline_pnl`;
`peak`/`current` are run-cumulative, `arm`/`exit_fee` are position-scoped.
`_trailing_lock_hit` already takes a baseline. Decisive on AVAX: position 2's
own excursion 0.4228 − 0.0806 = **0.3422 < 0.398 arm → would never have
armed**; it flattened at $0.0377 gross against an already-paid $0.0896 open
fee, a guaranteed loss at trigger.

**(b) One leg at an inflated rate.** `exit_fee` = notional × 0.001 × 1 leg
(28.024 × 0.001 = 0.028024 ✓). True crypto rate 0.00045 → true leg
$0.012598. Binding on FIL: `total` 0.015127 sits between the floors; at the
true rate the fire condition is FALSE.

**TRAP — do not fix (a) alone.** A position-scoped current is gross while the
floor is one leg, so baseline-correcting alone makes the best case **−1 open
fee**. The floor must become a full ROUND TRIP in the same change, with the
rate from `fees.fee_rate(market)`.

**Fail-before tests, both from live tape:** AVAX must not arm; FIL must not
fire.

**Residual after the fix:** even on a single-position run the comparison is
off by one open fee (`total` is net of it, `arm` is gross).

**Separate and larger:** ~4.7-minute mark staleness is the binding
constraint. FIL's mark refreshed 16x in 75.8 min; the peak existed for one
observation; arm and fire landed on consecutive marks with a $0.0458 giveback
entirely between them. No threshold tuning addresses this.

## Empty-why arms — watch CORRECTED 2026-08-17 (was "n=6", actually 131/132)

132 `intent:arm` events all time; **131 (99.24%) carry `why: ""`**; exactly 1
has a real why. It is the default behaviour of the arm path, not an anomaly.
One arm (run 1358, 08:29:58Z) was authored **103s after its run stopped**,
with `position_qty: 0.0`, and was still persisted to
`trading_runs.armed_order_json`.

## Arm-reachability rail — SPEC STRUCK 2026-08-17 cycle 14 (hypothesis refuted)

I specified a rail to clamp arms set beyond the measured next-look range.
**Measured: arm levels sit 0.1%–1.5% from entry** (one outlier, CL 4.4%) —
inside an ordinary day for these symbols. The levels are not the problem and
this spec should not be built.

**The real finding is arm STARVATION.** 132 `intent:arm` authored, **2
`armed_exit` ever (1.5%)**, none in 3+ days; 10 runs carry a persisted
`armed_order_json` and all 10 are `stopped`. Of the 44 runs that ever armed,
only **9 (20%)** ended by desk choice; **34 (77%)** were ended by a rail or
fleet action first — `at_time` 14, `adapt_retired` 7, `fleet_stop_all` 7,
`trailing_lock` 6. The prompt tells the desk to prefer arm over hold; the
platform then closes the book before the arm can act 4 times in 5.

**Measurement required before any remedy** (all candidates change when real
positions close): for each armed run closed by a rail, was the arm's level
subsequently hit inside the run's ORIGINAL horizon, and what would the
reduce have been worth at that level? Computable from stored marks.

## Arm starvation — MEASURED 2026-08-17 cycle 15, bounded at ~29% (was implied 77%)

Replayed every crypto run that armed and was then closed by a rail, against
1-minute Hyperliquid candles from the close to the run's OWN original
`at_time` horizon. 18 such runs, 14 replayable.

**4 of 14 (29%) had the arm level crossed inside the original horizon; 10
(71%) did not.** Crossings: 1175 SOL below 75.0 (low 74.650), 1293 UNI above
3.27 (high 3.3378), 1304 JTO above 0.586 (high 0.59043), 1305 FIL below
0.667 (low 0.65785).

**This corrects cycle 14.** The 77% rail-closure rate is how often a rail
ended the run — NOT how often that cost the desk a trigger. Most arms would
never have fired anyway.

**Correction to the cycle-14 spec:** it said "computable from stored marks".
There is no price-history table and `equity` payloads carry no mark. The
source is `price_fetcher._hyperliquid_post` with `candleSnapshot` at 1m —
finer than the ~4.7-min mark cadence the rails run on.

**NEXT LAYER (one script away, decides the whole question):** for the 4
crossings, what would the half-reduce have realized at the crossing versus
what the rail's exit actually realized? Crossing a level is not profiting
from it — for a short, `price_below → reduce` banks, `price_above → reduce`
cuts a loser.

## STRUCK 2026-08-17 cycle 17 — "LLM host is ~5x oversubscribed" (refuted by re-measurement)

Cycle 12 concluded the local model host was ~5x oversubscribed from
`178 calls/h x ~100s = 17,800s vs 3,600 available`. **The ~100s input was
sampled during a 06h-08h latency anomaly.** Re-measured with call volume
unchanged (189/h): decision calls take **3.9-7.0s**, giving **0.29x** — not
oversubscribed.

Hourly no-verdict rate for 2026-08-17: ~3% baseline (00h-05h), then 20.0% /
17.4% / 13.0% (06h/07h/08h), then **0% (09h, 10h)**. **Episodic, not
structural.** Cause of the episode unknown; do not invent one.

Also struck: the "reduce call volume or add host capacity" recommendation
built on that arithmetic. #468 (decision tier 300s) stays — cheap, plausibly
protective against a repeat — but is NOT established as effective; it spanned
the episode without moving the rate (18.5% -> 23.1%).

## RE-STATED 2026-08-17 cycle 17 — panel fallback on exits is a GOVERNANCE item, not a P&L one

Tested: fallback-authored closes n=16, total **-$4.206**, mean **-$0.263**,
31% wins. All other closes n=225, total -$180.417, mean **-$0.802**, 42%
wins. **Fallback closes realize BETTER on the mean.** The "it costs money"
framing is refuted.

Confounds not controlled: book size, regime, n=16 vs 225. So this is "no
evidence of harm", not "the fallback is good".

The governance concern is unchanged and must be argued on its own terms:
`_order_discussion` fails OPEN, so a path that labels itself "not the AI"
has authored 10 closes/reduces while §7b makes the panel the final author.

## SQL TRAP (found the hard way 2026-08-17 cycle 20): close rows overwrite entry_price

On a CLOSING `signals` row (`exit_price IS NOT NULL`), **`entry_price` is
overwritten with the exit price** — e.g. FIL 1358 `ep=0.66614 xp=0.66614`,
SUI 1356 `ep=0.67478 xp=0.67478`. Computing a realized move from a close row
alone yields **exactly 0.0000% on every leg**, which reads like a clean null
result and is a query bug.

Entry must be taken from the run's OPENING row (`exit_price IS NULL`).

Joins the standing trap list: `ts` not `created_at`; CONCAT with any NULL
returns NULL and the row vanishes; `dec` is reserved in MySQL; the DB wrapper
mangles a quoted `IN ('a','b')` list; an unquoted ssh heredoc eats `$.json`
paths.

## NEXT EXPERIMENT — horizon replay of target_pct (specified 2026-08-17 cycle 20)

H5 measured: target median **4.800%**, realized median **0.1478%**, **0 of 36
legs ever reached their own target**, r(target, realized) = **+0.155**
(r² 0.024).

**Confounded:** positions close in ~1h against multi-hour targets, so "bad
forecast" and "never given a chance" are not separated.

**The separating measurement** (tooling built in cycle 15 — 1-minute
`candleSnapshot` from close to the run's ORIGINAL `at_time`): for each of the
36 legs closed early, was `target_pct` subsequently hit inside that horizon?

* hit after exit → forecasts are sound, exit policy cuts them off; re-opens
  the arm/at_time precedence question with n=36 instead of n=4.
* not hit even with the full horizon → `target_pct` is decoration, and R:R
  gating, sizing and `outlook.exit.target_px` all consume a number with no
  content.

**Do not act on H5 before this runs** — the two outcomes imply opposite
remedies.

## MEASURED 2026-08-17 cycles 21-22 — target_pct is decoration, and the reachable band is now known

**H6 (cycle 21):** replayed 34 crypto legs from close to the run's OWN
original `at_time`. Target reached **4 / 34**, and all four had targets of
**0.60%, 2.00%, 0.60%, 0.60%**. **No target above 2.00% has ever been
reached**, median target 4.80%. Exit policy exonerated; the
arm/at_time precedence question is CLOSED (the n=4 hint from cycle 15 does
not survive at n=34).

**H7 (cycle 22):** max favourable excursion available inside each run's own
horizon, 29 crypto entries — **p25 0.52%, median 1.14%, p75 1.89%, max
4.24%**. Desk target median **4.55%**; the market **offered** that target on
**1 of 28 legs (4%)**.

**Arithmetic of the remedy:** the R:R gate demands target >= 2x stop. At the
median available excursion of 1.14%, a 2:1 ratio requires a stop **<=0.57%**.
The crypto fee hurdle is ~0.09%, so 0.57% is ~6x the fee — structurally
viable. Measured design band: **stop ~0.5-0.6%, target ~1.1-1.2%** against
today's ~1.2-2.5% / ~4.55%.

**The gate is not wrong; its inputs are drawn from a market that does not
exist.** Do NOT change the R:R ratio itself.

**LAST MEASUREMENT NEEDED before any change:** replay each entry against its
horizon and count, per candidate (stop, target) pair, how often the STOP is
hit BEFORE the target. Tighter pairs buy reachability with more stop-outs;
expectancy of the tighter band is unmeasured and is the only remaining
unknown.

**Method note:** a percentile-index bug in the cycle-22 probe printed
"3.47% -> 90% of legs". Inverted — 3.47% is near the TOP, offered on ~10%.

## RETRACTED 2026-08-17 cycle 30 — "dependency audit is RED on main" is NOT supported by CI

CI's `Python dependency audit` reports **success on both main (500d003a) and
PR #471**, using the identical command this entry was based on. The local run
below found 32 advisories across 9 packages and cannot be reconciled with
CI's environment. **Do not act on it.** If the vulnerabilities are real they
will appear in CI; they have not.

Kept below only as a record of what the local run said, and of the mistake:
a local replication made during a provider outage was allowed to block a
merge for two cycles after CI's own verdict had become readable.

### (original entry, retracted) dependency audit local finding

Surfaced only because GitHub Actions was in major outage and the standing
rule required replicating every CI job locally.

| package | pinned | first fixed |
|---|---|---|
| **aiohttp** | 3.13.5 | **3.14.3** |
| **python-multipart** | 0.0.20 | **0.0.31** |
| **starlette** | 0.49.3 | **1.3.1** |
| requests | 2.32.5 | 2.33.0 |
| urllib3 | 2.6.3 | 2.7.0 |
| click | 8.1.8 | 8.3.3 |
| curl-cffi | 0.13.0 | 0.15.0 |
| pyarrow | 21.0.0 | 23.0.1 |
| python-dotenv | 1.2.1 | 1.2.2 |

`pip-audit -r requirements.txt` exits **1**. The same CI job reported SUCCESS
on #465/#466/#468 hours earlier, so these advisories are newly published —
**pre-existing on main, caused by no PR.**

`aiohttp`, `python-multipart` and `starlette` sit in the request path of a
web service. **Owner call**: `starlette` 0.49 -> 1.3 is a major bump that can
break FastAPI compatibility and must not be attempted blind during an
Actions outage.

**HOW TO RUN pip-audit ON THIS MACHINE** (the venv has no `pip`, and
pip-audit's internal venv creation dies with `ensurepip` SIGABRT on uv's
managed CPython — `uv tool install`, `uv run --with` and `--no-deps` all hit
it):

```
cd service && VIRTUAL_ENV= uv run --with pip-audit --python /usr/bin/python3 \
    pip-audit -r requirements.txt
```

## SILENT RAILS — measured cost, 2026-08-17 cycle 35

Two shipped rails know something the desk does not, and neither tells it:

1. **R:R ceiling** clamps `target_pct` and journals a note. `order_params`
   notes **never reach the prompt**; there is **no brief line** for a clamped
   parameter (verified by grep).
2. **`classify_arm`** labels an armed exit protective/defensive. Nothing
   consumes the label.

**Measured cost of the silence:** run 1375 requested **target_pct 3.02%
three times in 95 minutes** (17:56, 18:27, 19:30) while its stop drifted
0.47 -> 0.475 -> 0.48. The clamp fired every time; the request never changed.
The desk is not deriving the target from the stop — it repeats a fixed
figure, and nothing corrects the belief.

**A rail that silently corrects a repeated mistake converts a learnable error
into a permanent one.**

**Baseline for the fix is already on tape:** three pre-notification cycles on
run 1375, all identical. The test after shipping a brief line is simply
whether the requested target changes.


### R17 — `size_frac: null` on an OPEN falls through to default sizing — largest bet lands on the weakest idea · STAGED (2026-08-18 cycle 41, n=2 ACCOUNTS)
- **Evidence (agent 60 / fleet 34, 08-15, verified on tape by main session):** ETH run 1272 cycle-4 buy parsed `size_frac: null` → filled **$990 notional (90% of the $1,100 run budget)** at the day's WEAKEST conviction (0.58 entry conf; desk's own cycle-3 report was bearish), vs $495 SOL @ conv 0.605 and $165 BTC @ conv 0.6905. The −$1.87 ETH run = **55% of the account's whole −$3.41 day**. Sizing was inversely ordered to conviction because null → default, not because the desk chose it.
- **Prior instance (agent 6, takeover brief §3):** the top P&L contributor since the 08-15 reset traces to `order_params: absent` → default sizing at **8.2×** the desk's habitual size. Same class, opposite sign — the default is a coin-flip amplifier.
- **Counterfactual at live marks (this tape):** ETH at the desk's habitual $165–495 sizing loses −$0.31…−0.94 instead of −$1.87 → the null-default cost **≈ $0.9–1.6 on one day, one account**.
- **Fix direction (AI-first order):** (a) skill/prompt: the desk must always author `size_frac` on an open (teach the observable: "a null size is not 'neutral', it is the platform's default bet"); (b) platform fallback: a null `size_frac` on an OPEN defaults to the run's SMALLEST recent authored size (or a conservative floor), never a large fixed fraction. Ship only after measuring the default's fleet-wide frequency and signed P&L (both accounts, all time).

### R18 — Rail stop-floor (0.3%) fires inside crypto session noise — spec-correct, economics wrong · STAGED (2026-08-18 cycle 41, n=1 measured + documented pattern)
- **Evidence (SOL run 1274, 08-15):** desk proposed a nonsense 0.016% stop; the rail floored it to 0.3%; the watcher stop-out at 75.514 was within 0.01% of the local top; SOL mean-reverted below entry by 08:08Z. **Stop-out cost ≈ $1.04 vs holding** (leg −0.88 vs ≈ +0.16). The 0.3% floor is tighter than SOL's ~3%/day ordinary move — the floor rescues the desk from instant fee-death and hands it noise-death instead.
- Matches standing watch (a) in HANDOFF §8: judge stops in ORDINARY DAYS. AI-first fix already specified there: state the symbol's ordinary daily move AT bracket-authoring time. The new fact is a measured $ cost of the FLOOR itself. Gate: more fires with the same shape (floored stop < ~0.3 ordinary days collected by routine range) before touching the floor.

### R19 — Budget geometry builds pre-untradeable us-stock slots · **REFUTED (2026-08-18 cycle 45 — full replay; do not re-open without new evidence)**
- **The replay killed this.** (1) R15 DID evaluate run 1380 (thesis 16609 carried vol_daily_pct 3.893 at compose; the config SNAPSHOT strips factor_scores_json — post-hoc snapshot replays are blind, see trap below). (2) 1380 passed by design: room $3.12 supports 0.54 ORCL shares at a 1-sigma stop — inside the 0.53–0.7 judgment band R15's calibration EXPLICITLY leaves to the desk ("ORCL 1164 traded at 0.675 while FDX 1216 refused at 0.68"). The desk refused at ~0.72 shares — the FDX-class judgment call, not a structural impossibility. (3) Cross-run replay: loss-rail/max-bet fractions are uniform (2–4%) platform-wide; runs with identical-or-worse fractional geometry (e.g. 1134: 0.72-of-bet cap at authored stop) traded fine; zero-trade runs occur at every budget size. (4) The absurd profit_target_usd ($120 vs ~$18 reachable) is inert — it is only a stop-event level that never fires; the trailing lock does the banking.
- **What survives:** the desk burned 7 open cycles re-analyzing a slot it had declared infeasible at cycle 1 (LLM waste, bounded by the 12-cycle idle fuse). Not worth a gate on n=1.
- **Evidence:** fleet 35 ($10,009 / 14 slots ≈ $715) → per-run loss rail ≈ $3, below the dollar cost of any realistic stock stop (~2.9% needed on ORCL). Run 1380's own cycle-1 outlook states it: "the required stop (~2.9%) would exceed the $3.12 loss rail, making a new position infeasible." The run then held 7 open-market cycles and parked — a slot that can never trade, burning research/LLM.
- **R15 (bracket feasibility, deployed 08-14 23:11Z) did not block this build** — either the check doesn't run on this compose path or its threshold passes configs the desk itself immediately declares infeasible. Verify which before designing.
- **Fix direction:** extend the exposure-feasibility build gate: at compose time, require (slot_budget × max_loss_frac) ≥ (typical stop distance in $ at minimum viable notional) for the market class; refuse/resize the slot otherwise. Evidence gate: a second fleet/slot with the same self-declared infeasibility, or a replay count of how many current slots fail the test.

### R17 addendum (2026-08-18) — third account confirmed
- Fleet 32 (agent 5): every us-stock entry had `size_frac: null` + `leverage: null` → extreme-appetite defaults filled $1,106 max-bet × 3× leverage; SPCX $3,317 notional → −$35.81 (65% of the us-stock loss) on a −1.07% move. **n=3 accounts (agents 6, 60, 5).** The default is the single largest loss author on the platform's us-stock tape.

### R20 — OWNER ORDER (2026-08-18, verbatim: "for make fleet N automatically by SOOPPIY then must be include USA tech hot to 5 issued stock 5 always") · HARD-READY, implement next session
- **Spec (as understood):** whenever SOOPPIY auto-builds/replenishes an N-slot fleet whose market scope allows us-stock, the research/candidate universe must ALWAYS include the **top-5 hot-issue USA TECH stocks** (ranked by the existing hot-issue/2-day-mover machinery restricted to a tech roster), so 5 tech names are always among the candidates.
- **Boundaries kept:** existing build gates (expectancy, maturity, R15) still apply to the seeded names — "include" means guaranteed universe presence, not gate bypass; the desk remains the final author of every order (§7b). Also add the matching prompt line so the research planner authors theses for these 5 names every batch ("add prompt for sooppiy" — the owner's words).
- **Implementation design (pinned to code anchors, 2026-08-18 cycle 48):**
  1. `US_TECH_HOT_UNIVERSE` constant in symbol_research.py — the S&P-100 TECH subset (AAPL ACN ADBE AMD AVGO CRM CSCO GOOG GOOGL IBM INTC INTU META MSFT NFLX NOW NVDA ORCL PLTR PYPL QCOM TXN TSLA), env kill switch `US_TECH_HOT_SEED` default on. Mechanical membership list, same justification prose as SWING_SEED_UNIVERSE (symbol_research.py ~245).
  2. Universe assembly (~line 356, the `if "us-stock" in autom:` block): ALWAYS extend with the tech roster (unconditional, unlike the swing seed which gates on swing demand) — guarantees the names are researched and carry mom_2d factors.
  3. Selection: after `_mover_rank_us_stock(eligible)` (~line 1436), new `_ensure_hot_tech_lead(eligible, k=5)`: reorder us-stock slots so the top-min(5,N) tech-membership theses by the SAME mover key (|mom_2d|×vol confirmation — the owner algorithm) lead the us-stock ordering. Universe/ordering guarantee only — expectancy/maturity/R15 gates still veto at build (documented safety kept), desk still authors every order (§7b).
  4. Prompt: research planner clause — always author theses for the current top-5 hot US tech names (locate the stage-2 planner prompt; "add prompt for sooppiy" is the owner's wording).
  5. Tests: tech roster present in universe when us-stock scoped; top-5 tech lead the us-stock ordering post-rank; non-us-stock markets' ordering untouched; kill switch off restores old behavior; gates still veto a seeded name.


### R21 — #485 ratchet baseline inverts on same-position losing covers · **LICENSED (2026-08-18 cycle 70, two-agent cross-checked)**
- **Defect:** #485 computes position-scoped peak as `peak_pnl_usd − CURRENT realized`. A losing partial cover drops realized and inflates the phantom peak by the loss booked — run 1417: true position peak +$0.1015 < arm $0.2549, yet fire-time subtraction manufactured 0.4614 → armed → flattened the remainder 9s after the desk's own reduce. The desk's reduce arms the rail that kills its book (976-shape).
- **Fix spec (both agents converge):** baseline = realized **at peak epoch** (freeze when peak is recorded), or track the position-scoped peak directly. Never realized-at-fire. `_breakeven_floor_hit` run_engine ~1004.
- **Evidence bar met:** measured + replayable + independently derived twice. P&L of the first fire ≈ $0.00 (mark-level flatten) — ship as correctness fix with the ratchet ledger (5 fires ≈ −$1.00 lifetime, zero net gains) as context. Coordinate with the parallel session that shipped #485.


### R22 — Ratchet/trail arm never rescales after partial covers · STAGED (2026-08-18 cycle 92, THREE measured instances of dimension (b))
- **Evidence:** (i) 1462: activate_usd $1.99 sized at open for the full book; after 50% banked, the remainder's own excursion peaked $1.04 — could never arm; gave back ~48% of peak un-defended. (ii) 1426 XOM: activate $15.29 vs $0.16 peak — unreachable at profit scale. (iii) 1417-era: threshold sized off machine_size ~40× the actual book. The rail is dead precisely for desks that trim well (the validated harvest template).
- **Fix direction:** rescale the trail/ratchet arm on every position-size change (activate_usd × |qty_now|/|qty_at_open|, floor at fee-scale), or arm off the position's own excursion (peak − peak_realized, the R21 quantity) rather than a fixed dollar set at open. Money-path change: requires counterfactual replay across historical fires/non-fires before shipping.

### R21 addendum (2026-08-19 cycle 94) — FIRST LIVE FIRE: VALID. Fix #487 confirmed working
- Run 1489 UNIUSDT, 03:16:31Z, `stop_mechanism: breakeven_ratchet` (the new discriminator event made attribution possible): base = `peak_realized_usd` −0.0045 (open fee), position's OWN excursion 0.0355 ≥ arm 0.02 → armed on a genuine peak, no phantom. Fire saved ≈ $0.075 vs the live mark (n=1 — no mechanism generalization). **Epoch baseline holds under live fire; R21 closes.**
- New dimension logged (not a defect, n=1): arm is fee-anchored at 0.1%/side while actual venue fees are 0.045%/side → arm sits at 2.2× the true round trip; on a $10 probe book the arm ($0.02) ≈ 0.2% price noise, and the fire stops the WHOLE run. Watch for degenerate-scale fires on probe-sized books.

### R23 — Outlook sweeper has no stopped-run fence: ~14 wasted LLM calls/hour on dead runs · MEASURED, SHIP NOW (2026-08-19 cycle 94)
- **Evidence (8h window, two-agent + main-session verified):** 112 outlook events written to runs already past their stopped_at — 111 `source:"sweeper"` across 15 stopped runs = **19.8% of ALL outlook writes**, ≈13.8/h. Every one consumed a live LLM call (basis.verdict adjusted 106 / adopted 5, zero algo fallbacks); the `tasks.py:864` docstring "Rule-based, no LLM calls" is stale and wrong (`_standing_payload` → `_llm_payload` first). Worst case: run 1407 swept 23h post-stop.
- **Root cause:** sweeper iterates fleet slots' `current_run_id`; `outlook_refresher.py:143` classifies `status != "running"` as sweepable "run_idle" — no stopped-run fence. A slot bound to a stopped run is swept every cadence until rebound.
- **Why it matters:** the shared local LLM is measured ~5× oversubscribed (the no_verdict signature); this is a pure waste stream feeding it. Non-money-path fix (outlook telemetry only): skip runs not in status "running". Per implement-every-time: ships this session, pipeline binds.

### R24 — Deferred-params branch structurally defeats "AUTHOR IT EVERY TIME" · STAGED (2026-08-19 cycle 94, n=2/2)
- **Evidence:** every in-window actionable decision with `order_params deferred:true` had `outcome: absent` (1479 cyc7, 1481 cyc12 → both null_size_cap fires); all 3 non-deferred authored params. The prompt line cannot bind on the defer path because params are simply never produced there — mechanism, not desk mood. (No light-vs-full claim possible: zero full-route entries in window.)
- **Honest cap ledger:** the cap is the designed backstop and it prices both ways — cost $1.13 forgone on the 1479 winner (uncapped net +$1.72 vs +$0.59), saved on earlier unsized losers (+$0.328 leg / $2.19 run / +$0.05). Insurance, working as designed.
- **Fix direction (needs design, money-path):** an actionable decision entering the defer branch should trigger a follow-up params request (the #473 render machinery exists) instead of falling through to absent→cap. Gate: more instances + measured cap cost/save balance turning negative.

### R25 — Simulated fills execute at cached quotes with no staleness check; fast tape converts feed latency into phantom P&L · STAGED, MEASure FIRST (2026-08-19 cycle 109, n=1 fully traced)
- **Evidence (run 1531 FILUSDT, two agents independently):** short filled 15:28:29Z @ 0.6498 — the 15:24–15:25 cached quote, 3.5–4 min stale — while the live tape printed 0.66–0.67 mid +5.1%/min cascade. The position was **−$5.26 the instant it was marked honestly** (~1 min later). At the real 15:28 price (~0.667) the same round trip is a small WIN; the recorded −$5.44 is substantially a stale-fill artifact.
- **The artifact cascades:** phantom loss −$5.18 breached the house loss-floor ($4.18, advisory brief line run_engine.py:4557) → the brief told the desk "past the floor … the house rule is to CLOSE" → desk closed at the local bottom (cut cost a further ~$2.4–2.6 vs holding to its own next cycle). One stale quote authored the entry loss, the advisory breach, AND the churn exit.
- **Also poisoned the entry decision:** the desk's own invalidation (0.652) was already breached on the live tape 3 min before the fill — but its mark was equally stale, so it could not see it. Detector help is physics-bound (cascade_shock needs the move already printed; even 60s cadence could not beat this fill).
- **Fix direction (money-path — do NOT ship without measurement):** quote-age check at execute_paper_trade (refresh or reject/slip market orders when quote age > threshold, at minimum during active shock flags); record mark age on every fill. **Measurement first (experimental mindset):** sweep historical fills for quote-age distribution and recompute P&L at age-corrected marks — how many legs and how many $ are phantom? Ship only on that result.

### R26 — The backtest expectancy gate is DIRECTION-BLIND and alien-in-kind: a long-only $100k daily-bar replay vetoes candidates for 87.5%-short fleets · MEASURED, HIGH-IMPACT (2026-08-19 owner diagnosis)
- **Evidence (entry-funnel agent, window 08-15→19):** `backtest_gate.symbol_expectancy` → `backtest_strategy.simulate()` runs a **long-only** Phase-4 confluence replay (initial_cash $100k, 5%/10%/14d) regardless of thesis direction, while live fleet entries are **35/40 = 87.5% SHORT** on $100–300 slots. A downtrending symbol backtests long-negative exactly when a short thesis is most plausible. Blocked in-window: LLY 315×, MRK 233×, AAVE 207×, KO 145×, GE 135×, NVDA 124×, ABBV 120×, BCH 97×… — **the most liquid names on the platform**, each on a −0.03%-to-−0.6%-of-$100k simulated expectancy. 609 gate events; the contamination hypothesis (R17-era sizing) was FALSIFIED — the stats aren't live trades at all.
- **Downstream cost:** liquid names stripped from every rebuild → fleets fill with residue candidates the desks correctly hold (96.8% hold; the falsification sample showed declined entries were ≈ fee-negative) → 12-cycle fuse retires them → 177 zero-trade retires consumed **72.7% of all desk LLM cycles (~17M tokens/window ≈ one full lane of the 5×-oversubscribed local model)** for $0.
- **Fix direction:** pass thesis direction into symbol_expectancy and simulate the SAME side the thesis proposes (short replay for short theses), or restrict the gate to direction-matched history; keep the veto semantics. Pipeline binds: fail-before test (short thesis on downtrending symbol currently blocked by long-negative replay), full suite, counterfactual sanity on the 18 blocked names.
- **Companion facts for scale (P&L agent):** post-fix expectancy +12.8bp/trip (t=0.77, unproven), utilization 0.18%, median trip $52 — unblocking candidates addresses throughput; SIZE remains the other binding constraint (owner resized fleet 38 to 15; 6–8 recommended vs candidate supply).

### R27 — Floor-carry churn: the run-cumulative loss-floor brief condemns every fresh entry after one big loss · MEASURED n=2 SAME MECHANISM, SHIP-READY DESIGN (2026-08-20 cycle 133)
- **Evidence (run 1531, two-agent cross-checked):** the $4.18 advisory floor (`_loss_verdict_line`, run_engine ~4620, = 0.006 × run budget; brief-only, zero enforcement consumers) reads `compute_run_pnl` — RUN-CUMULATIVE. After the −$5.44 phantom stale-fill loss, the run's total sits permanently past the floor, so: (i) the floor line is INVISIBLE at entry (renders only with an open position) → desk enters; (ii) first held cycle, the brief says "past the floor … the house rule is to CLOSE" → desk obeys at any wobble. Fire #2: covered at +0.12% against (1/41 of stop, 30 min into 30h), −$1.16 leg, counterfactual −$2.20 at live mark, class (a) n=4. The desk was directionally RIGHT both times; the mechanism authored the losses. Enter→condemned→exit→re-enter is structurally guaranteed until the run dies (1531: consecutive_losses 2, retires at 3 or at_time 15:24Z).
- **Fix directions (pick at implementation):** (a) position-epoch floor — evaluate the floor against P&L since the CURRENT position opened (the R21 epoch pattern: total − realized_at_entry), keeping the run-cumulative number as context, not mandate; (b) render the floor state at ENTRY decisions too, so a condemned entry is visible before it opens; (c) block fresh entries while run total is past the floor (platform gate — heaviest, conflicts with §7b least-touch). Run-level bleeding stays covered by consecutive_losses retire, max_loss rail, at_time.
- **Note:** R25 fixed the phantom SOURCE; this fixes the phantom's PERSISTENCE. Both fires so far obeyed a number that was 97% yesterday's carried loss.

### R28 — Local LLM host outages leave the desk mute for days, unannounced · **SHIPPED (2026-11-07 sweep: `llm_silence` admin alert)** — outage itself is an OWNER item
- **Evidence (two independent routes, two outages):** `llm_usage` decision calls fell from 238–357/h to 2–13/h at **2026-11-05T21Z** and had not recovered by 11-07T15Z (42 h+); the previous spell ran **2026-10-30T12Z → 2026-11-02T~10Z (~70 h)**. Worker log since the 04:12Z restart: **967 `LLM generation failed (provider=local): Request timed out`** in 11 h (70–97/h, every hour). A 5-token probe from inside the worker to `LOCAL_LLM_BASE_URL` (a Tailscale host, not the prod box) took **271 s and timed out**. Effect on the desk: agent 6 **255/255 decisions hold, 251 with no verdict** (70 scaffold + 182 rule/"no llm response"), agent 60 27/29 scaffold; **0 fills** in the KST day. Per-day scaffold+infra-fallback share (decision payloads) since 10-26: up days ≈ 4–8 %, down days ≈ 95–100 % — a step function of host uptime, as memory `month-loss-analysis-1005-veto-override` recorded.
- **What it cost / saved, plainly:** $0 realized. On the 10-05→11-06 tape agent 6 ran −$0.058/trip × ~14 trips/day ≈ −$0.8/day expected, so a mute day is "+$0.8" only in the sense of §5 solution #7 of the 11-06 analysis (not trading agent 6 = +$27.21). **Not improvement.** The platform exists to trade; 112 h mute in 9 days is ~50 % dead time, and the user-facing `fleet_churn` alert blamed "market volatility" for 16 idle-retire rotations the dead LLM caused.
- **Shipped (platform, because a mute desk cannot perceive its own silence):** `service/server/llm_silence.py` + `tasks.llm_silence_loop` (role research, 15-min tick): trailing 120-min window of `decision` events; ≥10 decisions and ≥80 % mute → ONE `admin_alerts.notify_admins` email+SMS (console recipients, both set on prod), re-alert every 6 h while mute, one recovery notice under 50 %. Kill switch `LLM_SILENCE_ALERT=0`. Reads only; never touches a run or an order.
- **Falsifier (next tape):** the first alert must land within 2 h 15 min of the next outage's start (window + tick), with exactly one re-alert per 6 h and one recovery notice; a mute day with no alert in the worker log (`[LlmSilence]`) means the fix FAILED. Also: today's outage is still open at ship time — the alert should fire on the first tick after deploy (prod window is ~99 % mute); report whether it did.
- **Owner item (cannot be fixed from the platform):** the LLM host itself. Options are the owner's: keep the host awake / on power, or point `LOCAL_LLM_BASE_URL` at a host that stays up. Paid-provider fallback was deliberately removed (owner 2026-07-30 "all AI local") and is NOT proposed here.

### R29 — Fleet 43 is capped at 3/8 by the user's plan; the planner retries every candidate every pass · OWNER ITEM + STAGED (planner spam)
- **Evidence:** `fleet_events` fleet 43: **37,922 `candidate_skipped` in 7 days (≈5,400/day; 2,532 in the last 24 h)**, every one `"plan allows 3 concurrent run(s); 3 already active"`; first such event **2026-09-15T19:13Z**, the day after user 25's `enterprise` manual grant expired (2026-09-14). Active plan `pro` (Stripe `sub_…`, **expires 2026-11-17**, auto-renew on) → `PLAN_LIMITS["pro"]`: max_concurrent_runs 3, max_bet_usd 1000 (also 22 `plan caps max bet at $1000` skips), max_fleet_size **0** (a pro user could not CREATE this fleet today). `ENTITLEMENTS_ENFORCED=true`. Resolves the 11-06 loss analysis §6 open item.
- **Reading:** code-correct enforcement; a product gap. The fleet row still says n_runs 8 and the UI shows `replenishing:3/8` forever; the planner iterates 4 candidates × 5 waiting slots every supervise pass although the deny reason is slot-independent. **If the Stripe renewal fails on 11-17, `plan_code_for_user` returns None → limits 0 → `check_run_start` denies everything and `subscription_enforcer` pauses the 3 running runs** — agent 60 goes dark; the owner should know a week ahead.
- **Owner decision:** resize fleet 43 to 3 (or restore an enterprise/professional grant). Monitoring will not edit the fleet or the plan.
- **STAGED platform fix (not money-path):** when `check_run_start` denies for concurrency, the planner should skip the remaining waiting slots for that pass and emit ONE `fleet_status` reason instead of 4×N `candidate_skipped` rows; and the user-facing `fleet_churn` alert must not attribute idle-retire rotations to "market volatility" when the retire reason is `idle_retired` under a mute LLM (R28). Gate: ship after R28's alert is seen working on one outage.

### R30 — "Chair reply unparseable" is a symptom of the mute LLM, not a chair defect · **KILLED as systematic (2026-11-07 sweep)**
- Hypothesis: the three-agent desk's chair stage fails to parse so often that it is dead weight (3 LLM calls per decision) in an LLM-starved regime. Measured on `decision` payloads 10-26→11-07: on up days chair `unparseable` is **1–4 %** of AI-decided decisions (3/74, 4/415, 5/84, 5/405, 8/389, 15/425); it reaches **4/4 = 100 %** only on 11-07, when the host answers nothing within the timeout and replies arrive truncated. **Killed.** Do not re-open without an up-day rate > 10 %.

### R31 — The idle fuse retires runs the desk never spoke to; a dead LLM authors every rotation · **SHIPPED 2026-11-09 sweep** (see 2026-11-09 note §6)
- **2026-11-09:** shipped as `_mute_cycles` (scaffold, or rule with fallback "no llm response"/"decision json unparseable"; NOT "panel unavailable" = already `entry_held`, NOT "no llm provider configured" = config, not outage). Reproduced 5 days / 2 outages (today 25/26 zero-verdict). Known NOTE: an entry-zone wake cycle during an outage is discounted twice (wake + mute) — a few cycles per outage, fleet runs still capped by `at_time`; exact fix = count distinct cycles across the four categories. Falsifiers: zero-verdict idle retires → ~0/day while mute; idle retires still happen on UP days; no run outlives `at_time`.
- **Evidence:** `run_engine.py:1613` `worked = cycle_seq − closed_market − entry_wake − entry_held`; a `no_verdict` / rule-"no llm response" cycle counts as worked. Zero-verdict share of agent-6 `idle_retired` runs per UTC day: **10-31 12/13, 11-01 22/23** (outage 1), **11-06 15/18, 11-07 12/16** (outage 2); up days 6/10–13/15. `_entry_held_cycles`' own docstring says an LLM outage must not author rotation but exempts only `entry_held`. Cost per mute day: ~25 builds, ~10 research batches (`'llm': 0`), 15 symbols benched 12 h simultaneously, ~850 decision call attempts at a dead host, 3 false `fleet_churn` user alerts. Fees $0.
- **Fix (platform; the desk cannot act while mute):** subtract cycles whose decision was `decided_by scaffold` or `rule` with an infra `fallback_reason` from `worked` (mirror `_entry_held_cycles`); keep `at_time` and the other terminals untouched so a run still expires on its horizon. Falsifier: `idle_retired` runs with 0 AI verdicts in their life must drop to ~0 per day; if idle retires vanish on an UP day too, the subtraction is over-broad.
- **Not shipped 2026-11-07:** R28 took this run's pipeline/review budget and the change touches run lifecycle during a live outage. Ship next run with fail-before/pass-after on the `worked` formula + two reviewers.

### W-post-stop-cycle — a run journaled a decision 18 min after it was stopped · WATCH (2026-11-09 sweep, n = 1)
- Run 143128 ENAUSDT stopped `idle_retired` 11-09T17:01:29Z; decision/recall/order_params/gate_skip at 17:19:58Z (hold, $0). Likely a cycle in flight across the stop while LLM calls time out (271 s each). **Live-risk trigger:** any post-stop decision carrying an order or fill. Measure: decisions with `ts > trading_runs.stopped_at` per day.

### W-chair-refuse — `RUN_NULL_SIZE_REFUSE` will refuse ~83 % of chair-flipped entries · WATCH (2026-11-07 sweep)
- Since 10-05, 281 AI decisions had the chair amend `action` to buy/sell; the flip drops `order_intent`+`outlook` by design (run_engine ~7055) and the light route defers params → **232 (83 %) had no size** (204 `defer`, 28 `absent`; 181 hit `null_size_cap`). Under the 11-06 refuse rule these entries no longer exist. Sign unknown: the 11-06 analysis priced panel-reversed buy→sell trips at −$2.46 / 107 trips. **Measure:** `null_size_refused` gate_skips whose decision carries `chair.amended ∋ action`, with the counterfactual at the live mark. AI-first lesson if the refused set would have been profitable: a chair that changes the verb to an entry must author `size_frac`.
