"""Plan 16 — margin-state oracle, health scalar, tier classifier, watch tick.

The anchor test is ``HealthGeometryTests.test_cushion_price_is_exactly_one_minus_frac``:
run_engine already ships ONE liquidation defence, the cushion stop at
``entry x (1 -+ c/L)``, and in normalised terms that is exactly
``health = 1 - c``. Pinning the new scalar to the shipped line is what stops
the two implementations drifting apart, and it would catch a sign error in
``health()`` immediately.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import liquidation  # noqa: E402


class _EnvMixin(unittest.TestCase):
    def setUp(self):
        self._saved = {}
        liquidation._samples.clear()
        liquidation._tiers.clear()

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        liquidation._samples.clear()
        liquidation._tiers.clear()

    def env(self, key, value):
        self._saved.setdefault(key, os.environ.get(key))
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


class HealthGeometryTests(_EnvMixin):
    def test_mmr_zero_reproduces_the_shipped_formula(self):
        """entry x (1 -+ 1/L) is a special case, not a parallel implementation."""
        for lev in (1.5, 2.0, 3.0, 10.0):
            self.assertAlmostEqual(
                liquidation.liquidation_price(100.0, lev, True, mmr=0.0),
                100.0 * (1 - 1 / lev), places=9)
            self.assertAlmostEqual(
                liquidation.liquidation_price(100.0, lev, False, mmr=0.0),
                100.0 * (1 + 1 / lev), places=9)

    def test_maintenance_margin_moves_the_line_closer(self):
        """The shipped model is OPTIMISTIC: real liquidation arrives earlier."""
        naive_long = liquidation.liquidation_price(100.0, 3.0, True, mmr=0.0)
        real_long = liquidation.liquidation_price(100.0, 3.0, True, mmr=0.005)
        self.assertGreater(real_long, naive_long)      # long liq rises toward mark
        naive_short = liquidation.liquidation_price(100.0, 3.0, False, mmr=0.0)
        real_short = liquidation.liquidation_price(100.0, 3.0, False, mmr=0.005)
        self.assertLess(real_short, naive_short)       # short liq falls toward mark

    def test_fully_funded_long_cannot_liquidate_but_short_can(self):
        self.assertIsNone(liquidation.liquidation_price(100.0, 1.0, True))
        self.assertAlmostEqual(
            liquidation.liquidation_price(100.0, 1.0, False, mmr=0.0), 200.0)

    def test_health_endpoints(self):
        for is_long in (True, False):
            liq = liquidation.liquidation_price(100.0, 3.0, is_long, mmr=0.0)
            self.assertAlmostEqual(
                liquidation.health(100.0, 100.0, liq, is_long), 1.0, places=9)
            self.assertAlmostEqual(
                liquidation.health(100.0, liq, liq, is_long), 0.0, places=9)

    def test_health_above_one_when_in_profit(self):
        liq_l = liquidation.liquidation_price(100.0, 3.0, True, mmr=0.0)
        self.assertGreater(liquidation.health(100.0, 110.0, liq_l, True), 1.0)
        liq_s = liquidation.liquidation_price(100.0, 3.0, False, mmr=0.0)
        self.assertGreater(liquidation.health(100.0, 90.0, liq_s, False), 1.0)

    def test_cushion_price_is_exactly_one_minus_frac(self):
        """THE anchor. c = 0.85 puts the shipped cushion at health 0.15 for
        both directions and every leverage — so today's entire liquidation
        defence is one fixed line at health 0.15."""
        for frac in (0.50, 0.85, 0.98):
            for lev in (1.5, 2.0, 3.0, 10.0):
                for is_long in (True, False):
                    cush = liquidation.cushion_price(100.0, lev, is_long,
                                                     frac=frac)
                    liq = liquidation.liquidation_price(100.0, lev, is_long,
                                                        mmr=0.0)
                    self.assertAlmostEqual(
                        liquidation.health(100.0, cush, liq, is_long),
                        1.0 - frac, places=9,
                        msg=f"frac={frac} lev={lev} long={is_long}")

    def test_liquidation_distance_is_size_invariant(self):
        """Correction 1 to the plan doc, asserted rather than asserted-in-prose:
        a partial reduce cannot move the liquidation price, so "reduce until
        healthy" is not an available action."""
        base = {"id": 1, "symbol": "X", "market": "crypto", "entry_price": 100.0,
                "current_price": 90.0, "leverage": 3.0}
        big = liquidation.margin_state({**base, "quantity": 100.0},
                                       cushion_frac=0.85)
        liquidation.forget(1)
        small = liquidation.margin_state({**base, "quantity": 1.0},
                                         cushion_frac=0.85)
        self.assertAlmostEqual(big["liq_price"], small["liq_price"], places=9)
        self.assertAlmostEqual(big["health"], small["health"], places=9)


