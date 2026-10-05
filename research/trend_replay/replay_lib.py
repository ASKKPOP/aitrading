"""Shared code for the trend-module replay.

Every trading decision is delegated to service/server/trend_module.py's own
pure functions; this file only walks the calendar, books fills and costs.
See PREREG.txt for the conventions (B1-B13, C1-C3).
"""
from __future__ import annotations

import csv
import os
import statistics
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
DATA = HERE / "data"

for _k in ("TREND_UNIVERSE", "TREND_RISK_USD", "TREND_MAX_POSITIONS"):
    os.environ.pop(_k, None)          # B1: module defaults, nothing tuned
sys.path.insert(0, str(REPO / "service" / "server"))
import trend_module as tm  # noqa: E402

FEE_BP = 4.5
SLIP_BP = 5.0
COST_RATE = (FEE_BP + SLIP_BP) / 1e4     # per side, of that side's notional
DAY_MS = 86_400_000
HOUR_MS = 3_600_000
RISK_USD = tm._risk_usd()
MAX_POS = tm._max_positions()
WINDOW = tm.HISTORY_DAYS                 # 280, what the live module fetches


def iso(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def dt(ts_ms: int) -> datetime:
    return datetime.fromtimestamp(ts_ms / 1000, timezone.utc)


def load_bars(symbol: str, bar: str) -> list[dict[str, Any]]:
    path = DATA / f"okx_swap_{symbol}_{bar}.csv"
    out = []
    with path.open() as fh:
        for r in csv.DictReader(fh):
            if r["confirm"] != "1":
                continue
            out.append({"ts": int(r["ts_ms"]), "open": float(r["open"]),
                        "high": float(r["high"]), "low": float(r["low"]),
                        "close": float(r["close"])})
    step = DAY_MS if bar == "1D" else HOUR_MS
    for a, b in zip(out, out[1:]):
        if b["ts"] <= a["ts"]:
            raise ValueError(f"{symbol} {bar}: non-increasing ts at {iso(b['ts'])}")
        if bar == "1D" and b["ts"] - a["ts"] != step:
            raise ValueError(f"{symbol} {bar}: gap at {iso(a['ts'])}")
    return out


def load_fng() -> dict[str, int]:
    with (DATA / "fng_alternative_me.csv").open() as fh:
        return {r["date_utc"]: int(r["value"]) for r in csv.DictReader(fh)}


def new_position(side_sig: str, sig: dict[str, Any], fill_px: float,
                 fill_ts_ms: int) -> dict[str, Any]:
    """Same construction as run_trend_cycle lines 550-586."""
    qty = tm.position_qty(sig["atr"], 1.0)
    if side_sig == "buy":
        side, stop = "long", fill_px - tm.STOP_ATR_MULT * sig["atr"]
    else:
        side, stop = "short", fill_px + tm.STOP_ATR_MULT * sig["atr"]
    return {"side": side, "qty": qty, "entry_price": fill_px,
            "entry_atr": sig["atr"], "initial_stop": stop, "trail": None,
            "best_close": fill_px, "entry_ts": dt(fill_ts_ms).isoformat(),
            "entry_kind": sig["entry_kind"],
            # replay bookkeeping (not read by the module's functions)
            "_entry_ts_ms": fill_ts_ms, "_sig": sig}


def close_trade(symbol: str, pos: dict[str, Any], signal_ts_ms: int,
                exit_px: float, exit_ts_ms: int, reason: str,
                exit_signal_ts_ms: Optional[int]) -> dict[str, Any]:
    direction = 1.0 if pos["side"] == "long" else -1.0
    qty = pos["qty"]
    entry_px = pos["entry_price"]
    gross = qty * (exit_px - entry_px) * direction
    cost = COST_RATE * qty * (entry_px + exit_px)
    net = gross - cost
    sig = pos["_sig"]
    return {
        "symbol": symbol, "side": pos["side"], "entry_kind": pos["entry_kind"],
        "signal_bar": iso(signal_ts_ms),
        "entry_ts": iso(pos["_entry_ts_ms"]), "entry_price": entry_px,
        "exit_signal_bar": iso(exit_signal_ts_ms) if exit_signal_ts_ms is not None else "",
        "exit_ts": iso(exit_ts_ms), "exit_price": exit_px, "exit_reason": reason,
        "qty": qty, "entry_atr": pos["entry_atr"], "initial_stop": pos["initial_stop"],
        "final_trail": pos["trail"] if pos["trail"] is not None else "",
        "signal_close": sig["close"], "adx": sig["adx"], "ma200": sig["ma200"],
        "channel_high": sig["channel_high"], "channel_low": sig["channel_low"],
        "fear_greed": sig.get("fear_greed") if sig.get("fear_greed") is not None else "",
        "gross_usd": gross, "cost_usd": cost, "net_usd": net, "R": net / RISK_USD,
        "_entry_ts_ms": pos["_entry_ts_ms"], "_exit_ts_ms": exit_ts_ms,
        "_signal_ts_ms": signal_ts_ms,
    }


def run_daily(bars: dict[str, list[dict[str, Any]]], universe: list[str],
              fill_mode: str = "next_open",
              fng: Optional[dict[str, int]] = None) -> dict[str, Any]:
    """Completed-bar replay. PREREG B5.

    fill_mode 'next_open' (primary) or 'signal_close' (S2, what live does).
    """
    index = {s: {b["ts"]: i for i, b in enumerate(bars[s])} for s in universe}
    timeline = sorted({b["ts"] for s in universe for b in bars[s]})
    positions: dict[str, dict[str, Any]] = {}
    signal_of: dict[str, int] = {}          # symbol -> signal bar ts of the open position
    trades: list[dict[str, Any]] = []
    dropped_last_bar = 0
    signals_seen = 0
    slot_blocked = 0
    first_eligible: Optional[int] = None
    mtm: list[tuple[int, float]] = []

    def window(sym: str, i: int) -> list[dict[str, Any]]:
        return bars[sym][max(0, i + 1 - WINDOW): i + 1]

    def fill(sym: str, i: int) -> Optional[tuple[float, int]]:
        """(price, ts) of the fill for a decision taken at the close of bar i."""
        b = bars[sym][i]
        if fill_mode == "signal_close":
            return b["close"], b["ts"] + DAY_MS
        if i + 1 < len(bars[sym]):
            nxt = bars[sym][i + 1]
            return nxt["open"], nxt["ts"]
        return None

    for ts in timeline:
        close_time = dt(ts + DAY_MS)
        fg = None
        if fng is not None:
            fg = fng.get(dt(ts).strftime("%Y-%m-%d"))

        # (i) open positions — trail update then exit check, sorted by symbol
        for sym in sorted(positions):
            i = index[sym].get(ts)
            if i is None:
                continue
            pos = positions[sym]
            if pos["_entry_ts_ms"] > ts:
                continue  # filled at the NEXT open; not yet live on this bar
            w = window(sym, i)
            highs, lows, closes = tm._series(w)
            atr = tm.wilder_atr(highs, lows, closes)
            if not closes or not atr or atr <= 0:
                continue
            close = closes[-1]
            tm.update_trail(pos, close, atr)
            reason = tm.check_exit(pos, close, now=close_time)
            if not reason:
                continue
            f = fill(sym, i)
            if f is None:   # exit signal on the last bar: no next open (B7)
                trades.append(close_trade(sym, pos, signal_of[sym], close,
                                          ts + DAY_MS, "end_of_data", ts))
            else:
                trades.append(close_trade(sym, pos, signal_of[sym], f[0], f[1],
                                          reason, ts))
            del positions[sym]
            del signal_of[sym]

        # (ii) new entries — module's universe order and slot cap
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
                # live `break`s here; count what the cap suppressed
                sig = tm.evaluate_symbol(w, fg)
                if sig is not None and sig.get("side"):
                    slot_blocked += 1
                continue
            sig = tm.evaluate_symbol(w, fg)
            if sig is None or sig.get("blocked"):
                continue
            signals_seen += 1
            f = fill(sym, i)
            if f is None:
                dropped_last_bar += 1
                continue
            positions[sym] = new_position(sig["side"], sig, f[0], f[1])
            signal_of[sym] = ts

        # daily mark-to-market equity at this bar's close (reported in addition
        # to the pre-registered closed-trade curve, which hides open-trade pain)
        eq = sum(t["net_usd"] for t in trades)
        for sym, pos in positions.items():
            i = index[sym].get(ts)
            if i is None or pos["_entry_ts_ms"] > ts:
                continue
            d = 1.0 if pos["side"] == "long" else -1.0
            c = bars[sym][i]["close"]
            eq += pos["qty"] * (c - pos["entry_price"]) * d \
                - COST_RATE * pos["qty"] * (pos["entry_price"] + c)
        mtm.append((ts + DAY_MS, eq))

    # B7: still open after the last completed bar -> close at that bar's close
    for sym in sorted(positions):
        last = bars[sym][-1]
        trades.append(close_trade(sym, positions[sym], signal_of[sym], last["close"],
                                  last["ts"] + DAY_MS, "end_of_data", None))

    trades.sort(key=lambda t: (t["_exit_ts_ms"], t["_entry_ts_ms"], t["symbol"]))
    return {"trades": trades, "signals_seen": signals_seen,
            "dropped_last_bar": dropped_last_bar, "slot_blocked": slot_blocked,
            "first_eligible_ts": first_eligible, "last_bar_ts": timeline[-1],
            "mtm": mtm}


def curve_drawdown(curve: list[tuple[int, float]]) -> dict[str, Any]:
    """Max drawdown of a (ts, equity) curve, in R and calendar days."""
    peak, peak_ts = 0.0, curve[0][0]
    best = {"dd": 0.0, "peak_ts": peak_ts, "trough_ts": peak_ts, "peak": 0.0, "k": 0}
    for k, (ts, eq) in enumerate(curve):
        if eq > peak:
            peak, peak_ts = eq, ts
        if peak - eq > best["dd"]:
            best = {"dd": peak - eq, "peak_ts": peak_ts, "trough_ts": ts, "peak": peak, "k": k}
    rec = next((ts for ts, eq in curve[best["k"] + 1:] if eq >= best["peak"]), None)
    longest_uw, start, uw_span = 0.0, None, (None, None)
    peak = 0.0
    for ts, eq in curve:                      # longest time spent below a prior high
        if eq >= peak:
            peak, start = eq, ts
        elif start is not None and (ts - start) / DAY_MS > longest_uw:
            longest_uw, uw_span = (ts - start) / DAY_MS, (start, ts)
    return {"max_dd_R": best["dd"] / RISK_USD, "peak_date": iso(best["peak_ts"]),
            "trough_date": iso(best["trough_ts"]),
            "peak_to_trough_days": round((best["trough_ts"] - best["peak_ts"]) / DAY_MS, 1),
            "recovered_date": iso(rec) if rec else None,
            "peak_to_recovery_days": round((rec - best["peak_ts"]) / DAY_MS, 1) if rec else None,
            "longest_underwater_days": round(longest_uw, 1),
            "longest_underwater_span": [iso(uw_span[0]), iso(uw_span[1])] if uw_span[0] else None}


# ─────────────────────────── statistics ───────────────────────────

def summarize(trades: list[dict[str, Any]], span_years: Optional[float] = None) -> dict[str, Any]:
    n = len(trades)
    if n == 0:
        return {"n": 0, "net_usd": 0.0, "net_R": 0.0}
    nets = [t["net_usd"] for t in trades]
    wins = [x for x in nets if x > 0]
    losses = [x for x in nets if x <= 0]
    avg_win = sum(wins) / len(wins) if wins else None
    avg_loss = abs(sum(losses) / len(losses)) if losses else None
    payoff = (avg_win / avg_loss) if (avg_win is not None and avg_loss) else None

    ordered = sorted(trades, key=lambda t: (t["_exit_ts_ms"], t["_entry_ts_ms"], t["symbol"]))
    eq = 0.0
    peak = 0.0
    peak_ts = ordered[0]["_entry_ts_ms"]
    best_dd = {"dd_usd": 0.0, "peak_ts": None, "trough_ts": None, "peak_eq": 0.0}
    streak = longest = 0
    streak_start = longest_span = None
    for k, t in enumerate(ordered):
        eq += t["net_usd"]
        if eq > peak:
            peak, peak_ts = eq, t["_exit_ts_ms"]
        dd = peak - eq
        if dd > best_dd["dd_usd"]:
            best_dd = {"dd_usd": dd, "peak_ts": peak_ts, "trough_ts": t["_exit_ts_ms"],
                       "peak_eq": peak, "trough_k": k}
        if t["net_usd"] <= 0:
            if streak == 0:
                streak_start = t["_exit_ts_ms"]
            streak += 1
            if streak > longest:
                longest = streak
                longest_span = (streak_start, t["_exit_ts_ms"])
        else:
            streak = 0
    recovery_ts = None
    if best_dd["trough_ts"] is not None:
        eq = 0.0
        for k, t in enumerate(ordered):
            eq += t["net_usd"]
            if k > best_dd["trough_k"] and eq >= best_dd["peak_eq"]:
                recovery_ts = t["_exit_ts_ms"]
                break
    dd_out: dict[str, Any] = {"max_dd_R": best_dd["dd_usd"] / RISK_USD,
                              "max_dd_usd": best_dd["dd_usd"]}
    if best_dd["trough_ts"] is not None:
        dd_out.update({
            "peak_date": iso(best_dd["peak_ts"]), "trough_date": iso(best_dd["trough_ts"]),
            "peak_to_trough_days": round((best_dd["trough_ts"] - best_dd["peak_ts"]) / DAY_MS, 1),
            "recovered_date": iso(recovery_ts) if recovery_ts else None,
            "peak_to_recovery_days": (round((recovery_ts - best_dd["peak_ts"]) / DAY_MS, 1)
                                      if recovery_ts else None),
        })
    best = max(trades, key=lambda t: t["net_usd"])
    out = {
        "n": n, "net_usd": sum(nets), "net_R": sum(nets) / RISK_USD,
        "gross_usd": sum(t["gross_usd"] for t in trades),
        "cost_usd": sum(t["cost_usd"] for t in trades),
        "wins": len(wins), "losses": len(losses), "win_rate": len(wins) / n,
        "avg_win_usd": avg_win, "avg_loss_usd": avg_loss, "payoff": payoff,
        "mean_R": sum(nets) / n / RISK_USD,
        "median_R": statistics.median(nets) / RISK_USD,
        "best_trade_R": best["net_usd"] / RISK_USD,
        "worst_trade_R": min(nets) / RISK_USD,
        "net_R_ex_best_trade": (sum(nets) - best["net_usd"]) / RISK_USD,
        "longest_losing_streak": longest,
        "longest_losing_streak_span": ([iso(longest_span[0]), iso(longest_span[1])]
                                       if longest_span else None),
        "drawdown": dd_out,
    }
    if span_years:
        out["trades_per_year"] = n / span_years
    return out


def by_key(trades: list[dict[str, Any]], key) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for t in trades:
        groups.setdefault(str(key(t)), []).append(t)
    return {k: {"n": len(v), "net_usd": sum(t["net_usd"] for t in v),
                "net_R": sum(t["net_usd"] for t in v) / RISK_USD,
                "wins": sum(1 for t in v if t["net_usd"] > 0)}
            for k, v in sorted(groups.items())}


TRADE_COLS = ["symbol", "side", "entry_kind", "signal_bar", "entry_ts", "entry_price",
              "exit_signal_bar", "exit_ts", "exit_price", "exit_reason", "qty",
              "entry_atr", "initial_stop", "final_trail", "signal_close", "adx", "ma200",
              "channel_high", "channel_low", "fear_greed",
              "gross_usd", "cost_usd", "net_usd", "R"]


def write_trades(path: Path, trades: list[dict[str, Any]], extra_cols: list[str] = ()) -> None:
    cols = TRADE_COLS + list(extra_cols)
    with path.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for t in trades:
            w.writerow([repr(t[c]) if isinstance(t[c], float) else t[c] for c in cols])


def round_floats(obj: Any, nd: int = 6) -> Any:
    if isinstance(obj, float):
        return round(obj, nd)
    if isinstance(obj, dict):
        return {k: round_floats(v, nd) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [round_floats(v, nd) for v in obj]
    return obj


__all__ = ["tm", "curve_drawdown", "load_bars", "load_fng", "run_daily", "summarize", "by_key",
           "write_trades", "round_floats", "iso", "dt", "new_position", "close_trade",
           "COST_RATE", "RISK_USD", "MAX_POS", "WINDOW", "DAY_MS", "HOUR_MS", "DATA",
           "HERE", "timedelta"]
