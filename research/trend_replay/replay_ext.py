"""Generic completed-bar engine for the R-LONG and R-STOCK runs (PREREG F, G).

Same decision logic as replay_lib.run_daily / replay_stops.run (every
decision delegated to trend_module's pure functions), parameterised by:
bar length, cost rate, whether short signals are taken, an optional V2
intraday stop on 1H bars, and the first date a signal may be taken.
replay_long.py proves it reproduces trades.csv and trades_V2.csv exactly.
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
from typing import Any, Optional

import numpy as np

from replay_lib import (DATA, DAY_MS, HOUR_MS, MAX_POS, RISK_USD, WINDOW, by_key,
                        close_trade, dt, iso, new_position, summarize, tm)

SEED = 20261005
N_SHUFFLES = 5000


def _recost(tr: dict[str, Any], cost_rate: float) -> dict[str, Any]:
    tr["cost_usd"] = cost_rate * tr["qty"] * (tr["entry_price"] + tr["exit_price"])
    tr["net_usd"] = tr["gross_usd"] - tr["cost_usd"]
    tr["R"] = tr["net_usd"] / RISK_USD
    return tr


def run(bars: dict[str, list[dict[str, Any]]], universe: list[str], *,
        close_offset_ms: int, cost_rate: float, allow_short: bool = True,
        hourly: Optional[dict[str, list[dict[str, Any]]]] = None,
        first_signal_ts: Optional[int] = None) -> dict[str, Any]:
    index = {s: {b["ts"]: i for i, b in enumerate(bars[s])} for s in universe}
    timeline = sorted({b["ts"] for s in universe for b in bars[s]})
    h_by_day: dict[str, dict[int, list[dict[str, Any]]]] = {}
    if hourly is not None:
        for s in universe:
            m: dict[int, list[dict[str, Any]]] = {}
            for hb in hourly[s]:
                d = ((hb["ts"] - 16 * HOUR_MS) // DAY_MS) * DAY_MS + 16 * HOUR_MS
                m.setdefault(d, []).append(hb)
            h_by_day[s] = m
    positions: dict[str, dict[str, Any]] = {}
    signal_of: dict[str, int] = {}
    trades: list[dict[str, Any]] = []
    ignored_short_signals = 0
    first_eligible: Optional[int] = None

    def window(sym, i):
        return bars[sym][max(0, i + 1 - WINDOW): i + 1]

    def book(tr, x_bar_ts, x_kind):
        tr["_x_bar_ts"], tr["_x_kind"] = x_bar_ts, x_kind
        trades.append(_recost(tr, cost_rate))

    for ts in timeline:
        close_time = dt(ts + close_offset_ms)

        if hourly is not None:                       # V2 intraday stop (PREREG E2/E3)
            for sym in sorted(positions):
                pos = positions[sym]
                if pos["_entry_ts_ms"] > ts or index[sym].get(ts) is None:
                    continue
                stop = pos["initial_stop"]
                for hb in h_by_day[sym].get(ts, []):
                    if hb["ts"] < pos["_entry_ts_ms"]:
                        continue
                    if pos["side"] == "long":
                        if hb["low"] > stop:
                            continue
                        px = min(stop, hb["open"])
                    else:
                        if hb["high"] < stop:
                            continue
                        px = max(stop, hb["open"])
                    tr = close_trade(sym, pos, signal_of[sym], px, hb["ts"] + HOUR_MS,
                                     "intraday_stop", None)
                    tr["stop_hour_bar"] = iso(hb["ts"])
                    book(tr, ts, "close")
                    del positions[sym]
                    del signal_of[sym]
                    break

        for sym in sorted(positions):
            i = index[sym].get(ts)
            if i is None:
                continue
            pos = positions[sym]
            if pos["_entry_ts_ms"] > ts:
                continue
            highs, lows, closes = tm._series(window(sym, i))
            atr = tm.wilder_atr(highs, lows, closes)
            if not closes or not atr or atr <= 0:
                continue
            close = closes[-1]
            tm.update_trail(pos, close, atr)
            reason = tm.check_exit(pos, close, now=close_time)
            if not reason:
                continue
            if i + 1 < len(bars[sym]):
                nxt = bars[sym][i + 1]
                tr = close_trade(sym, pos, signal_of[sym], nxt["open"], nxt["ts"], reason, ts)
                tr["stop_hour_bar"] = ""
                book(tr, nxt["ts"], "open")
            else:
                tr = close_trade(sym, pos, signal_of[sym], close, ts + close_offset_ms,
                                 "end_of_data", ts)
                tr["stop_hour_bar"] = ""
                book(tr, ts, "close")
            del positions[sym]
            del signal_of[sym]

        if first_signal_ts is not None and ts < first_signal_ts:
            continue
        for sym in universe:
            if sym in positions:
                continue
            i = index[sym].get(ts)
            if i is None:
                continue
            w = window(sym, i)
            if len(w) >= tm.MIN_BARS and first_eligible is None:
                first_eligible = ts
            if len(positions) >= MAX_POS:
                break
            sig = tm.evaluate_symbol(w, None)
            if sig is None or sig.get("blocked"):
                continue
            if sig["side"] == "short" and not allow_short:
                ignored_short_signals += 1
                continue
            if i + 1 >= len(bars[sym]):
                continue
            nxt = bars[sym][i + 1]
            positions[sym] = new_position(sig["side"], sig, nxt["open"], nxt["ts"])
            signal_of[sym] = ts

    for sym in sorted(positions):
        last = bars[sym][-1]
        tr = close_trade(sym, positions[sym], signal_of[sym], last["close"],
                         last["ts"] + close_offset_ms, "end_of_data", None)
        tr["stop_hour_bar"] = ""
        book(tr, last["ts"], "close")
    trades.sort(key=lambda t: (t["_exit_ts_ms"], t["_entry_ts_ms"], t["symbol"]))
    return {"trades": trades, "ignored_short_signals": ignored_short_signals,
            "first_eligible_ts": first_eligible, "last_bar_ts": timeline[-1],
            "span_years": (timeline[-1] + close_offset_ms
                           - (first_eligible or timeline[0])) / DAY_MS / 365.25}


def permutation(trades, bars, cost_rate: float,
                first_signal_ts: Optional[int] = None) -> dict[str, Any]:
    """PREREG B10 (+F3 for intraday-stop trades, +G6 start restriction)."""
    rng = np.random.default_rng(SEED)
    prep = {}
    for sym in sorted({t["symbol"] for t in trades}):
        bl = bars[sym]
        opens = np.array([b["open"] for b in bl])
        closes = np.array([b["close"] for b in bl])
        atr_prev = np.full(len(bl), np.nan)
        lo = tm.MIN_BARS
        if first_signal_ts is not None:
            lo = max(lo, next(i for i, b in enumerate(bl) if b["ts"] >= first_signal_ts) + 1)
        for s in range(lo, len(bl)):
            highs, lows, cl = tm._series(bl[max(0, s - WINDOW): s])
            atr_prev[s] = tm.wilder_atr(highs, lows, cl)
        prep[sym] = (opens, closes, atr_prev, {b["ts"]: i for i, b in enumerate(bl)}, lo)
    totals = np.zeros(N_SHUFFLES)
    observed = 0.0
    for t in trades:
        opens, closes, atr_prev, idx, lo = prep[t["symbol"]]
        e = idx[t["_entry_ts_ms"]]
        direction = 1.0 if t["side"] == "long" else -1.0
        x = idx[t["_x_bar_ts"]]
        exit_arr = opens if t["_x_kind"] == "open" else closes
        length = x - e
        starts = rng.integers(lo, len(opens) - length, size=N_SHUFFLES)
        qty = RISK_USD / (tm.STOP_ATR_MULT * atr_prev[starts])
        p_in, p_out = opens[starts], exit_arr[starts + length]
        totals += qty * (p_out - p_in) * direction - cost_rate * qty * (p_in + p_out)
        observed += t["net_usd"]
    ge = int((totals >= observed).sum())
    return {"n_trades": len(trades), "n_shuffles": N_SHUFFLES, "seed": SEED,
            "observed_net_R": observed / RISK_USD,
            "null_mean_R": float(totals.mean()) / RISK_USD,
            "null_sd_R": float(totals.std(ddof=1)) / RISK_USD,
            "null_p95_R": float(np.percentile(totals, 95)) / RISK_USD,
            "null_ge_observed": ge, "p_one_sided": (1 + ge) / (1 + N_SHUFFLES)}


def judge(trades, bars, cost_rate: float, years: list[int], min_pos_years: int,
          span_years: float, first_signal_ts: Optional[int] = None,
          subset_from: str = "2023-01-01") -> dict[str, Any]:
    """Five criteria + the reported figures, for one run."""
    if not trades:
        return {"verdict": "FALSIFIED", "n": 0, "criteria_failed": ["no trades"]}
    s = summarize(trades, span_years)
    ytab = by_key(trades, lambda t: t["exit_ts"][:4])
    by_year = {str(y): ytab.get(str(y), {"n": 0, "net_usd": 0.0, "net_R": 0.0, "wins": 0})
               for y in years}
    pos_years = [y for y, v in by_year.items() if v["net_usd"] > 0]
    symbols = by_key(trades, lambda t: t["symbol"])
    best_symbol = max(symbols, key=lambda k: symbols[k]["net_usd"])
    best = max(trades, key=lambda t: t["net_usd"])
    net_ex_trade = s["net_usd"] - best["net_usd"]
    net_ex_symbol = s["net_usd"] - symbols[best_symbol]["net_usd"]
    perm = permutation(trades, bars, cost_rate, first_signal_ts)
    crit = {
        "1_net_positive": s["net_usd"] > 0,
        "2_payoff_ge_1.5": s["payoff"] is not None and s["payoff"] >= 1.5,
        "3_survives_best_trade_and_best_symbol_removed": net_ex_trade > 0 and net_ex_symbol > 0,
        f"4_at_least_{min_pos_years}_of_{len(years)}_years_positive": len(pos_years) >= min_pos_years,
        "5_permutation_p_lt_0.05": perm["p_one_sided"] < 0.05,
    }
    failed = [k for k, v in crit.items() if not v]
    verdict = ("NOT FALSIFIED" if not failed else
               "FALSIFIED" if not crit["1_net_positive"] else "INCONCLUSIVE")
    sub = [t for t in trades if t["entry_ts"] >= subset_from]
    sides = {k: [t for t in trades if t["side"] == k] for k in ("long", "short")}
    return {
        "verdict": verdict, "criteria": crit, "criteria_failed": failed,
        "n": s["n"], "net_R": s["net_R"], "payoff": s["payoff"], "win_rate": s["win_rate"],
        "median_R": s["median_R"], "mean_R": s["mean_R"],
        "n_positive_years": len(pos_years), "n_years": len(years), "positive_years": pos_years,
        "by_exit_year": {y: [v["n"], round(v["net_R"], 4)] for y, v in by_year.items()},
        "max_dd_closed_R": s["drawdown"]["max_dd_R"], "drawdown": s["drawdown"],
        "longest_losing_streak": s["longest_losing_streak"],
        "longest_losing_streak_span": s["longest_losing_streak_span"],
        "trades_per_year": s.get("trades_per_year"),
        "best_trade": {"symbol": best["symbol"], "side": best["side"],
                       "entry_ts": best["entry_ts"], "R": best["R"]},
        "net_R_ex_best_trade": net_ex_trade / RISK_USD,
        "best_symbol": best_symbol, "net_R_ex_best_symbol": net_ex_symbol / RISK_USD,
        "by_symbol": {k: [v["n"], round(v["net_R"], 4)] for k, v in symbols.items()},
        "by_side": {k: {"n": len(v), "net_R": sum(t["net_usd"] for t in v) / RISK_USD,
                        "payoff": summarize(v).get("payoff") if v else None}
                    for k, v in sides.items()},
        "by_exit_reason": {k: [v["n"], round(v["net_R"], 4)]
                           for k, v in by_key(trades, lambda t: t["exit_reason"]).items()},
        "cost_R": s["cost_usd"] / RISK_USD, "gross_R": s["gross_usd"] / RISK_USD,
        f"subset_entry_from_{subset_from}": (
            {k: summarize(sub)[k] for k in ("n", "net_R", "payoff", "win_rate",
                                           "net_R_ex_best_trade")} if sub else {"n": 0}),
        "permutation": perm,
    }


def line(name: str, j: dict[str, Any]) -> str:
    return (f"{name:16s} n={j['n']:3d} net={j['net_R']:8.2f}R payoff={j['payoff']:.2f} "
            f"win={j['win_rate']:.3f} yrs+={j['n_positive_years']}/{j['n_years']} "
            f"dd={j['max_dd_closed_R']:.1f}R exbest={j['net_R_ex_best_trade']:.2f}R "
            f"exsym({j['best_symbol']})={j['net_R_ex_best_symbol']:.2f}R "
            f"p={j['permutation']['p_one_sided']:.4f} -> {j['verdict']} {j['criteria_failed']}")


def load_stock(ticker: str) -> list[dict[str, Any]]:
    """Yahoo raw -> total-return adjusted O/H/L/C (PREREG G3). Bar ts is a
    nominal 14:30 UTC session open on the session date; close = +6.5h."""
    out = []
    with (DATA / f"yahoo_{ticker}_1D.csv").open() as fh:
        for r in csv.DictReader(fh):
            f = float(r["adjclose"]) / float(r["close"])
            day = datetime.strptime(r["date"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
            out.append({"ts": int(day.timestamp() * 1000) + 14 * HOUR_MS + HOUR_MS // 2,
                        "open": float(r["open"]) * f, "high": float(r["high"]) * f,
                        "low": float(r["low"]) * f, "close": float(r["close"]) * f})
    for a, b in zip(out, out[1:]):
        if b["ts"] <= a["ts"]:
            raise ValueError(f"{ticker}: non-increasing dates")
    return out
