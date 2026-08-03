"""Risk engine (Phase 1) — Kelly sizing, limits, circuit breaker, SL/TP watcher.

Covers the phase acceptance criteria:
  - SL/TP positions auto-close when the polled price crosses, journaled as signals
  - daily max-loss breach makes automation reject orders (skip_reason)
  - HALT stops auto-trading until cleared
  - Kelly lowers order size based on journal win-rate / payoff ratio
"""
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
from routes import create_app


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


# Anchor test timestamps at 01:00 UTC so a few hours of offsets never cross a
# UTC day boundary (realized_today is bucketed by UTC date).
TODAY = datetime.now(timezone.utc).replace(hour=1, minute=0, second=0, microsecond=0)
YESTERDAY = TODAY - timedelta(days=1)


class RiskEngineTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        os.environ["RISK_ENGINE_ENABLED"] = "true"
        self.client = TestClient(create_app())
        resp = self.client.post(
            "/api/claw/agents/selfRegister",
            json={"name": "risk-agent", "password": "pw123", "initial_balance": 100000.0},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        self.agent_id = body["agent_id"]
        self.token = body["token"]

    def tearDown(self) -> None:
        os.environ["RISK_ENGINE_ENABLED"] = "false"
        self.tmp.cleanup()

    # ── helpers ──────────────────────────────────────────────────────────

    _next_signal_id = 900000

    def _insert_signal(self, side: str, price: float, qty: float,
                       executed_at: str, symbol: str = "BTC", market: str = "crypto",
                       run_id: "int | None" = None):
        RiskEngineTestCase._next_signal_id += 1
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO signals
               (signal_id, agent_id, message_type, market, signal_type, symbol,
                side, entry_price, quantity, content, timestamp, created_at,
                executed_at, run_id)
               VALUES (?, ?, 'operation', ?, 'automation', ?, ?, ?, ?, 'test', 0, ?, ?, ?)""",
            (RiskEngineTestCase._next_signal_id, self.agent_id, market, symbol,
             side, price, qty, executed_at, executed_at, run_id),
        )
        conn.commit()
        conn.close()

    def _round_trip(self, buy: float, sell: float, when: datetime, qty: float = 1.0,
                    run_id: "int | None" = None):
        self._insert_signal("buy", buy, qty, _iso(when), run_id=run_id)
        self._insert_signal("sell", sell, qty, _iso(when + timedelta(minutes=1)),
                            run_id=run_id)

    def _insert_position(self, symbol="BTC", market="crypto", qty=1.0, entry=100.0,
                         current=None, stop_loss=None, take_profit=None):
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO positions
               (agent_id, symbol, market, side, quantity, entry_price, current_price,
                opened_at, stop_loss, take_profit)
               VALUES (?, ?, ?, 'long', ?, ?, ?, ?, ?, ?)""",
            (self.agent_id, symbol, market, qty, entry, current,
             _iso(datetime.now(timezone.utc)), stop_loss, take_profit),
        )
        conn.commit()
        conn.close()

    def _position(self, symbol="BTC", market="crypto"):
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM positions WHERE agent_id = ? AND market = ? AND symbol = ?",
            (self.agent_id, market, symbol),
        )
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def _cash(self) -> float:
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT cash FROM agents WHERE id = ?", (self.agent_id,))
        cash = cursor.fetchone()["cash"]
        conn.close()
        return float(cash)


# ── Kelly math ────────────────────────────────────────────────────────────

class KellyFractionTests(unittest.TestCase):
    def test_kelly_fraction_positive_edge(self):
        from risk_engine import kelly_fraction
        # W=0.6, R=2 → f* = 0.6 − 0.4/2 = 0.4
        self.assertAlmostEqual(kelly_fraction(0.6, 2.0), 0.4)

    def test_kelly_fraction_negative_edge(self):
        from risk_engine import kelly_fraction
        # W=0.3, R=1 → f* = 0.3 − 0.7 = −0.4
        self.assertAlmostEqual(kelly_fraction(0.3, 1.0), -0.4)

    def test_kelly_fraction_unavailable_payoff(self):
        from risk_engine import kelly_fraction
        self.assertIsNone(kelly_fraction(0.6, None))
        self.assertIsNone(kelly_fraction(0.6, 0.0))


