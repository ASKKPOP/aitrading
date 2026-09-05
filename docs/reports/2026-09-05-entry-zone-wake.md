# Entry-zone wake — in measured crypto decisions the desk is asked at the wrong price 98.4% of the time

Cycle note, 2026-09-05. Ships `entry_router` (951b0ae5) plus six bounding
fixes (69555ebc). **Registered before deploy.**

## The state this is answering

Four rails were removed on 2026-09-04 — loss budget, switch window,
plan-awareness, panel blindness. Every one was a real, measured defect. The
trade count after all four: **zero**. Prod at 2026-09-05 01:01Z: 55/55 hold
over three hours, 0 trades in 24h, 8 running runs, 0 open positions.

Owner, plainly: "All order hold, it's not solution, it's not trading
software."

## Hypothesis

The desk is not refusing to trade. It is being **asked at instants when
price is not where it said it wanted to buy**. It names a level nearly every
hour and the platform has nowhere to put one:

> LIT: "Hold until price retraces into the 4.678-4.761 zone; current price
> is above entry range."
> ENA: "the entry itself is the disqualifier — price sits ABOVE my target,
> the easy leg is already spent."

Selection ranks candidates by how much they ALREADY moved (|mom_2d| ×
volume) and then asks for a market entry at an arbitrary hourly instant.
Momentum selection plus market-only entry at sampling instants is a
permanent deadlock for a desk with pullback discipline.

## Measurement

**A false positive I caught and killed.** The first pass paired each
decision with the zone the desk had most recently authored, using the
decision payload's `entry` field as the mark. It returned 13.8% of
decisions taken with price inside the zone — which would have refuted the
hypothesis. It was an artifact: `entry` is the desk's own AUTHORED entry
price, not the live mark (it equalled the zone's high exactly in several
cases), so it sits inside the zone by construction and measures nothing.

**Re-run with an independent instrument** — Hyperliquid 1m candles, asking
whether the realized minute at each decision timestamp overlapped the zone:

| | n | share |
|---|---|---|
| live price OUTSIDE the desk's own zone at decision time | 250 | **98.4%** |
| live price inside it | 4 | 1.6% |

(254 crypto decisions over 36h that had both an authored zone and candle
data; 0 dropped for missing candles.)

**Dwell**, from the same candles over 24h, 15 crypto zone plans:
6 zones touched, 9 never touched at all. Across the 6, 62 episodes, median
dwell 3 min — but every one of the 6 had at least one episode of 36-117
minutes, and 912 total in-zone minutes. LIT alone spent 339 minutes (23.5%
of the day) inside the zone it had named.

So the levels are reachable and are reached for long stretches. The platform
simply is not looking when price gets there.

## The contrary evidence, stated plainly

All **4** of the in-zone asks were holds. This is weak evidence AGAINST
the ship, not neutral: under a uniform prior, 0 entries in 4 asks puts the
posterior mean entry rate near 17%. One of the four (LIT, minute
4.7345-4.8211 vs zone 4.678-4.761) only clipped the zone with its low, so
the honest n is closer to 3. It remains the only direct evidence about what
the desk does when asked at its own level, and it does not favour the ship.
Recorded here so no later session can claim this was justified without it.

The registered threshold below is calibrated against exactly that prior: at
a true 20% entry rate, P(0 entries in 20 wakes) is about 1.2%, so >=20
wakes with zero entries is a real refutation and not bad luck.

## What this ship actually claims

Not "this will produce trades." The honest claim is narrower and it is why
the ship is worth making:

**Today we cannot even run the experiment.** At a 1.6% in-zone ask rate the
desk is essentially never consulted at its own level, so we can never learn
whether it would enter there. This ship raises that rate deliberately. Within
a day it will tell us which of two very different problems we have — and
they need opposite fixes.

## Registered falsifier — F-WAKE

Measured 24h after the switch, on `entry_zone_touch` telemetry and the
decisions that follow each wake.

1. **The mechanism is dead** if `entry_zone_touch` count is **0** in 24h.
   Given 6/15 zones were touched for 912 minutes, zero wakes means the probe,
   the guards, or the plan read is broken — not that the market was quiet.
2. **The timing theory is REFUTED** if wakes fire but the desk holds through
   **≥20 in-zone wakes with 0 entries**. Then being asked at the right price
   is not the binding constraint, the blocker is the desk's own criteria,
   and `entry_router` must be reported as a FAILED fix in these same terms —
   not re-framed as "healthy discipline".
3. **Supported** if entries appear at or near authored zones. Report P&L
   first, with and without the largest contributor; if stripping the largest
   flips the sign, the result is INCONCLUSIVE.
4. **Selection is the real constraint** if wakes stay near zero *and*
   the untouched-zone share stays ~9/15 — the desk would be naming levels
   its own momentum-ranked symbols never revisit. That points at
   `entry_funnel`, not at the wake.

Anti-rubber-stamp: if wakes convert to entries at **≥80%**, treat that as a
defect signal, not success — the panel has declined 465/466 proposals, so a
sudden near-total approval means the wake is functioning as an order rather
than a question.

## What shipped

`entry_router.py` mirrors `stop_router`: in-process pending map, think-window
suppression (`ENTRY_ZONE_RENOTE_MIN`, 30 min), kill switch `ENTRY_ZONE_WAKE`.
Three seams in `run_engine`: note the touch in the control pass, dispatch the
run in `due_run_ids`, clear on cycle.

**It places no order.** The zone is a WAKE condition; the desk authors every
order at market through every gate. Owner rule 2026-08-13 intact.

### Six defects fixed before it ran on live money (69555ebc)

Three from adversarial review, three from my own reading of the live path.

1. **Skipped cycles never cleared the wake** — `_pre_gate_skip` returns above
   the `clear` site, so `due_run_ids` re-dispatched every pass forever: ~800
   spun cycles per symbol per night. Same shape as the SOL 1274 incident
   (2026-08-15) where a stop ruling died at a gate whose "return sits before
   `stop_router.clear`" and the fail-safe dumped the book at 2.00× the
   desk's own exit.
2. **Waking a market that cannot fill** — the closed-market feed does not
   return None. Measured with the NYSE shut: NVDA 230.36, PLTR 174.33
   (provider: yahoo). Now guarded on `is_market_open`, fail-closed.
3. **Unbounded feed load on the stop path** — `price_fetcher` has no price
   cache; unthrottled this was **120 live fetches/hour per flat run**
   (`RUN_TICK_INTERVAL` is 30s, not the 60s first assumed), ~960-1560/hour at
   fleet scale, inside the SERIAL control pass that also evaluates stops and
   fires armed exits, each with a 10s timeout, and a 429 trips the
   provider-wide cooldown that starves the marks the stop system reads. It
   was entirely net-new: `compute_run_pnl` reads `positions.current_price`
   from the DB, so the control pass previously fetched nothing.
   `ENTRY_ZONE_POLL_SEC` default 300 = the platform's existing mark cadence.
   Independently measured after the fix: **12 fetches/hour per run.**
4. **The wake bypassed swing dormancy** — pending check sat above the
   `analysis_window` block. Moved below it.
