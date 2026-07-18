"""Plan 06 D4 — AI-native fusion (LLM mocked; no live calls).

The contract under test:
  * when enabled and usable, the AI verdict REPLACES the fixed-weight one
  * the deterministic result survives as a labeled fallback — a rule score is
    never presented as an AI score
  * the model may choose freely inside the box but cannot redefine the box
    (psych-only -> hold; score/confidence clamped)
"""

from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import ai_fusion

QUANT = {"value": 0.4, "evidence": ["RSI 55"], "current_price": 63000.0}
SENTIMENT = {"value": 0.2, "evidence": ["mildly bullish"]}
PSYCH = {"value": -0.6, "evidence": ["fear 25"]}

AI_REPLY = json.dumps({
    "signal": "buy", "score": 0.55, "confidence": 0.72,
    "components": {"quant": 0.6, "sentiment": 0.3, "psych": -0.5},
    "weights_used": {"quant": 0.7, "sentiment": 0.2, "psych": 0.1},
    "evidence": ["RSI 55 with price above MA20", "fear 25 is a contrarian tailwind"],
    "rationale": "Trend intact; fear is fading.",
})


class FlagTests(unittest.TestCase):
    def test_disabled_returns_none(self):
        with patch.dict(os.environ, {"AI_FUSION_ENABLED": "false"}):
            self.assertIsNone(ai_fusion.fuse_with_ai("BTCUSDT", QUANT, SENTIMENT, PSYCH))

    def test_enabled_but_no_llm_returns_none(self):
        with patch.dict(os.environ, {"AI_FUSION_ENABLED": "true"}), \
             patch("llm_client.llm_configured", return_value=False):
            self.assertIsNone(ai_fusion.fuse_with_ai("BTCUSDT", QUANT, SENTIMENT, PSYCH))


class AiFusionTests(unittest.TestCase):
    def setUp(self):
        ai_fusion._AI_CACHE.clear()   # module-level cache is process-global
        self._env = patch.dict(os.environ, {"AI_FUSION_ENABLED": "true",
                                            "DATA_VERIFY_MODE": "off"})
        self._env.start()

    def tearDown(self):
        self._env.stop()
        ai_fusion._AI_CACHE.clear()

    def _run(self, reply, quant=QUANT, sentiment=SENTIMENT, psych=PSYCH):
        ai_fusion._AI_CACHE.clear()   # each case asserts on a fresh verdict
        return self._run_cached(reply, quant, sentiment, psych)

    def _run_cached(self, reply, quant=QUANT, sentiment=SENTIMENT, psych=PSYCH):
        with patch.object(ai_fusion, "build_factor_snapshot", return_value={"symbol": "BTCUSDT"}), \
             patch("llm_client.llm_configured", return_value=True), \
             patch("llm_client.generate_text", return_value=reply), \
             patch("llm_client.active_provider_model", return_value="claude-opus-4-8"):
            return ai_fusion.fuse_with_ai("BTCUSDT", quant, sentiment, psych)

    def test_ai_verdict_shape(self):
        out = self._run(AI_REPLY)
        self.assertEqual(out["signal"], "buy")
        self.assertEqual(out["score"], 0.55)
        self.assertEqual(out["confidence"], 0.72)
        self.assertEqual(out["fusion_source"], "ai")
        self.assertEqual(out["llm_model"], "claude-opus-4-8")
        self.assertEqual(out["ai_weights"]["quant"], 0.7)   # model chose its own weights
        self.assertIn("RSI 55 with price above MA20", out["evidence"])

    def test_score_and_confidence_clamped(self):
        out = self._run(json.dumps({"signal": "buy", "score": 99, "confidence": 5,
                                    "components": {}, "weights_used": {}}))
        self.assertEqual(out["score"], 1.0)
        self.assertEqual(out["confidence"], 1.0)
        out = self._run(json.dumps({"signal": "sell", "score": -99, "confidence": -3,
                                    "components": {}, "weights_used": {}}))
        self.assertEqual(out["score"], -1.0)
        self.assertEqual(out["confidence"], 0.0)

    def test_psych_only_is_never_put_to_the_model(self):
        """The invariant is now enforced by NOT ASKING: with psychology alone
        the verdict is 'hold' whatever a model would say, so it is not
        consulted — it cannot argue past a rule it is never shown. Previously
        we called the model and overrode a 'buy' afterwards; same outcome, two
        Opus calls cheaper, and the rule is no longer negotiable.
        The resulting hold is asserted in PublicEndpointAbuseTests via
        fuse_symbol (the caller's rule path), which is where it now lives.
        """
        out = self._run(json.dumps({"signal": "buy", "score": 0.9, "confidence": 0.9,
                                    "components": {}, "weights_used": {}}),
                        quant=None, sentiment=None, psych=PSYCH)
        self.assertIsNone(out)

    def test_a_single_usable_component_still_reaches_the_model(self):
        """The guard must be narrow: psych + sentiment is not psych-alone."""
        out = self._run(AI_REPLY, quant=None, sentiment=SENTIMENT, psych=PSYCH)
        self.assertIsNotNone(out)
        self.assertEqual(out["fusion_source"], "ai")

    def test_unusable_replies_return_none(self):
        self.assertIsNone(self._run("no json here"))
        self.assertIsNone(self._run(json.dumps({"signal": "moon", "score": 0.5})))
        self.assertIsNone(self._run(""))


