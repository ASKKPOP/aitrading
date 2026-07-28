"""Thesis decay (2026-07-28).

`_unactionable_streak` catches the desk CONTRADICTING its thesis — a long book
being told to sell. It cannot catch the desk quietly abandoning one.

Live, run 345 (ZC), built on an AI thesis reading "corn shows robust positive
momentum, 18% over 20 days":

    cycle 1   thesis_alignment 0.70   momentum 0.62   -> traded
    cycle 3   thesis_alignment 0.35   momentum 0.20   -> hold
    cycle 4   thesis_alignment 0.30   momentum 0.15   -> hold
    cycle 5   thesis_alignment 0.30   momentum 0.20   -> hold

Every decision was `hold`, so no rail fired, and the position sat on a thesis
its own author had marked down by more than half. The two existing rails both
require a FLAT run; this one is the only rail that applies while holding,
which is the whole point — a flat run with a dead thesis wastes a slot, a
holding one carries risk for a reason nobody believes.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
import fleet_planner
import run_engine


def _run(run_id=345):
    return {"id": run_id, "agent_id": 6, "symbol": "ZC", "market": "futures",
            "status": "running", "cycle_seq": 5,
            "config_snapshot_json": json.dumps(
                {"symbol": "ZC", "market": "futures",
                 "thesis": {"expected_move_pct": 3.5}}),
            "stop_conditions_json": "{}"}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "t.db")
        database.init_database()
        self._seq = 0

    def tearDown(self):
        self.tmp.cleanup()

    def decisions(self, aligns, run_id=345):
        """Write decisions oldest-first; the rail reads newest-first."""
        conn = database.get_db_connection(); cur = conn.cursor()
        for a in aligns:
            self._seq += 1
            scores = None if a is None else {"thesis_alignment": a,
                                             "momentum_quality": 0.2}
            cur.execute(
                "INSERT INTO run_events (run_id, seq, event_type, ts, payload) "
                "VALUES (?, ?, 'decision', ?, ?)",
                (run_id, self._seq, "2026-07-28T0%d:00:00Z" % (self._seq % 10),
                 json.dumps({"cycle": self._seq, "action": "hold",
                             "scores": scores})))
        conn.commit(); conn.close()

    def evaluate(self, run, has_position=True, trades=1):
        pos = {"quantity": 1 if has_position else 0, "entry_price": 476.0,
               "current_price": 475.0, "leverage": 1.0}
        pnl = {"total": -1.0, "realized": -0.45, "trades": trades,
               "mark_age_ok": True, "position": pos if has_position else None}
        with patch.object(run_engine, "compute_run_pnl", return_value=pnl):
            return run_engine._evaluate_stop(run)


class Streak(Base):
    def test_the_live_run_345_sequence(self):
        self.decisions([0.70, 0.35, 0.30, 0.30])
        self.assertEqual(run_engine._thesis_decay_streak(345), 3)

    def test_a_recovery_breaks_the_streak(self):
        """One good read means the desk still believes it — start over."""
        self.decisions([0.30, 0.30, 0.70, 0.30])
        self.assertEqual(run_engine._thesis_decay_streak(345), 1)

    def test_a_healthy_run_has_no_streak(self):
        self.decisions([0.70, 0.68, 0.72])
        self.assertEqual(run_engine._thesis_decay_streak(345), 0)

    def test_missing_scores_do_not_extend_or_reset(self):
        """A decision with no scores says nothing either way; it must not be
        counted as decay, and must not silently clear real decay."""
        self.decisions([0.30, 0.30, None])
        self.assertEqual(run_engine._thesis_decay_streak(345), 0)

    def test_unreadable_journal_is_quiet(self):
        with patch.object(run_engine, "get_db_connection",
                          side_effect=RuntimeError("db")):
            self.assertEqual(run_engine._thesis_decay_streak(345), 0)


class Rail(Base):
    def test_a_holding_run_is_retired_on_decay(self):
        """The gap this closes — both other rails require a FLAT run."""
        self.decisions([0.70, 0.35, 0.30, 0.30])
        self.assertEqual(self.evaluate(_run()), "thesis_decayed")

    def test_a_believed_thesis_is_left_alone(self):
        self.decisions([0.70, 0.68, 0.72])
        self.assertIsNone(self.evaluate(_run()))

    def test_two_bad_cycles_are_not_enough(self):
        """One weak read is a wobble; the rail waits for a pattern."""
        self.decisions([0.70, 0.30, 0.30])
        self.assertIsNone(self.evaluate(_run()))

    def test_it_applies_to_a_flat_run_too(self):
        self.decisions([0.30, 0.30, 0.30])
        self.assertEqual(self.evaluate(_run(), has_position=False, trades=0),
                         "thesis_decayed")

    def test_floor_zero_disables_it(self):
        self.decisions([0.30, 0.30, 0.30])
        with patch.dict(os.environ, {"RUN_THESIS_DECAY_FLOOR": "0"}):
            self.assertIsNone(self.evaluate(_run()))

    def test_bad_env_falls_back_to_defaults(self):
        with patch.dict(os.environ, {"RUN_THESIS_DECAY_FLOOR": "high",
                                     "RUN_THESIS_DECAY_STRIKES": "many"}):
            self.assertAlmostEqual(run_engine._thesis_decay_floor(), 0.35)
            self.assertEqual(run_engine._thesis_decay_strikes(), 3)

    def test_strikes_never_below_two(self):
        with patch.dict(os.environ, {"RUN_THESIS_DECAY_STRIKES": "1"}):
            self.assertGreaterEqual(run_engine._thesis_decay_strikes(), 2)

    def test_reason_is_classified_for_immediate_replacement(self):
        """An unclassified stop reason strands the fleet slot."""
        self.assertIn("thesis_decayed", fleet_planner.REPLACE_IMMEDIATE)


if __name__ == "__main__":
    unittest.main()


class NoRunId(Base):
    """The safety-rail suites call _evaluate_stop with a bare
    {"stop_conditions_json": ...} and no id. A rail that needs the journal
    must degrade to silence there, not raise through the caller's
    fail-closed handler and pause the run."""

    def test_a_run_dict_without_an_id_is_not_evaluated(self):
        self.decisions([0.30, 0.30, 0.30])
        self.assertIsNone(self.evaluate({"stop_conditions_json": "{}"}))

    def test_no_journal_read_is_attempted_without_an_id(self):
        """Reading the journal for run None is a pointless query on every
        cycle of every safety-rail path; the guard must short-circuit."""
        with patch.object(run_engine, "_thesis_decay_streak") as streak:
            self.assertIsNone(self.evaluate({"stop_conditions_json": "{}"}))
        streak.assert_not_called()
