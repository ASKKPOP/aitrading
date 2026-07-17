"""Tests for regime.py — regime classification, persistence, breaker safety."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
from regime import compute_regime, rolling_sigma_series, vol_percentile


class ComputeRegimeTests(unittest.TestCase):
    """Every band from the module table, boundaries half-open."""

    def _r(self, fng=50, vol=30.0, shock=False, event=False):
        return compute_regime(fng_value=fng, vol_pct=vol,
                              unresolved_shock=shock, event_window_active=event)

    def test_trend(self):
        r = self._r(fng=50, vol=30.0)
        self.assertEqual(r["regime"], "trend")
        self.assertTrue(r["allow_new_buys"])
        self.assertEqual(r["size_multiplier"], 1.0)

    def test_caution_bands(self):
        for fng, vol in [(25, 30.0), (75, 30.0), (50, 75.0)]:
            r = self._r(fng=fng, vol=vol)
            self.assertEqual(r["regime"], "caution", f"fng={fng} vol={vol}")
            self.assertTrue(r["allow_new_buys"])
            self.assertEqual(r["size_multiplier"], 0.5)

    def test_panic_triggers(self):
        for kwargs in [dict(fng=15), dict(vol=95.0), dict(shock=True)]:
            r = self._r(**kwargs)
            self.assertEqual(r["regime"], "panic", str(kwargs))
            self.assertFalse(r["allow_new_buys"])

    def test_euphoria(self):
        r = self._r(fng=85)
        self.assertEqual(r["regime"], "euphoria")
        self.assertFalse(r["allow_new_buys"])

    def test_event_overrides_everything(self):
        r = self._r(fng=15, vol=95.0, shock=True, event=True)
        self.assertEqual(r["regime"], "event")
        self.assertFalse(r["allow_new_buys"])

    def test_boundaries_half_open(self):
        self.assertEqual(self._r(fng=30)["regime"], "trend")
        self.assertEqual(self._r(fng=29)["regime"], "caution")
        self.assertEqual(self._r(fng=20)["regime"], "caution")
        self.assertEqual(self._r(fng=19)["regime"], "panic")
        self.assertEqual(self._r(fng=80)["regime"], "euphoria")
        self.assertEqual(self._r(fng=79)["regime"], "caution")
        self.assertEqual(self._r(vol=70.0)["regime"], "caution")
        self.assertEqual(self._r(vol=69.9)["regime"], "trend")
        self.assertEqual(self._r(vol=90.0)["regime"], "panic")

    def test_unknown_when_all_data_missing(self):
        r = compute_regime(fng_value=None, vol_pct=None,
                           unresolved_shock=False, event_window_active=False)
        self.assertEqual(r["regime"], "unknown")
        self.assertTrue(r["allow_new_buys"])
        self.assertEqual(r["size_multiplier"], 0.5)  # caution-sized

    def test_partial_data_is_unknown_not_trend(self):
        r = compute_regime(fng_value=50, vol_pct=None,
                           unresolved_shock=False, event_window_active=False)
        self.assertEqual(r["regime"], "unknown")


class VolPercentileTests(unittest.TestCase):
    def test_rolling_sigma_known_values(self):
        closes = []
        price = 100.0
        for i in range(60):
            price *= 1.01 if i % 2 == 0 else 0.99
            closes.append(price)
        series = rolling_sigma_series(closes, window=20)
        self.assertEqual(len(series), 60 - 1 - 20 + 1)
        for s in series:
            self.assertAlmostEqual(s, 1.0, delta=0.05)

    def test_percentile_rank(self):
        series = [1.0] * 99 + [5.0]  # latest is the max
        self.assertAlmostEqual(vol_percentile(series), 100.0)
        series2 = [float(i) for i in range(1, 101)] + [50.5]
        pct = vol_percentile(series2)
        self.assertAlmostEqual(pct, 50.0, delta=1.5)

    def test_too_short_series_returns_none(self):
        self.assertIsNone(vol_percentile([1.0] * 10))


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._old = database._SQLITE_DB_PATH
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()

    def tearDown(self):
        database._SQLITE_DB_PATH = self._old
        self.tmp.cleanup()

    def test_transition_recorded_only_on_change(self):
        from regime import _record_transition, current_regime_state
        _record_transition("trend", {"x": 1})
        _record_transition("trend", {"x": 2})  # same regime — no new row
        first = current_regime_state()
        _record_transition("panic", {"x": 3})
        second = current_regime_state()

        conn = database.get_db_connection()
        try:
            n = conn.cursor().execute("SELECT COUNT(*) AS n FROM regime_snapshots").fetchone()["n"]
        finally:
            conn.close()
        self.assertEqual(n, 2)
        self.assertEqual(first["regime"], "trend")
        self.assertEqual(second["regime"], "panic")
        self.assertIsNotNone(second["entered_at"])


class BreakerSafetyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._old = database._SQLITE_DB_PATH
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()

    def tearDown(self):
        database._SQLITE_DB_PATH = self._old
        self.tmp.cleanup()

    def test_auto_resume_clears_only_expired_auto_trips(self):
        from risk_engine import get_breaker, resume_expired_auto_breakers, trip_breaker
        trip_breaker("manual halt", scope="global")  # manual — never auto-cleared
        trip_breaker("auto shock", scope="market:crypto", tripped_by="auto",
                     expires_at="2000-01-01T00:00:00Z")  # long expired
        trip_breaker("auto fresh", scope="market:polymarket", tripped_by="auto",
                     expires_at="2999-01-01T00:00:00Z")  # not yet expired

        resumed = resume_expired_auto_breakers()
        self.assertEqual(resumed, 1)

        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            rows = {r["scope"]: r["state"] for r in
                    cur.execute("SELECT scope, state FROM breaker_state").fetchall()}
        finally:
            conn.close()
        self.assertEqual(rows["global"], "halted", "manual halt must survive")
        self.assertEqual(rows["market:crypto"], "normal", "expired auto-trip cleared")
        self.assertEqual(rows["market:polymarket"], "halted", "unexpired auto-trip kept")
        self.assertIn("global", str(get_breaker()))

    def test_sells_pass_auto_trips_but_not_manual_halts(self):
        from risk_engine import evaluate_order, trip_breaker
        with patch.dict(os.environ, {"RISK_ENGINE_ENABLED": "true"}):
            # seed an agent row so equity math doesn't explode
            conn = database.get_db_connection()
            try:
                cur = conn.cursor()
                cur.execute("INSERT INTO agents (name, token, cash) VALUES ('t', 'tok', 100000)")
                agent_id = cur.lastrowid
                conn.commit()
            finally:
                conn.close()

            trip_breaker("auto shock", scope="market:crypto", tripped_by="auto",
                         expires_at="2999-01-01T00:00:00Z")
            sell = evaluate_order(agent_id, "BTC", "crypto", "sell", 1.0, 100.0)
            self.assertTrue(sell.allowed, "sell must pass an AUTO trip")
            buy = evaluate_order(agent_id, "BTC", "crypto", "buy", 1.0, 100.0)
            self.assertFalse(buy.allowed, "buy must be blocked by the market auto trip")

            trip_breaker("manual", scope="global")
            sell2 = evaluate_order(agent_id, "BTC", "crypto", "sell", 1.0, 100.0)
            self.assertFalse(sell2.allowed, "manual HALT blocks even sells")

    def test_market_scope_does_not_block_other_markets(self):
        from risk_engine import evaluate_order, trip_breaker
        with patch.dict(os.environ, {"RISK_ENGINE_ENABLED": "true"}):
            conn = database.get_db_connection()
            try:
                cur = conn.cursor()
                cur.execute("INSERT INTO agents (name, token, cash) VALUES ('t2', 'tok2', 100000)")
                agent_id = cur.lastrowid
                conn.commit()
            finally:
                conn.close()
            trip_breaker("auto shock", scope="market:crypto", tripped_by="auto",
                         expires_at="2999-01-01T00:00:00Z")
            stock_buy = evaluate_order(agent_id, "AAPL", "us-stock", "buy", 1.0, 100.0)
            self.assertTrue(stock_buy.allowed, "crypto trip must not block us-stock")


class AutoTripTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._old = database._SQLITE_DB_PATH
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()

    def tearDown(self):
        database._SQLITE_DB_PATH = self._old
        self.tmp.cleanup()

    @staticmethod
    def _hist(real_flags):
        return [{"created_at": f"2099-01-01T0{i}:00:00Z",
                 "shocks": [{"symbol": "BTCUSDT", "shock": True, "estimated": not real}]}
                for i, real in enumerate(real_flags)]

    def test_two_consecutive_real_shocks_trip_market_breaker(self):
        from regime import maybe_auto_trip_market_breaker
        with patch.dict(os.environ, {"REGIME_FILTER_ENABLED": "true",
                                     "PSYCH_FEED_ENABLED": "true"}), \
             patch("psych_feed.shock_history", return_value=self._hist([True, True])):
            tripped = maybe_auto_trip_market_breaker()
        self.assertIsNotNone(tripped)
        self.assertEqual(tripped["scope"], "market:crypto")
        self.assertEqual(tripped["tripped_by"], "auto")
        self.assertIsNotNone(tripped["expires_at"])

    def test_single_or_estimated_shocks_never_trip(self):
        from regime import maybe_auto_trip_market_breaker
        cases = [self._hist([True]),           # only one reading
                 self._hist([False, True]),    # first is proxy-only
                 self._hist([True, False])]    # latest is proxy-only
        for hist in cases:
            with patch.dict(os.environ, {"REGIME_FILTER_ENABLED": "true",
                                         "PSYCH_FEED_ENABLED": "true"}), \
                 patch("psych_feed.shock_history", return_value=hist):
                self.assertIsNone(maybe_auto_trip_market_breaker())

    def test_noop_when_regime_filter_disabled(self):
        from regime import maybe_auto_trip_market_breaker
        with patch.dict(os.environ, {"REGIME_FILTER_ENABLED": "false"}), \
             patch("psych_feed.shock_history", return_value=self._hist([True, True])):
            self.assertIsNone(maybe_auto_trip_market_breaker())


if __name__ == "__main__":
    unittest.main()
