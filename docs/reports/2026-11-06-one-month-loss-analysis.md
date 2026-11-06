# One-month loss analysis — 2026-10-05 → 2026-11-06

Continues [2026-10-05-one-month-loss-analysis.md](2026-10-05-one-month-loss-analysis.md)
from the minute it stopped (10-05 15:49Z) to 11-06 20:30Z. Accounts: `info@askkpop.com`
(user 5, agent 6, crypto fleet 44), `forevery1969@gmail.com` (user 25, agent 60, us-stock
fleet 43), agent 63 (trend module, Plan 32). Two-subagent procedure (CLAUDE.md monitoring
rules): Agent A = AI-authored outcomes, Agent B = algorithm-authored outcomes, cross-checked
here; every key figure was also reproduced by a third independent script before it was
written down.

Scripts, pre-registration and data dumps: `research/loss_analysis_20261106/` (`PREREG.txt`
registered before analysis; `dump.py`/`dump2.py` read-only SELECTs; `trips1.py`; Agent A
`a_*.py` + `agentA.md`; Agent B `b_*.py` + `agentB.md`). Fills `d/signals.tsv`, events
`d/events.tsv.gz` (189,317 run_events), runs, llm_usage.

## 1. Verdict, in profit-or-loss terms

| | amount | note |
|---|---|---|
| Agent 6 crypto desk | **−$27.21** | 468 round trips; gross −$1.46; **fees $25.74 = 95% of the loss** |
| Agent 60 us-stock | **+$1.17** | 30 trips + 1 MSFT carry; gross +$0.95, fees $0.46; sign flips ex-COP → inconclusive as a book |
| Agent 63 trend module | **−$51.31** | two −1R stop-outs (BNB −25.54, XRP −25.42) on 10-08; n=2; **zero run_events** |
| Paid LLM | **$0** | 94,119 calls since 10-05, 100% local gpt-oss 120b/20b (vs −$743.39 real money last month) |

Ledger check: agent 6 cash 9918.92 (10-05) → 9891.72 = −27.20; reconstructed trips −27.21
(+0.05 on one straddling trip). Agent 60 +1.18 vs +1.17. Agent 63 10000 → 9933.77 = −66.23,
of which −14.92 was reported on 10-05.

**The desk lost money in a market it had read correctly.** The 39 coins it traded fell
**−24.0% on average** over the window (37 of 39 down) and the desk was **93% short** (433 of
468 trips). It captured none of that: median hold 27 minutes, median notional $45.6, and
its entries are timed *worse than a random minute on the same coin, same side*
(§2.1). Right sign, wrong horizon, paid a round-trip fee 468 times.

Compared with last month: trips 633 → 468, fees $52.81 → $25.74, net −$81.08 → −$27.21.
The loss halved because the book halved (median size $94 → $46, §2.5), not because the
trading improved: gross per trip −5.2bp → −2.0bp, both CIs contain zero.

## 2. Why it lost

### 2.1 The entries carry no edge — fourth replication, and now anti-timed

Pre-registered H1: side-signed forward return of the 468 entries beats a same-symbol,
same-side random entry time (Hyperliquid 15m candles, 2,000 shuffles).

| horizon | desk | random, whole window | desk − random | z | random, ±24h of entry | z |
|---|---|---|---|---|---|---|
| 1h | −5.2bp | +2.6 | −7.8 | −1.73 | +3.1 | −1.85 |
| 4h | −1.0 | +11.0 | −12.0 | −1.31 | +12.8 | −1.56 |
| 12h | −25.2 | +33.9 | −59.0 | **−3.76** | +36.1 | **−4.44** |
| 24h | −26.9 | +70.9 | −97.8 | **−4.57** | +62.1 | **−5.65** |
| 48h | −16.5 | +120.9 | −137.3 | **−4.69** | +70.3 | **−5.14** |

