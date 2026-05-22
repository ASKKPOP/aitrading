"""Pure portfolio performance metrics.

All functions operate on plain Python lists — no external dependencies.

Public functions:
    max_drawdown(curve)                          -> float
    sharpe_ratio(returns, periods_per_year)      -> float | None
    sortino_ratio(returns, periods_per_year)     -> float | None
    calmar_ratio(total_return_pct, max_dd_pct)   -> float | None
    hit_rate(pnls)                               -> float
    avg_win(pnls)                                -> float | None
    avg_loss(pnls)                               -> float | None
    profit_factor(pnls)                          -> float | None
"""

from __future__ import annotations

import math
from typing import Optional


def max_drawdown(curve: list[float]) -> float:
    """Return maximum peak-to-trough drawdown as a percentage (0–100).

    Args:
        curve: Portfolio values in chronological order.
    """
    if len(curve) < 2:
        return 0.0
    peak = curve[0]
    worst = 0.0
    for v in curve:
        if v > peak:
            peak = v
        if peak > 0:
            dd = (peak - v) / peak * 100.0
            if dd > worst:
                worst = dd
    return worst


def sharpe_ratio(
    returns: list[float],
    periods_per_year: int = 252,
) -> Optional[float]:
    """Annualised Sharpe ratio (risk-free rate = 0).

    Args:
        returns:         Per-period returns (e.g. daily return fractions).
        periods_per_year: Trading periods per year for annualisation (252 for daily).

    Returns:
        Rounded Sharpe ratio, or None when fewer than 2 observations or std = 0.
    """
    n = len(returns)
    if n < 2:
        return None
    mean = sum(returns) / n
    variance = sum((r - mean) ** 2 for r in returns) / (n - 1)
    std = math.sqrt(variance)
    if std == 0:
        return None
    return round(mean / std * math.sqrt(periods_per_year), 3)


def sortino_ratio(
    returns: list[float],
    periods_per_year: int = 252,
) -> Optional[float]:
    """Annualised Sortino ratio (risk-free rate = 0, downside deviation only).

    Args:
        returns:         Per-period returns.
        periods_per_year: Trading periods per year for annualisation.

    Returns:
        Rounded Sortino ratio, or None when fewer than 2 observations or no
        negative returns exist (downside deviation = 0).
    """
    n = len(returns)
    if n < 2:
        return None
    mean = sum(returns) / n
    negative = [r for r in returns if r < 0]
    if not negative:
        return None
    downside_variance = sum(r ** 2 for r in negative) / n
    downside_std = math.sqrt(downside_variance)
    if downside_std == 0:
        return None
    return round(mean / downside_std * math.sqrt(periods_per_year), 3)


def calmar_ratio(
    total_return_pct: float,
    max_drawdown_pct: float,
) -> Optional[float]:
    """Return / max-drawdown ratio.

    Args:
        total_return_pct: Total return as a percentage (e.g. 20.0 for 20%).
        max_drawdown_pct: Maximum drawdown as a percentage (positive value).

    Returns:
        Rounded Calmar ratio, or None when max_drawdown_pct is zero.
    """
    if max_drawdown_pct == 0:
        return None
    return round(total_return_pct / max_drawdown_pct, 3)


def hit_rate(pnls: list[float]) -> float:
    """Fraction of trades with positive P&L.

    Args:
        pnls: Per-trade profit/loss values.

    Returns:
        Value in [0, 1]. Returns 0.0 for empty input.
    """
    if not pnls:
        return 0.0
    wins = sum(1 for p in pnls if p > 0)
    return wins / len(pnls)


def avg_win(pnls: list[float]) -> Optional[float]:
    """Average P&L of winning trades (P&L > 0).

    Returns None when there are no winning trades.
    """
    wins = [p for p in pnls if p > 0]
    if not wins:
        return None
    return sum(wins) / len(wins)


def avg_loss(pnls: list[float]) -> Optional[float]:
    """Average P&L of losing trades (P&L <= 0).

    Returns None when there are no losing trades.
    """
    losses = [p for p in pnls if p <= 0]
    if not losses:
        return None
    return sum(losses) / len(losses)


def profit_factor(pnls: list[float]) -> Optional[float]:
    """Gross profit divided by gross loss (absolute value).

    Returns:
        Profit factor >= 0, or None when there are no trades or no losses.
        Returns 0.0 when there are losses but no wins.
    """
    if not pnls:
        return None
    gross_profit = sum(p for p in pnls if p > 0)
    gross_loss = sum(abs(p) for p in pnls if p <= 0)
    if gross_loss == 0:
        return None
    return gross_profit / gross_loss
