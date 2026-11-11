# Automation monitoring — 2026-11-11 (UTC day) — daily 24h sweep

Newest-first. Authority for rules/access/traps: `HANDOFF-automation-monitoring.md`.

## 24h sweep — 2026-11-11T15:13:26Z (KST day 2026-11-11 = 11-10T15:00Z → 11-11T15:00Z)

Prod clock `SELECT UTC_TIMESTAMP()` = 2026-11-11 15:13:26. Window = 11-10T15:13:26Z → 11-11T15:13:26Z
(≈ the KST day; no fill in the 13 min that differ). Worker + backend on
`sooppiy-backend:20261110-sweep-20261110` (c46a3ff); origin/main was c972dc8 (+1 docs) → no code drift.
Trading set re-derived = exactly {6, 60}. No leftover `/tmp/sooppiy-sweep.*`. Early P&L commit 2bc34a5
carried **a wrong figure (−0.65)** — corrected below.

### 1. P&L — dollars first

| window | agent 6 (info) | agent 60 (forevery1969) | combined | n trips | fees |
|---|---|---|---|---|---|
| **24 h ≈ KST day 11-11** (fee-inclusive per trip, incl. orphan closes) | **−1.645** (win 22/34) | **0.00** (0 fills) | **−1.645** | 34 | 1.005 |
| same, **without the largest** (NEAR 151814a −2.755) | **+1.11** | — | +1.11 | 33 | |
| UTC 11-10 (pnl_audit all_in = ledger −0.61 + orphan −0.49) | −1.10 | 0.00 | −1.10 | | |
| UTC 11-11 to 15:13Z (all_in = ledger +0.87 + orphan −0.47) | +0.39 | 0.00 | +0.39 | | |
| open uPNL now | none | none | 0.00 | | |

**Verdict: a −$1.65 day, and it is one trade.** Stripping NEAR 151814a flips the sign (+1.11) →
by owner rule 6 the day is **inconclusive as a strategy reading**; it is conclusive about one entry.
Cash vs 10,000 seed (no open positions): agent 6 9,890.94 (−109.06), agent 60 9,995.95 (−4.05). Agent 60's −4.05 cash gap vs yesterday's "lifetime realized −1.34" is NOT reconciled (not verified).

- Routes: (a) Agent A pairing −1.65; (b) Agent B pairing −1.645 and plain SQL (Σ close pnl −1.1429 −
  window entry fees 0.4937 − pre-window entry fee 0.0085); (c) patched `pnl_audit` all_in
  (−2.00 for 11-10 15:13→24Z + 0.39) = −1.61, residual −0.03 = pre-window fee/rounding.
- **My error (early commit):** −0.65 over 32 trips. I paired fills by `run_id`; the two orphan
  stop covers (BTC 21:35Z −0.488, FIL 01:30Z −0.473) carry `run_id NULL`. Both subagents caught it
  independently. The deployed `pnl_audit` has **the same blind spot** (§6, fixed this run).

### 2. Per-trade reasons (Agents A and B, cross-checked)

| run | sym | notional | net $ | entry author | exit author | reason |
|---|---|---|---|---|---|---|
| 151814a | NEAR | 103.8 | **−2.755** | desk sell→sell, **size_frac 0.3** at chair conf 0.6 (lowest band), `railed {}` | watcher SL 2.5 % (fill +6.1 bp) | shorted into a +6 % up-leg (3.50→3.72 over ~10 h), **21 min after the same fleet flattened NEAR 151801**; 5.5× normal size on a generic why; stop = 1.7× NEAR's median hourly range, hit in 33 min |
| 151814b | NEAR | 17.4 | −0.379 | **trader BUY 0.65 → chair overrode to SELL 0.62** | watcher SL 2.0 % (+9.2 bp) | the desk's own 23:41Z outlook said "short plan invalidated — price already above 3.56"; the chair re-shorted at 3.6435, 4 % above entry (a). Trader was right. |
| 151825 | BTC | 45.5 | −0.509 | desk sell 0.1 | orphan watcher SL | wrong direction (−0.34 % at 1 h); run died `stop_eval_failed` 18:37Z (deploy window) → handed off |
| 151804 | FIL | 18.7 | −0.481 | desk sell | orphan watcher SL | wrong direction; same handoff. 6 orphan verdicts all "sell"/agree → only a buy verdict closes a short |
| 153039 | TRUMP | 124.5 | +0.520 | desk size_frac 0.4 | ratchet | caught a 0.5 % dip at 4× size; 4 h move −0.54 % — timing luck, not edge |
| 151796/151795/151789 | ETH/ENA/HYPE | 16–19 | +0.48/+0.43/+0.21 | desk | **desk trail** (give 0.15) | real down-moves; the trail kept ~80 % of peak — the day's only exits that rode a move |
| 152185 | UNI | 37.5 | +0.301 | trader buy → chair sell | **desk arm** reduce ½ (+0.147) + ratchet | the 1 of 9 armed exits that fired; 0.85 % from entry = reachable |
| 152355 | UNI | 112.8 | +0.125 | desk 0.3 | ratchet | right direction (4 h MFE 4.0 %); ratchet banked 0.2 % |
| 24 others | | 15–45 | Σ ≈ +0.33 | desk | ratchet | fee-sized moves; 9 net-negative (Σ −0.12): mark stepped through a 1–2-tick floor |

