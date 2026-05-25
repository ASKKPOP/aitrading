"""Unit + integration tests for Phase 4.4 materialized leaderboard.

Covers:
  - refresh_leaderboard_snapshot() writes one row per (metric, rank)
    for every agent and orders correctly within each metric.
  - read_leaderboard_snapshot() returns None when empty, [] past EOF,
    a sorted page when populated.
  - The /api/profit/history endpoint reads from the snapshot fast-path
    when available and falls back to live computation when empty.
"""
from __future__ import annotations

import hashlib
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
from leaderboard_snapshot import (
    METRICS,
    read_leaderboard_snapshot,
    refresh_leaderboard_snapshot,
    snapshot_freshness_seconds,
)
from routes import create_app


# ── fixtures ──────────────────────────────────────────────────────────────

def _mk_agent(name: str, *, cash: float = 100_000.0, deposited: float = 0.0) -> int:
    """Insert an agent and return its id. Uses a stable hashed dummy token."""
    token_raw = f"tok-{name}"
    token_hash = hashlib.sha256(token_raw.encode()).hexdigest()
    conn = database.get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO agents (name, token, token_hash, cash, deposited) "
        "VALUES (?, NULL, ?, ?, ?)",
        (name, token_hash, cash, deposited),
    )
    aid = cur.lastrowid
    conn.commit()
    conn.close()
    return aid


