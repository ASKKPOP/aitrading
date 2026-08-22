# HANDOFF — 2026-08-22: Monitoring Stopped, Full Audit Done, Redesign Phase 1 LIVE

**Read this first.** It supersedes HANDOFF-SESSION-2026-08-21.md and, in part,
HANDOFF-rag-phase3.md (its #508 A/B readout plan is DEAD — see §4). The two
research documents this session produced are the authority for everything here:

- [docs/research/05-full-logic-audit-2026-08-22.md](../research/05-full-logic-audit-2026-08-22.md) — the five-agent audit
- [docs/research/06-redesign-experiments-2026-08-22.md](../research/06-redesign-experiments-2026-08-22.md) — the experiments + Phase 1

## 1. OWNER ORDER (2026-08-22, binding until the owner says otherwise)

> "stop monitoring, and Analysis and researching full all logics
> (we can not use anymore current logic). Analysis our project for
> what is problems."  — then, to the analysis+redesign plan: "do"

Consequences:
- **The 30-min monitoring cycle and the daily 15:07Z sweep are STOPPED.** The
  session crons were deleted. Do NOT re-arm them unless the owner asks.
- The old "monitor and only change on reproduced evidence" operating model is
  suspended; the current mode is **redesign by pre-registered experiment**
  (owner law: implement only on experimental result — unchanged).

## 2. What was measured (headline facts, all with n, all cross-verified)

- Lifetime realized P&L of the current accounts: **−$175.30** (373 fills; sign
  robust to every single removal). Post-08-15 ≈ $0. Zero trades 08-20→deploy.
- 08-13→08-14 entry cliff **SOLVED**: #413/#414 made the 4-analyst panel the
  final author; it demoted **611 buy proposals → 11 kept (98.2%)**. Old
  suspects #426/#416/#424/#422 cleared by merge timing.
- **Panel-demotion counterfactual replay:** crypto demotions WRONG (+$145.10
  net / 74 episodes, +$84.54 stripping the best winner); futures RIGHT (0/32
  targets ever reached); forex RIGHT (0/41, 21/41 hit own stop first);
  us-stock INCONCLUSIVE (all profit = INTU).
- **Horizon replay:** targets hit **7/104** within the desk's own horizon;
  holding to plan loses **$158 MORE** than the actual early exits — targets
  are decoration, the exit rails PROTECT value (H-LEAK dead in all markets).
- Fee hurdle 2.40% is DEAD (FEE_PER_MARKET=true live). Sizing pins at the
  size_frac floor (median trip $52) — the daily-profit inequality misses by
  100–300×. Selection variable r²=0.024.

## 3. What is LIVE on prod right now

Image: **`sooppiy-backend:20260822-redesign-phase1`** (PR #527, merged main
cf0da9c9). Rollback: set `SOOPPIY_IMAGE=sooppiy-backend:20260821-revert-entry-window`
in `/home/ec2-user/sooppiy/.env` and re-run compose up.

Phase 1 changes (all live-verified ≥2×):
1. **desk_record R30 denominator fix** — record scales by peak concurrent
   notional. Live: us-stock best 0.894% → **1.68%** (matches the independent
   replay's 1.684%), futures 0.199% → 0.40%.
2. **Crypto excluded from the reachability line** (central gate in
   `desk_record.record_line`; both prompts). Other markets keep the line.
3. **`DESK_REACHABILITY_AB` deleted from code** (env var inert either way).
4. **New base skill `measured-entry-record`** (priority 47, light+trader,
   all markets) — seeded and rendering, verified in-container.

Post-deploy: first 3 decisions clean (no `reach_ab` key), 0 tracebacks.

## 4. DEAD THEORIES — do not re-run these (owner law: refutations by name)

- **#508 DESK_REACHABILITY_AB readout** (HANDOFF-rag-phase3 §4b): the A/B was
  structurally unreadable — `analysis_agents.py` rendered the line un-gated in
  both arms AND the doctrine reached control runs through skills/brief
  channels. 0 entries in both arms refuted nothing. The code is deleted.
- **Corpus-feedback suffocation via recall**: refuted — flat cycles had no
  corpus read path until 08-20, two days after the collapse.
- **"Flat fee needs ≥2.40%"**: dead since FEE_PER_MARKET went live (~07-28).
- **Forex 5-pip absurdity**: no longer reproduces (0.30% rail floor fixed it).
- **"#426/#416/#424/#422 caused the 08-13 cliff"**: cleared by timing.

## 5. THE ONE THING TO WATCH NOW (accountability metric)

The Phase 1 change is accountable to **crypto entry recovery**. Baseline:
0 entries/day for the 2 days pre-deploy; pre-collapse crypto flat-cycle
entry-intent was 5.83%. Take readings with (run from anywhere with SSH):

```sql
SELECT
 (SELECT COUNT(*) FROM run_events WHERE event_type='decision'
   AND ts > '2026-08-22T10:36:00')                          AS decisions,
 (SELECT COUNT(*) FROM run_events WHERE event_type='order_discussion'
   AND ts > '2026-08-22T10:36:00'
   AND JSON_UNQUOTE(JSON_EXTRACT(payload,'$.proposed.action'))='buy') AS buy_proposals,
 (SELECT COUNT(*) FROM run_events WHERE event_type='order_discussion'
   AND ts > '2026-08-22T10:36:00'
   AND JSON_UNQUOTE(JSON_EXTRACT(payload,'$.final.action')) IN ('buy','sell')) AS panel_kept,
 (SELECT COUNT(*) FROM signals WHERE created_at > '2026-08-22T10:36:00') AS fills;
```

Honest reporting rules: name the n; a few hours of tape is a signal, not a
verdict; if entries recover, the NEXT question is their P&L (pnl_audit, never
hand sums); if they do NOT recover within ~48h of crypto tape, say the fix
failed to move its own metric — the remaining suppressors are the panel's own
baseline (2.6% buy survival even pre-#484) and the anti-entry doctrine class
(skills wall, ordinary_day, entry_rail, predecessor_run), which Phase 2's
doctrine-dedupe addresses. Do NOT loosen any gate to manufacture recovery.

Tripwires: any traceback mentioning desk_record/trading_skills → rollback per
§3. Any single-leg loss >$10 → two-agent outcome analysis (owner law §7e).

## 6. Phase 2 queue (docs/research/06 §Phase 2 — each gated on its experiment)

1. **ATR-of-hold bracket generator** — paper-replay against the desk's own
   brackets on the 30d entries BEFORE wiring. Highest value next step.
2. Win-side exit machinery (trailing activation scaled to position, not
   max_loss_usd; position-scaled profit target; split `trailing_lock` labels).
3. Sizing ladder $52→$520→$5,200, sign measured per rung.
4. Futures/forex re-horizon or descope (decided by 1's replay).
5. positions DB invariant (UNIQUE index or SUM-based reads) — run-1099 class.
6. Idle-retire→cooldown→rebuild treadmill (299/485 stops; fleet 38 occupancy).

## 7. Access + standing traps (unchanged)

- SSH: `ssh -i ~/shell/sierrabiolab/sierrabiolab-aws.pem ec2-user@52.9.147.202`;
  MySQL: `docker exec noesis-mysql mysql -uroot -p"$(docker exec noesis-mysql
  printenv MYSQL_ROOT_PASSWORD)" sooppiy -e "…"`. Never put the password in
  the repo.
- `run_events`: filter by `ts` (no created_at); JSON column `payload`;
  JSON null coerces to 0 — guard `JSON_TYPE(…) <> 'NULL'`. `short` never
  appears in decision events — count entries from `signals`.
- P&L: `docker exec -w /app/service/server sooppiy-worker python -m pnl_audit
  --since <ts>`. Deploy: `scripts/deploy.sh <tag>` from a CLEAN worktree at
  exactly origin/main (fresh worktree needs `npm ci` in marketing/ first).
- Fleets: 37 = us-stock+forex (agent 60, $100k, 10 slots), 38 = crypto
  (agent 6, ~$10k, 7 slots). Simulator-only (verified: automation_configs
  empty; execute path hardcodes simulator).
