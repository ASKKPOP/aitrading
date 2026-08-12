"""Plan 24 fix 5 — us-stock target selection ranks fresh 2-day movers.

Owner algorithm (2026-08-12): "AI choose target USA stock — main algorithm
is high price changed for 2 days." The trend blend kept nominating sleepy
names for a 30-minute desk (three idle-retires in one day; GLD at
−$300.66/trade over 7 closed runs topping the list every pass).
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database  # noqa: E402
import symbol_research as sr  # noqa: E402


def _candles(rets):
    """Daily candles with the given day-over-day % returns, oldest first."""
    out, price = [], 100.0
    out.append({"ts": 0, "open": price, "high": price, "low": price,
                "close": price, "volume": 5_000_000})
    for i, r in enumerate(rets, start=1):
        price *= 1 + r / 100.0
        out.append({"ts": i, "open": price, "high": price, "low": price,
                    "close": price, "volume": 5_000_000})
    return out


class Mom2dFactorTests(unittest.TestCase):
    def test_mom_2d_is_the_two_day_return(self):
        # flat for 28 days, then +3% and +2.9126% -> exactly +6% over 2 days
        f = sr.candle_factors(_candles([0.0] * 28 + [3.0, 2.9126]), "us-stock")
        self.assertIsNotNone(f)
        self.assertAlmostEqual(f["mom_2d"], 6.0, places=1)


class MoverRankTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "t.db")
        database.init_database()
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO agents (id, name, token, starting_capital)"
                    " VALUES (9, 'mv', 't', 1000.0)")
        rows = [
            # symbol, market, final, mom_2d, vol_ratio
            ("SLEEPY", "us-stock", 0.90, 0.4, 1.0),   # trend name, tops final
            ("MOVER", "us-stock", 0.60, 6.2, 2.0),    # the 2-day mover
            ("BTCUSDT", "crypto", 0.95, 8.0, 3.0),    # crypto ignores mover rank
        ]
        for sym, market, final, m2, vr in rows:
            fs = json.dumps({"factors": {"mom_2d": m2, "vol_ratio": vr}})
            cur.execute(
                """INSERT INTO research_theses
                   (batch_id, market, symbol, market_type, direction,
                    factor_scores_json, thesis, expected_move_pct,
                    horizon_hours, confidence, ev_per_day_pct, final_score,
                    selectable, planner, created_at, expires_at)
                   VALUES ('b1', ?, ?, 'spot', 'long', ?, 't', 5.0, 24.0,
                           0.7, 1.0, ?, 1, 'p', '2026-08-12T00:00:00Z',
                           '2099-01-01T00:00:00Z')""",
                (market, sym, fs, final))
        conn.commit()
        conn.close()

    def tearDown(self):
        self.tmp.cleanup()

    def _select(self, n=3, scope=None):
        conn = database.get_db_connection()
        try:
            return sr.select_targets(conn.cursor(), 9, n,
                                     markets_scope=scope)
        finally:
            conn.close()

    def test_us_stock_mover_outranks_the_trend_name(self):
        picks = [t["symbol"] for t in self._select(scope=["us-stock"])]
        self.assertEqual(picks[0], "MOVER",
                         "the 2-day mover must lead the us-stock ranking")
        self.assertIn("SLEEPY", picks)

    def test_cross_market_ordering_is_untouched(self):
        """Mover ranking reorders us-stock among its own slots only — the
        crypto thesis keeps its final_score position at the top."""
        picks = [t["symbol"] for t in self._select()]
        self.assertEqual(picks[0], "BTCUSDT")
        self.assertLess(picks.index("MOVER"), picks.index("SLEEPY"))

    def test_old_batches_without_mom_2d_keep_final_order(self):
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE research_theses SET factor_scores_json = '{}' "
                    "WHERE market = 'us-stock'")
        conn.commit()
        conn.close()
        picks = [t["symbol"] for t in self._select(scope=["us-stock"])]
        self.assertEqual(picks[0], "SLEEPY",
                         "no mover data ⇒ final_score order stands")


if __name__ == "__main__":
    unittest.main()