# ── journal replay ────────────────────────────────────────────────────────

class TradeStatsTests(RiskEngineTestCase):
    def test_commodity_pnl_is_not_scaled_by_contract_point_value(self):
        """The ledger is USD-notional end to end: automation sizes
        `quantity = size_usd / entry` and run_engine marks that quantity
        straight against price, so a CL row is dollars of exposure, not
        contracts of 1,000 barrels. Applying a point value here scaled the
        same trade by 1000x against the book that produced it — prod run 76
        booked -$159.82 and this counted -$159,816, tripping the account
        daily-loss breaker 49 times in a week."""
        from risk_engine import trade_stats
        # CL carries contract_multiplier 1000; a $10 loss must stay $10.
        self._insert_signal("buy", 100.0, 1.0, _iso(TODAY),
                            symbol="CL", market="futures")
        self._insert_signal("sell", 90.0, 1.0, _iso(TODAY + timedelta(minutes=1)),
                            symbol="CL", market="futures")
        stats = trade_stats(self.agent_id)
        self.assertAlmostEqual(stats["realized_today"], -10.0)

    def test_replay_win_rate_payoff_and_daily_pnl(self):
        from risk_engine import trade_stats
        # Two wins of +20 yesterday, one loss of −10 today.
        self._round_trip(100.0, 120.0, YESTERDAY)
        self._round_trip(100.0, 120.0, YESTERDAY + timedelta(hours=1))
        self._round_trip(100.0, 90.0, TODAY)
        stats = trade_stats(self.agent_id)
        self.assertEqual(stats["n_trades"], 3)
        self.assertAlmostEqual(stats["win_rate"], 2 / 3)
        self.assertAlmostEqual(stats["payoff_ratio"], 2.0)  # avg win 20 / avg loss 10
        self.assertAlmostEqual(stats["realized_today"], -10.0)

    def test_replay_averages_cost_basis(self):
        from risk_engine import trade_stats
        # Buy 1 @100 and 1 @200 (avg 150), sell 2 @180 → pnl +60, one winning trade.
        self._insert_signal("buy", 100.0, 1.0, _iso(TODAY))
        self._insert_signal("buy", 200.0, 1.0, _iso(TODAY + timedelta(minutes=1)))
        self._insert_signal("sell", 180.0, 2.0, _iso(TODAY + timedelta(minutes=2)))
        stats = trade_stats(self.agent_id)
        self.assertEqual(stats["n_trades"], 1)
        self.assertAlmostEqual(stats["realized_today"], 60.0)

    def test_agent_wide_replay_keeps_concurrent_runs_on_separate_books(self):
        """Two live runs on the SAME symbol must not cross-match. Run 1 is a
        clean +10 round trip; run 2 is still open with a single buy far above
        the market. Merging the books would average run 2's open buy into run
        1's cost basis and invent a large loss (prod 2026-07-24: a fabricated
        "realized today $-154,418" hard-blocked the agent's daily-loss gate)."""
        from risk_engine import trade_stats
        # Run 2's open buy lands FIRST, so a merged book would average it into
        # run 1's cost basis before run 1's exit replays.
        self._insert_signal("buy", 9000.0, 1.0,                   # run 2: open, no exit
                            _iso(TODAY), run_id=2)
        self._insert_signal("buy", 100.0, 1.0,
                            _iso(TODAY + timedelta(minutes=1)), run_id=1)
        self._insert_signal("sell", 110.0, 1.0,                   # run 1 exits: +10
                            _iso(TODAY + timedelta(minutes=2)), run_id=1)
        stats = trade_stats(self.agent_id)
        self.assertEqual(stats["n_trades"], 1, "run 2's open buy must not close run 1")
        # Merged books would price the exit against avg(9000, 100) = 4550 and
        # book a −$4,440 phantom loss instead of run 1's real +$10.
        self.assertAlmostEqual(stats["realized_today"], 10.0)

    def test_agent_wide_replay_sums_realized_across_runs(self):
        """Per-run books, but realized_today still aggregates every run — the
        daily-loss breaker is an account-level rail and must stay agent-wide."""
        from risk_engine import trade_stats
        self._round_trip(100.0, 110.0, TODAY, run_id=1)                       # +10
        self._round_trip(100.0, 70.0, TODAY + timedelta(minutes=5), run_id=2)  # −30
        stats = trade_stats(self.agent_id)
        self.assertEqual(stats["n_trades"], 2)
        self.assertAlmostEqual(stats["realized_today"], -20.0)


