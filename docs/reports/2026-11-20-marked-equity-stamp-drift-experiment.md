# marked_equity stamp drift — experiment (2026-11-20)

**Verdict: H REFUTED on prod data. No code changed.**
0 of 1,196 cleanly stopped runs with operation legs carry a stamp that differs
from their ledger replay. Σ|drift| = **$0.00**, the same with or without the
largest contributor because there is none. The stale-stamp mechanism exists in
code but the recorded data never triggered it. Exposure is bounded and is
written down below so it does not get re-argued from the code.

## Question

`fleet_planner.marked_equity` adds the stamped `trading_runs.realized_pnl_usd`
for every cleanly stopped member, and that equity feeds the fleet rails (warn,
stop-loss, harvest). The stamp is written only by
`run_engine._cache_realized_pnl`: every control tick in `_control_active`, and
after the terminal transition in `_control_stopping`.
`trading_runs.request_stop`'s no-position branch goes running/paused → stopped
through `_transition`, which never stamps (checked: its UPDATE sets status,
reason, `active_key`, `stopped_at` only). A leg booked after the last tick's
stamp would then be missing from the stamp forever.

- **H:** on prod, a measurable share of cleanly stopped runs have
  stamp ≠ `run_engine.replay_realized(legs)`.
- **Falsifier:** 0 mismatches over a large sample of stopped runs that still
  have operation signals.

## Method

Read-only. `replay_realized` is the repo's leg math (the same function that
produces the stamp through `compute_run_pnl`). Tolerance 1e-6 USD; the stamp
column stores 8 decimals.

1. **Live prod DB** (after the 2026-11-20 owner reset): one bulk read of all
   stopped runs and their operation legs inside `sooppiy-backend`.
2. **Pre-reset snapshot:** the reset deleted agents 6 and 60's operation signals
   and zeroed their run P&L, so the live DB has almost no legs left.
   `signals` + `trading_runs` were taken from the weekly backup
   `/home/ec2-user/backups/db/sooppiy-20261115-040002.sql.gz` (last leg
   2026-11-14T12:19:40Z), loaded into a throwaway `mysql:8.0` container
   (`--network none`), exported as ids and numbers only, and replayed locally.
   The container and files were deleted afterwards.
3. **Sensitivity probe:** drop each run's last leg and re-compare. If the check
   cannot flag a missing leg, its zero means nothing.
4. **Exposure:** for every stop reason, the gap between `stopped_at` and the
   run's last leg, plus the code path that reason takes.

## Results

| sample | clean-stopped runs | with legs | mismatches | Σ\|drift\| |
|---|---:|---:|---:|---:|
| live prod DB (all) | 5,162 | 47 | 0 | $0.00 |
| live prod DB, non-owner agents | 126 | 47 | 0 | $0.00 |
| 11-15 snapshot (pre-reset) | 4,885 | **1,196** | **0** | **$0.00** |

- The snapshot stamps are real money: all 1,196 are non-zero, Σ stamp −$284.13,
  Σ|stamp| $623.67. Agents: 6 (1,101), 60 (48), 5 (31), 59 (16).
- **Sensitivity:** dropping the last leg flags **1,196 / 1,196**, so the
  comparison detects exactly the defect H describes.
- With and without the largest contributor: no contributor, so $0 either way.
  Not an outlier effect.

### Why zero: almost no stop takes the direct path

| stop reason (snapshot) | n | with legs | path | stamped at stop? |
|---|---:|---:|---|---|
| stop_event:trailing_lock / conviction_collapse / at_time / max_loss | 1,221 | 1,114 | `_evaluate_stop` → stopping → `_control_stopping` | yes |
| idle_retired, no_prospect_switched | 3,152 | 31 | `_evaluate_stop` (run_engine 1687/1750) → stopping | yes |
| desk_retired | 367 | 13 | `_simple_transition(→stopping)` (run_engine 8719) | yes |
| adapt_retired | 35 | 33 | `run_feedback.retire_run` → stopping | yes |
| fleet_stop_all | 110 | 5 | `request_stop`: stopping if a position is open, else **direct** | only via stopping |
| fleet_profit_target, fleet_breaker, user_stop, agent_deleted | 0 | 0 | `request_stop` direct when flat | — |

