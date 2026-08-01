"""Steps 0+1 of the confidence-calibration plan (2026-08-01).

PROD_PAIRS is the REAL population the plan was written against: the 98 closed
runs' (entry confidence, won) pairs exported from production on 2026-08-01
(21 winners / 77 losers, base rate 21.4%). The headline test asserts the
entire point of Step 1 on that real data: the Platt-calibrated Brier beats
both the raw scalar and the base-rate quote.
"""
import unittest
from unittest.mock import patch

import confidence_calibration as cc

PROD_PAIRS = [
    (0.62, False),
    (0.68, True),
    (0.65, False),
    (0.65, False),
    (0.63, False),
    (0.65, False),
    (0.58, False),
    (0.61, False),
    (0.6, False),
    (0.62, False),
    (0.57, False),
    (0.55, False),
    (0.55, False),
    (0.54, False),
    (0.55, False),
    (0.62, True),
    (0.62, False),
    (0.61, True),
    (0.62, True),
    (0.58, True),
    (0.63, False),
    (0.57, False),
    (0.58, True),
    (0.62, False),
    (0.62, True),
    (0.62, True),
    (0.58, False),
    (0.57, False),
    (0.61, False),
    (0.55, False),
    (0.53, False),
    (0.58, False),
    (0.58, False),
    (0.63, False),
    (0.62, False),
    (0.61, False),
    (0.62, False),
    (0.62, False),
    (0.61, False),
    (0.62, False),
    (0.61, False),
    (0.62, False),
    (0.58, False),
    (0.62, False),
    (0.62, False),
    (0.62, False),
    (0.62, False),
    (0.62, False),
    (0.62, False),
    (0.58, True),
    (0.6, False),
    (0.58, True),
    (0.58, True),
    (0.62, True),
    (0.62, True),
    (0.6, False),
    (0.6, False),
    (0.56, False),
    (0.6, False),
    (0.62, False),
    (0.64, False),
    (0.58, False),
    (0.62, True),
    (0.64, False),
    (0.58, False),
    (0.58, False),
    (0.62, True),
    (0.62, False),
    (0.58, False),
    (0.54, False),
    (0.58, False),
    (0.58, False),
    (0.62, True),
    (0.58, False),
    (0.61, False),
    (0.61, True),
    (0.55, True),
    (0.62, False),
    (0.68, False),
    (0.75, False),
    (0.58, False),
    (0.62, False),
    (0.95, False),
    (0.95, True),
    (0.95, False),
    (0.95, False),
    (0.95, False),
    (0.95, False),
    (0.95, False),
    (0.95, False),
    (0.95, False),
    (0.95, False),
    (0.78, True),
    (0.7, False),
    (0.78, False),
    (0.63, False),
    (0.66, True),
    (0.62, False),
]


class PureScoring(unittest.TestCase):
    def test_brier_perfect_is_zero(self):
        self.assertEqual(cc.brier_score([(1.0, True), (0.0, False)]), 0.0)

    def test_brier_coin_flip_is_quarter(self):
        self.assertAlmostEqual(cc.brier_score([(0.5, True), (0.5, False)]), 0.25)

    def test_brier_empty_is_none(self):
        self.assertIsNone(cc.brier_score([]))

    def test_curve_buckets_cover_everything(self):
        curve = cc.calibration_curve(PROD_PAIRS)
        self.assertEqual(sum(b["n"] for b in curve), len(PROD_PAIRS))

    def test_curve_reproduces_the_inversion(self):
        """The measured pathology: the >=0.70 bucket wins LESS than 0.65-0.70."""
        curve = {(b["lo"], b["hi"]): b for b in cc.calibration_curve(PROD_PAIRS)}
        top = curve[(0.70, 1.0)]
        mid = curve[(0.65, 0.70)]
        self.assertLess(top["win_rate"], mid["win_rate"])


class PlattFit(unittest.TestCase):
    def test_refuses_thin_or_single_class_samples(self):
        self.assertIsNone(cc.fit_platt([(0.6, True)] * 10))          # thin
        self.assertIsNone(cc.fit_platt([(0.6, False)] * 50))         # no winners
        self.assertIsNone(cc.fit_platt([(0.6, True)] * 50))          # no losers

    def test_recovers_direction_on_separable_data(self):
        pairs = [(0.3, False)] * 40 + [(0.8, True)] * 40
        fit = cc.fit_platt(pairs)
        self.assertIsNotNone(fit)
        self.assertGreater(fit[0], 0)  # higher conf -> higher p
        self.assertGreater(cc.platt_apply(fit, 0.8), cc.platt_apply(fit, 0.3))

    def test_real_data_platt_beats_raw_and_base(self):
        """THE Step-1 claim, on the real 98-run production sample."""
        fit = cc.fit_platt(PROD_PAIRS)
        self.assertIsNotNone(fit)
        raw = cc.brier_score(PROD_PAIRS)
        calibrated = cc.brier_score([(cc.platt_apply(fit, c), w) for c, w in PROD_PAIRS])
        base = 21 / 98
        self.assertLess(calibrated, raw)                  # beats the raw scalar
        self.assertLess(calibrated, base * (1 - base) + 0.005)  # ~beats base quote
        # and the mapped probabilities live near reality, not near 0.6
        mean_p = sum(cc.platt_apply(fit, c) for c, _ in PROD_PAIRS) / len(PROD_PAIRS)
        self.assertLess(abs(mean_p - base), 0.08)


class Scoreboard(unittest.TestCase):
    def test_build_scoreboard_on_real_pairs(self):
        sb = cc.build_scoreboard(PROD_PAIRS)
        self.assertEqual(sb["n"], 98)
        self.assertAlmostEqual(sb["base_rate"], 0.2143, places=3)
        self.assertIsNotNone(sb["platt"])
        self.assertLess(sb["brier_platt"], sb["brier_raw"])

    def test_empty_ledger_degrades_gracefully(self):
        sb = cc.build_scoreboard([])
        self.assertEqual(sb["n"], 0)
        self.assertIsNone(sb["brier_raw"])
        self.assertIsNone(sb["platt"])


class GatedRead(unittest.TestCase):
    def test_off_by_default_returns_none(self):
        with patch.dict("os.environ", {}, clear=False):
            import os
            os.environ.pop("RUN_CONF_CALIBRATED", None)
            self.assertIsNone(cc.calibrated_confidence(0.62))

    def test_shadow_maps_through_the_fit(self):
        sb = cc.build_scoreboard(PROD_PAIRS)
        with patch.dict("os.environ", {"RUN_CONF_CALIBRATED": "shadow"}), \
             patch.object(cc, "get_scoreboard", return_value=sb):
            p = cc.calibrated_confidence(0.62)
        self.assertIsNotNone(p)
        self.assertLess(p, 0.40)   # "0.62" maps toward its delivered ~21%, not 62%

    def test_never_raises_on_garbage(self):
        with patch.dict("os.environ", {"RUN_CONF_CALIBRATED": "shadow"}), \
             patch.object(cc, "get_scoreboard", side_effect=RuntimeError("db down")):
            self.assertIsNone(cc.calibrated_confidence(0.62))
        self.assertIsNone(cc.calibrated_confidence(None))
        self.assertIsNone(cc.calibrated_confidence(True))


if __name__ == "__main__":
    unittest.main()
