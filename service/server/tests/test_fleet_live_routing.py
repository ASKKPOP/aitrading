"""Full Auto fleet in Real mode routes its orders to the gateway (owner
2026-11-24: "make Full Auto fleet route orders to Webull in Real mode").

Contract under test:
  - a run whose config snapshot says account_type=live sends every trade —
    entries, closes, and closes of a position it handed off — to the
    gateway FIRST, and books the ledger only when the broker took it;
  - the ledger's own refusals (cash, duplicate client_order_id) are checked
    BEFORE the broker, so a trade the ledger would refuse never reaches it;
  - a simulator run never touches the network;
  - live fleets are refused at creation unless every market has a usable
    live gateway, and never leveraged; the account type rides into each
    run's config snapshot.

All HTTP is faked; an unexpected request fails the test.
"""
from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path
from urllib.parse import urlparse

SERVER_DIR = Path(__file__).resolve().parents[1]
TESTS_DIR = Path(__file__).resolve().parent
for p in (SERVER_DIR, TESTS_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import database  # noqa: E402
from test_execution_venues import (  # noqa: E402
    _accept_tcs,
    _add_account,
    _DbTestCase,
    _FakeResponse,
    _patch_http,
)

PLACE = "/trading/orders/place"
POSITIONS = "/trading/assets/positions/list"


def _placed(calls):
    return [json.loads(c[2]["content"])["new_orders"][0]
            for c in calls if urlparse(c[1]).path == PLACE]


def _webull_ok(method, url, kwargs):
    if urlparse(url).path == PLACE:
        return _FakeResponse(200, {"client_order_id": "c", "order_id": "W1"})
    return None


class _LiveRunCase(_DbTestCase):
    def setUp(self):
        super().setUp()
        _add_account(self.agent_id, "webull", {"key": "k", "secret": "s",
                                               "account_id": "ACC1"})
        _accept_tcs(self.agent_id, "webull")
        os.environ["LIVE_BROKER_ALLOWLIST"] = "webull"

    def _run(self, account_type):
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO trading_runs (agent_id, symbol, market, market_type,"
            " status, config_snapshot_json, start_condition_json,"
            " stop_conditions_json, created_at, created_via) VALUES "
            "(?,?,?,'spot','running',?,'{}','{}','2026-11-24T00:00:00Z','fleet')",
            (self.agent_id, "AAPL", "us-stock",
             json.dumps({"account_type": account_type} if account_type else {})))
        rid = cur.lastrowid
        conn.commit()
        conn.close()
        return rid

    def _trade(self, side, qty, run_id, price=100.0, coid=None):
        from automation import execute_paper_trade
        return execute_paper_trade(self.agent_id, "AAPL", "us-stock", side, qty,
                                   price, run_id=run_id, client_order_id=coid)

    def _signals(self):
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT side, quantity, run_id FROM signals WHERE agent_id=?"
                    " ORDER BY id", (self.agent_id,))
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows

    def _live_orders(self):
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT side, status, execution_mode FROM broker_orders"
                    " WHERE agent_id=? ORDER BY id", (self.agent_id,))
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows


