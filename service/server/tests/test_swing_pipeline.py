"""swing_pipeline.py — the live wiring of research/SWING_SIGNAL_STACK.md.

swing_stack.py has always been a pure engine with no caller. This module is
the caller: it collects the six feeds, turns them into the five processor
scores, combines them, decides, and persists the result per symbol.

Every source is patched here — the pipeline must be provable without network.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import crawl_monitor
import database
import swing_pipeline


class _StopLoop(Exception):
    """Breaks the infinite loop under test."""


def _rising_candles(n=30, start=100.0, step=1.0, volume=1_000_000):
    return [
        {
            "open": start + i * step, "high": start + i * step + 1.0,
            "low": start + i * step - 1.0, "close": start + i * step,
            "volume": volume,
        }
        for i in range(n)
    ]


def _falling_candles(n=30, start=200.0, step=-1.5):
    return _rising_candles(n=n, start=start, step=step)


class SwingPipelineTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()

    def tearDown(self):
        self.tmp.cleanup()

    def _evaluate(self, **overrides):
        defaults = {
            "candles": _rising_candles(),
            "benchmark": _rising_candles(),
            "macro": {"vix": 14.0, "vix_5d_ago": 16.0, "y10": 4.0,
                      "y10_5d_ago": 4.2, "dxy": 99.0, "dxy_5d_ago": 100.0},
            "fear_greed": {"value": 20.0, "avg_7d": 15.0},
            "catalyst": {"score": 60.0, "hours_to_next_earnings": None},
            "filings": {"score": 40.0},
            "event_hours": None,
        }
        defaults.update(overrides)

        with patch.object(swing_pipeline, "fetch_candles",
                          lambda symbol, market: defaults["candles"]), \
             patch.object(swing_pipeline, "fetch_benchmark_candles",
                          lambda market: defaults["benchmark"]), \
             patch.object(swing_pipeline, "fetch_macro", lambda: defaults["macro"]), \
             patch.object(swing_pipeline, "fetch_fear_greed",
                          lambda market: defaults["fear_greed"]), \
             patch.object(swing_pipeline, "fetch_catalyst",
                          lambda symbol: defaults["catalyst"]), \
             patch.object(swing_pipeline, "fetch_filings",
                          lambda symbol: defaults["filings"]), \
             patch.object(swing_pipeline, "fetch_macro_event_hours",
                          lambda: defaults["event_hours"]):
            return swing_pipeline.evaluate_symbol("NVDA", market="us-stock")

    # -- composition -----------------------------------------------------
    def test_all_feeds_present_produces_five_scores_and_a_composite(self):
        row = self._evaluate()
        for feed in ("sentiment", "macro", "thesis", "smart_money", "technical"):
            self.assertIsNotNone(row["scores"][feed], feed)
        self.assertIsNotNone(row["composite"])
        self.assertIn(row["action"], ("BUY", "SELL", "WAIT"))

    def test_agreeing_bullish_axes_above_threshold_buy(self):
        row = self._evaluate()
        self.assertEqual(row["action"], "BUY")
        self.assertEqual(row["axis"], "AGREE_BULL")
        self.assertGreaterEqual(row["composite"], 40.0)

    def test_agreeing_bearish_axes_below_threshold_sell(self):
        row = self._evaluate(
            candles=_falling_candles(),
            benchmark=_rising_candles(),
            macro={"vix": 34.0, "vix_5d_ago": 20.0, "y10": 4.6,
                   "y10_5d_ago": 4.2, "dxy": 102.0, "dxy_5d_ago": 99.0},
            fear_greed={"value": 92.0, "avg_7d": 95.0},
            catalyst={"score": -70.0, "hours_to_next_earnings": None},
            filings={"score": -80.0},
        )
        self.assertEqual(row["action"], "SELL")
        self.assertEqual(row["axis"], "AGREE_BEAR")

    def test_conflicting_axes_wait_even_with_a_strong_composite(self):
        """Price firm, crowd euphoric -> the doc's trap row, never a BUY."""
        row = self._evaluate(
            candles=_falling_candles(),
            fear_greed={"value": 20.0, "avg_7d": 15.0},
            catalyst={"score": 90.0, "hours_to_next_earnings": None},
            filings={"score": 90.0},
        )
        self.assertEqual(row["action"], "WAIT")
        self.assertTrue(row["axis"].startswith("CONFLICT"))

    # -- coverage --------------------------------------------------------
    def test_a_dead_feed_is_none_and_its_weight_renormalizes_away(self):
        row = self._evaluate(filings={"score": None}, catalyst={"score": None,
                                                               "hours_to_next_earnings": None})
        self.assertIsNone(row["scores"]["smart_money"])
        self.assertIsNone(row["scores"]["thesis"])
        self.assertIsNotNone(row["composite"])
        self.assertEqual(row["coverage"], 3)

    def test_no_coverage_at_all_waits_and_says_why(self):
        row = self._evaluate(
            candles=[], macro={}, fear_greed=None,
            catalyst={"score": None, "hours_to_next_earnings": None},
            filings={"score": None},
        )
        self.assertIsNone(row["composite"])
        self.assertEqual(row["action"], "WAIT")
        self.assertEqual(row["coverage"], 0)
        self.assertIn("coverage", row["reason"])

    def test_too_few_candles_is_no_technical_score(self):
        row = self._evaluate(candles=_rising_candles(n=10))
        self.assertIsNone(row["scores"]["technical"])

    # -- risk gate -------------------------------------------------------
    def test_earnings_inside_24h_vetoes_a_fresh_buy(self):
        row = self._evaluate(catalyst={"score": 60.0, "hours_to_next_earnings": 12})
        self.assertEqual(row["action"], "WAIT")
        self.assertEqual(row["veto"], "event_blackout")

    def test_macro_event_inside_24h_also_vetoes(self):
        row = self._evaluate(event_hours=6.0)
        self.assertEqual(row["veto"], "event_blackout")

    def test_the_nearest_binary_event_is_the_one_that_gates(self):
        row = self._evaluate(catalyst={"score": 60.0, "hours_to_next_earnings": 100},
                             event_hours=200.0)
        self.assertEqual(row["hours_to_binary_event"], 100)
        self.assertIsNone(row["veto"])

    # -- request economy (2026-08-31: faireconomy answered 429 after the
    #    calendar was fetched once PER SYMBOL — ~112 requests in a day) ----
    def test_market_level_feeds_fetch_once_per_pass_not_per_symbol(self):
        calls = {"calendar": 0, "macro": 0, "gauge": 0, "benchmark": 0}

        def count(key, value):
            def _fn(*a, **k):
                calls[key] += 1
                return value
            return _fn

        with patch.object(swing_pipeline, "fetch_candles",
                          lambda symbol, market: _rising_candles()), \
             patch.object(swing_pipeline, "fetch_benchmark_candles",
                          count("benchmark", _rising_candles())), \
             patch.object(swing_pipeline, "fetch_macro",
                          count("macro", {"vix": 14.0, "vix_5d_ago": 16.0,
                                          "y10": 4.0, "y10_5d_ago": 4.2,
                                          "dxy": 99.0, "dxy_5d_ago": 100.0})), \
             patch.object(swing_pipeline, "fetch_fear_greed",
                          count("gauge", {"value": 20.0, "avg_7d": 15.0})), \
             patch.object(swing_pipeline, "fetch_catalyst",
                          lambda symbol: {"score": 60.0,
                                          "hours_to_next_earnings": None}), \
             patch.object(swing_pipeline, "fetch_filings",
                          lambda symbol: {"score": 40.0}), \
             patch.object(swing_pipeline, "fetch_macro_event_hours",
                          count("calendar", None)):
            result = swing_pipeline.run_pipeline(
                ["NVDA", "AMD", "MSFT"], market="us-stock")
        self.assertEqual(result["evaluated"], 3)
        # one fetch per PASS for every symbol-independent feed
        self.assertEqual(calls, {"calendar": 1, "macro": 1,
                                 "gauge": 1, "benchmark": 1})

    # -- persistence -----------------------------------------------------
    def test_run_persists_one_decision_row_per_symbol(self):
        with patch.object(swing_pipeline, "evaluate_symbol",
                          lambda symbol, market, **kw: {
                              "symbol": symbol, "market": market,
                              "scores": {"sentiment": 1.0, "macro": None, "thesis": None,
                                         "smart_money": None, "technical": 2.0},
                              "composite": 12.0, "axis": "NEUTRAL", "action": "WAIT",
                              "veto": None, "reason": "test", "coverage": 2,
                              "hours_to_binary_event": None, "detail": {},
                          }):
            result = swing_pipeline.run_pipeline(["AAA", "BBB"], market="us-stock")
        self.assertEqual(result["evaluated"], 2)
        latest = swing_pipeline.latest_decisions()
        self.assertEqual({r["symbol"] for r in latest}, {"AAA", "BBB"})
        self.assertEqual(latest[0]["action"], "WAIT")

    def test_latest_decisions_returns_only_the_newest_row_per_symbol(self):
        for composite in (10.0, 50.0):
            swing_pipeline._persist({
                "symbol": "AAA", "market": "us-stock",
                "scores": {"sentiment": None, "macro": None, "thesis": None,
                           "smart_money": None, "technical": composite},
                "composite": composite, "axis": "NEUTRAL", "action": "WAIT",
                "veto": None, "reason": "", "coverage": 1,
                "hours_to_binary_event": None, "detail": {},
            })
        latest = swing_pipeline.latest_decisions()
        self.assertEqual(len(latest), 1)
        self.assertEqual(latest[0]["composite"], 50.0)
        self.assertEqual(len(swing_pipeline.decision_history("AAA")), 2)

    def test_a_symbol_that_explodes_does_not_abort_the_pass(self):
        def flaky(symbol, market, **kw):
            if symbol == "BAD":
                raise RuntimeError("upstream down")
            return {
                "symbol": symbol, "market": market,
                "scores": {"sentiment": None, "macro": None, "thesis": None,
                           "smart_money": None, "technical": 5.0},
                "composite": 5.0, "axis": "NEUTRAL", "action": "WAIT",
                "veto": None, "reason": "", "coverage": 1,
                "hours_to_binary_event": None, "detail": {},
            }

        with patch.object(swing_pipeline, "evaluate_symbol", flaky):
            result = swing_pipeline.run_pipeline(["BAD", "GOOD"], market="us-stock")
        self.assertEqual(result["evaluated"], 1)
        self.assertEqual(result["failed"], 1)
        self.assertEqual([r["symbol"] for r in swing_pipeline.latest_decisions()], ["GOOD"])

    def test_the_pass_is_recorded_for_the_console(self):
        with patch.object(swing_pipeline, "evaluate_symbol",
                          lambda symbol, market, **kw: {
                              "symbol": symbol, "market": market,
                              "scores": {"sentiment": None, "macro": None, "thesis": None,
                                         "smart_money": None, "technical": 5.0},
                              "composite": 5.0, "axis": "NEUTRAL", "action": "WAIT",
                              "veto": None, "reason": "", "coverage": 1,
                              "hours_to_binary_event": None, "detail": {},
                          }):
            swing_pipeline.run_pipeline(["AAA"], market="us-stock")
        rows = crawl_monitor.recent_runs(feed="pipeline")
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["ok"])
        self.assertEqual(rows[0]["items"], 1)

    # -- disabled feeds --------------------------------------------------
    def test_a_disabled_feed_is_not_recorded_as_a_healthy_pass(self):
        """An env-gated-off collector produces nothing; recording it as
        `ok, 1 item` paints a non-producing feed green — the exact failure
        this monitoring exists to catch (reproduced in the console 2026-08-30).
        """
        self._evaluate(catalyst={"score": None, "hours_to_next_earnings": None,
                                 "disabled": True},
                       filings={"score": None, "disabled": True})
        for feed in (swing_pipeline.FEED_CATALYST, swing_pipeline.FEED_FILINGS):
            row = crawl_monitor.recent_runs(feed=feed)[0]
            self.assertEqual(row["items"], 0, feed)
            self.assertTrue(row["detail"].get("disabled"), feed)

    def test_an_enabled_feed_with_data_still_counts_an_item(self):
        self._evaluate()
        row = crawl_monitor.recent_runs(feed=swing_pipeline.FEED_CATALYST)[0]
        self.assertEqual(row["items"], 1)
        self.assertFalse(row["detail"].get("disabled"))

    # -- sentiment blend (shadow / live) ---------------------------------
    def _evaluate_blend(self, mode, news=None, social=None, **kw):
        news = news if news is not None else {"score": -100.0, "articles": 10}
        social = social if social is not None else {"score": -100.0, "posts": 20}
        with patch.dict(os.environ, {"SWING_SENTIMENT_BLEND": mode}), \
             patch.object(swing_pipeline, "fetch_news_sentiment", lambda s: news), \
             patch.object(swing_pipeline, "fetch_social_sentiment", lambda s: social):
            return self._evaluate(**kw)

    def test_off_keeps_the_market_gauge_and_records_no_shadow(self):
        row = self._evaluate_blend("off")
        self.assertEqual(row["scores"]["sentiment"], row["detail"]["sentiment"]["market"])
        self.assertIsNone(row["sentiment_shadow"])

    def test_shadow_decides_on_the_market_gauge_but_records_the_blend(self):
        """Shadow must not change a single decision — it only measures."""
        control = self._evaluate_blend("off")
        shadow = self._evaluate_blend("shadow")
        self.assertEqual(shadow["scores"]["sentiment"], control["scores"]["sentiment"])
        self.assertEqual(shadow["action"], control["action"])
        self.assertIsNotNone(shadow["sentiment_shadow"])
        # bearish news+social pull the blend below the market-only gauge
        self.assertLess(shadow["sentiment_shadow"], shadow["scores"]["sentiment"])

    def test_live_uses_the_blend_and_shadows_the_market_gauge(self):
        row = self._evaluate_blend("live")
        self.assertLess(row["scores"]["sentiment"], row["sentiment_shadow"])

    def test_live_blend_can_actually_flip_the_decision(self):
        """If it could never change an outcome it would not be worth wiring.

        The thesis score is dialled down so the composite sits just above the
        +40 line: with the default fixture every other feed is near maximum,
        so a -71pt sentiment swing still lands at 44.75 and the assertion
        would prove nothing.
        """
        near_threshold = {"catalyst": {"score": 20.0, "hours_to_next_earnings": None}}
        control = self._evaluate_blend("off", **near_threshold)
        live = self._evaluate_blend("live", **near_threshold)
        self.assertEqual(control["action"], "BUY")
        self.assertEqual(control["axis"], "AGREE_BULL")
        self.assertEqual(live["action"], "WAIT")
        # the qualitative axis itself goes flat — the doc's two-axis rule
        self.assertEqual(live["axis"], "NEUTRAL")
        self.assertLess(live["composite"], control["composite"])

    def test_a_thin_sample_leaves_the_blend_equal_to_the_gauge(self):
        row = self._evaluate_blend("shadow",
                                   news={"score": -100.0, "articles": 1},
                                   social={"score": -100.0, "posts": 2})
        self.assertEqual(row["sentiment_shadow"], row["scores"]["sentiment"])

    def test_blend_components_are_recorded_for_diagnosis(self):
        row = self._evaluate_blend("shadow")
        detail = row["detail"]["sentiment"]
        self.assertEqual(detail["mode"], "shadow")
        self.assertEqual(detail["news_articles"], 10)
        self.assertEqual(detail["social_posts"], 20)
        self.assertEqual(detail["news"], -100.0)

    def test_off_does_not_pay_for_reads_it_will_not_use(self):
        calls = {"n": 0}

        def counted(_symbol):
            calls["n"] += 1
            return {"score": 0.0, "articles": 9}

        with patch.dict(os.environ, {"SWING_SENTIMENT_BLEND": "off"}), \
             patch.object(swing_pipeline, "fetch_news_sentiment", counted), \
             patch.object(swing_pipeline, "fetch_social_sentiment", counted):
            self._evaluate()
        self.assertEqual(calls["n"], 0)

    def test_shadow_is_persisted_with_the_decision(self):
        swing_pipeline._persist({
            "symbol": "AAA", "market": "us-stock",
            "scores": {"sentiment": 20.0, "macro": None, "thesis": None,
                       "smart_money": None, "technical": 30.0},
            "composite": 25.0, "axis": "NEUTRAL", "action": "WAIT",
            "veto": None, "reason": "", "coverage": 2,
            "hours_to_binary_event": None, "sentiment_shadow": -12.5, "detail": {},
        })
        self.assertEqual(swing_pipeline.latest_decisions()[0]["sentiment_shadow"], -12.5)

    def test_an_unknown_mode_falls_back_to_off_rather_than_trading_on_it(self):
        with patch.dict(os.environ, {"SWING_SENTIMENT_BLEND": "nonsense"}):
            self.assertEqual(swing_pipeline.sentiment_blend_mode(), "off")

    # -- loop housekeeping -----------------------------------------------
    def test_retention_prune_runs_even_while_the_pipeline_is_disabled(self):
        """social_feed and market_news write crawl_runs regardless of this
        feature flag, so pruning must not be gated behind it or the table
        grows forever whenever the pipeline is off."""
        import asyncio
        calls = {"pruned": 0, "ran": 0}

        async def fake_sleep(_):
            raise _StopLoop()

        with patch.object(swing_pipeline, "enabled", lambda: False), \
             patch.object(swing_pipeline.crawl_monitor, "prune",
                          lambda *a, **k: calls.__setitem__("pruned", calls["pruned"] + 1)), \
             patch.object(swing_pipeline, "run_pipeline",
                          lambda *a, **k: calls.__setitem__("ran", calls["ran"] + 1)), \
             patch.object(swing_pipeline.asyncio, "sleep", fake_sleep):
            with self.assertRaises(_StopLoop):
                asyncio.run(swing_pipeline.swing_pipeline_loop())

        self.assertEqual(calls["pruned"], 1)
        self.assertEqual(calls["ran"], 0)

    # -- config ----------------------------------------------------------
    def test_disabled_by_default(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SWING_PIPELINE_ENABLED", None)
            self.assertFalse(swing_pipeline.enabled())

    def test_symbol_list_comes_from_env(self):
        with patch.dict(os.environ, {"SWING_PIPELINE_SYMBOLS": "NVDA, aapl ,, MSFT"}):
            self.assertEqual(swing_pipeline.configured_symbols(), ["NVDA", "AAPL", "MSFT"])


if __name__ == "__main__":
    unittest.main()
