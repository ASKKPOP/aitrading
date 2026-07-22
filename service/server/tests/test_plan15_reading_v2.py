"""Plan 15 P1 — reading-algorithm v2 inputs.

Covers the four P1 changes (docs/plan/15-run-ai-reading-algorithm-fix.html):
  F1 — calibration rubric + inventory context in the light-cycle prompt
  F2 — us-stock technicals fall back to Yahoo candles behind the Alpha
       Vantage premium wall
  F3 — fleet builder never sets a run gate above its thesis confidence
  F4 — covered in test_run_futures_short.py (spot sell with empty book)
"""

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
import run_engine
from fleet_planner import FLEET_BOUNDS, compose_run_settings


class LightAnalysisPromptTests(unittest.TestCase):
    """The decision prompt must carry the rubric and the book state."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()

    def tearDown(self):
        self.tmp.cleanup()

    def _capture_prompt(self, run, cfg):
        captured = {}

        def fake_generate(prompt, **kwargs):
            captured["prompt"] = prompt
            return '{"action": "hold", "confidence": 0.55, "report": "r"}'

        with patch("price_fetcher.get_price_from_market", return_value=100.0), \
                patch("price_fetcher.get_daily_candles", return_value=[]), \
                patch("llm_client.generate_text", side_effect=fake_generate):
            out = run_engine._light_analysis(run, cfg)
        return captured.get("prompt", ""), out

    def _run_row(self, **overrides):
        row = {"id": 1, "agent_id": 999999, "symbol": "ETHUSDT",
               "market": "crypto", "market_type": "spot"}
        row.update(overrides)
        return row

    def test_prompt_contains_rubric_and_flat_spot_inventory_rule(self):
        prompt, out = self._capture_prompt(self._run_row(), {})
        self.assertIn("0.50 = coin-flip", prompt)
        self.assertIn("0.85+ = exceptional", prompt)
        self.assertIn("Do not default to a habitual value", prompt)
        self.assertIn("Position in this run's book: 0.0 units", prompt)
        self.assertIn("'sell' is NOT available", prompt)
        self.assertEqual(out["decision"]["action"], "hold")

    def test_prompt_futures_book_allows_short(self):
        prompt, _ = self._capture_prompt(
            self._run_row(market_type="futures"), {})
        self.assertIn("'sell' opens or extends a short", prompt)
        self.assertNotIn("'sell' is NOT available", prompt)

    def test_prompt_long_inventory_rule(self):
        with patch.object(run_engine, "_position_quantity", return_value=2.5):
            captured = {}

            def fake_generate(prompt, **kwargs):
                captured["prompt"] = prompt
                return '{"action": "hold", "confidence": 0.55, "report": "r"}'

            with patch("price_fetcher.get_price_from_market", return_value=100.0), \
                    patch("price_fetcher.get_daily_candles", return_value=[]), \
                    patch("llm_client.generate_text", side_effect=fake_generate):
                run_engine._light_analysis(self._run_row(), {})
        self.assertIn("Position in this run's book: 2.5 units", captured["prompt"])
        self.assertIn("reduces/closes this long", captured["prompt"])


class YahooTechnicalsFallbackTests(unittest.TestCase):
    """F2 — the premium wall must no longer starve us-stock technicals."""

    def _candles(self, n=40, start_close=100.0):
        # oldest-first epoch-ms candles, one per day
        day_ms = 86_400_000
        base = 1_752_000_000_000  # 2025-07 area; exact date irrelevant
        return [{"ts": base + i * day_ms, "open": start_close, "high": start_close,
                 "low": start_close, "close": start_close + i * 0.5,
                 "volume": 1000 + i} for i in range(n)]

    def test_premium_wall_falls_back_to_yahoo(self):
        import market_intel
        wall = {"Information": "Thank you for using Alpha Vantage! This is a "
                               "premium endpoint."}
        with patch.object(market_intel, "_alpha_vantage_get", return_value=wall), \
                patch("price_fetcher.get_daily_candles",
                      return_value=self._candles()):
            rows = market_intel._fetch_daily_adjusted_series("TSLA")
        self.assertGreaterEqual(len(rows), 20)
        # newest-first, real ISO dates, close/volume floats
        self.assertGreater(rows[0]["date"], rows[-1]["date"])
        self.assertRegex(rows[0]["date"], r"^\d{4}-\d{2}-\d{2}$")
        self.assertIsInstance(rows[0]["close"], float)

    def test_premium_wall_and_no_yahoo_still_raises(self):
        import market_intel
        wall = {"Information": "premium endpoint"}
        with patch.object(market_intel, "_alpha_vantage_get", return_value=wall), \
                patch("price_fetcher.get_daily_candles", return_value=[]):
            with self.assertRaises(RuntimeError):
                market_intel._fetch_daily_adjusted_series("TSLA")

    def test_build_stock_analysis_survives_premium_wall(self):
        import market_intel
        wall = {"Information": "premium endpoint"}
        with patch.object(market_intel, "_alpha_vantage_get", return_value=wall), \
                patch("price_fetcher.get_daily_candles",
                      return_value=self._candles()), \
                patch.object(market_intel, "_build_stock_long_window_features",
                             return_value={
                                 "momentum_12_1_pct": None,
                                 "reversal_1m_pct": None, "ma50": None,
                                 "ma200": None, "price_above_ma200": None,
                                 "golden_cross_state": None,
                                 "sigma_daily_pct": None,
                                 "volume_ratio": None}):
            analysis = market_intel._build_stock_analysis("TSLA")
        self.assertEqual(analysis["market"], "us-stock")
        self.assertGreater(analysis["current_price"], 0)


class FleetGateCoherenceTests(unittest.TestCase):
    """F3 — no run is born with a gate above its own thesis confidence."""

    def _settings(self, thesis_conf, risk="balanced"):
        thesis = {"symbol": "ZC", "market": "futures", "market_type": "spot",
                  "direction": "long", "confidence": thesis_conf,
                  "expected_move_pct": 3.0, "horizon_hours": 48,
                  "entry_ref_price": 477.25, "thesis_key": "k",
                  "rationale": "r"}
        return compose_run_settings(thesis, 1000.0, {"risk_appetite": risk})

    def test_weak_thesis_lowers_gate_to_floor(self):
        # thesis 0.539 (the real fleet-6 ZC case): gate 0.50, not 0.60
        self.assertEqual(self._settings(0.539)["min_confidence"], 0.50)

    def test_mid_thesis_gate_tracks_thesis_minus_margin(self):
        # thesis 0.62: gate = min(0.60, 0.57) = 0.57
        self.assertEqual(self._settings(0.62)["min_confidence"], 0.57)

    def test_strong_thesis_keeps_risk_bound(self):
        # thesis 0.80: bound 0.60 stays (balanced)
        self.assertEqual(self._settings(0.80)["min_confidence"],
                         FLEET_BOUNDS["min_confidence"]["balanced"])

    def test_stable_risk_bound_still_clamped_by_thesis(self):
        # stable bound 0.75, thesis 0.68 → 0.63
        self.assertEqual(self._settings(0.68, risk="stable")["min_confidence"],
                         0.63)


if __name__ == "__main__":
    unittest.main()
