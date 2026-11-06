"""Stop-hit routing (owner 2026-08-13: "by AI it is main — programming
decision is optional"): a stop/target HIT on a live fleet run convenes the
desk's emergency discussion; the watcher's close is only the fail-safe.
Manual users' SL/TP semantics are untouched — that is a promise.

Live evidence behind the design: both of the day block's largest losses on
2026-08-13 (SLV −1.82, UBER −3.53) were watcher full-closes at desk-
authored levels the desk never got to reconsider at the moment they traded.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
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

    def _at(self, t):
        return patch.object(stop_router, "_now", lambda: float(t))

    def test_a_hit_is_pending_only_inside_the_desks_window(self):
        """`pending` is what makes a run due NOW, lifts its loss cooldown and
        writes the STOP HIT brief line. A hit nobody cleared kept doing all
        three for as long as the process lived (adversarial review round 2,
        2026-10-05: still due at +6h, six full-tier cycles). Past the
        fail-safe deadline the desk's window is over."""
        with self._at(1000):
            stop_router.note_hit(9, 1, "stop_loss", 58.3)
        with self._at(1179):
            self.assertIsNotNone(stop_router.pending(9))
        with self._at(1180):
            self.assertIsNone(stop_router.pending(9))
        # a desk that started deliberating gets its window from that start
        stop_router._reset()
        with self._at(1000):
            stop_router.note_hit(9, 1, "stop_loss", 58.3)
        with self._at(1100):
            stop_router.begin_ruling(9)
        with self._at(1279):
            self.assertIsNotNone(stop_router.pending(9))
        with self._at(1280):
            self.assertIsNone(stop_router.pending(9))

    def test_an_unruled_hit_still_meets_the_failsafe_while_in_breach(self):
        with self._at(1000):
            stop_router.note_hit(9, 1, "stop_loss", 58.3)
        for t in (1030, 1060, 1090, 1120, 1150):      # watcher scan ticks
            with self._at(t):
                self.assertTrue(stop_router.note_hit(9, 1, "stop_loss", 58))
        with self._at(1180):
            self.assertFalse(stop_router.note_hit(9, 1, "stop_loss", 57.9),
                             "still through the level at the deadline ⇒ "
                             "programming closes")

    def test_a_long_deliberation_still_ends_in_the_close(self):
        # Deadline 330s after the first note (ruling began at +150s). The
        # hit has been seen every scan, so it is the SAME breach and the
        # fail-safe closes — it is not mistaken for a new hit because the
        # note is old.
        with self._at(1000):
            stop_router.note_hit(9, 1, "stop_loss", 58.3)
        for t in range(1030, 1330, 30):
            with self._at(t):
                if t == 1150:
                    stop_router.begin_ruling(9)
                self.assertTrue(stop_router.note_hit(9, 1, "stop_loss", 58))
        with self._at(1330):
            self.assertFalse(stop_router.note_hit(9, 1, "stop_loss", 57.9))

    def test_a_ruling_that_lands_after_the_window_does_not_clear(self):
        """`pending` ends at the deadline, so a desk SELL landing at +215s
        is no longer stop-exempt and a panel hold can replace it. `clear`
        then popped the note and armed 30 minutes of suppression: hold, no
        fail-safe, watcher off (round 3, reproduced; prod kept the sell).
        Past the window the note belongs to the watcher."""
        with self._at(1000):
            stop_router.note_hit(9, 1, "stop_loss", 58.3)
        with self._at(1030):
            stop_router.begin_ruling(9)             # deadline 1210
        with self._at(1215):
            stop_router.clear(9)
        with self._at(1220):
            self.assertFalse(stop_router.note_hit(9, 1, "stop_loss", 57.9),
                             "a late verdict cancelled the fail-safe")

    def test_a_stale_note_cannot_arm_suppression(self):
        # Touch, bounce, nobody ruled; 25 minutes later an ordinary hold
        # settles. It ruled on nothing, so the next breach must be noted.
        with self._at(1000):
            stop_router.note_hit(9, 1, "stop_loss", 58.3)
        with self._at(2500):
            stop_router.clear(9)
        with self._at(2900):
            self.assertTrue(stop_router.note_hit(9, 1, "stop_loss", 57.0))
            self.assertIsNotNone(stop_router.pending(9),
                                 "the re-breach was suppressed, not noted")

    def test_a_slow_watcher_still_reaches_the_failsafe(self):
        # The new-hit gap must exceed the scan cadence, or every scan of a
        # continuous breach looks like a fresh one and nothing ever closes.
        with patch.dict(os.environ, {"RISK_WATCHER_INTERVAL": "600"}):
            with self._at(1000):
                stop_router.note_hit(9, 1, "stop_loss", 58.3)
            with self._at(1600):
                self.assertFalse(stop_router.note_hit(9, 1, "stop_loss", 57))

    def test_a_rebreach_after_the_price_left_is_a_new_hit(self):
        """Touch, bounce, nobody ruled. The stale note must not turn a
        breach a day later into an instant close with no desk window."""
        with self._at(1000):
            stop_router.note_hit(9, 1, "stop_loss", 58.3)
        with self._at(1030):
            stop_router.note_hit(9, 1, "stop_loss", 58.2)     # last seen
        with self._at(1000 + 86400):
            self.assertTrue(stop_router.note_hit(9, 1, "stop_loss", 57.0),
                            "a new breach closed on yesterday's clock")
            self.assertEqual(stop_router.pending(9)["price"], 57.0)
        with self._at(1000 + 86400 + 180):
            self.assertFalse(stop_router.note_hit(9, 1, "stop_loss", 56.9),
                             "the new hit has its own fail-safe")

    def test_the_failsafe_does_not_dump_mid_deliberation(self):
        """A desk actually DECIDING must not be fail-safed out from under
        its own ruling. SOL 1274 (2026-08-15): the fail-safe fired at 183s
        against the 180s window; dispatch alone can eat 30s and the
        emergency runs the expensive full tier, so a slow LLM cycle can
        cross the deadline mid-deliberation — the watcher then dumps the
        book AND the deliberation is wasted. Once run_cycle stamps
        `begin_ruling`, the hit gets one full timeout window measured from
        deliberation start, hard-bounded: a hung cycle still meets the
        fail-safe at (deciding_since + timeout)."""
        t = {"now": 1000.0}
        with patch.object(stop_router, "_now", side_effect=lambda: t["now"]):
            stop_router.note_hit(9, 1, "stop_loss", 58.3)
            t["now"] = 1170.0                    # 170s in, desk cycle starts
            stop_router.begin_ruling(9)
            t["now"] = 1200.0                    # 200s: past the raw window
            self.assertTrue(stop_router.note_hit(9, 1, "stop_loss", 58.2),
                            "the fail-safe dumped the book while the desk "
                            "was mid-deliberation")
            t["now"] = 1170.0 + stop_router.timeout_s() + 1.0
            self.assertFalse(stop_router.note_hit(9, 1, "stop_loss", 58.1),
                             "a hung deliberation must still meet the "
                             "fail-safe at the hard bound")

    def test_without_a_ruling_the_window_is_unchanged(self):
        """No begin_ruling => the original 180s clock, byte-for-byte."""
        t = {"now": 1000.0}
        with patch.object(stop_router, "_now", side_effect=lambda: t["now"]):
            stop_router.note_hit(9, 1, "stop_loss", 58.3)
            t["now"] = 1000.0 + stop_router.timeout_s() + 1.0
            self.assertFalse(stop_router.note_hit(9, 1, "stop_loss", 58.1))

    def test_begin_ruling_on_an_unnoted_run_is_a_noop(self):
        stop_router.begin_ruling(77)             # must not raise or create
        self.assertIsNone(stop_router.pending(77))

    def test_run_cycle_stamps_the_ruling_start(self):
        import inspect
        self.assertIn("stop_router.begin_ruling(run_id)",
                      inspect.getsource(run_engine.run_cycle),
                      "the desk never announces deliberation start — the "
                      "fail-safe cannot know it is mid-ruling")


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
        with patch.dict(os.environ, {"STOP_DESK_CLOSE_FIRST": "0"}):
            self.assertTrue(risk_engine._route_stop_hit_to_desk(
                self._pos(rid), "stop_loss", 58.3))
        self.assertIsNotNone(stop_router.pending(rid))
        hits = self._stop_hits(rid)
        self.assertEqual([h["mode"] for h in hits], ["routed"], hits)

    # ── 2026-11-06: close first; the desk never ruled inside its window ──
    # Tape 10-05→11-06 (docs/reports/2026-11-06-one-month-loss-analysis.md
    # §2.3): 0 of 26 stop hits received an AI ruling within 180s; the watcher
    # closed all 26, 25 of them past the authored stop ($1.95 slippage), and
    # once (UNI 10-08) the late ruling re-shorted 20× larger 47s after the
    # fail-safe cover. The default is now: close AT the stop, journal the
    # hit so the next tape can attribute it, and fence re-entry.

    def _stop_hits(self, rid):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT payload FROM run_events WHERE run_id = ? AND "
                        "event_type = 'stop_hit' ORDER BY id", (rid,))
            return [json.loads(r["payload"]) for r in cur.fetchall()]
        finally:
            conn.close()

    def test_close_first_is_the_default(self):
        rid = self._run_row()
        self.assertFalse(risk_engine._route_stop_hit_to_desk(
            self._pos(rid), "stop_loss", 58.3), "default must close at the stop")
        self.assertIsNone(stop_router.pending(rid), "nothing routed to the desk")
        # The close is journaled by the watcher loop once it happens (mode
        # "closed", see test_run_stops), never here — a skipped close must
        # not journal the same hit on every scan.
        self.assertEqual(self._stop_hits(rid), [])

    def test_failsafe_close_in_routed_mode_is_journaled_too(self):
        rid = self._run_row()
        with patch.dict(os.environ, {"STOP_DESK_CLOSE_FIRST": "0",
                                     "STOP_DESK_TIMEOUT_S": "0"}):
            self.assertTrue(risk_engine._route_stop_hit_to_desk(
                self._pos(rid), "stop_loss", 58.3))
            self.assertFalse(risk_engine._route_stop_hit_to_desk(
                self._pos(rid), "stop_loss", 58.1))
        modes = [h["mode"] for h in self._stop_hits(rid)]
        self.assertEqual(modes, ["routed", "failsafe_close"], modes)

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
        with patch.dict(os.environ, {"STOP_DESK_CLOSE_FIRST": "0",
                                     "STOP_DESK_TIMEOUT_S": "0"}):
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


