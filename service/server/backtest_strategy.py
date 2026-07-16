"""Strategy backtest (parameter-upgrade plan Phase 4) — the go/no-go gate.

Simulates the confluence engine + regime filter + Phase-3 sizing/exits over
daily bars, with the honesty constraints the verification panel forced:

SCOPE — what is historically evaluable (the backtested gate ≠ the live gate):
  B1 price>MA200        ✅ full          S1 mirror ✅
  B2 12-1 momentum      ✅ full          S2 mirror ✅
  B3 technical+volume   ⚠️ degraded — MA/RSI/volume legs only (funding/basis/
                           OI/L-S have no deep history)
  B4 crowd sentiment    ❌ null throughout (live-forward only)
  B5 fear recovering    ⚠️ F&G leg only (full 2018+ archive); shock leg null
  B6 event window       ✅ via the source-verified 2019–2025 calendar
  S4 euphoria           ⚠️ F&G leg only  S5 ❌ null  S6 ✅ simulated exits
Consequence: with B4 null, the historical "≥4/6" is stricter than live. The
runner therefore reports the deployment-faithful threshold AND a ≥3/6
sensitivity row. Only historically-evaluated conditions earn default-on.

DISCIPLINE:
  - signals on bar close t, execution at bar open t+1 (no look-ahead);
    F&G stamps day-start UTC, so day-t F&G is known at day-t close; it is
    additionally lagged one day (delta_3d uses t-1..t-4) for safety
  - fees 0.1%/leg + 0.05% slippage per leg
  - anchored walk-forward, expanding train, 14-day purge before each test
    window (max holding period); tuning grid evaluated on train only;
    configuration count reported (data-snooping accounting)
  - go/no-go is INTERVAL-based and pre-registered in run_full_backtest():
    ≥400 pooled OOS trades else "insufficient evidence"; Wilson 90% CI lower
    bound of win rate > 0.50; bootstrap 90% CI lower bound of profit factor
    > 1.0; absolute max drawdown ≤ 30%; buy-and-hold reported alongside

Pure computation on plain data structures — network access only in the
load_* helpers, so the engine is unit-testable with synthetic series.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from quant_crypto import compute_ma, compute_momentum_12_1_pct, compute_rsi

FEE_RATE = 0.001        # per leg (fees.py)
SLIPPAGE_RATE = 0.0005  # per leg, placeholder
WARMUP_BARS = 400       # 365d momentum lookback + slack
MIN_OOS_TRADES = 400    # pre-registered evidence floor

DEFAULT_PARAMS = {
    "confluence_min": 4,
    "volume_confirm_min": 1.5,
    "fng_fear_max": 30,
    "fng_panic_max": 20,
    "fng_euphoria_min": 80,
    "vol_caution_pct": 70.0,
    "vol_panic_pct": 90.0,
    "stop_loss_pct": 0.05,
    "trail_pct": 0.05,
    "time_stop_days": 14,
    "risk_budget_pct": 0.5,
}


@dataclass
class Trade:
    symbol: str
    entry_date: str
    exit_date: str
    entry_price: float
    exit_price: float
    quantity: float
    pnl: float
    exit_reason: str
    confluence: int
    regime: str


@dataclass
class SimResult:
    symbol: str
    start: str
    end: str
    initial_cash: float
    final_value: float
    trades: list[Trade] = field(default_factory=list)
    daily_values: list[tuple[str, float]] = field(default_factory=list)
    buy_hold_return_pct: float = 0.0
    exposure_pct: float = 0.0
    condition_series: dict[str, list[Optional[bool]]] = field(default_factory=dict)
    confluence_counts: list[int] = field(default_factory=list)


# ─────────────────────────── condition math (historical) ───────────────────────────

def _tech_score(closes: list[float]) -> Optional[float]:
    """Degraded quant score: the MA/RSI legs of quant_crypto's scorer only
    (funding/basis/OI/L-S have no history). Same weights and cutoffs."""
    if len(closes) < 61:
        return None
    price = closes[-1]
    ma5, ma20, ma60 = compute_ma(closes, 5), compute_ma(closes, 20), compute_ma(closes, 60)
    rsi = compute_rsi(closes)
    score = 0.0
    if ma20 is not None:
        score += 1 if price > ma20 else -1
    if ma5 is not None and ma20 is not None:
        score += 1 if ma5 > ma20 else -1
    if ma20 is not None and ma60 is not None:
        score += 1 if ma20 > ma60 else -1
    if rsi is not None:
        if rsi >= 70:
            score -= 2
        elif rsi <= 30:
            score += 2
    return score


def evaluate_bar_conditions(
    closes: list[float],
    volumes: list[float],
    fng_window: list[Optional[int]],   # F&G values for days t-4..t (5 entries), already lagged
    hours_to_next_event: Optional[float],
    params: dict[str, Any],
) -> dict[str, Optional[bool]]:
    """Historical B/S conditions for the bar whose close is closes[-1]."""
    cond: dict[str, Optional[bool]] = {}

    ma200 = compute_ma(closes, 200)
    price = closes[-1] if closes else None
    cond["B1"] = (price > ma200) if (price is not None and ma200 is not None) else None
    cond["S1"] = (price < ma200) if (price is not None and ma200 is not None) else None

    momentum = compute_momentum_12_1_pct(closes)
    cond["B2"] = (momentum > 0) if momentum is not None else None
    cond["S2"] = (momentum < 0) if momentum is not None else None

    score = _tech_score(closes)
    vol_window = volumes[-21:-1]
    avg_vol = sum(vol_window) / len(vol_window) if vol_window else 0
    volume_ratio = (volumes[-1] / avg_vol) if avg_vol > 0 else None
    if score is None or volume_ratio is None:
        cond["B3"] = cond["S3"] = None
    else:
        volume_ok = volume_ratio >= params["volume_confirm_min"]
        cond["B3"] = score >= 2 and volume_ok
        cond["S3"] = score <= -2 and volume_ok

    cond["B4"] = None  # crowd sentiment: no historical archive — live-forward only

    fng_now = fng_window[-1] if fng_window else None
    fng_3d = fng_window[-4] if len(fng_window) >= 4 else None
    if fng_now is None or fng_3d is None:
        cond["B5"] = None
        cond["S4"] = None if fng_now is None else (fng_now >= params["fng_euphoria_min"])
    else:
        cond["B5"] = fng_now < params["fng_fear_max"] and (fng_now - fng_3d) > 0
        cond["S4"] = fng_now >= params["fng_euphoria_min"]

    cond["S5"] = None  # unresolved-shock state: no liquidation archive

    cond["B6"] = (hours_to_next_event > 24) if hours_to_next_event is not None else None
    cond["S6"] = None  # positional — simulated by the exit stack below
    return cond


def _regime_for_bar(fng_now: Optional[int], vol_pct: Optional[float],
                    in_event_window: bool, params: dict[str, Any]) -> str:
    if in_event_window:
        return "event"
    if fng_now is None and vol_pct is None:
        return "unknown"
    if (fng_now is not None and fng_now < params["fng_panic_max"]) or \
            (vol_pct is not None and vol_pct >= params["vol_panic_pct"]):
        return "panic"
    if fng_now is not None and fng_now >= params["fng_euphoria_min"]:
        return "euphoria"
    if (fng_now is not None and (fng_now < params["fng_fear_max"] or fng_now >= 75)) or \
            (vol_pct is not None and vol_pct >= params["vol_caution_pct"]):
        return "caution"
    if fng_now is None or vol_pct is None:
        return "unknown"
    return "trend"


def _sigma_daily_pct(closes: list[float], window: int = 20) -> Optional[float]:
    if len(closes) < window + 1:
        return None
    returns = [(closes[i] - closes[i - 1]) / closes[i - 1]
               for i in range(len(closes) - window, len(closes)) if closes[i - 1] > 0]
    if len(returns) < window:
        return None
    mean = sum(returns) / len(returns)
    return math.sqrt(sum((r - mean) ** 2 for r in returns) / len(returns)) * 100


# ─────────────────────────── simulation ───────────────────────────

def simulate(
    symbol: str,
    bars: list[dict[str, Any]],           # [{date, open, close, volume}] oldest-first
    fng_by_date: dict[str, int],
    event_datetimes: list[datetime],       # UTC datetimes of macro releases
    params: dict[str, Any],
    *,
    initial_cash: float = 100_000.0,
    signal_start: Optional[str] = None,    # evaluate signals only from this date
    signal_end: Optional[str] = None,
) -> SimResult:
    """Event-driven daily simulation. Signals on close t, fills at open t+1."""
    dates = [b["date"] for b in bars]
    closes = [float(b["close"]) for b in bars]
    opens = [float(b["open"]) for b in bars]
    volumes = [float(b["volume"]) for b in bars]

    event_days: dict[str, list[datetime]] = {}
    for ev in event_datetimes:
        event_days.setdefault(ev.strftime("%Y-%m-%d"), []).append(ev)

    def hours_to_next_event(d: str) -> Optional[float]:
        bar_close = datetime.fromisoformat(d).replace(tzinfo=timezone.utc) + timedelta(days=1)
        best = None
        probe = datetime.fromisoformat(d).replace(tzinfo=timezone.utc)
        for k in range(0, 4):  # events within the next 3 days matter for a 24h window
            day = (probe + timedelta(days=k)).strftime("%Y-%m-%d")
            for ev in event_days.get(day, []):
                delta_h = (ev - bar_close).total_seconds() / 3600
                if delta_h >= 0 and (best is None or delta_h < best):
                    best = delta_h
        return best if best is not None else float("inf")

    def in_event_window(d: str) -> bool:
        # release day itself = window active (daily resolution)
        return d in event_days

    # rolling σ percentile needs a trailing series
    sigma_series: list[float] = []

    cash = initial_cash
    qty = 0.0
    entry_price = 0.0
    entry_date = ""
    entry_confluence = 0
    entry_regime = ""
    stop: Optional[float] = None
    tp: Optional[float] = None
    trail_armed = False
    first_open_date: Optional[str] = None
    cooldown_until: Optional[str] = None

    trades: list[Trade] = []
    daily_values: list[tuple[str, float]] = []
    condition_series: dict[str, list[Optional[bool]]] = {k: [] for k in
        ("B1", "B2", "B3", "B4", "B5", "B6", "S1", "S2", "S3", "S4", "S5", "S6")}
    confluence_counts: list[int] = []
    exposure_days = 0
    eval_days = 0

    pending_entry = False
    pending_exit_reason: Optional[str] = None

    for i in range(len(bars)):
        d = dates[i]
        window_closes = closes[: i + 1]
        window_volumes = volumes[: i + 1]

        # execute pending orders at today's open (decided on yesterday's close)
        if pending_exit_reason and qty > 0:
            fill = opens[i] * (1 - SLIPPAGE_RATE)
            proceeds = fill * qty * (1 - FEE_RATE)
            cost = entry_price * qty * (1 + FEE_RATE + SLIPPAGE_RATE)
            pnl = proceeds - cost
            trades.append(Trade(symbol, entry_date, d, entry_price, fill, qty,
                                round(pnl, 6), pending_exit_reason,
                                entry_confluence, entry_regime))
            cash += proceeds
            qty = 0.0
            stop = tp = None
            trail_armed = False
            if pending_exit_reason == "time_stop":
                cooldown_until = (date.fromisoformat(d) + timedelta(days=2)).isoformat()
            pending_exit_reason = None
        if pending_entry and qty == 0.0:
            sigma = _sigma_daily_pct(window_closes)
            if sigma and sigma > 0:
                equity = cash
                target = equity * (params["risk_budget_pct"] / 100.0) / (sigma / 100.0)
                regime_mult = 0.5 if entry_regime == "caution" else 1.0
                notional = min(target * regime_mult, cash * 0.99)
                fill = opens[i] * (1 + SLIPPAGE_RATE)
                if notional > 10 and fill > 0:
                    qty = notional / fill
                    cash -= fill * qty * (1 + FEE_RATE)
                    entry_price = fill
                    entry_date = d
                    first_open_date = d
                    stop = fill * (1 - params["stop_loss_pct"])
                    tp = fill * 1.10
                    trail_armed = False
            pending_entry = False

        # mark portfolio
        pv = cash + qty * closes[i]
        daily_values.append((d, pv))
        if qty > 0:
            exposure_days += 1

        # exit management on today's close
        if qty > 0:
            price = closes[i]
            if not trail_armed and price >= entry_price * (1 + params["trail_pct"]):
                trail_armed = True
                tp = None
            if trail_armed:
                candidate = price * (1 - params["trail_pct"])
                if stop is None or candidate > stop:
                    stop = candidate
            if stop is not None and price <= stop:
                pending_exit_reason = "trail_stop" if trail_armed else "stop_loss"
            elif tp is not None and price >= tp:
                pending_exit_reason = "take_profit"
            elif (params["time_stop_days"] > 0 and first_open_date
                  and price < entry_price
                  and (date.fromisoformat(d) - date.fromisoformat(first_open_date)).days
                      >= params["time_stop_days"]):
                pending_exit_reason = "time_stop"

        # signal evaluation on today's close (fills tomorrow)
        if i < WARMUP_BARS:
            continue
        if signal_start and d < signal_start:
            continue
        if signal_end and d > signal_end:
            continue
        eval_days += 1

        # F&G lagged one extra day for timestamp safety: use values t-1..t-5
        fng_window = [fng_by_date.get(dates[i - k]) if i - k >= 0 else None
                      for k in (5, 4, 3, 2, 1)]
        nxt = hours_to_next_event(d)
        cond = evaluate_bar_conditions(window_closes, window_volumes, fng_window,
                                       nxt, params)
        for key, val in cond.items():
            condition_series[key].append(val)

        sigma_now = _sigma_daily_pct(window_closes)
        if sigma_now is not None:
            sigma_series.append(sigma_now)
        vol_pct = None
        if len(sigma_series) > 365:
            sigma_series = sigma_series[-365:]
        if len(sigma_series) >= 30:
            prior = sigma_series[:-1]
            vol_pct = sum(1 for s in prior if s < sigma_series[-1]) / len(prior) * 100

        fng_now = fng_window[-1]
        regime = _regime_for_bar(fng_now, vol_pct, in_event_window(d), params)

        buy_count = sum(1 for k in ("B1", "B2", "B3", "B4", "B5", "B6") if cond[k] is True)
        confluence_counts.append(buy_count)
        sell_count = sum(1 for k in ("S1", "S2", "S3", "S4", "S5", "S6") if cond[k] is True)

        if qty == 0.0 and not pending_entry:
            regime_allows = regime in ("trend", "caution", "unknown")
            cooled = cooldown_until is None or d >= cooldown_until
            if (buy_count >= params["confluence_min"] and regime_allows and cooled
                    and not in_event_window(d)):
                pending_entry = True
                entry_confluence = buy_count
                entry_regime = regime
        elif qty > 0 and pending_exit_reason is None:
            # confluence sell: mirrored threshold (S6 null → max 5 historically)
            if sell_count >= params["confluence_min"]:
                pending_exit_reason = "sell_confluence"

    # liquidate any open position at the last close for accounting
    final_value = cash + qty * closes[-1] if bars else initial_cash
    if qty > 0:
        fill = closes[-1]
        proceeds = fill * qty * (1 - FEE_RATE)
        cost = entry_price * qty * (1 + FEE_RATE + SLIPPAGE_RATE)
        trades.append(Trade(symbol, entry_date, dates[-1], entry_price, fill, qty,
                            round(proceeds - cost, 6), "end_of_data",
                            entry_confluence, entry_regime))
        final_value = cash + proceeds

    first_idx = next((j for j, d in enumerate(dates)
                      if j >= WARMUP_BARS and (not signal_start or d >= signal_start)), None)
    bh_return = 0.0
    if first_idx is not None and closes[first_idx] > 0:
        last_idx = len(closes) - 1
        if signal_end:
            last_idx = max(first_idx, max((j for j, d in enumerate(dates) if d <= signal_end),
                                          default=last_idx))
        bh_return = (closes[last_idx] - closes[first_idx]) / closes[first_idx] * 100

    return SimResult(
        symbol=symbol,
        start=signal_start or (dates[WARMUP_BARS] if len(dates) > WARMUP_BARS else ""),
        end=signal_end or (dates[-1] if dates else ""),
        initial_cash=initial_cash,
        final_value=round(final_value, 2),
        trades=trades,
        daily_values=daily_values,
        buy_hold_return_pct=round(bh_return, 2),
        exposure_pct=round(exposure_days / max(1, eval_days) * 100, 1),
        condition_series=condition_series,
        confluence_counts=confluence_counts,
    )


# ─────────────────────────── statistics ───────────────────────────

def wilson_lower_bound(wins: int, n: int, z: float = 1.2816) -> Optional[float]:
    """Wilson score interval lower bound (default z = one-sided 90%)."""
    if n == 0:
        return None
    p = wins / n
    denom = 1 + z * z / n
    centre = p + z * z / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (centre - margin) / denom


def bootstrap_pf_lower_bound(pnls: list[float], iters: int = 2000,
                             q: float = 0.10, seed: int = 42) -> Optional[float]:
    """Bootstrap lower bound (q-quantile) of the profit factor."""
    if not pnls or not any(p <= 0 for p in pnls) or not any(p > 0 for p in pnls):
        return None
    rng = random.Random(seed)
    n = len(pnls)
    pfs = []
    for _ in range(iters):
        sample = [pnls[rng.randrange(n)] for _ in range(n)]
        gross_win = sum(p for p in sample if p > 0)
        gross_loss = sum(-p for p in sample if p <= 0)
        pfs.append(gross_win / gross_loss if gross_loss > 0 else float("inf"))
    pfs.sort()
    return pfs[int(q * iters)]


def summarize(results: list[SimResult]) -> dict[str, Any]:
    """Pooled metrics + calibration curve + condition agreement matrix."""
    from backtest_metrics import daily_equity_returns, max_drawdown, sharpe_ratio

    all_trades = [t for r in results for t in r.trades if t.exit_reason != "end_of_data"]
    pnls = [t.pnl for t in all_trades]
    wins = sum(1 for p in pnls if p > 0)
    n = len(pnls)

    per_asset = {}
    for r in results:
        closed = [t for t in r.trades if t.exit_reason != "end_of_data"]
        dd = max_drawdown([v for _, v in r.daily_values])
        sharpe = sharpe_ratio(daily_equity_returns(r.daily_values), periods_per_year=365)
        per_asset[r.symbol] = {
            "window": f"{r.start} → {r.end}",
            "trades": len(closed),
            "win_rate": round(sum(1 for t in closed if t.pnl > 0) / len(closed), 4) if closed else None,
            "total_return_pct": round((r.final_value - r.initial_cash) / r.initial_cash * 100, 2),
            "buy_hold_return_pct": r.buy_hold_return_pct,
            "max_drawdown_pct": round(dd, 2),
            "sharpe": sharpe,
            "exposure_pct": r.exposure_pct,
        }

    # calibration: realized hit rate per entry confluence count
    calibration = {}
    for count in sorted({t.confluence for t in all_trades}):
        bucket = [t for t in all_trades if t.confluence == count]
        bwins = sum(1 for t in bucket if t.pnl > 0)
        calibration[str(count)] = {
            "n": len(bucket),
            "hit_rate": round(bwins / len(bucket), 4),
            "wilson_lb_90": round(wilson_lower_bound(bwins, len(bucket)), 4)
                if len(bucket) >= 5 else None,
        }

    # condition agreement matrix (buy side) — pairwise fraction of days agreeing
    keys = ["B1", "B2", "B3", "B5", "B6"]  # B4 always null historically
    agreement: dict[str, dict[str, Optional[float]]] = {}
    series = {k: [v for r in results for v in r.condition_series.get(k, [])] for k in keys}
    for a in keys:
        agreement[a] = {}
        for b in keys:
            pairs = [(x, y) for x, y in zip(series[a], series[b])
                     if x is not None and y is not None]
            agreement[a][b] = round(sum(1 for x, y in pairs if x == y) / len(pairs), 3) \
                if pairs else None

    gross_win = sum(p for p in pnls if p > 0)
    gross_loss = sum(-p for p in pnls if p <= 0)
    pooled_dd = max(per_asset[s]["max_drawdown_pct"] for s in per_asset) if per_asset else None

    return {
        "pooled": {
            "trades": n,
            "wins": wins,
            "win_rate": round(wins / n, 4) if n else None,
            "wilson_lb_90": round(wilson_lower_bound(wins, n), 4) if n else None,
            "profit_factor": round(gross_win / gross_loss, 4) if gross_loss > 0 else None,
            "pf_bootstrap_lb_90": (round(bootstrap_pf_lower_bound(pnls), 4)
                                   if bootstrap_pf_lower_bound(pnls) is not None else None),
            "worst_asset_max_dd_pct": pooled_dd,
        },
        "per_asset": per_asset,
        "calibration_by_confluence": calibration,
        "condition_agreement": agreement,
        "exit_reasons": {reason: sum(1 for t in all_trades if t.exit_reason == reason)
                         for reason in sorted({t.exit_reason for t in all_trades})},
    }


def evaluate_go_no_go(pooled: dict[str, Any]) -> dict[str, Any]:
    """Pre-registered criteria (plan §4 Phase 4). Order matters: evidence floor
    first — with too few trades the verdict is 'insufficient evidence', not PASS
    (at 60–250 trades a zero-edge strategy passes a naive 52% bar ~1 in 3)."""
    n = pooled.get("trades") or 0
    checks = {
        "min_trades_400": n >= MIN_OOS_TRADES,
        "wilson_lb_gt_050": (pooled.get("wilson_lb_90") or 0) > 0.50,
        "pf_bootstrap_lb_gt_1": (pooled.get("pf_bootstrap_lb_90") or 0) > 1.0,
        "max_dd_le_30pct": (pooled.get("worst_asset_max_dd_pct") or 100) <= 30.0,
    }
    if not checks["min_trades_400"]:
        verdict = "INSUFFICIENT_EVIDENCE"
    elif all(checks.values()):
        verdict = "PASS"
    else:
        verdict = "FAIL"
    return {"verdict": verdict, "checks": checks, "oos_trades": n}
