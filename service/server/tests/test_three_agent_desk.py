"""Three-agent desk discussion (owner 2026-09-02: "Sooppiy Desk always
discusses with 3 agents"): the TRADER proposes, a RISK agent challenges,
a CHAIR authors the final — on BOTH tiers. Fail-open everywhere: LLM
trouble leaves the trader's decision standing."""
from __future__ import annotations

import inspect
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import analysis_agents
import run_engine

_RUN = {"symbol": "NVDA", "market": "us-stock"}
_TRADER = {"action": "buy", "confidence": 0.66, "stop_pct": 3.0,
           "target_pct": 7.0, "report": "trader says buy",
           "scores": {"thesis_alignment": 0.7}}


def _fake_llm(replies):
    """generate_text stub returning canned replies in order."""
    it = iter(replies)

    def _fn(prompt, **kw):
        r = next(it)
        if isinstance(r, Exception):
            raise r
        return r
    return _fn


class LightTierDiscussion(unittest.TestCase):
    def setUp(self):
        # conftest turns the discussion off for stage-isolation tests;
        # THIS file is the discussion's own suite.
        os.environ["DESK_THREE_AGENT"] = "1"

    def tearDown(self):
        os.environ["DESK_THREE_AGENT"] = "0"

    def test_default_on_and_kill_switch(self):
        # The PRODUCTION default (no env set) is ON.
        os.environ.pop("DESK_THREE_AGENT", None)
        self.assertTrue(run_engine._three_agent_enabled())
        self.assertTrue(analysis_agents._chair_enabled())
        os.environ["DESK_THREE_AGENT"] = "0"
        self.assertFalse(run_engine._three_agent_enabled())
        self.assertFalse(analysis_agents._chair_enabled())

    def test_chair_adopt_keeps_the_trader_verdict(self):
        replies = [json.dumps({"verdict": "agree", "challenge": "none"}),
                   json.dumps({"final": "adopt"})]
        with patch("llm_client.generate_text", _fake_llm(replies)):
            final, rec = run_engine._three_agent_light_discussion(
                _RUN, dict(_TRADER), can_sell=False, pos_qty=0.0, entry=100.0)
        self.assertEqual(final["action"], "buy")
        self.assertEqual(final["confidence"], 0.66)
        self.assertEqual(rec["chair"], "adopt")
        self.assertEqual(rec["risk"]["verdict"], "agree")

    def test_chair_amend_overlays_only_allowed_fields(self):
        replies = [json.dumps({"verdict": "reject",
                               "challenge": "entry is chasing"}),
                   json.dumps({"final": "amend", "action": "hold",
                               "confidence": 0.4,
                               "report": "chair: wait for a pullback"})]
        with patch("llm_client.generate_text", _fake_llm(replies)):
            final, rec = run_engine._three_agent_light_discussion(
                _RUN, dict(_TRADER), can_sell=False, pos_qty=0.0, entry=100.0)
        self.assertEqual(final["action"], "hold")
        self.assertEqual(final["confidence"], 0.4)
        self.assertEqual(final["report"], "chair: wait for a pullback")
        # untouched trader keys survive
        self.assertEqual(final["scores"], _TRADER["scores"])
        self.assertIn("action", rec["chair"]["amended"])

    def test_chair_cannot_use_a_verb_the_trader_was_not_offered(self):
        # Flat spot book: 'sell' was never on the menu — the chair may not
        # introduce it (the 33-refused-sells lesson applies to every agent).
        replies = [json.dumps({"verdict": "reject", "challenge": "bearish"}),
                   json.dumps({"final": "amend", "action": "sell"})]
        with patch("llm_client.generate_text", _fake_llm(replies)):
            final, _rec = run_engine._three_agent_light_discussion(
                _RUN, dict(_TRADER), can_sell=False, pos_qty=0.0, entry=100.0)
        self.assertEqual(final["action"], "buy")   # trader's verb stands

    def test_fail_open_on_chair_infrastructure_error(self):
        replies = [json.dumps({"verdict": "agree", "challenge": "ok"}),
                   RuntimeError("provider down")]
        with patch("llm_client.generate_text", _fake_llm(replies)):
            final, rec = run_engine._three_agent_light_discussion(
                _RUN, dict(_TRADER), can_sell=False, pos_qty=0.0, entry=100.0)
        self.assertEqual(final, _TRADER)           # proposal stands
        self.assertIn("error", rec["chair"])

    def test_fail_open_on_risk_error_still_asks_the_chair(self):
        replies = [RuntimeError("risk agent down"),
                   json.dumps({"final": "adopt"})]
        with patch("llm_client.generate_text", _fake_llm(replies)):
            final, rec = run_engine._three_agent_light_discussion(
                _RUN, dict(_TRADER), can_sell=False, pos_qty=0.0, entry=100.0)
        self.assertEqual(final["action"], "buy")
        self.assertIn("error", rec["risk"])
        self.assertEqual(rec["chair"], "adopt")

    def test_action_amendment_kills_stale_intent_and_outlook(self):
        # Review finding 1 (CONFIRMED live-path trace): a surviving
        # order_intent compiles to an order verb under RUN_ORDER_INTENT=
        # apply and OVERRIDES the chair's ruling while dodging the order
        # panel. An amended action must take the trader's intent and plan
        # with it.
        trader = dict(_TRADER)
        trader["order_intent"] = {"intent": "close", "size_frac": 1.0}
        trader["outlook"] = {"bias": "long"}
        replies = [json.dumps({"verdict": "reject", "challenge": "trap"}),
                   json.dumps({"final": "amend", "action": "hold"})]
        with patch("llm_client.generate_text", _fake_llm(replies)):
            final, rec = run_engine._three_agent_light_discussion(
                _RUN, trader, can_sell=True, pos_qty=5.0, entry=100.0)
        self.assertEqual(final["action"], "hold")
        self.assertNotIn("order_intent", final)
        self.assertNotIn("outlook", final)
        self.assertEqual(sorted(rec["chair"]["dropped"]),
                         ["order_intent", "outlook"])

    def test_adopt_keeps_the_intent(self):
        trader = dict(_TRADER)
        trader["order_intent"] = {"intent": "close", "size_frac": 0.5}
        replies = [json.dumps({"verdict": "agree", "challenge": "ok"}),
                   json.dumps({"final": "adopt"})]
        with patch("llm_client.generate_text", _fake_llm(replies)):
            final, _rec = run_engine._three_agent_light_discussion(
                _RUN, trader, can_sell=True, pos_qty=5.0, entry=100.0)
        self.assertEqual(final["order_intent"], {"intent": "close",
                                                 "size_frac": 0.5})

    def test_empty_amend_is_journaled_as_an_empty_amend(self):
        # Review finding 5 (cosmetic): under-counting amendments.
        replies = [json.dumps({"verdict": "agree", "challenge": "ok"}),
                   json.dumps({"final": "amend"})]
        with patch("llm_client.generate_text", _fake_llm(replies)):
            final, rec = run_engine._three_agent_light_discussion(
                _RUN, dict(_TRADER), can_sell=False, pos_qty=0.0, entry=100.0)
        self.assertEqual(final["action"], "buy")
        self.assertEqual(rec["chair"], {"amended": []})

    def test_discussion_record_reaches_the_decision_event(self):
        # Review finding 4 (CONFIRMED): the first cut journaled nothing.
        src = Path(run_engine.__file__).read_text()
        self.assertIn('**({"discussion": _disc}', src)
        self.assertIn('**({"chair": _chair}', src)

    def test_lease_renewed_before_the_discussion(self):
        # Review finding 7: 1->3 sequential calls can outlive the claim.
        src = inspect.getsource(run_engine._light_analysis)
        self.assertLess(src.index("_renew_lease(run"),
                        src.index("_three_agent_light_discussion("))

    def test_light_path_is_wired(self):
        # Wiring proof (brief-line lesson): the hook must live inside
        # _light_analysis and the record must reach the decision dict.
        src = inspect.getsource(run_engine._light_analysis)
        self.assertIn("_three_agent_light_discussion(", src)
        self.assertIn('decision["discussion"]', src)


