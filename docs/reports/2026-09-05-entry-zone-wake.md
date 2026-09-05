# Entry-zone wake — the desk is asked at the wrong price 98.4% of the time

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

All **4** of the in-zone asks were holds. n=4 is far too small to conclude
anything, and one of the four (LIT, minute 4.7345-4.8211 vs zone
4.678-4.761) only clipped the zone with its low. But it is the only direct
evidence we have about what the desk does when asked at its own level, and
it is not encouraging. It is recorded here so that no later session can
claim this ship was justified without it.

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
   cache; unthrottled this was ~480-780 live fetches/hour inside the SERIAL
   control pass that also evaluates stops, each with a 10s timeout, and a 429
   trips the provider-wide cooldown that starves the marks the stop system
   reads. `ENTRY_ZONE_POLL_SEC` default 300 = the platform's existing mark
   cadence.
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

### Does a 300s probe defeat the purpose?

No, and it was measured rather than assumed. All 6 touched symbols had at
least one in-zone episode of 36-117 minutes, so a 5-minute grid is
guaranteed to land inside each. The 36/62 episodes shorter than 5 minutes
that a probe can miss are redundant — they are re-touches of zones already
caught by a long episode. Against a status quo of sampling once an HOUR this
is ~12× finer, and paying a systemic feed risk to chase sub-5-minute wicks
is a bad trade.

## Still open

- **9 of 15 zones were never touched at all in 24h.** No wake mechanism can
  help a level price never revisits. That is momentum selection naming
  levels its own picks have already left behind — `entry_funnel`, not yet
  shipped.
- `_PENDING` is in-process: a worker restart drops pending wakes (fail-safe)
  but also drops suppression, so a crash-looping worker becomes a wake loop.
- Fence strip in the panel proposal context is case-sensitive.
- `RR_FLOOR=0.2` is no longer binding under the 2.5/5.0 geometry.
