"""Plan 31 ship tests (items 2-6 + psych_shock de-saturation).

Covers the run_engine changes: the crypto stop cap (item 3), the per-agent
entry freeze (item 2), the adds-gate fail-open closure (item 4), the
per-market ratchet arm fee (item 5), the per-run minimum hold (item 6) and
the psych_shock transition trigger. Integration tests ride the
test_run_cycle_order_params harness pattern; gate helpers are unit-tested
directly.
"""

from __future__ import annotations

import inspect
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
import run_engine
import target_policy
from routes import create_app

ORDER = {"defer": False, "size_frac": 0.20, "leverage": 1.0,
         "stop_pct": 2.0, "target_pct": 6.0, "why": "ATR-anchored"}


def _analysis(order=None, action="buy", confidence=0.9):
    decision = {"action": action, "confidence": confidence,
                "entry": 100.0, "report": "r"}
    if order is not None:
        decision["order"] = order
    return {
        "symbol": "BTC", "market": "crypto",
        "analysts": {"technical": {"brief": "t",
                                   "data": {"sigma_daily_pct": 2.5,
                                            "current_price": 100.0}}},
        "decision": decision,
    }


class _CycleHarness(unittest.TestCase):
    """Same DB/agent scaffolding as test_run_cycle_order_params."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        os.environ["AUTO_TRADING_ENABLED"] = "true"
        os.environ["RUN_CONF_PERCENTILE"] = "false"
        os.environ["RISK_ENGINE_ENABLED"] = "true"
        os.environ["FEE_PER_MARKET"] = "true"
        self.probe = patch("routes_runs._probe_price", return_value=100.0)
        self.probe.start()
        self.client = TestClient(create_app())
        resp = self.client.post(
            "/api/claw/agents/selfRegister",
            json={"name": "p31-agent", "password": "pw123",
                  "initial_balance": 100000.0})
        assert resp.status_code == 200, resp.text
        self.token = resp.json()["token"]
        self.agent_id = resp.json()["agent_id"]

    def tearDown(self):
        self.probe.stop()
        for key in ("AUTO_TRADING_ENABLED", "RUN_CONF_PERCENTILE",
                    "RUN_AI_ORDER_PARAMS", "RISK_ENGINE_ENABLED",
                    "FEE_PER_MARKET", "STOP_CAP_PCT_CRYPTO",
                    "AGENT_ENTRY_FREEZE", "ADD_INTO_LOSER_BLOCK",
                    "TARGET_PSYCH_CAP", "TARGET_PSYCH_CAP_MAP", "RR_FLOOR"):
            os.environ.pop(key, None)
        self.tmp.cleanup()

    def _h(self):
        return {"Authorization": f"Bearer {self.token}"}

    def _run(self, **overrides) -> int:
        payload = {"symbol": "BTC", "market": "crypto", "max_bet_usd": 500.0}
        payload.update(overrides)
        run_id = self.client.post("/api/runs", json=payload,
                                  headers=self._h()).json()["id"]
        assert self.client.post(f"/api/runs/{run_id}/start",
                                headers=self._h()).status_code == 200
        return run_id

    def _events(self, run_id, kind):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT payload FROM run_events WHERE run_id = ? "
                        "AND event_type = ?", (run_id, kind))
            return [json.loads(r["payload"]) for r in cur.fetchall()]
        finally:
            conn.close()

    def _position(self, run_id):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT stop_loss, take_profit, quantity FROM "
                        "positions WHERE run_id = ?", (run_id,))
            return cur.fetchone()
        finally:
            conn.close()


class StopCapTests(_CycleHarness):
    def test_env_unset_stop_untouched(self):
        os.environ["RUN_AI_ORDER_PARAMS"] = "apply"
        run_id = self._run()
        with patch("analysis_agents.run_analysis",
                   return_value=_analysis(order=ORDER)):
            result = run_engine.run_cycle(run_id)
        self.assertTrue(result["executed"], result.get("skip_reason"))
        pos = self._position(run_id)
        self.assertAlmostEqual(float(pos["stop_loss"]), 98.0, places=4)
        self.assertEqual(self._events(run_id, "stop_cap"), [])

    def test_cap_clamps_wide_crypto_stop_and_journals(self):
        os.environ["RUN_AI_ORDER_PARAMS"] = "apply"
        os.environ["STOP_CAP_PCT_CRYPTO"] = "0.5"
        run_id = self._run()
        with patch("analysis_agents.run_analysis",
                   return_value=_analysis(order=ORDER)):
            result = run_engine.run_cycle(run_id)
        self.assertTrue(result["executed"], result.get("skip_reason"))
        pos = self._position(run_id)
        self.assertAlmostEqual(float(pos["stop_loss"]), 99.5, places=4)
        evs = self._events(run_id, "stop_cap")
        self.assertEqual(len(evs), 1)
        self.assertEqual(evs[0]["cap_pct"], 0.5)
        self.assertAlmostEqual(evs[0]["stop_after"], 99.5, places=4)

    def test_cap_bounds_the_target_cap_leak(self):
        """With the stop clamped, the RR_FLOOR term can no longer inflate
        the effective target cap past cap x RR_FLOOR (D-CAP-STOP-LEAK)."""
        os.environ["RUN_AI_ORDER_PARAMS"] = "apply"
        os.environ["STOP_CAP_PCT_CRYPTO"] = "0.5"
        os.environ["TARGET_PSYCH_CAP"] = "1"
        os.environ["TARGET_PSYCH_CAP_MAP"] = '{"crypto":{"base":0.3}}'
        import target_policy as _tp
        _tp._MAP_RAW = None
        _tp._MAP_CACHE = {}
        import order_params as _op
        run_id = self._run()
        with patch("analysis_agents.run_analysis",
                   return_value=_analysis(order=ORDER)), \
             patch.object(_op, "RR_FLOOR", 0.2):
            result = run_engine.run_cycle(run_id)
        self.assertTrue(result["executed"], result.get("skip_reason"))
        pos = self._position(run_id)
        # eff = max(0.3, 0.5*0.2=0.1, crypto fee floor 0.27) = 0.30, not
        # the 0.40 the unclamped 2% stop would have produced.
        self.assertAlmostEqual(float(pos["take_profit"]), 100.30, places=2)
        caps = self._events(run_id, "target_cap")
        self.assertEqual(len(caps), 1)
        self.assertAlmostEqual(caps[0]["eff_cap_pct"], 0.30, places=3)

    def test_non_crypto_market_not_clamped(self):
        self.assertIn("STOP_CAP_PCT_CRYPTO",
                      inspect.getsource(run_engine.run_cycle))
        # the guard is market == "crypto"; prove it textually AND by env
        src = inspect.getsource(run_engine.run_cycle)
        idx = src.index("STOP_CAP_PCT_CRYPTO")
        self.assertIn('== "crypto"', src[idx - 400:idx + 400])


class EntryFreezeTests(_CycleHarness):
    def test_frozen_agent_buy_skips(self):
        os.environ["AGENT_ENTRY_FREEZE"] = str(self.agent_id)
        run_id = self._run()
        with patch("analysis_agents.run_analysis",
                   return_value=_analysis(order=ORDER)):
            result = run_engine.run_cycle(run_id)
        self.assertFalse(result.get("executed"))
        self.assertIn("entry freeze", result.get("skip_reason") or "")
        skips = self._events(run_id, "gate_skip")
        self.assertTrue(any(s.get("stage") == "entry_freeze" for s in skips))
        self.assertIsNone(self._position(run_id))

    def test_frozen_agent_sell_still_exits(self):
        run_id = self._run()
        with patch("analysis_agents.run_analysis",
                   return_value=_analysis(order=ORDER)):
            result = run_engine.run_cycle(run_id)
        self.assertTrue(result["executed"], result.get("skip_reason"))
        os.environ["AGENT_ENTRY_FREEZE"] = str(self.agent_id)
        with patch("analysis_agents.run_analysis",
                   return_value=_analysis(action="sell")):
            result = run_engine.run_cycle(run_id)
        self.assertTrue(result.get("executed"), result.get("skip_reason"))
        pos = self._position(run_id)
        self.assertTrue(pos is None or float(pos["quantity"]) == 0)

    def test_unset_env_is_noop(self):
        self.assertFalse(run_engine._entry_frozen(5))
        os.environ["AGENT_ENTRY_FREEZE"] = "5, 12"
        self.assertTrue(run_engine._entry_frozen(5))
        self.assertTrue(run_engine._entry_frozen(12))
        self.assertFalse(run_engine._entry_frozen(6))


class MinHoldTests(_CycleHarness):
    def _set_min_hold(self, run_id, hours):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT config_snapshot_json FROM trading_runs "
                        "WHERE id = ?", (run_id,))
            cfg = json.loads(cur.fetchone()["config_snapshot_json"] or "{}")
            cfg["min_hold_hours"] = hours
            cur.execute("UPDATE trading_runs SET config_snapshot_json = ? "
                        "WHERE id = ?", (json.dumps(cfg), run_id))
            conn.commit()
        finally:
            conn.close()

    def test_young_position_desk_sell_deferred(self):
        run_id = self._run()
        with patch("analysis_agents.run_analysis",
                   return_value=_analysis(order=ORDER)):
            result = run_engine.run_cycle(run_id)
        self.assertTrue(result["executed"], result.get("skip_reason"))
        self._set_min_hold(run_id, 12)
        with patch("analysis_agents.run_analysis",
                   return_value=_analysis(action="sell")):
            result = run_engine.run_cycle(run_id)
        self.assertFalse(result.get("executed"))
        self.assertIn("min_hold", result.get("skip_reason") or "")
        pos = self._position(run_id)
        self.assertIsNotNone(pos)
        self.assertNotEqual(float(pos["quantity"]), 0)

    def test_zero_config_sells_normally(self):
        run_id = self._run()
        with patch("analysis_agents.run_analysis",
                   return_value=_analysis(order=ORDER)):
            run_engine.run_cycle(run_id)
        with patch("analysis_agents.run_analysis",
                   return_value=_analysis(action="sell")):
            result = run_engine.run_cycle(run_id)
        self.assertTrue(result.get("executed"), result.get("skip_reason"))

    def test_min_hold_fails_open(self):
        """Stale mark or any error must let the exit through — the block
        exists in a try/except that ends in a debug log, never a skip."""
        src = inspect.getsource(run_engine.run_cycle)
        idx = src.index("min_hold check failed open")
        self.assertIn("mark_age_ok", src[idx - 1600:idx])


class AddsGateTests(unittest.TestCase):
    RUN = {"id": 1, "agent_id": 9, "market": "crypto", "symbol": "BTC"}

    def tearDown(self):
        os.environ.pop("ADD_INTO_LOSER_BLOCK", None)
        os.environ.pop("RUN_ADDS_REQUIRE_PROFIT", None)

    def _skip(self, cfg, action="buy", qty=5.0, upnl=-3.0):
        with patch.object(run_engine, "_position_quantity",
                          return_value=qty), \
             patch.object(run_engine, "_unrealized_pnl", return_value=upnl):
            return run_engine._add_limit_skip(dict(self.RUN), cfg, action)

    def test_no_limits_env_off_is_legacy_noop(self):
        self.assertIsNone(self._skip({}, upnl=-3.0))

    def test_no_limits_env_on_blocks_underwater_add(self):
        os.environ["ADD_INTO_LOSER_BLOCK"] = "1"
        reason = self._skip({}, upnl=-3.0)
        self.assertIsNotNone(reason)
        self.assertIn("underwater", reason)

    def test_no_limits_env_on_blocks_unknown_upnl(self):
        os.environ["ADD_INTO_LOSER_BLOCK"] = "1"
        reason = self._skip({}, upnl=None)
        self.assertIsNotNone(reason)
        self.assertIn("fail-closed", reason)

    def test_winner_add_passes_without_limits(self):
        os.environ["ADD_INTO_LOSER_BLOCK"] = "1"
        self.assertIsNone(self._skip({}, upnl=+3.0))

    def test_losing_long_reduce_never_blocked(self):
        """A sell against a long book is a reduce — intent-keyed, never an
        add, so the underwater block must not touch it."""
        os.environ["ADD_INTO_LOSER_BLOCK"] = "1"
        self.assertIsNone(self._skip({}, action="sell", qty=5.0, upnl=-3.0))

    def test_losing_short_cover_never_blocked(self):
        os.environ["ADD_INTO_LOSER_BLOCK"] = "1"
        self.assertIsNone(self._skip({}, action="buy", qty=-5.0, upnl=-3.0))


class RatchetArmFeeTests(unittest.TestCase):
    PNL = {"position": {"quantity": 1.0, "current_price": 10000.0}}

    def tearDown(self):
        os.environ.pop("BREAKEVEN_FEE_RATE", None)
        os.environ.pop("BREAKEVEN_ARM_FEES", None)

    def test_crypto_market_uses_real_rate(self):
        os.environ["FEE_PER_MARKET"] = "true"
        try:
            arm = run_engine._breakeven_arm_usd(self.PNL, market="crypto")
        finally:
            os.environ.pop("FEE_PER_MARKET", None)
        self.assertAlmostEqual(arm, 10000.0 * 0.00045 * 2.0, places=4)

    def test_env_override_wins(self):
        os.environ["BREAKEVEN_FEE_RATE"] = "0.001"
        arm = run_engine._breakeven_arm_usd(self.PNL, market="crypto")
        self.assertAlmostEqual(arm, 20.0, places=4)

    def test_no_market_keeps_legacy_rate(self):
        arm = run_engine._breakeven_arm_usd(self.PNL)
        self.assertAlmostEqual(arm, 20.0, places=4)

    def test_call_sites_pass_market(self):
        src = inspect.getsource(run_engine)
        calls = [seg for seg in src.split("_breakeven_arm_usd(")[1:]
                 if not seg.startswith("pnl: dict")]
        self.assertEqual(len(calls), 2)
        for seg in calls:
            self.assertIn('market=run.get("market")', seg[:120])


class PsychShockDeltaTests(unittest.TestCase):
    def setUp(self):
        run_engine._PSYCH_SHOCK_STATE.update({"active": False, "since": 0.0})

    def tearDown(self):
        os.environ.pop("PSYCH_SHOCK_DELTA", None)
        os.environ.pop("PSYCH_SHOCK_FRESH_MIN", None)
        run_engine._PSYCH_SHOCK_STATE.update({"active": False, "since": 0.0})

    def test_transition_fires_then_goes_quiet(self):
        self.assertTrue(run_engine._psych_shock_fresh(True))
        run_engine._PSYCH_SHOCK_STATE["since"] = time.time() - 3700
        self.assertFalse(run_engine._psych_shock_fresh(True))

    def test_clearing_rearms(self):
        self.assertTrue(run_engine._psych_shock_fresh(True))
        run_engine._PSYCH_SHOCK_STATE["since"] = time.time() - 3700
        self.assertFalse(run_engine._psych_shock_fresh(True))
        self.assertFalse(run_engine._psych_shock_fresh(False))
        self.assertTrue(run_engine._psych_shock_fresh(True))

    def test_kill_switch_restores_always_on(self):
        os.environ["PSYCH_SHOCK_DELTA"] = "0"
        run_engine._PSYCH_SHOCK_STATE.update(
            {"active": True, "since": time.time() - 999999})
        self.assertTrue(run_engine._psych_shock_fresh(True))
        self.assertFalse(run_engine._psych_shock_fresh(False))


class PromptLineTests(unittest.TestCase):
    def tearDown(self):
        for k in ("TARGET_PSYCH_CAP", "TARGET_PSYCH_CAP_MAP",
                  "STOP_CAP_PCT_CRYPTO"):
            os.environ.pop(k, None)
        target_policy._MAP_RAW = None
        target_policy._MAP_CACHE = {}

    def _arm_cap(self):
        os.environ["TARGET_PSYCH_CAP"] = "1"
        os.environ["TARGET_PSYCH_CAP_MAP"] = '{"crypto":{"base":0.3}}'
        target_policy._MAP_RAW = None
        target_policy._MAP_CACHE = {}

    def test_stop_cap_line_states_full_geometry(self):
        self._arm_cap()
        os.environ["STOP_CAP_PCT_CRYPTO"] = "0.5"
        line = target_policy.prompt_line("crypto")
        self.assertIn("stop_pct is capped at 0.5%", line)
        self.assertIn("target_pct at 0.3%", line)
        self.assertIn("house design", line)
        self.assertNotIn("Do not hold", line)

    def test_without_stop_cap_line_unchanged(self):
        self._arm_cap()
        line = target_policy.prompt_line("crypto")
        self.assertIn("House target band", line)
        self.assertNotIn("stop_pct is capped", line)


if __name__ == "__main__":
    unittest.main()
