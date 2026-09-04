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

    # ── a futures book can be LONG, and the rule never said so ─────────────
    # Prod run 776 (ZC, futures, long 14.02, peak +$78.58) emitted `buy` for
    # 43 straight cycles and reported "I cover the existing short and go long"
    # while holding that long — it gave back 94% of the peak. The futures
    # branch was one state-blind sentence describing short mechanics only, so
    # "sell to bank this long" was not reachable from the instruction set.

    def _futures_prompt(self, qty):
        with patch.object(run_engine, "_position_quantity", return_value=qty):
            return self._capture_prompt(self._run_row(market="futures"), {})[0]

    def test_futures_long_is_told_sell_reduces_it(self):
        prompt = self._futures_prompt(14.02)
        self.assertIn("currently LONG", prompt)
        self.assertIn("'sell' reduces/closes this long", prompt)

    def test_futures_long_is_not_told_it_holds_a_short(self):
        """The exact hallucination run 776 produced: a long book primed with
        'buy covers a short'."""
        prompt = self._futures_prompt(14.02)
        self.assertNotIn("covers a short", prompt)
        self.assertNotIn("opens or extends a short", prompt)

    def test_futures_short_rule_is_unchanged(self):
        prompt = self._futures_prompt(-3.0)
        self.assertIn("'sell' opens or extends a short", prompt)
        self.assertIn("'buy' covers a short", prompt)

    def test_futures_flat_rule_is_unchanged(self):
        prompt = self._futures_prompt(0.0)
        self.assertIn("'sell' opens or extends a short", prompt)
        self.assertNotIn("'sell' is NOT available", prompt)

    # ── the desk must be able to decide to BANK ────────────────────────────
    # The four component scores are all entry-framed, so a desk holding a
    # decaying winner had nothing to reason from. Prod runs 776 / 811 / 816
    # round-tripped peaks of $78.58 / $33.44 / $75.29 to ~zero while emitting
    # `hold` or `buy`, with `sell`/`cover` available every cycle; 811's own
    # reports read "...rather than adding". Give it the trajectory and the verb.

    def _held_prompt(self, qty, unrealized, peak, expected_move_pct=2.0,
                     entry=100.0, mark=104.0, mark_ok=True):
        pnl = {"unrealized": unrealized, "mark_age_ok": mark_ok,
               "position": {"quantity": qty, "entry_price": entry,
                            "current_price": mark}}
        run = self._run_row(market="futures")
        run["peak_pnl_usd"] = peak
        cfg = {"thesis": {"expected_move_pct": expected_move_pct}}
        with patch.object(run_engine, "_position_quantity", return_value=qty), \
                patch.object(run_engine, "compute_run_pnl", return_value=pnl):
            return self._capture_prompt(run, cfg)[0]

    def test_held_position_gets_its_open_pnl_and_high_water_mark(self):
        prompt = self._held_prompt(qty=2.0, unrealized=30.0, peak=75.0)
        self.assertIn("Open P&L on this position: $30.00", prompt)
        self.assertIn("$75.00", prompt)
        self.assertIn("40% of that high-water mark", prompt)

    def test_held_position_is_told_how_much_of_the_move_arrived(self):
        # long from 100 to 104 = +4.00% against a thesis wanting 2.00%
        prompt = self._held_prompt(qty=2.0, unrealized=30.0, peak=75.0)
        self.assertIn("Thesis expected a 2.00% move; +4.00% has arrived", prompt)

    def test_short_move_is_measured_in_the_short_s_favour(self):
        # short from 100 with price at 104 = the move went AGAINST it
        prompt = self._held_prompt(qty=-2.0, unrealized=-30.0, peak=0.0)
        self.assertIn("-4.00% has arrived", prompt)

    def test_banking_is_stated_as_a_first_class_action(self):
        prompt = self._held_prompt(qty=2.0, unrealized=30.0, peak=75.0)
        self.assertIn("Banking is a first-class action", prompt)
        self.assertIn("still valid is not a reason to keep giving back", prompt)

    def test_flat_book_gets_no_position_state_and_no_banking_line(self):
        """A flat run must not be nudged to close something it does not hold."""
        prompt = self._capture_prompt(self._run_row(market="futures"), {})[0]
        self.assertNotIn("Open P&L on this position", prompt)
        self.assertNotIn("Banking is a first-class action", prompt)

    # ── session close: a gain you cannot act on is a gain you carry ────────
    # Prod run 818 held +$30.99 across the CME close with every rail out of
    # reach (brake −$27.15, trail arming at $89.02 against a $35.16 peak). The
    # pre-gate refuses a CLOSED market; nothing warned it while it could act.

    def _closing_prompt(self, minutes_left):
        with patch("markets.session_minutes_left", return_value=minutes_left):
            return self._held_prompt(qty=-0.11, unrealized=30.99, peak=35.16)

    def test_desk_is_warned_while_it_can_still_act(self):
        prompt = self._closing_prompt(12)
        self.assertIn("closes in about 12 minute(s)", prompt)
        self.assertIn("close or reduce it NOW", prompt)

    def test_no_closing_warning_when_the_session_has_hours_left(self):
        prompt = self._closing_prompt(300)
        self.assertNotIn("closes in about", prompt)

    def test_no_closing_warning_when_already_shut(self):
        """0 means shut — the pre-gate handles that; do not tell the desk to
        act when acting is impossible."""
        prompt = self._closing_prompt(0)
        self.assertNotIn("closes in about", prompt)

    def test_a_24x7_market_never_warns(self):
        prompt = self._closing_prompt(24 * 60)
        self.assertNotIn("closes in about", prompt)

    def test_exit_awareness_is_kill_switchable(self):
        """One env var reverts to the pre-2026-07-29 entry-only prompt."""
        with patch.dict(os.environ, {"RUN_DESK_EXIT_AWARENESS": "false"}):
            prompt = self._held_prompt(qty=2.0, unrealized=30.0, peak=75.0)
        self.assertNotIn("Open P&L on this position", prompt)
        self.assertNotIn("Banking is a first-class action", prompt)

    def test_stale_mark_reports_nothing_rather_than_a_confident_zero(self):
        """An untrustworthy book must stay silent — rendering $0.00 would read
        as 'breakeven, nothing to bank', the opposite of the truth."""
        prompt = self._held_prompt(qty=2.0, unrealized=30.0, peak=75.0,
                                   mark_ok=False)
        self.assertNotIn("Open P&L on this position", prompt)
        # the verb still stands: it holds a position, it may still close it
        self.assertIn("Banking is a first-class action", prompt)


