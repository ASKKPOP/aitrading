"""Optional external data sources for the multi-agent analysis engine.

Each fetcher returns empty/None when its API key is missing or the call fails, so the
analysts degrade gracefully. Wired in by analysis_agents.py.

    FinnHub     company news              (FINNHUB_API_KEY)
    StockTwits  crowd sentiment           (public, no key)
    FRED        US macro series           (FRED_API_KEY)
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)

_TIMEOUT = float(os.getenv("ANALYSIS_SOURCE_TIMEOUT", "8"))


def fetch_finnhub_news(symbol: str, limit: int = 5) -> list[dict[str, Any]]:
    key = os.getenv("FINNHUB_API_KEY", "").strip()
    if not key or not symbol:
        return []
    today = datetime.now(timezone.utc).date()
    frm = (today - timedelta(days=7)).isoformat()
    try:
        resp = requests.get(
            "https://finnhub.io/api/v1/company-news",
            params={"symbol": symbol.upper(), "from": frm, "to": today.isoformat(), "token": key},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        rows = resp.json() or []
    except Exception as exc:  # noqa: BLE001
        logger.warning("FinnHub news failed for %s: %s", symbol, exc)
        return []
    out = []
    for row in rows[:limit]:
        out.append({
            "title": row.get("headline"),
            "source": row.get("source") or "FinnHub",
            "sentiment": None,
            "category": "company (FinnHub)",
        })
    return out


def fetch_stocktwits_sentiment(symbol: str) -> Optional[dict[str, Any]]:
    if not symbol:
        return None
    try:
        resp = requests.get(
            f"https://api.stocktwits.com/api/2/streams/symbol/{symbol.upper()}.json",
            timeout=_TIMEOUT,
            headers={"User-Agent": "Sooppiy/1.0"},
        )
        if resp.status_code != 200:
            return None
        messages = (resp.json() or {}).get("messages", [])
    except Exception as exc:  # noqa: BLE001
        logger.warning("StockTwits failed for %s: %s", symbol, exc)
        return None
    bull = bear = 0
    for m in messages:
        basic = ((m.get("entities") or {}).get("sentiment") or {}).get("basic")
        if basic == "Bullish":
            bull += 1
        elif basic == "Bearish":
            bear += 1
    total = bull + bear
    if total == 0 and not messages:
        return None
    return {"bullish": bull, "bearish": bear, "messages_scored": total,
            "tilt": "bullish" if bull > bear else "bearish" if bear > bull else "neutral"}


# A small, widely-watched set of FRED series.
_FRED_SERIES = {
    "FEDFUNDS": "Fed funds rate",
    "DGS10": "10Y Treasury yield",
    "CPIAUCSL": "CPI (all items)",
    "UNRATE": "Unemployment rate",
}


def fetch_fred_macro() -> Optional[dict[str, Any]]:
    key = os.getenv("FRED_API_KEY", "").strip()
    if not key:
        return None
    out: dict[str, Any] = {}
    for series_id, label in _FRED_SERIES.items():
        try:
            resp = requests.get(
                "https://api.stlouisfed.org/fred/series/observations",
                params={"series_id": series_id, "api_key": key, "file_type": "json",
                        "sort_order": "desc", "limit": 1},
                timeout=_TIMEOUT,
            )
            resp.raise_for_status()
            obs = (resp.json() or {}).get("observations", [])
            if obs:
                out[series_id] = {"label": label, "value": obs[0].get("value"), "date": obs[0].get("date")}
        except Exception as exc:  # noqa: BLE001
            logger.warning("FRED %s failed: %s", series_id, exc)
    return out or None
