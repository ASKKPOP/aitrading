"""Terminal (spot/futures) backend surface — the ga-parity additions.

Covers the three market-data endpoints the terminals poll (recent trades,
funding, fee rates) and PATCH /api/positions/{id}/tpsl, whose three-state
semantics (absent=keep / null=clear / number=set) and side-aware validation
are what keep a fat-fingered TP from instantly closing a position.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import crypto_feed
import database
from routes import create_app


# ─── crypto_feed.fetch_trades ────────────────────────────────────────────────

class FetchTradesTests(unittest.TestCase):
    def test_normalises_okx_rows(self):
        rows = [
            {"ts": "1700000001000", "px": "63800.5", "sz": "0.04", "side": "sell"},
            {"ts": "1700000000000", "px": "63800.0", "sz": "1.2", "side": "buy"},
        ]
        with patch.object(crypto_feed, "_okx_get", return_value=rows):
            trades = crypto_feed.fetch_trades("BTCUSDT", 30)
        self.assertEqual(trades, [
            {"ts": 1700000001000, "price": 63800.5, "size": 0.04, "side": "sell"},
            {"ts": 1700000000000, "price": 63800.0, "size": 1.2, "side": "buy"},
        ])

    def test_skips_malformed_rows(self):
        rows = [
            {"ts": "not-a-number", "px": "1", "sz": "1", "side": "buy"},
            {"px": "63800.0"},  # missing ts/sz
            {"ts": "1700000000000", "px": "63800.0", "sz": "1.2", "side": "buy"},
        ]
        with patch.object(crypto_feed, "_okx_get", return_value=rows):
            trades = crypto_feed.fetch_trades("BTCUSDT")
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0]["price"], 63800.0)

    def test_limit_clamped_to_okx_max(self):
        with patch.object(crypto_feed, "_okx_get", return_value=[]) as mock_get:
            crypto_feed.fetch_trades("BTCUSDT", 999)
        self.assertEqual(mock_get.call_args[0][1]["limit"], "100")


# ─── route surface ───────────────────────────────────────────────────────────

class _TerminalRouteBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())

    def tearDown(self):
        self.tmp.cleanup()

    def _agent(self, name: str = "tpsl-bot") -> dict:
        r = self.client.post("/api/claw/agents/selfRegister",
                             json={"name": name, "password": "testpass123"})
        assert r.status_code == 200, r.text
        body = r.json()
        return {"id": body["agent_id"],
                "headers": {"Authorization": f"Bearer {body['token']}"}}

    def _position(self, agent_id: int, side: str = "long", qty: float = 0.01,
                  entry: float = 63000.0, current: float | None = 64000.0,
                  sl: float | None = None, tp: float | None = None) -> int:
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO positions (agent_id, symbol, market, side, quantity,
                                      entry_price, current_price, stop_loss, take_profit,
                                      opened_at)
               VALUES (?, 'BTC', 'crypto', ?, ?, ?, ?, ?, ?, '2026-07-31T00:00:00Z')""",
            (agent_id, side, qty if side == "long" else -qty, entry, current, sl, tp))
        pos_id = cur.lastrowid
        conn.commit()
        conn.close()
        return pos_id


