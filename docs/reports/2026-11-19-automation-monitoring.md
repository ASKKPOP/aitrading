# Automation monitoring — 2026-11-19 (UTC day) — daily 24h sweep

Newest-first. Authority for rules/access/traps: `HANDOFF-automation-monitoring.md`.

## 24h sweep — 2026-11-19T15:13:14Z (KST day 2026-11-19 = 11-18T15:00Z → 11-19T15:00Z, closed)

Prod clock `SELECT UTC_TIMESTAMP()` = 2026-11-19 15:13:14 (**on schedule**; no leftover `/tmp/sooppiy-sweep.*`). Image `.env` = worker =
backend = `sooppiy-backend:20261118-sweep-20261118` (f8a015c); origin/main after it is docs-only → **no code drift**. Trading set re-derived
= {6, 60} (fleet 44 agent 6, fleet 43 agent 60, both `active`); only agent 6 cycled (85 runs).

### 1. P&L — dollars first

| window | agent 6 (info) | agent 60 (forevery1969) | combined | closes / opens | fees |
|---|---|---|---|---|---|
| **KST 11-19** net | **+0.97** | 0.00 (0 fills) | **+0.97** | 68 / 68 | 2.10 (68 % of gross ≈ 3.07) |
| KST 11-19 without largest (FIL 226601 TP +1.01 close-leg / +1.00 trip-net, opened 11-18 05:17Z) | **−0.04 / −0.03** | — | **−0.04 / −0.03** | | |
| 24 h (11-18T15:13Z → 11-19T15:14Z) net | +1.03 | 0.00 | +1.03 | 70 / 69 | 2.15 |
| trips opened AND closed in window (n = 66) | +0.11; ex-largest winner (STRK 230385 +0.76) **−0.65**; ex-INJ +0.93 | — | | | |
| pnl_audit all_in UTC 11-18 (full) / 11-19 (to 15:13Z) | +4.87 / **−1.15** (`ok`, EXIT 0, orphan 0) | 0 | | | |
| open uPNL 15:13Z (BNB, TRUMP, STRK, AAVE shorts, $219 notional) | −0.52 | — | −0.52 | | |

- **Routes agree (4):** pnl_audit = signals SQL to the cent (+4.867 / −1.155); cash reconciliation 9,815.626 + 75.01 − 219.14 + R = 9,671.194
  → R = −0.299 vs signals since 11-18T18:07Z −0.296; Agent A and Agent B each rebuilt +0.967 by two query shapes.
- **Shape (A, n = 66 in-window trips):** 46 W +3.70 (avg +0.080) / 20 L −3.59 (avg −0.180) → win 70 %, **payoff 0.45** (yesterday 0.78).
  Largest winner STRK 230385 +0.76, largest loser INJ 229944 −0.82.
- **Verdict:** **inconclusive, not a profit.** The KST figure is one take-profit on a trip opened before the window; without it the day is
  −0.03, and the window's own trips flip sign without their largest winner. Week since 11-16 pnl_audit: **−1.86**. Agent 60: $0, 8th day.

### 2. Per-trade reasons (A = AI-authored, B = algorithm-authored; cross-checked)

