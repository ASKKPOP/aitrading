"""A durably-blocked replacement candidate goes on symbol cooldown.

When the builder rejects a candidate because an open position exists for
the symbol outside any run, the replacement loop used to re-pick the same
name every tick forever (fleet 23 sat at 6/10 retrying SOLUSDT for an
hour, 2026-07-31). The blocked symbol now gets a fleet_symbol_cooldowns
row so the next pass surfaces other names.
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

import database
import fleet_supervisor


class BlockedCandidateCooldown(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()

    def tearDown(self):
        self.tmp.cleanup()

    def _rows(self):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT agent_id, market, symbol, until_ts, "
                        "source_run_id FROM fleet_symbol_cooldowns")
            return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

    def test_inserts_runless_cooldown(self):
        fleet_supervisor._cooldown_blocked_symbol(6, "crypto", "SOLUSDT")
        rows = self._rows()
        assert len(rows) == 1
        r = rows[0]
        assert (r["agent_id"], r["market"], r["symbol"]) == (6, "crypto", "SOLUSDT")
        assert r["source_run_id"] is None
        assert r["until_ts"] > fleet_supervisor._now_iso()

    def test_no_duplicate_while_active(self):
        fleet_supervisor._cooldown_blocked_symbol(6, "crypto", "SOLUSDT")
        fleet_supervisor._cooldown_blocked_symbol(6, "crypto", "SOLUSDT")
        assert len(self._rows()) == 1


if __name__ == "__main__":
    unittest.main()
