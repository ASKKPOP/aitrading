"""Which-coin scanner (Phase 4) — volume surge, mention spikes, listings, candidates.

Covers the phase acceptance criteria:
  - candidates return with plain-language reasons (volume x2.4 · mentions +180%)
  - an automation rule with symbol=SCANNER auto-analyzes the top candidate
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
from routes import create_app


def _daily(volumes):
    return [{"ts": i, "open": 1, "high": 1, "low": 1, "close": 1, "volume": v}
            for i, v in enumerate(volumes)]


class ScannerTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _seed_snapshot(self, mentions=None, instruments=None, candidates=None):
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO scanner_snapshots
               (snapshot_key, candidates_json, mentions_json, instruments_json, created_at)
               VALUES (?, ?, ?, ?, datetime('now'))""",
            ("scanner:seed", json.dumps(candidates or []),
             json.dumps(mentions or []), json.dumps(instruments or [])),
        )
        conn.commit()
        conn.close()


# ─── unit math ─────────────────────────────────────────────────────────────

class VolumeRatioTests(unittest.TestCase):
    def test_volume_ratio_vs_7d_average(self):
        from scanner import compute_volume_ratio
        # prior 7 days avg 100, last day 240 → x2.4
        ratio = compute_volume_ratio(_daily([100] * 7 + [240]))
        self.assertAlmostEqual(ratio, 2.4)

    def test_insufficient_history_is_none(self):
        from scanner import compute_volume_ratio
        self.assertIsNone(compute_volume_ratio(_daily([100] * 5)))


class MentionSurgeTests(unittest.TestCase):
    def test_change_pct_vs_baseline(self):
        from scanner import compute_mention_surges
        current = [{"symbol": "BTC", "rate_per_hour": 28.0, "watchers": 1}]
        baselines = {"BTC": [10.0, 10.0, 10.0]}
        surges = compute_mention_surges(current, baselines)
        self.assertEqual(len(surges), 1)
        self.assertAlmostEqual(surges[0]["change_pct"], 180.0)

    def test_needs_min_baseline_points(self):
        from scanner import compute_mention_surges
        current = [{"symbol": "BTC", "rate_per_hour": 28.0, "watchers": 1}]
        self.assertEqual(compute_mention_surges(current, {"BTC": [10.0, 10.0]}), [])


class NewListingTests(unittest.TestCase):
    def test_diff_detects_new_instruments(self):
        from scanner import compute_new_listings
        new = compute_new_listings(["A-USDT-SWAP", "B-USDT-SWAP"], ["A-USDT-SWAP"])
        self.assertEqual(new, ["B-USDT-SWAP"])

    def test_first_scan_reports_nothing(self):
        from scanner import compute_new_listings
        # No previous list → everything would be "new"; report none instead.
        self.assertEqual(compute_new_listings(["A-USDT-SWAP"], []), [])


class AssembleCandidatesTests(unittest.TestCase):
    def test_candidates_carry_reasons_and_rank(self):
        from scanner import assemble_candidates
        candidates = assemble_candidates(
            volume_surges=[{"symbol": "SOLUSDT", "volume_ratio": 2.4,
                            "volume_24h_usdt": 1e6, "last_price": 77.0},
                           {"symbol": "BTCUSDT", "volume_ratio": 1.1,
                            "volume_24h_usdt": 1e8, "last_price": 64000.0}],
            mention_surges=[{"symbol": "SOL", "rate_per_hour": 28.0,
                             "baseline_rate": 10.0, "change_pct": 180.0}],
            new_listings=["NEW-USDT-SWAP"],
            whale_signals=[],
        )
        symbols = [c["symbol"] for c in candidates]
        self.assertIn("SOLUSDT", symbols)
        self.assertIn("NEWUSDT", symbols)
        self.assertNotIn("BTCUSDT", symbols)  # ratio 1.1 < surge threshold
        sol = next(c for c in candidates if c["symbol"] == "SOLUSDT")
        self.assertEqual(sol, candidates[0])  # volume+mentions outranks listing
        self.assertIn("volume x2.4 vs 7d avg", sol["reasons"])
        self.assertIn("mentions +180%/h on StockTwits", sol["reasons"])

    def test_whale_interface_is_consumed(self):
        from scanner import assemble_candidates, fetch_whale_signals
        self.assertEqual(fetch_whale_signals(), [])  # Phase 6 stub
        candidates = assemble_candidates([], [], [], [
            {"symbol": "ETHUSDT", "direction": "out", "usd_value": 5e6,
             "reason": "whale outflow $5M"}])
        self.assertEqual(candidates[0]["symbol"], "ETHUSDT")
        self.assertIn("whale outflow $5M", candidates[0]["reasons"])


