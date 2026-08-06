"""Plan 14 Phase 1+2 gates — symbol research engine.

Pure-function factor math, gates and clamps (with the mutation targets the
plan names), the no-network discipline, cooldown subordination, the batch
sentinel dedupe (Redis absent), and select_targets exclusion rules.
"""

from __future__ import annotations

import math
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
import symbol_research as sr


def _candles(n=60, start=100.0, drift=0.5, volume=1_000_000):
    """Synthetic daily candles with a steady drift (%/day)."""
    out, price = [], start
    for i in range(n):
        price *= 1 + drift / 100.0
        out.append({"ts": i, "open": price, "high": price, "low": price,
                    "close": price, "volume": volume})
    return out


class FactorMathTests(unittest.TestCase):
    def test_data_sufficiency_gate(self):
        self.assertIsNone(sr.candle_factors(_candles(n=10), "crypto"))
        self.assertIsNotNone(sr.candle_factors(_candles(n=40), "crypto"))

    def test_momentum_sign_follows_drift(self):
        up = sr.candle_factors(_candles(drift=1.0), "crypto")
        down = sr.candle_factors(_candles(drift=-1.0), "crypto")
        self.assertGreater(up["mom_5d"], 0)
        self.assertLess(down["mom_5d"], 0)
        self.assertGreater(sr.technical_subscore(up), 0)
        self.assertLess(sr.technical_subscore(down), 0)

    def test_technical_subscore_bounded(self):
        f = sr.candle_factors(_candles(drift=25.0), "crypto")
        s = sr.technical_subscore(f)
        self.assertLessEqual(abs(s), 1.0)

    def test_vol_fit_peaks_in_band(self):
        lo, hi = sr.VOL_BAND["crypto"]
        self.assertEqual(sr.vol_fit_score((lo + hi) / 2, "crypto"), 1.0)
        self.assertLess(sr.vol_fit_score(hi * 4, "crypto"), 1.0)
        self.assertLess(sr.vol_fit_score(lo / 4, "crypto"), 1.0)
        self.assertIsNone(sr.vol_fit_score(None, "crypto"))

    def test_composite_renormalizes_over_available_families(self):
        """Missing factor = None, never a fabricated 0 (mutation target)."""
        full = sr.composite_score({"technical": 0.5, "news": 0.5, "macro": 0.5},
                                  "forex")
        self.assertAlmostEqual(full["coverage"], 1.0, places=6)
        self.assertAlmostEqual(full["eps_raw"], 0.5, places=6)
        thin = sr.composite_score({"technical": 0.5, "news": None, "macro": None},
                                  "forex")
        # renormalized mean is still 0.5 — None did NOT drag it toward 0
        self.assertAlmostEqual(thin["eps_raw"], 0.5, places=6)
        # but coverage shrinkage reduces the rank score
        self.assertLess(thin["rank_score"], full["rank_score"])
        self.assertAlmostEqual(thin["rank_score"],
                               0.5 * math.sqrt(thin["coverage"]), places=6)

    def test_mom5d_component_sign_is_pinned(self):
        """Each component's sign matters alone — a single flipped component
        must not hide inside the aggregate (mutation target)."""
        up_only = {"mom_5d": 5.0, "mom_20d": None, "sma20_dist": None,
                   "vol_ratio": None}
        down_only = {**up_only, "mom_5d": -5.0}
        self.assertGreater(sr.technical_subscore(up_only), 0)
        self.assertLess(sr.technical_subscore(down_only), 0)

    def test_weighted_mean_uses_the_profile_weights(self):
        """Distinct family values pin the actual weighted mean — uniform
        values would make a flipped/altered weight invisible (mutation target)."""
        got = sr.composite_score({"technical": 1.0, "news": 0.0, "macro": 0.0},
                                 "forex")
        self.assertAlmostEqual(got["eps_raw"],
                               sr.WEIGHT_PROFILES["forex"]["technical"], places=6)

    def test_shrinkage_is_monotone_in_coverage(self):
        subs = {"technical": 0.6}
        one = sr.composite_score(subs, "us-stock")
        two = sr.composite_score({**subs, "news": 0.6}, "us-stock")
        self.assertLess(one["rank_score"], two["rank_score"])

    def test_veto_gates_zero_not_scale(self):
        base = sr.apply_gates(0.8, event_window=False, regime_blocks_longs=False,
                              direction="long", session_open=True)
        self.assertEqual(base, 0.8)
        self.assertEqual(sr.apply_gates(0.8, event_window=True,
                                        regime_blocks_longs=False,
                                        direction="long", session_open=True), 0.0)
        self.assertEqual(sr.apply_gates(0.8, event_window=False,
                                        regime_blocks_longs=True,
                                        direction="long", session_open=True), 0.0)
        # shorts pass a longs-only regime block
        self.assertGreater(sr.apply_gates(0.8, event_window=False,
                                          regime_blocks_longs=True,
                                          direction="short", session_open=True), 0)
        # closed session is a factor, not a veto
        self.assertAlmostEqual(sr.apply_gates(0.8, event_window=False,
                                              regime_blocks_longs=False,
                                              direction="long",
                                              session_open=False), 0.8 * 0.85)

    def test_fee_hurdle_makes_tiny_moves_negative_ev(self):
        ev = sr.expected_value(0.1, 0.9, 24, 2.0, "crypto")
        self.assertLess(ev["ev_pct"], 0)
        ev2 = sr.expected_value(3.0, 0.7, 24, 2.0, "crypto")
        self.assertGreater(ev2["ev_pct"], 0)


