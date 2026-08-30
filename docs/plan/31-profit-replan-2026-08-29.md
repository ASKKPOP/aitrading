# Plan 31 — Full logic re-analysis and profit replan (2026-08-29)

**Owner order (verbatim):** "So re analysis, full checking our logic, after then make
plan How can we make profit by whole history + github AI trading research —
research by 5 agents, planing 5 agents, verification 5 agents."

**Program:** 15 agents ran 2026-08-29 (workflow `wf_0832a503-8bf`): 5 research
(R1 P&L attribution, R2 exit audit, R3 entry audit, R4 external GitHub/literature,
R5 psychology+microstructure) → 5 planners (P1–P5) → 5 adversarial verifiers
(V1 data recompute, V2 code feasibility, V3 refutation, V4 money-path safety,
V5 experimental method). Every number below survived independent recomputation or
carries its verifier's correction. Datasets + scripts: `research/replan30/`.

---

## Part A — The verified diagnosis (why the logic cannot make profit)

**A1. The scoreboard lies.** Agent 6's exits write `pnl=0` (174/174 fills; truth
preserved in `reset6_bak_signals`: −2.59 + $9.03 fees ≈ the −4.52 the UI shows).
And recorded `signals.pnl` = gross − **exit fee only**; entry fees ($15.06 this
window) are invisible everywhere. True whole-window net = **−$186.71 over 17.0d
≈ −$329/mo** (recorded: −$171.65 ≈ −$302/mo). Verified two independent ways to $0.01.

**A2. One agent is the entire loss.** Agent 5 (user 4) = −$178.22 of it
(n=31 trips, win rate 22.6%, payoff 0.20); all five largest loss trips are agent 5.
Platform excluding agent 5 = **+$1.15 true-net ≈ flat, and sign-fragile**
(−0.18 excluding its single largest winner). Nobody is making money; one agent is
losing all of it.

**A3. The payoff geometry is inverted — and degenerate on this tape.**
Win rate 42.7%, avg winner +$0.92 vs avg loser −$3.41 → payoff **0.27** (breakeven
would need ~79% wins). Target-authored exits on this tape: **0 of 310**.
The 08-29 target-cap ship made it worse two ways:
- **D-CAP-STOP-LEAK** pins deployed R:R at exactly **1:5 against** for every stop
  >1.5% (72% of stops) — proven live by run 2259 (eff cap 0.736% vs configured 0.30%).
- **Retire regression:** post-ship, 8/8 sampled retires and 26/292 holds cite an
  "unconstructible bracket" (0.30% target vs ~1.5–3.7% stop offends the LLM's own
  R:R norm) — slots now self-retire citing house rules. 0 buys in the 9.3h sample.

**A4. The dollars die in concentrated dumps the desk didn't author.** The desk
authors 72.9% of exit fills but only 11% of the loss. 80% of the loss comes from
platform-forced closes of positions held/grown too long: run 1099 (SOLUSDT short,
1 entry + 6 adds into a loser, $9.2k book, max_loss flatten, **−$65.00 = 30% of
gross loss**) and retire-flattens (−$69.65; SPCX peaked +5.78 unprotected →
−35.81). Worst 3 runs = 71.5% of the loss. The no-adds-into-losers gate EXISTS and
is on (`RUN_ADDS_REQUIRE_PROFIT`, run_engine.py:2547) but **fail-opens three ways**
(no `add_limits` on the run; `_position_quantity` exception; `upnl is None`) —
run 1099 went through one of those holes.

**A5. The horizon is cost-infeasible — no signal can save it.** Round-trip cost
15.8–22.6bp (9bp fees + 6.8–13.6bp slip) vs measured diffusion 18.9bp/√hr:
at the median 1.4h hold, cost ≈ 0.7σ; at 30min, **1.18–1.69σ** — the desk must
predict more than a full standard deviation to break even. Only 54% of actual
trips even moved more than cost. Feasibility (cost ≤ 0.1σ, a realistic signal's
capture) starts at ~3-day holds. This is why −6.14bp gross at ZERO fee (retired,
CI90<0): the class is infeasible at its own horizon, independent of fees.

