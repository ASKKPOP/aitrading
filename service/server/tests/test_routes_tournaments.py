"""Integration tests for /api/tournaments — Phase 3.8 out-of-sample tournaments."""
from __future__ import annotations

import hashlib
import json
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


def _mk_agent(name: str, token_raw: str, cash: float = 100_000.0) -> tuple[int, str]:
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
    return aid, token_raw


def _mk_strategy(agent_id: int, name: str = "S", config: dict | None = None) -> int:
    conn = database.get_db_connection()
    cur = conn.cursor()
    cfg = json.dumps(config) if config is not None else None
    cur.execute(
        "INSERT INTO strategies (agent_id, name, config) VALUES (?, ?, ?)",
        (agent_id, name, cfg),
    )
    sid = cur.lastrowid
    conn.commit()
    conn.close()
    return sid


# Reusable tournament body with a deadline well in the past so we can
# also test "after deadline" rejection. Tests that need an open window
# pass `submission_deadline` explicitly.
_FAR_FUTURE = "2099-01-01T00:00:00Z"
_FAR_PAST = "2000-01-01T00:00:00Z"


def _t_body(**overrides) -> dict:
    base = {
        "name": "Q1 Out-of-Sample Challenge",
        "description": "Closed-book evaluation",
        "submission_deadline": _FAR_FUTURE,
        "evaluation_start":   "2099-02-01T00:00:00Z",
        "evaluation_end":     "2099-03-01T00:00:00Z",
        "symbol":             "AAPL",
        "initial_cash":       100_000.0,
    }
    base.update(overrides)
    return base


class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())
        self.agent_id, self.token = _mk_agent("agent-a", "tok-a")
        self.auth = {"Authorization": f"Bearer {self.token}"}

    def tearDown(self):
        self.tmp.cleanup()


# ── CREATE ────────────────────────────────────────────────────────────────────

class CreateTournamentTests(_Base):
    def test_create_returns_201(self):
        r = self.client.post("/api/tournaments", json=_t_body(), headers=self.auth)
        self.assertEqual(r.status_code, 201)

    def test_create_returns_tournament_id_and_open_status(self):
        r = self.client.post("/api/tournaments", json=_t_body(), headers=self.auth)
        body = r.json()
        self.assertIn("tournament_id", body)
        self.assertEqual(body["status"], "open")

    def test_create_without_auth_returns_401(self):
        r = self.client.post("/api/tournaments", json=_t_body())
        self.assertEqual(r.status_code, 401)

    def test_create_rejects_deadline_after_evaluation_start(self):
        # invariant: must commit before evaluation begins
        r = self.client.post(
            "/api/tournaments",
            json=_t_body(
                submission_deadline="2099-03-01T00:00:00Z",
                evaluation_start="2099-02-01T00:00:00Z",
            ),
            headers=self.auth,
        )
        self.assertEqual(r.status_code, 400)

    def test_create_rejects_evaluation_end_before_start(self):
        r = self.client.post(
            "/api/tournaments",
            json=_t_body(
                evaluation_start="2099-03-01T00:00:00Z",
                evaluation_end="2099-02-01T00:00:00Z",
            ),
            headers=self.auth,
        )
        self.assertEqual(r.status_code, 400)


# ── LIST / GET ────────────────────────────────────────────────────────────────

class ListAndGetTournamentTests(_Base):
    def test_list_returns_created_tournament(self):
        self.client.post("/api/tournaments", json=_t_body(name="A"), headers=self.auth)
        self.client.post("/api/tournaments", json=_t_body(name="B"), headers=self.auth)
        r = self.client.get("/api/tournaments")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()["tournaments"]), 2)

    def test_list_does_not_require_auth(self):
        self.client.post("/api/tournaments", json=_t_body(), headers=self.auth)
        r = self.client.get("/api/tournaments")
        self.assertEqual(r.status_code, 200)

    def test_get_unknown_returns_404(self):
        r = self.client.get("/api/tournaments/99999")
        self.assertEqual(r.status_code, 404)

    def test_get_returns_detail(self):
        cid = self.client.post("/api/tournaments", json=_t_body(), headers=self.auth).json()["tournament_id"]
        r = self.client.get(f"/api/tournaments/{cid}")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["tournament_id"], cid)
        self.assertEqual(body["symbol"], "AAPL")


