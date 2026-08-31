"""swing_pipeline.py — the live wiring of the swing signal stack.

swing_stack.py implements research/SWING_SIGNAL_STACK.md as a pure engine
(five processors -> composite -> two-axis rule -> decision -> risk gate) and
has had **no caller** since it shipped: nothing collected the inputs. This
module is that caller.

    COLLECT                          SCORE                       COMBINE/DECIDE
    price & volume  (candles)  ->    technical    w=.20  ─┐
    social + news   (F&G)      ->    sentiment    w=.25  ─┤
    macro calendar/regime      ->    macro        w=.20  ─┼─> composite -> BUY
    earnings & catalysts       ->    thesis       w=.20  ─┤    (-100..100)  WAIT
    filings (Form 4)           ->    smart_money  w=.15  ─┘                 SELL
                                                              risk gate (veto)

Coverage discipline, inherited from swing_stack: a feed with no data scores
**None** and its weight renormalizes away; 0 would assert "genuinely neutral",
which an outage has not measured. A symbol with no coverage WAITs.

The risk gate's binary event is whichever comes first — the symbol's next
earnings print or the next high-impact macro release.

Every pass writes crawl_runs rows (crawl_monitor) so the admin console shows
what the crawlers did, and one swing_decisions row per symbol so a decision
can be read back and reviewed later.

Env-gated: SWING_PIPELINE_ENABLED (default off), SWING_PIPELINE_SYMBOLS,
SWING_PIPELINE_MARKET, SWING_PIPELINE_INTERVAL_S.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

import requests

import catalyst_feed
import crawl_monitor
import database
import filings_feed
import market_events
import psych_feed
import swing_stack

logger = logging.getLogger(__name__)

_YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
_OKX_CANDLES = "https://www.okx.com/api/v5/market/candles"
_FF_CALENDAR = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
_TIMEOUT_S = 12.0
_UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

CRYPTO_MARKETS = ("crypto",)
STOCK_BENCHMARK = "%5EGSPC"   # ^GSPC
CRYPTO_BENCHMARK = "BTC-USDT-SWAP"

# Feed keys recorded in crawl_runs — the diagram's COLLECT nodes.
FEED_PRICE = "price_volume"
FEED_MACRO = "macro_regime"
FEED_GAUGE = "sentiment_gauge"
FEED_CATALYST = "earnings_catalysts"
FEED_FILINGS = "filings"
FEED_CALENDAR = "macro_calendar"
FEED_SOCIAL = "social_crawl"
FEED_NEWS = "news"
FEED_PIPELINE = "pipeline"

PROCESSORS = ("sentiment", "macro", "thesis", "smart_money", "technical")

# The pipeline as the admin console draws it. `wired` is the honest bit: a
# collector can be running and healthy while feeding NOTHING into a score.
# social_crawl and news are in that state today — social_feed.py and
# market_intel.py collect them for other consumers, but the sentiment
# processor is driven by the Fear & Greed gauge (the doc's §4 psychology
# mapping, recalibrated by the 2026-08-30 mid-band experiment). Painting them
# as feeding the score would be a drawing, not the system.
COLLECT_NODES: tuple[dict[str, Any], ...] = (
    {"key": FEED_SOCIAL, "doc_feed": 1, "label": "Social crawl",
     "feeds": "sentiment", "wired": False,
     "note": "collected by social_feed.py; not an input to the sentiment score yet"},
    {"key": FEED_NEWS, "doc_feed": 2, "label": "News feeds",
     "feeds": "sentiment", "wired": False,
     "note": "collected by market_intel.py; not an input to the sentiment score yet"},
    {"key": FEED_GAUGE, "doc_feed": 1, "label": "Crowd gauge (F&G)",
     "feeds": "sentiment", "wired": True,
     "note": "CNN F&G for stocks, alternative.me for crypto"},
    {"key": FEED_MACRO, "doc_feed": 3, "label": "Macro regime (VIX/10Y/DXY)",
     "feeds": "macro", "wired": True, "note": None},
    {"key": FEED_CALENDAR, "doc_feed": 3, "label": "Macro calendar",
     "feeds": "risk_gate", "wired": True,
     "note": "high-impact USD releases -> event blackout"},
    {"key": FEED_CATALYST, "doc_feed": 4, "label": "Earnings & catalysts",
     "feeds": "thesis", "wired": True, "note": None},
    {"key": FEED_FILINGS, "doc_feed": 5, "label": "Filings (Form 4)",
     "feeds": "smart_money", "wired": True,
     "note": "open-market P/S only; 13F is out of scope in v1"},
    {"key": FEED_PRICE, "doc_feed": 6, "label": "Price & volume",
     "feeds": "technical", "wired": True, "note": None},
)

_BLEND_NOTES = {
    "off": "collected; not an input to the sentiment score",
    "shadow": "shadow only — the blended value is recorded beside each decision "
              "for comparison, and is NOT used to decide",
    "live": "blended into the per-symbol sentiment score",
}


def collect_nodes() -> tuple[dict[str, Any], ...]:
    """COLLECT_NODES with the sentiment feeds' wiring resolved for the current
    blend mode. `wired` means "affects decisions" — shadow does not, and must
    not be reported as if it did."""
    mode = sentiment_blend_mode()
    resolved: list[dict[str, Any]] = []
    for node in COLLECT_NODES:
        entry = dict(node)
        if entry["key"] in (FEED_SOCIAL, FEED_NEWS):
            entry["wired"] = mode == "live"
            entry["note"] = _BLEND_NOTES[mode]
            entry["blend_mode"] = mode
        resolved.append(entry)
    return tuple(resolved)


PROCESSOR_NODES: tuple[dict[str, Any], ...] = tuple(
    {"key": name, "weight": swing_stack.WEIGHTS[name],
     "axis": "qualitative" if name in swing_stack.QUAL_FEEDS
             else ("quantitative" if name == "technical" else "tide")}
    for name in PROCESSORS
)


def enabled() -> bool:
    return os.environ.get("SWING_PIPELINE_ENABLED", "false").strip().lower() in {
        "1", "true", "yes", "on",
    }


def configured_symbols() -> list[str]:
    raw = os.environ.get("SWING_PIPELINE_SYMBOLS", "")
    return [s.strip().upper() for s in raw.split(",") if s.strip()]


def configured_market() -> str:
    return os.environ.get("SWING_PIPELINE_MARKET", "us-stock").strip() or "us-stock"


def interval_seconds() -> int:
    try:
        return max(60, int(os.environ.get("SWING_PIPELINE_INTERVAL_S", "3600")))
    except ValueError:
        return 3600


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _get_json(url: str, params: Optional[dict] = None) -> Any:
    resp = requests.get(url, params=params, headers=_UA, timeout=_TIMEOUT_S)
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# COLLECT — one function per feed, each patchable in tests
# ---------------------------------------------------------------------------

def _yahoo_candles(symbol: str, range_: str = "3mo") -> list[dict[str, Any]]:
    data = _get_json(_YAHOO_CHART.format(symbol=symbol),
                     {"interval": "1d", "range": range_})
    result = (data["chart"]["result"] or [None])[0]
    quote = result["indicators"]["quote"][0]
    candles: list[dict[str, Any]] = []
    for open_, high, low, close, volume in zip(
        quote.get("open") or [], quote.get("high") or [],
        quote.get("low") or [], quote.get("close") or [],
        quote.get("volume") or [],
    ):
        if close is None or high is None or low is None:
            continue
        candles.append({
            "open": float(open_ if open_ is not None else close),
            "high": float(high), "low": float(low), "close": float(close),
            "volume": float(volume or 0.0),
        })
    return candles


def _okx_candles(inst_id: str, limit: int = 90) -> list[dict[str, Any]]:
    """OKX returns newest-first; swing_stack expects oldest-first."""
    data = _get_json(_OKX_CANDLES, {"instId": inst_id, "bar": "1Dutc", "limit": str(limit)})
    rows = list(reversed(data.get("data") or []))
    return [
        {"open": float(r[1]), "high": float(r[2]), "low": float(r[3]),
         "close": float(r[4]), "volume": float(r[5])}
        for r in rows
    ]


def _is_crypto(market: str) -> bool:
    return (market or "").strip().lower() in CRYPTO_MARKETS


def fetch_candles(symbol: str, market: str) -> list[dict[str, Any]]:
    if _is_crypto(market):
        inst = symbol if symbol.endswith("-SWAP") else f"{symbol.replace('USDT', '')}-USDT-SWAP"
        return _okx_candles(inst)
    return _yahoo_candles(symbol)


def fetch_benchmark_candles(market: str) -> list[dict[str, Any]]:
    if _is_crypto(market):
        return _okx_candles(CRYPTO_BENCHMARK)
    return _yahoo_candles(STOCK_BENCHMARK)


def _yahoo_close_series(symbol: str) -> list[float]:
    data = _get_json(_YAHOO_CHART.format(symbol=symbol), {"interval": "1d", "range": "1mo"})
    closes = data["chart"]["result"][0]["indicators"]["quote"][0]["close"]
    return [float(c) for c in closes if c is not None]


def fetch_macro() -> dict[str, Optional[float]]:
    """VIX / 10Y yield / DXY, now and five sessions back. Partial is fine."""
    out: dict[str, Optional[float]] = {}
    for key, symbol in (("vix", "%5EVIX"), ("y10", "%5ETNX"), ("dxy", "DX-Y.NYB")):
        try:
            closes = _yahoo_close_series(symbol)
        except Exception as exc:  # noqa: BLE001 — one leg, not the read
            logger.debug("swing_pipeline macro leg %s failed: %s", key, exc)
            continue
        if not closes:
            continue
        out[key] = closes[-1]
        if len(closes) >= 6:
            out[f"{key}_5d_ago"] = closes[-6]
    return out


def fetch_fear_greed(market: str) -> Optional[dict[str, Optional[float]]]:
    """Crowd gauge + its week-ago level (the turn, per doc §4).

    Crypto reads alternative.me (with daily history); US stocks read CNN,
    whose payload carries `previous_1_week` — a week-ago LEVEL, not a 7-day
    mean. swing_stack uses it only as the turn baseline, so a level is the
    honest input; it is not relabelled as an average.
    """
    try:
        if _is_crypto(market):
            data = psych_feed.fetch_fear_greed(limit=8)
            history = data.get("history") or []
            week_ago = float(history[7]["value"]) if len(history) > 7 else None
            return {"value": float(data["value"]), "avg_7d": week_ago}
        row = psych_feed.us_fear_greed()
        if not row or row.get("value") is None:
            return None
        prev = row.get("prev_1w")
        return {"value": float(row["value"]),
                "avg_7d": float(prev) if prev is not None else None}
    except Exception as exc:  # noqa: BLE001
        logger.debug("swing_pipeline fear&greed failed: %s", exc)
        return None


SENTIMENT_BLEND_MODES = ("off", "shadow", "live")


def sentiment_blend_mode() -> str:
    """off | shadow | live.

    `shadow` computes the per-symbol blend and records it beside the decision
    WITHOUT changing a single outcome — the blend has no vendor history to
    backtest (news/social snapshots are retention-pruned local tables), so the
    only honest evidence is live-forward disagreement, the same reason
    factor_snapshots exists. Flip to `live` on that evidence, not before.

    An unrecognized value falls back to `off`: never trade on a typo.
    """
    mode = os.environ.get("SWING_SENTIMENT_BLEND", "shadow").strip().lower()
    return mode if mode in SENTIMENT_BLEND_MODES else "off"


def fetch_news_sentiment(symbol: str) -> dict[str, Any]:
    """Per-symbol news tilt from snapshots market_intel already stores."""
    import market_intel
    return market_intel.news_sentiment_for(symbol)


def fetch_social_sentiment(symbol: str) -> dict[str, Any]:
    """Per-symbol social tilt from the social_feed snapshot (-1..1 -> -100..100)."""
    import social_feed
    read = social_feed.social_sentiment_for(symbol) or {}
    tilt = read.get("tilt")
    return {
        "score": round(float(tilt) * 100.0, 2) if tilt is not None else None,
        "posts": int(read.get("posts") or 0),
    }


def fetch_catalyst(symbol: str) -> dict[str, Any]:
    if not catalyst_feed.enabled():
        return {"score": None, "hours_to_next_earnings": None, "disabled": True}
    return catalyst_feed.catalyst_read(symbol)


def fetch_filings(symbol: str) -> dict[str, Any]:
    if not filings_feed.enabled():
        return {"score": None, "disabled": True}
    return filings_feed.insider_read(symbol)


def fetch_macro_event_hours() -> Optional[float]:
    """Hours to the next high-impact macro release, or None if unknown.

    Prefers this week's ForexFactory calendar; falls back to the repo's own
    static FOMC/CPI schedule (market_events) when the crawl fails."""
    now = datetime.now(timezone.utc)
    try:
        rows = _get_json(_FF_CALENDAR)
        upcoming = []
        for row in rows or []:
            if row.get("country") != "USD" or row.get("impact") != "High":
                continue
            raw = row.get("date")
            if not raw:
                continue
            try:
                when = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            except ValueError:
                continue
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
            delta = (when - now).total_seconds() / 3600.0
            if delta >= 0:
                upcoming.append(delta)
        if upcoming:
            return round(min(upcoming), 2)
    except Exception as exc:  # noqa: BLE001
        logger.debug("swing_pipeline calendar crawl failed: %s", exc)
    try:
        events = market_events.upcoming_events(now=now, limit=1)
        if events:
            when = datetime.fromisoformat(str(events[0]["when_utc"]).replace("Z", "+00:00"))
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
            return round((when - now).total_seconds() / 3600.0, 2)
    except Exception as exc:  # noqa: BLE001
        logger.debug("swing_pipeline static calendar fallback failed: %s", exc)
    return None


# ---------------------------------------------------------------------------
# SCORE -> COMBINE -> DECIDE
# ---------------------------------------------------------------------------

def _safe(feed: str, fn, default=None):
    """Run one collector inside crawl bookkeeping; a failure is no coverage.

    A feed that is switched off produces nothing, so it is recorded as
    `disabled` with 0 items rather than as a healthy pass — otherwise the
    console paints a non-producing collector green, which is the exact
    failure this monitoring exists to catch.
    """
    try:
        with crawl_monitor.track(feed) as run:
            value = fn()
            if isinstance(value, dict) and value.get("disabled"):
                run.items = 0
                run.detail = {"disabled": True}
                return value
            run.items = 1 if value not in (None, [], {}) else 0
            return value
    except Exception as exc:  # noqa: BLE001 — recorded by track, then absorbed
        logger.warning("swing_pipeline feed %s failed: %s", feed, exc)
        return default


def evaluate_symbol(symbol: str, market: str = "us-stock",
                    shared: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Collect -> score -> combine -> decide for one symbol.

    `shared` carries the four symbol-INDEPENDENT feeds pre-fetched once per
    pass by run_pipeline (measured 2026-08-31: fetching them per symbol put
    ~8 requests/hour on faireconomy's weekly calendar and the host answered
    429 with retry-after — a full-time feed down for 2+ monitoring cycles).
    Absent keys fall back to fetching here, so standalone calls behave
    exactly as before."""
    symbol = (symbol or "").strip().upper()
    shared = shared or {}

    candles = _safe(FEED_PRICE, lambda: fetch_candles(symbol, market), []) or []
    benchmark = (shared["benchmark"] if "benchmark" in shared else
                 _safe(FEED_PRICE, lambda: fetch_benchmark_candles(market), [])) or []
    macro = (shared["macro"] if "macro" in shared else
             _safe(FEED_MACRO, fetch_macro, {})) or {}
    gauge = (shared["gauge"] if "gauge" in shared else
             _safe(FEED_GAUGE, lambda: fetch_fear_greed(market)))
    catalyst = _safe(FEED_CATALYST, lambda: fetch_catalyst(symbol), {}) or {}
    filings = _safe(FEED_FILINGS, lambda: fetch_filings(symbol), {}) or {}
    event_hours = (shared["event_hours"] if "event_hours" in shared else
                   _safe(FEED_CALENDAR, fetch_macro_event_hours))

    market_sentiment = swing_stack.psych_sentiment_score(
        (gauge or {}).get("value"), (gauge or {}).get("avg_7d")
    )
    mode = sentiment_blend_mode()
    news: dict[str, Any] = {}
    social: dict[str, Any] = {}
    blended: Optional[float] = None
    if mode != "off":
        news = _safe(FEED_NEWS, lambda: fetch_news_sentiment(symbol), {}) or {}
        social = _safe(FEED_SOCIAL, lambda: fetch_social_sentiment(symbol), {}) or {}
        blended = swing_stack.blended_sentiment_score(
            market_sentiment,
            news=news.get("score"), social=social.get("score"),
            news_n=int(news.get("articles") or 0),
            social_n=int(social.get("posts") or 0),
        )
    # shadow measures without deciding; live decides on the blend and shadows
    # the gauge, so the comparison stays available in both directions.
    if mode == "live" and blended is not None:
        sentiment_used, sentiment_shadow = blended, market_sentiment
    elif mode == "shadow":
        sentiment_used, sentiment_shadow = market_sentiment, blended
    else:
        sentiment_used, sentiment_shadow = market_sentiment, None

    scores: dict[str, Optional[float]] = {
        "technical": swing_stack.technical_score(candles, benchmark or None),
        "macro": swing_stack.macro_score(
            macro.get("vix"), macro.get("vix_5d_ago"),
            macro.get("y10"), macro.get("y10_5d_ago"),
            macro.get("dxy"), macro.get("dxy_5d_ago"),
        ),
        "sentiment": sentiment_used,
        "thesis": catalyst.get("score"),
        "smart_money": filings.get("score"),
    }

    horizons = [
        h for h in (catalyst.get("hours_to_next_earnings"), event_hours) if h is not None
    ]
    hours_to_event = min(horizons) if horizons else None

    decision = swing_stack.decide(scores, hours_to_binary_event=hours_to_event)
    return {
        "symbol": symbol,
        "market": market,
        "scores": scores,
        "composite": decision["composite"],
        "axis": decision["axis"],
        "action": decision["action"],
        "veto": decision["veto"],
        "reason": decision["reason"],
        "coverage": sum(1 for v in scores.values() if v is not None),
        "hours_to_binary_event": hours_to_event,
        "sentiment_shadow": sentiment_shadow,
        "detail": {
            "candles": len(candles),
            "macro": macro,
            "fear_greed": gauge,
            "sentiment": {
                "mode": mode,
                "market": market_sentiment,
                "blended": blended,
                "news": news.get("score"),
                "news_articles": int(news.get("articles") or 0),
                "social": social.get("score"),
                "social_posts": int(social.get("posts") or 0),
            },
            "catalyst": {k: catalyst.get(k) for k in
                         ("quarters", "beats", "latest_surprise_pct",
                          "next_earnings_date", "error")},
            "filings": {k: filings.get(k) for k in
                        ("transactions", "buy_usd", "sell_usd", "filings_read")},
            "macro_event_hours": event_hours,
        },
    }


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def _persist(row: dict[str, Any]) -> None:
    scores = row.get("scores") or {}
    with database.get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO swing_decisions
                (symbol, market, computed_at, sentiment, macro, thesis,
                 smart_money, technical, composite, axis, action, veto,
                 reason, coverage, hours_to_event, sentiment_shadow, detail)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["symbol"], row.get("market"), _utc_now_iso(),
                scores.get("sentiment"), scores.get("macro"), scores.get("thesis"),
                scores.get("smart_money"), scores.get("technical"),
                row.get("composite"), row.get("axis"), row.get("action"),
                row.get("veto"), row.get("reason"), int(row.get("coverage") or 0),
                row.get("hours_to_binary_event"),
                row.get("sentiment_shadow"),
                json.dumps(row.get("detail") or {}, default=str)[:4000],
            ),
        )
        conn.commit()


