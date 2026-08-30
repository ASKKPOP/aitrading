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
import os
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


# ──────────────── shadow mode (Plan 31 item 8) ────────────────
# The bands above are self-described UNVALIDATED PLACEHOLDERS, so a global
# REGIME_FILTER_ENABLED flip is rejected. Shadow mode is the measurement
# path: log what the entry policy WOULD do (veto / resize / allow) for two
# weeks without enforcing anything, then decide per-arm on vetoed-entry EV
# vs allowed-entry EV. Exits are never even shadow-evaluated.


def regime_shadow_enabled() -> bool:
    """REGIME_SHADOW=1 turns on log-only shadow evaluation at the automation
    gate sites. Default OFF — byte-identical to today."""
    raw = os.getenv("REGIME_SHADOW")
    if raw is None:
        return False
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def shadow_gate_check(regime_read: Optional[dict[str, Any]], *, market: str,
                      symbol: str, action: Optional[str]) -> Optional[dict[str, Any]]:
    """What the regime entry policy WOULD do to this new buy if it were
    enforced — logged, never applied.

    Returns None (and stays silent) unless REGIME_SHADOW is on, the read is
    NOT enforced (an enforced read is the real gate's job — shadow must never
    double-report it), and the order is a new buy (sells are never
    regime-gated; exit-permissiveness rule). Emits ONE structured log line
    per would-be-executed buy so the two-week census is greppable:

        regime_shadow {"market":..,"symbol":..,"regime":..,
                       "would_action":"veto|resize|allow","size_mult":..}
    """
    if action != "buy" or not regime_read:
        return None
    if regime_read.get("enforced"):
        return None
    if not regime_shadow_enabled():
        return None
    mult = float(regime_read.get("size_multiplier") or 1.0)
    if regime_read.get("allow_new_buys", True) is False:
        would_action, mult = "veto", 0.0
    elif mult != 1.0:
        would_action = "resize"
    else:
        would_action = "allow"
    payload = {"market": market, "symbol": symbol,
               "regime": regime_read.get("regime"),
               "would_action": would_action, "size_mult": mult,
               "reasons": regime_read.get("reasons") or []}
    logger.info("regime_shadow %s", json.dumps(payload, ensure_ascii=False))
    return payload


# ──────────────── crypto composite (Plan 21 P3) ────────────────
# Six-component 0–100 crypto posture score, distilled from the hermes
# work-package upstream's crypto-regime-analyzer (tradermonty/
# claude-trading-skills, MIT). Keyless: OKX candles + funding only — the
# upstream's CoinGecko dominance component is replaced by a relative-strength
# proxy (BTC 30d return vs the alt universe's median) computed from candles
# we already fetch. 100 = broad risk-on health, 0 = critical risk-off.
# Advisory-only, same stance as the regime bands: displayed, journaled, and
# rendered as research backdrop — never an enforcement input.

_COMPOSITE_TTL_SECONDS = 1800.0
_composite_cache: dict[str, Any] = {"at": 0.0, "value": None}

# OKX-listed majors used for breadth / relative strength / thrust. BTC is the
# reserve asset and scored separately.
COMPOSITE_ALTS = ("ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT", "DOGEUSDT",
                  "ADAUSDT", "LINKUSDT", "AVAXUSDT")

COMPOSITE_WEIGHTS = {
    "btc_trend": 0.25,      # reserve asset's primary trend intact?
    "alt_breadth": 0.20,    # % of alts above their 200DMA
    "dominance_proxy": 0.15,  # capital rotation: alts vs BTC 30d
    "funding": 0.15,        # perp leverage crowding (contrarian at extremes)
    "cycle": 0.15,          # drawdown from ~1y high + realized-vol percentile
    "thrust": 0.10,         # % of universe positive over 30d
}

# neutral perp funding ≈ 0.01% / 8h; ±0.075% is deeply crowded territory
_FUNDING_NEUTRAL = 0.0001
_FUNDING_EXTREME_DEV = 0.00075


