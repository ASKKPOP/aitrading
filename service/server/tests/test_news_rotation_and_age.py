"""Market-news refresh rotation + news-age visibility in the analysis brief.

The 4-category sweep spent 4 Alpha Vantage calls per refresh against the
SHARED 25/day free key; late-day sweeps failed all-or-nothing (prod
2026-08-08: two consecutive `inserted=0 errors=4` sweeps, crypto 38h stale).
The refresh now touches ONE category per sweep, stalest first — and because
the feed can legitimately be hours old, the analysis brief must state the
snapshot's age so the analyst (the sooppiy AI, not the platform) decides how
much a stale headline is worth.
"""
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
import market_intel
from analysis_agents import _fallback_brief


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


class NewsRotationTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _seed(self, category: str, age_hours: float) -> None:
        created = _iso(datetime.now(timezone.utc) - timedelta(hours=age_hours))
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO market_news_snapshots
               (category, snapshot_key, items_json, summary_json, created_at)
               VALUES (?, ?, '[]', '{}', ?)""",
            (category, f"{category}:{created}", created),
        )
        conn.commit()
        conn.close()

    def test_refresh_touches_only_the_stalest_category(self):
        # crypto is stalest by far; the other three are fresh.
        self._seed("crypto", age_hours=38)
        self._seed("equities", age_hours=1)
        self._seed("macro", age_hours=2)
        self._seed("commodities", age_hours=3)
        fetched: list[str] = []

        def fake_fetch(category, definition):
            fetched.append(category)
            return [{"title": "t", "overall_sentiment_label": "Neutral",
                    "time_published": "20260808T050000"}]

        with patch.object(market_intel, "_fetch_news_feed", side_effect=fake_fetch):
            out = market_intel.refresh_market_news_snapshots()
        self.assertEqual(fetched, ["crypto"])
        self.assertEqual(out["inserted_categories"], 1)
        self.assertEqual(out["errors"], {})

    def test_a_category_with_no_snapshot_at_all_goes_first(self):
        # A never-fetched category is infinitely stale — it must win even
        # against a very old row.
        self._seed("crypto", age_hours=100)
        fetched: list[str] = []

        def fake_fetch(category, definition):
            fetched.append(category)
            return [{"title": "t", "overall_sentiment_label": "Neutral",
                    "time_published": "20260808T050000"}]

        with patch.object(market_intel, "_fetch_news_feed", side_effect=fake_fetch):
            market_intel.refresh_market_news_snapshots()
        self.assertEqual(len(fetched), 1)
        self.assertNotEqual(fetched[0], "crypto")


class NewsAgeInBriefTestCase(unittest.TestCase):
    def test_stale_snapshot_age_is_stated(self):
        as_of = _iso(datetime.now(timezone.utc) - timedelta(hours=25))
        msg = _fallback_brief("news", {
            "items": [{"title": "Fed holds"}],
            "sentiment_breakdown": {"bullish": 1},
            "as_of": as_of,
        })
        self.assertIn("h old", msg)
        self.assertIn("25", msg)

    def test_fresh_snapshot_carries_no_age_noise(self):
        as_of = _iso(datetime.now(timezone.utc) - timedelta(minutes=20))
        msg = _fallback_brief("news", {
            "items": [{"title": "Fed holds"}],
            "sentiment_breakdown": {},
            "as_of": as_of,
        })
        self.assertNotIn("h old", msg)


if __name__ == "__main__":
    unittest.main()
