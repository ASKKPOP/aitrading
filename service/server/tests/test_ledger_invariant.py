"""Plan 31 item 1 — ledger invariant tests.

The invariant exists because the agent-6 reset zeroed 102 exit rows and
nothing noticed for three days. These tests seed a ledger, break it the
same two ways (zeroed pnl, wrong pnl), and prove the sweep fires — plus
the sign conventions, the averaging replay, the window, and the wiring
(an unregistered background loop is a silent no-op — the standing lesson).
"""

from __future__ import annotations

import inspect
import os
import sqlite3
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import ledger_invariant


NOW = int(time.time())


class _KeepOpen:
    """check_exit_rows closes what it opens; the fixture must outlive that."""

    def __init__(self, inner):
        self._inner = inner

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def close(self):
        return None


def _make_db(fills):
    """fills: (id, agent_id, market, symbol, side, price, qty, pnl, fee, run_id, ts)."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE signals (
        id INTEGER PRIMARY KEY, agent_id INT, market TEXT, symbol TEXT,
        side TEXT, entry_price REAL, quantity REAL, pnl REAL,
        fee_usd REAL, run_id INT, timestamp INT)""")
    conn.executemany(
        "INSERT INTO signals (id, agent_id, market, symbol, side,"
        " entry_price, quantity, pnl, fee_usd, run_id, timestamp)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?)", fills)
    conn.commit()
    return conn


def _check(fills, hours=None):
    conn = _make_db(fills)
    with patch.object(ledger_invariant, "get_db_connection",
                      return_value=_KeepOpen(conn)):
        return ledger_invariant.check_exit_rows(hours)


class LongTripTests(unittest.TestCase):
    def test_clean_long_trip_passes(self):
        # buy 1 @ 100, sell 1 @ 110 fee 0.10 → pnl (110-100)*1 - 0.10 = 9.90
        violations = _check([
            (1, 6, "crypto", "BTCUSDT", "buy", 100.0, 1.0, None, 0.10, 10, NOW),
            (2, 6, "crypto", "BTCUSDT", "sell", 110.0, 1.0, 9.90, 0.10, 10, NOW),
        ])
        self.assertEqual(violations, [])

    def test_zeroed_pnl_is_caught(self):
        # The agent-6 reset fingerprint: real trade, pnl overwritten to 0.
        violations = _check([
            (1, 6, "crypto", "BTCUSDT", "buy", 100.0, 1.0, None, 0.10, 10, NOW),
            (2, 6, "crypto", "BTCUSDT", "sell", 110.0, 1.0, 0.0, 0.10, 10, NOW),
        ])
        self.assertEqual(len(violations), 1)
        v = violations[0]
        self.assertEqual(v["signal_id"], 2)
        self.assertEqual(v["agent_id"], 6)
        self.assertEqual(v["run_id"], 10)
        self.assertEqual(v["pnl"], 0.0)
        self.assertAlmostEqual(v["expected"], 9.90, places=6)

    def test_wrong_value_is_caught(self):
        violations = _check([
            (1, 6, "crypto", "BTCUSDT", "buy", 100.0, 1.0, None, 0.10, 10, NOW),
            (2, 6, "crypto", "BTCUSDT", "sell", 110.0, 1.0, 5.0, 0.10, 10, NOW),
        ])
        self.assertEqual(len(violations), 1)
        self.assertAlmostEqual(violations[0]["expected"], 9.90, places=6)

    def test_within_tolerance_passes(self):
        # $0.03 of disagreement stays under the $0.05 line.
        violations = _check([
            (1, 6, "crypto", "BTCUSDT", "buy", 100.0, 1.0, None, 0.10, 10, NOW),
            (2, 6, "crypto", "BTCUSDT", "sell", 110.0, 1.0, 9.87, 0.10, 10, NOW),
        ])
        self.assertEqual(violations, [])

    def test_averaged_adds_replay(self):
        # buy 1 @ 100 + buy 1 @ 110 → avg 105; sell 2 @ 110 → 10.00 - fee
        violations = _check([
            (1, 6, "crypto", "ETHUSDT", "buy", 100.0, 1.0, None, 0.0, 11, NOW),
            (2, 6, "crypto", "ETHUSDT", "buy", 110.0, 1.0, None, 0.0, 11, NOW),
            (3, 6, "crypto", "ETHUSDT", "sell", 110.0, 2.0, 9.90, 0.10, 11, NOW),
        ])
        self.assertEqual(violations, [])


class ShortTripTests(unittest.TestCase):
    def test_clean_short_cover_passes(self):
        # short 2 @ 50, cover 2 @ 45 fee 0.09 → (50-45)*2 - 0.09 = 9.91
        violations = _check([
            (1, 6, "crypto", "SOLUSDT", "short", 50.0, 2.0, None, 0.10, 12, NOW),
            (2, 6, "crypto", "SOLUSDT", "cover", 45.0, 2.0, 9.91, 0.09, 12, NOW),
        ])
        self.assertEqual(violations, [])

    def test_cover_sign_flip_is_caught(self):
        # The convention error this test pins: (exit-entry) on a short
        # would record −9.91 where (entry-exit) says +9.91.
        violations = _check([
            (1, 6, "crypto", "SOLUSDT", "short", 50.0, 2.0, None, 0.10, 12, NOW),
            (2, 6, "crypto", "SOLUSDT", "cover", 45.0, 2.0, -9.91, 0.09, 12, NOW),
        ])
        self.assertEqual(len(violations), 1)
        self.assertAlmostEqual(violations[0]["expected"], 9.91, places=6)


