"""Per-symbol sentiment blend (swing signal stack §1/§4).

The stack's sentiment processor has been MARKET-level since it shipped: it
reads a Fear & Greed gauge, so every symbol gets the same qualitative score on
a given day. social_feed and market_intel already collect per-symbol readings
but feed nothing. These tests cover the two pieces that connect them:

  market_intel.news_sentiment_for()   relevance-weighted per-symbol news score
  swing_stack.blended_sentiment_score()  market gauge + news + social

Structural rules under test (not preferences — the blueprint's §1 says
sentiment alone is noisy and manipulable):
  * the market gauge is REQUIRED; a crowd reading alone is never the score
  * per-symbol components can never exceed half the blend
  * a thin sample is NO COVERAGE (None), never a neutral 0
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
import market_intel
import swing_stack


class BlendedSentimentTest(unittest.TestCase):
    """swing_stack.blended_sentiment_score — pure, no I/O."""

    def test_market_only_is_unchanged_from_todays_behaviour(self):
        self.assertEqual(swing_stack.blended_sentiment_score(40.0), 40.0)

    def test_blend_moves_the_score_toward_the_per_symbol_reading(self):
        blended = swing_stack.blended_sentiment_score(
            0.0, news=100.0, social=100.0, news_n=10, social_n=20
        )
        self.assertGreater(blended, 0.0)
        # 0.5*0 + 0.3*100 + 0.2*100 == 50
        self.assertAlmostEqual(blended, 50.0, places=6)

    def test_two_symbols_with_the_same_gauge_can_disagree(self):
        """The entire point: sentiment stops being identical per symbol."""
        bull = swing_stack.blended_sentiment_score(10.0, news=80.0, news_n=5)
        bear = swing_stack.blended_sentiment_score(10.0, news=-80.0, news_n=5)
        self.assertGreater(bull, bear)

    # -- structural guarantees -------------------------------------------
    def test_the_market_gauge_is_required(self):
        """A crowd reading with no market anchor must not become the score."""
        self.assertIsNone(
            swing_stack.blended_sentiment_score(None, news=90.0, social=90.0,
                                                news_n=50, social_n=50)
        )

    def test_per_symbol_components_can_never_exceed_half_the_blend(self):
        with patch.object(swing_stack, "SENTIMENT_W_NEWS", 5.0), \
             patch.object(swing_stack, "SENTIMENT_W_SOCIAL", 5.0):
            blended = swing_stack.blended_sentiment_score(
                0.0, news=100.0, social=100.0, news_n=10, social_n=10
            )
        # capped at half, so a runaway weight edit cannot let the crowd lead
        self.assertAlmostEqual(blended, 50.0, places=6)

    # -- sample gates ----------------------------------------------------
    def test_a_thin_news_sample_is_dropped_not_counted_as_zero(self):
        thin = swing_stack.blended_sentiment_score(40.0, news=-100.0, news_n=1)
        self.assertEqual(thin, 40.0)

    def test_a_thin_social_sample_is_dropped_not_counted_as_zero(self):
        thin = swing_stack.blended_sentiment_score(40.0, social=-100.0, social_n=2)
        self.assertEqual(thin, 40.0)

    def test_a_sufficient_sample_is_admitted(self):
        thick = swing_stack.blended_sentiment_score(
            40.0, social=-100.0, social_n=swing_stack.MIN_SOCIAL_POSTS
        )
        self.assertLess(thick, 40.0)

    def test_none_components_renormalize_away(self):
        self.assertEqual(
            swing_stack.blended_sentiment_score(30.0, news=None, social=None), 30.0
        )

    def test_result_stays_inside_the_score_scale(self):
        self.assertLessEqual(
            swing_stack.blended_sentiment_score(100.0, news=100.0, social=100.0,
                                                news_n=9, social_n=9), 100.0)
        self.assertGreaterEqual(
            swing_stack.blended_sentiment_score(-100.0, news=-100.0, social=-100.0,
                                                news_n=9, social_n=9), -100.0)


class ExistingDatabaseGetsTheShadowColumnTest(unittest.TestCase):
    """CREATE TABLE IF NOT EXISTS never adds a column to a table that already
    exists, so a SQLite database created before this change would keep the old
    swing_decisions shape and every insert would fail. Prod MySQL is covered by
    alembic 0056; dev SQLite needs the ALTER in init_database."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "old.db")
        database.init_database()

    def tearDown(self):
        self.tmp.cleanup()

    def _columns(self):
        with database.get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM swing_decisions LIMIT 0")
            return {d[0] for d in cur.description}

    def test_an_older_table_is_upgraded_in_place(self):
        with database.get_db_connection() as conn:
            conn.cursor().execute(
                "ALTER TABLE swing_decisions DROP COLUMN sentiment_shadow")
            conn.commit()
        self.assertNotIn("sentiment_shadow", self._columns())

        database.init_database()
        self.assertIn("sentiment_shadow", self._columns())

    def test_reinitialising_a_current_database_is_a_no_op(self):
        database.init_database()
        self.assertIn("sentiment_shadow", self._columns())


