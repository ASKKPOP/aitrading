"""Government policy feed (Plan 14 F7) — Federal Register watchlists.

Fetches recent rules/notices from the Federal Register REST API (keyless,
official, stable) for agency+term watchlists and exposes them as an
ATTENTION signal per market: policy *direction* is deliberately not
keyword-scored — the research engine's LLM thesis stage reads the titles.

Pattern-copy of the market_events/whale_feed discipline: env-gated
(POLICY_FEED_ENABLED, default off), every fetch fails soft, results are
snapshotted in cache so the scorer makes zero external calls.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Optional

import requests

import cache

logger = logging.getLogger(__name__)

_API_URL = "https://www.federalregister.gov/api/v1/documents.json"
_SNAPSHOT_KEY = "policy_feed:snapshot"
_FETCH_TIMEOUT = 15

# Watchlists: market -> list of (agencies, term). Agencies use the Federal
# Register's slug vocabulary. Deliberately small — this is an attention flag,
# not a crawler.
WATCHLISTS: dict[str, list[dict[str, Any]]] = {
    "crypto": [
        {"agencies": ["securities-and-exchange-commission",
                      "commodity-futures-trading-commission",
                      "treasury-department"],
         "term": "digital asset"},
        {"agencies": ["securities-and-exchange-commission",
                      "treasury-department"],
         "term": "stablecoin"},
    ],
    "us-stock": [
        {"agencies": ["securities-and-exchange-commission"], "term": "listing standards"},
        {"agencies": ["federal-reserve-system"], "term": "capital requirements"},
    ],
}

POLICY_RECENCY_DAYS = max(1, int(os.environ.get("POLICY_RECENCY_DAYS", "7")))


def policy_feed_enabled() -> bool:
    return os.getenv("POLICY_FEED_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}


def _fetch_watchlist(agencies: list[str], term: str, limit: int = 10) -> list[dict[str, Any]]:
    """One Federal Register query. Returns [] on any failure (fail-soft)."""
    params: list[tuple[str, str]] = [
        ("per_page", str(limit)),
        ("order", "newest"),
        ("conditions[term]", term),
    ]
    for slug in agencies:
        params.append(("conditions[agencies][]", slug))
    try:
        resp = requests.get(_API_URL, params=params, timeout=_FETCH_TIMEOUT)
        resp.raise_for_status()
        results = (resp.json() or {}).get("results") or []
    except Exception as exc:  # noqa: BLE001
        logger.info("[PolicyFeed] fetch failed (%s / %s): %s", agencies, term, exc)
        return []
    docs = []
    for doc in results:
        if not isinstance(doc, dict):
            continue
        docs.append({
            "title": doc.get("title"),
            "type": doc.get("type"),
            "publication_date": doc.get("publication_date"),
            "agencies": [a.get("name") for a in (doc.get("agencies") or [])
                         if isinstance(a, dict)],
            "url": doc.get("html_url"),
            "term": term,
        })
    return docs


def refresh_policy_snapshot() -> dict[str, Any]:
    """Fetch every watchlist and snapshot the result. Called by the loop."""
    snapshot: dict[str, Any] = {"markets": {}, "fetched_at": time.time(), "errors": {}}
    for market, watchlists in WATCHLISTS.items():
        docs: list[dict[str, Any]] = []
        for wl in watchlists:
            got = _fetch_watchlist(wl["agencies"], wl["term"])
            if not got:
                snapshot["errors"][f"{market}:{wl['term']}"] = "empty_or_failed"
            docs.extend(got)
        snapshot["markets"][market] = docs
    cache.set_json(_SNAPSHOT_KEY, snapshot, ttl_seconds=48 * 3600)
    return snapshot


def get_policy_signals(max_age_seconds: float = 2 * 24 * 3600) -> dict[str, Any]:
    """Read API for the research scorer — snapshot only, zero external calls.

    Returns {market: {"recent_count": int, "titles": [...]}} for docs published
    within POLICY_RECENCY_DAYS. An absent or over-age snapshot returns {} so
    the factor scores as None (coverage shrinkage), never a fabricated 0.
    """
    snap = cache.get_json(_SNAPSHOT_KEY)
    if not isinstance(snap, dict):
        return {}
    fetched_at = snap.get("fetched_at") or 0
    if time.time() - float(fetched_at) > max_age_seconds:
        return {}  # age gate: stale snapshot == missing factor
    out: dict[str, Any] = {}
    import datetime as _dt
    cutoff = (_dt.date.today() - _dt.timedelta(days=POLICY_RECENCY_DAYS)).isoformat()
    for market, docs in (snap.get("markets") or {}).items():
        recent = [d for d in docs
                  if isinstance(d, dict) and str(d.get("publication_date") or "") >= cutoff]
        if recent:
            out[market] = {
                "recent_count": len(recent),
                "titles": [d.get("title") for d in recent[:6]],
            }
    return out


async def policy_feed_loop() -> None:
    """Background loop (registry key 'policy_feed', role 'research')."""
    import asyncio

    interval = max(3600, int(os.environ.get("POLICY_FEED_INTERVAL", str(6 * 3600))))
    while True:
        if policy_feed_enabled():
            try:
                snap = await asyncio.to_thread(refresh_policy_snapshot)
                total = sum(len(v) for v in snap.get("markets", {}).values())
                print(f"[PolicyFeed] refreshed: {total} docs, "
                      f"{len(snap.get('errors') or {})} errors")
            except Exception as exc:  # noqa: BLE001
                logger.warning("[PolicyFeed] refresh crashed: %s", exc)
        await asyncio.sleep(interval)
