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


def _make_db(fills, agents=(), runs=()):
    """fills: (id, agent_id, market, symbol, side, price, qty, pnl, fee,
    run_id, ts[, message_type]) — message_type defaults to 'operation'.
    agents: (id, cash). runs: (id, config_snapshot_json)."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE signals (
        id INTEGER PRIMARY KEY, agent_id INT, market TEXT, symbol TEXT,
        side TEXT, entry_price REAL, quantity REAL, pnl REAL,
        fee_usd REAL, run_id INT, timestamp INT,
        message_type TEXT NOT NULL DEFAULT 'operation')""")
    conn.executemany(
        "INSERT INTO signals (id, agent_id, market, symbol, side,"
        " entry_price, quantity, pnl, fee_usd, run_id, timestamp, message_type)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        [tuple(f) + ("operation",) if len(f) == 11 else tuple(f) for f in fills])
    conn.execute("CREATE TABLE agents (id INTEGER PRIMARY KEY, cash REAL)")
    conn.executemany("INSERT INTO agents (id, cash) VALUES (?,?)", agents)
    conn.execute("""CREATE TABLE trading_runs (
        id INTEGER PRIMARY KEY, config_snapshot_json TEXT)""")
    conn.executemany(
        "INSERT INTO trading_runs (id, config_snapshot_json) VALUES (?,?)", runs)
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


class NullPnlTests(unittest.TestCase):
    """D12(a): a NULL pnl on an exit with a replayable book is the same
    defect as a zeroed one — the old ``pnl IS NOT NULL`` filter hid it."""

    def test_null_pnl_with_material_expected_is_flagged(self):
        violations = _check([
            (1, 6, "crypto", "BTCUSDT", "buy", 100.0, 1.0, None, 0.10, 10, NOW),
            (2, 6, "crypto", "BTCUSDT", "sell", 110.0, 1.0, None, 0.10, 10, NOW),
        ])
        self.assertEqual(len(violations), 1)
        self.assertIsNone(violations[0]["pnl"])
        self.assertAlmostEqual(violations[0]["expected"], 9.90, places=6)

    def test_null_pnl_within_tolerance_passes(self):
        # Expected 0.04 — under the $0.05 line, NULL is not flagged.
        violations = _check([
            (1, 6, "crypto", "BTCUSDT", "buy", 100.0, 1.0, None, 0.0, 10, NOW),
            (2, 6, "crypto", "BTCUSDT", "sell", 100.04, 1.0, None, 0.0, 10, NOW),
        ])
        self.assertEqual(violations, [])

    def test_null_pnl_cover_is_flagged(self):
        violations = _check([
            (1, 6, "crypto", "SOLUSDT", "short", 50.0, 2.0, None, 0.10, 12, NOW),
            (2, 6, "crypto", "SOLUSDT", "cover", 45.0, 2.0, None, 0.09, 12, NOW),
        ])
        self.assertEqual(len(violations), 1)
        self.assertAlmostEqual(violations[0]["expected"], 9.91, places=6)


class MessageTypeTests(unittest.TestCase):
    """D12(b): only message_type='operation' rows are fills. A discussion
    row that happens to carry a side must neither corrupt the book nor be
    checked itself."""

    def test_non_operation_rows_do_not_corrupt_the_book(self):
        # The discussion 'buy' @999 would drag avg to 549.5 if replayed.
        violations = _check([
            (1, 6, "crypto", "BTCUSDT", "buy", 100.0, 1.0, None, 0.10, 10, NOW),
            (2, 6, "crypto", "BTCUSDT", "buy", 999.0, 1.0, None, 0.0, 10, NOW,
             "discussion"),
            (3, 6, "crypto", "BTCUSDT", "sell", 110.0, 1.0, 9.90, 0.10, 10, NOW),
        ])
        self.assertEqual(violations, [])

    def test_non_operation_exit_is_not_checked(self):
        violations = _check([
            (1, 6, "crypto", "BTCUSDT", "buy", 100.0, 1.0, None, 0.10, 10, NOW),
            (2, 6, "crypto", "BTCUSDT", "sell", 110.0, 1.0, -777.0, 0.10, 10,
             NOW, "discussion"),
        ])
        self.assertEqual(violations, [])


class ToleranceBoundaryTests(unittest.TestCase):
    """Q3(d): pin the $0.05 line from both sides (kills _TOLERANCE=1.0)."""

    def test_just_above_tolerance_fires(self):
        # Expected 9.90, recorded 9.84 → $0.06 of disagreement.
        violations = _check([
            (1, 6, "crypto", "BTCUSDT", "buy", 100.0, 1.0, None, 0.10, 10, NOW),
            (2, 6, "crypto", "BTCUSDT", "sell", 110.0, 1.0, 9.84, 0.10, 10, NOW),
        ])
        self.assertEqual(len(violations), 1)

    def test_just_below_tolerance_passes(self):
        # Expected 9.90, recorded 9.86 → $0.04 stays under the line.
        violations = _check([
            (1, 6, "crypto", "BTCUSDT", "buy", 100.0, 1.0, None, 0.10, 10, NOW),
            (2, 6, "crypto", "BTCUSDT", "sell", 110.0, 1.0, 9.86, 0.10, 10, NOW),
        ])
        self.assertEqual(violations, [])


class WindowUnitsTests(unittest.TestCase):
    """Q3(e): the window is HOURS (kills hours→minutes: 30h in a 48h
    window, out of a 24h one — *60 would put it out of both)."""

    def test_30h_old_exit_in_48h_window_out_of_24h(self):
        ts = NOW - 30 * 3600
        fills = [
            (1, 6, "crypto", "BTCUSDT", "buy", 100.0, 1.0, None, 0.10, 10, ts),
            (2, 6, "crypto", "BTCUSDT", "sell", 110.0, 1.0, 0.0, 0.10, 10, ts),
        ]
        self.assertEqual(len(_check(fills, hours=48)), 1)
        self.assertEqual(_check(fills, hours=24), [])


class PartialExitTests(unittest.TestCase):
    """Q3(f): entry → partial exit → re-buy → second exit, where the book
    average across the sequence decides the expected values (kills a
    book-corruption mutant — a sell that fails to decrement qty makes the
    re-buy average 123.33 instead of 120)."""

    def test_partial_exit_then_rebuy_sequence(self):
        violations = _check([
            # avg 110 across two buys
            (1, 6, "crypto", "ETHUSDT", "buy", 100.0, 1.0, None, 0.0, 11, NOW),
            (2, 6, "crypto", "ETHUSDT", "buy", 120.0, 1.0, None, 0.0, 11, NOW),
            # partial exit: (115-110)*1 = 5.00
            (3, 6, "crypto", "ETHUSDT", "sell", 115.0, 1.0, 5.0, 0.0, 11, NOW),
            # re-buy onto the 1-lot remainder: avg (110+130)/2 = 120
            (4, 6, "crypto", "ETHUSDT", "buy", 130.0, 1.0, None, 0.0, 11, NOW),
            # final exit: (125-120)*2 = 10.00
            (5, 6, "crypto", "ETHUSDT", "sell", 125.0, 2.0, 10.0, 0.0, 11, NOW),
        ])
        self.assertEqual(violations, [])

    def test_corrupted_second_exit_is_caught(self):
        # Same sequence with the second exit recorded against the WRONG
        # average (as if the partial exit never left the book).
        violations = _check([
            (1, 6, "crypto", "ETHUSDT", "buy", 100.0, 1.0, None, 0.0, 11, NOW),
            (2, 6, "crypto", "ETHUSDT", "buy", 120.0, 1.0, None, 0.0, 11, NOW),
            (3, 6, "crypto", "ETHUSDT", "sell", 115.0, 1.0, 5.0, 0.0, 11, NOW),
            (4, 6, "crypto", "ETHUSDT", "buy", 130.0, 1.0, None, 0.0, 11, NOW),
            (5, 6, "crypto", "ETHUSDT", "sell", 125.0, 2.0, 3.33, 0.0, 11, NOW),
        ])
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0]["signal_id"], 5)
        self.assertAlmostEqual(violations[0]["expected"], 10.0, places=6)


