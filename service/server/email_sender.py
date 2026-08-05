"""
Email delivery module.

Primary: Resend (https://resend.com) — set RESEND_API_KEY and EMAIL_FROM.
Fallback: SendGrid via SENDGRID_API_KEY + ALERT_FROM_EMAIL — the account
that already delivers alert email (see alerts.py), so verification codes
go out on prod where Resend was never configured.
Last resort: no-op (the caller logs the code; suitable for local dev).

Install the optional dep:  pip install resend>=1.0.0
"""

from __future__ import annotations

import json
import logging
import os
import urllib.request

_logger = logging.getLogger(__name__)

RESEND_API_KEY: str = os.environ.get("RESEND_API_KEY", "").strip()
EMAIL_FROM: str = os.environ.get("EMAIL_FROM", "noreply@sooppiy.com").strip()

try:
    import resend as _resend_lib  # type: ignore[import-untyped]
    if RESEND_API_KEY:
        _resend_lib.api_key = RESEND_API_KEY
    _RESEND_AVAILABLE = bool(RESEND_API_KEY)
except ImportError:
    _resend_lib = None  # type: ignore[assignment]
    _RESEND_AVAILABLE = False


def _send_via_sendgrid(to_email: str, subject: str, text: str, html: str) -> bool:
    """Fallback rail: the SendGrid account that already delivers alert email.
    Reuses that rail's env pair — the FROM must be a SendGrid-verified
    sender, and ALERT_FROM_EMAIL is the proven one (alerts.py)."""
    key = os.environ.get("SENDGRID_API_KEY", "").strip()
    from_email = os.environ.get("ALERT_FROM_EMAIL", "").strip()
    if not key or not from_email:
        return False
    payload = {
        "personalizations": [{"to": [{"email": to_email}]}],
        "from": {"email": from_email, "name": "Sooppiy"},
        "subject": subject,
        # SendGrid requires text/plain before text/html.
        "content": [{"type": "text/plain", "value": text},
                    {"type": "text/html", "value": html}],
    }
    req = urllib.request.Request(
        "https://api.sendgrid.com/v3/mail/send",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}",
                 "Content-Type": "application/json"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return 200 <= resp.status < 300
    except Exception as exc:
        _logger.warning("[Email] SendGrid send to %s failed: %s", to_email, exc)
        return False


def _deliver(to_email: str, subject: str, text: str, html: str) -> bool:
    """Shared delivery rail: Resend first, then the SendGrid alert account,
    then no-op. Returns True if either provider accepted the email."""
    if _RESEND_AVAILABLE and _resend_lib is not None:
        try:
            _resend_lib.Emails.send({
                "from": EMAIL_FROM,
                "to": to_email,
                "subject": subject,
                "html": html,
            })
            _logger.info("[Email] Sent to %s via Resend", to_email)
            return True
        except Exception as exc:
            _logger.warning("[Email] Failed to send to %s: %s", to_email, exc)
    if _send_via_sendgrid(to_email, subject, text, html):
        _logger.info("[Email] Sent to %s via SendGrid", to_email)
        return True
    return False


def send_verification_code_email(to_email: str, code: str, lang: str = "en",
                                 purpose: str = "signup") -> bool:
    """Send a 6-digit code to *to_email*, localized to *lang*. `purpose`
    selects the copy: 'signup' (email confirmation), 'reset' (password),
    or 'invite' (admin-created account).

    Tries Resend first, then SendGrid. Returns True if either provider
    accepted the email. Callers should log the code as a fallback when
    this returns False.
    """
    from email_i18n import verification_email, verification_email_text
    subject, html = verification_email(code, lang, purpose)
    return _deliver(to_email, subject,
                    verification_email_text(code, lang, purpose), html)


def send_welcome_email(to_email: str, lang: str = "en") -> bool:
    """Post-signup welcome. Same rails as the code emails: Resend when
    configured, the SendGrid alert account otherwise, no-op last."""
    from email_i18n import welcome_email, welcome_email_text
    subject, html = welcome_email(lang)
    text = welcome_email_text(lang)
    return _deliver(to_email, subject, text, html)
