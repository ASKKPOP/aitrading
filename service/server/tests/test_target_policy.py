"""Owner order 2026-08-29: reachable targets ("target price make lower, and
then make order") + raised human factor ("make human fact more higher"),
each case depending on the psych regime.

Unit tests for target_policy plus the wiring proofs: the run_cycle clamp is
integration-tested in test_run_cycle_order_params.py; here we prove the two
new brief lines exist, render, gate on their envs, and are actually wired
into _compose_position_state (a brief line that is not wired is a silent
no-op — the standing lesson)."""

from __future__ import annotations

import inspect
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import run_engine
import target_policy


def _clean_env():
    for k in ("TARGET_PSYCH_CAP", "TARGET_PSYCH_CAP_MAP",
              "PSYCH_WEIGHT_LEVEL"):
        os.environ.pop(k, None)


class TargetPolicyUnitTests(unittest.TestCase):
    def setUp(self):
        _clean_env()

    def tearDown(self):
        _clean_env()

    def test_off_by_default(self):
        os.environ["TARGET_PSYCH_CAP_MAP"] = '{"crypto": {"base": 0.3}}'
        self.assertEqual(target_policy.cap_for("crypto"), (None, ""))
        self.assertEqual(target_policy.prompt_line("crypto"), "")

    def test_on_with_base_level(self):
        os.environ["TARGET_PSYCH_CAP"] = "1"
        os.environ["TARGET_PSYCH_CAP_MAP"] = '{"crypto": {"base": 0.3}}'
        with patch.object(target_policy, "_current_regime",
                          return_value="caution"):
            cap, regime = target_policy.cap_for("crypto")
        self.assertEqual(cap, 0.3)
        self.assertEqual(regime, "caution")

    def test_regime_specific_level_wins_over_base(self):
        os.environ["TARGET_PSYCH_CAP"] = "1"
        os.environ["TARGET_PSYCH_CAP_MAP"] = \
            '{"crypto": {"base": 0.3, "euphoria": 0.6}}'
        with patch.object(target_policy, "_current_regime",
                          return_value="euphoria"):
            cap, _ = target_policy.cap_for("crypto")
        self.assertEqual(cap, 0.6)

    def test_unknown_regime_falls_to_base(self):
        os.environ["TARGET_PSYCH_CAP"] = "1"
        os.environ["TARGET_PSYCH_CAP_MAP"] = '{"crypto": {"base": 0.3}}'
        with patch.object(target_policy, "_current_regime",
                          return_value="unknown"):
            self.assertEqual(target_policy.cap_for("crypto")[0], 0.3)

    def test_regime_read_exception_falls_to_base(self):
        os.environ["TARGET_PSYCH_CAP"] = "1"
        os.environ["TARGET_PSYCH_CAP_MAP"] = '{"crypto": {"base": 0.3}}'

        def _boom():
            raise RuntimeError("db down")

        with patch("regime.current_regime_state", _boom):
            cap, regime = target_policy.cap_for("crypto")
        self.assertEqual(cap, 0.3, "a regime read failure must fall to base, "
                                   "never uncap or raise")
        self.assertEqual(regime, "unknown")

    def test_unmapped_market_is_uncapped(self):
        os.environ["TARGET_PSYCH_CAP"] = "1"
        os.environ["TARGET_PSYCH_CAP_MAP"] = '{"crypto": {"base": 0.3}}'
        self.assertEqual(target_policy.cap_for("forex"), (None, ""))

    def test_bad_json_fails_soft_to_no_cap(self):
        os.environ["TARGET_PSYCH_CAP"] = "1"
        os.environ["TARGET_PSYCH_CAP_MAP"] = "{not json"
        self.assertEqual(target_policy.cap_for("crypto"), (None, ""))

    def test_prompt_line_names_regime_and_level(self):
        os.environ["TARGET_PSYCH_CAP"] = "1"
        os.environ["TARGET_PSYCH_CAP_MAP"] = '{"crypto": {"base": 0.3}}'
        with patch.object(target_policy, "_current_regime",
                          return_value="caution"):
            line = target_policy.prompt_line("crypto")
        self.assertIn("caution", line)
        self.assertIn("0.3%", line)


