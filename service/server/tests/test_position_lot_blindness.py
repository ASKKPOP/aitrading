"""Position lot blindness (live 2026-08-13, run 1099 / SOL −$62 unrealized).

The chain: a cover's float residue left a DECIMAL-rounded zero row; every
position read was a bare fetchone that returned that stub; the desk was told
"flat" every cycle and re-opened its short six times; the add-churn guard
(qty 0 ⇒ off) and the run-budget cap (one-row basis) both slept; and a full
cover would have failed against a single lot's quantity.

Four fixes, each tested: epsilon close (no stub is ever left), mutation-time
lot consolidation (one book per run again), aggregated snapshot (readers see
the SUM), summed cost basis (the budget cap sees the real book).
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
import run_engine  # noqa: E402
import services  # noqa: E402
from routes_shared import get_position_snapshot  # noqa: E402


class LotBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "t.db")
        database.init_database()
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO agents (id, name, token, starting_capital)"
                    " VALUES (5, 'lot', 't', 100000.0)")
        conn.commit()
        conn.close()

    def tearDown(self):
        self.tmp.cleanup()

    def _lot(self, qty, entry, run_id=1099, leverage=3.0):
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO positions (agent_id, symbol, market, side, quantity,"
            " entry_price, opened_at, run_id, leverage) VALUES (5, 'SOLUSDT',"
            " 'crypto', ?, ?, ?, '2026-08-13T00:00:00Z', ?, ?)",
            ("short" if qty < 0 else "long", qty, entry, run_id, leverage))
        conn.commit()
        conn.close()

    def _rows(self, run_id=1099):
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT quantity, entry_price FROM positions WHERE"
                    " run_id = ? ORDER BY id", (run_id,))
        out = [dict(r) for r in cur.fetchall()]
        conn.close()
        return out

    def _mutate(self, action, qty, price):
        conn = database.get_db_connection()
        cur = conn.cursor()
        services._update_position_from_signal(
            5, "SOLUSDT", "crypto", action, qty, price,
            "2026-08-13T01:00:00Z", cursor=cur, run_id=1099, leverage=3.0)
        conn.commit()
        conn.close()


class EpsilonCloseTests(LotBase):
    def test_cover_float_residue_leaves_no_stub(self):
        """The stub's birth: cover 'all' with a 1e-9 float mismatch must
        DELETE the row, not park a rounded-zero ghost."""
        self._lot(-2281.55999195189, 0.44731)
        self._mutate("cover", 2281.55999195, 0.45135)   # residue ≈ -1.9e-9
        self.assertEqual(self._rows(), [], "no ghost row may survive a close")

    def test_sell_float_residue_leaves_no_stub(self):
        self._lot(5.000000001, 100.0)
        self._mutate("sell", 5.0, 101.0)
        self.assertEqual(self._rows(), [], "long side has the same epsilon")


class ConsolidationTests(LotBase):
    def test_add_merges_lots_instead_of_stacking(self):
        """The run-1099 shape: a zero stub plus live lots. The next mutation
        consolidates to ONE row and merges the add into it."""
        self._lot(0.0, 75.963)                    # the poisonous stub
        self._lot(-13.19273036, 75.437)
        self._lot(-13.13388321, 75.775)
        self._mutate("short", 10.0, 76.0)
        rows = self._rows()
        self.assertEqual(len(rows), 1, "one book per run, not a lot stack")
        self.assertAlmostEqual(float(rows[0]["quantity"]),
                               -(13.19273036 + 13.13388321 + 10.0), places=6)

    def test_full_cover_exits_a_multi_lot_stack(self):
        """Before the fix this raised 'Insufficient short position quantity'
        against one lot — the desk could not exit its own book."""
        self._lot(-13.0, 75.4)
        self._lot(-34.0, 75.6)
        self._mutate("cover", 47.0, 76.0)
        self.assertEqual(self._rows(), [])


class SnapshotAggregationTests(LotBase):
    def test_snapshot_sums_lots_and_weights_entry(self):
        self._lot(0.0, 75.963)
        self._lot(-10.0, 75.0)
        self._lot(-30.0, 76.0)
        conn = database.get_db_connection()
        pos = get_position_snapshot(conn.cursor(), 5, "crypto", "SOLUSDT",
                                    None, 1099)
        conn.close()
        self.assertAlmostEqual(float(pos["quantity"]), -40.0, places=6)
        self.assertAlmostEqual(float(pos["entry_price"]), 75.75, places=4)

    def test_no_rows_still_reads_none(self):
        conn = database.get_db_connection()
        pos = get_position_snapshot(conn.cursor(), 5, "crypto", "SOLUSDT",
                                    None, 1099)
        conn.close()
        self.assertIsNone(pos)

    def test_position_quantity_sees_the_whole_book(self):
        self._lot(0.0, 75.963)
        self._lot(-15.0, 75.7)
        self.assertAlmostEqual(
            run_engine._position_quantity(5, "crypto", "SOLUSDT", 1099),
            -15.0, places=6)


class CostBasisTests(LotBase):
    def test_open_cost_basis_sums_every_lot(self):
        self._lot(-13.0, 75.0, leverage=3.0)      # 13*75/3 = 325
        self._lot(-30.0, 76.0, leverage=3.0)      # 30*76/3 = 760
        self.assertAlmostEqual(
            run_engine._open_cost_basis(5, "crypto", "SOLUSDT", 1099),
            325.0 + 760.0, places=2)


if __name__ == "__main__":
    unittest.main()
