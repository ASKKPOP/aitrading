"""Top-5 symbol universe (Plan 11 F1).

For fully-delegated (mode='agent') and simple-mode automation the AI must pick
from the market's current top symbols only — the highest-volume, most-watched
USDT perps — instead of an open universe. Ranking:

  primary    OKX 24h USDT volume across all USDT-margined perps
  popularity when the scanner has StockTwits mention data (SCANNER_ENABLED),
             a mention-rate boost of up to +25% is applied to the volume score

The result is intersected with the priceable universe (Hyperliquid listing —
the simulator prices crypto through it) and cached for TOP_SYMBOLS_CACHE_SECONDS.
All fetches fail soft: on any error callers fall back to their own defaults.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Any

TOP_SYMBOLS_LIMIT = 5
_CACHE_SECONDS = int(os.environ.get("TOP_SYMBOLS_CACHE_SECONDS", "300"))
_VOLUME_CANDIDATES = 20  # rank this many by volume before popularity/priceable filters

_cache_lock = threading.Lock()
_cache: dict[str, Any] = {"at": 0.0, "items": []}


def _mention_rates() -> dict[str, float]:
    """symbol → StockTwits mentions/hour from the scanner's cached payload.
    Empty when the scanner is off or has no snapshot yet."""
    try:
        from scanner import get_scanner_payload, scanner_enabled
        if not scanner_enabled():
            return {}
        payload = get_scanner_payload() or {}
        rates: dict[str, float] = {}
        for m in payload.get("mentions") or []:
            sym = str(m.get("symbol") or "").upper()
            rate = m.get("rate_per_hour")
            if sym and rate:
                rates[f"{sym}USDT"] = float(rate)
        return rates
    except Exception:  # noqa: BLE001
        return {}


def _priceable_bases() -> set[str] | None:
    """Base coins the simulator can actually price (Hyperliquid listing).
    None = unknown (fail-soft: skip the filter)."""
    try:
        from price_fetcher import _get_hyperliquid_available_symbols
        listed = _get_hyperliquid_available_symbols()
        return set(listed) if listed else None
    except Exception:  # noqa: BLE001
        return None


def _compute(limit: int) -> list[dict[str, Any]]:
    from crypto_feed import _okx_get, _to_symbol

    data = _okx_get("tickers", {"instType": "SWAP"})
    rows = []
    for item in data:
        inst_id = item.get("instId") or ""
        if not inst_id.endswith("-USDT-SWAP"):
            continue
        try:
            # volCcy24h is denominated in the BASE coin, not USDT — multiply by
            # price or meme coins with trillion-token supplies top the ranking.
            vol_base = float(item.get("volCcy24h") or 0)
            last = float(item.get("last") or 0)
        except (TypeError, ValueError):
            continue
        if vol_base <= 0 or last <= 0:
            continue
        rows.append({
            "symbol": _to_symbol(inst_id),
            "last_price": last,
            "volume_24h_usd": round(vol_base * last, 2),
        })
    rows.sort(key=lambda r: r["volume_24h_usd"], reverse=True)
    rows = rows[:_VOLUME_CANDIDATES]

    bases = _priceable_bases()
    if bases is not None:
        rows = [r for r in rows if r["symbol"].removesuffix("USDT") in bases] or rows

    mentions = _mention_rates()
    if mentions:
        top_rate = max(mentions.values())
        for r in rows:
            rate = mentions.get(r["symbol"], 0.0)
            boost = 1.0 + 0.25 * min(1.0, rate / top_rate) if top_rate > 0 else 1.0
            r["score"] = r["volume_24h_usd"] * boost
            if rate:
                r["mention_rate_per_hour"] = rate
        rows.sort(key=lambda r: r["score"], reverse=True)
    return rows[:limit]


def get_top_symbols(limit: int = TOP_SYMBOLS_LIMIT) -> list[dict[str, Any]]:
    """Top symbols ranked by 24h volume (+ mention popularity). Cached.
    Raises on total data-source failure — callers are expected to fail soft."""
    now = time.time()
    with _cache_lock:
        if _cache["items"] and now - _cache["at"] < _CACHE_SECONDS:
            return list(_cache["items"])[:limit]
    items = _compute(max(limit, TOP_SYMBOLS_LIMIT))
    with _cache_lock:
        _cache["at"] = now
        _cache["items"] = items
    return items[:limit]
