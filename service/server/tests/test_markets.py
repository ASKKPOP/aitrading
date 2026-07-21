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
        # 'options' used to stand in for an unknown market here; it is a real
        # market as of plan 13 phase 5, so this needs a value that is genuinely
        # absent from the registry.
        self.assertEqual(markets.normalize_market('warrants'), 'warrants')
        self.assertIsNone(markets.get_spec('warrants'))


class CapabilityTests(unittest.TestCase):
    def test_polymarket_is_tradeable_but_not_automatable(self):
        # Guards the historical VALID_MARKETS/VALID_RUN_MARKETS behavior.
        self.assertIn('polymarket', markets.tradeable_markets())
        self.assertNotIn('polymarket', markets.automatable_markets())

    def test_automatable_set_matches_legacy_plus_expansion_markets(self):
        self.assertEqual(markets.automatable_markets(),
                         ('a-stock', 'crypto', 'forex', 'futures', 'us-stock'))

    def test_options_are_tradeable_but_not_automatable(self):
        # A rule cannot express "roll to the next expiry", so runs may not
        # target an options contract even though a user can trade one by hand.
        self.assertIn('options', markets.tradeable_markets())
        self.assertNotIn('options', markets.automatable_markets())

    def test_polymarket_forbids_shorting(self):
        self.assertFalse(markets.supports_short('polymarket'))
        self.assertTrue(markets.supports_short('crypto'))

    def test_unknown_market_fails_open_on_short(self):
        self.assertTrue(markets.supports_short('nonsense'))

    def test_cash_markets_have_a_multiplier_of_one(self):
        for market in ('us-stock', 'crypto', 'polymarket', 'forex', 'a-stock'):
            self.assertEqual(markets.contract_multiplier(market), 1.0)
        self.assertEqual(markets.contract_multiplier('nonsense'), 1.0)

    def test_futures_multiplier_is_per_contract(self):
        # The whole point of the column: ES is $50 a point, so a naive
        # (exit - entry) * qty under-reports an ES trade by 50x.
        self.assertEqual(markets.contract_multiplier('futures', 'ES'), 50.0)
        self.assertEqual(markets.contract_multiplier('futures', 'MES'), 5.0)
        self.assertEqual(markets.contract_multiplier('futures', 'GC'), 100.0)
        self.assertEqual(markets.contract_multiplier('futures', 'CL'), 1000.0)
        # Yahoo-suffixed form resolves identically.
        self.assertEqual(markets.contract_multiplier('futures', 'ES=F'), 50.0)
        # An unlisted root falls back rather than raising.
        self.assertEqual(markets.contract_multiplier('futures', 'ZZZ'), 1.0)

    def test_equity_options_are_one_hundred_shares(self):
        self.assertEqual(
            markets.contract_multiplier('options', 'AAPL260720C00205000'), 100.0)


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


class CmeSessionTests(unittest.TestCase):
    """Globex runs Sunday 18:00 ET to Friday 17:00 ET, halting 17:00-18:00 daily."""

    def test_open_midweek_overnight(self):
        # Wednesday 03:00 ET — equities closed, futures trading.
        at = datetime(2026, 7, 22, 3, 0, tzinfo=ET)
        self.assertTrue(markets.is_market_open('futures', at))
        self.assertFalse(markets.is_market_open('us-stock', at))

    def test_daily_maintenance_halt(self):
        # The hour that distinguishes CME from 24x5 forex.
        self.assertTrue(markets.is_market_open('futures', datetime(2026, 7, 22, 16, 59, tzinfo=ET)))
        self.assertFalse(markets.is_market_open('futures', datetime(2026, 7, 22, 17, 0, tzinfo=ET)))
        self.assertFalse(markets.is_market_open('futures', datetime(2026, 7, 22, 17, 59, tzinfo=ET)))
        self.assertTrue(markets.is_market_open('futures', datetime(2026, 7, 22, 18, 0, tzinfo=ET)))
        # Forex has no such break — same instant, different answer.
        self.assertTrue(markets.is_market_open('forex', datetime(2026, 7, 22, 17, 30, tzinfo=ET)))

    def test_friday_closes_without_reopening(self):
        self.assertTrue(markets.is_market_open('futures', datetime(2026, 7, 24, 16, 59, tzinfo=ET)))
        self.assertFalse(markets.is_market_open('futures', datetime(2026, 7, 24, 17, 0, tzinfo=ET)))
        self.assertFalse(markets.is_market_open('futures', datetime(2026, 7, 24, 18, 30, tzinfo=ET)))

    def test_saturday_closed_all_day(self):
        for hour in (0, 12, 23):
            self.assertFalse(markets.is_market_open('futures', datetime(2026, 7, 25, hour, 0, tzinfo=ET)))

    def test_sunday_reopens_at_eighteen(self):
        # An hour later than forex, which is the easy off-by-one here.
        self.assertFalse(markets.is_market_open('futures', datetime(2026, 7, 26, 17, 0, tzinfo=ET)))
        self.assertTrue(markets.is_market_open('futures', datetime(2026, 7, 26, 18, 0, tzinfo=ET)))
        self.assertTrue(markets.is_market_open('forex', datetime(2026, 7, 26, 17, 0, tzinfo=ET)))


