"""Tests for crypto_feed.py — OKX perpetuals market data client."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import crypto_feed

# ─── helpers ─────────────────────────────────────────────────────────────────

def _okx_envelope(data: list, code: str = "0", msg: str = "") -> dict:
    return {"code": code, "msg": msg, "data": data}


def _ticker_item(
    inst_id: str = "BTC-USDT-SWAP",
    last: str = "73779.0",
    open24h: str = "71000.0",
    vol_ccy24h: str = "150000000.0",
) -> dict:
    return {
        "instType": "SWAP",
        "instId": inst_id,
        "last": last,
        "lastSz": "0.01",
        "open24h": open24h,
        "high24h": "74000.0",
        "low24h": "72000.0",
        "volCcy24h": vol_ccy24h,
        "vol24h": "2000.0",
        "ts": "1700000000000",
        "sodUtc0": "72000.0",
        "sodUtc8": "72500.0",
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
        self.assertEqual(len(crypto_feed.TOP_20_PAIRS), 20)

    def test_top_20_pairs_all_usdt_suffixed(self) -> None:
        for pair in crypto_feed.TOP_20_PAIRS:
            self.assertTrue(pair.endswith("USDT"), f"{pair} does not end with USDT")

    def test_top_20_pairs_includes_btc_eth_sol(self) -> None:
        self.assertIn("BTCUSDT", crypto_feed.TOP_20_PAIRS)
        self.assertIn("ETHUSDT", crypto_feed.TOP_20_PAIRS)
        self.assertIn("SOLUSDT", crypto_feed.TOP_20_PAIRS)


# ─── fetch_ticker ─────────────────────────────────────────────────────────────

class FetchTickerTests(unittest.TestCase):
    def test_returns_normalised_ticker_fields(self) -> None:
        payload = _okx_envelope([_ticker_item()])
        with patch("crypto_feed.requests.get", return_value=_mock_response(payload)):
            result = crypto_feed.fetch_ticker("BTCUSDT")

        self.assertEqual(result["symbol"], "BTCUSDT")
        self.assertIn("last_price", result)
        self.assertIn("mark_price", result)
        self.assertIn("price_24h_pct", result)
        self.assertIn("volume_24h", result)
        self.assertIn("open_interest", result)

    def test_last_price_numeric(self) -> None:
        # last_price is cast to float (consistent with fetch_spot_ticker) —
        # consumers expect numeric prices, not OKX's raw strings.
        payload = _okx_envelope([_ticker_item(last="73779.0")])
        with patch("crypto_feed.requests.get", return_value=_mock_response(payload)):
            result = crypto_feed.fetch_ticker("BTCUSDT")

        self.assertEqual(result["last_price"], 73779.0)
        self.assertIsInstance(result["last_price"], float)

    def test_24h_pct_computed_from_open24h(self) -> None:
        # (73779 - 71000) / 71000 * 100 = 3.91...% ≈ 3.91
        payload = _okx_envelope([_ticker_item(last="73779.0", open24h="71000.0")])
        with patch("crypto_feed.requests.get", return_value=_mock_response(payload)):
            result = crypto_feed.fetch_ticker("BTCUSDT")

        pct = float(result["price_24h_pct"])
        self.assertAlmostEqual(pct, 3.91, places=1)

    def test_negative_24h_pct_when_price_fell(self) -> None:
        # (69000 - 71000) / 71000 * 100 = -2.81...%
        payload = _okx_envelope([_ticker_item(last="69000.0", open24h="71000.0")])
        with patch("crypto_feed.requests.get", return_value=_mock_response(payload)):
            result = crypto_feed.fetch_ticker("BTCUSDT")

        self.assertLess(float(result["price_24h_pct"]), 0)

    def test_raises_value_error_when_symbol_not_found(self) -> None:
        payload = _okx_envelope([])
        with patch("crypto_feed.requests.get", return_value=_mock_response(payload)):
            with self.assertRaises(ValueError):
                crypto_feed.fetch_ticker("BTCUSDT")

    def test_raises_runtime_error_on_okx_error_code(self) -> None:
        payload = _okx_envelope([], code="51001", msg="Instrument ID does not exist")
        with patch("crypto_feed.requests.get", return_value=_mock_response(payload)):
            with self.assertRaises(RuntimeError):
                crypto_feed.fetch_ticker("BTCUSDT")

    def test_raises_on_http_error(self) -> None:
        resp = _mock_response({}, status_code=503)
        resp.raise_for_status.side_effect = Exception("HTTP 503")
        with patch("crypto_feed.requests.get", return_value=resp):
            with self.assertRaises(Exception):
                crypto_feed.fetch_ticker("BTCUSDT")

    def test_calls_okx_endpoint(self) -> None:
        payload = _okx_envelope([_ticker_item()])
        with patch("crypto_feed.requests.get", return_value=_mock_response(payload)) as mock_get:
            crypto_feed.fetch_ticker("BTCUSDT")

        url = mock_get.call_args.args[0]
        self.assertIn("okx.com", url)

    def test_symbol_converted_from_btcusdt_to_okx_instid(self) -> None:
        # BTCUSDT → BTC-USDT-SWAP in OKX API call
        payload = _okx_envelope([_ticker_item(inst_id="BTC-USDT-SWAP")])
        with patch("crypto_feed.requests.get", return_value=_mock_response(payload)) as mock_get:
            crypto_feed.fetch_ticker("BTCUSDT")

        url = mock_get.call_args.args[0]
        self.assertIn("BTC-USDT-SWAP", url)


# ─── fetch_tickers ────────────────────────────────────────────────────────────

class FetchTickersTests(unittest.TestCase):
    def _make_payload(self, symbols: list[str]) -> dict:
        items = [_ticker_item(inst_id=f"{s.replace('USDT', '')}-USDT-SWAP") for s in symbols]
        return _okx_envelope(items)

    def test_returns_list_of_tickers(self) -> None:
        payload = self._make_payload(["BTCUSDT", "ETHUSDT"])
        with patch("crypto_feed.requests.get", return_value=_mock_response(payload)):
            results = crypto_feed.fetch_tickers(["BTCUSDT", "ETHUSDT"])

        self.assertEqual(len(results), 2)
        returned_symbols = {r["symbol"] for r in results}
        self.assertEqual(returned_symbols, {"BTCUSDT", "ETHUSDT"})

    def test_empty_symbols_returns_empty_list(self) -> None:
        results = crypto_feed.fetch_tickers([])
        self.assertEqual(results, [])

    def test_skips_symbols_missing_from_response(self) -> None:
        # Response only has BTC even though we asked for BTC+ETH
        payload = self._make_payload(["BTCUSDT"])
        with patch("crypto_feed.requests.get", return_value=_mock_response(payload)):
            results = crypto_feed.fetch_tickers(["BTCUSDT", "ETHUSDT"])

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["symbol"], "BTCUSDT")


class FetchCandlesPaginationTests(unittest.TestCase):
    """fetch_candles must chain OKX pages (max 300/call) for long windows."""

    @staticmethod
    def _candle_row(ts_ms: int) -> list:
        return [str(ts_ms), "100", "110", "90", "105", "1000", "0", "0", "1"]

    def test_single_page_under_300(self) -> None:
        day = 86_400_000
        rows = [self._candle_row(1_700_000_000_000 - i * day) for i in range(100)]
        with patch("crypto_feed.requests.get", return_value=_mock_response(_okx_envelope(rows))):
            candles = crypto_feed.fetch_candles("BTCUSDT", bar="1D", limit=100)
        self.assertEqual(len(candles), 100)
        self.assertLess(candles[0]["ts"], candles[-1]["ts"], "oldest-first ordering")

    def test_paginates_beyond_300(self) -> None:
        day = 86_400_000
        newest = 1_700_000_000_000
        page1 = [self._candle_row(newest - i * day) for i in range(300)]
        page2 = [self._candle_row(newest - (300 + i) * day) for i in range(100)]
        calls = []

        def fake_get(url, timeout=None):
            calls.append(url)
            return _mock_response(_okx_envelope(page1 if len(calls) == 1 else page2))

        with patch("crypto_feed.requests.get", side_effect=fake_get):
            candles = crypto_feed.fetch_candles("BTCUSDT", bar="1D", limit=400)

        self.assertEqual(len(calls), 2)
        self.assertIn("after=", calls[1], "second page must pass the `after` cursor")
        self.assertEqual(len(candles), 400)
        ts_list = [c["ts"] for c in candles]
        self.assertEqual(ts_list, sorted(ts_list), "merged pages stay oldest-first")
        self.assertEqual(len(set(ts_list)), 400, "no duplicate bars across pages")

    def test_stops_when_history_exhausted(self) -> None:
        day = 86_400_000
        rows = [self._candle_row(1_700_000_000_000 - i * day) for i in range(120)]
        with patch("crypto_feed.requests.get", return_value=_mock_response(_okx_envelope(rows))) as mock_get:
            candles = crypto_feed.fetch_candles("BTCUSDT", bar="1D", limit=400)
        # first page returned 120 < 300 requested → history exhausted, no second call
        self.assertEqual(mock_get.call_count, 1)
        self.assertEqual(len(candles), 120)


if __name__ == "__main__":
    unittest.main()
