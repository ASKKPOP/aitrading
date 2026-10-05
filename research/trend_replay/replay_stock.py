#!/usr/bin/env python
"""R-STOCK — the trend rule on US stocks, daily bars (PREREG section G).

    .venv/bin/python research/trend_replay/replay_stock.py

Writes trades_STOCK_{U1,U2}_{LS,LO}.csv and stock_result.json.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from replay_ext import _recost, judge, line, load_stock, run
from replay_lib import HERE, HOUR_MS, RISK_USD, round_floats, write_trades

U1 = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AVGO", "AMD", "NFLX"]
U2 = ["AAPL", "AMGN", "AMZN", "AXP", "BA", "CAT", "CRM", "CSCO", "CVX", "DIS", "GOOGL",
      "GS", "HD", "HON", "IBM", "JNJ", "JPM", "KO", "MCD", "MMM", "MRK", "MSFT", "NKE",
      "NVDA", "PG", "SHW", "TRV", "UNH", "V", "WMT"]
YEARS = list(range(2015, 2027))
MIN_POS_YEARS = 9                      # >= 70% of 12 (8.4 -> 9)
COST = 3e-4                            # 1bp fee + 2bp slippage per side
COST_SENS = 5e-4                       # sensitivity: 5bp per side total
CLOSE_OFFSET = 6 * HOUR_MS + HOUR_MS // 2
FIRST_SIGNAL = int(datetime(2015, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)


def main() -> None:
    bars = {t: load_stock(t) for t in sorted(set(U1) | set(U2))}
    kw = dict(close_offset_ms=CLOSE_OFFSET, cost_rate=COST, first_signal_ts=FIRST_SIGNAL)
    result = {
        "conventions": "PREREG.txt section G",
        "data": {"source": "Yahoo chart API v8; O/H/L/C x adjclose/close (total return)",
                 "bars_per_symbol": len(bars["AAPL"]),
                 "first_bar": "2014-01-02 (warm-up)", "first_signal_allowed": "2015-01-01",
                 "last_bar": datetime.fromtimestamp(bars["AAPL"][-1]["ts"] / 1000,
                                                    timezone.utc).strftime("%Y-%m-%d")},
        "costs": {"fee_bp_per_side": 1, "slippage_bp_per_side": 2},
        "universes": {"U1": U1, "U2": U2},
    }
    for uname, uni in (("U1", U1), ("U2", U2)):
        for mode, allow_short in (("LS", True), ("LO", False)):
            name = f"{uname}_{mode}"
            r = run(bars, uni, allow_short=allow_short, **kw)
            j = judge(r["trades"], bars, COST, YEARS, MIN_POS_YEARS, r["span_years"],
                      first_signal_ts=FIRST_SIGNAL)
            j["ignored_short_signal_bars"] = r["ignored_short_signals"]
            # sensitivities (non-verdict): 5bp/side, reversed scan order
            hi = [_recost(dict(t), COST_SENS) for t in r["trades"]]
            j["sensitivity_5bp_per_side_net_R"] = sum(t["net_usd"] for t in hi) / RISK_USD
            rev = run(bars, list(reversed(uni)), allow_short=allow_short, **kw)["trades"]
            j["sensitivity_reversed_scan_order"] = {
                "n": len(rev), "net_R": sum(t["net_usd"] for t in rev) / RISK_USD}
            result[name] = j
            write_trades(HERE / f"trades_STOCK_{name}.csv", r["trades"])
            print(line(name, j))
            print(f"    years: {j['by_exit_year']}")
            print(f"    sides: { {k: (v['n'], round(v['net_R'], 2), v['payoff']) for k, v in j['by_side'].items()} }"
                  f" median {j['median_R']:.2f}R streak {j['longest_losing_streak']} "
                  f"tpy {j['trades_per_year']:.1f} cost {j['cost_R']:.2f}R "
                  f"5bp: {j['sensitivity_5bp_per_side_net_R']:.2f}R "
                  f"reversed: {j['sensitivity_reversed_scan_order']} "
                  f"2023+: {j['subset_entry_from_2023-01-01']}")
            print(f"    dd: {j['drawdown']}")
            print(f"    perm: {j['permutation']}")
    (HERE / "stock_result.json").write_text(json.dumps(round_floats(result), indent=2) + "\n")


if __name__ == "__main__":
    main()
