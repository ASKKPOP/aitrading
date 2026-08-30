#!/usr/bin/env python3
"""Fetch OKX 1m candles for every crypto symbol in r1_trips.json, covering
entry_ts-1h .. min(entry_ts+24h) for each trip (union per symbol).
Cache one JSON per instrument: [[ts, o, h, l, c], ...] ascending.
"""
import json, os, sys, time, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor

D = os.path.dirname(os.path.abspath(__file__))
CD = os.path.join(D, "candles")
os.makedirs(CD, exist_ok=True)
HORIZON = 24 * 3600
UA = {"User-Agent": "Mozilla/5.0"}

T = json.load(open(os.path.join(D, "r1_trips.json")))
C = [t for t in T if t["market"] == "crypto"]
need = {}
for t in C:
    s = t["symbol"]
    lo = t["entry_ts"] - 3600
    hi = max(t["exit_ts"], t["entry_ts"] + HORIZON) + 3600
    a, b = need.get(s, (lo, hi))
    need[s] = (min(a, lo), max(b, hi))

def fetch(sym):
    inst = sym[:-4] + "-USDT"
    path = os.path.join(CD, f"okx1m_{inst}.json")
    t0, t1 = need[sym]
    if os.path.exists(path):
        rows = json.load(open(path))
        if rows and rows[0][0] <= t0 + 120 and rows[-1][0] >= t1 - 120:
            return sym, len(rows), "cached"
    out = {}
    after = (t1 + 60) * 1000
    calls = 0
    while True:
        q = urllib.parse.urlencode({"instId": inst, "bar": "1m",
                                    "after": str(int(after)), "limit": "100"})
        req = urllib.request.Request(
            "https://www.okx.com/api/v5/market/history-candles?" + q, headers=UA)
        try:
            with urllib.request.urlopen(req, timeout=25) as r:
                data = json.load(r).get("data", [])
        except Exception as e:  # noqa: BLE001
            time.sleep(1.0)
            calls += 1
            if calls > 2000:
                break
            continue
        calls += 1
        if not data:
            break
        for c in data:
            ts = int(c[0]) // 1000
            if t0 <= ts <= t1:
                out[ts] = [ts, float(c[1]), float(c[2]), float(c[3]), float(c[4])]
        oldest = int(data[-1][0]) // 1000
        if oldest <= t0:
            break
        after = int(data[-1][0])
        time.sleep(0.32)
    rows = [out[k] for k in sorted(out)]
    json.dump(rows, open(path, "w"))
    return sym, len(rows), f"{calls} calls"

syms = sorted(need)
print(f"{len(syms)} symbols", flush=True)
with ThreadPoolExecutor(max_workers=4) as ex:
    for sym, n, how in ex.map(fetch, syms):
        print(f"{sym:14s} {n:7d} bars  {how}", flush=True)
print("DONE", flush=True)
