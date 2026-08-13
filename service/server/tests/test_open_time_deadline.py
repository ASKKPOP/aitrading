"""A composed run's `at_time` horizon means hours of OPEN market, not wall
hours (owner 2026-08-13: "make clean this time").

Live shape: run 1128 CBRS (fleet 33) was composed 2026-08-13 01:09Z with a
6-hour thesis horizon → `at_time` 07:09Z, entirely inside the NYSE overnight.
It lived and died against a shut exchange — zero cycles, zero trades, one
confusing night notification — and its slot was rebuilt with the same
symbol. Same precedent as idle-retire counting only open-market cycles.
"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import fleet_planner as fp


def _utc(y, mo, d, h, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=timezone.utc)


class OpenTimeDeadlineTests(unittest.TestCase):
    def test_24_7_market_is_plain_wall_clock(self):
        start = _utc(2026, 8, 15, 1, 0)          # Saturday — crypto trades on
        got = fp._deadline_after_open_hours("crypto", start, 6.0)
        self.assertEqual(got, start + timedelta(hours=6))

    def test_us_stock_overnight_compose_reaches_the_session(self):
        # Run 1128's exact shape: composed overnight (Wed 01:00Z), 6h
        # horizon. Six OPEN hours start at the 13:30Z bell → deadline
        # ~19:30Z the same day, never 07:00Z.
        start = _utc(2026, 8, 12, 1, 0)          # Wednesday, NYSE shut
        got = fp._deadline_after_open_hours("us-stock", start, 6.0)
        self.assertGreaterEqual(got, _utc(2026, 8, 12, 19, 15))
        self.assertLessEqual(got, _utc(2026, 8, 12, 19, 46))

    def test_us_stock_weekend_compose_spans_to_monday(self):
        # Saturday 01:00Z + 6 open hours → Monday ~19:30Z.
        start = _utc(2026, 8, 15, 1, 0)
        got = fp._deadline_after_open_hours("us-stock", start, 6.0)
        self.assertEqual(got.date(), _utc(2026, 8, 17, 0, 0).date())
        self.assertGreaterEqual(got, _utc(2026, 8, 17, 19, 15))
        self.assertLessEqual(got, _utc(2026, 8, 17, 19, 46))

    def test_horizon_longer_than_one_session_rolls_forward(self):
        # 10 open hours from a Wednesday overnight: 6.5h Wed session +
        # 3.5h into Thursday → Thu ~17:00Z.
        start = _utc(2026, 8, 12, 1, 0)
        got = fp._deadline_after_open_hours("us-stock", start, 10.0)
        self.assertEqual(got.date(), _utc(2026, 8, 13, 0, 0).date())
        self.assertGreaterEqual(got, _utc(2026, 8, 13, 16, 45))
        self.assertLessEqual(got, _utc(2026, 8, 13, 17, 16))

    def test_compose_actually_USES_the_open_time_deadline(self):
        # Wiring: a helper nobody calls is a no-op that looks tested.
        sentinel = _utc(2026, 8, 17, 19, 30)
        thesis = {"symbol": "CBRS", "market": "us-stock", "direction": "long",
                  "confidence": 0.7, "expected_move_pct": 2.0,
                  "horizon_hours": 6}
        with patch.object(fp, "_deadline_after_open_hours",
                          return_value=sentinel) as spy:
            settings = fp.compose_run_settings(
                thesis, 1000.0, {"risk_appetite": "balanced", "lang": "en"})
        self.assertEqual(settings["stop_conditions"]["at_time"],
                         "2026-08-17T19:30:00Z")
        self.assertEqual(spy.call_args[0][0], "us-stock")
        self.assertAlmostEqual(spy.call_args[0][2], 6.0)


if __name__ == "__main__":
    unittest.main()
