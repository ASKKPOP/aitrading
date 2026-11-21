"""Long-exit policy for automation (owner decision 2026-11-21).

Owner, verbatim: "buy low price, sell over buy price, that is main";
"only one except, lost ... then selling" -> "15%"; "our target rules is over
5% (base buy price) and AI decision is going down price then selling".

So for a LONG held by automation (a trading run, a fleet, an automation
rule, a platform rail) there are exactly three exits:

  * TARGET    -- price reaches +5% over the buy price (the bracket's
                 take-profit is pinned there);
  * AI SELL   -- the desk decides the price is going down and sells, but only
                 at a price above the buy price plus the round-trip fee;
  * EMERGENCY -- price falls 15% below the buy price (the bracket's
                 stop-loss is pinned there).

Every other automatic close of a long below its buy price plus fees is
refused. A human pressing a button (manual sell, stopping a run or fleet
with flatten, admin action) is NOT automation and is never refused here.

Shorts: the same owner decision made the platform long-only
(futures_policy.shorts_blocked() now defaults ON). Open shorts wind down
under the existing rules; nothing in this module touches them.

Evidence on record against this rule (stated to the owner before building):
docs/reports/2026-11-21-payoff-ratio-exit-replay.md and
docs/reports/2026-11-19-buy-low-take-profit-slots-research.md -- holding
losers raises the closed-trade win rate while positions sit underwater.
The rule ships on the owner's order; the follow-up measurement is the
judge.

Kill switch: LONG_EXIT_POLICY=0 restores the previous behaviour. Fractions:
LONG_TARGET_FRAC (default 0.05) and LONG_EMERGENCY_LOSS_FRAC (default 0.15).
"""

from __future__ import annotations

import os
from typing import Optional


def enabled() -> bool:
    return (os.getenv("LONG_EXIT_POLICY", "1") or "1").strip().lower() \
        not in ("0", "false", "off", "no")


def _frac(env: str, default: float) -> float:
    try:
        v = float(os.getenv(env, "") or default)
    except (TypeError, ValueError):
        return default
    return v if 0.0 < v < 1.0 else default


def target_frac() -> float:
    return _frac("LONG_TARGET_FRAC", 0.05)


def emergency_frac() -> float:
    return _frac("LONG_EMERGENCY_LOSS_FRAC", 0.15)


def _fee_rate(market: Optional[str]) -> float:
    try:
        import fees
        return float(fees.fee_rate(market))
    except Exception:  # noqa: BLE001 -- charging something is the safe side
        return 0.001


def breakeven_price(entry_price: float, market: Optional[str]) -> float:
    """Lowest price at which selling the long nets more than zero after
    both legs' fees."""
    rate = _fee_rate(market)
    return float(entry_price) * (1.0 + rate) / max(1e-12, (1.0 - rate))


def target_price(entry_price: float) -> float:
    return float(entry_price) * (1.0 + target_frac())


def emergency_price(entry_price: float) -> float:
    return float(entry_price) * (1.0 - emergency_frac())


def long_close_refusal(entry_price, price, market: Optional[str],
                       automated: bool = True) -> Optional[str]:
    """Reason to refuse an automated close of a long at `price`, or None.

    None when: the policy is off, the close is human-initiated, the inputs
    are unusable (fail open -- a broken read must never trap a position),
    the price is above breakeven, or the price is at/below the emergency
    level."""
    if not enabled() or not automated:
        return None
    try:
        entry = float(entry_price)
        px = float(price)
    except (TypeError, ValueError):
        return None
    if entry <= 0 or px <= 0:
        return None
    if px > breakeven_price(entry, market):
        return None
    if px <= emergency_price(entry):
        return None
    return (f"long exit policy: selling at {px:g} is below the buy price "
            f"{entry:g} plus fees, and above the {emergency_frac():.0%} "
            "emergency level. The long is held.")


def long_bracket(entry_price) -> Optional[tuple[float, float]]:
    """(stop_loss, take_profit) pinned for a long: -15% / +5% of the buy
    price. None when the policy is off or the entry is unusable."""
    if not enabled():
        return None
    try:
        entry = float(entry_price)
    except (TypeError, ValueError):
        return None
    if entry <= 0:
        return None
    return emergency_price(entry), target_price(entry)
