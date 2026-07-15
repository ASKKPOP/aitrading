"""Macro event calendar (card 07) + cross-market spreads (card 16).

All tests are offline: market_events is pure static computation, and
cross_market's fetchers are mocked.
"""
import os
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))


class EventCalendarTests(unittest.TestCase):
    def test_upcoming_events_sorted_and_future_only(self):
        from market_events import upcoming_events
        now = datetime(2026, 7, 15, 0, 0, tzinfo=timezone.utc)
        events = upcoming_events(now, limit=5)
        self.assertTrue(events)
        ats = [e["at"] for e in events]
        self.assertEqual(ats, sorted(ats))
        for e in events:
            self.assertGreater(e["hours_until"], 0)

    def test_next_event_after_jul_15_2026_is_fomc_jul_29(self):
        from market_events import upcoming_events
        now = datetime(2026, 7, 15, 0, 0, tzinfo=timezone.utc)
        first = upcoming_events(now, limit=1)[0]
        self.assertEqual(first["event_type"], "fomc")
        # 14:00 ET on Jul 29 is 18:00 UTC (EDT).
        self.assertEqual(first["at"], "2026-07-29T18:00:00Z")

    def test_dst_conversion_winter_fomc_is_19_utc(self):
        from market_events import upcoming_events
        now = datetime(2026, 12, 1, 0, 0, tzinfo=timezone.utc)
        first = upcoming_events(now, limit=1)[0]
        # Dec 4 NFP at 08:30 ET = 13:30 UTC (EST); Dec 9 FOMC 14:00 ET = 19:00 UTC.
        self.assertEqual(first["at"], "2026-12-04T13:30:00Z")
        fomc = [e for e in upcoming_events(now, limit=8) if e["event_type"] == "fomc"][0]
        self.assertEqual(fomc["at"], "2026-12-09T19:00:00Z")

    def test_event_window_detection_and_boundaries(self):
        from market_events import active_event_window
        # FOMC 2026-07-29 18:00 UTC, default window ±60min.
        inside = active_event_window(datetime(2026, 7, 29, 17, 30, tzinfo=timezone.utc))
        self.assertIsNotNone(inside)
        self.assertEqual(inside["event_type"], "fomc")
        self.assertEqual(inside["minutes_to_release"], 30.0)
        at_start = active_event_window(datetime(2026, 7, 29, 17, 0, tzinfo=timezone.utc))
        self.assertIsNotNone(at_start)
        before = active_event_window(datetime(2026, 7, 29, 15, 59, tzinfo=timezone.utc))
        self.assertIsNone(before)
        after = active_event_window(datetime(2026, 7, 29, 19, 1, tzinfo=timezone.utc))
        self.assertIsNone(after)

    def test_payload_shape(self):
        from market_events import build_events_payload
        p = build_events_payload(datetime(2026, 7, 15, tzinfo=timezone.utc))
        self.assertTrue(p["available"])
        self.assertIn("next", p)
        self.assertIn("recent", p)
        self.assertIn("event_window", p)
        self.assertEqual(p["window_minutes"], {"before": 60, "after": 60})


class EventGuardTests(unittest.TestCase):
    def test_guard_off_by_default(self):
        from automation import _event_guard_blocks
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("EVENT_GUARD_ENABLED", None)
            self.assertIsNone(_event_guard_blocks())

    def test_guard_blocks_inside_window(self):
        from automation import _event_guard_blocks
        fake_window = {
            "event_type": "fomc", "title": "FOMC rate decision",
            "at": "2026-07-29T18:00:00Z",
            "window_start": "2026-07-29T17:00:00Z",
            "window_end": "2026-07-29T19:00:00Z",
            "minutes_to_release": 30.0,
        }
        with patch.dict(os.environ, {"EVENT_GUARD_ENABLED": "true"}):
            with patch("market_events.active_event_window", return_value=fake_window):
                reason = _event_guard_blocks()
        self.assertIsNotNone(reason)
        self.assertIn("FOMC", reason)

    def test_guard_fails_open_on_error(self):
        from automation import _event_guard_blocks
        with patch.dict(os.environ, {"EVENT_GUARD_ENABLED": "true"}):
            with patch("market_events.active_event_window", side_effect=RuntimeError("boom")):
                self.assertIsNone(_event_guard_blocks())


