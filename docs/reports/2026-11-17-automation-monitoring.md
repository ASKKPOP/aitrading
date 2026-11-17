# Automation monitoring — 2026-11-17 (UTC day) — daily 24h sweep

Newest-first. Authority for rules/access/traps: `HANDOFF-automation-monitoring.md`.

## 24h sweep — 2026-11-17T15:13:07Z (KST day 2026-11-17 = 11-16T15:00Z → 11-17T15:00Z, just closed)

Prod clock `SELECT UTC_TIMESTAMP()` = 2026-11-17 15:13:07. Fired on schedule (15:07Z) — no coverage gap since the 11-16 sweep.
Image on `.env`, worker and backend = `sooppiy-backend:20261116-sweep-20261116` (495f5a5); origin/main had only docs commits
after it → **no code drift**. Trading set re-derived = {6, 60} (fleets 44, 43 active); only agent 6 cycled.

### 1. P&L — dollars first
| window | agent 6 (info) | agent 60 (forevery1969) | combined | fills | fees |
|---|---|---|---|---|---|
| 24 h (11-16T15:13Z → 11-17T15:13Z) realized | **−5.17** | 0.00 (0 fills) | **−5.17** | 94 (50 closes) | 1.43 |
| 24 h without largest loser (TRUMP 217302 −2.74) | −2.43 | — | −2.43 | | |
| KST 11-17 (11-16T15Z → 11-17T15Z) | **−5.20** | 0.00 | −5.20 | 92 | 1.39 |
| pnl_audit all_in UTC 11-16 / 11-17 (to 15:13Z) | +0.17 / **−5.34** (`ok`, EXIT 0) | 0 | | | |
| open uPNL (ETH 215281 short 0.0209 @1793.1, mark 1803.7) | −0.22 | — | −0.22 | | |

Routes agree: pnl_audit UTC 11-17 −5.34 = SQL Σ close pnl − entry fees −5.343; cash 9,858.48 (11-16 sweep) + 33.53 margin released
− 5.155 realized since sweep − 37.52 ETH margin = 9,849.335 vs live 9,849.338.
Four runs carry −6.02 (TRUMP 217302 −2.74, LINK 215403 −1.18, SOL 215280 −1.18, AVAX 215524 −0.91); the other ~40 trips +0.85.

- Fees 1.43 on −5.17: **fees are not the loss today** (gross before fees ≈ −3.74). The loss is four held shorts against a rally.
- **Payoff:** 43 closed trips, 28 W +1.17 / 15 L −6.32 → avg loss 10× avg win. Without the worst 4 runs +0.53. Ratchet trips (n = 36)
  net **+0.93** (+0.78 without ZEC). The four losers (−6.03) erased the ratchet's +0.93 ≈ 6.5×.
- **Verdict:** a −$5.17 day on n = 43 trips, decided by n = 4 runs. Stripping TRUMP leaves −2.43: the sign holds; the loss is not one
  outlier. Agent 60: $0 (still entitlement-denied; O-1116 unchanged).

### 2. Per-trade reasons (Agent A = AI-authored, Agent B = algorithm-authored; cross-checked)

**Authorship:** the AI authored 44/44 entries — **all shorts again** — every one via the light route (`rule_route=full`, the AI router
downgraded all 53 entry decisions). The desk was 84–85 % mute until ~21Z 11-16, then 0–7 % (23 % 03–06Z); every entry followed recovery.
Losses closed through desk paths: `cyc:` 7 closes −2.31, desk-armed `arm:` 4 closes −2.08, SL watcher 2 closes −1.30, adapt-retire 1 −0.19;
ratchet 36 closes +1.44 gross-of-entry-fee.

