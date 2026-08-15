"""Stop-hit routing (owner 2026-08-13: "by AI it is main — programming
decision is optional"): a stop/target HIT on a live fleet run convenes the
desk's emergency discussion; the watcher's close is only the fail-safe.
Manual users' SL/TP semantics are untouched — that is a promise.

Live evidence behind the design: both of the day block's largest losses on
2026-08-13 (SLV −1.82, UBER −3.53) were watcher full-closes at desk-
authored levels the desk never got to reconsider at the moment they traded.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import automation
import database
import risk_engine
import run_engine
import stop_router


class RouterCoreTests(unittest.TestCase):
    def setUp(self):
        stop_router._reset()

    def tearDown(self):
        stop_router._reset()

    def test_first_hit_routes_and_repeat_hits_wait(self):
        self.assertTrue(stop_router.note_hit(9, 1, "stop_loss", 58.3))
        self.assertTrue(stop_router.note_hit(9, 1, "stop_loss", 58.2),
                        "the meeting is already convened — keep waiting")
        self.assertEqual(stop_router.pending(9)["trigger"], "stop_loss")

    def test_timeout_fails_safe_to_the_close(self):
        with patch.dict(os.environ, {"STOP_DESK_TIMEOUT_S": "0"}):
            self.assertTrue(stop_router.note_hit(9, 1, "stop_loss", 58.3))
            self.assertFalse(stop_router.note_hit(9, 1, "stop_loss", 58.1),
                             "expired window ⇒ programming closes")
        self.assertIsNone(stop_router.pending(9))

    def test_desk_ruling_clears_and_suppresses_relitigation(self):
        stop_router.note_hit(9, 1, "stop_loss", 58.3)
        stop_router.clear(9)
        self.assertIsNone(stop_router.pending(9))
        self.assertTrue(stop_router.note_hit(9, 1, "stop_loss", 58.2),
                        "suppressed re-note must not close either")
        self.assertIsNone(stop_router.pending(9),
                          "suppressed ⇒ no new meeting inside the window")

    def test_kill_switch(self):
        with patch.dict(os.environ, {"STOP_DESK_ROUTING": "0"}):
            self.assertFalse(stop_router.enabled())


class WatcherRoutingTests(unittest.TestCase):
    def setUp(self):
        stop_router._reset()
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO agents (name, cash) VALUES ('r', 10000)")
        self.agent_id = cur.lastrowid
        conn.commit()
        conn.close()

    def tearDown(self):
        stop_router._reset()
        self.tmp.cleanup()

    def _run_row(self, created_via="fleet", status="running"):
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO trading_runs (agent_id, symbol, market, market_type,"
            " status, config_snapshot_json, start_condition_json,"
            " stop_conditions_json, created_at, created_via) VALUES "
            "(?,?,?,'spot',?,'{}','{}','{}','2026-08-13T00:00:00Z',?)",
            (self.agent_id, "SLV", "us-stock", status, created_via))
        rid = cur.lastrowid
        conn.commit()
        conn.close()
        return rid

    def _pos(self, run_id):
        return {"id": 501, "run_id": run_id}

    def test_fleet_run_hit_is_routed_not_closed(self):
        rid = self._run_row()
        self.assertTrue(risk_engine._route_stop_hit_to_desk(
            self._pos(rid), "stop_loss", 58.3))
        self.assertIsNotNone(stop_router.pending(rid))

    def test_manual_position_closes_exactly_as_before(self):
        self.assertFalse(risk_engine._route_stop_hit_to_desk(
            {"id": 502, "run_id": None}, "stop_loss", 58.3))

    def test_non_fleet_run_closes_exactly_as_before(self):
        rid = self._run_row(created_via="user")
        self.assertFalse(risk_engine._route_stop_hit_to_desk(
            self._pos(rid), "stop_loss", 58.3))

    def test_dead_run_closes(self):
        rid = self._run_row(status="stopped")
        self.assertFalse(risk_engine._route_stop_hit_to_desk(
            self._pos(rid), "stop_loss", 58.3))

    def test_timeout_falls_back_to_the_close(self):
        rid = self._run_row()
        with patch.dict(os.environ, {"STOP_DESK_TIMEOUT_S": "0"}):
            self.assertTrue(risk_engine._route_stop_hit_to_desk(
                self._pos(rid), "stop_loss", 58.3))
            self.assertFalse(risk_engine._route_stop_hit_to_desk(
                self._pos(rid), "stop_loss", 58.1),
                "desk silent past the window ⇒ the fail-safe closes")

    def test_disabled_env_closes(self):
        rid = self._run_row()
        with patch.dict(os.environ, {"STOP_DESK_ROUTING": "0"}):
            self.assertFalse(risk_engine._route_stop_hit_to_desk(
                self._pos(rid), "stop_loss", 58.3))

    def test_watcher_loop_is_actually_WIRED(self):
        import inspect
        src = inspect.getsource(risk_engine.run_sltp_watcher_tick)
        self.assertIn("_route_stop_hit_to_desk(pos, trigger, price)", src,
                      "routing is not wired into the watcher loop")


class EngineSideTests(unittest.TestCase):
    def setUp(self):
        stop_router._reset()

    def tearDown(self):
        stop_router._reset()

    _RUN = {"id": 9, "agent_id": 1, "symbol": "SLV", "market": "us-stock"}

    def test_pending_hit_forces_the_full_discussion(self):
        stop_router.note_hit(9, 1, "stop_loss", 58.3)
        route = run_engine._classify_situation(self._RUN, {})
        self.assertEqual(route["route"], "full")
        self.assertEqual(route["triggers"], ["stop_hit"])

    def test_pending_hit_makes_the_run_due_now(self):
        import inspect
        src = inspect.getsource(run_engine.due_run_ids)
        self.assertIn("stop_router.pending(row[\"id\"])", src,
                      "stop-hit dispatch is not wired into due_run_ids")

    def test_stop_hit_line_renders_the_emergency(self):
        stop_router.note_hit(9, 1, "stop_loss", 58.3)
        line = run_engine._stop_hit_line(self._RUN)
        self.assertIn("STOP HIT", line)
        self.assertIn("stop_loss", line)
        self.assertIn("58.3", line)
        self.assertIn("fail-safe closes", line)

    def test_stop_hit_line_silent_without_a_hit(self):
        self.assertEqual(run_engine._stop_hit_line(self._RUN), "")

    def test_the_emergency_never_offers_an_option_the_code_cannot_execute(self):
        """The brief used to offer 'hold ONLY with a re-authored stop_pct'.

        No code path can apply that. `automation.execute_paper_trade` writes
        the bracket monotonically — `min()` for a short, `max()` for a long —
        so a WIDER stop is refused by design ('NEVER LOOSEN an existing exit
        level'); `risk_engine` only ratchets tighter; `orphan_reclaim` only
        fills a NULL; and run_engine consumes `stop_pct` only on an opening
        action. Live proof, prod 2026-08-15: run 1271 authored `stop_pct 1.23`
        at cycle 5 (-> 63,749) and `positions.stop_loss` stayed 63,163.5, the
        0.3% value written at open.

        Offering it is worse than useless: 'hold' is the branch that ends in
        the fail-safe close, so the brief steered the desk toward the one
        option that both fails silently and forfeits its authority."""
        stop_router.note_hit(9, 1, "stop_loss", 58.3)
        line = run_engine._stop_hit_line(self._RUN)
        self.assertNotIn("re-authored", line)
        self.assertNotIn("stop_pct", line)
        self.assertIn("cannot be widened", line,
                      "the desk must be told the stop is fixed, not invited "
                      "to move it")

    def test_the_bracket_rail_really_does_refuse_to_widen(self):
        """Pins the fact the brief's wording depends on. If a future change
        lets the desk widen a stop mid-life, this fails and the brief text
        has to be revisited with it."""
        import inspect
        src = inspect.getsource(automation.execute_paper_trade)
        self.assertIn("NEVER LOOSEN", src)
        self.assertIn("new_sl = min(", src, "short-side stop is not monotone")
        self.assertIn("new_sl = max(", src, "long-side stop is not monotone")

    def test_line_is_WIRED_into_both_prompts(self):
        import inspect
        self.assertIn("_stop_hit_line(run)",
                      inspect.getsource(run_engine._compose_position_state))
        for path in (run_engine._light_analysis, run_engine.run_cycle):
            self.assertIn("_compose_position_state(",
                          inspect.getsource(path))

    def test_a_routed_stop_hit_outranks_the_loss_cooldown(self):
        """The SOL 1274 sequence, live 2026-08-15 02:21–02:24Z: the desk's own
        de-risking half-cover was scored `losing_close`, arming a 3600s adapt
        cooldown; the stop then traded; SIX stop-hit priority dispatches at
        30s spacing all short-circuited at the cooldown gate (it returns
        before `stop_router.clear`); after the 180s router timeout the
        fail-safe dumped the book at 75.514 — exactly 2.00x worse than the
        desk's own exit on the same symbol/qty 14.5 min earlier (−0.88105 vs
        −0.44030). The shape re-armed twice more the same day (ETH 1272, BTC
        1271 — the latter blind for an hour at 0.17% from its stop).

        stop_router exists because of the owner rule 2026-08-13: the sooppiy
        AI is the MAIN author of stop exits; the watcher's close is only the
        fail-safe. A cooldown gate that structurally prevents the desk from
        ever ruling on its own stop reinstates the behaviour that module was
        built to abolish — precisely when it matters most, right after a
        loss. The emergency ruling must pass the gate; ordinary cycles in
        cooldown stay gated; the 180s fail-safe still binds a silent desk."""
        cooling = {"cooldown_until": "2999-01-01T00:00:00Z"}
        # cooldown, no hit: gates.
        self.assertTrue(run_engine._cooldown_blocks(9, cooling))
        # cooldown + routed hit: the emergency outranks the gate.
        stop_router.note_hit(9, 1, "stop_loss", 58.3)
        self.assertFalse(run_engine._cooldown_blocks(9, cooling),
                         "a run in adapt cooldown can never rule on its own "
                         "stop — the 180s timer sells the book instead")
        # and run_cycle must consult this predicate, not re-derive it.
        import inspect
        self.assertIn("_cooldown_blocks(run_id, adapt_state)",
                      inspect.getsource(run_engine.run_cycle))

    def test_ordinary_cooldown_cycles_stay_gated(self):
        """The bypass is for the emergency ruling ONLY."""
        cooling = {"cooldown_until": "2999-01-01T00:00:00Z"}
        # another run's hit must not open THIS run's gate
        stop_router.note_hit(8, 1, "stop_loss", 58.3)
        self.assertTrue(run_engine._cooldown_blocks(9, cooling))
        # no cooldown: never blocks
        self.assertFalse(run_engine._cooldown_blocks(9, {}))
        # router disabled: fail closed — the cooldown gates as before
        stop_router.note_hit(9, 1, "stop_loss", 58.3)
        with patch.dict(os.environ, {"STOP_DESK_ROUTING": "0"}):
            self.assertTrue(run_engine._cooldown_blocks(9, cooling))
        # router BROKEN: also fail closed — an exception must gate, not open
        with patch.object(stop_router, "pending",
                          side_effect=RuntimeError("router down")):
            self.assertTrue(run_engine._cooldown_blocks(9, cooling),
                            "a broken router must not silently disable the "
                            "loss cooldown")

    def test_decision_clears_the_pending_hit(self):
        import inspect
        src = inspect.getsource(run_engine.run_cycle)
        self.assertIn("stop_router.clear(run_id)", src,
                      "the desk's ruling must clear the noted hit")


if __name__ == "__main__":
    unittest.main()