class CrossMarketTests(unittest.TestCase):
    def test_disabled_by_default(self):
        import cross_market
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CROSS_MARKET_ENABLED", None)
            p = cross_market.build_cross_market_payload()
        self.assertFalse(p["available"])

    def test_kimchi_premium_math(self):
        import cross_market
        with patch.dict(os.environ, {"CROSS_MARKET_ENABLED": "true"}):
            with patch.object(cross_market, "fetch_upbit_krw_btc", return_value=97_500_000.0), \
                 patch.object(cross_market, "fetch_usdkrw", return_value=1500.0), \
                 patch.object(cross_market, "fetch_global_btc_usd", return_value=63_106.8), \
                 patch.object(cross_market, "fetch_dollar_index", return_value=None):
                p = cross_market.build_cross_market_payload()
        k = p["kimchi"]
        # upbit_usd = 97.5M / 1500 = 65000; premium = (65000-63106.8)/63106.8 ≈ +3.0%
        self.assertAlmostEqual(k["upbit_usd_equiv"], 65000.0, places=2)
        self.assertAlmostEqual(k["premium_pct"], 3.0, places=1)
        self.assertEqual(k["verdict"], "overheated")

    def test_kimchi_discount_verdict(self):
        import cross_market
        with patch.dict(os.environ, {"CROSS_MARKET_ENABLED": "true"}):
            with patch.object(cross_market, "fetch_upbit_krw_btc", return_value=94_000_000.0), \
                 patch.object(cross_market, "fetch_usdkrw", return_value=1500.0), \
                 patch.object(cross_market, "fetch_global_btc_usd", return_value=64_000.0), \
                 patch.object(cross_market, "fetch_dollar_index", return_value=None):
                p = cross_market.build_cross_market_payload()
        # upbit_usd = 62666.67 → premium ≈ -2.08% → discount
        self.assertEqual(p["kimchi"]["verdict"], "discount")

    def test_partial_source_failure_nulls_kimchi_only(self):
        import cross_market
        dxy = {"series": "DTWEXBGS", "value": 120.5, "change_1d_pct": -0.2, "date": "2026-07-14"}
        with patch.dict(os.environ, {"CROSS_MARKET_ENABLED": "true"}):
            with patch.object(cross_market, "fetch_upbit_krw_btc", return_value=None), \
                 patch.object(cross_market, "fetch_usdkrw", return_value=1500.0), \
                 patch.object(cross_market, "fetch_global_btc_usd", return_value=64_000.0), \
                 patch.object(cross_market, "fetch_dollar_index", return_value=dxy):
                p = cross_market.build_cross_market_payload()
        self.assertTrue(p["available"])
        self.assertIsNone(p["kimchi"])
        self.assertEqual(p["dollar_index"]["value"], 120.5)


class QuantPositioningTests(unittest.TestCase):
    def test_crowded_long_ratio_is_risk_factor(self):
        from quant_crypto import LS_CROWDED_LONG
        self.assertGreaterEqual(LS_CROWDED_LONG, 1.5)

    def test_build_crypto_analysis_carries_positioning_fields(self):
        import quant_crypto as qc

        def fake_candles(symbol, bar="1D", limit=100):
            closes = [100 + i * 0.1 for i in range(limit)]
            return [{"ts": i, "open": c, "high": c, "low": c, "close": c, "volume": 10.0}
                    for i, c in enumerate(closes)]

        with patch("crypto_feed.fetch_candles", side_effect=fake_candles), \
             patch("crypto_feed.fetch_funding_rate", return_value={"funding_rate": 0.0001}), \
             patch("crypto_feed.fetch_ticker", return_value={"last_price": "110.0"}), \
             patch("crypto_feed.fetch_spot_ticker", return_value={"last_price": 109.0}), \
             patch("crypto_feed.fetch_open_interest",
                   return_value={"open_interest": 100.0, "open_interest_ccy": 50.0, "ts": 1}), \
             patch("crypto_feed.fetch_long_short_ratio",
                   return_value={"long_short_ratio": 2.5, "ts": 1}):
            out = qc.build_crypto_analysis("BTC")

        self.assertEqual(out["long_short_ratio"], 2.5)
        self.assertIsNotNone(out["open_interest_usd"])
        self.assertTrue(any("crowded long" in r for r in out["risk_factors"]))


if __name__ == "__main__":
    unittest.main()


