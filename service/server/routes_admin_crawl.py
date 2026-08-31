"""routes_admin_crawl.py — the admin crawling & monitoring console.

Renders the swing signal stack the way the blueprint draws it —

    COLLECT (feeds) -> SCORE (5 processors, weighted) -> COMBINE (composite)
                    -> DECIDE (BUY / WAIT / SELL) -> risk gate (veto)

— but with live health on every node, taken from what our crawlers actually
did (crawl_runs) rather than from a one-shot probe of an upstream URL.

  GET  /api/admin/crawl/overview    the pipeline + per-node health
  GET  /api/admin/crawl/runs        crawl history, optionally per feed
  GET  /api/admin/crawl/decisions   latest decision per symbol, or one
                                    symbol's history
  POST /api/admin/crawl/run         run a pass now

Node status vocabulary: ok / failing / stale / idle. `idle` is not `ok` — a
feed that has never run has proven nothing, and the console must not paint
silence green.

Auth: admin session, same gate as the rest of the console.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import Body, FastAPI, Header, HTTPException

import crawl_monitor
import swing_pipeline
import swing_stack
from admin_auth import require_admin
from routes_shared import RouteContext

logger = logging.getLogger(__name__)

STALE_AFTER_SECONDS = 6 * 3600
MAX_MANUAL_SYMBOLS = 50


def _status_for(health: Optional[dict[str, Any]]) -> str:
    if not health:
        return "idle"
    if not health.get("last_ok"):
        return "failing"
    # A switched-off collector ran cleanly and produced nothing. That is not
    # health, and must never be counted as ok.
    if (health.get("last_detail") or {}).get("disabled"):
        return "disabled"
    age = health.get("age_seconds")
    if age is not None and age > STALE_AFTER_SECONDS:
        return "stale"
    return "ok"


def _node_health(key: str, summary: dict[str, dict[str, Any]]) -> dict[str, Any]:
    health = summary.get(key) or {}
    return {
        "status": _status_for(health or None),
        "last_run_at": health.get("last_run_at"),
        "last_ok": health.get("last_ok"),
        "last_items": health.get("last_items"),
        "last_error": health.get("last_error"),
        "last_duration_ms": health.get("last_duration_ms"),
        "age_seconds": health.get("age_seconds"),
        "runs_24h": health.get("runs_24h", 0),
        "success_rate": health.get("success_rate"),
    }


def _blend_readout(decisions: list[dict[str, Any]]) -> dict[str, Any]:
    """How often would the shadow sentiment have produced a different call?

    This is the evidence that decides whether the per-symbol blend is promoted
    to `live`. It cannot be backtested — news/social snapshots are
    retention-pruned with no vendor history — so the disagreement rate has to
    accumulate live-forward.
    """
    measured = 0
    action_flips = 0
    flipped: list[str] = []
    for row in decisions:
        shadow = row.get("sentiment_shadow")
        if shadow is None:
            continue
        measured += 1
        alt_scores = dict(row.get("scores") or {})
        alt_scores["sentiment"] = shadow
        alt = swing_stack.decide(
            alt_scores, hours_to_binary_event=row.get("hours_to_event")
        )
        if alt["action"] != row.get("action"):
            action_flips += 1
            flipped.append(row["symbol"])
    return {
        "mode": swing_pipeline.sentiment_blend_mode(),
        "measured": measured,
        "action_flips": action_flips,
        "flip_rate": round(action_flips / measured, 4) if measured else None,
        "flipped_symbols": flipped[:20],
    }


def _build_overview() -> dict[str, Any]:
    summary = crawl_monitor.feed_summary()
    decisions = swing_pipeline.latest_decisions()

    collect = [
        {**node, **_node_health(node["key"], summary)}
        for node in swing_pipeline.collect_nodes()
    ]

    score = []
    for node in swing_pipeline.PROCESSOR_NODES:
        covered = sum(
            1 for d in decisions if (d["scores"] or {}).get(node["key"]) is not None
        )
        values = [
            (d["scores"] or {}).get(node["key"]) for d in decisions
            if (d["scores"] or {}).get(node["key"]) is not None
        ]
        score.append({
            **node,
            "symbols": len(decisions),
            "covered_symbols": covered,
            "mean_score": round(sum(values) / len(values), 2) if values else None,
        })

    actions: dict[str, int] = {}
    for d in decisions:
        if d.get("action"):
            actions[d["action"]] = actions.get(d["action"], 0) + 1

    composites = [d["composite"] for d in decisions if d.get("composite") is not None]
    vetoed = sum(1 for d in decisions if d.get("veto"))
    blend = _blend_readout(decisions)

    return {
        "collect": collect,
        "score": score,
        "combine": {
            "range": [-100, 100],
            "symbols_scored": len(composites),
            "mean_composite": (
                round(sum(composites) / len(composites), 2) if composites else None
            ),
        },
        "decide": {
            "buy_threshold": swing_stack.BUY_THRESHOLD,
            "sell_threshold": swing_stack.SELL_THRESHOLD,
            "actions": actions,
            "vetoed": vetoed,
            "event_blackout_hours": swing_stack.EVENT_BLACKOUT_HOURS,
        },
        "ok_count": sum(1 for n in collect if n["status"] == "ok"),
        "failing_count": sum(1 for n in collect if n["status"] == "failing"),
        "idle_count": sum(1 for n in collect if n["status"] == "idle"),
        "disabled_count": sum(1 for n in collect if n["status"] == "disabled"),
        "stale_count": sum(1 for n in collect if n["status"] == "stale"),
        "pipeline_enabled": swing_pipeline.enabled(),
        "configured_symbols": swing_pipeline.configured_symbols(),
        "interval_seconds": swing_pipeline.interval_seconds(),
        "pipeline_health": _node_health(swing_pipeline.FEED_PIPELINE, summary),
        "blend": blend,
    }


def register_admin_crawl_routes(app: FastAPI, ctx: RouteContext) -> None:
    @app.get("/api/admin/crawl/overview")
    async def crawl_overview(authorization: str = Header(None)):
        require_admin(authorization)
        return _build_overview()

    @app.get("/api/admin/crawl/runs")
    async def crawl_runs(
        feed: Optional[str] = None,
        limit: int = 100,
        authorization: str = Header(None),
    ):
        require_admin(authorization)
        return {
            "runs": crawl_monitor.recent_runs(feed=feed, limit=limit),
            "feed": feed,
        }

    @app.get("/api/admin/crawl/decisions")
    async def crawl_decisions(
        symbol: Optional[str] = None,
        limit: int = 50,
        authorization: str = Header(None),
    ):
        require_admin(authorization)
        if symbol:
            return {
                "symbol": symbol.strip().upper(),
                "decisions": swing_pipeline.decision_history(symbol, limit=limit),
            }
        return {"symbol": None, "decisions": swing_pipeline.latest_decisions()}

    @app.post("/api/admin/crawl/run")
    async def crawl_run(
        payload: dict[str, Any] = Body(default_factory=dict),
        authorization: str = Header(None),
    ):
        require_admin(authorization)
        raw = payload.get("symbols") or swing_pipeline.configured_symbols()
        symbols = [str(s).strip().upper() for s in raw if str(s).strip()]
        if not symbols:
            raise HTTPException(
                status_code=400,
                detail="No symbol to run: pass symbols, or set SWING_PIPELINE_SYMBOLS.",
            )
        if len(symbols) > MAX_MANUAL_SYMBOLS:
            raise HTTPException(
                status_code=400,
                detail=f"Too many symbols ({len(symbols)}); max {MAX_MANUAL_SYMBOLS}.",
            )
        market = (payload.get("market") or swing_pipeline.configured_market()).strip()
        try:
            result = swing_pipeline.run_pipeline(symbols, market=market)
        except Exception as exc:  # noqa: BLE001 — a bad pass is a report, not a 500
            logger.warning("admin manual crawl run failed: %s", exc)
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:300]}
        return {"ok": True, **result}