5. **The wake accelerated idle-retire** — `_claim` bumps `cycle_seq` every
   cycle, so a run parked in its zone hit the count-based rail in ~6h instead
   of ~12h, retiring fastest exactly the run waiting at the level it named.
   `_entry_wake_cycles` discounts it.
6. **The dispatch seam was not pinned** — `if entry_router.pending(...) and
   False:` killed the whole feature and passed all 20 tests, because the pin
   was source-text. Third time in two days a source-text pin hid a behaviour
   kill.

Tests 20 → 39, all six mutation-checked behaviourally; files verified
byte-identical to their pre-mutation copies afterwards.

### Then two more of the same bug, and the structural fix (b3d13cbc + follow-up)

A second adversarial pass found that two of those six were not actually
pinned: multiplying the idle-retire discount by 100 (which makes a run
permanently un-retirable, holding its slot forever) and flipping its SIGN
(which inverts the fix) both passed all 39 tests. The test had
re-implemented the rail's arithmetic in its own body instead of driving
`_evaluate_stop`, so the sign was never exercised — a RE-IMPLEMENTATION pin,
the fourth variant in two days of a test that looks like it checks behaviour
and does not.

A third pass then found the spin bug at two more gates, including the adapt
loss cooldown — which is the PRODUCTION path, since `compose_run_settings`
sets `feedback:True` on every fleet run. That one is the worst of the family:
each spun cycle bumps `cycle_seq` while `_entry_wake_cycles` stays at 1 (the
pending flag blocks new notes), so the spin also defeats fix #5 above. Roughly
60 spins against a 3600s cooldown, versus an idle limit of 12, retires the
slot in about twelve minutes — the exact inversion fix #5 exists to prevent.

**The lesson is the shape, not the count.** `run_cycle` has five early exits
above the old clear site, and they were being patched one at a time; the
third pass would have been followed by a fourth. The clear now lives in
`run_cycle`'s `finally`, guarded on `run is not None` — which ends the class
and still preserves the one case that must NOT clear, a failed `_claim`,
where no cycle ran at all. This is the same shape `_cooldown_blocks` records
costing real money on `stop_router` (SOL 1274, 2026-08-15); it has now cost
four separate defects in one feature.

### Does a 300s probe defeat the purpose?

No, and it was measured rather than assumed — but the finding is scoped to
the 6 symbols observed, not a general property. Each of those 6 had at least
one in-zone episode of 36-117 minutes, so a 5-minute grid is guaranteed to
land inside each, and for THIS set the 36/62 episodes shorter than 5 minutes
are redundant re-touches of zones already caught by a long episode. A miss
requires price to enter AND fully exit the band inside one 300s gap: the
worked LIT band is 1.76% wide against a typical ~0.24% five-minute move on a
4%/day name, so traversing it in one gap is a spike, and a market entry into
a spike is a bad fill anyway. TIGHT bands are the real exposure — at ~0.5%
width the band is only ~2x the five-minute step. Measuring the distribution
of authored zone widths is registered as a follow-up; if the median is under
~0.5%, lower the interval for crypto. Against a status quo of sampling once an HOUR this
is ~12× finer, and paying a systemic feed risk to chase sub-5-minute wicks
is a bad trade.

## Deployed

`sooppiy-backend:20260905-20260905-entry-zone-wake` from `6d61df7`, backend
and worker recreated 2026-09-05 01:58Z. Rollback: set `SOOPPIY_IMAGE=`
`sooppiy-backend:20260904-panel-reviews-proposal` and re-run compose up.

Local CI on `6d61df7b`, all six jobs: ruff PASS, pytest PASS (5143 passed,
1349 subtests), frontend-build PASS, npm-audit PASS, gitleaks PASS, pip-audit
PASS. What a local run does NOT give: a clean-room runner, a hosted audit
trail, and any check needing provider secrets.

Verified live in the worker: `ENTRY_ZONE_WAKE` on, poll 300s, renote 30 min,
all three seams present.

**Pre-deploy baseline** (01:47Z): 0 `entry_zone_touch` ever, 34/34 hold over
two hours, 0 trades in 24h, 9 running runs.

### First wake — the diagnosis case, 56 seconds after deploy

    run 2734  LITUSDT  mark 4.74815  zone 4.678-4.761  @ 01:59:02Z

That is the exact zone from the sentence this whole ship was built on:
"Hold until price retraces into the 4.678-4.761 zone; current price is above
entry range." Price returned to the level the desk named, and for the first
time the platform was looking. **F-WAKE clause 1 (the mechanism is dead) is
refuted.** Clauses 2-4 remain open and are the ones that decide whether the
ship was right.

### First wake, ruled — F-WAKE count 1 of 20

The wake survived a stale lease (run 2734 was claimed 01:58:04 and the worker
was killed at 01:58:45 by this very deploy, leaving `claimed_by` held until
02:03:04). It was PRESERVED, not consumed — the `run is not None` guard doing
in production exactly what its unit test asserts — and the run was claimed at
02:03:33, the first tick after expiry.

    cycle 7  02:05:42Z  action=hold  conviction=0.64  order_params: parsed

A real cycle, not a scaffold: the model answered and the order params parsed.
The desk was asked at its own level for the first time and said no.

**Its reason is not the entry price.** From its own report one cycle earlier:
"RSI 79.5 and a collapsing volume ratio of 0.22 — thinning participation, the
classic exhaustion tell this desk has repeatedly refused to chase." If that
reason holds across the next 19 wakes, F-WAKE clause 2 refutes the timing
theory and this ship gets reported as FAILED in those words.

**Anomaly to watch:** this decision recorded `confidence: 0.0` alongside
`conviction: 0.64`, and no `decided_by`. Cycle 5 on the same run recorded
confidence 0.62 normally. A confidence of exactly 0.0 on a parsed cycle looks
like a field that failed to populate rather than a desk with zero confidence
— and confidence is what the 0.55 risk gate reads, so a spurious 0.0 would
veto any entry regardless of the desk's view. Not yet reproduced; recorded
here so the next session checks it rather than rediscovering it.

## The attribution, measured — and it corrects my own emphasis

Every risk-stage refusal since 2026-09-03 (n=820):

| refusal | n |
|---|---|
| `decision is 'hold'` — the desk's own choice | **819** |
| `confidence 0.38 below threshold 0.55` — a gate vetoing the desk | 1 |

So the zero-trade state is overwhelmingly **the desk choosing to hold**, not
code blocking it. That is worth stating plainly because it bounds what
`entry_router` can achieve: the wake changes WHEN the desk is asked, which is
a hypothesis about why it holds, not a way around holding.

Confidence distribution over 828 decisions since 09-03: median 0.500, mean
0.493; 36.6% reach the 0.55 gate. Histogram (rounded): 0.3 -> 58, 0.4 -> 260,
0.5 -> 199, 0.6 -> 263, 0.7+ -> 40.

### The one authored buy, and what happened to it

    run 2630  DE (us-stock)  2026-09-04T15:56:03Z
    chair AMENDED action, confidence and report:
      "Bullish technical and sentiment signals outweigh the trader's weak
       hold rationale, prompting a low-confidence buy."
    -> gate_skip  risk: confidence 0.38 below threshold 0.55