class TpslEndpointTests(_TerminalRouteBase):
    def test_sets_both_levels(self):
        a = self._agent()
        pid = self._position(a["id"])  # long @ current 64000
        r = self.client.patch(f"/api/positions/{pid}/tpsl", headers=a["headers"],
                              json={"stop_loss": 60000, "take_profit": 70000})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json(), {"id": pid, "stop_loss": 60000.0, "take_profit": 70000.0})

    def test_three_state_absent_keeps_null_clears(self):
        """The zenix contract: {stop_loss: null} clears SL and must NOT touch TP."""
        a = self._agent()
        pid = self._position(a["id"], sl=60000.0, tp=70000.0)
        r = self.client.patch(f"/api/positions/{pid}/tpsl", headers=a["headers"],
                              json={"stop_loss": None})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIsNone(r.json()["stop_loss"])
        self.assertEqual(r.json()["take_profit"], 70000.0)

    def test_long_rejects_wrong_side_levels(self):
        a = self._agent()
        pid = self._position(a["id"], side="long", current=64000.0)
        r = self.client.patch(f"/api/positions/{pid}/tpsl", headers=a["headers"],
                              json={"stop_loss": 65000})       # above price
        self.assertEqual(r.status_code, 422)
        r = self.client.patch(f"/api/positions/{pid}/tpsl", headers=a["headers"],
                              json={"take_profit": 63000})     # below price
        self.assertEqual(r.status_code, 422)

    def test_short_validation_is_inverted(self):
        a = self._agent()
        pid = self._position(a["id"], side="short", current=64000.0)
        # Valid for a short: SL above, TP below.
        r = self.client.patch(f"/api/positions/{pid}/tpsl", headers=a["headers"],
                              json={"stop_loss": 66000, "take_profit": 60000})
        self.assertEqual(r.status_code, 200, r.text)
        # Inverted levels refused.
        r = self.client.patch(f"/api/positions/{pid}/tpsl", headers=a["headers"],
                              json={"stop_loss": 60000})
        self.assertEqual(r.status_code, 422)

    def test_foreign_position_is_404(self):
        owner = self._agent("owner-bot")
        thief = self._agent("thief-bot")
        pid = self._position(owner["id"])
        r = self.client.patch(f"/api/positions/{pid}/tpsl", headers=thief["headers"],
                              json={"stop_loss": 60000})
        self.assertEqual(r.status_code, 404)

    def test_empty_body_is_422(self):
        a = self._agent()
        pid = self._position(a["id"])
        r = self.client.patch(f"/api/positions/{pid}/tpsl", headers=a["headers"], json={})
        self.assertEqual(r.status_code, 422)

    def test_closed_position_is_409(self):
        a = self._agent()
        pid = self._position(a["id"], qty=0.0)
        r = self.client.patch(f"/api/positions/{pid}/tpsl", headers=a["headers"],
                              json={"stop_loss": 60000})
        self.assertEqual(r.status_code, 409)

    def test_requires_auth(self):
        a = self._agent()
        pid = self._position(a["id"])
        r = self.client.patch(f"/api/positions/{pid}/tpsl", json={"stop_loss": 60000})
        self.assertEqual(r.status_code, 401)


class MarketDataEndpointTests(_TerminalRouteBase):
    def test_trades_endpoint_wraps_fetch_trades(self):
        sample = [{"ts": 1700000000000, "price": 63800.0, "size": 1.2, "side": "buy"}]
        with patch("routes_market.fetch_trades", return_value=sample) as mock_fn:
            r = self.client.get("/api/markets/crypto/trades?symbol=btcusdt&limit=5")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json(), {"symbol": "BTCUSDT", "trades": sample})
        mock_fn.assert_called_once_with("BTCUSDT", 5)

    def test_trades_upstream_failure_is_503(self):
        with patch("routes_market.fetch_trades", side_effect=RuntimeError("OKX down")):
            r = self.client.get("/api/markets/crypto/trades?symbol=NOPEUSDT")
        self.assertEqual(r.status_code, 503)

    def test_funding_endpoint_wraps_fetch_funding_rate(self):
        sample = {"symbol": "BTCUSDT", "funding_rate": 0.0001, "next_funding_time": 1700000000000}
        with patch("routes_market.fetch_funding_rate", return_value=sample):
            r = self.client.get("/api/markets/crypto/funding?symbol=BTCUSDT")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["funding_rate"], 0.0001)

    def test_fees_endpoint_covers_all_tradeable_markets(self):
        from markets import tradeable_markets
        r = self.client.get("/api/markets/fees")
        self.assertEqual(r.status_code, 200, r.text)
        rates = r.json()["rates"]
        self.assertEqual(set(rates), set(tradeable_markets()))
        for market, rate in rates.items():
            self.assertIsInstance(rate, float, market)
            self.assertGreaterEqual(rate, 0.0)
            self.assertLess(rate, 0.11)


if __name__ == "__main__":
    unittest.main()