def _decision_row(row: Any) -> dict[str, Any]:
    detail: dict[str, Any] = {}
    if row["detail"]:
        try:
            detail = json.loads(row["detail"])
        except (TypeError, ValueError):
            detail = {}
    return {
        "id": row["id"],
        "symbol": row["symbol"],
        "market": row["market"],
        "computed_at": row["computed_at"],
        "scores": {name: row[name] for name in PROCESSORS},
        "composite": row["composite"],
        "axis": row["axis"],
        "action": row["action"],
        "veto": row["veto"],
        "reason": row["reason"],
        "coverage": row["coverage"],
        "hours_to_event": row["hours_to_event"],
        "sentiment_shadow": row["sentiment_shadow"],
        "detail": detail,
    }


def latest_decisions() -> list[dict[str, Any]]:
    """The newest decision per symbol."""
    try:
        with database.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT d.* FROM swing_decisions d
                JOIN (SELECT symbol, MAX(id) AS last_id
                      FROM swing_decisions GROUP BY symbol) m
                  ON d.id = m.last_id
                ORDER BY d.symbol
                """
            )
            return [_decision_row(r) for r in cursor.fetchall()]
    except Exception as exc:  # noqa: BLE001
        logger.warning("swing_pipeline.latest_decisions failed: %s", exc)
        return []


def decision_history(symbol: str, limit: int = 50) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit or 50), 500))
    try:
        with database.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM swing_decisions WHERE symbol = ? "
                "ORDER BY id DESC LIMIT ?",
                ((symbol or "").strip().upper(), limit),
            )
            return [_decision_row(r) for r in cursor.fetchall()]
    except Exception as exc:  # noqa: BLE001
        logger.warning("swing_pipeline.decision_history failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Pass + loop
# ---------------------------------------------------------------------------

def run_pipeline(symbols: Optional[list[str]] = None,
                 market: Optional[str] = None) -> dict[str, Any]:
    """One full pass. A symbol that fails is counted, never fatal."""
    symbols = [s.strip().upper() for s in (symbols or configured_symbols()) if s.strip()]
    market = market or configured_market()
    evaluated = 0
    failed = 0
    actions: dict[str, int] = {}
    with crawl_monitor.track(FEED_PIPELINE) as run:
        # Symbol-independent feeds: ONE fetch per pass, not one per symbol
        # (the per-symbol version tripped faireconomy's rate limit — 429 on
        # the macro calendar after ~112 fetches in a day).
        shared: dict[str, Any] = {}
        if symbols:
            shared = {
                "benchmark": _safe(FEED_PRICE,
                                   lambda: fetch_benchmark_candles(market), []),
                "macro": _safe(FEED_MACRO, fetch_macro, {}),
                "gauge": _safe(FEED_GAUGE, lambda: fetch_fear_greed(market)),
                "event_hours": _safe(FEED_CALENDAR, fetch_macro_event_hours),
            }
        for symbol in symbols:
            try:
                row = evaluate_symbol(symbol, market=market, shared=shared)
                _persist(row)
                evaluated += 1
                actions[row["action"]] = actions.get(row["action"], 0) + 1
            except Exception as exc:  # noqa: BLE001 — one symbol, not the pass
                failed += 1
                logger.warning("swing_pipeline %s failed: %s", symbol, exc)
        run.items = evaluated
        run.detail = {"symbols": len(symbols), "failed": failed, "actions": actions}
    return {"evaluated": evaluated, "failed": failed, "actions": actions,
            "symbols": len(symbols), "market": market}


async def swing_pipeline_loop() -> None:
    """Background task: one pass per interval while the feature is enabled."""
    while True:
        try:
            if enabled() and configured_symbols():
                await asyncio.to_thread(run_pipeline)
            # Unconditional: social_feed and market_intel write crawl_runs
            # whether or not THIS feature is on, so retention cannot be gated
            # behind the pipeline flag or the table grows without bound.
            await asyncio.to_thread(crawl_monitor.prune)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 — a loop must not die
            logger.warning("swing_pipeline loop pass failed: %s", exc)
        await asyncio.sleep(interval_seconds())
