"""
Email delivery module.

Primary: Resend (https://resend.com) — set RESEND_API_KEY and EMAIL_FROM.
Fallback: no-op (the caller logs the code; suitable for local dev).

Install the optional dep:  pip install resend>=1.0.0
"""

from __future__ import annotations

import logging
import os

_logger = logging.getLogger(__name__)

RESEND_API_KEY: str = os.environ.get("RESEND_API_KEY", "").strip()
EMAIL_FROM: str = os.environ.get("EMAIL_FROM", "noreply@aitrad.ai").strip()

try:
    import resend as _resend_lib  # type: ignore[import-untyped]
    if RESEND_API_KEY:
        _resend_lib.api_key = RESEND_API_KEY
    _RESEND_AVAILABLE = bool(RESEND_API_KEY)
except ImportError:
    _resend_lib = None  # type: ignore[assignment]
    _RESEND_AVAILABLE = False


def send_verification_code_email(to_email: str, code: str) -> bool:
    """Send a 6-digit verification code to *to_email*.

    Returns True if the email was accepted by Resend, False otherwise.
    Callers should log the code as a fallback when this returns False.
    """
    if not _RESEND_AVAILABLE or _resend_lib is None:
        return False
    try:
        _resend_lib.Emails.send({
            "from": EMAIL_FROM,
            "to": to_email,
            "subject": "Your AITRAD verification code",
            "html": (
                f"<p>Your verification code is: <strong>{code}</strong></p>"
                "<p>It expires in 5 minutes. Do not share it.</p>"
            ),
        })
        _logger.info("[Email] Verification code sent to %s", to_email)
        return True
    except Exception as exc:
        _logger.warning("[Email] Failed to send to %s: %s", to_email, exc)
        return False
