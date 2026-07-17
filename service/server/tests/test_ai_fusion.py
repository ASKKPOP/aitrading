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

    def test_psych_only_forced_hold(self):
        """The model may not trade on psychology alone — structural rule."""
        out = self._run(json.dumps({"signal": "buy", "score": 0.9, "confidence": 0.9,
                                    "components": {}, "weights_used": {}}),
                        quant=None, sentiment=None, psych=PSYCH)
        self.assertEqual(out["signal"], "hold")
        self.assertTrue(any("forced hold" in e for e in out["evidence"]))

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

    def test_fallback_is_labeled_rule_not_ai(self):
        """When AI is unavailable the payload must say 'rule' — never 'ai'."""
        out = self._fuse(None)
        self.assertEqual(out["fusion_source"], "rule")
        self.assertNotIn("llm_model", out)
        self.assertNotIn("rule_fusion", out)
        # the deterministic weighted score still works
        self.assertIsInstance(out["score"], float)
        self.assertIn(out["signal"], ("buy", "sell", "hold"))

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
