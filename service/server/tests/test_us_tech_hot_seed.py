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


class RestrictHotTechMustTests(unittest.TestCase):
    """R20-MUST, clarified (owner 2026-09-04, superseding the 08-31
    drop-all reading: "not limit 5 usa stock … ex slot 10 then 5 must be
    tech stock, and then other 5"): the top-5 hottest tech theses LEAD the
    us-stock slice as mandatory first picks; every other us-stock thesis
    stays eligible BELOW them for the remaining slots."""

    def tearDown(self):
        os.environ.pop("US_TECH_HOT_MUST", None)
        os.environ.pop("US_TECH_HOT_SEED", None)

    def test_default_on(self):
        self.assertTrue(sr._tech_hot_must_enabled())
        os.environ["US_TECH_HOT_MUST"] = "0"
        self.assertFalse(sr._tech_hot_must_enabled())

    def test_top5_tech_lead_and_non_tech_stays_below(self):
        eligible = [
            _thesis("BTCUSDT", market="crypto", final=0.9),
            _thesis("KO", mom_2d=9.0, vol_ratio=3.0, final=0.99),   # non-tech
            _thesis("NVDA", mom_2d=3.0, vol_ratio=1.0),   # hot 3.0
            _thesis("WMT", mom_2d=8.0, vol_ratio=3.0),    # non-tech
            _thesis("AMD", mom_2d=5.0, vol_ratio=1.0),    # hot 5.0
            _thesis("GC", market="futures", final=0.4),
            _thesis("MSFT", mom_2d=1.0, vol_ratio=1.0),   # hot 1.0
            _thesis("META", mom_2d=2.0, vol_ratio=1.0),   # hot 2.0
            _thesis("INTC", mom_2d=0.5, vol_ratio=1.0),   # hot 0.5
            _thesis("ORCL", mom_2d=4.0, vol_ratio=1.0),   # hot 4.0
        ]
        out = sr._hot_tech_first_us_stock(eligible)
        us = [t["symbol"] for t in out if t["market"] == "us-stock"]
        # top-5 hottest tech lead; everything else follows in its order
        self.assertEqual(us, ["AMD", "ORCL", "NVDA", "META", "MSFT",
                              "KO", "WMT", "INTC"])
        # other markets survive untouched and in order
        others = [t["symbol"] for t in out if t["market"] != "us-stock"]
        self.assertEqual(others, ["BTCUSDT", "GC"])

    def test_fewer_than_five_tech_leads_them_all(self):
        eligible = [_thesis("KO", mom_2d=9.0, vol_ratio=3.0),
                    _thesis("NVDA", mom_2d=1.0), _thesis("AMD", mom_2d=2.0)]
        out = sr._hot_tech_first_us_stock(eligible)
        self.assertEqual([t["symbol"] for t in out], ["AMD", "NVDA", "KO"])

    def test_zero_tech_keeps_the_rest_of_the_market(self):
        """2026-09-04: zero eligible tech no longer blanks the us-stock
        slice — the rest of the market still fills slots."""
        eligible = [_thesis("KO", mom_2d=9.0, vol_ratio=3.0),
                    _thesis("BTCUSDT", market="crypto")]
        out = sr._hot_tech_first_us_stock(eligible)
        self.assertEqual([t["symbol"] for t in out], ["KO", "BTCUSDT"])

    def test_owner_hot_issue_names_are_on_the_roster(self):
        """Owner 2026-09-04: 'space x, ASTS, nvidia, pltr, tsla, SMR …'"""
        for sym in ("ASTS", "SMR", "SPCX", "NVDA", "PLTR", "TSLA"):
            self.assertIn(sym, sr.US_TECH_HOT_UNIVERSE)

    def test_select_targets_wiring(self):
        # The brief-line lesson: prove the restriction actually runs inside
        # select_targets, not only as a helper. Patch the batch plumbing to
        # hand select_targets a mixed eligible set via the theses query.
        import database
        import tempfile
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(tmp.name, "t.db")
        database.init_database()
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO users (email, password_hash) VALUES ('x@x', 'x')")
        cur.execute("INSERT INTO agents (name, user_id) VALUES ('a', 1)")
        agent_id = cur.lastrowid
        cur.execute(
            "INSERT INTO research_batches (batch_id, created_at) VALUES (1, ?)",
            ("2026-08-31T00:00:00Z",))
        far = "2099-01-01T00:00:00Z"
        rows = [("KO", 0.99, 9.0), ("NVDA", 0.5, 3.0), ("AMD", 0.5, 5.0)]
        for sym, final, mom in rows:
            cur.execute(
                """INSERT INTO research_theses
                   (batch_id, market, symbol, market_type, direction, thesis,
                    risks, invalidation, expected_move_pct, horizon_hours,
                    confidence, ev_per_day_pct, final_score, selectable,
                    planner, factor_scores_json, created_at, expires_at)
                   VALUES (1, 'us-stock', ?, 'spot', 'long', 't', 'r', 'i',
                           5.0, 24, 0.7, 1.0, ?, 1, 'llm', ?, ?, ?)""",
                (sym, final,
                 json.dumps({"factors": {"mom_2d": mom, "vol_ratio": 1.0}}),
                 "2026-08-31T00:00:00Z", far))
        conn.commit()
        picked = sr.select_targets(cur, agent_id, 3)
        syms = [t["symbol"] for t in picked]
        # must-rule wired: both tech names are forced ahead of the
        # higher-scored non-tech KO, which still fills the remaining slot
        # (owner 2026-09-04: tech first, then others — never tech-only).
        self.assertEqual(syms[:2], ["AMD", "NVDA"])
        self.assertEqual(syms[2], "KO")
        conn.close()


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
