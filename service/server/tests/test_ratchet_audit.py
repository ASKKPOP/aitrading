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


class ReduceStepTests(unittest.TestCase):
    """The reduce leg is the only moment the anchor decides anything."""

    def test_a_partial_exit_is_a_reduce(self):
        steps = ra.reduce_steps([
            {"side": "buy", "quantity": 1.32, "price": 4317.4, "ts": "a"},
            {"side": "sell", "quantity": 0.66, "price": 4314.1, "ts": "b"}])
        self.assertEqual(len(steps), 1)
        self.assertAlmostEqual(steps[0]["max_book_before"], 1.32, places=6)
        self.assertAlmostEqual(steps[0]["book_after"], 0.66, places=6)
        self.assertAlmostEqual(steps[0]["price"], 4314.1, places=4)

    def test_a_full_close_is_not_a_reduce(self):
        # Nothing is left for an arm to sit under.
        self.assertEqual(ra.reduce_steps([
            {"side": "buy", "quantity": 1.0, "price": 10.0, "ts": "a"},
            {"side": "sell", "quantity": 1.0, "price": 10.0, "ts": "b"}]), [])

    def test_the_forced_flatten_is_not_a_reduce(self):
        steps = ra.reduce_steps([
            {"side": "buy", "quantity": 2.0, "price": 10.0, "ts": "a"},
            {"side": "sell", "quantity": 0.5, "price": 10.0, "ts": "b",
             "client_order_id": "run:9:flatten"}])
        self.assertEqual(steps, [])

    def test_an_add_is_not_a_reduce(self):
        self.assertEqual(ra.reduce_steps([
            {"side": "buy", "quantity": 1.0, "price": 10.0, "ts": "a"},
            {"side": "buy", "quantity": 1.0, "price": 10.0, "ts": "b"}]), [])

    def test_shorts_reduce_by_covering(self):
        steps = ra.reduce_steps([
            {"side": "short", "quantity": 2.0, "price": 10.0, "ts": "a"},
            {"side": "cover", "quantity": 0.5, "price": 10.0, "ts": "b"}])
        self.assertEqual(len(steps), 1)
        self.assertAlmostEqual(steps[0]["book_after"], 1.5, places=6)


class BandTests(unittest.TestCase):
    """Runs 976 and 977 are the two live cases, and they must classify
    OPPOSITE ways — 977 looks superficially like a confirmation and is not."""

    def test_run_976_is_inside_the_band(self):
        cls = ra.classify_exposure(7.22, {
            "price": 4314.1, "max_book_before": 1.3166, "book_after": 0.6583})
        self.assertTrue(cls["in_band"])
        self.assertLess(cls["arm_after"], 7.22)
        self.assertGreater(cls["arm_full"], 7.22)

    def test_run_977_proves_nothing_because_its_peak_cleared_both_arms(self):
        cls = ra.classify_exposure(21.08, {
            "price": 4313.3, "max_book_before": 1.3187, "book_after": 0.6593})
        self.assertFalse(cls["in_band"])

    def test_a_peak_below_both_arms_proves_nothing_either(self):
        cls = ra.classify_exposure(0.5, {
            "price": 4314.1, "max_book_before": 1.3166, "book_after": 0.6583})
        self.assertFalse(cls["in_band"])

    def test_a_flat_book_after_never_bands(self):
        cls = ra.classify_exposure(50.0, {
            "price": 4314.1, "max_book_before": 1.3166, "book_after": 0.0})
        self.assertFalse(cls["in_band"])


