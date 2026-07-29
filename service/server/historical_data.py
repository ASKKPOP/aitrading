"""Historical OHLCV bar loader with Parquet cache.

Public API:
    get_bars(symbol, resolution, start_date, end_date, *, provider, cache_dir, force_refresh)
        -> list[Bar]

Providers:
    "yfinance" (default) — wraps yfinance.download; free, no key required.
    "alphavantage"       — uses TIME_SERIES_DAILY via price_fetcher's AV key.

Cache:
    Bars are persisted to {cache_dir}/{SYMBOL}_{resolution}.parquet after every
    successful fetch. On subsequent calls the cache is read instead of hitting the
    network, unless force_refresh=True or the cached range doesn't cover the request.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pyarrow as pa
import pyarrow.parquet as pq
import yfinance as yf

_DEFAULT_CACHE_DIR = Path(__file__).parent / "data" / "historical"

# Alpha Vantage key — reuse the same env var as price_fetcher.py
_AV_API_KEY = os.environ.get("ALPHA_VANTAGE_API_KEY", "demo")
_AV_BASE_URL = "https://www.alphavantage.co/query"


@dataclass
class Bar:
    date: str      # YYYY-MM-DD
    open: float
    high: float
    low: float
    close: float
    volume: int


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

def _cache_path(symbol: str, resolution: str, cache_dir: Path) -> Path:
    return cache_dir / f"{symbol}_{resolution}.parquet"


def _bars_to_table(bars: list[Bar]) -> pa.Table:
    return pa.table(
        {
            "date": [b.date for b in bars],
            "open": [b.open for b in bars],
            "high": [b.high for b in bars],
            "low": [b.low for b in bars],
            "close": [b.close for b in bars],
            "volume": [b.volume for b in bars],
        }
    )


def _table_to_bars(table: pa.Table) -> list[Bar]:
    dates = table.column("date").to_pylist()
    opens = table.column("open").to_pylist()
    highs = table.column("high").to_pylist()
    lows = table.column("low").to_pylist()
    closes = table.column("close").to_pylist()
    volumes = table.column("volume").to_pylist()
    return [
        Bar(date=d, open=o, high=h, low=l, close=c, volume=v)
        for d, o, h, l, c, v in zip(dates, opens, highs, lows, closes, volumes)
    ]


def _write_cache(bars: list[Bar], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(_bars_to_table(bars), path)


def _read_cache(path: Path) -> list[Bar]:
    table = pq.read_table(path)
    return _table_to_bars(table)


def _bar_is_finite(bar: Bar) -> bool:
    """A bar with a NaN/Inf price is not a bar. Dropping it is the only honest
    option: any window that includes it (MA, σ, return) evaluates to NaN, and
    NaN passes every `is not None` guard downstream."""
    return all(math.isfinite(v) for v in (bar.open, bar.high, bar.low, bar.close))


def _cache_covers(cached: list[Bar], start_date: str, end_date: str) -> bool:
    if not cached:
        return False
    earliest = cached[0].date
    latest = cached[-1].date
    return earliest <= start_date and latest >= end_date


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------

def _fetch_yfinance(symbol: str, start_date: str, end_date: str) -> list[Bar]:
    import pandas as pd

    try:
        df = yf.download(symbol, start=start_date, end=end_date, interval="1d", progress=False, auto_adjust=True)
    except Exception:
        return []

    if df is None or df.empty:
        return []

    # yfinance may return MultiIndex columns like ('Close', 'AAPL') for single tickers
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    required = {"Open", "High", "Low", "Close", "Volume"}
    if not required.issubset(set(df.columns)):
        return []

    bars = []
    for idx, row in df.iterrows():
        try:
            date_str = idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)[:10]
            bar = Bar(
                date=date_str,
                open=float(row["Open"]),
                high=float(row["High"]),
                low=float(row["Low"]),
                close=float(row["Close"]),
                volume=int(row["Volume"]),
            )
        except (TypeError, ValueError):
            continue
        # float(NaN) succeeds, so an incomplete row (yfinance emits one for the
        # in-progress session) would otherwise arrive as a bar with a NaN close
        # and poison every window that touches it: MA50/MA200, σ, returns.
        if not _bar_is_finite(bar):
            continue
        bars.append(bar)

    bars.sort(key=lambda b: b.date)
    return bars


def _fetch_alphavantage(symbol: str, start_date: str, end_date: str) -> list[Bar]:
    import requests

    params = {
        "function": "TIME_SERIES_DAILY",
        "symbol": symbol,
        "outputsize": "full",
        "apikey": _AV_API_KEY,
    }
    try:
        resp = requests.get(_AV_BASE_URL, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return []

    series = data.get("Time Series (Daily)")
    if not isinstance(series, dict):
        return []

    bars = []
    for date_str, values in series.items():
        if date_str < start_date or date_str > end_date:
            continue
        try:
            bars.append(Bar(
                date=date_str,
                open=float(values["1. open"]),
                high=float(values["2. high"]),
                low=float(values["3. low"]),
                close=float(values["4. close"]),
                volume=int(float(values["5. volume"])),
            ))
        except (KeyError, TypeError, ValueError):
            continue

    bars.sort(key=lambda b: b.date)
    return bars


_PROVIDERS = {
    "yfinance": _fetch_yfinance,
    "alphavantage": _fetch_alphavantage,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_bars(
    symbol: str,
    resolution: str,
    start_date: str,
    end_date: str,
    *,
    provider: str = "yfinance",
    cache_dir: Optional[Path | str] = None,
    force_refresh: bool = False,
) -> list[Bar]:
    """Return historical OHLCV bars for *symbol* between *start_date* and *end_date*.

    Args:
        symbol:        Ticker symbol (case-insensitive).
        resolution:    Bar resolution — "1d" (daily) is currently supported.
        start_date:    Inclusive start date, "YYYY-MM-DD".
        end_date:      Inclusive end date, "YYYY-MM-DD".
        provider:      Data source: "yfinance" (default) or "alphavantage".
        cache_dir:     Directory for Parquet cache files. Defaults to
                       service/server/data/historical/.
        force_refresh: Ignore cache and fetch fresh data from the provider.

    Returns:
        List of Bar objects sorted by date ascending.
        Returns an empty list on any provider error.
    """
    symbol = symbol.upper().strip()
    cache_dir = Path(cache_dir) if cache_dir else _DEFAULT_CACHE_DIR
    cache_file = _cache_path(symbol, resolution, cache_dir)

    fetch_fn = _PROVIDERS.get(provider, _fetch_yfinance)

    # Try cache first — only when the cached range actually covers the request
    cached: list[Bar] = []
    if not force_refresh and cache_file.exists():
        try:
            cached = _read_cache(cache_file)
            if _cache_covers(cached, start_date, end_date):
                return [b for b in cached
                        if start_date <= b.date <= end_date and _bar_is_finite(b)]
        except Exception:
            cached = []  # corrupt cache — fall through to fetch

    # Fetch from provider, extending to the union of cached + requested range so
    # the cache monotonically grows instead of being replaced by a narrower window.
    fetch_start = min(start_date, cached[0].date) if cached else start_date
    fetch_end = max(end_date, cached[-1].date) if cached else end_date
    bars = fetch_fn(symbol, fetch_start, fetch_end)

    if bars:
        if cached:
            merged = {b.date: b for b in cached}
            merged.update({b.date: b for b in bars})  # fresh data wins on overlap
            bars = sorted(merged.values(), key=lambda b: b.date)
        try:
            _write_cache(bars, cache_file)
        except Exception:
            pass  # cache write failure is non-fatal
    elif cached:
        bars = cached  # provider outage — stale cache beats nothing

    # _bar_is_finite again here: caches written before this guard existed, and
    # any non-yfinance provider, can still hold a NaN-priced row.
    return [b for b in bars if start_date <= b.date <= end_date and _bar_is_finite(b)]
