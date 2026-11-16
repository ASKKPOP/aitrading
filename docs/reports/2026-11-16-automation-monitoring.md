# Automation monitoring — 2026-11-16 (UTC day) — daily 24h sweep

Newest-first. Authority for rules/access/traps: `HANDOFF-automation-monitoring.md`.

## 24h sweep — 2026-11-16T21:42:52Z (KST day 2026-11-17 began 11-16T15:00Z; KST 11-16 = 11-15T15Z→11-16T15Z)

Prod clock `SELECT UTC_TIMESTAMP()` = 2026-11-16 21:42:52. Image on `.env`, worker and backend =
`sooppiy-backend:20261113-deps-cve-1113` (c77f810) = origin/main code (main has only docs commits after it) → **no deploy drift**.
Trading set re-derived = {6, 60} (fleets 44 and 43 active); only agent 6 cycled in 24 h.

**Coverage gap:** the scheduled task started NO session on 11-12, 11-13, 11-14 or 11-15 (`list_task_runs`: runs 11-07…11-11,
then today at 21:41:48Z instead of 15:07Z). No leftover `/tmp/sooppiy-sweep.*`. The scheduler fires only while the desktop app is
open; four days went unmonitored, including the only active trading burst (11-13 20–23Z). This sweep covers the gap window
**11-11T15:13:26Z → 11-16T21:43Z** as well as the 24 h window.

### 1. P&L — dollars first

| window | agent 6 (info) | agent 60 (forevery1969) | combined | n | fees |
|---|---|---|---|---|---|
| **24 h** (11-15T21:42Z → 11-16T21:42Z) realized | **−0.015** (2 entry fees, 0 closes) | **0.00** (0 fills) | −0.015 | 0 trips | 0.015 |
| open uPNL at 21:48Z (AAVE 169927 short $16.1, SUI 209417 short $17.4) | −0.08 … −0.10 | — | ≈ −0.09 | 2 open | |
| KST 11-16 (11-15T15Z → 11-16T15Z) | 0.00 | 0.00 | 0.00 | 0 | 0 |
| KST 11-17 so far (11-16T15Z →) | −0.015 realized | 0.00 | −0.015 | | |
| pnl_audit all_in, UTC 11-12 / 13 / 14 / 15 / 16 | 0 / **+1.09** / −0.00 / 0 / −0.02 (all `ok`, EXIT 0) | 0 | | | |
| **gap window since last sweep** realized | **+1.089** (win 20/26, payoff 1.99) | **0.00** | **+1.089** | 26 trips | 0.742 |
| gap window **without the largest** (AAVE 169219 +0.393) | **+0.696** | — | +0.696 | 25 | |

- Routes (agree within $0.02): (a) pnl_audit all_in 1.09 − 0.00 − 0.02; (b) SQL Σ close `signals.pnl` 1.4391 − entry fees 0.346
  (pnl is net of the exit fee) = 1.093; (c) Σ `trading_runs.realized_pnl_usd` of agent-6 runs started in the window = 1.074
  (includes the 2 open entry fees); (d) Agent A and Agent B per-trip pairing, each +1.0893.
- Cash reconciliation: agent 6 cash 9,858.48 = 11-11 cash 9,890.94 + realized ≈ +1.07 − margin of the two open shorts 33.53 → exact.
  Agent 60 cash 9,995.95 unchanged since 11-11 (the −4.05 lifetime gap vs seed stays unreconciled, as on 11-11).
- **Verdict:** a +$1.09 gap window on n = 26 that is really **one correlated short-beta episode** (11-13 20–23Z, 24 of 26 trips,
  same-second clustered closes at 21:07:53Z and 22:19:17Z). It does not show entry edge. It shows that **the platform exit
  kept 3–6 % of what the AI's own directional call made available** (§3). The 24 h day itself is $0: desk mute + agent 60 locked out.

### 2. Per-trade reasons (Agent A = AI-authored, Agent B = algorithm-authored; cross-checked)

**Authorship split: the AI authored 28/28 entries (all shorts) and 0/26 exits. Every exit was the breakeven ratchet**
(`stop_mechanism {trailing_lock, breakeven_ratchet}` → `run_status stop_event:trailing_lock` → `run:N:flatten`, same second).
Median hold ≈ 16 min against desk horizons of 12–72 h and brackets of 2.5 % stop / 5 % target.

