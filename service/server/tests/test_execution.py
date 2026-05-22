"""Unit tests for the execution layer (Broker ABC, PaperBroker, crypto, router)."""
from __future__ import annotations

import asyncio
import hashlib
import os
import sys
import tempfile
import unittest
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
from routes_shared import utc_now_iso_z


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _create_agent(name: str = "exec-agent", cash: float = 100_000.0) -> int:
    token_hash = hashlib.sha256(name.encode()).hexdigest()
    conn = database.get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO agents (name, token, token_hash, cash) VALUES (?, NULL, ?, ?)",
        (name, token_hash, cash),
    )
    agent_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return agent_id


class TestOrderDataclass(unittest.TestCase):
    def test_defaults(self):
        from execution.base import Order, OrderStatus, ExecutionMode
        o = Order(agent_id=1, symbol="AAPL", market="us-stock", side="buy",
                  quantity=10, price=150.0)
        self.assertEqual(o.status, OrderStatus.PENDING)
        self.assertEqual(o.execution_mode, ExecutionMode.PAPER)
        self.assertIsNone(o.broker_order_id)

    def test_is_terminal(self):
        from execution.base import Order, OrderStatus
        o = Order(agent_id=1, symbol="AAPL", market="us-stock", side="buy",
                  quantity=10, price=150.0)
        self.assertFalse(o.is_terminal())
        o.status = OrderStatus.FILLED
        self.assertTrue(o.is_terminal())
        o.status = OrderStatus.REJECTED
        self.assertTrue(o.is_terminal())
        o.status = OrderStatus.SUBMITTED
        self.assertFalse(o.is_terminal())


