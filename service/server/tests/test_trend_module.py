"""Plan 31 item 7 — trend edge module (sim-only, default OFF).

Deterministic, no network: bars are fabricated, the LLM is patched
(llm_client.generate_text — unit tests never make live LLM calls), and the
F&G accessor is patched. Covers: Wilder ATR/ADX arithmetic vs hand-computed
values, Donchian break + regime gates, the F&G overlay (≥80 blocks longs,
≤20 enables the contrarian tag), chandelier trail update + exit triggers,
time-stop, vol-parity sizing, disabled-by-default, the TREND_AGENT_ID
refusal, and the full cycle against the real simulated ledger.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
import trend_module as tm


# ─────────────────────────── bar fabricators ───────────────────────────

def _bars_up(n=220, base=100.0, step=0.5, final_jump=5.0):
    """Steady uptrend whose final close breaks the prior 20d high."""
    bars, price = [], base
    for i in range(n):
        price += step
        bars.append({"ts": i, "open": price, "high": price + 1.0,
                     "low": price - 1.0, "close": price, "volume": 1e6})
    last = dict(bars[-1])
    last["close"] += final_jump
    last["high"] = max(last["high"], last["close"])
    bars[-1] = last
    return bars


def _bars_down(n=220, base=1000.0, step=0.5, final_drop=5.0):
    """Steady downtrend whose final close breaks the prior 20d low."""
    bars, price = [], base
    for i in range(n):
        price -= step
        bars.append({"ts": i, "open": price, "high": price + 1.0,
                     "low": price - 1.0, "close": price, "volume": 1e6})
    last = dict(bars[-1])
    last["close"] -= final_drop
    last["low"] = min(last["low"], last["close"])
    bars[-1] = last
    return bars


class TestWilderArithmetic(unittest.TestCase):
    def test_atr_constant_true_range(self):
        # Every bar: high 101, low 99, close 100 → TR = 2 exactly, so any
        # amount of Wilder smoothing must return exactly 2.
        n = 40
        highs, lows, closes = [101.0] * n, [99.0] * n, [100.0] * n
        self.assertAlmostEqual(tm.wilder_atr(highs, lows, closes), 2.0, places=10)

    def test_atr_hand_computed_ramp(self):
        # close=0, low=0, high_i = i for i=1..15 → TR sequence 1..15.
        # Seed = mean(1..14) = 7.5; next = (7.5·13 + 15)/14 = 8.0357142857.
        highs = [0.0] + [float(i) for i in range(1, 16)]
        lows = [0.0] * 16
        closes = [0.0] * 16
        self.assertAlmostEqual(tm.wilder_atr(highs, lows, closes),
                               112.5 / 14.0, places=10)

    def test_atr_insufficient_bars(self):
        self.assertIsNone(tm.wilder_atr([1.0] * 14, [1.0] * 14, [1.0] * 14))

    def test_adx_pure_uptrend_is_100(self):
        # highs/lows/closes all rise 1/bar: +DM=1, −DM=0 every bar, so
        # DX = 100·|+DI−0|/(+DI+0) = 100 for every bar → ADX = 100 exactly.
        n = 40
        highs = [100.0 + i for i in range(n)]
        lows = [99.0 + i for i in range(n)]
        closes = [99.5 + i for i in range(n)]
        self.assertAlmostEqual(tm.wilder_adx(highs, lows, closes), 100.0, places=8)

    def test_adx_flat_market_is_0(self):
        n = 40
        highs, lows, closes = [101.0] * n, [99.0] * n, [100.0] * n
        self.assertAlmostEqual(tm.wilder_adx(highs, lows, closes), 0.0, places=10)

    def test_adx_insufficient_bars(self):
        self.assertIsNone(tm.wilder_adx([1.0] * 28, [1.0] * 28, [1.0] * 28))


class TestSignalGates(unittest.TestCase):
    def test_donchian_long_break_with_gates_passing(self):
        bars = _bars_up()
        with patch.object(tm, "wilder_adx", return_value=30.0):
            sig = tm.evaluate_symbol(bars, fear_greed=50)
        self.assertIsNotNone(sig)
        self.assertEqual(sig["side"], "buy")
        self.assertEqual(sig["entry_kind"], "donchian")

    def test_adx_out_of_band_blocks(self):
        bars = _bars_up()
        for adx in (20.0, 45.0):
            with patch.object(tm, "wilder_adx", return_value=adx):
                self.assertIsNone(tm.evaluate_symbol(bars, fear_greed=50))

    def test_ma200_gate_blocks_long(self):
        # Breakout above the 20d channel but far below the 200MA: 200 bars
        # at 1000, then 21 bars near 100 with a final pop to 110.
        bars = []
        for i in range(200):
            bars.append({"ts": i, "open": 1000.0, "high": 1001.0,
                         "low": 999.0, "close": 1000.0, "volume": 1e6})
        for i in range(200, 221):
            bars.append({"ts": i, "open": 100.0, "high": 101.0,
                         "low": 99.0, "close": 100.0, "volume": 1e6})
        bars[-1] = {**bars[-1], "close": 110.0, "high": 110.0}
        with patch.object(tm, "wilder_adx", return_value=30.0):
            self.assertIsNone(tm.evaluate_symbol(bars, fear_greed=50))

    def test_donchian_short_break_with_gates_passing(self):
        bars = _bars_down()
        with patch.object(tm, "wilder_adx", return_value=30.0):
            sig = tm.evaluate_symbol(bars, fear_greed=50)
        self.assertIsNotNone(sig)
        self.assertEqual(sig["side"], "short")
        self.assertEqual(sig["entry_kind"], "donchian")

    def test_greed_80_blocks_new_longs(self):
        bars = _bars_up()
        with patch.object(tm, "wilder_adx", return_value=30.0):
            blocked = tm.evaluate_symbol(bars, fear_greed=80)
            allowed = tm.evaluate_symbol(bars, fear_greed=79)
        self.assertIsNone(blocked["side"])
        self.assertEqual(blocked["blocked"], "fg_greed_no_new_longs")
        self.assertEqual(allowed["side"], "buy")

    def test_fear_20_enables_contrarian_long(self):
        # Down-break under extreme fear → contrarian long, tagged, even
        # though ADX (50, out of band) and the 200MA (close below) both fail.
        bars = _bars_down()
        with patch.object(tm, "wilder_adx", return_value=50.0):
            sig = tm.evaluate_symbol(bars, fear_greed=20)
            none_sig = tm.evaluate_symbol(bars, fear_greed=30)
        self.assertEqual(sig["side"], "buy")
        self.assertEqual(sig["entry_kind"], "fg_contrarian")
        self.assertIsNone(none_sig)  # no extreme fear → regime gates bind

    def test_insufficient_history(self):
        self.assertIsNone(tm.evaluate_symbol(_bars_up(n=150), fear_greed=50))


class TestTrailAndExits(unittest.TestCase):
    def _long(self, **over):
        pos = {"side": "long", "qty": 1.0, "entry_price": 100.0,
               "entry_atr": 2.0, "initial_stop": 97.0, "trail": None,
               "best_close": 100.0,
               "entry_ts": datetime.now(timezone.utc).isoformat()}
        pos.update(over)
        return pos

    def test_trail_ratchets_up_and_never_loosens(self):
        pos = self._long()
        tm.update_trail(pos, 110.0, 2.0)
        self.assertAlmostEqual(pos["trail"], 104.0)   # 110 − 3×2
        tm.update_trail(pos, 108.0, 2.0)
        self.assertAlmostEqual(pos["best_close"], 110.0)
        self.assertAlmostEqual(pos["trail"], 104.0)   # best close unchanged
        tm.update_trail(pos, 108.0, 4.0)
        self.assertAlmostEqual(pos["trail"], 104.0)   # ATR expansion: no loosen

    def test_trail_stop_triggers_on_close_cross(self):
        pos = self._long(trail=104.0, best_close=110.0)
        self.assertEqual(tm.check_exit(pos, 103.9), "trail_stop")
        self.assertIsNone(tm.check_exit(pos, 104.1))

    def test_initial_stop_before_trail_arms(self):
        pos = self._long()   # trail None, initial 97
        self.assertEqual(tm.check_exit(pos, 96.5), "initial_stop")
        self.assertIsNone(tm.check_exit(pos, 97.5))

    def test_short_mirror(self):
        pos = {"side": "short", "qty": 1.0, "entry_price": 100.0,
               "entry_atr": 2.0, "initial_stop": 103.0, "trail": None,
               "best_close": 100.0,
               "entry_ts": datetime.now(timezone.utc).isoformat()}
        tm.update_trail(pos, 90.0, 2.0)
        self.assertAlmostEqual(pos["trail"], 96.0)    # 90 + 3×2
        tm.update_trail(pos, 92.0, 4.0)
        self.assertAlmostEqual(pos["trail"], 96.0)    # never loosens
        self.assertEqual(tm.check_exit(pos, 96.5), "trail_stop")
        self.assertIsNone(tm.check_exit(pos, 95.0))

    def test_time_stop(self):
        stale = (datetime.now(timezone.utc) - timedelta(days=31)).isoformat()
        pos = self._long(entry_ts=stale, trail=1.0, initial_stop=1.0)
        self.assertEqual(tm.check_exit(pos, 500.0), "time_stop")


class TestSizing(unittest.TestCase):
    def test_vol_parity_default_risk(self):
        os.environ.pop("TREND_RISK_USD", None)
        self.assertAlmostEqual(tm.position_qty(2.0), 25.0 / 3.0)   # 25/(1.5×2)

    def test_env_risk_and_size_mult(self):
        os.environ["TREND_RISK_USD"] = "50"
        try:
            self.assertAlmostEqual(tm.position_qty(2.0), 50.0 / 3.0)
            self.assertAlmostEqual(tm.position_qty(2.0, 0.5), 25.0 / 3.0)
        finally:
            del os.environ["TREND_RISK_USD"]

    def test_zero_atr(self):
        self.assertEqual(tm.position_qty(0.0), 0.0)


class CycleBase(unittest.TestCase):
    """Full cycle against the real simulated ledger (tmp sqlite)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO users (email, password_hash, created_at) "
            "VALUES ('trend@x.com', 'x', '2026-01-01T00:00:00Z')")
        user_id = cur.lastrowid
        cur.execute(
            "INSERT INTO agents (name, token_hash, cash, user_id, created_at) "
            "VALUES ('trend-agent', 'tth1', 100000, ?, '2026-01-01T00:00:00Z')",
            (user_id,))
        self.agent_id = cur.lastrowid
        conn.commit()
        conn.close()
        os.environ["TREND_MODULE_ENABLED"] = "1"
        os.environ["TREND_AGENT_ID"] = str(self.agent_id)
        os.environ["TREND_UNIVERSE"] = "BTCUSDT"
        for key in ("TREND_MODULE_ENABLED", "TREND_AGENT_ID", "TREND_UNIVERSE",
                    "TREND_MAX_POSITIONS", "TREND_RISK_USD"):
            self.addCleanup(os.environ.pop, key, None)

    def _signals(self):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT side, quantity, entry_price, pnl, client_order_id "
                "FROM signals WHERE agent_id = ? ORDER BY id", (self.agent_id,))
            return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

    def _state(self):
        from platform_settings import get_setting
        raw = get_setting(tm.STATE_KEY)
        return json.loads(raw) if raw else {}


