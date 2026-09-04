"""Swing seed universe (2026-08-14, fleet 31 stuck at 17/25).

The organic us-stock pool — the dropdown list plus hot movers — kept
proposing exactly the names the swing universe gate refuses (QNT/CBRS/SPCX
at 42–62 daily bars), so every replacement pass gated to nothing. While a
swing-archetype fleet is live, research widens what it CONSIDERS with the
S&P 100 roster (SWING_SEED_UNIVERSE): seeded names enter build_universe,
survive the screen cut up to swing demand, and become theses like any
other. swing_symbol_check and the expectancy gate still decide what builds
— the seed grants no bypass. SWING_SEED_UNIVERSE=0 disables.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database  # noqa: E402
import fleet_planner as fp  # noqa: E402
import routes_market  # noqa: E402
import symbol_research as sr  # noqa: E402

# A seed name that is NOT in the frontend dropdown list — the one class the
# seed actually adds to the researched universe.
SEED_ONLY = "HON"
assert SEED_ONLY in sr.SWING_SEED_UNIVERSE
assert SEED_ONLY not in routes_market.US_STOCK_SYMBOLS


def _candles(n=60, start=100.0, drift=0.5, volume=1_000_000):
    """Synthetic daily candles with a steady drift (%/day)."""
    out, price = [], start
    for i in range(n):
        price *= 1 + drift / 100.0
        out.append({"ts": i, "open": price, "high": price, "low": price,
                    "close": price, "volume": volume})
    return out


_OVERLAYS = {"event_window": False, "regime_blocks_longs": False, "policy": {}}


class _DbBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "t.db")
        database.init_database()
        os.environ.pop("SWING_SEED_UNIVERSE", None)
        for key in list(os.environ):
            if key.startswith("FLEET_RESEARCH_SURVIVORS_"):
                os.environ.pop(key)

    def tearDown(self):
        os.environ.pop("SWING_SEED_UNIVERSE", None)
        os.environ.pop("FLEET_RESEARCH_SURVIVORS_US_STOCK", None)
        self.tmp.cleanup()

    def _fleet(self, n_runs, archetype="swing", status="active",
               scope_json='["us-stock"]'):
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO fleets (agent_id, status, n_runs, total_budget_usd,"
            " risk_appetite, market_scope_json, archetype, created_at) VALUES"
            " (6, ?, ?, 10000.0, 'balanced', ?, ?, '2026-08-14T00:00:00Z')",
            (status, n_runs, scope_json, archetype))
        conn.commit()
        conn.close()

    def _universe_us_stock(self):
        # us-stock only: the crypto branch probes the venue's listed set,
        # and this suite must make zero live calls.
        with patch("markets.automatable_markets", return_value=("us-stock",)), \
             patch("market_intel._get_hot_us_stock_symbols", return_value=[]):
            return [c["symbol"] for c in sr.build_universe()
                    if c["market"] == "us-stock"]


class SwingDemandTests(_DbBase):
    def test_no_fleets_means_zero_demand_and_no_seed(self):
        self.assertEqual(sr._swing_fleet_demand(), 0)
        self.assertNotIn(SEED_ONLY, self._universe_us_stock())

    def test_demand_sums_non_terminal_swing_fleets_only(self):
        self._fleet(25)
        self._fleet(5, status="paused")
        self._fleet(10, status="stopped")          # terminal — never counts
        self._fleet(7, archetype="short")          # not swing — never counts
        self.assertEqual(sr._swing_fleet_demand(), 30)

    def test_swing_demand_pulls_seed_symbols_into_the_universe(self):
        self._fleet(25)
        got = self._universe_us_stock()
        self.assertIn(SEED_ONLY, got)
        # every seed name is present, and dedupe holds for the overlap
        for s in sr.SWING_SEED_UNIVERSE:
            self.assertIn(s, got)
        self.assertEqual(got.count("AAPL"), 1)

    def test_short_archetype_fleet_does_not_trigger_the_seed(self):
        self._fleet(25, archetype="short")
        self.assertNotIn(SEED_ONLY, self._universe_us_stock())

    def test_kill_switch_disables_the_seed(self):
        self._fleet(25)
        os.environ["SWING_SEED_UNIVERSE"] = "0"
        self.assertNotIn(SEED_ONLY, self._universe_us_stock())

    def test_demand_fails_soft_to_zero(self):
        with patch.object(database, "get_db_connection",
                          side_effect=RuntimeError("db down")):
            self.assertEqual(sr._swing_fleet_demand(), 0)


class SurvivorTopUpTests(_DbBase):
    """Seed names below the mover-tilted cut still reach thesis stage."""

    MOVERS = [f"MOVR{i}" for i in range(4)]        # not in the seed roster
    SEEDS = ["JNJ", "KO", "PG"]

    def _fetch(self, sym, market):
        return _candles(drift=2.0 if sym in self.MOVERS else 0.3)

    def _screen(self):
        os.environ["FLEET_RESEARCH_SURVIVORS_US_STOCK"] = "2"
        universe = [{"symbol": s, "market": "us-stock"}
                    for s in self.MOVERS + self.SEEDS]
        return sr.screen_universe(universe, fetch_candles=self._fetch,
                                  overlays=_OVERLAYS)

    def test_no_swing_demand_keeps_the_plain_cut(self):
        got = self._screen()
        self.assertEqual(len(got), 2)
        self.assertFalse(set(s["symbol"] for s in got) & set(self.SEEDS))

    def test_seed_names_below_the_cut_survive_up_to_demand(self):
        self._fleet(3)
        got = self._screen()
        syms = [s["symbol"] for s in got]
        self.assertEqual(len(got), 5)              # top-2 movers + 3 seeds
        for s in self.SEEDS:
            self.assertIn(s, syms)
        self.assertEqual(sum(1 for s in syms if s in self.MOVERS), 2)

    def test_the_hard_cap_still_bounds_the_market(self):
        self._fleet(50)
        with patch.object(sr, "_SURVIVOR_HARD_CAP", 4):
            got = self._screen()
        self.assertEqual(len(got), 4)

    def test_demand_already_covered_by_the_cut_adds_nothing(self):
        self._fleet(2)

        def seed_led(sym, market):                 # seeds outscore the movers
            return _candles(drift=0.3 if sym in self.MOVERS else 2.0)

        os.environ["FLEET_RESEARCH_SURVIVORS_US_STOCK"] = "2"
        universe = [{"symbol": s, "market": "us-stock"}
                    for s in self.MOVERS + self.SEEDS]
        got = sr.screen_universe(universe, fetch_candles=seed_led,
                                 overlays=_OVERLAYS)
        self.assertEqual(len(got), 2)
        self.assertTrue(set(s["symbol"] for s in got) <= set(self.SEEDS))

    def test_kill_switch_disables_the_top_up(self):
        self._fleet(3)
        os.environ["SWING_SEED_UNIVERSE"] = "0"
        self.assertEqual(len(self._screen()), 2)


class SeededCandidatesStillGatedTests(unittest.TestCase):
    """The seed widens what is CONSIDERED, never what PASSES — a seed name
    failing the swing universe gate or the expectancy gate is still dropped."""

    SWING_FLEET = {"archetype": "swing"}

    def test_a_thin_history_seed_name_is_still_dropped_by_the_swing_gate(self):
        self.assertIn("JNJ", sr.SWING_SEED_UNIVERSE)
        thesis = {"symbol": "JNJ", "market": "us-stock"}
        with patch("price_fetcher.get_daily_candles",
                   return_value=_candles(n=42)):
            kept, dropped = fp.swing_gate_candidates(self.SWING_FLEET, [thesis])
        self.assertEqual(kept, [])
        self.assertIn("swing_history_thin", dropped["JNJ"])

    def test_a_negative_expectancy_seed_name_is_still_dropped(self):
        import backtest_gate as bg
        self.assertIn("KO", sr.SWING_SEED_UNIVERSE)
        stats = {"n_trades": 12, "expectancy_usd": -4.0, "win_rate": 0.3,
                 "wilson_lb": 0.15}
        with patch.object(bg, "symbol_expectancy", return_value=stats):
            kept, dropped = bg.gate_candidates(
                [{"symbol": "KO", "market": "us-stock"}])
        self.assertEqual(kept, [])
        self.assertIn("expectancy", dropped["KO"])

    def test_a_seed_name_clearing_the_swing_gate_is_kept(self):
        thesis = {"symbol": "PG", "market": "us-stock"}
        deep = _candles(n=260, start=100.0, drift=0.0, volume=1_000_000)
        with patch("price_fetcher.get_daily_candles", return_value=deep), \
             patch("fmp_feed.days_to_earnings", return_value=None):
            kept, dropped = fp.swing_gate_candidates(self.SWING_FLEET, [thesis])
        self.assertEqual(dropped, {})
        self.assertEqual(kept[0]["swing_g_frac"], fp.SWING_G_FLOOR)


class EndToEndRefreshTests(_DbBase):
    """A live swing fleet pulls a seed-only symbol all the way through the
    normal pipeline: universe → screen → persisted thesis. Under R20-MUST
    (owner 2026-08-31) SELECTION is restricted to the hot-5 tech names, so
    the seed-only name is researched but no longer selectable while the
    must-rule is on; with it off, the pre-existing end-to-end guarantee
    still holds."""

    def test_seed_symbol_reaches_selectable_theses(self):
        self._fleet(25)

        def fetch(sym, market):                    # seed-only name leads
            return _candles(drift=2.0 if sym == SEED_ONLY else 0.5)

        with patch("markets.automatable_markets", return_value=("us-stock",)), \
             patch("market_intel._get_hot_us_stock_symbols",
                   return_value=[]), \
             patch("fmp_feed.days_to_earnings", return_value=None), \
             patch.object(sr, "_read_overlays", return_value=_OVERLAYS):
            summary = sr.refresh_research_batch(
                generate_text=lambda *a, **k: None, fetch_candles=fetch)
        self.assertGreater(summary.get("persisted", 0), 0)

        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            # The seed symbol IS a research_theses row like any other.
            cur.execute(
                "SELECT COUNT(*) AS n FROM research_theses WHERE symbol = ?",
                (SEED_ONLY,))
            self.assertGreater(cur.fetchone()["n"], 0)
            # R20-MUST on (the default), clarified 2026-09-04: the hot
            # tech roster leads as mandatory first picks, but the rest of
            # the market — the seed-only name included — still fills the
            # remaining slots (the drop-all reading starved fleet 43).
            picked = sr.select_targets(cur, 6, 25,
                                       markets_scope=["us-stock"])
            roster = set(sr.US_TECH_HOT_UNIVERSE)
            self.assertTrue(picked)
            syms = [t["symbol"] for t in picked]
            n_lead = min(sr.US_TECH_HOT_K,
                         sum(1 for s in syms if s in roster))
            self.assertTrue(all(s in roster for s in syms[:n_lead]),
                            f"tech roster must lead the picks: {syms}")
            self.assertIn(SEED_ONLY, syms)
            # R20-MUST off: the original guarantee — the seed-only name is
            # selectable end to end.
            os.environ["US_TECH_HOT_MUST"] = "0"
            try:
                picked = sr.select_targets(cur, 6, 25,
                                           markets_scope=["us-stock"])
            finally:
                os.environ.pop("US_TECH_HOT_MUST", None)
            self.assertIn(SEED_ONLY, [t["symbol"] for t in picked])
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
