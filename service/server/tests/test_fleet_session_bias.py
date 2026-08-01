"""Auto session-bias for fleet composition.

An unrestricted fleet (no explicit market_scope) composed while a market is
closed used to bind slots to symbols that idle until the next session — the
proven case is us-stock picked overnight, dead until ~13:30Z. `_open_markets_scope`
narrows the composition universe to markets open *now*, so every slot works
immediately. Explicit market_scope is untouched by this (tested at the
_do_research call site is heavier; the scope-derivation is the whole behaviour).
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import unittest

import fleet_planner

# 2026-07-23 is a Thursday; 2026-07-25 a Saturday. (July 1 2026 = Wed.)
_THU_OVERNIGHT = datetime(2026, 7, 23, 22, 0, tzinfo=timezone.utc)   # 18:00 ET — NYSE closed
_THU_MIDDAY = datetime(2026, 7, 23, 15, 0, tzinfo=timezone.utc)      # 11:00 ET — NYSE open
_SAT = datetime(2026, 7, 25, 22, 0, tzinfo=timezone.utc)            # weekend


class OpenMarketsScopeTests(unittest.TestCase):
    def setUp(self):
        # Force the kill switch on regardless of the ambient env.
        self._env = patch.dict(os.environ, {"FLEET_SESSION_BIAS": "true"})
        self._env.start()

    def tearDown(self):
        self._env.stop()

    def test_overnight_excludes_us_stock_keeps_crypto(self):
        scope = fleet_planner._open_markets_scope(_THU_OVERNIGHT)
        self.assertIsNotNone(scope)
        self.assertIn("crypto", scope)         # 24x7, always open
        self.assertNotIn("us-stock", scope)    # NYSE closed at 18:00 ET

    def test_us_session_includes_us_stock(self):
        scope = fleet_planner._open_markets_scope(_THU_MIDDAY)
        self.assertIsNotNone(scope)
        self.assertIn("us-stock", scope)       # NYSE open at 11:00 ET
        self.assertIn("crypto", scope)

    def test_weekend_keeps_only_always_on_markets(self):
        scope = fleet_planner._open_markets_scope(_SAT)
        self.assertIsNotNone(scope)
        self.assertIn("crypto", scope)         # crypto trades weekends
        self.assertNotIn("us-stock", scope)
        self.assertNotIn("futures", scope)     # CME closed Saturday
        self.assertNotIn("forex", scope)       # FX closed Saturday

    def test_kill_switch_off_returns_none(self):
        with patch.dict(os.environ, {"FLEET_SESSION_BIAS": "0"}):
            self.assertIsNone(fleet_planner._open_markets_scope(_THU_OVERNIGHT))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
