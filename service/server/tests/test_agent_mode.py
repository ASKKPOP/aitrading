"""Plan 06 C1 — Agent Mode: planner clamps, budget cap, journaling, routes."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
from routes import create_app

_NO_LLM_ENV = {k: "" for k in (
    "LLM_PROVIDER", "LLM_MODEL", "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY", "XAI_API_KEY", "GROK_API_KEY", "DASHSCOPE_API_KEY",
    "QWEN_API_KEY", "GLM_API_KEY", "ZHIPUAI_API_KEY", "OPENROUTER_API_KEY",
    "LOCAL_LLM_API_KEY",
)}


class AgentModeTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())
        resp = self.client.post(
            "/api/claw/agents/selfRegister",
            json={"name": "delegator", "password": "pw123", "initial_balance": 100000.0})
        assert resp.status_code == 200
        body = resp.json()
        self.agent_id = body["agent_id"]
        self.token = body["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def tearDown(self):
        self.tmp.cleanup()

    def _config(self, **overrides):
        base = {"id": 1, "agent_id": self.agent_id, "symbol": "AGENT", "market": "crypto",
                "mode": "agent", "budget_usd": 10000.0, "interval_minutes": 60,
                "min_confidence": 0.65, "size_usd": 500.0}
        base.update(overrides)
        return base


class PlannerClampTests(AgentModeTestCase):
    def test_llm_plan_is_clamped_to_bounds(self):
        import agent_planner
        wild = json.dumps({"symbol": "DOGEUSDT", "interval_minutes": 1,
                           "min_confidence": 0.1, "size_usd": 99999,
                           "risk_level": "yolo", "rationale": "moon"})
        with patch.object(agent_planner, "_gather_context",
                          return_value={"scanner_candidates": [], "budget_usd": 10000.0}), \
             patch("llm_client.llm_configured", return_value=True), \
             patch.object(agent_planner, "_parse_plan_json", side_effect=lambda t: json.loads(wild)), \
             patch("llm_client.generate_text", return_value=wild), \
             patch("llm_client.active_provider_model", return_value="claude-opus-4-8"):
            plan = agent_planner.plan_agent_cycle(self._config())
        # DOGEUSDT not in allowed universe -> first allowed symbol
        self.assertIn(plan["symbol"], ("BTCUSDT", "ETHUSDT", "SOLUSDT"))
        self.assertEqual(plan["interval_minutes"], 15)         # floor
        self.assertEqual(plan["min_confidence"], 0.55)         # floor
        self.assertEqual(plan["size_usd"], 2500.0)             # 25% of budget cap
        self.assertEqual(plan["risk_level"], "balanced")       # invalid -> default
        self.assertEqual(plan["planner"], "llm")

    def test_planner_prompt_carries_market_scoped_skills(self):
        # Research 04 wiring fix: skills_block("planner") without a market
        # silently excluded every market-scoped planner skill (e.g. the
        # crypto-only manipulated-book-hygiene judgment). The rule's market
        # must ride into the skills selection.
        import agent_planner
        seen = {}

        def fake_block(site, market=None):
            seen["args"] = (site, market)
            return ""
        wild = json.dumps({"symbol": "BTCUSDT", "interval_minutes": 60,
                           "min_confidence": 0.65, "size_usd": 500,
                           "risk_level": "balanced", "rationale": "ok"})
        with patch.object(agent_planner, "_gather_context",
                          return_value={"scanner_candidates": [],
                                        "budget_usd": 10000.0}), \
             patch("llm_client.llm_configured", return_value=True), \
             patch("trading_skills.skills_block", side_effect=fake_block), \
             patch("llm_client.generate_text", return_value=wild), \
             patch("llm_client.active_provider_model", return_value="m"):
            agent_planner.plan_agent_cycle(self._config())
        self.assertEqual(seen["args"], ("planner", "crypto"))

    def test_fallback_plan_without_llm(self):
        import agent_planner
        with patch.dict(os.environ, _NO_LLM_ENV), \
             patch.object(agent_planner, "_gather_context",
                          return_value={"scanner_candidates": [{"symbol": "SOLUSDT"}],
                                        "budget_usd": 10000.0}):
            plan = agent_planner.plan_agent_cycle(self._config())
        self.assertEqual(plan["planner"], "fallback")
        self.assertEqual(plan["symbol"], "SOLUSDT")  # scanner top candidate first
        self.assertLessEqual(plan["size_usd"], 2500.0)

    def test_top_symbols_universe_wins_over_scanner(self):
        """Plan 11 F1: a fully-delegated rule trades the market's top-5 by
        volume/popularity; scanner candidates are only the fallback."""
        import agent_planner
        allowed = agent_planner._allowed_symbols(
            [{"symbol": "SOLUSDT"}], ["KAITOUSDT", "ZECUSDT"])
        self.assertEqual(allowed[:2], ["KAITOUSDT", "ZECUSDT"])
        self.assertNotIn("SOLUSDT", allowed[:2])
        self.assertLessEqual(len(allowed), 5)
        # majors still pad the universe so a plan is always possible
        self.assertIn("BTCUSDT", allowed)

    def test_allowed_symbols_falls_back_when_top_symbols_unavailable(self):
        import agent_planner
        allowed = agent_planner._allowed_symbols([{"symbol": "SOLUSDT"}], [])
        self.assertEqual(allowed[0], "SOLUSDT")
        self.assertLessEqual(len(allowed), 5)

    def test_decisions_are_journaled(self):
        import agent_planner
        with patch.dict(os.environ, _NO_LLM_ENV), \
             patch.object(agent_planner, "_gather_context",
                          return_value={"scanner_candidates": [], "budget_usd": 10000.0}):
            agent_planner.plan_agent_cycle(self._config())
        rows = self.client.get("/api/automation/agent-decisions", headers=self.headers).json()
        self.assertEqual(len(rows["decisions"]), 1)
        d = rows["decisions"][0]
        self.assertEqual(d["planner"], "fallback")
        params = json.loads(d["params_json"])
        self.assertIn("symbol", params)


class BudgetCapTests(AgentModeTestCase):
    def _insert_position(self, symbol, qty, price):
        conn = database.get_db_connection()
        conn.execute(
            """INSERT INTO positions (agent_id, symbol, market, side, quantity,
               entry_price, current_price, opened_at)
               VALUES (?, ?, 'crypto', 'long', ?, ?, ?, '2026-07-01T00:00:00Z')""",
            (self.agent_id, symbol, qty, price, price))
        conn.commit()
        conn.close()

    def test_budget_blocks_when_exceeded(self):
        from agent_planner import budget_blocks
        self._insert_position("BTC", 1.0, 9000.0)   # $9k deployed of $10k budget
        reason = budget_blocks(self.agent_id, 10000.0, 2000.0)
        self.assertIsNotNone(reason)
        self.assertIn("agent-mode budget", reason)

    def test_budget_allows_within(self):
        from agent_planner import budget_blocks
        self._insert_position("BTC", 1.0, 5000.0)
        self.assertIsNone(budget_blocks(self.agent_id, 10000.0, 2000.0))
        self.assertIsNone(budget_blocks(self.agent_id, 0, 999999.0))  # 0 disables


class AgentModeRoutesTests(AgentModeTestCase):
    def test_agent_mode_requires_budget(self):
        resp = self.client.post("/api/automation/configs", headers=self.headers,
                                json={"symbol": "AGENT", "market": "crypto", "mode": "agent"})
        self.assertEqual(resp.status_code, 400)

    def test_agent_mode_forces_simulator_and_auto_execute(self):
        resp = self.client.post("/api/automation/configs", headers=self.headers,
                                json={"symbol": "AGENT", "market": "crypto", "mode": "agent",
                                      "budget_usd": 5000, "auto_execute": False,
                                      "account_type": "real"})
        self.assertEqual(resp.status_code, 200, resp.text)
        cfg = self.client.get("/api/automation/configs", headers=self.headers).json()["configs"][0]
        self.assertEqual(cfg["mode"], "agent")
        self.assertEqual(cfg["budget_usd"], 5000)
        self.assertEqual(cfg["auto_execute"], 1)
        self.assertEqual(cfg["account_type"], "simulator")

    def test_invalid_mode_and_budget_rejected(self):
        r1 = self.client.post("/api/automation/configs", headers=self.headers,
                              json={"symbol": "BTC", "mode": "autopilot"})
        self.assertEqual(r1.status_code, 422)
        r2 = self.client.post("/api/automation/configs", headers=self.headers,
                              json={"symbol": "AGENT", "mode": "agent", "budget_usd": 5})
        self.assertEqual(r2.status_code, 422)


class AgentModeRunTests(AgentModeTestCase):
    def test_run_rule_applies_plan_and_journals(self):
        import agent_planner
        import automation
        # Mirrors run_analysis: per-analyst payloads live under "analysts".
        fake_analysis = {"decision": {"action": "hold", "confidence": 0.6,
                                      "entry": 100.0, "report": "r"},
                         "analysts": {"technical": {"brief": "t", "data": {}}}}
        plan = {"symbol": "ETHUSDT", "interval_minutes": 30, "min_confidence": 0.7,
                "size_usd": 1000.0, "risk_level": "balanced",
                "rationale": "test", "planner": "llm"}
        resp = self.client.post("/api/automation/configs", headers=self.headers,
                                json={"symbol": "AGENT", "market": "crypto", "mode": "agent",
                                      "budget_usd": 8000})
        config_id = resp.json()["id"]
        conn = database.get_db_connection()
        cfg = dict(conn.execute("SELECT * FROM automation_configs WHERE id = ?",
                                (config_id,)).fetchone())
        conn.close()
        with patch.object(agent_planner, "plan_agent_cycle", return_value=plan) as mock_plan, \
             patch("analysis_agents.run_analysis", return_value=fake_analysis) as mock_analysis:
            result = automation.run_rule(cfg)
        mock_plan.assert_called_once()
        # analysis ran on the planner's symbol, not the stored placeholder
        self.assertEqual(mock_analysis.call_args[0][0], "ETHUSDT")
        self.assertEqual(result["agent_plan"]["symbol"], "ETHUSDT")
        # planner interval persisted for the due-checker
        conn = database.get_db_connection()
        row = conn.execute("SELECT interval_minutes FROM automation_configs WHERE id = ?",
                           (config_id,)).fetchone()
        conn.close()
        self.assertEqual(row["interval_minutes"], 30)


if __name__ == "__main__":
    unittest.main()
