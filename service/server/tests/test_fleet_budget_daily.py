"""Daily compounding of the fleet's working capital.

Owner 2026-08-09: the fleet's trading budget should grow/shrink each day by
realized profit — seed + Σ realized P&L — never by unrealized, and without
ever touching an open position.
"""
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
import fleet_budget_daily


class FleetBudgetDailyTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        fleet_budget_daily._last_day = None
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO agents (id, name, token, starting_capital)"
                    " VALUES (6, 'a', 't', 1000.0)")
        cur.execute("INSERT INTO fleets (id, agent_id, name, status, n_runs,"
                    " total_budget_usd, risk_appetite, active_fleet_key, created_at)"
                    " VALUES (28, 6, 'f', 'active', 10, 1000.0, 'aggressive',"
                    " 'user:1', '2026-08-09T00:00:00Z')")
        conn.commit()
        conn.close()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _budget(self) -> float:
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT total_budget_usd FROM fleets WHERE id = 28")
        v = float(dict(cur.fetchone())["total_budget_usd"])
        conn.close()
        return v

    def _add_run(self, run_id: int, realized: float, status="stopped") -> None:
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO trading_runs (id, agent_id, symbol, market, status,"
            " realized_pnl_usd, created_at) VALUES (?, 6, 'X', 'crypto', ?, ?,"
            " '2026-08-09T00:00:00Z')",
            (run_id, status, realized))
        conn.commit()
        conn.close()

    def test_profit_raises_the_budget(self):
        self._add_run(1, 5.0)
        self._add_run(2, -1.5)   # net realized +3.5
        changed = fleet_budget_daily.compound_fleet_budgets()
        self.assertAlmostEqual(self._budget(), 1003.5, places=2)
        self.assertEqual(len(changed), 1)
        self.assertAlmostEqual(changed[0]["to"], 1003.5, places=2)

    def test_loss_lowers_the_budget(self):
        self._add_run(1, -12.0)
        fleet_budget_daily.compound_fleet_budgets()
        self.assertAlmostEqual(self._budget(), 988.0, places=2)

    def test_realized_only_open_run_unrealized_is_ignored(self):
        # A running run carries realized on closed legs only; this row's
        # realized column IS the realized figure — unrealized never enters.
        self._add_run(1, 2.0, status="running")   # realized so far +2
        fleet_budget_daily.compound_fleet_budgets()
        self.assertAlmostEqual(self._budget(), 1002.0, places=2)

    def test_no_change_is_not_written(self):
        # zero realized ⇒ budget already equals seed ⇒ no update row
        changed = fleet_budget_daily.compound_fleet_budgets()
        self.assertEqual(changed, [])
        self.assertAlmostEqual(self._budget(), 1000.0, places=2)

    def test_budget_is_clamped_to_bounds(self):
        self._add_run(1, -100000.0)   # would drive below the floor
        fleet_budget_daily.compound_fleet_budgets()
        lo, _ = fleet_budget_daily.FLEET_BOUNDS["total_budget_usd"]
        self.assertAlmostEqual(self._budget(), lo, places=2)

    def test_terminal_fleet_is_not_compounded(self):
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE fleets SET status = 'stopped' WHERE id = 28")
        conn.commit()
        conn.close()
        self._add_run(1, 5.0)
        changed = fleet_budget_daily.compound_fleet_budgets()
        self.assertEqual(changed, [])
        self.assertAlmostEqual(self._budget(), 1000.0, places=2)

    def test_maybe_compound_runs_once_per_utc_day(self):
        self._add_run(1, 5.0)
        first = fleet_budget_daily.maybe_compound("2026-08-09")
        self.assertTrue(first and first["changed"])
        # same day again → throttled, no second write even if realized moved
        self._add_run(2, 5.0)
        second = fleet_budget_daily.maybe_compound("2026-08-09")
        self.assertIsNone(second)
        self.assertAlmostEqual(self._budget(), 1005.0, places=2)  # unchanged
        # next day → recompute picks up the new realized (+10)
        third = fleet_budget_daily.maybe_compound("2026-08-10")
        self.assertTrue(third and third["changed"])
        self.assertAlmostEqual(self._budget(), 1010.0, places=2)

    def test_kill_switch_disables_it(self):
        self._add_run(1, 5.0)
        with patch.dict(os.environ, {"FLEET_BUDGET_DAILY": "0"}):
            out = fleet_budget_daily.maybe_compound("2026-08-09")
        self.assertIsNone(out)
        self.assertAlmostEqual(self._budget(), 1000.0, places=2)


if __name__ == "__main__":
    unittest.main()
