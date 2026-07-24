"""
routes_admin.py — Manager/admin API for platform operations.

Everything an operator needs in one gated surface:
  GET    /api/admin/overview            platform counts + money totals
  GET    /api/admin/agents              agent accounts (search, paging)
  DELETE /api/admin/agents/{id}         delete an agent + all its content
  GET    /api/admin/users               human user accounts
  DELETE /api/admin/users/{id}          delete a user (+ linked agent cascade)
  GET    /api/admin/transactions        money movements: trades + points ledger
  GET    /api/admin/automation          all automation rules + recent runs

Auth: admin session tokens from admin_auth.py — admins log in with email +
password (POST /api/admin/login, see routes_admin_auth.py) and every write
action is recorded in admin_audit_log. The old shared ADMIN_TOKEN is gone.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Optional

from fastapi import FastAPI, Header, HTTPException

from admin_auth import audit, require_admin as _require_admin_session
from database import get_db_connection
from routes_shared import RouteContext, utc_now_iso_z

logger = logging.getLogger("routes_admin")

# Tables that hold per-agent content — the delete cascade, in FK-safe order.
_AGENT_CONTENT_TABLES: tuple[tuple[str, str], ...] = (
    ("signal_replies", "agent_id"),
    ("signals", "agent_id"),
    ("subscriptions", "follower_id"),
    ("subscriptions", "leader_id"),
    ("positions", "agent_id"),
    ("agent_messages", "agent_id"),
    ("agent_tasks", "agent_id"),
    ("automation_configs", "agent_id"),
    ("automation_runs", "agent_id"),
    ("trading_runs", "agent_id"),
    ("profit_history", "agent_id"),
    ("agent_reward_ledger", "agent_id"),
    ("signal_predictions", "agent_id"),
    ("signal_quality_scores", "agent_id"),
    ("agent_metric_snapshots", "agent_id"),
    ("agent_audit_log", "agent_id"),
    ("challenge_participants", "agent_id"),
    ("challenge_submissions", "agent_id"),
    ("challenge_trades", "agent_id"),
    ("team_mission_participants", "agent_id"),
    ("team_members", "agent_id"),
    ("team_messages", "agent_id"),
    ("team_submissions", "agent_id"),
    ("team_contributions", "agent_id"),
    ("experiment_assignments", "agent_id"),
    ("experiment_events", "agent_id"),
    ("broker_accounts", "agent_id"),
    ("broker_orders", "agent_id"),
    ("broker_live_optins", "agent_id"),
    ("agent_leaderboard_exclusions", "agent_id"),
)


def _require_admin(authorization: Optional[str]) -> dict[str, Any]:
    return _require_admin_session(authorization)


def _count(cursor, sql: str, params: tuple = ()) -> int:
    cursor.execute(sql, params)
    row = cursor.fetchone()
    if not row:
        return 0
    # MySQL (DictCursor) rows are dicts — iterate values, not keys. SQLite
    # Rows index positionally.
    value = next(iter(row.values())) if isinstance(row, dict) else row[0]
    return int(value)


def _delete_agent_cascade(cursor, agent_id: int) -> dict[str, int]:
    deleted: dict[str, int] = {}
    # run_events / run_reports key on run_id, not agent_id — clear them via
    # the agent's runs BEFORE trading_runs itself goes (Plan 10 Phase 5).
    for run_table in ("run_events", "run_reports"):
        try:
            cursor.execute(
                f"""DELETE FROM {run_table} WHERE run_id IN
                    (SELECT id FROM trading_runs WHERE agent_id = ?)""",
                (agent_id,))
            if cursor.rowcount:
                deleted[f"{run_table}.run_id"] = cursor.rowcount
        except Exception as exc:  # noqa: BLE001
            logger.warning("admin cascade %s.run_id failed: %s", run_table, exc)
    # Plan 14: fleet children key on fleet_id — clear via the agent's fleets
    # BEFORE the fleets rows go (prod MySQL enforces the FKs SQLite ignores).
    for fleet_table in ("fleet_events", "fleet_candidates", "fleet_slots"):
        try:
            cursor.execute(
                f"""DELETE FROM {fleet_table} WHERE fleet_id IN
                    (SELECT id FROM fleets WHERE agent_id = ?)""",
                (agent_id,))
            if cursor.rowcount:
                deleted[f"{fleet_table}.fleet_id"] = cursor.rowcount
        except Exception as exc:  # noqa: BLE001
            logger.warning("admin cascade %s.fleet_id failed: %s", fleet_table, exc)
    for table, column in (("fleet_symbol_cooldowns", "agent_id"),
                          ("fleets", "agent_id")):
        try:
            cursor.execute(f"DELETE FROM {table} WHERE {column} = ?", (agent_id,))
            if cursor.rowcount:
                deleted[f"{table}.{column}"] = cursor.rowcount
        except Exception as exc:  # noqa: BLE001
            logger.warning("admin cascade %s.%s failed: %s", table, column, exc)
    for table, column in _AGENT_CONTENT_TABLES:
        try:
            cursor.execute(f"DELETE FROM {table} WHERE {column} = ?", (agent_id,))
            if cursor.rowcount:
                deleted[f"{table}.{column}"] = cursor.rowcount
        except Exception as exc:  # noqa: BLE001 — tolerate schema drift per table
            logger.warning("admin cascade %s.%s failed: %s", table, column, exc)
    cursor.execute("DELETE FROM agents WHERE id = ?", (agent_id,))
    deleted["agents"] = cursor.rowcount
    return deleted


def register_admin_routes(app: FastAPI, ctx: RouteContext) -> None:

    @app.get('/api/admin/overview')
    async def admin_overview(authorization: str = Header(None)):
        _require_admin(authorization)
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            overview = {
                "agents": _count(cursor, "SELECT COUNT(*) FROM agents"),
                "users": _count(cursor, "SELECT COUNT(*) FROM users"),
                "signals_total": _count(cursor, "SELECT COUNT(*) FROM signals"),
                "trades": _count(cursor, "SELECT COUNT(*) FROM signals WHERE message_type = 'operation'"),
                "strategies": _count(cursor, "SELECT COUNT(*) FROM signals WHERE message_type = 'strategy'"),
                "discussions": _count(cursor, "SELECT COUNT(*) FROM signals WHERE message_type = 'discussion'"),
                "open_positions": _count(cursor, "SELECT COUNT(*) FROM positions"),
                "automation_rules": _count(cursor, "SELECT COUNT(*) FROM automation_configs"),
                "automation_rules_enabled": _count(cursor, "SELECT COUNT(*) FROM automation_configs WHERE enabled = 1"),
                "automation_runs_24h": _count(
                    cursor,
                    "SELECT COUNT(*) FROM automation_runs WHERE ran_at >= datetime('now', '-1 day')"
                    if not os.getenv("DATABASE_URL") else
                    "SELECT COUNT(*) FROM automation_runs WHERE ran_at >= NOW() - INTERVAL 1 DAY",
                ),
            }
            cursor.execute("SELECT COALESCE(SUM(cash), 0) AS c, COALESCE(SUM(points), 0) AS p FROM agents")
            row = cursor.fetchone()
            overview["total_sim_cash"] = round(float(row["c"] or 0), 2)
            overview["total_points"] = int(row["p"] or 0)
            cursor.execute(
                "SELECT id, name, created_at FROM agents ORDER BY id DESC LIMIT 5")
            overview["recent_agents"] = [dict(r) for r in cursor.fetchall()]
        finally:
            conn.close()
        return {"overview": overview, "as_of": utc_now_iso_z()}

    @app.get('/api/admin/agents')
    async def admin_agents(q: str = "", limit: int = 50, offset: int = 0,
                           authorization: str = Header(None)):
        _require_admin(authorization)
        limit = max(1, min(limit, 200))
        offset = max(0, offset)
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            where = ""
            params: list[Any] = []
            if q.strip():
                where = "WHERE LOWER(a.name) LIKE ?"
                params = [f"%{q.strip().lower()}%"]
            cursor.execute(
                f"""
                SELECT a.id, a.name, a.cash, a.points, a.created_at,
                       (SELECT COUNT(*) FROM signals s
                        WHERE s.agent_id = a.id AND s.message_type = 'operation') AS trade_count,
                       (SELECT COUNT(*) FROM positions p WHERE p.agent_id = a.id) AS open_positions
                FROM agents a {where}
                ORDER BY a.id DESC LIMIT ? OFFSET ?
                """,
                (*params, limit, offset),
            )
            agents = [dict(r) for r in cursor.fetchall()]
            total = _count(cursor, f"SELECT COUNT(*) FROM agents a {where}", tuple(params))
        finally:
            conn.close()
        return {"agents": agents, "total": total, "limit": limit, "offset": offset}

    @app.delete('/api/admin/agents/{agent_id}')
    async def admin_delete_agent(agent_id: int, authorization: str = Header(None)):
        admin = _require_admin(authorization)
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT id, name FROM agents WHERE id = ?", (agent_id,))
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Agent not found")
            deleted = _delete_agent_cascade(cursor, agent_id)
            conn.commit()
        finally:
            conn.close()
        logger.info("admin deleted agent %s (%s): %s", agent_id, row["name"], deleted)
        audit(admin, "agent.delete", f"agent:{agent_id}", f"name={row['name']}")
        return {"ok": True, "deleted": deleted}

    @app.get('/api/admin/users')
    async def admin_users(limit: int = 50, offset: int = 0,
                          authorization: str = Header(None)):
        _require_admin(authorization)
        limit = max(1, min(limit, 200))
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT u.id, u.email, u.created_at, COALESCE(u.mfa_enabled, 0) AS mfa_enabled,
                       COALESCE(u.status, 'active') AS status,
                       (SELECT s.plan_code FROM user_subscriptions s
                        WHERE s.user_id = u.id AND s.status = 'active'
                        ORDER BY s.id DESC LIMIT 1) AS plan_code,
                       (SELECT CASE
                          WHEN SUM(c.account_type IN ('live', 'real')) > 0 THEN 'live'
                          WHEN SUM(c.account_type = 'shadow') > 0 THEN 'shadow'
                          WHEN COUNT(*) > 0 THEN 'simulator'
                          ELSE NULL END
                        FROM automation_configs c WHERE c.agent_id = a.id) AS trading_mode,
                       a.id AS agent_id, a.name AS agent_name
                FROM users u
                LEFT JOIN agents a ON a.user_id = u.id
                ORDER BY u.id DESC LIMIT ? OFFSET ?
                """,
                (limit, max(0, offset)),
            )
            users = [dict(r) for r in cursor.fetchall()]
            total = _count(cursor, "SELECT COUNT(*) FROM users")
        finally:
            conn.close()
        return {"users": users, "total": total}

    @app.delete('/api/admin/users/{user_id}')
    async def admin_delete_user(user_id: int, authorization: str = Header(None)):
        admin = _require_admin(authorization)
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT id, email FROM users WHERE id = ?", (user_id,))
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="User not found")
            deleted: dict[str, Any] = {}
            # Linked agents cascade first (auto-provisioned simulator agents).
            cursor.execute("SELECT id FROM agents WHERE user_id = ?", (user_id,))
            linked = [r["id"] for r in cursor.fetchall()]
            for aid in linked:
                deleted[f"agent:{aid}"] = _delete_agent_cascade(cursor, aid)
            for table in ("user_tokens", "user_api_settings", "points_transactions", "oauth_identities"):
                try:
                    cursor.execute(f"DELETE FROM {table} WHERE user_id = ?", (user_id,))
                    if cursor.rowcount:
                        deleted[table] = cursor.rowcount
                except Exception as exc:  # noqa: BLE001
                    logger.warning("admin user cascade %s failed: %s", table, exc)
            cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
            deleted["users"] = cursor.rowcount
            conn.commit()
        finally:
            conn.close()
        logger.info("admin deleted user %s (%s): %s", user_id, row["email"], deleted)
        audit(admin, "user.delete", f"user:{user_id}", f"email={row['email']}")
        return {"ok": True, "deleted": deleted}

    @app.get('/api/admin/transactions')
    async def admin_transactions(limit: int = 50, authorization: str = Header(None)):
        _require_admin(authorization)
        limit = max(1, min(limit, 200))
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT s.signal_id, s.agent_id, a.name AS agent_name, s.market, s.symbol,
                       s.side, s.entry_price, s.quantity, s.created_at
                FROM signals s LEFT JOIN agents a ON a.id = s.agent_id
                WHERE s.message_type = 'operation'
                ORDER BY s.id DESC LIMIT ?
                """,
                (limit,),
            )
            trades = [dict(r) for r in cursor.fetchall()]
            cursor.execute(
                """
                SELECT pt.id, pt.user_id, u.email AS user_email, pt.amount,
                       pt.type, pt.description, pt.created_at
                FROM points_transactions pt LEFT JOIN users u ON u.id = pt.user_id
                ORDER BY pt.id DESC LIMIT ?
                """,
                (limit,),
            )
            points = [dict(r) for r in cursor.fetchall()]
            # Agent-side reward/points ledger (publish rewards, exchanges).
            cursor.execute(
                """
                SELECT l.id, l.agent_id, a.name AS agent_name, l.amount, l.reason, l.created_at
                FROM agent_reward_ledger l LEFT JOIN agents a ON a.id = l.agent_id
                ORDER BY l.id DESC LIMIT ?
                """,
                (limit,),
            )
            rewards = [dict(r) for r in cursor.fetchall()]
        finally:
            conn.close()
        return {"trades": trades, "points_transactions": points, "reward_ledger": rewards}

    @app.get('/api/admin/automation')
    async def admin_automation(limit: int = 50, authorization: str = Header(None)):
        _require_admin(authorization)
        limit = max(1, min(limit, 200))
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT c.id, c.agent_id, a.name AS agent_name, c.symbol, c.market,
                       c.provider, c.interval_minutes, c.min_confidence, c.size_usd,
                       c.auto_execute, c.account_type, c.enabled, c.last_run_at
                FROM automation_configs c LEFT JOIN agents a ON a.id = c.agent_id
                ORDER BY c.id DESC LIMIT ?
                """,
                (limit,),
            )
            rules = [dict(r) for r in cursor.fetchall()]
            cursor.execute(
                """
                SELECT r.id, r.config_id, r.agent_id, a.name AS agent_name, r.action,
                       r.confidence, r.executed, r.skip_reason, r.ran_at
                FROM automation_runs r LEFT JOIN agents a ON a.id = r.agent_id
                ORDER BY r.id DESC LIMIT ?
                """,
                (limit,),
            )
            runs = [dict(r) for r in cursor.fetchall()]
        finally:
            conn.close()
        return {"rules": rules, "runs": runs}
