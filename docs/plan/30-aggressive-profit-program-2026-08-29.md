# Plan 30 — Aggressive-Profit Program (2026-08-29)

**Owner order (2026-08-29):** "analysis make profit for 20 hours monitoring (We need
very Aggressive trading), and research from online and our history" — executed
"working with 5 agents", then "QA 5 agents", plus "we need Price forecast data
from online" and "Don't forget human fact".

**Method:** five analysis agents (A tape / B history / C experiment / D online /
E adversary), each audited 1:1 by a paired QA agent that re-derived every
load-bearing number by an independent route. Only claims that survived BOTH
waves appear below. Where QA corrected a number, the corrected value is stated
and the original is struck in-line.

Authority: this plan extends Plan 29 (does not replace its Phase-4 gates) and
binds to the experimental-mindset rule — nothing ships without an experimental
result, and every ship carries a pre-registered falsifier.

---

## 1. The 20-hour tape (2026-08-28T07:00Z → 08-29T03:15Z) — verified twice

- **Net +$0.3989 realized on $464.76 entry notional, 2 trips, both winners,
  both closed by the #592 breakeven-ratchet trailing lock** (BNB short +$0.1082;
  LINK run 2235 short +$0.2907, fees 34.2% of gross). Book flat at window end.
- Honest cross-boundary view (QA-A): since 08-27T00:00Z it is **4 trips, 3 wins /
  1 loss (LIT −$0.5451), net +$0.8405**. The LIT loss fell 17h before the window.
