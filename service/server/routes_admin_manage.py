"""
routes_admin_manage.py — the extended manager-console API.

Member management
  GET  /api/admin/members/{user_id}             full member detail
  POST /api/admin/members/{user_id}/status      suspend / reactivate

Paid membership
  GET  /api/admin/subscriptions                 list (filter by status)
  POST /api/admin/subscriptions/{id}/approve    pending → active (30 days)
  POST /api/admin/subscriptions/{id}/reject     pending → rejected
  POST /api/admin/subscriptions/{id}/extend     push expires_at out N days
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


class SubscriptionExtendBody(BaseModel):
    days: int = 30


class ContractStatusBody(BaseModel):
    status: str


class ExclusionBody(BaseModel):
    agent_id: int
    reason: str = ""


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
