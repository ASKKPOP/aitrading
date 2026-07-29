"""The desk panel's stance sentences (2026-07-28).

The after-login dashboard renders /api/market-intel/regime's `reasons` under
Korean headings. regime.py builds them in English and the route served them
raw, so a Korean member read

    지금 데스크의 판단
    F&G 29 in fear band · realized-vol percentile 18 elevated

They are a closed set of 11 sentences WE author, with the same interpolation
shape as the error catalogue, so they live there and translate on the way out.

The risk this design creates is cache poisoning: one cache entry is shared by
every language, so translating in place — rather than on a copy — would serve
the first caller's language to everyone. That is the main thing under test.
"""
from __future__ import annotations

import ast
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from fastapi.testclient import TestClient

import database
from analysis_agents import LANG_NAMES
from i18n_errors import translate
from i18n_errors_data import MESSAGES

FAKE = {
    "regime": "caution", "size_multiplier": 0.5, "allow_new_buys": True,
    "enforced": False,
    "reasons": ["F&G 29 in fear band", "realized-vol percentile 18 elevated"],
}


def _regime_reason_templates() -> list[str]:
    """Every string regime.py appends to `reasons`, f-strings collapsed."""
    tree = ast.parse((SERVER_DIR / "regime.py").read_text(encoding="utf-8"))
    out = []
    for n in ast.walk(tree):
        if not (isinstance(n, ast.Call)
                and getattr(n.func, "attr", "") == "append"
                and getattr(getattr(n.func, "value", None), "id", "") == "reasons"):
            continue
        a = n.args[0]
        if isinstance(a, ast.Constant):
            out.append(a.value)
        elif isinstance(a, ast.JoinedStr):
            out.append("".join(v.value if isinstance(v, ast.Constant) else "{}"
                               for v in a.values))
    return out


class TheCatalogueCoversTheEngine(unittest.TestCase):

    def test_every_reason_the_engine_can_emit_is_translated(self):
        templates = _regime_reason_templates()
        self.assertGreaterEqual(len(templates), 11, "reason extraction broke")
        for t in templates:
            with self.subTest(reason=t):
                self.assertIn(t, MESSAGES, f"regime reason not in the catalogue: {t!r}")
                for lang in LANG_NAMES:
                    if lang != "en":
                        self.assertIn(lang, MESSAGES[t], f"{t!r} missing {lang}")

    def test_values_survive_the_pattern_path(self):
        for lang in LANG_NAMES:
            with self.subTest(lang=lang):
                out = translate("F&G 29 < 20 (extreme fear)", lang)
                self.assertIn("29", out)
                self.assertIn("20", out)


class TheRouteLocalizes(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "t.db")
        database.init_database()
        self.client = TestClient(create_app_fresh())

    def tearDown(self):
        self.tmp.cleanup()

    def _get(self, lang):
        with patch("regime.evaluate_market_regime", return_value=dict(FAKE)):
            return self.client.get("/api/market-intel/regime",
                                   headers={"Accept-Language": lang}).json()

    def test_english_is_unchanged(self):
        self.assertEqual(self._get("en")["reasons"], FAKE["reasons"])

    def test_each_language_differs_from_english(self):
        for lang in LANG_NAMES:
            if lang == "en":
                continue
            with self.subTest(lang=lang):
                got = self._get(lang)["reasons"]
                self.assertNotEqual(got, FAKE["reasons"], lang)
                self.assertEqual(len(got), len(FAKE["reasons"]))

    def test_a_shared_cache_entry_is_not_poisoned_by_the_first_caller(self):
        """One cache entry serves every language. Translating in place would
        hand the second caller the first caller's language."""
        self._get("ko")
        self.assertEqual(self._get("en")["reasons"], FAKE["reasons"])
        ko = self._get("ko")["reasons"]
        self._get("id")
        self.assertEqual(self._get("ko")["reasons"], ko)

    def test_an_untranslated_reason_passes_through(self):
        payload = dict(FAKE, reasons=["a reason nobody translated"])
        with patch("regime.evaluate_market_regime", return_value=payload):
            got = self.client.get("/api/market-intel/regime",
                                  headers={"Accept-Language": "ko"}).json()
        self.assertEqual(got["reasons"], ["a reason nobody translated"])

    def test_the_rest_of_the_payload_is_untouched(self):
        got = self._get("ko")
        for k in ("regime", "size_multiplier", "allow_new_buys", "enforced"):
            self.assertEqual(got[k], FAKE[k], k)


def create_app_fresh():
    from routes import create_app
    return create_app()


if __name__ == "__main__":
    unittest.main()
