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


class CacheAndWarmTests(unittest.TestCase):
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
        # Clear the process-global in-flight set + in-process cache between tests.
        with market_i18n._inflight_lock:
            market_i18n._inflight.clear()
        market_i18n._MEM_CACHE.clear()

    def _seed(self, src, lang, value):
        self._store[market_i18n._cache_key(src, lang)] = value

    # ── the request path never calls the model ─────────────────────────────
    def test_cold_miss_returns_english_and_schedules_warm_when_enabled(self):
        src = "Apple beats on earnings, shares pop"
        with patch.object(market_i18n, "_warm_enabled", return_value=True), \
             patch.object(market_i18n, "generate_text") as gen, \
             patch.object(market_i18n, "_schedule_warm") as sched:
            out = market_i18n.localize_text(src, "ko")
        gen.assert_not_called()          # no model call on the request path
        self.assertEqual(out, src)        # English now
        sched.assert_called_once()
        self.assertEqual(sched.call_args.args[0], [src])  # queued for warming

    def test_warm_enabled_by_default_schedules(self):
        # Default (unset) is ON now that translation runs on the dedicated model.
        src = "Apple beats on earnings, shares pop"
        with patch.dict(market_i18n.os.environ, {}, clear=False), \
             patch.object(market_i18n, "_schedule_warm") as sched:
            market_i18n.os.environ.pop("MARKET_I18N_LLM_WARM", None)
            out = market_i18n.localize_text(src, "ko")
        self.assertEqual(out, src)   # English now, localizes on a later request
        sched.assert_called_once()

    def test_warm_kill_switch_disables_scheduling(self):
        src = "Apple beats on earnings, shares pop"
        with patch.dict(market_i18n.os.environ, {"MARKET_I18N_LLM_WARM": "0"}), \
             patch.object(market_i18n, "_schedule_warm") as sched:
            out = market_i18n.localize_text(src, "ko")
        self.assertEqual(out, src)
        sched.assert_not_called()

    def test_cache_hit_resolves_inline_without_warming(self):
        src = "Apple beats on earnings, shares pop"
        self._seed(src, "ko", "애플 실적 호조, 주가 급등")
        with patch.object(market_i18n, "_schedule_warm") as sched:
            out = market_i18n.localize_text(src, "ko")
        self.assertEqual(out, "애플 실적 호조, 주가 급등")
        sched.assert_not_called()

    def test_catalogue_resolves_inline_only_miss_is_warmed(self):
        with patch.object(market_i18n, "_warm_enabled", return_value=True), \
             patch.object(market_i18n, "_schedule_warm") as sched:
            out = market_i18n.localize_texts([_KNOWN, "External only text"], "ko")
        self.assertEqual(out[0], MARKET_PHRASES[_KNOWN]["ko"])  # catalogue inline
        self.assertEqual(out[1], "External only text")           # English now
        sched.assert_called_once()
        self.assertEqual(sched.call_args.args[0], ["External only text"])

    # ── the background warmer populates the cache ──────────────────────────
    def test_warm_translates_and_caches(self):
        src = "Apple beats on earnings, shares pop"
        with patch.object(market_i18n, "llm_configured", return_value=True), \
             patch.object(market_i18n, "generate_text", return_value="1. 애플 실적 호조, 주가 급등"):
            market_i18n._warm([src], "ko")
        self.assertEqual(self._store[market_i18n._cache_key(src, "ko")], "애플 실적 호조, 주가 급등")
        # After warming, the request path serves it inline.
        with patch.object(market_i18n, "_schedule_warm") as sched:
            self.assertEqual(market_i18n.localize_text(src, "ko"), "애플 실적 호조, 주가 급등")
        sched.assert_not_called()

    def test_warm_persists_in_process_without_kv(self):
        # The prod condition: Redis-less, so get_json/set_json are no-ops. The
        # in-process cache must still carry a warmed translation from the warm
        # thread to a later request — otherwise Tier C produces nothing.
        src = "Headline that needs translating"
        with patch.object(market_i18n, "get_json", lambda k: None), \
             patch.object(market_i18n, "set_json", lambda k, v, ttl_seconds=None: False), \
             patch.object(market_i18n, "llm_configured", return_value=True), \
             patch.object(market_i18n, "generate_text", return_value="1. 번역됨"):
            market_i18n._warm([src], "ko")
            with patch.object(market_i18n, "_schedule_warm") as sched:
                out = market_i18n.localize_text(src, "ko")
        self.assertEqual(out, "번역됨")   # served from the in-process cache
        sched.assert_not_called()         # it was a hit, no re-warm

    def test_warm_salvages_dropped_line(self):
        a, b = "Headline alpha", "Headline bravo"
        # Model returns only line 2 — line 1 stays uncached (English), line 2 caches.
        with patch.object(market_i18n, "llm_configured", return_value=True), \
             patch.object(market_i18n, "generate_text", return_value="2. 브라보 번역"):
            market_i18n._warm([a, b], "ko")
        self.assertNotIn(market_i18n._cache_key(a, "ko"), self._store)
        self.assertEqual(self._store[market_i18n._cache_key(b, "ko")], "브라보 번역")

    def test_translate_batch_pins_dedicated_provider(self):
        # Tier C must run on the dedicated translation model (Sonnet), never the
        # trading gpt-oss — assert the LLM context in force during the call.
        from llm_client import current_llm_context
        seen = {}

        def capture(*a, **k):
            ctx = current_llm_context()
            seen["provider"] = ctx.provider if ctx else None
            seen["model"] = ctx.model if ctx else None
            return "1. 번역"

        with patch.object(market_i18n, "llm_configured", return_value=True), \
             patch.object(market_i18n, "generate_text", side_effect=capture):
            out = market_i18n._llm_translate_batch(["A headline"], "ko")
        self.assertEqual(seen["provider"], market_i18n._XLATE_PROVIDER)
        self.assertEqual(seen["provider"], "anthropic")
        self.assertEqual(seen["model"], "claude-sonnet-5")
        self.assertEqual(out, {"A headline": "번역"})

    def test_batch_token_budget_scales_with_content(self):
        # Paragraph-length summaries must get a budget big enough not to truncate
        # the tail of the batch (the old flat ~48/line ceiling did — regression).
        summaries = [f"Summary number {i} " + "detail " * 40 for i in range(4)]
        seen = {}

        def capture(prompt, **k):
            seen["max_tokens"] = k.get("max_tokens")
            return "\n".join(f"{i + 1}. 번역{i}" for i in range(len(summaries)))

        with patch.object(market_i18n, "llm_configured", return_value=True), \
             patch.object(market_i18n, "generate_text", side_effect=capture):
            out = market_i18n._llm_translate_batch(summaries, "ko")
        self.assertGreater(seen["max_tokens"], 1000)   # not the old ~272 ceiling
        self.assertEqual(len(out), len(summaries))      # every line survives

    def test_warm_model_none_caches_nothing(self):
        src = "Another external headline"
        with patch.object(market_i18n, "llm_configured", return_value=True), \
             patch.object(market_i18n, "generate_text", return_value=None):
            market_i18n._warm([src], "ko")
        self.assertEqual(self._store, {})

    # ── scheduling: dedup + no-model guards ────────────────────────────────
    def test_schedule_warm_skips_unconfigured_model(self):
        with patch.object(market_i18n, "llm_configured", return_value=False), \
             patch.object(market_i18n.threading, "Thread") as thread:
            market_i18n._schedule_warm(["x"], "ko")
        thread.assert_not_called()
        self.assertEqual(market_i18n._inflight, set())  # marks released

    def test_schedule_warm_dedupes_inflight(self):
        with patch.object(market_i18n, "llm_configured", return_value=True), \
             patch.object(market_i18n.threading, "Thread") as thread:
            market_i18n._schedule_warm(["x"], "ko")   # claims + spawns
            market_i18n._schedule_warm(["x"], "ko")   # already in flight → skip
        self.assertEqual(thread.call_count, 1)


