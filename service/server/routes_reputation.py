"""Phase 4.7 — reputation slashing endpoints.

GET  /api/agents/{agent_id}/reputation          — reputation score + slash history
POST /api/signals/{signal_id}/slash             — evaluate a closed signal for slashing
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel

import database
import reputation as rep
from routes_shared import RouteContext

_logger = logging.getLogger(__name__)


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


class SlashRequest(BaseModel):
    entry_price: float
    close_price: float


def register_reputation_routes(app: FastAPI, ctx: RouteContext) -> None:

    @app.get("/api/agents/{agent_id}/reputation")
    def get_reputation(agent_id: int):
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, reputation_score FROM agents WHERE id=?", (agent_id,))
        agent = cur.fetchone()
        if not agent:
            conn.close()
            raise HTTPException(status_code=404, detail="Agent not found")

        cur.execute(
            """SELECT id, signal_id, loss_pct, follower_count, points_deducted, created_at
               FROM reputation_slashes
               WHERE leader_id=?
               ORDER BY created_at DESC""",
            (agent_id,),
        )
        slashes = [dict(r) for r in cur.fetchall()]
        conn.close()

        return {
            "agent_id": agent_id,
            "reputation_score": agent["reputation_score"],
            "slashes": slashes,
        }

    @app.post("/api/signals/{signal_id}/slash")
    def slash_signal(signal_id: int, req: Request, body: SlashRequest):
        caller = _require_agent(req)

        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, agent_id FROM signals WHERE signal_id=?", (signal_id,))
        signal = cur.fetchone()
        conn.close()

        if not signal:
            raise HTTPException(status_code=404, detail="Signal not found")

        if signal["agent_id"] != caller["id"]:
            raise HTTPException(status_code=403, detail="Only the signal's author can evaluate slashing")

        if body.entry_price <= 0:
            raise HTTPException(status_code=400, detail="entry_price must be positive")

        loss_pct = (body.entry_price - body.close_price) / body.entry_price * 100.0

        if loss_pct <= rep.SLASH_THRESHOLD_PCT:
            return {"slashed": False, "points_deducted": 0, "loss_pct": round(loss_pct, 4)}

        follower_count = rep.count_active_followers(caller["id"])
        points = rep.apply_reputation_slash(
            leader_id=caller["id"],
            signal_id=signal_id,
            loss_pct=round(loss_pct, 4),
            follower_count=follower_count,
        )

        return {
            "slashed": True,
            "points_deducted": points,
            "loss_pct": round(loss_pct, 4),
            "follower_count": follower_count,
        }
