"""Member notification centre — the in-app feed plus per-category preferences.

Every notification a *member* (users row) can receive belongs to one of the
categories in CATEGORY_CATALOG. Each category has three switches, mirroring
the iOS Settings → Notifications layout:

    enabled   master switch — off means nothing is delivered at all
    email     also send to the member's account email
    sms       also send to the phone stored on the 'alerts' settings target

Preferences live in user_api_settings under target 'notifications'; a member
who never touched the page has no row, so get_prefs() falls back to defaults.
For the trade/risk categories the email/sms defaults are read from the older
'alerts' target so members who opted in before this page existed keep their
delivery unchanged.

alerts.send_alert() (trade/risk/watch alerts) delegates its channel decision
here and mirrors every alert into the feed, so the notification centre is the
single place a member sees everything.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from database import begin_write_transaction, get_db_connection

logger = logging.getLogger(__name__)

PREFS_TARGET = "notifications"
LEGACY_ALERT_TARGET = "alerts"

# Ordered — the settings page renders the list in this order.
CATEGORY_CATALOG: dict[str, dict[str, Any]] = {
    "trade": {
        "label": "Trade activity",
        "description": "Order fills and position closes from your automation rules.",
        "default": {"enabled": True, "email": False, "sms": False},
    },
    "risk": {
        "label": "Risk & safety",
        "description": "Circuit-breaker halts and rejected pre-trade verifications.",
        "default": {"enabled": True, "email": False, "sms": False},
    },
    "watch": {
        "label": "Watches",
        "description": "Price and indicator watches you configured firing.",
        "default": {"enabled": True, "email": False, "sms": False},
    },
    "auto_trading_reports": {
        "label": "Auto-trading reports",
        "description": "Scheduled P&L digests from your trading runs.",
        # Digests are never SMS (per-message cost; Plan 10 D8) — the sms
        # switch stays off and the safety category below carries SMS.
        "default": {"enabled": True, "email": True, "sms": False},
    },
    "auto_trading_safety": {
        "label": "Auto-trading safety",
        "description": "Run stop events, profit/loss threshold triggers, and safety pauses.",
        "default": {"enabled": True, "email": True, "sms": False},
    },
    "support": {
        "label": "Support replies",
        "description": "Replies from the Sooppiy team in your support conversation.",
        "default": {"enabled": True, "email": True, "sms": False},
    },
    "announcement": {
        "label": "Announcements",
        "description": "Platform announcements and service notices from Sooppiy.",
        "default": {"enabled": True, "email": False, "sms": False},
    },
}

CATEGORIES = tuple(CATEGORY_CATALOG.keys())

# alerts.send_alert kinds → notification category.
ALERT_KIND_CATEGORY = {
    "trade_executed": "trade",
    "position_closed": "trade",
    "breaker": "risk",
    "verify_rejected": "risk",
    "custom": "watch",
    # Trading Runs (Plan 10 D8)
    "run_report": "auto_trading_reports",
    "run_threshold": "auto_trading_safety",
    "run_stopped": "auto_trading_safety",
    "gateway_down": "auto_trading_safety",
    "order_drift": "auto_trading_safety",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _truthy(value: Any) -> bool:
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _safe_link(link: Optional[str]) -> Optional[str]:
    """Only in-app paths may reach the feed's <Link to>.

    The frontend renders link straight into react-router's <Link to>, which for
    'javascript:...' or '//host' emits a raw <a href> (React only warns). Since
    broadcast accepts a free-form link from admins, restrict it to a single
    leading '/' (not '//', which is protocol-relative). Anything else is dropped.
    """
    if not link:
        return None
    link = link.strip()
    if link.startswith("/") and not link.startswith("//"):
        return link[:255]
    return None


def _load_target(cursor, user_id: int, target: str) -> dict[str, Any]:
    # enabled = 1 filter matters for the legacy 'alerts' target: a member who
    # turned that target OFF (PUT .../api/alerts {enabled:false}) must not have
    # its email_enabled/sms_enabled config inherited — that was the historical
    # off switch (the pre-refactor alerts._alert_prefs joined on s.enabled = 1).
    # The 'notifications' target is always written enabled = 1, so this is a
    # no-op for it.
    cursor.execute(
        "SELECT config_json FROM user_api_settings "
        "WHERE user_id = ? AND target = ? AND enabled = 1",
        (user_id, target))
    row = cursor.fetchone()
    if row is None:
        return {}
    try:
        return json.loads(row["config_json"] or "{}") or {}
    except (TypeError, ValueError):
        return {}


# ─────────────────────────── preferences ───────────────────────────

def get_prefs(user_id: int, cursor=None) -> dict[str, dict[str, bool]]:
    """Full per-category preference map, defaults filled in."""
    own_conn = cursor is None
    conn = None
    if own_conn:
        conn = get_db_connection()
        cursor = conn.cursor()
    try:
        stored = _load_target(cursor, user_id, PREFS_TARGET)
        legacy = _load_target(cursor, user_id, LEGACY_ALERT_TARGET)
        legacy_email = _truthy(legacy.get("email_enabled"))
        legacy_sms = _truthy(legacy.get("sms_enabled"))
    finally:
        if own_conn and conn is not None:
            conn.close()

    prefs: dict[str, dict[str, bool]] = {}
    for category, spec in CATEGORY_CATALOG.items():
        default = dict(spec["default"])
        # Members who opted into email/SMS before this page existed keep it.
        if category in ("trade", "risk", "watch"):
            default["email"] = legacy_email
            default["sms"] = legacy_sms
        saved = stored.get(category) or {}
        prefs[category] = {
            key: bool(saved[key]) if key in saved else default[key]
            for key in ("enabled", "email", "sms")
        }
    return prefs


def _apply_patch(merged: dict[str, dict[str, bool]],
                 patch: dict[str, dict[str, Any]]) -> dict[str, dict[str, bool]]:
    for category, switches in (patch or {}).items():
        if category not in CATEGORY_CATALOG or not isinstance(switches, dict):
            continue
        for key in ("enabled", "email", "sms"):
            if key in switches:
                merged[category][key] = bool(switches[key])
    return merged


def set_prefs(user_id: int, patch: dict[str, dict[str, Any]]) -> dict[str, dict[str, bool]]:
    """Merge a partial preference patch. Unknown categories/keys are ignored."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        merged = _apply_patch(get_prefs(user_id, cursor), patch)
        now = _now_iso()
        begin_write_transaction(cursor)
        cursor.execute(
            "SELECT id FROM user_api_settings WHERE user_id = ? AND target = ?",
            (user_id, PREFS_TARGET))
        row = cursor.fetchone()
        if row is not None:
            cursor.execute(
                "UPDATE user_api_settings SET config_json = ?, updated_at = ? WHERE id = ?",
                (json.dumps(merged), now, row["id"]))
            conn.commit()
            return merged
        try:
            cursor.execute(
                """INSERT INTO user_api_settings
                   (user_id, target, api_key, config_json, enabled, updated_at)
                   VALUES (?, ?, NULL, ?, 1, ?)""",
                (user_id, PREFS_TARGET, json.dumps(merged), now))
            conn.commit()
            return merged
        except Exception:  # noqa: BLE001 — concurrent first-write lost the UNIQUE race
            # Same recovery as _get_or_create_thread (commit 73f4573): the SELECT
            # missed on the pre-race snapshot, so the INSERT collides on
            # UNIQUE(user_id, target). Roll back to reset the MySQL read view,
            # re-read the winner's row, re-apply this patch on top of it, UPDATE.
            conn.rollback()
            cursor.execute(
                "SELECT id FROM user_api_settings WHERE user_id = ? AND target = ?",
                (user_id, PREFS_TARGET))
            row = cursor.fetchone()
            if row is None:
                raise  # genuine INSERT failure, not the duplicate-key race
            merged = _apply_patch(get_prefs(user_id, cursor), patch)
            begin_write_transaction(cursor)
            cursor.execute(
                "UPDATE user_api_settings SET config_json = ?, updated_at = ? WHERE id = ?",
                (json.dumps(merged), _now_iso(), row["id"]))
            conn.commit()
            return merged
    finally:
        conn.close()


