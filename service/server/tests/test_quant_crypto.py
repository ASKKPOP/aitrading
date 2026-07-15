"""Crypto quant technicals (Phase 3) — RSI/MA/σ/basis math + analyst integration.

Covers the phase acceptance criteria:
  - a crypto analysis carries real RSI · MA · basis · funding in its evidence
  - the buy/sell decision path consumes quantitative conditions for crypto
  - indicator math is exact against hand-computed fixtures
"""
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))


def _candles(closes, volume=50.0):
    return [{"ts": i, "open": c, "high": c, "low": c, "close": c, "volume": volume}
            for i, c in enumerate(closes)]


# ─── indicator math ────────────────────────────────────────────────────────

class RsiTests(unittest.TestCase):
    def test_rsi_hand_computed_wilder_example(self):
        from quant_crypto import compute_rsi
        # period=3, closes 10,11,12,11,13 → changes +1,+1,−1,+2
        # seed: avg_gain=(1+1+0)/3=0.6667, avg_loss=(0+0+1)/3=0.3333
        # next (+2): avg_gain=(0.6667·2+2)/3=1.1111, avg_loss=(0.3333·2)/3=0.2222
        # RS=5 → RSI = 100 − 100/6 = 83.333
        rsi = compute_rsi([10, 11, 12, 11, 13], period=3)
        self.assertAlmostEqual(rsi, 83.3333, places=3)

    def test_rsi_all_gains_is_100(self):
        from quant_crypto import compute_rsi
        self.assertEqual(compute_rsi(list(range(1, 20)), period=14), 100.0)

    def test_rsi_balanced_gains_losses_near_50(self):
        from quant_crypto import compute_rsi
        closes = [100 + (1 if i % 2 == 0 else 0) for i in range(40)]  # +1/−1 alternating
        rsi = compute_rsi(closes, period=14)
        # Wilder smoothing oscillates around 50 by up to ~±4 on alternating bars
        self.assertAlmostEqual(rsi, 50.0, delta=5.0)

    def test_rsi_insufficient_data_is_none(self):
        from quant_crypto import compute_rsi
        self.assertIsNone(compute_rsi([1, 2, 3], period=14))


class MaAndBasisTests(unittest.TestCase):
    def test_moving_average(self):
        from quant_crypto import compute_ma
        self.assertAlmostEqual(compute_ma([1, 2, 3, 4, 5, 6], 5), 4.0)
        self.assertIsNone(compute_ma([1, 2], 5))

    def test_basis_pct(self):
        from quant_crypto import compute_basis_pct
        # swap 101.2 vs spot 100 → +1.2%
        self.assertAlmostEqual(compute_basis_pct(101.2, 100.0), 1.2)
        self.assertIsNone(compute_basis_pct(101.2, 0))

    def test_sigma_and_volume(self):
        from quant_crypto import compute_sigma_and_volume
        closes = []
        price = 100.0
        for i in range(29):
            price *= 1.001 if i % 2 == 0 else 0.999
            closes.append(price)
        closes.append(price * 0.99)
        hourly = _candles(closes[:-1]) + _candles([closes[-1]], volume=150.0)
        sigma_pct, volume_ratio = compute_sigma_and_volume(hourly)
        self.assertIsNotNone(sigma_pct)
        self.assertGreater(sigma_pct, 0)
        self.assertAlmostEqual(volume_ratio, 3.0, delta=0.01)  # 150 vs 50 avg


# ─── analysis builder ──────────────────────────────────────────────────────

