"""Drawdown-triggered thesis review (Henry 2026-07-21).

An open position bleeding UNREALIZED drawdown must get its LLM
what-went-wrong review without waiting for a closed trade: the review now
also fires when drawdown ≥ review_drawdown_frac × max_loss_usd, under the
same daily cap and 6h interval as the close-triggered path.
"""
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import database
import run_feedback as rf


class DrawdownReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO users (email, password_hash, created_at) "
                    "VALUES ('dd@x.com', 'x', '2026-01-01T00:00:00Z')")
        user_id = cur.lastrowid
        cur.execute(
            "INSERT INTO agents (name, token_hash, cash, user_id, created_at) "
            "VALUES ('dd-agent', 'th', 100000, ?, '2026-01-01T00:00:00Z')",
            (user_id,))
        self.agent_id = cur.lastrowid
        conn.commit()
        conn.close()
        self.plan = patch("entitlements.plan_code_for_user",
                          return_value="professional")
        self.plan.start()

    def tearDown(self):
        self.plan.stop()
        self.tmp.cleanup()

    def _fixture(self, max_loss=100.0):
        state = rf.load_state({"adapt_state_json": None})
        run = {"id": 1, "agent_id": self.agent_id, "status": "running",
               "stop_conditions_json": json.dumps({"max_loss_usd": max_loss})}
        cfg = {"thesis": {"direction": "short", "rationale": "seed"}}
        return state, run, cfg

    def test_drawdown_triggers_review_with_zero_closes(self):
        state, run, cfg = self._fixture(max_loss=100.0)
        pnl = {"total": -40.0, "unrealized": -40.0}  # 40 >= 0.35 * 100
        gen = MagicMock(return_value='{"thesis_status": "weakened", '
                                     '"rationale": "thesis off"}')
        res = rf.maybe_review_thesis(state, run, cfg, pnl, generate_text=gen)
        self.assertIsNotNone(res, "drawdown past the line must trigger review")
        self.assertEqual(res["status"], "weakened")
        self.assertEqual(state["size_mult"], 0.75,
                         "weakened verdict must tighten one rung")
        gen.assert_called_once()

    def test_below_threshold_no_review(self):
        state, run, cfg = self._fixture(max_loss=100.0)
        pnl = {"total": -20.0, "unrealized": -20.0}  # 20 < 35
        gen = MagicMock()
        self.assertIsNone(rf.maybe_review_thesis(state, run, cfg, pnl,
                                                 generate_text=gen))
        gen.assert_not_called()

    def test_no_max_loss_means_no_drawdown_trigger(self):
        state, run, cfg = self._fixture()
        run["stop_conditions_json"] = "{}"
        pnl = {"total": -500.0, "unrealized": -500.0}
        gen = MagicMock()
        self.assertIsNone(rf.maybe_review_thesis(state, run, cfg, pnl,
                                                 generate_text=gen))
        gen.assert_not_called()

    def test_interval_gate_bounds_drawdown_path(self):
        state, run, cfg = self._fixture(max_loss=100.0)
        state["last_thesis_review_at"] = rf._now_iso()  # just reviewed
        pnl = {"total": -90.0, "unrealized": -90.0}
        gen = MagicMock()
        self.assertIsNone(rf.maybe_review_thesis(state, run, cfg, pnl,
                                                 generate_text=gen))
        gen.assert_not_called()

    def test_invalidated_on_drawdown_retires(self):
        state, run, cfg = self._fixture(max_loss=100.0)
        pnl = {"total": -60.0, "unrealized": -60.0}
        gen = MagicMock(return_value='{"thesis_status": "invalidated", '
                                     '"rationale": "broken"}')
        res = rf.maybe_review_thesis(state, run, cfg, pnl, generate_text=gen)
        self.assertIsNotNone(res)
        self.assertTrue(res["retire"],
                        "invalidated at a loss must retire the run")


if __name__ == "__main__":
    unittest.main()
