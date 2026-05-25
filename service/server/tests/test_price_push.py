"""TDD test suite for Phase 4.5 — push-based market data.

Covers:
  - apply_price_update() writes to matching positions and returns count
  - apply_price_update() ignores nonexistent symbol/market combos
  - apply_price_update() respects token_id partition (Polymarket)
  - InMemoryPriceFeed: push → callback fires with the tick
  - InMemoryPriceFeed: multiple pushes preserve order
  - InMemoryPriceFeed: close stops further callback invocations
  - HyperliquidWebSocketFeed: parses 'allMids' message into PriceTick stream
  - HyperliquidWebSocketFeed: ignores malformed messages without crashing
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
from price_dispatch import apply_price_update
from price_feed import HyperliquidWebSocketFeed, InMemoryPriceFeed, PriceTick


def _run(coro):
    """Helper to drive a coroutine to completion inside a sync unittest."""
    return asyncio.new_event_loop().run_until_complete(coro)


# ── apply_price_update ────────────────────────────────────────────────────

class ApplyPriceUpdateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()

    def tearDown(self):
        self.tmp.cleanup()

    def _mk_agent_with_position(
        self,
        *,
        symbol: str = "BTC",
        market: str = "crypto",
        token_id: str = "",
        entry_price: float = 50_000.0,
        quantity: float = 1.0,
    ) -> int:
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) AS n FROM agents",
        )
        n = cur.fetchone()["n"]
        cur.execute(
            "INSERT INTO agents (name, token_hash, cash) VALUES (?, ?, 100000)",
            (f"agent-{n}", f"hash-{n}"),
        )
        agent_id = cur.lastrowid
        cur.execute(
            """INSERT INTO positions
                 (agent_id, symbol, market, side, entry_price, quantity,
                  current_price, token_id, opened_at)
               VALUES (?, ?, ?, 'long', ?, ?, NULL, ?, '2026-05-25T00:00:00Z')""",
            (agent_id, symbol, market, entry_price, quantity, token_id),
        )
        conn.commit()
        conn.close()
        return agent_id

    def test_writes_price_to_matching_position(self):
        self._mk_agent_with_position()
        rows = apply_price_update("BTC", "crypto", 51_000.0)
        self.assertEqual(rows, 1)

        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT current_price FROM positions WHERE symbol='BTC'")
        self.assertAlmostEqual(float(cur.fetchone()["current_price"]), 51_000.0)
        conn.close()

    def test_updates_every_matching_agents_position(self):
        self._mk_agent_with_position()
        self._mk_agent_with_position()  # second agent, same symbol
        rows = apply_price_update("BTC", "crypto", 52_000.0)
        self.assertEqual(rows, 2)

    def test_returns_zero_when_no_position_matches(self):
        self._mk_agent_with_position()
        rows = apply_price_update("ETH", "crypto", 3_000.0)
        self.assertEqual(rows, 0)

    def test_market_partition_is_respected(self):
        # Same symbol on different market shouldn't get the crypto price.
        self._mk_agent_with_position(symbol="AAPL", market="us-stock")
        rows = apply_price_update("AAPL", "crypto", 100.0)
        self.assertEqual(rows, 0)

    def test_token_id_partition_for_polymarket(self):
        self._mk_agent_with_position(symbol="market-x", market="polymarket", token_id="TOK_A")
        self._mk_agent_with_position(symbol="market-x", market="polymarket", token_id="TOK_B")
        rows = apply_price_update("market-x", "polymarket", 0.42, token_id="TOK_A")
        self.assertEqual(rows, 1)

    def test_rejects_negative_or_nan(self):
        self._mk_agent_with_position()
        with self.assertRaises(ValueError):
            apply_price_update("BTC", "crypto", -5.0)
        with self.assertRaises(ValueError):
            apply_price_update("BTC", "crypto", float("nan"))


# ── InMemoryPriceFeed ─────────────────────────────────────────────────────

class InMemoryFeedTests(unittest.TestCase):
    def test_push_invokes_callback_with_tick(self):
        received: list[PriceTick] = []
        feed = InMemoryPriceFeed()

        async def driver():
            await feed.start(on_tick=lambda t: received.append(t))
            await feed.push(PriceTick(symbol="BTC", market="crypto", price=50_000.0))
            await feed.close()

        _run(driver())
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].symbol, "BTC")
        self.assertEqual(received[0].price, 50_000.0)

    def test_multiple_pushes_preserve_order(self):
        received: list[PriceTick] = []
        feed = InMemoryPriceFeed()

        async def driver():
            await feed.start(on_tick=lambda t: received.append(t))
            for i in range(5):
                await feed.push(PriceTick("X", "crypto", float(i)))
            await feed.close()

        _run(driver())
        self.assertEqual([t.price for t in received], [0.0, 1.0, 2.0, 3.0, 4.0])

    def test_close_stops_further_callbacks(self):
        received: list[PriceTick] = []
        feed = InMemoryPriceFeed()

        async def driver():
            await feed.start(on_tick=lambda t: received.append(t))
            await feed.push(PriceTick("X", "crypto", 1.0))
            await feed.close()
            # Pushes after close are silently dropped (no exception).
            await feed.push(PriceTick("X", "crypto", 2.0))

        _run(driver())
        self.assertEqual(len(received), 1)

    def test_supports_async_callback(self):
        received: list[PriceTick] = []
        feed = InMemoryPriceFeed()

        async def async_handler(t: PriceTick) -> None:
            await asyncio.sleep(0)
            received.append(t)

        async def driver():
            await feed.start(on_tick=async_handler)
            await feed.push(PriceTick("X", "crypto", 1.0))
            await feed.close()

        _run(driver())
        self.assertEqual(len(received), 1)


# ── HyperliquidWebSocketFeed (parser only — no live network) ──────────────

class HyperliquidParserTests(unittest.TestCase):
    def setUp(self):
        self.feed = HyperliquidWebSocketFeed()

    def test_parses_allMids_message(self):
        msg = json.dumps({
            "channel": "allMids",
            "data": {"mids": {"BTC": "51234.5", "ETH": "3200.0"}},
        })
        ticks = list(self.feed._parse_message(msg))
        symbols = {t.symbol: t.price for t in ticks}
        self.assertEqual(symbols, {"BTC": 51_234.5, "ETH": 3_200.0})
        for t in ticks:
            self.assertEqual(t.market, "crypto")

    def test_ignores_non_allMids_channel(self):
        msg = json.dumps({
            "channel": "subscriptionResponse",
            "data": {"subscription": {"type": "allMids"}},
        })
        ticks = list(self.feed._parse_message(msg))
        self.assertEqual(ticks, [])

    def test_ignores_malformed_message(self):
        for bad in ["not-json", "{}", json.dumps({"channel": "allMids"})]:
            ticks = list(self.feed._parse_message(bad))
            self.assertEqual(ticks, [])

    def test_ignores_non_numeric_prices(self):
        msg = json.dumps({
            "channel": "allMids",
            "data": {"mids": {"BAD": "not-a-number", "BTC": "100.0"}},
        })
        ticks = list(self.feed._parse_message(msg))
        # BAD dropped, BTC kept.
        self.assertEqual([t.symbol for t in ticks], ["BTC"])


# ── price_push_loop (env-gated registration) ──────────────────────────────

class PushLoopTests(unittest.TestCase):
    def test_loop_returns_immediately_when_disabled(self):
        """Default state — ENABLE_PRICE_PUSH unset — must not open a socket."""
        os.environ.pop("ENABLE_PRICE_PUSH", None)
        from tasks import price_push_loop

        # Should return inside the millisecond without hitting the network.
        async def driver():
            await asyncio.wait_for(price_push_loop(), timeout=0.5)

        # No exception, no timeout = correct disabled behavior.
        _run(driver())

    def test_loop_is_registered_in_background_tasks(self):
        from tasks import BACKGROUND_TASK_REGISTRY
        self.assertIn("price_push", BACKGROUND_TASK_REGISTRY)


if __name__ == "__main__":
    unittest.main()
