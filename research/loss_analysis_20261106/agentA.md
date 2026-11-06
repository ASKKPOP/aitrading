# Agent A — AI-authored outcomes, 2026-10-05 15:49Z → 2026-11-06 20:30Z

Scope: every outcome the sooppiy AI authored — entries (who decided, which path), the
short tilt, AI-authored exits (`cyc`, `arm`, and the 29 NULL-coid exits), PREREG H1/H2/H4,
no-verdict behaviour, the trend module (agent 63). Scripts: `a_load.py` (events →
`a_events.pkl`), `a_entries.py`, `a_exits.py`, `a_exits2.py`, `a_paths.py`, `a_h1.py`,
`a_h4.py`, `a_h35.py`, `a_noverdict.py`, `a_trend.py`, `a_fetch_candles.py`
(Hyperliquid 15m → `a_candles15.pkl`, 39 symbols, 3,829 candles each from 09-28).
Trips = `trips1.pkl` (shared). Every table shows the figure with and without its largest
contributor.

Ledger checks (two independent records each):
- Agent 6: trips net −$27.21; `agents.cash` 9,918.92 (10-05) → 9,891.72 = −$27.20.
- Agent 60: window trips +$0.48 + MSFT (opened pre-window, closed 10-06) +$0.69 = +$1.18;
  cash 9,994.77 → 9,995.95 = +$1.17.
