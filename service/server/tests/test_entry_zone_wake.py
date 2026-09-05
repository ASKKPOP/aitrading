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
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

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
                "market": "crypto"}

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


if __name__ == "__main__":
    unittest.main()


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
