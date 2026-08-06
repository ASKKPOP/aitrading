"""pnl_audit — the monitoring layer's own accounting, and its self-check.

The runbook's hand-written realized-P&L snippet was a SECOND implementation
of the platform's accounting. It drifted (omitting every forced flatten),
nothing checked it, and it stayed wrong for weeks while the platform itself
was correct throughout. These tests pin the replacement.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import pnl_audit  # noqa: E402


class ReplayRealizedTests(unittest.TestCase):
    def test_long_round_trip_nets_both_fees(self):
        r = pnl_audit.replay_realized([
            {"side": "buy", "quantity": 10, "price": 100.0, "fee_usd": 1.0},
            {"side": "sell", "quantity": 10, "price": 110.0, "fee_usd": 1.1}])
        self.assertAlmostEqual(r, 100.0 - 2.1, places=6)

    def test_SHORT_COVER_SIGN_the_bug_this_module_exists_for(self):
        # A naive replay keeps a signed cost and does `cost -= avg*closed` on
        # every close. For a SHORT the basis is negative, so that drives it
        # away from zero and corrupts every later average. It reported
        # +116,756 on a run that made +13.19 — and stays plausible on small
        # runs, which is why it survived for weeks.
        r = pnl_audit.replay_realized([
            {"side": "short", "quantity": 100, "price": 50.0, "fee_usd": 0.0},
            {"side": "cover", "quantity": 50, "price": 49.0, "fee_usd": 0.0},
            {"side": "cover", "quantity": 50, "price": 48.0, "fee_usd": 0.0}])
        # 50*(50-49) + 50*(50-48) = 50 + 100
        self.assertAlmostEqual(r, 150.0, places=6)

    def test_partial_closes_price_off_a_stable_average(self):
        r = pnl_audit.replay_realized([
            {"side": "buy", "quantity": 100, "price": 10.0, "fee_usd": 0.0},
            {"side": "sell", "quantity": 50, "price": 12.0, "fee_usd": 0.0},
            {"side": "sell", "quantity": 25, "price": 11.0, "fee_usd": 0.0}])
        self.assertAlmostEqual(r, 50 * 2.0 + 25 * 1.0, places=6)

    def test_adding_moves_the_average(self):
        r = pnl_audit.replay_realized([
            {"side": "buy", "quantity": 10, "price": 100.0, "fee_usd": 0.0},
            {"side": "buy", "quantity": 10, "price": 120.0, "fee_usd": 0.0},
            {"side": "sell", "quantity": 20, "price": 110.0, "fee_usd": 0.0}])
        self.assertAlmostEqual(r, 0.0, places=6)   # avg 110, out at 110

    def test_a_flip_closes_then_opens_the_other_side(self):
        r = pnl_audit.replay_realized([
            {"side": "buy", "quantity": 10, "price": 100.0, "fee_usd": 0.0},
            {"side": "sell", "quantity": 30, "price": 110.0, "fee_usd": 0.0},
            {"side": "buy", "quantity": 20, "price": 105.0, "fee_usd": 0.0}])
        # +100 closing the long, then 20 short from 110 covered at 105 = +100
        self.assertAlmostEqual(r, 200.0, places=6)

    def test_run_971_matches_the_platforms_own_stored_figure(self):
        # Three independent methods agree on -58.18: this replay, hand
        # arithmetic, and trading_runs.realized_pnl_usd on prod.
        r = pnl_audit.replay_realized([
            {"side": "buy", "quantity": 5.8393100901905735,
             "price": 520.01, "fee_usd": 1.366424838},
            {"side": "buy", "quantity": 9.97220412002995,
             "price": 520.87, "fee_usd": 2.3373998819999997},
            {"side": "sell", "quantity": 15.81151421,
             "price": 517.34, "fee_usd": 3.6809679426306303}])
        self.assertAlmostEqual(r, -58.18, places=2)

    def test_garbage_legs_are_skipped_not_fatal(self):
        r = pnl_audit.replay_realized([
            {"side": "buy", "quantity": 10, "price": 100.0, "fee_usd": 0.0},
            {"nonsense": True},
            {"side": "buy", "quantity": "x", "price": 100.0},
            {"side": "sell", "quantity": 10, "price": 0.0},       # bad price
            {"side": "sell", "quantity": 10, "price": 110.0, "fee_usd": 0.0}])
        self.assertAlmostEqual(r, 100.0, places=6)


class DriftReportTests(unittest.TestCase):
    """The point of the module: disagreement between the two methods must be
    LOUD. The old snippet was wrong silently for weeks."""

    def test_drift_is_flagged_and_agreement_is_not(self):
        rows = [{"day": "2026-08-05", "ledger": 8.62, "adapt": 73.21,
                 "delta": -64.59, "flattens": 2, "agrees": False},
                {"day": "2026-08-06", "ledger": -4.21, "adapt": -1.44,
                 "delta": -2.77, "flattens": 0, "agrees": True}]
        report = pnl_audit.format_report(rows)
        self.assertIn("*** DRIFT ***", report)
        self.assertIn("2026-08-05", report)
        self.assertEqual(report.count("*** DRIFT ***"), 1)

    def test_main_exit_code_is_nonzero_on_drift(self):
        # So a scheduled run can FAIL rather than print into the void.
        from unittest.mock import patch
        drift = [{"day": "d", "ledger": 1.0, "adapt": 99.0, "delta": -98.0,
                  "flattens": 1, "agrees": False}]
        clean = [dict(drift[0], agrees=True)]
        with patch.object(pnl_audit, "realized_by_day", return_value=drift):
            self.assertEqual(pnl_audit.main(["--since", "2026-08-01"]), 1)
        with patch.object(pnl_audit, "realized_by_day", return_value=clean):
            self.assertEqual(pnl_audit.main(["--since", "2026-08-01"]), 0)


class RealizedByDayTests(unittest.TestCase):
    """Exercises the `agrees` COMPUTATION, not a hand-passed flag.

    A first pass at these tests only fed pre-built rows into format_report,
    so hardcoding `"agrees": True` in realized_by_day survived mutation —
    the alarm itself was untested. This drives the real query path.
    """

    def setUp(self):
        import os
        import tempfile
        import database
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "t.db")
        database.init_database()
        self.database = database

    def tearDown(self):
        self.tmp.cleanup()

    def _seed(self, trades, adapts):
        import json as _json
        conn = self.database.get_db_connection()
        cur = conn.cursor()
        self.database.begin_write_transaction(cur)
        seq = 0
        for run_id, ts, payload in trades:
            seq += 1
            cur.execute(
                "INSERT INTO run_events (run_id, seq, event_type, ts, payload)"
                " VALUES (?, ?, 'trade', ?, ?)",
                (run_id, seq, ts, _json.dumps(payload)))
        for ts, payload in adapts:
            seq += 1
            cur.execute(
                "INSERT INTO run_events (run_id, seq, event_type, ts, payload)"
                " VALUES (?, ?, 'adapt', ?, ?)",
                (1, seq, ts, _json.dumps(payload)))
        conn.commit()
        conn.close()

    def test_agreement_and_DRIFT_are_computed_from_the_data(self):
        # A clean long round trip: ledger +100, and an adapt that agrees.
        self._seed(
            trades=[(1, "2026-08-06T01:00:00Z",
                     {"side": "buy", "quantity": 10, "price": 100.0,
                      "fee_usd": 0.0}),
                    (1, "2026-08-06T02:00:00Z",
                     {"side": "sell", "quantity": 10, "price": 110.0,
                      "fee_usd": 0.0})],
            adapts=[("2026-08-06T02:00:00Z", {"realized": 100.0})])
        rows = pnl_audit.realized_by_day("2026-08-06")
        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows[0]["ledger"], 100.0, places=2)
        self.assertAlmostEqual(rows[0]["adapt"], 100.0, places=2)
        self.assertTrue(rows[0]["agrees"])

    def test_a_flatten_with_no_adapt_shows_up_as_DRIFT(self):
        # This is exactly the historical defect: the flatten leg is real P&L
        # that the adapt stream never carried.
        self._seed(
            trades=[(1, "2026-08-06T01:00:00Z",
                     {"side": "buy", "quantity": 10, "price": 100.0,
                      "fee_usd": 0.0}),
                    (1, "2026-08-06T02:00:00Z",
                     {"side": "sell", "quantity": 10, "price": 40.0,
                      "fee_usd": 0.0,
                      "client_order_id": "run:1:flatten"})],
            adapts=[])
        rows = pnl_audit.realized_by_day("2026-08-06")
        self.assertAlmostEqual(rows[0]["ledger"], -600.0, places=2)
        self.assertAlmostEqual(rows[0]["adapt"], 0.0, places=2)
        self.assertEqual(rows[0]["flattens"], 1)
        self.assertFalse(rows[0]["agrees"], "a 600 gap must NOT read as agreement")

    def test_a_position_carried_across_midnight_is_replayed_from_inception(self):
        # Window-scoped replay invents a phantom opening leg for a carried
        # position; that is how an earlier pass produced +116,756 nonsense.
        self._seed(
            trades=[(1, "2026-08-05T23:00:00Z",
                     {"side": "buy", "quantity": 10, "price": 100.0,
                      "fee_usd": 0.0}),
                    (1, "2026-08-06T01:00:00Z",
                     {"side": "sell", "quantity": 10, "price": 110.0,
                      "fee_usd": 0.0})],
            adapts=[])
        rows = pnl_audit.realized_by_day("2026-08-06")
        day = [r for r in rows if r["day"] == "2026-08-06"][0]
        # +100 total, all of it realized ON 08-06 — not a phantom short.
        self.assertAlmostEqual(day["ledger"], 100.0, places=2)
