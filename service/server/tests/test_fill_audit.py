"""Fill-quality audit — how much was transacted against a stalled price.

Cycle 83: run 977 exited GC at 4320.700195, the exact price that symbol had
printed for 70+ minutes, and booked +1.65 against it. `trade` events carry
no notion of whether the price was live, so the day's realized P&L could not
be split into "earned" and "booked against a motionless tape".
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
import fill_audit as fa


class GapTests(unittest.TestCase):
    def test_gap_is_measured_in_seconds(self):
        self.assertEqual(
            fa.gap_seconds("2026-08-06T07:57:40Z", "2026-08-06T10:58:42Z"),
            3 * 3600 + 1 * 60 + 2)

    def test_a_day_boundary_returns_none_rather_than_a_wrong_number(self):
        self.assertIsNone(
            fa.gap_seconds("2026-08-05T23:59:00Z", "2026-08-06T00:01:00Z"))

    def test_junk_returns_none(self):
        self.assertIsNone(fa.gap_seconds("nonsense", "2026-08-06T00:01:00Z"))


class RepeatPriceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.conn = database.get_db_connection()
        self._seq = 0

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def _fill(self, run_id, ts, symbol, price, qty=1.0):
        self._seq += 1
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO run_events (run_id, seq, event_type, ts, payload) "
            "VALUES (?, ?, 'trade', ?, ?)",
            (run_id, self._seq, ts,
             json.dumps({"symbol": symbol, "price": price, "quantity": qty,
                         "side": "sell"})))
        self.conn.commit()

    def test_977s_real_shape_is_caught(self):
        # GC printed 4320.700195 at 07:57:40 and again at 10:58:42 — three
        # hours apart, identical to six decimals.
        self._fill(977, "2026-08-06T07:57:40Z", "GC", 4320.700195, 0.3297)
        self._fill(977, "2026-08-06T10:58:42Z", "GC", 4320.700195, 0.16483587)
        rows = fa.repeat_price_fills("2026-08-06", conn=self.conn)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["symbol"], "GC")
        self.assertEqual(rows[0]["gap_seconds"], 3 * 3600 + 62)
        self.assertAlmostEqual(rows[0]["notional"], 0.16483587 * 4320.700195,
                               places=4)

    def test_a_moving_tape_reports_nothing(self):
        self._fill(975, "2026-08-06T05:37:34Z", "BTCUSDT", 64870.0)
        self._fill(975, "2026-08-06T10:54:43Z", "BTCUSDT", 64584.0)
        self.assertEqual(fa.repeat_price_fills("2026-08-06", conn=self.conn), [])

    def test_two_fills_in_the_same_minute_are_a_quiet_market_not_a_freeze(self):
        self._fill(979, "2026-08-06T08:53:48Z", "SI", 62.099998)
        self._fill(979, "2026-08-06T08:54:26Z", "SI", 62.099998)
        self.assertEqual(fa.repeat_price_fills("2026-08-06", conn=self.conn), [])

    def test_the_same_price_on_a_DIFFERENT_symbol_is_not_a_repeat(self):
        self._fill(1, "2026-08-06T01:00:00Z", "AAA", 100.0)
        self._fill(2, "2026-08-06T05:00:00Z", "BBB", 100.0)
        self.assertEqual(fa.repeat_price_fills("2026-08-06", conn=self.conn), [])

    def test_every_later_repeat_is_counted_not_just_the_second(self):
        self._fill(9, "2026-08-06T01:00:00Z", "SI", 62.099998)
        self._fill(9, "2026-08-06T03:00:00Z", "SI", 62.099998)
        self._fill(9, "2026-08-06T05:00:00Z", "SI", 62.099998)
        self.assertEqual(len(fa.repeat_price_fills("2026-08-06", conn=self.conn)), 2)

    def test_garbage_payloads_are_skipped_not_fatal(self):
        self._seq += 1
        cur = self.conn.cursor()
        cur.execute("INSERT INTO run_events (run_id, seq, event_type, ts, "
                    "payload) VALUES (1, ?, 'trade', '2026-08-06T01:00:00Z', "
                    "'not json')", (self._seq,))
        self.conn.commit()
        self._fill(1, "2026-08-06T02:00:00Z", "GC", 4320.7)
        self._fill(1, "2026-08-06T05:00:00Z", "GC", 4320.7)
        self.assertEqual(len(fa.repeat_price_fills("2026-08-06", conn=self.conn)), 1)


class ReportTests(unittest.TestCase):
    ROW = {"run_id": 977, "symbol": "GC", "price": 4320.700195,
           "first_at": "2026-08-06T07:57:40Z", "repeat_at": "2026-08-06T10:58:42Z",
           "gap_seconds": 10862, "notional": 712.19}

    def test_a_clean_window_says_the_tape_was_moving(self):
        self.assertIn("the tape was moving", fa.format_report([]))

    def test_the_report_states_the_notional_and_owns_its_limits(self):
        out = fa.format_report([self.ROW])
        self.assertIn("712.19", out)
        self.assertIn("This is a FLOOR", out)
        self.assertIn("not proof of the true market price", out)


class ExitCodeTests(unittest.TestCase):
    """`main` must go non-zero on findings, like pnl_audit on drift — and it
    will therefore stay red until the feed is fixed. That is intended: a
    monitor that goes quiet on an ongoing fault is the failure this family of
    tools exists to stop."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.conn = database.get_db_connection()
        self._seq = 0

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def _fill(self, ts, price):
        self._seq += 1
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO run_events (run_id, seq, event_type, ts, payload) "
            "VALUES (7, ?, 'trade', ?, ?)",
            (self._seq, ts, json.dumps({"symbol": "GC", "price": price,
                                        "quantity": 1.0, "side": "sell"})))
        self.conn.commit()

    def test_a_clean_window_exits_zero(self):
        self._fill("2026-08-06T01:00:00Z", 4320.7)
        self._fill("2026-08-06T05:00:00Z", 4311.2)
        self.assertEqual(fa.main(["--since", "2026-08-06"]), 0)

    def test_a_repeat_price_fill_exits_non_zero(self):
        self._fill("2026-08-06T01:00:00Z", 4320.700195)
        self._fill("2026-08-06T05:00:00Z", 4320.700195)
        self.assertEqual(fa.main(["--since", "2026-08-06"]), 1)
