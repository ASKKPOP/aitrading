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


def register_guide_routes(app: FastAPI, ctx: RouteContext) -> None:

    @app.get("/api/guide/docs")
    async def guide_docs(authorization: str = Header(None)):
        # The whole guide is owner-only: a logged-in non-owner is forbidden,
        # so nothing about the docs (not even the listing) is exposed.
        _require_login(authorization)
        if not _is_owner(authorization):
            raise HTTPException(status_code=403, detail="Owner only")
        return _load_manifest()

    @app.get("/api/guide/doc/{key}")
    async def guide_doc(key: str, authorization: str = Header(None)):
        _require_login(authorization)
        # Non-owners get 404 (not 403) so no document key — including whether
        # this one exists — is ever confirmed to a non-owner.
        if not _is_owner(authorization):
            raise HTTPException(status_code=404, detail="Unknown document")
        manifest = _load_manifest()
        if not any(d["key"] == key for d in manifest["docs"]):
            raise HTTPException(status_code=404, detail="Unknown document")
        path = _CONTENT_DIR / f"{key}.html"   # keys come from the manifest, never the path
        if not path.exists():
            raise HTTPException(status_code=404, detail="Document not built")
        return HTMLResponse(
            path.read_text(encoding="utf-8"),
            headers={"Cache-Control": "private, max-age=300"})
