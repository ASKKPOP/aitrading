"""Analyst output language follows the top-bar language selection.

The UI ships five languages (frontend i18n.ts: ko/en/ja/th/vi) and sends the
selection as `lang` on /api/analysis/*. Before this, the routes collapsed
everything to "th" or "en", so a Korean user got a Korean UI shell wrapped
around English briefs and an English trader report.

Also covers the decision parser: when the model answers with the decision and
the report as two separate JSON objects, the report must still be parsed —
not dumped into the card as raw JSON.
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


class NormalizeLangTests(unittest.TestCase):

    def test_every_ui_language_survives(self):
        for code in ("ko", "en", "ja", "th", "vi"):
            self.assertEqual(analysis_agents.normalize_lang(code), code)

    def test_full_locales_are_reduced_to_the_language(self):
        self.assertEqual(analysis_agents.normalize_lang("ko-KR"), "ko")
        self.assertEqual(analysis_agents.normalize_lang("en_US"), "en")

    def test_unknown_and_empty_fall_back_to_english(self):
        for value in ("zh", "", None, "   "):
            self.assertEqual(analysis_agents.normalize_lang(value), "en")


class PromptLanguageTests(unittest.TestCase):
    """The language instruction reaches both LLM prompts that write prose."""

    def _prompts(self, lang: str) -> list[str]:
        captured: list[str] = []

        def fake_generate(prompt, **kwargs):
            captured.append(prompt)
            return '{"action":"hold","confidence":0.5,"report":"ok"}'

        briefs = {k: "brief" for k in
                  ("news", "sentiment", "fundamentals_macro", "technical")}
        with patch.object(analysis_agents, "llm_configured", return_value=True), \
             patch.object(analysis_agents, "generate_text", fake_generate):
            analysis_agents._brief("News Analyst", "Summarise.", {"x": 1}, lang)
            analysis_agents._trader_risk_decision(
                "SOL", "crypto", briefs, {"current_price": 76.4}, [], lang)
        return captured

    def test_each_language_names_itself_in_both_prompts(self):
        for lang, name in (("ko", "Korean"), ("en", "English"), ("ja", "Japanese"),
                           ("th", "Thai"), ("vi", "Vietnamese")):
            brief_prompt, decision_prompt = self._prompts(lang)
            self.assertIn(f"Write in {name}.", brief_prompt)
            self.assertIn(f"Write the rationale and report in {name}.", decision_prompt)

    def test_korean_is_not_silently_downgraded_to_english(self):
        brief_prompt, decision_prompt = self._prompts("ko")
        self.assertNotIn("Write in English.", brief_prompt)
        self.assertNotIn("in English.", decision_prompt)


class DecisionJsonParsingTests(unittest.TestCase):

    def test_decision_and_report_split_across_two_objects_are_merged(self):
        text = ('{"action":"hold","confidence":0.6,"stop":73.0,"rationale":"no edge"}\n'
                '{"report":"**SOL - HOLD.** Consolidating below MA20."}')
        parsed = analysis_agents._parse_decision_json(text)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["action"], "hold")
        self.assertEqual(parsed["confidence"], 0.6)
        self.assertTrue(parsed["report"].startswith("**SOL - HOLD.**"))

    def test_earlier_object_wins_on_conflicting_keys(self):
        text = '{"action":"buy","confidence":0.9}{"action":"sell","confidence":0.1}'
        self.assertEqual(analysis_agents._parse_decision_json(text)["action"], "buy")

    def test_braces_inside_strings_do_not_break_scanning(self):
        text = '{"action":"sell","confidence":0.4,"report":"use {curly} and \\"quotes\\""}'
        parsed = analysis_agents._parse_decision_json(text)
        self.assertEqual(parsed["report"], 'use {curly} and "quotes"')

    def test_single_fenced_object_still_parses(self):
        text = 'Sure!\n```json\n{"action":"buy","confidence":0.8,"report":"go"}\n```'
        self.assertEqual(analysis_agents._parse_decision_json(text)["action"], "buy")

    def test_unusable_answers_still_return_none(self):
        for text in ("", "no json here", '{"action":"yolo"}', '{"action":"buy",'):
            self.assertIsNone(analysis_agents._parse_decision_json(text))

    def test_verification_json_split_across_objects(self):
        text = '{"verdict":"weakened","adjusted_confidence":0.3}\n{"reason":"thin data"}'
        parsed = analysis_agents._parse_verification_json(text)
        self.assertEqual(parsed["verdict"], "weakened")
        self.assertEqual(parsed["adjusted_confidence"], 0.3)
        self.assertEqual(parsed["reason"], "thin data")


if __name__ == "__main__":
    unittest.main()
