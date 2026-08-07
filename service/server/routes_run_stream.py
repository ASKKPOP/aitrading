"""Trading Runs live stream (Plan 10, Phase 6).

    POST /api/runs/ws-ticket   mint a short-lived single-use WS ticket
    WS   /ws/runs?ticket=...   multiplexed run event/tick stream

Transport decisions (verified against prod reality, 2026-07-19):
  * Prod runs REDIS_ENABLED=false, so the DB-TAIL plane is the primary
    engine day one: each connection polls its subscribed runs' journals
    every RUN_WS_POLL_SECONDS (default 1.5s) between client messages. The
    wire protocol is latency-agnostic — a Redis pub/sub fast path can be
    layered in later without any client change.
  * Auth is a TICKET, not the session token: nginx's access log records
    full request lines including query strings, so long-lived tokens must
    never ride the WS URL. Tickets are HMAC-signed, 60s TTL, single-use
    (best-effort in-process nonce burn).
  * AUTHORIZATION IS PER-SUB, not per-connection (the Plan 10 blocker):
    every `sub` frame re-checks that the run belongs to the ticket's agent —
    an authenticated connection can never stream another tenant's P&L.

Client -> server ops:  {"op":"sub","run_id":N,"from_seq":N} · {"op":"unsub","run_id":N} · {"op":"ping"}
Server -> client:      {"type":"event","run_id","seq","event_type","ts","payload","v":1}
                       {"type":"tick","market","symbol","price","ts"}   (lossy by design)
                       {"type":"backfill_done","run_id","to_seq","oldest_retained_seq"}
                       {"type":"error"|"pong"|"sub_ok", ...}
Replay: client sends from_seq; backfill caps at 500 rows — larger gaps get
{"type":"resync_required"} and should cold-start from GET /api/runs/{id}/snapshot.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from typing import Any, Optional

from fastapi import FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect

from analysis_agents import normalize_lang
from database import get_db_connection
from market_i18n import localize_text
from routes_shared import RouteContext
from services import _get_agent_by_token
from utils import _extract_token

logger = logging.getLogger(__name__)

TICKET_TTL_SECONDS = 60
BACKFILL_CAP = 500

_burned_nonces: dict[str, float] = {}


def _poll_seconds() -> float:
    try:
        return max(0.2, float(os.getenv("RUN_WS_POLL_SECONDS", "1.5")))
    except ValueError:
        return 1.5


def _ticket_secret() -> bytes:
    secret = (os.getenv("WS_TICKET_SECRET", "").strip()
              or os.getenv("EXECUTION_ENCRYPTION_KEY", "").strip())
    if not secret:
        # dev fallback: per-process random (tickets die with the process)
        secret = _process_secret()
    return secret.encode()


_PROCESS_SECRET: Optional[str] = None


def _process_secret() -> str:
    global _PROCESS_SECRET
    if _PROCESS_SECRET is None:
        _PROCESS_SECRET = secrets.token_urlsafe(32)
    return _PROCESS_SECRET


def mint_ticket(agent_id: int) -> str:
    payload = f"{agent_id}:{int(time.time()) + TICKET_TTL_SECONDS}:{secrets.token_urlsafe(8)}"
    sig = hmac.new(_ticket_secret(), payload.encode(), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(f"{payload}:{sig}".encode()).decode()


def redeem_ticket(ticket: str) -> Optional[int]:
    """agent_id when valid+fresh+unused, else None."""
    try:
        raw = base64.urlsafe_b64decode(ticket.encode()).decode()
        agent_s, exp_s, nonce, sig = raw.rsplit(":", 3)[-4:]
        payload = f"{agent_s}:{exp_s}:{nonce}"
        expect = hmac.new(_ticket_secret(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expect):
            return None
        if int(exp_s) < time.time():
            return None
        now = time.time()
        for key, exp in list(_burned_nonces.items()):
            if exp < now:
                _burned_nonces.pop(key, None)
        if nonce in _burned_nonces:
            return None
        _burned_nonces[nonce] = float(exp_s)
        return int(agent_s)
    except Exception:  # noqa: BLE001
        return None


def _owned_run(run_id: int, agent_id: int) -> Optional[dict]:
    # User-scoped like the REST run surface (trading_runs.get_run_user_scoped):
    # the /automation grid lists every run of the caller's linked user, and its
    # WS subscriptions must be accepted for the same set.
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """SELECT r.id, r.agent_id, r.symbol, r.market, r.last_event_seq
               FROM trading_runs r
               JOIN agents owner ON owner.id = r.agent_id
               JOIN agents caller ON caller.id = ?
               WHERE r.id = ? AND (r.agent_id = caller.id
                     OR (owner.user_id IS NOT NULL
                         AND owner.user_id = caller.user_id))""",
            (agent_id, run_id))
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _events_after(run_id: int, after_seq: int, limit: int) -> list[dict]:
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """SELECT seq, event_type, ts, payload FROM run_events
               WHERE run_id = ? AND seq > ? ORDER BY seq ASC LIMIT ?""",
            (run_id, after_seq, limit))
        return [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()


def _oldest_retained_seq(run_id: int) -> int:
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT MIN(seq) AS s FROM run_events WHERE run_id = ?",
                       (run_id,))
        row = cursor.fetchone()
        return int(row["s"] or 0)
    finally:
        conn.close()


def _mark_for(run: dict) -> Optional[dict]:
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """SELECT current_price, price_updated_at FROM positions
               WHERE agent_id = ? AND market = ? AND symbol = ? AND run_id = ?""",
            (run["agent_id"], run["market"], run["symbol"], run["id"]))
        row = cursor.fetchone()
        if not row or row["current_price"] is None:
            return None
        return {"type": "tick", "market": run["market"], "symbol": run["symbol"],
                "price": float(row["current_price"]),
                "ts": row["price_updated_at"]}
    finally:
        conn.close()


def _event_frame(run_id: int, ev: dict, lang: str = "en") -> dict:
    payload = ev.get("payload")
    try:
        payload = json.loads(payload) if isinstance(payload, str) else payload
    except Exception:  # noqa: BLE001
        pass
    # A gate-skip REASON is English prose the run engine wrote ("decision is
    # 'hold'"), and the card renders it verbatim — so it stayed English on a
    # Korean or Thai screen. Localized here rather than on the client because
    # the catalogue behind it already exists server-side (desk_i18n_data, the
    # same one /automation/ai-analysis uses); duplicating it in TypeScript
    # would be two catalogues to keep in step.
    #
    # This connection belongs to ONE agent, so a per-connection language is
    # exactly right. Everything else in the payload stays raw: statuses and
    # stop reasons are codes the client maps itself.
    if (ev["event_type"] == "gate_skip" and isinstance(payload, dict)
            and isinstance(payload.get("reason"), str)):
        payload = {**payload, "reason": localize_text(payload["reason"], lang)}
    return {"type": "event", "v": 1, "run_id": run_id, "seq": ev["seq"],
            "event_type": ev["event_type"], "ts": ev["ts"], "payload": payload}


def register_run_stream_routes(app: FastAPI, ctx: RouteContext) -> None:

    @app.post("/api/runs/ws-ticket")
    async def ws_ticket(authorization: str = Header(None)):
        agent = _get_agent_by_token(_extract_token(authorization))
        if not agent:
            raise HTTPException(status_code=401, detail="Invalid token")
        return {"ticket": mint_ticket(int(agent["id"])),
                "expires_in": TICKET_TTL_SECONDS}

    @app.websocket("/ws/runs")
    async def ws_runs(websocket: WebSocket):
        ticket = websocket.query_params.get("ticket") or ""
        agent_id = redeem_ticket(ticket)
        if agent_id is None:
            await websocket.close(code=4401)
            return
        # Explicit query param rather than the handshake's Accept-Language:
        # the client already builds this URL, and a header the browser is not
        # obliged to send on an upgrade is a silent fallback to English.
        lang = normalize_lang(websocket.query_params.get("lang"))
        await websocket.accept()

        # run_id -> {"run": row, "cursor": last seq sent, "last_tick": frame}
        subs: dict[int, dict[str, Any]] = {}

        async def _drain_new(sub: dict[str, Any], run_id: int) -> None:
            events = await asyncio.to_thread(
                _events_after, run_id, sub["cursor"], BACKFILL_CAP)
            for ev in events:
                await websocket.send_json(_event_frame(run_id, ev, lang))
                sub["cursor"] = max(sub["cursor"], int(ev["seq"]))
            tick = await asyncio.to_thread(_mark_for, sub["run"])
            if tick and tick != sub.get("last_tick"):
                sub["last_tick"] = tick
                await websocket.send_json(tick)

        try:
            while True:
                try:
                    raw = await asyncio.wait_for(websocket.receive_text(),
                                                 timeout=_poll_seconds())
                except asyncio.TimeoutError:
                    for run_id, sub in list(subs.items()):
                        await _drain_new(sub, run_id)
                    continue

                try:
                    msg = json.loads(raw)
                except Exception:  # noqa: BLE001
                    await websocket.send_json({"type": "error", "error": "bad json"})
                    continue
                op = msg.get("op")

                if op == "ping":
                    await websocket.send_json({"type": "pong"})

                elif op == "sub":
                    run_id = int(msg.get("run_id") or 0)
                    from_seq = max(0, int(msg.get("from_seq") or 0))
                    # PER-SUB ownership check — every frame, no exceptions.
                    run = await asyncio.to_thread(_owned_run, run_id, agent_id)
                    if not run:
                        await websocket.send_json(
                            {"type": "error", "run_id": run_id,
                             "error": "run not found"})
                        continue
                    oldest = await asyncio.to_thread(_oldest_retained_seq, run_id)
                    gap = int(run["last_event_seq"] or 0) - from_seq
                    if gap > BACKFILL_CAP:
                        await websocket.send_json(
                            {"type": "resync_required", "run_id": run_id,
                             "oldest_retained_seq": oldest})
                        continue
                    sub = {"run": run, "cursor": from_seq, "last_tick": None}
                    subs[run_id] = sub
                    await websocket.send_json({"type": "sub_ok", "run_id": run_id})
                    await _drain_new(sub, run_id)
                    await websocket.send_json(
                        {"type": "backfill_done", "run_id": run_id,
                         "to_seq": sub["cursor"], "oldest_retained_seq": oldest})

                elif op == "unsub":
                    subs.pop(int(msg.get("run_id") or 0), None)
                    await websocket.send_json(
                        {"type": "unsub_ok", "run_id": msg.get("run_id")})

                else:
                    await websocket.send_json({"type": "error",
                                               "error": f"unknown op '{op}'"})
        except WebSocketDisconnect:
            pass
        except Exception:  # noqa: BLE001
            logger.debug("ws_runs connection error", exc_info=True)
