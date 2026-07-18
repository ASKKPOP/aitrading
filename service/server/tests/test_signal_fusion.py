"""Signal fusion (Phase 5) — weighted score, psych cap, trigger matching, API.

Covers the phase acceptance criteria plus the plan's honest-limits rule:
the psych weight is structurally capped so psychology never trades alone.
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
from routes import create_app


def _component(value, **extra):
    return {"value": value, "evidence": extra.pop("evidence", ["e"]), **extra}


class WeightTests(unittest.TestCase):
    def tearDown(self) -> None:
        for k in ("FUSION_W_QUANT", "FUSION_W_SENTIMENT", "FUSION_W_PSYCH"):
            os.environ.pop(k, None)

    def test_default_weights_normalized(self):
        from signal_fusion import _weights
        w = _weights()
        self.assertAlmostEqual(sum(w.values()), 1.0)
        self.assertAlmostEqual(w["quant"], 0.5)
        self.assertAlmostEqual(w["psych"], 0.2)

    def test_psych_weight_hard_capped(self):
        """No configuration can make psychology dominate the fused score."""
        from signal_fusion import _weights, PSYCH_WEIGHT_MAX
        os.environ["FUSION_W_QUANT"] = "0.05"
        os.environ["FUSION_W_SENTIMENT"] = "0.05"
        os.environ["FUSION_W_PSYCH"] = "0.9"
        w = _weights()
        self.assertLessEqual(w["psych"], PSYCH_WEIGHT_MAX)
        self.assertAlmostEqual(sum(w.values()), 1.0)

    def test_malformed_weight_env_falls_back(self):
        """A bad env value must not 500 the public fusion endpoint."""
        from signal_fusion import _weights
        os.environ["FUSION_W_QUANT"] = "0,5"  # malformed
        w = _weights()
        self.assertAlmostEqual(w["quant"], 0.5)  # default, not a crash


class FuseSymbolTests(unittest.TestCase):
    def setUp(self) -> None:
        # The Phase-1 confluence block inside fuse_symbol fetches StockTwits /
        # event data — stub it out so unit tests stay offline and fast.
        self._confluence_patch = patch(
            "confluence.evaluate_confluence",
            return_value={"buy_confluence": 0, "sell_confluence": 0,
                          "conditions": {}, "nulls": {}, "vetoes": [],
                          "direction_bias": "none"})
        self._confluence_patch.start()
        self.addCleanup(self._confluence_patch.stop)

    def _fuse(self, quant, sentiment, psych):
        from signal_fusion import fuse_symbol
        # Patch _psych_component too: fuse_symbol(psych=None) would otherwise
        # fetch the REAL dev DB's psych snapshot, making these tests depend on
        # whatever the local server recorded last (observed flake 2026-07-16).
        with patch("signal_fusion._quant_component", return_value=quant), \
             patch("signal_fusion._sentiment_component", return_value=sentiment), \
             patch("signal_fusion._psych_component", return_value=psych):
            return fuse_symbol("BTC")

    def test_weighted_fusion_math(self):
        # 0.5·0.8 + 0.3·0.5 + 0.2·(−0.5) = 0.45
        fused = self._fuse(_component(0.8), _component(0.5), _component(-0.5))
        self.assertAlmostEqual(fused["score"], 0.45)
        self.assertEqual(fused["signal"], "buy")
        self.assertEqual(fused["missing"], [])

    def test_bearish_fusion_signals_sell(self):
        fused = self._fuse(_component(-0.9), _component(-0.4), _component(-0.2))
        self.assertLessEqual(fused["score"], -0.25)
        self.assertEqual(fused["signal"], "sell")

    def test_missing_components_renormalize(self):
        # Only quant available → score is quant's value, missing names the rest.
        fused = self._fuse(_component(0.6), None, None)
        self.assertAlmostEqual(fused["score"], 0.6)
        self.assertEqual(sorted(fused["missing"]), ["psych", "sentiment"])

    def test_no_components_holds_with_zero_confidence(self):
        fused = self._fuse(None, None, None)
        self.assertEqual(fused["signal"], "hold")
        self.assertEqual(fused["confidence"], 0.0)
        self.assertEqual(fused["score"], 0.0)

    def test_psych_alone_cannot_reach_buy_threshold(self):
        """Structural guarantee: a maxed-out psych read with nothing else still
        cannot fire a buy at the capped weight when other sources exist."""
        fused = self._fuse(_component(0.0), _component(0.0), _component(1.0))
        # 0.5·0 + 0.3·0 + 0.2·1.0 = 0.2 < 0.25 buy threshold
        self.assertLess(fused["score"], 0.25)
        self.assertEqual(fused["signal"], "hold")

    def test_psych_as_only_component_forces_hold(self):
        """Renormalization must not defeat the cap: when quant and sentiment
        are missing, a psych-only read carries full weight numerically — the
        signal is forced to hold so psychology never decides alone."""
        fused = self._fuse(None, None, _component(1.0))
        self.assertEqual(fused["signal"], "hold")
        fused_bear = self._fuse(None, None, _component(-1.0))
        self.assertEqual(fused_bear["signal"], "hold")


class TriggerMatchTests(unittest.TestCase):
    def test_buy_trigger_fng_sentiment_basis(self):
        from signal_fusion import _matched_triggers
        quant = {"basis_pct": 1.4, "rsi_14": 55.0}
        sentiment = {"value": 0.35}
        psych = {"fear_greed": {"delta_3d": 12}, "negative_spikes": [],
                 "odds_reratings": [], "shocks": []}
        triggers = _matched_triggers(quant, sentiment, psych)
        self.assertEqual(len(triggers), 1)
        self.assertIn("buy: F&G recovery +12", triggers[0])
        self.assertIn("basis 1.40%", triggers[0])

    def test_sell_trigger_rsi_plus_negative_spike(self):
        from signal_fusion import _matched_triggers
        quant = {"basis_pct": 0.1, "rsi_14": 74.0}
        psych = {"fear_greed": {"delta_3d": -1},
                 "negative_spikes": [{"category": "crypto", "z": -2.4}],
                 "odds_reratings": [], "shocks": []}
        triggers = _matched_triggers(quant, {"value": -0.1}, psych)
        self.assertTrue(any(t.startswith("sell: RSI 74") for t in triggers))

    def test_reduce_trigger_on_shock(self):
        from signal_fusion import _matched_triggers
        psych = {"fear_greed": {}, "negative_spikes": [], "odds_reratings": [],
                 "shocks": [{"symbol": "BTCUSDT", "sigma_multiple": 3.4}]}
        triggers = _matched_triggers(None, None, psych)
        self.assertTrue(any("reduce: volatility shock" in t for t in triggers))
        self.assertTrue(any("estimated" in t for t in triggers))

    def test_no_triggers_when_nothing_fires(self):
        from signal_fusion import _matched_triggers
        self.assertEqual(_matched_triggers({"basis_pct": 0.1, "rsi_14": 50.0},
                                           {"value": 0.0},
                                           {"fear_greed": {"delta_3d": 2},
                                            "negative_spikes": [],
                                            "odds_reratings": [], "shocks": []}), [])


class FusionApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_fusion_route_parses_symbols_and_returns_signals(self):
        def fake_fuse(symbols):
            return [{"symbol": s, "score": 0.1, "signal": "hold"} for s in symbols]

        with patch("signal_fusion.fuse_symbols", side_effect=fake_fuse):
            resp = self.client.get("/api/market-intel/fusion?symbols=btc, eth ,SOL")
        self.assertEqual(resp.status_code, 200)
        symbols = [s["symbol"] for s in resp.json()["signals"]]
        self.assertEqual(symbols, ["BTC", "ETH", "SOL"])

    def test_fusion_route_caps_symbol_count(self):
        captured = {}

        def fake_fuse(symbols):
            captured["symbols"] = symbols
            return []

        many = ",".join(f"S{i}" for i in range(20))
        with patch("signal_fusion.fuse_symbols", side_effect=fake_fuse):
            resp = self.client.get(f"/api/market-intel/fusion?symbols={many}")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(captured["symbols"]), 8)

    def test_fusion_route_end_to_end_without_sources(self):
        # No quant flag, no psych snapshot, no stocktwits — every component
        # missing → hold with zero confidence, but the route still answers.
        with patch("signal_fusion._sentiment_component", return_value=None):
            resp = self.client.get("/api/market-intel/fusion?symbols=BTC")
        self.assertEqual(resp.status_code, 200)
        signal = resp.json()["signals"][0]
        self.assertEqual(signal["signal"], "hold")
        self.assertEqual(sorted(signal["missing"]), ["psych", "quant", "sentiment"])


if __name__ == "__main__":
    unittest.main()


class QuantForwardingTests(unittest.TestCase):
    """The TOP-10 decision parameters must reach the model.

    quant_crypto computes reversal_1m_pct, golden_cross_state and sigma_24h_pct
    and _quant_component used to drop all three, so the AI never saw
    mean-reversion (#10), the MA-cross trend state (#1/#2) or the 24h
    volatility read (#4). Found live on 2026-07-17: BTC's reversal_1m_pct was
    -3.9 in the analysis and absent from the snapshot.
    """

    ANALYSIS = {
        "signal_score": 1, "rsi_14": 48.6, "current_price": 63146.4,
        "volume_ratio": 0.44, "price_above_ma200": False,
        "momentum_12_1_pct": -44.74, "sigma_daily_pct": 1.902,
        "reversal_1m_pct": -3.901, "golden_cross_state": "death_cross",
        "sigma_24h_pct": 0.347, "trend_status": "mixed",
        "bullish_factors": [], "risk_factors": [],
        "as_of": "2026-07-17T12:00:00Z",
    }

    def _component(self, analysis):
        import signal_fusion
        with patch("quant_crypto.quant_crypto_enabled", return_value=True), \
             patch("quant_crypto.build_crypto_analysis", return_value=analysis):
            return signal_fusion._quant_component("BTCUSDT")

    def test_top10_parameters_reach_the_snapshot(self):
        c = self._component(self.ANALYSIS)
        self.assertEqual(c["reversal_1m_pct"], -3.901)      # #10 mean-reversion
        self.assertEqual(c["golden_cross_state"], "death_cross")  # #1/#2 trend
        self.assertEqual(c["sigma_24h_pct"], 0.347)         # #4 volatility (24h)
        self.assertEqual(c["sigma_daily_pct"], 1.902)       # #4 volatility (20d)

    def test_absent_values_pass_through_as_none_not_dropped(self):
        """A feed that returns nothing must read as None, not vanish — the
        verifier treats an absent key differently from a null."""
        thin = {**self.ANALYSIS, "reversal_1m_pct": None, "golden_cross_state": None}
        c = self._component(thin)
        self.assertIn("reversal_1m_pct", c)
        self.assertIsNone(c["reversal_1m_pct"])
        self.assertIn("golden_cross_state", c)


if __name__ == "__main__":
    unittest.main()