In 828 decisions the desk authored exactly ONE entry, and a threshold refused
it. That is 100% of authored entries vetoed — but n=1, so it is registered,
not acted on. The experimental-mindset rule is explicit that one data point
is not a result, and this session has already killed one theory that rested
on a bad instrument.

**Registered watch, F-CONF:** if a SECOND authored entry is refused by the
confidence gate, that is reproduction and the gate is then a money path worth
changing. Note the tension is genuine and not obviously a defect: the chair
itself set confidence 0.38 while overriding to buy, so the gate is refusing a
shot the desk itself called low-conviction. The fix, if it comes, is more
likely "the chair must restate confidence when it overrides the trader" than
"lower the threshold".

## Falsifier v2 (owner-registered 2026-09-04, due 2026-09-05 04:00Z)

Terms: at least one authored buy/short decision by 04:00Z, else FAILED and
revert the risk tiers to 0.015/0.02/0.03/0.04 without debate.

**PASSES on its literal terms** — the DE buy above is an authored entry
inside the window. The tiers are NOT reverted.

Stated without varnish: it passes on a technicality worth naming. One
authored entry in 572 decisions, which never became a trade because a gate
refused it, is not evidence that the tier change works. It clears the bar
that was registered, and nothing more.

## Hourly monitoring cycle — 2026-09-05 02:14Z

**P&L first.** Both owner accounts: 0 executed trades all-time, $0 realized,
$0 unrealized, 0 open positions, cash exactly $10,000.00 each (the 08-31
reset baseline). Platform-wide the last executed trade was
**2026-08-16T21:00:04Z** — 19 days ago. Note this corrects the standing
memory line "zero trades since 08-29": 08-29 was the last buy DECISION; the
last FILL was 08-16.

No trades closed since the previous cycle, so the two-subagent outcome
analysis does not apply this cycle (there are no outcomes to attribute).

**Falsifier v2: PASSES.** One authored buy exists in the window (run 2630,
DE, conf 0.38, 2026-09-04T15:56:03Z). The risk tiers are NOT reverted.

**Process health.** Fleet 44 (crypto) 8/8 running. Fleet 43 (us-stock) 1/8,
`replenishing:1/8` — the US session is shut until 13:30Z and 40 symbol
cooldowns are active, so this is expected, not a stall; it should climb after
the open. Twelve `no_prospect_switched` in 6h across 8 crypto slots ≈ hourly
per slot, matching the 1h window shipped on 09-04.

### Last-fix verification — a false alarm I had to chase down

The raw check said 11 of 12 no-prospect switches were backed by decisions
with `decided_by=None`, which would mean scaffold/rule-authored switches and
a violated fix. **It is a false positive.** Inspecting those payloads: all 25
`decided_by=None` decisions in the 6h window carry a real report, none
contains the scaffold text "no LLM verdict", all carry conviction, and the
sampled report is a reasoned desk hold ("Bearish bias and lack of support
make a buy entry risky; better to hold"). Zero are `decided_by="rule"`.

So the fix HOLDS: **0 scaffold/rule-authored switches.** What is actually
broken is the instrument.

**INSTRUMENT GAP (reproduced, 62/62).** Cross-tab over 12h:

| | `decided_by` present | absent |
|---|---|---|
| payload carries `discussion` | 0 | **62** |
| no `discussion` | 198 | 2 |

`decided_by` is stamped in `analysis_agents.py` (the escalated panel path).
The non-escalated light-cycle builder at `run_engine.py:7106` constructs
`decision = {action, confidence, entry, report, scores}` and never sets it.
Those are the cycles that carry the three-agent `discussion`, so ~24% of the
tape cannot be checked for authorship — precisely the check the owner ordered
every cycle.

**Designed fix (NOT shipped this cycle):** label the light-path builder's
verdict, "ai" only when a trader verdict actually parsed, so the existing
scaffold/no-verdict path keeps its own label and the rule-hold guard is not
weakened by mislabelling a fallback as desk-authored. Held back because this
cycle's instruction was monitor-don't-redesign and the gap is a blind spot in
measurement, not a money path. It should ship next cycle.

Also seen: `confidence == 0.0` on 5 of 262 decisions in 12h, all in the
unlabelled group. Confidence is what the 0.55 risk gate reads, so a spurious
0.0 would veto an entry regardless of the desk's view. Not yet reproduced
often enough to act on; watch it.

**F-WAKE: 1 wake, 0 entries.** Refutation threshold is 20.

## Deployed — authorship label (5077adeb, 02:52Z)

`sooppiy-backend:20260905-20260905-authorship-label`, backend and worker
recreated. Rollback: `SOOPPIY_IMAGE=sooppiy-backend:20260905-20260905-entry-zone-wake`.

Local CI: ruff PASS, pytest PASS (5148 tests, 1349 subtests), frontend-build
PASS, npm-audit PASS, gitleaks PASS, pip-audit PASS. The full-suite job ran on
the identical code commit `5dac4093`; the only delta to `5077adeb` is a test
file, verified separately (20/20 on the rail suite, 736 adjacent tests, ruff
clean). What a local run does NOT give: a clean-room runner, a hosted audit
trail, any check needing provider secrets.

Adversarial review certified it with no BLOCKER, MAJOR or MINOR — seven
mutations attempted, seven killed, including both halves of the
belt-and-braces guard independently.

**Verified on prod after restart:** decisions carrying the three-agent
`discussion` now arrive labelled `decided_by="ai"`. That combination was
0 of 62 before the ship. Zero unlabelled decisions post-restart.

**Measurement trap hit and corrected in the act.** The first verification
window used a space-format cutoff (`2026-09-05 02:52:50`) against
`run_events.ts`, which is `T`-format. `'T'` sorts above `' '`, so the
comparison matched every row for that date and reported 50 "post-restart"
decisions in 46 seconds — including the 9 unlabelled rows the fix was
supposed to eliminate, which would have read as the fix failing. Re-run with
a `T`-format cutoff. This is the trap recorded in
[[mysql-timestamp-comparison-traps]], walked into anyway; it is the second
time this session a bad instrument nearly produced a false conclusion, after
the `entry` field that made 13.8% of decisions look in-zone.

## Hourly monitoring cycle — 2026-09-05 03:06Z

**P&L first.** Unchanged and still zero: both accounts 0 executed trades
all-time, $0 realized, $0 unrealized, 0 open positions, cash $10,000.00 each.
Zero trades in the v2 window. No trades have closed, so the two-subagent
outcome-analysis rule does not apply again this cycle.

Authored entries: **0 in the last hour** (20 decisions, all hold), 1 in 24h,
1 since the tier ship.

**FALSIFIER v2: PASSES — verified against every registered term.** The terms
are "by 2026-09-05 04:00Z … ≥1 buy/short decision on any fleet run (executed
or gate-demoted both count as authored)". Run 2630 (DE) is `fleet_id=43`,
`created_via='fleet'`, authored 2026-09-04T15:56:03Z — inside the 24h window
— and was gate-demoted, which the terms admit explicitly and in advance. The
risk tiers are NOT reverted. The pass rests on that one decision and no new
one has appeared since; it clears the registered bar and nothing more.

