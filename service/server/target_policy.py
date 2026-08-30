"""Reachable-target cap, keyed on the psych regime (owner order 2026-08-29).

The 1,099-trip demoted-proposal replay (research/target_sweep_20260829) found
the desk's 4.4-4.5%-class targets reached on 0.5% of trips (stop:target
27.8:1) while a flat 0.30% target is the mean- AND median-maximising level
(target-hit 61.9%, stop:target 1:4.9, median +17.98bp, 71% winners). No
psych-regime split survived measurement — fear (n=622) and greed (n=455)
both pick 0.30% with overlapping CIs, and the F&G extremes never occurred in
the window — so the MAP is regime-keyed (the owner's ask) but ships with
flat values: the machinery is conditional, the evidence is not, yet.

Default OFF (`TARGET_PSYCH_CAP` unset) — zero behavior change. When on, the
cap only ever pulls a take-profit INWARD and never blocks a trade: the
caller floors the effective cap at RR_FLOOR x the actual stop distance and
at the fee floor, so `rr_floor_violation` can never be raised by this rail.
Any read failure falls to the map's `base` level; a missing base means no
cap. Stated plainly per the replay: no target level makes the mean positive
— 0.30% closes 31.5% of the gap; the residual is authored by the stop's
reward:risk, which is out of this rail's scope.
"""
import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

_MAP_RAW: Optional[str] = None
_MAP_CACHE: dict = {}


def enabled() -> bool:
    return (os.environ.get("TARGET_PSYCH_CAP") or "").strip().lower() \
        in ("1", "true", "yes")


def _cap_map() -> dict:
    """Parse TARGET_PSYCH_CAP_MAP once per distinct env value (memoized).

    Shape: {"crypto": {"base": 0.3, "panic": 0.3, "euphoria": 0.3}, ...} —
    market -> regime -> target_pct. Markets absent from the map get no cap.
    Bad JSON fails soft to an empty map (logged once per value)."""
    global _MAP_RAW, _MAP_CACHE
    raw = os.environ.get("TARGET_PSYCH_CAP_MAP", "")
    if raw == _MAP_RAW:
        return _MAP_CACHE
    parsed: dict = {}
    if raw:
        try:
            candidate = json.loads(raw)
            if isinstance(candidate, dict):
                parsed = candidate
            else:
                logger.warning("TARGET_PSYCH_CAP_MAP is not a JSON object; "
                               "cap disabled")
        except ValueError:
            logger.warning("TARGET_PSYCH_CAP_MAP is not valid JSON; "
                           "cap disabled")
    _MAP_RAW, _MAP_CACHE = raw, parsed
    return parsed


def _current_regime() -> str:
    """The platform's own psychology classifier (regime_snapshots latest row:
    panic/caution/event/trend/euphoria/...). Transition-recorded, so the
    latest row IS the current regime — no staleness window to manage.
    Any failure reads as 'unknown', which falls to the map's base level."""
    try:
        from regime import current_regime_state
        state = current_regime_state()
        if isinstance(state, dict) and state.get("regime"):
            return str(state["regime"])
    except Exception:  # noqa: BLE001 — a cap read must never block a cycle
        logger.debug("regime read failed; using base target cap", exc_info=True)
    return "unknown"


def cap_for(market: Optional[str]) -> tuple[Optional[float], str]:
    """(cap_pct, regime) for this market, or (None, '') when uncapped."""
    if not enabled():
        return None, ""
    market_map = _cap_map().get(str(market or ""))
    if not isinstance(market_map, dict):
        return None, ""
    regime = _current_regime()
    value = market_map.get(regime, market_map.get("base"))
    try:
        cap = float(value) if value is not None else None
    except (TypeError, ValueError):
        cap = None
    if cap is not None and cap <= 0:
        cap = None
    return cap, regime


def prompt_line(market: Optional[str]) -> str:
    """The teaching channel: run_cycle clamps bypass order_params notes, so
    without this line the desk re-authors the same far target forever (the
    run-1375 lesson). Renders '' whenever the cap does.

    Plan 31: the line states the FULL house geometry as fact. Post-08-29
    tape showed the desk retiring slots because a 0.30% target against a
    1.5-3.7% stop offends its internalised target>=stop norm (8/8 sampled
    retires cited an "unconstructible bracket") — so when the stop cap is
    active the line says both numbers and that the geometry is deliberate.
    Facts only; no imperative about holding (that would manufacture
    entries via prompt, which the owner prohibits)."""
    cap, regime = cap_for(market)
    stop_cap = ""
    if (market or "") == "crypto":
        stop_cap = os.environ.get("STOP_CAP_PCT_CRYPTO", "").strip()
    if cap is None:
        # Stop cap active with the target cap off (verification Q4-7): the
        # stops are still cut at order time, so the teaching line must still
        # say so or the desk re-authors wide stops forever (run-1375 shape).
        if stop_cap:
            try:
                return (f"House bracket right now: stop_pct is capped at "
                        f"{float(stop_cap):g}% — a wider stop is cut to it "
                        f"at order time.\n")
            except ValueError:
                pass
        return ""
    if stop_cap:
        try:
            return (f"House bracket right now ({regime} regime): stop_pct is "
                    f"capped at {float(stop_cap):g}% and target_pct at "
                    f"{cap:g}% — wider values are cut to these at order "
                    f"time. Target below stop is the house design: the "
                    f"breakeven ratchet and trailing lock carry a winner "
                    f"past the target; the tight stop bounds the loser.\n")
        except ValueError:
            pass
    return (f"House target band right now ({regime} regime): write "
            f"target_pct at or below {cap:g}% — a wider target is cut to "
            f"it at order time.\n")
