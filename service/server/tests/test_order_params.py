"""AI-authored order parameters and their rails (2026-07-27).

The desk already emits situation-specific order parameters and the runner
already discards them: `analysis_agents` asks for "stop" and "target", nothing
reads either, and a flat 5%/10% is applied to every instrument instead. These
tests cover the contract that stops discarding them — and, more importantly,
the rails that make trusting a model output survivable.

The rails carry two invariants:
  MONOTONE  a rail may only make an order smaller / tighter / shorter.
  R:R FLOOR target >= 2 x stop, so the 10:1 geometry that lost the
            2026-07-19..27 window cannot be expressed at all.
"""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import patch
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import order_params as op

GOOD = {"size_frac": 0.45, "leverage": 2.0, "stop_pct": 1.8, "target_pct": 4.2,
        "trail_arm_pct": 2.0, "trail_give": 0.20, "horizon_hours": 8,
        "max_adds": 0, "why": "ATR 1.1%/day; stop under the session low."}


class ModeTests(unittest.TestCase):
    def tearDown(self):
        os.environ.pop("RUN_AI_ORDER_PARAMS", None)

    def test_default_is_shadow_not_apply(self):
        """The whole migration argument rests on this: parsed and journaled,
        but changing no order until someone opts in deliberately."""
        self.assertEqual(op.mode(), "shadow")

    def test_modes_round_trip(self):
        for value in ("off", "shadow", "apply"):
            os.environ["RUN_AI_ORDER_PARAMS"] = value
            self.assertEqual(op.mode(), value)

    def test_garbage_mode_falls_back_to_shadow(self):
        os.environ["RUN_AI_ORDER_PARAMS"] = "yolo"
        self.assertEqual(op.mode(), "shadow")


class DeferAndDegradeTests(unittest.TestCase):
    """Every failure mode must degrade to the deterministic path (None),
    never to a guess."""

    def test_absent_block(self):
        self.assertIsNone(op.parse_order_block(None))

    def test_explicit_defer(self):
        self.assertIsNone(op.parse_order_block({"defer": True, "size_frac": 0.9}))

    def test_not_a_dict(self):
        for junk in ("stop at 2%", 42, [1, 2], True):
            self.assertIsNone(op.parse_order_block(junk))

    def test_unparseable_numbers_yield_nothing(self):
        self.assertIsNone(op.parse_order_block(
            {"size_frac": "abc", "leverage": None, "stop_pct": "?"}))

    def test_booleans_are_not_numbers(self):
        """JSON true would coerce to 1.0 and become a full-size order."""
        self.assertIsNone(op.parse_order_block({"size_frac": True}))

    def test_nan_and_inf_are_rejected(self):
        self.assertIsNone(op.parse_order_block(
            {"size_frac": float("nan"), "leverage": float("inf")}))

    def test_partial_block_is_usable(self):
        """A model that only has a view on the stop should not be forced to
        invent a size."""
        p = op.parse_order_block({"stop_pct": 1.5})
        self.assertIsNotNone(p)
        self.assertEqual(p.stop_pct, 1.5)
        self.assertIsNone(p.size_frac)


class MonotoneRailTests(unittest.TestCase):
    def test_hostile_oversize_is_clamped_not_honoured(self):
        p = op.parse_order_block({"size_frac": 50, "leverage": 99},
                                 leverage_cap=2.0)
        self.assertEqual(p.size_frac, 1.0)
        self.assertEqual(p.leverage, 2.0)
        self.assertEqual(len(p.notes), 2)

    def test_leverage_never_exceeds_the_run_tier(self):
        p = op.parse_order_block({"leverage": 10.0}, leverage_cap=2.0)
        self.assertEqual(p.leverage, 2.0)

    def test_leverage_below_the_cap_is_respected(self):
        """Shrinking is allowed — the rail is a ceiling, not a target."""
        p = op.parse_order_block({"leverage": 1.0}, leverage_cap=5.0)
        self.assertEqual(p.leverage, 1.0)

    def test_absurd_horizon_and_adds_are_capped(self):
        p = op.parse_order_block({"horizon_hours": 100000, "max_adds": 99})
        self.assertEqual(p.horizon_hours, 336.0)
        self.assertEqual(p.max_adds, 3)

    def test_every_clamp_is_recorded(self):
        p = op.parse_order_block({"size_frac": 9, "trail_give": 0.99})
        self.assertEqual(len(p.notes), 2)
        self.assertTrue(all("cut to cap" in n for n in p.notes))