class CacheTests(unittest.TestCase):
    """Cost control: a frontier call must not fire on every 30s dashboard poll."""

    def setUp(self):
        ai_fusion._AI_CACHE.clear()
        # D5's verifier is a second model call; these tests are about the
        # fusion cache alone, so hold it off (D5 has its own suite).
        self._env = patch.dict(os.environ, {"AI_FUSION_ENABLED": "true",
                                            "DATA_VERIFY_MODE": "off"})
        self._env.start()

    def tearDown(self):
        self._env.stop()
        ai_fusion._AI_CACHE.clear()

    def _fuse(self):
        with patch.object(ai_fusion, "build_factor_snapshot", return_value={}), \
             patch("llm_client.llm_configured", return_value=True), \
             patch("llm_client.generate_text", return_value=AI_REPLY) as gen, \
             patch("llm_client.active_provider_model", return_value="claude-opus-4-8"):
            out = ai_fusion.fuse_with_ai("BTCUSDT", QUANT, SENTIMENT, PSYCH)
            return out, gen

    def test_second_call_is_cached(self):
        out1, gen1 = self._fuse()
        self.assertEqual(gen1.call_count, 1)
        self.assertEqual(out1["cached_age_s"], 0)
        out2, gen2 = self._fuse()
        self.assertEqual(gen2.call_count, 0)          # no second model call
        self.assertEqual(out2["signal"], out1["signal"])
        self.assertIn("cached_age_s", out2)           # age is disclosed, not hidden

    def test_expired_cache_refetches(self):
        self._fuse()
        stamp, payload = ai_fusion._AI_CACHE["BTCUSDT"]
        ai_fusion._AI_CACHE["BTCUSDT"] = (stamp - ai_fusion.ai_fusion_ttl() - 1, payload)
        _, gen = self._fuse()
        self.assertEqual(gen.call_count, 1)

    def test_ttl_and_tier_are_configurable(self):
        with patch.dict(os.environ, {"AI_FUSION_TTL": "300"}):
            self.assertEqual(ai_fusion.ai_fusion_ttl(), 300)
        with patch.dict(os.environ, {"AI_FUSION_TTL": "5"}):
            self.assertEqual(ai_fusion.ai_fusion_ttl(), 60)     # floor
        with patch.dict(os.environ, {"AI_FUSION_TIER": "brief"}):
            self.assertEqual(ai_fusion.ai_fusion_tier(), "brief")
        with patch.dict(os.environ, {"AI_FUSION_TIER": "nonsense"}):
            self.assertEqual(ai_fusion.ai_fusion_tier(), "decision")

    def test_cheap_tier_is_honored(self):
        with patch.dict(os.environ, {"AI_FUSION_TIER": "brief"}), \
             patch.object(ai_fusion, "build_factor_snapshot", return_value={}), \
             patch("llm_client.llm_configured", return_value=True), \
             patch("llm_client.generate_text", return_value=AI_REPLY) as gen, \
             patch("llm_client.active_provider_model", return_value="claude-haiku-4-5"):
            out = ai_fusion.fuse_with_ai("ETHUSDT", QUANT, SENTIMENT, PSYCH)
        self.assertEqual(gen.call_args.kwargs["tier"], "brief")
        self.assertEqual(out["llm_model"], "claude-haiku-4-5")


