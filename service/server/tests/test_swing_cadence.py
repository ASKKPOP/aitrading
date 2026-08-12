"""Owner spec 2026-08-12 — us-stock swing cadence: look often, act rarely.

The desk ANALYZES every 30 min through the session shoulders (open−2h to
close+2h), but orders fill only while the market is OPEN, entries land at
least 60 min apart (exits exempt — a risk brake must never delay getting
out), and the fee_edge gate still refuses any entry whose edge cannot pay
its own round trip. Four seams, each inert for runs without the stamps:

  1. markets.extended_session_state — the shoulder clock
  2. compose stamps + carry_snapshot_stamps — the stamps must SURVIVE
     validate_run_payload (the archetype stamp died there on prod fleet 31)
  3. run_engine._order_gate_skip — session-only fills + entry spacing
  4. run_engine.due_run_ids / _pre_gate_skip — dormant outside shoulders,
     analysis-only inside them while closed
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
import fleet_planner as fp
import markets
import run_engine as re_

_ET = ZoneInfo("America/New_York")


def _iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


class ExtendedSessionStateTests(unittest.TestCase):
    """2026-11-18 is an ordinary NYSE Wednesday (open 09:30–16:00 ET)."""

    def _state(self, hour, minute, day=18):
        return markets.extended_session_state(
            "us-stock", datetime(2026, 11, day, hour, minute, tzinfo=_ET))

    def test_in_session_is_open(self):
        self.assertEqual(self._state(12, 0), "open")

    def test_90min_before_open_is_analysis(self):
        self.assertEqual(self._state(8, 0), "analysis")

    def test_exactly_2h_before_open_is_analysis(self):
        self.assertEqual(self._state(7, 30), "analysis")

    def test_150min_before_open_is_closed(self):
        self.assertEqual(self._state(7, 0), "closed")

    def test_90min_after_close_is_analysis(self):
        self.assertEqual(self._state(17, 30), "analysis")

    def test_deep_evening_is_closed(self):
        self.assertEqual(self._state(18, 30), "closed")

    def test_saturday_is_closed_no_shoulder(self):
        # 2026-11-21 is a Saturday — no session anywhere near, both probes miss
        self.assertEqual(self._state(10, 0, day=21), "closed")

    def test_full_holiday_is_closed(self):
        # Thanksgiving 2026 (Thu Nov 26): midday, yet no session within ±2h
        self.assertEqual(self._state(12, 0, day=26), "closed")

    def test_24x7_market_is_always_open(self):
        self.assertEqual(markets.extended_session_state(
            "crypto", datetime(2026, 11, 21, 3, 0, tzinfo=_ET)), "open")


class CarrySnapshotStampsTests(unittest.TestCase):
    def test_stamps_are_copied_into_the_validated_core(self):
        core = {"symbol": "SLV"}
        settings = {"archetype": "swing", "entry_spacing_minutes": 60,
                    "analysis_window": {"pre_open_minutes": 120,
                                        "post_close_minutes": 120}}
        fp.carry_snapshot_stamps(core, settings)
        self.assertEqual(core["archetype"], "swing")
        self.assertEqual(core["entry_spacing_minutes"], 60)
        self.assertEqual(core["analysis_window"]["pre_open_minutes"], 120)

    def test_short_settings_leave_core_untouched(self):
        core = {"symbol": "BTCUSDT"}
        fp.carry_snapshot_stamps(core, {"archetype": "short"})
        self.assertEqual(core, {"symbol": "BTCUSDT", "archetype": "short"})


class OrderGateSkipTests(unittest.TestCase):
    RUN = {"id": 77, "market": "us-stock"}
    CFG = {"entry_spacing_minutes": 60,
           "analysis_window": {"pre_open_minutes": 120,
                               "post_close_minutes": 120}}

    def test_closed_market_blocks_every_order(self):
        with patch("routes_shared.is_market_open", return_value=False):
            for action in ("buy", "short", "sell", "cover"):
                self.assertIn("orders resume at the open",
                              re_._order_gate_skip(self.RUN, self.CFG, action))

    def test_open_market_first_entry_passes(self):
        with patch("routes_shared.is_market_open", return_value=True), \
             patch.object(re_, "_last_entry_at", return_value=None):
            self.assertIsNone(re_._order_gate_skip(self.RUN, self.CFG, "buy"))

    def test_entry_30min_after_entry_is_refused(self):
        recent = _iso(datetime.now(timezone.utc) - timedelta(minutes=30))
        with patch("routes_shared.is_market_open", return_value=True), \
             patch.object(re_, "_last_entry_at", return_value=recent):
            skip = re_._order_gate_skip(self.RUN, self.CFG, "buy")
            self.assertIn("entry spacing", skip)

    def test_exit_30min_after_entry_is_free(self):
        recent = _iso(datetime.now(timezone.utc) - timedelta(minutes=30))
        with patch("routes_shared.is_market_open", return_value=True), \
             patch.object(re_, "_last_entry_at", return_value=recent):
            self.assertIsNone(re_._order_gate_skip(self.RUN, self.CFG, "sell"))
            self.assertIsNone(re_._order_gate_skip(self.RUN, self.CFG, "cover"))

    def test_entry_61min_after_entry_passes(self):
        old = _iso(datetime.now(timezone.utc) - timedelta(minutes=61))
        with patch("routes_shared.is_market_open", return_value=True), \
             patch.object(re_, "_last_entry_at", return_value=old):
            self.assertIsNone(re_._order_gate_skip(self.RUN, self.CFG, "buy"))

    def test_unstamped_run_is_untouched_even_closed(self):
        with patch("routes_shared.is_market_open", return_value=False):
            self.assertIsNone(re_._order_gate_skip(self.RUN, {}, "buy"))


class _DBBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO agents (name, cash) VALUES ('c', 100000)")
        self.agent_id = cur.lastrowid
        conn.commit(); conn.close()

    def tearDown(self):
        self.tmp.cleanup()

    def _mk_run(self, cfg, last_cycle_at, market="us-stock"):
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO trading_runs (agent_id, symbol, market, market_type,"
            " status, config_snapshot_json, start_condition_json,"
            " stop_conditions_json, last_cycle_at, created_at) VALUES "
            "(?,?,?,'spot','running',?,'{}','{}',?,?)",
            (self.agent_id, "SLV", market, json.dumps(cfg), last_cycle_at,
             "2026-01-01T00:00:00Z"))
        rid = cur.lastrowid
        conn.commit(); conn.close()
        return rid

    STAMPED = {"interval_minutes": 30, "archetype": "swing",
               "entry_spacing_minutes": 60,
               "analysis_window": {"pre_open_minutes": 120,
                                   "post_close_minutes": 120}}


class DueDormancyTests(_DBBase):
    def test_stamped_run_is_never_due_while_closed(self):
        stale = _iso(datetime.now(timezone.utc) - timedelta(minutes=90))
        rid = self._mk_run(self.STAMPED, stale)
        with patch("markets.extended_session_state", return_value="closed"):
            self.assertNotIn(rid, re_.due_run_ids())

    def test_stamped_run_is_due_in_the_analysis_shoulder(self):
        stale = _iso(datetime.now(timezone.utc) - timedelta(minutes=90))
        rid = self._mk_run(self.STAMPED, stale)
        with patch("markets.extended_session_state", return_value="analysis"):
            self.assertIn(rid, re_.due_run_ids())

    def test_unstamped_run_dispatch_is_unchanged(self):
        stale = _iso(datetime.now(timezone.utc) - timedelta(minutes=90))
        rid = self._mk_run({"interval_minutes": 30, "archetype": "short"},
                           stale, market="crypto")
        with patch("markets.extended_session_state", return_value="closed"):
            self.assertIn(rid, re_.due_run_ids())


class PreGateShoulderTests(_DBBase):
    def _run_row(self, rid):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM trading_runs WHERE id = ?", (rid,))
            return dict(cur.fetchone())
        finally:
            conn.close()

    def test_closed_market_in_shoulder_allows_analysis(self):
        rid = self._mk_run(self.STAMPED, _iso(datetime.now(timezone.utc)))
        run = self._run_row(rid)
        with patch("routes_shared.is_market_open", return_value=False), \
             patch("markets.extended_session_state", return_value="analysis"):
            skip = re_._pre_gate_skip(run, self.STAMPED)
        self.assertNotEqual(skip, "market closed")

    def test_closed_market_outside_shoulder_still_skips(self):
        rid = self._mk_run(self.STAMPED, _iso(datetime.now(timezone.utc)))
        run = self._run_row(rid)
        with patch("routes_shared.is_market_open", return_value=False), \
             patch("markets.extended_session_state", return_value="closed"):
            self.assertEqual(re_._pre_gate_skip(run, self.STAMPED),
                             "market closed")

    def test_unstamped_run_keeps_the_hard_closed_skip(self):
        cfg = {"interval_minutes": 30, "archetype": "short"}
        rid = self._mk_run(cfg, _iso(datetime.now(timezone.utc)))
        run = self._run_row(rid)
        with patch("routes_shared.is_market_open", return_value=False):
            self.assertEqual(re_._pre_gate_skip(run, cfg), "market closed")


class LastEntryAtTests(_DBBase):
    def test_reads_only_entry_legs_of_this_run(self):
        rid = self._mk_run(self.STAMPED, _iso(datetime.now(timezone.utc)))
        conn = database.get_db_connection()
        cur = conn.cursor()
        rows = [
            (rid, "buy", "2026-08-12T14:00:00Z"),
            (rid, "sell", "2026-08-12T15:00:00Z"),   # exit — must not count
            (999, "buy", "2026-08-12T15:30:00Z"),    # other run — must not count
        ]
        for run_id, side, ts in rows:
            cur.execute(
                "INSERT INTO signals (signal_id, agent_id, message_type,"
                " market, signal_type, symbol, side, entry_price, quantity,"
                " content, timestamp, created_at, run_id) VALUES "
                "(?,?, 'operation', 'us-stock', 'automation', 'SLV', ?, 10, 1,"
                " 'x', 0, ?, ?)",
                (f"s-{run_id}-{ts}", self.agent_id, side, ts, run_id))
        conn.commit(); conn.close()
        self.assertEqual(re_._last_entry_at(rid), "2026-08-12T14:00:00Z")


if __name__ == "__main__":
    unittest.main()