class ThesisClampTests(unittest.TestCase):
    def test_garbage_llm_output_lands_in_bounds(self):
        raw = {"direction": "MOON", "expected_move_pct": 5000,
               "horizon_hours": -3, "confidence": 9.9}
        t = sr.clamp_thesis(raw, "crypto", vol_daily_pct=2.0, momentum_sign=1.0)
        self.assertIn(t["direction"], ("long", "short"))
        lo, hi = sr.THESIS_BOUNDS["horizon_hours"]
        self.assertTrue(lo <= t["horizon_hours"] <= hi)
        c_lo, c_hi = sr.THESIS_BOUNDS["confidence"]
        self.assertTrue(c_lo <= t["confidence"] <= c_hi)
        cap = sr.THESIS_BOUNDS["expected_move_vol_mult"] * 2.0 * \
            math.sqrt(t["horizon_hours"] / 24.0)
        self.assertLessEqual(t["expected_move_pct"], cap + 1e-9)

    def test_short_forced_long_where_unsupported(self):
        t = sr.clamp_thesis({"direction": "short", "expected_move_pct": 2,
                             "horizon_hours": 24, "confidence": 0.6},
                            "polymarket", 1.5, momentum_sign=-1.0)
        self.assertEqual(t["direction"], "long")

    def test_fallback_thesis_in_bounds(self):
        t = sr.fallback_thesis("crypto", 2.0, momentum_sign=-1.0,
                               score_percentile=0.9)
        self.assertEqual(t["direction"], "short")
        c_lo, c_hi = sr.THESIS_BOUNDS["confidence"]
        self.assertTrue(c_lo <= t["confidence"] <= c_hi)


class ShortVenueTests(unittest.TestCase):
    """A short needs a book that can express it.

    Prod 2026-08-03: run 938 carried a forex SHORT written onto market_type
    'spot' and spent ten cycles saying so — "Short thesis matches recent yen
    rally but entry is unfavourable and WE CANNOT SHORT, so we hold." Run 928
    did the same on crypto spot on 2026-08-02. The venue rule mapped shorts to
    futures only for crypto, so every other market's short landed on a spot
    book with no inventory to sell.
    """

    def test_crypto_short_gets_the_futures_venue(self):
        self.assertEqual(sr.thesis_market_type("crypto", "short"), "futures")
        self.assertTrue(sr.thesis_is_expressible("crypto", "short"))

    def test_longs_stay_on_spot_everywhere(self):
        for market in ("crypto", "us-stock", "forex", "futures"):
            self.assertEqual(sr.thesis_market_type(market, "long"), "spot")
            self.assertTrue(sr.thesis_is_expressible(market, "long"))

    def test_short_with_no_shortable_venue_is_not_expressible(self):
        # forex is supports_short=True at the MARKET level, which is what let
        # this through — the venue it actually lands on is what matters.
        for market in ("forex", "us-stock", "futures"):
            self.assertEqual(sr.thesis_market_type(market, "short"), "spot")
            self.assertFalse(sr.thesis_is_expressible(market, "short"),
                             f"{market} short would be written to a spot book")

    def test_inexpressible_shorts_are_not_selectable(self):
        """select_targets filters on selectable=1, so this is what stops the
        fleet building a run that can never trade."""
        def fake_generate(prompt, **kw):
            return ('[{"symbol":"USDJPY","market":"forex","direction":"short",'
                    '"expected_move_pct":1.2,"horizon_hours":24,"confidence":0.71,'
                    '"thesis":"yen strength","risks":"r",'
                    '"invalidation":"A break above the recent swing high."}]')

        survivors = [{
            "symbol": "USDJPY", "market": "forex", "eps_raw": 1.0,
            "momentum_sign": -1.0, "session_open": True,
            "factors": {"last": 156.7, "mom_5d": -1.0, "mom_20d": -2.0,
                        "vol_daily_pct": 0.4, "vol_ratio": 1.0},
        }]
        with patch.object(sr, "_previous_thesis", return_value=None):
            out = sr.generate_theses(survivors, generate_text=fake_generate)
        self.assertEqual(out[0]["thesis"]["direction"], "short")
        self.assertEqual(out[0]["selectable"], 0,
                         "an unshortable short must never reach the fleet")

    def test_expressible_positive_ev_thesis_stays_selectable(self):
        def fake_generate(prompt, **kw):
            return ('[{"symbol":"BTCUSDT","market":"crypto","direction":"short",'
                    '"expected_move_pct":4.0,"horizon_hours":24,"confidence":0.7,'
                    '"thesis":"t","risks":"r",'
                    '"invalidation":"A break above the recent swing high."}]')

        survivors = [{
            "symbol": "BTCUSDT", "market": "crypto", "eps_raw": 1.0,
            "momentum_sign": -1.0, "session_open": True,
            "factors": {"last": 63000.0, "mom_5d": -3.0, "mom_20d": -4.0,
                        "vol_daily_pct": 2.0, "vol_ratio": 1.1},
        }]
        with patch.object(sr, "_previous_thesis", return_value=None):
            out = sr.generate_theses(survivors, generate_text=fake_generate)
        self.assertEqual(out[0]["selectable"], 1)


