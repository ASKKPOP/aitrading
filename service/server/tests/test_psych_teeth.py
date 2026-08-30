"""Plan 31 item 8 — psychology with teeth, shadow first.

Two dormant mechanisms, verified in R5 (research/replan30/reports/R5.md):

  * crypto's 0.20 psych weight NEVER bound — the subscore was hardcoded
    None (symbol_research.py), so coverage renormalization removed it and
    crypto candidate ranking read ZERO psychology. Now an F&G-derived
    contrarian tilt (cached snapshot only) feeds it, behind
    CRYPTO_PSYCH_SUBSCORE (default ON; off/feed-down = old behavior).
  * the regime engine's enforcement (size×0.5 / no-new-buys) is dormant
    behind REGIME_FILTER_ENABLED (default False) and its bands are
    self-described unvalidated placeholders — a global enable is rejected.
    REGIME_SHADOW=1 logs what the policy WOULD do (veto/resize/allow) at
    the automation gate sites without enforcing anything; with both flags
    off the gate chain is byte-identical, and with REGIME_FILTER_ENABLED
    the real enforcement is untouched.
"""

from __future__ import annotations

import hashlib
import json
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
import symbol_research as sr

_ENV_KEYS = ("CRYPTO_PSYCH_SUBSCORE", "REGIME_SHADOW", "REGIME_FILTER_ENABLED")


def _clean_env():
    for key in _ENV_KEYS:
        os.environ.pop(key, None)


def _psych_payload(fng_value):
    return {"available": True, "fear_greed": {"value": fng_value}}


def _patched_feed(fng_value):
    """Patch the snapshot accessors — never the network."""
    return (patch("psych_feed.psych_feed_enabled", return_value=True),
            patch("psych_feed.get_psych_payload",
                  return_value=_psych_payload(fng_value)))


class CryptoPsychTiltTests(unittest.TestCase):
    """F&G → contrarian tilt ∈ [−1, +1]; neutral 30–70; fail-soft None."""

    def setUp(self):
        _clean_env()

    def tearDown(self):
        _clean_env()

    def _tilt(self, fng_value):
        p1, p2 = _patched_feed(fng_value)
        with p1, p2:
            return sr.crypto_psych_tilt()

    def test_extreme_fear_is_a_positive_tilt(self):
        self.assertAlmostEqual(self._tilt(0), 1.0)
        self.assertAlmostEqual(self._tilt(10), 2.0 / 3.0)

    def test_extreme_greed_is_a_negative_tilt(self):
        self.assertAlmostEqual(self._tilt(100), -1.0)
        self.assertAlmostEqual(self._tilt(90), -2.0 / 3.0)

    def test_mid_band_is_a_real_neutral_zero(self):
        for fng in (30, 50, 69):
            self.assertEqual(self._tilt(fng), 0.0, fng)
        self.assertEqual(self._tilt(70), 0.0)  # band edge, matches regime.py [30,70)

    def test_feed_error_is_none(self):
        with patch("psych_feed.psych_feed_enabled", return_value=True), \
             patch("psych_feed.get_psych_payload",
                   side_effect=RuntimeError("db down")):
            self.assertIsNone(sr.crypto_psych_tilt())

    def test_feed_disabled_is_none(self):
        with patch("psych_feed.psych_feed_enabled", return_value=False):
            self.assertIsNone(sr.crypto_psych_tilt())

    def test_missing_fng_value_is_none(self):
        with patch("psych_feed.psych_feed_enabled", return_value=True), \
             patch("psych_feed.get_psych_payload",
                   return_value={"available": True, "fear_greed": None}):
            self.assertIsNone(sr.crypto_psych_tilt())


def _candles(n=60, start=100.0, drift=0.5, volume=5_000_000):
    out, price = [], start
    for i in range(n):
        price *= 1 + drift / 100.0
        out.append({"ts": i, "open": price, "high": price, "low": price,
                    "close": price, "volume": volume})
    return out


_OVERLAYS = {"event_window": False, "regime_blocks_longs": False, "policy": {}}


