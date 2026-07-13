"""Analysis routes — run the multi-agent trading-analysis engine on demand.

POST /api/analysis/run   { symbol, market, lang }  -> { decision, report, analysts }
"""

from __future__ import annotations

import asyncio

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from analysis_agents import run_analysis
from routes_shared import RouteContext
from services import _get_agent_by_token
from utils import _extract_token


class AnalysisRequest(BaseModel):
    symbol: str
    market: str = "us-stock"
    lang: str = "en"


def register_analysis_routes(app: FastAPI, ctx: RouteContext) -> None:

    @app.post("/api/analysis/run")
    async def run_analysis_endpoint(data: AnalysisRequest, authorization: str = Header(None)):
        token = _extract_token(authorization)
        agent = _get_agent_by_token(token)
        if not agent:
            raise HTTPException(status_code=401, detail="Invalid token")

        symbol = (data.symbol or "").strip()
        if not symbol:
            raise HTTPException(status_code=400, detail="symbol is required")
        market = (data.market or "us-stock").strip().lower()
        lang = "th" if (data.lang or "en").lower().startswith("th") else "en"

        try:
            result = await asyncio.to_thread(run_analysis, symbol, market, lang)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=f"Analysis failed: {exc}")

        result["requested_by"] = agent.get("name")
        return result