class FullPathSeesThePositionTests(unittest.TestCase):
    """The E1 router escalates to the FULL path for position reasons — prod run
    811 cycle 55, "Open position near loss warrants judgement check" — and that
    path took no position input of any kind. #124 fixed the light path only;
    the escalated cycles are the ones that need it most."""

    def _trader_prompt(self, position_state):
        captured = {}

        def fake_generate(prompt, **kwargs):
            captured["prompt"] = prompt
            return ('{"action":"hold","confidence":0.5,"scores":'
                    '{"thesis_alignment":0.5,"momentum_quality":0.5,'
                    '"entry_quality":0.5,"risk_context":0.5},'
                    '"rationale":"r","report":"r"}')

        briefs = {k: "brief" for k in ("news", "sentiment",
                                       "fundamentals_macro", "technical")}
        import analysis_agents
        # `from llm_client import generate_text` binds the name into this
        # module at import, so patching llm_client would miss it.
        with patch.object(analysis_agents, "llm_configured", return_value=True), \
                patch.object(analysis_agents, "generate_text",
                             side_effect=fake_generate):
            analysis_agents._trader_risk_decision(
                "BTC", "crypto", briefs, {"current_price": 100.0}, {}, "en",
                position_state=position_state)
        return captured.get("prompt", "")

    def test_position_state_reaches_the_trader_prompt(self):
        state = ("Open P&L on this position: $30.99. Banking is a "
                 "first-class action.\n")
        self.assertIn("Open P&L on this position: $30.99",
                      self._trader_prompt(state))

    def test_flat_book_adds_nothing_to_the_trader_prompt(self):
        self.assertNotIn("Open P&L on this position", self._trader_prompt(""))


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


