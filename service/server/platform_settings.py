"""Operator-editable platform settings.

A tiny key/value store for configuration the operator must be able to change
from the manager console, without a deploy or a shell on the box. The first
tenant is the USDT receiving address: an address that can only be rotated by
editing .env and restarting is an address nobody rotates.

Not a secrets store. Everything here is readable by any admin and some of it
reaches unauthenticated clients (the deposit address is published on the
Subscribe page by design). API keys and credentials stay in .env.

Reads fall back to an environment variable when the key is unset, so an
existing .env-configured deployment keeps working until an admin saves a
value, at which point the stored value wins.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Optional

from database import begin_write_transaction, get_db_connection

logger = logging.getLogger(__name__)

# setting key -> environment variable consulted when the key has no stored value
_ENV_FALLBACK: dict[str, str] = {
    "usdt_address": "USDT_ADDRESS",
    "usdt_network": "USDT_NETWORK",
    "bank_transfer_info": "BANK_TRANSFER_INFO",
}

_DEFAULTS: dict[str, str] = {
    "usdt_network": "TRC20",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def get_setting(key: str) -> str:
    """Stored value, else the env fallback, else the built-in default, else ''.

    Fail-soft: a settings-table problem must not take down the Subscribe page,
    so a read error degrades to the environment rather than raising."""
    try:
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT setting_value FROM platform_settings WHERE setting_key = ?", (key,))
            row = cursor.fetchone()
        finally:
            conn.close()
        if row and (row["setting_value"] or "").strip():
            return str(row["setting_value"]).strip()
    except Exception as exc:  # noqa: BLE001
        logger.warning("platform_settings read failed for %s: %s", key, exc)
    env = _ENV_FALLBACK.get(key)
    if env and os.getenv(env, "").strip():
        return os.getenv(env, "").strip()
    return _DEFAULTS.get(key, "")


def set_setting(key: str, value: str, updated_by: Optional[str] = None) -> None:
    """Upsert one setting. Writes are admin-only at the route layer."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        begin_write_transaction(cursor)
        cursor.execute(
            "SELECT setting_key FROM platform_settings WHERE setting_key = ?", (key,))
        if cursor.fetchone():
            cursor.execute(
                "UPDATE platform_settings SET setting_value = ?, updated_by = ?, "
                "updated_at = ? WHERE setting_key = ?",
                (value, updated_by, _now_iso(), key))
        else:
            cursor.execute(
                "INSERT INTO platform_settings (setting_key, setting_value, updated_by, "
                "updated_at) VALUES (?, ?, ?, ?)", (key, value, updated_by, _now_iso()))
        conn.commit()
    finally:
        conn.close()


def get_setting_meta(key: str) -> dict:
    """Value plus who last changed it and when — shown in the console so an
    operator can tell a freshly-typed address from one set months ago."""
    out = {"value": get_setting(key), "updated_by": None, "updated_at": None,
           "source": "default"}
    try:
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT setting_value, updated_by, updated_at FROM platform_settings "
                "WHERE setting_key = ?", (key,))
            row = cursor.fetchone()
        finally:
            conn.close()
        if row and (row["setting_value"] or "").strip():
            out.update({"updated_by": row["updated_by"], "updated_at": row["updated_at"],
                        "source": "console"})
            return out
    except Exception as exc:  # noqa: BLE001
        logger.warning("platform_settings meta read failed for %s: %s", key, exc)
    env = _ENV_FALLBACK.get(key)
    if env and os.getenv(env, "").strip():
        out["source"] = "env"
    return out
