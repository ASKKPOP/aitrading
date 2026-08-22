# Full Logic Audit — Why the Current Trading Logic Cannot Profit (2026-08-22)

**Owner order (2026-08-22): stop monitoring; audit all trading logic; the current logic is not usable.**
This document is the result: five parallel audits (P&L forensics, entry pipeline, exit rails,
learning loop, strategy economics), cross-checked against each other and against two independent
verification passes by the synthesizing session. Every claim below carries its n; hypotheses that
were killed are named. Read this before designing anything new.

## 1. Verdict

The owner's conclusion is **confirmed by the ledger**:

- **The old logic (through 08-14) reliably lost.** Lifetime realized P&L of the current account
  generation: **−$175.30** (373 fills, 274 closed legs; first fill 2026-08-12). Triple-verified
  (pnl_audit ledger replay −175.30 / independent fill replay −175.29 / equity-curve deltas −175.28).
  The loss is robust: removing the biggest winner, the biggest loser, or the entire 08-13 size-bug
  day never flips the sign (−$30.90 even without the bug day).
- **The cleaned-up logic (08-15 onward) is statistically zero.** +$5.63 over 6 days on a ~$110k
  book (−$0.03 stripping the best day; one FIL leg is 64% of the profit) — then **zero trades at
  all** from 08-20 07:10Z onward.
- **The current logic's expected profit is $0 by construction**: it no longer enters. A system
  that cannot lose also cannot pay.

## 2. Where the money went (P&L forensics)

- 55% of the lifetime loss is **two trades on 08-13**, both authored by sizing: run 1099 SOLUSDT
  (desk averaged down a short 6× into a rising price, two adds at the extinct 2.5× size-bug scale,
  −$60.6 net) and run 1159 SPCX (single $3,317 oversized entry, −1.07% ordinary move = −$35.8).
  The rails (max_loss, adapt-retire) capped these losses; they did not cause them.
- **Structural defect independent of any bug:** average win $0.42 vs average loss $1.89 —
  payoff ratio **0.22** at 51.1% win rate (n=274). That is a losing machine by arithmetic.
- The only net-positive components in the whole system were **mechanical exit devices**
  (armed exits +$1.09, trailing/at_time cyc buckets +$17.15).
- Fees: $24.97 total = 37.5% of gross wins (47% in the post-fix era). Small versus the losses,
  large versus the microscopic wins.

## 3. Why entries died (entry pipeline + learning loop)

