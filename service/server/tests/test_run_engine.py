"""Trading Runs scheduler engine (Plan 10, Phase 2) — exactly-once gates.

Covers the Phase 2 verification gates without a live LLM:
  * a due running run executes exactly one attributed, journaled trade
  * client_order_id idempotency (same seq can never trade twice)
  * fencing: a zombie claimant whose lease was reclaimed cannot trade,
    and a stop pressed mid-cycle prevents the trade
  * lease claim: owner renewal allowed; a live foreign lease blocks
  * crash recovery: an uncleared lease does not wedge the run — the next
    due window reclaims and runs a fresh cycle under a new seq
  * pre-LLM gates: market closed / insufficient cash skip WITHOUT calling
    the analysis (zero LLM cost), journaled as gate_skip telemetry
  * control pass: at_time arming fires; stopping without positions finishes
"""

from __future__ import annotations

import json
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

BUY_ANALYSIS = {
    "symbol": "BTC",
    "market": "crypto",
    "analysts": {"technical": {"brief": "t", "data": {"sigma_daily_pct": 2.5,
                                                      "current_price": 100.0}}},
    "decision": {"action": "buy", "confidence": 0.9, "entry": 100.0, "report": "r"},
}


def _ts(dt: datetime) -> str:
    return dt.strftime(trading_runs.TS_FMT)


