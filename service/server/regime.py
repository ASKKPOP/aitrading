"""Market regime filter (parameter-upgrade plan Phase 2).

The research's Layer 1: psychology decides WHEN and HOW MUCH — a mode switch
and veto, never an additive signal. Crypto adaptation (no VIX exists): the
fear gauge is the crypto Fear & Greed index plus a realized-volatility
percentile (today's 20-day daily σ vs its trailing-year distribution, BTC as
the market proxy).

    regime     trigger                                          entry effect
    trend      F&G in [30,70) and vol pct < 70                  normal
    caution    F&G in [20,30) or [70,80), or vol pct in [70,90) size × 0.5
    panic      F&G < 20, or vol pct >= 90, or unresolved shock  no new buys
    euphoria   F&G >= 80                                        no new buys
    event      inside a macro release window                    no new entries
    unknown    psych/vol data unavailable or stale              treated as caution

All bands are UNVALIDATED PLACEHOLDERS pending the Phase-4 walk-forward
(strategy_config.py). Phase 2 is advisory-only: the regime is displayed and
journaled; enforcement waits for REGIME_FILTER_ENABLED at the Phase-4 flip.

Transitions are persisted (regime_snapshots) so "panic day 0" survives
restarts: day 0 = the first snapshot satisfying the trigger after a
non-panic snapshot. Exits are NEVER blocked by any regime.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

import strategy_config as scfg
from database import begin_write_transaction, get_db_connection

logger = logging.getLogger(__name__)

# ordered from most to least restrictive for display
REGIMES = ("event", "panic", "euphoria", "caution", "trend", "unknown")

# entry policy per regime: (allow_new_buys, size_multiplier)
_ENTRY_POLICY: dict[str, tuple[bool, float]] = {
    "trend": (True, 1.0),
    "caution": (True, None),  # multiplier read from config at call time
    "panic": (False, 0.0),
    "euphoria": (False, 0.0),
    "event": (False, 0.0),
    "unknown": (True, None),  # conservative: caution-sized, never blocking exits
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _utc_now().strftime("%Y-%m-%dT%H:%M:%SZ")


# ─────────────────────────── pure math ───────────────────────────

def rolling_sigma_series(closes: list[float], window: int = 20) -> list[float]:
    """Rolling `window`-day daily-return σ (%) series — one value per day once
    the window fills. Input oldest-first daily closes."""
    import math
    returns = [(closes[i] - closes[i - 1]) / closes[i - 1]
               for i in range(1, len(closes)) if closes[i - 1] > 0]
    out: list[float] = []
    for i in range(window, len(returns) + 1):
        chunk = returns[i - window:i]
        mean = sum(chunk) / window
        out.append(math.sqrt(sum((r - mean) ** 2 for r in chunk) / window) * 100)
    return out


def vol_percentile(sigma_series: list[float]) -> Optional[float]:
    """Percentile rank (0–100) of the latest σ within its trailing series."""
    if len(sigma_series) < 30:  # too few order statistics to mean anything
        return None
    latest = sigma_series[-1]
    prior = sigma_series[:-1]
    below = sum(1 for s in prior if s < latest)
    return below / len(prior) * 100


def compute_regime(
    *,
    fng_value: Optional[int],
    vol_pct: Optional[float],
    unresolved_shock: bool,
    event_window_active: Optional[bool],
) -> dict[str, Any]:
    """Pure regime classification. Half-open bands, one place (module doc)."""
    reasons: list[str] = []

    if event_window_active:
        regime = "event"
        reasons.append("macro release window active")
    elif fng_value is None and vol_pct is None and not unresolved_shock:
        regime = "unknown"
        reasons.append("psych + volatility data unavailable")
    elif (fng_value is not None and fng_value < scfg.fng_panic_max()) \
            or (vol_pct is not None and vol_pct >= scfg.vol_panic_percentile()) \
            or unresolved_shock:
        regime = "panic"
        if fng_value is not None and fng_value < scfg.fng_panic_max():
            reasons.append(f"F&G {fng_value} < {scfg.fng_panic_max()} (extreme fear)")
        if vol_pct is not None and vol_pct >= scfg.vol_panic_percentile():
            reasons.append(f"realized-vol percentile {vol_pct:.0f} ≥ {scfg.vol_panic_percentile():.0f}")
        if unresolved_shock:
            reasons.append("unresolved volatility/liquidation shock")
    elif fng_value is not None and fng_value >= scfg.fng_euphoria_min():
        regime = "euphoria"
        reasons.append(f"F&G {fng_value} ≥ {scfg.fng_euphoria_min()} (euphoria extreme)")
    elif (fng_value is not None and (fng_value < scfg.fng_fear_max()
                                     or fng_value >= scfg.fng_euphoria_ls_min())) \
            or (vol_pct is not None and vol_pct >= scfg.vol_caution_percentile()):
        regime = "caution"
        if fng_value is not None and fng_value < scfg.fng_fear_max():
            reasons.append(f"F&G {fng_value} in fear band")
        if fng_value is not None and fng_value >= scfg.fng_euphoria_ls_min():
            reasons.append(f"F&G {fng_value} in greed band")
        if vol_pct is not None and vol_pct >= scfg.vol_caution_percentile():
            reasons.append(f"realized-vol percentile {vol_pct:.0f} elevated")
    elif fng_value is None or vol_pct is None:
        regime = "unknown"
        reasons.append("partial data (F&G or volatility missing)")
    else:
        regime = "trend"
        reasons.append(f"F&G {fng_value} neutral, vol percentile {vol_pct:.0f} normal")

    allow_buys, multiplier = _ENTRY_POLICY[regime]
    if multiplier is None:
        multiplier = scfg.caution_size_multiplier()
    return {
        "regime": regime,
        "reasons": reasons,
        "allow_new_buys": allow_buys,
        "size_multiplier": multiplier,
        "fng_value": fng_value,
        "vol_percentile": round(vol_pct, 1) if vol_pct is not None else None,
        "unresolved_shock": unresolved_shock,
        "event_window_active": bool(event_window_active),
    }


# ─────────────────────────── persistence ───────────────────────────

def _record_transition(regime: str, detail: dict[str, Any]) -> None:
    """Insert a snapshot only when the regime changed — the newest row's
    created_at IS 'day 0' of the current regime (restart-safe)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT regime FROM regime_snapshots ORDER BY created_at DESC, id DESC LIMIT 1")
        row = cursor.fetchone()
        if row is not None and row["regime"] == regime:
            return
        begin_write_transaction(cursor)
        cursor.execute(
            "INSERT INTO regime_snapshots (regime, detail_json, created_at) VALUES (?, ?, ?)",
            (regime, json.dumps(detail, ensure_ascii=False), _now_iso()))
        conn.commit()
    except Exception:  # noqa: BLE001
        conn.rollback()
        logger.exception("failed to record regime transition")
    finally:
        conn.close()