**Authorship:** the AI authored all 70 entries, **70/70 shorts**, one thesis template ("crowded longs, extreme fear, downtrend"), light route,
gpt-oss:120b. Exits (B, trip-net): breakeven ratchet 58 **+1.97**, classic trail 2 +1.14, watcher TP 1 +1.00, conviction collapse 1 −0.30,
watcher SL 3 **−1.69**, armed exits 3 **−1.28**, desk `cyc:` 2 +0.28. Platform-decided exits n = 61 **+2.80**; exits at desk-chosen levels n = 9
**−1.69**. (A's table uses close-leg P&L, which excludes open fees — same ordering, different basis; reconciled.)

| run | sym | conf / sf | net $ | author | reason (evidence) |
|---|---|---|---|---|---|
| 226601 | FIL | 0.55 / 0.40 (11-18) | +1.00 | watcher TP | the write-once TP 0.5710 from 11-18 hit at 16:12Z; +1 h after would have been −0.12 → the TP was right |
| 230385 | STRK | 0.58 / 0.10 | +0.76 | classic trail | direction right (MFE 2.07 %); filled at its lock; +1 h later holding would have lost 0.55 |
| 230336 | STRK | 0.60 / 0.05 | +0.38 | classic trail | right (+4.1 % at 1 h); tiny size capped it |
| 228559 | ETH | 0.55 / 0.20 | +0.46 | desk half-cut + ratchet | the desk's cut at 1753.7 saved money vs the remainder's 1765.2 |
| **229944** | **INJ** | 0.53 / 0.10 | **−0.82** | watcher SL | short a "support break" that rose 2.2 % in 1 h (MFE 0.07 %) — wrong from the first tick. At 07:50:48Z price 7.18 crossed the desk's own 7.14 invalidation; **trader proposed `sell` conf 0.80 "Stop breach invalidates short; close now."; the chair amended to `hold` 0.32** (`order_discussion`, `chair.amended` [action]). Stop 7.249 filled 7.2806 at the top of a 1-minute spike (gap $0.143). Closing at the intent ≈ +0.46 better |
| 229544 | HYPE | 0.55 / 0.10 | −0.74 | armed half + SL | template short in a rising tape; 05:11Z trader "Full close locks loss", chair → hold 0.50; stop right at +4 h |
| 228805 | LTC | 0.58 / 0.05 | −0.57 | armed close | wrong at entry; 01:05Z trader "Close now to avoid stop hit", chair → hold 0.40; 9 holds past its 43.69 invalidation, armed exit moved to 44.4 |
| 229782 | BCH | 0.55 / 0.07 | −0.43 | armed close | tiny short, MFE 0.13 % in 6 h, slow grind up; its `sell`-as-close blocked by add_limit (underwater) 11:29Z |
| 228801 | SUI | 0.58 / 0.05 | −0.42 | watcher SL | wrong at entry (MFE 0.01 %); chair turned trader covers into adds twice (both blocked) |
| 229396 | BTC | 0.60 / 0.07 | −0.30 | conviction collapse | short into a rising BTC; crossed its 63,800 invalidation 09:00Z; chair `sell` (add) above it, blocked; collapse closed 11 s later — the exit was right |
| 49 others | | ≤ 0.1 | +0.33 | ratchet | scalps banked at near break-even; 13 net-negative ratchet fires Σ −0.29 (peak 1.0–1.3 × arm, next 62 s sample below the floor) |

- **Direction (A): yesterday's first positive reading did NOT replicate.** +1 h: 29/67 hits (43 %), +0.016 % (edge vs drift +0.10 %, −0.05 % ex-largest);
  +4 h: **18/56 (32 %), −0.55 %, t = −3.5**, no edge over drift. The tape rose ≈ +0.47 %/4 h and the book shorted it 70 times.
- **Capture:** hold-1 h counterfactual +1.87 better; hold-4 h **−7.03 worse** → on this tape the ratchet's quick exits saved the book from the AI's
  direction (B: same on n = 47 fires, −6.03 at +4 h).
- **Confidence:** corr(conf, notional) −0.09 (sizing ignores confidence, again); conf < 0.6 n = 40 −0.92 (−0.10 ex-INJ), conf ≥ 0.6 n = 26 +1.03.
- **Chair vs trader at entry:** flips (trader buy → chair short) n = 13 net +0.23, 8/12 right at 1 h; concurrences n = 52 net −0.28, 19/51 (37 %).

### 3. Experiments (hypothesis → falsifier → result)

**E1 — the day's AI disagreement: "the chair converting a trader's stated close/reduce into `hold` costs money."** Measured over every agent-6
cycle in the window whose final action was `hold` while the trader's `order_params.why` said close/cut/reduce/cover: **n = 9** (STRK 228558,
STRK 228635, SOL 228750, ETH 228559, LTC 228805, BNB 228823, HYPE 229544, INJ 229944, LIT 230634). The trader's verb was `buy` (the correct cover)
in 4 and `sell` (which would ADD to a short — the R40 ambiguity) in 5; the chair held in both cases. B's counterfactual on the 5 "full close"
intents: **+0.63, +0.17 without INJ**, 4/5 positive. A on 7 chair overrides of a trader cover: chair lost 0.38. **Against:** 11-17 E1 measured the
same class (chair `sell` over a trader cover, n = 32 since 10-01) and covering would have LOST 4.83. Two readings, opposite signs, today's is
n = 9 on one rising tape → **inconclusive; staged as R43 with the history measurement owed** (below). Not shippable.