- **#592 tally advances to n=3 of 30, 3/3 positive fires** (TAO +$0.9868,
  BNB +$0.1082, LINK +$0.2907), all `breakeven_ratchet`. n=9 breakeven readout
  (pre-committed, reading #75) is the next checkpoint.
- **Throughput is the binding constraint, and it worsened:** panel kept 2 of 105
  proposals = **1.90%** vs all-time **5.95%** (84/1,412 — QA-A; the old "4.36%
  (21/482)" baseline no longer reproduces on today's tape and is retired).
  Treadmill: 117 runs started / 115 stopped in 20h (80 idle_retired), 1,189
  decisions → 2 entries. Agent 6's 17 runs produced zero fills.
- Process health good: 0 tracebacks since 02:16Z, no-verdict 3/1,189 = 0.25%,
  one #591 local-fallback panel activation (run 2182).

**Reason-level verdict:** the two exits were authored by the machine and both
banked profit — exit machinery did its job at small scale; the book earned
almost nothing because the panel passed 1.9% of candidates. Profit constraint =
entry channel, not exit quality, on this tape.

## 2. The decisive experiment — fee-sensitivity sweep (pre-registered in #77; run and audited)

Rebuilt from prod (original replay artifacts were never committed): 1,208
demoted proposals → 1,129 entries → 1,115 simulated through the committed house
rails; port differentially verified against `research/zi_control_replay.py` to
7.1e-15 (QA-C re-proved with its own 600-trial test).

| RT fee | mean eq-wt (CI90) | median | % pos |
|---|---|---|---|
| 9bp taker (booked) | **−17.89bp** [−21.7, −14.1] | +1.23bp | 52.4% |
| 3bp maker | **−13.89bp** [−17.7, −10.2] | +5.19bp | 57.9% |
| 0bp | −11.89bp | +7.33bp | 60.3% |
| 0 fee + 0 slip (exact re-walk, QA-C) | **−6.14bp** | +11.43bp | 67.2% |

**The falsifier did NOT fire: NO SIGN FLIP at any fee level — "no edge" is not
a fee-modelling artifact.** The mean is gross-negative before any cost, CI90
excluding zero. Cause, measured: exit mix **ratchet 754 / horizon 188 / stop 167 /
target 6 — a 28:1 stop:target hit ratio** (QA-C: zero same-candle stop+target
cases, so not adjudication bias). This is Plan 29's payoff-ratio diagnosis
re-measured on the blocked book.

**But the maker lever is real and secondary:** +4.0bp on the replay mean,
+2.7bp on the realized ledger; the replay median flips well positive at maker
(+5.19bp) and the 57-trip crypto cohort moves from median −5.75 → **+0.25bp**,
total −$6.60 → **≈breakeven** (QA-C: −$0.40..−$0.65, NOT the +$0.08 first
reported — softened accordingly). Maker fill reality: a limit at signal price
is traded through within 30min on **95.4%** of crypto entries, but 83% of exits
are momentum-adverse (necessarily taker); the honest mixed case is mean
−15.83bp / median +3.33bp.

Realized ledger (n=289 since 08-13): mean +0.85bp with CI spanning zero at
booked fees; the −$168.84 dollar total is **sizing concentration** (agent 5,
08-12/13) and survives even at zero fee (−$147). Expectancy is statistically
zero; the dollars were lost by size placement.

## 3. What survives from our history (QA-B audited; grades adjusted)

**Proven, cheap, unfixed money-path defects (all re-verified against live code on main):**
1. `BREAKEVEN_FEE_RATE=0.001` vs booked 0.00045 (`run_engine.py:914`) — ratchet
   arm demands 2.22× the real round trip; positions run effectively rail-less.
2. Desk bracket discarded on 23.9% of entries when `order_params` absent
   (`run_engine.py:7480-7486`) → flat 5%/10% `DEFAULT_LIMITS`, legs 3.30×
   further than authored.
3. Expectancy gate never called on the replacement path that builds 95.1% of
   runs (`_bucket_expectancy_block`: sole call `fleet_planner.py:1847`;
   `fleet_supervisor` comments claim a gate that is not below).
4. `backtest_gate.py:209-222` short fail-open (shorts admitted unscored).
5. `trading_runs.realized_pnl_usd` 98.4% zeros and load-bearing in the
   admission gate; `symbol_research.py:234` FEE_LEG_PCT=0.1 hardcode and
   `routes_signals.py` stale flat `TRADE_FEE_RATE` import.

**The one replay-proven positive mechanism, still unimplemented:** the resting
price-level ratchet lock — level fill counterfactual **+$3.00 aggregate, 0/9
fires worse; strip-largest +$1.78, 0/8 worse** (08-24 replay; QA-B re-verified
numbers and confirmed no intrabar fill path exists in code — stops evaluate
only at polled marks). #77's live fire lost 125% of its keep to exactly this gap.

**Downgraded by QA:** the #66 rail-sweep "monotone dial" holds only on grid
averages (3/14 cells are counterexamples); any rail-geometry lever built on
that sweep stays dead (#67). Maker-fee lever = now MEASURED by §2 (was
untested this morning).

## 4. Online research — price-forecast data (owner ask), QA-D verified by live API probes

Ranked by (evidence of skill × integration ease × cost). The strong sources are
all **free**; the paid "AI forecast" services are marketing (TokenMetrics,
Glassnode self-published studies, 95%+ accuracy claims — no independent
evidence; academic LSTM baseline ≈52% directional).

1. **Funding rates + `predictedFundings`** (Hyperliquid `POST /info`, keyless —
   probe-verified; Binance/Bybit public). Evidence: BIS WP1087 (verified
   verbatim): carry ≈7%/yr 2019–2024, spikes >40%, driven by trend-chasing
   leveraged retail longs. Caveat: post-ETF arbitrage capital is compressing it.
2. **Deribit DVOL** (public API, probe-verified, BTC+ETH) — variance-risk-
   premium spikes precede large moves; regime/magnitude signal, not direction.
3. **Kalshi crypto threshold markets** (15min/hourly/daily BTC-ETH-SOL;
   market data keyless, probe-verified; reading data unrestricted). Calibration
   caveat (QA-D): the good Brier numbers are measured 12–24h pre-resolution
   where calibration is trivially good — treat as probability INPUT, prove
   value at OUR horizons before trusting.
4. **Polymarket** (already integrated) — extend to crypto price-threshold
   markets, same probability-line format, same caveat.
5. **Binance positioning endpoints** (L/S ratios, OI — free) — crowding flag,
   not a validated forecast. **Operational blocker: geo-blocked from US IPs
   (prod is us-west) — needs a proxy decision or Hyperliquid-only equivalent.**

**Acceptance test for ANY forecast feed (adversary's, adopted as law):** logged
ex-ante into our DB, our symbols, our horizons (2–8h), ≥30 days shadow;
cluster-collapsed CI90 of net bp/trip excluding zero; and it must beat
random-side AND always-long on identical paths (the bar the internal AI
currently fails: random +1.01, always-long +5.27 vs AI on the demoted cohort).
A feed that cannot beat always-long is a cost, not a signal.

## 5. The human factor (owner: "Don't forget human fact")

1. **Markets:** the best-evidenced forecast inputs are crowd-psychology gauges —
   funding = trend-chasing retail longs paying to hold (BIS), L/S ratios and
   F&G are the same crowd read through different windows. The standing owner
   direction (08-14: weight psychology harder in us-stock/forex) carries into
   the desk prompt work in P30-D.
2. **Our own AI's psychology:** the panel demotes 98.1% out of caution and
   leaves 101 bytes of rationale; the desk states brackets in prose that the
   platform discards; conviction numbers carry zero information (r=−0.039).
   These are behavioral defects of the decision layer and are treated as such.
3. **The owner:** aggressive is a risk-tolerance statement. This plan spends
   aggression where it is cheapest (frequency of MEASURED experiments, breadth
   toward low-fee markets) and refuses it where our own tape shows it kills
   (size — armed once at 20× on a size-blind experiment; negative skew means
   the tail carries the book).

## 6. The program

Ordering law (from the audited adversary case): **frequency < breadth < size**
in risk; nothing scales until the mean is ≥0 on replay with cluster-collapsed
CI90. Honest current bar: median winner 7.8bp vs 9.0bp taker RT (~1.2–1.5×
short — NOT the earlier "21bp/2.7×", which double-counted; QA-E). At maker the
bar is 3bp and the median trip already clears it.

**P30-A — Fix the floor (the five defects, §3). Each = code fix + replay
falsifier, shippable independently:**
- A1 ratchet-arm fee constant → falsifier: armed-rate and per-fire net on
  replay before/after; expected: arm ≈2.2× more reachable.
- A2 honor authored brackets (parse prose levels / force structured emission) →
  falsifier: absent-rate <5% over next 30 entries; tail-width ratio →1.
- A3 wire expectancy gate into the replacement path + fills-recount → falsifier:
  `candidate_skipped` fires on a seeded negative bucket (mutation-tested).
- A4 close the short fail-open (score shorts or refuse) → falsifier: short
  admit-rate change measured, MFE replay split by direction.
- A5 fix `realized_pnl_usd` writes + the two stale 0.1% fee sites → falsifier:
  column non-zero on next 20 closed runs.

**P30-B — Payoff repair (attack the 28:1):**
- B1 **implement the resting price-level lock** (intrabar stop-fill path behind
  a flag) → acceptance: replay the 9 episodes, slip ≤24% of crossing range,
  LTC save preserved; forward metric = #77's replacement (median overrun ÷ band
  width per fire).
- B2 **MFE replay on the demoted cohort** (fork-decider, offline): if <50% of
  entries reach MFE >18bp and median MFE <9bp, no exit geometry can pay in
  crypto at taker → the lever becomes market mix (forex clears its 1.6bp hurdle
  50% of trips) + maker; else exit-geometry redesign proceeds on MFE evidence.
- B3 #592 continues accruing (n=3/30, 3/3 positive; n=9 readout pre-committed);
  decide by replay per #75's corrected falsifier (mean primary, median demoted).

**P30-C — Maker-first execution (the measured +4bp):**
- C1 shadow resting-order fill simulator against the real tape (adversary §3
  design): post synthetic post-only at proposal price; fill only on
  trade-through; log fill rate, time-to-fill, post-fill adverse selection vs
  unfilled cohort. Pre-registered: maker edge is real only if filled-subset
  net CI90 >0 AND fill rate keeps throughput viable (state the number first).
- C2 if C1 passes: post-only entry mode in the simulator (entries only — exits
  stay taker; that IS the honest mixed case, mean −15.83 → target is to beat it
  with A+B live).

**P30-D — Forecast/human-factor feeds (owner ask), all behind §4's acceptance test:**
- D1 funding percentile + predictedFundings line in the desk brief (crowding
  fade: block/fade longs above 90th trailing percentile) — replay on our own
  fills first, then 30-day ex-ante shadow.
- D2 DVOL level + 24h change as a regime line (magnitude, not direction).
- D3 Kalshi/Polymarket probability line at matched horizons — first-50-decision
  falsifier vs control, per the day-digest precedent.
- Wiring: `crypto_feed.py` / new small fetchers; brief-line wiring tests
  mandatory (brief lines are untested by default — standing lesson).

**P30-E — Aggression gates (unchanged from Plan 29 Phase 4, now with §2's data):**
frequency scaling only after replay mean ≥0 (cluster-collapsed CI90) on the
post-A/B/C stack; breadth = re-run §2's sweep per market at true per-market
fees (forex 1.6bp hurdle is the cheapest live test); size LAST, never on a
size-blind replay, impact re-measured at each step.

## 7. What we will NOT do (added to the dead list)

- Scale size or frequency on today's stack (mean gross −6.14bp, CI90 < 0).
- Buy paid forecast APIs (TokenMetrics/Glassnode/Santiment class) — no
  independent evidence of skill; free derivatives-implied sources dominate.
- Trust prediction-market calibration at tradable horizons without our own
  30-day ex-ante scoring (near-resolution Brier is not forecast skill).
- Quote retired numbers: "4.36% keep baseline", "21bp gross bar", "2.7× short",
  "9/9 adverse exits", "maker flips the crypto cohort positive", "monotone
  per-cell rail dial", "$57/day ruin rate" (correct: ~$44/day).

## 8. Owner decision points

1. Approve P30-A defect fixes (code-verified defects; each ships with its own
   falsifier and rollback).
2. Approve building B1 (resting lock) and C1 (fill simulator) — both offline/
   sim, zero live risk, and they gate everything aggressive.
3. D-feeds: confirm free-tier-only (recommended) — no paid data until a free
   feed passes the acceptance test.
4. Panel throughput: 1.9% keep is the entry choke. Options: (a) leave until
   B2's MFE verdict says entries are worth having, (b) pre-register a bounded
   measurement budget (adversary's steelman) — N minimum-size entries/day
   through a frozen filter purely to accrue falsifier n. Recommend (a) then (b)
   only if B2 shows positive reachable MFE.

*Method note: 10 agents (5 analysis + 5 QA), every number above re-derived at
least twice by independent routes; corrections applied where QA refuted the
first pass are marked. Artifacts: session scratchpad `fee_sweep.py`,
`fee_sweep_trips.json`, `realized_trips.json`, `maker_fill_check.py`, QA
scripts `qa_audit.py`/`qa_resim.py`/`qa_ref_zi.py`.*
