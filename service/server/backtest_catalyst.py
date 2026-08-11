"""Catalyst event-study backtest — Plan 23 Gate 0.

Purpose-built harness for catalyst trades (post-earnings drift first): the
existing engines replay signal streams over one symbol's candles and cannot
answer "across N symbols, did entering after qualified catalyst reactions
carry positive after-fee expectancy?". This one does exactly that and
nothing else.

Pure replay over explicit inputs — no DB, no LLM, no network. Daily bars
only (oldest-first dicts with date/open/high/low/close/volume, ISO dates so
lexical order is chronological). Mechanics are deliberately conservative and
match the paper-trial fill rules of docs/plan/23-swing-block-news-fade.md §7:

  * reaction day     the session of the print or the one after, whichever
                     carries the larger |open-gap| (BMO/AMC timestamps on
                     free earnings feeds are unreliable; the tape is not)
  * qualification    |gap| >= gap_min AND reaction volume >= vol_mult x the
                     trailing-20 average (price AND volume anomaly together,
                     the pead-drift skill's event bar), direction = gap sign
  * entry            next session OPEN after the reaction day — never inside
                     the print, never at a cached quote
  * exit             OPEN of entry day + hold_days sessions (time exit), or
                     the stop: an intraday touch fills AT the stop, but a
                     session that OPENS through it fills at the open
                     (gap-through — overnight stops are decision levels,
                     not fills)
  * fees             fee_side (fraction, e.g. 0.00005) charged on both legs

walk_forward() picks the parameter combo on the train window ONLY and
reports the untouched test window — the gate is judged on the test panel.
block_bootstrap_lb90() resamples ISO-week blocks (earnings cluster within
weeks; iid bootstrap would overstate confidence).
"""

from __future__ import annotations

import math
import random
from typing import Any, Optional

from backtest_metrics import (avg_loss, avg_win, hit_rate, max_drawdown,
                              profit_factor)

VOL_LOOKBACK = 20
DEFAULT_GRID = tuple((h, g, v) for h in (1, 2, 3, 5)
                     for g in (2.0, 4.0, 6.0) for v in (1.5, 2.5))
DEFAULT_COMBO = (2, 4.0, 2.0)


def _idx_on_or_after(bars: list[dict[str, Any]], date: str) -> Optional[int]:
    for i, b in enumerate(bars):
        if str(b.get("date", "")) >= date:
            return i
    return None


def _gap_and_vol(bars: list[dict[str, Any]], i: int) -> Optional[tuple[float, float]]:
    if i < VOL_LOOKBACK + 1:
        return None
    prev_close = float(bars[i - 1].get("close") or 0)
    o = float(bars[i].get("open") or 0)
    if prev_close <= 0 or o <= 0:
        return None
    vols = [float(b.get("volume") or 0) for b in bars[i - VOL_LOOKBACK:i]]
    avg_vol = sum(vols) / len(vols)
    if avg_vol <= 0:
        return None
    gap_pct = (o / prev_close - 1.0) * 100.0
    vol_ratio = float(bars[i].get("volume") or 0) / avg_vol
    return gap_pct, vol_ratio


def qualify_event(bars: list[dict[str, Any]], event_date: str,
                  gap_min_pct: float, vol_mult_min: float) -> Optional[dict[str, Any]]:
    """Resolve the reaction day for a catalyst dated `event_date` and apply
    the PEAD event bar. Null-honest: thin history or a quiet tape -> None."""
    i0 = _idx_on_or_after(bars, event_date)
    if i0 is None:
        return None
    candidates = []
    for i in (i0, i0 + 1):
        if i < len(bars):
            gv = _gap_and_vol(bars, i)
            if gv is not None:
                candidates.append((abs(gv[0]), i, gv))
    if not candidates:
        return None
    _, idx, (gap_pct, vol_ratio) = max(candidates)
    if abs(gap_pct) < gap_min_pct or vol_ratio < vol_mult_min:
        return None
    return {"reaction_date": str(bars[idx]["date"]), "reaction_idx": idx,
            "direction": 1 if gap_pct > 0 else -1,
            "gap_pct": gap_pct, "vol_ratio": vol_ratio}


