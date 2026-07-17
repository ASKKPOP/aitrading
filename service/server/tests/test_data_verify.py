"""Plan 06 D5 — AI data verification (LLM mocked; no live calls).

The contract under test:
  * facts are MEASURED in code, never asked of the model (P-3)
  * the model reports; code enforces (P-1) — and only in enforce mode
  * every failure path is fail-OPEN: a verifier that cannot run must never be
    the reason a decision is blocked
"""

from __future__ import annotations

import json
import os
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import data_verify

SNAPSHOT = {
    "symbol": "BTCUSDT",
    "quant": {"rsi_14": 47.9, "current_price": 62917.2, "funding_rate": 1.05e-05,
              "long_short_ratio": 1.79, "sigma_daily_pct": 1.93},
    "sentiment": None,
    "psych": {"fear_greed": {"value": 27, "classification": "Fear"}},
    "whales": {"btc_transfer_usd": 0, "eth_net_flow_usd": 0},
    "etf_flows": {"direction": "inflow", "btc": {"as_of": "2026-07-16"}},
    "next_event": {"title": "FOMC rate decision", "hours_until": 296.4},
}

OK_REPLY = json.dumps({"status": "ok", "concerns": [], "reason": "Inputs consistent."})
SUSPECT_HIGH = json.dumps({
    "status": "suspect",
    "concerns": [{"field": "etf_flows.direction", "issue": "headline disagrees with counts",
                  "severity": "high"}],
    "reason": "ETF headline contradicts its own numbers.",
})
SUSPECT_LOW = json.dumps({
    "status": "suspect",
    "concerns": [{"field": "whales", "issue": "all zero, possibly idle feed", "severity": "low"}],
    "reason": "Whale feed is quiet; not disqualifying.",
})


class MeasureTests(unittest.TestCase):
    """The deterministic half. No model involved — these are facts or bugs."""

    def test_presence_and_absence(self):
        f = data_verify.measure_snapshot(SNAPSHOT)
        self.assertIn("quant", f["sources_present"])
        self.assertIn("sentiment", f["sources_missing"])   # None -> missing
        self.assertIn("cross_market", f["sources_missing"])  # absent key -> missing

    def test_out_of_range_detected(self):
        snap = {**SNAPSHOT, "quant": {**SNAPSHOT["quant"], "rsi_14": 4000.0}}
        f = data_verify.measure_snapshot(snap)
        self.assertEqual(f["out_of_range"][0]["field"], "rsi_14")
        self.assertEqual(f["out_of_range"][0]["value"], 4000.0)

    def test_in_range_values_are_not_flagged(self):
        self.assertEqual(data_verify.measure_snapshot(SNAPSHOT)["out_of_range"], [])

    def test_negative_price_is_impossible(self):
        snap = {**SNAPSHOT, "quant": {**SNAPSHOT["quant"], "current_price": -5.0}}
        f = data_verify.measure_snapshot(snap)
        self.assertEqual([c["field"] for c in f["out_of_range"]], ["current_price"])

    def test_etf_age_is_computed_not_guessed(self):
        two_days = (date.today() - timedelta(days=2)).isoformat()
        snap = {**SNAPSHOT, "etf_flows": {"btc": {"as_of": two_days}}}
        self.assertEqual(data_verify.measure_snapshot(snap)["etf_print_age_days"], 2)

    def test_unparseable_date_is_absent_not_wrong(self):
        snap = {**SNAPSHOT, "etf_flows": {"btc": {"as_of": "not-a-date"}}}
        self.assertIsNone(data_verify.measure_snapshot(snap)["etf_print_age_days"])

    def test_whale_all_zero_is_stated_as_fact(self):
        self.assertTrue(data_verify.measure_snapshot(SNAPSHOT)["whales_all_zero"])
        snap = {**SNAPSHOT, "whales": {"btc_transfer_usd": 14_200_000}}
        self.assertFalse(data_verify.measure_snapshot(snap)["whales_all_zero"])

    def test_empty_snapshot_does_not_crash(self):
        f = data_verify.measure_snapshot({})
        self.assertEqual(f["sources_present"], [])
        self.assertEqual(len(f["sources_missing"]), 7)


