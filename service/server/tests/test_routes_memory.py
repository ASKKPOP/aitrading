"""TDD test suite for Phase 4.3 — /api/agents/me/memory endpoints.

Covers:
  - POST stores memory entries (with + without embedding)
  - POST without auth → 401
  - POST exceeding 10 MB quota → 413
  - GET list returns recent first, filters out expired
  - GET search ranks by cosine similarity, k limits results
  - GET search rejects bad embedding shape
  - GET quota returns used/max/count
  - DELETE removes only your own; other agents' rows → 404
"""
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


def _mk_agent(name: str, token_raw: str) -> tuple[int, str]:
    token_hash = hashlib.sha256(token_raw.encode()).hexdigest()
    conn = database.get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO agents (name, token, token_hash, cash) VALUES (?, NULL, ?, 100000.0)",
        (name, token_hash),
    )
    aid = cur.lastrowid
    conn.commit()
    conn.close()
    return aid, token_raw


class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())
        self.agent_id, self.token = _mk_agent("mem-agent", "tok-mem")
        self.auth = {"Authorization": f"Bearer {self.token}"}

    def tearDown(self):
        self.tmp.cleanup()


# ── POST ──────────────────────────────────────────────────────────────────

class PostMemoryTests(_Base):
    def test_post_returns_201_with_memory_id(self):
        r = self.client.post(
            "/api/agents/me/memory",
            json={"content": "remembered fact"},
            headers=self.auth,
        )
        self.assertEqual(r.status_code, 201)
        body = r.json()
        self.assertIn("memory_id", body)
        self.assertIsInstance(body["memory_id"], int)

    def test_post_without_auth_returns_401(self):
        r = self.client.post(
            "/api/agents/me/memory",
            json={"content": "ghost"},
        )
        self.assertEqual(r.status_code, 401)

    def test_post_with_embedding_and_metadata(self):
        r = self.client.post(
            "/api/agents/me/memory",
            json={
                "content": "BTC long thesis",
                "embedding": [0.1, 0.2, 0.3],
                "metadata": {"symbol": "BTC", "confidence": 0.7},
            },
            headers=self.auth,
        )
        self.assertEqual(r.status_code, 201)

    def test_post_requires_content(self):
        r = self.client.post(
            "/api/agents/me/memory",
            json={"metadata": {"tag": "no-content"}},
            headers=self.auth,
        )
        self.assertEqual(r.status_code, 422)

    def test_post_exceeding_quota_returns_413(self):
        # Default quota is 10 MB. We'll lower it via an env var so the test
        # is fast and deterministic.
        os.environ["AGENT_MEMORY_QUOTA_BYTES"] = "256"
        try:
            self.client.post(
                "/api/agents/me/memory",
                json={"content": "x" * 200},
                headers=self.auth,
            )
            # Second entry should push past the 256-byte cap.
            r = self.client.post(
                "/api/agents/me/memory",
                json={"content": "y" * 200},
                headers=self.auth,
            )
            self.assertEqual(r.status_code, 413)
        finally:
            os.environ.pop("AGENT_MEMORY_QUOTA_BYTES", None)


# ── LIST ──────────────────────────────────────────────────────────────────

class ListMemoryTests(_Base):
    def test_list_returns_empty_for_new_agent(self):
        r = self.client.get("/api/agents/me/memory", headers=self.auth)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["memories"], [])

    def test_list_returns_all_stored(self):
        for i in range(3):
            self.client.post(
                "/api/agents/me/memory",
                json={"content": f"fact {i}"},
                headers=self.auth,
            )
        r = self.client.get("/api/agents/me/memory", headers=self.auth)
        self.assertEqual(len(r.json()["memories"]), 3)

    def test_list_returns_newest_first(self):
        self.client.post(
            "/api/agents/me/memory",
            json={"content": "first"},
            headers=self.auth,
        )
        self.client.post(
            "/api/agents/me/memory",
            json={"content": "second"},
            headers=self.auth,
        )
        rows = self.client.get(
            "/api/agents/me/memory", headers=self.auth
        ).json()["memories"]
        self.assertEqual(rows[0]["content"], "second")
        self.assertEqual(rows[1]["content"], "first")

    def test_list_filters_out_expired(self):
        # Past-date expiry — should be excluded from the list.
        self.client.post(
            "/api/agents/me/memory",
            json={
                "content": "expired entry",
                "expires_at": "2000-01-01T00:00:00Z",
            },
            headers=self.auth,
        )
        self.client.post(
            "/api/agents/me/memory",
            json={"content": "live entry"},
            headers=self.auth,
        )
        rows = self.client.get(
            "/api/agents/me/memory", headers=self.auth
        ).json()["memories"]
        contents = {r["content"] for r in rows}
        self.assertEqual(contents, {"live entry"})

    def test_list_requires_auth(self):
        r = self.client.get("/api/agents/me/memory")
        self.assertEqual(r.status_code, 401)


# ── SEARCH (cosine similarity) ────────────────────────────────────────────

