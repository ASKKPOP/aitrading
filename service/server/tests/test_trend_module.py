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


def _next_bar(bars, close):
    """`bars` plus one newly COMPLETED bar. An open position is evaluated
    once per completed bar, so "the next cycle" needs one."""
    last = bars[-1]
    return [dict(b) for b in bars] + [{
        "ts": last["ts"] + 1, "open": last["close"],
        "high": max(last["close"], close) + 1.0,
        "low": min(last["close"], close) - 1.0,
        "close": close, "volume": 1e6}]


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
        # The dedicated module agent carries user_id NULL — that shape IS
        # the module's authorization (verification Q2-2: _agent_is_dedicated
        # refuses any agent linked to a user).
        cur.execute(
            "INSERT INTO agents (name, token_hash, cash, user_id, created_at) "
            "VALUES ('trend-agent', 'tth1', 100000, NULL, "
            "'2026-01-01T00:00:00Z')")
        self.agent_id = cur.lastrowid
        conn.commit()
        conn.close()
        # Fills go at the live mark; the suite must not reach a price feed.
        mark = patch.object(tm, "_mark",
                            side_effect=lambda symbol, fallback: fallback)
        mark.start()
        self.addCleanup(mark.stop)
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
        crash_close = entry_close - 20.0   # far through the 1.5×ATR stop
        crashed = _next_bar(bars, crash_close)
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
        bars = _next_bar(bars, bars[-1]["close"] + 0.5)
        with patch.object(tm, "_get_bars", return_value=bars), \
             patch.object(tm, "wilder_adx", return_value=30.0), \
             patch.object(tm, "_fear_greed_value", return_value=50), \
             patch("llm_client.generate_text", return_value=None):
            summary = tm.run_trend_cycle()
        self.assertEqual(summary["exits"], 1)
        exit_events = [e for e in summary["actions"] if e["event"] == "exit"]
        self.assertEqual(exit_events[0]["reason"], "time_stop")
        self.assertEqual(self._state()["positions"], {})

    def test_trail_update_emitted_on_each_new_bar_without_exit(self):
        bars = _bars_up()
        self._enter(bars)
        bars = _next_bar(bars, bars[-1]["close"] + 0.5)
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


class TestCycleShortEntry(CycleBase):
    """Round-2 mutation pin (Q3 #4): a donchian SHORT's initial stop must sit
    ABOVE entry at entry + 1.5xATR — a side-flipped mutant placed it below,
    an already-triggered stop that check_exit fires instantly."""

    def test_short_entry_initial_stop_above_entry(self):
        bars = _bars_down()
        with patch.object(tm, "_get_bars", return_value=bars), \
             patch.object(tm, "wilder_adx", return_value=30.0), \
             patch.object(tm, "_fear_greed_value", return_value=50), \
             patch("llm_client.generate_text", return_value=None):
            summary = tm.run_trend_cycle()
        self.assertEqual(summary["entries"], 1)
        self.assertEqual(self._signals()[0]["side"], "short")
        pos = self._state()["positions"]["BTCUSDT"]
        self.assertEqual(pos["side"], "short")
        highs, lows, closes = tm._series(bars)
        atr = tm.wilder_atr(highs, lows, closes)
        self.assertGreater(pos["initial_stop"], pos["entry_price"])
        self.assertAlmostEqual(pos["initial_stop"],
                               closes[-1] + 1.5 * atr, places=6)


class TestLlmSizeMultWhitelist(CycleBase):
    """Round-2 mutation pin (Q3 #5): size_mult outside {0.5, 1.0} is clamped
    to 1.0 THROUGH the cycle — a mutant dropping the whitelist let a runaway
    LLM 10x the position."""

    def test_out_of_whitelist_mult_enters_at_full_size(self):
        bars = _bars_up()
        with patch.object(tm, "_get_bars", return_value=bars), \
             patch.object(tm, "wilder_adx", return_value=30.0), \
             patch.object(tm, "_fear_greed_value", return_value=50), \
             patch("llm_client.generate_text",
                   return_value='{"veto": false, "size_mult": 10.0}'):
            summary = tm.run_trend_cycle()
        self.assertEqual(summary["entries"], 1)
        highs, lows, closes = tm._series(bars)
        atr = tm.wilder_atr(highs, lows, closes)
        self.assertAlmostEqual(self._signals()[0]["quantity"],
                               25.0 / (1.5 * atr), places=6)  # 1.0-mult qty


