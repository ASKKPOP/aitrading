"""An agent's profit is measured against what IT started with.

Before `agents.starting_capital` existed, every profit figure was measured
against a module-level 100,000. An agent seeded with anything else reported a
collapse it never took — 1,000 read as -99%, on zero trades. These tests pin
the seed to the agent and fail on the old hardcoded behaviour.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
from routes import create_app
from routes_shared import DEFAULT_AGENT_SEED_CAPITAL
from routes_trading import profit_percent_for_display, starting_capital_of


class StartingCapitalUnitTests(unittest.TestCase):
    def test_percent_uses_the_agents_own_seed(self) -> None:
        # Flat on a 1,000 seed is 0%, not -99%.
        self.assertEqual(profit_percent_for_display(0.0, 0.0, 1000.0), 0.0)
        # +100 on 1,000 is +10%, not +0.1%.
        self.assertAlmostEqual(
            profit_percent_for_display(100.0, 0.0, 1000.0), 10.0, places=6)

    def test_percent_default_is_the_house_seed(self) -> None:
        self.assertAlmostEqual(
            profit_percent_for_display(DEFAULT_AGENT_SEED_CAPITAL * 0.1, 0.0),
            10.0, places=6)

    def test_deposits_extend_the_base(self) -> None:
        # base = seed + deposited = 1,000 + 1,000
        self.assertAlmostEqual(
            profit_percent_for_display(200.0, 1000.0, 1000.0), 10.0, places=6)

    def test_starting_capital_of_falls_back_when_absent_or_null(self) -> None:
        self.assertEqual(starting_capital_of({'starting_capital': 250.0}), 250.0)
        # A row from before the migration carries NULL — the fallback is the
        # house seed, which is in fact what those rows were started with.
        self.assertEqual(starting_capital_of({'starting_capital': None}),
                         DEFAULT_AGENT_SEED_CAPITAL)
        self.assertEqual(starting_capital_of({}), DEFAULT_AGENT_SEED_CAPITAL)


class StartingCapitalEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _register(self, name: str, balance: float) -> int:
        resp = self.client.post(
            "/api/claw/agents/selfRegister",
            json={"name": name, "password": "pw123", "initial_balance": balance},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        return resp.json()["agent_id"]

    def test_small_seed_agent_is_not_reported_as_a_99_percent_loss(self) -> None:
        agent_id = self._register("seed-1k", 1000.0)
        body = self.client.get(f"/api/agents/{agent_id}/profile").json()
        self.assertEqual(body["cash"], 1000.0)
        # The whole point: flat, untraded, on its own seed.
        self.assertEqual(body["profit_pct"], 0.0)

    def test_default_seed_agent_still_reads_flat(self) -> None:
        agent_id = self._register("seed-default", DEFAULT_AGENT_SEED_CAPITAL)
        body = self.client.get(f"/api/agents/{agent_id}/profile").json()
        self.assertEqual(body["profit_pct"], 0.0)

    def test_seed_is_persisted_from_the_registered_balance(self) -> None:
        agent_id = self._register("seed-persist", 2500.0)
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT starting_capital FROM agents WHERE id = ?", (agent_id,))
            self.assertEqual(float(cur.fetchone()["starting_capital"]), 2500.0)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
