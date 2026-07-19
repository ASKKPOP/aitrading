"""Trading Runs routes (Plan 10) — lifecycle API for AI auto-trading runs.

    POST   /api/runs                      create (draft)
    GET    /api/runs                      list my runs
    GET    /api/runs/{id}                 detail
    POST   /api/runs/{id}/start           draft -> armed|running
    POST   /api/runs/{id}/pause           running -> paused (entries only)
    POST   /api/runs/{id}/resume          paused -> running
    POST   /api/runs/{id}/stop            body {"flatten": bool}
    PUT    /api/runs/{id}/stop-conditions tighten-only while active
    DELETE /api/runs/{id}                 draft/stopped only
    GET    /api/runs/{id}/events          journal replay (?after_seq=&limit=)

Auth follows routes_automation.py exactly: agent bearer token, and EVERY
read/write carries the agent_id ownership predicate (cross-tenant access is
a 404, never a data leak — by-run_id telemetry endpoints are where IDOR
creeps in).
"""

from __future__ import annotations

import json as _json
from typing import Optional

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, field_validator

import trading_runs
from routes_shared import RouteContext
from services import _get_agent_by_token
from utils import _extract_token

ALLOWED_PROVIDERS = ("", "openai", "gemini", "grok", "qwen", "glm", "local",
                     "openrouter", "anthropic")


def _probe_price(symbol: str, market: str) -> Optional[float]:
    """Creation-time probe that the symbol is actually price-fetchable —
    an unfetchable symbol would arm a run whose stops can never evaluate.
    Isolated for test patching."""
    from price_fetcher import get_price_from_market
    try:
        return get_price_from_market(symbol, None, market)
    except Exception:  # noqa: BLE001
        return None


class RunIn(BaseModel):
    symbol: str
    market: str = "crypto"
    market_type: str = "spot"
    max_bet_usd: float
    run_budget_usd: Optional[float] = None
    interval_minutes: int = 60
    min_confidence: float = 0.65
    provider: Optional[str] = None
    lang: str = "en"
    leverage: float = 1.0
    start_condition: Optional[dict] = None
    stop_conditions: Optional[dict] = None
    stop_flatten: bool = True

    @field_validator("symbol")
    @classmethod
    def _symbol(cls, v: str) -> str:
        v = (v or "").strip().upper()
        if not v or len(v) > 20:
            raise ValueError("symbol must be 1-20 characters")
        return v

    @field_validator("market")
    @classmethod
    def _market(cls, v: str) -> str:
        v = (v or "").strip().lower()
        if v not in trading_runs.VALID_RUN_MARKETS:
            raise ValueError(f"market must be one of {trading_runs.VALID_RUN_MARKETS}")
        return v

    @field_validator("market_type")
    @classmethod
    def _market_type(cls, v: str) -> str:
        v = (v or "spot").strip().lower()
        if v not in trading_runs.VALID_MARKET_TYPES:
            raise ValueError(f"market_type must be one of {trading_runs.VALID_MARKET_TYPES}")
        return v

    @field_validator("max_bet_usd")
    @classmethod
    def _max_bet(cls, v: float) -> float:
        if v <= 0 or v > 1_000_000:
            raise ValueError("max_bet_usd must be positive and <= 1,000,000")
        return v

    @field_validator("run_budget_usd")
    @classmethod
    def _budget(cls, v):
        if v is not None and (v <= 0 or v > 10_000_000):
            raise ValueError("run_budget_usd must be positive and <= 10,000,000")
        return v

    @field_validator("interval_minutes")
    @classmethod
    def _interval(cls, v: int) -> int:
        if v < 5 or v > 24 * 60:
            raise ValueError("interval_minutes must be between 5 and 1440")
        return v

    @field_validator("min_confidence")
    @classmethod
    def _conf(cls, v: float) -> float:
        if not (0 <= v <= 1):
            raise ValueError("min_confidence must be 0..1")
        return v

    @field_validator("provider")
    @classmethod
    def _provider(cls, v):
        v = (v or "").strip().lower()
        if v not in ALLOWED_PROVIDERS:
            raise ValueError(f"provider must be one of {[p for p in ALLOWED_PROVIDERS if p]} or empty")
        return v or None

    @field_validator("lang")
    @classmethod
    def _lang(cls, v: str) -> str:
        return "th" if (v or "en").lower().startswith("th") else "en"

    @field_validator("leverage")
    @classmethod
    def _leverage(cls, v: float) -> float:
        # v1: leverage is pinned to 1. Real leverage (2-5x isolated margin +
        # liquidation) is gated on ENABLE_PRICE_PUSH in prod (Plan 10 D5).
        if v != 1:
            raise ValueError("leverage must be 1 in this build")
        return 1.0


class StartIn(BaseModel):
    resolve_conflicts: bool = False


class StopIn(BaseModel):
    flatten: bool = True


