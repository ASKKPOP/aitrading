# Fee Configuration

# Transaction fee rate (per trade)
# Example: 0.001 = 0.1%
#
# LEGACY DEFAULT, kept as the fallback for any market not in the table below
# and as the value every existing call site imports. Do not remove it — a
# market with no entry must charge SOMETHING, and charging too much only
# refuses trades, which is the safe direction.
TRADE_FEE_RATE = 0.001

# ── per-market rates (2026-07-28) ──────────────────────────────────────────
# One flat 0.1%/side was charged to every market. It is roughly right for a
# crypto taker and badly wrong everywhere else, and it did two kinds of damage
# at once:
#
#   1. P&L. Over the week to 2026-07-28 the desk paid $363.31 in fees across
#      140 legs while 58 closed round trips netted +$14.88. The trading was
#      approximately break-even; the fees were the loss.
#   2. Selection. run_engine._fee_edge_skip requires a claimed move of 3x the
#      round trip — >= 2.40% at 0.1%/side. Across all 2,141 theses ever
#      generated, 711 (33%) could never clear that bar, and forex was 308 of
#      308: no FX run has ever opened a position on this platform.
#
# Rates are the realistic cost of one leg on the venue each market actually
# trades on, chosen at the retail (expensive) end of each range: overcharging
# only refuses trades, while undercharging invents edge that is not there.
_MARKET_FEE_RATES: dict[str, float] = {
    # Binance/OKX perp taker 0.04–0.05%; the fleet trades perps.
    "crypto": 0.00045,
    # CME/CBOT round turn ~$2.50 on ~$70k notional for ZC/CL-sized contracts
    # (~0.0035% per leg). Rounded up.
    "futures": 0.00005,
    # Retail FX on a major: ~0.5–1 pip, ~0.005–0.010% one way.
    "forex": 0.00008,
    # US equities: ~$0.005/share plus SEC/TAF on the sell — well under 0.01%.
    "us-stock": 0.00005,
    # SSE/SZSE commission plus the 0.05% stamp duty charged on sells.
    "a-stock": 0.00025,
    # Polymarket takes no per-trade fee; gas is not modelled here.
    "polymarket": 0.0,
}


# fee_rate() is on the hot path — every fill and every gate evaluation calls
# it — and platform_settings.get_setting opens its own DB connection. Without
# a cache that is a round trip per fee lookup for a value that changes maybe
# once a quarter. 30s TTL matches the llm_client settings cache, so a console
# edit still lands within half a minute and no restart is needed.
_OVERRIDE_TTL_SECONDS = 30.0
_override_cache: "dict[str, tuple[float, float | None]]" = {}


def reset_override_cache() -> None:
    """Drop cached overrides — for tests, and for an operator who has just
    changed a rate and does not want to wait out the TTL."""
    _override_cache.clear()


def _override(market: str) -> "float | None":
    """Operator override from platform_settings (`fee_rate_<market>`).

    A fee is an external fact about a venue, not something the desk can infer,
    so it must be settable without a deploy when a venue changes its schedule.
    Never raises — a bad row falls through to the table."""
    import time
    now = time.monotonic()
    hit = _override_cache.get(market)
    if hit is not None and (now - hit[0]) < _OVERRIDE_TTL_SECONDS:
        return hit[1]
    try:
        import platform_settings
        raw = platform_settings.get_setting(f"fee_rate_{market}")
    except Exception:  # noqa: BLE001 — settings must never break a fill
        _override_cache[market] = (now, None)
        return None
    val: "float | None" = None
    if raw not in (None, ""):
        try:
            parsed = float(raw)
        except (TypeError, ValueError):
            parsed = None
        # A negative fee would pay the desk to trade; anything above 10% is a
        # typo, not a venue. Refuse both rather than price a fill on them.
        if parsed is not None and 0.0 <= parsed <= 0.10:
            val = parsed
    _override_cache[market] = (now, val)
    return val


def per_market_enabled() -> bool:
    """Default OFF — this ships dark, like every other money-path change here.

    Turning it on changes what every fill costs and what the fee_edge gate
    will admit, on a book that is already live. It gets its own switch and its
    own deliberate flip, not a silent default. With it off, fee_rate() returns
    the legacy flat rate for every market and behaviour is byte-identical to
    before this module grew a table."""
    import os
    return os.getenv("FEE_PER_MARKET", "false").strip().lower() in (
        "1", "true", "yes", "on")


def fee_rate(market: "str | None") -> float:
    """Per-leg fee rate for `market`.

    Order: operator override -> per-market table -> TRADE_FEE_RATE. An unknown
    market charges the legacy rate, which is the expensive direction and
    therefore the safe one. An explicit override is honoured even while the
    table is off, so a single venue can be corrected without flipping
    everything at once.
    """
    key = (market or "").strip().lower()
    if not key:
        return TRADE_FEE_RATE
    ov = _override(key)
    if ov is not None:
        return ov
    if not per_market_enabled():
        return TRADE_FEE_RATE
    return _MARKET_FEE_RATES.get(key, TRADE_FEE_RATE)


def round_trip_rate(market: "str | None") -> float:
    """Both legs — what an entry has to out-earn before it is worth taking."""
    return fee_rate(market) * 2
