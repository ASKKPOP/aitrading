# Established facts — full logic re-analysis, 2026-08-29 (owner-ordered)

Read this FIRST. Every number here was verified in prior sessions (≥2 independent passes)
or extracted fresh from prod MySQL today. Do NOT re-derive retired numbers; do not
contradict these without new evidence from the data files below.

## The owner's complaint (verbatim intent)
"Our logic totally wrong, can not make positive profit, always hold and doesn't order."
Month-to-date UI (agent 6): total −4.52, every row +0.00. Goal of this program:
re-analyze the whole logic against complete history + external research, and produce a
plan that can actually make profit.

## Fresh prod extraction (2026-08-29, files in this directory)
- `fills_live.tsv` — signals table, ALL fills, 468 rows, 2026-08-12..08-29.
  Columns: id, agent_id, message_type, market, symbol, side, entry_price, exit_price,
  quantity, pnl, fee_usd, timestamp(epoch-sec), run_id, strategy_id.
  Per-agent: agent 5 = 186 fills, pnl −178.22 (largest loser); agent 6 = 174 fills,
  pnl shows 0.00 (WRITE DEFECT — see below); agent 59 = 82 fills +7.32; agent 60 = 26 fills +1.84.
  Platform month total (as recorded) = −169.06.
- `fills_bak.tsv` — reset6_bak_signals, agent 6's same 174 fills WITH REAL pnl:
  sum −2.59, fees 9.03. This is the truth for agent 6; the live table's 0.00 is the defect.
- `runs.tsv` — all 1,148 trading_runs (id, agent, symbol, market, status, stop_flatten,
  realized_pnl_usd, peak_pnl_usd, peak_realized_usd, fleet_id, ...).
- `exit_events.tsv` / `exit_events_bak.tsv` — full exit-relevant run_events tape
  (trade, stop_mechanism, order_intent, adapt, armed_exit, target_cap, order_plan,
  size_clamp, verdict_salvaged, no_verdict, horizon_shadow, young_dump_flag) with payloads.
- `decisions_sample.tsv` — 300 most recent full decision payloads.
- `decision_actions.tsv` — ALL-TIME decision distribution: hold 10,579 / sell 289 /
  retire 244 / buy 150. The desk holds ~94.8% of cycles. THIS is "always hold".
- `gate_skip_reasons.tsv` — why cycles skip: decision-is-hold 10,535; market closed 5,721;
  desk retired 244; loss cooldown 240; concurrency caps; confidence-below-threshold ~10.
  NOTE: entries are NOT being blocked by gates — the desk itself chooses hold.
- `agents.tsv` — agent id → name/user/capital map.

## Verified prior findings (retired-numbers list — binding)
- Fee sweep (289 crypto trips): NO sign flip at any fee level. Mean/trip −17.89bp at
  real 9bp RT taker; −13.89bp at 3bp; **−6.14bp at ZERO fee, zero slip; CI90 < 0**.
  The strategy loses money gross. Fees are secondary (+4bp maker worth having, not a fix).
- Exit-author mix (1,099-trip window): 754 ratchet / 188 horizon / 167 stop / 6 target
  = 28:1 stop:target. The give-back median was 103.1% of peak; payoff ratio 0.22 with
  ~46% win rate. THE PAYOFF GEOMETRY IS THE DEFECT, NOT WIN RATE.
- Target sweep (1,099 trips, 6 passes): flat 0.30% target maximizes mean AND median
  (target-hit 61.9%, median +17.98bp, 71% winners) but NO level's mean clears zero —
  closes only 31.5% of the gap. Residual loss = 1.5%-wide stops at 1:5 R:R + fees.
- SHIPPED 08-29 (image 20260829-targets, env-gated): TARGET_PSYCH_CAP=1 with
  {"crypto":{"base":0.3}} — targets capped to 0.30% at order time; RR_FLOOR=0.2;
  PSYCH_WEIGHT_LEVEL=high; crypto psych brief line. Known defect D-CAP-STOP-LEAK:
  eff_cap = max(cap, 0.2×stop) lets wide authored stops (72% > 1.5%) inflate the
  effective cap to 0.45–1.6% — the deployed geometry is NOT the tested one. Unfixed.
- Ratchet arm still uses legacy 0.001 fee rate while real crypto fee is 0.00045/side.
- Marks refresh 60s (was 300s; overrun was 93% of gross loss pre-fix). Measured slip 0.068%.
- agent 6 pnl write defect: exits write pnl=0 while cash delta carries the real number.
  ANY analysis of agent 6 must use fills_bak.tsv or cash deltas, never live pnl.
- #592 RATCHET_LOCK_FRAC shipped 08-27 (locks fraction of peak); n=4 fills since, 4/4 positive, starving.
- Win rate ~46% historically; all-time keep rate 84/1,412 buys = 5.95%.
- Panel demotion (#413/#414) demoted 98.2% of buys at the 08-13 cliff — the desk's
  candidate funnel, not platform gates, throttles entries.
- Fear&Greed observed range in-window only 27–74; extremes unobserved. Psych-regime-
  conditional target levels were UNSUPPORTED by data (fear and greed cohorts both pick 0.30%).

## Code map (worktree root: /Users/desirey/Programming/src/ai-trade-wt-throughput)
- `service/server/run_engine.py` — the desk: decision loop, prompts, ratchet/trail/stop
  machinery, brief lines, target cap clamp. ~8k lines.
- `service/server/order_params.py` — stop/target rails, RR_FLOOR/RR_CEILING, fee floor.
- `service/server/target_policy.py` — the shipped psych-regime target cap.
- `service/server/fleet_planner.py` — fleet slots, candidate selection, research theses.
- `service/server/analysis_agents.py` — panel (multi-agent verdicts on entries).
- `service/server/risk_engine.py` — SL/TP watcher (no mark-age check), risk rails.
- `service/server/regime.py` — psych/F&G regime state.
- `service/server/execution/` — live routing (opt-in; default is simulated ledger).

## Hard constraints (owner)
- This session NEVER places trades; the daemon trades.
- Never restart fleet 38. Never loosen gates just to manufacture entries.
- Implement only on experimental result; pre-register falsifiers; re-measure after ship.
- Profit-or-loss first: a plan is judged by expected P&L, not process elegance.
- Real money path exists but default is the simulated ledger; plans may use sim as testbed.
