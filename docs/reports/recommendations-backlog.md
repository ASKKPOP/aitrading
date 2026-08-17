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

