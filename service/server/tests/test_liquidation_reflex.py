"""The T3 reflex executor — the half of Plan 16 that places an order.

Plan 16 shipped the oracle and the classifier, and reflex_action() returned
"flatten" into a counter nobody read: LIQ_REFLEX=true closed nothing. These
cover the wire from a T3 reading to an actual exit, and — more importantly —
every condition under which an armed daemon must refuse to pull the trigger.
"""
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import liquidation as L  # noqa: E402


def _state(**over):
    """A T3 reading that is clear to fire, so each test can spoil one field."""
    base = {
        "position_id": 42, "agent_id": 7, "run_id": 900,
        "symbol": "SOLUSDT", "market": "crypto", "side": "long",
        "quantity": 10.0, "entry_price": 100.0, "mark_price": 51.0,
        "mark_age_seconds": 12.0, "leverage": 2.0, "liq_price": 50.0,
        "health": 0.02, "tier": L.TIER_REFLEX, "source": "synthetic",
    }
    base.update(over)
    return base


class _Recorder:
    """Stands in for automation.execute_paper_trade."""

    def __init__(self, signal_id=1234, skip=None):
        self.calls = []
        self._ret = (signal_id, skip)

    def __call__(self, agent_id, symbol, market, action, qty, price, **kw):
        self.calls.append({"agent_id": agent_id, "symbol": symbol,
                           "market": market, "action": action, "qty": qty,
                           "price": price, **kw})
        return self._ret


class ReflexExecutorBase(unittest.TestCase):
    def setUp(self):
        self._prev = {k: os.environ.get(k) for k in
                      ("LIQ_REFLEX", "LIQ_REFLEX_MAX_STALE", "LIQ_REFLEX_RETRY")}
        os.environ["LIQ_REFLEX"] = "true"
        L._flatten_attempts.clear()
        self.rec = _Recorder()
        import automation
        self._real_trade = getattr(automation, "execute_paper_trade", None)
        automation.execute_paper_trade = self.rec
        import alerts
        self._real_alert = getattr(alerts, "send_alert", None)
        self.alerts = []
        alerts.send_alert = lambda *a, **k: self.alerts.append((a, k))

    def tearDown(self):
        for k, v in self._prev.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        L._flatten_attempts.clear()
        import automation
        if self._real_trade is not None:
            automation.execute_paper_trade = self._real_trade
        import alerts
        if self._real_alert is not None:
            alerts.send_alert = self._real_alert


class FiresTests(ReflexExecutorBase):
    def test_t3_long_places_a_full_size_sell(self):
        out = L.execute_reflex(_state(), now=1000.0)
        self.assertTrue(out["fired"], out)
        self.assertIsNone(out["reason"])
        self.assertEqual(len(self.rec.calls), 1)
        call = self.rec.calls[0]
        self.assertEqual(call["action"], "sell")
        self.assertEqual(call["qty"], 10.0)
        self.assertEqual(call["agent_id"], 7)
        self.assertEqual(call["run_id"], 900)

    def test_t3_short_covers_the_absolute_quantity(self):
        L.execute_reflex(_state(side="short", quantity=-8.5), now=1000.0)
        call = self.rec.calls[0]
        self.assertEqual(call["action"], "cover")
        self.assertEqual(call["qty"], 8.5)

    def test_orphan_with_no_run_still_closes(self):
        # The whole reason the scope is on positions rather than runs.
        out = L.execute_reflex(_state(run_id=None), now=1000.0)
        self.assertTrue(out["fired"])
        self.assertIsNone(self.rec.calls[0]["run_id"])

    def test_owner_is_alerted_with_a_translatable_label(self):
        L.execute_reflex(_state(), now=1000.0)
        self.assertEqual(len(self.alerts), 1)
        params = self.alerts[0][0][3]
        self.assertEqual(params["trigger_label"], "liquidation_defense")

    def test_alert_label_exists_in_every_language(self):
        # A msg_id or token absent from the catalogue is a broken alert in
        # every language, not a missing nicety.
        from notifications_i18n import TOKENS
        table = TOKENS["trigger_label"]
        for lang, values in table.items():
            self.assertIn("liquidation_defense", values,
                          f"trigger_label missing for {lang}")


