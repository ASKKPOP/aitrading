"""Signal fusion (signal-collection plan Phase 5).

Fuses the three signal families built in Phases 2–3 into one score per symbol:

    fused = w_quant · quant + w_sentiment · sentiment + w_psych · psych

  quant       Phase 3 technicals (quant_crypto): signal_score clamped to [−1, 1]
  sentiment   StockTwits crowd tilt for the symbol: (bull − bear) / scored
  psych       Phase 2 feed: F&G 3-day delta, negative sentiment spikes,
              prediction-market odds moves — combined then clamped to [−1, 1]

Weights come from env (FUSION_W_QUANT / FUSION_W_SENTIMENT / FUSION_W_PSYCH,
defaults 0.5 / 0.3 / 0.2) and are normalized over the components that are
actually available. The psych weight is HARD-CAPPED at PSYCH_WEIGHT_MAX (0.3):
the framework forbids psychology-led trading, so no configuration can make
psych dominate the fused score — the cap is structural, not advisory.

The fused read also reports which framework triggers matched (plan §4):
  buy    F&G Δ3d ≥ +10 · sentiment > +0.2 · basis ≥ 1.2%
  buy    odds re-rating: Δodds ≥ +0.05 / 24h
  sell   RSI ≥ 70 · negative sentiment spike z ≤ −2
  reduce volatility shock (3σ proxy) — surfaced for the Phase 1 breaker

Read-only and pull-based (GET /api/market-intel/fusion) — no background loop,
no execution. Missing sources shrink to the remaining components and are named
in `missing`, so a consumer always knows what the score is built from.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

PSYCH_WEIGHT_MAX = 0.3   # structural cap — psychology never leads the score
BUY_THRESHOLD = 0.25
SELL_THRESHOLD = -0.25
QUANT_SCORE_SCALE = 4.0  # quant signal_score of ±4 saturates the component

# Framework trigger thresholds (plan §4 — configurable defaults)
FNG_RECOVERY_DELTA = 10
SENTIMENT_BUY_MIN = 0.2
BASIS_BUY_GAP_PCT = 1.2
ODDS_RERATING_MIN = 0.05
RSI_OVERBOUGHT = 70


def _env_weight(name: str, default: float) -> float:
    """A malformed weight env var must not 500 a public endpoint — fall back."""
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        logger.warning("invalid %s value %r — using default %s", name, os.getenv(name), default)
        return default


def _weights() -> dict[str, float]:
    w = {
        "quant": _env_weight("FUSION_W_QUANT", 0.5),
        "sentiment": _env_weight("FUSION_W_SENTIMENT", 0.3),
        "psych": _env_weight("FUSION_W_PSYCH", 0.2),
    }
    w = {k: max(0.0, v) for k, v in w.items()}
    total = sum(w.values()) or 1.0
    w = {k: v / total for k, v in w.items()}
    if w["psych"] > PSYCH_WEIGHT_MAX:  # re-normalize the excess into the others
        excess = w["psych"] - PSYCH_WEIGHT_MAX
        w["psych"] = PSYCH_WEIGHT_MAX
        rest = w["quant"] + w["sentiment"]
        if rest > 0:
            w["quant"] += excess * (w["quant"] / rest)
            w["sentiment"] += excess * (w["sentiment"] / rest)
        else:
            w["quant"] += excess
    return w


def _clamp(value: float, low: float = -1.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


# ─────────────────────────── components ───────────────────────────

def _quant_component(symbol: str) -> Optional[dict[str, Any]]:
    try:
        from quant_crypto import build_crypto_analysis, quant_crypto_enabled
        if not quant_crypto_enabled():
            return None
        analysis = build_crypto_analysis(symbol)
    except Exception as exc:  # noqa: BLE001
        logger.debug("fusion quant unavailable for %s: %s", symbol, exc)
        return None
    return {
        "value": _clamp((analysis.get("signal_score") or 0) / QUANT_SCORE_SCALE),
        "rsi_14": analysis.get("rsi_14"),
        "basis_pct": analysis.get("basis_pct"),
        "funding_rate": analysis.get("funding_rate"),
        "open_interest_usd": analysis.get("open_interest_usd"),
        "long_short_ratio": analysis.get("long_short_ratio"),
        "current_price": analysis.get("current_price"),
        "trend_status": analysis.get("trend_status"),
        # long-window direction features (parameter-upgrade Phase 0.2) — also
        # exactly the fields the confluence engine reads from `analysis`
        "signal_score": analysis.get("signal_score"),
        "volume_ratio": analysis.get("volume_ratio"),
        "price_above_ma200": analysis.get("price_above_ma200"),
        "momentum_12_1_pct": analysis.get("momentum_12_1_pct"),
        "sigma_daily_pct": analysis.get("sigma_daily_pct"),
        # Forwarded so the D5 verifier can age this read (Plan 06 D5b). The
        # feed builds it fresh per call today, but that is a property of the
        # feed, not a promise — carry the stamp rather than assume.
        "as_of": analysis.get("as_of"),
        "evidence": (analysis.get("bullish_factors") or [])[:2]
                    + (analysis.get("risk_factors") or [])[:2],
    }


def _sentiment_component(symbol: str) -> Optional[dict[str, Any]]:
    try:
        from analysis_sources import fetch_stocktwits_sentiment
        st = fetch_stocktwits_sentiment(f"{symbol}.X")
    except Exception as exc:  # noqa: BLE001
        logger.debug("fusion sentiment unavailable for %s: %s", symbol, exc)
        return None
    if not st or not st.get("messages_scored"):
        return None
    bull, bear = st["bullish"], st["bearish"]
    scored = st["messages_scored"]
    return {
        "value": _clamp((bull - bear) / scored),
        "bullish": bull,
        "bearish": bear,
        "messages_scored": scored,
        "evidence": [f"StockTwits {bull} bull / {bear} bear (n={scored})"],
    }


def _psych_component() -> Optional[dict[str, Any]]:
    """Market-wide psychology read (symbol-independent) from the Phase 2 feed."""
    try:
        from psych_feed import get_psych_payload
        psych = get_psych_payload()
    except Exception as exc:  # noqa: BLE001
        logger.debug("fusion psych unavailable: %s", exc)
        return None
    if not psych.get("available"):
        return None

    value = 0.0
    evidence: list[str] = []
    fng = psych.get("fear_greed") or {}
    delta_3d = fng.get("delta_3d")
    if delta_3d is not None:
        value += _clamp(delta_3d / 20.0)
        evidence.append(f"F&G {fng.get('value')} ({fng.get('classification')}), Δ3d {delta_3d:+d}")
    negative_spikes = [s for s in psych.get("spikes", [])
                       if s.get("spike") and s.get("direction") == "negative"]
    if negative_spikes:
        value -= 0.5
        s = negative_spikes[0]
        evidence.append(f"negative sentiment spike in {s.get('category')} (z={s.get('z')})")
    odds_up = [d for d in psych.get("odds_deltas", []) if d.get("delta", 0) >= ODDS_RERATING_MIN]
    if odds_up:
        value += 0.25
        d = odds_up[0]
        evidence.append(f"odds re-rating {d.get('title')}: {d.get('odds_from')}→{d.get('odds_to')}")
    shocks = [s for s in psych.get("shock", []) if s.get("shock")]
    return {
        "value": _clamp(value),
        # F&G's as_of is the VENDOR's print time (updates daily); the payload's
        # created_at is when we assembled the read. Both are forwarded for D5b:
        # they age differently, and the gap between them is itself information.
        "fear_greed": {k: fng.get(k) for k in ("value", "classification", "delta_3d", "as_of")},
        "negative_spikes": negative_spikes,
        "odds_reratings": odds_up[:3],
        "shocks": shocks,
        "as_of": psych.get("created_at"),
        "evidence": evidence or ["psych feed live, no strong reads"],
    }


# ─────────────────────────── trigger matching (plan §4) ───────────────────────────

def _matched_triggers(quant, sentiment, psych) -> list[str]:
    triggers = []
    fng_delta = ((psych or {}).get("fear_greed") or {}).get("delta_3d")
    senti_val = (sentiment or {}).get("value")
    basis = (quant or {}).get("basis_pct")
    if (fng_delta is not None and fng_delta >= FNG_RECOVERY_DELTA
            and senti_val is not None and senti_val > SENTIMENT_BUY_MIN
            and basis is not None and basis >= BASIS_BUY_GAP_PCT):
        triggers.append(f"buy: F&G recovery +{fng_delta} · sentiment {senti_val:+.2f} · basis {basis:.2f}%")
    if psych and psych.get("odds_reratings"):
        # Odds come from the top Polymarket markets by volume (any topic), so
        # this is a market-wide anticipation read, not a per-symbol buy call.
        d = psych["odds_reratings"][0]
        triggers.append(
            f"anticipation (market-wide): odds re-rating {d.get('odds_from')}→{d.get('odds_to')}")
    rsi = (quant or {}).get("rsi_14")
    if (rsi is not None and rsi >= RSI_OVERBOUGHT and psych and psych.get("negative_spikes")):
        triggers.append(f"sell: RSI {rsi:.0f} overbought · negative sentiment spike")
    if psych and psych.get("shocks"):
        s = psych["shocks"][0]
        triggers.append(f"reduce: volatility shock {s.get('symbol')} ({s.get('sigma_multiple')}σ, estimated)")
    return triggers


# ─────────────────────────── fusion ───────────────────────────

def fuse_symbol(symbol: str, psych: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """One symbol's fused signal. psych may be passed in to share the
    market-wide component across a multi-symbol call."""
    symbol = (symbol or "").strip().upper()
    quant = _quant_component(symbol)
    sentiment = _sentiment_component(symbol)
    if psych is None:
        psych = _psych_component()

    components = {"quant": quant, "sentiment": sentiment, "psych": psych}
    weights = _weights()
    available = {k: v for k, v in components.items() if v is not None}
    missing = sorted(set(components) - set(available))

    if available:
        weight_sum = sum(weights[k] for k in available)
        score = sum(weights[k] * available[k]["value"] for k in available) / weight_sum
    else:
        score = 0.0

    signal = "buy" if score >= BUY_THRESHOLD else ("sell" if score <= SELL_THRESHOLD else "hold")
    if not available:
        signal = "hold"
    elif set(available) == {"psych"}:
        # Structural invariant: renormalizing over available components would
        # otherwise let a psych-only read carry full weight. Psychology may
        # inform the score but never decides alone — force hold.
        signal = "hold"

    evidence: list[str] = []
    for key in ("quant", "sentiment", "psych"):
        if components[key]:
            evidence.extend(components[key]["evidence"])

    # Card 07 — scheduled macro releases are volatility events; surface them
    # in evidence so readers (and the automation guard) see the context.
    event_window = None
    try:
        from market_events import active_event_window, upcoming_events
        event_window = active_event_window()
        if event_window:
            evidence.append(
                f"{event_window['title']} release window active "
                f"({event_window['minutes_to_release']}min to release — scheduled volatility)")
        else:
            nxt = upcoming_events(limit=1)
            if nxt and nxt[0]["hours_until"] <= 24:
                evidence.append(
                    f"{nxt[0]['title']} in {nxt[0]['hours_until']}h (scheduled volatility event)")
    except Exception:  # noqa: BLE001
        pass

    # Confluence checklist (parameter-upgrade Phase 1) — count-based B1–B6/
    # S1–S6 read, display/API only until the Phase-4 flip. Fail-soft.
    confluence_block = None
    try:
        from confluence import evaluate_confluence
        confluence_block = evaluate_confluence(symbol, "crypto", analysis=quant)
    except Exception as exc:  # noqa: BLE001
        logger.debug("fusion confluence unavailable for %s: %s", symbol, exc)

    payload = {
        "symbol": symbol,
        "score": round(score, 3),
        "signal": signal,
        "confluence": confluence_block,
        "confidence": round(min(0.95, 0.5 + abs(score) / 2), 2) if available else 0.0,
        "weights": {k: round(weights[k], 3) for k in weights},
        "components": {
            k: ({**v, "weight": round(weights[k], 3)} if v else None)
            for k, v in components.items()
        },
        "missing": missing,
        "matched_triggers": (_matched_triggers(quant, sentiment, psych)
                             + (["event_window"] if event_window else [])),
        "event_window": event_window,
        "evidence": evidence,
        "current_price": (quant or {}).get("current_price"),
        "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "fusion_source": "rule",
        "note": "psych weight structurally capped at "
                f"{PSYCH_WEIGHT_MAX} — psychology never trades alone",
    }

    # AI-native fusion (Plan 06 D4) is the PRIMARY path when enabled: the model
    # weighs the full factor snapshot itself instead of the fixed 0.5/0.3/0.2.
    # The deterministic result above stays as the fail-soft fallback and every
    # payload says which one produced it (`fusion_source`) — a rule-based score
    # is never passed off as an AI one.
    try:
        from ai_fusion import fuse_with_ai
        ai = fuse_with_ai(symbol, quant, sentiment, psych)
        if ai:
            payload["rule_fusion"] = {"score": payload["score"], "signal": payload["signal"],
                                      "confidence": payload["confidence"]}
            payload.update({
                "score": ai["score"], "signal": ai["signal"], "confidence": ai["confidence"],
                "fusion_source": "ai", "llm_model": ai.get("llm_model"),
                "ai_components": ai.get("ai_components"), "ai_weights": ai.get("ai_weights"),
                "rationale": ai.get("rationale"),
                "evidence": (ai.get("evidence") or []) + evidence,
                "note": "AI-fused: the model weighed the factor snapshot itself; "
                        "psychology-only reads are still forced to hold",
            })
    except Exception as exc:  # noqa: BLE001
        logger.debug("ai fusion unavailable for %s: %s", symbol, exc)
        payload["fusion_source"] = "rule-fallback"

    return payload


def fuse_symbols(symbols: list[str]) -> list[dict[str, Any]]:
    psych = _psych_component()  # market-wide: fetch once, share across symbols
    return [fuse_symbol(s, psych=psych) for s in symbols]
