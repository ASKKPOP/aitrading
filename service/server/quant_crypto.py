"""Crypto quantitative technicals (signal-collection plan Phase 3).

Replaces the "spot price only" technical path for crypto in the 4-analyst
pipeline with self-computed indicators — no TA library needed:

  RSI(14)          Wilder smoothing on OKX daily closes (matches chart-site defaults)
  MA(5/20/60)      simple moving averages on daily closes
  σ / volume       24h hourly-return σ and last-hour volume ratio (1H candles)
  funding rate     OKX /public/funding-rate (perp sentiment)
  basis            (swap last − spot last) / spot last — the framework's gap input

The output shape mirrors market_intel._build_stock_analysis (signal /
signal_score / trend_status / bullish_factors / risk_factors / current_price)
so the existing fallback brief and rule-based trader decision use it unchanged —
this is what makes the buy/sell triggers quantitative for crypto too.

Signal scoring (deterministic, each factor also lands in bullish/risk lists):
  price > MA20 ±1 · MA5 > MA20 ±1 · MA20 > MA60 ±1
  RSI ≥ 70 −2 (overbought, framework sell trigger) · RSI ≤ 30 +2 (contrarian)
  funding > +0.05% −1 (crowded longs) · < −0.05% +1
  basis ≥ +1.2% +1 (framework buy-gap threshold) · ≤ −0.5% −1
  score ≥ +2 → buy · ≤ −2 → sell · else hold

Gated behind QUANT_CRYPTO_ENABLED (default off): when off, the analyst keeps
the old light path. All fetches fail soft at the caller (_gather_technical).
"""

from __future__ import annotations

import math
import os
from datetime import datetime, timezone
from typing import Any, Optional

RSI_PERIOD = 14
DAILY_CANDLES = 120
HOURLY_CANDLES = 100
FUNDING_CROWDED = 0.0005    # ±0.05% per 8h
LS_CROWDED_LONG = 2.0       # long/short account ratio ≥ 2 = crowded long
LS_CROWDED_SHORT = 0.5      # ≤ 0.5 = crowded short (contrarian)
BASIS_BUY_GAP_PCT = 1.2     # framework buy trigger: basis ≥ 1.2%
BASIS_STRESS_PCT = -0.5


