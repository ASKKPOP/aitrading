"""One language set, six places that must agree (2026-07-28).

Adding Indonesian meant touching the LLM output language, the alert
catalogue, the email catalogue, the error catalogue, the region registry, the
signup resolver and the frontend picker. Any one of them missed is a silent
half-launch: the member picks Bahasa Indonesia in the top bar and still gets
English alerts, because normalize_lang maps an unknown code to 'en' rather
than raising.

LANG_NAMES in analysis_agents is the single source of truth. These tests fail
on a language present there but missing from a catalogue — which is the shape
of every drift this file exists to catch.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import notifications_i18n as n
import regions
from analysis_agents import LANG_NAMES, normalize_lang
from email_i18n import _VERIFICATION
from i18n_errors_data import MESSAGES as ERROR_MESSAGES

FRONTEND = SERVER_DIR.parents[0] / "frontend" / "src" / "i18n.ts"


class TheRegistryIsTheSourceOfTruth(unittest.TestCase):

    def test_indonesian_is_registered(self):
        self.assertIn("id", LANG_NAMES)
        self.assertEqual(normalize_lang("id-ID"), "id")
        self.assertEqual(normalize_lang("ID"), "id")

    def test_an_unknown_code_still_falls_back_to_english(self):
        for bad in ("de", "xx", "", None, "zz-ZZ"):
            self.assertEqual(normalize_lang(bad), "en")


class EveryCatalogueCoversEveryLanguage(unittest.TestCase):

    def test_alert_messages(self):
        for msg_id, variants in n.MESSAGES.items():
            for lang in LANG_NAMES:
                with self.subTest(msg_id=msg_id, lang=lang):
                    self.assertIn(lang, variants)
                    title, body = variants[lang]
                    self.assertTrue(title and body)

    def test_alert_tokens(self):
        for family, langs in n.TOKENS.items():
            for lang in LANG_NAMES:
                with self.subTest(family=family, lang=lang):
                    self.assertIn(lang, langs)
                    self.assertEqual(set(langs[lang]), set(langs["en"]),
                                     f"{family}/{lang} key set differs from English")

    def test_verdict_and_trigger_tables(self):
        for name, table in (("_VERDICT", n._VERDICT), ("_STANCE", n._STANCE),
                            ("_URGENCY", n._URGENCY), ("_SIDE", n._SIDE),
                            ("_TRIGGER", n._TRIGGER)):
            for lang in LANG_NAMES:
                with self.subTest(table=name, lang=lang):
                    self.assertIn(lang, table)

    def test_transactional_email(self):
        for lang in LANG_NAMES:
            with self.subTest(lang=lang):
                self.assertIn(lang, _VERIFICATION)
                subject, html = _VERIFICATION[lang]
                self.assertTrue(subject)
                self.assertIn("{code}", html)

    def test_error_catalogue(self):
        missing = {lang: [k for k, v in ERROR_MESSAGES.items() if lang not in v]
                   for lang in LANG_NAMES if lang != "en"}
        for lang, keys in missing.items():
            with self.subTest(lang=lang):
                self.assertFalse(keys, f"{lang}: {len(keys)} keys untranslated")

    def test_region_display_names(self):
        for code in regions.supported_regions():
            for lang in LANG_NAMES:
                with self.subTest(region=code, lang=lang):
                    self.assertIn(lang, regions.REGISTRY[code].names)


class IndonesiaIsServed(unittest.TestCase):

    def test_the_region_exists_with_a_real_zone(self):
        r = regions.get_region("ID")
        self.assertIsNotNone(r)
        self.assertEqual(r.timezone, "Asia/Jakarta")
        self.assertEqual(r.lang, "id")
        # zoneinfo must actually know it, or every clock on the page is wrong
        self.assertEqual(regions.normalize_timezone("Asia/Jakarta"), "Asia/Jakarta")

    def test_an_indonesian_ip_resolves_to_indonesian(self):
        import signup_lang
        self.assertEqual(signup_lang._country_to_lang("ID"), "id")

    def test_every_region_default_lang_is_a_language_we_serve(self):
        for code in regions.supported_regions():
            with self.subTest(region=code):
                self.assertIn(regions.default_lang(code), LANG_NAMES)


class TheFrontendPickerAgrees(unittest.TestCase):
    """A language offered in the top bar but unknown to the backend means the
    member switches to it and keeps receiving English."""

    def _source(self) -> str:
        return FRONTEND.read_text(encoding="utf-8")

    def test_the_language_union_matches(self):
        src = self._source()
        declared = re.search(r"export type Language = ([^\n]+)", src)
        self.assertIsNotNone(declared)
        codes = set(re.findall(r"'([a-z-]+)'", declared.group(1)))
        self.assertEqual(codes, set(LANG_NAMES))

    def test_every_language_has_a_picker_label_and_a_locale(self):
        src = self._source()
        listed = set(re.findall(r"\{ value: '([a-z-]+)', label:", src))
        self.assertEqual(listed, set(LANG_NAMES))
        block = re.search(r"LOCALE_BY_LANGUAGE: Record<Language, string> = \{(.*?)\}",
                          src, re.S)
        self.assertIsNotNone(block)
        locales = set(re.findall(r"^\s*([a-z-]+):", block.group(1), re.M))
        self.assertEqual(locales, set(LANG_NAMES))


if __name__ == "__main__":
    unittest.main()
