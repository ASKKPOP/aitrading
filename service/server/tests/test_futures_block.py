"""Platform-wide futures block (owner decision 2026-11-20).

sooppiy.com trades spot and US stock only. No futures orders, runs or fleets
anywhere. futures_policy holds one switch (platform_settings key
`futures_trading_blocked`, env twin FUTURES_TRADING_BLOCKED, default ON). Each
entry path asks it the same question:

  * ledger         services._update_position_from_signal (every simulated fill)
  * executor       automation.execute_paper_trade (runs, rules, resting fills,
                   trend module, fleets)
  * automation     _execute_for_account_type (checked BEFORE a live venue)
  * gateway        execution.gateway.submit_live / submit_shadow, router.execute
  * run start      trading_runs.start_run (a draft made before the switch too)
  * run create     POST /api/runs
  * manual order   POST /api/signals/realtime, resting orders, self-register seeds
  * fleet          symbol_research.select_targets, compose leverage, create_fleet

The invariant every test pins alongside the refusal: CLOSING is never blocked.
A cover of an existing short and a sell of an existing (leveraged) long always
pass, so a book opened before the switch can always reach flat.

conftest.py runs the suite with the block OFF (pre-existing tests exercise the
futures paths). Each test here turns it on explicitly, and the
production default is asserted by unsetting the variable.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
import futures_policy
import trading_runs

_ON = {"FUTURES_TRADING_BLOCKED": "1"}
_OFF = {"FUTURES_TRADING_BLOCKED": "0"}
_NOW = "2026-11-20T03:00:00Z"
# A Tuesday within NYSE market hours (10:00 AM ET).
_MARKET_TS = "2024-01-02T15:00:00Z"


class _DbBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO users (email, password_hash, created_at) "
            "VALUES ('f@x.com', 'x', '2026-01-01T00:00:00Z')")
        self.user_id = cur.lastrowid
        cur.execute(
            "INSERT INTO agents (name, token_hash, cash, user_id, created_at) "
            "VALUES ('fut-agent', 'thf', 100000, ?, '2026-01-01T00:00:00Z')",
            (self.user_id,))
        self.agent_id = cur.lastrowid
        conn.commit()
        conn.close()
        self.env = patch.dict(os.environ, _ON)
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def _q(self, sql, args=()):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute(sql, args)
            return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

    def _x(self, sql, args=()):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute(sql, args)
            conn.commit()
        finally:
            conn.close()

    def _seed_position(self, symbol, market, qty, entry=100.0, leverage=1.0):
        side = "short" if qty < 0 else "long"
        self._x("INSERT INTO positions (agent_id, symbol, market, side, quantity, "
                "entry_price, opened_at, leverage) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (self.agent_id, symbol, market, side, qty, entry, _NOW, leverage))

    def _positions(self, symbol):
        return self._q("SELECT quantity, leverage FROM positions WHERE agent_id = ? "
                       "AND symbol = ?", (self.agent_id, symbol))


# ── the switch ──────────────────────────────────────────────────────────────

class SwitchTests(_DbBase):
    def test_production_default_is_blocked(self):
        """No stored setting and no env var: futures are refused."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("FUTURES_TRADING_BLOCKED", None)
            self.assertTrue(futures_policy.futures_blocked())

    def test_env_off_unblocks(self):
        with patch.dict(os.environ, _OFF):
            self.assertFalse(futures_policy.futures_blocked())

    def test_stored_setting_wins_over_env(self):
        self._x("INSERT INTO platform_settings (setting_key, setting_value, updated_at) "
                "VALUES ('futures_trading_blocked', '0', ?)", (_NOW,))
        self.assertFalse(futures_policy.futures_blocked())  # env says 1
        self._x("UPDATE platform_settings SET setting_value = 'on' "
                "WHERE setting_key = 'futures_trading_blocked'")
        with patch.dict(os.environ, _OFF):
            self.assertTrue(futures_policy.futures_blocked())

    def test_unreadable_setting_falls_back_to_env_then_on(self):
        broken = MagicMock()
        broken.execute.side_effect = RuntimeError("no table")
        os.environ.pop("FUTURES_TRADING_BLOCKED", None)
        self.assertTrue(futures_policy.futures_blocked(broken))
        with patch.dict(os.environ, _OFF):
            self.assertFalse(futures_policy.futures_blocked(broken))

    def test_closes_are_never_refused(self):
        for market in ("crypto", "futures", "us-stock"):
            for action in ("sell", "cover"):
                self.assertIsNone(
                    futures_policy.order_refusal(market, action, leverage=5.0))

    def test_spot_open_passes(self):
        self.assertIsNone(futures_policy.order_refusal("crypto", "buy", 1.0))
        self.assertIsNone(futures_policy.order_refusal("us-stock", "buy", 1.0))