# ── SUBMIT ENTRY ──────────────────────────────────────────────────────────────

class SubmitEntryTests(_Base):
    def setUp(self):
        super().setUp()
        self.tid = self.client.post(
            "/api/tournaments", json=_t_body(), headers=self.auth
        ).json()["tournament_id"]
        self.sid = _mk_strategy(self.agent_id, name="My Strategy",
                                config={"threshold": 0.1})

    def test_submit_before_deadline_returns_201(self):
        r = self.client.post(
            f"/api/tournaments/{self.tid}/entries",
            json={"strategy_id": self.sid},
            headers=self.auth,
        )
        self.assertEqual(r.status_code, 201)

    def test_submit_returns_entry_id_and_config_hash(self):
        r = self.client.post(
            f"/api/tournaments/{self.tid}/entries",
            json={"strategy_id": self.sid},
            headers=self.auth,
        )
        body = r.json()
        self.assertIn("entry_id", body)
        self.assertIn("config_hash", body)
        self.assertEqual(len(body["config_hash"]), 64)  # sha-256 hex

    def test_submit_after_deadline_returns_403(self):
        # create a closed tournament
        cid = self.client.post(
            "/api/tournaments",
            json=_t_body(
                submission_deadline=_FAR_PAST,
                evaluation_start="2001-01-01T00:00:00Z",
                evaluation_end="2001-02-01T00:00:00Z",
            ),
            headers=self.auth,
        ).json()["tournament_id"]
        r = self.client.post(
            f"/api/tournaments/{cid}/entries",
            json={"strategy_id": self.sid},
            headers=self.auth,
        )
        self.assertEqual(r.status_code, 403)

    def test_submit_duplicate_returns_409(self):
        self.client.post(
            f"/api/tournaments/{self.tid}/entries",
            json={"strategy_id": self.sid},
            headers=self.auth,
        )
        r = self.client.post(
            f"/api/tournaments/{self.tid}/entries",
            json={"strategy_id": self.sid},
            headers=self.auth,
        )
        self.assertEqual(r.status_code, 409)

    def test_submit_foreign_strategy_returns_404(self):
        # another agent's strategy
        other_id, _ = _mk_agent("agent-b", "tok-b")
        other_sid = _mk_strategy(other_id, name="Theirs")
        r = self.client.post(
            f"/api/tournaments/{self.tid}/entries",
            json={"strategy_id": other_sid},
            headers=self.auth,
        )
        self.assertEqual(r.status_code, 404)

    def test_submit_requires_auth(self):
        r = self.client.post(
            f"/api/tournaments/{self.tid}/entries",
            json={"strategy_id": self.sid},
        )
        self.assertEqual(r.status_code, 401)

    def test_submit_unknown_tournament_returns_404(self):
        r = self.client.post(
            "/api/tournaments/99999/entries",
            json={"strategy_id": self.sid},
            headers=self.auth,
        )
        self.assertEqual(r.status_code, 404)


# ── LIST ENTRIES ──────────────────────────────────────────────────────────────

class ListEntriesTests(_Base):
    def test_entries_listed_for_a_tournament(self):
        tid = self.client.post(
            "/api/tournaments", json=_t_body(), headers=self.auth
        ).json()["tournament_id"]
        sid_a = _mk_strategy(self.agent_id, name="A")
        sid_b = _mk_strategy(self.agent_id, name="B")
        self.client.post(f"/api/tournaments/{tid}/entries",
                         json={"strategy_id": sid_a}, headers=self.auth)
        self.client.post(f"/api/tournaments/{tid}/entries",
                         json={"strategy_id": sid_b}, headers=self.auth)
        r = self.client.get(f"/api/tournaments/{tid}/entries")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()["entries"]), 2)


# ── EVALUATE + LEADERBOARD ────────────────────────────────────────────────────

