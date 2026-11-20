# Automation monitoring — 2026-11-20 (UTC day) — daily 24h sweep

Newest-first. Authority for rules/access/traps: `HANDOFF-automation-monitoring.md`.

## 24h sweep — 2026-11-20T15:13:21Z (KST day 2026-11-20 = 11-19T15:00Z → 11-20T15:00Z, closed)

Prod clock `SELECT UTC_TIMESTAMP()` = 2026-11-20 15:13:21 (on schedule; no leftover `/tmp/sooppiy-sweep.*`). Image `.env` = worker =
backend = `sooppiy-backend:20261120-stop-stamp` = 267f742 = origin/main HEAD → **no drift**.

**Ground state changed overnight (owner):** fleets 44 (agent 6) and 43 (agent 60) got `stop_all` (flatten) at **02:54:37Z**; both agents'
`signals` were deleted, `realized_pnl_usd` zeroed, cash back to 10,000.00 (reset); the platform-wide **futures / short / forex / options /
Polymarket block** shipped 04:11Z–06:02Z. Two new agent-6 fleets (51 at 06:22Z, 52 at 07:31Z, archetype `short`) ended `build_failed` after 20
`research_empty` each. **No fleet is active; `MAX(run_events.ts)` = 02:54:59Z — nothing has traded for 12 h 18 m.**

### 1. P&L — dollars first (rebuilt from `run_events` `trade` fills; `signals` and `pnl_audit` are unusable after the reset)

| window | agent 6 (info) | agent 60 (forevery1969) | combined | closes / entries | fees |
|---|---|---|---|---|---|
| **KST 11-20** = 24 h (trading ended 02:54:59Z) | **+2.44** | 0.00 (0 runs) | **+2.44** | 42 / 38 (38/38 shorts) | 1.13 |
| without largest (AAVE 230677 +0.51) | **+1.93** | — | +1.93 | | |
| trips opened AND closed in window (n = 38) | +2.30; ex-largest +1.79 | — | | | |
| UTC 11-19 (15Z–24Z part) n = 25 | +1.63 (ex-largest +1.12) | 0 | | | |
| UTC 11-20 n = 17 | +0.81 (ex-largest LIT 230979 +0.28 → +0.53) | 0 | | | |
| open uPNL now | 0 (flat; 8 members flattened by stop_all) | 0 | 0 | | |

- Shape: 33 W / 9 L (79 %), **payoff 1.40**. By exit: breakeven-ratchet/trailing-lock stops n = 40 **+2.67**, owner `fleet_stop_all`
  flatten n = 2 **−0.23** (TRUMP 230987 −0.17, BNB 230988 −0.07).
- Routes: (1) fill replay +2.437; (2) `adapt` realized Σ +3.003 (n = 44) — adapt nets exit fees only; Δ 0.566 ≈ the 42 trips' open fees
  (½ of 1.129) → reconciled; (3) `trading_runs.realized_pnl_usd` stamps = 0.00 for every run (zeroed by the reset — not a route any more).
- **Verdict: a small profit (+2.44, +1.93 without its largest), on a falling tape the all-short book was positioned for. The owner reset
  then removed it from the ledger.** Agent 60: $0, 9th day (subscription, R39).

### 2. Per-trade reasons (A = AI-authored, B = algorithm-authored; cross-checked)

**Authorship.** All 38 entries were AI shorts on one thesis template ("below all MAs, extreme fear, crowded-long squeeze"), light route,
trigger `regime:panic`. The panel flipped a light-desk LONG into the short on 11/38 (the flips netted +0.49 overall, −0.02 without AAVE 230677).
**Exits by author (B, trip-net; reconciles to +2.437 by three routes):** breakeven ratchet 37 **+2.26**, classic trail 1 +0.51, desk covers
4 legs **−0.10**, owner `fleet_stop_all` 2 **−0.23**. B counts 38 trailing-lock runs and my run-status grouping said 35. B's 38 is right: my
count grouped by `last_cycle_at` and missed 3.