class TestExitFailureRetention(CycleBase):
    """Round-2 mutation pin (Q3 #6): a failed exit whose error does NOT
    contain 'position' keeps the position in state (retry next cycle) — a
    mutant dropping state on ANY error orphaned the ledger lot."""

    def test_transient_exit_error_keeps_state(self):
        bars = _bars_up()
        with patch.object(tm, "_get_bars", return_value=bars), \
             patch.object(tm, "wilder_adx", return_value=30.0), \
             patch.object(tm, "_fear_greed_value", return_value=50), \
             patch("llm_client.generate_text", return_value=None):
            self.assertEqual(tm.run_trend_cycle()["entries"], 1)
        # force a time-stop exit, then fail it with a transient error
        from platform_settings import get_setting, set_setting
        state = json.loads(get_setting(tm.STATE_KEY))
        stale = (datetime.now(timezone.utc) - timedelta(days=31)).isoformat()
        state["positions"]["BTCUSDT"]["entry_ts"] = stale
        set_setting(tm.STATE_KEY, json.dumps(state), updated_by="test")
        bars = _next_bar(bars, bars[-1]["close"] + 0.5)
        with patch.object(tm, "_get_bars", return_value=bars), \
             patch.object(tm, "wilder_adx", return_value=30.0), \
             patch.object(tm, "_fear_greed_value", return_value=50), \
             patch("llm_client.generate_text", return_value=None), \
             patch("automation.execute_paper_trade",
                   return_value=(None, "temporary db error")):
            summary = tm.run_trend_cycle()
        self.assertEqual(summary["exits"], 0)
        self.assertIn("BTCUSDT", self._state()["positions"])  # RETAINED
        events = [e["event"] for e in summary["actions"]]
        self.assertIn("exit_failed", events)
        self.assertNotIn("state_desync", events)
        # The retry is the NEXT TICK on the same bar — a failed exit must
        # not wait for tomorrow's close behind the once-per-bar rule.
        with patch.object(tm, "_get_bars", return_value=bars), \
             patch.object(tm, "wilder_adx", return_value=30.0), \
             patch.object(tm, "_fear_greed_value", return_value=50), \
             patch("llm_client.generate_text", return_value=None):
            summary = tm.run_trend_cycle()
        self.assertEqual(summary["exits"], 1)
        self.assertEqual(self._state()["positions"], {})


class TestCompletedBars(unittest.TestCase):
    """The rule decides on a bar's CLOSE; the feed's last row is the bar in
    progress. research/trend_replay (2026-10-05): completed bars 115 trades
    +114R; the same rule read hourly on the forming bar 164 trades +93R,
    and the 63 forming-only entries net -2.2R."""

    NOW = 1_760_000_000_000

    def _bar(self, age_ms, close=1.0):
        return {"ts": self.NOW - age_ms, "open": close, "high": close,
                "low": close, "close": close, "volume": 1.0}

    def test_the_forming_bar_is_dropped(self):
        done = self._bar(2 * tm.DAY_MS)
        just_closed = self._bar(tm.DAY_MS)              # closed this instant
        forming = self._bar(tm.DAY_MS - 1, close=99.0)
        out = tm._completed_bars([done, just_closed, forming], self.NOW)
        self.assertEqual(out, [done, just_closed])

    def test_a_bar_without_a_timestamp_is_kept(self):
        bar = {"close": 5.0}
        self.assertEqual(tm._completed_bars([bar], self.NOW), [bar])

    def test_get_bars_reads_fresh_and_drops_the_forming_bar(self):
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        closed = {"ts": now_ms - 2 * tm.DAY_MS, "open": 1, "high": 1,
                  "low": 1, "close": 1.0, "volume": 1}
        forming = {"ts": now_ms - 3_600_000, "open": 1, "high": 9,
                   "low": 1, "close": 9.0, "volume": 1}
        with patch("crypto_feed.fetch_candles",
                   return_value=[closed, forming]) as fc, \
             patch("price_fetcher.get_daily_candles") as cached:
            out = tm._get_bars("BTCUSDT")
        self.assertEqual(out, [closed])
        cached.assert_not_called()      # the hours-long cache is bypassed
        self.assertEqual(fc.call_args.kwargs["bar"], "1D")
        # one extra row is requested so the window survives the drop
        self.assertEqual(fc.call_args.kwargs["limit"], tm.HISTORY_DAYS + 1)

    def test_a_dead_feed_is_no_bars_not_a_crash(self):
        with patch("crypto_feed.fetch_candles",
                   side_effect=RuntimeError("okx down")):
            self.assertEqual(tm._get_bars("BTCUSDT"), [])