# ── the gate ──────────────────────────────────────────────────────────────

class GateTests(RiskEngineTestCase):
    def test_gate_passes_through_when_disabled(self):
        from risk_engine import evaluate_order, trip_breaker
        os.environ["RISK_ENGINE_ENABLED"] = "false"
        trip_breaker("test halt", agent_id=self.agent_id)
        decision = evaluate_order(self.agent_id, "BTC", "crypto", "buy", 5.0, 100.0)
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.quantity, 5.0)

    def test_gate_rejects_when_agent_halted_until_cleared(self):
        from risk_engine import clear_breaker, evaluate_order, trip_breaker
        trip_breaker("manual test halt", agent_id=self.agent_id)
        decision = evaluate_order(self.agent_id, "BTC", "crypto", "buy", 1.0, 100.0)
        self.assertFalse(decision.allowed)
        self.assertIn("breaker", decision.reason)
        # HALT persists until explicitly cleared
        decision2 = evaluate_order(self.agent_id, "BTC", "crypto", "sell", 1.0, 100.0)
        self.assertFalse(decision2.allowed)
        clear_breaker(agent_id=self.agent_id)
        decision3 = evaluate_order(self.agent_id, "BTC", "crypto", "buy", 1.0, 100.0)
        self.assertTrue(decision3.allowed)

    def test_gate_rejects_when_globally_halted(self):
        from risk_engine import clear_breaker, evaluate_order, trip_breaker
        trip_breaker("3σ shock", agent_id=None)
        decision = evaluate_order(self.agent_id, "BTC", "crypto", "buy", 1.0, 100.0)
        self.assertFalse(decision.allowed)
        self.assertIn("global", decision.reason)
        clear_breaker(agent_id=None)

    def test_gate_rejects_after_daily_loss_limit(self):
        from risk_engine import evaluate_order
        # Realize a −1500 loss today; default limit is 1000.
        self._round_trip(2000.0, 500.0, TODAY)
        decision = evaluate_order(self.agent_id, "BTC", "crypto", "buy", 1.0, 100.0)
        self.assertFalse(decision.allowed)
        self.assertIn("daily loss", decision.reason)

    def test_gate_rejects_over_symbol_exposure(self):
        from risk_engine import evaluate_order
        # Default cap 10k; hold 9k of BTC and try to buy 2k more.
        self._insert_position(qty=90.0, entry=100.0, current=100.0)
        decision = evaluate_order(self.agent_id, "BTC", "crypto", "buy", 20.0, 100.0)
        self.assertFalse(decision.allowed)
        self.assertIn("exposure", decision.reason)

    def test_gate_kelly_lowers_size(self):
        from risk_engine import evaluate_order, put_risk_limits
        # Lift the exposure cap so this test exercises Kelly, not the exposure check.
        put_risk_limits(self.agent_id, {"max_symbol_exposure_usd": 1_000_000})
        # 12 closed trades: 8 wins +20, 4 losses −10 → W=2/3, R=2, f*=1/2, ½f*=1/4.
        for i in range(8):
            self._round_trip(100.0, 120.0, YESTERDAY + timedelta(minutes=10 * i))
        for i in range(4):
            self._round_trip(100.0, 90.0, YESTERDAY + timedelta(minutes=10 * (8 + i)))
        # Equity = 100000 cash (signals inserted directly — no cash/position moved).
        # Request $50k at $100/unit.
        decision = evaluate_order(self.agent_id, "BTC", "crypto", "buy", 500.0, 100.0)
        self.assertTrue(decision.allowed)
        self.assertLess(decision.quantity, 500.0)
        # cap ≈ 0.25 × 100000 = 25000 → 250 units at $100
        self.assertAlmostEqual(decision.quantity, 250.0, delta=5.0)

    def test_gate_kelly_rejects_no_edge(self):
        from risk_engine import evaluate_order
        # 12 closed trades: 3 wins +10, 9 losses −10 → W=0.25, R=1, f*=−0.5.
        for i in range(3):
            self._round_trip(100.0, 110.0, YESTERDAY + timedelta(minutes=10 * i))
        for i in range(9):
            self._round_trip(100.0, 90.0, YESTERDAY + timedelta(minutes=10 * (3 + i)))
        decision = evaluate_order(self.agent_id, "BTC", "crypto", "buy", 10.0, 100.0)
        self.assertFalse(decision.allowed)
        self.assertIn("kelly", decision.reason)

    def test_gate_kelly_skipped_below_min_trades(self):
        from risk_engine import evaluate_order
        # Only 3 closed trades — not enough history, no Kelly adjustment.
        for i in range(3):
            self._round_trip(100.0, 90.0, YESTERDAY + timedelta(minutes=10 * i))
        decision = evaluate_order(self.agent_id, "BTC", "crypto", "buy", 5.0, 100.0)
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.quantity, 5.0)

    def test_gate_attaches_default_sl_tp_on_buy(self):
        from risk_engine import evaluate_order
        decision = evaluate_order(self.agent_id, "BTC", "crypto", "buy", 1.0, 100.0)
        self.assertTrue(decision.allowed)
        self.assertAlmostEqual(decision.stop_loss, 95.0)    # default 5%
        self.assertAlmostEqual(decision.take_profit, 110.0)  # default 10%

    def test_kelly_scopes_to_run_breaking_the_death_spiral(self):
        """A losing AGENT-wide journal must not lock a FRESH run out of trading.
        Kelly's edge is estimated per-run; a run with no history of its own is
        below KELLY_MIN_TRADES so Kelly is skipped and the order proceeds.
        Passing run_id=None keeps the agent-wide behaviour (no regression)."""
        from risk_engine import evaluate_order
        # Agent-wide history (run_id NULL) is a net loser: 3 wins, 9 losses.
        for i in range(3):
            self._round_trip(100.0, 110.0, YESTERDAY + timedelta(minutes=10 * i))
        for i in range(9):
            self._round_trip(100.0, 90.0, YESTERDAY + timedelta(minutes=10 * (3 + i)))
        # Agent-wide (run_id=None): still blocked — behaviour preserved.
        blocked = evaluate_order(self.agent_id, "BTC", "crypto", "buy", 5.0, 100.0)
        self.assertFalse(blocked.allowed)
        self.assertIn("kelly", blocked.reason)
        # Fresh run (its own journal empty): NOT gated by the agent's history.
        fresh = evaluate_order(self.agent_id, "BTC", "crypto", "buy", 5.0, 100.0,
                               run_id=4242)
        self.assertTrue(fresh.allowed)
        self.assertEqual(fresh.quantity, 5.0)

    def test_per_run_kelly_still_engages_on_the_runs_own_losses(self):
        """Scoping doesn't disable Kelly: once a run has ≥ KELLY_MIN_TRADES of
        its OWN closed trades with a losing edge, its own opens are rejected."""
        from risk_engine import evaluate_order
        rid = 7777
        for i in range(3):
            self._round_trip(100.0, 110.0, YESTERDAY + timedelta(minutes=10 * i),
                             run_id=rid)
        for i in range(9):
            self._round_trip(100.0, 90.0, YESTERDAY + timedelta(minutes=10 * (3 + i)),
                             run_id=rid)
        decision = evaluate_order(self.agent_id, "BTC", "crypto", "buy", 5.0, 100.0,
                                  run_id=rid)
        self.assertFalse(decision.allowed)
        self.assertIn("kelly", decision.reason)


