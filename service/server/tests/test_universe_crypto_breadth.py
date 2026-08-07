"""build_universe must ask for the crypto breadth it slices for.

2026-08-07: `get_top_symbols()` defaults to 5 (TOP_SYMBOLS_LIMIT, sized for a
UI widget). build_universe called it bare and then sliced `[:50]`, so the slice
was a no-op and crypto discovery was pinned at five symbols — against us-stock
72, futures 21, forex 30, and this module's own "~198 symbols" docstring.
"""
import unittest
from unittest.mock import patch

import symbol_research
import top_symbols


class CryptoBreadthTests(unittest.TestCase):
    def test_it_requests_more_than_the_widget_default(self):
        seen = {}

        def _spy(limit=top_symbols.TOP_SYMBOLS_LIMIT):
            seen["limit"] = limit
            return [{"symbol": f"C{i}USDT"} for i in range(limit)]

        with patch("top_symbols.get_top_symbols", side_effect=_spy), \
             patch("scanner.get_scanner_payload", return_value={}), \
             patch("price_fetcher.crypto_symbol_listed", return_value=True):
            got = [c["symbol"] for c in symbol_research.build_universe()
                   if c["market"] == "crypto"]
        self.assertGreater(seen.get("limit", 0), top_symbols.TOP_SYMBOLS_LIMIT,
                           "build_universe is still taking the UI widget's "
                           "5-symbol default")
        self.assertGreater(len(got), top_symbols.TOP_SYMBOLS_LIMIT)

    def test_the_slice_still_bounds_the_result(self):
        """The limit must not become unbounded — the slice is the ceiling."""
        with patch("top_symbols.get_top_symbols",
                   return_value=[{"symbol": f"C{i}USDT"} for i in range(400)]), \
             patch("scanner.get_scanner_payload", return_value={}), \
             patch("price_fetcher.crypto_symbol_listed", return_value=True):
            got = [c["symbol"] for c in symbol_research.build_universe()
                   if c["market"] == "crypto"]
        self.assertLessEqual(len(got), 50)

    def test_a_dead_source_still_falls_back(self):
        with patch("top_symbols.get_top_symbols",
                   side_effect=RuntimeError("venue down")), \
             patch("scanner.get_scanner_payload", return_value={}), \
             patch("price_fetcher.crypto_symbol_listed", return_value=True):
            got = [c["symbol"] for c in symbol_research.build_universe()
                   if c["market"] == "crypto"]
        self.assertIn("BTCUSDT", got, "the hardcoded fallback must survive")


if __name__ == "__main__":
    unittest.main()
