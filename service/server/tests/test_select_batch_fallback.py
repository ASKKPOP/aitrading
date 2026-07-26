"""An EMPTY research batch must not blank the trading universe (2026-07-26:
batch research:495847 refreshed with zero theses and every fleet replacement
went no_candidates while the previous batch's theses were still live).
select_targets now picks the newest batch that actually HAS selectable,
non-expired theses."""

from __future__ import annotations

import sys
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
import symbol_research as sr

from test_fleet_planner import FleetTestBase, _seed_batch


class EmptyBatchFallbackTests(FleetTestBase):
    def test_empty_newer_batch_falls_back_to_live_theses(self):
        _seed_batch()                       # batch with AAA..FFF theses
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT batch_id FROM research_batches "
                    "ORDER BY batch_id DESC LIMIT 1")
        good = cur.fetchone()["batch_id"]
        # a NEWER batch that produced nothing (LLM/feed failure)
        cur.execute("INSERT INTO research_batches (batch_id, created_at) "
                    "VALUES (?, ?)", (good + ":zzz-empty",
                                      "2026-01-01T01:00:00Z"))
        conn.commit()

        picks = sr.select_targets(cur, self.agent_id, 3)
        conn.close()
        self.assertTrue(picks, "empty newest batch blanked the universe")
        self.assertTrue(all(p["batch_id"] == good for p in picks))
