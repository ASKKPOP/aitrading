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

# run_id -> {"position_id", "trigger", "price", "ts"}
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


def note_hit(run_id: int, position_id: int, trigger: str,
             price: float) -> bool:
    """Record a stop/target hit for the desk. Returns True when the hit is
    newly routed (the watcher must NOT close), False when the fail-safe
    window has expired for an already-noted hit (the watcher closes) or
    re-noting is suppressed after a fresh desk verdict (no close either —
    the desk just ruled)."""
    now = time.monotonic()
    pending = _PENDING.get(run_id)
    if pending is not None:
        if now - pending["ts"] >= timeout_s():
            _PENDING.pop(run_id, None)
            return False               # fail-safe: programming closes
        return True                    # meeting already convened — wait
    if now < _SUPPRESS_UNTIL.get(run_id, 0.0):
        return True                    # desk just ruled; do not re-litigate
    _PENDING[run_id] = {"position_id": position_id, "trigger": trigger,
                        "price": price, "ts": now}
    return True


def pending(run_id: int) -> "dict | None":
    return _PENDING.get(run_id)


def clear(run_id: int) -> None:
    """A desk decision cycle ran for this run — its verdict governs.
    Suppress re-noting for one think-window so a justified hold sticks."""
    if _PENDING.pop(run_id, None) is not None:
        _SUPPRESS_UNTIL[run_id] = time.monotonic() + renote_min() * 60.0


def _reset() -> None:
    """Test hook."""
    _PENDING.clear()
    _SUPPRESS_UNTIL.clear()
