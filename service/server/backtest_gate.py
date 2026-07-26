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
    return max(30, int(os.getenv("BACKTEST_GATE_DAYS", "900")))


def _min_trades() -> int:
    return max(1, int(os.getenv("BACKTEST_GATE_MIN_TRADES", "5")))


def _iso_date(ts: Any) -> str:
    """Candle timestamp → YYYY-MM-DD. Feeds return epoch ms (OKX), epoch s,
    or ISO strings — simulate() keys F&G and event windows by ISO date, so a
    raw epoch here silently evaluates zero bars (observed live 2026-07-25)."""
    if ts is None:
        return ""
    text = str(ts)
    if text[:4].isdigit() and "-" in text:
        return text[:10]
    try:
        val = float(text)
    except ValueError:
        return text[:10]
    if val > 1e11:          # epoch milliseconds
        val /= 1000.0
    return datetime.fromtimestamp(val, tz=timezone.utc).strftime("%Y-%m-%d")


def _bars_from_candles(candles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """price_fetcher daily candles → simulate() bar shape (None-safe)."""
    bars = []
    for c in candles or []:
        close = c.get("close")
        if close is None:
            continue
        bars.append({
            "date": _iso_date(c.get("ts") or c.get("date")),
            "open": float(c.get("open") or close),
            "close": float(close),
            "volume": float(c.get("volume") or 0.0),
        })
    return bars


def _yahoo_ticker(symbol: str, market: str) -> str:
    """Exchange symbol → the historical_data (Yahoo-style) ticker the Phase-4
    runner uses: BTCUSDT → BTC-USD. Non-crypto passes through."""
    if market == "crypto":
        base = symbol[:-4] if symbol.upper().endswith("USDT") else symbol
        return f"{base}-USD"
    return symbol


def _load_bars(symbol: str, market: str, days: int) -> list[dict[str, Any]]:
    """Multi-year daily bars. The live exchange feed caps at 365 bars while
    the strategy's WARMUP_BARS is 400 (observed live 2026-07-25: every symbol
    scored zero evaluated days) — so prefer the runner's historical_data
    loader (years of history), falling back to the short live feed."""
    try:
        from datetime import timedelta
        from historical_data import get_bars
        end = datetime.now(timezone.utc).date()
        start = end - timedelta(days=days)
        raw = get_bars(_yahoo_ticker(symbol, market), "1d",
                       start.isoformat(), end.isoformat())
        bars = [{"date": b.date, "open": float(b.open), "close": float(b.close),
                 "volume": float(b.volume or 0)} for b in raw or []]
        if len(bars) >= 430:      # warmup 400 + a real evaluation window
            return bars
    except Exception:  # noqa: BLE001
        pass
    import price_fetcher
    return _bars_from_candles(
        price_fetcher.get_daily_candles(symbol, market, days=days))


def _event_datetimes() -> list:
    """Macro release datetimes for the event-window condition — same sources
    as the Phase-4 runner, fail-soft empty."""
    events = []
    try:
        from zoneinfo import ZoneInfo
        et = ZoneInfo("America/New_York")
        from market_events import _CALENDAR
        from market_events_history import all_historical_events
        for _etype, day, hhmm, _title in list(all_historical_events()) + list(_CALENDAR):
            events.append(datetime.fromisoformat(f"{day}T{hhmm}")
                          .replace(tzinfo=et).astimezone(timezone.utc))
    except Exception:  # noqa: BLE001
        pass
    return sorted(events)


def symbol_expectancy(symbol: str, market: str,
                      days: Optional[int] = None) -> dict[str, Any]:
    """Replay the Phase-4 strategy on the symbol's recent bars → closed-trade
    stats {n_trades, expectancy_usd, win_rate, wilson_lb}. Raises on feed
    trouble (caller treats any raise as fail-open)."""
    from backtest_strategy import DEFAULT_PARAMS, simulate, wilson_lower_bound

    days = days or _days()
    key = (market, symbol, datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    if key in _CACHE:
        return _CACHE[key]
    bars = _load_bars(symbol, market, days)
    if len(bars) < 30:
        raise ValueError(f"only {len(bars)} bars for {market}:{symbol}")
    # The Phase-4 strategy uses Fear&Greed in its confluence conditions —
    # without it entries rarely align and every symbol scores 0 trades
    # (observed live 2026-07-25). Fail-soft to {} when the feed is down.
    fng_by_date: dict[str, int] = {}
    try:
        from psych_feed import fetch_fear_greed_full_history
        fng_by_date = {r["date"]: r["value"]
                       for r in fetch_fear_greed_full_history() or []}
    except Exception:  # noqa: BLE001
        pass
    result = simulate(symbol, bars, fng_by_date, _event_datetimes(),
                      dict(DEFAULT_PARAMS))
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