class AuditExposureTests(AuditFiresTests):
    def _run_peak(self, run_id, peak):
        cur = self.conn.cursor()
        cur.execute("INSERT INTO trading_runs (id, agent_id, symbol, market, "
                    "status, peak_pnl_usd, created_at) VALUES (?, 1, 'GC', "
                    "'futures', 'stopped', ?, '2026-08-06T00:00:00Z')",
                    (run_id, peak))
        self.conn.commit()

    def _life(self, run_id, reduce_ts):
        self._ev(run_id, "trade", "2026-08-06T04:54:31Z",
                 {"side": "buy", "quantity": 1.3166, "price": 4317.4})
        self._ev(run_id, "trade", reduce_ts,
                 {"side": "sell", "quantity": 0.6583, "price": 4314.1})

    def test_a_post_fix_in_band_reduce_that_survived_is_the_evidence(self):
        self._run_peak(977, 7.22)
        self._life(977, "2026-08-06T07:12:00Z")
        rows = ra.audit_exposures("2026-08-01", conn=self.conn)
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["post_fix"])
        self.assertFalse(rows[0]["fired"])
        self.assertIn("1 survived", ra.format_exposures(rows))

    def test_a_pre_fix_in_band_reduce_that_flattened_is_the_defect(self):
        self._run_peak(976, 7.22)
        self._life(976, "2026-08-06T05:40:01Z")
        # 976's REAL timestamps: the fire lands the second AFTER the reduce.
        self._fire(976, "2026-08-06T05:40:02Z")
        rows = ra.audit_exposures("2026-08-01", conn=self.conn)
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0]["post_fix"])
        self.assertTrue(rows[0]["fired"])
        self.assertIn("FLATTENED", ra.format_exposures(rows))

    def test_out_of_band_reduces_are_not_counted_as_evidence(self):
        # 977's real peak. Both anchors arm, so the fix changed nothing.
        self._run_peak(977, 21.08)
        self._life(977, "2026-08-06T07:12:00Z")
        rows = ra.audit_exposures("2026-08-01", conn=self.conn)
        self.assertEqual(rows, [])
        self.assertIn("not yet been asked", ra.format_exposures(rows))

    def test_empty_band_says_so_rather_than_implying_the_fix_is_proven(self):
        self.assertIn("not yet been asked", ra.format_exposures([]))


class LiveTableDefectTests(AuditFiresTests):
    """Defects the first live run of the exposure table exposed, which its
    own unit tests had passed. Same lesson as _is_flatten: a monitoring tool
    carries the defects it hunts until real data is pointed at it."""

    def _run_peak(self, run_id, peak):
        cur = self.conn.cursor()
        cur.execute("INSERT INTO trading_runs (id, agent_id, symbol, market, "
                    "status, peak_pnl_usd, created_at) VALUES (?, 1, 'GC', "
                    "'futures', 'stopped', ?, '2026-08-06T00:00:00Z')",
                    (run_id, peak))
        self.conn.commit()

    def test_a_fire_one_second_after_the_reduce_is_the_same_event(self):
        # The first live table read 976 — the ONE case whose answer is known
        # — as "survived", because it matched fire to reduce on an exact
        # second. 976 reduced at 05:40:01 and was flattened at 05:40:02.
        self._run_peak(976, 7.22)
        self._ev(976, "trade", "2026-08-06T04:54:31Z",
                 {"side": "buy", "quantity": 1.3166, "price": 4317.4})
        self._ev(976, "trade", "2026-08-06T05:40:01Z",
                 {"side": "sell", "quantity": 0.6583, "price": 4314.1})
        self._fire(976, "2026-08-06T05:40:02Z")
        rows = ra.audit_exposures("2026-08-01", conn=self.conn)
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["fired"], "976 was flattened, not survived")

    def test_a_fire_hours_later_is_not_this_reduce(self):
        self._run_peak(973, 7.22)
        self._ev(973, "trade", "2026-08-06T02:00:00Z",
                 {"side": "buy", "quantity": 1.3166, "price": 4317.4})
        self._ev(973, "trade", "2026-08-06T02:10:00Z",
                 {"side": "sell", "quantity": 0.6583, "price": 4314.1})
        self._fire(973, "2026-08-06T04:12:00Z")
        rows = ra.audit_exposures("2026-08-01", conn=self.conn)
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0]["fired"])

    def test_reduces_from_before_the_ratchet_existed_are_not_judged(self):
        # The first live table judged eight 08-01/08-02 reduces against a
        # rail that did not exist until 08-06 01:45Z and called them all
        # "survived" — eight counts of evidence for nothing.
        self._run_peak(898, 1.49)
        self._ev(898, "trade", "2026-08-01T00:10:00Z",
                 {"side": "buy", "quantity": 1.3166, "price": 4317.4})
        self._ev(898, "trade", "2026-08-01T00:39:17Z",
                 {"side": "sell", "quantity": 1.3160, "price": 4314.1})
        self.assertEqual(ra.audit_exposures("2026-08-01", conn=self.conn), [])

    def test_a_sliver_arm_is_printed_with_enough_precision_to_read(self):
        rows = [{"run_id": 1, "reduced_at": "2026-08-06T02:00:00Z",
                 "arm_full": 1.70, "arm_after": 0.0042, "peak": 1.49,
                 "in_band": True, "post_fix": False, "fired": False}]
        self.assertIn("0.0042", ra.format_exposures(rows))
