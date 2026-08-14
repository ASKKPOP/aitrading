"""Multi-agent trading analysis engine.

Four analyst roles gather data and write briefs, then a Trader + Risk team debates
them into a single decision (BUY / SELL / HOLD) plus a written report:

    News analyst          market + macro news with sentiment (Alpha Vantage; FinnHub/Reddit optional)
    Sentiment analyst     aggregated ticker / market sentiment (+ StockTwits optional)
    Fundamentals + macro  macro-regime signals + Polymarket prediction markets (+ FRED optional)
    Technical analyst     price / moving averages / support-resistance / signal score
    Trader + Risk team    debate all four -> decision + confidence + report

Powered by the multi-provider LLM client (llm_client.py) — OpenAI, Gemini, Grok,
Qwen, GLM, local, OpenRouter, or Anthropic. If no provider is configured, every
role falls back to a deterministic, data-grounded brief so the engine always runs.
Optional data sources (FinnHub / FRED / StockTwits) are added by analysis_sources.py
and merged in when their keys are present; missing sources are simply skipped.
"""

from __future__ import annotations

import contextvars
import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from llm_client import generate_text, llm_configured

logger = logging.getLogger(__name__)

VALID_ACTIONS = ("buy", "sell", "hold")

# Progress callback: receives {"step": str, "status": "start"|"done"|"error", "ts": iso, ...}.
# Used by the streaming endpoint to show the pipeline live; must never break the run.
ProgressFn = Callable[[dict[str, Any]], None]


def _emit(progress: Optional[ProgressFn], step: str, status: str, **extra: Any) -> None:
    if progress is None:
        return
    try:
        progress({"step": step, "status": status, "ts": _now_iso(), **extra})
    except Exception:  # noqa: BLE001 — a broken listener must not kill analysis
        pass


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─────────────────────────── data gathering ───────────────────────────

def _gather_technical(symbol: str, market: str) -> dict[str, Any]:
    if market == "us-stock":
        try:
            from market_intel import _build_stock_analysis
            return _build_stock_analysis(symbol)
        except Exception as exc:  # noqa: BLE001
            return {"symbol": symbol, "market": market, "error": str(exc)}
    # crypto: full quant technicals from OKX (Phase 3) — RSI/MA/σ/funding/basis.
    # Falls back to the light spot-price path when disabled or OKX is unreachable.
    if market == "crypto":
        try:
            from quant_crypto import build_crypto_analysis, quant_crypto_enabled
            if quant_crypto_enabled():
                return build_crypto_analysis(symbol)
        except Exception as exc:  # noqa: BLE001
            logger.warning("quant crypto technicals failed for %s, using light path: %s",
                           symbol, exc)
    # polymarket / fallback: light technical from the live price
    try:
        from price_fetcher import get_price_from_market
        price = get_price_from_market(symbol, _now_iso(), market)
        out = {"symbol": symbol, "market": market, "current_price": price,
               "note": "light technical (spot price only) for non-equity market"}
        # Plan 25 Phase B: forex was the only fleet market whose technical
        # analyst saw nothing but the spot price. Attach the risk-sentiment
        # facts (equity F&G + dollar index), fail-soft — the analyst reads
        # them as regime context, never as a pair-level signal.
        if market == "forex":
            risk: dict[str, Any] = {}
            try:
                import psych_feed
                fg = psych_feed.us_fear_greed()
                if fg:
                    risk["fear_greed"] = fg
            except Exception:  # noqa: BLE001
                pass
            try:
                import cross_market
                dxy = cross_market.dollar_index_cached()
                if dxy:
                    risk["dollar_index"] = dxy
            except Exception:  # noqa: BLE001
                pass
            if risk:
                out["risk_sentiment"] = risk
        return out
    except Exception as exc:  # noqa: BLE001
        return {"symbol": symbol, "market": market, "error": str(exc)}


def _gather_news(symbol: str, market: str) -> dict[str, Any]:
    out: dict[str, Any] = {"items": [], "sentiment_breakdown": {}}
    try:
        from market_intel import get_market_news_payload
        payload = get_market_news_payload(limit=6)
        # The snapshot's age travels with the items: the analyst must be able
        # to weigh stale headlines itself (the quota-limited feed can be
        # many hours old), and a timestamp it never sees cannot be weighed.
        out["as_of"] = payload.get("last_updated_at")
        for cat in payload.get("categories", []):
            for it in cat.get("items", [])[:4]:
                out["items"].append({
                    "title": it.get("title"),
                    "source": it.get("source"),
                    "sentiment": it.get("overall_sentiment_label"),
                    "category": cat.get("label") or cat.get("category"),
                })
    except Exception as exc:  # noqa: BLE001
        out["error"] = str(exc)
    # optional external sources (FinnHub / Reddit) — skipped if keys absent
    try:
        from analysis_sources import fetch_finnhub_news
        extra = fetch_finnhub_news(symbol)
        if extra:
            out["items"].extend(extra)
            out["finnhub_count"] = len(extra)
    except Exception:  # noqa: BLE001
        pass
    labels = [i.get("sentiment") for i in out["items"] if i.get("sentiment")]
    breakdown: dict[str, int] = {}
    for lab in labels:
        key = str(lab).lower()
        breakdown[key] = breakdown.get(key, 0) + 1
    out["sentiment_breakdown"] = breakdown
    out["count"] = len(out["items"])
    return out