class VelocityTests(_EnvMixin):
    def test_needs_three_samples(self):
        liquidation.record_sample("k", 1.0, now=0)
        liquidation.record_sample("k", 0.9, now=300)
        self.assertIsNone(liquidation.velocity_per_hour("k"))
        liquidation.record_sample("k", 0.8, now=600)
        self.assertIsNotNone(liquidation.velocity_per_hour("k"))

    def test_slope_is_per_hour_and_signed(self):
        """Spacing must sit inside the retention window: samples an hour apart
        are pruned by design, so a units test has to use a realistic cadence."""
        for i in range(4):                       # -0.1 health per 600s
            liquidation.record_sample("k", 1.0 - 0.1 * i, now=i * 600)
        self.assertAlmostEqual(liquidation.velocity_per_hour("k"), -0.6, places=6)

    def test_flat_series_has_zero_slope(self):
        for i in range(4):
            liquidation.record_sample("k", 0.5, now=i * 60)
        self.assertAlmostEqual(liquidation.velocity_per_hour("k"), 0.0, places=9)

    def test_ttl_none_when_not_decaying(self):
        self.assertIsNone(liquidation.time_to_liquidation_hours(0.5, 0.0))
        self.assertIsNone(liquidation.time_to_liquidation_hours(0.5, +0.2))
        self.assertAlmostEqual(
            liquidation.time_to_liquidation_hours(0.5, -0.25), 2.0, places=9)

    def test_out_of_order_timestamp_resets_the_series(self):
        """Least squares has no defence against a bad abscissa: one sample with
        a wild timestamp drags the slope to ~0 and silently suppresses the
        velocity warning at exactly the moment it matters. Found by printing a
        real series, not by a passing test."""
        liquidation.record_sample("k", 0.99, now=1.77e9)   # wall-clock reading
        for i in range(4):                                  # then a replay series
            liquidation.record_sample("k", 1.0 - 0.2 * i, now=i * 600)
        v = liquidation.velocity_per_hour("k")
        self.assertIsNotNone(v)
        self.assertAlmostEqual(v, -1.2, places=6)           # not ~0

    def test_samples_older_than_the_window_are_pruned(self):
        """A worker that pauses and resumes must not fit a line across its own
        downtime — the gap is not a price move."""
        self.env("LIQ_SAMPLE_MAX_AGE_S", "1800")
        liquidation.record_sample("k", 1.0, now=0)
        for i in range(3):
            liquidation.record_sample("k", 0.5 - 0.1 * i, now=10_000 + i * 600)
        series = liquidation._samples["k"]
        self.assertTrue(all(t >= 10_000 - 1800 for t, _ in series))
        self.assertEqual(len(series), 3)

    def test_cap_bounds_the_series(self):
        for i in range(40):
            liquidation.record_sample("k", 1.0 - 0.001 * i, now=i * 10)
        self.assertLessEqual(len(liquidation._samples["k"]),
                             liquidation._SAMPLE_CAP)

    def test_forget_drops_the_series(self):
        for i in range(4):
            liquidation.record_sample("k", 1.0 - 0.1 * i, now=i * 3600)
        liquidation.forget("k")
        self.assertIsNone(liquidation.velocity_per_hour("k"))