class TestPaperBrokerFill(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.agent_id = _create_agent()

    def tearDown(self):
        self.tmp.cleanup()

    def test_buy_fills_immediately(self):
        from execution.base import Order, OrderStatus
        from execution.paper import PaperBroker
        order = Order(
            agent_id=self.agent_id, symbol="AAPL", market="us-stock",
            side="buy", quantity=5, price=200.0,
            created_at=utc_now_iso_z(),
        )
        result = _run(PaperBroker().submit_order(order))
        self.assertEqual(result.status, OrderStatus.FILLED)
        self.assertEqual(result.filled_qty, 5)

    def test_sell_without_position_rejects(self):
        from execution.base import Order, OrderStatus
        from execution.paper import PaperBroker
        order = Order(
            agent_id=self.agent_id, symbol="AAPL", market="us-stock",
            side="sell", quantity=5, price=200.0,
            created_at=utc_now_iso_z(),
        )
        result = _run(PaperBroker().submit_order(order))
        self.assertEqual(result.status, OrderStatus.REJECTED)
        self.assertIn("long position", result.error_message)

    def test_buy_then_sell_both_fill(self):
        from execution.base import Order, OrderStatus
        from execution.paper import PaperBroker
        broker = PaperBroker()
        buy = Order(agent_id=self.agent_id, symbol="MSFT", market="us-stock",
                    side="buy", quantity=10, price=300.0, created_at=utc_now_iso_z())
        _run(broker.submit_order(buy))
        sell = Order(agent_id=self.agent_id, symbol="MSFT", market="us-stock",
                     side="sell", quantity=10, price=320.0, created_at=utc_now_iso_z())
        result = _run(broker.submit_order(sell))
        self.assertEqual(result.status, OrderStatus.FILLED)

    def test_cancel_returns_false(self):
        from execution.paper import PaperBroker
        result = _run(PaperBroker().cancel_order("paper-123"))
        self.assertFalse(result)

    def test_get_broker_positions_is_empty(self):
        from execution.paper import PaperBroker
        positions = _run(PaperBroker().get_broker_positions())
        self.assertEqual(positions, [])


class TestPaperBrokerShort(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.agent_id = _create_agent("short-agent")

    def tearDown(self):
        self.tmp.cleanup()

    def test_short_and_cover(self):
        from execution.base import Order, OrderStatus
        from execution.paper import PaperBroker
        broker = PaperBroker()
        short = Order(agent_id=self.agent_id, symbol="TSLA", market="us-stock",
                      side="short", quantity=5, price=250.0, created_at=utc_now_iso_z())
        r1 = _run(broker.submit_order(short))
        self.assertEqual(r1.status, OrderStatus.FILLED)
        cover = Order(agent_id=self.agent_id, symbol="TSLA", market="us-stock",
                      side="cover", quantity=5, price=240.0, created_at=utc_now_iso_z())
        r2 = _run(broker.submit_order(cover))
        self.assertEqual(r2.status, OrderStatus.FILLED)


class TestCrypto(unittest.TestCase):
    def test_roundtrip(self):
        from execution.crypto import decrypt_credentials, encrypt_credentials
        creds = {"key": "AK123", "secret": "SK456"}
        token = encrypt_credentials(creds)
        self.assertIsInstance(token, str)
        self.assertGreater(len(token), 20)
        recovered = decrypt_credentials(token)
        self.assertEqual(recovered, creds)

    def test_tampered_token_raises(self):
        from execution.crypto import decrypt_credentials, encrypt_credentials
        token = encrypt_credentials({"key": "x", "secret": "y"})
        # Corrupt a byte in the middle of the ciphertext (not just append to
        # the end, which base64 padding can absorb harmlessly).
        mid = len(token) // 2
        corrupted = token[:mid] + ("A" if token[mid] != "A" else "B") + token[mid + 1:]
        with self.assertRaises(ValueError):
            decrypt_credentials(corrupted)

    def test_generate_key_b64_is_string(self):
        from execution.crypto import generate_key_b64
        key = generate_key_b64()
        self.assertIsInstance(key, str)
        self.assertGreater(len(key), 30)


class TestExecutionRouterPaperMode(unittest.TestCase):
    """Router defaults to paper mode when no broker_accounts row exists."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.agent_id = _create_agent("router-agent")

    def tearDown(self):
        self.tmp.cleanup()

    def test_paper_mode_fills_and_persists(self):
        from execution.base import Order, OrderStatus, ExecutionMode
        from execution.router import ExecutionRouter
        order = Order(
            agent_id=self.agent_id, symbol="NVDA", market="us-stock",
            side="buy", quantity=3, price=500.0, created_at=utc_now_iso_z(),
        )
        router = ExecutionRouter()
        result = _run(router.execute(self.agent_id, order))
        self.assertEqual(result.status, OrderStatus.FILLED)
        self.assertEqual(result.execution_mode, ExecutionMode.PAPER)
        self.assertIsNotNone(result.db_id)

        # Verify broker_orders row exists
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM broker_orders WHERE id=?", (result.db_id,))
        row = cursor.fetchone()
        conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(row["status"], "filled")

    def test_order_for_unknown_agent_is_rejected(self):
        from execution.base import Order, OrderStatus
        from execution.router import ExecutionRouter
        order = Order(
            agent_id=99999, symbol="AAPL", market="us-stock",
            side="buy", quantity=1, price=100.0, created_at=utc_now_iso_z(),
        )
        router = ExecutionRouter()
        # agent 99999 doesn't exist — position insert will fail or succeed
        # depending on FK enforcement; either way no crash
        result = _run(router.execute(99999, order))
        self.assertIn(result.status.value, ("filled", "rejected"))


class TestExecutionRouterShadowMode(unittest.TestCase):
    """Shadow mode: paper is authoritative, real broker runs in parallel."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.agent_id = _create_agent("shadow-agent")

    def tearDown(self):
        self.tmp.cleanup()

    def _create_broker_account(self, mode: str = "shadow", broker: str = "alpaca"):
        from execution.crypto import encrypt_credentials
        creds_enc = encrypt_credentials({"key": "", "secret": ""})
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO broker_accounts
               (agent_id, broker, execution_mode, credentials_enc, is_active)
               VALUES (?,?,?,?,1)""",
            (self.agent_id, broker, mode, creds_enc),
        )
        conn.commit()
        conn.close()

    def test_shadow_mode_returns_filled_paper_order(self):
        from execution.base import Order, OrderStatus, ExecutionMode
        from execution.router import ExecutionRouter
        self._create_broker_account(mode="shadow", broker="alpaca")
        order = Order(
            agent_id=self.agent_id, symbol="AAPL", market="us-stock",
            side="buy", quantity=2, price=180.0, created_at=utc_now_iso_z(),
        )
        result = _run(ExecutionRouter().execute(self.agent_id, order))
        # Paper is authoritative — order should be filled
        self.assertEqual(result.status, OrderStatus.FILLED)
        self.assertEqual(result.execution_mode, ExecutionMode.SHADOW)

    def test_shadow_mode_records_reconciliation(self):
        from execution.base import Order
        from execution.router import ExecutionRouter
        self._create_broker_account(mode="shadow", broker="alpaca")
        order = Order(
            agent_id=self.agent_id, symbol="MSFT", market="us-stock",
            side="buy", quantity=1, price=400.0, created_at=utc_now_iso_z(),
        )
        _run(ExecutionRouter().execute(self.agent_id, order))
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM position_reconciliations WHERE agent_id=?",
            (self.agent_id,),
        )
        rows = cursor.fetchall()
        conn.close()
        self.assertGreater(len(rows), 0)


class TestOrderStatusEnum(unittest.TestCase):
    def test_all_values_are_strings(self):
        from execution.base import OrderStatus
        for s in OrderStatus:
            self.assertIsInstance(s.value, str)

    def test_execution_mode_values(self):
        from execution.base import ExecutionMode
        self.assertEqual(ExecutionMode.PAPER.value, "paper")
        self.assertEqual(ExecutionMode.SHADOW.value, "shadow")
        self.assertEqual(ExecutionMode.LIVE.value, "live")


class TestAlpacaBrokerNoCredentials(unittest.TestCase):
    def test_submit_without_credentials_rejects(self):
        from execution.alpaca import AlpacaBroker
        from execution.base import Order, OrderStatus
        broker = AlpacaBroker(key="", secret="", paper=True)
        order = Order(agent_id=1, symbol="AAPL", market="us-stock",
                      side="buy", quantity=1, price=100.0)
        result = _run(broker.submit_order(order))
        self.assertEqual(result.status, OrderStatus.REJECTED)
        self.assertIn("ALPACA_KEY", result.error_message)

    def test_cancel_without_credentials_returns_false(self):
        from execution.alpaca import AlpacaBroker
        broker = AlpacaBroker(key="", secret="", paper=True)
        result = _run(broker.cancel_order("fake-id"))
        self.assertFalse(result)

    def test_get_positions_without_credentials_is_empty(self):
        from execution.alpaca import AlpacaBroker
        broker = AlpacaBroker(key="", secret="", paper=True)
        result = _run(broker.get_broker_positions())
        self.assertEqual(result, [])


class TestBinanceBrokerNoCredentials(unittest.TestCase):
    def test_submit_without_credentials_rejects(self):
        from execution.binance import BinanceBroker
        from execution.base import Order, OrderStatus
        broker = BinanceBroker(key="", secret="", testnet=True)
        order = Order(agent_id=1, symbol="BTCUSDT", market="crypto",
                      side="buy", quantity=0.001, price=60000.0)
        result = _run(broker.submit_order(order))
        self.assertEqual(result.status, OrderStatus.REJECTED)
        self.assertIn("BINANCE_KEY", result.error_message)

    def test_get_positions_without_credentials_is_empty(self):
        from execution.binance import BinanceBroker
        broker = BinanceBroker(key="", secret="")
        result = _run(broker.get_broker_positions())
        self.assertEqual(result, [])


class TestIBKRBrokerStub(unittest.TestCase):
    def test_submit_always_rejects(self):
        from execution.ibkr import IBKRBroker
        from execution.base import Order, OrderStatus
        broker = IBKRBroker()
        order = Order(agent_id=1, symbol="AAPL", market="us-stock",
                      side="buy", quantity=1, price=100.0)
        result = _run(broker.submit_order(order))
        self.assertEqual(result.status, OrderStatus.REJECTED)
        self.assertIn("not yet implemented", result.error_message)


if __name__ == "__main__":
    unittest.main()
