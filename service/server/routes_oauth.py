"""
routes_oauth.py — Phase 5 production auth: external OAuth providers.

Today: Google. Apple + Phone (SMS) are stubs reporting `false` in the
provider list; their endpoints land when their credentials do.

Endpoints:
  GET /api/auth/providers              { providers: { email, google, apple, phone } }
  GET /api/auth/google/start           302 → Google consent URL (sets state cookie)
  GET /api/auth/google/callback        exchanges code, finds/creates user, returns session

OAuth state is held in the same cache layer as MFA tokens (Redis with
TTL when configured, in-process dict otherwise) so the CSRF check
survives across the two requests.

Env vars (all required for Google to be enabled):
  GOOGLE_CLIENT_ID
  GOOGLE_CLIENT_SECRET
  GOOGLE_REDIRECT_URI
"""
from __future__ import annotations

import os
import secrets as _secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from urllib.parse import urlencode

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse

import database
from cache import delete as _cache_delete, get_json as _cache_get, set_json as _cache_set
from routes_shared import RouteContext
from services import _create_user_session
from utils import hash_password


_STATE_TTL_SECONDS = 600         # OAuth state nonces live 10 min
_STATE_KEY_PREFIX = "auth:oauth-state"
_inproc_oauth_states: dict[str, dict] = {}


def _state_key(state: str) -> str:
    return f"{_STATE_KEY_PREFIX}:{state}"


def _store_state(state: str, payload: dict) -> None:
    if not _cache_set(_state_key(state), payload, ttl_seconds=_STATE_TTL_SECONDS):
        _inproc_oauth_states[state] = {
            **payload,
            "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=_STATE_TTL_SECONDS)).isoformat(),
        }


def _consume_state(state: str) -> Optional[dict]:
    cached = _cache_get(_state_key(state))
    if cached is not None:
        _cache_delete(_state_key(state))
        return cached
    payload = _inproc_oauth_states.pop(state, None)
    if not payload:
        return None
    expires = payload.get("expires_at")
    if expires:
        try:
            if datetime.fromisoformat(expires) < datetime.now(timezone.utc):
                return None
        except Exception:
            pass
    return payload


# ── provider configuration ───────────────────────────────────────────────

def _google_configured() -> bool:
    return all(
        os.environ.get(k, "").strip()
        for k in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REDIRECT_URI")
    )


def _provider_state() -> dict[str, bool]:
    return {
        "email":  True,                # always available — email + 6-digit OTP
        "google": _google_configured(),
        "apple":  False,               # Phase 5b
        "phone":  False,               # Phase 5c (Twilio)
    }


# ── google calls (split out so tests can patch them) ─────────────────────

def _exchange_google_code(code: str) -> dict[str, Any]:
    """POST to Google's token endpoint; returns the JSON body."""
    r = httpx.post(
        "https://oauth2.googleapis.com/token",
        data={
            "code": code,
            "client_id":     os.environ["GOOGLE_CLIENT_ID"],
            "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
            "redirect_uri":  os.environ["GOOGLE_REDIRECT_URI"],
            "grant_type":    "authorization_code",
        },
        timeout=10.0,
    )
    r.raise_for_status()
    return r.json()


def _fetch_google_userinfo(access_token: str) -> dict[str, Any]:
    """GET /oauth2/v2/userinfo with the access token."""
    r = httpx.get(
        "https://www.googleapis.com/oauth2/v2/userinfo",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10.0,
    )
    r.raise_for_status()
    body = r.json()
    # Google sometimes returns `id`, sometimes `sub`; normalize.
    if "sub" not in body and "id" in body:
        body["sub"] = body["id"]
    return body


def _find_or_create_user_from_google(google_user: dict[str, Any]) -> int:
    """Map a Google identity to a Sooppiy user. Returns user_id.

    Three cases, in priority:
      1. (provider, provider_user_id) already in oauth_identities → reuse.
      2. users.email matches Google email → link a new oauth_identity row.
      3. neither → create a new user, then link.
    """
    sub = str(google_user.get("sub") or "")
    email = (google_user.get("email") or "").strip().lower()
    if not sub:
        raise HTTPException(status_code=502, detail="Google response missing 'sub'")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    conn = database.get_db_connection()
    cur = conn.cursor()
    try:
        # 1. existing link
        cur.execute(
            "SELECT user_id FROM oauth_identities WHERE provider='google' AND provider_user_id=?",
            (sub,),
        )
        row = cur.fetchone()
        if row:
            return int(row["user_id"])

        # 2. existing user with same email
        if email:
            cur.execute("SELECT id FROM users WHERE email = ?", (email,))
            row = cur.fetchone()
            if row:
                user_id = int(row["id"])
                cur.execute(
                    "INSERT INTO oauth_identities (user_id, provider, provider_user_id, email, created_at) "
                    "VALUES (?, 'google', ?, ?, ?)",
                    (user_id, sub, email, now),
                )
                conn.commit()
                return user_id

        # 3. brand-new user — assign a random password since OAuth-only users
        # can't sign in via the password endpoint until they set one.
        random_password = _secrets.token_urlsafe(32)
        cur.execute(
            "INSERT INTO users (email, password_hash, points) VALUES (?, ?, 0)",
            (email or f"google-{sub}@sooppiy.com", hash_password(random_password)),
        )
        user_id = int(cur.lastrowid)
        cur.execute(
            "INSERT INTO oauth_identities (user_id, provider, provider_user_id, email, created_at) "
            "VALUES (?, 'google', ?, ?, ?)",
            (user_id, sub, email, now),
        )
        conn.commit()
        return user_id
    finally:
        conn.close()


# ── Route registration ────────────────────────────────────────────────────

def register_oauth_routes(app: FastAPI, ctx: RouteContext) -> None:

    @app.get("/api/auth/providers")
    async def list_providers():
        return {"providers": _provider_state()}

    @app.get("/api/auth/google/start")
    async def google_start():
        if not _google_configured():
            raise HTTPException(status_code=503, detail="Google OAuth is not configured")
        state = _secrets.token_urlsafe(24)
        _store_state(state, {"created_at": datetime.now(timezone.utc).isoformat()})
        qs = urlencode({
            "response_type": "code",
            "client_id":     os.environ["GOOGLE_CLIENT_ID"],
            "redirect_uri":  os.environ["GOOGLE_REDIRECT_URI"],
            "scope":         "openid email profile",
            "state":         state,
            "access_type":   "offline",
            "prompt":        "consent",
        })
        return RedirectResponse(
            url=f"https://accounts.google.com/o/oauth2/v2/auth?{qs}",
            status_code=302,
        )

    @app.get("/api/auth/google/callback")
    async def google_callback(code: str, state: str):
        if not _google_configured():
            raise HTTPException(status_code=503, detail="Google OAuth is not configured")
        if not _consume_state(state):
            raise HTTPException(status_code=400, detail="Invalid or expired state")

        try:
            token_body = _exchange_google_code(code)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Google token exchange failed: {exc}")

        access_token = token_body.get("access_token")
        if not access_token:
            raise HTTPException(status_code=502, detail="Google response missing access_token")

        try:
            user_info = _fetch_google_userinfo(access_token)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Google userinfo failed: {exc}")

        user_id = _find_or_create_user_from_google(user_info)
        session_token = _create_user_session(user_id)
        return JSONResponse({
            "token":   session_token,
            "user_id": user_id,
            "email":   (user_info.get("email") or "").strip().lower(),
        })
