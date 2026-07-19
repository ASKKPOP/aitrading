"""Trading Runs live stream (Plan 10, Phase 6) — verification gates.

Covers: ticket mint/redeem (expiry, tamper, single-use), WS rejection
without a valid ticket, PER-SUB cross-tenant rejection (the blocker),
backfill-then-live replay with seq continuity, resync_required for
oversized gaps, tick frames from position marks, equity snapshot
emission (on change + heartbeat, not blind cadence), equity-only pruning,
and the snapshot endpoint.
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
import routes_run_stream
import run_engine
import trading_runs
from automation import execute_paper_trade
from routes import create_app


def _ts(offset_seconds: float = 0) -> str:
    return (datetime.now(timezone.utc)
            + timedelta(seconds=offset_seconds)).strftime(trading_runs.TS_FMT)


class RunStreamTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        os.environ["AUTO_TRADING_ENABLED"] = "true"
        os.environ["RUN_WS_POLL_SECONDS"] = "0.2"
        self.probe = patch("routes_runs._probe_price", return_value=100.0)
        self.probe.start()
        self.client = TestClient(create_app())
        self.token_a, self.agent_a = self._register("stream-a")
        self.token_b, self.agent_b = self._register("stream-b")

    def tearDown(self):
        self.probe.stop()
        os.environ.pop("AUTO_TRADING_ENABLED", None)
        os.environ.pop("RUN_WS_POLL_SECONDS", None)
        self.tmp.cleanup()

    def _register(self, name):
        resp = self.client.post(
            "/api/claw/agents/selfRegister",
            json={"name": name, "password": "pw123", "initial_balance": 100000.0})
        return resp.json()["token"], resp.json()["agent_id"]

    def _h(self, token):
        return {"Authorization": f"Bearer {token}"}

    def _running_run(self, token=None) -> int:
        run_id = self.client.post(
            "/api/runs", json={"symbol": "BTC", "market": "crypto",
                               "max_bet_usd": 500.0},
            headers=self._h(token or self.token_a)).json()["id"]
        self.client.post(f"/api/runs/{run_id}/start",
                         headers=self._h(token or self.token_a))
        return run_id

    def _ticket(self, token=None) -> str:
        resp = self.client.post("/api/runs/ws-ticket",
                                headers=self._h(token or self.token_a))
        self.assertEqual(resp.status_code, 200, resp.text)
        return resp.json()["ticket"]

    # ── tickets ────────────────────────────────────────────────────────

    def test_ticket_redeem_and_single_use(self):
        ticket = routes_run_stream.mint_ticket(42)
        self.assertEqual(routes_run_stream.redeem_ticket(ticket), 42)
        self.assertIsNone(routes_run_stream.redeem_ticket(ticket))  # burned

    def test_ticket_tamper_and_expiry_rejected(self):
        ticket = routes_run_stream.mint_ticket(42)
        tampered = ticket[:-6] + "AAAAAA"
        self.assertIsNone(routes_run_stream.redeem_ticket(tampered))
        fresh = routes_run_stream.mint_ticket(1)  # minted with REAL time
        with patch("routes_run_stream.time.time", return_value=9999999999.0):
            self.assertIsNone(routes_run_stream.redeem_ticket(fresh))

    def test_ws_rejects_without_ticket(self):
        with self.assertRaises(Exception):
            with self.client.websocket_connect("/ws/runs?ticket=bogus"):
                pass

    # ── per-sub authorization (the blocker) ────────────────────────────

    def test_cross_tenant_sub_rejected(self):
        run_a = self._running_run()
        with self.client.websocket_connect(
                f"/ws/runs?ticket={self._ticket(self.token_b)}") as ws:
            ws.send_text(json.dumps({"op": "sub", "run_id": run_a}))
            frame = ws.receive_json()
            self.assertEqual(frame["type"], "error")
            self.assertIn("not found", frame["error"])

    # ── backfill + live tail ───────────────────────────────────────────

    def test_backfill_then_live_events_with_seq_continuity(self):
        run_id = self._running_run()
        with self.client.websocket_connect(
                f"/ws/runs?ticket={self._ticket()}") as ws:
            ws.send_text(json.dumps({"op": "sub", "run_id": run_id, "from_seq": 0}))
            frames = []
            frame = ws.receive_json()
            while frame["type"] != "backfill_done":
                frames.append(frame)
                frame = ws.receive_json()
            seqs = [f["seq"] for f in frames if f["type"] == "event"]
            self.assertEqual(seqs, sorted(seqs))
            self.assertGreaterEqual(len(seqs), 2)  # created + start
            self.assertEqual(frame["to_seq"], max(seqs))

            # a trade lands while connected -> the poll tail relays it
            execute_paper_trade(self.agent_a, "BTC", "crypto", "buy", 1.0, 100.0,
                                run_id=run_id, client_order_id=f"run:{run_id}:ws:1")
            got = ws.receive_json()
            while got["type"] not in ("event",):
                got = ws.receive_json()
            self.assertEqual(got["event_type"], "trade")
            self.assertEqual(got["seq"], max(seqs) + 1)

    def test_oversized_gap_requests_resync(self):
        run_id = self._running_run()
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            database.begin_write_transaction(cur)
            cur.execute("UPDATE trading_runs SET last_event_seq = 10000 WHERE id = ?",
                        (run_id,))
            conn.commit()
        finally:
            conn.close()
        with self.client.websocket_connect(
                f"/ws/runs?ticket={self._ticket()}") as ws:
            ws.send_text(json.dumps({"op": "sub", "run_id": run_id, "from_seq": 0}))
            frame = ws.receive_json()
            self.assertEqual(frame["type"], "resync_required")

    def test_tick_frame_from_position_mark(self):
        run_id = self._running_run()
        execute_paper_trade(self.agent_a, "BTC", "crypto", "buy", 1.0, 100.0,
                            run_id=run_id, client_order_id=f"run:{run_id}:ws:t")
        with self.client.websocket_connect(
                f"/ws/runs?ticket={self._ticket()}") as ws:
            ws.send_text(json.dumps({"op": "sub", "run_id": run_id, "from_seq": 0}))
            saw_tick = False
            for _ in range(20):
                frame = ws.receive_json()
                if frame["type"] == "tick":
                    saw_tick = True
                    self.assertEqual(frame["symbol"], "BTC")
                    self.assertAlmostEqual(frame["price"], 100.0)
                    break
                if frame["type"] == "backfill_done":
                    # tick arrives right after backfill in the same drain
                    continue
            self.assertTrue(saw_tick)

    # ── equity telemetry + prune ───────────────────────────────────────

    def test_equity_emitted_on_change_not_blindly(self):
        run_id = self._running_run()
        run = trading_runs.get_run(run_id, self.agent_a)
        run_engine._last_equity.pop(run_id, None)
        pnl = {"realized": 0.0, "unrealized": 5.0, "total": 5.0, "trades": 1}
        run_engine._maybe_emit_equity(run, pnl)
        run_engine._maybe_emit_equity(run, pnl)  # unchanged within heartbeat
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) AS n FROM run_events WHERE run_id = ? "
                        "AND event_type = 'equity'", (run_id,))
            self.assertEqual(cur.fetchone()["n"], 1)
        finally:
            conn.close()
        run_engine._maybe_emit_equity(run, {**pnl, "total": 6.0})  # changed
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) AS n FROM run_events WHERE run_id = ? "
                        "AND event_type = 'equity'", (run_id,))
            self.assertEqual(cur.fetchone()["n"], 2)
        finally:
            conn.close()

    def test_prune_touches_only_aged_equity_events(self):
        run_id = self._running_run()
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            database.begin_write_transaction(cur)
            cur.execute(
                """INSERT INTO run_events (run_id, seq, event_type, ts, payload)
                   VALUES (?, 500, 'equity', ?, '{}'),
                          (?, 501, 'trade', ?, '{}')""",
                (run_id, _ts(-30 * 86400), run_id, _ts(-30 * 86400)))
            conn.commit()
        finally:
            conn.close()
        from run_reports import prune_equity_events
        pruned = prune_equity_events()
        self.assertEqual(pruned, 1)
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT event_type FROM run_events WHERE run_id = ? "
                        "AND seq IN (500, 501)", (run_id,))
            kinds = [r["event_type"] for r in cur.fetchall()]
        finally:
            conn.close()
        self.assertEqual(kinds, ["trade"])  # audit rows never pruned

    # ── snapshot endpoint ──────────────────────────────────────────────

    def test_snapshot_endpoint(self):
        run_id = self._running_run()
        execute_paper_trade(self.agent_a, "BTC", "crypto", "buy", 2.0, 100.0,
                            run_id=run_id, client_order_id=f"run:{run_id}:snap")
        resp = self.client.get(f"/api/runs/{run_id}/snapshot", headers=self._h(self.token_a))
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["run"]["status"], "running")
        self.assertAlmostEqual(float(body["position"]["quantity"]), 2.0)
        self.assertGreaterEqual(body["subscribe_from_seq"], 3)
        # cross-tenant: 404
        resp = self.client.get(f"/api/runs/{run_id}/snapshot", headers=self._h(self.token_b))
        self.assertEqual(resp.status_code, 404)


if __name__ == "__main__":
    unittest.main()
