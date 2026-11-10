# Automation monitoring — 2026-11-10 (UTC day) — daily 24h sweep

Newest-first. Authority for rules/access/traps: `HANDOFF-automation-monitoring.md`.

## 24h sweep — 2026-11-10T17:27:57Z (KST day 2026-11-10 = 11-09T15:00Z → 11-10T15:00Z)

> Early P&L commit 4d46a9e (HANDOFF §10 trap); this revision completes it.

Prod clock `SELECT UTC_TIMESTAMP()` = 2026-11-10 17:27:57 (fire ~2.3 h late vs 15:07Z).
Window = 2026-11-09T17:28Z → 2026-11-10T17:28Z. Worker + backend on
`sooppiy-backend:20261109-sweep-20261109` (374bba4); origin/main 9fb2fc0 = +1 docs commit
→ no code drift. Trading set re-derived = **exactly {6, 60}**. No leftover `/tmp/sooppiy-sweep.*`
from a dead prior run.

### 1. P&L — dollars first

| window | agent 6 (info) | agent 60 (forevery1969) | combined | n closes | fees (all legs) |
|---|---|---|---|---|---|
| **24 h window** (ledger ≈ Σ stopped-run realized) | **+2.11** | **0.00** | **+2.11** | 58 | 1.48 |
| **KST day 11-10** (close legs; entry fees ≈ −0.6 not netted) | +1.48 gross-of-entry-fee | 0.00 | +1.48 | 46 | 1.24 |
| UTC day 11-10 (pnl_audit ledger, 00Z→17:28Z) | +2.14 | 0.00 | **+2.14** | 54 | 1.43 |
| UTC day 11-09 (pnl_audit ledger) | −0.07 | 0.00 | −0.07 | 5 | 0.13 |
| open uPNL now (3 shorts, agent 6) | FIL −0.10, NEAR −1.92, BTC −0.03 = **−2.05** | none | **−2.05** | — | — |

- pnl_audit `--since 2026-11-09`: EXIT 0, both days `ok` (resid 0.00 / 0.01), 71/71 validated.
- Independent routes agree: `signals` operation fills 115 (58 short, 57 cover), Σfee 1.4796,
  Σ`pnl` on closes 2.8452 = my close-leg replay 2.84; Σ`realized_pnl_usd` of the 80 agent-6
  runs stopped in window = 2.1082 ≈ ledger.
- **CORRECTION (Agents A and B, both, two query shapes each):** closes = **57**, not 58 (58 =
  entries; 151802 HYPE still open); flattens 54 not 55; my "84 % win" was close-leg P&L before
  entry fees. **Fee-inclusive per trip (n = 57): net +2.14, win 45/58 = 77.6 %, avg win +0.058,
  avg loss −0.037**, gross 3.63, fees 1.48 = **41 % of gross**. Largest +0.481 (151796 ETH),
  worst −0.206 (147516 TRUMP watcher stop). **Without the largest: +1.66; without the top 3:
  +1.00 — sign holds, but 53 % of the day's net came from 3 of 57 trips (all 15:20–15:46Z).**
- **Mark-to-market verdict: realized +2.11, open −2.05 → ≈ +$0.06 for the day.** Agent 60
  made **zero trades**. Lifetime realized: agent 6 −104.99, agent 60 −1.34.
- Stopped runs by reason (agent 6): `stop_event:trailing_lock` 54 runs **+2.38**,
  `no_prospect_switched` 26 runs **−0.27**; agent 60: `idle_retired` 3 runs 0.00.
- Notionals are tiny: open shorts $18.7 / $103.8 / $45.5 on a ~$9.9k book.

### 2. Who authored the day's P&L — exits (A and B agree, run_events `stop_mechanism`)

| exit author | n | gross | fees | **net** | reason |
|---|---|---|---|---|---|
| **breakeven ratchet** (platform rail, `mechanism: breakeven_ratchet`) | **51** | +2.66 | 1.40 (**52.5 % of gross**) | **+1.26** | arms at `BREAKEVEN_ARM_FEES=1.78` × round trip (prod env) ≈ $0.03 on $18.75, then keeps fee floor + 50 % of excursion (`RATCHET_LOCK_FRAC` 0.5). Median captured move **0.154 %**, median hold 21 min. 11/51 net negative (−0.21): price crossed the floor between polled marks |
| desk-planned trail (`order_plan.trail`, give 0.15) | 3 (ETH 151796, ENA 151795, HYPE 151789) | +1.17 | 0.05 | **+1.12** | the only exits that rode the 15:20–15:46Z leg (−2.4 % to −2.7 %) |
| watcher stop (147516 TRUMP) | 1 | −0.19 | 0.01 | −0.21 | desk-authored **1.0 % stop on a coin whose mean 1 h range was 1.55 %** (B, n = 27 h); filled 0.23 % through the level |
| desk cycle covers | 2 (BNB 144821 −0.065, ETH 150492) | | | | |