class PsychCapTests(unittest.TestCase):
    """The Signals Board tells users the psych weight is structurally capped.
    That was true only of the rule path — the AI's score is used directly and
    cannot be decomposed, so nothing stopped a psychology-led AI verdict.
    (Audit 2026-07-17, 4/4 QA: false-user-claim.)

    The box is now enforced on the model's own declaration: say psychology led,
    and the verdict is discarded.
    """

    def setUp(self):
        ai_fusion._AI_CACHE.clear()
        self._env = patch.dict(os.environ, {"AI_FUSION_ENABLED": "true",
                                            "DATA_VERIFY_MODE": "off"})
        self._env.start()

    def tearDown(self):
        self._env.stop()
        ai_fusion._AI_CACHE.clear()

    def _reply(self, psych_weight):
        return json.dumps({"signal": "buy", "score": 0.9, "confidence": 0.9,
                           "components": {"quant": 0.1, "psych": 0.9},
                           "weights_used": {"quant": 1 - psych_weight, "psych": psych_weight},
                           "evidence": ["e"], "rationale": "r"})

    def _run(self, psych_weight):
        with patch.object(ai_fusion, "build_factor_snapshot", return_value={}), \
             patch("llm_client.llm_configured", return_value=True), \
             patch("llm_client.generate_text", return_value=self._reply(psych_weight)), \
             patch("llm_client.active_provider_model", return_value="m"):
            return ai_fusion.fuse_with_ai("BTCUSDT", QUANT, SENTIMENT, PSYCH)

    def test_psychology_led_verdict_is_discarded(self):
        from signal_fusion import PSYCH_WEIGHT_MAX
        self.assertIsNone(self._run(0.9))
        self.assertIsNone(self._run(PSYCH_WEIGHT_MAX + 0.01))

    def test_a_verdict_inside_the_cap_stands(self):
        from signal_fusion import PSYCH_WEIGHT_MAX
        out = self._run(PSYCH_WEIGHT_MAX)          # exactly at the cap is allowed
        self.assertIsNotNone(out)
        self.assertEqual(out["fusion_source"], "ai")

    def test_the_model_still_chooses_freely_below_the_cap(self):
        """The box constrains one wall, not the whole room."""
        out = self._run(0.1)
        self.assertEqual(out["ai_weights"]["quant"], 0.9)

    def test_a_discarded_verdict_falls_back_labelled(self):
        """Rejecting the AI must not silently pass a rule score off as an AI one."""
        import signal_fusion
        with patch.object(signal_fusion, "_quant_component", return_value=QUANT), \
             patch.object(signal_fusion, "_sentiment_component", return_value=SENTIMENT), \
             patch.object(signal_fusion, "_psych_component", return_value=PSYCH), \
             patch("ai_fusion.fuse_with_ai", return_value=None):
            out = signal_fusion.fuse_symbol("BTCUSDT")
        self.assertEqual(out["fusion_source"], "rule-fallback")


