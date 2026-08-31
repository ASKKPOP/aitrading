"""OWNER 2026-08-31: (1) the TRADING count a user chooses is pinned — no
machine path may change it; (2) the suggested fleet budget is the user's FULL
money (realized equity), fresh on every read."""
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
import fleet_planner
from routes_fleets import _default_budget


class UserCountPinTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO users (email, password_hash) VALUES ('u@x.com','x')")
        self.user_id = cur.lastrowid
        cur.execute(
            "INSERT INTO agents (name, user_id, cash, starting_capital) "
            "VALUES ('pin-agent', ?, 10000, 10000)", (self.user_id,))
        self.agent_id = cur.lastrowid
        conn.commit()

    def tearDown(self):
        self.tmp.cleanup()

    def _cap(self, fleet_id: int):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT user_size_cap FROM fleets WHERE id = ?", (fleet_id,))
            return cur.fetchone()["user_size_cap"]
        finally:
            conn.close()

    def _create(self, n: int) -> int:
        with patch("entitlements.limits_for_agent",
                   return_value=("professional", {"max_fleet_size": 25})):
            return fleet_planner.create_fleet(self.agent_id, n, 5000.0)

    def test_creation_pins_the_chosen_count(self):
        fleet_id = self._create(7)
        self.assertEqual(self._cap(fleet_id), 7)

    def test_migration_backfills_unpinned_fleets(self):
        fleet_id = self._create(5)
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE fleets SET user_size_cap = NULL WHERE id = ?", (fleet_id,))
        conn.commit()
        database.init_database()  # migrations are idempotent; backfill re-pins
        self.assertEqual(self._cap(fleet_id), 5)


class DefaultBudgetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO agents (name, cash, starting_capital) "
            "VALUES ('budget-agent', 4000, 10000)")
        self.agent_id = cur.lastrowid
        conn.commit()

    def tearDown(self):
        self.tmp.cleanup()

    def _agent(self):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM agents WHERE id = ?", (self.agent_id,))
            return dict(cur.fetchone())
        finally:
            conn.close()

    def test_suggestion_is_full_realized_equity_not_half_cash(self):
        # seed 10,000 + realized −500 = 9,500 — NOT cash*0.5 (2,000)
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO trading_runs (agent_id, symbol, realized_pnl_usd, "
            "created_at) VALUES (?, 'BTC', -500, '2026-08-01T00:00:00Z')",
            (self.agent_id,))
        conn.commit()
        self.assertEqual(_default_budget(self._agent()), 9500.0)

    def test_suggestion_updates_as_realized_moves(self):
        # "everyday update by user full money": the read is always current
        self.assertEqual(_default_budget(self._agent()), 10000.0)
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO trading_runs (agent_id, symbol, realized_pnl_usd, "
            "created_at) VALUES (?, 'ETH', 250, '2026-08-02T00:00:00Z')",
            (self.agent_id,))
        conn.commit()
        self.assertEqual(_default_budget(self._agent()), 10250.0)

    def test_no_seed_falls_back_to_cash(self):
        agent = self._agent()
        agent["starting_capital"] = None
        self.assertEqual(_default_budget(agent), 4000.0)


if __name__ == "__main__":
    unittest.main()
