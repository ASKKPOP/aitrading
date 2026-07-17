"""Automation routes (Target 3) — CRUD for per-agent AI auto-trading rules + run history.

    GET    /api/automation/configs        list my rules
    POST   /api/automation/configs        create a rule
    PUT    /api/automation/configs/{id}   update a rule (partial)
    DELETE /api/automation/configs/{id}   delete a rule
    GET    /api/automation/runs           recent run history (optionally ?config_id=)
"""

from __future__ import annotations

from typing import Optional

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, field_validator

from automation import VALID_MARKETS
from database import begin_write_transaction, get_db_connection
from routes_shared import RouteContext
from services import _get_agent_by_token
from utils import _extract_token

ALLOWED_PROVIDERS = ("", "openai", "gemini", "grok", "qwen", "glm", "local", "openrouter", "anthropic")

# Plan 06 C2/B2 — first-class risk levels. Choosing one on a rule ALSO writes
# the matching exit profile into the agent's risk_limits (SL/TP/trailing/time
# stop), so UI presets finally propagate to the risk engine. Per-agent (not
# per-rule): the most recent risk_level applied wins, and the response echoes
# the applied limits so the UI can show them.
RISK_LEVEL_PRESETS: dict = {
    "stable": {"stop_loss_pct": 0.03, "take_profit_pct": 0.06,
               "use_trailing": 1, "trail_pct": 0.04, "time_stop_days": 5},
    "balanced": {"stop_loss_pct": 0.05, "take_profit_pct": 0.10,
                 "use_trailing": 1, "trail_pct": 0.05, "time_stop_days": 0},
    "aggressive": {"stop_loss_pct": 0.08, "take_profit_pct": 0.15,
                   "use_trailing": 0, "trail_pct": 0.05, "time_stop_days": 0},
}


class AutomationConfigIn(BaseModel):
    symbol: str
    market: str = "crypto"
    provider: Optional[str] = None
    interval_minutes: int = 60
    min_confidence: float = 0.65
    size_usd: float = 500
    auto_execute: bool = False
    account_type: str = "simulator"
    enabled: bool = True
    lang: str = "en"
    risk_level: Optional[str] = None
    # Plan 06 C1 — Agent Mode (full delegation): the AI plans symbol/size/
    # cadence/confidence each cycle inside a user budget.
    mode: str = "manual"
    budget_usd: Optional[float] = None

    @field_validator("risk_level")
    @classmethod
    def _risk_level(cls, v):
        v = (v or "").strip().lower()
        if v and v not in RISK_LEVEL_PRESETS:
            raise ValueError(f"risk_level must be one of {list(RISK_LEVEL_PRESETS)} or empty")
        return v or None

    @field_validator("mode")
    @classmethod
    def _mode(cls, v):
        v = (v or "manual").strip().lower()
        if v not in ("manual", "agent"):
            raise ValueError("mode must be manual or agent")
        return v

    @field_validator("budget_usd")
    @classmethod
    def _budget(cls, v):
        if v is not None and (v < 100 or v > 1_000_000):
            raise ValueError("budget_usd must be between 100 and 1,000,000")
        return v

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
        if v not in VALID_MARKETS:
            raise ValueError(f"market must be one of {VALID_MARKETS}")
        return v

    @field_validator("provider")
    @classmethod
    def _provider(cls, v):
        v = (v or "").strip().lower()
        if v not in ALLOWED_PROVIDERS:
            raise ValueError(f"provider must be one of {[p for p in ALLOWED_PROVIDERS if p]} or empty")
        return v or None

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

    @field_validator("size_usd")
    @classmethod
    def _size(cls, v: float) -> float:
        if v <= 0 or v > 1_000_000:
            raise ValueError("size_usd must be positive and <= 1,000,000")
        return v

    @field_validator("account_type")
    @classmethod
    def _account(cls, v: str) -> str:
        v = (v or "").strip().lower()
        if v not in ("simulator", "real"):
            raise ValueError("account_type must be simulator or real")
        return v

    @field_validator("lang")
    @classmethod
    def _lang(cls, v: str) -> str:
        return "th" if (v or "en").lower().startswith("th") else "en"


def _auth(authorization: Optional[str]):
    agent = _get_agent_by_token(_extract_token(authorization))
    if not agent:
        raise HTTPException(status_code=401, detail="Invalid token")
    return agent


def _apply_risk_level(agent_id: int, risk_level: Optional[str]):
    """B2: propagate a chosen risk level into the agent's risk_limits exit
    profile. Returns the applied limits (or None when no level was chosen).
    Fail-soft: a limits write problem must not fail rule creation."""
    preset = RISK_LEVEL_PRESETS.get(risk_level or "")
    if not preset:
        return None
    try:
        from risk_engine import put_risk_limits
        return put_risk_limits(agent_id, dict(preset))
    except Exception:  # noqa: BLE001
        return None