class TierTests(_EnvMixin):
    def test_bands_by_health(self):
        self.assertEqual(liquidation.classify_tier(0.80, None), liquidation.TIER_NOMINAL)
        self.assertEqual(liquidation.classify_tier(0.50, None), liquidation.TIER_WATCH)
        self.assertEqual(liquidation.classify_tier(0.30, None), liquidation.TIER_DEFEND)
        self.assertEqual(liquidation.classify_tier(0.10, None), liquidation.TIER_REFLEX)

    def test_velocity_escalates_past_what_health_alone_says(self):
        """health 0.80 is nominal on distance and an emergency on speed —
        the failure mode a pure threshold cannot see."""
        self.assertEqual(liquidation.classify_tier(0.80, None),
                         liquidation.TIER_NOMINAL)
        self.assertEqual(liquidation.classify_tier(0.80, 0.05),
                         liquidation.TIER_REFLEX)

    def test_unleveraged_is_nominal_not_alarming(self):
        self.assertEqual(liquidation.classify_tier(None, None),
                         liquidation.TIER_NOMINAL)

    def test_escalation_is_immediate(self):
        eff, streak = liquidation.apply_hysteresis(
            liquidation.TIER_NOMINAL, liquidation.TIER_DEFEND, 0)
        self.assertEqual(eff, liquidation.TIER_DEFEND)
        self.assertEqual(streak, 0)

    def test_deescalation_needs_consecutive_better_reads(self):
        self.env("LIQ_DEESCALATE_SAMPLES", "3")
        eff, streak = liquidation.apply_hysteresis(
            liquidation.TIER_DEFEND, liquidation.TIER_NOMINAL, 0)
        self.assertEqual(eff, liquidation.TIER_DEFEND)
        eff, streak = liquidation.apply_hysteresis(
            liquidation.TIER_DEFEND, liquidation.TIER_NOMINAL, streak)
        self.assertEqual(eff, liquidation.TIER_DEFEND)
        eff, streak = liquidation.apply_hysteresis(
            liquidation.TIER_DEFEND, liquidation.TIER_NOMINAL, streak)
        self.assertEqual(eff, liquidation.TIER_NOMINAL)

    def test_a_wick_does_not_reset_the_streak_to_a_better_tier(self):
        """One good read then one bad read must not de-escalate."""
        self.env("LIQ_DEESCALATE_SAMPLES", "3")
        eff, streak = liquidation.apply_hysteresis(
            liquidation.TIER_DEFEND, liquidation.TIER_NOMINAL, 0)
        eff, streak = liquidation.apply_hysteresis(
            eff, liquidation.TIER_DEFEND, streak)
        self.assertEqual(eff, liquidation.TIER_DEFEND)
        self.assertEqual(streak, 0)


class MarginStateTests(_EnvMixin):
    def prod_like(self, **over):
        """Prod position 71 (ETHUSDT long 3x) unless overridden."""
        row = {"id": 71, "run_id": 811, "symbol": "ETHUSDT", "market": "crypto",
               "quantity": 0.290881, "entry_price": 1897.80,
               "current_price": 1904.70, "leverage": 3.0}
        row.update(over)
        return row

    def test_prod_position_reads_healthy(self):
        st = liquidation.margin_state(self.prod_like(), cushion_frac=0.85)
        self.assertEqual(st["side"], "long")
        self.assertEqual(st["source"], "synthetic")
        self.assertEqual(st["confidence"], "modelled")
        self.assertGreater(st["health"], 0.99)
        self.assertEqual(st["tier"], liquidation.TIER_NOMINAL)

    def test_short_side_and_margin_maths(self):
        st = liquidation.margin_state(
            self.prod_like(id=73, symbol="MNQ", market="futures",
                           quantity=-0.0928, entry_price=27539.87,
                           current_price=27443.50), cushion_frac=0.85)
        self.assertEqual(st["side"], "short")
        self.assertAlmostEqual(st["notional_usd"], 0.0928 * 27443.50, places=6)
        self.assertAlmostEqual(st["margin_usd"], st["notional_usd"] / 3.0,
                               places=6)

    def test_unleveraged_long_returns_none(self):
        self.assertIsNone(liquidation.margin_state(
            self.prod_like(leverage=1.0), cushion_frac=0.85))

    def test_broker_reading_wins_and_is_labelled(self):
        st = liquidation.margin_state(
            self.prod_like(), cushion_frac=0.85,
            broker_reading={"liquidation_price": 1500.0,
                            "maintenance_margin": 0.004})
        self.assertEqual(st["source"], "broker")
        self.assertEqual(st["confidence"], "venue")
        self.assertAlmostEqual(st["liq_price"], 1500.0)

    def test_missing_mark_returns_none(self):
        self.assertIsNone(liquidation.margin_state(
            self.prod_like(current_price=None), cushion_frac=0.85))

    def test_flat_position_returns_none(self):
        self.assertIsNone(liquidation.margin_state(
            self.prod_like(quantity=0.0), cushion_frac=0.85))