| run | sym | $ | conf / size_frac | entry author | net $ | reason (A + B) |
|---|---|---|---|---|---|---|
| 169219 | AAVE | 129.2 | **0.55 / 0.40** | trader sell .55 → chair sell .55 | **+0.393** | largest by 4–8× size at the floor confidence; peak gross 1.157, ratchet floor 0.636, filled 0.509 (stepped 0.127 through); a mid-trade AI hold said "short still in loss" while the book was +0.90 → the desk misread its own position. Profit = tape, not conviction (R34 shape, this time a winner) |
| 169724 | ENA | 37.5 | 0.68 / 0.10 | trader sell → chair sell | **−0.096** | 3rd ENA short in 2 h, entered at the local low (A: chase); peak +0.144, next sample −0.062 → ratchet fired **below** its own floor (B: 0.151 step-through, 3 marks in a 2.5-min life). Direction right at 4 h (+0.55 %) |
| 169775 | ENA | 54.8 | 0.62 / 0.12 | **trader BUY .60 → chair SELL .62** | −0.041 | cut at fee noise after 11 min (step-through 0.066); right by 4 h (+3.09 %) |
| 170076 | TAO | 18.7 | 0.55 / 0.05 | **trader BUY → chair SELL** | −0.024 | the one genuine thesis failure: TAO +1.77 % in 1 h against the short; ratchet saved +0.24 vs the stop |
| 170189 / 169776 / 169089 | ZEC / FIL / LTC | 23–38 | 0.55–0.73 | mixed | −0.018 / −0.008 / −0.006 | cut within 4–13 min by step-through on a bounce; ZEC, FIL right by 4 h (+2.13 / +3.23 %), LTC mildly wrong |
| 19 others | various | 16–62 | 0.55–0.78 / 0.05–0.20 | desk | Σ +0.890 | right direction on a falling tape; ratchet banked ~40–50 % of a fee-scale peak (median peak = 4.5× round-trip fees) |

| exit mechanism (B) | n | gross | fees | net |
|---|---|---|---|---|
| breakeven ratchet | 26 | +1.831 | 0.742 | **+1.089** |
| SL / TP / max_loss / desk trail / arm / orphan | 0 | — | — | — |
| at_time / no_prospect stops (all flat) | 14 / 4 | 0 | 0 | 0 |

- **Direction (A):** right at +1 h 20/26, at +4 h 23/26, but on one falling tape (effective n ≈ 1 regime). Sixth reading of
  "entries carry no PROVEN edge"; this episode cannot refute or confirm it.
- **Size does not track confidence (A):** corr(conf, notional) −0.15 (+0.07 without 169219). The 0.40 entry was at conf 0.55.
  R34 count now 4 entries ≥ 0.3 (11-11: 3, net −2.11; 11-13: 1, net +0.39) → Σ −1.72; still below its n ≥ 10 bar.
- **Chair flips (A):** trader buy → chair sell on 8/28 entries; the 7 closed flips +0.112 (4 W / 3 L). No measurable value, again.
  Across all discussions buy→buy = 0: the panel let no long through.
- **Entries against the desk's own outlook (A):** 157187 BTC shorted 9 min after "no viable entry window before the run expires";
  **209417 SUI (open)** shorted at conf 0.55 thirteen minutes after "Maintain a flat position" at hold 0.22. R35-adjacent (n grows).
- **Step-through (B): the 6 losers lost to mark sampling, not to where the floor sits.** Marks are sampled ~60–75 s; Σ give-back
  below the intended floor across all 26 = **0.706** (net would have been ~+1.79). Same shape as 11-11 (9 net-negative ratchet exits,
  "mark stepped through a 1–2-tick floor") → **second independent reading** → R37 staged.
- **Desk exit intents that arrived after the ratchet flattened: 3** (LTC 168789, ZEC 169251, ENA 169775) — the desk is slower than the
  ratchet; its exits are moot.
- **Fences/rails (B):** null_size_refused 7, stop_cap 1, add_limit 1, fence "run is stopped" 1 ($0), size clamp 0, orphan 0.
- **Open-book risk (B, verified):** AAVE 169927 shorted at 21:33:23Z with a 72 h horizon and **at_time 22:35:47Z** — ≈ 62 min of
  run life left. The at_time stop will flatten it ~1 h after entry unless the ratchet/stop fires first. Nothing gates entry
  against remaining run life; only `_run_expiry_line` warns, and the desk ignored it → R38.

