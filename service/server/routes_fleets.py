"""Fleet API (Plan 14 §9.1) — agent bearer auth, cross-tenant 404.

Raise sites stay English; i18n happens at the routes.py boundary
(i18n_errors), and async failure states (build_failed, partial:k/N,
replenishing:k/N) surface through fleet status_reason + the client-side
reasonLabel map — never through the exception boundary (no request is in
flight when the worker discovers them).
"""

from __future__ import annotations

import json as _json
from typing import Any, Optional

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, field_validator

import fleet_planner
import trading_runs
from database import get_db_connection
from routes_shared import RouteContext
from services import _get_agent_by_token
from utils import _extract_token

VALID_RISK = ("stable", "balanced", "aggressive", "extreme")


class FleetIn(BaseModel):
    n_runs: int
    total_budget_usd: Optional[float] = None
    risk_appetite: str = "balanced"
    markets: Optional[list[str]] = None
    provider: Optional[str] = None
    lang: str = "en"
    warn_loss_frac: float = 0.30
    stop_loss_frac: float = 0.40
    # Fleet goal: bank everything and start the same trading again at this
    # gain (fraction of total budget). None = run until the user stops.
    profit_target_frac: Optional[float] = None
    idempotency_key: Optional[str] = None
    name: Optional[str] = None
    leverage: Optional[float] = None   # None ⇒ auto by tier; 1–10 ⇒ override
    # Plan 23: 'short' = today's intraday behavior (default); 'swing' = the
    # US-stock overnight-hold archetype (market scope pinned server-side).
    archetype: str = "short"

    @field_validator("archetype")
    @classmethod
    def _archetype(cls, v: str) -> str:
        v = (v or "short").strip().lower()
        if v not in ("short", "swing"):
            raise ValueError("archetype must be short|swing")
        return v

    @field_validator("risk_appetite")
    @classmethod
    def _risk(cls, v: str) -> str:
        v = (v or "balanced").strip().lower()
        if v not in VALID_RISK:
            raise ValueError(f"risk_appetite must be one of {VALID_RISK}")
        return v

    @field_validator("markets")
    @classmethod
    def _markets(cls, v):
        if not v:
            return None
        import markets
        autom = set(markets.automatable_markets())
        cleaned = [m.strip().lower() for m in v if m and m.strip()]
        bad = [m for m in cleaned if m not in autom]
        if bad:
            raise ValueError(f"markets must be within {sorted(autom)}")
        return cleaned

    @field_validator("lang")
    @classmethod
    def _lang(cls, v: str) -> str:
        from analysis_agents import normalize_lang
        return normalize_lang(v)


class RailsIn(BaseModel):
    warn_loss_frac: Optional[float] = None
    stop_loss_frac: Optional[float] = None
    # The take-profit GOAL is not a risk rail: raising it just runs longer,
    # lowering it banks sooner, 0/null clears it. So it is freely editable
    # while the fleet is live — the tighten-only rule applies to the loss
    # rails only.
    profit_target_frac: Optional[float] = None
    confirm: bool = False


class StopIn(BaseModel):
    flatten: bool = True


class SizeIn(BaseModel):
    n_runs: int


def _auth(authorization: Optional[str]) -> dict:
    agent = _get_agent_by_token(_extract_token(authorization))
    if not agent:
        raise HTTPException(status_code=401, detail="Invalid token")
    return agent


def _fleet_or_404(fleet_id: int, agent: dict) -> dict:
    """Fleet ownership is per USER (the uniqueness guard is user-scoped), so
    any agent linked to the same user may see and control the fleet — without
    this, the panel refuses a launch for a fleet the caller cannot even see
    (hit live on 2026-07-21: fleet made by agent A, user browsing as agent B).
    Cross-USER access stays a 404, never a leak."""
    fleet = fleet_planner.get_fleet(fleet_id)
    if not fleet:
        raise HTTPException(status_code=404, detail="Fleet not found")
    if fleet["agent_id"] != agent["id"]:
        caller_user = agent.get("user_id")
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT user_id FROM agents WHERE id = ?",
                           (fleet["agent_id"],))
            row = cursor.fetchone()
        finally:
            conn.close()
        owner_user = row["user_id"] if row else None
        if not caller_user or owner_user != caller_user:
            raise HTTPException(status_code=404, detail="Fleet not found")
    return fleet