class BuildAnalysisTests(unittest.TestCase):
    def _build(self, daily_closes, funding=0.0001, spot=None, swap=None,
               hourly_closes=None):
        """build_crypto_analysis with every OKX fetch mocked."""
        daily = _candles(daily_closes)
        hourly = _candles(hourly_closes or ([daily_closes[-1]] * 30))

        def fake_candles(symbol, bar="1H", limit=100):
            return daily if bar == "1D" else hourly

        swap = swap if swap is not None else daily_closes[-1]
        spot = spot if spot is not None else daily_closes[-1]
        from quant_crypto import build_crypto_analysis
        with patch("crypto_feed.fetch_candles", side_effect=fake_candles), \
             patch("crypto_feed.fetch_funding_rate",
                   return_value={"symbol": "BTCUSDT", "funding_rate": funding,
                                 "next_funding_time": None}), \
             patch("crypto_feed.fetch_ticker",
                   return_value={"symbol": "BTCUSDT", "last_price": str(swap)}), \
             patch("crypto_feed.fetch_spot_ticker",
                   return_value={"symbol": "BTCUSDT", "last_price": float(spot)}):
            return build_crypto_analysis("BTC")

    def test_analysis_carries_all_quant_evidence(self):
        closes = [100.0 + i * 0.5 for i in range(120)]  # steady uptrend
        analysis = self._build(closes, funding=0.0001, spot=100.0, swap=101.5)
        self.assertEqual(analysis["symbol"], "BTC")
        self.assertIsNotNone(analysis["rsi_14"])
        self.assertIsNotNone(analysis["moving_averages"]["ma5"])
        self.assertIsNotNone(analysis["moving_averages"]["ma60"])
        self.assertAlmostEqual(analysis["basis_pct"], 1.5)
        self.assertEqual(analysis["funding_rate"], 0.0001)
        self.assertEqual(analysis["source"], "okx")

    def test_uptrend_without_overbought_signals_buy(self):
        # Mild steady uptrend: MAs aligned bullish, RSI high but the +1.2% basis
        # keeps it net positive only when not overbought — use gentle slope.
        closes = [100.0]
        for i in range(119):
            closes.append(closes[-1] * (1.002 if i % 3 else 0.999))
        analysis = self._build(closes, spot=closes[-1], swap=closes[-1] * 1.013)
        self.assertGreaterEqual(analysis["signal_score"], 2)
        self.assertEqual(analysis["signal"], "buy")
        self.assertEqual(analysis["trend_status"], "uptrend")

    def test_downtrend_signals_sell(self):
        # Mild decline with up-days mixed in: MAs align bearish (−3) but RSI
        # stays out of the ≤30 oversold zone, so no contrarian +2 offsets it.
        closes = [200.0]
        for i in range(119):
            closes.append(closes[-1] * (0.9985 if i % 2 else 1.001))
        analysis = self._build(closes)
        self.assertGreater(analysis["rsi_14"], 30)
        self.assertLessEqual(analysis["signal_score"], -2)
        self.assertEqual(analysis["signal"], "sell")
        self.assertEqual(analysis["trend_status"], "downtrend")

    def test_overbought_rsi_is_a_risk_factor(self):
        closes = [100.0 * (1.01 ** i) for i in range(120)]  # relentless rally → RSI≈100
        analysis = self._build(closes)
        self.assertGreaterEqual(analysis["rsi_14"], 70)
        self.assertTrue(any("overbought" in r for r in analysis["risk_factors"]))

    def test_crowded_funding_is_a_risk_factor(self):
        closes = [100.0 + i * 0.5 for i in range(120)]
        analysis = self._build(closes, funding=0.001)
        self.assertTrue(any("crowded long" in r for r in analysis["risk_factors"]))

    def test_fails_soft_when_secondary_sources_error(self):
        daily = _candles([100.0 + i for i in range(120)])

        def fake_candles(symbol, bar="1H", limit=100):
            if bar == "1D":
                return daily
            raise RuntimeError("hourly down")

        from quant_crypto import build_crypto_analysis
        with patch("crypto_feed.fetch_candles", side_effect=fake_candles), \
             patch("crypto_feed.fetch_funding_rate", side_effect=RuntimeError("down")), \
             patch("crypto_feed.fetch_ticker", side_effect=RuntimeError("down")), \
             patch("crypto_feed.fetch_spot_ticker", side_effect=RuntimeError("down")):
            analysis = build_crypto_analysis("BTC")
        self.assertIsNotNone(analysis["rsi_14"])       # core path still works
        self.assertIsNone(analysis["funding_rate"])    # missing inputs stay None
        self.assertIsNone(analysis["basis_pct"])
        self.assertIsNone(analysis["sigma_24h_pct"])


# ─── analyst integration ───────────────────────────────────────────────────

class GatherTechnicalTests(unittest.TestCase):
    def tearDown(self) -> None:
        os.environ["QUANT_CRYPTO_ENABLED"] = "false"

    def test_crypto_path_uses_quant_when_enabled(self):
        os.environ["QUANT_CRYPTO_ENABLED"] = "true"
        from analysis_agents import _gather_technical
        fake = {"symbol": "BTC", "market": "crypto", "rsi_14": 55.0,
                "signal": "hold", "signal_score": 0, "current_price": 64000.0}
        with patch("quant_crypto.build_crypto_analysis", return_value=fake) as mock_build:
            out = _gather_technical("BTC", "crypto")
        mock_build.assert_called_once_with("BTC")
        self.assertEqual(out["rsi_14"], 55.0)

    def test_crypto_path_keeps_light_path_when_disabled(self):
        os.environ["QUANT_CRYPTO_ENABLED"] = "false"
        from analysis_agents import _gather_technical
        with patch("price_fetcher.get_price_from_market", return_value=64000.0):
            out = _gather_technical("BTC", "crypto")
        self.assertEqual(out["current_price"], 64000.0)
        self.assertIn("light technical", out.get("note", ""))

    def test_crypto_path_falls_back_when_quant_errors(self):
        os.environ["QUANT_CRYPTO_ENABLED"] = "true"
        from analysis_agents import _gather_technical
        with patch("quant_crypto.build_crypto_analysis", side_effect=RuntimeError("okx down")), \
             patch("price_fetcher.get_price_from_market", return_value=64000.0):
            out = _gather_technical("BTC", "crypto")
        self.assertEqual(out["current_price"], 64000.0)

    def test_rule_based_decision_uses_quant_signal(self):
        """Acceptance: buy/sell triggers consume quant conditions for crypto."""
        from analysis_agents import _rule_based_decision
        technical = {"signal": "sell", "signal_score": -3, "current_price": 64000.0}
        decision = _rule_based_decision(technical, {"sentiment_breakdown": {}})
        self.assertEqual(decision["action"], "sell")
        self.assertEqual(decision["entry"], 64000.0)

    def test_rule_based_confidence_is_direction_agnostic(self):
        """A strong bearish score is a confident sell — same confidence as an
        equally strong bullish score (soak finding: score/20 buried all sells)."""
        from analysis_agents import _rule_based_decision
        sell = _rule_based_decision({"signal": "sell", "signal_score": -3,
                                     "current_price": 100.0}, {"sentiment_breakdown": {}})
        buy = _rule_based_decision({"signal": "buy", "signal_score": 3,
                                    "current_price": 100.0}, {"sentiment_breakdown": {}})
        self.assertEqual(sell["confidence"], buy["confidence"])
        self.assertGreaterEqual(sell["confidence"], 0.65)


if __name__ == "__main__":
    unittest.main()
