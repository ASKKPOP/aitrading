"""Leverage safety pair: #3 leverage-aware conviction sizing + #4 liq cushion.

#3 — at leverage L>1, marginal conviction commits less margin (a wrong L×
     thesis burns margin L× faster toward the 1/L liquidation line); high
     conviction is untouched; L=1 is byte-identical to the prior sizing.
#4 — a protective stop fires INSIDE the liquidation line, so a small position
     whose USD max_loss stop sits beyond the liq price still exits under control
     instead of being liquidated.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import unittest

import run_engine


class LeverageAwareSizingTests(unittest.TestCase):
    def setUp(self):
        self._env = patch.dict(os.environ, {
            "RUN_SIZE_BY_CONVICTION": "true", "RUN_LEV_SIZING": "true",
            "RUN_LEV_SIZE_DAMP": "0.5"})
        self._env.start()

    def tearDown(self):
        self._env.stop()

    def test_1x_is_base_behaviour(self):
        # conviction 0.60 → base (0.60-0.45)/0.30 = 0.5, unchanged at 1×
        self.assertEqual(run_engine._conviction_size_scale(0.60, 1.0), 0.5)

    def test_3x_tempers_marginal_conviction(self):
        # 0.5 ** (1 + 0.5*2) = 0.5**2 = 0.25 → clamped to 0.30 floor
        s3 = run_engine._conviction_size_scale(0.60, 3.0)
        self.assertLess(s3, 0.5)
        self.assertEqual(s3, 0.30)

    def test_high_conviction_untouched(self):
        # conviction ≥0.75 → base 1.0 → 1.0**anything == 1.0 (certain = full size)
        self.assertEqual(run_engine._conviction_size_scale(0.75, 3.0), 1.0)

    def test_more_leverage_smaller_size(self):
        s2 = run_engine._conviction_size_scale(0.66, 2.0)
        s5 = run_engine._conviction_size_scale(0.66, 5.0)
        self.assertLess(s5, s2)   # monotone: more leverage → less margin

    def test_killswitch_off_restores_base(self):
        with patch.dict(os.environ, {"RUN_LEV_SIZING": "0"}):
            self.assertEqual(run_engine._conviction_size_scale(0.60, 3.0), 0.5)

    def test_conviction_sizing_disabled_returns_none(self):
        with patch.dict(os.environ, {"RUN_SIZE_BY_CONVICTION": "0"}):
            self.assertIsNone(run_engine._conviction_size_scale(0.60, 3.0))


class LiquidationCushionStopTests(unittest.TestCase):
    def setUp(self):
        self._env = patch.dict(os.environ, {
            "RUN_LIQ_CUSHION": "true", "RUN_LIQ_CUSHION_FRAC": "0.85"})
        self._env.start()

    def tearDown(self):
        self._env.stop()

    def _stop(self, qty, entry, mark, lev):
        pos = {"quantity": qty, "entry_price": entry,
               "current_price": mark, "leverage": lev}
        pnl = {"position": pos, "mark_age_ok": True, "total": -1.0, "trades": 1}
        with patch.object(run_engine, "compute_run_pnl", return_value=pnl):
            return run_engine._evaluate_stop({"stop_conditions_json": "{}"})

    # long 3× at 100: liq at 66.67, cushion (0.85) at 100*(1-0.85/3)=71.67
    def test_long_cushion_fires_before_liq(self):
        self.assertEqual(self._stop(10.0, 100.0, 71.0, 3.0), "stop_event:liq_cushion")

    def test_long_above_cushion_is_clear(self):
        self.assertIsNone(self._stop(10.0, 100.0, 72.0, 3.0))

    def test_long_cushion_wins_even_past_liq(self):
        # checked before the hard-liq branch → a controlled close, not a wipe
        self.assertEqual(self._stop(10.0, 100.0, 65.0, 3.0), "stop_event:liq_cushion")

    # short 3× at 100: liq at 133.33, cushion at 100*(1+0.85/3)=128.33
    def test_short_cushion_fires(self):
        self.assertEqual(self._stop(-10.0, 100.0, 129.0, 3.0), "stop_event:liq_cushion")

    def test_short_below_cushion_is_clear(self):
        self.assertIsNone(self._stop(-10.0, 100.0, 128.0, 3.0))

    def test_l1_inert(self):
        # L=1 long never liquidates and has no cushion
        self.assertIsNone(self._stop(10.0, 100.0, 50.0, 1.0))

    def test_killswitch_off_falls_through_to_hard_liq(self):
        with patch.dict(os.environ, {"RUN_LIQ_CUSHION": "0"}):
            # mark 65 < liq 66.67 and no cushion → the hard liquidation fires
            self.assertEqual(self._stop(10.0, 100.0, 65.0, 3.0), "synthetic_liquidation")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