def _pullback_entry_idx(bars: list[dict[str, Any]], reaction_idx: int,
                        direction: int, window: int) -> Optional[int]:
    """pead-drift's stated entry, daily-bar approximation: the first
    with-trend pause (down-close on a long / up-close on a short) whose
    extreme HOLDS the reaction-day open; entry is the next session. A bar
    that breaks the gap area disqualifies the event; no pullback inside the
    window is no trade — chasing the spike is what pump-ignition-veto
    forbids, and the naive next-open replay measured exactly that chase."""
    gap_open = float(bars[reaction_idx]["open"])
    for j in range(reaction_idx + 1, min(reaction_idx + 1 + window, len(bars))):
        b = bars[j]
        if direction > 0:
            if float(b["low"]) < gap_open:
                return None                        # gap area failed
            if float(b["close"]) < float(bars[j - 1]["close"]):
                return j + 1
        else:
            if float(b["high"]) > gap_open:
                return None
            if float(b["close"]) > float(bars[j - 1]["close"]):
                return j + 1
    return None


def replay_event(bars: list[dict[str, Any]], ev: Optional[dict[str, Any]],
                 hold_days: int, fee_side: float,
                 stop_pct: Optional[float] = None,
                 entry_mode: str = "next_open",
                 pullback_window: int = 5) -> Optional[dict[str, Any]]:
    """One trade: entry per `entry_mode` ('next_open' or 'pullback'), day-H
    open time exit, optional stop with gap-through-at-open semantics. None
    when history can't hold the trade or the entry never triggers."""
    if not ev:
        return None
    d = ev["direction"]
    if entry_mode == "pullback":
        entry_idx = _pullback_entry_idx(bars, ev["reaction_idx"], d,
                                        pullback_window)
        if entry_idx is None:
            return None
    else:
        entry_idx = ev["reaction_idx"] + 1
    exit_idx = entry_idx + hold_days
    if exit_idx >= len(bars):
        return None
    entry = float(bars[entry_idx]["open"])
    if entry <= 0:
        return None
    stop_px = None
    if stop_pct is not None:
        stop_px = entry * (1 - d * stop_pct / 100.0)
    exit_px, exit_date, reason = None, None, "time"
    for j in range(entry_idx + 1, exit_idx + 1):
        b = bars[j]
        if stop_px is not None:
            o = float(b["open"])
            if (d > 0 and o <= stop_px) or (d < 0 and o >= stop_px):
                exit_px, exit_date, reason = o, str(b["date"]), "stop_gap_through"
                break
            lo, hi = float(b["low"]), float(b["high"])
            if (d > 0 and lo <= stop_px) or (d < 0 and hi >= stop_px):
                exit_px, exit_date, reason = stop_px, str(b["date"]), "stop"
                break
        if j == exit_idx:
            exit_px, exit_date = float(b["open"]), str(b["date"])
    if exit_px is None:
        return None
    gross_pct = d * (exit_px / entry - 1.0) * 100.0
    net_pct = gross_pct - 2 * fee_side * 100.0
    return {"symbol": ev.get("symbol"), "reaction_date": ev["reaction_date"],
            "entry_date": str(bars[entry_idx]["date"]), "entry": entry,
            "exit_date": exit_date, "exit_px": exit_px, "direction": d,
            "gross_ret_pct": gross_pct, "net_ret_pct": net_pct,
            "exit_reason": reason}


def block_bootstrap_lb90(dated_rets: list[tuple[str, float]],
                         iters: int = 1000, seed: int = 7) -> float:
    """10th percentile of bootstrapped mean returns, resampling ISO-week
    blocks (catalyst trades cluster within earnings weeks — iid resampling
    would understate the variance and flatter the gate)."""
    if not dated_rets:
        return 0.0
    blocks: dict[str, list[float]] = {}
    for date, r in dated_rets:
        try:
            import datetime as _dt
            iso = _dt.date.fromisoformat(date[:10]).isocalendar()
            key = f"{iso[0]}-W{iso[1]:02d}"
        except ValueError:
            key = date[:7]
        blocks.setdefault(key, []).append(float(r))
    groups = list(blocks.values())
    rng = random.Random(seed)
    means = []
    for _ in range(iters):
        sample: list[float] = []
        for _ in range(len(groups)):
            sample.extend(rng.choice(groups))
        means.append(sum(sample) / len(sample))
    means.sort()
    return means[max(0, int(0.10 * len(means)) - 1)]


