"""
routes_oauth.py — Phase 5 production auth: external OAuth providers.

Today: Google + Apple. Phone (SMS) is still a stub reporting `false` in
the provider list; its endpoints land when its credentials do.

Endpoints:
  GET  /api/auth/providers             { providers: { email, google, apple, phone } }
  GET  /api/auth/google/start          302 → Google consent URL
  GET  /api/auth/google/callback       exchanges code, finds/creates user, returns session
  GET  /api/auth/apple/start           302 → Apple consent URL
  POST /api/auth/apple/callback        Apple's form_post lands HERE, then 302s to the SPA
  POST /api/auth/apple/session         SPA redeems the one-time handoff for the session

OAuth state is held in the same cache layer as MFA tokens (Redis with
TTL when configured, in-process dict otherwise) so the CSRF check
survives across the two requests. For Apple that is not a nicety: its
callback is a cross-site POST, which would not carry a SameSite=Lax
cookie at all.

Apple differs from Google in four ways that shape the code below:
  1. The client secret is not a string Apple gives you — it is an ES256
     JWT we sign with the .p8 key, valid at most 6 months. Minted per
     request with a short expiry so there is nothing to rotate.
  2. The callback is a POST (response_mode=form_post is mandatory once
     the scope asks for name or email), so it cannot land on an SPA
     route the way the Google one does — it must hit the backend.
  3. Name and email arrive ONLY on the first-ever authorization, in a
     `user` form field. Miss it and it is gone for good.
  4. There is no userinfo endpoint; identity comes from the id_token,
     verified against Apple's JWKS.

Env vars:
  Google (all three required to enable it)
    GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET / GOOGLE_REDIRECT_URI
  Apple (all five required to enable it)
    APPLE_TEAM_ID       10-char team id, the JWT `iss`
    APPLE_CLIENT_ID     the Services ID (e.g. com.sooppiy.web), the JWT `sub`
    APPLE_KEY_ID        10-char key id, the JWT header `kid`
    APPLE_REDIRECT_URI  must equal the Return URL registered with Apple
    APPLE_PRIVATE_KEY   the .p8 body (literal or \\n-escaped), or
    APPLE_PRIVATE_KEY_B64  the same bytes base64-encoded
"""
from __future__ import annotations

import asyncio
import base64
import binascii
import json
import logging
import os
import secrets as _secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from urllib.parse import parse_qs, urlencode

import httpx
import jwt
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

import database
from cache import delete as _cache_delete, get_json as _cache_get, set_json as _cache_set
from email_sender import send_welcome_email
from routes_shared import RouteContext
from services import _create_user_session
from utils import hash_password

_logger = logging.getLogger(__name__)


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


def _apple_private_key() -> str:
    """The .p8 body, from either env form. Empty string when unusable.

    `.env` is a single-line format and the .p8 is not, so the key arrives
    one of two ways: with its newlines escaped, or base64-encoded. Accept
    both rather than making the operator guess which one we parse.
    """
    raw = os.environ.get("APPLE_PRIVATE_KEY", "").strip()
    if raw:
        # An escaped-newline key is the common shape; a literal multi-line
        # value (docker-compose, k8s secret) already works as-is.
        return raw.replace("\\n", "\n")
    encoded = os.environ.get("APPLE_PRIVATE_KEY_B64", "").strip()
    if encoded:
        try:
            return base64.b64decode(encoded).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError, ValueError):
            _logger.warning("APPLE_PRIVATE_KEY_B64 is set but is not valid base64 UTF-8")
    return ""


def _apple_configured() -> bool:
    return bool(
        all(
            os.environ.get(k, "").strip()
            for k in ("APPLE_TEAM_ID", "APPLE_CLIENT_ID", "APPLE_KEY_ID", "APPLE_REDIRECT_URI")
        )
        and _apple_private_key()
    )


