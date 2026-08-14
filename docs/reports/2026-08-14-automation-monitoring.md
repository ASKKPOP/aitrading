# Automation monitoring — 2026-08-14 (UTC day)

Newest first. Anchor every entry to the prod DB clock.

## Probation PROVEN live to the cent (07:10Z cycle)

First post-#416 builds verified: **EURUSD 1190 (agent 5, zero completed
runs) composed at max_bet 236.93 = 0.33 × (1025.65 budget × 0.70 tier
frac) — probation applied exactly.** History-holders at full size as
designed: ZECUSDT 643.84 (2 prior runs), INTC 180.09 (agent 6 had 1
prior run — my initial suspicion was wrong and the evidence said so),
PFE/T/VZ/SBUX full. #416 post-ship watch: first sample CLOSED-CORRECT.
Overnight otherwise quiet: panels 100% genuine (0 fallback errors all
night), no stop-hits, agent P&L 5: −185.66 / 6: −7.64 / 59: +7.06.

## SCALE COHERENCE DEPLOYED (#416) — both owner-approved fixes live (00:13Z)

Merged `816091bc`, deployed **`20260814-scale-coherence`** (rollback:
`20260813-panel-fallback-guard`). Billing-block procedure followed in the
correct order this time: billing signature confirmed on THIS PR's checks
first (all 5 jobs dead in 4s, payment annotation verbatim), then full
local CI equivalents (4,105/0 pytest, ruff, frontend tsc+build, audits
closed by argument — no dep changes, zero secret-like lines), then merge.

1. **Budget-proportional house floor** live-probed in the worker:
   fleet-32 slot ($1,579.72) → floor **$9.48**; fleet-31 slot ($399.9) →
   **$2.40**; budget-less legacy → $0.99. Desks stop closing fee-scale
   ticks; authored stops get to act.
2. **First-admission probation** live-probed: fresh symbol → **0.33**,
   proven symbol (SOLUSDT, agent 5) → 1.0. Zero-record admissions can no
   longer arrive at full size.

**Watch from the open (13:30Z):** floor-close decisions should reference
scaled floors (grep 'House floor' report lines for the new $ figures);
first-admission builds should carry ~1/3 max_bet + proportionally smaller
max_loss; count probation applications per day. OPEN OWNER ITEMS: GitHub
billing; Settings AI for users 4/23.
