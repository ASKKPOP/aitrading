# Research — "10 slots · AI buys low · sell at +X % · repeat" (2026-11-19)

**Owner request (2026-11-19):** a new algorithm. (1) The user makes 10 slots.
(2) Each slot buys when the AI decides the price is low. (3) The slot is
monitored and sells at +10 %, +12 % or any user-set rise. Repeat 1–3.
Scope set by the owner mid-session: **spot and US stocks only, no futures.**

**Verdict, in profit-or-loss terms first: as specified, this loses money.**
Every closed trade is a winner (99.9–100 % closed-trade win rate). Even so,
every slot eventually ends up holding a loser that never comes back. In crypto
spot, the median portfolio ended **−59 % to −82 %** in four of five start
dates. In US stocks it made money in absolute terms, but it lost to simply
holding the same stocks in all six start dates. The "buy low" step did not
help: dip-buying rules were *worse* than a random entry in about three cells
of four.

Pre-registration, scripts and summaries: `research/buylow_tp_slots/`
(`PREREG.md` was written before any result; deviations are listed at its end).

## 1. Method (summary)

- **Data:** Binance spot 1-hour bars, 35 coins, 2020-01-01 → 2026-11-20. The
  set is 5 majors plus 30 liquid alts from 2020–22, chosen *before* any result.
  US stocks use daily bars for 55 names, 2016-01-04 → 2026-11-19: megacap tech,
  the Dow 30 and 2020–21 high-flyers.
- **Portfolio:** $10,000 in 10 slots of $1,000. Each slot compounds its own
  proceeds, and at most one slot holds a given symbol.
- **Orders:** signal on a completed bar, buy at the next open + 5 bp.
  Take-profit is a resting limit at entry × (1+X). Fees are 10 bp/leg for
  crypto spot (4.5 bp sensitivity) and 1 bp/leg for stocks. When a stop and
  the target sit in the same bar, the stop is assumed to fill first.
- **"AI decides low" cannot be replayed on history.** It was replaced by three
  common dip rules and a **random-entry null**:
  - `dip`: 15 % below the 7-day high (stocks: 10 % below the 20-day high).
  - `drop`: −8 % in 24 h (stocks: −4 % in one day).
  - `rsi`: RSI14 < 25 (stocks: < 30).
  - Random null: 50 seeds for crypto, 200 for stocks.

  Four earlier measurements of the live desk (09-08, 10-05, 11-06 ×2) found
  its entries no better than a random minute. The random null is therefore
  the honest stand-in for the AI until the AI beats it on tape.
- **Exits tested:** the spec (take-profit only), take-profit with a 15 % stop,
  and take-profit with a 30-day time stop. Targets swept: 3, 5, 8, 10, 12, 15,
  20 and 30 %.
- **Start dates:** crypto 2020-01, 2021-11 (cycle top), 2022-06, 2024-01,
  2025-01. Stocks 2016-01, 2020-02, 2021-11, 2022-06, 2024-01, 2025-01. All
  are marked to market at the last bar.
- **Survivorship:** delisted names (LUNA, FTT, …) are absent. This biases
  every result **in favour** of a no-stop strategy, so the failure found here
  is conservative.

## 2. Results — the spec (TP 10 %, no stop)

Final equity of $10,000. "Random" is the null spread. "Realized" and
"unrealized" are the random-entry medians.

**Crypto spot**

