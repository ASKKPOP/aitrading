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
