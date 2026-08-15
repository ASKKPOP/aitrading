"""Plan 24 fix 1 — the contradiction rule: a held position may not silently
ignore the desk's own reading.

Live 2026-08-12, run 1086: short ZEC while the desk's own report read
"technical 'buy', news 10 bullish vs 1 bearish" for three straight cycles,
holding silently to −$5.55. Three layers, each tested here:
counter (run_feedback.note_contradiction), prompt line
(run_engine._contradiction_line + wiring), and the streak-3 backstop rail
inside run_cycle that forces a half reduce on a silent hold.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
import run_engine
import run_feedback as rf
from routes import create_app


class NoteContradictionTests(unittest.TestCase):
    def test_full_opposing_reading_increments(self):
        state: dict = {}
        # short book, tech buy + news bullish ⇒ contradiction (the ZEC shape)
        self.assertEqual(rf.note_contradiction(state, -1.0, "buy", 10, 1), 1)
        self.assertEqual(rf.note_contradiction(state, -1.0, "buy", 10, 1), 2)
        self.assertEqual(rf.note_contradiction(state, -1.0, "buy", 10, 1), 3)

    def test_aligned_reading_resets(self):
        state = {"contradiction_streak": 2}
        self.assertEqual(rf.note_contradiction(state, -1.0, "sell", 1, 9), 0)

    def test_mixed_reading_resets(self):
        # tech and news disagree with each other ⇒ no verdict against the book
        state = {"contradiction_streak": 2}
        self.assertEqual(rf.note_contradiction(state, -1.0, "buy", 1, 9), 0)

    def test_partial_reading_leaves_streak_untouched(self):
        state = {"contradiction_streak": 2}
        self.assertEqual(rf.note_contradiction(state, -1.0, "hold", 10, 1), 2)
        self.assertEqual(rf.note_contradiction(state, -1.0, "buy", None, None), 2)

    def test_flat_resets(self):
        state = {"contradiction_streak": 2}
        self.assertEqual(rf.note_contradiction(state, 0.0, "buy", 10, 1), 0)

    def test_long_book_contradicted_by_bearish_reading(self):
        state: dict = {}
        self.assertEqual(rf.note_contradiction(state, 1.0, "sell", 1, 9), 1)


class ContradictionLineTests(unittest.TestCase):
    def _run_dict(self, streak):
        return {"adapt_state_json": json.dumps(
            {"contradiction_streak": streak})}

    def test_silent_below_one(self):
        self.assertEqual(run_engine._contradiction_line(self._run_dict(0), -1.0), "")

    def test_flat_is_silent_even_with_streak(self):
        self.assertEqual(run_engine._contradiction_line(self._run_dict(3), 0.0), "")

    def test_streak_one_informs(self):
        line = run_engine._contradiction_line(self._run_dict(1), -1.0)
        self.assertIn("OPPOSED this short for 1", line)
        self.assertNotIn("silent hold", line)

    def test_streak_two_mandates(self):
        line = run_engine._contradiction_line(self._run_dict(2), 1.0)
        self.assertIn("OPPOSED this long for 2", line)
        self.assertIn("silent hold is not an available action", line)


class RailIntegrationTests(unittest.TestCase):
    """The streak-3 backstop actually reduces inside run_cycle."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        os.environ["AUTO_TRADING_ENABLED"] = "true"
        os.environ["RUN_CONF_PERCENTILE"] = "false"
        self.probe = patch("routes_runs._probe_price", return_value=100.0)
        self.probe.start()
        self.client = TestClient(create_app())
        resp = self.client.post(
            "/api/claw/agents/selfRegister",
            json={"name": "contra-agent", "password": "pw123",
                  "initial_balance": 100000.0})
        assert resp.status_code == 200, resp.text
        self.token = resp.json()["token"]
        self.agent_id = resp.json()["agent_id"]

    def tearDown(self):
        self.probe.stop()
        for key in ("AUTO_TRADING_ENABLED", "RUN_CONF_PERCENTILE"):
            os.environ.pop(key, None)
        self.tmp.cleanup()

    def _h(self):
        return {"Authorization": f"Bearer {self.token}"}

    def _run(self) -> int:
        run_id = self.client.post(
            "/api/runs", json={"symbol": "BTC", "market": "crypto",
                               "max_bet_usd": 500.0, "feedback": True},
            headers=self._h()).json()["id"]
        assert self.client.post(f"/api/runs/{run_id}/start",
                                headers=self._h()).status_code == 200
        return run_id

    def _seed_position_and_streak(self, run_id, streak):
        state = dict(rf._DEFAULT_STATE)
        state["contradiction_streak"] = streak
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            database.begin_write_transaction(cur)
            cur.execute(
                "INSERT INTO positions (agent_id, symbol, market, side, "
                "quantity, entry_price, current_price, opened_at, run_id, "
                "price_updated_at, leverage) VALUES (?, 'BTC', 'crypto', "
                "'long', 5.0, 100.0, 100.0, ?, ?, ?, 1.0)",
                (self.agent_id, rf._now_iso(), run_id, rf._now_iso()))
            cur.execute("SELECT config_snapshot_json FROM trading_runs "
                        "WHERE id = ?", (run_id,))
            cfg = json.loads(cur.fetchone()["config_snapshot_json"] or "{}")
            cfg["feedback"] = True
            cur.execute(
                "UPDATE trading_runs SET adapt_state_json = ?, "
                "config_snapshot_json = ? WHERE id = ?",
                (json.dumps(state), json.dumps(cfg), run_id))
            conn.commit()
        finally:
            conn.close()

    def _events(self, run_id, kind):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT payload FROM run_events WHERE run_id = ? "
                        "AND event_type = ?", (run_id, kind))
            return [json.loads(r["payload"]) for r in cur.fetchall()]
        finally:
            conn.close()

    def _hold_analysis(self):
        return {"symbol": "BTC", "market": "crypto",
                "analysts": {},
                "decision": {"action": "hold", "confidence": 0.5,
                             "entry": 100.0, "report": "silent hold"}}

    def test_streak_three_silent_hold_forces_half_reduce(self):
        run_id = self._run()
        self._seed_position_and_streak(run_id, 3)
        with patch("analysis_agents.run_analysis",
                   return_value=self._hold_analysis()):
            run_engine.run_cycle(run_id)
        reduces = self._events(run_id, "contradiction_reduce")
        self.assertEqual(len(reduces), 1, "rail must fire at streak 3")
        self.assertEqual(reduces[0]["side"], "sell")
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT SUM(quantity) q FROM positions WHERE run_id = ?",
                        (run_id,))
            remaining = float(cur.fetchone()["q"] or 0)
            cur.execute("SELECT adapt_state_json FROM trading_runs WHERE id = ?",
                        (run_id,))
            state = json.loads(cur.fetchone()["adapt_state_json"] or "{}")
        finally:
            conn.close()
        self.assertAlmostEqual(remaining, 2.5, places=6,
                               msg="half the position must be shed")
        self.assertEqual(int(state.get("contradiction_streak") or 0), 0,
                         "streak resets after the rail acts")

    def test_streak_two_does_not_fire(self):
        run_id = self._run()
        self._seed_position_and_streak(run_id, 2)
        with patch("analysis_agents.run_analysis",
                   return_value=self._hold_analysis()):
            run_engine.run_cycle(run_id)
        self.assertEqual(self._events(run_id, "contradiction_reduce"), [])

    def test_full_path_reading_advances_the_streak(self):
        """Wiring: a contradicting full-route reading actually increments the
        persisted streak (the ZEC shape — long book, bearish reading here)."""
        run_id = self._run()
        self._seed_position_and_streak(run_id, 0)
        analysis = {
            "symbol": "BTC", "market": "crypto",
            "analysts": {
                "technical": {"brief": "t", "data": {"signal": "sell",
                                                     "current_price": 100.0}},
                "news": {"brief": "n", "data": {"sentiment_breakdown": {
                    "bearish": 9, "bullish": 1}}},
            },
            "decision": {"action": "hold", "confidence": 0.5,
                         "entry": 100.0, "report": "r"},
        }
        with patch("analysis_agents.run_analysis", return_value=analysis):
            run_engine.run_cycle(run_id)
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT adapt_state_json FROM trading_runs WHERE id = ?",
                        (run_id,))
            state = json.loads(cur.fetchone()["adapt_state_json"] or "{}")
        finally:
            conn.close()
        self.assertEqual(int(state.get("contradiction_streak") or 0), 1)

    def test_prompt_line_is_wired_into_position_state(self):
        """The line must actually reach the desk (brief-line wiring lesson:
        an unwired helper passes every rendering test)."""
        run_id = self._run()
        self._seed_position_and_streak(run_id, 2)
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM trading_runs WHERE id = ?", (run_id,))
            run = dict(cur.fetchone())
        finally:
            conn.close()
        line = run_engine._contradiction_line(run, 5.0)
        self.assertIn("OPPOSED", line)
        import inspect
        self.assertIn("_contradiction_line(run, pos_qty)",
                      inspect.getsource(run_engine._compose_position_state),
                      "line must be in the composed brief (both prompt paths "
                      "route through it — pinned by BriefJournalTests)")


if __name__ == "__main__":
    unittest.main()