class PayloadLocalizerTests(unittest.TestCase):
    def setUp(self):
        self._store: dict = {}
        patch.object(market_i18n, "get_json", lambda k: self._store.get(k)).start()
        patch.object(
            market_i18n, "set_json",
            lambda k, v, ttl_seconds=None: self._store.__setitem__(k, v) or True).start()
        # Warming is async in production; keep it out of these wiring tests.
        patch.object(market_i18n, "_schedule_warm", lambda texts, lang: None).start()
        self.addCleanup(patch.stopall)
        market_i18n._MEM_CACHE.clear()

    def _seed(self, src, lang, value):
        self._store[market_i18n._cache_key(src, lang)] = value

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
        # External strings resolve inline only when already cached (warmed).
        self._seed("Fresh headline here", "ko", "헤드라인")
        self._seed("Item title", "ko", "항목 제목")
        # "Item summary body" deliberately left uncached — stays English (deferred).
        original = copy.deepcopy(payload)
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
        # Cached external free text is localized; uncached stays English.
        self.assertEqual(cat["summary"]["top_headline"], "헤드라인")
        self.assertEqual(cat["items"][0]["title"], "항목 제목")
        self.assertEqual(cat["items"][0]["summary"], "Item summary body")

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
        # The free-text summary is external — it localizes once warmed into cache.
        self._seed("AAPL keeps a constructive setup.", "ko", "애플 우호적 구도 유지")
        out = market_i18n.localize_featured_stocks_payload(payload, "ko")
        item = out["items"][0]
        # Factors are fixed vocabulary → catalogue, inline.
        self.assertEqual(item["bullish_factors"][0],
                         MARKET_PHRASES["Short-term momentum is positive."]["ko"])
        self.assertEqual(item["risk_factors"][0],
                         MARKET_PHRASES["Price is approaching the recent resistance zone."]["ko"])
        self.assertEqual(item["analysis"]["bullish_factors"][0],
                         MARKET_PHRASES["Monthly trend remains constructive."]["ko"])
        self.assertEqual(item["summary"], "애플 우호적 구도 유지")  # cached (warmed)
        # Enums untouched.
        self.assertEqual(item["signal"], "buy")
        self.assertEqual(item["trend_status"], "bullish")

    def test_en_request_returns_payload_unchanged(self):
        payload = {"signals": [{"label": "BTC trend"}], "meta": {}}
        self.assertIs(market_i18n.localize_macro_payload(payload, "en"), payload)


if __name__ == "__main__":
    unittest.main()
