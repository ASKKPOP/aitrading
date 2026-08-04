"""Breadth feed — keyless public CSV with degraded mode (tradermonty mining).

The feed supplies market-wide breadth to the us-stock desks; a fetch
failure serves the last good snapshot, a stale dataset advises nobody, and
BREADTH_FEED_ENABLED=0 kills it outright. Fetches are mocked — no live
HTTP (the quant-crypto live-data-leak lesson).
"""

from __future__ import annotations

import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import breadth_feed

_HEADER = ("Date,S&P500_Price,Breadth_Index_Raw,Breadth_Index_200MA,"
           "Breadth_Index_8MA,Breadth_200MA_Trend,Bearish_Signal,Is_Peak,"
           "Is_Trough,Is_Trough_8MA_Below_04,Breadth_50_Index_Raw,"
           "Breadth_50_Index_50MA,Breadth_50_Index_8MA,Breadth_50_MA_Trend,"
           "Bearish_Signal_50,Is_Peak_50,Is_Trough_50")


def _row(date: str, raw=0.70, ma200=0.62, ma8=0.69, trend=1,
         bearish=False, raw50=0.65) -> str:
    return (f"{date},741.69,{raw},{ma200},{ma8},{trend},{bearish},False,"
            f"False,False,{raw50},0.61,0.66,1,False,False,False")


def _csv(*rows: str) -> str:
    return "\n".join((_HEADER,) + rows)


def _resp(text: str, status: int = 200):
    class R:
        def raise_for_status(self):
            if status >= 400:
                raise RuntimeError(f"http {status}")
    R.text = text
    return R()


def _days_ago(n: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=n)).strftime("%Y-%m-%d")


class _Cache(unittest.TestCase):
    def setUp(self):
        breadth_feed._cache["at"] = 0.0
        breadth_feed._cache["row"] = None
        # conftest forces the feed off so no other test fetches the live
        # CSV; these tests exercise the feed itself, always with mocks.
        self._env = patch.dict(os.environ, {"BREADTH_FEED_ENABLED": "true"})
        self._env.start()

    def tearDown(self):
        self._env.stop()
        breadth_feed._cache["at"] = 0.0
        breadth_feed._cache["row"] = None


class BreadthFeedTests(_Cache):
    def test_disabled_never_fetches(self):
        with patch.dict(os.environ, {"BREADTH_FEED_ENABLED": "0"}), \
                patch("breadth_feed.requests.get",
                      side_effect=AssertionError("must not call")):
            self.assertIsNone(breadth_feed.latest_breadth())

    def test_parses_last_row_and_caches(self):
        text = _csv(_row(_days_ago(9), raw=0.30), _row(_days_ago(1)))
        with patch("breadth_feed.requests.get", return_value=_resp(text)) as g:
            b = breadth_feed.latest_breadth()
            self.assertEqual(b["date"], _days_ago(1))
            self.assertAlmostEqual(b["above_ma200"], 0.70)
            self.assertAlmostEqual(b["above_ma200_8ema"], 0.69)
            self.assertAlmostEqual(b["above_ma50"], 0.65)
            self.assertEqual(b["trend200"], 1)
            self.assertFalse(b["bearish"])
            self.assertFalse(b["pink_zone"])
            breadth_feed.latest_breadth()
            self.assertEqual(g.call_count, 1, "second read must hit the cache")

    def test_pink_zone_needs_falling_trend_and_fast_below_slow(self):
        text = _csv(_row(_days_ago(1), trend=-1, ma8=0.55, ma200=0.62))
        with patch("breadth_feed.requests.get", return_value=_resp(text)):
            self.assertTrue(breadth_feed.latest_breadth()["pink_zone"])
        self.setUp()
        # Falling trend alone is not the zone.
        text = _csv(_row(_days_ago(1), trend=-1, ma8=0.65, ma200=0.62))
        with patch("breadth_feed.requests.get", return_value=_resp(text)):
            self.assertFalse(breadth_feed.latest_breadth()["pink_zone"])

    def test_stale_dataset_advises_nobody(self):
        text = _csv(_row(_days_ago(breadth_feed.MAX_AGE_DAYS + 1)))
        with patch("breadth_feed.requests.get", return_value=_resp(text)):
            self.assertIsNone(breadth_feed.latest_breadth())

    def test_fetch_failure_serves_stale_then_none_when_cold(self):
        text = _csv(_row(_days_ago(1)))
        with patch("breadth_feed.requests.get", return_value=_resp(text)):
            self.assertIsNotNone(breadth_feed.latest_breadth())
        breadth_feed._cache["at"] = 0.0  # expire the TTL, keep the row
        with patch("breadth_feed.requests.get",
                   side_effect=RuntimeError("down")):
            b = breadth_feed.latest_breadth()
            self.assertIsNotNone(b, "a fetch failure must serve the snapshot")
        self.setUp()
        with patch("breadth_feed.requests.get",
                   side_effect=RuntimeError("down")):
            self.assertIsNone(breadth_feed.latest_breadth())

    def test_empty_or_garbage_csv_is_none_not_fatal(self):
        with patch("breadth_feed.requests.get", return_value=_resp(_HEADER)):
            self.assertIsNone(breadth_feed.latest_breadth())
        self.setUp()
        with patch("breadth_feed.requests.get",
                   return_value=_resp("not,a,breadth\nfile,at,all")):
            self.assertIsNone(breadth_feed.latest_breadth())


if __name__ == "__main__":
    unittest.main()
