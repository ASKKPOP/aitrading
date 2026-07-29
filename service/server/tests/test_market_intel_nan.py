"""Regression tests for the NaN-500 on /api/market-intel/stocks/*.

Prod symptom (2026-07-29): every request to /api/market-intel/stocks/featured,
/{symbol}/latest and /{symbol}/history returned 500 with
`ValueError: Out of range float values are not JSON compliant: nan`.

Chain: yfinance returned a trailing bar for the in-progress session whose Close
was NaN -> float(NaN) passed _fetch_yfinance's guard -> every window touching
closes[-1] (MA50, MA200, 1m reversal, daily sigma) evaluated to NaN -> the
`is not None` guards in _build_stock_long_window_features let NaN through ->
json.dumps stored a bare `NaN` literal in stock_analysis_snapshots.analysis_json
-> json.loads restored it as a float -> Starlette's allow_nan=False renderer
raised on every read of that row.

Each test below covers one link in that chain.
"""

from __future__ import annotations

import math
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import historical_data
import market_intel
from historical_data import Bar, get_bars
from json_safe import json_safe


class JsonSafeTests(unittest.TestCase):
    def test_replaces_nan_and_inf_with_none(self) -> None:
        self.assertIsNone(json_safe(float("nan")))
        self.assertIsNone(json_safe(float("inf")))
        self.assertIsNone(json_safe(float("-inf")))

    def test_preserves_finite_values_and_non_floats(self) -> None:
        self.assertEqual(json_safe(1.5), 1.5)
        self.assertEqual(json_safe(0.0), 0.0)
        self.assertEqual(json_safe("nan"), "nan")
        self.assertEqual(json_safe(7), 7)
        self.assertIsNone(json_safe(None))

    def test_recurses_through_nested_containers(self) -> None:
        payload = {
            "items": [
                {"moving_averages": {"ma50": float("nan"), "ma20": 317.04}},
                {"levels": (float("inf"), 1.0)},
            ],
            "ok": True,
        }
        cleaned = json_safe(payload)
        self.assertIsNone(cleaned["items"][0]["moving_averages"]["ma50"])
        self.assertEqual(cleaned["items"][0]["moving_averages"]["ma20"], 317.04)
        self.assertEqual(cleaned["items"][1]["levels"], [None, 1.0])
        self.assertTrue(cleaned["ok"])

    def test_output_survives_a_strict_json_encoder(self) -> None:
        import json

        # allow_nan=False is exactly what Starlette's JSONResponse uses.
        json.dumps(json_safe({"sigma": float("nan")}), allow_nan=False)


def _yfinance_df(rows: list[tuple]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Open": [r[1] for r in rows],
            "High": [r[2] for r in rows],
            "Low": [r[3] for r in rows],
            "Close": [r[4] for r in rows],
            "Volume": [r[5] for r in rows],
        },
        index=pd.DatetimeIndex([r[0] for r in rows], name="Date"),
    )


_NAN = float("nan")