def current_regime_state() -> Optional[dict[str, Any]]:
    """Latest persisted regime + when it was entered (age computable)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT regime, detail_json, created_at FROM regime_snapshots "
            "ORDER BY created_at DESC, id DESC LIMIT 1")
        row = cursor.fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    try:
        detail = json.loads(row["detail_json"] or "{}")
    except ValueError:
        detail = {}
    return {"regime": row["regime"], "entered_at": row["created_at"], "detail": detail}


def maybe_auto_trip_market_breaker() -> Optional[dict[str, Any]]:
    """Panic auto-trip (documented-but-unwired path, now wired safely):
    TWO consecutive psych snapshots with a REAL (non-estimated) liquidation
    shock trip the per-market crypto breaker for PANIC_BREAKER_MINUTES.

    Deliberately narrow: single readings and σ-proxy-only shocks never trip
    (OKX $5M/1h liquidations occur on routine moves — one reading is not a
    tail event); scope is market:crypto, never global; expiry + tripped_by
    'auto' let the resume sweep clear it without touching manual HALTs.
    No-op unless REGIME_FILTER_ENABLED. Fail-open on data errors.
    """
    if not scfg.regime_filter_enabled():
        return None
    try:
        from psych_feed import psych_feed_enabled, shock_history
        if not psych_feed_enabled():
            return None
        hist = shock_history(hours=3)
        if len(hist) < 2:
            return None

        def _has_real_shock(entry: dict[str, Any]) -> bool:
            return any(not s.get("estimated", True) for s in entry.get("shocks", []))

        if not (_has_real_shock(hist[-1]) and _has_real_shock(hist[-2])):
            return None

        from datetime import timedelta
        from risk_engine import trip_breaker
        expires = (_utc_now() + timedelta(minutes=scfg.panic_breaker_minutes())) \
            .strftime("%Y-%m-%dT%H:%M:%SZ")
        return trip_breaker(
            "auto: consecutive real liquidation shocks (panic regime)",
            scope="market:crypto", tripped_by="auto", expires_at=expires)
    except Exception:  # noqa: BLE001
        logger.exception("panic auto-trip evaluation failed (fail-open)")
        return None


# ─────────────────────────── evaluation wrapper ───────────────────────────

def evaluate_market_regime(persist: bool = True) -> dict[str, Any]:
    """Compute the current crypto-market regime from live data (BTC as the
    market proxy), fail-soft per source, optionally persisting transitions."""
    fng_value: Optional[int] = None
    unresolved_shock = False
    try:
        from psych_feed import get_psych_payload, psych_feed_enabled
        if psych_feed_enabled():
            psych = get_psych_payload()
            if psych.get("available"):
                fng = psych.get("fear_greed") or {}
                fng_value = fng.get("value")
                unresolved_shock = any(s.get("shock") for s in psych.get("shock", []))
    except Exception as exc:  # noqa: BLE001
        logger.debug("regime: psych unavailable: %s", exc)

    vol_pct: Optional[float] = None
    try:
        from crypto_feed import fetch_candles
        closes = [c["close"] for c in fetch_candles("BTCUSDT", bar="1D", limit=400)]
        vol_pct = vol_percentile(rolling_sigma_series(closes))
    except Exception as exc:  # noqa: BLE001
        logger.debug("regime: vol percentile unavailable: %s", exc)

    event_window_active: Optional[bool] = None
    try:
        from market_events import active_event_window
        event_window_active = active_event_window() is not None
    except Exception as exc:  # noqa: BLE001
        logger.debug("regime: event calendar unavailable: %s", exc)

    result = compute_regime(
        fng_value=fng_value,
        vol_pct=vol_pct,
        unresolved_shock=unresolved_shock,
        event_window_active=event_window_active,
    )
    result["as_of"] = _now_iso()
    result["enforced"] = scfg.regime_filter_enabled()
    result["note"] = ("bands are unvalidated placeholders pending Phase-4 "
                      "walk-forward; advisory-only until REGIME_FILTER_ENABLED")

    if persist:
        try:
            _record_transition(result["regime"], result)
            state = current_regime_state()
            if state:
                result["entered_at"] = state["entered_at"]
        except Exception:  # noqa: BLE001
            logger.exception("regime persistence failed")
    return result
