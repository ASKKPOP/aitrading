"""The desk is woken at the level it named (owner 2026-09-04: "All order
hold, it's not solution, it's not trading software").

Four rails were removed that day — loss budget, switch window,
plan-awareness, panel blindness — each a real measured defect, and the
trade count stayed at zero. What the desk actually said afterwards was
never about a rail:

    LIT : "Hold until price retraces into the 4.678-4.761 zone; current
           price is above entry range."
    ENA : "the entry itself is the disqualifier - price sits ABOVE my
           target, the easy leg is already spent."

Selection ranks candidates by how much they ALREADY moved, then asks for
an entry at market on a fixed interval. A desk with pullback discipline
can never say yes to that: by the time it looks, its level is behind it.
Measured: 0 of 49 authored zones were reached inside a slot's life, while
~9 of 19 sat inside the day's realized range.

This makes the zone a WAKE condition, never an order. Owner rule
2026-08-13 is untouched: the desk still authors every order, at market,
through every gate — it is merely present when its own condition is met.
"""

from __future__ import annotations

import inspect
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
import entry_router
import run_engine


class ZoneMathTests(unittest.TestCase):
    def setUp(self):
        entry_router._reset()

    tearDown = setUp

    def test_inclusive_containment(self):
        self.assertTrue(entry_router.in_zone(5.0, 4.0, 6.0))
        self.assertTrue(entry_router.in_zone(4.0, 4.0, 6.0))
        self.assertTrue(entry_router.in_zone(6.0, 4.0, 6.0))
        self.assertFalse(entry_router.in_zone(3.99, 4.0, 6.0))
        self.assertFalse(entry_router.in_zone(6.01, 4.0, 6.0))

    def test_a_zone_written_high_first_still_works(self):
        self.assertTrue(entry_router.in_zone(5.0, 6.0, 4.0))

    def test_junk_is_never_a_hit(self):
        for bad in (("x", 4.0, 6.0), (5.0, None, 6.0), (5.0, 4.0, "y")):
            self.assertFalse(entry_router.in_zone(*bad))


class PendingLifecycleTests(unittest.TestCase):
    def setUp(self):
        entry_router._reset()
        import os
        for k in ("ENTRY_ZONE_WAKE", "ENTRY_ZONE_RENOTE_MIN"):
            os.environ.pop(k, None)

    tearDown = setUp

    def test_a_touch_becomes_pending(self):
        self.assertTrue(entry_router.note_zone_hit(1, "ETH", 4.0, 6.0, 5.0))
        self.assertIsNotNone(entry_router.pending(1))
        self.assertEqual(entry_router.pending(1)["symbol"], "ETH")

    def test_a_second_touch_while_pending_is_a_noop(self):
        entry_router.note_zone_hit(1, "ETH", 4.0, 6.0, 5.0)
        self.assertFalse(entry_router.note_zone_hit(1, "ETH", 4.0, 6.0, 5.1))

    def test_a_ruling_clears_and_then_suppresses(self):
        """The desk said its piece; price still sitting in the zone must
        not re-wake it every 60 seconds — that is a spend loop."""
        entry_router.note_zone_hit(1, "ETH", 4.0, 6.0, 5.0)
        entry_router.clear(1)
        self.assertIsNone(entry_router.pending(1))
        self.assertFalse(entry_router.note_zone_hit(1, "ETH", 4.0, 6.0, 5.0),
                         "re-woken inside the think-window")

    def test_the_suppression_expires(self):
        import os
        os.environ["ENTRY_ZONE_RENOTE_MIN"] = "1"
        entry_router.note_zone_hit(2, "ETH", 4.0, 6.0, 5.0)
        entry_router.clear(2)
        # jump the clock past the think-window
        with patch.object(entry_router, "_now", lambda: 10_000_000.0):
            self.assertTrue(entry_router.note_zone_hit(2, "ETH", 4.0, 6.0, 5.0))

    def test_kill_switch(self):
        import os
        os.environ["ENTRY_ZONE_WAKE"] = "0"
        self.assertFalse(entry_router.enabled())
        self.assertFalse(entry_router.note_zone_hit(3, "ETH", 4.0, 6.0, 5.0))
        self.assertIsNone(entry_router.pending(3))


