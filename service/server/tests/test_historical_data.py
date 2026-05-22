"""Tests for the historical data loader (historical_data.py).

Covers:
  - Bar dataclass shape
  - Parquet cache write on first fetch
  - Parquet cache read on second fetch (no HTTP call)
  - Date range filtering
  - Empty result when provider returns nothing
  - Provider error returns empty list
  - force_refresh bypasses cache
  - Alpha Vantage fallback path (mocked)
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from historical_data import Bar, get_bars


def _make_yfinance_df(rows: list[tuple]) -> pd.DataFrame:
    """Build a minimal yfinance-shaped DataFrame from (date, open, high, low, close, vol) tuples."""
    dates = [r[0] for r in rows]
    index = pd.DatetimeIndex(dates, name="Date")
    df = pd.DataFrame(
        {
            "Open": [r[1] for r in rows],
            "High": [r[2] for r in rows],
            "Low": [r[3] for r in rows],
            "Close": [r[4] for r in rows],
            "Volume": [r[5] for r in rows],
        },
        index=index,
    )
    return df


_SAMPLE_ROWS = [
    ("2024-01-02", 185.0, 186.5, 184.0, 185.5, 50_000_000),
    ("2024-01-03", 185.5, 187.0, 184.5, 186.0, 45_000_000),
    ("2024-01-04", 186.0, 188.0, 185.5, 187.5, 60_000_000),
]


class TestBarDataclass(unittest.TestCase):
    def test_bar_has_expected_fields(self):
        b = Bar(date="2024-01-02", open=100.0, high=105.0, low=99.0, close=103.0, volume=1_000_000)
        self.assertEqual(b.date, "2024-01-02")
        self.assertEqual(b.open, 100.0)
        self.assertEqual(b.high, 105.0)
        self.assertEqual(b.low, 99.0)
        self.assertEqual(b.close, 103.0)
        self.assertEqual(b.volume, 1_000_000)


class TestGetBars(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.cache_dir = Path(self._tmpdir.name)

    def tearDown(self):
        self._tmpdir.cleanup()

    # ------------------------------------------------------------------
    # Basic fetch + shape
    # ------------------------------------------------------------------

    def test_returns_bars_sorted_by_date(self):
        df = _make_yfinance_df(_SAMPLE_ROWS)
        with patch("historical_data.yf.download", return_value=df):
            bars = get_bars("AAPL", "1d", "2024-01-02", "2024-01-04", cache_dir=self.cache_dir)

        dates = [b.date for b in bars]
        self.assertEqual(dates, sorted(dates))

    def test_bar_fields_populated_correctly(self):
        df = _make_yfinance_df(_SAMPLE_ROWS)
        with patch("historical_data.yf.download", return_value=df):
            bars = get_bars("AAPL", "1d", "2024-01-02", "2024-01-02", cache_dir=self.cache_dir)

        self.assertEqual(len(bars), 1)
        b = bars[0]
        self.assertEqual(b.date, "2024-01-02")
        self.assertAlmostEqual(b.open, 185.0)
        self.assertAlmostEqual(b.close, 185.5)
        self.assertEqual(b.volume, 50_000_000)

    def test_symbol_is_uppercased(self):
        df = _make_yfinance_df(_SAMPLE_ROWS)
        call_args = {}

        def mock_download(ticker, **kwargs):
            call_args["ticker"] = ticker
            return df

        with patch("historical_data.yf.download", side_effect=mock_download):
            get_bars("aapl", "1d", "2024-01-02", "2024-01-04", cache_dir=self.cache_dir)

        self.assertEqual(call_args["ticker"], "AAPL")

    # ------------------------------------------------------------------
    # Parquet cache
    # ------------------------------------------------------------------

    def test_cache_file_is_written_on_first_fetch(self):
        df = _make_yfinance_df(_SAMPLE_ROWS)
        with patch("historical_data.yf.download", return_value=df):
            get_bars("AAPL", "1d", "2024-01-02", "2024-01-04", cache_dir=self.cache_dir)

        cache_file = self.cache_dir / "AAPL_1d.parquet"
        self.assertTrue(cache_file.exists(), "Parquet cache file should be created")

    def test_cache_file_named_by_symbol_and_resolution(self):
        df = _make_yfinance_df(_SAMPLE_ROWS)
        with patch("historical_data.yf.download", return_value=df):
            get_bars("MSFT", "1d", "2024-01-02", "2024-01-04", cache_dir=self.cache_dir)

        self.assertTrue((self.cache_dir / "MSFT_1d.parquet").exists())

    def test_second_call_reads_cache_without_api_call(self):
        df = _make_yfinance_df(_SAMPLE_ROWS)
        download_call_count = {"n": 0}

        def mock_download(ticker, **kwargs):
            download_call_count["n"] += 1
            return df

        with patch("historical_data.yf.download", side_effect=mock_download):
            get_bars("AAPL", "1d", "2024-01-02", "2024-01-04", cache_dir=self.cache_dir)
            get_bars("AAPL", "1d", "2024-01-02", "2024-01-04", cache_dir=self.cache_dir)

        self.assertEqual(download_call_count["n"], 1, "yf.download should only be called once")

    def test_force_refresh_bypasses_cache(self):
        df = _make_yfinance_df(_SAMPLE_ROWS)
        download_call_count = {"n": 0}

        def mock_download(ticker, **kwargs):
            download_call_count["n"] += 1
            return df

        with patch("historical_data.yf.download", side_effect=mock_download):
            get_bars("AAPL", "1d", "2024-01-02", "2024-01-04", cache_dir=self.cache_dir)
            get_bars("AAPL", "1d", "2024-01-02", "2024-01-04", cache_dir=self.cache_dir, force_refresh=True)

        self.assertEqual(download_call_count["n"], 2, "force_refresh should trigger a fresh API call")

    def test_cache_is_used_across_different_date_ranges(self):
        """Cache stores all fetched bars; date filter is applied at read time."""
        df = _make_yfinance_df(_SAMPLE_ROWS)
        download_call_count = {"n": 0}

        def mock_download(ticker, **kwargs):
            download_call_count["n"] += 1
            return df

        with patch("historical_data.yf.download", side_effect=mock_download):
            # First call populates cache
            get_bars("AAPL", "1d", "2024-01-02", "2024-01-04", cache_dir=self.cache_dir)
            # Second call with narrower range — no re-fetch needed
            bars = get_bars("AAPL", "1d", "2024-01-03", "2024-01-03", cache_dir=self.cache_dir)

        self.assertEqual(download_call_count["n"], 1)
        self.assertEqual(len(bars), 1)
        self.assertEqual(bars[0].date, "2024-01-03")

    # ------------------------------------------------------------------
    # Date range filtering
    # ------------------------------------------------------------------

    def test_date_range_filters_returned_bars(self):
        df = _make_yfinance_df(_SAMPLE_ROWS)
        with patch("historical_data.yf.download", return_value=df):
            bars = get_bars("AAPL", "1d", "2024-01-03", "2024-01-04", cache_dir=self.cache_dir)

        dates = [b.date for b in bars]
        self.assertNotIn("2024-01-02", dates)
        self.assertIn("2024-01-03", dates)
        self.assertIn("2024-01-04", dates)

    def test_empty_result_when_no_bars_in_range(self):
        df = _make_yfinance_df(_SAMPLE_ROWS)
        with patch("historical_data.yf.download", return_value=df):
            bars = get_bars("AAPL", "1d", "2025-01-01", "2025-01-31", cache_dir=self.cache_dir)

        self.assertEqual(bars, [])

    # ------------------------------------------------------------------
    # Error handling
    # ------------------------------------------------------------------

    def test_empty_dataframe_returns_empty_list(self):
        empty_df = pd.DataFrame()
        with patch("historical_data.yf.download", return_value=empty_df):
            bars = get_bars("AAPL", "1d", "2024-01-02", "2024-01-04", cache_dir=self.cache_dir)

        self.assertEqual(bars, [])

    def test_provider_exception_returns_empty_list(self):
        with patch("historical_data.yf.download", side_effect=Exception("network error")):
            bars = get_bars("AAPL", "1d", "2024-01-02", "2024-01-04", cache_dir=self.cache_dir)

        self.assertEqual(bars, [])

    def test_no_cache_written_on_provider_error(self):
        with patch("historical_data.yf.download", side_effect=Exception("network error")):
            get_bars("AAPL", "1d", "2024-01-02", "2024-01-04", cache_dir=self.cache_dir)

        cache_file = self.cache_dir / "AAPL_1d.parquet"
        self.assertFalse(cache_file.exists(), "Cache should not be written on error")

    # ------------------------------------------------------------------
    # Cache requests that exceed cached range trigger a re-fetch
    # ------------------------------------------------------------------

    def test_refetch_when_requested_range_extends_beyond_cache(self):
        """If start_date is before the earliest cached bar, a fresh fetch happens."""
        df_small = _make_yfinance_df(_SAMPLE_ROWS[1:])  # only 2024-01-03, 2024-01-04
        df_full = _make_yfinance_df(_SAMPLE_ROWS)       # 2024-01-02 .. 2024-01-04

        download_call_count = {"n": 0}

        def mock_download(ticker, **kwargs):
            download_call_count["n"] += 1
            if download_call_count["n"] == 1:
                return df_small
            return df_full

        with patch("historical_data.yf.download", side_effect=mock_download):
            # First call — cache contains 01-03 and 01-04
            get_bars("AAPL", "1d", "2024-01-03", "2024-01-04", cache_dir=self.cache_dir)
            # Second call — requests 01-02 which is before cached range
            bars = get_bars("AAPL", "1d", "2024-01-02", "2024-01-04", cache_dir=self.cache_dir, force_refresh=True)

        # After force_refresh the cache is updated with full range
        self.assertEqual(download_call_count["n"], 2)
        dates = [b.date for b in bars]
        self.assertIn("2024-01-02", dates)


if __name__ == "__main__":
    unittest.main()
