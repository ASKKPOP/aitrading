"""Owner rule 2026-08-13 (STRONG, all trading orders): "Must be final
discussion for contract or order by sooppiy AI — NOT any programming
logic." / "by AI it is main — programming decision is optional."

A cheap-tier fleet cycle may PROPOSE an order; the full 4-analyst +
trader discussion is the FINAL AUTHOR. The panel's decision replaces the
proposal wholesale — code convenes the meeting, never arbitrates it.
Holds convene nothing (no order to author); fail-OPEN on panel
infrastructure errors (an LLM hiccup must not freeze the book).
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import run_engine


def _analysis(action="buy", confidence=0.7):
    return {"decision": {"action": action, "confidence": confidence,
                         "entry": 100.0},
            "analysts": {},
            "position_state": "BRIEF_TEXT\n"}


_RUN = {"id": 7, "agent_id": 1, "symbol": "MSFT", "market": "us-stock",
        "market_type": "spot"}


class OrderDiscussionTests(unittest.TestCase):
    def _events(self):
        return self.events

    def setUp(self):
        self.events = []
        self.emit = patch.object(
            run_engine, "emit_telemetry_event",
            side_effect=lambda rid, et, payload: self.events.append(
                (et, payload)))
        self.emit.start()
        self.held = patch.object(run_engine, "_position_quantity",
                                 return_value=0.0)
        self.held.start()

    def tearDown(self):
        self.emit.stop()
        self.held.stop()

    def test_the_panel_reviews_the_motion_but_cannot_veto_it(self):
        """Owner 2026-09-05: "if continue hold then we will be remove desk
        hold logic".

        Measured on the live tape since 2026-09-04: the desk proposed an
        entry 435 times (367 buys, 67 sells) and the panel answered `hold`
        on 434 of them. One survived. Meanwhile the risk gates refused
        exactly ONE order in 625 decisions. The wall was here, and nowhere
        else. The panel still meets, still reviews, still may substitute
        its own order or tighten the bracket — it may no longer answer a
        motion to trade with "no trade"."""
        panel = {"decision": {"action": "hold", "confidence": 0.55,
                              "report": "a chase, not a thesis"},
                 "analysts": {"news": {"data": {}}}}
        with patch("analysis_agents.run_analysis",
                   return_value=panel) as ra:
            out = run_engine._order_discussion(_RUN, {}, _analysis("buy"))
        self.assertEqual(out["decision"]["action"], "buy",
                         "the panel vetoed an entry it was only meant to "
                         "review")
        self.assertEqual(out["decision"]["confidence"], 0.7,
                         "the desk's own confidence must carry the order — "
                         "taking the panel's just moves the veto into the "
                         "confidence gate")
        self.assertEqual(out["decision"]["escalated_from"],
                         {"action": "buy", "confidence": 0.7})
        self.assertIn("chase", out["decision"]["panel_review"],
                      "the panel's reasoning must survive on the record")
        self.assertEqual(ra.call_count, 1)
        self.assertEqual(ra.call_args.kwargs.get("position_state"),
                         "BRIEF_TEXT\n")
        et, payload = self.events[0]
        self.assertEqual(et, "order_discussion")
        self.assertEqual(payload["panel_verdict"], "hold")
        self.assertTrue(payload["veto_overridden"])
        self.assertEqual(payload["final"]["action"], "buy")

    def test_the_old_veto_is_one_env_flag_away(self):
        """PANEL_ORDER_VETO=1 restores the pre-2026-09-05 behaviour
        exactly, so the change is reversible without a deploy."""
        import os
        panel = {"decision": {"action": "hold", "confidence": 0.55},
                 "analysts": {}}
        os.environ["PANEL_ORDER_VETO"] = "1"
        try:
            with patch("analysis_agents.run_analysis", return_value=panel):
                out = run_engine._order_discussion(_RUN, {}, _analysis("buy"))
        finally:
            os.environ.pop("PANEL_ORDER_VETO", None)
        self.assertEqual(out["decision"]["action"], "hold")

    def test_a_panel_that_authors_a_DIFFERENT_order_is_honoured(self):
        """Substituting an order is not vetoing one. Only `hold` is
        overridden — a panel that turns a buy into a sell has authored its
        own order and that verdict stands untouched."""
        panel = {"decision": {"action": "sell", "confidence": 0.66},
                 "analysts": {}}
        with patch("analysis_agents.run_analysis", return_value=panel):
            out = run_engine._order_discussion(_RUN, {}, _analysis("buy"))
        self.assertEqual(out["decision"]["action"], "sell")
        self.assertEqual(out["decision"]["confidence"], 0.66)

    def _with_order(self, action, order, confidence=0.7):
        a = _analysis(action, confidence)
        a["decision"]["order"] = dict(order)
        return a

    def test_the_panel_may_still_TIGHTEN_the_bracket(self):
        """It loses the veto, not its risk voice.

        Uses the `order` block, which is the shape production actually
        emits — `_parse_decision_json` keeps stop_pct/target_pct only in
        there. An earlier version of this test asserted top-level keys that
        can never occur, so it certified the tighten path while exercising
        nothing (adversarial review 2026-09-05)."""
        panel = {"decision": {"action": "hold", "confidence": 0.4,
                              "order": {"size_frac": 0.10, "stop_pct": 1.2}},
                 "analysts": {}}
        with patch("analysis_agents.run_analysis", return_value=panel):
            out = run_engine._order_discussion(
                _RUN, {}, self._with_order("buy", {"size_frac": 0.25,
                                                   "stop_pct": 2.0}))
        self.assertEqual(out["decision"]["action"], "buy")
        self.assertEqual(out["decision"]["order"]["size_frac"], 0.10)
        self.assertEqual(out["decision"]["order"]["stop_pct"], 1.2)

    def test_the_panel_may_NOT_loosen_the_bracket(self):
        """The 16x hole. A hold-voting panel returning a bigger size and a
        wider stop was adopted wholesale — 4x size at 4x stop distance, with
        numbers authored by the voice that said don't trade. Only strictly
        smaller values are taken now."""
        panel = {"decision": {"action": "hold", "confidence": 0.4,
                              "order": {"size_frac": 1.0, "leverage": 10,
                                        "stop_pct": 25.0}},
                 "analysts": {}}
        with patch("analysis_agents.run_analysis", return_value=panel):
            out = run_engine._order_discussion(
                _RUN, {}, self._with_order("buy", {"size_frac": 0.25,
                                                   "leverage": 1,
                                                   "stop_pct": 2.0}))
        o = out["decision"]["order"]
        self.assertEqual(o["size_frac"], 0.25, "the panel upsized the order")
        self.assertEqual(o["leverage"], 1, "the panel raised leverage")
        self.assertEqual(o["stop_pct"], 2.0, "the panel widened the stop")

    def test_a_defer_hold_cannot_discard_the_desks_sizing(self):
        """`{"defer": true}` is not a bracket. It used to pass the
        `is not None` check and replace the desk's whole block with house
        defaults."""
        panel = {"decision": {"action": "hold", "order": {"defer": True}},
                 "analysts": {}}
        with patch("analysis_agents.run_analysis", return_value=panel):
            out = run_engine._order_discussion(
                _RUN, {}, self._with_order("buy", {"size_frac": 0.25,
                                                   "stop_pct": 2.0}))
        self.assertEqual(out["decision"]["order"]["size_frac"], 0.25)
        self.assertEqual(out["decision"]["order"]["stop_pct"], 2.0)

    def test_a_missing_desk_value_is_never_filled_in_by_a_hold(self):
        panel = {"decision": {"action": "hold",
                              "order": {"size_frac": 0.9}}, "analysts": {}}
        with patch("analysis_agents.run_analysis", return_value=panel):
            out = run_engine._order_discussion(
                _RUN, {}, self._with_order("buy", {"stop_pct": 2.0}))
        self.assertNotIn("size_frac", out["decision"]["order"])

    def test_the_override_does_not_mutate_the_callers_decision(self):
        """Defensive copy. `kept = proposal` (alias) survived a mutation
        run — it would edit the caller's dict in place."""
        a = self._with_order("buy", {"size_frac": 0.25})
        original = dict(a["decision"])
        panel = {"decision": {"action": "hold", "report": "no"},
                 "analysts": {}}
        with patch("analysis_agents.run_analysis", return_value=panel):
            run_engine._order_discussion(_RUN, {}, a)
        self.assertNotIn("panel_review", a["decision"],
                         "the override mutated the caller's decision dict")
        self.assertEqual(a["decision"]["action"], original["action"])

    def test_the_panels_objection_is_kept_on_the_tape(self):
        """`panel_reason` is the audit record F-VETO is judged on. It
        survived a mutation run unpinned."""
        panel = {"decision": {"action": "hold",
                              "report": "a chase, not a thesis"},
                 "analysts": {}}
        with patch("analysis_agents.run_analysis", return_value=panel):
            run_engine._order_discussion(_RUN, {}, _analysis("buy"))
        _, payload = self.events[0]
        self.assertIn("chase", payload["panel_reason"])

    def test_a_panel_hold_on_an_EXIT_is_also_overridden(self):
        """SCOPE, previously unstated (adversarial review 2026-09-05): the
        condition is on the VERDICT, not the proposal, so desk sells on a
        held book and retires are overridden too. That is the protective
        direction — the platform does not second-guess a reduction, and a
        panel able to veto an exit could trap a losing book — but it must
        be pinned, and it is why the flag is PANEL_ORDER_VETO."""
        self.held.stop()
        self.held = patch.object(run_engine, "_position_quantity",
                                 return_value=4.0)
        self.held.start()
        panel = {"decision": {"action": "hold", "confidence": 0.5},
                 "analysts": {}}
        with patch("analysis_agents.run_analysis", return_value=panel):
            out = run_engine._order_discussion(_RUN, {}, _analysis("sell"))
        self.assertEqual(out["decision"]["action"], "sell",
                         "the panel vetoed the desk's own exit")

    def test_agreeing_panel_still_authors_the_final_decision(self):
        panel = {"decision": {"action": "buy", "confidence": 0.81},
                 "analysts": {}}
        with patch("analysis_agents.run_analysis", return_value=panel):
            out = run_engine._order_discussion(_RUN, {}, _analysis("buy", 0.6))
        self.assertEqual(out["decision"]["action"], "buy")
        self.assertEqual(out["decision"]["confidence"], 0.81,
                         "the panel's own confidence governs the gates")

    def test_holds_convene_no_meeting(self):
        with patch("analysis_agents.run_analysis") as ra:
            out = run_engine._order_discussion(_RUN, {}, _analysis("hold"))
        ra.assert_not_called()
        self.assertEqual(out["decision"]["action"], "hold")
        self.assertEqual(self.events, [])

    def test_desk_exit_is_an_order_and_gets_the_discussion(self):
        # ALL trading orders (owner): a desk sell on a held book escalates
        # too — only protective rails executing pre-authored brackets stay
        # immediate.
        self.held.stop()
        self.held = patch.object(run_engine, "_position_quantity",
                                 return_value=3.5)
        self.held.start()
        panel = {"decision": {"action": "sell", "confidence": 0.7},
                 "analysts": {}}
        with patch("analysis_agents.run_analysis", return_value=panel) as ra:
            run_engine._order_discussion(_RUN, {}, _analysis("sell"))
        self.assertEqual(ra.call_count, 1)

    def test_retire_with_flat_book_convenes_nothing(self):
        with patch("analysis_agents.run_analysis") as ra:
            run_engine._order_discussion(_RUN, {}, _analysis("retire"))
        ra.assert_not_called()

    def test_rule_fallback_final_is_not_the_AI_and_fails_open(self):
        # Owner policy 2026-07-31: a user without Settings-page AI gets a
        # rule-engine trader fallback (decided_by='rule', hold 0.5). That is
        # programming, not the sooppiy AI — it must NOT overrule the cheap
        # tier's genuine AI verdict (live 2026-08-13: every fleet 32/33
        # discussion flat-lined to hold 0.5, silently blocking even desk
        # EXITS for those fleets).
        panel = {"decision": {"action": "hold", "confidence": 0.5,
                              "decided_by": "rule",
                              "fallback_reason": "no llm provider configured"},
                 "analysts": {}}
        with patch("analysis_agents.run_analysis", return_value=panel):
            out = run_engine._order_discussion(_RUN, {}, _analysis("sell"))
        self.assertEqual(out["decision"]["action"], "sell",
                         "a rule fallback must not overrule the AI proposal")
        et, payload = self.events[0]
        self.assertEqual(et, "order_discussion")
        self.assertIn("no llm provider configured", payload["error"])

    def test_panel_error_fails_open_and_journals(self):
        with patch("analysis_agents.run_analysis",
                   side_effect=RuntimeError("llm down")):
            out = run_engine._order_discussion(_RUN, {}, _analysis("buy"))
        self.assertEqual(out["decision"]["action"], "buy",
                         "an infra error must not freeze the book")
        et, payload = self.events[0]
        self.assertEqual(et, "order_discussion")
        self.assertIn("llm down", payload["error"])

    def test_kill_switch(self):
        import os
        with patch.dict(os.environ, {"ORDER_DISCUSSION": "0"}):
            self.assertFalse(run_engine._order_discussion_enabled())
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ORDER_DISCUSSION", None)
            self.assertTrue(run_engine._order_discussion_enabled())

    def test_the_hook_is_actually_WIRED_into_run_cycle(self):
        import inspect
        src = inspect.getsource(run_engine.run_cycle)
        self.assertIn("_order_discussion(run, cfg, analysis)", src,
                      "order discussion is not wired into the cycle")
        self.assertIn("_order_discussion_enabled()", src)


