"""Guards for the /financial-events response-layer localization.

Three tiers meet here and each has a way to fail silently:

* Catalogue (Tier B): a key that no longer matches the exact English literal
  market_intel.py emits stops translating and the string reverts to English
  with nobody noticing. `test_catalogue_covers_market_intel_literals` pins the
  known literals so a reword breaks the build.
* LLM cache (Tier C): the batch parser, the salvage-on-drop, the English
  fallback, and the cache write are all covered with a stubbed model.
* Payload localizers: they must deep-copy (never mutate the shared English
  cache object) and must leave enums / numbers alone.
"""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SERVER = Path(__file__).resolve().parent.parent
if str(SERVER) not in sys.path:
    sys.path.insert(0, str(SERVER))

import market_i18n  # noqa: E402
from market_i18n_data import MARKET_PHRASES  # noqa: E402

_KNOWN = "BTC momentum is mixed."  # a catalogue entry, byte-for-byte


class CatalogueTests(unittest.TestCase):
    def test_english_is_passthrough(self):
        self.assertEqual(market_i18n.localize_text(_KNOWN, "en"), _KNOWN)

    def test_empty_and_non_string_passthrough(self):
        self.assertEqual(market_i18n.localize_text("", "ko"), "")
        self.assertEqual(market_i18n.localize_text(None, "ko"), None)
        self.assertEqual(market_i18n.localize_texts([None, "", 42], "ko"), [None, "", 42])

    def test_catalogue_hit_never_calls_llm(self):
        with patch.object(market_i18n, "generate_text") as gen:
            out = market_i18n.localize_text(_KNOWN, "ko")
        gen.assert_not_called()
        self.assertEqual(out, MARKET_PHRASES[_KNOWN]["ko"])
        self.assertNotEqual(out, _KNOWN)

    def test_every_catalogue_entry_has_all_five_languages(self):
        for en, variants in MARKET_PHRASES.items():
            for lang in ("ko", "ja", "th", "vi", "id"):
                self.assertIn(lang, variants, f"{en!r} missing {lang}")
                self.assertTrue(variants[lang].strip(), f"{en!r} empty {lang}")

    def test_catalogue_covers_market_intel_literals(self):
        # These are the exact strings market_intel.py emits into the payloads.
        # If one is reworded there without updating the catalogue, Tier B goes
        # silently English — this list is the tripwire.
        required = {
            # news category labels / descriptions
            "Equities", "Macro", "Crypto", "Commodities",
            "Stocks, ETFs, and company market developments.",
            "Macro regime, policy, and broad economic context.",
            "Crypto market headlines anchored on BTC and ETH.",
            "Energy, transport, and commodity-linked events.",
            # macro signal labels
            "BTC trend", "QQQ trend", "QQQ vs XLP", "Safe-haven pressure",
            "Macro news tone",
            # macro explanations
            "BTC momentum remains positive over the last week.",
            "BTC weakened materially over the last week.",
            "BTC momentum is mixed.",
            "Growth equities are trending higher.",
            "Growth equities are losing momentum.",
            "Growth equity momentum is mixed.",
            "Growth is outperforming defensive staples.",
            "Defensive staples are outperforming growth.",
            "Growth and defensive sectors are balanced.",
            "Safe-haven assets are bid.",
            "Safe-haven demand is subdued.",
            "Safe-haven demand is present but not dominant.",
            "Macro news snapshot is not available yet.",
            "Macro news flow leans constructive.",
            "Macro news flow leans defensive.",
            "Macro news flow is mixed.",
            # macro verdict summaries
            "Risk appetite is leading across the current macro snapshot.",
            "Defensive pressure dominates the current macro snapshot.",
            "Macro signals are mixed and do not show a clear regime.",
            # stock factors
            "Price is above the 20-day moving average.",
            "Price is below the 20-day moving average.",
            "Price is above the 60-day moving average.",
            "Price is below the 60-day moving average.",
            "Short-term momentum is positive.",
            "Short-term momentum weakened materially.",
            "Monthly trend remains constructive.",
            "Monthly trend remains weak.",
            "Moving averages are stacked in a bullish order.",
            "Moving averages are stacked in a bearish order.",
            "Price is approaching the recent resistance zone.",
            "Price is holding near recent support.",
        }
        missing = sorted(required - set(MARKET_PHRASES))
        self.assertEqual(missing, [], f"catalogue drifted from market_intel: {missing}")


