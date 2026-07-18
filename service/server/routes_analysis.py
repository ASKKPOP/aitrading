"""Analysis routes — run the multi-agent trading-analysis engine on demand.

POST /api/analysis/run          { symbol, market, lang }  -> { decision, report, analysts }
POST /api/analysis/run/stream   same body -> SSE stream of per-step progress events,
                                ending with {"event":"result", ...} (or {"event":"error"}).
POST /api/analysis/jobs         same body -> { job_id, status } — runs server-side,
                                detached from the connection (survives page close).
GET  /api/analysis/jobs/current -> { job } — the caller's newest job with step
                                events, result and gate verdict (see analysis_jobs.py).
"""

from __future__ import annotations

import asyncio
import json
from typing import Optional

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator

from analysis_agents import run_analysis
from routes_shared import RouteContext
from services import _get_agent_by_token
from utils import _extract_token


class AnalysisRequest(BaseModel):
    symbol: str
    market: str = "us-stock"
    lang: str = "en"
    # Optional LLM-provider override for this run (used by the Automation page
    # test-run so a rule's provider choice powers its preview). Same allowed
    # set as automation rules; empty/None -> the user's configured provider.
    provider: Optional[str] = None
    # Optional automation rule id (must belong to the caller). When set, the
    # stream also emits a {"event":"gates"} verdict: would the worker's
    # execution gates have placed this trade? Preview only — nothing executes.
    config_id: Optional[int] = None

    @field_validator("provider")
    @classmethod
    def _provider(cls, v):
        from routes_automation import ALLOWED_PROVIDERS
        v = (v or "").strip().lower()
        if v not in ALLOWED_PROVIDERS:
            raise ValueError(f"provider must be one of {[p for p in ALLOWED_PROVIDERS if p]} or empty")
        return v or None


class ChatStartRequest(BaseModel):
    symbol: Optional[str] = None
    market: str = "crypto"
    title: Optional[str] = None


class ChatMessageRequest(BaseModel):
    message: str


class AssistantMessageRequest(BaseModel):
    message: str
    lang: str = "en"