class RefusesTests(ReflexExecutorBase):
    def _refused(self, state, reason, now=1000.0):
        # Counted rather than compared to [], so a test may refuse AFTER an
        # earlier deliberate fire (the cooldown case) and still prove that this
        # call placed nothing.
        before = len(self.rec.calls)
        out = L.execute_reflex(state, now=now)
        self.assertFalse(out["fired"])
        self.assertEqual(out["reason"], reason)
        self.assertEqual(len(self.rec.calls), before, "an order was placed anyway")

    def test_disarmed_flag_places_nothing(self):
        os.environ["LIQ_REFLEX"] = "false"
        self._refused(_state(), "not_reflex")

    def test_tier_below_t3_places_nothing(self):
        self._refused(_state(tier=L.TIER_DEFEND), "not_reflex")

    def test_stale_mark_refuses(self):
        os.environ["LIQ_REFLEX_MAX_STALE"] = "300"
        self._refused(_state(mark_age_seconds=901.0), "stale_mark")

    def test_fresh_mark_at_the_boundary_still_fires(self):
        os.environ["LIQ_REFLEX_MAX_STALE"] = "300"
        out = L.execute_reflex(_state(mark_age_seconds=300.0), now=1000.0)
        self.assertTrue(out["fired"], out)

    def test_unknown_mark_age_refuses(self):
        self._refused(_state(mark_age_seconds=None), "mark_age_unknown")

    def test_ownerless_position_refuses(self):
        self._refused(_state(agent_id=None), "no_owner")

    def test_flat_position_refuses(self):
        self._refused(_state(quantity=0.0), "flat")

    def test_nonpositive_mark_refuses(self):
        self._refused(_state(mark_price=0.0), "no_mark")

    def test_second_attempt_inside_the_window_is_a_cooldown(self):
        os.environ["LIQ_REFLEX_RETRY"] = "60"
        first = L.execute_reflex(_state(), now=1000.0)
        self.assertTrue(first["fired"])
        self._refused(_state(), "cooldown", now=1030.0)
        self.assertEqual(len(self.rec.calls), 1)

    def test_after_the_cooldown_it_retries(self):
        os.environ["LIQ_REFLEX_RETRY"] = "60"
        L.execute_reflex(_state(), now=1000.0)
        out = L.execute_reflex(_state(), now=1061.0)
        self.assertTrue(out["fired"], out)
        self.assertEqual(len(self.rec.calls), 2)

    def test_a_failed_close_reports_the_skip_and_still_holds_cooldown(self):
        self.rec._ret = (None, "insufficient_balance")
        out = L.execute_reflex(_state(), now=1000.0)
        self.assertFalse(out["fired"])
        self.assertEqual(out["reason"], "insufficient_balance")
        # The cooldown must hold even though nothing closed, or the 5s hot
        # cadence hammers a failing close twelve times a minute.
        again = L.execute_reflex(_state(), now=1010.0)
        self.assertEqual(again["reason"], "cooldown")

    def test_a_raising_close_still_holds_cooldown(self):
        def boom(*a, **k):
            raise RuntimeError("gateway down")
        import automation
        automation.execute_paper_trade = boom
        with self.assertRaises(RuntimeError):
            L.execute_reflex(_state(), now=1000.0)
        automation.execute_paper_trade = self.rec
        self.assertEqual(L.execute_reflex(_state(), now=1005.0)["reason"],
                         "cooldown")

    def test_no_state_at_all(self):
        out = L.execute_reflex(None, now=1000.0)
        self.assertFalse(out["fired"])
        self.assertEqual(out["reason"], "not_reflex")


class MarkAgeTests(unittest.TestCase):
    def test_iso_z_string(self):
        now = datetime(2026, 7, 30, 12, 0, tzinfo=timezone.utc)
        pos = {"price_updated_at": "2026-07-30T11:59:00Z"}
        self.assertAlmostEqual(
            L.mark_age_seconds(pos, now=now.timestamp()), 60.0, places=3)

    def test_sqlite_space_string(self):
        now = datetime(2026, 7, 30, 12, 0, tzinfo=timezone.utc)
        pos = {"price_updated_at": "2026-07-30 11:55:00"}
        self.assertAlmostEqual(
            L.mark_age_seconds(pos, now=now.timestamp()), 300.0, places=3)

    def test_mysql_datetime_object(self):
        # MySQL returns a datetime for a DATETIME column, which the string-only
        # parser in risk_engine would raise AttributeError on.
        now = datetime(2026, 7, 30, 12, 0, tzinfo=timezone.utc)
        pos = {"price_updated_at": now - timedelta(seconds=45)}
        self.assertAlmostEqual(
            L.mark_age_seconds(pos, now=now.timestamp()), 45.0, places=3)

    def test_missing_and_garbage(self):
        self.assertIsNone(L.mark_age_seconds({}))
        self.assertIsNone(L.mark_age_seconds({"price_updated_at": "not a date"}))
        self.assertIsNone(L.mark_age_seconds({"price_updated_at": 12345}))

    def test_future_timestamp_clamps_to_zero(self):
        now = datetime(2026, 7, 30, 12, 0, tzinfo=timezone.utc)
        pos = {"price_updated_at": now + timedelta(seconds=30)}
        self.assertEqual(L.mark_age_seconds(pos, now=now.timestamp()), 0.0)


