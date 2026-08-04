"""FMP (Financial Modeling Prep) feed — Plan 21 P6, key-gated.

The hermes work-package upstream's earnings/fundamentals skills are FMP-backed
Python engines; per the standing rule they land here as a backend feed, not
prompt material. Scope for P6 is the single highest-value signal for the
data-starved us-stock desk: **days to the next earnings print** per symbol,
so the thesis writer can price holding-through-print risk.

Degraded mode is the contract: without ``FMP_API_KEY`` every reader returns
None/{} and research proceeds exactly as before — the key's absence must
never subtract anything that exists today. One calendar call covers the
whole window and is cached for six hours; a fetch failure serves the stale
map (stale beats absent) and never raises into the research cycle.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)

# The /api/v3 tree is legacy-only (accounts created before 2025-08-31 get a
# 403 "Legacy Endpoint"); the stable tree serves the same calendar shape.
FMP_BASE = "https://financialmodelingprep.com/stable"

_CACHE_TTL_SECONDS = 6 * 3600.0
_cache: dict[str, Any] = {"at": 0.0, "by_symbol": None}

EARNINGS_WINDOW_DAYS = 14


def fmp_enabled() -> bool:
    return bool(os.getenv("FMP_API_KEY", "").strip())


def _today() -> datetime:
    return datetime.now(timezone.utc)


def upcoming_earnings(force: bool = False) -> dict[str, str]:
    """symbol -> next earnings date (YYYY-MM-DD) inside the window.

    {} without a key, on a cold failed fetch, or when FMP returns nothing.
    """
    if not fmp_enabled():
        return {}
    now = time.monotonic()
    cached = _cache["by_symbol"]
    if not force and cached is not None and now - _cache["at"] < _CACHE_TTL_SECONDS:
        return cached
    start = _today().strftime("%Y-%m-%d")
    end = (_today() + timedelta(days=EARNINGS_WINDOW_DAYS)).strftime("%Y-%m-%d")
    try:
        resp = requests.get(
            f"{FMP_BASE}/earnings-calendar",
            params={"from": start, "to": end,
                    "apikey": os.getenv("FMP_API_KEY", "").strip()},
            timeout=10)
        resp.raise_for_status()
        rows = resp.json()
        by_symbol: dict[str, str] = {}
        for row in rows if isinstance(rows, list) else []:
            sym = str(row.get("symbol") or "").strip().upper()
            date = str(row.get("date") or "").strip()
            if sym and date and (sym not in by_symbol or date < by_symbol[sym]):
                by_symbol[sym] = date
    except Exception as exc:  # noqa: BLE001
        logger.debug("fmp earnings calendar unavailable: %s", exc)
        return cached if cached is not None else {}
    _cache["by_symbol"] = by_symbol
    _cache["at"] = now
    return by_symbol


def days_to_earnings(symbol: str) -> Optional[int]:
    """Whole days until the symbol's next print, None when unknown/no key."""
    date = upcoming_earnings().get((symbol or "").strip().upper())
    if not date:
        return None
    try:
        when = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    days = (when.date() - _today().date()).days
    return days if days >= 0 else None