**H1 FALSIFIED at every horizon.** Robust to seed, to the null definition, and ex-TRUMP
(the largest contributor); the clustered CI excludes 0 at 12–48h. Independent re-test
(main session, own code, A's candles): 24h desk −26.8bp vs random +52.9bp. This is the
fourth replication (08-30, 09-08, 10-05, 11-06) and the first where the entries are
*actively* worse than random rather than indistinguishable: in a falling tape, a random
short made +0.7% in 24h; the desk's short made −0.27%. The desk shorts after the drop.

Nothing the desk knows at entry sorts winners from losers. **361 of 468 entries carry a
final confidence in [0.55, 0.60) and sum to −$22.72** (A: 365, −$22.84). 0.55 is the gate
threshold: Risk's dominant move is "lower confidence to 0.55 for mixed signals, keep the
sell" — the order passes at the minimum. No confidence bucket nets more than +$2.23.

Fixed-hold counterfactuals on the same entries flip sign by horizon (4h −15.73, 24h +9.36,
48h −23.51): no exit horizon rescues them. INCONCLUSIVE as a fix; the entries are the
problem.

### 2.2 The 10-05 fix landed and moved $0

Pre-registered H2: a29cd6b (panel hold binds on entries; chair cannot order off a rule
fallback) removed "entries over objection".

**H2 SUPPORTED.** 13 `veto_overridden` entries, all between 15:52Z and 17:15Z on 10-05,
before the ~17:20Z deploy; 0 after. 0 chair orders off a rule fallback (3,166 rule
fallbacks, all hold, 0 trades). The panel now holds 83% of proposals (3,764 / 4,523).

And it changed nothing about the money: the panel **confirms** the same no-edge orders it
used to be overridden on. Panel-confirmed sells: 314 trips, −$19.91. Panel reversed
buy→sell: 107, −$2.46. The "over objection" label is gone; the trade is the same trade.

### 2.3 Where the dollars went, by who closed the position

Agents A and B agree on every total; the one attribution difference (B counts 25
watcher stop closes −34.93; A splits them 22 watcher −27.37 + 2 adapt_retired −4.86 +
1 trailing_lock run-stop −2.70 = same −34.93) is resolved to A's finer labels below.

| exit author | n | net | gross | fees | WR | reason |
|---|---|---|---|---|---|---|
| breakeven ratchet (code) | 377 | **+17.69** | +37.41 | 19.72 | 75% | arm = 1.78× round-trip fee ≈ 16bp; banks median +14.5bp after 20 min; 62% of fires below 2× fee |
| legacy trailing lock (code) | 16 | **+14.86** | +16.52 | 1.66 | 88% | the only positions allowed to run +2.5%; the whole positive gross lives here and in the ratchet |
| SL/TP watcher stop-out (code fail-safe) | 22 | **−27.37** | −26.07 | 1.29 | 0% | mark went 2.5% against a desk-sized position; **the desk never answered**; 25/26 filled past the authored stop |
| desk cycle close `cyc` (AI) | 20 | **−13.05** | −11.87 | 1.18 | 20% | 11 = desk closing a short ahead of its own stop; 3 chair flips to long; 2 "bank" already negative |
| desk-armed level `arm` (AI level, code execution) | 13 | **−7.88** | −7.26 | 0.62 | 23% | 10 = desk's own armed stop hit |
| adapt_retired flatten | 2 | −4.86 | −4.61 | 0.25 | 0% | two consecutive losing partials |
| conviction_collapse | 11 | −2.93 | −2.48 | 0.45 | 0% | de-facto −70bp loss cut; conviction tracks P&L |
| orphans after `stop_eval_failed` | 3 | −2.82 | −2.57 | 0.25 | 33% | run died `positions_held`, position unmanaged 39–75h, sold outside any run |
| trailing_lock run-stop | 1 | −2.70 | −2.61 | 0.09 | 0% | |
| watcher take-profit | 1 | +2.51 | +2.59 | 0.08 | | LIT |

Shape: 393 code-banked wins **+$32.55**, 25 stop-side closes **−$34.93**. One 2.5% stop-out
erases ~30 ratchet wins (ratchet mean net $0.047). 25 trips with net < −$1 sum −$50.10;
the other 443 sum +$22.90. Median loss on the 25: −221bp against a −250bp authored stop;
21 of 25 went straight down. No existing rail should have fired earlier on the recorded
marks. The loss is the geometry the desk authored (size up to $375 at a 2.5% stop, banks
at 13bp = payoff 0.33) meeting a no-edge entry.

**The stop router does not convene the desk.** `stop_router.py` is designed to call an
immediate full-tier decision on a stop hit and let code close only after
`STOP_DESK_TIMEOUT_S` (180s) of silence. On the tape: **0 of 26 stop hits received an AI
ruling** inside the window; 2 received a rule-fallback hold; the watcher closed all 26,
25 of them past the authored stop (median ~15bp past; **$1.95** slippage certain, ex-UNI
$0.75). Once (UNI 10-08) the late ruling arrived 47s after the fail-safe cover and
re-shorted 20× larger with a 0.3% stop; stopped again 15 min later, −$2.67 (n=1). There is
no event for the dispatch itself, so the tape shows the ruling did not land, not why.

### 2.4 No-verdict: fail-closed works, and the tape is a step function of local-AI uptime

Agent 6: 1,202 of 10,894 decisions (11.0%) no verdict, agent 60: 486 / 1,283 (37.9%). All
→ scaffold hold, 0 trades; 3,166 rule fallbacks → hold, 0 trades; 18 `entry_held`. But
273 `verdict_salvaged` (truncated JSON) did author trades (17 within 240s). Days the
local model was up: 15 days, 384 trips, −$19.79; down days: 18 days, 84 trips, −$7.42
(memory `month-loss-analysis-1005-veto-override`: local AI = host sleeping, confirmed).

### 2.5 Sizing (PREREG H5) — the clamp is not the cause; the desk sizes itself small

Median notional fell $94 → $45.6. **H5 FALSIFIED on the cause, held on the scale.** The
`null_size_cap` (0.25 × $375 = $93.75) is unchanged. It fired on **187 trips** where the
desk returned no size (`defer` 105 / `absent` 74 / parsed-null 12) and sized them at
$93.7 median. The other **281 trips the desk sized itself**: `size_frac` 0.05 on 162,
0.10 on 58, median **$20.0**. So "no size from the desk" is now sized at **5× the desk's
own size**, and those 187 trips carry **$15.47 of the $25.74 fee bill** on 40% of the
trips (net −12.21; −8.96 ex-worst). Clamped − unclamped gross: +5.3bp, CI [−9.9, +20.7]
— no difference in quality. Unclamped book: net −47.91 (same sign, bigger).

### 2.6 Fees (PREREG H3) — the fee is the loss, and no real venue is cheaper than the simulator

**H3 SUPPORTED.** Fees / |net| = 0.95; gross −2.0bp, symbol-clustered CI [−8.3, +2.9];
gross $ CI [−25.1, +23.5]. Loss ≈ 468 trips × $61 × 9bp = $25.7 = the fee bill. Fee rate
4.50bp on 998 of 998 legs; 2.13 legs/trip (4 adds $0.17, 58 partial exits $0.94).

Same fills, different fee schedule (agent 6):

| fee model | net | ex-worst trip |
|---|---|---|
| actual, 4.5bp/leg | −27.21 | −23.95 |
| zero fee | **−1.46** | +1.71 |
| Hyperliquid maker 1.5bp | −10.04 | −6.85 |
| Binance spot maker 0 entries + 10bp taker exits | −30.07 | −26.81 |
| Binance spot 7.5bp (BNB discount) | −44.37 | −41.06 |
| Binance spot taker 10bp | **−58.67** | −55.32 |

The simulated 4.5bp is a perp-taker rate and is already **below every real spot taker
schedule**. A live spot book with today's market-order adapters would have lost 2.2× as
much on the same fills. Zero fee is −$1.46 (sign INCONCLUSIVE ex-worst +1.71): **fee
reduction changes the scale of a zero-edge book, never its sign.**

### 2.7 Direction (PREREG H4)

H4 predicted the short tilt was not a market read. **NOT FALSIFIED, premise half wrong.**
Shorts' gross −3.17 (ex-SUI 0.00); the matched market move over the shorts' own hold
windows is −2.2bp, CI [−8.5, +4.2] — over 27-minute holds the tape is noise. Yet the
tape fell 24%. The panel's reasons for shorting were daily technicals ("below 5/20-MA,
downtrend, crowded longs"), which were right; the holding period could not collect on
them. Light tier proposed 70% sells; the panel turned 107 of 139 buys into sells and
3 of 323 sells into buys.

### 2.8 Agent 63 trend module — the largest algorithm-authored loss, with no telemetry

Two longs opened before 10-05 on Donchian breakouts (BNB from 782.10, XRP from 1.4916),
sized at R = $25 (`TREND_RISK_USD`), initial 1.5×ATR14 stop written to
`positions.stop_loss`. Both failed: BNB best +2.9% then −4.8%; XRP best +10.5% then −8.5%.
The SL/TP watcher closed both on 10-08 (`run_id NULL`, `client_order_id NULL`; module
logged `closed_outside`): −$25.54 and −$25.42, i.e. −1.01R each, by design. Module record
since enrolment: 3 trips, 3 losers, −$66. n=3 says nothing about the rule's edge (replay
+107R over 66 trades, 2025–26 near zero) — but **both closes are invisible to every
monitor built on `run_events`**. A's bar-boundary check on the XRP trail (evaluated at the
first tick after 16:00Z; UTC-midnight close would have exited for −$14.0 instead of −$25.3)
is INCONCLUSIVE on bar convention ($11.3, n=1).

