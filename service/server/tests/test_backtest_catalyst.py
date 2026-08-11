"""Plan 23 Gate 0 — catalyst event-study harness (backtest_catalyst.py).

Pure replay over explicit inputs: no DB, no LLM, no network. The contract
under test: reaction-day resolution, PEAD qualification (gap AND volume
shock, both directions), next-open entry / day-H open exit, fees on both
legs, gap-through stops filling at the open, and a walk-forward that picks
parameters on the train window only.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import backtest_catalyst as bc


def _bars(start_day=1, n=40, price=100.0, vol=1000.0):
    """Flat daily bars: date d{i:03d} keeps lexical order == chronological."""
    out = []
    for i in range(n):
        out.append({"date": f"2025-01-{start_day + i:02d}" if start_day + i <= 28
                    else f"2025-02-{start_day + i - 28:02d}",
                    "open": price, "high": price, "low": price,
                    "close": price, "volume": vol})
    return out


def _gap_up(bars, idx, gap_pct=6.0, vol_mult=3.0, drift_pct=0.0):
    """Make bars[idx] a reaction day: open gaps up from prev close on volume.
    Optionally drift every later bar up by drift_pct per day (open & close)."""
    prev_close = bars[idx - 1]["close"]
    o = prev_close * (1 + gap_pct / 100.0)
    bars[idx].update({"open": o, "high": o, "low": o, "close": o,
                      "volume": bars[idx - 1]["volume"] * vol_mult})
    for j in range(idx + 1, len(bars)):
        p = bars[j - 1]["close"] * (1 + drift_pct / 100.0)
        bars[j].update({"open": p, "high": p, "low": p, "close": p})
    return bars


class Qualification(unittest.TestCase):
    def test_gap_and_volume_shock_qualify_long(self):
        bars = _gap_up(_bars(), 25, gap_pct=6.0, vol_mult=3.0)
        ev = bc.qualify_event(bars, bars[25]["date"], gap_min_pct=4.0,
                              vol_mult_min=2.0)
        self.assertIsNotNone(ev)
        self.assertEqual(ev["direction"], 1)
        self.assertEqual(ev["reaction_date"], bars[25]["date"])
        self.assertAlmostEqual(ev["gap_pct"], 6.0, places=6)

    def test_gap_without_volume_does_not_qualify(self):
        bars = _gap_up(_bars(), 25, gap_pct=6.0, vol_mult=1.1)
        self.assertIsNone(bc.qualify_event(bars, bars[25]["date"],
                                           gap_min_pct=4.0, vol_mult_min=2.0))

    def test_volume_without_gap_does_not_qualify(self):
        bars = _gap_up(_bars(), 25, gap_pct=1.0, vol_mult=3.0)
        self.assertIsNone(bc.qualify_event(bars, bars[25]["date"],
                                           gap_min_pct=4.0, vol_mult_min=2.0))

    def test_down_gap_qualifies_short_direction(self):
        bars = _gap_up(_bars(), 25, gap_pct=-6.0, vol_mult=3.0)
        ev = bc.qualify_event(bars, bars[25]["date"], gap_min_pct=4.0,
                              vol_mult_min=2.0)
        self.assertIsNotNone(ev)
        self.assertEqual(ev["direction"], -1)

    def test_reaction_day_resolves_to_larger_gap_of_two_candidates(self):
        # AMC print: the event date session is quiet, the NEXT session gaps.
        bars = _gap_up(_bars(), 26, gap_pct=6.0, vol_mult=3.0)
        ev = bc.qualify_event(bars, bars[25]["date"], gap_min_pct=4.0,
                              vol_mult_min=2.0)
        self.assertIsNotNone(ev)
        self.assertEqual(ev["reaction_date"], bars[26]["date"])


class Replay(unittest.TestCase):
    def test_entry_next_open_exit_day_h_open_with_fees_both_legs(self):
        # 1%/day drift after a qualified up-gap at index 25.
        bars = _gap_up(_bars(), 25, gap_pct=6.0, vol_mult=3.0, drift_pct=1.0)
        ev = bc.qualify_event(bars, bars[25]["date"], 4.0, 2.0)
        tr = bc.replay_event(bars, ev, hold_days=2, fee_side=0.00005)
        self.assertEqual(tr["entry_date"], bars[26]["date"])   # next open
        self.assertEqual(tr["exit_date"], bars[28]["date"])    # +2 sessions
        self.assertAlmostEqual(tr["entry"], bars[26]["open"])
        self.assertAlmostEqual(tr["exit_px"], bars[28]["open"])
        gross = (bars[28]["open"] / bars[26]["open"] - 1) * 100
        self.assertAlmostEqual(tr["net_ret_pct"], gross - 2 * 0.005, places=6)
        self.assertGreater(tr["net_ret_pct"], 0)

    def test_short_direction_profits_from_down_drift(self):
        bars = _gap_up(_bars(), 25, gap_pct=-6.0, vol_mult=3.0, drift_pct=-1.0)
        ev = bc.qualify_event(bars, bars[25]["date"], 4.0, 2.0)
        tr = bc.replay_event(bars, ev, hold_days=2, fee_side=0.00005)
        self.assertGreater(tr["net_ret_pct"], 0)

    def test_stop_gap_through_fills_at_open_not_stop(self):
        bars = _gap_up(_bars(), 25, gap_pct=6.0, vol_mult=3.0)
        # day after entry opens −10% — far through a 5% stop
        entry_open = bars[26]["open"]
        crash = entry_open * 0.90
        for j in range(27, len(bars)):
            bars[j].update({"open": crash, "high": crash, "low": crash,
                            "close": crash})
        ev = bc.qualify_event(bars, bars[25]["date"], 4.0, 2.0)
        tr = bc.replay_event(bars, ev, hold_days=5, fee_side=0.0,
                             stop_pct=5.0)
        self.assertEqual(tr["exit_reason"], "stop_gap_through")
        self.assertAlmostEqual(tr["exit_px"], crash)          # open, not stop
        self.assertAlmostEqual(tr["net_ret_pct"], -10.0, places=4)

    def test_intraday_stop_touch_fills_at_stop(self):
        bars = _gap_up(_bars(), 25, gap_pct=6.0, vol_mult=3.0)
        entry_open = bars[26]["open"]
        stop_px = entry_open * 0.95
        bars[27].update({"open": entry_open, "high": entry_open,
                         "low": stop_px * 0.999, "close": entry_open})
        ev = bc.qualify_event(bars, bars[25]["date"], 4.0, 2.0)
        tr = bc.replay_event(bars, ev, hold_days=5, fee_side=0.0, stop_pct=5.0)
        self.assertEqual(tr["exit_reason"], "stop")
        self.assertAlmostEqual(tr["exit_px"], stop_px)
        self.assertAlmostEqual(tr["net_ret_pct"], -5.0, places=4)

    def test_event_too_near_end_of_history_returns_none(self):
        bars = _gap_up(_bars(), 38, gap_pct=6.0, vol_mult=3.0)
        ev = bc.qualify_event(bars, bars[38]["date"], 4.0, 2.0)
        self.assertIsNone(bc.replay_event(bars, ev, hold_days=5,
                                          fee_side=0.0))


class PullbackEntry(unittest.TestCase):
    """entry_mode='pullback' — the strategy as pead-drift actually states it:
    enter the first orderly pullback that HOLDS the gap area, on resumption.
    Daily-bar approximation: within `pullback_window` sessions after the
    reaction day, find the first down-close session whose LOW stays at or
    above the reaction-day open; entry is the NEXT session's open. A pullback
    that breaks the gap area disqualifies; no pullback in the window = no
    trade (chasing the spike is exactly what pump-ignition-veto forbids)."""

    def _gapped(self, up=True):
        """Reaction at 25 (gap open 106 / 94); session 26 explicitly HOLDS
        with a with-trend close so the pullback under test sits at 27."""
        bars = _gap_up(_bars(), 25, gap_pct=6.0 if up else -6.0, vol_mult=3.0)
        g = bars[25]["open"]                     # 106.0 up / 94.0 down
        if up:
            bars[26].update({"open": g * 1.002, "high": g * 1.01,
                             "low": g * 1.001, "close": g * 1.008})
        else:
            bars[26].update({"open": g * 0.998, "high": g * 0.999,
                             "low": g * 0.99, "close": g * 0.992})
        return bars, g

    def test_enters_after_first_holding_pullback(self):
        bars, g = self._gapped()
        # session 27: down close vs 26, low HOLDS at/above the gap-day open
        bars[27].update({"open": g * 1.005, "high": g * 1.006,
                         "low": g * 1.0005, "close": g * 1.001})
        ev = bc.qualify_event(bars, bars[25]["date"], 4.0, 2.0)
        tr = bc.replay_event(bars, ev, hold_days=2, fee_side=0.0,
                             entry_mode="pullback")
        self.assertIsNotNone(tr)
        self.assertEqual(tr["entry_date"], bars[28]["date"])
        self.assertAlmostEqual(tr["entry"], bars[28]["open"])

    def test_gap_break_disqualifies(self):
        bars, g = self._gapped()
        # the pullback knifes BELOW the gap-day open — gap area failed
        bars[27].update({"open": g, "high": g,
                         "low": g * 0.97, "close": g * 0.98})
        ev = bc.qualify_event(bars, bars[25]["date"], 4.0, 2.0)
        self.assertIsNone(bc.replay_event(bars, ev, hold_days=2, fee_side=0.0,
                                          entry_mode="pullback"))

    def test_no_pullback_in_window_means_no_trade(self):
        # straight-up drift, never a down close -> no chase, no trade
        bars = _gap_up(_bars(), 25, gap_pct=6.0, vol_mult=3.0, drift_pct=1.0)
        ev = bc.qualify_event(bars, bars[25]["date"], 4.0, 2.0)
        self.assertIsNone(bc.replay_event(bars, ev, hold_days=2, fee_side=0.0,
                                          entry_mode="pullback",
                                          pullback_window=5))

    def test_short_side_mirrors(self):
        bars, g = self._gapped(up=False)
        # session 27: UP close vs 26 whose high stays below the gap-day open
        bars[27].update({"open": g * 0.993, "high": g * 0.9995,
                         "low": g * 0.992, "close": g * 0.998})
        ev = bc.qualify_event(bars, bars[25]["date"], 4.0, 2.0)
        tr = bc.replay_event(bars, ev, hold_days=2, fee_side=0.0,
                             entry_mode="pullback")
        self.assertIsNotNone(tr)
        self.assertEqual(tr["entry_date"], bars[28]["date"])


class WalkForward(unittest.TestCase):
    def _dataset(self):
        """Two symbols; drift exists ONLY after up-gaps (long edge).
        Train events in 2025-01, test events in 2025-02 (lexical split)."""
        data = {}
        events = []
        for sym, idx in (("AAA", 22), ("BBB", 24)):
            bars = _gap_up(_bars(), idx, gap_pct=6.0, vol_mult=3.0,
                           drift_pct=1.5)
            data[sym] = bars
            events.append({"symbol": sym, "event_date": bars[idx]["date"]})
        return data, events

    def test_grid_is_chosen_on_train_only_and_reported(self):
        data, events = self._dataset()
        res = bc.walk_forward(events, data, split_date="2025-01-31",
                              fee_side=0.00005)
        self.assertIn(res["chosen"]["hold_days"], (1, 2, 3, 5))
        self.assertIn("train", res)
        self.assertIn("test", res)
        # with all events in train, test is empty and says so
        self.assertEqual(res["test"]["n"], 0)

    def test_metrics_panel_shape(self):
        data, events = self._dataset()
        res = bc.walk_forward(events, data, split_date="2025-01-01",
                              fee_side=0.00005)
        # all events land in test
        t = res["test"]
        for key in ("n", "hit_rate", "expectancy_pct", "profit_factor",
                    "avg_win_pct", "avg_loss_pct", "max_drawdown_pct",
                    "bootstrap_lb90_pct", "worst_trade_pct"):
            self.assertIn(key, t)
        self.assertEqual(t["n"], 2)
        self.assertGreater(t["expectancy_pct"], 0)


class Bootstrap(unittest.TestCase):
    def test_block_bootstrap_lower_bound_is_deterministic_and_sane(self):
        rets = [("2025-01-06", 1.0), ("2025-01-07", 2.0), ("2025-01-13", 1.5),
                ("2025-01-14", 0.5), ("2025-01-20", 1.2), ("2025-01-21", 1.8)]
        lb1 = bc.block_bootstrap_lb90(rets, seed=7)
        lb2 = bc.block_bootstrap_lb90(rets, seed=7)
        self.assertEqual(lb1, lb2)                 # seeded → reproducible
        self.assertGreater(lb1, 0)                 # all-positive sample
        self.assertLess(lb1, 2.0)                  # a lower bound, not the max

    def test_all_negative_sample_has_negative_lower_bound(self):
        rets = [("2025-01-06", -1.0), ("2025-01-13", -2.0),
                ("2025-01-20", -1.5), ("2025-01-27", -0.5)]
        self.assertLess(bc.block_bootstrap_lb90(rets, seed=7), 0)


if __name__ == "__main__":
    unittest.main()
