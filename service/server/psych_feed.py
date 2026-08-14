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
import re
import time
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
# Card 11 — real liquidations (OKX, keyless). Last-hour liquidation notional
# at/above this threshold flags a shock regardless of the σ proxy.
LIQ_SHOCK_NOTIONAL_USD = float(os.getenv("LIQ_SHOCK_NOTIONAL_USD", "5000000") or 5_000_000)
SPIKE_Z = 2.0                  # |z| ≥ 2 is a sentiment spike
SPIKE_MIN_POINTS = 5           # snapshots needed before z-scores mean anything
ANTICIPATION_MARKETS = 10      # how many relevant markets we keep
ANTICIPATION_POOL = 250        # how many top-volume markets we sift to find them

# Topics whose odds can plausibly move crypto: the assets themselves, the
# regulatory decisions that reprice them, and the macro prints that set the
# risk backdrop. Anything else (elections abroad, sport, esports) is noise
# for this platform, however heavily traded. Overridable per deployment.
ANTICIPATION_TOPICS = tuple(
    t.strip().lower()
    for t in os.getenv(
        "ANTICIPATION_TOPICS",
        "bitcoin,btc,ethereum,eth,solana,xrp,ripple,dogecoin,crypto,coinbase,binance,"
        "stablecoin,defi,altcoin,etf,sec,cftc,regulation,lawsuit,"
        "fed,fomc,interest rate,rate cut,rate hike,cpi,inflation,recession,powell,"
        "treasury,tariff,strategic reserve",
    ).split(",")
    if t.strip()
)

# Matched on WORD BOUNDARIES, not as substrings. The tickers are short enough
# to hide inside ordinary words: plain `"eth" in text` matches "Ethiopia" —
# which is exactly how the live Ethiopian-election markets would have survived
# this filter. Likewise "sec" in "second", "fed" in "federal". Hyphens in slugs
# ("will-the-fed-cut-rates") count as boundaries, so \b handles those too.
_ANTICIPATION_PATTERNS = tuple(
    re.compile(rf"\b{re.escape(t)}\b") for t in ANTICIPATION_TOPICS
)
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
        # The vendor's own print time, not ours. F&G updates once daily, so a
        # reader (and the D5 verifier) cannot tell a fresh read from a
        # day-old one without it — we were fetching it and dropping it.
        "as_of": datetime.fromtimestamp(current["timestamp"], timezone.utc)
                         .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "history": history,
        "source": "alternative.me",
    }


def fetch_cnn_fear_greed() -> Optional[dict[str, Any]]:
    """US-stock analog of the crypto F&G (Plan 14 F2): CNN's fear&greed index.

    Unofficial endpoint — breakage is an accepted risk, so this returns None
    on ANY failure and the caller's factor coverage renormalizes it away.
    Never raises.
    """
    try:
        resp = requests.get(
            "https://production.dataviz.cnn.io/index/fearandgreed/graphdata",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10,
        )
        resp.raise_for_status()
        fg = (resp.json() or {}).get("fear_and_greed") or {}
        score = fg.get("score")
        if score is None:
            return None
        prev_1w = fg.get("previous_1_week")
        return {
            "value": float(score),
            "classification": fg.get("rating"),
            "prev_1w": float(prev_1w) if prev_1w is not None else None,
            "as_of": fg.get("timestamp"),
            "source": "cnn",
        }
    except Exception:  # noqa: BLE001
        return None


# Plan 25 Phase B — the CNN gauge above was fetched-but-never-wired since
# Plan 14. The desk brief lines read it every cycle, so it is cached here
# with last-known-good semantics: a CNN outage degrades the read to the
# previous value, never to a network call per cycle and never to an error.
_US_FNG_CACHE: dict[str, Any] = {"row": None, "at": 0.0}
_US_FNG_TTL_SECONDS = 1800.0