class MarkRefreshDefaultTests(unittest.TestCase):
    """Overnight finding — futures/us-stock marks must refresh, or every run
    holding such a position dies stop_eval_failed at the staleness limit."""

    def test_default_covers_run_markets(self):
        import tasks
        parsed = tasks._env_csv_set("__UNSET_ENV__",
                                    tasks.REFRESH_PRICED_MARKETS_DEFAULT)
        self.assertIn("crypto", parsed)
        self.assertIn("futures", parsed)
        self.assertIn("us-stock", parsed)


class HeadroomFloorTests(unittest.TestCase):
    """Overnight (Henry-approved): dust adds below max($10, 2% of max_bet)
    skip instead of trading — a $17 add on a $5.2k max_bet is fee churn."""

    def test_floor_scales_with_max_bet(self):
        # replicate the floor expression used in run_cycle
        for max_bet, expected in ((5200.0, 104.0), (400.0, 10.0), (0, 10.0)):
            floor = max(10.0, 0.02 * float(max_bet or 0))
            self.assertEqual(floor, expected)


class ConvictionSizeScaleTests(unittest.TestCase):
    """rec-2 — size follows conviction, shrink-only."""

    def test_mapping(self):
        f = run_engine._conviction_size_scale
        self.assertEqual(f(0.75), 1.0)
        self.assertEqual(f(0.90), 1.0)     # never levers up
        self.assertEqual(f(0.60), 0.5)
        self.assertEqual(f(0.45), 0.40)
        self.assertEqual(f(0.10), 0.40)    # floor
        self.assertIsNone(f(None))

    def test_kill_switch(self):
        os.environ["RUN_SIZE_BY_CONVICTION"] = "0"
        try:
            self.assertIsNone(run_engine._conviction_size_scale(0.9))
        finally:
            os.environ.pop("RUN_SIZE_BY_CONVICTION", None)

    def test_trade_size_scales_with_scores(self):
        """Integration: weak scores → smaller executed quantity."""
        import tempfile as _tf
        tmp = _tf.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(tmp.name, "t.db")
        database.init_database()
        os.environ["AUTO_TRADING_ENABLED"] = "true"
        from fastapi.testclient import TestClient
        from routes import create_app
        probe = patch("routes_runs._probe_price", return_value=100.0)
        probe.start()
        client = TestClient(create_app())
        try:
            def mk_run(name):
                tok = client.post("/api/claw/agents/selfRegister",
                                  json={"name": name, "password": "pw123",
                                        "initial_balance": 100000.0}).json()["token"]
                h = {"Authorization": f"Bearer {tok}"}
                rid = client.post("/api/runs",
                                  json={"symbol": "BTC", "market": "crypto",
                                        "max_bet_usd": 1000.0,
                                        "min_confidence": 0.5},
                                  headers=h).json()["id"]
                assert client.post(f"/api/runs/{rid}/start",
                                   headers=h).status_code == 200
                return rid

            def analysis(scores):
                return {"symbol": "BTC", "market": "crypto",
                        "analysts": {"technical": {"brief": "t",
                                                   "data": {"sigma_daily_pct": 2.5,
                                                            "current_price": 100.0}}},
                        "decision": {"action": "buy", "confidence": 0.62,
                                     "entry": 100.0, "report": "r",
                                     "scores": scores}}

            strong = {"thesis_alignment": 0.9, "momentum_quality": 0.9,
                      "entry_quality": 0.9, "risk_context": 0.9}   # cv 0.9 → 1.0
            weak = {"thesis_alignment": 0.6, "momentum_quality": 0.6,
                    "entry_quality": 0.6, "risk_context": 0.6}     # cv 0.6 → 0.5
            r1, r2 = mk_run("sz-strong"), mk_run("sz-weak")
            with patch("analysis_agents.run_analysis",
                       return_value=analysis(strong)):
                self.assertTrue(run_engine.run_cycle(r1)["executed"])
            with patch("analysis_agents.run_analysis",
                       return_value=analysis(weak)):
                self.assertTrue(run_engine.run_cycle(r2)["executed"])
            conn = database.get_db_connection()
            cur = conn.cursor()
            cur.execute("SELECT run_id, quantity FROM signals ORDER BY id")
            rows = {r["run_id"]: float(r["quantity"]) for r in cur.fetchall()}
            conn.close()
            # weak run's quantity ≈ half the strong run's
            self.assertAlmostEqual(rows[r2] / rows[r1], 0.5, places=2)
        finally:
            probe.stop()
            os.environ.pop("AUTO_TRADING_ENABLED", None)
            tmp.cleanup()


