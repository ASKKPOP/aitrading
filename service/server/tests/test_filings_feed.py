"""filings_feed.py — SEC EDGAR Form 4 insider activity -> smart-money score.

Pipeline feed #5 (research/SWING_SIGNAL_STACK.md §2). All HTTP is patched;
the fixtures mirror shapes verified live against data.sec.gov on 2026-08-30.

The load-bearing rule under test: only open-market codes P (purchase) and
S (sale) carry conviction. Measured on live NVDA/TSLA filings, the bulk of
Form 4 rows are A (grants), G (gifts), M (option exercise) and F (tax
withholding) — scoring those as "insiders are buying" would invert the
signal, so they must score nothing at all.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import filings_feed


TICKERS = {
    "0": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA CORP"},
    "1": {"cik_str": 1318605, "ticker": "TSLA", "title": "Tesla, Inc."},
}


def _submissions(forms):
    return {
        "filings": {
            "recent": {
                "form": [f[0] for f in forms],
                "filingDate": [f[1] for f in forms],
                "accessionNumber": [f[2] for f in forms],
                "primaryDocument": [f[3] for f in forms],
            }
        }
    }


def _form4_xml(transactions, owner="DOE JANE"):
    rows = "".join(
        f"""<nonDerivativeTransaction>
              <transactionCoding><transactionCode>{code}</transactionCode></transactionCoding>
              <transactionAmounts>
                <transactionShares><value>{shares}</value></transactionShares>
                <transactionPricePerShare><value>{price}</value></transactionPricePerShare>
              </transactionAmounts>
            </nonDerivativeTransaction>"""
        for code, shares, price in transactions
    )
    return f"""<?xml version="1.0"?>
    <ownershipDocument>
      <reportingOwner><reportingOwnerId><rptOwnerName>{owner}</rptOwnerName></reportingOwnerId></reportingOwner>
      <nonDerivativeTable>{rows}</nonDerivativeTable>
    </ownershipDocument>"""


class InsiderScoreTest(unittest.TestCase):
    def setUp(self):
        filings_feed.reset_caches()

    def _run(self, forms, docs, symbol="NVDA", today="2026-08-30"):
        def fake_get_json(url, *a, **k):
            if "company_tickers" in url:
                return TICKERS
            if "submissions" in url:
                return _submissions(forms)
            raise AssertionError(f"unexpected json url {url}")

        def fake_get_text(url, *a, **k):
            for key, xml in docs.items():
                if key in url:
                    return xml
            raise AssertionError(f"unexpected doc url {url}")

        with patch.object(filings_feed, "_get_json", fake_get_json), \
             patch.object(filings_feed, "_get_text", fake_get_text):
            return filings_feed.insider_read(symbol, today=today)

    def test_net_buying_scores_positive(self):
        read = self._run(
            [("4", "2026-08-20", "0001-26-000001", "x/f1.xml")],
            {"f1.xml": _form4_xml([("P", "1000", "100")])},
        )
        self.assertEqual(read["score"], 100.0)
        self.assertEqual(read["buy_usd"], 100000.0)
        self.assertEqual(read["sell_usd"], 0.0)
        self.assertEqual(read["transactions"], 1)

    def test_net_selling_scores_negative_but_capped(self):
        # Base-rate cap (2026-09-02): sells-only used to score -100 and 71%
        # of live readings pinned there — routine compensation liquidation
        # is not a -100 signal. Sells-only now reads the -20 floor.
        read = self._run(
            [("4", "2026-08-20", "0001-26-000001", "x/f1.xml")],
            {"f1.xml": _form4_xml([("S", "1000", "100")])},
        )
        self.assertEqual(read["score"], -20.0)

    def test_mildly_net_selling_above_the_cap_is_untouched(self):
        # (10k-20k)/30k*100 = -33.3 raw -> capped to -20; but (10k-15k)/25k
        # = -20 exactly sits ON the floor, and anything shallower passes
        # through unchanged: (10k-12k)/22k*100 = -9.09.
        read = self._run(
            [("4", "2026-08-20", "0001-26-000001", "x/f1.xml")],
            {"f1.xml": _form4_xml([("P", "100", "100"), ("S", "120", "100")])},
        )
        self.assertEqual(read["score"], -9.09)

    def test_score_is_value_weighted_not_count_weighted(self):
        read = self._run(
            [("4", "2026-08-20", "0001-26-000001", "x/f1.xml")],
            {"f1.xml": _form4_xml([("P", "300", "100"), ("S", "100", "100")])},
        )
        self.assertEqual(read["buy_usd"], 30000.0)
        self.assertEqual(read["sell_usd"], 10000.0)
        self.assertEqual(read["score"], 50.0)  # (30k-10k)/40k * 100

    def test_grants_gifts_and_exercises_are_not_conviction(self):
        """A/G/M/F rows are compensation mechanics, not open-market trades."""
        read = self._run(
            [("4", "2026-08-20", "0001-26-000001", "x/f1.xml")],
            {"f1.xml": _form4_xml([
                ("A", "5000", "0"), ("G", "500000", "0"),
                ("M", "1000", "10"), ("F", "400", "100"),
            ])},
        )
        self.assertIsNone(read["score"])  # no coverage, NOT neutral zero
        self.assertEqual(read["transactions"], 0)
        self.assertEqual(read["skipped_codes"]["A"], 1)
        self.assertEqual(read["skipped_codes"]["G"], 1)

    def test_no_coverage_is_none_so_the_weight_renormalizes_away(self):
        read = self._run([("10-Q", "2026-08-20", "0001-26-000001", "x/q.htm")], {})
        self.assertIsNone(read["score"])
        self.assertEqual(read["filings_read"], 0)

    def test_filings_outside_the_lookback_window_are_ignored(self):
        read = self._run(
            [("4", "2025-01-05", "0001-25-000001", "x/old.xml")],
            {"old.xml": _form4_xml([("P", "1000", "100")])},
        )
        self.assertIsNone(read["score"])
        self.assertEqual(read["filings_read"], 0)

    def test_unknown_ticker_returns_no_coverage_without_fetching(self):
        with patch.object(filings_feed, "_get_json", lambda url, *a, **k: TICKERS):
            read = filings_feed.insider_read("NOSUCHTICKER", today="2026-08-30")
        self.assertIsNone(read["score"])
        self.assertIsNone(read["cik"])

    def test_a_broken_filing_does_not_kill_the_whole_read(self):
        def fake_get_text(url, *a, **k):
            if "bad.xml" in url:
                raise RuntimeError("500 from sec.gov")
            return _form4_xml([("P", "1000", "100")])

        def fake_get_json(url, *a, **k):
            if "company_tickers" in url:
                return TICKERS
            return _submissions([
                ("4", "2026-08-20", "0001-26-000001", "x/bad.xml"),
                ("4", "2026-08-19", "0001-26-000002", "x/good.xml"),
            ])

        with patch.object(filings_feed, "_get_json", fake_get_json), \
             patch.object(filings_feed, "_get_text", fake_get_text):
            read = filings_feed.insider_read("NVDA", today="2026-08-30")
        self.assertEqual(read["score"], 100.0)
        self.assertEqual(read["errors"], 1)

    def test_a_dead_upstream_cannot_walk_the_whole_filing_index(self):
        """The per-symbol cap must bound ATTEMPTS, not successes. Counting
        only successes lets a systematically failing SEC (403/500) issue one
        request per Form 4 in the index — a retry storm per symbol, per pass.
        """
        forms = [("4", "2026-08-20", f"0001-26-{i:06d}", f"x/f{i}.xml") for i in range(200)]
        attempts = {"n": 0}

        def always_fails(url, *a, **k):
            attempts["n"] += 1
            raise RuntimeError("503 from sec.gov")

        def fake_get_json(url, *a, **k):
            if "company_tickers" in url:
                return TICKERS
            return _submissions(forms)

        with patch.dict("os.environ", {"FILINGS_MAX_PER_SYMBOL": "5"}), \
             patch.object(filings_feed, "_get_json", fake_get_json), \
             patch.object(filings_feed, "_get_text", always_fails):
            read = filings_feed.insider_read("NVDA", today="2026-08-30")

        self.assertLessEqual(attempts["n"], 5)
        self.assertEqual(read["errors"], attempts["n"])
        self.assertIsNone(read["score"])

    def test_raw_xml_url_drops_the_xsl_render_prefix(self):
        self.assertEqual(
            filings_feed._document_url(1045810, "0001347842-26-000015",
                                       "xslF345X06/wk-form4_178.xml"),
            "https://www.sec.gov/Archives/edgar/data/1045810/"
            "000134784226000015/wk-form4_178.xml",
        )

    def test_disabled_feed_reads_nothing(self):
        with patch.dict("os.environ", {"FILINGS_FEED_ENABLED": "false"}):
            self.assertFalse(filings_feed.enabled())


if __name__ == "__main__":
    unittest.main()
