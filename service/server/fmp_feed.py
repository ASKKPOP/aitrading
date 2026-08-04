"""FMP (Financial Modeling Prep) feed — Plan 21 P6, key-gated.

The hermes work-package upstream's earnings/fundamentals skills are FMP-backed
Python engines; per the standing rule they land here as a backend feed, not
prompt material. Scope for P6 is the single highest-value signal for the
data-starved us-stock desk: **days to the next earnings print** per symbol,
so the thesis writer can price holding-through-print risk.

Degraded mode is the contract: without a key every reader returns
None/{} and research proceeds exactly as before — the key's absence must
never subtract anything that exists today. One calendar call covers the
whole window and is cached for six hours; a fetch failure serves the stale
map (stale beats absent) and never raises into the research cycle.

Alpha Vantage fallback (2026-08-04): FMP_API_KEY has never been set on prod,
so this feed shipped dead — the us-stock desks (939 TSLA / 940 NVDA) hold
positions with zero knowledge of scheduled prints. Prod DOES carry
ALPHA_VANTAGE_API_KEY for stock prices, and its EARNINGS_CALENDAR endpoint
serves the same symbol→date map as CSV.

Union (2026-08-04): "FMP preferred, AV fallback" proved wrong the first day
it faced a real print — FMP's plan tier served 16 symbols in a peak-season
window and missed SPCX reporting THAT DAY, while AV's window carried 2,674
symbols including it. Every keyed source is now fetched and unioned (FMP
wins per-symbol conflicts), with per-source stale maps so AV's daily
rate-limit cannot evict print knowledge mid-day. Same degraded contract.
"""

from __future__ import annotations

import csv
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
# by_symbol is the served union; fmp/av hold each source's last good map so
# one source failing a refresh (AV's free key rate-limits daily) can never
# evict the other's — or its own prior — knowledge mid-day.
_cache: dict[str, Any] = {"at": 0.0, "by_symbol": None, "fmp": None, "av": None}

EARNINGS_WINDOW_DAYS = 14


def fmp_enabled() -> bool:
    return bool(os.getenv("FMP_API_KEY", "").strip())


def _alphavantage_key() -> str:
    # price_fetcher ships a "demo" default; a demo key serves nothing real.
    key = os.getenv("ALPHA_VANTAGE_API_KEY", "").strip()
    return "" if key == "demo" else key


def feed_enabled() -> bool:
    return fmp_enabled() or bool(_alphavantage_key())


def _today() -> datetime:
    return datetime.now(timezone.utc)


def _within_window(date: str, start: str, end: str) -> bool:
    return bool(date) and start <= date <= end


def _fetch_fmp(start: str, end: str) -> dict[str, str]:
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
    return by_symbol


def _fetch_alphavantage(start: str, end: str) -> dict[str, str]:
    # CSV: symbol,name,reportDate,fiscalDateEnding,estimate,currency.
    # The 3-month horizon is the smallest offered; the window filter below
    # keeps parity with the FMP query's 14-day range.
    resp = requests.get(
        "https://www.alphavantage.co/query",
        params={"function": "EARNINGS_CALENDAR", "horizon": "3month",
                "apikey": _alphavantage_key()},
        timeout=30)
    resp.raise_for_status()
    by_symbol: dict[str, str] = {}
    reader = csv.reader(resp.text.splitlines())
    header = next(reader, None) or []
    try:
        sym_i = header.index("symbol")
        date_i = header.index("reportDate")
    except ValueError:
        return {}
    for row in reader:
        if len(row) <= max(sym_i, date_i):
            continue
        sym = row[sym_i].strip().upper()
        date = row[date_i].strip()
        if (sym and _within_window(date, start, end)
                and (sym not in by_symbol or date < by_symbol[sym])):
            by_symbol[sym] = date
    return by_symbol


def upcoming_earnings(force: bool = False) -> dict[str, str]:
    """symbol -> next earnings date (YYYY-MM-DD) inside the window.

    {} without any key, on a cold failed fetch, or when the sources return
    nothing. Every keyed source is fetched and the maps unioned — FMP's date
    wins per-symbol conflicts (2026-08-04: FMP's thin tier served 16 symbols
    and missed a fleet symbol printing that day; AV's window carried 2,674).
    A source that fails a refresh contributes its last good map instead;
    only when every live fetch fails does the whole stale union serve.
    """
    if not feed_enabled():
        return {}
    now = time.monotonic()
    cached = _cache["by_symbol"]
    if not force and cached is not None and now - _cache["at"] < _CACHE_TTL_SECONDS:
        return cached
    start = _today().strftime("%Y-%m-%d")
    end = (_today() + timedelta(days=EARNINGS_WINDOW_DAYS)).strftime("%Y-%m-%d")
    fmp_map, av_map = _cache["fmp"], _cache["av"]
    sources = failures = 0
    if fmp_enabled():
        sources += 1
        try:
            fmp_map = _cache["fmp"] = _fetch_fmp(start, end)
        except Exception as exc:  # noqa: BLE001
            failures += 1
            logger.debug("FMP earnings calendar unavailable: %s", exc)
    if _alphavantage_key():
        sources += 1
        try:
            av_map = _cache["av"] = _fetch_alphavantage(start, end)
        except Exception as exc:  # noqa: BLE001
            failures += 1
            logger.debug("Alpha Vantage earnings calendar unavailable: %s", exc)
    if failures == sources:
        return cached if cached is not None else {}
    by_symbol = dict(av_map or {})
    by_symbol.update(fmp_map or {})
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
