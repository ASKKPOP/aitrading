"""catalyst_feed.py — earnings surprises/catalysts -> thesis score.

Pipeline feed #4 (research/SWING_SIGNAL_STACK.md §2). HTTP is patched;
fixtures mirror the Nasdaq payloads verified live on 2026-08-30:

  - earnings-surprise rows carry an already-computed "% Surprise" string
  - the NEXT earnings date exists only inside free text, e.g.
    "Earnings announcement* for ORCL: Sep 8, 2026" — and is often absent
    ("our vendor hasn't provided us with the upcoming earnings report date")
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import catalyst_feed


def _surprise(rows):
    return {"data": {"earningsSurpriseTable": {"rows": rows}}}


def _row(qtr, reported, eps, consensus, pct):
    return {
        "fiscalQtrEnd": qtr, "dateReported": reported, "eps": eps,
        "consensusForecast": consensus, "percentageSurprise": pct,
    }


def _announcement(text):
    return {"data": {"announcement": text}}


class ThesisScoreTest(unittest.TestCase):
    def _read(self, surprise_payload, date_payload=None, today="2026-08-30"):
        def fake_get_json(url, *a, **k):
            if "earnings-surprise" in url:
                return surprise_payload
            if "earnings-date" in url:
                return date_payload or _announcement("no date here")
            raise AssertionError(f"unexpected url {url}")

        with patch.object(catalyst_feed, "_get_json", fake_get_json):
            return catalyst_feed.catalyst_read("NVDA", today=today)

    def test_consistent_beats_score_bullish(self):
        read = self._read(_surprise([
            _row("Jul 2026", "8/26/2026", 2.22, "2.09", "6.22"),
            _row("Apr 2026", "5/20/2026", 1.87, "1.7", "10"),
            _row("Jan 2026", "2/25/2026", 1.57, "1.45", "8.28"),
            _row("Oct 2025", "11/19/2025", 1.3, "1.2", "8.33"),
        ]))
        self.assertGreater(read["score"], 30)
        self.assertEqual(read["latest_surprise_pct"], 6.22)
        self.assertEqual(read["beats"], 4)
        self.assertEqual(read["quarters"], 4)

    def test_consistent_misses_score_bearish(self):
        read = self._read(_surprise([
            _row("Jul 2026", "8/26/2026", 1.0, "1.2", "-16.67"),
            _row("Apr 2026", "5/20/2026", 0.9, "1.1", "-18.18"),
        ]))
        self.assertLess(read["score"], -30)
        self.assertEqual(read["beats"], 0)

    def test_latest_print_outweighs_the_older_average(self):
        """A fresh miss after old beats must not stay bullish."""
        recent_miss = self._read(_surprise([
            _row("Jul 2026", "8/26/2026", 1.0, "1.5", "-33.3"),
            _row("Apr 2026", "5/20/2026", 1.87, "1.7", "10"),
            _row("Jan 2026", "2/25/2026", 1.57, "1.45", "8.28"),
        ]))
        self.assertLess(recent_miss["score"], 0)

    def test_no_rows_is_no_coverage_not_neutral(self):
        read = self._read(_surprise([]))
        self.assertIsNone(read["score"])
        self.assertEqual(read["quarters"], 0)

    def test_upstream_failure_degrades_to_no_coverage(self):
        def boom(url, *a, **k):
            raise RuntimeError("403 from api.nasdaq.com")

        with patch.object(catalyst_feed, "_get_json", boom):
            read = catalyst_feed.catalyst_read("NVDA", today="2026-08-30")
        self.assertIsNone(read["score"])
        self.assertIn("403", read["error"])

    def test_unparsable_surprise_values_are_skipped_not_fatal(self):
        read = self._read(_surprise([
            _row("Jul 2026", "8/26/2026", 2.22, "2.09", "N/A"),
            _row("Apr 2026", "5/20/2026", 1.87, "1.7", "10"),
        ]))
        self.assertEqual(read["quarters"], 1)
        self.assertEqual(read["latest_surprise_pct"], 10.0)

    # -- next earnings date (risk-gate input) ----------------------------
    def test_next_earnings_date_parsed_from_free_text(self):
        read = self._read(
            _surprise([_row("Jul 2026", "8/26/2026", 2.22, "2.09", "6.22")]),
            _announcement("Earnings announcement* for ORCL: Sep 8, 2026"),
        )
        self.assertEqual(read["next_earnings_date"], "2026-09-08")
        self.assertEqual(read["days_to_next_earnings"], 9)
        self.assertEqual(read["hours_to_next_earnings"], 9 * 24)

    def test_zero_padded_date_form_also_parses(self):
        read = self._read(
            _surprise([_row("Jul 2026", "8/26/2026", 2.22, "2.09", "6.22")]),
            _announcement("Earnings announcement* for AVGO: Sep 02, 2026"),
        )
        self.assertEqual(read["next_earnings_date"], "2026-09-02")

    def test_missing_next_date_is_none_not_a_guess(self):
        read = self._read(
            _surprise([_row("Jul 2026", "8/26/2026", 2.22, "2.09", "6.22")]),
            _announcement("Our vendor, Zacks Investment Research, hasn't provided us "
                          "with the upcoming earnings report date."),
        )
        self.assertIsNone(read["next_earnings_date"])
        self.assertIsNone(read["hours_to_next_earnings"])

    def test_an_already_passed_earnings_date_is_not_a_future_event(self):
        """A stale date would make hours_to_next_earnings negative, and the
        risk gate vetoes anything inside 24h — a past print would blackout
        the symbol forever."""
        read = self._read(
            _surprise([_row("Jul 2026", "8/26/2026", 2.22, "2.09", "6.22")]),
            _announcement("Earnings announcement* for NVDA: Aug 26, 2026"),
            today="2026-08-30",
        )
        self.assertIsNone(read["next_earnings_date"])
        self.assertIsNone(read["days_to_next_earnings"])
        self.assertIsNone(read["hours_to_next_earnings"])

    def test_todays_earnings_date_still_counts_as_upcoming(self):
        read = self._read(
            _surprise([_row("Jul 2026", "8/26/2026", 2.22, "2.09", "6.22")]),
            _announcement("Earnings announcement* for NVDA: Aug 30, 2026"),
            today="2026-08-30",
        )
        self.assertEqual(read["next_earnings_date"], "2026-08-30")
        self.assertEqual(read["hours_to_next_earnings"], 0)

    def test_days_since_last_report_is_tracked(self):
        read = self._read(_surprise([_row("Jul 2026", "8/26/2026", 2.22, "2.09", "6.22")]))
        self.assertEqual(read["days_since_report"], 4)

    def test_disabled_feed_reads_nothing(self):
        with patch.dict("os.environ", {"CATALYST_FEED_ENABLED": "false"}):
            self.assertFalse(catalyst_feed.enabled())


if __name__ == "__main__":
    unittest.main()