# ── SL/TP watcher ─────────────────────────────────────────────────────────

class WatcherTests(RiskEngineTestCase):
    def test_watcher_closes_position_at_stop_loss(self):
        from risk_engine import run_sltp_watcher_tick
        cash_before = self._cash()
        self._insert_position(qty=2.0, entry=100.0, current=94.0,
                              stop_loss=95.0, take_profit=120.0)
        result = run_sltp_watcher_tick()
        self.assertEqual(result["closed"], 1)
        self.assertIsNone(self._position())  # position fully closed
        self.assertGreater(self._cash(), cash_before)  # sale proceeds credited
        # Journaled: a sell signal with the trigger in its content
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """SELECT side, content FROM signals
               WHERE agent_id = ? AND signal_type = 'automation'
               ORDER BY id DESC LIMIT 1""",
            (self.agent_id,),
        )
        row = cursor.fetchone()
        conn.close()
        self.assertEqual(row["side"], "sell")
        self.assertIn("stop_loss", row["content"])

    def test_watcher_closes_position_at_take_profit(self):
        from risk_engine import run_sltp_watcher_tick
        self._insert_position(qty=1.0, entry=100.0, current=121.0,
                              stop_loss=95.0, take_profit=120.0)
        result = run_sltp_watcher_tick()
        self.assertEqual(result["closed"], 1)
        self.assertIsNone(self._position())

    def test_watcher_leaves_position_inside_band(self):
        from risk_engine import run_sltp_watcher_tick
        self._insert_position(qty=1.0, entry=100.0, current=105.0,
                              stop_loss=95.0, take_profit=120.0)
        result = run_sltp_watcher_tick()
        self.assertEqual(result["closed"], 0)
        self.assertIsNotNone(self._position())

    def test_watcher_noop_when_disabled(self):
        from risk_engine import run_sltp_watcher_tick
        os.environ["RISK_ENGINE_ENABLED"] = "false"
        self._insert_position(qty=1.0, entry=100.0, current=50.0,
                              stop_loss=95.0, take_profit=120.0)
        result = run_sltp_watcher_tick()
        self.assertEqual(result["closed"], 0)
        self.assertIsNotNone(self._position())

    def test_watcher_runs_even_when_halted(self):
        """Protective exits must bypass the breaker — HALT never traps a position."""
        from risk_engine import run_sltp_watcher_tick, trip_breaker
        trip_breaker("test halt", agent_id=self.agent_id)
        self._insert_position(qty=1.0, entry=100.0, current=90.0,
                              stop_loss=95.0, take_profit=None)
        result = run_sltp_watcher_tick()
        self.assertEqual(result["closed"], 1)
        self.assertIsNone(self._position())


