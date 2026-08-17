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
        # Plan 24 fix 4 (live run 1083, 2026-08-12): repeated "cover half"
        # decayed a winner to a $4.45 remainder that can never clear its own
        # round trip — babysat by 30-min desk cycles thereafter. A reduce
        # whose REMAINDER would fall below the manage-worthy floor grows to
        # a full close. Still shed-only: the rail may only grow a reduce.
        frac = float(out["size_frac"])
        floor = _dust_remainder_usd()
        if frac < 1.0 and position_notional_usd * (1.0 - frac) < floor:
            # 2026-08-16, fleet 35, n=4: the desk authored `reduce 0.5`
            # into this escalation four times — SUI at a $47.32 book where
            # the rendered bound was 47.2% (missed by 2.8 points), DOT at
            # $40.42, twice below — and in THREE of them it stated it
            # wanted to KEEP the remainder. Growing to a full close does
            # the opposite of the desk's own stated intent, and authorship
            # belongs to the desk (#119).
            #
            # Plan 24 fix 4's actual harm was an UN-BANKABLE $4.45
            # remainder. Clamping to leave exactly the manage-worthy floor
            # prevents that harm too, so the clamp is preferred WHENEVER a
            # meaningful partial is still possible; below that the old
            # grow-to-full stands (DOT at $25.47 could only shed 1.8% — a
            # sliver that pays a full round trip to shed nothing).
            max_reduce = (1.0 - floor / position_notional_usd) \
                if position_notional_usd > 0 else 0.0
            if max_reduce >= _MEANINGFUL_PARTIAL:
                out["railed"] = {"size_frac": {"from": frac, "to": max_reduce,
                                               "why": "dust_remainder_clamped"}}
                out["size_frac"] = max_reduce
            else:
                out["railed"] = {"size_frac": {"from": frac, "to": 1.0,
                                               "why": "dust_remainder_closed"}}
                out["size_frac"] = 1.0
    return out


# Smallest clamped reduce worth executing: below this the clamp would author
# a sliver that pays a full round trip to shed almost nothing, so the rail
# grows to a full close instead (DOT 1308 at $25.47 could shed only 1.8%).
_MEANINGFUL_PARTIAL = 0.25


def _dust_remainder_usd() -> float:
    """Notional below which a position is not worth managing: at the R1
    fee-hurdle geometry (~2.4% favourable move to break even on flat-fee
    minimums) a remainder under ~$25 cannot pay for its own exit plus the
    desk attention it consumes. Env-tunable; 0 disables."""
    try:
        return max(0.0, float(os.getenv("RUN_DUST_REMAINDER_USD", "25")))
    except (TypeError, ValueError):
        return 25.0


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


# ── arm execution (2026-08-05) ─────────────────────────────────────────────
# An `arm` is the desk PRE-COMMITTING an exit to a price level so it fires
# BETWEEN decision cycles. Until now nothing consumed one: 54 arm intents
# were emitted lifetime and every single one was discarded.
#
# Cycle 65 measured why that mattered. On 2026-08-05 every losing run was in
# PROFIT first, and for four of seven the profit existed ONLY between
# decisions — dwell above half-peak was 5-20 minutes against a ~45 minute
# cycle, so runs 967 and 957 never had a single cycle while in profit. The
# desk cannot bank what it never sees, and no prompt lesson can reach a
# window in which no prompt is rendered. The arm is the mechanism that can.
#
# GAP-THROUGH SEMANTICS, resolved from this module's own doctrine: ARM_THEN
# is restricted to ("reduce", "close"), so an arm can only ever SHED risk.
# The asymmetry at the top of this file says a risk-shedding intent may be
# clamped UP and is never refused — "there is no safe reason to refuse a
# flatten; refusing one is how a rail becomes the risk". Therefore a fired
# arm executes at the NEXT AVAILABLE MARK regardless of how far price gapped
# past the level. Slippage is journalled, never a veto.

