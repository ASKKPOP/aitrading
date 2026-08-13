# Automation monitoring — 2026-08-13 (UTC day)

Newest first. Anchor every entry to the prod DB clock (`SELECT NOW()`).

---

## Cycle 1 (new loop) — 2026-08-13 05:46Z

**Loop restart under a new owner mandate (2026-08-13, verbatim intent):**
monitoring is for **user info@askkpop.com** (user 5, agent 6); analyze
each run on /automation — (1) working per plan? (2) losses/profits and WHY,
checking/modifying the RUN AI reading algorithm; (3) what we missed; (4)
how-it-works + plan-16 docs healthy; (5) suggestions + strong
recommendations, then solve directly. Cadence **every 30 min, 6AM–7PM**
(interpreted as **US Eastern** — the US-stock trading day; a KST reading
would put every cycle outside the session with nothing new to report.
Stated to the owner; adjust on their word). Additionally: *"make plan: US
stock day trading, buy/sell each 30 min, MUST follow big traders — it's
key"* → recommendation R1 below.

**State anchor:** DB NOW 2026-08-13 05:46:16Z · image
`sooppiy-backend:20260813-lot-blindness` · worker tracebacks (12h): 0 ·
main = `85e2d3fd` (#404).

### The monitored fleet exists — fleet 31 (the event §7 of the n-slot handoff was waiting for)

- **Fleet 31**, agent 6 (info@askkpop.com), archetype **swing**, us-stock
  only, target 25 slots, **replenishing:16/25**, budget $10,001.51 (seed
  10,000). Built by the owner at user level 2026-08-12 ~15:13Z. Also live
  but OUT OF SCOPE: fleet 32 (agent 5 = user 4 yoojinbe) and fleet 33
  (agent 59 = user 23).
- **P&L attribution matters:** `pnl_audit` shows 08-12 −23.53 / 08-13 (to
  05:46Z) −72.98 platform-wide, but **agent 6's share is only −4.54**
  (fleet 31 −3.81 + fleet 29 remnants −0.73). The −91.85 sits on agent 5
  (fleet 32, futures/forex/crypto) — different user, not this loop's scope.

### (1) Working per plan — mostly YES

- **All 16 running swing runs correctly stamped**: `archetype: "swing"`,
  `swing_g_frac` 0.031–0.099 (all ≥ 0.03 floor), `analysis_window`
  pre 120 / post 120 min. Session dormancy WORKS — zero decision cycles
  overnight (last decisions ~21:46–22:00Z, none since; §2.5 satisfied
  in the dormancy direction).
- **Run 1095 TMO is the exemplar**: buy 0.167 @ 601.15, then five banked
  partial wins (+0.04/+0.14/+0.11/+0.12/+0.07 = **+0.46 realized**), and
  the **first armed_exit fire on a us-stock symbol** — `price_above 603 →
  reduce 0.5`, executed, slippage **+0.0174%** (`run:1095:arm:10`,
  19:29:46Z). Buy-bank-arm is exactly the intended shape.
- **Rails fired small and correctly**: 1091/1092/1093/1096 died to
  `stop_event:trailing_lock` at −0.21/−0.13/−0.33/−0.04 — trims, not dumps.
- **Fees are percentage-scale** (e.g. 0.005 on a $100 fill) — the flat-fee
  hurdle that killed early fleets does not apply here.
- **Docs healthy**: /docs/how-it-works 200, plan-16 HTML 200, /automation
  200.

### (2) The losses and why

- **1081 UBER −3.53 (78% of fleet-31 red).** Cycle-8 buy 4.78 @ 77.81
  (conf 0.73, `hot_issue` trigger), then a **full-book sell 12 minutes
  later** @ 77.07 (−0.94%) with `client_order_id: null` — a stop-path
  execution, not a desk cycle. Desk retired the run 2h later at conf 0.53.
  The known killer shape (full dump on a sub-1% move) at small scale.
  **WATCH: identify the null-client_order_id sell path** (risk watcher /
  stop executor) and whether the authored stop sat inside ordinary range
  (§8(a) of the main handoff — judge in ordinary days).
- Everything else red is fee-scale dust (−0.01…−0.33).

### (3) What we missed — defects found this cycle

1. **Swing cadence never actually slowed: `interval_minutes: 30` is
   stamped at compose, and the 240 in `due_run_ids` is only a CEILING**
   (`interval_min = min(cap, cfg.interval_minutes)`). So the "240-min
   swing clock" (plan 23 Phase B) never engages — runs think every ~26–30
   min. n=16, structural, reproduced in code + tape (1095: 15 decisions in
   6.5h). ⚠️ This coincidentally MATCHES the owner's new day-trade ask, so
   the FIX IS A DECISION, not a patch: either compose stamps 240 for swing,
   or the owner blesses 30-min thinking as a distinct **day archetype**
   (R1). Do not silently change either way.
2. **"Follow big traders" is record-only.** `us_stock_factor_snapshots`
   is fresh (6-hourly; FINRA `short_volume_ratio` + `stocktwits_tilt`
   populated; `putcall_oi_ratio` intermittently NULL — last non-null
   04:18Z, watch the feed) — but **grep proves 0 references in
   `run_engine` or `fleet_planner`**. The desk cannot see the one signal
   the owner calls key. → R1.
3. **Replenish churn against an exhausted pool**: 671 `swing_gate` + 671
   `backtest_gate` + 333 `fleet_status` events in <6h for fleet 31 alone —
   ~9 empty slots retried every ~60s tick, re-dropping the same candidates
   (QNT/CBRS/SPCX `swing_history_thin`; NVDA −200.50, MRK −292.03 per
   trade). Universe starvation (the cycle-100 class) now with event-table
   bloat attached (~5k rows/day/fleet). Fix candidate (needs nothing from
   the desk): back off replacement attempts while the candidate set is
   unchanged, and/or don't attempt us-stock builds while the session is
   closed. Evidence: reproduced 1,342×.
4. **Orphan positions held**: agent 6 carries run-less CRM (~$124) +
   USDKRW dust ×2; `OrphanReclaim` sees them (`held: 3`) and holds by
   design. Dead capital against a $10k book — watch, don't force.

### (5) Recommendations

- **R1 (STRONG, the owner's own ask): a US-stock DAY block that follows
  big traders.** Make the accidental 30-min cadence intentional: a `day`
  archetype (30-min think clock, flat-or-reduced into the close, no
  overnight G pricing), and AI-first wiring of the big-trader tape the
  platform already records — a brief line (FINRA short-volume tilt,
  put/call OI, unusual volume) + a skill clause teaching the desk to trade
  WITH institutional flow and never against a heavy short-volume tape.
  Perception first, then measure on our own tape per §6 gates.
- **R2:** replenish back-off (defect 3) — pure platform hygiene.
- **R3:** keep the §7 promotion counters running from fleet 31's tape
  (closed legs to date: ~9 fleet-31 closes; panel starts accumulating).

**Actions this cycle:** cycle note + n-slot handoff §7 updated; loop
crons armed (30-min 6AM–7PM ET + daily sweep); no code shipped (both fix
candidates need either owner decision (cadence) or a quiet-hours window
(churn back-off) — R2 queued for evidence-complete ship next cycles).