def us_fear_greed(force: bool = False) -> Optional[dict[str, Any]]:
    """Cached CNN fear&greed for the us-stock/forex desk brief lines."""
    now = time.monotonic()
    if (force or _US_FNG_CACHE["row"] is None
            or now - _US_FNG_CACHE["at"] >= _US_FNG_TTL_SECONDS):
        row = fetch_cnn_fear_greed()
        if row is not None:
            _US_FNG_CACHE["row"] = row
            _US_FNG_CACHE["at"] = now
        elif _US_FNG_CACHE["row"] is not None:
            # outage: keep serving last-known-good, retry next TTL window
            _US_FNG_CACHE["at"] = now
    return _US_FNG_CACHE["row"]


def fetch_fear_greed_full_history() -> list[dict[str, Any]]:
    """Complete F&G daily archive (limit=0 → everything since 2018-02),
    oldest-first as {date, value, classification}. Used by the strategy
    backtester (Phase 4) — live reads keep the 30-day window."""
    resp = requests.get(FNG_API_URL, params={"limit": "0"}, timeout=30)
    resp.raise_for_status()
    data = resp.json().get("data") or []
    rows = []
    for row in data:
        try:
            ts = int(row["timestamp"])
            rows.append({
                "date": datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d"),
                "value": int(row["value"]),
                "classification": row.get("value_classification"),
            })
        except (KeyError, TypeError, ValueError):
            continue
    rows.sort(key=lambda r: r["date"])
    return rows


def shock_history(hours: int = 72) -> list[dict[str, Any]]:
    """Shock readings from stored psych snapshots within the last `hours`.

    Returns [{created_at, shocks: [...only rows flagged shock...]}, ...]
    oldest-first. Confluence B5's "shock flagged then cleared" and the regime
    filter's panic age both need this window; snapshots retain ~20 days at the
    hourly cadence, comfortably covering 72h.
    """
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """SELECT shock_json, created_at FROM psych_snapshots
               WHERE created_at >= ? ORDER BY created_at ASC, id ASC""",
            (cutoff,))
        rows = cursor.fetchall()
    finally:
        conn.close()

    out = []
    for row in rows:
        try:
            shocks = [s for s in json.loads(row["shock_json"] or "[]")
                      if isinstance(s, dict) and s.get("shock")]
        except ValueError:
            continue
        out.append({"created_at": row["created_at"], "shocks": shocks})
    return out