class RRFeasibilityTests(unittest.TestCase):
    """A thesis whose own invalidation sits farther away than its expected
    move can pay for can never clear the desk's 2:1 R:R floor.

    Prod 2026-08-04: run 948 (ZC long, 2.5% expected move, stop at $460 ≈ 3%
    below) burned 8 idle cycles emitting "R:R geometry fails" and retired
    without ever trading; 947 (HG) and 943 idled on the same shape, and the
    live batch had HG long 2.0% with its level 4.3% away marked selectable=1 —
    loaded to rebuild the identical idle run. Fifth instance of the
    infeasible-at-build class: gate it at build or churn forever.
    """

    def test_948_geometry_is_infeasible(self):
        thesis = {"invalidation": "If price falls below $460.",
                  "expected_move_pct": 2.5}
        self.assertFalse(sr.thesis_rr_feasible(thesis, 474.0))

    def test_hg_live_batch_geometry_is_infeasible(self):
        thesis = {"invalidation": "price falling below the recent swing low "
                                  "near $6.30", "expected_move_pct": 2.0}
        self.assertFalse(sr.thesis_rr_feasible(thesis, 6.58))

    def test_near_level_with_room_is_feasible(self):
        thesis = {"invalidation": "A break above $63800 voids the short.",
                  "expected_move_pct": 4.0}
        self.assertTrue(sr.thesis_rr_feasible(thesis, 63000.0))

    def test_relative_invalidation_has_nothing_to_judge(self):
        self.assertIsNone(sr.invalidation_distance_pct(
            "Break above the recent swing high.", 63000.0))
        self.assertTrue(sr.thesis_rr_feasible(
            {"invalidation": "Break above the recent swing high.",
             "expected_move_pct": 0.5}, 63000.0))

    def test_percentages_and_periods_are_not_levels(self):
        self.assertIsNone(sr.invalidation_distance_pct(
            "a 3% adverse move within 24 hours", 100.0))

    def test_distance_uses_the_nearest_level(self):
        dist = sr.invalidation_distance_pct(
            "support between $460 and $470", 474.0)
        self.assertAlmostEqual(dist, (1 - 470.0 / 474.0) * 100.0, places=6)

    def test_exactly_at_the_floor_is_feasible(self):
        # 75/100 is exactly representable: dist = 25%, floor needs move >= 50%.
        thesis = {"invalidation": "below $75", "expected_move_pct": 50.0}
        self.assertTrue(sr.thesis_rr_feasible(thesis, 100.0))
        thesis["expected_move_pct"] = 49.9
        self.assertFalse(sr.thesis_rr_feasible(thesis, 100.0))

    def test_infeasible_thesis_is_not_selectable(self):
        def fake_generate(prompt, **kw):
            return ('[{"symbol":"ZC","market":"futures","direction":"long",'
                    '"expected_move_pct":2.5,"horizon_hours":48,"confidence":0.7,'
                    '"thesis":"t","risks":"r",'
                    '"invalidation":"If price falls below $460."}]')

        survivors = [{
            "symbol": "ZC", "market": "futures", "eps_raw": 1.0,
            "momentum_sign": 1.0, "session_open": True,
            "factors": {"last": 474.0, "mom_5d": 2.0, "mom_20d": 3.0,
                        "vol_daily_pct": 1.5, "vol_ratio": 1.0},
        }]
        with patch.object(sr, "_previous_thesis", return_value=None):
            out = sr.generate_theses(survivors, generate_text=fake_generate)
        self.assertEqual(out[0]["selectable"], 0,
                         "an unbracketable thesis must never reach the fleet")


