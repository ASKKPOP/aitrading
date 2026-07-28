"""Idle-retire must not count closed-market cycles (2026-07-28).

cycle_seq increments when a cycle is CLAIMED, before _pre_gate_skip runs, so a
run parked on a shut market still burns a cycle every tick. The idle-retire
rail then collects it for "never traded".

Live: runs 127 (ORCL) and 128 (CAT) were built at 19:56:40 UTC — 3m20s before
the US close — spent twelve cycles on `pre: market closed`, and were
idle-retired at 04:27, nine hours before the market reopened. They never had
one open session to trade in.

The rail's own premise is that a never-trading run "is burning a multi-agent
analysis per tick for nothing". That is false for these cycles: a pre-gate
skip returns before any analysis is requested and costs nothing.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
import run_engine


def _run(cycle_seq, run_id=127):
    return {"id": run_id, "agent_id": 6, "symbol": "ORCL", "market": "us-stock",
            "status": "running", "cycle_seq": cycle_seq,
            "config_snapshot_json": json.dumps(
                {"symbol": "ORCL", "market": "us-stock",
                 "thesis": {"expected_move_pct": 5.0}}),
            "stop_conditions_json": "{}"}


class ClosedMarketCounting(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "t.db")
        database.init_database()
        self._env = os.environ.get("RUN_IDLE_RETIRE_CYCLES")
        os.environ["RUN_IDLE_RETIRE_CYCLES"] = "12"

    def tearDown(self):
        self.tmp.cleanup()
        if self._env is None:
            os.environ.pop("RUN_IDLE_RETIRE_CYCLES", None)
        else:
            os.environ["RUN_IDLE_RETIRE_CYCLES"] = self._env

    _seq = 0

    def _skips(self, run_id, n, stage="pre", reason="market closed"):
        conn = database.get_db_connection()
        cur = conn.cursor()
        for i in range(n):
            ClosedMarketCounting._seq += 1          # unique per row, per test
            s = ClosedMarketCounting._seq
            cur.execute(
                "INSERT INTO run_events (run_id, seq, event_type, ts, payload) "
                "VALUES (?, ?, 'gate_skip', ?, ?)",
                (run_id, s, f"2026-07-28T0{i % 10}:00:00Z",
                 json.dumps({"cycle": i + 1, "stage": stage, "reason": reason})))
        conn.commit()
        conn.close()

    def _evaluate(self, run):
        pnl = {"total": 0.0, "realized": 0.0, "trades": 0,
               "mark_age_ok": True, "position": None}
        with patch.object(run_engine, "compute_run_pnl", return_value=pnl):
            return run_engine._evaluate_stop(run)

    def test_counts_closed_market_skips(self):
        self._skips(127, 12)
        self.assertEqual(run_engine._closed_market_cycles(127), 12)

    def test_ignores_other_skip_stages(self):
        self._skips(127, 4, stage="risk", reason="decision is 'hold'")
        self._skips(127, 3)
        self.assertEqual(run_engine._closed_market_cycles(127), 3)

    def test_only_the_pre_stage_counts(self):
        """The stage filter must do real work, not lean on the reason text.

        Only `pre` returns before any analysis is requested — that is the whole
        justification for discounting the cycle. A later stage mentioning a
        closed market has already spent the tick and must still count.
        """
        self._skips(127, 5, stage="risk", reason="market closed downstream")
        self.assertEqual(run_engine._closed_market_cycles(127), 0)
        self._skips(127, 2)
        self.assertEqual(run_engine._closed_market_cycles(127), 2)

    def test_the_orcl_case_is_not_retired(self):
        """12 cycles, every one market-closed — the exact live shape."""
        self._skips(127, 12)
        self.assertIsNone(self._evaluate(_run(12)),
                          "a run that never saw an open market must not be "
                          "retired for never trading")

    def test_a_genuinely_idle_run_is_still_retired(self):
        """The rail must keep working for runs that COULD have traded."""
        self._skips(127, 0)
        self.assertEqual(self._evaluate(_run(12)), "idle_retired")

    def test_mixed_counts_only_the_workable_cycles(self):
        """20 cycles, 9 of them closed -> 11 workable, still under the 12 limit."""
        self._skips(127, 9)
        self.assertIsNone(self._evaluate(_run(20)))

    def test_mixed_retires_once_workable_cycles_reach_the_limit(self):
        self._skips(127, 9)
        self.assertEqual(self._evaluate(_run(21)), "idle_retired")

    def test_unreadable_journal_falls_back_to_old_behaviour(self):
        """Fail-soft: a broken read must not make runs un-retirable."""
        with patch.object(run_engine, "get_db_connection",
                          side_effect=RuntimeError("db down")):
            self.assertEqual(run_engine._closed_market_cycles(127), 0)


if __name__ == "__main__":
    unittest.main()
