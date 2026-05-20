"""Tests for the risk-normalized leaderboard Sharpe computation."""

import math
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from routes_trading import _annualized_sharpe  # noqa: E402


def test_empty_history_returns_zero():
    assert _annualized_sharpe([]) == 0.0


def test_short_history_returns_zero():
    # Fewer than 3 points → not enough for a meaningful stddev
    assert _annualized_sharpe([{"profit": 0, "recorded_at": "2026-05-01T00:00:00Z"}]) == 0.0
    assert _annualized_sharpe([
        {"profit": 0, "recorded_at": "2026-05-01T00:00:00Z"},
        {"profit": 100, "recorded_at": "2026-05-01T00:05:00Z"},
    ]) == 0.0


def test_zero_variance_returns_zero():
    # Constant cumulative profit → all deltas are zero → stddev=0 → Sharpe=0
    history = [
        {"profit": 50, "recorded_at": "2026-05-01T00:00:00Z"},
        {"profit": 50, "recorded_at": "2026-05-01T00:05:00Z"},
        {"profit": 50, "recorded_at": "2026-05-01T00:10:00Z"},
        {"profit": 50, "recorded_at": "2026-05-01T00:15:00Z"},
    ]
    assert _annualized_sharpe(history) == 0.0


def test_positive_returns_yield_positive_sharpe():
    # Monotonically increasing profit with small jitter → positive Sharpe.
    history = [{"profit": i * 100 + (i % 2) * 5, "recorded_at": f"2026-05-01T00:{i:02d}:00Z"} for i in range(20)]
    sharpe = _annualized_sharpe(history)
    assert sharpe > 0
    assert sharpe <= 10.0  # clamped


def test_negative_returns_yield_negative_sharpe():
    history = [{"profit": -(i * 100) + (i % 2) * 5, "recorded_at": f"2026-05-01T00:{i:02d}:00Z"} for i in range(20)]
    sharpe = _annualized_sharpe(history)
    assert sharpe < 0
    assert sharpe >= -10.0  # clamped


def test_sharpe_is_finite():
    # Defensive: never NaN or Inf for any realistic input.
    history = [{"profit": float(i) * 0.001, "recorded_at": f"2026-05-01T00:{i:02d}:00Z"} for i in range(50)]
    sharpe = _annualized_sharpe(history)
    assert math.isfinite(sharpe)
