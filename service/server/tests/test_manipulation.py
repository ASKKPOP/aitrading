"""Research 04 Phase 1 — manipulation-shape detection (zero-LLM checklist).

The detector names three engineered-move shapes from data already fetched:
pump ignition (vertical bar on anomalous volume), cascade shock (outsized
move vs the symbol's own σ on elevated volume), crowded funding. Signals are
advisory triggers; null-honesty is the contract under test — missing or
degenerate data must yield NO signal, never a fabricated one.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import manipulation as m


def _bars(n=30, vol=100.0, price=100.0, wiggle=0.2):
    """Quiet tape: alternating ±wiggle% closes so σ is small but nonzero."""
    out = []
    p = price
    for i in range(n):
        nxt = p * (1 + (wiggle / 100.0) * (1 if i % 2 else -1))
        out.append({"ts": i, "open": p, "high": max(p, nxt),
                    "low": min(p, nxt), "close": nxt, "volume": vol})
        p = nxt
    return out


class HourlyShapes(unittest.TestCase):
    def test_quiet_tape_yields_nothing(self):
        self.assertEqual(m.signals_from_hourly(_bars()), [])

    def test_pump_ignition_needs_price_AND_volume_anomaly(self):
        # +6% bar on 8x volume → pump.
        bars = _bars()
        last = bars[-1]
        last["volume"] = 800.0
        last["close"] = last["open"] * 1.06
        self.assertEqual(m.signals_from_hourly(bars),
                         ["manipulation:pump_ignition"])
        # Same climb on ordinary volume is momentum, not a pump.
        last["volume"] = 100.0
        self.assertNotIn("manipulation:pump_ignition",
                         m.signals_from_hourly(bars))
        # Same volume burst without the climb is not a pump either.
        bars2 = _bars()
        bars2[-1]["volume"] = 800.0
        self.assertNotIn("manipulation:pump_ignition",
                         m.signals_from_hourly(bars2))

    def test_pump_is_directional_a_vertical_drop_is_not_ignition(self):
        bars = _bars()
        bars[-1]["volume"] = 800.0
        bars[-1]["close"] = bars[-1]["open"] * 0.94
        self.assertNotIn("manipulation:pump_ignition",
                         m.signals_from_hourly(bars))

    def test_cascade_shock_fires_on_sigma_break_with_volume(self):
        # -3% close-to-close against a ±0.2% tape on 3x volume.
        bars = _bars()
        bars[-1]["volume"] = 300.0
        bars[-1]["close"] = bars[-2]["close"] * 0.97
        bars[-1]["open"] = bars[-2]["close"]
        self.assertEqual(m.signals_from_hourly(bars),
                         ["manipulation:cascade_shock"])
        # The same move on quiet volume is a repricing, not forced flow.
        bars[-1]["volume"] = 100.0
        self.assertEqual(m.signals_from_hourly(bars), [])

    def test_pump_label_suppresses_the_cascade_duplicate(self):
        # A pump bar also breaks σ; it must be reported once, as the pump.
        bars = _bars()
        bars[-1]["volume"] = 900.0
        bars[-1]["close"] = bars[-1]["open"] * 1.08
        self.assertEqual(m.signals_from_hourly(bars),
                         ["manipulation:pump_ignition"])

    def test_null_honest_on_short_history(self):
        bars = _bars(n=10)
        bars[-1]["volume"] = 900.0
        bars[-1]["close"] = bars[-1]["open"] * 1.08
        self.assertEqual(m.signals_from_hourly(bars), [])
        self.assertEqual(m.signals_from_hourly([]), [])
        self.assertEqual(m.signals_from_hourly(None), [])

    def test_null_honest_on_dead_baseline(self):
        # Zero baseline volume: a ratio against nothing is not evidence.
        bars = _bars(vol=0.0)
        bars[-1]["volume"] = 500.0
        bars[-1]["close"] = bars[-1]["open"] * 1.08
        self.assertEqual(m.signals_from_hourly(bars), [])
        # Perfectly flat tape (σ = 0): no cascade judgment possible.
        flat = _bars(wiggle=0.0)
        flat[-1]["volume"] = 300.0
        self.assertEqual(m.signals_from_hourly(flat), [])


class Funding(unittest.TestCase):
    def test_crowded_extremes_flag_both_sides(self):
        self.assertEqual(m.funding_signal(0.0009),
                         ["manipulation:crowded_funding"])
        self.assertEqual(m.funding_signal(-0.0009),
                         ["manipulation:crowded_funding"])

    def test_ordinary_and_null_funding_stay_silent(self):
        self.assertEqual(m.funding_signal(0.0001), [])
        self.assertEqual(m.funding_signal(None), [])
        self.assertEqual(m.funding_signal("garbage"), [])


class Wrapper(unittest.TestCase):
    def test_signals_combine_and_symbol_form_is_normalized(self):
        bars = _bars()
        bars[-1]["volume"] = 900.0
        bars[-1]["close"] = bars[-1]["open"] * 1.08
        seen = {}
        with patch("crypto_feed.fetch_candles",
                   side_effect=lambda p, **k: (seen.setdefault("pair", p), bars)[1]), \
             patch("crypto_feed.fetch_funding_rate",
                   return_value={"funding_rate": 0.0008}):
            out = m.manipulation_signals("btc")
        self.assertEqual(out, ["manipulation:pump_ignition",
                               "manipulation:crowded_funding"])
        self.assertEqual(seen["pair"], "BTCUSDT")

    def test_each_feed_fails_soft_independently(self):
        with patch("crypto_feed.fetch_candles",
                   side_effect=RuntimeError("okx down")), \
             patch("crypto_feed.fetch_funding_rate",
                   return_value={"funding_rate": 0.0008}):
            self.assertEqual(m.manipulation_signals("BTC"),
                             ["manipulation:crowded_funding"])
        with patch("crypto_feed.fetch_candles", return_value=_bars()), \
             patch("crypto_feed.fetch_funding_rate",
                   side_effect=RuntimeError("okx down")):
            self.assertEqual(m.manipulation_signals("BTC"), [])

    def test_kill_switch(self):
        with patch.dict("os.environ", {"MANIP_DETECT_ENABLED": "0"}):
            self.assertEqual(m.manipulation_signals("BTC"), [])


if __name__ == "__main__":
    unittest.main()
