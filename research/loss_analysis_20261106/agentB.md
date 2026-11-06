# Agent B — algorithm-authored outcomes, 2026-10-05 15:49Z → 2026-11-06 20:30Z

Scope: every exit the platform's code decided (breakeven ratchet, legacy trail, SL/TP watcher fail-safe, conviction-collapse, at_time, adapt/idle/no-prospect retires, orphan closes), the fee and sizing mechanics, and what the fleet did with its slots. AI-authored exits (`cyc` cycle closes, `arm` armed levels) are Agent A's; they appear here only where the split needs them.

Scripts: `b_load.py` (event pickle), `b_trips.py` (exit-author join → `b_trips.pkl`), `b_losers.py`, `b_fees.py`, `b_sizing.py`, `b_sizing2.py`, `b_fleet.py`, `b_agent63.py`, `b_watcher.py`, `b_verify.py`, `b_final.py`. Fills: `d/signals.tsv`; events: `d/events.tsv`; run rows: `d/runs.tsv`. Exit author = the `run_status → stopping` reason and `stop_mechanism` event in the 300 s before the final exit leg of each `trips1.pkl` round trip, keyed on the exit leg's `run_id`.

Ledger check (two independent records): agent 6 cash now 9891.72; prior report left it at 9918.92 on 10-05 → −27.20 realised in the window; the 468 reconstructed trips sum to −27.21. Exit legs summed straight from `signals.tsv` by `client_order_id` kind (flatten 407 legs / cyc 64 / arm 27 / NULL 29) reproduce the per-kind trip totals. Fee rate: 998 of 998 window legs at exactly 4.50 bp of notional (min = max).

## 1. Verdict, in profit-or-loss terms

| | n | net | gross | fees | ex-largest contributor |
|---|---|---|---|---|---|
| Agent 6, all trips | 468 | **−27.21** | −1.46 | 25.74 | ex-SUI −3.25 trip: net −23.96 |
| of which algorithm-closed (my scope) | 435 | **−6.27** | +17.67 | 23.94 | |
| — breakeven ratchet | 377 | +17.69 | +37.41 | 19.72 | ex-SUI +1.18: +16.52 |
| — legacy trailing lock | 16 | +14.86 | +16.52 | 1.66 | ex-LINK +2.84: +12.02 |
| — SL/TP watcher fail-safe, stop side | 25 | **−34.93** | −33.30 | 1.63 | ex-SUI −3.25: −31.68 |
| — SL/TP watcher fail-safe, take-profit side | 1 | +2.51 | +2.59 | 0.08 | |
| — conviction_collapse | 11 | −2.93 | −2.48 | 0.45 | ex-BTC −0.72: −2.21 |
| — adapt_retired flatten | 2 | −0.65 | −0.51 | 0.15 | |
| — orphan close (run_id NULL) | 3 | −2.82 | −2.57 | 0.25 | ex-ETH −2.06: −0.76 |
| AI-closed (Agent A): cyc 20 / arm 13 | 33 | −20.93 | −19.13 | 1.80 | |
| Agent 60 (us-stock), all | 30 | +0.48 | +0.95 | 0.46 | ex-MCD −2.00: +2.48 |
| Agent 63 (trend module), window | 2 closes | **−51.31** | −50.97 | 0.34 | each close ≈ −25.5; n=2 |

The desk lost **$27.21 on $28,600 of notional** (−9.5 bp per trip net, −0.5 bp gross). Fees are 95 % of the loss. The algorithm's own exits are net **−$6.28** as a group: the ratchet and the trail bank **+$32.55** over 393 trips and the 25 stop-side watcher closes give back **−$34.93**. One stop-out erases ~30 ratchet wins (ratchet mean net $0.047/trip, median $0.022). That ratio is the shape of the book; with and without the single largest trip every category keeps its sign (no INCONCLUSIVE category at the mechanism level).

Agent 63: cash 9933.77 = −66.23 since reset; −14.92 of it is the pre-window closed loss already reported on 10-05, **−51.31 is this window**: two longs (BNB 0.6667 @744.12, XRP 197.8 @1.3637) sold on 10-08 15:20/15:23Z with `run_id NULL`, `client_order_id NULL`, pnl −25.54 and −25.42. The module's exit is a 1.5×ATR14 initial stop written to `positions.stop_loss` and enforced intraday by the SL/TP watcher (`trend_module.py` lines 12, 255-274, 485-508); both closes are that stop firing (−5.1 % and −9.4 % of entry notional). The two positions were +$3.6 open on 10-05 and −$51 three days later; n = 2 says nothing about the module's edge, but it is the largest single algorithm-authored loss in the window and it has no run events at all — it is invisible to every monitor built on `run_events`.

