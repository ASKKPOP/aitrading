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
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse

from routes_shared import RouteContext
from services import _get_agent_by_token
from utils import _extract_token

_CONTENT_DIR = Path(__file__).resolve().parent / "guide_content"


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


def register_guide_routes(app: FastAPI, ctx: RouteContext) -> None:

    @app.get("/api/guide/docs")
    async def guide_docs(authorization: str = Header(None)):
        _require_login(authorization)
        return _load_manifest()

    @app.get("/api/guide/doc/{key}")
    async def guide_doc(key: str, authorization: str = Header(None)):
        _require_login(authorization)
        manifest = _load_manifest()
        if not any(d["key"] == key for d in manifest["docs"]):
            raise HTTPException(status_code=404, detail="Unknown document")
        path = _CONTENT_DIR / f"{key}.html"   # keys come from the manifest, never the path
        if not path.exists():
            raise HTTPException(status_code=404, detail="Document not built")
        return HTMLResponse(
            path.read_text(encoding="utf-8"),
            headers={"Cache-Control": "private, max-age=300"})