**A6. External evidence (R4):** our defect is the textbook "win-rate trap"
(small target/wide stop/negative expectancy). The only live real-money LLM
trading test (Alpha Arena, Hyperliquid, Oct–Nov 2025) reproduced our exact
failure: 4/6 frontier LLMs lost 31–63%; organizer's diagnosis "over-traded,
quick tiny gains that fees erased." No published edge exists for per-cycle LLM
hold/buy micro-decisions; documented LLM value is slow-cadence sizing/veto.
Profitable geometry is bimodal — trend (10–40% WR, payoff ≫1, trailing uncapped
exits) or true scalping (1:1 R:R, near-zero fees) — ours is neither. Strongest
60s-compatible documented crypto edge: daily/weekly time-series momentum,
regime-gated (ADX/200MA), large caps.

**A7. Psychology (the human factor) has no teeth where it counts.** On the live
crypto path it is prompt prose only: the regime engine's size×0.5/no-buy policy is
dormant (`REGIME_FILTER_ENABLED` unset), `human_facts` OFF, and the crypto
candidate ranking's 0.20 psych weight multiplies a subscore hardcoded `None`
(symbol_research.py:857). The `psych_shock` routing trigger fires 100% of cycles
(zero information) and the full panel ran 0/300 sampled cycles. External evidence:
the F&G edge is real but **multi-day contrarian at extremes** (F&G≤10 → +48% avg
90-day forward, 0 negatives); no sub-hour sentiment edge exists anywhere.

**A8. Corrected magnitudes (V1/V3 — these replace all planner headline claims).**
Stop-cap replay, dollar-weighted, on the real 110 trips: 0.5% stop cap →
window −$104.58 (**≈−$185/mo, recovers ~+$118/mo**); 0.3% cap → −$57.62
(**≈−$102/mo, recovers ~+$200/mo**). Payoff improves monotonically with tighter
caps in every convention, but **geometry repair alone reaches −$100..−$185/mo,
NOT breakeven and NOT profit.** The ≥12h-holds-are-positive bucket is
**inconclusive by the owner's own rule** (sign flips when the largest winner is
stripped: +5.37 → −1.18) — horizon shift is a hypothesis for a sim A/B, not a
shippable fact. Positive expectancy can only come from a new edge class (Part B
item 7), or it doesn't exist.

---

## Part B — The plan (sequence, with verifier corrections applied)

Ordering: trustworthy measurement → stop the bleed → test the horizon → build the
edge. Every item env-gated with a kill switch, its falsifier pre-registered, and
re-measured post-ship on the same metric. Nothing loosens an entry gate. All new
fleets/rules pin `account_type=simulator` explicitly. Canonical env names fixed
here to prevent drift.

**1. Measurement first** (small code + one audited backfill).
Fix the agent-6 exit write path (healthy path: automation.py:191–212) with a
fail-before test; backfill the 174 live rows from `reset6_bak_signals` (DB backup
first; note: `signals.pnl` feeds desk_reference + adapt — this is a desk-input
change, sample decisions before/after). Add true-net accounting (entry fees
included) to the trades/positions views and a nightly invariant: per agent,
Σ`signals.pnl` == cash-delta replay ± $0.05, alert on violation; validate the
invariant by seeding a deliberate mismatch locally.
*Acceptance:* window renders −186.71 ± $0.10; fills vs runs reconcile.

**2. Stand down agent 5's new entries** (platform mechanism — env/admin toggle on
its automation rules; never a DB row patch; agent 5 = user 4 yoojinbe, fleet 32 —
fleet 38 untouched; existing positions exit normally).
*Mechanism:* removes a −$331/mo true-net source; residual platform ≈ $0.
*Falsifier:* over 30d, surviving agents' true-net per-trip EV degrades below their
windowed baseline (CI stated at n≥30) **and item 3's falsifier has not fired**
(else the geometry failure, not the pause, explains it) → unfreeze.

