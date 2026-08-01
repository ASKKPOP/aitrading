"""Plan 13 phases 3-5: futures and options.

Covers the parts that are cheap to get subtly wrong and expensive to notice:
the contract multiplier (a missing 50x is a silently wrong P&L, not a crash),
the OCC symbol parse, the option mark, and the FX conversion that stops a
non-USD P&L from being summed into a USD total as though it were dollars.

Every network call is stubbed — these must not depend on Yahoo being up.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
import fx_rates
import markets
import price_fetcher
import trading_runs
from routes import create_app
from routes_market import (
    FUTURES_SYMBOLS,
    OPTION_UNDERLYINGS,
    US_STOCK_SYMBOLS,
)


class SymbolUniverseTests(unittest.TestCase):
    def test_every_offered_future_has_a_multiplier(self):
        """The important one. A root missing from FUTURES_MULTIPLIERS prices at
        1.0, so an ES trade would book 1/50th of its real P&L — no error, just
        a wrong number."""
        missing = [s for s in FUTURES_SYMBOLS if s not in markets.FUTURES_MULTIPLIERS]
        self.assertEqual(missing, [], f"futures offered with no multiplier: {missing}")

    def test_multipliers_are_positive(self):
        for root, mult in markets.FUTURES_MULTIPLIERS.items():
            self.assertGreater(mult, 0, f"{root} has a non-positive multiplier")

    def test_option_underlyings_are_plain_tickers(self):
        for symbol in OPTION_UNDERLYINGS:
            self.assertRegex(symbol, r'^[A-Z]{1,6}$')

    def test_us_tickers_are_well_formed(self):
        # The list is hand-maintained, and the UI is selection-only: a typo'd
        # ticker becomes a dropdown option that no provider can price, which
        # surfaces only as a confusing rejection at run creation.
        for symbol in US_STOCK_SYMBOLS:
            self.assertRegex(symbol, r'^[A-Z]{1,5}(\.[A-Z])?$', symbol)

    def test_no_duplicate_us_tickers(self):
        dupes = sorted({s for s in US_STOCK_SYMBOLS
                        if US_STOCK_SYMBOLS.count(s) > 1})
        self.assertEqual(dupes, [], f"duplicate tickers offered: {dupes}")


class YahooSymbolTests(unittest.TestCase):
    def test_futures_root_gains_the_suffix_idempotently(self):
        self.assertEqual(price_fetcher._yahoo_symbol('ES', 'futures'), 'ES=F')
        self.assertEqual(price_fetcher._yahoo_symbol('ES=F', 'futures'), 'ES=F')
        self.assertEqual(price_fetcher._yahoo_symbol('es', 'futures'), 'ES=F')

    def test_share_class_dot_is_rewritten(self):
        # The us-stock branch rewrites '.' to '-' for share classes (BRK.B ->
        # BRK-B).
        self.assertEqual(price_fetcher._yahoo_symbol('BRK.B', 'us-stock'), 'BRK-B')

    def test_malformed_symbols_fail_fast(self):
        for symbol, market in [('', 'futures'),
                               ('ES!', 'futures'), ('EUR', 'forex')]:
            self.assertIsNone(price_fetcher._yahoo_symbol(symbol, market),
                              f'{symbol} ({market}) should not resolve')


def _contract(**kw):
    base = {'contractSymbol': 'AAPL260720C00205000', 'strike': 205.0,
            'bid': None, 'ask': None, 'lastPrice': None}
    base.update(kw)
    return base


class OptionMarkTests(unittest.TestCase):
    def test_mid_is_preferred_when_both_sides_are_quoted(self):
        self.assertEqual(price_fetcher._option_contract_price(
            _contract(bid=1.0, ask=2.0, lastPrice=99.0)), 1.5)

    def test_falls_back_to_last_when_the_book_is_empty(self):
        # Out of hours every strike is bid 0 / ask 0; mid would mark the book
        # to zero and wipe out the position.
        self.assertEqual(price_fetcher._option_contract_price(
            _contract(bid=0.0, ask=0.0, lastPrice=127.1)), 127.1)

    def test_one_sided_quote_falls_back_rather_than_halving(self):
        self.assertEqual(price_fetcher._option_contract_price(
            _contract(bid=3.0, ask=0.0, lastPrice=4.0)), 4.0)

    def test_no_price_at_all_is_none(self):
        self.assertIsNone(price_fetcher._option_contract_price(_contract()))


class OccSymbolTests(unittest.TestCase):
    def test_rejects_non_occ_symbols(self):
        for bad in ('AAPL', 'NOTANOPTION', '', 'AAPL260720X00205000'):
            self.assertIsNone(price_fetcher._get_yahoo_option_price(bad))

    def test_parses_root_expiry_right_and_strike(self):
        m = price_fetcher._OCC_RE.match('AAPL260720C00205000')
        self.assertIsNotNone(m)
        self.assertEqual(m.group('root'), 'AAPL')
        self.assertEqual(m.group('date'), '260720')
        self.assertEqual(m.group('right'), 'C')
        self.assertEqual(int(m.group('strike')) / 1000, 205.0)

    def test_requests_the_expiry_encoded_in_the_symbol(self):
        """Yahoo returns only the nearest expiry unless a date is passed, so a
        far-dated contract would never be found if the symbol's own expiry
        were not derived and sent."""
        with patch.object(price_fetcher, '_fetch_yahoo_option_chain',
                          return_value=None) as fetch:
            price_fetcher._get_yahoo_option_price('AAPL260720C00205000')
        underlying, expiry = fetch.call_args[0]
        self.assertEqual(underlying, 'AAPL')
        self.assertIsNotNone(expiry)

    def test_absent_contract_returns_none(self):
        chain = {'options': [{'calls': [_contract(contractSymbol='AAPL260720C00999000')]}]}
        with patch.object(price_fetcher, '_fetch_yahoo_option_chain', return_value=chain):
            self.assertIsNone(price_fetcher._get_yahoo_option_price('AAPL260720C00205000'))

    def test_matching_contract_is_priced(self):
        chain = {'options': [{'calls': [_contract(bid=2.0, ask=4.0)]}]}
        with patch.object(price_fetcher, '_fetch_yahoo_option_chain', return_value=chain):
            self.assertEqual(
                price_fetcher._get_yahoo_option_price('AAPL260720C00205000'), 3.0)

    def test_puts_are_read_from_the_put_side(self):
        put = _contract(contractSymbol='AAPL260720P00205000', bid=1.0, ask=3.0)
        chain = {'options': [{'calls': [], 'puts': [put]}]}
        with patch.object(price_fetcher, '_fetch_yahoo_option_chain', return_value=chain):
            self.assertEqual(
                price_fetcher._get_yahoo_option_price('AAPL260720P00205000'), 2.0)


class FuturesBookTests(unittest.TestCase):
    """The market_type/market naming collision plan 13 phase 3 flagged."""

    def test_crypto_perpetual_is_a_futures_book(self):
        self.assertTrue(trading_runs.is_futures_book('crypto', 'futures'))

    def test_cme_market_is_a_futures_book_without_the_flag(self):
        # The regression this predicate exists to prevent: a CME run carries
        # market_type='spot', so a market_type-only check would leave it unable
        # to ever open a short.
        self.assertTrue(trading_runs.is_futures_book('futures', 'spot'))
        self.assertTrue(trading_runs.is_futures_book('futures', None))

    def test_spot_markets_are_not(self):
        self.assertFalse(trading_runs.is_futures_book('crypto', 'spot'))
        self.assertFalse(trading_runs.is_futures_book('us-stock', None))


class FxConversionTests(unittest.TestCase):
    def setUp(self):
        fx_rates.reset_cache()

    def tearDown(self):
        fx_rates.reset_cache()

    def test_usd_is_identity_and_never_calls_the_feed(self):
        with patch.object(fx_rates, '_fetch_rate',
                          side_effect=AssertionError('should not fetch')):
            self.assertEqual(fx_rates.to_usd(100.0, 'USD'), 100.0)
            self.assertEqual(fx_rates.to_usd(100.0, None), 100.0)

    def test_converts_at_the_fetched_rate(self):
        with patch.object(fx_rates, '_fetch_rate', return_value=0.14):
            self.assertAlmostEqual(fx_rates.to_usd(1000.0, 'CNY'), 140.0)

    def test_rate_is_cached(self):
        with patch.object(fx_rates, '_fetch_rate', return_value=0.14) as fetch:
            fx_rates.to_usd(1.0, 'CNY')
            fx_rates.to_usd(1.0, 'CNY')
        self.assertEqual(fetch.call_count, 1)

    def test_feed_failure_falls_back_to_a_seed_rate(self):
        # A dead rate provider must not make a CNY balance read as USD, which
        # would overstate it ~7x.
        with patch.object(fx_rates, '_fetch_rate', return_value=None):
            converted = fx_rates.to_usd(1000.0, 'CNY')
        self.assertLess(converted, 1000.0)
        self.assertGreater(converted, 0.0)

    def test_feed_exception_never_propagates(self):
        with patch.object(fx_rates, '_fetch_rate', side_effect=RuntimeError('boom')):
            self.assertGreater(fx_rates.to_usd(1000.0, 'CNY'), 0.0)

    def test_unknown_currency_is_passed_through_unconverted(self):
        with patch.object(fx_rates, '_fetch_rate', return_value=None):
            self.assertEqual(fx_rates.to_usd(50.0, 'XYZ'), 50.0)

    def test_stale_rate_is_reused_when_a_refresh_fails(self):
        with patch.object(fx_rates, '_fetch_rate', return_value=0.20):
            fx_rates.to_usd(1.0, 'CNY')
        fx_rates._CACHE['CNY'] = (0.20, 0.0)  # force expiry
        with patch.object(fx_rates, '_fetch_rate', return_value=None):
            self.assertAlmostEqual(fx_rates.to_usd(100.0, 'CNY'), 20.0)


class MarketExpansionRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_symbols_endpoint_exposes_the_new_universes(self):
        with patch('price_fetcher._get_hyperliquid_available_symbols', return_value=set()):
            body = self.client.get('/api/markets/symbols').json()
        self.assertIn('ES', body['futures'])
        self.assertIn('AAPL', body['option_underlyings'])

    def test_option_chain_rejects_an_unlisted_underlying(self):
        self.assertEqual(self.client.get('/api/markets/options/NOTREAL').status_code, 404)

    def test_option_chain_is_shaped_for_the_picker(self):
        chain = {
            'quote': {'regularMarketPrice': 210.0},
            'expirationDates': [1784505600],
            'options': [{
                'expirationDate': 1784505600,
                'calls': [_contract(bid=2.0, ask=4.0, openInterest=12, inTheMoney=True)],
                'puts': [],
            }],
        }
        with patch('price_fetcher._fetch_yahoo_option_chain', return_value=chain):
            body = self.client.get('/api/markets/options/AAPL').json()
        self.assertEqual(body['underlying'], 'AAPL')
        self.assertEqual(body['contract_multiplier'], 100.0)
        self.assertEqual(body['expirations'], [1784505600])
        call = body['calls'][0]
        self.assertEqual(call['symbol'], 'AAPL260720C00205000')
        self.assertEqual(call['strike'], 205.0)
        # The picker must show the same mark the ledger would book.
        self.assertEqual(call['price'], 3.0)

    def test_option_chain_surfaces_provider_outage(self):
        with patch('price_fetcher._fetch_yahoo_option_chain', return_value=None):
            self.assertEqual(self.client.get('/api/markets/options/AAPL').status_code, 503)


if __name__ == '__main__':
    unittest.main()


class FuturesPnlTests(unittest.TestCase):
    """Futures P&L is USD-notional, NOT contract point value (World B).

    Reversed 2026-07-26. This class previously asserted the 50x point value
    ("one ES contract, +10 points = $500"), but nothing else in the system
    ever adopted that convention: automation sizes `quantity = size_usd /
    entry` (automation.py), run_engine.compute_run_pnl marks that quantity
    straight against price, and positions / realized_pnl_usd / every risk cap
    follow suit. Sizing routinely produces fractional "contracts" (0.267 ES),
    which is meaningless if qty were really contracts.

    Only risk_engine.trade_stats and backtest.py applied the point value, so
    the SAME trade was graded 50-1000x larger by the account risk gate than by
    the book that produced it:
        run 76 CL booked -$159.82  ->  risk_engine counted -$159,816
        run 83 ZW booked -$218.83  ->  risk_engine counted  -$10,942
    which is exactly the "realized today $-154,418" / "$-10,521" that tripped
    the daily-loss breaker 49 times in 7 days and hard-blocked every order.
    """

    _next_signal_id = 950000

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        os.environ["RISK_ENGINE_ENABLED"] = "true"
        self.client = TestClient(create_app())
        resp = self.client.post(
            "/api/claw/agents/selfRegister",
            json={"name": "fut-agent", "password": "pw123", "initial_balance": 100000.0},
        )
        assert resp.status_code == 200, resp.text
        self.agent_id = resp.json()["agent_id"]
        fx_rates.reset_cache()

    def tearDown(self) -> None:
        os.environ["RISK_ENGINE_ENABLED"] = "false"
        fx_rates.reset_cache()
        self.tmp.cleanup()

    def _signal(self, side, price, qty, when, symbol, market):
        FuturesPnlTests._next_signal_id += 1
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO signals
               (signal_id, agent_id, message_type, market, signal_type, symbol,
                side, entry_price, quantity, content, timestamp, created_at, executed_at)
               VALUES (?, ?, 'operation', ?, 'automation', ?, ?, ?, ?, 'test', 0, ?, ?)""",
            (FuturesPnlTests._next_signal_id, self.agent_id, market, symbol,
             side, price, qty, when, when),
        )
        conn.commit()
        conn.close()

    def _round_trip(self, entry, exit_, symbol, market, qty=1.0):
        from datetime import datetime, timedelta, timezone
        t0 = datetime.now(timezone.utc).replace(hour=1, minute=0, second=0, microsecond=0)
        fmt = "%Y-%m-%dT%H:%M:%SZ"
        self._signal("buy", entry, qty, t0.strftime(fmt), symbol, market)
        self._signal("sell", exit_, qty, (t0 + timedelta(minutes=1)).strftime(fmt),
                     symbol, market)

    def test_es_round_trip_books_usd_notional_not_point_value(self):
        import risk_engine
        # 1.0 "ES" of exposure is $7,500 of notional, not one 50x contract.
        # +10 points on that notional is $10 — the same arithmetic the run's
        # own book uses. Booking $500 here is what broke the risk gate.
        self._round_trip(7500.0, 7510.0, 'ES', 'futures')
        self.assertAlmostEqual(risk_engine.trade_stats(self.agent_id)["realized_today"],
                               10.0, places=6)

    def test_commodity_loss_matches_the_run_book_that_produced_it(self):
        """Regression for the 49 phantom daily-loss trips: CL carries a 1000x
        point value, so this $10 loss was being counted as $10,000."""
        import risk_engine
        self._round_trip(100.0, 90.0, 'CL', 'futures')
        self.assertAlmostEqual(risk_engine.trade_stats(self.agent_id)["realized_today"],
                               -10.0, places=6)

    def test_equity_round_trip_is_unchanged_by_the_multiplier_work(self):
        import risk_engine
        self._round_trip(100.0, 110.0, 'AAPL', 'us-stock', qty=3.0)
        self.assertAlmostEqual(risk_engine.trade_stats(self.agent_id)["realized_today"],
                               30.0, places=6)