# ── automation integration ────────────────────────────────────────────────

class AutomationGateIntegrationTests(RiskEngineTestCase):
    def _make_config(self) -> int:
        resp = self.client.post(
            "/api/automation/configs",
            json={"symbol": "BTC", "market": "crypto", "auto_execute": True,
                  "min_confidence": 0.5, "size_usd": 1000},
            headers={"Authorization": f"Bearer {self.token}"},
        )
        assert resp.status_code == 200, resp.text
        return resp.json()["id"]

    def _run_rule(self, config_id: int):
        from automation import run_rule
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM automation_configs WHERE id = ?", (config_id,))
        config = dict(cursor.fetchone())
        conn.close()
        fake = {"decision": {"action": "buy", "confidence": 0.9, "entry": 100.0,
                             "report": "test"}}
        with patch("analysis_agents.run_analysis", return_value=fake), \
             patch("routes_shared.is_market_open", return_value=True):
            return run_rule(config)

    def test_run_rule_executes_and_registers_sl_tp(self):
        config_id = self._make_config()
        result = self._run_rule(config_id)
        self.assertTrue(result["executed"], result)
        pos = self._position()
        self.assertIsNotNone(pos)
        self.assertAlmostEqual(pos["stop_loss"], 95.0)
        self.assertAlmostEqual(pos["take_profit"], 110.0)

    def test_run_rule_halt_records_skip_reason(self):
        from risk_engine import trip_breaker
        trip_breaker("test halt", agent_id=self.agent_id)
        config_id = self._make_config()
        result = self._run_rule(config_id)
        self.assertFalse(result["executed"])
        self.assertIn("breaker", result["skip_reason"])
        # journaled in automation_runs
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT skip_reason FROM automation_runs WHERE config_id = ? ORDER BY id DESC",
            (config_id,),
        )
        row = cursor.fetchone()
        conn.close()
        self.assertIn("breaker", row["skip_reason"])

    def test_run_rule_daily_loss_records_skip_reason(self):
        self._round_trip(2000.0, 500.0, TODAY)  # −1500 realized today > 1000 limit
        config_id = self._make_config()
        result = self._run_rule(config_id)
        self.assertFalse(result["executed"])
        self.assertIn("daily loss", result["skip_reason"])