class TestOncePerCompletedBar(CycleBase):
    def _cycle(self, bars, adx=45.0):
        with patch.object(tm, "_get_bars", return_value=bars), \
             patch.object(tm, "wilder_adx", return_value=adx), \
             patch.object(tm, "_fear_greed_value", return_value=50), \
             patch("llm_client.generate_text", return_value=None):
            return tm.run_trend_cycle()

    def test_ticks_inside_the_entry_bar_rule_on_nothing(self):
        bars = _bars_up()
        self.assertEqual(self._cycle(bars, adx=30.0)["entries"], 1)
        pos = self._state()["positions"]["BTCUSDT"]
        self.assertEqual(pos["bar_ts"], bars[-1]["ts"])
        before = dict(pos)
        # same completed bar, an hour later: the position was not open for
        # it, so no trail is drawn off it and no exit is judged on it
        summary = self._cycle(bars)
        self.assertEqual([e["event"] for e in summary["actions"]], [])
        self.assertEqual(self._state()["positions"]["BTCUSDT"], before)

    def test_a_new_bar_is_ruled_on_exactly_once(self):
        bars = _bars_up()
        self._cycle(bars, adx=30.0)
        bars = _next_bar(bars, bars[-1]["close"] + 0.5)
        first = self._cycle(bars)
        self.assertIn("trail_update", [e["event"] for e in first["actions"]])
        self.assertEqual(self._state()["positions"]["BTCUSDT"]["bar_ts"],
                         bars[-1]["ts"])
        again = self._cycle(bars)
        self.assertEqual([e["event"] for e in again["actions"]], [])

    def test_a_position_from_before_this_rule_is_picked_up(self):
        # The two live positions carry no bar_ts.
        bars = _bars_up()
        self._cycle(bars, adx=30.0)
        from platform_settings import get_setting, set_setting
        state = json.loads(get_setting(tm.STATE_KEY))
        del state["positions"]["BTCUSDT"]["bar_ts"]
        set_setting(tm.STATE_KEY, json.dumps(state), updated_by="test")
        summary = self._cycle(bars)
        self.assertIn("trail_update",
                      [e["event"] for e in summary["actions"]])
        self.assertEqual(self._state()["positions"]["BTCUSDT"]["bar_ts"],
                         bars[-1]["ts"])


class TestFillsAtTheMark(CycleBase):
    def test_entry_and_stop_are_anchored_on_the_live_mark(self):
        bars = _bars_up()
        close = bars[-1]["close"]
        with patch.object(tm, "_get_bars", return_value=bars), \
             patch.object(tm, "_mark", return_value=close + 2.0), \
             patch.object(tm, "wilder_adx", return_value=30.0), \
             patch.object(tm, "_fear_greed_value", return_value=50), \
             patch("llm_client.generate_text", return_value=None):
            summary = tm.run_trend_cycle()
        self.assertEqual(summary["entries"], 1)
        pos = self._state()["positions"]["BTCUSDT"]
        self.assertEqual(pos["entry_price"], close + 2.0)
        self.assertAlmostEqual(
            pos["initial_stop"],
            close + 2.0 - tm.STOP_ATR_MULT * pos["entry_atr"])
        self.assertEqual(self._signals()[0]["entry_price"], close + 2.0)

    def test_an_exit_also_fills_at_the_mark(self):
        bars = _bars_up()
        with patch.object(tm, "_get_bars", return_value=bars), \
             patch.object(tm, "wilder_adx", return_value=30.0), \
             patch.object(tm, "_fear_greed_value", return_value=50), \
             patch("llm_client.generate_text", return_value=None):
            tm.run_trend_cycle()
        crash = bars[-1]["close"] - 20.0
        with patch.object(tm, "_get_bars",
                          return_value=_next_bar(bars, crash)), \
             patch.object(tm, "_mark", return_value=crash - 3.0), \
             patch.object(tm, "wilder_adx", return_value=30.0), \
             patch.object(tm, "_fear_greed_value", return_value=50), \
             patch("llm_client.generate_text", return_value=None):
            summary = tm.run_trend_cycle()
        self.assertEqual(summary["exits"], 1)
        exit_event = [e for e in summary["actions"]
                      if e["event"] == "exit"][0]
        self.assertEqual(exit_event["price"], crash - 3.0)


