"""Trading Runs stops & P&L (Plan 10, Phase 3) — verification gates.

Covers: fee-inclusive average-cost replay (long and short), max_loss /
profit_target / max_trades / at_time stops, stale-mark FAIL-CLOSED pause +
auto-recovery + escalation, flatten (incl. manual-halt block -> bounded
retry -> stopped(positions_held)), hold path, synthetic liquidation for v1
shorts, and SL/TP-watcher close attribution via positions.run_id.
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
from automation import execute_paper_trade
from routes import create_app

FEE = 0.001  # fees.TRADE_FEE_RATE


def _ts(offset_seconds: float = 0) -> str:
    return (datetime.now(timezone.utc)
            + timedelta(seconds=offset_seconds)).strftime(trading_runs.TS_FMT)


class RunStopsTests(unittest.TestCase):
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
            json={"name": "stops-agent", "password": "pw123",
                  "initial_balance": 100000.0})
        self.token = resp.json()["token"]
        self.agent_id = resp.json()["agent_id"]

    def tearDown(self):
        self.probe.stop()
        os.environ.pop("AUTO_TRADING_ENABLED", None)
        self.tmp.cleanup()

    # ── helpers ────────────────────────────────────────────────────────

    def _h(self):
        return {"Authorization": f"Bearer {self.token}"}

    def _run(self, **overrides) -> int:
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

    def _set_run(self, run_id, **cols):
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

    def _set_mark(self, price, updated_at=None):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            database.begin_write_transaction(cur)
            cur.execute(
                "UPDATE positions SET current_price = ?, price_updated_at = ? "
                "WHERE agent_id = ?",
                (price, updated_at or _ts(), self.agent_id))
            conn.commit()
        finally:
            conn.close()

    def _position(self):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM positions WHERE agent_id = ?", (self.agent_id,))
            row = cur.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def _trade(self, run_id, side, qty, price, key):
        signal_id, err = execute_paper_trade(
            self.agent_id, "BTC", "crypto", side, qty, price,
            run_id=run_id, client_order_id=f"run:{run_id}:test:{key}")
        assert signal_id, err
        return signal_id

    # ── P&L replay ─────────────────────────────────────────────────────

    def test_long_round_trip_pnl_is_fee_inclusive(self):
        run_id = self._run()
        self._trade(run_id, "buy", 5.0, 100.0, "b1")
        self._trade(run_id, "sell", 5.0, 110.0, "s1")
        pnl = run_engine.compute_run_pnl(self._row(run_id))
        expected = (110 - 100) * 5 - (500 * FEE) - (550 * FEE)
        self.assertAlmostEqual(pnl["realized"], expected)
        self.assertAlmostEqual(pnl["total"], expected)
        self.assertEqual(pnl["trades"], 2)

    def test_short_round_trip_pnl_matches_cover_credit_math(self):
        run_id = self._run(market_type="futures")
        self._trade(run_id, "short", 5.0, 100.0, "sh1")
        self._trade(run_id, "cover", 5.0, 90.0, "c1")
        pnl = run_engine.compute_run_pnl(self._row(run_id))
        expected = (100 - 90) * 5 - (500 * FEE) - (450 * FEE)
        self.assertAlmostEqual(pnl["realized"], expected)
        # replay agrees with the actual cash ledger (fee-inclusive truth)
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT cash FROM agents WHERE id = ?", (self.agent_id,))
            cash = cur.fetchone()["cash"]
        finally:
            conn.close()
        self.assertAlmostEqual(cash - 100000.0, expected)

    def test_unrealized_uses_position_mark(self):
        run_id = self._run()
        self._trade(run_id, "buy", 5.0, 100.0, "b1")
        self._set_mark(104.0)
        pnl = run_engine.compute_run_pnl(self._row(run_id))
        self.assertAlmostEqual(pnl["unrealized"], 20.0)
        self.assertTrue(pnl["mark_age_ok"])

    # ── stop conditions ────────────────────────────────────────────────

    def test_max_loss_stop_flattens_and_stops(self):
        run_id = self._run(stop_conditions={"max_loss_usd": 10.0})
        self._trade(run_id, "buy", 5.0, 100.0, "b1")
        self._set_mark(97.0)  # total ≈ -15.5
        out = run_engine.control_pass()   # fires stop, flattens, finishes — one scan
        self.assertEqual(out["stops_fired"], 1)
        self.assertEqual(out["stopping_finished"], 1)
        row = self._row(run_id)
        self.assertEqual(row["status"], "stopped")
        self.assertEqual(row["status_reason"], "stop_event:max_loss")
        pos = self._position()
        self.assertTrue(pos is None or float(pos["quantity"]) == 0)
        # realized cache reconciled from the ledger
        expected = (97 - 100) * 5 - (500 * FEE) - (485 * FEE)
        self.assertAlmostEqual(float(row["realized_pnl_usd"]), expected, places=6)

    def test_profit_target_stop(self):
        run_id = self._run(stop_conditions={"profit_target_usd": 10.0})
        self._trade(run_id, "buy", 5.0, 100.0, "b1")
        self._set_mark(105.0)  # total ≈ +24.5
        run_engine.control_pass()  # fires + flattens same scan
        self.assertEqual(self._row(run_id)["status"], "stopped")
        self.assertEqual(self._row(run_id)["status_reason"],
                         "stop_event:profit_target")

    def test_max_trades_stop(self):
        run_id = self._run(stop_conditions={"max_trades": 2})
        self._trade(run_id, "buy", 1.0, 100.0, "b1")
        self._trade(run_id, "buy", 1.0, 100.0, "b2")
        self._set_mark(100.0)
        run_engine.control_pass()
        self.assertEqual(self._row(run_id)["status_reason"], "stop_event:max_trades")

    def test_at_time_stop_fires_for_paused_runs_too(self):
        run_id = self._run(stop_conditions={"at_time": _ts(86400)})
        self.client.post(f"/api/runs/{run_id}/pause", headers=self._h())
        self._set_run(run_id, stop_conditions_json='{"at_time": "%s"}' % _ts(-5))
        run_engine.control_pass()
        row = self._row(run_id)
        self.assertEqual(row["status"], "stopped")  # no position -> immediate
        self.assertEqual(row["status_reason"], "stop_event:at_time")

    # ── stale marks: fail closed ───────────────────────────────────────

    def test_stale_marks_pause_then_recover(self):
        run_id = self._run(stop_conditions={"max_loss_usd": 10.0})
        self._trade(run_id, "buy", 5.0, 100.0, "b1")
        self._set_mark(97.0, updated_at=_ts(-7200))  # stale beyond 900s max
        run_engine.control_pass()
        row = self._row(run_id)
        self.assertEqual(row["status"], "paused")
        self.assertEqual(row["paused_reason"], "stop_eval_failed")
        self.assertEqual(row["consecutive_errors"], 1)
        # marks freshen -> auto-recovery (but the loss stop then fires)
        self._set_mark(100.0)
        run_engine.control_pass()
        row = self._row(run_id)
        self.assertEqual(row["status"], "running")
        self.assertEqual(row["consecutive_errors"], 0)

    def test_persistent_eval_failure_escalates_to_stop(self):
        run_id = self._run(stop_conditions={"max_loss_usd": 10.0})
        self._trade(run_id, "buy", 5.0, 100.0, "b1")
        self._set_mark(97.0, updated_at=_ts(-7200))
        self._set_run(run_id, consecutive_errors=4)
        run_engine.control_pass()
        self.assertEqual(self._row(run_id)["status"], "stopping")
        self.assertEqual(self._row(run_id)["status_reason"], "stop_eval_failed")

    # ── flatten paths ──────────────────────────────────────────────────

    def test_hold_stop_keeps_position_under_watcher(self):
        run_id = self._run(stop_flatten=False)
        self._trade(run_id, "buy", 5.0, 100.0, "b1")
        resp = self.client.post(f"/api/runs/{run_id}/stop", json={"flatten": False},
                                headers=self._h())
        self.assertEqual(resp.json()["run"]["status"], "stopping")
        run_engine.control_pass()
        row = self._row(run_id)
        self.assertEqual(row["status"], "stopped")
        self.assertEqual(row["status_reason"], "positions_held")
        pos = self._position()
        self.assertAlmostEqual(float(pos["quantity"]), 5.0)
        # The position stays open under the SL/TP watcher, but the finished run
        # releases it back to the unowned book. `run_id` now means "an ACTIVE
        # run owns this book" (sibling runs share a symbol and are told apart
        # by it), and every non-run reader filters on `run_id IS NULL` — a
        # lingering stamp would hide the position from the owner's own sell.
        self.assertIsNone(pos["run_id"])

    def test_manual_halt_blocks_flatten_then_positions_held_after_timeout(self):
        run_id = self._run()
        self._trade(run_id, "buy", 5.0, 100.0, "b1")
        self.client.post(f"/api/runs/{run_id}/stop", json={"flatten": True},
                         headers=self._h())
        with patch("run_engine._manual_halt_blocks", return_value=True):
            run_engine.control_pass()
            self.assertEqual(self._row(run_id)["status"], "stopping")  # retrying
            self._set_run(run_id, stopped_at=_ts(-7200))  # past RUN_FLATTEN_TIMEOUT
            out = run_engine.control_pass()
        self.assertEqual(out["stopping_finished"], 1)
        row = self._row(run_id)
        self.assertEqual(row["status"], "stopped")
        self.assertEqual(row["status_reason"], "positions_held")
        self.assertAlmostEqual(float(self._position()["quantity"]), 5.0)

    def test_flatten_is_idempotent_across_retries(self):
        run_id = self._run()
        self._trade(run_id, "buy", 5.0, 100.0, "b1")
        self._set_mark(101.0)
        row = self._row(run_id)
        ok, why = run_engine._flatten_run(row)
        self.assertTrue(ok, why)
        ok2, why2 = run_engine._flatten_run(row)  # retry: duplicate key -> ok
        self.assertTrue(ok2, why2)
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) AS n FROM signals WHERE run_id = ? "
                        "AND side = 'sell'", (run_id,))
            self.assertEqual(cur.fetchone()["n"], 1)
        finally:
            conn.close()

    # ── synthetic liquidation (v1 shorts) ──────────────────────────────

    def test_short_synthetic_liquidation_at_double_entry(self):
        run_id = self._run(market_type="futures")
        self._trade(run_id, "short", 5.0, 100.0, "sh1")
        self._set_mark(205.0)  # loss > 100% of escrowed collateral
        run_engine.control_pass()  # liquidation fires + cover in one scan
        row = self._row(run_id)
        self.assertEqual(row["status"], "stopped")
        self.assertEqual(row["status_reason"], "synthetic_liquidation")
        pos = self._position()
        self.assertTrue(pos is None or float(pos["quantity"]) == 0)
        expected = (100 - 205) * 5 - (500 * FEE) - (205 * 5 * FEE)
        self.assertAlmostEqual(float(row["realized_pnl_usd"]), expected, places=6)

    # ── watcher attribution ────────────────────────────────────────────

    def test_watcher_close_attributes_to_owning_run(self):
        run_id = self._run()
        self._trade(run_id, "buy", 5.0, 100.0, "b1")
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            database.begin_write_transaction(cur)
            cur.execute(
                "UPDATE positions SET stop_loss = 95.0, current_price = 94.0, "
                "price_updated_at = ? WHERE agent_id = ?",
                (_ts(), self.agent_id))
            conn.commit()
        finally:
            conn.close()
        from risk_engine import run_sltp_watcher_tick
        with patch.dict(os.environ, {"RISK_ENGINE_ENABLED": "true"}):
            out = run_sltp_watcher_tick()
        self.assertEqual(out["closed"], 1)
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT run_id, side FROM signals WHERE agent_id = ? "
                        "ORDER BY id DESC LIMIT 1", (self.agent_id,))
            last = dict(cur.fetchone())
            self.assertEqual(last["side"], "sell")
            self.assertEqual(last["run_id"], run_id)
            cur.execute("SELECT COUNT(*) AS n FROM run_events WHERE run_id = ? "
                        "AND event_type = 'trade'", (run_id,))
            self.assertEqual(cur.fetchone()["n"], 2)  # entry + watcher close
        finally:
            conn.close()

    # ── auto-restart after a goal-reached stop ─────────────────────────

    def _runs_for_symbol(self, symbol="BTC"):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM trading_runs WHERE agent_id = ? AND symbol = ? "
                        "ORDER BY id", (self.agent_id, symbol))
            return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

    def test_profit_target_stop_auto_restarts_with_identical_settings(self):
        run_id = self._run(stop_conditions={"profit_target_usd": 10.0},
                           interval_minutes=45, min_confidence=0.8)
        self._trade(run_id, "buy", 5.0, 100.0, "b1")
        self._set_mark(105.0)
        run_engine.control_pass()

        runs = self._runs_for_symbol()
        self.assertEqual(len(runs), 2, "goal-reached stop should spawn one successor")
        old, new = runs
        self.assertEqual(old["id"], run_id)
        self.assertEqual(old["status"], "stopped")
        self.assertEqual(old["status_reason"], "stop_event:profit_target")
        # the successor is live and carries the ORIGINAL settings verbatim
        self.assertEqual(new["status"], "running")
        self.assertEqual(new["symbol"], old["symbol"])
        self.assertEqual(new["market"], old["market"])
        self.assertEqual(new["market_type"], old["market_type"])
        self.assertEqual(json.loads(new["config_snapshot_json"]),
                         json.loads(old["config_snapshot_json"]))
        self.assertEqual(json.loads(new["stop_conditions_json"]),
                         json.loads(old["stop_conditions_json"]))
        self.assertEqual(new["stop_flatten"], old["stop_flatten"])
        # and it starts clean — no inherited P&L or trades
        self.assertEqual(run_engine.compute_run_pnl(new)["trades"], 0)

    def test_max_trades_stop_auto_restarts(self):
        run_id = self._run(stop_conditions={"max_trades": 2})
        self._trade(run_id, "buy", 1.0, 100.0, "b1")
        self._trade(run_id, "sell", 1.0, 100.0, "s1")
        self._set_mark(100.0)
        run_engine.control_pass()
        runs = self._runs_for_symbol()
        self.assertEqual(len(runs), 2)
        self.assertEqual(runs[0]["status_reason"], "stop_event:max_trades")
        self.assertEqual(runs[1]["status"], "running")

    def test_max_loss_stop_never_auto_restarts(self):
        """A protective stop must stay stopped — restarting re-enters the
        setup that just lost money and turns the loss cap into a loop."""
        run_id = self._run(stop_conditions={"max_loss_usd": 10.0})
        self._trade(run_id, "buy", 5.0, 100.0, "b1")
        self._set_mark(97.0)
        run_engine.control_pass()
        runs = self._runs_for_symbol()
        self.assertEqual(len(runs), 1, "max_loss must not spawn a successor")
        self.assertEqual(runs[0]["status_reason"], "stop_event:max_loss")

    def test_user_stop_never_auto_restarts(self):
        """Otherwise the Stop button resurrects its own run."""
        run_id = self._run()
        resp = self.client.post(f"/api/runs/{run_id}/stop", json={"flatten": True},
                                headers=self._h())
        self.assertEqual(resp.status_code, 200, resp.text)
        run_engine.control_pass()
        runs = self._runs_for_symbol()
        self.assertEqual(len(runs), 1, "user_stop must not spawn a successor")
        self.assertEqual(runs[0]["status"], "stopped")

    def test_auto_restart_kill_switch_disables_it(self):
        run_id = self._run(stop_conditions={"profit_target_usd": 10.0})
        self._trade(run_id, "buy", 5.0, 100.0, "b1")
        self._set_mark(105.0)
        with patch.dict(os.environ, {"RUN_AUTO_RESTART": "false"}):
            run_engine.control_pass()
        self.assertEqual(len(self._runs_for_symbol()), 1)
        self.assertEqual(self._row(run_id)["status"], "stopped")


if __name__ == "__main__":
    unittest.main()
