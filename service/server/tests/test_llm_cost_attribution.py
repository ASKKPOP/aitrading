"""LLM spend must name the member it belongs to.

Measured on prod 2026-08-12: over 2026-07-26→30, 2716 of 4297 Anthropic calls
— $75.46 of $118.50, 64% of spend — landed in `llm_usage` with `user_id NULL`.
Every one of them was a daemon-side decision-tier call: the run cycle's route
verdict and light analysis (`run_engine`) and the thesis review
(`run_feedback.maybe_review_thesis`, invoked from inside the cycle).

The cause is not a missing column. `LlmContext` already carries user_id/agent_id
through a contextvar, and `analysis_agents.run_analysis` sets it — but
`run_engine.run_cycle` never did, so every LLM call it makes outside the analyst
pipeline was metered against nobody. The same class of bug was found and fixed
once before, on the verifier path (see the comment at analysis_agents.py:749).

Consequence: no per-member or per-tier spend cap can be built, because the
majority of spend cannot be attributed to a member. These tests pin the wiring
— that identity is *in force at the moment generate_text is called* — not the
rendering of any prompt.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
import run_engine
from routes import create_app


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class RunCycleAttributionTests(unittest.TestCase):
    """A cycle's LLM calls must be metered against the run's owning user."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        os.environ["AUTO_TRADING_ENABLED"] = "true"
        self.probe = patch("routes_runs._probe_price", return_value=100.0)
        self.probe.start()
        self.client = TestClient(create_app())
        resp = self.client.post(
            "/api/claw/agents/selfRegister",
            json={"name": "attr-agent", "password": "pw123",
                  "initial_balance": 100000.0})
        assert resp.status_code == 200, resp.text
        self.token = resp.json()["token"]
        self.agent_id = resp.json()["agent_id"]
        self.user_id = self._link_user()

    def tearDown(self):
        self.probe.stop()
        os.environ.pop("AUTO_TRADING_ENABLED", None)
        self.tmp.cleanup()

    def _link_user(self) -> int:
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            database.begin_write_transaction(cur)
            cur.execute("INSERT INTO users (email, password_hash, created_at) "
                        "VALUES ('attr@test.dev', 'x', ?)", (_ts(),))
            user_id = cur.lastrowid
            cur.execute("UPDATE agents SET user_id = ? WHERE id = ?",
                        (user_id, self.agent_id))
            conn.commit()
            return user_id
        finally:
            conn.close()

    def _light_run(self) -> int:
        h = {"Authorization": f"Bearer {self.token}"}
        run_id = self.client.post(
            "/api/runs", json={"symbol": "BTC", "market": "crypto",
                               "max_bet_usd": 500.0}, headers=h).json()["id"]
        assert self.client.post(f"/api/runs/{run_id}/start",
                                headers=h).status_code == 200
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT config_snapshot_json FROM trading_runs "
                        "WHERE id = ?", (run_id,))
            cfg = json.loads(cur.fetchone()["config_snapshot_json"] or "{}")
            cfg["cycle_mode"] = "light"
            cfg["thesis"] = {"direction": "long", "expected_move_pct": 2.0,
                             "invalidation": "below the recent range"}
            database.begin_write_transaction(cur)
            cur.execute("UPDATE trading_runs SET config_snapshot_json = ?, "
                        "created_via = 'fleet' WHERE id = ?",
                        (json.dumps(cfg), run_id))
            conn.commit()
        finally:
            conn.close()
        return run_id

    def _contexts_seen(self, run_id: int) -> list:
        """Every LlmContext in force across the cycle's generate_text calls."""
        from llm_client import current_llm_context
        seen = []

        def spy(prompt, **kw):
            seen.append(current_llm_context())
            return '{"action":"hold","confidence":0.5}'

        with patch("llm_client.generate_text", side_effect=spy), \
             patch("price_fetcher.get_price_from_market", return_value=100.0), \
             patch("price_fetcher.get_daily_candles", return_value=[]):
            run_engine.run_cycle(run_id)
        return seen

    def test_cycle_llm_calls_name_the_owning_user(self):
        seen = self._contexts_seen(self._light_run())
        self.assertTrue(seen, "the cycle made no LLM call — harness broke")
        for ctx in seen:
            self.assertIsNotNone(
                ctx, "generate_text ran with no LlmContext at all — the "
                     "llm_usage row lands with user_id NULL")
            self.assertEqual(ctx.user_id, self.user_id)

    def test_cycle_llm_calls_name_the_agent(self):
        """agent_id too — per-run attribution, not just per-member totals."""
        seen = self._contexts_seen(self._light_run())
        self.assertTrue(seen)
        for ctx in seen:
            self.assertIsNotNone(ctx)
            self.assertEqual(ctx.agent_id, self.agent_id)

    def test_ownerless_agent_still_records_the_agent(self):
        """A self-registered (claw) agent has no member. That is a legitimate
        None user_id — but the agent_id must still be recorded, or the spend is
        untraceable rather than merely unbilled."""
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            database.begin_write_transaction(cur)
            cur.execute("UPDATE agents SET user_id = NULL WHERE id = ?",
                        (self.agent_id,))
            conn.commit()
        finally:
            conn.close()
        seen = self._contexts_seen(self._light_run())
        self.assertTrue(seen)
        for ctx in seen:
            self.assertIsNotNone(ctx)
            self.assertIsNone(ctx.user_id)
            self.assertEqual(ctx.agent_id, self.agent_id)