class SosoValueEtfTests(unittest.TestCase):
    _ROWS = [
        {"date": "2026-07-14", "total_net_inflow": 1.81e8, "total_value_traded": 2.3e9,
         "total_net_assets": 7.79e10, "cum_net_inflow": 5.10e10},
        {"date": "2026-07-13", "total_net_inflow": -4.24e8, "total_value_traded": 2.0e9,
         "total_net_assets": 7.47e10, "cum_net_inflow": 5.08e10},
        {"date": "2026-07-10", "total_net_inflow": 9.0e7, "total_value_traded": 1.4e9,
         "total_net_assets": 7.74e10, "cum_net_inflow": 5.12e10},
    ]

    def test_disabled_without_key(self):
        import sosovalue_etf
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SOSOVALUE_API_KEY", None)
            self.assertIsNone(sosovalue_etf.build_real_flow_summary())

    def test_real_summary_from_rows(self):
        import sosovalue_etf
        with patch.dict(os.environ, {"SOSOVALUE_API_KEY": "k"}):
            with patch.object(sosovalue_etf, "fetch_summary_history", return_value=list(self._ROWS)):
                s = sosovalue_etf.build_real_flow_summary()
        self.assertEqual(s["direction"], "inflow")
        self.assertFalse(s["is_estimated"])
        self.assertEqual(s["btc"]["latest_net_inflow_usd"], 181000000.0)
        self.assertEqual(s["btc"]["streak_days"], 1)   # +181M then -424M breaks the streak
        self.assertIn("$181M", s["summary"])

    def test_outflow_streak(self):
        import sosovalue_etf
        rows = [
            {"date": "2026-07-14", "total_net_inflow": -1e8, "cum_net_inflow": 1, "total_net_assets": 1},
            {"date": "2026-07-13", "total_net_inflow": -2e8, "cum_net_inflow": 1, "total_net_assets": 1},
            {"date": "2026-07-10", "total_net_inflow": -3e8, "cum_net_inflow": 1, "total_net_assets": 1},
            {"date": "2026-07-09", "total_net_inflow": 5e7, "cum_net_inflow": 1, "total_net_assets": 1},
        ]
        with patch.dict(os.environ, {"SOSOVALUE_API_KEY": "k"}):
            with patch.object(sosovalue_etf, "fetch_summary_history", return_value=rows):
                s = sosovalue_etf.build_real_flow_summary()
        self.assertEqual(s["direction"], "outflow")
        self.assertEqual(s["btc"]["streak_days"], -3)
        self.assertIn("3 consecutive days of outflows", s["summary"])

    def test_fetch_failure_returns_none(self):
        import sosovalue_etf
        with patch.dict(os.environ, {"SOSOVALUE_API_KEY": "k"}):
            with patch.object(sosovalue_etf, "fetch_summary_history", side_effect=RuntimeError("api down")):
                self.assertIsNone(sosovalue_etf.build_real_flow_summary())


class RealLiquidationTests(unittest.TestCase):
    def test_aggregation_math_and_window(self):
        from psych_feed import aggregate_liquidations
        now_ms = 1_784_150_000_000
        rows = [
            # inside window: 2 contracts x 0.01 x 64000 = $1,280 (long side)
            {"price": 64000.0, "contracts": 2.0, "pos_side": "long", "ts": now_ms - 10 * 60 * 1000},
            # inside window: short, 5 x 0.01 x 65000 = $3,250
            {"price": 65000.0, "contracts": 5.0, "pos_side": "short", "ts": now_ms - 30 * 60 * 1000},
            # outside window (2h old) — ignored
            {"price": 64000.0, "contracts": 100.0, "pos_side": "long", "ts": now_ms - 120 * 60 * 1000},
        ]
        agg = aggregate_liquidations(rows, ct_val=0.01, now_ms=now_ms, window_minutes=60)
        self.assertEqual(agg["liq_count_1h"], 2)
        self.assertEqual(agg["long_liq_usd_1h"], 1280.0)
        self.assertEqual(agg["short_liq_usd_1h"], 3250.0)
        self.assertEqual(agg["liq_notional_usd_1h"], 4530.0)

    def test_merge_marks_real_and_flags_cascade(self):
        import psych_feed
        proxy = {"symbol": "BTCUSDT", "sigma_multiple": 1.0, "volume_ratio": 1.0,
                 "shock": False, "estimated": True}
        big_rows = [{"price": 64000.0, "contracts": 1000.0, "pos_side": "long",
                     "ts": 10 ** 15}]  # far future ts → inside any window
        with patch("crypto_feed.fetch_liquidation_orders", return_value=big_rows), \
             patch("crypto_feed.fetch_instrument_ct_val", return_value=0.01):
            out = psych_feed._merge_real_liquidations(dict(proxy), "BTCUSDT")
        # 1000 x 0.01 x 64000 = $640,000 < $5M default → no cascade shock
        self.assertFalse(out["shock"])
        self.assertFalse(out["estimated"])
        self.assertEqual(out["liq_source"], "okx")
        # 10x bigger → crosses the $5M threshold
        big_rows[0]["contracts"] = 10_000.0
        with patch("crypto_feed.fetch_liquidation_orders", return_value=big_rows), \
             patch("crypto_feed.fetch_instrument_ct_val", return_value=0.01):
            out2 = psych_feed._merge_real_liquidations(dict(proxy), "BTCUSDT")
        self.assertTrue(out2["shock"])

    def test_merge_fails_soft_to_proxy(self):
        import psych_feed
        proxy = {"symbol": "BTCUSDT", "shock": True, "estimated": True}
        with patch("crypto_feed.fetch_liquidation_orders", side_effect=RuntimeError("okx down")):
            out = psych_feed._merge_real_liquidations(dict(proxy), "BTCUSDT")
        self.assertTrue(out["estimated"])   # unchanged proxy
        self.assertNotIn("liq_source", out)