**Correction of record — the 08-13→08-14 cliff root cause.** The previously suspected PRs
(#426/#416/#424/#422) are **cleared by timing** (merged ~22h after the cliff hour). The cause is
**#413 + #414 (merged 08-13 21:35Z / 22:55Z): the 4-analyst order-discussion panel became the
final author of every order.** Since then the light desk still proposes entries at volume, and the
panel demotes them:

- Since 08-14: **611 buy proposals → 11 kept (1.8% survival; 585 demoted to hold)**;
  300 sell proposals → 59 kept (19.7%) — hence 86% of executed entries were shorts.
  (Verified twice: subagent measurement + independent session query, identical counts.)
- The asymmetry is structural: only would-trade proposals are ever reviewed; a hold is never
  challenged.

**The 08-18 collapse (#484 reachability disclosure) compounds it at both stages**: light-desk buy
proposals fell 105–118/day → 17/day (z=4.43), and panel buy survival fell 2.6% → 0.4%, because
#484 put the discouraging line into the panel's prompt too — as its first line.

**The discouragement is not one line; it is a doctrine class delivered through ≥4 always-on
channels**: the reachability record line, recall's static skill atoms ("if you cannot name a stop
and a target, you are not confident enough to open"), `_ordinary_day_line`, `_entry_rail_line`,
the 48k skills wall ("when flat and the read is unclear, holding costs nothing"), and a hard-coded
loss anecdote (`predecessor_run`) rendered on 82% of decisions. Across everything the entry-side
AI reads, **pro-entry content is zero — every entry-relevant lesson is a veto**, and no line ever
prices the cost of not entering.

**The doctrine's numbers are also wrong (R30 denominator bug, still live):** the reachability
record shown to the AI divides a single-moment peak by the cumulative notional of every entry leg
over the run's life, understating the true best-move ceiling by ~47% (us-stock) and ~57% (forex).
The AI is told the market moves roughly half as much as it actually does.

**Mechanical gates are not the constraint**: fee-edge, confidence-rank, and R:R-floor gates fired
0 times in 14 days; all mechanical gates combined blocked ~48 orders while the LLM verdict chain
produced ~5,030 holds.

**Killed hypotheses (by name):** corpus-feedback suffocation via recall (flat cycles had no read
path until 08-20, two days after the collapse — REFUTED); DESK_RECALL_FLAT as the killer
(actionable was already 0 before the flip — REFUTED); candidate drought (research supply steady,
both fleets full-board while holding — REFUTED); model switch (llm stamp unchanged — REFUTED);
"the cliff was an assessment change" (primarily an action-authorship change: the panel's scores
entered the tape — CORRECTED).

**#508 (DESK_REACHABILITY_AB) is invalid and should be ended.** Two independent defects:
(a) `analysis_agents.py:603-604` renders the reachability line with no run_id/arm check, so the
final author sees it in both arms the moment a cycle escalates; (b) the same doctrine reaches
control-arm runs through the other channels — control runs were observed quoting the treatment's
own numbers ("~68% of cases"). 0 entries in both arms is the expected null of a contaminated
experiment and refutes nothing. Waiting on this readout was a mistake; nothing is gated on it
anymore.

## 4. The exit layer (rails)

- **The loss-side rails protect value; they are not the leak.** Every counterfactual replay ran
  in the rails' favor: at_time force-closes 2/2 saved money (holding walked to the plan's own
  stop); idle-retire 5/5 — the retired theses would have lost −$65.88 in total (sign robust to
  stripping the largest). Owner's law applied: a forced close only costs money if holding would
  have paid; none would have.
- **The win side has no working machinery — this asymmetry is the exit layer's real defect.**
  The classic trailing lock structurally never arms (activation threshold = 1.0× max_loss_usd,
  $8–45, vs observed run peaks $0.03–6.6); `profit_target` is unreachable by construction
  (budget-scaled target on bet-scaled positions; 0 fires in 485 stops). The only mechanical
  profit exit that engages is a breakeven ratchet whose best case is $0 — and 5 of its last 7
  fires booked small losses under the `trailing_lock` label (label hygiene: two mechanisms share
  one reason string, corrupting outcome analysis).
- Three overlapping executioners on the loss side, none engaged on the win side → the measured
  0.22 payoff ratio is partly built into the exit design.
- **One integrity risk remains**: run 1099's −$69.56 on a $44.23 cap came from a zero-quantity
  positions stub that blinded max_loss, the add guard, and the underwater block simultaneously.
  The consolidation fix shipped 08-13, but correctness still depends on a single code path —
  there is no DB-level UNIQUE index on (agent_id, market, symbol, run_id).
- **Simulator boundary confirmed**: all fleet trading routes exclusively to the simulated ledger
  (`execute_paper_trade`, account_type "simulator" hardcoded); `automation_configs` has 0 rows,
  so the live router is never invoked.

## 5. The economics — why the design cannot pay even without bugs

1. **The selection variable carries no information.** Entries are admitted assuming 25% of the
   claimed move gets realized; measured realization is 0.5–6% (4–50× optimistic). Correlation of
   target vs realized move r²=0.024; 0/36 legs ever reached their own target.
2. **Horizon mismatch 5–15×.** Theses are priced for 33–47h moves; positions are held 2.1–7.8h.
   Forex is terminal: entry requires a claimed 0.60% move; across 62 real forex holds the
   maximum move ever realized was 0.47% — every forex entry was admitted on a promise the market
   has never delivered inside the holding window. Forex in-direction edge: +0.0036% ≈ zero.
3. **The profit inequality is violated in all four markets** (WR×avg_win < (1−WR)×avg_loss by
   2.3–4.4×, 30d). The post-fix window repairs it but only at probe size, outlier-dependent.
4. **Size is microscopic and behavioral, not platform-capped.** Design permits ~$280 risk/trade;
   the desk pins size_frac at the 0.05 floor → $1.4–2.4 actual risk, median trip $52. At measured
   post-fix expectancy (+$0.13–0.17/trip) a $50/day target needs 300–380 trades/day; the
   best-ever funnel produced ~35 entries/day (~$6/day theoretical ceiling). Off by 100–300×.
   The only at-scale sample (n=26, >$800 notional) is negative — scaling by fiat is unproven.
5. **Below the gates there is no hidden profit.** Declined-entry replay: mean +$1.87 flips to
   −$1.02 without the single best winner; median −$2.27 (6/15 winners). Loosening gates buys
   losing trades. (This is the table the owner saw; the refusals were mostly correct — the defect
   is that almost nothing worth taking is generated.)

## 6. What is NOT broken (do not redesign these)

- **Fees.** FEE_PER_MARKET=true is live; the legacy 2.40% flat-fee hurdle is dead. Current entry
  hurdles: crypto ≥1.08%, others ≥0.60% claimed. 94% of actual trades cleared their own
  round-trip fee. No fee-model change needed.
- **Research/candidate supply** — steady at 1,000–2,300 theses/day; R33 (regime screen wrongly
  enforcing an advisory verdict) was the one research-side killer and is already fixed (#513).
- **The "5-pip forex absurdity"** — no longer reproduces; the 0.30% rail floor fixed it.
- **Loss-side rails** (max_loss, at_time, idle-retire, adapt) — replay-verified value-protecting.
- **The simulator/live boundary.**

## 7. Redesign requirements — each with its proving experiment (no gate-loosening anywhere)

Ordered by information value:

1. **Counterfactual replay of the panel's 585 demoted buys** (paper-walk each to its own
   stop/target/horizon). This single experiment decides the fork: if demotions were right, the
   entry *generator* is the defect (no alpha) → work on selection; if they would have paid, the
   panel's context/doctrine is the defect → work on the prompt stack. Everything else sequences
   behind this answer.
2. **Horizon reconciliation** — replay closed legs on 1-min candles: "was the target hit within
   the horizon the desk wrote?" If yes → the exit policy (at_time/arm precedence) is the leak;
   if no → LLM targets are decoration and must be replaced by ATR-of-hold-derived brackets.
3. **Rebuild the win-side exit layer**: trailing activation scaled to the position (not
   max_loss_usd); profit target scaled to the position (not the run budget); separate reason
   strings for breakeven-ratchet vs classic lock.
4. **De-duplicate the doctrine, then test it honestly**: fix R30's denominator; dedupe repeated
   skill atoms (exit-discipline #4=#6=#7); author symmetric when-to-enter content; make
   `analysis_agents.py` reachability arm-aware; then A/B the doctrine *class* (all channels),
   not one line. End #508 now — it is unreadable.
5. **Sizing ladder** — 1×→3×→10× median notional ($52→$520→$5.2k), sign measured at each rung
   before the next; explain the negative >$800 cohort before any 100× claim.
6. **Forex: drop it or re-horizon it** — replay forex theses held to full horizon; if edge
   appears the problem is #2; if not, remove forex from fleet scope.
7. **Fix the direction-blind candidate expectancy gate (R26)** — short-aware replay; measure the
   candidate-universe delta.
8. **DB invariant on positions** — UNIQUE index or SUM-based reads, so no future write path can
   re-fragment a book (run-1099 class).
9. **Kill the retire→cooldown→rebuild treadmill** (299 idle-retires of 485 stops; 175/7d on the
   current fleets) — it taxes fleet 38's occupancy and mass-produces the 73.5% "never traded"
   corpus that any future learning system would train on.

## 8. Corrections to standing beliefs (recorded so no session re-runs dead theories)

| Old belief | Status |
|---|---|
| "Flat fee needs ≥2.40% move" | DEAD — per-market fees live since ~07-28 |
| "08-13→08-14 cliff unexplained; suspects #426/#416/#424/#422" | SOLVED — #413/#414 panel authorship; suspects cleared by timing |
| "Reachability disclosure (#484/#505) is the collapse's cause" | PARTIAL — it is the 08-18 trigger, but one channel of a redundant doctrine class; removing it alone is not a treatment |
| "Recall corpus teaches the desk to hold (suffocation)" | REFUTED — no flat-cycle read path existed before 08-20 |
| "#508 A/B will answer the reachability question" | INVALID — contaminated in design (panel un-gated) and in substance (doctrine redundancy) |
| "Platform caps deployment at ~8.9%" | NOT REPRODUCED — the binder is the desk pinning size_frac at the 0.05 rail floor |
| "Forex plans are 5-pip absurdities" | REFUTED on current tape — rail floor fixed it |

Provenance: five subagent reports (2026-08-22), prod MySQL read-only, pnl_audit ledger,
origin/main @ 3943c640. Synthesis cross-checks: #413/#414 merge timestamps and the 611→11 panel
matrix re-measured independently by the synthesizing session; all inter-agent numeric
discrepancies reconciled (−175.30 total vs −162.82 close-leg-only = open-side fees).