### 2.9 What the fleets did with their slots

Fleet 44 (agent 6): 2,035 runs alive in the window, **63 per day, median life 68 min**,
1,578 (78%) never traded (1,268 switched by the 1-hour no-prospect rule, 295 idle-retired).
Slot occupancy 91%, but **a position was held 15.5% of slot-hours**; the other 85% was a
flat desk deciding hold (10,018 "decision is 'hold'" gate skips). Churn fee $0 (all three
retire rails fire flat-only; verified 0 trips on 1,592 retired runs). Its cost is LLM
load: 10,887 decisions, 29% "no llm response".

Fleet 43 (agent 60): **3 of 8 slots for 709 of 773 hours** (`replenishing:3/8`); cause is in
fleet-planner events not present in `run_events` — not determined here. 30 trips, +$0.48
in-window; 13 of them are 0.3-minute `conviction_collapse` fee burns (−$0.42): the rail
counts conviction reads from flat cycles before the entry — the 10-05 backlog defect, still
unshipped (15 zero-hold trips across both agents, −$0.24).

## 3. Cross-check of the two agents

- **Agreement**: every book total to the cent; fee share 95%; gross CI contains 0; H1
  falsified; H2 landed and moved $0; H5 clamp-not-cause; 0/26 AI rulings on stop hits;
  the 25 big losers' composition (13 watcher / 6 cyc / 4 arm / 2 orphan).
