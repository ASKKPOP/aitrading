"""order_intent.py — the desk states WHAT it wants; a total function compiles it.

Plan 17 (docs/plan/17-ai-order-authority.html). Today the desk emits one of
three verbs and the machine authors every number that matters: exit quantity
is ``max_bet x adapt x conviction x L`` and never references the position, so
"bank half" is unsayable and the fraction actually reduced is a residue of
entry sizing, not a decision. Run 776 held a futures long for 43 cycles while
reporting "I cover the existing short" because the verb space could not
express its book.

This module adds the Order Intent: ``open | add | reduce | close | flip |
hold | arm`` plus a ``size_frac`` whose BASIS SWITCHES WITH THE INTENT —
opens are a fraction of the max bet (risk being taken), exits are a fraction
of the position actually held (risk being shed). The ledger's vocabulary does
not change: intents COMPILE to ``buy | sell | short | cover`` through one
total function over (intent x book x side), because the run-776 class of bug
lives exactly where that mapping is an inline special case.

THE ASYMMETRY carries the entire safety argument:

  * an intent that TAKES risk (open/add, flip's new side) may be clamped DOWN
    and refused by every entry gate;
  * an intent that SHEDS risk (reduce/close) may be clamped UP — never down —
    and ``close`` is never railed at all. There is no safe reason to refuse a
    flatten; refusing one is how a rail becomes the risk.

Rollout mirrors order_params: RUN_ORDER_INTENT = off | shadow | apply,
default SHADOW — the intent is journalled beside the legacy decision on every
cycle, and only ``reduce``/``close`` execute in apply (phase 1: exits first,
because they can only shed risk and that is where the defect lives). ``arm``
and ``flip`` are parsed and journalled but do not execute yet; their apply
phases are gated on shadow evidence per the plan doc.
"""
from __future__ import annotations

import os
from typing import Any, Optional

INTENTS = ("open", "add", "reduce", "close", "flip", "hold", "arm")

# Intents that take risk (budget basis) vs shed it (position basis).
_BUDGET_BASIS = ("open", "add", "flip")
_POSITION_BASIS = ("reduce", "close")

ARM_CONDITIONS = ("price_below", "price_above", "health_below")
ARM_THEN = ("reduce", "close")

# The smallest exit slice worth paying a round trip on. An exit rail may only
# ever RAISE the fraction to reach it — see rail().
MIN_EXIT_NOTIONAL_USD = 1.0


def intent_mode() -> str:
    """off | shadow | apply. Default shadow: journalled beside the legacy
    decision either way, which is what makes the paired reduce measurement in
    the plan doc's §8 possible with nothing at risk."""
    v = (os.getenv("RUN_ORDER_INTENT", "shadow") or "shadow").strip().lower()
    return v if v in ("off", "shadow", "apply") else "shadow"


def parse(raw: Any) -> Optional[dict]:
    """Validate the desk's order_intent object. None = no usable intent, and
    the legacy verb path runs unchanged — backward compatibility is a hard
    requirement (the fallback decision and any older model emit no intent).

    ``size_basis`` is SET HERE from the intent, never read from the model: a
    desk that says "reduce 0.5 of my budget" is confused, and honouring the
    confusion would recreate the defect this module exists to fix.
    """
    if not isinstance(raw, dict):
        return None
    kind = str(raw.get("intent") or "").strip().lower()
    if kind not in INTENTS:
        return None

    out: dict[str, Any] = {"intent": kind,
                           "why": str(raw.get("why") or "")[:300]}

    if kind == "close":
        # Never railed, never partial: close means close.
        out["size_frac"] = 1.0
        out["size_basis"] = "position"
        return out
    if kind == "hold":
        return out

    if kind == "arm":
        arm = raw.get("arm")
        if not isinstance(arm, dict):
            return None
        cond = str(arm.get("if") or "").strip().lower()
        then = str(arm.get("then") or "").strip().lower()
        try:
            level = float(arm.get("level"))
        except (TypeError, ValueError):
            return None
        if cond not in ARM_CONDITIONS or then not in ARM_THEN:
            return None
        if level <= 0 or (cond == "health_below" and not (0.0 < level < 1.0)):
            return None
        frac = 1.0 if then == "close" else _frac(arm.get("size_frac"))
        if frac is None:
            return None
        # arm may only ever shed risk — the `then` enum enforces it here and
        # the compiler has no arm row that opens anything.
        out["arm"] = {"if": cond, "level": level, "then": then,
                      "size_frac": frac}
        out["size_basis"] = "position"
        return out

    frac = _frac(raw.get("size_frac"))
    if frac is None:
        return None
    out["size_frac"] = frac
    out["size_basis"] = "budget" if kind in _BUDGET_BASIS else "position"
    return out


def _frac(v: Any) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if not (0.0 < f <= 1.0):
        return None
    return f


