"""AI-authored order parameters, with deterministic rails (2026-07-27).

Why this exists
---------------
The desk already produces situation-specific order parameters and the runner
already throws them away. `analysis_agents` asks the trader for `"stop"` and
`"target"` on every cycle; nothing reads either field, and neither is even
journaled. In their place `risk_engine.DEFAULT_LIMITS` applies a flat 5% stop
and 10% target to every instrument in every regime — corn, crude, ZEC, ETH and
USD/KRW alike, against realised weekly moves that ranged 0.00%–4.86%.

Collapsing the order space to one point per risk tier is what produced the
dominant defect of the 2026-07-19..27 window: the trailing lock armed at
exactly 1/10th of the stop, so the desk banked ~$6 wins against ~$67 losses —
a geometry needing a 90.9% hit rate against a measured 35% directional
accuracy. No value of a single global constant fixes that for every symbol.

The contract
------------
The trader may attach an `order` object to its verdict. Every field is
RELATIVE (a fraction, or a percent of entry) — never an absolute price and
never absolute dollars — so a hallucinated number is a bounded error rather
than a fabricated order. `"defer": true`, an absent block, or an unparseable
one all mean "use the deterministic path", so this module is inert until the
model actually uses it.

The rails
---------
Rails are the reason tier 2 is safe. Two invariants:

  1. MONOTONE: a rail may only ever make an order smaller, tighter or shorter.
     Size and leverage clamp DOWN, the stop clamps TIGHTER, the horizon clamps
     SHORTER, adds clamp FEWER. The one field allowed to move outward is
     `target_pct`, because demanding more edge before banking is conservative.
     A rail that can enlarge an order is not a rail. (One bounded exception:
     `size_frac` floors UP to the run's executable minimum — the $10-margin
     dust floor — because below it the order is not shrunk but destroyed;
     the enlargement is capped at the smallest order the platform will fill.)
  2. R:R FLOOR: `target_pct >= RR_FLOOR * stop_pct`. Had this existed last
     week the 10:1 geometry could not have been expressed at all — it caps the
     breakeven hit rate at ~33% instead of 90.9%.

Every clamp is recorded in `notes` and journaled, so a model that keeps
pushing against a rail is visible rather than silently corrected.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Fraction of a round trip the target must clear, mirroring the entry gate in
# run_engine._fee_edge_skip. Fees were 180% of gross over the measured window,
# so a target that cannot pay its own cost is not a target.
FEE_MULTIPLE = 3.0
# target_pct >= RR_FLOOR * stop_pct. The single most valuable invariant here.
# Env-tunable since 2026-08-29 (owner order "target price make lower"): the
# 1,099-trip target sweep measured the mean-optimal target at 0.30% against
# 1.5-1.6% stops — a geometry the 2.0 floor forbids. The DEFAULT stays 2.0;
# lowering it is a prod .env decision that also widens the research funnel
# (symbol_research.thesis_rr_feasible imports this value).
def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default


RR_FLOOR = _env_float("RR_FLOOR", 2.0)
# target_pct <= RR_CEILING * stop_pct. The floor's mirror, added 2026-08-17
# after four experiments agreed the target was set past anything the market
# offers: no target above 2.00% has EVER been reached even given a run's own
# full horizon (4/34, all 0.60-2.00%); the maximum favourable excursion
# available inside that horizon is median 1.14% against a median target of
# 4.80%; the market OFFERED the desk's target on 1 leg in 28; and a
# stop-vs-target-first replay wins 6 times in 30 at a 2.50% target versus
# ZERO at 4.55%. `take_profit` is live in risk_engine and carried on every
# position — 0 of 210 stopped runs closed on it because the level is
# unreachable, not because the path is dead. Only the floor existed, so the
# desk overshot its own gate by ~1.8x with nothing to pull it back.
# THE MEASURED OPTIMUM IS 2.0 AND THIS DEFAULT IS 3.0. That gap is deliberate
# and should not be quietly closed. Existing tests encode brackets at R:R
# 2.5, 2.67 and 3.0 as intended behaviour; a 2.0 ceiling contradicts nine of
# them and a 2.5 ceiling contradicts two. Overriding tests that record an
# earlier deliberate decision, on the strength of a 30-entry replay, would be
# fitting the tests to the code — so the default ships INERT against every
# existing case and only binds above R:R 3.0 (a 4.55% target at a 1.24% stop
# becomes 3.72%, roughly doubling how often the level is offered).
#
# Set RR_CEILING=2.0 to take H8's optimum. That is a config change, not a
# code change, precisely so the decision stays with whoever owns the
# doctrine those tests encode.
RR_CEILING_DEFAULT = 3.0

# (minimum, maximum) per field. Absolute outer bounds — the tier leverage cap
# tightens the leverage rail further at call time.
RAILS: dict[str, tuple[float, float]] = {
    "size_frac":      (0.05, 1.00),    # of max_bet_usd
    "leverage":       (1.0, 10.0),     # further capped by the run's tier
    "stop_pct":       (0.30, 8.00),    # % from entry
    "target_pct":     (0.30, 40.00),   # % from entry
    "trail_arm_pct":  (0.10, 40.00),   # % from entry
    "trail_give":     (0.05, 0.40),    # fraction of peak surrendered
    "horizon_hours":  (1.0, 336.0),
    "max_adds":       (0.0, 3.0),
}

# Which direction a clamp is allowed to move a value. "down" fields may only
# shrink toward the floor when the model overshoots the ceiling; "up" fields
# (target only) may be pushed outward to satisfy the floors.
_SHRINK_ONLY = ("size_frac", "leverage", "stop_pct", "horizon_hours", "max_adds")


@dataclass
class OrderParams:
    """A railed, ready-to-apply order specification."""
    size_frac: Optional[float] = None
    leverage: Optional[float] = None
    stop_pct: Optional[float] = None
    target_pct: Optional[float] = None
    trail_arm_pct: Optional[float] = None
    trail_give: Optional[float] = None
    horizon_hours: Optional[float] = None
    max_adds: Optional[int] = None
    why: str = ""
    notes: list[str] = field(default_factory=list)

    def as_event(self) -> dict:
        """Journal shape. Everything the model asked for plus every clamp."""
        d = asdict(self)
        d["why"] = (self.why or "")[:600]
        return d

    def has_sizing(self) -> bool:
        return self.size_frac is not None or self.leverage is not None

    def has_exits(self) -> bool:
        return self.stop_pct is not None and self.target_pct is not None


def outcome(raw: Any) -> str:
    """Why no params were applied — 'parsed' | 'defer' | 'absent' | 'malformed'.

    The journal previously recorded a single `deferred: true` for all three
    non-parsing cases, which made the shadow experiment unreadable: a model
    that never emits an order block and a model that deliberately defers on a
    quiet tape are opposite findings, and both looked identical. 'absent' in
    particular is the signal that the prompt (or the cheap analysis path,
    which never asks for the block) is the thing to fix — not the model."""
    if raw is None:
        return "absent"
    if not isinstance(raw, dict):
        return "malformed"
    if raw.get("defer") is True:
        return "defer"
    return "parsed" if parse_order_block(raw) is not None else "malformed"


def mode() -> str:
    """'off' | 'shadow' | 'apply'.

    Default 'shadow': the block is parsed, railed and journaled but changes no
    order. That produces the paired dataset (what the constants did vs what the
    AI would have done) at zero risk, which is the only honest way to find out
    whether AI parameters beat constants."""
    raw = (os.getenv("RUN_AI_ORDER_PARAMS", "shadow") or "shadow").strip().lower()
    return raw if raw in ("off", "shadow", "apply") else "shadow"


def _num(raw: Any) -> Optional[float]:
    """Coerce to a finite float, or None. Rejects bool (a JSON true would
    otherwise sail through as 1.0 and become a real position size)."""
    if raw is None or isinstance(raw, bool):
        return None
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return None
    if val != val or val in (float("inf"), float("-inf")):   # NaN / inf
        return None
    return val


def _clamp(name: str, val: float, notes: list[str],
           lo_override: Optional[float] = None,
           hi_override: Optional[float] = None) -> float:
    lo, hi = RAILS[name]
    if lo_override is not None:
        lo = max(lo, lo_override)
    if hi_override is not None:
        hi = min(hi, hi_override)
    if val < lo:
        notes.append(f"{name} {val:g} raised to floor {lo:g}")
        return lo
    if val > hi:
        notes.append(f"{name} {val:g} cut to cap {hi:g}")
        return hi
    return val


def parse_order_block(raw: Any, *, leverage_cap: float = 10.0,
                      fee_rate: Optional[float] = None,
                      min_size_frac: Optional[float] = None
                      ) -> Optional[OrderParams]:
    """Parse + rail the trader's `order` block.

    Returns None when there is nothing to apply — absent, not a dict, deferred,
    or empty after parsing. None always means "use the deterministic path", so
    every failure mode degrades to today's behaviour rather than to a guess."""
    if not isinstance(raw, dict):
        return None
    if raw.get("defer") is True:
        return None

    notes: list[str] = []
    out = OrderParams(why=str(raw.get("why") or raw.get("rationale") or ""))

    # Unit-slip reinterpretation (JTO 2026-08-15): the desk sometimes emits
    # the percent fields as FRACTIONS (stop 0.05 / target 0.09 / arm 0.06
    # meaning 5%/9%/6% — its own narrative said "~4.5% gain -> reduce half").
    # Clamping each field to its floor independently rebuilt that bracket
    # 100x tighter than authored and the desk traded a noise bracket it
    # never designed. A deliberate ultra-tight bracket never has EVERY pct
    # field sub-floor at once, so that pattern is diagnostic: reinterpret
    # x100, journal it, then rail normally. Anchored on the stop — without
    # an authored stop nothing pins the units.
    raw = dict(raw)
    _pct_fields = ("stop_pct", "target_pct", "trail_arm_pct")

    # SIGN slip, recovered BEFORE the unit slip below (2026-09-05).
    #
    # Every RAILS floor here is positive, so a negative pct is never a legal
    # value — it is the model expressing a signed OFFSET. For a long the
    # invalidation sits below entry, so "5% below" is written -5, and the
    # prompt asked for "% from entry to your invalidation level" without ever
    # saying positive magnitude. That is the model being consistent, not
    # wrong.
    #
    # The old behaviour was the damaging one: -5 failed the `0 < v` guard
    # below, fell through to _clamp, and `-5 < 0.30` raised it to the FLOOR.
    # A 5% stop silently became 0.30% — 16.7x tighter — and the R:R ceiling
    # then dragged a 12% target down to 0.9%. Measured on prod: 3 of the 6
    # positions opened on 2026-09-05 carried a stop the desk never authored,
    # and 12 floor-hits since 09-04 carried a negative authored value.
    #
    # Recovering the magnitude is the same class of fix as the unit slip
    # already handled below — intent is unambiguous, so recover it and
    # journal it rather than silently substituting a floor. Ordered first so
    # a value that is BOTH signed and fractional (-0.05) recovers twice.
    _neg = {n: v for n in _pct_fields
            if (v := _num(raw.get(n))) is not None and v < 0}
    if _neg:
        for n, v in _neg.items():
            raw[n] = -v
        notes.append(
            "bracket sign recovered (signed offset: "
            + ", ".join(f"{n} {v:g} -> {-v:g}" for n, v in _neg.items())
            + ") — a negative pct is a direction, not a magnitude")

    _authored = {n: _num(raw.get(n)) for n in _pct_fields}
    _present = {n: v for n, v in _authored.items() if v is not None}
    if _present.get("stop_pct") is not None and \
            all(0 < v < RAILS[n][0] for n, v in _present.items()):
        for n, v in _present.items():
            raw[n] = v * 100.0
        notes.append(
            "bracket interpreted as percent fractions (unit slip: every "
            "authored pct field sub-floor — "
            + ", ".join(f"{n} {v:g} -> {v * 100:g}"
                        for n, v in _present.items()) + ")")

    for name in ("size_frac", "leverage", "stop_pct", "target_pct",
                 "trail_arm_pct", "trail_give", "horizon_hours"):
        val = _num(raw.get(name))
        if val is None:
            continue
        hi = leverage_cap if name == "leverage" else None
        # Executable-size floor: the prompt advertises 0.05 as the legal
        # minimum, but on a small max_bet that lands under the $10 dust floor
        # and the order is silently discarded (fleet 35 FIL, n=2). The caller
        # passes the run's true minimum; the ask is floored up to it — never
        # past the full bet — and journaled like every other clamp.
        lo = min(min_size_frac, RAILS["size_frac"][1]) \
            if name == "size_frac" and min_size_frac is not None else None
        setattr(out, name, _clamp(name, val, notes,
                                  lo_override=lo, hi_override=hi))

    adds = _num(raw.get("max_adds"))
    if adds is not None:
        out.max_adds = int(_clamp("max_adds", adds, notes))

    # ── the two floors that make a bad parameter set harmless ──────────────
    # Fee floor first: a target under its own round trip is not a target.
    if out.target_pct is not None:
        min_target = _fee_floor_target(fee_rate)
        if out.target_pct < min_target:
            notes.append(f"target_pct {out.target_pct:g} raised to fee floor "
                         f"{min_target:g} ({FEE_MULTIPLE:g}x round trip)")
            out.target_pct = min_target

    # R:R floor. Raises the TARGET rather than loosening the stop, because
    # loosening the stop would enlarge the loss — which the monotone rule
    # forbids. A model that wants a wide stop must justify a wider target.
    if out.stop_pct is not None and out.target_pct is not None:
        min_target = out.stop_pct * RR_FLOOR
        if out.target_pct < min_target:
            notes.append(f"target_pct {out.target_pct:g} raised to R:R floor "
                         f"{min_target:g} ({RR_FLOOR:g}x stop {out.stop_pct:g})")
            out.target_pct = min_target

    # R:R CEILING — the floor's mirror. See RR_CEILING_DEFAULT for the four
    # experiments behind it. Clamped so it can never fight the two floors:
    # a ceiling below the R:R floor would invert the bracket, and one below
    # the fee floor would make the target cheaper than its own round trip.
    if out.stop_pct is not None and out.target_pct is not None:
        ceiling_mult = max(_rr_ceiling(), RR_FLOOR)
        max_target = max(out.stop_pct * ceiling_mult, _fee_floor_target(fee_rate))
        if out.target_pct > max_target:
            notes.append(f"target_pct {out.target_pct:g} pulled to R:R ceiling "
                         f"{max_target:g} ({ceiling_mult:g}x stop "
                         f"{out.stop_pct:g}) — unreachable targets never fill")
            out.target_pct = max_target

    # The lock must not arm before the position is worth protecting, and never
    # inside the stop — that was the 10:1 defect in miniature.
    if out.trail_arm_pct is not None and out.stop_pct is not None \
            and out.trail_arm_pct < out.stop_pct:
        notes.append(f"trail_arm_pct {out.trail_arm_pct:g} raised to stop "
                     f"{out.stop_pct:g} (must not arm inside the stop)")
        out.trail_arm_pct = out.stop_pct

    out.notes = notes
    # Nothing usable parsed — treat exactly like an absent block.
    if not any(getattr(out, f) is not None for f in
               ("size_frac", "leverage", "stop_pct", "target_pct",
                "trail_arm_pct", "trail_give", "horizon_hours", "max_adds")):
        return None
    return out