| exit mechanism (B) | n | gross | fees | net |
|---|---|---|---|---|
| breakeven ratchet | 27 | +1.986 | 0.772 | **+1.214** |
| desk trail | 3 | +1.165 | 0.048 | **+1.118** |
| desk arm | 1 | +0.164 | 0.017 | +0.147 |
| run watcher stop (NEAR) | 2 | −3.024 | 0.110 | **−3.134** |
| orphan watcher stop (handoff) | 2 | −0.932 | 0.058 | **−0.990** |

- **Direction: no edge (A).** 33 entries, all shorts; right at 1 h 15/33, at 4 h 14/33, on a tape that fell
  1–9 %. Fifth replication of "no entry edge".
- **Size does not track confidence (A, both days).** The three 0.3–0.4 entries (NEAR, UNI, TRUMP) came at
  chair confidence 0.55–0.6, the lowest band; combined −2.11. Yesterday's sizes were NOT uniform either
  ($15.5–$187.3) — yesterday's note was wrong to call them all 0.05; corrected here.
- **Chair verb flips** (trader buy → final sell): 10/33 entries, net +0.09, right 5/10 — no measurable value;
  the one that mattered (151814b) lost.
- **The desk never asked out.** Last verdict before all 28 ratchet flattens = hold (or no holding cycle yet).
  Its repeated holding request was to *widen* the stop — which never takes effect (stop is write-once).
- **Agent 60:** 49 decisions, all hold (30 desk, 19 scaffold); 0 entry verbs → $0. 3 runs idle_retired
  with 12–13 verdicts each. Plan cap 3/3 (3,090 `candidate_skipped`).
- **Mute desk:** agent 6 129/272 decisions verdict-less (47 %); **full route failed 75/78**; 06Z–15Z ≈ 100 %
  mute. `llm_silence` fired silent 20:04Z, recovered 22:12Z, silent 04:29Z, re-alert 10:29Z (email+sms).
  937 `Request timed out` in the worker log (20.5 h). The only entry after 03:36Z was TRUMP 10:35Z.

### 3. Three-axis verification

- **DATA:** −1.645 by four routes (A, B pairing, B plain SQL, all_in tool) within $0.04. Mechanism split
  identical in A and B. Orphan rows re-read by my own SQL (3 lifetime: 09-10, 11-10, 11-11).
- **CODE:** `user_resume` = `trading_runs.resume_run()` hardcoded label; fleet_supervisor `eval_recovered`
  calls it (fleet 44 resumed 151808/151814/151836/151847 at 18:49:38Z) — **no human acted**; label is
  misleading. In the live worker: `_mute_cycles` present, `_null_size_refuse_enabled()` True,
  `_stop_reentry_fence_min()` 30.0. `pnl_audit` replays only run `trade` events (orphan closes have none:
  0 trade events carry an `orphan:` id on prod).