def metrics_panel(trades: list[dict[str, Any]]) -> dict[str, Any]:
    """The full §7 checkpoint panel from a trade list."""
    pnls = [t["net_ret_pct"] for t in trades]
    if not pnls:
        return {"n": 0, "hit_rate": None, "expectancy_pct": None,
                "profit_factor": None, "avg_win_pct": None,
                "avg_loss_pct": None, "max_drawdown_pct": None,
                "bootstrap_lb90_pct": None, "worst_trade_pct": None}
    ordered = sorted(trades, key=lambda t: t["entry_date"])
    curve = [100.0]
    for t in ordered:
        curve.append(curve[-1] * (1 + t["net_ret_pct"] / 100.0))
    pf = profit_factor(pnls)
    return {
        "n": len(pnls),
        "hit_rate": round(hit_rate(pnls), 4),
        "expectancy_pct": round(sum(pnls) / len(pnls), 4),
        "profit_factor": (round(pf, 3) if pf is not None
                          and math.isfinite(pf) else pf),
        "avg_win_pct": avg_win(pnls),
        "avg_loss_pct": avg_loss(pnls),
        "max_drawdown_pct": round(max_drawdown(curve), 3),
        "bootstrap_lb90_pct": round(block_bootstrap_lb90(
            [(t["entry_date"], t["net_ret_pct"]) for t in ordered]), 4),
        "worst_trade_pct": round(min(pnls), 4),
    }


def _run_combo(events: list[dict[str, Any]],
               bars_by_symbol: dict[str, list[dict[str, Any]]],
               combo: tuple[int, float, float], fee_side: float,
               stop_pct: Optional[float],
               long_only: bool,
               entry_mode: str = "next_open") -> list[dict[str, Any]]:
    hold_days, gap_min, vol_min = combo
    trades = []
    for e in events:
        bars = bars_by_symbol.get(e["symbol"])
        if not bars:
            continue
        ev = qualify_event(bars, e["event_date"], gap_min, vol_min)
        if not ev or (long_only and ev["direction"] < 0):
            continue
        ev["symbol"] = e["symbol"]
        tr = replay_event(bars, ev, hold_days, fee_side, stop_pct=stop_pct,
                          entry_mode=entry_mode)
        if tr:
            trades.append(tr)
    return trades


def walk_forward(events: list[dict[str, Any]],
                 bars_by_symbol: dict[str, list[dict[str, Any]]],
                 split_date: str, fee_side: float,
                 grid: tuple = DEFAULT_GRID,
                 stop_pct: Optional[float] = None,
                 long_only: bool = False,
                 entry_mode: str = "next_open") -> dict[str, Any]:
    """Choose (hold_days, gap_min, vol_mult) on trades whose reaction date
    is <= split_date; report the untouched test window with the SAME combo.
    The gate is judged on `test` — `train` is shown for honesty, not proof."""
    best_key: Optional[tuple[float, int, int]] = None
    chosen = DEFAULT_COMBO
    for combo in grid:
        trades = _run_combo(events, bars_by_symbol, combo, fee_side,
                            stop_pct, long_only, entry_mode=entry_mode)
        train = [t for t in trades if t["reaction_date"] <= split_date]
        if not train:
            continue
        exp = sum(t["net_ret_pct"] for t in train) / len(train)
        # prefer expectancy, then sample size, then the shorter hold
        key = (exp, len(train), -combo[0])
        if best_key is None or key > best_key:
            best_key, chosen = key, combo
    trades = _run_combo(events, bars_by_symbol, chosen, fee_side,
                        stop_pct, long_only, entry_mode=entry_mode)
    train = [t for t in trades if t["reaction_date"] <= split_date]
    test = [t for t in trades if t["reaction_date"] > split_date]
    return {
        "chosen": {"hold_days": chosen[0], "gap_min_pct": chosen[1],
                   "vol_mult_min": chosen[2], "stop_pct": stop_pct,
                   "long_only": long_only, "entry_mode": entry_mode},
        "split_date": split_date,
        "train": metrics_panel(train),
        "test": metrics_panel(test),
        "test_trades": test,
    }
