"""Tests for Phase 4.7 — reputation slashing logic and routes."""
from __future__ import annotations

import hashlib
import os
import sys
import tempfile
import unittest
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
from routes import create_app
from fastapi.testclient import TestClient


def _mk_agent(name: str, token_raw: str, reputation: int = 100) -> tuple[int, str]:
    token_hash = hashlib.sha256(token_raw.encode()).hexdigest()
    conn = database.get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO agents (name, token, token_hash, cash, reputation_score) VALUES (?, NULL, ?, 100000, ?)",
        (name, token_hash, reputation),
    )
    aid = cur.lastrowid
    conn.commit()
    conn.close()
    return aid, token_raw


def _mk_subscription(leader_id: int, follower_id: int) -> None:
    conn = database.get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO subscriptions (leader_id, follower_id, status) VALUES (?, ?, 'active')",
        (leader_id, follower_id),
    )
    conn.commit()
    conn.close()


def _mk_signal(agent_id: int, pnl: float | None = None) -> int:
    from routes_shared import utc_now_iso_z
    conn = database.get_db_connection()
    cur = conn.cursor()
    # Reserve a signal_id from the sequence table (same mechanism as services.py)
    cur.execute("INSERT INTO signal_sequence DEFAULT VALUES")
    signal_id = cur.lastrowid
    cur.execute(
        """INSERT INTO signals
           (signal_id, agent_id, message_type, market, symbol, side,
            entry_price, quantity, pnl, timestamp, created_at)
           VALUES (?, ?, 'trade', 'us-stock', 'AAPL', 'long',
                   100.0, 10.0, ?, ?, ?)""",
        (signal_id, agent_id, pnl, 1000000, utc_now_iso_z()),
    )
    conn.commit()
    conn.close()
    return signal_id


class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())
        self.leader_id, self.token = _mk_agent("leader", "tok-leader", reputation=100)
        self.auth = {"Authorization": f"Bearer {self.token}"}

    def tearDown(self):
        self.tmp.cleanup()


# ── Unit: compute_slash_points ────────────────────────────────────────────────

class ComputeSlashPointsTests(unittest.TestCase):
    def setUp(self):
        from reputation import compute_slash_points
        self.compute = compute_slash_points

    def test_no_slash_below_threshold(self):
        # 1.9% loss → below 2% threshold
        self.assertEqual(self.compute(loss_pct=1.9, follower_count=10), 0)

    def test_no_slash_exactly_at_threshold(self):
        # 2.0% is NOT strictly above 2% → no slash
        self.assertEqual(self.compute(loss_pct=2.0, follower_count=10), 0)

    def test_slash_triggered_above_threshold(self):
        # 2.01% loss with 5 followers → 5 points
        self.assertEqual(self.compute(loss_pct=2.01, follower_count=5), 5)

    def test_slash_proportional_to_follower_count(self):
        # 10 followers → 10 points, 3 followers → 3 points
        self.assertEqual(self.compute(loss_pct=5.0, follower_count=10), 10)
        self.assertEqual(self.compute(loss_pct=5.0, follower_count=3), 3)

    def test_slash_with_zero_followers(self):
        # No copiers hurt → no points deducted
        self.assertEqual(self.compute(loss_pct=5.0, follower_count=0), 0)

    def test_slash_with_large_loss_large_volume(self):
        # Larger loss doesn't multiply; only follower_count is proportional
        self.assertEqual(self.compute(loss_pct=50.0, follower_count=100), 100)


# ── Unit: count_active_followers ──────────────────────────────────────────────

