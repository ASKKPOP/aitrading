# Automation monitoring — 2026-11-18 (UTC day) — daily 24h sweep

Newest-first. Authority for rules/access/traps: `HANDOFF-automation-monitoring.md`.

## 24h sweep — 2026-11-18T18:02:21Z (KST day 2026-11-18 = 11-17T15:00Z → 11-18T15:00Z, closed)

Prod clock `SELECT UTC_TIMESTAMP()` = 2026-11-18 18:02:21. **Fired ≈ 2h55m late** (schedule 15:07Z; desktop app/network — the first
clone and SSH attempts were reset by peer at ~18:00Z, then recovered). Image on `.env`, worker, backend = `sooppiy-backend:20261117-sweep-20261117`
(5a28171); origin/main = 7339a2c (docs-only after it) → **no code drift**. Trading set re-derived = {6, 60} (fleet 44 agent 6, fleet 43
agent 60, both `active`); only agent 6 cycled (84 runs).

### 1. P&L — dollars first

| window | agent 6 (info) | agent 60 (forevery1969) | combined | fills / closes | fees |
|---|---|---|---|---|---|
| **KST 11-18** (11-17T15Z → 11-18T15Z) net | **+2.48** | 0.00 (0 fills) | **+2.48** | 129 / 67 | 2.34 |
| KST 11-18 without largest (ASTER 227445 +1.04) | +1.45 | — | +1.45 | | |
| **24 h** (11-17T18:02Z → 11-18T18:03Z) net | **+3.45** | 0.00 | **+3.45** | 137 / 68 | 2.59 |
| 24 h without largest (ASTER +1.04) | +2.41 | — | +2.41 | | |
| pnl_audit all_in UTC 11-17 / 11-18 (to 18:03Z) | −5.58 / **+4.01** (`ok`, EXIT 0, orphan 0) | 0 | | | |
| open uPNL 18:07Z (FIL, STRK, HYPE, BNB shorts, ≈$75) | +0.22 (−0.10 without STRK → inconclusive) | — | +0.22 | | |

- **Routes agree (3):** pnl_audit UTC 11-18 +4.01 = signals Σ close pnl − entry fees +4.009; UTC 11-17 −5.58 = −5.576. Cash reconciliation:
  9,849.338 (11-17 sweep) + 37.52 ETH margin released + R − 75.01 open margin = 9,815.626 live → R = **+3.78** vs signals since 11-17T15:13:07Z
  **+3.776**. Agents A and B per-trip rebuild +3.77 / +3.772 over the full window 11-17T15Z → 11-18T18:03Z (n = 73 trips).
- **KST day shape:** 62 runs, 46 W +4.46 / 16 L −1.98, win rate 74 %, avg win 0.097 vs avg loss 0.124 → **payoff 0.78**. Largest winner ASTER
  +1.04, largest loser FIL 226601 −0.94 *inside the KST day* (the same run closed +1.01 at TP after 15:00Z → trip +0.07).
- **Verdict:** a profitable day (+2.48 KST, +3.45 24 h) on n = 62–65 trips, sign holds without the largest contributor. It does **not** repair
  the week: since 11-16 pnl_audit TOTAL **−1.40**. Agent 60: $0 for the 7th day (subscription denied; R39 loop still burning, §5).

### 2. Per-trade reasons (Agent A = AI-authored, Agent B = algorithm-authored; cross-checked)

**Authorship:** the AI authored all 74 entries (all shorts, no longs). Exits: breakeven ratchet 67 (+3.50 net, +2.46 ex-ASTER) + legacy trail 1
(FIL 224348 +0.63) + watcher TP 1 (+1.00) + watcher SL 2 (−0.90) = **algorithm +4.23**; desk `cyc:` exits 5 = **AI −0.37…−0.46**. The profit was
banked by the platform's exits; the AI's own exits lost money. max_loss / at_time / retire-with-position fired 0×.

