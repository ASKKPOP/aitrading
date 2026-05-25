"""Exception hierarchy for the aitrad SDK.

All SDK errors derive from AITRADError, so callers can use a single
`except AITRADError:` to catch everything the SDK might raise.
"""
from __future__ import annotations


class AITRADError(Exception):
    """Base for every aitrad-raised exception."""


class AuthError(AITRADError):
    """Raised on 401 / 403 — bad or missing token."""


class NotFound(AITRADError):
    """Raised on 404 — resource doesn't exist."""


class APIError(AITRADError):
    """Raised on any other non-2xx response.

    Attributes:
        status_code: HTTP status code
        body: response body text (may be empty)
    """

    def __init__(self, status_code: int, body: str = ""):
        self.status_code = status_code
        self.body = body
        super().__init__(f"AITRAD API returned {status_code}: {body[:200]}")