**The desk did not want out.** On the cycle before every ratchet flatten the desk's last verdict was
`sell` (stay short) ×30 or `hold` ×21 — never a close (Agent A). The rail, not the AI, authored 51 of
57 exits and capped gross at ≈ 2× fees by construction (Agent B).

### 3. Entries (Agent A) — direction was right, size and exit were not

- 58 entries, **all shorts**, all `decided_by ai`, 57/58 light route. The tape really fell: ETH −5.1 %,
  HYPE −5.1 %, ENA −3.6 %, NEAR −2.5 %, FIL −2.0 %, SUI −2.0 %, LINK −1.9 %, TRUMP −1.6 %; only BNB,
  LTC, UNI rose.
- The panel made the book 100 % short: desk→panel `sell→sell` 70, `sell→hold` 55, `buy→hold` 40,
  **`buy→sell` 34**, `buy→buy` 1. 20 of 58 entries were desk *buys* flipped to short: +0.66, 17/20
  wins. BNB 144821 is the one flip that lost (BNB rose). The verb flip is **not recorded as a chair
  amendment** (amendment lists only confidence/report) — attribution gap, P&L-positive today.
- **Size is the desk's own choice, not a cap:** notional = `size_frac` × `max_bet_usd` ($375 = 30 %
  of $1,250 run budget) on all 53 sized entries, `railed={}` every time; `size_frac` 0.05 (the legal
  minimum) ×38, 0.10 ×9, others ≤ 0.5. **$18.75 = 0.19 % of the book.** machine_size_usd averaged $372.
  Total notional 58 entries = $1,654; net = 12.9 bps of notional.
- `null_size_refused` 31 (agent 6: 16 `absent` + 15 `defer`, 28 of them flat-book sells in a falling
  tape) — P&L of those not quantified.

### 4. Agent 60 — $0, desk/panel-authored, inside the plan cap

All six runs us-stock (MDT, MSFT, HD → idle_retired 14:37Z after 11/12/11 AI holds; CMCSA, LOW, MCD
running). 66 decisions: hold 64, buy 2; the trader proposed buy 30× and the panel turned 28 into
hold; the 2 buys (HD 20:09Z, MCD 15:10Z) were `null_size_refused` (order_params deferred). Fleet 43
`replenishing 3/8`: 6,382 `candidate_skipped` = "plan allows 3 concurrent run(s)". Plan `pro`,
`auto_renew=1`, expires **2026-11-17T21:52Z**.

### 5. Three-axis verification

- **DATA:** net +2.14 by (a) A's pairing, (b) `pnl_audit.replay_realized`, (c) Σ`realized_pnl_usd`
  (+2.1394), (d) pnl_audit day table — four routes. Exit-mechanism split 51/3/1/2 by A and B
  independently. Fee 1.4796 from `signals` = trade events.
- **CODE:** `_breakeven_floor_hit` on origin/main (run_engine.py ~1523–1615): floor = fee_floor +
  `RATCHET_LOCK_FRAC`(0.5) × (peak − fee_floor); arm = `BREAKEVEN_ARM_FEES` × round trip. Running
  worker env: `BREAKEVEN_ARM_FEES=1.78`, `RATCHET_LOCK_FRAC` unset (0.5), `BREAKEVEN_RATCHET` unset (on).
  `_mute_cycles` present in the live image (R31).
- **ADVERSARY:** "the desk banked small wins by choice" — **refuted** (last verdict before 51/51
  ratchet fires was sell/hold). "Fees are the problem" — partly: fees are 41 % of gross *because* the
  exit rail banks 0.15 % moves; at the desk's own exits (trail) fees were 4 %. "Holding wins" —
  **selection-conditioned** on a −2 % to −5 % tape; see §7 for the experiment.
- **My own errors this run:** (1) 58→57 closes and 84 %→77.6 % win (fixed above); (2) I wrote a
  space-form literal `created_at >= '2026-11-09 17:28:00'` against `signals.created_at` (varchar
  `T…Z`) — caught on the first read and re-run with `T…Z`. `signals.created_at` is the same trap as
  `run_events.ts` (added to HANDOFF §10).

### 6. 24-hour re-verification ledger