- **Resolved**: B's 25 "watcher stop closes" = A's 22 watcher + 2 adapt_retired + 1
  trailing-lock run-stop (same −34.93). A's labels are used; the money is the same.
- **Rejected under the owner law**: A's "gate confidence ≥ 0.60 → +$22.84" — threshold
  chosen after seeing the data; A itself flags it post-hoc and as fee avoidance, not edge.
  Kept as a distribution fact only. B's "ratchet 60s sampling $15.33" — a description of
  where fills landed, not shown recoverable (same rejection as 10-05); candidate only.
- **Not an excuse, a measurement**: "the local model does not answer in time" (0/26 stop
  rulings, 29% no-response) is the cause of code closing every stop; it is not a reason the
  stops lost. The stops lost because the entries have no edge and the desk authored a 2.5%
  stop under a 13bp bank.

## 4. Hypotheses, ledger

| id | registered prediction | result |
|---|---|---|
| H1 entry edge | desk beats random same-symbol same-side entry | **FALSIFIED at every horizon; anti-timed at 12–48h (z −3.8 to −5.7)**; 4th replication |
| H2 fix landed | a29cd6b cut overridden entries to ~0 | **SUPPORTED** (13, all pre-deploy; 0 after); **moved $0** |
| H3 fee share | fees ≥ 50% of \|net\|, gross CI ∋ 0 | **SUPPORTED** (95%; CI [−8.3, +2.9]bp) |
| H4 short bias | tilt was not a market read | **NOT FALSIFIED; premise half wrong** — the read was right (−24%), the 27-min hold could not collect |
| H5 size | clamp caused $94→$45 and scales the loss | **FALSIFIED on cause** (desk self-sizes $20); held on scale (unclamped −47.91) |
| 09-04 tier falsifier | expectancy ≥ 0 at n ≥ 50 | **FAILED again**: n=468, −$0.058/trip |
| 08-27 ratchet falsifier | median give-back < 100%, median realised > 0 | PASSES (51%, $0.022) |
| "stop exits are AI-authored, code is fail-safe" | — | **FALSIFIED on tape**: 0/26 |
| "rotation costs money" | — | re-REFUTED: $0, 0 trips on 1,592 retired runs |
| "zero-hold conviction burns fixed" | — | NOT fixed: 15 trips, −$0.24 |

## 5. Solutions — ranked by the dollar each would have moved on THIS tape

Certain = the sign survives removing the largest contributor and needs no model of what
the mark would have done.

