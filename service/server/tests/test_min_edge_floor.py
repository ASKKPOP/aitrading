"""Absolute edge floor, independent of fees (2026-07-28).

The fee multiple stopped filtering the moment fees became per-market. It ties
the edge requirement to the fee, so once fees differ 20x across venues one
multiple cannot serve them — measured on the live universe:

    required DISCOUNTED move, at multiple M
    market      M=3      M=10     M=20     M=40
    crypto      0.270%   0.900%   1.800%   3.600%
    futures     0.030%   0.100%   0.200%   0.400%

Raising M to protect crypto over-blocks futures; lowering it to admit futures
lets crypto noise through. The flat-fee gate admitted 67% of all theses;
per-market fees took that to 100%, which is not a gate.

This floor is a NOISE bar, not a proven-edge threshold. 0.15% admits 96% of
the universe and 78% of forex, refusing only the weakest FX theses. 0.25%
would cut forex to 28% and quietly undo a market just deliberately opened.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import fees
import run_engine


class Base(unittest.TestCase):
    def setUp(self):
        fees.reset_override_cache()
        self._p = patch.dict("os.environ", {"FEE_PER_MARKET": "true"})
        self._p.start()

    def tearDown(self):
        self._p.stop()
        fees.reset_override_cache()

    def skip(self, move, market):
        return run_engine._fee_edge_skip(move, market=market)


class Floor(Base):
    def test_default_is_the_measured_noise_bar(self):
        self.assertAlmostEqual(run_engine._min_edge_pct(), 0.15)

    def test_bad_env_falls_back(self):
        with patch.dict("os.environ", {"RUN_MIN_EDGE_PCT": "loads"}):
            self.assertAlmostEqual(run_engine._min_edge_pct(), 0.15)

    def test_zero_disables_it(self):
        with patch.dict("os.environ", {"RUN_MIN_EDGE_PCT": "0"}):
            self.assertEqual(run_engine._min_edge_pct(), 0.0)
            # 0.5% claimed -> 0.125% realized: over the futures fee hurdle
            # (0.03%) but under the floor, so only the floor would refuse it.
            self.assertIsNone(self.skip(0.5, "futures"))

    def test_floor_binds_where_fees_no_longer_would(self):
        """0.5% claimed = 0.125% realized. Futures fees want only 0.03%, so
        without the floor this passes on a move indistinguishable from zero."""
        with patch.dict("os.environ", {"RUN_MIN_EDGE_PCT": "0"}):
            self.assertIsNone(self.skip(0.5, "futures"))
        self.assertIsNotNone(self.skip(0.5, "futures"))

    def test_the_reason_says_which_hurdle_bound(self):
        """A skip that blames fees when the floor bound it would send the next
        reader to fix the wrong number."""
        r = self.skip(0.5, "futures")
        self.assertIn("min_edge", r)
        self.assertIn("fees would have allowed", r)

    def test_fee_hurdle_still_reported_when_it_is_the_binding_one(self):
        """Crypto fees (0.27% required) are above the 0.15% floor."""
        r = self.skip(0.8, "crypto")          # 0.20% realized
        self.assertIsNotNone(r)
        self.assertIn("fee_edge", r)
        self.assertNotIn("min_edge", r)


class TheDeployedUniverse(Base):
    """Numbers taken from the live thesis table."""

    def test_the_forex_runs_that_just_opened_still_pass(self):
        # USDZAR 1.80% -> 0.450% ; USDKRW 1.50% -> 0.375%
        self.assertIsNone(self.skip(1.80, "forex"))
        self.assertIsNone(self.skip(1.50, "forex"))

    def test_the_weakest_fx_thesis_is_refused(self):
        # AUDJPY 0.443% -> 0.111%, under the 0.15% floor
        self.assertIsNotNone(self.skip(0.443, "forex"))

    def test_the_futures_and_crypto_theses_still_pass(self):
        for mv, mkt in ((2.37, "futures"), (4.50, "futures"),
                        (3.50, "crypto"), (2.00, "crypto")):
            self.assertIsNone(self.skip(mv, mkt), f"{mv}% {mkt} should trade")

    def test_noise_is_refused_in_every_market(self):
        for mkt in ("crypto", "futures", "forex", "us-stock"):
            self.assertIsNotNone(self.skip(0.02, mkt))
            self.assertIsNotNone(self.skip(0.30, mkt))   # 0.075% realized

    def test_the_floor_is_not_market_dependent(self):
        """The whole point: the same tiny move is refused everywhere, however
        cheap the venue."""
        for mkt in ("crypto", "futures", "forex", "us-stock", "a-stock"):
            self.assertIsNotNone(self.skip(0.4, mkt))    # 0.10% realized


if __name__ == "__main__":
    unittest.main()
