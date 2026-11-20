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
  * an open at leverage > 1.

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
from typing import Optional

logger = logging.getLogger(__name__)

SETTING_KEY = "futures_trading_blocked"
ENV_VAR = "FUTURES_TRADING_BLOCKED"

_OFF = ("0", "false", "no", "off")
OPEN_ACTIONS = ("buy", "short")

REFUSAL_PREFIX = "futures trading is disabled on this platform (spot and US stock only)"


def _parse(raw: Optional[str]) -> Optional[bool]:
    value = (raw or "").strip().lower()
    if not value:
        return None
    return value not in _OFF


def futures_blocked(cursor=None) -> bool:
    """True unless an operator explicitly turned the block off.

    `cursor`: pass the caller's cursor when inside a write transaction, so
    the read happens on the same connection. Order: stored setting, then the
    env var, then ON."""
    sql = "SELECT setting_value FROM platform_settings WHERE setting_key = ?"
    try:
        if cursor is not None:
            cursor.execute(sql, (SETTING_KEY,))
            row = cursor.fetchone()
        else:
            from database import get_db_connection
            conn = get_db_connection()
            try:
                own = conn.cursor()
                own.execute(sql, (SETTING_KEY,))
                row = own.fetchone()
            finally:
                conn.close()
        stored = _parse(row["setting_value"] if row else None)
    except Exception as exc:  # noqa: BLE001 — fall through to env, then ON
        logger.warning("futures_policy: setting read failed (%s); using %s "
                       "or the default (blocked)", exc, ENV_VAR)
        stored = None
    if stored is not None:
        return stored
    env = _parse(os.getenv(ENV_VAR))
    return True if env is None else env


def _exposure_kind(action: str, market: Optional[str], leverage: float,
                   market_type: Optional[str] = None) -> Optional[str]:
    """Which futures exposure an OPEN would create, or None for spot."""
    if (action or "").strip().lower() not in OPEN_ACTIONS:
        return None
    if (action or "").strip().lower() == "short":
        return "opening a short"
    if (market or "").strip().lower() == "futures":
        return "a futures-market order"
    if (market_type or "spot").strip().lower() == "futures":
        return "a futures (perpetual) book"
    try:
        lev = float(leverage or 1.0)
    except (TypeError, ValueError):
        lev = 1.0
    if lev > 1.0:
        return f"a {lev:g}x leveraged open"
    return None


def order_refusal(market: Optional[str], action: str, leverage: float = 1.0,
                  market_type: Optional[str] = None, cursor=None) -> Optional[str]:
    """Reason to refuse this order, or None. Closes always get None."""
    kind = _exposure_kind(action, market, leverage, market_type)
    if kind is None or not futures_blocked(cursor):
        return None
    return (f"{REFUSAL_PREFIX}: {kind} is refused. "
            "Closing an existing position is still allowed.")


def run_refusal(market: Optional[str], market_type: Optional[str],
                leverage: float = 1.0, cursor=None) -> Optional[str]:
    """Reason to refuse starting a run with this shape, or None."""
    kind = None
    if (market or "").strip().lower() == "futures":
        kind = "a futures-market run"
    elif (market_type or "spot").strip().lower() == "futures":
        kind = "a futures (perpetual) run"
    else:
        try:
            lev = float(leverage or 1.0)
        except (TypeError, ValueError):
            lev = 1.0
        if lev > 1.0:
            kind = f"a {lev:g}x leveraged run"
    if kind is None or not futures_blocked(cursor):
        return None
    return f"{REFUSAL_PREFIX}: {kind} cannot start. Use a spot run at 1x."


def thesis_refusal(market: Optional[str], direction: Optional[str],
                   cursor=None) -> Optional[str]:
    """Reason a research thesis cannot become a run, or None."""
    if (direction or "").strip().lower() != "short" and \
            (market or "").strip().lower() != "futures":
        return None
    if not futures_blocked(cursor):
        return None
    return "futures_blocked"