def rail(parsed: dict, *, position_notional_usd: float = 0.0) -> dict:
    """Apply the asymmetric rails. Returns a copy with ``size_frac`` railed
    and ``railed`` describing what moved (empty = untouched).

    open/add/flip: the desk asks to TAKE risk — the rail may only SHRINK it
    (parse already bounds to (0, 1]; nothing here may raise it).
    reduce: the desk asks to SHED risk — the rail may only GROW it. The one
    grow case is dust: a slice too small to clear its own round trip is
    raised to MIN_EXIT_NOTIONAL_USD, never refused.
    close: never railed. The dict passes through byte-identical.
    """
    out = dict(parsed)
    out["railed"] = {}
    kind = out.get("intent")
    if kind == "reduce" and position_notional_usd > 0:
        frac = float(out["size_frac"])
        slice_usd = position_notional_usd * frac
        if slice_usd < MIN_EXIT_NOTIONAL_USD:
            grown = min(1.0, MIN_EXIT_NOTIONAL_USD / position_notional_usd)
            if grown > frac:
                out["railed"] = {"size_frac": {"from": frac, "to": grown,
                                               "why": "dust_slice_grown"}}
                out["size_frac"] = grown
    return out


def compile_intent(kind: str, size_frac: Optional[float], *,
                   is_futures: bool, position_qty: float,
                   bull: Optional[bool]) -> dict:
    """The §6 table as a total function over (intent x book x side).

    Returns {"steps": [{"verb", "size_frac", "basis"}, ...], "note": str}.
    Empty steps + a note is a legal answer (hold, spot bear, flat exit) —
    the note is journalled so a no-op is a record, not a silence.

    ``bull`` is the desk's direction, derived from the legacy verb it emits
    alongside the intent (buy/cover = bull, sell/short = bear); None means
    the desk gave no direction, which makes open/add/flip-from-flat
    uncompilable rather than guessable.
    """
    long_ = position_qty > 0
    short = position_qty < 0
    flat = position_qty == 0

    if kind in ("hold", "arm"):
        return {"steps": [], "note": kind}

    if kind == "reduce":
        if flat:
            return {"steps": [], "note": "reduce_on_flat_noop"}
        verb = "sell" if long_ else "cover"
        return {"steps": [{"verb": verb, "size_frac": float(size_frac or 0),
                           "basis": "position"}], "note": "reduce"}

    if kind == "close":
        if flat:
            return {"steps": [], "note": "close_on_flat_noop"}
        verb = "sell" if long_ else "cover"
        return {"steps": [{"verb": verb, "size_frac": 1.0,
                           "basis": "position"}], "note": "close"}

    if kind == "flip":
        if flat:
            # The table says a flat flip degrades to open — fall through with
            # the desk's stated direction.
            return compile_intent("open", size_frac, is_futures=is_futures,
                                  position_qty=0.0, bull=bull)
        if long_:
            steps = [{"verb": "sell", "size_frac": 1.0, "basis": "position"}]
            if is_futures:
                steps.append({"verb": "short",
                              "size_frac": float(size_frac or 0),
                              "basis": "budget"})
                return {"steps": steps, "note": "flip_long_to_short"}
            # No short on spot: the flip degrades to a plain close — the
            # correct failure mode, since the desk's stated view is that the
            # old position is wrong.
            return {"steps": steps, "note": "flip_spot_degrades_to_close"}
        steps = [{"verb": "cover", "size_frac": 1.0, "basis": "position"},
                 {"verb": "buy", "size_frac": float(size_frac or 0),
                  "basis": "budget"}]
        return {"steps": steps, "note": "flip_short_to_long"}

    if kind in ("open", "add"):
        if bull is None:
            return {"steps": [], "note": "no_direction"}
        if bull:
            if short:
                # open(bull) on a short book: cover first, then buy — two
                # orders, per the table.
                return {"steps": [
                    {"verb": "cover", "size_frac": 1.0, "basis": "position"},
                    {"verb": "buy", "size_frac": float(size_frac or 0),
                     "basis": "budget"}], "note": "open_bull_covers_short"}
            return {"steps": [{"verb": "buy",
                               "size_frac": float(size_frac or 0),
                               "basis": "budget"}], "note": kind}
        # bear
        if not is_futures:
            # n/a -> hold: a spot book cannot express a bear open.
            return {"steps": [], "note": "spot_bear_hold"}
        if long_:
            # Per the table a bear open against a long book compiles to
            # `sell` — it reduces toward the desk's view rather than
            # auto-flipping, which only `flip` may do.
            return {"steps": [{"verb": "sell",
                               "size_frac": float(size_frac or 0),
                               "basis": "budget"}], "note": "open_bear_reduces_long"}
        return {"steps": [{"verb": "short",
                           "size_frac": float(size_frac or 0),
                           "basis": "budget"}], "note": kind}

    # Unreachable while INTENTS and this function agree; kept total anyway.
    return {"steps": [], "note": f"unknown_intent_{kind}"}


def exit_size_usd(size_frac: float, *, position_qty: float, entry: float,
                  leverage: float) -> float:
    """Margin (size_usd) for a position-basis exit slice.

    The permanent tripwire of Plan 17 §2: an exit is a fraction of WHAT IS
    HELD. max_bet_usd must never appear here — deriving an exit from the
    budget is the defect this module exists to fix, and the test suite
    injects that bug back to prove something fails.
    """
    lev = max(1.0, float(leverage or 1.0))
    return abs(float(position_qty or 0)) * float(entry or 0) * \
        max(0.0, min(1.0, float(size_frac))) / lev


def bull_from_action(action: Optional[str]) -> Optional[bool]:
    """The desk's direction, from the legacy verb it emits beside the intent.
    None (hold/absent) leaves direction-needing intents uncompilable."""
    a = (action or "").strip().lower()
    if a in ("buy", "cover"):
        return True
    if a in ("sell", "short"):
        return False
    return None
