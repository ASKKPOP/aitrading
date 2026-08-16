# Plan 26 — Slot Strategy Outlook: Monitoring Guide

*For automation-monitoring sessions. Authority chain: docs/reports/HANDOFF-n-slot-monitoring.md (§7b AI
authors every order, §7c two-axis attribution, §7e two-subagent outcome rules) + docs/plan/26-slot-strategy-outlook.html
(§3.7 profit mechanism and verdict). This guide adds Plan-26-specific checks to the normal cycle; it replaces nothing.*

## 0 · State awareness (read first)

- Feature ships behind `OUTLOOK_ENABLED` (default **off**). Until the flag is flipped on prod, there is
  **nothing to observe** — zero `outlook` rows is the *correct* state, not a defect. Check the flag before
  reporting absence as a finding.
- Rollback is `OUTLOOK_ENABLED=0` + worker restart: prompt reverts to its pre-plan shape instantly. No schema
  to unwind (`run_events` rows are inert history).
- All queries below: `run_events` is queried by **`ts`** — `created_at` does not exist and fails silently.

## 1 · First hour after the flag flips (deploy verification)

1. Cycle-authored outlooks appear for every open fast market within its floor (us-stock/crypto/forex ≤ 30 min):
   ```sql
   SELECT r.market, COUNT(*) n, MAX(e.ts) newest
   FROM run_events e JOIN trading_runs r ON r.id = e.run_id
   WHERE e.event_type = 'outlook' AND e.ts > NOW() - INTERVAL 1 HOUR
   GROUP BY r.market;
   ```
2. Sweeper-authored rows (`$.source = "sweeper"`) appear only for closed sessions / dormant slots — after
   us-stock close, over the forex weekend, or on paused runs. Open+cycling runs must have **only**
   `"cycle"`-sourced rows (double-writing is a defect).
3. i18n warm: new rows in the translation cache for outlook narratives shortly after first emissions.
4. API: `GET /api/fleets/{id}/outlook` returns 200 with populated `outlook` for a live fleet; the Automation
   page panel renders (levels strip + dialog).
5. Every decision row now carries `plan_adherence`:
   ```sql
   SELECT JSON_UNQUOTE(JSON_EXTRACT(payload,'$.plan_adherence')) a, COUNT(*)
   FROM run_events WHERE event_type='decision' AND ts > NOW() - INTERVAL 1 HOUR GROUP BY a;
   ```
   `NULL` here after the flag is on = the parser or prompt regressed — that is a finding.

## 2 · Ongoing per-cycle checks (add to the normal ~30-min sweep)

- **Freshness SLO:** newest outlook age per *open* market ≤ its floor (30/30/30, others 60). Closed sessions
  may age up to 60 min. Breach twice in a row = reproduced evidence → investigate the sweeper loop
  (`outlook_refresher` in the worker's `settlement` role).
- **Discussion verdict mix** (which author is winning the argument):
  ```sql
  SELECT JSON_UNQUOTE(JSON_EXTRACT(payload,'$.basis.verdict')) v, COUNT(*)
  FROM run_events WHERE event_type='outlook' AND ts > NOW() - INTERVAL 1 DAY GROUP BY v;
  ```
  A **spike in `algo_fallback`** = the LLM path is down (provider dead, parse failures) — same class as the
  silent-desk trap; check worker logs immediately.
- **Adherence mix:** `deviated` without a stated reason in the decision `report` violates the plan-discipline
  skill — per-trade finding, not a statistic.
- **Known gaps shipped with v1** (watch, don't re-discover):
  1. Runs not in status `running` (armed/paused/stopping) are treated as cold by the sweeper — rare
     double-author within one floor window is possible. Log if seen; fix only on reproduced evidence.
  2. Sweeper has **no per-tick LLM call cap** — first tick after a weekend can burst one call per due slot.
     Watch Saturday 00:00 UTC (forex close) and Monday reopen.
  3. `time_exit` from the LLM is length-clamped, not ISO-validated — malformed values render raw in the UI.
- **Stop echo invariant:** `outlook.exit.stop_ref_px` must equal the run's live stop. Any mismatch is a
  defect (the model's stop is discarded in code — write-once stop rule).

## 3 · Outcome analysis (two-subagent rule integration)

Agent A (AI-authored outcomes) now has a sharper tool: every close can be judged **against the slot's
standing plan at the time** — was the exit at the planned target/stop/time, or a deviation, and what reason
was stated? A description without the plan-vs-action reason is not analysis. Agent B (algorithm-authored
outcomes) additionally attributes sweeper-authored (`algo_fallback`) plans to the algorithm axis.

## 4 · Day-7 profit verdict (the actual goal — plan §3.7)

After 7 trading days with the flag on, run the `pnl_audit` ledger replay (forced flattens included) and split:

- by `plan_adherence` (followed / revised / deviated), and
- by `basis.verdict` (adopted / adjusted / overridden / algo_fallback).

**Pass** = expectancy per trade at or above the pre-flag baseline AND plan-following cycles not
underperforming deviations. **Fail** = `OUTLOOK_ENABLED=0` and the plan logic is revised. Verdict is stated
in profit-or-loss terms first, process health second; a small favorable delta on a large loss is not
improvement. The verdict-split also answers "which author picks better targets" — by measured P&L, not
preference — and that decides who leads the next iteration.
