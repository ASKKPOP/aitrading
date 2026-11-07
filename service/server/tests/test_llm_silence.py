"""Operator alert when the desk LLM goes mute (llm_silence.py, 2026-11-07 sweep).

Two multi-day outages of the local LLM host (10-30→11-02, 11-05T21Z→) left the
desk deciding "scaffold hold" on 90%+ of cycles with no alert to anyone. These
tests pin: what counts as a mute decision (and that it tracks run_engine's own
infra-fallback reasons), the window query over run_events, the alert /
re-alert / recovery state machine, the fail-soft tick, and the task wiring.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
import llm_silence as ls

NOW = datetime(2026, 11, 7, 15, 0, 0, tzinfo=timezone.utc)
_ENV = ("LLM_SILENCE_ALERT", "LLM_SILENCE_WINDOW_MIN", "LLM_SILENCE_MIN_N",
        "LLM_SILENCE_MUTE_FRAC", "LLM_SILENCE_RECOVER_FRAC", "LLM_SILENCE_REALERT_H")


def _clear_env():
    for k in _ENV:
        os.environ.pop(k, None)


class MuteDecision(unittest.TestCase):
    def test_scaffold_is_mute(self):
        self.assertTrue(ls.is_mute_decision({"decided_by": "scaffold", "action": "hold"}))

    def test_rule_with_no_llm_response_is_mute(self):
        self.assertTrue(ls.is_mute_decision(
            {"decided_by": "rule", "fallback_reason": "no llm response"}))

    def test_rule_with_unparseable_json_is_mute(self):
        self.assertTrue(ls.is_mute_decision(
            {"decided_by": "rule", "fallback_reason": "decision json unparseable"}))

    def test_rule_the_desk_chose_is_not_mute(self):
        self.assertFalse(ls.is_mute_decision(
            {"decided_by": "rule", "fallback_reason": "market closed"}))

    def test_ai_verdict_is_not_mute(self):
        self.assertFalse(ls.is_mute_decision({"decided_by": "ai", "action": "hold"}))

    def test_garbage_is_not_mute(self):
        self.assertFalse(ls.is_mute_decision(None))
        self.assertFalse(ls.is_mute_decision("scaffold"))

    def test_reasons_track_run_engine(self):
        """The infra-fallback reasons are run_engine's; if it adds one, this
        module must learn it or the alert under-counts silence."""
        import run_engine
        src = __import__("inspect").getsource(run_engine)
        for reason in ls.INFRA_RULE_REASONS:
            self.assertIn(f'"{reason}"', src)
        self.assertIn('_INFRA_RULE_REASONS = ("no llm response", "decision json unparseable")', src)


class Evaluate(unittest.TestCase):
    def setUp(self):
        _clear_env()

    def tearDown(self):
        _clear_env()

    def test_silent_window_alerts_once(self):
        ev, st = ls.evaluate({"n": 40, "mute": 38, "frac": 0.95}, None, NOW)
        self.assertEqual(ev, ls.EVENT_SILENT)
        self.assertTrue(st["silent"])
        self.assertEqual(st["alerted_at"], "2026-11-07T15:00:00Z")
        ev2, st2 = ls.evaluate({"n": 40, "mute": 39, "frac": 0.975}, st,
                               NOW + timedelta(hours=1))
        self.assertIsNone(ev2, "still silent inside the re-alert window: no second alert")
        self.assertEqual(st2["alerted_at"], "2026-11-07T15:00:00Z")

    def test_realerts_after_the_realert_window(self):
        _, st = ls.evaluate({"n": 40, "mute": 38, "frac": 0.95}, None, NOW)
        ev, st2 = ls.evaluate({"n": 40, "mute": 38, "frac": 0.95}, st,
                              NOW + timedelta(hours=6, minutes=1))
        self.assertEqual(ev, ls.EVENT_SILENT)
        self.assertEqual(st2["alerted_at"], "2026-11-07T21:01:00Z")

    def test_too_small_a_window_changes_nothing(self):
        ev, st = ls.evaluate({"n": 3, "mute": 3, "frac": 1.0}, None, NOW)
        self.assertIsNone(ev)
        self.assertFalse(st["silent"])

    def test_healthy_desk_never_alerts(self):
        ev, st = ls.evaluate({"n": 300, "mute": 30, "frac": 0.1}, None, NOW)
        self.assertIsNone(ev)
        self.assertFalse(st["silent"])

    def test_recovery_notice_once_after_an_alert(self):
        _, st = ls.evaluate({"n": 40, "mute": 38, "frac": 0.95}, None, NOW)
        ev, st2 = ls.evaluate({"n": 40, "mute": 4, "frac": 0.1}, st, NOW + timedelta(hours=2))
        self.assertEqual(ev, ls.EVENT_RECOVERED)
        self.assertFalse(st2["silent"])
        ev3, _ = ls.evaluate({"n": 40, "mute": 4, "frac": 0.1}, st2, NOW + timedelta(hours=3))
        self.assertIsNone(ev3, "recovery is announced once")

    def test_partial_recovery_does_not_flap(self):
        """Between recover_frac and mute_frac the state holds: no re-alert,
        no recovery — one hour of half-answers is not a recovery."""
        _, st = ls.evaluate({"n": 40, "mute": 38, "frac": 0.95}, None, NOW)
        ev, st2 = ls.evaluate({"n": 40, "mute": 26, "frac": 0.65}, st, NOW + timedelta(hours=7))
        self.assertIsNone(ev)
        self.assertTrue(st2["silent"])

    def test_no_recovery_notice_when_no_alert_was_received(self):
        """Silent but every delivery failed (alerted_at None): a later recovery
        announces nothing — nobody was told of the silence."""
        ev, st = ls.evaluate({"n": 40, "mute": 4, "frac": 0.1},
                             {"silent": True, "alerted_at": None}, NOW)
        self.assertIsNone(ev)
        self.assertFalse(st["silent"])

    def test_thresholds_read_env(self):
        os.environ["LLM_SILENCE_MUTE_FRAC"] = "0.99"
        ev, _ = ls.evaluate({"n": 40, "mute": 38, "frac": 0.95}, None, NOW)
        self.assertIsNone(ev)
        os.environ["LLM_SILENCE_MIN_N"] = "50"
        os.environ["LLM_SILENCE_MUTE_FRAC"] = "0.8"
        ev, _ = ls.evaluate({"n": 40, "mute": 38, "frac": 0.95}, None, NOW)
        self.assertIsNone(ev)


class MeasureOnDb(unittest.TestCase):
    def setUp(self):
        _clear_env()
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO trading_runs (agent_id, symbol, market, market_type,"
            " status, config_snapshot_json, created_at) VALUES"
            " (6, 'BTCUSDT', 'crypto', 'futures', 'running', '{}', '2026-11-07T00:00:00Z')")
        conn.commit()
        conn.close()
        self._seq = 0

    def tearDown(self):
        _clear_env()
        self.tmp.cleanup()

    def _event(self, ts: str, payload: dict, event_type: str = "decision"):
        conn = database.get_db_connection()
        cur = conn.cursor()
        self._seq += 1
        cur.execute(
            "INSERT INTO run_events (run_id, seq, event_type, ts, payload)"
            " VALUES (1, ?, ?, ?, ?)", (self._seq, event_type, ts, json.dumps(payload)))
        conn.commit()
        conn.close()

    def test_counts_only_decisions_inside_the_window(self):
        mute = {"decided_by": "scaffold", "action": "hold"}
        ai = {"decided_by": "ai", "action": "hold", "confidence": 0.58}
        rule = {"decided_by": "rule", "fallback_reason": "no llm response"}
        self._event("2026-11-07T14:50:00Z", mute)
        self._event("2026-11-07T14:20:00Z", rule)
        self._event("2026-11-07T13:30:00Z", ai)
        self._event("2026-11-07T12:59:00Z", mute)            # outside a 120-min window
        self._event("2026-11-07T14:55:00Z", {"x": 1}, "gate_skip")  # not a decision
        self._event("2026-11-07T15:10:00Z", mute)            # after `now`
        s = ls.measure(NOW, 120)
        self.assertEqual((s["n"], s["mute"]), (3, 2))
        self.assertAlmostEqual(s["frac"], 2 / 3)
        self.assertEqual(s["since"], "2026-11-07T13:00:00Z")

    def test_window_bound_is_iso_t_form(self):
        """A space-separated bound would lexically pass every 'T' row of the
        day (HANDOFF §4 trap); the bound must be rendered with the T."""
        s = ls.measure(NOW, 60)
        self.assertRegex(s["since"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

    def test_tick_alerts_through_the_admin_channel_and_is_fail_soft(self):
        for i in range(12):
            self._event(f"2026-11-07T14:{10 + i:02d}:00Z", {"decided_by": "scaffold"})
        sent = []
        state = {"silent": False, "alerted_at": None}
        r = ls.tick(NOW, notify=lambda s, b: sent.append((s, b)) or {"channels": ["email"]},
                    state=state)
        self.assertEqual(r["event"], ls.EVENT_SILENT)
        self.assertEqual(len(sent), 1)
        self.assertIn("100%", sent[0][0])
        self.assertIn("12 of 12", sent[0][1])
        self.assertIn("LOCAL_LLM_BASE_URL", sent[0][1])
        self.assertEqual(r["sent"], {"channels": ["email"]})
        # a broken notifier never raises out of the tick
        def boom(s, b):
            raise RuntimeError("twilio down")
        state2 = {"silent": False, "alerted_at": None}
        r2 = ls.tick(NOW, notify=boom, state=state2)
        self.assertEqual(r2["event"], ls.EVENT_SILENT)
        self.assertEqual(r2["sent"]["channels"], [])

    def test_failed_delivery_does_not_stamp_the_alert(self):
        """Adversarial review #2: a SILENT alert nobody received must retry on
        the next tick, not go quiet for the re-alert window."""
        for i in range(12):
            self._event(f"2026-11-07T14:{10 + i:02d}:00Z", {"decided_by": "scaffold"})
        state = {"silent": False, "alerted_at": None}
        r = ls.tick(NOW, notify=lambda s, b: {"channels": []}, state=state)
        self.assertEqual(r["event"], ls.EVENT_SILENT)
        self.assertTrue(state["silent"])
        self.assertIsNone(state["alerted_at"], "unreached alert must not be stamped")
        sent = []
        r2 = ls.tick(NOW + timedelta(minutes=15),
                     notify=lambda s, b: sent.append(1) or {"channels": ["sms"]}, state=state)
        self.assertEqual(r2["event"], ls.EVENT_SILENT, "retried on the very next tick")
        self.assertEqual(state["alerted_at"], "2026-11-07T15:15:00Z")

    def test_state_persists_across_a_restart(self):
        """Adversarial review #1: state lives in platform_settings, so a worker
        restart mid-outage neither re-alerts on boot nor loses the recovery."""
        for i in range(12):
            self._event(f"2026-11-07T14:{10 + i:02d}:00Z", {"decided_by": "scaffold"})
        sent = []
        r = ls.tick(NOW, notify=lambda s, b: sent.append(s) or {"channels": ["email"]})
        self.assertEqual(r["event"], ls.EVENT_SILENT)
        self.assertTrue(r["persisted"])
        self.assertEqual(ls.load_state(), {"silent": True, "alerted_at": "2026-11-07T15:00:00Z"})
        # "restart": no in-memory state handed in; the persisted one must gate the re-alert
        r2 = ls.tick(NOW + timedelta(hours=1), notify=lambda s, b: sent.append(s) or {"channels": ["email"]})
        self.assertIsNone(r2["event"])
        self.assertEqual(len(sent), 1)
        # recovery after the "restart" is announced, from persisted state
        for i in range(12):
            self._event(f"2026-11-07T16:{10 + i:02d}:00Z", {"decided_by": "ai"})
        r3 = ls.tick(NOW + timedelta(hours=2), notify=lambda s, b: sent.append(s) or {"channels": ["email"]})
        self.assertEqual(r3["event"], ls.EVENT_RECOVERED)
        self.assertIn("recovered", sent[-1])
        self.assertEqual(ls.load_state(), {"silent": False, "alerted_at": None})

    def test_unreadable_persisted_state_is_fresh_state(self):
        from platform_settings import set_setting
        set_setting(ls.STATE_KEY, "not json {{{")
        self.assertEqual(ls.load_state(), {"silent": False, "alerted_at": None})

    def test_tick_is_quiet_on_a_healthy_desk(self):
        for i in range(12):
            self._event(f"2026-11-07T14:{10 + i:02d}:00Z", {"decided_by": "ai"})
        sent = []
        r = ls.tick(NOW, notify=lambda s, b: sent.append(1), state={"silent": False, "alerted_at": None})
        self.assertIsNone(r["event"])
        self.assertEqual(sent, [])

    def test_tick_survives_a_measure_failure(self):
        from unittest.mock import patch
        with patch.object(ls, "measure", side_effect=RuntimeError("db gone")):
            r = ls.tick(NOW, notify=lambda s, b: None, state={})
        self.assertIsNone(r["event"])
        self.assertIn("db gone", r["error"])


class EnvAndFormat(unittest.TestCase):
    def setUp(self):
        _clear_env()

    def tearDown(self):
        _clear_env()

    def test_env_float_bounds_and_garbage(self):
        os.environ["LLM_SILENCE_WINDOW_MIN"] = "abc"
        self.assertEqual(ls.window_minutes(), 120)
        os.environ["LLM_SILENCE_WINDOW_MIN"] = "5"
        self.assertEqual(ls.window_minutes(), 15, "floored at 15 min")
        os.environ["LLM_SILENCE_REALERT_H"] = "0"
        self.assertEqual(ls.realert_hours(), 0.25, "floored at 15 min")
        os.environ["LLM_SILENCE_MUTE_FRAC"] = "7"
        self.assertEqual(ls.mute_frac(), 1.0, "capped at 1.0")

    def test_recovered_format(self):
        subject, body = ls._format(ls.EVENT_RECOVERED, {"n": 40, "mute": 4, "frac": 0.1, "window_min": 120})
        self.assertIn("recovered", subject)
        self.assertIn("10%", subject)
        self.assertIn("4 of 40", body)


class Wiring(unittest.TestCase):
    def test_task_registered_with_a_role(self):
        from tasks import BACKGROUND_TASK_REGISTRY, BACKGROUND_TASK_ROLES
        self.assertIn("llm_silence", BACKGROUND_TASK_REGISTRY)
        self.assertEqual(BACKGROUND_TASK_ROLES["llm_silence"], "research")

    def test_loop_calls_tick_when_enabled(self):
        import inspect
        import tasks
        src = inspect.getsource(tasks.llm_silence_loop)
        self.assertIn("llm_silence_tick", src)
        self.assertIn("llm_silence_enabled()", src)

    def test_kill_switch(self):
        _clear_env()
        self.assertTrue(ls.enabled())
        os.environ["LLM_SILENCE_ALERT"] = "0"
        try:
            self.assertFalse(ls.enabled())
        finally:
            _clear_env()


if __name__ == "__main__":
    unittest.main()