class MentionRateTests(unittest.TestCase):
    def test_fetch_mention_rate_from_stream(self):
        from scanner import fetch_mention_rate

        class FakeResp:
            status_code = 200
            def json(self):
                # 30 messages spanning exactly 1 hour → 30/h
                return {"symbol": {"watchlist_count": 671941},
                        "messages": [
                            {"created_at": "2026-07-15T01:00:00Z"},
                            *[{"created_at": "2026-07-15T01:30:00Z"} for _ in range(28)],
                            {"created_at": "2026-07-15T02:00:00Z"},
                        ]}

        with patch("scanner.requests.get", return_value=FakeResp()):
            rate = fetch_mention_rate("BTC")
        self.assertEqual(rate["symbol"], "BTC")
        self.assertAlmostEqual(rate["rate_per_hour"], 30.0)
        self.assertEqual(rate["watchers"], 671941)


# ─── refresh + payload + API ──────────────────────────────────────────────

class RefreshAndPayloadTests(ScannerTestCase):
    def _refresh(self, tickers, candles_by_symbol, mention_rates, instruments):
        from scanner import refresh_scanner_snapshot

        def fake_okx_get(path, params, base=None):
            if path == "tickers":
                return tickers
            if path == "instruments":
                return [{"instId": i} for i in instruments]
            raise AssertionError(f"unexpected path {path}")

        def fake_candles(symbol, bar="1D", limit=9):
            return candles_by_symbol[symbol]

        def fake_mention(symbol):
            return mention_rates.get(symbol)

        with patch("crypto_feed._okx_get", side_effect=fake_okx_get), \
             patch("crypto_feed.fetch_candles", side_effect=fake_candles), \
             patch("scanner.fetch_mention_rate", side_effect=fake_mention):
            return refresh_scanner_snapshot()

    TICKERS = [
        {"instId": "SOL-USDT-SWAP", "volCcy24h": "9000000", "last": "77"},
        {"instId": "BTC-USDT-SWAP", "volCcy24h": "100000000", "last": "64000"},
        {"instId": "ETH-USD-SWAP", "volCcy24h": "50000000", "last": "1876"},  # non-USDT: skipped
    ]
    CANDLES = {
        "SOLUSDT": _daily([100] * 7 + [240]),   # x2.4 surge
        "BTCUSDT": _daily([100] * 7 + [110]),   # calm
    }

    def test_full_scan_produces_ranked_candidates_with_reasons(self):
        from scanner import get_scanner_payload
        instruments = ["BTC-USDT-SWAP", "SOL-USDT-SWAP"]
        rates = {"BTC": {"symbol": "BTC", "rate_per_hour": 10.0, "watchers": 1}}
        # Three scans to build the mention baseline, then a spike + new listing.
        for _ in range(3):
            self._refresh(self.TICKERS, self.CANDLES, rates, instruments)
        spiked = {"BTC": {"symbol": "BTC", "rate_per_hour": 28.0, "watchers": 1}}
        result = self._refresh(self.TICKERS, self.CANDLES, spiked,
                               instruments + ["NEW-USDT-SWAP"])
        self.assertEqual(result["errors"], {})
        self.assertEqual(result["new_listings"], ["NEW-USDT-SWAP"])

        payload = get_scanner_payload()
        self.assertTrue(payload["available"])
        by_symbol = {c["symbol"]: c for c in payload["candidates"]}
        self.assertIn("SOLUSDT", by_symbol)   # volume x2.4
        self.assertIn("BTCUSDT", by_symbol)   # mentions +180%
        self.assertIn("NEWUSDT", by_symbol)   # new listing
        self.assertTrue(any("volume x2.4" in r for r in by_symbol["SOLUSDT"]["reasons"]))
        self.assertTrue(any("+180%" in r for r in by_symbol["BTCUSDT"]["reasons"]))
        self.assertTrue(any("newly listed" in r for r in by_symbol["NEWUSDT"]["reasons"]))

    def test_payload_unavailable_before_first_scan(self):
        from scanner import get_scanner_payload
        self.assertFalse(get_scanner_payload()["available"])

    def test_api_route_serves_candidates(self):
        client = TestClient(create_app())
        resp = client.get("/api/scanner/candidates")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()["available"])
        self._seed_snapshot(candidates=[{"symbol": "SOLUSDT", "score": 2.4,
                                         "reasons": ["volume x2.4 vs 7d avg"],
                                         "signals": {"volume_ratio": 2.4}}])
        body = client.get("/api/scanner/candidates").json()
        self.assertTrue(body["available"])
        self.assertEqual(body["candidates"][0]["symbol"], "SOLUSDT")


