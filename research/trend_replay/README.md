# Trend module — independent historical replay (2026-10-05)

Reproduce-or-refute replay of `service/server/trend_module.py`. Every decision
is made by the module's own functions (`evaluate_symbol`, `wilder_atr`,
`position_qty`, `update_trail`, `check_exit`) at its default parameters; this
directory only walks the calendar and books fills and costs.
`PREREG.txt` was written before the first replay run and has not been edited.

## Commands (repo root)

```bash
PY=.venv/bin/python
# 1. data (already cached in data/; re-fetching changes the end date)
$PY research/trend_replay/fetch_data.py daily     # OKX <SYM>-USDT-SWAP 1D, confirmed bars
$PY research/trend_replay/fetch_data.py hourly    # OKX 1H (~15 min, 21 MB)
$PY research/trend_replay/fetch_data.py fng       # alternative.me F&G (secondary run S1)
$PY research/trend_replay/fetch_data.py funding   # BitMEX funding proxy (post-hoc S4)
# 2. replays — offline, deterministic
$PY research/trend_replay/replay_daily.py         # -> trades.csv, trades_S1_fng.csv, result.json
$PY research/trend_replay/replay_forming.py       # -> trades_forming_hourly.csv, forming_result.json
# 3. verification — imports neither trend_module nor replay_lib
$PY research/trend_replay/handcheck.py
```

## Files

| file | what |
|---|---|
| `PREREG.txt` | hypothesis, criteria, every replay convention, fixed before the run |
| `fetch_data.py` | candle / F&G / funding fetch, raw strings cached to `data/` |
| `replay_lib.py` | loaders, the completed-bar engine, statistics |
| `replay_daily.py` | primary run + verdict + permutation + secondary runs |
| `replay_forming.py` | hourly forming-bar replay, comparison, live-fill check |
| `handcheck.py` | independent re-derivation of best/worst/median trade and of the whole trade list |
| `trades.csv` | every primary-run trade |
| `result.json` | every primary figure, with n |
| `trades_forming_hourly.csv`, `forming_result.json` | forming-bar replay |
| `trades_S1_fng.csv` | trade list with the Fear & Greed overlay on |

## Result (primary, pre-registered)

OKX swap `1D` bars (16:00 UTC open), 2020-01-01 → 2026-10-04 bar; first
eligible bar 2020-07-28 (BTC/ETH/XRP), SOL from 2021-08-18, BNB from 2023-07-19.

| criterion | result |
|---|---|
| 1 net > 0 | **+114.15R** ($2,853.65), n=115 |
| 2 payoff ≥ 1.5 | **2.95** (avg win $85.67, n=54; avg loss $29.06, n=61) |
| 3 ex best trade / ex best symbol | **+87.46R** (n=114) / **+72.05R** without BTC (n=89) |
| 4 ≥5 of 7 years positive | **7/7** — 2020 +22.2 (n=7), 2021 +12.4 (22), 2022 +13.0 (13), 2023 +13.0 (19), 2024 +37.5 (24), 2025 +2.3 (18), 2026 +13.9 (12) |
| 5 permutation p < 0.05 | **p = 0.002** (9 of 5000 shuffles ≥ observed) |

**Verdict: NOT FALSIFIED.**

Other figures: win rate 47.0%; median trade −0.26R; mean +0.99R; 18.6
trades/yr; longest losing streak 11 (2024-06-08 → 2024-08-28); max drawdown
20.2R on closed trades (2024-03-22 → 2024-12-10, 263 days, ended by the single
best trade) and 25.0R marked to market daily (2024-03-13 → 2024-11-12,
recovered 2024-11-30); longest time under a prior high 507 days (2022-06-18 →
2023-11-07). Long +107.1R (n=66, payoff 4.22); short +7.1R (n=49, payoff 1.48,
in a 23.3R drawdown since 2022-07, not recovered). Entries from 2023 on:
+66.9R (n=72, payoff 3.29), +40.2R without the best trade.

## What weakens it (read before quoting the table)

* **Not pre-registered, added after seeing the result** (`post_hoc_not_preregistered`
  in `result.json`):
  * a null that moves all trades by one common date shift (keeps the
    clustering of trades across symbols): **p = 0.020** (44 of 2258 shifts) —
    ten times weaker than the pre-registered p;
  * perp funding, proxied with BitMEX rates (OKX history is not public that
    far back): **−20.6R**, leaving +93.5R, 2025 at +1.7R.
* Secondary runs: F&G overlay on (the rule as the live code runs it when a
  reading exists) **+90.8R, n=121**; fill at the signal close +114.1R; universe
  without BTC rerun +67.5R (n=96).
* One trade (XRP long 2024-11-12, +26.7R) is 23% of the total; time-stop
  exits carry +125.9R of the +114.2R.
* Biases that cannot be removed: the universe is five coins that are large
  **today** (chosen with hindsight); trades cluster in the same episodes, so
  115 trades are far fewer independent bets; there is one historical path and
  it contains two crypto bull legs; the LLM veto cannot be replayed.

## Forming-bar finding

Code path: `tasks.py:918-943` (hourly loop) → `trend_module.py:528`
(`evaluate_symbol(_get_bars(symbol), …)`) → `trend_module.py:271-273` →
`price_fetcher.py:1060` (`fetch_candles(symbol, bar="1D", limit=days)`) →
`crypto_feed.py:138-177`, which never reads OKX's `confirm` flag and keeps the
newest (forming) row. Exits use the same window (`trend_module.py:485-496`).
With Redis up the candles are cached 6–7.5 h (`price_fetcher.py:1038,1099`).

