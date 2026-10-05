#!/usr/bin/env python
"""Independent re-derivation of intraday-stop trades from the RAW 1H rows.
Imports neither trend_module nor the replay engine (only handcheck.atr14,
which is itself a from-scratch Wilder ATR).

    .venv/bin/python research/trend_replay/handcheck_stops.py
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path

from handcheck import atr14, raw_rows

HERE = Path(__file__).resolve().parent
H = 3_600_000
_hourly_cache: dict[str, list[dict]] = {}


def hourly(symbol):
    if symbol not in _hourly_cache:
        with (HERE / "data" / f"okx_swap_{symbol}_1H.csv").open() as fh:
            _hourly_cache[symbol] = list(csv.DictReader(fh))
    return _hourly_cache[symbol]


def ms(iso_s):
    return int(datetime.strptime(iso_s, "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=timezone.utc).timestamp() * 1000)


def derive(trade, variant, verbose=False):
    sym, side = trade["symbol"], trade["side"]
    d = 1 if side == "long" else -1
    days = raw_rows(sym)
    dpos = {r["iso_utc"]: i for i, r in enumerate(days)}
    s = dpos[trade["signal_bar"]]
    atr = atr14(days[max(0, s + 1 - 280): s + 1])
    entry_row = days[s + 1]
    entry = float(entry_row["open"])
    entry_ms = int(entry_row["ts_ms"])
    qty = 25.0 / (1.5 * atr)
    hrs = hourly(sym)
    if variant == "V2":
        stop, active_from, note = entry - d * 1.5 * atr, entry_ms, "entry -/+ 1.5 x ATR"
    else:
        mark_row = next(r for r in hrs if int(r["ts_ms"]) == entry_ms + 2 * H)
        mark = float(mark_row["open"])
        anchor = min(entry, mark) if d == 1 else max(entry, mark)
        stop = anchor * (0.95 if d == 1 else 1.05)
        active_from = entry_ms + 2 * H
        note = (f"mark at +2h ({mark_row['iso_utc']} open) = {mark}; anchor = {anchor} "
                f"({'entry' if anchor == entry else 'MARK'}); x {'0.95' if d == 1 else '1.05'}")
    hit = None
    for r in hrs:
        t = int(r["ts_ms"])
        if t < active_from:
            continue
        o, hi, lo = float(r["open"]), float(r["high"]), float(r["low"])
        if (d == 1 and lo <= stop) or (d == -1 and hi >= stop):
            fill = min(stop, o) if d == 1 else max(stop, o)
            hit = (r, fill)
            break
    r, fill = hit
    gross = qty * (fill - entry) * d
    fee = 0.00045 * qty * (entry + fill)
    slip = 0.00050 * qty * (entry + fill)
    net = gross - fee - slip
    ok = (r["iso_utc"] == trade["stop_hour_bar"]
          and round(net, 2) == round(float(trade["net_usd"]), 2)
          and abs(fill - float(trade["exit_price"])) <= 1e-9 * fill
          and abs(stop - float(trade["stop_price"])) <= 1e-9 * stop
          and entry_row["iso_utc"] == trade["entry_ts"])
    if verbose:
        print(f"\n=== {variant}  {sym} {side}  signal bar {trade['signal_bar']} ===")
        print(f" entry: daily bar {entry_row['iso_utc']} open = {entry}   ATR14 = {atr:.8f}   qty = {qty:.8f}")
        print(f" stop rule: {note}")
        print(f" stop = {stop:.8f}, active from "
              f"{datetime.fromtimestamp(active_from / 1000, timezone.utc):%Y-%m-%dT%H:%MZ}")
        i = hrs.index(r)
        first_i = next(k for k, x in enumerate(hrs) if int(x["ts_ms"]) == entry_ms)
        for x in hrs[max(first_i, i - 3): i + 1]:
            flag = "  <-- trades through the stop" if x is r else ""
            print(f"   1H {x['iso_utc']} O={x['open']} H={x['high']} L={x['low']} C={x['close']}{flag}")
        prior = hrs[first_i: i]
        act = [x for x in prior if int(x["ts_ms"]) >= active_from]
        if act:
            ext = (min(float(x["low"]) for x in act) if d == 1 else max(float(x["high"]) for x in act))
            print(f" {len(act)} earlier active 1H bars; their extreme "
                  f"{'low' if d == 1 else 'high'} = {ext} (stop not reached)")
        print(f" fill = {fill}   gross = {gross:.4f}  fees = {fee:.4f}  slippage = {slip:.4f}")
        print(f" NET = {net:.4f} USD = {net / 25:.4f} R")
        print(f" replay says: hit bar {trade['stop_hour_bar']} fill {trade['exit_price']} "
              f"net {float(trade['net_usd']):.4f}  -> MATCH TO THE CENT: {ok}")
    return ok


def main():
    with (HERE / "trades.csv").open() as fh:
        prim = {(t["symbol"], t["side"], t["signal_bar"]): t for t in csv.DictReader(fh)}
    for variant in ("V2", "V3"):
        with (HERE / f"trades_{variant}.csv").open() as fh:
            stops = [t for t in csv.DictReader(fh) if t["exit_reason"] == "intraday_stop"]

        def diff(t):
            p = prim.get((t["symbol"], t["side"], t["signal_bar"]))
            return abs(float(t["net_usd"]) - float(p["net_usd"])) if p else -1.0
        pick = max(stops, key=diff)                     # most consequential trade
        derive(pick, variant, verbose=True)
        if variant == "V3":                             # also one with a MARK-based anchor
            moved = [t for t in stops if abs(
                float(t["stop_price"]) / float(t["entry_price"])
                - (0.95 if t["side"] == "long" else 1.05)) > 1e-9]
            print(f"\nV3 stops anchored on the +2h mark instead of entry: {len(moved)} of {len(stops)}")
            if moved:
                derive(max(moved, key=diff), variant, verbose=True)
        n_ok = sum(1 for t in stops if derive(t, variant))
        late = sum(1 for t in stops
                   if (p := prim.get((t["symbol"], t["side"], t["signal_bar"])))
                   and ms(t["exit_ts"]) > ms(p["exit_ts"]))
        print(f"\n{variant}: all intraday-stop trades independently re-derived and matched: "
              f"{n_ok}/{len(stops)}; stop stamped later than the paired primary exit: {late}")


if __name__ == "__main__":
    main()
