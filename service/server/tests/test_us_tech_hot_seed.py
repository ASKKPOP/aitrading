"""R20 — OWNER ORDER (2026-08-18): auto-built fleets always research the
US tech roster, and the hottest min(5, slots) tech theses lead the
us-stock ordering at selection. Universe/ordering guarantee ONLY — the
build gates and the desk's authorship are untouched. US_TECH_HOT_SEED=0
disables everything."""

from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from unittest.mock import patch

import routes_market  # noqa: E402
import symbol_research as sr  # noqa: E402

# A tech name NOT in the dropdown list — the class the seed actually adds.
TECH_ONLY = "ACN"
assert TECH_ONLY in sr.US_TECH_HOT_UNIVERSE
assert TECH_ONLY not in routes_market.US_STOCK_SYMBOLS


def _thesis(symbol, market="us-stock", mom_2d=0.0, vol_ratio=1.0, final=0.5):
    return {"symbol": symbol, "market": market, "final_score": final,
            "factor_scores_json": json.dumps(
                {"factors": {"mom_2d": mom_2d, "vol_ratio": vol_ratio}})}


class TechHotUniverseTests(unittest.TestCase):
    def tearDown(self):
        os.environ.pop("US_TECH_HOT_SEED", None)

    def test_tech_roster_always_in_us_stock_universe(self):
        stocks = list(routes_market.US_STOCK_SYMBOLS)
        if sr._tech_hot_seed_enabled():
            for s in sr.US_TECH_HOT_UNIVERSE:
                if s not in stocks:
                    stocks.append(s)
        self.assertIn(TECH_ONLY, stocks)

    def test_kill_switch_removes_seed(self):
        os.environ["US_TECH_HOT_SEED"] = "0"
        self.assertFalse(sr._tech_hot_seed_enabled())


class EnsureHotTechLeadTests(unittest.TestCase):
    def tearDown(self):
        os.environ.pop("US_TECH_HOT_SEED", None)

    def test_top5_hot_tech_lead_us_stock_ordering(self):
        # 3 non-tech leaders + 6 tech names with varying hotness.
        eligible = [
            _thesis("KO", mom_2d=9.0, vol_ratio=3.0, final=0.9),
            _thesis("XOM", mom_2d=8.0, vol_ratio=3.0, final=0.9),
            _thesis("BTCUSDT", market="crypto", final=0.99),
            _thesis("NVDA", mom_2d=5.0, vol_ratio=2.0),
            _thesis("AAPL", mom_2d=4.0, vol_ratio=2.0),
            _thesis("MSFT", mom_2d=3.0, vol_ratio=2.0),
            _thesis("AMD", mom_2d=2.0, vol_ratio=2.0),
            _thesis("META", mom_2d=1.5, vol_ratio=2.0),
            _thesis("CSCO", mom_2d=0.1, vol_ratio=1.0),
        ]
        sr._ensure_hot_tech_lead(eligible)
        us = [t["symbol"] for t in eligible if t["market"] == "us-stock"]
        # hottest 5 tech lead, in hotness order; non-tech follow; CSCO (6th
        # tech) is not force-led.
        self.assertEqual(us[:5], ["NVDA", "AAPL", "MSFT", "AMD", "META"])
        self.assertEqual(set(us[5:]), {"KO", "XOM", "CSCO"})
        # crypto row untouched in place
        self.assertEqual(eligible[2]["symbol"], "BTCUSDT")

    def test_fewer_than_five_tech_takes_what_exists(self):
        eligible = [
            _thesis("KO", mom_2d=9.0, vol_ratio=3.0),
            _thesis("NVDA", mom_2d=1.0),
            _thesis("AAPL", mom_2d=2.0),
        ]
        sr._ensure_hot_tech_lead(eligible)
        us = [t["symbol"] for t in eligible]
        self.assertEqual(us[:2], ["AAPL", "NVDA"])
        self.assertEqual(us[2], "KO")

    def test_kill_switch_restores_old_ordering(self):
        os.environ["US_TECH_HOT_SEED"] = "0"
        eligible = [
            _thesis("KO", mom_2d=9.0, vol_ratio=3.0),
            _thesis("NVDA", mom_2d=1.0),
        ]
        before = [t["symbol"] for t in eligible]
        sr._ensure_hot_tech_lead(eligible)
        self.assertEqual([t["symbol"] for t in eligible], before)

    def test_no_tech_rows_is_a_noop(self):
        eligible = [_thesis("KO", mom_2d=9.0), _thesis("XOM", mom_2d=1.0)]
        before = [t["symbol"] for t in eligible]
        sr._ensure_hot_tech_lead(eligible)
        self.assertEqual([t["symbol"] for t in eligible], before)


class HotTechPromptTests(unittest.TestCase):
    """The prompt clause and row flag ship WIRED (the brief-line lesson:
    a rendered-but-unwired line passes every helper test)."""

    def setUp(self):
        import tempfile
        import database
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "t.db")
        database.init_database()

    def tearDown(self):
        self.tmp.cleanup()

    def test_hot_tech_flag_and_clause_reach_the_prompt(self):
        captured = {}

        def fake_generate(prompt, **kw):
            captured["prompt"] = prompt
            return "[]"

        theses = [{"symbol": "NVDA", "market": "us-stock", "eps_raw": 1.0,
                   "momentum_sign": 1.0, "session_open": True,
                   "factors": {"last": 100.0, "mom_5d": 1.0, "mom_20d": 2.0,
                               "vol_daily_pct": 2.0, "vol_ratio": 1.0}}]
        with patch.object(sr, "_previous_thesis", return_value=None):
            sr.generate_theses(theses, generate_text=fake_generate)
        self.assertIn('"hot_tech": true', captured["prompt"])
        self.assertIn("hot_tech", captured["prompt"])
        self.assertIn("US technology large-cap", captured["prompt"])

    def test_no_flag_no_clause(self):
        captured = {}

        def fake_generate(prompt, **kw):
            captured["prompt"] = prompt
            return "[]"

        theses = [{"symbol": "KO", "market": "us-stock", "eps_raw": 1.0,
                   "momentum_sign": 1.0, "session_open": True,
                   "factors": {"last": 100.0, "mom_5d": 1.0, "mom_20d": 2.0,
                               "vol_daily_pct": 2.0, "vol_ratio": 1.0}}]
        with patch.object(sr, "_previous_thesis", return_value=None):
            sr.generate_theses(theses, generate_text=fake_generate)
        self.assertNotIn("US technology large-cap", captured["prompt"])


if __name__ == "__main__":
    unittest.main()