class PublicEndpointAbuseTests(unittest.TestCase):
    """The fusion endpoint is public and unauthenticated, so callers decide how
    many symbols exist. Live: a made-up symbol bought 2 Opus calls and ~21s of
    a worker (audit 2026-07-17, 4/4 QA)."""

    def setUp(self):
        ai_fusion._AI_CACHE.clear()
        self._env = patch.dict(os.environ, {"AI_FUSION_ENABLED": "true",
                                            "DATA_VERIFY_MODE": "off"})
        self._env.start()

    def tearDown(self):
        self._env.stop()
        ai_fusion._AI_CACHE.clear()

    def test_nothing_to_fuse_costs_no_model_call(self):
        """quant=None + sentiment=None is structurally forced to hold, so the
        model cannot change the answer — do not pay it."""
        with patch("llm_client.llm_configured", return_value=True), \
             patch("llm_client.generate_text") as gen:
            out = ai_fusion.fuse_with_ai("ZZQQ9", None, None, PSYCH)
        self.assertIsNone(out)
        self.assertEqual(gen.call_count, 0)      # the money pump is closed

    def test_a_real_symbol_still_calls_the_model(self):
        with patch.object(ai_fusion, "build_factor_snapshot", return_value={}), \
             patch("llm_client.llm_configured", return_value=True), \
             patch("llm_client.generate_text", return_value=AI_REPLY) as gen, \
             patch("llm_client.active_provider_model", return_value="m"):
            out = ai_fusion.fuse_with_ai("BTCUSDT", QUANT, None, PSYCH)
        self.assertEqual(gen.call_count, 1)
        self.assertEqual(out["fusion_source"], "ai")

    def test_skipping_is_labelled_rule_not_fallback(self):
        """Deliberately not calling the model is a choice, not a failure."""
        import signal_fusion
        with patch.object(signal_fusion, "_quant_component", return_value=None), \
             patch.object(signal_fusion, "_sentiment_component", return_value=None), \
             patch.object(signal_fusion, "_psych_component", return_value=PSYCH):
            out = signal_fusion.fuse_symbol("ZZQQ9")
        self.assertEqual(out["fusion_source"], "rule")
        self.assertEqual(out["signal"], "hold")   # structurally forced anyway

    def test_cache_is_bounded_against_novel_symbols(self):
        """A loop over junk symbols must not grow the cache forever."""
        with patch.object(ai_fusion, "build_factor_snapshot", return_value={}), \
             patch("llm_client.llm_configured", return_value=True), \
             patch("llm_client.generate_text", return_value=AI_REPLY), \
             patch("llm_client.active_provider_model", return_value="m"):
            for i in range(ai_fusion._AI_CACHE_MAX + 25):
                ai_fusion.fuse_with_ai(f"SYM{i}", QUANT, None, PSYCH)
        self.assertLessEqual(len(ai_fusion._AI_CACHE), ai_fusion._AI_CACHE_MAX)

    def test_eviction_drops_the_oldest_first(self):
        with patch.object(ai_fusion, "build_factor_snapshot", return_value={}), \
             patch("llm_client.llm_configured", return_value=True), \
             patch("llm_client.generate_text", return_value=AI_REPLY), \
             patch("llm_client.active_provider_model", return_value="m"):
            for i in range(ai_fusion._AI_CACHE_MAX + 5):
                ai_fusion.fuse_with_ai(f"S{i}", QUANT, None, PSYCH)
        self.assertNotIn("S0", ai_fusion._AI_CACHE)                       # oldest gone
        self.assertIn(f"S{ai_fusion._AI_CACHE_MAX + 4}", ai_fusion._AI_CACHE)  # newest kept


