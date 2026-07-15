"""Risk engine routes (signal-collection plan Phase 1).

    GET  /api/risk/limits    my risk limits (defaults if never set)
    PUT  /api/risk/limits    update my risk limits (partial)
    GET  /api/risk/breaker   circuit-breaker state (global + my agent scope)
    POST /api/risk/halt      HALT my automation (per-agent breaker)
    POST /api/risk/resume    clear my HALT

There is no admin role in this build, so the halt endpoint only trips the
caller's own agent-scope breaker; the 'global' scope is reserved for system
trips (e.g. the Phase-3 volatility-shock feed) and ops tooling.
"""

from __future__ import annotations

from typing import Optional

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, field_validator

from risk_engine import (
    clear_breaker,
    get_breaker,
    get_risk_limits,
    put_risk_limits,
    risk_engine_enabled,
    trip_breaker,
)
from routes_shared import RouteContext
from services import _get_agent_by_token
from utils import _extract_token


class RiskLimitsIn(BaseModel):
    max_daily_loss_usd: Optional[float] = None
    max_symbol_exposure_usd: Optional[float] = None
    stop_loss_pct: Optional[float] = None
    take_profit_pct: Optional[float] = None
    use_kelly: Optional[bool] = None

    @field_validator("max_daily_loss_usd", "max_symbol_exposure_usd")
    @classmethod
    def _usd(cls, v):
        if v is not None and (v < 0 or v > 10_000_000):
            raise ValueError("must be between 0 and 10,000,000 (0 disables the check)")
        return v

    @field_validator("stop_loss_pct", "take_profit_pct")
    @classmethod
    def _pct(cls, v):
        if v is not None and (v < 0 or v >= 1):
            raise ValueError("must be 0 <= pct < 1 (0 disables)")
        return v


class HaltIn(BaseModel):
    reason: Optional[str] = None


def _auth(authorization: Optional[str]):
    agent = _get_agent_by_token(_extract_token(authorization))
    if not agent:
        raise HTTPException(status_code=401, detail="Invalid token")
    return agent


def register_risk_routes(app: FastAPI, ctx: RouteContext) -> None:

    @app.get("/api/risk/limits")
    async def read_limits(authorization: str = Header(None)):
        agent = _auth(authorization)
        return {"limits": get_risk_limits(agent["id"]),
                "risk_engine_enabled": risk_engine_enabled()}

    @app.put("/api/risk/limits")
    async def update_limits(data: RiskLimitsIn, authorization: str = Header(None)):
        agent = _auth(authorization)
        values = data.model_dump(exclude_none=True)
        if "use_kelly" in values:
            values["use_kelly"] = 1 if values["use_kelly"] else 0
        return {"limits": put_risk_limits(agent["id"], values)}

    @app.get("/api/risk/breaker")
    async def read_breaker(authorization: str = Header(None)):
        agent = _auth(authorization)
        return {"breaker": get_breaker(agent["id"]),
                "risk_engine_enabled": risk_engine_enabled()}

    @app.post("/api/risk/halt")
    async def halt(data: HaltIn = None, authorization: str = Header(None)):
        agent = _auth(authorization)
        reason = (data.reason if data else None) or "manual halt"
        state = trip_breaker(reason, agent_id=agent["id"])
        return {"ok": True, "breaker": state}

    @app.post("/api/risk/resume")
    async def resume(authorization: str = Header(None)):
        agent = _auth(authorization)
        state = clear_breaker(agent_id=agent["id"])
        return {"ok": True, "breaker": state}
