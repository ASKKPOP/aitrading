"""Maturity gate — young listings out of every non-swing us-stock build.

Owner 2026-08-13 ("yoojinbe got too much lost profit"): SPCX −$35.81 (42
daily bars) and QNT −$7.49 (48 bars) were refused by the swing gate's
180-bar floor and landed in the UNGATED short-archetype fleet 32, carrying
32% of the account's day loss. A listing under ~90 bars has no statistical
base any archetype can size against.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import fleet_planner as fp  # noqa: E402
import price_fetcher  # noqa: E402


def _bars(n):
    return [{"close": 10.0 + i * 0.01, "open": 10.0, "high": 10.1,
             "low": 9.9, "volume": 1_000_000} for i in range(n)]


def _thesis(symbol, market="us-stock"):
    return {"symbol": symbol, "market": market, "direction": "long"}


SHORT_FLEET = {"archetype": "short"}
SWING_FLEET = {"archetype": "swing"}


class MaturityGateTests(unittest.TestCase):
    def test_young_listing_is_dropped_for_short_archetype(self):
        # the SPCX shape: 42 bars against a 90-bar floor
        with patch.object(price_fetcher, "get_daily_candles",
                          return_value=_bars(42)):
            kept, dropped = fp.usstock_maturity_gate(
                SHORT_FLEET, [_thesis("SPCX")])
        self.assertEqual(kept, [])
        self.assertIn("SPCX", dropped)
        self.assertIn("listing_young: 42 bars < 90", dropped["SPCX"])

    def test_seasoned_listing_passes(self):
        with patch.object(price_fetcher, "get_daily_candles",
                          return_value=_bars(250)):
            kept, dropped = fp.usstock_maturity_gate(
                SHORT_FLEET, [_thesis("MSFT")])
        self.assertEqual(len(kept), 1)
        self.assertEqual(dropped, {})

    def test_non_usstock_markets_pass_untouched(self):
        with patch.object(price_fetcher, "get_daily_candles",
                          return_value=_bars(5)):
            kept, dropped = fp.usstock_maturity_gate(
                SHORT_FLEET, [_thesis("SOLUSDT", market="crypto")])
        self.assertEqual(len(kept), 1)
        self.assertEqual(dropped, {})

    def test_swing_fleets_skip_this_gate(self):
        """Swing runs its own stricter 180-bar check — no double fetch."""
        with patch.object(price_fetcher, "get_daily_candles",
                          side_effect=AssertionError("must not fetch")):
            kept, dropped = fp.usstock_maturity_gate(
                SWING_FLEET, [_thesis("SPCX")])
        self.assertEqual(len(kept), 1)

    def test_feed_error_fails_open(self):
        """A feed hiccup must not blank the day's universe."""
        with patch.object(price_fetcher, "get_daily_candles",
                          side_effect=RuntimeError("feed down")):
            kept, dropped = fp.usstock_maturity_gate(
                SHORT_FLEET, [_thesis("MSFT")])
        self.assertEqual(len(kept), 1)

    def test_env_zero_disables(self):
        import os
        os.environ["FLEET_USSTOCK_MIN_BARS"] = "0"
        try:
            with patch.object(price_fetcher, "get_daily_candles",
                              side_effect=AssertionError("must not fetch")):
                kept, _ = fp.usstock_maturity_gate(
                    SHORT_FLEET, [_thesis("SPCX")])
            self.assertEqual(len(kept), 1)
        finally:
            os.environ.pop("FLEET_USSTOCK_MIN_BARS")

    def test_wired_into_the_replacement_path(self):
        src = (Path(SERVER_DIR) / "fleet_supervisor.py").read_text()
        self.assertIn("usstock_maturity_gate", src,
                      "replacement path must consult the gate")

    def test_wired_into_the_build_path(self):
        src = (Path(SERVER_DIR) / "fleet_planner.py").read_text()
        self.assertEqual(src.count("usstock_maturity_gate(fleet, [thesis])"),
                         1, "build path must consult the gate")


if __name__ == "__main__":
    unittest.main()
