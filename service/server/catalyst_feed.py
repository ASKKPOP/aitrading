"""catalyst_feed.py — earnings surprises & the next print -> thesis score.

Feed #4 of the swing signal stack (research/SWING_SIGNAL_STACK.md §2) — "the
future of the company" — which the stack's `thesis` processor (w=0.20) had no
collector for. Source is Nasdaq's public company API (keyless):

    /api/company/{sym}/earnings-surprise   last quarters: EPS vs consensus,
                                           with "% Surprise" precomputed
    /api/analyst/{sym}/earnings-date       the NEXT print, but only ever as
                                           free text inside `announcement`

Two properties measured live 2026-08-30 shape this module:

  1. The upcoming-earnings date is frequently ABSENT ("our vendor ... hasn't
     provided us with the upcoming earnings report date"). It is therefore
     Optional everywhere and never guessed — the risk gate simply has no
     blackout input for that symbol rather than a fabricated one.
  2. `percentageSurprise` is a string and is sometimes non-numeric. Rows that
     do not parse are skipped, not defaulted to zero.

Scoring: the latest print dominates (0.6) over the four-quarter average (0.4)
— a fresh miss after three beats is a broken thesis, not a good one. No
parsable quarter means **no coverage** (score None, weight renormalized away),
never a neutral 0.

Nasdaq is an unofficial endpoint and may start refusing cloud IPs. That is
deliberately NOT hidden behind a fallback: the read degrades to no coverage
and crawl_monitor records the failure, so the admin console shows a dead feed
instead of a silently-invented score.

Env-gated (CATALYST_FEED_ENABLED, default off).
"""
from __future__ import annotations

import logging
import os
import re
from datetime import date, datetime, timezone
from typing import Any, Optional

import requests

import cache

logger = logging.getLogger(__name__)

_SURPRISE_URL = "https://api.nasdaq.com/api/company/{symbol}/earnings-surprise"
_EARNINGS_DATE_URL = "https://api.nasdaq.com/api/analyst/{symbol}/earnings-date"
_TIMEOUT_S = 12.0
_UA = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept": "application/json",
}
_READ_CACHE_KEY = "catalyst_feed:read:{symbol}"

# "Earnings announcement* for ORCL: Sep 8, 2026" / "... AVGO: Sep 02, 2026"
_DATE_RE = re.compile(r"([A-Z][a-z]{2})\s+(\d{1,2}),\s*(\d{4})")

SURPRISE_SCALE = 5.0   # a +20% surprise saturates the component
LATEST_WEIGHT = 0.6
AVERAGE_WEIGHT = 0.4
MAX_QUARTERS = 4


def enabled() -> bool:
    return os.environ.get("CATALYST_FEED_ENABLED", "false").strip().lower() in {
        "1", "true", "yes", "on",
    }


def _get_json(url: str) -> Any:
    resp = requests.get(url, headers=_UA, timeout=_TIMEOUT_S)
    resp.raise_for_status()
    return resp.json()


def _clamp(value: float, lo: float = -100.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def _as_float(raw: Any) -> Optional[float]:
    """Nasdaq sends numbers as strings, and sometimes as 'N/A' or ''."""
    if raw is None:
        return None
    try:
        return float(str(raw).replace(",", "").replace("%", "").strip())
    except (TypeError, ValueError):
        return None


def _parse_reported_date(raw: Any) -> Optional[date]:
    try:
        return datetime.strptime(str(raw).strip(), "%m/%d/%Y").date()
    except (TypeError, ValueError):
        return None


def _parse_announcement_date(text: Any) -> Optional[date]:
    match = _DATE_RE.search(str(text or ""))
    if not match:
        return None
    month, day, year = match.groups()
    try:
        return datetime.strptime(f"{month} {int(day)} {year}", "%b %d %Y").date()
    except ValueError:
        return None


def _empty_read(symbol: str) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "score": None,
        "quarters": 0,
        "beats": 0,
        "latest_surprise_pct": None,
        "avg_surprise_pct": None,
        "days_since_report": None,
        "next_earnings_date": None,
        "days_to_next_earnings": None,
        "hours_to_next_earnings": None,
        "error": None,
    }


def catalyst_read(symbol: str, today: Optional[str] = None) -> dict[str, Any]:
    """Earnings-surprise thesis read for `symbol`.

    `score` is -100..+100, or None when no quarter parsed (no coverage)."""
    symbol = (symbol or "").strip().upper()
    read = _empty_read(symbol)
    ref = (
        datetime.strptime(today, "%Y-%m-%d").date()
        if today
        else datetime.now(timezone.utc).date()
    )

    try:
        payload = _get_json(_SURPRISE_URL.format(symbol=symbol))
    except Exception as exc:  # noqa: BLE001 — degrade to no coverage
        read["error"] = f"{type(exc).__name__}: {exc}"[:200]
        logger.warning("catalyst_feed surprise fetch failed for %s: %s", symbol, exc)
        return read

    table = ((payload or {}).get("data") or {}).get("earningsSurpriseTable") or {}
    surprises: list[float] = []
    for row in (table.get("rows") or [])[:MAX_QUARTERS]:
        pct = _as_float(row.get("percentageSurprise"))
        if pct is None:
            continue
        if not surprises:
            reported = _parse_reported_date(row.get("dateReported"))
            if reported:
                read["days_since_report"] = (ref - reported).days
        surprises.append(pct)

    read["quarters"] = len(surprises)
    read["beats"] = sum(1 for s in surprises if s > 0)
    if surprises:
        latest = surprises[0]
        average = sum(surprises) / len(surprises)
        read["latest_surprise_pct"] = round(latest, 2)
        read["avg_surprise_pct"] = round(average, 2)
        read["score"] = round(
            _clamp(
                LATEST_WEIGHT * _clamp(latest * SURPRISE_SCALE)
                + AVERAGE_WEIGHT * _clamp(average * SURPRISE_SCALE)
            ),
            2,
        )

    # The next print is the symbol's binary event; absent for many symbols.
    try:
        announcement = ((_get_json(_EARNINGS_DATE_URL.format(symbol=symbol)) or {})
                        .get("data") or {}).get("announcement")
    except Exception as exc:  # noqa: BLE001 — the surprise read still stands
        logger.debug("catalyst_feed earnings-date failed for %s: %s", symbol, exc)
        announcement = None
    next_date = _parse_announcement_date(announcement)
    if next_date and next_date >= ref:
        days = (next_date - ref).days
        read["next_earnings_date"] = next_date.isoformat()
        read["days_to_next_earnings"] = days
        read["hours_to_next_earnings"] = days * 24
    return read


def thesis_score(symbol: str) -> Optional[float]:
    """Just the score, cached — earnings facts change quarterly, not hourly."""
    key = _READ_CACHE_KEY.format(symbol=(symbol or "").upper())
    cached = cache.get_json(key)
    if isinstance(cached, dict):
        return cached.get("score")
    read = catalyst_read(symbol)
    cache.set_json(key, read, ttl_seconds=6 * 3600)
    return read["score"]
