"""profit-history recording — agent_leaderboard_exclusions table (fix for
'no such table' failing every recording tick)."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
from tasks import _record_profit_history_once


class ProfitHistoryExclusionsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _add_agent(self, name: str) -> int:
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO agents (name, token, cash) VALUES (?, ?, 100000)", (name, f"claw_{name}"))
        agent_id = cur.lastrowid
        conn.commit()
        conn.close()
        return agent_id

    def test_recording_inserts_snapshot_per_agent(self) -> None:
        self._add_agent("a1")
        self._add_agent("a2")
        self.assertEqual(_record_profit_history_once(), 2)
        conn = database.get_db_connection()
        count = conn.cursor().execute("SELECT COUNT(*) AS c FROM profit_history").fetchone()["c"]
        conn.close()
        self.assertEqual(count, 2)

    def test_active_exclusion_skips_agent(self) -> None:
        kept = self._add_agent("kept")
        excluded = self._add_agent("excluded")
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO agent_leaderboard_exclusions (agent_id, reason, active) VALUES (?, 'test', 1)",
            (excluded,),
        )
        conn.commit()
        conn.close()

        self.assertEqual(_record_profit_history_once(), 1)
        conn = database.get_db_connection()
        rows = conn.cursor().execute("SELECT agent_id FROM profit_history").fetchall()
        conn.close()
        self.assertEqual([r["agent_id"] for r in rows], [kept])

    def test_inactive_exclusion_does_not_skip(self) -> None:
        agent = self._add_agent("back-in")
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO agent_leaderboard_exclusions (agent_id, active) VALUES (?, 0)",
            (agent,),
        )
        conn.commit()
        conn.close()
        self.assertEqual(_record_profit_history_once(), 1)


if __name__ == "__main__":
    unittest.main()