# ── ledger ──────────────────────────────────────────────────────────────────

class LedgerTests(_DbBase):
    def _fill(self, symbol, market, action, qty=1.0, leverage=1.0):
        from services import _update_position_from_signal
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            _update_position_from_signal(self.agent_id, symbol, market, action, qty,
                                         100.0, _NOW, cursor=cur, leverage=leverage)
            conn.commit()
        finally:
            conn.close()

    def test_short_open_refused_on_every_market(self):
        for market, sym in (("crypto", "SOLUSDT"), ("us-stock", "AAPL")):
            with self.assertRaises(ValueError) as ctx:
                self._fill(sym, market, "short")
            self.assertIn("futures trading is disabled", str(ctx.exception))
            self.assertEqual(self._positions(sym), [])

    def test_futures_market_buy_refused(self):
        with self.assertRaises(ValueError):
            self._fill("ES", "futures", "buy")
        self.assertEqual(self._positions("ES"), [])

    def test_leveraged_buy_refused(self):
        with self.assertRaises(ValueError):
            self._fill("BTC", "crypto", "buy", leverage=3.0)
        self.assertEqual(self._positions("BTC"), [])

    def test_adding_to_an_existing_short_refused(self):
        self._seed_position("ETH", "crypto", -2.0)
        with self.assertRaises(ValueError):
            self._fill("ETH", "crypto", "short")
        self.assertEqual(float(self._positions("ETH")[0]["quantity"]), -2.0)

    def test_spot_buy_and_closes_pass(self):
        self._fill("BTC", "crypto", "buy")
        self.assertEqual(float(self._positions("BTC")[0]["quantity"]), 1.0)
        self._seed_position("ETH", "crypto", -2.0)
        self._fill("ETH", "crypto", "cover", qty=2.0)          # full cover
        self.assertEqual(self._positions("ETH"), [])
        self._seed_position("XRP", "crypto", 5.0, leverage=3.0)
        self._fill("XRP", "crypto", "sell", qty=5.0)           # leveraged long out
        self.assertEqual(self._positions("XRP"), [])

    def test_switch_off_restores_shorts(self):
        with patch.dict(os.environ, _OFF):
            self._fill("SOLUSDT", "crypto", "short")
        self.assertEqual(float(self._positions("SOLUSDT")[0]["quantity"]), -1.0)


# ── paper executor (runs, rules, resting fills, trend module, fleets) ──────

class ExecutorTests(_DbBase):
    def test_short_is_a_clean_skip_with_no_write(self):
        from automation import execute_paper_trade
        sid, why = execute_paper_trade(self.agent_id, "SOLUSDT", "crypto", "short",
                                       1.0, 100.0)
        self.assertIsNone(sid)
        self.assertIn("futures trading is disabled", why)
        self.assertEqual(self._positions("SOLUSDT"), [])
        self.assertEqual(self._q("SELECT cash FROM agents WHERE id = ?",
                                 (self.agent_id,))[0]["cash"], 100000)

    def test_leveraged_run_buy_skipped(self):
        from automation import execute_paper_trade
        sid, why = execute_paper_trade(self.agent_id, "BTC", "crypto", "buy",
                                       1.0, 100.0, leverage=2.0)
        self.assertIsNone(sid)
        self.assertIn("leveraged", why)

    def test_cover_of_a_pre_switch_short_still_fills(self):
        from automation import execute_paper_trade
        self._seed_position("BNBUSDT", "crypto", -1.0, entry=100.0)
        sid, why = execute_paper_trade(self.agent_id, "BNBUSDT", "crypto", "cover",
                                       1.0, 90.0)
        self.assertIsNone(why)
        self.assertIsNotNone(sid)
        self.assertEqual(self._positions("BNBUSDT"), [])

    def test_spot_buy_fills(self):
        from automation import execute_paper_trade
        sid, why = execute_paper_trade(self.agent_id, "BTC", "crypto", "buy", 1.0, 100.0)
        self.assertIsNone(why)
        self.assertEqual(float(self._positions("BTC")[0]["quantity"]), 1.0)


