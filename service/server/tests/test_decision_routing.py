"""E1-A — situation-routed decision cycles (AI for the tails, cheap path for
the middle).

A deterministic, zero-LLM classifier (`run_engine._classify_situation`) reads
signals that already exist (macro event window, psych shock, regime, P&L near
the stop) and routes each fleet cycle: any trigger → the FULL analyst pipeline
(human factors); quiet → the light path. Gated by DECISION_ROUTING_ENABLED
(default off); an explicit per-run cycle_mode pin always wins. The chosen
route + triggers ride the decision telemetry event so every cycle is
explainable.
"""

from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
import fleet_planner as fp
import run_engine

from test_fleet_planner import FleetTestBase, _seed_batch


QUIET = dict(  # every signal silent → classifier must say "light"
    event=("market_events.active_event_window", None),
    psych=("psych_feed.get_psych_payload", {"available": False}),
    regime=("regime.current_regime_state", None),
)


def _quiet_patches():
    return [patch(t, return_value=v) for t, v in QUIET.values()]


def _run_row(market="crypto", stop_conditions=None):
    return {"id": 1, "agent_id": 1, "symbol": "BTC", "market": market,
            "market_type": "spot",
            "stop_conditions_json": json.dumps(stop_conditions or {})}


class ClassifierUnitTests(unittest.TestCase):
    """_classify_situation is pure routing logic over patchable signals."""

    def _classify(self, run=None, **overrides):
        patches = dict(QUIET)
        patches.update(overrides)
        ctxs = [patch(t, return_value=v) for t, v in patches.values()]
        for c in ctxs:
            c.start()
        try:
            return run_engine._classify_situation(run or _run_row(), {})
        finally:
            for c in ctxs:
                c.stop()

    def test_quiet_signals_route_light(self):
        out = self._classify()
        self.assertEqual(out["route"], "light")
        self.assertEqual(out["triggers"], [])

    def test_event_window_routes_full(self):
        out = self._classify(event=("market_events.active_event_window",
                                    {"title": "FOMC"}))
        self.assertEqual(out["route"], "full")
        self.assertIn("event_window", out["triggers"])

    def test_psych_shock_routes_full_for_crypto_only(self):
        shock = ("psych_feed.get_psych_payload",
                 {"available": True, "shock": [{"symbol": "BTC"}]})
        out = self._classify(psych=shock)
        self.assertEqual(out["route"], "full")
        self.assertIn("psych_shock", out["triggers"])
        # the shock proxy is crypto-wide OKX data — a us-stock run ignores it
        out = self._classify(run=_run_row(market="us-stock"), psych=shock)
        self.assertEqual(out["route"], "light")

    def test_regime_panic_routes_full_trend_does_not(self):
        out = self._classify(regime=("regime.current_regime_state",
                                     {"regime": "panic"}))
        self.assertEqual(out["route"], "full")
        self.assertIn("regime:panic", out["triggers"])
        out = self._classify(regime=("regime.current_regime_state",
                                     {"regime": "trend"}))
        self.assertEqual(out["route"], "light")

    def test_near_stop_routes_full(self):
        run = _run_row(stop_conditions={"max_loss_usd": 100.0})
        pnl = {"total": -55.0, "position": {"quantity": -1.0}, "mark_age_ok": True}
        with patch.object(run_engine, "compute_run_pnl", return_value=pnl):
            out = self._classify(run=run)
        self.assertEqual(out["route"], "full")
        self.assertIn("near_stop", out["triggers"])
        # small drawdown → quiet
        pnl2 = {"total": -20.0, "position": {"quantity": -1.0}, "mark_age_ok": True}
        with patch.object(run_engine, "compute_run_pnl", return_value=pnl2):
            out = self._classify(run=run)
        self.assertEqual(out["route"], "light")

    def test_signal_failures_fail_soft_to_light(self):
        boom = Exception("feed down")
        ctxs = [patch("market_events.active_event_window", side_effect=boom),
                patch("psych_feed.get_psych_payload", side_effect=boom),
                patch("regime.current_regime_state", side_effect=boom)]
        for c in ctxs:
            c.start()
        try:
            out = run_engine._classify_situation(_run_row(), {})
        finally:
            for c in ctxs:
                c.stop()
        self.assertEqual(out["route"], "light")

    def test_env_gate_default_off(self):
        os.environ.pop("DECISION_ROUTING_ENABLED", None)
        self.assertFalse(run_engine._decision_routing_enabled())
        os.environ["DECISION_ROUTING_ENABLED"] = "true"
        try:
            self.assertTrue(run_engine._decision_routing_enabled())
        finally:
            os.environ.pop("DECISION_ROUTING_ENABLED", None)