class ControlPassTests(unittest.TestCase):
    """What actually notes the touch."""

    def setUp(self):
        entry_router._reset()

    tearDown = setUp

    def _run(self):
        return {"id": 77, "agent_id": 6, "symbol": "LITUSDT",
                "market": "crypto", "status": "running"}

    def _touch(self, qty=0.0, plan=None, mark=4.70):
        plan = plan if plan is not None else {"kind": "zone", "low": 4.678,
                                              "high": 4.761}
        pnl = {"position": {"quantity": qty}}
        with patch.object(run_engine, "_live_entry_plan", lambda rid: plan), \
             patch("price_fetcher.get_price_from_market",
                   lambda *a, **k: mark), \
             patch.object(run_engine, "emit_telemetry_event",
                          lambda *a, **k: None):
            run_engine._note_entry_zone_touch(self._run(), pnl)
        return entry_router.pending(77)

    def test_price_entering_the_authored_zone_wakes_the_desk(self):
        """The live LIT case: 'hold until price retraces into 4.678-4.761'."""
        self.assertIsNotNone(self._touch(mark=4.70))

    def test_price_outside_the_zone_does_not(self):
        self.assertIsNone(self._touch(mark=5.20))

    def test_a_held_book_is_never_woken_for_an_entry(self):
        """An entry level means nothing while exposed; stops govern there."""
        self.assertIsNone(self._touch(qty=12.0, mark=4.70))

    def test_no_plan_or_a_trigger_plan_does_not_wake(self):
        self.assertIsNone(self._touch(plan={"kind": "none"}))
        self.assertIsNone(self._touch(plan={"kind": "trigger",
                                            "trigger": "breakout"}))

    def test_a_zone_without_numbers_does_not_wake(self):
        self.assertIsNone(self._touch(plan={"kind": "zone", "low": None,
                                            "high": 4.761}))

    def test_a_dead_feed_never_wakes_anything(self):
        pnl = {"position": {"quantity": 0.0}}
        def boom(*a, **k):
            raise RuntimeError("feed down")
        with patch.object(run_engine, "_live_entry_plan",
                          lambda rid: {"kind": "zone", "low": 4.6, "high": 4.8}), \
             patch("price_fetcher.get_price_from_market", boom), \
             patch.object(run_engine, "emit_telemetry_event", lambda *a, **k: None):
            run_engine._note_entry_zone_touch(self._run(), pnl)
        self.assertIsNone(entry_router.pending(77))


class WiringTests(unittest.TestCase):
    """A router nobody consults changes nothing."""

    def test_the_control_pass_notes_touches(self):
        """Cheap smoke check; the BEHAVIOURAL guarantee is
        ControlPassEndToEndTests below. A source-text pin passed a
        behaviour-killing mutation three separate times on 2026-09-04."""
        self.assertIn("_note_entry_zone_touch(",
                      inspect.getsource(run_engine._control_active))

    def test_a_touch_makes_the_run_due_now(self):
        src = inspect.getsource(run_engine.due_run_ids)
        self.assertIn("entry_router", src)
        self.assertIn("pending(", src)

    def test_a_cycle_clears_the_wake(self):
        self.assertIn("entry_router.clear(",
                      inspect.getsource(run_engine.run_cycle))

    def test_it_places_no_order(self):
        """Owner rule 2026-08-13: code convenes, the AI authors. This must
        wake the desk and never trade."""
        src = inspect.getsource(run_engine._note_entry_zone_touch)
        for forbidden in ("execute_paper_trade", "execute_trade", "_open_position"):
            self.assertNotIn(forbidden, src)