# ── automation live path + gateway ─────────────────────────────────────────

class GatewayTests(_DbBase):
    def test_live_rule_short_never_reaches_the_venue(self):
        import automation
        with patch("execution.gateway.submit_live") as live:
            sid, why = automation._execute_for_account_type(
                {"account_type": "live"}, self.agent_id, "SOLUSDT", "crypto",
                "short", 1.0, 100.0, None, None, {})
        live.assert_not_called()
        self.assertIsNone(sid)
        self.assertIn("futures trading is disabled", why)

    def test_submit_live_refuses_before_any_broker(self):
        from execution import gateway
        from execution.base import OrderStatus
        acct = {"broker": "binance", "execution_mode": "live"}
        with patch.object(gateway, "active_broker_account", return_value=acct), \
             patch.object(gateway, "_broker_for") as broker_for, \
             patch("execution.router._persist_order", return_value=1):
            order = gateway.submit_live(self.agent_id, "SOLUSDT", "crypto",
                                        "short", 1.0, 100.0)
        broker_for.assert_not_called()
        self.assertEqual(order.status, OrderStatus.REJECTED)
        self.assertIn("futures trading is disabled", order.error_message)

    def test_submit_live_cover_is_not_refused_by_the_block(self):
        """A cover reaches the broker selection (here: no link → NOT_CONFIGURED,
        not the futures refusal)."""
        from execution import gateway
        with patch.object(gateway, "active_broker_account", return_value=None), \
             patch("execution.router._persist_order", return_value=1):
            order = gateway.submit_live(self.agent_id, "SOLUSDT", "crypto",
                                        "cover", 1.0, 100.0)
        self.assertNotIn("futures trading is disabled", order.error_message or "")

    def test_submit_shadow_sends_no_sandbox_short(self):
        from execution import gateway
        with patch.object(gateway, "active_broker_account") as acct:
            self.assertIsNone(gateway.submit_shadow(
                self.agent_id, "SOLUSDT", "crypto", "short", 1.0, 100.0, 1.0))
        acct.assert_not_called()

    def test_router_execute_refuses_short(self):
        import asyncio
        from execution.base import Order, OrderStatus
        from execution.router import ExecutionRouter
        order = Order(agent_id=self.agent_id, symbol="SOLUSDT", market="crypto",
                      side="short", quantity=1.0, price=100.0, created_at=_NOW)
        with patch("execution.router._get_active_broker_account") as acct:
            out = asyncio.run(ExecutionRouter().execute(self.agent_id, order))
        acct.assert_not_called()
        self.assertEqual(out.status, OrderStatus.REJECTED)


# ── runs ────────────────────────────────────────────────────────────────────

def _settings(**over):
    base = {"symbol": "BTC", "market": "crypto", "market_type": "spot",
            "max_bet_usd": 100.0, "run_budget_usd": None, "interval_minutes": 60,
            "min_confidence": 0.7, "provider": "openai", "lang": "en",
            "leverage": 1.0}
    base.update(over)
    return base


class RunStartTests(_DbBase):
    def _draft(self, **over):
        with patch.dict(os.environ, _OFF):   # a draft made before the switch
            return trading_runs.create_run(self.agent_id, _settings(**over),
                                           {"type": "manual"}, {}, True)

    def _status(self, run_id):
        return self._q("SELECT status FROM trading_runs WHERE id = ?",
                       (run_id,))[0]["status"]

    def test_futures_run_cannot_start(self):
        for over in ({"market_type": "futures"},
                     {"symbol": "ES", "market": "futures"},
                     {"symbol": "ETH", "leverage": 3.0}):
            run_id = self._draft(**over)
            with self.assertRaises(trading_runs.EntitlementDenied) as ctx:
                trading_runs.start_run(run_id, self.agent_id)
            self.assertIn("futures trading is disabled", str(ctx.exception))
            self.assertEqual(self._status(run_id), "draft")

    def test_spot_crypto_and_us_stock_runs_start(self):
        crypto = self._draft()
        stock = self._draft(symbol="AAPL", market="us-stock")
        with patch("entitlements.check_run_start", return_value=None):
            trading_runs.start_run(crypto, self.agent_id)
            trading_runs.start_run(stock, self.agent_id)
        self.assertEqual(self._status(crypto), "running")
        self.assertEqual(self._status(stock), "running")