| # | change | $ on this tape | certainty | where |
|---|---|---|---|---|
| 1 | **Do not take an entry the desk declined to size.** `order_params.outcome ∈ {defer, absent, parsed-null}` currently → `null_size_cap` 0.25×max_bet ($94) = 5× the desk's own median. Refuse the entry instead (or size at the desk's own median: +$9.77). | **+$12.21** (+14.72 ex-best); fee saving $15.47 certain | certain | `order_params.py` / `run_engine.py` null-size path; 187 trips |
| 2 | **Stop hits: stop waiting for a ruling that never comes.** 0/26 AI rulings in 180s. Close at the stop immediately, and emit a `stop_dispatch` event so the next tape can show whether the desk was ever asked. Fence re-entry on the same symbol for N minutes after a fail-safe close (UNI −2.67, n=1). | **+$1.95** slippage (ex-UNI +0.75) + −2.67 fenced (n=1) | certain / n=1 | `stop_router.py`, `risk_engine` watcher |
| 3 | **Zero-hold `conviction_collapse`**: count only conviction reads taken while holding. | **+$0.24** | certain | `run_engine.py` conviction rail; on the 10-05 backlog |
| 4 | **Orphans after `stop_eval_failed`**: a run that dies `positions_held` must flatten or hand the position to a live run, not leave it unmanaged 39–75h. | −$2.82 untraceable → traceable | n=3 | run lifecycle |
| 5 | **Trend module closes must write `run_id`/`client_order_id` and a `run_events` row.** −$51.31 this window with zero telemetry. Also decide the bar convention for the trail check (UTC-midnight vs first tick after 16:00Z; XRP $11.3). | 0 (observability); $11.3 INCONCLUSIVE | n=2 | `trend_module.py`, watcher |
| 6 | **Fee / venue**: on the simulated book, nothing — 4.5bp is already below every real taker schedule. For any live spot routing: **maker-only** (post-only limit) is the only schedule that does not double the loss (Hyperliquid maker −10.04 vs Binance taker −58.67). Build post-only entries + taker exits before any live order, or the live book loses 2.2× the paper book. | +$17.17 at 1.5bp maker; −$31.46 at 10bp taker | counterfactual | `execution/*` adapters (all send MARKET today) |
| 7 | **The entries.** The one number that is exact: **not trading agent 6 = +$27.21** (+23.95 ex-SUI). Four replications say the scalping desk's entries have no edge; this one says they are anti-timed. Fee, size, stop and exit changes above rescale this loss; none changes its sign. The platform's only strategy with a positive pre-registered replay (long-only crypto trend, +107R / 66 trades, p = 0.004, multi-week holds) is live as agent 63 with n=3 and no telemetry. Product decision, not a fix: either fleet 44 stops scalping crypto, or its gross must be shown > 0 on ≥ 300 trips with a CI excluding 0 before another fee/exit/size tune is justified. | **+$27.21** | exact | owner |

What is *not* a solution, by this tape: lowering the simulated fee (hides the cost; −$1.46
at zero), tuning the ratchet arm (08-27 falsifier passes; 393 code-banked trips are the
only positive bucket), changing the exit horizon (fixed-hold counterfactuals flip sign),
switching provider (paid spend is $0 and the model's silence fails closed).

**Pre-registered falsifiers for the ships above** (read on the next tape):
#1 — `size_clamp` events with stage `null_size_cap` must be 0 and agent-6 fees must fall
by ≥ 40% per trip-count; if trips fall but fees/trip do not, the fix failed.
#2 — every watcher stop close must have a `stop_dispatch` event within 180s before it, and
the median fill-vs-authored-stop gap must drop from ~15bp to ≤ 5bp.
#3 — zero `conviction_collapse` closes with hold < 2 min.

## 6. What could not be determined

- Why fleet 43 ran 3/8 for 92% of the window (planner rejections are fleet-level events).
- Whether the stop-router dispatch fired at all (no event for the dispatch, only the
  absent decision).
- Prod env values: `BREAKEVEN_ARM_FEES` (1.78 inferred from 377/377 payload ratios),
  `RATCHET_LOCK_FRAC` (0.5 inferred), `STOP_DESK_TIMEOUT_S`, conviction rail params.
- Who sold the 3 orphaned positions; the trend module's bar boundary.
- Peak/drawdown for 21 of the 25 big losers (equity events keep 7 days; run-level peaks
  may belong to a sibling trip).
- The value of the 3,764 panel holds (the trades not taken) — would need the proposal
  marks, which are not journaled.
- The $25 gap between `ledger_invariant_cash_state` 01:18Z and `agents.cash` 21:08Z
  (consistent with intraday open margin; not reconciled leg by leg).
