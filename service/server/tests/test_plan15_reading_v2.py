"""Plan 15 P1 — reading-algorithm v2 inputs.

Covers the four P1 changes (docs/plan/15-run-ai-reading-algorithm-fix.html):
  F1 — calibration rubric + inventory context in the light-cycle prompt
  F2 — us-stock technicals fall back to Yahoo candles behind the Alpha
       Vantage premium wall
  F3 — fleet builder never sets a run gate above its thesis confidence
  F4 — covered in test_run_futures_short.py (spot sell with empty book)
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

import database
import run_engine
from fleet_planner import FLEET_BOUNDS, compose_run_settings


class LightAnalysisPromptTests(unittest.TestCase):
    """The decision prompt must carry the rubric and the book state."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()

    def tearDown(self):
        self.tmp.cleanup()

    def _capture_prompt(self, run, cfg):
        captured = {}

        def fake_generate(prompt, **kwargs):
            captured["prompt"] = prompt
            return '{"action": "hold", "confidence": 0.55, "report": "r"}'

        with patch("price_fetcher.get_price_from_market", return_value=100.0), \
                patch("price_fetcher.get_daily_candles", return_value=[]), \
                patch("llm_client.generate_text", side_effect=fake_generate):
            out = run_engine._light_analysis(run, cfg)
        return captured.get("prompt", ""), out

    def _run_row(self, **overrides):
        row = {"id": 1, "agent_id": 999999, "symbol": "ETHUSDT",
               "market": "crypto", "market_type": "spot"}
        row.update(overrides)
        return row

    def test_prompt_contains_rubric_and_flat_spot_inventory_rule(self):
        prompt, out = self._capture_prompt(self._run_row(), {})
        self.assertIn("0.50 = coin-flip", prompt)
        self.assertIn("0.85+ = exceptional", prompt)
        self.assertIn("Do not default to a habitual value", prompt)
        self.assertIn("Position in this run's book: 0.0 units", prompt)
        self.assertIn("'sell' is NOT available", prompt)
        self.assertEqual(out["decision"]["action"], "hold")

    def test_prompt_futures_book_allows_short(self):
        prompt, _ = self._capture_prompt(
            self._run_row(market_type="futures"), {})
        self.assertIn("'sell' opens or extends a short", prompt)
        self.assertNotIn("'sell' is NOT available", prompt)

    def test_prompt_long_inventory_rule(self):
        with patch.object(run_engine, "_position_quantity", return_value=2.5):
            captured = {}

            def fake_generate(prompt, **kwargs):
                captured["prompt"] = prompt
                return '{"action": "hold", "confidence": 0.55, "report": "r"}'

            with patch("price_fetcher.get_price_from_market", return_value=100.0), \
                    patch("price_fetcher.get_daily_candles", return_value=[]), \
                    patch("llm_client.generate_text", side_effect=fake_generate):
                run_engine._light_analysis(self._run_row(), {})
        self.assertIn("Position in this run's book: 2.5 units", captured["prompt"])
        self.assertIn("reduces/closes this long", captured["prompt"])


class YahooTechnicalsFallbackTests(unittest.TestCase):
    """F2 — the premium wall must no longer starve us-stock technicals."""

    def _candles(self, n=40, start_close=100.0):
        # oldest-first epoch-ms candles, one per day
        day_ms = 86_400_000
        base = 1_752_000_000_000  # 2025-07 area; exact date irrelevant
        return [{"ts": base + i * day_ms, "open": start_close, "high": start_close,
                 "low": start_close, "close": start_close + i * 0.5,
                 "volume": 1000 + i} for i in range(n)]

    def test_premium_wall_falls_back_to_yahoo(self):
        import market_intel
        wall = {"Information": "Thank you for using Alpha Vantage! This is a "
                               "premium endpoint."}
        with patch.object(market_intel, "_alpha_vantage_get", return_value=wall), \
                patch("price_fetcher.get_daily_candles",
                      return_value=self._candles()):
            rows = market_intel._fetch_daily_adjusted_series("TSLA")
        self.assertGreaterEqual(len(rows), 20)
        # newest-first, real ISO dates, close/volume floats
        self.assertGreater(rows[0]["date"], rows[-1]["date"])
        self.assertRegex(rows[0]["date"], r"^\d{4}-\d{2}-\d{2}$")
        self.assertIsInstance(rows[0]["close"], float)

    def test_premium_wall_raise_falls_back_to_yahoo(self):
        # THE REAL PROD SHAPE: _alpha_vantage_get RAISES on the premium
        # message (it converts it to RuntimeError) — it does not return the
        # payload. Caught live on prod 2026-07-22; the return-shape mock
        # above alone let a dead fallback pass locally.
        import market_intel
        with patch.object(market_intel, "_alpha_vantage_get",
                          side_effect=RuntimeError("premium endpoint")), \
                patch("price_fetcher.get_daily_candles",
                      return_value=self._candles()):
            rows = market_intel._fetch_daily_adjusted_series("TSLA")
        self.assertGreaterEqual(len(rows), 20)

    def test_premium_wall_and_no_yahoo_still_raises(self):
        import market_intel
        wall = {"Information": "premium endpoint"}
        with patch.object(market_intel, "_alpha_vantage_get", return_value=wall), \
                patch("price_fetcher.get_daily_candles", return_value=[]):
            with self.assertRaises(RuntimeError):
                market_intel._fetch_daily_adjusted_series("TSLA")

    def test_build_stock_analysis_survives_premium_wall(self):
        import market_intel
        wall = {"Information": "premium endpoint"}
        with patch.object(market_intel, "_alpha_vantage_get", return_value=wall), \
                patch("price_fetcher.get_daily_candles",
                      return_value=self._candles()), \
                patch.object(market_intel, "_build_stock_long_window_features",
                             return_value={
                                 "momentum_12_1_pct": None,
                                 "reversal_1m_pct": None, "ma50": None,
                                 "ma200": None, "price_above_ma200": None,
                                 "golden_cross_state": None,
                                 "sigma_daily_pct": None,
                                 "volume_ratio": None}):
            analysis = market_intel._build_stock_analysis("TSLA")
        self.assertEqual(analysis["market"], "us-stock")
        self.assertGreater(analysis["current_price"], 0)


