"""TDD tests for Phase 4.4b: materialized signal feed snapshot.

Covers:
  - read_signal_feed_snapshot() returns None when table is empty.
  - refresh_signal_feed_snapshot() with agents+signals writes rows sorted
    by last_signal_at DESC per (message_type, market) combination.
  - Pagination (limit/offset) works correctly against the snapshot.
  - message_type isolation: operation and strategy rows don't mix.
  - market isolation: 'us-stock' and 'all' are separate snapshot keys.
  - read returns [] when page is past EOF (not None — snapshot exists).
  - total_for_filter matches the number of agents in that combo.
  - refreshed_at is set on all rows after a refresh.
  - Positions are serialised in positions_json per agent row.
  - Atomic swap: a second refresh replaces old rows cleanly.
  - /api/signals/grouped reads from the snapshot (fast-path).
  - /api/signals/grouped falls back to live query when snapshot is empty.
"""
from __future__ import annotations

import hashlib
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
from signal_feed_snapshot import (
    FILTER_COMBOS,
    read_signal_feed_snapshot,
    refresh_signal_feed_snapshot,
    snapshot_freshness_seconds,
)
from routes import create_app
from fastapi.testclient import TestClient


# ── helpers ───────────────────────────────────────────────────────────────────

def _mk_agent(name: str, *, cash: float = 100_000.0) -> int:
    token_raw = f"tok-{name}"
    token_hash = hashlib.sha256(token_raw.encode()).hexdigest()
    conn = database.get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO agents (name, token, token_hash, cash) VALUES (?, NULL, ?, ?)",
        (name, token_hash, cash),
    )
    aid = cur.lastrowid
    conn.commit()
    conn.close()
    return aid


_signal_id_seq = 0


def _mk_signal(
    agent_id: int,
    *,
    symbol: str = "AAPL",
    message_type: str = "operation",
    market: str = "us-stock",
    created_at: str = "2026-05-26T10:00:00",
) -> int:
    global _signal_id_seq
    _signal_id_seq += 1
    conn = database.get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO signals
            (signal_id, agent_id, symbol, market, message_type, content, side,
             entry_price, quantity, timestamp, executed_at, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (_signal_id_seq, agent_id, symbol, market, message_type, "Test signal",
         "long", 100.0, 10, _signal_id_seq, created_at, created_at),
    )
    sid = cur.lastrowid
    conn.commit()
    conn.close()
    return sid


