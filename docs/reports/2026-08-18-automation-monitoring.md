# Automation monitoring — 2026-08-18 (UTC day), newest-first

Continued from [2026-08-17](2026-08-17-automation-monitoring.md) (day closed
**+$3.84** ledger; #475 lease-renewal shipped + verified; two-user scope).
Targets: **info@askkpop.com — user 5 / agent 6 / fleet 35**;
**forevery1969@gmail.com — user 25 / agent 60 — WIPED CLEAN 00:2xZ (below),
no fleet exists until the user rebuilds one**.

## Cycle 43 — 00:2xZ (anchor 00:22): FULL US-STOCK ANALYSIS (owner ask) + owner-ordered clean-all of forevery1969

### Owner-ordered account wipe — EXECUTED 00:2xZ

Owner: "make clean all for forevery1969@gmail.com", scope confirmed via
question = **full wipe including active fleet 36**. Executed per the fleet-30
precedent (one transaction, children-first, FK-safe):

- Deleted: run_events 23,711 · fleet_events 22,200 · desk_memory 313 ·
  fleet_slots 50 · fleet_candidates 36 · trading_runs 33 · signals 13 ·
  fleets 2 (34, 36) · cooldowns 16 · profit_history 500 · alert_log 28 ·
  agent_memory 176 · agent_metric_snapshots 318. `agents.cash` reset
  **100,000.00** (= starting_capital).
- Verified: every scope-count 0; the single surviving metric row was written
  AFTER the wipe by the live metrics loop (all zeros — clean state); 0 FK
  errors / tracebacks in worker logs.
- **Rollback dump (pre-deletion, all affected rows):**
  `52.9.147.202:/home/ec2-user/backups/forevery1969-wipe-rollback-20260818.sql.gz`
  (791 KB, gzip -t OK). User 25 / agent 60 rows themselves untouched.
- llm_usage (1,084 rows) deliberately KEPT — metering, not trading history.
- Consequence: the #475 "fleet 36 Tuesday test" is void — no fleet exists
  until the user rebuilds one via sooppiy.com. The lease-fence watch
  continues on fleet 35 (agent 6) regardless.

### FULL US-STOCK ANALYSIS (two-subagent, cross-checked) — the headline numbers

Retention caveat (verified): run_events ≥ 08-09, signals ≥ 08-12 — which
covers the entire us-stock tape (first trades 08-13).

| fleet | user | config | us-stock net | legs / win rate |
|---|---|---|---|---|
| 32 | yoojinbe (agent 5) | **extreme**: 3× lev on spot, $1,106 max-bet, conf≥0.55 | **−$55.33** | 9 / **11%** |
| 33 | henry.j (agent 59) | balanced: 1× lev, $150 max-bet, conf≥0.60 | **+$7.52** | 17 / **59%** |
| 31 | agent 6 swing trial | — | ≈ −$2.14 us-stock portion (markdown only) | purged from DB |
| 35 run 1380 / 36 | agents 6 / 60 | — | $0.00 — never traded | — |

**Where the −$55.33 went:**

1. **SPCX one leg = −$35.81 (65%)** on a −1.07% ordinary move. The desk left
   `size_frac`/`leverage` null → **extreme-appetite defaults filled in
   $3,317 notional at 3× leverage**; the AI's 6.4% stop was unreachable
   because the run loss rail tolerated only ~1.3% at that size — born dead.
   drawdown_brake flatten was spec-correct and merciful (capped what the
   6.4% stop would have let reach ≈ −$212). Fleet 33 ran the SAME SPCX
   thesis at $121 → −$0.33. **27× notional on the identical signal.**
2. Watcher slippage ≈ **$5.1 beyond AI-specified stops** across 3 legs
   (worst QNT: −1.68% fill on a 1.0% stop; 30-min cycle + poll granularity).
3. Self-contradicting entries −$11.4 (QNT bought after its own thesis
   invalidation; INTC bought the setup it refused twice).
4. Fees $0.72 of $55.33 (1.3%) — **refutes any churn/fee story; this loss
   is direction × size.**
5. The 8/8 position cap blocked the one winning call (ORCL, worth ≈ +$6.6
   at fleet-33 execution) because losers were funded first.

**Fleet 32 vs 33 verdict: ~90% sizing config, not direction or rails.**
Both all-long, same symbols, same research. 33 won on quarter-size,
fast-banked partials, every loss ≤ $0.34.

**Cross-check resolutions (the law):** A's "AI put max size on" vs B's
"platform defaults" — both true: desk authored direction + full size_scale,
left size null; the **user-selected extreme appetite** filled the amount.
This is the **third account** with the null-size default class →
**R17 evidence n=3** (agents 6, 60, 5). A's fleet-33 "direction similar"
confirmed by B's config diff. B refuted three of its own priors (no us-stock
short was ever proposed — spot-only conflict is zero-cost so far; rails
identical in shape; feeds fresh through tonight).

**Structural findings:**

- **Fleet 35's us-stock slot is pre-made untradeable (budget geometry):**
  $10,009/14 ≈ $715 slot → ~$3 loss rail < any realistic stock stop; run
  1380's own cycle-1 outlook states the infeasibility. R15
  (bracket-feasibility, deployed 08-14) did NOT block this build →
  **backlog R19**.
- **Session logic clean:** all 41 us-stock signals inside 13:30–20:00Z;
  queued SBUX flatten filled 23s after open. Cost: 1,368 retry gate_skips
  over 14.7h (log spam, $0).
- **Churn:** 46 of 59 stopped us-stock runs (78%) ended at exactly $0.00.
- **Fleet 31 destruction finding:** the 08-15 agent-6 re-seed purged the
  swing trial's entire record AND its queued Monday gap-flattens
  (IBM/JPM/MSFT) — they never executed and can never be verified. The swing
  block's terminal experiment was destroyed, not answered.
- **Post-close behavior verified for the owner's question:** us-stock
  decisions stop AT the bell (last 19:58:57Z; pre-gate skips before any
  LLM); what continues is the Plan-26 outlook sweeper hourly all night.
  **No 2-hour post-close analysis window exists.**

### Watches carried

`fence: lease expired` post-#475: **0** (now agent-6 fleet 35 only).
`_railed_params_line`: mechanism proven (cycle 42), behavior n=1-ambiguous.
R:R ceiling: 5 fires, all hold, $0.00. Loss floor #460: unexercised.
Ratchet (a)-alone: queued.
