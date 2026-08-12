"""Pre-live TODO #3 — per-market broker routing (multi-gateway live).

The activation flow already allows several brokers active at once (connect
deactivates same-broker rows only); the router was the bottleneck: ONE
active row, market-blind (LIMIT 1). Now: a broker→markets capability map,
and the router picks the active account that supports the ORDER'S market —
a stock broker and a crypto broker both active, each order routed to its
own. Fail-closed: a market no active broker supports lands on the paper
ledger, never mis-routed to the wrong venue.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
from execution import base as xbase
from execution import router as xrouter


class CapabilityMap(unittest.TestCase):
    def test_stock_brokers(self):
        for b in ("alpaca", "ibkr"):
            self.assertTrue(xbase.broker_supports_market(b, "us-stock"), b)
            self.assertFalse(xbase.broker_supports_market(b, "crypto"), b)

    def test_crypto_brokers(self):
        for b in ("binance", "kraken", "coinbase", "okx", "bybit", "kucoin",
                  "cryptocom", "upbit"):
            self.assertTrue(xbase.broker_supports_market(b, "crypto"), b)
            self.assertFalse(xbase.broker_supports_market(b, "us-stock"), b)

    def test_unknown_broker_fails_closed(self):
        self.assertFalse(xbase.broker_supports_market("mystery", "crypto"))

    def test_no_market_means_any(self):
        self.assertTrue(xbase.broker_supports_market("kraken", None))


class _DBBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO agents (name, cash) VALUES ('g', 1000)")
        self.agent_id = cur.lastrowid
        conn.commit(); conn.close()

    def tearDown(self):
        self.tmp.cleanup()

    def _account(self, broker, mode="paper", active=1, updated="2026-01-02"):
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO broker_accounts (agent_id, broker, execution_mode,"
            " is_active, created_at, updated_at) VALUES (?,?,?,?,?,?)",
            (self.agent_id, broker, mode, active, updated, updated))
        conn.commit(); conn.close()


class PerMarketSelection(_DBBase):
    def test_both_active_each_market_routes_to_its_broker(self):
        self._account("kraken", updated="2026-01-01")
        self._account("alpaca", updated="2026-01-02")
        us = xrouter._get_active_broker_account(self.agent_id, "us-stock")
        cr = xrouter._get_active_broker_account(self.agent_id, "crypto")
        self.assertEqual(us["broker"], "alpaca")
        self.assertEqual(cr["broker"], "kraken")

    def test_unsupported_market_returns_none(self):
        self._account("kraken")
        self.assertIsNone(
            xrouter._get_active_broker_account(self.agent_id, "us-stock"))

    def test_legacy_no_market_keeps_most_recent(self):
        self._account("kraken", updated="2026-01-01")
        self._account("alpaca", updated="2026-01-02")
        acct = xrouter._get_active_broker_account(self.agent_id)
        self.assertEqual(acct["broker"], "alpaca")   # most recently updated

    def test_inactive_rows_never_selected(self):
        self._account("alpaca", active=0)
        self.assertIsNone(
            xrouter._get_active_broker_account(self.agent_id, "us-stock"))


class ExecuteWiring(_DBBase):
    def test_execute_passes_the_orders_market(self):
        import asyncio
        seen = {}
        orig = xrouter._get_active_broker_account

        def spy(agent_id, market=None):
            seen["market"] = market
            return None                      # -> paper path, no broker calls
        order = xbase.Order(agent_id=self.agent_id, symbol="MSFT",
                            market="us-stock", side="buy", quantity=1.0,
                            price=100.0)
        with patch.object(xrouter, "_get_active_broker_account",
                          side_effect=spy):
            with patch.object(xrouter, "_persist_order", return_value=1):
                out = asyncio.run(
                    xrouter.ExecutionRouter().execute(self.agent_id, order))
        self.assertEqual(seen["market"], "us-stock")
        self.assertEqual(out.broker, "paper")
        del orig


class LiveRefusalMarketAware(_DBBase):
    def test_live_rule_needs_a_gateway_for_ITS_market(self):
        from execution import gateway as g
        # only a stock broker connected (no creds): a live CRYPTO rule must
        # refuse with NOT_CONFIGURED (no matching gateway at all), while the
        # market-blind legacy call finds the alpaca row and reaches the
        # credentials branch instead.
        self._account("alpaca")
        crypto_reason = g.live_refusal_reason(self.agent_id, "live",
                                              market="crypto")
        legacy_reason = g.live_refusal_reason(self.agent_id, "live")
        self.assertEqual(crypto_reason, g.NOT_CONFIGURED)
        self.assertEqual(legacy_reason, g.NOT_CONFIGURED_NO_CREDS)


if __name__ == "__main__":
    unittest.main()
