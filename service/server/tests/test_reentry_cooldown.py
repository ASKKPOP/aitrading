"""Fee/edge re-entry cooldown (Finding L2 follow-up, #2).

Fees scale with leverage AND round-trip frequency, so a fast leveraged tier
(extreme: 30-min cycles, 3×) can churn fees faster than the edge pays. After a
close, a flat run is held an extra window that grows with leverage
(interval × (leverage − 1)); at 1× the window is 0 — byte-identical to the old
ungated behaviour.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import unittest

import run_engine

NOW = datetime(2026, 7, 24, 3, 0, 0, tzinfo=timezone.utc)


def _iso(minutes_ago: float) -> str:
    return (NOW - timedelta(minutes=minutes_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


class ReentryCooldownMinutesTests(unittest.TestCase):
    def test_no_extra_at_1x(self):
        self.assertEqual(run_engine._reentry_cooldown_minutes(
            {"leverage": 1, "interval_minutes": 30}), 0.0)

    def test_scales_with_leverage(self):
        # 3× / 30m → 30 × (3−1) = 60 min extra
        self.assertEqual(run_engine._reentry_cooldown_minutes(
            {"leverage": 3, "interval_minutes": 30}), 60.0)

    def test_env_multiplier(self):
        with patch.dict(os.environ, {"RUN_REENTRY_LEV_MULT": "0.5"}):
            self.assertEqual(run_engine._reentry_cooldown_minutes(
                {"leverage": 3, "interval_minutes": 30}), 30.0)


class ReentryCooldownReasonTests(unittest.TestCase):
    CFG = {"leverage": 3, "interval_minutes": 30}   # 60-min cooldown

    def setUp(self):
        self._env = patch.dict(os.environ, {"RUN_REENTRY_COOLDOWN": "true", "RUN_REENTRY_LEV_MULT": "1.0"})
        self._env.start()

    def tearDown(self):
        self._env.stop()

    def test_blocks_inside_window(self):
        # closed 20 min ago, cooldown 60 min → blocked
        self.assertIsNotNone(run_engine._reentry_cooldown_reason(_iso(20), self.CFG, NOW))

    def test_allows_after_window(self):
        # closed 75 min ago, cooldown 60 min → clear
        self.assertIsNone(run_engine._reentry_cooldown_reason(_iso(75), self.CFG, NOW))

    def test_no_close_no_block(self):
        self.assertIsNone(run_engine._reentry_cooldown_reason(None, self.CFG, NOW))

    def test_one_x_never_blocks(self):
        # 1× → cooldown 0, even a close 1 minute ago is fine
        self.assertIsNone(run_engine._reentry_cooldown_reason(
            _iso(1), {"leverage": 1, "interval_minutes": 30}, NOW))

    def test_microseconds_and_z_tolerated(self):
        # closing timestamps written with microseconds must still parse
        stamp = (NOW - timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%S.123456Z")
        self.assertIsNotNone(run_engine._reentry_cooldown_reason(stamp, self.CFG, NOW))

    def test_kill_switch_off(self):
        with patch.dict(os.environ, {"RUN_REENTRY_COOLDOWN": "0"}):
            self.assertIsNone(run_engine._reentry_cooldown_reason(_iso(20), self.CFG, NOW))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
