"""
Single source of truth for the markets Sooppiy supports.

Before this module there were five independent allowlists (routes_shared.SUPPORTED_MARKETS,
automation.VALID_MARKETS, trading_runs.VALID_RUN_MARKETS, tasks._SUPPORTED_PRICE_MARKETS and
the frontend MARKETS array) which had drifted apart. Each of those is now a derived view over
REGISTRY so a new market is declared once, here.

See docs/plan/13-market-expansion.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class MarketSpec:
    value: str
    # Quote currency for PnL. Forex overrides this per-symbol (see position_currency).
    currency: str
    # Notional per point of price movement. 1.0 for cash instruments, 50.0 for ES, 100.0
    # for equity options. PnL is (exit - entry) * quantity * contract_multiplier.
    contract_multiplier: float
    # Session calendar key consumed by is_session_open().
    session: str
    # Dispatch key for price_fetcher.get_price_from_market().
    price_provider: str
    supports_short: bool
    # Whether the market can carry positions and manual signals.
    tradeable: bool
    # Whether automation rules and AI trading runs may target this market. Narrower than
    # `tradeable`: Polymarket is manually tradeable but was never automatable.
    automatable: bool
    # Decimal places for price display. Forex quotes to 5.
    price_decimals: int
    # Whether the API may fetch a price synchronously on the trade path. False for
    # rate-limited providers (Alpha Vantage), which are left to the background refresher.
    server_priced: bool


REGISTRY: dict[str, MarketSpec] = {
    'us-stock': MarketSpec(
        value='us-stock',
        currency='USD',
        contract_multiplier=1.0,
        session='nyse',
        # Yahoo, not Alpha Vantage. AV's free tier cannot serve this at all:
        # the intraday call carries entitlement=realtime, which is premium-only,
        # and the 25-requests/day cap is a second wall the news/macro loops
        # already spend. Measured from the production host 2026-07-20 — AV
        # returned "This is a premium endpoint" while Yahoo served AAPL, MSFT
        # and SPY unthrottled. AV is still used for news/macro intel.
        price_provider='yahoo',
        supports_short=True,
        tradeable=True,
        automatable=True,
        price_decimals=2,
        # Stays False even though the Alpha Vantage cap that motivated it is gone.
        # Flipping it makes the API demand a server price on the trade path and
        # REJECT the trade when the fetch fails — and Yahoo carries 1m bars for
        # only ~7 days, so submitting a historical us-stock signal (what the
        # backtest flow does) would start failing. Unlike forex, us-stock has an
        # established agent-provided-price workflow that depends on this.
        server_priced=False,
    ),
    'crypto': MarketSpec(
        value='crypto',
        currency='USD',
        contract_multiplier=1.0,
        session='24x7',
        price_provider='hyperliquid',
        supports_short=True,
        tradeable=True,
        automatable=True,
        price_decimals=2,
        server_priced=True,
    ),
    'polymarket': MarketSpec(
        value='polymarket',
        currency='USD',
        contract_multiplier=1.0,
        session='24x7',
        price_provider='polymarket',
        # Prediction-market shares cannot be sold naked; see services._update_position_from_signal.
        supports_short=False,
        tradeable=True,
        automatable=False,
        price_decimals=2,
        server_priced=True,
    ),
    'forex': MarketSpec(
        value='forex',
        # Overridden per pair by position_currency() — EURJPY settles in JPY.
        currency='USD',
        contract_multiplier=1.0,
        session='24x5',
        price_provider='yahoo',
        supports_short=True,
        tradeable=True,
        automatable=True,
        price_decimals=5,
        server_priced=True,
    ),
}

MARKET_ALIASES: dict[str, str] = {
    'binance': 'crypto',
    'binance-spot': 'crypto',
    'binance_spot': 'crypto',
    'coinbase': 'crypto',
    'coinbase-spot': 'crypto',
    'coinbase_spot': 'crypto',
    'hyperliquid': 'crypto',
    'hl': 'crypto',
    'kraken': 'crypto',
    'okx': 'crypto',
    'stock': 'us-stock',
    'stocks': 'us-stock',
    'us': 'us-stock',
    'us stock': 'us-stock',
    'us stocks': 'us-stock',
    'us_stock': 'us-stock',
    'us_stocks': 'us-stock',
    'usstock': 'us-stock',
    'nasdaq': 'us-stock',
    'sp500': 'us-stock',
    'etf': 'us-stock',
    'equity': 'us-stock',
    'equities': 'us-stock',
    'fx': 'forex',
    'currency': 'forex',
    'currencies': 'forex',
}


def normalize_market(market: str | None) -> str:
    normalized = (market or 'us-stock').strip().lower()
    return MARKET_ALIASES.get(normalized, normalized)


def get_spec(market: str | None) -> MarketSpec | None:
    return REGISTRY.get(normalize_market(market))


def supported_markets() -> set[str]:
    return set(REGISTRY)


def tradeable_markets() -> tuple[str, ...]:
    return tuple(sorted(spec.value for spec in REGISTRY.values() if spec.tradeable))


def automatable_markets() -> tuple[str, ...]:
    return tuple(sorted(spec.value for spec in REGISTRY.values() if spec.automatable))


def is_server_priced(market: str | None) -> bool:
    spec = get_spec(market)
    return spec.server_priced if spec else False


def contract_multiplier(market: str | None) -> float:
    spec = get_spec(market)
    return spec.contract_multiplier if spec else 1.0


def position_currency(market: str | None, symbol: str | None = None) -> str:
    """Settlement currency for a position.

    Forex is the one market where currency is a property of the symbol rather than the
    market: EURUSD settles in USD, EURJPY in JPY. Canonical forex symbols are the six-letter
    concatenated form (EURUSD), so the quote currency is the trailing three characters.
    """
    spec = get_spec(market)
    if spec is None:
        return 'USD'
    if spec.value == 'forex':
        cleaned = (symbol or '').strip().upper().replace('/', '')
        if len(cleaned) == 6 and cleaned.isalpha():
            return cleaned[3:]
    return spec.currency


def supports_short(market: str | None) -> bool:
    spec = get_spec(market)
    return spec.supports_short if spec else True


# ─── Session calendars ──────────────────────────────────────────────────────
# Replaces the NYSE window that was hardcoded in routes_shared.is_us_market_open() and
# duplicated in the frontend. Unknown sessions fail open, matching prior behavior.

_ET = ZoneInfo('America/New_York')

# NYSE regular hours, as minutes past midnight ET.
_NYSE_OPEN_MIN = 9 * 60 + 30
_NYSE_CLOSE_MIN = 16 * 60
# Forex trades continuously from Sunday 17:00 ET to Friday 17:00 ET.
_FX_WEEK_BOUNDARY_MIN = 17 * 60


def is_session_open(session: str, now: datetime | None = None) -> bool:
    now_et = (now or datetime.now(_ET)).astimezone(_ET)
    weekday = now_et.weekday()  # Mon=0 .. Sun=6
    minutes = now_et.hour * 60 + now_et.minute

    if session == '24x7':
        return True
    if session == 'nyse':
        return weekday < 5 and _NYSE_OPEN_MIN <= minutes < _NYSE_CLOSE_MIN
    if session == '24x5':
        if weekday == 5:  # Saturday — closed all day
            return False
        if weekday == 6:  # Sunday — opens 17:00 ET
            return minutes >= _FX_WEEK_BOUNDARY_MIN
        if weekday == 4:  # Friday — closes 17:00 ET
            return minutes < _FX_WEEK_BOUNDARY_MIN
        return True
    return True


def is_market_open(market: str | None, now: datetime | None = None) -> bool:
    spec = get_spec(market)
    if spec is None:
        return True
    return is_session_open(spec.session, now)