class ControlPassEndToEndTests(unittest.TestCase):
    """Drive the real control pass and assert the wake was noted.

    The source-text pin above passes a mutation that deletes the call's
    effect; this class does not. Same lesson as the three earlier ships
    today, applied before shipping rather than after review caught it."""

    def setUp(self):
        entry_router._reset()

    tearDown = setUp

    def _drive(self, mark):
        run = {"id": 91, "agent_id": 6, "symbol": "LITUSDT",
               "market": "crypto", "status": "running", "consecutive_errors": 0}
        pnl = {"total": 0.0, "realized": 0.0, "unrealized": 0.0, "trades": 0,
               "mark_age_ok": True, "position": {"quantity": 0.0}}
        with patch.object(run_engine, "_evaluate_stop", lambda r: None), \
             patch.object(run_engine, "compute_run_pnl", lambda r: pnl), \
             patch.object(run_engine, "_cache_realized_pnl", lambda *a: None), \
             patch.object(run_engine, "_ratchet_peak_pnl", lambda *a: None), \
             patch.object(run_engine, "_fire_armed_order", lambda *a: None), \
             patch.object(run_engine, "_maybe_emit_equity", lambda *a: None), \
             patch.object(run_engine, "emit_telemetry_event", lambda *a, **k: None), \
             patch.object(run_engine, "_live_entry_plan",
                          lambda rid: {"kind": "zone", "low": 4.678,
                                       "high": 4.761}), \
             patch("price_fetcher.get_price_from_market", lambda *a, **k: mark):
            run_engine._control_active(run, {})
        return entry_router.pending(91)

    def test_the_control_pass_really_wakes_on_a_zone_touch(self):
        self.assertIsNotNone(self._drive(4.70),
                             "the control pass did not note the touch")

    def test_and_stays_quiet_outside_the_zone(self):
        self.assertIsNone(self._drive(5.30))


class ClosedMarketTests(unittest.TestCase):
    """A shut market cannot fill, and the FEED DOES NOT SAY SO.

    Measured on prod 2026-09-05 with the NYSE closed:
    get_price_from_market returned NVDA 230.36 / PLTR 174.33 — the last
    close, not None. A zone holding that close would sit "touched" all
    night, re-waking the desk every think-window for a session that refuses
    every order."""

    def setUp(self):
        entry_router._reset()

    tearDown = setUp

    def _touch(self, is_open):
        run = {"id": 55, "agent_id": 6, "symbol": "NVDA", "market": "us-stock",
               "status": "running"}
        pnl = {"position": {"quantity": 0.0}}
        with patch("markets.is_market_open", return_value=is_open), \
             patch.object(run_engine, "_live_entry_plan",
                          lambda rid: {"kind": "zone", "low": 225.0,
                                       "high": 235.0}), \
             patch("price_fetcher.get_price_from_market",
                   lambda *a, **k: 230.36), \
             patch.object(run_engine, "emit_telemetry_event",
                          lambda *a, **k: None):
            run_engine._note_entry_zone_touch(run, pnl)
        return entry_router.pending(55)

    def test_a_closed_market_never_wakes_the_desk(self):
        self.assertIsNone(self._touch(is_open=False))

    def test_but_an_open_one_still_does(self):
        """The guard must not be a blanket off-switch."""
        self.assertIsNotNone(self._touch(is_open=True))

    def test_a_broken_calendar_fails_closed(self):
        run = {"id": 56, "agent_id": 6, "symbol": "NVDA", "market": "us-stock",
               "status": "running"}
        def boom(*a, **k):
            raise RuntimeError("calendar down")
        with patch("markets.is_market_open", boom), \
             patch.object(run_engine, "_live_entry_plan",
                          lambda rid: {"kind": "zone", "low": 225.0,
                                       "high": 235.0}), \
             patch("price_fetcher.get_price_from_market",
                   lambda *a, **k: 230.36), \
             patch.object(run_engine, "emit_telemetry_event",
                          lambda *a, **k: None):
            run_engine._note_entry_zone_touch(run, {"position": {"quantity": 0.0}})
        self.assertIsNone(entry_router.pending(56))