| run | sym | $ notional | conf / size_frac | hold | net $ | reason (A + B, evidence) |
|---|---|---|---|---|---|---|
| 227445 | ASTER | 187.5 | 0.55 / 0.50 | 15 m | **+1.04** | short into a falling tape; ratchet banked +0.64 % at 10:16Z. Risk agent cut conf .60 → .55, size stayed 0.50 |
| 228216 | WLD | 228.2 | 0.62 / 0.50 | 32 m | +0.70 | same pattern; ratchet exit +0.39 % |
| 228213 | LINK | 161.0 | 0.60 / 0.50 | 43 m | +0.39 | ratchet exit +0.33 % |
| 224348 | FIL | 32.3 | — | — | +0.63 | legacy trail lock (peak 0.758 ≥ activate 0.64, lock 0.644, fill 0.661) |
| **226601** | **FIL** | 150.0 | 0.55 / 0.40 | 10.9 h | **+0.07** | **the desk's own cuts destroyed this trade:** 05:33Z (16 min in, price +0.75 % against, stop 2.5 % away) cover 126 u −0.60 "cut exposure by half… short-squeeze"; 08:49Z cover 63 u −0.35 "reduce half" (+0.9 % against). MAE 1.47 % never threatened the stop; price ran to TP (watcher TP 16:12Z +1.01 on the last 42 u). Holding all 252 u to TP ≈ +5.9 net (my fill read); by the pre-registered H-CUT method (each cut vs the trip's later exits) +2.76 |
| 224010 | SOL | 18.7 | 0.58 / 0.05 | 4.2 h | **−0.55** | wrong-way entry on a rising tape (MFE 0.11 %); SL 74.1495 filled 74.408 (gap between 62 s marks, $0.067 slip); desk `no_verdict` 20:42Z + 21:42Z while underwater (LLM host outage, §6). Price 4 h after stop 74.72 → stop was right |
| 226583 | LIT | 24.3 | 0.55 / 0.07 | 55 m | −0.35 | re-short 1 h after banking +0.39 on the same run; reanchored stop only 0.80 % away; gapped through (fill 2.8613 vs stop 2.8461, $0.131 = 38 % of the loss). Price 4 h later 2.81 → thesis right, timing/stop width wrong |
| 226533 | LIT | 45.4 | 0.55 / 0.10 | 5 m | −0.20 | ratchet peak +0.078 (arm 0.073, floor 0.060); next 62 s sample −0.155 → fired 0.215 below its floor (step-through, R37) |
| 62 others | various | ≈ 25 | 0.05–0.12 | median 17 m | +2.53 | 48 W / 14 L (losses Σ −0.26); first-hour move banked by the ratchet |

- **Direction (A), first window that contradicts "entries carry no edge":** +1 h right 45/69 (65 %, mean +0.28 %), +4 h 37/59 (63 %, +0.36 %);
  unconditional short drift of the traded coins +0.06 % (1 h) / +0.18 % (4 h) → entries beat drift by **+0.22 % at 1 h** (45/69). One bearish
  regime, correlated entries, one day → **inconclusive, needs replication**; it is not a proven edge.
- **Capture:** holding every entry 1 h would have moved +9.42 gross (+7.44 ex-largest); realized +3.77 → exits kept ≈ 40–50 %.
- **Confidence carries no outcome information today (A):** corr(conf, notional) −0.14 (n = 74); conf ≥ 0.65 net +0.24 (1 h hit 9/16); conf < 0.6
  net +1.40 (21/33). Chair flips (trader buy → chair short) n = 18: 14/18 right at 1 h, net +1.34.
- **Tiny entries (A):** 37 entries at size_frac ≤ 0.07 (≈ $18) netted **−0.54** — fees + stops exceed the move at that size. SOFT, n = 37, one day.
- **R40 hazard (A):** 0 reduces executed as adds; 3 chair `sell`-as-reduce blocked by `add_limit` (226601 ×2, 227626) — the hazard is still live.
- **Fences (B):** gate_skip hold 217, null_size_refused 25, loss cooldown 14, conf below threshold 8, mark_drift 7, add_limit 7, stop re-entry 1,
  run-stopped 1; bracket_reanchor 75, stop_cap 1; 23 `no_prospect_switched` retires (22 zero-fill, 1 flat). 80 of 344 desk calls were spent on
  the 22 zero-fill runs (LLM $0, local — capacity, not dollars).

### 3. Experiments (hypothesis → falsifier → result)

