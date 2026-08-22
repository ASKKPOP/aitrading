"""The desk's own excursion record — what its book has ACTUALLY reached.

Measured on prod 2026-08-18 across 66 closed runs that opened a position:
42% never had a positive moment at all, and among those that did the best
moment was median 0.17% of notional with an all-time best of 0.97%. The desk
authors targets with a median of 4.80% and is told to pick "a level the move
can realistically reach" — with no data about what its own book has ever
reached. Every downstream consumer (the R:R floor, sizing, outlook target_px)
then runs on that number.
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database  # noqa: E402
import desk_record  # noqa: E402


class ExcursionRecordTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "x.db")
        database.init_database()
        desk_record._CACHE.clear()

    def tearDown(self):
        desk_record._CACHE.clear()
        self.tmp.cleanup()

    def _run(self, rid, market, peak, notional, status="stopped"):
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO trading_runs (id, agent_id, symbol, market, status, "
            "peak_pnl_usd, created_at) VALUES (?,?,?,?,?,?,?)",
            (rid, 1, "X", market, status, peak, "2026-08-18T00:00:00Z"))
        if notional:
            cur.execute(
                "INSERT INTO run_events (run_id, seq, event_type, ts, payload) "
                "VALUES (?,?,?,?,?)",
                (rid, 1, "trade", "2026-08-18T00:00:00Z",
                 '{"side": "buy", "quantity": 1, "price": %s}' % notional))
        conn.commit()
        conn.close()

    def test_it_reports_the_best_moment_as_a_percentage_of_notional(self):
        """pnl/notional IS the % price move: pnl = move x qty, notional =
        price x qty. Any other unit cannot be compared to `target_pct`."""
        for i in range(12):
            self._run(100 + i, "crypto", 1.0, 100.0)      # 1.0/100 = 1.00%
        rec = desk_record.excursion_record("crypto")
        self.assertEqual(rec["n"], 12)
        self.assertAlmostEqual(rec["best"], 1.0, places=4)
        self.assertAlmostEqual(rec["median"], 1.0, places=4)

    def test_a_run_that_never_went_positive_is_counted_not_dropped(self):
        """42% of the live book never had a positive moment. Dropping them
        would report the record of the survivors and flatter the desk."""
        for i in range(6):
            self._run(200 + i, "forex", -0.5, 100.0)
        for i in range(6):
            self._run(300 + i, "forex", 0.4, 100.0)
        rec = desk_record.excursion_record("forex")
        self.assertEqual(rec["n"], 12)
        self.assertAlmostEqual(rec["never_positive"], 0.5, places=3)

    def test_a_thin_book_reports_nothing_rather_than_a_number(self):
        """A record built on 3 runs is noise wearing a decimal point."""
        for i in range(3):
            self._run(400 + i, "futures", 1.0, 100.0)
        self.assertIsNone(desk_record.excursion_record("futures"))
        self.assertEqual(desk_record.record_line("futures"), "")

    def test_runs_that_never_opened_a_position_are_excluded(self):
        """A run with no trade has no notional, so its peak has no scale."""
        for i in range(12):
            self._run(500 + i, "us-stock", 1.0, 100.0)
        for i in range(9):
            self._run(600 + i, "us-stock", 5.0, None)
        rec = desk_record.excursion_record("us-stock")
        self.assertEqual(rec["n"], 12, "a run with no fill was given a scale")

    def test_open_runs_are_excluded(self):
        for i in range(12):
            self._run(700 + i, "crypto", 1.0, 100.0)
        for i in range(12):
            self._run(800 + i, "crypto", 9.0, 100.0, status="running")
        rec = desk_record.excursion_record("crypto")
        self.assertEqual(rec["n"], 12)
        self.assertAlmostEqual(
            rec["best"], 1.0, 4,
            "a LIVE run's peak is not a record — it has not finished "
            "giving it back")

    def test_the_line_refuses_to_imply_a_tighter_bracket(self):
        """MEASURED REFUTATION 2026-08-18. The reachability figure alone
        invites exactly one wrong inference — "my target is unreachable, so
        shrink it" — and the 2x R:R floor then drags the stop to ~0.5%.
        Replayed on 22 crypto entries against their own at_time horizons, that
        is the WORST band on the board: stop 0.6/target 1.2 loses 0.34%/trade
        with the stop hit first in 15 of 22, while expectancy improves
        monotonically as stops WIDEN.

        Unreachable targets and tight stops are the same market fact. The line
        must carry both halves or it argues for a band the tape refutes."""
        for i in range(12):
            self._run(1200 + i, "us-stock", 1.0, 100.0)
        line = desk_record.record_line("us-stock")
        self.assertIn("tighter", line.lower(),
                      "the desk can still infer 'shrink the bracket'")
        self.assertIn("stop", line.lower(),
                      "the line never mentions what tightening does to the "
                      "stop, which is where the loss actually lands")

    def test_the_line_states_n_and_the_ceiling(self):
        for i in range(12):
            self._run(900 + i, "us-stock", 1.0, 100.0)
        line = desk_record.record_line("us-stock")
        self.assertIn("n=12", line)
        self.assertIn("1.00%", line)
        self.assertIn("us-stock", line)

    def test_crypto_is_silent_by_measurement(self):
        """Measured 2026-08-22 (docs/research/06): after this line shipped,
        the panel's crypto demotions replayed to +$145 net over 8 days,
        positive even with the largest winner stripped — in crypto the
        disclosure suppressed entries that would have paid. The record data
        stays available (excursion_record); only the prompt line is silent."""
        for i in range(12):
            self._run(1300 + i, "crypto", 1.0, 100.0)
        self.assertEqual(desk_record.record_line("crypto"), "",
                         "crypto was handed the disclosure the replay "
                         "measured as profit-destroying")
        self.assertIsNotNone(desk_record.excursion_record("crypto"),
                             "the crypto RECORD must survive — only the "
                             "prompt line is policy-gated")

    def test_it_never_raises_and_never_blocks_a_cycle(self):
        database._SQLITE_DB_PATH = "/nonexistent/dir/x.db"
        desk_record._CACHE.clear()
        self.assertIsNone(desk_record.excursion_record("forex"))
        self.assertEqual(desk_record.record_line("forex"), "")

    def test_the_record_is_cached_so_it_cannot_cost_every_cycle(self):
        for i in range(12):
            self._run(1000 + i, "crypto", 1.0, 100.0)
        first = desk_record.excursion_record("crypto")
        for i in range(12):
            self._run(1100 + i, "crypto", 9.0, 100.0)
        self.assertEqual(desk_record.excursion_record("crypto"), first,
                         "the query ran again inside the TTL")

    def _trade(self, rid, seq, side, qty, price):
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO run_events (run_id, seq, event_type, ts, payload) "
            "VALUES (?,?,?,?,?)",
            (rid, seq, "trade", "2026-08-18T00:00:0%dZ" % (seq % 10),
             '{"side": "%s", "quantity": %s, "price": %s}' % (side, qty, price)))
        conn.commit()
        conn.close()

    def test_the_scale_is_peak_concurrent_notional_not_the_sum_of_entries(self):
        """R30 (2026-08-22). A run that enters $100, closes, and re-enters
        $100 was scaled by $200 — its record halved by its own churn.
        Measured on prod: us-stock best 0.894% by the old sum vs 1.684%
        true. The scale must be the most the book ever held at once."""
        for i in range(12):
            rid = 2000 + i
            self._run(rid, "us-stock", 1.0, None)
            self._trade(rid, 1, "buy", 1, 100.0)
            self._trade(rid, 2, "sell", 1, 100.0)
            self._trade(rid, 3, "buy", 1, 100.0)
            self._trade(rid, 4, "sell", 1, 100.0)
        rec = desk_record.excursion_record("us-stock")
        self.assertEqual(rec["n"], 12)
        self.assertAlmostEqual(
            rec["best"], 1.0, places=4,
            msg="a re-entry was summed into the scale — the record is "
                "understated by churn (old denominator would report 0.50%)")

    def test_a_short_book_is_scaled_by_its_peak_too(self):
        """Signs: short opens negative, cover walks back to flat. A
        short-cover-short run peaked at $100 held, never $200."""
        for i in range(12):
            rid = 2100 + i
            self._run(rid, "forex", 1.0, None)
            self._trade(rid, 1, "short", 1, 100.0)
            self._trade(rid, 2, "cover", 1, 100.0)
            self._trade(rid, 3, "short", 1, 100.0)
            self._trade(rid, 4, "cover", 1, 100.0)
        rec = desk_record.excursion_record("forex")
        self.assertEqual(rec["n"], 12)
        self.assertAlmostEqual(rec["best"], 1.0, places=4)

    def test_averaging_in_still_counts_the_full_held_notional(self):
        """Two adds held TOGETHER are $200 at peak — the fix must not
        under-scale a genuinely larger book."""
        for i in range(12):
            rid = 2200 + i
            self._run(rid, "us-stock", 1.0, None)
            self._trade(rid, 1, "buy", 1, 100.0)
            self._trade(rid, 2, "buy", 1, 100.0)
            self._trade(rid, 3, "sell", 2, 100.0)
        rec = desk_record.excursion_record("us-stock")
        self.assertEqual(rec["n"], 12)
        self.assertAlmostEqual(
            rec["best"], 0.5, places=4,
            msg="concurrent adds must sum: peak held was $200, so a $1 "
                "peak P&L is 0.50% of it")


if __name__ == "__main__":
    unittest.main()