**Process health.** Fleet 44 8/8, fleet 43 1/8 (`replenishing:1/8`) with the
US session shut until 13:30Z and 39 cooldowns active — expected, not a stall.
Fourteen `no_prospect_switched` in 6h across 8 crypto slots ≈ hourly per slot.

**LAST-FIX VERIFICATION — now clean, and the false alarm is structurally
impossible.** Scoped to the labelled era (after 02:52:50Z):

    switches authored by real desk holds: 1/1   scaffold/rule-authored: 0
    decisions since deploy: 5 labelled, 0 unlabelled
    decisions carrying `discussion` now arrive labelled "ai" (was 0/62)

The 13 older switches are unlabelled *by construction* — `_light_analysis`
did not write the field before this morning — so counting them as
scaffold-authored is precisely the error that produced the 02:14Z false
alarm. The sweep is now scoped so it cannot repeat it.

### The wake and the switch rail work against each other (n=1, registered)

Run 2734, the woken LIT run, in order:

    01:29:46  hold  conf 0.62  (desk)
    01:59:02  ENTRY_ZONE_TOUCH  mark 4.74815 in its own zone 4.678-4.761
    02:05:42  hold             (the woken cycle — the desk, at its level)
    02:29:09  hold  conf 0.59
    02:29:16  no_prospect_switched -> symbol benched

The desk named a level, price reached it, the desk was asked there for the
first time and declined — and 24 minutes later the no-prospect rail retired
that symbol for having no prospect and benched it for 12h. The switch itself
was well-founded (every cycle from 00:00 was a hold, so the span and count
were met independently of the wake), so this is not a defect in either
mechanism. It is a conflict between them: price sitting AT the desk's own
authored entry zone is close to the definition of a prospect, and the rail
cannot see that.

Consequence for F-WAKE: if woken symbols are routinely rotated out shortly
after, the falsifier accumulates evidence very slowly and may never reach its
n=20. Registered as an observation on n=1. NOT acted on — this cycle is
monitor-don't-redesign, and one occurrence is not a result.

**F-WAKE: 1 wake, 0 entries** (threshold 20).

### Instrument discipline

The `T`-format comparison trap was hit TWICE more this cycle — once verifying
the deploy, once auditing post-deploy switches. `run_events.ts` and
`stopped_at` are `YYYY-MM-DDTHH:MM:SSZ`; `'T'` sorts above `' '`, so a
space-format cutoff matches every row of that date and makes the window
vacuous while looking like a large healthy sample. Both were caught by the
result being implausible (50 decisions in 46 seconds), not by care. The sweep
now carries the warning inline.

## Hourly monitoring cycle — 2026-09-05 03:44Z

**P&L first.** Zero again: both accounts 0 executed trades all-time, $0
realized, $0 unrealized, 0 open positions, cash $10,000.00 each. No trades
have closed, so the two-subagent outcome rule does not apply.

Authored entries: **0 in the last hour** (22 decisions, all hold), 1 in 24h,
1 since the tier ship.

**FALSIFIER v2: PASSES** (run 2630 DE, verified against every term last
cycle). Tiers NOT reverted. The deadline is 04:00Z and no new authored entry
has appeared, so it closes on that single gate-demoted decision.

**Process health.** Fleet 44 8/8, fleet 43 1/8 with the US session shut until
13:30Z, 41 cooldowns. Fifteen switches in 6h.

**LAST-FIX VERIFICATION — clean and now accumulating.** In the labelled era:
**4/4 switches desk-authored, 0 scaffold/rule** (was 1/1 last cycle). The 11
older switches are correctly excluded as unlabelled-by-construction.

### Why F-WAKE is still 1 — measured, not guessed

The wake has been live ~1h45m with one touch. Two candidate explanations
were on the table: rotation starving it, or the mechanism being broken.
Measured both.

**Rotation is NOT the constraint.** Median run lifetime before the
no-prospect rail rotates a symbol is **302 minutes (~5h)**, n=8, range
79-303. That is ample time for a wake. Last cycle's worry that woken symbols
get rotated away too fast is not supported at this n — run 2734 (79 min) was
the short outlier, not the norm.

**The constraint is the addressable population.** Snapshot of all 9 live runs:

| run | symbol | plan | distance to zone |
|---|---|---|---|
| 2732 | AAVEUSDT | zone | +6.29% away |
| 2736 | ACN | zone | **IN ZONE** (us-stock, market shut) |
| 2740 | HYPEUSDT | zone | +6.45% away |
| 2741 | ASTERUSDT | zone | +1.73% away |
| 2737, 2738, 2742, 2743 | LTC, SOL, FIL, ZEC | `trigger` | no numeric zone |
| 2739 | DOTUSDT | `none` | no plan |

