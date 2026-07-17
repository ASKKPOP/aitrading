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

# The cache is keyed by symbol on a PUBLIC endpoint, so its size is decided by
# callers, not by us. Bounded and evicted oldest-first: a loop over novel
# symbols must not grow it forever. Comfortably above any real watchlist.
_AI_CACHE_MAX = 64


def ai_fusion_enabled() -> bool:
    return os.getenv("AI_FUSION_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}


def ai_fusion_ttl() -> int:
    try:
        return max(60, int(os.getenv("AI_FUSION_TTL", "900")))
    except ValueError:
        return 900


def ai_fusion_tier() -> str:
    """Which model tier fuses. 'decision' (Opus) reasons best about conflicting
    factors — which is the whole job here; 'brief' (Sonnet since 2026-07-17)
    is the cheaper fallback if fusion ever runs hot."""
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
            # The kimchi premium is measured on BTC (Upbit KRW-BTC vs OKX
            # BTC-USDT) and read as a market-wide Korean-retail-demand gauge,
            # so it rides along for every symbol. Unlabelled, that put ~$63k
            # BTC prices inside an ETH snapshot — the D5 verifier flagged it
            # 'suspect' (high) on 2026-07-17, correctly: nothing said whose
            # prices those were. Say what it measures instead of stripping it.
            snapshot["cross_market"] = {"kimchi": cm.get("kimchi"), "dxy": cm.get("dxy"),
                                        "as_of": cm.get("as_of"),
                                        "measured_on": "BTCUSDT",
                                        "scope": "market-wide (Korean retail demand gauge; "
                                                 "its prices are BTC's, not this symbol's)"}
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
            # Carry the feed's own stamp (D5b). Whale totals are all-zero both
            # when nothing moved and when the feed is broken — without an age,
            # those two read identically to the verifier.
            snapshot["whales"] = {**(w.get("totals") or {}), "as_of": w.get("created_at")}
    except Exception:  # noqa: BLE001
        pass
    try:
        from market_intel import get_etf_flows_payload
        etf = get_etf_flows_payload()
        summary = etf.get("summary") or {}
        if summary:
            # The real (SoSoValue) summary is merged OVER the estimated proxy,
            # which leaves the proxy's per-ETF counts behind at zero when its
            # rows came back empty. Passing those on shows the model
            # "direction: inflow" beside "net_score: 0" — a contradiction that
            # isn't real. Send the counts only when they describe real rows.
            keep = {k: v for k, v in summary.items()
                    if k not in ("inflow_count", "outflow_count", "tracked_count", "net_score")}
            if summary.get("tracked_count"):
                keep.update({k: summary[k] for k in
                             ("inflow_count", "outflow_count", "tracked_count", "net_score")
                             if k in summary})
            # The headline direction/summary come from BTC alone (sosovalue_etf:
            # "BTC decides the headline direction; ETH rides along"), while the
            # eth block carries its own flows — so the headline can say inflow
            # while ETH shows an outflow. That is not a contradiction, but only
            # if the payload says which asset the headline speaks for.
            if keep.get("direction"):
                keep["headline_measured_on"] = "BTC"
            snapshot["etf_flows"] = keep
    except Exception:  # noqa: BLE001
        pass
    try:
        from calibration import get_calibration
        cal = get_calibration()
        if cal.get("available"):
            snapshot["live_calibration"] = {"buckets": cal["buckets"],
                                            "as_of": cal.get("generated_at")}
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
    "'hold'; (2) score is -1..1 and confidence is 0..1; (3) psychology may "
    "never LEAD the score — its weight must not exceed 0.3, and a verdict that "
    "declares otherwise is discarded. Weigh the other factors as you see fit.\n"
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

    # THE STRUCTURAL INVARIANT, enforced by not asking: psychology alone never
    # trades. With no quant and no sentiment the verdict is 'hold' whatever the
    # model answers, so the model is not consulted — it cannot argue its way
    # past a rule it is never shown. The caller's rule path produces the hold.
    #
    # This also closes a real cost vector: the fusion endpoint is public and
    # unauthenticated, and a made-up symbol (quant=None, sentiment=None) bought
    # two Opus calls and ~21s of a threadpool worker — an anonymous loop over
    # junk symbols was a money pump. (Audit 2026-07-17, 4/4 QA confirmed.)
    if quant is None and sentiment is None:
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

    # The box the model may not redefine: psychology never LEADS the score.
    # The rule path enforces this by construction (PSYCH_WEIGHT_MAX
    # re-normalizes at signal_fusion.py:69); the AI path could not, because the
    # model's score is used directly and cannot be decomposed. So we enforce it
    # on the model's own declaration — a verdict that says psychology led is
    # discarded, and the deterministic path answers instead.
    #
    # This is honesty as much as safety: the Signals Board tells users the
    # psych weight is structurally capped, and until now that was true only of
    # the rule path. (Audit 2026-07-17, 4/4 QA.)
    from signal_fusion import PSYCH_WEIGHT_MAX
    declared = parsed.get("weights_used") if isinstance(parsed.get("weights_used"), dict) else {}
    declared_psych = _clamp(declared.get("psych"), 0.0, 1.0, 0.0)
    if declared_psych > PSYCH_WEIGHT_MAX:
        logger.warning("ai fusion for %s declared psych weight %.2f > %.2f — discarded",
                       symbol, declared_psych, PSYCH_WEIGHT_MAX)
        return None

    # Structural invariant (safety, not judgment): psychology never trades alone.
    components = parsed.get("components") if isinstance(parsed.get("components"), dict) else {}
    weights_used = parsed.get("weights_used") if isinstance(parsed.get("weights_used"), dict) else {}
    evidence = [str(e)[:200] for e in (parsed.get("evidence") or [])][:8]

    result: dict[str, Any] = {
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

    # D5: verify the inputs the verdict was built from. Runs inside the cache
    # so it costs once per TTL alongside the fusion call, not once per poll.
    # Fail-open — a verifier that errors must not sink a usable verdict.
    try:
        from data_verify import apply_verification, verify_snapshot
        result = apply_verification(result, verify_snapshot(snapshot))
    except Exception as exc:  # noqa: BLE001
        logger.warning("data verification failed for %s: %s", symbol, exc)

    _AI_CACHE[symbol] = (time.time(), result)
    while len(_AI_CACHE) > _AI_CACHE_MAX:
        _AI_CACHE.pop(min(_AI_CACHE, key=lambda k: _AI_CACHE[k][0]), None)
    return {**result, "cached_age_s": 0}
