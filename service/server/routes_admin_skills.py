"""Admin console — trading skills registry (Plan 20).

Routes:
    GET    /api/admin/skills              list every skill (base + custom)
    POST   /api/admin/skills              create a custom skill
    PATCH  /api/admin/skills/{slug}       edit a skill (base skills editable)
    POST   /api/admin/skills/{slug}/reset restore a base skill's defaults
    DELETE /api/admin/skills/{slug}       delete a custom skill (base: 400)

Skill bodies reach the desk's decision prompts, so writes are admin-only,
size-capped, and audited. The worker process picks changes up through the
registry's 30 s TTL cache; this process is invalidated immediately.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

import trading_skills
from admin_auth import audit, require_admin
from routes_shared import RouteContext

_SLUG_RE = re.compile(r"[a-z0-9][a-z0-9-]{0,47}")


class SkillCreateBody(BaseModel):
    slug: str
    name: str
    body: str
    description: str = ""
    prompts: list[str] = []
    markets: Optional[list[str]] = None
    priority: int = 100
    enabled: bool = True


class SkillPatchBody(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    body: Optional[str] = None
    prompts: Optional[list[str]] = None
    markets: Optional[list[str]] = None
    priority: Optional[int] = None
    enabled: Optional[bool] = None


def _validate_common(name: Optional[str], description: Optional[str],
                     body: Optional[str], prompts: Optional[list[str]],
                     markets: Optional[list[str]]) -> None:
    if name is not None and not (1 <= len(name.strip()) <= trading_skills.MAX_NAME_LEN):
        raise HTTPException(status_code=400,
                            detail=f"name must be 1-{trading_skills.MAX_NAME_LEN} chars")
    if description is not None and len(description) > trading_skills.MAX_DESCRIPTION_LEN:
        raise HTTPException(status_code=400,
                            detail=f"description exceeds {trading_skills.MAX_DESCRIPTION_LEN} chars")
    if body is not None and not (1 <= len(body.strip()) <= trading_skills.MAX_BODY_LEN):
        raise HTTPException(status_code=400,
                            detail=f"body must be 1-{trading_skills.MAX_BODY_LEN} chars")
    if prompts is not None:
        bad = [p for p in prompts if p not in trading_skills.PROMPT_SITES]
        if bad:
            raise HTTPException(
                status_code=400,
                detail=f"unknown prompt site(s) {bad}; valid: {list(trading_skills.PROMPT_SITES)}")
    if markets is not None:
        if not all(isinstance(m, str) and m.strip() for m in markets):
            raise HTTPException(status_code=400, detail="markets must be non-empty strings")


def register_admin_skill_routes(app: FastAPI, ctx: RouteContext) -> None:

    @app.get('/api/admin/skills')
    async def admin_skills_list(authorization: str = Header(None)):
        require_admin(authorization)
        return {"skills": trading_skills.all_skills(fresh=True)}

    @app.post('/api/admin/skills')
    async def admin_skills_create(body: SkillCreateBody,
                                  authorization: str = Header(None)):
        admin = require_admin(authorization)
        slug = body.slug.strip().lower()
        if not _SLUG_RE.fullmatch(slug):
            raise HTTPException(
                status_code=400,
                detail="slug must be lowercase letters/digits/dashes, max 48 chars")
        _validate_common(body.name, body.description, body.body,
                         body.prompts, body.markets)
        if not body.prompts:
            raise HTTPException(status_code=400,
                                detail="prompts must name at least one site")
        if trading_skills.get_skill(slug) is not None:
            raise HTTPException(status_code=409, detail="slug already exists")
        trading_skills.create_skill(
            slug, body.name.strip(), body.body.strip(),
            description=body.description.strip(), prompts=body.prompts,
            markets=body.markets, priority=body.priority,
            enabled=body.enabled, updated_by=admin.get("email"))
        audit(admin, "skill.create", f"skill:{slug}",
              f"prompts={body.prompts} enabled={body.enabled}")
        return {"ok": True, "skill": trading_skills.get_skill(slug)}

    @app.patch('/api/admin/skills/{slug}')
    async def admin_skills_patch(slug: str, body: SkillPatchBody,
                                 authorization: str = Header(None)):
        admin = require_admin(authorization)
        existing = trading_skills.get_skill(slug)
        if existing is None:
            raise HTTPException(status_code=404, detail="Unknown skill")
        _validate_common(body.name, body.description, body.body,
                         body.prompts, body.markets)
        fields: dict[str, Any] = {}
        if body.name is not None:
            fields["name"] = body.name.strip()
        if body.description is not None:
            fields["description"] = body.description.strip()
        if body.body is not None:
            fields["body"] = body.body.strip()
        if body.prompts is not None:
            if not body.prompts:
                raise HTTPException(status_code=400,
                                    detail="prompts must name at least one site")
            import json as _json
            fields["prompts_json"] = _json.dumps(body.prompts)
        if body.markets is not None:
            import json as _json
            fields["markets_json"] = _json.dumps(body.markets) if body.markets else None
        if body.priority is not None:
            fields["priority"] = int(body.priority)
        if body.enabled is not None:
            fields["enabled"] = 1 if body.enabled else 0
        if not fields:
            raise HTTPException(status_code=400, detail="nothing to update")
        trading_skills.update_skill(slug, fields, updated_by=admin.get("email"))
        audit(admin, "skill.update", f"skill:{slug}",
              f"fields={sorted(fields.keys())}")
        return {"ok": True, "skill": trading_skills.get_skill(slug)}

    @app.post('/api/admin/skills/{slug}/reset')
    async def admin_skills_reset(slug: str, authorization: str = Header(None)):
        admin = require_admin(authorization)
        if trading_skills.get_skill(slug) is None:
            raise HTTPException(status_code=404, detail="Unknown skill")
        if not trading_skills.reset_skill(slug, updated_by=admin.get("email")):
            raise HTTPException(status_code=400,
                                detail="Only base skills can be reset")
        audit(admin, "skill.reset", f"skill:{slug}")
        return {"ok": True, "skill": trading_skills.get_skill(slug)}

    @app.delete('/api/admin/skills/{slug}')
    async def admin_skills_delete(slug: str, authorization: str = Header(None)):
        admin = require_admin(authorization)
        existing = trading_skills.get_skill(slug)
        if existing is None:
            raise HTTPException(status_code=404, detail="Unknown skill")
        if existing["is_base"]:
            raise HTTPException(
                status_code=400,
                detail="Base skills cannot be deleted — disable or reset them instead")
        trading_skills.delete_skill(slug)
        audit(admin, "skill.delete", f"skill:{slug}")
        return {"ok": True}
