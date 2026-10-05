"""Stop-hit routing — the sooppiy AI is the MAIN author of stop exits;
the watcher's close is the OPTIONAL fail-safe (owner rule 2026-08-13:
"Must be final discussion for contract or order by sooppiy AI — NOT any
programming logic. ... by AI it is main; programming decision is
optional.")

Before this module, a hit on a position's stop_loss/take_profit was
executed by the SL/TP watcher as an immediate FULL close (risk_engine
sl_tp_watch). Both of the day block's largest losses on 2026-08-13 were
exactly that shape (SLV −1.82, UBER −3.53). The level itself was authored
by the desk — but the *decision at the moment the level traded* was
code's, and the desk never got to choose close vs reduce vs re-author.

Now, for LIVE FLEET runs only (manual users' SL/TP semantics are a
promise and stay untouched):

1. The watcher NOTES the hit here instead of closing, and the run is
   dispatched for an IMMEDIATE full-tier decision (the emergency
   discussion) with a STOP HIT brief line.
2. The desk's verdict — close, reduce, or hold with a re-authored
   bracket — executes through the normal decision path.
3. Programming stays as the fail-safe only: if no decision lands within
   STOP_DESK_TIMEOUT_S (default 180) the watcher closes exactly as
   before. After a desk verdict, re-noting is suppressed for
   STOP_RENOTE_MIN (default 30) so a justified hold is not re-litigated
   every scan tick; if the desk does not widen its bracket, the next
   window re-convenes the meeting.

Process-local by design: watcher and dispatcher share the worker
process. A restart loses the notes — and the watcher simply re-notes on
its next 30s tick while the fail-safe clock restarts, which is the safe
direction.
"""

from __future__ import annotations

import os
import time

# Indirection for tests — patch stop_router._now, never stdlib time.
_now = time.monotonic

# run_id -> {"position_id", "trigger", "price", "ts", "deciding_since"?}
_PENDING: dict[int, dict] = {}
# run_id -> suppress re-noting until this monotonic time
_SUPPRESS_UNTIL: dict[int, float] = {}


def timeout_s() -> float:
    try:
        return float(os.environ.get("STOP_DESK_TIMEOUT_S", "180"))
    except ValueError:
        return 180.0


def renote_min() -> float:
    try:
        return float(os.environ.get("STOP_RENOTE_MIN", "30"))
    except ValueError:
        return 30.0


def enabled() -> bool:
    return (os.environ.get("STOP_DESK_ROUTING", "1").strip().lower()
            not in ("0", "false", "no"))


# The watcher scans every ~30s and calls note_hit each time the level is
# still traded through; a note unseen for this long means the price left.
_REBREACH_GAP_S = 300.0


def _deadline(note: dict) -> float:
    """When the desk's window on a noted hit ends and programming closes.

    A desk actually DECIDING is not "silent": once run_cycle stamps
    begin_ruling, the hit gets one full timeout window measured from
    deliberation start (SOL 1274's fail-safe fired at 183s vs the 180s
    window; dispatch alone can eat 30s and the emergency runs the expensive
    full tier — dumping the book mid-deliberation both wastes the LLM call
    and steals the ruling). HARD-BOUNDED: a hung cycle still meets the
    fail-safe at deciding_since + timeout, so the worst case is
    dispatch-window + one deliberation window."""
    deadline = note["ts"] + timeout_s()
    deciding = note.get("deciding_since")
    if deciding is not None:
        deadline = max(deadline, deciding + timeout_s())
    return deadline


def note_hit(run_id: int, position_id: int, trigger: str,
             price: float) -> bool:
    """Record a stop/target hit for the desk. Returns True when the hit is
    newly routed (the watcher must NOT close), False when the fail-safe
    window has expired for an already-noted hit (the watcher closes) or
    re-noting is suppressed after a fresh desk verdict (no close either —
    the desk just ruled)."""
    now = _now()
    pending = _PENDING.get(run_id)
    if pending is not None:
        seen = pending.get("seen", pending["ts"])
        if now < _deadline(pending):
            pending["seen"] = now
            return True                # meeting already convened — wait
        _PENDING.pop(run_id, None)
        if now - seen < _REBREACH_GAP_S:
            return False               # fail-safe: programming closes
        # The note expired with nobody ruling AND the watcher stopped
        # seeing the level traded (it calls here every scan while price is
        # through it): the price left. This breach is a new hit with its
        # own window — not an instant close on a clock that ran out while
        # the position was fine.
    if now < _SUPPRESS_UNTIL.get(run_id, 0.0):
        return True                    # desk just ruled; do not re-litigate
    _PENDING[run_id] = {"position_id": position_id, "trigger": trigger,
                        "price": price, "ts": now}
    return True


def begin_ruling(run_id: int) -> None:
    """The desk's emergency cycle has STARTED for this run's pending hit.

    Stamped once (the first cycle to reach it wins); a no-op when nothing
    is pending. See note_hit for why this extends the fail-safe window."""
    pending = _PENDING.get(run_id)
    if pending is not None and "deciding_since" not in pending:
        pending["deciding_since"] = _now()


def pending(run_id: int) -> "dict | None":
    """The hit the desk is still inside its window to rule on.

    None once the fail-safe deadline has passed, even though the note stays
    for the watcher to close on. A cycle that ends without a verdict (rule
    fallback, scaffold) deliberately leaves the note uncleared, and callers
    read this to dispatch the run NOW, lift its loss cooldown and write the
    STOP HIT line — unbounded, that was a run cycled on the full tier for
    as long as the process lived after one touch-and-bounce."""
    note = _PENDING.get(run_id)
    if note is None or _now() >= _deadline(note):
        return None
    return note


def clear(run_id: int) -> None:
    """A desk decision cycle ran for this run — its verdict governs.
    Suppress re-noting for one think-window so a justified hold sticks."""
    if _PENDING.pop(run_id, None) is not None:
        _SUPPRESS_UNTIL[run_id] = _now() + renote_min() * 60.0


def _reset() -> None:
    """Test hook."""
    _PENDING.clear()
    _SUPPRESS_UNTIL.clear()
