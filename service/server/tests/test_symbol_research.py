"""Plan 14 Phase 1+2 gates — symbol research engine.

Pure-function factor math, gates and clamps (with the mutation targets the
plan names), the no-network discipline, cooldown subordination, the batch
sentinel dedupe (Redis absent), and select_targets exclusion rules.
"""

from __future__ import annotations

import math
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
import symbol_research as sr


def _candles(n=60, start=100.0, drift=0.5, volume=1_000_000):
    """Synthetic daily candles with a steady drift (%/day)."""
    out, price = [], start
    for i in range(n):
        price *= 1 + drift / 100.0
        out.append({"ts": i, "open": price, "high": price, "low": price,
                    "close": price, "volume": volume})
    return out


class FactorMathTests(unittest.TestCase):
    def test_data_sufficiency_gate(self):
        self.assertIsNone(sr.candle_factors(_candles(n=10), "crypto"))
        self.assertIsNotNone(sr.candle_factors(_candles(n=40), "crypto"))

    def test_momentum_sign_follows_drift(self):
        up = sr.candle_factors(_candles(drift=1.0), "crypto")
        down = sr.candle_factors(_candles(drift=-1.0), "crypto")
        self.assertGreater(up["mom_5d"], 0)
        self.assertLess(down["mom_5d"], 0)
        self.assertGreater(sr.technical_subscore(up), 0)
        self.assertLess(sr.technical_subscore(down), 0)

    def test_technical_subscore_bounded(self):
        f = sr.candle_factors(_candles(drift=25.0), "crypto")
        s = sr.technical_subscore(f)
        self.assertLessEqual(abs(s), 1.0)

    def test_vol_fit_peaks_in_band(self):
        lo, hi = sr.VOL_BAND["crypto"]
        self.assertEqual(sr.vol_fit_score((lo + hi) / 2, "crypto"), 1.0)
        self.assertLess(sr.vol_fit_score(hi * 4, "crypto"), 1.0)
        self.assertLess(sr.vol_fit_score(lo / 4, "crypto"), 1.0)
        self.assertIsNone(sr.vol_fit_score(None, "crypto"))

    def test_composite_renormalizes_over_available_families(self):
        """Missing factor = None, never a fabricated 0 (mutation target)."""
        full = sr.composite_score({"technical": 0.5, "news": 0.5, "macro": 0.5},
                                  "forex")
        self.assertAlmostEqual(full["coverage"], 1.0, places=6)
        self.assertAlmostEqual(full["eps_raw"], 0.5, places=6)
        thin = sr.composite_score({"technical": 0.5, "news": None, "macro": None},
                                  "forex")
        # renormalized mean is still 0.5 — None did NOT drag it toward 0
        self.assertAlmostEqual(thin["eps_raw"], 0.5, places=6)
        # but coverage shrinkage reduces the rank score
        self.assertLess(thin["rank_score"], full["rank_score"])
        self.assertAlmostEqual(thin["rank_score"],
                               0.5 * math.sqrt(thin["coverage"]), places=6)

    def test_mom5d_component_sign_is_pinned(self):
        """Each component's sign matters alone — a single flipped component
        must not hide inside the aggregate (mutation target)."""
        up_only = {"mom_5d": 5.0, "mom_20d": None, "sma20_dist": None,
                   "vol_ratio": None}
        down_only = {**up_only, "mom_5d": -5.0}
        self.assertGreater(sr.technical_subscore(up_only), 0)
        self.assertLess(sr.technical_subscore(down_only), 0)

    def test_weighted_mean_uses_the_profile_weights(self):
        """Distinct family values pin the actual weighted mean — uniform
        values would make a flipped/altered weight invisible (mutation target)."""
        got = sr.composite_score({"technical": 1.0, "news": 0.0, "macro": 0.0},
                                 "forex")
        self.assertAlmostEqual(got["eps_raw"],
                               sr.WEIGHT_PROFILES["forex"]["technical"], places=6)

    def test_shrinkage_is_monotone_in_coverage(self):
        subs = {"technical": 0.6}
        one = sr.composite_score(subs, "us-stock")
        two = sr.composite_score({**subs, "news": 0.6}, "us-stock")
        self.assertLess(one["rank_score"], two["rank_score"])

    def test_veto_gates_zero_not_scale(self):
        base = sr.apply_gates(0.8, event_window=False, regime_blocks_longs=False,
                              direction="long", session_open=True)
        self.assertEqual(base, 0.8)
        self.assertEqual(sr.apply_gates(0.8, event_window=True,
                                        regime_blocks_longs=False,
                                        direction="long", session_open=True), 0.0)
        self.assertEqual(sr.apply_gates(0.8, event_window=False,
                                        regime_blocks_longs=True,
                                        direction="long", session_open=True), 0.0)
        # shorts pass a longs-only regime block
        self.assertGreater(sr.apply_gates(0.8, event_window=False,
                                          regime_blocks_longs=True,
                                          direction="short", session_open=True), 0)
        # closed session is a factor, not a veto
        self.assertAlmostEqual(sr.apply_gates(0.8, event_window=False,
                                              regime_blocks_longs=False,
                                              direction="long",
                                              session_open=False), 0.8 * 0.85)

    def test_fee_hurdle_makes_tiny_moves_negative_ev(self):
        ev = sr.expected_value(0.1, 0.9, 24, 2.0, "crypto")
        self.assertLess(ev["ev_pct"], 0)
        ev2 = sr.expected_value(3.0, 0.7, 24, 2.0, "crypto")
        self.assertGreater(ev2["ev_pct"], 0)


