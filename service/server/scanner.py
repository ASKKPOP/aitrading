"""Which-coin scanner (signal-collection plan Phase 4).

Answers "which coin should the desk even look at?" by ranking candidates from
three free, verified sources, snapshotted per scan (scanner_snapshots):

  volume surge   OKX: top-N USDT perps by 24h volume, each checked against its
                 own 7d average daily volume from 1D candles → ratio (e.g. x2.4)
  mention surge  StockTwits messages-per-hour for a small watch set, compared
                 to the baseline rate stored in our own previous snapshots
                 (needs ≥ MENTION_MIN_BASELINE prior scans before it can fire)
  new listing    OKX /public/instruments SWAP list diffed against the previous
                 snapshot's list — anything new is a candidate by itself

Whale/on-chain flows need paid sources (Hashdive-class) and are deferred to
Phase 6 — fetch_whale_signals() below is the interface stub, wired so the
assembly loop already consumes its (empty) output.

Every candidate carries human-readable reasons ("volume x2.4 vs 7d avg",
"mentions +180%/h") — the acceptance criterion. The automation engine can point
a rule's symbol at 'SCANNER' to auto-analyze the current top candidate.

Gated behind SCANNER_ENABLED (default off). All fetches fail soft; a partial
snapshot still lands.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

import requests

from database import get_db_connection

logger = logging.getLogger(__name__)

SCANNER_UNIVERSE = int(os.environ.get("SCANNER_UNIVERSE", "30"))  # top-N by 24h volume
VOLUME_SURGE_RATIO = 2.0        # 24h volume ≥ 2× its 7d average
MENTION_SURGE_PCT = 100.0       # mention rate ≥ +100% vs baseline
MENTION_MIN_BASELINE = 3        # prior scans needed before mention surge can fire
MENTION_SYMBOLS = tuple(
    s.strip().upper() for s in
    os.environ.get("SCANNER_MENTION_SYMBOLS", "BTC,ETH,SOL,DOGE,XRP").split(",") if s.strip())
SCANNER_HISTORY_LIMIT = 500
STOCKTWITS_TIMEOUT = 8

_CACHE_KEY = "sooppiy:scanner:payload"
_CACHE_TTL_SECONDS = 120


def scanner_enabled() -> bool:
    return os.getenv("SCANNER_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}


def _utc_now_iso_z() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ─────────────────────────── volume surge ───────────────────────────

def compute_volume_ratio(daily_candles: list[dict[str, Any]]) -> Optional[float]:
    """Last day's volume vs the average of the prior 7 daily volumes."""
    volumes = [c["volume"] for c in daily_candles]
    if len(volumes) < 8:
        return None
    prior = volumes[-8:-1]
    avg = sum(prior) / len(prior)
    if avg <= 0:
        return None
    return volumes[-1] / avg


def _gather_volume_surges() -> list[dict[str, Any]]:
    """Rank the top-N USDT perps by 24h volume and compute each one's ratio
    vs its own 7d average (one 1D-candle call per symbol, N ≤ SCANNER_UNIVERSE)."""
    from crypto_feed import _okx_get, fetch_candles

    data = _okx_get("tickers", {"instType": "SWAP"})
    usdt = [d for d in data if str(d.get("instId", "")).endswith("-USDT-SWAP")]
    usdt.sort(key=lambda d: float(d.get("volCcy24h") or 0), reverse=True)

    surges = []
    for item in usdt[:SCANNER_UNIVERSE]:
        symbol = item["instId"].replace("-USDT-SWAP", "") + "USDT"
        try:
            candles = fetch_candles(symbol, bar="1D", limit=9)
            ratio = compute_volume_ratio(candles)
        except Exception as exc:  # noqa: BLE001
            logger.debug("volume ratio fetch failed for %s: %s", symbol, exc)
            continue
        if ratio is None:
            continue
        surges.append({
            "symbol": symbol,
            "volume_ratio": round(ratio, 2),
            "volume_24h_usdt": float(item.get("volCcy24h") or 0),
            "last_price": float(item.get("last") or 0),
        })
    return surges


# ─────────────────────────── mention surge (StockTwits) ───────────────────────────

def fetch_mention_rate(symbol: str) -> Optional[dict[str, Any]]:
    """Messages-per-hour for a crypto symbol from the public StockTwits stream
    (symbol BTC → stream BTC.X). The stream returns the latest 30 messages; the
    rate is 30 / hours-spanned."""
    resp = requests.get(
        f"https://api.stocktwits.com/api/2/streams/symbol/{symbol.upper()}.X.json",
        timeout=STOCKTWITS_TIMEOUT, headers={"User-Agent": "Sooppiy/1.0"})
    if resp.status_code != 200:
        return None
    body = resp.json() or {}
    messages = body.get("messages") or []
    if len(messages) < 2:
        return None
    times = []
    for m in messages:
        try:
            times.append(datetime.fromisoformat(str(m["created_at"]).replace("Z", "+00:00")))
        except (KeyError, ValueError):
            continue
    if len(times) < 2:
        return None
    span_hours = abs((max(times) - min(times)).total_seconds()) / 3600
    if span_hours <= 0:
        return None
    return {
        "symbol": symbol.upper(),
        "rate_per_hour": round(len(messages) / span_hours, 2),
        "watchers": ((body.get("symbol") or {}).get("watchlist_count")),
    }