class CryptoPsychScreenTests(unittest.TestCase):
    """The subscore reaches the composite and the 0.20 weight binds."""

    def setUp(self):
        _clean_env()

    def tearDown(self):
        _clean_env()

    def _fetch(self, sym, market):
        drift = {"UP": 1.2, "DOWN": -1.2}.get(sym, 0.6)
        return _candles(drift=drift)

    def _screen(self, universe):
        return sr.screen_universe(universe, fetch_candles=self._fetch,
                                  overlays=dict(_OVERLAYS))

    def test_fear_boosts_longs_and_penalizes_shorts(self):
        universe = [{"symbol": "UP", "market": "crypto"},
                    {"symbol": "DOWN", "market": "crypto"}]
        p1, p2 = _patched_feed(10)  # tilt +2/3
        with p1, p2:
            by = {s["symbol"]: s for s in self._screen(universe)}
        self.assertAlmostEqual(by["UP"]["subscores"]["psych"], 2.0 / 3.0)
        self.assertAlmostEqual(by["DOWN"]["subscores"]["psych"], -2.0 / 3.0)

    def test_greed_fades_longs(self):
        p1, p2 = _patched_feed(90)  # tilt −2/3
        with p1, p2:
            got = self._screen([{"symbol": "UP", "market": "crypto"}])
        self.assertAlmostEqual(got[0]["subscores"]["psych"], -2.0 / 3.0)

    def test_mid_band_contributes_a_real_zero(self):
        p1, p2 = _patched_feed(50)
        with p1, p2:
            got = self._screen([{"symbol": "UP", "market": "crypto"}])
        self.assertEqual(got[0]["subscores"]["psych"], 0.0)

    def test_feed_down_preserves_current_behavior(self):
        with patch("psych_feed.psych_feed_enabled", return_value=True), \
             patch("psych_feed.get_psych_payload",
                   side_effect=RuntimeError("down")):
            got = self._screen([{"symbol": "UP", "market": "crypto"}])
        self.assertTrue(got)
        self.assertIsNone(got[0]["subscores"]["psych"])

    def test_kill_switch_restores_none_even_with_a_live_feed(self):
        os.environ["CRYPTO_PSYCH_SUBSCORE"] = "0"
        with patch.object(sr, "crypto_psych_tilt",
                          side_effect=AssertionError("must not read the feed")):
            got = self._screen([{"symbol": "UP", "market": "crypto"}])
        self.assertIsNone(got[0]["subscores"]["psych"])

    def test_the_020_weight_binds_in_the_composite(self):
        """Same technical, different psych ⇒ different rank_score."""
        self.assertEqual(sr.WEIGHT_PROFILES["crypto"]["psych"], 0.20)
        base = sr.composite_score({"technical": 0.5, "psych": None}, "crypto")
        pos = sr.composite_score({"technical": 0.5, "psych": 1.0}, "crypto")
        neg = sr.composite_score({"technical": 0.5, "psych": -1.0}, "crypto")
        # renormalized blend: (.30*.5 ± .20*1.0) / .50
        self.assertAlmostEqual(pos["eps_raw"], 0.7)
        self.assertAlmostEqual(neg["eps_raw"], -0.1)
        self.assertGreater(pos["rank_score"], base["rank_score"])
        self.assertLess(neg["rank_score"], base["rank_score"])

    def test_fear_raises_a_long_candidates_screen_score(self):
        universe = [{"symbol": "UP", "market": "crypto"}]
        without = self._screen(universe)[0]["screen_score"]
        p1, p2 = _patched_feed(5)
        with p1, p2:
            with_fear = self._screen(universe)[0]["screen_score"]
        self.assertGreater(with_fear, without)

    def test_crypto_tilt_never_leaks_to_other_markets(self):
        """Round-2 mutation pin (Q3 #7): the tilt is market-scoped — a mutant
        dropping the market == 'crypto' guard fed the crypto F&G tilt into
        us-stock and forex candidates' psych subscores."""
        os.environ.pop("FLEET_PSYCH_WEIGHTS_V2", None)  # us_tilts path off
        universe = [{"symbol": "UP", "market": "crypto"},
                    {"symbol": "AAPL", "market": "us-stock"},
                    {"symbol": "EURUSD", "market": "forex"}]
        p1, p2 = _patched_feed(5)  # extreme fear, tilt = +25/30
        with p1, p2:
            by = {(s["symbol"], s["market"]): s for s in self._screen(universe)}
        self.assertAlmostEqual(by[("UP", "crypto")]["subscores"]["psych"],
                               25.0 / 30.0)
        self.assertIn(("AAPL", "us-stock"), by)
        self.assertIn(("EURUSD", "forex"), by)
        self.assertIsNone(by[("AAPL", "us-stock")]["subscores"]["psych"])
        self.assertIsNone(by[("EURUSD", "forex")]["subscores"]["psych"])


# ── regime shadow mode at the automation gate sites ─────────────────────────

def _regime_read(*, regime="panic", allow_new_buys=False, size_multiplier=0.0,
                 enforced=False):
    return {"regime": regime, "reasons": [f"synthetic {regime} read"],
            "allow_new_buys": allow_new_buys,
            "size_multiplier": size_multiplier, "enforced": enforced}


