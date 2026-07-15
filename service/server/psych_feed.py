"""Psychology feed (signal-collection plan Phase 2).

Collects the crowd-psychology inputs the trigger framework needs and stores them
as periodic snapshots (psych_snapshots), one row per refresh:

  fear_greed     alternative.me /fng — index value + classification + daily history
                 (no API key; verified live 2026-07-14: 22 → 25 "Extreme Fear")
  spikes         sentiment Δ per news category, computed from our own
                 market_news_snapshots history: z-score of the latest snapshot's
                 mean overall_sentiment_score vs. the prior series. A negative
                 spike (z ≤ −SPIKE_Z) is journaled as an experiment event
                 ('psych_sentiment_spike') at refresh time.
  shock          liquidation-shock PROXY: hourly candle σ + volume ratio from OKX.
                 Free sources have no real liquidation data, so this is an honest
                 approximation — every payload carries "estimated": True and the
                 UI must label it as such.
  anticipation   Polymarket odds snapshot (top markets by 24h volume, prices from
                 the Gamma API). Δodds is computed in the payload by comparing
                 the latest snapshot with the previous one.

The refresh loop is gated behind PSYCH_FEED_ENABLED (default off) per the plan's
phase-isolation principle; reads (/api/market-intel/psych) work regardless and
report available=False until a snapshot exists. Every external fetch fails soft:
a failed source is skipped and the rest of the snapshot still lands.
"""

from __future__ import annotations

import json
import logging
import math
import os
from datetime import datetime, timezone
from typing import Any, Optional

import requests

from database import get_db_connection

logger = logging.getLogger(__name__)

FNG_API_URL = os.environ.get("FNG_API_URL", "https://api.alternative.me/fng/")
FNG_HISTORY_DAYS = 30
SHOCK_SYMBOLS = ("BTCUSDT", "ETHUSDT")
SHOCK_SIGMA_MULTIPLE = 3.0     # |latest return| ≥ 3σ counts as a shock
SHOCK_VOLUME_RATIO = 2.0       # last-hour volume ≥ 2× 24h average
SPIKE_Z = 2.0                  # |z| ≥ 2 is a sentiment spike
SPIKE_MIN_POINTS = 5           # snapshots needed before z-scores mean anything
ANTICIPATION_MARKETS = 10
PSYCH_HISTORY_LIMIT = 500

_CACHE_KEY = "sooppiy:psych:payload"
_CACHE_TTL_SECONDS = 120