if __name__ == "__main__":
    unittest.main()


class PortfolioCapTests(RiskEngineTestCase):
    """Plan 06 A1 — aggregate portfolio exposure % and concurrent-position caps."""

    def _gate(self, symbol="NEW", qty=1.0, price=100.0):
        from risk_engine import evaluate_order
        return evaluate_order(self.agent_id, symbol, "crypto", "buy", qty, price)

    def test_portfolio_exposure_cap_rejects(self):
        # equity = 100k cash + positions. Deploy ~59k, cap 60% → a 5k order breaches.
        self._insert_position(symbol="BTC", qty=1.0, entry=59000.0, current=59000.0)
        self.client.put("/api/risk/limits", headers={"Authorization": f"Bearer {self.token}"},
                        json={"max_portfolio_exposure_pct": 60, "max_concurrent_positions": 0,
                              "max_symbol_exposure_usd": 0, "use_kelly": False})
        gate = self._gate(symbol="ETH", qty=100.0, price=400.0)  # $40k order
        self.assertFalse(gate.allowed)
        self.assertIn("portfolio exposure limit", gate.reason)

    def test_portfolio_exposure_cap_allows_within(self):
        self._insert_position(symbol="BTC", qty=1.0, entry=10000.0, current=10000.0)
        self.client.put("/api/risk/limits", headers={"Authorization": f"Bearer {self.token}"},
                        json={"max_portfolio_exposure_pct": 60, "max_concurrent_positions": 0,
                              "max_symbol_exposure_usd": 0, "use_kelly": False})
        gate = self._gate(symbol="ETH", qty=10.0, price=400.0)  # $4k on ~110k equity
        self.assertTrue(gate.allowed)

    def test_concurrent_positions_cap_rejects_new_symbol(self):
        for i in range(3):
            self._insert_position(symbol=f"C{i}", qty=1.0, entry=100.0, current=100.0)
        self.client.put("/api/risk/limits", headers={"Authorization": f"Bearer {self.token}"},
                        json={"max_concurrent_positions": 3, "max_portfolio_exposure_pct": 0,
                              "max_symbol_exposure_usd": 0, "use_kelly": False})
        gate = self._gate(symbol="C99")
        self.assertFalse(gate.allowed)
        self.assertIn("max concurrent positions", gate.reason)

    def test_concurrent_cap_allows_addon_to_held_symbol(self):
        for i in range(3):
            self._insert_position(symbol=f"C{i}", qty=1.0, entry=100.0, current=100.0)
        self.client.put("/api/risk/limits", headers={"Authorization": f"Bearer {self.token}"},
                        json={"max_concurrent_positions": 3, "max_portfolio_exposure_pct": 0,
                              "max_symbol_exposure_usd": 0, "use_kelly": False})
        gate = self._gate(symbol="C1")  # already held → add-on allowed
        self.assertTrue(gate.allowed)

    def test_zero_disables_both_caps(self):
        for i in range(5):
            self._insert_position(symbol=f"C{i}", qty=1.0, entry=100.0, current=100.0)
        self.client.put("/api/risk/limits", headers={"Authorization": f"Bearer {self.token}"},
                        json={"max_concurrent_positions": 0, "max_portfolio_exposure_pct": 0,
                              "max_symbol_exposure_usd": 0, "use_kelly": False})
        gate = self._gate(symbol="C99")
        self.assertTrue(gate.allowed)

    def test_defaults_present_in_limits_api(self):
        resp = self.client.get("/api/risk/limits", headers={"Authorization": f"Bearer {self.token}"})
        limits = resp.json()["limits"]
        self.assertEqual(limits["max_portfolio_exposure_pct"], 60.0)
        self.assertEqual(limits["max_concurrent_positions"], 8)