class TestModuleStopOnTheLedger(CycleBase):
    """research/trend_replay, stop variants (2026-10-05), same 2020-2026
    entries: daily-close exits +114.2R; the module's own 1.5×ATR stop
    enforced intraday +122.9R (max drawdown 14.6R vs 20.2R); the 5% stop the
    orphan sweep had been attaching +71.4R. So the row carries the MODULE's
    stop, the SL/TP watcher enforces it, and nothing else."""

    def _row(self):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT stop_loss, take_profit, exit_policy, quantity "
                "FROM positions WHERE agent_id = ? AND symbol = 'BTCUSDT'",
                (self.agent_id,))
            row = cur.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def _cycle(self, bars, adx=30.0):
        with patch.object(tm, "_get_bars", return_value=bars), \
             patch.object(tm, "wilder_adx", return_value=adx), \
             patch.object(tm, "_fear_greed_value", return_value=50), \
             patch("llm_client.generate_text", return_value=None):
            return tm.run_trend_cycle()

    def test_entry_puts_the_modules_own_stop_on_the_row(self):
        self._cycle(_bars_up())
        pos = self._state()["positions"]["BTCUSDT"]
        row = self._row()
        self.assertAlmostEqual(row["stop_loss"], pos["initial_stop"])
        self.assertIsNone(row["take_profit"])
        # exit_policy stays NULL: 'v1' would switch on the watcher's own
        # loser time-stop and trailing — two more foreign exits.
        self.assertIsNone(row["exit_policy"])

    def test_a_foreign_stop_is_replaced_by_the_modules(self):
        # The two positions open on 2026-10-05 carry the sweep's 5% stop.
        bars = _bars_up()
        self._cycle(bars)
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE positions SET stop_loss = 1.0 WHERE agent_id = ?",
                    (self.agent_id,))
        conn.commit()
        conn.close()
        self._cycle(bars, adx=45.0)       # same bar: nothing else to rule on
        self.assertAlmostEqual(
            self._row()["stop_loss"],
            self._state()["positions"]["BTCUSDT"]["initial_stop"])

    def test_a_position_the_watcher_closed_frees_its_slot(self):
        """The watcher sells the ledger lot; module state knew nothing, kept
        the slot, and only found out when its own exit was refused — 747
        phantom position-days in the replay of that behaviour."""
        bars = _bars_up()
        self._cycle(bars)
        from automation import execute_paper_trade
        pos = self._state()["positions"]["BTCUSDT"]
        sid, err = execute_paper_trade(
            self.agent_id, "BTCUSDT", "crypto", "sell", float(pos["qty"]),
            pos["initial_stop"], content="risk: stop_loss triggered")
        self.assertIsNotNone(sid, err)
        summary = self._cycle(bars, adx=45.0)
        self.assertEqual(self._state()["positions"], {})
        events = [e["event"] for e in summary["actions"]]
        self.assertIn("closed_outside", events)
        self.assertEqual(summary["open_positions"], 0)

    def test_the_sync_never_touches_a_row_a_run_owns(self):
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO positions (agent_id, symbol, market, side, quantity,"
            " entry_price, opened_at, run_id, stop_loss) VALUES "
            "(?, 'ETHUSDT', 'crypto', 'long', 1.0, 10.0,"
            " '2026-01-01T00:00:00Z', 7, 5.0)", (self.agent_id,))
        conn.commit()
        conn.close()
        tm._sync_stop(self.agent_id, "ETHUSDT", 9.0)
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT stop_loss FROM positions WHERE symbol = 'ETHUSDT'")
        self.assertEqual(cur.fetchone()["stop_loss"], 5.0)
        conn.close()

    def test_a_stopped_out_signal_is_not_taken_again_on_the_same_bar(self):
        """The slot is free again, the bar that gave the signal is still the
        newest one, and the signal still evaluates true — so every tick
        re-entered (review 2026-10-05; five times in the 6.7-year replay,
        four of them losers). The replay takes a signal bar once."""
        bars = _bars_up()
        self._cycle(bars)
        from automation import execute_paper_trade
        pos = self._state()["positions"]["BTCUSDT"]
        sid, err = execute_paper_trade(
            self.agent_id, "BTCUSDT", "crypto", "sell", float(pos["qty"]),
            pos["initial_stop"], content="risk: stop_loss triggered")
        self.assertIsNotNone(sid, err)
        with patch.object(tm, "_llm_veto") as veto:
            summary = self._cycle(bars)           # adx 30: the signal holds
        self.assertEqual(summary["entries"], 0)
        self.assertEqual(self._state()["positions"], {})
        veto.assert_not_called()                  # nor an LLM call an hour
        # A NEW bar that still breaks out is a new signal and is evaluated.
        # (It cannot FILL inside this test: the order id is per UTC day, and
        # a real next bar is a day later.)
        fresh = _next_bar(bars, bars[-1]["close"] + 30.0)
        self.assertEqual(self._cycle(fresh)["signals"], 1)

    def test_stats_count_the_trades_the_watcher_closed(self):
        """`trend_stats` read only fills carrying the module's own order id.
        The watcher's close has none, so every stop-out — 57 of 118 trades
        and -58R in the replay of this stop — was missing from the record
        the falsifier is read off: a loss-censored payoff."""
        bars = _bars_up()
        self._cycle(bars)
        from automation import execute_paper_trade
        pos = self._state()["positions"]["BTCUSDT"]
        sid, err = execute_paper_trade(
            self.agent_id, "BTCUSDT", "crypto", "sell", float(pos["qty"]),
            pos["initial_stop"],
            content="risk: stop_loss triggered (SL/TP watcher)")
        self.assertIsNotNone(sid, err)
        stats = tm.trend_stats()
        self.assertEqual(stats["entries"], 1)
        self.assertEqual(stats["n_trades"], 1)
        self.assertLess(stats["total_pnl"], 0)

    def test_a_failed_ledger_read_is_None_not_an_empty_book(self):
        self.assertEqual(tm._ledger_read(self.agent_id), {})
        with patch("database.get_db_connection",
                   side_effect=RuntimeError("db down")):
            self.assertIsNone(tm._ledger_read(self.agent_id))

        class _Boom:
            def cursor(self):
                raise RuntimeError("query failed")

            def close(self):
                pass

        with patch("database.get_db_connection", return_value=_Boom()):
            self.assertIsNone(tm._ledger_read(self.agent_id))
            self.assertEqual(tm._ledger_positions(self.agent_id), {})

    def test_an_unreadable_ledger_drops_nothing(self):
        bars = _bars_up()
        self._cycle(bars)
        with patch.object(tm, "_ledger_read", return_value=None):
            summary = self._cycle(bars, adx=45.0)
        self.assertIn("BTCUSDT", self._state()["positions"])
        self.assertNotIn("closed_outside",
                         [e["event"] for e in summary["actions"]])


