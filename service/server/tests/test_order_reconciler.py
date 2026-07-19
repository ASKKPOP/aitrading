"""Broker-order reconciler — confirming the final state of SUBMITTED orders.

The invariant: the platform wrote the ledger at the REQUESTED size on submit;
this sweep records what the broker actually did and alerts on divergence, but
never mutates positions or cash — detection, not correction.
"""
from __future__ import annotations

import asyncio
import hashlib
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
from routes_shared import utc_now_iso_z


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class _ReconcilerTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO agents (name, token, token_hash, cash) VALUES (?,NULL,?,?)",
            ("rec-agent", hashlib.sha256(b"rec").hexdigest(), 100_000.0),
        )
        self.agent_id = cursor.lastrowid
        conn.commit()
        conn.close()

    def tearDown(self):
        self.tmp.cleanup()

    def _add_account(self, broker="alpaca"):
        from execution.crypto import encrypt_credentials
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO broker_accounts
               (agent_id, broker, execution_mode, credentials_enc, is_active, created_at, updated_at)
               VALUES (?,?,?,?,1,?,?)""",
            (self.agent_id, broker, "live",
             encrypt_credentials({"key": "k", "secret": "s"}),
             utc_now_iso_z(), utc_now_iso_z()),
        )
        conn.commit()
        conn.close()

    def _add_order(self, status="submitted", broker="alpaca", mode="live",
                   qty=10.0, broker_order_id="BO-1"):
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO broker_orders
               (agent_id, symbol, market, side, quantity, price, status,
                execution_mode, broker, broker_order_id, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (self.agent_id, "AAPL", "us-stock", "buy", qty, 190.0, status,
             mode, broker, broker_order_id, utc_now_iso_z()),
        )
        order_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return order_id

    def _order_row(self, order_id):
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM broker_orders WHERE id = ?", (order_id,))
        row = dict(cursor.fetchone())
        conn.close()
        return row

    def _tick(self, broker_answer):
        """Run one sweep with the adapter's get_order_status stubbed."""
        from execution.gateway import reconcile_orders_tick

        class _Stub:
            broker_name = "alpaca"
            async def get_order_status(self, broker_order_id, symbol=""):
                return broker_answer
        with patch("execution.gateway._broker_for", return_value=_Stub()), \
             patch("alerts.send_alert") as alert:
            out = reconcile_orders_tick()
        return out, alert


class TestSweepDecisions(_ReconcilerTestCase):
    def test_empty_db_is_a_free_noop(self):
        from execution.gateway import reconcile_orders_tick
        with patch("execution.gateway._broker_for") as bf:
            out = reconcile_orders_tick()
        self.assertEqual(out["checked"], 0)
        bf.assert_not_called()

    def test_paper_orders_are_never_looked_up(self):
        from execution.gateway import reconcile_orders_tick
        self._add_order(broker="paper")
        with patch("execution.gateway._broker_for") as bf:
            out = reconcile_orders_tick()
        self.assertEqual(out["checked"], 0)
        bf.assert_not_called()

    def test_still_open_order_is_left_untouched(self):
        from execution.base import OrderStatus
        self._add_account()
        oid = self._add_order()
        out, alert = self._tick({"status": OrderStatus.SUBMITTED,
                                 "filled_qty": None, "avg_price": None})
        self.assertEqual(out["still_open"], 1)
        self.assertEqual(self._order_row(oid)["status"], "submitted")
        alert.assert_not_called()

    def test_clean_full_fill_settles_without_alert(self):
        from execution.base import OrderStatus
        self._add_account()
        oid = self._add_order(qty=10.0)
        out, alert = self._tick({"status": OrderStatus.FILLED,
                                 "filled_qty": 10.0, "avg_price": 190.5})
        self.assertEqual((out["settled"], out["drift"]), (1, 0))
        row = self._order_row(oid)
        self.assertEqual(row["status"], "filled")
        self.assertAlmostEqual(float(row["filled_qty"]), 10.0)
        self.assertIsNotNone(row["filled_at"])
        alert.assert_not_called()

    def test_partial_fill_records_broker_qty_and_alerts(self):
        """The ledger assumed 10; the broker filled 4. quantity stays 10
        (requested), filled_qty records the truth, and the owner is told."""
        from execution.base import OrderStatus
        self._add_account()
        oid = self._add_order(qty=10.0)
        out, alert = self._tick({"status": OrderStatus.PARTIAL_FILL,
                                 "filled_qty": 4.0, "avg_price": 190.0})
        self.assertEqual(out["drift"], 1)
        row = self._order_row(oid)
        self.assertEqual(row["status"], "partial_fill")
        self.assertAlmostEqual(float(row["filled_qty"]), 4.0)
        self.assertAlmostEqual(float(row["quantity"]), 10.0, msg="requested size untouched")
        alert.assert_called_once()
        self.assertEqual(alert.call_args[0][1], "order_drift")
        self.assertEqual(alert.call_args[1]["dedupe_key"], f"order_drift:{oid}")

    def test_cancelled_after_submit_alerts(self):
        from execution.base import OrderStatus
        self._add_account()
        self._add_order()
        out, alert = self._tick({"status": OrderStatus.CANCELLED,
                                 "filled_qty": 0.0, "avg_price": None})
        self.assertEqual(out["drift"], 1)
        alert.assert_called_once()
        self.assertIn("cancelled", alert.call_args[0][3])

    def test_shadow_drift_is_recorded_but_not_alerted(self):
        """Shadow's ledger is authoritative by design — sandbox divergence is
        expected and journalled, not an emergency for the user."""
        from execution.base import OrderStatus
        self._add_account()
        oid = self._add_order(mode="shadow")
        out, alert = self._tick({"status": OrderStatus.CANCELLED,
                                 "filled_qty": 0.0, "avg_price": None})
        self.assertEqual(out["settled"], 1)
        self.assertEqual(out["drift"], 0)
        self.assertEqual(self._order_row(oid)["status"], "cancelled")
        alert.assert_not_called()

    def test_failed_lookup_leaves_the_order_for_next_sweep(self):
        self._add_account()
        oid = self._add_order()
        out, alert = self._tick(None)
        self.assertEqual(out["lookup_failed"], 1)
        self.assertEqual(self._order_row(oid)["status"], "submitted")
        alert.assert_not_called()

    def test_broker_changed_since_submit_skips_the_order(self):
        """The order went to alpaca but the agent's active account is now
        binance — asking binance about an alpaca order id is nonsense."""
        self._add_account(broker="binance")
        oid = self._add_order(broker="alpaca")
        out, _ = self._tick({"status": None})
        self.assertEqual(out["lookup_failed"], 1)
        self.assertEqual(self._order_row(oid)["status"], "submitted")

    def test_positions_and_cash_are_never_touched(self):
        """The reconciler detects; it must not correct money math."""
        from execution.base import OrderStatus
        self._add_account()
        self._add_order(qty=10.0)
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT cash FROM agents WHERE id = ?", (self.agent_id,))
        cash_before = dict(cursor.fetchone())["cash"]
        conn.close()
        self._tick({"status": OrderStatus.PARTIAL_FILL, "filled_qty": 4.0,
                    "avg_price": None})
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT cash FROM agents WHERE id = ?", (self.agent_id,))
        cash_after = dict(cursor.fetchone())["cash"]
        cursor.execute("SELECT COUNT(*) AS n FROM positions WHERE agent_id = ?",
                       (self.agent_id,))
        positions = dict(cursor.fetchone())["n"]
        conn.close()
        self.assertEqual(cash_before, cash_after)
        self.assertEqual(positions, 0)


