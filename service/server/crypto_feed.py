"""
OKX perpetuals market data client.

Provides REST-based ticker fetch for the top 20 USDT-margined perpetual futures.
Uses OKX v5 API (accessible from AWS EC2; Bybit/Binance block cloud provider IPs).

All data is normalised to snake_case. Symbols use Sooppiy's format (BTCUSDT),
internally mapped to OKX's instId format (BTC-USDT-SWAP).
"""

import os
from typing import Any

import requests

# ─── constants ────────────────────────────────────────────────────────────────

OKX_REST_BASE = os.environ.get("OKX_REST_BASE", "https://www.okx.com/api/v5/market").rstrip("/")
OKX_TIMEOUT = int(os.environ.get("OKX_TIMEOUT", "5"))

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

def _to_inst_id(symbol: str) -> str:
    """Convert BTCUSDT → BTC-USDT-SWAP for OKX instId."""
    base = symbol.rstrip("USDT").rstrip("-")
    # strip trailing USDT characters correctly
    if symbol.endswith("USDT"):
        base = symbol[:-4]
    return f"{base}-USDT-SWAP"


def _to_symbol(inst_id: str) -> str:
    """Convert BTC-USDT-SWAP → BTCUSDT."""
    return inst_id.replace("-USDT-SWAP", "") + "USDT"


def _compute_pct(last: str, open24h: str) -> str:
    """Compute 24h % change as a display string like '3.91' or '-2.81'."""
    try:
        l, o = float(last), float(open24h)
        if o == 0:
            return "0.00"
        return f"{(l - o) / o * 100:.2f}"
    except (ValueError, TypeError, ZeroDivisionError):
        return "0.00"


def _normalise(item: dict[str, Any]) -> dict[str, Any]:
    last = item.get("last", "0")
    open24h = item.get("open24h", last)  # fallback to last if missing
    return {
        "symbol": _to_symbol(item.get("instId", "")),
        "last_price": last,
        "mark_price": last,  # OKX ticker doesn't include markPx; use last as proxy
        "price_24h_pct": _compute_pct(last, open24h),
        "volume_24h": item.get("volCcy24h", "0"),  # USDT-denominated volume
        "open_interest": "0",                        # OI requires separate endpoint
    }


def _okx_get(path: str, params: dict[str, str]) -> list[dict[str, Any]]:
    """
    GET from OKX v5 market API.
    Raises RuntimeError on non-zero code, Exception on HTTP error.
    Returns the data list on success.
    """
    from urllib.parse import urlencode
    url = f"{OKX_REST_BASE}/{path}?{urlencode(params)}"
    resp = requests.get(url, timeout=OKX_TIMEOUT)
    resp.raise_for_status()
    body = resp.json()
    if body.get("code", "0") != "0":
        raise RuntimeError(f"OKX error {body['code']}: {body.get('msg', '')}")
    return body.get("data", [])


# ─── public API ───────────────────────────────────────────────────────────────

def fetch_ticker(symbol: str) -> dict[str, Any]:
    """
    Fetch a single USDT-margined perpetual ticker from OKX.

    Accepts Sooppiy symbol format (BTCUSDT) and returns a normalised dict:
        symbol, last_price, mark_price, price_24h_pct, volume_24h, open_interest

    Raises ValueError if the symbol is not found.
    Raises RuntimeError on OKX API error.
    Raises requests.HTTPError on HTTP failure.
    """
    inst_id = _to_inst_id(symbol)
    data = _okx_get("ticker", {"instId": inst_id})
    if not data:
        raise ValueError(f"Symbol {symbol!r} not found in OKX response")
    return _normalise(data[0])


def fetch_tickers(symbols: list[str]) -> list[dict[str, Any]]:
    """
    Fetch tickers for a list of symbols using OKX's bulk SWAP tickers endpoint.

    OKX supports instType=SWAP to get all swaps in one call; we filter client-side.
    Symbols missing from the response are silently skipped.
    Returns an empty list immediately when symbols is empty.
    """
    if not symbols:
        return []

    wanted = {_to_inst_id(s) for s in symbols}
    data = _okx_get("tickers", {"instType": "SWAP"})
    return [_normalise(item) for item in data if item.get("instId") in wanted]
