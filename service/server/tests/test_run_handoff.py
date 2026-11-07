"""Orphans after `stop_eval_failed` — docs/reports/2026-11-06-one-month-loss-analysis.md
§2.3 / §5 #4.

Three positions on the 10-05→11-06 tape were released by a run that stopped
`positions_held` (`stop_flatten 0`, after `stop_eval_failed`) and then sat
39–75 h with nobody deciding anything about them, until they were sold with
`run_id NULL` and no order id (−$2.82; who sold them is not recoverable).
The reclaim sweep WAS running on prod (every 15 min, exits enabled): it only
protects a bare orphan and only asks the desk about an orphan that refuses a
fleet slot — a released position that already carried a stop was "held" on
every pass, forever.

What these tests pin: a run that stops holding (1) stamps the position with
the run that released it, (2) journals the handoff on that run's tape,
(3) protects a bare position at once, not 15 minutes later, (4) is read by
the desk on the reclaim's NEXT pass whatever its age, and (5) whoever closes
the position afterwards — watcher or reclaim — writes an order id and a
run_event on the run that handed it off.
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
import orphan_reclaim as orc
import run_engine
import trading_runs
from automation import execute_paper_trade
from routes import create_app


def _ts(offset_seconds: float = 0) -> str:
    return (datetime.now(timezone.utc)
            + timedelta(seconds=offset_seconds)).strftime(trading_runs.TS_FMT)


class HandoffBase(unittest.TestCase):
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
            json={"name": "handoff-agent", "password": "pw123",
                  "initial_balance": 100000.0})
        self.token = resp.json()["token"]
        self.agent_id = resp.json()["agent_id"]

    def tearDown(self):
        self.probe.stop()
        os.environ.pop("AUTO_TRADING_ENABLED", None)
        os.environ.pop("ORPHAN_RECLAIM_ENABLED", None)
        self.tmp.cleanup()

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

    def _sql(self, sql, params=()):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            database.begin_write_transaction(cur)
            cur.execute(sql, params)
            conn.commit()
        finally:
            conn.close()

    def _one(self, sql, params=()):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute(sql, params)
            row = cur.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def _all(self, sql, params=()):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

    def _row(self, run_id):
        return self._one("SELECT * FROM trading_runs WHERE id = ?", (run_id,))

    def _position(self):
        return self._one("SELECT * FROM positions WHERE agent_id = ?",
                         (self.agent_id,))

    def _events(self, run_id, event_type):
        rows = self._all(
            "SELECT payload FROM run_events WHERE run_id = ? AND event_type = ? "
            "ORDER BY id", (run_id, event_type))
        return [json.loads(r["payload"] or "{}") for r in rows]

    def _trade(self, run_id, side, qty, price, key):
        signal_id, err = execute_paper_trade(
            self.agent_id, "BTC", "crypto", side, qty, price,
            run_id=run_id, client_order_id=f"run:{run_id}:test:{key}")
        assert signal_id, err
        return signal_id

    def _die_stop_eval_failed(self, stop=90.0) -> int:
        """The tape's path: running → stopping(stop_eval_failed, stop_flatten 0)
        → stopped(positions_held). Returns the run id."""
        run_id = self._run(stop_conditions={"max_loss_usd": 10.0})
        self._trade(run_id, "buy", 5.0, 100.0, "b1")
        # The desk's own stop sits on the row (not bare), marks go stale.
        self._sql("UPDATE positions SET stop_loss = ?, current_price = 97.0, "
                  "price_updated_at = ? WHERE agent_id = ?",
                  (stop, _ts(-7200), self.agent_id))
        self._sql("UPDATE trading_runs SET consecutive_errors = 4 WHERE id = ?",
                  (run_id,))
        run_engine.control_pass()
        self.assertEqual(self._row(run_id)["status_reason"], "stop_eval_failed")
        self.assertEqual(self._row(run_id)["status"], "stopping")
        run_engine.control_pass()
        row = self._row(run_id)
        self.assertEqual(row["status"], "stopped")
        self.assertEqual(row["status_reason"], "positions_held")
        return run_id


class HandoffOnPositionsHeld(HandoffBase):

    def test_the_released_position_remembers_the_run_that_held_it(self):
        run_id = self._die_stop_eval_failed()
        pos = self._position()
        self.assertAlmostEqual(float(pos["quantity"]), 5.0)
        self.assertIsNone(pos["run_id"], "release to the unowned book is unchanged")
        self.assertEqual(pos["handoff_run_id"], run_id)

    def test_the_handoff_is_journaled_on_the_runs_tape(self):
        run_id = self._die_stop_eval_failed(stop=90.0)
        held = self._events(run_id, "positions_held")
        self.assertEqual(len(held), 1, held)
        ev = held[0]
        self.assertEqual(ev["position_id"], self._position()["id"])
        self.assertAlmostEqual(float(ev["quantity"]), 5.0)
        self.assertAlmostEqual(float(ev["stop_loss"]), 90.0)
        self.assertEqual(ev["why"], "stop_eval_failed")
        self.assertFalse(ev["protected"], "a stop was already there")

    def test_a_bare_position_is_protected_at_the_handoff_not_a_sweep_later(self):
        run_id = self._run(stop_conditions={"max_loss_usd": 10.0})
        self._trade(run_id, "buy", 5.0, 100.0, "b1")
        self._sql("UPDATE positions SET stop_loss = NULL, take_profit = NULL, "
                  "current_price = 97.0, price_updated_at = ? WHERE agent_id = ?",
                  (_ts(-7200), self.agent_id))
        self._sql("UPDATE trading_runs SET consecutive_errors = 4 WHERE id = ?",
                  (run_id,))
        run_engine.control_pass()
        run_engine.control_pass()
        self.assertEqual(self._row(run_id)["status_reason"], "positions_held")
        pos = self._position()
        self.assertIsNotNone(pos["stop_loss"], "released bare — exactly the gap")
        # orphan_reclaim.protect's geometry: a losing long anchors on the mark
        self.assertLess(float(pos["stop_loss"]), 97.0)
        ev = self._events(run_id, "positions_held")[0]
        self.assertTrue(ev["protected"])
        self.assertAlmostEqual(float(ev["stop_loss"]), float(pos["stop_loss"]))

    def test_the_flatten_timeout_terminal_hands_off_too(self):
        run_id = self._run()
        self._trade(run_id, "buy", 5.0, 100.0, "b1")
        self._sql("UPDATE positions SET current_price = 100.0, price_updated_at = ? "
                  "WHERE agent_id = ?", (_ts(), self.agent_id))
        self.client.post(f"/api/runs/{run_id}/stop", json={"flatten": True},
                         headers=self._h())
        with patch("run_engine._manual_halt_blocks", return_value=True):
            run_engine.control_pass()
            self.assertEqual(self._row(run_id)["status"], "stopping")
            self._sql("UPDATE trading_runs SET stopped_at = ? WHERE id = ?",
                      (_ts(-7200), run_id))
            run_engine.control_pass()
        self.assertEqual(self._row(run_id)["status_reason"], "positions_held")
        self.assertEqual(self._position()["handoff_run_id"], run_id)
        ev = self._events(run_id, "positions_held")
        self.assertEqual(len(ev), 1)
        self.assertIn("halt", ev[0]["why"])


class HandoffReachesTheDesk(HandoffBase):
    """The 39–75 h gap. The sweep ran every 15 minutes the whole time; the
    position was minutes old when released, carried a stop, and refused no
    slot — so it was never scanned (grace) and never read (not blocking)."""

    def test_the_desk_reads_a_handed_off_position_on_the_next_sweep(self):
        run_id = self._die_stop_eval_failed(stop=90.0)
        pos = self._position()
        asked, executed = [], []
        os.environ["ORPHAN_RECLAIM_ENABLED"] = "true"
        out = orc.sweep(read_desk=lambda p: asked.append(p["id"]) or "sell",
                        execute=lambda p, v: executed.append((p["id"], v)),
                        blocking={})
        self.assertEqual(out["scanned"], 1,
                         "a position released minutes ago must not wait out the grace")
        self.assertEqual(asked, [pos["id"]], "no fleet slot refused, still asked")
        self.assertEqual([e[0] for e in executed], [pos["id"]])
        self.assertEqual(out["exited"], 1)
        # …and the verdict is on the dead run's tape, not lost in a fleet_id-0
        # fleet_events insert that fails on the FK.
        verdicts = self._events(run_id, "orphan_verdict")
        self.assertEqual(len(verdicts), 1, verdicts)
        self.assertEqual(verdicts[0]["verdict"], "sell")
        self.assertEqual(verdicts[0]["position_id"], pos["id"])

    def test_a_second_sweep_reuses_the_verdict_from_the_runs_tape(self):
        run_id = self._die_stop_eval_failed(stop=90.0)
        os.environ["ORPHAN_RECLAIM_ENABLED"] = "true"
        asked = []
        orc.sweep(read_desk=lambda p: asked.append(p["id"]) or "hold",
                  execute=lambda p, v: None, blocking={})
        orc.sweep(read_desk=lambda p: asked.append(p["id"]) or "hold",
                  execute=lambda p, v: None, blocking={})
        self.assertEqual(len(asked), 1, "cooldown must hold for a handoff too")
        self.assertEqual(len(self._events(run_id, "orphan_verdict")), 1)

    def test_an_unreadable_desk_holds_and_the_position_stays_protected(self):
        run_id = self._die_stop_eval_failed(stop=90.0)
        os.environ["ORPHAN_RECLAIM_ENABLED"] = "true"
        out = orc.sweep(read_desk=lambda p: None,
                        execute=lambda p, v: self.fail("must not close on a guess"),
                        blocking={})
        self.assertEqual(out["held"], 1)
        self.assertAlmostEqual(float(self._position()["stop_loss"]), 90.0)
        self.assertEqual(self._row(run_id)["status_reason"], "positions_held")


class HandoffSurvivesRunDeletion(HandoffBase):

    def test_deleting_the_stopped_run_turns_the_position_into_a_plain_orphan(self):
        """Adversarial review 2026-11-06: with the run row gone, the sweep's
        verdict journal on its tape fails on the run_events FK every pass
        (MySQL), the cooldown never caches, and the desk is re-billed every
        15 minutes. The stamp must go with the run."""
        run_id = self._die_stop_eval_failed(stop=90.0)
        trading_runs.delete_run(run_id, self.agent_id)
        self.assertIsNone(self._row(run_id))
        pos = self._position()
        self.assertIsNone(pos["handoff_run_id"])
        self.assertAlmostEqual(float(pos["quantity"]), 5.0)
        os.environ["ORPHAN_RECLAIM_ENABLED"] = "true"
        asked = []
        out = orc.sweep(read_desk=lambda p: asked.append(p["id"]) or "sell",
                        execute=lambda p, v: None, blocking={})
        # minutes old, no slot refused: back under the ordinary grace, not
        # a desk read with nowhere to journal it
        self.assertEqual(out["scanned"], 0, out)
        self.assertEqual(asked, [])


class HandoffTelemetryIsFailSoft(HandoffBase):

    def test_a_failing_journal_never_blocks_the_terminal_or_the_close(self):
        with patch("trading_runs.emit_telemetry_event",
                   side_effect=RuntimeError("journal down")):
            run_id = self._die_stop_eval_failed(stop=95.0)   # asserts positions_held
            pos = self._position()
            self.assertEqual(pos["handoff_run_id"], run_id)
            self._sql("UPDATE positions SET current_price = 94.0, price_updated_at = ? "
                      "WHERE agent_id = ?", (_ts(), self.agent_id))
            from risk_engine import run_sltp_watcher_tick
            with patch.dict(os.environ, {"RISK_ENGINE_ENABLED": "true"}):
                self.assertEqual(run_sltp_watcher_tick()["closed"], 1)
        self.assertEqual(self._events(run_id, "positions_held"), [])
        self.assertEqual(self._events(run_id, "stop_hit"), [])


class HandoffCloseIsAttributable(HandoffBase):

    def test_the_watcher_close_carries_an_order_id_and_a_run_event(self):
        run_id = self._die_stop_eval_failed(stop=95.0)
        pos = self._position()
        self._sql("UPDATE positions SET current_price = 94.0, price_updated_at = ? "
                  "WHERE agent_id = ?", (_ts(), self.agent_id))
        from risk_engine import run_sltp_watcher_tick
        with patch.dict(os.environ, {"RISK_ENGINE_ENABLED": "true"}):
            out = run_sltp_watcher_tick()
        self.assertEqual(out["closed"], 1)
        last = self._one("SELECT run_id, side, client_order_id, pnl FROM signals "
                         "WHERE agent_id = ? ORDER BY id DESC LIMIT 1",
                         (self.agent_id,))
        self.assertEqual(last["side"], "sell")
        self.assertIsNone(last["run_id"], "the run is finished; not its P&L row")
        self.assertTrue((last["client_order_id"] or "").startswith(
            f"orphan:{pos['id']}:watcher:stop_loss:"), last["client_order_id"])
        hits = self._events(run_id, "stop_hit")
        self.assertEqual(len(hits), 1, hits)
        self.assertEqual(hits[0]["mode"], "closed")
        self.assertEqual(hits[0]["position_id"], pos["id"])
        self.assertTrue(hits[0]["handoff"])
        self.assertEqual(hits[0]["client_order_id"], last["client_order_id"])

    def test_the_reclaim_close_writes_a_run_event(self):
        run_id = self._die_stop_eval_failed(stop=90.0)
        pos = self._position()
        self._sql("UPDATE positions SET current_price = 96.0, price_updated_at = ? "
                  "WHERE agent_id = ?", (_ts(), self.agent_id))
        os.environ["ORPHAN_RECLAIM_ENABLED"] = "true"
        out = orc.sweep(read_desk=lambda p: "sell", execute=orc.close_orphan,
                        blocking={})
        self.assertEqual(out["exited"], 1, out)
        last = self._one("SELECT client_order_id, pnl FROM signals "
                         "WHERE agent_id = ? ORDER BY id DESC LIMIT 1",
                         (self.agent_id,))
        self.assertEqual(last["client_order_id"], f"orphan:{pos['id']}:reclaim")
        closed = self._events(run_id, "orphan_closed")
        self.assertEqual(len(closed), 1, closed)
        self.assertEqual(closed[0]["position_id"], pos["id"])
        self.assertEqual(closed[0]["client_order_id"], last["client_order_id"])
        self.assertIsNotNone(closed[0]["signal_id"])
        pos_after = self._position()       # the ledger drops a flat row
        self.assertTrue(pos_after is None or float(pos_after["quantity"]) == 0.0)


if __name__ == "__main__":
    unittest.main()