class RunRouteTests(_DbBase):
    def setUp(self):
        super().setUp()
        from routes import create_app
        self.client = TestClient(create_app())
        resp = self.client.post("/api/claw/agents/selfRegister",
                                json={"name": "route-agent", "password": "pw123",
                                      "initial_balance": 10000})
        self.assertEqual(resp.status_code, 200, resp.text)
        self.headers = {"Authorization": f"Bearer {resp.json()['token']}"}
        self.probe = patch("routes_runs._probe_price", return_value=100.0)
        self.probe.start()
        self.tier = patch("entitlements.check_futures_access", return_value=None)
        self.tier.start()

    def tearDown(self):
        self.probe.stop()
        self.tier.stop()
        super().tearDown()

    def _create(self, **body):
        payload = {"symbol": "BTC", "market": "crypto", "market_type": "spot",
                   "max_bet_usd": 100.0}
        payload.update(body)
        return self.client.post("/api/runs", json=payload, headers=self.headers)

    def test_futures_run_create_is_403(self):
        resp = self._create(market_type="futures")
        self.assertEqual(resp.status_code, 403, resp.text)
        self.assertIn("futures trading is disabled", resp.text)

    def test_spot_run_create_is_ok(self):
        resp = self._create()
        self.assertEqual(resp.status_code, 200, resp.text)


# ── manual orders ───────────────────────────────────────────────────────────

class ManualOrderTests(_DbBase):
    def setUp(self):
        super().setUp()
        from routes import create_app
        self.client = TestClient(create_app())
        resp = self.client.post("/api/claw/agents/selfRegister",
                                json={"name": "manual-agent", "password": "pw123",
                                      "initial_balance": 100000})
        self.assertEqual(resp.status_code, 200, resp.text)
        self.manual_id = resp.json()["agent_id"]
        self.headers = {"Authorization": f"Bearer {resp.json()['token']}"}

    def _trade(self, action, qty=1.0, leverage=None):
        body = {"market": "us-stock", "action": action, "symbol": "AAPL",
                "price": 150.0, "quantity": qty, "executed_at": _MARKET_TS}
        if leverage is not None:
            body["leverage"] = leverage
        with patch.dict(os.environ, {"ALLOW_SYNC_PRICE_FETCH_IN_API": "false"}):
            return self.client.post("/api/signals/realtime", json=body,
                                    headers=self.headers)

    def test_short_and_leverage_are_403(self):
        self.assertEqual(self._trade("short").status_code, 403)
        resp = self._trade("buy", leverage=5)
        self.assertEqual(resp.status_code, 403, resp.text)
        self.assertEqual(self._q("SELECT * FROM positions WHERE agent_id = ?",
                                 (self.manual_id,)), [])

    def test_spot_buy_sell_and_cover_pass(self):
        self.assertEqual(self._trade("buy").status_code, 200)
        self.assertEqual(self._trade("sell").status_code, 200)
        self._x("INSERT INTO positions (agent_id, symbol, market, side, quantity, "
                "entry_price, opened_at) VALUES (?, 'AAPL', 'us-stock', 'short', "
                "-1, 160, ?)", (self.manual_id, _NOW))
        resp = self._trade("cover")
        self.assertEqual(resp.status_code, 200, resp.text)

    def test_self_register_cannot_seed_a_short(self):
        resp = self.client.post("/api/claw/agents/selfRegister", json={
            "name": "seed-agent", "password": "pw123", "initial_balance": 1000,
            "positions": [{"symbol": "AAPL", "market": "us-stock", "side": "short",
                           "quantity": 1, "entry_price": 100}]})
        self.assertEqual(resp.status_code, 403, resp.text)
        self.assertEqual(self._q("SELECT id FROM agents WHERE name = 'seed-agent'"), [])

    def test_resting_order_refused_at_placement(self):
        from resting_orders import place_resting_order
        order, why = place_resting_order(self.manual_id, "crypto", "short", "SOL",
                                         1.0, 120.0, 100.0)
        self.assertIsNone(order)
        self.assertIn("futures trading is disabled", why)
        order, why = place_resting_order(self.manual_id, "crypto", "buy", "SOL",
                                         1.0, 90.0, 100.0, leverage=3)
        self.assertIsNone(order)
        self.assertIn("leveraged", why)
        order, why = place_resting_order(self.manual_id, "crypto", "buy", "SOL",
                                         1.0, 90.0, 100.0)
        self.assertIsNone(why)


# ── fleets ──────────────────────────────────────────────────────────────────