class CashResetTests(unittest.TestCase):
    """D12(c): the 08-26 incident's other half — cash restored to exactly
    starting_capital passes the row replay clean; only a snapshot-to-
    snapshot cash comparison against the window's fills can see it."""

    def _run(self, fills, agents, prev_state, runs=()):
        conn = _make_db(fills, agents=agents, runs=runs)
        saved = {}
        with patch.object(ledger_invariant, "get_db_connection",
                          return_value=_KeepOpen(conn)), \
             patch.object(ledger_invariant, "_load_cash_state",
                          return_value=prev_state), \
             patch.object(ledger_invariant, "_save_cash_state",
                          side_effect=lambda s: saved.update(s)):
            violations = ledger_invariant.check_cash_reset(now_ts=NOW)
        return violations, saved

    def test_first_run_stores_snapshot_only(self):
        violations, saved = self._run([], [(6, 1000.0)], prev_state=None)
        self.assertEqual(violations, [])
        self.assertEqual(saved["ts"], NOW)
        self.assertEqual(saved["cash"], {"6": 1000.0})

    def test_unchanged_cash_no_fills_is_clean(self):
        violations, _ = self._run(
            [], [(6, 1000.0)],
            {"ts": NOW - 3600, "cash": {"6": 1000.0}})
        self.assertEqual(violations, [])

    def test_cash_reset_with_no_fills_is_flagged(self):
        # Cash jumped 950 → 1000 (back to starting capital), zero fills.
        violations, _ = self._run(
            [], [(6, 1000.0)],
            {"ts": NOW - 3600, "cash": {"6": 950.0}})
        self.assertEqual(len(violations), 1)
        v = violations[0]
        self.assertEqual(v["agent_id"], 6)
        self.assertEqual(v["prev_cash"], 950.0)
        self.assertEqual(v["current_cash"], 1000.0)

    def test_buy_accounted_change_is_clean(self):
        # buy 1 @ 100 fee 0.10 → cash 1000 − 100.10 = 899.90.
        violations, _ = self._run(
            [(1, 6, "crypto", "BTCUSDT", "buy", 100.0, 1.0, None, 0.10, 10,
              NOW - 100)],
            [(6, 899.90)],
            {"ts": NOW - 3600, "cash": {"6": 1000.0}})
        self.assertEqual(violations, [])

    def test_sell_credit_with_out_of_window_entry_is_clean(self):
        # Entry predates the snapshot; the sell credits margin + P&L − fee:
        # 100×1 + (110−100)×1 − 0.11 = 109.89.
        old = NOW - 2 * 86400
        violations, _ = self._run(
            [(1, 6, "crypto", "BTCUSDT", "buy", 100.0, 1.0, None, 0.10, 10, old),
             (2, 6, "crypto", "BTCUSDT", "sell", 110.0, 1.0, 9.89, 0.11, 10,
              NOW - 100)],
            [(6, 1009.89)],
            {"ts": NOW - 3600, "cash": {"6": 900.0}})
        self.assertEqual(violations, [])

    def test_reset_alongside_real_fills_is_flagged(self):
        # Same window fill as the clean case, but cash reads 1000 — as if
        # someone restored starting capital after the trade.
        violations, _ = self._run(
            [(1, 6, "crypto", "BTCUSDT", "buy", 100.0, 1.0, None, 0.10, 10,
              NOW - 100)],
            [(6, 1000.0)],
            {"ts": NOW - 3600, "cash": {"6": 1000.0}})
        self.assertEqual(len(violations), 1)

    def test_leverage_from_run_config(self):
        # 5× leverage: margin = 500/5 = 100, +0.50 fee → cash 899.50.
        violations, _ = self._run(
            [(1, 6, "crypto", "BTCUSDT", "buy", 100.0, 5.0, None, 0.50, 10,
              NOW - 100)],
            [(6, 899.50)],
            {"ts": NOW - 3600, "cash": {"6": 1000.0}},
            runs=[(10, '{"leverage": 5}')])
        self.assertEqual(violations, [])

    def test_polymarket_window_fill_skips_agent(self):
        # Polymarket cash math doesn't follow the two-leg convention —
        # the agent is unverifiable this window, never flagged.
        violations, _ = self._run(
            [(1, 6, "polymarket", "x-yes", "buy", 0.5, 10.0, None, 0.0, None,
              NOW - 100)],
            [(6, 700.0)],
            {"ts": NOW - 3600, "cash": {"6": 1000.0}})
        self.assertEqual(violations, [])

    def test_short_cover_round_trip_is_clean(self):
        # short 2 @ 50 fee 0.10: cash −100.10; cover 2 @ 45 fee 0.09:
        # +100 + (50−45)×2 − 0.09 = +109.91 → net +9.81.
        violations, _ = self._run(
            [(1, 6, "crypto", "SOLUSDT", "short", 50.0, 2.0, None, 0.10, 12,
              NOW - 200),
             (2, 6, "crypto", "SOLUSDT", "cover", 45.0, 2.0, 9.91, 0.09, 12,
              NOW - 100)],
            [(6, 1009.81)],
            {"ts": NOW - 3600, "cash": {"6": 1000.0}})
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
             patch.object(ledger_invariant, "_load_cash_state",
                          return_value=None), \
             patch.object(ledger_invariant, "_save_cash_state"), \
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
             patch.object(ledger_invariant, "_load_cash_state",
                          return_value=None), \
             patch.object(ledger_invariant, "_save_cash_state"), \
             patch.object(trading_runs, "emit_telemetry_event") as emit, \
             patch.object(admin_alerts, "notify_admins") as notify:
            result = ledger_invariant.run_nightly_check()
        self.assertEqual(result["violations"], 0)
        self.assertEqual(result["cash_violations"], 0)
        emit.assert_not_called()
        notify.assert_not_called()

    def test_null_pnl_violation_renders_in_alert(self):
        # The alert line must not crash formatting a NULL pnl.
        import admin_alerts
        import trading_runs
        fills = [
            (1, 6, "crypto", "BTCUSDT", "buy", 100.0, 1.0, None, 0.10, 10, NOW),
            (2, 6, "crypto", "BTCUSDT", "sell", 110.0, 1.0, None, 0.10, 10, NOW),
        ]
        conn = _make_db(fills)
        with patch.object(ledger_invariant, "get_db_connection",
                          return_value=_KeepOpen(conn)), \
             patch.object(ledger_invariant, "_load_cash_state",
                          return_value=None), \
             patch.object(ledger_invariant, "_save_cash_state"), \
             patch.object(trading_runs, "emit_telemetry_event"), \
             patch.object(admin_alerts, "notify_admins") as notify:
            result = ledger_invariant.run_nightly_check()
        self.assertEqual(result["violations"], 1)
        self.assertIn("pnl=NULL", notify.call_args[0][1])

    def test_cash_reset_fires_its_own_alert(self):
        import admin_alerts
        import trading_runs
        conn = _make_db([], agents=[(6, 1000.0)])
        with patch.object(ledger_invariant, "get_db_connection",
                          return_value=_KeepOpen(conn)), \
             patch.object(ledger_invariant, "_load_cash_state",
                          return_value={"ts": NOW - 3600,
                                        "cash": {"6": 950.0}}), \
             patch.object(ledger_invariant, "_save_cash_state"), \
             patch.object(trading_runs, "emit_telemetry_event") as emit, \
             patch.object(admin_alerts, "notify_admins") as notify:
            result = ledger_invariant.run_nightly_check()
        self.assertEqual(result["violations"], 0)
        self.assertEqual(result["cash_violations"], 1)
        emit.assert_not_called()
        notify.assert_called_once()
        self.assertIn("agent 6", notify.call_args[0][1])


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
