# Payoff-ratio exit replay — H-PAYOFF refuted (2026-11-21)

Owner ask (2026-11-20): "fix the stop-loss vs ratchet payoff ratio", after
fleet 54 lost $3.93 realized in its first 4.5 h — three desk stops at
+2.5–2.7% (−$3.32) against nine breakeven-ratchet exits that netted −$0.02.

**Verdict: no exit geometry fixes the payoff ratio on this tape. Nothing
shipped.** Every setting that improves P&L does it by holding directional
exposure longer, and the gain is mirror-symmetric on random entries: about
+$X on random shorts and −$X on random longs. That is a bet on market direction,
not a payoff fix.

## Hypothesis and falsifiers (written before the replay)

H-PAYOFF: some exit geometry (stop distance, ratchet arm, lock fraction,
target), applied to the desk's ACTUAL entries, beats the current rules on
both time halves of the window.

Refuted if any of these hold:

- (a) the baseline replay does not reproduce actual P&L;
- (b) the first-half winner fails on the second half;
- (c) the same geometry gains as much on random-time entries (beta, not
  payoff);
- (d) the sign flips when the largest contributor is removed.

## Data

- 354 closed crypto round trips, 2026-11-03 → 11-21, rebuilt from
  `run_events` `trade` payloads. The `signals` table keeps only 306 rows,
  so older legs are gone from it.
  - 350 trips are fleet 44, 15 are fleet 54, all from agent 6.
  - Every trip is a 1x futures short.
- The desk's own bracket comes from `bracket_reanchor` (`stop_after` /
  `tp_after`, available on 340 trips). The median stop is 2.5% (p10 2.0%,
  p90 2.5%) and the median target is 5.0%. The horizon comes from
  `order_plan.horizon_until`.
- Actual results: net +$1.05 across 245 wins (avg +$0.10) and 109 losses
  (avg −$0.214). Fees were $11.97.
  - The payoff ratio is 0.47 at a 69.2% win rate. The breakeven win rate
    at that payoff is 68.2%, so the book sits at breakeven.
- Prices: Hyperliquid 5m candles (the platform's crypto feed). Market drift
  over the window:

  | Coin | Drift |
  |---|---|
  | BTC | −23.9% |
  | ETH | −29.4% |
  | SOL | −26.1% |
  | AAVE | −23.6% |
  | HYPE | −30.4% |

## Replay validation (falsifier a)

The current rules replayed (desk stop, desk target, ratchet armed at one
round-trip fee, lock 0.5) give +$1.63, against an actual +$0.36 on the same
340 trips.

- Per-trip correlation is 0.59; signs agree on 235 of 340 trips.
- Exit mix: 326 ratchet, 12 stop, 2 target.
- Of the 13 actual stop exits, 7 replay as stops.

The replay is faithful to about ±$1.3. Any effect smaller than that is noise.
The causes are 5-minute candles against the platform's ~60 s mark polling,
and fills at the floor price against real slippage.

## Grid: 224 geometries

Ranges tested:

- stop at 0.4–2.0x the desk stop, or no stop;
- ratchet arm at one round-trip fee, 0.2%, 0.4%, 0.8% or 1.5% of
  notional, or off;
- lock at 0.5, 0.75 or 0.9;
- target from the desk, or none.

167 of the 224 geometries beat the current rules on both halves (split at
11-17T12:27Z). The first-half winner also wins the second half. Falsifiers
(b) and (d) pass, and on their own would look like a strong result.

## The null kills it (falsifier c)

Each trip was re-run at a random entry minute (same coin, size, horizon and
bracket), 40 draws for shorts and 20 for shorts plus longs.

| Geometry (stop×, arm, lock, target) | Desk Δ | Random-short Δ | Random-long Δ |
|---|---|---|---|
| No stop, no ratchet, no target (hold to horizon) | +337.30 | +263.75 | −263.73 |
| Stop 2×, no ratchet, no target | +304.34 | +222.29 | −228.85 |
| Desk stop, no ratchet, desk target | +173.94 | +144.60 | −133.25 |
| No stop, arm 1.5%, no target | +175.54 | +134.60 | −146.12 |
| Stop 0.4×, no ratchet, no target | +148.36 | +88.27 | −72.60 |
| Desk stop, arm 0.4%, desk target | +20.59 | +16.45 | −20.08 |
| Desk stop, arm 0.2%, desk target | +11.19 | +5.33 | −8.02 |
| Desk stop, fee arm, lock 0.75, desk target | +0.13 | −0.23 | −0.21 |

Δ is each geometry's P&L minus the current rules' P&L, in USD.

- Every geometry that raises the payoff ratio takes the same dollars from a
  random long as it gives a random short. The improvement is short exposure
  in a market that fell 24–30%, and it reverses in a rally.
- The current tight geometry is the setting that limits that exposure. Under
  it, random shorts lose $4.85 and random longs $18.35 over the window.
- Second pass with seed 2026: the symmetry holds (hold to horizon +245.13 /
  −248.41; desk stop with desk target +131.29 / −131.31).
- A lock of 0.75 or 0.9 is neutral (within ±$1 across both seeds). Tighter stops with the ratchet
  on lose money: 0.4–0.6x stops come out between −$11 and −$12. That agrees
  with the 09-08 H-STOP refutation.

## Entry edge (the 09-08 gate, re-run on fresh tape)

Under the current rules the desk's entries made +$1.63, against a random-short
mean of −$3.37 (sd 6.26):

- z = 0.80;
- 17.5% of random draws beat the desk;
- without NEAR (the largest single coin, −$2.83) the desk figure is +$4.46.

That is inconclusive and does not show an entry edge, which replicates
[2026-09-08 noise floor](2026-09-08-noise-floor.md). Overlapping trips (the
same coin in the same hour) shrink the effective n, so even the 1.9–2.1 z
values for the hold-longer geometries overstate the evidence.

## What this means

- The payoff ratio is not a defect in the exit rails on its own. With no
  entry edge, exit geometry only trades win rate against payoff and adds
  directional exposure; it cannot create expectancy.
- Fleet 54's −$3.93 came from three 2.5% stops in an up-move, inside a
  window that is ±$0 overall. One bad 4-hour stretch is n=3 and supports
  no change.
- **Do not re-run:** "let winners run / widen or remove stops / raise the
  ratchet arm" on a one-way tape without a two-direction null. It will
  always look like a large win in a trend.
- A real payoff fix has to come from entry selection: entries whose timing
  beats random at the traded horizon. Until such an edge is shown, keep the
  current rails.

## Limits

- One regime only: a steady 17-day decline. There was no rising window to
  test directly. The random-long arm stands in for one.
- 5-minute candles, with ±$1.3 replay error on 340 trips.
- Entries were single-leg (first fill, total size). Desk partial covers were
  not modelled; they are only 11 of 354 exits.
- No live-mark counterfactual was needed, because nothing shipped.