class PausedRunTests(unittest.TestCase):
    """A paused run can be woken but never dispatched.

    control_pass hands _control_active both running AND paused runs, while
    due_run_ids selects status='running'. So a wake noted on a paused run
    is never consumed: a wasted poll every window, a misleading journal row,
    and a permanent -1 on the idle-retire discount for a cycle that never
    ran. Pause blocks entries anyway."""

    def setUp(self):
        entry_router._reset()

    tearDown = setUp

    def _touch(self, status):
        run = {"id": 70, "agent_id": 6, "symbol": "ETH", "market": "crypto",
               "status": status}
        with patch("markets.is_market_open", return_value=True), \
             patch.object(run_engine, "_live_entry_plan",
                          lambda rid: {"kind": "zone", "low": 4.0, "high": 6.0}), \
             patch("price_fetcher.get_price_from_market", lambda *a, **k: 5.0), \
             patch.object(run_engine, "emit_telemetry_event", lambda *a, **k: None):
            run_engine._note_entry_zone_touch(run, {"position": {"quantity": 0.0}})
        return entry_router.pending(70)

    def test_a_paused_run_is_never_woken(self):
        self.assertIsNone(self._touch("paused"))

    def test_a_running_run_still_is(self):
        self.assertIsNotNone(self._touch("running"))

    def test_a_stopping_run_is_never_woken(self):
        self.assertIsNone(self._touch("stopping"))


class PollBudgetTests(unittest.TestCase):
    """The probe sits in the SERIAL control pass — the same loop that
    evaluates stops — and price_fetcher has no price cache. Unthrottled
    that is ~480-780 live fetches/hour, each with a 10s timeout, and a 429
    trips a provider-wide cooldown that starves the marks the stop system
    reads. An entry convenience must not sit on the exit path."""

    def setUp(self):
        entry_router._reset()
        for k in ("ENTRY_ZONE_POLL_SEC",):
            os.environ.pop(k, None)

    tearDown = setUp

    def test_the_second_probe_inside_the_window_is_refused(self):
        self.assertTrue(entry_router.should_poll(1))
        self.assertFalse(entry_router.should_poll(1))

    def test_it_reopens_after_the_window(self):
        entry_router.should_poll(1)
        with patch.object(entry_router, "_now", lambda: 10_000_000.0):
            self.assertTrue(entry_router.should_poll(1))

    def test_runs_are_throttled_independently(self):
        self.assertTrue(entry_router.should_poll(1))
        self.assertTrue(entry_router.should_poll(2))

    def test_the_throttle_actually_suppresses_the_fetch(self):
        """Behavioural: count real calls into the price feed."""
        calls = []
        run = {"id": 60, "agent_id": 6, "symbol": "ETH", "market": "crypto",
               "status": "running"}
        pnl = {"position": {"quantity": 0.0}}

        def feed(*a, **k):
            calls.append(1)
            return 99.0            # far outside the zone -> never pending

        for _ in range(5):
            with patch("markets.is_market_open", return_value=True), \
                 patch.object(run_engine, "_live_entry_plan",
                              lambda rid: {"kind": "zone", "low": 4.0,
                                           "high": 6.0}), \
                 patch("price_fetcher.get_price_from_market", feed), \
                 patch.object(run_engine, "emit_telemetry_event",
                              lambda *a, **k: None):
                run_engine._note_entry_zone_touch(run, pnl)
        self.assertEqual(len(calls), 1,
                         "the feed was hit on every pass despite the throttle")


