"""The horizon clock starts when the run can TRADE (live 2026-08-13):
run 1135 (SBUX) was built at 01:11Z with an 8-hour horizon and time-expired
at 09:11Z — 4.3 hours before the 13:30Z open. Three us-stock runs burned out
flat that night, each mailing the owner a stop notice, because at_time was
anchored to build time over a closed market.
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

import fleet_planner as fp  # noqa: E402
import markets  # noqa: E402


class HorizonAnchorTests(unittest.TestCase):
    def test_open_market_anchors_to_now(self):
        with patch.object(markets, "is_market_open", return_value=True):
            anchor = fp._horizon_anchor("crypto")
        self.assertLess((fp._now_dt() - anchor).total_seconds(), 5)

    def test_closed_market_anchors_to_the_next_open(self):
        now = fp._now_dt()
        bell = (now + timedelta(hours=4)).replace(second=0, microsecond=0)
        with patch.object(markets, "is_market_open",
                          side_effect=lambda m, at=None:
                          (at or now) >= bell):
            anchor = fp._horizon_anchor("us-stock")
        self.assertLessEqual(abs((anchor - bell).total_seconds()), 90,
                             "anchor must land at the bell, not at build")

    def test_calendar_failure_falls_back_to_now(self):
        with patch.object(markets, "is_market_open",
                          side_effect=RuntimeError("no calendar")):
            anchor = fp._horizon_anchor("us-stock")
        self.assertLess((fp._now_dt() - anchor).total_seconds(), 5)

    def test_composed_run_at_time_clears_the_open(self):
        """The run-1135 shape end to end: built while closed with an 8h
        horizon ⇒ at_time lands AFTER the bell + 8h, never before the
        open."""
        now = fp._now_dt()
        bell = (now + timedelta(hours=4)).replace(second=0, microsecond=0)
        thesis = {"symbol": "SBUX", "market": "us-stock", "direction": "long",
                  "confidence": 0.6, "expected_move_pct": 3.0,
                  "horizon_hours": 8.0}
        fleet = {"risk_appetite": "balanced", "leverage": None,
                 "archetype": "short"}
        with patch.object(markets, "is_market_open",
                          side_effect=lambda m, at=None:
                          (at or now) >= bell):
            settings = fp.compose_run_settings(thesis, 1000.0, fleet)
        at_time = datetime.strptime(settings["stop_conditions"]["at_time"],
                                    fp.TS_FMT).replace(tzinfo=timezone.utc)
        self.assertGreaterEqual(at_time, bell + timedelta(hours=7, minutes=58),
                                "horizon must start at the bell")


if __name__ == "__main__":
    unittest.main()