So **only 4 of 9 runs (44%) carry a numeric zone the wake can act on at
all** — four outlooks express their entry as a text `trigger` ("breakout
above…") which `_live_entry_plan` deliberately refuses, and one has no plan.
Of the four zones, three are 1.7-6.5% away and untouched; the one that IS in
zone is `ACN`, a us-stock, with the NYSE shut — so the market-open guard is
correctly suppressing it, because a wake there could never produce a fill.

F-WAKE = 1 is therefore fully explained by the population, not by a broken
mechanism: 4 inapplicable plans, 1 correctly suppressed, 3 simply not
reached yet.

**Note against my own earlier claim.** The `entry_router` docstring says 82%
of outlooks carry a concrete zone. This snapshot says 44%. n=9 is far too
small to overturn the earlier figure, and the two measure different things (a
population of outlooks over time versus live runs at one instant) — but the
gap is large enough that the 82% should be re-measured before it is relied on
again. Recorded rather than quietly reconciled.

**Registered prediction (falsifiable, cheap):** run 2736 ACN is sitting in
its authored zone with the market shut. If price is still in that zone after
13:30Z, a wake must fire for it within one poll interval. If it does not, the
market-open guard or the us-stock path is broken and F-WAKE clause 1 gets
re-opened for that market.

## Hourly monitoring cycle — 2026-09-05 04:44Z

**P&L first.** Zero: both accounts 0 executed trades all-time, $0 realized,
$0 unrealized, 0 open positions, cash $10,000.00 each. No closed trades, so
the two-subagent outcome rule does not apply.

Authored entries: **0 in the last hour** (18 decisions, all hold), 1 in 24h,
1 since the tier ship.

**FALSIFIER v2: CLOSED — PASSED.** The 04:00Z deadline has passed (now
04:44Z) with one authored entry on the tape (run 2630 DE, fleet run,
gate-demoted, which the terms admit explicitly). `stop_loss_frac_of_bet`
stays at 0.03/0.05/0.07/0.10; **no revert**. It passed on one decision that
never became a trade — the registered bar, and nothing more.

**Process health — the first genuine improvement in days.** Fleet 43 climbed
**1/8 → 4/8** as benches expired (cooldowns 41 → 35); fleet 44 holds 8/8;
12 runs total. Thirteen switches in 6h.

**LAST-FIX VERIFICATION — accumulating clean:** **6/6 switches desk-authored,
0 scaffold/rule** in the labelled era (1/1 → 4/4 → 6/6 over three cycles).

### A validity defect in MY OWN falsifier, caught before it fired

Four us-stock runs read "IN ZONE" this cycle — ACN, CVX, META, DE. Every one
has `mark` exactly equal to the zone's HIGH. That is the same artifact shape
that produced the 13.8% false positive earlier today, so I tested it:

| run | zone | low / high | width |
|---|---|---|---|
| ACN | 185.3196 – 186.72 | 0.992500 | **0.7500%** |
| CVX | 207.29625 – 208.6 | 0.993750 | **0.6250%** |
| META | 612.144225 – 616.77 | 0.992500 | **0.7500%** |
| DE | 688.328525 – 693.53 | 0.992500 | **0.7500%** |

The low reconstructs from the high to six decimal places. These zones are
`[last_close × 0.9925, last_close]` — mechanically anchored to the frozen
close (the NYSE has been shut since 20:00Z), not judged levels. A support
level does not land on exactly 0.7500% of the close four times.

Contrast the one crypto zone, authored while its market was OPEN:

> HYPE: "the only high-expectancy long is a pullback into 77.5-79.0 with
> volume confirmation, not a chase at 83.92" — round numbers, 6.29% below
> price, and a stated reason.

**Two different behaviours are being counted as one thing.** A close-anchored
band is "reached" the instant it is written; a pullback level has to actually
be traded to. When the NYSE opens at 13:30Z, if price opens anywhere near
yesterday's close, four wakes fire immediately — and they would test nothing,
because no level was reached in any meaningful sense.

**F-WAKE amended (registered now, before those wakes exist).** Wakes are
counted in two classes and BOTH are always reported:

- **Class A, pullback wakes** — the zone's high sat meaningfully below the
  mark at the time the outlook was authored. These test the timing theory.
  Clause 2's refutation threshold (≥20 with 0 entries) applies to Class A
  ONLY.
- **Class B, close-anchored wakes** — `zone_high ≈ mark_at_authoring`. These
  are reported but excluded from the threshold.

**Stating the obvious objection against myself:** excluding Class B makes
n=20 SLOWER to reach, which delays the refutation of my own ship. That looks
self-serving and I am not going to hide it. The defence is that a criterion
which counts a band drawn around the current price as "price reached the
desk's level" does not measure the hypothesis at all — and the mitigation is
that both counts are reported every cycle, so nothing is buried. If Class A
never accumulates, that is itself the answer, and clause 4 (selection is the
real constraint) takes over.

**F-WAKE: Class A = 1, Class B = 0** (threshold 20 on Class A).

### Population snapshot (12 live runs)

numeric zones 5 · trigger-only 6 · none/no-outlook 1. Crypto — the only open
market — carries exactly ONE numeric zone (HYPE, 6.29% away), which is why no
wake has fired since 01:59Z. The wake cannot act on a `trigger` plan by
design, and 6 of 8 crypto runs are trigger-only right now.

## THE HOLD WALL, LOCATED — and removed (owner 2026-09-05)

Owner: "if continue hold then we will be remove desk hold logic."

Four ships yesterday fixed four real rails and the trade count stayed at
zero, because none of them was the wall. Measured on the live tape since
2026-09-04:

| | n |
|---|---|
| desk proposed an entry | **435** (367 buy, 67 sell) |
| escalation panel answered `hold` | **434** |
| survived | **1** |
| orders refused by the risk gates | **1 in 625 decisions** |

The cheap-tier desk wants to trade every cycle. The panel kills 99.8% of
what it proposes. Every no-trade day since 2026-08-16 was authored there.
This also explains why the earlier fixes changed nothing: they were all
upstream or downstream of the only step that mattered.

Hold reasons, 90 reports since 00:00Z (multi-label): macro/regime caution
83%, entry/price wrong 59%, overbought/exhaustion 53%, risk arithmetic 53%.
Verbatim: *"The proposal to 'buy now instead of waiting' is a chase, not a
thesis"*. The panel is reviewing genuine motions and refusing nearly all.

**Shipped (f528b691):** a `hold` verdict on a PROPOSED ENTRY is journaled
(`panel_verdict`, `veto_overridden`, `panel_reason`) and then overridden —
the desk's order stands. The panel keeps everything else: it meets, it
reviews, it may substitute its OWN order (buy -> sell is honoured untouched,
because substituting an order is not vetoing one) and it may hand back a
tighter bracket, which is adopted. Kill switch `PANEL_ENTRY_VETO=1`.

**Owner rule 2026-08-13 — stated precisely, because a capability WAS
removed.** The order is still authored by the sooppiy AI either way: code
invents no order, and both the proposing desk and the panel are that AI.
Which voice is final when the two disagree was always a code decision — it
was the panel by construction, not by anyone's ruling — and it has moved to
the desk that spoke first. What genuinely changed is that the deliberation
can no longer reach one particular conclusion. Saying "the rule is
untouched" would let a future session miss that. Given 434 of 435, the
owner chose to remove exactly that capability.

**SCOPE, wider than the name suggests.** The override keys off the VERDICT,
not the proposal, so a panel hold on a desk SELL of a held book, or on a
RETIRE (flatten), is overridden too. That is deliberate and protective — the
platform does not second-guess a reduction, and a panel able to veto an exit
could trap a losing book. The flag is `PANEL_ORDER_VETO`, not
`PANEL_ENTRY_VETO`, for that reason, and the exit case is pinned by test.

**A 16x dollar-risk hole, caught in review before deploy.** The first
version adopted the panel's whole order block with a `# tighten, never
cancel` comment and no comparison. Measured through the real clamps: desk
`{size_frac 0.25, stop_pct 2.0}` against a hold-voting panel returning
`{size_frac 1.0, stop_pct 25.0}` shipped `size_frac 1.0, stop_pct 8.0` —
leverage and stop are clamped downstream, size is NOT — 4x the size at 4x
the stop distance, using numbers authored by the voice that said don't
trade. Now only strictly smaller `size_frac`/`leverage`/`stop_pct` are
taken, only when both sides named a value; `target` is never taken, because
reshaping the payoff is not tightening risk.

### Will the confidence gate just become the new wall?

Measured before deploying, because if so the ship is theatre. The 439
proposed entries carry median confidence **0.600**, mean 0.621:

    clear a 0.55 gate:  419/439  (95.4%)
    histogram: 0.4->1  0.5->19  0.6->237  0.7->169  0.8->13

No. The proposals sit well above the gate — which is also why carrying the
DESK's confidence rather than the panel's matters: the panel's confidence on
a hold is a hold's confidence, and using it would have moved the veto one
door down and changed nothing.

### Correction: the "1 in 625" argument was wrong

The commit first argued this change was low-risk because the risk gates
refused only 1 order in 625 decisions. That reasoning does not hold, and
adversarial review killed it: the denominator counts DECISIONS, and holds
never reach the gates at all. With the panel killing 434 of 435 proposals,
**the gate stack was asked roughly once.** The same statistic is equally
consistent with "the gates refused the only order they ever saw".

So the gates are untested at volume, and this change routes hundreds of
orders into them for the first time in 19 days. The honest framing is that
the first window is a **test of the gate stack**, not of the desk. On
simulator accounts that costs paper, which is exactly why it is worth doing
— but it must be watched as a stress test, not reported as a safe change.

### Registered falsifier — F-VETO

1. **The panel was the wall** (supported) if >=1 order EXECUTES within 2h of
   the switch. Slots are the natural bound: 12 runs, one position each, so
   this cannot become unbounded churn — a filled slot stops proposing.
2. **REFUTED — the wall is downstream** if entry proposals continue and 0
   orders execute after 2h. Then the panel was never the binding constraint,
   this ship must be reported as FAILED in those words, and the next
   suspects are the expectancy gate, fee-edge, and bracket feasibility.
3. **The panel was RIGHT to veto** if trades execute and realized P&L is
   materially negative over the first 20 closed legs. Report P&L first, with
   and without the largest contributor; if stripping the largest flips the
   sign, INCONCLUSIVE. This is the outcome I am least able to predict and it
   must not be spun: a 99.8% veto rate could have been protecting the book.
4. **Churn check:** if executed trades exceed ~4 per slot per day, the
   spacing/fee rails are not holding and that is its own defect.

Reporting obligation either way: profit or loss first, process second.

### Four review rounds before this touched prod

The first version of this change was not safe. Adversarial review found, in
order: a 16x dollar-risk hole (the panel's order block adopted wholesale —
`# tighten, never cancel` was a comment, not code); a wrong safety argument
(the "1 in 625" statistic counts DECISIONS, and holds never reach the gates,
so the gate stack had been asked roughly ONCE); an undocumented exit scope;
`size_frac 0` adopted as "smaller", which would have cancelled orders
through sizing — the veto through the back door, invisible, with the ship
appearing to work while trading nothing; the exit inversion (`smaller` means
a smaller EXIT on a reduction — a hold-voting panel could retain 70% of a
book the desk wanted out of); and its mirror, `buy` closing a SHORT, which
`run_cycle` maps to `cover` only AFTER the panel runs, so a verb-only
predicate called it risk-increasing.

Final state: 10 mutations attempted, 10 killed; 16 quadrant cases verified
independently on both spot and futures books; 1033 adjacent tests; CI green
on all six jobs (5176 tests).

I also caught one of my own: the first exit fix was pinned ONLY by a direct
`_tighter_order(reducing=True)` unit test, so hardcoding the call site's flag
to False passed all 56 tests. That is the fifth instance in two days of the
unit-vs-wiring gap.

**Registered MINOR (shipped knowingly, not fixed).** `held` is read before
the meeting and feeds only the keep/narrow classification — action and
sizing basis both re-read the position, so staleness cannot corrupt either.
Two transitions are reachable if a stop fires mid-meeting: a flattened long
with a proposed `sell` sizes to $0 and dust-skips (wasteful, harmless); a
covered short with a proposed `buy` stays a long ENTRY sized off max_bet —
$10,000 where narrowing would have made it $3,000, so an unintended long is
3.3x larger. The underlying "buy-to-cover whose short vanished becomes a
long entry" hazard is pre-existing and independent of this change; only the
size is affected, and every downstream gate still applies. Fix if it ever
reproduces: re-read `_position_quantity` after the panel returns and fall
back to the narrowing branch when the sign changed or went to zero (~3
lines, fails safe).

## THE FIRST TRADE IN 20 DAYS — and why it must not be called a success

Deployed `20260905-panel-no-veto` (`181da98`) at 06:00Z. **13 minutes later
an order executed.** The last previous fill was 2026-08-16.

    signal 1566  run 2740  HYPEUSDT  BUY  1.11436 @ 84.105
    notional $93.72 = 0.94% of the $10,000 account
    stop 83.8527 (0.30%)   target 84.8619 (0.90%)   R:R 3.00
    risk at the stop: $0.28      unrealized at the time of writing: -$0.08

**F-VETO clause 1: SUPPORTED.** Two overrides fired, both `buy -> buy`, one
executed and one was refused by the confidence gate (0.45 below 0.57). The
panel WAS the wall. Four ships that fixed real rails did nothing; removing
the veto produced a trade in thirteen minutes.

**And now the honest part, which is more important than the trade.**

**1. The desk bought the chase its own outlook forbade.** Thirty minutes
earlier, run 2740's own outlook read: *"Uptrend intact but stretched into
resistance on thin volume; wait for a dip into 78-79 rather than chase 6%
above entry."* It then bought at 84.105 — 6.5% above the top of the zone it
had named. The panel's objection was the same one: *"RSI ~70 into resistance
on volume"*. Removing the veto did not make the desk trade well; it made the
desk's FIRST voice final, and that voice contradicted its own standing plan.

**2. The trade that executed is not the trade the desk authored.** Its
report asked for *"a 5% stop and 12% target"*. What shipped was a 0.30% stop
and a 0.90% target. The order_params notes give the mechanism:

    "stop_pct -5 raised to floor 0.3"
    "target_pct 12 pulled to R:R ceiling 0.9 (3x stop 0.3)"

The desk emitted **-5**, meaning "5% below entry". The rail correctly refuses
a negative stop and raised it to the floor; the R:R ceiling then pulled the
target down to 3x that floor. A 5% stop became 0.30% — **16.7x tighter** —
and the target collapsed from 12% to 0.9%.

**REPRODUCED, not a single data point:** across 654 order_params events since
09-04, the stop was raised to the floor 15 times, and in **9** of those the
desk's authored value was negative. This is a sign-convention loss between
the desk's prose and the parser, not an outlier.

**3. This CONFOUNDS F-VETO clause 3, and I am flagging it before the result
exists rather than after.** Clause 3 says: if trades execute and P&L is
materially negative over the first 20 closed legs, the panel was right to
veto. That reading is not available while the stop bug is live. A 0.30% stop
on a crypto name at RSI 70 will be taken out by ordinary noise, so a loss
would attribute to the CLAMPED STOP, not to a bad entry. This codebase has
already measured that too-tight stops are themselves a loss engine.

Any P&L verdict on the veto removal must therefore either wait until the
stop convention is fixed, or explicitly separate legs stopped out inside
0.5% from legs that reached a genuine invalidation. I will not report a loss
from a 0.30% stop as evidence that the panel was right.

**Not fixed this cycle, deliberately.** Shipping a stop-handling change now
would confound the F-VETO window that just opened — two changes, one window,
no attribution, which is the exact error the joint-window note records from
yesterday. It is registered as the next ship.

## Hourly monitoring cycle — 2026-09-05 06:18Z (first cycle with a book)

**P&L first.** Two fills, both still open, **zero closed legs** — so the
two-subagent outcome rule does not apply this cycle either.

    agent 6  : 2 fills, realized +0.00, unrealized +0.02, cash 9,825.71
    agent 60 : 0 fills, flat, cash 10,000.00

    HYPEUSDT run 2740  1.11436 @ 84.1050  mark 84.000  uPNL -0.117  stop 0.30%
    LITUSDT  run 2749 17.20765 @ 4.67720  mark 4.6850  uPNL +0.134  stop 1.00%

Deployed capital $174.21 = 1.74% of the account. **Fees already paid $0.078
against +$0.02 unrealized, so the book is net -$0.06 all-in.** No verdict is
available and none is claimed.

Authored entries: **4** since the tier ship (1 before the veto removal, 3
after, in 15 minutes). Falsifier v2 PASSES on four now rather than one.

**Process health.** Fleet 44 8/8, fleet 43 4/8, cooldowns 34. Last-fix
verification **10/10 switches desk-authored, 0 scaffold/rule**.

### Both fills bought ABOVE the zone the desk itself named

| run | its own zone | filled at | above the zone top |
|---|---|---|---|
| 2740 HYPE | 77.5 – 79.0 | 84.105 | **+6.5%** |
| 2749 LIT | 4.20 – 4.35 | 4.6772 | **+7.5%** |

2 of 2. The desk names a pullback level in its outlook and then buys at
market when asked. This is the exact behaviour `entry_router` was built to
serve — and it shows the wake is not the binding constraint on entry
QUALITY: the desk does not wait for its level, it just was not previously
allowed to buy at all. Removing the veto produced trades; it did not produce
patience.

**`plan_adherence` is not a trustworthy audit field.** Run 2749 filled 7.5%
above its own zone and self-reported `plan_adherence: "followed"`. Run 2740
correctly said `"deviated"`. The field is self-declared by the model, not
computed against the authored zone, and it was wrong on the larger of the
two deviations — in the permissive direction. Distribution on buy decisions
since 09-04: followed 4, deviated 1. Do not use it as evidence of plan
discipline without recomputing against the zone.

### A SECOND bracket convention defect

Alongside the sign slip recorded last cycle, run 2749 shows a unit slip:

    "bracket interpreted as percent fractions (unit slip: every authored
     pct field sub-floor — stop_pct 0.01 -> 1, target_pct 0.03 -> 3)"