def psych_feed_enabled() -> bool:
    return os.getenv("PSYCH_FEED_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}


def _utc_now_iso_z() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ─────────────────────────── fear & greed ───────────────────────────

def fetch_fear_greed(limit: int = FNG_HISTORY_DAYS) -> dict[str, Any]:
    """Fetch the crypto Fear & Greed index with daily history from alternative.me."""
    resp = requests.get(FNG_API_URL, params={"limit": str(limit)}, timeout=10)
    resp.raise_for_status()
    data = resp.json().get("data") or []
    history = []
    for row in data:
        try:
            history.append({
                "value": int(row["value"]),
                "classification": row.get("value_classification"),
                "timestamp": int(row["timestamp"]),
            })
        except (KeyError, TypeError, ValueError):
            continue
    if not history:
        raise RuntimeError("alternative.me returned no F&G data")
    current = history[0]
    # Δ over 3 days — the framework's buy trigger watches for F&G recovery.
    delta_3d = current["value"] - history[3]["value"] if len(history) > 3 else None
    return {
        "value": current["value"],
        "classification": current["classification"],
        "delta_3d": delta_3d,
        "history": history,
        "source": "alternative.me",
    }


# ─────────────────────────── sentiment spikes ───────────────────────────

def _news_sentiment_series() -> dict[str, list[dict[str, Any]]]:
    """Per news category, the time series of snapshot mean sentiment scores
    (oldest → newest) from our stored market_news_snapshots history."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """SELECT category, items_json, created_at
               FROM market_news_snapshots
               ORDER BY created_at ASC, id ASC""")
        rows = cursor.fetchall()
    finally:
        conn.close()

    series: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        try:
            items = json.loads(row["items_json"] or "[]")
        except ValueError:
            continue
        scores = [float(i.get("overall_sentiment_score") or 0)
                  for i in items if isinstance(i, dict)]
        if not scores:
            continue
        series.setdefault(row["category"], []).append({
            "mean_score": sum(scores) / len(scores),
            "created_at": row["created_at"],
        })
    return series


def compute_sentiment_spikes() -> list[dict[str, Any]]:
    """z-score of each category's latest snapshot sentiment vs. its prior series.
    Returns every category with enough history; 'spike' marks |z| ≥ SPIKE_Z."""
    spikes = []
    for category, points in _news_sentiment_series().items():
        if len(points) < SPIKE_MIN_POINTS:
            continue
        prior = [p["mean_score"] for p in points[:-1]]
        latest = points[-1]
        mean = sum(prior) / len(prior)
        var = sum((x - mean) ** 2 for x in prior) / len(prior)
        std = math.sqrt(var)
        if std <= 1e-9:
            continue
        z = (latest["mean_score"] - mean) / std
        spikes.append({
            "category": category,
            "z": round(z, 2),
            "latest_score": round(latest["mean_score"], 4),
            "baseline_mean": round(mean, 4),
            "spike": abs(z) >= SPIKE_Z,
            "direction": "negative" if z < 0 else "positive",
            "as_of": latest["created_at"],
        })
    return spikes


def _record_spike_events(spikes: list[dict[str, Any]], snapshot_key: str) -> int:
    """Journal negative sentiment spikes as experiment events (acceptance:
    'a negative z>2 spike is recorded as an event'). Runs once per refresh —
    the snapshot_key makes the event traceable to its snapshot."""
    from experiment_events import record_event

    recorded = 0
    for spike in spikes:
        if not spike["spike"] or spike["direction"] != "negative":
            continue
        try:
            record_event(
                "psych_sentiment_spike",
                object_type="psych_snapshot",
                object_id=snapshot_key,
                metadata={"category": spike["category"], "z": spike["z"],
                          "latest_score": spike["latest_score"],
                          "baseline_mean": spike["baseline_mean"]},
            )
            recorded += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("failed to record psych spike event: %s", exc)
    return recorded


# ─────────────────────────── shock proxy ───────────────────────────

def compute_shock_proxy(candles: list[dict[str, Any]], symbol: str) -> Optional[dict[str, Any]]:
    """Volatility-shock PROXY from hourly candles: σ of hourly returns plus a
    volume ratio. NOT real liquidation data — always labeled estimated."""
    closes = [c["close"] for c in candles]
    volumes = [c["volume"] for c in candles]
    if len(closes) < 26:
        return None
    returns = [(closes[i] - closes[i - 1]) / closes[i - 1]
               for i in range(1, len(closes)) if closes[i - 1] > 0]
    if len(returns) < 25:
        return None
    window = returns[-25:-1]  # trailing 24h, excluding the latest hour
    mean = sum(window) / len(window)
    var = sum((r - mean) ** 2 for r in window) / len(window)
    sigma = math.sqrt(var)
    latest_return = returns[-1]
    sigma_multiple = abs(latest_return) / sigma if sigma > 1e-12 else 0.0
    vol_24h = volumes[-25:-1]
    avg_volume = sum(vol_24h) / len(vol_24h) if vol_24h else 0.0
    volume_ratio = volumes[-1] / avg_volume if avg_volume > 0 else 0.0
    return {
        "symbol": symbol,
        "latest_return_pct": round(latest_return * 100, 3),
        "sigma_pct": round(sigma * 100, 3),
        "sigma_multiple": round(sigma_multiple, 2),
        "volume_ratio": round(volume_ratio, 2),
        "shock": sigma_multiple >= SHOCK_SIGMA_MULTIPLE and volume_ratio >= SHOCK_VOLUME_RATIO,
        "estimated": True,  # proxy for liquidations — free sources have no real data
    }


def _gather_shock_proxies() -> list[dict[str, Any]]:
    from crypto_feed import fetch_candles

    proxies = []
    for symbol in SHOCK_SYMBOLS:
        try:
            candles = fetch_candles(symbol, bar="1H", limit=100)
            proxy = compute_shock_proxy(candles, symbol)
            if proxy:
                proxies.append(proxy)
        except Exception as exc:  # noqa: BLE001
            logger.warning("shock proxy fetch failed for %s: %s", symbol, exc)
    return proxies


# ─────────────────────────── anticipation (Polymarket odds) ───────────────────────────

def _gather_anticipation() -> list[dict[str, Any]]:
    """Snapshot top Polymarket markets with their outcome prices (odds)."""
    from price_fetcher import _parse_string_array, _polymarket_get_json, POLYMARKET_GAMMA_BASE_URL

    if not POLYMARKET_GAMMA_BASE_URL:
        return []
    url = f"{POLYMARKET_GAMMA_BASE_URL.rstrip('/')}/markets"
    raw = _polymarket_get_json(url, params={
        "limit": str(ANTICIPATION_MARKETS), "order": "volume24hr",
        "ascending": "false", "active": "true", "closed": "false",
    })
    markets = []
    for m in raw if isinstance(raw, list) else []:
        if not isinstance(m, dict):
            continue
        outcomes = _parse_string_array(m.get("outcomes"))
        prices = _parse_string_array(m.get("outcomePrices"))
        odds = {}
        for outcome, price in zip(outcomes, prices):
            try:
                odds[str(outcome)] = float(price)
            except (TypeError, ValueError):
                continue
        if not odds:
            continue
        markets.append({
            "slug": m.get("slug"),
            "title": m.get("question") or m.get("title") or m.get("slug"),
            "volume_24hr": m.get("volume24hr"),
            "odds": odds,
        })
    return markets


def compute_odds_deltas(latest: list[dict[str, Any]],
                        previous: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Δodds per market outcome between two anticipation snapshots (matched by slug)."""
    prev_by_slug = {m["slug"]: m for m in previous if m.get("slug")}
    deltas = []
    for market in latest:
        prev = prev_by_slug.get(market.get("slug"))
        if not prev:
            continue
        for outcome, price in (market.get("odds") or {}).items():
            old = (prev.get("odds") or {}).get(outcome)
            if old is None or old <= 0:
                continue
            deltas.append({
                "slug": market["slug"],
                "title": market.get("title"),
                "outcome": outcome,
                "odds_from": old,
                "odds_to": price,
                "delta": round(price - old, 4),
                "delta_pct": round((price - old) / old * 100, 2),
            })
    deltas.sort(key=lambda d: abs(d["delta"]), reverse=True)
    return deltas


# ─────────────────────────── snapshot refresh + payload ───────────────────────────

def refresh_psych_snapshot() -> dict[str, Any]:
    """Collect all four psych sources and persist one snapshot row.
    Each source fails soft — a partial snapshot is still stored."""
    created_at = _utc_now_iso_z()
    snapshot_key = f"psych:{created_at}"
    errors: dict[str, str] = {}

    fng = None
    try:
        fng = fetch_fear_greed()
    except Exception as exc:  # noqa: BLE001
        errors["fear_greed"] = str(exc)

    spikes: list[dict[str, Any]] = []
    try:
        spikes = compute_sentiment_spikes()
    except Exception as exc:  # noqa: BLE001
        errors["spikes"] = str(exc)

    shock = _gather_shock_proxies()
    anticipation: list[dict[str, Any]] = []
    try:
        anticipation = _gather_anticipation()
    except Exception as exc:  # noqa: BLE001
        errors["anticipation"] = str(exc)

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """INSERT INTO psych_snapshots
               (snapshot_key, fng_json, spikes_json, shock_json, anticipation_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (snapshot_key,
             json.dumps(fng, ensure_ascii=True) if fng else None,
             json.dumps(spikes, ensure_ascii=True),
             json.dumps(shock, ensure_ascii=True),
             json.dumps(anticipation, ensure_ascii=True),
             created_at),
        )
        cursor.execute(
            """DELETE FROM psych_snapshots
               WHERE id NOT IN (SELECT id FROM psych_snapshots
                                ORDER BY created_at DESC, id DESC LIMIT ?)""",
            (PSYCH_HISTORY_LIMIT,),
        )
        conn.commit()
    finally:
        conn.close()

    events = _record_spike_events(spikes, snapshot_key)

    try:
        from cache import delete
        delete(_CACHE_KEY)
    except Exception:  # noqa: BLE001
        pass

    return {"snapshot_key": snapshot_key, "created_at": created_at,
            "fng": fng["value"] if fng else None,
            "spike_events_recorded": events, "errors": errors}


def get_psych_payload() -> dict[str, Any]:
    """Latest psych snapshot plus Δodds computed against the previous snapshot."""
    try:
        from cache import get_json
        cached = get_json(_CACHE_KEY)
        if isinstance(cached, dict):
            return cached
    except Exception:  # noqa: BLE001
        pass

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """SELECT fng_json, spikes_json, shock_json, anticipation_json, created_at
               FROM psych_snapshots ORDER BY created_at DESC, id DESC LIMIT 2""")
        rows = cursor.fetchall()
    finally:
        conn.close()

    if not rows:
        return {"available": False, "fear_greed": None, "spikes": [],
                "shock": [], "anticipation": [], "odds_deltas": [], "created_at": None}

    latest = rows[0]
    anticipation = json.loads(latest["anticipation_json"] or "[]")
    odds_deltas: list[dict[str, Any]] = []
    if len(rows) > 1:
        previous = json.loads(rows[1]["anticipation_json"] or "[]")
        odds_deltas = compute_odds_deltas(anticipation, previous)

    payload = {
        "available": True,
        "fear_greed": json.loads(latest["fng_json"]) if latest["fng_json"] else None,
        "spikes": json.loads(latest["spikes_json"] or "[]"),
        "shock": json.loads(latest["shock_json"] or "[]"),
        "shock_note": "estimated proxy (volatility σ + volume) — not real liquidation data",
        "anticipation": anticipation,
        "odds_deltas": odds_deltas,
        "created_at": latest["created_at"],
    }
    try:
        from cache import set_json
        set_json(_CACHE_KEY, payload, ttl_seconds=_CACHE_TTL_SECONDS)
    except Exception:  # noqa: BLE001
        pass
    return payload
