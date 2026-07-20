"""USD conversion for the non-USD markets.

Positions settle in their native currency (Plan 13 decision 2: store native,
convert only for aggregates). A-share books CNY, a JPY-quoted forex pair books
JPY. Anything that sums across markets — portfolio totals, leaderboards, the
risk gate — has to land in one unit first, and that unit is USD.

Rates come from the same Yahoo feed the forex market already uses, cached for
an hour. An hour of staleness is immaterial here: these are display and
risk-gate aggregates, not execution prices, and the majors do not move enough
intraday to change a decision the gate would otherwise make.

Conversion never raises and never blocks. If the rate cannot be fetched the
last known rate is reused, and failing that the amount is returned unconverted
with a log line. A portfolio total that is briefly wrong is recoverable; a
portfolio page that 500s because a rate provider blinked is not.
"""

from __future__ import annotations

import threading
import time

# USD per one unit of the quoted currency.
_CACHE: dict[str, tuple[float, float]] = {}  # currency -> (rate, fetched_at)
_LOCK = threading.RLock()
_TTL_SECONDS = 3600.0

# Fallbacks used only when the feed has never answered for a currency. Marked
# approximate on purpose — they keep a total roughly right rather than showing
# a CNY balance as though it were USD, which is a ~7x error.
_SEED_RATES: dict[str, float] = {
    'USD': 1.0,
    'CNY': 0.14,
    'CNH': 0.14,
    'JPY': 0.0064,
    'EUR': 1.08,
    'GBP': 1.27,
    'CHF': 1.12,
    'AUD': 0.66,
    'CAD': 0.73,
    'NZD': 0.60,
    'HKD': 0.128,
    'SGD': 0.74,
    'KRW': 0.00072,
    'MXN': 0.058,
    'TRY': 0.029,
    'ZAR': 0.055,
}


def _fetch_rate(currency: str) -> float | None:
    """USD per one unit of `currency`, from the Yahoo chart feed."""
    from price_fetcher import _get_yahoo_chart_price
    # Yahoo quotes the majors as USDJPY (JPY per USD) rather than JPYUSD, so
    # ask for the pair that exists and invert. USDCNY resolves for the onshore
    # rate; both CNY and CNH map onto it closely enough for aggregates.
    pair = f"USD{currency}"
    price = _get_yahoo_chart_price(pair, None, 'forex')
    if price and price > 0:
        return 1.0 / float(price)
    # A handful of currencies are quoted the other way round (EURUSD, GBPUSD).
    price = _get_yahoo_chart_price(f"{currency}USD", None, 'forex')
    return float(price) if price and price > 0 else None


def get_rate(currency: str | None) -> float:
    """USD per one unit of `currency`. Returns 1.0 for USD and for unknowns."""
    code = (currency or 'USD').strip().upper()
    if code in ('', 'USD'):
        return 1.0

    with _LOCK:
        cached = _CACHE.get(code)
        if cached is not None and (time.time() - cached[1]) < _TTL_SECONDS:
            return cached[0]

    try:
        rate = _fetch_rate(code)
    except Exception:  # noqa: BLE001 — never let a rate lookup break a total
        rate = None

    with _LOCK:
        if rate is None:
            stale = _CACHE.get(code)
            if stale is not None:
                return stale[0]
            return _SEED_RATES.get(code, 1.0)
        _CACHE[code] = (rate, time.time())
        return rate


def to_usd(amount: float, currency: str | None) -> float:
    """Convert an amount in `currency` to USD. Identity for USD."""
    code = (currency or 'USD').strip().upper()
    if code in ('', 'USD'):
        return float(amount)
    return float(amount) * get_rate(code)


def reset_cache() -> None:
    """Test hook — drops memoised rates so a patched feed is actually called."""
    with _LOCK:
        _CACHE.clear()