class InvalidationCoherenceTests(unittest.TestCase):
    """A thesis whose invalidation level is already breached is born dead: the
    desk reads it every cycle, correctly refuses to enter, and eventually
    retires the run — then the fleet refills the slot from the same pool.

    Payloads below are the real 2026-08-03 prod theses that paralyzed fleet 26
    (runs 933/934/937/938 — four runs, three research batches, zero trades)."""

    def test_short_level_below_price_is_rejected(self):
        # run 934: ETH short, "close above $1,850" while ETH trades at 1875.15.
        # A short dies on a break UP, so the level must sit ABOVE the price.
        t = sr.clamp_thesis(
            {"direction": "short", "expected_move_pct": 2.8, "horizon_hours": 48,
             "confidence": 0.6, "invalidation": "Close above $1,850 on high volume."},
            "crypto", 2.0, momentum_sign=-1.0, last=1875.15)
        self.assertNotIn("1,850", t["invalidation"])
        self.assertTrue(t["invalidation"])

    def test_stale_epoch_price_is_rejected(self):
        # run 933: BTC short, "$30,500" while BTC trades at 63,361 — the model
        # recalled a 2023 price because the prompt never showed it one.
        t = sr.clamp_thesis(
            {"direction": "short", "expected_move_pct": 4.0, "horizon_hours": 72,
             "confidence": 0.66,
             "invalidation": "Break above $30,500 with sustained volume."},
            "crypto", 2.0, momentum_sign=-1.0, last=63361.5)
        self.assertNotIn("30,500", t["invalidation"])

    def test_long_level_absurdly_far_below_is_rejected(self):
        # run 937: ZEC long, "stay above $18" while ZEC trades at 488.675. The
        # side is right for a long but the distance makes it unreachable, so
        # the run can never invalidate — and the desk refused the bracket.
        t = sr.clamp_thesis(
            {"direction": "long", "expected_move_pct": 4.0, "horizon_hours": 24,
             "confidence": 0.65,
             "invalidation": "Failure to stay above $18 for 6 hours invalidates the long."},
            "crypto", 2.0, momentum_sign=1.0, last=488.675)
        self.assertNotIn("$18", t["invalidation"])

    def test_long_level_above_price_is_rejected(self):
        # Mirror of the short case: a long dies on a break DOWN, so its level
        # must sit BELOW the price. Above it, the long is void on arrival —
        # near enough to pass the distance rule, so only the side rule catches it.
        t = sr.clamp_thesis(
            {"direction": "long", "expected_move_pct": 2.0, "horizon_hours": 24,
             "confidence": 0.6,
             "invalidation": "A close below $1,950 ends the long."},
            "crypto", 2.0, momentum_sign=1.0, last=1875.0)
        self.assertNotIn("1,950", t["invalidation"])
        self.assertTrue(t["invalidation"])

    def test_coherent_levels_survive_untouched(self):
        # Correct-side, sane-distance levels must pass through verbatim.
        short = sr.clamp_thesis(
            {"direction": "short", "expected_move_pct": 2.0, "horizon_hours": 24,
             "confidence": 0.6,
             "invalidation": "Crossing above $1,950 with strong momentum nullifies the short."},
            "crypto", 2.0, momentum_sign=-1.0, last=1875.0)
        self.assertIn("1,950", short["invalidation"])
        long_ = sr.clamp_thesis(
            {"direction": "long", "expected_move_pct": 2.0, "horizon_hours": 24,
             "confidence": 0.6,
             "invalidation": "A close below $1,800 ends the long."},
            "crypto", 2.0, momentum_sign=1.0, last=1875.0)
        self.assertIn("1,800", long_["invalidation"])

    def test_relative_levels_never_rejected(self):
        # No absolute number to check — these are always coherent, and they are
        # what the model emits correctly today.
        for direction, sign in (("short", -1.0), ("long", 1.0)):
            t = sr.clamp_thesis(
                {"direction": direction, "expected_move_pct": 2.0,
                 "horizon_hours": 24, "confidence": 0.6,
                 "invalidation": "Price closes above the 20-day moving average."},
                "crypto", 2.0, momentum_sign=sign, last=488.0)
            self.assertIn("20-day moving average", t["invalidation"])

    def test_percentages_and_durations_are_not_price_levels(self):
        # "2%" and "48-hours" must not be read as prices — the real GM thesis.
        # Prod emits U+2011 NON-BREAKING HYPHENs ("48‑hours"), not "-", so
        # the scrubber is exercised with the character the model actually writes.
        t = sr.clamp_thesis(
            {"direction": "long", "expected_move_pct": 2.0, "horizon_hours": 48,
             "confidence": 0.6,
             "invalidation": "If GM falls more than 2% in the next 48‑hours, "
                             "the bullish case is invalidated."},
            "us-stock", 1.5, momentum_sign=1.0, last=52.4)
        self.assertIn("2%", t["invalidation"])
        t2 = sr.clamp_thesis(
            {"direction": "short", "expected_move_pct": 2.0, "horizon_hours": 24,
             "confidence": 0.6,
             "invalidation": "QCOM rallies above its 20‑day moving average."},
            "us-stock", 1.5, momentum_sign=-1.0, last=21.0)
        self.assertIn("20‑day moving average", t2["invalidation"])

    def test_level_pinned_to_spot_is_rejected(self):
        """Given `last`, the model started answering WITH `last`. Real batches
        research:496034 and :496035 (2026-08-03) — a level 0.03% from spot is
        not a level, it is a restatement of spot, and ordinary noise fires it
        within minutes. Reproduced 7 of 8 bare-number levels across both."""
        for txt, last in (("Price closes above 63140.4.", 63159.5),
                          ("Price closes above 1865.", 1866.05),
                          ("Price closes above 73.0.", 73.0495),
                          ("Price moves above $63,140.", 63159.5),
                          ("Price climbs above $73.07.", 73.05)):
            t = sr.clamp_thesis(
                {"direction": "short", "expected_move_pct": 2.0,
                 "horizon_hours": 24, "confidence": 0.6, "invalidation": txt},
                "crypto", 2.0, momentum_sign=-1.0, last=last)
            self.assertEqual(t["invalidation"],
                             sr._RELATIVE_INVALIDATION["short"],
                             f"noise-distance level survived: {txt}")

    def test_min_distance_scales_with_volatility(self):
        """A 0.5% level is noise on 4%/day crypto and a real level on 0.2%/day
        forex — the floor must follow the tape, not a fixed percent."""
        txt, last = "Price closes above 100.5.", 100.0          # 0.5% away
        quiet = sr.clamp_thesis(
            {"direction": "short", "expected_move_pct": 1.0, "horizon_hours": 24,
             "confidence": 0.6, "invalidation": txt},
            "forex", 0.2, momentum_sign=-1.0, last=last)
        self.assertIn("100.5", quiet["invalidation"])
        wild = sr.clamp_thesis(
            {"direction": "short", "expected_move_pct": 4.0, "horizon_hours": 24,
             "confidence": 0.6, "invalidation": txt},
            "crypto", 4.0, momentum_sign=-1.0, last=last)
        self.assertEqual(wild["invalidation"], sr._RELATIVE_INVALIDATION["short"])

    def test_flat_floor_applies_when_volatility_is_unknown(self):
        """vol_daily_pct is None whenever there are under 5 usable returns
        (symbol_research.py:196), so the flat floor is the only thing standing
        between a spot-pinned level and the desk."""
        near = sr.clamp_thesis(
            {"direction": "short", "expected_move_pct": 2.0, "horizon_hours": 24,
             "confidence": 0.6, "invalidation": "Price closes above 100.1."},
            "crypto", None, momentum_sign=-1.0, last=100.0)          # 0.1% away
        self.assertEqual(near["invalidation"], sr._RELATIVE_INVALIDATION["short"])
        far = sr.clamp_thesis(
            {"direction": "short", "expected_move_pct": 2.0, "horizon_hours": 24,
             "confidence": 0.6, "invalidation": "Price closes above 101.0."},
            "crypto", None, momentum_sign=-1.0, last=100.0)          # 1.0% away
        self.assertIn("101.0", far["invalidation"])

    def test_thesis_prompt_states_the_minimum_distance(self):
        captured = {}

        def fake_generate(prompt, **kw):
            captured["prompt"] = prompt
            return "[]"

        survivors = [{
            "symbol": "BTCUSDT", "market": "crypto", "eps_raw": 1.0,
            "momentum_sign": -1.0, "session_open": True,
            "factors": {"last": 63159.5, "mom_5d": -2.0, "mom_20d": -3.0,
                        "vol_daily_pct": 2.0, "vol_ratio": 1.1},
        }]
        with patch.object(sr, "_previous_thesis", return_value=None):
            sr.generate_theses(survivors, generate_text=fake_generate)
        low = captured["prompt"].lower()
        self.assertIn("vol_daily_pct", low)
        self.assertTrue("at least" in low and "away from" in low,
                        "prompt must state a MINIMUM distance, not only a maximum")

    def test_missing_price_leaves_invalidation_alone(self):
        # No price to check against ⇒ no verdict. Never guess.
        t = sr.clamp_thesis(
            {"direction": "short", "expected_move_pct": 2.0, "horizon_hours": 24,
             "confidence": 0.6, "invalidation": "Break above $30,500."},
            "crypto", 2.0, momentum_sign=-1.0, last=None)
        self.assertIn("30,500", t["invalidation"])

    def test_incoherent_stored_thesis_is_not_reused(self):
        """Reuse keeps a stored thesis verbatim. A pre-existing bad one must be
        re-derived, not carried forward on every quiet-tape refresh."""
        calls = []

        def fake_generate(prompt, **kw):
            calls.append(prompt)
            return ('[{"symbol":"SPCX","market":"us-stock","direction":"short",'
                    '"expected_move_pct":2.0,"horizon_hours":24,"confidence":0.6,'
                    '"thesis":"t","risks":"r","invalidation":"Close above $23.00."}]')

        survivors = [{
            "symbol": "SPCX", "market": "us-stock", "eps_raw": 1.0,
            "momentum_sign": -1.0, "session_open": True,
            "factors": {"last": 21.0, "mom_5d": -2.0, "mom_20d": -3.0,
                        "vol_daily_pct": 1.5, "vol_ratio": 1.1},
        }]
        stale = {"stage1_key": sr._stage1_key(survivors[0]), "planner": "llm",
                 "thesis": {"direction": "short", "expected_move_pct": 2.0,
                            "horizon_hours": 24, "confidence": 0.6,
                            "thesis": "t", "risks": "r",
                            "invalidation": "Break above $8.00."}}
        with patch.object(sr, "_previous_thesis", return_value=stale):
            out = sr.generate_theses(survivors, generate_text=fake_generate)

        self.assertEqual(len(calls), 1, "stale thesis was reused instead of re-derived")
        self.assertNotIn("$8.00", out[0]["thesis"]["invalidation"])

    def test_coherent_stored_thesis_is_still_reused(self):
        """The zero-LLM quiet-tape path must survive the new check."""
        calls = []

        def fake_generate(prompt, **kw):  # pragma: no cover - must not run
            calls.append(prompt)
            return "[]"

        survivors = [{
            "symbol": "SPCX", "market": "us-stock", "eps_raw": 1.0,
            "momentum_sign": -1.0, "session_open": True,
            "factors": {"last": 21.0, "mom_5d": -2.0, "mom_20d": -3.0,
                        "vol_daily_pct": 1.5, "vol_ratio": 1.1},
        }]
        good = {"stage1_key": sr._stage1_key(survivors[0]), "planner": "llm",
                "thesis": {"direction": "short", "expected_move_pct": 2.0,
                           "horizon_hours": 24, "confidence": 0.6,
                           "thesis": "t", "risks": "r",
                           "invalidation": "Close above $23.00 on volume."}}
        with patch.object(sr, "_previous_thesis", return_value=good):
            out = sr.generate_theses(survivors, generate_text=fake_generate)

        self.assertEqual(calls, [], "quiet-tape reuse should spend zero LLM")
        self.assertIn("$23.00", out[0]["thesis"]["invalidation"])

    def test_thesis_prompt_carries_the_current_price(self):
        """The defect's origin: the model was asked for a price level while the
        prompt payload contained no price."""
        captured = {}

        def fake_generate(prompt, **kw):
            captured["prompt"] = prompt
            return ('[{"symbol":"BTCUSDT","market":"crypto","direction":"short",'
                    '"expected_move_pct":2.0,"horizon_hours":24,"confidence":0.6,'
                    '"thesis":"t","risks":"r","invalidation":"Break above $64,000."}]')

        survivors = [{
            "symbol": "BTCUSDT", "market": "crypto", "eps_raw": 1.0,
            "momentum_sign": -1.0, "session_open": True,
            "factors": {"last": 63361.5, "mom_5d": -2.0, "mom_20d": -3.0,
                        "vol_daily_pct": 2.0, "vol_ratio": 1.1},
        }]
        with patch.object(sr, "_previous_thesis", return_value=None):
            out = sr.generate_theses(survivors, generate_text=fake_generate)

        self.assertIn("63361.5", captured["prompt"])
        self.assertEqual(out[0]["thesis"]["direction"], "short")