def quant_crypto_enabled() -> bool:
    return os.getenv("QUANT_CRYPTO_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}


def _okx_symbol(symbol: str) -> str:
    """Automation configs use 'BTC'; OKX helpers want 'BTCUSDT'."""
    s = (symbol or "").strip().upper()
    return s if s.endswith("USDT") else f"{s}USDT"


# ─────────────────────────── indicator math ───────────────────────────

def compute_rsi(closes: list[float], period: int = RSI_PERIOD) -> Optional[float]:
    """RSI with Wilder smoothing: seed with the simple average of the first
    `period` changes, then avg = (avg·(period−1) + change) / period."""
    if len(closes) < period + 1:
        return None
    changes = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [max(c, 0.0) for c in changes]
    losses = [max(-c, 0.0) for c in changes]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(changes)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - 100.0 / (1.0 + rs)


def compute_ma(closes: list[float], window: int) -> Optional[float]:
    if len(closes) < window:
        return None
    return sum(closes[-window:]) / window


def compute_sigma_and_volume(hourly: list[dict[str, Any]]) -> tuple[Optional[float], Optional[float]]:
    """24h hourly-return σ (%) and last-hour volume ratio vs the 24h average."""
    closes = [c["close"] for c in hourly]
    volumes = [c["volume"] for c in hourly]
    if len(closes) < 26:
        return None, None
    returns = [(closes[i] - closes[i - 1]) / closes[i - 1]
               for i in range(1, len(closes)) if closes[i - 1] > 0]
    window = returns[-24:]
    mean = sum(window) / len(window)
    sigma = math.sqrt(sum((r - mean) ** 2 for r in window) / len(window))
    vol_24h = volumes[-25:-1]
    avg_volume = sum(vol_24h) / len(vol_24h) if vol_24h else 0.0
    volume_ratio = volumes[-1] / avg_volume if avg_volume > 0 else None
    return sigma * 100, volume_ratio


def compute_basis_pct(swap_last: float, spot_last: float) -> Optional[float]:
    if spot_last <= 0:
        return None
    return (swap_last - spot_last) / spot_last * 100


# ─────────────────────────── analysis builder ───────────────────────────

def build_crypto_analysis(symbol: str) -> dict[str, Any]:
    """Full quantitative technical read for one crypto symbol, from OKX."""
    from crypto_feed import fetch_candles, fetch_funding_rate, fetch_spot_ticker, fetch_ticker

    okx = _okx_symbol(symbol)
    daily = fetch_candles(okx, bar="1D", limit=DAILY_CANDLES)
    closes = [c["close"] for c in daily]
    current_price = closes[-1] if closes else None

    rsi = compute_rsi(closes)
    ma5 = compute_ma(closes, 5)
    ma20 = compute_ma(closes, 20)
    ma60 = compute_ma(closes, 60)

    sigma_pct = volume_ratio = None
    try:
        hourly = fetch_candles(okx, bar="1H", limit=HOURLY_CANDLES)
        sigma_pct, volume_ratio = compute_sigma_and_volume(hourly)
    except Exception:  # noqa: BLE001
        pass

    funding_rate = None
    try:
        funding_rate = fetch_funding_rate(okx)["funding_rate"]
    except Exception:  # noqa: BLE001
        pass

    basis_pct = None
    try:
        swap_last = float(fetch_ticker(okx)["last_price"])
        spot_last = fetch_spot_ticker(okx)["last_price"]
        basis_pct = compute_basis_pct(swap_last, spot_last)
    except Exception:  # noqa: BLE001
        pass

    # Card 12 — positioning: open interest + long/short account ratio (OKX).
    open_interest_ccy = open_interest_usd = long_short_ratio = None
    try:
        from crypto_feed import fetch_open_interest
        oi = fetch_open_interest(okx)
        open_interest_ccy = oi["open_interest_ccy"]
        if current_price is not None and open_interest_ccy:
            open_interest_usd = open_interest_ccy * current_price
    except Exception:  # noqa: BLE001
        pass
    try:
        from crypto_feed import fetch_long_short_ratio
        long_short_ratio = fetch_long_short_ratio(okx)["long_short_ratio"]
    except Exception:  # noqa: BLE001
        pass

    score = 0
    bullish: list[str] = []
    risks: list[str] = []

    def _fmt(v, digits=2):
        return f"{v:.{digits}f}" if isinstance(v, (int, float)) else "n/a"

    if current_price is not None and ma20 is not None:
        if current_price > ma20:
            score += 1
            bullish.append(f"price {_fmt(current_price)} above MA20 {_fmt(ma20)}")
        else:
            score -= 1
            risks.append(f"price {_fmt(current_price)} below MA20 {_fmt(ma20)}")
    if ma5 is not None and ma20 is not None:
        if ma5 > ma20:
            score += 1
            bullish.append(f"MA5 {_fmt(ma5)} above MA20 {_fmt(ma20)}")
        else:
            score -= 1
            risks.append(f"MA5 {_fmt(ma5)} below MA20 {_fmt(ma20)}")
    if ma20 is not None and ma60 is not None:
        if ma20 > ma60:
            score += 1
            bullish.append(f"MA20 {_fmt(ma20)} above MA60 {_fmt(ma60)} (medium-term uptrend)")
        else:
            score -= 1
            risks.append(f"MA20 {_fmt(ma20)} below MA60 {_fmt(ma60)} (medium-term downtrend)")
    if rsi is not None:
        if rsi >= 70:
            score -= 2
            risks.append(f"RSI(14) {_fmt(rsi, 1)} overbought (≥70 sell trigger)")
        elif rsi <= 30:
            score += 2
            bullish.append(f"RSI(14) {_fmt(rsi, 1)} oversold (≤30, contrarian)")
    if funding_rate is not None:
        if funding_rate > FUNDING_CROWDED:
            score -= 1
            risks.append(f"funding {funding_rate * 100:.4f}% crowded long")
        elif funding_rate < -FUNDING_CROWDED:
            score += 1
            bullish.append(f"funding {funding_rate * 100:.4f}% crowded short (contrarian)")
    if basis_pct is not None:
        if basis_pct >= BASIS_BUY_GAP_PCT:
            score += 1
            bullish.append(f"spot-perp basis {_fmt(basis_pct)}% ≥ {BASIS_BUY_GAP_PCT}% buy gap")
        elif basis_pct <= BASIS_STRESS_PCT:
            score -= 1
            risks.append(f"spot-perp basis {_fmt(basis_pct)}% in backwardation")
    if long_short_ratio is not None:
        if long_short_ratio >= LS_CROWDED_LONG:
            score -= 1
            risks.append(f"long/short ratio {_fmt(long_short_ratio)} crowded long "
                         f"(≥{LS_CROWDED_LONG}, squeeze risk)")
        elif long_short_ratio <= LS_CROWDED_SHORT:
            score += 1
            bullish.append(f"long/short ratio {_fmt(long_short_ratio)} crowded short "
                           f"(≤{LS_CROWDED_SHORT}, contrarian)")

    signal = "buy" if score >= 2 else ("sell" if score <= -2 else "hold")
    if ma5 is not None and ma20 is not None and ma60 is not None:
        trend_status = ("uptrend" if ma5 > ma20 > ma60
                        else "downtrend" if ma5 < ma20 < ma60 else "mixed")
    else:
        trend_status = "unknown"

    return {
        "symbol": (symbol or "").strip().upper(),
        "market": "crypto",
        "current_price": current_price,
        "rsi_14": round(rsi, 2) if rsi is not None else None,
        "moving_averages": {
            "ma5": round(ma5, 4) if ma5 is not None else None,
            "ma20": round(ma20, 4) if ma20 is not None else None,
            "ma60": round(ma60, 4) if ma60 is not None else None,
        },
        "sigma_24h_pct": round(sigma_pct, 3) if sigma_pct is not None else None,
        "volume_ratio": round(volume_ratio, 2) if volume_ratio is not None else None,
        "funding_rate": funding_rate,
        "basis_pct": round(basis_pct, 4) if basis_pct is not None else None,
        "open_interest_ccy": round(open_interest_ccy, 2) if open_interest_ccy is not None else None,
        "open_interest_usd": round(open_interest_usd, 0) if open_interest_usd is not None else None,
        "long_short_ratio": round(long_short_ratio, 3) if long_short_ratio is not None else None,
        "signal": signal,
        "signal_score": score,
        "trend_status": trend_status,
        "bullish_factors": bullish,
        "risk_factors": risks,
        "source": "okx",
        "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