- **ADVERSARY:** "the day lost because of fees" — refuted: fees 1.005, but NEAR alone −3.13 > all 30
  ratchet+trail exits (+2.33). "The handoff cost money" — n = 2, custody lost ~$0.88 vs flattening at the
  handoff mark, but the 07-26 stale-mark rule points the other way; **not actionable at n = 2**. "Raise the
  ratchet arm" — today's replay says the opposite (§5).

### 4. 24-hour re-verification ledger

| item | evidence on prod | verdict |
|---|---|---|
| 11-10 ship record (image 20261110-sweep-20261110) | `.env` + worker + backend on that tag; deploy-log c46a3ff | **HELD** |
| R31 `_mute_cycles` | 4 idle retires, each 12–13 verdicts; zero-verdict idle retires **0** | **HELD** |
| R28 `llm_silence` | 4 transitions, re-alert at +6 h as designed | **HELD** |
| f545d3e #1 null_size_cap | `size_clamp` 0; `null_size_refused` 9 (agent 6) | **HELD** |
| f545d3e #2 stop close-first, gap ≤ 5 bp | `stop_hit` on 4/4 stop closes; **median gap 7.0 bp** (2.7/6.1/7.9/9.2) | **FAILED** in its own terms (was ~15 bp; improved, not to ≤ 5 bp). Gap = 1-min mark sampling; ~$0.11 |
| f545d3e #2b re-entry fence | not challenged (re-entry 6 h 22 m after stop) | NOT YET MEASURABLE |
| f545d3e #3 conviction collapse | none | NOT YET MEASURABLE |
| **7110f54 #4 handoff** | first live case: `positions_held` event same second (18:39:50Z); `orphan_verdict` +6m50s (FIL) / +8m43s (BTC), then ~hourly (6/3) | **HELD (PASS)**; note payload `protected:false` while stop_loss was set — cosmetic |
| R32 ratchet arm (day 2 of 10) | §5: every k > 1 worse; calib median 0.0116 (> 0.01 bar) | day **against**; does not count as calibrated |
| W-post-stop-cycle | 8 runs ran a cycle 1–5 min after stop; 0 fills | OPEN, $0 |
| R29 fleet 43 cap | 3/3, expiry 11-17T21:52Z | OPEN (owner) |

### 5. Ratchet replay (daily, `research/ratchet_arm_replay.py`, 1m, agent 6, n = 25, 2 skipped)

| k | 1 | 2 | 3 | 5 | 10 | none |
|---|---|---|---|---|---|---|
| Δ vs actual (+1.02) | −0.22 | −1.94 | −2.24 | −1.26 | −1.89 | −3.67 |
| Δ ex-largest | +0.25 | −1.01 | −1.31 | −0.33 | −4.68 | −6.45 |

Calibration k = 1: median |sim − actual| 0.0116, max 0.475, Σ sim 0.79 vs 1.02 — just fails the R32 ≤ $0.01
bar. Direction: **against raising the arm** on a day where all symbols fell. R32 tally: 11-10 for, 11-11
against (uncalibrated). Stays STAGED.

### 6. What shipped — `pnl_audit` now counts orphan closes (monitoring tool, $0 money path)

