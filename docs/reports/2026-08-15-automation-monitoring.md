# Automation monitoring — 2026-08-15 (UTC day), newest-first

Loop RESUMED by owner 01:34Z after the 2026-08-14 23:3xZ stop. Crons re-armed:
30-min cycle `4ade12c3` (`13,43 * * * *`), 24-h sweep `71d7c9ce` (`7 8 * * *`).
Live fleet is **34** (forevery1969@gmail.com, user 25 / agent 60) — the Plan 25
Phase D v2 cohort, created 00:12:28Z. See `2026-08-15-plan25-phase-d-baseline.md`
for the v1 bar this fleet must beat.

---

## Cycle 28 — 16:4xZ (anchor 16:40:34): quiet — one hold, flat

---

## Cycle 27 — 16:2xZ (anchor 16:25:31): quiet — UNI out of loss cooldown, all flat

---

## 24-HOUR SWEEP — 15:3x–16:0xZ (window 08-14 15:35Z → 08-15 15:35Z): adversarial re-proof of the day

### Ships re-proven in the RUNNING container (single cumulative image `20260815-one-invalidation`, 0 tracebacks)
Every fix grep-verified live: #439 `_cooldown_blocks`/`begin_ruling` ✓,
#440 `min_size_frac`+`_dust_floor_usd` ✓, #441 discard note ✓, #443
`_reduce_geometry_line` ✓, #444 + fee-drag + path-coherence skills ✓
(and render-verified via live `skills_block`), #436 `_VOLUME_CANDIDATES=60`
✓, #432 `_RECALL_KINDS=(outcome,lesson)` ✓. Six PRs merged+deployed in
the window: #439 #440 #441 #442 #443 #444.

### Behaviour over the day — what each fix ACTUALLY did (adversarial)
- **PROVEN at scale**: #438 briefs on 100% of decisions since fleet-35
  birth (0 missing of ~180); #432 recall — 41 recall events, lesson
  chunks visibly served (FIL entry quote, UNI exit).
- **PROVEN n=1 but decisive**: #440 fired EXACTLY ONCE (UNI 11:53) —
  and that one raise created the fleet's first position and its first
  win path. **Correction to my own cycle-13-era tally: the "5 floor
  raises" count was a contaminated grep** (trail-arm floor notes
  matched); the true #440 count is 1. R15 bracket gate exercised
  (KAITO refused at $561, admitted at $1,000). #436 built the fleet
  from 24 candidates (n=1 build).
- **UNEXERCISED — deployed but no occasion, say so plainly**: #439 (0
  stop hits in 24h, zero stop_router events), #441 (no post-deploy
  discarded non-hold), #443 positive render (no held book since 14:50;
  negative case proven), #437 size pin (owner never resized;
  user_size_cap NULL), #434 stop-hit brief (no stop hits). These are
  code-verified, behaviour-pending — not "working", not "failed".

### True 24h P&L (pnl_audit, flatten-reconciled, resid 0.00 both frames)
- **UTC 08-15: ledger −$3.26** (fee asym −0.84 explains ledger−adapt
  fully). Decomposition: fleet 34 (agent 60) −$2.50 (ETH −1.43,
  SOL −1.32, BTC orphan −0.17, FIL +0.42); **fleet 35 (agent 6)
  +$0.08** (UNI −0.086, FIL +0.169); pre-reset NQ in KST segment.
- **KST day 08-15 (08-14 15:00Z → 08-15 15:00Z): −$5.44** (adds the
  08-14 evening wind-down segment, dominated by the NQ flatten −2.15).

### SHAPE of wins and losses
Wins: floor-scale desk scratches banked before bounces (FIL +0.17,
fleet-34 FIL +0.42) — small, fee-heavy, real. Losses: (a) fleet 34's
fee-churn pattern — ETH entered LONG after three straight cycles of
"conflicting inputs / preserve capital", scratched half at entry price,
closed −0.2% lower; **fees were 62% of the ETH loss**; (b) wind-down
flattens (NQ −2.15, BTC orphan −0.17) — owner-ordered, not strategy.
The monitored fleet (35) finished its first day NET POSITIVE with
visibly better process than fleet 34's tape.

### Gap admitted (no excuse): fleet 34's final closes (ETH 1272,
SOL 1274, BTC 1271) received NO two-agent review — the owner reset and
target switch arrived mid-morning. Their visible shape (fee churn on
conflicted entries; "loss exceeds house floor" exits) is the same class
today's shipped skills target. Fleet 34 is stopped; no continuing
exposure; the skills apply platform-wide to every future fleet.

