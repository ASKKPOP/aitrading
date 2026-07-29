"""The public board shows members with a track record (2026-07-28).

Two defects, visible together on prod:

1. Fifteen agents were ranked publicly and fourteen had never traded —
   `guide-deploy-check`, `gate-verify-1784328779`, `intruder-verify-e2e`,
   `cfgprobe-9257`, `fleet-deploy-check`, `stranger-v`, `bostonbc`,
   `assistant-verify-e2e` and others left by deploy checks and e2e probes.

2. They showed catastrophic losses they never took. profit_percent is measured
   against a hardcoded INITIAL_CAPITAL of 100,000 and `agents` has NO
   starting-capital column, so an agent seeded with anything else reports a
   collapse on zero trades:

       cash  1,000 -> -99.00%      cash  5,000 -> -95.00%
       cash 50,000 -> -50.00%      cash    999 -> -99.00%

   This is not a test-data problem. Any real member funded with other than
   exactly 100,000 reads the same way.

Both are fixed by asking what a performance board is for: a TRACK RECORD.
`trade_count > 0` removes the phantom-loss class entirely, because an agent
with no trades has no performance to rank.

Requiring an OWNER as well was my first attempt and it was wrong.
routes_agent.py registers third-party agents with no user_id, so that rule
would have hidden every external agent — the population an agent-native
platform exists to showcase. Ownership is not a quality signal here.
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
import leaderboard_snapshot as lb


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "t.db")
        database.init_database()

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
                    "(?, ?, 'operation', 'crypto', 'BTCUSDT', 0, "
                    "'2026-07-28T00:00:00Z')",
                    (aid * 1000 + i, aid))
            conn.commit()
        finally:
            conn.close()
        return aid

    def names(self):
        return {r["name"] for r in lb._compute_agent_rows()}


class OwnershipIsNotTheSignal(Base):
    """The correction: an agent without a user_id is a third-party agent, not
    junk. routes_agent.py creates them that way on purpose."""

    def test_an_unowned_agent_that_trades_is_ranked(self):
        self._agent("third-party-bot", None, cash=1000.0, trades=3)
        self.assertIn("third-party-bot", self.names())

    def test_an_unowned_agent_that_never_traded_is_not(self):
        """Excluded for the absence of a record, not the absence of an owner."""
        self._agent("guide-deploy-check", None, cash=1000.0)
        self.assertNotIn("guide-deploy-check", self.names())

    def test_an_owned_agent_with_trades_is_included(self):
        self._agent("real-member", 1, trades=2)
        self.assertIn("real-member", self.names())


class NoTrackRecordNoRanking(Base):

    def test_an_owned_agent_that_never_traded_is_excluded(self):
        self._agent("newcomer", 2, trades=0)
        self.assertNotIn("newcomer", self.names())

    def test_one_trade_is_enough(self):
        self._agent("has-a-record", 3, trades=1)
        self.assertIn("has-a-record", self.names())


class PhantomLoss(Base):
    """The -99% class. These are the exact prod figures."""

    def test_an_underfunded_agent_is_not_shown_at_minus_99(self):
        self._agent("cfgprobe-9257", None, cash=5000.0, trades=0)
        self._agent("fleet-canary", 5, cash=50_000.0, trades=0)
        self.assertEqual(self.names() & {"cfgprobe-9257", "fleet-canary"}, set())

    def test_the_underlying_arithmetic_is_still_wrong_when_it_does_trade(self):
        """Documents the REMAINING defect rather than pretending it is fixed:
        an owned agent seeded below INITIAL_CAPITAL that HAS traded still
        reports a loss it never took, because `agents` has no starting-capital
        column to measure against. The filters hide the common case; they do
        not repair the formula."""
        self._agent("underfunded-but-active", 6, cash=1000.0, trades=1)
        row = next(r for r in lb._compute_agent_rows()
                   if r["name"] == "underfunded-but-active")
        self.assertLess(row["profit_percent"], -98)   # still wrong, on purpose

    def test_a_fully_funded_trader_reads_zero(self):
        self._agent("fair", 7, cash=100_000.0, trades=1)
        row = next(r for r in lb._compute_agent_rows() if r["name"] == "fair")
        self.assertAlmostEqual(row["profit_percent"], 0.0, places=6)


class TheProdBoard(Base):
    """Reproduce prod's agent table and assert what survives."""

    def test_only_agents_that_ever_traded_are_ranked(self):
        for name in ("guide-deploy-check", "cfgprobe-9257",
                     "gate-verify-1784328779", "assistant-verify-e2e",
                     "intruder-verify-e2e", "fleet-deploy-check",
                     "stranger-v", "bostonbc"):
            self._agent(name, None, cash=1000.0)
        self._agent("pnl-deploy-check", None, cash=999.89, trades=2)
        self._agent("yoojinbe", 4, trades=0)
        self._agent("junekimsop", 7, trades=0)
        self._agent("boardcheck", 6, trades=0)
        self._agent("fleet-canary", 5, cash=50_000.0, trades=0)
        self._agent("scope-verify", 5, trades=0)
        self._agent("info", 5, cash=96_436.7, trades=155)
        self.assertEqual(self.names(), {"info", "pnl-deploy-check"})


if __name__ == "__main__":
    unittest.main()
