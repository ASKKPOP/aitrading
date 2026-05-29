"""Tests for bybit_feed.py — Bybit V5 linear perpetuals market data client."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import bybit_feed

# ─── helpers ─────────────────────────────────────────────────────────────────

def _bybit_envelope(result: dict, ret_code: int = 0, ret_msg: str = "OK") -> dict:
    return {"retCode": ret_code, "retMsg": ret_msg, "result": result, "time": 1700000000000}


def _ticker_list_item(
    symbol: str = "BTCUSDT",
    last_price: str = "67000.00",
    mark_price: str = "66990.00",
    price_24h_pct: str = "0.025",
    volume_24h: str = "150000000.00",
    open_interest: str = "85000.00",
) -> dict:
    return {
        "symbol": symbol,
        "lastPrice": last_price,
        "markPrice": mark_price,
        "price24hPcnt": price_24h_pct,
        "turnover24h": volume_24h,
        "openInterest": open_interest,
    }


def _mock_response(payload: dict, status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.raise_for_status = MagicMock(
        side_effect=None if status_code < 400 else Exception(f"HTTP {status_code}")
    )
    resp.json.return_value = payload
    return resp


# ─── constants ────────────────────────────────────────────────────────────────

class TopPairsConstantTests(unittest.TestCase):
    def test_top_20_pairs_has_20_entries(self) -> None:
        self.assertEqual(len(bybit_feed.TOP_20_PAIRS), 20)

    def test_top_20_pairs_all_usdt_suffixed(self) -> None:
        for pair in bybit_feed.TOP_20_PAIRS:
            self.assertTrue(pair.endswith("USDT"), f"{pair} does not end with USDT")

    def test_top_20_pairs_includes_btc_eth_sol(self) -> None:
        self.assertIn("BTCUSDT", bybit_feed.TOP_20_PAIRS)
        self.assertIn("ETHUSDT", bybit_feed.TOP_20_PAIRS)
        self.assertIn("SOLUSDT", bybit_feed.TOP_20_PAIRS)


# ─── fetch_bybit_ticker ───────────────────────────────────────────────────────

class FetchBybitTickerTests(unittest.TestCase):
    def test_returns_normalised_ticker_fields(self) -> None:
        payload = _bybit_envelope({"category": "linear", "list": [_ticker_list_item()]})
        with patch("bybit_feed.requests.get", return_value=_mock_response(payload)):
            result = bybit_feed.fetch_bybit_ticker("BTCUSDT")

        self.assertEqual(result["symbol"], "BTCUSDT")
        self.assertIn("last_price", result)
        self.assertIn("mark_price", result)
        self.assertIn("price_24h_pct", result)
        self.assertIn("volume_24h", result)
        self.assertIn("open_interest", result)

    def test_last_price_is_string(self) -> None:
        payload = _bybit_envelope({"category": "linear", "list": [_ticker_list_item(last_price="67000.00")]})
        with patch("bybit_feed.requests.get", return_value=_mock_response(payload)):
            result = bybit_feed.fetch_bybit_ticker("BTCUSDT")

        self.assertEqual(result["last_price"], "67000.00")

    def test_price_24h_pct_converted_to_percentage_string(self) -> None:
        # Bybit sends "0.025" meaning 2.5% — we convert to "2.50"
        payload = _bybit_envelope({"category": "linear", "list": [_ticker_list_item(price_24h_pct="0.025")]})
        with patch("bybit_feed.requests.get", return_value=_mock_response(payload)):
            result = bybit_feed.fetch_bybit_ticker("BTCUSDT")

        self.assertEqual(result["price_24h_pct"], "2.50")

    def test_negative_24h_pct_preserved(self) -> None:
        payload = _bybit_envelope({"category": "linear", "list": [_ticker_list_item(price_24h_pct="-0.0312")]})
        with patch("bybit_feed.requests.get", return_value=_mock_response(payload)):
            result = bybit_feed.fetch_bybit_ticker("BTCUSDT")

        self.assertEqual(result["price_24h_pct"], "-3.12")

    def test_raises_value_error_when_symbol_not_in_response(self) -> None:
        payload = _bybit_envelope({"category": "linear", "list": []})
        with patch("bybit_feed.requests.get", return_value=_mock_response(payload)):
            with self.assertRaises(ValueError):
                bybit_feed.fetch_bybit_ticker("BTCUSDT")

    def test_raises_runtime_error_on_bybit_non_zero_ret_code(self) -> None:
        payload = _bybit_envelope({}, ret_code=10001, ret_msg="Invalid symbol")
        with patch("bybit_feed.requests.get", return_value=_mock_response(payload)):
            with self.assertRaises(RuntimeError):
                bybit_feed.fetch_bybit_ticker("BADUSDT")

    def test_raises_on_http_error(self) -> None:
        resp = _mock_response({}, status_code=502)
        resp.raise_for_status.side_effect = Exception("HTTP 502")
        with patch("bybit_feed.requests.get", return_value=resp):
            with self.assertRaises(Exception):
                bybit_feed.fetch_bybit_ticker("BTCUSDT")

    def test_calls_bybit_v5_linear_endpoint(self) -> None:
        payload = _bybit_envelope({"category": "linear", "list": [_ticker_list_item()]})
        with patch("bybit_feed.requests.get", return_value=_mock_response(payload)) as mock_get:
            bybit_feed.fetch_bybit_ticker("BTCUSDT")

        url, = mock_get.call_args.args
        self.assertIn("api.bybit.com/v5/market/tickers", url)
        self.assertIn("category=linear", url)
        self.assertIn("symbol=BTCUSDT", url)


# ─── fetch_bybit_tickers ──────────────────────────────────────────────────────

class FetchBybitTickersTests(unittest.TestCase):
    def _make_payload(self, symbols: list[str]) -> dict:
        return _bybit_envelope({
            "category": "linear",
            "list": [_ticker_list_item(symbol=s) for s in symbols],
        })

    def test_returns_list_of_tickers(self) -> None:
        symbols = ["BTCUSDT", "ETHUSDT"]
        payload = self._make_payload(symbols)
        with patch("bybit_feed.requests.get", return_value=_mock_response(payload)):
            results = bybit_feed.fetch_bybit_tickers(symbols)

        self.assertEqual(len(results), 2)
        returned_symbols = {r["symbol"] for r in results}
        self.assertEqual(returned_symbols, set(symbols))

    def test_single_symbol_returns_one_item(self) -> None:
        payload = self._make_payload(["SOLUSDT"])
        with patch("bybit_feed.requests.get", return_value=_mock_response(payload)):
            results = bybit_feed.fetch_bybit_tickers(["SOLUSDT"])

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["symbol"], "SOLUSDT")

    def test_empty_symbols_returns_empty_list(self) -> None:
        results = bybit_feed.fetch_bybit_tickers([])
        self.assertEqual(results, [])

    def test_skips_symbols_missing_from_response(self) -> None:
        # Response only has BTC even though we asked for BTC+ETH
        payload = self._make_payload(["BTCUSDT"])
        with patch("bybit_feed.requests.get", return_value=_mock_response(payload)):
            results = bybit_feed.fetch_bybit_tickers(["BTCUSDT", "ETHUSDT"])

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["symbol"], "BTCUSDT")


if __name__ == "__main__":
    unittest.main()
