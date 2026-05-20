"""
Application-level Prometheus metrics.

Import the counters/gauges from this module to avoid initialising them in
multiple places (prometheus_client raises on duplicate registration).

All metrics degrade gracefully to no-ops when prometheus_client is absent.
"""

from __future__ import annotations


class _Noop:
    """Stub that accepts any attribute access and any call."""

    def __getattr__(self, _name: str) -> "_Noop":
        return self

    def __call__(self, *_args, **_kwargs) -> "_Noop":
        return self

    def inc(self, _amount: float = 1) -> None:  # Counter
        pass

    def set(self, _value: float) -> None:  # Gauge
        pass

    def observe(self, _value: float) -> None:  # Histogram / Summary
        pass


try:
    from prometheus_client import Counter, Gauge

    signal_publish_total = Counter(
        "signal_publish_total",
        "Total signals published, partitioned by market and action.",
        ["market", "action"],
    )

    price_fetch_errors_total = Counter(
        "price_fetch_errors_total",
        "Total price-fetch failures, partitioned by provider.",
        ["provider"],
    )

    active_ws_connections = Gauge(
        "active_ws_connections",
        "Number of currently open WebSocket connections.",
    )

except Exception:  # prometheus_client not installed
    signal_publish_total = _Noop()  # type: ignore[assignment]
    price_fetch_errors_total = _Noop()  # type: ignore[assignment]
    active_ws_connections = _Noop()  # type: ignore[assignment]
