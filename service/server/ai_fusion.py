"""AI-native signal fusion (Plan 06 D4).

Directive: signals are aggregated, calculated and verified BY THE AI — not by
fixed programming. This module replaces the hand-tuned 0.5/0.3/0.2 weighted
sum as the PRIMARY fusion path: the decision-tier model receives the complete
factor snapshot (quant indicators, sentiment, psychology, cross-market,
events, whale flows, ETF flows) and returns its own component scores, fused
verdict, confidence and rationale.

What stays deterministic, and why (the honest split):
  * The DETERMINISTIC fusion remains as a fail-soft FALLBACK only — when the
    model is unconfigured, unreachable or returns something unusable. Every
    payload is labeled `fusion_source: ai | rule-fallback` so a reader can
    always tell which produced the number. We never silently pass a rule-based
    score off as an AI one.
  * Two structural invariants survive because they are safety, not judgment:
    a psychology-only read can never be a trade (forced hold), and the
    verdict/confidence are range-clamped. The model chooses freely inside
    that box; it cannot redefine the box.
  * Downstream, the risk gate, breakers and budget caps are untouched.

Gated by AI_FUSION_ENABLED (default off) so the deterministic path stays the
default until the AI path has been observed in production telemetry.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

VALID_SIGNALS = ("buy", "sell", "hold")

# Cost control. The fusion ENDPOINT caches for 30s — right for cheap API
# fan-out, ruinous for a frontier model (3 symbols × 120 refresh/h ≈ 8.6k
# calls/day with one dashboard open). AI verdicts get their own, much longer
# cache: the factors they weigh (trend, regime, flows) move on minutes, not
# seconds. Tunable per deployment.
_AI_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


def ai_fusion_enabled() -> bool:
    return os.getenv("AI_FUSION_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}


def ai_fusion_ttl() -> int:
    try:
        return max(60, int(os.getenv("AI_FUSION_TTL", "900")))
    except ValueError:
        return 900


def ai_fusion_tier() -> str:
    """Which model tier fuses. 'decision' (Opus) reasons best about conflicting
    factors; 'brief' (Haiku) is ~20× cheaper if fusion runs hot."""
    tier = os.getenv("AI_FUSION_TIER", "decision").strip().lower()
    return tier if tier in ("brief", "decision") else "decision"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_factor_snapshot(symbol: str, quant: Optional[dict[str, Any]],
                          sentiment: Optional[dict[str, Any]],
                          psych: Optional[dict[str, Any]]) -> dict[str, Any]:
    """Everything the model scores from. Components already gathered by
    signal_fusion are passed in; the rest is fetched here, fail-soft."""
    snapshot: dict[str, Any] = {
        "symbol": symbol,
        "quant": quant,
        "sentiment": sentiment,
        "psych": psych,
        "as_of": _now_iso(),
    }
    try:
        from cross_market import build_cross_market_payload, cross_market_enabled
        if cross_market_enabled():
            cm = build_cross_market_payload() or {}
            snapshot["cross_market"] = {"kimchi": cm.get("kimchi"), "dxy": cm.get("dxy")}
    except Exception:  # noqa: BLE001
        pass
    try:
        from market_events import active_event_window, upcoming_events
        snapshot["event_window"] = active_event_window()
        nxt = upcoming_events(limit=1)
        snapshot["next_event"] = ({"title": nxt[0].get("title"),
                                   "hours_until": nxt[0].get("hours_until")} if nxt else None)
    except Exception:  # noqa: BLE001
        pass
    try:
        from whale_feed import get_whale_payload
        w = get_whale_payload()
        if w.get("available"):
            snapshot["whales"] = w.get("totals")
    except Exception:  # noqa: BLE001
        pass
    try:
        from market_intel import get_etf_flows_payload
        etf = get_etf_flows_payload()
        if etf.get("summary"):
            snapshot["etf_flows"] = etf["summary"]
    except Exception:  # noqa: BLE001
        pass
    try:
        from calibration import get_calibration
        cal = get_calibration()
        if cal.get("available"):
            snapshot["live_calibration"] = cal["buckets"]
    except Exception:  # noqa: BLE001
        pass
    return snapshot


PROMPT_HEADER = (
    "You are the signal fusion engine for a paper-trading research platform. "
    "Aggregate the factor snapshot below into ONE verdict for this symbol.\n"
    "You decide how much each factor matters — there is no fixed weighting. "
    "Reason about agreement, contradiction, staleness and missing data. "
    "Be conservative when factors conflict or when key data is absent.\n"
    "HARD RULES you cannot override: (1) psychology alone never justifies a "
    "trade — if the only usable evidence is psychological, the verdict is "
    "'hold'; (2) score is -1..1 and confidence is 0..1.\n"
    "Respond with ONLY a JSON object:\n"
    '{"signal":"buy|sell|hold","score":-1..1,"confidence":0..1,'
    '"components":{"quant":-1..1,"sentiment":-1..1,"psych":-1..1},'
    '"weights_used":{"quant":0..1,"sentiment":0..1,"psych":0..1},'
    '"evidence":["short factual bullets, each citing a real number"],'
    '"rationale":"1-2 sentences"}\n\n'
)


def _parse(text: str) -> Optional[dict[str, Any]]:
    if not text:
        return None
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        obj = json.loads(match.group(0))
    except Exception:  # noqa: BLE001
        return None
    if str(obj.get("signal", "")).lower() not in VALID_SIGNALS:
        return None
    return obj


def _clamp(v: Any, lo: float, hi: float, default: float) -> float:
    try:
        return max(lo, min(hi, float(v)))
    except (TypeError, ValueError):
        return default


def fuse_with_ai(symbol: str, quant: Optional[dict[str, Any]],
                 sentiment: Optional[dict[str, Any]],
                 psych: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """AI fusion for one symbol. Returns None when unavailable/unusable so the
    caller can fall back to the deterministic path (and label it)."""
    from llm_client import active_provider_model, generate_text, llm_configured
    if not ai_fusion_enabled() or not llm_configured():
        return None

    # Serve a recent AI verdict rather than paying for a frontier call on every
    # 30s dashboard poll. Cached entries carry the age they were served at, so
    # a reader can see the verdict is a minute old rather than assume it is live.
    cached = _AI_CACHE.get(symbol)
    if cached and time.time() - cached[0] < ai_fusion_ttl():
        return {**cached[1], "cached_age_s": int(time.time() - cached[0])}

    snapshot = build_factor_snapshot(symbol, quant, sentiment, psych)
    prompt = (PROMPT_HEADER +
              f"FACTOR SNAPSHOT (JSON):\n{json.dumps(snapshot, ensure_ascii=False, default=str)[:8000]}\n")
    tier = ai_fusion_tier()
    parsed = _parse(generate_text(prompt, max_tokens=700, temperature=0.2,
                                  tier=tier) or "")
    if not parsed:
        return None

    signal = str(parsed["signal"]).lower()
    score = _clamp(parsed.get("score"), -1.0, 1.0, 0.0)
    confidence = _clamp(parsed.get("confidence"), 0.0, 1.0, 0.5)

    # Structural invariant (safety, not judgment): psychology never trades alone.
    usable = [k for k, v in (("quant", quant), ("sentiment", sentiment)) if v is not None]
    if not usable and signal != "hold":
        signal = "hold"
        parsed.setdefault("evidence", []).append(
            "forced hold: psychology-only evidence never trades alone (structural rule)")

    components = parsed.get("components") if isinstance(parsed.get("components"), dict) else {}
    weights_used = parsed.get("weights_used") if isinstance(parsed.get("weights_used"), dict) else {}
    evidence = [str(e)[:200] for e in (parsed.get("evidence") or [])][:8]

    result = {
        "signal": signal,
        "score": round(score, 3),
        "confidence": round(confidence, 2),
        "ai_components": {k: _clamp(components.get(k), -1.0, 1.0, 0.0)
                          for k in ("quant", "sentiment", "psych") if k in components},
        "ai_weights": {k: _clamp(weights_used.get(k), 0.0, 1.0, 0.0)
                       for k in ("quant", "sentiment", "psych") if k in weights_used},
        "evidence": evidence,
        "rationale": str(parsed.get("rationale") or "")[:500],
        "fusion_source": "ai",
        "llm_model": active_provider_model(tier=tier),
        "fused_at": _now_iso(),
    }
    _AI_CACHE[symbol] = (time.time(), result)
    return {**result, "cached_age_s": 0}