**Agent 60 (B, verified by me):** 0 runs started since **2026-11-12T22:12:55Z**; last run stopped 11-14T20:02:01Z (at_time).
Cause: `billing_events` id 8 `customer.subscription.deleted` processed 11-12T22:07:55Z → `billing_sync.end_subscription` set
user_subscriptions row 21 (`pro`, stripe, expires_at 11-17) to `expired`. Payload **`livemode: false`**, cancellation reason
**`canceled_by_retention_policy`**. All 8 billing_events ever recorded are test-mode. **User 25's entitlement rested on a Stripe
TEST subscription, and Stripe's test-data retention deleted it.** This is the owner's (billing) decision; nothing was changed.
Side effect: fleet 43 retries every candidate on every tick (`_build_replacement` catches EntitlementDenied in a generic
`except`; no cooldown) → 11.8k–17.6k `candidate_skipped`/day, ~2k `backtest_gate`/day, 279,951 fleet_events rows on this fleet,
and ~39.5k burned `trading_runs` ids (13 surviving rows in 169928–209416) → R39. One leaked draft run (169250 BLK, created at the
11-13T21:21 restart second).

**Mute desk (A, B, `llm_silence.measure`):** agent 6 1,327/1,416 decisions verdict-less in the window (**93.7 %**); per day
100 / 99.6 / 77.2 / 98.9 / 99.6 / 94.3 %. In the 24 h window the 3-h buckets read 100 % mute until 18:42Z, then 70 % at 21:42Z (the
desk started answering at ~21Z). `llm_silence_state`: silent since 11-14T01:09:04Z, re-alerted 19:34:16Z, notified. 1,904
`Request timed out` lines in the worker log (24 h). **The LLM outage set the trade count; no algorithm did.** In both recovery
windows the desk's first act was to open shorts.

### 3. Ratchet replay (daily, `research/ratchet_arm_replay.py 2026-11-13T15:00:00Z 2026-11-16T21:43:00Z 6`, 1m, n = 26, 0 skipped)

| k | 1 | 2 | 3 | 5 | 10 | none |
|---|---|---|---|---|---|---|
| sim Σ (actual +1.09) | 0.87 | 2.26 | 3.38 | 5.84 | 12.76 | 18.97 |
| Δ vs actual | −0.22 | +1.17 | +2.29 | +4.75 | +11.67 | +17.88 |
| Δ ex-largest | −0.06 | +0.51 | +1.62 | +3.98 | +9.33 | +15.54 |

