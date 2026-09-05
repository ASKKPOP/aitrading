"""Wake the desk when price reaches the entry level the desk itself named.

WHY THIS EXISTS (owner, 2026-09-04: "All order hold, it's not solution,
it's not trading software").

Four rails were removed on 2026-09-04 — loss budget, switch window,
plan-awareness, panel blindness — every one a real, measured defect, and
the trade count stayed at zero. Reading what the desk actually says after
all four were fixed gave the answer, and it was never a rail:

    LIT : "Hold until price retraces into the 4.678-4.761 zone;
           current price is above entry range."
    ENA : "the entry itself is the disqualifier - price sits ABOVE my
           target, the easy leg is already spent."

That LIT sentence is a limit order. The desk writes one nearly every hour
(82% of outlooks carry a concrete zone) and the platform has nowhere to
put it. Meanwhile selection ranks candidates by how much they ALREADY
moved (|mom_2d| x volume), then asks for an entry at market at an
arbitrary hourly instant. Momentum selection plus market-only entry at
sampling instants is a permanent deadlock for a desk with pullback
discipline: by the time it looks, the level it wanted is behind it.

Measured: of 49 authored zones, 0 were reached inside a slot's life,
while ~9 of 19 sat inside the day's realized range. The levels are real.
The platform simply was not looking when price got there.

WHAT THIS DOES NOT DO. It does NOT place an order. The desk's outlook is
a forward PLAN, not an authored order, and executing it directly would be
programming logic placing trades — which owner rule 2026-08-13 forbids in
as many words ("Must be final discussion for contract or order by sooppiy
AI - NOT any programming logic"). Instead the zone becomes a WAKE
condition: when price enters it, the run becomes due immediately, the desk
runs a normal cycle with fresh data, and it authors (or declines) its own
order through every existing gate. Event-driven decision, not automated
execution.

Deliberately mirrors stop_router: same in-process pending map, same
suppress window so a considered hold sticks instead of re-firing every
60 seconds, same fail-open posture.
"""

from __future__ import annotations

import os
import time

# run_id -> {"symbol","low","high","mark","noted_at"}
_PENDING: dict[int, dict] = {}
# run_id -> unix seconds until which a fresh note is suppressed
_SUPPRESS_UNTIL: dict[int, float] = {}
# run_id -> monotonic stamp of the last live price probe
_LAST_POLL: dict[int, float] = {}


def _now() -> float:
    return time.monotonic()


def enabled() -> bool:
    """Kill switch. Default ON: with it off the desk is back to deciding
    only at fixed intervals, which is the state that produced zero trades."""
    return (os.getenv("ENTRY_ZONE_WAKE", "true") or "true").strip().lower() in (
        "1", "true", "yes", "on")


def renote_min() -> float:
    """Minutes a considered decision suppresses re-waking on the same zone.

    Without it a run sitting inside its zone would be re-woken every
    control pass (~60s), which is a spend loop, not a signal. The desk
    said its piece; give that verdict a think-window before asking again."""
    try:
        return max(1.0, float(os.getenv("ENTRY_ZONE_RENOTE_MIN", "30") or 30))
    except ValueError:
        return 30.0


def poll_seconds() -> float:
    """Minimum seconds between live price probes for one run.

    The probe runs inside the ~60s control pass, which is a SERIAL loop and
    also the loop that evaluates stops. `price_fetcher` has no price cache
    (its caches hold symbol lists and token metadata), so an unthrottled
    watch is one live HTTP call per flat run per pass — ~480-780/hour at
    fleet scale — each carrying a 10s timeout and retry backoff. Two ways
    that hurts beyond cost: a slow feed on an early run delays STOP
    evaluation for every run behind it in the same pass, and a 429 trips
    the provider-wide cooldown that starves the marks the stop system
    reads. An entry convenience must not sit on the exit path.

    Default 300s is deliberately the platform's existing mark-refresh
    cadence, so an entry watch costs no more feed than an open position
    already costs. The price is granularity: a touch shorter than five
    minutes can be missed. Against a status quo of sampling once an HOUR
    that is still ~12x finer, and paying a systemic feed risk to chase
    sub-five-minute wicks is a bad trade."""
    try:
        return max(0.0, float(os.getenv("ENTRY_ZONE_POLL_SEC", "300") or 300))
    except ValueError:
        return 300.0


def should_poll(run_id: int) -> bool:
    """True when this run is due a live probe; stamps the clock when it is."""
    last = _LAST_POLL.get(run_id)
    now = _now()
    if last is not None and now - last < poll_seconds():
        return False
    _LAST_POLL[run_id] = now
    return True


def note_zone_hit(run_id: int, symbol: str, low: float, high: float,
                  mark: float) -> bool:
    """Record that price entered the desk's authored entry zone. Returns
    True when the note is new (suppressed or already-pending notes are a
    no-op, so the caller can log honestly)."""
    if not enabled():
        return False
    if _PENDING.get(run_id) is not None:
        return False
    until = _SUPPRESS_UNTIL.get(run_id)
    if until is not None and _now() < until:
        return False
    _PENDING[run_id] = {"symbol": symbol, "low": low, "high": high,
                        "mark": mark, "noted_at": _now()}
    return True


def pending(run_id: int) -> "dict | None":
    return _PENDING.get(run_id)


def clear(run_id: int) -> None:
    """A desk cycle ran for this run — its verdict governs. Suppress
    re-noting for one think-window so a justified hold sticks."""
    if _PENDING.pop(run_id, None) is not None:
        _SUPPRESS_UNTIL[run_id] = _now() + renote_min() * 60.0


def in_zone(mark: float, low: float, high: float) -> bool:
    """Inclusive containment, tolerant of a zone written high-first."""
    try:
        lo, hi = float(low), float(high)
        if lo > hi:
            lo, hi = hi, lo
        return lo <= float(mark) <= hi
    except (TypeError, ValueError):
        return False


def _reset() -> None:
    """Test hook."""
    _PENDING.clear()
    _SUPPRESS_UNTIL.clear()
    _LAST_POLL.clear()