Only `request_stop`'s no-position branch skips the stamp. In the snapshot,
`fleet_stop_all` is the only reason that ever used it. Of its 5 runs with legs,
1 was a flatten through `stopping` (gap 0 s). The other 4 had been flat for
**19–28 h** (69,242–99,611 s), so dozens of control ticks had stamped their
final legs before the stop.

The three runs that really did close 3–54 s before their stop (1107, 18368,
112429, all `adapt_retired`) went through `stopping`, and `_control_stopping`
stamped them. They matched.

### Refuted hypotheses (do not re-run)

- **"Stopped-run stamps drift on prod":** 0 / 1,196, sensitivity 100%.
- **"Retire rails race the stamp":** every retire reason goes through
  `stopping` and gets stamped.

## Update 2026-11-20: fixed on owner order

The owner ordered the single-member stop path fixed anyway ("fix the
single-member stop path anyway"). This is a fix on an order, **not on a
measured defect**: the measurement above still stands at 0 / 1,196. What
shipped:

1. `trading_runs.request_stop`'s flat branch replays the run's operation
   legs (`run_engine.replay_realized`, same query and math as
   `compute_run_pnl`) and writes `realized_pnl_usd` in the same UPDATE that
   stops the run. If the leg read fails, the run still stops with its
   previous stamp.
2. The adversarial review found and reproduced a race the first commit left
   open. A `_control_active` tick that read its legs before the stop could
   write its older value after the stop committed, and a stopped run is
   never ticked again. The tick's write now applies only while the run is
   `running` or `paused`. `_control_stopping`'s post-stop writes are
   unchanged.

Tests: `tests/test_stop_stamps_realized.py`. Fail-before/pass-after on the
parent commit, with mutants on the leg filter, the guard and the call site
killed. The independent verifier ran 15 of its own probes, including the
HTTP Stop route: 11 fail on the parent and all pass after the fix.

To measure afterwards: re-run the replay over the next weekly backup. It
must still give 0 mismatches. The fix cannot raise that count, so a
non-zero result would point to a writer that has not been found yet.

## What stays latent (superseded by the update above)

The mechanism is real in code: a member whose position closes (SL/TP watcher,
desk sell, armed exit, which `_control_active` fires *after* its stamp) and that
is then stopped through `request_stop` **inside the same control tick, while
flat**, keeps a stamp missing that leg. Triggers: fleet stop-all, harvest
(`fleet_profit_target`), breaker, user Stop, master-remove (and agent delete in
run_engine).

- Window: one control tick (about 30 s) between the closing leg and the stop.
- Size: at most the fee plus the realized P&L of the legs in that window, one
  round trip on one member.
- Effect on rails: harvest, breaker, stop-all and master-remove
  (routes_automation 524/568) move the whole fleet to
  `stopping`. `fleet_supervisor` returns before it calls `marked_equity` for a
  stopping fleet, and the successor fleet gets the original
  `total_budget_usd`, not equity. A stale stamp there only reaches the
  dashboard's equity display. The one case that does reach the rails is a
  **single member stopped by hand** (user Stop on one member,
  `POST` stop in routes_runs:640) inside that window while the fleet keeps trading. The fleet's warn,
  stop-loss and harvest then read that member's stamp, off by at most that one
  leg, for the rest of the fleet's life.

Re-measure if any of these changes: a new direct `request_stop` caller that runs
on its own (a rail that stops individual members while the fleet keeps
trading), a much longer control tick, or harvest/breaker stops actually showing
up on prod. Recipe: re-run this replay over the newest weekly backup (the
script is about 40 lines: bulk legs → `replay_realized` → compare,
tolerance 1e-6). If the mechanism ever produces a mismatch, the fix is the one
`routes_fleets._stopped_member_legs` already uses since 9220875: have
`marked_equity` replay stopped members from one bulk leg read instead of
trusting the stamp.

Related: `docs/reports` 504 root cause (fix 9220875), memory
`fleet-detail-replay-pinned-event-loop`.