class ExecutableSizeFloorTests(unittest.TestCase):
    """The prompt advertises size_frac 0.05 as legal, but a small max_bet puts
    0.05 under the $10 dust floor — the desk's order is then silently
    discarded (fleet 35 FIL, 2x, n=2). The caller passes the run's true
    executable minimum and the rail floors the ask up to it, journaled."""

    def test_a_sub_floor_ask_is_raised_to_the_executable_minimum(self):
        p = op.parse_order_block({"size_frac": 0.05}, min_size_frac=0.058)
        self.assertEqual(p.size_frac, 0.058)
        self.assertTrue(any("size_frac 0.05 raised to floor 0.058" in n
                            for n in p.notes), p.notes)

    def test_an_ask_above_the_minimum_is_untouched(self):
        p = op.parse_order_block({"size_frac": 0.2}, min_size_frac=0.058)
        self.assertEqual(p.size_frac, 0.2)
        self.assertEqual(p.notes, [])

    def test_the_floor_never_exceeds_the_full_bet(self):
        """A max_bet under $10 would imply min_size_frac > 1; the rail must
        clamp to the full bet, not above the 1.0 cap."""
        p = op.parse_order_block({"size_frac": 0.05}, min_size_frac=2.5)
        self.assertEqual(p.size_frac, 1.0)

    def test_no_minimum_keeps_the_static_floor(self):
        p = op.parse_order_block({"size_frac": 0.01})
        self.assertEqual(p.size_frac, 0.05)


class RRFloorTests(unittest.TestCase):
    """The single most valuable rail: it makes last week's dominant defect
    structurally impossible."""

    def test_target_is_raised_to_twice_the_stop(self):
        p = op.parse_order_block({"stop_pct": 3.0, "target_pct": 1.0})
        self.assertEqual(p.target_pct, 6.0)
        self.assertTrue(any("R:R floor" in n for n in p.notes))

    def test_the_stop_is_never_loosened_to_satisfy_the_floor(self):
        """Widening the stop would ENLARGE the loss — the monotone rule
        forbids it. Only the target may move."""
        p = op.parse_order_block({"stop_pct": 3.0, "target_pct": 1.0})
        self.assertEqual(p.stop_pct, 3.0)

    def test_compliant_bracket_is_untouched(self):
        p = op.parse_order_block({"stop_pct": 2.0, "target_pct": 5.0})
        self.assertEqual(p.target_pct, 5.0)
        self.assertEqual(p.notes, [])

    def test_target_must_also_clear_the_fee_round_trip(self):
        p = op.parse_order_block({"target_pct": 0.4}, fee_rate=0.001)
        self.assertAlmostEqual(p.target_pct, 0.6)   # 3 x 0.2% round trip
        self.assertTrue(any("fee floor" in n for n in p.notes))

    def test_lock_cannot_arm_inside_the_stop(self):
        """The 10:1 defect in miniature — arming at a fraction of the stop is
        exactly how the desk came to bank $6 wins against $67 losses."""
        p = op.parse_order_block({"stop_pct": 2.0, "trail_arm_pct": 0.2})
        self.assertEqual(p.trail_arm_pct, 2.0)

    def test_the_prod_geometry_is_now_unexpressible(self):
        """Runs 103-112: arm $6.79 against a $67.88 stop, breakeven 90.9%."""
        p = op.parse_order_block({"stop_pct": 3.0, "trail_arm_pct": 0.3,
                                  "target_pct": 0.3})
        self.assertGreaterEqual(p.trail_arm_pct, p.stop_pct)
        self.assertGreaterEqual(p.target_pct, p.stop_pct * op.RR_FLOOR)


