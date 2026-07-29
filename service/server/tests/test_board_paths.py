"""Every board path applies the same rankable rule (2026-07-28).

I filtered the materialized snapshot and called it done. Prod still served
`assistant-verify-e2e` and `boardcheck` on the front page, because THREE
separate code paths rank agents and I had fixed one:

  1. leaderboard_snapshot._compute_agent_rows   — the materialized table
  2. /api/profit/history live fallback          — runs when the snapshot is
                                                  empty or the page is past
                                                  its top_n
  3. /api/leaderboard/position-pnl              — iterated every agent, no
                                                  filter at all

The rule is a TRACK RECORD and nothing else. Requiring an owner as well was
my first attempt and it was wrong: routes_agent.py registers third-party
agents with no user_id, and an agent-native platform cannot hide every
external agent from its own leaderboard.

The snapshot-only tests passed the whole time. They were testing a function,
not the endpoint a browser actually hits.

These tests go through the HTTP API so a fourth path cannot be added quietly,
and they assert the *population*, not the plumbing.
"""
from __future__ import annotations

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

TS = "2026-07-28T00:00:00Z"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "t.db")
        database.init_database()
        self.client = TestClient(create_app())
        self._seed()

    def tearDown(self):
        self.tmp.cleanup()

    def _agent(self, name, user_id, cash=100_000.0, trades=0):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("INSERT INTO agents (name, user_id, cash, deposited) "
                        "VALUES (?, ?, ?, 0)", (name, user_id, cash))
            aid = cur.lastrowid
            for i in range(trades):
                cur.execute(
                    "INSERT INTO signals (signal_id, agent_id, message_type, "
                    "market, symbol, timestamp, created_at) VALUES "
                    "(?, ?, 'operation', 'crypto', 'BTCUSDT', 0, ?)",
                    (aid * 1000 + i, aid, TS))
            conn.commit()
        finally:
            conn.close()
        return aid

    def _seed(self):
        """Prod's actual population on 2026-07-28."""
        for name in ("guide-deploy-check", "cfgprobe-9257",
                     "gate-verify-1784328779", "assistant-verify-e2e",
                     "intruder-verify-e2e", "fleet-deploy-check",
                     "stranger-v", "bostonbc"):
            self._agent(name, None, cash=1000.0)
        # pnl-deploy-check had TWO trades on prod. An unowned agent that has
        # traded is the case where trade_count > 0 stops masking a missing
        # owner check — seed it faithfully or the owner filter is untested.
        self._agent("pnl-deploy-check", None, cash=999.89, trades=2)
        self._agent("yoojinbe", 4)
        self._agent("junekimsop", 7)
        self._agent("boardcheck", 6)
        self._agent("fleet-canary", 5, cash=50_000.0)
        self._agent("scope-verify", 5)
        self._agent("info", 5, cash=96_436.7, trades=155)

    def _names(self, payload, key):
        return {r.get("name") for r in (payload.get(key) or [])}


class ProfitHistory(Base):
    """The endpoint LeaderboardPage actually renders cards from."""

    def test_only_agents_with_a_track_record_are_returned(self):
        r = self.client.get("/api/profit/history?limit=50&offset=0&days=30")
        self.assertEqual(r.status_code, 200, r.text)
        # pnl-deploy-check has 2 real trades, so a track-record rule keeps it.
        # Removing it is data cleanup, not a filter.
        self.assertEqual(self._names(r.json(), "top_agents"),
                         {"info", "pnl-deploy-check"})

    def test_the_named_prod_offenders_are_gone(self):
        r = self.client.get("/api/profit/history?limit=50&offset=0&days=30")
        names = self._names(r.json(), "top_agents")
        for bad in ("assistant-verify-e2e", "boardcheck", "guide-deploy-check",
                    "cfgprobe-9257", "fleet-canary"):
            self.assertNotIn(bad, names, bad)

    def test_total_counts_the_same_population_it_lists(self):
        """A total of 15 against one listed row makes the client page into
        rows that do not exist — and is what made the live fallback fire."""
        body = self.client.get(
            "/api/profit/history?limit=50&offset=0&days=30").json()
        self.assertEqual(body.get("total"), 2)


class PositionPnl(Base):
    """This one had no filter whatsoever."""

    def test_only_rankable_agents_are_returned(self):
        r = self.client.get("/api/leaderboard/position-pnl")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self._names(r.json(), "top_agents"),
                         {"info", "pnl-deploy-check"})


class EveryPathAgrees(Base):
    """The property that actually matters: no path disagrees with another."""

    def test_all_board_endpoints_return_the_same_population(self):
        a = self._names(self.client.get(
            "/api/profit/history?limit=50&offset=0&days=30").json(), "top_agents")
        b = self._names(self.client.get(
            "/api/leaderboard/position-pnl").json(), "top_agents")
        import leaderboard_snapshot as lb
        c = {r["name"] for r in lb._compute_agent_rows()}
        self.assertEqual(a, b, "profit/history vs position-pnl disagree")
        self.assertEqual(a, c, "endpoint vs materialized snapshot disagree")

    def test_an_unowned_third_party_agent_that_trades_is_ranked(self):
        """The platform is agent-native: an external agent registers with no
        user_id. Excluding it would hide the population the board exists for."""
        self._agent("third-party-bot", None, trades=4)
        names = self._names(self.client.get(
            "/api/profit/history?limit=50&offset=0&days=30").json(), "top_agents")
        self.assertIn("third-party-bot", names)

    def test_a_newly_qualifying_member_appears_everywhere_at_once(self):
        self._agent("newly-active", 9, trades=1)
        a = self._names(self.client.get(
            "/api/profit/history?limit=50&offset=0&days=30").json(), "top_agents")
        b = self._names(self.client.get(
            "/api/leaderboard/position-pnl").json(), "top_agents")
        self.assertIn("newly-active", a)
        self.assertIn("newly-active", b)


if __name__ == "__main__":
    unittest.main()
