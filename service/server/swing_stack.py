"""Swing Signal Stack — pure scoring/decision engine.

Implements research/SWING_SIGNAL_STACK.md:

- five processor scores, each -100 (max bearish) .. +100 (max bullish):
  sentiment (w=0.25), macro (0.20), thesis (0.20), smart_money (0.15),
  technical (0.20)
- composite = weighted sum; a feed with no data is ``None`` and its weight is
  renormalized away (0 means "genuinely neutral reading", None means "no
  coverage"); all-None -> no composite -> WAIT
- two-axis agreement matrix (quant = technical; qual = sentiment+thesis):
  act only when the axes agree, otherwise WAIT
- decision thresholds: composite >= +40 BUY, <= -40 SELL, else WAIT
- risk gate: no fresh entry < 24h before a binary macro event; position sized
  to a fixed max loss (default 1% of equity)
- playbook exits: hard stop, 2R target, time stop at D+5 (stocks: 5 trading
  bars; crypto: 120 clock hours = 5 daily bars), euphoria exit, shock exit

This module is deliberately pure (no I/O, no env flags): callers feed it
candles/score inputs. The doc's weights/thresholds are starting points to
calibrate by backtesting — see research/swing_stack_sim_20260830.py.
"""
from __future__ import annotations

from typing import Any, Optional

WEIGHTS: dict[str, float] = {
    "sentiment": 0.25,
    "macro": 0.20,
    "thesis": 0.20,
    "smart_money": 0.15,
    "technical": 0.20,
}
QUAL_FEEDS = ("sentiment", "thesis")  # qualitative axis members
BUY_THRESHOLD = 40.0
SELL_THRESHOLD = -40.0
AXIS_DEAD_ZONE = 10.0  # |score| <= this -> the axis is flat, not bull/bear
EVENT_BLACKOUT_HOURS = 24.0
DEFAULT_RISK_FRACTION = 0.01
TARGET_R_MULTIPLE = 2.0
TIME_STOP_BARS = 5  # D+5 for stocks; crypto trades daily bars too (120h)