def _default_budget(agent: dict) -> float:
    """Tier-defaulted budget (requirement d: the user sets only N; budget is
    pre-filled and editable): half the agent's cash, clamped to bounds."""
    lo, hi = fleet_planner.FLEET_BOUNDS["total_budget_usd"]
    cash = float(agent.get("cash") or 0)
    return max(lo, min(hi, round(cash * 0.5, 2)))


def _public_fleet(fleet: dict) -> dict:
    out = dict(fleet)
    out.pop("claimed_by", None)
    out.pop("claim_expires_at", None)
    out.pop("active_fleet_key", None)
    out.pop("idempotency_key", None)
    # The AI's slot recommendation for this budget — the resize confirm
    # dialog shows it so the user decides with the fee evidence in view.
    # Clamped to the plan cap (live 2026-08-12: the dialog recommended 25 to
    # a plan capped at 10, and following it could only ever be denied).
    try:
        rec = fleet_planner.recommended_max_slots(
            float(fleet.get("total_budget_usd") or 0))
        import entitlements
        from database import get_db_connection as _gdc
        _conn = _gdc()
        try:
            _, _limits = entitlements.limits_for_agent(
                _conn.cursor(), int(fleet["agent_id"]))
        finally:
            _conn.close()
        _cap = int(_limits.get("max_fleet_size") or 0)
        out["recommended_max_n_runs"] = min(rec, _cap) if _cap > 0 else rec
    except Exception:  # noqa: BLE001
        out["recommended_max_n_runs"] = None
    try:
        out["market_scope"] = _json.loads(out.pop("market_scope_json") or "null")
    except Exception:  # noqa: BLE001
        out["market_scope"] = None
    return out


FLEET_INDEX_BASE = 100.0


def fleet_index(fleet: dict, equity: "dict | None") -> "dict | None":
    """This fleet's own performance, rebased to 100 at launch.

    The account total answers "am I up?"; it cannot answer "is THIS sleeve
    working?" — an N-symbol fleet is a distinct bet with its own budget, and
    its result is invisible inside a six-figure account balance. Rebasing to
    100 makes fleets comparable to each other and to a benchmark regardless
    of how much money each was given.

    Built on marked_equity (budget + Σ P&L over every run ever attributed to
    the fleet, including stopped members and positions_held zombies), so a
    retired run's result stays in the index instead of vanishing with it.
    Returns None when equity is unreadable — the caller must not invent a
    number, same fail-closed rule the supervisor uses.
    """
    if not equity or not equity.get("ok"):
        return None
    try:
        budget = float(fleet.get("total_budget_usd") or 0)
        eq = float(equity.get("equity") or 0)
    except (TypeError, ValueError):
        return None
    if budget <= 0:
        return None
    pnl = eq - budget
    return {
        "base": FLEET_INDEX_BASE,
        "value": round(FLEET_INDEX_BASE * eq / budget, 2),
        "pnl_usd": round(pnl, 2),
        "pnl_pct": round(100.0 * pnl / budget, 2),
        "budget_usd": round(budget, 2),
        "equity_usd": round(eq, 2),
        "since": fleet.get("started_at") or fleet.get("created_at"),
    }