class ReportingIn(BaseModel):
    report_frequency: str = "off"
    report_hour_local: Optional[int] = None
    report_tz: Optional[str] = None
    notify_on_trade: bool = False
    profit_threshold_pct: Optional[float] = None
    loss_threshold_pct: Optional[float] = None
    drawdown_threshold_pct: Optional[float] = None

    @field_validator("report_frequency")
    @classmethod
    def _freq(cls, v: str) -> str:
        v = (v or "off").strip().lower()
        from run_reports import VALID_FREQUENCIES
        if v not in VALID_FREQUENCIES:
            raise ValueError(f"report_frequency must be one of {VALID_FREQUENCIES}")
        return v

    @field_validator("report_hour_local")
    @classmethod
    def _hour(cls, v):
        if v is not None and not (0 <= v <= 23):
            raise ValueError("report_hour_local must be 0..23")
        return v

    @field_validator("report_tz")
    @classmethod
    def _tz(cls, v):
        if v is None or not str(v).strip():
            return None
        from zoneinfo import ZoneInfo
        try:
            ZoneInfo(str(v).strip())
        except Exception:
            raise ValueError(f"unknown timezone '{v}' (IANA name expected)")
        return str(v).strip()

    @field_validator("profit_threshold_pct", "loss_threshold_pct",
                     "drawdown_threshold_pct")
    @classmethod
    def _pct(cls, v):
        if v is not None and (v <= 0 or v > 1000):
            raise ValueError("threshold percents must be in (0, 1000]")
        return v


def _auth(authorization: Optional[str]):
    agent = _get_agent_by_token(_extract_token(authorization))
    if not agent:
        raise HTTPException(status_code=401, detail="Invalid token")
    return agent


