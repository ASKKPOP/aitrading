"""Profit on a leveraged book.

2026-08-07: profit was computed three ways and every one was wrong for a
leveraged position, because `agents.cash` has only the MARGIN deducted while
the SQL added back the whole NOTIONAL. Agent 6 read -29.04 (-2.9%) on the
profile and +30.09 (+3.0%) on the leaderboard while it was +0.51 (+0.05%) up.
"""
import os
import tempfile
import unittest

import database
from portfolio_value import POSITION_VALUE_SUM, position_value


class PositionValueTests(unittest.TestCase):
    def test_a_position_is_worth_margin_plus_unrealized(self):
        # $100 notional at 2x = $50 margin; price +10% -> +$10 unrealized.
        self.assertAlmostEqual(
            position_value(10.0, 10, 11.0, "long", 2), 50.0 + 10.0, places=6)

    def test_short_profits_as_price_falls(self):
        self.assertAlmostEqual(
            position_value(10.0, 10, 9.0, "short", 2), 50.0 + 10.0, places=6)

    def test_unpriced_position_is_worth_its_margin(self):
        self.assertAlmostEqual(
            position_value(10.0, 10, None, "long", 4), 25.0, places=6)

    def test_spot_is_unchanged_by_the_fix(self):
        """At leverage 1 the new expression equals the old notional+unrealized,
        so spot books must not move at all."""
        for lev in (1, None, 0):        # 0 and None both mean unleveraged
            self.assertAlmostEqual(
                position_value(10.0, 10, 11.0, "long", lev), 110.0, places=6,
                msg=f"spot moved at leverage={lev!r}")


class ProfitOnALeveragedBookTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "p.db")
        database.init_database()

    def tearDown(self):
        self.tmp.cleanup()

    def _book(self):
        """Seed 1000, $100 notional long at 2x (so $50 margin), price flat."""
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO agents (name, cash, starting_capital) VALUES (?, ?, ?)",
                ("lev", 950.0, 1000.0))          # 1000 - 50 margin
            cur.execute("SELECT id FROM agents ORDER BY id DESC")
            aid = dict(cur.fetchone())["id"]
            cur.execute(
                "INSERT INTO positions (agent_id, symbol, market, side, quantity, "
                "entry_price, current_price, leverage, opened_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (aid, "X", "futures", "long", 10.0, 10.0, 10.0, 2.0,
                 "2026-08-07T00:00:00Z"))
            conn.commit()
            return aid
        finally:
            conn.close()

    def _open_value(self, aid):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute(f"SELECT {POSITION_VALUE_SUM} AS v FROM positions p "
                        "WHERE p.agent_id = ?", (aid,))
            return float(dict(cur.fetchone())["v"] or 0)
        finally:
            conn.close()

    def test_a_flat_leveraged_book_shows_zero_profit_not_a_loss(self):
        aid = self._book()
        cash, seed = 950.0, 1000.0
        self.assertAlmostEqual(self._open_value(aid), 50.0, places=6,
                               msg="position must be worth its margin")
        self.assertAlmostEqual(cash + self._open_value(aid) - seed, 0.0,
                               places=6)
        # the old expression, for contrast
        self.assertAlmostEqual(cash - seed, -50.0, places=6,
                               msg="this is what the profile used to report")

    def test_the_sql_no_longer_adds_back_the_whole_notional(self):
        aid = self._book()
        self.assertAlmostEqual(self._open_value(aid), 50.0, places=6)
        self.assertNotAlmostEqual(self._open_value(aid), 100.0, places=6,
                                  msg="notional is being added back — the "
                                      "leaderboard's old over-count")

    def test_a_winning_leveraged_position_reports_its_gain_once(self):
        aid = self._book()
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("UPDATE positions SET current_price = ? WHERE agent_id = ?",
                        (11.0, aid))
            conn.commit()
        finally:
            conn.close()
        # margin 50 + unrealized 10
        self.assertAlmostEqual(self._open_value(aid), 60.0, places=6)
        self.assertAlmostEqual(950.0 + self._open_value(aid) - 1000.0, 10.0,
                               places=6, msg="a +10% move on $100 notional is "
                                             "+$10, counted exactly once")


if __name__ == "__main__":
    unittest.main()
