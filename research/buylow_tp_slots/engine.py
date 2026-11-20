"""10-slot buy-low / take-profit replay engine (see PREREG.md).

Long-only, spot-only (crypto spot + US stocks). One run = one portfolio of
N slots walking every bar of a common time grid.
"""
from __future__ import annotations

import glob
import json
import os
import random
from dataclasses import dataclass, field

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))


# ---------------------------------------------------------------- data
def load_panel(kind: str):
    """Returns (ts_ms[T], names[N], O,H,L,C [T,N] with NaN where unlisted)."""
    pat = "data/*USDT_1h.json" if kind == "crypto" else "data/stk_*_1d.json"
    files = sorted(glob.glob(os.path.join(HERE, pat)))
    series, names = {}, []
    for f in files:
        rows = json.load(open(f))
        if not rows:
            continue
        name = os.path.basename(f).split("_")[0] if kind == "crypto" else \
            os.path.basename(f)[4:].rsplit("_", 1)[0]
        names.append(name)
        series[name] = rows
    grid = sorted({r[0] for rows in series.values() for r in rows})
    if kind == "stock":   # stocks: the grid is the union of sessions
        pass
    idx = {t: i for i, t in enumerate(grid)}
    T, N = len(grid), len(names)
    O = np.full((T, N), np.nan); H = O.copy(); L = O.copy(); C = O.copy()
    for j, n in enumerate(names):
        for r in series[n]:
            i = idx[r[0]]
            O[i, j], H[i, j], L[i, j], C[i, j] = r[1], r[2], r[3], r[4]
    return np.array(grid, dtype=np.int64), names, O, H, L, C


def ffill(a):
    out = a.copy()
    for j in range(a.shape[1]):
        col = out[:, j]
        mask = np.isnan(col)
        idx = np.where(~mask, np.arange(len(col)), 0)
        np.maximum.accumulate(idx, out=idx)
        col[:] = col[idx]
        first = np.argmax(~mask) if (~mask).any() else len(col)
        col[:first] = np.nan
    return out


def rolling_max(a, w):
    out = np.full_like(a, np.nan)
    from numpy.lib.stride_tricks import sliding_window_view
    for j in range(a.shape[1]):
        col = a[:, j]
        if len(col) < w:
            continue
        v = sliding_window_view(col, w)
        with np.errstate(all="ignore"):
            m = np.nanmax(np.where(np.isnan(v), -np.inf, v), axis=1)
        m[np.isinf(m)] = np.nan
        out[w - 1:, j] = m
    return out


def rsi(c, n=14):
    out = np.full_like(c, np.nan)
    for j in range(c.shape[1]):
        col = c[:, j]
        valid = ~np.isnan(col)
        if valid.sum() < n + 2:
            continue
        s = np.where(valid)[0]
        x = col[s]
        d = np.diff(x)
        up = np.where(d > 0, d, 0.0); dn = np.where(d < 0, -d, 0.0)
        au = np.zeros_like(x); ad = np.zeros_like(x)
        au[n] = up[:n].mean(); ad[n] = dn[:n].mean()
        for k in range(n + 1, len(x)):
            au[k] = (au[k - 1] * (n - 1) + up[k - 1]) / n
            ad[k] = (ad[k - 1] * (n - 1) + dn[k - 1]) / n
        r = np.full_like(x, np.nan)
        with np.errstate(all="ignore"):
            r[n:] = 100 - 100 / (1 + au[n:] / np.where(ad[n:] == 0, 1e-12, ad[n:]))
        out[s, j] = r
    return out


def signals(kind, O, H, L, C):
    """Return {rule: score[T,N]} — score > 0 means 'low' fired; bigger = lower."""
    if kind == "crypto":
        lb_hi, dip_frac, lb_drop, drop_frac, rsi_lvl = 168, 0.15, 24, 0.08, 25
    else:
        lb_hi, dip_frac, lb_drop, drop_frac, rsi_lvl = 20, 0.10, 1, 0.04, 30
    hi = rolling_max(H, lb_hi)
    off_hi = 1 - C / hi
    prev = np.vstack([np.full((lb_drop, C.shape[1]), np.nan), C[:-lb_drop]])
    drop = 1 - C / prev
    r = rsi(C)
    with np.errstate(invalid="ignore"):
        return {
            "dip": np.where(off_hi >= dip_frac, off_hi, 0.0),
            "drop": np.where(drop >= drop_frac, drop, 0.0),
            "rsi": np.where(r < rsi_lvl, (rsi_lvl - r) / 100.0, 0.0),
        }


# ---------------------------------------------------------------- replay
@dataclass
class Cfg:
    tp: float = 0.10
    stop: float | None = None       # e.g. 0.15
    time_bars: int | None = None    # e.g. 720 (30 d of 1h)
    fee: float = 0.0010             # per leg
    slip: float = 0.0005
    slots: int = 10
    slot_usd: float = 1000.0
    rule: str = "random"            # random | dip | drop | rsi
    seed: int = 0


@dataclass
class Result:
    final_equity: float
    realized: float
    unrealized: float
    trips: list = field(default_factory=list)
    open_pos: list = field(default_factory=list)
    eq_daily: list = field(default_factory=list)
    deployed_frac: float = 0.0


