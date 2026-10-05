#!/usr/bin/env python
"""R-LONG — crypto, long-only (PREREG section F).

    .venv/bin/python research/trend_replay/replay_long.py

Writes trades_RLONG_D.csv, trades_RLONG_V2.csv, long_result.json.
"""
from __future__ import annotations

import csv
import json

from replay_ext import judge, line, run
from replay_lib import COST_RATE, DAY_MS, HERE, RISK_USD, load_bars, round_floats, tm, write_trades

UNIVERSE = list(tm.DEFAULT_UNIVERSE)
YEARS = list(range(2020, 2027))


def same_as_csv(trades, name: str) -> bool:
    with (HERE / name).open() as fh:
        ref = sorted((r["symbol"], r["side"], r["signal_bar"], r["entry_ts"], r["exit_ts"],
                      r["exit_reason"], r["net_usd"]) for r in csv.DictReader(fh))
    mine = sorted((t["symbol"], t["side"], t["signal_bar"], t["entry_ts"], t["exit_ts"],
                   t["exit_reason"], repr(t["net_usd"])) for t in trades)
    return ref == mine


def vs_primary_longs(trades, primary_longs) -> dict:
    p = {(t["symbol"], t["signal_bar"]): t for t in primary_longs}
    v = {(t["symbol"], t["signal_bar"]): t for t in trades}
    both = set(p) & set(v)
    identical = [k for k in both if p[k]["exit_ts"] == v[k]["exit_ts"]
                 and abs(float(p[k]["net_usd"]) - v[k]["net_usd"]) < 0.005]
    changed = sorted(both - set(identical))
    only_p, only_v = sorted(set(p) - set(v)), sorted(set(v) - set(p))
    return {
        "primary_long_trades": len(p), "this_run_trades": len(v),
        "identical": len(identical),
        "same_entry_different_outcome": len(changed),
        "only_in_primary": len(only_p),
        "only_in_primary_net_R": sum(float(p[k]["net_usd"]) for k in only_p) / RISK_USD,
        "only_in_this_run": len(only_v),
        "only_in_this_run_net_R": sum(v[k]["net_usd"] for k in only_v) / RISK_USD,
        "only_in_this_run_list": [f"{k[0]} {k[1][:10]} {v[k]['R']:+.2f}R" for k in only_v],
        "only_in_primary_list": [f"{k[0]} {k[1][:10]} {float(p[k]['R']):+.2f}R" for k in only_p],
    }


def main() -> None:
    daily = {s: load_bars(s, "1D") for s in UNIVERSE}
    hourly = {s: load_bars(s, "1H") for s in UNIVERSE}
    kw = dict(close_offset_ms=DAY_MS, cost_rate=COST_RATE)

    # F5 self-checks: the generic engine reproduces both verified trade lists
    ok_p = same_as_csv(run(daily, UNIVERSE, **kw)["trades"], "trades.csv")
    ok_v2 = same_as_csv(run(daily, UNIVERSE, hourly=hourly, **kw)["trades"], "trades_V2.csv")
    if not (ok_p and ok_v2):
        raise SystemExit(f"SELF-CHECK FAILED primary={ok_p} V2={ok_v2}")
    print("self-check: generic engine reproduces trades.csv and trades_V2.csv exactly")

    with (HERE / "trades.csv").open() as fh:
        prim_longs = [r for r in csv.DictReader(fh) if r["side"] == "long"]
    with (HERE / "trades_V2.csv").open() as fh:
        v2_longs = [r for r in csv.DictReader(fh) if r["side"] == "long"]

    result = {"conventions": "PREREG.txt section F", "self_check": True}
    for name, hr, ref in (("R-LONG-D", None, prim_longs), ("R-LONG-V2", hourly, v2_longs)):
        r = run(daily, UNIVERSE, allow_short=False, hourly=hr, **kw)
        j = judge(r["trades"], daily, COST_RATE, YEARS, 5, r["span_years"])
        j["ignored_short_signal_bars"] = r["ignored_short_signals"]
        j["intraday_stop_exits"] = sum(1 for t in r["trades"] if t["exit_reason"] == "intraday_stop")
        j["vs_long_trades_of_both_sides_run"] = vs_primary_longs(r["trades"], ref)
        result[name] = j
        write_trades(HERE / f"trades_{name.replace('-', '').replace('RLONG', 'RLONG_')}.csv",
                     r["trades"], extra_cols=["stop_hour_bar"])
        print(line(name, j))
        c = j["vs_long_trades_of_both_sides_run"]
        print(f"    vs both-sides longs: identical {c['identical']}/{c['primary_long_trades']}, "
              f"changed {c['same_entry_different_outcome']}, only-primary {c['only_in_primary']} "
              f"({c['only_in_primary_net_R']:+.2f}R), new {c['only_in_this_run']} "
              f"({c['only_in_this_run_net_R']:+.2f}R); dd {j['drawdown']}; "
              f"streak {j['longest_losing_streak']}; tpy {j['trades_per_year']:.1f}; "
              f"2023+ {j['subset_entry_from_2023-01-01']}")
        print("    years:", j["by_exit_year"])
    (HERE / "long_result.json").write_text(json.dumps(round_floats(result), indent=2) + "\n")


if __name__ == "__main__":
    main()
