"""Golden tests for confluence.py — B1–B6/S1–S6 condition math.

Every condition gets an explicit true / false / null case, boundaries use the
plan's half-open conventions, and nulls must never count as satisfied.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from confluence import compute_conditions, evaluate_confluence


def _analysis(**over):
    base = {
        "price_above_ma200": True,
        "momentum_12_1_pct": 12.5,
        "signal_score": 3,
        "volume_ratio": 2.0,
        "long_short_ratio": 1.2,
    }
    base.update(over)
    return base


def _psych(fng_value=50, delta_3d=0, spikes=(), shock=(), available=True,
           created_at="2099-01-01T00:00:00Z", **over):
    base = {
        "available": available,
        "fear_greed": {"value": fng_value, "delta_3d": delta_3d},
        "spikes": list(spikes),
        "shock": list(shock),
        "created_at": created_at,
    }
    base.update(over)
    return base


def _compute(market="crypto", analysis=None, sentiment=None, psych=None,
             shock_hist=None, next_event_hours=100.0, event_window_active=False,
             now=None):
    from datetime import datetime, timezone
    return compute_conditions(
        market,
        analysis=analysis,
        sentiment=sentiment,
        psych=psych,
        shock_hist=shock_hist,
        next_event_hours=next_event_hours,
        event_window_active=event_window_active,
        now=now or datetime(2099, 1, 1, 1, 0, tzinfo=timezone.utc),
    )


class BuySideTests(unittest.TestCase):
    def test_full_bullish_reaches_six(self):
        result = _compute(
            analysis=_analysis(),
            sentiment={"tilt": 0.4, "n": 20, "prev_tilt": 0.1},
            psych=_psych(fng_value=25, delta_3d=6),
            shock_hist=[],
        )
        self.assertEqual(result["buy_confluence"], 6)
        self.assertEqual(result["direction_bias"], "long")
        self.assertEqual(result["vetoes"], [])

    def test_missing_analysis_makes_technical_conditions_null(self):
        result = _compute(analysis=None, sentiment={"tilt": 0.4, "n": 20, "prev_tilt": None},
                          psych=_psych(fng_value=25, delta_3d=6))
        for key in ("B1", "B2", "B3", "S1", "S2", "S3"):
            self.assertIsNone(result["conditions"][key], key)
            self.assertIn(key, result["nulls"])
        # nulls never satisfy: only B4, B5, B6 can contribute here
        self.assertLessEqual(result["buy_confluence"], 3)

    def test_b3_null_when_volume_ratio_missing_even_with_strong_score(self):
        result = _compute(analysis=_analysis(volume_ratio=None, signal_score=4))
        self.assertIsNone(result["conditions"]["B3"])
        self.assertIn("volume", result["nulls"]["B3"])

    def test_b3_false_when_volume_below_min(self):
        result = _compute(analysis=_analysis(volume_ratio=1.2, signal_score=4))
        self.assertIs(result["conditions"]["B3"], False)

    def test_b3_stock_cutoff_is_three(self):
        ok = _compute("us-stock", analysis=_analysis(signal_score=3.0))
        low = _compute("us-stock", analysis=_analysis(signal_score=2.5))
        self.assertIs(ok["conditions"]["B3"], True)
        self.assertIs(low["conditions"]["B3"], False)

    def test_b2_momentum_zero_satisfies_neither_side(self):
        result = _compute(analysis=_analysis(momentum_12_1_pct=0.0))
        self.assertIs(result["conditions"]["B2"], False)
        self.assertIs(result["conditions"]["S2"], False)

    def test_b4_recovering_branch(self):
        rec = _compute(sentiment={"tilt": -0.1, "n": 20, "prev_tilt": -0.3}, psych=_psych())
        flat = _compute(sentiment={"tilt": -0.1, "n": 20, "prev_tilt": -0.1}, psych=_psych())
        no_prev = _compute(sentiment={"tilt": -0.1, "n": 20, "prev_tilt": None}, psych=_psych())
        self.assertIs(rec["conditions"]["B4"], True)
        self.assertIs(flat["conditions"]["B4"], False)
        self.assertIs(no_prev["conditions"]["B4"], False)

    def test_negative_spike_fails_b4_and_vetoes_buys(self):
        spike = {"category": "crypto", "spike": True, "direction": "negative", "z": -2.5}
        result = _compute(sentiment={"tilt": 0.5, "n": 20, "prev_tilt": None},
                          psych=_psych(spikes=[spike]))
        self.assertIs(result["conditions"]["B4"], False)
        self.assertTrue(any("buy_veto" in v for v in result["vetoes"]))

    def test_stale_psych_spike_does_not_veto(self):
        """A negative spike from a snapshot older than 24h must not veto."""
        from datetime import datetime, timezone
        spike = {"category": "crypto", "spike": True, "direction": "negative", "z": -2.5}
        result = _compute(sentiment={"tilt": 0.5, "n": 20, "prev_tilt": None},
                          psych=_psych(spikes=[spike], created_at="2098-12-28T00:00:00Z"),
                          now=datetime(2099, 1, 1, tzinfo=timezone.utc))
        self.assertEqual(result["vetoes"], [])
        self.assertIs(result["conditions"]["B4"], True)

    def test_b5_fear_recovery_leg(self):
        recovering = _compute(psych=_psych(fng_value=25, delta_3d=6))
        deepening = _compute(psych=_psych(fng_value=25, delta_3d=-3), shock_hist=[])
        not_fear = _compute(psych=_psych(fng_value=50, delta_3d=6), shock_hist=[])
        self.assertIs(recovering["conditions"]["B5"], True)
        self.assertIs(deepening["conditions"]["B5"], False)
        self.assertIs(not_fear["conditions"]["B5"], False)

    def test_b5_shock_cleared_leg(self):
        cleared = _compute(
            psych=_psych(fng_value=50, delta_3d=0, shock=[]),
            shock_hist=[{"created_at": "2099-01-01T00:00:00Z",
                         "shocks": [{"symbol": "BTCUSDT", "shock": True}]}])
        still_active = _compute(
            psych=_psych(fng_value=50, delta_3d=0,
                         shock=[{"symbol": "BTCUSDT", "shock": True}]),
            shock_hist=[{"created_at": "2099-01-01T00:00:00Z",
                         "shocks": [{"symbol": "BTCUSDT", "shock": True}]}])
        self.assertIs(cleared["conditions"]["B5"], True)
        self.assertIs(still_active["conditions"]["B5"], False)

    def test_b6_event_window_boundary(self):
        near = _compute(next_event_hours=10.0)
        far = _compute(next_event_hours=30.0)
        unavailable = _compute(next_event_hours=None)
        self.assertIs(near["conditions"]["B6"], False)
        self.assertIs(far["conditions"]["B6"], True)
        self.assertIsNone(unavailable["conditions"]["B6"])

    def test_active_event_window_vetoes_both_sides(self):
        result = _compute(event_window_active=True)
        self.assertTrue(any("entry_veto" in v for v in result["vetoes"]))


class SellSideTests(unittest.TestCase):
    def test_full_bearish(self):
        result = _compute(
            analysis=_analysis(price_above_ma200=False, momentum_12_1_pct=-15.0,
                               signal_score=-3, volume_ratio=2.5, long_short_ratio=2.5),
            psych=_psych(fng_value=82, delta_3d=2,
                         shock=[{"symbol": "BTCUSDT", "shock": True}]),
        )
        # S1, S2, S3, S4, S5 all true; S6 always null → 5 is the display max
        self.assertEqual(result["sell_confluence"], 5)
        self.assertEqual(result["direction_bias"], "short")

    def test_s4_secondary_leg_needs_both_fng_and_ls(self):
        both = _compute(analysis=_analysis(long_short_ratio=2.5), psych=_psych(fng_value=76))
        ls_only = _compute(analysis=_analysis(long_short_ratio=2.5), psych=_psych(fng_value=60))
        fng_mid = _compute(analysis=_analysis(long_short_ratio=1.0), psych=_psych(fng_value=76))
        self.assertIs(both["conditions"]["S4"], True)
        self.assertIs(ls_only["conditions"]["S4"], False)
        self.assertIs(fng_mid["conditions"]["S4"], False)

    def test_s5_unresolved_shock_has_no_expiry(self):
        result = _compute(psych=_psych(shock=[{"symbol": "ETHUSDT", "shock": True}]))
        self.assertIs(result["conditions"]["S5"], True)

    def test_s6_always_null_with_reason(self):
        result = _compute(analysis=_analysis())
        self.assertIsNone(result["conditions"]["S6"])
        self.assertIn("watcher", result["nulls"]["S6"])


class MarketScopeTests(unittest.TestCase):
    def test_stock_market_nulls_crypto_only_conditions(self):
        result = _compute("us-stock", analysis=_analysis(), psych=_psych(fng_value=10))
        for key in ("B5", "S4", "S5"):
            self.assertIsNone(result["conditions"][key], key)
            self.assertIn(key, result["nulls"])


class WrapperTests(unittest.TestCase):
    def test_evaluate_confluence_fail_soft_all_sources_down(self):
        """With every gate off and no data sources, the wrapper must return a
        well-formed all-null result, never raise."""
        with patch("confluence._fetch_sentiment", return_value=None), \
             patch("market_events.upcoming_events", side_effect=Exception("down")):
            result = evaluate_confluence("BTC", "crypto")
        self.assertEqual(result["symbol"], "BTC")
        self.assertEqual(result["buy_confluence"], 0)
        self.assertEqual(result["sell_confluence"], 0)
        self.assertGreaterEqual(len(result["nulls"]), 8)
        self.assertIn("note", result)

    def test_evaluate_confluence_uses_passed_payloads(self):
        with patch("confluence._fetch_sentiment",
                   return_value={"tilt": 0.4, "n": 10, "prev_tilt": None}):
            result = evaluate_confluence(
                "BTC", "crypto",
                analysis=_analysis(),
                psych=_psych(fng_value=25, delta_3d=6),
            )
        self.assertGreaterEqual(result["buy_confluence"], 4)


if __name__ == "__main__":
    unittest.main()
