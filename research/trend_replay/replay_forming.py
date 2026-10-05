#!/usr/bin/env python
"""Forming-bar replay (PREREG section C): the same rule, evaluated the way the
live loop evaluates it — every hour, on a window whose last bar is the
still-forming daily bar — and compared with the completed-bar replay.

    .venv/bin/python research/trend_replay/replay_forming.py

Needs trades.csv from replay_daily.py. Writes trades_forming_hourly.csv and
forming_result.json (deterministic).
"""
from __future__ import annotations

import csv
import json
from typing import Any, Optional

from replay_lib import (DAY_MS, HERE, HOUR_MS, MAX_POS, RISK_USD, WINDOW, by_key,
                        close_trade, dt, iso, load_bars, new_position, round_floats,
                        summarize, tm, write_trades)

OFFSET_16H = 16 * HOUR_MS
UNIVERSE = list(tm.DEFAULT_UNIVERSE)


def day_of(ts_ms: int) -> int:
    """Open time of the OKX '1D' bar (16:00 UTC) that contains ts_ms."""
    return ((ts_ms - OFFSET_16H) // DAY_MS) * DAY_MS + OFFSET_16H


def run_forming(daily, hourly, every: int = 1, phase: int = 0) -> dict[str, Any]:
    d_index = {s: {b["ts"]: i for i, b in enumerate(daily[s])} for s in UNIVERSE}
    h_index = {s: {b["ts"]: i for i, b in enumerate(hourly[s])} for s in UNIVERSE}
    timeline = sorted({b["ts"] for s in UNIVERSE for b in hourly[s]})
    forming: dict[str, Optional[dict[str, Any]]] = {s: None for s in UNIVERSE}
    positions: dict[str, dict[str, Any]] = {}
    meta: dict[str, dict[str, Any]] = {}
    trades: list[dict[str, Any]] = []
    entry_keys: set[tuple[str, str, str]] = set()   # trend:{agent}:{sym}:{side}:{utc date}
    exit_keys: set[tuple[str, str]] = set()         # trend:{agent}:{sym}:exit:{utc date}
    dup_entry_refused = dup_exit_deferred = 0

    def window(sym: str, day_ts: int) -> Optional[list[dict[str, Any]]]:
        f = forming[sym]
        if f is None or f["ts"] != day_ts:
            return None
        di = d_index[sym].get(day_ts)
        if di is None:
            if day_ts > daily[sym][-1]["ts"]:
                di = len(daily[sym])              # today's bar: not in the completed set yet
            else:
                return None
        return daily[sym][max(0, di - (WINDOW - 1)): di] + [f]

    for t in timeline:
        day_ts = day_of(t)
        for sym in UNIVERSE:
            i = h_index[sym].get(t)
            if i is None:
                continue
            hb = hourly[sym][i]
            f = forming[sym]
            if f is None or f["ts"] != day_ts:
                forming[sym] = {"ts": day_ts, "open": hb["open"], "high": hb["high"],
                                "low": hb["low"], "close": hb["close"]}
            else:
                forming[sym] = {"ts": day_ts, "open": f["open"],
                                "high": max(f["high"], hb["high"]),
                                "low": min(f["low"], hb["low"]), "close": hb["close"]}
        now_ms = t + HOUR_MS
        hours_in = (now_ms - day_ts) // HOUR_MS          # 1..24
        if (hours_in - phase) % every != 0:
            continue
        now = dt(now_ms)
        today = now.strftime("%Y-%m-%d")

        def fill(sym: str) -> Optional[tuple[float, int]]:
            i = h_index[sym].get(t)
            if i is not None and i + 1 < len(hourly[sym]):
                nxt = hourly[sym][i + 1]
                return nxt["open"], nxt["ts"]
            return None

        for sym in sorted(positions):
            pos = positions[sym]
            if pos["_entry_ts_ms"] > t or h_index[sym].get(t) is None:
                continue
            w = window(sym, day_ts)
            if w is None:
                continue
            highs, lows, closes = tm._series(w)
            atr = tm.wilder_atr(highs, lows, closes)
            if not closes or not atr or atr <= 0:
                continue
            close = closes[-1]
            tm.update_trail(pos, close, atr)
            reason = tm.check_exit(pos, close, now=now)
            if not reason:
                continue
            if (sym, today) in exit_keys:               # live: duplicate client_order_id
                dup_exit_deferred += 1                  # -> exit_failed, retried next cycle
                continue
            f = fill(sym)
            m = meta.pop(sym)
            if f is None:
                tr = close_trade(sym, pos, m["signal_ts"], close, now_ms, "end_of_data", t)
            else:
                tr = close_trade(sym, pos, m["signal_ts"], f[0], f[1], reason, t)
            tr.update(m["extra"])
            trades.append(tr)
            exit_keys.add((sym, today))
            del positions[sym]

        for sym in UNIVERSE:
            if sym in positions:
                continue
            if len(positions) >= MAX_POS:
                break
            if h_index[sym].get(t) is None:
                continue
            w = window(sym, day_ts)
            if w is None:
                continue
            sig = tm.evaluate_symbol(w, None)
            if sig is None or sig.get("blocked"):
                continue
            if (sym, sig["side"], today) in entry_keys:  # live: duplicate client_order_id
                dup_entry_refused += 1
                continue
            f = fill(sym)
            if f is None:
                continue
            positions[sym] = new_position(sig["side"], sig, f[0], f[1])
            entry_keys.add((sym, sig["side"], today))
            meta[sym] = {"signal_ts": t, "extra": {
                "signal_day": iso(day_ts), "hours_into_day": int(hours_in)}}

    for sym in sorted(positions):
        last = hourly[sym][-1]
        m = meta[sym]
        tr = close_trade(sym, positions[sym], m["signal_ts"], last["close"],
                         last["ts"] + HOUR_MS, "end_of_data", None)
        tr.update(m["extra"])
        trades.append(tr)
    trades.sort(key=lambda x: (x["_exit_ts_ms"], x["_entry_ts_ms"], x["symbol"]))
    return {"trades": trades, "dup_entry_refused": dup_entry_refused,
            "dup_exit_deferred": dup_exit_deferred}


def completed_signals(daily) -> dict[str, dict[int, Optional[str]]]:
    """Raw completed-bar signal per (symbol, daily bar), ignoring positions."""
    out: dict[str, dict[int, Optional[str]]] = {}
    for sym in UNIVERSE:
        m: dict[int, Optional[str]] = {}
        bl = daily[sym]
        for i in range(len(bl)):
            sig = tm.evaluate_symbol(bl[max(0, i + 1 - WINDOW): i + 1], None)
            m[bl[i]["ts"]] = sig["side"] if sig else None
        out[sym] = m
    return out


def classify(trades, comp, daily) -> None:
    d_index = {s: {b["ts"]: i for i, b in enumerate(daily[s])} for s in UNIVERSE}
    for t in trades:
        day_ts = day_of(t["_signal_ts_ms"])
        want = "buy" if t["side"] == "long" else "short"
        if day_ts not in comp[t["symbol"]]:
            t["class"] = "undetermined_day_not_closed"
            t["early_fill_edge_R"] = ""
            continue
        t["class"] = "confirmed_at_close" if comp[t["symbol"]][day_ts] == want else "forming_only"
        i = d_index[t["symbol"]][day_ts]
        if t["class"] == "confirmed_at_close" and i + 1 < len(daily[t["symbol"]]):
            nxt_open = daily[t["symbol"]][i + 1]["open"]
            d = 1.0 if t["side"] == "long" else -1.0
            t["early_fill_edge_R"] = (nxt_open - t["entry_price"]) * d * t["qty"] / RISK_USD
        else:
            t["early_fill_edge_R"] = ""


def compare(trades, comp_trades, label: str, start_iso: str = "") -> dict[str, Any]:
    tr = [t for t in trades if t["entry_ts"] >= start_iso]
    ct = [c for c in comp_trades if c["entry_ts"] >= start_iso]
    fo = [t for t in tr if t["class"] == "forming_only"]
    cf = [t for t in tr if t["class"] == "confirmed_at_close"]
    f_keys = {(t["symbol"], t["side"], t["signal_day"]) for t in tr}
    c_keys = {(c["symbol"], c["side"], c["signal_bar"]) for c in ct}
    edges = [t["early_fill_edge_R"] for t in cf if t["early_fill_edge_R"] != ""]
    c_net = sum(float(c["net_usd"]) for c in ct)
    return {
        "label": label, "entries_from": start_iso or "full history",
        "forming_replay": summarize(tr),
        "completed_bar_replay_same_period": {"n": len(ct), "net_R": c_net / RISK_USD},
        "net_R_difference_forming_minus_completed": (sum(t["net_usd"] for t in tr) - c_net) / RISK_USD,
        "forming_only_entries": {
            "n": len(fo), "share_of_forming_entries": len(fo) / len(tr) if tr else None,
            **{k: v for k, v in summarize(fo).items()
               if k in ("net_usd", "net_R", "wins", "losses", "win_rate", "payoff",
                        "mean_R", "median_R", "best_trade_R", "worst_trade_R")},
            "by_side": by_key(fo, lambda t: t["side"]),
            "by_exit_reason": by_key(fo, lambda t: t["exit_reason"]),
            "by_exit_year": by_key(fo, lambda t: t["exit_ts"][:4]),
        },
        "confirmed_at_close_entries": {
            "n": len(cf), "net_R": sum(t["net_usd"] for t in cf) / RISK_USD,
            "mean_hours_into_day_at_entry": (sum(t["hours_into_day"] for t in cf) / len(cf)) if cf else None,
            "mean_fill_edge_vs_next_daily_open_R": (sum(edges) / len(edges)) if edges else None,
        },
        "undetermined": sum(1 for t in tr if t["class"].startswith("undetermined")),
        "entry_set_vs_completed_replay": {
            "in_both": len(f_keys & c_keys),
            "forming_replay_only": len(f_keys - c_keys),
            "completed_replay_only": len(c_keys - f_keys),
        },
        "by_exit_reason": by_key(tr, lambda t: t["exit_reason"]),
        "by_exit_year": by_key(tr, lambda t: t["exit_ts"][:4]),
    }


def hourly_vs_daily(daily, hourly) -> dict[str, Any]:
    """Data sanity: do the 24 hourly bars aggregate to the venue's own 1D bar?"""
    out = {}
    for sym in UNIVERSE:
        agg: dict[int, dict[str, float]] = {}
        cnt: dict[int, int] = {}
        for hb in hourly[sym]:
            d = day_of(hb["ts"])
            a = agg.get(d)
            if a is None:
                agg[d] = {"open": hb["open"], "high": hb["high"], "low": hb["low"], "close": hb["close"]}
                cnt[d] = 1
            else:
                a["high"] = max(a["high"], hb["high"])
                a["low"] = min(a["low"], hb["low"])
                a["close"] = hb["close"]
                cnt[d] += 1
        days = full = exact = 0
        worst = 0.0
        for b in daily[sym]:
            a = agg.get(b["ts"])
            if a is None:
                continue
            days += 1
            if cnt[b["ts"]] == 24:
                full += 1
            rel = max(abs(a[k] - b[k]) / b[k] for k in ("open", "high", "low", "close"))
            worst = max(worst, rel)
            if rel < 1e-9:
                exact += 1
        out[sym] = {"daily_bars_with_hourly": days, "with_all_24_hours": full,
                    "ohlc_identical": exact, "worst_relative_mismatch": worst,
                    "hourly_bars": len(hourly[sym]), "first_hour": iso(hourly[sym][0]["ts"]),
                    "last_hour": iso(hourly[sym][-1]["ts"])}
    return out


LIVE_FILLS = [
    {"symbol": "XRPUSDT", "side": "short", "ts": "2026-09-15T20:30:00Z", "price": 1.2716,
     "note": "stopped 2026-09-18 @1.3423"},
    {"symbol": "BNBUSDT", "side": "long", "ts": "2026-09-21T01:43:00Z", "price": 782.10, "note": ""},
    {"symbol": "XRPUSDT", "side": "long", "ts": "2026-09-21T12:48:00Z", "price": 1.4916, "note": ""},
]


def facts(sig_or_none, w) -> dict[str, Any]:
    highs, lows, closes = tm._series(w)
    return {"close": closes[-1], "channel_low": min(lows[-21:-1]), "channel_high": max(highs[-21:-1]),
            "adx": tm.wilder_adx(highs, lows, closes), "ma200": sum(closes[-200:]) / 200,
            "atr": tm.wilder_atr(highs, lows, closes),
            "signal": (sig_or_none or {}).get("side")}


def live_fill_check(daily, hourly, comp, comp_trades) -> list[dict[str, Any]]:
    from datetime import datetime, timezone
    out = []
    for lf in LIVE_FILLS:
        sym = lf["symbol"]
        want = "buy" if lf["side"] == "long" else "short"
        ts = int(datetime.strptime(lf["ts"], "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc).timestamp() * 1000)
        day_ts = day_of(ts)
        d_idx = {b["ts"]: i for i, b in enumerate(daily[sym])}
        di = d_idx[day_ts]
        # (1) what the live code saw: forming window at the last completed hour before the fill
        hrs = [hb for hb in hourly[sym] if day_ts <= hb["ts"] and hb["ts"] + HOUR_MS <= ts]
        seen = None
        if hrs:
            fb = {"ts": day_ts, "open": hrs[0]["open"], "high": max(h["high"] for h in hrs),
                  "low": min(h["low"] for h in hrs), "close": hrs[-1]["close"]}
            w = daily[sym][max(0, di - (WINDOW - 1)): di] + [fb]
            seen = facts(tm.evaluate_symbol(w, None), w)
            seen["as_of"] = iso(hrs[-1]["ts"] + HOUR_MS)
        hour_bar = next((hb for hb in hourly[sym] if hb["ts"] <= ts < hb["ts"] + HOUR_MS), None)
        # (2) the completed daily bar that contains the fill
        wc = daily[sym][max(0, di + 1 - WINDOW): di + 1]
        comp_same = facts(tm.evaluate_symbol(wc, None), wc)
        # (3) the previous completed bar (the last one the tested rule could act on before the fill)
        wp = daily[sym][max(0, di - WINDOW): di]
        comp_prev = facts(tm.evaluate_symbol(wp, None), wp)
        # (4) nearest completed-bar raw signals of that side, +-15 bars
        near = [iso(daily[sym][j]["ts"]) for j in range(max(0, di - 15), min(len(daily[sym]), di + 16))
                if comp[sym][daily[sym][j]["ts"]] == want]
        book = [{k: c[k] for k in ("symbol", "side", "signal_bar", "entry_ts", "entry_price",
                                   "exit_ts", "exit_price", "exit_reason", "R")}
                for c in comp_trades if c["symbol"] == sym
                and abs(d_idx.get(day_of(_ms(c["entry_ts"])), -10**9) - di) <= 15]
        out.append({
            "live_fill": lf, "daily_bar_containing_fill": iso(day_ts),
            "hours_into_that_bar": round((ts - day_ts) / HOUR_MS, 2),
            "hourly_bar_at_fill": hour_bar and {k: hour_bar[k] for k in ("open", "high", "low", "close")},
            "forming_window_before_fill": seen,
            "completed_bar_containing_fill": {"bar": iso(day_ts), **comp_same,
                                              "bar_ohlc": {k: daily[sym][di][k] for k in ("open", "high", "low", "close")}},
            "previous_completed_bar": {"bar": iso(daily[sym][di - 1]["ts"]), **comp_prev},
            "completed_rule_signals_same_side_within_15_bars": near,
            "completed_bar_replay_trades_within_15_bars": book,
        })
    return out


def _ms(iso_s: str) -> int:
    from datetime import datetime, timezone
    return int(datetime.strptime(iso_s, "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=timezone.utc).timestamp() * 1000)


def main() -> None:
    daily = {s: load_bars(s, "1D") for s in UNIVERSE}
    hourly = {s: load_bars(s, "1H") for s in UNIVERSE}
    with (HERE / "trades.csv").open() as fh:
        comp_trades = list(csv.DictReader(fh))
    comp = completed_signals(daily)

    result: dict[str, Any] = {"hourly_vs_daily_sanity": hourly_vs_daily(daily, hourly)}
    runs = {"hourly": (1, 0), "every_6h_phase0_incl_close": (6, 0), "every_6h_phase3": (6, 3)}
    for name, (every, phase) in runs.items():
        r = run_forming(daily, hourly, every=every, phase=phase)
        classify(r["trades"], comp, daily)
        block = {"full": compare(r["trades"], comp_trades, name),
                 "from_2023": compare(r["trades"], comp_trades, name, "2023-01-01"),
                 "from_2024": compare(r["trades"], comp_trades, name, "2024-01-01"),
                 "dup_entry_refused": r["dup_entry_refused"],
                 "dup_exit_deferred": r["dup_exit_deferred"]}
        result[name] = block
        if name == "hourly":
            write_trades(HERE / "trades_forming_hourly.csv", r["trades"],
                         extra_cols=["signal_day", "hours_into_day", "class", "early_fill_edge_R"])
        f = block["full"]
        fo = f["forming_only_entries"]
        print(f"[{name}] forming replay n={f['forming_replay']['n']} "
              f"net={f['forming_replay']['net_R']:.2f}R payoff={f['forming_replay'].get('payoff')} | "
              f"completed n={f['completed_bar_replay_same_period']['n']} "
              f"net={f['completed_bar_replay_same_period']['net_R']:.2f}R | "
              f"forming-only n={fo['n']} ({fo['share_of_forming_entries']:.1%}) net={fo.get('net_R', 0):.2f}R | "
              f"confirmed n={f['confirmed_at_close_entries']['n']} "
              f"net={f['confirmed_at_close_entries']['net_R']:.2f}R | sets {f['entry_set_vs_completed_replay']}")
        for sub in ("from_2023", "from_2024"):
            g = block[sub]
            go = g["forming_only_entries"]
            print(f"    {sub}: forming n={g['forming_replay']['n']} net={g['forming_replay']['net_R']:.2f}R | "
                  f"completed n={g['completed_bar_replay_same_period']['n']} "
                  f"net={g['completed_bar_replay_same_period']['net_R']:.2f}R | "
                  f"forming-only n={go['n']} net={go.get('net_R', 0):.2f}R")
    result["live_fills"] = live_fill_check(daily, hourly, comp, comp_trades)
    (HERE / "forming_result.json").write_text(json.dumps(round_floats(result), indent=2) + "\n")
    print(json.dumps(round_floats(result["live_fills"], 5), indent=1))
    print(json.dumps(result["hourly_vs_daily_sanity"], indent=1))


if __name__ == "__main__":
    main()