| run | sym | $ | conf / size_frac | entry author | held | net $ | reason (A + B) |
|---|---|---|---|---|---|---|---|
| 217302 | TRUMP | **187.45** | **0.55 / 0.50** | trader sell, chair | 8h29m | **−2.74** | 5–10× the day's normal size at the floor confidence on a self-contradictory thesis ("downtrend + contrarian extreme fear"); +1 h −1.49 % against; desk moved its invalidation 0.981 → 1.05 (beyond its own stop) and called the move "noise" for 8 h; its two partial covers (−1.21, −0.08) saved ≈ 2.8 vs holding all to the stop; its armed reduce sat AT the stop (no value); stop 0.98065 filled 0.98417 (0.36 % slip, ≈ 0.17); ratchet blind on the remainder (R41) |
| 215403 | LINK | 75.09 | 0.60 / 0.20 | trader sell .55 → chair .60 | 10h58m | −1.18 | adverse from entry (+4 h −1.50 %); peak 0.088 < arm 0.12 (ratchet correctly unarmed); desk's "cut by half" orders sent as `sell` on a short → blocked `add_limit` ×2 (R40); desk-armed close beat the stop by ≈ 0.22 |
| 215280 | SOL | 45.42 | 0.66 / 0.10 | **chair flip** buy → sell | 4h50m | −1.18 | never positive (max uPNL 0.000); chair overrode a trader cover at −0.13 (blocked as add); armed reduce + stop (0.18 % slip); stop avoided more loss (HL high 73.61) |
| 215524 | AVAX | 34.75 ×2 | 0.58 → 0.55 | trader sell; trip 2 chair flip | 9h01m + 1h57m | −0.91 | trip 1: closed by a **truncated-salvaged verdict** (panel "json unparseable", conviction null) at −0.57 after the chair held through 4 trader cover proposals; trip 2 re-shorted 89 min after the same thesis lost; adapt-retire flattened 2.41 u at 7.2757 (counted a synthetic off_track loss) — AVAX then fell to 7.15, ≈ 0.30 cost (n = 1) |
| 169927 | AAVE | 16.1 | — | desk (11-16, R38 entry) | 53 min | −0.14 | the R38 entry (opened 62 min before at_time, 72 h horizon) closed by the desk at a loss before at_time |
| 36 runs | various | 16–75 | 0.55–0.68 / 0.05–0.2 | desk | 2–519 min | **+0.93** | first-hour move banked by the ratchet; 9 negative (Σ −0.165) on step-through |
| 215281 | ETH (open) | 37.5 | 0.68 / 0.10 | trader sell | — | +0.08 realized / −0.10…−0.22 open | desk reduce timed well; re-short +1 h −1.22 % |

- **Direction (A):** +1 h right 21/37 (57 %), **+4 h right 4/23 (17 %, mean −0.77 %)**. The +4 h sample is survivorship-biased and one
  correlated bet (effective n small). The desk's 12–48 h downtrend thesis was wrong; the ratchet's sub-hour exits are why most trips won.
  Seventh reading consistent with "entries carry no proven edge".
- **Size vs confidence (A):** corr(conf, notional) −0.06 (n = 44), +0.09 without TRUMP. The largest entry was at conf 0.55 → **R34 n = 5,
  Σ −4.46** (still below its n ≥ 10 / 7-day bar; 5 inside 11-11…11-17). Counterfactual cap 0.1 on TRUMP: −0.55 instead of −2.74 (+2.19).
- **Ratchet step-through (B, R37):** n = 36, Σ(floor − fill gross) = **0.70**, every fire at or below its floor; sampling ≈ 62 s (gaps
  190–220 s). **Third independent reading** (11-11: 9 negative; 11-13/14: 0.706; today 0.70).
- **Fences (B):** null_size_refused 10, add_limit 12 (8 underwater, 2 max_adds = 0, 2 cooldown), loss cooldown 22, stop_cap 1, target_cap 2,
  stopped-run fence 1, re-entry fence 0, orphan/handoff 0 (pnl_audit orphan 0 is correct). TRUMP's two 24.49 covers 29 s apart are
  **not a duplicate** (arm + watcher on the same mark; quantities sum exactly).
- **LINK 215403** still `running` flat, cycling every ~30 min (paid desk calls on no position) until at_time 11-18T00:40Z.

### 3. Experiments run on the agents' headline claims (hypothesis → falsifier → result)

