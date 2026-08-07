"""GET /api/positions/trades/summary — capless realized-P&L aggregate.

Regression for the /automation summary strip: it summed realized P&L
client-side over GET /api/positions/trades?limit=200 (server cap 200), so
any account with more than 200 fills silently lost its oldest fills from
the lifetime/올해 figures, and the numbers drifted as new fills pushed old
ones out (prod agent 6: capped sum -2.31 vs true lifetime +114.82). The
tile sums must come from this SQL aggregate, which has no row cap.
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

SPLIT = '2026-07-25'


class TradesSummaryTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())
        resp = self.client.post(
            "/api/claw/agents/selfRegister",
            json={"name": "summary-agent", "password": "pw123", "initial_balance": 100000.0},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        self.agent_id = body["agent_id"]
        self.headers = {"Authorization": f"Bearer {body['token']}"}

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _insert_fills(self, rows: list[tuple[str, float | None]]) -> None:
        """rows: (created_at, pnl) — pnl None on opening legs."""
        conn = database.get_db_connection()
        cursor = conn.cursor()
        for i, (created_at, pnl) in enumerate(rows):
            cursor.execute(
                """INSERT INTO signals
                   (signal_id, agent_id, message_type, market, symbol, side,
                    pnl, timestamp, created_at)
                   VALUES (?, ?, 'operation', 'crypto', 'BTC', 'sell', ?, ?, ?)""",
                (900000 + i, self.agent_id, pnl, 1700000000 + i, created_at),
            )
        conn.commit()
        conn.close()

    def _summary(self, **params) -> dict:
        resp = self.client.get("/api/positions/trades/summary",
                               params=params, headers=self.headers)
        self.assertEqual(resp.status_code, 200, resp.text)
        return resp.json()

    def test_requires_auth(self):
        resp = self.client.get("/api/positions/trades/summary")
        self.assertEqual(resp.status_code, 401)

    def test_empty_book(self):
        out = self._summary(since='2026-08-01T00:00:00.000Z', split=SPLIT)
        self.assertEqual(out['pnl'], 0)
        self.assertEqual(out['trades'], 0)
        self.assertIsNone(out['first_trade'])
        self.assertIsNone(out['last_trade'])
        self.assertEqual(out['split']['pnl'], 0)
        self.assertEqual(out['split']['trades'], 0)
        self.assertEqual(out['window']['pnl'], 0)
        self.assertEqual(out['window']['trades'], 0)
        self.assertEqual(out['window']['split_pnl'], 0)

    def test_lifetime_split_and_window_sums(self):
        self._insert_fills([
            ('2026-07-17T10:00:00.000000Z', 100.0),   # pre-split
            ('2026-07-20T10:00:00Z', 50.0),           # pre-split
            ('2026-07-24T23:59:59.999999Z', 25.0),    # pre-split (edge)
            ('2026-07-25T00:00:00Z', -10.0),          # split boundary
            ('2026-07-26T10:00:00Z', None),           # opening leg, no pnl
            ('2026-08-01T10:00:00Z', -30.0),          # in window
            ('2026-08-02T10:00:00Z', 5.0),            # in window
        ])
        out = self._summary(since='2026-08-01T00:00:00.000Z', split=SPLIT)
        self.assertAlmostEqual(out['pnl'], 140.0, places=6)
        self.assertEqual(out['trades'], 7)
        self.assertEqual(out['first_trade'], '2026-07-17T10:00:00.000000Z')
        self.assertEqual(out['last_trade'], '2026-08-02T10:00:00Z')
        # split (>= 2026-07-25 lexically, matching the client string compare)
        self.assertAlmostEqual(out['split']['pnl'], -35.0, places=6)
        self.assertEqual(out['split']['trades'], 4)
        # window (>= since)
        self.assertAlmostEqual(out['window']['pnl'], -25.0, places=6)
        self.assertEqual(out['window']['trades'], 2)
        # window ∩ split = the later boundary (since here)
        self.assertAlmostEqual(out['window']['split_pnl'], -25.0, places=6)

    def test_window_before_split_uses_split_boundary(self):
        self._insert_fills([
            ('2026-07-20T10:00:00Z', 50.0),
            ('2026-07-26T10:00:00Z', -10.0),
        ])
        out = self._summary(since='2026-07-01T00:00:00.000Z', split=SPLIT)
        self.assertAlmostEqual(out['window']['pnl'], 40.0, places=6)
        self.assertEqual(out['window']['trades'], 2)
        # since < split → the overlap starts at the split epoch
        self.assertAlmostEqual(out['window']['split_pnl'], -10.0, places=6)

    def test_open_leg_fees_reduce_realized(self):
        """A closing leg's pnl nets only ITS OWN fee (automation.py); the
        opening leg's fee was invisible here. Measured on prod agent 6: tile
        +1.02 vs the runs ledger's +0.79 — the 0.2342 gap was exactly the
        open-leg fees. An open row (pnl NULL) must contribute minus its fee,
        in every bucket (lifetime, split, window)."""
        conn = database.get_db_connection()
        cursor = conn.cursor()
        rows = [
            # (created_at, pnl, fee_usd)
            ('2026-07-20T10:00:00Z', None, 0.10),   # open, pre-split
            ('2026-07-26T10:00:00Z', 1.00, 0.05),   # close (pnl already net)
            ('2026-08-01T10:00:00Z', None, 0.20),   # open, in window
        ]
        for i, (created_at, pnl, fee) in enumerate(rows):
            cursor.execute(
                """INSERT INTO signals
                   (signal_id, agent_id, message_type, market, symbol, side,
                    pnl, fee_usd, timestamp, created_at)
                   VALUES (?, ?, 'operation', 'crypto', 'BTC', 'sell', ?, ?, ?, ?)""",
                (910000 + i, self.agent_id, pnl, fee, 1700000000 + i, created_at),
            )
        conn.commit()
        conn.close()
        out = self._summary(since='2026-08-01T00:00:00.000Z', split=SPLIT)
        self.assertAlmostEqual(out['pnl'], 0.70, places=6)          # 1.00 - 0.10 - 0.20
        self.assertAlmostEqual(out['split']['pnl'], 0.80, places=6)  # 1.00 - 0.20
        self.assertAlmostEqual(out['window']['pnl'], -0.20, places=6)

    def test_params_optional(self):
        self._insert_fills([('2026-07-20T10:00:00Z', 50.0)])
        out = self._summary()
        self.assertAlmostEqual(out['pnl'], 50.0, places=6)
        self.assertNotIn('split', out)
        self.assertNotIn('window', out)

    def test_no_row_cap(self):
        # 250 closed fills of $1 — 50 more than the trades-list cap. The
        # capped list must still return 200 rows; the aggregate must see all.
        rows = [(f'2026-07-18T{h:02d}:{m:02d}:00Z', 1.0)
                for h in range(11) for m in range(25)][:250]
        self._insert_fills(rows)
        listed = self.client.get("/api/positions/trades",
                                 params={"limit": 500}, headers=self.headers)
        self.assertEqual(listed.json()['count'], 200)
        out = self._summary(split=SPLIT)
        self.assertAlmostEqual(out['pnl'], 250.0, places=6)
        self.assertEqual(out['trades'], 250)
        self.assertAlmostEqual(out['split']['pnl'], 0.0, places=6)


if __name__ == "__main__":
    unittest.main()