| start | random p10 / p50 / p90 | dip / drop / rsi p50 | EW hold | BTC hold | realized | unrealized | slots stuck at end | worst slot | max DD |
|---|---|---|---|---|---|---|---|---|---|
| 2020-01 | 15,740 / 30,562 / 80,674 | 15,982 / 8,598 / 5,107 | 99,596 | 85,583 | +273,348 | −248,854 | 10/10 | −100 % | −87 % |
| 2021-11 | 1,124 / 1,798 / 2,696 | 801 / 719 / 1,724 | 3,732 | 9,198 | +3,665 | −11,809 | 10/10 | −100 % | −84 % |
| 2022-06 | 1,830 / 3,875 / 8,158 | 1,949 / 1,659 / 3,900 | 8,456 | 19,364 | +17,230 | −23,646 | 10/10 | −98 % | −83 % |
| 2024-01 | 2,465 / 4,086 / 7,036 | 2,697 / 1,487 / 3,385 | 14,354 | 14,563 | +15,254 | −21,039 | 10/10 | −98 % | −81 % |
| 2025-01 | 2,057 / 2,853 / 3,990 | 2,234 / 1,608 / 3,784 | 7,386 | 6,581 | +2,910 | −9,987 | 10/10 | −97 % | −78 % |

**US stocks**

| start | random p10 / p50 / p90 | dip / drop / rsi p50 | EW hold | EW ex-best | SPY | realized | unrealized | stuck | worst slot | max DD |
|---|---|---|---|---|---|---|---|---|---|---|
| 2016-01 | 33,521 / 54,076 / 91,547 | 77,273 / 64,235 / 37,651 | 157,592 | 113,998 | 42,458 | +68,431 | −25,886 | 10/10 | −94 % | −45 % |
| 2020-02 | 14,755 / 21,558 / 31,437 | 16,342 / 17,387 / 24,084 | 31,578 | 28,243 | 23,308 | +21,460 | −10,550 | 10/10 | −95 % | −43 % |
| 2021-11 | 9,191 / 13,698 / 18,431 | 5,447 / 6,095 / 10,119 | 15,122 | 14,137 | 16,439 | +9,675 | −5,880 | 10/10 | −91 % | −45 % |
| 2022-06 | 15,469 / 20,020 / 27,155 | 19,318 / 21,236 / 29,761 | 23,595 | 20,704 | 18,314 | +16,779 | −6,650 | 10/10 | −79 % | −23 % |
| 2024-01 | 12,276 / 15,259 / 19,250 | 11,277 / 13,463 / 15,876 | 17,404 | 16,015 | 15,658 | +9,870 | −4,563 | 10/10 | −66 % | −20 % |
| 2025-01 | 10,881 / 13,215 / 16,243 | 11,396 / 13,123 / 15,190 | 13,258 | 12,639 | 12,385 | +6,625 | −3,517 | 10/10 | −56 % | −20 % |

TP 12 % gives the same picture (`summary_*.txt`).

## 3. Hypotheses — verdicts

| | hypothesis | verdict | evidence |
|---|---|---|---|
| H1 | TP-only ends above start in every cohort | **FALSIFIED** (crypto) | crypto ended −59…−82 % in 4 of 5 cohorts. In **every** cohort and both markets, realized P&L is positive while mark-to-market is far worse (the bag-holding case). |
| H2 | a dip rule beats random entry | **FALSIFIED** | Stocks: a dip-rule median beat the random median in 103 of 432 cells (24 %), and sat below the random p10 in 141. Crypto: 97 of 360 (27 %), below p10 in 159. `rsi` on crypto is the only rule near even (62/120 above p50), and it is not consistent across cohorts (2020: 5,107 vs 30,562). |
| H3 | the best config beats buy-and-hold of the same universe | **FALSIFIED** | Random-entry p50 is below EW hold in all 11 cohorts. It is below BTC hold in all 5 crypto cohorts. With the single best stock removed from the benchmark, it is still below in 5 of 6. Of those, 2021-11 and 2022-06 are within the seed spread, and 2025-01 is above it (13,215 vs 12,639). |
| H4 | the target level matters | **mostly falsified for 10 vs 12** | 10 % and 12 % are inside the seed spread everywhere. A *higher* target tends to be better (30 % ≥ 10 % in 10 of 11 cohorts, TP-only), because it cuts winners less. |
| H5 | a stop / time stop helps | **FALSIFIED** (crypto), neutral (stocks) | A 15 % stop lowered the crypto median in all 5 cohorts (2020: 30,562 → 4,498). It sells the dip and rebuys the next dip. The 30-day time stop was also worse in crypto. In stocks both were between −14 % and +6 % of the spec. |

