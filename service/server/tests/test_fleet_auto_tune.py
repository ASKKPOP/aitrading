"""AI auto-tuning of a fleet's slot count and take-profit goal.

Owner 2026-08-12: the Edit-fleet slot count and profit goal % are set by the
AI's analysis (slots = fee-viable rec; goal = derived from the fleet's own
realized edge), continuously, never touching a live position.
"""
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
import fleet_auto_tune


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


class GoalDerivationTestCase(unittest.TestCase):
    """recommended_profit_goal_frac is a pure function of the edge."""

    def test_positive_edge_maps_to_in_band_goal(self):
        # $140 realized over 14 days on a $1000 budget = $10/day → 14-day
        # horizon projects $140 → 14% goal.
        g = fleet_auto_tune.recommended_profit_goal_frac(1000.0, 140.0, 14.0, 10)
        self.assertAlmostEqual(g, 0.14, places=3)

    def test_weak_edge_clamped_to_floor(self):
        g = fleet_auto_tune.recommended_profit_goal_frac(1000.0, 10.0, 14.0, 10)
        self.assertAlmostEqual(g, fleet_auto_tune._GOAL_LO, places=4)

    def test_strong_edge_clamped_to_cap(self):
        g = fleet_auto_tune.recommended_profit_goal_frac(1000.0, 5000.0, 14.0, 10)
        self.assertAlmostEqual(g, fleet_auto_tune._GOAL_HI, places=4)

    def test_young_fleet_returns_none(self):
        self.assertIsNone(
            fleet_auto_tune.recommended_profit_goal_frac(1000.0, 140.0, 0.5, 10))

    def test_too_few_closed_runs_returns_none(self):
        self.assertIsNone(
            fleet_auto_tune.recommended_profit_goal_frac(1000.0, 140.0, 14.0, 2))

    def test_no_positive_edge_returns_none(self):
        self.assertIsNone(
            fleet_auto_tune.recommended_profit_goal_frac(1000.0, -5.0, 14.0, 10))


class AutoTuneFleetsTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        fleet_auto_tune._last_run_epoch = None
        # 14 days old so a positive-edge goal is derivable and deterministic.
        self.created = _iso(datetime.now(timezone.utc) - timedelta(days=14))
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO agents (id, name, token, starting_capital)"
                    " VALUES (6, 'a', 't', 1000.0)")
        cur.execute(
            "INSERT INTO fleets (id, agent_id, name, status, n_runs,"
            " total_budget_usd, risk_appetite, active_fleet_key, created_at,"
            " started_at) VALUES (28, 6, 'f', 'active', 10, 300.0, 'aggressive',"
            " 'user:1', ?, ?)", (self.created, self.created))
        conn.commit()
        conn.close()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _fleet(self) -> dict:
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT n_runs, total_budget_usd, profit_target_frac"
                    " FROM fleets WHERE id = 28")
        row = dict(cur.fetchone())
        conn.close()
        return row

    def _add_runs(self, n: int, realized_each: float) -> None:
        conn = database.get_db_connection()
        cur = conn.cursor()
        for i in range(n):
            cur.execute(
                "INSERT INTO trading_runs (agent_id, fleet_id, symbol, market,"
                " status, realized_pnl_usd, created_at) VALUES"
                " (6, 28, 'X', 'crypto', 'stopped', ?, ?)",
                (realized_each, self.created))
        conn.commit()
        conn.close()

    def test_slots_lowered_to_recommendation(self):
        # budget $300 ⇒ rec 3 slots ⇒ lower from 10 (lowering needs no cap).
        fleet_auto_tune.auto_tune_fleets()
        self.assertEqual(self._fleet()["n_runs"], 3)

    def test_goal_set_from_positive_edge(self):
        # 6 closed runs, $140 realized, 14 days old ⇒ ~14% goal.
        self._add_runs(6, 140.0 / 6)
        fleet_auto_tune.auto_tune_fleets()
        goal = self._fleet()["profit_target_frac"]
        self.assertIsNotNone(goal)
        self.assertGreater(float(goal), fleet_auto_tune._GOAL_LO)
        self.assertLessEqual(float(goal), fleet_auto_tune._GOAL_HI)

    def test_no_edge_leaves_goal_untouched(self):
        self._add_runs(6, -3.0)   # net negative realized
        fleet_auto_tune.auto_tune_fleets()
        self.assertIsNone(self._fleet()["profit_target_frac"])

    def test_terminal_fleet_is_not_tuned(self):
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE fleets SET status = 'stopped' WHERE id = 28")
        conn.commit()
        conn.close()
        self._add_runs(6, 140.0 / 6)
        changed = fleet_auto_tune.auto_tune_fleets()
        self.assertEqual(changed, [])
        self.assertEqual(self._fleet()["n_runs"], 10)   # unchanged

    def test_maybe_tune_throttles_within_interval(self):
        first = fleet_auto_tune.maybe_tune(1000.0)
        self.assertIsNotNone(first)
        # same window → throttled
        self.assertIsNone(fleet_auto_tune.maybe_tune(1000.0 + 10))
        # past the interval → runs again
        self.assertIsNotNone(
            fleet_auto_tune.maybe_tune(1000.0 + fleet_auto_tune._INTERVAL_S + 1))

    def test_kill_switch_disables_it(self):
        with patch.dict(os.environ, {"FLEET_AUTO_TUNE": "0"}):
            self.assertIsNone(fleet_auto_tune.maybe_tune(1000.0))
        self.assertEqual(self._fleet()["n_runs"], 10)   # untouched


if __name__ == "__main__":
    unittest.main()