class RiskLevelPropagationTests(RiskEngineTestCase):
    """Plan 06 B2/C2 — rule risk_level expands into the agent's risk_limits."""

    def _post_rule(self, risk_level=None):
        body = {"symbol": "BTC", "market": "crypto", "interval_minutes": 60,
                "min_confidence": 0.65, "size_usd": 500, "auto_execute": True,
                "account_type": "simulator"}
        if risk_level is not None:
            body["risk_level"] = risk_level
        return self.client.post("/api/automation/configs", json=body,
                                headers={"Authorization": f"Bearer {self.token}"})

    def test_stable_level_writes_exit_profile(self):
        resp = self._post_rule("stable")
        self.assertEqual(resp.status_code, 200, resp.text)
        applied = resp.json()["risk_limits"]
        self.assertAlmostEqual(applied["stop_loss_pct"], 0.03)
        self.assertAlmostEqual(applied["take_profit_pct"], 0.06)
        self.assertEqual(applied["use_trailing"], 1)
        self.assertEqual(applied["time_stop_days"], 5)
        # persisted, not just echoed
        limits = self.client.get("/api/risk/limits",
                                 headers={"Authorization": f"Bearer {self.token}"}).json()["limits"]
        self.assertAlmostEqual(limits["stop_loss_pct"], 0.03)
        self.assertEqual(limits["time_stop_days"], 5)

    def test_aggressive_level_disables_trailing(self):
        resp = self._post_rule("aggressive")
        applied = resp.json()["risk_limits"]
        self.assertAlmostEqual(applied["stop_loss_pct"], 0.08)
        # 0.16, not the 0.15 this used to pin: at 0.15 the profile graded 1.875
        # against RR_FLOOR 2.0 and the gate refused every deferred-bracket
        # entry. See test_every_preset_can_clear_the_house_rr_floor.
        self.assertAlmostEqual(applied["take_profit_pct"], 0.16)
        self.assertEqual(applied["use_trailing"], 0)

    def test_no_level_leaves_limits_untouched(self):
        before = self.client.get("/api/risk/limits",
                                 headers={"Authorization": f"Bearer {self.token}"}).json()["limits"]
        resp = self._post_rule(None)
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.json()["risk_limits"])
        after = self.client.get("/api/risk/limits",
                                headers={"Authorization": f"Bearer {self.token}"}).json()["limits"]
        self.assertEqual(before["stop_loss_pct"], after["stop_loss_pct"])

    def test_invalid_level_rejected(self):
        resp = self._post_rule("yolo")
        self.assertEqual(resp.status_code, 422)

    def test_risk_level_stored_on_rule(self):
        self._post_rule("balanced")
        configs = self.client.get("/api/automation/configs",
                                  headers={"Authorization": f"Bearer {self.token}"}).json()["configs"]
        self.assertEqual(configs[0]["risk_level"], "balanced")


