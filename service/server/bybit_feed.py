"""
Bybit V5 linear perpetuals market data client.

Provides REST-based ticker fetch for the top 20 USDT-margined perpetual futures.
Mirrors the reference implementation in ~/Programming/src/TRAD/trading but in Python.

All data is normalised to snake_case. price_24h_pct is converted from Bybit's
fractional form (0.025) to percentage string ("2.50").
"""

import os
from typing import Any

import requests

# ─── constants ────────────────────────────────────────────────────────────────

BYBIT_REST_BASE = os.environ.get("BYBIT_REST_BASE", "https://api.bybit.com/v5/market").rstrip("/")
BYBIT_TIMEOUT = int(os.environ.get("BYBIT_TIMEOUT", "5"))

TOP_20_PAIRS: tuple[str, ...] = (
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "BNBUSDT",
    "XRPUSDT",
    "DOGEUSDT",
    "ADAUSDT",
    "AVAXUSDT",
    "LINKUSDT",
    "DOTUSDT",
    "LTCUSDT",
    "BCHUSDT",
    "UNIUSDT",
    "ATOMUSDT",
    "TRXUSDT",
    "NEARUSDT",
    "MATICUSDT",
    "FILUSDT",
    "APTUSDT",
    "ARBUSDT",
)

# ─── helpers ──────────────────────────────────────────────────────────────────

def _pct_to_display(raw: str) -> str:
    """Convert Bybit fractional pct ('0.025') → percentage string ('2.50')."""
    try:
        return f"{float(raw) * 100:.2f}"
    except (ValueError, TypeError):
        return "0.00"


def _normalise(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "symbol": item.get("symbol", ""),
        "last_price": item.get("lastPrice", "0"),
        "mark_price": item.get("markPrice", "0"),
        "price_24h_pct": _pct_to_display(item.get("price24hPcnt", "0")),
        "volume_24h": item.get("turnover24h", "0"),
        "open_interest": item.get("openInterest", "0"),
    }


def _bybit_get(path: str, params: dict[str, str]) -> dict[str, Any]:
    """
    GET from Bybit V5 with category=linear enforced.
    Raises RuntimeError on non-zero retCode, Exception on HTTP error.
    """
    url = f"{BYBIT_REST_BASE}/{path}"
    query = {"category": "linear", **params}
    # build URL string for testability (tests assert on the URL)
    from urllib.parse import urlencode
    full_url = f"{url}?{urlencode(query)}"
    resp = requests.get(full_url, timeout=BYBIT_TIMEOUT)
    resp.raise_for_status()
    body = resp.json()
    if body.get("retCode", 0) != 0:
        raise RuntimeError(f"Bybit error {body['retCode']}: {body.get('retMsg', '')}")
    return body["result"]


# ─── public API ───────────────────────────────────────────────────────────────

def fetch_bybit_ticker(symbol: str) -> dict[str, Any]:
    """
    Fetch a single USDT-linear perpetual ticker from Bybit V5.

    Returns a normalised dict with keys:
        symbol, last_price, mark_price, price_24h_pct, volume_24h, open_interest

    Raises ValueError if the symbol is not found in the response.
    Raises RuntimeError on Bybit API error.
    Raises requests.HTTPError on HTTP failure.
    """
    result = _bybit_get("tickers", {"symbol": symbol})
    items: list[dict] = result.get("list", [])
    if not items:
        raise ValueError(f"Symbol {symbol!r} not found in Bybit response")
    return _normalise(items[0])


def fetch_bybit_tickers(symbols: list[str]) -> list[dict[str, Any]]:
    """
    Fetch tickers for a list of symbols in a single Bybit request.

    Bybit V5 does not support bulk ticker fetch by symbol list — we omit
    the symbol param to get all linear tickers, then filter client-side.
    Symbols missing from the response are silently skipped.

    Returns an empty list immediately when symbols is empty.
    """
    if not symbols:
        return []

    symbol_set = set(symbols)
    result = _bybit_get("tickers", {})
    items: list[dict] = result.get("list", [])
    return [_normalise(item) for item in items if item.get("symbol") in symbol_set]
