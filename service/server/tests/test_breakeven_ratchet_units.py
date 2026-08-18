"""The breakeven ratchet's two arithmetic defects, from live tape.

Measured 2026-08-18 by reconstructing all four fires from their own legs:

  run 1335 AVAX pos-2  excursion 0.342192 vs arm 0.398   -> must NOT arm
  run 1358 FIL         unrealized 0.027738 vs round trip 0.025196 -> must NOT fire
  run 1367 SOL         +0.160 -> -0.067   -> must STILL fire
  run 1392 ZEC         +1.224 -> -0.534   -> must STILL fire

Defect (a): `peak`/`current` reach the rail RUN-CUMULATIVE while `arm` and the
fee floor are POSITION-scoped, so a fresh position inherits the peak an
earlier, already-closed position earned. `_trailing_lock_hit` in the same
block already takes `baseline_pnl`; this one never did.

Defect (b): the floor was ONE leg priced at `BREAKEVEN_FEE_RATE` 0.001, while
`fees.fee_rate("crypto")` is 0.00045 — 2.2x the true rate on the wrong number
of legs.

The two must be fixed TOGETHER. Baseline-correcting alone leaves a gross
position-scoped `current` measured against a one-leg floor, whose best case is
-1 open fee; the floor has to become a full ROUND TRIP in the same change.

Net measured effect over the four fires: +$0.138914 — the exact running total
these fires had accumulated. Tiny in dollars and reported as such: the defect
is that a protection rail fired at a guaranteed loss, not the amount.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import run_engine  # noqa: E402


class BreakevenUnitTests(unittest.TestCase):
    """Every number below is from the live tape, not invented."""

    def _pnl(self, qty, mark):
        return {"position": {"quantity": qty, "current_price": mark}}

    def test_avax_1335_position_two_never_arms(self):
        """Position 1 netted +0.170174 and closed. Position 2 opened, paid
        0.0895662, and inherited a run peak of 0.4228 it had not earned: its
        OWN excursion was 0.342192, under the 0.398 arm. It flattened at
        0.037672 gross against 0.179115 of fees — a guaranteed -0.141443."""
        self.assertFalse(
            run_engine._breakeven_floor_hit(
                0.4228002106349821,          # run-cumulative peak
                0.11828140938999473,         # run-cumulative total
                0.398,                       # arm, position-scoped
                exit_fee_usd=0.199,
                baseline_pnl=0.080608),      # realized before this position
            "a position armed on a peak an earlier position earned")

    def test_fil_1358_does_not_fire_inside_its_own_round_trip(self):
        """Single position, so the baseline is just its open fee (-0.0126108).
        Corrected current = 0.027738 gross; the true round trip is
        42.02759448 x 0.66614 x 0.00045 x 2 = 0.025196. Firing here banks
        less than the cost of the round trip it is closing."""
        round_trip = 42.02759448 * 0.66614 * 0.00045 * 2
        self.assertAlmostEqual(round_trip, 0.025196, places=5)
        self.assertFalse(
            run_engine._breakeven_floor_hit(
                0.06093749033999656, 0.015127412356799744, 0.056,
                exit_fee_usd=round_trip, baseline_pnl=-0.0126108),
            "fired while still above its own round-trip cost")

    def test_sol_1367_still_fires(self):
        """The rail doing its job: +0.160316 excursion given back to
        -0.067030 unrealized. A fix that silences this is not a fix."""
        round_trip = 0.691021056813667 * 75.607 * 0.00045 * 2
        self.assertTrue(
            run_engine._breakeven_floor_hit(
                0.13683633591999952, -0.09050959281999599, 0.1045,
                exit_fee_usd=round_trip, baseline_pnl=-0.0234805))

    def test_zec_1392_still_fires(self):
        """+1.224468 excursion given back to -0.533981. The largest fire on
        the tape and the clearest give-back."""
        round_trip = 0.9206539604826017 * 514.13 * 0.00045 * 2
        self.assertTrue(
            run_engine._breakeven_floor_hit(
                1.011228356799933, -0.7472207068000376, 0.9467,
                exit_fee_usd=round_trip, baseline_pnl=-0.21324141))

    def test_the_baseline_defaults_to_zero_for_every_existing_caller(self):
        self.assertTrue(run_engine._breakeven_floor_hit(1.0, -0.5, 0.5))

    def test_a_bad_baseline_never_raises(self):
        for bad in (None, "", "abc"):
            run_engine._breakeven_floor_hit(1.0, -0.5, 0.5, baseline_pnl=bad)


class BreakevenFeeRateTests(unittest.TestCase):
    def test_the_floor_uses_the_market_rate_not_the_legacy_default(self):
        """TRAP, and it decides whether this fix does anything at all:
        `fee_rate` returns the LEGACY 0.001 for every market unless
        `FEE_PER_MARKET` is on. It is `true` on prod (verified 2026-08-18 in
        the running worker: crypto 0.00045) and defaults to false off-prod,
        so a test that simply called `fee_rate` would assert the opposite of
        production and pass. Pin both sides."""
        import fees
        prior = os.environ.get("FEE_PER_MARKET")
        try:
            os.environ["FEE_PER_MARKET"] = "true"
            self.assertAlmostEqual(fees.fee_rate("crypto"), 0.00045, places=6)
            os.environ["FEE_PER_MARKET"] = "false"
            self.assertAlmostEqual(fees.fee_rate("crypto"), 0.001, places=6)
        finally:
            if prior is None:
                os.environ.pop("FEE_PER_MARKET", None)
            else:
                os.environ["FEE_PER_MARKET"] = prior

    def test_an_explicit_breakeven_override_still_wins(self):
        """`BREAKEVEN_FEE_RATE` is unset on prod (verified), so the market
        rate binds. If an operator ever sets it, it must still win — that is
        the documented escape hatch."""
        import inspect
        src = inspect.getsource(run_engine._evaluate_stop)
        self.assertIn("BREAKEVEN_FEE_RATE", src)

    def _stop_src(self):
        import inspect
        return "\n".join(
            ln.split("#")[0]
            for ln in inspect.getsource(run_engine._evaluate_stop).splitlines())

    def _breakeven_call(self):
        """The `_breakeven_floor_hit(...)` call ALONE.

        A plain grep of `_evaluate_stop` for "baseline_pnl" is VACUOUS — the
        trailing lock three lines above passes one too, so dropping it from
        THIS call left the test green. Mutation caught it; scope the grep to
        the call expression instead of the enclosing function."""
        src = self._stop_src()
        i = src.index("_breakeven_floor_hit(")
        depth, j = 0, i + len("_breakeven_floor_hit")
        for j in range(j, len(src)):
            if src[j] == "(":
                depth += 1
            elif src[j] == ")":
                depth -= 1
                if depth == 0:
                    break
        return src[i:j + 1]

    def test_the_call_site_passes_this_positions_baseline(self):
        call = self._breakeven_call()
        self.assertIn("baseline_pnl", call,
                      "the rail compares a run-cumulative peak against a "
                      "position-scoped arm — AVAX 1335 all over again")
        self.assertIn("realized", call,
                      "the baseline must be the run's realized P&L, the same "
                      "quantity the trailing lock uses")

    def test_the_call_site_prices_a_full_round_trip_at_the_market_rate(self):
        """B3 survived a first pass: the round trip is computed at the CALL
        SITE, so a unit test that passes `exit_fee_usd` by hand cannot see it
        revert to one leg."""
        src = self._stop_src()
        fee_block = src[src.index("_rate = "):src.index("_breakeven_floor_hit(")]
        self.assertIn("fee_rate", fee_block,
                      "the floor is still priced at the legacy flat rate")
        self.assertIn("* 2.0", fee_block,
                      "the floor is ONE leg again — best case is -1 open fee")


if __name__ == "__main__":
    unittest.main()