**E2 — "tiny entries (sf ≤ 0.07) lose money; stop opening them."** Second reading today (A: n = 33, −0.68, −0.12 ex-largest; 11-18 n = 37 −0.54).
Pre-registered falsifier: since 10-01, trips with entry notional < $27.5 net ≥ 0, or lose LESS per trip than larger entries. Result (trip
rebuild from `signals`, relative close tolerance):

| entry notional | n since 10-01 | net | per trip | ex-largest | since 11-01 |
|---|---|---|---|---|---|
| < $27.5 | 326 | −2.01 | **−0.006** | −2.70 | **+1.36** (n = 189) |
| $27.5–60 | 167 | −7.34 | −0.044 | −5.82 | −1.62 |
| ≥ $60 | 272 | −13.49 | **−0.050** | −10.24 | −2.63 |

**KILLED (H-TINY):** tiny entries are the *least* damaging per trip, and positive in November. Two bad days are not the history.

**E3 — R32 ratchet arm, calibrated 1m replay** (`research/ratchet_arm_replay.py 2026-11-18T15:00:00Z 2026-11-19T15:14:00Z 6`, n = 52, 6 skipped).
Calibration k = 1: median |sim − actual| **0.0063 (passes)**, max 0.225; Σ sim 1.73 vs actual 1.58.

| k | 1 | 2 | 3 | 5 | 10 | none |
|---|---|---|---|---|---|---|
| Δ vs actual (+1.58) | +0.14 | +0.45 | +0.71 | −2.65 | −8.92 | −13.32 |
| Δ ex-largest | −0.08 | +1.44 | +1.70 | −1.66 | −11.52 | −18.25 |

A rising tape under an all-short book: moderate raises (k 2–3) win small, large raises lose. k = 3 tally: 11-10 +4.06, 11-13/16 +2.29, 11-17 −3.96,
11-18 +5.69, 11-19 +0.71 → **Σ +8.79, +3.10 without the largest day, 4/5 positive; 5 of 10 days.** STAGED (owner `.env` knob).

**E4 — R37 ratchet step-through, 5th reading (B):** Σ(floor − fill) **1.26 over 58 fires ($0.022/fire)**, median 0.011, max 0.082, 1.18 ex-largest;
fill = fire-time mark 53/53 (zero execution slippage); 5 fires below zero gross (Σ −0.10). Readings $/fire: 0.027, 0.019, 0.028, **0.022** →
**"R37 is worsening" (11-18) is REFUTED**; it is stable at ≈ $0.02/fire, $1.2–1.9/day, = 64 % of the ratchet's own net today.

**E5 — "the L-1118 lesson reached the desk through the RAG corpus."** Hypothesis implicit in the 11-18 ship. Falsifier: zero `monitoring`
chunks in the desk's recall after the 18:17Z deploy. Result: the 11-18 note IS in `desk_memory` (11 `monitoring` chunks, L-1118 in 2), but
**`run_engine._RECALL_KINDS = ("outcome", "lesson")`; `monitoring` is only `_RECALL_KINDS_FALLBACK`, searched when outcome+lesson return
nothing** (origin/main `run_engine.py:6017-6018` AND the running image). Data: 328 recalls since 18:17Z → 656 chunks, **all `outcome`**;
**15,601 recalls since 10-01, 0 with a monitoring chunk.** → **KILLED. L-1118 never reached a decision.** The "AI-first lesson via the note"
channel this sweep relies on has been dead since the two-tier recall shipped; any AI-first lesson must be a **skill** (ingested as `lesson`) or
a prompt line. Consequence: the R42 7-day falsifier ("did the RAG lesson change behaviour?") is **void** — there was no treatment. H-CUT itself
is still measured as an observation: day 1 after 18:17Z n = 2, Σ(hold − cut) **−0.14** (ETH −0.24 the cut saved, STRK +0.10).

**E6 — R41 (B):** two losing partials with a remainder (STRK 228635 — ratchet fired normally; HYPE 229544 — remainder never positive) → $0, no instance.

### 4. Three-axis verification

- **DATA:** P&L by 4 routes (above). Chair-hold n = 9 read directly from `order_discussion`/`decision`/`order_params` (INJ 229944 payload read raw).
  Recall claim by two query shapes (24 h kinds; since-10-01 count). H-TINY on the full trip history, not the window.
- **CODE:** `_RECALL_KINDS` read on origin/main and inside `sooppiy-worker` (`('outcome','lesson') ('monitoring',)`); watcher fills at the scan
  mark (`risk_engine.py:852`, B); ratchet floor = fee + 0.5·(peak − fee) (`run_engine.py:1559`, B).
