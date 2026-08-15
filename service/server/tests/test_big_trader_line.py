"""Big-trader tape brief (owner 2026-08-13: "must follow big trader — it's
key"): Plan 23 Phase D records FINRA short-volume, put/call OI and
StockTwits tilt 6-hourly into us_stock_factor_snapshots, and until this
line NOTHING showed them to the desk — the signal was record-only (0
references in the decision layer). These tests pin the render (null-honest,
age-capped, us-stock only) and — per the standing wiring rule — that the
line is actually concatenated into BOTH decision prompts.
"""

from __future__ import annotations

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
import run_engine


def _iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


class BigTraderLineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()

    def tearDown(self):
        self.tmp.cleanup()

    _RUN = {"id": 1, "agent_id": 1, "symbol": "XOM", "market": "us-stock"}

    def _seed(self, symbol="XOM", putcall=1.32, short_ratio=0.58,
              tilt=0.40, tilt_n=25, age_hours=7.0):
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO us_stock_factor_snapshots (symbol, putcall_oi_ratio,"
            " short_volume_ratio, stocktwits_tilt, tilt_n, created_at)"
            " VALUES (?,?,?,?,?,?)",
            (symbol, putcall, short_ratio, tilt, tilt_n,
             _iso(datetime.now(timezone.utc) - timedelta(hours=age_hours))))
        conn.commit()
        conn.close()

    def test_renders_all_three_fields_with_age(self):
        self._seed()
        line = run_engine._big_trader_line(self._RUN)
        self.assertIn("Big-trader tape (7h old):", line)
        self.assertIn("FINRA short-volume ratio 0.58", line)
        self.assertIn("put/call OI 1.32", line)
        self.assertIn("StockTwits tilt +0.40 (n=25)", line)

    def test_null_fields_are_omitted_never_guessed(self):
        # putcall_oi_ratio has been NULL on whole live batches (2026-08-13);
        # the line must stay honest and simply not mention the field.
        self._seed(putcall=None, tilt=None, tilt_n=None)
        line = run_engine._big_trader_line(self._RUN)
        self.assertIn("FINRA short-volume ratio 0.58", line)
        self.assertNotIn("put/call", line)
        self.assertNotIn("StockTwits", line)

    def test_silent_when_no_row_stale_row_or_wrong_market(self):
        self.assertEqual(run_engine._big_trader_line(self._RUN), "")
        self._seed(age_hours=72.0)          # beyond the 48h FINRA T+1 cap
        self.assertEqual(run_engine._big_trader_line(self._RUN), "")
        self._seed(age_hours=1.0)
        crypto_run = dict(self._RUN, market="crypto")
        self.assertEqual(run_engine._big_trader_line(crypto_run), "")

    def test_all_null_row_renders_nothing(self):
        self._seed(putcall=None, short_ratio=None, tilt=None, tilt_n=None)
        self.assertEqual(run_engine._big_trader_line(self._RUN), "")

    def test_uses_the_newest_row(self):
        self._seed(short_ratio=0.61, age_hours=30.0)
        self._seed(short_ratio=0.44, age_hours=2.0)
        line = run_engine._big_trader_line(self._RUN)
        self.assertIn("0.44", line)
        self.assertNotIn("0.61", line)

    def test_the_line_is_actually_WIRED_into_the_light_prompt(self):
        # A brief line that renders but is not concatenated into the prompt
        # is a no-op that looks tested (standing rule, main handoff §5).
        seen = {}

        def _capture(prompt, **kw):
            seen["prompt"] = prompt
            return '{"action":"hold","confidence":0.5}'

        import llm_client
        import price_fetcher
        run = {"id": 1, "agent_id": 1, "symbol": "XOM", "market": "us-stock",
               "market_type": "spot"}
        with patch.object(price_fetcher, "get_price_from_market",
                          return_value=159.75), \
            patch.object(price_fetcher, "get_daily_candles",
                         return_value=[]), \
            patch.object(run_engine, "_position_quantity",
                         return_value=0.75), \
            patch.object(run_engine, "_big_trader_line",
                         return_value="TAPE_SENTINEL\n"), \
                patch.object(llm_client, "generate_text", _capture):
            run_engine._light_analysis(run, {})
        self.assertIn("TAPE_SENTINEL", seen.get("prompt", ""),
                      "big-trader line is not wired into the light prompt")

    def test_the_line_is_actually_WIRED_into_the_full_prompt(self):
        import inspect
        src = inspect.getsource(run_engine._compose_position_state)
        self.assertIn("_big_trader_line(run)", src,
                      "big-trader line is not wired into the full prompt")


class FollowTheFlowTapeClauseTests(unittest.TestCase):
    """The observable and the lesson ship together (main handoff §10: an
    observable with no lesson is half a fix). The skill must teach exactly
    the fields the line renders."""

    def test_skill_teaches_the_tape_line_levels(self):
        import trading_skills
        skill = next(s for s in trading_skills.BASE_SKILLS
                     if s["slug"] == "follow-the-flow")
        body = skill["body"]
        self.assertIn("Big-trader tape", body)
        self.assertIn("short-volume", body)
        self.assertIn("Put/call OI", body)
        self.assertIn("never assume a reading", body)


if __name__ == "__main__":
    unittest.main()
