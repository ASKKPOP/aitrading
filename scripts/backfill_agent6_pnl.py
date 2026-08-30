#!/usr/bin/env python3
"""Plan 31 item 1 — restore agent 6's zeroed signals.pnl from reset6_bak_signals.

The 2026-08-26 00:32Z reset zeroed pnl on agent 6's live exit rows
(ids 1361–1541) while reset6_bak_signals kept the true values for the
identical rows. This restores signals.pnl by id join, ONLY where the live
value is 0 and the backup differs. Nothing else is touched — not cash,
not points, no other column or table.

Run manually on prod (from the repo root, so database.py picks up the
prod DATABASE_URL from the environment/.env):

    .venv/bin/python scripts/backfill_agent6_pnl.py            # dry run
    .venv/bin/python scripts/backfill_agent6_pnl.py --apply    # commit

Take a DB backup first. Expected scope (verified against the
research/replan30 extraction): 102 rows, backup pnl sum −2.5865.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "service" / "server"))

from database import begin_write_transaction, get_db_connection  # noqa: E402

AGENT_ID = 6

# Live pnl = 0 (the reset's fingerprint) and the backup carries a real value.
SELECT_SCOPE = """
    SELECT s.id, s.pnl AS live_pnl, b.pnl AS bak_pnl
    FROM signals s
    JOIN reset6_bak_signals b ON b.id = s.id
    WHERE s.agent_id = ?
      AND s.pnl = 0
      AND b.pnl IS NOT NULL
      AND ABS(b.pnl) > 0.0000001
"""


def main() -> int:
    apply = "--apply" in sys.argv[1:]
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        begin_write_transaction(cursor)

        cursor.execute(SELECT_SCOPE, (AGENT_ID,))
        rows = [dict(r) for r in cursor.fetchall()]
        before_sum = sum(float(r["live_pnl"]) for r in rows)
        bak_sum = sum(float(r["bak_pnl"]) for r in rows)
        print(f"scope: {len(rows)} rows (agent {AGENT_ID}, live pnl=0, backup differs)")
        print(f"before: live sum {before_sum:.4f} | backup sum {bak_sum:.4f}")
        if not rows:
            conn.rollback()
            print("nothing to do")
            return 0

        # Portable UPDATE (SQLite has no UPDATE...JOIN); the id set is small.
        ids = [int(r["id"]) for r in rows]
        placeholders = ",".join("?" for _ in ids)
        cursor.execute(
            "UPDATE signals SET pnl = "
            "(SELECT b.pnl FROM reset6_bak_signals b WHERE b.id = signals.id) "
            f"WHERE id IN ({placeholders})",
            ids,
        )
        updated = cursor.rowcount if cursor.rowcount is not None else -1

        cursor.execute(
            "SELECT COUNT(*) AS n, SUM(pnl) AS s FROM signals "
            f"WHERE id IN ({placeholders})",
            ids,
        )
        after = dict(cursor.fetchone())
        print(f"after: {after['n']} rows, live sum {float(after['s']):.4f} "
              f"(updated={updated})")

        if abs(float(after["s"]) - bak_sum) > 0.0001:
            conn.rollback()
            print("ABORT: post-update sum does not match the backup — rolled back")
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
