"""Research supply scales to fleet demand (live 2026-08-12, fleet 31).

A 25-slot us-stock fleet sat against a fixed survivor cap of 8: the batch
carried four us-stock theses, three already running, so the fleet crawled
2→3→4 while 21 slots waited on a pool that could never feed them.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database  # noqa: E402
import symbol_research as sr  # noqa: E402


class SupplyScalesToDemandTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "t.db")
        database.init_database()
        for key in list(os.environ):
            if key.startswith("FLEET_RESEARCH_SURVIVORS_"):
                os.environ.pop(key)

    def tearDown(self):
        self.tmp.cleanup()

    def _fleet(self, n_runs, scope_json, status="active"):
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO fleets (agent_id, status, n_runs, total_budget_usd,"
            " risk_appetite, market_scope_json, created_at) VALUES"
            " (6, ?, ?, 10000.0, 'balanced', ?, '2026-08-12T00:00:00Z')",
            (status, n_runs, scope_json))
        conn.commit()
        conn.close()

    def test_defaults_stand_with_no_fleets(self):
        self.assertEqual(sr._survivors_per_market(),
                         sr._SURVIVOR_DEFAULTS)

    def test_scoped_fleet_raises_its_market_only(self):
        self._fleet(25, '["us-stock"]')
        out = sr._survivors_per_market()
        # 25 slots + default-8 exclusion headroom = 33
        self.assertEqual(out["us-stock"], 33)
        self.assertEqual(out["crypto"], sr._SURVIVOR_DEFAULTS["crypto"])

    def test_unscoped_fleet_counts_toward_every_market(self):
        self._fleet(10, None)
        out = sr._survivors_per_market()
        self.assertEqual(out["crypto"], 18)
        self.assertEqual(out["us-stock"], 18)
        self.assertEqual(out["forex"], 14)

    def test_hard_cap_bounds_the_raise(self):
        self._fleet(200, '["us-stock"]')
        self.assertEqual(sr._survivors_per_market()["us-stock"],
                         sr._SURVIVOR_HARD_CAP)

    def test_terminal_fleets_do_not_count(self):
        self._fleet(25, '["us-stock"]', status="stopped")
        self.assertEqual(sr._survivors_per_market()["us-stock"],
                         sr._SURVIVOR_DEFAULTS["us-stock"])

    def test_env_override_still_wins_outright(self):
        self._fleet(25, '["us-stock"]')
        os.environ["FLEET_RESEARCH_SURVIVORS_US_STOCK"] = "5"
        try:
            self.assertEqual(sr._survivors_per_market()["us-stock"], 5)
        finally:
            os.environ.pop("FLEET_RESEARCH_SURVIVORS_US_STOCK")


if __name__ == "__main__":
    unittest.main()