class RunEngineTests(unittest.TestCase):
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
            json={"name": "engine-agent", "password": "pw123",
                  "initial_balance": 100000.0})
        assert resp.status_code == 200, resp.text
        self.token = resp.json()["token"]
        self.agent_id = resp.json()["agent_id"]

    def tearDown(self):
        self.probe.stop()
        os.environ.pop("AUTO_TRADING_ENABLED", None)
        self.tmp.cleanup()

    # ── helpers ────────────────────────────────────────────────────────

    def _h(self):
        return {"Authorization": f"Bearer {self.token}"}

    def _running_run(self, **overrides) -> int:
        payload = {"symbol": "BTC", "market": "crypto", "max_bet_usd": 500.0}
        payload.update(overrides)
        run_id = self.client.post("/api/runs", json=payload,
                                  headers=self._h()).json()["id"]
        resp = self.client.post(f"/api/runs/{run_id}/start", headers=self._h())
        assert resp.status_code == 200, resp.text
        return run_id

    def _row(self, run_id):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM trading_runs WHERE id = ?", (run_id,))
            return dict(cur.fetchone())
        finally:
            conn.close()

    def _set(self, run_id, **cols):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            database.begin_write_transaction(cur)
            sets = ", ".join(f"{k} = ?" for k in cols)
            cur.execute(f"UPDATE trading_runs SET {sets} WHERE id = ?",
                        (*cols.values(), run_id))
            conn.commit()
        finally:
            conn.close()

    def _signals(self, run_id):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM signals WHERE run_id = ? ORDER BY id", (run_id,))
            return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

    def _events(self, run_id):
        resp = self.client.get(f"/api/runs/{run_id}/events?limit=500", headers=self._h())
        return resp.json()["events"]

    # ── happy path ─────────────────────────────────────────────────────

    def test_cycle_executes_one_attributed_journaled_trade(self):
        run_id = self._running_run()
        with patch("analysis_agents.run_analysis", return_value=BUY_ANALYSIS):
            result = run_engine.run_cycle(run_id)
        self.assertTrue(result["executed"], result)

        signals = self._signals(run_id)
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0]["client_order_id"], f"run:{run_id}:cyc:1")
        self.assertAlmostEqual(signals[0]["fee_usd"], 500.0 * 0.001)

        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT run_id, quantity FROM positions WHERE agent_id = ?",
                        (self.agent_id,))
            pos = dict(cur.fetchone())
            self.assertEqual(pos["run_id"], run_id)
            self.assertAlmostEqual(pos["quantity"], 5.0)  # $500 / $100
            cur.execute("SELECT cash FROM agents WHERE id = ?", (self.agent_id,))
            self.assertAlmostEqual(cur.fetchone()["cash"], 100000.0 - 500.0 - 0.5)
        finally:
            conn.close()

        kinds = [e["event_type"] for e in self._events(run_id)]
        self.assertIn("trade", kinds)
        self.assertIn("decision", kinds)
        # lease released after the cycle
        row = self._row(run_id)
        self.assertIsNone(row["claimed_by"])

    def test_duplicate_client_order_id_cannot_trade_twice(self):
        run_id = self._running_run()
        from automation import execute_paper_trade
        first, err = execute_paper_trade(self.agent_id, "BTC", "crypto", "buy",
                                         1.0, 100.0, run_id=run_id,
                                         client_order_id=f"run:{run_id}:cyc:7")
        self.assertIsNotNone(first, err)
        second, err2 = execute_paper_trade(self.agent_id, "BTC", "crypto", "buy",
                                           1.0, 100.0, run_id=run_id,
                                           client_order_id=f"run:{run_id}:cyc:7")
        self.assertIsNone(second)
        self.assertIn("duplicate client_order_id", err2)
        self.assertEqual(len(self._signals(run_id)), 1)

    # ── fencing / zombie claimant ──────────────────────────────────────

    def test_zombie_claimant_cannot_trade_after_reclaim(self):
        """SIGSTOP-equivalent: worker A's lease is reclaimed by B while A is
        'inside' its LLM call; A's trade transaction must abort at the fence."""
        run_id = self._running_run()

        def steal_lease_then_decide(*args, **kwargs):
            # B reclaims while A is mid-analysis
            self._set(run_id, claimed_by="worker-B:999",
                      claim_expires_at=_ts(datetime.now(timezone.utc)
                                           + timedelta(seconds=300)))
            return BUY_ANALYSIS

        with patch("analysis_agents.run_analysis",
                   side_effect=steal_lease_then_decide):
            result = run_engine.run_cycle(run_id)
        self.assertFalse(result["executed"])
        self.assertIn("lease reclaimed", result["skip_reason"] or "")
        self.assertEqual(self._signals(run_id), [])

    def test_stop_pressed_mid_cycle_prevents_trade(self):
        run_id = self._running_run()

        def stop_then_decide(*args, **kwargs):
            self._set(run_id, status="stopped", active_key=None)
            return BUY_ANALYSIS

        with patch("analysis_agents.run_analysis", side_effect=stop_then_decide):
            result = run_engine.run_cycle(run_id)
        self.assertFalse(result["executed"])
        self.assertIn("fence: run is stopped", result["skip_reason"] or "")
        self.assertEqual(self._signals(run_id), [])

    def test_live_foreign_lease_blocks_claim(self):
        run_id = self._running_run()
        self._set(run_id, claimed_by="worker-B:999",
                  claim_expires_at=_ts(datetime.now(timezone.utc)
                                       + timedelta(seconds=300)))
        result = run_engine.run_cycle(run_id)
        self.assertFalse(result["executed"])
        self.assertIn("not claimed", result["skip_reason"])

    def test_expired_foreign_lease_is_reclaimed(self):
        run_id = self._running_run()
        self._set(run_id, claimed_by="worker-B:999",
                  claim_expires_at=_ts(datetime.now(timezone.utc)
                                       - timedelta(seconds=10)),
                  cycle_seq=3)
        with patch("analysis_agents.run_analysis", return_value=BUY_ANALYSIS):
            result = run_engine.run_cycle(run_id)
        self.assertTrue(result["executed"], result)
        # fresh cycle under a NEW seq — never a reuse of the stale one
        self.assertEqual(self._signals(run_id)[0]["client_order_id"],
                         f"run:{run_id}:cyc:4")

    def test_crashed_worker_lease_does_not_wedge_the_run(self):
        """kill -9 equivalent: a cycle that died without releasing its lease.
        The run waits for its due window, then the reclaim path runs a fresh
        cycle — no duplicate of the crashed cycle's trade."""
        run_id = self._running_run()
        with patch("analysis_agents.run_analysis", return_value=BUY_ANALYSIS):
            run_engine.run_cycle(run_id)  # cycle 1 trades
        # simulate crash: stale foreign lease left behind, clock in the past
        self._set(run_id,
                  claimed_by=run_engine.WORKER_IDENTITY + ":dead",
                  claim_expires_at=_ts(datetime.now(timezone.utc)
                                       - timedelta(seconds=5)),
                  last_cycle_at=_ts(datetime.now(timezone.utc)
                                    - timedelta(hours=2)))
        self.assertEqual(run_engine.due_run_ids(), [run_id])
        with patch("analysis_agents.run_analysis", return_value=BUY_ANALYSIS):
            result = run_engine.run_cycle(run_id)
        self.assertTrue(result["executed"], result)
        ids = [s["client_order_id"] for s in self._signals(run_id)]
        self.assertEqual(len(ids), len(set(ids)), f"duplicate keys: {ids}")
        self.assertEqual(len(ids), 2)  # two distinct cycles, one trade each

    # ── pre-LLM gates ──────────────────────────────────────────────────

    def test_market_closed_skips_without_llm(self):
        run_id = self._running_run()
        with patch("routes_shared.is_market_open", return_value=False), \
             patch("analysis_agents.run_analysis") as analysis:
            result = run_engine.run_cycle(run_id)
        analysis.assert_not_called()
        self.assertEqual(result["skip_reason"], "market closed")
        kinds = [(e["event_type"], (e["payload"] or {}).get("stage"))
                 for e in self._events(run_id)]
        self.assertIn(("gate_skip", "pre"), kinds)

    def test_insufficient_cash_skips_without_llm(self):
        run_id = self._running_run()
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            database.begin_write_transaction(cur)
            cur.execute("UPDATE agents SET cash = 10 WHERE id = ?", (self.agent_id,))
            conn.commit()
        finally:
            conn.close()
        with patch("analysis_agents.run_analysis") as analysis:
            result = run_engine.run_cycle(run_id)
        analysis.assert_not_called()
        self.assertIn("insufficient cash", result["skip_reason"])

    def test_kill_switch_disables_tick(self):
        os.environ["AUTO_TRADING_ENABLED"] = "false"
        import asyncio
        out = asyncio.run(run_engine.tick())
        self.assertEqual(out, {"enabled": False})

    # ── control pass ───────────────────────────────────────────────────

    def test_at_time_arming_fires_when_due(self):
        future = _ts(datetime.now(timezone.utc) + timedelta(days=1))
        run_id = self.client.post(
            "/api/runs",
            json={"symbol": "BTC", "market": "crypto", "max_bet_usd": 500.0,
                  "start_condition": {"type": "at_time", "at": future}},
            headers=self._h()).json()["id"]
        self.client.post(f"/api/runs/{run_id}/start", headers=self._h())
        self.assertEqual(self._row(run_id)["status"], "armed")

        out = run_engine.control_pass()
        self.assertEqual(out["armed_started"], 0)  # not due yet

        past = _ts(datetime.now(timezone.utc) - timedelta(seconds=5))
        self._set(run_id, start_condition_json=json.dumps(
            {"type": "at_time", "at": past}))
        out = run_engine.control_pass()
        self.assertEqual(out["armed_started"], 1)
        self.assertEqual(self._row(run_id)["status"], "running")

    def test_stopping_without_position_finishes(self):
        run_id = self._running_run()
        self._set(run_id, status="stopping", status_reason="user_stop")
        out = run_engine.control_pass()
        self.assertEqual(out["stopping_finished"], 1)
        row = self._row(run_id)
        self.assertEqual(row["status"], "stopped")
        self.assertIsNone(row["active_key"])

    def test_due_check_respects_interval(self):
        run_id = self._running_run()
        self._set(run_id, last_cycle_at=_ts(datetime.now(timezone.utc)
                                            - timedelta(minutes=2)))
        self.assertEqual(run_engine.due_run_ids(), [])  # 60m interval default
        self._set(run_id, last_cycle_at=_ts(datetime.now(timezone.utc)
                                            - timedelta(minutes=61)))
        self.assertEqual(run_engine.due_run_ids(), [run_id])


if __name__ == "__main__":
    unittest.main()