Hourly forming-bar replay, full history: n=164, **+92.9R** (completed-bar:
n=115, +114.2R). 63 entries (38%) happen on a bar whose close does not
confirm them; those net **−2.2R** (median −1.04R, win rate 32%). 25
completed-bar entries are missing. 6-hourly sampling: +109.2R / +91.1R
depending on phase. 2025 turns negative in the hourly run (−3.0R).

The forming replay also reproduces a second live behaviour: the exit
idempotency key `trend:{agent}:{symbol}:exit:{utc-date}` refuses a second
exit of the same symbol on one UTC date, so a stop-out is deferred to
midnight UTC (9 occurrences).

## Intraday-stop variants (PREREG section E, appended before the run)

```bash
$PY research/trend_replay/replay_stops.py       # -> trades_V2.csv, trades_V3.csv, trades_V3b.csv, stops_result.json
$PY research/trend_replay/handcheck_stops.py    # independent check from raw 1H rows
```

| run | n | net R | payoff | win rate | years + | max DD (closed) | ex best trade | ended by intraday stop |
|---|---|---|---|---|---|---|---|---|
| primary (daily-close exits only) | 115 | +114.15 | 2.95 | 47.0% | 7/7 | 20.2R | +87.46 | — |
| V2 module stop enforced on 1H bars | 118 | +122.87 | 3.58 | 45.8% | 7/7 | 14.6R | +96.18 | 57 |
| V3 foreign 5% stop + phantom slot (prod today) | 115 | +71.42 | 4.79 | 33.0% | 7/7 | 12.3R | +55.53 | 72 |
| V3b foreign 5% stop, slot freed | 136 | +98.90 | 5.20 | 33.8% | 6/7 | 13.6R | +83.00 | 85 |

H-STOP (V3 < primary): **not falsified**, V3 is 42.7R lower. V3's 72 stopped
trades returned −49.8R against −7.1R for the same trades in the primary:
48 did better (losers cut earlier, +27.3R), 24 did worse, of which 16 were
primary winners (−70.0R). One trade is −27.4R of that (XRP long 2024-11-12:
stopped 13 hours after entry, +26.7R in the primary); without it the paired
difference is still −15.3R. V2's 55 paired stops: +9.75R (50 better, 5 worse).
No open trade lacked 1H coverage.

## R-LONG and R-STOCK (PREREG sections F and G, appended before the runs)

```bash
$PY research/trend_replay/fetch_stocks.py     # Yahoo chart API, 35 tickers, 2014-01-02 -> last completed session
$PY research/trend_replay/replay_long.py      # -> trades_RLONG_D.csv, trades_RLONG_V2.csv, long_result.json
$PY research/trend_replay/replay_stock.py     # -> trades_STOCK_{U1,U2}_{LS,LO}.csv, stock_result.json
$PY research/trend_replay/handcheck_ext.py    # independent reproduction of all six runs + best/worst/median
```

`replay_ext.py` is the shared engine; `replay_long.py` aborts unless it
reproduces `trades.csv` and `trades_V2.csv` exactly.

| run | n | net R | payoff | win | years + | max DD | ex best trade | perm. p | verdict |
|---|---|---|---|---|---|---|---|---|---|
| R-LONG daily-close | 66 | +107.09 | 4.22 | 48.5% | 6/7 | 7.9R | +80.40 | 0.004 | NOT FALSIFIED |
| R-LONG V2 | 68 | +107.92 | 4.72 | 47.1% | 6/7 | 8.2R | +81.23 | 0.003 | NOT FALSIFIED |
| R-STOCK U1 long/short | 339 | +115.67 | 1.82 | 45.4% | 12/12 | 13.9R | +103.51 | 0.19 | INCONCLUSIVE (5) |
| R-STOCK U1 long-only | 250 | +133.71 | 1.84 | 50.0% | 11/12 | 12.7R | +121.55 | 0.44 | INCONCLUSIVE (5) |
| R-STOCK U2 long/short | 543 | +34.67 | 1.58 | 40.7% | 8/12 | 41.7R | +26.27 | 0.73 | INCONCLUSIVE (4, 5) |
| R-STOCK U2 long-only | 414 | +69.39 | 1.50 | 45.2% | 8/12 | 30.8R | +55.14 | 0.91 | INCONCLUSIVE (4, 5) |

R-LONG: the long-only run takes exactly the primary's 66 long trades — no
long trade was added, lost or changed by freeing the short slots. 2022 has
no trade; 2025 is +0.6R (n=10) and 2026 +0.4R (n=4).

R-STOCK: every run is net positive and every run fails the permutation
test. Holding the same names, on the same side, for the same number of
sessions from a random date earns on average +82.5R (U1 L/S), +129.0R (U1
long-only), +63.5R (U2 L/S), +123.8R (U2 long-only) — as much as or more
than the rule. The profit is the drift of stocks that are in these lists
because they rose; the rule's timing adds nothing measurable. Shorts lose in
both universes (U1 −16.4R, n=97; U2 −30.1R, n=172). Reversing the scan order
moves U2 long/short to +17.1R and U1 long/short to +96.4R.
