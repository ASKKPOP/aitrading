# Automation monitoring — 2026-08-14 (UTC day)

Loop restarted this day under a fresh session. Cadence: 30-min cycles
(cron 13,43) + 24h sweep (15:07Z). Scope per owner directive (2026-08-14):
the fleets of **three accounts** — henry.j@eklotho.com (user 23, agent 59,
fleet 33), yoojinbe@gmail.com (user 4, agent 5, fleet 32),
info@askkpop.com (user 5, agent 6, fleet 31 = THE swing trial). US-stock
runs are NOT actively monitored outside NYSE hours (13:30–20:00Z).
Also standing: RAG (docs/plan/22) status watch — Phase 0 only, nothing
live yet.

---

## Cycle 1 — 09:00Z → 09:40Z (anchored SELECT NOW() 09:00:05)

**P&L (pnl_audit, ledger):** 08-12 −23.53 · 08-13 **−147.49** (13 flattens;
DRIFT flag −7.38 = entry-side fees, proven benign to the cent on runs
1104/1159 — see Agent B §4) · 08-14 so far −15.34.

**Fleet shape (lifetime):** 31 swing −6.90 (8W/12L, noise) ·
32 **−185.68** (7W/24L, avg win $1.45 vs avg loss $8.16 — the problem
book) · 33 **+6.94** (8W/8L, wins > losses — healthy).

### Two-agent analysis (owner rule 2026-08-13), cross-checked

**Agent A (AI-authored) verdict:** every large loss was an ENTRY decision
failure; no large loss came from a good entry managed badly. Winners share
one shape: small size (≤0.3–0.6), patience-holds, staged partials
(+7.6 across 4). Losers: full-size/stacked entries or chases against the
desk's own written invalidation (−167 across 8). Patterns:
- **AI stop economically behind the platform loss floor** n=3 (SPCX 1159,
  SOL 1099 aggregate, GC 1186), −$118: at chosen size, stop-USD > run
  loss budget, so the platform rail always fires first — the desk's stop
  is fiction. → TOP fix candidate (AI-first: sizing lesson vs remaining
  loss budget; see backlog).
- **Momentum-chase self-contradiction** n=3 (QNT 1157 bought 29 min after
  the desk itself wrote "thesis already invalidated"; INTC 1169; SPCX
  1159), −$47.
- **House-floor churn on intact theses** n=2 runs (HYPE 1148, ADBE 1163),
  8 young-dump/near-flat closes, ≈−$7 of fees/slippage.
- 7 decisions across 5 runs on the `no llm provider configured` fallback
  23:04–00:23Z (incl. GC's full-size losing entry). Zero since the
  00:27Z deploy (image `20260814-llmdefault`) — resolved.

**Agent B (algorithm-authored) verdict:** 27 forced closes; 5 rails
CORRECT (KAITO brake saved ~$19; CBRS brake preserved +0.32; fleet-33
trailing trio all beat later prices), 2 HARMFUL in hindsight (SPCX brake,
SOL max_loss timing) — both harmful cases root to UPSTREAM sizing, the
mechanisms executed as specified. Swing rails: G-sanity PASS (17/17
≥0.03); overnight cap not exercised (3.2% exposure); queued flatten 1161
correctly queued (watch execution at 13:30Z open). **Handoff §2 cadence
check is STALE**: 30-min swing cycling is the owner's 2026-08-12 spec
(look 30-min / act 60-min), not a defect — corrected in
HANDOFF-n-slot-monitoring.md this cycle.

### ROOT CAUSE of the day's largest loss (SOL 1099 −69.56, 47% of 08-13)

Confirmed empirically: the run's book was INVISIBLE to every run-scoped
read for 6h (equity `unrealized: 0.0` from re-entry 23:13Z to force-cover
05:09Z while short up to 120 SOL). Mechanism: a cover's float residue
(−8.9e-16) survived the `new_qty >= 0` delete check, MySQL DECIMAL(20,8)
rounded it to a ZERO row, and every `fetchone()` read returned that stub —
add-limit gate (max_adds 2 / cooldown 90m / underwater-add ban) and
budget cap all slept; the desk re-shorted 6× believing itself flat; only
the signal-based max_loss watcher finally acted.

**Already fixed**: PR #404 (85e2d3fd, merged 08-13 04:47Z — AFTER the
blind window) — epsilon close, lot consolidation, aggregated reads —
**deployed to prod 2026-08-14T00:26:57Z** (`20260814-llmdefault`).
Verified ≥2×: (1) epsilon code present in the running container;
(2) fresh dust-reproduction tests (exact 1099 arithmetic) pass against
main; (3) live NQ run 1197 shows moving nonzero unrealized post-deploy.
No zero-qty rows in prod. Residual: one duplicate pair on the UNOWNED
book (agent 6 USDKRW ×2) — #404's aggregated reads make it harmless;
watch, don't hand-edit.

### Docs / daemons

- `/docs/how-it-works`: healthy (login-gated SPA; guide API serves all
  groups/langs; slug falls back to `guide` group by design).
- liquidation_watch: ALIVE (`escalations=2 worst=T1 measured=6/6`), no
  action needed in-window. orphan_reclaim ALIVE (holding CRM orphan 281).
- Plan 22 RAG: **design only (Phase 0)** — Phase 1 chunking not started.

### Watch items opened

1. Run 1161 SBUX queued flatten must execute at 13:30Z open.
2. Fleet 31 stuck 17/25 — swing universe exhausted (gates honest:
   swing_history_thin + negative-expectancy backtests drop everything).
   Structural; owner decision (wider universe or smaller n).
3. Event spam ~2,500 rows/day (fleet 31 `replenishing` every 62s ×1,385;
   run 1161 queue-retry gate_skip every 33s ×1,144).
4. Same-symbol instant rebuild after desk-retire (WMT/UBER/SBUX/PFE
   chains) — cooldown only binds adapt-retires. Watch; do not ship while
   the candidate pool is this thin.
