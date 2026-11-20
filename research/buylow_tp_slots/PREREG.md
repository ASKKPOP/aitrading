# Pre-registration — "10 slots · buy low · sell at +X% · repeat"

Written 2026-11-19 BEFORE any backtest result was seen.

## The algorithm under test (owner spec, 2026-11-19)

1. The user creates N = 10 slots.
2. Each free slot BUYS when the AI judges the price "low".
3. The slot is monitored; when price reaches entry × (1 + X) — X = 10 %, 12 %
   or any user-set value — it SELLS.
4. Repeat 1–3 forever.

The spec has no stop-loss and no time limit. That is tested as written, and
two protective variants are tested next to it.

## What cannot be replayed

The live AI's notion of "low" cannot be replayed on 2020–2026 history (the
desk did not exist, and its prompts change). It is replaced by deterministic
"buy-low" proxies, each a common definition of a dip:

- `dip7d`   close ≤ 0.85 × highest high of the last 168 h (15 % off the 7-day high)
- `drop24`  close ≤ 0.92 × close 24 h earlier (−8 % in a day)
- `rsi25`   RSI(14) on 1-h closes < 25
- `random`  null: a random eligible coin the hour a slot frees (100 seeds)

The prior on the live AI: four replications (09-08, 10-05, 11-06, and the
11-06 z −4.6 read) found the desk's entries no better than a random minute,
so the `random` null is the honest stand-in for "AI-decided low" until the AI
beats it on tape.

## Hypotheses and falsifiers

- **H1 (take-profit makes money):** TP-only, 10 slots, X = 10 % ends with
  mark-to-market equity above the start in every start-date cohort.
  *Falsified* if any start cohort ends below start equity, or if realised
  P&L is positive while mark-to-market is negative (the bag-holding case).
- **H2 (buying the dip is an edge):** at least one dip proxy beats the
  random-entry null's median final equity AND sits above its 90th
  percentile. *Falsified* if every dip proxy is inside the null's 10–90 band.
- **H3 (it beats doing nothing clever):** the best configuration beats an
  equal-weight buy-and-hold of the same universe over the same window.
  *Falsified* if it does not.
- **H4 (the target level matters):** final equity varies with X across
  {3, 5, 8, 10, 12, 15, 20, 30} % by more than the random-seed spread.
  *Falsified* if the spread across X is inside the seed spread.
- **H5 (a stop helps):** adding a 15 % stop or a 30-day time stop raises the
  worst-cohort result. *Falsified* if it lowers it.

## Mechanics (fixed before running)

- Binance spot 1-h bars, 35 coins (see fetch.py), 2020-01-01 → 2026-11-19.
  Survivorship: delisted coins (LUNA, FTT, …) are absent — this biases every
  result IN FAVOUR of a no-stop strategy, so a failure here is conservative.
- $10,000, 10 slots × $1,000; each slot compounds its own proceeds; at most
  one slot per coin.
- Signal on a completed bar's close; buy at the NEXT bar's open + 5 bp slip.
- Fee 10 bp per leg (Binance spot default); sensitivity at 4.5 bp (the
  platform's simulated fee).
- TP is a resting limit: fills at entry × (1+X) when a later bar's high
  reaches it. Stop fills at the stop − 5 bp; if stop and TP sit inside the
  same bar the STOP is assumed first (conservative).
- Start cohorts: 2020-01-01, 2021-11-10 (cycle top), 2022-06-01, 2024-01-01,
  2025-01-01. All cohorts end 2026-11-19 (mark-to-market at last close).
- Benchmarks: equal-weight buy-and-hold of the coins listed at the cohort
  start; BTC buy-and-hold.

## Deviations (recorded honestly, 2026-11-19)

1. **US stocks added after this file was written** — the owner narrowed scope
   mid-session to "only spot and USA stock". The stock universe (55 names,
   `fetch_stocks.py`), daily-bar thresholds (dip = close ≤ 0.90 × 20-session
   high, drop = −4 % in one session, RSI(14) < 30), fee 1 bp/leg, time stop
   21 sessions and cohorts 2016-01-04 / 2020-02-19 / 2021-11-10 / 2022-06-01 /
   2024-01-02 / 2025-01-02 were fixed BEFORE any stock result was seen, but
   they are not in the original pre-registration.
2. **Dip rules also run as a distribution** — seed 0 = deepest dip first (the
   pre-registered rule); seeds 1…S = a random pick among the coins whose dip
   signal fired. A single deterministic path proved chaotic (one different
   pick early changes every later trade), so H2 compares the dip-rule
   median against the random null's percentiles.
3. **Delist exit** — EOS stops trading on Binance 2025-05-26 (renamed). A
   position whose series ends > 30 days before the grid ends is closed at the
   last close (optimistic vs. a real delisting). The first version of this
   rule also fired on 19 stock files that merely ended one session early —
   found by the independent verifier, fixed, all grids re-run.