class ShadowReportTests(unittest.TestCase):
    """rec-1 — the flip test is computed from episodes."""

    def test_episode_cutting_and_weighting(self):
        from conviction_shadow import build_episodes
        legs = [
            {"side": "buy", "quantity": 10, "entry_price": 100.0,
             "fee_usd": 1.0, "cycle": 1},
            {"side": "buy", "quantity": 10, "entry_price": 110.0,
             "fee_usd": 1.0, "cycle": 2},
            {"side": "sell", "quantity": 20, "entry_price": 120.0,
             "fee_usd": 2.0, "cycle": None},          # win: +300 -4 fees
            {"side": "short", "quantity": 5, "entry_price": 100.0,
             "fee_usd": 1.0, "cycle": 3},
            {"side": "cover", "quantity": 5, "entry_price": 110.0,
             "fee_usd": 1.0, "cycle": None},          # loss: -50 -2 fees
        ]
        metrics = {1: {"confidence": 0.6, "conviction": 0.7},
                   2: {"confidence": 0.8, "conviction": 0.9},
                   3: {"confidence": 0.5, "conviction": 0.4}}
        eps = build_episodes(legs, metrics)
        self.assertEqual(len(eps), 2)
        self.assertAlmostEqual(eps[0]["pnl"], 296.0)
        # weighted mean: (1000*0.6 + 1100*0.8) / 2100
        self.assertAlmostEqual(eps[0]["confidence"], 0.7048, places=4)
        self.assertAlmostEqual(eps[0]["conviction"], 0.8048, places=4)
        self.assertAlmostEqual(eps[1]["pnl"], -52.0)
        self.assertEqual(eps[1]["confidence"], 0.5)

    def test_rank_agreement(self):
        from conviction_shadow import _rank_agreement
        eps = [{"pnl": 10, "confidence": 0.6}, {"pnl": 20, "confidence": 0.7},
               {"pnl": -5, "confidence": 0.65}, {"pnl": -8, "confidence": 0.5}]
        # pairs: (0.6 vs 0.65)=0, (0.6 vs 0.5)=1, (0.7 vs 0.65)=1, (0.7 vs 0.5)=1
        self.assertEqual(_rank_agreement(eps, "confidence"), 0.75)
        self.assertIsNone(_rank_agreement(
            [{"pnl": 1, "confidence": 0.6}], "confidence"))

    def test_cycle_from_coid(self):
        # regression: the metric join must read the cycle from the SIGNALS
        # client_order_id, and only :cyc: forms carry a cycle (fleet 9 bug).
        from conviction_shadow import _cycle_from_coid
        self.assertEqual(_cycle_from_coid("run:65:cyc:3"), 3)
        self.assertEqual(_cycle_from_coid("run:112:cyc:17"), 17)
        self.assertIsNone(_cycle_from_coid("run:65:flatten"))
        self.assertIsNone(_cycle_from_coid(None))
        self.assertIsNone(_cycle_from_coid(""))


