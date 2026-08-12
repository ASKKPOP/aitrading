"""Research 04 follow-up (owner, 2026-08-11): the manipulation defense must
have an explicit, tested EFFECT in each automation mode's symbol path —
Full Auto (fleet research picks symbols), Agent mode (planner picks from a
candidate universe), Simple mode (the user picks; the platform advises).

The desk-prompt skills and the hot-issue daemon already cover every RUNNING
position in all three modes; these tests pin the symbol-SELECTION seams.
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


class _DBBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()

    def tearDown(self):
        self.tmp.cleanup()


def _survivor(symbol="PUMPY", market="crypto"):
    return {"symbol": symbol, "market": market,
            "factors": {"last": 1.23, "mom_5d": 2.0, "mom_20d": 5.0,
                        "vol_daily_pct": 4.0, "vol_ratio": 1.2},
            "subscores": {"technical": 0.5},
            "eps_raw": 0.4, "coverage": 0.4, "screen_score": 0.5,
            "momentum_sign": 1.0, "session_open": True}


class FullAutoResearchOverlay(_DBBase):
    """Fleet symbols come from research theses — the thesis prompt must carry
    the manipulation shape for a flagged crypto candidate, and stay
    byte-stable when the detector is quiet."""

    def _prompt_for(self, signals):
        import symbol_research as sr
        seen = {}

        def fake_llm(prompt, **kw):
            seen["prompt"] = prompt
            return "[]"
        with patch("manipulation.manipulation_signals",
                   return_value=signals):
            sr.generate_theses([_survivor()], generate_text=fake_llm)
        return seen.get("prompt", "")

    def test_flagged_candidate_carries_the_shape_and_instruction(self):
        prompt = self._prompt_for(["manipulation:pump_ignition"])
        self.assertIn('"manipulation_shape": ["pump_ignition"]', prompt)
        self.assertIn("manipulation_shape", prompt.split("CANDIDATES:")[0],
                      "instruction sentence missing from the prompt header")

    def test_quiet_detector_leaves_the_prompt_unchanged(self):
        prompt = self._prompt_for([])
        self.assertNotIn("manipulation_shape", prompt)

    def test_detector_failure_is_fail_soft(self):
        import symbol_research as sr
        seen = {}

        def fake_llm(prompt, **kw):
            seen["prompt"] = prompt
            return "[]"
        with patch("manipulation.manipulation_signals",
                   side_effect=RuntimeError("okx down")):
            sr.generate_theses([_survivor()], generate_text=fake_llm)
        self.assertIn("PUMPY", seen.get("prompt", ""))
        self.assertNotIn("manipulation_shape", seen["prompt"])

    def test_us_stock_candidates_never_call_the_detector(self):
        import symbol_research as sr
        called = {}

        def spy(sym):
            called["sym"] = sym
            return []
        with patch("manipulation.manipulation_signals", side_effect=spy):
            sr.generate_theses([_survivor(symbol="AAPL", market="us-stock")],
                               generate_text=lambda p, **kw: "[]")
        self.assertEqual(called, {})


class AgentModeUniverseScreen(_DBBase):
    """The delegated planner must not hand a pump-flagged symbol to the LLM
    as a pickable candidate — zero-LLM screen, fail-open on detector error."""

    def _plan(self, manip_side_effect):
        import json
        import agent_planner
        seen = {}
        ok = json.dumps({"symbol": "BTCUSDT", "interval_minutes": 60,
                         "min_confidence": 0.65, "size_usd": 500,
                         "risk_level": "balanced", "rationale": "ok"})

        def fake_gen(prompt, **kw):
            seen["prompt"] = prompt
            return ok
        with patch.object(agent_planner, "_gather_context",
                          return_value={"scanner_candidates": [],
                                        "top_symbols": ["PUMPY", "BTCUSDT",
                                                        "ETHUSDT"],
                                        "budget_usd": 10000.0}), \
             patch("llm_client.llm_configured", return_value=True), \
             patch("manipulation.manipulation_signals",
                   side_effect=manip_side_effect), \
             patch("trading_skills.skills_block", return_value=""), \
             patch("llm_client.generate_text", side_effect=fake_gen), \
             patch("llm_client.active_provider_model", return_value="m"):
            agent_planner.plan_agent_cycle(
                {"id": 1, "agent_id": 1, "symbol": "AGENT",
                 "market": "crypto", "mode": "agent",
                 "budget_usd": 10000.0, "interval_minutes": 60,
                 "min_confidence": 0.65, "size_usd": 500.0})
        return seen.get("prompt", "")

    def test_pump_flagged_symbol_is_dropped_from_allowed(self):
        prompt = self._plan(
            lambda s: ["manipulation:pump_ignition"] if s == "PUMPY" else [])
        self.assertNotIn("'PUMPY'", prompt)
        self.assertIn("BTCUSDT", prompt)

    def test_detector_error_fails_open_keeping_the_universe(self):
        prompt = self._plan(RuntimeError("okx down"))
        self.assertIn("PUMPY", prompt)

    def test_crowded_funding_alone_does_not_drop(self):
        # funding crowding is a judgment input, not a mechanical veto
        prompt = self._plan(
            lambda s: ["manipulation:crowded_funding"] if s == "PUMPY" else [])
        self.assertIn("PUMPY", prompt)


class SimpleModeAdvisory(_DBBase):
    """The user picks the symbol; the platform ADVISES (never blocks) at run
    creation, in the user's language."""

    def setUp(self):
        super().setUp()
        from fastapi.testclient import TestClient
        from main import create_app
        self.client = TestClient(create_app())
        resp = self.client.post(
            "/api/claw/agents/selfRegister",
            json={"name": "simple", "password": "pw123",
                  "initial_balance": 100000.0})
        assert resp.status_code == 200
        self.headers = {"Authorization": f"Bearer {resp.json()['token']}"}

    def _create(self, signals, symbol="BTC", market="crypto", lang="ko"):
        with patch("manipulation.manipulation_signals",
                   return_value=signals):
            r = self.client.post(
                "/api/runs", headers=self.headers,
                json={"symbol": symbol, "market": market,
                      "market_type": "spot", "lang": lang,
                      "interval_minutes": 60, "min_confidence": 0.65,
                      "max_bet_usd": 500})
        return r

    def test_flagged_symbol_returns_localized_advisory_not_a_block(self):
        r = self._create(["manipulation:pump_ignition"])
        self.assertEqual(r.status_code, 200)          # advisory, never a block
        adv = r.json().get("manipulation_advisory")
        self.assertIsNotNone(adv)
        self.assertEqual(adv["signals"], ["manipulation:pump_ignition"])
        self.assertIn("펌핑형 급등", adv["text"])        # ko localization

    def test_quiet_symbol_has_no_advisory(self):
        r = self._create([])
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(r.json().get("manipulation_advisory"))

    def test_non_crypto_never_calls_the_detector(self):
        called = {}

        def spy(sym):
            called["sym"] = sym
            return []
        with patch("manipulation.manipulation_signals", side_effect=spy):
            r = self.client.post(
                "/api/runs", headers=self.headers,
                json={"symbol": "AAPL", "market": "us-stock",
                      "market_type": "spot", "lang": "en",
                      "interval_minutes": 60, "min_confidence": 0.65,
                      "max_bet_usd": 500})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(called, {})


