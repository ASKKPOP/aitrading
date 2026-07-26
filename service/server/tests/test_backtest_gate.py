"""Expectancy gate (plan #1-D, 2026-07-25): no strategy deploys capital
without a measured, positive, net-of-fees edge.

At fleet composition, every candidate symbol is scored by replaying the
validated Phase-4 deterministic strategy (backtest_strategy.simulate — fees
included) over recent daily bars. Candidates whose closed-trade expectancy is
non-positive are DROPPED before a slot is bound; too little history to judge
is fail-open (kept, journaled) unless BACKTEST_GATE_STRICT. Gated by
BACKTEST_GATE_ENABLED (default off); per-day per-symbol verdicts are cached.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import backtest_gate as bg


def _stats(n=12, mean_pnl=5.0, win_rate=0.5):
    return {"n_trades": n, "expectancy_usd": mean_pnl, "win_rate": win_rate,
            "wilson_lb": max(0.0, win_rate - 0.15)}


class VerdictTests(unittest.TestCase):
    def test_positive_expectancy_passes(self):
        v = bg._verdict(_stats(mean_pnl=12.0))
        self.assertTrue(v["eligible"])

    def test_non_positive_expectancy_drops(self):
        v = bg._verdict(_stats(mean_pnl=-3.0))
        self.assertFalse(v["eligible"])
        self.assertIn("expectancy", v["reason"])

    def test_insufficient_history_fails_open_by_default(self):
        os.environ.pop("BACKTEST_GATE_STRICT", None)
        v = bg._verdict(_stats(n=2))
        self.assertTrue(v["eligible"])
        self.assertIn("insufficient", v["reason"])

    def test_insufficient_history_drops_when_strict(self):
        os.environ["BACKTEST_GATE_STRICT"] = "true"
        try:
            v = bg._verdict(_stats(n=2))
            self.assertFalse(v["eligible"])
        finally:
            os.environ.pop("BACKTEST_GATE_STRICT", None)

    def test_env_gate_default_off(self):
        os.environ.pop("BACKTEST_GATE_ENABLED", None)
        self.assertFalse(bg.gate_enabled())


class GateCandidatesTests(unittest.TestCase):
    THESES = [{"symbol": "GOOD", "market": "crypto"},
              {"symbol": "BAD", "market": "crypto"},
              {"symbol": "THIN", "market": "crypto"}]

    def test_filters_by_symbol_expectancy(self):
        def fake_exp(symbol, market, days=120):
            return {"GOOD": _stats(mean_pnl=9.0),
                    "BAD": _stats(mean_pnl=-4.0),
                    "THIN": _stats(n=1)}[symbol]
        with patch.object(bg, "symbol_expectancy", side_effect=fake_exp):
            kept, dropped = bg.gate_candidates(list(self.THESES))
        self.assertEqual([t["symbol"] for t in kept], ["GOOD", "THIN"])
        self.assertEqual(list(dropped.keys()), ["BAD"])
        self.assertIn("expectancy", dropped["BAD"])

    def test_scoring_failure_fails_open(self):
        with patch.object(bg, "symbol_expectancy",
                          side_effect=RuntimeError("no data feed")):
            kept, dropped = bg.gate_candidates(list(self.THESES))
        self.assertEqual(len(kept), 3)
        self.assertEqual(dropped, {})


class BarsAdapterTests(unittest.TestCase):
    def test_candles_adapt_to_simulate_bars(self):
        candles = [{"ts": "2026-01-0%d" % d, "open": 10 + d, "close": 11 + d,
                    "high": 12, "low": 9, "volume": None} for d in range(1, 6)]
        bars = bg._bars_from_candles(candles)
        self.assertEqual(len(bars), 5)
        self.assertEqual(set(bars[0].keys()), {"date", "open", "close", "volume"})
        self.assertEqual(bars[0]["volume"], 0.0)   # None-safe


class FleetWiringTests(unittest.TestCase):
    """_do_research consults the gate when enabled: dropped candidates never
    get slots; the decision is journaled as a backtest_gate fleet event."""

    def test_research_drops_gated_candidates(self):
        from test_fleet_planner import FleetTestBase, _seed_batch
        import fleet_planner as fp

        class _T(FleetTestBase):
            def runTest(self):  # noqa: N802
                _seed_batch()
                fleet_id = self._fleet(n=2, budget=1000.0)
                fp.start_fleet(fleet_id, self.agent_id)
                os.environ["BACKTEST_GATE_ENABLED"] = "true"

                def fake_exp(symbol, market, days=120):
                    # first-ranked symbol AAA fails the gate; everything else passes
                    if symbol == "AAA":
                        return _stats(mean_pnl=-8.0)
                    return _stats(mean_pnl=6.0)
                try:
                    with patch.object(bg, "symbol_expectancy",
                                      side_effect=fake_exp):
                        fp._do_research(fp.get_fleet(fleet_id))
                finally:
                    os.environ.pop("BACKTEST_GATE_ENABLED", None)
                import database
                conn = database.get_db_connection()
                cur = conn.cursor()
                cur.execute("SELECT thesis_key FROM fleet_candidates WHERE "
                            "fleet_id = ?", (fleet_id,))
                keys = [r["thesis_key"] for r in cur.fetchall()]
                cur.execute("SELECT payload FROM fleet_events WHERE fleet_id = ?"
                            " AND event_type = 'backtest_gate'", (fleet_id,))
                ev = cur.fetchone()
                conn.close()
                assert keys, "no candidates bound"
                assert all("AAA" not in k for k in keys), keys
                assert ev is not None, "backtest_gate event not journaled"
                assert "AAA" in ev["payload"]

        t = _T()
        t.setUp()
        try:
            t.runTest()
        finally:
            t.tearDown()


if __name__ == "__main__":
    unittest.main()
