#!/usr/bin/env python
"""Completed-daily-bar replay of the trend module + the pre-registered
verdict (PREREG.txt section A/B). Reads only research/trend_replay/data/.

    .venv/bin/python research/trend_replay/replay_daily.py

Writes trades.csv and result.json (deterministic: no wall-clock in output).
"""
from __future__ import annotations

import json

import numpy as np

import csv
from datetime import datetime, timezone

from replay_lib import (COST_RATE, DATA, DAY_MS, HERE, MAX_POS, RISK_USD, WINDOW,
                        by_key, curve_drawdown, iso, load_bars, load_fng, round_floats,
                        run_daily, summarize, tm, write_trades)

SEED = 20261005
N_SHUFFLES = 5000
YEARS = [2020, 2021, 2022, 2023, 2024, 2025, 2026]


def permutation_null(trades, bars) -> dict:
    """PREREG B10."""
    rng = np.random.default_rng(SEED)
    prep = {}
    for sym, bl in bars.items():
        opens = np.array([b["open"] for b in bl])
        closes = np.array([b["close"] for b in bl])
        atr_prev = np.full(len(bl), np.nan)
        for s in range(tm.MIN_BARS, len(bl)):
            w = bl[max(0, s - WINDOW): s]           # window ending the bar before s
            highs, lows, cl = tm._series(w)
            atr_prev[s] = tm.wilder_atr(highs, lows, cl)
        prep[sym] = (opens, closes, atr_prev, {b["ts"]: i for i, b in enumerate(bl)})
    totals = np.zeros(N_SHUFFLES)
    observed = 0.0
    recomputed = 0.0
    for t in trades:
        opens, closes, atr_prev, idx = prep[t["symbol"]]
        e = idx[t["_entry_ts_ms"]]
        direction = 1.0 if t["side"] == "long" else -1.0
        if t["exit_reason"] == "end_of_data":
            x = idx[t["_exit_ts_ms"] - DAY_MS]       # exit at that bar's CLOSE
            exit_arr = closes
        else:
            x = idx[t["_exit_ts_ms"]]                # exit at that bar's OPEN
            exit_arr = opens
        length = x - e
        lo, hi = tm.MIN_BARS, len(opens) - 1 - length   # inclusive start range
        starts = rng.integers(lo, hi + 1, size=N_SHUFFLES)
        qty = RISK_USD / (tm.STOP_ATR_MULT * atr_prev[starts])
        p_in, p_out = opens[starts], exit_arr[starts + length]
        totals += qty * (p_out - p_in) * direction - COST_RATE * qty * (p_in + p_out)
        observed += t["net_usd"]
        # self-check: the null's arithmetic reproduces the real trade at its real start
        q0 = RISK_USD / (tm.STOP_ATR_MULT * atr_prev[e])
        recomputed += (q0 * (exit_arr[x] - opens[e]) * direction
                       - COST_RATE * q0 * (opens[e] + exit_arr[x]))
    ge = int((totals >= observed).sum())
    return {
        "n_trades": len(trades), "n_shuffles": N_SHUFFLES, "seed": SEED,
        "observed_net_usd": observed,
        "selfcheck_recomputed_net_usd": recomputed,
        "null_mean_usd": float(totals.mean()), "null_sd_usd": float(totals.std(ddof=1)),
        "null_p05_usd": float(np.percentile(totals, 5)),
        "null_p50_usd": float(np.percentile(totals, 50)),
        "null_p95_usd": float(np.percentile(totals, 95)),
        "null_ge_observed": ge,
        "p_one_sided": (1 + ge) / (1 + N_SHUFFLES),
    }