def _fee_floor_target(fee_rate: Optional[float] = None) -> float:
    """The smallest target worth naming: FEE_MULTIPLE round trips."""
    rate = fee_rate if fee_rate is not None else _fee_rate()
    return rate * 2 * 100.0 * FEE_MULTIPLE


def _rr_ceiling() -> float:
    """How many multiples of the stop the target may sit at, at most.

    Env-tunable so the band can be relaxed without a deploy — the evidence
    behind the default is a 30-entry replay, not a law."""
    try:
        return float(os.environ.get("RR_CEILING", str(RR_CEILING_DEFAULT)))
    except (TypeError, ValueError):
        return RR_CEILING_DEFAULT


def _fee_rate() -> float:
    try:
        from fees import TRADE_FEE_RATE
        return float(TRADE_FEE_RATE)
    except Exception:  # noqa: BLE001
        return 0.001


def exit_prices(params: OrderParams, entry: float,
                is_short: bool) -> tuple[Optional[float], Optional[float]]:
    """(stop_loss, take_profit) absolute prices from the railed percentages.

    Derived here rather than taken from the model so an absolute price can
    never enter the system — the percentages are railed, the arithmetic is
    ours."""
    if entry is None or entry <= 0:
        return None, None
    sl = tp = None
    if params.stop_pct is not None:
        sl = entry * (1 + params.stop_pct / 100.0) if is_short \
            else entry * (1 - params.stop_pct / 100.0)
    if params.target_pct is not None:
        tp = entry * (1 - params.target_pct / 100.0) if is_short \
            else entry * (1 + params.target_pct / 100.0)
    return sl, tp


