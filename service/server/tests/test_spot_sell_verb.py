"""A flat spot book must not be offered a verb it cannot execute.

`inventory_rule` (run_engine.py:2527) tells the desk "Spot book with no
inventory: 'sell' is NOT available (nothing to reduce) — a bearish read means
'hold'", and five lines later the action set offers "buy"|"sell"|"hold"
unconditionally. The prompt says sell is impossible and then lists it.

Measured on prod: 33 refusals of "spot sell with no inventory — treated as
hold" across 16 runs between 2026-07-27 and 2026-08-03 — run 939 cycle 19 threw
away a decision at confidence 0.62 / thesis_alignment 0.8 that way. The comment
at run_engine.py:2513 already records the symptom ("spot runs emitted
unactionable sells"): the awareness fix landed, the vocabulary fix did not.
"""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import patch

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import analysis_agents as aa
import run_engine


class LightPathVerbTests(unittest.TestCase):
    def _prompt(self, market, market_type, pos_qty):
        captured = {}

        def gen(prompt, **kw):
            captured["p"] = prompt
            return '{"action": "hold", "confidence": 0.5}'

        run = {"id": 1, "agent_id": 1, "symbol": "SPCX",
               "market": market, "market_type": market_type}
        cfg = {"thesis": {"direction": "short"}}
        with patch("price_fetcher.get_price_from_market", return_value=100.0), \
                patch("price_fetcher.get_daily_candles", return_value=[]), \
                patch("llm_client.generate_text", side_effect=gen), \
                patch.object(run_engine, "_position_quantity", return_value=pos_qty), \
                patch("trading_skills.skills_block", return_value=""):
            run_engine._light_analysis(run, cfg)
        return captured.get("p", "")

    def test_flat_spot_book_is_not_offered_sell(self):
        p = self._prompt("us-stock", "spot", 0.0)
        self.assertTrue(p)
        self.assertNotIn('"sell"', p, "a flat spot book cannot sell")
        self.assertIn('"buy"', p)
        self.assertIn('"hold"', p)

    def test_spot_book_holding_inventory_keeps_sell(self):
        p = self._prompt("us-stock", "spot", 5.0)
        self.assertIn('"sell"', p, "selling reduces a long — must stay offered")

    def test_futures_book_always_keeps_sell(self):
        p = self._prompt("crypto", "futures", 0.0)
        self.assertIn('"sell"', p, "a futures book can open a short while flat")


class FullPathVerbTests(unittest.TestCase):
    def _prompt(self, can_sell):
        captured = {}

        def gen(prompt, **kw):
            captured["p"] = prompt
            return '{"action": "hold", "confidence": 0.5}'

        with patch("analysis_agents.llm_configured", return_value=True), \
                patch("analysis_agents.generate_text", side_effect=gen):
            briefs = {"news": "n", "sentiment": "s",
                      "fundamentals_macro": "f", "technical": "t"}
            aa._trader_risk_decision("SPCX", "us-stock", briefs, {}, {}, "en",
                                     can_sell=can_sell)
        return captured.get("p", "")

    def test_flat_spot_book_is_not_offered_sell(self):
        self.assertNotIn("sell", self._prompt(can_sell=False))

    def test_sell_offered_when_the_book_can_take_it(self):
        self.assertIn("sell", self._prompt(can_sell=True))


if __name__ == "__main__":
    unittest.main()