class FleetGateCoherenceTests(unittest.TestCase):
    """F3 — no run is born with a gate above its own thesis confidence."""

    def _settings(self, thesis_conf, risk="balanced"):
        thesis = {"symbol": "ZC", "market": "futures", "market_type": "spot",
                  "direction": "long", "confidence": thesis_conf,
                  "expected_move_pct": 3.0, "horizon_hours": 48,
                  "entry_ref_price": 477.25, "thesis_key": "k",
                  "rationale": "r"}
        return compose_run_settings(thesis, 1000.0, {"risk_appetite": risk})

    def test_weak_thesis_lowers_gate_to_floor(self):
        # thesis 0.539 (the real fleet-6 ZC case): gate 0.50, not 0.60
        self.assertEqual(self._settings(0.539)["min_confidence"], 0.50)

    def test_mid_thesis_gate_tracks_thesis_minus_margin(self):
        # thesis 0.62: gate = min(0.60, 0.57) = 0.57
        self.assertEqual(self._settings(0.62)["min_confidence"], 0.57)

    def test_strong_thesis_keeps_risk_bound(self):
        # thesis 0.80: bound 0.60 stays (balanced)
        self.assertEqual(self._settings(0.80)["min_confidence"],
                         FLEET_BOUNDS["min_confidence"]["balanced"])

    def test_stable_risk_bound_still_clamped_by_thesis(self):
        # stable bound 0.75, thesis 0.68 → 0.63
        self.assertEqual(self._settings(0.68, risk="stable")["min_confidence"],
                         0.63)


class ConvictionMathTests(unittest.TestCase):
    """P2 — conviction is computed in code from the component scores."""

    def test_weighted_blend(self):
        scores = {"thesis_alignment": 0.8, "momentum_quality": 0.6,
                  "entry_quality": 0.4, "risk_context": 0.5}
        # 0.35*0.8 + 0.25*0.6 + 0.25*0.4 + 0.15*0.5 = 0.605
        self.assertEqual(run_engine.compute_conviction(scores), 0.605)

    def test_missing_key_is_none(self):
        self.assertIsNone(run_engine.compute_conviction(
            {"thesis_alignment": 0.8, "momentum_quality": 0.6,
             "entry_quality": 0.4}))

    def test_out_of_range_is_none(self):
        self.assertIsNone(run_engine.compute_conviction(
            {"thesis_alignment": 1.4, "momentum_quality": 0.6,
             "entry_quality": 0.4, "risk_context": 0.5}))

    def test_non_dict_is_none(self):
        self.assertIsNone(run_engine.compute_conviction(None))
        self.assertIsNone(run_engine.compute_conviction("0.7"))

    def test_light_analysis_parses_scores(self):
        reply = ('{"action": "buy", "confidence": 0.62, "scores": '
                 '{"thesis_alignment": 0.8, "momentum_quality": 0.7, '
                 '"entry_quality": 0.6, "risk_context": 0.5}, "report": "r"}')
        with patch("price_fetcher.get_price_from_market", return_value=100.0), \
                patch("price_fetcher.get_daily_candles", return_value=[]), \
                patch("llm_client.generate_text", return_value=reply), \
                patch.object(run_engine, "_position_quantity", return_value=0.0):
            out = run_engine._light_analysis(
                {"id": 1, "agent_id": 1, "symbol": "X", "market": "crypto",
                 "market_type": "spot"}, {})
        self.assertEqual(out["decision"]["scores"]["thesis_alignment"], 0.8)
        self.assertEqual(run_engine.compute_conviction(out["decision"]["scores"]),
                         0.68)