class CountFollowersTests(_Base):
    def test_counts_active_followers_only(self):
        from reputation import count_active_followers
        f1_id, _ = _mk_agent("f1", "tok-f1")
        f2_id, _ = _mk_agent("f2", "tok-f2")
        _mk_subscription(self.leader_id, f1_id)
        _mk_subscription(self.leader_id, f2_id)
        # add one inactive subscription
        conn = database.get_db_connection()
        cur = conn.cursor()
        f3_id, _ = _mk_agent("f3", "tok-f3")
        cur.execute(
            "INSERT INTO subscriptions (leader_id, follower_id, status) VALUES (?, ?, 'cancelled')",
            (self.leader_id, f3_id),
        )
        conn.commit()
        conn.close()

        self.assertEqual(count_active_followers(self.leader_id), 2)

    def test_no_followers_returns_zero(self):
        from reputation import count_active_followers
        self.assertEqual(count_active_followers(self.leader_id), 0)


# ── Unit: apply_reputation_slash ─────────────────────────────────────────────

class ApplyReputationSlashTests(_Base):
    def test_slash_decrements_reputation_score(self):
        from reputation import apply_reputation_slash
        f1_id, _ = _mk_agent("f1", "tok-f1")
        _mk_subscription(self.leader_id, f1_id)
        signal_id = _mk_signal(self.leader_id, pnl=-50.0)

        apply_reputation_slash(
            leader_id=self.leader_id, signal_id=signal_id,
            loss_pct=3.0, follower_count=1,
        )

        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT reputation_score FROM agents WHERE id=?", (self.leader_id,))
        score = cur.fetchone()["reputation_score"]
        conn.close()
        self.assertEqual(score, 99)  # started at 100, deducted 1

    def test_slash_creates_audit_row(self):
        from reputation import apply_reputation_slash
        signal_id = _mk_signal(self.leader_id, pnl=-50.0)

        apply_reputation_slash(
            leader_id=self.leader_id, signal_id=signal_id,
            loss_pct=3.0, follower_count=5,
        )

        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM reputation_slashes WHERE leader_id=?", (self.leader_id,))
        row = cur.fetchone()
        conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(row["signal_id"], signal_id)
        self.assertAlmostEqual(row["loss_pct"], 3.0)
        self.assertEqual(row["follower_count"], 5)
        self.assertEqual(row["points_deducted"], 5)

    def test_slash_returns_points_deducted(self):
        from reputation import apply_reputation_slash
        signal_id = _mk_signal(self.leader_id)

        points = apply_reputation_slash(
            leader_id=self.leader_id, signal_id=signal_id,
            loss_pct=4.0, follower_count=7,
        )
        self.assertEqual(points, 7)

    def test_slash_with_zero_followers_does_not_change_score(self):
        from reputation import apply_reputation_slash
        signal_id = _mk_signal(self.leader_id)

        apply_reputation_slash(
            leader_id=self.leader_id, signal_id=signal_id,
            loss_pct=5.0, follower_count=0,
        )

        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT reputation_score FROM agents WHERE id=?", (self.leader_id,))
        score = cur.fetchone()["reputation_score"]
        conn.close()
        self.assertEqual(score, 100)  # unchanged

    def test_reputation_score_can_go_negative(self):
        # Slash a leader with only 2 reputation points by 5 followers
        from reputation import apply_reputation_slash
        low_id, _ = _mk_agent("low-rep", "tok-low", reputation=2)
        signal_id = _mk_signal(low_id)

        apply_reputation_slash(
            leader_id=low_id, signal_id=signal_id,
            loss_pct=5.0, follower_count=5,
        )

        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT reputation_score FROM agents WHERE id=?", (low_id,))
        score = cur.fetchone()["reputation_score"]
        conn.close()
        self.assertEqual(score, -3)


# ── API: GET /api/agents/{id}/reputation ─────────────────────────────────────

