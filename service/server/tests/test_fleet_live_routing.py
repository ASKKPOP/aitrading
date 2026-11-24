"""Full Auto fleet in Real mode routes its orders to the gateway (owner
2026-11-24: "make Full Auto fleet route orders to Webull in Real mode").

Contract under test:
  - a run whose config snapshot says account_type=live sends every trade —
    entries, closes, and closes of a position it handed off — to the
    gateway FIRST, and books the ledger only when the broker took it;
  - the ledger's own refusals (cash, duplicate client_order_id) are checked
    BEFORE the broker, so a trade the ledger would refuse never reaches it;
  - a simulator run never touches the network;
  - only the trade's own run decides (never a position stamp); a live run
    keeps its positions when it stops; one live order per symbol at a time;
    no live order outside the market session;
  - live fleets are refused at creation unless every market has a usable
    live gateway, and never leveraged; the account type rides into each
    run's config snapshot.

All HTTP is faked; an unexpected request fails the test.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
import unittest
from unittest.mock import patch
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
        # Live orders are refused outside the session; most tests are about
        # routing, so the clock is pinned open (one test pins it shut).
        self._open = patch("markets.is_market_open", return_value=True)
        self._open.start()

    def tearDown(self):
        self._open.stop()
        super().tearDown()

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

    def test_live_order_outside_the_session_is_refused(self):
        """A market order after hours is queued by the broker while the
        ledger would book it at once: refuse instead."""
        run = self._run("live")
        patcher, calls = _patch_http(_webull_ok)
        with patch("markets.is_market_open", return_value=False), patcher:
            sig, skip = self._trade("buy", 5, run)
        self.assertIsNone(sig)
        self.assertIn("market is closed", skip)
        self.assertEqual(calls, [])
        self.assertEqual(self._signals(), [])

    def test_unowned_trades_are_never_routed_even_with_a_live_handoff_stamp(self):
        """Rules, resting orders, the trend module and the live rule path's
        own ledger write carry no run_id. Routing them on a position stamp
        double-sent a live rule's sell and sent simulator sells to the
        broker (review 2026-11-24) — only the trade's own run decides."""
        run = self._run("live")
        patcher, calls = _patch_http(lambda m, u, k: None)
        with patcher:
            self._trade("buy", 5, None)
            conn = database.get_db_connection()
            conn.cursor().execute(
                "UPDATE positions SET handoff_run_id = ? WHERE agent_id = ?",
                (run, self.agent_id))
            conn.commit()
            conn.close()
            sig, skip = self._trade("sell", 5, None)
        self.assertTrue(sig, skip)
        self.assertEqual(calls, [])

    def test_a_stopped_live_run_keeps_its_real_positions(self):
        """Released to the unowned book, a live run's shares would be closed
        by ledger-only paths (manual sell, orphan reclaim) and stay open at
        the broker. A simulator run still releases as before."""
        from trading_runs import release_positions
        live, sim = self._run("live"), self._run("simulator")
        patcher, _ = _patch_http(_webull_ok)
        with patcher:
            self._trade("buy", 2, live)
            self._trade("buy", 3, sim)
        conn = database.get_db_connection()
        cur = conn.cursor()
        release_positions(cur, live, self.agent_id)
        release_positions(cur, sim, self.agent_id)
        conn.commit()
        cur.execute("SELECT run_id, handoff_run_id, quantity FROM positions"
                    " WHERE agent_id = ? ORDER BY quantity", (self.agent_id,))
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        self.assertEqual(rows, [{"run_id": live, "handoff_run_id": None, "quantity": 2.0},
                                {"run_id": None, "handoff_run_id": sim, "quantity": 3.0}])

    def test_a_run_holding_positions_cannot_be_deleted(self):
        from trading_runs import delete_run
        run = self._run("live")
        patcher, _ = _patch_http(_webull_ok)
        with patcher:
            self._trade("buy", 2, run)
        conn = database.get_db_connection()
        conn.cursor().execute("UPDATE trading_runs SET status = 'stopped' WHERE id = ?", (run,))
        conn.commit()
        conn.close()
        with self.assertRaises(ValueError) as cm:
            delete_run(run, self.agent_id)
        self.assertIn("open positions", str(cm.exception))

    def test_two_closers_on_one_live_position_send_one_order(self):
        """The SL/TP watcher and the run cycle closing the same position at
        once: the first holds the live-order lock through the broker call
        and the ledger write, so the second's dry run sees nothing left to
        sell and never reaches the broker."""
        run = self._run("live")
        patcher, _ = _patch_http(_webull_ok)
        with patcher:
            self._trade("buy", 5, run)
        in_broker = threading.Event()
        places = []

        def slow(method, url, kwargs):
            if urlparse(url).path == PLACE:
                places.append(json.loads(kwargs["content"])["new_orders"][0]["side"])
                in_broker.set()
                time.sleep(0.3)
                return _FakeResponse(200, {"client_order_id": "c", "order_id": "W2"})
            return None

        results = []
        patcher, _ = _patch_http(slow)
        with patcher:
            t1 = threading.Thread(target=lambda: results.append(self._trade("sell", 5, run)))
            t1.start()
            in_broker.wait(5)
            t2 = threading.Thread(target=lambda: results.append(self._trade("sell", 5, run)))
            t2.start()
            t1.join(10)
            t2.join(10)
        self.assertEqual(places, ["SELL"], "the second close must not reach Webull")
        self.assertEqual(sorted(bool(r[0]) for r in results), [False, True])


    def test_broker_gets_the_size_the_ledger_books(self):
        """A stale watcher read asks to sell 10 while the run holds 5 (an
        armed exit already sold the rest): the ledger trims to 5, and the
        broker must get 5 — never 10."""
        run = self._run("live")
        patcher, calls = _patch_http(_webull_ok)
        with patcher:
            self._trade("buy", 5, run)
            sig, skip = self._trade("sell", 10, run)
        self.assertTrue(sig, skip)
        legs = _placed(calls)
        self.assertEqual([(leg["side"], float(leg["quantity"])) for leg in legs],
                         [("BUY", 5.0), ("SELL", 5.0)])

    def test_live_run_whose_flatten_keeps_failing_stays_stopping(self):
        """Past the flatten timeout a simulator run hands its position to the
        unowned book (positions_held). A live run must not: it stays
        `stopping`, still owning its real shares, and keeps retrying."""
        import run_engine
        run = self._run("live")
        patcher, _ = _patch_http(_webull_ok)
        with patcher:
            self._trade("buy", 5, run)
        conn = database.get_db_connection()
        conn.cursor().execute(
            "UPDATE trading_runs SET status = 'stopping', stop_flatten = 1,"
            " stopped_at = '2026-01-01T00:00:00Z' WHERE id = ?", (run,))
        conn.commit()
        cur = conn.cursor()
        cur.execute("SELECT * FROM trading_runs WHERE id = ?", (run,))
        row = dict(cur.fetchone())
        conn.close()
        out = {"stopping_finished": 0}
        patcher, _ = _patch_http(lambda m, u, k: _FakeResponse(
            417, {"error_code": "X", "message": "rejected"}))
        with patcher, patch.object(run_engine, "_alert_run") as alert:
            run_engine._control_stopping(row, out)
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT status FROM trading_runs WHERE id = ?", (run,))
        status = cur.fetchone()["status"]
        cur.execute("SELECT run_id, handoff_run_id FROM positions WHERE agent_id = ?",
                    (self.agent_id,))
        pos = dict(cur.fetchone())
        conn.close()
        self.assertEqual(status, "stopping")
        self.assertEqual(pos, {"run_id": run, "handoff_run_id": None})
        self.assertEqual(out["stopping_finished"], 0)
        self.assertTrue(alert.called, "the user is told the shares are still open")

    def test_a_close_over_the_cap_still_reaches_the_broker(self):
        """The $1,000 new-venue cap limits NEW risk. A position that grew past
        it (several entries, or a rise) must still close — refusing would
        trap real shares at the broker on every flatten and SL/TP exit."""
        run = self._run("live")
        patcher, calls = _patch_http(_webull_ok)
        with patcher:
            self._trade("buy", 6, run)            # $600
            self._trade("buy", 6, run)            # $600 more: 12 shares held
            sig, skip = self._trade("sell", 12, run, price=110.0)   # $1,320 close
        self.assertTrue(sig, skip)
        self.assertEqual([leg["side"] for leg in _placed(calls)], ["BUY", "BUY", "SELL"])

    def test_two_symbols_cannot_both_spend_the_last_cash(self):
        """Members on DIFFERENT symbols share the agent's cash: with $600
        left, two $500 buys at once must not both reach the broker."""
        conn = database.get_db_connection()
        conn.cursor().execute("UPDATE agents SET cash = 600 WHERE id = ?", (self.agent_id,))
        conn.commit()
        conn.close()
        run_a, run_b = self._run("live"), self._run("live")
        in_broker = threading.Event()
        places = []

        def slow(method, url, kwargs):
            if urlparse(url).path == PLACE:
                places.append(json.loads(kwargs["content"])["new_orders"][0]["symbol"])
                in_broker.set()
                time.sleep(0.3)
                return _FakeResponse(200, {"client_order_id": "c", "order_id": "W"})
            return None

        from automation import execute_paper_trade
        results = []

        def buy(run, sym):
            results.append(execute_paper_trade(self.agent_id, sym, "us-stock", "buy",
                                               5, 100.0, run_id=run))

        patcher, _ = _patch_http(slow)
        with patcher:
            t1 = threading.Thread(target=buy, args=(run_a, "AAPL"))
            t1.start()
            in_broker.wait(5)
            t2 = threading.Thread(target=buy, args=(run_b, "MSFT"))
            t2.start()
            t1.join(10)
            t2.join(10)
        self.assertEqual(places, ["AAPL"], "the second buy must be refused before the broker")
        self.assertIn("insufficient cash", [r[1] for r in results if not r[0]][0])

    def test_owner_stop_restamps_a_machine_stopping_run(self):
        """A live run stuck `stopping` under a machine reason (a below-cost
        long the long exit policy will not sell) must yield to the owner's
        own Stop, or the fleet can never finish."""
        from trading_runs import request_stop
        run = self._run("live")
        conn = database.get_db_connection()
        conn.cursor().execute("UPDATE trading_runs SET status = 'stopping', "
                              "status_reason = 'fleet_breaker' WHERE id = ?", (run,))
        conn.commit()
        conn.close()
        request_stop(run, self.agent_id, True, reason="fleet_stop_all")
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT status, status_reason FROM trading_runs WHERE id = ?", (run,))
        row = dict(cur.fetchone())
        conn.close()
        self.assertEqual(row, {"status": "stopping", "status_reason": "fleet_stop_all"})

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
