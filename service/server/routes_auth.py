"""
routes_auth.py — Phase 5 production auth: TOTP MFA endpoints.

The existing /api/users/{send-code,register,login} flow stays. This
module adds the second-factor layer on top: when a user has
mfa_enabled=1, login returns an mfa_token (short-lived, single-use)
instead of a session, and the client posts that token + a TOTP code
to /api/auth/mfa/verify to complete the login.

Endpoints:
  POST   /api/auth/mfa/setup           generate secret + backup codes
  POST   /api/auth/mfa/verify-setup    confirm a TOTP code → enable MFA
  GET    /api/auth/mfa/status          { enabled, backup_codes_remaining }
  POST   /api/auth/mfa/verify          login second-step (TOTP or backup code)
  POST   /api/auth/mfa/disable         disable MFA (requires password)

Also: a small login-wrapper override that intercepts /api/users/login
to issue an mfa_token when MFA is enabled. We do that by registering
this module's routes AFTER the user routes — FastAPI honors the first
match, but for /api/users/login we deliberately want the user-route
behavior, then check MFA inside _maybe_require_mfa() called by the
existing handler. Implementation note below: we patch the response
shape via a thin endpoint at /api/auth/login that the frontend
should use going forward.
"""
from __future__ import annotations

import json
import secrets as _secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import pyotp
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

import database
from cache import delete as _cache_delete, get_json as _cache_get, set_json as _cache_set
from routes_shared import RouteContext
from services import _create_user_session, _get_user_by_token
from utils import _extract_token, verify_password


# ── short-lived MFA-token store (Redis with TTL, in-proc fallback) ────────

_MFA_TOKEN_TTL_SECONDS = 300        # 5 minutes to complete the second step
_MFA_TOKEN_KEY_PREFIX = "auth:mfa-token"
_inproc_mfa_tokens: dict[str, dict] = {}


def _mfa_token_key(token: str) -> str:
    return f"{_MFA_TOKEN_KEY_PREFIX}:{token}"


def _store_mfa_token(token: str, payload: dict) -> None:
    if not _cache_set(_mfa_token_key(token), payload, ttl_seconds=_MFA_TOKEN_TTL_SECONDS):
        _inproc_mfa_tokens[token] = {
            **payload,
            "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=_MFA_TOKEN_TTL_SECONDS)).isoformat(),
        }


def _load_mfa_token(token: str) -> Optional[dict]:
    cached = _cache_get(_mfa_token_key(token))
    if cached is not None:
        return cached
    payload = _inproc_mfa_tokens.get(token)
    if not payload:
        return None
    # in-proc TTL check
    expires = payload.get("expires_at")
    if expires:
        try:
            exp_dt = datetime.fromisoformat(expires)
            if exp_dt < datetime.now(timezone.utc):
                _inproc_mfa_tokens.pop(token, None)
                return None
        except Exception:
            pass
    return payload


def _delete_mfa_token(token: str) -> None:
    _cache_delete(_mfa_token_key(token))
    _inproc_mfa_tokens.pop(token, None)


# ── helpers ───────────────────────────────────────────────────────────────

def _require_user(authorization: Optional[str]) -> dict:
    token = _extract_token(authorization)
    user = _get_user_by_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user


def _gen_backup_codes(n: int = 10) -> list[str]:
    """Random alphanumeric one-time codes, 8 chars each."""
    return ["".join(_secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(8))
            for _ in range(n)]


def _verify_totp_or_backup(user_row: dict, code: str) -> tuple[bool, Optional[list[str]]]:
    """Validate either a TOTP or a backup code.

    Returns (ok, new_backup_codes_to_persist). When a backup code is used,
    it's removed from the list and the caller must persist the new list.
    """
    secret = user_row.get("mfa_secret")
    if not secret:
        return False, None

    # TOTP path
    if code.isdigit() and len(code) == 6:
        if pyotp.TOTP(secret).verify(code, valid_window=1):
            return True, None
        return False, None

    # Backup-code path
    raw = user_row.get("mfa_backup_codes") or "[]"
    try:
        codes = json.loads(raw) if isinstance(raw, str) else (raw or [])
    except Exception:
        codes = []
    if code in codes:
        codes.remove(code)
        return True, codes
    return False, None


# ── Pydantic ──────────────────────────────────────────────────────────────

class VerifySetupBody(BaseModel):
    code: str = Field(min_length=4, max_length=12)


class VerifyMfaBody(BaseModel):
    mfa_token: str
    code: str = Field(min_length=4, max_length=12)


