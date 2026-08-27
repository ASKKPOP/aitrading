# Handoff — Ratchet-Lock Falsifier Monitoring (started 2026-08-27)

**For another session picking this up.** This is a live, in-progress monitoring
watch, not a finished report. Read this whole file before touching anything.

## What this is

Owner order (2026-08-27 ~02:00Z, verbatim): "loop a hour monitoring" → "loop
until my order stop". A session-only cron job (re-armed 2026-08-27 ~10:20Z as `837a8d89` after
the original session's `912b0076` died with it; hourly at :23,
**dies if the session that created it ends, and auto-expires after 7 days
i.e. ~2026-09-03**) has been reporting hourly since ~02:00Z. **If you are
reading this because that session ended, the loop has stopped — re-arm it
if the owner still wants hourly monitoring** (CronCreate, hourly `0 */1 * * *`
is wrong — use `*/60 * * * *`-equivalent, i.e. `0 * * * *`, same prompt as
below).

**MONITOR ONLY — never create/stop/modify fleets, runs, trades, or any DB
row.** This is analysis, never trading (trading is always the daemon's job)
— see `CLAUDE.md` "Automation monitoring sessions" and the Monitoring Rules
block (owner, 2026-08-13, non-negotiable): every outcome needs a REASON, not
an excuse; profit-or-loss is the only goal; never assume your own analysis
is correct.

## The fix being watched

**PR #592 → ed1a5c55, prod image `20260827-ratchetlock`, deployed ~01:55Z.**
Full root-cause writeup: memory [[payoff-ratio-is-the-defect-not-entries]].

One-line summary: measured all 30 `stop_mechanism` fires 08-01→08-27 —
directional win rate 46% (a coin flip, **not** the problem); the ratchet's
old exit rule made its best case **exactly $0 by construction**
(`current_pnl <= exit_fee`), so median give-back was 103.1% of peak and
payoff ratio 0.22. That geometry, not entry quality, explains 40 days of
losses. Fix: `floor = fee_floor + RATCHET_LOCK_FRAC * max(0, peak -
fee_floor)`, default frac 0.5, kill switch `RATCHET_LOCK_FRAC=0` (not set in
prod .env — code default is live).

## THE FALSIFIER — check this first, every cycle

```sql
SELECT e.run_id, e.ts, e.payload FROM run_events e
WHERE e.event_type='stop_mechanism' AND e.ts >= '2026-08-27T01:55:00Z'
ORDER BY e.ts;
```
(query `run_events` by `ts`, **never** `created_at`; use T-format ISO
literals — space-format silently matches everything because `'T' > ' '`
lexically)

For each fire, extract `peak`, `total`, `arm`, `exit_fee` from the payload.
Compute give-back % = `(peak-total)/peak*100`, track running median
give-back and median realized `total` over the **first 30 fires**.

- **PASS**: median give-back < 100% of peak AND median realized positive.
- **BASELINE it must beat** (the old rule, 30 fires 08-01..08-27): median
  give-back 103.1% of peak, median realized −$0.0066, peak/arm median 1.18x.
- **If n reaches 30 and either condition misses**: state plainly the fix
  FAILED, recommend `RATCHET_LOCK_FRAC=0`, do not re-frame the result.

**Status as of 2026-08-27T10:20Z: 1/30 fires — first fire is
PASS-consistent.** Run 2001 (agent 60, fleet 42, TAOUSDT long, entered
10:01Z at 253.49 after the FIRST panel keep since deploy, buy 0.62 kept as
buy 0.62): peak $2.2846, fired at total $1.0877, arm $0.4486, exit_fee
$0.2018 → give-back **52.4%** (baseline 103.1%), realized positive.
Computed new-rule floor = 0.2018 + 0.5×(2.2846−0.2018) = $1.2432; the fire
overshot it by $0.156 because uPNL fell 2.28→1.19 in one ~70s tick (cadence
cost, watch whether overshoot grows with n). Counterfactual old rule
(ride to ~exit_fee) ≈ +$0.20 → this fire saved ≈ $0.89. NOTE: payload
`total` deducts only the entry fee (same convention as the baseline, so the
comparison is valid); all-in net after the exit fee ($0.1009) = **+$0.987**.
The run was STOPPED entirely by the trailing lock (not just flattened).
Running medians (n=1): give-back 52.4%, realized +$1.0877 (payload basis).

## Why nothing is entering (verified, not assumed)

Two paper accounts, desk = local gpt-oss for both, only the panel differs:
- **A** = info@askkpop.com (user 5, agent 6, fleet 41, panel = Claude
  opus-4-8, $10,000 book)
- **B** = forevery1969@gmail.com (user 25, agent 60, fleet 42, panel =
  local gpt-oss, ~$100,000 book)

As of 10:20Z: 489 decisions since deploy (A 214, B 275). 19 proposals
reached a panel (A 7, B 12). **18 demoted, 1 KEPT** — the first keep
(run 2001, 10:00:59Z, buy 0.62 → buy 0.62) became the falsifier's first
fire above. Demotion rationale pattern unchanged ("no expressible edge",
"preserve capital until a clear breakout"). This is the **sizing/noise
deadlock** the prior 5-lens round identified, not a panel outage: at 13
slots × ~$180–$466 machine size, no stop can sit outside crypto's ±2–3%
noise band, so panels correctly cannot defend an entry. See remaining
levers below — this is lever (4).

## Access

```
ssh -i ~/shell/sierrabiolab/sierrabiolab-aws.pem ec2-user@52.9.147.202
CREDS=$(grep "^DATABASE_URL" /home/ec2-user/sooppiy/.env | sed -E "s|.*//([^:]+):([^@]+)@.*|\1 \2|")
U=$(echo $CREDS | cut -d" " -f1); P=$(echo $CREDS | cut -d" " -f2)
docker exec noesis-mysql mysql -u"$U" -p"$P" sooppiy -N -e "SQL"
```
Traps hit this session: `signals` has no `action`/`price` column (use
`signal_type`, `entry_price`/`exit_price`); `positions` has no
`status`/`unrealized_pnl` column (open rows just exist — filter by
presence, compute uPNL from `current_price - entry_price`).
`signals.timestamp` is epoch seconds; `signals.pnl` deducts **only** the
entry fee — all-in P&L needs both legs.

## Health checks (every cycle)

- `docker logs --since 2h sooppiy-worker/sooppiy-backend | grep -ci traceback`
  — must stay 0.
- `order_discussion` events: `"final":{"action":"hold"...}` = demoted,
  `"reviewed_by":"local-fallback"` = local stepped in (post-#591), an
  `"error"` verdict = fail-open, which post-#591 is a **new bug** — alert.
- Other falsifiers still tracked: trail (fee-anchored activation, PR #589)
  2/20; day_digest no-verdict rate must not regress from 0.69%(A)/0.19%(B);
  panel local-fallback 0/20.
- Recompute keep/demote counts fresh each cycle — never propagate a running
  mental tally (caught a bug earlier this way).

## Alert thresholds (report immediately, don't wait for the hourly digest)

Either account realized ≤ −$50; any traceback; single trip loss > $10
(fleet 41) or > $100 (fleet 42); a `mark_drift` kill; panel fail-open
errors > 0; ratchet falsifier trending to fail as n grows.

## EXPERIMENT: slot consolidation (owner-ordered 2026-08-27 ~21:30Z)

Owner order (quoting the proposal back verbatim): consolidate slots
(13→3–4 as proposed; live fleets actually run n_runs=25) and run the
zero-intelligence control in parallel. Conflict disclosed and accepted:
research 07 §12.3 rejected "slot consolidation now" premised on the 0.22
payoff (since addressed by #592) and a stopped fleet (since restarted).

**Pre-registered hypothesis H-CONSOL** (stated BEFORE the change): the
entry deadlock is caused by slot size. At ~B/4 per slot:
- P1: panel keep rate over the NEXT 20 panel discussions on the resized
  fleets rises from 3.4% (2/59) to **≥15%** (the §12.2 gate figure).
- P2: kept entries carry desk stops ≥2% of price (outside the ±2–3%
  noise band that authored the deadlock).
- FALSIFIED if P1 misses over 20 discussions at the new size → sizing was
  not the binding constraint; revert to n=25 and the cause moves to
  desk/panel logic itself. State it plainly; do not re-frame.

**Method** (built paths only, no new code): stop fleet (flatten; both
fleets flat at decision time) → create fresh fleet n_runs=4, same budget →
start. A resize-down alone is WRONG here: the drain keeps survivors'
original small allocations (fleet_supervisor._slot_pass deletes emptied
excess slots, never re-allocates) — only a fresh build allocates B/4.

**Risk bounds (supersede the old per-trip alert thresholds):**
- Fleet A ($10k, 4 slots ≈ $2.5k, max_bet ~$1k, 2x → ~$2k notional):
  per-trip loss alert $60; REVERT (resize back / stop) if fleet equity
  −3% from experiment start or 5 consecutive losing trips.
- Fleet B ($100k, 4 slots ≈ $25k, max_bet ~$10k, 2x → ~$20k notional):
  per-trip loss alert $600; same −3% / 5-consecutive revert.
- Ratchet falsifier continues unchanged (fires at the new size count
  toward the same 30; note size regime per fire).

**Zero-intelligence control (W2, in parallel):** offline replay per
research 07 §12.2(1): random-entry-at-matched-kept-rate with IDENTICAL
rails/fees vs the AI's actual entries 08-01→08-27, ≥1,000 draws,
bootstrap 90% CI, regime-stratified, both fill bases (0.03%/0.16%).
Verdict criteria pre-registered in the script itself before first run.

**Status (OWNER 2026-08-27 ~21:25Z): execution is NOT this session's job.**
Verbatim: "must be verification from sooppiy.com after deploy (not this
session), we just monitoring fixing that." → This session attempted the
API path once (blocked by the permission classifier, correctly) and STOPS
there. The consolidation happens on sooppiy.com by owner action / the
normal pipeline. This session = MONITOR ONLY, re-affirmed.
Second owner order (same window, verbatim): "do not do any action by
you, must be do by desk" — EVERY action on the book belongs to the
sooppiy desk/daemon, never to a session. This extends the standing law
(§7b: the AI is the final author of every order; memory: build the path,
don't patch the row). A session's outputs are: monitoring, verification,
analysis artifacts, and code shipped through the normal pipeline — the
desk executes everything on the book.

**FINAL OWNER CLARIFICATION (2026-08-27 ~21:55Z, superseding the
~21:45Z reading):** "this session not any action for order, but must be
fix, and planning, implement & monitoring." → Correct division of labor:
- This session must NOT act on the BOOK (no trades, no live-fleet API
  mutations — the desk/platform executes everything on the book).
- This session MUST fix, plan, IMPLEMENT (code → tests → local CI →
  deploy to prod), and monitor. The consolidation ships as platform code
  the desk's own machinery executes (supervisor/auto-tune), env-gated.

Hand-over state for whoever/whatever implements it:
- ZI control: complete offline run exists on local branch
  `feat/throughput-experiment` (worktree ai-trade-wt-throughput,
  commit 52f8d0b7 — script, cohort, result JSON; verdict INCONCLUSIVE
  at realistic fills / AI ≈ random; even long-only random loses at
  current slot size). Unpushed by order; take it or re-derive.
- Consolidation mechanism notes (verified this session): resize-down
  drain (fleet_supervisor._slot_pass) deletes emptied excess slots but
  NEVER re-anchors survivors' budgets — a fresh build at n_runs=4 (or a
  replacement-funding re-anchor to B/n) is required for slots to
  actually get ≈B/4. Whoever implements must handle this or the
  consolidation is cosmetic.

**Monitoring additions from this point (every cycle):**
- Watch `fleets` for the consolidation landing: a new fleet (or resize)
  with n_runs ≤ 4 for agent 6 and/or 60, or fleet 41/42 leaving `active`.
- When it lands: stamp H-CONSOL t0 = new fleet's started_at; then judge
  the PRE-REGISTERED falsifier from prod data only — P1 keep rate ≥15%
  over the NEXT 20 panel discussions on the new fleet(s); P2 desk stops
  ≥2% on kept entries; alert bounds per-trip $60 (A) / $600 (B); revert
  recommendation at fleet equity −3% or 5 consecutive losing trips.
- Report each verdict in profit-or-loss terms first; the ratchet
  falsifier (1/30) continues unchanged in parallel, size regime noted
  per fire.

## ZI CONTROL — FIRST RUN COMPLETE (2026-08-27 ~22:00Z)

Script: `research/zi_control_replay.py` (worktree branch
feat/throughput-experiment; criteria pre-registered in the docstring
BEFORE any candle was fetched). Cohort: all 57 closed crypto trips
08-15→08-27, ledger NET −$6.60 (AI side = real fills, never simulated).
1,000 draws, symbol+notional matched, coin-flip side, house rails
(1.5%/4.5% + #592 ratchet), OKX 5m candles.

**VERDICT: INCONCLUSIVE by pre-registration** (needed both fill bases):
- Realistic basis (0.03% slip): AI at the **63.7th percentile** of random;
  CI90 of mean trip diff [−0.31, +0.46] — includes 0. AI ≈ random.
- Worst-case basis (0.16%): AI at 88.7th pct; CI90 [+0.08, +0.90]
  excludes 0 — but this basis mostly charges random more slippage than
  the AI's paper fills paid; not evidence of timing/direction edge.

**Secondary findings (stronger than the headline):**
1. **Everything loses at this size** — even LONG-ONLY random in a window
   where BTC rose +22.7% then +3.5% nets −$4.24 (0.03% basis) after
   rails+fees. The house geometry at $180–770 notional is negative-EV
   for pure beta. This is direct experimental support for the sizing
   consolidation (H-CONSOL) — the deadlock is structural, not the AI.
2. **Regime split**: strong-trend half AI +$5.35 vs ZI −$4.30; quiet half
   AI −$11.95 vs ZI −$6.78. Sign flips across halves — consistent with
   the trip-1/-2 carry-forward hypothesis (with-trend wins, counter-trend
   loses). n too small to gate anything.
3. Largest-contributor strip: AI ex-worst-trip = $0.00 vs ZI −$11.0 —
   one −$6.60 trip is the entire AI net.

Artifacts: `research/ai_trips_20260815_27.json`,
`research/zi_control_result_20260827.json` (seed 20260827,
reproducible). Basis caveat on record: AI = prod paper fills, ZI = OKX 5m
closes (the known candle-vs-fill trap) — the 0.03% row is the
like-for-like read.

## Trip 2 — run 2019 LITUSDT short, LOSS −$0.545 all-in (closed 14:11:52Z)

Not a falsifier event (never profitable, ratchet never armed — count stays
1/30). Two-agent analysis dispatched 14:45Z; cross-checked verdict appended
when returned. Facts established from tape + worker log:

- Entry 12:51:39Z short 9.869 @ 3.4031 ($33.6 notional, 2x), keep #2 —
  panel kept sell 0.58 after DEMOTING sell 0.59 on the same run 14 min
  earlier (lower confidence kept, same ambient state). Desk authored FULL
  params this time (params-absent flag did NOT repeat; run 2001 stays n=1).
- Desk-authored arm (price_above 3.45 → reduce 50%) executed 13:21:43 @
  3.4587, slippage 0.25% past the level — second cadence-lag datum after
  trip 1's $0.156 ratchet overshoot. Realized −$0.282.
- Stop 3.44999 hit → ROUTED to desk; desk ruled HOLD 13:25 (thesis 0.78,
  invalidation 3.52). 46 min later three more routings (14:10:16→14:11:20)
  went unanswered; 14:11:52 routing TIMED OUT → watcher fail-safe closed
  @ 3.4518 (0.05% past stop). Realized −$0.248. Cycle 6 arrived 14:14 —
  2 min late — calling the same breach "thesis failure; close".
- Run left "running" after the loser exit (vs trailing_lock STOPPING run
  2001 after its winner) — asymmetry to characterize. Adapt penalties
  size_mult 1.0→0.75→0.5, loss cooldown active.
- Running 2-trip net since deploy: +$0.99 − $0.545 = **+$0.44**.

## Trip 2 two-agent analysis — cross-checked verdict (15:00Z)

Loss −$0.545 all-in. Author chain, each with its reason (no excuses):

1. **Root author: the desk's counter-trend entry.** Cycle-1 scores said no
   (momentum 0.3, entry 0.2, panel demoted); 14 min later, on a −0.15%
   price change, the scores DOUBLED (momentum 0.55, entry 0.51) and the
   sell went through. Scores moved with no new information — they fit the
   verdict rather than deriving it. The short fought a flagged market-wide
   up-leg the same fleet's TAOUSDT long had just profited riding; the
   position was never positive (max favorable −$0.07).
2. **Damage control (desk arm): worked.** The self-authored reduce at 3.45
   cut half at −$0.28. Cadence cost $0.043 (0.252% past the level) — 2/2
   triggered exits now pay 0.15–0.25% to scan cadence; per-fire cadence
   cost is a tracked metric from here (kill: median < half the fee floor
   over next 20 fires ⇒ immaterial).
3. **The desk's stop-override HOLD (13:25): state-inconsistent output.**
   Thesis 0.62 at entry → 0.78 AFTER the stop hit → "thesis failure" at
   ~the same price at 14:14. Ex-post the HOLD cost ≈ nothing (+$0.02 vs
   closing at ruling time) — luck, not vindication; tail risk to
   invalidation 3.52 was −$0.34 more.
4. **Final order author: the 180s fail-safe, not the AI.** Resolved from
   code+tape (snapshot C3 mechanism, risk_engine.py:602): routed stop
   dispatches a desk cycle via the cooldown BYPASS; episode (a) LLM
   answered in ~3 min < 180s (desk ruled), episode (b) took ~5.7 min >
   180s (fail-safe closed @ 3.4518, 0.05% past stop — good fill; ruling
   arrived 2 min after death). The desk authors the exit only when the
   local LLM wins a 180s race. Ties to the 08-17 llm_usage
   oversubscription finding.
5. **Structural characterizations (no proposals, no experiments yet):**
   winner-exit retires the run (2001) while loser-exit keeps it trading at
   0.5× (2019) — momentum-inverted by construction, n=1 per branch;
   adapt penalties shrink size after losses with no symmetric growth after
   wins — compounds the payoff-ratio defect direction.
6. **Panel record after 3 actions: 0 demonstrated discrimination.** Both
   keeps are rubber-stamps (proposed==final); the one demote was the
   HIGHER-confidence twin of a kept proposal (order-inversion). The
   "regime recognition" hypothesis has no supporting instance; not dead
   at n=3.

**2-trip net since deploy: +$0.44 — INCONCLUSIVE** (strip trip 1 and the
sign flips; experimental-mindset rule). Carry-forward falsifiable
hypothesis for next trips: with-trend entries profit, counter-trend
entries lose, panel provides no discrimination.

## Fire n=1 two-agent analysis — cross-checked verdict (10:30Z)

Dispatched per the law; both reports cross-checked, none rejected. Findings:

- **Falsifier metric (pre-registered): PASS-consistent at n=1.** Give-back
  52.4% (baseline 103.1%), realized positive. Cadence overshoot: fired
  $0.156 BELOW the computed floor $1.2432 (uPNL fell 2.28→1.09 in one ~70s
  tick) = 6.8% of peak lost to tick granularity. **Track (floor −
  fire_total) as a distribution across the 30 fires** — if median overshoot
  exceeds ~20% of the locked increment, cadence is eating the fix.
- **Counterfactual is path-dependent, NOT a measured save.** Earlier claim
  "saved ≈ $0.89" was wrong as a point estimate. Measured at 10:19Z: TAO
  $256.0 > exit 254.84 — the old rule would still be HOLDING ≈ +$2.11 paper
  vs the new rule's banked +$0.99. But the old rule's own mechanism can
  only ever bank ~$0 (best case by construction), and this run had no
  desk-authored target to convert paper into cash. n=1 inconclusive on the
  counterfactual; the falsifier's medians are the only decision criterion.
- **Root finding (both agents converge from opposite axes): the desk
  ABDICATED the bracket.** Deployed code (ed1a5c55, run_engine light path)
  DOES ask for stop_pct/target_pct on light route; decision JSON contained
  no order block → params_state absent → (a) null_size_cap clamped size
  265.6→111.37 and (b) exit authorship fell entirely to the platform
  ratchet. The profit's author was market beta (desk's own
  momentum_quality score was its LOWEST, 0.5) locked in by #592 geometry —
  not desk skill. Watch whether params_state=absent repeats on future
  kept entries; if it does, that is the next defect, not the ratchet.
- **Panel keep added zero information** (proposed buy 0.62 == final buy
  0.62; only distinguishing feature vs the 18 demotions = a nameable
  market-wide up-move with psych_shock flags). n=1 cannot separate "panel
  recognizes momentum regimes" from "filter leaked one through".
- **Run-stop semantics flag:** trailing_lock STOPPED run 2001 entirely, not
  just the position — a winner retired by its own lock. Structurally
  questionable but NO change without an experiment (owner 08-17 rule);
  first measure replenish latency and post-stop TAO tape.
- **Named disagreement (the finding, per law):** Agent A: "52% give-back on
  even a winner is the actionable signal" vs Agent B: "52% vs 103.1% is the
  fix working". Both true; whether frac=0.5 + cadence overshoot captures
  enough is exactly what the 30-fire sample decides. Do not resolve it
  early in either direction.

## Two-agent outcome analysis (owner law, non-negotiable)

Dispatch **only when there is new closed-trade tape** (there is none yet).
Agent A analyzes every AI-authored outcome (desk cycles, panel finals,
armed exits) and which AI authored it. Agent B analyzes every
algorithm-authored outcome (SL/TP watcher, trailing/ratchet lock, max_loss,
at_time, adapt-retire, flattens, sizing/selection). Cross-check both against
the owner's law — reject any finding that excuses a loss, assumes its own
correctness, or lacks a per-trade reason. Where they disagree, the
disagreement is the finding, not noise to average away.

## Remaining levers, ranked (not yet ordered — offer, don't act)

1. **Unreachable targets** — desk authors median target 4.80% of notional;
   the all-time best moment across the whole sample was 0.97%; 0 of 73
   futures trades ever reached target.
2. **Zero-intelligence control** — doc 07's decisive unrun experiment
   (would isolate whether entry logic adds any value over random entry).
3. **Fee hurdle** — fees are 27–28% of gross; argues for fewer, larger,
   longer trades.
4. **Sizing deadlock** (the one currently binding, per above) — 13 slots ×
   $769 avg can't fit a stop outside ±2–3% noise.

## Methodology lesson from this session (don't re-learn it)

Two agents analyzing the same Claude-vs-local A/B reached opposite
conclusions because they stripped different things. Stripping by SYMBOL
left one fleet's demotions looking robustly wrong; stripping the
CORRELATED EVENT (9 proposals inside one 4-hour crypto down-leg, several
re-proposals on the same run) flipped the sign. **Strip correlated event
clusters, not just repeated symbols** — effective independent n was ~13,
not 22. Full writeup: memory [[ab-panel-experiment-inconclusive]].

## Rules that bind every cycle

- Query `run_events` by `ts`, never `created_at`.
- English first, Korean second, in every report.
- Never any form of address (no name, no 사장님/대표님/boss/sir).
- MONITOR ONLY.
- Implement only on an experimental result — CLAUDE.md "Rule of Analysis &
  Monitoring", owner 2026-08-17.
