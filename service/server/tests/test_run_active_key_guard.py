"""Active-key integrity guard (Plan 10).

`active_key` UNIQUE is what keeps one agent+market+symbol+filter_key to a
single active run — without it two runs with identical settings race the same
signal with two books. The key is only ever set by `start_run` and
only ever cleared on the way to `stopped`, so an active run holding a NULL
key means the row was written outside the state machine (a raw DB edit, a
half-applied migration, a backup restore). The engine used to trade on
regardless; these tests pin the guard that no longer lets it.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
import run_engine
import trading_runs


class ActiveKeyGuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO agents (id, name, token, cash, created_at) "
            "VALUES (1, 'guard', 'claw_guard', 100000, '2026-01-01T00:00:00Z')")
        conn.commit()
        conn.close()

    def tearDown(self):
        self.tmp.cleanup()

    # ── helpers ────────────────────────────────────────────────────────

    def _started_run(self, symbol: str = "BTC") -> int:
        run_id = trading_runs.create_run(
            1, {"symbol": symbol, "market": "crypto", "market_type": "spot",
                "max_bet_usd": 100.0},
            {"type": "manual"}, {}, True)
        trading_runs.start_run(run_id, 1)
        return run_id

    def _drop_key(self, run_id: int) -> None:
        """Reproduce the corrupt row: active but holding no key."""
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE trading_runs SET active_key = NULL WHERE id = ?",
                    (run_id,))
        conn.commit()
        conn.close()

    def _row(self, run_id: int) -> dict:
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM trading_runs WHERE id = ?", (run_id,))
        row = dict(cur.fetchone())
        conn.close()
        return row

    # ── the state is reachable and it is dangerous ─────────────────────

    def test_null_key_lets_a_second_run_start_on_the_same_tuple(self):
        """Why the guard exists: the UNIQUE index cannot fire against NULL."""
        first = self._started_run()
        self._drop_key(first)
        second = trading_runs.create_run(
            1, {"symbol": "BTC", "market": "crypto", "market_type": "spot",
                "max_bet_usd": 100.0},
            {"type": "manual"}, {}, True)
        trading_runs.start_run(second, 1)  # no collision — nothing to collide with
        self.assertEqual(self._row(first)["status"], trading_runs.STATUS_RUNNING)
        self.assertEqual(self._row(second)["status"], trading_runs.STATUS_RUNNING)

    # ── the guard ──────────────────────────────────────────────────────

    def test_control_pass_backfills_a_free_key(self):
        """The tuple is unclaimed: heal it and let the run keep trading."""
        run_id = self._started_run()
        self._drop_key(run_id)
        with patch.object(run_engine, "_evaluate_stop", return_value=None):
            out = run_engine.control_pass()
        row = self._row(run_id)
        # the key carries the run's filter digest now — runs that differ in
        # strategy shape share a symbol, so the tuple alone is not the identity
        self.assertEqual(row["active_key"],
                         trading_runs._active_key(1, "crypto", "BTC",
                                                  trading_runs.run_filter_key(row)))
        self.assertEqual(row["status"], trading_runs.STATUS_RUNNING)
        self.assertEqual(out["keys_healed"], 1)

    def test_control_pass_pauses_the_duplicate_it_cannot_heal(self):
        """The tuple is owned by another run: the keyless one must not trade."""
        keeper = self._started_run()
        self._drop_key(keeper)
        duplicate = self._started_run()  # takes 1:crypto:BTC for itself
        with patch.object(run_engine, "_evaluate_stop", return_value=None):
            out = run_engine.control_pass()
        stray = self._row(keeper)
        self.assertEqual(stray["status"], trading_runs.STATUS_PAUSED)
        self.assertEqual(stray["status_reason"], "duplicate_active_key")
        self.assertIsNone(stray["active_key"])
        self.assertEqual(self._row(duplicate)["status"],
                         trading_runs.STATUS_RUNNING)
        self.assertEqual(out["keys_conflicted"], 1)

    def test_armed_run_without_a_key_is_stopped_not_paused(self):
        """armed -> paused is not a legal transition; armed -> stopped is."""
        run_id = trading_runs.create_run(
            1, {"symbol": "ETH", "market": "crypto", "market_type": "spot",
                "max_bet_usd": 100.0},
            {"type": "at_time", "at": "2099-01-01T00:00:00Z"}, {}, True)
        trading_runs.start_run(run_id, 1)
        self.assertEqual(self._row(run_id)["status"], trading_runs.STATUS_ARMED)
        self._drop_key(run_id)
        blocker = trading_runs.create_run(
            1, {"symbol": "ETH", "market": "crypto", "market_type": "spot",
                "max_bet_usd": 100.0},
            {"type": "manual"}, {}, True)
        trading_runs.start_run(blocker, 1)  # takes 1:crypto:ETH
        run_engine.control_pass()
        self.assertEqual(self._row(run_id)["status"], trading_runs.STATUS_STOPPED)

    def test_healthy_runs_are_untouched(self):
        run_id = self._started_run()
        with patch.object(run_engine, "_evaluate_stop", return_value=None):
            out = run_engine.control_pass()
        row = self._row(run_id)
        self.assertEqual(row["active_key"],
                         trading_runs._active_key(1, "crypto", "BTC",
                                                  trading_runs.run_filter_key(row)))
        self.assertEqual(row["status"], trading_runs.STATUS_RUNNING)
        self.assertEqual(out["keys_healed"], 0)
        self.assertEqual(out["keys_conflicted"], 0)


if __name__ == "__main__":
    unittest.main()
