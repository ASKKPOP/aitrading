"""Confidence recalibration (2026-07-26): gate on percentile rank, not on a
raw scalar the model never reaches.

Prod distribution over 7 days: 261 decisions at exactly 0.58, 137 at exactly
0.62, and only 13 all week at or above the 0.65 gate — the anchors are prompt
artefacts, so an absolute threshold rejects on noise. Rank grades a decision
against the agent's own recent output; a low absolute floor stays underneath
so a uniformly bad tape cannot promote its least-bad idea.
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
import run_engine


class PercentileRankTests(unittest.TestCase):
    def test_empty_sample_ranks_top(self):
        self.assertEqual(run_engine.percentile_rank(0.5, []), 1.0)

    def test_midrank_splits_ties(self):
        """The prod pileup: 0.58 against a wall of 0.58s must land mid-pack,
        not at 0% or 100% — either extreme would make the gate meaningless."""
        self.assertAlmostEqual(run_engine.percentile_rank(0.58, [0.58] * 10), 0.5)

    def test_ranks_against_a_spread(self):
        sample = [0.50, 0.55, 0.58, 0.62, 0.70]
        self.assertAlmostEqual(run_engine.percentile_rank(0.70, sample), 0.9)
        self.assertAlmostEqual(run_engine.percentile_rank(0.50, sample), 0.1)

    def test_value_above_everything_ranks_top(self):
        self.assertAlmostEqual(run_engine.percentile_rank(0.99, [0.1, 0.2]), 1.0)


class ConfidenceGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO agents (name, cash) VALUES ('a', 100000)")
        cur.execute(
            "INSERT INTO trading_runs (agent_id, symbol, market, market_type,"
            " status, config_snapshot_json, start_condition_json,"
            " stop_conditions_json, created_at) VALUES (1,'BTC','crypto',"
            "'spot','running','{}','{}','{}','2026-01-01T00:00:00Z')")
        conn.commit()
        conn.close()
        self._seq = 0

    def tearDown(self):
        for key in ("RUN_CONF_PERCENTILE", "RUN_CONF_PERCENTILE_MIN",
                    "RUN_CONF_PERCENTILE_MIN_SAMPLES", "RUN_CONF_ABS_FLOOR"):
            os.environ.pop(key, None)
        self.tmp.cleanup()

    def _decisions(self, confidences):
        conn = database.get_db_connection()
        cur = conn.cursor()
        for conf in confidences:
            self._seq += 1
            cur.execute(
                "INSERT INTO run_events (run_id, seq, event_type, ts, payload)"
                " VALUES (1, ?, 'decision', '2026-01-01T00:00:00Z', ?)",
                (self._seq, json.dumps({"confidence": conf})))
        conn.commit()
        conn.close()

    def test_too_few_samples_falls_back_to_absolute_threshold(self):
        self._decisions([0.58] * 5)
        skip, eff = run_engine._conf_percentile_skip(1, 0.62, 0.65)
        self.assertIsNone(skip)
        self.assertEqual(eff, 0.65, "must hand the original gate back untouched")

    def test_top_of_the_distribution_passes_below_the_old_threshold(self):
        """The headline fix: 0.62 never cleared the 0.65 gate, but against a
        wall of 0.58s it is genuinely the agent's strongest read."""
        self._decisions([0.58] * 40)
        skip, eff = run_engine._conf_percentile_skip(1, 0.62, 0.65)
        self.assertIsNone(skip)
        self.assertEqual(eff, run_engine._conf_abs_floor(),
                         "rank did the discriminating; only the floor remains")

    def test_middle_of_the_pack_is_refused(self):
        self._decisions([0.58] * 20 + [0.70] * 20)
        skip, _ = run_engine._conf_percentile_skip(1, 0.58, 0.65)
        self.assertIsNotNone(skip)
        self.assertIn("ranks", skip)

    def test_absolute_floor_still_rejects_a_weak_read(self):
        """Rank alone must not promote garbage: in a uniformly terrible tape
        the best of a bad bunch still fails the floor."""
        self._decisions([0.20] * 40)
        skip, _ = run_engine._conf_percentile_skip(1, 0.30, 0.65)
        self.assertIsNotNone(skip)
        self.assertIn("absolute floor", skip)

    def test_disabled_returns_original_threshold(self):
        self._decisions([0.58] * 40)
        os.environ["RUN_CONF_PERCENTILE"] = "false"
        skip, eff = run_engine._conf_percentile_skip(1, 0.62, 0.65)
        self.assertIsNone(skip)
        self.assertEqual(eff, 0.65)

    def test_missing_confidence_is_left_alone(self):
        self._decisions([0.58] * 40)
        skip, eff = run_engine._conf_percentile_skip(1, None, 0.65)
        self.assertIsNone(skip)
        self.assertEqual(eff, 0.65)

    def test_required_rank_is_configurable(self):
        self._decisions([0.58] * 20 + [0.62] * 20)
        os.environ["RUN_CONF_PERCENTILE_MIN"] = "0.95"
        skip, _ = run_engine._conf_percentile_skip(1, 0.62, 0.65)
        self.assertIsNotNone(skip, "0.62 midranks at 75% — below a 95% bar")

    def test_only_this_agents_history_is_graded(self):
        """Another agent's decisions must not set this agent's bar."""
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO agents (name, cash) VALUES ('b', 100000)")
        cur.execute(
            "INSERT INTO trading_runs (agent_id, symbol, market, market_type,"
            " status, config_snapshot_json, start_condition_json,"
            " stop_conditions_json, created_at) VALUES (2,'ETH','crypto',"
            "'spot','running','{}','{}','{}','2026-01-01T00:00:00Z')")
        for i in range(40):                       # agent 2 runs hot
            cur.execute(
                "INSERT INTO run_events (run_id, seq, event_type, ts, payload)"
                " VALUES (2, ?, 'decision', '2026-01-01T00:00:00Z', ?)",
                (i + 1, json.dumps({"confidence": 0.95})))
        conn.commit()
        conn.close()
        self._decisions([0.58] * 40)              # agent 1 runs cold
        skip, _ = run_engine._conf_percentile_skip(1, 0.62, 0.65)
        self.assertIsNone(skip, "agent 2's 0.95s must not raise agent 1's bar")


if __name__ == "__main__":
    unittest.main()