class GetReputationTests(_Base):
    def test_returns_reputation_score(self):
        r = self.client.get(f"/api/agents/{self.leader_id}/reputation")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["reputation_score"], 100)
        self.assertEqual(body["agent_id"], self.leader_id)

    def test_returns_empty_slash_history_initially(self):
        r = self.client.get(f"/api/agents/{self.leader_id}/reputation")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["slashes"], [])

    def test_slash_history_populated_after_slash(self):
        from reputation import apply_reputation_slash
        signal_id = _mk_signal(self.leader_id)
        apply_reputation_slash(
            leader_id=self.leader_id, signal_id=signal_id,
            loss_pct=3.5, follower_count=4,
        )

        r = self.client.get(f"/api/agents/{self.leader_id}/reputation")
        self.assertEqual(r.status_code, 200)
        slashes = r.json()["slashes"]
        self.assertEqual(len(slashes), 1)
        self.assertEqual(slashes[0]["points_deducted"], 4)
        self.assertAlmostEqual(slashes[0]["loss_pct"], 3.5)

    def test_returns_404_for_unknown_agent(self):
        r = self.client.get("/api/agents/99999/reputation")
        self.assertEqual(r.status_code, 404)


# ── API: POST /api/signals/{id}/slash ────────────────────────────────────────

class SlashSignalEndpointTests(_Base):
    def test_slash_below_threshold_returns_no_action(self):
        """Signal with <2% loss: 200, points_deducted=0."""
        f1_id, _ = _mk_agent("f1", "tok-f1")
        _mk_subscription(self.leader_id, f1_id)
        # entry_price=100, close_price=99 → 1% loss
        signal_id = _mk_signal(self.leader_id, pnl=None)

        r = self.client.post(
            f"/api/signals/{signal_id}/slash",
            json={"entry_price": 100.0, "close_price": 99.0},
            headers=self.auth,
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["points_deducted"], 0)
        self.assertFalse(r.json()["slashed"])

    def test_slash_above_threshold_deducts_points(self):
        """Signal with >2% loss and followers: deducts points."""
        f1_id, _ = _mk_agent("f1", "tok-f1")
        f2_id, _ = _mk_agent("f2", "tok-f2")
        _mk_subscription(self.leader_id, f1_id)
        _mk_subscription(self.leader_id, f2_id)
        # entry_price=100, close_price=95 → 5% loss
        signal_id = _mk_signal(self.leader_id, pnl=None)

        r = self.client.post(
            f"/api/signals/{signal_id}/slash",
            json={"entry_price": 100.0, "close_price": 95.0},
            headers=self.auth,
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body["slashed"])
        self.assertEqual(body["points_deducted"], 2)  # 2 followers
        self.assertAlmostEqual(body["loss_pct"], 5.0)

    def test_slash_requires_auth(self):
        signal_id = _mk_signal(self.leader_id)
        r = self.client.post(
            f"/api/signals/{signal_id}/slash",
            json={"entry_price": 100.0, "close_price": 95.0},
        )
        self.assertEqual(r.status_code, 401)

    def test_slash_unknown_signal_returns_404(self):
        r = self.client.post(
            "/api/signals/99999/slash",
            json={"entry_price": 100.0, "close_price": 95.0},
            headers=self.auth,
        )
        self.assertEqual(r.status_code, 404)

    def test_slash_only_owner_can_evaluate(self):
        """Other agent cannot evaluate slashing on someone else's signal."""
        other_id, other_tok = _mk_agent("other", "tok-other")
        other_auth = {"Authorization": f"Bearer {other_tok}"}
        signal_id = _mk_signal(self.leader_id)

        r = self.client.post(
            f"/api/signals/{signal_id}/slash",
            json={"entry_price": 100.0, "close_price": 90.0},
            headers=other_auth,
        )
        self.assertEqual(r.status_code, 403)

    def test_slash_leader_reputation_decremented_via_api(self):
        """End-to-end: slash via API, then verify reputation endpoint."""
        f1_id, _ = _mk_agent("f1", "tok-f1")
        _mk_subscription(self.leader_id, f1_id)
        signal_id = _mk_signal(self.leader_id)

        self.client.post(
            f"/api/signals/{signal_id}/slash",
            json={"entry_price": 100.0, "close_price": 90.0},
            headers=self.auth,
        )

        r = self.client.get(f"/api/agents/{self.leader_id}/reputation")
        self.assertEqual(r.json()["reputation_score"], 99)  # 100 - 1 follower


if __name__ == "__main__":
    unittest.main()
