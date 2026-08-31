"""crawl_monitor.py — per-pass crawl bookkeeping for the swing pipeline.

Every collector pass writes one crawl_runs row (ok / duration / items /
error), so the admin console can show what the crawlers actually did rather
than only whether an upstream URL answers right now.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import crawl_monitor
import database


class CrawlMonitorTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()

    def tearDown(self):
        self.tmp.cleanup()

    # -- recording -------------------------------------------------------
    def test_successful_pass_records_ok_row(self):
        with crawl_monitor.track("filings") as run:
            run.items = 7
            run.detail = {"symbols": ["NVDA"]}
        rows = crawl_monitor.recent_runs(feed="filings")
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["ok"])
        self.assertEqual(rows[0]["items"], 7)
        self.assertEqual(rows[0]["detail"]["symbols"], ["NVDA"])
        self.assertIsNone(rows[0]["error"])
        self.assertIsNotNone(rows[0]["duration_ms"])

    def test_failing_pass_records_error_and_reraises(self):
        with self.assertRaises(ValueError):
            with crawl_monitor.track("catalyst"):
                raise ValueError("upstream 503")
        rows = crawl_monitor.recent_runs(feed="catalyst")
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0]["ok"])
        self.assertIn("upstream 503", rows[0]["error"])

    def test_track_never_swallows_a_db_failure_of_its_own(self):
        """Bookkeeping must not break the crawler it wraps."""
        database._SQLITE_DB_PATH = "/nonexistent/dir/x.db"
        with crawl_monitor.track("filings") as run:
            run.items = 1
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")

    # -- summary ---------------------------------------------------------
    def test_summary_reports_last_run_and_success_rate_per_feed(self):
        with crawl_monitor.track("filings") as run:
            run.items = 3
        try:
            with crawl_monitor.track("filings"):
                raise RuntimeError("boom")
        except RuntimeError:
            pass
        with crawl_monitor.track("catalyst") as run:
            run.items = 1

        summary = crawl_monitor.feed_summary()
        self.assertEqual(summary["filings"]["runs_24h"], 2)
        self.assertEqual(summary["filings"]["ok_24h"], 1)
        self.assertEqual(summary["filings"]["success_rate"], 0.5)
        self.assertFalse(summary["filings"]["last_ok"])
        self.assertIn("boom", summary["filings"]["last_error"])
        self.assertEqual(summary["catalyst"]["success_rate"], 1.0)
        self.assertIsNotNone(summary["filings"]["last_run_at"])
        self.assertIsNotNone(summary["filings"]["age_seconds"])

    def test_summary_is_empty_before_any_crawl(self):
        self.assertEqual(crawl_monitor.feed_summary(), {})

    def test_recent_runs_without_feed_returns_all_newest_first(self):
        for i in range(3):
            with crawl_monitor.track("filings") as run:
                run.items = i
        rows = crawl_monitor.recent_runs(limit=2)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["items"], 2)

    def test_prune_deletes_only_rows_older_than_retention(self):
        """Asserting the COUNT alone cannot tell `started_at < cutoff` from
        `> cutoff` — both delete exactly one row here. Identify the survivor."""
        with crawl_monitor.track("filings") as run:
            run.items = 1
        with database.get_db_connection() as conn:
            conn.cursor().execute(
                "UPDATE crawl_runs SET started_at = ?", ("2020-01-01T00:00:00Z",)
            )
            conn.commit()
        with crawl_monitor.track("filings") as run:
            run.items = 2
        deleted = crawl_monitor.prune(retention_days=7)
        self.assertEqual(deleted, 1)
        survivors = crawl_monitor.recent_runs(feed="filings")
        self.assertEqual(len(survivors), 1)
        # the RECENT row must be the one left standing, not the 2020 one
        self.assertEqual(survivors[0]["items"], 2)
        self.assertNotEqual(survivors[0]["started_at"], "2020-01-01T00:00:00Z")

    def test_prune_keeps_everything_inside_the_window(self):
        for i in range(3):
            with crawl_monitor.track("filings") as run:
                run.items = i
        self.assertEqual(crawl_monitor.prune(retention_days=7), 0)
        self.assertEqual(len(crawl_monitor.recent_runs(feed="filings")), 3)


if __name__ == "__main__":
    unittest.main()