def common_shift_null(trades, bars) -> dict:
    """POST-HOC (not pre-registered; added after the primary result was seen,
    because B10 draws each trade independently and so ignores that real trades
    cluster in the same market episodes). Every trade is moved by ONE common
    number of days (circularly inside its symbol's eligible range), which
    keeps the cross-symbol / cross-trade clustering intact. All possible
    shifts are enumerated — no randomness."""
    prep = {}
    for sym, bl in bars.items():
        opens = np.array([b["open"] for b in bl])
        closes = np.array([b["close"] for b in bl])
        atr_prev = np.full(len(bl), np.nan)
        for s in range(tm.MIN_BARS, len(bl)):
            highs, lows, cl = tm._series(bl[max(0, s - WINDOW): s])
            atr_prev[s] = tm.wilder_atr(highs, lows, cl)
        prep[sym] = (opens, closes, atr_prev, {b["ts"]: i for i, b in enumerate(bl)})
    n_shift = max(len(bl) for bl in bars.values()) - tm.MIN_BARS
    shifts = np.arange(1, n_shift)
    totals = np.zeros(len(shifts))
    observed = 0.0
    for t in trades:
        opens, closes, atr_prev, idx = prep[t["symbol"]]
        e = idx[t["_entry_ts_ms"]]
        direction = 1.0 if t["side"] == "long" else -1.0
        if t["exit_reason"] == "end_of_data":
            x, exit_arr = idx[t["_exit_ts_ms"] - DAY_MS], closes
        else:
            x, exit_arr = idx[t["_exit_ts_ms"]], opens
        length = x - e
        lo = tm.MIN_BARS
        m = len(opens) - length - lo                 # number of eligible starts
        starts = lo + (e - lo + shifts) % m
        qty = RISK_USD / (tm.STOP_ATR_MULT * atr_prev[starts])
        p_in, p_out = opens[starts], exit_arr[starts + length]
        totals += qty * (p_out - p_in) * direction - COST_RATE * qty * (p_in + p_out)
        observed += t["net_usd"]
    ge = int((totals >= observed).sum())
    return {"post_hoc": True, "n_trades": len(trades), "n_shifts": int(len(shifts)),
            "observed_net_usd": observed, "null_mean_usd": float(totals.mean()),
            "null_sd_usd": float(totals.std(ddof=1)),
            "null_p95_usd": float(np.percentile(totals, 95)),
            "null_max_usd": float(totals.max()),
            "null_ge_observed": ge, "p_one_sided": (1 + ge) / (1 + len(shifts))}