def register_automation_routes(app: FastAPI, ctx: RouteContext) -> None:

    @app.get("/api/automation/configs")
    async def list_configs(authorization: str = Header(None)):
        agent = _auth(authorization)
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM automation_configs WHERE agent_id = ? ORDER BY id DESC",
                (agent["id"],),
            )
            return {"configs": [dict(r) for r in cursor.fetchall()]}
        finally:
            conn.close()

    @app.post("/api/automation/configs")
    async def create_config(data: AutomationConfigIn, authorization: str = Header(None)):
        agent = _auth(authorization)
        # Agent-mode invariants: a budget is required, execution is on (that is
        # the point of delegation), and only the simulator account is allowed.
        auto_execute = data.auto_execute
        account_type = data.account_type
        if data.mode == "agent":
            if not data.budget_usd:
                raise HTTPException(status_code=400,
                                    detail="agent mode requires budget_usd (100..1,000,000)")
            auto_execute = True
            account_type = "simulator"
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            begin_write_transaction(cursor)
            cursor.execute(
                """INSERT INTO automation_configs
                   (agent_id, symbol, market, provider, interval_minutes, min_confidence,
                    size_usd, auto_execute, account_type, enabled, lang, risk_level,
                    mode, budget_usd)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (agent["id"], data.symbol, data.market, data.provider, data.interval_minutes,
                 data.min_confidence, data.size_usd, 1 if auto_execute else 0,
                 account_type, 1 if data.enabled else 0, data.lang, data.risk_level,
                 data.mode, data.budget_usd),
            )
            config_id = cursor.lastrowid
            conn.commit()
        finally:
            conn.close()
        applied_limits = _apply_risk_level(agent["id"], data.risk_level)
        return {"id": config_id, "ok": True, "risk_limits": applied_limits}

    @app.put("/api/automation/configs/{config_id}")
    async def update_config(config_id: int, data: AutomationConfigIn, authorization: str = Header(None)):
        agent = _auth(authorization)
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM automation_configs WHERE id = ? AND agent_id = ?",
                           (config_id, agent["id"]))
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail="Rule not found")
            begin_write_transaction(cursor)
            cursor.execute(
                """UPDATE automation_configs SET symbol=?, market=?, provider=?, interval_minutes=?,
                   min_confidence=?, size_usd=?, auto_execute=?, account_type=?, enabled=?, lang=?,
                   risk_level=?, mode=?, budget_usd=?
                   WHERE id=? AND agent_id=?""",
                (data.symbol, data.market, data.provider, data.interval_minutes,
                 data.min_confidence, data.size_usd, 1 if data.auto_execute else 0,
                 data.account_type, 1 if data.enabled else 0, data.lang, data.risk_level,
                 data.mode, data.budget_usd,
                 config_id, agent["id"]),
            )
            conn.commit()
        finally:
            conn.close()
        applied_limits = _apply_risk_level(agent["id"], data.risk_level)
        return {"ok": True, "risk_limits": applied_limits}

    @app.delete("/api/automation/configs/{config_id}")
    async def delete_config(config_id: int, authorization: str = Header(None)):
        agent = _auth(authorization)
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            begin_write_transaction(cursor)
            cursor.execute("DELETE FROM automation_configs WHERE id = ? AND agent_id = ?",
                           (config_id, agent["id"]))
            deleted = cursor.rowcount
            conn.commit()
            if not deleted:
                raise HTTPException(status_code=404, detail="Rule not found")
            return {"ok": True}
        finally:
            conn.close()

    @app.get("/api/automation/agent-decisions")
    async def list_agent_decisions(config_id: Optional[int] = None, limit: int = 30,
                                   authorization: str = Header(None)):
        """Agent-mode decision feed: what the planner chose each cycle and why."""
        agent = _auth(authorization)
        limit = max(1, min(limit, 100))
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            if config_id:
                cursor.execute(
                    """SELECT * FROM agent_mode_decisions
                       WHERE agent_id = ? AND config_id = ?
                       ORDER BY id DESC LIMIT ?""",
                    (agent["id"], config_id, limit))
            else:
                cursor.execute(
                    "SELECT * FROM agent_mode_decisions WHERE agent_id = ? ORDER BY id DESC LIMIT ?",
                    (agent["id"], limit))
            return {"decisions": [dict(r) for r in cursor.fetchall()]}
        finally:
            conn.close()

    @app.get("/api/automation/runs")
    async def list_runs(config_id: Optional[int] = None, limit: int = 30,
                        authorization: str = Header(None)):
        agent = _auth(authorization)
        limit = max(1, min(limit, 100))
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            if config_id:
                cursor.execute(
                    """SELECT * FROM automation_runs WHERE agent_id = ? AND config_id = ?
                       ORDER BY id DESC LIMIT ?""",
                    (agent["id"], config_id, limit),
                )
            else:
                cursor.execute(
                    "SELECT * FROM automation_runs WHERE agent_id = ? ORDER BY id DESC LIMIT ?",
                    (agent["id"], limit),
                )
            return {"runs": [dict(r) for r in cursor.fetchall()]}
        finally:
            conn.close()
