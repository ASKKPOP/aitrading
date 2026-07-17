"""Analysis routes — run the multi-agent trading-analysis engine on demand.

POST /api/analysis/run   { symbol, market, lang }  -> { decision, report, analysts }
"""

from __future__ import annotations

import asyncio
from typing import Optional

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


class ChatStartRequest(BaseModel):
    symbol: Optional[str] = None
    market: str = "crypto"
    title: Optional[str] = None


class ChatMessageRequest(BaseModel):
    message: str


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
            result = await asyncio.to_thread(
                run_analysis, symbol, market, lang, None, agent.get("id"))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=f"Analysis failed: {exc}")

        result["requested_by"] = agent.get("name")
        return result

    # ── Consultation chat (Plan 06 C3) — advisory only; never executes ──

    def _agent(authorization):
        agent = _get_agent_by_token(_extract_token(authorization))
        if not agent:
            raise HTTPException(status_code=401, detail="Invalid token")
        return agent

    @app.get("/api/analysis/chat/sessions")
    async def list_chat_sessions(authorization: str = Header(None)):
        agent = _agent(authorization)
        from consult import list_sessions
        return {"sessions": list_sessions(agent["id"])}

    @app.post("/api/analysis/chat/sessions")
    async def start_chat_session(data: ChatStartRequest, authorization: str = Header(None)):
        agent = _agent(authorization)
        from consult import MAX_SESSIONS_PER_AGENT, create_session, list_sessions
        if len(list_sessions(agent["id"], limit=MAX_SESSIONS_PER_AGENT + 1)) >= MAX_SESSIONS_PER_AGENT:
            raise HTTPException(status_code=400,
                                detail=f"at most {MAX_SESSIONS_PER_AGENT} sessions — delete some first")
        market = (data.market or "crypto").strip().lower()
        if market not in ("crypto", "us-stock"):
            raise HTTPException(status_code=400, detail="market must be crypto or us-stock")
        session_id = create_session(agent["id"], data.symbol, market, data.title)
        return {"id": session_id, "ok": True}

    @app.get("/api/analysis/chat/sessions/{session_id}")
    async def read_chat_session(session_id: int, authorization: str = Header(None)):
        agent = _agent(authorization)
        from consult import get_messages, get_session
        session = get_session(session_id, agent["id"])
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        return {"session": session, "messages": get_messages(session_id)}

    @app.post("/api/analysis/chat/sessions/{session_id}/messages")
    async def post_chat_message(session_id: int, data: ChatMessageRequest,
                                authorization: str = Header(None)):
        agent = _agent(authorization)
        from consult import chat_turn, get_session
        session = get_session(session_id, agent["id"])
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        try:
            return await asyncio.to_thread(chat_turn, agent["id"], session, data.message)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=f"Chat failed: {exc}")

    @app.post("/api/analysis/chat/sessions/{session_id}/propose-rule")
    async def propose_rule_endpoint(session_id: int, authorization: str = Header(None)):
        """Distill the conversation into a rule DRAFT. Creates nothing."""
        agent = _agent(authorization)
        from consult import get_session, propose_rule
        session = get_session(session_id, agent["id"])
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        draft = await asyncio.to_thread(propose_rule, agent["id"], session)
        if draft is None:
            raise HTTPException(status_code=503,
                                detail="Could not draft a rule (no model configured or empty conversation)")
        return {"draft": draft}

    @app.delete("/api/analysis/chat/sessions/{session_id}")
    async def delete_chat_session(session_id: int, authorization: str = Header(None)):
        agent = _agent(authorization)
        from consult import delete_session
        if not delete_session(session_id, agent["id"]):
            raise HTTPException(status_code=404, detail="Session not found")
        return {"ok": True}