def channel_prefs(user_id: Optional[int], category: str, cursor=None) -> dict[str, bool]:
    """Switches for one category — the decision alerts.send_alert delegates to."""
    if user_id is None or category not in CATEGORY_CATALOG:
        return {"enabled": False, "email": False, "sms": False}
    return get_prefs(user_id, cursor)[category]


def sms_phone(user_id: int) -> str:
    """The member's SMS destination — stored on the 'alerts' settings target."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        return (_load_target(cursor, user_id, LEGACY_ALERT_TARGET).get("phone") or "").strip()
    finally:
        conn.close()


def catalog_for_user(user_id: int) -> list[dict[str, Any]]:
    """Settings-page payload: catalog metadata merged with the member's switches."""
    prefs = get_prefs(user_id)
    return [
        {
            "key": key,
            "label": spec["label"],
            "description": spec["description"],
            **prefs[key],
        }
        for key, spec in CATEGORY_CATALOG.items()
    ]


# ─────────────────────────── delivery ───────────────────────────

def _send_external(user_id: int, category: str, title: str, body: str,
                   switches: dict[str, bool]) -> list[str]:
    """Email/SMS fan-out. Reuses the alerts.py senders and contact points."""
    sent: list[str] = []
    if not (switches.get("email") or switches.get("sms")):
        return sent

    from alerts import _send_email, _send_sms  # senders + provider credentials

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT email FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        email = row["email"] if row else None
        phone = (_load_target(cursor, user_id, LEGACY_ALERT_TARGET).get("phone") or "").strip()
    finally:
        conn.close()

    if switches.get("email") and email:
        try:
            if _send_email(email, f"[Sooppiy] {title}", body):
                sent.append("email")
        except Exception as exc:  # noqa: BLE001
            logger.warning("notification email failed (user %s): %s", user_id, exc)
    if switches.get("sms") and phone:
        # Plan 10 D9: SMS is tier-gated in EVERY send path (per-message cost);
        # fail-closed when the entitlement can't be verified.
        conn2 = get_db_connection()
        try:
            from entitlements import sms_allowed_for_user
            sms_ok = sms_allowed_for_user(conn2.cursor(), user_id)
        except Exception:  # noqa: BLE001
            sms_ok = False
        finally:
            conn2.close()
        if not sms_ok:
            return sent
        try:
            if _send_sms(phone, f"[Sooppiy] {title} — {body}"):
                sent.append("sms")
        except Exception as exc:  # noqa: BLE001
            logger.warning("notification sms failed (user %s): %s", user_id, exc)
    return sent