class ExitPriceTests(unittest.TestCase):
    """Prices are derived from railed percentages by our arithmetic — an
    absolute price from the model never enters the system."""

    def test_long_bracket(self):
        p = op.parse_order_block({"stop_pct": 2.0, "target_pct": 5.0})
        sl, tp = op.exit_prices(p, 100.0, is_short=False)
        self.assertAlmostEqual(sl, 98.0)
        self.assertAlmostEqual(tp, 105.0)

    def test_short_bracket_inverts(self):
        p = op.parse_order_block({"stop_pct": 2.0, "target_pct": 5.0})
        sl, tp = op.exit_prices(p, 100.0, is_short=True)
        self.assertAlmostEqual(sl, 102.0)
        self.assertAlmostEqual(tp, 95.0)

    def test_bad_entry_yields_nothing(self):
        p = op.parse_order_block({"stop_pct": 2.0, "target_pct": 5.0})
        self.assertEqual(op.exit_prices(p, 0.0, is_short=False), (None, None))


class DeterministicPathFloorTests(unittest.TestCase):
    """rr_floor_violation guards the CODE path too — the rail is worth more
    than the AI feature it was built for."""

    def test_house_default_bracket_passes(self):
        # risk_limits 5% stop / 10% target = exactly 2.0 R:R
        self.assertIsNone(op.rr_floor_violation(95.0, 110.0, 100.0, False))

    def test_house_default_bracket_passes_at_any_entry_price(self):
        """Prod 2026-07-31: two QA opens at entry 1.0816 were refused with
        'reward 0.1082 < 2x risk 0.0541' — the 5%/10% default computes reward
        = exactly 2.0x risk, so one ulp of rounding in exit_prices decided the
        strict `<` comparison. The floor must tolerate float noise at the
        exact-equality boundary."""
        entry = 1.0816
        p = op.parse_order_block({"stop_pct": 5.0, "target_pct": 10.0})
        sl, tp = op.exit_prices(p, entry, is_short=False)
        self.assertIsNone(op.rr_floor_violation(sl, tp, entry, False))
        sl, tp = op.exit_prices(p, entry, is_short=True)
        self.assertIsNone(op.rr_floor_violation(sl, tp, entry, True))

    def test_inverted_geometry_is_refused(self):
        # 5% stop against a 2% target — risks more than it can win
        v = op.rr_floor_violation(95.0, 102.0, 100.0, False)
        self.assertIsNotNone(v)
        self.assertIn("r:r floor", v)

    def test_short_side_is_graded_correctly(self):
        self.assertIsNone(op.rr_floor_violation(105.0, 90.0, 100.0, True))
        self.assertIsNotNone(op.rr_floor_violation(105.0, 98.0, 100.0, True))

    def test_missing_bracket_is_not_graded(self):
        """A one-sided or absent bracket is not a violation — other rails own
        that case, and failing here would block every run without a target."""
        self.assertIsNone(op.rr_floor_violation(None, 110.0, 100.0, False))
        self.assertIsNone(op.rr_floor_violation(95.0, None, 100.0, False))
        self.assertIsNone(op.rr_floor_violation(0, 0, 100.0, False))

    def test_nonsensical_bracket_is_not_graded(self):
        """Stop above entry on a long is not a stop; grading it would produce
        a spurious refusal rather than a safety win."""
        self.assertIsNone(op.rr_floor_violation(105.0, 110.0, 100.0, False))


class JournalShapeTests(unittest.TestCase):
    def test_event_carries_the_reason_and_the_clamps(self):
        p = op.parse_order_block({**GOOD, "size_frac": 99})
        ev = p.as_event()
        self.assertIn("why", ev)
        self.assertIn("notes", ev)
        self.assertEqual(ev["size_frac"], 1.0)
        self.assertTrue(ev["notes"])

    def test_why_is_truncated(self):
        p = op.parse_order_block({**GOOD, "why": "x" * 5000})
        self.assertLessEqual(len(p.as_event()["why"]), 600)

    def test_clean_block_survives_intact(self):
        p = op.parse_order_block(GOOD, leverage_cap=2.0)
        self.assertEqual(p.notes, [])
        self.assertEqual(p.size_frac, 0.45)
        self.assertEqual(p.target_pct, 4.2)
        self.assertTrue(p.has_sizing())
        self.assertTrue(p.has_exits())


