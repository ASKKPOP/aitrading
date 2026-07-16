"""Strategy-backtest engine mechanics — synthetic-series tests.

Validates the discipline claims: no look-ahead fills, exit stack behavior,
regime/event gating, statistics (Wilson, bootstrap, go/no-go ordering).
"""

from __future__ import annotations

import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from backtest_strategy import (
    DEFAULT_PARAMS,
    WARMUP_BARS,
    bootstrap_pf_lower_bound,
    evaluate_bar_conditions,
    evaluate_go_no_go,
    simulate,
    wilson_lower_bound,
)


def _bars(closes, volumes=None, start="2019-01-01"):
    d0 = date.fromisoformat(start)
    volumes = volumes or [100.0] * len(closes)
    return [{"date": (d0 + timedelta(days=i)).isoformat(),
             "open": closes[i - 1] if i > 0 else closes[0],
             "close": closes[i], "volume": volumes[i]}
            for i in range(len(closes))]


def _drifting_series(n, drift=0.003, wobble=0.009, base=100.0):
    """Rising series with real down-days: +1.2% / −0.6% alternating →
    RSI ≈ 66 (out of the ≥70 overbought zone), MAs stacked bullish."""
    closes, price = [], base
    for i in range(n):
        price *= (1 + drift + (wobble if i % 2 == 0 else -wobble))
        closes.append(price)
    return closes


class ConditionTests(unittest.TestCase):
    def test_b4_and_s5_always_null_historically(self):
        closes = _drifting_series(450)
        cond = evaluate_bar_conditions(closes, [100.0] * len(closes),
                                       [50, 50, 50, 50, 50], 100.0, DEFAULT_PARAMS)
        self.assertIsNone(cond["B4"])
        self.assertIsNone(cond["S5"])
        self.assertIsNone(cond["S6"])

    def test_uptrend_satisfies_direction_conditions(self):
        closes = _drifting_series(450)
        volumes = [100.0] * 449 + [200.0]
        cond = evaluate_bar_conditions(closes, volumes, [50, 50, 50, 50, 50],
                                       100.0, DEFAULT_PARAMS)
        self.assertIs(cond["B1"], True)
        self.assertIs(cond["B2"], True)
        self.assertIs(cond["B3"], True)   # score ≥ 2 with volume 2× confirmed
        self.assertIs(cond["B6"], True)

    def test_b3_fails_without_volume(self):
        closes = _drifting_series(450)
        volumes = [100.0] * 450  # ratio 1.0 < 1.5
        cond = evaluate_bar_conditions(closes, volumes, [50, 50, 50, 50, 50],
                                       100.0, DEFAULT_PARAMS)
        self.assertIs(cond["B3"], False)

    def test_b5_fear_recovery(self):
        closes = _drifting_series(450)
        recovering = evaluate_bar_conditions(closes, [100.0] * 450,
                                             [20, 21, 22, 24, 26], 100.0, DEFAULT_PARAMS)
        deepening = evaluate_bar_conditions(closes, [100.0] * 450,
                                            [28, 27, 26, 24, 22], 100.0, DEFAULT_PARAMS)
        self.assertIs(recovering["B5"], True)
        self.assertIs(deepening["B5"], False)

    def test_b6_event_proximity(self):
        closes = _drifting_series(450)
        near = evaluate_bar_conditions(closes, [100.0] * 450, [50] * 5, 5.0, DEFAULT_PARAMS)
        self.assertIs(near["B6"], False)


