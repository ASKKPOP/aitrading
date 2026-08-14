"""site_config.py — the one place the platform's own public URL comes from.

Every outbound link the platform emits — Stripe checkout/portal returns, and
the CTA and footer of every transactional email — has to point at the site the
member actually used. Three modules used to answer that question separately:
routes_subscriptions defaulted to ``http://localhost:3000`` and the two email
modules hardcoded ``https://sooppiy.com``.

That cost a live defect on 2026-08-13: SOOPPIY_FRONTEND_URL was never set on
prod, so every member returning from Stripe was redirected to *their own*
machine. Nothing errored — a wrong-but-plausible default is worse than a
missing one, because it fails silently and only the user sees it.

So there is no default here. An unset value raises at call time, which is the
same contract docker-compose.yml already enforces with its ``:?set in .env``
markers. Set SOOPPIY_FRONTEND_URL in .env; tests set it in conftest.
"""
from __future__ import annotations

import os

ENV_VAR = "SOOPPIY_FRONTEND_URL"


def site_url() -> str:
    """Public base URL of the platform, no trailing slash.

    Raises RuntimeError when unset, rather than guessing. A deploy that forgets
    it should fail loudly on the first email or checkout, not quietly send
    members somewhere useless.
    """
    raw = (os.getenv(ENV_VAR) or "").strip().rstrip("/")
    if not raw:
        raise RuntimeError(
            f"{ENV_VAR} is not set. It is the base URL used for Stripe return "
            "links and every transactional email; there is deliberately no "
            "default, because the previous localhost fallback silently "
            "redirected production members to their own machine."
        )
    if not raw.startswith(("http://", "https://")):
        raise RuntimeError(f"{ENV_VAR} must start with http:// or https:// (got {raw!r})")
    return raw
