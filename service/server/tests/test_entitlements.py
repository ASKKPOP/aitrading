"""Entitlements + safety rails (Plan 10, Phase 5) — verification gates.

Covers: PLAN_LIMITS enforcement at run start (unlinked agent, no plan,
concurrent cap, max-bet cap), the automation-API bypass rejection at BOTH
doors (create + in-loop gate), subscription-lapse pause, the infeasible
auto-pause, agent-delete cascade of the new tables, and the daily LLM tick
budget pre-gate. Enforcement is env-gated (ENTITLEMENTS_ENFORCED).
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
import run_engine
import trading_runs
from routes import create_app


def _ts(offset_seconds: float = 0) -> str:
    return (datetime.now(timezone.utc)
            + timedelta(seconds=offset_seconds)).strftime(trading_runs.TS_FMT)


class EntitlementTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        os.environ["AUTO_TRADING_ENABLED"] = "true"
        os.environ["ENTITLEMENTS_ENFORCED"] = "true"
        self.probe = patch("routes_runs._probe_price", return_value=100.0)
        self.probe.start()
        self.client = TestClient(create_app())
        resp = self.client.post(
            "/api/claw/agents/selfRegister",
            json={"name": "ent-agent", "password": "pw123",
                  "initial_balance": 100000.0})
        self.token = resp.json()["token"]
        self.agent_id = resp.json()["agent_id"]

    def tearDown(self):
        self.probe.stop()
        os.environ.pop("AUTO_TRADING_ENABLED", None)
        os.environ.pop("ENTITLEMENTS_ENFORCED", None)
        self.tmp.cleanup()

    def _h(self):
        return {"Authorization": f"Bearer {self.token}"}

    def _link_user(self):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            database.begin_write_transaction(cur)
            cur.execute("INSERT INTO users (email, password_hash, created_at) "
                        "VALUES ('ent@test.dev', 'x', ?)", (_ts(),))
            user_id = cur.lastrowid
            cur.execute("UPDATE agents SET user_id = ? WHERE id = ?",
                        (user_id, self.agent_id))
            conn.commit()
            return user_id
        finally:
            conn.close()

    def _draft(self, **overrides):
        payload = {"symbol": "BTC", "market": "crypto", "max_bet_usd": 500.0}
        payload.update(overrides)
        return self.client.post("/api/runs", json=payload,
                                headers=self._h()).json()["id"]

    # ── run-start gates ────────────────────────────────────────────────

    def test_unlinked_agent_cannot_start_run(self):
        run_id = self._draft()
        resp = self.client.post(f"/api/runs/{run_id}/start", headers=self._h())
        self.assertEqual(resp.status_code, 403)
        self.assertIn("linked to a user", resp.json()["detail"])

    def test_linked_user_without_plan_cannot_start(self):
        self._link_user()
        run_id = self._draft()
        resp = self.client.post(f"/api/runs/{run_id}/start", headers=self._h())
        self.assertEqual(resp.status_code, 403)
        self.assertIn("subscription", resp.json()["detail"])

    def test_plan_caps_concurrent_runs_and_max_bet(self):
        self._link_user()
        with patch("entitlements.plan_code_for_user", return_value="junior"):
            # junior placeholder: 1 run, max bet $100
            over_bet = self._draft(max_bet_usd=500.0)
            resp = self.client.post(f"/api/runs/{over_bet}/start", headers=self._h())
            self.assertEqual(resp.status_code, 403)
            self.assertIn("caps max bet", resp.json()["detail"])

            ok_run = self._draft(max_bet_usd=50.0)
            resp = self.client.post(f"/api/runs/{ok_run}/start", headers=self._h())
            self.assertEqual(resp.status_code, 200, resp.text)

            second = self._draft(symbol="ETH", max_bet_usd=50.0)
            resp = self.client.post(f"/api/runs/{second}/start", headers=self._h())
            self.assertEqual(resp.status_code, 403)
            self.assertIn("concurrent", resp.json()["detail"])

    def test_enforcement_off_means_no_gates(self):
        os.environ["ENTITLEMENTS_ENFORCED"] = "false"
        run_id = self._draft()
        resp = self.client.post(f"/api/runs/{run_id}/start", headers=self._h())
        self.assertEqual(resp.status_code, 200, resp.text)

    # ── automation bypass closed at both doors ─────────────────────────

    def test_automation_create_rejects_auto_execute_without_plan(self):
        resp = self.client.post(
            "/api/automation/configs",
            json={"symbol": "BTC", "market": "crypto", "auto_execute": True,
                  "size_usd": 100.0},
            headers=self._h())
        self.assertEqual(resp.status_code, 403)
        # analysis-only rules stay allowed
        resp = self.client.post(
            "/api/automation/configs",
            json={"symbol": "BTC", "market": "crypto", "auto_execute": False,
                  "size_usd": 100.0},
            headers=self._h())
        self.assertEqual(resp.status_code, 200, resp.text)
        # ...and cannot be flipped to auto-execute via update
        config_id = resp.json()["id"]
        resp = self.client.put(
            f"/api/automation/configs/{config_id}",
            json={"symbol": "BTC", "market": "crypto", "auto_execute": True,
                  "size_usd": 100.0},
            headers=self._h())
        self.assertEqual(resp.status_code, 403)

    def test_automation_in_loop_gate_blocks_lapsed_rules(self):
        from automation import evaluate_execution_gates
        config = {"auto_execute": 1, "account_type": "simulator",
                  "min_confidence": 0.5, "size_usd": 100.0}
        out = evaluate_execution_gates(config, self.agent_id, "BTC", "crypto",
                                       "buy", 0.9, 100.0, None,
                                       {"sigma_daily_pct": 2.0})
        self.assertIsNotNone(out["skip_reason"])
        self.assertIn("user account", out["skip_reason"])

    # ── lapse enforcement + LLM budget ─────────────────────────────────

    def test_subscription_enforcer_pauses_lapsed_running_run(self):
        self._link_user()
        with patch("entitlements.plan_code_for_user", return_value="pro"):
            run_id = self._draft()
            resp = self.client.post(f"/api/runs/{run_id}/start", headers=self._h())
            self.assertEqual(resp.status_code, 200, resp.text)
        out = run_engine.subscription_enforcer_tick()  # plan now unresolvable
        self.assertEqual(out["paused"], 1)
        run = trading_runs.get_run(run_id, self.agent_id)
        self.assertEqual(run["status"], "paused")
        self.assertEqual(run["paused_reason"], "subscription_lapsed")

    def test_llm_tick_budget_pre_gate(self):
        self._link_user()
        with patch("entitlements.plan_code_for_user", return_value="junior"):
            run_id = self._draft(max_bet_usd=50.0)
            self.client.post(f"/api/runs/{run_id}/start", headers=self._h())
            # exhaust the junior budget with synthetic decision events
            conn = database.get_db_connection()
            try:
                cur = conn.cursor()
                database.begin_write_transaction(cur)
                for i in range(100):
                    cur.execute(
                        """INSERT INTO run_events (run_id, seq, event_type, ts,
                           payload) VALUES (?, ?, 'decision', ?, '{}')""",
                        (run_id, i + 100, _ts()))
                conn.commit()
            finally:
                conn.close()
            with patch("analysis_agents.run_analysis") as analysis:
                result = run_engine.run_cycle(run_id)
            analysis.assert_not_called()
            self.assertIn("budget exhausted", result["skip_reason"])

    # ── infeasible auto-pause + agent lifecycle ────────────────────────

    def test_infeasible_skips_auto_pause(self):
        os.environ["ENTITLEMENTS_ENFORCED"] = "false"
        run_id = self._draft()
        self.client.post(f"/api/runs/{run_id}/start", headers=self._h())
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            database.begin_write_transaction(cur)
            cur.execute("UPDATE agents SET cash = 1 WHERE id = ?", (self.agent_id,))
            cur.execute("UPDATE trading_runs SET consecutive_infeasible = 9 "
                        "WHERE id = ?", (run_id,))
            conn.commit()
        finally:
            conn.close()
        result = run_engine.run_cycle(run_id)
        self.assertIn("insufficient cash", result["skip_reason"])
        run = trading_runs.get_run(run_id, self.agent_id)
        self.assertEqual(run["status"], "paused")
        self.assertEqual(run["paused_reason"], "infeasible")

    def test_deleted_agent_stops_run(self):
        os.environ["ENTITLEMENTS_ENFORCED"] = "false"
        run_id = self._draft()
        self.client.post(f"/api/runs/{run_id}/start", headers=self._h())
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            database.begin_write_transaction(cur)
            cur.execute("DELETE FROM agents WHERE id = ?", (self.agent_id,))
            conn.commit()
        finally:
            conn.close()
        result = run_engine.run_cycle(run_id)
        self.assertEqual(result["skip_reason"], "agent deleted")
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT status, status_reason FROM trading_runs WHERE id = ?",
                        (run_id,))
            row = dict(cur.fetchone())
        finally:
            conn.close()
        self.assertEqual(row["status"], "stopped")
        self.assertEqual(row["status_reason"], "agent_deleted")

    def test_admin_agent_delete_cascades_run_tables(self):
        os.environ["ENTITLEMENTS_ENFORCED"] = "false"
        run_id = self._draft()
        self.client.post(f"/api/runs/{run_id}/start", headers=self._h())
        from routes_admin import _delete_agent_cascade
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            database.begin_write_transaction(cur)
            deleted = _delete_agent_cascade(cur, self.agent_id)
            conn.commit()
        finally:
            conn.close()
        self.assertIn("trading_runs.agent_id", deleted)
        self.assertIn("run_events.run_id", deleted)
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            for table in ("trading_runs", "run_events", "run_reports"):
                cur.execute(f"SELECT COUNT(*) AS n FROM {table}")
                self.assertEqual(cur.fetchone()["n"], 0, table)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