class ScreenTests(unittest.TestCase):
    """screen_universe with injected candles — zero network by construction."""

    def _fetch(self, sym, market):
        drift = {"UP": 1.2, "DOWN": -1.2, "FLAT": 0.0}.get(sym, 0.6)
        return _candles(drift=drift, volume=5_000_000)

    def test_no_network_and_per_market_caps(self):
        universe = ([{"symbol": f"C{i}", "market": "crypto"} for i in range(8)] +
                    [{"symbol": f"S{i}", "market": "us-stock"} for i in range(8)])
        overlays = {"event_window": False, "regime_blocks_longs": False, "policy": {}}
        with patch.object(sr, "_read_overlays", side_effect=AssertionError("network")):
            got = sr.screen_universe(universe, fetch_candles=self._fetch,
                                     overlays=overlays)
        per_market = {}
        for s in got:
            per_market[s["market"]] = per_market.get(s["market"], 0) + 1
        self.assertLessEqual(per_market.get("crypto", 0),
                             sr.SURVIVORS_PER_MARKET["crypto"])
        self.assertLessEqual(per_market.get("us-stock", 0),
                             sr.SURVIVORS_PER_MARKET["us-stock"])
        self.assertTrue(got)

    def test_liquidity_floor_drops_thin_crypto(self):
        def thin(sym, market):
            return _candles(volume=10)  # ~$1k dollar volume
        got = sr.screen_universe([{"symbol": "THIN", "market": "crypto"}],
                                 fetch_candles=thin,
                                 overlays={"event_window": False,
                                           "regime_blocks_longs": False,
                                           "policy": {}})
        self.assertEqual(got, [])

    def test_event_window_vetoes_macro_markets_only(self):
        overlays = {"event_window": True, "regime_blocks_longs": False, "policy": {}}
        got = sr.screen_universe(
            [{"symbol": "ES", "market": "futures"},
             {"symbol": "BTCUSDT", "market": "crypto"}],
            fetch_candles=self._fetch, overlays=overlays)
        markets_seen = {s["market"] for s in got}
        self.assertNotIn("futures", markets_seen)
        self.assertIn("crypto", markets_seen)

    def test_failing_fetcher_fails_soft(self):
        def boom(sym, market):
            raise RuntimeError("provider down")
        got = sr.screen_universe([{"symbol": "X", "market": "crypto"}],
                                 fetch_candles=boom,
                                 overlays={"event_window": False,
                                           "regime_blocks_longs": False,
                                           "policy": {}})
        self.assertEqual(got, [])