class TestCycleGating(CycleBase):
    def test_disabled_by_default_no_ops(self):
        del os.environ["TREND_MODULE_ENABLED"]
        with patch.object(tm, "_get_bars") as bars_mock:
            summary = tm.run_trend_cycle()
        self.assertFalse(summary["enabled"])
        self.assertEqual(summary["actions"], [])
        bars_mock.assert_not_called()
        self.assertEqual(self._signals(), [])

    def test_refuses_without_agent_id(self):
        del os.environ["TREND_AGENT_ID"]
        with patch.object(tm, "_get_bars") as bars_mock:
            summary = tm.run_trend_cycle()
        self.assertEqual(summary["error"], "TREND_AGENT_ID unset")
        self.assertEqual(summary["entries"], 0)
        bars_mock.assert_not_called()
        self.assertEqual(self._signals(), [])

    def test_non_numeric_agent_id_refuses(self):
        os.environ["TREND_AGENT_ID"] = "not-a-number"
        with patch.object(tm, "_get_bars") as bars_mock:
            summary = tm.run_trend_cycle()
        self.assertEqual(summary["error"], "TREND_AGENT_ID unset")
        bars_mock.assert_not_called()


class TestCycleEntries(CycleBase):
    def test_entry_recorded_on_ledger_with_llm_size(self):
        bars = _bars_up()
        with patch.object(tm, "_get_bars", return_value=bars), \
             patch.object(tm, "wilder_adx", return_value=30.0), \
             patch.object(tm, "_fear_greed_value", return_value=50), \
             patch("llm_client.generate_text",
                   return_value='{"veto": false, "size_mult": 0.5}'):
            summary = tm.run_trend_cycle()
        self.assertEqual(summary["entries"], 1)
        rows = self._signals()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["side"], "buy")
        highs, lows, closes = tm._series(bars)
        atr = tm.wilder_atr(highs, lows, closes)
        self.assertAlmostEqual(rows[0]["quantity"],
                               25.0 / (1.5 * atr) * 0.5, places=6)
        self.assertTrue(rows[0]["client_order_id"].startswith(
            f"trend:{self.agent_id}:BTCUSDT:buy:"))
        state = self._state()
        pos = state["positions"]["BTCUSDT"]
        self.assertEqual(pos["side"], "long")
        self.assertEqual(pos["entry_kind"], "donchian")
        self.assertAlmostEqual(pos["initial_stop"],
                               closes[-1] - 1.5 * atr, places=6)

    def test_llm_veto_blocks_entry(self):
        with patch.object(tm, "_get_bars", return_value=_bars_up()), \
             patch.object(tm, "wilder_adx", return_value=30.0), \
             patch.object(tm, "_fear_greed_value", return_value=50), \
             patch("llm_client.generate_text",
                   return_value='{"veto": true, "size_mult": 1.0}'):
            summary = tm.run_trend_cycle()
        self.assertEqual(summary["vetoes"], 1)
        self.assertEqual(summary["entries"], 0)
        self.assertEqual(self._signals(), [])
        events = [e["event"] for e in summary["actions"]]
        self.assertIn("veto", events)

    def test_llm_failure_defaults_to_full_size_entry(self):
        bars = _bars_up()
        with patch.object(tm, "_get_bars", return_value=bars), \
             patch.object(tm, "wilder_adx", return_value=30.0), \
             patch.object(tm, "_fear_greed_value", return_value=50), \
             patch("llm_client.generate_text", return_value=None):
            summary = tm.run_trend_cycle()
        self.assertEqual(summary["entries"], 1)
        highs, lows, closes = tm._series(bars)
        atr = tm.wilder_atr(highs, lows, closes)
        self.assertAlmostEqual(self._signals()[0]["quantity"],
                               25.0 / (1.5 * atr), places=6)

    def test_max_positions_cap(self):
        os.environ["TREND_UNIVERSE"] = "BTCUSDT,ETHUSDT"
        os.environ["TREND_MAX_POSITIONS"] = "1"
        with patch.object(tm, "_get_bars", return_value=_bars_up()), \
             patch.object(tm, "wilder_adx", return_value=30.0), \
             patch.object(tm, "_fear_greed_value", return_value=50), \
             patch("llm_client.generate_text", return_value=None):
            summary = tm.run_trend_cycle()
        self.assertEqual(summary["entries"], 1)
        self.assertEqual(len(self._state()["positions"]), 1)

    def test_greed_blocks_long_in_cycle(self):
        with patch.object(tm, "_get_bars", return_value=_bars_up()), \
             patch.object(tm, "wilder_adx", return_value=30.0), \
             patch.object(tm, "_fear_greed_value", return_value=85), \
             patch("llm_client.generate_text", return_value=None):
            summary = tm.run_trend_cycle()
        self.assertEqual(summary["entries"], 0)
        events = [e["event"] for e in summary["actions"]]
        self.assertIn("signal_blocked", events)
        self.assertEqual(self._signals(), [])

    def test_contrarian_entry_tagged(self):
        with patch.object(tm, "_get_bars", return_value=_bars_down()), \
             patch.object(tm, "wilder_adx", return_value=50.0), \
             patch.object(tm, "_fear_greed_value", return_value=15), \
             patch("llm_client.generate_text", return_value=None):
            summary = tm.run_trend_cycle()
        self.assertEqual(summary["entries"], 1)
        self.assertEqual(self._signals()[0]["side"], "buy")
        self.assertEqual(
            self._state()["positions"]["BTCUSDT"]["entry_kind"],
            "fg_contrarian")


