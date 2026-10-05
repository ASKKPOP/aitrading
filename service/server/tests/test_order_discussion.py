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

# The override path (a desk entry standing over the panel's hold) is opt-in
# since 2026-10-05. Tests of what that path does to the order — tightening,
# sizing, the objection on the tape — exercise it under its flag.
_ENTRY_OVERRIDE = patch.dict("os.environ", {"PANEL_ENTRY_OVERRIDE": "1"})


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

    def test_the_0905_entry_override_is_one_env_flag_away(self):
        """PANEL_ENTRY_OVERRIDE=1 restores the 2026-09-05 arrangement
        exactly; it stopped being the default on 2026-10-05 (see
        test_a_panel_hold_on_an_ENTRY_is_binding). Original reasoning kept:

        Owner 2026-09-05: "if continue hold then we will be remove desk
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
        with patch.dict("os.environ", {"PANEL_ENTRY_OVERRIDE": "1"}), \
             patch("analysis_agents.run_analysis",
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

    def test_a_panel_hold_on_an_ENTRY_is_binding(self):
        """Supersedes the 2026-09-05 default. That ship made the panel's
        hold on an entry advisory "to get the first real outcome data in 19
        days". The data, 09-05..10-05 on both owner accounts: the panel
        answered `hold` on 590 of 590 proposed buys and was overridden 590
        times; the 548 entries that followed netted -$67.26, and their
        timing was no better than a random minute in the same symbol at
        any horizon from 1h to 48h (n=632). An entry with no edge costs
        its fee. The hold is binding again."""
        panel = {"decision": {"action": "hold", "confidence": 0.55,
                              "report": "a chase, not a thesis"},
                 "analysts": {}}
        with patch("analysis_agents.run_analysis", return_value=panel):
            out = run_engine._order_discussion(_RUN, {}, _analysis("buy"))
        self.assertEqual(out["decision"]["action"], "hold",
                         "an entry stood over the panel's hold")
        self.assertEqual(out["decision"]["confidence"], 0.55)
        et, payload = self.events[0]
        self.assertEqual(et, "order_discussion")
        self.assertNotIn("veto_overridden", payload)
        self.assertEqual(payload["final"]["action"], "hold")

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

    @_ENTRY_OVERRIDE
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

    @_ENTRY_OVERRIDE
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

    @_ENTRY_OVERRIDE
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

    @_ENTRY_OVERRIDE
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

    @_ENTRY_OVERRIDE
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

    def test_an_EXIT_is_not_overridden_at_all_now(self):
        """Supersedes the size-preservation pin: exits no longer reach the
        override, so there is no sizing to preserve. `_tighter_order`'s
        reducing branch stays as defence against re-widening and keeps its
        own unit tests."""
        self.held.stop()
        self.held = patch.object(run_engine, "_position_quantity",
                                 return_value=4.0)
        self.held.start()
        panel = {"decision": {"action": "hold", "confidence": 0.5,
                              "order": {"size_frac": 0.3}}, "analysts": {}}
        with patch("analysis_agents.run_analysis", return_value=panel):
            out = run_engine._order_discussion(
                _RUN, {}, self._with_order("sell", {"size_frac": 1.0}))
        self.assertEqual(out["decision"]["action"], "hold")

    def test_an_overridden_ENTRY_still_takes_the_smaller_size(self):
        """The other half of the same wiring: on a flat book a sell is a
        SHORT ENTRY, so narrowing is correct there."""
        panel = {"decision": {"action": "hold",
                              "order": {"size_frac": 0.3}}, "analysts": {}}
        with patch("analysis_agents.run_analysis", return_value=panel):
            out = run_engine._order_discussion(
                _RUN, {}, self._with_order("sell", {"size_frac": 1.0}))
        self.assertEqual(out["decision"]["order"]["size_frac"], 0.3)

    def test_a_panel_hold_on_an_EXIT_now_STANDS(self):
        """REVERSED 2026-09-05 07:00Z by the tape.

        The exit-side override was kept deliberately at 06:00Z, reasoning
        that a panel able to veto an exit could trap a losing book. A revert
        condition was registered the same hour and the tape met it three
        times in fifty minutes — every overridden EXIT lost, and in each the
        panel had refuted the desk's stated premise against the tape:

            LTC   -0.2136  "LTC is technically stacked above MA20/50/200"
            ASTER -0.2742  "price 0.7298 holds cleanly above MA5/.../MA200"
            FIL   -0.2009  "closing the fresh long at a -0.17% wiggle"

        -$0.6887 over 3 of 3. An EXIT has a concrete factual premise the
        panel can check against the tape; an ENTRY is a forecast it cannot.
        Keep the veto where it catches false premises, remove it where it
        blocks."""
        self.held.stop()
        self.held = patch.object(run_engine, "_position_quantity",
                                 return_value=4.0)
        self.held.start()
        panel = {"decision": {"action": "hold", "confidence": 0.5},
                 "analysts": {}}
        with patch("analysis_agents.run_analysis", return_value=panel):
            out = run_engine._order_discussion(_RUN, {}, _analysis("sell"))
        self.assertEqual(out["decision"]["action"], "hold",
                         "the panel's exit veto was overridden again")
        _, payload = self.events[0]
        self.assertNotIn("veto_overridden", payload)

    def test_an_ENTRY_is_overridden_only_under_the_flag(self):
        """Was `test_an_ENTRY_is_still_overridden` ("the wall that mattered
        stays down"). Superseded 2026-10-05: the entries the wall had been
        stopping lost money once they were let through."""
        panel = {"decision": {"action": "hold", "confidence": 0.5},
                 "analysts": {}}
        with patch("analysis_agents.run_analysis", return_value=panel):
            out = run_engine._order_discussion(_RUN, {}, _analysis("buy"))
        self.assertEqual(out["decision"]["action"], "hold")
        self.assertNotIn("veto_overridden", self.events[0][1])
        self.events.clear()
        with patch.dict("os.environ", {"PANEL_ENTRY_OVERRIDE": "1"}), \
             patch("analysis_agents.run_analysis", return_value=panel):
            out = run_engine._order_discussion(_RUN, {}, _analysis("buy"))
        self.assertEqual(out["decision"]["action"], "buy")
        self.assertTrue(self.events[0][1]["veto_overridden"])

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
        self._hold(4.0)      # a desk EXIT is a sell on a HELD book
        with patch("analysis_agents.run_analysis", return_value=panel):
            out = run_engine._order_discussion(_RUN, {}, _analysis("sell"))
        self.assertEqual(out["decision"]["action"], "sell",
                         "a rule fallback must not overrule the AI proposal")
        et, payload = self.events[0]
        self.assertEqual(et, "order_discussion")
        self.assertIn("no llm provider configured", payload["error"])

    def _hold(self, qty):
        self.held.stop()
        self.held = patch.object(run_engine, "_position_quantity",
                                 return_value=qty)
        self.held.start()

    def test_panel_error_fails_open_for_the_book_and_journals(self):
        self._hold(4.0)
        with patch("analysis_agents.run_analysis",
                   side_effect=RuntimeError("llm down")):
            out = run_engine._order_discussion(_RUN, {}, _analysis("sell"))
        self.assertEqual(out["decision"]["action"], "sell",
                         "an infra error must not freeze the book")
        et, payload = self.events[0]
        self.assertEqual(et, "order_discussion")
        self.assertIn("llm down", payload["error"])
        self.assertNotIn("entry_held", payload)

    def test_a_short_cover_also_fails_open(self):
        # `buy` on a short book is the exit; the verb alone would hold it.
        self._hold(-4.0)
        with patch("analysis_agents.run_analysis",
                   side_effect=RuntimeError("llm down")):
            out = run_engine._order_discussion(_RUN, {}, _analysis("buy"))
        self.assertEqual(out["decision"]["action"], "buy")

    def test_an_ENTRY_the_panel_could_not_review_is_held(self):
        """Owner 2026-10-05. Fail-open is for the book. On an entry it is
        the override by another door: 2026-08-25, ~15h of a dead SDK passed
        every proposal through and all of that window's realized loss
        entered unreviewed; 09-11..10-05, 14 of 52 meetings ended in this
        branch, 8 of them buys."""
        proposal = _analysis("buy")
        proposal["decision"].update({
            "report": "breakout over 101",
            "order_intent": {"intent": "open", "size_frac": 0.25},
            "outlook": {"bias": "long"}, "scores": {"entry_quality": 0.7}})
        with patch("analysis_agents.run_analysis",
                   side_effect=RuntimeError("llm down")):
            out = run_engine._order_discussion(_RUN, {}, proposal)
        d = out["decision"]
        self.assertEqual(d["action"], "hold")
        # The desk's own confidence stays on the record. Zeroing it fed
        # `_recent_confidences`, which samples every decision agent-wide:
        # an outage's worth of 0.0s pulls the percentile gate to its floor
        # and admits afterwards what it refused before (review 2026-10-05).
        self.assertEqual(d["confidence"], 0.7)
        # code held it, and says so: the hold-streak and the stop router
        # both read this label as "nobody's verdict"
        self.assertEqual(d["decided_by"], "rule")
        self.assertEqual(d["fallback_reason"], "panel unavailable")
        self.assertEqual(d["escalated_from"],
                         {"action": "buy", "confidence": 0.7})
        # the entry verb's plan must not survive to compile into an order
        self.assertNotIn("order_intent", d)
        self.assertNotIn("outlook", d)
        self.assertEqual(d["scores"], {"entry_quality": 0.7})
        self.assertIn("breakout over 101", d["report"])
        self.assertEqual(out["position_state"], "BRIEF_TEXT\n")
        # the caller's proposal is not mutated
        self.assertEqual(proposal["decision"]["action"], "buy")
        self.assertIn("order_intent", proposal["decision"])
        _, payload = self.events[0]
        self.assertEqual(payload["entry_held"], "panel unavailable")
        self.assertEqual(payload["final"],
                         {"action": "hold", "confidence": 0.7})
        self.assertIn("llm down", payload["error"])

    def test_the_book_is_read_again_after_the_meeting(self):
        """Two panel attempts can take minutes of timeouts. A long the
        watcher closed meanwhile turns the desk's `sell` from an exit into
        an order on a flat book — on futures, a short nobody reviewed
        (reproduced through run_cycle, review 2026-10-05)."""
        self.held.stop()
        self.held = patch.object(run_engine, "_position_quantity",
                                 side_effect=[4.0, 0.0])
        self.held.start()
        with patch("analysis_agents.run_analysis",
                   side_effect=RuntimeError("llm down")):
            out = run_engine._order_discussion(_RUN, {}, _analysis("sell"))
        self.assertEqual(out["decision"]["action"], "hold")
        self.assertEqual(self.events[0][1]["entry_held"], "panel unavailable")
        # ...and a re-read that fails is an unreadable book: not held
        self.held.stop()
        self.held = patch.object(run_engine, "_position_quantity",
                                 side_effect=[0.0, RuntimeError("db down")])
        self.held.start()
        with patch("analysis_agents.run_analysis",
                   side_effect=RuntimeError("llm down")):
            out = run_engine._order_discussion(_RUN, {}, _analysis("buy"))
        self.assertEqual(out["decision"]["action"], "buy")

    def test_the_flag_and_an_unreadable_book_keep_fail_open(self):
        with patch.dict("os.environ", {"PANEL_ENTRY_OVERRIDE": "1"}), \
             patch("analysis_agents.run_analysis",
                   side_effect=RuntimeError("llm down")):
            out = run_engine._order_discussion(_RUN, {}, _analysis("buy"))
        self.assertEqual(out["decision"]["action"], "buy")
        # unknown is not flat: this may be an exit, and exits are not held
        self.held.stop()
        self.held = patch.object(run_engine, "_position_quantity",
                                 side_effect=RuntimeError("db down"))
        self.held.start()
        with patch("analysis_agents.run_analysis",
                   side_effect=RuntimeError("llm down")):
            out = run_engine._order_discussion(_RUN, {}, _analysis("sell"))
        self.assertEqual(out["decision"]["action"], "sell")

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
        # The local panel IS a panel: its hold on an entry binds like any
        # other panel's (2026-10-05; it was advisory from 09-05). The
        # escalation is still attributed.
        self.assertEqual(out["decision"]["action"], "hold",
                         "an entry stood over the local panel's hold")
        et, payload = self.events[0]
        self.assertEqual(payload["reviewed_by"], "local-fallback")
        self.assertNotIn("veto_overridden", payload)

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
        self.held.stop()     # a desk exit: sell on a HELD book
        self.held = patch.object(run_engine, "_position_quantity",
                                 return_value=4.0)
        self.held.start()
        with patch("analysis_agents.run_analysis",
                   return_value=panel) as ra:
            out = run_engine._order_discussion(_RUN, {}, _analysis("sell"))
        self.assertEqual(ra.call_count, 1)
        self.assertEqual(out["decision"]["action"], "sell")

    def test_local_also_failing_journals_both_errors(self):
        # Two panels tried, neither answered. The entry is held
        # (2026-10-05; it used to stand) — see
        # test_an_ENTRY_the_panel_could_not_review_is_held.
        with patch("analysis_agents.run_analysis",
                   side_effect=RuntimeError("llm down")) as ra:
            out = run_engine._order_discussion(_RUN, {}, _analysis("buy"))
        self.assertEqual(ra.call_count, 2)
        self.assertEqual(out["decision"]["action"], "hold")
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
        self.assertEqual(out["decision"]["action"], "hold")

    def test_a_local_first_config_never_retries_itself(self):
        with patch("analysis_agents.run_analysis",
                   side_effect=RuntimeError("ollama down")) as ra:
            out = run_engine._order_discussion(
                _RUN, {"provider": "local"}, _analysis("buy"))
        self.assertEqual(ra.call_count, 1)
        self.assertEqual(out["decision"]["action"], "hold")


class TighterOrderJunkTests(unittest.TestCase):
    """`_tighter_order` is fed an LLM's JSON. Measured 2026-09-05: before
    the positivity guard, 0, -1 and -5 were all adopted as "smaller".

    The zero case is the dangerous one and it is not a typo hazard, it is
    a correctness hazard: a panel that voted `hold` returning
    `size_frac: 0` cancels the order through its sizing — the veto
    reinstated through the back door, and INVISIBLE, because the ship would
    look like it worked while trading nothing."""

    DESK = {"size_frac": 0.25, "leverage": 1, "stop_pct": 2.0}

    def _t(self, panel):
        return run_engine._tighter_order(dict(self.DESK), panel)

    def test_zero_size_cannot_cancel_the_order(self):
        self.assertEqual(self._t({"size_frac": 0})["size_frac"], 0.25)

    def test_zero_leverage_is_refused(self):
        self.assertEqual(self._t({"leverage": 0})["leverage"], 1)

    def test_negative_values_are_refused(self):
        self.assertEqual(self._t({"stop_pct": -5})["stop_pct"], 2.0)
        self.assertEqual(self._t({"size_frac": -1})["size_frac"], 0.25)

    def test_junk_types_are_ignored_not_crashed(self):
        for junk in ({"size_frac": "lots"}, {"size_frac": {"a": 1}},
                     {"size_frac": None}, {"size_frac": float("nan")}):
            self.assertEqual(self._t(junk)["size_frac"], 0.25)

    def test_a_numeric_string_still_tightens(self):
        self.assertEqual(self._t({"size_frac": "0.10"})["size_frac"], 0.10)

    def test_a_genuine_tighten_still_applies(self):
        out = self._t({"size_frac": 0.10, "stop_pct": 1.2})
        self.assertEqual(out["size_frac"], 0.10)
        self.assertEqual(out["stop_pct"], 1.2)

    def test_no_panel_block_is_a_passthrough(self):
        self.assertEqual(run_engine._tighter_order(dict(self.DESK), None),
                         self.DESK)
        self.assertIsNone(run_engine._tighter_order(None, None))


class ReductionSizingTests(unittest.TestCase):
    """"Smaller is tighter" INVERTS on an exit.

    On a sell/cover/retire against a held book, size_frac is a fraction OF
    WHAT IS HELD. Measured 2026-09-05: desk proposes `sell size_frac 1.0`
    ("thesis broken, get out"), a panel that voted hold returns 0.3, and the
    order shipped 30% exited / 70% RETAINED — the veto reinstated through
    sizing, on the very path kept open so a panel could not trap a losing
    book."""

    def test_a_hold_cannot_shrink_an_exit(self):
        out = run_engine._tighter_order({"size_frac": 1.0, "stop_pct": 2.0},
                                        {"size_frac": 0.3, "stop_pct": 1.0},
                                        reducing=True)
        self.assertEqual(out["size_frac"], 1.0,
                         "the panel kept 70% of a book the desk exited")
        self.assertEqual(out["stop_pct"], 1.0,
                         "stop_pct does not invert and must still tighten")

    def test_but_it_still_shrinks_an_ENTRY(self):
        out = run_engine._tighter_order({"size_frac": 1.0},
                                        {"size_frac": 0.3}, reducing=False)
        self.assertEqual(out["size_frac"], 0.3)

    def test_target_is_never_taken_from_a_hold(self):
        """Stated invariant with nothing enforcing it (review 2026-09-05):
        a smaller target is not less risk, it is less reward, and the R:R
        ceiling already re-derives it downstream."""
        out = run_engine._tighter_order({"target_pct": 6.0},
                                        {"target_pct": 0.5})
        self.assertEqual(out["target_pct"], 6.0)

    def test_a_panel_block_cannot_be_adopted_when_the_desk_named_none(self):
        """The `{"defer": true}` hole in another shape."""
        out = run_engine._tighter_order(None, {"size_frac": 0.9,
                                               "stop_pct": 1.0})
        self.assertIsNone(out)
        out2 = run_engine._tighter_order({}, {"size_frac": 0.9})
        self.assertIsNone(out2)


class ShortBookReductionTests(unittest.TestCase):
    """The mirror of the long-exit defect (review 2026-09-05).

    `run_cycle` maps the desk's verb for futures books — buy -> cover when
    the position is short — but that mapping runs AFTER the panel. So a
    proposal to CLOSE a short still reads `buy` at panel time, and a
    verb-only predicate classified it as risk-increasing. Measured
    end-to-end on a crypto futures short: desk size_frac 1.0 (close the
    whole short) shipped 0.3 — 70% of the short retained by a panel that
    voted hold."""

    def setUp(self):
        self.events = []
        self.emit = patch.object(
            run_engine, "emit_telemetry_event",
            side_effect=lambda rid, et, p: self.events.append((et, p)))
        self.emit.start()

    def tearDown(self):
        self.emit.stop()

    def _drive(self, action, held, desk_size=1.0, panel_size=0.3):
        run = {"id": 9, "agent_id": 1, "symbol": "ETHUSDT",
               "market": "crypto", "market_type": "futures"}
        a = {"decision": {"action": action, "confidence": 0.7,
                          "entry": 100.0,
                          "order": {"size_frac": desk_size}},
             "analysts": {}, "position_state": ""}
        panel = {"decision": {"action": "hold", "confidence": 0.4,
                              "order": {"size_frac": panel_size}},
                 "analysts": {}}
        with patch.object(run_engine, "_position_quantity", return_value=held), \
             patch("analysis_agents.run_analysis", return_value=panel):
            out = run_engine._order_discussion(run, {}, a)
        return out.get("decision") or {}

    def test_a_buy_that_CLOSES_a_short_is_not_overridden(self):
        """The sign-aware predicate now decides WHETHER the override
        applies, not how the order is sized."""
        self.assertEqual(self._drive("buy", -100.0)["action"], "hold",
                         "the panel's exit veto was overridden again")

    @_ENTRY_OVERRIDE
    def test_a_sell_that_ADDS_to_a_short_is_still_narrowed(self):
        """The opposite mis-classification from the same root: selling
        into a short increases exposure, so the panel keeps its voice."""
        d = self._drive("sell", -100.0)
        self.assertEqual(d["action"], "sell", "an ADD is an entry and must "
                         "still override")
        self.assertEqual(d["order"]["size_frac"], 0.3)

    def test_a_sell_that_CLOSES_a_long_is_not_overridden(self):
        self.assertEqual(self._drive("sell", 100.0)["action"], "hold")

    @_ENTRY_OVERRIDE
    def test_a_buy_that_ADDS_to_a_long_is_still_narrowed(self):
        d = self._drive("buy", 100.0)
        self.assertEqual(d["action"], "buy")
        self.assertEqual(d["order"]["size_frac"], 0.3)

    def test_target_is_never_taken_on_a_REDUCTION_either(self):
        """The docstring states it unconditionally; it was pinned only on
        the entry path (the reducing-path mutation survived)."""
        out = run_engine._tighter_order({"target_pct": 6.0},
                                        {"target_pct": 0.5}, reducing=True)
        self.assertEqual(out["target_pct"], 6.0)


class RoutedStopHitExemption(unittest.TestCase):
    """A desk ruling on its OWN breached stop is never vetoable.

    `stop_router` dispatches a run precisely so the desk rules on a stop hit
    in a normal cycle. Letting the panel veto that is the SOL 1274 family and
    worse than the original: there the ruling died at a gate, no decision
    landed, and the 180s fail-safe still dumped the book. Here a `hold` LANDS,
    so run_cycle calls `stop_router.clear(run_id)` — "a desk decision cycle
    ran, its verdict governs" — cancelling the fail-safe and suppressing
    re-noting for 30 minutes. The position rides past its own price stop with
    the watcher switched off.

    Costs the exit-veto revert nothing: none of LTC/ASTER/FIL was a stop hit;
    all three were discretionary exits."""

    def setUp(self):
        self.events = []
        self.emit = patch.object(
            run_engine, "emit_telemetry_event",
            side_effect=lambda rid, et, p: self.events.append((et, p)))
        self.emit.start()
        self.held = patch.object(run_engine, "_position_quantity",
                                 return_value=4.0)
        self.held.start()

    def tearDown(self):
        self.emit.stop()
        self.held.stop()

    def _drive(self, stop_pending):
        import stop_router
        panel = {"decision": {"action": "hold", "confidence": 0.5},
                 "analysts": {}}
        with patch.object(stop_router, "enabled", lambda: True), \
             patch.object(stop_router, "pending",
                          lambda rid: {"reason": "stop"} if stop_pending else None), \
             patch("analysis_agents.run_analysis", return_value=panel):
            out = run_engine._order_discussion(_RUN, {}, _analysis("sell"))
        return out["decision"]["action"]

    def test_a_stop_hit_ruling_survives_the_panel(self):
        self.assertEqual(self._drive(stop_pending=True), "sell",
                         "the panel vetoed the desk's ruling on its own "
                         "breached stop, cancelling the fail-safe with it")

    def test_a_DISCRETIONARY_exit_is_still_vetoable(self):
        """The three losses that justified the revert were all this shape."""
        self.assertEqual(self._drive(stop_pending=False), "hold")

    def test_the_stop_hit_override_is_journaled(self):
        # The action alone cannot pin the exemption: the substitution guard
        # restores the desk's verb even with the exemption removed. The
        # record of WHY it stood can.
        self._drive(stop_pending=True)
        _, payload = self.events[0]
        self.assertEqual(payload["panel_verdict"], "hold")
        self.assertTrue(payload["veto_overridden"])

    def _drive_entry(self, held, action, pending_fn):
        import stop_router
        self.held.stop()
        self.held = patch.object(run_engine, "_position_quantity",
                                 return_value=held)
        self.held.start()
        panel = {"decision": {"action": "hold", "confidence": 0.5},
                 "analysts": {}}
        with patch.object(stop_router, "enabled", lambda: True), \
             patch.object(stop_router, "pending", pending_fn), \
             patch("analysis_agents.run_analysis", return_value=panel):
            out = run_engine._order_discussion(_RUN, {}, _analysis(action))
        return out["decision"]["action"]

    def test_a_stop_hit_does_not_carry_an_ENTRY_past_the_panel(self):
        """The exemption protects the desk's ruling on its own breached
        stop — a reduction. It was keyed on the stop flag alone, so three
        entries rode it over a panel hold (adversarial review 2026-10-05):
        an add to the long that just breached, a buy on a flat book with a
        stale flag, and a buy when the router itself raised."""
        def hit(rid):
            return {"reason": "stop"}

        def boom(rid):
            raise RuntimeError("router down")

        self.assertEqual(self._drive_entry(4.0, "buy", hit), "hold",
                         "an add stood over the panel on a stop hit")
        self.assertEqual(self._drive_entry(0.0, "buy", hit), "hold",
                         "a stale stop flag carried a fresh entry")
        self.assertEqual(self._drive_entry(0.0, "buy", boom), "hold",
                         "a broken router carried a fresh entry")

    def test_an_unreadable_book_keeps_the_stop_ruling(self):
        # A failed position lookup reads as flat, and "flat + sell" is not a
        # reduction — so a real stop ruling lost its exemption (round 2).
        # Unknown is not flat: on a stop hit the desk's ruling stands.
        def hit(rid):
            return {"reason": "stop"}
        self.held.stop()
        self.held = patch.object(run_engine, "_position_quantity",
                                 side_effect=RuntimeError("db down"))
        self.held.start()
        import stop_router
        panel = {"decision": {"action": "hold", "confidence": 0.5},
                 "analysts": {}}
        with patch.object(stop_router, "enabled", lambda: True), \
             patch.object(stop_router, "pending", hit), \
             patch("analysis_agents.run_analysis", return_value=panel):
            out = run_engine._order_discussion(_RUN, {}, _analysis("sell"))
        self.assertEqual(out["decision"]["action"], "sell")

    def test_the_entry_flag_does_not_reopen_the_EXIT_veto(self):
        # PANEL_ENTRY_OVERRIDE=1 restores 09-05 for entries only; the
        # discretionary-exit veto (LTC / ASTER / FIL) stays.
        with patch.dict("os.environ", {"PANEL_ENTRY_OVERRIDE": "1"}):
            self.assertEqual(self._drive(stop_pending=False), "hold")

    def test_a_broken_router_fails_toward_the_desks_ruling(self):
        import stop_router
        panel = {"decision": {"action": "hold", "confidence": 0.5},
                 "analysts": {}}
        def boom(rid):
            raise RuntimeError("router down")
        with patch.object(stop_router, "pending", boom), \
             patch("analysis_agents.run_analysis", return_value=panel):
            out = run_engine._order_discussion(_RUN, {}, _analysis("sell"))
        self.assertEqual(out["decision"]["action"], "sell")


class StopHitSubstitutionRefused(unittest.TestCase):
    """On a routed stop hit the desk's ruling stands against a panel
    SUBSTITUTION too, not only against a veto.

    Desk `sell` -> panel `buy` would ADD to a position that just breached its
    own stop, and `stop_router.clear` would then cancel the fail-safe on it.
    Substituting an order is normally not vetoing one and is honoured — but
    on a stop hit the desk is ruling on its own breached level under a
    fail-safe clock, the one population where this codebase has already paid
    2x for letting anything but the desk's ruling govern (SOL 1274)."""

    def setUp(self):
        self.events = []
        self.emit = patch.object(
            run_engine, "emit_telemetry_event",
            side_effect=lambda rid, et, p: self.events.append((et, p)))
        self.emit.start()
        self.held = patch.object(run_engine, "_position_quantity",
                                 return_value=4.0)
        self.held.start()

    def tearDown(self):
        self.emit.stop()
        self.held.stop()

    def _drive(self, panel_action, stop_pending=True, enabled=True):
        import stop_router
        panel = {"decision": {"action": panel_action, "confidence": 0.6},
                 "analysts": {}}
        with patch.object(stop_router, "enabled", lambda: enabled), \
             patch.object(stop_router, "pending",
                          lambda rid: {"r": 1} if stop_pending else None), \
             patch("analysis_agents.run_analysis", return_value=panel):
            out = run_engine._order_discussion(_RUN, {}, _analysis("sell"))
        return out["decision"]

    def test_a_panel_buy_cannot_replace_the_desks_stop_exit(self):
        d = self._drive("buy")
        self.assertEqual(d["action"], "sell",
                         "the panel added to a position that had just "
                         "breached its own stop")
        _, payload = self.events[0]
        self.assertEqual(payload["panel_substitution_refused"], "buy")

    def test_an_AGREEING_panel_is_untouched(self):
        self.assertEqual(self._drive("sell")["action"], "sell")

    def test_substitution_is_still_honoured_WITHOUT_a_stop_hit(self):
        """Only the stop-hit population is protected; ordinary substitution
        remains the panel's prerogative."""
        d = self._drive("buy", stop_pending=False)
        self.assertEqual(d["action"], "buy")

    def test_a_DISABLED_router_does_not_grant_the_exemption(self):
        """A stale _PENDING left over from when the router was enabled must
        not exempt anything once STOP_ROUTER is off (review survivor)."""
        d = self._drive("hold", stop_pending=True, enabled=False)
        self.assertEqual(d["action"], "hold",
                         "a disabled router still granted the exemption")