def _members_public(fleet_id: int) -> list[dict]:
    members = []
    for m in fleet_planner.list_members(fleet_id):
        cfg: dict[str, Any] = {}
        try:
            cfg = _json.loads(m.get("config_snapshot_json") or "{}")
        except Exception:  # noqa: BLE001
            pass
        # Plan 15 overnight finding O2 (2026-07-23): realized alone is the
        # FEE ledger until the first close — a card showing it reads "loss"
        # on every young run even while its position is winning (Henry read
        # a +$9-unrealized fleet as "100% lost"). Ship the marked total too.
        unrealized = None
        total = m.get("realized_pnl_usd")
        try:
            import run_engine
            pnl = run_engine.compute_run_pnl(m)
            unrealized = pnl.get("unrealized")
            total = pnl.get("total")
        except Exception:  # noqa: BLE001
            pass
        members.append({
            "run_id": m["id"], "symbol": m["symbol"], "market": m["market"],
            "market_type": m["market_type"], "status": m["status"],
            "status_reason": m.get("status_reason"),
            "paused_reason": m.get("paused_reason"),
            "run_budget_usd": cfg.get("run_budget_usd"),
            "thesis": cfg.get("thesis"),
            "realized_pnl_usd": m.get("realized_pnl_usd"),
            "unrealized_pnl_usd": unrealized,
            "total_pnl_usd": total,
        })
    return members


