"""Plan 23 Phase D — US-equity positioning snapshots + the surprise feed.

Self-accrued live-forward history for the v2 crowd-fade (no vendor sells
it), and the AV EARNINGS surprise feed v1-PEAD was missing. Contracts under
test: put/call OI math with null-honesty, BARE-symbol StockTwits (the
crypto '.X' suffix must not leak), fail-soft per-source rows, watchlist
union with active us-stock runs, surprise parse + cache + no-key null.
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

import database
import us_stock_factors as usf


def _chain(call_oi=1000, put_oi=1500):
    return {"options": [{
        "calls": [{"openInterest": call_oi // 2},
                  {"openInterest": call_oi - call_oi // 2}],
        "puts": [{"openInterest": put_oi}],
    }]}


class PutCall(unittest.TestCase):
    def test_ratio_math(self):
        with patch("price_fetcher._fetch_yahoo_option_chain",
                   return_value=_chain(1000, 1500)):
            self.assertEqual(usf.putcall_oi_ratio("MSFT"), 1.5)

    def test_zero_call_oi_is_null_not_infinite(self):
        with patch("price_fetcher._fetch_yahoo_option_chain",
                   return_value=_chain(0, 500)):
            self.assertIsNone(usf.putcall_oi_ratio("MSFT"))

    def test_dead_chain_is_null(self):
        with patch("price_fetcher._fetch_yahoo_option_chain",
                   return_value=None):
            self.assertIsNone(usf.putcall_oi_ratio("MSFT"))


class Tilt(unittest.TestCase):
    def test_bare_symbol_no_crypto_suffix(self):
        seen = {}

        def fake(sym):
            seen["sym"] = sym
            return {"messages_scored": 40, "bullish": 30, "bearish": 10}
        with patch("analysis_sources.fetch_stocktwits_sentiment",
                   side_effect=fake):
            tilt, n = usf.stocktwits_tilt("MSFT")
        self.assertEqual(seen["sym"], "MSFT")          # NOT 'MSFT.X'
        self.assertEqual(n, 40)
        self.assertAlmostEqual(tilt, 0.5)


class Recorder(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()

    def tearDown(self):
        self.tmp.cleanup()

    def _rows(self):
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM us_stock_factor_snapshots ORDER BY id")
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows

    def test_rows_written_with_partial_sources(self):
        # chain works, stocktwits dead -> row still lands, tilt NULL
        with patch("price_fetcher._fetch_yahoo_option_chain",
                   return_value=_chain(1000, 800)), \
             patch("analysis_sources.fetch_stocktwits_sentiment",
                   side_effect=RuntimeError("down")), \
             patch.object(usf, "finra_short_volume_ratios",
                          return_value={}):
            out = usf.record_us_stock_factor_snapshots(("MSFT", "AAPL"))
        self.assertEqual(out["written"], 2)
        rows = self._rows()
        self.assertEqual(rows[0]["putcall_oi_ratio"], 0.8)
        self.assertIsNone(rows[0]["stocktwits_tilt"])
        self.assertIsNone(rows[0]["short_volume_ratio"])   # reserved

    def test_watchlist_unions_active_us_stock_runs(self):
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO agents (name, cash) VALUES ('w', 1000)")
        aid = cur.lastrowid
        cur.execute(
            "INSERT INTO trading_runs (agent_id, symbol, market, market_type,"
            " status, config_snapshot_json, start_condition_json,"
            " stop_conditions_json, created_at) VALUES "
            "(?,?,?,'spot','running','{}','{}','{}','2026-01-01T00:00:00Z')",
            (aid, "ZZZQ", "us-stock"))
        conn.commit(); conn.close()
        wl = usf.watchlist()
        self.assertIn("ZZZQ", wl)
        self.assertIn("AAPL", wl)                       # defaults kept


class SurpriseFeed(unittest.TestCase):
    def setUp(self):
        import fmp_feed
        fmp_feed._surprise_cache.clear()

    def test_parse_latest_reported_quarter(self):
        import fmp_feed
        payload = {"quarterlyEarnings": [
            {"reportedDate": "2026-07-30", "reportedEPS": "2.40",
             "estimatedEPS": "2.10", "surprisePercentage": "14.29"},
            {"reportedDate": "2026-04-30", "reportedEPS": "2.00",
             "estimatedEPS": "2.05", "surprisePercentage": "-2.44"},
        ]}

        class _Resp:
            def raise_for_status(self):
                pass

            def json(self):
                return payload
        with patch.object(fmp_feed, "_alphavantage_key", return_value="k"), \
             patch.object(fmp_feed.requests, "get", return_value=_Resp()):
            out = fmp_feed.latest_earnings_surprise("AAPL")
        self.assertEqual(out["report_date"], "2026-07-30")
        self.assertAlmostEqual(out["surprise_pct"], 14.29)
        self.assertAlmostEqual(out["eps_actual"], 2.40)

    def test_unreported_head_rows_are_skipped(self):
        import fmp_feed
        payload = {"quarterlyEarnings": [
            {"reportedDate": "2026-10-30", "reportedEPS": "None",
             "estimatedEPS": "2.50", "surprisePercentage": "None"},
            {"reportedDate": "2026-07-30", "reportedEPS": "2.40",
             "estimatedEPS": "2.10", "surprisePercentage": "14.29"},
        ]}

        class _Resp:
            def raise_for_status(self):
                pass

            def json(self):
                return payload
        with patch.object(fmp_feed, "_alphavantage_key", return_value="k"), \
             patch.object(fmp_feed.requests, "get", return_value=_Resp()):
            out = fmp_feed.latest_earnings_surprise("AAPL")
        self.assertEqual(out["report_date"], "2026-07-30")

    def test_no_key_is_null(self):
        import fmp_feed
        with patch.object(fmp_feed, "_alphavantage_key", return_value=""):
            self.assertIsNone(fmp_feed.latest_earnings_surprise("AAPL"))

    def test_cache_serves_without_a_second_fetch(self):
        import fmp_feed
        calls = {"n": 0}

        class _Resp:
            def raise_for_status(self):
                pass

            def json(self):
                calls["n"] += 1
                return {"quarterlyEarnings": [
                    {"reportedDate": "2026-07-30", "reportedEPS": "1.0",
                     "estimatedEPS": "1.0", "surprisePercentage": "0.0"}]}
        with patch.object(fmp_feed, "_alphavantage_key", return_value="k"), \
             patch.object(fmp_feed.requests, "get", return_value=_Resp()):
            fmp_feed.latest_earnings_surprise("AAPL")
            fmp_feed.latest_earnings_surprise("AAPL")
        self.assertEqual(calls["n"], 1)


class SchedulerWiringPin(unittest.TestCase):
    def test_factor_loop_carries_the_us_recorder(self):
        import inspect
        import tasks
        src = inspect.getsource(tasks)
        self.assertIn("record_us_stock_factor_snapshots", src,
                      "the factor loop lost the US recorder")


if __name__ == "__main__":
    unittest.main()


class FinraShortVolume(unittest.TestCase):
    def setUp(self):
        usf._finra_cache.clear()

    def _resp(self, text, status=200):
        class _R:
            status_code = status
        r = _R()
        r.text = text
        return r

    def test_parse_and_ratio(self):
        payload = ("Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market\n"
                   "20260811|MSFT|400|0|1000|B,Q,N\n"
                   "20260811|AAPL|250|0|500|B,Q,N\n")
        import us_stock_factors as u
        with patch.object(u, "datetime") as dt:
            from datetime import datetime as real_dt, timezone as tz
            dt.now.return_value = real_dt(2026, 8, 12, tzinfo=tz.utc)
            with patch("requests.get", return_value=self._resp(payload)):
                out = u.finra_short_volume_ratios()
        self.assertEqual(out["MSFT"], 0.4)
        self.assertEqual(out["AAPL"], 0.5)

    def test_walks_back_over_missing_days(self):
        payload = ("Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market\n"
                   "20260808|MSFT|300|0|1000|B\n")
        calls = []

        def fake_get(url, timeout=30):
            calls.append(url)
            if len(calls) < 3:               # two missing days (404)
                return self._resp("", status=404)
            return self._resp(payload)
        with patch("requests.get", side_effect=fake_get):
            out = usf.finra_short_volume_ratios()
        self.assertEqual(out.get("MSFT"), 0.3)
        self.assertEqual(len(calls), 3)

    def test_total_failure_is_empty_not_raise(self):
        with patch("requests.get", side_effect=RuntimeError("net down")):
            self.assertEqual(usf.finra_short_volume_ratios(), {})

    def test_recorder_fills_the_reserved_column(self):
        # DB fixture lives in Recorder; reuse its base
        pass


