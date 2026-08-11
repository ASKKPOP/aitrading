"""Manipulation-shape detection — zero-LLM checklist (Research 04).

docs/research/04-market-manipulation-detection.html, Phase 1. Small-cap
crypto price-setting is routinely done by coordinated rings (pump-and-dump,
stop hunts, funding harvesting); every scheme that moves price leaves a
fingerprint in data the platform already fetches. This module names three
shapes from those fingerprints:

  manipulation:pump_ignition   vertical hourly move on anomalous volume —
                               the tape of an organized pump's ignition
                               (Kamps & Kleinberg: price anomaly AND volume
                               anomaly together, hourly-bar granularity)
  manipulation:cascade_shock   outsized move vs the symbol's own hourly σ on
                               elevated volume — forced-flow / stop-hunt
                               shape (house shock thresholds, psych_feed)
  manipulation:crowded_funding perp funding at a crowded extreme — squeeze
                               setup / funding-harvesting shape (same
                               threshold as quant_crypto)

Detection is ADVISORY and defensive: signals ride hot_issue_daemon triggers
(position holders alerted, next desk cycle escalated) and quant_crypto risk
lines. Nothing here places, blocks, or sizes a trade — the desk's judgment
skills (pump-ignition-veto, stop-hunt-discipline, manipulated-book-hygiene)
decide what the shape means.

Null-honest and fail-soft: too little history, a zero baseline, or a dead
feed yields NO signal, never a fabricated one, and no caller path may break
on an exception here.
"""

from __future__ import annotations

import logging
import os
import statistics
from typing import Any

logger = logging.getLogger(__name__)

# Bars consulted: the latest bar judged against the 24 before it.
MIN_BARS = 25

# Pump ignition: within-bar climb AND volume multiple, both anomalous.
# 4%-in-an-hour is multiples of a major's ordinary hourly range yet well
# inside a real pump's print (organized pumps average ~65% distortion);
# 6x trailing-average volume is far past organic bursts on the same bar.
PUMP_MOVE_PCT = float(os.getenv("MANIP_PUMP_MOVE_PCT", "4.0"))
PUMP_VOL_RATIO = float(os.getenv("MANIP_PUMP_VOL_RATIO", "6.0"))

# Cascade shock: the house abnormal-move definition (psych_feed.SHOCK_*):
# |close-to-close return| >= 3 sigma of the trailing day AND volume >= 2x.
CASCADE_SIGMA_MULT = float(os.getenv("MANIP_CASCADE_SIGMA", "3.0"))
CASCADE_VOL_RATIO = float(os.getenv("MANIP_CASCADE_VOL", "2.0"))

# Crowded funding: same crowded-perp threshold quant_crypto flags (0.05%
# per interval). Kept as a local default so the check works with the
# QUANT_CRYPTO gate off.
FUNDING_CROWDED = float(os.getenv("MANIP_FUNDING_CROWDED", "0.0005"))


def detection_enabled() -> bool:
    """Kill switch. Default ON: the detector only runs inside already-gated
    hosts (hot_issue_daemon, quant_crypto), so the daemon flag is the real
    gate and this exists for emergency shutoff."""
    return os.getenv("MANIP_DETECT_ENABLED", "true").strip().lower() in {
        "1", "true", "yes", "on"}


def signals_from_hourly(hourly: list[dict[str, Any]]) -> list[str]:
    """Manipulation-shape signals from OKX-style hourly candles
    (oldest-first dicts with open/close/volume).

    Pure and null-honest: < MIN_BARS bars, zero baseline volume, or a zero
    σ tape yields []. A bar that is pump-shaped is not also reported as a
    cascade — the pump label carries the stronger claim.
    """
    if not hourly or len(hourly) < MIN_BARS:
        return []
    try:
        last = hourly[-1]
        window = hourly[-MIN_BARS:-1]
        vols = [float(b.get("volume") or 0) for b in window]
        avg_vol = sum(vols) / len(vols)
        if avg_vol <= 0:
            return []
        vol_ratio = float(last.get("volume") or 0) / avg_vol
        last_open = float(last.get("open") or 0)
        last_close = float(last.get("close") or 0)
        prev_close = float(window[-1].get("close") or 0)
        if last_open <= 0 or last_close <= 0 or prev_close <= 0:
            return []
        bar_move_pct = (last_close - last_open) / last_open * 100.0
        if bar_move_pct >= PUMP_MOVE_PCT and vol_ratio >= PUMP_VOL_RATIO:
            return ["manipulation:pump_ignition"]
        closes = [float(b.get("close") or 0) for b in window]
        rets = [(b / a - 1.0) for a, b in zip(closes, closes[1:])
                if a > 0 and b > 0]
        if len(rets) < 10:
            return []
        sigma = statistics.pstdev(rets)
        if sigma <= 0:
            return []
        latest_ret = abs(last_close / prev_close - 1.0)
        if (latest_ret / sigma >= CASCADE_SIGMA_MULT
                and vol_ratio >= CASCADE_VOL_RATIO):
            return ["manipulation:cascade_shock"]
    except Exception:  # noqa: BLE001
        logger.debug("manipulation hourly classify failed", exc_info=True)
    return []


def funding_signal(funding_rate: float | None) -> list[str]:
    """['manipulation:crowded_funding'] when |rate| sits at the crowded
    extreme; None (feed unavailable) is null, not neutral-and-fine."""
    if funding_rate is None:
        return []
    try:
        if abs(float(funding_rate)) >= FUNDING_CROWDED:
            return ["manipulation:crowded_funding"]
    except (TypeError, ValueError):
        pass
    return []


def manipulation_signals(symbol: str) -> list[str]:
    """All manipulation-shape triggers for one crypto symbol (bare 'BTC' or
    pair 'BTCUSDT' form). Each feed fails soft and independently."""
    if not detection_enabled():
        return []
    s = (symbol or "").strip().upper()
    if not s:
        return []
    pair = s if s.endswith("USDT") else f"{s}USDT"
    out: list[str] = []
    try:
        from crypto_feed import fetch_candles
        out.extend(signals_from_hourly(fetch_candles(pair, bar="1H", limit=30)))
    except Exception:  # noqa: BLE001
        logger.debug("manipulation candles unavailable (%s)", pair,
                     exc_info=True)
    try:
        from crypto_feed import fetch_funding_rate
        out.extend(funding_signal(fetch_funding_rate(pair)["funding_rate"]))
    except Exception:  # noqa: BLE001
        logger.debug("manipulation funding unavailable (%s)", pair,
                     exc_info=True)
    return out
