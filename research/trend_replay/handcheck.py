#!/usr/bin/env python
"""Independent re-derivation of the best, worst and median trade from the raw
candle CSVs. Deliberately does NOT import trend_module or replay_lib: the
indicators, the trail and the P&L are re-implemented here from the rule's
written definition, then compared to trades.csv to the cent.

    .venv/bin/python research/trend_replay/handcheck.py
"""
from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent


def raw_rows(symbol):
    with (HERE / "data" / f"okx_swap_{symbol}_1D.csv").open() as fh:
        return list(csv.DictReader(fh))


def atr14(rows):
    """Wilder ATR(14) over `rows` (seeded with the mean of the first 14 TRs)."""
    tr = []
    for prev, cur in zip(rows, rows[1:]):
        h, l, pc = float(cur["high"]), float(cur["low"]), float(prev["close"])
        tr.append(max(h - l, abs(h - pc), abs(l - pc)))
    a = sum(tr[:14]) / 14.0
    for x in tr[14:]:
        a = a + (x - a) / 14.0          # algebraically (13a + x)/14
    return a


def adx14(rows):
    """Wilder ADX(14), textbook form with smoothed sums."""
    tr, pdm, mdm = [], [], []
    for prev, cur in zip(rows, rows[1:]):
        h, l, ph, pl, pc = (float(cur["high"]), float(cur["low"]), float(prev["high"]),
                            float(prev["low"]), float(prev["close"]))
        tr.append(max(h - l, abs(h - pc), abs(l - pc)))
        up, dn = h - ph, pl - l
        pdm.append(up if (up > dn and up > 0) else 0.0)
        mdm.append(dn if (dn > up and dn > 0) else 0.0)
    s_tr, s_p, s_m = sum(tr[:14]), sum(pdm[:14]), sum(mdm[:14])
    dx = []
    k = 14
    while True:
        pdi, mdi = 100 * s_p / s_tr, 100 * s_m / s_tr
        dx.append(100 * abs(pdi - mdi) / (pdi + mdi) if (pdi + mdi) > 0 else 0.0)
        if k >= len(tr):
            break
        s_tr = s_tr * 13 / 14 + tr[k]
        s_p = s_p * 13 / 14 + pdm[k]
        s_m = s_m * 13 / 14 + mdm[k]
        k += 1
    adx = sum(dx[:14]) / 14.0
    for x in dx[14:]:
        adx = (adx * 13 + x) / 14.0
    return adx


