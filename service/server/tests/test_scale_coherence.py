"""Scale coherence (owner "do", 2026-08-13, from the two-subagent pass):

1. The house loss floor becomes budget-proportional — $0.99 was 0.6% of a
   seed-1000 slot; on a $1,580 slot it is fee noise, and desks spent
   2026-08-13 closing fee-scale "wounds" (SLV −2.51 called "past the
   floor") while their authored 3–5% stops never acted.
2. First-admission probation sizing — QNT/CBRS/SPCX were admitted with
   zero record at extreme size and produced the day's largest us-stock
   losses; a symbol the agent never completed a run on trades its first
   run at PROBATION_SIZE_FRAC of max_bet.
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
import run_engine


class LossFloorScalingTests(unittest.TestCase):
    def test_no_budget_keeps_the_plain_dollar_floor(self):
        self.assertAlmostEqual(run_engine._loss_floor_usd(None), 0.99)
        self.assertAlmostEqual(run_engine._loss_floor_usd({}), 0.99)

    def test_budget_scales_the_floor(self):
        # Fleet 32's real slot: $1,579.72 → 0.6% = $9.48, not $0.99.
        floor = run_engine._loss_floor_usd({"run_budget_usd": 1579.72})
        self.assertAlmostEqual(floor, 9.478, places=2)

    def test_small_budget_never_drops_below_the_owner_dollar_floor(self):
        self.assertAlmostEqual(
            run_engine._loss_floor_usd({"run_budget_usd": 50.0}), 0.99)

    def test_frac_env_kill_switch(self):
        with patch.dict(os.environ, {"RUN_LOSS_FLOOR_FRAC": "0"}):
            self.assertAlmostEqual(
                run_engine._loss_floor_usd({"run_budget_usd": 1579.72}), 0.99)

    def test_slv_class_loss_is_no_longer_past_a_scaled_floor(self):
        # SLV run 1100 (budget $399.9): cumulative −2.51 was reported "past
        # the −0.99 floor" and fully closed at the day's low. At 0.6% of
        # budget the floor is $2.40 — −2.51 is still past it (real), but
        # a −1.50 tick is NOT, where the flat floor would have flagged it.
        run = {"id": 1, "symbol": "SLV", "market": "us-stock",
               "run_budget_usd": 399.9}
        with patch.object(run_engine, "_typical_daily_move_pct",
                          return_value=1.5):
            line_tick = run_engine._loss_verdict_line(
                run, {"total": -1.50, "position": {}})
            line_wound = run_engine._loss_verdict_line(
                run, {"total": -2.51, "position": {}})
        self.assertEqual(line_tick, "",
                         "a sub-floor tick must not be called a wound")
        self.assertIn("House floor", line_wound)
        self.assertIn("$-2.40", line_wound)


class ProbationSizingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO agents (name, cash) VALUES ('p', 100000)")
        self.agent_id = cur.lastrowid
        conn.commit()
        conn.close()

    def tearDown(self):
        self.tmp.cleanup()

    def _stopped_run(self, symbol):
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO trading_runs (agent_id, symbol, market, market_type,"
            " status, config_snapshot_json, start_condition_json,"
            " stop_conditions_json, created_at) VALUES "
            "(?,?,?,'spot','stopped','{}','{}','{}','2026-08-01T00:00:00Z')",
            (self.agent_id, symbol, "us-stock"))
        conn.commit()
        conn.close()

    def test_zero_record_symbol_gets_probation(self):
        self.assertAlmostEqual(
            fp._probation_size_frac(self.agent_id, "QNT"), 0.33)

    def test_any_completed_run_lifts_probation(self):
        self._stopped_run("QNT")
        self.assertAlmostEqual(
            fp._probation_size_frac(self.agent_id, "QNT"), 1.0)

    def test_no_identity_means_full_size(self):
        self.assertAlmostEqual(fp._probation_size_frac(None, "QNT"), 1.0)

    def test_env_kill_switch(self):
        with patch.dict(os.environ, {"PROBATION_SIZE_FRAC": "1"}):
            self.assertAlmostEqual(
                fp._probation_size_frac(self.agent_id, "QNT"), 1.0)

    def test_compose_actually_APPLIES_probation(self):
        # Wiring: patch the frac to a sentinel and confirm max_bet halves
        # (and the stop scales to the probation bet, not the full one).
        thesis = {"symbol": "QNT", "market": "crypto", "direction": "long",
                  "confidence": 0.7, "expected_move_pct": 2.0,
                  "horizon_hours": 24}
        base = fp.compose_run_settings(
            thesis, 1000.0, {"risk_appetite": "balanced", "lang": "en"})
        with patch.object(fp, "_probation_size_frac", return_value=0.5) as spy:
            probed = fp.compose_run_settings(
                thesis, 1000.0, {"risk_appetite": "balanced", "lang": "en",
                                 "agent_id": self.agent_id})
        self.assertAlmostEqual(probed["max_bet_usd"],
                               round(base["max_bet_usd"] * 0.5, 2))
        self.assertLess(probed["stop_conditions"]["max_loss_usd"],
                        base["stop_conditions"]["max_loss_usd"])
        self.assertEqual(spy.call_args[0][0], self.agent_id)


if __name__ == "__main__":
    unittest.main()
