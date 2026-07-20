"""Tests for the market registry (docs/plan/13-market-expansion.md)."""

import os
import sys
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import markets  # noqa: E402


ET = ZoneInfo('America/New_York')


class NormalizeTests(unittest.TestCase):
    def test_aliases_resolve(self):
        self.assertEqual(markets.normalize_market('hyperliquid'), 'crypto')
        self.assertEqual(markets.normalize_market('NASDAQ'), 'us-stock')
        self.assertEqual(markets.normalize_market('  Equities  '), 'us-stock')
        self.assertEqual(markets.normalize_market('fx'), 'forex')

    def test_empty_defaults_to_us_stock(self):
        # Preserved from the original routes_shared.normalize_market contract.
        self.assertEqual(markets.normalize_market(None), 'us-stock')
        self.assertEqual(markets.normalize_market(''), 'us-stock')

    def test_unknown_passes_through(self):
        self.assertEqual(markets.normalize_market('options'), 'options')
        self.assertIsNone(markets.get_spec('options'))


class CapabilityTests(unittest.TestCase):
    def test_polymarket_is_tradeable_but_not_automatable(self):
        # Guards the historical VALID_MARKETS/VALID_RUN_MARKETS behavior.
        self.assertIn('polymarket', markets.tradeable_markets())
        self.assertNotIn('polymarket', markets.automatable_markets())

    def test_automatable_set_matches_legacy_plus_forex(self):
        self.assertEqual(markets.automatable_markets(), ('crypto', 'forex', 'us-stock'))

    def test_polymarket_forbids_shorting(self):
        self.assertFalse(markets.supports_short('polymarket'))
        self.assertTrue(markets.supports_short('crypto'))

    def test_unknown_market_fails_open_on_short(self):
        self.assertTrue(markets.supports_short('nonsense'))

    def test_multipliers_default_to_one(self):
        for market in markets.supported_markets():
            self.assertEqual(markets.contract_multiplier(market), 1.0)
        self.assertEqual(markets.contract_multiplier('nonsense'), 1.0)


class CurrencyTests(unittest.TestCase):
    def test_non_forex_markets_are_usd(self):
        self.assertEqual(markets.position_currency('us-stock', 'AAPL'), 'USD')
        self.assertEqual(markets.position_currency('crypto', 'BTC'), 'USD')

    def test_forex_currency_comes_from_the_pair(self):
        self.assertEqual(markets.position_currency('forex', 'EURUSD'), 'USD')
        self.assertEqual(markets.position_currency('forex', 'EURJPY'), 'JPY')
        self.assertEqual(markets.position_currency('forex', 'eurjpy'), 'JPY')
        self.assertEqual(markets.position_currency('forex', 'EUR/JPY'), 'JPY')

    def test_forex_falls_back_to_usd_on_malformed_symbol(self):
        self.assertEqual(markets.position_currency('forex', 'EUR'), 'USD')
        self.assertEqual(markets.position_currency('forex', None), 'USD')
        self.assertEqual(markets.position_currency('forex', 'EUR123'), 'USD')

    def test_unknown_market_is_usd(self):
        self.assertEqual(markets.position_currency('nonsense', 'X'), 'USD')


class NyseSessionTests(unittest.TestCase):
    def test_open_during_regular_hours(self):
        # Tuesday 10:00 ET
        self.assertTrue(markets.is_market_open('us-stock', datetime(2026, 7, 21, 10, 0, tzinfo=ET)))

    def test_boundaries(self):
        self.assertTrue(markets.is_market_open('us-stock', datetime(2026, 7, 21, 9, 30, tzinfo=ET)))
        self.assertFalse(markets.is_market_open('us-stock', datetime(2026, 7, 21, 9, 29, tzinfo=ET)))
        self.assertTrue(markets.is_market_open('us-stock', datetime(2026, 7, 21, 15, 59, tzinfo=ET)))
        self.assertFalse(markets.is_market_open('us-stock', datetime(2026, 7, 21, 16, 0, tzinfo=ET)))

    def test_closed_on_weekend(self):
        self.assertFalse(markets.is_market_open('us-stock', datetime(2026, 7, 25, 12, 0, tzinfo=ET)))
        self.assertFalse(markets.is_market_open('us-stock', datetime(2026, 7, 26, 12, 0, tzinfo=ET)))

    def test_crypto_always_open(self):
        self.assertTrue(markets.is_market_open('crypto', datetime(2026, 7, 26, 3, 0, tzinfo=ET)))
        self.assertTrue(markets.is_market_open('polymarket', datetime(2026, 7, 26, 3, 0, tzinfo=ET)))


class ForexSessionTests(unittest.TestCase):
    """Forex runs Sunday 17:00 ET through Friday 17:00 ET."""

    def test_open_midweek_overnight(self):
        # Wednesday 03:00 ET — closed for equities, open for FX.
        at = datetime(2026, 7, 22, 3, 0, tzinfo=ET)
        self.assertTrue(markets.is_market_open('forex', at))
        self.assertFalse(markets.is_market_open('us-stock', at))

    def test_friday_close(self):
        self.assertTrue(markets.is_market_open('forex', datetime(2026, 7, 24, 16, 59, tzinfo=ET)))
        self.assertFalse(markets.is_market_open('forex', datetime(2026, 7, 24, 17, 0, tzinfo=ET)))

    def test_saturday_closed_all_day(self):
        for hour in (0, 12, 23):
            self.assertFalse(markets.is_market_open('forex', datetime(2026, 7, 25, hour, 0, tzinfo=ET)))

    def test_sunday_reopen(self):
        self.assertFalse(markets.is_market_open('forex', datetime(2026, 7, 26, 16, 59, tzinfo=ET)))
        self.assertTrue(markets.is_market_open('forex', datetime(2026, 7, 26, 17, 0, tzinfo=ET)))

    def test_naive_and_other_timezones_are_converted(self):
        # Friday 21:00 UTC == 17:00 ET == closed.
        utc_close = datetime(2026, 7, 24, 21, 0, tzinfo=ZoneInfo('UTC'))
        self.assertFalse(markets.is_market_open('forex', utc_close))


class UnknownMarketTests(unittest.TestCase):
    def test_unknown_market_fails_open(self):
        # Matches the prior routes_shared.is_market_open fallback.
        self.assertTrue(markets.is_market_open('options', datetime(2026, 7, 25, 3, 0, tzinfo=ET)))


if __name__ == '__main__':
    unittest.main()
