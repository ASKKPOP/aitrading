"""Login-gated guide & research documents.

The public sooppiy.com/guide.html is a thin shell with no document content;
the actual pages live in service/server/guide_content/ (built by
build_guide_content.py, committed) and are served ONLY through these
authenticated endpoints — without a valid user or agent token the content
bytes are never sent. This is the real gate, not a client-side hide.

  GET /api/guide/docs        → manifest (groups + per-doc key/lang/title)
  GET /api/guide/doc/{key}   → the document HTML

Both accept either auth scheme the platform uses: a human user token or an
agent claw token, via the standard Authorization: Bearer header.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse

from routes_shared import RouteContext
from services import _get_agent_by_token
from utils import _extract_token

_CONTENT_DIR = Path(__file__).resolve().parent / "guide_content"


def _owner_emails() -> set[str]:
    """Emails allowed to see owner-only docs (e.g. the API-key reference, which
    lists which secrets are set). Env-overridable; defaults to the org owner."""
    raw = os.getenv("DOCS_OWNER_EMAILS", "info@askkpop.com")
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


def _load_manifest() -> dict:
    try:
        return json.loads((_CONTENT_DIR / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"groups": [], "docs": []}


def _visible_manifest(is_owner: bool) -> dict:
    """The manifest as this reader may see it.

    A member sees every doc NOT marked owner_only; an owner sees those too.
    Either way a doc is listed only when its file is actually on disk, and a
    group only while it still has a listed doc.

    Both filters exist because the sidebar is built from this: an entry the
    reader cannot open renders as a tab that answers 'could not load the
    document'. That happened twice — first for members, when the whole guide
    was gated on one email, then for the owner, when the E1/E2 analysis was
    registered in a manifest that shipped without its HTML file."""
    manifest = _load_manifest()
    docs = [
        d for d in manifest.get("docs", [])
        if (is_owner or not d.get("owner_only")) and (_CONTENT_DIR / f"{d['key']}.html").exists()
    ]
    live = {d.get("group") for d in docs}
    groups = [g for g in manifest.get("groups", []) if g.get("group") in live]
    return {"groups": groups, "docs": docs}


def _require_login(authorization: Optional[str]) -> None:
    """401 unless the bearer token belongs to a user OR an agent."""
    token = _extract_token(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="Login required")
    from services import _get_user_by_token
    if _get_user_by_token(token) or _get_agent_by_token(token):
        return
    raise HTTPException(status_code=401, detail="Login required")


def _is_owner(authorization: Optional[str]) -> bool:
    """True only for a USER token whose email is on the owner allowlist. Agent
    tokens have no email, so they are never owners."""
    token = _extract_token(authorization)
    if not token:
        return False
    from services import _get_user_by_token
    user = _get_user_by_token(token)
    email = (user or {}).get("email", "") if user else ""
    return bool(email) and email.strip().lower() in _owner_emails()


def _has_enterprise(authorization: Optional[str]) -> bool:
    """True when the reader holds an ACTIVE enterprise subscription — via
    their own user token, or (for a claw token) the agent's linked user.
    Owner exemption is the caller's job (_is_owner), not this check's."""
    token = _extract_token(authorization)
    if not token:
        return False
    from services import _get_user_by_token
    user = _get_user_by_token(token)
    user_id = user["id"] if user else None
    if user_id is None:
        agent = _get_agent_by_token(token)
        user_id = (agent or {}).get("user_id")
    if not user_id:
        return False
    import database
    from routes_subscriptions import get_subscription_state
    conn = database.get_db_connection()
    try:
        cursor = conn.cursor()
        state = get_subscription_state(cursor, user_id)
        conn.commit()  # get_subscription_state lazy-expires stale rows
        sub = state.get("subscription") or {}
        return state.get("status") == "active" and sub.get("plan_code") == "enterprise"
    finally:
        conn.close()


def _require_enterprise(authorization: Optional[str], is_owner: bool) -> None:
    """403 unless the reader is the owner or an enterprise subscriber
    (owner decision 2026-08-02: the /docs/guide library is an Enterprise
    perk — junior/pro/professional members see an upgrade notice)."""
    if is_owner or _has_enterprise(authorization):
        return
    raise HTTPException(status_code=403, detail="enterprise_required")


def register_guide_routes(app: FastAPI, ctx: RouteContext) -> None:

    @app.get("/api/guide/docs")
    async def guide_docs(authorization: str = Header(None)):
        # Members see the member documents; owner_only docs stay owner-only
        # (2026-07-27). Previously the WHOLE guide was gated on a single
        # allowlisted email, so every other member got 403 and the UI showed
        # "could not load the document" — while the same page advertised
        # itself as members-only. Three of four accounts could not open any
        # guide at all, including the ones written for them.
        _require_login(authorization)
        is_owner = _is_owner(authorization)
        # The manifest feeds the /docs/guide rail only, so it carries the
        # enterprise gate too; the gwsetup docs opened from /accounts fetch
        # by key and never touch this endpoint.
        _require_enterprise(authorization, is_owner)
        return _visible_manifest(is_owner)

    @app.get("/api/guide/doc/{key}")
    async def guide_doc(key: str, authorization: str = Header(None)):
        _require_login(authorization)
        is_owner = _is_owner(authorization)
        # An owner_only key is 404 (not 403) for a member, so its existence is
        # never confirmed to someone who may not read it.
        manifest = _visible_manifest(is_owner)
        entry = next((d for d in manifest["docs"] if d["key"] == key), None)
        if entry is None:
            raise HTTPException(status_code=404, detail="Unknown document")
        # Two kinds of docs are fetched BY KEY from the page they document,
        # not from the /docs rail, and stay open to every signed-in member:
        # the gwsetup connection guides on /accounts, and the /automation
        # page manual, which opens in place from that page's guide drawer
        # (owner ask 2026-08-10). The enterprise gate covers the /docs/guide
        # library only.
        group = str(entry.get("group") or "")
        if not (group.startswith("gwsetup") or group == "automation"):
            _require_enterprise(authorization, is_owner)
        path = _CONTENT_DIR / f"{key}.html"   # keys come from the manifest, never the path
        if not path.exists():
            raise HTTPException(status_code=404, detail="Document not built")
        return HTMLResponse(
            path.read_text(encoding="utf-8"),
            headers={"Cache-Control": "private, max-age=300"})
