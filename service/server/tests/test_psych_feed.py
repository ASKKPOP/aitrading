"""Psych feed (Phase 2) — F&G, sentiment spikes, shock proxy, Polymarket odds Δ.

Covers the phase acceptance criteria:
  - the real F&G value flows into the payload and the sentiment analyst
  - a negative sentiment z-spike (|z| ≥ 2) is recorded as an event
  - odds changes (0.61 → 0.68 style) are queryable as Δ%
  - the shock proxy is always labeled estimated
"""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
from routes import create_app


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


FNG_FIXTURE = {
    "value": 25, "classification": "Extreme Fear", "delta_3d": 3,
    "history": [{"value": 25, "classification": "Extreme Fear", "timestamp": 1784073600}],
    "source": "alternative.me",
}


def _flat_candles(n=30, close=100.0, volume=50.0):
    base_ts = 1784000000000
    return [{"ts": base_ts + i * 3600_000, "open": close, "high": close,
             "low": close, "close": close, "volume": volume} for i in range(n)]


class PsychFeedTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _seed_news_snapshots(self, category: str, scores: list[float]):
        """One market_news_snapshots row per score, hourly apart, oldest first."""
        start = datetime.now(timezone.utc) - timedelta(hours=len(scores))
        conn = database.get_db_connection()
        cursor = conn.cursor()
        for i, score in enumerate(scores):
            created = _iso(start + timedelta(hours=i))
            items = [{"title": f"item-{i}", "overall_sentiment_score": score}]
            cursor.execute(
                """INSERT INTO market_news_snapshots
                   (category, snapshot_key, items_json, summary_json, created_at)
                   VALUES (?, ?, ?, '{}', ?)""",
                (category, f"{category}:{created}", json.dumps(items), created),
            )
        conn.commit()
        conn.close()

    def _refresh(self, anticipation=None):
        """Run refresh_psych_snapshot with all external fetches mocked."""
        gamma = []
        for m in anticipation or []:
            gamma.append({
                "slug": m["slug"], "question": m.get("title", m["slug"]),
                "volume24hr": 1000,
                "outcomes": json.dumps(list(m["odds"].keys())),
                "outcomePrices": json.dumps([str(v) for v in m["odds"].values()]),
            })
        from psych_feed import refresh_psych_snapshot
        with patch("psych_feed.fetch_fear_greed", return_value=dict(FNG_FIXTURE)), \
             patch("crypto_feed.fetch_candles", return_value=_flat_candles()), \
             patch("price_fetcher._polymarket_get_json", return_value=gamma):
            return refresh_psych_snapshot()


# ── fear & greed ──────────────────────────────────────────────────────────

class FearGreedTests(unittest.TestCase):
    def test_fetch_fear_greed_parses_api_response(self):
        from psych_feed import fetch_fear_greed

        class FakeResp:
            def raise_for_status(self):
                pass
            def json(self):
                return {"data": [
                    {"value": "25", "value_classification": "Extreme Fear", "timestamp": "1784073600"},
                    {"value": "22", "value_classification": "Extreme Fear", "timestamp": "1783987200"},
                    {"value": "28", "value_classification": "Fear", "timestamp": "1783900800"},
                    {"value": "31", "value_classification": "Fear", "timestamp": "1783814400"},
                ]}

        with patch("psych_feed.requests.get", return_value=FakeResp()):
            fng = fetch_fear_greed()
        self.assertEqual(fng["value"], 25)
        self.assertEqual(fng["classification"], "Extreme Fear")
        self.assertEqual(fng["delta_3d"], 25 - 31)
        self.assertEqual(len(fng["history"]), 4)


# ── sentiment spikes ──────────────────────────────────────────────────────