## 2. Per-category outcomes, with reasons

### 2.1 Breakeven ratchet — 377 trips, +17.69 net (+16.52 ex-best), WR 75 %, median hold 20 min, median notional $38.6

Mechanics as read from 377 `stop_mechanism` payloads: `arm` = 1.78 × the round-trip fee on the largest book held (ratio 1.775–1.782 on all 377 → `BREAKEVEN_ARM_FEES=1.78` must be set on prod; code default is 1.0), i.e. 16 bp of notional; the floor locks 50 % of the excursion above the fee (`RATCHET_LOCK_FRAC` default 0.5). Observed: peak excursion / arm median 1.91, give-back (peak − exit)/peak median 51 %, realised gross median +14.5 bp (mean +17.6 bp), i.e. **the ratchet banks about +$0.05 after 20 minutes**.

Reason money was made: the mark moved ≥16 bp in the position's favour and the rule sold the retrace at half the excursion. Reason the bank is small: it is sized to the fee, not to the move — 233 of 377 fires (62 %) closed at a gross below 2× the round-trip fee (net −1.57 on those 233), 94 fires (25 %) netted ≤ 0 (−4.91), 28 fired at or below zero gross (−3.49). Peaks summed to $87.32; realised gross $37.41.

Sampling gap (distribution fact, not a claimed recovery): the engine's value at the moment it fired was $15.33 below the rule's own floor summed over 377 fires (median floor $0.109 vs $0.059 at fire; realised gross median $0.056). The 60 s scan sees the mark after it has already passed the line. Whether that $15.33 is recoverable depends on how marks move between scans; not tested on candles here (last month's analysis rejected the same figure as a cause for the same reason).

Agent 60 ratchet: 13 trips +2.32, of which MCD −2.00 is a ratchet fire at total −$2.00 against a +$0.20 floor — the position was held overnight, stops were dormant on the closed market, and the open gapped through the floor. The ratchet label on a −$2 close is the "dormant-then-gap" case, not a defect in the arm.

### 2.2 Legacy trailing lock — 16 trips, +14.86 net (+12.02 ex-best), WR 88 %, median hold 53 min, median notional $93.6

`order_plan.trail.activate_usd` median 248 bp of notional (desk-authored `trail_arm_pct` raised to the 2.5 % stop by the "must not arm inside the stop" rule), giveback 0.20; realised gross median +218 bp. Reason: these are the 16 positions that ran +2.5 % — the only trips in the book allowed to become real winners, because the ratchet below them did not fire first (16 of 16 trips whose run peak reached `activate_usd` were taken by the trail (14) or the watcher (2); none was clipped by the ratchet). The book's whole positive gross lives here and in the ratchet.

### 2.3 SL/TP watcher fail-safe — 26 trips, −32.42 net; stop side 25 trips **−34.93** (−31.68 ex-worst), WR 0/25, median loss −220 bp, median hold 140 min

Author: `risk_engine` sl_tp_watch closing `positions.stop_loss` (desk-authored, capped at 2.5 % by `stop_cap`: 220 of 220 events `cap_pct 2.5`) with `client_order_id NULL`. Per `stop_router.py` the hit should first convene an immediate full-tier desk decision, with the code close only after `STOP_DESK_TIMEOUT_S` (180 s) of silence. On the tape: **a `decision` event landed inside the 200 s before the close on 2 of 26 trips, and both were rule fallbacks ("no llm response", "decision json unparseable") → hold.** Median time since the last decision at the close: 19.4 min. The emergency discussion produced zero AI rulings on 26 stop hits; every stop exit in the window was code's. (Routing did run: 14 `gate_skip` "loss cooldown BYPASSED: routed stop hit awaits the desk's ruling" events on 5 of these runs.)

Reason money was lost: the mark went 2.5 % against a position whose size and stop the desk set; the desk did not answer; the fail-safe sold. 25 of 26 closes landed worse than the authored stop (median ~15 bp past it; SUI 114 bp / $1.01, UNI $1.20, NEAR $0.43), total **$1.95** of slippage attributable to the wait-then-scan sequence. The one take-profit-side close (LIT +2.51) is the same watcher on `take_profit`.

13 of the 25 trips with net < −$1 are in this category (−28.18). Loss bp per trip −159…−366; authored stop −250 bp on 21 of the 23 big losers with a recorded stop (the other two −30 and −150 bp). The 2.5 % cap (raised from 0.5 % on 09-04) is still in force.

### 2.4 conviction_collapse — agent 6: 11 trips −2.93 (−2.21 ex-worst), WR 0/11, median hold 176 min, median loss −70 bp; agent 60: 13 trips −0.42, median hold **0.3 min**

Rail: close when the desk's conviction reads < 0.35 two cycles running (`RUN_CONVICTION_EXIT_FLOOR` 0.35, `_STRIKES` 2). Agent 6's 9 real fires: conviction decayed from 0.29–0.66 to 0.15–0.35 while 8 of the 9 positions were 15–184 bp underwater (BCH closed at +4 bp); it is a de-facto loss cut at ~−70 bp, every one a loser because the desk's conviction tracks the P&L. The other 2 (TAO, ARB) and all 13 of agent 60's were closed 0–76 s after entry: the rail counts conviction reads from the flat cycles before the entry (the entry gate reads confidence, the rail reads conviction — the backlog defect from 10-05, still unshipped). 15 zero-hold trips, **−$0.24**, pure fee burn; sign certain, dollars trivial.

### 2.5 Retires and orphans

- `adapt_retired` flattens: 2 trips −0.65. `idle_retired` (295 runs) and `desk_retired` (14) fired on flat books only: 0 trips, $0 fee. `no_prospect_switched` (1,297 runs): fires flat-only; the 30 trips in those runs (−17.79) closed before the switch and are counted in their own exit category.
- Orphan closes: 3 trips −2.82 (XRP +0.48 after 3.1 days, ETH −2.06 after 2.0 days, SOL −1.24 after 1.6 days). Their runs ended `positions_held` (`stop_flatten 0`) on 10-10 08:34 and 10-31 09:50 — a fleet stop that left the book open — and the position was later sold with `run_id NULL`. The reclaim path (`orphan_reclaim.py`) hands the decision to the desk, so the author of those three sells is not recoverable from this dump.

### 2.6 The 25 trips with net < −$1 (−50.10; −46.85 ex-worst) vs the other 443 (+22.90)

By author: watcher stop closes 13 (−28.18), desk cycle closes 6 (−10.62, Agent A), armed exits 4 (−8.01, Agent A), orphan 2 (−3.30). Median loss −221 bp against a −250 bp authored stop; 4 of 25 had any positive peak at all (run-level `peak_pnl − peak_realized`: 4–61 bp), and only 4 ever cleared the ratchet arm (SUI, LINK ×2, BCH; peaks 17–61 bp) — in those 4 the position reversed from +0.15–0.49 to −1.2…−3.2 between 60 s scans or across a partial exit, and the ratchet's 50 % floor on a $0.2 excursion sits $0.10 above entry, i.e. it protects nothing against a 2.5 % move. No existing rail should have fired earlier on the recorded marks: 21 of 25 went straight down and the stop is where they closed. The reason these trips lost is the geometry the desk authored (size up to $375 at a 2.5 % stop) meeting a no-edge entry, not a rail that failed to fire.

### 2.7 Fees, legs, sizing (PREREG H3, H5)

- Fee: 4.5 bp on every leg; 998 legs = 2.13/trip; 472 entry legs (4 adds, fee $0.17, all `cyc`), 526 exit legs (58 partials before the final leg, fee $0.94, 44 `cyc` + 14 `arm`). Multi-leg trips 43: −15.07 net (gross −11.53) vs single in/out 425: −12.14 (gross +10.06). Fees $25.74 = 95 % of |net|.
- Gross per trip −2.0 bp, trip-bootstrap CI [−9.4, +5.3], symbol-clustered CI [−8.3, +2.9]; gross $ CI [−25.1, +23.5]. **Contains 0.**
- Size clamp: 292 `size_clamp` events, all `null_size_cap`, `cap_frac 0.25`, cap = 0.25 × max_bet $375 = **$93.75** — unchanged from last month. It fired on **187 of 468 trips** (the trips where `order_params.outcome` was `defer` 105 / `absent` 74 / parsed-null 12 — the desk returned no size) and cut their size by 64 % (sum size_before 48,142 → 17,109). The other **281 trips were sized by the desk itself** (`size_frac` 0.05 on 162, 0.1 on 58; implied budget $375) at a median **$20.0**. That, not the clamp, is why the book's median fell from $94 to $45.6.
- Clamped vs desk-sized: gross +1.2 bp vs −4.1 bp, difference 5.3 bp CI [−9.9, +20.7]: no difference. Net −12.21 (fees 15.47) vs −15.00 (fees 10.27).
- Without the clamp (clamped trips scaled by size_before/size_after): notional 28,600 → 59,878, gross −1.46 → +5.99, fees 25.74 → 53.89, **net −27.21 → −47.91**. The clamp halved the book and the loss, not the sign.

### 2.8 Fee counterfactuals on this tape (same fills, same legs, agent 6)

| fee model | net | ex-worst trip |
|---|---|---|
| actual 4.5 bp/leg | −27.21 | −23.95 |
| zero fee | **−1.46** | +1.71 |
| Hyperliquid maker 1.5 bp/leg | −10.04 | −6.85 |
| 2.25 bp/leg | −14.33 | −11.12 |
| Binance maker 0 on entries + 10 bp taker on exits | −30.07 | −26.81 |
| Binance VIP0 7.5 bp/leg (BNB discount) | −44.37 | −41.06 |
| Binance spot taker 10 bp/leg | **−58.67** | −55.32 |

Break-even flat fee on this tape: 0 bp (gross is negative). Ex-worst the zero-fee tape is +1.71, so the sign of gross is INCONCLUSIVE — consistent with the CI.

### 2.9 What the fleet did with its slots (in-window counts; the brief's 14,459 / 9,486 are since 09-25)

Agent 6 / fleet 44: `gate_skip` 10,555 — stage `risk` 10,205 of which "decision is 'hold'" 10,018, "confidence below threshold" 183, "loss cooldown" 190, `add_limit` 78 (62 "position underwater", 14 "max_adds=0"), `mark_drift` 38, `execute` 14 (fence: run stopped), `desk_retire` 14. `run_status` 8,136; stopping reasons: `no_prospect_switched` 1,297, `stop_event:trailing_lock` 394, `idle_retired` 295, `desk_retired` 14, `conviction_collapse` 11, `adapt_retired` 9, `at_time` 4, `stop_eval_failed` 3; paused: `eval_failed` 13, `stop_eval_failed` 3.

2,035 runs alive in the window, **63 per day, median lifetime 68 min**; 1,578 (78 %) never traded — 1,268 switched out by the 1-hour no-prospect rule, 295 idle-retired, 14 desk-retired. Slot occupancy 91 % (mean 7.24 of 8 running), but **a position was held for 959 of 6,181 slot-hours (15.5 %)**; the other 4,636 alive slot-hours were a flat desk deciding hold. Churn fee: $0 (all three retire rails are flat-only, verified: 0 trips on 295 + 14 + 3 runs). Its cost is LLM load: 10,887 decisions, 3,136 "no llm response" (29 %), 1,201 `no_verdict`, 3,160 rule-fallback decisions — on a fleet whose entries carry no edge, the fastest-cycling slot machine the platform has.

Agent 60 / fleet 43: `gate_skip` 1,415 (hold 1,161, "market closed — flatten queued" 144, "market closed" 48, confidence 39); `run_status` 440; 112 runs alive, 73 idle-retired without a trade (median lifetime ~20 h). **Fleet 43 ran 3 of 8 slots for 709 of 773 hours** (mean 2.89; status `replenishing:3/8`); the planner's rejection reasons are fleet-level events not present in `run_events` — the stall cause is not in this dump. 30 trips, +0.48; 13 of them are the zero-hold conviction burns (−0.42).

## 3. Hypotheses tested

| id | prediction | result |
|---|---|---|
| H3 FEE-SHARE | fees ≥ 50 % of \|net\|; gross CI contains 0 | **SUPPORTED, not falsified.** fees/\|net\| = 0.95; gross −2.0 bp, symbol-clustered CI [−8.3, +2.9]; gross $ CI [−25.1, +23.5]. Loss ≈ 468 × $61 × 9 bp = $25.7 = the fee bill. |
| H5 SIZE | the 0.25 null_size_cap caused the $94 → $45 median fall and scales the loss, not the sign; falsified if clamped trips show different gross bp | **FALSIFIED on the cause, held on the scale.** The cap is unchanged ($93.75) and fired on 187 trips whose median is still $93.7; the median fell because the desk now authors `size_frac 0.05–0.1` on 281 trips (median $20). Clamped − unclamped gross bp = +5.3, CI [−9.9, +20.7] (no difference). Unclamped book: net −47.91 vs −27.21 — scale, same sign. |
| F-ARM / ratchet "banks a real winner" (10-05 §2.4 geometry) | — | Replicated: 377 fires at median +14.5 bp, 62 % below 2× fee, give-back 51 %. The rule now locks half the excursion (RATCHET_LOCK_FRAC 0.5), and median realised is positive ($0.022) — the 08-27 falsifier (median give-back < 100 %, median realised > 0) PASSES on this window. |
| "stop exits are AI-authored; code is the fail-safe" (stop_router design) | — | **FALSIFIED on the tape:** 0 of 26 stop hits received an AI ruling within the 180 s window; 2 received a rule-fallback hold; 26 of 26 were closed by the watcher. |
| "rotation (idle/no-prospect) costs money" (10-05 §4) | — | Re-confirmed REFUTED: $0 fee, 0 trips on 1,592 retired runs. |
| "zero-hold conviction burns fixed" | — | Not fixed: 15 trips, −$0.24, 13 on agent 60. |

Not in my scope and not tested here: H1 (entry edge), H2 (fix landed), H4 (short bias) — Agent A. I note only that 352 of 377 ratchet fires and 22 of 26 watcher closes are shorts; the mechanism split does not differ by direction.

## 4. What must change — each with the dollar it would have moved on this tape

1. **Stop hits: the desk is not being convened; stop exits are code's and the 180 s wait only costs slippage.** 0/26 AI rulings; 25/26 closes past the authored stop; **$1.95** certain on this tape (SUI $1.01, UNI $1.20 alone; sign survives ex-largest UNI: $0.75). Either make the emergency dispatch actually produce a `decision` inside 180 s (there is no event for the dispatch itself — add one, so the next tape can show it fired) or drop the wait and close at the stop. The −$34.93 behind these closes is the 2.5 % stop geometry on no-edge entries; last month's unconditional tests put exit-timing effects at ≈ 0, so I do not claim that figure as recoverable.
2. **The null-size cap now sizes "no size from the desk" at 5× the desk's own size.** 187 trips, net −12.21 (−8.96 ex-worst), carrying $15.47 of the $25.74 fee bill on 40 % of the trips. At the desk's own median size ($18.7): **+$9.77** (+$7.17 ex-worst). Not taken at all: **+$12.21** (+$14.72 ex-best; the fee saving alone is $15.47 and certain). A `defer`/`absent` size is the desk declining to size; treating it as "quarter of max_bet" was an R17 convenience for a desk that never sized — this desk sizes 60 % of the time. Both signs survive stripping the largest trip.
3. **Fee.** On this tape the fee is the loss: zero fee −1.46 (INCONCLUSIVE sign ex-worst +1.71). Of the real venue schedules only maker-side execution helps: Hyperliquid maker 1.5 bp **+$17.17** (−10.04); Binance taker 10 bp **−$31.46** (−58.67); 0/10 maker-taker split −$2.86 (−30.07). The simulated 4.5 bp is already below every taker schedule — any move to a real venue at taker rates doubles the loss on the same fills. Fee reduction changes the scale of a zero-edge book; it cannot change its sign.
4. **Zero-hold conviction_collapse** (rail counts flat-cycle convictions): 15 trips, **+$0.24**, certain. Count only reads taken while holding. Tiny, and it was on the 10-05 backlog.
5. **Ratchet 60 s sampling vs its own floor: $15.33** across 377 fires. Candidate only — recoverable only if marks move continuously between scans; needs the 15 m-candle replay before it is a finding.
6. **Trend module exits must emit run_events.** −$51.31 in this window with zero telemetry; it is the largest algorithm-authored loss and the only account whose closes cannot be attributed from the tape. n = 2, nothing to say about the rule's edge.
7. **Fleet 44 churn** is not a dollar item ($0 fee) but it is the LLM load: 63 runs/day, 1,578 never-trading runs, 29 % no-response. A slot that is flat 85 % of the time and flips symbol every hour is what the no-prospect switch was built to do; it is also why the full-tier trader is silent a third of the time. Fleet 43 at 3/8 for 92 % of the window: cause not in this dump.

## 5. What I could not determine

- Why fleet 43 sits at `replenishing:3/8` — planner/gate rejections are fleet events, not in `run_events`.
- Whether the stop-router emergency dispatch fired at all: there is no event for the dispatch, only for the resulting decision (which did not come). I can show the decision did not land, not why.
- Prod env values: `BREAKEVEN_ARM_FEES` (inferred 1.78 from 377/377 payload ratios), `RATCHET_LOCK_FRAC` (inferred 0.5 from the 51 % give-back), `STOP_DESK_TIMEOUT_S`, `RUN_CONVICTION_EXIT_*` — read from payloads and code defaults, not from the host.
- Author of the 3 orphan sells (run_id NULL) and the trend module's two closes beyond "the watcher at the ledger stop" — no events.
- Peak/drawdown for 21 of the 25 big losers comes from the run row (`peak_pnl_usd − peak_realized_usd`), not from `equity` events (7-day retention); for the 19 runs carrying 2–3 trips the run-level peak may belong to a sibling trip.
- The ratchet sampling gap's recoverability (item 5) — needs candles.
