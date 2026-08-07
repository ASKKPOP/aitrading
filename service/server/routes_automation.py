"""Automation routes (Target 3) — CRUD for per-agent AI auto-trading rules + run history.

    GET    /api/automation/configs        list my rules
    POST   /api/automation/configs        create a rule
    PUT    /api/automation/configs/{id}   update a rule (partial)
    DELETE /api/automation/configs/{id}   delete a rule
    GET    /api/automation/runs           recent run history (optionally ?config_id=)
    GET    /api/automation/ai-analysis    my desk cycles on the 30-minute grid
"""

from __future__ import annotations

import json as _json
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, field_validator

from automation import VALID_MARKETS
from database import begin_write_transaction, get_db_connection
from desk_cycles import CYCLE_MINUTES, DEFAULT_CYCLES, agent_cycles
from i18n_errors import lang_from_request
from market_i18n import localize_desk_cycles
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
    # 0.16, not 0.15: every preset must clear order_params.RR_FLOOR (2.0), and
    # stable/balanced both sit exactly on it. At 0.15 this one graded 1.875 and
    # the rr_floor gate refused EVERY entry that deferred its bracket to the
    # deterministic path — silently, for anyone who picked this profile
    # (prod runs 908/923 on 2026-08-02, run 937 on the 3rd).
    # test_every_preset_can_clear_the_house_rr_floor guards the invariant.
    "aggressive": {"stop_loss_pct": 0.08, "take_profit_pct": 0.16,
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
    # Plan 06 C3 — trading-window schedule (days/hours/timezone)
    schedule: Optional[dict] = None
    # Plan 21 P5 — live promotion ticket (from the hermes work-package's
    # trade-ticket APPROVED contract): promoting a rule TO account_type
    # 'live' requires the caller to RE-TYPE symbol, the word 'live', and
    # size_usd here. It gates ENABLEMENT only — order-time live gating
    # (gateway configured, T&Cs consent, broker allowlist, caps) is
    # unchanged in execution/gateway.
    live_confirm: Optional[dict] = None

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

    @field_validator("schedule")
    @classmethod
    def _schedule(cls, v):
        if v is None:
            return None
        from schedule import parse_schedule
        try:
            return parse_schedule(v)
        except ValueError as exc:
            raise ValueError(str(exc))

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
        """simulator | shadow | live decides where a fill lands. 'real' is the
        pre-gateway spelling of live and is normalized so existing clients and
        stored rules keep working."""
        from execution.gateway import ACCOUNT_TYPES, normalize_account_type
        v = (v or "").strip().lower()
        if v not in ACCOUNT_TYPES and v != "real":
            raise ValueError(f"account_type must be one of {', '.join(ACCOUNT_TYPES)}")
        return normalize_account_type(v)

    @field_validator("lang")
    @classmethod
    def _lang(cls, v: str) -> str:
        from analysis_agents import normalize_lang
        return normalize_lang(v)


def _auth(authorization: Optional[str]):
    agent = _get_agent_by_token(_extract_token(authorization))
    if not agent:
        raise HTTPException(status_code=401, detail="Invalid token")
    return agent


def _deny_live_without_confirmation(data: "AutomationConfigIn",
                                    currently_live: bool) -> None:
    """Plan 21 P5 — the shadow→live promotion ticket.

    A rule may only BECOME live when the payload re-types the three values
    that define what goes live: the symbol, the literal word 'live', and the
    per-trade size. A mismatch (or absence) is a 400 naming each bad field —
    the caller either corrects the confirmation or fixes the rule body, the
    exact demote-on-mismatch contract of the upstream trade ticket. Rules
    that are already live (edits not changing the account), simulator, and
    shadow rules pass untouched; order-time live gates are unchanged.
    """
    from execution.gateway import normalize_account_type
    if normalize_account_type(data.account_type) != "live" or currently_live:
        return
    confirm = data.live_confirm if isinstance(data.live_confirm, dict) else {}
    bad: list[str] = []
    if str(confirm.get("symbol") or "").strip().upper() != \
            (data.symbol or "").strip().upper():
        bad.append("symbol")
    if str(confirm.get("account_type") or "").strip().lower() != "live":
        bad.append("account_type")
    try:
        if abs(float(confirm.get("size_usd")) - float(data.size_usd)) > 1e-9:
            bad.append("size_usd")
    except (TypeError, ValueError):
        bad.append("size_usd")
    if bad:
        raise HTTPException(
            status_code=400,
            detail=("promoting this rule to live requires re-typed "
                    "confirmation: send live_confirm with the rule's own "
                    "values re-entered; missing or mismatched: "
                    + ", ".join(bad)))


def _deny_auto_execute_without_plan(agent_id: int) -> None:
    """Plan 10 D9: the automation engine gets the SAME entitlement gate as
    the runs engine — otherwise anyone rejected by run limits simply creates
    an auto-executing rule here instead. Env-gated (ENTITLEMENTS_ENFORCED)."""
    from entitlements import check_auto_execute
    conn = get_db_connection()
    try:
        deny = check_auto_execute(conn.cursor(), agent_id)
        conn.commit()
    finally:
        conn.close()
    if deny:
        raise HTTPException(status_code=403, detail=deny)


def _deny_rule_conflicting_active_run(agent_id: int, market: str, symbol: str) -> None:
    """Mirror of trading_runs.start_run guard #3: a run start is blocked by an
    enabled auto-executing rule on its tuple, so enabling such a rule while a
    run is ACTIVE on the tuple must be blocked too — otherwise the rule trades
    into the run's book mid-flight and run P&L attribution becomes fiction."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """SELECT id FROM trading_runs
               WHERE agent_id = ? AND market = ? AND symbol = ?
                 AND active_key IS NOT NULL""",
            (agent_id, market, symbol),
        )
        row = cursor.fetchone()
    finally:
        conn.close()
    if row:
        raise HTTPException(
            status_code=409,
            detail=f"trading run #{row['id']} is active on {symbol} ({market}) — "
                   "stop it before enabling an auto-executing rule on this symbol")


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
        else:
            _deny_live_without_confirmation(data, currently_live=False)
        if auto_execute:
            _deny_auto_execute_without_plan(agent["id"])
            if data.enabled:
                _deny_rule_conflicting_active_run(agent["id"], data.market, data.symbol)
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            begin_write_transaction(cursor)
            cursor.execute(
                """INSERT INTO automation_configs
                   (agent_id, symbol, market, provider, interval_minutes, min_confidence,
                    size_usd, auto_execute, account_type, enabled, lang, risk_level,
                    mode, budget_usd, schedule_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (agent["id"], data.symbol, data.market, data.provider, data.interval_minutes,
                 data.min_confidence, data.size_usd, 1 if auto_execute else 0,
                 account_type, 1 if data.enabled else 0, data.lang, data.risk_level,
                 data.mode, data.budget_usd,
                 _json.dumps(data.schedule) if data.schedule else None),
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
        if data.auto_execute or data.mode == "agent":
            _deny_auto_execute_without_plan(agent["id"])
        if (data.auto_execute or data.mode == "agent") and data.enabled:
            _deny_rule_conflicting_active_run(agent["id"], data.market, data.symbol)
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT id, account_type FROM automation_configs "
                           "WHERE id = ? AND agent_id = ?",
                           (config_id, agent["id"]))
            existing = cursor.fetchone()
            if not existing:
                raise HTTPException(status_code=404, detail="Rule not found")
            # Plan 21 P5: the ticket fires on the TRANSITION to live only —
            # editing an already-live rule needs no re-confirmation.
            from execution.gateway import normalize_account_type
            _deny_live_without_confirmation(
                data,
                currently_live=(normalize_account_type(
                    existing["account_type"] or "") == "live"))
            begin_write_transaction(cursor)
            cursor.execute(
                """UPDATE automation_configs SET symbol=?, market=?, provider=?, interval_minutes=?,
                   min_confidence=?, size_usd=?, auto_execute=?, account_type=?, enabled=?, lang=?,
                   risk_level=?, mode=?, budget_usd=?, schedule_json=?
                   WHERE id=? AND agent_id=?""",
                (data.symbol, data.market, data.provider, data.interval_minutes,
                 data.min_confidence, data.size_usd, 1 if data.auto_execute else 0,
                 data.account_type, 1 if data.enabled else 0, data.lang, data.risk_level,
                 data.mode, data.budget_usd,
                 _json.dumps(data.schedule) if data.schedule else None,
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
            cursor.execute("SELECT id FROM automation_configs WHERE id = ? AND agent_id = ?",
                           (config_id, agent["id"]))
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail="Rule not found")
            begin_write_transaction(cursor)
            # Child rows first: automation_runs and agent_mode_decisions carry
            # FKs to automation_configs with no ON DELETE CASCADE, so MySQL
            # (prod) rejects deleting a rule that has ever run (error 1451).
            cursor.execute("DELETE FROM agent_mode_decisions WHERE config_id = ? AND agent_id = ?",
                           (config_id, agent["id"]))
            cursor.execute("DELETE FROM automation_runs WHERE config_id = ? AND agent_id = ?",
                           (config_id, agent["id"]))
            cursor.execute("DELETE FROM automation_configs WHERE id = ? AND agent_id = ?",
                           (config_id, agent["id"]))
            conn.commit()
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

    # ── Plan 14 §6.7: account-level master control (USER-SESSION auth) ─────
    # One switch over EVERYTHING AI-automated the user owns, across every
    # linked agent: the fleet, all runs, all automation rules. Marker-stamped
    # so resume restores exactly the held set; the zero-cost pre-gate in
    # run_cycle / the fleet loop / run_rule backs the fan-out (a held account
    # cannot trade even if an object was missed here).

    @app.post("/api/automation/master")
    async def master_control(data: dict, authorization: str = Header(None)):
        from services import _get_user_by_token
        token = _extract_token(authorization)
        user = _get_user_by_token(token) if token else None
        if not user:
            raise HTTPException(status_code=401, detail="Invalid token")
        action = str((data or {}).get("action") or "").strip().lower()
        if action not in ("hold", "resume", "remove"):
            raise HTTPException(status_code=400,
                                detail="action must be hold, resume or remove")
        import fleet_planner
        import trading_runs as tr
        from database import begin_write_transaction as _bwt

        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM agents WHERE user_id = ?",
                           (user["id"],))
            agent_ids = [int(r["id"]) for r in cursor.fetchall()]
        finally:
            conn.close()

        results: dict[str, dict] = {"runs": {}, "rules": {}, "fleets": {}}
        state = "held" if action == "hold" else "active"

        if action == "hold":
            # stamp the account FIRST — the pre-gate closes the fan-out race
            conn = get_db_connection()
            try:
                cursor = conn.cursor()
                _bwt(cursor)
                cursor.execute(
                    "UPDATE users SET ai_automation_state = 'held', "
                    "ai_automation_held_at = ? WHERE id = ?",
                    (fleet_planner._now_iso(), user["id"]))
                conn.commit()
            finally:
                conn.close()
        for agent_id in agent_ids:
            conn = get_db_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM trading_runs WHERE agent_id = ? "
                               "AND status IN ('running','paused','armed')",
                               (agent_id,))
                runs = [dict(r) for r in cursor.fetchall()]
                cursor.execute("SELECT id FROM fleets WHERE agent_id = ? AND "
                               "status NOT IN ('stopped')", (agent_id,))
                fleets = [int(r["id"]) for r in cursor.fetchall()]
            finally:
                conn.close()

            for run in runs:
                rid = run["id"]
                try:
                    if action == "hold":
                        if run["status"] == "running":
                            tr.pause_run(rid, agent_id, reason="master_hold",
                                         paused_marker="master_hold")
                            results["runs"][rid] = "held"
                        else:
                            # armed runs STAY armed — _control_armed blocks
                            # the start and suspends the timeout clock
                            results["runs"][rid] = run["status"]
                    elif action == "resume":
                        if run["status"] == "paused" and \
                                (run.get("paused_reason") or "") == "master_hold":
                            # a warn-latched fleet's members convert to the
                            # drawdown marker instead of waking (§6.5.1)
                            latched = False
                            if run.get("fleet_id"):
                                fl = fleet_planner.get_fleet(run["fleet_id"])
                                latched = bool(fl and fl.get("warn_latched_at")
                                               and not fl.get("warn_acked_at"))
                            if latched:
                                conn = get_db_connection()
                                try:
                                    cursor = conn.cursor()
                                    _bwt(cursor)
                                    cursor.execute(
                                        "UPDATE trading_runs SET paused_reason "
                                        "= 'drawdown_warning' WHERE id = ?",
                                        (rid,))
                                    conn.commit()
                                finally:
                                    conn.close()
                                results["runs"][rid] = "still_warned"
                            else:
                                tr.resume_run(rid, agent_id)
                                results["runs"][rid] = "running"
                        else:
                            results["runs"][rid] = "not_held"
                    else:  # remove
                        if run["status"] == "armed":
                            tr._transition(rid, agent_id, ("armed",), "stopped",
                                           "user_master_remove",
                                           clear_active_key=True)
                        else:
                            tr.request_stop(rid, agent_id, flatten=True)
                        results["runs"][rid] = "stopping"
                except Exception as exc:  # noqa: BLE001
                    results["runs"][rid] = f"error: {exc}"

            conn = get_db_connection()
            try:
                cursor = conn.cursor()
                _bwt(cursor)
                if action == "hold":
                    cursor.execute(
                        "UPDATE automation_configs SET enabled = 0, "
                        "held_by_master = 1 WHERE agent_id = ? AND enabled = 1",
                        (agent_id,))
                elif action == "resume":
                    cursor.execute(
                        "UPDATE automation_configs SET enabled = 1, "
                        "held_by_master = 0 WHERE agent_id = ? AND "
                        "held_by_master = 1", (agent_id,))
                else:
                    cursor.execute(
                        "UPDATE automation_configs SET enabled = 0, "
                        "held_by_master = 0 WHERE agent_id = ?", (agent_id,))
                results["rules"][agent_id] = cursor.rowcount
                conn.commit()
            finally:
                conn.close()

            for fleet_id in fleets:
                try:
                    if action == "hold":
                        fleet_planner._update_master_hold(fleet_id, True)
                        results["fleets"][fleet_id] = "held"
                    elif action == "resume":
                        fleet_planner._update_master_hold(fleet_id, False)
                        results["fleets"][fleet_id] = "resumed"
                    else:
                        fleet_planner.request_stop_fleet(fleet_id, agent_id,
                                                         flatten=True)
                        fleet_planner._set_status(
                            fleet_id, fleet_planner._NON_TERMINAL,
                            fleet_planner.STATUS_STOPPING, "user_master_remove")
                        results["fleets"][fleet_id] = "stopping"
                except Exception as exc:  # noqa: BLE001
                    results["fleets"][fleet_id] = f"error: {exc}"

        if action != "hold":
            conn = get_db_connection()
            try:
                cursor = conn.cursor()
                _bwt(cursor)
                cursor.execute(
                    "UPDATE users SET ai_automation_state = ?, "
                    "ai_automation_held_at = NULL WHERE id = ?",
                    (state, user["id"]))
                conn.commit()
            finally:
                conn.close()
        return {"ok": True, "action": action, "results": results}

    @app.get("/api/automation/master")
    async def master_state(authorization: str = Header(None)):
        from services import _get_user_by_token
        token = _extract_token(authorization)
        user = _get_user_by_token(token) if token else None
        if not user:
            raise HTTPException(status_code=401, detail="Invalid token")
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT ai_automation_state, ai_automation_held_at FROM users "
                "WHERE id = ?", (user["id"],))
            row = dict(cursor.fetchone() or {})
            cursor.execute(
                """SELECT COUNT(*) AS n FROM trading_runs tr
                   JOIN agents a ON a.id = tr.agent_id
                   WHERE a.user_id = ? AND tr.paused_reason = 'master_hold'""",
                (user["id"],))
            held_runs = int(cursor.fetchone()["n"] or 0)
        finally:
            conn.close()
        return {"state": row.get("ai_automation_state") or "active",
                "held_at": row.get("ai_automation_held_at"),
                "held_runs": held_runs}

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

    @app.get("/api/automation/ai-analysis")
    async def ai_analysis(request: Request, cycles: int = DEFAULT_CYCLES,
                          end_ms: Optional[int] = None,
                          authorization: str = Header(None)):
        """The signed-in agent's desk cycles on the fixed 30-minute grid.

        Composed on read from the journal Sooppiy AI already writes each
        cycle — no separate analysis pass, so the list is complete for the
        whole window whether or not the owner was watching.

        `end_ms` (epoch milliseconds) ends the window somewhere other than
        now, which is how the panel's date filter asks for a past day. The
        caller sends it because the DAY is the caller's — the grid is UTC and
        the reader's day is not, and only the browser knows the offset.

        The free text comes back in the request's Accept-Language: gate-skip
        reasons from the deterministic catalogue, the desk's written report
        from the cached translator (English on a cache miss, localized on the
        next poll — the request never waits on a model)."""
        agent = _auth(authorization)
        end = None
        if end_ms is not None:
            try:
                end = datetime.fromtimestamp(end_ms / 1000, tz=timezone.utc)
            except (OverflowError, OSError, ValueError):
                raise HTTPException(status_code=400, detail="invalid end_ms")
        rows = agent_cycles(agent["id"], cycles, now=end)
        return {"cycle_minutes": CYCLE_MINUTES,
                "cycles": localize_desk_cycles(
                    rows, lang_from_request(request.headers))}
