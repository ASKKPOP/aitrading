"""Ratchet-fire audit — the retro-arm watch, automated.

PR #251 anchored the breakeven arm to the largest book a run ever held. The
forward evidence was n=0 and proving it depended on hand-auditing every
future fire — the same manual arrangement that let the original defect kill
two runs. These tests pin the detector that replaces the manual watch.
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
import ratchet_audit as ra


def _t(side, qty, ts):
    return {"side": side, "quantity": qty, "ts": ts}


class BookSizeTests(unittest.TestCase):
    def test_reduce_shrinks_the_book_but_not_the_peak(self):
        # 976's exact shape: full book, then the desk's own reduce.
        trades = [_t("buy", 1.32, "2026-08-06T04:00:00Z"),
                  _t("sell", 0.66, "2026-08-06T05:39:00Z")]
        peak, at_fire = ra.book_sizes(trades, until_ts="2026-08-06T05:40:02Z")
        self.assertAlmostEqual(peak, 1.32, places=6)
        self.assertAlmostEqual(at_fire, 0.66, places=6)

    def test_short_book_is_measured_by_absolute_size(self):
        trades = [_t("short", 2.0, "2026-08-06T01:00:00Z"),
                  _t("cover", 0.5, "2026-08-06T02:00:00Z")]
        peak, at_fire = ra.book_sizes(trades, until_ts="2026-08-06T03:00:00Z")
        self.assertAlmostEqual(peak, 2.0, places=6)
        self.assertAlmostEqual(at_fire, 1.5, places=6)

    def test_trades_after_the_fire_do_not_change_the_book_at_fire(self):
        # The flatten leg lands in the same second as the fire; it must not
        # be counted as "the book at the fire" or every fire looks flat.
        trades = [_t("buy", 4.0, "2026-08-06T01:00:00Z"),
                  _t("sell", 4.0, "2026-08-06T09:00:00Z")]
        peak, at_fire = ra.book_sizes(trades, until_ts="2026-08-06T05:00:00Z")
        self.assertAlmostEqual(peak, 4.0, places=6)
        self.assertAlmostEqual(at_fire, 4.0, places=6)

    def test_garbage_legs_are_skipped_not_fatal(self):
        trades = [{"side": "buy", "quantity": "oops", "ts": "x"},
                  _t("buy", 1.0, "2026-08-06T01:00:00Z")]
        peak, at_fire = ra.book_sizes(trades, until_ts="2026-08-06T02:00:00Z")
        self.assertAlmostEqual(peak, 1.0, places=6)


class LiveDataDefectTests(unittest.TestCase):
    """Both caught by running the first draft against live prod, not by the
    unit tests — which is why this class exists."""

    def test_the_fires_own_flatten_leg_is_not_the_book_before_the_fire(self):
        # The flatten is journalled with the SAME ts as the fire. Counting
        # it made 15 of 16 historical fires read as a flat -> "shrunken"
        # book, which post-fix would fire a false REGRESSION on the first
        # genuine full-book fire.
        trades = [
            {"side": "buy", "quantity": 1.32, "ts": "2026-08-06T05:00:00Z",
             "client_order_id": "run:976:cyc:1"},
            {"side": "sell", "quantity": 1.32, "ts": "2026-08-06T05:40:02Z",
             "client_order_id": "run:976:flatten"},
        ]
        peak, at_fire = ra.book_sizes(trades, until_ts="2026-08-06T05:40:02Z")
        self.assertAlmostEqual(peak, 1.32, places=6)
        self.assertAlmostEqual(at_fire, 1.32, places=6,
                               msg="the fire's own liquidation must not "
                                   "count as the book that preceded it")

    def test_a_desk_reduce_in_the_same_second_still_counts(self):
        # The retro-arm signature itself: the desk's own reduce lands in the
        # same second and MUST shrink the book, unlike the flatten.
        trades = [
            {"side": "buy", "quantity": 1.32, "ts": "2026-08-06T05:00:00Z",
             "client_order_id": "run:976:cyc:1"},
            {"side": "sell", "quantity": 0.66, "ts": "2026-08-06T05:40:02Z",
             "client_order_id": "run:976:cyc:2"},
        ]
        peak, at_fire = ra.book_sizes(trades, until_ts="2026-08-06T05:40:02Z")
        self.assertAlmostEqual(at_fire, 0.66, places=6)


class AuditFiresTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.conn = database.get_db_connection()
        cur = self.conn.cursor()
        cur.execute("INSERT INTO users (id, email, password_hash, created_at) "
                    "VALUES (1, 'r@x.com', 'x', '2026-01-01T00:00:00Z')")
        cur.execute("INSERT INTO agents (id, name, token_hash, cash, user_id, "
                    "created_at) VALUES (1, 'ra', 'th', 1000, 1, "
                    "'2026-01-01T00:00:00Z')")
        self.conn.commit()
        self._seq = 0

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def _run(self, run_id):
        cur = self.conn.cursor()
        cur.execute("INSERT INTO trading_runs (id, agent_id, symbol, market, "
                    "status, created_at) VALUES (?, 1, 'GC', 'futures', "
                    "'stopped', '2026-08-06T00:00:00Z')", (run_id,))
        self.conn.commit()

    def _ev(self, run_id, etype, ts, payload):
        self._seq += 1
        cur = self.conn.cursor()
        cur.execute("INSERT INTO run_events (run_id, seq, event_type, ts, "
                    "payload) VALUES (?, ?, ?, ?, ?)",
                    (run_id, self._seq, etype, ts, json.dumps(payload)))
        self.conn.commit()

    def _fire(self, run_id, ts):
        self._ev(run_id, "run_status", ts,
                 {"from": "running", "to": "stopping",
                  "reason": "stop_event:trailing_lock"})

    def test_post_fix_shrunken_book_is_flagged_for_review_and_exits_nonzero(self):
        self._run(976)
        self._ev(976, "trade", "2026-08-06T07:00:00Z",
                 {"side": "buy", "quantity": 1.32, "price": 4310.0})
        self._ev(976, "trade", "2026-08-06T07:59:00Z",
                 {"side": "sell", "quantity": 0.66, "price": 4313.0})
        self._fire(976, "2026-08-06T08:00:00Z")
        rows = ra.audit_fires("2026-08-06", conn=self.conn)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["verdict"], "shrunken")
        self.assertTrue(rows[0]["post_fix"])
        self.assertTrue(rows[0]["needs_review"])
        self.assertIn("REVIEW", ra.format_report(rows))
        self.assertIn("CANDIDATE retro-arm, not proof",
                      ra.format_report(rows))

    def test_pre_fix_shrunken_book_is_reported_but_not_a_regression(self):
        self._run(973)
        self._ev(973, "trade", "2026-08-06T00:00:00Z",
                 {"side": "buy", "quantity": 22.24, "price": 100.0})
        self._ev(973, "trade", "2026-08-06T00:20:00Z",
                 {"side": "sell", "quantity": 11.12, "price": 101.0})
        self._fire(973, "2026-08-06T00:21:23Z")
        rows = ra.audit_fires("2026-08-06", conn=self.conn)
        self.assertEqual(rows[0]["verdict"], "shrunken")
        self.assertFalse(rows[0]["post_fix"])
        self.assertFalse(rows[0]["needs_review"],
                         "a pre-fix fire is never flagged")

    def test_a_stop_emits_two_status_rows_but_counts_as_one_fire(self):
        # running->stopping and stopping->stopped BOTH mention "stopping";
        # matching loosely double-counted every fire on live data.
        self._run(981)
        self._ev(981, "trade", "2026-08-06T07:00:00Z",
                 {"side": "buy", "quantity": 2.0, "price": 10.0})
        self._fire(981, "2026-08-06T08:00:00Z")
        self._ev(981, "run_status", "2026-08-06T08:00:01Z",
                 {"from": "stopping", "to": "stopped",
                  "reason": "stop_event:trailing_lock"})
        rows = ra.audit_fires("2026-08-06", conn=self.conn)
        self.assertEqual(len(rows), 1, "one stop must be one audited fire")

    def test_post_fix_full_book_fire_is_clean(self):
        self._run(980)
        self._ev(980, "trade", "2026-08-06T07:00:00Z",
                 {"side": "buy", "quantity": 3.0, "price": 50.0})
        self._fire(980, "2026-08-06T08:00:00Z")
        rows = ra.audit_fires("2026-08-06", conn=self.conn)
        self.assertEqual(rows[0]["verdict"], "full-book")
        self.assertFalse(rows[0]["needs_review"])
        self.assertIn("anchor holding", ra.format_report(rows))

    def test_empty_post_fix_sample_says_so_rather_than_claiming_success(self):
        self._run(973)
        self._ev(973, "trade", "2026-08-06T00:00:00Z",
                 {"side": "buy", "quantity": 5.0, "price": 10.0})
        self._fire(973, "2026-08-06T00:21:23Z")
        report = ra.format_report(ra.audit_fires("2026-08-06", conn=self.conn))
        self.assertIn("post-fix sample is EMPTY", report)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