_PANIC_ADVISORY = dict(_regime_read())
_CAUTION_ADVISORY = dict(_regime_read(regime="caution", allow_new_buys=True,
                                      size_multiplier=0.5))
_PANIC_ENFORCED = dict(_regime_read(enforced=True))
_CAUTION_ENFORCED = dict(_regime_read(regime="caution", allow_new_buys=True,
                                      size_multiplier=0.5, enforced=True))


class _DbTestCase(unittest.TestCase):
    def setUp(self):
        _clean_env()
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()

    def tearDown(self):
        _clean_env()
        self.tmp.cleanup()


class RegimeShadowGateTests(_DbTestCase):
    """Shadow logs the would-be action; it never blocks or resizes."""

    def setUp(self):
        super().setUp()
        token_hash = hashlib.sha256(b"psych-teeth").hexdigest()
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO agents (name, token, token_hash, cash) VALUES (?, NULL, ?, ?)",
            ("psych-teeth", token_hash, 100_000.0))
        self.agent_id = cursor.lastrowid
        conn.commit()
        conn.close()

    def _gates(self, regime_read, action="buy"):
        from automation import evaluate_execution_gates
        config = {"auto_execute": 1, "account_type": "simulator",
                  "min_confidence": 0.1, "size_usd": 100.0}
        return evaluate_execution_gates(config, self.agent_id, "BTC", "crypto",
                                        action, 0.9, 100.0, dict(regime_read),
                                        {"sigma_daily_pct": 2.0})

    def test_shadow_does_not_block_a_would_be_vetoed_entry(self):
        os.environ["REGIME_SHADOW"] = "1"
        with self.assertLogs("regime", level="INFO") as logs:
            gates = self._gates(_PANIC_ADVISORY)
        self.assertIsNone(gates["skip_reason"])
        self.assertEqual(gates["regime_shadow"]["would_action"], "veto")
        line = next(m for m in logs.output if "regime_shadow" in m)
        payload = json.loads(line.split("regime_shadow ", 1)[1])
        self.assertEqual(payload["market"], "crypto")
        self.assertEqual(payload["symbol"], "BTC")
        self.assertEqual(payload["regime"], "panic")
        self.assertEqual(payload["would_action"], "veto")
        self.assertEqual(payload["size_mult"], 0.0)

    def test_shadow_reports_resize_but_quantity_is_untouched(self):
        os.environ["REGIME_SHADOW"] = "1"
        captured = {}

        def fake_evaluate_order(agent_id, symbol, market, action, quantity,
                                entry, **kwargs):
            captured["quantity"] = quantity
            from risk_engine import GateDecision
            return GateDecision(allowed=False, quantity=0.0, reason="stop here")

        with patch("risk_engine.evaluate_order", side_effect=fake_evaluate_order):
            gates = self._gates(_CAUTION_ADVISORY)
        self.assertEqual(gates["regime_shadow"]["would_action"], "resize")
        self.assertEqual(gates["regime_shadow"]["size_mult"], 0.5)
        self.assertIsNone(gates["regime_size_multiplier"])
        self.assertEqual(captured["quantity"], 1.0)  # 100 USD / 100 — unhalved

    def test_shadow_never_evaluates_sells(self):
        os.environ["REGIME_SHADOW"] = "1"
        # a sell has no long position → skip, but never a shadow verdict
        gates = self._gates(_PANIC_ADVISORY, action="sell")
        self.assertNotIn("regime_shadow", gates)

    def test_both_flags_off_is_byte_identical(self):
        with self.assertNoLogs("regime", level="INFO"):
            gates = self._gates(_PANIC_ADVISORY)
        self.assertIsNone(gates["skip_reason"])
        self.assertNotIn("regime_shadow", gates)
        self.assertIsNone(gates["regime_size_multiplier"])

    def test_enforced_veto_still_blocks(self):
        for shadow_flag in (None, "1"):
            _clean_env()
            if shadow_flag:
                os.environ["REGIME_SHADOW"] = shadow_flag
            gates = self._gates(_PANIC_ENFORCED)
            self.assertIn("regime 'panic' blocks new buys",
                          gates["skip_reason"], f"REGIME_SHADOW={shadow_flag}")
            self.assertNotIn("regime_shadow", gates)

    def test_none_read_with_shadow_on_fails_soft(self):
        """Round-2 mutation pin (Q3 #9): REGIME_SHADOW=1 with regime_read
        None (any non-crypto or read-failure path) must neither raise nor
        emit a shadow verdict — a mutant dropping the None guard crashed
        the whole gate chain on every such cycle."""
        os.environ["REGIME_SHADOW"] = "1"
        from automation import evaluate_execution_gates
        config = {"auto_execute": 1, "account_type": "simulator",
                  "min_confidence": 0.1, "size_usd": 100.0}
        gates = evaluate_execution_gates(config, self.agent_id, "BTC",
                                         "crypto", "buy", 0.9, 100.0, None,
                                         {"sigma_daily_pct": 2.0})
        self.assertIsNone(gates["skip_reason"])
        self.assertNotIn("regime_shadow", gates)
        self.assertIsNone(gates["regime_size_multiplier"])

    def test_enforced_caution_still_halves_size(self):
        os.environ["REGIME_SHADOW"] = "1"  # must not interfere with enforcement
        captured = {}

        def fake_evaluate_order(agent_id, symbol, market, action, quantity,
                                entry, **kwargs):
            captured["quantity"] = quantity
            from risk_engine import GateDecision
            return GateDecision(allowed=False, quantity=0.0, reason="stop here")

        with patch("risk_engine.evaluate_order", side_effect=fake_evaluate_order):
            gates = self._gates(_CAUTION_ENFORCED)
        self.assertEqual(gates["regime_size_multiplier"], 0.5)
        self.assertEqual(captured["quantity"], 0.5)
        self.assertNotIn("regime_shadow", gates)