class RoutingCycleTests(FleetTestBase):
    """End-to-end: with routing on, a quiet cycle takes the light path even
    under FLEET_CYCLE_MODE=full; a triggered cycle runs the full pipeline;
    the route rides the decision event."""

    def setUp(self):
        super().setUp()
        os.environ["DECISION_ROUTING_ENABLED"] = "true"
        os.environ["FLEET_CYCLE_MODE"] = "full"   # routing must override this

    def tearDown(self):
        os.environ.pop("DECISION_ROUTING_ENABLED", None)
        os.environ.pop("FLEET_CYCLE_MODE", None)
        super().tearDown()

    def _member(self):
        _seed_batch()
        fleet_id = self._fleet(n=1, budget=1000.0)
        fp.start_fleet(fleet_id, self.agent_id)
        fp._do_research(fp.get_fleet(fleet_id))
        fp._do_build(fp.get_fleet(fleet_id))
        return fp.list_members(fleet_id)[0]

    def _decision_event(self, run_id):
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT payload FROM run_events WHERE run_id = ? AND "
                    "event_type = 'decision' ORDER BY id DESC LIMIT 1", (run_id,))
        row = cur.fetchone()
        conn.close()
        return json.loads(row["payload"]) if row else None

    def test_quiet_cycle_routes_light_despite_full_env(self):
        member = self._member()
        full_calls = []
        quiet = _quiet_patches()
        for c in quiet:
            c.start()
        try:
            with patch("analysis_agents.run_analysis",
                       side_effect=lambda *a, **k: full_calls.append(1)), \
                 patch("llm_client.generate_text",
                       return_value='{"action": "hold", "confidence": 0.55, '
                                    '"report": "quiet"}'), \
                 patch("price_fetcher.get_price_from_market", return_value=100.0), \
                 patch("price_fetcher.get_daily_candles", return_value=[]):
                run_engine.run_cycle(member["id"])
        finally:
            for c in quiet:
                c.stop()
        self.assertEqual(full_calls, [])          # full pipeline NOT used
        ev = self._decision_event(member["id"])
        self.assertIsNotNone(ev)
        self.assertEqual(ev["route"]["route"], "light")
        self.assertEqual(ev["route"]["triggers"], [])

    def test_triggered_cycle_routes_full(self):
        member = self._member()
        light_calls = []
        quiet = _quiet_patches()[1:]              # keep psych+regime quiet
        for c in quiet:
            c.start()
        try:
            with patch("market_events.active_event_window",
                       return_value={"title": "FOMC"}), \
                 patch("analysis_agents.run_analysis",
                       return_value={"decision": {"action": "hold",
                                                  "confidence": 0.5},
                                     "analysts": {}}) as full, \
                 patch("llm_client.generate_text",
                       side_effect=lambda *a, **k: light_calls.append(1)), \
                 patch("price_fetcher.get_price_from_market", return_value=100.0), \
                 patch("price_fetcher.get_daily_candles", return_value=[]):
                run_engine.run_cycle(member["id"])
        finally:
            for c in quiet:
                c.stop()
        self.assertEqual(full.call_count, 1)      # full pipeline used
        self.assertEqual(light_calls, [])         # light path skipped
        ev = self._decision_event(member["id"])
        self.assertEqual(ev["route"]["route"], "full")
        self.assertIn("event_window", ev["route"]["triggers"])

    def test_per_run_pin_beats_routing(self):
        member = self._member()
        cfg = json.loads(member["config_snapshot_json"])
        cfg["cycle_mode"] = "light"               # explicit user pin
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE trading_runs SET config_snapshot_json = ? WHERE id = ?",
                    (json.dumps(cfg), member["id"]))
        conn.commit()
        conn.close()
        with patch("market_events.active_event_window",
                   return_value={"title": "FOMC"}), \
             patch("psych_feed.get_psych_payload",
                   return_value={"available": False}), \
             patch("regime.current_regime_state", return_value=None), \
             patch("analysis_agents.run_analysis") as full, \
             patch("llm_client.generate_text",
                   return_value='{"action": "hold", "confidence": 0.55, '
                                '"report": "pinned"}'), \
             patch("price_fetcher.get_price_from_market", return_value=100.0), \
             patch("price_fetcher.get_daily_candles", return_value=[]):
            run_engine.run_cycle(member["id"])
        self.assertEqual(full.call_count, 0)      # pin wins over the trigger


if __name__ == "__main__":
    unittest.main()
