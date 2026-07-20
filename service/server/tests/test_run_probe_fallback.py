"""_probe_price falls back to a recent position mark (Plan 10).

A live fetch failing does not mean the symbol is unpriceable: Alpha Vantage's
daily quota and its rate-limit cooldown take us-stock down wholesale, and
refusing run creation on that basis locks users out of a market that works.
A mark the refresher wrote minutes ago proves the symbol IS priceable.

The fallback is bounded by run_engine._mark_staleness_max() — the same limit
the stop evaluator fails closed on — so a mark too old to evaluate stops
against can never arm a run.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
import routes_runs
import run_engine


def _ts(age_seconds: float) -> str:
    dt = datetime.now(timezone.utc) - timedelta(seconds=age_seconds)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


class ProbePriceFallbackTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()

    def tearDown(self):
        self.tmp.cleanup()

    def _mark(self, symbol, market, price, age_seconds):
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO positions
               (agent_id, symbol, market, side, quantity, entry_price,
                current_price, price_updated_at, opened_at)
               VALUES (1, ?, ?, 'long', 1, ?, ?, ?, ?)""",
            (symbol, market, price, price, _ts(age_seconds), _ts(age_seconds)))
        conn.commit()
        conn.close()

    # ── a live fetch always wins ───────────────────────────────────────

    def test_live_price_preferred_over_mark(self):
        self._mark("AAPL", "us-stock", 100.0, age_seconds=10)
        with patch("price_fetcher.get_price_from_market", return_value=222.0):
            self.assertEqual(routes_runs._probe_price("AAPL", "us-stock"), 222.0)

    # ── fallback ───────────────────────────────────────────────────────

    def test_fresh_mark_used_when_fetch_returns_none(self):
        self._mark("AAPL", "us-stock", 190.5, age_seconds=60)
        with patch("price_fetcher.get_price_from_market", return_value=None):
            self.assertEqual(routes_runs._probe_price("AAPL", "us-stock"), 190.5)

    def test_fresh_mark_used_when_fetch_raises(self):
        self._mark("AAPL", "us-stock", 190.5, age_seconds=60)
        with patch("price_fetcher.get_price_from_market",
                   side_effect=RuntimeError("quota exhausted")):
            self.assertEqual(routes_runs._probe_price("AAPL", "us-stock"), 190.5)

    # ── the staleness bound is the whole safety argument ───────────────

    def test_stale_mark_rejected(self):
        stale = run_engine._mark_staleness_max() + 60
        self._mark("AAPL", "us-stock", 190.5, age_seconds=stale)
        with patch("price_fetcher.get_price_from_market", return_value=None):
            self.assertIsNone(routes_runs._probe_price("AAPL", "us-stock"))

    def test_mark_exactly_at_bound_accepted(self):
        self._mark("AAPL", "us-stock", 190.5,
                   age_seconds=run_engine._mark_staleness_max() - 5)
        with patch("price_fetcher.get_price_from_market", return_value=None):
            self.assertEqual(routes_runs._probe_price("AAPL", "us-stock"), 190.5)

    # ── the mark must actually be for this symbol AND market ───────────

    def test_no_mark_at_all_still_rejects(self):
        with patch("price_fetcher.get_price_from_market", return_value=None):
            self.assertIsNone(routes_runs._probe_price("AAPL", "us-stock"))

    def test_other_market_mark_not_borrowed(self):
        self._mark("AAPL", "crypto", 190.5, age_seconds=10)
        with patch("price_fetcher.get_price_from_market", return_value=None):
            self.assertIsNone(routes_runs._probe_price("AAPL", "us-stock"))

    def test_market_alias_matches(self):
        # positions.market holds the caller's raw string; 'stock' aliases to us-stock.
        self._mark("AAPL", "stock", 190.5, age_seconds=10)
        with patch("price_fetcher.get_price_from_market", return_value=None):
            self.assertEqual(routes_runs._probe_price("AAPL", "us-stock"), 190.5)

    def test_freshest_mark_wins(self):
        self._mark("AAPL", "us-stock", 100.0, age_seconds=600)
        self._mark("AAPL", "us-stock", 195.0, age_seconds=30)
        with patch("price_fetcher.get_price_from_market", return_value=None):
            self.assertEqual(routes_runs._probe_price("AAPL", "us-stock"), 195.0)

    def test_null_mark_skipped_for_older_real_one(self):
        self._mark("AAPL", "us-stock", 188.0, age_seconds=300)
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO positions
               (agent_id, symbol, market, side, quantity, entry_price,
                current_price, price_updated_at, opened_at)
               VALUES (1, 'AAPL', 'us-stock', 'long', 1, 188.0, NULL, ?, ?)""",
            (_ts(5), _ts(5)))
        conn.commit()
        conn.close()
        with patch("price_fetcher.get_price_from_market", return_value=None):
            self.assertEqual(routes_runs._probe_price("AAPL", "us-stock"), 188.0)


if __name__ == "__main__":
    unittest.main()
