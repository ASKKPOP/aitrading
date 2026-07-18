"""
admin_auth.py — admin identity for the manager console.

Real admin accounts (email + password) replace the old shared ADMIN_TOKEN.
Sessions live in admin_tokens (12h TTL, same raw-token pattern as
user_tokens); every admin write action is recorded in admin_audit_log.

Roles: 'superadmin' (can manage other admins) and 'operator' (everything
else). The first superadmin is created with scripts/create_admin.py.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import HTTPException

from database import get_db_connection
from utils import hash_password, verify_password

ADMIN_SESSION_HOURS = 12


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def login_admin(email: str, password: str) -> dict[str, Any]:
    """Verify credentials and mint a session token. Raises 401/403."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM admin_users WHERE email = ?", (email.strip().lower(),))
        row = cursor.fetchone()
        if not row or not verify_password(password, row["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid credentials")
        if row["status"] != "active":
            raise HTTPException(status_code=403, detail="Admin account disabled")
        token = secrets.token_urlsafe(32)
        expires_at = _iso(_now() + timedelta(hours=ADMIN_SESSION_HOURS))
        cursor.execute(
            "INSERT INTO admin_tokens (admin_id, token, expires_at) VALUES (?, ?, ?)",
            (row["id"], token, expires_at),
        )
        cursor.execute(
            "UPDATE admin_users SET last_login_at = ? WHERE id = ?",
            (_iso(_now()), row["id"]),
        )
        conn.commit()
    finally:
        conn.close()
    return {"token": token, "admin_id": row["id"], "email": row["email"],
            "role": row["role"], "expires_at": expires_at}


def require_admin(authorization: Optional[str]) -> dict[str, Any]:
    """Resolve the bearer token to an active admin row. Raises 401."""
    supplied = (authorization or "").removeprefix("Bearer ").strip()
    if not supplied:
        raise HTTPException(status_code=401, detail="Admin login required")
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT a.id, a.email, a.role, a.status, t.expires_at
            FROM admin_tokens t JOIN admin_users a ON a.id = t.admin_id
            WHERE t.token = ?
            """,
            (supplied,),
        )
        row = cursor.fetchone()
    finally:
        conn.close()
    if not row:
        raise HTTPException(status_code=401, detail="Invalid admin session")
    if row["status"] != "active":
        raise HTTPException(status_code=403, detail="Admin account disabled")
    try:
        expires = datetime.fromisoformat(str(row["expires_at"]).replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid admin session")
    if expires < _now():
        raise HTTPException(status_code=401, detail="Admin session expired")
    return {"id": row["id"], "email": row["email"], "role": row["role"]}


def require_superadmin(authorization: Optional[str]) -> dict[str, Any]:
    admin = require_admin(authorization)
    if admin["role"] != "superadmin":
        raise HTTPException(status_code=403, detail="Superadmin role required")
    return admin


def logout_admin(authorization: Optional[str]) -> None:
    supplied = (authorization or "").removeprefix("Bearer ").strip()
    if not supplied:
        return
    conn = get_db_connection()
    try:
        conn.cursor().execute("DELETE FROM admin_tokens WHERE token = ?", (supplied,))
        conn.commit()
    finally:
        conn.close()


def audit(admin: dict[str, Any], action: str, target: str = "", detail: str = "") -> None:
    """Record an admin write action. Never raises — auditing must not break the op."""
    try:
        conn = get_db_connection()
        conn.cursor().execute(
            "INSERT INTO admin_audit_log (admin_id, admin_email, action, target, detail) VALUES (?, ?, ?, ?, ?)",
            (admin.get("id"), admin.get("email"), action, target, detail[:2000]),
        )
        conn.commit()
        conn.close()
    except Exception:  # noqa: BLE001
        pass


def create_admin(email: str, password: str, role: str = "operator") -> int:
    """Insert an admin account; returns its id. Raises 400 on duplicates/bad role."""
    email = email.strip().lower()
    if role not in ("superadmin", "operator"):
        raise HTTPException(status_code=400, detail="Role must be superadmin or operator")
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Valid email required")
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id FROM admin_users WHERE email = ?", (email,))
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail="Admin already exists")
        cursor.execute(
            "INSERT INTO admin_users (email, password_hash, role) VALUES (?, ?, ?)",
            (email, hash_password(password), role),
        )
        admin_id = cursor.lastrowid
        conn.commit()
    finally:
        conn.close()
    return int(admin_id)