class TestCycleExits(CycleBase):
    def _enter(self, bars):
        with patch.object(tm, "_get_bars", return_value=bars), \
             patch.object(tm, "wilder_adx", return_value=30.0), \
             patch.object(tm, "_fear_greed_value", return_value=50), \
             patch("llm_client.generate_text", return_value=None):
            summary = tm.run_trend_cycle()
        self.assertEqual(summary["entries"], 1)
        return summary

    def test_stop_cross_exits_and_stats_report_the_loss(self):
        bars = _bars_up()
        self._enter(bars)
        entry_close = bars[-1]["close"]
        crashed = [dict(b) for b in bars]
        crash_close = entry_close - 20.0   # far through the 1.5×ATR stop
        crashed[-1].update({"close": crash_close, "low": crash_close - 1.0})
        with patch.object(tm, "_get_bars", return_value=crashed), \
             patch.object(tm, "wilder_adx", return_value=30.0), \
             patch.object(tm, "_fear_greed_value", return_value=50), \
             patch("llm_client.generate_text", return_value=None):
            summary = tm.run_trend_cycle()
        self.assertEqual(summary["exits"], 1)
        self.assertEqual(self._state()["positions"], {})
        exit_events = [e for e in summary["actions"] if e["event"] == "exit"]
        self.assertEqual(exit_events[0]["reason"], "initial_stop")
        rows = self._signals()
        self.assertEqual(rows[-1]["side"], "sell")
        self.assertLess(rows[-1]["pnl"], 0)
        stats = tm.trend_stats()
        self.assertEqual(stats["entries"], 1)
        self.assertEqual(stats["n_trades"], 1)
        self.assertEqual(stats["win_rate"], 0.0)
        self.assertLess(stats["total_pnl"], 0)

    def test_time_stop_exits(self):
        bars = _bars_up()
        self._enter(bars)
        from platform_settings import get_setting, set_setting
        state = json.loads(get_setting(tm.STATE_KEY))
        stale = (datetime.now(timezone.utc) - timedelta(days=31)).isoformat()
        state["positions"]["BTCUSDT"]["entry_ts"] = stale
        set_setting(tm.STATE_KEY, json.dumps(state), updated_by="test")
        with patch.object(tm, "_get_bars", return_value=bars), \
             patch.object(tm, "wilder_adx", return_value=30.0), \
             patch.object(tm, "_fear_greed_value", return_value=50), \
             patch("llm_client.generate_text", return_value=None):
            summary = tm.run_trend_cycle()
        self.assertEqual(summary["exits"], 1)
        exit_events = [e for e in summary["actions"] if e["event"] == "exit"]
        self.assertEqual(exit_events[0]["reason"], "time_stop")
        self.assertEqual(self._state()["positions"], {})

    def test_trail_update_emitted_each_cycle_without_exit(self):
        bars = _bars_up()
        self._enter(bars)
        with patch.object(tm, "_get_bars", return_value=bars), \
             patch.object(tm, "wilder_adx", return_value=45.0), \
             patch.object(tm, "_fear_greed_value", return_value=50), \
             patch("llm_client.generate_text", return_value=None):
            summary = tm.run_trend_cycle()
        self.assertEqual(summary["exits"], 0)
        events = [e["event"] for e in summary["actions"]]
        self.assertIn("trail_update", events)
        pos = self._state()["positions"]["BTCUSDT"]
        highs, lows, closes = tm._series(bars)
        atr = tm.wilder_atr(highs, lows, closes)
        self.assertAlmostEqual(pos["trail"], closes[-1] - 3.0 * atr, places=6)


if __name__ == "__main__":
    unittest.main()
