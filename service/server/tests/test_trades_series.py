"""GET /api/positions/trades/series — hourly realized-P&L buckets for the
summary-tile graphs.

The /automation tile modals draw a cumulative profit curve. Like the sums
(#219), the curve must NOT come from the 200-row capped trades list — a
window whose fills exceed the cap would silently flatten its oldest days.
The server groups ALL fills by hour in SQL; the client accumulates and
re-buckets to local days for display, so no timezone math lives in SQL.
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


class TradesSeriesTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())
        resp = self.client.post(
            "/api/claw/agents/selfRegister",
            json={"name": "series-agent", "password": "pw123", "initial_balance": 100000.0},
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
                (910000 + i, self.agent_id, pnl, 1700000000 + i, created_at),
            )
        conn.commit()
        conn.close()

    def _series(self, **params) -> dict:
        resp = self.client.get("/api/positions/trades/series",
                               params=params, headers=self.headers)
        self.assertEqual(resp.status_code, 200, resp.text)
        return resp.json()

    def test_requires_auth(self):
        resp = self.client.get("/api/positions/trades/series")
        self.assertEqual(resp.status_code, 401)

    def test_empty_book(self):
        out = self._series(since='2026-08-01T00:00:00.000Z', split=SPLIT)
        self.assertEqual(out['points'], [])

    def test_hourly_buckets_ascending_with_split(self):
        self._insert_fills([
            ('2026-07-20T10:15:00Z', 50.0),            # pre-split
            ('2026-07-26T09:05:00Z', -10.0),           # post-split, hour A
            ('2026-07-26T09:40:00.123456Z', 4.0),      # post-split, same hour A
            ('2026-07-26T11:00:00Z', None),            # opening leg, no pnl
            ('2026-07-27T00:00:00Z', 7.5),             # post-split, hour B
        ])
        out = self._series(split=SPLIT)
        pts = out['points']
        self.assertEqual([p['t'] for p in pts],
                         ['2026-07-20T10', '2026-07-26T09',
                          '2026-07-26T11', '2026-07-27T00'])
        by_t = {p['t']: p for p in pts}
        self.assertAlmostEqual(by_t['2026-07-20T10']['pnl'], 50.0, places=6)
        self.assertAlmostEqual(by_t['2026-07-20T10']['split_pnl'], 0.0, places=6)
        self.assertAlmostEqual(by_t['2026-07-26T09']['pnl'], -6.0, places=6)
        self.assertAlmostEqual(by_t['2026-07-26T09']['split_pnl'], -6.0, places=6)
        self.assertEqual(by_t['2026-07-26T09']['trades'], 2)
        # opening leg: counts as a fill, contributes 0 P&L
        self.assertAlmostEqual(by_t['2026-07-26T11']['pnl'], 0.0, places=6)
        self.assertEqual(by_t['2026-07-26T11']['trades'], 1)
        self.assertAlmostEqual(by_t['2026-07-27T00']['pnl'], 7.5, places=6)

    def test_open_leg_fee_lands_in_its_own_hour(self):
        """An opening leg's fee is realized cost the moment it is paid; the
        graph must show it in that hour, not hide it (the summary tile and
        this series must agree — prod showed +1.02 for a +0.79 book)."""
        conn = database.get_db_connection()
        cursor = conn.cursor()
        for i, (created_at, pnl, fee) in enumerate([
                ('2026-07-26T09:10:00Z', None, 0.10),   # open with fee
                ('2026-07-26T10:20:00Z', 1.00, 0.05)]):  # close, pnl net already
            cursor.execute(
                """INSERT INTO signals
                   (signal_id, agent_id, message_type, market, symbol, side,
                    pnl, fee_usd, timestamp, created_at)
                   VALUES (?, ?, 'operation', 'crypto', 'BTC', 'sell', ?, ?, ?, ?)""",
                (920000 + i, self.agent_id, pnl, fee, 1700000000 + i, created_at),
            )
        conn.commit()
        conn.close()
        out = self._series(split=SPLIT)
        by_t = {p['t']: p for p in out['points']}
        self.assertAlmostEqual(by_t['2026-07-26T09']['pnl'], -0.10, places=6)
        self.assertAlmostEqual(by_t['2026-07-26T10']['pnl'], 1.00, places=6)

    def test_since_windows_the_series(self):
        self._insert_fills([
            ('2026-07-20T10:00:00Z', 50.0),
            ('2026-08-01T10:00:00Z', -30.0),
            ('2026-08-02T10:00:00Z', 5.0),
        ])
        out = self._series(since='2026-08-01T00:00:00.000Z')
        self.assertEqual([p['t'] for p in out['points']],
                         ['2026-08-01T10', '2026-08-02T10'])

    def test_space_datetime_format_merges_into_t_bucket(self):
        # Legacy rows store '2026-07-26 09:00:00' (space, no T). They must
        # land in the same bucket as ISO-T rows of the same hour.
        self._insert_fills([
            ('2026-07-26 09:00:00', 3.0),
            ('2026-07-26T09:30:00Z', 2.0),
        ])
        out = self._series()
        self.assertEqual(len(out['points']), 1)
        self.assertEqual(out['points'][0]['t'], '2026-07-26T09')
        self.assertAlmostEqual(out['points'][0]['pnl'], 5.0, places=6)

    def test_no_row_cap(self):
        # 250 fills of $1 across 250 distinct hours — beyond the trades-list
        # cap of 200; the series must still cover every hour.
        rows = []
        i = 0
        for d in range(18, 29):
            for h in range(24):
                if i >= 250:
                    break
                rows.append((f'2026-07-{d:02d}T{h:02d}:00:00Z', 1.0))
                i += 1
        self._insert_fills(rows)
        out = self._series()
        self.assertEqual(len(out['points']), 250)
        self.assertAlmostEqual(sum(p['pnl'] for p in out['points']), 250.0, places=6)


if __name__ == "__main__":
    unittest.main()