class TestStateFitsItsColumn(CycleBase):
    """platform_settings.setting_value is TEXT on MySQL — 65,535 bytes, strict
    mode. The event log (EVENT_CAP 400 rows of ~180 bytes) cannot fit, and on
    prod it stopped fitting at 366 rows: the state was last saved
    2026-09-27T06:25Z and every hourly save after it failed, so trails,
    exits and entries ran from a frozen snapshot for eight days."""

    def _big_state(self, n_events):
        row = {"ts": "2026-09-27T06:25:24+00:00", "event": "trail_update",
               "symbol": "BNBUSDT", "trail": 733.5111561035872,
               "best_close": 805.2, "close": 786.72,
               "atr": 24.998437745867932}
        return {"positions": {"BNBUSDT": {"side": "long", "qty": 0.6667,
                                          "initial_stop": 744.6}},
                "entered_bar": {"BNBUSDT": 1},
                "events": [dict(row, n=i) for i in range(n_events)]}

    def test_an_oversized_state_is_trimmed_to_fit_and_still_saved(self):
        state = self._big_state(600)
        self.assertGreater(len(json.dumps(state).encode()), 65_535)
        tm._save_state(state)
        from platform_settings import get_setting
        raw = get_setting(tm.STATE_KEY)
        self.assertLessEqual(len(raw.encode()), tm.STATE_MAX_BYTES)
        self.assertLess(tm.STATE_MAX_BYTES, 65_535)
        saved = json.loads(raw)
        # what trading depends on survives whole; only old telemetry goes
        self.assertEqual(saved["positions"], state["positions"])
        self.assertEqual(saved["entered_bar"], {"BNBUSDT": 1})
        self.assertTrue(saved["events"])
        self.assertEqual(saved["events"][-1]["n"], 599)   # newest kept

    def test_a_state_that_fits_is_saved_untouched(self):
        state = self._big_state(20)
        tm._save_state(state)
        self.assertEqual(self._state(), state)

    def test_the_prod_shape_saves_after_one_more_cycle(self):
        # 366 rows on file, then a cycle that emits more.
        from platform_settings import set_setting
        on_file = self._big_state(366)
        on_file["positions"] = {}       # the telemetry is what overflowed
        set_setting(tm.STATE_KEY, json.dumps(on_file), updated_by="test")
        with patch.object(tm, "_get_bars", return_value=_bars_up()), \
             patch.object(tm, "_ledger_read", return_value=None), \
             patch.object(tm, "_sync_stop"), \
             patch.object(tm, "wilder_adx", return_value=45.0), \
             patch.object(tm, "_fear_greed_value", return_value=50), \
             patch("llm_client.generate_text", return_value=None), \
             patch("platform_settings.set_setting") as write:
            tm.run_trend_cycle()
        raw = write.call_args.args[1]
        self.assertLessEqual(len(raw.encode()), tm.STATE_MAX_BYTES)


