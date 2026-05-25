"""
routes_memory.py — Phase 4.3 agent memory layer.

Per-agent persistent memory with optional vector embeddings.
Cosine similarity is computed in Python at query time — brute force
within the 10 MB per-agent quota (configurable via
AGENT_MEMORY_QUOTA_BYTES env var).

Embeddings store as JSON-stringified float arrays (TEXT in SQLite,
LONGTEXT in MySQL). When MySQL gets a proper VECTOR index (or we add
pgvector), the read path becomes WHERE agent_id=? ORDER BY embedding
<=> ?::vector LIMIT k — until then it's a Python scan.

Endpoints:
  POST   /api/agents/me/memory             store a memory
  GET    /api/agents/me/memory             list (newest first, expiry-filtered)
  GET    /api/agents/me/memory/search      cosine-similarity ranking
  GET    /api/agents/me/memory/quota       current usage vs cap
  DELETE /api/agents/me/memory/{id}        remove one
"""
from __future__ import annotations

import json
import math
import os
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Query, Request
from pydantic import BaseModel, Field

import database
from routes_shared import RouteContext, utc_now_iso_z


DEFAULT_QUOTA_BYTES = 10 * 1024 * 1024  # 10 MB per agent


def _quota_bytes() -> int:
    """Read-at-call-time so tests can override via env without reloading."""
    raw = os.environ.get("AGENT_MEMORY_QUOTA_BYTES")
    if raw:
        try:
            return max(1, int(raw))
        except ValueError:
            pass
    return DEFAULT_QUOTA_BYTES


# ── Pydantic ──────────────────────────────────────────────────────────────

class CreateMemoryRequest(BaseModel):
    content:    str = Field(min_length=1)
    embedding:  Optional[list[float]] = None
    metadata:   Optional[dict[str, Any]] = None
    expires_at: Optional[str] = None


# ── helpers ───────────────────────────────────────────────────────────────

def _require_agent(req: Request) -> dict:
    from services import _get_agent_by_token
    auth = req.headers.get("authorization", "")
    token = auth.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Authorization required")
    agent = _get_agent_by_token(token)
    if not agent:
        raise HTTPException(status_code=401, detail="Invalid token")
    return agent


def _agent_used_bytes(agent_id: int) -> int:
    conn = database.get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT COALESCE(SUM(size_bytes), 0) AS used FROM agent_memory WHERE agent_id=?",
        (agent_id,),
    )
    row = cur.fetchone()
    conn.close()
    return int(row["used"] if row else 0)


def _agent_memory_count(agent_id: int) -> int:
    conn = database.get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) AS c FROM agent_memory WHERE agent_id=?",
        (agent_id,),
    )
    row = cur.fetchone()
    conn.close()
    return int(row["c"] if row else 0)


def _is_live(row: dict, now_iso: str) -> bool:
    exp = row.get("expires_at")
    if not exp:
        return True
    return str(exp) > now_iso


def _row_to_response(row: dict) -> dict:
    embedding = row.get("embedding")
    if embedding and isinstance(embedding, str):
        try:
            embedding = json.loads(embedding)
        except Exception:
            embedding = None
    metadata = row.get("metadata")
    if metadata and isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except Exception:
            metadata = None
    return {
        "memory_id":  row["id"],
        "content":    row["content"],
        "embedding":  embedding,
        "metadata":   metadata,
        "created_at": row["created_at"],
        "expires_at": row.get("expires_at"),
        "size_bytes": row.get("size_bytes") or 0,
    }


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return -1.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return -1.0
    return dot / (norm_a * norm_b)


# ── Routes ────────────────────────────────────────────────────────────────