class ConvictionGateFlagTests(unittest.TestCase):
    """P3 — RUN_CONF_V2 flips the gate to conviction; default stays legacy."""

    STRONG_SCORES_WEAK_SCALAR = {
        "symbol": "BTC", "market": "crypto",
        "analysts": {"technical": {"brief": "t",
                                   "data": {"sigma_daily_pct": 2.5,
                                            "current_price": 100.0}}},
        "decision": {"action": "buy", "confidence": 0.30, "entry": 100.0,
                     "report": "r",
                     "scores": {"thesis_alignment": 0.9, "momentum_quality": 0.8,
                                "entry_quality": 0.8, "risk_context": 0.7}},
    }  # conviction = 0.35*.9+0.25*.8+0.25*.8+0.15*.7 = 0.82

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        os.environ["AUTO_TRADING_ENABLED"] = "true"
        from fastapi.testclient import TestClient
        from routes import create_app
        self.probe = patch("routes_runs._probe_price", return_value=100.0)
        self.probe.start()
        self.client = TestClient(create_app())
        resp = self.client.post(
            "/api/claw/agents/selfRegister",
            json={"name": "conv-agent", "password": "pw123",
                  "initial_balance": 100000.0})
        self.token = resp.json()["token"]

    def tearDown(self):
        self.probe.stop()
        os.environ.pop("AUTO_TRADING_ENABLED", None)
        os.environ.pop("RUN_CONF_V2", None)
        self.tmp.cleanup()

    def _running_run(self):
        h = {"Authorization": f"Bearer {self.token}"}
        run_id = self.client.post(
            "/api/runs", json={"symbol": "BTC", "market": "crypto",
                               "max_bet_usd": 500.0, "min_confidence": 0.6},
            headers=h).json()["id"]
        assert self.client.post(f"/api/runs/{run_id}/start",
                                headers=h).status_code == 200
        return run_id

    def test_flag_off_gates_on_scalar(self):
        run_id = self._running_run()
        with patch("analysis_agents.run_analysis",
                   return_value=self.STRONG_SCORES_WEAK_SCALAR):
            result = run_engine.run_cycle(run_id)
        self.assertFalse(result["executed"], result)
        self.assertIn("below threshold", result["skip_reason"] or "")

    def test_flag_on_gates_on_conviction(self):
        os.environ["RUN_CONF_V2"] = "1"
        run_id = self._running_run()
        with patch("analysis_agents.run_analysis",
                   return_value=self.STRONG_SCORES_WEAK_SCALAR):
            result = run_engine.run_cycle(run_id)
        self.assertTrue(result["executed"], result)

    def test_decision_event_carries_shadow_fields(self):
        run_id = self._running_run()
        with patch("analysis_agents.run_analysis",
                   return_value=self.STRONG_SCORES_WEAK_SCALAR):
            run_engine.run_cycle(run_id)
        import json as _j
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT payload FROM run_events WHERE run_id = ? AND "
                        "event_type = 'decision' ORDER BY id DESC LIMIT 1",
                        (run_id,))
            payload = _j.loads(cur.fetchone()["payload"])
        finally:
            conn.close()
        self.assertEqual(payload["conviction"], 0.82)
        self.assertEqual(payload["gate_source"], "confidence")
        self.assertEqual(payload["scores"]["thesis_alignment"], 0.9)