def replay(panel, sig, cfg: Cfg, t0: int, t1: int, bars_per_day: int) -> Result:
    ts, names, O, H, L, C, Cf = panel
    N = len(names)
    # A series is DEAD (delisted/renamed) only if it stops > 30 days before the
    # grid ends; a file that merely lags the grid by a few bars is not (verifier
    # finding 2026-11-19: 19 stock files ended one session early).
    gap = 720 if bars_per_day == 24 else 20
    LAST = []
    for j in range(N):
        lj = int(np.where(~np.isnan(C[:, j]))[0][-1])
        LAST.append(lj if lj < len(ts) - 1 - gap else 10 ** 12)
    rng = random.Random(cfg.seed)
    score = sig.get(cfg.rule)
    cash = [cfg.slot_usd] * cfg.slots
    pos = [None] * cfg.slots      # dict(j, qty, entry_px, tp, stop, e_bar, cost)
    pending = []                  # (slot, j) to fill at next bar open
    held = set()
    trips, eq_daily = [], []
    realized = 0.0
    deployed_bars = 0
    for t in range(t0, t1):
        # 1) fill pending entries at this bar's open
        for s, j in pending:
            o = O[t, j]
            if np.isnan(o):
                held.discard(j); continue
            px = o * (1 + cfg.slip)
            spend = cash[s]
            qty = spend * (1 - cfg.fee) / px
            pos[s] = {"j": j, "qty": qty, "px": px, "cost": spend,
                      "tp": px * (1 + cfg.tp),
                      "stop": px * (1 - cfg.stop) if cfg.stop else None,
                      "e": t}
            cash[s] = 0.0
        pending = []
        # 2) exits on this bar
        for s in range(cfg.slots):
            p = pos[s]
            if p is None:
                continue
            j = p["j"]
            o, h, lo, c = O[t, j], H[t, j], L[t, j], C[t, j]
            if np.isnan(c):
                continue
            exit_px, why = None, None
            if t == LAST[j] and t < t1 - 1:   # series ends (delist/rename): exit at last close
                exit_px = c * (1 - cfg.slip); why = "delist"
            elif p["stop"] is not None and lo <= p["stop"]:        # stop first
                exit_px = min(o, p["stop"]) * (1 - cfg.slip); why = "stop"
            elif h >= p["tp"]:
                exit_px = max(o, p["tp"]) if t > p["e"] else p["tp"]; why = "tp"
            elif cfg.time_bars and t - p["e"] >= cfg.time_bars:
                exit_px = c * (1 - cfg.slip); why = "time"
            if exit_px is not None:
                proceeds = p["qty"] * exit_px * (1 - cfg.fee)
                pnl = proceeds - p["cost"]
                realized += pnl
                trips.append((names[j], int(ts[p["e"]]), int(ts[t]), why,
                              proceeds / p["cost"] - 1, t - p["e"]))
                cash[s] = proceeds
                pos[s] = None
                held.discard(j)
        deployed_bars += sum(1 for p in pos if p is not None)
        # 3) entries decided on this bar's close, filled next bar open
        if t + 1 < t1:
            free = [s for s in range(cfg.slots) if pos[s] is None and cash[s] > 1]
            if free:
                # no look-ahead: only bar-t information decides; an order on a
                # symbol with no next open simply does not fill (slot stays free)
                ok = [j for j in range(N) if j not in held
                      and not np.isnan(C[t, j]) and t < LAST[j]]
                if cfg.rule == "random":
                    rng.shuffle(ok)
                    cand = ok
                else:
                    cand = [j for j in ok if score[t, j] > 0]
                    if cfg.seed == 0:      # seed 0: deepest dip first
                        cand.sort(key=lambda j: -score[t, j])
                    else:                  # seed>0: random pick among the signalled
                        rng.shuffle(cand)
                for s, j in zip(free, cand):
                    pending.append((s, j)); held.add(j)
        if (t - t0) % bars_per_day == 0 or t == t1 - 1:
            eq = sum(cash) + sum(p["qty"] * Cf[t, p["j"]] for p in pos if p)
            eq_daily.append((int(ts[t]), eq))
    tl = t1 - 1
    open_pos = []
    unreal = 0.0
    for p in pos:
        if p:
            mv = p["qty"] * Cf[tl, p["j"]]
            unreal += mv - p["cost"]
            open_pos.append((names[p["j"]], int(ts[p["e"]]), mv / p["cost"] - 1,
                             tl - p["e"]))
    final = sum(cash) + sum(p["qty"] * Cf[tl, p["j"]] for p in pos if p)
    # pending entries never filled keep their cash
    return Result(final, realized, unreal, trips, open_pos, eq_daily,
                  deployed_bars / max(1, (t1 - t0) * cfg.slots))


def max_dd(eq_daily):
    peak, dd = -1e18, 0.0
    for _, e in eq_daily:
        peak = max(peak, e)
        dd = min(dd, e / peak - 1)
    return dd


def buy_hold(panel, t0, t1, only=None):
    ts, names, O, H, L, C, Cf = panel
    js = [j for j in range(len(names)) if not np.isnan(O[t0, j])
          and (only is None or names[j] in only)]
    if not js:
        return None
    per = 10000.0 / len(js)
    eq = sum(per / O[t0, j] * Cf[t1 - 1, j] for j in js)
    path = []
    for t in range(t0, t1, 24 if len(ts) > 30000 else 1):
        path.append((int(ts[t]), sum(per / O[t0, j] * Cf[t, j] for j in js)))
    return eq, len(js), max_dd(path)