class FullTierChair(unittest.TestCase):
    def setUp(self):
        os.environ["DESK_THREE_AGENT"] = "1"

    def tearDown(self):
        os.environ["DESK_THREE_AGENT"] = "0"

    _DECISION = {"action": "buy", "confidence": 0.7, "report": "verified buy"}

    def test_adopt(self):
        with patch.object(analysis_agents, "generate_text",
                          _fake_llm([json.dumps({"final": "adopt"})])):
            out = analysis_agents._chair_final(
                "NVDA", "us-stock", dict(self._DECISION),
                {"verdict": "confirm"}, "en", can_sell=True)
        self.assertEqual(out["action"], "buy")
        self.assertEqual(out["chair"], "adopt")

    def test_amend_action_and_sell_gating(self):
        with patch.object(analysis_agents, "generate_text",
                          _fake_llm([json.dumps({"final": "amend",
                                                 "action": "sell",
                                                 "confidence": 0.55})])):
            out = analysis_agents._chair_final(
                "NVDA", "us-stock", dict(self._DECISION),
                {"verdict": "challenge"}, "en", can_sell=False)
        self.assertEqual(out["action"], "buy")      # sell not allowed
        self.assertEqual(out["confidence"], 0.55)   # confidence amended
        with patch.object(analysis_agents, "generate_text",
                          _fake_llm([json.dumps({"final": "amend",
                                                 "action": "sell"})])):
            out = analysis_agents._chair_final(
                "NVDA", "us-stock", dict(self._DECISION),
                {"verdict": "challenge"}, "en", can_sell=True)
        self.assertEqual(out["action"], "sell")     # allowed when can_sell

    def test_enforced_rejection_pins_the_chair_to_hold(self):
        # Review finding 2 (CONFIRMED): the chair must not resurrect an
        # action the verifier's enforce mode deterministically rejected.
        decision = {"action": "hold", "confidence": 0.2,
                    "report": "demoted by enforcement",
                    "verification": {"verdict": "rejected", "applied": True,
                                     "adjusted_confidence": 0.2}}
        with patch.object(analysis_agents, "generate_text",
                          _fake_llm([json.dumps({"final": "amend",
                                                 "action": "buy",
                                                 "confidence": 0.85})])):
            out = analysis_agents._chair_final(
                "NVDA", "us-stock", dict(decision),
                decision["verification"], "en", can_sell=True)
        self.assertEqual(out["action"], "hold")          # buy not allowed
        self.assertEqual(out["confidence"], 0.2)         # capped at adjusted

    def test_enforced_weakening_caps_chair_confidence(self):
        decision = {"action": "buy", "confidence": 0.4,
                    "report": "weakened",
                    "verification": {"verdict": "weakened", "applied": True,
                                     "adjusted_confidence": 0.4}}
        with patch.object(analysis_agents, "generate_text",
                          _fake_llm([json.dumps({"final": "amend",
                                                 "confidence": 0.9})])):
            out = analysis_agents._chair_final(
                "NVDA", "us-stock", dict(decision),
                decision["verification"], "en", can_sell=True)
        self.assertEqual(out["confidence"], 0.4)

    def test_full_tier_action_amendment_kills_stale_intent(self):
        decision = {"action": "sell", "confidence": 0.7, "report": "close it",
                    "order_intent": {"intent": "close", "size_frac": 1.0}}
        with patch.object(analysis_agents, "generate_text",
                          _fake_llm([json.dumps({"final": "amend",
                                                 "action": "hold"})])):
            out = analysis_agents._chair_final(
                "NVDA", "us-stock", dict(decision), None, "en", can_sell=True)
        self.assertEqual(out["action"], "hold")
        self.assertNotIn("order_intent", out)
        self.assertIn("order_intent", out["chair"]["dropped"])

    def test_unparseable_chair_leaves_decision_standing(self):
        with patch.object(analysis_agents, "generate_text",
                          _fake_llm(["not json at all"])):
            out = analysis_agents._chair_final(
                "NVDA", "us-stock", dict(self._DECISION),
                None, "en", can_sell=True)
        self.assertEqual(out["action"], "buy")
        self.assertEqual(out["chair"], "unparseable")

    def test_full_pipeline_is_wired(self):
        src = inspect.getsource(analysis_agents._run_analysis_inner)
        self.assertIn("_chair_final(", src)
        self.assertIn("_chair_enabled()", src)


if __name__ == "__main__":
    unittest.main()