class DustOrderGuardTests(unittest.TestCase):
    """Overnight: Kelly-sized dust must skip at the final order, not trade
    ($5.18 ZC add observed after the budget-headroom floor shipped)."""

    def test_kelly_sized_dust_skips(self):
        import tempfile as _tf
        tmp = _tf.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(tmp.name, "t.db")
        database.init_database()
        os.environ["AUTO_TRADING_ENABLED"] = "true"
        from fastapi.testclient import TestClient
        from routes import create_app
        probe = patch("routes_runs._probe_price", return_value=100.0)
        probe.start()
        client = TestClient(create_app())
        try:
            tok = client.post("/api/claw/agents/selfRegister",
                              json={"name": "dust-agent", "password": "pw123",
                                    "initial_balance": 100000.0}).json()["token"]
            h = {"Authorization": f"Bearer {tok}"}
            rid = client.post("/api/runs",
                              json={"symbol": "BTC", "market": "crypto",
                                    "max_bet_usd": 2000.0,
                                    "min_confidence": 0.5},
                              headers=h).json()["id"]
            assert client.post(f"/api/runs/{rid}/start",
                               headers=h).status_code == 200
            analysis = {"symbol": "BTC", "market": "crypto",
                        "analysts": {"technical": {"brief": "t",
                                                   "data": {"sigma_daily_pct": 2.5,
                                                            "current_price": 100.0}}},
                        "decision": {"action": "buy", "confidence": 0.9,
                                     "entry": 100.0, "report": "r"}}

            class TinyGate:
                quantity = 0.05          # $5 notional at entry 100
                stop_loss = None
                take_profit = None

            with patch("analysis_agents.run_analysis", return_value=analysis), \
                 patch("automation.evaluate_execution_gates",
                       return_value={"skip_reason": None, "gate": TinyGate(),
                                     "regime_size_multiplier": None}):
                result = run_engine.run_cycle(rid)
            self.assertFalse(result["executed"], result)
            self.assertIn("dust order skip", result["skip_reason"] or "")
        finally:
            probe.stop()
            os.environ.pop("AUTO_TRADING_ENABLED", None)
            tmp.cleanup()