def _sma(closes: list[float], n: int) -> Optional[float]:
    if len(closes) < n:
        return None
    return sum(closes[-n:]) / n


def _ret_pct(closes: list[float], days: int) -> Optional[float]:
    if len(closes) < days + 1 or closes[-days - 1] <= 0:
        return None
    return (closes[-1] - closes[-days - 1]) / closes[-days - 1] * 100.0


def score_btc_trend(closes: list[float]) -> Optional[float]:
    """Price vs 50/200DMA stack (+40 each) and 200DMA slope over 20d (+20)."""
    sma50, sma200 = _sma(closes, 50), _sma(closes, 200)
    sma200_prior = _sma(closes[:-20], 200) if len(closes) >= 220 else None
    if sma50 is None or sma200 is None:
        return None
    score = 0.0
    if closes[-1] > sma50:
        score += 40.0
    if closes[-1] > sma200:
        score += 40.0
    if sma200_prior is not None and sma200 > sma200_prior:
        score += 20.0
    return score


def score_alt_breadth(alt_closes: list[list[float]]) -> Optional[float]:
    """% of the alt universe trading above its own 200DMA."""
    above = total = 0
    for closes in alt_closes:
        sma200 = _sma(closes, 200)
        if sma200 is None:
            continue
        total += 1
        if closes[-1] > sma200:
            above += 1
    return above / total * 100.0 if total else None