def check(trade):
    sym, side = trade["symbol"], trade["side"]
    rows = raw_rows(sym)
    pos = {r["iso_utc"]: i for i, r in enumerate(rows)}
    s = pos[trade["signal_bar"]]
    win = rows[max(0, s + 1 - 280): s + 1]
    sig_close = float(rows[s]["close"])
    atr = atr14(win)
    adx = adx14(win)
    ma200 = sum(float(r["close"]) for r in rows[s - 199: s + 1]) / 200.0
    ch_hi = max(float(r["high"]) for r in rows[s - 20: s])
    ch_lo = min(float(r["low"]) for r in rows[s - 20: s])
    if side == "long":
        cond = sig_close > ch_hi and 25 <= adx <= 40 and sig_close > ma200
    else:
        cond = sig_close < ch_lo and 25 <= adx <= 40 and sig_close < ma200
    e = s + 1
    entry = float(rows[e]["open"])
    qty = 25.0 / (1.5 * atr)
    d = 1 if side == "long" else -1
    init_stop = entry - d * 1.5 * atr
    entry_time = datetime.fromtimestamp(int(rows[e]["ts_ms"]) / 1000, timezone.utc)

    print(f"\n=== {sym} {side}  signal bar {rows[s]['iso_utc']} ===")
    print(f" signal bar raw: O={rows[s]['open']} H={rows[s]['high']} L={rows[s]['low']} C={rows[s]['close']}")
    print(f" prior-20 channel [{ch_lo}, {ch_hi}]  ADX14={adx:.4f}  MA200={ma200:.6f}  ATR14={atr:.8f}")
    print(f" entry condition holds: {cond}")
    print(f" entry bar raw:  {rows[e]['iso_utc']} O={rows[e]['open']}  -> fill {entry}")
    print(f" qty = 25/(1.5*ATR) = {qty:.8f}   initial stop = {init_stop:.8f}")

    best, trail, reason, x = entry, None, None, None
    for j in range(e, len(rows)):
        w = rows[max(0, j + 1 - 280): j + 1]
        c = float(rows[j]["close"])
        a = atr14(w)
        if side == "long":
            best = max(best, c)
            cand = best - 3 * a
            trail = cand if trail is None else max(trail, cand)
            stop = max(init_stop, trail)
            hit = c <= stop
        else:
            best = min(best, c)
            cand = best + 3 * a
            trail = cand if trail is None else min(trail, cand)
            stop = min(init_stop, trail)
            hit = c >= stop
        close_time = datetime.fromtimestamp(int(rows[j]["ts_ms"]) / 1000, timezone.utc) + timedelta(days=1)
        if close_time - entry_time >= timedelta(days=30):
            reason = "time_stop"
        elif hit:
            reason = "initial_stop" if stop == init_stop else "trail_stop"
        if j - e < 3 or reason:
            print(f"   {rows[j]['iso_utc']} C={rows[j]['close']} atr={a:.6f} best={best} "
                  f"trail={trail:.6f} stop={stop:.6f} {'EXIT ' + reason if reason else ''}")
        elif j - e == 3:
            print("   ...")
        if reason:
            x = j + 1
            break
    exit_px = float(rows[x]["open"])
    gross = qty * (exit_px - entry) * d
    fee = 0.00045 * qty * (entry + exit_px)
    slip = 0.00050 * qty * (entry + exit_px)
    net = gross - fee - slip
    print(f" exit bar raw:   {rows[x]['iso_utc']} O={rows[x]['open']}  -> fill {exit_px}   reason {reason}")
    print(f" gross = {gross:.4f}  fees(4.5bp x2 sides) = {fee:.4f}  slippage(5bp x2) = {slip:.4f}")
    print(f" NET = {net:.4f} USD = {net / 25:.4f} R")
    ok = (cond and rows[e]["iso_utc"] == trade["entry_ts"] and rows[x]["iso_utc"] == trade["exit_ts"]
          and reason == trade["exit_reason"]
          and Decimal(f"{net:.2f}") == Decimal(f"{float(trade['net_usd']):.2f}")
          and abs(qty - float(trade["qty"])) < 1e-9 * max(1.0, qty)
          and Decimal(f"{entry:.10g}") == Decimal(f"{float(trade['entry_price']):.10g}")
          and Decimal(f"{exit_px:.10g}") == Decimal(f"{float(trade['exit_price']):.10g}"))
    print(f" trades.csv says: entry {trade['entry_ts']} @{trade['entry_price']} exit {trade['exit_ts']} "
          f"@{trade['exit_price']} {trade['exit_reason']} net {float(trade['net_usd']):.4f}")
    print(f" MATCH TO THE CENT: {ok}")
    return ok