class HistoricalBarNaNTests(unittest.TestCase):
    """The bar that started it: yfinance's in-progress-session row."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_bar_with_nan_close_is_dropped_by_the_provider(self) -> None:
        rows = [
            ("2026-07-27", 330.0, 338.0, 329.0, 336.91, 49_604_300),
            ("2026-07-28", _NAN, _NAN, _NAN, _NAN, 50_765_695),
        ]
        with patch.object(historical_data.yf, "download", return_value=_yfinance_df(rows)):
            bars = get_bars("AAPL", "1d", "2026-07-01", "2026-07-28", cache_dir=self.tmp.name)

        self.assertEqual([b.date for b in bars], ["2026-07-27"])
        self.assertTrue(all(math.isfinite(b.close) for b in bars))

    def test_finite_bars_are_still_returned(self) -> None:
        rows = [
            ("2026-07-27", 330.0, 338.0, 329.0, 336.91, 49_604_300),
            ("2026-07-28", 336.0, 340.0, 335.0, 339.10, 50_765_695),
        ]
        with patch.object(historical_data.yf, "download", return_value=_yfinance_df(rows)):
            bars = get_bars("AAPL", "1d", "2026-07-01", "2026-07-28", cache_dir=self.tmp.name)

        self.assertEqual([b.date for b in bars], ["2026-07-27", "2026-07-28"])

    def test_nan_bar_already_in_the_parquet_cache_is_filtered_on_read(self) -> None:
        """Caches written before this guard existed still hold the bad row."""
        cache_file = Path(self.tmp.name) / "AAPL_1d.parquet"
        historical_data._write_cache(
            [
                Bar(date="2026-07-27", open=330.0, high=338.0, low=329.0, close=336.91, volume=49_604_300),
                Bar(date="2026-07-28", open=_NAN, high=_NAN, low=_NAN, close=_NAN, volume=50_765_695),
            ],
            cache_file,
        )
        with patch.object(historical_data.yf, "download", side_effect=AssertionError("must serve from cache")):
            bars = get_bars("AAPL", "1d", "2026-07-27", "2026-07-28", cache_dir=self.tmp.name)

        self.assertEqual([b.date for b in bars], ["2026-07-27"])


class LongWindowFeatureNaNTests(unittest.TestCase):
    """NaN is not None, so it passed every `is not None` guard and then answered
    False to `latest > ma200` — a wrong signal, not a missing one."""

    @staticmethod
    def _bars(closes: list[float]) -> list[Bar]:
        return [
            Bar(date=f"2026-01-{i + 1:02d}", open=c, high=c, low=c, close=c, volume=1_000_000)
            for i, c in enumerate(closes)
        ]

    def test_nan_close_yields_null_features_not_nan(self) -> None:
        closes = [100.0 + i for i in range(60)] + [_NAN]
        with patch("historical_data.get_bars", return_value=self._bars(closes)):
            features = market_intel._build_stock_long_window_features("AAPL")

        for key in ("ma50", "ma200", "reversal_1m_pct", "sigma_daily_pct", "volume_ratio"):
            value = features[key]
            self.assertFalse(isinstance(value, float) and math.isnan(value),
                             f"{key} came back as NaN")

    def test_directional_booleans_are_none_not_false_when_undecidable(self) -> None:
        # 260 clean bars is enough for MA200, so without the guard ma50/ma200
        # are NaN (the NaN close is inside both windows) and `latest > ma200`
        # answers False — prod reported price_above_ma200=False on a rising
        # tape. Unknown must read as null, never as a bearish signal.
        closes = [100.0 + i for i in range(260)] + [_NAN]
        with patch("historical_data.get_bars", return_value=self._bars(closes)):
            features = market_intel._build_stock_long_window_features("AAPL")

        self.assertIsNone(features["price_above_ma200"])
        self.assertIsNone(features["golden_cross_state"])

    def test_clean_bars_still_produce_real_numbers(self) -> None:
        closes = [100.0 + i for i in range(260)]
        with patch("historical_data.get_bars", return_value=self._bars(closes)):
            features = market_intel._build_stock_long_window_features("AAPL")

        self.assertIsNotNone(features["ma50"])
        self.assertIsNotNone(features["ma200"])
        self.assertTrue(features["price_above_ma200"])
        self.assertTrue(features["golden_cross_state"])


class SnapshotWriteNaNTests(unittest.TestCase):
    """A NaN must never reach stock_analysis_snapshots.analysis_json — once
    stored, every read of that row 500s until the row ages out."""

    def test_refresh_persists_null_not_a_nan_literal(self) -> None:
        import json

        analysis = {
            "symbol": "AAPL",
            "current_price": 336.91,
            "signal": "hold",
            "signal_score": 1.0,
            "trend_status": "mixed",
            "summary": "s",
            "support_levels": [330.0],
            "resistance_levels": [340.0],
            "bullish_factors": [],
            "risk_factors": [],
            "moving_averages": {"ma50": _NAN, "ma200": _NAN},
            "sigma_daily_pct": _NAN,
        }
        captured: list[tuple] = []

        class _Cursor:
            def executemany(self, _sql, rows):
                captured.extend(rows)

            def execute(self, *_args, **_kwargs):
                return None

            def fetchall(self):
                return []

            def fetchone(self):
                return None

        class _Conn:
            def cursor(self):
                return _Cursor()

            def commit(self):
                return None

            def close(self):
                return None

        with patch("market_intel._get_hot_us_stock_symbols", return_value=["AAPL"]), \
             patch("market_intel._build_stock_analysis", return_value=analysis), \
             patch("market_intel.get_db_connection", return_value=_Conn()), \
             patch("market_intel._prune_stock_analysis_history"), \
             patch("market_intel.delete_pattern"):
            market_intel.refresh_stock_analysis_snapshots()

        self.assertEqual(len(captured), 1)
        analysis_json = captured[0][13]
        self.assertNotIn("NaN", analysis_json)
        # Strict decode is what proves it: json.loads accepts NaN by default.
        restored = json.loads(analysis_json, parse_constant=_reject_constant)
        self.assertIsNone(restored["moving_averages"]["ma50"])
        self.assertIsNone(restored["sigma_daily_pct"])
        self.assertEqual(restored["current_price"], 336.91)


def _reject_constant(name: str):
    raise AssertionError(f"non-finite constant {name!r} persisted to analysis_json")


if __name__ == "__main__":
    unittest.main()