class ScopeTests(unittest.TestCase):
    def test_window_excludes_old_exits(self):
        # A broken exit 3 days back: invisible at 24h, visible all-time.
        old = NOW - 3 * 86400
        fills = [
            (1, 6, "crypto", "BTCUSDT", "buy", 100.0, 1.0, None, 0.10, 10, old),
            (2, 6, "crypto", "BTCUSDT", "sell", 110.0, 1.0, 0.0, 0.10, 10, old),
        ]
        self.assertEqual(_check(fills, hours=24), [])
        self.assertEqual(len(_check(fills, hours=None)), 1)

    def test_out_of_window_entries_still_replay(self):
        # Entry legs older than the window must still anchor the book.
        old = NOW - 3 * 86400
        violations = _check([
            (1, 6, "crypto", "BTCUSDT", "buy", 100.0, 1.0, None, 0.10, 10, old),
            (2, 6, "crypto", "BTCUSDT", "sell", 110.0, 1.0, 9.90, 0.10, 10, NOW),
        ], hours=24)
        self.assertEqual(violations, [])

    def test_unverifiable_exit_is_skipped_not_flagged(self):
        # An exit with no replayable book (entries predate retention) must
        # never fire the alarm.
        violations = _check([
            (2, 6, "crypto", "BTCUSDT", "sell", 110.0, 1.0, 42.0, 0.10, 10, NOW),
        ])
        self.assertEqual(violations, [])

    def test_polymarket_is_excluded(self):
        violations = _check([
            (1, 6, "polymarket", "x-yes", "buy", 0.5, 10.0, None, 0.0, None, NOW),
            (2, 6, "polymarket", "x-yes", "sell", 0.9, 10.0, 0.0, 0.0, None, NOW),
        ])
        self.assertEqual(violations, [])

    def test_books_keyed_by_run(self):
        # Two runs on one symbol must not average into a shared book.
        violations = _check([
            (1, 6, "crypto", "BTCUSDT", "buy", 100.0, 1.0, None, 0.0, 10, NOW),
            (2, 6, "crypto", "BTCUSDT", "buy", 200.0, 1.0, None, 0.0, 20, NOW),
            (3, 6, "crypto", "BTCUSDT", "sell", 110.0, 1.0, 10.0, 0.0, 10, NOW),
            (4, 6, "crypto", "BTCUSDT", "sell", 210.0, 1.0, 10.0, 0.0, 20, NOW),
        ])
        self.assertEqual(violations, [])


class NightlySweepTests(unittest.TestCase):
    def _fills(self):
        return [
            (1, 6, "crypto", "BTCUSDT", "buy", 100.0, 1.0, None, 0.10, 10, NOW),
            (2, 6, "crypto", "BTCUSDT", "sell", 110.0, 1.0, 0.0, 0.10, 10, NOW),
        ]

    def test_violations_emit_telemetry_and_admin_alert(self):
        import admin_alerts
        import trading_runs
        conn = _make_db(self._fills())
        with patch.object(ledger_invariant, "get_db_connection",
                          return_value=_KeepOpen(conn)), \
             patch.object(trading_runs, "emit_telemetry_event") as emit, \
             patch.object(admin_alerts, "notify_admins") as notify:
            result = ledger_invariant.run_nightly_check()
        self.assertEqual(result["violations"], 1)
        emit.assert_called_once()
        self.assertEqual(emit.call_args[0][0], 10)
        self.assertEqual(emit.call_args[0][1], "ledger_invariant_violation")
        notify.assert_called_once()
        self.assertIn("signal 2", notify.call_args[0][1])

    def test_clean_ledger_stays_silent(self):
        import admin_alerts
        import trading_runs
        fills = [
            (1, 6, "crypto", "BTCUSDT", "buy", 100.0, 1.0, None, 0.10, 10, NOW),
            (2, 6, "crypto", "BTCUSDT", "sell", 110.0, 1.0, 9.90, 0.10, 10, NOW),
        ]
        conn = _make_db(fills)
        with patch.object(ledger_invariant, "get_db_connection",
                          return_value=_KeepOpen(conn)), \
             patch.object(trading_runs, "emit_telemetry_event") as emit, \
             patch.object(admin_alerts, "notify_admins") as notify:
            result = ledger_invariant.run_nightly_check()
        self.assertEqual(result["violations"], 0)
        emit.assert_not_called()
        notify.assert_not_called()


class KillSwitchTests(unittest.TestCase):
    def tearDown(self):
        os.environ.pop("LEDGER_INVARIANT_ENABLED", None)

    def test_default_on(self):
        os.environ.pop("LEDGER_INVARIANT_ENABLED", None)
        self.assertTrue(ledger_invariant.ledger_invariant_enabled())

    def test_kill_switch(self):
        os.environ["LEDGER_INVARIANT_ENABLED"] = "0"
        self.assertFalse(ledger_invariant.ledger_invariant_enabled())


class WiringTests(unittest.TestCase):
    """A loop that never calls the checker, or is never registered, is a
    silent no-op."""

    def test_loop_calls_checker_behind_kill_switch(self):
        import tasks
        src = inspect.getsource(tasks.ledger_invariant_loop)
        self.assertIn("run_nightly_check", src)
        self.assertIn("ledger_invariant_enabled", src)

    def test_registered_with_research_role(self):
        import tasks
        self.assertIn("ledger_invariant", tasks.BACKGROUND_TASK_REGISTRY)
        self.assertEqual(tasks.BACKGROUND_TASK_ROLES["ledger_invariant"],
                         "research")


if __name__ == "__main__":
    unittest.main()