# ─── automation integration ───────────────────────────────────────────────

class AutomationScannerTests(ScannerTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.client = TestClient(create_app())
        resp = self.client.post(
            "/api/claw/agents/selfRegister",
            json={"name": "scanner-agent", "password": "pw123", "initial_balance": 100000.0},
        )
        assert resp.status_code == 200, resp.text
        self.token = resp.json()["token"]

    def _make_scanner_rule(self) -> dict:
        resp = self.client.post(
            "/api/automation/configs",
            json={"symbol": "SCANNER", "market": "crypto", "auto_execute": True,
                  "min_confidence": 0.5, "size_usd": 500},
            headers={"Authorization": f"Bearer {self.token}"},
        )
        assert resp.status_code == 200, resp.text
        config_id = resp.json()["id"]
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM automation_configs WHERE id = ?", (config_id,))
        config = dict(cursor.fetchone())
        conn.close()
        return config

    def test_scanner_rule_analyzes_top_candidate(self):
        from automation import run_rule
        self._seed_snapshot(candidates=[{"symbol": "SOLUSDT", "score": 2.4,
                                         "reasons": ["volume x2.4 vs 7d avg"],
                                         "signals": {}}])
        config = self._make_scanner_rule()
        fake = {"decision": {"action": "buy", "confidence": 0.9, "entry": 77.0,
                             "report": "test"}}
        with patch("analysis_agents.run_analysis", return_value=fake) as mock_analysis, \
             patch("routes_shared.is_market_open", return_value=True):
            result = run_rule(config)
        mock_analysis.assert_called_once()
        self.assertEqual(mock_analysis.call_args[0][0], "SOL")  # USDT suffix trimmed
        self.assertTrue(result["executed"], result)
        self.assertEqual(result["scanner_symbol"], "SOL")

    def test_scanner_rule_skips_when_no_candidates(self):
        from automation import run_rule
        self._seed_snapshot(candidates=[])
        config = self._make_scanner_rule()
        result = run_rule(config)
        self.assertFalse(result["executed"])
        self.assertIn("no candidates", result["skip_reason"])
        # run is journaled
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT skip_reason FROM automation_runs WHERE config_id = ?",
                       (config["id"],))
        row = cursor.fetchone()
        conn.close()
        self.assertIn("no candidates", row["skip_reason"])


if __name__ == "__main__":
    unittest.main()