class TestAdapterStatusParsing(unittest.TestCase):
    def test_alpaca_maps_terminal_states(self):
        from execution.alpaca import AlpacaBroker
        from execution.base import OrderStatus

        class _Resp:
            status_code = 200
            def json(self):
                return {"status": "partially_filled", "filled_qty": "3",
                        "filled_avg_price": "190.25"}
        class _Client:
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False
            async def get(self, *a, **k): return _Resp()
        broker = AlpacaBroker(key="k", secret="s", paper=True)
        with patch("execution.alpaca.httpx.AsyncClient", return_value=_Client()):
            st = _run(broker.get_order_status("abc"))
        self.assertEqual(st["status"], OrderStatus.PARTIAL_FILL)
        self.assertAlmostEqual(st["filled_qty"], 3.0)
        self.assertAlmostEqual(st["avg_price"], 190.25)

    def test_binance_requires_symbol_and_uses_submit_normalisation(self):
        from execution.binance import BinanceBroker
        from execution.base import OrderStatus
        broker = BinanceBroker(key="k", secret="s", testnet=True)
        self.assertIsNone(_run(broker.get_order_status("1", symbol="")))

        seen = {}
        class _Resp:
            status_code = 200
            def json(self):
                return {"status": "FILLED", "executedQty": "0.5",
                        "cummulativeQuoteQty": "25000"}
        class _Client:
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False
            async def get(self, url, params=None, **k):
                seen.update(params or {})
                return _Resp()
        with patch("execution.binance.httpx.AsyncClient", return_value=_Client()):
            st = _run(broker.get_order_status("77", symbol="BTC/USDT"))
        self.assertEqual(seen["symbol"], "BTCUSDT",
                         "must match submit_order's normalisation exactly")
        self.assertEqual(st["status"], OrderStatus.FILLED)
        self.assertAlmostEqual(st["avg_price"], 50000.0)

    def test_ibkr_partial_inference_from_cum_fill(self):
        from execution.ibkr import IBKRBroker
        from execution.base import OrderStatus

        class _Resp:
            status_code = 200
            def json(self):
                return {"order_status": "Submitted", "cum_fill": "2",
                        "average_price": "190.1"}
        class _Client:
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False
            async def get(self, *a, **k): return _Resp()
        broker = IBKRBroker(gateway_url="https://gw/v1/api", account_id="DU1")
        with patch.object(broker, "_client", return_value=_Client()):
            st = _run(broker.get_order_status("42"))
        self.assertEqual(st["status"], OrderStatus.PARTIAL_FILL)
        self.assertAlmostEqual(st["filled_qty"], 2.0)

    def test_paper_broker_has_no_lookup(self):
        from execution.paper import PaperBroker
        self.assertIsNone(_run(PaperBroker().get_order_status("x")))


if __name__ == "__main__":
    unittest.main()
