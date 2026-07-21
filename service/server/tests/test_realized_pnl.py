"""Realized P&L stamping on closing legs (sell/cover).

Regression for "profit doesn't appear on /assets": no execution path ever
wrote signals.pnl / signals.exit_price, so realized profit vanished into
cash invisibly. Every executor (automation execute_paper_trade, the manual
/api/signals/realtime path, copy-trade follower fills) must stamp
pnl = (exit - avg_entry) * qty - exit_fee (sign-flipped for shorts) on the
closing signals row.
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
from fees import TRADE_FEE_RATE
from routes import create_app


class RealizedPnlTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())
        resp = self.client.post(
            "/api/claw/agents/selfRegister",
            json={"name": "pnl-agent", "password": "pw123", "initial_balance": 100000.0},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        self.agent_id = body["agent_id"]
        self.token = body["token"]

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _signal_row(self, signal_id: int) -> dict:
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT side, pnl, exit_price, fee_usd FROM signals WHERE signal_id = ?",
            (signal_id,),
        )
        row = dict(cursor.fetchone())
        conn.close()
        return row

    def _last_signal_rows(self, agent_id: int, n: int = 1) -> list[dict]:
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """SELECT side, pnl, exit_price, fee_usd FROM signals
               WHERE agent_id = ? AND message_type = 'operation'
               ORDER BY signal_id DESC LIMIT ?""",
            (agent_id, n),
        )
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return rows

    # ── automation executor ─────────────────────────────────────────────

    def test_paper_trade_sell_stamps_realized_pnl(self):
        from automation import execute_paper_trade
        buy_id, skip = execute_paper_trade(self.agent_id, "BTC", "crypto", "buy", 1.0, 100.0)
        self.assertIsNotNone(buy_id, skip)
        self.assertIsNone(self._signal_row(buy_id)["pnl"])

        sell_id, skip = execute_paper_trade(self.agent_id, "BTC", "crypto", "sell", 1.0, 110.0)
        self.assertIsNotNone(sell_id, skip)
        row = self._signal_row(sell_id)
        fee = 110.0 * 1.0 * TRADE_FEE_RATE
        self.assertAlmostEqual(row["pnl"], (110.0 - 100.0) * 1.0 - fee, places=6)
        self.assertAlmostEqual(row["exit_price"], 110.0, places=6)

    def test_paper_trade_cover_stamps_realized_pnl(self):
        from automation import execute_paper_trade
        short_id, skip = execute_paper_trade(self.agent_id, "BTC", "crypto", "short", 2.0, 100.0)
        self.assertIsNotNone(short_id, skip)
        self.assertIsNone(self._signal_row(short_id)["pnl"])

        cover_id, skip = execute_paper_trade(self.agent_id, "BTC", "crypto", "cover", 2.0, 90.0)
        self.assertIsNotNone(cover_id, skip)
        row = self._signal_row(cover_id)
        fee = 90.0 * 2.0 * TRADE_FEE_RATE
        self.assertAlmostEqual(row["pnl"], (100.0 - 90.0) * 2.0 - fee, places=6)
        self.assertAlmostEqual(row["exit_price"], 90.0, places=6)

    def test_paper_trade_partial_sell_uses_average_entry(self):
        from automation import execute_paper_trade
        execute_paper_trade(self.agent_id, "ETH", "crypto", "buy", 1.0, 100.0)
        execute_paper_trade(self.agent_id, "ETH", "crypto", "buy", 1.0, 200.0)  # avg 150
        sell_id, skip = execute_paper_trade(self.agent_id, "ETH", "crypto", "sell", 0.5, 180.0)
        self.assertIsNotNone(sell_id, skip)
        row = self._signal_row(sell_id)
        fee = 180.0 * 0.5 * TRADE_FEE_RATE
        self.assertAlmostEqual(row["pnl"], (180.0 - 150.0) * 0.5 - fee, places=6)

    def test_paper_trade_losing_sell_stamps_negative_pnl(self):
        from automation import execute_paper_trade
        execute_paper_trade(self.agent_id, "SOL", "crypto", "buy", 10.0, 80.0)
        sell_id, skip = execute_paper_trade(self.agent_id, "SOL", "crypto", "sell", 10.0, 79.0)
        self.assertIsNotNone(sell_id, skip)
        row = self._signal_row(sell_id)
        fee = 79.0 * 10.0 * TRADE_FEE_RATE
        self.assertAlmostEqual(row["pnl"], (79.0 - 80.0) * 10.0 - fee, places=6)
        self.assertLess(row["pnl"], 0)

    # ── manual /api/signals/realtime path ───────────────────────────────

    def _realtime(self, action: str, price: float, qty: float, token: str = None):
        # crypto is server-priced: the endpoint always fetches a live quote,
        # so pin the fetcher to the test's price for deterministic P&L math.
        with patch("price_fetcher.get_price_from_market", return_value=price):
            resp = self.client.post(
                "/api/signals/realtime",
                json={"market": "crypto", "action": action, "symbol": "BTC",
                      "price": price, "quantity": qty, "executed_at": "now"},
                headers={"Authorization": f"Bearer {token or self.token}"},
            )
        self.assertEqual(resp.status_code, 200, resp.text)
        return resp.json()

    def test_manual_sell_stamps_pnl_and_fee(self):
        self._realtime("buy", 100.0, 1.0)
        body = self._realtime("sell", 120.0, 1.0)
        row = self._signal_row(body["signal_id"])
        fee = 120.0 * 1.0 * TRADE_FEE_RATE
        self.assertAlmostEqual(row["pnl"], (120.0 - 100.0) * 1.0 - fee, places=6)
        self.assertAlmostEqual(row["exit_price"], 120.0, places=6)
        self.assertAlmostEqual(row["fee_usd"], fee, places=6)

    def test_manual_cover_stamps_pnl(self):
        self._realtime("short", 100.0, 1.0)
        body = self._realtime("cover", 95.0, 1.0)
        row = self._signal_row(body["signal_id"])
        fee = 95.0 * 1.0 * TRADE_FEE_RATE
        self.assertAlmostEqual(row["pnl"], (100.0 - 95.0) * 1.0 - fee, places=6)

    def test_manual_buy_leaves_pnl_null(self):
        body = self._realtime("buy", 100.0, 1.0)
        row = self._signal_row(body["signal_id"])
        self.assertIsNone(row["pnl"])
        self.assertIsNone(row["exit_price"])
        self.assertAlmostEqual(row["fee_usd"], 100.0 * TRADE_FEE_RATE, places=6)

    # ── copy-trade follower fills ───────────────────────────────────────

    def test_follower_sell_stamps_pnl_against_follower_entry(self):
        resp = self.client.post(
            "/api/claw/agents/selfRegister",
            json={"name": "pnl-follower", "password": "pw123", "initial_balance": 100000.0},
        )
        assert resp.status_code == 200, resp.text
        follower = resp.json()
        resp = self.client.post(
            "/api/signals/follow",
            json={"leader_id": self.agent_id},
            headers={"Authorization": f"Bearer {follower['token']}"},
        )
        self.assertEqual(resp.status_code, 200, resp.text)

        self._realtime("buy", 100.0, 1.0)   # leader buys; follower mirrors @100
        self._realtime("sell", 110.0, 1.0)  # leader sells; follower mirrors @110

        rows = self._last_signal_rows(follower["agent_id"], 2)
        sell_row = next(r for r in rows if r["side"] == "sell")
        fee = 110.0 * 1.0 * TRADE_FEE_RATE
        self.assertAlmostEqual(sell_row["pnl"], (110.0 - 100.0) * 1.0 - fee, places=6)
        self.assertAlmostEqual(sell_row["exit_price"], 110.0, places=6)

    # ── the trades API surfaces it ──────────────────────────────────────

    def test_positions_trades_endpoint_returns_pnl(self):
        from automation import execute_paper_trade
        execute_paper_trade(self.agent_id, "BTC", "crypto", "buy", 1.0, 100.0)
        execute_paper_trade(self.agent_id, "BTC", "crypto", "sell", 1.0, 110.0)
        resp = self.client.get(
            "/api/positions/trades",
            headers={"Authorization": f"Bearer {self.token}"},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        trades = resp.json()["trades"]
        sell = next(t for t in trades if t["side"] == "sell")
        self.assertIsNotNone(sell["pnl"])
        self.assertGreater(sell["pnl"], 0)


if __name__ == "__main__":
    unittest.main()