Calibration k = 1: **median |sim − actual| 0.004 (passes the ≤ $0.01 bar)**, max 0.164. Three counterfactual methods, all the same sign:
replay none +18.97; A hold-to-4h ≈ +9.3; B hold-to-bracket +35.92 (first trip per symbol only, n = 11: +13.61 vs +0.47). They differ
by horizon (4 h vs bracket vs the script's bracket + trail), not by direction. **ETH fell ~2.5 % over 11-13/14 → a trending day.**
R32 tally: 11-10 for (calibrated, trending), 11-11 against (uncalibrated), 11-13/14 for (calibrated, trending) = **2 of the 10
calibrated days, 0 of the ≥ 3 non-trending days required**. 09-20→10-01 and October said the opposite on chop. Stays STAGED.

### 4. Three-axis verification

- **DATA:** gap P&L by 4 routes (§1). Mute fraction by 3 routes (A census 93.7 %, B census 93.5 %, `llm_silence.measure` buckets).
  Billing cause re-read by my own query (event id 8, livemode false, retention). Run-id burn re-counted (13 rows in the range).
- **CODE:** `fleet_supervisor._build_replacement` generic `except Exception` → `candidate_skipped`, cooldown only for
  "outside any run" (read on origin/main). `entitlements.check_run_start` returns the deny when `max_concurrent_runs ≤ 0`
  (ENTITLEMENTS_ENFORCED on prod). `get_subscription_state` lazy-expires only `expires_at < now` → could not have expired row 21.
  Live worker: `llm_silence.realert_hours()` 6.0, `run_engine._mute_cycles` present; pip freeze soupsieve 4.0.1,
  opentelemetry-api 1.45.2, dnspython 2.9.2.
- **ADVERSARY:** "the ratchet cost $18 today, raise it" — refuted as a general claim: n ≈ 1 regime, trending; history says the sign
  follows the tape. "The +1.09 shows edge" — refuted: 24/26 trips are one correlated down-leg. "Step-through is noise" — not
  refuted: 0.706 on 26 closes here plus 9 negative ratchet exits on 11-11 (two readings, same mechanism). "Agent 60's $0 is a
  platform bug" — refuted: the platform correctly enforced a real (test-mode) cancellation; the defect is the retry loop's cost.
- **A vs B disagreement (the finding):** A attributes 169724's loss to a chased entry; B to step-through below the floor. Both hold:
  the entry was at the local low (A) AND the exit filled 0.151 under its own floor (B). The step-through is the part that recurs.

### 5. Re-verification ledger (fixes and watches since the 11-11 sweep)

| item | evidence on prod | verdict |
|---|---|---|
| 11-11 deploy (20261111-sweep-20261111) | superseded by 11-13 deploys; deploy-log rows 3ea8010, c77f810 | HELD (superseded) |
| 3ea8010 llm_silence onset + recovery never swallowed | state `silent_since` 11-14T01:09:04Z (detection tick), `alerted_at` 19:34:16Z, notified true; re-alert 6 h | **HELD** |
| c77f810 deps CVE bump | pip freeze in worker = soupsieve 4.0.1 / otel 1.45.2 / dnspython 2.9.2; containers on 20261113-deps-cve-1113 | **HELD** |
| 11-11 `pnl_audit` orphan / all_in | runs EXIT 0; orphan column 0 in window (no handoffs) | HELD, not challenged |
| R31 `_mute_cycles` (no zero-verdict idle retires) | idle retires in window 0, at 93.7 % mute | **HELD** |
| f545d3e #1 null_size refuse | 7 refusals, 0 clamps | HELD |
| f545d3e #2 stop gap ≤ 5 bp | no watcher stops in window | NOT YET MEASURABLE (still FAILED at 7 bp from 11-11) |
| f545d3e #2b stop re-entry fence / #3 conviction collapse | not challenged | NOT YET MEASURABLE |
| 7110f54 handoff | 0 handoffs | NOT YET MEASURABLE |
| R32 ratchet arm | day 3 calibrated, for (trending) | OPEN — 2/10 calibrated, 0/3 non-trending |
| R34 size at low confidence | +1 entry (169219 +0.39) → n 4, Σ −1.72 | OPEN |
| R35 chair re-entry against own invalidation | 2 new entries against the desk's own flat outlook (157187 +0.040, 209417 open) | OPEN; first class-(c)-adjacent winner (157187) — does not meet the strict class (no trader reversal) |
| R29 fleet 43 plan cap (expiry 11-17) | **trigger passed early**: test-mode Stripe sub deleted 11-12T22:07Z | **CLOSED → replaced by owner item O-1116** |
| W-post-stop-cycle | 1 fence "run is stopped" ($0) | OPEN, $0 |
| Daily-sweep cadence | 4 days unfired (app closed) | **FAILED** (coverage) |

### 6. Today's solution (AI-first; nothing ships — reasons stated)

The day's loss is **$0 realized but ~$18 of directional value not kept** on the one live episode, plus **one user fully idle for
4 days**. The losing shapes, in P&L order:

1. **Owner item O-1116 (agent 60, $0 since 11-14):** user 25's `pro` entitlement was a Stripe TEST-mode subscription; Stripe's
   retention policy deleted it 11-12T22:07:55Z. The owner decides: re-grant (manual, like user 5's enterprise row) or a live
   subscription. Not mine to change.
2. **R37 — ratchet step-through (STAGED, platform; the desk cannot be the actor):** the lock is checked on ~60–75 s mark samples, so
   fast bounces fill below the floor. Σ 0.706 on 26 closes = 65 % of the window's net; 11-11 showed the same (9 negative ratchet
   exits). *Hypothesis:* sampling the mark for ratchet-armed positions at ≤ 15 s (or arming a resting stop at the floor in the
   simulator, priced at the first sample past the floor — NOT at the floor, which would fake fills) recovers ≥ 50 % of the
   step-through. *Falsifier:* a replay on the 11-11 + 11-13 tapes at 15 s marks recovers < 0.3. *Metric:* Σ(floor − fill) per
   ratchet close. *Counterfactual at live marks:* ≤ +0.71 for this window (upper bound, exact floor). Needs a design (sampler cost,
   live-venue parity) and a sub-minute replay before any code.
3. **R38 — no entry inside the last hour of a run whose horizon is longer (STAGED, desk lesson):** AAVE 169927 opened 62 min before
   at_time with a 72 h horizon; the brief line exists and was ignored. Lesson text (run-expiry skill): "If the run ends before your
   stated horizon, do not open; hold and let the successor decide." *Falsifier:* entries opened with < 1 h run life net ≥ entries
   with > 6 h per $ notional over 7 days. n = 1 today → measure first (count all entries with run-life < horizon since 10-01).
4. **R39 — entitlement denial retried forever (STAGED, platform):** treat a user-level EntitlementDenied (no subscription /
   concurrency) as user-level: stop iterating candidates on the first one and back off ≥ 30 min; never INSERT a run that will be
   denied. *Metric:* fleet 43 `candidate_skipped`/day (now 12–18k) → ≤ 50. $0 money path, but it changes fleet build flow, so it
   goes through the full gate with two reviewers in a run with the review budget. Not shipped in this run.
5. **R32 continues** (§3), daily calibrated replay.
6. **Monitoring cadence:** the sweep depends on the desktop app being open; four days (including the only trading burst) were
   unmonitored. Recorded in the handoff; HANDOFF §12 (EC2 timer, designed, not built) is the durable answer — owner decision.

### 7. Killed / corrected

- **"Agent 60 is capped at 3/3 until 11-17" (R29)** — killed: the subscription ended 11-12T22:07Z (test-mode retention).
- **"Lazy expiry flipped row 21"** — killed: `expires_at` 11-17 > now; Stripe webhook did it.
- **"The gap window's +1.09 is evidence of entry edge"** — killed: one correlated episode.
- **"The ratchet loses because its floor is set too low"** for the 6 losers — killed for this window: they lost to step-through
  below the floor (B), while the floor arithmetic armed correctly on all 26 (B checked the 4 payloads where peak < arm).

### 8. Health

| check | value |
|---|---|
| containers | worker/backend `20261113-deps-cve-1113` up 3 days; admin up; mysql healthy |
| `MAX(run_events.ts)` | 21:42:36Z at 21:42:52Z |
| tracebacks / ModuleNotFoundError / ERROR (24 h) | worker 0 / 0 / 3 (yfinance "BRK.B possibly delisted"); backend 0 / 0 / 0 |
| LLM | 1,904 timeouts; 24 h ≈ 97 % mute, recovering since ~21Z |
| `/api/health` | 200 |
| fleets | 44: 8 running, 0 idle retires; 43: `replenishing:0/8`, subscription-denied loop |
| prod image vs origin/main | equal (code) |

### 9. Not verified

- Whether the AI's mid-trade stop changes (1 / 3 / 5 %) reached `positions.stop_loss` (the ratchet closed every one first).
- Hyperliquid marks vs the simulator's own price source (first-bar open within ±0.22 % of fills on all 26).
- P&L of the 7 null-size refusals.
- Why draft run 169250 leaked (pre-restart logs gone).
- Whether prod Stripe keys are test-mode by design (all 8 billing_events are livemode=false).
- The outcome of the two open shorts (AAVE at_time 22:35:47Z falls after this note).

### 10. Deploy record

`scripts/deploy.sh sweep-20261116` from the scratch clone at 495f5a5, rc 0 → **`sooppiy-backend:20261116-sweep-20261116`**.
Rollback: `SOOPPIY_IMAGE=sooppiy-backend:20261113-deps-cve-1113`. Reason (mode ②): R32 verdict moved, R29 killed, new findings
(O-1116, R37, R39), coverage failure. Docs-only; no code change.

| prod check | pass 1 (21:59:29Z) | pass 2 (22:00:20Z) |
|---|---|---|
| `.env` + worker + backend image | 20261116-sweep-20261116 ×3 | same |
| today's note in `/app/docs/reports/` | present | present |
| `pnl_audit` 11-13 / 14 / 16 all_in | +1.09 / −0.00 / −0.02, `ok` | same |
| `_mute_cycles` in live worker | True | True |
| tracebacks worker / backend (10 min) | 0 / 0 | 0 / 0 |
| events flowing | max ts 21:58:42Z at 21:59:34Z | 21:59:41Z at 22:00:25Z |
| `/api/health` + public routes | 200 | 200 |