Counts since 09-04: **stop raised to floor 12** (the sign slip, which
DESTROYS the desk's intent — 5% became 0.30%), **unit slip 2** (which the
rail CORRECTS to 1%/3%). Two different conventions arriving from the desk,
one recovered and one not. LIT got a 1.00% stop because its slip was the
recoverable kind; HYPE got 0.30% because its slip was not.

**Still not fixed, still deliberately.** F-VETO opened 18 minutes ago with
two live positions; changing stop handling now would put two changes in one
window with no attribution. It remains the next ship, and F-VETO clause 3
remains unreadable until it lands.

## Outcome analysis — first trades (two-agent rule, 2026-09-05 06:33Z)

### THE PLATFORM REPORTS A WIN ON A TRADE THAT LOST MONEY

Verified independently, twice, from the raw ledger:

    LIT round trip:  gross move      +0.067110
                     fees BOTH sides  0.072465
                     TRUE all-in     -0.005356
                     signals.pnl says +0.030862
                     difference       0.036218  == exactly the ENTRY fee

`signals.pnl` nets **only the exit-side fee**. Every realized figure taken
from it is biased favourable by one entry fee per round trip. My own earlier
report of "gross +$0.0309" used this number and was WRONG — that is the
exit-netted figure, not gross.

This extends the standing rule (`realized-pnl-misses-forced-flattens`) with a
second, sharper reason: raw `signals.pnl` is wrong on ORDINARY closes too,
not only forced flattens. Use `pnl_audit.replay_realized`.