class FuseSymbolIntegrationTests(unittest.TestCase):
    """fuse_symbol: AI is primary, rule is the labeled fallback."""

    def _fuse(self, ai_return):
        import signal_fusion
        with patch.object(signal_fusion, "_quant_component", return_value=QUANT), \
             patch.object(signal_fusion, "_sentiment_component", return_value=SENTIMENT), \
             patch.object(signal_fusion, "_psych_component", return_value=PSYCH), \
             patch("ai_fusion.fuse_with_ai", return_value=ai_return):
            return signal_fusion.fuse_symbol("BTCUSDT")

    def test_verification_and_age_survive_the_handoff(self):
        """Both are produced upstream and were dropped by fuse_symbol — the
        verdict costs a real model call, and the age is what tells a reader a
        cached verdict from a fresh one. Nothing asserted they arrived.
        """
        ai = {"signal": "hold", "score": 0.05, "confidence": 0.35,
              "ai_components": {}, "ai_weights": {}, "evidence": [], "rationale": "r",
              "fusion_source": "ai", "llm_model": "claude-opus-4-8",
              "cached_age_s": 42,
              "data_verification": {"status": "suspect", "mode": "advisory",
                                    "reason": "quant feed stale", "applied": False}}
        out = self._fuse(ai)
        self.assertEqual(out["data_verification"]["status"], "suspect")
        self.assertEqual(out["data_verification"]["reason"], "quant feed stale")
        self.assertEqual(out["cached_age_s"], 42)

    def test_fresh_verdict_reports_zero_age_not_missing(self):
        """cached_age_s=0 must reach the caller; a falsy value must not be
        confused with 'absent' on the way through."""
        ai = {"signal": "buy", "score": 0.5, "confidence": 0.6,
              "ai_components": {}, "ai_weights": {}, "evidence": [], "rationale": "r",
              "fusion_source": "ai", "llm_model": "m", "cached_age_s": 0,
              "data_verification": {"status": "ok", "mode": "advisory",
                                    "reason": "", "applied": False}}
        out = self._fuse(ai)
        self.assertEqual(out["cached_age_s"], 0)
        self.assertEqual(out["data_verification"]["status"], "ok")

    def test_ai_replaces_rule_and_keeps_it_visible(self):
        ai = {"signal": "buy", "score": 0.55, "confidence": 0.72,
              "ai_components": {"quant": 0.6}, "ai_weights": {"quant": 0.7},
              "evidence": ["ai evidence"], "rationale": "why",
              "fusion_source": "ai", "llm_model": "claude-opus-4-8"}
        out = self._fuse(ai)
        self.assertEqual(out["fusion_source"], "ai")
        self.assertEqual(out["score"], 0.55)
        self.assertEqual(out["signal"], "buy")
        self.assertEqual(out["llm_model"], "claude-opus-4-8")
        self.assertIn("ai evidence", out["evidence"])
        # the deterministic result is preserved for comparison, not discarded
        self.assertIn("rule_fusion", out)
        self.assertIsInstance(out["rule_fusion"]["score"], float)

    def test_fusion_off_is_labeled_rule(self):
        """Flag off: 'rule' is the honest label — nothing failed."""
        with patch.dict(os.environ, {"AI_FUSION_ENABLED": "false"}):
            out = self._fuse(None)
        self.assertEqual(out["fusion_source"], "rule")
        self.assertNotIn("llm_model", out)
        self.assertNotIn("rule_fusion", out)
        self.assertIsInstance(out["score"], float)
        self.assertIn(out["signal"], ("buy", "sell", "hold"))

    def test_enabled_but_unusable_is_labeled_fallback_not_rule(self):
        """Flag ON + None = the model failed. generate_text swallows provider
        errors and returns None, so this is what a real outage looks like — it
        must NOT wear the same label as 'AI fusion is off'."""
        with patch.dict(os.environ, {"AI_FUSION_ENABLED": "true"}):
            out = self._fuse(None)
        self.assertEqual(out["fusion_source"], "rule-fallback")
        self.assertIn("enabled but returned nothing usable", out["note"])
        self.assertIn(out["signal"], ("buy", "sell", "hold"))   # still tradeable

    def test_ai_exception_falls_back_labeled(self):
        import signal_fusion
        with patch.object(signal_fusion, "_quant_component", return_value=QUANT), \
             patch.object(signal_fusion, "_sentiment_component", return_value=SENTIMENT), \
             patch.object(signal_fusion, "_psych_component", return_value=PSYCH), \
             patch("ai_fusion.fuse_with_ai", side_effect=RuntimeError("model down")):
            out = signal_fusion.fuse_symbol("BTCUSDT")
        self.assertEqual(out["fusion_source"], "rule-fallback")
        self.assertIn(out["signal"], ("buy", "sell", "hold"))


if __name__ == "__main__":
    unittest.main()