def shock_series(hours: int = 72, symbol: Optional[str] = None) -> dict[str, Any]:
    """Every stored σ reading in the window, for charting — not just the
    flagged ones.

    shock_history() drops rows where shock is False because its callers
    (confluence B5, the regime filter) only care about breaches. A chart needs
    the opposite: the whole σ-multiple line, so the 3σ threshold has something
    to be crossed. Kept separate rather than widening shock_history, whose
    filtered contract those two callers depend on.

    Returns {"available", "threshold_sigma", "threshold_volume_ratio",
             "series": {SYMBOL: [{created_at, sigma_multiple, volume_ratio,
                                  latest_return_pct, shock}, ...]}}
    oldest-first per symbol.
    """
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=max(1, hours))
              ).strftime("%Y-%m-%dT%H:%M:%SZ")
    want = (symbol or "").strip().upper() or None

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """SELECT shock_json, created_at FROM psych_snapshots
               WHERE created_at >= ? ORDER BY created_at ASC, id ASC""",
            (cutoff,))
        rows = cursor.fetchall()
    finally:
        conn.close()

    series: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        try:
            readings = json.loads(row["shock_json"] or "[]")
        except ValueError:
            continue
        for r in readings:
            if not isinstance(r, dict):
                continue
            sym = str(r.get("symbol") or "").upper()
            if not sym or (want and sym != want):
                continue
            series.setdefault(sym, []).append({
                "created_at": row["created_at"],
                "sigma_multiple": r.get("sigma_multiple"),
                "volume_ratio": r.get("volume_ratio"),
                "latest_return_pct": r.get("latest_return_pct"),
                "shock": bool(r.get("shock")),
            })

    return {
        "available": bool(series),
        "hours": max(1, hours),
        "threshold_sigma": SHOCK_SIGMA_MULTIPLE,
        "threshold_volume_ratio": SHOCK_VOLUME_RATIO,
        # The shock read is a liquidation PROXY on free data — say so wherever
        # it is charted, or a σ spike reads as measured liquidation volume.
        "estimated": True,
        "series": series,
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


def aggregate_liquidations(rows: list[dict[str, Any]], ct_val: float,
                           now_ms: Optional[int] = None,
                           window_minutes: int = 60) -> dict[str, Any]:
    """Aggregate raw OKX liquidation orders into last-window totals.

    Notional per order = contracts x ctVal x bankruptcy price. 'long' pos_side
    means longs got liquidated (forced sells) and vice versa.
    """
    if now_ms is None:
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    cutoff = now_ms - window_minutes * 60 * 1000
    count = 0
    long_usd = short_usd = 0.0
    for r in rows:
        if (r.get("ts") or 0) < cutoff:
            continue
        notional = (r.get("contracts") or 0) * ct_val * (r.get("price") or 0)
        count += 1
        if r.get("pos_side") == "long":
            long_usd += notional
        else:
            short_usd += notional
    total = long_usd + short_usd
    return {
        "liq_count_1h": count,
        "liq_notional_usd_1h": round(total, 0),
        "long_liq_usd_1h": round(long_usd, 0),
        "short_liq_usd_1h": round(short_usd, 0),
    }


def _merge_real_liquidations(proxy: dict[str, Any], symbol: str) -> dict[str, Any]:
    """Attach real OKX liquidation aggregates to a shock row (card 11).
    On success the row stops being an estimate; on any failure the σ proxy
    stands unchanged."""
    try:
        from crypto_feed import fetch_instrument_ct_val, fetch_liquidation_orders
        rows = fetch_liquidation_orders(symbol, limit=100)
        ct_val = fetch_instrument_ct_val(symbol)
        agg = aggregate_liquidations(rows, ct_val)
    except Exception as exc:  # noqa: BLE001
        logger.warning("real liquidation fetch failed for %s: %s", symbol, exc)
        return proxy
    proxy.update(agg)
    proxy["estimated"] = False
    proxy["liq_source"] = "okx"
    proxy["liq_shock_threshold_usd"] = LIQ_SHOCK_NOTIONAL_USD
    proxy["shock"] = bool(proxy["shock"]) or agg["liq_notional_usd_1h"] >= LIQ_SHOCK_NOTIONAL_USD
    return proxy


def _gather_shock_proxies() -> list[dict[str, Any]]:
    from crypto_feed import fetch_candles

    proxies = []
    for symbol in SHOCK_SYMBOLS:
        try:
            candles = fetch_candles(symbol, bar="1H", limit=100)
            proxy = compute_shock_proxy(candles, symbol)
            if proxy:
                proxies.append(_merge_real_liquidations(proxy, symbol))
        except Exception as exc:  # noqa: BLE001
            logger.warning("shock proxy fetch failed for %s: %s", symbol, exc)
    return proxies


# ─────────────────────────── anticipation (Polymarket odds) ───────────────────────────

def is_relevant_market(text: Any) -> bool:
    """Could this prediction market plausibly move crypto?

    Polymarket's top-volume markets are whatever the world is betting on —
    live that was Ethiopian elections, the FIFA World Cup and a League of
    Legends match. Unfiltered, those fed the CRYPTO anticipation signal: a
    ±0.05 swing on an esports match added +0.25 to the psych component and
    printed "odds re-rating LoL: Hanwha Life vs T1" as a trade rationale on
    the board. That is noise laundered into a reason to trade.

    The mockup specifies event-relevant odds tied to the asset ("XRP 규제 판결
    기대감, 배당률 0.61→0.68"), so relevance is the spec, not a refinement.
    """
    haystack = str(text or "").lower()
    return any(p.search(haystack) for p in _ANTICIPATION_PATTERNS)


def _gather_anticipation() -> list[dict[str, Any]]:
    """Snapshot the top CRYPTO/MACRO-relevant Polymarket markets with their odds.

    Fetches a wider pool than it keeps, because relevance filtering discards
    most of the top-volume list. If nothing relevant is live, returns [] —
    anticipation then reports as missing, which is honest. Substituting an
    unrelated market would not be.
    """
    from price_fetcher import _parse_string_array, _polymarket_get_json, POLYMARKET_GAMMA_BASE_URL

    if not POLYMARKET_GAMMA_BASE_URL:
        return []
    url = f"{POLYMARKET_GAMMA_BASE_URL.rstrip('/')}/markets"
    raw = _polymarket_get_json(url, params={
        "limit": str(ANTICIPATION_POOL), "order": "volume24hr",
        "ascending": "false", "active": "true", "closed": "false",
    })
    markets = []
    for m in raw if isinstance(raw, list) else []:
        if not isinstance(m, dict):
            continue
        if not is_relevant_market(f"{m.get('question') or ''} {m.get('title') or ''} {m.get('slug') or ''}"):
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
        if len(markets) >= ANTICIPATION_MARKETS:
            break
    return markets


def _canonical_outcome(odds: dict[str, Any]) -> Optional[str]:
    """The one outcome whose movement carries the market's meaning.

    A binary market says the same thing twice: P(Yes) falling 0.10 IS P(No)
    rising 0.10. Emitting both rows made the anticipation signal
    mathematically incapable of being bearish — the consumer tests
    `delta >= +0.05` one-sidedly, so ANY movement always produced the bullish
    row and a +0.25 bump. Proven live: 'Will BTC be above $60k?' with Yes
    collapsing 0.70 -> 0.55 fired BULLISH via the No side.
    (Audit 2026-07-17, 4/4 QA.)

    'Yes' is the canonical side where it exists — that is the side the
    question is asked from. Otherwise fall back to the first outcome, which is
    arbitrary but at least consistent between snapshots.
    """
    if not odds:
        return None
    for key in odds:
        if str(key).strip().lower() == "yes":
            return key
    return next(iter(odds))


def compute_odds_deltas(latest: list[dict[str, Any]],
                        previous: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Signed Δodds per MARKET (not per outcome) between two anticipation
    snapshots, matched by slug. One row per market, from its canonical side,
    so the sign means something."""
    prev_by_slug = {m["slug"]: m for m in previous if m.get("slug")}
    deltas = []
    for market in latest:
        prev = prev_by_slug.get(market.get("slug"))
        if not prev:
            continue
        outcome = _canonical_outcome(market.get("odds") or {})
        if outcome is not None:
            price = (market.get("odds") or {})[outcome]
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
        # Two-step prune: MySQL rejects both LIMIT-in-IN-subquery (1235) and
        # selecting from the DELETE target (1093), so pick the cutoff first.
        cursor.execute(
            """SELECT id FROM psych_snapshots
               ORDER BY created_at DESC, id DESC LIMIT 1 OFFSET ?""",
            (PSYCH_HISTORY_LIMIT - 1,),
        )
        cutoff = cursor.fetchone()
        if cutoff:
            cursor.execute("DELETE FROM psych_snapshots WHERE id < ?", (cutoff["id"],))
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
        "shock_note": ("real liquidation data (OKX) when available; "
                       "volatility-σ proxy only as fail-soft fallback (see per-entry 'estimated')"),
        "anticipation": anticipation,
        "odds_deltas": odds_deltas,
        "created_at": latest["created_at"],
    }
    # Plan 06 B1 — real whale activity rides along on the psych payload so the
    # signals board gets it without another endpoint. Fail-soft.
    try:
        from whale_feed import get_whale_payload
        payload["whales"] = get_whale_payload()
    except Exception:  # noqa: BLE001
        payload["whales"] = {"available": False, "events": [], "totals": {}}
    try:
        from cache import set_json
        set_json(_CACHE_KEY, payload, ttl_seconds=_CACHE_TTL_SECONDS)
    except Exception:  # noqa: BLE001
        pass
    return payload