**Hypothesis:** the authoritative P&L tool omits handed-off position closes. **Falsifier:** an orphan close
appearing in a day's ledger. **Result:** 0 run trade events carry an `orphan:` id; 11-11 ledger +0.87 = run
trips +0.856 without FIL −0.473. Reproduced on both handoff days (11-10 −0.49, 11-11 −0.47; Σ −0.96
never reported). Fix: per-day `orphan` (Σ `signals.pnl` of `orphan:%` operation fills whose id the releasing
run journaled — `stop_hit` handoff:true or `orphan_closed`) and `all_in` = ledger + orphan; `agrees`/exit code
unchanged. Manual-user SL/TP closes share the `orphan:` prefix and are excluded (adversarial reviewer's
should-fix, folded in); the 09-10 −0.49 orphan fill predates the handoff journal and is out of scope.
Fail-before 3/5 red; 3 mutations (drop id filter, drop handoff whitelist, accept non-handoff stop_hit) each caught.
Live dry-run on prod: 11-10 all_in −1.10, 11-11 +0.39; ledger/adapt/resid columns identical to the deployed
tool on all 58 days since 09-09. Gate (scratch clone): ruff F-set clean, **5,467 pytest pass**, pip-audit clean,
gitleaks clean; adversarial reviewer (0 blockers; should-fix #1 manual-user ids folded in) + independent verifier
(re-ran tests, fail-before, 3 own mutations, prod dry-run, −1.6451 re-derived) on BOTH revisions. Platform side, NOT fixed: the releasing run's
`realized_pnl_usd` shows only the entry fee (FIL −0.008, BTC −0.020), so run-level P&L also hides the stop
loss — **R36 STAGED** (user-visible; needs its own design).

### 7. Today's solution (AI-first) — STAGED, not shipped

The loss shape: **an outsized entry at the lowest confidence band, then a chair override that re-entered
against the desk's own invalidation.**

- **R34 — size_frac above 0.1 needs a stated edge (desk lesson).** Evidence: 3 entries at 0.3–0.4, all at
  chair conf 0.55–0.6, net −2.11 (n = 3, one outlier; without NEAR +0.65). A/B both days: size does not
  track confidence. *Hypothesis:* capping size_frac ≤ 0.1 unless confidence ≥ 0.7 lowers loss without
  costing wins. *Counterfactual at the live mark (today):* NEAR at 0.1 → −0.92 (save +1.84); UNI 152355 →
  +0.04 (−0.08); TRUMP → +0.13 (−0.39); **net +1.37 today**. *Falsifier:* over the next 7 days the ≥ 0.3
  entries net ≥ the 0.05–0.1 entries per dollar of notional. Not shipped: n = 3 and the skills catalogue
  is at capacity (HANDOFF §10 — a prune must come first). **Promote** at ≥ 10 such entries in 7 days with
  the counterfactual positive with and without the largest.
- **R35 — the chair must not re-enter against the desk's own invalidation.** §8 churn class (c)
  "re-entry against own invalidation" was n = 4, all losers; 151814b makes **n = 5, all losers**, and this
  time the trader had already flipped to buy. *Falsifier:* a class-(c) re-entry that wins. Lesson text
  (chair skill): "If the desk's own outlook declared the plan invalidated, do not override a reversing
  trader back into the invalidated direction; hold." Promote with a catalogue prune in a run that has the
  review budget — the change touches the chair's prompt, a money path.
- **Watch, not act:** handoff custody (n = 2, −0.88 vs flatten-at-handoff); stop-fill gap 7 bp.

### 8. Killed / corrected

- **My −0.65** — corrected to −1.645 (run_id NULL orphan closes).
- **"Yesterday all entries were 0.05 × $375"** (11-10 note) — false: $15.5–$187.3.
- **"user_resume = a human resumed NEAR"** — killed: fleet_supervisor auto-resume label.
- **"Raising the ratchet arm helps"** — against again today (§5).
- **f545d3e #2 "gap ≤ 5 bp"** — FAILED at 7.0 bp (n = 4).

### 9. Health

| check | value |
|---|---|
| containers | worker/backend `20261110-sweep-20261110` up 20 h; admin up; mysql healthy |
| `MAX(run_events.ts)` | 15:12:53Z at 15:13:26Z |
| tracebacks / ModuleNotFoundError / ERROR (20.5 h log) | 0 / 0 / 0 worker; 0 / 0 / 0 backend |
| LLM timeouts | 937 worker; agent 6 47 % verdict-less; full route 96 % failed |
| `/api/health` | 200 |
| fleets | 43 3/3 (plan cap); 44 8 slots, 46 rotations, 72 skips blocked by orphans (BTC 71, FIL 1), 11 `breaker_eval_failed` 18:37–18:48Z (deploy window) |
| FleetPlanner | researched 0, built 0 |
| alembic | 0057 |

### 10. Not verified

- Cause of the 18:37Z `stop_eval_failed` (pre-restart logs gone) — it coincides with the 18:44Z deploy.
- Why adapt `size_mult 0.75` (18:38Z) did not scale the 00:41Z re-entry (A).
- Size source of 3 opens with no size_frac in their order_intent.
- Whether agent cash is debited by orphan closes (user-visible balance) — R36.
- Whether the 18:09Z stop-widen request ever reached `positions.stop_loss` (inferred from the stop that hit).
- Hyperliquid candles vs the simulator's own marks; Binance klines are geo-blocked from prod.