class ReentryFenceTests(unittest.TestCase):
    """After a watcher stop close the same symbol must not be re-opened for
    STOP_REENTRY_FENCE_MIN (default 30): UNI 10-08 was covered by the
    fail-safe at 00:51:43Z and re-shorted 20× larger by the desk at
    00:52:30Z, stopped again 15 min later (−$2.67)."""

    def test_inside_the_fence_is_refused(self):
        now = datetime(2026, 10, 8, 0, 52, 30, tzinfo=timezone.utc)
        reason = run_engine._stop_reentry_fence_reason("2026-10-08T00:51:43Z", now)
        self.assertIsNotNone(reason)
        self.assertIn("fence", reason)

    def test_outside_the_fence_is_free(self):
        now = datetime(2026, 10, 8, 1, 30, 0, tzinfo=timezone.utc)
        self.assertIsNone(run_engine._stop_reentry_fence_reason(
            "2026-10-08T00:51:43Z", now))

    def test_no_watcher_close_no_fence(self):
        now = datetime(2026, 10, 8, 0, 52, 30, tzinfo=timezone.utc)
        self.assertIsNone(run_engine._stop_reentry_fence_reason(None, now))

    def test_env_zero_disables(self):
        now = datetime(2026, 10, 8, 0, 52, 30, tzinfo=timezone.utc)
        with patch.dict(os.environ, {"STOP_REENTRY_FENCE_MIN": "0"}):
            self.assertIsNone(run_engine._stop_reentry_fence_reason(
                "2026-10-08T00:51:43Z", now))

    def test_fence_is_WIRED_into_the_pre_gate(self):
        import inspect
        src = inspect.getsource(run_engine._pre_gate_skip)
        self.assertIn("_stop_reentry_fence_reason(", src)
        self.assertIn(":watcher:", src, "the fence must key on the watcher's order id")

    def test_watcher_close_carries_its_order_id(self):
        import inspect
        src = inspect.getsource(risk_engine.run_sltp_watcher_tick)
        self.assertIn(":watcher:", src, "the watcher close has no client_order_id — "
                      "it is invisible on the tape (29 NULL-coid exits on 10-05→11-06)")


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
        stop_router.note_hit(9, 1, "stop_loss", 10.0)
        run_engine._settle_stop_hit(9, {"action": "hold",
                                        "decided_by": "ai"})
        self.assertIsNone(stop_router.pending(9),
                          "the desk's ruling must clear the noted hit")
        # wiring: the cycle settles through the helper, with the decision
        import inspect
        self.assertIn("_settle_stop_hit(run_id, decision)",
                      inspect.getsource(run_engine.run_cycle))

    def _cycle(self, decision):
        """One REAL run_cycle for a run with a noted stop hit."""
        import json
        import tempfile as _tf
        from datetime import datetime, timedelta, timezone
        tmp = _tf.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(tmp.name, "t.db")
        database.init_database()
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO agents (name, cash) VALUES ('c', 100000)")
        fresh = (datetime.now(timezone.utc)
                 - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        cur.execute(
            "INSERT INTO trading_runs (agent_id, symbol, market, market_type,"
            " status, config_snapshot_json, start_condition_json,"
            " stop_conditions_json, last_cycle_at, created_at) VALUES "
            "(?,?,?,'spot','running',?,'{}','{}',?,?)",
            (cur.lastrowid, "ETHUSDT", "crypto",
             json.dumps({"interval_minutes": 60}), fresh,
             "2026-01-01T00:00:00Z"))
        rid = cur.lastrowid
        conn.commit()
        conn.close()
        stop_router.note_hit(rid, 1, "stop_loss", 100.0)
        with patch("analysis_agents.run_analysis",
                   return_value={"decision": decision, "analysts": {}}), \
             patch.object(run_engine, "_pre_gate_skip",
                          lambda run, cfg: None):
            self.assertIn(rid, run_engine.due_run_ids(),
                          "fixture: the noted hit did not dispatch the run")
            run_engine.run_cycle(rid)
        return rid

    def test_run_cycle_settles_with_the_decision_it_made(self):
        """The seam. `_settle_stop_hit(run_id, {})` — the round-1 bug with
        the right function name on it — passed every test in the tree."""
        rid = self._cycle({"action": "hold", "confidence": 0.6,
                           "decided_by": "ai", "report": "stop re-authored"})
        self.assertIsNone(stop_router.pending(rid),
                          "the desk ruled and the hit was not cleared")
        stop_router._reset()
        rid = self._cycle({"action": "hold", "confidence": 0.0,
                           "decided_by": "rule",
                           "fallback_reason": "no llm response",
                           "report": "Technical signal is 'buy'"})
        self.assertIsNotNone(stop_router.pending(rid),
                             "a hold nobody authored cancelled the fail-safe")
        # ...and the run stops being dispatched for it once the window ends
        import time as _time
        with patch.object(stop_router, "_now",
                          lambda: _time.monotonic() + stop_router.timeout_s()):
            self.assertNotIn(rid, run_engine.due_run_ids())

    def test_an_unlabelled_decision_still_clears(self):
        # Older producers stamp no decided_by; absence is not "not the AI".
        stop_router.note_hit(9, 1, "stop_loss", 10.0)
        run_engine._settle_stop_hit(9, {"action": "sell"})
        self.assertIsNone(stop_router.pending(9))

    def test_a_hold_nobody_authored_does_not_cancel_the_failsafe(self):
        """`clear` means "a desk decision cycle ran, its verdict governs".
        A rule fallback or a no-verdict scaffold is not a verdict: the
        trader returned nothing. Clearing on it cancelled the fail-safe and
        suppressed re-noting for 30 minutes, so a position sat through its
        own breached stop for as long as the LLM stayed down (adversarial
        review 2026-10-05, reproduced through run_cycle). Left pending, the
        watcher closes at the timeout exactly as it does for a silent
        desk."""
        for label in ("rule", "scaffold"):
            stop_router._reset()
            stop_router.note_hit(9, 1, "stop_loss", 10.0)
            run_engine._settle_stop_hit(9, {"action": "hold",
                                            "decided_by": label})
            self.assertIsNotNone(stop_router.pending(9), label)
            # ...and the fail-safe still fires on schedule
            with patch.object(stop_router, "_now",
                              lambda: __import__("time").monotonic()
                              + stop_router.timeout_s() + 1):
                self.assertFalse(stop_router.note_hit(9, 1, "stop_loss",
                                                      9.9), label)


if __name__ == "__main__":
    unittest.main()