**E1 — H-CUT: "the desk's partial covers of a position cost money versus holding the cut quantity to the trip's own later exits."**
Pre-registered falsifier: across every agent-6 desk (`cyc:`) partial cover since 10-01, Σ(hold − cut) ≤ 0, or the sign flips without the largest.
Method: per run, rebuild trips from `signals`; for each desk close that is not the trip's last close, benefit of holding =
sign × (VWAP of the trip's later closes − cut price) × cut qty. **First pass was wrong and is retracted:** trips were closed on `|pos| < 1e-9`,
but fill quantities carry ~2e-8 rounding residue, so trips with partials never closed (FIL 226601, TRUMP 217302 missing; n = 19). Fixed with a
relative tolerance (1e-5 × trip quantity) → n = 47 (trap added to HANDOFF §10).

| desk partials since 10-01 | n | Σ(hold − cut) | hold better | without largest | Oct / Nov |
|---|---|---|---|---|---|
| all | 47 | **+4.85** | 23/47 | **+3.40** | +3.72 / +1.13 |
| underwater at the cut | 33 | **+3.03** | 18/33 | +1.58 | +2.20 / +0.83 |
| in profit at the cut | 14 | +1.82 | 5/14 | +0.45 | +1.52 / +0.30 |

**Survives the falsifier** (positive without the largest, both halves positive). Caveats stated plainly: by COUNT it is a coin flip (49 %); the
edge is magnitude — cuts that were followed by a TP lose big (FIL 226601 +2.76, 31807 +2.77), cuts followed by a stop save (TRUMP 217302
−1.52, 112429 −1.21). Second independent reading in the same direction: 11-17 E2 — the desk's *blocked* reduce orders, if executed, would
have lost **2.70** (n = 26). Two readings, two mechanisms, same sign: **the desk's discretionary reduces have destroyed money (≈ +7.5 combined
counterfactual over 7 weeks, ≈ $0.15/day).** Size of the prize is small; the shape is consistent.

**E2 — R32 ratchet arm, daily calibrated 1m replay** (`research/ratchet_arm_replay.py 2026-11-17T15:00:00Z 2026-11-18T18:03:00Z 6`, n = 63,
4 skipped). Calibration k = 1: median |sim − actual| **0.0053 (passes ≤ 0.01)**, max 0.563.

| k | 1 | 2 | 3 | 5 | 10 | none |
|---|---|---|---|---|---|---|
| Δ vs actual (+3.13) | +0.35 | +3.96 | +5.69 | +9.29 | +30.50 | +33.97 |
| Δ ex-largest | +0.91 | +3.07 | +4.80 | +8.17 | +25.42 | +28.89 |

A falling tape under all-short entries: every raise of the arm wins (the mirror of 11-17). Calibrated-day tally at k = 3: 11-10 +4.06,
11-13/16 +2.29, 11-17 −3.96, 11-18 +5.69 → **ΣΔ +8.08, +2.39 without the largest day, 3/4 positive; 4 of the required 10 days; non-trending
days still 0 of ≥ 3.** Sign still follows the tape. R32 stays STAGED (the arm is an owner `.env` knob anyway).

**E3 — R41 "ratchet blind after a losing partial" (B): n = 1 today (FIL 226601) AGAINST.** A position-anchored ratchet would have armed at 12 h
and fired near +0.2 on 63 u; actual desk cover +0.076 + TP +1.008 = +1.084 → the blindness was worth **+0.86** here. Tally n = 2: +1.5 (TRUMP,
for) vs −0.86 (FIL, against) → inconclusive; R41 must not ship.

**E4 — R34 "size must follow confidence": refuted in this window.** n = 6 entries at size_frac ≥ 0.3 and conf < 0.7, all winners, Σ **+2.31**
(+1.27 ex-ASTER). Cumulative 7-day n = 11, Σ −2.15. Counterfactual cap 0.1: today ≈ −1.8 (gives up winners), prior +3.2 → net ≈ +1.4, **−0.8
without TRUMP → sign flips → inconclusive.** And confidence predicted nothing today (E above). R34 is not promoted; its premise weakened.