def notify(user_id: Optional[int], category: str, title: str, body: str = "",
           link: Optional[str] = None, external: bool = True) -> dict[str, Any]:
    """Write one notification to a member's feed and fan out to opted-in channels.

    Fail-soft: a notification problem must never break the caller's work.
    `external=False` journals in-app only — used by alerts.send_alert, which
    already performed its own email/SMS delivery.
    """
    if user_id is None:
        return {"skipped": "no_user", "channels": []}
    if category not in CATEGORY_CATALOG:
        return {"skipped": "unknown_category", "channels": []}

    try:
        switches = channel_prefs(user_id, category)
        if not switches["enabled"]:
            return {"skipped": "disabled", "channels": []}

        channels = ["inapp"]
        if external:
            channels.extend(_send_external(user_id, category, title, body, switches))

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            begin_write_transaction(cursor)
            cursor.execute(
                """INSERT INTO user_notifications
                   (user_id, category, title, body, link, channels_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (user_id, category, title[:200], (body or "")[:2000],
                 _safe_link(link),
                 json.dumps(channels), _now_iso()))
            conn.commit()
        finally:
            conn.close()
        return {"channels": channels}
    except Exception as exc:  # noqa: BLE001
        logger.exception("notify failed (user %s, category %s): %s", user_id, category, exc)
        return {"error": str(exc), "channels": []}


# ─────────────────────────── feed reads ───────────────────────────

def list_notifications(user_id: int, limit: int = 50,
                       unread_only: bool = False) -> list[dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        sql = "SELECT * FROM user_notifications WHERE user_id = ?"
        if unread_only:
            sql += " AND read_at IS NULL"
        sql += " ORDER BY id DESC LIMIT ?"
        cursor.execute(sql, (user_id, max(1, min(limit, 200))))
        return [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()


def unread_count(user_id: int) -> int:
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT COUNT(*) AS n FROM user_notifications WHERE user_id = ? AND read_at IS NULL",
            (user_id,))
        return int(cursor.fetchone()["n"] or 0)
    finally:
        conn.close()


def mark_read(user_id: int, ids: Optional[list[int]] = None) -> int:
    """Mark the given ids read, or every unread notification when ids is None."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        begin_write_transaction(cursor)
        if ids:
            affected = 0
            # Chunk the IN clause (SQLite host-param limit) instead of dropping
            # ids past the first 500 — every id the caller passed gets marked.
            for start in range(0, len(ids), 500):
                chunk = ids[start:start + 500]
                placeholders = ",".join("?" for _ in chunk)
                cursor.execute(
                    f"""UPDATE user_notifications SET read_at = ?
                        WHERE user_id = ? AND read_at IS NULL AND id IN ({placeholders})""",
                    [_now_iso(), user_id, *chunk])
                affected += cursor.rowcount
            conn.commit()
            return max(0, affected)
        else:
            cursor.execute(
                "UPDATE user_notifications SET read_at = ? WHERE user_id = ? AND read_at IS NULL",
                (_now_iso(), user_id))
        affected = cursor.rowcount
        conn.commit()
        return max(0, affected)
    finally:
        conn.close()
