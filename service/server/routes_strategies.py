"""
routes_strategies.py — Strategy CRUD + backtest validation flag.

Endpoints:
  POST   /api/strategies                       — create strategy
  GET    /api/strategies                       — list agent's active strategies
  GET    /api/strategies/{strategy_id}         — strategy detail + signal_count
  PUT    /api/strategies/{strategy_id}         — update name / description / config
  DELETE /api/strategies/{strategy_id}         — soft-deactivate
  POST   /api/strategies/{strategy_id}/validate — mark backtest_validated=1, record Sharpe
"""
from __future__ import annotations

import json
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel

import database
from routes_shared import RouteContext, utc_now_iso_z


# ── Request / response models ─────────────────────────────────────────────────

class CreateStrategyRequest(BaseModel):
    name: str
    description: Optional[str] = None
    config: Optional[Any] = None  # any JSON-serialisable value


class UpdateStrategyRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    config: Optional[Any] = None


class ValidateStrategyRequest(BaseModel):
    sharpe: float


# ── Route registration ────────────────────────────────────────────────────────

def register_strategy_routes(app: FastAPI, ctx: RouteContext) -> None:

    # ── POST /api/strategies ──────────────────────────────────────────────────
    @app.post("/api/strategies", status_code=201)
    def create_strategy(req: Request, body: CreateStrategyRequest):
        agent = _require_agent(req)
        config_json = json.dumps(body.config) if body.config is not None else None
        now = utc_now_iso_z()

        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO strategies
               (agent_id, name, description, config, created_at, updated_at)
               VALUES (?,?,?,?,?,?)""",
            (agent["id"], body.name, body.description, config_json, now, now),
        )
        strategy_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return {
            "strategy_id": strategy_id,
            "name": body.name,
            "description": body.description,
            "config": body.config,
            "backtest_validated": False,
            "last_backtest_sharpe": None,
        }

    # ── GET /api/strategies ───────────────────────────────────────────────────
    @app.get("/api/strategies")
    def list_strategies(req: Request):
        agent = _require_agent(req)
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """SELECT id, name, description, config, backtest_validated,
                      last_backtest_sharpe, last_backtest_at, created_at, updated_at
               FROM strategies
               WHERE agent_id=? AND is_active=1
               ORDER BY created_at DESC""",
            (agent["id"],),
        )
        rows = cursor.fetchall()
        conn.close()
        return {"strategies": [_row_to_dict(r) for r in rows]}

    # ── GET /api/strategies/{strategy_id} ─────────────────────────────────────
    @app.get("/api/strategies/{strategy_id}")
    def get_strategy(strategy_id: int, req: Request):
        agent = _require_agent(req)
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """SELECT id, name, description, config, backtest_validated,
                      last_backtest_sharpe, last_backtest_at, created_at, updated_at
               FROM strategies
               WHERE id=? AND agent_id=? AND is_active=1""",
            (strategy_id, agent["id"]),
        )
        row = cursor.fetchone()
        if not row:
            conn.close()
            raise HTTPException(status_code=404, detail="Strategy not found")

        # Count signals that reference this strategy
        cursor.execute(
            "SELECT COUNT(*) AS cnt FROM signals WHERE strategy_id=?",
            (strategy_id,),
        )
        signal_count = cursor.fetchone()["cnt"]
        conn.close()

        d = _row_to_dict(row)
        d["signal_count"] = signal_count
        return d

    # ── PUT /api/strategies/{strategy_id} ─────────────────────────────────────
    @app.put("/api/strategies/{strategy_id}")
    def update_strategy(strategy_id: int, req: Request, body: UpdateStrategyRequest):
        agent = _require_agent(req)
        conn = database.get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT id FROM strategies WHERE id=? AND agent_id=? AND is_active=1",
            (strategy_id, agent["id"]),
        )
        if not cursor.fetchone():
            conn.close()
            raise HTTPException(status_code=404, detail="Strategy not found")

        # Build update set dynamically (only provided fields)
        sets = ["updated_at=?"]
        params: list = [utc_now_iso_z()]
        if body.name is not None:
            sets.append("name=?")
            params.append(body.name)
        if body.description is not None:
            sets.append("description=?")
            params.append(body.description)
        if body.config is not None:
            sets.append("config=?")
            params.append(json.dumps(body.config))
        params += [strategy_id, agent["id"]]

        cursor.execute(
            f"UPDATE strategies SET {', '.join(sets)} WHERE id=? AND agent_id=?",
            params,
        )
        conn.commit()

        # Return updated row
        cursor.execute(
            "SELECT id, name, description, config, backtest_validated, last_backtest_sharpe FROM strategies WHERE id=?",
            (strategy_id,),
        )
        row = cursor.fetchone()
        conn.close()
        return _row_to_dict(row)

    # ── DELETE /api/strategies/{strategy_id} ──────────────────────────────────
    @app.delete("/api/strategies/{strategy_id}", status_code=204)
    def deactivate_strategy(strategy_id: int, req: Request):
        agent = _require_agent(req)
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE strategies SET is_active=0, updated_at=? WHERE id=? AND agent_id=?",
            (utc_now_iso_z(), strategy_id, agent["id"]),
        )
        if cursor.rowcount == 0:
            conn.close()
            raise HTTPException(status_code=404, detail="Strategy not found")
        conn.commit()
        conn.close()

    # ── POST /api/strategies/{strategy_id}/validate ───────────────────────────
    @app.post("/api/strategies/{strategy_id}/validate")
    def validate_strategy(strategy_id: int, req: Request, body: ValidateStrategyRequest):
        """Record backtest result and set backtest_validated=1 when Sharpe > 0."""
        agent = _require_agent(req)
        conn = database.get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT id FROM strategies WHERE id=? AND agent_id=? AND is_active=1",
            (strategy_id, agent["id"]),
        )
        if not cursor.fetchone():
            conn.close()
            raise HTTPException(status_code=404, detail="Strategy not found")

        validated = 1 if body.sharpe > 0 else 0
        cursor.execute(
            """UPDATE strategies
               SET backtest_validated=?, last_backtest_sharpe=?, last_backtest_at=?, updated_at=?
               WHERE id=? AND agent_id=?""",
            (validated, body.sharpe, utc_now_iso_z(), utc_now_iso_z(), strategy_id, agent["id"]),
        )
        conn.commit()
        conn.close()

        return {
            "strategy_id": strategy_id,
            "backtest_validated": bool(validated),
            "last_backtest_sharpe": body.sharpe,
        }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _row_to_dict(row) -> dict:
    d = dict(row)
    # Deserialise config JSON if present
    if d.get("config") and isinstance(d["config"], str):
        try:
            d["config"] = json.loads(d["config"])
        except Exception:
            pass
    d["backtest_validated"] = bool(d.get("backtest_validated", 0))
    d["strategy_id"] = d.pop("id", d.get("strategy_id"))
    return d


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
