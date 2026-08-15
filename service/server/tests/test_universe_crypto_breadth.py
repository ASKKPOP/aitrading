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

    def test_the_volume_prefilter_is_not_the_binding_ceiling(self):
        """The 2026-08-07 widening raised build_universe's own slice to 50 but
        stopped at `_VOLUME_CANDIDATES = 20` — the pre-filter that actually
        binds, sized for the top-5 UI widget ("Plan 11 F1") and reused as the
        discovery channel for a 25-slot fleet.

        Measured on prod 2026-08-15 against the live OKX/Hyperliquid feeds:
        of the top 20 by volume only 8 were priceable, so the whole research
        universe was 10 crypto symbols against us-stock 126 — and 12
        consecutive batches each produced exactly 5 crypto theses. On a
        Saturday (crypto is the only open market) fleet 34 exhausted that
        pool with $50k of a $100k budget idle: the ranker had 5 candidates
        for 5 slots and made no choice at all, accepting HYPEUSDT at
        final_score 0.30. Counterfactual, same live feeds: cap 60 -> 21
        priceable. The ranking costs no extra network calls — the OKX tickers
        response already carries all ~431 rows.

        This widens CHOICE, not exposure: the survivor caps and quality gates
        still govern what is actually taken."""
        fake = [{"instId": f"C{i:03d}-USDT-SWAP", "volCcy24h": str(1000 - i),
                 "last": "1.0"} for i in range(200)]
        with patch("crypto_feed._okx_get", return_value=fake), \
             patch("top_symbols._priceable_bases", return_value=None), \
             patch("top_symbols._mention_rates", return_value={}):
            top_symbols._cache["items"] = []          # bypass the 5-min cache
            top_symbols._cache["at"] = 0.0
            rows = top_symbols.get_top_symbols(50)
        self.assertGreaterEqual(
            len(rows), 50,
            "get_top_symbols(50) is still pre-cut to _VOLUME_CANDIDATES "
            f"{top_symbols._VOLUME_CANDIDATES} before the priceable filter — "
            "the fleet's discovery channel is pinned at the UI widget's scale")

    def test_the_ui_widget_still_gets_exactly_five(self):
        """TOP_SYMBOLS_LIMIT is the widget's contract; widening the fleet's
        discovery channel must not change what the widget renders."""
        fake = [{"instId": f"C{i:03d}-USDT-SWAP", "volCcy24h": str(1000 - i),
                 "last": "1.0"} for i in range(200)]
        with patch("crypto_feed._okx_get", return_value=fake), \
             patch("top_symbols._priceable_bases", return_value=None), \
             patch("top_symbols._mention_rates", return_value={}):
            top_symbols._cache["items"] = []
            top_symbols._cache["at"] = 0.0
            rows = top_symbols.get_top_symbols()
        self.assertEqual(len(rows), top_symbols.TOP_SYMBOLS_LIMIT)

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
