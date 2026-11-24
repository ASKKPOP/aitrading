"""Fleet position cap (owner 2026-11-23).

Owner, verbatim: "when we make fleet 5 by Full Auto, always keep 5 (active 3,
waiting 2), if one is finish, then that be retire and make one more".
Chosen reading: all N member TRADINGs run, but at most ceil(60% of N) may
hold a position at once; the rest WAIT flat until a spot frees. N=5 -> 3+2,
N=10 -> 6+4, N=3 -> 2+1. Retire-and-replace of a finished member is the
supervisor's existing perpetual-N loop and is unchanged.

Two callers, one rule:
  * run_engine._pre_gate_skip — a flat member of a full fleet skips its cycle
    before any LLM call (waiting costs nothing), and those cycles are not
    counted by the idle-retire rail.
  * automation.execute_paper_trade — the ledger check inside the trade
    transaction, with the fleet row locked (MySQL), so two members deciding
    in the same tick cannot both take the last spot, and every opening path
    (desk cycle, armed/resting order, entry router) is covered.

Only OPENS from flat are capped. A member already holding may add, and every
exit path is untouched. Kill switch: FLEET_POSITION_CAP_FRAC=0.
"""

from __future__ import annotations

import math
import os
from typing import Any, Optional

DEFAULT_FRAC = 0.6
SKIP_PREFIX = "fleet position cap"


def cap_frac() -> float:
    raw = (os.getenv("FLEET_POSITION_CAP_FRAC") or "").strip()
    if not raw:
        return DEFAULT_FRAC
    try:
        return float(raw)
    except ValueError:
        return DEFAULT_FRAC


def cap_for(n_runs: int) -> Optional[int]:
    """Members allowed in a position at once, or None when no cap applies
    (switched off, or the cap would not be below N)."""
    frac = cap_frac()
    n = int(n_runs or 0)
    if frac <= 0 or frac >= 1 or n <= 1:
        return None
    cap = max(1, math.ceil(n * frac))
    return cap if cap < n else None


def refusal(cursor: Any, run_id: int, fleet_id: int,
            lock: bool = False) -> Optional[str]:
    """Why run_id may not open a new position right now, or None."""
    from database import using_mysql
    mysql_lock = lock and using_mysql()
    for_update = " FOR UPDATE" if mysql_lock else ""
    # MySQL REPEATABLE READ: a plain SELECT reads the snapshot taken at the
    # transaction's first plain read — in execute_paper_trade that is BEFORE
    # this lock, so a member that committed the last spot meanwhile would be
    # invisible (reproduced on MySQL 8.0, 2026-11-24). Locking reads see the
    # latest committed rows.
    for_share = " FOR SHARE" if mysql_lock else ""
    cursor.execute("SELECT n_runs FROM fleets WHERE id = ?" + for_update,
                   (fleet_id,))
    row = cursor.fetchone()
    if not row:
        return None
    cap = cap_for(int(row["n_runs"] or 0))
    if cap is None:
        return None
    cursor.execute("SELECT 1 FROM positions WHERE run_id = ? AND quantity != 0 "
                   "LIMIT 1" + for_share, (run_id,))
    if cursor.fetchone():
        return None  # already holds a spot: adds are not a new spot
    cursor.execute(
        """SELECT COUNT(DISTINCT p.run_id) AS n FROM positions p
           JOIN trading_runs t ON t.id = p.run_id
           WHERE t.fleet_id = ? AND p.quantity != 0""" + for_share, (fleet_id,))
    holding = int((cursor.fetchone() or {"n": 0})["n"] or 0)
    if holding >= cap:
        return (f"{SKIP_PREFIX}: {holding}/{cap} TRADINGs already hold a "
                "position — waiting for a free spot")
    return None
