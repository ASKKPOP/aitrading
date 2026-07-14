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

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional

from llm_client import generate_text, llm_configured

logger = logging.getLogger(__name__)

VALID_ACTIONS = ("buy", "sell", "hold")


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
    # crypto / polymarket: light technical from the live price
    try:
        from price_fetcher import get_price_from_market
        price = get_price_from_market(symbol, _now_iso(), market)
        return {"symbol": symbol, "market": market, "current_price": price,
                "note": "light technical (spot price only) for non-equity market"}
    except Exception as exc:  # noqa: BLE001
        return {"symbol": symbol, "market": market, "error": str(exc)}


def _gather_news(symbol: str, market: str) -> dict[str, Any]:
    out: dict[str, Any] = {"items": [], "sentiment_breakdown": {}}
    try:
        from market_intel import get_market_news_payload
        payload = get_market_news_payload(limit=6)
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


def _gather_sentiment(symbol: str, market: str, news: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {"from_news": news.get("sentiment_breakdown", {})}
    try:
        from analysis_sources import fetch_stocktwits_sentiment
        st = fetch_stocktwits_sentiment(symbol)
        if st:
            out["stocktwits"] = st
    except Exception:  # noqa: BLE001
        pass
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


# ─────────────────────────── analyst briefs ───────────────────────────

def _brief(role: str, instructions: str, data: dict[str, Any], lang: str) -> str:
    """Ask the LLM for a short brief; fall back to a compact data dump."""
    if not llm_configured():
        return _fallback_brief(role, data)
    lang_line = "Write in Thai." if lang == "th" else "Write in English."
    prompt = (
        f"You are the {role} on a trading desk. {instructions}\n"
        f"{lang_line} Be concrete and under 90 words. No disclaimers, no bullet lists.\n\n"
        f"Data (JSON):\n{json.dumps(data, ensure_ascii=False, default=str)[:6000]}\n"
    )
    text = generate_text(prompt, max_tokens=220, temperature=0.4)
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
        msg = f"{len(items)} headlines scanned — tone {tone} ({bull} bullish vs {bear} bearish)."
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
        confidence = max(0.3, min(0.9, 0.5 + score / 20.0))
    rationale = (
        f"Technical signal is '{signal}'"
        + (f" (score {score})" if score is not None else "")
        + f"; news sentiment {bull} bullish vs {bear} bearish."
    )
    return {"action": action, "confidence": round(confidence, 2), "entry": technical.get("current_price"),
            "target": None, "stop": None, "rationale": rationale, "report": rationale}


def _parse_decision_json(text: str) -> Optional[dict[str, Any]]:
    if not text:
        return None
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        obj = json.loads(match.group(0))
    except Exception:  # noqa: BLE001
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


def _trader_risk_decision(symbol, market, briefs, technical, news, lang) -> dict[str, Any]:
    if not llm_configured():
        return _rule_based_decision(technical, news)
    lang_line = "Write the rationale and report in Thai." if lang == "th" else "Write the rationale and report in English."
    prompt = (
        "You are the Trader + Risk Management team. Debate the four analyst briefs below and "
        f"decide whether to BUY, SELL, or HOLD {symbol} ({market}).\n"
        f"{lang_line}\n"
        "Weigh disagreement, size risk, and be decisive. Respond with ONLY a JSON object:\n"
        '{"action":"buy|sell|hold","confidence":0.0-1.0,"entry":number|null,'
        '"target":number|null,"stop":number|null,"rationale":"1-2 sentences",'
        '"report":"a 4-6 sentence markdown report synthesizing the analysts"}\n\n'
        f"NEWS ANALYST:\n{briefs['news']}\n\n"
        f"SENTIMENT ANALYST:\n{briefs['sentiment']}\n\n"
        f"FUNDAMENTALS/MACRO ANALYST:\n{briefs['fundamentals_macro']}\n\n"
        f"TECHNICAL ANALYST:\n{briefs['technical']}\n\n"
        f"Current price: {technical.get('current_price')}\n"
    )
    text = generate_text(prompt, max_tokens=900, temperature=0.3)
    parsed = _parse_decision_json(text or "")
    if parsed:
        # LLMs sometimes return entry: null — fall back to the live price so
        # downstream execution always has a valid entry.
        if not parsed.get("entry"):
            parsed["entry"] = technical.get("current_price")
        if not parsed.get("report"):
            parsed["report"] = parsed.get("rationale", "")
        return parsed
    # LLM answered but unparseable -> keep its prose as the report, decide by rule
    fallback = _rule_based_decision(technical, news)
    if text:
        fallback["report"] = text.strip()[:2000]
    return fallback


# ─────────────────────────── orchestration ───────────────────────────

def run_analysis(symbol: str, market: str = "us-stock", lang: str = "en",
                 provider: Optional[str] = None) -> dict[str, Any]:
    """Run the full multi-agent pipeline for one symbol and return decision + report.

    provider optionally forces a specific LLM provider for this run (used by
    automation rules); None keeps the server-configured default."""
    symbol = (symbol or "").strip().upper()
    market = (market or "us-stock").strip().lower()
    if not symbol:
        raise ValueError("symbol is required")

    override_token = None
    if provider:
        from llm_client import set_provider_override
        override_token = set_provider_override(provider)
    try:
        return _run_analysis_inner(symbol, market, lang)
    finally:
        if override_token is not None:
            from llm_client import reset_provider_override
            reset_provider_override(override_token)


def _run_analysis_inner(symbol: str, market: str, lang: str) -> dict[str, Any]:
    technical = _gather_technical(symbol, market)
    news = _gather_news(symbol, market)
    sentiment = _gather_sentiment(symbol, market, news)
    fundamentals = _gather_fundamentals_macro(symbol, market)

    briefs = {
        "news": _brief("News Analyst",
                       "Summarize what today's news implies for this asset (company, global, macro, government).",
                       news, lang),
        "sentiment": _brief("Sentiment Analyst",
                            "Judge crowd/social sentiment and whether it is a tailwind or a contrarian warning.",
                            sentiment, lang),
        "fundamentals_macro": _brief("Fundamentals & Macro Analyst",
                                     "Read the macro regime and prediction-market odds; is the backdrop supportive?",
                                     fundamentals, lang),
        "technical": _brief("Technical Analyst",
                           "Read trend, momentum, and key support/resistance; what is price telling us?",
                           technical, lang),
    }

    decision = _trader_risk_decision(symbol, market, briefs, technical, news, lang)

    return {
        "symbol": symbol,
        "market": market,
        "as_of": _now_iso(),
        "llm_provider": _provider_label(),
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
