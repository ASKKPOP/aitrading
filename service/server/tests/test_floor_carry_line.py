"""R27 — floor-carry churn (2026-08-20): the house loss floor rendered only
while a position was OPEN, so a run already past the floor entered fresh
positions blind and was floor-mandated out one cycle later (run 1531: a
−$5.44 carried loss, then a −$1.16 churn leg covered at 1/41 of its own
stop; class (a) n=4). These tests pin the flat-side render and — per the
standing rule — the WIRING into the composed brief."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import run_engine

_RUN = {"id": 1531, "agent_id": 6, "symbol": "FILUSDT", "market": "crypto"}
_CFG = {"run_budget_usd": 697.42}


class FloorCarryLineTests(unittest.TestCase):
    def test_renders_when_flat_and_past_floor(self):
        with patch.object(run_engine, "compute_run_pnl",
                          return_value={"realized": -6.5993}):
            line = run_engine._floor_carry_line(_RUN, _CFG, 0.0)
        self.assertIn("already realized $-6.60", line.replace("−", "-"))
        self.assertIn("retire", line)
        self.assertIn("first held cycle", line)

    def test_silent_when_holding(self):
        with patch.object(run_engine, "compute_run_pnl",
                          return_value={"realized": -6.5993}):
            self.assertEqual(
                run_engine._floor_carry_line(_RUN, _CFG, -816.4), "")

    def test_silent_when_not_past_floor(self):
        with patch.object(run_engine, "compute_run_pnl",
                          return_value={"realized": -1.0}):
            self.assertEqual(run_engine._floor_carry_line(_RUN, _CFG, 0.0), "")

    def test_fail_soft(self):
        with patch.object(run_engine, "compute_run_pnl",
                          side_effect=RuntimeError("boom")):
            self.assertEqual(run_engine._floor_carry_line(_RUN, _CFG, 0.0), "")

    def test_WIRED_into_the_composed_brief_and_journal(self):
        """Unwire protection: the composed flat brief must carry the line
        AND journal its name (#438)."""
        with patch.object(run_engine, "compute_run_pnl",
                          return_value={"realized": -6.5993}):
            composed = run_engine._compose_position_state(
                _RUN, _CFG, 0.0, {})
        self.assertIn("House floor, before you enter", composed)
        self.assertIn("floor_carry",
                      run_engine._BRIEF_JOURNAL.get(1531, []))
