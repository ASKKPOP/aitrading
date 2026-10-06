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

    def _account(self, broker, mode="paper", active=1, updated="2026-01-02",
                 creds=False):
        blob = ""
        if creds:
            from execution.crypto import encrypt_credentials
            # IBKR's credential is the gateway session; everyone else key+secret.
            blob = encrypt_credentials(
                {"gateway_url": "https://gw/v1/api", "account_id": "DU1"}
                if broker == "ibkr" else {"key": "k", "secret": "s"})
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO broker_accounts (agent_id, broker, execution_mode,"
            " credentials_enc, is_active, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (self.agent_id, broker, mode, blob, active, updated, updated))
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


class _FakeVenue:
    """Stands in for the broker adapter: remembers which ACCOUNT ROW the
    gateway built it from, and answers every order as SUBMITTED."""

    def __init__(self, account):
        self.account = account
        self.broker_name = account["broker"]

    async def submit_order(self, order):
        order.status = xbase.OrderStatus.SUBMITTED
        order.broker_order_id = f"{self.broker_name}-1"
        return order

    async def get_order_status(self, broker_order_id, symbol=""):
        return {"status": xbase.OrderStatus.FILLED, "filled_qty": 1.0}


class SubmitPathsUseTheOrdersMarket(_DBBase):
    """2026-10-05 adversarial review: the gate (live_refusal_reason) checks a
    broker that supports the rule's market, but submit_live / submit_shadow
    picked the agent's most-recently-updated broker, market-blind. With a
    binance link plus a NEWER ibkr link, a crypto shadow order was built for
    ibkr and journalled `rejected` — the crypto venue never saw the dry run.
    Live: a real order sent to (and rejected by) the wrong venue."""

    def setUp(self):
        super().setUp()
        self.built = []
        patcher = patch("execution.gateway._broker_for",
                        side_effect=self._fake_broker_for)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _fake_broker_for(self, account, mode):
        self.built.append((account["broker"], mode))
        return _FakeVenue(account)

    def _two_brokers(self, newer):
        """binance (crypto) + ibkr (us-stock) both active; `newer` is the one
        with the later updated_at — the one the market-blind pick returned."""
        older = "ibkr" if newer == "binance" else "binance"
        self._account(older, updated="2026-01-01", creds=True)
        self._account(newer, updated="2026-01-02", creds=True)

    # ── submit_shadow ────────────────────────────────────────────────────
    def test_shadow_crypto_goes_to_the_crypto_broker_when_ibkr_is_newer(self):
        from execution import gateway as g
        self._two_brokers(newer="ibkr")
        order = g.submit_shadow(self.agent_id, "BTCUSDT", "crypto", "buy",
                                0.01, 50_000.0, ledger_quantity=0.01)
        self.assertEqual(order.broker, "binance")
        self.assertEqual([b for b, _ in self.built], ["binance"])

    def test_shadow_crypto_goes_to_the_crypto_broker_when_binance_is_newer(self):
        from execution import gateway as g
        self._two_brokers(newer="binance")
        order = g.submit_shadow(self.agent_id, "BTCUSDT", "crypto", "buy",
                                0.01, 50_000.0, ledger_quantity=0.01)
        self.assertEqual(order.broker, "binance")

    def test_shadow_stock_goes_to_the_stock_broker_when_binance_is_newer(self):
        from execution import gateway as g
        self._two_brokers(newer="binance")
        order = g.submit_shadow(self.agent_id, "MSFT", "us-stock", "buy",
                                1.0, 400.0, ledger_quantity=1.0)
        self.assertEqual(order.broker, "ibkr")
        self.assertEqual([b for b, _ in self.built], ["ibkr"])

    def test_shadow_with_no_broker_for_the_market_is_no_gateway(self):
        """Only a stock broker linked: a crypto shadow order has nothing to
        mirror into — None, exactly like an agent with no link at all. It must
        NOT be built for the stock venue and journalled as rejected."""
        from execution import gateway as g
        self._account("ibkr", creds=True)
        order = g.submit_shadow(self.agent_id, "BTCUSDT", "crypto", "buy",
                                0.01, 50_000.0, ledger_quantity=0.01)
        self.assertIsNone(order)
        self.assertEqual(self.built, [])
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) AS n FROM broker_orders WHERE agent_id = ?",
                    (self.agent_id,))
        n = dict(cur.fetchone())["n"]
        cur.execute("SELECT COUNT(*) AS n FROM position_reconciliations"
                    " WHERE agent_id = ?", (self.agent_id,))
        r = dict(cur.fetchone())["n"]
        conn.close()
        self.assertEqual((n, r), (0, 0))

    # ── submit_live ──────────────────────────────────────────────────────
    def test_live_crypto_goes_to_the_crypto_broker_when_ibkr_is_newer(self):
        from execution import gateway as g
        self._two_brokers(newer="ibkr")
        order = g.submit_live(self.agent_id, "BTCUSDT", "crypto", "buy",
                              0.01, 50_000.0)
        self.assertEqual(order.broker, "binance")
        self.assertIs(order.status, xbase.OrderStatus.SUBMITTED)
        self.assertEqual(self.built, [("binance", xbase.ExecutionMode.LIVE)])

    def test_live_crypto_goes_to_the_crypto_broker_when_binance_is_newer(self):
        from execution import gateway as g
        self._two_brokers(newer="binance")
        order = g.submit_live(self.agent_id, "BTCUSDT", "crypto", "buy",
                              0.01, 50_000.0)
        self.assertEqual(order.broker, "binance")
        self.assertIs(order.status, xbase.OrderStatus.SUBMITTED)

    def test_live_stock_goes_to_the_stock_broker_when_binance_is_newer(self):
        from execution import gateway as g
        self._two_brokers(newer="binance")
        order = g.submit_live(self.agent_id, "MSFT", "us-stock", "buy",
                              1.0, 400.0)
        self.assertEqual(order.broker, "ibkr")
        self.assertEqual(self.built, [("ibkr", xbase.ExecutionMode.LIVE)])

    def test_live_with_no_broker_for_the_market_is_refused_never_rerouted(self):
        """Only a stock broker linked: a live CRYPTO order is refused with the
        configure-a-gateway message. No adapter is built — not the stock
        venue, not the paper ledger. The refusal is journalled."""
        from execution import gateway as g
        self._account("ibkr", creds=True)
        order = g.submit_live(self.agent_id, "BTCUSDT", "crypto", "buy",
                              0.01, 50_000.0)
        self.assertIs(order.status, xbase.OrderStatus.REJECTED)
        self.assertEqual(order.error_message, g.NOT_CONFIGURED)
        self.assertIsNone(order.broker_order_id)
        self.assertEqual(self.built, [])
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT status, error_message FROM broker_orders"
                    " WHERE agent_id = ?", (self.agent_id,))
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        self.assertEqual(rows, [{"status": "rejected",
                                 "error_message": g.NOT_CONFIGURED}])

    # ── gateway_health ───────────────────────────────────────────────────
    def test_health_for_a_market_reports_that_markets_broker(self):
        from execution import gateway as g
        self._two_brokers(newer="ibkr")
        self.assertEqual(g.gateway_health(self.agent_id, market="crypto")["broker"],
                         "binance")
        self.assertEqual(g.gateway_health(self.agent_id, market="us-stock")["broker"],
                         "ibkr")

    def test_health_for_an_unsupported_market_is_unconfigured(self):
        from execution import gateway as g
        self._account("ibkr", creds=True)
        h = g.gateway_health(self.agent_id, market="crypto")
        self.assertFalse(h["configured"])
        self.assertIn("no trading gateway", h["detail"])

    def test_health_without_a_market_keeps_the_legacy_pick(self):
        from execution import gateway as g
        self._two_brokers(newer="ibkr")
        self.assertEqual(g.gateway_health(self.agent_id)["broker"], "ibkr")

    # ── reconcile_orders_tick ────────────────────────────────────────────
    def test_reconciler_finds_the_order_venue_when_a_newer_other_market_link_exists(self):
        """A submitted binance order must still be looked up on binance after
        the user links ibkr — the sweep keyed accounts per agent, so every
        order from the older link counted as lookup_failed forever."""
        from execution import gateway as g
        self._two_brokers(newer="ibkr")
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO broker_orders
               (agent_id, symbol, market, side, quantity, price, status,
                execution_mode, broker, broker_order_id, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (self.agent_id, "BTCUSDT", "crypto", "buy", 1.0, 50_000.0,
             "submitted", "live", "binance", "binance-1", "2026-01-03"))
        conn.commit(); conn.close()
        with patch("alerts.send_alert"):
            out = g.reconcile_orders_tick()
        self.assertEqual((out["checked"], out["settled"], out["lookup_failed"]),
                         (1, 1, 0))
        self.assertEqual([b for b, _ in self.built], ["binance"])


if __name__ == "__main__":
    unittest.main()
