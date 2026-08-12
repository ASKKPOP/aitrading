"""Plan 23 Phase C1 — swing universe filter + gap-sized risk, decided at
build (the exposure-feasibility precedent: an unsizable overnight hold must
never become a run that churns).

swing_symbol_check: coded eligibility (>=180 bars, price >= $10, ADV20 >=
$50M) and G = max(P99 overnight gap, 2xATR20/price, 3% floor), fail-closed.
swing_gate_candidates: pre-build gate (no-op for short fleets), earnings
guard when the feed can see a print. compose: swing max_bet capped at
R/G with R = 1% of fleet budget, leverage pinned 1.0.
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

import database
import fleet_planner as fp


def _bars(n=260, price=100.0, vol=1_000_000.0, gap_every=0, gap_pct=0.0):
    """Daily bars; optionally an |gap_pct| open-gap every `gap_every` bars."""
    out = []
    prev_close = price
    for i in range(n):
        o = prev_close
        if gap_every and i and i % gap_every == 0:
            o = prev_close * (1 + gap_pct / 100.0)
        c = o
        out.append({"date": f"d{i:03d}", "open": o, "high": max(o, c) * 1.01,
                    "low": min(o, c) * 0.99, "close": c, "volume": vol})
        prev_close = c
    return out


class SymbolCheck(unittest.TestCase):
    def _check(self, bars):
        with patch("price_fetcher.get_daily_candles", return_value=bars):
            return fp.swing_symbol_check("MSFT")

    def test_deep_seasoned_name_is_eligible_with_floored_g(self):
        g, why = self._check(_bars())
        self.assertIsNone(why)
        self.assertGreaterEqual(g, fp.SWING_G_FLOOR)

    def test_gap_history_raises_g_above_the_floor(self):
        # 6% overnight gaps every 20 sessions push P99 above the 3% floor
        g, why = self._check(_bars(gap_every=20, gap_pct=6.0))
        self.assertIsNone(why)
        self.assertGreater(g, fp.SWING_G_FLOOR)

    def test_thin_history_refused(self):
        g, why = self._check(_bars(n=100))
        self.assertIsNone(g)
        self.assertIn("swing_history_thin", why)

    def test_low_price_refused(self):
        g, why = self._check(_bars(price=4.0))
        self.assertIsNone(g)
        self.assertIn("swing_price_low", why)

    def test_thin_dollar_volume_refused(self):
        g, why = self._check(_bars(vol=1000.0))
        self.assertIsNone(g)
        self.assertIn("swing_adv_thin", why)

    def test_dead_feed_is_fail_closed(self):
        with patch("price_fetcher.get_daily_candles",
                   side_effect=RuntimeError("yahoo down")):
            g, why = fp.swing_symbol_check("MSFT")
        self.assertIsNone(g)
        self.assertIn("swing_data_unavailable", why)


class GateCandidates(unittest.TestCase):
    def _fleet(self, archetype="swing"):
        return {"id": 1, "archetype": archetype, "total_budget_usd": 10000.0}

    def test_short_fleets_are_untouched(self):
        theses = [{"symbol": "ANY"}]
        kept, dropped = fp.swing_gate_candidates(self._fleet("short"), theses)
        self.assertIs(kept, theses)
        self.assertEqual(dropped, {})

    def test_kept_theses_carry_g_dropped_carry_reasons(self):
        def candles(sym, market, days=260):
            return _bars() if sym == "GOOD" else _bars(n=50)
        with patch("price_fetcher.get_daily_candles", side_effect=candles), \
             patch("fmp_feed.days_to_earnings", return_value=None):
            kept, dropped = fp.swing_gate_candidates(
                self._fleet(), [{"symbol": "GOOD"}, {"symbol": "THIN"}])
        self.assertEqual([t["symbol"] for t in kept], ["GOOD"])
        self.assertGreaterEqual(kept[0]["swing_g_frac"], fp.SWING_G_FLOOR)
        self.assertIn("swing_history_thin", dropped["THIN"])

    def test_imminent_earnings_print_is_refused(self):
        with patch("price_fetcher.get_daily_candles", return_value=_bars()), \
             patch("fmp_feed.days_to_earnings", return_value=1):
            kept, dropped = fp.swing_gate_candidates(
                self._fleet(), [{"symbol": "MSFT"}])
        self.assertEqual(kept, [])
        self.assertIn("earnings_window", dropped["MSFT"])

    def test_unknown_earnings_date_is_allowed_not_guessed(self):
        with patch("price_fetcher.get_daily_candles", return_value=_bars()), \
             patch("fmp_feed.days_to_earnings", return_value=None):
            kept, dropped = fp.swing_gate_candidates(
                self._fleet(), [{"symbol": "MSFT"}])
        self.assertEqual(len(kept), 1)


class ComposeGapSizing(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()

    def tearDown(self):
        self.tmp.cleanup()

    def _thesis(self, g=None):
        t = {"symbol": "MSFT", "market": "us-stock", "direction": "long",
             "expected_move_pct": 3.0, "horizon_hours": 48,
             "confidence": 0.7}
        if g is not None:
            t["swing_g_frac"] = g
        return t

    def _fleet(self, archetype="swing", budget=10000.0):
        return {"id": 1, "archetype": archetype, "risk_appetite": "balanced",
                "total_budget_usd": budget, "provider": None, "lang": "en",
                "leverage": 3.0}

    def test_swing_bet_is_capped_at_r_over_g_and_leverage_pinned(self):
        # R = 1% of $10k = $100; G = 5% -> notional cap $2,000, below the
        # balanced 30% x $5k = $1,500? (1500 < 2000 -> tier cap already
        # tighter). Use G = 20% to make the gap cap the binding one: $500.
        s = fp.compose_run_settings(self._thesis(g=0.20), 5000.0,
                                    self._fleet())
        self.assertEqual(s["max_bet_usd"], 500.0)
        self.assertEqual(s["leverage"], 1.0)
        self.assertEqual(s["archetype"], "swing")
        # the overnight-cap pass reads G from the frozen snapshot thesis
        self.assertEqual(s["thesis"]["swing_g_frac"], 0.20)

    def test_swing_without_g_fetches_and_fails_closed_on_dead_feed(self):
        with patch("price_fetcher.get_daily_candles",
                   side_effect=RuntimeError("down")):
            with self.assertRaises(ValueError):
                fp.compose_run_settings(self._thesis(), 5000.0, self._fleet())

    def test_short_compose_is_unchanged(self):
        s = fp.compose_run_settings(
            {**self._thesis(), "market": "crypto", "symbol": "BTC"},
            5000.0, self._fleet(archetype="short"))
        self.assertEqual(s["archetype"], "short")
        self.assertEqual(s["leverage"], 3.0)     # fleet leverage honored


if __name__ == "__main__":
    unittest.main()
