"""Trading Runs (Plan 10, Phase 1) — lifecycle state machine + API gates.

Covers the Phase 1 verification gates:
  * strict condition validation (malformed REJECTS — never "start now")
  * lifecycle transitions incl. armed vs running, pause/resume, stop
  * tighten-only stop-condition edits while active
  * DB-level exclusivity (active_key) incl. a real concurrent double-start
  * pre-existing position / conflicting auto-execute rule block a start
  * cross-tenant ownership (agent B sees 404 on agent A's run)
  * run_events journal: monotonic seq per transition, UNIQUE(run_id, seq)
"""

from __future__ import annotations

import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
import trading_runs
from routes import create_app


def _future_ts() -> str:
    from datetime import datetime, timedelta, timezone
    return (datetime.now(timezone.utc) + timedelta(days=1)).strftime(trading_runs.TS_FMT)


class TradingRunsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.probe = patch("routes_runs._probe_price", return_value=100.0)
        self.probe.start()
        self.client = TestClient(create_app())
        self.token_a, self.agent_a = self._register("runner-a")
        self.token_b, self.agent_b = self._register("runner-b")

    def tearDown(self):
        self.probe.stop()
        self.tmp.cleanup()

    def _register(self, name):
        resp = self.client.post(
            "/api/claw/agents/selfRegister",
            json={"name": name, "password": "pw123", "initial_balance": 100000.0})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        return body["token"], body["agent_id"]

    def _h(self, token):
        return {"Authorization": f"Bearer {token}"}

    def _create(self, token=None, **overrides):
        payload = {"symbol": "BTC", "market": "crypto", "max_bet_usd": 500.0}
        payload.update(overrides)
        return self.client.post("/api/runs", json=payload,
                                headers=self._h(token or self.token_a))

    # ── creation validation ────────────────────────────────────────────

    def test_create_draft_ok(self):
        resp = self._create()
        self.assertEqual(resp.status_code, 200, resp.text)
        run = resp.json()["run"]
        self.assertEqual(run["status"], "draft")
        self.assertEqual(run["config"]["max_bet_usd"], 500.0)
        self.assertEqual(run["start_condition"], {"type": "manual"})

    def test_futures_is_crypto_only(self):
        resp = self._create(market="us-stock", market_type="futures")
        self.assertEqual(resp.status_code, 400)

    def test_leverage_accepted_and_clamped(self):
        # Isolated-margin leverage is accepted (1–10×) and clamped.
        # A max_loss_usd rides along from 2026-07-30: leveraged SPOT with no
        # P&L bound at all is refused separately (routes_runs), so without one
        # this would fail for a reason that has nothing to do with clamping.
        # The assertions below are unchanged — this still tests exactly what it
        # was written to test.
        stop = {"max_loss_usd": 50.0}
        r3 = self._create(leverage=3, stop_conditions=stop)
        self.assertEqual(r3.status_code, 200, r3.text)
        self.assertEqual(r3.json()["run"]["config"]["leverage"], 3.0)
        r99 = self._create(leverage=99, stop_conditions=stop)  # clamps, not rejected
        self.assertEqual(r99.status_code, 200, r99.text)
        self.assertEqual(r99.json()["run"]["config"]["leverage"], 10.0)

    def test_malformed_start_condition_rejects(self):
        for bad in ({"type": "sometime"},
                    {"type": "at_time"},
                    {"type": "at_time", "at": "not-a-date"},
                    {"type": "price_cross", "direction": "up", "price": 5},
                    {"type": "price_cross", "direction": "above", "price": -1},
                    {"type": "window", "schedule": {"days": [9]}}):
            resp = self._create(start_condition=bad)
            self.assertEqual(resp.status_code, 400, f"{bad} -> {resp.text}")

    def test_at_time_start_must_be_future(self):
        resp = self._create(start_condition={"type": "at_time",
                                             "at": "2020-01-01T00:00:00Z"})
        self.assertEqual(resp.status_code, 400)

    def test_unpriceable_symbol_rejects(self):
        with patch("routes_runs._probe_price", return_value=None):
            resp = self._create(symbol="NOPE")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("no price", resp.json()["detail"])

    def test_budget_below_max_bet_rejects(self):
        resp = self._create(run_budget_usd=100.0)
        self.assertEqual(resp.status_code, 400)

    # ── lifecycle ──────────────────────────────────────────────────────

    def test_manual_start_goes_running_then_pause_resume_stop(self):
        run_id = self._create().json()["id"]
        resp = self.client.post(f"/api/runs/{run_id}/start", headers=self._h(self.token_a))
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()["run"]["status"], "running")

        resp = self.client.post(f"/api/runs/{run_id}/pause", headers=self._h(self.token_a))
        self.assertEqual(resp.json()["run"]["status"], "paused")
        resp = self.client.post(f"/api/runs/{run_id}/resume", headers=self._h(self.token_a))
        self.assertEqual(resp.json()["run"]["status"], "running")

        # no run-owned position exists -> stop completes immediately
        resp = self.client.post(f"/api/runs/{run_id}/stop", json={"flatten": True},
                                headers=self._h(self.token_a))
        self.assertEqual(resp.json()["run"]["status"], "stopped")

    def test_timed_start_arms(self):
        run_id = self._create(start_condition={"type": "at_time",
                                               "at": _future_ts()}).json()["id"]
        resp = self.client.post(f"/api/runs/{run_id}/start", headers=self._h(self.token_a))
        self.assertEqual(resp.json()["run"]["status"], "armed")
        # armed run has taken the exclusivity slot
        second = self._create()
        resp2 = self.client.post(f"/api/runs/{second.json()['id']}/start",
                                 headers=self._h(self.token_a))
        self.assertEqual(resp2.status_code, 409)
        # stopping the armed run frees the slot
        self.client.post(f"/api/runs/{run_id}/stop", json={"flatten": False},
                         headers=self._h(self.token_a))
        resp3 = self.client.post(f"/api/runs/{second.json()['id']}/start",
                                 headers=self._h(self.token_a))
        self.assertEqual(resp3.status_code, 200, resp3.text)

    def test_pause_only_from_running(self):
        run_id = self._create().json()["id"]
        resp = self.client.post(f"/api/runs/{run_id}/pause", headers=self._h(self.token_a))
        self.assertEqual(resp.status_code, 400)

    def test_delete_only_draft_or_stopped(self):
        run_id = self._create().json()["id"]
        self.client.post(f"/api/runs/{run_id}/start", headers=self._h(self.token_a))
        resp = self.client.delete(f"/api/runs/{run_id}", headers=self._h(self.token_a))
        self.assertEqual(resp.status_code, 400)
        self.client.post(f"/api/runs/{run_id}/stop", json={"flatten": False},
                         headers=self._h(self.token_a))
        resp = self.client.delete(f"/api/runs/{run_id}", headers=self._h(self.token_a))
        self.assertEqual(resp.status_code, 200)

    # ── tighten-only stop conditions ───────────────────────────────────

    def test_stop_conditions_tighten_only_while_active(self):
        run_id = self._create(stop_conditions={"max_loss_usd": 200.0,
                                               "max_trades": 10}).json()["id"]
        # draft: free edit, loosening allowed
        resp = self.client.put(f"/api/runs/{run_id}/stop-conditions",
                               json={"max_loss_usd": 500.0},
                               headers=self._h(self.token_a))
        self.assertEqual(resp.status_code, 200, resp.text)

        self.client.post(f"/api/runs/{run_id}/start", headers=self._h(self.token_a))
        # active: tightening ok
        resp = self.client.put(f"/api/runs/{run_id}/stop-conditions",
                               json={"max_loss_usd": 300.0},
                               headers=self._h(self.token_a))
        self.assertEqual(resp.status_code, 200, resp.text)
        # active: loosening rejected
        resp = self.client.put(f"/api/runs/{run_id}/stop-conditions",
                               json={"max_loss_usd": 400.0},
                               headers=self._h(self.token_a))
        self.assertEqual(resp.status_code, 400)
        # active: removing a condition rejected
        resp = self.client.put(f"/api/runs/{run_id}/stop-conditions",
                               json={}, headers=self._h(self.token_a))
        self.assertEqual(resp.status_code, 400)
        # active: adding a new numeric condition tightens -> ok
        resp = self.client.put(f"/api/runs/{run_id}/stop-conditions",
                               json={"max_loss_usd": 300.0, "max_trades": 5},
                               headers=self._h(self.token_a))
        self.assertEqual(resp.status_code, 200, resp.text)

    # ── exclusivity & conflicting writers ──────────────────────────────

    def test_second_active_run_same_tuple_conflicts(self):
        first = self._create().json()["id"]
        self.client.post(f"/api/runs/{first}/start", headers=self._h(self.token_a))
        second = self._create().json()["id"]
        resp = self.client.post(f"/api/runs/{second}/start", headers=self._h(self.token_a))
        self.assertEqual(resp.status_code, 409)
        # different symbol is fine
        other = self._create(symbol="ETH").json()["id"]
        resp = self.client.post(f"/api/runs/{other}/start", headers=self._h(self.token_a))
        self.assertEqual(resp.status_code, 200, resp.text)
        # agent B on the same symbol is fine (exclusivity is per agent)
        b_run = self._create(token=self.token_b).json()["id"]
        resp = self.client.post(f"/api/runs/{b_run}/start", headers=self._h(self.token_b))
        self.assertEqual(resp.status_code, 200, resp.text)

    def test_concurrent_double_start_exactly_one_wins(self):
        run1 = self._create().json()["id"]
        run2 = self._create().json()["id"]
        barrier = threading.Barrier(2)
        results = {}

        def _start(rid):
            barrier.wait()
            resp = self.client.post(f"/api/runs/{rid}/start",
                                    headers=self._h(self.token_a))
            results[rid] = resp.status_code

        threads = [threading.Thread(target=_start, args=(r,)) for r in (run1, run2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        codes = sorted(results.values())
        self.assertEqual(codes, [200, 409], f"expected one winner: {results}")

    def test_existing_position_blocks_start(self):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            database.begin_write_transaction(cur)
            cur.execute(
                """INSERT INTO positions (agent_id, market, symbol, side, quantity,
                                          entry_price, opened_at)
                   VALUES (?, 'crypto', 'BTC', 'buy', 1.0, 100.0, datetime('now'))""",
                (self.agent_a,))
            conn.commit()
        finally:
            conn.close()
        run_id = self._create().json()["id"]
        resp = self.client.post(f"/api/runs/{run_id}/start", headers=self._h(self.token_a))
        self.assertEqual(resp.status_code, 409)
        detail = resp.json()["detail"]
        self.assertIn("position", detail["message"])
        self.assertIsNotNone(detail["conflicts"]["position"])
        self.assertEqual(detail["conflicts"]["position"]["quantity"], 1.0)

    def test_auto_executing_rule_blocks_start(self):
        resp = self.client.post(
            "/api/automation/configs",
            json={"symbol": "BTC", "market": "crypto", "auto_execute": True,
                  "size_usd": 100.0},
            headers=self._h(self.token_a))
        self.assertEqual(resp.status_code, 200, resp.text)
        rule_id = resp.json()["id"]
        run_id = self._create().json()["id"]
        resp = self.client.post(f"/api/runs/{run_id}/start", headers=self._h(self.token_a))
        self.assertEqual(resp.status_code, 409)
        detail = resp.json()["detail"]
        self.assertIn("automation rule", detail["message"])
        self.assertEqual(detail["conflicts"]["rule_ids"], [rule_id])

    def test_resolve_conflicts_closes_position_disables_rules_and_starts(self):
        # A stale shared long AND an enabled auto-exec rule on the tuple —
        # the exact trap where "close it first" alone can never succeed
        # (the rule re-opens the book). One consented call resolves both.
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            database.begin_write_transaction(cur)
            cur.execute(
                """INSERT INTO positions (agent_id, market, symbol, side, quantity,
                                          entry_price, current_price, opened_at)
                   VALUES (?, 'crypto', 'BTC', 'buy', 1.0, 100.0, 120.0, datetime('now'))""",
                (self.agent_a,))
            conn.commit()
        finally:
            conn.close()
        resp = self.client.post(
            "/api/automation/configs",
            json={"symbol": "BTC", "market": "crypto", "auto_execute": True,
                  "size_usd": 100.0},
            headers=self._h(self.token_a))
        rule_id = resp.json()["id"]
        run_id = self._create().json()["id"]

        resp = self.client.post(f"/api/runs/{run_id}/start",
                                json={"resolve_conflicts": True},
                                headers=self._h(self.token_a))
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["run"]["status"], "running")
        self.assertTrue(body["resolved"]["closed_position"])
        self.assertEqual(body["resolved"]["disabled_rule_ids"], [rule_id])

        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """SELECT quantity FROM positions
                   WHERE agent_id = ? AND market = 'crypto' AND symbol = 'BTC'""",
                (self.agent_a,))
            row = cur.fetchone()
            self.assertEqual(float(row["quantity"]) if row else 0.0, 0.0)
            cur.execute("SELECT enabled FROM automation_configs WHERE id = ?", (rule_id,))
            self.assertEqual(cur.fetchone()["enabled"], 0)
            cur.execute(
                "SELECT id FROM run_events WHERE run_id = ? AND event_type = 'conflicts_resolved'",
                (run_id,))
            self.assertIsNotNone(cur.fetchone())
        finally:
            conn.close()

    def test_resolve_conflicts_noop_when_clean(self):
        run_id = self._create().json()["id"]
        resp = self.client.post(f"/api/runs/{run_id}/start",
                                json={"resolve_conflicts": True},
                                headers=self._h(self.token_a))
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()["resolved"],
                         {"closed_position": False, "disabled_rule_ids": []})

    def test_enabling_auto_exec_rule_blocked_while_run_active(self):
        # Mirror guard: without it a rule enabled mid-run trades into the
        # run's book and corrupts attribution.
        run_id = self._create().json()["id"]
        resp = self.client.post(f"/api/runs/{run_id}/start", headers=self._h(self.token_a))
        self.assertEqual(resp.status_code, 200, resp.text)
        resp = self.client.post(
            "/api/automation/configs",
            json={"symbol": "BTC", "market": "crypto", "auto_execute": True,
                  "size_usd": 100.0},
            headers=self._h(self.token_a))
        self.assertEqual(resp.status_code, 409)
        self.assertIn("is active", resp.json()["detail"])
        # A non-auto-executing (analysis-only) rule is still fine.
        resp = self.client.post(
            "/api/automation/configs",
            json={"symbol": "BTC", "market": "crypto", "auto_execute": False,
                  "size_usd": 100.0},
            headers=self._h(self.token_a))
        self.assertEqual(resp.status_code, 200, resp.text)
        # ...and so is an auto-exec rule on a different symbol.
        resp = self.client.post(
            "/api/automation/configs",
            json={"symbol": "ETH", "market": "crypto", "auto_execute": True,
                  "size_usd": 100.0},
            headers=self._h(self.token_a))
        self.assertEqual(resp.status_code, 200, resp.text)

    # ── ownership / authz ──────────────────────────────────────────────

    def test_cross_tenant_access_is_404(self):
        run_id = self._create().json()["id"]
        for method, path, body in (
                ("get", f"/api/runs/{run_id}", None),
                ("post", f"/api/runs/{run_id}/start", None),
                ("post", f"/api/runs/{run_id}/stop", {"flatten": True}),
                ("get", f"/api/runs/{run_id}/events", None),
                ("delete", f"/api/runs/{run_id}", None)):
            fn = getattr(self.client, method)
            kwargs = {"headers": self._h(self.token_b)}
            if body is not None:
                kwargs["json"] = body
            resp = fn(path, **kwargs)
            self.assertEqual(resp.status_code, 404, f"{method} {path}: {resp.status_code}")

    def test_no_token_is_401(self):
        resp = self.client.get("/api/runs")
        self.assertEqual(resp.status_code, 401)

    # ── run_events journal ─────────────────────────────────────────────

    def test_transitions_journal_monotonic_seq(self):
        run_id = self._create().json()["id"]
        self.client.post(f"/api/runs/{run_id}/start", headers=self._h(self.token_a))
        self.client.post(f"/api/runs/{run_id}/pause", headers=self._h(self.token_a))
        self.client.post(f"/api/runs/{run_id}/resume", headers=self._h(self.token_a))
        self.client.post(f"/api/runs/{run_id}/stop", json={"flatten": False},
                         headers=self._h(self.token_a))
        resp = self.client.get(f"/api/runs/{run_id}/events", headers=self._h(self.token_a))
        events = resp.json()["events"]
        seqs = [e["seq"] for e in events]
        self.assertEqual(seqs, sorted(seqs))
        self.assertEqual(len(seqs), len(set(seqs)))
        states = [e["payload"]["to"] for e in events if e["event_type"] == "run_status"]
        self.assertEqual(states, ["draft", "running", "paused", "running", "stopped"])
        # after_seq replay works
        resp = self.client.get(f"/api/runs/{run_id}/events?after_seq={seqs[1]}",
                               headers=self._h(self.token_a))
        self.assertEqual(resp.json()["events"][0]["seq"], seqs[2])

    def test_run_events_unique_run_seq(self):
        run_id = self._create().json()["id"]
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            database.begin_write_transaction(cur)
            with self.assertRaises(Exception):
                cur.execute(
                    """INSERT INTO run_events (run_id, seq, event_type, ts, payload)
                       VALUES (?, 1, 'x', '2026-01-01T00:00:00Z', '{}')""",
                    (run_id,))
                conn.commit()
        finally:
            try:
                conn.rollback()
            except Exception:
                pass
            conn.close()


if __name__ == "__main__":
    unittest.main()
