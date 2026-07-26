"""Expectancy gate (plan #1-D, 2026-07-25): "deploy what's proven, not hoped."

At fleet composition, every candidate symbol is scored by replaying the
validated Phase-4 deterministic strategy (backtest_strategy.simulate — the
engine behind the committed Go/No-Go report, fees included) over recent daily
bars. A candidate whose closed-trade NET expectancy is non-positive is
dropped before a slot is ever bound to it; the whole decision is journaled as
a `backtest_gate` fleet event.

Honesty rules:
  - fees are inside simulate() (fees.TRADE_FEE_RATE) — the expectancy is what
    a trade would actually keep;
  - too few closed trades to judge (< BACKTEST_GATE_MIN_TRADES) is
    fail-open — kept with reason "insufficient history" — unless
    BACKTEST_GATE_STRICT flips scarcity to a drop;
  - any scoring failure (feed down, bad bars) fails OPEN: the gate must
    never be the reason a fleet cannot compose at all.

Env: BACKTEST_GATE_ENABLED (default off) · BACKTEST_GATE_DAYS (120) ·
BACKTEST_GATE_MIN_TRADES (5) · BACKTEST_GATE_STRICT (off).
Per-(symbol, market, UTC-day) verdicts are memoized in-process so an hourly
research loop re-scores each symbol at most once a day.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

_CACHE: dict[tuple[str, str, str], dict[str, Any]] = {}


def gate_enabled() -> bool:
    return os.getenv("BACKTEST_GATE_ENABLED", "false").strip().lower() in (
        "1", "true", "yes", "on")


def _strict() -> bool:
    return os.getenv("BACKTEST_GATE_STRICT", "false").strip().lower() in (
        "1", "true", "yes", "on")


def _days() -> int:
    return max(30, int(os.getenv("BACKTEST_GATE_DAYS", "120")))


def _min_trades() -> int:
    return max(1, int(os.getenv("BACKTEST_GATE_MIN_TRADES", "5")))


def _bars_from_candles(candles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """price_fetcher daily candles → simulate() bar shape (None-safe)."""
    bars = []
    for c in candles or []:
        close = c.get("close")
        if close is None:
            continue
        bars.append({
            "date": str(c.get("ts") or c.get("date") or "")[:10],
            "open": float(c.get("open") or close),
            "close": float(close),
            "volume": float(c.get("volume") or 0.0),
        })
    return bars


def symbol_expectancy(symbol: str, market: str,
                      days: Optional[int] = None) -> dict[str, Any]:
    """Replay the Phase-4 strategy on the symbol's recent bars → closed-trade
    stats {n_trades, expectancy_usd, win_rate, wilson_lb}. Raises on feed
    trouble (caller treats any raise as fail-open)."""
    import price_fetcher
    from backtest_strategy import DEFAULT_PARAMS, simulate, wilson_lower_bound

    days = days or _days()
    key = (market, symbol, datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    if key in _CACHE:
        return _CACHE[key]
    candles = price_fetcher.get_daily_candles(symbol, market, days=days)
    bars = _bars_from_candles(candles)
    if len(bars) < 30:
        raise ValueError(f"only {len(bars)} bars for {market}:{symbol}")
    result = simulate(symbol, bars, {}, [], dict(DEFAULT_PARAMS))
    closed = [t for t in result.trades if t.exit_reason != "end_of_data"]
    pnls = [t.pnl for t in closed]
    n = len(pnls)
    wins = sum(1 for p in pnls if p > 0)
    stats = {
        "n_trades": n,
        "expectancy_usd": round(sum(pnls) / n, 4) if n else 0.0,
        "win_rate": round(wins / n, 4) if n else 0.0,
        "wilson_lb": round(wilson_lower_bound(wins, n) or 0.0, 4) if n else 0.0,
    }
    _CACHE[key] = stats
    return stats


def _verdict(stats: dict[str, Any]) -> dict[str, Any]:
    """Stats → {eligible, reason}. Positive net expectancy passes; scarcity
    is fail-open unless strict."""
    n = int(stats.get("n_trades") or 0)
    if n < _min_trades():
        if _strict():
            return {"eligible": False,
                    "reason": f"insufficient history ({n} closed trades, strict)"}
        return {"eligible": True,
                "reason": f"insufficient history ({n} closed trades) — fail-open"}
    exp = float(stats.get("expectancy_usd") or 0.0)
    if exp <= 0:
        return {"eligible": False,
                "reason": (f"non-positive expectancy {exp:+.2f} USD/trade "
                           f"over {n} closed trades")}
    return {"eligible": True,
            "reason": (f"expectancy {exp:+.2f} USD/trade, "
                       f"win {stats.get('win_rate')}, "
                       f"wilson_lb {stats.get('wilson_lb')}")}


def gate_candidates(theses: list[dict[str, Any]]
                    ) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Filter candidate theses by measured edge. Returns (kept, dropped) where
    dropped maps symbol → reason. Every failure mode fails OPEN."""
    kept: list[dict[str, Any]] = []
    dropped: dict[str, str] = {}
    for thesis in theses:
        symbol = thesis.get("symbol") or ""
        market = thesis.get("market") or ""
        try:
            verdict = _verdict(symbol_expectancy(symbol, market))
        except Exception as exc:  # noqa: BLE001 — fail-open, never block composition
            logger.debug("backtest gate scoring failed for %s:%s: %s",
                         market, symbol, exc)
            kept.append(thesis)
            continue
        if verdict["eligible"]:
            thesis = dict(thesis)
            thesis["backtest_gate"] = verdict["reason"]
            kept.append(thesis)
        else:
            dropped[symbol] = verdict["reason"]
    return kept, dropped
