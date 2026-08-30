#!/usr/bin/env python3
"""Plan 31 round 2 (D2) — backfill agent 6's trading_runs.realized_pnl_usd.

The 2026-08-26 reset left realized_pnl_usd = 0 on every agent-6 run while
the restored signals ledger (scripts/backfill_agent6_pnl.py) attributes
real P&L to them — so fleet_budget_daily, fleet_planner, fleet_supervisor,
fleet_auto_tune, confidence_calibration and desk_brief all read banked
money that never existed. This recomputes each run's realized P&L with the
production writer's own formula — run_engine.compute_run_pnl (the value
_cache_realized_pnl stamps): a full replay of the run's
message_type='operation' signals, entry fees included. Verified against
15/15 agent-5 runs with nonzero stored realized_pnl_usd: replay matched
the stored value to 1e-8.

Scope: agent-6 runs where realized_pnl_usd = 0 but the replay says
otherwise. Runs with no fills replay to 0 and are correctly untouched.
Expected (verified on prod 2026-08-29): 53 runs, total −7.1072
(= −2.5865 restored exit pnl − 4.5207 entry fees).

Run manually on prod (from the repo root, so database.py picks up the
prod DATABASE_URL from the environment/.env):

    .venv/bin/python scripts/backfill_agent6_runs_realized.py            # dry run
    .venv/bin/python scripts/backfill_agent6_runs_realized.py --apply    # commit

Take a DB backup first. Idempotent: a second run finds realized_pnl_usd
already nonzero and updates nothing.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "service" / "server"))

from database import begin_write_transaction, get_db_connection  # noqa: E402
from run_engine import compute_run_pnl  # noqa: E402 — the production formula

AGENT_ID = 6
# A replay this close to zero is "no realized P&L" (matches the sibling
# script's epsilon) — those runs correctly keep their stored 0.
EPS = 0.0000001


def main() -> int:
    apply = "--apply" in sys.argv[1:]

    # Read pass: every agent-6 run whose stored value is 0, recomputed with
    # the writer's own function (it opens its own connections).
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, agent_id, market, symbol, realized_pnl_usd "
            "FROM trading_runs WHERE agent_id = ? ORDER BY id",
            (AGENT_ID,))
        runs = [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()

    targets: list[tuple[int, float]] = []  # (run_id, computed realized)
    for run in runs:
        if abs(float(run["realized_pnl_usd"] or 0)) > EPS:
            continue  # already carries a value — never overwrite
        computed = float(compute_run_pnl(run)["realized"])
        if abs(computed) > EPS:
            targets.append((int(run["id"]), computed))

    expected_total = sum(v for _, v in targets)
    print(f"scope: {len(targets)} of {len(runs)} agent-{AGENT_ID} runs "
          "(stored 0, replay nonzero)")
    for run_id, computed in targets:
        print(f"run {run_id}: 0.00000000 -> {computed:+.8f}")
    print(f"expected total: {expected_total:+.8f}")
    if not targets:
        print("nothing to do")
        return 0

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        begin_write_transaction(cursor)
        for run_id, computed in targets:
            # Guard each write on the still-zero stored value (idempotent,
            # and safe against a concurrent _cache_realized_pnl write).
            cursor.execute(
                "UPDATE trading_runs SET realized_pnl_usd = ? "
                "WHERE id = ? AND agent_id = ? AND realized_pnl_usd = 0",
                (computed, run_id, AGENT_ID))

        ids = [run_id for run_id, _ in targets]
        placeholders = ",".join("?" for _ in ids)
        cursor.execute(
            "SELECT COUNT(*) AS n, SUM(realized_pnl_usd) AS s "
            f"FROM trading_runs WHERE id IN ({placeholders})", ids)
        after = dict(cursor.fetchone())
        after_sum = float(after["s"] or 0)
        print(f"after: {after['n']} rows, sum {after_sum:+.8f}")

        if abs(after_sum - expected_total) > 0.0001:
            conn.rollback()
            print("ABORT: post-update sum does not match the replay — rolled back")
            return 1
        if apply:
            conn.commit()
            print("COMMITTED")
        else:
            conn.rollback()
            print("DRY RUN — rolled back (pass --apply to commit)")
        return 0
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