| run | sym | net $ | author | reason (evidence) |
|---|---|---|---|---|
| 230677 | AAVE | +0.51 | classic trail | $19 short after a −3 % leg (panel flip of a light long); −3.1 % in 1 h; trail fired at 0.5155 of peak 0.646 |
| 230979 / 230972 | LIT | +0.28 / +0.24 | ratchet | short in a falling tape; lock banked the move |
| 230984 / 230975 | LTC / TRUMP | +0.24 / +0.22 | ratchet | same |
| **230845** | **AAVE** | **−0.22** | AI sizing + AI partial | the day's only sf 0.20 ($75, 4× usual; conv 0.77, conf 0.60) entered 104.16 into a bounce (+0.87 % at 1 h). At cyc 8 (19:59Z) the panel `hold` carried an intent that covered **half at 105.43, the bounce top** (−0.47 leg); price then fell to 103.23. Holding that half to the final lock = **+0.79 better** (verified from the four `trade` fills). The day's worst decision; it is the AI's whole net loss |
| 230987 | TRUMP | −0.17 | AI entry, owner flatten | short at 02:36Z into a bounce (+0.63 % at 1 h, +0.55 % at 4 h) — the entry was wrong; the owner's flatten 18 min later SAVED 0.09 (1 h) / 0.18 (4 h) vs holding |
| 230988 | BNB | −0.07 | AI entry (panel flip), owner flatten | wrong direction (+0.28 % at 1 h); flatten saved 0.07 at 1 h, cost 0.01 at 4 h |
| 6 ratchet losers | TRUMP 230438, STRK 230835, BCH 230967, HYPE 230992, AVAX 230950, ETH 230966b | Σ −0.14 | ratchet | 4 of the 6 armed on a **single-sample spike**: prior mark below arm, one mark set the peak, the next ~62 s mark was already under the floor (BCH: −0.010 → +0.211 → 0.091, fired at −0.011 gross). The rest is fees |
| 230966 | ETH | +0.23 | AI close | action `hold` but `order_intent` close covered at 1746.2 — right at 1 h. A close under a `hold` convenes no panel (review gap, n = 1) |
| 230967 | BCH | +0.12 | AI (panel turned an add into a cover) | correct, +0.16 vs 1 h |
| 15 runs | — | 0.00 | `no_prospect_switched` | all flat; zero fills; switch-time 1 h short counterfactual +0.89, **−0.03 without INJ** → inconclusive |

- **Direction (A):** short hit +1 h 21/38 (55 %) vs a base down-rate 59.9 %; +4 h 26/38 (68 %) vs 79.7 %. Mean move after entry −0.96 %/4 h vs
  tape drift −1.06 %. **No timing edge (5th replication). The profit was the tape, not the entries.**
- **Sizing:** corr(notional, conf) 0.06, corr(conf, net) −0.04. The only sf 0.20 was the largest loser.
- **Panel vetoes (price-only):** 29 light long proposals vetoed fell −0.61 % at 1 h → vetoes right. 33 short proposals vetoed ≈ neutral at 1 h.

### 3. Experiments (hypothesis → falsifier → result)

**E1. R43 second reading:** H = "the chair holding over a trader's stated close costs money." Same class as 11-19, n = 9 cycles / 7 positions.
**Holding beat covering by +0.78 (+0.50 ex-largest; first cycle per position +0.57), 7/9.** 11-19 gave +0.63 the other way, and 11-17's history
(n = 32) gave −4.83 the other way. Each reading follows its tape: a rising tape rewards covering a short, a falling tape rewards holding it.
**R43 stays STAGED and the R43-as-stated hypothesis is weakened.** No reading so far separates panel skill from tape. The invalidation-printed
split is still owed.

**E2. R32 ratchet arm, calibrated 1 m replay** (`research/ratchet_arm_replay.py 2026-11-19T15:00:00Z 2026-11-20T15:14:00Z 6`, n = 34, 3
skipped). Calibration k = 1 median |sim − actual| 0.0112 (passes), Σ sim 1.63 vs actual 2.08.