def _mk_position(
    agent_id: int,
    *,
    symbol: str = "AAPL",
    market: str = "us-stock",
    side: str = "long",
    quantity: float = 10.0,
    entry_price: float = 100.0,
    current_price: float = 110.0,
) -> None:
    conn = database.get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO positions
            (agent_id, symbol, market, side, quantity, entry_price, current_price, opened_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """,
        (agent_id, symbol, market, side, quantity, entry_price, current_price),
    )
    conn.commit()
    conn.close()


# ── test class ────────────────────────────────────────────────────────────────

class TestSignalFeedSnapshot(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()

    def tearDown(self):
        self.tmp.cleanup()

    # 1. read returns None when snapshot is completely empty
    def test_read_returns_none_when_snapshot_empty(self):
        result = read_signal_feed_snapshot("operation", "", limit=20, offset=0)
        self.assertIsNone(result)

    # 2. refresh with no agents → snapshot exists but each combo has 0 agent rows
    def test_refresh_with_no_agents_writes_zero_rows(self):
        summary = refresh_signal_feed_snapshot()
        self.assertIsInstance(summary, dict)
        self.assertIn("refreshed_at", summary)
        # All combos should have 0 agents — snapshot populated but empty
        for (mt, mkt) in FILTER_COMBOS:
            result = read_signal_feed_snapshot(mt, mkt, limit=20, offset=0)
            self.assertIsNotNone(result)  # snapshot exists (not None)
            rows, total = result
            self.assertEqual(rows, [])
            self.assertEqual(total, 0)

    # 3. refresh with agents+signals → rows appear, sorted by last_signal_at DESC
    def test_refresh_writes_agents_sorted_by_last_signal(self):
        aid1 = _mk_agent("Alpha")
        aid2 = _mk_agent("Beta")
        _mk_signal(aid1, created_at="2026-05-26T08:00:00")
        _mk_signal(aid2, created_at="2026-05-26T09:00:00")  # newer

        refresh_signal_feed_snapshot()

        rows, total = read_signal_feed_snapshot("operation", "", limit=20, offset=0)
        self.assertEqual(total, 2)
        self.assertEqual(len(rows), 2)
        # Beta (newer signal) should rank first
        self.assertEqual(rows[0]["agent_name"], "Beta")
        self.assertEqual(rows[1]["agent_name"], "Alpha")

    # 4. pagination: limit/offset slice the sorted list
    def test_pagination_returns_correct_slice(self):
        for i in range(5):
            aid = _mk_agent(f"Agent{i:02d}")
            _mk_signal(aid, created_at=f"2026-05-26T0{i}:00:00")

        refresh_signal_feed_snapshot()

        page0, total = read_signal_feed_snapshot("operation", "", limit=2, offset=0)
        page1, _ = read_signal_feed_snapshot("operation", "", limit=2, offset=2)

        self.assertEqual(total, 5)
        self.assertEqual(len(page0), 2)
        self.assertEqual(len(page1), 2)
        # Pages don't overlap
        ids0 = {r["agent_id"] for r in page0}
        ids1 = {r["agent_id"] for r in page1}
        self.assertEqual(len(ids0 & ids1), 0)

    # 5. read returns [] (not None) when page is past EOF
    def test_read_returns_empty_list_past_eof(self):
        aid = _mk_agent("Solo")
        _mk_signal(aid)
        refresh_signal_feed_snapshot()

        result = read_signal_feed_snapshot("operation", "", limit=20, offset=100)
        self.assertIsNotNone(result)   # snapshot exists
        rows, total = result
        self.assertEqual(rows, [])
        self.assertEqual(total, 1)     # total is still accurate

    # 6. message_type isolation: operation agents don't appear in strategy combo
    def test_message_type_isolation(self):
        aid = _mk_agent("OpAgent")
        _mk_signal(aid, message_type="operation")
        refresh_signal_feed_snapshot()

        op_rows, op_total = read_signal_feed_snapshot("operation", "", limit=20, offset=0)
        strat_rows, strat_total = read_signal_feed_snapshot("strategy", "", limit=20, offset=0)

        self.assertEqual(op_total, 1)
        self.assertEqual(strat_total, 0)
        self.assertEqual(strat_rows, [])

    # 7. market isolation: us-stock signal doesn't appear in crypto combo
    def test_market_isolation(self):
        aid = _mk_agent("StockTrader")
        _mk_signal(aid, market="us-stock")
        refresh_signal_feed_snapshot()

        us_rows, us_total = read_signal_feed_snapshot("operation", "us-stock", limit=20, offset=0)
        crypto_rows, crypto_total = read_signal_feed_snapshot("operation", "crypto", limit=20, offset=0)

        self.assertEqual(us_total, 1)
        self.assertEqual(crypto_total, 0)

    # 8. all-market combo counts agent that has any signal regardless of market
    def test_all_market_combo_includes_any_market_signal(self):
        aid = _mk_agent("CryptoGuy")
        _mk_signal(aid, market="crypto")
        refresh_signal_feed_snapshot()

        all_rows, all_total = read_signal_feed_snapshot("operation", "", limit=20, offset=0)
        self.assertEqual(all_total, 1)

    # 9. positions_json is serialised in each agent row
    def test_positions_json_included_in_rows(self):
        aid = _mk_agent("Trader")
        _mk_signal(aid)
        _mk_position(aid, symbol="AAPL", entry_price=100.0, current_price=120.0)
        refresh_signal_feed_snapshot()

        rows, _ = read_signal_feed_snapshot("operation", "", limit=20, offset=0)
        self.assertEqual(len(rows), 1)
        positions = rows[0]["positions"]
        self.assertIsInstance(positions, list)
        self.assertEqual(len(positions), 1)
        self.assertEqual(positions[0]["symbol"], "AAPL")

    # 10. total_for_filter is correct per row
    def test_total_for_filter_matches_agent_count(self):
        for i in range(3):
            aid = _mk_agent(f"T{i}")
            _mk_signal(aid)
        refresh_signal_feed_snapshot()

        rows, total = read_signal_feed_snapshot("operation", "", limit=20, offset=0)
        self.assertEqual(total, 3)
        self.assertEqual(len(rows), 3)

    # 11. refreshed_at is set on all rows
    def test_refreshed_at_is_set(self):
        aid = _mk_agent("Fresh")
        _mk_signal(aid)
        refresh_signal_feed_snapshot()

        rows, _ = read_signal_feed_snapshot("operation", "", limit=20, offset=0)
        self.assertIsNotNone(rows[0].get("refreshed_at"))

    # 12. atomic swap: second refresh replaces rows cleanly (no duplicates)
    def test_second_refresh_replaces_rows(self):
        aid = _mk_agent("Stable")
        _mk_signal(aid)
        refresh_signal_feed_snapshot()
        refresh_signal_feed_snapshot()

        rows, total = read_signal_feed_snapshot("operation", "", limit=100, offset=0)
        self.assertEqual(total, 1)
        self.assertEqual(len(rows), 1)

    # 13. snapshot_freshness_seconds is None before first refresh
    def test_freshness_none_before_refresh(self):
        self.assertIsNone(snapshot_freshness_seconds())

    # 14. snapshot_freshness_seconds returns a non-negative float after refresh
    def test_freshness_float_after_refresh(self):
        refresh_signal_feed_snapshot()
        age = snapshot_freshness_seconds()
        self.assertIsNotNone(age)
        self.assertGreaterEqual(age, 0.0)

    # 15. /api/signals/grouped reads from snapshot fast-path
    def test_api_endpoint_reads_snapshot(self):
        aid = _mk_agent("SnapshotAgent")
        _mk_signal(aid)
        refresh_signal_feed_snapshot()

        client = TestClient(create_app())
        resp = client.get("/api/signals/grouped?message_type=operation")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("agents", data)
        self.assertIn("total", data)

    # 16. /api/signals/grouped falls back to live query when snapshot empty
    def test_api_endpoint_fallback_when_snapshot_empty(self):
        aid = _mk_agent("LiveAgent")
        _mk_signal(aid)
        # No refresh — snapshot is empty

        client = TestClient(create_app())
        resp = client.get("/api/signals/grouped?message_type=operation")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("agents", data)
        self.assertGreaterEqual(data["total"], 1)


if __name__ == "__main__":
    unittest.main()
