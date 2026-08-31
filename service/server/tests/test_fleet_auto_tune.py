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

    def test_a_user_resize_pins_the_size_against_a_raise(self):
        """Owner decision 2026-08-15 (live n=2 on fleet 34): the user resized
        25 -> 10 at 03:21:42Z and auto_tune_slots raised it straight back to
        25 at 03:49:14Z — the second override of an explicit user size in one
        day, and the 9 runs it then built sat in slots the user had just
        deleted. recommended_max_slots knows the budget, not the intent.

        A size set through the resize API is now a CAP: auto-tune may still
        LOWER below it (a fee-viability shrink is safety), but never raise
        above it. The pin lasts until the user resizes again."""
        conn = database.get_db_connection()
        cur = conn.cursor()
        # big budget => rec well above 4; the user chose 4.
        cur.execute("UPDATE fleets SET total_budget_usd = 100000 WHERE id = 28")
        conn.commit()
        conn.close()
        import fleet_planner
        with patch("entitlements.limits_for_agent",
                   return_value=("professional", {"max_fleet_size": 25})):
            fleet_planner.set_fleet_size(28, 4, user_set=True)
            fleet_auto_tune.auto_tune_fleets()
        self.assertEqual(self._fleet()["n_runs"], 4,
                         "auto-tune raised a fleet above the size the user "
                         "explicitly chose")

    def test_auto_tune_never_changes_a_pinned_size(self):
        """OWNER 2026-08-31 ('when user make trading count, must be keep
        that'): a user-chosen size is pinned in BOTH directions — the old
        fee-viability shrink becomes an advisory event, not a resize."""
        import fleet_planner
        # budget $300 => rec 3; the user pinned 8. The count must stay 8.
        fleet_planner.set_fleet_size(28, 8, user_set=True)
        fleet_auto_tune.auto_tune_fleets()
        self.assertEqual(self._fleet()["n_runs"], 8)
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT event_type FROM fleet_events WHERE fleet_id = 28")
            kinds = [r["event_type"] for r in cur.fetchall()]
        finally:
            conn.close()
        self.assertIn("auto_tune_slots_advisory", kinds)
        self.assertNotIn("auto_tune_slots", kinds)

    def test_an_unpinned_fleet_keeps_the_old_behaviour(self):
        """NULL cap = every fleet created before this change: auto-tune may
        raise toward the recommendation exactly as before."""
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE fleets SET total_budget_usd = 100000, n_runs = 10"
                    " WHERE id = 28")
        conn.commit()
        conn.close()
        with patch("entitlements.limits_for_agent",
                   return_value=("professional", {"max_fleet_size": 25})):
            fleet_auto_tune.auto_tune_fleets()
        self.assertGreater(self._fleet()["n_runs"], 10,
                           "an unpinned fleet should still grow to the rec")

    def test_a_new_user_resize_replaces_the_pin(self):
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE fleets SET total_budget_usd = 100000 WHERE id = 28")
        conn.commit()
        conn.close()
        import fleet_planner
        with patch("entitlements.limits_for_agent",
                   return_value=("professional", {"max_fleet_size": 25})):
            fleet_planner.set_fleet_size(28, 4, user_set=True)
            fleet_planner.set_fleet_size(28, 12, user_set=True)
            fleet_auto_tune.auto_tune_fleets()
        self.assertEqual(self._fleet()["n_runs"], 12,
                         "the newer user size must be the cap")

    def test_an_auto_tune_resize_does_not_create_a_pin(self):
        """Only the USER's hand pins. set_fleet_size called without user_set
        (auto-tune's own path) must leave the cap untouched."""
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE fleets SET total_budget_usd = 100000, n_runs = 10"
                    " WHERE id = 28")
        conn.commit()
        conn.close()
        import fleet_planner
        with patch("entitlements.limits_for_agent",
                   return_value=("professional", {"max_fleet_size": 25})):
            fleet_planner.set_fleet_size(28, 6)      # machine path, no pin
            fleet_auto_tune.auto_tune_fleets()
        self.assertGreater(self._fleet()["n_runs"], 6,
                           "a machine resize must not pin the size")

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
