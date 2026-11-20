"""Platform-wide futures block (owner decision 2026-11-20).

From 2026-11-20 sooppiy.com trades spot and US stock only. No futures
orders, runs or fleets anywhere on the platform. This module holds the one
switch and the one definition of a futures exposure, so every entry path
asks the same question.

Switch: platform_settings key `futures_trading_blocked`, with env twin
`FUTURES_TRADING_BLOCKED`. Default ON (blocked). Only an explicit
off/0/false/no unblocks it. The stored setting wins over the env var. If the
setting cannot be read, the env var decides, and with no env var the block
stays ON (fail closed).

What it refuses is OPENING or GROWING futures exposure. "Spot" here means
what the Junior tier already means by it (entitlements.check_futures_access):
no futures book, no leverage. On this ledger that is:
  * a new or larger short, on any market. A spot book holds no inventory
    to sell, so a short is a perp or margin construct;
  * any open on the CME `futures` market;
  * a run whose market_type is 'futures';
  * an open at leverage > 1;
  * any open on the `forex` market (added 2026-11-20, owner: "also exchange
    do not use"), and on `options` and `polymarket` (same day, owner: "Block
    them too"). None of them is spot or US stock.

TWO-WAY UPDATE (owner 2026-11-20 ~18:35Z: "short and long two way";
confirmed in chat as "Crypto + US stock shorts"). Shorts are allowed again
on crypto and US stock, at 1x. A crypto short is a crypto perp book, so a
market_type='futures' run on the `crypto` market at 1x may start again.
Still refused: leverage > 1, the CME `futures` market, forex, options,
Polymarket, and a 'futures' book on any market other than crypto. Shorts
have their own switch so the long-only block can be re-armed without a
deploy: platform_settings key `shorts_trading_blocked`, env twin
`SHORTS_TRADING_BLOCKED`. Default OFF (shorts allowed). It only bites while
the main block above is on.

Closing is NEVER refused. A sell of a long and a cover of a short always pass,
so a position opened before the switch can always be reduced to flat.

Enforced at the ledger (services._update_position_from_signal, the one
function every simulated fill goes through), at the live/shadow gateway
(execution.gateway), and at run start (trading_runs.start_run). The fleet
planner and the signal route also check early, so they refuse with a clear
reason instead of failing at the ledger.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Optional

logger = logging.getLogger(__name__)

SETTING_KEY = "futures_trading_blocked"
ENV_VAR = "FUTURES_TRADING_BLOCKED"
SHORTS_SETTING_KEY = "shorts_trading_blocked"
SHORTS_ENV_VAR = "SHORTS_TRADING_BLOCKED"
# The only market a 1x short / perp book may open on when shorts are allowed
# (US-stock shorts are plain short-sales on a spot book).
PERP_MARKETS = ("crypto",)
# Shorts are an ALLOWLIST (the owner's rule is "crypto and US stock"), so an
# unaliased label ('option', 'cme', '') cannot open one.
SHORT_MARKETS = ("crypto", "us-stock")
# A short sent to a real venue: only US stock (a margin short-sale). Every
# crypto adapter is spot-only, so a live crypto "short" would sell coin the
# ledger does not hold. Crypto shorts stay on the simulated ledger.
LIVE_SHORT_MARKETS = ("us-stock",)

_OFF = ("0", "false", "no", "off")
OPEN_ACTIONS = ("buy", "short")

_SCOPE = "(crypto and US stock at 1x only)"
REFUSAL_PREFIX = f"futures trading is disabled on this platform {_SCOPE}"

# Markets nothing may OPEN on while the block is on. Forex added 2026-11-20
# (owner: "also exchange do not use"): it is neither spot nor US stock.
# Options and Polymarket added the same day (owner: "Block them too").
BLOCKED_MARKETS = ("futures", "forex", "options", "polymarket")

# Non-futures blocked markets: how refusals name them.
_LABEL = {"forex": "forex", "options": "options", "polymarket": "Polymarket"}
_ORDER_KIND = {"forex": "a forex order", "options": "an options order",
               "polymarket": "a Polymarket order"}
_RUN_KIND = {"forex": "a forex run", "options": "an options run",
             "polymarket": "a Polymarket run"}


# An OCC option symbol (AAPL261218C00200000). Same shape as
# price_fetcher._OCC_RE. An option contract booked under another market
# label (us-stock) would slip past a market-only check and be priced at
# multiplier 1 instead of 100.
_OCC_RE = re.compile(r"^[A-Z]{1,6}\d{6}[CP]\d{8}$")


def _is_option_symbol(symbol: Optional[str]) -> bool:
    return bool(_OCC_RE.match((symbol or "").strip().upper()))


def _norm(market: Optional[str]) -> str:
    """Canonical market name, aliases included ('fx', 'currency' -> 'forex'),
    so an alias spelling cannot slip past the block."""
    m = (market or "").strip().lower()
    try:
        from markets import MARKET_ALIASES
        return MARKET_ALIASES.get(m, m)
    except Exception:  # noqa: BLE001
        return m


def _prefix(market: Optional[str]) -> str:
    label = _LABEL.get(_norm(market))
    if label is None:
        return REFUSAL_PREFIX
    return f"{label} trading is disabled on this platform {_SCOPE}"


def _parse(raw: Optional[str]) -> Optional[bool]:
    value = (raw or "").strip().lower()
    if not value:
        return None
    return value not in _OFF


def _switch(key: str, env_var: str, default: bool, cursor=None) -> bool:
    """Stored setting, then the env var, then `default`."""
    sql = "SELECT setting_value FROM platform_settings WHERE setting_key = ?"
    try:
        if cursor is not None:
            cursor.execute(sql, (key,))
            row = cursor.fetchone()
        else:
            from database import get_db_connection
            conn = get_db_connection()
            try:
                own = conn.cursor()
                own.execute(sql, (key,))
                row = own.fetchone()
            finally:
                conn.close()
        stored = _parse(row["setting_value"] if row else None)
    except Exception as exc:  # noqa: BLE001 — fall through to env, then default
        logger.warning("futures_policy: %s read failed (%s); using %s "
                       "or the default", key, exc, env_var)
        stored = None
    if stored is not None:
        return stored
    env = _parse(os.getenv(env_var))
    return default if env is None else env


def futures_blocked(cursor=None) -> bool:
    """True unless an operator explicitly turned the block off.

    `cursor`: pass the caller's cursor when inside a write transaction, so
    the read happens on the same connection. Order: stored setting, then the
    env var, then ON (fail closed)."""
    return _switch(SETTING_KEY, ENV_VAR, True, cursor)


def shorts_blocked(cursor=None) -> bool:
    """True when the main block is on AND shorts are re-armed as blocked.
    Default: shorts allowed (owner 2026-11-20, two-way)."""
    if not futures_blocked(cursor):
        return False
    return _switch(SHORTS_SETTING_KEY, SHORTS_ENV_VAR, False, cursor)


# Which market each short-capable book type may live on.
_BOOK_MARKETS = {"futures": PERP_MARKETS, "margin": ("us-stock",)}


def _book_ok(market: Optional[str], market_type: Optional[str], cursor=None) -> bool:
    """A short-capable book of this type on this market is allowed right now:
    'futures' (perp) on crypto, 'margin' (short-sale) on US stock."""
    allowed = _BOOK_MARKETS.get((market_type or "spot").strip().lower())
    return bool(allowed) and _norm(market) in allowed and not shorts_blocked(cursor)


def _exposure_kind(action: str, market: Optional[str], leverage: float,
                   market_type: Optional[str] = None,
                   symbol: Optional[str] = None, cursor=None,
                   live: bool = False) -> Optional[str]:
    """Which refused exposure an OPEN would create, or None if allowed."""
    act = (action or "").strip().lower()
    if act not in OPEN_ACTIONS:
        return None
    if _norm(market) == "futures":
        return "a futures-market order"
    if _norm(market) in _ORDER_KIND:
        return _ORDER_KIND[_norm(market)]
    if _is_option_symbol(symbol):
        return "an options contract"
    if act == "short":
        if shorts_blocked(cursor) or _norm(market) not in SHORT_MARKETS:
            return "opening a short"
        if live and _norm(market) not in LIVE_SHORT_MARKETS:
            return "a live crypto short (no perp venue is connected)"
    mt = (market_type or "spot").strip().lower()
    if mt in _BOOK_MARKETS and not _book_ok(market, mt, cursor):
        return ("a margin (short-sale) book" if mt == "margin"
                else "a futures (perpetual) book")
    try:
        lev = float(leverage or 1.0)
    except (TypeError, ValueError):
        lev = 1.0
    if lev > 1.0:
        return f"a {lev:g}x leveraged open"
    return None


def order_refusal(market: Optional[str], action: str, leverage: float = 1.0,
                  market_type: Optional[str] = None, cursor=None,
                  symbol: Optional[str] = None, live: bool = False) -> Optional[str]:
    """Reason to refuse this order, or None. Closes always get None.
    `symbol`: pass it where known, so an option contract under another
    market label is refused too. `live`: the order goes to a real venue
    (live or shadow), where only a US-stock short is possible."""
    if not futures_blocked(cursor):
        return None
    kind = _exposure_kind(action, market, leverage, market_type, symbol, cursor,
                          live)
    if kind is None:
        return None
    prefix = _prefix("options") if kind == "an options contract" else _prefix(market)
    return (f"{prefix}: {kind} is refused. "
            "Closing an existing position is still allowed.")


def run_refusal(market: Optional[str], market_type: Optional[str],
                leverage: float = 1.0, cursor=None,
                symbol: Optional[str] = None) -> Optional[str]:
    """Reason to refuse starting a run with this shape, or None."""
    kind = None
    if _norm(market) == "futures":
        kind = "a futures-market run"
    elif _norm(market) in _RUN_KIND:
        kind = _RUN_KIND[_norm(market)]
    elif _is_option_symbol(symbol):
        kind = "an options-contract run"
        market = "options"
    elif ((market_type or "spot").strip().lower() in _BOOK_MARKETS
          and not _book_ok(market, market_type, cursor)):
        kind = ("a margin (short-sale) run"
                if (market_type or "").strip().lower() == "margin"
                else "a futures (perpetual) run")
    else:
        try:
            lev = float(leverage or 1.0)
        except (TypeError, ValueError):
            lev = 1.0
        if lev > 1.0:
            kind = f"a {lev:g}x leveraged run"
    if kind is None or not futures_blocked(cursor):
        return None
    return f"{_prefix(market)}: {kind} cannot start. Use a 1x spot run, or a 1x crypto run."


def thesis_refusal(market: Optional[str], direction: Optional[str],
                   cursor=None) -> Optional[str]:
    """Reason a research thesis cannot become a run, or None."""
    m = _norm(market)
    short = (direction or "").strip().lower() == "short"
    if not short and m not in BLOCKED_MARKETS:
        return None
    if not futures_blocked(cursor):
        return None
    if m in _LABEL:
        return f"{m}_blocked"
    if m == "futures" or shorts_blocked(cursor):
        return "futures_blocked"
    return None


def blocked_markets(cursor=None) -> tuple[str, ...]:
    """Markets with no new opens right now (empty when the block is off)."""
    return BLOCKED_MARKETS if futures_blocked(cursor) else ()