### Owner obligation — TODAY'S LOSSES → TODAY'S SOLUTIONS (all shipped, not described)
- UNI −$0.095 → path-coherence skill (#443), fee-drag-truth skill
  (#443), reduce-geometry line (#443), one-invalidation (#444) — all
  DEPLOYED and render-verified same day.
- Fleet-34 fee churn → the same fee-drag + path-coherence lessons are
  in every future desk prompt; the fleet itself is owner-stopped.
- Structural entry stall (would have kept fleet 35 at 0 positions
  forever) → #440 shipped and proven on tape.

### Regression check vs prior day
Yesterday's two headline defects both have shipped counters: write-once
stop discard + cooldown blindness → #439 (code-verified, awaiting first
live stop-in-cooldown); recall corpus starvation → 41 recall events
serving outcome/lesson chunks today. No new regressions: 0 tracebacks
24h, briefs 100%, calibration/leaderboard jobs running, site 200s.
Standing next: AUDCHF 1147 Sunday 21:00Z flatten; fleet 33 `stopping`;
#443/#441/#439 first live exercises.

---

## Cycle 26 — 15:3xZ (anchor 15:34:56): quiet — both ex-position runs in their cooldowns

UNI 1293 sits in adapt **loss cooldown** (cycles 14/15 skipped — the
feedback loop doing its job after −$0.095; #439's bypass correctly NOT
firing, no routed stop hit pending). FIL 1286 passed its 45-min
re-entry cooldown and resumed deliberating (hold 0.36, flat-book
briefs). No positions, 0 tracebacks, fleet 33 unchanged. Day stands at
+$0.058 across 2 trades.

---

## Cycle 25 — 15:0xZ: SECOND CLOSED TRADE — FIL short net +$0.153, the fleet's first WIN; two-agent verdict cross-checked

**P&L first: +$0.153 net** (gross +$0.184, fees $0.031). Entry AND exit
timing desk-authored: shorted a real downtrend at the top of its 6-hour
range (13:34Z, 0.6935) and covered before the bounce (14:34Z, 0.6898).
Day P&L for fleet 35: +$0.153 − $0.095 = **+$0.058 net across 2 trades.**

**Agent A (desk axis), accepted:** entry grade A — clean geometry (path
never crosses its own stop; contrast UNI), strongest score set of the
run (momentum 0.81, conviction 0.689), and honest no-arm reasoning at
entry. Process overall **C+**: (1) an empty-`why` arm at 0.70 placed
INSIDE the stop one cycle after the desk itself wrote "no arm needed" —
a stealth tighten with no stated evidence; (2) THREE simultaneous
invalidation levels (0.70 arm / 0.70848 stop / 0.71 prose) — the desk
does not read its own standing orders; (3) the reduce fired at **12.3%**
of the path to target, citing an invalidation that never fired while the
true trigger (momentum 0.81→0.45 decay) went unnamed. Fees ate 17% of
gross — the signature of scratching, which cannot outrun one full
stop-out (~$0.74).

**Agent B (rail axis), accepted with two corrections to MY briefing:**
today had THREE dust escalations (fleet 34 run 1283 too), and UNI's
escalation cost **−$0.032 at B's mark**, not ≈$0 (my cycle-24 figure was
priced at an earlier mark — escalation impact is mark-dependent, small,
symmetric). FIL's escalation SAVED +$0.031 by luck (banked before the
bounce; the desk's coherent keep-half intent was the worse book at both
agents' marks). All rails per design intent; **3 of 3 reduce intents
today escalated** — partial exits effectively do not exist at this book
scale, which is exactly what #443's line now tells the desk.
Per-market dust floor: stays BACKLOGGED (evidence insufficient — impact
±$0.03 and #443 unmeasured).

**#444 DEPLOYED — 15:3xZ addendum.** PR MERGED (`391d7db`), image
`sooppiy-backend:20260815-one-invalidation` on worker+backend, verified
2×: skill text in-container AND all three new lessons render in the
live `skills_block("trader", "crypto")` (one-invalidation, fee-drag,
path-coherence — catalog auto-upgrade confirmed). 0 tracebacks.
Rollback: `SOOPPIY_IMAGE=sooppiy-backend:20260815-reduce-geometry`.
Ship count today: #439 #440 #441 #442 #443 #444.

**Actions:**
1. SHIP NOW — skill (position-management): ONE THESIS, ONE INVALIDATION —
   stop/arm/prose must reference the same level; an arm inside the stop
   requires a stated tightening reason (empty why forbidden); an exit
   before target/invalidation must name its actual firing signal.
2. Watch armed (B): verify #443's line renders in the next held-book
   prompt (brief-line wiring is untested by default — house lesson) and
   observe the next sub-$50 reduce intent.

---

## Cycle 24 — 14:1xZ: FIRST CLOSED TRADE — UNI short net −$0.095; two-agent review, cross-checked

**P&L first: net −$0.0949** (gross −$0.0769, fees −$0.0180). Desk-authored
reduce-half escalated to full cover by the dust-remainder rail
(half of $20 leaves $10 < $25). Both agents priced live marks
independently (3.2655 @14:12:37Z / 3.2635 @14:13:13Z, Hyperliquid) and
agree: **the loss was authored at ENTRY; the exit machinery moved ≈ $0.**

**Agent A (desk axis), accepted after cross-check:**
- Entry thesis incoherent BY CONSTRUCTION: the desk predicted a pullback
  UP to 3.40–3.45 "before any rebound" while shorting at 3.253 with a
  +1.5% stop at 3.3018 — its own stated path crosses its own stop with
  certainty. No scenario in its own narrative wins. That authored the
  gross −$0.077 (+0.38% drift against).
- Exit reason "reduce half to limit further fee drag" is economically
  FALSE: holds cost nothing in this ledger; the reduce CREATED the only
  fee in play (−$0.009 deadweight vs holding, price delta $0.00).
- Confidence machinery decorative: risk_context 0.9 and conviction at
  its trade-life HIGH (0.6925) on the cycle it cut.
- Recall served position-management #5/#3 and did not prevent the
  fee-fiction exit — the lesson corpus lacks this case.

**Agent B (rail axis), accepted after cross-check:**
- Both rails performed their design intent. #440 created the trade
  ($20 vs $0); the dust-remainder escalation was −$0.006 vs the literal
  half-reduce at live mark — noise. On percentage-fee markets closing in
  two slices costs IDENTICAL total fees, so the escalation's fee-saving
  on crypto is exactly $0 (its value is desk-attention economics).
- STRUCTURAL: floor-minimum notional ($10×L = $20 at 2×) sits INSIDE
  the $25 dust-remainder band → any partial reduce escalates to full
  close; floor positions are all-or-nothing below 2.5× leverage. The
  desk did not know this when it authored "reduce half".
- $25 dust-remainder floor is flat-fee-calibrated (2.4% hurdle); a
  crypto round trip is 0.09% — stated reason wrong for this market
  (backlog: per-market value).

**Cross-check:** no contradiction between agents (different
counterfactuals, both priced correctly); neither excused the loss; both
tie every element to a reason. Accepted in full.

**Actions (AI-first, decisions-become-skills):**
1. SHIP NOW — composer line: when position notional < dust-remainder
   floor, tell the desk "any reduce closes this position fully" (B's
   option 3; the desk issued a physically impossible order unknowingly).
2. SHIP NOW — skill edits: (a) thesis-path coherence (an entry whose
   stated path crosses its own stop before the target is incoherent —
   restate or stand down); (b) fee-drag truth (holds are free; a
   fee-motivated exit must name the avoided fee and show it exceeds the
   fee the action incurs).
3. Backlog: per-market RUN_DUST_REMAINDER_USD.

---

## Cycle 23 — 13:4xZ (anchor 13:40:34): FIL finally gets its short — third attempt, first fill

FIL 1286 cycle 11 (13:34:38Z): sell conf 0.66, authored size_frac **0.1**
(margin $17.24, clears the floor unaided — no raise note, correct),
executed short 49.70 @ 0.6935 (`run:1286:cyc:11`), stop 0.70848
(+2.16%), target 0.6635 (R:R floor note). The same entry died at
cycles 1 and 4 on size_frac 0.05; whether the schema's new $10-minimum
line nudged the desk to 0.1 or it re-derived independently, the entry
path is now clean. Book: two shorts (UNI −$0.10, FIL +$0.01). 10 holds
otherwise, 0 tracebacks.

---

## Cycle 22 — 13:1xZ (anchor 13:10:36): quiet — 9 holds, UNI short held (uPNL −$0.01)

---

## Cycle 21 — 12:4xZ (anchor 12:42:11): quiet — UNI short held correctly; position-state briefs rendering

9 holds; UNI (1293) held its short at 0.6 with the held-book brief set
rendering exactly as designed: `["position_state", "young_exit",
"last_cycle_word", "brake_distance", "exit_size", "ordinary_day"]` —
entry_rail correctly dropped, position lines correctly present (#438
working both ways). Flat runs now render `hold_streak`. uPNL −$0.04,
0 tracebacks. Docs PR #442 merged+deployed — cycles 5-20 in the corpus.

---

## Cycle 20 — 12:1xZ (anchor 12:16:55): #440 PROVEN ON TAPE — fleet 35's first position exists because of the fix; #441 deployed

**WORKED — the behavioural proof landed.** UNI 1293 cycle 8 (11:53:09Z),
sell conf 0.62:

- notes: **"size_frac 0.05 raised to floor 0.108131"** — the journaled
  raise, floored to UNI's exact per-run minimum (10 / $92.48).
- **Trade executed**: short 6.148 UNI @ 3.253 (`run:1293:cyc:8`), margin
  6.148 × 3.253 / 2 = **$10.00 exactly** — the minimum executable order.
  Fleet 35's FIRST position, ~3.3 h after birth; without #440 this order
  dies like the previous three.
- Position: qty −6.148, stop 3.3018 (+1.5%), target 3.1554 (−3%).
- Rails also caught garbage: the desk authored **target_pct −6**
  (negative) → floor 0.3 → R:R floor 3.0. Stop shape sane (1.5).

**Phantom resolved without #441**: the 11:53 cycle re-derived a fresh
short with no "existing position" reference — LLM non-determinism broke
the chain one cycle after the 0.78 phantom hold. #441 makes that
correction deterministic instead of lucky.

**#441 DEPLOYED**: PR MERGED (`45447d1`), image
`sooppiy-backend:20260815-last-cycle-word` on worker+backend, "did NOT
execute" wired in-container, 0 tracebacks. Rollback:
`SOOPPIY_IMAGE=sooppiy-backend:20260815-size-frac-floor`.

Watch: UNI stop at 3.3018 (~1.5% away) — first live exit will exercise
the stop_router path (#439 armed; no cooldown active). uPNL −$0.04.

---

## Cycle 19 — 11:4xZ (anchor 11:40:33): the desk is managing a PHANTOM position — fix in flight

**FAILED:** UNI 1293 held at conf **0.78** (11:23:21Z) with the report
"Given our existing short position and limited rail headroom, we should
hold and protect rather than add new exposure" — **it has no position.**
Its 10:53Z sell was dust-skipped (pre-fix). Cause read from code, not
guessed: `_position_state_line` renders NOTHING when flat, and
`_last_cycle_word_line` quotes "action: sell" with no execution outcome
— so after any discarded non-hold, the only position-relevant prompt
line implies the order filled. The desk now believes itself short in a
downtrend it wants to be short in: it neither holds real exposure nor
will re-enter ("no new exposure"). Profit leak on both sides.

#440 removed the dust discard, but Kelly / exposure / fee-edge /
add-limit skips still discard non-holds routinely — the phantom hazard
is general.

**Fix (branch `fix/last-cycle-word-outcome`):** the quote now carries
the outcome — when the quoted non-hold's cycle has a matching
gate_skip, the line appends "That sell did NOT execute — the platform
discarded it (<reason>). Your book is unchanged…". Holds exempt by
construction (every hold emits its own gate_skip); an old cycle's skip
cannot taint a newer executed order. Fail-before red→green (4 new
tests), 3/3 mutants killed, ruff clean; full suite running → PR → CI →
deploy. Otherwise: 10 holds, flat, 0 tracebacks.

---

## Cycle 18 — 11:1xZ (anchor 11:10:35): quiet — 5 holds, flat; first post-fix sell still awaited

---

## Cycle 17 — 10:5xZ (anchor 10:56:39): dust defect fired a THIRD time — 81 s before the fix went live

UNI 1293 cycle 6 (10:53:03Z): sell conf 0.68, authored size_frac **0.1**
(double the advertised minimum) — still destroyed: margin $9.25 < $10,
because UNI's $92.48 max_bet puts the executable floor at 0.108. Worker
restarted onto `size-frac-floor` at **10:54:24Z** — the decision ran on
the old image by 81 seconds, so this is pre-fix evidence n=3 (second
symbol), NOT a fix failure. It also validates the design: a static bump
of the 0.05 minimum would not have saved this order; only the per-run
floor does. Post-fix behavioural proof still pending — next sub-floor
sell must fill at $10 with the raise note. Otherwise: 14 decisions
(13 hold), book flat, 0 tracebacks, fleet 33 `stopping`.

---

## Cycle 16 — 10:1xZ (anchor 10:10:35): REPRODUCED — the schema's advertised minimum size is below the executable floor; fix in flight

**FAILED (n=2, deterministic):** FIL run 1286 cycle 4 (10:04:11Z) authored
its second sell (conf 0.58, conviction 0.60, stop 1.97 / target 4.44 —
sane shape again) and the identical dust skip destroyed it: **margin
$8.62 < $10 floor**, same figure as cycle 1 despite a different
size_scale. Cause traced in code, not guessed:

- `size_usd = max_bet_usd × size_frac` (size_scale never enters — the
  cycle-13 formula was wrong; corrected here).
- The desk's prompt schema advertises **`size_frac: 0.05-1.0`** as legal.
- Fleet 35's true executable minimum (`$10 dust floor / max_bet`):
  FIL 0.058, KAITO 0.067, UNI 0.108, **BNB 0.120** — on EVERY fleet-35
  run the advertised minimum is below the executable floor. The desk
  picked the advertised minimum for a cautious starter, twice; the
  platform silently destroyed both. Contract violation between prompt
  and rail — the fleet cannot open a cautious position at all.

**Fix (shipped this cycle, branch `fix/size-frac-dust-floor`):** one
definition `_dust_floor_usd` now serves the final dust guard AND a new
order-params rail — the engine passes the run's true minimum and a
sub-floor ask is floored UP to it (capped at the full bet), journaled
`"size_frac 0.05 raised to floor 0.058"` in the rails' own idiom; the
schema line states the raise. Documented as the one bounded monotone
exception: below the floor an order is not shrunk but destroyed, and the
enlargement is capped at the $10-margin minimum order. Fail-before tests
red→green (4 new), 4/4 mutants killed, ruff clean; full suite running,
then PR → CI → deploy.

**#440 DEPLOYED — 10:5xZ addendum.** PR MERGED (merge commit `612c96a`),
image `sooppiy-backend:20260815-size-frac-floor` from that exact sha on
both worker and backend. In-container: `min_size_frac` in
order_params.py (3) + run_engine.py call site (1), `_dust_floor_usd` (1),
schema line updated. 0 tracebacks; FleetPlanner ticking. Rollback:
`SOOPPIY_IMAGE=sooppiy-backend:20260815-stop-outranks-cooldown`.
Behavioural proof pending: the desk's next sub-floor entry must fill at
the $10 minimum with a `size_frac … raised to floor` note — armed on the
fleet-35 watch.

**Also this cycle:** BNB 1294 logged one `conf 0.0` hold — "light cycle:
no LLM verdict" fail-safe (LLM returned nothing); safe when flat, noted
only. Cycle 5 otherwise all-hold, book flat, 0 tracebacks.

---

## Cycle 15 — 09:4xZ (anchor 09:40:35): quiet — cycle 3 all-hold, still flat

10/10 holds (conf 0.38–0.63), `last_cycle_word` on every brief, 0
positions, 0 tracebacks. Three full desk cycles now without a single
entry on an *aggressive/short* fleet — the only attempt (FIL, cycle 1)
died on the $10 dust floor. Not yet a defect (light route, ambient-only
Saturday tape) but the entry-stall count starts here. Fleet 33 `stopping`.

---

## Cycle 14 — 09:1xZ (anchor 09:10:33): quiet — 12 holds, flat book

Fleet 35 desk cycle 2 complete on all 10 runs: **every decision hold**
(conf 0.45–0.67), 0 positions, 0 trades, 0 tracebacks. Dust-skip did NOT
reproduce (FIL desk chose hold at 0.50 rather than retry the sell; n
stays 1). **#438 brief arrays now show `last_cycle_word`** on
second-cycle decisions — the predecessor/continuity line rendering
exactly when it should. Fleet 33 `stopping` (AUDCHF Sunday flatten
pending). #439 deployed mid-window (see cycle-13 addendum).

---

## Cycle 13 — 08:5x–09:0xZ: fleet 35 fully built in 2½ min; first entry attempt dies on the dust floor

**Fleet 35 build (08:32–08:35Z): every gate fired, cleanly.** 10/10 slots
`active` from the 24-crypto universe (#436): FIL, AVAX, WLD, HYPE, SOL,
LINK, TRUMP, UNI + replacements BNB, KAITO. Gates on tape:

- **Expectancy gate**: AAVE dropped 3× ("non-positive expectancy −367.51
  USD/trade over 5 closed trades") — the deleted-account history still
  informs the corpus gate. Correct.
- **Bracket-feasibility gate**: KAITO first skipped
  (`bracket_infeasible: sigma_daily_pct=9.501 min_stop_usd=1.90 >
  loss_rail_usd=1.75` at a $561 slot), then admitted in a replacement
  round at a **$1,000 slot** — the gate did exactly what it exists for:
  refuse the impossible config, accept the feasible one.
- Vol-parity allocations $561–$1,719 summing to exactly $10,000.

**First desk cycles (3 decisions, 0 positions):**

| run | sym | action | conf | outcome |
|---|---|---|---|---|
| 1289 | HYPE | hold | 0.48 | gate_skip (hold) |
| 1286 | FIL | **sell** | 0.58 | **dust order skip: margin $8.62 < $10 floor** |
| 1287 | AVAX | hold | 0.38 | gate_skip (hold) |

- **#438 brief arrays LIVE on all 3**: `["entry_rail", "ordinary_day"]` —
  correct for a flat cycle-1 book.
- **#432 recall visibly serving**: FIL's report quotes "echoing desk
  memory that high fear can nullify bullish bias" — an ingested
  lesson/outcome chunk reaching the prompt, on the very first cycle.
- **stop_pct shape: SANE.** FIL short authored stop 2.46 / target 3.82
  → rails raised target to R:R floor 4.92 and trail_arm to 2.46, both
  journaled in `notes`. No 0.016-style garbage.

**⚠️ New watch — cautious entries can't clear the $10 margin floor.**
FIL: size_frac 0.05 × size_scale 0.30 (conviction 0.5575) × $1,160 alloc
÷ 2× leverage = **$8.62 margin → skipped**. The desk decided to enter;
the platform silently discarded it. One data point — if fleet 35's
starter entries keep dying here, that is an entry-stall defect
(conviction scaling × small size_frac interacts with the floor). Monitor,
don't fix yet.

Health: 0 tracebacks; one Hyperliquid read-timeout on AVAX (transient);
#439 merge chain still gating on CI (head 20d1fd78). Equity ticks ×48.

**#439 DEPLOYED — 09:5xZ addendum.** PR MERGED (merge commit `88555c6`),
image `sooppiy-backend:20260815-stop-outranks-cooldown` built **from that
exact sha** and running on both worker and backend. Verified in-container:
`_cooldown_blocks`/`begin_ruling` present in run_engine.py (4 hits) and
`begin_ruling`/`deciding_since` in stop_router.py (6 hits). 0 tracebacks
post-restart; FleetPlanner ticking (claimed 2, supervised 2). Rollback:
`SOOPPIY_IMAGE=sooppiy-backend:20260815-brief-journal`. The full overnight
stack #432–#439 is now live on prod. Remaining #439 verification is
behavioural: the first real cooldown-era stop hit must show "loss cooldown
BYPASSED" + a desk ruling — armed on the fleet-35 watch.

---

## TARGET SET — 09:1xZ: monitoring follows info@askkpop.com; FLEET 35 born

Owner: *"monitoring target user is info@askkpop.com (keep going this user)."*
**Fleet 35** created 08:32:14Z on the freshly-reset account: 10 slots,
$10,000, aggressive, archetype `short`, market_scope NULL, status `building`.
Loop re-armed (cron `b0ea7f21`, 30-min) centred on fleet 35 with the full
watch list: #436 universe build quality, #438 brief arrays, #432 recall
kinds, R15/R16 first exercises, #437 size-pin first live stamp if the user
resizes, #439 deploy + BYPASSED verification, and the desk's stop_pct
authoring shape (garbage 0.016/0.007 vs sane 1.9 — which does fleet 35
produce?). AUDCHF 1147 Sunday flatten remains the only other live position.

---

## OWNER-ORDERED STOP-ALL — 08:5x–09:0xZ: every other user's fleet stopped

Owner: *"and stop all other user fleet and slot."* Executed via the
platform's own kill switch (`fleet_planner.request_stop_fleet(34, 60,
flatten=True)`):

- **Fleet 34** (forevery1969, agent 60): 9 flat members → `stopping` →
  finished instantly (crypto open, nothing to flatten) → **fleet stopped**.
- **Run 1271 BTC had stopped itself `positions_held` moments earlier**,
  releasing its short to the unowned book and dodging the kill switch's
  flatten. Completed the owner's 청산 semantics by closing the orphan via
  `execute_paper_trade` (cover 0.00131005 @ 63,022.5, signal 1365,
  `owner:stopall:orphan-1271`). **Agent 60: zero open positions.**
- **Fleet 33** (henry.j, agent 59): already `stopping`; unchanged. Its
  AUDCHF 1147 queued flatten (Sunday 21:00Z FX open) is now the ONLY live
  position platform-wide among these users.

**⚠️ Watch resolutions:**
- **BTC 1271 stop-out prediction: ABORTED, not resolved** — position closed
  by owner order before the stop could confirm or refute the mechanism.
  The write-once-stop discard evidence (n=2 with P&L) and the cooldown-trap
  evidence (1 fire + 3 armings) stand on their own; #439 ships regardless.
- Cooldown-trap live exposure (1271 blind to 08:47Z): mooted by the close.
- Platform state: **zero active fleets.** Next event: owner builds the new
  $10k test fleet on info@askkpop.com.

---

## OWNER-ORDERED RESET — 08:2x–08:4xZ: info@askkpop.com (user 5 / agent 6) wiped for a fresh test

Owner: *"i need test again for info@askkpop.com so remove this part (can not
delete)"* → *"delete all slot and fleet"* → *"and balance make 10000"* →
*"and clear this part week, month year"*. Executed step by step, platform
paths first, single transactions, verified after each:

1. **Queued flattens executed early** via the platform's own
   `_flatten_run` → `_simple_transition` (the exact code Monday's open
   would run, minus the market gate — owner order accepts Friday-close
   marks on the test account): MSFT 1113 +0.331, JPM 1116 −1.604,
   IBM 1119 −0.863 lifetime. `pnl_audit` verdict `ok`, 3 flattens, before
   the history deletion below.
2. **Fleet 31 finished stopping on its own** within seconds (all runs
   terminal → supervisor stopped it, released `active_fleet_key='user:5'` —
   the unique key that was blocking any new fleet for this account; that
   WAS the "cannot delete/test again" blocker).
3. **Full graph deletion, fleets 28/29/31** (fleet-30 precedent, one
   transaction): 154 runs, 97,004 run_events, 14,173 fleet_events, 576
   signals, 155 candidates, 43 slots, 67 symbol cooldowns, 3 fleets, all 3
   leftover agent-6 positions (CRM + USDKRW ×2 orphans). Zero orphans
   verified.
4. **Balance reset**: agents.cash = starting_capital = **10,000**.
5. **History widgets cleared** (week/month/year sources): profit_history
   903, agent_metric_snapshots 874, signal_quality_scores 576,
   signal_predictions 576, +2 cooldowns. Runs/signals/positions all 0.

**Kept, deliberately**: `desk_memory` chunks (owner order "all cycle result
keep in RAG" — the corpus keeps the lessons; bodies are self-contained
text), users/agents identity rows, risk_limits, automation_configs.

**⚠️ CONSEQUENCES FOR FUTURE CYCLES (do not misread):**
- `pnl_audit --since 2026-08-12..15` now EXCLUDES agent 6's deleted ledger —
  historical day sums have changed. The 24h sweep must NOT read that as
  drift. The markdown record above retains the true pre-deletion figures.
- Watch item CLOSED: MSFT/JPM/IBM Monday-open flattens (executed early by
  owner order). **AUDCHF 1147 (fleet 33, agent 59) still stands** for
  Sunday 21:00Z.
- Swing-block trial (HANDOFF-n-slot §7 counter) for fleet 31: terminated by
  owner reset; counter resets with whatever fleet is built next.
- Next expected event: the owner builds a NEW fleet on info@askkpop.com
  ($10k). First session after: run §2 checks, note the fleet id in the
  handoff.

---

## Cycle 12 — 07:42Z (anchored 07:42:37Z) — BTC cuts half before its stop; THE COOLDOWN TRAP ARMS A THIRD TIME

**P&L FIRST: day −$3.31** (`pnl_audit` `ok`). One desk trade: BTC 1271
covered HALF its losing short @ 63076.9 (07:20:30Z), realized **−$0.171**
(fee = 22–28% of the loss). SUI 1284 desk-retired $0. Both agents dispatched,
cross-checked; they agree, and B verified the forward claim live.

### The half-cover (Agent A, ledger-exact; live-mark rule followed)

Ranks MIDDLE of three at the live mark: hold −0.237 < **actual −0.289** <
full-cover −0.342. The desk's reasoning flipped on NARRATIVE, not price
(+0.05% between cycles; thesis_alignment 0.8→0.5; cites a "60k–62k squeeze
target" BELOW the current price — stale/garbled input; its own router graded
the evidence "no specific trigger" while acting on it). It followed
exit-discipline's FORM (reduce a slice, state why — not the 91%-of-loss
full dump) while contradicting its substance (a 0.16% adverse move inside
the 0.3% stop distance is the "expected cost of owning the trade").
Executed unshaped — `railed: {}`, dust floor is $25 NOTIONAL and the $82.6
remainder is 3.3× above it (B corrected A's margin framing).

### 🔴 THE SOL TRAP, ARMED A THIRD TIME — verified live, not predicted

adapt seq 534 at **07:47:26Z**: `losing_close` (−0.1712), size_mult 0.75,
**cooldown_until 08:47:26Z**. Cycle 16 already gate-skipped. The desk is
BLIND to its own remainder — short $82.6 notional, **0.169% from the
63163.5 stop** — for an hour. Bounded: the SL/TP watcher runs on the
control pass, so the stop executes regardless; what the cooldown removes is
any better-than-stop pre-emption. Worst case ≈ −$0.29 + a cascading 2h
cooldown (second losing_close).

Arming tally: SOL 1274 (fired, desk exit −0.44 vs machine −0.88 = 2.00×
worse) · ETH 1272 (armed, self-disarmed) · **BTC 1271 (armed, live now)**.
The mechanism is deterministic (cooldown gate returns before
`stop_router.clear`, 3600s vs 180s asymmetry). Owner rule
`implement-every-time` binds: **the fix ships this session** — a routed
stop hit outranks the loss cooldown (one block: check `stop_router.pending`
before the `in_cooldown` return). This RESTORES the owner's 2026-08-13 rule
(the AI is the main author of stop exits) rather than loosening a rail; the
180s fail-safe stays for a silent desk.

### Also on the tape

- Prediction status: **halved, not resolved** — remainder keeps the same
  stop/invalidation geometry; the dead-letter arm (63250 > stop 63163.5)
  survives the cover, dead by geometry (`_evaluate_stop` runs before
  `_fire_armed_order` in the same pass).
- SUI 1284 retire: clean bracket-infeasibility in the desk's own words
  ("stop at swing high ~2.6% exceeds target — no acceptable bracket").
  Symbol cooldown stamped to 19:20:23Z. Tension flagged by B: the fresh
  batch re-scored SUI short at 1.80 (2nd highest) — the 12h bench is the
  anti-churn rail's cost if the thesis pays. Watch, by design.
- ETH cooldown held (1 gate-skip, nothing slipped). Flattens parked clean
  (B verified `is_market_open("forex")` = False — Saturday). Liq daemon
  alive. 0 tracebacks. 10/25 running — under-deployment remains the
  largest P&L lever (owner's call).

---

## Cycle 11 — 07:12Z (anchored 07:12:36Z) — FIL completes the day's only winner (+$0.355); replacement pool fully accounted

**P&L FIRST: day improved to −$3.13** (`pnl_audit` `ok`, was −3.32). The delta
is FIL 1283's final cover: 49.869 @ 0.6908 (06:43:54Z), net **+$0.184**, fee
cleared ~13×. Run total **+$0.3547** — the fleet's only fully-realized winner
today. Both agents dispatched (owner law); cross-checked.

### FIL 1283 — the completed staged exit (Agent A, ledger-exact)

Three covers on a short from 0.6948: 0.69302 → 0.69275 → 0.6908, each at a
better price, per-tranche capture of its own favourable excursion
**56% → 65% → 78%**. The desk kept **62% of its own high-water mark by its
OWN decisions** — the first fully desk-authored staged-exit winner on tape.

**The #432 loop visibly closed on a winner:** cycle 7's recall served two
ENRICHED OUTCOME chunks (runs 1013/1017 — "the trailing lock closed it, not
the desk's own call" give-back cases) and the desk then self-banked. Corpus
fed the lesson; desk acted in line with it. `brief` array present
(brake_distance, standing_arm rendered).

**Nuance (both agents agree):** the desk asked `reduce 0.5`; the Plan 24
`dust_remainder_closed` rail widened it to 1.0 (remainder ≈ $5.74 margin =
dust). Direction desk-authored, full size platform-authored. At live marks
the closed half would be +$0.05–0.115 better and the 60-min re-entry
cooldown (to ~07:43Z) means the continuing move toward 0.66 is captured by
nothing. One data point, immaterial USD — watch, not a change request.

Post-close adapt `winning_close`: size_mult [1.0,1.0], no cooldown penalty —
correct. Confidence quantization sighting #3 today: final 0.62 again.

### Replacement pool — B's "fresh theses never reach it" RESOLVED by accounting

Batch 496326's 16 crypto theses decompose exactly:
**10–11 held** (run exclusivity) + **3 in fleet_symbol_cooldowns** (UNI ×2
to 16:2x, HYPE 17:32, ZEC 17:46 — retire cooldowns DO stamp for desk/idle
retires on this fleet, n=4 rows) + **AAVE/BCH expectancy-refused**
(−367.51 and −255.02 USD/trade) = 16. **No defect: the pool is exhausted by
holding + cooldown + refusal — the design.** Note the research screen also
now marks ETH/SOL/HYPE/BNB `selectable=0` in the fresh batch — its own
gates rejecting what just lost.

The honest residual (B is right about the money): **~14 unfilled slots earn
nothing on a crypto-only Saturday.** 25 slots >> viable crypto ideas.
That is capital allocation for the owner, not a mechanism defect.

### Other

- BTC 1271: 0.18–0.21% from stop all window, watcher provably silent
  (`stops_fired: 0` every tick), NOT in cooldown, dead-letter arm still
  standing. Prediction open.
- ETH 1272: exactly 1 gate-skip (cooldown) — nothing slipped through.
- SUI 1284 desk_retired 07:19:35Z ($0, never traded) — post-window,
  next cycle's tape.
- Liq daemon ALIVE with proof: its 06:12Z T1 escalation WAS FIL pos 401,
  resolved by the desk's own cover. Flattens parked clean. 0 tracebacks.
- 10 running at 07:19Z.

---

## Cycle 10 — 06:42Z (anchored 06:42:44Z) — silent

Zero trades, zero status changes, `pnl_audit` −$3.32 `ok` unchanged, zero
tracebacks. BTC 1271 eased to 0.21% from its stop; FIL 1283 short +$0.20
open; 11 running. All watches unchanged.

---

## Cycle 9 — 06:13Z (anchored 06:13:44Z) — ETH round trip closes at −$1.87; FIL banks a winner; two-agent cross-check

**P&L FIRST: day −$3.32** (`pnl_audit` `ok`), delta −$0.98 from cycle 8,
reconciled to the cent: ETH 1272 remainder sell **−1.213** + FIL 1283 covers
**+0.146 / +0.087**. Two idle-retires (1273 HYPE, 1275 ZEC) at $0. 11 running.

### ETH 1272 — the completed round trip, −$1.8708 (ledger-verified)

| leg | price | net |
|---|---|---|
| entry buy 0.5256 @ 1883.60 (01:56, **panel-crash fallback**) | | −0.4455 fee |
| trim 0.2628 @ 1883.64 (02:56, fee 21× gain) | +0.04 | −0.2122 |
| final 0.2628 @ 1879.83 (05:56, floor-rule exit) | −3.77 | −1.2130 |
| **total** | | **−1.8708** |

**Verdict (both agents, cross-checked): the loss was authored at ENTRY, and
48% of it was fees.** The buy existed only because the panel crashed on the
one cycle it would have vetoed (it had downgraded the same buy 3 consecutive
cycles). The same fleet's FIL desk read the identical tape (FGI 34 fear,
negative macro) as SHORT — and profited. Fee decomposition: −0.98 price,
−0.89 fees.

- **The 02:56 fee-churn trim's real cost was structural, not the $0.21:**
  its `losing_close` armed a 1h59m decision lockout (cycles 7–9 gate-skipped)
  spanning the remainder's ENTIRE profitable window (peak +0.37), and burned
  0.66 of floor headroom so the floor tripped on a −0.69% move.
- **Cycle 10's stated belief "existing arm protect downside" was false** —
  the 1865 arm sat behind the house floor and could never fire.
- **The 05:56 exit itself is a WASH at the live mark** (ETH 1879.75 vs sold
  1879.83, ~$0.20 inside fee noise). No post-entry choice ended positive.
  Whether the lockout cost money is NOT DETERMINABLE — a cycle-7 sell at
  +0.29 was available (+$1.28 better) but the desk's revealed behaviour at
  flat readings was hold. The lockout provably removed the option, no more.
- Post-close adapt (06:24:05Z): size_mult 0.75→**0.5**, conf_bump 0.1,
  cooldown to 08:24:05Z — the feedback loop responding proportionately to 2
  consecutive losing closes.

### FIL 1283 — the healthy shape, +$0.171 realized, +$0.15 open

Short 199.48 @ 0.6948 into fear + bearish technicals (stated, with >2:1 R:R
plan). The panel **twice overrode a counter-trend "buy" proposal to hold**
(04:43, 05:16) while the short ran to +0.63. Two staged partials cleared
their fees **5.7× and 6.6×**. Blemish: cover 1 came after giving back ~47%
from peak — banked on the retrace, not the extension. Cycle 6's decision
carries the new `brief` array (brake_distance, standing_arm rendered) — #438
telemetry live in real decisions.

### Cross-check verdicts

- **Agent B's "research pipeline dead" claim REJECTED.** It read
  `researched: 0, built: 0` as a dead pipeline — the EXACT trap the
  fleet-replenish-stall memory warns about (those counters only increment
  for researching/building fleets, and cycle 5 already established this).
  Verified live: fresh batches 05:16:07Z and 06:17:44Z, 105 rows / 16 crypto
  each, `llm: 105`. The two-candidate replacement pool (AAVE −367.51/trade,
  BCH −255.02/trade, both expectancy-dropped 6×) is holding + refusal —
  the design, not starvation.
- Both agents obeyed the live-mark counterfactual rule this cycle (first
  time both have).
- **Agent B's real find: BTC 1271's armed order is a dead letter.** Armed
  05:18:11Z `price_above 63250 → reduce 0.5`, but the full-close stop sits
  at 63163.5 — the stop always fires first; the desk's graduated exit intent
  is silently void. $0 effect so far; same family as "the desk cannot see
  the rail that retires it". Carried as a watch.
- Idle-retires both CORRECT (12/12 cycles at sub-gate confidence, the
  rail's exact target pattern).

### Watches

- BTC 1271: 0.15% from stop at anchor, still oscillating, prediction open;
  NOT in cooldown (a stop hit would reach the desk).
- ETH 1272 in cooldown to 08:24:05Z with a FLAT book — watch whether it
  re-longs the same tape on expiry.
- Queued flattens clean; liq daemon alive (FIL margin T1 improving); zero
  tracebacks across both deploy restarts.

---

## Intercycle — 06:12Z: #437 + #438 SHIPPED; brief-line journal VERIFIED LIVE

Two more fixes to prod since cycle 8:

**#437 size pin (image `20260815-size-pin`, migration 0051):** a user resize
now stamps `fleets.user_size_cap`; auto-tune may lower below it, never raise
above it. From live n=2 (auto-tune undid the user's 25→10 within 27 min,
twice in one day). Fleet 34's cap is NULL until the next user resize — left
to the user by design. Verified: column on prod MySQL, pin code in image.

**#438 brief-line journal (image `20260815-brief-journal`):** every decision
event now carries `brief` — the NAMES of the brief lines that rendered.
Solves the R16-class blindness (prompts not journaled → rendering not
determinable from tape; memory: brief-line wiring is untested by default).
`_compose_position_state` is byte-identical to the old inline chain (pinned
by test); pop-never-read semantics like the recall journal.

**VERIFIED LIVE at 06:12:14Z** — first clean post-deploy decision, run 1283
FIL (holding short):

```json
"brief": ["position_state", "last_cycle_word", "brake_distance",
          "ordinary_day", "standing_arm"]
```

Exactly the expected composition for a holding crypto run: no predecessor
(fresh slot), no stop_hit, no earnings (crypto). The 06:10:26Z decision that
straddled the container restart carried NULL — correctly absent, not wrong.

Ship discipline note: the composer refactor stale-ified **16 pre-existing
per-line wiring tests** across two rounds (14 caught by the first full suite,
2 more raw-source greps by the second — they grep the FILE, not
`inspect.getsource`, so the first sweep missed them). All repointed at the
composer; unwire protection re-proven by mutation after repointing. Three
full-suite passes; the last fully green at 4,269 + 1,337.

**Session ship total: 7 PRs to prod** (#432 recall corpus, #433 deploy prune,
#434 stop-hit brief, #435 cycle notes→RAG, #436 universe cap, #437 size pin,
#438 brief journal).

---

## Cycle 8 — 05:02Z (anchored 05:02:38Z) — UNI retire-churn (1 rebuild, $0); psych_shock swept all 13 runs

**No closed TRADES** since cycle 7 (two desk-retires realized 0.00 with zero
trades — nothing to attribute) → no two-agent dispatch. `pnl_audit` 08-15
**−$2.34** `ok` (delta = FIL entry fee). Zero tracebacks. 13 running.

### UNI retire-churn — the known shape, but it stopped at ONE rebuild

- 04:28:05Z run 1281 UNIUSDT `desk_retired` at cycle 2, never traded, $0.
- 04:28:56Z replacement **1285, same symbol UNIUSDT** (the known same-symbol
  instant-rebuild shape — cooldown binds only adapt-retires).
- 04:30:08Z **1285 retired itself at cycle 1**: *"Short thesis aligns with
  the downtrend but lacks a realistic stop/target within risk limits, so
  retiring the slot."* conviction 0.64, thesis_alignment 0.9.
- After the second retire the replacement gate now keeps **[]** — UNI no
  longer offered (04:44, 04:59, 05:01 passes) — so the chain STOPPED at one
  wasted build, against the 4-long WMT/UBER/SBUX chains of 08-14. Cost: $0
  (no trades, no fees).

**R16 (predecessor line) — first live scenario, verdict LIMITED:**
`_predecessor_run_line` is wired into both prompt paths (run_engine 4611,
5185), but prompts are not journaled, so whether it rendered for 1285 c1 is
**not determinable from the tape** (0 payload mentions of "predecessor" —
which proves nothing either way). The behavioural evidence is consistent with
it working: the replacement declined to re-litigate in ONE cycle, citing
bracket infeasibility. **R15 note:** no `bracket_infeasible` event fired —
the DESK judged the bracket infeasible and retired before any platform gate
saw it. Both watches stay technically unexercised.

### psych_shock swept ALL 13 runs (~04:49Z)

Every run got a `hot_issue {"triggers": ["psych_shock"]}` — a market-wide
F&G/psych spike event, two with extras (1276 `manipulation:crowded_funding`,
1279 `price_move:+6.9%` on LINK). **Zero trades resulted** — 25 decisions in
the window, all hold/retire. The book stayed still through a shock event;
whether that is discipline or missed opportunity is not judgeable without the
counterfactual.

### Watches

- **BTC 1271: 0.083% from stop again** (63,111 vs 63,163.5). It has now
  oscillated 0.053% → 0.19% → 0.083% without firing. Prediction open.
- ETH 1272 recovered to −$0.03; cooldown expired 04:24Z without the trap
  firing (disarmed as predicted).
- FIL 1283 short −$0.004, stop 1.90% away, desk-authored bracket clean.
- Fleet 34: 13/25 filled; replacement passes find kept=[] — every selectable
  crypto candidate is held or expectancy-dropped (AAVE −367.51/trade, BCH).
  **The wider universe is being consumed by REFUSAL, which is the design.**
- #437 (size pin) deployed 04:5xZ as image `20260815-size-pin`, migration
  0051, fleet 34 cap NULL until the next user resize.

---

## Cycle 7 — 04:12Z (anchored 04:12:35Z) — #436 VERIFIED END-TO-END: 16 crypto theses, 9 new runs, gates exercised

**Tape: one OPEN trade, zero closes** → no two-agent dispatch. FIL 1283
shorted 199.48 @ 0.6948 (fee 0.0624) at 04:06:14Z — cycle-1 entry, desk stop
**1.9%** (`stop_pct 1.9, target 4.1, trail_arm 3.0` — NOT floored; the 0.3%
floor never bound, unlike the SOL/BTC entries). uPNL −0.01.

### ✅ #436 end-to-end verification — all three predictions landed

1. **The 13-batch streak of ~5 crypto theses broke.** First post-deploy batch
   (`research:496323`, 03:55:27Z): **16 crypto theses, 14 selectable** (vs 6/3
   the batch before). Total batch 105 rows.
2. **Fleet 34 built 9 new runs in ~2 minutes** (03:56:13–56:19Z): KAITO, WLD,
   AVAX, LINK, BNB, UNI, TRUMP, FIL, SUI — 1276–1284. Now **14 running**.
3. **The gates exercised REAL selection pressure** — the profit argument in
   action: `backtest_gate` **dropped AAVEUSDT ("non-positive expectancy
   −367.51 USD/trade over 5 closed trades") and BCHUSDT (non-positive
   expectancy)** from every replacement pass. A ranker with 14 candidates
   refused the negative-expectancy tail; three weeks ago it accepted
   HYPEUSDT at 0.30 because there was nothing else.

**LINKUSDT** — yesterday's highest-scored-but-unselectable thesis — is now
running (1279). Book exposure of the 9 newcomers so far: one FIL short; the
other 8 are in first-cycle analysis. Watch, don't celebrate: 14 running
negative-expectancy-*class* crypto runs is 14 chances to lose; the v1 crypto
cohort averages −$1.50/closed run. The measure of #436 is whether SELECTION
(dropping AAVE/BCH class candidates) improves the per-run mean, and that is a
Phase-D-style judgement over closed runs, not tonight's open book.

### 🔴 Auto-tune overrode the user's size AGAIN — n=2, owner decision needed

03:21:42Z: user resized 25 → **10** (resize API). **03:49:14Z: auto_tune_slots
raised it straight back 10 → 25** — 27 minutes later. This is the second
override of an explicit user sizing choice on this fleet in one day (first:
00:36:27Z, 10 → 25). `fleet_auto_tune.recommended_max_slots(budget)` knows the
budget but not the user's intent; nothing marks a user-chosen size as sticky.
The 9 new runs exist in slots the user had just deleted.
**Escalated to the owner: should a user resize pin the fleet size against
auto-tune?** (One-line fix candidate: honour the resize API's size as a cap
until the user changes it.)

### Watch items

- **R16 predecessor line: NOT exercised** — 0 events. Correct-by-design so
  far: none of the 9 new runs replaced a retired predecessor on the same
  symbol (all fresh slots). Still unexercised, not failed.
- **R15 bracket_infeasible: 0 events** — nothing infeasible in the new
  builds (FIL's 1.9%/4.1% bracket parsed clean). Still unexercised.
- ETH 1272 cooldown expires 04:24:24Z; stop 0.92% away — trap disarms itself
  if ETH stays up.
- BTC 1271: 0.174% from stop. Prediction open.
- `pnl_audit` unchanged −$2.28 `ok` (FIL entry fee lands next audit).

---

## Cycle 6 — 03:50Z (anchored 03:50:14Z) — 4-PR deploy verified; the cooldown trap is now armed on ETH

**Tape: no trades since cycle 5** → no two-agent dispatch. `pnl_audit` 08-15
**−$2.28**, `ok`, resid −0.01. Zero tracebacks. BTC 1271 backed off to
**0.188%** from its stop (was 0.053% at the closest) — prediction still open,
unresolved either way.

### SHIPPED — image `20260815-desk-universe` (03:48:43Z), PRs #433+#434+#435+#436

All verified in the running image:

1. **#436 universe cap 20→60:** `build_universe()` crypto **10 → 24**
   (total 187 → 201). Live pool now includes LINK, WLD, UNI, AVAX, SUI, ADA,
   BNB, KAITO, FIL, TRUMP, BCH, NEAR, AAVE. Zero extra network calls.
2. **#433 prune — first live exercise, kept the RIGHT backups**: exactly
   `*.prev-20260815-024950` + `*.prev-20260815-034822` per surface. The old
   logic would have deleted `034822` (today's rollback).
3. **#434:** `"cannot be widened"` in the running run_engine — the desk is no
   longer offered the unexecutable re-authored-stop option.
4. **#435:** `2026-08-15-automation-monitoring.md` present on the box —
   cycle results now reach the RAG corpus (owner order).
5. Post-deploy recall re-verified on the new image: 1271 cycle at 03:47:38Z
   served `lesson`/`lesson` (exit-discipline#4 + horizon-discipline#2).

**Pending verification:** the current research batch (496322, 02:47Z, built on
the OLD image, crypto 6) predates the deploy. The first post-deploy batch
(~04:47Z) must show crypto theses > 6 (survivor cap 8 from 24 candidates) and
fleet 34's 5 waiting slots seeing eligible candidates. Next cycle's job.

### 🔴 The cooldown trap is now ARMED on ETH 1272 — same shape as SOL 1274

At 03:24:24Z adapt scored the desk's fee-churn half-trim (−0.2122, the leg
where the fee was 21× the gain) as a `losing_close`:
`size_mult 0.75, conf_bump 0.05, cooldown_until 04:24:24Z`.

So until **04:24:24Z**, run 1272 is in exactly the state that killed SOL: if
ETH trades down to the stop at **1864.95** (currently 0.93% away, mark
1882.40), the stop-hit dispatches will hit the cooldown gate, the desk cannot
rule, and the 180s fail-safe closes the book with a null client_order_id.
Distance makes it unlikely in the hour; the STRUCTURE is the point — the
desk's own trim again disarmed its own authority. n=2 of the arming shape
(not yet of the fail-safe firing).

Also carried: 1272's armed reduce at **1865.0** sits 5 cents above the stop
at **1864.95** — stacked triggers, flagged by Agent B in cycle 5.

### Fleet 34 (5/10 after the user's resize at 03:21:42Z)

`size_changed {"from":25,"to":10}` with no auto-tune pair = the resize API
(user action via UI). Drain removed empty slots only — correct. The 5 waiting
slots remain empty pending the post-deploy research batch.

---

## Cycle 5 — 03:04Z (anchored 03:04:06Z) — ETH fee-churn trim; agents cross-checked

**P&L: fleet 34 −$2.276 realized** (1274 −1.544, 1272 −0.658, 1271 −0.074
fee). One closed leg in-window → both agents dispatched.

### The outcome: ETH 1272 sold half at 02:56:22Z — the fee was 21× the gain

0.26279 @ 1883.64 vs entry 1883.60: gross **+$0.0105**, fee **−$0.2228**, net
**−$0.2122**. Age 59m53s (young threshold 90m). **No young_dump_flag fired**:
`run_engine.py` guard `if got >= 0: return ""` — the profit-side exemption has
no fee term, so a bank whose fee is 21× its gain is classified as legitimate.

**Agent A (verified against prod source):** the desk sat under the standing
banking mandate — "open P&L is rolling over from its high-water mark →
reducing is the correct answer THIS cycle" — which has **no magnitude floor
and no fee term**. The high-water mark it defended was **+$0.47 = 0.0478%**,
smaller than the 0.09% round-trip fee. Its report claimed "slightly
underwater" (false — the mark was above entry) and "noise-sized" (true, and
the argument against the trade it then made). It also abandoned its own
cycle-5 trigger (reduce at 1865) by executing 18.6 points above it, and its
report said "keep the position" while the intent compiled `sell 0.5`.

**Agent B:** the exit path has no fee hurdle by design (`Exits are never
gated`) and the reduce bypassed the risk stage. Trim cost vs holding full:
**−$0.53** at the 03:10 mark. Also: found the sharper root cause of SOL's leg
2 — `automation.py:230` writes brackets only on OPENING sides, so a `cover`
cycle can never re-author a stop; the desk's 0.7% was parsed and discarded.
**Stop-discard now n=2 with P&L attached.**

### Cross-check — BOTH agents made the same counterfactual error, opposite signs

- Cycle 3: Agent A claimed honouring the wider stop saved $0.88 → **wrong**,
  priced live it was $0.12 worse.
- Cycle 5: Agent B claimed "had the 0.7% stop applied, the loss never
  happens" → **wrong**, at SOL 75.55 the position would be −1.66 total vs
  −1.544 actual — deferred and larger, not avoided.

Both compared a REALIZED loss to an UNREALIZED snapshot. Pattern now named;
every future counterfactual gets priced to the live mark before acceptance.

**Agent B's deploy-timing correction was itself wrong**: deploy-log.tsv shows
TWO deploys of the same image/sha (024237 and 024950); the containers were on
the new image from 02:42:54Z, so the 02:48:14Z live recall verification
stands. Agent B read only the current StartedAt.

### Population measurement — the third refuted microstructure fix tonight

619 exit legs, whole history: fee-ate-the-gain legs = 20 (3.2%), total
**−$0.32**; move-smaller-than-fee legs = 32 (5.2%), total **−$0.49**. Today's
ETH leg (−$0.2122) is the single worst ever. Meanwhile ALL exit legs: gross
**−$158.90**, fees −$13.02 → **~92% of the loss is gross price movement**.
No exit fee gate shipped — it would fix $0.49 in nine days. Recorded with the
other two refutations in memory `measure-before-shipping-a-microstructure-fix`.

### Fleet 34 starvation — root cause proven (Agent B + main session)

Build attempted on all 20 empty slots at 02:50:16Z, **eligible candidates:
zero**: `market_scope_json` NULL → open-markets bias → Saturday → crypto only
→ pool 6 symbols, 3 selectable all already held, LINK `selectable=0`.
42 selectable us-stock theses were excluded solely by the NULL scope
(closed-market builds are supported by design). → led to #436.

---

## Cycle 4 — 02:45Z (anchored 02:45:54Z) — PR #432 SHIPPED TO PROD + verified

**Tape silent: zero trades, zero closes** since cycle 3 → no two-agent dispatch.
`pnl_audit` 08-15 **−$2.06**, verdict `ok`, resid 0.00, 0 flattens — matches the
hand figure to the cent. Zero tracebacks in 20 min.

**Book is still bleeding, slowly:** fleet 34 realized −$2.06, open −$0.405
(BTC 1271 −0.352, ETH 1272 −0.053) → **≈ −$2.47 mark-to-market**, worse than
cycle 3's −$1.93. ETH 1272 flipped from +$0.47 to **−$0.05** (mark 1883.5 vs
entry 1883.6) — it has not yet paid for its own $0.4455 entry fee. No rail
touched; the book is simply drifting against both positions.

### SHIPPED — PR #432, prod image `20260815-desk-recall` (02:42:54Z)

All 5 CI jobs green → squash-merged `1a9feb01` → deployed. Migrations 0050,
both containers up, all six prod endpoints 200.

**Verified in the deployed image against the live 4,307-chunk corpus** (4/4
cells, zero monitoring):

| cell | kinds read | sources |
|---|---|---|
| crypto/losing | `lesson` | exit-discipline#4, horizon-discipline#2 |
| crypto/winning | `outcome` | run:1013:outcome, run:1017:outcome |
| us-stock/losing | `lesson` | exit-discipline#4, horizon-discipline#2 |
| forex/winning | `outcome` | run:1130:outcome, run:1178:outcome |

**The enrichment is live and `forget_superseded` is proven.** Newest outcome
body now reads: *"Run 1270 on BKNG (us-stock) **never opened a position**: 4
cycles of looking, then **the user stopped the whole fleet — not the desk's own
call**. Nothing was risked and nothing was learned about the entry — the thesis
never became a trade."* And the outcome count held at **278, not 556** — the
supersede replaced the stale bodies instead of duplicating them, exactly as the
test asserted.

Em-dash `�` in an earlier query result was **my shell client, not the data**:
column is `utf8mb4`, stored bytes `E28094` = U+2014. No corruption.

**✅ LIVE JOURNAL PATH CONFIRMED at 02:48:14Z — run 1271, cycle 6**, the BTC
short while losing, i.e. the exact situation that produced the original
finding:

```json
{"cycle": 6, "action": "hold",
 "query": "crypto holding position losing position stop distance cut or hold reduce",
 "chunks": [{"kind": "lesson", "source": "skill:exit-discipline#4",     "score": 10.1344},
            {"kind": "lesson", "source": "skill:horizon-discipline#2",  "score":  7.9884}],
 "scheme": "deterministic-top2", "explore": false, "propensity": 1.0}
```

**Both chunks `lesson`, zero monitoring.** The identical query string that six
hours of history answered with *"…that is why nothing ships"* and *"Two
instances, no outcome yet … Logged, not shipped"* now returns exit and horizon
discipline. The desk then decided `hold` at confidence 0.64.

**Verified three independent ways** (owner rule ≥2): (1) locally against a copy
of the 4,292-chunk corpus, 12/12 cells; (2) in the deployed prod image against
the live 4,307-chunk corpus, 4/4 cells; (3) the live journalled `recall` event
above.

### Deploy completed end-to-end on the second run (02:49:50Z)

`npm ci` in `marketing/` cleared the astro trap. Run with **`KEEP_BACKUPS=5`**
so the still-buggy prune (below) could not fire. Every step ran: SPA to all
three static roots, marketing published, verify green. `.well-known/README.txt`
canary **200** (the script's own dotfile canary), `/docs/how-it-works`,
`/docs/guide`, `/smsoptin/`, `/pricing`, `/privacypolicy`, `/termsconditions`,
`/api/subscriptions/plans` all **200**. Zero tracebacks. Backups now 4 per
surface with **nothing pruned** — both of today's rollbacks survived, as
intended.

⚠️ **The script's printed rollback line is wrong-but-harmless this time:** it
says `Rollback: set SOOPPIY_IMAGE=sooppiy-backend:20260815-desk-recall`, which
is the image just deployed — because the guard captured the value already
swapped in by the aborted first run. **The real rollback target is
`sooppiy-backend:20260815-plan25-phase-c`.**

### Corpus self-observation worth recording

`monitoring` grew **636 → 641** in the last hour: these very cycle notes are
being ingested into the corpus the desk used to read from. That is precisely
why the retrieval source had to change — the loop was feeding its own
engineering commentary back into the trading prompt.

### 🔴 BTC 1271 — the cycle-3 prediction is tightening, not resolving

| cycle | mark | stop | distance |
|---|---|---|---|
| 3 (02:27Z) | 63,094 | 63,163.5 | 0.110% |
| **4 (02:45Z)** | **63,109** | 63,163.5 | **0.086%** |

Thesis invalidation ~63,785; the cycle-5 request for `stop_pct 1.23` is still
discarded. Prediction stands unrevised.

### 🔴 deploy.sh bug found and NOT executed

The deploy aborted at the marketing step (`astro: command not found`, the known
worktree trap) — safely, before any marketing mutation, and `marketing/` +
`service/frontend/` have **zero changes** since the last deployed image, so that
step was a content no-op. But the skipped step 7 prune was dry-run and would
have **deleted today's rollback backup**:

```
WOULD DELETE:  admin-site.prev-20260815-024237
               /usr/share/nginx/sooppiy.prev-20260815-024237   ← newest
```

Cause: all three directory backups share an identical mtime
(`2026-08-14 22:50:50`) because `cp -a` preserves the SOURCE tree's mtime and
the built SPA has not changed since. `ls -dt` then has nothing to sort by and an
arbitrary tiebreak puts the newest-by-name last, where `tail -n +3` deletes it.
The script's comment *"Sort by mtime, never by name"* is right for `.env.bak-*`
(real files, distinct mtimes) and **wrong for the `cp -a` directory surfaces**.

**Net effect on every normal deploy: the SPA and admin-site rollback for the
deploy that just ran is destroyed while two older ones are kept.** It did not
fire this time only because the marketing build aborted the script first.
Prune NOT run; backups left at 3 per surface, rollback path intact.

---

## Cycle 3 — 02:27Z (anchored 02:27:49Z) — FIRST REAL LOSS, two-agent analysis

**P&L FIRST: fleet 34 realized −$2.06** (1271 −0.074, 1272 −0.446, **1274 −1.544**),
open +$0.13 → **≈ −$1.93 mark-to-market**. `pnl_audit` 08-15 remains `ok`.

Run 1274 SOLUSDT: shorted 6.5755 @ 75.28 (01:11:03Z), covered in two halves —
3.2877 @ 75.38 (02:10:19Z, `run:1274:cyc:5`) and 3.2877 @ 75.514 (02:24:52Z,
**`client_order_id: null`**). Both agents dispatched per the owner rule.

### Loss decomposition (Agent B, reconciled to equity seq 165 to the cent)

| component | USD | share |
|---|---|---|
| fees (0.22275 + 0.11152 + 0.11172) | **−0.44599** | **28.9%** |
| leg 1 price (75.28→75.38) | −0.32877 | 21.3% |
| leg 2 price (75.28→75.514) | −0.76933 | 49.8% |

**29% of the loss was fee, on a $495 notional held 74 minutes.**

### 🔴 THE AGENTS DISAGREED — and the disagreement is the finding

**Agent A:** honouring the desk's own cycle-5 stop (0.7% → 75.807) means leg 2
never fires; realized would be **−0.663 instead of −1.544 — "$0.881 less loss."**

**Agent B:** refuted it on the actual tape — SOL's post-hit lows were 75.506 /
75.535 / 75.536 and the wider stops (75.807, 76.454) were **never reached**
(max 75.576).

**Main-session adjudication — B is right, A is wrong.** Priced against the live
mark **SOL 75.55** (OKX, 02:37Z): the surviving 3.2877 short at entry 75.28
marks at **−0.888**, plus the −0.663 already realized = **−1.551**, and it would
still owe ~0.111 of exit fee → **−1.662 versus the actual −1.544.**
**The counterfactual is ~$0.12 WORSE, not $0.88 better.**

Agent A compared a *realized* loss against an *unrealized* snapshot of the
alternative and booked the gap as a saving. That is precisely the flawed logic
the owner law forbids, and it is rejected. **No rail cost money in this window;
the fail-safe close at 75.514 was at or better than every subsequent print.**

### ✅ CONFIRMED BY BOTH, and re-verified in the main session

1. **The stop that killed it was never the desk's.** Verbatim from
   `order_params` cycle 3: `"stop_pct 0.016 raised to floor 0.3"` (SOL) and
   `"stop_pct 0.007 raised to floor 0.3"` (BTC). The desk emits sub-basis-point
   stops while writing the rationale *"stop sits just above recent
   resistance"* — its words and its number are disconnected.
2. **Stop revisions after the opening cycle are journaled and discarded.**
   BTC 1271 asked for `stop_pct 1.23` at cycle 5 (→ 63,749); the stored
   `positions.stop_loss` is still **63,163.5**, the cycle-3 0.3% value. Agent B
   audited all four writers of `positions.stop_loss` — `automation.py:247/271`
   (monotone), `orphan_reclaim.py:183` (`WHERE stop_loss IS NULL`),
   `risk_engine.py:656` (tighten-only), `routes_trading.py:845` (manual user
   API) — **no path exists for the desk to widen a stop mid-life**, while
   `_stop_hit_line` (run_engine.py:3196) explicitly instructs it to *"hold ONLY
   with a re-authored stop_pct"*. An instruction the code cannot execute.
3. **The null `client_order_id` is `risk_engine.sl_tp_watch`'s fail-safe.**
   Worker log names it: 6 × "SL/TP hit routed to desk" at 30 s ticks from
   02:21:48, then `02:24:51,977 WARNING SL/TP desk routing TIMED OUT —
   fail-safe close`. Desk orders stamp `run:{id}:cyc:{n}`; the watcher has no
   cycle to name.
4. **The desk was structurally barred from ruling on its own stop.**
   `stop_router` timeout 180 s vs an adapt loss-cooldown of **3600 s**, and the
   cooldown gate (`run_engine.py:5047`) `return`s 186 lines *before*
   `stop_router.clear()` (line 5233). **A 20× asymmetry: any stop hit during
   adapt cooldown deterministically ends in a watcher close.** Self-inflicted —
   the desk's own risk-reducing half-cover armed the cooldown 23 seconds after
   the stop hit was noted. `adapt` simultaneously recorded
   `thesis_status: "intact"` and locked the desk out for an hour.
5. **`young_dump_flag` is telemetry only** — `run_engine.py:5462`, comment says
   *"NO behavior change"*. P&L effect exactly $0.00.
6. **recall never returns lessons or outcomes.** Agent A measured **163 recall
   events since 2026-08-14: `monitoring` 163, `lesson` 0, `outcome` 0** — an
   independent, wider-window confirmation of the cycle-2 finding that PR #432
   fixes. Bitter detail: recall delivered *"stops tighter than a day's noise"*
   to this very run at 01:38 and 02:10. **The desk acted on it** — it asked for
   0.7%. The platform discarded the request and stopped it out on 0.3%.

### 🔴 THE PROFIT FINDING — the thesis was fabricated, and the gate cannot see it

Agent B found this and Agent A missed it entirely. Verified verbatim in the
main session from `research_theses` / `config_snapshot_json`:

| field | value |
|---|---|
| `expected_move_pct` | **4.0** |
| `vol_daily_pct` (SOL's own measured daily range) | **1.2421** |
| `mom_2d_pct` | −0.3175 |
| `volume_ratio` | **0.2573** (26% of normal) |
| `technical` subscore | **−0.0597** (≈ zero) |
| `psych` / `social` / `news` subscores | **all null** |
| `final_score` | 0.8655 → **selected** |

**A 4.0% expected move was claimed on an asset whose ordinary day is 1.24%** —
3.2× a day's range, over 48 h, on quarter-normal volume, with a technical
subscore of approximately zero and no psych/social/news support at all.

The resulting geometry could essentially only lose:

- stop 0.3% = **one quarter of an ordinary day**
- target 0.6%, claimed move 4.0% = **3.2 ordinary days**
- round-trip fee ≈ 9 bp = **30% of the stop distance**

**And the fee/edge gate consumes `expected_move_pct` as an INPUT** — so it
verified the arithmetic against a number the planner invented. The gate cannot
detect that the claim is unsupported by the momentum and volume fields sitting
beside it in the same row.

**This chains directly to cycle 1.** The ranker had 5 crypto candidates for 5
open slots and took 100% of them — so a thesis claiming 3.2× a day's range on
26% volume could not be rejected, because there was nothing to reject it in
favour of.

### Falsifiable prediction, stated BEFORE the outcome

**BTC 1271 is 0.110% from the same death**: mark 63,094, stop 63,163.5, thesis
invalidation ~63,785, and its cycle-5 request for `stop_pct 1.23` was discarded.
If it stops out on an unfalsified thesis, the mechanism is proven at n=2 and a
fix is designed. If it does not, this analysis is revised. Recorded now so it
cannot be confirmed after the fact.

### Watch items (new)

7. **Run 1274 is still `status='running'` with a flat book**, cooldown to
   03:22:11Z, on the same fabricated thesis. Watch whether it re-shorts SOL.
8. Liquidation daemon liveness **inside** the window is not provable from logs —
   there is no heartbeat line, only registration + a successful run 36 min
   prior + no crash trace. Stated as a limit, not asserted as healthy.

---

## Cycle 2 — 01:47Z (anchored `SELECT NOW()` = 2026-08-15 01:47:34Z)

**Tape: silent.** Zero trades, zero closes since cycle 1 → no two-agent
dispatch (nothing to attribute). `pnl_audit` 08-15 **−$0.30**, `ok`, 0 flattens
— unchanged. Two decisions, both `hold` (SOL 1274 conf 0.53, ZEC 1275 conf
0.48). Fleet 34 still **5/25**. Queued flattens still correctly parked. Worker
clean; one new benign feed 404 (`Yahoo daily candles failed for BK`).

**Book drifted against us, small:** SOL 1274 short −$0.53 → **−$0.74**,
BTC 1271 short −$0.09 → **−$0.12**. Fleet 34 total −$1.16 (−$0.30 realized fees
+ −$0.86 open). Both shorts are losing because crypto ticked up; neither has
reached any rail. Not a defect — but it is a loss, and it is the reason the next
finding matters.

### 🔴 FINDING — the desk's memory recall reads the wrong 15% of its own corpus

First live sighting of the Plan 22 RAG `recall` event this session, on run 1274
cycle 4 — the SOL short, while losing, asking *"cut or hold?"*.

**The corpus (`desk_memory`, prod):**

| kind | chunks | retrieved in production? |
|---|---|---|
| `decision` | 3,231 | ❌ never |
| **`monitoring`** | **636** | ✅ **the only kind ever read** |
| `outcome` | 278 | ❌ never |
| `lesson` | 147 | ❌ never |

There is exactly **one** production call site — `run_engine.py:3937`, inside
`_recall_line`, with **`kind="monitoring"` hardcoded**. Every other
`desk_memory.search` in the tree is in `tests/`. The result is injected straight
into the decision prompt at `run_engine.py:4385` under the heading
*"What this desk has already learned about cycles like this."*

So the desk's memory of **actual trade outcomes (278 chunks)** and its
**curated Plan 22 trading lessons (147 chunks)** are dead weight — written,
stored, and never read by anything that trades.

**What it actually injected into run 1274's prompt** (`scheme:
deterministic-top2`, both hits from `2026-08-03-automation-monitoring.md`):

1. `#The ladder that never ends — quantified, and NOT shipped` (score 12.29).
   Body: scaling out of a position cost **0.53 of drag** versus holding whole,
   concluding *"the cause is not mechanical greed, and that is why nothing
   ships."*
2. `#NEW WATCH — stops tighter than a day's noise` (score 10.88). Body:
   *"Two instances, **no outcome yet** — neither has been stopped out. Logged,
   not shipped."*

A desk deciding whether to cut a losing short was handed (a) an argument that
trimming is drag, and (b) an explicitly unresolved hypothesis — both labelled
as things it had *learned*. Neither chunk carries an outcome. Both are
engineering commentary about whether to ship a platform change.

**Base rate of deliberately-inconclusive chunks** ("NOT shipped" / "no outcome
yet" / "logged, not"): **16 / 636 monitoring — and 0 in every other kind.** The
one corpus the desk reads is the only one carrying text we wrote precisely
*because we had not concluded anything.* And retrieval is biased toward them:
those sections are written while analysing a losing shape, so they are
term-dense for exactly the query a losing run generates. The observed hit
ranked **#1**.

**Honesty about strength of claim** (owner law — do not assume the analysis is
right):
- **CERTAIN** (code + payload + body all read): the single prod recall path
  reads only `monitoring`; `outcome` and `lesson` are never retrieved.
- **CERTAIN**: the two chunks quoted above were injected into a live decision.
- **NOT PROVEN**: that this changed the decision. SOL held at conf 0.53 and is
  −$0.74. **n=1.** This is not yet grounds to claim a measured P&L cost.

**Fix designed (AI-first):** rank `outcome` + `lesson` first — what actually
happened last time in this shape, and the curated lessons — with `monitoring`
as fallback, and exclude chunks carrying unresolved markers. One call site.

### Watch items (carried + new)

5. Recall corpus kind selection — fix in build.
6. `horizon_shadow` fired twice (runs 1274, 1271) with triggers
   `["psych_shock","hot_issue"]`, "desk horizon holds until ~13:1xZ". Shadow
   mode, not acting. First sighting; watching for its first live promotion.

---

## Cycle 1 — 01:34Z (anchored `SELECT NOW()` = 2026-08-15 01:34:35Z)

**P&L (pnl_audit ledger replay, authoritative):** 08-15 **−$0.30**, 0 flattens,
verdict `ok` (fee_asym −0.30, resid 0.00). 08-14 −$17.99 `ok`, 08-13 −$147.49
`ok`. The whole of today's −$0.30 is the **entry fee on two open shorts** —
there are **zero closed trades today**, so no two-agent outcome dispatch this
cycle (nothing to attribute).

**Book (fleet 34):** 5 runs of 25 slots. Two positions open, both shorts, both
marginally underwater: SOLUSDT 1274 −6.5755 @ 75.28 (mark 75.36, uPNL −$0.53),
BTCUSDT 1271 −0.00262 @ 62,974.6 (mark 63,009, uPNL −$0.09). Deployed notional
≈ **$660 against a $100,000 budget**.

**Legacy book (fleets 31/33, both `stopping` since 22:2xZ yesterday):** 4
positions awaiting queued flattens — AUDCHF 1147 (Sunday 21:00Z FX open),
MSFT 1113 / JPM 1116 / IBM 1119 (Monday 13:30Z NYSE open). All four emit
`gate_skip {"stage":"flatten","reason":"market closed — flatten queued to the
next open"}`, 3× each since 00:00Z (R12 dedupe holding — no spam). **Correct
behaviour, not a stall.** Execution must be verified at those two opens.

**Daemons:** worker restarted 00:36:07Z with all 40 tasks. Zero tracebacks in
45 min. `[Liquidation] escalations=1 worst=T1 measured=4/4` — alive. Feeds
healthy (Social 150 fetched, Psych fng=34, Scanner candidates=2, Market Intel
inserted=10, errors=0 on all).

### 🔴 FINDING — the crypto research universe is structurally starved (ROOT CAUSE, measured)

Fleet 34 has sat at **5 of 25 slots for 68 minutes**, and it is Saturday: crypto
is the **only** market tradeable until the FX open Sunday 21:00Z. The fleet is
not stalled by a bug in the fleet planner — it ran out of ideas.

`[FleetPlanner] tick: {'claimed': 3, 'researched': 0, 'built': 0, 'supervised': 3}`
on every tick, and the last build-related fleet event is
`slot_waiting {"slot": 5, "reason": "no_candidates"}` at 00:27:42Z.

**Where the candidates die — measured live in the prod worker:**

| stage | count |
|---|---|
| OKX USDT perpetuals available | **431** |
| Hyperliquid-listed (priceable) bases | **232** |
| `top_symbols._VOLUME_CANDIDATES` pre-filter cut | **20** |
| …of those 20, Hyperliquid-priceable | **8** |
| + scanner discovery candidates | 2 → universe **10** |
| survive the research screen → theses | **5** |

`build_universe()` in prod returns `{'crypto': 10, 'us-stock': 126,
'futures': 21, 'forex': 30}`. Crypto — the only 24/7 market — is **5.3% of a
187-symbol universe.**

**Reproduced, not n=1:** the last **12 consecutive research batches** over 24h
each produced **exactly 5** crypto theses (us-stock 40, forex 24, futures 14).
This is a hard structural ceiling, not a quiet-tape artifact.

**Counterfactual, measured against the live OKX/Hyperliquid response:**

| `_VOLUME_CANDIDATES` | priceable crypto symbols |
|---|---|
| 20 (today) | **8** |
| 40 | 12 |
| 60 | **21** |
| 80 | 33 |
| 120 | 51 |

At 60 the pool is BTC, ETH, SOL, XRP, ZEC, HYPE, DOGE, PUMP, LINK, WLD, UNI,
SUI, 2Z, BNB, KAITO, ADA, WLFI, FIL, TRUMP, BCH, AVNT — all top-60 by 24h OKX
volume, so all genuinely liquid. The ranking step costs **no extra network
call** (`_okx_get("tickers")` already returns all 431 rows); only the research
screen's daily-candle reads grow.

**Why `_VOLUME_CANDIDATES = 20` is wrong here:** its docstring says "Top-5
symbol universe (Plan 11 F1)" — it was sized for a **UI widget**
(`TOP_SYMBOLS_LIMIT = 5`), then reused as the discovery channel for a 25-slot
fleet. `symbol_research.build_universe` even documents the ceiling
("The effective ceiling is top_symbols._VOLUME_CANDIDATES (20)") — the
2026-08-07 widening fix raised its own `[:50]` slice but stopped at the
constant that actually binds.

### ⚠️ The honest profit reading — widening is NOT "more trades = more profit"

Per the Phase D v1 baseline, **crypto is the worst v1 cohort: −$1.50 per closed
run over 68 runs.** Filling 20 more slots into a negative-expectancy book would
*increase* losses. Saying "$99k is idle, deploy it" would be exactly the flawed
logic the owner's law forbids.

The defensible profit argument is **selection, not exposure**:

> With 5 candidates and 5 open slots, the ranker **made no choice at all** —
> it took 100% of what existed.

Evidence: fleet 34 accepted HYPEUSDT at `final_score` **0.30** / confidence
**0.45** (the weakest of the five; BTC scored 1.08). Run 1273 has since decided
`hold` on every one of its 4 cycles (confidence 0.42–0.46) and has **never
traded** — $5,000 parked in a slot that only exists because nothing better was
offered. A ranker given 21 candidates rejects that tail; a ranker given exactly
as many candidates as slots is a pass-through.

**So the fix is scoped as: widen the candidate pool, keep exposure governed by
the existing quality gates.** More to choose from, not more taken.

### Other observations

- **Auto-tune raised fleet 34 from 10 → 25 slots at 00:36:27Z**
  (`auto_tune_slots {"from":10,"to":25}`), 24 minutes after the user created it
  at 10. This is by design (`fleet_auto_tune.recommended_max_slots(budget)`,
  clamped to the plan entitlement cap), but it means the platform silently
  overrode the user's own sizing choice, and it **cut per-slot allocation from
  $10,000 to $4,000** — then created 15 slots that could never fill. Worth an
  owner decision: should auto-tune raise a fleet above the size the user chose?
- `"llm": {"provider":"local","model":"gpt-oss:120b","source":"rule"}` on every
  decision. **`source: "rule"` is NOT "a rule decided this"** — it is the
  `LlmContext` spend-attribution tag set in `run_cycle` (run_engine.py ~5008).
  The desk is live. Checked so a future cycle does not re-raise it.
- Both trades today fired at confidence **exactly 0.62** — the known
  quantization shape (memory `run-ai-confidence-quantization`). n=2, watching.
- One `gate_skip {"stage":"execute","reason":"fence: lease expired"}` on run
  1271 cycle 1. Single occurrence; watching for recurrence.

### Watch items opened

1. Fleet 34 crypto universe — fix in build (above).
2. Queued flatten execution: AUDCHF 1147 @ Sun 21:00Z; MSFT/JPM/IBM @ Mon 13:30Z.
3. R15 (`bracket_infeasible`) and R16 (predecessor line) — first live exercise
   on fleet 34, not yet observed.
4. Fleet 34 is the Plan 25 **v2** cohort: the us-stock v2 members needed for the
   Phase D A/B do not exist yet and cannot until the Monday open.