def register_fleet_routes(app: FastAPI, ctx: RouteContext) -> None:

    @app.get("/api/entitlements/me")
    async def entitlements_me(authorization: str = Header(None)):
        """Tier echo — the Full Auto N stepper must not learn its cap from a
        403 round-trip."""
        agent = _auth(authorization)
        from entitlements import limits_for_agent, plan_code_for_user
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            user_id, limits = limits_for_agent(cursor, agent["id"])
            plan = plan_code_for_user(cursor, user_id)
            conn.commit()
        finally:
            conn.close()
        return {"plan": plan, "linked_user": user_id is not None,
                "max_fleet_size": limits.get("max_fleet_size", 0),
                "max_concurrent_runs": limits.get("max_concurrent_runs", 0),
                "max_bet_usd": limits.get("max_bet_usd", 0.0),
                "default_budget_usd": _default_budget(agent)}

    @app.post("/api/fleets")
    async def create_fleet(data: FleetIn, authorization: str = Header(None)):
        agent = _auth(authorization)
        budget = data.total_budget_usd
        if budget is None:
            budget = _default_budget(agent)
        try:
            fleet_id = fleet_planner.create_fleet(
                agent["id"], data.n_runs, budget,
                risk_appetite=data.risk_appetite, market_scope=data.markets,
                provider=data.provider, lang=data.lang,
                warn_loss_frac=data.warn_loss_frac,
                stop_loss_frac=data.stop_loss_frac,
                profit_target_frac=data.profit_target_frac,
                idempotency_key=data.idempotency_key, name=data.name,
                leverage=data.leverage, archetype=data.archetype)
        except trading_runs.EntitlementDenied as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        except fleet_planner.FleetConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return {"id": fleet_id, "ok": True,
                "fleet": _public_fleet(_fleet_or_404(fleet_id, agent))}

    @app.post("/api/fleets/{fleet_id}/start")
    async def start_fleet(fleet_id: int, authorization: str = Header(None)):
        agent = _auth(authorization)
        owner_id = _fleet_or_404(fleet_id, agent)["agent_id"]
        try:
            fleet = fleet_planner.start_fleet(fleet_id, owner_id)
        except trading_runs.EntitlementDenied as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        return {"ok": True, "fleet": _public_fleet(fleet)}

    @app.get("/api/fleets")
    async def list_fleets(authorization: str = Header(None)):
        agent = _auth(authorization)
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            if agent.get("user_id"):
                cursor.execute(
                    "SELECT f.* FROM fleets f JOIN agents a ON a.id = f.agent_id "
                    "WHERE a.user_id = ? ORDER BY f.id DESC LIMIT 20",
                    (agent["user_id"],))
            else:
                cursor.execute(
                    "SELECT * FROM fleets WHERE agent_id = ? ORDER BY id DESC "
                    "LIMIT 20", (agent["id"],))
            fleets = [dict(r) for r in cursor.fetchall()]
        finally:
            conn.close()
        # The index rides along on the list so a fleet card can show its own
        # result without a second round trip per fleet. Non-terminal only —
        # marked_equity replays every member's P&L, which is not worth paying
        # for on an archived fleet nobody is watching.
        out = []
        for f in fleets:
            pub = _public_fleet(f)
            if f.get("status") not in ("stopped", "archived"):
                try:
                    pub["index"] = fleet_index(f, fleet_planner.marked_equity(f))
                except Exception:  # noqa: BLE001 — a stats read never breaks the list
                    pub["index"] = None
            out.append(pub)
        return {"fleets": out}

    @app.get("/api/fleets/{fleet_id}")
    async def get_fleet(fleet_id: int, authorization: str = Header(None)):
        agent = _auth(authorization)
        fleet = _fleet_or_404(fleet_id, agent)
        eq = None
        try:
            eq = fleet_planner.marked_equity(fleet)
        except Exception:  # noqa: BLE001
            eq = None
        return {"fleet": _public_fleet(fleet),
                "members": _members_public(fleet_id),
                "equity": eq,
                "index": fleet_index(fleet, eq)}

    @app.put("/api/fleets/{fleet_id}/rails")
    async def edit_rails(fleet_id: int, data: RailsIn,
                         authorization: str = Header(None)):
        """TIGHTEN-ONLY while non-terminal (the runs stop-conditions pattern).
        A new stop at/inside the current drawdown 409s without confirm:true;
        any warn change rebases the episode latch so the tightened warning
        can actually fire (§6.5.1)."""
        agent = _auth(authorization)
        fleet = _fleet_or_404(fleet_id, agent)
        if fleet["status"] == fleet_planner.STATUS_STOPPED:
            raise HTTPException(status_code=409,
                                detail="fleet already stopped")
        if data.profit_target_frac is not None:
            goal = float(data.profit_target_frac)
            t_lo, t_hi = fleet_planner.FLEET_BOUNDS["profit_target_goal_bounds"]
            if goal and not (t_lo <= goal <= t_hi):
                raise HTTPException(
                    status_code=400,
                    detail=f"profit_target_frac must be between {t_lo} and {t_hi}")
            fleet_planner.set_profit_target(fleet_id, goal or None)
            fleet_planner.emit_fleet_event(fleet_id, "goal_changed",
                                           {"profit_target_frac": goal or None})
            fleet = _fleet_or_404(fleet_id, agent)
            if data.warn_loss_frac is None and data.stop_loss_frac is None:
                return {"ok": True, "profit_target_frac": fleet["profit_target_frac"]}
        warn = data.warn_loss_frac if data.warn_loss_frac is not None \
            else float(fleet["warn_loss_frac"])
        stop = data.stop_loss_frac if data.stop_loss_frac is not None \
            else float(fleet["stop_loss_frac"])
        if not (0 < warn < stop <= 0.40):
            raise HTTPException(
                status_code=400,
                detail="rails must satisfy 0 < warn < stop <= 0.40")
        if fleet["status"] != fleet_planner.STATUS_DRAFT:
            if warn > float(fleet["warn_loss_frac"]) or \
                    stop > float(fleet["stop_loss_frac"]):
                raise HTTPException(
                    status_code=400,
                    detail="rails are tighten-only while the fleet is active")
            try:
                eq = fleet_planner.marked_equity(fleet)
                total = float(fleet["total_budget_usd"])
                loss_frac = max(0.0, (total - eq["equity"]) / total) \
                    if total > 0 and eq["ok"] else 0.0
            except Exception:  # noqa: BLE001
                loss_frac = 0.0
            if loss_frac >= stop and not data.confirm:
                raise HTTPException(
                    status_code=409,
                    detail="this stop level would stop the fleet immediately "
                           "— confirm to proceed")
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            from database import begin_write_transaction
            begin_write_transaction(cursor)
            cursor.execute(
                """UPDATE fleets SET warn_loss_frac = ?, stop_loss_frac = ?,
                   warn_latched_at = NULL, warn_acked_at = NULL,
                   warn_level_frac = NULL
                   WHERE id = ? AND agent_id = ?""",
                (warn, stop, fleet_id, fleet["agent_id"]))
            conn.commit()
        finally:
            conn.close()
        fleet_planner.emit_fleet_event(fleet_id, "rails_changed",
                                       {"warn": warn, "stop": stop,
                                        "confirm": data.confirm})
        return {"ok": True,
                "fleet": _public_fleet(_fleet_or_404(fleet_id, agent))}

    @app.put("/api/fleets/{fleet_id}/size")
    async def edit_size(fleet_id: int, data: SizeIn,
                        authorization: str = Header(None)):
        """Change the slot target of a live fleet (owner ask 2026-08-08).
        Raising re-checks the plan cap and the supervisor grows toward the
        new N on its next pass; lowering drains — excess slots retire only
        as they empty, a live position is never touched."""
        agent = _auth(authorization)
        fleet = _fleet_or_404(fleet_id, agent)
        if fleet["status"] == fleet_planner.STATUS_STOPPED:
            raise HTTPException(status_code=409,
                                detail="fleet already stopped")
        try:
            fleet_planner.set_fleet_size(fleet_id, data.n_runs)
        except trading_runs.EntitlementDenied as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return {"ok": True,
                "fleet": _public_fleet(_fleet_or_404(fleet_id, agent))}

    @app.post("/api/fleets/{fleet_id}/resume-warning")
    async def resume_warning(fleet_id: int, authorization: str = Header(None)):
        """Acknowledge the −30% warning — 'continuing is your responsibility'."""
        agent = _auth(authorization)
        fleet = _fleet_or_404(fleet_id, agent)
        try:
            from fleet_supervisor import ack_warning
            result = ack_warning(fleet_id, fleet["agent_id"])
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        return {"ok": True, **result}

    @app.post("/api/fleets/{fleet_id}/pause")
    async def pause_fleet(fleet_id: int, authorization: str = Header(None)):
        agent = _auth(authorization)
        owner_id = _fleet_or_404(fleet_id, agent)["agent_id"]
        return {"ok": True, **fleet_planner.pause_fleet(fleet_id, owner_id)}

    @app.post("/api/fleets/{fleet_id}/resume")
    async def resume_fleet(fleet_id: int, authorization: str = Header(None)):
        agent = _auth(authorization)
        owner_id = _fleet_or_404(fleet_id, agent)["agent_id"]
        return {"ok": True, **fleet_planner.resume_fleet(fleet_id, owner_id)}

    @app.post("/api/fleets/{fleet_id}/stop")
    async def stop_fleet(fleet_id: int, data: StopIn = None,  # type: ignore[assignment]
                         authorization: str = Header(None)):
        agent = _auth(authorization)
        owner_id = _fleet_or_404(fleet_id, agent)["agent_id"]
        flatten = data.flatten if data is not None else True
        return {"ok": True,
                **fleet_planner.request_stop_fleet(fleet_id, owner_id, flatten)}

    @app.delete("/api/fleets/{fleet_id}")
    async def delete_fleet(fleet_id: int, authorization: str = Header(None)):
        agent = _auth(authorization)
        owner_id = _fleet_or_404(fleet_id, agent)["agent_id"]
        try:
            fleet_planner.delete_fleet(fleet_id, owner_id)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        return {"ok": True}

    @app.get("/api/fleets/{fleet_id}/events")
    async def fleet_events(fleet_id: int, after_seq: int = 0, limit: int = 100,
                           authorization: str = Header(None)):
        agent = _auth(authorization)
        _fleet_or_404(fleet_id, agent)
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT seq, ts, event_type, payload FROM fleet_events
                   WHERE fleet_id = ? AND seq > ? ORDER BY seq LIMIT ?""",
                (fleet_id, after_seq, max(1, min(limit, 500))))
            events = []
            for r in cursor.fetchall():
                ev = dict(r)
                try:
                    ev["payload"] = _json.loads(ev["payload"] or "{}")
                except Exception:  # noqa: BLE001
                    ev["payload"] = {}
                events.append(ev)
        finally:
            conn.close()
        return {"events": events}

    @app.get("/api/fleet/research")
    async def fleet_research(authorization: str = Header(None)):
        """The 'why these symbols' panel — latest global batch, ranked."""
        _auth(authorization)
        import symbol_research
        return symbol_research.latest_batch_payload()
