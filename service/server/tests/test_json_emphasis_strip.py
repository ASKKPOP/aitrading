"""Markdown emphasis leaking into decision JSON (prod 2026-08-02/03).

gpt-oss intermittently bolds a JSON key — `**"confidence": 0.57,` — which makes
json.loads reject the whole object, so `_json_objects` skips it and a complete
decision is lost: the run journals confidence 0.0, conviction null, scores null
and defaults to hold. Observed on run 923 cycle 9 and run 928 cycle 2 on
2026-08-02, and run 939 cycle 18 on 2026-08-03.

Emphasis INSIDE a string is content, not corruption — 939's own report field
carries "**News analyst**" — so only markers outside string literals may go.
"""

from __future__ import annotations

import os
import sys
import unittest

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import analysis_agents as aa


class EmphasisStripTests(unittest.TestCase):
    # The real run 939 cycle 18 response, trimmed.
    PROD_939 = (
        '{\n  "action": "hold",\n  **"confidence": 0.57,\n'
        '  "scores": {\n    "thesis_alignment": 0.42,\n'
        '    "momentum_quality": 0.35,\n    "entry_quality": 0.28,\n'
        '    "risk_context": 0.33\n  },\n'
        '  "rationale": "no clear long edge exists.",\n'
        '  "report": "### Analyst Synthesis\\n- **News analyst** highlights '
        'broad bullishness. \\n- **Technical analyst** points out TSLA at $322."'
        '\n}'
    )

    def test_bolded_key_no_longer_costs_the_decision(self):
        obj = aa._parse_decision_json(self.PROD_939)
        self.assertIsNotNone(obj, "the whole decision was discarded")
        self.assertEqual(obj["action"], "hold")
        self.assertAlmostEqual(obj["confidence"], 0.57)
        self.assertEqual(obj["scores"]["thesis_alignment"], 0.42)
        self.assertEqual(obj["scores"]["risk_context"], 0.33)

    def test_emphasis_inside_strings_is_content_and_survives(self):
        obj = aa._parse_decision_json(self.PROD_939)
        self.assertIn("**News analyst**", obj["report"])
        self.assertIn("**Technical analyst**", obj["report"])

    def test_clean_json_is_untouched(self):
        obj = aa._parse_decision_json(
            '{"action": "buy", "confidence": 0.71, "rationale": "clean"}')
        self.assertEqual(obj["action"], "buy")
        self.assertAlmostEqual(obj["confidence"], 0.71)
        self.assertEqual(obj["rationale"], "clean")

    def test_bold_around_a_whole_object_is_survivable(self):
        obj = aa._parse_decision_json('**{"action": "sell", "confidence": 0.6}**')
        self.assertIsNotNone(obj)
        self.assertEqual(obj["action"], "sell")

    def test_an_escaped_quote_before_emphasis_does_not_confuse_the_scanner(self):
        obj = aa._parse_decision_json(
            '{"action": "hold", "rationale": "he said \\"**hi**\\" loudly", '
            '**"confidence": 0.44}')
        self.assertIsNotNone(obj)
        self.assertAlmostEqual(obj["confidence"], 0.44)
        self.assertIn("**hi**", obj["rationale"])


if __name__ == "__main__":
    unittest.main()
