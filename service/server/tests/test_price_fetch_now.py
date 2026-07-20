"""executed_at=None means "price it now" — for EVERY market.

get_price_from_market(symbol, None, market) is the app's way of asking for a
current price: routes_runs._probe_price, run_engine (price_cross evaluation)
and trading_runs (closing a position at mark) all call it that way.

Three of the four providers honoured that; the alphavantage branch did not.
_get_us_stock_price typed executed_at as str and called .replace() on it,
which raises AttributeError on None — and the guard beside it only caught
ValueError. The exception escaped to get_price_from_market's broad handler,
so every us-stock lookup returned None and read as "unpriceable symbol",
regardless of API key or quota.

These tests pin the contract per market so a future provider cannot quietly
break it again.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import price_fetcher


class AlphaVantageNowTests(unittest.TestCase):
    """The PR #23 regression, kept as a direct test of the helper.

    us-stock no longer routes here (markets.py points it at yahoo), but
    _get_us_stock_price survives for the day Alpha Vantage is paid for, and the
    None-handling bug must not come back with it.
    """

    def test_none_timestamp_does_not_raise(self):
        with patch.object(price_fetcher, "_request_json_with_retry",
                          side_effect=AssertionError("should not be reached")):
            # Would previously raise AttributeError on None before any HTTP call.
            self.assertIsNone(price_fetcher._get_us_stock_price("AAPL", None))

    def test_none_timestamp_queries_current_month_and_returns_latest_bar(self):
        from datetime import datetime

        now_et = datetime.now(price_fetcher.UTC).astimezone(price_fetcher.ET_TZ)
        recent = now_et.strftime("%Y-%m-%d %H:%M:%S")
        older = now_et.replace(hour=4, minute=0, second=0).strftime("%Y-%m-%d %H:%M:%S")
        captured = {}

        def fake_request(provider, method, url, params=None, **kw):
            captured.update(params or {})
            return {"Time Series (1min)": {
                older: {"4. close": "180.00"},
                recent: {"4. close": "191.25"},
            }}

        with patch.object(price_fetcher, "_request_json_with_retry", fake_request):
            price = price_fetcher._get_us_stock_price("AAPL", None)

        self.assertEqual(price, 191.25)
        self.assertEqual(captured.get("month"), now_et.strftime("%Y-%m"))

    def test_explicit_timestamp_still_honoured(self):
        def fake_request(provider, method, url, params=None, **kw):
            return {"Time Series (1min)": {
                "2026-03-06 10:00:00": {"4. close": "150.00"},
                "2026-03-06 14:30:00": {"4. close": "160.00"},
                "2026-03-06 15:00:00": {"4. close": "170.00"},
            }}

        with patch.object(price_fetcher, "_request_json_with_retry", fake_request):
            price = price_fetcher._get_us_stock_price("AAPL", "2026-03-06T19:30:00Z")

        # 19:30Z == 14:30 ET — an exact bar match, not the later 15:00 one.
        self.assertEqual(price, 160.00)

    def test_malformed_timestamp_still_returns_none(self):
        with patch.object(price_fetcher, "_request_json_with_retry",
                          side_effect=AssertionError("should not be reached")):
            self.assertIsNone(price_fetcher._get_us_stock_price("AAPL", "not-a-date"))


class OtherProvidersHonourNoneTests(unittest.TestCase):
    """The contract the us-stock branch had drifted from."""

    def test_us_stock_none_routes_to_yahoo(self):
        with patch.object(price_fetcher, "_get_yahoo_chart_price",
                          return_value=333.74) as spy:
            self.assertEqual(
                price_fetcher.get_price_from_market("AAPL", None, "us-stock"), 333.74)
        self.assertIsNone(spy.call_args[0][1])

    def test_forex_none_uses_current_quote(self):
        with patch.object(price_fetcher, "_get_yahoo_chart_price",
                          return_value=1.1446) as spy:
            self.assertEqual(
                price_fetcher.get_price_from_market("EURUSD", None, "forex"), 1.1446)
        self.assertIsNone(spy.call_args[0][1])

    def test_crypto_none_falls_back_to_mid_price(self):
        with patch.object(price_fetcher, "_get_hyperliquid_candle_close",
                          return_value=None), \
             patch.object(price_fetcher, "_get_hyperliquid_mid_price",
                          return_value=64112.5):
            self.assertEqual(
                price_fetcher.get_price_from_market("BTC", None, "crypto"), 64112.5)

    def test_polymarket_none_ignores_timestamp(self):
        with patch.object(price_fetcher, "_get_polymarket_mid_price",
                          return_value=0.42):
            self.assertEqual(
                price_fetcher.get_price_from_market("some-slug", None, "polymarket"),
                0.42)


class YahooTickerShapeTests(unittest.TestCase):
    """us-stock symbols go to Yahoo now, and Yahoo spells share classes with a dash."""

    def test_share_class_dot_becomes_dash(self):
        # Measured 2026-07-20: BRK.B 404s, BRK-B returns a price.
        self.assertEqual(price_fetcher._yahoo_symbol("BRK.B", "us-stock"), "BRK-B")
        self.assertEqual(price_fetcher._yahoo_symbol("BF.B", "us-stock"), "BF-B")

    def test_plain_ticker_unchanged(self):
        self.assertEqual(price_fetcher._yahoo_symbol("AAPL", "us-stock"), "AAPL")
        self.assertEqual(price_fetcher._yahoo_symbol(" aapl ", "us-stock"), "AAPL")

    def test_empty_symbol_rejected(self):
        self.assertIsNone(price_fetcher._yahoo_symbol("", "us-stock"))
        self.assertIsNone(price_fetcher._yahoo_symbol(None, "us-stock"))

    def test_forex_shape_untouched_by_the_dash_rule(self):
        self.assertEqual(price_fetcher._yahoo_symbol("EURUSD", "forex"), "EURUSD=X")
        self.assertIsNone(price_fetcher._yahoo_symbol("EUR.USD", "forex"))


class RegistryRoutingTests(unittest.TestCase):
    def test_us_stock_provider_is_yahoo(self):
        import markets
        self.assertEqual(markets.REGISTRY["us-stock"].price_provider, "yahoo")

    def test_us_stock_stays_off_the_synchronous_trade_path(self):
        # server_priced=True would make the API reject a us-stock trade whenever
        # the price fetch fails; Yahoo has no 1m bars beyond ~7 days, so historical
        # signal submission (the backtest flow) depends on this staying False.
        import markets
        self.assertFalse(markets.REGISTRY["us-stock"].server_priced)


if __name__ == "__main__":
    unittest.main()