class SurvivalBriefTests(_EnvMixin):
    def state(self, **over):
        st = liquidation.margin_state(
            {"id": 1, "symbol": "KAITO", "market": "crypto", "quantity": 300.0,
             "entry_price": 1.2157, "current_price": 1.0,
             "leverage": 3.0}, cushion_frac=0.85)
        st.update(over)
        return st

    def test_brief_names_the_source_as_modelled(self):
        text = liquidation.survival_brief(self.state())
        self.assertIn("MODELLED", text)
        self.assertNotIn("reported by your broker", text)

    def test_broker_source_is_named_as_such(self):
        text = liquidation.survival_brief(self.state(source="broker"))
        self.assertIn("reported by your broker", text)

    def test_brief_tells_the_desk_reducing_buys_no_distance(self):
        """Correction 1 must reach the DESK, not just the docstring: a desk
        that believes trimming buys room will trim instead of exiting."""
        text = liquidation.survival_brief(self.state())
        self.assertIn("does NOT move the liquidation price", text)
        self.assertIn("Only closing removes the risk", text)

    def test_missing_run_stop_is_called_out(self):
        text = liquidation.survival_brief(self.state(), has_run_stop=False)
        self.assertIn("no max-loss stop", text)
        text = liquidation.survival_brief(self.state(), has_run_stop=True)
        self.assertNotIn("no max-loss stop", text)

    def test_brief_is_empty_when_disabled(self):
        self.env("LIQ_DESK_BRIEF", "false")
        self.assertEqual(liquidation.survival_brief(self.state()), "")

    def test_brief_is_empty_without_a_health_reading(self):
        self.assertEqual(liquidation.survival_brief(None), "")
        self.assertEqual(liquidation.survival_brief({"health": None}), "")


class ReflexTests(_EnvMixin):
    def t3(self):
        return {"tier": liquidation.TIER_REFLEX}

    def test_reflex_is_off_by_default(self):
        self.env("LIQ_REFLEX", None)
        self.assertIsNone(liquidation.reflex_action(self.t3()))

    def test_reflex_flattens_when_enabled(self):
        self.env("LIQ_REFLEX", "true")
        self.assertEqual(liquidation.reflex_action(self.t3()), "flatten")

    def test_reflex_never_fires_above_t3(self):
        self.env("LIQ_REFLEX", "true")
        for tier in (liquidation.TIER_NOMINAL, liquidation.TIER_WATCH,
                     liquidation.TIER_DEFEND):
            self.assertIsNone(liquidation.reflex_action({"tier": tier}))


class WatchTickTests(_EnvMixin):
    def rows(self):
        return [
            # attached, healthy
            {"id": 71, "run_id": 811, "symbol": "ETHUSDT", "market": "crypto",
             "quantity": 0.29, "entry_price": 1897.80, "current_price": 1904.70,
             "leverage": 3.0},
            # ORPHAN — run_id None. _evaluate_stop never sees this one.
            {"id": 67, "run_id": None, "symbol": "SOLUSDT", "market": "crypto",
             "quantity": -9.16, "entry_price": 74.031, "current_price": 73.52,
             "leverage": 2.0},
        ]

    def test_orphans_are_measured(self):
        out = liquidation.watch_tick(cushion_frac=0.85, positions=self.rows())
        self.assertEqual(out["checked"], 2)
        self.assertEqual(out["measured"], 2)
        ids = {s["position_id"] for s in out["states"]}
        self.assertIn(67, ids)

    def test_tick_is_a_noop_when_the_oracle_is_off(self):
        self.env("LIQ_ORACLE", "false")
        out = liquidation.watch_tick(cushion_frac=0.85, positions=self.rows())
        self.assertEqual(out["checked"], 0)

    def test_closed_positions_are_forgotten(self):
        liquidation.watch_tick(cushion_frac=0.85, positions=self.rows())
        self.assertIn(67, liquidation._tiers)
        liquidation.watch_tick(cushion_frac=0.85, positions=self.rows()[:1])
        self.assertNotIn(67, liquidation._tiers)
        self.assertNotIn(67, liquidation._samples)

    def test_worst_tier_drives_the_hot_cadence(self):
        rows = self.rows()
        rows[0]["current_price"] = 1300.0        # deep toward the long's liq
        out = liquidation.watch_tick(cushion_frac=0.85, positions=rows)
        self.assertIn(out["worst"], (liquidation.TIER_DEFEND,
                                     liquidation.TIER_REFLEX))

    def test_escalation_is_counted(self):
        rows = self.rows()
        liquidation.watch_tick(cushion_frac=0.85, positions=rows)
        rows[0]["current_price"] = 1300.0
        out = liquidation.watch_tick(cushion_frac=0.85, positions=rows)
        self.assertGreaterEqual(out["escalations"], 1)


