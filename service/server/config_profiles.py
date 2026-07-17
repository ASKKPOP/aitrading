"""Named config profiles (Plan 06 C3 — Configuration).

A profile is a named snapshot of the knobs a user tunes together: their risk
limits and their trading guidelines. Save the current setup under a name,
switch between them, export one as JSON, import it back (or on another
account).

The one design decision that matters here (P-1): **risk limits ARE the
deterministic safety limits**. A profile that wrote them straight from JSON
would be a validation bypass wearing a convenience feature's clothes — paste
`{"max_daily_loss_usd": 1e12}` into an import and the limit is gone. So every
path that writes limits — apply AND import — goes through the exact same
`RiskLimitsIn` model the normal PUT /api/risk/limits endpoint uses. A profile
can only ever contain settings the user could have typed by hand.

Storage is per-agent (limits are agent-scoped); guidelines are user-scoped and
reached through agents.user_id, matching how the rest of the personalized
suite resolves the pair.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from database import get_db_connection

logger = logging.getLogger(__name__)

MAX_PROFILES_PER_AGENT = 20
MAX_NAME_LEN = 60
MAX_GUIDELINES_LEN = 2000        # same ceiling as PUT /api/users/guidelines


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class ProfileError(Exception):
    """Rejected profile — the caller maps this to a 400."""


def validate_limits(limits: dict[str, Any]) -> dict[str, Any]:
    """Run limits through the SAME model the risk endpoint uses.

    Importing must not be a way to write a limit the PUT endpoint would have
    refused. Unknown keys are dropped rather than stored: a profile carrying
    junk would quietly become junk-on-apply later.
    """
    from routes_risk import RiskLimitsIn
    from pydantic import ValidationError
    try:
        model = RiskLimitsIn(**{k: v for k, v in (limits or {}).items()
                                if k in RiskLimitsIn.model_fields})
    except ValidationError as exc:
        first = exc.errors()[0]
        field = ".".join(str(p) for p in first.get("loc") or ()) or "limits"
        raise ProfileError(f"{field}: {first.get('msg')}") from exc
    return {k: v for k, v in model.model_dump().items() if v is not None}


def _clean_name(name: Any) -> str:
    text = str(name or "").strip()
    if not text:
        raise ProfileError("profile name is required")
    if len(text) > MAX_NAME_LEN:
        raise ProfileError(f"profile name must be <= {MAX_NAME_LEN} characters")
    return text


def _clean_guidelines(text: Any) -> str:
    out = str(text or "").strip()
    if len(out) > MAX_GUIDELINES_LEN:
        raise ProfileError(f"guidelines must be <= {MAX_GUIDELINES_LEN} characters")
    return out


def capture_current(agent_id: int) -> dict[str, Any]:
    """The live setup, in profile shape."""
    from risk_engine import get_risk_limits
    limits = get_risk_limits(agent_id)
    conn = get_db_connection()
    try:
        row = conn.execute(
            """SELECT u.trading_guidelines FROM users u
               JOIN agents a ON a.user_id = u.id WHERE a.id = ?""", (agent_id,)).fetchone()
    finally:
        conn.close()
    return {"limits": {k: v for k, v in limits.items() if k != "updated_at"},
            "guidelines": (row["trading_guidelines"] or "") if row else ""}


def list_profiles(agent_id: int) -> list[dict[str, Any]]:
    conn = get_db_connection()
    try:
        rows = conn.execute(
            """SELECT id, name, payload_json, created_at, updated_at
               FROM config_profiles WHERE agent_id = ? ORDER BY name""", (agent_id,)).fetchall()
    finally:
        conn.close()
    out = []
    for r in rows:
        try:
            payload = json.loads(r["payload_json"])
        except (TypeError, ValueError):      # a row we cannot read is not a row we serve
            logger.warning("config profile %s has unreadable payload", r["id"])
            continue
        out.append({"id": r["id"], "name": r["name"], "created_at": r["created_at"],
                    "updated_at": r["updated_at"], **payload})
    return out


def save_profile(agent_id: int, name: Any, payload: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Create or overwrite a named profile. `payload` defaults to the live
    setup — that is the 'save my current config' path."""
    clean = _clean_name(name)
    body = payload if payload is not None else capture_current(agent_id)
    stored = {"limits": validate_limits(body.get("limits") or {}),
              "guidelines": _clean_guidelines(body.get("guidelines"))}

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        existing = cursor.execute(
            "SELECT id FROM config_profiles WHERE agent_id = ? AND name = ?",
            (agent_id, clean)).fetchone()
        if existing is None:
            count = cursor.execute(
                "SELECT COUNT(*) AS n FROM config_profiles WHERE agent_id = ?",
                (agent_id,)).fetchone()["n"]
            if count >= MAX_PROFILES_PER_AGENT:
                raise ProfileError(f"profile limit reached ({MAX_PROFILES_PER_AGENT})")
        now = _now_iso()
        cursor.execute(
            """INSERT INTO config_profiles (agent_id, name, payload_json, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(agent_id, name) DO UPDATE SET
                   payload_json = excluded.payload_json, updated_at = excluded.updated_at""",
            (agent_id, clean, json.dumps(stored, ensure_ascii=False), now, now))
        conn.commit()
        row = cursor.execute(
            "SELECT id, created_at, updated_at FROM config_profiles WHERE agent_id = ? AND name = ?",
            (agent_id, clean)).fetchone()
    finally:
        conn.close()
    return {"id": row["id"], "name": clean, "created_at": row["created_at"],
            "updated_at": row["updated_at"], **stored}


def apply_profile(agent_id: int, profile_id: int) -> dict[str, Any]:
    """Write a profile's contents to the live setup.

    Re-validates on the way out, not just on the way in: a profile stored
    before a limit's bounds were tightened must not slip through on apply.
    """
    conn = get_db_connection()
    try:
        row = conn.execute(
            "SELECT name, payload_json FROM config_profiles WHERE id = ? AND agent_id = ?",
            (profile_id, agent_id)).fetchone()
    finally:
        conn.close()
    if row is None:
        raise ProfileError("profile not found")
    try:
        payload = json.loads(row["payload_json"])
    except (TypeError, ValueError) as exc:
        raise ProfileError("profile payload is unreadable") from exc

    limits = validate_limits(payload.get("limits") or {})
    guidelines = _clean_guidelines(payload.get("guidelines"))

    from risk_engine import put_risk_limits
    applied = put_risk_limits(agent_id, limits)

    conn = get_db_connection()
    try:
        conn.execute(
            """UPDATE users SET trading_guidelines = ?
               WHERE id = (SELECT user_id FROM agents WHERE id = ?)""",
            (guidelines or None, agent_id))
        conn.commit()
    finally:
        conn.close()
    return {"applied": row["name"], "limits": applied, "guidelines": guidelines}


def delete_profile(agent_id: int, profile_id: int) -> bool:
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM config_profiles WHERE id = ? AND agent_id = ?",
                       (profile_id, agent_id))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def import_profile(agent_id: int, blob: dict[str, Any]) -> dict[str, Any]:
    """Create a profile from exported JSON. Importing only STORES it — the
    user still has to apply it, so a paste never silently changes live limits.
    """
    if not isinstance(blob, dict):
        raise ProfileError("import payload must be a JSON object")
    return save_profile(agent_id, blob.get("name"),
                        {"limits": blob.get("limits") or {},
                         "guidelines": blob.get("guidelines")})