def clamp(value: float, lo: float = -100.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


# ---------------------------------------------------------------------------
# Processor scores
# ---------------------------------------------------------------------------

def rsi(closes: list[float], period: int = 14) -> Optional[float]:
    """Wilder RSI over the last `period` deltas; None when not enough data."""
    if len(closes) < period + 1:
        return None
    gains = 0.0
    losses = 0.0
    for prev, cur in zip(closes[-period - 1:-1], closes[-period:]):
        delta = cur - prev
        if delta >= 0:
            gains += delta
        else:
            losses -= delta
    if losses == 0:
        return 100.0
    rs = (gains / period) / (losses / period)
    return 100.0 - 100.0 / (1.0 + rs)


def technical_score(
    candles: list[dict[str, Any]],
    benchmark_candles: Optional[list[dict[str, Any]]] = None,
) -> Optional[float]:
    """Quant axis: RSI momentum, trend structure, relative strength, volume,
    short-term level reclaim/loss. Needs >= 21 bars; else None (no coverage)."""
    if len(candles) < 21:
        return None
    closes = [float(c["close"]) for c in candles]
    vols = [float(c.get("volume") or 0.0) for c in candles]

    rsi_val = rsi(closes)
    rsi_term = clamp((rsi_val - 50.0) * 2.0) if rsi_val is not None else 0.0

    sma20 = sum(closes[-20:]) / 20.0
    prev_sma20 = sum(closes[-21:-1]) / 20.0
    if closes[-1] > sma20 and sma20 >= prev_sma20:
        trend_term = 100.0
    elif closes[-1] < sma20 and sma20 <= prev_sma20:
        trend_term = -100.0
    else:
        trend_term = 0.0

    rs_term = 0.0
    if benchmark_candles and len(benchmark_candles) >= 6:
        bench = [float(c["close"]) for c in benchmark_candles]
        if closes[-6] > 0 and bench[-6] > 0:
            own_5d = closes[-1] / closes[-6] - 1.0
            bench_5d = bench[-1] / bench[-6] - 1.0
            rs_term = clamp((own_5d - bench_5d) * 1000.0)

    vol_term = 0.0
    avg_vol = sum(vols[-21:-1]) / 20.0
    if avg_vol > 0 and vols[-1] >= 1.3 * avg_vol:
        vol_term = 100.0 if closes[-1] >= closes[-2] else -100.0

    highs = [float(c["high"]) for c in candles[-6:-1]]
    lows = [float(c["low"]) for c in candles[-6:-1]]
    if closes[-1] >= max(highs):
        reclaim_term = 100.0
    elif closes[-1] <= min(lows):
        reclaim_term = -100.0
    else:
        reclaim_term = 0.0

    score = (
        0.30 * rsi_term
        + 0.30 * trend_term
        + 0.20 * rs_term
        + 0.10 * vol_term
        + 0.10 * reclaim_term
    )
    return clamp(score)


def macro_score(
    vix: Optional[float],
    vix_5d_ago: Optional[float],
    y10: Optional[float],
    y10_5d_ago: Optional[float],
    dxy: Optional[float],
    dxy_5d_ago: Optional[float],
) -> Optional[float]:
    """The tide: VIX level+direction, 10Y yield direction, DXY direction.
    Growth assets move inversely to real yields and the dollar (doc pillar 2).
    All inputs missing -> None."""
    if vix is None and y10 is None and dxy is None:
        return None
    score = 0.0
    if vix is not None:
        if vix < 15:
            score += 40.0
        elif vix < 20:
            score += 10.0
        elif vix < 28:
            score -= 30.0
        else:
            score -= 70.0
        if vix_5d_ago:
            vix_chg = vix / vix_5d_ago - 1.0
            if vix_chg <= -0.10:
                score += 20.0
            elif vix_chg >= 0.10:
                score -= 20.0
    if y10 is not None and y10_5d_ago:
        score += clamp(-(y10 / y10_5d_ago - 1.0) * 800.0, -40.0, 40.0)
    if dxy is not None and dxy_5d_ago:
        score += clamp(-(dxy / dxy_5d_ago - 1.0) * 1500.0, -30.0, 30.0)
    return clamp(score)


def psych_sentiment_score(
    fear_greed: Optional[float],
    fear_greed_7d_avg: Optional[float],
) -> Optional[float]:
    """Sentiment/psychology proxy from a Fear & Greed index (0=extreme fear ..
    100=extreme greed), per doc pillar 1 + section 4:

    - extremes are CONTRARIAN (fear spike = BUY setup, euphoria = SELL setup)
    - mid-band is crowd TONE (the doc's pillar-1 sentiment score is a tone
      reading — its worked example scores bullish sentiment +62), and the
      rate of change matters more than the level
    - a positive turn out of fear / greed rolling over get the strongest
      adjustment.

    v1 of this mapping scored the whole mid-band 0 (extremes-only); measured
    over 2026-08 it left the qualitative axis flat 100% of days -> the
    two-axis rule could never agree. Killed by experiment 2026-08-30."""
    if fear_greed is None:
        return None
    fg = float(fear_greed)
    if fg <= 25:
        level = (25.0 - fg) * 2.4
    elif fg >= 75:
        level = -(fg - 75.0) * 2.4
    else:
        level = (fg - 50.0) * 0.8
    turn_term = 0.0
    if fear_greed_7d_avg is not None:
        turn = fg - float(fear_greed_7d_avg)
        if fg <= 40 and turn > 0:
            turn_term = 30.0  # fear + first positive turn -> contrarian entry
        elif fg >= 60 and turn < 0:
            turn_term = -30.0  # greed rolling over -> top risk
        elif 25 < fg < 75:
            turn_term = clamp(turn * 3.0, -25.0, 25.0)  # tone rate-of-change
    return clamp(level + turn_term)


# ---------------------------------------------------------------------------
# Combine + decide
# ---------------------------------------------------------------------------

# --- per-symbol sentiment blend --------------------------------------------
# The sentiment processor above reads a MARKET-level gauge, so every symbol
# scores identically on a given day. These weights fold the per-symbol
# readings (news, social) in on top of it, so the qualitative axis can differ
# between two tickers on the same date — which is what the two-axis rule needs.
#
# Starting points to calibrate, like the doc's own weights. What is NOT a
# preference and must survive recalibration:
#   * the market gauge is REQUIRED (doc §1: sentiment alone is noisy and
#     manipulable, so a crowd reading never becomes the score on its own)
#   * per-symbol components are capped at half the blend, structurally, so no
#     weight edit can let the crowd lead
#   * a thin sample is no coverage (None), never a neutral 0
SENTIMENT_W_MARKET = 0.50
SENTIMENT_W_NEWS = 0.30
SENTIMENT_W_SOCIAL = 0.20
SENTIMENT_SYMBOL_WEIGHT_MAX = 0.50
MIN_NEWS_ARTICLES = 3
MIN_SOCIAL_POSTS = 5


def blended_sentiment_score(
    market: Optional[float],
    news: Optional[float] = None,
    social: Optional[float] = None,
    news_n: int = 0,
    social_n: int = 0,
) -> Optional[float]:
    """Market gauge blended with per-symbol news/social readings.

    All inputs are on the -100..+100 processor scale. Returns None when the
    market gauge is absent — identical to today's behaviour, since
    psych_sentiment_score also returns None without a gauge."""
    if market is None:
        return None

    symbol_parts: list[tuple[float, float]] = []
    if news is not None and news_n >= MIN_NEWS_ARTICLES:
        symbol_parts.append((SENTIMENT_W_NEWS, clamp(float(news))))
    if social is not None and social_n >= MIN_SOCIAL_POSTS:
        symbol_parts.append((SENTIMENT_W_SOCIAL, clamp(float(social))))
    if not symbol_parts:
        return clamp(float(market))

    market_w = SENTIMENT_W_MARKET
    symbol_w = sum(w for w, _ in symbol_parts)
    total = market_w + symbol_w
    # Structural cap: rescale the per-symbol side if it would take more than
    # its permitted share of the blend.
    if symbol_w / total > SENTIMENT_SYMBOL_WEIGHT_MAX:
        target = market_w * SENTIMENT_SYMBOL_WEIGHT_MAX / (1.0 - SENTIMENT_SYMBOL_WEIGHT_MAX)
        scale = target / symbol_w
        symbol_parts = [(w * scale, v) for w, v in symbol_parts]
        symbol_w = target
        total = market_w + symbol_w

    acc = market_w * clamp(float(market)) + sum(w * v for w, v in symbol_parts)
    return clamp(acc / total)


def composite_score(scores: dict[str, Optional[float]]) -> Optional[float]:
    """Weighted sum, renormalized over feeds that have coverage (non-None).
    With all five present this reproduces the doc's worked example exactly."""
    total_w = 0.0
    acc = 0.0
    for name, weight in WEIGHTS.items():
        val = scores.get(name)
        if val is None:
            continue
        acc += weight * clamp(float(val))
        total_w += weight
    if total_w == 0.0:
        return None
    return acc / total_w * sum(WEIGHTS.values())


def _axis_state(score: Optional[float]) -> str:
    if score is None:
        return "flat"
    if score > AXIS_DEAD_ZONE:
        return "bull"
    if score < -AXIS_DEAD_ZONE:
        return "bear"
    return "flat"


def qual_score(scores: dict[str, Optional[float]]) -> Optional[float]:
    vals = [(WEIGHTS[k], scores.get(k)) for k in QUAL_FEEDS if scores.get(k) is not None]
    if not vals:
        return None
    return sum(w * v for w, v in vals) / sum(w for w, _ in vals)


def two_axis_state(scores: dict[str, Optional[float]]) -> str:
    """Agreement matrix: quant = technical, qual = sentiment+thesis.

    AGREE_BULL / AGREE_BEAR -> act; anything else -> WAIT (per ticker,
    per moment; conflict rows carry the doc's matrix reading)."""
    quant = _axis_state(scores.get("technical"))
    qual = _axis_state(qual_score(scores))
    if quant == "bull" and qual == "bull":
        return "AGREE_BULL"
    if quant == "bear" and qual == "bear":
        return "AGREE_BEAR"
    if quant == "bull" and qual == "bear":
        return "CONFLICT_CONTRARIAN_WATCH"  # price firm, crowd fearful
    if quant == "bear" and qual == "bull":
        return "CONFLICT_POSSIBLE_TRAP"  # crowd euphoric, price weak
    return "NEUTRAL"


def decide(
    scores: dict[str, Optional[float]],
    hours_to_binary_event: Optional[float] = None,
) -> dict[str, Any]:
    """BUY / SELL / WAIT with the risk-gate veto applied to fresh entries."""
    comp = composite_score(scores)
    axis = two_axis_state(scores)
    result: dict[str, Any] = {
        "action": "WAIT",
        "composite": comp,
        "axis": axis,
        "veto": None,
        "reason": None,
    }
    if comp is None:
        result["reason"] = "no feed coverage"
        return result
    if comp >= BUY_THRESHOLD and axis == "AGREE_BULL":
        if (
            hours_to_binary_event is not None
            and hours_to_binary_event < EVENT_BLACKOUT_HOURS
        ):
            result["veto"] = "event_blackout"
            result["reason"] = "binary macro event inside 24h"
            return result
        result["action"] = "BUY"
        return result
    if comp <= SELL_THRESHOLD and axis == "AGREE_BEAR":
        result["action"] = "SELL"
        return result
    if axis.startswith("CONFLICT"):
        result["reason"] = "axes conflict — write the resolving condition and wait"
    else:
        result["reason"] = "composite inside the WAIT band"
    return result


# ---------------------------------------------------------------------------
# Risk gate sizing + playbook exits
# ---------------------------------------------------------------------------

def position_size(
    equity: float,
    entry_price: float,
    stop_price: float,
    risk_fraction: float = DEFAULT_RISK_FRACTION,
) -> float:
    """Quantity such that a stop-out loses `risk_fraction` of equity."""
    risk_per_unit = entry_price - stop_price
    if risk_per_unit <= 0 or equity <= 0:
        return 0.0
    return (equity * risk_fraction) / risk_per_unit


def initial_stop(candles: list[dict[str, Any]], lookback: int = 5) -> Optional[float]:
    """Stop below the recent flush low (min low of the last `lookback` bars)."""
    if not candles:
        return None
    lows = [float(c["low"]) for c in candles[-lookback:]]
    return min(lows)


def target_price(entry_price: float, stop_price: float) -> float:
    return entry_price + TARGET_R_MULTIPLE * (entry_price - stop_price)


def signal_exit_reason(scores: dict[str, Optional[float]]) -> Optional[str]:
    """Score-driven exits for an OPEN long (doc trigger table):
    - shock / broken thesis: composite collapses through the SELL threshold
    - euphoria top: crowd euphoric (qual deeply negative, contrarian) while
      price is still firm -> trim into strength."""
    comp = composite_score(scores)
    if comp is not None and comp <= SELL_THRESHOLD:
        return "shock_or_broken_thesis"
    qual = qual_score(scores)
    quant = scores.get("technical")
    if (
        qual is not None
        and qual <= -40.0
        and quant is not None
        and quant >= AXIS_DEAD_ZONE
    ):
        return "euphoria_top"
    return None


def time_stop_hit(bars_held: int) -> bool:
    """No follow-through and no dated catalyst by D+5 = failed thesis -> exit.
    Both markets trade daily bars here; for crypto 5 daily bars == 120h."""
    return bars_held >= TIME_STOP_BARS