**3. Geometry: ONE ATOMIC ship** (small code).
(a) Delete the `_stop_dist × RR_FLOOR` term from the cap clamp (run_engine.py:7577)
**and in the same commit** clamp crypto stops: `STOP_CAP_PCT_CRYPTO` — covering
BOTH bracket paths (AI rails in order_params.py AND the deterministic gate-bracket
finalize site ~run_engine.py:7550; rails-only misses gate-authored 5% stops).
Never ship the deletion alone — the downstream R:R rail would refuse every entry.
(b) Run 0.5% vs 0.3% as the measured variable (two sim/slot arms if feasible,
else sequential 50-trip windows).
(c) Replace the prompt's bracket guidance with the house geometry stated as FACT
(stop ≤0.5%, target 0.30%, ratchet carries winners) — no "do not hold" imperative
(that would manufacture entries via prompt).
*Mechanism (corrected):* payoff 0.27 → 0.39–1.1 ($-weighted); recovers
+$118..$200/mo of the −$302/mo recorded bleed; residual −$100..−$185/mo. Also
un-wedges the retire regression (8/8 geometry-citing retires).
*Falsifiers:* at 50 completed trips — payoff not improved from 0.27 baseline
(CI), or true-net EV/trip worse than −$0.15 vs baseline −$0.55; secondary: >2
geometry-citing retires in the next 300 decisions.
*Kill:* env revert.