class LlmCacheTests(unittest.TestCase):
    def setUp(self):
        # Isolate the KV cache to a per-test dict so cache state can't leak.
        self._store: dict = {}
        self._get = patch.object(market_i18n, "get_json", lambda k: self._store.get(k))
        self._set = patch.object(
            market_i18n, "set_json",
            lambda k, v, ttl_seconds=None: self._store.__setitem__(k, v) or True)
        self._get.start()
        self._set.start()
        self.addCleanup(self._get.stop)
        self.addCleanup(self._set.stop)

    def test_external_text_translated_and_cached(self):
        src = "Apple beats on earnings, shares pop"
        with patch.object(market_i18n, "llm_configured", return_value=True), \
             patch.object(market_i18n, "generate_text", return_value="1. 애플 실적 호조, 주가 급등") as gen:
            out = market_i18n.localize_text(src, "ko")
        self.assertEqual(out, "애플 실적 호조, 주가 급등")
        gen.assert_called_once()
        # Second call is served from cache — no second model call.
        with patch.object(market_i18n, "llm_configured", return_value=True), \
             patch.object(market_i18n, "generate_text") as gen2:
            out2 = market_i18n.localize_text(src, "ko")
        gen2.assert_not_called()
        self.assertEqual(out2, "애플 실적 호조, 주가 급등")

    def test_unconfigured_llm_falls_back_to_english(self):
        src = "Some fresh external headline"
        with patch.object(market_i18n, "llm_configured", return_value=False), \
             patch.object(market_i18n, "generate_text") as gen:
            out = market_i18n.localize_text(src, "ko")
        gen.assert_not_called()
        self.assertEqual(out, src)

    def test_model_returning_none_falls_back_to_english(self):
        src = "Another external headline"
        with patch.object(market_i18n, "llm_configured", return_value=True), \
             patch.object(market_i18n, "generate_text", return_value=None):
            out = market_i18n.localize_text(src, "ko")
        self.assertEqual(out, src)

    def test_dropped_line_salvages_the_rest(self):
        a, b = "Headline alpha", "Headline bravo"
        # Model returns only line 2 — line 1 must stay English, line 2 wins.
        with patch.object(market_i18n, "llm_configured", return_value=True), \
             patch.object(market_i18n, "generate_text", return_value="2. 브라보 번역"):
            out = market_i18n.localize_texts([a, b], "ko")
        self.assertEqual(out, [a, "브라보 번역"])

    def test_catalogue_wins_over_llm_in_mixed_batch(self):
        with patch.object(market_i18n, "llm_configured", return_value=True), \
             patch.object(market_i18n, "generate_text", return_value="1. 외부 번역") as gen:
            out = market_i18n.localize_texts([_KNOWN, "External only text"], "ko")
        # Only the non-catalogue string is sent to the model.
        gen.assert_called_once()
        self.assertEqual(out[0], MARKET_PHRASES[_KNOWN]["ko"])
        self.assertEqual(out[1], "외부 번역")