def register_memory_routes(app: FastAPI, ctx: RouteContext) -> None:

    @app.post("/api/agents/me/memory", status_code=201)
    def post_memory(req: Request, body: CreateMemoryRequest):
        agent = _require_agent(req)

        embedding_text = json.dumps(body.embedding) if body.embedding is not None else None
        metadata_text  = json.dumps(body.metadata)  if body.metadata is not None else None
        now = utc_now_iso_z()

        # Approximate byte cost. Conservative: sum the string lengths of
        # the JSON-encoded fields, so a 10 MB cap reflects actual storage
        # not item count.
        size_bytes = (
            len(body.content.encode("utf-8"))
            + (len(embedding_text.encode("utf-8")) if embedding_text else 0)
            + (len(metadata_text.encode("utf-8")) if metadata_text else 0)
        )

        used = _agent_used_bytes(agent["id"])
        quota = _quota_bytes()
        if used + size_bytes > quota:
            raise HTTPException(
                status_code=413,
                detail=(
                    f"Memory quota exceeded: would use {used + size_bytes} "
                    f"of {quota} bytes (current {used})."
                ),
            )

        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO agent_memory
               (agent_id, content, embedding, metadata, created_at, expires_at, size_bytes)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (agent["id"], body.content, embedding_text, metadata_text,
             now, body.expires_at, size_bytes),
        )
        memory_id = cur.lastrowid
        conn.commit()
        conn.close()

        return {
            "memory_id":   memory_id,
            "size_bytes":  size_bytes,
            "created_at":  now,
        }

    @app.get("/api/agents/me/memory")
    def list_memories(req: Request, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
        agent = _require_agent(req)
        now = utc_now_iso_z()

        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """SELECT * FROM agent_memory
               WHERE agent_id=?
                 AND (expires_at IS NULL OR expires_at > ?)
               ORDER BY created_at DESC
               LIMIT ? OFFSET ?""",
            (agent["id"], now, limit, offset),
        )
        rows = [_row_to_response(dict(r)) for r in cur.fetchall()]
        conn.close()
        return {"memories": rows}

    @app.get("/api/agents/me/memory/search")
    def search_memories(
        req: Request,
        embedding: str = Query(..., description="JSON-encoded float array"),
        k: int = Query(10, ge=1, le=100),
    ):
        agent = _require_agent(req)

        try:
            query_vec = json.loads(embedding)
            if not isinstance(query_vec, list) or not all(isinstance(x, (int, float)) for x in query_vec):
                raise ValueError("embedding must be a JSON array of numbers")
        except (ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=422, detail=f"Bad embedding: {exc}")
        query_vec = [float(x) for x in query_vec]

        now = utc_now_iso_z()
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """SELECT * FROM agent_memory
               WHERE agent_id=?
                 AND embedding IS NOT NULL
                 AND (expires_at IS NULL OR expires_at > ?)""",
            (agent["id"], now),
        )
        candidates = [dict(r) for r in cur.fetchall()]
        conn.close()

        scored: list[tuple[float, dict]] = []
        for r in candidates:
            try:
                vec = json.loads(r["embedding"])
                if isinstance(vec, list):
                    score = _cosine_similarity(query_vec, [float(x) for x in vec])
                    scored.append((score, r))
            except Exception:
                continue
        scored.sort(key=lambda t: t[0], reverse=True)
        top = scored[:k]

        return {
            "results": [
                {**_row_to_response(r), "score": score}
                for score, r in top
            ],
        }

    @app.get("/api/agents/me/memory/quota")
    def get_quota(req: Request):
        agent = _require_agent(req)
        return {
            "used_bytes": _agent_used_bytes(agent["id"]),
            "max_bytes":  _quota_bytes(),
            "count":      _agent_memory_count(agent["id"]),
        }

    @app.delete("/api/agents/me/memory/{memory_id}", status_code=204)
    def delete_memory(memory_id: int, req: Request):
        agent = _require_agent(req)
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM agent_memory WHERE id=? AND agent_id=?",
            (memory_id, agent["id"]),
        )
        if cur.rowcount == 0:
            conn.close()
            raise HTTPException(status_code=404, detail="Memory not found")
        conn.commit()
        conn.close()
