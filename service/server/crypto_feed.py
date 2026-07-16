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
OKX_PUBLIC_BASE = os.environ.get("OKX_PUBLIC_BASE", "https://www.okx.com/api/v5/public").rstrip("/")
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
    "POLUSDT",  # was MATICUSDT — OKX delisted MATIC-USDT-SWAP after the POL rebrand
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
        # Cast like fetch_spot_ticker does — consumers expect numeric prices.
        "last_price": float(last or 0),
        "mark_price": float(last or 0),  # OKX ticker doesn't include markPx; use last as proxy
        "price_24h_pct": _compute_pct(last, open24h),
        "volume_24h": item.get("volCcy24h", "0"),  # USDT-denominated volume
        "open_interest": "0",                        # OI requires separate endpoint
    }


def _okx_get(path: str, params: dict[str, str], base: str = None) -> list[dict[str, Any]]:
    """
    GET from OKX v5 API (market base by default; pass base for /public etc).
    Raises RuntimeError on non-zero code, Exception on HTTP error.
    Returns the data list on success.
    """
    from urllib.parse import urlencode
    url = f"{base or OKX_REST_BASE}/{path}?{urlencode(params)}"
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


def fetch_candles(symbol: str, bar: str = "1H", limit: int = 100) -> list[dict[str, Any]]:
    """
    Fetch OHLCV candles for a USDT-margined perpetual from OKX.

    Returns oldest-first: [{"ts": ms, "open", "high", "low", "close", "volume"}, ...]
    (OKX returns newest-first; we reverse). volume is contract volume (candle[5]).
    """
    inst_id = _to_inst_id(symbol)
    data = _okx_get("candles", {"instId": inst_id, "bar": bar, "limit": str(max(1, min(limit, 300)))})
    candles = []
    for row in reversed(data):
        if len(row) < 6:
            continue
        candles.append({
            "ts": int(row[0]),
            "open": float(row[1]),
            "high": float(row[2]),
            "low": float(row[3]),
            "close": float(row[4]),
            "volume": float(row[5]),
        })
    return candles


def fetch_funding_rate(symbol: str) -> dict[str, Any]:
    """
    Fetch the current funding rate for a USDT-margined perpetual (OKX /public).

    Returns {"symbol", "funding_rate": float, "next_funding_time": ms|None}.
    """
    inst_id = _to_inst_id(symbol)
    data = _okx_get("funding-rate", {"instId": inst_id}, base=OKX_PUBLIC_BASE)
    if not data:
        raise ValueError(f"Symbol {symbol!r} not found in OKX funding response")
    row = data[0]
    return {
        "symbol": symbol.upper(),
        "funding_rate": float(row.get("fundingRate") or 0),
        "next_funding_time": int(row["fundingTime"]) if row.get("fundingTime") else None,
    }


def fetch_open_interest(symbol: str) -> dict[str, Any]:
    """
    Fetch current open interest for a USDT-margined perpetual (OKX /public).

    Returns {"symbol", "open_interest": float (contracts), "open_interest_ccy":
    float (base currency), "ts": ms|None}.
    """
    inst_id = _to_inst_id(symbol)
    data = _okx_get("open-interest", {"instType": "SWAP", "instId": inst_id},
                    base=OKX_PUBLIC_BASE)
    if not data:
        raise ValueError(f"Symbol {symbol!r} not found in OKX open-interest response")
    row = data[0]
    return {
        "symbol": symbol.upper(),
        "open_interest": float(row.get("oi") or 0),
        "open_interest_ccy": float(row.get("oiCcy") or 0),
        "ts": int(row["ts"]) if row.get("ts") else None,
    }


