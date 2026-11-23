# Correction log

Every correction given to an agent twice becomes a deterministic check rather
than another paragraph of prose (rule 2 of the Potato method: "can this be a
lint rule, a type, a test, or an API change?"). The checks live in
`service/server/tests/test_correction_checks.py` and run in the pytest job of
`scripts/ci-local.sh`, so `scripts/deploy.sh` refuses any tree that breaks one.

| Check | Correction it replaces | Incident |
|---|---|---|
| `test_sql_contains_no_backslash` | Never use `LIKE … ESCAPE '\'`; use `ESCAPE '!'` | 2026-08-01, /api/profit/history 500 on MySQL (PR #168→#169) |
| `test_run_events_is_never_queried_by_created_at` | `run_events` has no `created_at`; use `ts` | False "not journaled" finding during monitoring |
| `test_sql_has_no_space_form_timestamp_literal` | ISO `T` literals only; a space literal matches the whole day | 2026-08-09, 2026-08-24, three times on 2026-09-05 |
| `test_position_book_reads_are_run_scoped` | Scope every agent+symbol `positions` read with `run_scope_sql` | 2026-07-20, run books merged; flatten found "no position" (PR #28) |
| `test_banned_packages_absent` | Never re-add Authlib / joserfc | 2026-11-07, 95e50b3 |
| `test_china_a_shares_stay_removed` | China A-shares removed platform-wide (owner) | 2026-08-01, PR #173; found still on the marketing homepage 2026-11-23 |
| `test_suite_cannot_reach_a_real_llm` + `tests/conftest.py` (keys and aliases blanked; `openai.OpenAI` / `anthropic.Anthropic` replaced by a blocker that fails the test) | Tests must never call a live model | 2026-07-27, PR #120: "deterministic" tests decided by a model on dev machines |

## Not yet a check

These are still prose. Each is a candidate for the next check:

- Pending wake flags are cleared in `run_cycle`'s `finally`, first, guarded by `run is not None` (memory `router-pending-must-clear-in-finally`).
- Every new `stop_conditions` key needs a branch in `validate_stop_conditions` (memory `stop-conditions-validator-strips-keys`).
- Paginated list endpoints page the base table, never a one-to-many join (memory `join-fanout-breaks-paging`).
- DELETE endpoints remove child rows in the same transaction (memory `sqlite-mysql-fk-enforcement-gap`).
- Ad-hoc monitoring SQL run over SSH is not in the repo, so the `ts` rules above do not reach it.

## Known blind spots of the checks above

These were found by an adversarial review on 2026-11-23. Today each one holds no live offender, but a new one would slip past:

- SQL passed into a helper as a parameter (`_rows(cursor, sql)` in pnl_audit.py, fill_audit.py and ratchet_audit.py, `trend_accounts._query`) is not traced back to where it was built.
- A space-form timestamp bound as a *parameter* is not caught, only one written into the SQL text. `research/loss_analysis_20261106/dump.py` and `dump2.py` bind `START = "2026-09-25 00:00:00"` to `ts >= %s`. That is correct only because the time is midnight and the test is `>=`.
- A backslash held in a variable and interpolated into SQL (`ESCAPE '{ESC}'`) is not caught.