class DeskSeesMarginStateTests(_EnvMixin):
    """The brief must reach BOTH decision paths.

    It is hung off run_engine._position_state_line rather than written into
    each prompt because both paths already route through that one function —
    _light_analysis at the cheap tier and run_analysis(position_state=...) at
    the full tier. #124 shipped the light path alone and #125 had to retrofit
    the other; one insertion point makes that impossible to repeat.
    """

    def _line(self, leverage=3.0, stop_conditions="{}"):
        from unittest.mock import patch
        import run_engine
        run = {"id": 811, "agent_id": 6, "symbol": "ETHUSDT",
               "market": "crypto", "stop_conditions_json": stop_conditions,
               "peak_pnl_usd": 33.44}
        pnl = {"mark_age_ok": True, "unrealized": -15.0,
               "position": {"quantity": 1.1446, "entry_price": 1908.90,
                            "current_price": 1895.80, "leverage": leverage}}
        with patch.object(run_engine, "compute_run_pnl", return_value=pnl):
            return run_engine._position_state_line(run, {}, 1.1446, {})

    def test_leveraged_position_gets_a_margin_brief(self):
        text = self._line(leverage=3.0)
        self.assertIn("MARGIN STATE", text)
        self.assertIn("Liquidation at", text)
        self.assertIn("Health", text)

    def test_fully_funded_long_gets_no_margin_brief(self):
        """Nothing to say — an unleveraged long cannot be wiped."""
        text = self._line(leverage=1.0)
        self.assertNotIn("MARGIN STATE", text)
        self.assertIn("Banking is a first-class action", text)

    def test_a_run_with_no_max_loss_stop_is_called_out(self):
        """Prod runs 821-825 shipped with stop_conditions_json == {} on 2x-3x
        leverage, so the desk's own exit was the only bound in existence."""
        self.assertIn("no max-loss stop", self._line(stop_conditions="{}"))
        self.assertNotIn("no max-loss stop",
                         self._line(stop_conditions='{"max_loss_usd": 97.11}'))

    def test_exit_awareness_kill_switch_does_not_blind_the_margin_brief(self):
        """Separate concerns, separate flags. Switching off the exit brief must
        not also hide the position's liquidation distance."""
        self.env("RUN_DESK_EXIT_AWARENESS", "false")
        text = self._line(leverage=3.0)
        self.assertIn("MARGIN STATE", text)
        self.assertNotIn("Banking is a first-class action", text)

    def test_margin_kill_switch_leaves_the_exit_brief_intact(self):
        self.env("LIQ_DESK_BRIEF", "false")
        text = self._line(leverage=3.0)
        self.assertNotIn("MARGIN STATE", text)
        self.assertIn("Banking is a first-class action", text)

    def test_flat_book_says_nothing_at_all(self):
        from unittest.mock import patch
        import run_engine
        with patch.object(run_engine, "compute_run_pnl", return_value={}):
            self.assertEqual(
                run_engine._position_state_line(
                    {"id": 1, "market": "crypto",
                     "stop_conditions_json": "{}"}, {}, 0.0, {}), "")

    def test_a_broken_oracle_never_breaks_a_decision(self):
        """A brief is an enhancement; it must never be able to stop the desk
        from deciding. Prod evidence for the shape: a NaN in one JSON column
        500'd every read of a table for a week."""
        from unittest.mock import patch
        import run_engine
        with patch.object(run_engine, "_liq_cushion_frac",
                          side_effect=RuntimeError("boom")):
            text = self._line(leverage=3.0)
        self.assertNotIn("MARGIN STATE", text)
        self.assertIn("Banking is a first-class action", text)


if __name__ == "__main__":
    unittest.main()