class SimulationTests(unittest.TestCase):
    def _run(self, closes, volumes=None, fng=50, events=(), params=None, **kw):
        bars = _bars(closes, volumes)
        fng_by_date = {b["date"]: fng for b in bars}
        p = dict(DEFAULT_PARAMS)
        p.update(params or {})
        return simulate("TEST", bars, fng_by_date, list(events), p, **kw), bars

    def test_entry_fills_next_open_not_signal_close(self):
        n = WARMUP_BARS + 40
        closes = _drifting_series(n)
        volumes = [100.0] * n
        for i in range(WARMUP_BARS, n):
            volumes[i] = 250.0  # confirm volume every signal day
        result, bars = self._run(closes, volumes)
        self.assertGreater(len(result.trades), 0, "uptrend must produce an entry")
        first = result.trades[0]
        signal_idx = next(i for i, b in enumerate(bars) if b["date"] == first.entry_date)
        # fill price is that day's OPEN (previous close) + slippage, not the close
        self.assertAlmostEqual(first.entry_price,
                               bars[signal_idx]["open"] * 1.0005, delta=1e-6)
        self.assertGreater(signal_idx, WARMUP_BARS,
                           "first fill must come after the warmup + signal day")

    def test_stop_loss_exit(self):
        n = WARMUP_BARS + 30
        closes = _drifting_series(WARMUP_BARS + 5)
        peak = closes[-1]
        closes += [peak * (1 - 0.03 * k) for k in range(1, n - len(closes) + 1)]  # crash
        volumes = [100.0] * len(closes)
        for i in range(WARMUP_BARS, len(closes)):
            volumes[i] = 250.0
        result, _ = self._run(closes, volumes)
        self.assertGreater(len(result.trades), 0)
        self.assertIn(result.trades[0].exit_reason,
                      {"stop_loss", "trail_stop", "time_stop", "sell_confluence"})
        self.assertLess(result.trades[0].pnl, 0)

    def test_trailing_lets_winner_ride_past_10pct(self):
        """With the trail armed, the +10% fixed TP is cleared — a strong trend
        must produce a trade exiting well above +10%."""
        n = WARMUP_BARS + 120
        # wobbly strong trend throughout (+1.4%/−0.7% → RSI ≈ 66, ~+0.35%/day)
        closes = _drifting_series(n, drift=0.0035, wobble=0.0105)
        closes += [closes[-1] * (1 - 0.08), closes[-1] * (1 - 0.10)]  # drop triggers trail; next bar fills the exit
        volumes = [100.0] * len(closes)
        for i in range(WARMUP_BARS, len(closes)):
            volumes[i] = 250.0
        result, _ = self._run(closes, volumes)
        self.assertGreater(len(result.trades), 0)
        best = max(result.trades, key=lambda t: t.exit_price / t.entry_price)
        self.assertGreater(best.exit_price / best.entry_price, 1.12,
                           "trail should ride past the old +10% TP")
        self.assertEqual(best.exit_reason, "trail_stop")

    def test_panic_fng_blocks_entries(self):
        n = WARMUP_BARS + 40
        closes = _drifting_series(n)
        volumes = [100.0] * n
        for i in range(WARMUP_BARS, n):
            volumes[i] = 250.0
        result, _ = self._run(closes, volumes, fng=10)  # extreme fear, flat → panic
        self.assertEqual(len(result.trades), 0)

    def test_event_day_blocks_entry(self):
        from datetime import datetime, timezone
        n = WARMUP_BARS + 10
        closes = _drifting_series(n)
        volumes = [100.0] * n
        for i in range(WARMUP_BARS, n):
            volumes[i] = 250.0
        bars = _bars(closes, volumes)
        # put an event on EVERY signal day → B6 false + event window veto
        events = [datetime.fromisoformat(b["date"]).replace(hour=14, tzinfo=timezone.utc)
                  for b in bars[WARMUP_BARS:]]
        result, _ = self._run(closes, volumes, events=events)
        self.assertEqual(len(result.trades), 0)

    def test_signal_window_respected(self):
        n = WARMUP_BARS + 60
        closes = _drifting_series(n)
        volumes = [100.0] * n
        for i in range(WARMUP_BARS, n):
            volumes[i] = 250.0
        bars = _bars(closes, volumes)
        start = bars[WARMUP_BARS + 30]["date"]
        result, _ = self._run(closes, volumes, signal_start=start)
        for t in result.trades:
            self.assertGreaterEqual(t.entry_date, start)


class StatisticsTests(unittest.TestCase):
    def test_wilson_known_value(self):
        # 60 wins / 100: p̂=0.60, z=1.2816 → LB ≈ 0.5359
        lb = wilson_lower_bound(60, 100)
        self.assertAlmostEqual(lb, 0.536, delta=0.005)
        self.assertIsNone(wilson_lower_bound(0, 0))

    def test_wilson_52pct_at_small_n_includes_coin_flip(self):
        """The panel's core point: 52% at n=150 cannot exclude 0.50."""
        lb = wilson_lower_bound(78, 150)  # 52%
        self.assertLess(lb, 0.50)
        lb_big = wilson_lower_bound(1092, 2100)  # 52% at n=2100
        self.assertGreater(lb_big, 0.50)

    def test_bootstrap_pf_bounds(self):
        clearly_profitable = [10.0] * 80 + [-5.0] * 20
        lb = bootstrap_pf_lower_bound(clearly_profitable)
        self.assertGreater(lb, 1.0)
        coin_flip = [10.0] * 50 + [-10.0] * 50
        lb2 = bootstrap_pf_lower_bound(coin_flip)
        self.assertLess(lb2, 1.0)
        self.assertIsNone(bootstrap_pf_lower_bound([1.0, 2.0]))  # no losses

    def test_go_no_go_ordering(self):
        few = evaluate_go_no_go({"trades": 150, "wilson_lb_90": 0.55,
                                 "pf_bootstrap_lb_90": 1.4, "worst_asset_max_dd_pct": 10})
        self.assertEqual(few["verdict"], "INSUFFICIENT_EVIDENCE",
                         "evidence floor must precede PASS")
        good = evaluate_go_no_go({"trades": 500, "wilson_lb_90": 0.52,
                                  "pf_bootstrap_lb_90": 1.2, "worst_asset_max_dd_pct": 20})
        self.assertEqual(good["verdict"], "PASS")
        bad = evaluate_go_no_go({"trades": 500, "wilson_lb_90": 0.49,
                                 "pf_bootstrap_lb_90": 1.2, "worst_asset_max_dd_pct": 20})
        self.assertEqual(bad["verdict"], "FAIL")


if __name__ == "__main__":
    unittest.main()
