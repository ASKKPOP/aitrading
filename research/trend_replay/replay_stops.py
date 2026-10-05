#!/usr/bin/env python
"""Intraday-stop variants of the completed-bar replay (PREREG section E).

    .venv/bin/python research/trend_replay/replay_stops.py

  primary  no intraday stop (must reproduce trades.csv exactly — self-check)
  V2       module's own initial stop (entry -/+ 1.5xATR), enforced on 1H bars
  V3       foreign 5% stop written 2h after entry (orphan_reclaim.protect),
           enforced on 1H bars; module keeps a phantom slot until its own
           daily-close exit fires (trend_module.py:512-516)
  V3b      V3's stop with the slot freed at once (sensitivity)

Writes trades_V2.csv, trades_V3.csv, trades_V3b.csv, stops_result.json.
"""
from __future__ import annotations

import csv
import json
from typing import Any, Optional

from replay_lib import (DAY_MS, HERE, HOUR_MS, MAX_POS, RISK_USD, WINDOW, by_key,
                        close_trade, dt, iso, load_bars, new_position, round_floats,
                        summarize, tm, write_trades)

UNIVERSE = list(tm.DEFAULT_UNIVERSE)
FOREIGN_FRAC = 0.05                  # orphan_reclaim.default_stop_frac() default
FOREIGN_DELAY_MS = 2 * HOUR_MS       # ORPHAN_RECLAIM_AFTER_MIN default 120
YEARS = [str(y) for y in range(2020, 2027)]