def _mk_metric_snapshot(
    agent_id: int,
    *,
    quality: float = 0.0,
    drawdown: float = 0.0,
    replies: int = 0,
    accepted: int = 0,
    citations: int = 0,
    adoptions: int = 0,
) -> None:
    """Insert one agent_metric_snapshot row so the join in the leaderboard
    aggregate has something to attach to."""
    conn = database.get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO agent_metric_snapshots
          (agent_id, window_key, window_start_at, window_end_at,
           quality_score_avg, max_drawdown,
           reply_count, accepted_reply_count, citation_count, adoption_count)
        VALUES (?, '7d', '2026-05-18T00:00:00Z', '2026-05-25T00:00:00Z',
                ?, ?, ?, ?, ?, ?)
        """,
        (agent_id, quality, drawdown, replies, accepted, citations, adoptions),
    )
    conn.commit()
    conn.close()


class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()

    def tearDown(self):
        self.tmp.cleanup()


# ── refresh ────────────────────────────────────────────────────────────────

class RefreshTests(_Base):
    def test_refresh_on_empty_db_writes_nothing(self):
        result = refresh_leaderboard_snapshot()
        # No agents → no rows for any metric.
        for m in METRICS:
            self.assertEqual(result["rows"][m], 0)
        self.assertEqual(result["total_agents"], 0)

    def test_refresh_writes_one_row_per_metric_per_agent(self):
        a = _mk_agent("a", cash=110_000.0)            # +10% return
        b = _mk_agent("b", cash=90_000.0)             # -10% return
        c = _mk_agent("c", cash=120_000.0)            # +20% return
        _mk_metric_snapshot(a, quality=0.8, replies=10)
        _mk_metric_snapshot(b, quality=0.5, replies=2)
        _mk_metric_snapshot(c, quality=0.9, replies=5)

        result = refresh_leaderboard_snapshot()
        self.assertEqual(result["total_agents"], 3)
        for m in METRICS:
            self.assertEqual(result["rows"][m], 3)

    def test_return_metric_orders_by_profit_percent_desc(self):
        a = _mk_agent("alpha", cash=110_000.0)
        b = _mk_agent("beta",  cash=90_000.0)
        c = _mk_agent("gamma", cash=120_000.0)
        for x in (a, b, c):
            _mk_metric_snapshot(x)

        refresh_leaderboard_snapshot()
        rows = read_leaderboard_snapshot("return", limit=10)
        self.assertIsNotNone(rows)
        names = [r["name"] for r in rows]
        self.assertEqual(names, ["gamma", "alpha", "beta"])
        ranks = [r["rank"] for r in rows]
        self.assertEqual(ranks, [1, 2, 3])

    def test_quality_metric_orders_by_quality_score(self):
        a = _mk_agent("a")
        b = _mk_agent("b")
        c = _mk_agent("c")
        _mk_metric_snapshot(a, quality=0.4)
        _mk_metric_snapshot(b, quality=0.9)
        _mk_metric_snapshot(c, quality=0.6)

        refresh_leaderboard_snapshot()
        rows = read_leaderboard_snapshot("quality", limit=10)
        assert rows is not None
        self.assertEqual([r["name"] for r in rows], ["b", "c", "a"])

    def test_refresh_is_idempotent(self):
        _mk_agent("only")
        _mk_metric_snapshot(_mk_agent("two"))

        first = refresh_leaderboard_snapshot()
        second = refresh_leaderboard_snapshot()
        # Same row counts both times — DELETE-then-INSERT keeps the
        # snapshot consistent rather than growing unboundedly.
        self.assertEqual(first["rows"], second["rows"])
        rows = read_leaderboard_snapshot("return", limit=10)
        assert rows is not None
        self.assertEqual(len(rows), 2)


# ── read ───────────────────────────────────────────────────────────────────

class ReadTests(_Base):
    def test_read_when_empty_returns_none(self):
        # No refresh has run yet — caller should fall back to live aggregate.
        self.assertIsNone(read_leaderboard_snapshot("return", limit=10))

    def test_read_when_past_eof_returns_empty_list(self):
        _mk_metric_snapshot(_mk_agent("x"))
        refresh_leaderboard_snapshot()
        # 1 row populated but page starts at offset=50 — should return [],
        # not None (signals "no fallback needed, page just empty").
        rows = read_leaderboard_snapshot("return", limit=10, offset=50)
        self.assertEqual(rows, [])

    def test_pagination_returns_correct_slice(self):
        for i in range(5):
            _mk_agent(f"a{i}", cash=100_000.0 + i * 1000.0)
        refresh_leaderboard_snapshot()
        page = read_leaderboard_snapshot("return", limit=2, offset=1)
        assert page is not None
        self.assertEqual(len(page), 2)
        # Ranks must be 2 and 3 (offset=1 skipped rank=1).
        self.assertEqual([r["rank"] for r in page], [2, 3])

    def test_freshness_returns_age_in_seconds(self):
        _mk_agent("x")
        refresh_leaderboard_snapshot()
        age = snapshot_freshness_seconds()
        self.assertIsNotNone(age)
        assert age is not None
        self.assertLess(age, 10.0)


# ── endpoint integration ──────────────────────────────────────────────────

class EndpointTests(_Base):
    def setUp(self):
        super().setUp()
        self.client = TestClient(create_app())

    def test_endpoint_uses_snapshot_when_available(self):
        a = _mk_agent("alpha", cash=110_000.0)
        b = _mk_agent("beta",  cash=120_000.0)
        _mk_metric_snapshot(a)
        _mk_metric_snapshot(b)

        # Populate the snapshot.
        refresh_leaderboard_snapshot()

        r = self.client.get("/api/profit/history?limit=5&days=30&include_history=false")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIn("top_agents", body)
        # Snapshot path preserves the response shape: beta (+20%) ranks above alpha (+10%).
        names = [a["name"] for a in body["top_agents"]]
        self.assertEqual(names, ["beta", "alpha"])

    def test_endpoint_falls_back_to_live_when_snapshot_empty(self):
        # No refresh — snapshot table is empty, endpoint must fall through.
        a = _mk_agent("only", cash=110_000.0)
        _mk_metric_snapshot(a)

        r = self.client.get("/api/profit/history?limit=5&days=30&include_history=false")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        # Live aggregate still finds and returns the agent.
        names = [a["name"] for a in body["top_agents"]]
        self.assertEqual(names, ["only"])

    def test_endpoint_metric_param_switches_ordering(self):
        a = _mk_agent("a", cash=110_000.0)
        b = _mk_agent("b", cash=100_000.0)
        _mk_metric_snapshot(a, quality=0.2)
        _mk_metric_snapshot(b, quality=0.9)

        refresh_leaderboard_snapshot()

        # metric=return → 'a' first (it's +10%)
        r1 = self.client.get("/api/profit/history?limit=5&metric=return&include_history=false")
        names_return = [x["name"] for x in r1.json()["top_agents"]]

        # metric=quality → 'b' first (0.9 > 0.2)
        r2 = self.client.get("/api/profit/history?limit=5&metric=quality&include_history=false")
        names_quality = [x["name"] for x in r2.json()["top_agents"]]

        self.assertEqual(names_return[0], "a")
        self.assertEqual(names_quality[0], "b")


if __name__ == "__main__":
    unittest.main()
