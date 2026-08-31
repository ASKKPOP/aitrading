"""routes_admin_swing_feeds.py — crawl-status monitoring for the six swing
signal stack feeds (research/SWING_SIGNAL_STACK.md section 2), on the admin
console.

  GET /api/admin/swing-feeds/status   probe all six sources, return per-feed
                                      ok / latency / freshness detail

Each probe is a cheap live GET against the feed's public source with a tight
timeout, run concurrently; results are cached in-process for 60s so console
refreshes don't hammer the upstreams. Probes are fail-soft: a dead source is
a row with ok=false + error, never a 500.

Auth: admin session (same gate as the rest of the console).
"""
from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Optional

import requests
from fastapi import FastAPI, Header

from admin_auth import require_admin
from routes_shared import RouteContext

_TIMEOUT_S = 6.0
_CACHE_TTL_S = 60.0
_UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

_cache_lock = threading.Lock()
_cache: dict[str, Any] = {"at": 0.0, "payload": None}


def _fetch_json(url: str, params: Optional[dict] = None) -> Any:
    resp = requests.get(url, params=params, headers=_UA, timeout=_TIMEOUT_S)
    resp.raise_for_status()
    return resp.json()


def _probe_price_us() -> str:
    data = _fetch_json(
        "https://query1.finance.yahoo.com/v8/finance/chart/NVDA",
        {"interval": "1d", "range": "5d"},
    )
    stamps = data["chart"]["result"][0]["timestamp"]
    last = datetime.fromtimestamp(int(stamps[-1]), tz=timezone.utc)
    return f"last bar {last.date().isoformat()}"


def _probe_price_crypto() -> str:
    data = _fetch_json(
        "https://www.okx.com/api/v5/market/candles",
        {"instId": "BTC-USDT-SWAP", "bar": "1Dutc", "limit": "2"},
    )
    rows = data["data"]
    last = datetime.fromtimestamp(int(rows[0][0]) / 1000, tz=timezone.utc)
    return f"last bar {last.date().isoformat()}, BTC close {float(rows[0][4]):,.0f}"


def _probe_macro_regime() -> str:
    data = _fetch_json(
        "https://query1.finance.yahoo.com/v8/finance/chart/%5EVIX",
        {"interval": "1d", "range": "5d"},
    )
    result = data["chart"]["result"][0]
    closes = [c for c in result["indicators"]["quote"][0]["close"] if c is not None]
    return f"VIX {closes[-1]:.1f}"


def _probe_sentiment_stock() -> str:
    data = _fetch_json("https://production.dataviz.cnn.io/index/fearandgreed/graphdata")
    now = data["fear_and_greed"]
    return f"CNN F&G {float(now['score']):.0f} ({now.get('rating', '?')})"


def _probe_sentiment_crypto() -> str:
    data = _fetch_json("https://api.alternative.me/fng/", {"limit": "1", "format": "json"})
    row = data["data"][0]
    return f"crypto F&G {row['value']} ({row.get('value_classification', '?')})"


def _probe_macro_calendar() -> str:
    data = _fetch_json("https://nfs.faireconomy.media/ff_calendar_thisweek.json")
    high_usd = [e for e in data if e.get("country") == "USD" and e.get("impact") == "High"]
    return f"{len(high_usd)} high-impact USD events this week"


# key -> (label, doc feed it implements, source, probe)
_FEEDS: tuple[tuple[str, str, str, str, Any], ...] = (
    ("price_us", "US stock OHLCV", "price & volume", "Yahoo v8 chart", _probe_price_us),
    ("price_crypto", "Crypto OHLCV", "price & volume", "OKX candles", _probe_price_crypto),
    ("macro_regime", "Macro regime (VIX/10Y/DXY)", "macro calendar & regime", "Yahoo v8 chart", _probe_macro_regime),
    ("sentiment_stock", "Stock crowd psychology", "social & news sentiment", "CNN Fear & Greed", _probe_sentiment_stock),
    ("sentiment_crypto", "Crypto crowd psychology", "social & news sentiment", "alternative.me F&G", _probe_sentiment_crypto),
    ("macro_calendar", "Macro event calendar", "macro calendar", "faireconomy (ForexFactory)", _probe_macro_calendar),
)


def _run_probe(entry: tuple[str, str, str, str, Any]) -> dict[str, Any]:
    key, label, doc_feed, source, probe = entry
    started = time.monotonic()
    row: dict[str, Any] = {
        "feed": key, "label": label, "doc_feed": doc_feed, "source": source,
        "ok": False, "latency_ms": None, "detail": None, "error": None,
    }
    try:
        row["detail"] = probe()
        row["ok"] = True
    except Exception as exc:  # noqa: BLE001 — a dead upstream is a status row
        row["error"] = f"{type(exc).__name__}: {exc}"[:200]
    row["latency_ms"] = int((time.monotonic() - started) * 1000)
    return row


def _collect_status() -> dict[str, Any]:
    with ThreadPoolExecutor(max_workers=len(_FEEDS)) as pool:
        rows = list(pool.map(_run_probe, _FEEDS))
    return {
        "feeds": rows,
        "ok_count": sum(1 for r in rows if r["ok"]),
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


def register_admin_swing_feed_routes(app: FastAPI, ctx: RouteContext) -> None:
    @app.get("/api/admin/swing-feeds/status")
    async def swing_feed_status(refresh: bool = False, authorization: str = Header(None)):
        require_admin(authorization)
        now = time.monotonic()
        with _cache_lock:
            fresh = _cache["payload"] is not None and now - _cache["at"] < _CACHE_TTL_S
            if fresh and not refresh:
                return {**_cache["payload"], "cached": True}
        payload = _collect_status()
        with _cache_lock:
            _cache["at"] = time.monotonic()
            _cache["payload"] = payload
        return {**payload, "cached": False}
