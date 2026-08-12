"""Plan 23 Gate 0 — historical PEAD event-study over liquid US large-caps.

Runs the backtest_catalyst harness over real earnings dates and daily bars
(yfinance). This is the kill-cheap gate: if the long-only test window cannot
show after-fee expectancy with a positive bootstrap lower bound and profit
factor >= 1.2, Plan 23's platform phases do not start.

Known biases, reported not hidden (plan §7): the universe is today's
constituents (survivorship — flatters the long side); earnings cluster in
weeks (handled by the harness's block bootstrap); daily-bar opens only.

Usage (from repo root, venv):
    .venv/bin/python research/gate0_pead_backtest.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "service" / "server"))

import backtest_catalyst as bc  # noqa: E402

# ~S&P-100 style liquid large-cap universe (static; survivorship documented).
UNIVERSE = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "AVGO", "BRK-B",
    "LLY", "JPM", "V", "XOM", "UNH", "MA", "PG", "COST", "JNJ", "HD", "WMT",
    "ABBV", "NFLX", "BAC", "CRM", "CVX", "KO", "MRK", "AMD", "PEP", "ADBE",
    "TMO", "LIN", "WFC", "CSCO", "ACN", "MCD", "ABT", "ORCL", "PM", "IBM",
    "GE", "TXN", "QCOM", "INTU", "DIS", "CAT", "VZ", "AMGN", "DHR", "PFE",
    "NOW", "NEE", "SPGI", "CMCSA", "RTX", "UNP", "LOW", "T", "HON", "UPS",
    "COP", "AXP", "BLK", "ETN", "BKNG", "SYK", "PANW", "MS", "GS", "VRTX",
    "SCHW", "TJX", "ISRG", "LMT", "MU", "C", "REGN", "ADP", "BSX", "MDT",
    "GILD", "CB", "MMC", "ADI", "SBUX", "LRCX", "MO", "AMAT", "BA", "PLD",
    "DE", "BMY", "SO", "ELV", "KLAC", "ANET", "NKE", "DUK", "INTC", "PYPL",
    "UBER", "SHOP", "ABNB", "SNOW", "PLTR",
]

BARS_START = "2023-01-01"
SPLIT_DATE = "2025-08-11"          # train: ->2025-08-11 (2y+), test: last 12mo
FEE_SIDE = 0.00005                 # us-stock per-side rate, FEE_PER_MARKET
OUT = Path(__file__).with_suffix(".result.json")
CACHE = Path(__file__).with_suffix(".cache.pkl")


def fetch(universe: list[str]):
    import yfinance as yf

    bars_by_symbol: dict[str, list[dict]] = {}
    events: list[dict] = []
    skipped: list[str] = []
    for i, sym in enumerate(universe):
        try:
            t = yf.Ticker(sym)
            hist = t.history(start=BARS_START, interval="1d",
                             auto_adjust=True)
            if hist is None or len(hist) < 260:
                skipped.append(f"{sym}:bars")
                continue
            bars = [{"date": idx.strftime("%Y-%m-%d"),
                     "open": float(r["Open"]), "high": float(r["High"]),
                     "low": float(r["Low"]), "close": float(r["Close"]),
                     "volume": float(r["Volume"])}
                    for idx, r in hist.iterrows()]
            ed = t.get_earnings_dates(limit=20)
            if ed is None or ed.empty:
                skipped.append(f"{sym}:earnings")
                continue
            last_bar = bars[-1]["date"]
            n_ev = 0
            for ts, erow in ed.iterrows():
                d = ts.strftime("%Y-%m-%d")
                if BARS_START < d < last_bar:
                    # yfinance carries the surprise inline — keep it for the
                    # SUE-qualified gate (plan section 12, revival path 1)
                    sp = erow.get("Surprise(%)")
                    try:
                        sp = float(sp)
                        if sp != sp:            # NaN
                            sp = None
                    except (TypeError, ValueError):
                        sp = None
                    events.append({"symbol": sym, "event_date": d,
                                   "surprise_pct": sp})
                    n_ev += 1
            if n_ev == 0:
                skipped.append(f"{sym}:no-past-events")
                continue
            bars_by_symbol[sym] = bars
        except Exception as exc:  # noqa: BLE001
            skipped.append(f"{sym}:{type(exc).__name__}")
        if (i + 1) % 20 == 0:
            print(f"  fetched {i + 1}/{len(universe)} "
                  f"({len(events)} events so far)", flush=True)
        time.sleep(0.4)
    return bars_by_symbol, events, skipped


def main() -> int:
    import pickle
    print(f"universe={len(UNIVERSE)} bars_start={BARS_START} "
          f"split={SPLIT_DATE} fee_side={FEE_SIDE}", flush=True)
    if CACHE.exists():
        bars, events, skipped = pickle.loads(CACHE.read_bytes())
        print(f"loaded cache: {len(bars)} symbols, {len(events)} events",
              flush=True)
    else:
        bars, events, skipped = fetch(UNIVERSE)
        CACHE.write_bytes(pickle.dumps((bars, events, skipped)))
    print(f"symbols with data: {len(bars)}  events: {len(events)}  "
          f"skipped: {len(skipped)}", flush=True)
    if len(events) < 300:
        print(f"WARNING: only {len(events)} events (< 300 target)", flush=True)

    result = {"universe": len(UNIVERSE), "symbols_with_data": len(bars),
              "events_total": len(events), "skipped": skipped,
              "fee_side": FEE_SIDE, "split_date": SPLIT_DATE, "runs": {}}
    for name, kwargs in (
            ("long_only", {"long_only": True}),
            ("long_only_stop5", {"long_only": True, "stop_pct": 5.0}),
            ("both_directions", {"long_only": False}),
            # the strategy as pead-drift actually specifies it: enter the
            # first pullback that HOLDS the gap, never chase the spike bar
            ("long_only_pullback", {"long_only": True,
                                    "entry_mode": "pullback"}),
            ("long_only_pullback_stop5", {"long_only": True, "stop_pct": 5.0,
                                          "entry_mode": "pullback"}),
            ("both_pullback", {"long_only": False,
                               "entry_mode": "pullback"})):
        r = bc.walk_forward(events, bars, split_date=SPLIT_DATE,
                            fee_side=FEE_SIDE, **kwargs)
        r.pop("test_trades", None)
        result["runs"][name] = r
        print(f"\n=== {name} ===", flush=True)
        print("chosen:", json.dumps(r["chosen"]), flush=True)
        print("train:", json.dumps(r["train"]), flush=True)
        print("test: ", json.dumps(r["test"]), flush=True)

    n_sue = sum(1 for e in events if e.get("surprise_pct") is not None)
    print(f"\nevents with surprise data: {n_sue}/{len(events)}", flush=True)
    for name, kwargs in (
            ("sue_long", {"long_only": True}),
            ("sue_long_stop5", {"long_only": True, "stop_pct": 5.0}),
            ("sue_both", {"long_only": False})):
        r = bc.walk_forward_sue(events, bars, split_date=SPLIT_DATE,
                                fee_side=FEE_SIDE, **kwargs)
        result["runs"][name] = r
        print(f"\n=== {name} ===", flush=True)
        print("chosen:", json.dumps(r["chosen"]), flush=True)
        print("train:", json.dumps(r["train"]), flush=True)
        print("test: ", json.dumps(r["test"]), flush=True)

    # SUE gate (plan section 12 path 1): judged on sue_long's untouched test
    g = result["runs"]["sue_long"]["test"]
    gate_pass = bool(
        g["n"] and g["n"] >= 50
        and (g["expectancy_pct"] or 0) > 0
        and (g["bootstrap_lb90_pct"] or 0) > 0
        and (g["profit_factor"] or 0) >= 1.2)
    result["gate0"] = {
        "criteria": ("test(sue_long): n>=50, expectancy>0, "
                     "bootstrap LB90>0, PF>=1.2"),
        "pass": gate_pass}
    OUT.write_text(json.dumps(result, indent=1))
    print(f"\nGATE 0 (long-only test window): {'PASS' if gate_pass else 'FAIL'}",
          flush=True)
    print(f"result written: {OUT}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