def rr_floor_violation(stop_loss: Optional[float], take_profit: Optional[float],
                       entry: float, is_short: bool) -> Optional[str]:
    """R:R floor applied to the DETERMINISTIC path too.

    The rail is worth more than the AI feature it was built for: the flat
    5%/10% defaults happen to satisfy it, but a per-agent risk_limits row can
    be edited into a 1:1 or worse geometry through the API, and the fleet's
    own tier maths produced 10:1 for a month. Returns a description when the
    reward does not clear RR_FLOOR x risk, or None."""
    if not (stop_loss and take_profit and entry and entry > 0):
        return None
    risk = (stop_loss - entry) if is_short else (entry - stop_loss)
    reward = (entry - take_profit) if is_short else (take_profit - entry)
    if risk <= 0 or reward <= 0:
        return None      # not a two-sided bracket; nothing to grade
    # Relative epsilon: the house 5%/10% default sits EXACTLY on the floor,
    # so a strict compare lets one ulp of rounding in exit_prices decide the
    # verdict per entry price (prod 2026-07-31: entry 1.0816 refused, others
    # passed, identical config).
    if reward < risk * RR_FLOOR * (1 - 1e-9):
        return (f"r:r floor: reward {reward:.4f} < {RR_FLOOR:g}x risk "
                f"{risk:.4f} (entry {entry:.4f})")
    return None
