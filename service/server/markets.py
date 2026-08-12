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
from datetime import datetime, timedelta
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
    'futures': MarketSpec(
        value='futures',
        currency='USD',
        # Overridden per contract by contract_multiplier() — ES is $50/point,
        # GC $100. The spec value is the fallback for an unlisted contract.
        contract_multiplier=1.0,
        session='cme',
        price_provider='yahoo',
        supports_short=True,
        tradeable=True,
        automatable=True,
        price_decimals=2,
        server_priced=True,
    ),
    'options': MarketSpec(
        value='options',
        currency='USD',
        # US equity options are 100 shares per contract. Unlike futures this is
        # uniform, so it lives in the spec rather than a per-symbol table.
        contract_multiplier=100.0,
        session='nyse',
        price_provider='yahoo-options',
        # Selling to open (naked short) is not modelled; see
        # services._update_position_from_signal.
        supports_short=False,
        tradeable=True,
        # Chain selection has no automation surface yet — a rule cannot express
        # "roll to the next expiry", so runs may not target options.
        automatable=False,
        price_decimals=2,
        server_priced=True,
    ),
}

# USD per full point of price movement, per exchange contract specs (verified
# 2026-07-20). Keyed by the canonical root symbol; price_fetcher appends '=F'
# for Yahoo. Grains (ZC/ZS/ZW) quote in cents per bushel on a 5,000 bushel
# contract, so one quoted point is one cent and the multiplier is 50, not 5000.
FUTURES_MULTIPLIERS: dict[str, float] = {
    'ES': 50.0,      # E-mini S&P 500
    'MES': 5.0,      # Micro E-mini S&P 500
    'NQ': 20.0,      # E-mini Nasdaq-100
    'MNQ': 2.0,      # Micro E-mini Nasdaq-100
    'YM': 5.0,       # E-mini Dow
    'MYM': 0.5,      # Micro E-mini Dow
    'RTY': 50.0,     # E-mini Russell 2000
    'M2K': 5.0,      # Micro E-mini Russell 2000
    'CL': 1000.0,    # WTI crude, 1,000 barrels
    'MCL': 100.0,    # Micro WTI crude
    'NG': 10000.0,   # Henry Hub natural gas, 10,000 MMBtu
    'GC': 100.0,     # Gold, 100 troy oz
    'MGC': 10.0,     # Micro gold
    'SI': 5000.0,    # Silver, 5,000 troy oz
    'HG': 25000.0,   # Copper, 25,000 lb
    'ZB': 1000.0,    # 30-year T-Bond, $100k face quoted in points
    'ZN': 1000.0,    # 10-year T-Note
    'ZF': 1000.0,    # 5-year T-Note
    'ZC': 50.0,      # Corn
    'ZS': 50.0,      # Soybeans
    'ZW': 50.0,      # Wheat
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


def contract_multiplier(market: str | None, symbol: str | None = None) -> float:
    """Notional per point of price movement.

    Futures are the one market where this is a property of the contract rather
    than the market: ES is $50/point, GC $100. Every other market answers from
    its spec. An unlisted futures root falls back to the spec value (1.0) —
    wrong-but-inert is better than refusing to price a contract, and
    FUTURES_SYMBOLS is what the UI actually offers.
    """
    spec = get_spec(market)
    if spec is None:
        return 1.0
    if spec.value == 'futures':
        root = (symbol or '').strip().upper().removesuffix('=F')
        return FUTURES_MULTIPLIERS.get(root, spec.contract_multiplier)
    return spec.contract_multiplier


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
# Plan 23 Phase A: the clock alone called Thanksgiving an ordinary Thursday —
# fatal for a swing archetype that holds overnight and queues terminal actions
# for "the next open". Static tables, extended yearly (they change annually);
# a date missing from BOTH tables is an ordinary session, so an out-of-date
# table degrades to the old weekday-only behavior, never to a stuck market.
_NYSE_HOLIDAYS = {
    # 2026: New Year, MLK, Presidents, Good Friday, Memorial, Juneteenth,
    # July-4th observed (Sat → Fri 7/3, FULL close), Labor, Thanksgiving,
    # Christmas.
    "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25",
    "2026-06-19", "2026-07-03", "2026-09-07", "2026-11-26", "2026-12-25",
    # 2027: Juneteenth observed Fri 6/18 (Sat), July-4th observed Mon 7/5
    # (Sun), Christmas observed Fri 12/24 (Sat).
    "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26", "2027-05-31",
    "2027-06-18", "2027-07-05", "2027-09-06", "2027-11-25", "2027-12-24",
}
# 13:00-ET early closes: the Friday after Thanksgiving; Christmas Eve when
# it is a trading day.
_NYSE_HALF_DAYS = {"2026-11-27", "2026-12-24", "2027-11-26"}
_NYSE_HALF_CLOSE_MIN = 13 * 60
# Forex trades continuously from Sunday 17:00 ET to Friday 17:00 ET.
_FX_WEEK_BOUNDARY_MIN = 17 * 60

# CME Globex: Sunday 18:00 ET open, a daily 17:00–18:00 ET maintenance halt,
# Friday 17:00 ET close.
_CME_HALT_START_MIN = 17 * 60
_CME_OPEN_MIN = 18 * 60

def is_session_open(session: str, now: datetime | None = None) -> bool:
    now_et = (now or datetime.now(_ET)).astimezone(_ET)
    weekday = now_et.weekday()  # Mon=0 .. Sun=6
    minutes = now_et.hour * 60 + now_et.minute

    if session == '24x7':
        return True
    if session == 'nyse':
        if weekday >= 5:
            return False
        day = now_et.strftime('%Y-%m-%d')
        if day in _NYSE_HOLIDAYS:
            return False
        close = _NYSE_HALF_CLOSE_MIN if day in _NYSE_HALF_DAYS else _NYSE_CLOSE_MIN
        return _NYSE_OPEN_MIN <= minutes < close
    if session == '24x5':
        if weekday == 5:  # Saturday — closed all day
            return False
        if weekday == 6:  # Sunday — opens 17:00 ET
            return minutes >= _FX_WEEK_BOUNDARY_MIN
        if weekday == 4:  # Friday — closes 17:00 ET
            return minutes < _FX_WEEK_BOUNDARY_MIN
        return True
    if session == 'cme':
        if weekday == 5:  # Saturday — closed all day
            return False
        if weekday == 6:  # Sunday — opens 18:00 ET
            return minutes >= _CME_OPEN_MIN
        if weekday == 4:  # Friday — closes 17:00 ET, no reopen
            return minutes < _CME_HALT_START_MIN
        # Mon–Thu run around the clock except the daily maintenance halt.
        return not (_CME_HALT_START_MIN <= minutes < _CME_OPEN_MIN)
    return True


def is_market_open(market: str | None, now: datetime | None = None) -> bool:
    spec = get_spec(market)
    if spec is None:
        return True
    return is_session_open(spec.session, now)


# A market that is open but about to close is, for a run being BUILT right now,
# effectively shut: the run gets one cycle and then parks until the next
# session. Live 2026-07-28 — ORCL and CAT were composed at 19:56:40 UTC, three
# minutes and twenty seconds before the NYSE close, and spent the next nine
# hours on `pre: market closed` before the idle rail collected them. Neither
# ever saw an open session. is_market_open() was true at that instant and told
# the builder nothing useful.
def session_minutes_left(market: str | None, now: datetime | None = None,
                         horizon_min: int = 24 * 60) -> int:
    """Whole minutes the market stays open from `now`, capped at horizon_min.

    0 when it is already shut. Probes forward a minute at a time — the session
    calendars are pure functions of the clock, so this needs no new schedule
    table to fall out of step with is_session_open()."""
    spec = get_spec(market)
    if spec is None:
        return horizon_min
    start = (now or datetime.now(_ET))
    # spec.session, not market: is_session_open() keys on the SESSION name and
    # returns True for anything else, so passing "us-stock" here silently
    # skipped this exit and left the bisection measuring a shut clock.
    if not is_session_open(spec.session, start):
        return 0
    lo, hi = 0, max(0, int(horizon_min))
    # The open window is contiguous forward from an open `now`, so the first
    # closed minute can be found by bisection instead of a linear walk.
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if is_market_open(market, start + timedelta(minutes=mid)):
            lo = mid
        else:
            hi = mid - 1
    return lo