def _run_or_404(run_id: int, agent_id: int) -> dict:
    run = trading_runs.get_run(run_id, agent_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


def _public(run: dict) -> dict:
    """Route-facing shape: JSON columns decoded, claim bookkeeping hidden."""
    out = dict(run)
    for col, key in (("config_snapshot_json", "config"),
                     ("start_condition_json", "start_condition"),
                     ("stop_conditions_json", "stop_conditions")):
        raw = out.pop(col, None)
        try:
            out[key] = _json.loads(raw) if raw else None
        except Exception:  # noqa: BLE001
            out[key] = None
    out.pop("claimed_by", None)
    out.pop("claim_expires_at", None)
    out.pop("active_key", None)
    return out


def register_runs_routes(app: FastAPI, ctx: RouteContext) -> None:

    @app.post("/api/runs")
    async def create_run(data: RunIn, authorization: str = Header(None)):
        agent = _auth(authorization)
        if data.market_type == "futures" and data.market != "crypto":
            raise HTTPException(status_code=400,
                                detail="futures market_type is crypto-only")
        if data.run_budget_usd is not None and data.run_budget_usd < data.max_bet_usd:
            raise HTTPException(status_code=400,
                                detail="run_budget_usd must be >= max_bet_usd")
        try:
            start_condition = trading_runs.validate_start_condition(data.start_condition)
            stop_conditions = trading_runs.validate_stop_conditions(data.stop_conditions)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        if _probe_price(data.symbol, data.market) is None:
            raise HTTPException(
                status_code=400,
                detail=f"no price available for {data.symbol} ({data.market}) — "
                       "an unpriceable symbol cannot be traded or stop-checked")
        settings = {
            "symbol": data.symbol, "market": data.market,
            "market_type": data.market_type, "max_bet_usd": data.max_bet_usd,
            "run_budget_usd": data.run_budget_usd,
            "interval_minutes": data.interval_minutes,
            "min_confidence": data.min_confidence, "provider": data.provider,
            "lang": data.lang, "leverage": 1.0,
        }
        run_id = trading_runs.create_run(agent["id"], settings, start_condition,
                                         stop_conditions, data.stop_flatten)
        return {"id": run_id, "ok": True,
                "run": _public(_run_or_404(run_id, agent["id"]))}

    @app.get("/api/runs")
    async def list_runs(limit: int = 50, authorization: str = Header(None)):
        agent = _auth(authorization)
        return {"runs": [_public(r) for r in trading_runs.list_runs(agent["id"], limit)]}

    @app.get("/api/runs/{run_id}")
    async def get_run(run_id: int, authorization: str = Header(None)):
        agent = _auth(authorization)
        return {"run": _public(_run_or_404(run_id, agent["id"]))}

    @app.post("/api/runs/{run_id}/start")
    async def start_run(run_id: int, data: StartIn = None,  # type: ignore[assignment]
                        authorization: str = Header(None)):
        agent = _auth(authorization)
        _run_or_404(run_id, agent["id"])
        resolved = None
        try:
            if data is not None and data.resolve_conflicts:
                resolved = trading_runs.resolve_start_conflicts(run_id, agent["id"])
            run = trading_runs.start_run(run_id, agent["id"])
        except trading_runs.EntitlementDenied as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        except trading_runs.StartConflict as exc:
            # detail is structured so the client can offer one-click resolution
            # ({"message": str, "conflicts": {"position": ..., "rule_ids": [...]}}).
            raise HTTPException(status_code=409,
                                detail={"message": str(exc),
                                        "conflicts": exc.conflicts})
        except LookupError:
            raise HTTPException(status_code=404, detail="Run not found")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        out = {"ok": True, "run": _public(run)}
        if resolved is not None:
            out["resolved"] = resolved
        return out

    @app.post("/api/runs/{run_id}/pause")
    async def pause_run(run_id: int, authorization: str = Header(None)):
        agent = _auth(authorization)
        _run_or_404(run_id, agent["id"])
        try:
            run = trading_runs.pause_run(run_id, agent["id"])
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return {"ok": True, "run": _public(run)}

    @app.post("/api/runs/{run_id}/resume")
    async def resume_run(run_id: int, authorization: str = Header(None)):
        agent = _auth(authorization)
        _run_or_404(run_id, agent["id"])
        try:
            run = trading_runs.resume_run(run_id, agent["id"])
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return {"ok": True, "run": _public(run)}

    @app.post("/api/runs/{run_id}/stop")
    async def stop_run(run_id: int, data: StopIn = None,  # type: ignore[assignment]
                       authorization: str = Header(None)):
        agent = _auth(authorization)
        _run_or_404(run_id, agent["id"])
        flatten = data.flatten if data is not None else True
        try:
            run = trading_runs.request_stop(run_id, agent["id"], flatten)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return {"ok": True, "run": _public(run)}

    @app.put("/api/runs/{run_id}/stop-conditions")
    async def put_stop_conditions(run_id: int, data: dict,
                                  authorization: str = Header(None)):
        agent = _auth(authorization)
        _run_or_404(run_id, agent["id"])
        try:
            run = trading_runs.update_stop_conditions(run_id, agent["id"], data)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return {"ok": True, "run": _public(run)}

    @app.delete("/api/runs/{run_id}")
    async def delete_run(run_id: int, authorization: str = Header(None)):
        agent = _auth(authorization)
        _run_or_404(run_id, agent["id"])
        try:
            trading_runs.delete_run(run_id, agent["id"])
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return {"ok": True}

    @app.get("/api/runs/{run_id}/snapshot")
    async def run_snapshot(run_id: int, authorization: str = Header(None)):
        """Cold-start state for the live dashboard: status + P&L + open
        position + the seq to subscribe from."""
        agent = _auth(authorization)
        run = _run_or_404(run_id, agent["id"])
        import run_engine
        pnl = run_engine.compute_run_pnl(run)
        pos = pnl.pop("position", None)
        return {"run": _public(run),
                "pnl": pnl,
                "position": pos,
                "subscribe_from_seq": int(run.get("last_event_seq") or 0)}

    @app.get("/api/runs/{run_id}/reporting")
    async def get_reporting(run_id: int, authorization: str = Header(None)):
        agent = _auth(authorization)
        run = _run_or_404(run_id, agent["id"])
        return {"reporting": {k: run.get(k) for k in (
            "report_frequency", "report_hour_local", "report_tz",
            "notify_on_trade", "profit_threshold_pct", "loss_threshold_pct",
            "drawdown_threshold_pct", "last_report_at")}}

    @app.put("/api/runs/{run_id}/reporting")
    async def put_reporting(run_id: int, data: ReportingIn,
                            authorization: str = Header(None)):
        agent = _auth(authorization)
        _run_or_404(run_id, agent["id"])
        from database import begin_write_transaction, get_db_connection
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            begin_write_transaction(cursor)
            cursor.execute(
                """UPDATE trading_runs
                   SET report_frequency = ?, report_hour_local = ?, report_tz = ?,
                       notify_on_trade = ?, profit_threshold_pct = ?,
                       loss_threshold_pct = ?, drawdown_threshold_pct = ?
                   WHERE id = ? AND agent_id = ?""",
                (data.report_frequency, data.report_hour_local, data.report_tz,
                 1 if data.notify_on_trade else 0, data.profit_threshold_pct,
                 data.loss_threshold_pct, data.drawdown_threshold_pct,
                 run_id, agent["id"]))
            conn.commit()
        finally:
            conn.close()
        return {"ok": True, "run": _public(_run_or_404(run_id, agent["id"]))}

    @app.get("/api/runs/{run_id}/reports")
    async def run_reports_feed(run_id: int, limit: int = 30,
                               authorization: str = Header(None)):
        agent = _auth(authorization)
        _run_or_404(run_id, agent["id"])
        from database import get_db_connection
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT * FROM run_reports WHERE run_id = ?
                   ORDER BY id DESC LIMIT ?""",
                (run_id, max(1, min(limit, 100))))
            return {"reports": [dict(r) for r in cursor.fetchall()]}
        finally:
            conn.close()

    @app.get("/api/runs/{run_id}/events")
    async def run_events(run_id: int, after_seq: int = 0, limit: int = 200,
                         authorization: str = Header(None)):
        agent = _auth(authorization)
        events = trading_runs.list_events(run_id, agent["id"], after_seq, limit)
        if events is None:
            raise HTTPException(status_code=404, detail="Run not found")
        for ev in events:
            try:
                ev["payload"] = _json.loads(ev["payload"]) if ev["payload"] else None
            except Exception:  # noqa: BLE001
                pass
        return {"events": events}
