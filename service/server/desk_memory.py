"""The desk's durable corpus — what has been learned, and what it decided.

Owner, 2026-08-06: *"RAG keep all analysis and monitoring for this session and
sooppiy AI"*.

Two bodies of knowledge were being lost between sessions:

1. **Monitoring analysis.** The Claude account is rotated every ~3 days, so a
   finding survives only if it is written down. Repo markdown was the answer,
   but it was only partly true — the handoff, the snapshot and six days of
   cycle notes had never been committed to main at all.
2. **The desk's own reasoning.** `run_events` holds `decision` rows and, much
   later, the `trade` and close rows they produced. Nothing joins a decision to
   what it actually cost or earned, so the desk cannot be asked "when you last
   reasoned like this, what happened?".

This module stores both as retrievable chunks and scores them in Python. No
FTS5, no MySQL FULLTEXT, no embedding service: the corpus is small (hundreds to
low thousands of chunks), and a pure-Python scorer behaves identically on both
dialects — which the SQLite/MySQL split in this codebase has burned us on
before.

Storage only in this module, plus search. Wiring retrieval into the decision
prompt is Phase 2 of docs/plan/22-desk-retrieval-rag.md, and deliberately
comes after: while every skill is in every prompt there is no variance for an
attribution model to learn from.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import re
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from database import get_db_connection

logger = logging.getLogger(__name__)

KINDS = ("monitoring", "decision", "outcome", "lesson")

_TOKEN = re.compile(r"[a-z0-9_]+")
# Words that carry no retrieval signal in this corpus. Kept deliberately short:
# an aggressive stop-list would strip the domain terms ("loss", "stop",
# "close") that are exactly what a query is usually about.
_STOP = frozenset((
    "the", "a", "an", "and", "or", "but", "if", "then", "than", "that", "this",
    "these", "those", "is", "are", "was", "were", "be", "been", "being", "to",
    "of", "in", "on", "at", "by", "for", "with", "as", "it", "its", "not",
    "no", "so", "we", "you", "your", "our", "they", "them", "from", "have",
    "has", "had", "do", "does", "did", "can", "could", "would", "should",
))


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _tokens(text: str) -> list[str]:
    return [t for t in _TOKEN.findall((text or "").lower())
            if len(t) > 1 and t not in _STOP]


def _sha(kind: str, source: str, body: str) -> str:
    """Dedupe identity. Body is included, so re-ingesting an EDITED chunk
    stores a new memory rather than silently keeping the stale one — the
    monitoring notes are revised in place as findings are corrected."""
    return hashlib.sha256(
        f"{kind}\x00{source}\x00{body}".encode("utf-8")).hexdigest()


def known_shas() -> set[str]:
    """Every stored chunk's identity, in one query.

    Measured on prod: a full ingest that stored NOTHING still took 26-33s,
    because it issued one SELECT per chunk — 442 round-trips to answer "have I
    seen this?". That cost grows with the corpus, on the same database that
    serves trading. Callers ingesting in bulk should fetch this once and pass
    it to `remember`."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT sha FROM desk_memory")
        return {dict(r)["sha"] for r in cur.fetchall()}
    finally:
        conn.close()


def remember(kind: str, source: str, title: str, body: str, *,
             ts: Optional[str] = None, run_id: Optional[int] = None,
             symbol: Optional[str] = None, market: Optional[str] = None,
             tags: Optional[Iterable[str]] = None,
             known: Optional[set[str]] = None) -> Optional[int]:
    """Store one chunk. Idempotent: re-ingesting identical content is a no-op.

    `known` is an optional pre-loaded sha set (see `known_shas`) that replaces
    the per-chunk existence query; it is updated in place so a duplicate within
    the same batch is caught too. The unique index remains the real guarantee.

    Returns the row id, or None when the chunk was already present."""
    if kind not in KINDS:
        raise ValueError(f"unknown kind {kind!r}; expected one of {KINDS}")
    body = (body or "").strip()
    if not body:
        return None
    sha = _sha(kind, source, body)
    if known is not None and sha in known:
        return None
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        if known is None:
            cur.execute("SELECT id FROM desk_memory WHERE sha = ?", (sha,))
            if cur.fetchone():
                return None
        cur.execute(
            "INSERT INTO desk_memory (kind, source, ts, run_id, symbol, market,"
            " tags_json, title, body, sha, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (kind, source[:255], ts or _now(), run_id, symbol, market,
             json.dumps(sorted({str(t) for t in (tags or [])})),
             (title or source)[:255], body, sha, _now()))
        conn.commit()
        if known is not None:
            known.add(sha)
        cur.execute("SELECT id FROM desk_memory WHERE sha = ?", (sha,))
        got = cur.fetchone()
        return dict(got)["id"] if got else None
    finally:
        conn.close()