class StateCarriesReflexInputsTests(unittest.TestCase):
    """margin_state must carry what execute_reflex needs, or the guard trips
    on every real position and the daemon silently never fires."""

    def test_agent_id_and_mark_age_reach_the_state(self):
        now = datetime(2026, 7, 30, 12, 0, tzinfo=timezone.utc)
        row = {"id": 5, "agent_id": 9, "run_id": None, "symbol": "BTCUSDT",
               "market": "crypto", "quantity": 1.0, "entry_price": 100.0,
               "current_price": 60.0, "leverage": 2.0,
               "price_updated_at": "2026-07-30T11:59:30Z"}
        st = L.margin_state(row, cushion_frac=0.85, now=now.timestamp())
        self.assertIsNotNone(st)
        self.assertEqual(st["agent_id"], 9)
        self.assertAlmostEqual(st["mark_age_seconds"], 30.0, places=3)

    def test_a_real_shaped_row_is_not_blocked(self):
        # End-to-end on the guard: the fields margin_state produces must
        # satisfy reflex_block_reason. This is the test that would have caught
        # shipping the executor without carrying agent_id.
        now = 1_800_000_000.0
        row = {"id": 5, "agent_id": 9, "run_id": None, "symbol": "BTCUSDT",
               "market": "crypto", "quantity": 1.0, "entry_price": 100.0,
               "current_price": 51.0, "leverage": 2.0,
               "price_updated_at": datetime.fromtimestamp(now - 10,
                                                          tz=timezone.utc)}
        st = L.margin_state(row, cushion_frac=0.85, now=now)
        L._flatten_attempts.clear()
        self.assertIsNone(L.reflex_block_reason(st, now=now))


class LoopWiringTests(unittest.TestCase):
    """The bug this whole change exists to fix.

    reflex_action() returned "flatten" into a counter nobody read, so
    LIQ_REFLEX=true closed nothing. Unit-testing execute_reflex alone would
    NOT have caught that — only driving the loop does.
    """

    def _run_one_tick(self, state):
        import asyncio
        import tasks

        fired = []

        class _StopTick(Exception):
            pass

        sleeps = {"n": 0}

        async def fake_sleep(_s):
            sleeps["n"] += 1
            if sleeps["n"] >= 2:      # first is the 12s settle, second ends it
                raise _StopTick()

        real_sleep = asyncio.sleep
        real_tick = L.watch_tick
        real_exec = L.execute_reflex
        asyncio.sleep = fake_sleep
        L.watch_tick = lambda *a, **k: {
            "checked": 1, "measured": 1, "escalations": 0,
            "worst": state["tier"], "reflex": 1, "states": [state]}
        L.execute_reflex = lambda s, *a, **k: (
            fired.append(s) or {"fired": True, "reason": None,
                                "signal_id": 1, "position_id": 1})
        try:
            with self.assertRaises(_StopTick):
                asyncio.run(tasks.liquidation_watch_loop())
        finally:
            asyncio.sleep = real_sleep
            L.watch_tick = real_tick
            L.execute_reflex = real_exec
        return fired

    def setUp(self):
        self._prev = os.environ.get("LIQ_REFLEX")
        os.environ["LIQ_REFLEX"] = "true"

    def tearDown(self):
        if self._prev is None:
            os.environ.pop("LIQ_REFLEX", None)
        else:
            os.environ["LIQ_REFLEX"] = self._prev

    def test_loop_executes_the_reflex_on_a_t3_state(self):
        fired = self._run_one_tick(_state())
        self.assertEqual(len(fired), 1,
                         "the watch loop measured T3 and placed no order")
        self.assertEqual(fired[0]["position_id"], 42)

    def test_loop_does_not_execute_below_t3(self):
        self.assertEqual(self._run_one_tick(_state(tier=L.TIER_DEFEND)), [])

    def test_loop_does_not_execute_when_disarmed(self):
        os.environ["LIQ_REFLEX"] = "false"
        self.assertEqual(self._run_one_tick(_state()), [])


if __name__ == "__main__":
    unittest.main()