def _load_own_config(agent_id: int, config_id: int) -> Optional[dict]:
    """The caller's automation rule, or None when absent / not theirs."""
    from database import get_db_connection
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM automation_configs WHERE id = ? AND agent_id = ?",
                       (config_id, agent_id))
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def register_analysis_routes(app: FastAPI, ctx: RouteContext) -> None:

    # Any job still marked 'running' at process start belongs to a dead
    # process (jobs live in daemon threads) — flip them to error once.
    try:
        from analysis_jobs import mark_stale_jobs
        mark_stale_jobs()
    except Exception:  # noqa: BLE001 — table may not exist yet on first boot
        pass

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
                run_analysis, symbol, market, lang, data.provider, agent.get("id"))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=f"Analysis failed: {exc}")

        result["requested_by"] = agent.get("name")
        return result

    @app.post("/api/analysis/run/stream")
    async def run_analysis_stream_endpoint(data: AnalysisRequest,
                                           authorization: str = Header(None)):
        """Same pipeline as /api/analysis/run, but streams per-step progress as
        Server-Sent Events so the UI can show the pipeline working live.
        Events: {"event":"step", "step":..., "status":"start|done|error", ...}
        then a final {"event":"result", "result": {...}} or {"event":"error"}."""
        token = _extract_token(authorization)
        agent = _get_agent_by_token(token)
        if not agent:
            raise HTTPException(status_code=401, detail="Invalid token")

        symbol = (data.symbol or "").strip()
        if not symbol:
            raise HTTPException(status_code=400, detail="symbol is required")
        market = (data.market or "us-stock").strip().lower()
        lang = "th" if (data.lang or "en").lower().startswith("th") else "en"

        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()

        def progress(evt: dict) -> None:
            # Called from worker threads inside the pipeline.
            loop.call_soon_threadsafe(queue.put_nowait, evt)

        def sse(payload: dict) -> str:
            return f"data: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"

        async def stream():
            task = asyncio.create_task(asyncio.to_thread(
                run_analysis, symbol, market, lang, data.provider, agent.get("id"),
                progress=progress))
            try:
                while True:
                    get = asyncio.ensure_future(queue.get())
                    done, _ = await asyncio.wait({get, task},
                                                 return_when=asyncio.FIRST_COMPLETED)
                    if get in done:
                        yield sse({"event": "step", **get.result()})
                        continue
                    get.cancel()
                    while not queue.empty():  # drain events raced with completion
                        yield sse({"event": "step", **queue.get_nowait()})
                    try:
                        result = task.result()
                        result["requested_by"] = agent.get("name")
                        # Automation test-run: report whether the worker's
                        # execution gates would have placed this trade.
                        # Fail-soft — a preview problem never hides the result.
                        if data.config_id:
                            try:
                                config = await asyncio.to_thread(
                                    _load_own_config, agent["id"], data.config_id)
                                if config is not None:
                                    from automation import preview_rule_execution
                                    gates = await asyncio.to_thread(
                                        preview_rule_execution, config, result)
                                    yield sse({"event": "gates", **gates})
                            except Exception:  # noqa: BLE001
                                pass
                        yield sse({"event": "result", "result": result})
                    except Exception as exc:  # noqa: BLE001
                        yield sse({"event": "error", "detail": str(exc)})
                    return
            finally:
                if not task.done():
                    task.cancel()

        return StreamingResponse(stream(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache",
                                          "X-Accel-Buffering": "no"})

    # ── Server-side jobs — the run survives the page being closed ──

    @app.post("/api/analysis/jobs")
    async def start_analysis_job(data: AnalysisRequest,
                                 authorization: str = Header(None)):
        token = _extract_token(authorization)
        agent = _get_agent_by_token(token)
        if not agent:
            raise HTTPException(status_code=401, detail="Invalid token")

        symbol = (data.symbol or "").strip()
        if not symbol:
            raise HTTPException(status_code=400, detail="symbol is required")
        if len(symbol) > 32:  # analysis_jobs.symbol is VARCHAR(32) on MySQL
            raise HTTPException(status_code=400, detail="symbol too long (max 32 chars)")
        market = (data.market or "us-stock").strip().lower()
        if market not in ("crypto", "us-stock"):
            raise HTTPException(status_code=400, detail="market must be crypto or us-stock")
        lang = "th" if (data.lang or "en").lower().startswith("th") else "en"

        import analysis_jobs
        return await asyncio.to_thread(
            analysis_jobs.start_job, agent["id"], symbol, market, lang,
            data.provider, data.config_id)

    @app.get("/api/analysis/jobs/current")
    async def read_current_analysis_job(authorization: str = Header(None)):
        token = _extract_token(authorization)
        agent = _get_agent_by_token(token)
        if not agent:
            raise HTTPException(status_code=401, detail="Invalid token")
        import analysis_jobs
        job = await asyncio.to_thread(analysis_jobs.get_current_job, agent["id"])
        return {"job": job}

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

    # ── AI Assistant (Plan 06 C3) — global, knows the user's whole account ──

    @app.get("/api/assistant")
    async def read_assistant(authorization: str = Header(None)):
        """The persistent assistant conversation for this agent."""
        agent = _agent(authorization)
        from assistant import get_or_create_session
        from consult import get_messages
        session = get_or_create_session(agent["id"])
        return {"session": session, "messages": get_messages(session["id"])}

    @app.get("/api/assistant/profile")
    async def read_assistant_profile(authorization: str = Header(None)):
        """The exact account snapshot the assistant sees (API keys excluded)."""
        agent = _agent(authorization)
        from assistant import build_user_profile
        return {"profile": await asyncio.to_thread(build_user_profile, agent["id"])}

    @app.post("/api/assistant/messages")
    async def post_assistant_message(data: AssistantMessageRequest,
                                     authorization: str = Header(None)):
        agent = _agent(authorization)
        from assistant import assistant_turn
        try:
            return await asyncio.to_thread(assistant_turn, agent["id"], data.message, data.lang)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=f"Assistant failed: {exc}")

    @app.get("/api/assistant/sessions")
    async def list_assistant_sessions(authorization: str = Header(None)):
        """Every past conversation this member had with the assistant."""
        agent = _agent(authorization)
        from assistant import list_sessions
        return {"sessions": list_sessions(agent["id"])}

    @app.get("/api/assistant/sessions/{session_id}")
    async def read_assistant_session(session_id: int, authorization: str = Header(None)):
        agent = _agent(authorization)
        from assistant import get_session_messages
        messages = get_session_messages(agent["id"], session_id)
        if messages is None:
            raise HTTPException(status_code=404, detail="Session not found")
        return {"messages": messages}

    @app.post("/api/assistant/sessions")
    async def new_assistant_session(authorization: str = Header(None)):
        """Start a fresh conversation; all previous ones are kept."""
        agent = _agent(authorization)
        from assistant import start_new_session
        return {"session": start_new_session(agent["id"])}

    @app.delete("/api/assistant")
    async def clear_assistant(authorization: str = Header(None)):
        """History is never deleted: 'clear' now just starts a new conversation."""
        agent = _agent(authorization)
        from assistant import start_new_session
        start_new_session(agent["id"])
        return {"ok": True}