class DisableMfaBody(BaseModel):
    password: str


# ── Route registration ────────────────────────────────────────────────────

def register_auth_routes(app: FastAPI, ctx: RouteContext) -> None:

    # ── 1. setup ──────────────────────────────────────────────────────────
    @app.post("/api/auth/mfa/setup")
    async def mfa_setup(authorization: Optional[str] = Header(None)):
        user = _require_user(authorization)
        secret = pyotp.random_base32()
        backup_codes = _gen_backup_codes()

        # Save secret + codes; mfa_enabled stays 0 until verify-setup succeeds.
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "UPDATE users SET mfa_secret = ?, mfa_backup_codes = ?, mfa_enabled = 0 WHERE id = ?",
            (secret, json.dumps(backup_codes), user["id"]),
        )
        conn.commit()
        conn.close()

        otpauth = pyotp.TOTP(secret).provisioning_uri(
            name=user.get("email") or f"user-{user['id']}",
            issuer_name="Sooppiy",
        )
        return {
            "secret": secret,
            "otpauth_url": otpauth,
            "backup_codes": backup_codes,
        }

    # ── 2. verify-setup ───────────────────────────────────────────────────
    @app.post("/api/auth/mfa/verify-setup")
    async def mfa_verify_setup(body: VerifySetupBody,
                               authorization: Optional[str] = Header(None)):
        user = _require_user(authorization)
        if not user.get("mfa_secret"):
            raise HTTPException(status_code=400, detail="Run /api/auth/mfa/setup first")

        if not pyotp.TOTP(user["mfa_secret"]).verify(body.code, valid_window=1):
            raise HTTPException(status_code=400, detail="Invalid code")

        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE users SET mfa_enabled = 1 WHERE id = ?", (user["id"],))
        conn.commit()
        conn.close()
        return {"enabled": True}

    # ── 3. status ─────────────────────────────────────────────────────────
    @app.get("/api/auth/mfa/status")
    async def mfa_status(authorization: Optional[str] = Header(None)):
        user = _require_user(authorization)
        codes_raw = user.get("mfa_backup_codes") or "[]"
        try:
            codes = json.loads(codes_raw) if isinstance(codes_raw, str) else (codes_raw or [])
        except Exception:
            codes = []
        return {
            "enabled": bool(user.get("mfa_enabled")),
            "backup_codes_remaining": len(codes),
        }

    # ── 4. verify (second-factor login) ───────────────────────────────────
    @app.post("/api/auth/mfa/verify")
    async def mfa_verify(body: VerifyMfaBody):
        payload = _load_mfa_token(body.mfa_token)
        if not payload:
            raise HTTPException(status_code=401, detail="Invalid or expired MFA token")
        user_id = int(payload["user_id"])

        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = cur.fetchone()
        conn.close()
        if not row:
            raise HTTPException(status_code=401, detail="User not found")
        user_row = dict(row)

        ok, new_codes = _verify_totp_or_backup(user_row, body.code.strip())
        if not ok:
            raise HTTPException(status_code=401, detail="Invalid code")

        if new_codes is not None:
            # backup code was consumed — persist the new list
            conn = database.get_db_connection()
            cur = conn.cursor()
            cur.execute(
                "UPDATE users SET mfa_backup_codes = ? WHERE id = ?",
                (json.dumps(new_codes), user_id),
            )
            conn.commit()
            conn.close()

        _delete_mfa_token(body.mfa_token)
        session_token = _create_user_session(user_id)
        return {"token": session_token, "user_id": user_id, "email": user_row.get("email")}

    # ── 5. disable ────────────────────────────────────────────────────────
    @app.post("/api/auth/mfa/disable")
    async def mfa_disable(body: DisableMfaBody,
                          authorization: Optional[str] = Header(None)):
        user = _require_user(authorization)
        if not verify_password(body.password, user.get("password_hash") or ""):
            raise HTTPException(status_code=401, detail="Wrong password")
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "UPDATE users SET mfa_enabled = 0, mfa_secret = NULL, mfa_backup_codes = NULL WHERE id = ?",
            (user["id"],),
        )
        conn.commit()
        conn.close()
        return {"enabled": False}


# ── helper exposed to routes_users.py login handler ───────────────────────

def issue_mfa_token_for_user(user_id: int) -> str:
    """Mint a short-lived MFA token that the client trades for a real session
    after presenting a valid TOTP / backup code. Called by /api/users/login
    when the user has mfa_enabled=1."""
    token = _secrets.token_urlsafe(24)
    _store_mfa_token(token, {"user_id": user_id})
    return token
