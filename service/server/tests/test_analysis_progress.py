"""Live pipeline progress (AI Analyst step monitoring).

run_analysis accepts a progress callback and emits paired start/done events for
every pipeline step; /api/analysis/run/stream forwards them as SSE and ends with
the final result. The step set and ordering constraints are what the AnalystPage
WebGL2 visualization depends on:

    gather:technical / gather:news / gather:fundamentals_macro   (concurrent)
    gather:sentiment                                             (after news)
    brief:news / brief:sentiment / brief:fundamentals_macro / brief:technical
    memory:recall                                                (desk memory)
    decision
    verify
    memory:write                                                 (desk memory)
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import analysis_agents
from routes import create_app

ALL_STEPS = {
    "gather:technical", "gather:news", "gather:fundamentals_macro", "gather:sentiment",
    "brief:news", "brief:sentiment", "brief:fundamentals_macro", "brief:technical",
    "memory:recall", "decision", "verify", "memory:write",
}


class RunAnalysisProgressTests(unittest.TestCase):

    def _run(self):
        events = []
        with patch.object(analysis_agents, "llm_configured", return_value=False), \
             patch.object(analysis_agents, "_gather_technical",
                          return_value={"current_price": 100.0, "signal": "buy",
                                        "signal_score": 4}), \
             patch.object(analysis_agents, "_gather_news",
                          return_value={"items": [], "sentiment_breakdown": {}, "count": 0}), \
             patch.object(analysis_agents, "_gather_fundamentals_macro",
                          return_value={"macro": {"verdict": "neutral"}}):
            result = analysis_agents.run_analysis(
                "BTC", "crypto", "en", None, None, progress=events.append)
        return events, result

    def test_every_step_emits_start_and_done(self):
        events, result = self._run()
        starts = {e["step"] for e in events if e["status"] == "start"}
        dones = {e["step"] for e in events if e["status"] == "done"}
        self.assertEqual(starts, ALL_STEPS)
        self.assertEqual(dones, ALL_STEPS)
        self.assertEqual(len(events), 2 * len(ALL_STEPS))
        # PRIMARY RULE (2026-07-27): with no LLM provider the engine still runs
        # every step and still reports — but the rule engine may not ORIGINATE
        # a position, so its "buy" signal is suppressed to hold. This asserted
        # "buy" before, which is precisely the behaviour the rule forbids.
        self.assertEqual(result["decision"]["action"], "hold")
        self.assertEqual(result["decision"]["rule_action_suppressed"], "buy")
        self.assertEqual(result["decision"]["decided_by"], "rule")

    def test_dependency_ordering(self):
        events, _ = self._run()
        idx = {(e["step"], e["status"]): i for i, e in enumerate(events)}
        # sentiment gathering needs the news breakdown
        self.assertGreater(idx[("gather:sentiment", "start")], idx[("gather:news", "done")])
        # the trader debate needs all four briefs and the recalled desk memory
        for role in ("news", "sentiment", "fundamentals_macro", "technical"):
            self.assertGreater(idx[("memory:recall", "start")], idx[(f"brief:{role}", "done")])
        self.assertGreater(idx[("decision", "start")], idx[("memory:recall", "done")])
        self.assertGreater(idx[("verify", "start")], idx[("decision", "done")])
        # what this run taught the desk is written back after verification
        self.assertGreater(idx[("memory:write", "start")], idx[("verify", "done")])

    def test_decision_and_verify_carry_details(self):
        events, _ = self._run()
        decision_done = next(e for e in events
                             if e["step"] == "decision" and e["status"] == "done")
        # Suppressed to hold by the AI-only-orders rule; see above.
        self.assertEqual(decision_done["action"], "hold")
        verify_done = next(e for e in events
                           if e["step"] == "verify" and e["status"] == "done")
        self.assertEqual(verify_done["verdict"], "skipped")  # no LLM -> verifier off

    def test_broken_progress_listener_does_not_break_analysis(self):
        def boom(_evt):
            raise RuntimeError("listener crashed")
        with patch.object(analysis_agents, "llm_configured", return_value=False), \
             patch.object(analysis_agents, "_gather_technical",
                          return_value={"current_price": 1.0, "signal": "hold"}), \
             patch.object(analysis_agents, "_gather_news",
                          return_value={"items": [], "sentiment_breakdown": {}}), \
             patch.object(analysis_agents, "_gather_fundamentals_macro",
                          return_value={}):
            result = analysis_agents.run_analysis(
                "BTC", "crypto", "en", None, None, progress=boom)
        self.assertIn(result["decision"]["action"], ("buy", "sell", "hold"))


class StreamEndpointTests(unittest.TestCase):

    def _stream_events(self, fake_agent):
        import routes_analysis

        def fake_run(symbol, market, lang, provider, agent_id, progress=None):
            progress({"step": "gather:news", "status": "start", "ts": "t0"})
            progress({"step": "gather:news", "status": "done", "ts": "t1"})
            return {"symbol": symbol, "market": market,
                    "decision": {"action": "hold", "confidence": 0.5},
                    "analysts": {}}

        app = create_app()
        with patch.object(routes_analysis, "_get_agent_by_token",
                          return_value=fake_agent), \
             patch.object(routes_analysis, "run_analysis", side_effect=fake_run):
            client = TestClient(app)
            with client.stream("POST", "/api/analysis/run/stream",
                               json={"symbol": "BTC", "market": "crypto"},
                               headers={"Authorization": "Bearer x"}) as res:
                self.assertEqual(res.status_code, 200)
                self.assertTrue(res.headers["content-type"].startswith("text/event-stream"))
                lines = [ln for ln in res.iter_lines() if ln.startswith("data: ")]
        return [json.loads(ln[6:]) for ln in lines]

    def test_streams_steps_then_result(self):
        payloads = self._stream_events({"id": 1, "name": "tester"})
        kinds = [p["event"] for p in payloads]
        self.assertEqual(kinds, ["step", "step", "result"])
        self.assertEqual(payloads[0]["step"], "gather:news")
        self.assertEqual(payloads[-1]["result"]["requested_by"], "tester")

    def test_pipeline_error_becomes_error_event(self):
        import routes_analysis

        app = create_app()
        with patch.object(routes_analysis, "_get_agent_by_token",
                          return_value={"id": 1, "name": "tester"}), \
             patch.object(routes_analysis, "run_analysis",
                          side_effect=RuntimeError("boom")):
            client = TestClient(app)
            with client.stream("POST", "/api/analysis/run/stream",
                               json={"symbol": "BTC", "market": "crypto"},
                               headers={"Authorization": "Bearer x"}) as res:
                lines = [ln for ln in res.iter_lines() if ln.startswith("data: ")]
        payloads = [json.loads(ln[6:]) for ln in lines]
        self.assertEqual(payloads[-1]["event"], "error")
        self.assertIn("boom", payloads[-1]["detail"])

    def test_provider_override_reaches_pipeline(self):
        """Automation test-runs post the rule's provider; it must reach run_analysis."""
        import routes_analysis

        seen = {}

        def fake_run(symbol, market, lang, provider, agent_id, progress=None):
            seen["provider"] = provider
            return {"symbol": symbol, "market": market,
                    "decision": {"action": "hold", "confidence": 0.5}, "analysts": {}}

        app = create_app()
        with patch.object(routes_analysis, "_get_agent_by_token",
                          return_value={"id": 1, "name": "tester"}), \
             patch.object(routes_analysis, "run_analysis", side_effect=fake_run):
            client = TestClient(app)
            with client.stream("POST", "/api/analysis/run/stream",
                               json={"symbol": "BTC", "market": "crypto",
                                     "provider": "gemini"},
                               headers={"Authorization": "Bearer x"}) as res:
                self.assertEqual(res.status_code, 200)
                list(res.iter_lines())
        self.assertEqual(seen["provider"], "gemini")

    def test_invalid_provider_rejected(self):
        import routes_analysis
        app = create_app()
        with patch.object(routes_analysis, "_get_agent_by_token",
                          return_value={"id": 1, "name": "tester"}):
            client = TestClient(app)
            res = client.post("/api/analysis/run/stream",
                              json={"symbol": "BTC", "market": "crypto",
                                    "provider": "not-a-provider"},
                              headers={"Authorization": "Bearer x"})
            self.assertEqual(res.status_code, 422)

    def test_requires_auth(self):
        import routes_analysis
        app = create_app()
        with patch.object(routes_analysis, "_get_agent_by_token", return_value=None):
            client = TestClient(app)
            res = client.post("/api/analysis/run/stream",
                              json={"symbol": "BTC", "market": "crypto"})
            self.assertEqual(res.status_code, 401)


if __name__ == "__main__":
    unittest.main()
