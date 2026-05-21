"""Tests for the backtest engine (backtest.py) and its API endpoint."""

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
from backtest import run_backtest
from routes import create_app

# A Tuesday within NYSE market hours — safe historical timestamp for us-stock.
_TS1 = "2024-01-02T15:00:00Z"
_TS2 = "2024-01-02T15:10:00Z"
_TS3 = "2024-01-02T15:20:00Z"
_TS4 = "2024-01-02T15:30:00Z"


def _register_agent(client: TestClient, name: str = "bt-agent") -> dict:
    resp = client.post(
        "/api/claw/agents/selfRegister",
        json={"name": name, "password": "pw", "initial_balance": 100000.0},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _buy(client: TestClient, token: str, symbol: str, price: float, qty: float, ts: str) -> None:
    with patch.dict(os.environ, {"ALLOW_SYNC_PRICE_FETCH_IN_API": "false"}):
        resp = client.post(
            "/api/signals/realtime",
            json={
                "market": "us-stock",
                "action": "buy",
                "symbol": symbol,
                "price": price,
                "quantity": qty,
                "executed_at": ts,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200, resp.text


def _sell(client: TestClient, token: str, symbol: str, price: float, qty: float, ts: str) -> None:
    with patch.dict(os.environ, {"ALLOW_SYNC_PRICE_FETCH_IN_API": "false"}):
        resp = client.post(
            "/api/signals/realtime",
            json={
                "market": "us-stock",
                "action": "sell",
                "symbol": symbol,
                "price": price,
                "quantity": qty,
                "executed_at": ts,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200, resp.text


class BacktestEngineTests(unittest.TestCase):
    """Unit tests that exercise the backtest engine directly (no HTTP)."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())
        self.agent = _register_agent(self.client)
        self.token = self.agent["token"]
        self.agent_id = self.agent["agent_id"]

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_no_trades_returns_initial_cash(self) -> None:
        result = run_backtest(self.agent_id, "2020-01-01T00:00:00Z", "2020-12-31T23:59:59Z")
        self.assertEqual(result.initial_cash, 100_000.0)
        self.assertEqual(result.final_value, 100_000.0)
        self.assertEqual(result.trade_count, 0)
        self.assertEqual(result.total_return_pct, 0.0)

    def test_buy_then_sell_at_profit(self) -> None:
        _buy(self.client, self.token, "AAPL", 100.0, 10.0, _TS1)
        _sell(self.client, self.token, "AAPL", 110.0, 10.0, _TS2)

        result = run_backtest(
            self.agent_id,
            "2024-01-01T00:00:00Z",
            "2024-12-31T23:59:59Z",
            initial_cash=100_000.0,
        )
        self.assertEqual(result.trade_count, 1)
        self.assertEqual(result.winning_trades, 1)
        self.assertEqual(result.losing_trades, 0)
        self.assertGreater(result.final_value, 100_000.0)
        self.assertGreater(result.total_return_pct, 0.0)

    def test_buy_then_sell_at_loss(self) -> None:
        _buy(self.client, self.token, "AAPL", 100.0, 10.0, _TS1)
        _sell(self.client, self.token, "AAPL", 90.0, 10.0, _TS2)

        result = run_backtest(
            self.agent_id,
            "2024-01-01T00:00:00Z",
            "2024-12-31T23:59:59Z",
            initial_cash=100_000.0,
        )
        self.assertEqual(result.trade_count, 1)
        self.assertEqual(result.winning_trades, 0)
        self.assertEqual(result.losing_trades, 1)
        self.assertLess(result.final_value, 100_000.0)
        self.assertLess(result.total_return_pct, 0.0)

    def test_open_position_reflected_in_final_value(self) -> None:
        # Buy but don't sell — open position should use last known price
        _buy(self.client, self.token, "AAPL", 150.0, 10.0, _TS1)

        result = run_backtest(
            self.agent_id,
            "2024-01-01T00:00:00Z",
            "2024-12-31T23:59:59Z",
        )
        self.assertEqual(result.trade_count, 0)  # no closed trades
        self.assertEqual(len(result.open_positions), 1)
        pos = result.open_positions[0]
        self.assertEqual(pos["symbol"], "AAPL")
        self.assertEqual(pos["direction"], "long")

    def test_multiple_symbols_tracked_independently(self) -> None:
        _buy(self.client, self.token, "AAPL", 100.0, 5.0, _TS1)
        _buy(self.client, self.token, "MSFT", 200.0, 3.0, _TS2)
        _sell(self.client, self.token, "AAPL", 120.0, 5.0, _TS3)  # win
        _sell(self.client, self.token, "MSFT", 180.0, 3.0, _TS4)  # loss

        result = run_backtest(
            self.agent_id,
            "2024-01-01T00:00:00Z",
            "2024-12-31T23:59:59Z",
        )
        self.assertEqual(result.trade_count, 2)
        self.assertEqual(result.winning_trades, 1)
        self.assertEqual(result.losing_trades, 1)

    def test_win_rate_calculation(self) -> None:
        # Two wins, one loss
        _buy(self.client, self.token, "AAPL", 100.0, 1.0, _TS1)
        _sell(self.client, self.token, "AAPL", 110.0, 1.0, _TS2)
        _buy(self.client, self.token, "AAPL", 100.0, 1.0, _TS3)
        _sell(self.client, self.token, "AAPL", 90.0, 1.0, _TS4)

        result = run_backtest(
            self.agent_id,
            "2024-01-01T00:00:00Z",
            "2024-12-31T23:59:59Z",
        )
        self.assertEqual(result.trade_count, 2)
        self.assertAlmostEqual(result.win_rate, 0.5, places=3)

    def test_curve_starts_at_initial_cash(self) -> None:
        _buy(self.client, self.token, "AAPL", 100.0, 1.0, _TS1)
        result = run_backtest(
            self.agent_id,
            "2024-01-01T00:00:00Z",
            "2024-12-31T23:59:59Z",
            initial_cash=50_000.0,
        )
        self.assertEqual(result.curve[0].portfolio_value, 50_000.0)

    def test_date_filter_excludes_out_of_range_trades(self) -> None:
        _buy(self.client, self.token, "AAPL", 100.0, 1.0, _TS1)
        _sell(self.client, self.token, "AAPL", 120.0, 1.0, _TS2)

        # Window that excludes both trades
        result = run_backtest(
            self.agent_id,
            "2025-01-01T00:00:00Z",
            "2025-12-31T23:59:59Z",
        )
        self.assertEqual(result.trade_count, 0)

    def test_market_filter(self) -> None:
        _buy(self.client, self.token, "AAPL", 100.0, 1.0, _TS1)
        _sell(self.client, self.token, "AAPL", 110.0, 1.0, _TS2)

        result_stock = run_backtest(
            self.agent_id,
            "2024-01-01T00:00:00Z",
            "2024-12-31T23:59:59Z",
            market="us-stock",
        )
        result_crypto = run_backtest(
            self.agent_id,
            "2024-01-01T00:00:00Z",
            "2024-12-31T23:59:59Z",
            market="crypto",
        )
        self.assertEqual(result_stock.trade_count, 1)
        self.assertEqual(result_crypto.trade_count, 0)

    def test_symbol_filter(self) -> None:
        _buy(self.client, self.token, "AAPL", 100.0, 1.0, _TS1)
        _sell(self.client, self.token, "AAPL", 110.0, 1.0, _TS2)

        result_aapl = run_backtest(
            self.agent_id,
            "2024-01-01T00:00:00Z",
            "2024-12-31T23:59:59Z",
            symbol="AAPL",
        )
        result_msft = run_backtest(
            self.agent_id,
            "2024-01-01T00:00:00Z",
            "2024-12-31T23:59:59Z",
            symbol="MSFT",
        )
        self.assertEqual(result_aapl.trade_count, 1)
        self.assertEqual(result_msft.trade_count, 0)


class BacktestEndpointTests(unittest.TestCase):
    """Integration tests for GET /api/research/backtest."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())
        self.agent = _register_agent(self.client, name="ep-agent")
        self.agent_id = self.agent["agent_id"]
        self.token = self.agent["token"]

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _url(self, **kwargs) -> str:
        base = f"/api/research/backtest?agent_id={self.agent_id}&start_at=2024-01-01T00:00:00Z&end_at=2024-12-31T23:59:59Z"
        for k, v in kwargs.items():
            base += f"&{k}={v}"
        return base

    def test_endpoint_returns_200(self) -> None:
        resp = self.client.get(self._url())
        self.assertEqual(resp.status_code, 200)

    def test_response_has_required_keys(self) -> None:
        resp = self.client.get(self._url())
        body = resp.json()
        for key in ("agent_id", "start_at", "end_at", "summary", "closed_trades", "open_positions", "curve"):
            self.assertIn(key, body)

    def test_summary_has_required_fields(self) -> None:
        resp = self.client.get(self._url())
        summary = resp.json()["summary"]
        for field in ("initial_cash", "final_value", "total_return_pct", "max_drawdown_pct",
                      "trade_count", "winning_trades", "losing_trades", "win_rate", "sharpe_ratio"):
            self.assertIn(field, summary)

    def test_empty_result_for_no_trades(self) -> None:
        resp = self.client.get(self._url())
        body = resp.json()
        self.assertEqual(body["summary"]["trade_count"], 0)
        self.assertEqual(body["summary"]["total_return_pct"], 0.0)

    def test_initial_cash_param(self) -> None:
        resp = self.client.get(self._url(initial_cash=50000))
        self.assertEqual(resp.json()["summary"]["initial_cash"], 50000.0)

    def test_invalid_initial_cash_rejected(self) -> None:
        resp = self.client.get(self._url(initial_cash=-1))
        self.assertEqual(resp.status_code, 400)

    def test_endpoint_reflects_actual_trade(self) -> None:
        _buy(self.client, self.token, "AAPL", 100.0, 10.0, _TS1)
        _sell(self.client, self.token, "AAPL", 110.0, 10.0, _TS2)

        resp = self.client.get(self._url())
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["summary"]["trade_count"], 1)
        self.assertGreater(body["summary"]["final_value"], 100_000.0)
        self.assertEqual(len(body["closed_trades"]), 1)
        self.assertGreater(len(body["curve"]), 1)

    def test_curve_first_point_equals_initial_cash(self) -> None:
        _buy(self.client, self.token, "AAPL", 100.0, 1.0, _TS1)
        resp = self.client.get(self._url())
        curve = resp.json()["curve"]
        self.assertGreater(len(curve), 0)
        self.assertEqual(curve[0]["portfolio_value"], 100_000.0)


if __name__ == "__main__":
    unittest.main()
