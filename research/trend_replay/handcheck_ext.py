#!/usr/bin/env python
"""Independent verification of the six R-LONG / R-STOCK runs (PREREG G9).

Imports neither trend_module nor any replay engine. Raw cached bars are
re-read here (stocks re-adjusted here), the rule is re-implemented from its
written definition (own ATR/ADX from handcheck.py, own trail, own slot
logic), and (a) the complete trade list of every run must come out
identical to the cent, (b) the best, worst and median trade of every run
are printed with the raw rows they come from.

    .venv/bin/python research/trend_replay/handcheck_ext.py
"""
from __future__ import annotations

import calendar
import csv
from datetime import datetime, timezone
from pathlib import Path

from handcheck import adx14, atr14

HERE = Path(__file__).resolve().parent
H = 3_600_000
DAY = 24 * H
CRYPTO = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
U1 = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AVGO", "AMD", "NFLX"]
U2 = sorted(["MMM", "GOOGL", "AXP", "AMGN", "AMZN", "AAPL", "BA", "CAT", "CVX", "CSCO", "KO",
             "DIS", "GS", "HD", "HON", "IBM", "JNJ", "JPM", "MCD", "MRK", "MSFT", "NKE", "NVDA",
             "PG", "CRM", "SHW", "TRV", "UNH", "V", "WMT"])


def iso(ms):
    return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def crypto_rows(sym, bar):
    out = []
    with (HERE / "data" / f"okx_swap_{sym}_{bar}.csv").open() as fh:
        for r in csv.DictReader(fh):
            out.append({"ts": int(r["ts_ms"]), "open": float(r["open"]), "high": float(r["high"]),
                        "low": float(r["low"]), "close": float(r["close"]),
                        "raw": f"O={r['open']} H={r['high']} L={r['low']} C={r['close']}"})
    return out


def stock_rows(sym):
    out = []
    with (HERE / "data" / f"yahoo_{sym}_1D.csv").open() as fh:
        for r in csv.DictReader(fh):
            y, m, d = (int(x) for x in r["date"].split("-"))
            ts = calendar.timegm((y, m, d, 14, 30, 0)) * 1000
            k = float(r["adjclose"]) / float(r["close"])
            out.append({"ts": ts, "open": k * float(r["open"]), "high": k * float(r["high"]),
                        "low": k * float(r["low"]), "close": k * float(r["close"]),
                        "raw": (f"O={float(r['open']):.4f} H={float(r['high']):.4f} "
                                f"L={float(r['low']):.4f} C={float(r['close']):.4f} "
                                f"adjclose={float(r['adjclose']):.4f} factor={k:.6f}")})
    return out


