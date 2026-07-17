"""P-1: the model may not author the execution price.

Found by the 2026-07-17 audit (4/4 QA confirmed). The trader prompt asks the
LLM for `"entry":number|null` and `_trader_risk_decision` only replaced it
when FALSY, so a non-null model price flowed straight into execution:

    automation.py:401   quantity = size_usd / entry
    risk_engine.py:464  exposure + quantity * price > max_exposure

Both use the SAME model-supplied price, so the arithmetic always reconciles to
exactly size_usd and every notional cap reports ALLOWED — while the position
opened is off by whatever factor the model's price was off by. A unit slip
(60 vs 60,000) is enough; no malice required.

This is the P-1 violation the architecture exists to prevent, hiding in the
one input nobody classified as a limit: every cap is denominated in price, so
whoever sets the price sets the denominator of the whole risk stack.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import analysis_agents

LIVE_PRICE = 63_000.0
TECHNICAL = {"current_price": LIVE_PRICE, "rsi_14": 48.0}
BRIEFS = {"news": "n", "sentiment": "s", "fundamentals_macro": "f", "technical": "t"}


def _decide(model_json: str):
    with patch("analysis_agents.llm_configured", return_value=True), \
         patch("analysis_agents.generate_text", return_value=model_json):
        return analysis_agents._trader_risk_decision(
            "BTCUSDT", "crypto", BRIEFS, TECHNICAL, [], "en")


class ExecutionPriceAuthorityTests(unittest.TestCase):

    def test_unit_slipped_model_price_does_not_become_the_fill(self):
        """The exploit: entry 60 instead of 60,000 would size 1000x."""
        d = _decide('{"action":"buy","confidence":0.8,"entry":60,"rationale":"r","report":"x"}')
        self.assertEqual(d["entry"], LIVE_PRICE)
        self.assertEqual(d["suggested_entry"], 60)      # kept as commentary

    def test_model_price_never_wins_even_when_plausible(self):
        """A near-miss is the dangerous case — it looks reasonable and still
        silently rescales every notional cap."""
        d = _decide('{"action":"buy","confidence":0.7,"entry":58000,"rationale":"r","report":"x"}')
        self.assertEqual(d["entry"], LIVE_PRICE)
        self.assertEqual(d["suggested_entry"], 58000)

    def test_null_entry_still_falls_back_to_the_live_price(self):
        d = _decide('{"action":"buy","confidence":0.6,"entry":null,"rationale":"r","report":"x"}')
        self.assertEqual(d["entry"], LIVE_PRICE)
        self.assertIsNone(d.get("suggested_entry"))

    def test_the_gate_arithmetic_can_no_longer_be_rescaled(self):
        """The whole point: size_usd/entry * entry must equal size_usd at the
        LIVE price, so the exposure cap measures the real notional."""
        size_usd = 1000.0
        d = _decide('{"action":"buy","confidence":0.8,"entry":60,"rationale":"r","report":"x"}')
        quantity = size_usd / float(d["entry"])
        # what the gate would compute, and what the position is really worth
        self.assertAlmostEqual(quantity * LIVE_PRICE, size_usd, places=6)
        # the exploit would have opened 1000x this
        self.assertAlmostEqual(quantity, size_usd / LIVE_PRICE, places=9)

    def test_absurd_model_price_cannot_zero_the_denominator(self):
        for bad in ("0", "-5", '"sixty thousand"'):
            d = _decide(f'{{"action":"buy","confidence":0.8,"entry":{bad},"rationale":"r","report":"x"}}')
            self.assertEqual(d["entry"], LIVE_PRICE, f"entry={bad} must not survive")

    def test_decision_fields_are_otherwise_untouched(self):
        d = _decide('{"action":"buy","confidence":0.8,"entry":60,"rationale":"why","report":"rep"}')
        self.assertEqual(d["action"], "buy")
        self.assertEqual(d["confidence"], 0.8)
        self.assertEqual(d["report"], "rep")


if __name__ == "__main__":
    unittest.main()