class TargetCeilingTests(unittest.TestCase):
    """Measured 2026-08-17 across four experiments — the target is set far
    beyond anything the market offers, and nothing bounded it.

    * H6: replaying every crypto leg from its close to the run's OWN original
      horizon, **no target above 2.00% has EVER been reached** (4 hits in 34,
      all at 0.60-2.00%). Median target: 4.80%.
    * H7: the maximum favourable excursion available inside a run's own
      horizon is median **1.14%** (p75 1.89%, max 4.24% over 29 entries). The
      market OFFERED the desk's target on **1 leg in 28**.
    * H8: replaying stop-vs-target-first over 30 entries, a 2.50% target wins
      **6 times**; 4.55% and 5.00% win **ZERO**.
    * The mechanism is live: `risk_engine` closes on `take_profit`, and
      positions carry the level — 0 of 210 stopped runs ever closed on it
      because the level is unreachable, not because the path is dead.

    `op.RR_FLOOR` only ever RAISES a target. Nothing capped it, so the desk
    overshot its own gate by ~1.8x (median 4.55% against a 2.48% requirement
    at a 1.24% stop). This ceiling pulls the level back into the range the
    market actually trades."""

    def test_an_unreachable_target_is_pulled_back_to_the_rr_ceiling(self):
        # Shipped default is 3.0x, not the 2.0x H8 measured as optimal — see
        # RR_CEILING_DEFAULT for why the gap is deliberate. 1.24 x 3.0 = 3.72.
        out = op.parse_order_block({"stop_pct": 1.24, "target_pct": 4.55})
        self.assertAlmostEqual(out.target_pct, 3.72, places=6)
        self.assertTrue(any("ceiling" in n for n in out.notes), out.notes)

    def test_a_target_inside_the_ceiling_is_untouched(self):
        out = op.parse_order_block({"stop_pct": 1.24, "target_pct": 2.40})
        self.assertAlmostEqual(out.target_pct, 2.48, places=6)  # RR floor lifts it
        out2 = op.parse_order_block({"stop_pct": 1.24, "target_pct": 3.60})
        self.assertAlmostEqual(out2.target_pct, 3.60, places=6)

    def test_the_ceiling_never_lands_below_the_fee_floor(self):
        """On a HIGH-fee market a tight stop puts ceiling x stop under the
        round-trip fee floor. The floor must win, or the ceiling would set a
        target cheaper than the cost of taking it.

        The crypto rate (0.00045) cannot exercise this: the smallest legal
        stop times the ceiling already clears that floor, so a crypto-only
        test passes whether the guard exists or not — it did, and the mutant
        survived until this case replaced it."""
        rate = 0.005                       # 0.5%/side, a high-fee venue
        fee_floor = rate * 2 * 100.0 * op.FEE_MULTIPLE      # = 3.0%
        out = op.parse_order_block({"stop_pct": 0.30, "target_pct": 9.0},
                                   fee_rate=rate)
        self.assertGreater(fee_floor, 0.30 * 3.0,
                           "test is vacuous unless the fee floor binds")
        self.assertAlmostEqual(out.target_pct, fee_floor, places=6)

    def test_the_result_still_satisfies_the_rr_floor(self):
        for stop, tgt in ((1.24, 4.55), (2.0, 9.0), (0.8, 7.0)):
            out = op.parse_order_block({"stop_pct": stop, "target_pct": tgt},
                                    fee_rate=0.00045)
            self.assertGreaterEqual(out.target_pct + 1e-9, stop * op.RR_FLOOR,
                                    f"ceiling broke the R:R floor at stop={stop}")

    def test_no_stop_means_no_ceiling(self):
        out = op.parse_order_block({"target_pct": 9.0})
        self.assertAlmostEqual(out.target_pct, 9.0, places=6)

    def test_the_ceiling_is_env_tunable(self):
        with patch.dict(os.environ, {"RR_CEILING": "2.0"}):   # H8's optimum
            out = op.parse_order_block({"stop_pct": 1.24, "target_pct": 4.55})
            self.assertAlmostEqual(out.target_pct, 2.48, places=6)

    def test_a_ceiling_below_the_floor_cannot_invert_the_bracket(self):
        with patch.dict(os.environ, {"RR_CEILING": "0.5"}):
            out = op.parse_order_block({"stop_pct": 1.24, "target_pct": 4.55})
            self.assertGreaterEqual(out.target_pct + 1e-9, 1.24 * op.RR_FLOOR)



