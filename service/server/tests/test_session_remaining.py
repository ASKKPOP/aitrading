"""Session-remaining guard at compose time (2026-07-28).

Being open is not the same as being usable. Live: ORCL and CAT were composed
at 19:56:40 UTC — three minutes and twenty seconds before the NYSE close — got
one cycle each, then spent nine hours on `pre: market closed` until the idle
rail collected them. `is_market_open()` was true at that instant and told the
builder nothing useful.
"""

from __future__ import annotations

import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import fleet_planner as fp
import markets

# 2026-07-27 is a Monday. NYSE runs 09:30–16:00 ET = 13:30–20:00 UTC.
_CLOSE = datetime(2026, 7, 27, 20, 0, tzinfo=timezone.utc)


class SessionMinutesLeft(unittest.TestCase):
    def test_crypto_is_always_open(self):
        self.assertEqual(markets.session_minutes_left("crypto", _CLOSE, 120), 120)

    def test_the_orcl_moment(self):
        """19:56:40 UTC — open, but only ~3 minutes of session left."""
        t = _CLOSE - timedelta(minutes=3, seconds=20)
        self.assertTrue(markets.is_market_open("us-stock", t),
                        "the old check said 'open' here — that is the bug")
        self.assertLess(markets.session_minutes_left("us-stock", t, 60), 5)

    def test_mid_session_has_hours_left(self):
        t = _CLOSE - timedelta(hours=3)
        self.assertGreaterEqual(markets.session_minutes_left("us-stock", t, 240), 179)

    def test_closed_market_is_zero(self):
        t = _CLOSE + timedelta(hours=1)
        self.assertEqual(markets.session_minutes_left("us-stock", t, 120), 0)

    def test_never_exceeds_the_horizon(self):
        t = _CLOSE - timedelta(hours=5)
        self.assertLessEqual(markets.session_minutes_left("us-stock", t, 30), 30)


class ScopeExcludesAClosingMarket(unittest.TestCase):
    def setUp(self):
        self._env = {k: os.environ.get(k) for k in
                     ("FLEET_MIN_SESSION_MINUTES", "FLEET_SESSION_BIAS")}
        os.environ["FLEET_SESSION_BIAS"] = "true"
        os.environ["FLEET_MIN_SESSION_MINUTES"] = "60"

    def tearDown(self):
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_us_stock_dropped_three_minutes_before_the_close(self):
        t = _CLOSE - timedelta(minutes=3, seconds=20)
        scope = fp._open_markets_scope(t)
        self.assertNotIn("us-stock", scope or [],
                         "a market about to close must not take a slot")
        self.assertIn("crypto", scope or [], "24x7 markets stay available")

    def test_us_stock_kept_mid_session(self):
        scope = fp._open_markets_scope(_CLOSE - timedelta(hours=3))
        self.assertIn("us-stock", scope or [])

    def test_zero_disables_the_check(self):
        os.environ["FLEET_MIN_SESSION_MINUTES"] = "0"
        t = _CLOSE - timedelta(minutes=3, seconds=20)
        self.assertIn("us-stock", fp._open_markets_scope(t) or [],
                      "0 must restore the previous open/closed behaviour")

    def test_scope_never_comes_back_empty(self):
        """Emptying the universe would starve the fleet entirely."""
        os.environ["FLEET_MIN_SESSION_MINUTES"] = "10000"
        scope = fp._open_markets_scope(_CLOSE - timedelta(hours=3))
        self.assertTrue(scope is None or len(scope) > 0)

    def test_bad_env_falls_back_to_the_default(self):
        os.environ["FLEET_MIN_SESSION_MINUTES"] = "soon"
        self.assertEqual(fp._min_session_minutes(), 60)


if __name__ == "__main__":
    unittest.main()