**E1 — Agent A's headline "the chair fights the trader's exits, so losers are held; fix the chair" — KILLED as a general claim.**
Falsifier: across all agent-6 history since 10-01, covering at the trader's proposed `buy` (while short) instead of the chair's `sell`
would NOT have made money. Measure: every `order_discussion` proposed buy → final sell on a held short; P&L of covering at the decision
mark vs the actual later covers. **n = 32, Σ = −4.83** (covering at the trader's call would have LOST 4.83); without the largest (−3.57)
−1.26. Today alone +1.25 (4/7) — today's shape is real, the general rule is not. No chair-hold fix is justified.

**E2 — "the desk's stated reduce is mis-sent as an add on a short" (R40) — DEFECT CONFIRMED, FIX KILLED ON P&L.** CODE: the chair prompt
in `_three_agent_light_discussion` gives `position N units (negative = short)` and `Allowed actions: buy|hold|sell` but **not** the
trader's inventory rule ("'sell' opens or extends a short; 'buy' covers"). DATA (since 10-01): **n = 30** `order_params` with action
`sell` on a held short whose own `why` says close / reduce / cut (e.g. LINK 05:55 "Cut exposure by half to limit loss"); 22 died at
`add_limit`, **1 executed as an ADD** (11-05 run 123737). Counterfactual at the live marks of executing the stated reduce: **n = 26,
Σ −2.70** (−0.92 without the largest; Oct −1.41, Nov −1.30 — both halves negative). The order did not do what the AI said, but the
mis-send has been P&L-positive. Not shipped: a fix that would have lost $2.70 is not a solution (profit is the target). Staged with the
1-ADD hazard named.

**E3 — R32 ratchet arm (daily replay, `research/ratchet_arm_replay.py 2026-11-16T15:00:00Z 2026-11-17T15:13:00Z 6`, 1m, n = 36, 0 skipped).**

| k | 1 | 2 | 3 | 5 | 10 | none |
|---|---|---|---|---|---|---|
| sim Σ (actual +0.93) | 0.80 | 0.80 | −3.03 | −3.82 | −6.96 | −6.38 |
| Δ vs actual | −0.13 | −0.13 | −3.96 | −4.75 | −7.88 | −7.31 |
| Δ ex-largest | −0.21 | +0.80 | −1.93 | −2.71 | −5.85 | −5.27 |

Calibration k = 1: median |sim − actual| **0.006 (passes ≤ 0.01)**, max 0.076. A rallying tape against the shorts: **every raise of the arm
loses**. R32 tally: **3 calibrated days — 2 for (trending), 1 against (reversal)**. The ratchet's first-hour banking is what kept today
from being −12. R32 stays STAGED and moves toward kill, not promotion.

**E4 — Agent B's "ratchet is blind after a losing partial" (R41) — CODE CONFIRMED, DATA n = 1.** `_ratchet_peak_pnl` advances
`peak_pnl_usd` only when the run TOTAL exceeds it while holding, and re-anchors only when flat. TRUMP: peak stamped near −0.08 at open;
after the desk's losing covers the total was −1.38 + uPNL; at 10:58Z the remaining 48.98 u showed +0.37 uPNL (equity events) — a
position excursion above its ≈ 0.30 arm that the ratchet could not see (total −1.01 < peak −0.08). Counterfactual ≈ +1.5 on n = 1.
R21 (run 1417) shows the opposite failure from the opposite fix, so this needs a replay across every run with a losing partial before any code.

### 4. Three-axis verification

- **DATA:** 24 h P&L by 4 routes (pnl_audit −5.34 UTC; SQL −5.343; cash reconciliation exact to 0.003; Agents A and B per-trip −5.15/−5.17,
  differing only by the open ETH entry fee). Mute by 2 routes (A census 84–85 % → 0–7 %; `llm_silence.measure` 3-h buckets 100 % → 2–7 %,
  24 h 23 %; state `silent:false`). add_limit blocks re-read by my own query (12 in window, 5 on the losers).
- **CODE:** chair prompt lacks the inventory rule (origin/main `run_engine.py` `_three_agent_light_discussion`); `_reducing_now` knows the
  sign but runs for the panel, not the chair; `_ratchet_peak_pnl` / breakeven baseline `peak_realized_usd` read on origin/main; live
  worker has `run_engine._ratchet_peak_pnl`.
- **ADVERSARY:** "the day was bad luck on a reversal" — rejected: the TRUMP entry was a sizing choice (0.5 at conf 0.55) that no tape excuses,
  and +4 h direction was 4/23. "Fix the chair override" — killed by E1. "Fix the verb mapping" — killed on P&L by E2. "Raise the ratchet" —
  killed today by E3.
- **A vs B disagreement (the finding):** A blames the chair for holding losers; B shows the losses were realized through the desk's own
  reduces and stops, with the ratchet unable to rescue the TRUMP remainder. E1 says A's mechanism is not a money rule over 6 weeks; B's
  R41 is a mechanism with n = 1. Both point at the same root: **one oversized, low-confidence entry decided the day** (R34).

### 5. Re-verification ledger (since the 11-16 sweep)

| item | evidence on prod | verdict |
|---|---|---|
| sweep-20261116 deploy (495f5a5) | `.env` + worker + backend on `20261116-sweep-20261116`, up 17 h; deploy-log row present | **HELD** |
| 3ea8010 llm_silence recovery | desk answered from ~21Z; state `silent:false, alerted_at:null`; 0 `Request timed out` in 24 h (1,904 the day before) | **HELD** (recovery notice delivery not separately checked) |
| c77f810 deps CVE bump | same image lineage, no rebuild | HELD |
| pnl_audit orphan / all_in | EXIT 0; orphan 0, confirmed by B (no run_id-NULL fills) | HELD |
| R31 `_mute_cycles` | 0 zero-verdict idle retires | HELD |
| R32 ratchet arm | day 4 calibrated: **against** | OPEN — 2 for / 1 against; trending-only support |
| R34 size at low confidence | TRUMP 0.50 @ 0.55 −2.74 → n 5, Σ −4.46 | OPEN, strengthened (bar n ≥ 10 / 7 d) |
| R35 chair re-entry against own invalidation | AVAX trip 2 re-short 89 min after the thesis lost (not strict class (c)) −0.33 | OPEN |
| R37 step-through | Σ 0.70 on 36 (3rd reading) | STAGED, now 3 readings — still needs the 15 s replay (design) |
| R38 short-life entry | AAVE 169927 closed −0.14 | SOFT, n = 1 (loss) |
| R39 entitlement retry loop | candidate_skipped 12,799 (11-16), 8,208 (11-17 to 15:16Z) | OPEN, unchanged |
| O-1116 user 25 subscription | still denied 15:13Z | owner item, unchanged |
| Daily-sweep cadence | fired 15:07Z on schedule | HELD today |

### 6. Today's solution (AI-first; nothing ships — reasons stated)

The day's loss is **−5.17, of which −2.74 is one entry sized 0.50 at confidence 0.55**. In P&L order:

1. **R34 — size must follow confidence (AI-first, desk sizing skill line; STAGED, strongest it has been).** Lesson text: "Your size_frac
   above 0.10 requires confidence ≥ 0.70; at the 0.55 floor the size is 0.05–0.10." *Counterfactual at live marks:* +2.19 today
   (TRUMP capped at 0.1); 11-11 +1.37; 11-13 169219 −0.31 (it was a winner) → Σ ≈ +3.2 over 5 entries, positive without the largest
   (+1.0). *Falsifier:* over 7 days the ≥ 0.3 entries net ≥ the 0.05–0.1 entries per $ notional. *Metric:* Σ P&L of entries with
   size_frac ≥ 0.3 and conf < 0.7. Not shipped: n = 5 < 10 bar, the catalogue is at capacity (needs a prune) and the sizing prompt is a
   money path that needs the two-reviewer gate. Promotion trigger unchanged (n ≥ 10 in 7 days, counterfactual positive with and without
   the largest).
2. **R41 — ratchet blind after a losing partial (platform; STAGED, n = 1).** Measure first: every run since 10-01 with a losing partial
   cover whose remainder's own excursion later exceeded the arm. *Falsifier:* Σ counterfactual (position-anchored peak) < 0 or n < 5.
3. **R40 — chair verb semantics on a short (STAGED, do-not-ship on P&L).** Watch the 1-ADD hazard (a stated reduce executed as an add):
   any further instance → promote the chair inventory line regardless of E2, because adding against the desk's own words is a risk event,
   not a P&L bet.
4. **R37** stays STAGED (3 readings, 0.70/day); needs a 15 s replay design before code.

### 7. Killed / corrected

- **"The chair holding losers against the trader's cover is a money defect"** — killed (E1: n = 32, Σ −4.83 for covering).
- **"Fixing the sell-on-short verb mapping recovers money"** — killed (E2: n = 26, Σ −2.70).
- **"Raising the ratchet arm (R32) is supported"** — today's calibrated replay says every raise loses (−3.96 at k = 3).
- **"The TRUMP double cover is a duplicate fill"** — killed (B: arm + watcher, quantities sum exactly).
- **"No scale-out rail exists / max_loss cut the losers"** — confirmed none exists; every partial was a desk `reduce 0.5` intent.

### 8. Health

| check | value |
|---|---|
| containers | worker/backend `20261116-sweep-20261116` up 17 h; admin up; mysql healthy |
| `MAX(run_events.ts)` | 15:12:26Z at 15:13:07Z |
| tracebacks / ModuleNotFoundError / ERROR (24 h) | worker 0 / 0 / 9 (yfinance "possibly delisted" HYPE-USD, BRK.B); backend 0 / 0 / 0 |
| LLM | 0 timeouts in 24 h; mute 100 % → 2–7 % after ~21Z 11-16 |
| `/api/health` | 200 |
| fleets | 44: 56 runs / 56 rotations, `replenishing:6/8`, 8 `slot_waiting no_candidates`; 43: subscription-denied loop |
| prod image vs origin/main | equal (code) |

### 9. Not verified

- Whether the llm_silence recovery notice was delivered (state reset seen; the notification row was not read).
- Post-close prices for B's counterfactuals are Hyperliquid 5m candles (Binance HTTP 451 from prod).
- E1/E2 use the run's own later cover VWAP as the counterfactual exit, not a fixed horizon.
- The +4 h direction sample (n = 23) is survivorship-biased.
- Agent A wrote a 16 KB scratch file `/tmp/agA.json` inside `sooppiy-worker`; **deleted by me** (15:2xZ), verified absent.