class EvaluateTests(_Base):
    def setUp(self):
        super().setUp()
        # closed-submission tournament (deadline in past) so evaluate is allowed
        self.tid = self.client.post(
            "/api/tournaments",
            json=_t_body(
                submission_deadline=_FAR_PAST,
                evaluation_start="2001-01-01T00:00:00Z",
                evaluation_end="2001-02-01T00:00:00Z",
            ),
            headers=self.auth,
        ).json()["tournament_id"]

    def _seed_entry(self, agent_id: int, strategy_id: int) -> int:
        """Bypass deadline by inserting directly."""
        from routes_shared import utc_now_iso_z
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO tournament_entries
               (tournament_id, agent_id, strategy_id, config_hash, config_snapshot, submitted_at)
               VALUES (?,?,?,?,?,?)""",
            (self.tid, agent_id, strategy_id, "x" * 64, "{}", utc_now_iso_z()),
        )
        eid = cur.lastrowid
        conn.commit()
        conn.close()
        return eid

    def test_evaluate_returns_200_and_closes_tournament(self):
        sid = _mk_strategy(self.agent_id, name="S1")
        self._seed_entry(self.agent_id, sid)
        r = self.client.post(f"/api/tournaments/{self.tid}/evaluate", headers=self.auth)
        self.assertEqual(r.status_code, 200)

        det = self.client.get(f"/api/tournaments/{self.tid}").json()
        self.assertEqual(det["status"], "closed")

    def test_evaluate_before_deadline_returns_409(self):
        # open tournament, can't evaluate yet
        open_tid = self.client.post(
            "/api/tournaments", json=_t_body(), headers=self.auth
        ).json()["tournament_id"]
        r = self.client.post(f"/api/tournaments/{open_tid}/evaluate", headers=self.auth)
        self.assertEqual(r.status_code, 409)

    def test_evaluate_ranks_entries(self):
        # Two entries, both stub. Ranking should fill the rank column for both.
        sid_a = _mk_strategy(self.agent_id, name="A")
        sid_b = _mk_strategy(self.agent_id, name="B")
        self._seed_entry(self.agent_id, sid_a)
        self._seed_entry(self.agent_id, sid_b)
        self.client.post(f"/api/tournaments/{self.tid}/evaluate", headers=self.auth)

        r = self.client.get(f"/api/tournaments/{self.tid}/leaderboard")
        self.assertEqual(r.status_code, 200)
        entries = r.json()["leaderboard"]
        self.assertEqual(len(entries), 2)
        self.assertEqual({e["rank"] for e in entries}, {1, 2})

    def test_evaluate_is_idempotent(self):
        sid = _mk_strategy(self.agent_id, name="S")
        self._seed_entry(self.agent_id, sid)
        r1 = self.client.post(f"/api/tournaments/{self.tid}/evaluate", headers=self.auth)
        self.assertEqual(r1.status_code, 200)
        # second call after closed
        r2 = self.client.post(f"/api/tournaments/{self.tid}/evaluate", headers=self.auth)
        self.assertEqual(r2.status_code, 409)


# ── CONFIG SNAPSHOT INTEGRITY ─────────────────────────────────────────────────

class SnapshotIntegrityTests(_Base):
    def test_mutating_strategy_after_submit_does_not_change_entry_snapshot(self):
        tid = self.client.post(
            "/api/tournaments", json=_t_body(), headers=self.auth
        ).json()["tournament_id"]
        sid = _mk_strategy(self.agent_id, name="Frozen", config={"v": 1})

        # submit captures snapshot of {"v": 1}
        self.client.post(
            f"/api/tournaments/{tid}/entries",
            json={"strategy_id": sid},
            headers=self.auth,
        )
        # mutate strategy.config afterward
        self.client.put(
            f"/api/strategies/{sid}",
            json={"config": {"v": 999}},
            headers=self.auth,
        )

        # entry snapshot should still encode {"v": 1}
        entries = self.client.get(f"/api/tournaments/{tid}/entries").json()["entries"]
        self.assertEqual(len(entries), 1)
        snap = entries[0]["config_snapshot"]
        if isinstance(snap, str):
            snap = json.loads(snap)
        self.assertEqual(snap, {"v": 1})


if __name__ == "__main__":
    unittest.main()