| k | 1 | 2 | 3 | 5 | 10 | none |
|---|---|---|---|---|---|---|
| Δ vs actual (+2.08) | −0.46 | +2.37 | +3.29 | +9.47 | +10.07 | +18.37 |
| Δ ex-largest | −0.29 | +1.24 | +2.16 | +6.25 | +6.85 | +15.14 |

A falling tape under an all-short book: every raise wins, the more the better. k = 3 tally: 11-10 +4.06, 11-13/16 +2.29, 11-17 −3.96,
11-18 +5.69, 11-19 +0.71, 11-20 +3.29 → **Σ +12.08, +6.39 without the largest day, 5/6 positive, 6 of 11 days.** It remains regime-dependent
(both rising-tape and falling-tape days favoured a raise only because of how the shorts moved). **Its premise changed tonight:** the book can no
longer be short. A long-only book has no calibrated day yet. **R32 is frozen until ≥3 calibrated long-only days exist; the short-book tally does not
transfer.**

**E3. R37 step-through, 6th reading (B):** Σ(floor − fill) 1.05 over 37 fires = **$0.0285/fire** (0.026 ex-largest), fill = trigger mark 37/37.
Readings: 0.027, 0.019, 0.028, 0.022, 0.0285. Stable inside $0.02–0.03; not worsening by a margin that means anything. New sub-shape: **9/37
fires armed on one-sample spikes, netted +0.035 and held 4 of the 6 losers.** Sharpens R37: arm only after two consecutive samples ≥ arm.
Counterfactual today ≤ +0.14 (the 4 losers) minus the winners it would also have delayed. Not computed; staged.

**E4. NEW: "no fleet can build under the spot-long-only rule in today's tape" (B found it; verified by me in data and code).**
- CODE: `symbol_research.py:922` sets `direction = long if mom_5d >= 0 else short`, and `select_targets` drops every short via
  `futures_policy.thesis_refusal` (`symbol_research.py:1735`, `fleet_planner.py:1931`). `build_universe` drops blocked MARKETS, not blocked DIRECTIONS.
  Each batch keeps the top 8 per market by |score| whatever the direction.
- DATA (`research_theses`, my query): batches 498653 (05:21Z) → 498662 (14:09Z) = **10 batches, 0 long theses**: 8 crypto shorts (refused) +
  8 us-stock shorts (`selectable=0`) each. Batch 498663 (15:13Z): 1 long, **SLV** (score 0.21, conf 0.45). B's read-only reproduction:
  `select_targets(6)` → `[SLV long]`, then `backtest_gate` drops it (expectancy −469 USD/trade over 5 trades).
- Fleets 51 and 52 each logged 20× `research_empty` ("no eligible candidates in the latest batch") → `build_failed`.
- **Killed by B:** "archetype `short` causes it" (`short` = the short-HORIZON archetype, the UI default; fleet 44 had it and traded);
  "market scope causes it" (both scopes empty); "crypto longs were crowded out by the top-8 cut" (29/29 major coins had negative mom_5d at 06:23Z).
- **Open, not measured:** whether us-stock longs with mom_5d ≥ 0 existed and were **crowded out of the top-8 by unselectable shorts.** 01:01–04:17Z
  batches still carried AMZN, TGT, MSFT longs.
- **P&L meaning:** $0 can be captured until a tradeable long passes the expectancy gate. This is the owner's rule working as written in a falling
  tape (no shorts, no falling-knife longs). It is not a malfunction. The 11-19 buy-low research found dip longs worse than random, so loosening the
  gate to "get trading" would be a loss path, not a fix.

### 4. Three-axis verification