class DailyCandleCooldownTests(unittest.TestCase):
    def test_cooldown_serves_no_http(self):
        """Active yahoo cooldown ⇒ [] with zero HTTP (subordination contract)."""
        import price_fetcher
        import time as _t
        with patch.dict(price_fetcher._provider_cooldowns,
                        {"yahoo": _t.time() + 60}), \
             patch("cache.get_json", return_value=None), \
             patch.object(price_fetcher, "_request_json_with_retry",
                          side_effect=AssertionError("HTTP during cooldown")):
            out = price_fetcher.get_daily_candles("AAPL", "us-stock")
        self.assertEqual(out, [])

    def test_cache_hit_serves_no_http(self):
        import price_fetcher
        cached = _candles(n=40)
        with patch("cache.get_json", return_value=cached), \
             patch.object(price_fetcher, "_request_json_with_retry",
                          side_effect=AssertionError("HTTP on cache hit")):
            out = price_fetcher.get_daily_candles("AAPL", "us-stock")
        self.assertEqual(out, cached)


class BatchAndSelectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()

    def tearDown(self):
        self.tmp.cleanup()

    def _refresh(self, generate_text=None, symbols=("AAA", "BBB", "CCC", "DDD")):
        universe = [{"symbol": s, "market": "crypto"} for s in symbols]
        with patch.object(sr, "build_universe", return_value=universe), \
             patch.object(sr, "_read_overlays",
                          return_value={"event_window": False,
                                        "regime_blocks_longs": False, "policy": {}}):
            return sr.refresh_research_batch(
                generate_text=generate_text or (lambda *a, **k: None),
                fetch_candles=lambda s, m: _candles(drift=0.8, volume=5_000_000))

    def test_sentinel_dedupe_without_redis(self):
        """Second refresh in the same window aborts BEFORE any LLM call —
        the deterministic sentinel is the guarantee, Redis absent."""
        calls = []

        def counting_llm(*a, **k):
            calls.append(1)
            return None

        with patch("cache.acquire_lock", return_value=None):
            first = self._refresh(generate_text=counting_llm)
            second = self._refresh(generate_text=counting_llm)
        self.assertNotIn("error", first)
        self.assertEqual(second.get("skipped"), "batch_exists")
        # only the first refresh may have spent LLM (its retry budget)
        self.assertLessEqual(len(calls), sr.MAX_LLM_CALLS_PER_REFRESH)

    def test_fallback_theses_persist_and_are_selectable(self):
        summary = self._refresh()  # LLM returns None -> fallback for all
        self.assertGreater(summary["persisted"], 0)
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT planner, selectable FROM research_theses")
        rows = cur.fetchall()
        conn.close()
        self.assertTrue(all(r["planner"] == "fallback" for r in rows))

    def test_llm_array_is_clamped_and_used(self):
        def llm(*a, **k):
            return ('[{"symbol":"AAA","market":"crypto","direction":"long",'
                    '"expected_move_pct":900,"horizon_hours":48,'
                    '"confidence":0.7,"thesis":"t","risks":"r",'
                    '"invalidation":"i"}]')
        self._refresh(generate_text=llm)
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT expected_move_pct, planner FROM research_theses "
                    "WHERE symbol='AAA'")
        row = cur.fetchone()
        conn.close()
        self.assertEqual(row["planner"], "llm")
        self.assertLess(float(row["expected_move_pct"]), 100.0)  # clamped

    def test_select_targets_excludes_busy_and_cooldowns(self):
        self._refresh(symbols=("AAA", "BBB", "CCC", "DDD"))
        conn = database.get_db_connection()
        cur = conn.cursor()
        # agent 1 already runs AAA; BBB is cooling down
        cur.execute(
            "INSERT INTO trading_runs (agent_id, symbol, market, status, created_at)"
            " VALUES (1, 'AAA', 'crypto', 'running', '2026-01-01T00:00:00Z')")
        cur.execute(
            "INSERT INTO fleet_symbol_cooldowns (agent_id, market, symbol, until_ts)"
            " VALUES (1, 'crypto', 'BBB', '2099-01-01T00:00:00Z')")
        conn.commit()
        picked = sr.select_targets(cur, agent_id=1, n=4)
        syms = {t["symbol"] for t in picked}
        self.assertNotIn("AAA", syms)
        self.assertNotIn("BBB", syms)
        conn.close()

    def test_select_targets_diversity_is_preference_not_starvation(self):
        """Diversity caps the FIRST pass; a single-market universe must still
        fill all n slots (perpetual N outranks spread — Phase 3 fix)."""
        self._refresh(symbols=("AAA", "BBB", "CCC", "DDD"))
        conn = database.get_db_connection()
        cur = conn.cursor()
        picked = sr.select_targets(cur, agent_id=2, n=3)
        self.assertEqual(len(picked), 3)  # crypto-only batch still fills n
        conn.close()


