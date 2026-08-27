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
import unittest.mock
from unittest.mock import patch

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
        args = (0.06093749033999656, 0.015127412356799744, 0.056)
        kw = {"exit_fee_usd": round_trip, "baseline_pnl": -0.0126108}
        # SUPERSEDED 2026-08-27 for the fire/no-fire call, PRESERVED for the
        # invariant it actually guards. Its own excursion peaked at 0.073548
        # and this reading is 0.027738 — a 62% give-back. The old rule held
        # on, because it only ever protected against going negative; the
        # 30-fire measurement (median give-back 103.1% of peak) says that
        # tolerance IS the loss, so under the lock it banks here instead.
        with patch.dict(os.environ, {"RATCHET_LOCK_FRAC": "0"}):
            self.assertFalse(run_engine._breakeven_floor_hit(*args, **kw),
                             "kill switch must restore the old tolerance")
        self.assertTrue(run_engine._breakeven_floor_hit(*args, **kw),
                        "a 62% give-back must be banked, not ridden down")
        # The ORIGINAL 2026-08-15 guarantee still holds: the lock can only
        # RAISE the floor (it adds a non-negative term to fee_floor), so
        # every case that fired under the old rule still fires. Checked at
        # the old boundary itself — gross exactly at the fee floor.
        at_fee_floor = (-0.0126108) + round_trip
        for frac in ("0", "0.5"):
            with patch.dict(os.environ, {"RATCHET_LOCK_FRAC": frac}):
                self.assertTrue(
                    run_engine._breakeven_floor_hit(
                        0.06093749033999656, at_fee_floor, 0.056,
                        exit_fee_usd=round_trip, baseline_pnl=-0.0126108),
                    f"lock={frac} must not un-fire the old boundary")

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
        """R21 revision (run 1417): the baseline is realized AT THE PEAK
        EPOCH (peak_realized_usd, frozen when the peak was stamped) — a
        current-realized baseline let the desk's own losing covers
        manufacture phantom peaks. Legacy NULL rows fall back to current
        realized until their next peak stamp."""
        call = self._breakeven_call()
        self.assertIn("baseline_pnl", call,
                      "the rail compares a run-cumulative peak against a "
                      "position-scoped arm — AVAX 1335 all over again")
        self.assertIn("_be_base", call,
                      "the baseline must be the peak-epoch realized value, "
                      "not realized-at-fire (run 1417 phantom peak)")

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


class PeakEpochBaselineTests(unittest.TestCase):
    """R21 (2026-08-18, run 1417, two-agent cross-checked): the call-site
    baseline must be realized AT THE PEAK EPOCH, never realized-at-fire.
    1417's numbers, from the live tape: run peak +0.044682 stamped at
    09:27Z when realized was -0.056806; by the 12:23:00 fire, realized had
    fallen to -0.416734 through the desk's own losing covers. True position
    excursion 0.1015 < arm 0.2549 — yet current-realized as baseline
    manufactured a phantom peak of 0.4614 and flattened the remainder."""

    ARM = 0.2549
    FEE = 0.0287

    def test_1417_does_not_arm_with_peak_epoch_baseline(self):
        self.assertFalse(
            run_engine._breakeven_floor_hit(
                0.044682, -0.747221, self.ARM,
                exit_fee_usd=self.FEE,
                baseline_pnl=-0.056806),   # realized AT the peak epoch
            "armed on a position whose true excursion never reached the arm")

    def test_1417_would_fire_with_the_defective_fire_time_baseline(self):
        """Documents the defect: the same inputs with realized-at-fire as
        baseline DO fire — this is the phantom-peak mechanism, kept as the
        disproof that the epoch baseline is load-bearing."""
        self.assertTrue(
            run_engine._breakeven_floor_hit(
                0.044682, -0.747221, self.ARM,
                exit_fee_usd=self.FEE,
                baseline_pnl=-0.416734))   # realized at FIRE time (defect)

    def test_call_site_uses_peak_epoch_baseline_with_legacy_fallback(self):
        """Wiring (the brief-line lesson): the stop evaluator must read
        peak_realized_usd and fall back to current realized only when the
        column is NULL (legacy rows)."""
        import inspect
        src = inspect.getsource(run_engine._evaluate_stop)
        self.assertIn('run.get("peak_realized_usd")', src)
        i = src.find('peak_realized_usd')
        j = src.find('_breakeven_floor_hit', i)
        self.assertGreater(j, i, "epoch baseline must be read before the ratchet call")

    def test_peak_stamp_writes_realized_beside_the_peak(self):
        import inspect
        src = inspect.getsource(run_engine._ratchet_peak_pnl)
        self.assertIn("peak_realized_usd", src)
        self.assertIn('pnl.get("realized")', src)