class _Cookie:
    """Minimal stand-in for a requests cookie — the handshake only reads
    .name/.value when building the Cookie header."""

    def __init__(self, name, value):
        self.name = name
        self.value = value


class CrumbHandshakeTests(unittest.TestCase):
    """The Yahoo chain is the committed options feed, so the session handshake
    has to recover on its own. A crumb expires; if that is not retried, every
    option position silently stops being marked."""

    def setUp(self):
        price_fetcher._yahoo_crumb = None

    def tearDown(self):
        price_fetcher._yahoo_crumb = None

    @staticmethod
    def _http_error(status):
        import requests
        response = requests.Response()
        response.status_code = status
        return requests.HTTPError(f"{status} Client Error", response=response)

    def test_expired_crumb_is_refreshed_and_the_call_retried(self):
        chain = {'optionChain': {'result': [{'options': [{'calls': [], 'puts': []}]}]}}
        with patch.object(price_fetcher, '_yahoo_crumb_pair',
                          return_value=('A3=x', 'crumb')) as pair, \
             patch.object(price_fetcher, '_request_json_with_retry',
                          side_effect=[self._http_error(401), chain]) as req:
            result = price_fetcher._fetch_yahoo_option_chain('AAPL')
        self.assertIsNotNone(result)
        self.assertEqual(req.call_count, 2)
        # Second handshake must be forced, or the cached dead crumb is reused.
        self.assertTrue(pair.call_args_list[1].kwargs.get('force_refresh'))

    def test_a_non_auth_error_is_not_retried(self):
        # Retrying a 500 just doubles load on a provider already in trouble.
        with patch.object(price_fetcher, '_yahoo_crumb_pair',
                          return_value=('A3=x', 'crumb')), \
             patch.object(price_fetcher, '_request_json_with_retry',
                          side_effect=self._http_error(500)) as req:
            self.assertIsNone(price_fetcher._fetch_yahoo_option_chain('AAPL'))
        self.assertEqual(req.call_count, 1)

    def test_repeated_auth_failure_gives_up_rather_than_looping(self):
        with patch.object(price_fetcher, '_yahoo_crumb_pair',
                          return_value=('A3=x', 'crumb')), \
             patch.object(price_fetcher, '_request_json_with_retry',
                          side_effect=self._http_error(401)) as req:
            self.assertIsNone(price_fetcher._fetch_yahoo_option_chain('AAPL'))
        self.assertEqual(req.call_count, 2)

    def test_failed_handshake_returns_none_without_calling_the_chain(self):
        with patch.object(price_fetcher, '_yahoo_crumb_pair', return_value=None), \
             patch.object(price_fetcher, '_request_json_with_retry') as req:
            self.assertIsNone(price_fetcher._fetch_yahoo_option_chain('AAPL'))
        req.assert_not_called()

    def test_handshake_rejects_an_html_error_page_as_a_crumb(self):
        # getcrumb returning an HTML block would otherwise be sent as a token
        # and 401 every subsequent call.
        class _Resp:
            status_code = 200
            text = '<!DOCTYPE html><html>error</html>'

        session = MagicMock()
        session.get.return_value = _Resp()
        # A cookie IS issued here on purpose: without it the missing-cookie
        # guard short-circuits first and this stops testing crumb validation
        # at all (it silently did, until a mutation check caught it).
        session.cookies = [_Cookie('A3', 'x')]
        with patch.object(price_fetcher.requests, 'Session', return_value=session):
            self.assertIsNone(price_fetcher._yahoo_crumb_pair(force_refresh=True))

    def test_handshake_rejects_an_overlong_crumb(self):
        class _Resp:
            status_code = 200
            text = 'x' * 200  # a truncated page body, not a token

        session = MagicMock()
        session.get.return_value = _Resp()
        session.cookies = [_Cookie('A3', 'x')]
        with patch.object(price_fetcher.requests, 'Session', return_value=session):
            self.assertIsNone(price_fetcher._yahoo_crumb_pair(force_refresh=True))

    def test_handshake_accepts_a_well_formed_crumb(self):
        # The positive case, so the guards above cannot pass by rejecting
        # everything unconditionally.
        class _Resp:
            status_code = 200
            text = 'qTnhJZYOj2X'

        session = MagicMock()
        session.get.return_value = _Resp()
        session.cookies = [_Cookie('A3', 'abc')]
        with patch.object(price_fetcher.requests, 'Session', return_value=session):
            pair = price_fetcher._yahoo_crumb_pair(force_refresh=True)
        self.assertEqual(pair, ('A3=abc', 'qTnhJZYOj2X'))

    def test_handshake_rejects_a_missing_cookie(self):
        class _Resp:
            status_code = 200
            text = 'goodcrumb'

        session = MagicMock()
        session.get.return_value = _Resp()
        session.cookies = []  # no A3 issued
        with patch.object(price_fetcher.requests, 'Session', return_value=session):
            self.assertIsNone(price_fetcher._yahoo_crumb_pair(force_refresh=True))