## 4. Why it loses — the mechanism

1. **It cuts the winners and keeps the losers.** A winner is sold at +10 %,
   but the returns of both markets live in a few huge winners: NVDA 186× from
   2016, PLTR 18× from 2022. A loser is held for as long as it takes, which
   for an alt that falls 95–99 % means forever.
2. **A stuck slot is an absorbing state.** Each sale hands the slot's money
   to another coin. Sooner or later every slot lands in a coin that never
   returns +10 %, and then it stops trading. That is why the median run ends
   with **10/10 slots stuck** in every cohort of both markets.
3. **The win rate is an illusion.** The user would see ~100 % winning trades
   and a rising "realized profit" while the account is down 80 %. Crypto
   2021-11 median: realized +$3,665, unrealized −$11,809.
4. **"Buy low" picks falling knives.** A coin 15 % off its high is, on
   average, the coin that keeps falling. This is the same finding as the four
   desk replications: no entry edge.
5. **Bear-market end date:** the tape ends with BTC −51 % and most alts −90 %
   or more from their highs. Measured instead at 2024-12-31, the 2022-06 and
   2024-01 crypto cohorts beat EW alts (16,999 vs 14,094; 15,208 vs 14,377).
   They still lost to BTC (29,179; 21,945). The strategy is a bull/chop
   strategy that gives everything back in a bear market. Max drawdown
   −78…−87 % in crypto does not depend on the end date.

## 5. Exploratory (post-hoc, not pre-registered)

On a blue-chip-only universe (5 crypto majors, 5 slots; or 10 megacap stocks,
10 slots), the loop degenerates into buy-and-hold with extra trades: with as
many slots as names, every slot just re-buys the same names. It is not a
consistent edge:

- Stocks, TP 10 %, vs EW hold: 2016 230k vs 471k (**−51 %**: NVDA sold at
  +10 % over and over); 2020 −9 %; 2021 −4 %; 2022 +11 %; 2024 +5 %;
  2025 −3 %.
- Crypto, TP 10 %: within −9…+0 % of EW hold in 2021, 2022, 2024 and 2025.
  2020 shows +52 %, but the comparison is unfair. SOL lists in 2020-08, so
  the EW basket (coins listed at the start) leaves it out, while the strategy
  can buy it. This is a likely artefact, not verified trade by trade.

## 6. Verification

- **Pass 1, independent:** a subagent re-implemented the engine from the spec
  without importing it. It matched the engine exactly: stock 2021-11 dip
  5,632.92, 24 trips, 10 open; crypto 2022-06 dip 1,783.2267, 71 trips. It
  hand-checked 5 trips against raw bars. It also **found a defect in my
  engine**: a "delist" exit fired on 19 stock files that simply ended one
  session early, which flipped realized P&L in some runs. Fixed (a series is
  dead only if it stops > 30 days before the end), all grids re-run.
- **Pass 2, accounting identities over all 140,082 runs:** final = $10,000 +
  realized + unrealized (0 breaks); trips = sum of exit reasons (0 breaks);
  zero losing closed trades in TP-only runs other than the EOS rename exit.
  The EOS exit is optimistic: it closes at the last price.

## 7. Recommendation

- **Do not ship this as a profit strategy.** No tested variant beat holding
  the same assets: no dip rule, no target level, no stop, no time stop.
- **If the owner wants it as a user-configurable product anyway** (spot / US
  stock, long-only, user-set X), it must not be sold on its win rate. The UI
  must show mark-to-market and stuck-slot age next to realized P&L, or users
  will see "100 % wins" on an account that is down 80 %.
- **What would change this verdict:** the AI's "low" call beating the random
  null on live tape, with the permutation test from `sooppiy-entries-carry-no-edge`
  at n ≥ 300. That has failed four times. Until it passes, the "AI decides
  low" step adds no money.
