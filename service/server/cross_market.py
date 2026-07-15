"""
cross_market.py — Cross-market spread signals (signal-collection plan, card 16).

Two spreads that put crypto price action in a wider context:

  * Kimchi premium — Upbit KRW-BTC vs global (OKX BTC-USDT) converted
    through USD/KRW. Extreme positive premium has historically flagged
    local (Korean retail) overheating; a discount flags demand
    contraction. Sources: Upbit public ticker + OKX spot ticker (both
    keyless) + open.er-api.com USD/KRW (keyless, daily).
  * Dollar index — FRED DTWEXBGS (nominal broad USD index, daily) when
    FRED_API_KEY is set; BTC has run a strong negative 30d correlation to
    dollar strength (≈ -0.7 in 2026 snapshots). Without the key the field
    is null and the payload says why.

All sources fail soft and independently: any one failing nulls its own
field only. Gated by CROSS_MARKET_ENABLED (default off until verified),
matching the other signal phases. Payload is cached by the route layer.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

import requests

logger = logging.getLogger("cross_market")

_TIMEOUT = 10.0

UPBIT_TICKER_URL = os.getenv("UPBIT_TICKER_URL", "https://api.upbit.com/v1/ticker")
USDKRW_RATE_URL = os.getenv("USDKRW_RATE_URL", "https://open.er-api.com/v6/latest/USD")
FRED_DXY_SERIES = os.getenv("FRED_DXY_SERIES", "DTWEXBGS")

# Rolling interpretation thresholds (pct). Kimchi premium regularly sits in
# the low single digits; ±3% is where the signal historically gets loud.
KIMCHI_HOT_PCT = float(os.getenv("KIMCHI_HOT_PCT", "3.0") or 3.0)
KIMCHI_DISCOUNT_PCT = float(os.getenv("KIMCHI_DISCOUNT_PCT", "-0.5") or -0.5)


def cross_market_enabled() -> bool:
    return (os.getenv("CROSS_MARKET_ENABLED", "false").strip().lower()
            in ("1", "true", "yes", "on"))


# ── source fetchers (each fails soft to None) ─────────────────────────────

def fetch_upbit_krw_btc() -> Optional[float]:
    """Last trade price of BTC in KRW on Upbit."""
    try:
        r = requests.get(UPBIT_TICKER_URL, params={"markets": "KRW-BTC"}, timeout=_TIMEOUT)
        r.raise_for_status()
        rows = r.json() or []
        price = float(rows[0]["trade_price"])
        return price if price > 0 else None
    except Exception as exc:  # noqa: BLE001
        logger.warning("upbit KRW-BTC fetch failed: %s", exc)
        return None


def fetch_usdkrw() -> Optional[float]:
    """USD->KRW rate (keyless, daily granularity — fine for a premium spread)."""
    try:
        r = requests.get(USDKRW_RATE_URL, timeout=_TIMEOUT)
        r.raise_for_status()
        rate = float(((r.json() or {}).get("rates") or {}).get("KRW") or 0)
        return rate if rate > 0 else None
    except Exception as exc:  # noqa: BLE001
        logger.warning("USD/KRW rate fetch failed: %s", exc)
        return None


def fetch_global_btc_usd() -> Optional[float]:
    """Global BTC spot in USD (OKX BTC-USDT spot; USDT≈USD for spread purposes)."""
    try:
        from crypto_feed import fetch_spot_ticker
        ticker = fetch_spot_ticker("BTCUSDT")
        price = float(ticker.get("last_price") or 0)
        return price if price > 0 else None
    except Exception as exc:  # noqa: BLE001
        logger.warning("OKX BTC spot fetch failed: %s", exc)
        return None


def fetch_dollar_index() -> Optional[dict[str, Any]]:
    """Latest two observations of the FRED broad dollar index -> level + 1d change."""
    key = os.getenv("FRED_API_KEY", "").strip()
    if not key:
        return None
    try:
        r = requests.get(
            "https://api.stlouisfed.org/fred/series/observations",
            params={"series_id": FRED_DXY_SERIES, "api_key": key, "file_type": "json",
                    "sort_order": "desc", "limit": 10},
            timeout=_TIMEOUT,
        )
        r.raise_for_status()
        obs = [o for o in (r.json() or {}).get("observations", [])
               if o.get("value") not in (None, "", ".")]
        if not obs:
            return None
        latest = float(obs[0]["value"])
        prev = float(obs[1]["value"]) if len(obs) > 1 else None
        return {
            "series": FRED_DXY_SERIES,
            "value": latest,
            "change_1d_pct": (round((latest - prev) / prev * 100, 3)
                              if prev else None),
            "date": obs[0].get("date"),
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("FRED %s fetch failed: %s", FRED_DXY_SERIES, exc)
        return None


# ── assembly ──────────────────────────────────────────────────────────────

def _kimchi_verdict(premium_pct: float) -> str:
    if premium_pct >= KIMCHI_HOT_PCT:
        return "overheated"       # local retail froth — contrarian caution
    if premium_pct <= KIMCHI_DISCOUNT_PCT:
        return "discount"         # Korean demand contraction
    return "neutral"


def build_cross_market_payload() -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    if not cross_market_enabled():
        return {
            "available": False,
            "reason": "CROSS_MARKET_ENABLED is off",
            "as_of": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    upbit_krw = fetch_upbit_krw_btc()
    usdkrw = fetch_usdkrw()
    global_usd = fetch_global_btc_usd()
    dxy = fetch_dollar_index()

    kimchi: Optional[dict[str, Any]] = None
    if upbit_krw and usdkrw and global_usd:
        upbit_usd = upbit_krw / usdkrw
        premium_pct = round((upbit_usd - global_usd) / global_usd * 100, 3)
        kimchi = {
            "premium_pct": premium_pct,
            "verdict": _kimchi_verdict(premium_pct),
            "upbit_krw": upbit_krw,
            "upbit_usd_equiv": round(upbit_usd, 2),
            "global_usd": global_usd,
            "usdkrw": usdkrw,
            "thresholds": {"hot_pct": KIMCHI_HOT_PCT, "discount_pct": KIMCHI_DISCOUNT_PCT},
        }

    return {
        "available": True,
        "kimchi": kimchi,
        "dollar_index": dxy,
        "dollar_index_note": (None if dxy else
                              "FRED_API_KEY not set (or FRED unavailable) — "
                              "dollar index skipped"),
        "note": ("Kimchi premium = Upbit KRW-BTC vs OKX BTC-USDT through USD/KRW. "
                 "Extreme premium = local overheating (contrarian caution); "
                 "discount = Korean demand contraction. Dollar strength has run "
                 "negatively correlated with BTC. FX rate is daily granularity."),
        "as_of": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