def _provider_state() -> dict[str, bool]:
    return {
        "email":  True,                # always available — email + 6-digit OTP
        "google": _google_configured(),
        "apple":  _apple_configured(),
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


def _find_or_create_user_from_google(google_user: dict[str, Any], lang: str = "en") -> tuple[int, bool]:
    """Map a Google identity to a Sooppiy user. Returns (user_id, created).

    Three cases, in priority:
      1. (provider, provider_user_id) already in oauth_identities → reuse.
      2. users.email matches Google email → link a new oauth_identity row.
      3. neither → create a new user, then link.

    `created` is True only in case 3 — the frontend routes a brand-new
    member's first visit to /getting-started, and a returning member who
    merely linked Google must not be treated as new.
    """
    sub = str(google_user.get("sub") or "")
    email = (google_user.get("email") or "").strip().lower()
    if not sub:
        raise HTTPException(status_code=502, detail="Google response missing 'sub'")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    conn = database.get_db_connection()
    cur = conn.cursor()
    try:
        # 1. existing link — but only if the linked user still exists. Users
        # can be deleted (admin console, data resets) without their
        # oauth_identities rows; blindly trusting the link would mint a
        # session for a ghost user_id that every authed endpoint then 401s.
        cur.execute(
            "SELECT oi.user_id FROM oauth_identities oi "
            "JOIN users u ON u.id = oi.user_id "
            "WHERE oi.provider='google' AND oi.provider_user_id=?",
            (sub,),
        )
        row = cur.fetchone()
        if row:
            return int(row["user_id"]), False
        # Drop any stale link for this Google account so the re-link INSERT
        # below can't collide with the UNIQUE(provider, provider_user_id) index.
        cur.execute(
            "DELETE FROM oauth_identities WHERE provider='google' AND provider_user_id=?",
            (sub,),
        )

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
                return user_id, False

        # 3. brand-new user — assign a random password since OAuth-only users
        # can't sign in via the password endpoint until they set one.
        random_password = _secrets.token_urlsafe(32)
        cur.execute(
            "INSERT INTO users (email, password_hash, points, lang) VALUES (?, ?, 0, ?)",
            (email or f"google-{sub}@sooppiy.com", hash_password(random_password), lang),
        )
        user_id = int(cur.lastrowid)
        cur.execute(
            "INSERT INTO oauth_identities (user_id, provider, provider_user_id, email, created_at) "
            "VALUES (?, 'google', ?, ?, ?)",
            (user_id, sub, email, now),
        )
        conn.commit()
        return user_id, True
    finally:
        conn.close()


# ── apple ─────────────────────────────────────────────────────────────────

_APPLE_ISSUER = "https://appleid.apple.com"
_APPLE_AUTHORIZE_URL = "https://appleid.apple.com/auth/authorize"
_APPLE_TOKEN_URL = "https://appleid.apple.com/auth/token"
_APPLE_JWKS_URL = "https://appleid.apple.com/auth/keys"

# Apple caps the client secret at 6 months. We mint one per exchange with a
# 5-minute life instead: nothing to store, nothing to rotate, and no silent
# expiry months from now that nobody connects to a login outage.
_APPLE_SECRET_TTL_SECONDS = 300

# The session handed to the SPA after Apple's POST. Redirecting with the real
# session token in the URL would leak it into browser history (and any
# referrer); a single-use nonce with a short life does not.
_HANDOFF_TTL_SECONDS = 120
_HANDOFF_KEY_PREFIX = "auth:apple-handoff"
_inproc_handoffs: dict[str, dict] = {}

_apple_jwk_client: Any = None


def _handoff_key(nonce: str) -> str:
    return f"{_HANDOFF_KEY_PREFIX}:{nonce}"


def _store_handoff(payload: dict) -> str:
    nonce = _secrets.token_urlsafe(24)
    if not _cache_set(_handoff_key(nonce), payload, ttl_seconds=_HANDOFF_TTL_SECONDS):
        _inproc_handoffs[nonce] = {
            **payload,
            "expires_at": (datetime.now(timezone.utc)
                           + timedelta(seconds=_HANDOFF_TTL_SECONDS)).isoformat(),
        }
    return nonce


def _consume_handoff(nonce: str) -> Optional[dict]:
    cached = _cache_get(_handoff_key(nonce))
    if cached is not None:
        _cache_delete(_handoff_key(nonce))
        return cached
    payload = _inproc_handoffs.pop(nonce, None)
    if not payload:
        return None
    expires = payload.get("expires_at")
    if expires:
        try:
            if datetime.fromisoformat(expires) < datetime.now(timezone.utc):
                return None
        except ValueError:
            pass
    return payload


def _apple_client_secret() -> str:
    """Sign the ES256 JWT Apple accepts in place of a static client secret."""
    now = int(time.time())
    return jwt.encode(
        {
            "iss": os.environ["APPLE_TEAM_ID"],
            "iat": now,
            "exp": now + _APPLE_SECRET_TTL_SECONDS,
            "aud": _APPLE_ISSUER,
            "sub": os.environ["APPLE_CLIENT_ID"],
        },
        _apple_private_key(),
        algorithm="ES256",
        headers={"kid": os.environ["APPLE_KEY_ID"]},
    )


def _exchange_apple_code(code: str) -> dict[str, Any]:
    """POST to Apple's token endpoint; returns the JSON body."""
    r = httpx.post(
        _APPLE_TOKEN_URL,
        data={
            "code": code,
            "client_id":     os.environ["APPLE_CLIENT_ID"],
            "client_secret": _apple_client_secret(),
            "redirect_uri":  os.environ["APPLE_REDIRECT_URI"],
            "grant_type":    "authorization_code",
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=10.0,
    )
    r.raise_for_status()
    return r.json()


def _verify_apple_id_token(id_token: str) -> dict[str, Any]:
    """Verify the id_token against Apple's JWKS and return its claims.

    Apple has no userinfo endpoint — the id_token IS the identity, so this
    signature check is the whole trust boundary. The JWK client caches keys
    so a sign-in does not fetch JWKS every time.
    """
    global _apple_jwk_client
    if _apple_jwk_client is None:
        _apple_jwk_client = jwt.PyJWKClient(_APPLE_JWKS_URL, cache_keys=True)
    signing_key = _apple_jwk_client.get_signing_key_from_jwt(id_token)
    return jwt.decode(
        id_token,
        signing_key.key,
        algorithms=["RS256"],
        audience=os.environ["APPLE_CLIENT_ID"],
        issuer=_APPLE_ISSUER,
    )


def _apple_display_name(user_field: str) -> str:
    """Pull the display name out of Apple's first-authorization `user` blob.

    Apple sends `{"name":{"firstName":..,"lastName":..},"email":..}` exactly
    once, on the first authorization ever. Malformed or absent → empty.
    """
    if not user_field:
        return ""
    try:
        blob = json.loads(user_field)
    except (json.JSONDecodeError, TypeError):
        return ""
    name = blob.get("name") or {}
    if not isinstance(name, dict):
        return ""
    parts = [str(name.get("firstName") or "").strip(),
             str(name.get("lastName") or "").strip()]
    return " ".join(p for p in parts if p).strip()


def _find_or_create_user_from_apple(
    sub: str, email: str, display_name: str = "", lang: str = "en",
) -> tuple[int, bool]:
    """Map an Apple identity to a Sooppiy user. Returns (user_id, created).

    Same three cases as the Google path, in the same priority order:
      1. (provider, provider_user_id) already linked → reuse.
      2. users.email matches → link a new oauth_identity row.
      3. neither → create the user, then link.

    `sub` is stable per developer team, so it — not the email — is the
    identity. That matters here more than it does for Google: an Apple user
    can hide their real address behind a per-app relay, and can change it.
    """
    sub = str(sub or "")
    email = (email or "").strip().lower()
    if not sub:
        raise HTTPException(status_code=502, detail="Apple response missing 'sub'")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    conn = database.get_db_connection()
    cur = conn.cursor()
    try:
        # 1. existing link — join users so a link pointing at a deleted user
        # cannot mint a session for a ghost id (same guard as the Google path).
        cur.execute(
            "SELECT oi.user_id FROM oauth_identities oi "
            "JOIN users u ON u.id = oi.user_id "
            "WHERE oi.provider='apple' AND oi.provider_user_id=?",
            (sub,),
        )
        row = cur.fetchone()
        if row:
            user_id = int(row["user_id"])
            # The name only ever arrives once; if we have it now and the row
            # does not, fill it in rather than losing it.
            if display_name:
                cur.execute(
                    "UPDATE oauth_identities SET display_name=? "
                    "WHERE provider='apple' AND provider_user_id=? "
                    "AND (display_name IS NULL OR display_name='')",
                    (display_name, sub),
                )
                conn.commit()
            return user_id, False
        # Drop a stale link so the re-link INSERT cannot collide with the
        # UNIQUE(provider, provider_user_id) index.
        cur.execute(
            "DELETE FROM oauth_identities WHERE provider='apple' AND provider_user_id=?",
            (sub,),
        )

        # 2. existing user with the same email. A private-relay address will
        # never match a real one, so those users correctly get a new account.
        if email:
            cur.execute("SELECT id FROM users WHERE email = ?", (email,))
            row = cur.fetchone()
            if row:
                user_id = int(row["id"])
                cur.execute(
                    "INSERT INTO oauth_identities "
                    "(user_id, provider, provider_user_id, email, display_name, created_at) "
                    "VALUES (?, 'apple', ?, ?, ?, ?)",
                    (user_id, sub, email, display_name or None, now),
                )
                conn.commit()
                return user_id, False

        # 3. brand-new user — random password, since an OAuth-only user cannot
        # sign in through the password endpoint until they set one.
        random_password = _secrets.token_urlsafe(32)
        cur.execute(
            "INSERT INTO users (email, password_hash, points, lang) VALUES (?, ?, 0, ?)",
            (email or f"apple-{sub}@sooppiy.com", hash_password(random_password), lang),
        )
        user_id = int(cur.lastrowid)
        cur.execute(
            "INSERT INTO oauth_identities "
            "(user_id, provider, provider_user_id, email, display_name, created_at) "
            "VALUES (?, 'apple', ?, ?, ?, ?)",
            (user_id, sub, email, display_name or None, now),
        )
        conn.commit()
        return user_id, True
    finally:
        conn.close()


async def _grant_signup_side_effects(user_id: int, email: str, lang: str, provider: str) -> None:
    """Trial + welcome email for a brand-new OAuth account.

    Shared by every provider on purpose: a member must not get a different
    starting entitlement for having signed up with Apple instead of Google.
    Both steps run off the event loop (billing and mail can hang for
    seconds) and fail soft — the account row is already committed, so a
    provider outage must not turn a successful signup into a 5xx.
    """
    if email:
        try:
            await asyncio.to_thread(send_welcome_email, email, lang)
        except Exception:  # noqa: BLE001
            _logger.warning("welcome email failed for %s signup user_id=%s",
                            provider, user_id, exc_info=True)


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
    async def google_callback(code: str, state: str, request: Request):
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

        from signup_lang import resolve_signup_lang
        # Offload the (sync, network) geo lookup off the event loop; fail-soft.
        lang = await asyncio.to_thread(resolve_signup_lang, request)
        user_id, created = _find_or_create_user_from_google(user_info, lang=lang)
        if created:
            await _grant_signup_side_effects(
                user_id, (user_info.get("email") or "").strip().lower(), lang, "google")
        session_token = _create_user_session(user_id)
        return JSONResponse({
            "token":   session_token,
            "user_id": user_id,
            "email":   (user_info.get("email") or "").strip().lower(),
            # True only when this callback just created the account — the
            # frontend sends a first-visit member to /getting-started.
            "created": created,
        })

    # ── Apple ────────────────────────────────────────────────────────────
    # The consent redirect is a plain GET like Google's. Everything after it
    # differs; see the module docstring.

    @app.get("/api/auth/apple/start")
    async def apple_start():
        if not _apple_configured():
            raise HTTPException(status_code=503, detail="Apple Sign In is not configured")
        state = _secrets.token_urlsafe(24)
        _store_state(state, {"created_at": datetime.now(timezone.utc).isoformat()})
        qs = urlencode({
            "response_type": "code",
            "client_id":     os.environ["APPLE_CLIENT_ID"],
            "redirect_uri":  os.environ["APPLE_REDIRECT_URI"],
            "scope":         "name email",
            "state":         state,
            # Mandatory once the scope asks for name or email — and the reason
            # the callback below is a POST rather than a GET.
            "response_mode": "form_post",
        })
        return RedirectResponse(url=f"{_APPLE_AUTHORIZE_URL}?{qs}", status_code=302)

    @app.post("/api/auth/apple/callback")
    async def apple_callback(request: Request):
        """Apple's form_post lands here, then we 302 the browser to the SPA.

        Parsed from the raw body rather than FastAPI's Form(...) so the
        handler carries no multipart dependency for what is plain
        application/x-www-form-urlencoded.
        """
        if not _apple_configured():
            raise HTTPException(status_code=503, detail="Apple Sign In is not configured")

        raw = (await request.body()).decode("utf-8", errors="replace")
        form = {k: v[0] for k, v in parse_qs(raw, keep_blank_values=True).items()}

        # The user tapped Cancel, or Apple refused. Not an error state for us —
        # send them back to the login page with a reason rather than a 4xx page.
        if form.get("error"):
            _logger.info("apple callback returned error=%s", form["error"])
            return RedirectResponse(url="/login?apple_error=denied", status_code=303)

        code = form.get("code", "")
        state = form.get("state", "")
        if not code or not state:
            raise HTTPException(status_code=400, detail="Apple callback missing code or state")
        if not _consume_state(state):
            raise HTTPException(status_code=400, detail="Invalid or expired state")

        try:
            token_body = await asyncio.to_thread(_exchange_apple_code, code)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=f"Apple token exchange failed: {exc}")

        id_token = token_body.get("id_token")
        if not id_token:
            raise HTTPException(status_code=502, detail="Apple response missing id_token")
        try:
            claims = await asyncio.to_thread(_verify_apple_id_token, id_token)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=f"Apple id_token verification failed: {exc}")

        sub = str(claims.get("sub") or "")
        # The token's email is authoritative; the `user` blob's is a courtesy
        # copy that only shows up on the very first authorization.
        email = (claims.get("email") or "").strip().lower()
        # First authorization only — there is no second chance to read this.
        display_name = _apple_display_name(form.get("user", ""))

        from signup_lang import resolve_signup_lang
        lang = await asyncio.to_thread(resolve_signup_lang, request)
        user_id, created = await asyncio.to_thread(
            _find_or_create_user_from_apple, sub, email, display_name, lang)
        if created:
            await _grant_signup_side_effects(user_id, email, lang, "apple")

        session_token = _create_user_session(user_id)
        # Never put the session token in the redirect URL — it would survive in
        # browser history and any referrer. The SPA redeems this one-time,
        # 2-minute nonce for it instead.
        handoff = _store_handoff({
            "token": session_token, "user_id": user_id,
            "email": email, "created": created,
        })
        return RedirectResponse(
            url=f"/auth/apple/callback?handoff={handoff}", status_code=303)

    @app.post("/api/auth/apple/session")
    async def apple_session(request: Request):
        """Redeem the one-time handoff nonce for the session token."""
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001
            body = {}
        nonce = str((body or {}).get("handoff") or "")
        payload = _consume_handoff(nonce) if nonce else None
        if not payload:
            raise HTTPException(status_code=400, detail="Invalid or expired handoff")
        return JSONResponse({
            "token":   payload.get("token"),
            "user_id": payload.get("user_id"),
            "email":   payload.get("email"),
            "created": bool(payload.get("created")),
        })