class SearchMemoryTests(_Base):
    def test_search_ranks_by_cosine_similarity(self):
        # Store three memories with hand-tuned 3-d vectors. The query
        # vector points along [1,0,0]; the entry with the same direction
        # should rank first.
        for content, vec in [
            ("orthogonal",  [0.0, 1.0, 0.0]),
            ("aligned",     [0.95, 0.05, 0.0]),
            ("anti",        [-1.0, 0.0, 0.0]),
        ]:
            self.client.post(
                "/api/agents/me/memory",
                json={"content": content, "embedding": vec},
                headers=self.auth,
            )

        r = self.client.get(
            "/api/agents/me/memory/search",
            params={"embedding": json.dumps([1.0, 0.0, 0.0]), "k": 3},
            headers=self.auth,
        )
        self.assertEqual(r.status_code, 200)
        results = r.json()["results"]
        self.assertEqual(len(results), 3)
        # 'aligned' should rank first; 'anti' last.
        self.assertEqual(results[0]["content"], "aligned")
        self.assertEqual(results[-1]["content"], "anti")
        # similarity score must be present and bounded in [-1, 1].
        for item in results:
            self.assertIn("score", item)
            self.assertGreaterEqual(item["score"], -1.0001)
            self.assertLessEqual(item["score"], 1.0001)

    def test_search_k_limits_results(self):
        for i in range(5):
            self.client.post(
                "/api/agents/me/memory",
                json={"content": f"item {i}", "embedding": [float(i), 0.0, 0.0]},
                headers=self.auth,
            )
        r = self.client.get(
            "/api/agents/me/memory/search",
            params={"embedding": json.dumps([1.0, 0.0, 0.0]), "k": 2},
            headers=self.auth,
        )
        self.assertEqual(len(r.json()["results"]), 2)

    def test_search_ignores_memories_without_embedding(self):
        # Memory without an embedding shouldn't appear in similarity search.
        self.client.post(
            "/api/agents/me/memory",
            json={"content": "no embedding"},
            headers=self.auth,
        )
        self.client.post(
            "/api/agents/me/memory",
            json={"content": "with embedding", "embedding": [1.0, 0.0, 0.0]},
            headers=self.auth,
        )
        r = self.client.get(
            "/api/agents/me/memory/search",
            params={"embedding": json.dumps([1.0, 0.0, 0.0]), "k": 5},
            headers=self.auth,
        )
        contents = [x["content"] for x in r.json()["results"]]
        self.assertEqual(contents, ["with embedding"])

    def test_search_rejects_malformed_embedding(self):
        r = self.client.get(
            "/api/agents/me/memory/search",
            params={"embedding": "not-json", "k": 5},
            headers=self.auth,
        )
        self.assertEqual(r.status_code, 422)

    def test_search_excludes_expired(self):
        self.client.post(
            "/api/agents/me/memory",
            json={
                "content": "old",
                "embedding": [1.0, 0.0, 0.0],
                "expires_at": "2000-01-01T00:00:00Z",
            },
            headers=self.auth,
        )
        self.client.post(
            "/api/agents/me/memory",
            json={"content": "fresh", "embedding": [1.0, 0.0, 0.0]},
            headers=self.auth,
        )
        r = self.client.get(
            "/api/agents/me/memory/search",
            params={"embedding": json.dumps([1.0, 0.0, 0.0]), "k": 5},
            headers=self.auth,
        )
        contents = [x["content"] for x in r.json()["results"]]
        self.assertEqual(contents, ["fresh"])


# ── QUOTA ─────────────────────────────────────────────────────────────────

class QuotaTests(_Base):
    def test_quota_endpoint_reports_usage(self):
        self.client.post(
            "/api/agents/me/memory",
            json={"content": "hello"},
            headers=self.auth,
        )
        r = self.client.get("/api/agents/me/memory/quota", headers=self.auth)
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIn("used_bytes", body)
        self.assertIn("max_bytes", body)
        self.assertIn("count", body)
        self.assertEqual(body["count"], 1)
        self.assertGreater(body["used_bytes"], 0)

    def test_quota_default_is_ten_megabytes(self):
        r = self.client.get("/api/agents/me/memory/quota", headers=self.auth)
        self.assertEqual(r.json()["max_bytes"], 10 * 1024 * 1024)


# ── DELETE ────────────────────────────────────────────────────────────────

class DeleteTests(_Base):
    def test_delete_removes_memory(self):
        mid = self.client.post(
            "/api/agents/me/memory",
            json={"content": "deleteme"},
            headers=self.auth,
        ).json()["memory_id"]
        r = self.client.delete(f"/api/agents/me/memory/{mid}", headers=self.auth)
        self.assertEqual(r.status_code, 204)
        rows = self.client.get("/api/agents/me/memory", headers=self.auth).json()["memories"]
        self.assertEqual(rows, [])

    def test_delete_other_agents_memory_returns_404(self):
        other_id, _ = _mk_agent("other", "tok-other")
        # Insert directly so we know it belongs to the other agent.
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO agent_memory (agent_id, content, created_at, size_bytes) "
            "VALUES (?, ?, '2026-05-25T00:00:00Z', 10)",
            (other_id, "their memory"),
        )
        other_memory_id = cur.lastrowid
        conn.commit()
        conn.close()

        r = self.client.delete(
            f"/api/agents/me/memory/{other_memory_id}", headers=self.auth
        )
        self.assertEqual(r.status_code, 404)

    def test_delete_nonexistent_returns_404(self):
        r = self.client.delete("/api/agents/me/memory/99999", headers=self.auth)
        self.assertEqual(r.status_code, 404)


if __name__ == "__main__":
    unittest.main()
