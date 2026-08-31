"""routes_admin_crawl.py — the admin crawling & monitoring console API.

Covers the pipeline overview (COLLECT -> SCORE -> COMBINE -> DECIDE with live
health per node), the crawl history, the decision table, and the manual
trigger. No network: crawl rows and decisions are seeded through the modules
that own them.
"""
from __future__ import annotations

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

import crawl_monitor
import database
import routes_admin_crawl
import swing_pipeline
from routes import create_app


def _decision(symbol="NVDA", action="BUY", composite=52.0, coverage=5):
    return {
        "symbol": symbol, "market": "us-stock",
        "scores": {"sentiment": 30.0, "macro": 20.0, "thesis": 60.0,
                   "smart_money": 40.0, "technical": 80.0},
        "composite": composite, "axis": "AGREE_BULL", "action": action,
        "veto": None, "reason": None, "coverage": coverage,
        "hours_to_binary_event": 72.0, "detail": {"candles": 64},
    }


class AdminCrawlConsoleTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())
        from admin_auth import create_admin
        create_admin("root@test.com", "rootpass123", "superadmin")
        r = self.client.post("/api/admin/login",
                             json={"email": "root@test.com", "password": "rootpass123"})
        self.admin = {"Authorization": f"Bearer {r.json()['token']}"}

    def tearDown(self):
        self.tmp.cleanup()

    # -- auth ------------------------------------------------------------
    def test_every_endpoint_requires_an_admin_session(self):
        for path in ("/api/admin/crawl/overview", "/api/admin/crawl/runs",
                     "/api/admin/crawl/decisions"):
            self.assertEqual(self.client.get(path).status_code, 401, path)
        self.assertEqual(
            self.client.post("/api/admin/crawl/run").status_code, 401)

    # -- overview --------------------------------------------------------
    def test_overview_describes_the_whole_pipeline(self):
        r = self.client.get("/api/admin/crawl/overview", headers=self.admin)
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(len(body["collect"]), len(swing_pipeline.COLLECT_NODES))
        self.assertEqual(len(body["score"]), 5)
        self.assertAlmostEqual(sum(n["weight"] for n in body["score"]), 1.0, places=6)
        self.assertEqual(body["decide"]["buy_threshold"], 40.0)
        self.assertEqual(body["decide"]["sell_threshold"], -40.0)

    def test_overview_marks_a_collector_that_feeds_no_score(self):
        """A healthy crawler that is wired to nothing must not read as wired."""
        body = self.client.get("/api/admin/crawl/overview", headers=self.admin).json()
        by_key = {n["key"]: n for n in body["collect"]}
        self.assertFalse(by_key["social_crawl"]["wired"])
        self.assertFalse(by_key["news"]["wired"])
        self.assertTrue(by_key["price_volume"]["wired"])
        self.assertIn("not an input", by_key["social_crawl"]["note"])

    def test_a_feed_that_never_ran_is_idle_not_ok(self):
        body = self.client.get("/api/admin/crawl/overview", headers=self.admin).json()
        node = next(n for n in body["collect"] if n["key"] == "filings")
        self.assertEqual(node["status"], "idle")
        self.assertIsNone(node["last_run_at"])

    def test_health_reflects_the_last_pass(self):
        with crawl_monitor.track("filings") as run:
            run.items = 4
        try:
            with crawl_monitor.track("price_volume"):
                raise RuntimeError("yahoo 502")
        except RuntimeError:
            pass

        body = self.client.get("/api/admin/crawl/overview", headers=self.admin).json()
        by_key = {n["key"]: n for n in body["collect"]}
        self.assertEqual(by_key["filings"]["status"], "ok")
        self.assertEqual(by_key["filings"]["last_items"], 4)
        self.assertEqual(by_key["price_volume"]["status"], "failing")
        self.assertIn("yahoo 502", by_key["price_volume"]["last_error"])
        self.assertEqual(body["ok_count"], 1)
        self.assertEqual(body["failing_count"], 1)

    def test_processor_coverage_comes_from_the_latest_decisions(self):
        swing_pipeline._persist(_decision())
        swing_pipeline._persist({**_decision(symbol="AAPL"),
                                 "scores": {"sentiment": 10.0, "macro": None,
                                            "thesis": None, "smart_money": None,
                                            "technical": 5.0}})
        body = self.client.get("/api/admin/crawl/overview", headers=self.admin).json()
        by_key = {n["key"]: n for n in body["score"]}
        self.assertEqual(by_key["sentiment"]["covered_symbols"], 2)
        self.assertEqual(by_key["thesis"]["covered_symbols"], 1)
        self.assertEqual(by_key["thesis"]["symbols"], 2)

    def test_overview_counts_the_decisions_by_action(self):
        swing_pipeline._persist(_decision(symbol="NVDA", action="BUY"))
        swing_pipeline._persist(_decision(symbol="AAPL", action="WAIT"))
        swing_pipeline._persist(_decision(symbol="MSFT", action="WAIT"))
        body = self.client.get("/api/admin/crawl/overview", headers=self.admin).json()
        self.assertEqual(body["decide"]["actions"], {"BUY": 1, "WAIT": 2})

    # -- runs ------------------------------------------------------------
    def test_runs_returns_history_newest_first_and_filters_by_feed(self):
        for i in range(3):
            with crawl_monitor.track("filings") as run:
                run.items = i
        with crawl_monitor.track("news") as run:
            run.items = 9

        body = self.client.get("/api/admin/crawl/runs", headers=self.admin).json()
        self.assertEqual(len(body["runs"]), 4)
        self.assertEqual(body["runs"][0]["feed"], "news")

        only = self.client.get("/api/admin/crawl/runs?feed=filings",
                               headers=self.admin).json()
        self.assertEqual(len(only["runs"]), 3)
        self.assertEqual(only["runs"][0]["items"], 2)

    def test_runs_limit_is_capped(self):
        r = self.client.get("/api/admin/crawl/runs?limit=99999", headers=self.admin)
        self.assertEqual(r.status_code, 200)

    # -- decisions -------------------------------------------------------
    def test_decisions_returns_the_latest_row_per_symbol(self):
        swing_pipeline._persist(_decision(symbol="NVDA", composite=10.0, action="WAIT"))
        swing_pipeline._persist(_decision(symbol="NVDA", composite=55.0, action="BUY"))
        body = self.client.get("/api/admin/crawl/decisions", headers=self.admin).json()
        self.assertEqual(len(body["decisions"]), 1)
        self.assertEqual(body["decisions"][0]["composite"], 55.0)
        self.assertEqual(body["decisions"][0]["action"], "BUY")

    def test_decision_history_for_one_symbol(self):
        swing_pipeline._persist(_decision(symbol="NVDA", composite=10.0))
        swing_pipeline._persist(_decision(symbol="NVDA", composite=20.0))
        body = self.client.get("/api/admin/crawl/decisions?symbol=NVDA",
                               headers=self.admin).json()
        self.assertEqual(len(body["decisions"]), 2)

    # -- manual trigger --------------------------------------------------
    def test_manual_run_uses_the_posted_symbols(self):
        captured = {}

        def fake_run(symbols=None, market=None):
            captured["symbols"] = symbols
            captured["market"] = market
            return {"evaluated": 2, "failed": 0, "actions": {"WAIT": 2},
                    "symbols": 2, "market": market}

        with patch.object(routes_admin_crawl.swing_pipeline, "run_pipeline", fake_run):
            r = self.client.post("/api/admin/crawl/run",
                                 json={"symbols": ["nvda", "aapl"], "market": "us-stock"},
                                 headers=self.admin)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(captured["symbols"], ["NVDA", "AAPL"])
        self.assertEqual(r.json()["evaluated"], 2)

    def test_manual_run_without_symbols_falls_back_to_configuration(self):
        with patch.dict(os.environ, {"SWING_PIPELINE_SYMBOLS": "TSLA"}), \
             patch.object(routes_admin_crawl.swing_pipeline, "run_pipeline",
                          lambda symbols=None, market=None: {
                              "evaluated": len(symbols or []), "failed": 0,
                              "actions": {}, "symbols": len(symbols or []),
                              "market": market}):
            r = self.client.post("/api/admin/crawl/run", json={}, headers=self.admin)
        self.assertEqual(r.json()["evaluated"], 1)

    def test_manual_run_with_no_symbols_anywhere_is_a_clear_400(self):
        with patch.dict(os.environ, {"SWING_PIPELINE_SYMBOLS": ""}):
            r = self.client.post("/api/admin/crawl/run", json={}, headers=self.admin)
        self.assertEqual(r.status_code, 400)
        self.assertIn("symbol", r.json()["detail"].lower())

    def test_a_failing_pass_is_reported_not_a_500(self):
        def boom(symbols=None, market=None):
            raise RuntimeError("pipeline exploded")

        with patch.object(routes_admin_crawl.swing_pipeline, "run_pipeline", boom):
            r = self.client.post("/api/admin/crawl/run",
                                 json={"symbols": ["NVDA"]}, headers=self.admin)
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()["ok"])
        self.assertIn("pipeline exploded", r.json()["error"])

    def test_manual_run_symbol_count_is_bounded(self):
        r = self.client.post("/api/admin/crawl/run",
                             json={"symbols": [f"S{i}" for i in range(200)]},
                             headers=self.admin)
        self.assertEqual(r.status_code, 400)


if __name__ == "__main__":
    unittest.main()
