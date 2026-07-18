"""Plan 06 B1 — real whale tracking (BTC mempool + ETH exchange wallets). Offline."""

from __future__ import annotations

import os
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import whale_feed
from whale_feed import (fetch_btc_whale_txs, fetch_eth_whale_txs,
                        get_whale_payload, whale_scanner_signals)

BINANCE_14 = "0x28c6c06298d514db089934071355e5743bf21d60"

_BTC_MEMPOOL = {"txs": [
    {"hash": "big1", "time": 1752700000,
     "out": [{"value": 200 * 10**8}, {"value": 50 * 10**8}]},   # 250 BTC
    {"hash": "small", "time": 1752700001, "out": [{"value": 10**8}]},  # 1 BTC
]}


def _eth_row(hash_, to, frm, eth, ts):
    return {"hash": hash_, "to": to, "from": frm,
            "value": str(int(eth * 1e18)), "timeStamp": str(ts)}


class BtcWhaleTests(unittest.TestCase):
    def test_threshold_and_shape(self):
        with patch.object(whale_feed, "_get_json", return_value=_BTC_MEMPOOL):
            events = fetch_btc_whale_txs(min_usd=5_000_000, btc_price=60_000)
        self.assertEqual(len(events), 1)  # 250 BTC = $15M in; 1 BTC filtered out
        e = events[0]
        self.assertEqual(e["symbol"], "BTCUSDT")
        self.assertEqual(e["direction"], "transfer")
        self.assertEqual(e["usd_value"], 250 * 60_000)
        self.assertFalse(e["estimated"])
        self.assertEqual(e["source"], "blockchain.info")


class EthWhaleTests(unittest.TestCase):
    def _fake_etherscan(self, rows_by_wallet):
        def fake(url):
            for wallet, rows in rows_by_wallet.items():
                if wallet in url:
                    return {"status": "1", "result": rows}
            return {"status": "1", "result": []}
        return fake

    def test_direction_threshold_and_lookback(self):
        now = int(time.time())
        rows = [
            _eth_row("in1", BINANCE_14, "0xabc", 3000, now - 60),        # $9M in
            _eth_row("out1", "0xdef", BINANCE_14, 4000, now - 120),      # $12M out
            _eth_row("small", BINANCE_14, "0xabc", 10, now - 60),        # too small
            _eth_row("old", BINANCE_14, "0xabc", 5000, now - 8 * 3600),  # too old
        ]
        with patch.object(whale_feed, "_get_json",
                          side_effect=self._fake_etherscan({BINANCE_14: rows})):
            events = fetch_eth_whale_txs(min_usd=5_000_000, eth_price=3000, api_key="k")
        by_hash = {e["tx_hash"]: e for e in events}
        self.assertEqual(set(by_hash), {"in1", "out1"})
        self.assertEqual(by_hash["in1"]["direction"], "in")
        self.assertEqual(by_hash["out1"]["direction"], "out")
        self.assertEqual(by_hash["in1"]["exchange"], "Binance 14")

    def test_no_key_returns_empty(self):
        with patch.dict(os.environ, {"ETHERSCAN_API_KEY": ""}):
            self.assertEqual(fetch_eth_whale_txs(5_000_000, 3000, api_key=None), [])

    def test_dedup_between_tracked_wallets(self):
        now = int(time.time())
        okx = "0x6cc5f688a315f3dc28a7781717a9a798a59fda7b"
        shared = _eth_row("shared", BINANCE_14, okx, 3000, now - 60)
        with patch.object(whale_feed, "_get_json",
                          side_effect=self._fake_etherscan({BINANCE_14: [shared], okx: [shared]})):
            events = fetch_eth_whale_txs(min_usd=5_000_000, eth_price=3000, api_key="k")
        self.assertEqual(len([e for e in events if e["tx_hash"] == "shared"]), 1)


class PayloadTests(unittest.TestCase):
    def setUp(self):
        whale_feed._CACHE["payload"] = None
        whale_feed._CACHE["at"] = 0.0

    def test_disabled_flag(self):
        with patch.dict(os.environ, {"WHALE_FEED_ENABLED": "false"}):
            payload = get_whale_payload()
        self.assertFalse(payload["available"])
        self.assertEqual(payload["events"], [])

    def test_totals_and_net_flow(self):
        now = int(time.time())
        eth_rows = [
            _eth_row("in1", BINANCE_14, "0xabc", 3000, now - 60),   # $9M in
            _eth_row("out1", "0xdef", BINANCE_14, 2000, now - 60),  # $6M out
        ]
        def fake_get(url):
            if "blockchain.info" in url:
                return _BTC_MEMPOOL
            return {"status": "1", "result": eth_rows if BINANCE_14 in url else []}
        with patch.dict(os.environ, {"WHALE_FEED_ENABLED": "true", "ETHERSCAN_API_KEY": "k"}), \
             patch.object(whale_feed, "_get_json", side_effect=fake_get), \
             patch.object(whale_feed, "_spot_price",
                          side_effect=lambda s: 60_000 if s == "BTCUSDT" else 3000):
            payload = get_whale_payload(force_refresh=True)
        self.assertTrue(payload["available"])
        self.assertEqual(payload["totals"]["btc_transfer_usd"], 15_000_000)
        self.assertEqual(payload["totals"]["eth_exchange_in_usd"], 9_000_000)
        self.assertEqual(payload["totals"]["eth_exchange_out_usd"], 6_000_000)
        self.assertEqual(payload["totals"]["eth_net_flow_usd"], 3_000_000)
        self.assertEqual(payload["count"], 3)

    def test_fail_soft_when_sources_down(self):
        with patch.dict(os.environ, {"WHALE_FEED_ENABLED": "true", "ETHERSCAN_API_KEY": "k"}), \
             patch.object(whale_feed, "_get_json", side_effect=OSError("down")), \
             patch.object(whale_feed, "_spot_price", return_value=60_000):
            payload = get_whale_payload(force_refresh=True)
        self.assertTrue(payload["available"])
        self.assertEqual(payload["events"], [])

    def test_scanner_adapter_reasons(self):
        now = int(time.time())
        def fake_get(url):
            if "blockchain.info" in url:
                return _BTC_MEMPOOL
            return {"status": "1",
                    "result": [_eth_row("in1", BINANCE_14, "0xabc", 3000, now - 60)]
                    if BINANCE_14 in url else []}
        with patch.dict(os.environ, {"WHALE_FEED_ENABLED": "true", "ETHERSCAN_API_KEY": "k"}), \
             patch.object(whale_feed, "_get_json", side_effect=fake_get), \
             patch.object(whale_feed, "_spot_price",
                          side_effect=lambda s: 60_000 if s == "BTCUSDT" else 3000):
            whale_feed._CACHE["payload"] = None
            signals = whale_scanner_signals()
        self.assertTrue(signals)
        symbols = {s["symbol"] for s in signals}
        self.assertTrue(symbols <= {"BTCUSDT", "ETHUSDT"})
        self.assertTrue(any("whale:" in s["reason"] for s in signals))

    def test_scanner_stub_replaced(self):
        from scanner import fetch_whale_signals
        with patch.dict(os.environ, {"WHALE_FEED_ENABLED": "false"}):
            whale_feed._CACHE["payload"] = None
            self.assertEqual(fetch_whale_signals(), [])


if __name__ == "__main__":
    unittest.main()
