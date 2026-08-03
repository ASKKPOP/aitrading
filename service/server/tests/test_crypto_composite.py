"""Plan 21 P3 — six-component crypto regime composite (advisory).

Pure scorers, weight redistribution, the TTL cache contract, the
evaluate_market_regime attachment, and the stage-2 research backdrop line.
Distilled from the hermes work-package upstream's crypto-regime-analyzer;
keyless (OKX candles + funding only).
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import regime
import symbol_research as sr


def _trend_up(n: int = 260, start: float = 100.0, step: float = 0.5) -> list[float]:
    return [start + i * step for i in range(n)]


def _trend_down(n: int = 260, start: float = 300.0, step: float = 0.5) -> list[float]:
    return [start - i * step for i in range(n)]


class ScorerTests(unittest.TestCase):
    def test_btc_trend_up_scores_full(self):
        self.assertEqual(regime.score_btc_trend(_trend_up()), 100.0)

    def test_btc_trend_down_scores_low(self):
        score = regime.score_btc_trend(_trend_down())
        self.assertLessEqual(score, 20.0)

    def test_btc_trend_short_series_is_none(self):
        self.assertIsNone(regime.score_btc_trend(_trend_up(100)))

    def test_alt_breadth_counts_only_alts_with_history(self):
        alts = [_trend_up(), _trend_down(), _trend_up(50)]  # third: no 200DMA
        self.assertEqual(regime.score_alt_breadth(alts), 50.0)
        self.assertIsNone(regime.score_alt_breadth([_trend_up(50)]))

    def test_dominance_proxy_rewards_alt_participation(self):
        btc = _trend_up(60, 100.0, 0.1)          # mild BTC uptrend
        alts = [_trend_up(60, 100.0, 1.0)] * 3   # alts far outperforming
        strong = regime.score_dominance_proxy(btc, alts)
        weak = regime.score_dominance_proxy(_trend_up(60, 100.0, 1.0),
                                            [_trend_up(60, 100.0, 0.1)] * 3)
        self.assertGreater(strong, weak)

    def test_dominance_proxy_flight_to_safety_penalty(self):
        btc_down = _trend_down(60, 300.0, 0.5)
        alts_worse = [_trend_down(60, 300.0, 2.0)] * 3
        score = regime.score_dominance_proxy(btc_down, alts_worse)
        self.assertLess(score, 40.0)

    def test_funding_neutral_scores_high_extremes_low(self):
        self.assertEqual(regime.score_funding([regime._FUNDING_NEUTRAL]), 100.0)
        self.assertEqual(regime.score_funding([0.001]), 0.0)  # crowded longs
        # crowded shorts penalized at 60% of the long-side slope
        short_side = regime.score_funding([-0.00065])
        long_side = regime.score_funding([0.00085])
        self.assertGreater(short_side, long_side)
        self.assertIsNone(regime.score_funding([]))

    def test_cycle_score_shallow_dd_beats_deep(self):
        at_high = _trend_up()
        deep = _trend_up() + [200.0 * 0.4]  # ~last far below the high
        self.assertGreater(regime.score_cycle(at_high), regime.score_cycle(deep))

    def test_thrust_fraction_positive(self):
        btc = _trend_up(60)
        alts = [_trend_up(60), _trend_down(60), _trend_down(60)]
        self.assertEqual(regime.score_thrust(btc, alts), 50.0)


class ComposeTests(unittest.TestCase):
    def test_all_present(self):
        out = regime.compose_crypto_composite({
            "btc_trend": 100, "alt_breadth": 100, "dominance_proxy": 100,
            "funding": 100, "cycle": 100, "thrust": 100})
        self.assertEqual(out["score"], 100.0)
        self.assertEqual(out["zone"], "RISK_ON")
        self.assertEqual(out["missing"], [])

    def test_missing_weight_redistributes(self):
        out = regime.compose_crypto_composite({
            "btc_trend": 80, "alt_breadth": None, "dominance_proxy": None,
            "funding": 80, "cycle": 80, "thrust": 80})
        self.assertEqual(out["score"], 80.0)  # redistribution keeps the level
        self.assertEqual(out["missing"], ["alt_breadth", "dominance_proxy"])

    def test_zones(self):
        mk = lambda v: regime.compose_crypto_composite(  # noqa: E731
            {k: v for k in regime.COMPOSITE_WEIGHTS})
        self.assertEqual(mk(85)["zone"], "RISK_ON")
        self.assertEqual(mk(60)["zone"], "NEUTRAL")
        self.assertEqual(mk(20)["zone"], "RISK_OFF")

    def test_all_missing_is_none(self):
        self.assertIsNone(regime.compose_crypto_composite(
            {k: None for k in regime.COMPOSITE_WEIGHTS}))


class EvaluateTests(unittest.TestCase):
    def setUp(self):
        regime._composite_cache["at"] = 0.0
        regime._composite_cache["value"] = None

    tearDown = setUp

    def test_cached_only_never_fetches_on_cold_cache(self):
        with patch("crypto_feed.fetch_candles",
                   side_effect=AssertionError("must not fetch")):
            self.assertIsNone(regime.evaluate_crypto_composite(cached_only=True))

    def test_evaluate_computes_and_caches(self):
        def candles(symbol, bar="1D", limit=100):
            return [{"close": c} for c in _trend_up(min(limit, 300))]

        with patch("crypto_feed.fetch_candles", side_effect=candles), \
             patch("crypto_feed.fetch_funding_rate",
                   return_value={"funding_rate": regime._FUNDING_NEUTRAL}):
            out = regime.evaluate_crypto_composite()
        self.assertIsNotNone(out)
        self.assertGreaterEqual(out["score"], 80.0)
        self.assertEqual(out["zone"], "RISK_ON")
        self.assertIn("as_of", out)
        # warm cache serves without touching the network
        with patch("crypto_feed.fetch_candles",
                   side_effect=AssertionError("must not fetch")):
            self.assertEqual(regime.evaluate_crypto_composite(cached_only=True),
                             out)

    def test_fetch_failure_keeps_stale_value(self):
        regime._composite_cache["value"] = {"score": 55.0, "zone": "NEUTRAL"}
        regime._composite_cache["at"] = -1e9  # expired
        with patch("crypto_feed.fetch_candles", side_effect=RuntimeError("down")):
            out = regime.evaluate_crypto_composite()
        self.assertEqual(out["score"], 55.0)

    def test_market_regime_payload_carries_composite(self):
        sentinel = {"score": 61.0, "zone": "NEUTRAL", "components": {}}
        with patch.object(regime, "evaluate_crypto_composite",
                          return_value=sentinel), \
             patch("psych_feed.psych_feed_enabled", return_value=False), \
             patch("crypto_feed.fetch_candles", return_value=[]), \
             patch("market_events.active_event_window", return_value=None):
            out = regime.evaluate_market_regime(persist=False)
        self.assertEqual(out["crypto_composite"], sentinel)


class ResearchBackdropTests(unittest.TestCase):
    def _survivor(self):
        return {
            "symbol": "BTCUSDT", "market": "crypto", "eps_raw": 1.0,
            "momentum_sign": 1.0, "session_open": True,
            "factors": {"last": 63000.0, "mom_5d": 3.0, "mom_20d": 4.0,
                        "vol_daily_pct": 2.0, "vol_ratio": 1.1},
        }

    def _prompt_with_composite(self, composite):
        seen = {}

        def fake_generate(prompt, **kw):
            seen["p"] = prompt
            return ('[{"symbol":"BTCUSDT","market":"crypto","direction":"long",'
                    '"expected_move_pct":2.0,"horizon_hours":24,"confidence":0.6,'
                    '"thesis":"t","risks":"r",'
                    '"invalidation":"below the recent swing low"}]')

        with patch.object(sr, "_previous_thesis", return_value=None), \
             patch("regime.evaluate_crypto_composite", return_value=composite):
            sr.generate_theses([self._survivor()], generate_text=fake_generate)
        return seen.get("p", "")

    def test_backdrop_line_renders_from_cache(self):
        prompt = self._prompt_with_composite({"score": 72.5, "zone": "NEUTRAL"})
        self.assertIn("CRYPTO MARKET BACKDROP: composite 72.5/100", prompt)
        self.assertIn("judge each candidate on its own data", prompt)

    def test_cold_cache_renders_nothing(self):
        prompt = self._prompt_with_composite(None)
        self.assertNotIn("CRYPTO MARKET BACKDROP", prompt)


if __name__ == "__main__":
    unittest.main()