class AdaptPercentileCapTests(unittest.TestCase):
    """E1 — loss-tightening can no longer out-run the model's own output."""

    def _params(self, values, bump=0.05, run_id=7):
        import run_feedback as rf
        state = dict(rf._DEFAULT_STATE)
        state["conf_bump"] = bump
        cfg = {"min_confidence": 0.60, "max_bet_usd": 500.0}
        with patch.object(rf, "_recent_decision_values", return_value=values):
            return rf.effective_gate_params(state, cfg, run_id=run_id)

    def test_pinned_output_caps_at_p90_minus_epsilon(self):
        # the fleet-6 disease: everything 0.62, base 0.60, one loss
        p = self._params([0.62] * 10)
        self.assertEqual(p["min_confidence"], 0.61)  # min(0.65, 0.62-0.01)

    def test_spread_output_keeps_full_tightening(self):
        values = [0.45, 0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9]
        p = self._params(values)
        self.assertEqual(p["min_confidence"], 0.65)  # p90 0.9 → cap 0.89 no-op

    def test_too_few_decisions_keeps_legacy(self):
        p = self._params([0.62] * 5)
        self.assertEqual(p["min_confidence"], 0.65)

    def test_no_run_id_keeps_legacy(self):
        import run_feedback as rf
        state = dict(rf._DEFAULT_STATE)
        state["conf_bump"] = 0.05
        p = rf.effective_gate_params(state, {"min_confidence": 0.60,
                                             "max_bet_usd": 500.0})
        self.assertEqual(p["min_confidence"], 0.65)

    def test_no_bump_skips_the_query(self):
        import run_feedback as rf
        state = dict(rf._DEFAULT_STATE)
        with patch.object(rf, "_recent_decision_values",
                          side_effect=AssertionError("must not query")) :
            p = rf.effective_gate_params(state, {"min_confidence": 0.60,
                                                 "max_bet_usd": 500.0},
                                         run_id=7)
        self.assertEqual(p["min_confidence"], 0.60)


class EarlyStopConfirmTests(unittest.TestCase):
    """E2 — stopping a thesis run before its horizon needs confirm_early."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        from fastapi.testclient import TestClient
        from routes import create_app
        self.probe = patch("routes_runs._probe_price", return_value=100.0)
        self.probe.start()
        self.client = TestClient(create_app())
        resp = self.client.post(
            "/api/claw/agents/selfRegister",
            json={"name": "estop-agent", "password": "pw123",
                  "initial_balance": 100000.0})
        self.token = resp.json()["token"]
        self.h = {"Authorization": f"Bearer {self.token}"}

    def tearDown(self):
        self.probe.stop()
        self.tmp.cleanup()

    def _running_run(self, thesis_horizon_h=None):
        run_id = self.client.post(
            "/api/runs", json={"symbol": "BTC", "market": "crypto",
                               "max_bet_usd": 500.0}, headers=self.h).json()["id"]
        assert self.client.post(f"/api/runs/{run_id}/start",
                                headers=self.h).status_code == 200
        if thesis_horizon_h is not None:
            import json as _j
            conn = database.get_db_connection()
            try:
                cur = conn.cursor()
                cur.execute("SELECT config_snapshot_json FROM trading_runs "
                            "WHERE id = ?", (run_id,))
                cfg = _j.loads(cur.fetchone()["config_snapshot_json"] or "{}")
                cfg["thesis"] = {"horizon_hours": thesis_horizon_h}
                cur.execute("UPDATE trading_runs SET config_snapshot_json = ? "
                            "WHERE id = ?", (_j.dumps(cfg), run_id))
                conn.commit()
            finally:
                conn.close()
        return run_id

    def test_early_stop_409s_without_confirm(self):
        run_id = self._running_run(thesis_horizon_h=48)
        resp = self.client.post(f"/api/runs/{run_id}/stop",
                                json={"flatten": True}, headers=self.h)
        self.assertEqual(resp.status_code, 409, resp.text)
        early = resp.json()["detail"]["early_stop"]
        self.assertEqual(early["horizon_hours"], 48)
        self.assertGreater(early["remaining_hours"], 0)

    def test_early_stop_with_confirm_stops(self):
        run_id = self._running_run(thesis_horizon_h=48)
        resp = self.client.post(
            f"/api/runs/{run_id}/stop",
            json={"flatten": True, "confirm_early": True}, headers=self.h)
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertIn(resp.json()["run"]["status"], ("stopping", "stopped"))

    def test_no_thesis_stops_without_confirm(self):
        run_id = self._running_run()
        resp = self.client.post(f"/api/runs/{run_id}/stop",
                                json={"flatten": True}, headers=self.h)
        self.assertEqual(resp.status_code, 200, resp.text)

    def test_elapsed_horizon_stops_without_confirm(self):
        # deterministic: 1h horizon, started_at backdated 2h
        from datetime import datetime, timedelta, timezone
        run_id = self._running_run(thesis_horizon_h=1)
        past = (datetime.now(timezone.utc) - timedelta(hours=2)).strftime(
            "%Y-%m-%dT%H:%M:%SZ")
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("UPDATE trading_runs SET started_at = ? WHERE id = ?",
                        (past, run_id))
            conn.commit()
        finally:
            conn.close()
        resp = self.client.post(f"/api/runs/{run_id}/stop",
                                json={"flatten": True}, headers=self.h)
        self.assertEqual(resp.status_code, 200, resp.text)


if __name__ == "__main__":
    unittest.main()