class LiveRunRoutingTests(_LiveRunCase):
    def test_live_run_entry_goes_to_webull_then_the_ledger(self):
        run = self._run("live")
        patcher, calls = _patch_http(_webull_ok)
        with patcher:
            sig, skip = self._trade("buy", 5, run)
        self.assertTrue(sig, skip)
        legs = _placed(calls)
        self.assertEqual([leg["side"] for leg in legs], ["BUY"])
        self.assertEqual(urlparse(calls[-1][1]).netloc, "api.webull.com")
        self.assertEqual(self._signals(), [{"side": "buy", "quantity": 5.0, "run_id": run}])
        self.assertEqual([(o["side"], o["execution_mode"]) for o in self._live_orders()],
                         [("buy", "live")])

    def test_simulator_run_never_calls_out(self):
        run = self._run("simulator")
        patcher, calls = _patch_http(lambda m, u, k: None)
        with patcher:
            sig, skip = self._trade("buy", 5, run)
        self.assertTrue(sig, skip)
        self.assertEqual(calls, [])
        self.assertEqual(self._live_orders(), [])

    def test_run_without_account_type_stays_simulated(self):
        run = self._run(None)
        patcher, calls = _patch_http(lambda m, u, k: None)
        with patcher:
            sig, _ = self._trade("buy", 5, run)
        self.assertTrue(sig)
        self.assertEqual(calls, [])

    def test_broker_rejection_books_nothing(self):
        run = self._run("live")
        patcher, _ = _patch_http(lambda m, u, k: _FakeResponse(
            417, {"error_code": "X", "message": "insufficient buying power"}))
        with patcher:
            sig, skip = self._trade("buy", 5, run)
        self.assertIsNone(sig)
        self.assertIn("gateway rejected order", skip)
        self.assertEqual(self._signals(), [], "no ledger position for a refused order")

    def test_ledger_refusal_is_checked_before_the_broker(self):
        """$500 buy with $50 cash: the ledger refuses, so Webull must never
        see the order (a broker fill the ledger then refused is a real
        position nothing on the platform knows about)."""
        conn = database.get_db_connection()
        conn.cursor().execute("UPDATE agents SET cash = 50 WHERE id = ?", (self.agent_id,))
        conn.commit()
        conn.close()
        run = self._run("live")
        patcher, calls = _patch_http(_webull_ok)
        with patcher:
            sig, skip = self._trade("buy", 5, run)
        self.assertIsNone(sig)
        self.assertIn("insufficient cash", skip)
        self.assertEqual(_placed(calls), [])

    def test_duplicate_cycle_is_not_sent_twice(self):
        run = self._run("live")
        patcher, calls = _patch_http(_webull_ok)
        with patcher:
            first, _ = self._trade("buy", 5, run, coid=f"run:{run}:cyc:1")
            again, skip = self._trade("buy", 5, run, coid=f"run:{run}:cyc:1")
        self.assertTrue(first)
        self.assertIsNone(again)
        self.assertIn("duplicate client_order_id", skip)
        self.assertEqual(len(_placed(calls)), 1, "a replayed cycle never reaches Webull again")

    def test_over_cap_order_is_refused_and_not_booked(self):
        run = self._run("live")
        patcher, calls = _patch_http(_webull_ok)
        with patcher:
            sig, skip = self._trade("buy", 15, run)   # $1,500 > $1,000 cap
        self.assertIsNone(sig)
        self.assertIn("per-order limit", skip)
        self.assertEqual(_placed(calls), [])
        self.assertEqual(self._signals(), [])

    def test_live_close_goes_to_webull_too(self):
        run = self._run("live")
        patcher, calls = _patch_http(_webull_ok)
        with patcher:
            self._trade("buy", 5, run)
            sig, skip = self._trade("sell", 5, run, price=101.0)
        self.assertTrue(sig, skip)
        self.assertEqual([leg["side"] for leg in _placed(calls)], ["BUY", "SELL"])

    def test_closing_a_handed_off_live_position_goes_to_webull(self):
        """A live run that stops with hold releases its position to the
        unowned book (run_id NULL, handoff_run_id set). The watcher / orphan
        reclaim then close it WITHOUT a run_id — that close must still reach
        Webull, or the shares stay open at the broker."""
        run = self._run("live")
        patcher, calls = _patch_http(_webull_ok)
        with patcher:
            self._trade("buy", 5, run)
        conn = database.get_db_connection()
        conn.cursor().execute(
            "UPDATE positions SET handoff_run_id = ?, run_id = NULL "
            "WHERE agent_id = ? AND symbol = 'AAPL'", (run, self.agent_id))
        conn.commit()
        conn.close()
        patcher, calls = _patch_http(_webull_ok)
        with patcher:
            sig, skip = self._trade("sell", 5, None, price=99.0)
        self.assertTrue(sig, skip)
        self.assertEqual([leg["side"] for leg in _placed(calls)], ["SELL"])

    def test_unowned_close_without_a_live_origin_stays_simulated(self):
        patcher, calls = _patch_http(lambda m, u, k: None)
        with patcher:
            self._trade("buy", 5, None)
            sig, _ = self._trade("sell", 5, None)
        self.assertTrue(sig)
        self.assertEqual(calls, [])


class LiveFleetCreationTests(_DbTestCase):
    def test_live_fleet_needs_a_usable_gateway_per_market(self):
        from fleet_planner import live_fleet_refusal
        self.assertIn("gateway", live_fleet_refusal(self.agent_id, ["us-stock"], None))
        _add_account(self.agent_id, "webull", {"key": "k", "secret": "s"})
        _accept_tcs(self.agent_id, "webull")
        os.environ["LIVE_BROKER_ALLOWLIST"] = "webull"
        self.assertIsNone(live_fleet_refusal(self.agent_id, ["us-stock"], None))
        # Webull cannot trade crypto: a crypto market has no live gateway.
        self.assertIsNotNone(live_fleet_refusal(self.agent_id, ["us-stock", "crypto"], None))
        self.assertIsNotNone(live_fleet_refusal(self.agent_id, None, None),
                             "a live fleet must name its markets")
        self.assertIsNotNone(live_fleet_refusal(self.agent_id, ["us-stock"], 2.0),
                             "never leveraged")

    def test_account_type_rides_into_the_run_snapshot(self):
        from fleet_planner import carry_snapshot_stamps
        core: dict = {}
        carry_snapshot_stamps(core, {"account_type": "live"})
        self.assertEqual(core["account_type"], "live")

    def test_compose_stamps_the_fleets_account_type(self):
        import fleet_planner as fp
        thesis = {"symbol": "AAPL", "market": "us-stock", "direction": "long",
                  "confidence": 0.7, "expected_move_pct": 2.0, "horizon_hours": 24}
        live = fp.compose_run_settings(
            thesis, 1000.0, {"risk_appetite": "balanced", "lang": "en",
                             "account_type": "live"})
        sim = fp.compose_run_settings(
            thesis, 1000.0, {"risk_appetite": "balanced", "lang": "en"})
        self.assertEqual(live["account_type"], "live")
        self.assertEqual(sim["account_type"], "simulator")

    def test_successor_of_a_live_fleet_is_live(self):
        from unittest.mock import patch
        import fleet_planner as fp
        import fleet_supervisor as fs
        fleet = {"id": 9, "agent_id": self.agent_id, "n_runs": 5,
                 "total_budget_usd": 5000.0, "warn_loss_frac": 0.3,
                 "stop_loss_frac": 0.4, "market_scope_json": '["us-stock"]',
                 "account_type": "live"}
        with patch.object(fp, "create_fleet", return_value=10) as cf, \
                patch.object(fp, "start_fleet"), \
                patch.object(fs, "_update_fleet"), patch.object(fp, "emit_fleet_event"):
            fs._spawn_successor(fleet)
        self.assertEqual(cf.call_args.kwargs["account_type"], "live")

if __name__ == "__main__":
    unittest.main()