if __name__ == "__main__":
    unittest.main()


class OutcomeClassificationTests(unittest.TestCase):
    """'absent' and 'defer' are opposite findings — one says the prompt never
    reached the model, the other says the desk looked and chose the house
    default. A single `deferred` flag made the shadow dataset unreadable."""

    def test_absent_block(self):
        self.assertEqual(op.outcome(None), "absent")

    def test_explicit_defer(self):
        self.assertEqual(op.outcome({"defer": True}), "defer")

    def test_usable_block(self):
        self.assertEqual(op.outcome(GOOD), "parsed")

    def test_non_dict_is_malformed_not_absent(self):
        self.assertEqual(op.outcome("stop at 2%"), "malformed")
        self.assertEqual(op.outcome(42), "malformed")

    def test_dict_with_nothing_usable_is_malformed(self):
        """A model emitting {"size_frac": "lots"} tried and failed — that is a
        prompt/model problem, not a deliberate deferral."""
        self.assertEqual(op.outcome({"size_frac": "lots"}), "malformed")

    def test_defer_wins_over_other_fields(self):
        self.assertEqual(op.outcome({"defer": True, "size_frac": 0.5}), "defer")


class UnitSlipTests(unittest.TestCase):
    """JTO 2026-08-15: the desk authored stop 0.05 / target 0.09 /
    trail_arm 0.06 — a coherent 5%/9%/6% bracket expressed as FRACTIONS
    (its own narrative said "~4.5% gain -> reduce half"; the same desk
    wrote correct percents on SUI 50 min earlier). Three independent
    floors silently rebuilt it 100x tighter (0.3/0.6/0.3) and the desk
    traded a noise bracket it never designed. When EVERY authored pct
    field is simultaneously below its floor, the block is a unit slip:
    reinterpret as fractions x100, journaled."""

    def test_an_all_sub_floor_bracket_is_reinterpreted_as_fractions(self):
        p = op.parse_order_block({"stop_pct": 0.05, "target_pct": 0.09,
                                  "trail_arm_pct": 0.06})
        self.assertEqual(p.stop_pct, 5.0)
        self.assertEqual(p.target_pct, 10.0)   # 9 raised to R:R floor 2x5
        self.assertEqual(p.trail_arm_pct, 6.0)
        self.assertTrue(any("unit slip" in n for n in p.notes), p.notes)

    def test_the_historical_garbage_values_convert_to_sane_percents(self):
        # SOL 0.016 -> 1.6%, BTC 0.007 -> 0.7% (both floored to 0.3 today).
        p = op.parse_order_block({"stop_pct": 0.016, "target_pct": 0.04})
        self.assertEqual(p.stop_pct, 1.6)
        self.assertEqual(p.target_pct, 4.0)

    def test_a_mixed_bracket_is_not_reinterpreted(self):
        # target above its floor -> the block is percent-denominated and
        # the tight stop is deliberate; floor it as today, no x100.
        p = op.parse_order_block({"stop_pct": 0.05, "target_pct": 1.0})
        self.assertEqual(p.stop_pct, 0.3)
        self.assertFalse(any("unit slip" in n for n in p.notes))

    def test_a_sane_bracket_is_untouched(self):
        p = op.parse_order_block({"stop_pct": 1.97, "target_pct": 3.94})
        self.assertEqual(p.stop_pct, 1.97)
        self.assertEqual(p.target_pct, 3.94)
        self.assertEqual(p.notes, [])

    def test_a_lone_sub_floor_target_without_a_stop_is_not_reinterpreted(self):
        # No stop authored: nothing anchors the units; floor as today.
        p = op.parse_order_block({"target_pct": 0.09})
        self.assertFalse(any("unit slip" in n for n in p.notes))

    def test_a_converted_bracket_is_still_railed_after_conversion(self):
        # 0.09 stop -> 9% exceeds the 8% cap: convert THEN clamp.
        p = op.parse_order_block({"stop_pct": 0.09, "target_pct": 0.2})
        self.assertEqual(p.stop_pct, 8.0)
        self.assertTrue(any("cut to cap" in n for n in p.notes))
