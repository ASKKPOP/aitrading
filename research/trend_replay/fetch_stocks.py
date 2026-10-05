#!/usr/bin/env python
"""Fetch and cache daily US-stock bars for R-STOCK (PREREG G3).

    .venv/bin/python research/trend_replay/fetch_stocks.py

Source: Yahoo Finance chart API v8 (interval 1d, events div+splits).
Raw fields are written untouched: open/high/low/close are Yahoo's
split-adjusted prices, adjclose is split+dividend adjusted. The replay
applies adjclose/close to O/H/L/C itself. The request window ends at 00:00
UTC of the fetch day, so the session in progress is never included.
"""
from __future__ import annotations

import csv
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"
U1 = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AVGO", "AMD", "NFLX"]
U2 = ["AAPL", "AMGN", "AMZN", "AXP", "BA", "CAT", "CRM", "CSCO", "CVX", "DIS", "GOOGL",
      "GS", "HD", "HON", "IBM", "JNJ", "JPM", "KO", "MCD", "MMM", "MRK", "MSFT", "NKE",
      "NVDA", "PG", "SHW", "TRV", "UNH", "V", "WMT"]
START = int(datetime(2014, 1, 1, tzinfo=timezone.utc).timestamp())


def fetch(ticker: str, end: int) -> dict:
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?"
           + urllib.parse.urlencode({"period1": START, "period2": end, "interval": "1d",
                                     "events": "div,splits"}))
    for attempt in range(6):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = json.loads(resp.read().decode())
            res = body["chart"]["result"][0]
            if not res.get("timestamp"):
                raise RuntimeError("empty series")
            return res
        except Exception as exc:  # noqa: BLE001
            print(f"  retry {attempt + 1} for {ticker} after {exc!r}", flush=True)
            time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"gave up on {ticker}")


def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    end = int(datetime(now.year, now.month, now.day, tzinfo=timezone.utc).timestamp())
    meta = {"fetched_at_utc": now.isoformat(timespec="seconds"),
            "source": "Yahoo Finance chart API v8, interval=1d, events=div,splits",
            "window_end_exclusive_utc": datetime.fromtimestamp(end, timezone.utc).isoformat(),
            "symbols": {}}
    for t in sorted(set(U1) | set(U2)):
        res = fetch(t, end)
        q = res["indicators"]["quote"][0]
        adj = res["indicators"]["adjclose"][0]["adjclose"]
        ev = res.get("events", {})
        kept = dropped = 0
        path = DATA / f"yahoo_{t}_1D.csv"
        with path.open("w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["ts_s", "date", "open", "high", "low", "close", "adjclose", "volume"])
            for i, ts in enumerate(res["timestamp"]):
                vals = [q["open"][i], q["high"][i], q["low"][i], q["close"][i], adj[i]]
                if any(v is None for v in vals):
                    dropped += 1
                    continue
                d = datetime.fromtimestamp(ts + res["meta"].get("gmtoffset", 0),
                                           timezone.utc).strftime("%Y-%m-%d")
                w.writerow([ts, d] + [repr(float(v)) for v in vals] + [q["volume"][i] or 0])
                kept += 1
        first = datetime.fromtimestamp(res["timestamp"][0], timezone.utc).strftime("%Y-%m-%d")
        last = datetime.fromtimestamp(res["timestamp"][-1], timezone.utc).strftime("%Y-%m-%d")
        meta["symbols"][t] = {"rows": kept, "dropped_null": dropped, "first": first,
                              "last": last, "splits": len(ev.get("splits", {})),
                              "dividends": len(ev.get("dividends", {}))}
        print(f"{t}: {kept} rows {first}..{last} (dropped {dropped}; "
              f"{len(ev.get('splits', {}))} splits, {len(ev.get('dividends', {}))} dividends)",
              flush=True)
        time.sleep(0.6)
    (DATA / "fetch_meta_stocks.json").write_text(json.dumps(meta, indent=2) + "\n")
    print("done")


if __name__ == "__main__":
    main()
