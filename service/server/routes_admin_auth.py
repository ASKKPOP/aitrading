"""
routes_admin_auth.py — admin identity endpoints for the manager console.

  POST   /api/admin/login              email + password → session token (12h)
  POST   /api/admin/logout             revoke the current session
  GET    /api/admin/me                 who am I (id / email / role)
  GET    /api/admin/admins             list admin accounts        (superadmin)
  POST   /api/admin/admins             create an admin            (superadmin)
  PATCH  /api/admin/admins/{id}        role / status / password   (superadmin)
  DELETE /api/admin/admins/{id}        remove an admin            (superadmin)
  GET    /api/admin/audit              audit log, newest first

Auth model lives in admin_auth.py. A superadmin cannot disable or delete
itself — prevents locking everyone out of the console.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from admin_auth import (
    audit,
    create_admin,
    login_admin,
    logout_admin,
    require_admin,
    require_superadmin,
)
from database import get_db_connection
from routes_shared import RouteContext
from utils import hash_password

logger = logging.getLogger("routes_admin_auth")


class AdminLoginBody(BaseModel):
    email: str
    password: str


class AdminCreateBody(BaseModel):
    email: str
    password: str
    role: str = "operator"


class AdminPatchBody(BaseModel):
    role: Optional[str] = None
    status: Optional[str] = None
    password: Optional[str] = None


def register_admin_auth_routes(app: FastAPI, ctx: RouteContext) -> None:

    @app.post('/api/admin/login')
    async def admin_login(body: AdminLoginBody):
        session = login_admin(body.email, body.password)
        audit({"id": session["admin_id"], "email": session["email"]}, "login")
        return session

    @app.post('/api/admin/logout')
    async def admin_logout(authorization: str = Header(None)):
        logout_admin(authorization)
        return {"ok": True}

    @app.get('/api/admin/me')
    async def admin_me(authorization: str = Header(None)):
        return require_admin(authorization)

    @app.get('/api/admin/admins')
    async def admin_list_admins(authorization: str = Header(None)):
        require_superadmin(authorization)
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT id, email, role, status, created_at, last_login_at FROM admin_users ORDER BY id")
            admins = [dict(r) for r in cursor.fetchall()]
        finally:
            conn.close()
        return {"admins": admins}

    @app.post('/api/admin/admins')
    async def admin_create_admin(body: AdminCreateBody, authorization: str = Header(None)):
        admin = require_superadmin(authorization)
        new_id = create_admin(body.email, body.password, body.role)
        audit(admin, "admin.create", f"admin:{new_id}", f"email={body.email.strip().lower()} role={body.role}")
        return {"ok": True, "id": new_id}

    @app.patch('/api/admin/admins/{admin_id}')
    async def admin_patch_admin(admin_id: int, body: AdminPatchBody,
                                authorization: str = Header(None)):
        admin = require_superadmin(authorization)
        if admin_id == admin["id"] and body.status and body.status != "active":
            raise HTTPException(status_code=400, detail="Cannot disable your own account")
        sets: list[str] = []
        params: list = []
        changes: list[str] = []
        if body.role is not None:
            if body.role not in ("superadmin", "operator"):
                raise HTTPException(status_code=400, detail="Role must be superadmin or operator")
            if admin_id == admin["id"] and body.role != "superadmin":
                raise HTTPException(status_code=400, detail="Cannot demote your own account")
            sets.append("role = ?"); params.append(body.role); changes.append(f"role={body.role}")
        if body.status is not None:
            if body.status not in ("active", "disabled"):
                raise HTTPException(status_code=400, detail="Status must be active or disabled")
            sets.append("status = ?"); params.append(body.status); changes.append(f"status={body.status}")
        if body.password is not None:
            if len(body.password) < 8:
                raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
            sets.append("password_hash = ?"); params.append(hash_password(body.password))
            changes.append("password=reset")
        if not sets:
            raise HTTPException(status_code=400, detail="Nothing to update")
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT id FROM admin_users WHERE id = ?", (admin_id,))
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail="Admin not found")
            cursor.execute(
                f"UPDATE admin_users SET {', '.join(sets)} WHERE id = ?", (*params, admin_id))
            # Disabling or resetting a password kills existing sessions.
            if body.status == "disabled" or body.password is not None:
                cursor.execute("DELETE FROM admin_tokens WHERE admin_id = ?", (admin_id,))
            conn.commit()
        finally:
            conn.close()
        audit(admin, "admin.update", f"admin:{admin_id}", " ".join(changes))
        return {"ok": True}

    @app.delete('/api/admin/admins/{admin_id}')
    async def admin_delete_admin(admin_id: int, authorization: str = Header(None)):
        admin = require_superadmin(authorization)
        if admin_id == admin["id"]:
            raise HTTPException(status_code=400, detail="Cannot delete your own account")
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT email FROM admin_users WHERE id = ?", (admin_id,))
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Admin not found")
            cursor.execute("DELETE FROM admin_tokens WHERE admin_id = ?", (admin_id,))
            cursor.execute("DELETE FROM admin_users WHERE id = ?", (admin_id,))
            conn.commit()
        finally:
            conn.close()
        audit(admin, "admin.delete", f"admin:{admin_id}", f"email={row['email']}")
        return {"ok": True}

    @app.get('/api/admin/audit')
    async def admin_audit_log(limit: int = 100, offset: int = 0,
                              authorization: str = Header(None)):
        require_admin(authorization)
        limit = max(1, min(limit, 500))
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT id, admin_id, admin_email, action, target, detail, created_at
                FROM admin_audit_log ORDER BY id DESC LIMIT ? OFFSET ?
                """,
                (limit, max(0, offset)),
            )
            entries = [dict(r) for r in cursor.fetchall()]
            cursor.execute("SELECT COUNT(*) AS c FROM admin_audit_log")
            total = int(cursor.fetchone()["c"])
        finally:
            conn.close()
        return {"entries": entries, "total": total}