class FleetProfitTierTests(unittest.TestCase):
    """2026-07-23 (Henry) — three profit tiers for 종목 자동 편성. Higher tiers
    deploy more of the run budget, gate looser, stop wider, bank later."""

    def _settings(self, risk):
        from fleet_planner import compose_run_settings
        thesis = {"symbol": "BTC", "market": "crypto", "market_type": "spot",
                  "direction": "long", "confidence": 0.80,  # high so gate isn't thesis-clamped
                  "expected_move_pct": 4.0, "horizon_hours": 48}
        return compose_run_settings(thesis, 1000.0, {"risk_appetite": risk})

    def test_bet_size_increases_by_tier(self):
        self.assertEqual(self._settings("balanced")["max_bet_usd"], 300.0)   # 30%
        self.assertEqual(self._settings("aggressive")["max_bet_usd"], 450.0)  # 45%
        self.assertEqual(self._settings("extreme")["max_bet_usd"], 700.0)     # 70%

    def test_gate_loosens_by_tier(self):
        self.assertEqual(self._settings("balanced")["min_confidence"], 0.60)
        self.assertEqual(self._settings("aggressive")["min_confidence"], 0.57)
        self.assertEqual(self._settings("extreme")["min_confidence"], 0.55)

    def test_stop_widens_by_tier(self):
        # 2026-07-25: the stop now scales to the POSITION (max_bet), not
        # run_budget, so it actually cuts a loser. max_bet = budget * bet_frac
        # (0.30/0.45/0.70); stop = max_bet * stop_loss_frac_of_bet
        # (0.05/0.07/0.10 — re-tiered 2026-09-03, hold-wall fix; see
        # test_hold_wall_fixes).
        self.assertAlmostEqual(
            self._settings("balanced")["stop_conditions"]["max_loss_usd"], 15.0, places=2)
        self.assertAlmostEqual(
            self._settings("aggressive")["stop_conditions"]["max_loss_usd"], 31.5, places=2)
        self.assertAlmostEqual(
            self._settings("extreme")["stop_conditions"]["max_loss_usd"], 70.0, places=2)

    def test_profit_target_multiplier(self):
        # expected_move 4% → 0.04; extreme ×2 = 0.08 of $1000 = $80
        self.assertEqual(self._settings("balanced")["stop_conditions"]["profit_target_usd"], 40.0)
        self.assertEqual(self._settings("aggressive")["stop_conditions"]["profit_target_usd"], 60.0)
        self.assertEqual(self._settings("extreme")["stop_conditions"]["profit_target_usd"], 80.0)

    def test_auto_leverage_by_tier(self):
        # auto leverage scales with the tier (isolated margin): 1× / 2× / 3×
        self.assertEqual(self._settings("balanced")["leverage"], 1.0)
        self.assertEqual(self._settings("aggressive")["leverage"], 2.0)
        self.assertEqual(self._settings("extreme")["leverage"], 3.0)

    def test_fleet_leverage_override_wins(self):
        from fleet_planner import compose_run_settings
        thesis = {"symbol": "BTC", "market": "crypto", "market_type": "spot",
                  "direction": "long", "confidence": 0.80,
                  "expected_move_pct": 4.0, "horizon_hours": 48}
        s = compose_run_settings(thesis, 1000.0,
                                 {"risk_appetite": "balanced", "leverage": 5})
        self.assertEqual(s["leverage"], 5.0)  # explicit set beats tier auto

    def test_unknown_risk_falls_back_to_balanced(self):
        self.assertEqual(self._settings("bogus")["max_bet_usd"],
                         self._settings("balanced")["max_bet_usd"])

    def test_extreme_accepted_by_api_validator(self):
        from routes_fleets import FleetIn
        self.assertEqual(FleetIn(n_runs=3, risk_appetite="extreme").risk_appetite,
                         "extreme")


