"""Routing decided by the desk, not by a trigger count (2026-07-27).

`route = "full" if triggers else "light"` treats every trigger as decisive.
Two of them — psych_shock and hot_issue — are MARKET-WIDE flags that stay on
for long stretches, so in prod 85% of cycles took the six-call path against a
15-20% design target. The routing saving was not reduced, it was inverted.

Which combination of ambient and specific signals genuinely warrants the desk
is exactly the judgement no threshold table can hold, so the desk decides —
with the deterministic answer as the fallback, because routing must never
break a cycle.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import run_engine

RUN = {"id": 1, "symbol": "ETHUSDT", "market": "crypto",
       "stop_conditions_json": "{}"}


class AiRoutingTests(unittest.TestCase):
    def tearDown(self):
        os.environ.pop("RUN_AI_ROUTING", None)

    def test_enabled_by_default(self):
        self.assertTrue(run_engine._ai_routing_enabled())

    def test_quiet_cycles_never_call_the_model(self):
        """No triggers means light regardless — spending a call to confirm
        silence would defeat the entire point.

        The trigger sources are patched OFF rather than left to the
        environment. This test asserted "no triggers means light" while only
        ever checking "the environment happens to be quiet": on 2026-08-07 it
        began failing because `active_event_window()` was genuinely true (a
        macro release window), so `full` was CORRECT and the test was wrong.
        A test that fails during every macro event window teaches people to
        ignore failures."""
        called = []
        with patch("llm_client.generate_text", side_effect=lambda *a, **k: called.append(1)), \
             patch("market_events.active_event_window", return_value=None), \
             patch("regime.current_regime_state", return_value=None), \
             patch("hot_issue_daemon.recent_hot_issue", return_value=False):
            out = run_engine._classify_situation({**RUN, "market": "us-stock"}, {})
        self.assertEqual(out["triggers"], [], "the test environment supplied a "
                                              "trigger; this test must control "
                                              "its own inputs")
        self.assertEqual(out["route"], "light")
        self.assertEqual(called, [], "a quiet cycle must cost nothing")

    def test_a_real_trigger_still_routes_full(self):
        """The mirror of the above: with a live event window the route MUST be
        full. Without this, patching the triggers off could hide a regression
        that makes everything light."""
        with patch("market_events.active_event_window",
                   return_value={"event": "CPI"}), \
             patch("regime.current_regime_state", return_value=None), \
             patch("hot_issue_daemon.recent_hot_issue", return_value=False):
            out = run_engine._classify_situation({**RUN, "market": "us-stock"}, {})
        self.assertIn("event_window", out["triggers"])
        self.assertEqual(out["route"], "full")

    def test_desk_can_downgrade_ambient_triggers_to_light(self):
        """The prod failure: market-wide flags forcing the six-call path on a
        flat book with nothing specific to the symbol."""
        with patch("llm_client.llm_configured", return_value=True), \
             patch("llm_client.generate_text",
                   return_value='{"route":"light","why":"ambient market-wide flags only"}'):
            r = run_engine._ai_route_verdict(RUN, {}, ["psych_shock", "hot_issue"])
        self.assertEqual(r[0], "light")
        self.assertIn("ambient", r[1])

    def test_desk_can_still_escalate(self):
        with patch("llm_client.llm_configured", return_value=True), \
             patch("llm_client.generate_text",
                   return_value='{"route":"full","why":"position near its stop"}'):
            r = run_engine._ai_route_verdict(RUN, {}, ["near_stop"])
        self.assertEqual(r[0], "full")

    def test_the_prompt_names_which_signals_are_ambient(self):
        """Without that context the model cannot tell a standing market-wide
        flag from a fresh event."""
        seen = {}
        def cap(prompt, **kw):
            seen["p"] = prompt
            return '{"route":"light","why":"x"}'
        with patch("llm_client.llm_configured", return_value=True), \
             patch("llm_client.generate_text", side_effect=cap):
            run_engine._ai_route_verdict(RUN, {}, ["psych_shock"])
        self.assertIn("MARKET-WIDE", seen["p"])
        self.assertIn("near_stop", seen["p"])

    def test_routing_stays_cheap(self):
        """This exists to avoid six calls; it must not become a seventh."""
        seen = {}
        def cap(prompt, **kw):
            seen.update(kw)
            return '{"route":"light","why":"x"}'
        with patch("llm_client.llm_configured", return_value=True), \
             patch("llm_client.generate_text", side_effect=cap):
            run_engine._ai_route_verdict(RUN, {}, ["psych_shock"])
        self.assertLessEqual(seen.get("max_tokens", 9999), 100)

    # ── every failure degrades to the deterministic answer ──────────────

    def test_no_provider_falls_back(self):
        with patch("llm_client.llm_configured", return_value=False):
            self.assertIsNone(run_engine._ai_route_verdict(RUN, {}, ["psych_shock"]))

    def test_unparseable_answer_falls_back(self):
        for reply in ("", "no json", '{"route":"teleport"}', '{"why":"x"}'):
            with patch("llm_client.llm_configured", return_value=True), \
                 patch("llm_client.generate_text", return_value=reply):
                self.assertIsNone(
                    run_engine._ai_route_verdict(RUN, {}, ["psych_shock"]), reply)

    def test_a_raising_model_falls_back_not_crashes(self):
        with patch("llm_client.llm_configured", return_value=True), \
             patch("llm_client.generate_text", side_effect=RuntimeError("boom")):
            self.assertIsNone(run_engine._ai_route_verdict(RUN, {}, ["psych_shock"]))

    def test_kill_switch_restores_any_trigger_means_full(self):
        """llm_configured must be patched TRUE here: without it the AI path
        bails on its own and the test passes even when the kill switch is
        ignored — which is exactly how it survived a mutation."""
        os.environ["RUN_AI_ROUTING"] = "false"
        called = []
        def cap(*a, **k):
            called.append(1)
            return '{"route":"light","why":"x"}'
        with patch("market_events.active_event_window", return_value=True), \
             patch("llm_client.llm_configured", return_value=True), \
             patch("llm_client.generate_text", side_effect=cap):
            out = run_engine._classify_situation({**RUN, "market": "us-stock"}, {})
        self.assertEqual(out["route"], "full", "kill switch must force the rule route")
        self.assertEqual(called, [], "kill switch must not spend a call")
        self.assertNotEqual(out.get("route_by"), "ai")

    def test_the_journal_records_who_routed_and_why(self):
        """A route the desk chose and one the rule chose must be tellable
        apart, or the 85%-full finding could never have been made."""
        with patch("market_events.active_event_window", return_value=True), \
             patch("llm_client.llm_configured", return_value=True), \
             patch("llm_client.generate_text",
                   return_value='{"route":"light","why":"stale window, flat book"}'):
            out = run_engine._classify_situation({**RUN, "market": "us-stock"}, {})
        self.assertEqual(out["route"], "light")
        self.assertEqual(out["route_by"], "ai")
        self.assertEqual(out["rule_route"], "full")
        self.assertIn("stale", out["route_why"])

    def test_fallback_is_labelled_as_rule(self):
        with patch("market_events.active_event_window", return_value=True), \
             patch("llm_client.llm_configured", return_value=False):
            out = run_engine._classify_situation({**RUN, "market": "us-stock"}, {})
        self.assertEqual(out["route"], "full")
        self.assertEqual(out["route_by"], "rule")


if __name__ == "__main__":
    unittest.main()