**4. Close the adds-gate fail-opens** (small code; canonical env
`ADD_INTO_LOSER_BLOCK=1`).
Diagnose which of the three fail-opens let run 1099's 6 adds through; make the
underwater check unconditional. **Key on position-increasing intent
(|qty_after| > |qty_before|), never on order side** — on a losing short, a buy is
the COVER; a side-keyed gate would trap losers open. Wiring test: losing-short
cover must pass, losing-short add must block.
*Falsifiers:* any post-ship run with ≥2 entry fills at negative uPnL (didn't bind);
30d walk-to-stop counterfactual of blocked adds nets > prevented loss (costs money).

**5. Ratchet arm at real cost, per-market** (small code — use
`fees.fee_rate(market)` at run_engine.py:915 instead of one global constant;
`BREAKEVEN_FEE_RATE` env stays as the kill switch. A global 0.00045 would
under-arm us-stock/forex/futures under FEE_PER_MARKET=true).
*Metric (de-confounded from #592):* arm rate — fraction of trips whose peak
exceeded 16bp that actually armed; give-back baseline = post-#592 fires only
(47–73% observed, n=3).
*Falsifier:* at 20 post-ship fires, arm rate unimproved or give-back median ≥100%.

**6. Horizon A/B — sim only, hypothesis-labeled** (small code).
Arm A current cadence vs arm B `MIN_HOLD_HOURS=12`, same candidates.
**Mandatory safety (V4-S2):** min-hold suppresses ONLY desk-authored early exits;
whitelist every platform exit author (max_loss, ratchet/trail, at_time,
adapt/retire flatten, fleet_stop_all, armed_exit) and fail-open when mark age
exceeds threshold (mark-blackout interplay). The ≥12h bucket stat is
inconclusive (A8) — this experiment decides it.
*Falsifier:* 40 trips/arm (calendar timeout 6 weeks → inconclusive), B's true-net
EV not better than A at 90% CI, or B drawdown > 2× A.

**7. The edge module — regime-gated trend class, sim only** (big code; the
program's only path to POSITIVE expectancy).
`trend_module.py` as a fleet strategy archetype: 20/55-day Donchian breakout on
large-cap crypto; trade only when ADX 25–40 and price on the right side of the
200MA; initial stop 1×ATR (≤0.5%); exit = 3×ATR chandelier trail, **no fixed
target** (class-keyed exemption from the 0.30% cap — needs a `cap_for` signature
change); vol-parity sizing; the LLM desk demoted to one daily veto/size decision
(the only role with documented LLM value). `account_type=simulator` pinned.
Panel de-saturation rides along: `psych_shock` fires only on delta; use the
existing env kill to restore deterministic full-routing for candidate cycles,
with a call-budget cap and a no_verdict-rate falsifier (LLM oversubscription:
~5× at 178 calls/h precedent).
*No promised P&L number* (backtests deflate ~500×; Alpha Arena).
*Falsifier:* 30 trips or 60 trading days of live-window sim — true-net EV ≤ 0 or
payoff < 1.5 → module dies, no capital.

**8. Psychology with teeth — shadow first** (small code).
Wire the crypto psych subscore (symbol_research.py:857 `None` → real F&G-derived
value) so the existing 0.20 weight binds. Build regime SHADOW mode (log-only —
this mode does not exist today and the global `REGIME_FILTER_ENABLED` flip is
rejected: bands are self-described placeholders): log 2 weeks of would-be
vetoes/sizings; enforce per-arm only if vetoed-entry EV < allowed-entry EV.
Arm the F&G-extreme contrarian rule passively (≤20 → contrarian multi-day long
via item 7's class; ≥80 → no new longs) — in-window F&G 27–74 means it correctly
does nothing until extremes appear (n=10 falsifier, underpowered by design,
acceptable because passive).

**9. Refuse list (binding).**
No throughput raises (at −$0.554/trip, 2× entries = −$605/mo). No gate loosening
to manufacture entries. No global regime enable. No psych re-weighting at the
current horizon (prose without teeth). Maker-fee work deferred (+4bp, secondary).
No live-account promotion of anything before its sim falsifier passes. Never
restart fleet 38.

**Program decision gates.** Item 3's 50-trip readout decides whether 6–7 proceed
on a stabilized base. Honest expectation: items 1–5 take the book from −$302/mo
(recorded) to roughly **−$100..−$185/mo**; item 6 may close more if the horizon
hypothesis survives; **only item 7 can make the number positive** — and if it
fails its falsifier, the honest answer is that this venue/cost structure has no
edge in this class, and being flat (which beat −$169 this month) is the correct
book until a class with an edge exists.

---

## Part C — Verifier corrections ledger (why numbers here differ from P1–P5 drafts)

- V1/V3: stop-cap "breakeven / +$240–300/mo" REFUTED dollar-weighted → replaced
  by +$118..$200/mo recovery, residual −$100..−$185/mo. R2's replay row appears
  convention-shifted; direction confirmed in every convention.
- V3: ≥12h bucket ruled inconclusive (owner rule §6 — sign flips ex-largest
  winner: +5.37 → −1.18); survivorship-conditioned; forced-hold live ship (P4-2)
  rejected; sim A/B retained.
- V3: "platform ex-agent-5 profitable" corrected to ≈ $0 true-net, sign-fragile.
- V2: adds-gate already exists (fail-opens are the defect); ratchet fee already
  env-tunable; leak-deletion must be atomic with the stop clamp; rails-only clamp
  misses the deterministic bracket path; regime shadow mode and per-arm scoping
  are new code, not env-flips; existing env kill for the AI router override.
- V4: adds-gate must be intent-keyed (side-keyed blocks losing-short covers);
  min-hold needs exit-author whitelist + mark-age fail-open; per-market ratchet
  fee; agent-5 pause is a platform mechanism on a real user's account, not a row
  patch; pin simulator on all new arms; canonical env names.
- V5: ratchet falsifier de-confounded from #592 (arm-rate metric, post-#592
  baseline); mechanism-specific falsifiers everywhere (never shared book P&L
  except at program gates); calendar timeouts; chandelier replay requires a
  continuous mark source (prod mark cache/OKX candles — feed-basis trap noted)
  or is unrunnable on the exit-censored fills tape.

---

## Part D — Execution log (owner: "do all", 2026-08-29/30)

All eight Part-B items implemented in one program (branch plan31-ship). Three
implementation agents on disjoint files + the main session on run_engine.py;
every gate mutation-tested (11 injected bugs total, 11 caught).

| # | Item | Mechanism shipped | Env (prod value) |
|---|------|-------------------|------------------|
| 1 | Measurement | agent-6 diagnosis: NOT a live write defect — a one-time reset 08-26 00:32Z (reset6_bak_* tables; live pnl zeroed, cash restored to 10000). Backfill script restores the 102 exit rows (`scripts/backfill_agent6_pnl.py`, dry-run default, sum-guard, idempotent). Nightly row-level invariant `ledger_invariant.py` replays each book (validated on all 310 prod exits, worst delta 3.1e-7) + admin alert. UI note: the server aggregate is ALREADY entry-fee-accurate (`COALESCE(pnl, -fee_usd)`, routes_trading.py:995) — only the zeroed rows corrupted it. | LEDGER_INVARIANT_ENABLED=1 (default) |
| 2 | Agent-5 stand-down | `_entry_frozen()` platform rail: AGENT_ENTRY_FREEZE csv of agent ids; buy/short skip with journaled gate_skip stage entry_freeze; sell/cover and every platform exit author untouched. | AGENT_ENTRY_FREEZE=5 |
| 3 | Geometry (atomic) | Stop clamp BEFORE the target-cap block on WHICHEVER bracket won (AI rails and the deterministic gate bracket both flow through it); clamped stop bounds the RR_FLOOR leak term at cap×RR_FLOOR — never-refuse invariant preserved at every RR_FLOOR. `stop_cap` telemetry. Prompt line now states the full house geometry as FACT (stop cap + target cap + "target below stop is the house design"), no imperative. | STOP_CAP_PCT_CRYPTO=0.5 |
| 4 | Adds-gate fail-close | Underwater block moved ABOVE the add_limits/opens early-outs; with the env on, unknown uPnL fail-CLOSES the add; intent-keyed via the existing open_side logic (a buy against a short book is a cover → never blocked; unit-tested both directions). qty-unreadable path stays fail-open (blocking there would block fresh entries) but now logs + emits add_gate_error. | ADD_INTO_LOSER_BLOCK=1 |
| 5 | Ratchet arm | `_breakeven_arm_usd` prices the arm at `fees.fee_rate(market)` (crypto 0.00045 vs legacy 0.001); BREAKEVEN_FEE_RATE env, when set, overrides everything (kill switch). Both call sites pass the market. Arm floor incl. slip via multiplier. | BREAKEVEN_ARM_FEES=1.78 (→ ~16bp arm on crypto) |
| 6 | Min-hold (sim A/B) | Per-run cfg `min_hold_hours` (NEVER a global env): desk sell/cover on a younger position converts to a journaled gate_skip stage min_hold; platform exit authors (max_loss, ratchet/trail, at_time, retire flatten, fleet_stop_all, armed_exit, watcher) run outside this path — whitelisted by construction; fails OPEN on stale mark or any error. Arm-B creation deferred until entries resume post-item-3 (an A/B needs flow to measure). | (per-run config) |
| 7 | Trend module | `trend_module.py` (522 lines, 33 tests, 8/8 mutations caught): Donchian-20 breakout gated by ADX 25–40 + 200MA, F&G≥80 blocks longs, F&G≤20 arms a tagged contrarian long; 1.5×ATR initial stop, RATCHETED 3×ATR chandelier trail (never loosens — the give-back lesson), 30d time-stop, vol-parity sizing (RISK_USD/1.5×ATR), max 3 positions; ONE LLM veto/size call per signal (fail-soft to no-veto); executes via `automation.execute_paper_trade` with run_id=None and idempotent client_order_ids — outside the desk world, invisible to the SL/TP watcher, sim ledger only, refuses to run without a dedicated TREND_AGENT_ID. Wired as hourly `trend_module_loop` (acts on daily closes). `trend_stats()` is the falsifier readout. | TREND_MODULE_ENABLED=1, TREND_AGENT_ID=(dedicated sim agent) |
| 8 | Psych with teeth | Crypto psych subscore wired (was hardcoded None): F&G→[−1,+1] tilt, direction-aligned contrarian (extreme fear boosts longs/penalizes shorts), knees at 30/70 matching regime bands, fail-soft None; the 0.20 weight now binds (tested). Regime SHADOW mode: REGIME_SHADOW=1 logs would-veto/resize verdicts (log line + automation_runs telemetry) without enforcing; REGIME_FILTER_ENABLED stays unset (global enforce rejected — placeholder bands). | CRYPTO_PSYCH_SUBSCORE=1 (default), REGIME_SHADOW=1 |
| + | psych_shock de-saturation | Trigger fires on the TRANSITION into shock + 60min, then quiet until it clears and re-enters (was: 300/300 cycles). PSYCH_SHOCK_DELTA=0 restores always-on. | (default on) |

### Falsifier board (frozen at ship)
- F31-GEOM: 50 completed crypto trips post-ship — payoff must improve from 0.27 (CI) and true-net EV/trip better than −$0.15 vs −$0.55 baseline; >2 geometry-citing retires in the next 300 decisions also fails it.
- F31-ADDS: any post-ship run with ≥2 entry fills at negative uPnL fails; 30d blocked-add walk-to-stop counterfactual must not exceed prevented loss.
- F31-ARM: arm rate of trips peaking >16bp must rise; give-back baseline = post-#592 fires only (47–73%, n=3); ≥100% median at n=20 fails.
- F31-FREEZE: 30d — surviving agents' true-net EV degrading below baseline (n≥30, CI) WITH F31-GEOM not fired → unfreeze agent 5.
- F31-TREND: 30 trips or 60 trading days sim — true-net EV ≤ 0 or payoff < 1.5 → module dies, no capital.
- F31-SHADOW: 2 weeks of regime_shadow logs → enforce per-arm only if vetoed-entry EV < allowed-entry EV.
- F31-PSYCH-SUB: candidate composites must actually move with F&G (measurable in screen logs); dead subscore = wiring failed.

---

## Part E — 10-agent verification (owner-ordered) + round-2 fixes (2026-08-30)

Workflow `wf_2a66c9fe-f44`: 5 analysis (A1 prod state, A2 gate code, A3 trend
module, A4 live tape, A5 measurement) + 5 QA (Q1 refutation, Q2 money path,
Q3 test quality, Q4 regression, Q5 method). Unanimous verdict:
**VERIFIED-WITH-DEFECTS** — deployment faithful (A1: per-file sha256 of all
1,602 prod files == fa6474fb; backfill blast radius exactly 102 rows), money
path proven isolated (Q2: submit_live has one caller and prod has 0
automation_configs; fleet 38 stopped, untouched), backfill numerically
perfect (A5: 0 violations over all 310 prod exits) — and the following
defects found and fixed the same night:

| ID | Finding (agent) | Fix |
|----|-----------------|-----|
| D1 | Stop cap 0.5% < entry mark-drift cap 0.75% → an entry can fill already through its capped stop; watcher then closes it at a guaranteed loss (A2-3, confirmed Q1-1/Q2-10) | prod env `RUN_ENTRY_MARK_DRIFT_CAP_PCT=0.5` — drift refusal bound at the stop cap |
| D2 | `trading_runs.realized_pnl_usd` still 0.00 for all 575 agent-6 runs; consumed live by fleet budget/planner/supervisor/auto-tune, confidence calibration, desk briefs, RAG ingest under ACTIVE fleet 41 (A5-7, bound to item-1 acceptance by Q1-2) | `scripts/backfill_agent6_runs_realized.py` — per-run restore mirroring the production writer's formula, ground-truthed against agent-5 stored values |
| D3 | REGIME_SHADOW census wired to a dead path: desk passes regime_read=None; automation rules have 0 configs → 2-week census collects nothing (Q5-1, refines Q2-7/A4-5) | run_cycle now computes the crypto regime read when shadow is on AND enforcement is off (the None stays whenever REGIME_FILTER_ENABLED is set, so enforcement semantics are unchanged) |
| D4 | Per-market ratchet arm collapsed non-crypto arms 7–11× (us-stock 1.78bp) and set polymarket's to 0 = ratchet disabled; the Part-B rationale was arithmetically inverted (A2-8, Q1-7, Q4-3) | arm re-scoped to the evidence: crypto gets fee_rate×mult; every other market keeps the byte-identical legacy anchor (0.001, mult 1.0) |
| D5 | Trend module: crash between ledger commit and state save leaves an unmanaged lot; next-day rerun double-enters (A3-5) | ledger reconcile at cycle start adopts any module-agent lot missing from state; same-day duplicate refusals re-adopt too |
| D6 | 12 surviving mutants = 12 test gaps (Q3): short-side stop cap, min_hold cover, ARM_FEES multiplier, invariant tolerance/window/partial-exit, trend short stop, size_mult clamp, exit-failure retention, tilt scoping, shadow allow/None-read | all 12 pinned with mutant-kill proofs |
| D7 | Item 3(b)'s 0.5-vs-0.3 stop-cap experiment silently dropped (Q5-2, Q1-4) | RECORDED here: after F31-GEOM's 50 trips at 0.5%, run the next 50-trip window at `STOP_CAP_PCT_CRYPTO=0.3` (sequential-window design); the two windows decide the cap level |
| D9 | min_hold consumer had no producer — arm B uncreatable without a DB row edit (A2-6, Q1-5) | `RunIn.min_hold_hours` (0<h≤720) flows into config_snapshot — the sanctioned producer |
| D10 | TREND_AGENT_ID mistyped to a real user's agent would trade that book unvalidated (Q2-2) | `_agent_is_dedicated`: agent must exist with user_id NULL, fail-closed |
| D11 | psych_shock state reset by a feed outage → re-convenes the full desk every feed flap (A2-10) | only an affirmative no-shock read clears the transition state |
| D12 | Invariant blind spots: NULL-pnl exits invisible; no message_type filter; and the 08-26 incident's cash-reset half would pass the row replay clean (A5-5/6, Q1-3) | NULL-pnl exits flagged; operation filter added; per-agent cash snapshot reconcile added (the Part-B cash-delta spec, implemented) |

Recorded deviations (deliberate, now documented): trend module uses 20-day
Donchian (not 20/55) and 1.5×ATR uncapped initial stop (not 1×ATR≤0.5%) —
the trend pole needs vol-scaled room; judged solely by F31-TREND. The
call-budget-cap rider was for a deterministic full-routing restore that was
NOT shipped (only psych_shock de-saturation was), so no cap is currently
needed; if full-routing is ever forced, ship the cap with it. Q4-2a/2b edge
deviations (degenerate no-open-fills add blocked; add_gate_error telemetry)
accepted as conservative. Trail-lock fee anchor (run_engine.py:~1236) left
at flat 0.001 — pre-existing, conservative direction, documented
inconsistency. UI render check: API-level totals verified (agent-6 month
−7.11, platform −186.71); browser-level render not exercised.

Additional falsifiers from this round:
- F31-SHOCK-QUIET: after any worker (re)start +60min, decisions must stop
  carrying psych_shock until the shock state clears and re-enters. First
  window (01:48–02:48) consistent: 35/35 decisions inside the window, 0 after.
- F31-SHADOW-CENSUS: within 48h of the D3 fix deploy, ≥1 regime_shadow
  verdict must appear in run telemetry on a crypto buy cycle — else the
  census is still dead and D3 failed.
- F31-ARM-NONCRYPTO: non-crypto stop_mechanism fires must show arm ≈ 20bp
  of notional (legacy) — any 1.78bp-class arm after the D4 fix deploy = regression.
