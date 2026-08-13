"""Ordinary-day scale at bracket-AUTHORING time (main handoff §8(a),
trigger met 2026-08-13 at n=2): SLV's authored stop sat at 0.55 ordinary
days and UBER's at 0.50; both were collected by routine range within the
hour (−1.82, −3.53) via the SL/TP watcher's full close. The desk authors
stop_pct every cycle but only saw the ordinary-day scale AFTER adverse
drift (_exit_size_line). These tests pin the render and — per the
standing rule — the wiring into BOTH decision prompts.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import run_engine


class OrdinaryDayLineTests(unittest.TestCase):
    _RUN = {"id": 1, "agent_id": 1, "symbol": "SLV", "market": "us-stock"}

    def test_states_the_scale_and_the_unit_lesson(self):
        with patch.object(run_engine, "_typical_daily_move_pct",
                          return_value=1.515):
            line = run_engine._ordinary_day_line(self._RUN)
        self.assertIn("ordinary day on this symbol moves ±1.51%", line)
        self.assertIn("size stops in ordinary-day units", line)

    def test_silent_without_history(self):
        with patch.object(run_engine, "_typical_daily_move_pct",
                          return_value=None):
            self.assertEqual(run_engine._ordinary_day_line(self._RUN), "")

    def test_fail_soft_on_helper_error(self):
        with patch.object(run_engine, "_typical_daily_move_pct",
                          side_effect=RuntimeError("boom")):
            self.assertEqual(run_engine._ordinary_day_line(self._RUN), "")

    def test_the_line_is_actually_WIRED_into_the_light_prompt(self):
        seen = {}

        def _capture(prompt, **kw):
            seen["prompt"] = prompt
            return '{"action":"hold","confidence":0.5}'

        import llm_client
        import price_fetcher
        run = {"id": 1, "agent_id": 1, "symbol": "SLV", "market": "us-stock",
               "market_type": "spot"}
        with patch.object(price_fetcher, "get_price_from_market",
                          return_value=58.85), \
            patch.object(price_fetcher, "get_daily_candles",
                         return_value=[]), \
            patch.object(run_engine, "_position_quantity",
                         return_value=3.65), \
            patch.object(run_engine, "_ordinary_day_line",
                         return_value="SCALE_SENTINEL\n"), \
                patch.object(llm_client, "generate_text", _capture):
            run_engine._light_analysis(run, {})
        self.assertIn("SCALE_SENTINEL", seen.get("prompt", ""),
                      "ordinary-day line is not wired into the light prompt")

    def test_the_line_is_actually_WIRED_into_the_full_prompt(self):
        import inspect
        src = inspect.getsource(run_engine.run_cycle)
        self.assertIn("_ordinary_day_line(run)", src,
                      "ordinary-day line is not wired into the full prompt")


if __name__ == "__main__":
    unittest.main()