- **ADVERSARY:** "a green KST day" — rejected (−0.03 without one carried-in TP). "Tiny entries are the leak" — killed by history. "Stop the chair
  holding closes" — rejected for now: 11-17's n = 32 says the opposite. "R37 worsening" — refuted. "The L-1118 lesson is being tested" — refuted;
  it was never shown to the desk.
- **A vs B disagreement:** A's exit-author table (lock +4.03) vs B's (ratchet+trail +3.10) — basis only (close-leg vs trip-net with open fees,
  Δ 0.93 = the 60 trips' open fees); both totals reconcile. Substantive convergence: A's "held through own invalidation" (n = 4, ≈ −1.09 optimistic)
  and B's "final verb hold while params said close" (n = 5, +0.63) are the **same mechanism — the chair amending a trader's close to hold** (E1).

### 5. Re-verification ledger (items raised/shipped since the 11-18 sweep)

| item | evidence on prod (15:13–16:10Z) | verdict |
|---|---|---|
| sweep-20261118 deploy (f8a015c) | `.env` + worker + backend on `20261118-sweep-20261118`, up 21 h; deploy-log 20261118-181633 | **HELD** |
| L-1118 lesson "delivered via RAG" | in `desk_memory`, never retrieved (0 / 656 chunks; 0 / 15,601 since 10-01) | **FAILED** — channel dead by design (E5) |
| R42 / H-CUT 7-day falsifier | treatment never applied; observation day 1 n = 2 Σ −0.14 | **VOID** as an experiment; H-CUT observation continues |
| llm_silence alert | 100 `Request timed out` 21–22Z 11-18, decisions kept flowing (10–17/h), no_verdict 5 / 24 h → correctly silent (`silent:false`) | HELD |
| pnl_audit orphan / all_in | EXIT 0, orphan 0, all days | HELD |
| R31 `_mute_cycles` | 80 stops: trailing_lock 60, no_prospect_switched 19, conviction_collapse 1, **0 idle_retired** | HELD |
| R32 ratchet arm | day 5 calibrated: for (+0.71 k=3) | OPEN — 4 for / 1 against, 5/10 days |
| R34 size vs confidence | corr(conf, notional) −0.09 again | OPEN (premise holds: size ignores conf; P&L inconclusive) |
| R35 chair re-entry against own invalidation | 0 / 41 re-entries; in-trade variant found (E1) | OPEN, no strict instance |
| R37 step-through | $0.022/fire, 1.26/day | STAGED, **"worsening" refuted** |
| R39 entitlement retry loop | fleet 43: 2,176 `candidate_skipped` (100 % "no active subscription"), 1,119 `backtest_gate`, 112 `swing_gate`; 0 runs | OPEN, unchanged |
| R40 1-ADD hazard | 0 executed adds; **10 blocked** by add_limit (5 max_adds=0, 4 underwater, 1 cooldown) | OPEN — rail contains it |
| R41 | n = 0 effective | STAGED, inconclusive |
| O-1116 user 25 subscription | pro row 21 `expired` 2026-11-17T21:52:06Z; still denied | owner item |
| daily-sweep cadence | fired on time (15:13Z) | HELD today |

### 6. Health

| check | value |
|---|---|
| containers | worker/backend `20261118-sweep-20261118` up 21 h; admin up; mysql healthy |
| `MAX(run_events.ts)` | 15:12:55Z at 15:13:14Z |
| worker / backend Traceback · ModuleNotFoundError | 0 · 0 / 0 · 0 |
| worker ERROR | 3 — yfinance `VVV-USD: possibly delisted` 08:00Z (data feed, benign) |
| LLM | 100 timeouts 21–22Z 11-18 (local host); no_verdict 5, verdict_salvaged 28; desk decisions 373 / 24 h, 5–23 per hour |
| fleets | 44: 78 rotations, `replenishing` 5/8, 11 `slot_waiting`; 18/85 runs zero-fill took 15.5 % of desk decisions; 43: denied loop (R39) |
| prod image vs origin/main | equal in code |
| worker `/tmp` | `sooppiy-worker.lock` only (A and B verified) |

### 7. Today's solution

The losing shape: **the AI shorted a rising tape 70/70 times (4 h hit 32 %), and on the trades that went wrong the chair overrode the trader's
own "close now" — INJ, HYPE, LTC lost −2.13 between them.** The platform's exits (+2.80) carried the day; the desk-level exits lost −1.69.

1. **Fix the lesson channel before writing another lesson (process fix, shipped as docs today).** HANDOFF §10 now states that monitoring notes
   are a recall *fallback* only; an AI-first lesson must be a skill or a prompt line. L-1118 is withdrawn as "delivered". The scheduled-task prompt
   still says notes reach the RAG via `/app/docs/reports/` — that sentence is false for decision recall (owner/next session to correct the task
   file; this run does not edit it).
2. **R43 (STAGED) — "the chair may not hold a position past the desk's own printed invalidation when the trader proposes to close it."**
   AI-first form: one skill line for the chair ("if your invalidation has printed and the trader proposes to close, close; holding a position
   your own thesis says is broken is not risk control"). *Hypothesis:* the chair's close→hold amendments after a printed invalidation lose money.
   *Measurement owed before any ship:* every chair close→hold amendment since 10-01, split by whether price had crossed the desk's printed
   invalidation, counterfactual close-at-decision-mark vs actual. *Falsifier:* Σ ≤ 0 on the invalidation-crossed subset, or sign flips ex-largest,
   or n < 15. *Counterfactual at live marks today:* +0.63 (n = 5), +0.17 ex-INJ — too small and too single-tape to ship. It must also reconcile
   with 11-17 E1 (n = 32, −4.83 the other way): the split by "invalidation printed" is the hypothesis that would make both readings true.
3. **R42 is re-scoped, not promoted:** H-CUT stays an observation. If R43's measurement holds, R42 and R43 are the same skill line (reduce/close
   only on printed invalidation, a changed thesis, or profit) — one prune, one ship.
4. Direction: no fix proposed — the 1 h edge did not replicate, and "stop shorting" on one rising day would be the same curve-fit H-TINY just died
   of. Watch: 4 h hit-rate per day; trigger = a 3rd consecutive day below 40 %.

### 8. Killed / corrected

- **H-TINY** ("tiny entries are the day's leak") — killed by the since-10-01 history (least loss per trip; positive in November).
- **H-1H-EDGE** (11-18's +0.22 % at 1 h) — not replicated (43 % hit, sign flips ex-largest).
- **"R37 is worsening"** (11-18) — refuted ($0.022/fire, stable over 5 readings).
- **"L-1118 reached the desk"** (11-18 §7) — killed; corrected here and in HANDOFF §10. This affects every past "lesson via the note" claim.
- **H-CONF-SIZE** — killed again (corr −0.09).

### 9. Not verified

- R43's historical split (the measurement that would promote or kill it) — not run; it needs invalidation text parsing over ~7 weeks.
- A's invalidation counterfactual (≈ −1.09) uses 5 m candle highs with no slippage — optimistic.
- Direction hit-rates use Hyperliquid candles (Binance 451 from prod).
- STRK 230419 (open at 15:14Z) closed after the window; its result is not in these figures.
- The notional < $27.5 proxy for sf ≤ 0.07 is exact for today (A: same 33 trips) but assumed for the history.
- Whether any *outcome* chunk carried an equivalent of L-1118 — not checked.

### 10. Deploy record

`scripts/deploy.sh sweep-20261119` from the scratch clone at 937234e, rc 0 → **`sooppiy-backend:20261119-sweep-20261119`**.
Rollback: `SOOPPIY_IMAGE=sooppiy-backend:20261118-sweep-20261118`. Reason (mode ②): new finding + retraction (E5 — notes never recalled;
L-1118 withdrawn), R43 staged, R37 verdict moved. Docs-only; no code change.

| prod check | pass 1 (15:31:02Z) | pass 2 (15:32:20Z) |
|---|---|---|
| `.env` + worker + backend image | 20261119-sweep-20261119 ×3 | same |
| today's note in `/app/docs/reports/`; HANDOFF trap present | present / 1 hit | present / 1 hit |
| tracebacks worker / backend (10 min) | 0 / 0 | 0 / 0 |
| `MAX(run_events.ts)` vs clock | 15:30:58Z at 15:31:04Z | 15:30:58Z at 15:32:22Z |
| worker `/tmp` | lock only | lock only |
| public pages + `/api/subscriptions/plans` | 200 ×5 (deploy.sh) | — |