def _mention_baselines(cursor) -> dict[str, list[float]]:
    """Per symbol, the mention rates stored in prior snapshots (oldest first)."""
    cursor.execute(
        """SELECT mentions_json FROM scanner_snapshots
           ORDER BY created_at DESC, id DESC LIMIT 24""")
    baselines: dict[str, list[float]] = {}
    for row in cursor.fetchall():
        try:
            mentions = json.loads(row["mentions_json"] or "[]")
        except ValueError:
            continue
        for m in mentions:
            if m.get("rate_per_hour") is not None:
                baselines.setdefault(m["symbol"], []).append(float(m["rate_per_hour"]))
    return baselines


def compute_mention_surges(current: list[dict[str, Any]],
                           baselines: dict[str, list[float]]) -> list[dict[str, Any]]:
    """Change % of each symbol's mention rate vs its stored baseline average."""
    surges = []
    for m in current:
        history = baselines.get(m["symbol"], [])
        if len(history) < MENTION_MIN_BASELINE:
            continue
        baseline = sum(history) / len(history)
        if baseline <= 0:
            continue
        change_pct = (m["rate_per_hour"] - baseline) / baseline * 100
        surges.append({**m, "baseline_rate": round(baseline, 2),
                       "change_pct": round(change_pct, 1)})
    return surges


# ─────────────────────────── new listings ───────────────────────────

def fetch_swap_instruments() -> list[str]:
    """All OKX SWAP instrument IDs (USDT and USD margined)."""
    from crypto_feed import OKX_PUBLIC_BASE, _okx_get
    data = _okx_get("instruments", {"instType": "SWAP"}, base=OKX_PUBLIC_BASE)
    return sorted(str(d["instId"]) for d in data if d.get("instId"))


def compute_new_listings(current: list[str], previous: list[str]) -> list[str]:
    return sorted(set(current) - set(previous)) if previous else []


# ─────────────────────────── whale interface (Phase 6 stub) ───────────────────────────

def fetch_whale_signals() -> list[dict[str, Any]]:
    """On-chain whale flows need a paid source (Hashdive-class API) — deferred
    to Phase 6. Interface: [{"symbol", "direction": "in|out", "usd_value",
    "reason"}]. Returns [] until a provider is wired in."""
    return []


# ─────────────────────────── candidate assembly ───────────────────────────