class RatchetLockFractionTests(unittest.TestCase):
    """The ratchet's best case was $0 BY CONSTRUCTION — and that is why the
    book cannot win.

    Measured 2026-08-27 across all 30 stop_mechanism fires since 08-01:
      peak / arm      median 1.18x, p75 1.76x  (24 of 30 never reached 2x)
      give-back       median 103.1% of peak, p25 84.0%
      realized total  median -$0.0066

    A position that peaks at 1.18x its arm and then exits at breakeven
    returns the ENTIRE peak; the median trip gives back MORE than it ever
    earned. With a 46% directional win rate the book still loses, because
    the payoff ratio is 0.22 — winners capped near zero, losers run to the
    stop. No entry-side intelligence can survive that geometry.

    The fix locks a FRACTION of the earned peak instead of exiting at
    breakeven: floor = exit_fee + RATCHET_LOCK_FRAC x peak_excursion.
    Every historical fire must still fire (they were deep give-backs); the
    never-arm cases must still never arm; RATCHET_LOCK_FRAC=0 restores the
    old behaviour exactly.

    Pre-registered falsifier: over the first 30 fires under this rule the
    median give-back must fall below 100% of peak AND median realized must
    be positive. Either misses -> RATCHET_LOCK_FRAC=0, report FAILED.
    """

    def setUp(self):
        self.env = unittest.mock.patch.dict(
            os.environ, {"RATCHET_LOCK_FRAC": "0.5"})
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def test_a_median_shaped_trip_exits_above_breakeven_not_at_it(self):
        # The measured median shape: arm 0.20, peak 1.18x arm = 0.236.
        # Locking half the peak puts the floor at 0.118 + exit fee, so a
        # retrace to bare breakeven must NOT be where it fires.
        arm, peak, exit_fee = 0.20, 0.236, 0.01
        # at gross 0.13 (above fee + 0.118 = 0.128) it holds
        self.assertFalse(
            run_engine._breakeven_floor_hit(peak, 0.130, arm,
                                            exit_fee_usd=exit_fee),
            "held above the locked floor")
        # at gross 0.12 (below the floor) it fires — banking ~0.11 NET,
        # where the old rule banked 0.00
        self.assertTrue(
            run_engine._breakeven_floor_hit(peak, 0.120, arm,
                                            exit_fee_usd=exit_fee),
            "must fire at the locked floor, not wait for breakeven")

    def test_the_fire_banks_a_positive_net(self):
        arm, peak, exit_fee = 0.20, 0.236, 0.01
        frac = 0.5
        floor = exit_fee + frac * (peak - exit_fee)
        net_at_floor = floor - exit_fee
        self.assertGreater(net_at_floor, 0.0,
                           "the whole point: best case is no longer $0")
        self.assertTrue(
            run_engine._breakeven_floor_hit(peak, floor - 1e-9, arm,
                                            exit_fee_usd=exit_fee))

    def test_kill_switch_restores_the_breakeven_rule_exactly(self):
        arm, peak, exit_fee = 0.20, 0.236, 0.01
        with unittest.mock.patch.dict(os.environ,
                                      {"RATCHET_LOCK_FRAC": "0"}):
            # old rule: fires only at/below the exit fee
            self.assertFalse(
                run_engine._breakeven_floor_hit(peak, 0.05, arm,
                                                exit_fee_usd=exit_fee))
            self.assertTrue(
                run_engine._breakeven_floor_hit(peak, exit_fee, arm,
                                                exit_fee_usd=exit_fee))

    def test_never_armed_positions_are_untouched(self):
        # peak under the arm never arms, whatever the lock fraction says
        self.assertFalse(
            run_engine._breakeven_floor_hit(0.10, 0.09, 0.20,
                                            exit_fee_usd=0.01))

    def test_historical_deep_givebacks_still_fire(self):
        # SOL 1367: +0.160316 -> -0.067; ZEC 1392: +1.224 -> -0.534.
        # A raised floor can only make these fire EARLIER, never later.
        self.assertTrue(
            run_engine._breakeven_floor_hit(0.160316, -0.067, 0.05,
                                            exit_fee_usd=0.02))
        self.assertTrue(
            run_engine._breakeven_floor_hit(1.224, -0.534, 0.30,
                                            exit_fee_usd=0.05))

    def test_lock_never_exceeds_what_was_earned(self):
        # A pathological fraction must not put the floor above the peak —
        # that would fire instantly on every armed position.
        arm, peak, exit_fee = 0.20, 0.236, 0.01
        with unittest.mock.patch.dict(os.environ,
                                      {"RATCHET_LOCK_FRAC": "5.0"}):
            self.assertFalse(
                run_engine._breakeven_floor_hit(peak, peak, arm,
                                                exit_fee_usd=exit_fee),
                "a position sitting AT its peak must never be flattened")

    def test_baseline_still_respected_with_the_lock(self):
        # AVAX 1335 shape: run-cumulative peak inherited from a closed
        # position must still not arm the fresh one.
        self.assertFalse(
            run_engine._breakeven_floor_hit(
                0.4228002106349821, 0.11828140938999473, 0.398,
                exit_fee_usd=0.199, baseline_pnl=0.080608))


class RatchetClampTests(unittest.TestCase):
    """The `max(0.0, peak - fee_floor)` clamp is load-bearing, not cosmetic.

    The arm is priced off BREAKEVEN_FEE_RATE (0.001) while the fee floor is
    the position's REAL round trip. In a market whose true rate exceeds
    0.001 the floor can exceed the arm, so a peak may arm while still
    sitting UNDER its own round trip. Unclamped, `frac * (peak - fee_floor)`
    goes negative and drags the floor BELOW fee_floor — re-opening exactly
    the 2026-08-15 JTO 1304 defect the fee floor was added to close (a rail
    firing at a built-in loss while the label reports a banked winner).
    """

    def test_a_sub_fee_peak_never_drags_the_floor_under_the_fee_floor(self):
        arm, peak, exit_fee = 0.02, 0.025, 0.04   # high-fee market shape
        with patch.dict(os.environ, {"RATCHET_LOCK_FRAC": "0.5"}):
            # clamped floor == fee_floor (0.04); unclamped it would be
            # 0.0325, so a reading of 0.035 would wrongly hold.
            self.assertTrue(
                run_engine._breakeven_floor_hit(peak, 0.035, arm,
                                                exit_fee_usd=exit_fee),
                "floor fell below the position's own round trip")
