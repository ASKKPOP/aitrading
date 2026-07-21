"""
routes_admin_manage.py — the extended manager-console API.

Member management
  GET  /api/admin/members/{user_id}             full member detail
  POST /api/admin/members/{user_id}/status      suspend / reactivate

Paid membership
  GET  /api/admin/plans                         all plans (incl. inactive)
  POST /api/admin/plans                         create a plan
  PATCH  /api/admin/plans/{code}                edit name/price/active/sort
  DELETE /api/admin/plans/{code}                delete (only if unreferenced)
  GET  /api/admin/subscriptions                 list (filter by status)
  POST /api/admin/subscriptions/grant           manually give a member a plan
  POST /api/admin/subscriptions/{id}/approve    pending → active (30 days)
  POST /api/admin/subscriptions/{id}/reject     pending → rejected
  POST /api/admin/subscriptions/{id}/extend     push expires_at out N days
  POST /api/admin/subscriptions/{id}/cancel     active/pending → cancelled
  GET  /api/admin/contracts                     enterprise contract requests
  POST /api/admin/contracts/{id}/status         new / contacted / closed

Statistics & analytics
  GET  /api/admin/stats/assets                  platform equity + top members
  GET  /api/admin/stats/positions               open-position breakdowns
  GET  /api/admin/stats/automation              run trends + success rates
  GET  /api/admin/analytics                     signups / trades / revenue

Content & leaderboard
  GET    /api/admin/discussions                 search discussions
  GET    /api/admin/discussions/{sid}/replies   replies for one discussion
  DELETE /api/admin/discussions/{sid}           delete discussion + replies
  DELETE /api/admin/replies/{reply_id}          delete a single reply
  GET    /api/admin/leaderboard                 snapshot + exclusions
  POST   /api/admin/leaderboard/exclusions      exclude an agent
  DELETE /api/admin/leaderboard/exclusions/{agent_id}
  POST   /api/admin/leaderboard/refresh         rebuild the snapshot now

Auth: admin sessions (admin_auth.require_admin); every write is audited.
Date bucketing uses substr(created_at, 1, 10) which works on both SQLite
('YYYY-MM-DD HH:MM:SS') and MySQL ISO strings ('YYYY-MM-DDTHH:MM:SSZ').
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from admin_auth import audit, require_admin
from database import get_db_connection
from leaderboard_snapshot import read_leaderboard_snapshot, refresh_leaderboard_snapshot
from routes_shared import RouteContext, utc_now_iso_z
from routes_subscriptions import SUBSCRIPTION_DAYS

logger = logging.getLogger("routes_admin_manage")

# Networks we are willing to publish a deposit address for. Free-typing this
# is how a subscriber ends up sending TRC20 funds to an ERC20 address.
SUPPORTED_USDT_NETWORKS = ("TRC20", "ERC20", "BEP20", "SOL", "POLYGON")


def _mask_address(value: str) -> str:
    """Audit entries record which address was set without pasting the whole
    string into the log on every edit."""
    value = (value or "").strip()
    if not value:
        return ""
    return value if len(value) <= 12 else f"{value[:6]}…{value[-4:]}"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def _cutoff(days: int) -> str:
    return (_now() - timedelta(days=days)).strftime("%Y-%m-%d")


class MemberStatusBody(BaseModel):
    status: str


class SubscriptionDecisionBody(BaseModel):
    note: str = ""


class SubscriptionGrantBody(BaseModel):
    email: str = ""
    user_id: int = 0
    plan_code: str
    days: int = 30
    note: str = ""


class PlanCreateBody(BaseModel):
    code: str
    name: str
    price_usd: float = 0
    contact_only: int = 0
    sort_order: int = 0


class PlanPatchBody(BaseModel):
    name: Optional[str] = None
    price_usd: Optional[float] = None
    contact_only: Optional[int] = None
    active: Optional[int] = None
    sort_order: Optional[int] = None


class SubscriptionExtendBody(BaseModel):
    days: int = 30


class ContractStatusBody(BaseModel):
    status: str


class ExclusionBody(BaseModel):
    agent_id: int
    reason: str = ""


class PaymentSettingsBody(BaseModel):
    usdt_address: str = ""
    usdt_network: str = "TRC20"
    # Optional, not "": a PUT that omits this field must leave the saved bank
    # details alone rather than silently wiping them. Send "" to clear.
    bank_transfer_info: str | None = None


class LlmSettingsBody(BaseModel):
    # None = leave unchanged; "" = clear (falls back to env, then defaults).
    local_base_url: str | None = None
    local_model: str | None = None
    brief_provider: str | None = None
    brief_model: str | None = None
    decision_provider: str | None = None
    decision_model: str | None = None


def register_admin_manage_routes(app: FastAPI, ctx: RouteContext) -> None:

    # ────────────────────────── member management ──────────────────────────

    @app.get('/api/admin/members/{user_id}')
    async def admin_member_detail(user_id: int, authorization: str = Header(None)):
        require_admin(authorization)
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT id, email, points, created_at, COALESCE(status, 'active') AS status, "
                "COALESCE(mfa_enabled, 0) AS mfa_enabled FROM users WHERE id = ?", (user_id,))
            user = cursor.fetchone()
            if not user:
                raise HTTPException(status_code=404, detail="User not found")
            detail: dict[str, Any] = {"user": dict(user)}

            cursor.execute(
                "SELECT id, name, cash, deposited, points, reputation_score, created_at "
                "FROM agents WHERE user_id = ?", (user_id,))
            agent = cursor.fetchone()
            detail["agent"] = dict(agent) if agent else None

            cursor.execute(
                "SELECT id, plan_code, status, method, reference, amount_usd, started_at, "
                "expires_at, note, created_at FROM user_subscriptions "
                "WHERE user_id = ? ORDER BY id DESC LIMIT 20", (user_id,))
            detail["subscriptions"] = [dict(r) for r in cursor.fetchall()]

            if agent:
                aid = agent["id"]
                cursor.execute(
                    "SELECT symbol, market, side, quantity, entry_price, current_price, opened_at "
                    "FROM positions WHERE agent_id = ? ORDER BY id DESC LIMIT 50", (aid,))
                detail["positions"] = [dict(r) for r in cursor.fetchall()]
                cursor.execute(
                    "SELECT signal_id, market, symbol, side, entry_price, quantity, created_at "
                    "FROM signals WHERE agent_id = ? AND message_type = 'operation' "
                    "ORDER BY id DESC LIMIT 50", (aid,))
                detail["trades"] = [dict(r) for r in cursor.fetchall()]
                cursor.execute(
                    "SELECT total_value, cash, position_value, profit, recorded_at "
                    "FROM profit_history WHERE agent_id = ? ORDER BY id DESC LIMIT 90", (aid,))
                detail["equity_history"] = [dict(r) for r in cursor.fetchall()][::-1]
            else:
                detail["positions"] = []
                detail["trades"] = []
                detail["equity_history"] = []
        finally:
            conn.close()
        return detail

    @app.post('/api/admin/members/{user_id}/status')
    async def admin_member_status(user_id: int, body: MemberStatusBody,
                                  authorization: str = Header(None)):
        admin = require_admin(authorization)
        if body.status not in ("active", "suspended"):
            raise HTTPException(status_code=400, detail="Status must be active or suspended")
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT id, email FROM users WHERE id = ?", (user_id,))
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="User not found")
            cursor.execute("UPDATE users SET status = ? WHERE id = ?", (body.status, user_id))
            if body.status == "suspended":
                # Kill live sessions so the suspension takes effect immediately.
                cursor.execute("DELETE FROM user_tokens WHERE user_id = ?", (user_id,))
            conn.commit()
        finally:
            conn.close()
        audit(admin, "member.status", f"user:{user_id}",
              f"email={row['email']} status={body.status}")
        return {"ok": True, "status": body.status}

    # ────────────────────────── paid membership ──────────────────────────

    @app.get('/api/admin/plans')
    async def admin_plans(authorization: str = Header(None)):
        require_admin(authorization)
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT id, code, name, price_usd, contact_only, active, sort_order, "
                "(SELECT COUNT(*) FROM user_subscriptions s WHERE s.plan_code = subscription_plans.code) AS subscriber_rows "
                "FROM subscription_plans ORDER BY sort_order, id")
            plans = [dict(r) for r in cursor.fetchall()]
        finally:
            conn.close()
        return {"plans": plans}

    @app.post('/api/admin/plans')
    async def admin_plan_create(body: PlanCreateBody, authorization: str = Header(None)):
        admin = require_admin(authorization)
        code = body.code.strip().lower()
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,30}", code):
            raise HTTPException(status_code=400,
                                detail="Code must be lowercase letters/digits/dashes (max 31 chars)")
        name = body.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Name required")
        if body.price_usd < 0:
            raise HTTPException(status_code=400, detail="Price cannot be negative")
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT id FROM subscription_plans WHERE code = ?", (code,))
            if cursor.fetchone():
                raise HTTPException(status_code=400, detail="Plan code already exists")
            cursor.execute(
                "INSERT INTO subscription_plans (code, name, price_usd, contact_only, sort_order) "
                "VALUES (?, ?, ?, ?, ?)",
                (code, name[:128], float(body.price_usd), 1 if body.contact_only else 0,
                 int(body.sort_order)),
            )
            conn.commit()
        finally:
            conn.close()
        audit(admin, "plan.create", f"plan:{code}",
              f"name={name} price={body.price_usd} contact_only={body.contact_only}")
        return {"ok": True, "code": code}

    @app.patch('/api/admin/plans/{code}')
    async def admin_plan_patch(code: str, body: PlanPatchBody,
                               authorization: str = Header(None)):
        admin = require_admin(authorization)
        sets: list[str] = []
        params: list[Any] = []
        changes: list[str] = []
        if body.name is not None:
            if not body.name.strip():
                raise HTTPException(status_code=400, detail="Name cannot be empty")
            sets.append("name = ?"); params.append(body.name.strip()[:128])
            changes.append(f"name={body.name.strip()[:60]}")
        if body.price_usd is not None:
            if body.price_usd < 0:
                raise HTTPException(status_code=400, detail="Price cannot be negative")
            sets.append("price_usd = ?"); params.append(float(body.price_usd))
            changes.append(f"price={body.price_usd}")
        if body.contact_only is not None:
            sets.append("contact_only = ?"); params.append(1 if body.contact_only else 0)
            changes.append(f"contact_only={1 if body.contact_only else 0}")
        if body.active is not None:
            sets.append("active = ?"); params.append(1 if body.active else 0)
            changes.append(f"active={1 if body.active else 0}")
        if body.sort_order is not None:
            sets.append("sort_order = ?"); params.append(int(body.sort_order))
            changes.append(f"sort={int(body.sort_order)}")
        if not sets:
            raise HTTPException(status_code=400, detail="Nothing to update")
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT id FROM subscription_plans WHERE code = ?", (code,))
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail="Plan not found")
            cursor.execute(
                f"UPDATE subscription_plans SET {', '.join(sets)} WHERE code = ?",
                (*params, code))
            conn.commit()
        finally:
            conn.close()
        audit(admin, "plan.update", f"plan:{code}", " ".join(changes))
        return {"ok": True}

    @app.delete('/api/admin/plans/{code}')
    async def admin_plan_delete(code: str, authorization: str = Header(None)):
        """Delete a plan nobody ever subscribed to; otherwise deactivate instead —
        subscription rows reference plan_code and history must stay readable."""
        admin = require_admin(authorization)
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT id FROM subscription_plans WHERE code = ?", (code,))
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail="Plan not found")
            cursor.execute(
                "SELECT COUNT(*) AS c FROM user_subscriptions WHERE plan_code = ?", (code,))
            if int(cursor.fetchone()["c"]):
                raise HTTPException(
                    status_code=400,
                    detail="Plan has subscription history — deactivate it instead of deleting")
            cursor.execute("DELETE FROM subscription_plans WHERE code = ?", (code,))
            conn.commit()
        finally:
            conn.close()
        audit(admin, "plan.delete", f"plan:{code}")
        return {"ok": True}

    @app.get('/api/admin/subscriptions')
    async def admin_subscriptions(status: str = "", limit: int = 50, offset: int = 0,
                                  authorization: str = Header(None)):
        require_admin(authorization)
        limit = max(1, min(limit, 200))
        where = ""
        params: list[Any] = []
        if status.strip():
            where = "WHERE s.status = ?"
            params = [status.strip()]
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                f"""
                SELECT s.id, s.user_id, u.email, s.plan_code, s.status, s.method,
                       s.reference, s.amount_usd, s.started_at, s.expires_at,
                       s.decided_by, s.decided_at, s.note, s.created_at
                FROM user_subscriptions s LEFT JOIN users u ON u.id = s.user_id
                {where} ORDER BY s.id DESC LIMIT ? OFFSET ?
                """,
                (*params, limit, max(0, offset)),
            )
            subs = [dict(r) for r in cursor.fetchall()]
            cursor.execute(
                f"SELECT COUNT(*) AS c FROM user_subscriptions s {where}", tuple(params))
            total = int(cursor.fetchone()["c"])
            cursor.execute(
                "SELECT status, COUNT(*) AS c FROM user_subscriptions GROUP BY status")
            by_status = {r["status"]: r["c"] for r in cursor.fetchall()}
        finally:
            conn.close()
        return {"subscriptions": subs, "total": total, "by_status": by_status}

    @app.post('/api/admin/subscriptions/grant')
    async def admin_subscription_grant(body: SubscriptionGrantBody,
                                       authorization: str = Header(None)):
        """Manually give a member a plan — comps, grandfathered accounts, and
        enterprise contracts (the one path that may grant contact-only plans).
        Replaces any pending/active subscription; amount 0 (not revenue)."""
        admin = require_admin(authorization)
        days = max(1, min(body.days, 3650))
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            if body.user_id:
                cursor.execute("SELECT id, email FROM users WHERE id = ?", (body.user_id,))
            elif body.email.strip():
                cursor.execute("SELECT id, email FROM users WHERE email = ?",
                               (body.email.strip().lower(),))
            else:
                raise HTTPException(status_code=400, detail="email or user_id required")
            user = cursor.fetchone()
            if not user:
                raise HTTPException(status_code=404, detail="Member not found")
            cursor.execute(
                "SELECT code FROM subscription_plans WHERE code = ? AND active = 1",
                (body.plan_code,))
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail="Unknown plan")
            now = _now()
            cursor.execute(
                "UPDATE user_subscriptions SET status = 'cancelled', decided_by = ?, "
                "decided_at = ?, note = 'replaced by manual grant' "
                "WHERE user_id = ? AND status IN ('pending', 'active')",
                (admin["id"], _iso(now), user["id"]),
            )
            replaced = cursor.rowcount
            cursor.execute(
                "INSERT INTO user_subscriptions (user_id, plan_code, status, method, amount_usd, "
                "started_at, expires_at, decided_by, decided_at, note) "
                "VALUES (?, ?, 'active', 'manual', 0, ?, ?, ?, ?, ?)",
                (user["id"], body.plan_code, _iso(now), _iso(now + timedelta(days=days)),
                 admin["id"], _iso(now), body.note[:1000]),
            )
            conn.commit()
        finally:
            conn.close()
        audit(admin, "subscription.grant", f"user:{user['id']}",
              f"email={user['email']} plan={body.plan_code} days={days} replaced={replaced}")
        return {"ok": True, "status": "active", "user_id": user["id"],
                "expires_at": _iso(now + timedelta(days=days)), "replaced": replaced}

    @app.post('/api/admin/subscriptions/{sub_id}/approve')
    async def admin_subscription_approve(sub_id: int, body: SubscriptionDecisionBody,
                                         authorization: str = Header(None)):
        admin = require_admin(authorization)
        started = _now()
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT id, user_id, plan_code, status FROM user_subscriptions WHERE id = ?",
                (sub_id,))
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Subscription not found")
            if row["status"] != "pending":
                raise HTTPException(status_code=400, detail=f"Subscription is {row['status']}, not pending")
            cursor.execute(
                "UPDATE user_subscriptions SET status = 'active', started_at = ?, expires_at = ?, "
                "decided_by = ?, decided_at = ?, note = ? WHERE id = ?",
                (_iso(started), _iso(started + timedelta(days=SUBSCRIPTION_DAYS)),
                 admin["id"], _iso(started), body.note[:1000], sub_id),
            )
            conn.commit()
        finally:
            conn.close()
        audit(admin, "subscription.approve", f"subscription:{sub_id}",
              f"user={row['user_id']} plan={row['plan_code']}")
        return {"ok": True, "status": "active"}

    @app.post('/api/admin/subscriptions/{sub_id}/reject')
    async def admin_subscription_reject(sub_id: int, body: SubscriptionDecisionBody,
                                        authorization: str = Header(None)):
        admin = require_admin(authorization)
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT id, user_id, plan_code, status FROM user_subscriptions WHERE id = ?",
                (sub_id,))
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Subscription not found")
            if row["status"] != "pending":
                raise HTTPException(status_code=400, detail=f"Subscription is {row['status']}, not pending")
            cursor.execute(
                "UPDATE user_subscriptions SET status = 'rejected', decided_by = ?, decided_at = ?, "
                "note = ? WHERE id = ?",
                (admin["id"], utc_now_iso_z(), body.note[:1000], sub_id),
            )
            conn.commit()
        finally:
            conn.close()
        audit(admin, "subscription.reject", f"subscription:{sub_id}",
              f"user={row['user_id']} plan={row['plan_code']} note={body.note[:200]}")
        return {"ok": True, "status": "rejected"}

    @app.post('/api/admin/subscriptions/{sub_id}/extend')
    async def admin_subscription_extend(sub_id: int, body: SubscriptionExtendBody,
                                        authorization: str = Header(None)):
        admin = require_admin(authorization)
        days = max(1, min(body.days, 3650))
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT id, user_id, status, expires_at FROM user_subscriptions WHERE id = ?",
                (sub_id,))
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Subscription not found")
            if row["status"] not in ("active", "expired"):
                raise HTTPException(status_code=400, detail=f"Cannot extend a {row['status']} subscription")
            base = _now()
            if row["expires_at"]:
                try:
                    prior = datetime.fromisoformat(str(row["expires_at"]).replace("Z", "+00:00"))
                    if prior.tzinfo is None:
                        prior = prior.replace(tzinfo=timezone.utc)
                    base = max(base, prior)
                except ValueError:
                    pass
            cursor.execute(
                "UPDATE user_subscriptions SET status = 'active', expires_at = ?, "
                "decided_by = ?, decided_at = ? WHERE id = ?",
                (_iso(base + timedelta(days=days)), admin["id"], utc_now_iso_z(), sub_id),
            )
            conn.commit()
        finally:
            conn.close()
        audit(admin, "subscription.extend", f"subscription:{sub_id}",
              f"user={row['user_id']} days={days}")
        return {"ok": True, "status": "active"}

    @app.post('/api/admin/subscriptions/{sub_id}/cancel')
    async def admin_subscription_cancel(sub_id: int, body: SubscriptionDecisionBody,
                                        authorization: str = Header(None)):
        admin = require_admin(authorization)
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT id, user_id, plan_code, status FROM user_subscriptions WHERE id = ?",
                (sub_id,))
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Subscription not found")
            if row["status"] not in ("active", "pending"):
                raise HTTPException(status_code=400, detail=f"Cannot cancel a {row['status']} subscription")
            cursor.execute(
                "UPDATE user_subscriptions SET status = 'cancelled', decided_by = ?, "
                "decided_at = ?, note = ? WHERE id = ?",
                (admin["id"], utc_now_iso_z(), body.note[:1000], sub_id),
            )
            conn.commit()
        finally:
            conn.close()
        audit(admin, "subscription.cancel", f"subscription:{sub_id}",
              f"user={row['user_id']} plan={row['plan_code']} note={body.note[:200]}")
        return {"ok": True, "status": "cancelled"}

    @app.get('/api/admin/contracts')
    async def admin_contracts(limit: int = 50, offset: int = 0,
                              authorization: str = Header(None)):
        require_admin(authorization)
        limit = max(1, min(limit, 200))
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT id, user_id, name, email, company, phone, message, status,
                       handled_by, handled_at, created_at
                FROM contract_requests ORDER BY id DESC LIMIT ? OFFSET ?
                """,
                (limit, max(0, offset)),
            )
            contracts = [dict(r) for r in cursor.fetchall()]
            cursor.execute("SELECT COUNT(*) AS c FROM contract_requests")
            total = int(cursor.fetchone()["c"])
        finally:
            conn.close()
        return {"contracts": contracts, "total": total}

    @app.post('/api/admin/contracts/{contract_id}/status')
    async def admin_contract_status(contract_id: int, body: ContractStatusBody,
                                    authorization: str = Header(None)):
        admin = require_admin(authorization)
        if body.status not in ("new", "contacted", "closed"):
            raise HTTPException(status_code=400, detail="Status must be new, contacted, or closed")
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT id, email FROM contract_requests WHERE id = ?", (contract_id,))
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Contract request not found")
            cursor.execute(
                "UPDATE contract_requests SET status = ?, handled_by = ?, handled_at = ? WHERE id = ?",
                (body.status, admin["id"], utc_now_iso_z(), contract_id),
            )
            conn.commit()
        finally:
            conn.close()
        audit(admin, "contract.status", f"contract:{contract_id}",
              f"email={row['email']} status={body.status}")
        return {"ok": True}

    # ────────────────────────── statistics & analytics ──────────────────────────

    @app.get('/api/admin/stats/assets')
    async def admin_stats_assets(authorization: str = Header(None)):
        require_admin(authorization)
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT COALESCE(SUM(cash), 0) AS cash, COALESCE(SUM(deposited), 0) AS deposited, "
                "COUNT(*) AS agents FROM agents")
            totals = dict(cursor.fetchone())
            cursor.execute(
                "SELECT COALESCE(SUM(quantity * COALESCE(current_price, entry_price)), 0) AS v "
                "FROM positions")
            totals["position_value"] = float(cursor.fetchone()["v"] or 0)

            # Latest equity per agent (profit_history is append-only per tick).
            cursor.execute(
                """
                SELECT a.id AS agent_id, a.name, u.email, p.total_value, p.cash,
                       p.position_value, p.profit, p.recorded_at
                FROM agents a
                LEFT JOIN users u ON u.id = a.user_id
                JOIN profit_history p ON p.id = (
                    SELECT MAX(p2.id) FROM profit_history p2 WHERE p2.agent_id = a.id)
                ORDER BY p.total_value DESC LIMIT 20
                """)
            top_members = [dict(r) for r in cursor.fetchall()]

            # Platform equity curve: daily sum of each agent's last reading that day.
            cursor.execute(
                """
                SELECT day, SUM(total_value) AS total_value, SUM(profit) AS profit
                FROM (
                    SELECT agent_id, substr(recorded_at, 1, 10) AS day,
                           MAX(id) AS last_id
                    FROM profit_history
                    WHERE recorded_at >= ?
                    GROUP BY agent_id, substr(recorded_at, 1, 10)
                ) latest
                JOIN profit_history ph ON ph.id = latest.last_id
                GROUP BY day ORDER BY day
                """,
                (_cutoff(30),),
            )
            equity_curve = [dict(r) for r in cursor.fetchall()]
        finally:
            conn.close()
        return {"totals": totals, "top_members": top_members, "equity_curve": equity_curve}

    @app.get('/api/admin/stats/positions')
    async def admin_stats_positions(authorization: str = Header(None)):
        require_admin(authorization)
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            pnl_expr = (
                "(COALESCE(current_price, entry_price) - entry_price) * quantity * "
                "CASE WHEN side IN ('buy', 'long', 'yes') THEN 1 ELSE -1 END"
            )
            cursor.execute(
                f"SELECT COUNT(*) AS open_positions, "
                f"COALESCE(SUM(quantity * COALESCE(current_price, entry_price)), 0) AS total_value, "
                f"COALESCE(SUM({pnl_expr}), 0) AS unrealized_pnl FROM positions")
            totals = dict(cursor.fetchone())
            cursor.execute(
                "SELECT market, COUNT(*) AS c, "
                "COALESCE(SUM(quantity * COALESCE(current_price, entry_price)), 0) AS value "
                "FROM positions GROUP BY market ORDER BY c DESC")
            by_market = [dict(r) for r in cursor.fetchall()]
            cursor.execute(
                "SELECT side, COUNT(*) AS c FROM positions GROUP BY side ORDER BY c DESC")
            by_side = [dict(r) for r in cursor.fetchall()]
            cursor.execute(
                "SELECT symbol, market, COUNT(*) AS c, "
                "COALESCE(SUM(quantity * COALESCE(current_price, entry_price)), 0) AS value "
                "FROM positions GROUP BY symbol, market ORDER BY value DESC LIMIT 15")
            top_symbols = [dict(r) for r in cursor.fetchall()]
            cursor.execute(
                f"""
                SELECT p.id, p.symbol, p.market, p.side, p.quantity, p.entry_price,
                       p.current_price, p.opened_at, a.name AS agent_name, u.email,
                       {pnl_expr} AS unrealized_pnl
                FROM positions p
                LEFT JOIN agents a ON a.id = p.agent_id
                LEFT JOIN users u ON u.id = a.user_id
                ORDER BY quantity * COALESCE(current_price, entry_price) DESC LIMIT 25
                """)
            largest = [dict(r) for r in cursor.fetchall()]
        finally:
            conn.close()
        return {"totals": totals, "by_market": by_market, "by_side": by_side,
                "top_symbols": top_symbols, "largest": largest}

    @app.get('/api/admin/stats/automation')
    async def admin_stats_automation(authorization: str = Header(None)):
        require_admin(authorization)
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT COUNT(*) AS rules, COALESCE(SUM(enabled), 0) AS enabled, "
                "COALESCE(SUM(auto_execute), 0) AS auto_execute FROM automation_configs")
            totals = dict(cursor.fetchone())
            cursor.execute(
                "SELECT COUNT(*) AS runs, COALESCE(SUM(executed), 0) AS executed "
                "FROM automation_runs WHERE ran_at >= ?", (_cutoff(30),))
            runs30 = dict(cursor.fetchone())
            totals.update({
                "runs_30d": runs30["runs"],
                "executed_30d": runs30["executed"],
                "execute_rate_30d": round(runs30["executed"] / runs30["runs"], 4) if runs30["runs"] else 0,
            })
            cursor.execute(
                "SELECT substr(ran_at, 1, 10) AS day, COUNT(*) AS runs, "
                "COALESCE(SUM(executed), 0) AS executed FROM automation_runs "
                "WHERE ran_at >= ? GROUP BY substr(ran_at, 1, 10) ORDER BY day", (_cutoff(14),))
            runs_by_day = [dict(r) for r in cursor.fetchall()]
            cursor.execute(
                """
                SELECT r.agent_id, a.name AS agent_name, COUNT(*) AS runs,
                       COALESCE(SUM(r.executed), 0) AS executed
                FROM automation_runs r LEFT JOIN agents a ON a.id = r.agent_id
                WHERE r.ran_at >= ?
                GROUP BY r.agent_id, a.name ORDER BY runs DESC LIMIT 15
                """,
                (_cutoff(30),),
            )
            by_agent = [dict(r) for r in cursor.fetchall()]
            cursor.execute(
                "SELECT COALESCE(skip_reason, '(executed)') AS reason, COUNT(*) AS c "
                "FROM automation_runs WHERE ran_at >= ? GROUP BY skip_reason "
                "ORDER BY c DESC LIMIT 12", (_cutoff(30),))
            skip_reasons = [dict(r) for r in cursor.fetchall()]
        finally:
            conn.close()
        return {"totals": totals, "runs_by_day": runs_by_day, "by_agent": by_agent,
                "skip_reasons": skip_reasons}

    @app.get('/api/admin/analytics')
    async def admin_analytics(authorization: str = Header(None)):
        require_admin(authorization)
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT substr(created_at, 1, 10) AS day, COUNT(*) AS c FROM users "
                "WHERE created_at >= ? GROUP BY substr(created_at, 1, 10) ORDER BY day",
                (_cutoff(30),))
            signups_by_day = [dict(r) for r in cursor.fetchall()]
            cursor.execute(
                "SELECT substr(created_at, 1, 10) AS day, COUNT(*) AS c FROM signals "
                "WHERE message_type = 'operation' AND created_at >= ? "
                "GROUP BY substr(created_at, 1, 10) ORDER BY day", (_cutoff(30),))
            trades_by_day = [dict(r) for r in cursor.fetchall()]
            cursor.execute(
                "SELECT substr(created_at, 1, 10) AS day, COUNT(*) AS c FROM signals "
                "WHERE message_type = 'discussion' AND created_at >= ? "
                "GROUP BY substr(created_at, 1, 10) ORDER BY day", (_cutoff(30),))
            discussions_by_day = [dict(r) for r in cursor.fetchall()]
            # Revenue = activated subscriptions (paypal capture or admin approval).
            cursor.execute(
                "SELECT substr(COALESCE(started_at, created_at), 1, 7) AS month, "
                "COALESCE(SUM(amount_usd), 0) AS revenue, COUNT(*) AS activations "
                "FROM user_subscriptions WHERE status IN ('active', 'expired') "
                "GROUP BY substr(COALESCE(started_at, created_at), 1, 7) ORDER BY month")
            revenue_by_month = [dict(r) for r in cursor.fetchall()]
            cursor.execute(
                "SELECT plan_code, status, COUNT(*) AS c FROM user_subscriptions "
                "GROUP BY plan_code, status")
            subs_matrix = [dict(r) for r in cursor.fetchall()]
            cursor.execute(
                "SELECT COUNT(*) AS c FROM user_subscriptions WHERE status = 'active'")
            active_subs = int(cursor.fetchone()["c"])
            cursor.execute("SELECT COUNT(*) AS c FROM users")
            total_users = int(cursor.fetchone()["c"])
        finally:
            conn.close()
        return {
            "signups_by_day": signups_by_day,
            "trades_by_day": trades_by_day,
            "discussions_by_day": discussions_by_day,
            "revenue_by_month": revenue_by_month,
            "subscriptions_matrix": subs_matrix,
            "active_subscriptions": active_subs,
            "total_users": total_users,
        }

    # ────────────────────────── discussions moderation ──────────────────────────

    @app.get('/api/admin/discussions')
    async def admin_discussions(q: str = "", limit: int = 50, offset: int = 0,
                                authorization: str = Header(None)):
        require_admin(authorization)
        limit = max(1, min(limit, 200))
        where = "WHERE s.message_type = 'discussion'"
        params: list[Any] = []
        if q.strip():
            where += " AND (LOWER(s.title) LIKE ? OR LOWER(s.content) LIKE ? OR LOWER(a.name) LIKE ?)"
            needle = f"%{q.strip().lower()}%"
            params = [needle, needle, needle]
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                f"""
                SELECT s.signal_id, s.agent_id, a.name AS agent_name, s.title, s.content,
                       s.tags, s.created_at,
                       (SELECT COUNT(*) FROM signal_replies r WHERE r.signal_id = s.signal_id) AS reply_count
                FROM signals s LEFT JOIN agents a ON a.id = s.agent_id
                {where} ORDER BY s.id DESC LIMIT ? OFFSET ?
                """,
                (*params, limit, max(0, offset)),
            )
            discussions = [dict(r) for r in cursor.fetchall()]
            cursor.execute(
                f"SELECT COUNT(*) AS c FROM signals s LEFT JOIN agents a ON a.id = s.agent_id {where}",
                tuple(params))
            total = int(cursor.fetchone()["c"])
        finally:
            conn.close()
        return {"discussions": discussions, "total": total}

    @app.get('/api/admin/discussions/{signal_id}/replies')
    async def admin_discussion_replies(signal_id: int, authorization: str = Header(None)):
        require_admin(authorization)
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT r.id, r.agent_id, a.name AS agent_name, r.content, r.created_at
                FROM signal_replies r LEFT JOIN agents a ON a.id = r.agent_id
                WHERE r.signal_id = ? ORDER BY r.id
                """,
                (signal_id,),
            )
            replies = [dict(r) for r in cursor.fetchall()]
        finally:
            conn.close()
        return {"replies": replies}

    @app.delete('/api/admin/discussions/{signal_id}')
    async def admin_delete_discussion(signal_id: int, authorization: str = Header(None)):
        admin = require_admin(authorization)
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT signal_id, title FROM signals WHERE signal_id = ? AND message_type = 'discussion'",
                (signal_id,))
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Discussion not found")
            cursor.execute("DELETE FROM signal_replies WHERE signal_id = ?", (signal_id,))
            replies = cursor.rowcount
            cursor.execute("DELETE FROM signals WHERE signal_id = ?", (signal_id,))
            conn.commit()
        finally:
            conn.close()
        audit(admin, "discussion.delete", f"signal:{signal_id}",
              f"title={(row['title'] or '')[:120]} replies={replies}")
        return {"ok": True, "deleted_replies": replies}

    @app.delete('/api/admin/replies/{reply_id}')
    async def admin_delete_reply(reply_id: int, authorization: str = Header(None)):
        admin = require_admin(authorization)
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT id, signal_id FROM signal_replies WHERE id = ?", (reply_id,))
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Reply not found")
            cursor.execute("DELETE FROM signal_replies WHERE id = ?", (reply_id,))
            conn.commit()
        finally:
            conn.close()
        audit(admin, "reply.delete", f"reply:{reply_id}", f"signal={row['signal_id']}")
        return {"ok": True}

    # ────────────────────────── leaderboard management ──────────────────────────

    @app.get('/api/admin/leaderboard')
    async def admin_leaderboard(metric: str = "return", limit: int = 50,
                                authorization: str = Header(None)):
        require_admin(authorization)
        limit = max(1, min(limit, 200))
        snapshot = read_leaderboard_snapshot(metric=metric, limit=limit, offset=0)
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT e.agent_id, a.name AS agent_name, e.reason, e.active, e.created_at
                FROM agent_leaderboard_exclusions e
                LEFT JOIN agents a ON a.id = e.agent_id
                ORDER BY e.id DESC
                """)
            exclusions = [dict(r) for r in cursor.fetchall()]
        finally:
            conn.close()
        return {"snapshot": snapshot, "exclusions": exclusions}

    @app.post('/api/admin/leaderboard/exclusions')
    async def admin_add_exclusion(body: ExclusionBody, authorization: str = Header(None)):
        admin = require_admin(authorization)
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT id, name FROM agents WHERE id = ?", (body.agent_id,))
            agent = cursor.fetchone()
            if not agent:
                raise HTTPException(status_code=404, detail="Agent not found")
            cursor.execute(
                "SELECT id FROM agent_leaderboard_exclusions WHERE agent_id = ?", (body.agent_id,))
            existing = cursor.fetchone()
            if existing:
                cursor.execute(
                    "UPDATE agent_leaderboard_exclusions SET active = 1, reason = ? WHERE agent_id = ?",
                    (body.reason[:500], body.agent_id))
            else:
                cursor.execute(
                    "INSERT INTO agent_leaderboard_exclusions (agent_id, reason, active) VALUES (?, ?, 1)",
                    (body.agent_id, body.reason[:500]))
            conn.commit()
        finally:
            conn.close()
        audit(admin, "leaderboard.exclude", f"agent:{body.agent_id}",
              f"name={agent['name']} reason={body.reason[:200]}")
        return {"ok": True}

    @app.delete('/api/admin/leaderboard/exclusions/{agent_id}')
    async def admin_remove_exclusion(agent_id: int, authorization: str = Header(None)):
        admin = require_admin(authorization)
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE agent_leaderboard_exclusions SET active = 0 WHERE agent_id = ?", (agent_id,))
            changed = cursor.rowcount
            conn.commit()
        finally:
            conn.close()
        if not changed:
            raise HTTPException(status_code=404, detail="No exclusion for that agent")
        audit(admin, "leaderboard.include", f"agent:{agent_id}")
        return {"ok": True}

    @app.post('/api/admin/leaderboard/refresh')
    async def admin_leaderboard_refresh(authorization: str = Header(None)):
        admin = require_admin(authorization)
        result = refresh_leaderboard_snapshot()
        audit(admin, "leaderboard.refresh", detail=str(result)[:500])
        return {"ok": True, "result": result}

    # ── payment settings (USDT receiving address) ────────────────────────────

    @app.get('/api/admin/settings/payment')
    async def admin_payment_settings(authorization: str = Header(None)):
        require_admin(authorization)
        from platform_settings import get_setting_meta
        return {"usdt_address": get_setting_meta("usdt_address"),
                "usdt_network": get_setting_meta("usdt_network"),
                "bank_transfer_info": get_setting_meta("bank_transfer_info"),
                "networks": SUPPORTED_USDT_NETWORKS}

    @app.put('/api/admin/settings/payment')
    async def admin_payment_settings_save(body: PaymentSettingsBody,
                                          authorization: str = Header(None)):
        """Register the USDT receiving address. This is the address subscribers
        are told to send money to, so a typo silently sends their funds to a
        stranger — hence the format check and the audit entry naming the old
        and new value. Saving an empty address is allowed and takes the USDT
        option off the Subscribe page."""
        admin = require_admin(authorization)
        from platform_settings import get_setting, set_setting

        address = body.usdt_address.strip()
        if address and not re.fullmatch(r"[A-Za-z0-9]{20,80}", address):
            raise HTTPException(
                status_code=400,
                detail="That does not look like a USDT address (20-80 letters and digits, "
                       "no spaces or punctuation). Paste it directly from your wallet.")
        network = body.usdt_network.strip().upper()
        if network not in SUPPORTED_USDT_NETWORKS:
            raise HTTPException(
                status_code=400,
                detail=f"Network must be one of: {', '.join(SUPPORTED_USDT_NETWORKS)}")

        bank_info = None if body.bank_transfer_info is None else body.bank_transfer_info.strip()
        if bank_info is not None and len(bank_info) > 2000:
            raise HTTPException(
                status_code=400,
                detail="Bank transfer details must be under 2000 characters.")

        previous = get_setting("usdt_address")
        set_setting("usdt_address", address, admin.get("email"))
        set_setting("usdt_network", network, admin.get("email"))
        if bank_info is not None:
            set_setting("bank_transfer_info", bank_info, admin.get("email"))
        # Bank details are free text and go out to subscribers verbatim, so the
        # audit records only that they changed, not the account number itself.
        audit(admin, "settings.payment", "usdt",
              f"network={network} address={_mask_address(address) or '(cleared)'} "
              f"was={_mask_address(previous) or '(unset)'} "
              f"bank_info={'unchanged' if bank_info is None else ('set' if bank_info else '(cleared)')}")
        return {"ok": True, "usdt_address": address, "usdt_network": network,
                "bank_transfer_info": get_setting("bank_transfer_info")}

    # ── LLM routing settings (local AI server + per-tier provider/model) ─────

    _LLM_SETTING_KEYS = ("llm_local_base_url", "llm_local_model",
                         "llm_brief_provider", "llm_brief_model",
                         "llm_decision_provider", "llm_decision_model")

    def _llm_effective() -> dict:
        """What each tier resolves to right now (no run/user context), so the
        console shows the routing that a plain automation cycle would use."""
        from llm_client import resolve_provider
        out = {}
        for tier in ("brief", "decision", "assistant"):
            ap = resolve_provider(tier=tier)
            out[tier] = ({"provider": ap.spec.name, "model": ap.model,
                          "base_url": ap.base_url} if ap else None)
        return out

    @app.get('/api/admin/settings/llm')
    async def admin_llm_settings(authorization: str = Header(None)):
        require_admin(authorization)
        from llm_client import _PROVIDERS
        from platform_settings import get_setting_meta
        return {"settings": {k: get_setting_meta(k) for k in _LLM_SETTING_KEYS},
                "providers": list(_PROVIDERS),
                "effective": _llm_effective()}

    @app.put('/api/admin/settings/llm')
    async def admin_llm_settings_save(body: LlmSettingsBody,
                                      authorization: str = Header(None)):
        """Route the platform's LLM tiers from the console — e.g. point the
        'local' provider at the operator's own AI server and run analyst
        briefs on it while decisions stay on a hosted model. Omitted fields
        stay unchanged; empty strings clear (env fallback resumes)."""
        admin = require_admin(authorization)
        from llm_client import _PROVIDERS, invalidate_admin_llm_settings_cache
        from platform_settings import set_setting

        fields = {"llm_local_base_url": body.local_base_url,
                  "llm_local_model": body.local_model,
                  "llm_brief_provider": body.brief_provider,
                  "llm_brief_model": body.brief_model,
                  "llm_decision_provider": body.decision_provider,
                  "llm_decision_model": body.decision_model}

        url = (body.local_base_url or "").strip()
        if url and not re.match(r"^https?://\S+$", url):
            raise HTTPException(
                status_code=400,
                detail="Local AI server URL must start with http:// or https:// "
                       "(e.g. http://100.64.0.7:11434/v1)")
        for key in ("llm_brief_provider", "llm_decision_provider"):
            val = (fields[key] or "").strip().lower()
            if val and val not in _PROVIDERS:
                raise HTTPException(
                    status_code=400,
                    detail=f"{key} must be one of: {', '.join(_PROVIDERS)}")
        for key, val in fields.items():
            if val is not None and len(val.strip()) > 300:
                raise HTTPException(status_code=400, detail=f"{key} too long")

        changed = []
        for key, val in fields.items():
            if val is None:
                continue
            val = val.strip()
            if key.endswith("_provider"):
                val = val.lower()
            set_setting(key, val, admin.get("email"))
            changed.append(f"{key}={val or '(cleared)'}")
        invalidate_admin_llm_settings_cache()
        audit(admin, "settings.llm", "routing", "; ".join(changed) or "(no-op)")
        return {"ok": True, "effective": _llm_effective()}