def main():
    with (HERE / "trades.csv").open() as fh:
        trades = list(csv.DictReader(fh))
    ranked = sorted(trades, key=lambda t: float(t["net_usd"]))
    picks = {"WORST": ranked[0], "MEDIAN": ranked[len(ranked) // 2], "BEST": ranked[-1]}
    results = {}
    for name, t in picks.items():
        print(f"\n################ {name} ################")
        results[name] = check(t)
    # and, beyond the three required, every trade in the file
    allok = sum(1 for t in trades if t["exit_reason"] != "end_of_data" and _quiet(t))
    n = sum(1 for t in trades if t["exit_reason"] != "end_of_data")
    print(f"\nthree required checks: {results}")
    print(f"all closed trades independently re-derived and matched: {allok}/{n}")


    independent_full_replay(trades)


def independent_full_replay(trades):
    """Second pass: a from-scratch walk of the whole calendar (own indicators,
    own slot/ordering logic, no trend_module import) must reproduce the full
    trade list — this also catches MISSED or EXTRA signals, which the
    per-trade check above cannot."""
    universe = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
    rows = {s: raw_rows(s) for s in universe}
    idx = {s: {int(r["ts_ms"]): i for i, r in enumerate(rows[s])} for s in universe}
    days = sorted({int(r["ts_ms"]) for s in universe for r in rows[s]})
    day = 86_400_000
    held, out = {}, []
    for ts in days:
        for s in sorted(held):
            i = idx[s].get(ts)
            p = held[s]
            if i is None or p["e_ts"] > ts:
                continue
            c = float(rows[s][i]["close"])
            a = atr14(rows[s][max(0, i + 1 - 280): i + 1])
            if p["d"] == 1:
                p["best"] = max(p["best"], c)
                cand = p["best"] - 3 * a
                p["trail"] = cand if p["trail"] is None else max(p["trail"], cand)
                stop = max(p["init"], p["trail"])
                hit = c <= stop
            else:
                p["best"] = min(p["best"], c)
                cand = p["best"] + 3 * a
                p["trail"] = cand if p["trail"] is None else min(p["trail"], cand)
                stop = min(p["init"], p["trail"])
                hit = c >= stop
            reason = None
            if (ts + day) - p["e_ts"] >= 30 * day:
                reason = "time_stop"
            elif hit:
                reason = "initial_stop" if stop == p["init"] else "trail_stop"
            if not reason:
                continue
            if i + 1 < len(rows[s]):
                xpx, xts = float(rows[s][i + 1]["open"]), ts + day
            else:
                xpx, xts, reason = c, ts + day, "end_of_data"
            net = p["q"] * (xpx - p["e"]) * p["d"] - 0.00095 * p["q"] * (p["e"] + xpx)
            out.append((s, p["sig_ts"], p["e_ts"], xts, reason, round(net, 2)))
            del held[s]
        for s in universe:
            if s in held:
                continue
            if len(held) >= 3:
                break
            i = idx[s].get(ts)
            if i is None or i + 1 < 210:
                continue
            w = rows[s][max(0, i + 1 - 280): i + 1]
            c = float(rows[s][i]["close"])
            hi = max(float(r["high"]) for r in rows[s][i - 20: i])
            lo = min(float(r["low"]) for r in rows[s][i - 20: i])
            if not (c > hi or c < lo):
                continue
            adx = adx14(w)
            ma = sum(float(r["close"]) for r in rows[s][i - 199: i + 1]) / 200.0
            if not 25 <= adx <= 40:
                continue
            d = 1 if (c > hi and c > ma) else (-1 if (c < lo and c < ma) else 0)
            if d == 0 or i + 1 >= len(rows[s]):
                continue
            a = atr14(w)
            e = float(rows[s][i + 1]["open"])
            held[s] = {"d": d, "e": e, "q": 25.0 / (1.5 * a), "init": e - d * 1.5 * a,
                       "trail": None, "best": e, "e_ts": ts + day, "sig_ts": ts}
    for s in sorted(held):
        p, last = held[s], rows[s][-1]
        c = float(last["close"])
        net = p["q"] * (c - p["e"]) * p["d"] - 0.00095 * p["q"] * (p["e"] + c)
        out.append((s, p["sig_ts"], p["e_ts"], int(last["ts_ms"]) + day, "end_of_data", round(net, 2)))

    def iso(ms):
        return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    mine = sorted((s, iso(a), iso(b), iso(c), r, n) for s, a, b, c, r, n in out)
    theirs = sorted((t["symbol"], t["signal_bar"], t["entry_ts"], t["exit_ts"], t["exit_reason"],
                     round(float(t["net_usd"]), 2)) for t in trades)
    total = sum(n for *_, n in mine)
    print(f"independent full replay: {len(mine)} trades, net ${total:.2f} "
          f"({total / 25:.2f}R); trades.csv: {len(theirs)} trades, "
          f"net ${sum(n for *_, n in theirs):.2f}")
    print(f"FULL TRADE LIST IDENTICAL (symbol, signal bar, entry, exit, reason, net to the cent): "
          f"{mine == theirs}")
    if mine != theirs:
        only_a = [m for m in mine if m not in theirs]
        only_b = [m for m in theirs if m not in mine]
        print(" only in independent:", only_a[:10])
        print(" only in trades.csv:", only_b[:10])


def _quiet(t):
    import contextlib
    import io
    with contextlib.redirect_stdout(io.StringIO()):
        return check(t)


if __name__ == "__main__":
    main()
