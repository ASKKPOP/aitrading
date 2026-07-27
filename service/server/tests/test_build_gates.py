"""Build-time candidate gates (2026-07-26).

Two checks moved to — or introduced at — fleet build, where they are decided
once instead of re-litigated every cycle:

  fee_infeasible      expected_move_pct is frozen in the config snapshot, so a
                      thesis that cannot clear the round-trip hurdle can NEVER
                      clear it. Prod run 114 (ZS, 1.31%) was refused on every
                      cycle and would have burned ~60 LLM calls over 7h before
                      idle-retire collected it.
  negative_expectancy the desk's directional accuracy is 35% overall (long 32%
                      / short 40%) over 40 runs. The per-(market, direction)
                      realised record is the only evidence about where any edge
                      actually lives, so a bucket that has demonstrably lost
                      stops being rebuilt.
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

import database
import fleet_planner as fp


class FeeInfeasibleTests(unittest.TestCase):
    """Pure predicate — mirrors run_engine._fee_edge_skip at build time."""

    def tearDown(self):
        os.environ.pop("RUN_FEE_EDGE_MULTIPLE", None)
        os.environ.pop("RUN_FEE_EDGE_REALIZATION", None)

    def test_thin_thesis_is_refused_before_a_run_exists(self):
        skip = fp._thesis_fee_infeasible({"expected_move_pct": 1.31})  # prod ZS
        self.assertIsNotNone(skip)
        self.assertIn("fee_infeasible", skip)

    def test_fat_thesis_builds(self):
        self.assertIsNone(fp._thesis_fee_infeasible({"expected_move_pct": 5.5}))

    def test_absent_expectation_builds(self):
        self.assertIsNone(fp._thesis_fee_infeasible({}))

    def test_matches_the_per_cycle_gate_exactly(self):
        """Build-time and per-cycle must never disagree, or a run is created
        that can only ever skip."""
        from run_engine import _fee_edge_skip
        for move in (0.4, 1.31, 2.0, 2.79, 3.43, 5.5, 6.6):
            build = fp._thesis_fee_infeasible({"expected_move_pct": move})
            cycle = _fee_edge_skip(move)
            self.assertEqual(bool(build), bool(cycle), f"disagreement at {move}%")

    def test_kill_switch_lets_everything_build(self):
        os.environ["RUN_FEE_EDGE_MULTIPLE"] = "0"
        self.assertIsNone(fp._thesis_fee_infeasible({"expected_move_pct": 0.01}))


class BucketExpectancyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO agents (name, cash) VALUES ('a', 100000)")
        conn.commit()
        conn.close()

    def tearDown(self):
        os.environ.pop("FLEET_EXPECTANCY_GATE", None)
        os.environ.pop("FLEET_EXPECTANCY_MIN_TRADES", None)
        self.tmp.cleanup()

    def _closed_run(self, market, direction, pnl):
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO trading_runs
               (agent_id, symbol, market, market_type, status, created_via,
                realized_pnl_usd, config_snapshot_json, start_condition_json,
                stop_conditions_json, created_at)
               VALUES (1,'X',?, 'futures','stopped','fleet',?,?,'{}','{}',
                       '2026-01-01T00:00:00Z')""",
            (market, pnl, json.dumps({"thesis": {"direction": direction}})))
        conn.commit()
        conn.close()

    def test_small_sample_never_vetoes(self):
        """Below the minimum the record says nothing — presumed innocent."""
        for _ in range(4):
            self._closed_run("crypto", "long", -50.0)
        self.assertIsNone(fp._bucket_expectancy_block(
            1, {"market": "crypto", "direction": "long"}))

    def test_proven_loser_bucket_is_refused(self):
        for _ in range(8):
            self._closed_run("crypto", "long", -50.0)
        block = fp._bucket_expectancy_block(
            1, {"market": "crypto", "direction": "long"})
        self.assertIsNotNone(block)
        self.assertIn("negative_expectancy", block)
        self.assertIn("-400.00", block)

    def test_profitable_bucket_still_builds(self):
        for _ in range(8):
            self._closed_run("crypto", "short", +30.0)
        self.assertIsNone(fp._bucket_expectancy_block(
            1, {"market": "crypto", "direction": "short"}))

    def test_direction_buckets_are_independent(self):
        """Long losing must not veto short — prod short 40% vs long 32%."""
        for _ in range(8):
            self._closed_run("crypto", "long", -50.0)
        for _ in range(8):
            self._closed_run("crypto", "short", +30.0)
        self.assertIsNotNone(fp._bucket_expectancy_block(
            1, {"market": "crypto", "direction": "long"}))
        self.assertIsNone(fp._bucket_expectancy_block(
            1, {"market": "crypto", "direction": "short"}))

    def test_market_buckets_are_independent(self):
        for _ in range(8):
            self._closed_run("futures", "long", -50.0)
        self.assertIsNone(fp._bucket_expectancy_block(
            1, {"market": "crypto", "direction": "long"}))

    def test_a_winning_run_can_rehabilitate_the_bucket(self):
        """The veto is on SUM, not count — one big winner reopens the bucket
        so a temporary bad patch is not a permanent ban."""
        for _ in range(8):
            self._closed_run("crypto", "long", -50.0)
        self.assertIsNotNone(fp._bucket_expectancy_block(
            1, {"market": "crypto", "direction": "long"}))
        self._closed_run("crypto", "long", +500.0)
        self.assertIsNone(fp._bucket_expectancy_block(
            1, {"market": "crypto", "direction": "long"}))

    def test_kill_switch_disables_the_veto(self):
        for _ in range(8):
            self._closed_run("crypto", "long", -50.0)
        os.environ["FLEET_EXPECTANCY_GATE"] = "false"
        self.assertIsNone(fp._bucket_expectancy_block(
            1, {"market": "crypto", "direction": "long"}))


class TrailGeometryTests(unittest.TestCase):
    """The 10:1 asymmetry (report #3): the lock armed at 1/10th of the stop,
    so the desk banked ~$6 wins against ~$67 losses — a structure needing a
    90.9% hit rate against a measured 35%."""

    def test_activation_is_at_least_the_stop(self):
        t = fp._trail_config(2276.08, 2.0, 68.28)
        self.assertGreaterEqual(t["activate_usd"], 68.28)

    def test_breakeven_hit_rate_is_no_longer_absurd(self):
        ml = 68.28
        t = fp._trail_config(2276.08, 2.0, ml)
        realized = t["activate_usd"] * (1 - t["giveback_frac"])
        breakeven = ml / (ml + realized)
        self.assertLess(breakeven, 0.60, "was 0.909 under the frac-only rule")

    def test_notional_floor_still_applies_without_a_stop(self):
        t = fp._trail_config(2276.08, 2.0, 0.0)
        self.assertAlmostEqual(t["activate_usd"], round(2276.08 * 0.003, 2))

    def test_tighten_line_stays_above_activation(self):
        """An RR-scaled activation can overtake the fee-based tighten; if it
        did, the tight band would apply the instant the lock armed and defeat
        the point of arming late."""
        t = fp._trail_config(2276.08, 2.0, 68.28)
        self.assertGreater(t["tighten_usd"], t["activate_usd"])


if __name__ == "__main__":
    unittest.main()
