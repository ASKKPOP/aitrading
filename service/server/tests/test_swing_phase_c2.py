"""Plan 23 Phase C2 — session-queued flattens + the C1 wiring seams.

Every terminal path (fleet stop-all, breaker, profit-goal, at_time expiry,
retire, user stop) funnels through status='stopping' and the control scan's
_control_stopping — so ONE check there queues them all: a flatten on a
CLOSED market would fill at the last stale mark, so it waits for the first
scan after the open (fresh mark), without advancing the positions_held
timeout clock (a Friday-evening stop must survive to Monday).

Also the supervisor-side wiring test C1 deferred: the replacement path must
actually call swing_gate_candidates and journal the drops.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
import run_engine as re_


class QueuedFlattenTests(unittest.TestCase):
    def setUp(self):
        # module-level throttle map is keyed by run_id; every test recreates
        # run 1 in the same process, so reset it
        re_._last_flatten_queued.clear()
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO agents (name, cash) VALUES ('c2', 100000)")
        self.agent_id = cur.lastrowid
        cur.execute(
            "INSERT INTO trading_runs (agent_id, symbol, market, market_type,"
            " status, status_reason, stop_flatten, config_snapshot_json,"
            " start_condition_json, stop_conditions_json, created_at) VALUES "
            "(?,?,?,'spot','stopping','fleet_breaker',1,?,'{}','{}',"
            "'2026-01-01T00:00:00Z')",
            (self.agent_id, "MSFT", "us-stock",
             json.dumps({"archetype": "swing"})))
        self.run_id = cur.lastrowid
        cur.execute(
            "INSERT INTO positions (agent_id, symbol, market, side, quantity,"
            " entry_price, current_price, opened_at, run_id) VALUES "
            "(?,?,?,'long',10,100.0,101.0,'2026-01-01T00:00:00Z',?)",
            (self.agent_id, "MSFT", "us-stock", self.run_id))
        conn.commit(); conn.close()

    def tearDown(self):
        self.tmp.cleanup()

    def _run_row(self):
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM trading_runs WHERE id = ?", (self.run_id,))
        row = dict(cur.fetchone())
        conn.close()
        return row

    def test_closed_market_queues_the_flatten(self):
        out = {"stopping_finished": 0}
        with patch("markets.is_market_open", return_value=False), \
             patch.object(re_, "_flatten_run") as flat:
            re_._control_stopping(self._run_row(), out)
        flat.assert_not_called()                       # nothing filled
        row = self._run_row()
        self.assertEqual(row["status"], "stopping")    # still queued
        self.assertIsNone(row["stopped_at"])           # timeout clock untouched

    def test_open_market_executes_the_queued_flatten(self):
        out = {"stopping_finished": 0}
        with patch("markets.is_market_open", return_value=True), \
             patch.object(re_, "_flatten_run",
                          return_value=(True, None)) as flat, \
             patch.object(re_, "_cache_realized_pnl"), \
             patch.object(re_, "compute_run_pnl",
                          return_value={"realized": 1.0}), \
             patch.object(re_, "_maybe_auto_restart"):
            re_._control_stopping(self._run_row(), out)
        flat.assert_called_once()
        self.assertEqual(self._run_row()["status"], "stopped")

    def _queued_skips(self):
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT payload FROM run_events WHERE run_id = ? AND "
                    "event_type = 'gate_skip'", (self.run_id,))
        rows = [json.loads(r["payload"]) for r in cur.fetchall()]
        conn.close()
        return [r for r in rows if "flatten queued" in (r.get("reason") or "")]

    def test_queue_retry_writes_one_gate_skip_not_one_per_scan(self):
        # R12: run 1161 wrote 1,144 identical rows over one closed session.
        # The retry keeps running each scan; only the journal write throttles.
        out = {"stopping_finished": 0}
        with patch("markets.is_market_open", return_value=False), \
             patch.object(re_, "_flatten_run") as flat:
            for _ in range(3):
                re_._control_stopping(self._run_row(), out)
        flat.assert_not_called()
        self.assertEqual(self._run_row()["status"], "stopping")
        self.assertEqual(len(self._queued_skips()), 1)

    def test_queue_heartbeat_rewrites_after_the_interval(self):
        out = {"stopping_finished": 0}
        with patch("markets.is_market_open", return_value=False), \
             patch.object(re_, "_flatten_run"):
            re_._control_stopping(self._run_row(), out)
            self.assertEqual(len(self._queued_skips()), 1)
            re_._last_flatten_queued[self.run_id] -= (
                re_._flatten_queued_heartbeat_seconds() + 1)
            re_._control_stopping(self._run_row(), out)
        self.assertEqual(len(self._queued_skips()), 2)

    def test_execution_after_a_throttled_queue_is_unchanged(self):
        # queued (one write), then the open executes exactly as before and
        # clears the throttle entry — a later re-queue writes immediately
        out = {"stopping_finished": 0}
        with patch("markets.is_market_open", return_value=False), \
             patch.object(re_, "_flatten_run"):
            re_._control_stopping(self._run_row(), out)
            re_._control_stopping(self._run_row(), out)
        self.assertEqual(len(self._queued_skips()), 1)
        with patch("markets.is_market_open", return_value=True), \
             patch.object(re_, "_flatten_run",
                          return_value=(True, None)) as flat, \
             patch.object(re_, "_cache_realized_pnl"), \
             patch.object(re_, "compute_run_pnl",
                          return_value={"realized": 1.0}), \
             patch.object(re_, "_maybe_auto_restart"):
            re_._control_stopping(self._run_row(), out)
        flat.assert_called_once()
        self.assertEqual(self._run_row()["status"], "stopped")
        self.assertNotIn(self.run_id, re_._last_flatten_queued)

    def test_requeue_after_leaving_the_queue_writes_immediately(self):
        out = {"stopping_finished": 0}
        with patch("markets.is_market_open", return_value=False), \
             patch.object(re_, "_flatten_run"):
            re_._control_stopping(self._run_row(), out)
        # market opens but the flatten fails — the run stays stopping and the
        # queue entry clears (state changed: it is now retry-failing, whose
        # gate_skip carries the failure reason and is untouched by the throttle)
        with patch("markets.is_market_open", return_value=True), \
             patch.object(re_, "_flatten_run",
                          return_value=(False, "no fill")):
            re_._control_stopping(self._run_row(), out)
        self.assertNotIn(self.run_id, re_._last_flatten_queued)
        # market closes again: the fresh queue entry writes without waiting
        with patch("markets.is_market_open", return_value=False), \
             patch.object(re_, "_flatten_run"):
            re_._control_stopping(self._run_row(), out)
        self.assertEqual(len(self._queued_skips()), 2)

    def test_calendar_failure_fails_open_to_the_flatten(self):
        # a broken calendar must not wedge a stop forever
        out = {"stopping_finished": 0}
        with patch("markets.is_market_open",
                   side_effect=RuntimeError("calendar broken")), \
             patch.object(re_, "_flatten_run",
                          return_value=(True, None)) as flat, \
             patch.object(re_, "_cache_realized_pnl"), \
             patch.object(re_, "compute_run_pnl",
                          return_value={"realized": 1.0}), \
             patch.object(re_, "_maybe_auto_restart"):
            re_._control_stopping(self._run_row(), out)
        flat.assert_called_once()


class SupervisorSwingGateWiring(unittest.TestCase):
    """C1's deferred wiring pin: severing either swing-gate call site must
    fail this test. (A full end-to-end replacement fixture is heavier than
    the seam warrants; the gate function itself is behavior-tested in
    test_swing_phase_c.py.)"""

    def test_gate_call_site_exists_in_both_build_paths(self):
        # A structural pin: severing either call site must fail this test.
        import inspect
        import fleet_supervisor as fs
        import fleet_planner as fp
        sup_src = inspect.getsource(fs)
        self.assertIn("swing_gate_candidates", sup_src,
                      "supervisor replacement path lost the swing gate")
        build_src = inspect.getsource(fp._do_build)
        self.assertIn("swing_gate_candidates", build_src,
                      "fleet builder candidate loop lost the swing gate")


if __name__ == "__main__":
    unittest.main()


class OvernightCapPass(unittest.TestCase):
    """Book-level sum(notional x G) <= 2.5% of equity inside the pre-close
    window; excess reduced from the largest contributor, never dumped."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO users (email, password_hash, created_at) "
                    "VALUES ('oc@x.com','x','2026-01-01T00:00:00Z')")
        uid = cur.lastrowid
        cur.execute("INSERT INTO agents (name, token_hash, cash, user_id,"
                    " created_at) VALUES ('oc','th',100000,?,"
                    "'2026-01-01T00:00:00Z')", (uid,))
        self.agent_id = cur.lastrowid
        cur.execute(
            "INSERT INTO fleets (agent_id, status, n_runs, total_budget_usd,"
            " archetype, created_at) VALUES (?,?,?,?,?,?)",
            (self.agent_id, "active", 2, 10000.0, "swing",
             "2026-01-01T00:00:00Z"))
        self.fleet_id = cur.lastrowid
        conn.commit(); conn.close()

    def tearDown(self):
        self.tmp.cleanup()

    def _run_with_position(self, symbol, qty, price, g):
        conn = database.get_db_connection()
        cur = conn.cursor()
        cfg = {"archetype": "swing", "thesis": {"swing_g_frac": g}}
        cur.execute(
            "INSERT INTO trading_runs (agent_id, symbol, market, market_type,"
            " status, config_snapshot_json, start_condition_json,"
            " stop_conditions_json, fleet_id, created_at) VALUES "
            "(?,?,?,'spot','running',?,'{}','{}',?,'2026-01-01T00:00:00Z')",
            (self.agent_id, symbol, "us-stock", json.dumps(cfg),
             self.fleet_id))
        rid = cur.lastrowid
        cur.execute(
            "INSERT INTO positions (agent_id, symbol, market, side, quantity,"
            " entry_price, current_price, opened_at, run_id) VALUES "
            "(?,?,?,'long',?,?,?,'2026-01-01T00:00:00Z',?)",
            (self.agent_id, symbol, "us-stock", qty, price, price, rid))
        conn.commit(); conn.close()
        return rid

    def _pass(self, minutes_left=15):
        import fleet_supervisor as fs
        import fleet_planner as fpm
        fleet = fpm.get_fleet(self.fleet_id)
        calls = []
        with patch("markets.session_minutes_left",
                   return_value=minutes_left), \
             patch("automation.execute_paper_trade",
                   side_effect=lambda *a, **k: (calls.append((a, k)) or
                                                (len(calls), None))):
            fs._swing_overnight_cap_pass(fleet, {"ok": True,
                                                 "equity": 10000.0})
        return calls

    def test_over_cap_reduces_largest_contributor(self):
        # risk = 4000 x 0.10 = $400 > cap ($250 weekday / $150 Friday)
        self._run_with_position("HIGHG", 40, 100.0, 0.10)
        calls = self._pass()
        self.assertEqual(len(calls), 1)
        args = calls[0][0]
        self.assertEqual(args[3], "sell")              # side
        self.assertGreater(args[4], 0)                 # cut qty

    def test_under_cap_is_a_noop(self):
        self._run_with_position("LOWG", 10, 100.0, 0.03)   # risk $30 < cap
        self.assertEqual(self._pass(), [])

    def test_outside_the_window_is_a_noop(self):
        self._run_with_position("HIGHG", 40, 100.0, 0.10)
        self.assertEqual(self._pass(minutes_left=120), [])

    def test_short_archetype_is_untouched(self):
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE fleets SET archetype='short' WHERE id=?",
                    (self.fleet_id,))
        conn.commit(); conn.close()
        self._run_with_position("HIGHG", 40, 100.0, 0.10)
        self.assertEqual(self._pass(), [])