| item | evidence on prod | verdict |
|---|---|---|
| R31 `_mute_cycles` (b773a20, image 20261109-sweep-20261109) | image on worker + backend = the ship record's tag; idle_retired since 18:37Z: **3 (agent 60) + 1 after window (agent 6), all with 11–12 AI verdicts**; zero-verdict idle retires **0** (was 24 in the prior 24 h) | falsifier (1) **HELD** (confound: agent-6 runs now die by ratchet/no-prospect at ~1 h); falsifier (2) "idle retires still occur on an up day" **HELD** (n = 4); falsifier (3) no run past at_time **HELD** (9 running + 83 stopped checked) |
| R28 `llm_silence` alert | fired `recovered` 11-09T19:10Z, `silent` 22:45Z (87.5 % mute, a 2nd short outage 20:45Z→~00Z: 239 timeouts, 21h:106 22h:81 23h:46, 0 after 00Z), `recovered` 11-10T00:31Z — email+sms each | **HELD** (now proven in both directions) |
| f545d3e #1 `RUN_NULL_SIZE_REFUSE` | 31 refusals (agent 6) + 2 (agent 60); no refused entry filled later | **MEASURABLE, behaving as designed**; its P&L cost in a falling tape is unquantified (watch) |
| f545d3e #2 stop close-first + 30-min fence | 1 stop (TRUMP); no re-entry attempted within 30 min | NOT YET MEASURABLE (fence never challenged) |
| f545d3e #3 conviction while holding | no conviction-collapse exits | NOT YET MEASURABLE |
| 7110f54 #4 handoff on `positions_held` | no `positions_held` stops | NOT YET MEASURABLE |
| W-chair-refuse | 0 `panel_substitution_refused`; but 34 buy→sell verb flips not recorded as amendments | NEW SHAPE — recorded, not a refusal |
| W-post-stop-cycle | **8 of 83 stopped runs (~10 %), 46 events 4 s–3 m after stopped_at**, incl. `buy`/`sell` decisions and one `order_intent open` (151247); **0 trades** | watch **escalated**: reproduced at n = 8; fence holds; still $0 |
| R29 fleet 43 plan cap | 3/8, 6,382 cap skips; expiry 11-17T21:52Z auto_renew 1 | OPEN |
| 11-09 ship record (deploy log 20261109-183755 374bba4) | prod `.env` `SOOPPIY_IMAGE` = 20261109-sweep-20261109; origin/main only +docs | **HELD**, no drift |

### 7. Today's solution — the experiment, and why NOTHING ships

**Losing shape inside a winning day:** the day made +$2.14 realized, but **open uPNL −2.05 erases
it to ≈ +$0.06 mark-to-market**; fees took 41 % of gross; the platform's ratchet authored 51/57 exits
at a median 0.154 % capture while the desk's own trail, on 3 trips, earned 52 % of the day.

**Hypothesis H-ratchet-arm-too-low (stated before the replay):** the ratchet arm (1.78 × round trip)
cuts winners the desk's own bracket would have carried; raising it (k × current arm) raises realized
P&L. **Falsifier:** on windows other than today, at a calibrated k = 1, higher k does not beat k = 1
with a consistent sign (with and without the largest contributor).

**Measurement** (`research/ratchet_arm_replay.py`, new, read-only; every ratchet-fired agent-6 run
replayed from entry with its own bracket + trail + RATCHET_LOCK_FRAC 0.5; k = None = no ratchet).
Δ = sim(k) − actual, $; "ex" = without the largest contributor.

| window | candles | n | actual | calib k=1 (sim vs actual) | Δ k=2 | Δ k=3 | Δ k=5 | Δ k=10 | Δ none |
|---|---|---|---|---|---|---|---|---|---|
| **today 24 h** | 1m | 50 | +1.05 | 1.26 vs 1.05, median err 0.005 ✔ | +0.96 | +4.06 (ex +3.07) | +7.62 (ex +5.84) | +12.27 | +24.76 |
| today 24 h | 15m | 50 | +1.05 | 2.51 vs 1.05 | +2.28 | +3.86 | +12.20 | +15.17 | +23.71 |
| 11-01 → 11-09T17Z | 15m | 64 | +3.01 | 8.57 vs 3.01 ✘ | +3.94 | +6.34 (ex +0.91) | +9.51 | +25.00 | +18.15 |
| 09-20 → 10-01 | 15m | 50 | +3.39 | 3.15 vs 3.39 ✔ | −4.38 | **−13.91** | **−13.48** | +7.80 | +17.58 |
| **October** | 15m | 303 | +13.40 | −3.69 vs 13.40 ✘ | −14.67 | −0.67 (ex +4.37) | **−25.25** | +2.09 (ex −3.48) | **−24.57** |