class VerifyTests(unittest.TestCase):
    def _run(self, reply, env=None):
        with patch.dict(os.environ, {"DATA_VERIFY_MODE": "advisory", **(env or {})}), \
             patch("llm_client.llm_configured", return_value=True), \
             patch("llm_client.generate_text", return_value=reply) as gen, \
             patch("llm_client.active_provider_model", return_value="claude-haiku-4-5"):
            return data_verify.verify_snapshot(SNAPSHOT), gen

    def test_ok_verdict(self):
        out, _ = self._run(OK_REPLY)
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["concerns"], [])
        self.assertIn("sources_missing", out["facts"])   # facts travel with the verdict

    def test_suspect_verdict_carries_concerns(self):
        out, _ = self._run(SUSPECT_HIGH)
        self.assertEqual(out["status"], "suspect")
        self.assertEqual(out["concerns"][0]["severity"], "high")

    def test_mode_off_is_fail_open(self):
        out, gen = self._run(OK_REPLY, env={"DATA_VERIFY_MODE": "off"})
        self.assertIsNone(out)
        self.assertEqual(gen.call_count, 0)   # and costs nothing

    def test_no_llm_is_fail_open(self):
        with patch.dict(os.environ, {"DATA_VERIFY_MODE": "advisory"}), \
             patch("llm_client.llm_configured", return_value=False):
            self.assertIsNone(data_verify.verify_snapshot(SNAPSHOT))

    def test_unusable_replies_are_fail_open(self):
        for bad in ("", "no json", json.dumps({"status": "maybe"})):
            out, _ = self._run(bad)
            self.assertIsNone(out, f"expected fail-open for {bad!r}")

    def test_truncated_reply_fails_open(self):
        """Live prod, 2026-07-17: a verbose model hit max_tokens and the JSON
        was cut mid-string. Must fail open, never half-parse."""
        truncated = '```json\n{"status": "suspect", "concerns": [{"field": "whales", "issue": "All whale metr'
        out, _ = self._run(truncated)
        self.assertIsNone(out)

    def test_fenced_json_is_parsed(self):
        """The model wraps replies in ```json fences — that is not a failure."""
        out, _ = self._run(f"```json\n{OK_REPLY}\n```")
        self.assertEqual(out["status"], "ok")

    def test_token_budget_fits_a_realistic_verbose_reply(self):
        """Guards the regression directly: the budget must clear a full
        3-concern verdict written at the verbose end of the model's range."""
        verbose = json.dumps({
            "status": "suspect",
            "concerns": [{"field": f"field_{i}", "issue": "w " * 20, "severity": "low"}
                         for i in range(3)],
            "reason": "s " * 25,
        })
        # ~4 chars/token is the standard rough conversion for English JSON.
        self.assertLess(len(verbose) / 4, 900,
                        "max_tokens=900 must clear a full verbose verdict")
        out, _ = self._run(verbose)
        self.assertEqual(len(out["concerns"]), 3)

    def test_cheap_tier_by_default_and_configurable(self):
        _, gen = self._run(OK_REPLY)
        self.assertEqual(gen.call_args.kwargs["tier"], "brief")
        _, gen = self._run(OK_REPLY, env={"DATA_VERIFY_TIER": "decision"})
        self.assertEqual(gen.call_args.kwargs["tier"], "decision")

    def test_unknown_severity_defaults_to_low(self):
        reply = json.dumps({"status": "suspect", "reason": "x",
                            "concerns": [{"field": "f", "issue": "i", "severity": "CATASTROPHIC"}]})
        out, _ = self._run(reply)
        self.assertEqual(out["concerns"][0]["severity"], "low")   # cannot invent a tier

    def test_mode_defaults_to_advisory(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DATA_VERIFY_MODE", None)
            self.assertEqual(data_verify.data_verify_mode(), "advisory")
        with patch.dict(os.environ, {"DATA_VERIFY_MODE": "nonsense"}):
            self.assertEqual(data_verify.data_verify_mode(), "advisory")


class ApplyTests(unittest.TestCase):
    """P-1: the model reports, code enforces."""

    VERDICT = {"signal": "buy", "score": 0.55, "evidence": ["ai evidence"]}

    def _verification(self, reply, mode):
        return {**json.loads(reply), "facts": {}, "mode": mode,
                "llm_model": "claude-haiku-4-5"}

    def test_advisory_annotates_but_never_changes_the_trade(self):
        out = data_verify.apply_verification(
            self.VERDICT, self._verification(SUSPECT_HIGH, "advisory"))
        self.assertEqual(out["signal"], "buy")          # untouched
        self.assertEqual(out["data_verification"]["status"], "suspect")
        self.assertFalse(out["data_verification"]["applied"])

    def test_enforce_high_severity_forces_hold(self):
        out = data_verify.apply_verification(
            self.VERDICT, self._verification(SUSPECT_HIGH, "enforce"))
        self.assertEqual(out["signal"], "hold")
        self.assertTrue(out["data_verification"]["applied"])
        self.assertTrue(any("forced hold" in e for e in out["evidence"]))

    def test_enforce_low_severity_does_not_block(self):
        """A quiet whale feed is not a reason to stop trading."""
        out = data_verify.apply_verification(
            self.VERDICT, self._verification(SUSPECT_LOW, "enforce"))
        self.assertEqual(out["signal"], "buy")
        self.assertFalse(out["data_verification"]["applied"])

    def test_enforce_ok_verdict_passes_through(self):
        out = data_verify.apply_verification(
            self.VERDICT, self._verification(OK_REPLY, "enforce"))
        self.assertEqual(out["signal"], "buy")
        self.assertFalse(out["data_verification"]["applied"])

    def test_no_verification_leaves_verdict_untouched(self):
        out = data_verify.apply_verification(self.VERDICT, None)
        self.assertEqual(out, self.VERDICT)
        self.assertNotIn("data_verification", out)

    def test_apply_does_not_mutate_the_caller_verdict(self):
        original = {"signal": "buy", "score": 0.55, "evidence": ["ai evidence"]}
        data_verify.apply_verification(original, self._verification(SUSPECT_HIGH, "enforce"))
        self.assertEqual(original["signal"], "buy")
        self.assertEqual(original["evidence"], ["ai evidence"])


class FusionIntegrationTests(unittest.TestCase):
    """D5 rides inside D4's cache: verified once per TTL, not once per poll."""

    def setUp(self):
        import ai_fusion
        ai_fusion._AI_CACHE.clear()
        self._env = patch.dict(os.environ, {"AI_FUSION_ENABLED": "true",
                                            "DATA_VERIFY_MODE": "enforce"})
        self._env.start()

    def tearDown(self):
        import ai_fusion
        self._env.stop()
        ai_fusion._AI_CACHE.clear()

    AI_REPLY = json.dumps({"signal": "buy", "score": 0.55, "confidence": 0.72,
                           "components": {}, "weights_used": {},
                           "evidence": ["fusion evidence"], "rationale": "why"})

    def test_suspect_inputs_hold_the_fused_verdict(self):
        import ai_fusion
        with patch.object(ai_fusion, "build_factor_snapshot", return_value=SNAPSHOT), \
             patch("llm_client.llm_configured", return_value=True), \
             patch("llm_client.generate_text", side_effect=[self.AI_REPLY, SUSPECT_HIGH]), \
             patch("llm_client.active_provider_model", return_value="m"):
            out = ai_fusion.fuse_with_ai("BTCUSDT", {"value": 0.4}, None, {"value": -0.6})
        self.assertEqual(out["signal"], "hold")           # buy -> hold on bad inputs
        self.assertTrue(out["data_verification"]["applied"])

    def test_verifier_failure_does_not_sink_the_verdict(self):
        import ai_fusion
        with patch.object(ai_fusion, "build_factor_snapshot", return_value=SNAPSHOT), \
             patch("llm_client.llm_configured", return_value=True), \
             patch("llm_client.generate_text", return_value=self.AI_REPLY), \
             patch("llm_client.active_provider_model", return_value="m"), \
             patch("data_verify.verify_snapshot", side_effect=RuntimeError("verifier down")):
            out = ai_fusion.fuse_with_ai("BTCUSDT", {"value": 0.4}, None, {"value": -0.6})
        self.assertEqual(out["signal"], "buy")            # fail-open
        self.assertNotIn("data_verification", out)

    def test_verification_is_cached_with_the_verdict(self):
        import ai_fusion
        with patch.object(ai_fusion, "build_factor_snapshot", return_value=SNAPSHOT), \
             patch("llm_client.llm_configured", return_value=True), \
             patch("llm_client.generate_text", side_effect=[self.AI_REPLY, OK_REPLY]) as gen, \
             patch("llm_client.active_provider_model", return_value="m"):
            ai_fusion.fuse_with_ai("BTCUSDT", {"value": 0.4}, None, {"value": -0.6})
            second = ai_fusion.fuse_with_ai("BTCUSDT", {"value": 0.4}, None, {"value": -0.6})
        self.assertEqual(gen.call_count, 2)   # fusion + verify once, then cache
        self.assertEqual(second["data_verification"]["status"], "ok")


class EtfSnapshotHygieneTests(unittest.TestCase):
    """The vestigial-counts bug found in live prod data on 2026-07-17."""

    def _snapshot_etf(self, summary):
        import ai_fusion
        with patch("market_intel.get_etf_flows_payload", return_value={"summary": summary}):
            snap = ai_fusion.build_factor_snapshot("BTCUSDT", None, None, None)
        return snap.get("etf_flows")

    def test_zero_proxy_counts_are_not_passed_to_the_model(self):
        """direction:inflow beside net_score:0 is a contradiction that isn't real."""
        etf = self._snapshot_etf({"direction": "inflow", "source": "sosovalue",
                                  "tracked_count": 0, "inflow_count": 0,
                                  "outflow_count": 0, "net_score": 0,
                                  "btc": {"latest_net_inflow_usd": 79150023.0}})
        self.assertEqual(etf["direction"], "inflow")
        self.assertIn("btc", etf)
        for dead in ("tracked_count", "inflow_count", "outflow_count", "net_score"):
            self.assertNotIn(dead, etf)

    def test_real_counts_are_kept(self):
        etf = self._snapshot_etf({"direction": "inflow", "tracked_count": 3,
                                  "inflow_count": 2, "outflow_count": 1, "net_score": 2.9})
        self.assertEqual(etf["tracked_count"], 3)
        self.assertEqual(etf["net_score"], 2.9)


if __name__ == "__main__":
    unittest.main()