### The entries, measured (Agent A, spot-checked by me)

Seven AI-authored entries, six filled, one closed. **7 of 7 were panel holds
that the veto removal overrode.** Six of six contradicted the desk's own
last written plan; five of six were placed against its own **flat** bias.
Two claimed an exchange listing that appears in **none** of the four analyst
briefs. Verified by me directly:

- **LTC** — outlook 05:51 said bias FLAT, trigger "hold above 51.58 with
  volume >1.0x AND crowding below ~2.0", **take-profit 53.5**. It filled at
  **53.574 — above its own take-profit**, 29 minutes later, with neither
  trigger condition cited as met.
- **FIL** — outlook said bias FLAT, "long ONLY on decisive close above 0.85".
  It filled at **0.77088, 9.3% BELOW that**, inside the range it had just
  called "no confirmed edge either direction".

`plan_adherence` self-reported `"followed"` on five of six. It is
self-declared, not computed against the plan, and it is wrong in the
permissive direction.

**A correction to my own framing.** I called these "chases". Agent A measured
position in the 24h range and refuted it for HYPE: 17.7%, the bottom fifth —
not a chase at all. LTC (93.9%) and FIL (87.9%) are. And HYPE/ENA/FIL's own
levels were never touched in 24h; HYPE re-published the identical 77.5-79.0
zone six cycles running while price never came within 5.5%. So a large part
of the gap is the desk **naming stale, unreachable levels it never
re-anchors** — a different defect from chasing, and it points at the outlook
refresher rather than at entry timing.

### ROOT CAUSE of the -5 stop — it is the PROMPT, not the model

Agent A could not determine this; the prompt text settles it
(`run_engine.py:6902`):

    "stop_pct = % from entry to your invalidation level"

Nothing states that this is a POSITIVE MAGNITUDE. For a long, the
invalidation IS below entry, so a model reasoning "5% below" writes `-5`
correctly under a signed reading. The rail then refuses the negative and
floors it to 0.30%, and the R:R ceiling drags the target from 12% to 0.9%.

That makes the fix a one-line prompt clarification, not a parser change:
state that stop_pct/target_pct are positive distances regardless of
direction. **Registered as the next ship.** Counts since 09-04: 12
stop-raised-to-floor, 2 unit slips.

### Expectancy: INCONCLUSIVE, and stated as such

ENA is the only winner (+0.447). Per owner rule 6, stripping the largest
contributor flips the gross to **-0.430**. The sign flips, therefore the
result is INCONCLUSIVE. What is NOT inconclusive is the fee: **$0.4156 of
round-trip cost is already spent** on $542.26 of deployed capital (0.0900%).

n=1 closed leg over 33 minutes. No expectancy verdict is available and none
is claimed.

## Two-agent cross-check — where they DISAGREE is the finding

**Realized, ledger replay (`trading_runs.realized_pnl_usd`, three agreeing paths):**

    LTC  +0.031062   closed by trailing_lock after 14m22s
    LIT  -0.005356   closed by trailing_lock after  3m36s
    NET  +0.025707   100% ALGORITHM-authored; the desk authored zero exits

**INCONCLUSIVE per owner rule 6**: n=2, and stripping the largest contributor
(LTC) leaves a loss. Fees consumed **86% of the gross realized edge**
($0.1826 gross move against $0.1569 of fees). $0.3225 of fees paid in total.

### The disagreement

- **Agent A**: the entries are bad — 6/6 against the desk's own written plan,
  5/6 against its own flat bias, 2/6 on a catalyst in no brief.