def fetch_long_short_ratio(symbol: str) -> dict[str, Any]:
    """
    Fetch the latest long/short account ratio for a coin (OKX rubik stats,
    public, keyless). Ratio > 1 = more long accounts than short.

    Returns {"symbol", "long_short_ratio": float, "ts": ms|None}.
    """
    ccy = symbol[:-4].upper() if symbol.upper().endswith("USDT") else symbol.upper()
    rubik_base = OKX_PUBLIC_BASE.replace("/public", "/rubik/stat")
    data = _okx_get("contracts/long-short-account-ratio",
                    {"ccy": ccy, "period": "5m"}, base=rubik_base)
    if not data:
        raise ValueError(f"Currency {ccy!r} not found in OKX long/short response")
    # Rows are [ts, ratio] newest-first.
    ts, ratio = data[0][0], data[0][1]
    return {
        "symbol": symbol.upper(),
        "long_short_ratio": float(ratio),
        "ts": int(ts) if ts else None,
    }


def fetch_instrument_ct_val(symbol: str) -> float:
    """Contract value (ctVal, in base currency) of a USDT-margined perpetual.
    Needed to turn liquidation sizes (contracts) into notional."""
    inst_id = _to_inst_id(symbol)
    data = _okx_get("instruments", {"instType": "SWAP", "instId": inst_id},
                    base=OKX_PUBLIC_BASE)
    if not data:
        raise ValueError(f"Symbol {symbol!r} not found in OKX instruments response")
    return float(data[0].get("ctVal") or 0)


def fetch_liquidation_orders(symbol: str, limit: int = 100) -> list[dict[str, Any]]:
    """
    Recent filled liquidation orders for a USDT-margined perpetual
    (OKX /public/liquidation-orders — real forced liquidations, keyless).

    Returns newest-first rows: {"price", "contracts", "pos_side" ('long'|'short'),
    "ts" (ms)}. Raises on API/HTTP error like the other fetchers.
    """
    base_ccy = symbol[:-4].upper() if symbol.upper().endswith("USDT") else symbol.upper()
    data = _okx_get("liquidation-orders",
                    {"instType": "SWAP", "uly": f"{base_ccy}-USDT",
                     "state": "filled", "limit": str(limit)},
                    base=OKX_PUBLIC_BASE)
    details = (data[0].get("details") or []) if data else []
    rows = []
    for d in details:
        try:
            rows.append({
                "price": float(d.get("bkPx") or 0),
                "contracts": float(d.get("sz") or 0),
                "pos_side": d.get("posSide") or "",
                "ts": int(d.get("ts") or 0),
            })
        except (TypeError, ValueError):
            continue
    return rows


def fetch_spot_ticker(symbol: str) -> dict[str, Any]:
    """
    Fetch the SPOT ticker (instId like BTC-USDT, no -SWAP) for basis calculation.

    Returns {"symbol", "last_price": float}.
    """
    base = symbol[:-4] if symbol.upper().endswith("USDT") else symbol.upper()
    data = _okx_get("ticker", {"instId": f"{base}-USDT"})
    if not data:
        raise ValueError(f"Symbol {symbol!r} not found in OKX spot response")
    return {"symbol": symbol.upper(), "last_price": float(data[0].get("last") or 0)}


def fetch_order_book(symbol: str, depth: int = 25) -> dict[str, Any]:
    """
    Fetch the live order book for a USDT-margined perpetual from OKX.

    Returns {"symbol", "bids": [[price, qty], ...], "asks": [[price, qty], ...]}
    with prices/qtys as floats, best bid/ask first, up to `depth` levels each.
    """
    inst_id = _to_inst_id(symbol)
    data = _okx_get("books", {"instId": inst_id, "sz": str(max(1, min(depth, 50)))})
    if not data:
        raise ValueError(f"Symbol {symbol!r} not found in OKX order book response")
    book = data[0]

    def _levels(rows: list[list[str]]) -> list[list[float]]:
        return [[float(r[0]), float(r[1])] for r in rows if len(r) >= 2]

    return {
        "symbol": symbol.upper(),
        "bids": _levels(book.get("bids", [])),
        "asks": _levels(book.get("asks", [])),
        "ts": book.get("ts"),
    }