class TestMark(unittest.TestCase):
    def test_live_mark_wins_and_every_miss_falls_back(self):
        with patch("price_fetcher.get_price_from_market",
                   return_value=12.0) as feed:
            self.assertEqual(tm._mark("BTCUSDT", 7.5), 12.0)
        self.assertEqual(feed.call_args.args[0], "BTCUSDT")
        self.assertEqual(feed.call_args.args[2], "crypto")
        for miss in (None, 0, -1.0):
            with patch("price_fetcher.get_price_from_market",
                       return_value=miss):
                self.assertEqual(tm._mark("BTCUSDT", 7.5), 7.5, miss)
        with patch("price_fetcher.get_price_from_market",
                   side_effect=RuntimeError("feed down")):
            self.assertEqual(tm._mark("BTCUSDT", 7.5), 7.5)


class TestDedicatedAgentRefusal(CycleBase):
    """Round-2 fix D5: a TREND_AGENT_ID pointing at an agent linked to a
    USER (user_id not NULL) is refused — the module must never trade a real
    user's sim book."""

    def test_user_linked_agent_refused(self):
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO agents (name, token_hash, cash, user_id, created_at) "
            "VALUES ('user-agent', 'tth2', 100000, 77, "
            "'2026-01-01T00:00:00Z')")
        user_agent_id = cur.lastrowid
        conn.commit()
        conn.close()
        os.environ["TREND_AGENT_ID"] = str(user_agent_id)
        with patch.object(tm, "_get_bars") as bars_mock:
            summary = tm.run_trend_cycle()
        self.assertEqual(summary["error"],
                         "TREND_AGENT_ID not a dedicated agent")
        self.assertEqual(summary["entries"], 0)
        bars_mock.assert_not_called()
        self.assertEqual(self._signals(), [])


class TestOrphanReconcile(CycleBase):
    """Round-2 fix D10: a ledger lot on the module agent that state forgot
    (crash between ledger commit and _save_state) is adopted at the top of
    the next cycle — with a rebuilt stop, and then managed like any other."""

    def test_ledger_orphan_adopted_with_stop_and_managed(self):
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO positions (agent_id, symbol, market, side, quantity, "
            "entry_price, opened_at) VALUES (?, 'BTCUSDT', 'crypto', 'long', "
            "2.0, 100.0, '2026-01-01T00:00:00Z')", (self.agent_id,))
        conn.commit()
        conn.close()
        self.assertEqual(self._state(), {})  # state has never seen it
        bars = _bars_up()
        with patch.object(tm, "_get_bars", return_value=bars), \
             patch.object(tm, "wilder_adx", return_value=30.0), \
             patch.object(tm, "_fear_greed_value", return_value=50), \
             patch("llm_client.generate_text", return_value=None):
            summary = tm.run_trend_cycle()
        events = [e["event"] for e in summary["actions"]]
        self.assertIn("orphan_adopted", events)
        pos = self._state()["positions"]["BTCUSDT"]
        self.assertEqual(pos["side"], "long")
        self.assertEqual(pos["entry_kind"], "adopted")
        self.assertAlmostEqual(pos["qty"], 2.0)
        highs, lows, closes = tm._series(bars)
        atr = tm.wilder_atr(highs, lows, closes)
        self.assertAlmostEqual(pos["initial_stop"], 100.0 - 1.5 * atr,
                               places=6)  # stop rebuilt from current bars
        self.assertIn("trail_update", events)  # managed in the same cycle
        self.assertEqual(summary["entries"], 0)  # no double-entry on top


if __name__ == "__main__":
    unittest.main()