class PayloadLocalizerTests(unittest.TestCase):
    def setUp(self):
        self._store: dict = {}
        patch.object(market_i18n, "get_json", lambda k: self._store.get(k)).start()
        patch.object(
            market_i18n, "set_json",
            lambda k, v, ttl_seconds=None: self._store.__setitem__(k, v) or True).start()
        self.addCleanup(patch.stopall)

    def test_news_payload_deep_copied_and_localized(self):
        payload = {
            "categories": [{
                "category": "macro",
                "label": "Macro",
                "description": "Macro regime, policy, and broad economic context.",
                "summary": {"activity_level": "active", "top_headline": "Fresh headline here"},
                "items": [{"title": "Item title", "summary": "Item summary body",
                           "overall_sentiment_label": "Bullish"}],
            }],
        }
        original = copy.deepcopy(payload)
        with patch.object(market_i18n, "llm_configured", return_value=True), \
             patch.object(market_i18n, "generate_text",
                          return_value="1. 헤드라인\n2. 항목 제목\n3. 항목 요약"):
            out = market_i18n.localize_news_payload(payload, "ko")
        # Original (the shared cache object) is untouched.
        self.assertEqual(payload, original)
        cat = out["categories"][0]
        # Catalogue-driven label/description.
        self.assertEqual(cat["label"], MARKET_PHRASES["Macro"]["ko"])
        self.assertEqual(cat["description"],
                         MARKET_PHRASES["Macro regime, policy, and broad economic context."]["ko"])
        # Enum + external sentiment label are left raw for the frontend to map.
        self.assertEqual(cat["summary"]["activity_level"], "active")
        self.assertEqual(cat["items"][0]["overall_sentiment_label"], "Bullish")
        # External free text went through the model.
        self.assertEqual(cat["summary"]["top_headline"], "헤드라인")
        self.assertEqual(cat["items"][0]["title"], "항목 제목")
        self.assertEqual(cat["items"][0]["summary"], "항목 요약")

    def test_macro_payload_localizes_via_catalogue_only(self):
        payload = {
            "verdict": "defensive",
            "meta": {"summary": "Defensive pressure dominates the current macro snapshot."},
            "signals": [{
                "id": "btc_trend", "label": "BTC trend", "status": "bullish",
                "explanation": "BTC momentum remains positive over the last week.",
                "value": 5.4,
            }],
        }
        with patch.object(market_i18n, "generate_text") as gen:
            out = market_i18n.localize_macro_payload(payload, "ja")
        gen.assert_not_called()  # everything here is catalogue
        self.assertEqual(out["meta"]["summary"],
                         MARKET_PHRASES["Defensive pressure dominates the current macro snapshot."]["ja"])
        sig = out["signals"][0]
        self.assertEqual(sig["label"], MARKET_PHRASES["BTC trend"]["ja"])
        self.assertEqual(sig["explanation"],
                         MARKET_PHRASES["BTC momentum remains positive over the last week."]["ja"])
        # Enum + number untouched.
        self.assertEqual(out["verdict"], "defensive")
        self.assertEqual(sig["status"], "bullish")
        self.assertEqual(sig["value"], 5.4)

    def test_featured_stocks_factors_localized(self):
        payload = {"items": [{
            "symbol": "AAPL", "signal": "buy", "trend_status": "bullish",
            "bullish_factors": ["Short-term momentum is positive."],
            "risk_factors": ["Price is approaching the recent resistance zone."],
            "summary": "AAPL keeps a constructive setup.",
            "analysis": {"bullish_factors": ["Monthly trend remains constructive."]},
        }]}
        with patch.object(market_i18n, "llm_configured", return_value=True), \
             patch.object(market_i18n, "generate_text", return_value="1. 애플 우호적 구도 유지"):
            out = market_i18n.localize_featured_stocks_payload(payload, "ko")
        item = out["items"][0]
        self.assertEqual(item["bullish_factors"][0],
                         MARKET_PHRASES["Short-term momentum is positive."]["ko"])
        self.assertEqual(item["risk_factors"][0],
                         MARKET_PHRASES["Price is approaching the recent resistance zone."]["ko"])
        self.assertEqual(item["analysis"]["bullish_factors"][0],
                         MARKET_PHRASES["Monthly trend remains constructive."]["ko"])
        self.assertEqual(item["summary"], "애플 우호적 구도 유지")  # LLM path
        # Enums untouched.
        self.assertEqual(item["signal"], "buy")
        self.assertEqual(item["trend_status"], "bullish")

    def test_en_request_returns_payload_unchanged(self):
        payload = {"signals": [{"label": "BTC trend"}], "meta": {}}
        self.assertIs(market_i18n.localize_macro_payload(payload, "en"), payload)


if __name__ == "__main__":
    unittest.main()
