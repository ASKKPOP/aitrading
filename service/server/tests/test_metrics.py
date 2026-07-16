"""Tests for metrics.py — pure portfolio metric functions.

All values are computed from known inputs so results are deterministic.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from backtest_metrics import (
    avg_loss,
    avg_win,
    calmar_ratio,
    hit_rate,
    max_drawdown,
    profit_factor,
    sharpe_ratio,
    sortino_ratio,
)


class TestMaxDrawdown(unittest.TestCase):
    def test_monotone_decline(self):
        # peak=100, trough=80 → 20%
        result = max_drawdown([100.0, 90.0, 80.0])
        self.assertAlmostEqual(result, 20.0, places=4)

    def test_recovery_after_drawdown(self):
        # peak=110, then drops to 90 → (110-90)/110 * 100 = 18.18%
        result = max_drawdown([100.0, 110.0, 90.0, 105.0])
        self.assertAlmostEqual(result, 100.0 * 20.0 / 110.0, places=3)

    def test_always_increasing_returns_zero(self):
        result = max_drawdown([100.0, 110.0, 120.0, 130.0])
        self.assertAlmostEqual(result, 0.0, places=6)

    def test_single_point_returns_zero(self):
        self.assertEqual(max_drawdown([100.0]), 0.0)

    def test_empty_returns_zero(self):
        self.assertEqual(max_drawdown([]), 0.0)

    def test_multiple_drawdowns_picks_worst(self):
        # First dip: 100→80 = 20%; second dip: 120→50 = 58.3%
        result = max_drawdown([100.0, 80.0, 120.0, 50.0])
        self.assertAlmostEqual(result, 100.0 * 70.0 / 120.0, places=3)

    def test_returns_percentage_not_fraction(self):
        result = max_drawdown([100.0, 50.0])
        self.assertAlmostEqual(result, 50.0, places=6)


class TestSharpeRatio(unittest.TestCase):
    def test_zero_std_returns_none(self):
        # All identical returns → std = 0 → undefined
        self.assertIsNone(sharpe_ratio([0.01, 0.01, 0.01]))

    def test_fewer_than_two_points_returns_none(self):
        self.assertIsNone(sharpe_ratio([]))
        self.assertIsNone(sharpe_ratio([0.05]))

    def test_positive_returns_give_positive_sharpe(self):
        returns = [0.01, 0.02, 0.015, 0.012, 0.018]
        result = sharpe_ratio(returns)
        self.assertIsNotNone(result)
        self.assertGreater(result, 0.0)

    def test_negative_returns_give_negative_sharpe(self):
        returns = [-0.01, -0.02, -0.015]
        result = sharpe_ratio(returns)
        self.assertIsNotNone(result)
        self.assertLess(result, 0.0)

    def test_annualised_with_daily_periods(self):
        # mean=0.001, std=0.001 → raw = 1.0 → annualised = sqrt(252) ≈ 15.87
        returns = [0.001] * 50 + [0.002] * 50
        result = sharpe_ratio(returns, periods_per_year=252)
        self.assertIsNotNone(result)
        self.assertGreater(result, 0.0)

    def test_result_is_rounded_to_three_decimals(self):
        returns = [0.01, 0.02, 0.015, 0.012]
        result = sharpe_ratio(returns)
        if result is not None:
            self.assertEqual(result, round(result, 3))


class TestSortinoRatio(unittest.TestCase):
    def test_all_positive_returns_none(self):
        # No downside deviation → undefined
        self.assertIsNone(sortino_ratio([0.01, 0.02, 0.03]))

    def test_fewer_than_two_points_returns_none(self):
        self.assertIsNone(sortino_ratio([]))
        self.assertIsNone(sortino_ratio([0.01]))

    def test_mixed_returns_give_positive_sortino_when_mean_positive(self):
        returns = [0.02, -0.005, 0.03, -0.003, 0.015]
        result = sortino_ratio(returns)
        self.assertIsNotNone(result)
        self.assertGreater(result, 0.0)

    def test_sortino_higher_than_sharpe_when_upside_skew(self):
        # When gains > losses, Sortino > Sharpe (downside vol < total vol)
        returns = [0.05, 0.04, -0.001, 0.06, -0.002, 0.05]
        s = sharpe_ratio(returns)
        so = sortino_ratio(returns)
        if s is not None and so is not None:
            self.assertGreater(so, s)

    def test_all_negative_returns_give_negative_sortino(self):
        returns = [-0.01, -0.02, -0.015]
        result = sortino_ratio(returns)
        self.assertIsNotNone(result)
        self.assertLess(result, 0.0)


class TestCalmarRatio(unittest.TestCase):
    def test_basic_division(self):
        result = calmar_ratio(20.0, 10.0)
        self.assertAlmostEqual(result, 2.0, places=6)

    def test_zero_drawdown_returns_none(self):
        self.assertIsNone(calmar_ratio(20.0, 0.0))

    def test_negative_return_gives_negative_calmar(self):
        result = calmar_ratio(-10.0, 20.0)
        self.assertIsNotNone(result)
        self.assertLess(result, 0.0)

    def test_result_rounded_to_three_decimals(self):
        result = calmar_ratio(10.0, 3.0)
        if result is not None:
            self.assertEqual(result, round(result, 3))


class TestHitRate(unittest.TestCase):
    def test_all_wins(self):
        self.assertAlmostEqual(hit_rate([1.0, 2.0, 3.0]), 1.0, places=6)

    def test_all_losses(self):
        self.assertAlmostEqual(hit_rate([-1.0, -2.0]), 0.0, places=6)

    def test_mixed(self):
        # 3 wins, 1 loss → 0.75
        self.assertAlmostEqual(hit_rate([10.0, -5.0, 20.0, 5.0]), 0.75, places=6)

    def test_empty_returns_zero(self):
        self.assertEqual(hit_rate([]), 0.0)

    def test_zero_pnl_counts_as_loss(self):
        # PnL of 0 is not a win
        self.assertAlmostEqual(hit_rate([0.0, 1.0]), 0.5, places=6)


class TestAvgWin(unittest.TestCase):
    def test_basic(self):
        result = avg_win([10.0, -5.0, 20.0, -3.0])
        self.assertAlmostEqual(result, 15.0, places=6)

    def test_no_wins_returns_none(self):
        self.assertIsNone(avg_win([-1.0, -2.0]))

    def test_empty_returns_none(self):
        self.assertIsNone(avg_win([]))

    def test_all_wins(self):
        result = avg_win([5.0, 10.0, 15.0])
        self.assertAlmostEqual(result, 10.0, places=6)


class TestAvgLoss(unittest.TestCase):
    def test_basic(self):
        result = avg_loss([10.0, -5.0, 20.0, -3.0])
        self.assertAlmostEqual(result, -4.0, places=6)

    def test_no_losses_returns_none(self):
        self.assertIsNone(avg_loss([1.0, 2.0]))

    def test_empty_returns_none(self):
        self.assertIsNone(avg_loss([]))

    def test_all_losses(self):
        result = avg_loss([-5.0, -10.0, -15.0])
        self.assertAlmostEqual(result, -10.0, places=6)


class TestProfitFactor(unittest.TestCase):
    def test_basic(self):
        # gross profit = 30, gross loss = 8 → 3.75
        result = profit_factor([10.0, -5.0, 20.0, -3.0])
        self.assertAlmostEqual(result, 3.75, places=6)

    def test_no_losses_returns_none(self):
        self.assertIsNone(profit_factor([1.0, 2.0, 3.0]))

    def test_no_wins_returns_zero(self):
        result = profit_factor([-1.0, -2.0, -3.0])
        self.assertAlmostEqual(result, 0.0, places=6)

    def test_empty_returns_none(self):
        self.assertIsNone(profit_factor([]))

    def test_break_even_returns_one(self):
        result = profit_factor([10.0, -10.0])
        self.assertAlmostEqual(result, 1.0, places=6)


class DailyEquityReturnsTests(unittest.TestCase):
    """Phase 0.3 — daily mark-to-market resampling for honest Sharpe."""

    def test_known_two_day_return(self):
        from backtest_metrics import daily_equity_returns
        returns = daily_equity_returns([
            ("2026-01-01T10:00:00Z", 100_000.0),
            ("2026-01-02T10:00:00Z", 101_000.0),
        ])
        self.assertEqual(len(returns), 1)
        self.assertAlmostEqual(returns[0], 0.01)

    def test_flat_days_are_forward_filled(self):
        from backtest_metrics import daily_equity_returns
        returns = daily_equity_returns([
            ("2026-01-01T10:00:00Z", 100_000.0),
            ("2026-01-04T10:00:00Z", 103_030.1),  # 3 days later
        ])
        # 3 daily returns: 0, 0, then the jump
        self.assertEqual(len(returns), 3)
        self.assertAlmostEqual(returns[0], 0.0)
        self.assertAlmostEqual(returns[1], 0.0)
        self.assertGreater(returns[2], 0.03)

    def test_last_observation_of_day_wins(self):
        from backtest_metrics import daily_equity_returns
        returns = daily_equity_returns([
            ("2026-01-01T09:00:00Z", 100_000.0),
            ("2026-01-01T18:00:00Z", 90_000.0),   # intraday dip then same-day final
            ("2026-01-02T10:00:00Z", 90_000.0),
        ])
        self.assertEqual(len(returns), 1)
        self.assertAlmostEqual(returns[0], 0.0)

    def test_insufficient_days_returns_empty(self):
        from backtest_metrics import daily_equity_returns
        self.assertEqual(daily_equity_returns([("2026-01-01T00:00:00Z", 1.0)]), [])
        self.assertEqual(daily_equity_returns([]), [])

    def test_sharpe_no_longer_scales_with_trade_count(self):
        """Same equity path chopped into more observations must not raise Sharpe —
        regression for the trade-count annualisation bug."""
        from backtest_metrics import daily_equity_returns, sharpe_ratio
        few = [("2026-01-01T00:00:00Z", 100.0), ("2026-01-05T00:00:00Z", 102.0),
               ("2026-01-09T00:00:00Z", 104.0)]
        many = few + [("2026-01-02T01:00:00Z", 100.5), ("2026-01-03T01:00:00Z", 101.0),
                      ("2026-01-06T01:00:00Z", 102.5), ("2026-01-07T01:00:00Z", 103.0)]
        s_few = sharpe_ratio(daily_equity_returns(sorted(few)), periods_per_year=365)
        s_many = sharpe_ratio(daily_equity_returns(sorted(many)), periods_per_year=365)
        # both defined and same order of magnitude — no √N blow-up with activity
        self.assertIsNotNone(s_few)
        self.assertIsNotNone(s_many)
        self.assertLess(abs(s_many), abs(s_few) * 3)


if __name__ == "__main__":
    unittest.main()
