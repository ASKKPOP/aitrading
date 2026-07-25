"""Resolve a member's default notification language at signup.

Order (Henry's directive — IP country first, browser language fallback):
  1. IP-geolocated country → language (KR→ko, JP→ja, TH→th, VN→vi, else en)
  2. Accept-Language header → language
  3. 'en'

Fail-soft: any geo lookup error or timeout is swallowed and we drop to the
header. No new dependency — httpx is already in requirements. The lookup uses
a free no-key endpoint with a short timeout; if it is unreachable the header
still gives a good default.
"""
from __future__ import annotations

import ipaddress
import logging
import os

import httpx

from analysis_agents import normalize_lang
from i18n_errors import _parse_accept_language

logger = logging.getLogger(__name__)

# Only the countries whose primary language is one we support need an entry;
# everything else (incl. unknown) resolves to English.
_COUNTRY_LANG = {"KR": "ko", "JP": "ja", "TH": "th", "VN": "vi"}

_GEO_TIMEOUT = float(os.getenv("SIGNUP_GEO_TIMEOUT", "1.5") or 1.5)
# ip-api.com: free, no key, returns {"countryCode": "KR", ...}. Overridable so
# tests never hit the network and prod can point at a paid endpoint later.
_GEO_URL = os.getenv("SIGNUP_GEO_URL", "http://ip-api.com/json/{ip}?fields=countryCode")


def _country_to_lang(country_code: str | None) -> str | None:
    if not country_code:
        return None
    cc = country_code.strip().upper()
    if not cc:
        return None
    return _COUNTRY_LANG.get(cc, "en")


def _client_ip(request) -> str | None:
    # Behind nginx the real client is the first X-Forwarded-For hop.
    xff = request.headers.get("x-forwarded-for")
    if xff:
        first = xff.split(",")[0].strip()
        if first:
            return first
    client = getattr(request, "client", None)
    return getattr(client, "host", None) if client else None


def _geo_country(ip: str | None) -> str | None:
    """Country code for an IP, or None on any failure. Never raises."""
    if not ip:
        return None
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return None  # not a parseable IP — no point calling geo
    if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
        return None
    try:
        resp = httpx.get(_GEO_URL.format(ip=ip), timeout=_GEO_TIMEOUT)
        if resp.status_code != 200:
            return None
        return (resp.json() or {}).get("countryCode") or None
    except Exception as exc:  # noqa: BLE001 — geo must never break signup
        logger.info("signup geo lookup failed for %s: %s", ip, exc)
        return None


def resolve_signup_lang(request) -> str:
    """Best default language for a signing-up user: IP country, else header, else en."""
    try:
        by_country = _country_to_lang(_geo_country(_client_ip(request)))
        if by_country:
            return normalize_lang(by_country)
        return normalize_lang(_parse_accept_language(request.headers.get("accept-language")))
    except Exception as exc:  # noqa: BLE001
        logger.info("resolve_signup_lang failed: %s", exc)
        return "en"