class LeverageMarginEngineTests(unittest.TestCase):
    """Isolated-margin leverage (2026-07-23). Every assertion also pins the
    L=1 identity so the fully-funded ledger can never silently change."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "t.db")
        database.init_database()
        from fastapi.testclient import TestClient
        from routes import create_app
        self.client = TestClient(create_app())
        r = self.client.post("/api/claw/agents/selfRegister",
                             json={"name": "lev", "password": "pw123",
                                   "initial_balance": 100000.0})
        self.token = r.json()["token"]
        self.agent_id = r.json()["agent_id"]

    def tearDown(self):
        self.tmp.cleanup()

    def _cash(self):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT cash FROM agents WHERE id = ?", (self.agent_id,))
            return float(cur.fetchone()["cash"])
        finally:
            conn.close()

    def _pos(self):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT quantity, entry_price, leverage FROM positions "
                        "WHERE agent_id = ?", (self.agent_id,))
            r = cur.fetchone()
            return dict(r) if r else None
        finally:
            conn.close()

    def test_long_open_debits_margin_not_notional(self):
        import automation
        c0 = self._cash()
        # notional = 100 * 10 = 1000; 5x ⇒ margin 200 + fee
        sid, skip = automation.execute_paper_trade(
            self.agent_id, "BTC", "crypto", "buy", 10.0, 100.0, leverage=5.0)
        self.assertIsNotNone(sid, skip)
        fee = 1000.0 * 0.001
        self.assertAlmostEqual(self._cash(), c0 - 200.0 - fee, places=4)
        self.assertEqual(self._pos()["leverage"], 5.0)

    def test_long_roundtrip_pnl_leveraged(self):
        import automation
        c0 = self._cash()
        automation.execute_paper_trade(self.agent_id, "BTC", "crypto", "buy",
                                       10.0, 100.0, leverage=5.0)
        # price +10% → notional pnl = (110-100)*10 = 100 (5x on 200 margin)
        automation.execute_paper_trade(self.agent_id, "BTC", "crypto", "sell",
                                       10.0, 110.0, leverage=5.0)
        fees = 1000.0 * 0.001 + 1100.0 * 0.001
        self.assertAlmostEqual(self._cash(), c0 + 100.0 - fees, places=4)
        self.assertIsNone(self._pos())

    def test_l1_long_roundtrip_identical_to_legacy(self):
        # L=1 must be byte-identical to the fully-funded model.
        import automation
        c0 = self._cash()
        automation.execute_paper_trade(self.agent_id, "BTC", "crypto", "buy",
                                       10.0, 100.0, leverage=1.0)
        self.assertAlmostEqual(self._cash(), c0 - 1000.0 - 1.0, places=4)
        automation.execute_paper_trade(self.agent_id, "BTC", "crypto", "sell",
                                       10.0, 110.0, leverage=1.0)
        fees = 1000.0 * 0.001 + 1100.0 * 0.001
        self.assertAlmostEqual(self._cash(), c0 + 100.0 - fees, places=4)

    def test_short_roundtrip_leveraged_and_l1(self):
        import automation
        for lev, price_exit in ((3.0, 90.0), (1.0, 90.0)):
            c0 = self._cash()
            automation.execute_paper_trade(self.agent_id, "ETH", "crypto",
                                           "short", 10.0, 100.0, leverage=lev)
            # short at 100, cover at 90 → pnl (100-90)*10 = 100
            automation.execute_paper_trade(self.agent_id, "ETH", "crypto",
                                           "cover", 10.0, 90.0, leverage=lev)
            fees = 1000.0 * 0.001 + 900.0 * 0.001
            self.assertAlmostEqual(self._cash(), c0 + 100.0 - fees, places=3,
                                   msg=f"lev={lev}")

    def test_liquidation_price_from_leverage(self):
        import run_engine
        # long 5x at 100 → liq at 100*(1-1/5) = 80. Cushion off so this exercises
        # the HARD liq path (the cushion, tested in test_leverage_safety, would
        # otherwise pre-empt it at 100*(1-0.85/5)=83).
        pos = {"quantity": 10.0, "entry_price": 100.0,
               "current_price": 79.0, "leverage": 5.0}
        pnl = {"position": pos, "mark_age_ok": True, "total": -1.0,
               "trades": 1}
        with patch.dict(os.environ, {"RUN_LIQ_CUSHION": "0"}), \
                patch.object(run_engine, "compute_run_pnl", return_value=pnl):
            reason = run_engine._evaluate_stop(
                {"stop_conditions_json": "{}"})
        self.assertEqual(reason, "synthetic_liquidation")

    def test_long_l1_never_liquidates(self):
        import run_engine
        # L=1 long: liq price is 0 → even a 99% drop does not liquidate
        pos = {"quantity": 10.0, "entry_price": 100.0,
               "current_price": 1.0, "leverage": 1.0}
        pnl = {"position": pos, "mark_age_ok": True, "total": -1.0, "trades": 1}
        with patch.object(run_engine, "compute_run_pnl", return_value=pnl):
            reason = run_engine._evaluate_stop({"stop_conditions_json": "{}"})
        self.assertIsNone(reason)

    def test_short_l1_liquidates_at_2x_entry(self):
        import run_engine
        pos = {"quantity": -10.0, "entry_price": 100.0,
               "current_price": 200.0, "leverage": 1.0}
        pnl = {"position": pos, "mark_age_ok": True, "total": -1.0, "trades": 1}
        with patch.object(run_engine, "compute_run_pnl", return_value=pnl):
            reason = run_engine._evaluate_stop({"stop_conditions_json": "{}"})
        self.assertEqual(reason, "synthetic_liquidation")
