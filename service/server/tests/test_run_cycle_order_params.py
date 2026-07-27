"""Wiring tests for AI-authored order parameters inside run_cycle.

The rails themselves are unit-tested in test_order_params.py; these prove the
cycle actually CONSULTS them — that shadow mode journals without changing the
order, apply mode moves the real size and bracket, and the R:R floor refuses a
trade whoever authored the bracket. Without these the whole feature could be
deleted from run_cycle and every other test would still pass.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
import run_engine
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


class RunCycleOrderParamTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        os.environ["AUTO_TRADING_ENABLED"] = "true"
        os.environ["RUN_CONF_PERCENTILE"] = "false"
        # Prod runs with the risk engine ON — that is what supplies the flat
        # 5%/10% bracket these tests are about (verified on prod run 113:
        # entry 487.25 -> stop 462.888, target 535.975). With it off there is
        # no bracket at all and none of the exit assertions mean anything.
        os.environ["RISK_ENGINE_ENABLED"] = "true"
        self.probe = patch("routes_runs._probe_price", return_value=100.0)
        self.probe.start()
        self.client = TestClient(create_app())
        resp = self.client.post(
            "/api/claw/agents/selfRegister",
            json={"name": "op-agent", "password": "pw123",
                  "initial_balance": 100000.0})
        assert resp.status_code == 200, resp.text
        self.token = resp.json()["token"]
        self.agent_id = resp.json()["agent_id"]

    def tearDown(self):
        self.probe.stop()
        for key in ("AUTO_TRADING_ENABLED", "RUN_CONF_PERCENTILE",
                    "RUN_AI_ORDER_PARAMS", "RISK_ENGINE_ENABLED"):
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

    def _fill(self, run_id):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT quantity, entry_price FROM signals "
                        "WHERE run_id = ? AND executed_at IS NOT NULL", (run_id,))
            fills = [dict(r) for r in cur.fetchall()]
            # The bracket lands on the POSITION, not the signal row.
            cur.execute("SELECT stop_loss, take_profit FROM positions "
                        "WHERE run_id = ?", (run_id,))
            pos = cur.fetchone()
            for f in fills:
                f["stop_loss"] = pos["stop_loss"] if pos else None
                f["take_profit"] = pos["take_profit"] if pos else None
            return fills
        finally:
            conn.close()

    # ── shadow mode: journal everything, change nothing ────────────────

    def test_shadow_journals_the_block_but_does_not_resize(self):
        os.environ["RUN_AI_ORDER_PARAMS"] = "shadow"
        run_id = self._run()
        with patch("analysis_agents.run_analysis",
                   return_value=_analysis(order=ORDER)):
            result = run_engine.run_cycle(run_id)
        self.assertTrue(result["executed"], result.get("skip_reason"))
        evs = self._events(run_id, "order_params")
        self.assertEqual(len(evs), 1)
        self.assertEqual(evs[0]["mode"], "shadow")
        self.assertFalse(evs[0]["deferred"])
        self.assertEqual(evs[0]["params"]["size_frac"], 0.20)
        # …and the fill is still the FULL configured bet, not 20% of it.
        fills = self._fill(run_id)
        self.assertEqual(len(fills), 1)
        self.assertAlmostEqual(float(fills[0]["quantity"]) * 100.0, 500.0, places=2)

    def test_shadow_records_a_deferral(self):
        os.environ["RUN_AI_ORDER_PARAMS"] = "shadow"
        run_id = self._run()
        with patch("analysis_agents.run_analysis",
                   return_value=_analysis(order={"defer": True})):
            run_engine.run_cycle(run_id)
        evs = self._events(run_id, "order_params")
        self.assertEqual(len(evs), 1)
        self.assertTrue(evs[0]["deferred"])
        self.assertEqual(evs[0]["outcome"], "defer")

    def test_an_absent_block_is_distinguished_from_a_deferral(self):
        """Prod journaled 6 straight `deferred: true` and there was no way to
        tell whether the model was choosing the house default or never seeing
        the prompt at all. Those are opposite findings."""
        os.environ["RUN_AI_ORDER_PARAMS"] = "shadow"
        run_id = self._run()
        with patch("analysis_agents.run_analysis", return_value=_analysis()):
            run_engine.run_cycle(run_id)
        self.assertEqual(self._events(run_id, "order_params")[0]["outcome"],
                         "absent")

    def test_a_malformed_block_is_not_reported_as_a_deferral(self):
        os.environ["RUN_AI_ORDER_PARAMS"] = "shadow"
        run_id = self._run()
        with patch("analysis_agents.run_analysis",
                   return_value=_analysis(order={"size_frac": "lots"})):
            run_engine.run_cycle(run_id)
        self.assertEqual(self._events(run_id, "order_params")[0]["outcome"],
                         "malformed")

    def test_light_path_is_not_eligible_rather_than_absent(self):
        """The cheap path deliberately does not ask for order parameters; it
        must not pollute the shadow dataset as a missing-prompt signal."""
        os.environ["RUN_AI_ORDER_PARAMS"] = "shadow"
        run_id = self._run()
        light = _analysis()
        light["decision"]["order_eligible"] = False
        with patch("analysis_agents.run_analysis", return_value=light):
            run_engine.run_cycle(run_id)
        self.assertEqual(self._events(run_id, "order_params")[0]["outcome"],
                         "not_eligible")

    def test_off_mode_journals_nothing(self):
        os.environ["RUN_AI_ORDER_PARAMS"] = "off"
        run_id = self._run()
        with patch("analysis_agents.run_analysis",
                   return_value=_analysis(order=ORDER)):
            run_engine.run_cycle(run_id)
        self.assertEqual(self._events(run_id, "order_params"), [])

    def test_a_model_that_emits_no_block_is_unaffected(self):
        os.environ["RUN_AI_ORDER_PARAMS"] = "shadow"
        run_id = self._run()
        with patch("analysis_agents.run_analysis", return_value=_analysis()):
            result = run_engine.run_cycle(run_id)
        self.assertTrue(result["executed"], result.get("skip_reason"))
        self.assertTrue(self._events(run_id, "order_params")[0]["deferred"])

    # ── apply mode: the desk's numbers reach the book ──────────────────

    def test_apply_resizes_the_order(self):
        os.environ["RUN_AI_ORDER_PARAMS"] = "apply"
        run_id = self._run()
        with patch("analysis_agents.run_analysis",
                   return_value=_analysis(order=ORDER)):
            result = run_engine.run_cycle(run_id)
        self.assertTrue(result["executed"], result.get("skip_reason"))
        fills = self._fill(run_id)
        # 20% of the $500 max bet, at $100 → 1.0 unit, not 5.0.
        self.assertAlmostEqual(float(fills[0]["quantity"]) * 100.0, 100.0, places=2)

    def test_apply_uses_the_desks_bracket_not_the_flat_default(self):
        os.environ["RUN_AI_ORDER_PARAMS"] = "apply"
        run_id = self._run()
        with patch("analysis_agents.run_analysis",
                   return_value=_analysis(order=ORDER)):
            run_engine.run_cycle(run_id)
        fill = self._fill(run_id)[0]
        # 2% stop / 6% target off a 100.0 entry — NOT the house 5%/10%.
        self.assertAlmostEqual(float(fill["stop_loss"]), 98.0, places=2)
        self.assertAlmostEqual(float(fill["take_profit"]), 106.0, places=2)

    def test_apply_still_rails_a_hostile_block(self):
        """size_frac 50 is 50x the configured bet; the rail must cap it at the
        full bet, never honour it."""
        os.environ["RUN_AI_ORDER_PARAMS"] = "apply"
        run_id = self._run()
        hostile = {**ORDER, "size_frac": 50, "leverage": 99}
        with patch("analysis_agents.run_analysis",
                   return_value=_analysis(order=hostile)):
            result = run_engine.run_cycle(run_id)
        self.assertTrue(result["executed"], result.get("skip_reason"))
        fills = self._fill(run_id)
        self.assertLessEqual(float(fills[0]["quantity"]) * 100.0, 500.0 + 0.01)

    def test_apply_with_a_deferral_falls_back_to_the_house_bracket(self):
        os.environ["RUN_AI_ORDER_PARAMS"] = "apply"
        run_id = self._run()
        with patch("analysis_agents.run_analysis",
                   return_value=_analysis(order={"defer": True})):
            run_engine.run_cycle(run_id)
        fill = self._fill(run_id)[0]
        self.assertAlmostEqual(float(fill["stop_loss"]), 95.0, places=2)   # 5%
        self.assertAlmostEqual(float(fill["take_profit"]), 110.0, places=2)  # 10%

    # ── the R:R floor guards both paths ────────────────────────────────

    def test_rr_floor_refuses_an_inverted_bracket_on_the_code_path(self):
        """No AI block at all — a hand-edited risk_limits row that risks 5% to
        win 2% must not trade. This is the rail that would have made last
        week's 10:1 geometry impossible."""
        os.environ["RUN_AI_ORDER_PARAMS"] = "off"
        self.client.put("/api/risk/limits",
                        json={"stop_loss_pct": 0.05, "take_profit_pct": 0.02},
                        headers=self._h())
        run_id = self._run()
        with patch("analysis_agents.run_analysis", return_value=_analysis()):
            result = run_engine.run_cycle(run_id)
        self.assertFalse(result["executed"])
        self.assertIn("r:r floor", result["skip_reason"])
        skips = [e for e in self._events(run_id, "gate_skip")
                 if e.get("stage") == "rr_floor"]
        self.assertEqual(len(skips), 1, "the refusal must be journaled")

    def test_compliant_house_bracket_still_trades(self):
        os.environ["RUN_AI_ORDER_PARAMS"] = "off"
        run_id = self._run()
        with patch("analysis_agents.run_analysis", return_value=_analysis()):
            result = run_engine.run_cycle(run_id)
        self.assertTrue(result["executed"], result.get("skip_reason"))


if __name__ == "__main__":
    unittest.main()