class UsageRowAttributionTests(RunCycleAttributionTests):
    """End-to-end through the REAL resolve_provider — the test #395 lacked.

    The tests above assert the context in force at call time, and every one of
    them patches `generate_text`. That is exactly how #395 shipped green and
    still silenced the desk: naming the member made `resolve_provider` return
    None, and no test ever ran it.

    Here only the provider TRANSPORT is patched. `resolve_provider`,
    `_record_usage` and the whole resolution chain run for real, off
    `LLM_PROVIDER=local` — the "default local AI by system .env setting" of the
    2026-08-12 owner policy. So this fails if naming the member ever again
    changes WHETHER an LLM is called, not just whose row it lands on.
    """

    def setUp(self):
        super().setUp()
        self._saved_provider = os.environ.get("LLM_PROVIDER")
        os.environ["LLM_PROVIDER"] = "local"

    def tearDown(self):
        if self._saved_provider is None:
            os.environ.pop("LLM_PROVIDER", None)
        else:
            os.environ["LLM_PROVIDER"] = self._saved_provider
        super().tearDown()

    def test_the_desk_still_calls_the_llm_when_the_member_is_named(self):
        """The #395 regression, at the level it actually broke: a cycle whose
        context names a member must still reach the model at all."""
        import llm_client
        run_id = self._light_run()
        with patch.object(llm_client, "_generate_openai_compatible",
                          return_value=('{"action":"hold","confidence":0.5}',
                                        (120, 40))) as transport, \
             patch("price_fetcher.get_price_from_market", return_value=100.0), \
             patch("price_fetcher.get_daily_candles", return_value=[]):
            run_engine.run_cycle(run_id)
        self.assertGreater(
            transport.call_count, 0,
            "the cycle made no LLM call at all — resolve_provider returned None "
            "for a context that names a member (the #395 desk-silence bug)")

    def test_llm_usage_row_carries_the_owning_user(self):
        import llm_client
        run_id = self._light_run()

        with patch.object(llm_client, "_generate_openai_compatible",
                          return_value=('{"action":"hold","confidence":0.5}',
                                        (120, 40))), \
             patch("price_fetcher.get_price_from_market", return_value=100.0), \
             patch("price_fetcher.get_daily_candles", return_value=[]):
            run_engine.run_cycle(run_id)

        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT user_id, agent_id, tier, prompt_tokens "
                        "FROM llm_usage ORDER BY id")
            rows = [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

        self.assertTrue(rows, "no llm_usage row was written — harness broke")
        orphaned = [r for r in rows if r["user_id"] is None]
        self.assertEqual(orphaned, [],
                         "these rows landed with user_id NULL — the exact"
                         "shape that made 64% of prod spend unattributable")
        for row in rows:
            self.assertEqual(row["user_id"], self.user_id)
            self.assertEqual(row["agent_id"], self.agent_id)


class PlannerAttributionTests(unittest.TestCase):
    """agent_planner.plan_agent_cycle is the other unattributed daemon path."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())
        resp = self.client.post(
            "/api/claw/agents/selfRegister",
            json={"name": "plan-agent", "password": "pw123",
                  "initial_balance": 100000.0})
        assert resp.status_code == 200, resp.text
        self.agent_id = resp.json()["agent_id"]
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            database.begin_write_transaction(cur)
            cur.execute("INSERT INTO users (email, password_hash, created_at) "
                        "VALUES ('planner@test.dev', 'x', ?)", (_ts(),))
            self.user_id = cur.lastrowid
            cur.execute("UPDATE agents SET user_id = ? WHERE id = ?",
                        (self.user_id, self.agent_id))
            conn.commit()
        finally:
            conn.close()

    def tearDown(self):
        self.tmp.cleanup()

    def test_planner_llm_call_names_the_owning_user(self):
        import agent_planner
        from llm_client import current_llm_context
        seen = []
        plan_json = json.dumps({"symbol": "BTCUSDT", "interval_minutes": 60,
                                "min_confidence": 0.65, "size_usd": 500,
                                "risk_level": "balanced", "rationale": "r"})

        def spy(prompt, **kw):
            seen.append(current_llm_context())
            return plan_json

        cfg = {"id": 1, "agent_id": self.agent_id, "symbol": "AGENT",
               "market": "crypto", "mode": "agent", "budget_usd": 10000.0,
               "interval_minutes": 60, "min_confidence": 0.65, "size_usd": 500.0}
        with patch.object(agent_planner, "_gather_context",
                          return_value={"scanner_candidates": [],
                                        "budget_usd": 10000.0}), \
             patch("llm_client.llm_configured", return_value=True), \
             patch("llm_client.generate_text", side_effect=spy), \
             patch("llm_client.active_provider_model", return_value="m"):
            agent_planner.plan_agent_cycle(cfg)

        self.assertEqual(len(seen), 1, "planner made no LLM call — harness broke")
        self.assertIsNotNone(seen[0], "planner ran with no LlmContext")
        self.assertEqual(seen[0].user_id, self.user_id)
        self.assertEqual(seen[0].agent_id, self.agent_id)

    def test_planner_context_is_released(self):
        """The context must not leak past the call — a daemon thread reused for
        another agent would otherwise bill this member for someone else."""
        import agent_planner
        from llm_client import current_llm_context
        plan_json = json.dumps({"symbol": "BTCUSDT", "interval_minutes": 60,
                                "min_confidence": 0.65, "size_usd": 500,
                                "risk_level": "balanced", "rationale": "r"})
        cfg = {"id": 1, "agent_id": self.agent_id, "symbol": "AGENT",
               "market": "crypto", "mode": "agent", "budget_usd": 10000.0,
               "interval_minutes": 60, "min_confidence": 0.65, "size_usd": 500.0}
        with patch.object(agent_planner, "_gather_context",
                          return_value={"scanner_candidates": [],
                                        "budget_usd": 10000.0}), \
             patch("llm_client.llm_configured", return_value=True), \
             patch("llm_client.generate_text", return_value=plan_json), \
             patch("llm_client.active_provider_model", return_value="m"):
            agent_planner.plan_agent_cycle(cfg)
        self.assertIsNone(current_llm_context())


if __name__ == "__main__":
    unittest.main()
