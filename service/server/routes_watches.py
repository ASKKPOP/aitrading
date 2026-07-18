"""Personal watch functions (Plan 06 C3).

    GET    /api/watches        list my watches (with current metric values)
    POST   /api/watches        create
    PUT    /api/watches/{id}   update (partial via full body)
    DELETE /api/watches/{id}   remove
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, field_validator

from database import begin_write_transaction, get_db_connection
from routes_shared import RouteContext
from services import _get_agent_by_token
from utils import _extract_token
import watch_engine
from watch_engine import COMPARATORS, METRICS, NEEDS_SYMBOL

MAX_WATCHES_PER_AGENT = 20


class WatchIn(BaseModel):
    name: str
    metric: str
    comparator: str
    threshold: float
    symbol: Optional[str] = None
    enabled: bool = True
    cooldown_min: int = 60

    @field_validator("name")
    @classmethod
    def _name(cls, v):
        v = (v or "").strip()
        if not v or len(v) > 60:
            raise ValueError("name must be 1-60 characters")
        return v

    @field_validator("metric")
    @classmethod
    def _metric(cls, v):
        v = (v or "").strip().lower()
        if v not in METRICS:
            raise ValueError(f"metric must be one of {list(METRICS)}")
        return v

    @field_validator("comparator")
    @classmethod
    def _comparator(cls, v):
        v = (v or "").strip().lower()
        if v not in COMPARATORS:
            raise ValueError(f"comparator must be one of {list(COMPARATORS)}")
        return v

    @field_validator("symbol")
    @classmethod
    def _symbol(cls, v):
        v = (v or "").strip().upper()
        return v or None

    @field_validator("cooldown_min")
    @classmethod
    def _cooldown(cls, v):
        if v < 5 or v > 1440:
            raise ValueError("cooldown_min must be 5..1440")
        return v


def _auth(authorization: Optional[str]):
    agent = _get_agent_by_token(_extract_token(authorization))
    if not agent:
        raise HTTPException(status_code=401, detail="Invalid token")
    return agent


def _require_symbol(data: WatchIn):
    if data.metric in NEEDS_SYMBOL and not data.symbol:
        raise HTTPException(status_code=400,
                            detail=f"metric '{data.metric}' requires a symbol (e.g. BTCUSDT)")


def register_watch_routes(app: FastAPI, ctx: RouteContext) -> None:

    @app.get("/api/watches")
    async def list_watches(authorization: str = Header(None)):
        agent = _auth(authorization)
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM user_watches WHERE agent_id = ? ORDER BY id DESC",
                           (agent["id"],))
            rows = [dict(r) for r in cursor.fetchall()]
        finally:
            conn.close()
        # attach the live value so the UI shows where each watch stands now
        cache: dict = {}
        for r in rows:
            key = (r["metric"], r.get("symbol") or "")
            if key not in cache:
                cache[key] = watch_engine.resolve_metric(r["metric"], r.get("symbol"))
            r["current_value"] = cache[key]
        return {"watches": rows, "metrics": list(METRICS), "needs_symbol": list(NEEDS_SYMBOL)}

    @app.post("/api/watches")
    async def create_watch(data: WatchIn, authorization: str = Header(None)):
        agent = _auth(authorization)
        _require_symbol(data)
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) AS n FROM user_watches WHERE agent_id = ?",
                           (agent["id"],))
            if int(cursor.fetchone()["n"]) >= MAX_WATCHES_PER_AGENT:
                raise HTTPException(status_code=400,
                                    detail=f"at most {MAX_WATCHES_PER_AGENT} watches per agent")
            begin_write_transaction(cursor)
            cursor.execute(
                """INSERT INTO user_watches
                   (agent_id, name, metric, symbol, comparator, threshold, enabled,
                    cooldown_min, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (agent["id"], data.name, data.metric, data.symbol, data.comparator,
                 data.threshold, 1 if data.enabled else 0, data.cooldown_min,
                 datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")))
            watch_id = cursor.lastrowid
            conn.commit()
            return {"id": watch_id, "ok": True}
        finally:
            conn.close()

    @app.put("/api/watches/{watch_id}")
    async def update_watch(watch_id: int, data: WatchIn, authorization: str = Header(None)):
        agent = _auth(authorization)
        _require_symbol(data)
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM user_watches WHERE id = ? AND agent_id = ?",
                           (watch_id, agent["id"]))
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail="Watch not found")
            begin_write_transaction(cursor)
            cursor.execute(
                """UPDATE user_watches SET name=?, metric=?, symbol=?, comparator=?,
                   threshold=?, enabled=?, cooldown_min=? WHERE id=? AND agent_id=?""",
                (data.name, data.metric, data.symbol, data.comparator, data.threshold,
                 1 if data.enabled else 0, data.cooldown_min, watch_id, agent["id"]))
            conn.commit()
            return {"ok": True}
        finally:
            conn.close()

    @app.delete("/api/watches/{watch_id}")
    async def delete_watch(watch_id: int, authorization: str = Header(None)):
        agent = _auth(authorization)
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            begin_write_transaction(cursor)
            cursor.execute("DELETE FROM user_watches WHERE id = ? AND agent_id = ?",
                           (watch_id, agent["id"]))
            deleted = cursor.rowcount
            conn.commit()
            if not deleted:
                raise HTTPException(status_code=404, detail="Watch not found")
            return {"ok": True}
        finally:
            conn.close()