# Conditions this executor can actually evaluate. `health_below` parses and
# journals but does NOT fire — margin health is not carried on the control
# pass. Kept explicit rather than silently ignored: an unexecutable arm the
# desk believes in is exactly the "flag with no executor" class of bug.
EXECUTABLE_ARM_CONDITIONS = ("price_below", "price_above")


def classify_arm(arm: Any, *, entry: float, is_short: bool,
                 fee_rate: float) -> Optional[str]:
    """Does this armed exit fire in PROFIT or in LOSS? Label, never a veto.

    Measured 2026-08-17 over 134 arms holding a live position: **77 fire on
    the banking side, 57 (43%) fire on the losing side.** SOL run 1367 is the
    worked example and cost -$0.114: a short entered at 75.51, breakeven
    including the round trip 75.4421, and its ONLY pre-committed exit armed
    at `price_above 75.56` — a level it could reach only underwater. The
    desk's report called that *"preserving profit"*, and across five cycles
    it never placed a profit-side arm, because it believed it already had
    one. The market sat at or below breakeven for 66 of its 84 minutes.

    A `defensive` arm is a legitimate stop and is NOT rejected. The defect is
    that the two are indistinguishable on the tape and in the brief, so the
    desk cannot be told which it holds. Fee-inclusive on purpose: an arm
    between breakeven and entry looks profitable on price alone and is not.

    Returns "protective" | "defensive" | None (unusable input)."""
    if not isinstance(arm, dict):
        return None
    try:
        level = float(arm.get("level"))
        e = float(entry)
        rate = float(fee_rate)
    except (TypeError, ValueError):
        return None
    if level <= 0 or e <= 0:
        return None
    cond = str(arm.get("if") or "").strip().lower()
    if cond not in EXECUTABLE_ARM_CONDITIONS:
        return None
    breakeven = e * (1 - 2 * rate) if is_short else e * (1 + 2 * rate)
    banks = level <= breakeven if is_short else level >= breakeven
    return "protective" if banks else "defensive"


def arm_level_implausible(level: Any, *, entry: float,
                          max_ratio: float = 10.0) -> bool:
    """Is this arm level so far from entry that it cannot be a plan?

    run 1297 LTCUSDT armed at **44700.00** against an entry of **44.09** —
    ~1000x out and unfireable for the life of the run. #446's unit-slip
    converter rails `order_params` percentages; nothing covered arm levels,
    so the number simply sat there. Deliberately loose (10x) — this catches
    decimal slips, not aggressive targets."""
    try:
        lv, e = float(level), float(entry)
    except (TypeError, ValueError):
        return False
    if lv <= 0 or e <= 0:
        return False
    ratio = lv / e if lv > e else e / lv
    return ratio > max_ratio


def arm_fires(arm: Optional[dict], *, mark: Optional[float]) -> bool:
    """Does this armed exit trigger at `mark`? Pure predicate, fail-closed.

    Fail-closed matters in both directions here: a missing/garbage arm must
    never fire (it would exit a position the desk never asked to exit), and
    a missing mark must never fire (it would price the exit on data we have
    already declared untrustworthy — the stop_eval_failed lesson).
    """
    if not isinstance(arm, dict) or mark is None:
        return False
    try:
        m = float(mark)
        level = float(arm.get("level"))
    except (TypeError, ValueError):
        return False
    if m <= 0 or level <= 0:
        return False
    cond = str(arm.get("if") or "").strip().lower()
    if cond not in EXECUTABLE_ARM_CONDITIONS:
        return False
    if str(arm.get("then") or "").strip().lower() not in ARM_THEN:
        return False
    return m < level if cond == "price_below" else m > level


def arm_exit_fraction(arm: Optional[dict]) -> float:
    """How much of the position a fired arm sheds. `close` is always the
    whole book; `reduce` carries its own fraction. Clamped to (0, 1]."""
    if not isinstance(arm, dict):
        return 0.0
    if str(arm.get("then") or "").strip().lower() == "close":
        return 1.0
    try:
        f = float(arm.get("size_frac"))
    except (TypeError, ValueError):
        return 0.0
    return f if 0.0 < f <= 1.0 else 0.0
