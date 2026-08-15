"""Catch the open (owner 2026-08-12): "most people try to buy and sell when
the US market opens — we must catch that time."

Two pieces: the scheduler makes any run whose last cycle predates the bell
due IMMEDIATELY at the open (bypassing slot phase and the half-interval
guard), and the desk is told when it stands inside the first 30 minutes of
the session.
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

import database  # noqa: E402
import markets  # noqa: E402
import run_engine  # noqa: E402
import trading_runs  # noqa: E402


def _iso(dt):
    return dt.strftime(trading_runs.TS_FMT)


class OpenedSinceTests(unittest.TestCase):
    def test_bell_between_stamps_fires(self):
        now = datetime.now(timezone.utc)
        bell = now - timedelta(minutes=5)          # opened 5 minutes ago
        with patch.object(markets, "is_market_open",
                          side_effect=lambda m, at=None:
                          (at or now) >= bell):
            self.assertTrue(run_engine._opened_since(
                "us-stock", now - timedelta(minutes=10), now))

    def test_always_open_market_never_fires(self):
        now = datetime.now(timezone.utc)
        with patch.object(markets, "is_market_open", return_value=True):
            self.assertFalse(run_engine._opened_since(
                "crypto", now - timedelta(minutes=10), now))

    def test_still_closed_never_fires(self):
        now = datetime.now(timezone.utc)
        with patch.object(markets, "is_market_open", return_value=False):
            self.assertFalse(run_engine._opened_since(
                "us-stock", now - timedelta(minutes=10), now))

    def test_calendar_failure_falls_back_closed(self):
        now = datetime.now(timezone.utc)
        with patch.object(markets, "is_market_open",
                          side_effect=RuntimeError("no calendar")):
            self.assertFalse(run_engine._opened_since(
                "us-stock", now - timedelta(minutes=10), now))


class DueAtTheBellTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "t.db")
        database.init_database()

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, market, last_minutes_ago):
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO trading_runs (agent_id, symbol, market, market_type,"
            " status, config_snapshot_json, created_at, last_cycle_at,"
            " cycle_seq) VALUES (6, 'X', ?, 'spot', 'running', ?, ?, ?, 3)",
            (market, json.dumps({"interval_minutes": 30}),
             _iso(datetime.now(timezone.utc) - timedelta(hours=2)),
             _iso(datetime.now(timezone.utc)
                  - timedelta(minutes=last_minutes_ago))))
        run_id = cur.lastrowid
        conn.commit()
        conn.close()
        return run_id

    def test_pre_open_run_is_due_the_moment_the_market_opens(self):
        """Last cycle 10 minutes ago (market closed then), market open now:
        the slot grid says 'not yet' (half-interval guard), the bell says
        NOW."""
        run_id = self._run("us-stock", last_minutes_ago=10)
        now = datetime.now(timezone.utc)
        bell = now - timedelta(minutes=5)          # opened 5 minutes ago
        with patch.object(markets, "is_market_open",
                          side_effect=lambda m, at=None:
                          (at or now) >= bell):
            self.assertIn(run_id, run_engine.due_run_ids())

    def test_open_market_run_keeps_its_normal_slotting(self):
        """Same 10-minutes-ago stamp with the market open THROUGHOUT: the
        half-interval guard must still hold (no premature refire)."""
        run_id = self._run("us-stock", last_minutes_ago=10)
        with patch.object(markets, "is_market_open", return_value=True):
            self.assertNotIn(run_id, run_engine.due_run_ids())


class OpeningWindowLineTests(unittest.TestCase):
    def test_renders_inside_the_first_30_minutes(self):
        now = datetime.now(timezone.utc)
        bell = now - timedelta(minutes=5)          # opened 5 minutes ago
        with patch.object(markets, "is_market_open",
                          side_effect=lambda m, at=None:
                          (at or now) >= bell):
            line = run_engine._opening_window_line({"market": "us-stock"})
        self.assertIn("OPENED within the last 30 minutes", line)

    def test_silent_when_open_for_a_while(self):
        with patch.object(markets, "is_market_open", return_value=True):
            self.assertEqual(
                run_engine._opening_window_line({"market": "us-stock"}), "")

    def test_silent_when_closed(self):
        with patch.object(markets, "is_market_open", return_value=False):
            self.assertEqual(
                run_engine._opening_window_line({"market": "us-stock"}), "")

    def test_wired_into_both_prompt_paths(self):
        import inspect
        self.assertIn("_opening_window_line(run)",
                      inspect.getsource(run_engine._compose_position_state),
                      "line must be in the composed brief (both paths route through it)")


if __name__ == "__main__":
    unittest.main()
