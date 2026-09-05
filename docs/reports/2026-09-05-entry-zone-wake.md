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
