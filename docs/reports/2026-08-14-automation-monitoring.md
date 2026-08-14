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

## QA — 5-agent post-deploy verification of #417 (owner-ordered)

All five QA agents reported against LIVE prod:

- **QA-1 R10/R11: PASS.** `_brake_room_usd` matched hand-computed room to
  10 decimals on 3 live runs; entry-rail notional examples correct;
  last-cycle quotes verbatim vs MySQL with correct ages; 17 decisions in
  29 min at normal cadence, 0 tracebacks. size_clamp events: 0 = expected
  (fires only on over-size); armed path proven (apply mode + default-on
  + code present). Watch: gate_skip composition change should settle;
  "light cycle: no LLM verdict" reports can be quoted — cosmetic filter
  candidate.
- **QA-2 R12: 3 PASS + open-time check.** Spam cut ~97% (fleet_status
  58/hr → 2/hr real; run 1161 gate_skips 107/hr → exactly one per 30-min
  heartbeat). Label change 17/25→22/25 emitted within 1 SECOND of the
  slot builds; UI status column always matched reality; supervision 61
  ticks/62 min, watchdog quiet. SBUX 13:30Z flatten execution check →
  one-shot scheduled 13:34Z (result below).
- **QA-3 R13: PASS 4/4.** Live audit exit 0; 08-13 false DRIFT now
  fee_asym −7.46 / resid +0.08 / ok; all historical days ok (resid ≤
  ±0.33, the max pair being the midnight adapt-lag shape); independent
  SQL hand-count matched to $0.0013, proven structural.
- **QA-4 R14: PASS 5/5.** First refresh: 22 of 40 us-stock theses are
  seed-only newcomers (composition changed, volume unchanged); gates
  kept dropping (MRK −292/trade, NVDA −200/9, SHOP −470/7) every pass;
  fleet 31 **17 → 22 slots in 27 min**, last 3 dormant on funding
  (headroom 0.0), not candidates; 2 desk-retires (FDX, BLK) each
  replaced in ONE pass; non-swing fleets bit-clean (forex-only
  rotations); LLM 80→76/refresh — watch reuse damping a few refreshes.
- **QA-5 RAG P1: PASS 5/5.** Zero DB rows touched by deploy; 40/40
  recomputed catalog hashes identical (upgrade path provably silent);
  deterministic renders in budget (trader/us-stock 39,381); 118 lessons
  rejoin byte-identically; decisions resumed 11 min post-restart; admin
  auth intact.

## SHIP — 11:09Z: PR #417 deployed (image 20260814-solutions-r10-rag)

Owner order ("full make solutions for 1,2" + "verify with 5 agents + QA 5
agents … after deploy"). Built by 5 parallel builders, adversarially
verified by 5 independent agents pre-merge (every finding fixed +
mutation-tested), shipped as one squash commit 8087e5f4:

- **R10** stop-coherence: `_entry_rail_line` (flat-book rail arithmetic)
  + apply-path shrink-only clamp (ADD-AWARE: room − held_notional×stop%,
  after the verifier reproduced the SOL shape surviving an
  increment-only clamp) + per-run-type rail selection (brake frac only
  for feedback runs). `size_clamp` telemetry; kill switch
  RUN_STOP_COHERENCE. Prod has RUN_AI_ORDER_PARAMS=apply → ACTIVE.
- **R11** `_last_cycle_word_line`: desk's own last decision quoted back,
  age-stamped, scanning past errored empty cycles.
- **R12** event dedupe: fleet replenishing status + queued-flatten
  gate_skip → change-driven + 30-min heartbeat; env parse guarded.
- **R13** pnl_audit fee_asym/resid columns; residual-judged tolerance.
- **R14** S&P-100 swing seed universe (gates untouched; kill switch
  SWING_SEED_UNIVERSE=0).
- **RAG Plan 22 Phase 1**: 40 skills → 118 atomic lessons, bodies/hashes
  byte-identical (DB no-op), `applies_when` staged for Phase 2.

Verification: full suite 4,190 + 1,337 subtests green ×2; CI green;
migrations at 0050; containers up on the new image; static roots 200;
zero startup errors. Rollback: SOOPPIY_IMAGE=sooppiy-backend:20260814-llmdefault.
5 QA agents dispatched against live prod (results appended when in).

## Cycle 2 — 09:29Z (anchored; quiet window)

- **Tape 09:00→09:29Z:** one AI partial profit-take (run 1147 AUDCHF sold
  half at 0.5753 vs entry 0.57484 — the good winner shape) and one new
  fleet-33 run (1199, draft→running). No closes, no losses, no forced
  events. No two-agent dispatch (no outcomes to analyze).
- **Open book:** 8 positions, all within ±$1. SBUX 1161 queued flatten
  still pending the 13:30Z open (watch #1).
- **Liq-defense silence EXPLAINED (not a defect):** tasks.py logs only
  when `escalations` > 0 and journals `margin_state` only for
  non-nominal/escalated states WITH a run_id. The 2 startup escalations
  were on unowned rows (USDKRW orphan pair → stdout only). Current book
  nominal → silence is the healthy output. Falsifiable dead-daemon
  trigger: leveraged position materially underwater AND zero
  margin_state events → then it's dead.
- Worker logs clean (only known Yahoo "possibly delisted" noise for
  AUDCHF/MNQ/GBPUSD symbol lookups).

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
