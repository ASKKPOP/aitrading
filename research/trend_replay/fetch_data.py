#!/usr/bin/env python
"""Fetch and cache OKX USDT-swap candles (and alternative.me F&G) for the
trend-module replay. Raw strings are written untouched so the cache is an
exact copy of what the venue returned.

Usage (from repo root):
    .venv/bin/python research/trend_replay/fetch_data.py daily
    .venv/bin/python research/trend_replay/fetch_data.py hourly
    .venv/bin/python research/trend_replay/fetch_data.py fng

Only CONFIRMED bars (OKX confirm == "1") are written; the forming bar is
dropped at the source. OKX "1D" bars open at 16:00 UTC — the same bar the
live module reads (crypto_feed.fetch_candles(symbol, bar="1D")).
"""
from __future__ import annotations

import csv
import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
START_MS = int(datetime(2020, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
BASE = "https://www.okx.com/api/v5/market/history-candles"
UA = {"User-Agent": "trend-replay-research/1.0"}


def inst_id(symbol: str) -> str:
    # identical mapping to crypto_feed._to_inst_id
    return f"{symbol[:-4]}-USDT-SWAP"


def _get(params: dict[str, str]) -> list[list[str]]:
    url = f"{BASE}?{urllib.parse.urlencode(params)}"
    for attempt in range(8):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=20) as resp:
                body = json.loads(resp.read().decode())
            if body.get("code") != "0":
                raise RuntimeError(f"OKX {body.get('code')}: {body.get('msg')}")
            return body.get("data", [])
        except Exception as exc:  # noqa: BLE001
            wait = 1.5 * (attempt + 1)
            print(f"  retry {attempt + 1} after {exc!r} (sleep {wait}s)", flush=True)
            time.sleep(wait)
    raise RuntimeError(f"gave up on {url}")


def fetch(symbol: str, bar: str) -> list[list[str]]:
    rows: dict[int, list[str]] = {}
    after: str | None = None
    while True:
        params = {"instId": inst_id(symbol), "bar": bar, "limit": "100"}
        if after is not None:
            params["after"] = after
        data = _get(params)
        if not data:
            break
        for row in data:
            rows[int(row[0])] = row
        oldest = int(data[-1][0])
        if oldest <= START_MS:
            break
        after = str(oldest)
        time.sleep(0.11)
    out = [rows[k] for k in sorted(rows) if k >= START_MS]
    return out


def write(symbol: str, bar: str, rows: list[list[str]]) -> Path:
    DATA.mkdir(parents=True, exist_ok=True)
    path = DATA / f"okx_swap_{symbol}_{bar}.csv"
    kept = dropped = 0
    with path.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["ts_ms", "iso_utc", "open", "high", "low", "close",
                    "vol_contracts", "confirm"])
        for r in rows:
            if r[8] != "1":
                dropped += 1
                continue
            iso = datetime.fromtimestamp(int(r[0]) / 1000, timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ")
            w.writerow([r[0], iso, r[1], r[2], r[3], r[4], r[5], r[8]])
            kept += 1
    print(f"{symbol} {bar}: kept {kept} confirmed, dropped {dropped} forming -> {path.name}",
          flush=True)
    return path


def fetch_fng() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    url = "https://api.alternative.me/fng/?limit=0&format=json"
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.loads(resp.read().decode())
    rows = sorted(body["data"], key=lambda r: int(r["timestamp"]))
    path = DATA / "fng_alternative_me.csv"
    with path.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["date_utc", "value"])
        for r in rows:
            d = datetime.fromtimestamp(int(r["timestamp"]), timezone.utc).strftime("%Y-%m-%d")
            w.writerow([d, r["value"]])
    print(f"fng: {len(rows)} rows -> {path.name}")


BITMEX_PROXY = {"BTCUSDT": "XBTUSD", "ETHUSDT": "ETHUSD", "XRPUSDT": "XRPUSD",
                "SOLUSDT": "SOLUSDT", "BNBUSDT": "BNBUSDT"}


def fetch_funding() -> None:
    """POST-HOC, cross-venue: OKX serves only ~3 months of funding history,
    Binance/Bybit are geo-blocked from this machine, so BitMEX 8h funding is
    cached as a PROXY for the unmodelled funding cost (sensitivity S4 only)."""
    DATA.mkdir(parents=True, exist_ok=True)
    for sym, bx in BITMEX_PROXY.items():
        rows: list[dict] = []
        start = 0
        while True:
            url = ("https://www.bitmex.com/api/v1/funding?" + urllib.parse.urlencode({
                "symbol": bx, "count": "500", "start": str(start), "reverse": "false",
                "startTime": "2020-01-01T00:00:00.000Z"}))
            for attempt in range(6):
                try:
                    req = urllib.request.Request(url, headers=UA)
                    with urllib.request.urlopen(req, timeout=30) as resp:
                        page = json.loads(resp.read().decode())
                    break
                except Exception as exc:  # noqa: BLE001
                    print(f"  retry {attempt + 1} after {exc!r}", flush=True)
                    time.sleep(10 * (attempt + 1))
            else:
                raise RuntimeError(f"gave up on {url}")
            rows.extend(page)
            if len(page) < 500:
                break
            start += 500
            time.sleep(2.2)
        path = DATA / f"bitmex_funding_{sym}.csv"
        with path.open("w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["timestamp_utc", "bitmex_symbol", "funding_rate"])
            for r in rows:
                w.writerow([r["timestamp"], r["symbol"], repr(r["fundingRate"])])
        print(f"{sym} ({bx}): {len(rows)} funding rows "
              f"{rows[0]['timestamp'] if rows else None} .. "
              f"{rows[-1]['timestamp'] if rows else None}", flush=True)
        time.sleep(2.2)


def main() -> None:
    what = sys.argv[1] if len(sys.argv) > 1 else "daily"
    if what == "fng":
        fetch_fng()
        return
    if what == "funding":
        fetch_funding()
        return
    bar = {"daily": "1D", "hourly": "1H"}[what]
    meta_path = DATA / f"fetch_meta_{bar}.json"
    meta = {"fetched_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "endpoint": BASE, "bar": bar, "symbols": {}}
    for sym in SYMBOLS:
        rows = fetch(sym, bar)
        write(sym, bar, rows)
        conf = [r for r in rows if r[8] == "1"]
        meta["symbols"][sym] = {
            "inst_id": inst_id(sym), "rows_confirmed": len(conf),
            "first_ts_ms": int(conf[0][0]) if conf else None,
            "last_ts_ms": int(conf[-1][0]) if conf else None}
    DATA.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(json.dumps(meta, indent=2) + "\n")
    print("done", flush=True)


if __name__ == "__main__":
    main()
