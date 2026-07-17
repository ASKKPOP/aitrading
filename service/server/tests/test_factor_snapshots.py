"""Tests for factor_snapshots.py — live-only factor history recording."""

from __future__ import annotations

import sys
import tempfile
import os
import unittest
from pathlib import Path
from unittest.mock import patch

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database


class FactorSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._old_path = database._SQLITE_DB_PATH
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()

    def tearDown(self):
        database._SQLITE_DB_PATH = self._old_path
        self.tmp.cleanup()

    def _rows(self):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM factor_snapshots ORDER BY id ASC")
            return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

    def test_records_one_row_per_symbol(self):
        from factor_snapshots import record_factor_snapshots
        with patch("crypto_feed.fetch_funding_rate", return_value={"funding_rate": 0.0001}), \
             patch("crypto_feed.fetch_open_interest", return_value={"open_interest_ccy": 20000.0}), \
             patch("crypto_feed.fetch_ticker", return_value={"last_price": "100000"}), \
             patch("crypto_feed.fetch_long_short_ratio", return_value={"long_short_ratio": 1.25}), \
             patch("analysis_sources.fetch_stocktwits_sentiment",
                   return_value={"bullish": 12, "bearish": 4, "messages_scored": 16}):
            result = record_factor_snapshots(("BTC", "ETH"))

        self.assertEqual(result["written"], 2)
        self.assertEqual(result["errors"], [])
        rows = self._rows()
        self.assertEqual([r["symbol"] for r in rows], ["BTC", "ETH"])
        self.assertAlmostEqual(rows[0]["funding_rate"], 0.0001)
        self.assertAlmostEqual(rows[0]["open_interest_usd"], 2_000_000_000.0)
        self.assertAlmostEqual(rows[0]["long_short_ratio"], 1.25)
        self.assertAlmostEqual(rows[0]["stocktwits_tilt"], 0.5)
        self.assertEqual(rows[0]["stocktwits_n"], 16)

    def test_partial_failures_still_write_row_with_nulls(self):
        from factor_snapshots import record_factor_snapshots
        with patch("crypto_feed.fetch_funding_rate", side_effect=Exception("okx down")), \
             patch("crypto_feed.fetch_open_interest", side_effect=Exception("okx down")), \
             patch("crypto_feed.fetch_ticker", side_effect=Exception("okx down")), \
             patch("crypto_feed.fetch_long_short_ratio", return_value={"long_short_ratio": 0.9}), \
             patch("analysis_sources.fetch_stocktwits_sentiment", return_value=None):
            result = record_factor_snapshots(("BTC",))

        self.assertEqual(result["written"], 1)
        # funding + oi + basis (Plan 06 A5 added the basis leg, which also
        # depends on the failing ticker fetch)
        self.assertEqual(len(result["errors"]), 3)
        row = self._rows()[0]
        self.assertIsNone(row["funding_rate"])
        self.assertIsNone(row["open_interest_usd"])
        self.assertAlmostEqual(row["long_short_ratio"], 0.9)
        self.assertIsNone(row["stocktwits_tilt"])


class ExtendedFactorColumnTests(FactorSnapshotTests):
    """Plan 06 A5 — basis, kimchi, ETF flow, whale flow columns."""

    def test_new_columns_recorded(self):
        from factor_snapshots import record_factor_snapshots
        with patch("crypto_feed.fetch_funding_rate", return_value={"funding_rate": 0.0001}), \
             patch("crypto_feed.fetch_open_interest", return_value={"open_interest_ccy": 100.0}), \
             patch("crypto_feed.fetch_ticker", return_value={"last_price": 60000.0}), \
             patch("crypto_feed.fetch_spot_ticker", return_value={"last_price": 59700.0}), \
             patch("crypto_feed.fetch_long_short_ratio", return_value={"long_short_ratio": 1.1}), \
             patch("analysis_sources.fetch_stocktwits_sentiment", return_value=None), \
             patch("factor_snapshots._global_factors",
                   return_value={"kimchi": 2.5, "etf": 181000000.0,
                                 "whale_btc": 14000000.0, "whale_eth": -3000000.0}):
            result = record_factor_snapshots(("BTC", "ETH", "SOL"))
        self.assertEqual(result["written"], 3)
        rows = {r["symbol"]: r for r in self._rows()}
        # basis = (60000-59700)/59700*100
        self.assertAlmostEqual(rows["BTC"]["basis_pct"], 0.5025, places=3)
        self.assertAlmostEqual(rows["BTC"]["kimchi_premium_pct"], 2.5)
        self.assertAlmostEqual(rows["BTC"]["etf_flow_usd"], 181000000.0)
        self.assertAlmostEqual(rows["BTC"]["whale_net_flow_usd"], 14000000.0)
        # globals only land on their symbol rows
        self.assertIsNone(rows["ETH"]["kimchi_premium_pct"])
        self.assertIsNone(rows["ETH"]["etf_flow_usd"])
        self.assertAlmostEqual(rows["ETH"]["whale_net_flow_usd"], -3000000.0)
        self.assertIsNone(rows["SOL"]["whale_net_flow_usd"])

    def test_global_factor_failures_are_null(self):
        from factor_snapshots import record_factor_snapshots
        with patch("crypto_feed.fetch_funding_rate", return_value={"funding_rate": 0.0001}), \
             patch("crypto_feed.fetch_open_interest", return_value={"open_interest_ccy": 100.0}), \
             patch("crypto_feed.fetch_ticker", return_value={"last_price": 60000.0}), \
             patch("crypto_feed.fetch_spot_ticker", side_effect=Exception("spot down")), \
             patch("crypto_feed.fetch_long_short_ratio", return_value={"long_short_ratio": 1.1}), \
             patch("analysis_sources.fetch_stocktwits_sentiment", return_value=None), \
             patch("factor_snapshots._global_factors",
                   return_value={"kimchi": None, "etf": None, "whale_btc": None, "whale_eth": None}):
            result = record_factor_snapshots(("BTC",))
        self.assertEqual(result["written"], 1)
        row = self._rows()[0]
        self.assertIsNone(row["basis_pct"])
        self.assertIsNone(row["kimchi_premium_pct"])
        self.assertIsNone(row["whale_net_flow_usd"])


if __name__ == "__main__":
    unittest.main()