def run(daily, hourly, mode: Optional[str]) -> dict[str, Any]:
    """mode: None | 'V2' | 'V3' | 'V3b'. Mirrors replay_lib.run_daily (B5)."""
    index = {s: {b["ts"]: i for i, b in enumerate(daily[s])} for s in UNIVERSE}
    h_by_day: dict[str, dict[int, list[dict[str, Any]]]] = {s: {} for s in UNIVERSE}
    h_at: dict[str, dict[int, dict[str, Any]]] = {s: {} for s in UNIVERSE}
    for s in UNIVERSE:
        for hb in hourly[s]:
            d = ((hb["ts"] - 16 * HOUR_MS) // DAY_MS) * DAY_MS + 16 * HOUR_MS
            h_by_day[s].setdefault(d, []).append(hb)
            h_at[s][hb["ts"]] = hb
    timeline = sorted({b["ts"] for s in UNIVERSE for b in daily[s]})
    positions: dict[str, dict[str, Any]] = {}
    signal_of: dict[str, int] = {}
    trades: list[dict[str, Any]] = []
    missing_hours = 0
    phantom_days = 0

    def window(sym, i):
        return daily[sym][max(0, i + 1 - WINDOW): i + 1]

    def set_stop(sym: str, pos: dict[str, Any]) -> None:
        """Compute the intraday stop for a fresh position."""
        entry = pos["entry_price"]
        if mode == "V2":
            pos["_stop"], pos["_stop_from"] = pos["initial_stop"], pos["_entry_ts_ms"]
        elif mode in ("V3", "V3b"):
            t0 = pos["_entry_ts_ms"] + FOREIGN_DELAY_MS
            hb = h_at[sym].get(t0)
            mark = hb["open"] if hb else entry          # no bar: entry is the only anchor
            if pos["side"] == "long":
                pos["_stop"] = min(entry, mark) * (1 - FOREIGN_FRAC)
            else:
                pos["_stop"] = max(entry, mark) * (1 + FOREIGN_FRAC)
            pos["_stop_from"] = t0
            pos["_mark_at_protect"] = mark

    for ts in timeline:
        close_time = dt(ts + DAY_MS)

        # (0) intraday stop on this daily bar's 1H bars (E2)
        if mode is not None:
            for sym in sorted(positions):
                pos = positions[sym]
                if pos.get("_ghost") or pos["_entry_ts_ms"] > ts or index[sym].get(ts) is None:
                    continue
                hrs = h_by_day[sym].get(ts, [])
                if len(hrs) != 24:
                    missing_hours += 24 - len(hrs)
                for hb in hrs:
                    if hb["ts"] < pos["_stop_from"]:
                        continue
                    stop = pos["_stop"]
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
                    tr["stop_price"] = stop
                    tr["stop_hour_bar"] = iso(hb["ts"])
                    trades.append(tr)
                    if mode == "V3":
                        pos["_ghost"] = True            # module still thinks it holds it
                    else:
                        del positions[sym]
                        del signal_of[sym]
                    break

        # (i) module's daily-close logic — trail update, exit check
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
            if pos.get("_ghost"):
                phantom_days += 1
            if not reason:
                continue
            if not pos.get("_ghost"):                    # ghost: sell refused -> state_desync
                if i + 1 < len(daily[sym]):
                    nxt = daily[sym][i + 1]
                    tr = close_trade(sym, pos, signal_of[sym], nxt["open"], nxt["ts"], reason, ts)
                else:
                    tr = close_trade(sym, pos, signal_of[sym], close, ts + DAY_MS,
                                     "end_of_data", ts)
                tr["stop_price"] = pos.get("_stop", "")
                tr["stop_hour_bar"] = ""
                trades.append(tr)
            del positions[sym]
            del signal_of[sym]

        # (ii) entries — identical to the primary
        for sym in UNIVERSE:
            if sym in positions:
                continue
            i = index[sym].get(ts)
            if i is None:
                continue
            if len(positions) >= MAX_POS:
                continue
            sig = tm.evaluate_symbol(window(sym, i), None)
            if sig is None or sig.get("blocked"):
                continue
            if i + 1 >= len(daily[sym]):
                continue
            nxt = daily[sym][i + 1]
            positions[sym] = new_position(sig["side"], sig, nxt["open"], nxt["ts"])
            signal_of[sym] = ts
            set_stop(sym, positions[sym])

    for sym in sorted(positions):
        pos = positions[sym]
        if pos.get("_ghost"):
            continue
        last = daily[sym][-1]
        # the last daily bar's hours were already scanned in step (0)
        tr = close_trade(sym, pos, signal_of[sym], last["close"], last["ts"] + DAY_MS,
                         "end_of_data", None)
        tr["stop_price"] = pos.get("_stop", "")
        tr["stop_hour_bar"] = ""
        trades.append(tr)
    trades.sort(key=lambda t: (t["_exit_ts_ms"], t["_entry_ts_ms"], t["symbol"]))
    return {"trades": trades, "missing_hours_while_open": missing_hours,
            "phantom_position_days": phantom_days}


def key(t) -> tuple[str, str, str]:
    return (t["symbol"], t["side"], t["signal_bar"])


def report(name: str, r: dict[str, Any], primary: list[dict[str, Any]]) -> dict[str, Any]:
    trades = r["trades"]
    s = summarize(trades)
    years = by_key(trades, lambda t: t["exit_ts"][:4])
    pos_years = [y for y in YEARS if years.get(y, {}).get("net_usd", 0.0) > 0]
    p_by_key = {key(t): t for t in primary}
    v_keys = {key(t) for t in trades}
    stopped = [t for t in trades if t["exit_reason"] == "intraday_stop"]
    paired = [(t, p_by_key[key(t)]) for t in stopped if key(t) in p_by_key]
    diffs = [(t["net_usd"] - p["net_usd"]) / RISK_USD for t, p in paired]
    eps = 0.005 / RISK_USD                                 # half a cent
    stopped_net = sum(t["net_usd"] for t in stopped) / RISK_USD
    out = {
        "n": s["n"], "net_R": s["net_R"], "payoff": s.get("payoff"),
        "win_rate": s.get("win_rate"), "median_R": s.get("median_R"),
        "positive_years": pos_years, "n_positive_years": len(pos_years),
        "by_exit_year_R": {y: [years.get(y, {}).get("n", 0),
                               years.get(y, {}).get("net_R", 0.0)] for y in YEARS},
        "max_dd_closed_R": s["drawdown"]["max_dd_R"], "drawdown": s["drawdown"],
        "net_R_ex_best_trade": s["net_R_ex_best_trade"], "best_trade_R": s["best_trade_R"],
        "worst_trade_R": s["worst_trade_R"],
        "longest_losing_streak": s["longest_losing_streak"],
        "by_exit_reason": by_key(trades, lambda t: t["exit_reason"]),
        "by_side": by_key(trades, lambda t: t["side"]),
        "intraday_stop": {
            "n_ended_by_intraday_stop": len(stopped),
            "their_net_R_in_this_variant": stopped_net,
            "n_paired_with_primary": len(paired),
            "n_unpaired": len(stopped) - len(paired),
            "paired_primary_net_R": sum(p["net_usd"] for _, p in paired) / RISK_USD,
            "paired_variant_net_R": sum(t["net_usd"] for t, _ in paired) / RISK_USD,
            "paired_diff_R_variant_minus_primary": sum(diffs),
            "n_better_than_primary": sum(1 for d in diffs if d > eps),
            "n_worse_than_primary": sum(1 for d in diffs if d < -eps),
            "n_equal": sum(1 for d in diffs if abs(d) <= eps),
            "paired_primary_winners_cut": sum(1 for _, p in paired if p["net_usd"] > 0),
            "paired_primary_winners_cut_net_R_lost": sum(
                (t["net_usd"] - p["net_usd"]) for t, p in paired if p["net_usd"] > 0) / RISK_USD,
            "paired_primary_losers_net_R_saved": sum(
                (t["net_usd"] - p["net_usd"]) for t, p in paired if p["net_usd"] <= 0) / RISK_USD,
            "largest_paired_loss_R": min(diffs) if diffs else None,
            "largest_paired_gain_R": max(diffs) if diffs else None,
            "paired_diff_R_ex_largest_abs": (sum(diffs) - max(diffs, key=abs)) if diffs else None,
        },
        "entry_set_vs_primary": {
            "in_both": len(v_keys & set(p_by_key)),
            "variant_only": len(v_keys - set(p_by_key)),
            "primary_only": len(set(p_by_key) - v_keys),
            "variant_only_net_R": sum(t["net_usd"] for t in trades
                                      if key(t) not in p_by_key) / RISK_USD,
            "primary_only_net_R": sum(p["net_usd"] for p in primary
                                      if key(p) not in v_keys) / RISK_USD,
        },
        "missing_hours_while_open": r["missing_hours_while_open"],
        "phantom_position_days": r["phantom_position_days"],
    }
    i = out["intraday_stop"]
    print(f"{name:8s} n={out['n']:3d} net={out['net_R']:7.2f}R payoff={out['payoff']:.2f} "
          f"win={out['win_rate']:.3f} yrs+={out['n_positive_years']}/7 "
          f"dd={out['max_dd_closed_R']:.1f}R exbest={out['net_R_ex_best_trade']:.2f}R | "
          f"stopped={i['n_ended_by_intraday_stop']} paired={i['n_paired_with_primary']} "
          f"diff={i['paired_diff_R_variant_minus_primary']:+.2f}R "
          f"(better {i['n_better_than_primary']}, worse {i['n_worse_than_primary']}, "
          f"equal {i['n_equal']}) unpaired={i['n_unpaired']} missing_h={out['missing_hours_while_open']}")
    return out


def main() -> None:
    daily = {s: load_bars(s, "1D") for s in UNIVERSE}
    hourly = {s: load_bars(s, "1H") for s in UNIVERSE}

    base = run(daily, hourly, None)
    with (HERE / "trades.csv").open() as fh:
        ref = sorted((r["symbol"], r["side"], r["signal_bar"], r["entry_ts"], r["exit_ts"],
                      r["exit_reason"], r["net_usd"]) for r in csv.DictReader(fh))
    mine = sorted((t["symbol"], t["side"], t["signal_bar"], t["entry_ts"], t["exit_ts"],
                   t["exit_reason"], repr(t["net_usd"])) for t in base["trades"])
    if ref != mine:
        raise SystemExit("SELF-CHECK FAILED: engine without stops does not reproduce trades.csv")
    print(f"self-check: engine with no intraday stop reproduces trades.csv exactly "
          f"({len(mine)} trades)")
    for t in base["trades"]:
        t["stop_price"], t["stop_hour_bar"] = "", ""

    result: dict[str, Any] = {
        "conventions": "PREREG.txt section E",
        "self_check_reproduces_trades_csv": True,
        "primary": report("primary", base, base["trades"]),
    }
    for mode in ("V2", "V3", "V3b"):
        r = run(daily, hourly, mode)
        result[mode] = report(mode, r, base["trades"])
        write_trades(HERE / f"trades_{mode}.csv", r["trades"],
                     extra_cols=["stop_price", "stop_hour_bar"])
    p, v3, v3b = result["primary"]["net_R"], result["V3"]["net_R"], result["V3b"]["net_R"]
    result["H_STOP"] = {
        "statement": "V3 net R is lower than the primary run's net R",
        "primary_net_R": p, "V3_net_R": v3, "V3b_net_R": v3b,
        "V3_minus_primary_R": v3 - p, "V3b_minus_primary_R": v3b - p,
        "verdict": "NOT FALSIFIED" if v3 < p else "FALSIFIED",
        "V3_and_V3b_same_side_of_primary": (v3 < p) == (v3b < p),
    }
    print("H-STOP:", json.dumps(round_floats(result["H_STOP"], 3)))
    (HERE / "stops_result.json").write_text(json.dumps(round_floats(result), indent=2) + "\n")


if __name__ == "__main__":
    main()