**Verdict: H-ratchet-arm-too-low is NOT SUPPORTED — killed as a general rule.** It wins on the two
trending windows (today, 11-01→11-09) and loses at k = 3–5 on the one older window with good
calibration (09-20→10-01) and at k = 5 / none on the largest window (October, n = 303). The sign
depends on the tape (trending vs chop), not on k. The k-curve is not monotone in any window except
today. A ship would have been tuning the rail to the last 24 hours, which the owner law forbids.
Also: the 15m simulator mis-calibrates badly on October (sum −3.69 vs +13.40), so no older window is
a strong reading either way. **No rail change, no env change.**

**What ships instead — the measurement, so the decision can be made on calibrated data:**
Hyperliquid retains only ~5,000 1m candles (~3.5 days), so a calibrated replay is possible ONLY on
recent days. From today, **every daily sweep runs `research/ratchet_arm_replay.py` on its own window
and appends the k-table** (HANDOFF §4 addition). **Promotion trigger (R32, STAGED):** after ≥ 10
sweep-days with calibrated 1m replays (median calib error ≤ $0.01), if Σ Δ(k*) > 0 with and without
the largest day AND it is positive on ≥ 7/10 days including ≥ 3 non-trending days (|ETH day move| < 1.5 %),
propose `BREAKEVEN_ARM_FEES = 1.78 × k*` to the owner (prod `.env` is the owner's — HANDOFF §9).
**Kill trigger:** Σ Δ ≤ 0 over those 10 days → R32 DROPPED, ratchet stays as is.

**AI-first part (desk lessons) — STAGED, not shipped (n too small):**
- *Stop width vs the symbol's hourly range* — TRUMP 147516: 1.0 % stop vs 1.55 % mean 1 h range,
  −0.206 = 16 median ratchet wins. **n = 1.** Promote to a skill line when ≥ 5 watcher stops in a week
  sat inside one median hourly range of their symbol and their counterfactual at 2× the stop is better.
- *Desk sizes at the legal minimum (0.05 × $375 = 0.19 % of book).* **Not** a recommendation to size
  up: the 09-08 permutation test and the 11-06 loss analysis found **no entry edge**, and one −2 % to
  −5 % tape where every short won is exactly the selection-conditioned read (memory) that cost six
  retractions. Sizing ×20 would have made ~+$36 today and ~×20 the month's −27 fees-led loss.

**Counterfactual at the live mark of what ships:** $0 (a read-only script and notes).

### 8. Killed / corrected hypotheses

- **H-ratchet-arm-too-low** — killed as a general rule (§7; regime-dependent, Oct n = 303 against).
- **"hold-to-bracket +$33.74 vs +$2.17"** (my first, uncalibrated replay of today) — retracted as
  evidence: hindsight mark on a falling tape, not modelled lock fraction (calib was off by 0.64 → fixed).
- **"the desk banked tiny wins by choice"** — refuted (51/51 ratchet fires came after a sell/hold verdict).
- **"a platform cap shrank the desk's size"** — refuted (`railed={}` on 53/53; notional = size_frac × max_bet).
- **58 closes / 84 % win** (mine) — corrected to 57 / 77.6 % fee-inclusive.

### 9. Not verified

- Ratchet tick cadence (the "gapped through the floor" explanation for 11 negative fires is inferred).
- Whether `size_scale` (0.40–1.0 on the decision) is meant to apply in apply mode — notional ignores it (B).
- Sizing path of 5 entries with no `order_intent` row.
- Worker log 17:28–18:38Z (container restarted at the 11-09 deploy).
- 30-min re-entry fence firing (never challenged); P&L of the 31 null-size refusals.
- Whether agent-60 `scaffold` cycles were mute or closed-market.
- NEAR 151814 / FIL / BTC open entries are after the window; their −2.05 belongs to the next sweep.
- Exchange ground truth: replay uses Hyperliquid candles, the simulator fills on its own mark source.

### 10. Health

| check | value |
|---|---|
| containers | worker, backend `20261109-sweep-20261109` up 23 h; admin up; mysql healthy |
| `MAX(run_events.ts)` | 17:26:31Z at 17:27:57Z |
| tracebacks / ModuleNotFoundError / ERROR (24 h) | 0 / 0 / 3 (yfinance "SUI-USD possibly delisted") — worker log only from 18:38Z (restart at R31 deploy) |
| `sooppiy.com/api/health` | 200 |
| LLM | no-verdict agent 6: 33/98 (11-09 17–23Z) → 1/260 after 00Z; agent 60 13/29 → 0/37 |
| fleets | 44 active 6/8 (6 `slot_waiting: no_candidates`), 78 rotations; 43 active 3/8 (plan cap) |
| FleetPlanner | 1,278 ticks, researched 0, built 0 (replenishment via rotation only) |
| stamp defect | all 424 decisions carry `llm.source="rule"` incl. decided_by ai — known (memory), attribute via llm_usage |
| temp file | Agent B left `/tmp/agB_w.log` on the prod host — **deleted** this run |