def score_dominance_proxy(btc_closes: list[float],
                          alt_closes: list[list[float]]) -> Optional[float]:
    """Rotation read without CoinGecko: median alt 30d return minus BTC's.

    Alts outperforming BTC ≈ falling dominance ≈ broad risk appetite (high).
    BTC outperforming in a BTC downtrend ≈ rising-dominance flight to safety
    (extra penalty). Clamped to a ±25pp spread window.
    """
    btc30 = _ret_pct(btc_closes, 30)
    alt30s = sorted(r for r in (_ret_pct(c, 30) for c in alt_closes)
                    if r is not None)
    if btc30 is None or not alt30s:
        return None
    median_alt = alt30s[len(alt30s) // 2] if len(alt30s) % 2 else \
        (alt30s[len(alt30s) // 2 - 1] + alt30s[len(alt30s) // 2]) / 2
    spread = max(-25.0, min(25.0, median_alt - btc30))
    score = 50.0 + spread * 1.6
    if btc30 < 0 and spread < 0:
        score -= 15.0  # flight to safety: BTC falling, alts falling harder
    return max(0.0, min(100.0, score))


def score_funding(rates: list[float]) -> Optional[float]:
    """Average 8h funding vs neutral. Crowded longs (positive excess) are
    penalized at full weight, crowded shorts at 60% — a short squeeze hurts
    the crowd, not this desk's default long book."""
    if not rates:
        return None
    excess = sum(rates) / len(rates) - _FUNDING_NEUTRAL
    if excess >= 0:
        penalty = min(1.0, excess / _FUNDING_EXTREME_DEV)
    else:
        penalty = min(1.0, -excess / _FUNDING_EXTREME_DEV) * 0.6
    return (1.0 - penalty) * 100.0


def score_cycle(closes: list[float]) -> Optional[float]:
    """Drawdown position (60%) + realized-vol percentile (40%); the vol leg
    drops out (weight folds into drawdown) when the series is too short."""
    if not closes or max(closes) <= 0:
        return None
    dd = closes[-1] / max(closes) - 1.0  # ≤ 0
    dd_score = (1.0 - min(1.0, -dd / 0.8)) * 100.0
    vol_pct = vol_percentile(rolling_sigma_series(closes))
    if vol_pct is None:
        return dd_score
    return 0.6 * dd_score + 0.4 * (100.0 - vol_pct)


def score_thrust(btc_closes: list[float],
                 alt_closes: list[list[float]]) -> Optional[float]:
    """% of the universe (BTC + alts) positive over 30d."""
    rets = [r for r in (_ret_pct(c, 30) for c in [btc_closes, *alt_closes])
            if r is not None]
    if not rets:
        return None
    return sum(1 for r in rets if r > 0) / len(rets) * 100.0


def compose_crypto_composite(
        components: dict[str, Optional[float]]) -> Optional[dict[str, Any]]:
    """Weighted 0–100 score; a missing component's weight is redistributed
    proportionally across the present ones (upstream convention). None when
    every component is missing."""
    present = {k: v for k, v in components.items()
               if v is not None and k in COMPOSITE_WEIGHTS}
    if not present:
        return None
    total_w = sum(COMPOSITE_WEIGHTS[k] for k in present)
    score = sum(COMPOSITE_WEIGHTS[k] * v for k, v in present.items()) / total_w
    zone = "RISK_ON" if score >= 80 else ("NEUTRAL" if score >= 40 else "RISK_OFF")
    return {
        "score": round(score, 1),
        "zone": zone,
        "components": {k: (round(v, 1) if v is not None else None)
                       for k, v in components.items()},
        "missing": sorted(k for k in COMPOSITE_WEIGHTS if k not in present),
    }


def evaluate_crypto_composite(cached_only: bool = False) -> Optional[dict[str, Any]]:
    """TTL-cached composite (30 min). `cached_only=True` never fetches —
    consumers on a prompt path use it so a cold cache costs nothing."""
    import time as _time
    now = _time.monotonic()
    cached = _composite_cache["value"]
    if cached is not None and now - _composite_cache["at"] < _COMPOSITE_TTL_SECONDS:
        return cached
    if cached_only:
        return None
    try:
        from crypto_feed import fetch_candles, fetch_funding_rate
        btc_closes = [c["close"] for c in fetch_candles("BTCUSDT", bar="1D",
                                                        limit=400)]
        alt_closes: list[list[float]] = []
        for sym in COMPOSITE_ALTS:
            try:
                alt_closes.append([c["close"] for c in
                                   fetch_candles(sym, bar="1D", limit=260)])
            except Exception:  # noqa: BLE001 — one dead alt never kills the read
                continue
        rates: list[float] = []
        for sym in ("BTCUSDT", *COMPOSITE_ALTS):
            try:
                rates.append(float(fetch_funding_rate(sym)["funding_rate"]))
            except Exception:  # noqa: BLE001
                continue
        result = compose_crypto_composite({
            "btc_trend": score_btc_trend(btc_closes),
            "alt_breadth": score_alt_breadth(alt_closes),
            "dominance_proxy": score_dominance_proxy(btc_closes, alt_closes),
            "funding": score_funding(rates),
            "cycle": score_cycle(btc_closes),
            "thrust": score_thrust(btc_closes, alt_closes),
        })
        if result is not None:
            result["as_of"] = _now_iso()
            result["universe_alts"] = len(alt_closes)
    except Exception as exc:  # noqa: BLE001
        logger.debug("crypto composite unavailable: %s", exc)
        return cached  # stale beats absent; None when never computed
    _composite_cache["value"] = result
    _composite_cache["at"] = now
    return result


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

    # Plan 21 P3: the six-component composite rides the same payload
    # (advisory, TTL-cached — at most one fetch sweep per 30 min per
    # process). Fail-soft: a composite problem never breaks the regime read.
    try:
        composite = evaluate_crypto_composite()
        if composite is not None:
            result["crypto_composite"] = composite
    except Exception:  # noqa: BLE001
        pass

    if persist:
        try:
            _record_transition(result["regime"], result)
            state = current_regime_state()
            if state:
                result["entered_at"] = state["entered_at"]
        except Exception:  # noqa: BLE001
            logger.exception("regime persistence failed")
    return result