class FleetTests(_DbBase):
    def setUp(self):
        super().setUp()
        self.plan = patch("entitlements.plan_code_for_user",
                          return_value="professional")
        self.plan.start()

    def tearDown(self):
        self.plan.stop()
        super().tearDown()

    def _seed_theses(self):
        rows = [("SOL", "short", 0.9), ("ETH", "short", 0.8),
                ("BTC", "long", 0.7), ("XRP", "long", 0.6)]
        for sym, direction, score in rows:
            mt = "futures" if direction == "short" else "spot"
            self._x("""INSERT INTO research_theses
                       (batch_id, market, symbol, market_type, direction,
                        factor_scores_json, final_score, selectable, planner,
                        created_at, expires_at)
                       VALUES ('b1', 'crypto', ?, ?, ?, '{}', ?, 1, 'fallback',
                               ?, '2999-01-01T00:00:00Z')""",
                    (sym, mt, direction, score, _NOW))

    def test_select_targets_never_hands_out_a_short(self):
        import symbol_research as sr
        self._seed_theses()
        conn = database.get_db_connection()
        try:
            picked = sr.select_targets(conn.cursor(), self.agent_id, 4)
        finally:
            conn.close()
        self.assertEqual(sorted(t["symbol"] for t in picked), ["BTC", "XRP"])
        self.assertTrue(all(t["direction"] == "long" for t in picked))

    def test_select_targets_off_keeps_shorts(self):
        import symbol_research as sr
        self._seed_theses()
        conn = database.get_db_connection()
        try:
            with patch.dict(os.environ, _OFF):
                picked = sr.select_targets(conn.cursor(), self.agent_id, 4)
        finally:
            conn.close()
        self.assertIn("short", {t["direction"] for t in picked})

    def test_compose_pins_leverage_to_1x(self):
        import fleet_planner as fp
        thesis = {"symbol": "BTC", "market": "crypto", "direction": "long",
                  "confidence": 0.7, "expected_move_pct": 3.0, "horizon_hours": 12}
        fleet = {"agent_id": self.agent_id, "risk_appetite": "aggressive",
                 "total_budget_usd": 10000, "n_runs": 4}
        settings = fp.compose_run_settings(thesis, 2500.0, fleet)
        self.assertEqual(settings["leverage"], 1.0)
        self.assertEqual(settings["market_type"], "spot")
        with patch.dict(os.environ, _OFF):
            self.assertEqual(fp.compose_run_settings(thesis, 2500.0, fleet)["leverage"],
                             2.0)

    def test_futures_or_leveraged_fleet_cannot_be_created(self):
        import fleet_planner as fp
        with self.assertRaises(trading_runs.EntitlementDenied):
            fp.create_fleet(self.agent_id, 3, 3000.0, market_scope=["futures"])
        with self.assertRaises(trading_runs.EntitlementDenied):
            fp.create_fleet(self.agent_id, 3, 3000.0, leverage=3.0)
        self.assertEqual(self._q("SELECT id FROM fleets"), [])

    def test_spot_and_us_stock_fleets_create(self):
        import fleet_planner as fp
        fid = fp.create_fleet(self.agent_id, 3, 3000.0,
                              market_scope=["crypto", "us-stock"])
        self.assertTrue(fid)

    def test_build_skips_a_short_thesis_selected_before_the_switch(self):
        """A candidate bound while the block was off must not become a run."""
        import fleet_planner as fp
        self._seed_theses()
        with patch.dict(os.environ, _OFF):
            fid = fp.create_fleet(self.agent_id, 1, 1000.0, market_scope=["crypto"])
            fp.start_fleet(fid, self.agent_id)
            fp._do_research(fp.get_fleet(fid))          # binds SOL (short)
        cands = self._q("SELECT thesis_key FROM fleet_candidates WHERE fleet_id = ?",
                        (fid,))
        self.assertTrue(any(":SOL" in c["thesis_key"] for c in cands), cands)
        with patch("routes_runs._probe_price", return_value=100.0):
            fp._do_build(fp.get_fleet(fid))
        self.assertEqual(self._q("SELECT id FROM trading_runs WHERE fleet_id = ?",
                                 (fid,)), [])
        reasons = [json.loads(r["payload"]).get("reason") for r in self._q(
            "SELECT payload FROM fleet_events WHERE fleet_id = ? AND "
            "event_type = 'candidate_skipped'", (fid,))]
        self.assertIn("futures_blocked", reasons)


if __name__ == "__main__":
    unittest.main()