class NewsSentimentForTest(unittest.TestCase):
    """market_intel.news_sentiment_for — reads snapshots we already store."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()

    def tearDown(self):
        self.tmp.cleanup()

    def _store(self, category: str, items: list[dict]):
        with database.get_db_connection() as conn:
            conn.cursor().execute(
                """INSERT INTO market_news_snapshots
                   (category, snapshot_key, items_json, summary_json, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (category, f"{category}:k", json.dumps(items), "{}",
                 "2026-08-30T00:00:00Z"),
            )
            conn.commit()

    @staticmethod
    def _item(tickers):
        return {"title": "t", "ticker_sentiment": [
            {"ticker": t, "relevance_score": rel, "sentiment_score": s}
            for t, rel, s in tickers
        ]}

    def test_no_snapshot_is_no_coverage(self):
        read = market_intel.news_sentiment_for("NVDA")
        self.assertIsNone(read["score"])
        self.assertEqual(read["articles"], 0)

    def test_scores_only_the_requested_symbol(self):
        self._store("equities", [
            self._item([("NVDA", 0.9, 0.35), ("AMD", 0.9, -0.35)]),
            self._item([("AMD", 0.9, -0.35)]),
        ])
        read = market_intel.news_sentiment_for("NVDA")
        self.assertEqual(read["articles"], 1)
        self.assertEqual(read["score"], 100.0)

    def test_relevance_weights_the_mean(self):
        """A passing mention must not outvote the article that is about it."""
        self._store("equities", [
            self._item([("NVDA", 1.0, 0.35)]),
            self._item([("NVDA", 0.01, -0.35)]),
        ])
        read = market_intel.news_sentiment_for("NVDA")
        self.assertGreater(read["score"], 90.0)

    def test_alpha_vantage_label_boundary_maps_to_full_scale(self):
        """AV calls >= 0.35 'Bullish'; raw *100 would under-read it as 35."""
        self._store("equities", [self._item([("NVDA", 1.0, 0.35)])])
        self.assertEqual(market_intel.news_sentiment_for("NVDA")["score"], 100.0)

    def test_extreme_vendor_scores_clamp(self):
        self._store("equities", [self._item([("NVDA", 1.0, 0.95)])])
        self.assertEqual(market_intel.news_sentiment_for("NVDA")["score"], 100.0)

    def test_articles_across_categories_are_pooled(self):
        self._store("equities", [self._item([("NVDA", 1.0, 0.35)])])
        self._store("macro", [self._item([("NVDA", 1.0, 0.35)])])
        self.assertEqual(market_intel.news_sentiment_for("NVDA")["articles"], 2)

    def test_only_the_newest_snapshot_per_category_counts(self):
        self._store("equities", [self._item([("NVDA", 1.0, -0.35)])])
        with database.get_db_connection() as conn:
            conn.cursor().execute(
                """INSERT INTO market_news_snapshots
                   (category, snapshot_key, items_json, summary_json, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                ("equities", "equities:k2",
                 json.dumps([self._item([("NVDA", 1.0, 0.35)])]), "{}",
                 "2026-08-31T00:00:00Z"),
            )
            conn.commit()
        read = market_intel.news_sentiment_for("NVDA")
        self.assertEqual(read["articles"], 1)
        self.assertEqual(read["score"], 100.0)

    def test_malformed_entries_are_skipped_not_fatal(self):
        self._store("equities", [
            {"ticker_sentiment": [{"ticker": "NVDA", "relevance_score": "x",
                                   "sentiment_score": "y"}]},
            self._item([("NVDA", 1.0, 0.35)]),
        ])
        read = market_intel.news_sentiment_for("NVDA")
        self.assertEqual(read["articles"], 1)

    def test_zero_total_relevance_is_no_coverage(self):
        self._store("equities", [self._item([("NVDA", 0.0, 0.35)])])
        self.assertIsNone(market_intel.news_sentiment_for("NVDA")["score"])


if __name__ == "__main__":
    unittest.main()