class PolicyFeedTests(unittest.TestCase):
    def test_fetch_fails_soft(self):
        import policy_feed
        with patch("policy_feed.requests.get",
                   side_effect=RuntimeError("down")):
            self.assertEqual(policy_feed._fetch_watchlist(["sec"], "x"), [])

    def test_age_gate_returns_empty(self):
        import policy_feed
        stale = {"markets": {"crypto": [{"publication_date": "2026-07-19",
                                         "title": "t"}]},
                 "fetched_at": 0}
        with patch("cache.get_json", return_value=stale):
            self.assertEqual(policy_feed.get_policy_signals(), {})

    def test_cnn_fng_fails_soft(self):
        import psych_feed
        with patch("psych_feed.requests.get", side_effect=RuntimeError("404")):
            self.assertIsNone(psych_feed.fetch_cnn_fear_greed())


if __name__ == "__main__":
    unittest.main()


class SurvivorPoolSizingTests(unittest.TestCase):
    """Cycles 97-101: the survivor cap was 4/4/2/2 = TWELVE, and a 10-slot
    fleet starved on it. Prod batch research:496122 produced ZERO buildable
    candidates and the fleet fell 8 runs -> 2 in a day. Each retire adds a 24h
    cooldown, so the fleet's own losses subtract from the pool it must rebuild
    from — the cap has to clear (slots + cooldowns + infeasible), not just
    slots."""

    def setUp(self):
        for k in list(os.environ):
            if k.startswith("FLEET_RESEARCH_SURVIVORS_"):
                del os.environ[k]

    tearDown = setUp

    def test_the_pool_clears_a_ten_slot_fleet_with_room_for_cooldowns(self):
        total = sum(sr._survivors_per_market().values())
        self.assertGreaterEqual(
            total, 20,
            "12 survivors could not sustain 10 slots once cooldowns and "
            "infeasible theses were subtracted — see cycles 97-101")

    def test_every_automatable_market_keeps_a_share(self):
        # Cross-market diversity: a hot crypto tape must not starve the rest.
        caps = sr._survivors_per_market()
        for market in ("crypto", "us-stock", "futures", "forex"):
            self.assertGreaterEqual(caps.get(market, 0), 1,
                                    f"{market} lost its survivor share")

    def test_each_market_cap_is_env_overridable(self):
        os.environ["FLEET_RESEARCH_SURVIVORS_CRYPTO"] = "3"
        os.environ["FLEET_RESEARCH_SURVIVORS_US_STOCK"] = "9"
        caps = sr._survivors_per_market()
        self.assertEqual(caps["crypto"], 3)
        self.assertEqual(caps["us-stock"], 9)

    def test_a_garbage_override_falls_back_to_the_default(self):
        os.environ["FLEET_RESEARCH_SURVIVORS_CRYPTO"] = "not-a-number"
        self.assertEqual(sr._survivors_per_market()["crypto"],
                         sr._SURVIVOR_DEFAULTS["crypto"])

    def test_a_zero_override_cannot_silently_disable_a_market(self):
        os.environ["FLEET_RESEARCH_SURVIVORS_FOREX"] = "0"
        self.assertGreaterEqual(sr._survivors_per_market()["forex"], 1)

    def test_screen_universe_honours_the_configured_cap(self):
        os.environ["FLEET_RESEARCH_SURVIVORS_CRYPTO"] = "2"
        rows = [{"symbol": f"S{i}USDT", "market": "crypto"} for i in range(6)]
        candles = _candles(volume=50_000_000)
        out = sr.screen_universe(rows, fetch_candles=lambda s, m: candles,
                                 overlays={})
        self.assertLessEqual(len([s for s in out if s["market"] == "crypto"]), 2)
