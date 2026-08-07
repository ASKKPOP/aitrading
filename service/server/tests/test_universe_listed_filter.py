"""Unlistable crypto symbols must not enter the research universe.

2026-08-07: ZBTUSDT produced 48 log failures across two days while consuming a
survivor slot and an LLM thesis in every research batch. It is not listed on
Hyperliquid, so it can never be priced and can never be built. Overnight, with
US equities closed, it was the ONLY unheld crypto candidate — so one dead
symbol was holding the fleet's last buildable slot.
"""
import unittest
from unittest.mock import patch

import symbol_research


class UniverseListedFilterTests(unittest.TestCase):
    def _universe(self):
        return [c["symbol"] for c in symbol_research.build_universe()
                if c["market"] == "crypto"]

    def test_an_unlistable_symbol_is_dropped(self):
        with patch("top_symbols.get_top_symbols",
                   return_value=[{"symbol": "BTCUSDT"}, {"symbol": "ZBTUSDT"}]), \
             patch("scanner.get_scanner_payload", return_value={}), \
             patch("price_fetcher.crypto_symbol_listed",
                   side_effect=lambda s: s != "ZBTUSDT"):
            got = self._universe()
        self.assertIn("BTCUSDT", got)
        self.assertNotIn("ZBTUSDT", got, "a symbol the feed cannot price is "
                                         "still eating a survivor slot")

    def test_it_fails_open_when_the_listed_set_is_unreadable(self):
        """A network hiccup must not empty the crypto universe."""
        with patch("top_symbols.get_top_symbols",
                   return_value=[{"symbol": "BTCUSDT"}, {"symbol": "ZBTUSDT"}]), \
             patch("scanner.get_scanner_payload", return_value={}), \
             patch("price_fetcher.crypto_symbol_listed",
                   side_effect=RuntimeError("venue down")):
            got = self._universe()
        self.assertIn("BTCUSDT", got)
        self.assertIn("ZBTUSDT", got, "an unreadable listed-set must leave the "
                                      "universe intact, not empty it")

    def test_it_fails_open_when_every_symbol_reads_unlisted(self):
        """If the check says NOTHING is listed, that is far likelier to be a
        broken read than a genuinely empty venue."""
        with patch("top_symbols.get_top_symbols",
                   return_value=[{"symbol": "BTCUSDT"}, {"symbol": "ETHUSDT"}]), \
             patch("scanner.get_scanner_payload", return_value={}), \
             patch("price_fetcher.crypto_symbol_listed", return_value=False):
            got = self._universe()
        self.assertEqual(sorted(got), ["BTCUSDT", "ETHUSDT"],
                         "an all-unlisted answer emptied the crypto universe")


if __name__ == "__main__":
    unittest.main()
