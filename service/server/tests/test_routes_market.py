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

    # --- Accept-Language localizes the response on the way out (Tier B) ---
    # The English payload built above is shared and cached; the handler must
    # translate the free text per request from the Accept-Language header while
    # leaving enums/numbers untouched. Catalogue strings keep this LLM-free.

    _MACRO_LOCALIZABLE = {
        "available": True,
        "verdict": "defensive",
        "meta": {"summary": "Defensive pressure dominates the current macro snapshot."},
        "signals": [{
            "id": "btc_trend", "label": "BTC trend", "status": "bullish",
            "explanation": "BTC momentum is mixed.", "value": 1.2,
        }],
    }

    def test_macro_localized_for_korean_request(self) -> None:
        from market_i18n_data import MARKET_PHRASES
        with patch("routes_market.get_macro_signals_payload",
                   return_value=dict(self._MACRO_LOCALIZABLE)):
            resp = self.client.get("/api/market-intel/macro-signals",
                                   headers={"Accept-Language": "ko"})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["meta"]["summary"],
                         MARKET_PHRASES["Defensive pressure dominates the current macro snapshot."]["ko"])
        sig = body["signals"][0]
        self.assertEqual(sig["label"], MARKET_PHRASES["BTC trend"]["ko"])
        self.assertEqual(sig["explanation"], MARKET_PHRASES["BTC momentum is mixed."]["ko"])
        # Enum + number are the frontend's to map / render — left raw.
        self.assertEqual(body["verdict"], "defensive")
        self.assertEqual(sig["status"], "bullish")
        self.assertEqual(sig["value"], 1.2)

    def test_macro_english_request_unchanged(self) -> None:
        with patch("routes_market.get_macro_signals_payload",
                   return_value=dict(self._MACRO_LOCALIZABLE)):
            resp = self.client.get("/api/market-intel/macro-signals",
                                   headers={"Accept-Language": "en"})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["meta"]["summary"],
                         "Defensive pressure dominates the current macro snapshot.")
        self.assertEqual(body["signals"][0]["explanation"], "BTC momentum is mixed.")

    # A snapshot row persisted with a bare NaN literal (json.loads restores it
    # as a float) 500'd every stocks endpoint in prod on 2026-07-29. The payload
    # must be scrubbed to null before it reaches the allow_nan=False renderer.

    def test_featured_stocks_with_nan_indicator_returns_200_and_null(self) -> None:
        payload = {"available": True, "items": [
            {"symbol": "AAPL", "analysis": {
                "moving_averages": {"ma20": 317.04, "ma50": float("nan")},
                "sigma_daily_pct": float("nan"),
            }},
        ]}
        with patch("routes_market.get_featured_stock_analysis_payload", return_value=payload):
            resp = self.client.get("/api/market-intel/stocks/featured?limit=10")
        self.assertEqual(resp.status_code, 200)
        analysis = resp.json()["items"][0]["analysis"]
        self.assertIsNone(analysis["moving_averages"]["ma50"])
        self.assertIsNone(analysis["sigma_daily_pct"])
        self.assertEqual(analysis["moving_averages"]["ma20"], 317.04)

    def test_stock_latest_with_nan_indicator_returns_200(self) -> None:
        payload = {"symbol": "AAPL", "analysis": {"reversal_1m_pct": float("nan")}}
        with patch("routes_market.get_stock_analysis_latest_payload", return_value=payload):
            resp = self.client.get("/api/market-intel/stocks/AAPL/latest")
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.json()["analysis"]["reversal_1m_pct"])

    def test_stock_history_with_nan_indicator_returns_200(self) -> None:
        payload = {"symbol": "AAPL", "history": [
            {"analysis_id": "AAPL:1", "analysis": {"moving_averages": {"ma200": float("nan")}}},
        ]}
        with patch("routes_market.get_stock_analysis_history_payload", return_value=payload):
            resp = self.client.get("/api/market-intel/stocks/AAPL/history?limit=6")
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.json()["history"][0]["analysis"]["moving_averages"]["ma200"])


# ─── Bybit futures market endpoints ──────────────────────────────────────────

_STUB_BTCUSDT = {
    "symbol": "BTCUSDT",
    "last_price": "67000.00",
    "mark_price": "66990.00",
    "price_24h_pct": "2.50",
    "volume_24h": "150000000.00",
    "open_interest": "85000.00",
}

_STUB_TICKERS = [
    _STUB_BTCUSDT,
    {
        "symbol": "ETHUSDT",
        "last_price": "3500.00",
        "mark_price": "3499.00",
        "price_24h_pct": "-1.20",
        "volume_24h": "80000000.00",
        "open_interest": "45000.00",
    },
]


class CryptoMarketRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())

    def tearDown(self) -> None:
        self.tmp.cleanup()

    # --- GET /api/markets/crypto/tickers ---

    def test_bybit_tickers_returns_list(self) -> None:
        with patch("routes_market.fetch_tickers", return_value=_STUB_TICKERS):
            resp = self.client.get("/api/markets/crypto/tickers")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("tickers", body)
        self.assertEqual(len(body["tickers"]), 2)

    def test_bybit_tickers_includes_symbol_and_price_fields(self) -> None:
        with patch("routes_market.fetch_tickers", return_value=_STUB_TICKERS):
            resp = self.client.get("/api/markets/crypto/tickers")
        ticker = resp.json()["tickers"][0]
        self.assertIn("symbol", ticker)
        self.assertIn("last_price", ticker)
        self.assertIn("price_24h_pct", ticker)

    def test_bybit_tickers_upstream_error_returns_503(self) -> None:
        with patch("routes_market.fetch_tickers", side_effect=RuntimeError("Bybit down")):
            resp = self.client.get("/api/markets/crypto/tickers")
        self.assertEqual(resp.status_code, 503)

    # --- GET /api/markets/crypto/ticker?symbol=BTCUSDT ---

    def test_bybit_single_ticker_returns_ticker(self) -> None:
        with patch("routes_market.fetch_ticker", return_value=_STUB_BTCUSDT):
            resp = self.client.get("/api/markets/crypto/ticker?symbol=BTCUSDT")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["symbol"], "BTCUSDT")
        self.assertIn("last_price", body)

    def test_bybit_single_ticker_symbol_required(self) -> None:
        resp = self.client.get("/api/markets/crypto/ticker")
        self.assertEqual(resp.status_code, 422)

    def test_bybit_single_ticker_not_found_returns_404(self) -> None:
        with patch("routes_market.fetch_ticker", side_effect=ValueError("not found")):
            resp = self.client.get("/api/markets/crypto/ticker?symbol=FAKEUSDT")
        self.assertEqual(resp.status_code, 404)

    def test_bybit_single_ticker_upstream_error_returns_503(self) -> None:
        with patch("routes_market.fetch_ticker", side_effect=RuntimeError("Bybit error")):
            resp = self.client.get("/api/markets/crypto/ticker?symbol=BTCUSDT")
        self.assertEqual(resp.status_code, 503)


class SuggestSymbolTests(unittest.TestCase):
    """POST /api/markets/suggest-symbol — the AI picks which symbol to trade."""

    CANDIDATES = [
        {"symbol": "ETHUSDT", "last_price": 1860.0, "volume_24h_usd": 5.6e9},
        {"symbol": "BTCUSDT", "last_price": 64000.0, "volume_24h_usd": 4.6e9},
        {"symbol": "SOLUSDT", "last_price": 76.0, "volume_24h_usd": 5.1e8,
         "mention_rate_per_hour": 12.5},
    ]

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())
        r = self.client.post("/api/claw/agents/selfRegister",
                             json={"name": "pick-agent", "password": "pw123",
                                   "initial_balance": 10000.0})
        self.h = {"Authorization": f"Bearer {r.json()['token']}"}

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _call(self, llm_reply: str, configured: bool = True):
        with patch("top_symbols.get_top_symbols", return_value=list(self.CANDIDATES)), \
                patch("llm_client.llm_configured", return_value=configured), \
                patch("llm_client.generate_text", return_value=llm_reply):
            return self.client.post("/api/markets/suggest-symbol", headers=self.h)

    def test_requires_an_agent_token(self):
        self.assertEqual(
            self.client.post("/api/markets/suggest-symbol").status_code, 401)

    def test_returns_the_models_choice_with_its_reason(self):
        r = self._call('{"symbol":"BTC","reason":"deepest liquidity"}')
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        # the model picked BTC over the volume leader ETH — the ranking must not
        # override a genuine choice
        self.assertEqual(body["symbol"], "BTC")
        self.assertEqual(body["reason"], "deepest liquidity")
        self.assertTrue(body["by_ai"])

    def test_a_symbol_outside_the_candidate_list_is_refused(self):
        """The model may rank, never invent — an unlisted symbol would create a
        run on something the price feed cannot quote."""
        r = self._call('{"symbol":"DOGECOIN9000","reason":"to the moon"}')
        body = r.json()
        self.assertEqual(body["symbol"], "ETH", "must fall back to the ranking leader")
        self.assertFalse(body["by_ai"])
        self.assertEqual(body["reason"], "")

    def test_unparseable_reply_falls_back_without_erroring(self):
        r = self._call("I think maybe Bitcoin? Not sure.")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["symbol"], "ETH")
        self.assertFalse(r.json()["by_ai"])

    def test_prose_wrapped_json_is_still_parsed(self):
        r = self._call('Sure! {"symbol":"SOL","reason":"rising mentions"} hope that helps')
        self.assertEqual(r.json()["symbol"], "SOL")
        self.assertTrue(r.json()["by_ai"])

    def test_no_llm_configured_returns_the_ranking_leader_not_an_error(self):
        r = self._call("", configured=False)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["symbol"], "ETH")
        self.assertFalse(r.json()["by_ai"])

    def test_no_candidates_is_a_503_not_a_bad_pick(self):
        with patch("top_symbols.get_top_symbols", return_value=[]):
            r = self.client.post("/api/markets/suggest-symbol", headers=self.h)
        self.assertEqual(r.status_code, 503)

    def test_the_call_runs_under_the_calling_agents_identity(self):
        """Spend must land in that agent's AI usage rather than floating free,
        so assert on the context the LLM call actually sees."""
        from llm_client import current_llm_context
        seen = {}

        def _capture(*_a, **kw):
            ctx = current_llm_context()
            seen["agent_id"] = ctx.agent_id if ctx else None
            seen["tier"] = kw.get("tier")
            return '{"symbol":"BTC","reason":"x"}'

        with patch("top_symbols.get_top_symbols", return_value=list(self.CANDIDATES)), \
                patch("llm_client.llm_configured", return_value=True), \
                patch("llm_client.generate_text", side_effect=_capture):
            r = self.client.post("/api/markets/suggest-symbol", headers=self.h)

        self.assertEqual(r.status_code, 200)
        self.assertIsNotNone(seen.get("agent_id"), "call must carry the agent identity")
        # brief tier, not the 30-90s analyst pipeline — a slow picker is useless
        self.assertEqual(seen.get("tier"), "brief")


if __name__ == "__main__":
    unittest.main()