if __name__ == "__main__":
    unittest.main()


class PanelLocalFallbackTests(unittest.TestCase):
    """Owner order 2026-08-25 ("solve claude and local AI"): when the
    CONFIGURED provider's meeting fails on infrastructure (a dead SDK, a
    timeout, unparseable output), the panel retries ONCE on the platform's
    local AI so the order still gets a genuine AI review — ~15h of a dead
    Anthropic SDK passed every proposal through fail-open, and 100% of that
    window's realized loss entered through unreviewed orders. The 2026-07-31
    policy stands untouched: a user with NO configured AI gets no borrowed
    default — their rule fallback fails open exactly as before."""

    def setUp(self):
        self.events = []
        self.emit = patch.object(
            run_engine, "emit_telemetry_event",
            side_effect=lambda rid, et, payload: self.events.append(
                (et, payload)))
        self.emit.start()
        self.held = patch.object(run_engine, "_position_quantity",
                                 return_value=0.0)
        self.held.start()

    def tearDown(self):
        self.emit.stop()
        self.held.stop()

    @staticmethod
    def _infra_rule_panel():
        return {"decision": {"action": "hold", "confidence": 0.5,
                             "decided_by": "rule",
                             "fallback_reason": "no llm response"},
                "analysts": {}}

    @staticmethod
    def _local_panel(action="hold", confidence=0.62):
        return {"decision": {"action": action, "confidence": confidence},
                "analysts": {}}

    def test_infra_failure_convenes_the_local_panel(self):
        calls = []

        def fake(*a, **kw):
            calls.append(kw.get("provider"))
            if kw.get("provider") == "local":
                return self._local_panel("hold", 0.62)
            return self._infra_rule_panel()

        with patch("analysis_agents.run_analysis", side_effect=fake):
            out = run_engine._order_discussion(_RUN, {}, _analysis("buy"))
        self.assertEqual(calls, [None, "local"])
        # The local panel IS a panel, so it reviews and it does NOT veto
        # (owner 2026-09-05). The escalation still happened and is still
        # attributed — only the cancellation is gone.
        self.assertEqual(out["decision"]["action"], "buy",
                         "the local fallback panel vetoed an entry")
        et, payload = self.events[0]
        self.assertEqual(payload["reviewed_by"], "local-fallback")
        self.assertEqual(payload["panel_verdict"], "hold")
        self.assertTrue(payload["veto_overridden"])

    def test_exception_failure_also_convenes_the_local_panel(self):
        calls = []

        def fake(*a, **kw):
            calls.append(kw.get("provider"))
            if kw.get("provider") == "local":
                return self._local_panel("buy", 0.71)
            raise RuntimeError("anthropic sdk exploded")

        with patch("analysis_agents.run_analysis", side_effect=fake):
            out = run_engine._order_discussion(_RUN, {}, _analysis("buy"))
        self.assertEqual(calls, [None, "local"])
        self.assertEqual(out["decision"]["confidence"], 0.71)

    def test_no_provider_user_never_borrows_the_local_default(self):
        # 2026-07-31 policy: rule fallback for a user with no Settings AI
        # fails open with NO local retry.
        panel = {"decision": {"action": "hold", "confidence": 0.5,
                              "decided_by": "rule",
                              "fallback_reason":
                                  "no llm provider configured"},
                 "analysts": {}}
        with patch("analysis_agents.run_analysis",
                   return_value=panel) as ra:
            out = run_engine._order_discussion(_RUN, {}, _analysis("sell"))
        self.assertEqual(ra.call_count, 1)
        self.assertEqual(out["decision"]["action"], "sell")

    def test_local_also_failing_fails_open_with_both_errors(self):
        with patch("analysis_agents.run_analysis",
                   side_effect=RuntimeError("llm down")) as ra:
            out = run_engine._order_discussion(_RUN, {}, _analysis("buy"))
        self.assertEqual(ra.call_count, 2)
        self.assertEqual(out["decision"]["action"], "buy")
        et, payload = self.events[0]
        self.assertIn("llm down", payload["error"])

    def test_kill_switch_restores_single_attempt(self):
        import os
        with patch.dict(os.environ, {"PANEL_LOCAL_FALLBACK": "0"}):
            with patch("analysis_agents.run_analysis",
                       side_effect=RuntimeError("llm down")) as ra:
                out = run_engine._order_discussion(_RUN, {},
                                                   _analysis("buy"))
        self.assertEqual(ra.call_count, 1)
        self.assertEqual(out["decision"]["action"], "buy")

    def test_a_local_first_config_never_retries_itself(self):
        with patch("analysis_agents.run_analysis",
                   side_effect=RuntimeError("ollama down")) as ra:
            out = run_engine._order_discussion(
                _RUN, {"provider": "local"}, _analysis("buy"))
        self.assertEqual(ra.call_count, 1)
        self.assertEqual(out["decision"]["action"], "buy")