class ShadowAllowVerdictTests(unittest.TestCase):
    """Round-2 mutation pin (Q3 #8): an allow-regime buy must return a dict
    with would_action 'allow' — a mutant returning None there silently
    dropped the census DENOMINATOR (allowed entries)."""

    def setUp(self):
        _clean_env()

    def tearDown(self):
        _clean_env()

    def test_allow_regime_buy_returns_allow_verdict(self):
        os.environ["REGIME_SHADOW"] = "1"
        import regime
        read = {"regime": "trend", "reasons": [], "allow_new_buys": True,
                "size_multiplier": 1.0, "enforced": False}
        with self.assertLogs("regime", level="INFO") as logs:
            verdict = regime.shadow_gate_check(read, market="crypto",
                                               symbol="BTC", action="buy")
        self.assertIsNotNone(verdict)
        self.assertEqual(verdict["would_action"], "allow")
        self.assertEqual(verdict["size_mult"], 1.0)
        line = next(m for m in logs.output if "regime_shadow" in m)
        payload = json.loads(line.split("regime_shadow ", 1)[1])
        self.assertEqual(payload["would_action"], "allow")


_BUY_ANALYSIS = {
    "symbol": "BTC",
    "market": "crypto",
    "analysts": {"technical": {"brief": "t",
                               "data": {"sigma_daily_pct": 2.5,
                                        "current_price": 100.0}}},
    "decision": {"action": "buy", "confidence": 0.9, "entry": 100.0,
                 "report": "r"},
}


class RegimeShadowRunRuleTests(_DbTestCase):
    """End to end: the would-vetoed entry executes and the verdict rides
    the regime telemetry (automation_runs row via _record_run)."""

    def setUp(self):
        super().setUp()
        from fastapi.testclient import TestClient
        from routes import create_app
        self.client = TestClient(create_app())
        resp = self.client.post(
            "/api/claw/agents/selfRegister",
            json={"name": "teeth", "password": "pw123",
                  "initial_balance": 100000.0})
        assert resp.status_code == 200, resp.text
        self.agent_id = resp.json()["agent_id"]

    def _config(self):
        return {"id": 1, "agent_id": self.agent_id, "symbol": "BTC",
                "market": "crypto", "interval_minutes": 60,
                "min_confidence": 0.5, "size_usd": 500.0,
                "auto_execute": 1, "account_type": "simulator"}

    def _run(self):
        import automation
        with patch("analysis_agents.run_analysis", return_value=_BUY_ANALYSIS), \
             patch("confluence.evaluate_confluence",
                   return_value={"conditions": {}, "score": 0}), \
             patch("regime.evaluate_market_regime",
                   return_value=dict(_PANIC_ADVISORY)):
            return automation.run_rule(self._config())

    def test_shadow_logs_and_executes_the_would_vetoed_entry(self):
        os.environ["REGIME_SHADOW"] = "1"
        with self.assertLogs("regime", level="INFO"):
            result = self._run()
        self.assertTrue(result["executed"], result.get("skip_reason"))
        self.assertEqual(result["regime"]["shadow"]["would_action"], "veto")

    def test_flags_off_run_rule_is_unchanged(self):
        with self.assertNoLogs("regime", level="INFO"):
            result = self._run()
        self.assertTrue(result["executed"], result.get("skip_reason"))
        self.assertNotIn("shadow", result["regime"])


if __name__ == "__main__":
    unittest.main()
