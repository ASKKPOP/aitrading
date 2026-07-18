"""Alert engine (Plan 06 C3) — in-app + email (SendGrid) + SMS (Twilio).

Every alert is journaled to alert_log (the in-app feed). Email/SMS delivery
happens only when the owning user opted in on the Settings page (settings
target 'alerts': email_enabled / sms_enabled / phone) AND the server has the
provider credentials:

    SENDGRID_API_KEY + ALERT_FROM_EMAIL          (email; FROM must be a
                                                  SendGrid-verified sender)
    TWILIO_ACCOUNT_SID + TWILIO_AUTH_TOKEN
      + TWILIO_FROM_NUMBER                       (SMS, E.164 numbers)

Safety: hourly rate limit per user for external channels (in-app is never
rate-limited), optional dedupe keys, and everything fail-soft — an alert
problem must never break trading code paths.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from database import begin_write_transaction, get_db_connection
from notifications import ALERT_KIND_CATEGORY, notify

logger = logging.getLogger(__name__)

_TIMEOUT = 10
RATE_LIMIT_PER_HOUR = int(os.getenv("ALERTS_RATE_LIMIT", "10") or 10)

ALERT_KINDS = ("trade_executed", "position_closed", "breaker", "verify_rejected", "custom")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().strftime("%Y-%m-%dT%H:%M:%SZ")


# ─────────────────────────── channel senders ───────────────────────────

def _send_email(to_email: str, subject: str, body: str) -> bool:
    key = os.getenv("SENDGRID_API_KEY", "").strip()
    from_email = os.getenv("ALERT_FROM_EMAIL", "").strip()
    if not key or not from_email:
        return False
    payload = {
        "personalizations": [{"to": [{"email": to_email}]}],
        "from": {"email": from_email, "name": "Sooppiy"},
        "subject": subject,
        "content": [{"type": "text/plain", "value": body}],
    }
    req = urllib.request.Request(
        "https://api.sendgrid.com/v3/mail/send",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST")
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        return 200 <= resp.status < 300


def _send_sms(to_number: str, body: str) -> bool:
    sid = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
    token = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
    from_number = os.getenv("TWILIO_FROM_NUMBER", "").strip()
    if not sid or not token or not from_number:
        return False
    data = urllib.parse.urlencode({
        "From": from_number, "To": to_number, "Body": body[:1500],
    }).encode("utf-8")
    auth = base64.b64encode(f"{sid}:{token}".encode()).decode()
    req = urllib.request.Request(
        f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
        data=data,
        headers={"Authorization": f"Basic {auth}",
                 "Content-Type": "application/x-www-form-urlencoded"},
        method="POST")
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        return 200 <= resp.status < 300


# ─────────────────────────── prefs & limits ───────────────────────────

def _alert_prefs(agent_id: int, cursor, category: str) -> dict[str, Any]:
    """Owning user's alert preferences + contact points.

    The phone number stays on the 'alerts' settings target (contact info),
    but whether email/SMS fire is the member's per-category notification
    switch — one place governs delivery (notifications.py).
    """
    cursor.execute(
        """SELECT u.id AS user_id, u.email, s.config_json
           FROM agents a
           JOIN users u ON u.id = a.user_id
           LEFT JOIN user_api_settings s
             ON s.user_id = u.id AND s.target = 'alerts' AND s.enabled = 1
           WHERE a.id = ?""", (agent_id,))
    row = cursor.fetchone()
    if row is None:
        return {"user_id": None, "email": None, "email_enabled": False,
                "sms_enabled": False, "phone": None, "enabled": False}
    try:
        config = json.loads(row["config_json"] or "{}")
    except (TypeError, ValueError):
        config = {}

    from notifications import channel_prefs
    switches = channel_prefs(row["user_id"], category, cursor)
    return {
        "user_id": row["user_id"],
        "email": row["email"],
        "enabled": switches["enabled"],
        "email_enabled": switches["email"],
        "sms_enabled": switches["sms"],
        "phone": (config.get("phone") or "").strip() or None,
    }


def _external_rate_limited(user_id: int, cursor) -> bool:
    hour_ago = (_now() - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    cursor.execute(
        """SELECT COUNT(*) AS n FROM alert_log
           WHERE user_id = ? AND created_at >= ?
             AND (channels_json LIKE '%email%' OR channels_json LIKE '%sms%')""",
        (user_id, hour_ago))
    return int(cursor.fetchone()["n"] or 0) >= RATE_LIMIT_PER_HOUR


def _is_duplicate(dedupe_key: str, cursor) -> bool:
    hour_ago = (_now() - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    cursor.execute(
        "SELECT 1 FROM alert_log WHERE dedupe_key = ? AND created_at >= ? LIMIT 1",
        (dedupe_key, hour_ago))
    return cursor.fetchone() is not None


# ─────────────────────────── entry point ───────────────────────────

def send_alert(agent_id: int, kind: str, title: str, body: str,
               dedupe_key: Optional[str] = None) -> dict[str, Any]:
    """Journal an alert (in-app feed) and deliver to opted-in channels.
    Fail-soft everywhere: trading code must never break on alert trouble."""
    if kind not in ALERT_KINDS:
        kind = "custom"
    channels: list[str] = []
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        if dedupe_key and _is_duplicate(dedupe_key, cursor):
            conn.close()
            return {"skipped": "duplicate", "channels": []}
        category = ALERT_KIND_CATEGORY.get(kind, "watch")
        prefs = _alert_prefs(agent_id, cursor, category)
        channels.append("inapp")

        limited = prefs["user_id"] is not None and _external_rate_limited(prefs["user_id"], cursor)
        if not limited and prefs["enabled"]:
            if prefs["email_enabled"] and prefs["email"]:
                try:
                    if _send_email(prefs["email"], f"[Sooppiy] {title}", body):
                        channels.append("email")
                except Exception as exc:  # noqa: BLE001
                    logger.warning("alert email failed: %s", exc)
            if prefs["sms_enabled"] and prefs["phone"]:
                try:
                    if _send_sms(prefs["phone"], f"[Sooppiy] {title} — {body}"):
                        channels.append("sms")
                except Exception as exc:  # noqa: BLE001
                    logger.warning("alert sms failed: %s", exc)

        begin_write_transaction(cursor)
        cursor.execute(
            """INSERT INTO alert_log
               (agent_id, user_id, kind, title, body, channels_json, dedupe_key, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (agent_id, prefs["user_id"], kind, title[:200], body[:1000],
             json.dumps(channels), dedupe_key, _now_iso()))
        conn.commit()
        conn.close()
        # Mirror into the member notification centre. external=False: email and
        # SMS already went out above, under this same category's switches.
        notify(prefs["user_id"], category, title, body, external=False)
        return {"channels": channels, "rate_limited": limited}
    except Exception as exc:  # noqa: BLE001
        logger.exception("send_alert failed (agent %s, kind %s): %s", agent_id, kind, exc)
        return {"error": str(exc), "channels": channels}


def recent_alerts(agent_id: int, limit: int = 30) -> list[dict[str, Any]]:
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM alert_log WHERE agent_id = ? ORDER BY id DESC LIMIT ?",
            (agent_id, max(1, min(limit, 100))))
        return [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()