- Agent 63: two fills −$50.97; cash implied at 10-05 = 9,984.74 vs 10,000 − 15.02 − 0.37
  entry fees = 9,984.61 (within $0.13 — the prior report's −15.02 is rounded).

## 1. Verdict, in profit-or-loss terms

| book | window P&L | what it is |
|---|---|---|
| Agent 6 (crypto desk, fleet 44) | **−$27.21** | 468 round trips; gross −$1.46 (−2.0bp/trip, symbol-clustered CI [−8.2, +2.9]bp), fees $25.74 = **95% of the loss** |
| Agent 60 (us-stock, fleet 43) | **+$1.17** | 30 trips + MSFT carry; gross +$0.95, fees $0.46; sign flips without COP (+1.17) → inconclusive as a book |
| Agent 63 (trend module) | **−$50.97** | two −1R stop-outs (BNB, XRP), both designed-size losses on failed breakouts |
| Paid LLM | $0 | 100% local gpt-oss (120b/20b) |

Agent 6 lost exactly the fee bill again, for the fourth month. The market the desk traded
fell **−24.4%** on average (37 of 39 coins down; `a_h4.py`) and the desk was **93% short**
(433 of 468) — direction right for the month — and it still made nothing gross, because
it held for a median 27 minutes and its entries are timed *worse than a random minute on
the same day* (H1 below, z −4.4 to −5.6 at 12–48h). The 10-05 fix (`a29cd6b`) did what it
said — zero entries over a panel hold after 17:20Z, zero chair orders off a rule fallback —
and it did not change the money, because every one of the 472 entry legs is now a fully
AI-authored order (`decided_by: ai`, gpt-oss:120b, full-panel final) and those orders
carry no edge.

## 2. Per-category outcomes, with reasons

### 2.1 Entries — who decided (agent 6, 472 legs = 468 trips + 4 adds; `a_entries.py`)

All 472: `decided_by=ai`, `llm.model=gpt-oss:120b`, `fallback_reason=None`, coid
`run:<id>:cyc:<n>`. 461 came through the light route (one-call proposal → full
`order_discussion` panel whose verdict replaces the proposal wholesale), 11 through the
full route. The `llm.source` field reads `rule` on all 13,229 decisions and is not a
useful authorship stamp (the `decided_by` stamp from `run_engine.py:7346` is).

| entry path (panel's final vs light proposal) | n | net | gross | fees | WR | ex-largest |
|---|---|---|---|---|---|---|
| panel **confirmed** light `sell` → short | 314 | −19.91 | −3.96 | 15.94 | 68% | −16.66 (SUI −3.25) |
| panel **reversed** light `buy` → `sell` → short | 107 | −2.46 | +3.24 | 5.70 | 64% | +0.70 (UNI −3.16) |
| panel confirmed light `buy` → long | 20 | −3.54 | −2.23 | 1.31 | 30% | −0.69 (NEAR −2.85) |
| panel reversed `sell` → `buy` → long | 3 | +0.53 | +0.70 | 0.17 | 67% | −0.02 |
| panel hold **overridden** (`veto_overridden`, all 10-05 15:52–17:15Z, pre-deploy) | 13 | −0.74 | +0.33 | 1.07 | 69% | +1.06 (LIT −1.80) |
| full route (no discussion event) | 10 | −1.00 | +0.46 | 1.46 | 70% | +1.66 |
| reversed `sell` → `hold` (0-min trip) | 1 | −0.08 | 0 | 0.08 | – | – |

By chair action on the final decision: `adopt` 56 trips **+$4.66** (ex-LINK +1.82);
`amended: confidence,report` 350 trips **−$25.16** (ex-UNI −22.00); `amended: action`
47 trips −$6.03 (ex-SUI −2.77). The 350 are the dominant shape: Risk "lowers confidence
to 0.55 because of bullish sentiment/news, but keeps the sell" — 0.55 is the gate
threshold (`gate_skip: confidence 0.42 below threshold 0.55`), so the order passes at the
minimum. **365 of 468 entries carry final confidence in [0.55, 0.60) and sum to −$22.84**
(84% of the loss; ex-UNI −19.68). No confidence bucket nets > +$2.23 (n=26).

Reason the entries lost: fee. Gross −1.46 is indistinguishable from zero; 468 × 9.0bp
of a median $45.6 notional is the −$25.74. Nothing the desk writes at entry (confidence,
path, chair verb, route, clamp) sorts winners from losers — every bucket is ≤ 0 after fees
except `adopt` (+4.66, n=56, sign survives ex-largest; too small to carry a book).

Agent 60 (30 legs): 30/30 `decided_by=ai`, 30/30 **chair amended the action**: the
trader said hold at low confidence, Risk argued "bullish fundamentals/technicals outweigh
the hold", the chair wrote `buy`. Net +$0.48 (ex-MCD −2.00 → +2.49). 11 of 30 trips were
closed within ≤1 minute at fee cost (−$0.18 total — the `conviction_collapse` zero-hold
defect from last month, still live, trivial in dollars).

### 2.2 The direction tilt (433 shorts / 35 longs; `a_paths.py`, `a_h4.py`)

Where it came from: the light tier itself proposed `sell` 323× vs `buy` 139× (70% sell);
the panel then turned 107 of the 139 buys into sells and only 3 of the 323 sells into
buys → 437 shorts : 35 buys. The panel's stated reasons (final `report`): "bearish
technicals / downtrend / below 5- and 20-day MAs / crowded longs (long-short ratio > 2)"
— present in 13% / 7% / 12% of short reports vs 3% / 0% / 6% of long reports — with Risk
lowering confidence for "bullish sentiment" in 61%. F&G is quoted in only 5 reports
(26–37, fear). The tilt is a technical read of a falling tape, not a psychology overlay.

Was it a market read (PREREG H4)? Over each short's own hold window the symbol-matched
buy-and-hold move averaged **−2.2bp** (median −5.1, cluster CI [−8.5, +4.2]), shorts'
gross **−$3.17** (ex-SUI: $0.00). A frictionless short of the same notional over the same
windows = +$8.48. So: right sign for the month, zero capture — the desk's 27-minute
windows contain none of the −24%. Shorts held < 60m: 288 trips gross +$21.18 (ratchet
banks of +13bp); shorts held ≥ 60m: 145 trips gross **−$24.34** (the stop-outs).

### 2.3 AI-authored exits (agent 6, `a_exits.py`, `a_exits2.py`)

| exit author | n | net | gross | fees | WR | ex-largest |
|---|---|---|---|---|---|---|
| `flatten` — breakeven ratchet (algorithm; Agent B's scope, shown for the sum) | 406 | +28.97 | +50.95 | 21.98 | 73% | +26.13 |
| `cyc` — desk cycle close | 20 | **−13.05** | −11.87 | 1.18 | 20% | −10.11 (TRUMP −2.94) |
| `arm` — desk-armed level, executed by the rail | 13 | **−7.88** | −7.26 | 0.62 | 23% | −5.11 (LINK −2.77) |
| `other`, NULL coid — SL/TP watcher stop-out (fail-safe) | 22 | **−27.37** | −26.07 | 1.29 | 0% | −24.12 (SUI −3.25) |
| `other` — SL/TP watcher take-profit | 1 | +2.51 | +2.59 | 0.08 | – | LIT |
| `other` — `adapt_retired` consecutive-losses flatten | 2 | −4.86 | −4.61 | 0.25 | 0% | −1.70 |
| `other` — `stop_event:trailing_lock` run stop | 1 | −2.70 | −2.61 | 0.09 | 0% | – |
| `other` — closed outside any run after `stop_eval_failed` orphaned it | 3 | −2.82 | −2.57 | 0.25 | 33% | −0.76 |

**`cyc` (20 trips, −13.05).** All 20 `decided_by=ai`. 16 losers, reasons from the
decision/intent text: 11 are the desk closing a short that had moved against it *ahead of
its own stop* ("thesis invalidated by price crossing 1.9106 — close to lock in loss"
TRUMP −2.94; "price above stop triggers invalidation; full close" LIT −2.14; "stop is only
~0.2% away" SUI −1.41; "stop about to trigger" WLD −1.31; HYPE −1.02, TAO −0.52, LINK
−0.48/−0.45, ENA −0.39, SOL −0.36, ETH −0.20/−0.13); 3 are chair action-flips that
covered a short to go long (AAVE −0.24, BTC −0.24, SOL −0.32 — "crowded long side,
potential squeeze"); 2 are "lock the small gain/avoid auto-close" that were already
negative. 4 winners are small banks (+0.07…+0.41). Reason: these are the desk's
discretionary stop-outs on shorts entered at local lows — the same entries as everything
else, closed by the AI instead of the rail; the AI close is not worse or better than the
rail (median −$0.44 vs the rail's −$1.4 because it fires earlier).

**`arm` (13 trips, −7.88).** 10 losers are the desk's own armed stop (`if price_above
→ close`, size 1.0) hitting on a short: LINK −2.77 (level 11.00, 56 min), SUI −2.48,
LINK −1.51, BCH −1.24, PONS −0.67, ETH −0.49, TRUMP −0.47, SOL −0.31, BTC −0.15, FIL
(long, `price_below`) −0.43. 3 winners are armed targets (FIL +2.18, BCH +0.45, SOL
+0.02). Reason: AI-authored level, AI-authored direction, price went the other way;
the rail executed faithfully (slippage 0.02–0.7%).

**`other` (29 trips, −35.24) — the author is identified for all 29.**
- **22 SL/TP-watcher stop-outs, −27.38.** `risk_engine.sl_tp_watch` closes with
  `run_id=pos.run_id` and no `client_order_id`; every one of the 22 printed at/through
  the ledger stop. The level is the desk's: 14 carried the desk's own `stop_pct`
  (0.3–2.5%), 8 had `params_state: absent` and were set by `stop_cap` at 2.5% (the desk
  had written wider, 4.7–5%). Median stop distance 2.5% against a ratchet arm of ~13bp —
  the payoff shape (0.33) is written by the AI's own bracket. Why the *watcher* and not
  the desk: for fleet runs a stop hit is routed to an emergency desk ruling with a 180s
  fail-safe (`stop_router.py`, `STOP_DESK_TIMEOUT_S`); in these 22 the fail-safe fired.
  In the cases where the desk's ruling is visible it landed *after* the watcher had already
  closed (UNI 10-08: watcher cover 00:51:43Z, desk `sell` 00:52:30Z — which re-opened the
  short 20× larger, 47.1 vs 2.42 UNI, with a 0.3% stop, and was stopped again 15 min later
  for −2.67; ETH 10-19, LINK 10-18, SUI 11-03: desk `hold` ~45–60s after the close).
  The desk had no vote on 22 of its own stop hits because the local model does not answer
  inside 180s.
- **1 watcher take-profit, +2.51** (LIT 10-18, target hit at 2.9251).
- **2 `adapt_retired`** (UNI 11-03 −3.16 after two losing partials; HYPE 10-06 −1.70,
  "consecutive_losses 3") — rule retire, flattened at the market.
- **1 `stop_event:trailing_lock`** run stop (LTC 10-15 −2.70) — the run's stop condition.
- **3 orphans, −2.82**: XRP (+0.48, 75h), ETH (−2.06, 47h), SOL (−1.24, 39h). Their runs
  went `running → paused (stop_eval_failed) → stopping → stopped (positions_held)`,
  `stop_flatten=0`, leaving the position unmanaged for 1.5–3 days until something without
  a run or coid closed it (the watcher's `run_id` comes from the position row; the
  run-start close in `trading_runs.py:632` writes neither). Same defect class as last
  month's CVX.

**The 25 trips < −$1 (−50.10 of the −27.21):** 10 watcher stop-outs −20.62, 6 `cyc`
−10.62, 4 `arm` −8.01, 2 adapt −4.86, 2 orphans −3.30, 1 trailing_lock −2.70. Every one
is a short (or one of 3 longs) entered by the AI and closed 1.0–2.5% against it; the
author of the close changes the label, not the dollar.

### 2.4 No-verdict cycles (`a_noverdict.py`)

Agent 6, in window: 10,894 decisions; `no_verdict` **1,202 (11.0%)**, all `no_response`
(1,136) / `empty` (59) / `truncated` (7); `verdict_salvaged` 273 (2.5%); rule fallback
("no llm response" on the full route) 3,166 (29%). Agent 60: 486 no-verdict of 1,283
(37.9%). (The brief's 2,281 / 275 are since 09-25 across agents.)

What the desk did on them: **all 1,202 no-verdicts became `scaffold: hold`**, 0 trades in
that cycle (2 trades within 240s belong to the following cycle). All 3,166 rule fallbacks
were `hold` (3,165) or one `sell` the chair amended — **0 trades**. 18 `panel unavailable`
entries were held (`entry_held`). Fail-closed is working. The 273 *salvaged* (truncated
JSON) verdicts did trade: 17 trades followed within 240s and 7 entries carry a salvage
within 15 min — the truncation-repair path authors real orders.

The tape is a step function of local-AI availability: 15 "AI-up" days (≥50% of decisions
`ai`) vs 18 "AI-down" days. Up-days: 384 trips, −$19.79 (gross +1.48, fees 21.26);
down-days: 84 trips, −$7.42. On 10-20, 10-21, 10-24, 10-25, 10-31, 11-01 the desk made
0–2 trades. More model = more trades = more fee loss; the host's availability, not any
decision quality, sets the month's loss.

### 2.5 Trend module, agent 63 (`a_trend.py`)

Two fills on 10-08: BNB sell 0.6667 @ 744.12 (pnl −25.54), XRP sell 197.81 @ 1.3637
(pnl −25.42), `run_id` NULL, coid NULL — the SL/TP watcher on the ledger `stop_loss`;
the module logged `closed_outside` for both at 15:30:20Z. Implied entries 782.10 (BNB)
and 1.4916 (XRP); initial stops 744.60 / 1.3652; R = $25.00 each (`TREND_RISK_USD`
÷ 1.5×ATR); realised **−1.01R and −1.01R**. Reason: both Donchian breakouts failed —
BNB best close 805.2 (+2.9%) then −4.8%; XRP best close 1.6487 (+10.5%) then −8.5%; the
3×ATR chandelier trail (737.8 / 1.4312) never rose above entry, so no profit was locked
and the 1.5×ATR initial stop was the binding exit. This is the design's loss shape.

Cadence finding: trail updates ran once per symbol per day in October (vs hourly in
September), each at the first hourly tick after 16:00Z (18:52Z on 10-05 right after the
redeploy, 16:21Z on 10-06, 16:24Z on 10-07) — i.e. minutes into a daily bar whose boundary
is 16:00Z (UTC+8 feed day, inferred): the module evaluates the *forming* bar (the prior
report's open defect) and then no-ops until the next bar. On this tape
it did not change the outcome: XRP at the 10-07 16:24Z check was 1.4338 (> trail 1.4312
by 0.18%); the completed 16:00Z bar closed 1.4352 (also above); the price then fell from
the trail to the stop inside one bar (10-08 11:00–15:23Z). Under UTC-midnight bars
(10-07 close 1.4208 < trail) the module would have exited at ≈1.42 for −$14.0 instead of
−$25.3 — **$11.3 that depends on the bar convention: INCONCLUSIVE.**

Module record since 09-12: 3 closed trips, 3 losers, −$66.0, 0 open. The pre-registered
falsifier (30 trips or 60 trading days; true-net EV ≤ 0 → module dies) reaches its
60-trading-day leg around 12-05 at 0/3.

## 3. Hypotheses (PREREG)

**H1 ENTRY-EDGE — FALSIFIED at every horizon, and worse than "no edge": the entries are
anti-timed.** Side-signed forward return of the 468 entries vs same-symbol same-side
random entry time, 2,000 shuffles, Hyperliquid 15m (feed check: median |candle
close/fill − 1| 12bp, p90 46bp).

| T | n | desk | random (window) | desk − random | z | random (±24h of entry) | z |
|---|---|---|---|---|---|---|---|
| 1h | 468 | −5.2bp | +2.6 | −7.8 | −1.73 | +3.1 | −1.85 |
| 4h | 468 | −1.0 | +11.0 | −12.0 | −1.31 | +12.8 | −1.56 |
| 12h | 468 | −25.2 | +33.9 | −59.0 | **−3.76** | +36.1 | **−4.44** |
| 24h | 468 | −26.9 | +70.9 | −97.8 | **−4.57** | +62.1 | **−5.65** |
| 48h | 435 | −16.5 | +120.9 | −137.3 | **−4.69** | +70.3 | **−5.14** |

Same with seed 13, with candle-close instead of fill as p0, and with the whole candle
range as null. Ex-TRUMP (largest contributor at 24/48h) the desk's own clustered CI
excludes zero at 12h/24h/48h ([−65, −7], [−91, −9], [−126, −14]bp). Shorts only: 24h
desk −6.3bp vs random short +81.1bp. Random shorts made money in this month; the desk's
shorts, entered after the drop, caught the bounce. Longs (n=35): −281bp at 24h vs
−80 random. Fixed-hold counterfactuals on the shorts (non-overlapping, 9bp RT): 4h
−$15.73, 24h **+$9.36**, 48h −$23.51 vs actual −20.64 / −13.87 / −8.40 — the sign flips
with the horizon → **no exit horizon rescues these entries (INCONCLUSIVE as a fix).**

**H2 FIX-LANDED — SUPPORTED.** `veto_overridden=true` on 13 of 472 entries (2.8% < 5%),
all between 15:52Z and 17:15:55Z on 10-05; commit `a29cd6b` is 16:18Z, first post-deploy
entry 17:23:46Z carries no override field, and none of the following 459 does. Zero
entries from a rule fallback (0 of 3,166 rule decisions traded; 0 of 1,202 scaffolds).
After the fix the panel said `hold` on 3,764 of 4,523 proposals (83%; buy→hold 2,290,
sell→hold 1,474) — the binding hold is doing a lot of refusing; what those 3,764 would have
earned is not computable from the tape (no size, no fill).

**H3 FEE-SHARE — SUPPORTED (Agent B's hypothesis; data here for the cross-check).**
Fees $25.74 = 95% of |net|; gross −2.0bp/trip, clustered CI [−8.2, +2.9] contains 0
(ex-UNI [−8.2, +3.2]).

**H4 SHORT-BIAS — NOT FALSIFIED, with a correction to its premise.** Shorts' gross is not
positive (−$3.17; ex-SUI $0.00) and the matched market move over the hold windows is
~0 (−2.2bp, CI [−8.5, +4.2]). But the tape *did* fall −24% (37/39 coins); the tilt was the
right sign at the month horizon and captured none of it at the 27-minute horizon. The
prediction "mean return ~0 over the hold windows" holds; the inference "the tilt was not
a market read" is only half right — it was a read of the daily technicals, executed at a
horizon where it is worth nothing.

**H5 SIZE — the clamp is NOT the cause of the $94→$45 median (Agent B's hypothesis; data
here).** Clamped trips (n=190) have median notional **$93.7**; the unclamped (n=278) have
**$19.3** — the desk's own `size_frac` 0.05–0.12 on parsed params is what shrank the
book. Gross bp: clamped −0.3 [−9.7, +9.5], unclamped −3.1 [−15.7, +5.5] — no difference
beyond noise; scale, not sign, as predicted.

## 4. What must change — each with the dollar it would have moved on this tape

1. **The desk must not take entries that fail the permutation test** (4th consecutive
   month; this month z ≤ −4.4 at 12–48h, CI excludes 0 ex-largest). Dollar: every entry
   not taken is +9bp certain; **not trading = +$27.21 exact on this tape** (+$23.95
   ex-SUI). The 10-05 fix removed the "over objection" label (verified, 0 overrides) and
   left the loss intact because the panel now *confirms* the same no-edge orders (314 sells
   confirmed, 107 buys turned into sells). A post-hoc cut that illustrates the same thing:
   gate confidence at ≥ 0.60 instead of 0.55 → 365 trips not taken, **+$22.84** (+$19.68
   ex-UNI). That number is post-hoc (threshold chosen after seeing the data) and is fee
   avoidance, not edge; register it before relying on it.
2. **The AI's bracket geometry is the loss shape and it writes it itself.** 22 watcher
   stop-outs at a median 2.5% (14 desk-authored stop_pct, 8 capped from wider) against a
   13bp ratchet bank = payoff 0.33; the 25 trips < −$1 are −$50.10. Dollar if stops had been
   0.5% (Plan 31's figure): not computable without a per-trip path replay (the 406 ratchet
   winners would also have been stopped earlier) — **INCONCLUSIVE**, do not ship on it.
   What *is* shown: the 180s fail-safe fires before the local model answers on its own stop
   hits (22/22 here), and at least once (UNI 10-08) the late ruling re-entered 20× the
   size and lost −$2.67 in 15 min. The stop-hit ruling must either be answered inside the
   fail-safe window or the re-entry after a fail-safe close must be fenced — dollar on this
   tape −$2.67 (n=1).
3. **Positions orphaned by `stop_eval_failed` (3 trips, −$2.82, unmanaged 39–75h) and the
   trend module's forming-bar check (XRP, $11.3 INCONCLUSIVE on bar convention).** Both
   are defects with small, named n; fix the orphan with a flatten-or-reassign on
   `positions_held`, and settle the trend module's bar convention (evaluate the *completed*
   bar at its close, whichever day boundary the feed uses) before its falsifier is read.

Not a change but the binding constraint: 18 of 33 days the local model was mostly silent;
on those days the desk lost −$7.42 on 84 trips, on the other 15 days −$19.79 on 384. Any
"fix" that restores AI availability without an entry edge increases the loss.

## 5. What could not be determined

- The dollar value of the 3,764 panel holds after the fix (no size, no fill to replay).
- The light tier's proposal text — only `proposed.action` is journaled, so *why* 70% of
  proposals were sells cannot be read; the panel's final `report` is the only reasoning.
- Whether each of the 22 fail-safe closes had a desk ruling in flight (no `stop_router`
  telemetry event; inferred from decision timestamps 45–60s after the cover in 4 cases).
- Who closed the 3 orphaned positions (no `run_id`, no `client_order_id`, `content` not
  dumped) — the watcher on a position whose `run_id` was cleared, or the run-start close.
- The trend module's bar day-boundary (16:24Z daily tick → UTC+8 inferred, not read from
  config), hence whether the XRP trail exit would have fired.
- Prod `.env` values (`STOP_DESK_TIMEOUT_S`, `PANEL_ENTRY_OVERRIDE`, `TREND_*`) — inferred
  from event payloads and code defaults.
- Agent 6's `ledger_invariant_cash_state` (9,866.35 at 01:18Z) vs `agents.cash`
  (9,891.72 at 21:08Z): the $25 gap is consistent with open-position margin at 01:18Z but
  was not reconciled leg by leg.