**E5 — R37 ratchet step-through, 4th reading:** Σ(floor − fill) **$1.90 over 67 fires** (median 0.014, max 0.215 LIT 226533; $1.69 ex-largest),
$0.028/fire vs $0.019 prior → **worse, not better**. Fill = fire-time mark in 67/67 → zero execution slippage; all of it is the 62 s mark
sampling. 6 fires landed below zero gross (Σ −0.447). It is now the largest single algorithmic leak (≈ 55 % of the ratchet's own +3.50).

### 4. Three-axis verification

- **DATA:** P&L by 4 routes (pnl_audit, signals SQL, cash reconciliation exact to 0.004, A/B per-trip rebuild). H-CUT re-run after finding my own
  tolerance bug; FIL 226601 fills read directly (252.19 u short @ 0.59481; covers 126.09 @ 0.59926, 63.05 @ 0.60014, 20.67 @ 0.59085, TP
  42.38 @ 0.57077 — quantities sum to 252.1856086, residue 2e-8). Mute measured by `llm_silence.measure` (not by events alone).
- **CODE:** running image `llm_silence.tick` → `admin_alerts.notify_admins`; worker log shows both events (below). Ratchet arm = fee-only
  (`RATCHET_ARM_TARGET_FRAC` default 0) per B, read in the running image.
- **ADVERSARY:** "the profitable day proves the desk improved" — rejected: the profit was the platform's exits (+4.23) on a falling tape the
  all-short book was aligned with; the AI's own exits lost; the week is still −1.40. "Cut less = always better" — rejected by count (23/47);
  the claim survives only as a magnitude rule and only as a *lesson*, not a rail. "R32 is now proven" — rejected: 4/10 days, 0 non-trending.
- **A vs B disagreement (the finding):** A says FIL 226601's damage was the desk's cuts; B says the ratchet's blindness on the remainder *helped*
  (+0.86). Both are right and they point the same way: **the remainder held to TP made the money; the cuts made the loss.** Chased into E1.

### 5. Re-verification ledger (items raised/shipped since the 11-17 sweep)

| item | evidence on prod (18:02–18:50Z) | verdict |
|---|---|---|
| sweep-20261117 deploy (5a28171) | `.env` + worker + backend on `20261117-sweep-20261117`, up 27 h; deploy-log row 20261117-152332 | **HELD** |
| 3ea8010 `llm_silence` alert + recovery | **first full live cycle observed**: desk mute from ≈ 20:23Z (160 `Request timed out` 20–22Z); measure 0.91 (22Z) / 1.00 (23Z) on n ≥ 10; `[LlmSilence] silent` sent email+sms **21:44:33Z** (≈ 80 min after onset; window 120 min); `recovered` sent **23:44:37Z**; state now `silent:false`. alert_log has no row (alert goes via admin channels, not alert_log) | **HELD** |
| pnl_audit orphan / all_in | EXIT 0, orphan 0 all three days | HELD |
| R31 `_mute_cycles` | runs stopped since 11-17T15Z: `stop_event:trailing_lock` 68, `no_prospect_switched` 23, **0 `idle_retired`** — including across the 20–23Z mute | HELD |
| R32 ratchet arm | day 4 calibrated: **for** (+5.69 at k=3) | OPEN — 3 for / 1 against, 4/10 days |
| R34 size at low confidence | 6 more entries, all won (+2.31); cumulative 11, −2.15; counterfactual sign flips ex-largest | OPEN, **weakened** |
| R35 chair re-entry against own invalidation | LIT 226583 re-short 1 h after a win −0.35 (not against its own invalidation — not strict class) | OPEN, no strict instance |
| R37 step-through | 4th reading $1.90 / 67 fires (worse) | STAGED, **strengthened** |
| R38 short-life entry | no new instance | SOFT |
| R39 entitlement retry loop | fleet 43: **4,616 `candidate_skipped`** + 304 `backtest_gate` in 24 h (B: 5,240 over its longer window, "no active subscription allows auto-trading runs"); 0 runs created; `replenishing:0/8` | OPEN, unchanged (lower than 8–12k/day) |
| R40 1-ADD hazard | 0 executed adds; 3 blocked sell-as-reduce | OPEN, watch |
| R41 ratchet blind after losing partial | n = 2: +1.5 / −0.86 | STAGED → inconclusive |
| O-1116 user 25 subscription | still denied | owner item, unchanged |
| Daily-sweep cadence | fired ≈ 2h55m late (18:02Z) | **FAILED today** (coverage gap 15:07Z → 18:02Z; nothing missed in data — windows overlap) |

### 6. Health

| check | value |
|---|---|
| containers | worker/backend `20261117-sweep-20261117` up 27 h; admin up; mysql healthy |
| `MAX(run_events.ts)` | 18:02:21Z at 18:02:21Z |
| tracebacks / ModuleNotFoundError / ERROR (24 h) | worker 0 / 0 / 0; backend 0 / 0 / 0 |
| LLM | 160 timeouts, all 20:00–22:59Z 11-17 (local host 100.121.33.7); 24 h mute 6.5 % (20/310); no_verdict 4, verdict_salvaged 15 |
| desk decisions / h (agent 6) | 3–24 (low 20Z = outage), 312 decisions / 24 h |
| fleets | 44: 81 rotations, `replenishing` 2/8 → 7/8, 13 `slot_waiting`; 43: subscription-denied loop (R39) |
| prod image vs origin/main | equal in code (origin/main ahead by one docs commit) |

### 7. Today's solution (AI-first; nothing ships as code — reasons stated)

The losing shape inside a winning day: **the AI's own exits lost (−0.37…−0.46) while the platform's exits made +4.23**, and the single largest
destruction was FIL 226601 — two "cut half on squeeze fear" covers at −0.95 on a trade that then ran to its target.

1. **Desk lesson L-1118 (AI-first, delivered through this note into the desk's RAG corpus on deploy):**
   > *"Your stop is your risk control. Do not cut a position on ordinary noise while price is still inside your own stop and your invalidation
   > has not printed. Since 10-01 your discretionary partial covers lost +4.85 versus simply holding the cut size to the trip's own later
   > exits (n = 47; +3.40 without the largest), and the reduces the platform blocked would have lost another 2.70 if executed (n = 26). On
   > 18 Nov FIL you cut half 16 minutes after entry at +0.75 % against with a 2.5 % stop, cut half again at +0.9 %, and the remainder then hit
   > your target. Reduce only when (a) your invalidation level has printed, (b) the thesis itself changed, or (c) you are taking profit."*
   - *Hypothesis:* the lesson reduces desk partial covers taken inside the stop with the invalidation not printed.
   - *Metric:* weekly Σ(hold − cut) of desk partials (E1 method, fixed tolerance) and the count of `cyc:` partial covers per trip.
   - *Falsifier (7 days):* desk partials still occur at ≥ the 10-01 → 11-18 rate (47 in 49 days) **and** Σ(hold − cut) > 0 → the RAG lesson
     did not reach the decision; promote to R42 (prompt line). If Σ(hold − cut) ≤ 0 over the next 7 days, H-CUT is killed.
   - *Counterfactual P&L at the live marks:* +4.85 over 47 cuts (≈ +0.10/day); +2.76 on today's FIL alone.
2. **R42 (STAGED) — one decision-prompt line encoding L-1118.** Not shipped this run: the catalogue is at capacity (needs a prune), it is a
   money path requiring the two-reviewer gate, and by count the rule is a coin flip — the prompt line ships only if the RAG lesson fails its
   falsifier above.
3. **R37 is now the largest algorithmic leak ($1.90/day, 4 readings, worsening).** Design owed: a ≤ 15 s mark sampler for ratchet-armed
   positions, replayed on 11-11/11-13/11-17/11-18 tapes; *falsifier:* recovers < 0.3 of the $1.90.
4. Watching, no action: R32 (4/10 days), R34 (weakened), R41 (inconclusive), tiny-entry fee drag (n = 37, −0.54, SOFT).

### 8. Killed / corrected

- **Retracted (mine):** first H-CUT pass (n = 19, Σ +5.19) — trip-close tolerance bug excluded every trip with partial covers that had rounding
  residue. Corrected n = 47, Σ +4.85.
- **"R34 sizing is the day's lever"** — refuted for this window (6/6 large low-conf entries won; conf uninformative).
- **"R41 position-anchored ratchet recovers money"** — n = 2, opposite signs → inconclusive, not shippable.
- **"llm_silence would not fire on a real outage"** — killed: it fired and recovered on the 11-17 20–23Z outage.

### 9. Not verified

- Delivery of the 21:44Z / 23:44Z llm_silence email+sms to a human (the worker log says `sent`; no inbox check).
- Direction hit-rates use Hyperliquid 5m closes (Binance 451 from prod); the drift baseline is the traded coins only.
- H-CUT counterfactual uses the trip's own later-exit VWAP, which itself depends on later desk/ratchet choices — not a fixed horizon.
- R32 non-trending classification for 11-18 (ETH day change not separately read).
- Agents A and B left local scratch files only (`scratchpad/a/`); nothing written on the prod box.

### 10. Deploy record

`scripts/deploy.sh sweep-20261118` from the scratch clone at f8a015c, rc 0 → **`sooppiy-backend:20261118-sweep-20261118`**.
Rollback: `SOOPPIY_IMAGE=sooppiy-backend:20261117-sweep-20261117`. Reason (mode ②): new finding H-CUT (R42) whose AI-first step is the
L-1118 lesson in this note (reaches the desk only via the image's `/app/docs/reports/`), R32 verdict moved, llm_silence verdict HELD.
Docs-only; no code change.

| prod check | pass 1 (18:17:26Z) | pass 2 (18:18:46Z) |
|---|---|---|
| `.env` + worker + backend image | 20261118-sweep-20261118 ×3 | same |
| today's note in `/app/docs/reports/` (L-1118 present) | present (2 hits) | present |
| tracebacks worker / backend (10 min) | 0 / 0 | 0 / 0 |
| events flowing | max ts 18:17:11Z at 18:17:28Z | 18:18:23Z at 18:18:49Z |
| `pnl_audit` 11-18 all_in | +4.01 `ok` | same |
| `/api/health` + public routes | 200 | 200 |
