"""Operator alerting — email/SMS to the platform admin on events that need attention.

Distinct from notifications.py (the member-facing feed): this is a single
fail-soft fan-out to the *operator's own* contact points. Today its one caller
is a new subscription request on /subscribe, which the admin must approve or
follow up on.

Recipients live in the manager console (platform_settings), NOT in .env — a
number that needs a deploy to change is a number nobody keeps current. The two
env vars survive as fallbacks:

    admin_alert_email   ← ADMIN_ALERT_EMAIL
    admin_alert_phone   ← ADMIN_ALERT_PHONE

An empty field means that channel is off. Delivery reuses the existing senders
in alerts.py (SendGrid for email, Twilio for SMS); no funds and no new provider
credentials are introduced here.

Fail-soft is the contract: alerting the operator must never break the caller's
work (a subscription submission must still succeed if Twilio is down).
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def notify_admins(subject: str, body: str) -> dict[str, list[str]]:
    """Send *subject*/*body* to the configured admin email and phone.

    Returns the channels that accepted the message, e.g. {"channels": ["email"]}.
    Never raises — a delivery problem is logged and swallowed.
    """
    try:
        from platform_settings import get_setting
        email = get_setting("admin_alert_email")
        phone = get_setting("admin_alert_phone")
    except Exception as exc:  # noqa: BLE001 — settings read must not break the caller
        logger.warning("admin alert: settings read failed: %s", exc)
        return {"channels": []}

    sent: list[str] = []

    if email:
        try:
            from alerts import _send_email
            if _send_email(email, f"[Sooppiy] {subject}", body):
                sent.append("email")
        except Exception as exc:  # noqa: BLE001
            logger.warning("admin alert email failed: %s", exc)

    if phone:
        try:
            from alerts import _send_sms
            if _send_sms(phone, f"[Sooppiy] {subject} — {body}"):
                sent.append("sms")
        except Exception as exc:  # noqa: BLE001
            logger.warning("admin alert sms failed: %s", exc)

    return {"channels": sent}