- **Agent B**: "No realized loss is attributable to the desk's entries in
  this window" — the algorithm authored every dollar.

**Both are right, and the resolution matters.** A characterised trades using
gross mark-to-market on OPEN positions; B refused to, correctly — an
unresolved mark is not a loss. On *realized money* B is right and I side with
it. On *forward risk* A is right: entries placed against the desk's own plan
are a real hazard that simply has not been paid for yet. A finding that
reads an open mark as a result is exactly what the owner's law forbids.

### My own fee argument was REFUTED, and I am recording that

I argued the 0.30% clamped stops are negative-expectancy because fees
(0.090%) are 30% of the stop distance, giving a 32.5% breakeven hit rate
against a 25% random-walk rate. **Agent B refuted it with better arithmetic**:
that geometry is net R:R 2.08:1, which is survivable on its own. My
random-walk model assumed the stop or target resolves the trade. **Neither
does — the ratchet fires first.**

### The actual loss engine: the ratchet arms at fee scale, not at bracket scale

`_breakeven_arm_usd` arms at `0.045% x 2 x 1.78` = **0.160% of notional**,
a constant that knows nothing about the authored stop or target. Verified by
my own cross-check:

| authored stop | arm vs the target | worst case: ratchet-at-arm vs stop | breakeven hit rate |
|---|---|---|---|
| 0.30% (clamped) | 5.6x closer | +0.035% vs -0.390% = **1:11.1** | **91.7%** |
| 2.50% (as authored) | 31.2x closer | +0.035% vs -2.590% = **1:73.8** | **98.7%** |

**The correctly-bracketed trades have WORSE geometry than the clamped ones.**
The floor is anchored to the FEE, so wins are capped at fee scale while
losses stay at stop scale — and the wider the desk's authored stop, the worse
the ratio. This is the 10:1 shape `order_params` exists to make
inexpressible, reintroduced downstream by a component that never sees the
target.

Caveat stated honestly: those are worst-case (peak exactly at the arm). At
the platform's own measured median peak/arm of 1.18x the 2.50% case is still
about 1:52. And n=2 fires, so the ratchet's net contribution is INCONCLUSIVE
— it must not be reported as positive either.

### The ratchet's own fee-floor guarantee is fictional under polling

The code promises "round trip in, best case exactly $0 net". Both fires
landed BELOW their own floor because marks are polled ~63s apart and the
check is `current <= floor`:

    LIT  slipped $0.0362 below floor (a FULL fee leg) — band was $0.0309 -> LOSS
    LTC  slipped $0.0125 below floor                  — band was $0.0435 -> profit

One rule predicts both, 2/2: **slip > half the net peak => net loss.** The
difference between the two trades was poll timing, not analysis.

**ASTER near-miss:** low 0.729610 against a clamped stop of 0.729535 — it
survived by 0.0102% of entry, 3.4% of its stop distance, seven minutes in.
Under the desk's authored 5% stop it was never remotely at risk.

### Two changes now meet the reproduced-evidence bar

1. **Prompt sign fix** (root cause found this cycle): `stop_pct = % from entry
   to your invalidation level` never says POSITIVE MAGNITUDE. 3/3 sign-slip
   positions, 12 floor-hits since 09-04. One line.
2. **Ratchet arm scale**: 2/2 fires slipped below their own floor; the arm is
   a fee-scaled constant against a bracket-scaled stop.

**Neither shipped.** This cycle is monitor-don't-redesign, and I have changed
nothing on prod.

## 06:49Z — F-VETO clause 3 has its first real evidence, and it is AGAINST the ship

**Realized, ledger replay, since the switch: −$0.414006.** Closed round
trips only: LIT −0.005356, LTC +0.031062, **ASTER −0.274156** = −$0.248450.
The rest is entry fees already booked on four still-open positions. Ten
fills, **$0.4068 of fees paid**.

Owner rule 6: ASTER is the largest contributor and stripping it flips the
closed-trip sum to +0.025706. **Sign flips, so the aggregate remains
INCONCLUSIVE** — but the ASTER trade itself is not inconclusive at all.

### Two corrections to my own reading, made before drawing conclusions

**1. ASTER was NOT stopped out.** I assumed my own prediction had come true.
It had not. Agent B had flagged ASTER's 0.0102% near-miss on its clamped
0.30% stop, and I read the close as that stop firing. It was not: the DESK
sold it (`decided_by: ai`, confidence 0.8) at 06:48:54.

**2. Agent B's "no realized loss is attributable to the desk's entries" was
true at 06:36 and is false at 06:49.** The largest realized loss is now
AI-authored. Findings expire; this one expired in thirteen minutes.

### The ASTER exit is a loss my own change caused

    desk   : sell, confidence 0.80 — "Close the long position immediately to
             avoid potential losses from a volatile market and breached
             support levels."
    panel  : HOLD — "The 0.80 sell proposal claims 'breached support levels,'
             but the tape contradicts it: price 0.7298 holds cleanly above
             MA5/MA20/MA60/MA200, and the loss of MA20 at 0.6865 that would
             actually invalidate..."
    result : veto_overridden = true. Exit filled. −$0.274156 all-in.

**The desk exited on a premise the panel demonstrated was factually false,
and the panel had the tape on its side.** The veto would have prevented this
loss. This is the exit path I kept open DELIBERATELY, on the reasoning that
"a panel able to veto an exit could trap a losing book" — that reasoning
produced its first bill within 49 minutes.

Whether holding ASTER would have been profitable is unknown and I am not
claiming it. What is established: the decision was made on a false stated
premise, the reviewer that catches false premises was disabled by my change,
and the trade lost money.

**n=1. Not enough to revert on, and I am not reverting on it.** Registered as
the leading candidate: if a SECOND override produces a loss whose stated
premise the panel refuted on the tape, the exit-side override goes back
(`PANEL_ORDER_VETO=1` restores it without a deploy) and this ship is reported
FAILED on the exit path in those words.

Note the asymmetry this exposes in my own design: on ENTRIES the panel was
wrong 434 times out of 435 by the only test that matters — it produced zero
trades for 19 days. On EXITS it may be right, because an exit has a concrete
factual premise the panel can check against the tape, while an entry is a
forecast it cannot. That distinction was not in the original reasoning and it
should have been.

## Still open

- **9 of 15 zones were never touched at all in 24h.** No wake mechanism can
  help a level price never revisits. That is momentum selection naming
  levels its own picks have already left behind — `entry_funnel`, not yet
  shipped.
- `_PENDING` is in-process: a worker restart drops pending wakes (fail-safe)
  but also drops suppression, so a crash-looping worker becomes a wake loop.
  Deliberately left as a comment rather than a mechanism: persisting it would
  cost a DB write per wake to save at most one LLM cycle per restart.
- `_PENDING` / `_SUPPRESS_UNTIL` / `_LAST_POLL` are never evicted for
  terminated runs, so a long-lived worker leaks one entry per retired run.
  `stop_router` has the same shape, so this is pre-existing, not new.
- Fence strip in the panel proposal context is case-sensitive.
- `RR_FLOOR=0.2` is no longer binding under the 2.5/5.0 geometry.