def replay(rows, universe, allow_short, cost, close_off, first_sig=None, hourly=None):
    idx = {s: {r["ts"]: i for i, r in enumerate(rows[s])} for s in universe}
    days = sorted({r["ts"] for s in universe for r in rows[s]})
    hby = {}
    if hourly:
        for s in universe:
            m = {}
            for hb in hourly[s]:
                m.setdefault((hb["ts"] - 16 * H) // DAY * DAY + 16 * H, []).append(hb)
            hby[s] = m
    held, out = {}, []

    def done(s, p, xpx, xts, reason, extra):
        gross = p["q"] * (xpx - p["e"]) * p["d"]
        fees = cost * p["q"] * (p["e"] + xpx)
        out.append({"symbol": s, "side": "long" if p["d"] == 1 else "short",
                    "signal": iso(p["sig_ts"]), "entry": iso(p["e_ts"]), "exit": iso(xts),
                    "reason": reason, "net": gross - fees, "gross": gross, "cost": fees,
                    "p": p, "xpx": xpx, **extra})
        del held[s]

    for ts in days:
        if hourly:
            for s in sorted(held):
                p = held[s]
                if p["e_ts"] > ts or ts not in idx[s]:
                    continue
                for hb in hby[s].get(ts, []):
                    if hb["ts"] < p["e_ts"]:
                        continue
                    if p["d"] == 1 and hb["low"] <= p["init"]:
                        done(s, p, min(p["init"], hb["open"]), hb["ts"] + H, "intraday_stop", {"hb": hb})
                        break
                    if p["d"] == -1 and hb["high"] >= p["init"]:
                        done(s, p, max(p["init"], hb["open"]), hb["ts"] + H, "intraday_stop", {"hb": hb})
                        break
        for s in sorted(held):
            i = idx[s].get(ts)
            p = held[s]
            if i is None or p["e_ts"] > ts:
                continue
            c = rows[s][i]["close"]
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
            if (ts + close_off) - p["e_ts"] >= 30 * DAY:
                reason = "time_stop"
            elif hit:
                reason = "initial_stop" if stop == p["init"] else "trail_stop"
            if not reason:
                continue
            info = {"xi": i, "stop_at_exit": stop}
            if i + 1 < len(rows[s]):
                done(s, p, rows[s][i + 1]["open"], rows[s][i + 1]["ts"], reason, info)
            else:
                done(s, p, c, ts + close_off, "end_of_data", info)
        if first_sig is not None and ts < first_sig:
            continue
        for s in universe:
            if s in held:
                continue
            if len(held) >= 3:
                break
            i = idx[s].get(ts)
            if i is None or i + 1 < 210 or i + 1 >= len(rows[s]):
                continue
            c = rows[s][i]["close"]
            hi = max(r["high"] for r in rows[s][i - 20: i])
            lo = min(r["low"] for r in rows[s][i - 20: i])
            if not (c > hi or c < lo):
                continue
            w = rows[s][max(0, i + 1 - 280): i + 1]
            adx = adx14(w)
            if not 25 <= adx <= 40:
                continue
            ma = sum(r["close"] for r in rows[s][i - 199: i + 1]) / 200.0
            d = 1 if (c > hi and c > ma) else (-1 if (c < lo and c < ma) else 0)
            if d == 0 or (d == -1 and not allow_short):
                continue
            a = atr14(w)
            e = rows[s][i + 1]["open"]
            held[s] = {"d": d, "e": e, "q": 25.0 / (1.5 * a), "init": e - d * 1.5 * a,
                       "trail": None, "best": e, "e_ts": rows[s][i + 1]["ts"], "sig_ts": ts,
                       "si": i, "atr": a, "adx": adx, "ma": ma, "hi": hi, "lo": lo}
    for s in sorted(held):
        last = rows[s][-1]
        done(s, held[s], last["close"], last["ts"] + close_off, "end_of_data", {})
    return out


def explain(t, rows):
    s, p = t["symbol"], t["p"]
    r = rows[s]
    i = p["si"]
    print(f"  {s} {t['side']}: signal bar {t['signal']}  raw {r[i]['raw']}")
    print(f"    adj close {r[i]['close']:.6f}; prior-20 channel [{p['lo']:.6f}, {p['hi']:.6f}]; "
          f"ADX14 {p['adx']:.3f}; MA200 {p['ma']:.6f}; ATR14 {p['atr']:.6f}")
    print(f"    entry bar {t['entry']}  raw {r[i + 1]['raw']}")
    print(f"    fill {p['e']:.6f}; qty {p['q']:.6f}; initial stop {p['init']:.6f}")
    if t["reason"] == "intraday_stop":
        hb = t["hb"]
        print(f"    1H bar {iso(hb['ts'])} {hb['raw']} trades through the stop -> fill {t['xpx']:.6f}")
    elif "xi" in t:
        x = t["xi"]
        print(f"    exit signal bar {iso(r[x]['ts'])}  raw {r[x]['raw']}  adj close {r[x]['close']:.6f} "
              f"vs stop {t['stop_at_exit']:.6f}; best close {p['best']:.6f}")
        if x + 1 < len(r):
            print(f"    exit bar {t['exit']}  raw {r[x + 1]['raw']}")
    print(f"    exit fill {t['xpx']:.6f} ({t['reason']}); gross {t['gross']:.4f}; "
          f"costs {t['cost']:.4f}; NET {t['net']:.4f} USD = {t['net'] / 25:.4f} R")


def check(name, csv_name, rows, universe, **kw):
    mine = replay(rows, universe, **kw)
    with (HERE / csv_name).open() as fh:
        theirs = list(csv.DictReader(fh))
    a = sorted((t["symbol"], t["side"], t["signal"], t["entry"], t["exit"], t["reason"],
                round(t["net"], 2)) for t in mine)
    b = sorted((t["symbol"], t["side"], t["signal_bar"], t["entry_ts"], t["exit_ts"],
                t["exit_reason"], round(float(t["net_usd"]), 2)) for t in theirs)
    total = sum(t["net"] for t in mine)
    print(f"\n######## {name}: independent {len(mine)} trades {total / 25:+.2f}R | "
          f"{csv_name} {len(theirs)} trades {sum(float(t['net_usd']) for t in theirs) / 25:+.2f}R | "
          f"FULL LIST IDENTICAL TO THE CENT: {a == b}")
    if a != b:
        print("   only independent:", [x for x in a if x not in b][:5])
        print("   only csv:", [x for x in b if x not in a][:5])
    ranked = sorted(mine, key=lambda t: t["net"])
    for label, t in (("WORST", ranked[0]), ("MEDIAN", ranked[len(ranked) // 2]), ("BEST", ranked[-1])):
        print(f" {label}")
        explain(t, rows)
    return a == b


def main():
    cd = {s: crypto_rows(s, "1D") for s in CRYPTO}
    ch = {s: crypto_rows(s, "1H") for s in CRYPTO}
    st = {s: stock_rows(s) for s in sorted(set(U1) | set(U2))}
    first = calendar.timegm((2015, 1, 1, 0, 0, 0)) * 1000
    ok = [
        check("R-LONG-D", "trades_RLONG_D.csv", cd, CRYPTO, allow_short=False, cost=9.5e-4,
              close_off=DAY),
        check("R-LONG-V2", "trades_RLONG_V2.csv", cd, CRYPTO, allow_short=False, cost=9.5e-4,
              close_off=DAY, hourly=ch),
    ]
    for uname, uni in (("U1", U1), ("U2", U2)):
        for mode, short in (("LS", True), ("LO", False)):
            ok.append(check(f"R-STOCK {uname} {mode}", f"trades_STOCK_{uname}_{mode}.csv", st, uni,
                            allow_short=short, cost=3e-4, close_off=6 * H + H // 2,
                            first_sig=first))
    print(f"\nALL SIX RUNS REPRODUCED INDEPENDENTLY: {all(ok)}  {ok}")


if __name__ == "__main__":
    main()
