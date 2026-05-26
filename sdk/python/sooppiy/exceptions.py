"""Exception hierarchy for the sooppiy SDK.

All SDK errors derive from SooppiyError, so callers can use a single
`except SooppiyError:` to catch everything the SDK might raise.
"""
from __future__ import annotations


class SooppiyError(Exception):
    """Base for every sooppiy-raised exception."""


class AuthError(SooppiyError):
    """Raised on 401 / 403 — bad or missing token."""


class NotFound(SooppiyError):
    """Raised on 404 — resource doesn't exist."""


class APIError(SooppiyError):
    """Raised on any other non-2xx response.

    Attributes:
        status_code: HTTP status code
        body: response body text (may be empty)
    """

    def __init__(self, status_code: int, body: str = ""):
        self.status_code = status_code
        self.body = body
        super().__init__(f"Sooppiy API returned {status_code}: {body[:200]}")
