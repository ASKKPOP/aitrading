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


class EntryFeesTests(unittest.TestCase):
    """entry_fees mirrors replay_realized's leg-walk, but sums only the
    ENTRY-side portion of each leg's fee — the half the adapt stream never
    nets, and therefore the exact expected ledger-vs-adapt delta."""

    def test_open_fee_counts_close_fee_does_not(self):
        f = pnl_audit.entry_fees([
            {"side": "buy", "quantity": 7.8342915, "price": 103.37,
             "fee_usd": 0.8761},
            {"side": "sell", "quantity": 7.8342915, "price": 104.91,
             "fee_usd": 0.4221}])
        self.assertAlmostEqual(f, 0.8761, places=6)

    def test_a_flip_prorates_its_single_fee(self):
        # 10 close + 20 open on one 30-unit leg with one fee: only the
        # opening two-thirds is entry-side.
        f = pnl_audit.entry_fees([
            {"side": "buy", "quantity": 10.153, "price": 100.0,
             "fee_usd": 0.3011},
            {"side": "sell", "quantity": 30.459, "price": 110.0,
             "fee_usd": 0.9033}])
        self.assertAlmostEqual(f, 0.3011 + 0.9033 * (20.306 / 30.459),
                               places=6)


class DriftReportTests(unittest.TestCase):
    """The point of the module: disagreement between the two methods must be
    LOUD. The old snippet was wrong silently for weeks."""

    def test_drift_is_flagged_and_agreement_is_not(self):
        rows = [{"day": "2026-08-05", "ledger": 8.62, "adapt": 73.21,
                 "delta": -64.59, "fee_asym": -0.31, "resid": -64.28,
                 "flattens": 2, "agrees": False},
                {"day": "2026-08-06", "ledger": -4.21, "adapt": -1.44,
                 "delta": -2.77, "fee_asym": -2.51, "resid": -0.26,
                 "flattens": 0, "agrees": True}]
        report = pnl_audit.format_report(rows)
        self.assertIn("*** DRIFT ***", report)
        self.assertIn("2026-08-05", report)
        self.assertEqual(report.count("*** DRIFT ***"), 1)

    def test_report_prints_the_expected_fee_and_residual_columns(self):
        # The report must stay honest: show WHAT was excused (fee_asym) and
        # what remains after excusing it (resid), not just a verdict.
        rows = [{"day": "2026-08-13", "ledger": -43.19, "adapt": -35.81,
                 "delta": -7.38, "fee_asym": -7.38, "resid": 0.0,
                 "flattens": 3, "agrees": True}]
        report = pnl_audit.format_report(rows)
        self.assertIn("fee_asym", report)
        self.assertIn("resid", report)
        self.assertIn("-7.38", report)

    def test_main_exit_code_is_nonzero_on_drift(self):
        # So a scheduled run can FAIL rather than print into the void.
        from unittest.mock import patch
        drift = [{"day": "d", "ledger": 1.0, "adapt": 99.0, "delta": -98.0,
                  "fee_asym": -0.42, "resid": -97.58,
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

    def test_ENTRY_FEE_ASYMMETRY_beyond_tolerance_is_ok_not_drift(self):
        # The 2026-08-13 false alarm: adapt `realized` nets EXIT-side fees
        # only, the ledger charges BOTH sides. Two closes whose raw delta
        # (-7.38, summed entry fees) exceeds the $5 tolerance but is the
        # asymmetry EXACTLY must read ok with resid ~ 0. (Modeled on prod
        # runs 1104/1159, 2026-08-13 — float-dusty on purpose.)
        pnl_1 = (517.34 - 520.01) * 5.8393100901905735   # -15.5910...
        pnl_2 = (0.9137 - 0.9312) * 917.4311926605505    # -16.0550...
        self._seed(
            trades=[(1, "2026-08-06T01:00:00Z",
                     {"side": "buy", "quantity": 5.8393100901905735,
                      "price": 520.01, "fee_usd": 3.6612}),
                    (1, "2026-08-06T02:00:00Z",
                     {"side": "sell", "quantity": 5.8393100901905735,
                      "price": 517.34, "fee_usd": 0.4221,
                      "client_order_id": "run:1:flatten"}),
                    (2, "2026-08-06T01:30:00Z",
                     {"side": "buy", "quantity": 917.4311926605505,
                      "price": 0.9312, "fee_usd": 3.7183}),
                    (2, "2026-08-06T03:00:00Z",
                     {"side": "sell", "quantity": 917.4311926605505,
                      "price": 0.9137, "fee_usd": 0.3902})],
            adapts=[("2026-08-06T02:00:00Z", {"realized": pnl_1 - 0.4221}),
                    ("2026-08-06T03:00:00Z", {"realized": pnl_2 - 0.3902})])
        rows = pnl_audit.realized_by_day("2026-08-06")
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertAlmostEqual(row["delta"], -7.38, places=2)
        self.assertGreater(abs(row["delta"]), 5.0,
                           "fixture must exceed raw tolerance to prove the point")
        self.assertAlmostEqual(row["fee_asym"], -7.38, places=2)
        self.assertAlmostEqual(row["resid"], 0.0, places=2)
        self.assertTrue(row["agrees"],
                        "entry-fee asymmetry alone must NOT read as drift")

    def test_a_REAL_drift_beyond_the_fee_asymmetry_still_alarms(self):
        # Same shape, but the adapt stream is short a further ~20 beyond
        # the entry fee: excusing fees must not excuse this.
        pnl = (517.34 - 520.01) * 5.8393100901905735
        self._seed(
            trades=[(1, "2026-08-06T01:00:00Z",
                     {"side": "buy", "quantity": 5.8393100901905735,
                      "price": 520.01, "fee_usd": 6.1273}),
                    (1, "2026-08-06T02:00:00Z",
                     {"side": "sell", "quantity": 5.8393100901905735,
                      "price": 517.34, "fee_usd": 0.4221})],
            adapts=[("2026-08-06T02:00:00Z",
                     {"realized": pnl - 0.4221 + 19.7341})])
        rows = pnl_audit.realized_by_day("2026-08-06")
        row = rows[0]
        self.assertAlmostEqual(row["fee_asym"], -6.13, places=2)
        self.assertAlmostEqual(row["resid"], -19.73, places=2)
        self.assertFalse(row["agrees"],
                         "a real 19.73 gap must NOT hide behind the fee excuse")
        # And the CLI must fail loudly on it, through the real query path.
        self.assertEqual(pnl_audit.main(["--since", "2026-08-06"]), 1)