def _whale_context(symbol: str) -> Optional[dict[str, Any]]:
    """Whale events relevant to this symbol (BTC/ETH only today). Fail-soft."""
    try:
        from whale_feed import get_whale_payload
        payload = get_whale_payload()
        if not payload.get("available"):
            return None
        base = symbol.replace("USDT", "").replace("USD", "")
        events = [e for e in payload["events"] if e["chain"] == base][:5]
        if not events and base not in ("BTC", "ETH"):
            return None
        return {"events": events, "totals": payload["totals"]}
    except Exception:  # noqa: BLE001
        return None


def _gather_sentiment(symbol: str, market: str, news: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {"from_news": news.get("sentiment_breakdown", {})}
    try:
        from analysis_sources import fetch_stocktwits_sentiment
        st = fetch_stocktwits_sentiment(symbol)
        if st:
            out["stocktwits"] = st
    except Exception:  # noqa: BLE001
        pass
    # Social feed (Plan 11 F5): crowd tilt from Facebook (SEA) / X (elsewhere).
    try:
        from social_feed import social_sentiment_for
        social = social_sentiment_for(symbol)
        if social:
            out["social"] = social
    except Exception:  # noqa: BLE001
        pass
    # Psych feed (Phase 2): F&G index, sentiment-spike z-scores, odds deltas.
    try:
        from psych_feed import get_psych_payload
        psych = get_psych_payload()
        if psych.get("available"):
            out["psych"] = {
                "fear_greed": {k: psych["fear_greed"][k]
                               for k in ("value", "classification", "delta_3d")}
                              if psych.get("fear_greed") else None,
                "spikes": [s for s in psych.get("spikes", []) if s.get("spike")],
                "odds_deltas": psych.get("odds_deltas", [])[:5],
                "shock": psych.get("shock", []),
                "shock_note": psych.get("shock_note"),
            }
    except Exception:  # noqa: BLE001
        pass
    # Plan 06 B1 — real whale flows for BTC/ETH (exchange in/out + large transfers)
    whales = _whale_context(symbol)
    if whales:
        out["whales"] = whales
    return out


def _gather_fundamentals_macro(symbol: str, market: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    try:
        from market_intel import get_macro_signals_payload
        macro = get_macro_signals_payload()
        out["macro"] = {
            "verdict": macro.get("verdict"),
            "bullish_count": macro.get("bullish_count"),
            "total_count": macro.get("total_count"),
            "signals": [{"name": s.get("name"), "status": s.get("status")}
                        for s in (macro.get("signals") or [])[:6]],
        }
    except Exception as exc:  # noqa: BLE001
        out["macro_error"] = str(exc)
    try:
        from price_fetcher import list_polymarket_markets
        pm = list_polymarket_markets(limit=5)
        out["polymarket"] = [{"title": m.get("title"), "volume_24hr": m.get("volume_24hr")}
                             for m in (pm or [])]
    except Exception as exc:  # noqa: BLE001
        out["polymarket_error"] = str(exc)
    try:
        from analysis_sources import fetch_fred_macro
        fred = fetch_fred_macro()
        if fred:
            out["fred"] = fred
    except Exception:  # noqa: BLE001
        pass
    return out


# ─────────────────────────── output language ───────────────────────────

# The UI ships six languages (frontend i18n.ts); the analyst briefs and the
# trader report are the only free-text the LLM writes, so they have to follow
# the same top-bar selection. Anything unknown falls back to English.
#
# This dict is the single source of truth for "which languages exist" — the
# error catalogue, the alert catalogue and the Accept-Language parser all
# derive their supported set from normalize_lang rather than keeping a second
# list that could drift.
LANG_NAMES = {"ko": "Korean", "en": "English", "ja": "Japanese",
              "th": "Thai", "vi": "Vietnamese", "id": "Indonesian"}


def normalize_lang(value: Optional[str]) -> str:
    """Map a UI language code (possibly a full locale like 'ko-KR') to a
    supported code. Unknown values become 'en'."""
    code = (value or "en").strip().lower().replace("_", "-").split("-")[0]
    return code if code in LANG_NAMES else "en"


# ─────────────────────────── analyst briefs ───────────────────────────

def _brief(role: str, instructions: str, data: dict[str, Any], lang: str) -> str:
    """Ask the LLM for a short brief; fall back to a compact data dump."""
    if not llm_configured():
        return _fallback_brief(role, data)
    lang_line = f"Write in {LANG_NAMES[normalize_lang(lang)]}."
    prompt = (
        f"You are the {role} on a trading desk. {instructions}\n"
        f"{lang_line} Be concrete and under 90 words. No disclaimers, no bullet lists.\n\n"
        f"Data (JSON):\n{json.dumps(data, ensure_ascii=False, default=str)[:6000]}\n"
    )
    text = generate_text(prompt, max_tokens=220, temperature=0.4, tier="brief")
    return text or _fallback_brief(role, data)


def _fallback_brief(role: str, data: dict[str, Any]) -> str:
    """Readable, rule-based brief used when no LLM provider is configured.
    Summarises the gathered data per analyst instead of dumping raw JSON."""
    if data.get("error"):
        return f"[{role}] data unavailable: {data['error']}"

    # Technical analyst — signal / score / price / trend
    if "signal" in data or str(data.get("note", "")).startswith("light technical"):
        sig = str(data.get("signal") or "neutral").lower()
        trend = data.get("trend_status")
        bits = []
        if data.get("current_price") is not None:
            bits.append(f"price {data['current_price']}")
        if data.get("signal_score") is not None:
            bits.append(f"score {data['signal_score']}")
        msg = f"Technical read is {sig}" + (f" ({trend})" if trend else "")
        if bits:
            msg += " — " + ", ".join(bits)
        msg += "."
        bull = data.get("bullish_factors") or []
        risk = data.get("risk_factors") or []
        if bull:
            msg += " Supports: " + "; ".join(bull[:2]) + "."
        if risk:
            msg += " Risks: " + "; ".join(risk[:2]) + "."
        return msg

    # News analyst — headline count, tone, lead headline
    if "items" in data:
        items = data.get("items") or []
        bd = data.get("sentiment_breakdown") or {}
        bull = bd.get("bullish", 0) + bd.get("somewhat-bullish", 0)
        bear = bd.get("bearish", 0) + bd.get("somewhat-bearish", 0)
        tone = "constructive" if bull > bear else ("cautious" if bear > bull else "mixed")
        # State the snapshot's age once it can matter (>= 2h): the decision
        # about how much stale news is worth belongs to the analyst reading
        # this brief, and it can only make it if the age is in the brief.
        age = ""
        as_of = data.get("as_of")
        if as_of:
            try:
                as_of_dt = datetime.fromisoformat(str(as_of).replace("Z", "+00:00"))
                hours = (datetime.now(timezone.utc) - as_of_dt).total_seconds() / 3600
                if hours >= 2:
                    age = f" (newest headline snapshot {hours:.0f}h old)"
            except ValueError:
                pass
        msg = f"{len(items)} headlines scanned{age} — tone {tone} ({bull} bullish vs {bear} bearish)."
        if items and items[0].get("title"):
            msg += f' Lead: "{items[0]["title"]}".'
        return msg

    # Sentiment analyst — net sentiment from news (+ StockTwits if present)
    if "from_news" in data:
        bd = data.get("from_news") or {}
        bull = bd.get("bullish", 0) + bd.get("somewhat-bullish", 0)
        bear = bd.get("bearish", 0) + bd.get("somewhat-bearish", 0)
        lean = "bullish" if bull > bear else ("bearish" if bear > bull else "neutral")
        msg = f"News-derived sentiment leans {lean} ({bull} vs {bear})."
        st = data.get("stocktwits")
        if isinstance(st, dict) and st:
            msg += f" StockTwits {st.get('bullish', '?')} bull / {st.get('bearish', '?')} bear."
        psych = data.get("psych") or {}
        fng = psych.get("fear_greed")
        if isinstance(fng, dict) and fng.get("value") is not None:
            msg += f" Fear & Greed {fng['value']} ({fng.get('classification')})."
        spikes = psych.get("spikes") or []
        if spikes:
            s = spikes[0]
            msg += f" Sentiment spike in {s.get('category')} (z={s.get('z')}, {s.get('direction')})."
        return msg

    # Fundamentals / macro analyst — macro regime verdict
    if "macro" in data:
        m = data.get("macro") or {}
        verdict = m.get("verdict") or "unavailable"
        return f"Macro regime reads {verdict} ({m.get('bullish_count', 0)}/{m.get('total_count', 0)} signals bullish)."

    compact = json.dumps(data, ensure_ascii=False, default=str)
    return f"[{role}] key data: {compact[:300]}"


# ─────────────────────────── trader + risk decision ───────────────────────────

def _rule_based_decision(technical: dict[str, Any], news: dict[str, Any]) -> dict[str, Any]:
    signal = str(technical.get("signal") or "hold").lower()
    action = signal if signal in VALID_ACTIONS else "hold"
    score = technical.get("signal_score")
    breakdown = news.get("sentiment_breakdown", {})
    bull = breakdown.get("bullish", 0) + breakdown.get("somewhat-bullish", 0)
    bear = breakdown.get("bearish", 0) + breakdown.get("somewhat-bearish", 0)
    confidence = 0.5
    if isinstance(score, (int, float)):
        # |score| — conviction strength is direction-agnostic. A strongly
        # negative score is a confident SELL, not a low-confidence one.
        confidence = max(0.3, min(0.9, 0.5 + abs(score) / 20.0))
    rationale = (
        f"Technical signal is '{signal}'"
        + (f" (score {score})" if score is not None else "")
        + f"; news sentiment {bull} bullish vs {bear} bearish."
    )
    return {"action": action, "confidence": round(confidence, 2), "entry": technical.get("current_price"),
            "target": None, "stop": None, "rationale": rationale, "report": rationale}


def _strip_markdown_emphasis(text: str) -> str:
    """Drop `**` that the model emitted OUTSIDE a string literal.

    gpt-oss intermittently bolds a JSON key — `**"confidence": 0.57,` — and
    json.loads then rejects the entire object, so _json_objects skips it and a
    complete decision is lost: the run journals confidence 0.0, conviction null
    and scores null, then defaults to hold. Prod runs 923 cycle 9 and 928
    cycle 2 (2026-08-02) and run 939 cycle 18 (2026-08-03), the last carrying a
    usable confidence 0.57 and all four component scores.

    Emphasis INSIDE a string is CONTENT, not corruption — 939's own report
    field carries "**News analyst**" — so the same string-literal tracking the
    brace scanner uses decides what is safe to remove.
    """
    out: list[str] = []
    in_str = False
    escaped = False
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if in_str:
            out.append(ch)
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_str = False
            i += 1
            continue
        if ch == '"':
            in_str = True
            out.append(ch)
        elif text.startswith("**", i):
            i += 2
            continue
        else:
            out.append(ch)
        i += 1
    return "".join(out)


def _json_objects(text: str) -> list[dict[str, Any]]:
    """Every top-level JSON object in `text`, in order.

    A single greedy `\\{.*\\}` breaks whenever the model answers with more than
    one object (e.g. the decision fields and the report emitted separately):
    the match spans both, json.loads raises, and the caller falls back to
    dumping the raw text into the report. Scanning brace depth — while
    respecting string literals — parses each object on its own instead."""
    text = _strip_markdown_emphasis(text)
    out: list[dict[str, Any]] = []
    depth = 0
    start = -1
    in_str = False
    escaped = False
    for i, ch in enumerate(text):
        if in_str:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth == 0:
                continue
            depth -= 1
            if depth == 0:
                try:
                    obj = json.loads(text[start:i + 1])
                except Exception:  # noqa: BLE001
                    continue
                if isinstance(obj, dict):
                    out.append(obj)
    # Salvage a TRUNCATED trailing object (2026-07-27). A response cut off by
    # the token limit leaves an object that never closes, `out` stays empty,
    # and the caller silently substitutes a rule-based decision for the AI's —
    # observed on 3 of 6 live full-path cycles, with the AI's own stop/target
    # sitting unused in the report field. The complete leading key/value pairs
    # are still perfectly good; only the final partial one is lost.
    if not out and start >= 0 and depth > 0:
        repaired = _repair_truncated_object(text[start:])
        if repaired is not None:
            out.append(repaired)
    return out


def _repair_truncated_object(fragment: str) -> Optional[dict[str, Any]]:
    """Best-effort parse of an unterminated JSON object.

    Trims back to the last complete `"key": value,` pair and closes the brace.
    Returns None when nothing complete survives — never guesses at a value.

    A salvaged object must carry BOTH action and confidence. `confidence`
    defaults to 0.5 downstream, so recovering an action without one would
    manufacture a midpoint the model never expressed and feed it to the gates.
    A fragment that short is not a damaged decision, it is no decision — the
    caller's rule fallback is the honest answer there."""
    for cut in range(len(fragment) - 1, 0, -1):
        if fragment[cut] != ",":
            continue
        try:
            obj = json.loads(fragment[:cut] + "}")
        except Exception:  # noqa: BLE001
            continue
        if isinstance(obj, dict) and "action" in obj and "confidence" in obj:
            obj["_truncated"] = True
            return obj
    return None


def _merged_json_object(text: str) -> Optional[dict[str, Any]]:
    """One dict from every JSON object in `text`, so an answer split across
    objects ({"action":...} then {"report":...}) still reads as one payload.
    Earlier keys win; later objects only fill in what is missing."""
    merged: dict[str, Any] = {}
    for part in _json_objects(text):
        for key, value in part.items():
            merged.setdefault(key, value)
    return merged or None


def _parse_decision_json(text: str) -> Optional[dict[str, Any]]:
    if not text:
        return None
    obj = _merged_json_object(text)
    if obj is None:
        return None
    action = str(obj.get("action", "")).lower()
    if action not in VALID_ACTIONS:
        return None
    try:
        conf = float(obj.get("confidence", 0.5))
    except Exception:  # noqa: BLE001
        conf = 0.5
    obj["action"] = action
    obj["confidence"] = max(0.0, min(1.0, conf))
    return obj


def _guidelines_block(guidelines: Optional[str]) -> str:
    """User guidelines injected into decision-tier prompts (Plan 06 C3).
    They may make the AI more conservative; they cannot loosen anything —
    the deterministic risk gates run downstream regardless."""
    if not guidelines:
        return ""
    return ("USER GUIDELINES (follow them where they make you MORE cautious; "
            "they can never override risk limits or execution gates):\n"
            f"{guidelines}\n\n")


def _skills_block(site: str, market: Optional[str] = None) -> str:
    """Trading skills (Plan 20) for one prompt site. Fail-soft to "" — a
    skills-registry problem must never break an analysis."""
    try:
        from trading_skills import skills_block
        return skills_block(site, market=market)
    except Exception:  # noqa: BLE001
        return ""


def ai_only_orders() -> bool:
    """PRIMARY RULE: an order is decided by the AI, or it is not placed.

    The order space is far too large to encode — size × leverage × stop ×
    target × trail × horizon × adds runs to ~10^11 configurations for a single
    symbol in a single regime — so a rule engine can never stand in for the
    desk's judgement on WHETHER and WHICH WAY to trade. It may still manage
    risk on a position that already exists (stops, liquidation cushions, the
    SL/TP watcher); those reduce exposure and are deliberately deterministic.

    What it must never do is ORIGINATE a position. Set false only to restore
    the pre-2026-07-27 behaviour, where an unreadable AI answer silently became
    a rule-authored buy or sell at up to 0.9 confidence."""
    return os.getenv("RUN_AI_ONLY_ORDERS", "true").strip().lower() in (
        "1", "true", "yes", "on")


def _hold_only(decision: dict[str, Any], reason: str) -> dict[str, Any]:
    """Strip a rule-authored decision down to HOLD, preserving its reasoning.

    Not a rejection of the analysis — the technical read stays in the report so
    the operator can see what the rule engine thought. It simply may not become
    an order."""
    if not ai_only_orders() or decision.get("action") == "hold":
        return decision
    out = dict(decision)
    out["rule_action_suppressed"] = out.get("action")
    out["action"] = "hold"
    out["confidence"] = 0.0
    out["ai_only_reason"] = reason
    return out


def _trader_risk_decision(symbol, market, briefs, technical, news, lang,
                          guidelines: Optional[str] = None,
                          memory: str = "",
                          position_state: str = "",
                          skills: str = "",
                          can_sell: bool = True) -> dict[str, Any]:
    if not llm_configured():
        # No provider at all. The engine still runs and still reports, but it
        # does not trade on a rule signal — see ai_only_orders().
        out = _rule_based_decision(technical, news)
        out["decided_by"] = "rule"
        out["fallback_reason"] = "no llm provider configured"
        return _hold_only(out, "no llm provider configured")
    lang_line = f"Write the rationale and report in {LANG_NAMES[normalize_lang(lang)]}."
    prompt = (
        "You are the Trader + Risk Management team. Debate the four analyst briefs below and "
        f"decide whether to BUY, SELL, or HOLD {symbol} ({market}).\n"
        f"{lang_line}\n"
        + memory
        + _guidelines_block(guidelines)
        + skills
        # Position awareness (2026-07-29). This path took no position input of
        # any kind — not size, entry, P&L, high-water mark, nor even whether a
        # position existed. That is worst exactly here: the E1 router escalates
        # to this expensive path FOR position reasons ("Open position near loss
        # warrants judgement check", prod run 811 cycle 55), so the desk was
        # promoted to judge a holding and handed nothing about it. The light
        # path got this in #124; the escalated cycles are the ones that need it
        # most.
        + position_state +
        "Weigh disagreement, size risk, and be decisive. Respond with ONLY a JSON object:\n"
        # 'entry' is asked for as the desk's VIEW and is recorded as
        # suggested_entry; execution always fills at the live price (P-1).
        # Saying so keeps the model from treating it as an order instruction.
        # A flat spot book cannot sell. Offering the verb anyway cost 33
        # decisions across 16 runs (2026-07-27..08-03) to "spot sell with no
        # inventory — treated as hold", run 939's confidence-0.62 read among
        # them. The light path gates the same way.
        + ('{"action":"buy|sell|hold","confidence":0.0-1.0,' if can_sell
           else '{"action":"buy|hold","confidence":0.0-1.0,')
        +
        # Component scores (2026-07-27). The LIGHT path already returns these
        # and the full path did not, so conviction came back None on every
        # expensive cycle — the cheap path had richer sizing input than the
        # one that costs six LLM calls. Same four keys, same weights.
        '"scores":{"thesis_alignment":0.0-1.0,"momentum_quality":0.0-1.0,'
        '"entry_quality":0.0-1.0,"risk_context":0.0-1.0},'
        '"entry":number|null (your suggested level — commentary only; the fill '
        'is executed at the live market price regardless),'
        '"target":number|null,"stop":number|null,"rationale":"1-2 sentences",'
        '"report":"a 4-6 sentence markdown report synthesizing the analysts",'
        # The order block: the desk sizes its own trade. Every field is
        # RELATIVE — no absolute prices, no dollar amounts — so a wrong number
        # is bounded by the rails instead of becoming a fabricated order. All
        # fields optional; "defer" hands the trade back to the fixed defaults,
        # which is the right answer whenever the situation is unremarkable.
        '"order":{"defer":true|false,'
        '"size_frac":0.05-1.0 (fraction of the max bet),'
        '"leverage":number,'
        '"stop_pct":number (%% from entry — size it to THIS instrument\'s '
        'volatility, not a house default),'
        '"target_pct":number (%% from entry — must be at least 2x stop_pct),'
        '"trail_arm_pct":number (%% profit before the trailing lock arms),'
        '"trail_give":0.05-0.40 (fraction of peak profit you will surrender),'
        '"horizon_hours":number,"max_adds":0-3,'
        '"why":"one sentence tying these numbers to the evidence above"},'
        # Plan 17 (2026-07-30): the Order Intent. Both decision paths get it —
        # the E1 router escalates HERE for position reasons, and PR #125
        # already had to fix a one-path-only blind spot once.
        '"order_intent":{"intent":"open|add|reduce|close|flip|hold|arm",'
        '"size_frac":0.0-1.0 (open/add: fraction of the max bet; reduce/close: '
        'fraction of WHAT YOU HOLD — 0.5 means half your position),'
        '"arm":{"if":"price_below|price_above","level":number,'
        '"then":"reduce|close","size_frac":0.0-1.0}|null,'
        '"why":"one sentence"}}\n\n'
        "For the intent: banking is a first-class action, not merely the "
        "absence of an add. flip means you were wrong — reverse. Prefer arm "
        "over hold whenever you can name the level that would change your "
        "mind: it acts at machine latency instead of waiting for your next "
        "cycle, and the platform will never second-guess a reduction.\n\n"
        "For the order block: set defer=true unless the analysts give you a "
        "concrete reason to depart from a house default. When you do set the "
        "numbers, anchor the stop to measured volatility (ATR/sigma) and a "
        "structural level, and the target to a real level the move can reach "
        "— not to a round number.\n\n"
        f"NEWS ANALYST:\n{briefs['news']}\n\n"
        f"SENTIMENT ANALYST:\n{briefs['sentiment']}\n\n"
        f"FUNDAMENTALS/MACRO ANALYST:\n{briefs['fundamentals_macro']}\n\n"
        f"TECHNICAL ANALYST:\n{briefs['technical']}\n\n"
        f"Current price: {technical.get('current_price')}\n"
    )
    # 900 was not enough once the order block joined action/confidence/entry/
    # target/stop/rationale/report in one payload: the JSON was cut mid-object
    # on half of the observed live cycles, and an unparseable answer silently
    # became a RULE decision (see the fallback below). Budget the completion
    # for what we actually ask for.
    text = generate_text(prompt, max_tokens=_trader_max_tokens(), temperature=0.3)
    parsed = _parse_decision_json(text or "")
    if parsed:
        parsed["decided_by"] = "ai"
        # P-1: the model does NOT author the execution price.
        #
        # Every risk limit is denominated in price — automation sizes with
        # `size_usd / entry` and the gate checks `quantity * price` — so both
        # sides use the same number and always reconcile to exactly size_usd.
        # Let the model set it and it sets the denominator of the entire risk
        # stack: an entry of 60 instead of 60,000 opens 1000x the position
        # while every cap still reports ALLOWED. No malice needed; LLMs slip
        # units routinely. (Audit 2026-07-17, 4/4 QA confirmed.)
        #
        # So its price is commentary, kept for the report, and execution always
        # uses the live one.
        suggested = parsed.get("entry")
        parsed["suggested_entry"] = suggested if isinstance(suggested, (int, float)) else None
        parsed["entry"] = technical.get("current_price")
        if not parsed.get("report"):
            parsed["report"] = parsed.get("rationale", "")
        return parsed
    # LLM answered but unparseable -> keep its prose as the report, decide by
    # rule. Stamped `decided_by='rule'` (2026-07-27): this path silently
    # replaces the desk's verdict with the rule engine's, and until it was
    # labelled the journal showed the two as identical — a rule decision was
    # indistinguishable from an AI one, including a confidence the AI never
    # produced (0.6 journaled against 0.55 in its own report text).
    fallback = _rule_based_decision(technical, news)
    fallback["decided_by"] = "rule"
    reason = "decision json unparseable" if text else "no llm response"
    fallback["fallback_reason"] = reason
    if text:
        fallback["report"] = text.strip()[:2000]
    # PRIMARY RULE (2026-07-27): the rule engine may not originate a position.
    # Before this, an unreadable AI answer became a rule-authored buy/sell at
    # up to 0.9 confidence, journaled as though the desk had decided it — 3 of
    # 6 observed live full-path cycles. Holding is the honest answer when the
    # desk could not be read.
    return _hold_only(fallback, reason)


def _trader_max_tokens() -> int:
    """Completion budget for the trader verdict. Must cover the whole JSON —
    a cut-off object is not a smaller answer, it is a lost one."""
    try:
        return max(400, int(os.getenv("RUN_TRADER_MAX_TOKENS", "1500")))
    except ValueError:
        return 1500


# ─────────────────────────── verification pass ───────────────────────────

VERIFY_VERDICTS = ("upheld", "weakened", "rejected")


def _verify_mode() -> str:
    """off | advisory | enforce — read at call time so tests/env can flip it."""
    import os
    mode = os.getenv("VERIFY_ENABLED", "advisory").strip().lower()
    return mode if mode in ("off", "advisory", "enforce") else "advisory"


def _parse_verification_json(text: str) -> Optional[dict[str, Any]]:
    if not text:
        return None
    obj = _merged_json_object(text)
    if obj is None:
        return None
    verdict = str(obj.get("verdict", "")).lower()
    if verdict not in VERIFY_VERDICTS:
        return None
    try:
        adj = float(obj.get("adjusted_confidence", 0.5))
    except Exception:  # noqa: BLE001
        adj = 0.5
    return {"verdict": verdict,
            "adjusted_confidence": max(0.0, min(1.0, adj)),
            "reason": str(obj.get("reason") or "")[:500]}


def _verify_decision(symbol: str, market: str, briefs: dict[str, str],
                     technical: dict[str, Any], decision: dict[str, Any],
                     lang: str, guidelines: Optional[str] = None,
                     memory: str = "",
                     skills: str = "") -> Optional[dict[str, Any]]:
    """Adversarial second pass: a strong-tier call that tries to REFUTE the
    trader's decision. Returns {verdict, adjusted_confidence, reason} or None
    (fail-open) when unconfigured/unparseable. VERIFY_PROVIDER optionally runs
    the verifier on a different provider for cross-model agreement."""
    if _verify_mode() == "off" or not llm_configured():
        return None
    import os
    prompt = (
        memory +
        _guidelines_block(guidelines) +
        skills +
        "You are an independent risk verifier. Your job is to try to REFUTE the trading "
        f"decision below for {symbol} ({market}). Check: (1) do the analyst briefs actually "
        "support the action, or is evidence mixed/contradictory? (2) is the confidence "
        "consistent with the disagreement between analysts? (3) any veto conditions "
        "(macro event risk, psychology-only signal, stale/absent data)?\n"
        "Respond with ONLY a JSON object:\n"
        '{"verdict":"upheld|weakened|rejected","adjusted_confidence":0.0-1.0,'
        '"reason":"1-2 sentences"}\n'
        "Use 'rejected' when the evidence does not support the action; 'weakened' when the "
        "action is defensible but the confidence is too high; 'upheld' otherwise.\n\n"
        f"PROPOSED DECISION: {json.dumps({k: decision.get(k) for k in ('action', 'confidence', 'rationale')}, ensure_ascii=False)}\n\n"
        f"NEWS ANALYST:\n{briefs['news']}\n\n"
        f"SENTIMENT ANALYST:\n{briefs['sentiment']}\n\n"
        f"FUNDAMENTALS/MACRO ANALYST:\n{briefs['fundamentals_macro']}\n\n"
        f"TECHNICAL ANALYST:\n{briefs['technical']}\n\n"
        f"Current price: {technical.get('current_price')}\n"
    )
    verify_provider = os.getenv("VERIFY_PROVIDER", "").strip().lower() or None
    token = None
    if verify_provider:
        # Override ONLY the provider — cross-model disagreement is the point of
        # an independent verifier, so the user's model must not be reused here.
        # Everything identifying WHO this call belongs to is carried over from
        # the surrounding context: building a bare LlmContext instead dropped
        # user_id/agent_id, and the verify call's llm_usage row then landed with
        # user_id NULL — invisible in that user's spend, silently absorbed into
        # the system total.
        from llm_client import LlmContext, current_llm_context, set_llm_context
        outer = current_llm_context()
        token = set_llm_context(LlmContext(
            provider=verify_provider, source="rule",
            user_id=outer.user_id if outer else None,
            agent_id=outer.agent_id if outer else None))
    try:
        text = generate_text(prompt, max_tokens=300, temperature=0.2, tier="decision")
    finally:
        if token is not None:
            from llm_client import reset_llm_context
            reset_llm_context(token)
    return _parse_verification_json(text or "")


def _apply_verification(decision: dict[str, Any],
                        verification: Optional[dict[str, Any]]) -> dict[str, Any]:
    """Deterministic application of the verifier's verdict (enforce mode only):
    rejected -> hold; weakened -> confidence = min(trader, adjusted); upheld -> unchanged.
    Advisory mode attaches the verdict without changing the decision. Fail-open."""
    mode = _verify_mode()
    block = None
    if verification is not None:
        block = dict(verification)
        block["mode"] = mode
        block["applied"] = False
        if mode == "enforce":
            if verification["verdict"] == "rejected":
                decision = dict(decision)
                decision["action"] = "hold"
                decision["confidence"] = min(float(decision.get("confidence") or 0.5),
                                             verification["adjusted_confidence"])
                block["applied"] = True
            elif verification["verdict"] == "weakened":
                decision = dict(decision)
                decision["confidence"] = min(float(decision.get("confidence") or 0.5),
                                             verification["adjusted_confidence"])
                block["applied"] = True
    if block is not None:
        decision = dict(decision)
        decision["verification"] = block
    return decision


# ─────────────────────────── orchestration ───────────────────────────

def run_analysis(symbol: str, market: str = "us-stock", lang: str = "en",
                 provider: Optional[str] = None,
                 agent_id: Optional[int] = None,
                 progress: Optional[ProgressFn] = None,
                 llm_tiers: Optional[dict] = None,
                 position_state: str = "",
                 can_sell: bool = True) -> dict[str, Any]:
    """Run the full multi-agent pipeline for one symbol and return decision + report.

    provider optionally forces a specific LLM provider for this run (automation
    rules). agent_id resolves the owning user's stored LLM settings (provider,
    model, API key) so a user's Settings-page choice actually powers their runs.
    A rule provider that differs from the user's configured provider wins for
    provider choice but cannot use the user's key."""
    symbol = (symbol or "").strip().upper()
    market = (market or "us-stock").strip().lower()
    if not symbol:
        raise ValueError("symbol is required")

    from llm_client import LlmContext, reset_llm_context, set_llm_context
    rule_provider = (provider or "").strip().lower() or None
    user_ctx = None
    try:
        from services import llm_context_for_agent
        user_ctx = llm_context_for_agent(agent_id)
    except Exception:  # noqa: BLE001 — settings lookup must never break analysis
        user_ctx = None

    # Metering identity (Plan 11 F2): every branch carries user/agent ids so
    # llm_usage rows attribute to the run's owner even without user settings.
    owner_user_id = user_ctx.user_id if user_ctx else None
    if owner_user_id is None and agent_id:
        try:
            from services import user_id_for_agent
            owner_user_id = user_id_for_agent(agent_id)
        except Exception:  # noqa: BLE001
            owner_user_id = None

    ctx: Optional[LlmContext] = None
    if user_ctx and rule_provider and user_ctx.provider and rule_provider != user_ctx.provider:
        ctx = LlmContext(provider=rule_provider, source="rule",
                         user_id=owner_user_id, agent_id=agent_id)
    elif user_ctx:
        ctx = LlmContext(provider=rule_provider or user_ctx.provider,
                         model=user_ctx.model, api_key=user_ctx.api_key, source="user",
                         user_id=owner_user_id, agent_id=agent_id)
    elif rule_provider:
        ctx = LlmContext(provider=rule_provider, source="rule",
                         user_id=owner_user_id, agent_id=agent_id)
    elif agent_id:
        ctx = LlmContext(source="rule", user_id=owner_user_id, agent_id=agent_id)

    # Per-tier routing (cost A/B): rides on whatever context the branches above
    # chose so metering identity and key selection are unchanged.
    if llm_tiers:
        from dataclasses import replace
        ctx = (replace(ctx, tier_providers=llm_tiers) if ctx is not None
               else LlmContext(source="rule", user_id=owner_user_id,
                               agent_id=agent_id, tier_providers=llm_tiers))

    guidelines = None
    try:
        from services import guidelines_for_agent
        guidelines = guidelines_for_agent(agent_id)
    except Exception:  # noqa: BLE001
        guidelines = None

    token = set_llm_context(ctx) if ctx is not None else None
    try:
        return _run_analysis_inner(symbol, market, lang, guidelines=guidelines,
                                   progress=progress, agent_id=agent_id,
                                   position_state=position_state,
                                   can_sell=can_sell)
    finally:
        if token is not None:
            reset_llm_context(token)


def _timed_step(progress: Optional[ProgressFn], step: str, fn, *args):
    """Run one pipeline step, emitting start/done (or error) around it."""
    _emit(progress, step, "start")
    try:
        out = fn(*args)
    except Exception as exc:  # noqa: BLE001
        _emit(progress, step, "error", detail=str(exc)[:200])
        raise
    _emit(progress, step, "done")
    return out


def _submit_step(pool: ThreadPoolExecutor, progress: Optional[ProgressFn],
                 step: str, fn, *args):
    """Submit a step to the pool with a copy of the current context, so the
    per-run LLM context (user provider/model/key) survives the thread hop."""
    ctx = contextvars.copy_context()
    return pool.submit(ctx.run, _timed_step, progress, step, fn, *args)


def _run_analysis_inner(symbol: str, market: str, lang: str,
                        guidelines: Optional[str] = None,
                        progress: Optional[ProgressFn] = None,
                        agent_id: Optional[int] = None,
                        position_state: str = "",
                        can_sell: bool = True) -> dict[str, Any]:
    # Data gathering: technical / news / fundamentals are independent and run
    # concurrently; sentiment needs the news breakdown so it starts after news.
    with ThreadPoolExecutor(max_workers=4) as pool:
        f_technical = _submit_step(pool, progress, "gather:technical",
                                   _gather_technical, symbol, market)
        f_news = _submit_step(pool, progress, "gather:news",
                              _gather_news, symbol, market)
        f_fundamentals = _submit_step(pool, progress, "gather:fundamentals_macro",
                                      _gather_fundamentals_macro, symbol, market)
        news = f_news.result()
        f_sentiment = _submit_step(pool, progress, "gather:sentiment",
                                   _gather_sentiment, symbol, market, news)
        technical = f_technical.result()
        fundamentals = f_fundamentals.result()
        sentiment = f_sentiment.result()

    # Analyst briefs: four independent LLM calls, run concurrently.
    brief_specs = {
        "news": ("News Analyst",
                 "Summarize what today's news implies for this asset (company, global, macro, government).",
                 news),
        "sentiment": ("Sentiment Analyst",
                      "Judge crowd/social sentiment and whether it is a tailwind or a contrarian warning.",
                      sentiment),
        "fundamentals_macro": ("Fundamentals & Macro Analyst",
                               "Read the macro regime and prediction-market odds; is the backdrop supportive?",
                               fundamentals),
        "technical": ("Technical Analyst",
                      "Read trend, momentum, and key support/resistance; what is price telling us?",
                      technical),
    }
    with ThreadPoolExecutor(max_workers=4) as pool:
        brief_futures = {
            role: _submit_step(pool, progress, f"brief:{role}",
                               _brief, title, instructions, data, lang)
            for role, (title, instructions, data) in brief_specs.items()
        }
        briefs = {role: f.result() for role, f in brief_futures.items()}

    # Desk memory (Plan 11 F4): durable lessons from this agent's earlier
    # analyses, injected next to the user guidelines. Fail-soft to "".
    _emit(progress, "memory:recall", "start")
    try:
        from analysis_memory import memory_block
        memory = memory_block(agent_id, symbol)
    except Exception:  # noqa: BLE001
        memory = ""
    _emit(progress, "memory:recall", "done", found=bool(memory))

    _emit(progress, "decision", "start")
    decision = _trader_risk_decision(symbol, market, briefs, technical, news, lang,
                                     guidelines=guidelines, memory=memory,
                                     position_state=position_state,
                                     skills=_skills_block("trader", market),
                                     can_sell=can_sell)
    _emit(progress, "decision", "done",
          action=decision.get("action"), confidence=decision.get("confidence"))

    # Verification pass (advisory by default; enforce applies deterministically).
    # Fail-open: verifier trouble never blocks the pipeline.
    _emit(progress, "verify", "start")
    try:
        verification = _verify_decision(symbol, market, briefs, technical, decision, lang,
                                        guidelines=guidelines, memory=memory,
                                        skills=_skills_block("verifier", market))
    except Exception:  # noqa: BLE001
        verification = None
    decision = _apply_verification(decision, verification)
    _emit(progress, "verify", "done",
          verdict=(verification or {}).get("verdict") or "skipped")

    # Write back what this run taught the desk. Fail-soft and non-blocking to
    # the result: a memory-write problem must not fail an analysis.
    _emit(progress, "memory:write", "start")
    try:
        from analysis_memory import remember_analysis
        remember_analysis(agent_id, symbol, market, briefs, decision)
        _emit(progress, "memory:write", "done", saved=True)
    except Exception:  # noqa: BLE001
        # Fail-soft: a memory-write problem must not fail (or redden) the run.
        _emit(progress, "memory:write", "done", saved=False)

    return {
        "symbol": symbol,
        "market": market,
        "as_of": _now_iso(),
        "llm_provider": _provider_label(),
        "llm_provider_source": _provider_source_label(),
        "llm_model": _provider_model_label(),
        "analysts": {
            "news": {"brief": briefs["news"], "data": news},
            "sentiment": {"brief": briefs["sentiment"], "data": sentiment},
            "fundamentals_macro": {"brief": briefs["fundamentals_macro"], "data": fundamentals},
            "technical": {"brief": briefs["technical"], "data": technical},
        },
        "decision": decision,
    }


def _provider_label() -> Optional[str]:
    try:
        from llm_client import active_provider_name
        return active_provider_name()
    except Exception:  # noqa: BLE001
        return None


def _provider_source_label() -> Optional[str]:
    try:
        from llm_client import active_provider_source
        return active_provider_source()
    except Exception:  # noqa: BLE001
        return None


def _provider_model_label() -> Optional[str]:
    try:
        from llm_client import active_provider_model
        return active_provider_model(tier="decision")
    except Exception:  # noqa: BLE001
        return None