class DispatchTests(unittest.TestCase):
    """The wake must actually make the run DUE.

    This class exists because the original source-text pin passed a
    mutation (`if entry_router.pending(...) and False:`) that kills the
    entire feature — noted forever, dispatched never. Adversarial review
    proved it on 2026-09-04; this drives the real due_run_ids instead."""

    def setUp(self):
        entry_router._reset()
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO agents (name, cash) VALUES ('c', 100000)")
        self.agent_id = cur.lastrowid
        conn.commit(); conn.close()

    def tearDown(self):
        entry_router._reset()
        self.tmp.cleanup()

    def _mk_run(self, cfg, last_cycle_at, market="crypto"):
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO trading_runs (agent_id, symbol, market, market_type,"
            " status, config_snapshot_json, start_condition_json,"
            " stop_conditions_json, last_cycle_at, created_at) VALUES "
            "(?,?,?,'spot','running',?,'{}','{}',?,?)",
            (self.agent_id, "ETHUSDT", market, json.dumps(cfg), last_cycle_at,
             "2026-01-01T00:00:00Z"))
        rid = cur.lastrowid
        conn.commit(); conn.close()
        return rid

    @staticmethod
    def _fresh():
        return (datetime.now(timezone.utc)
                - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ")

    def test_a_woken_run_is_due_before_its_interval_elapses(self):
        rid = self._mk_run({"interval_minutes": 60}, self._fresh())
        self.assertNotIn(rid, run_engine.due_run_ids(),
                         "fixture is wrong: the run was already due")
        entry_router.note_zone_hit(rid, "ETHUSDT", 4.0, 6.0, 5.0)
        self.assertIn(rid, run_engine.due_run_ids(),
                      "the wake did not dispatch the run")

    def test_a_wake_does_not_override_swing_dormancy(self):
        """Unlike a stop hit, an entry has no fail-safe clock, and
        `_order_gate_skip` refuses every order while shut — so a wake
        inside dormancy could only spend an LLM cycle and break the
        window's 'zero cycles, zero journal noise' contract."""
        cfg = {"interval_minutes": 30, "archetype": "swing",
               "analysis_window": {"pre_open_minutes": 120,
                                   "post_close_minutes": 120}}
        rid = self._mk_run(cfg, self._fresh(), market="us-stock")
        entry_router.note_zone_hit(rid, "NVDA", 225.0, 235.0, 230.0)
        with patch("markets.extended_session_state", return_value="closed"):
            self.assertNotIn(rid, run_engine.due_run_ids())

    def test_and_still_dispatches_inside_the_window(self):
        cfg = {"interval_minutes": 30, "archetype": "swing",
               "analysis_window": {"pre_open_minutes": 120,
                                   "post_close_minutes": 120}}
        rid = self._mk_run(cfg, self._fresh(), market="us-stock")
        entry_router.note_zone_hit(rid, "NVDA", 225.0, 235.0, 230.0)
        with patch("markets.extended_session_state", return_value="open"):
            self.assertIn(rid, run_engine.due_run_ids())


class SkippedCycleClearsTheWakeTests(DispatchTests):
    """A gate refusing IS a resolution of the wake.

    `_pre_gate_skip` returns from run_cycle ABOVE the `entry_router.clear`
    site, so without an explicit clear on that path the wake is never
    consumed: due_run_ids re-dispatches the run every control pass and each
    one lands right back on the same skip — a spin, not a decision.

    The codebase has already paid for this exact shape once. See
    `_cooldown_blocks`: a stop ruling died at a gate whose "return sits
    before stop_router.clear", and the fail-safe then dumped the book at
    2.00x the desk's own exit (SOL 1274, 2026-08-15)."""

    def test_a_pre_gate_skip_consumes_the_wake(self):
        rid = self._mk_run({"interval_minutes": 60}, self._fresh())
        entry_router.note_zone_hit(rid, "ETHUSDT", 4.0, 6.0, 5.0)
        self.assertIsNotNone(entry_router.pending(rid), "fixture is wrong")
        with patch.object(run_engine, "_pre_gate_skip",
                          lambda run, cfg: "pre: market closed"):
            run_engine.run_cycle(rid)
        self.assertIsNone(entry_router.pending(rid),
                          "the skipped cycle left the wake pending — "
                          "due_run_ids will spin on it every pass")

    def test_the_horizon_gate_also_consumes_the_wake(self):
        """The same spin hazard, one gate over. Dormant today only because
        _horizon_gate_enabled() defaults False — arming it would wake the
        bug, which is exactly how the SOL 1274 shape got shipped."""
        rid = self._mk_run({"interval_minutes": 60}, self._fresh())
        entry_router.note_zone_hit(rid, "ETHUSDT", 4.0, 6.0, 5.0)
        with patch.object(run_engine, "_horizon_gate_enabled",
                          lambda: True), \
             patch.object(run_engine, "_horizon_state",
                          lambda *a, **k: "horizon: hold"), \
             patch.object(run_engine, "_pre_gate_skip", lambda run, cfg: None):
            run_engine.run_cycle(rid)
        self.assertIsNone(entry_router.pending(rid),
                          "a horizon-gated cycle left the wake pending — "
                          "due_run_ids will spin on it every pass")

    def test_and_the_run_stops_being_due(self):
        """The consequence that actually matters: no re-dispatch loop."""
        rid = self._mk_run({"interval_minutes": 60}, self._fresh())
        entry_router.note_zone_hit(rid, "ETHUSDT", 4.0, 6.0, 5.0)
        self.assertIn(rid, run_engine.due_run_ids())
        with patch.object(run_engine, "_pre_gate_skip",
                          lambda run, cfg: "pre: market closed"):
            run_engine.run_cycle(rid)
        self.assertNotIn(rid, run_engine.due_run_ids(),
                         "the run is still due after being skipped — spin")


class IdleRetireDiscountTests(unittest.TestCase):
    """A wake must not accelerate the rail it exists to satisfy.

    `_claim` bumps cycle_seq on every claimed cycle, so a run parked in its
    zone runs ~2 cycles/hour instead of 1 and the count-based idle rail
    would collect it in ~6h instead of ~12h — retiring fastest exactly the
    run that is waiting patiently at the level it named."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO agents (name, cash) VALUES ('c', 100000)")
        agent_id = cur.lastrowid
        cur.execute(
            "INSERT INTO trading_runs (agent_id, symbol, market, market_type,"
            " status, config_snapshot_json, start_condition_json,"
            " stop_conditions_json, created_at) VALUES "
            "(?,'ETHUSDT','crypto','spot','running','{}','{}','{}',?)",
            (agent_id, "2026-01-01T00:00:00Z"))
        self.run_id = cur.lastrowid
        cur.execute(
            "INSERT INTO trading_runs (agent_id, symbol, market, market_type,"
            " status, config_snapshot_json, start_condition_json,"
            " stop_conditions_json, created_at) VALUES "
            "(?,'BTCUSDT','crypto','spot','running','{}','{}','{}',?)",
            (agent_id, "2026-01-01T00:00:00Z"))
        self.quiet_run_id = cur.lastrowid
        conn.commit(); conn.close()

    def tearDown(self):
        self.tmp.cleanup()

    def _note(self, run_id, n):
        """Write through the REAL emitter, so the event name the counter
        queries is the event name the wake actually writes — a hand-rolled
        INSERT would let those two drift apart silently."""
        for _ in range(n):
            run_engine.emit_telemetry_event(
                run_id, "entry_zone_touch",
                {"symbol": "ETH", "mark": 5.0, "low": 4.0, "high": 6.0})

    def test_wake_cycles_are_counted(self):
        self._note(self.run_id, 3)
        self.assertEqual(run_engine._entry_wake_cycles(self.run_id), 3)

    def test_a_run_with_no_wakes_is_unaffected(self):
        self.assertEqual(run_engine._entry_wake_cycles(self.quiet_run_id), 0)

    def test_other_event_types_are_not_miscounted(self):
        run_engine.emit_telemetry_event(self.run_id, "gate_skip",
                                        {"stage": "pre", "reason": "x"})
        self.assertEqual(run_engine._entry_wake_cycles(self.run_id), 0)

    # The end-to-end assertion that the discount actually spares a run from
    # idle-retire lives in test_idle_retire_closed_market.EntryWakeDiscount,
    # beside the rail it protects. It is NOT duplicated here: the version
    # that used to sit in this class re-implemented the rail's arithmetic in
    # the test body, which let a x100 discount and a flipped SIGN both pass.
    # Counting is pinned here; behaviour is pinned where the behaviour is.


if __name__ == "__main__":
    unittest.main()