def funding_sensitivity(trades, bars) -> dict:
    """POST-HOC S4: perp funding is a real cost the candle replay cannot see.
    BitMEX 8h funding is used as a cross-venue PROXY (OKX history is not
    public that far back). Long pays a positive rate, short receives it.
    Stamps the proxy does not cover are charged at the 0.01%/8h baseline."""
    out_rows = []
    total = 0.0
    missing = 0
    stamps_all = {}
    for sym in bars:
        path = DATA / f"bitmex_funding_{sym}.csv"
        if not path.exists():
            return {"available": False}
        with path.open() as fh:
            stamps_all[sym] = sorted(
                (int(datetime.strptime(r["timestamp_utc"][:19], "%Y-%m-%dT%H:%M:%S")
                     .replace(tzinfo=timezone.utc).timestamp() * 1000), float(r["funding_rate"]))
                for r in csv.DictReader(fh))
    eight_h = 8 * 3_600_000
    for t in trades:
        sym = t["symbol"]
        rates = dict(stamps_all[sym])
        idx = {b["ts"]: i for i, b in enumerate(bars[sym])}
        direction = 1.0 if t["side"] == "long" else -1.0
        paid = 0.0
        grid = sorted(ts for ts in rates if t["_entry_ts_ms"] < ts <= t["_exit_ts_ms"])
        expected = int((t["_exit_ts_ms"] - t["_entry_ts_ms"]) // eight_h)
        for ts in grid:
            day_ts = ((ts - 16 * 3_600_000) // DAY_MS) * DAY_MS + 16 * 3_600_000
            i = idx.get(day_ts)
            px = bars[sym][i]["open"] if i is not None else t["entry_price"]
            paid += rates[ts] * t["qty"] * px * direction
        gap = max(0, expected - len(grid))
        if gap:
            missing += gap
            paid += gap * 0.0001 * t["qty"] * t["entry_price"] * direction
        total += paid
        out_rows.append((t, paid))
    net_after = [(t, t["net_usd"] - paid) for t, paid in out_rows]
    years = {}
    for t, v in net_after:
        years.setdefault(t["exit_ts"][:4], 0.0)
        years[t["exit_ts"][:4]] += v / RISK_USD
    wins = [v for _, v in net_after if v > 0]
    losses = [v for _, v in net_after if v <= 0]
    return {"available": True, "post_hoc": True, "proxy": "BitMEX 8h funding (cross-venue)",
            "funding_paid_usd": total, "funding_paid_R": total / RISK_USD,
            "funding_paid_R_long": sum(p for t, p in out_rows if t["side"] == "long") / RISK_USD,
            "funding_paid_R_short": sum(p for t, p in out_rows if t["side"] == "short") / RISK_USD,
            "stamps_filled_with_baseline": missing,
            "net_R_after_funding": sum(v for _, v in net_after) / RISK_USD,
            "payoff_after_funding": (sum(wins) / len(wins)) / abs(sum(losses) / len(losses)),
            "net_R_after_funding_ex_best_trade":
                (sum(v for _, v in net_after) - max(v for _, v in net_after)) / RISK_USD,
            "by_exit_year_R_after_funding": dict(sorted(years.items()))}


def year_table(trades) -> dict:
    tab = by_key(trades, lambda t: t["exit_ts"][:4])
    return {str(y): tab.get(str(y), {"n": 0, "net_usd": 0.0, "net_R": 0.0, "wins": 0})
            for y in YEARS}


def main() -> None:
    universe = list(tm.DEFAULT_UNIVERSE)
    bars = {s: load_bars(s, "1D") for s in universe}
    run = run_daily(bars, universe, fill_mode="next_open", fng=None)
    trades = run["trades"]
    span_years = (run["last_bar_ts"] + DAY_MS - run["first_eligible_ts"]) / DAY_MS / 365.25

    overall = summarize(trades, span_years)
    years = year_table(trades)
    symbols = by_key(trades, lambda t: t["symbol"])
    best_symbol = max(symbols, key=lambda s: symbols[s]["net_usd"])
    best_trade = max(trades, key=lambda t: t["net_usd"])
    ex_best_trade = [t for t in trades if t is not best_trade]
    ex_best_symbol = [t for t in trades if t["symbol"] != best_symbol]
    perm = permutation_null(trades, bars)
    perm_shift = common_shift_null(trades, bars)
    funding = funding_sensitivity(trades, bars)

    c1 = overall["net_usd"] > 0
    c2 = overall["payoff"] is not None and overall["payoff"] >= 1.5
    net_ex_trade = sum(t["net_usd"] for t in ex_best_trade)
    net_ex_symbol = sum(t["net_usd"] for t in ex_best_symbol)
    c3 = net_ex_trade > 0 and net_ex_symbol > 0
    pos_years = [y for y, v in years.items() if v["net_usd"] > 0]
    c4 = len(pos_years) >= 5
    c5 = perm["p_one_sided"] < 0.05
    crit = {"1_net_positive": c1, "2_payoff_ge_1.5": c2,
            "3_survives_best_trade_and_best_symbol_removed": c3,
            "4_at_least_5_of_7_years_positive": c4, "5_permutation_p_lt_0.05": c5}
    failed = [k for k, v in crit.items() if not v]
    verdict = "NOT FALSIFIED" if not failed else ("FALSIFIED" if not c1 else "INCONCLUSIVE")

    closed_only = [t for t in trades if t["exit_reason"] != "end_of_data"]
    since_2023 = [t for t in trades if t["entry_ts"] >= "2023-01-01"]

    # secondary, non-verdict runs (PREREG B13)
    fng = load_fng()
    s1 = run_daily(bars, universe, fill_mode="next_open", fng=fng)["trades"]
    s2 = run_daily(bars, universe, fill_mode="signal_close", fng=None)["trades"]
    uni3 = [s for s in universe if s != best_symbol]
    s3 = run_daily(bars, uni3, fill_mode="next_open", fng=None)["trades"]

    meta = json.loads((DATA / "fetch_meta_1D.json").read_text())
    result = {
        "hypothesis": "H-TREND (see PREREG.txt)",
        "verdict": verdict, "criteria": crit, "criteria_failed": failed,
        "config": {
            "universe": universe, "risk_usd": RISK_USD, "max_positions": MAX_POS,
            "window_bars": WINDOW, "fee_bp_per_side": 4.5, "slippage_bp_per_side": 5.0,
            "fill": "next daily bar open", "fear_greed": None, "llm_veto": "skipped (fail-open default)",
            "bar": "OKX USDT-SWAP 1D, opens 16:00 UTC, confirmed bars only",
        },
        "data": {s: {"bars": len(bars[s]), "first_bar": iso(bars[s][0]["ts"]),
                     "last_bar": iso(bars[s][-1]["ts"]),
                     "first_eligible_bar": iso(bars[s][tm.MIN_BARS - 1]["ts"])}
                 for s in universe},
        "data_fetched_at_utc": meta["fetched_at_utc"],
        "span": {"first_eligible_bar": iso(run["first_eligible_ts"]),
                 "last_bar": iso(run["last_bar_ts"]), "years": span_years},
        "signals": {"entry_signals_taken_or_dropped": run["signals_seen"],
                    "dropped_no_next_open": run["dropped_last_bar"],
                    "signal_bars_suppressed_by_position_cap": run["slot_blocked"]},
        "overall": overall,
        "criterion_3": {
            "best_trade": {"symbol": best_trade["symbol"], "side": best_trade["side"],
                           "entry_ts": best_trade["entry_ts"], "R": best_trade["R"]},
            "net_R_ex_best_trade": net_ex_trade / RISK_USD, "n_ex_best_trade": len(ex_best_trade),
            "best_symbol": best_symbol,
            "net_R_ex_best_symbol": net_ex_symbol / RISK_USD, "n_ex_best_symbol": len(ex_best_symbol),
        },
        "by_exit_year": years, "positive_years": pos_years,
        "by_symbol": symbols,
        "by_side": {k: summarize(v) for k, v in
                    (("long", [t for t in trades if t["side"] == "long"]),
                     ("short", [t for t in trades if t["side"] == "short"]))},
        "by_exit_reason": by_key(trades, lambda t: t["exit_reason"]),
        "subset_entry_2023_onward": summarize(since_2023),
        "subset_entry_2023_onward_by_year": by_key(since_2023, lambda t: t["exit_ts"][:4]),
        "excluding_end_of_data_trades": summarize(closed_only),
        "permutation": perm,
        "drawdown_mark_to_market_daily": curve_drawdown(run["mtm"]),
        "post_hoc_not_preregistered": {
            "common_shift_null": perm_shift,
            "S4_funding_proxy": funding,
        },
        "secondary_non_verdict": {
            "S1_fear_greed_overlay_on": {**summarize(s1),
                                         "by_entry_kind": by_key(s1, lambda t: t["entry_kind"]),
                                         "by_exit_year": by_key(s1, lambda t: t["exit_ts"][:4])},
            "S2_fill_at_signal_close": {**summarize(s2),
                                        "by_exit_year": by_key(s2, lambda t: t["exit_ts"][:4])},
            f"S3_universe_without_{best_symbol}": summarize(s3),
        },
    }
    write_trades(HERE / "trades.csv", trades)
    write_trades(HERE / "trades_S1_fng.csv", s1)
    (HERE / "result.json").write_text(json.dumps(round_floats(result), indent=2) + "\n")

    o = overall
    print(f"VERDICT: {verdict}   failed: {failed}")
    print(f"n={o['n']} net={o['net_R']:.2f}R (${o['net_usd']:.2f}) gross=${o['gross_usd']:.2f} "
          f"cost=${o['cost_usd']:.2f} win={o['win_rate']:.3f} payoff={o['payoff']:.3f} "
          f"median={o['median_R']:.3f}R mean={o['mean_R']:.3f}R tpy={o['trades_per_year']:.1f}")
    print("years:", {y: (v["n"], round(v["net_R"], 2)) for y, v in years.items()})
    print("symbols:", {s: (v["n"], round(v["net_R"], 2)) for s, v in symbols.items()})
    print(f"ex best trade: {net_ex_trade / RISK_USD:.2f}R  ex best symbol ({best_symbol}): "
          f"{net_ex_symbol / RISK_USD:.2f}R")
    print("drawdown:", round_floats(o["drawdown"], 2), "streak:", o["longest_losing_streak"])
    for k, v in result["by_side"].items():
        print(k, v.get("n"), round(v.get("net_R", 0), 2), v.get("payoff"))
    s23 = result["subset_entry_2023_onward"]
    print(f"2023+: n={s23['n']} net={s23['net_R']:.2f}R payoff={s23.get('payoff')}")
    print("perm:", round_floats(perm, 3))
    print("mtm dd:", round_floats(result["drawdown_mark_to_market_daily"], 2))
    print("post-hoc common-shift null:", round_floats(perm_shift, 3))
    print("post-hoc funding proxy:", round_floats(funding, 2))
    print("S1 by year:", {k: (v["n"], round(v["net_R"], 2)) for k, v in
                          result["secondary_non_verdict"]["S1_fear_greed_overlay_on"]["by_exit_year"].items()})
    for k, v in result["secondary_non_verdict"].items():
        print(k, v["n"], round(v["net_R"], 2), v.get("payoff"))


if __name__ == "__main__":
    main()
