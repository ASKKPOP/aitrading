"""Plan 23 Phase B — the run engine learns the swing archetype.

Four seams, each wired off the config snapshot's `archetype` stamp (Phase A)
and each inert for 'short' runs: the 240-min desk cadence cap, the two
archetype-conditioned brief lines (closing-soon and banking — wiring test per
line, per the brief-wiring trap), the horizon gate armed for swing only, and
overnight stop dormancy (frozen marks on a CLOSED market are expected, not a
fault; the gap through a stop fires at the open's fresh mark instead).
(The fifth panel item — idle-retire counting closed-session cycles — was
already fixed platform-wide via _closed_market_cycles.)
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

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
import run_engine as re_


def _iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


class _DBBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO agents (name, cash) VALUES ('b', 100000)")
        self.agent_id = cur.lastrowid
        conn.commit(); conn.close()

    def tearDown(self):
        self.tmp.cleanup()

    def _mk_run(self, archetype, interval, last_cycle_at, market="us-stock"):
        cfg = {"interval_minutes": interval, "archetype": archetype}
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO trading_runs (agent_id, symbol, market, market_type,"
            " status, config_snapshot_json, start_condition_json,"
            " stop_conditions_json, last_cycle_at, created_at) VALUES "
            "(?,?,?,'spot','running',?,'{}','{}',?,?)",
            (self.agent_id, "MSFT", market, json.dumps(cfg), last_cycle_at,
             "2026-01-01T00:00:00Z"))
        rid = cur.lastrowid
        conn.commit(); conn.close()
        return rid


class SwingCadenceCap(_DBBase):
    def test_swing_runs_now_share_the_30min_platform_cap(self):
        # Owner decision 2026-08-13 (amends Plan 23 Phase B): the us-stock
        # block DAY-trades — buy/sell on the 30-min think clock. A swing run
        # stamped 240 is therefore capped to 30 exactly like a short run;
        # the previous 240-min special-case is retired, not tunable back by
        # a stamp.
        now = datetime.now(timezone.utc)
        rid = self._mk_run("swing", 240, _iso(now - timedelta(minutes=90)))
        self.assertIn(rid, re_.due_run_ids(),
                      "swing run must be due on the 30-min day clock")

    def test_short_runs_keep_the_30min_platform_cap(self):
        now = datetime.now(timezone.utc)
        # a short run asking for 240 is capped at 30 — 90min elapsed = due
        rid = self._mk_run("short", 240, _iso(now - timedelta(minutes=90)),
                           market="crypto")
        self.assertIn(rid, re_.due_run_ids())


class SwingBriefLines(_DBBase):
    """One wiring test per changed line — the brief-wiring trap: an unwired
    line passes every rendering test."""

    def _line(self, archetype, minutes_left=10):
        cfg = {"archetype": archetype}
        run = {"id": 1, "agent_id": self.agent_id, "symbol": "MSFT",
               "market": "us-stock", "status": "running",
               "config_snapshot_json": json.dumps(cfg),
               "stop_conditions_json": "{}", "peak_pnl_usd": 0.0}
        pnl = {"realized": 0.0, "unrealized": 5.0, "total": 5.0, "trades": 2,
               "mark_age_ok": True,
               "position": {"quantity": 10, "entry_price": 100.0,
                            "current_price": 100.5,
                            "price_updated_at": _iso(datetime.now(timezone.utc)),
                            "leverage": 1.0}}
        with patch.object(re_, "compute_run_pnl", return_value=pnl), \
             patch("markets.session_minutes_left",
                   return_value=minutes_left), \
             patch.object(re_, "_margin_state_line", return_value=""):
            return re_._position_state_line(run, cfg, 10.0, {})

    def test_swing_closing_soon_says_holding_is_the_design(self):
        line = self._line("swing")
        self.assertIn("this run's DESIGN", line)
        self.assertNotIn("no longer yours", line)

    def test_short_closing_soon_line_is_unchanged(self):
        line = self._line("short")
        self.assertIn("no longer yours", line)
        self.assertNotIn("this run's DESIGN", line)

    def test_swing_banking_line_indexes_to_the_thesis(self):
        line = self._line("swing")
        self.assertIn("SWING desk", line)
        self.assertIn("never allowed to round-trip", line)
        self.assertNotIn("Banking is a first-class action", line)

    def test_short_banking_line_is_unchanged(self):
        line = self._line("short")
        self.assertIn("Banking is a first-class action", line)
        self.assertNotIn("SWING desk", line)


class SwingHorizonGate(_DBBase):
    def _run(self, archetype, horizon_until):
        return {"id": 1, "config_snapshot_json":
                json.dumps({"archetype": archetype}),
                "stop_conditions_json":
                json.dumps({"horizon_until": horizon_until})}

    def test_swing_arms_the_gate_without_the_env_flag(self):
        until = _iso(datetime.now(timezone.utc) + timedelta(hours=20))
        skip = re_._horizon_skip(self._run("swing", until), {}, True)
        self.assertIsNotNone(skip)
        self.assertIn("horizon holds", skip)

    def test_short_runs_stay_dark_as_before(self):
        until = _iso(datetime.now(timezone.utc) + timedelta(hours=20))
        self.assertIsNone(
            re_._horizon_skip(self._run("short", until), {}, True))

    def test_position_specific_trigger_still_bypasses_for_swing(self):
        until = _iso(datetime.now(timezone.utc) + timedelta(hours=20))
        route = {"triggers": ["position_underwater"]}
        self.assertIsNone(
            re_._horizon_skip(self._run("swing", until), route, True))


class OvernightStopDormancy(_DBBase):
    def _run_row(self):
        rid = self._mk_run("swing", 240,
                           _iso(datetime.now(timezone.utc)))
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE trading_runs SET stop_conditions_json = ? "
                    "WHERE id = ?",
                    (json.dumps({"max_loss_usd": 50.0}), rid))
        conn.commit()
        cur.execute("SELECT * FROM trading_runs WHERE id = ?", (rid,))
        row = dict(cur.fetchone())
        conn.close()
        return row

    def _stale_pnl(self):
        return {"realized": 0.0, "unrealized": -10.0, "total": -10.0,
                "trades": 2, "mark_age_ok": False,
                "position": {"quantity": 10, "entry_price": 100.0,
                             "current_price": 99.0,
                             "price_updated_at": "2026-01-01T00:00:00Z",
                             "leverage": 1.0}}

    def test_closed_market_goes_dormant_instead_of_raising(self):
        run = self._run_row()
        with patch.object(re_, "compute_run_pnl",
                          return_value=self._stale_pnl()), \
             patch("markets.is_market_open", return_value=False):
            self.assertIsNone(re_._evaluate_stop(run))

    def test_open_market_with_stale_marks_still_raises(self):
        run = self._run_row()
        with patch.object(re_, "compute_run_pnl",
                          return_value=self._stale_pnl()), \
             patch("markets.is_market_open", return_value=True):
            with self.assertRaises(RuntimeError):
                re_._evaluate_stop(run)

    def test_gap_through_stop_fires_on_the_first_fresh_mark(self):
        run = self._run_row()
        gapped = self._stale_pnl()
        gapped["mark_age_ok"] = True
        gapped["total"] = -60.0            # gapped through the $50 stop
        with patch.object(re_, "compute_run_pnl", return_value=gapped), \
             patch("markets.is_market_open", return_value=True):
            self.assertEqual(re_._evaluate_stop(run), "stop_event:max_loss")


if __name__ == "__main__":
    unittest.main()
