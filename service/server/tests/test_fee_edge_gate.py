"""Fee/edge entry gate (2026-07-26): an open must promise a move bigger than
the round trip it costs.

Prod evidence that motivated it: the five ZEC winners captured 0.24–0.44%
gross against a 0.2% round trip, so the 0.1%/side fee took 44–82% of every
win (run 109 paid $9.13 in fees to net $1.98). Gating on the thesis' stated
expected move keeps the desk out of trades that cannot pay for themselves.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import run_engine
from fees import TRADE_FEE_RATE

# 0.1%/side ⇒ 0.2% round trip ⇒ 0.6% of REALIZED move required at the 3×
# default. The thesis claim is discounted by the realization factor first, so
# the claim itself must clear 0.6% / 0.25 = 2.4%.
ROUND_TRIP_PCT = TRADE_FEE_RATE * 2 * 100.0
REQUIRED_PCT = ROUND_TRIP_PCT * 3.0
DEFAULT_REALIZATION = 0.25
REQUIRED_CLAIM = REQUIRED_PCT / DEFAULT_REALIZATION


class FeeEdgeGateTests(unittest.TestCase):
    def tearDown(self):
        for key in ("RUN_FEE_EDGE_MULTIPLE", "RUN_FEE_EDGE_REALIZATION"):
            os.environ.pop(key, None)

    def test_move_below_three_round_trips_is_refused(self):
        skip = run_engine._fee_edge_skip(0.44)      # the ZEC-sized move
        self.assertIsNotNone(skip)
        self.assertIn("fee_edge", skip)

    def test_claim_is_discounted_by_the_realization_factor(self):
        """The regression that motivated this: grading the RAW claim passed
        all 40 prod runs (zero effect). At the measured prod median
        realization of 0.154, ETH run 112's claimed 3.43% is really
        3.43 × 0.154 = 0.53% — under the 0.6% hurdle — so the run that went on
        to lose $70.13 is refused."""
        os.environ["RUN_FEE_EDGE_REALIZATION"] = "0.154"   # prod median
        skip = run_engine._fee_edge_skip(3.43)
        self.assertIsNotNone(skip, "run 112 claimed 3.43% and lost $70.13")
        self.assertIn("realization", skip)
        # The raw claim would have sailed past the hurdle unchanged.
        os.environ["RUN_FEE_EDGE_REALIZATION"] = "1.0"
        self.assertIsNone(run_engine._fee_edge_skip(3.43))

    def test_move_clearing_the_hurdle_passes(self):
        self.assertIsNone(run_engine._fee_edge_skip(REQUIRED_CLAIM + 0.01))

    def test_hurdle_is_three_round_trips_of_realized_move(self):
        self.assertIsNone(run_engine._fee_edge_skip(REQUIRED_CLAIM))
        self.assertIsNotNone(run_engine._fee_edge_skip(REQUIRED_CLAIM - 0.01))

    def test_realization_factor_is_configurable_and_clamped(self):
        os.environ["RUN_FEE_EDGE_REALIZATION"] = "1.0"     # trust the claim
        self.assertIsNone(run_engine._fee_edge_skip(REQUIRED_PCT + 0.01))
        os.environ["RUN_FEE_EDGE_REALIZATION"] = "garbage"
        self.assertEqual(run_engine._thesis_realization(), 0.25)
        os.environ["RUN_FEE_EDGE_REALIZATION"] = "0"       # clamped off zero
        self.assertEqual(run_engine._thesis_realization(), 0.01)

    def test_direction_does_not_matter(self):
        """A short thesis states a negative move; only magnitude is graded."""
        self.assertIsNone(run_engine._fee_edge_skip(-(REQUIRED_CLAIM + 0.5)))
        self.assertIsNotNone(run_engine._fee_edge_skip(-0.3))

    def test_absent_expectation_is_not_refused(self):
        """The gate refuses only moves it can prove are too small — a thesis
        with no stated expectation is left to the other rails."""
        self.assertIsNone(run_engine._fee_edge_skip(None))
        self.assertIsNone(run_engine._fee_edge_skip(0))
        self.assertIsNone(run_engine._fee_edge_skip("not-a-number"))

    def test_multiple_is_configurable_and_zero_disables(self):
        os.environ["RUN_FEE_EDGE_MULTIPLE"] = "0"
        self.assertIsNone(run_engine._fee_edge_skip(0.01))
        os.environ["RUN_FEE_EDGE_MULTIPLE"] = "10"
        self.assertIsNotNone(run_engine._fee_edge_skip(REQUIRED_CLAIM + 0.01))

    def test_bad_multiple_falls_back_to_default(self):
        os.environ["RUN_FEE_EDGE_MULTIPLE"] = "garbage"
        self.assertEqual(run_engine._fee_edge_multiple(), 3.0)


if __name__ == "__main__":
    unittest.main()
