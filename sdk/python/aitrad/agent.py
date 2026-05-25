"""agent.py — minimal helpers for writing an AITRAD agent loop.

run_strategy() is the simplest useful loop: poll the signal feed every
N seconds, deduplicate, and invoke a handler for each new signal. Built
for clarity not throughput — when push-based market data ships (Phase 4.5)
this will be replaced with a WebSocket subscriber.
"""
from __future__ import annotations

import time
from typing import Callable, Iterable

from aitrad.client import AITRADClient


def run_strategy(
    handler: Callable[[dict], None],
    *,
    client: AITRADClient,
    interval: float = 5.0,
    message_type: str | None = "operation",
    market: str | None = None,
    initial_limit: int = 50,
    max_iterations: int | None = None,
) -> None:
    """Poll the signal feed and dispatch new signals to ``handler``.

    Args:
        handler:        called once per new signal with the raw signal dict.
                        Exceptions inside ``handler`` are logged-and-skipped
                        so a buggy strategy doesn't kill the loop.
        client:         authenticated AITRADClient.
        interval:       seconds between polls.
        message_type:   "operation" (default), "strategy", "discussion", or None.
        market:         optional market filter (e.g. "us-stock", "crypto").
        initial_limit:  size of the first fetch (subsequent polls always 20).
        max_iterations: stop after N poll cycles (None = forever). Mostly for tests.
    """
    seen: set[int] = set()
    # Pre-seed `seen` with the current head so the first poll doesn't fire
    # the handler against everything that already existed.
    bootstrap = client.list_signals(
        limit=initial_limit,
        message_type=message_type,
        market=market,
    )
    for sig in _signals_from(bootstrap):
        sid = sig.get("signal_id") or sig.get("id")
        if sid is not None:
            seen.add(sid)

    iters = 0
    while max_iterations is None or iters < max_iterations:
        iters += 1
        try:
            page = client.list_signals(
                limit=20, message_type=message_type, market=market,
            )
        except Exception:  # noqa: BLE001 — keep loop alive across transient errors
            time.sleep(interval)
            continue

        for sig in _signals_from(page):
            sid = sig.get("signal_id") or sig.get("id")
            if sid is None or sid in seen:
                continue
            seen.add(sid)
            try:
                handler(sig)
            except Exception:  # noqa: BLE001 — buggy handler shouldn't kill the loop
                pass

        time.sleep(interval)


def _signals_from(payload: dict | list) -> Iterable[dict]:
    """The /api/signals/feed endpoint has occasionally shipped two shapes;
    this normalizer absorbs both so the loop doesn't care."""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("signals", "items", "results", "data"):
            v = payload.get(key)
            if isinstance(v, list):
                return v
    return []