class SentimentSpikeTests(PsychFeedTestCase):
    def test_negative_spike_detected_with_z_score(self):
        from psych_feed import compute_sentiment_spikes
        # Stable slightly-positive series, then a plunge in the latest snapshot.
        self._seed_news_snapshots("global", [0.20, 0.22, 0.18, 0.21, 0.19, 0.20, -0.40])
        spikes = compute_sentiment_spikes()
        self.assertEqual(len(spikes), 1)
        spike = spikes[0]
        self.assertEqual(spike["category"], "global")
        self.assertTrue(spike["spike"])
        self.assertEqual(spike["direction"], "negative")
        self.assertLessEqual(spike["z"], -2.0)

    def test_stable_series_is_not_a_spike(self):
        from psych_feed import compute_sentiment_spikes
        self._seed_news_snapshots("global", [0.20, 0.10, 0.25, 0.15, 0.22, 0.18])
        spikes = compute_sentiment_spikes()
        self.assertEqual(len(spikes), 1)
        self.assertFalse(spikes[0]["spike"])

    def test_too_little_history_yields_nothing(self):
        from psych_feed import compute_sentiment_spikes
        self._seed_news_snapshots("global", [0.2, 0.2, -0.5])
        self.assertEqual(compute_sentiment_spikes(), [])

    def test_refresh_records_negative_spike_as_event(self):
        self._seed_news_snapshots("global", [0.20, 0.22, 0.18, 0.21, 0.19, 0.20, -0.40])
        result = self._refresh()
        self.assertEqual(result["spike_events_recorded"], 1)
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT event_type, metadata_json FROM experiment_events WHERE event_type = 'psych_sentiment_spike'")
        rows = cursor.fetchall()
        conn.close()
        self.assertEqual(len(rows), 1)
        meta = json.loads(rows[0]["metadata_json"])
        self.assertEqual(meta["category"], "global")
        self.assertLessEqual(meta["z"], -2.0)


# ── shock proxy ───────────────────────────────────────────────────────────

class ShockProxyTests(unittest.TestCase):
    def test_shock_detected_on_3sigma_move_with_volume(self):
        from psych_feed import compute_shock_proxy
        # 29 gently alternating hours (~±0.1% returns), then a −5% hour on 5× volume.
        candles = []
        price = 100.0
        for i in range(29):
            price *= 1.001 if i % 2 == 0 else 0.999
            candles.append({"ts": i, "open": price, "high": price, "low": price,
                            "close": price, "volume": 50.0})
        candles.append({"ts": 29, "open": price, "high": price, "low": price * 0.95,
                        "close": price * 0.95, "volume": 250.0})
        proxy = compute_shock_proxy(candles, "BTCUSDT")
        self.assertIsNotNone(proxy)
        self.assertTrue(proxy["shock"])
        self.assertGreaterEqual(proxy["sigma_multiple"], 3.0)
        self.assertGreaterEqual(proxy["volume_ratio"], 2.0)
        self.assertTrue(proxy["estimated"])  # honest-proxy label is mandatory

    def test_calm_market_is_not_a_shock(self):
        from psych_feed import compute_shock_proxy
        candles = []
        price = 100.0
        for i in range(30):
            price *= 1.001 if i % 2 == 0 else 0.999
            candles.append({"ts": i, "open": price, "high": price, "low": price,
                            "close": price, "volume": 50.0})
        proxy = compute_shock_proxy(candles, "BTCUSDT")
        self.assertIsNotNone(proxy)
        self.assertFalse(proxy["shock"])

    def test_insufficient_candles_returns_none(self):
        from psych_feed import compute_shock_proxy
        self.assertIsNone(compute_shock_proxy(_flat_candles(10), "BTCUSDT"))


# ── anticipation (odds deltas) ────────────────────────────────────────────