class ShortSideTests(RiskEngineTestCase):
    """Plan 06 A3 — short/cover executor, inverted SL/TP, watcher legs."""

    def test_short_open_and_cover_cash_math(self):
        from automation import execute_paper_trade
        from fees import TRADE_FEE_RATE
        start = self._cash()
        sig1, skip1 = execute_paper_trade(self.agent_id, "BTC", "crypto", "short", 1.0, 100.0)
        self.assertIsNotNone(sig1, skip1)
        pos = self._position()
        self.assertEqual(float(pos["quantity"]), -1.0)
        self.assertAlmostEqual(self._cash(), start - 100.0 - 100.0 * TRADE_FEE_RATE, places=6)
        # cover at 90 → profit 10; credit = (2*100 - 90)*1 - fee(90)
        sig2, skip2 = execute_paper_trade(self.agent_id, "BTC", "crypto", "cover", 1.0, 90.0)
        self.assertIsNotNone(sig2, skip2)
        self.assertIsNone(self._position())
        expected = start - 100.0 - 100.0 * TRADE_FEE_RATE + (200.0 - 90.0) - 90.0 * TRADE_FEE_RATE
        self.assertAlmostEqual(self._cash(), expected, places=6)

    def test_cover_without_short_skips(self):
        from automation import execute_paper_trade
        sig, skip = execute_paper_trade(self.agent_id, "BTC", "crypto", "cover", 1.0, 100.0)
        self.assertIsNone(sig)
        self.assertIn("no short position", skip)

    def test_gate_stamps_inverted_exits_for_short(self):
        from risk_engine import evaluate_order
        gate = evaluate_order(self.agent_id, "BTC", "crypto", "short", 1.0, 100.0)
        self.assertTrue(gate.allowed)
        self.assertAlmostEqual(gate.stop_loss, 105.0)     # 5% above
        self.assertAlmostEqual(gate.take_profit, 90.0)    # 10% below

    def test_watcher_covers_short_on_stop(self):
        from risk_engine import run_sltp_watcher_tick
        self._insert_position(symbol="BTC", qty=-1.0, entry=100.0, current=106.0,
                              stop_loss=105.0, take_profit=90.0)
        result = run_sltp_watcher_tick()
        self.assertEqual(result["closed"], 1)
        self.assertIsNone(self._position())

    def test_watcher_covers_short_on_target(self):
        from risk_engine import run_sltp_watcher_tick
        self._insert_position(symbol="BTC", qty=-1.0, entry=100.0, current=89.0,
                              stop_loss=105.0, take_profit=90.0)
        result = run_sltp_watcher_tick()
        self.assertEqual(result["closed"], 1)
        self.assertIsNone(self._position())

    def test_watcher_leaves_healthy_short_alone(self):
        from risk_engine import run_sltp_watcher_tick
        self._insert_position(symbol="BTC", qty=-1.0, entry=100.0, current=99.0,
                              stop_loss=105.0, take_profit=90.0)
        result = run_sltp_watcher_tick()
        self.assertEqual(result["closed"], 0)
        self.assertIsNotNone(self._position())

    def test_short_counts_toward_portfolio_exposure(self):
        from risk_engine import evaluate_order
        self._insert_position(symbol="ETH", qty=-10.0, entry=5900.0, current=5900.0)  # $59k short
        self.client.put("/api/risk/limits", headers={"Authorization": f"Bearer {self.token}"},
                        json={"max_portfolio_exposure_pct": 60, "max_concurrent_positions": 0,
                              "max_symbol_exposure_usd": 0, "use_kelly": False})
        gate = evaluate_order(self.agent_id, "BTC", "crypto", "buy", 100.0, 400.0)  # $40k order
        self.assertFalse(gate.allowed)
        self.assertIn("portfolio exposure limit", gate.reason)