- **DATA:** P&L by three routes (fill replay 2.437, adapt-minus-open-fees 2.437, B's cash-flow sum 2.4374). The AAVE 230845 fills were re-read by
  me. Research direction counts were re-queried by me from `research_theses` (independent of B's batch read).
- **CODE:** the direction rule and the two `thesis_refusal` call sites were read on origin/main. `futures_policy.futures_blocked()` = True and the
  stop-stamp change in `trading_runs.request_stop` were confirmed inside the running `sooppiy-worker`.
- **ADVERSARY:** "a +2.44 day means the desk improved": rejected; the entries had no edge vs drift, and the tape paid every short. "The stop_all
  flatten cost money": rejected, it saved 0.16–0.17. "Fleets fail because of a bug": rejected as stated, because the direction rule and the block
  together produce an empty set by construction in a downtrend. The crowding sub-hypothesis is unmeasured. "R43 is promotable": rejected; three
  readings, signs follow the tape.
- **A vs B:** A's exit table (lock 37 +2.556) vs B's (ratchet 37 +2.259, trail 1 +0.507): the same 38 trips with AAVE 230845's final lock leg
  booked differently (A counts the whole trip under "AI partials"). Both reconcile to +2.437. A says "no armed exits fired"; B shows none either. They agree.

### 5. Re-verification ledger (items raised or shipped since the 11-19 sweep)

| item | evidence on prod | verdict |
|---|---|---|
| sweep-20261119 deploy | superseded by 8 owner-session deploys; prod `20261120-stop-stamp` = 267f742 = origin/main | HELD (no drift) |
| futures / short block (d9826ed, 04:11Z) + forex (4ee48d3) + options/Polymarket (dc3a80f) | `futures_blocked()` True live; no order since 02:55Z, so no live refusal yet; research-side refusal proven (E4) | **HELD in code; never exercised by an order.** Side effect E4 |
| stop-stamp fixes 6c88cbb / f4f31a5 (06:49Z) | 0 runs stopped since deploy | NOT YET MEASURABLE |
| GET /api/fleets/{id} event-loop fix 9220875 | backend 0 tracebacks since 06:49Z restart | HELD (no 504 measurement taken) |
| MySQL shared SSLContext 8744641 | 0 errors in logs since restart | HELD (latency not re-measured) |
| R43 chair close→hold | 2nd reading +0.78 for holding (opposite of 11-19) | OPEN, weakened, tape-confounded |
| R42 H-CUT | the AAVE 230845 half-cut at the bounce top cost 0.79 (n = 1, for H-CUT) | observation continues |
| R32 ratchet arm | day 6 for (+3.29 k=3) | **FROZEN**: premise (short book) gone |
| R37 step-through | $0.0285/fire; new spike-arm sub-shape | STAGED |
| R34 size vs confidence | corr 0.06; sf 0.20 = largest loser | OPEN |
| R39 fleet 43 denial loop | 328 `candidate_skipped` until the 02:54Z stop, 100 % "no active subscription" | OPEN; fleet now stopped |
| R40 sell-on-short | 0 executed adds; 8 panel `sell` rulings all blocked (max_adds / underwater) | OPEN, rail contains it |
| direction 4 h hit trigger (3rd day < 40 %) | 68 % today (falling tape) | not reached; moot for a long-only book |
| llm_silence | 211 decisions / 12 h (14–26/h), 1 no_verdict, 8 salvaged | HELD (correctly silent) |

### 6. Health

| check | value |
|---|---|
| containers | worker / backend `20261120-stop-stamp` up 8 h (restart 06:49Z); admin up; mysql healthy |
| `MAX(run_events.ts)` | **02:54:59Z at 15:13:21Z.** Correct for zero active runs, not a dead worker (research batches hourly to 15:13Z) |
| tracebacks / ModuleNotFoundError / ERROR (since 06:49Z, logs before the restart are gone) | 0 / 0 / 0 worker and backend |
| active fleets | **0** (44, 43 stopped 02:54Z by the owner's reset; 51, 52 `build_failed`) |
| LLM | local gpt-oss 120b 1,466 / 20b 1,494 calls in window |
| worker `/tmp` | `sooppiy-worker.lock` only |
| agent 63 (trend module, user_id NULL) | 3 pre-block shorts (SOL, ETH, BNB, run_id NULL) still open; out of this sweep's two-user scope; the hourly block monitor tracks them |

### 7. Today's solution

The day's losing shape was **AI sizing and AI partial cuts**. The only 4×-sized entry went into a bounce, and the panel cut half of it at the
bounce top. That cost −0.47 on the leg and 0.79 vs holding, against an algorithm-exit book of +2.77. From tonight, though, the binding constraint
on P&L is not any trade: **the platform cannot open a position at all.**

1. **R44 (STAGED, owner-visible).** Research ranks directions it may not trade. AI-first is not possible here, because the desk never sees a
   candidate: research and selection are perception plumbing. The platform fix would be: when `futures_blocked()`, the screen keeps the top-N
   per market **among long-direction candidates only** and stops spending thesis LLM calls on shorts.
   - *Hypothesis:* unselectable shorts crowd tradeable us-stock longs out of the top-8.
   - *Falsifier:* at the screen time, the us-stock universe has 0 symbols with mom_5d ≥ 0 that pass the liquidity floor, or every long it would
     admit fails `backtest_gate`. Then the fix only saves compute and still builds nothing.
   - *Metric it must move:* fleet builds succeeding, then the realized P&L of what they open.
   - *Counterfactual P&L:* **none computable**, because these longs were never traded; prior evidence (11-19 buy-low research, 5 entry-edge
     replications) says such longs carry no edge.
   - **Not shipped.** Measure the crowding first (one read-only screen replay over today's batches).
2. **For the owner (a decision, not a fix):** under "spot + US stock, long-only" in a tape where 29/29 coins have negative 5-day momentum, the
   platform will, correctly, stay flat. Creating more fleets will keep ending `build_failed` after 20 tries. That is not a malfunction; nothing
   was edited.
3. **R37 sharpened:** arm the ratchet only after two consecutive samples ≥ arm. Measure its counterfactual over the six R37 readings before staging a ship.

### 8. Killed / corrected

- **"archetype `short` makes fleets fail"**, **"scope makes fleets fail"**, **"crypto longs crowded out"**: killed (E4, B).
- **"the stop_all flatten cost money"**: killed (saved 0.16–0.17).
- **"+2.44 = entry skill"**: killed (no edge vs drift).
- **R32 short-book tally applies to future trading**: withdrawn (the book is long-only now).
- My own run-status count (35 trailing-lock runs) was wrong; it is 38 (B).

### 9. Not verified

- us-stock crowding (R44's premise): not measured.
- Who sent the 02:54:37Z stop_all. B attributes it to an owner-ordered Claude session (same second across two users; `admin_audit_log` 85–87
  `member.reset_capital` 03:01:53Z by a temp admin; a session memory record). The HTTP request is not in any log still on disk.
- Price counterfactuals use Hyperliquid 5 m candles, not the platform mark. Holding-horizon counterfactuals are fixed 1 h / 4 h.
- The futures block has not refused a single live order yet (none attempted).
- Decision model stamp (`local / gpt-oss:120b / rule`) is the known-unreliable stamp; provider not resolved from `llm_usage` per decision.

### 10. Deploy record

`scripts/deploy.sh sweep-20261120` from the scratch clone at ef5d57e, rc 0 → **`sooppiy-backend:20261120-sweep-20261120`**.
Rollback: `SOOPPIY_IMAGE=sooppiy-backend:20261120-stop-stamp`. Reason (mode ②): new finding (E4 / R44, no fleet can build), R32 frozen,
new handoff trap. Docs-only; no code change.

| prod check | pass 1 (15:29:39Z) | pass 2 (15:30:26Z) |
|---|---|---|
| `.env` + worker + backend image | 20261120-sweep-20261120 ×3 | same |
| today's note in `/app/docs/reports/`; HANDOFF trap present | present / 1 hit | present / 1 hit |
| tracebacks worker / backend (since restart) | 0 / 0 | 0 / 0 |
| `futures_blocked()` live | True | True |
| worker `/tmp` | lock only | lock only |
| public pages + `/api/subscriptions/plans` | 200 ×5 (deploy.sh) | — |