def assemble_candidates(volume_surges: list[dict[str, Any]],
                        mention_surges: list[dict[str, Any]],
                        new_listings: list[str],
                        whale_signals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge the sources into ranked candidates, each with plain-language reasons."""
    by_symbol: dict[str, dict[str, Any]] = {}

    def entry(symbol: str) -> dict[str, Any]:
        return by_symbol.setdefault(symbol, {"symbol": symbol, "score": 0.0,
                                             "reasons": [], "signals": {}})

    for v in volume_surges:
        if v["volume_ratio"] >= VOLUME_SURGE_RATIO:
            c = entry(v["symbol"])
            c["score"] += v["volume_ratio"]
            c["signals"]["volume_ratio"] = v["volume_ratio"]
            c["reasons"].append(f"volume x{v['volume_ratio']} vs 7d avg")

    for m in mention_surges:
        if m["change_pct"] >= MENTION_SURGE_PCT:
            symbol = f"{m['symbol']}USDT" if not m["symbol"].endswith("USDT") else m["symbol"]
            c = entry(symbol)
            c["score"] += 1 + m["change_pct"] / 100
            c["signals"]["mention_change_pct"] = m["change_pct"]
            c["reasons"].append(f"mentions +{m['change_pct']:.0f}%/h on StockTwits")

    for inst_id in new_listings:
        symbol = inst_id.replace("-USDT-SWAP", "USDT").replace("-USD-SWAP", "USD")
        c = entry(symbol)
        c["score"] += 2
        c["signals"]["new_listing"] = True
        c["reasons"].append(f"newly listed on OKX ({inst_id})")

    for w in whale_signals:  # Phase 6 — empty today, interface already consumed
        c = entry(w["symbol"])
        c["score"] += 1.5
        c["signals"]["whale"] = w
        c["reasons"].append(w.get("reason") or "whale flow")

    candidates = sorted(by_symbol.values(), key=lambda c: c["score"], reverse=True)
    for c in candidates:
        c["score"] = round(c["score"], 2)
    return candidates


# ─────────────────────────── snapshot refresh + payload ───────────────────────────

def refresh_scanner_snapshot() -> dict[str, Any]:
    """Run one full scan and persist the snapshot. Each source fails soft."""
    created_at = _utc_now_iso_z()
    snapshot_key = f"scanner:{created_at}"
    errors: dict[str, str] = {}

    volume_surges: list[dict[str, Any]] = []
    try:
        volume_surges = _gather_volume_surges()
    except Exception as exc:  # noqa: BLE001
        errors["volume"] = str(exc)

    mentions: list[dict[str, Any]] = []
    for symbol in MENTION_SYMBOLS:
        try:
            rate = fetch_mention_rate(symbol)
            if rate:
                mentions.append(rate)
        except Exception as exc:  # noqa: BLE001
            errors[f"mentions:{symbol}"] = str(exc)

    instruments: list[str] = []
    try:
        instruments = fetch_swap_instruments()
    except Exception as exc:  # noqa: BLE001
        errors["instruments"] = str(exc)

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        baselines = _mention_baselines(cursor)
        cursor.execute(
            """SELECT instruments_json FROM scanner_snapshots
               ORDER BY created_at DESC, id DESC LIMIT 1""")
        row = cursor.fetchone()
        previous_instruments = json.loads(row["instruments_json"] or "[]") if row else []

        mention_surges = compute_mention_surges(mentions, baselines)
        new_listings = compute_new_listings(instruments, previous_instruments) if instruments else []
        candidates = assemble_candidates(volume_surges, mention_surges,
                                         new_listings, fetch_whale_signals())

        cursor.execute(
            """INSERT INTO scanner_snapshots
               (snapshot_key, candidates_json, mentions_json, instruments_json, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (snapshot_key, json.dumps(candidates, ensure_ascii=True),
             json.dumps(mentions, ensure_ascii=True),
             json.dumps(instruments, ensure_ascii=True), created_at),
        )
        # Two-step prune: MySQL rejects both LIMIT-in-IN-subquery (1235) and
        # selecting from the DELETE target (1093), so pick the cutoff first.
        cursor.execute(
            """SELECT id FROM scanner_snapshots
               ORDER BY created_at DESC, id DESC LIMIT 1 OFFSET ?""",
            (SCANNER_HISTORY_LIMIT - 1,),
        )
        cutoff = cursor.fetchone()
        if cutoff:
            cursor.execute("DELETE FROM scanner_snapshots WHERE id < ?", (cutoff["id"],))
        conn.commit()
    finally:
        conn.close()

    try:
        from cache import delete
        delete(_CACHE_KEY)
    except Exception:  # noqa: BLE001
        pass

    return {"snapshot_key": snapshot_key, "created_at": created_at,
            "candidates": len(candidates), "volume_symbols": len(volume_surges),
            "mention_symbols": len(mentions), "instruments": len(instruments),
            "new_listings": new_listings, "errors": errors}


def get_scanner_payload() -> dict[str, Any]:
    """Latest scan's ranked candidates with reasons."""
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
            """SELECT candidates_json, created_at FROM scanner_snapshots
               ORDER BY created_at DESC, id DESC LIMIT 1""")
        row = cursor.fetchone()
    finally:
        conn.close()

    if not row:
        return {"available": False, "candidates": [], "created_at": None,
                "note": "no scan has run yet (SCANNER_ENABLED off or warming up)"}

    payload = {
        "available": True,
        "candidates": json.loads(row["candidates_json"] or "[]"),
        "created_at": row["created_at"],
        "sources": ["okx volume ratio (24h vs 7d avg)",
                    "stocktwits mention rate vs stored baseline",
                    "okx new listings", "whale flows (Phase 6, not wired)"],
    }
    try:
        from cache import set_json
        set_json(_CACHE_KEY, payload, ttl_seconds=_CACHE_TTL_SECONDS)
    except Exception:  # noqa: BLE001
        pass
    return payload


def top_candidate() -> Optional[str]:
    """Symbol of the current top-ranked candidate (for automation rules whose
    symbol is set to 'SCANNER'). Trims the USDT/USD suffix — automation/crypto
    symbols are base assets ('BTC'). Returns None when the latest scan is
    stale (older than 2× the scan interval) so a dead scanner can't keep
    feeding the same candidate to automation forever."""
    payload = get_scanner_payload()
    candidates = payload.get("candidates") or []
    if not candidates:
        return None
    created_at = payload.get("created_at")
    if created_at:
        try:
            scanned = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
            if scanned.tzinfo is None:  # SQLite datetime('now') is naive UTC
                scanned = scanned.replace(tzinfo=timezone.utc)
            interval_s = max(300, int(os.environ.get("SCANNER_INTERVAL", "3600")))
            if (datetime.now(timezone.utc) - scanned).total_seconds() > 2 * interval_s:
                return None
        except (TypeError, ValueError):
            pass
    symbol = str(candidates[0]["symbol"])
    for suffix in ("USDT", "USD"):
        if symbol.endswith(suffix) and len(symbol) > len(suffix):
            return symbol[:-len(suffix)]
    return symbol