def _kind_list(kind: "str | Iterable[str] | None") -> list[str]:
    """Normalise the `kind` filter to a list. A bare string stays one kind."""
    if kind is None:
        return []
    if isinstance(kind, str):
        return [kind]
    return [str(k) for k in kind if k]


def _candidates(kind: "str | Iterable[str] | None", market: Optional[str],
                symbol: Optional[str], run_id: Optional[int],
                cap: int) -> list[dict[str, Any]]:
    """Cheap SQL narrowing before Python scoring. `market` and `symbol` match
    permissively — a chunk with no market recorded is general knowledge and
    stays a candidate for every market."""
    where, params = [], []
    kinds = _kind_list(kind)
    if kinds:
        where.append("kind IN (%s)" % ", ".join("?" for _ in kinds))
        params.extend(kinds)
    if market:
        where.append("(market IS NULL OR market = ?)")
        params.append(market)
    if symbol:
        where.append("(symbol IS NULL OR symbol = ?)")
        params.append(symbol)
    if run_id is not None:
        where.append("(run_id IS NULL OR run_id = ?)")
        params.append(run_id)
    sql = "SELECT * FROM desk_memory"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY ts DESC LIMIT ?"
    params.append(cap)
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(sql, tuple(params))
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def search(query: str, *, kind: "str | Iterable[str] | None" = None,
           market: Optional[str] = None, symbol: Optional[str] = None,
           run_id: Optional[int] = None, tags: Optional[Iterable[str]] = None,
           limit: int = 5, pool: int = 2000) -> list[dict[str, Any]]:
    """Rank stored chunks against a query.

    BM25-style saturation over the candidate pool: a term repeated ten times
    does not count ten times, and a term common to the whole corpus (every
    monitoring note says "run") counts for almost nothing. Tag overlap and an
    exact symbol match add a bounded boost — bounded on purpose, so a tag can
    surface a chunk but never outrank genuine textual relevance.

    `kind` takes one kind or several. Several is not a convenience: IDF and
    the length norm are computed over the candidate pool, so scores from two
    separate calls are not the same unit and must never be merged by the
    caller. Asking for the kinds together is the only way to get one ranking
    across them."""
    rows = _candidates(kind, market, symbol, run_id, pool)
    if not rows:
        return []
    want_tags = {str(t) for t in (tags or [])}
    q_terms = set(_tokens(query))

    docs = [Counter(_tokens(f'{r["title"]} {r["body"]}')) for r in rows]
    n = len(docs)
    df = Counter()
    for d in docs:
        df.update(d.keys())
    avg_len = sum(sum(d.values()) for d in docs) / n or 1.0

    scored = []
    for row, doc in zip(rows, docs):
        dl = sum(doc.values()) or 1
        score = 0.0
        for term in q_terms:
            tf = doc.get(term, 0)
            if not tf:
                continue
            idf = math.log(1 + (n - df[term] + 0.5) / (df[term] + 0.5))
            score += idf * (tf * 2.5) / (tf + 1.5 * (0.25 + 0.75 * dl / avg_len))
        if want_tags:
            try:
                have = set(json.loads(row.get("tags_json") or "[]"))
            except (ValueError, TypeError):
                have = set()
            if have & want_tags:
                score += 0.5 * len(have & want_tags)
        if symbol and row.get("symbol") == symbol:
            score += 0.5
        if score > 0:
            scored.append((score, row))
    scored.sort(key=lambda x: (-x[0], x[1]["ts"]), reverse=False)
    scored.sort(key=lambda x: -x[0])
    return [dict(r, score=round(s, 4)) for s, r in scored[:limit]]


def stats() -> dict[str, Any]:
    """Corpus size by kind — the cheapest way to see whether ingest ran."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT kind, COUNT(*) n FROM desk_memory GROUP BY kind")
        by_kind = {dict(r)["kind"]: dict(r)["n"] for r in cur.fetchall()}
        cur.execute("SELECT COUNT(*) n FROM desk_memory")
        total = dict(cur.fetchone())["n"]
        return {"total": total, "by_kind": by_kind}
    finally:
        conn.close()