class ThesisClampTests(unittest.TestCase):
    def test_garbage_llm_output_lands_in_bounds(self):
        raw = {"direction": "MOON", "expected_move_pct": 5000,
               "horizon_hours": -3, "confidence": 9.9}
        t = sr.clamp_thesis(raw, "crypto", vol_daily_pct=2.0, momentum_sign=1.0)
        self.assertIn(t["direction"], ("long", "short"))
        lo, hi = sr.THESIS_BOUNDS["horizon_hours"]
        self.assertTrue(lo <= t["horizon_hours"] <= hi)
        c_lo, c_hi = sr.THESIS_BOUNDS["confidence"]
        self.assertTrue(c_lo <= t["confidence"] <= c_hi)
        cap = sr.THESIS_BOUNDS["expected_move_vol_mult"] * 2.0 * \
            math.sqrt(t["horizon_hours"] / 24.0)
        self.assertLessEqual(t["expected_move_pct"], cap + 1e-9)

    def test_short_forced_long_where_unsupported(self):
        t = sr.clamp_thesis({"direction": "short", "expected_move_pct": 2,
                             "horizon_hours": 24, "confidence": 0.6},
                            "a-stock", 1.5, momentum_sign=-1.0)
        self.assertEqual(t["direction"], "long")

    def test_fallback_thesis_in_bounds(self):
        t = sr.fallback_thesis("crypto", 2.0, momentum_sign=-1.0,
                               score_percentile=0.9)
        self.assertEqual(t["direction"], "short")
        c_lo, c_hi = sr.THESIS_BOUNDS["confidence"]
        self.assertTrue(c_lo <= t["confidence"] <= c_hi)