class BriefTruncationPriority(unittest.TestCase):
    """The technical brief renders only the first TWO risk lines — a pump
    shape must therefore be the FIRST risk, or the desk never sees it."""

    def test_pump_risk_line_is_first(self):
        from unittest.mock import patch as p
        closes = [100.0 + i * 0.1 for i in range(120)]
        daily = [{"ts": i, "open": c, "high": c, "low": c, "close": c,
                  "volume": 50.0} for i, c in enumerate(closes)]
        hourly = [{"ts": i, "open": 100.0, "high": 100.0, "low": 100.0,
                   "close": 100.0, "volume": 50.0} for i in range(30)]
        hourly[-1].update({"open": 100.0, "close": 108.0, "volume": 500.0})

        def fake_candles(symbol, bar="1H", limit=100):
            return daily if bar == "1D" else hourly

        from quant_crypto import build_crypto_analysis
        with p("crypto_feed.fetch_candles", side_effect=fake_candles), \
             p("crypto_feed.fetch_funding_rate",
               return_value={"symbol": "BTCUSDT", "funding_rate": 0.002,
                             "next_funding_time": None}), \
             p("crypto_feed.fetch_ticker",
               return_value={"symbol": "BTCUSDT", "last_price": "108.0"}), \
             p("crypto_feed.fetch_spot_ticker",
               return_value={"symbol": "BTCUSDT", "last_price": 108.0}), \
             p("crypto_feed.fetch_open_interest",
               return_value={"symbol": "BTCUSDT", "open_interest": 1000.0,
                             "open_interest_ccy": 1000.0}), \
             p("crypto_feed.fetch_long_short_ratio",
               return_value={"symbol": "BTCUSDT", "long_short_ratio": 3.0,
                             "ts": None}):
            analysis = build_crypto_analysis("BTC")
        risks = analysis["risk_factors"]
        # crowded funding + crowded long/short both fire above, yet the pump
        # shape must still sit at index 0 (the brief shows risks[:2])
        self.assertTrue(risks and "pump-shaped spike" in risks[0], risks)


if __name__ == "__main__":
    unittest.main()
