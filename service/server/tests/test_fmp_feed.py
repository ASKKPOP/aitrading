"""Plan 21 P6 — FMP earnings feed, key-gated with degraded mode.

Without FMP_API_KEY every reader is empty and the research prompt is
byte-identical to the keyless world; with a key, us-stock candidates carry
days_to_earnings and the prompt explains the field. Fetches are mocked —
no live HTTP (the quant-crypto live-data-leak lesson).
"""

from __future__ import annotations

import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import fmp_feed
import symbol_research as sr


def _resp(payload, status=200):
    class R:
        def raise_for_status(self):
            if status >= 400:
                raise RuntimeError(f"http {status}")

        def json(self):
            return payload
    return R()


def _in_days(n: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=n)).strftime("%Y-%m-%d")


class _Cache(unittest.TestCase):
    def setUp(self):
        fmp_feed._cache["at"] = 0.0
        fmp_feed._cache["by_symbol"] = None

    tearDown = setUp


class KeyGateTests(_Cache):
    def test_disabled_without_key(self):
        with patch.dict(os.environ, {"FMP_API_KEY": ""}):
            self.assertFalse(fmp_feed.fmp_enabled())
            with patch("fmp_feed.requests.get",
                       side_effect=AssertionError("must not call")):
                self.assertEqual(fmp_feed.upcoming_earnings(), {})
                self.assertIsNone(fmp_feed.days_to_earnings("AAPL"))

    def test_enabled_fetches_and_caches(self):
        payload = [{"symbol": "AAPL", "date": _in_days(3)},
                   {"symbol": "AAPL", "date": _in_days(95)},  # later dupe loses
                   {"symbol": "NVDA", "date": _in_days(9)}]
        with patch.dict(os.environ, {"FMP_API_KEY": "k"}), \
             patch("fmp_feed.requests.get", return_value=_resp(payload)) as get:
            self.assertEqual(fmp_feed.days_to_earnings("AAPL"), 3)
            self.assertEqual(fmp_feed.days_to_earnings("nvda"), 9)
            self.assertIsNone(fmp_feed.days_to_earnings("TSLA"))
            self.assertEqual(get.call_count, 1, "second read must hit the cache")

    def test_fetch_failure_serves_stale(self):
        fmp_feed._cache["by_symbol"] = {"AAPL": _in_days(2)}
        fmp_feed._cache["at"] = -1e9  # expired
        with patch.dict(os.environ, {"FMP_API_KEY": "k"}), \
             patch("fmp_feed.requests.get", side_effect=RuntimeError("down")):
            self.assertEqual(fmp_feed.days_to_earnings("AAPL"), 2)

    def test_past_or_garbage_dates_are_none(self):
        fmp_feed._cache["by_symbol"] = {"OLD": "2020-01-01", "BAD": "not-a-date"}
        fmp_feed._cache["at"] = 1e18
        with patch.dict(os.environ, {"FMP_API_KEY": "k"}):
            self.assertIsNone(fmp_feed.days_to_earnings("OLD"))
            self.assertIsNone(fmp_feed.days_to_earnings("BAD"))


class ResearchEnrichmentTests(_Cache):
    def _survivor(self, market="us-stock", symbol="NVDA"):
        return {
            "symbol": symbol, "market": market, "eps_raw": 1.0,
            "momentum_sign": 1.0, "session_open": True,
            "factors": {"last": 500.0, "mom_5d": 3.0, "mom_20d": 4.0,
                        "vol_daily_pct": 2.0, "vol_ratio": 1.1},
        }

    def _prompt(self, survivor, dte):
        seen = {}

        def fake_generate(prompt, **kw):
            seen["p"] = prompt
            return (f'[{{"symbol":"{survivor["symbol"]}",'
                    f'"market":"{survivor["market"]}","direction":"long",'
                    '"expected_move_pct":2.0,"horizon_hours":24,'
                    '"confidence":0.6,"thesis":"t","risks":"r",'
                    '"invalidation":"below the recent swing low"}]')

        with patch.object(sr, "_previous_thesis", return_value=None), \
             patch("regime.evaluate_crypto_composite", return_value=None), \
             patch("fmp_feed.days_to_earnings", return_value=dte):
            sr.generate_theses([survivor], generate_text=fake_generate)
        return seen.get("p", "")

    def test_us_stock_row_carries_days_to_earnings(self):
        prompt = self._prompt(self._survivor(), dte=4)
        self.assertIn('"days_to_earnings": 4', prompt)
        self.assertIn("holding-through-print", prompt)

    def test_no_key_prompt_is_unchanged(self):
        prompt = self._prompt(self._survivor(), dte=None)
        self.assertNotIn("days_to_earnings", prompt)
        self.assertNotIn("holding-through-print", prompt)

    def test_crypto_rows_never_query_fmp(self):
        with patch.object(sr, "_previous_thesis", return_value=None), \
             patch("regime.evaluate_crypto_composite", return_value=None), \
             patch("fmp_feed.days_to_earnings",
                   side_effect=AssertionError("crypto must not query FMP")):
            sr.generate_theses(
                [self._survivor(market="crypto", symbol="BTCUSDT")],
                generate_text=lambda p, **kw: (
                    '[{"symbol":"BTCUSDT","market":"crypto","direction":"long",'
                    '"expected_move_pct":2.0,"horizon_hours":24,'
                    '"confidence":0.6,"thesis":"t","risks":"r",'
                    '"invalidation":"below the recent swing low"}]'))


if __name__ == "__main__":
    unittest.main()
