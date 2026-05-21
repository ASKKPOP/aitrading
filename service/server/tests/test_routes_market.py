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
from routes import create_app

# Stub return values for external market-data calls
_STUB_MARKETS = [{"id": "1", "slug": "test-market", "question": "Will it?"}]
_STUB_OVERVIEW = {"summary": "flat", "signals": []}
_STUB_NEWS = {"articles": []}
_STUB_MACRO = {"signals": []}
_STUB_ETF = {"flows": []}
_STUB_STOCKS = {"stocks": []}
_STUB_STOCK_LATEST = {"symbol": "AAPL", "signal": "buy"}
_STUB_STOCK_HISTORY = {"symbol": "AAPL", "history": []}


class MarketRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())

    def tearDown(self) -> None:
        self.tmp.cleanup()

    # --- GET /health ---

    def test_health_check(self) -> None:
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "ok")

    # --- GET /api/markets/polymarket ---

    def test_polymarket_list_returns_markets(self) -> None:
        with patch("routes_market.list_polymarket_markets", return_value=_STUB_MARKETS):
            resp = self.client.get("/api/markets/polymarket")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("markets", body)
        self.assertEqual(body["count"], 1)

    def test_polymarket_list_empty(self) -> None:
        with patch("routes_market.list_polymarket_markets", return_value=[]):
            resp = self.client.get("/api/markets/polymarket")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["count"], 0)

    def test_polymarket_list_limit_param_clamped(self) -> None:
        with patch("routes_market.list_polymarket_markets", return_value=[]) as mock_fn:
            self.client.get("/api/markets/polymarket?limit=999")
            # limit should be clamped to 100
            called_limit = mock_fn.call_args.kwargs.get("limit") or mock_fn.call_args.args[0]
            self.assertLessEqual(called_limit, 100)

    # --- GET /api/markets/polymarket/{slug_or_id} ---

    def test_polymarket_detail_found(self) -> None:
        stub = {"id": "1", "slug": "test-market", "outcomes": []}
        with patch("routes_market.get_polymarket_market_detail", return_value=stub):
            resp = self.client.get("/api/markets/polymarket/test-market")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["slug"], "test-market")

    def test_polymarket_detail_not_found_returns_404(self) -> None:
        with patch("routes_market.get_polymarket_market_detail", return_value=None):
            resp = self.client.get("/api/markets/polymarket/no-such-market")
        self.assertEqual(resp.status_code, 404)

    # --- /api/market-intel/* ---

    def test_market_intel_overview(self) -> None:
        with patch("routes_market.get_market_intel_overview", return_value=_STUB_OVERVIEW):
            resp = self.client.get("/api/market-intel/overview")
        self.assertEqual(resp.status_code, 200)

    def test_market_intel_news(self) -> None:
        with patch("routes_market.get_market_news_payload", return_value=_STUB_NEWS):
            resp = self.client.get("/api/market-intel/news")
        self.assertEqual(resp.status_code, 200)

    def test_market_intel_macro_signals(self) -> None:
        with patch("routes_market.get_macro_signals_payload", return_value=_STUB_MACRO):
            resp = self.client.get("/api/market-intel/macro-signals")
        self.assertEqual(resp.status_code, 200)

    def test_market_intel_etf_flows(self) -> None:
        with patch("routes_market.get_etf_flows_payload", return_value=_STUB_ETF):
            resp = self.client.get("/api/market-intel/etf-flows")
        self.assertEqual(resp.status_code, 200)

    def test_market_intel_featured_stocks(self) -> None:
        with patch("routes_market.get_featured_stock_analysis_payload", return_value=_STUB_STOCKS):
            resp = self.client.get("/api/market-intel/stocks/featured")
        self.assertEqual(resp.status_code, 200)

    def test_market_intel_stock_latest(self) -> None:
        with patch("routes_market.get_stock_analysis_latest_payload", return_value=_STUB_STOCK_LATEST):
            resp = self.client.get("/api/market-intel/stocks/AAPL/latest")
        self.assertEqual(resp.status_code, 200)

    def test_market_intel_stock_history(self) -> None:
        with patch("routes_market.get_stock_analysis_history_payload", return_value=_STUB_STOCK_HISTORY):
            resp = self.client.get("/api/market-intel/stocks/AAPL/history")
        self.assertEqual(resp.status_code, 200)


if __name__ == "__main__":
    unittest.main()