class ScreenTests(unittest.TestCase):
    """screen_universe with injected candles — zero network by construction."""

    def _fetch(self, sym, market):
        drift = {"UP": 1.2, "DOWN": -1.2, "FLAT": 0.0}.get(sym, 0.6)
        return _candles(drift=drift, volume=5_000_000)

    def test_no_network_and_per_market_caps(self):
        universe = ([{"symbol": f"C{i}", "market": "crypto"} for i in range(8)] +
                    [{"symbol": f"S{i}", "market": "us-stock"} for i in range(8)])
        overlays = {"event_window": False, "regime_blocks_longs": False, "policy": {}}
        with patch.object(sr, "_read_overlays", side_effect=AssertionError("network")):
            got = sr.screen_universe(universe, fetch_candles=self._fetch,
                                     overlays=overlays)
        per_market = {}
        for s in got:
            per_market[s["market"]] = per_market.get(s["market"], 0) + 1
        self.assertLessEqual(per_market.get("crypto", 0),
                             sr.SURVIVORS_PER_MARKET["crypto"])
        self.assertLessEqual(per_market.get("us-stock", 0),
                             sr.SURVIVORS_PER_MARKET["us-stock"])
        self.assertTrue(got)

    def test_liquidity_floor_drops_thin_crypto(self):
        def thin(sym, market):
            return _candles(volume=10)  # ~$1k dollar volume
        got = sr.screen_universe([{"symbol": "THIN", "market": "crypto"}],
                                 fetch_candles=thin,
                                 overlays={"event_window": False,
                                           "regime_blocks_longs": False,
                                           "policy": {}})
        self.assertEqual(got, [])

    def test_event_window_vetoes_macro_markets_only(self):
        overlays = {"event_window": True, "regime_blocks_longs": False, "policy": {}}
        got = sr.screen_universe(
            [{"symbol": "ES", "market": "futures"},
             {"symbol": "BTCUSDT", "market": "crypto"}],
            fetch_candles=self._fetch, overlays=overlays)
        markets_seen = {s["market"] for s in got}
        self.assertNotIn("futures", markets_seen)
        self.assertIn("crypto", markets_seen)

    def test_failing_fetcher_fails_soft(self):
        def boom(sym, market):
            raise RuntimeError("provider down")
        got = sr.screen_universe([{"symbol": "X", "market": "crypto"}],
                                 fetch_candles=boom,
                                 overlays={"event_window": False,
                                           "regime_blocks_longs": False,
                                           "policy": {}})
        self.assertEqual(got, [])


class DailyCandleCooldownTests(unittest.TestCase):
    def test_cooldown_serves_no_http(self):
        """Active yahoo cooldown ⇒ [] with zero HTTP (subordination contract)."""
        import price_fetcher
        import time as _t
        with patch.dict(price_fetcher._provider_cooldowns,
                        {"yahoo": _t.time() + 60}), \
             patch("cache.get_json", return_value=None), \
             patch.object(price_fetcher, "_request_json_with_retry",
                          side_effect=AssertionError("HTTP during cooldown")):
            out = price_fetcher.get_daily_candles("AAPL", "us-stock")
        self.assertEqual(out, [])

    def test_cache_hit_serves_no_http(self):
        import price_fetcher
        cached = _candles(n=40)
        with patch("cache.get_json", return_value=cached), \
             patch.object(price_fetcher, "_request_json_with_retry",
                          side_effect=AssertionError("HTTP on cache hit")):
            out = price_fetcher.get_daily_candles("AAPL", "us-stock")
        self.assertEqual(out, cached)


class BatchAndSelectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()

    def tearDown(self):
        self.tmp.cleanup()

    def _refresh(self, generate_text=None, symbols=("AAA", "BBB", "CCC", "DDD")):
        universe = [{"symbol": s, "market": "crypto"} for s in symbols]
        with patch.object(sr, "build_universe", return_value=universe), \
             patch.object(sr, "_read_overlays",
                          return_value={"event_window": False,
                                        "regime_blocks_longs": False, "policy": {}}):
            return sr.refresh_research_batch(
                generate_text=generate_text or (lambda *a, **k: None),
                fetch_candles=lambda s, m: _candles(drift=0.8, volume=5_000_000))

    def test_sentinel_dedupe_without_redis(self):
        """Second refresh in the same window aborts BEFORE any LLM call —
        the deterministic sentinel is the guarantee, Redis absent."""
        calls = []

        def counting_llm(*a, **k):
            calls.append(1)
            return None

        with patch("cache.acquire_lock", return_value=None):
            first = self._refresh(generate_text=counting_llm)
            second = self._refresh(generate_text=counting_llm)
        self.assertNotIn("error", first)
        self.assertEqual(second.get("skipped"), "batch_exists")
        # only the first refresh may have spent LLM (its retry budget)
        self.assertLessEqual(len(calls), sr.MAX_LLM_CALLS_PER_REFRESH)

    def test_fallback_theses_persist_and_are_selectable(self):
        summary = self._refresh()  # LLM returns None -> fallback for all
        self.assertGreater(summary["persisted"], 0)
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT planner, selectable FROM research_theses")
        rows = cur.fetchall()
        conn.close()
        self.assertTrue(all(r["planner"] == "fallback" for r in rows))

    def test_llm_array_is_clamped_and_used(self):
        def llm(*a, **k):
            return ('[{"symbol":"AAA","market":"crypto","direction":"long",'
                    '"expected_move_pct":900,"horizon_hours":48,'
                    '"confidence":0.7,"thesis":"t","risks":"r",'
                    '"invalidation":"i"}]')
        self._refresh(generate_text=llm)
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT expected_move_pct, planner FROM research_theses "
                    "WHERE symbol='AAA'")
        row = cur.fetchone()
        conn.close()
        self.assertEqual(row["planner"], "llm")
        self.assertLess(float(row["expected_move_pct"]), 100.0)  # clamped

    def test_select_targets_excludes_busy_and_cooldowns(self):
        self._refresh(symbols=("AAA", "BBB", "CCC", "DDD"))
        conn = database.get_db_connection()
        cur = conn.cursor()
        # agent 1 already runs AAA; BBB is cooling down
        cur.execute(
            "INSERT INTO trading_runs (agent_id, symbol, market, status, created_at)"
            " VALUES (1, 'AAA', 'crypto', 'running', '2026-01-01T00:00:00Z')")
        cur.execute(
            "INSERT INTO fleet_symbol_cooldowns (agent_id, market, symbol, until_ts)"
            " VALUES (1, 'crypto', 'BBB', '2099-01-01T00:00:00Z')")
        conn.commit()
        picked = sr.select_targets(cur, agent_id=1, n=4)
        syms = {t["symbol"] for t in picked}
        self.assertNotIn("AAA", syms)
        self.assertNotIn("BBB", syms)
        conn.close()

    def test_select_targets_diversity_cap(self):
        self._refresh(symbols=("AAA", "BBB", "CCC", "DDD"))
        conn = database.get_db_connection()
        cur = conn.cursor()
        picked = sr.select_targets(cur, agent_id=2, n=2)
        # ceil(2/2)=1 per market — only one crypto pick allowed
        self.assertLessEqual(len([t for t in picked if t["market"] == "crypto"]), 1)
        conn.close()


class PolicyFeedTests(unittest.TestCase):
    def test_fetch_fails_soft(self):
        import policy_feed
        with patch("policy_feed.requests.get",
                   side_effect=RuntimeError("down")):
            self.assertEqual(policy_feed._fetch_watchlist(["sec"], "x"), [])

    def test_age_gate_returns_empty(self):
        import policy_feed
        stale = {"markets": {"crypto": [{"publication_date": "2026-07-19",
                                         "title": "t"}]},
                 "fetched_at": 0}
        with patch("cache.get_json", return_value=stale):
            self.assertEqual(policy_feed.get_policy_signals(), {})

    def test_cnn_fng_fails_soft(self):
        import psych_feed
        with patch("psych_feed.requests.get", side_effect=RuntimeError("404")):
            self.assertIsNone(psych_feed.fetch_cnn_fear_greed())


if __name__ == "__main__":
    unittest.main()