class SseSessionTests(unittest.TestCase):
    """Shanghai/Shenzhen: 09:30-11:30 and 13:00-15:00 China Standard Time."""

    CST = ZoneInfo('Asia/Shanghai')

    def test_morning_and_afternoon_sessions(self):
        self.assertTrue(markets.is_market_open('a-stock', datetime(2026, 7, 21, 10, 0, tzinfo=self.CST)))
        self.assertTrue(markets.is_market_open('a-stock', datetime(2026, 7, 21, 14, 0, tzinfo=self.CST)))

    def test_midday_break_is_closed(self):
        # The feature no other calendar in the registry has.
        self.assertFalse(markets.is_market_open('a-stock', datetime(2026, 7, 21, 12, 0, tzinfo=self.CST)))
        self.assertTrue(markets.is_market_open('a-stock', datetime(2026, 7, 21, 11, 29, tzinfo=self.CST)))
        self.assertFalse(markets.is_market_open('a-stock', datetime(2026, 7, 21, 11, 30, tzinfo=self.CST)))
        self.assertFalse(markets.is_market_open('a-stock', datetime(2026, 7, 21, 12, 59, tzinfo=self.CST)))
        self.assertTrue(markets.is_market_open('a-stock', datetime(2026, 7, 21, 13, 0, tzinfo=self.CST)))

    def test_boundaries(self):
        self.assertFalse(markets.is_market_open('a-stock', datetime(2026, 7, 21, 9, 29, tzinfo=self.CST)))
        self.assertTrue(markets.is_market_open('a-stock', datetime(2026, 7, 21, 9, 30, tzinfo=self.CST)))
        self.assertTrue(markets.is_market_open('a-stock', datetime(2026, 7, 21, 14, 59, tzinfo=self.CST)))
        self.assertFalse(markets.is_market_open('a-stock', datetime(2026, 7, 21, 15, 0, tzinfo=self.CST)))

    def test_weekday_comes_from_the_shanghai_clock_not_new_york(self):
        # Monday 10:00 CST is Sunday 22:00 ET. Deriving the weekday from ET
        # would read this as a weekend and close the market.
        monday_open = datetime(2026, 7, 20, 10, 0, tzinfo=self.CST)
        self.assertEqual(monday_open.astimezone(ET).weekday(), 6)  # Sunday in ET
        self.assertTrue(markets.is_market_open('a-stock', monday_open))

        # And the mirror: Saturday 10:00 CST is Friday 22:00 ET — still closed.
        saturday = datetime(2026, 7, 25, 10, 0, tzinfo=self.CST)
        self.assertEqual(saturday.astimezone(ET).weekday(), 4)  # Friday in ET
        self.assertFalse(markets.is_market_open('a-stock', saturday))

    def test_closed_on_weekend(self):
        self.assertFalse(markets.is_market_open('a-stock', datetime(2026, 7, 25, 10, 0, tzinfo=self.CST)))
        self.assertFalse(markets.is_market_open('a-stock', datetime(2026, 7, 26, 10, 0, tzinfo=self.CST)))


class UnknownMarketTests(unittest.TestCase):
    def test_unknown_market_fails_open(self):
        # Matches the prior routes_shared.is_market_open fallback.
        self.assertTrue(markets.is_market_open('warrants', datetime(2026, 7, 25, 3, 0, tzinfo=ET)))


if __name__ == '__main__':
    unittest.main()