class CryptoPsychLineTests(unittest.TestCase):
    """The crypto light path read no market psychology before this line."""

    PAYLOAD = {"available": True,
               "fear_greed": {"value": 68, "classification": "Greed",
                              "delta_3d": 4},
               "spikes": [], "shock": [], "anticipation": [],
               "odds_deltas": [], "created_at": "2026-08-29T10:00:00Z"}

    def setUp(self):
        _clean_env()

    def tearDown(self):
        _clean_env()

    def test_renders_value_and_restraint_for_crypto(self):
        import psych_feed
        with patch.object(psych_feed, "get_psych_payload",
                          return_value=self.PAYLOAD):
            line = run_engine._crypto_psych_line({"market": "crypto"})
        self.assertIn("68/100", line)
        self.assertIn("Greed", line)
        self.assertIn("never the sole reason", line)

    def test_other_markets_render_empty(self):
        import psych_feed
        with patch.object(psych_feed, "get_psych_payload",
                          return_value=self.PAYLOAD):
            self.assertEqual(
                run_engine._crypto_psych_line({"market": "us-stock"}), "")

    def test_unavailable_feed_renders_empty(self):
        import psych_feed
        with patch.object(psych_feed, "get_psych_payload",
                          return_value={"available": False}):
            self.assertEqual(
                run_engine._crypto_psych_line({"market": "crypto"}), "")

    def test_feed_exception_renders_empty(self):
        import psych_feed

        def _boom():
            raise RuntimeError("feed down")

        with patch.object(psych_feed, "get_psych_payload", _boom):
            self.assertEqual(
                run_engine._crypto_psych_line({"market": "crypto"}), "")


class PsychWeightLevelTests(unittest.TestCase):
    """PSYCH_WEIGHT_LEVEL default keeps every psych line byte-identical;
    'high' appends exactly one sentence to all three market lines."""

    SENTENCE = "first-class"

    def setUp(self):
        _clean_env()

    def tearDown(self):
        _clean_env()

    def _crypto(self):
        import psych_feed
        with patch.object(psych_feed, "get_psych_payload",
                          return_value=CryptoPsychLineTests.PAYLOAD):
            return run_engine._crypto_psych_line({"market": "crypto"})

    def _us(self):
        import psych_feed
        with patch.object(psych_feed, "us_fear_greed",
                          return_value={"value": 55.0, "classification":
                                        "Neutral", "prev_1w": 50.0,
                                        "source": "cnn"}):
            return run_engine._us_psych_line({"market": "us-stock"})

    def _fx(self):
        import psych_feed
        import cross_market
        with patch.object(psych_feed, "us_fear_greed",
                          return_value={"value": 55.0, "classification":
                                        "Neutral", "prev_1w": 50.0,
                                        "source": "cnn"}), \
                patch.object(cross_market, "dollar_index_cached",
                             return_value=None):
            return run_engine._fx_risk_line({"market": "forex"})

    def test_default_is_byte_identical_no_extra_sentence(self):
        for line in (self._crypto(), self._us(), self._fx()):
            self.assertNotIn(self.SENTENCE, line)

    def test_high_appends_the_sentence_to_all_three(self):
        os.environ["PSYCH_WEIGHT_LEVEL"] = "high"
        for line in (self._crypto(), self._us(), self._fx()):
            self.assertIn(self.SENTENCE, line)
            # the invariant stays verbatim
            self.assertTrue("never the sole reason" in line
                            or "one signal alone is no trade" in line)


class WiringTests(unittest.TestCase):
    """A brief line that is not in _compose_position_state is a silent no-op."""

    def test_crypto_psych_is_wired(self):
        src = inspect.getsource(run_engine._compose_position_state)
        self.assertIn("_crypto_psych_line(run)", src)

    def test_target_band_is_wired(self):
        src = inspect.getsource(run_engine._compose_position_state)
        self.assertIn("_target_band_line(run)", src)

    def test_target_band_line_delegates_to_policy(self):
        os.environ["TARGET_PSYCH_CAP"] = "1"
        os.environ["TARGET_PSYCH_CAP_MAP"] = '{"crypto": {"base": 0.3}}'
        with patch.object(target_policy, "_current_regime",
                          return_value="caution"):
            line = run_engine._target_band_line({"market": "crypto"})
        self.assertIn("target_pct at or below 0.3%", line)
        _clean_env()
        self.assertEqual(run_engine._target_band_line({"market": "crypto"}), "")


class RrFloorEnvTests(unittest.TestCase):
    def test_env_parse_helper(self):
        import order_params
        self.assertEqual(order_params._env_float("NO_SUCH_ENV_XYZ", 2.0), 2.0)
        os.environ["NO_SUCH_ENV_XYZ"] = "0.2"
        try:
            self.assertEqual(order_params._env_float("NO_SUCH_ENV_XYZ", 2.0), 0.2)
            os.environ["NO_SUCH_ENV_XYZ"] = "junk"
            self.assertEqual(order_params._env_float("NO_SUCH_ENV_XYZ", 2.0), 2.0)
        finally:
            os.environ.pop("NO_SUCH_ENV_XYZ", None)

    def test_default_floor_is_unchanged(self):
        import order_params
        self.assertEqual(order_params.RR_FLOOR, 2.0)


if __name__ == "__main__":
    unittest.main()