class OddsDeltaTests(unittest.TestCase):
    def test_odds_delta_pct_between_snapshots(self):
        from psych_feed import compute_odds_deltas
        previous = [{"slug": "m1", "title": "M1", "odds": {"Yes": 0.61, "No": 0.39}}]
        latest = [{"slug": "m1", "title": "M1", "odds": {"Yes": 0.68, "No": 0.32}}]
        deltas = compute_odds_deltas(latest, previous)
        yes = next(d for d in deltas if d["outcome"] == "Yes")
        self.assertAlmostEqual(yes["odds_from"], 0.61)
        self.assertAlmostEqual(yes["odds_to"], 0.68)
        self.assertAlmostEqual(yes["delta"], 0.07)
        self.assertAlmostEqual(yes["delta_pct"], 11.48, places=2)

    def test_unmatched_markets_are_skipped(self):
        from psych_feed import compute_odds_deltas
        deltas = compute_odds_deltas([{"slug": "new", "odds": {"Yes": 0.5}}],
                                     [{"slug": "old", "odds": {"Yes": 0.4}}])
        self.assertEqual(deltas, [])


# ── refresh + payload + API ───────────────────────────────────────────────

class PayloadTests(PsychFeedTestCase):
    def test_payload_unavailable_before_first_snapshot(self):
        from psych_feed import get_psych_payload
        payload = get_psych_payload()
        self.assertFalse(payload["available"])

    def test_refresh_and_payload_roundtrip_with_odds_deltas(self):
        from psych_feed import get_psych_payload
        self._refresh(anticipation=[{"slug": "m1", "title": "M1", "odds": {"Yes": 0.61}}])
        self._refresh(anticipation=[{"slug": "m1", "title": "M1", "odds": {"Yes": 0.68}}])
        payload = get_psych_payload()
        self.assertTrue(payload["available"])
        self.assertEqual(payload["fear_greed"]["value"], 25)
        self.assertEqual(payload["fear_greed"]["classification"], "Extreme Fear")
        self.assertIn("estimated", payload["shock_note"])
        yes = next(d for d in payload["odds_deltas"] if d["outcome"] == "Yes")
        self.assertAlmostEqual(yes["delta"], 0.07)
        # shock proxies present for both symbols, each labeled estimated
        self.assertEqual(len(payload["shock"]), 2)
        self.assertTrue(all(s["estimated"] for s in payload["shock"]))

    def test_refresh_fails_soft_when_sources_error(self):
        from psych_feed import refresh_psych_snapshot, get_psych_payload
        with patch("psych_feed.fetch_fear_greed", side_effect=RuntimeError("down")), \
             patch("crypto_feed.fetch_candles", side_effect=RuntimeError("down")), \
             patch("price_fetcher._polymarket_get_json", side_effect=RuntimeError("down")):
            result = refresh_psych_snapshot()
        self.assertIn("fear_greed", result["errors"])
        payload = get_psych_payload()
        self.assertTrue(payload["available"])  # partial snapshot still stored
        self.assertIsNone(payload["fear_greed"])

    def test_api_route_serves_payload(self):
        client = TestClient(create_app())
        resp = client.get("/api/market-intel/psych")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()["available"])
        self._refresh()
        resp = client.get("/api/market-intel/psych")
        self.assertTrue(resp.json()["available"])
        self.assertEqual(resp.json()["fear_greed"]["value"], 25)


# ── analyst integration ───────────────────────────────────────────────────

class SentimentAnalystIntegrationTests(PsychFeedTestCase):
    def test_gather_sentiment_includes_psych_feed(self):
        self._seed_news_snapshots("global", [0.20, 0.22, 0.18, 0.21, 0.19, 0.20, -0.40])
        self._refresh()
        from analysis_agents import _gather_sentiment
        out = _gather_sentiment("BTC", "crypto", {"sentiment_breakdown": {}})
        self.assertIn("psych", out)
        self.assertEqual(out["psych"]["fear_greed"]["value"], 25)
        self.assertTrue(any(s["direction"] == "negative" for s in out["psych"]["spikes"]))

    def test_fallback_brief_mentions_fear_greed(self):
        from analysis_agents import _fallback_brief
        brief = _fallback_brief("Sentiment Analyst", {
            "from_news": {"bullish": 2, "bearish": 1},
            "psych": {"fear_greed": {"value": 25, "classification": "Extreme Fear"},
                      "spikes": []},
        })
        self.assertIn("Fear & Greed 25", brief)
        self.assertIn("Extreme Fear", brief)


if __name__ == "__main__":
    unittest.main()
