"""Tier-4 human-fact collection — ONE service for the crowd's own behavior.

Owner direction (2026-08-24, Research 07 §9): the collection pillar must carry
a human-factor fact class, expanded in real time beyond StockTwits — and the
Sooppiy AI must be able to read it when it makes a decision. This module is
that single service. It covers the Tier-4 sources selected by the owner:

  * telegram — public-channel audience size via the Bot API
    (getChatMemberCount; the Bot API cannot read channel history without
    admin rights, so message velocity is deliberately NOT faked from it).
  * youtube  — finance-channel activity via the Data API v3
    (subscribers, uploads in the last 24h from the uploads playlist —
    1-unit endpoints only; the 100-unit search endpoint is never called).
  * discord  — message velocity in public servers the bot has been invited
    to (messages/hour and unique authors over the last hour).
  * naver    — Korean retail attention via the official DataLab search-trend
    API (relative search index per symbol keyword group, and its 1-day
    delta). The 종목토론실 board is NOT scraped: official APIs only, the
    same rule social_feed.py ships under.
  * tiktok   — registered but UNAVAILABLE: there is no practical public API
    for the readings we need; the source reports itself unconfigured rather
    than pretending. Revisit only if an official API appears.

Contract (the desk_reference pattern, test-enforced):

  * FACTS ONLY. Every reading is a number with a source, a scope, and a
    timestamp — counts, deltas, indices. The service never writes a verdict
    word ("bullish", "bearish") and the rendered line never grows an
    instruction. What the readings mean is the AI's call (§7b).
  * KEY-GATED PER SOURCE. A source without its credentials is skipped
    silently; the whole service is a no-op unless HUMAN_FACTS_ENABLED.
    Official APIs only — no scraping, no logged-in sessions.
  * FAIL-SOFT. One dead source never blocks another; a broken table never
    costs a trading cycle a decision.

Configuration:

  HUMAN_FACTS_ENABLED           master switch (default off)
  HUMAN_FACTS_INTERVAL          collection cadence seconds (default 300,
                                minimum 60 — the "real time" the sources
                                actually support without burning quotas)
  HUMAN_FACTS_CHANNELS          JSON: {"telegram": ["@chan"],
                                "youtube": ["UC..."], "discord": ["1234"]}
  HUMAN_FACTS_NAVER_KEYWORDS    JSON: {"BTCUSDT": ["비트코인"], ...}
  HUMAN_FACTS_RETENTION_DAYS    raw-fact retention (default 14)
  TELEGRAM_BOT_TOKEN / YOUTUBE_API_KEY / DISCORD_BOT_TOKEN /
  NAVER_CLIENT_ID + NAVER_CLIENT_SECRET   per-source credentials (owner)
"""
from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import requests

_REQUEST_TIMEOUT = 10

# ── config ─────────────────────────────────────────────────────────────────


def human_facts_enabled() -> bool:
    return (os.getenv("HUMAN_FACTS_ENABLED", "0") or "0").strip().lower() in (
        "1", "true", "yes", "on")


def _interval_s() -> int:
    try:
        return max(60, int(os.getenv("HUMAN_FACTS_INTERVAL", "300")))
    except ValueError:
        return 300


def _retention_days() -> int:
    try:
        return max(1, int(os.getenv("HUMAN_FACTS_RETENTION_DAYS", "14")))
    except ValueError:
        return 14


def _channels(source: str) -> list[str]:
    try:
        raw = json.loads(os.getenv("HUMAN_FACTS_CHANNELS", "") or "{}")
        vals = raw.get(source) or []
        return [str(v).strip() for v in vals if str(v).strip()]
    except Exception:  # noqa: BLE001
        return []


def _naver_keywords() -> dict[str, list[str]]:
    try:
        raw = json.loads(os.getenv("HUMAN_FACTS_NAVER_KEYWORDS", "") or "{}")
        return {str(k).strip().upper(): [str(w) for w in v if str(w).strip()]
                for k, v in raw.items() if v}
    except Exception:  # noqa: BLE001
        return {}


# Source registry: name -> env vars that must ALL be non-empty for the
# source to be considered configured. tiktok maps to an impossible sentinel
# on purpose — it is registered so the admin surface can say WHY it is off.
_SOURCE_KEYS: dict[str, tuple[str, ...]] = {
    "telegram": ("TELEGRAM_BOT_TOKEN",),
    "youtube": ("YOUTUBE_API_KEY",),
    "discord": ("DISCORD_BOT_TOKEN",),
    "naver": ("NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET"),
    "tiktok": ("TIKTOK_NO_PUBLIC_API",),   # deliberately unsatisfiable
}


def source_configured(source: str) -> bool:
    keys = _SOURCE_KEYS.get(source)
    if not keys:
        return False
    return all((os.getenv(k, "") or "").strip() for k in keys)


# ── HTTP (fail-soft) ───────────────────────────────────────────────────────


def _http_json(method: str, url: str, *, headers: dict | None = None,
               params: dict | None = None,
               body: dict | None = None) -> Optional[dict]:
    try:
        resp = requests.request(method, url, headers=headers, params=params,
                                json=body, timeout=_REQUEST_TIMEOUT)
        if resp.status_code != 200:
            return None
        return resp.json()
    except Exception:  # noqa: BLE001
        return None


# ── collectors — each returns [{scope, metric, value, meta}] ───────────────


def collect_telegram() -> list[dict[str, Any]]:
    token = (os.getenv("TELEGRAM_BOT_TOKEN", "") or "").strip()
    facts: list[dict[str, Any]] = []
    for chan in _channels("telegram"):
        chat_id = chan if chan.startswith("@") else f"@{chan}"
        data = _http_json(
            "GET",
            f"https://api.telegram.org/bot{token}/getChatMemberCount",
            params={"chat_id": chat_id})
        if data and data.get("ok") and isinstance(data.get("result"), int):
            facts.append({"scope": f"telegram:{chat_id}", "metric": "members",
                          "value": float(data["result"]), "meta": None})
    return facts


def collect_youtube() -> list[dict[str, Any]]:
    key = (os.getenv("YOUTUBE_API_KEY", "") or "").strip()
    facts: list[dict[str, Any]] = []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    for chan in _channels("youtube"):
        info = _http_json(
            "GET", "https://www.googleapis.com/youtube/v3/channels",
            params={"part": "statistics,contentDetails", "id": chan,
                    "key": key})
        items = (info or {}).get("items") or []
        if not items:
            continue
        stats = items[0].get("statistics") or {}
        try:
            facts.append({"scope": f"youtube:{chan}", "metric": "subscribers",
                          "value": float(stats.get("subscriberCount", 0)),
                          "meta": None})
        except (TypeError, ValueError):
            pass
        uploads = (((items[0].get("contentDetails") or {})
                    .get("relatedPlaylists") or {}).get("uploads"))
        if not uploads:
            continue
        plist = _http_json(
            "GET", "https://www.googleapis.com/youtube/v3/playlistItems",
            params={"part": "contentDetails", "playlistId": uploads,
                    "maxResults": 20, "key": key})
        n = 0
        for it in (plist or {}).get("items") or []:
            ts = ((it.get("contentDetails") or {})
                  .get("videoPublishedAt") or "")
            try:
                if datetime.fromisoformat(ts.replace("Z", "+00:00")) >= cutoff:
                    n += 1
            except ValueError:
                continue
        facts.append({"scope": f"youtube:{chan}", "metric": "uploads_24h",
                      "value": float(n), "meta": None})
    return facts


def collect_discord() -> list[dict[str, Any]]:
    token = (os.getenv("DISCORD_BOT_TOKEN", "") or "").strip()
    facts: list[dict[str, Any]] = []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
    for chan in _channels("discord"):
        msgs = _http_json(
            "GET", f"https://discord.com/api/v10/channels/{chan}/messages",
            headers={"Authorization": f"Bot {token}"},
            params={"limit": 100})
        if not isinstance(msgs, list):
            continue
        recent, authors = 0, set()
        for m in msgs:
            ts = str(m.get("timestamp") or "")
            try:
                if datetime.fromisoformat(ts) >= cutoff:
                    recent += 1
                    authors.add((m.get("author") or {}).get("id"))
            except ValueError:
                continue
        facts.append({"scope": f"discord:{chan}", "metric": "msgs_per_hr",
                      "value": float(recent), "meta": None})
        facts.append({"scope": f"discord:{chan}", "metric": "authors_per_hr",
                      "value": float(len(authors)), "meta": None})
    return facts


def collect_naver() -> list[dict[str, Any]]:
    cid = (os.getenv("NAVER_CLIENT_ID", "") or "").strip()
    sec = (os.getenv("NAVER_CLIENT_SECRET", "") or "").strip()
    keywords = _naver_keywords()
    if not keywords:
        return []
    today = datetime.now(timezone.utc).date()
    body = {
        "startDate": (today - timedelta(days=7)).isoformat(),
        "endDate": today.isoformat(),
        "timeUnit": "date",
        "keywordGroups": [{"groupName": sym, "keywords": words[:5]}
                          for sym, words in list(keywords.items())[:5]],
    }
    data = _http_json(
        "POST", "https://openapi.naver.com/v1/datalab/search",
        headers={"X-Naver-Client-Id": cid, "X-Naver-Client-Secret": sec,
                 "Content-Type": "application/json"},
        body=body)
    facts: list[dict[str, Any]] = []
    for group in (data or {}).get("results") or []:
        sym = str(group.get("title") or "").upper()
        series = group.get("data") or []
        if not sym or not series:
            continue
        last = series[-1].get("ratio")
        prev = series[-2].get("ratio") if len(series) > 1 else None
        if last is None:
            continue
        facts.append({"scope": sym, "metric": "naver_search_idx",
                      "value": float(last), "meta": None})
        if prev is not None:
            facts.append({"scope": sym, "metric": "naver_search_idx_d1",
                          "value": float(last) - float(prev), "meta": None})
    return facts


def collect_tiktok() -> list[dict[str, Any]]:
    """No practical public API for message/attention velocity — returns
    nothing, on purpose. A fact source that cannot be collected officially
    reports itself unconfigured instead of inventing numbers."""
    return []


_COLLECTORS = {
    "telegram": collect_telegram,
    "youtube": collect_youtube,
    "discord": collect_discord,
    "naver": collect_naver,
    "tiktok": collect_tiktok,
}


# ── storage ────────────────────────────────────────────────────────────────


def _bucket(now: Optional[float] = None) -> str:
    """Collection bucket key — ts floored to the interval, so re-running a
    collection inside one interval upserts instead of duplicating."""
    t = int(now if now is not None else time.time())
    step = _interval_s()
    return datetime.fromtimestamp((t // step) * step,
                                  tz=timezone.utc).isoformat()


def _store(cursor, source: str, facts: list[dict[str, Any]],
           bucket: str) -> int:
    stored = 0
    now = datetime.now(timezone.utc).isoformat()
    for f in facts:
        try:
            value = float(f["value"])
        except (KeyError, TypeError, ValueError):
            continue
        scope = str(f.get("scope") or "global")
        metric = str(f.get("metric") or "")
        # DELETE+INSERT instead of INSERT OR REPLACE: the SQLite spelling
        # is not adapted for MySQL, and this pair is portable to both.
        cursor.execute(
            "DELETE FROM human_facts WHERE source = ? AND scope = ?"
            " AND metric = ? AND bucket = ?",
            (source, scope, metric, bucket))
        cursor.execute(
            """INSERT INTO human_facts
               (source, scope, metric, bucket, ts, value, meta)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (source, scope, metric, bucket, now, value,
             json.dumps(f.get("meta")) if f.get("meta") else None))
        stored += 1
    return stored


def collect_once() -> dict[str, Any]:
    """One collection pass over every configured source. Fail-soft per
    source; never raises."""
    if not human_facts_enabled():
        return {"skipped": "disabled"}
    from database import get_db_connection
    summary: dict[str, Any] = {"stored": 0, "errors": {}, "sources": []}
    bucket = _bucket()
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        for name, collector in _COLLECTORS.items():
            if not source_configured(name):
                continue
            summary["sources"].append(name)
            try:
                summary["stored"] += _store(cursor, name, collector(), bucket)
            except Exception as e:  # noqa: BLE001
                summary["errors"][name] = str(e)
        try:
            horizon = (datetime.now(timezone.utc)
                       - timedelta(days=_retention_days())).isoformat()
            cursor.execute("DELETE FROM human_facts WHERE ts < ?", (horizon,))
        except Exception:  # noqa: BLE001
            pass
        conn.commit()
    except Exception as e:  # noqa: BLE001
        summary["errors"]["db"] = str(e)
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass
    return summary


# ── read side (60s TTL cache — the loop refreshes far slower) ──────────────

_CACHE: dict[str, tuple[float, Any]] = {}
_CACHE_LOCK = threading.Lock()
_CACHE_TTL = 60


def _cached(key: str, build):
    with _CACHE_LOCK:
        hit = _CACHE.get(key)
        if hit and time.time() - hit[0] < _CACHE_TTL:
            return hit[1]
    val = build()
    with _CACHE_LOCK:
        _CACHE[key] = (time.time(), val)
    return val


def _fresh_rows(symbol: str, max_age_s: int = 3600) -> list[dict[str, Any]]:
    from database import get_db_connection
    horizon = (datetime.now(timezone.utc)
               - timedelta(seconds=max_age_s)).isoformat()
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        # Symbol-scoped rows (naver search index uses the bare symbol) plus
        # channel-scoped crowd rows (every channel scope contains ':').
        cursor.execute(
            """SELECT source, scope, metric, value, ts FROM human_facts
               WHERE ts >= ? AND (scope = ? OR scope LIKE '%:%')
               ORDER BY ts DESC LIMIT 200""",
            (horizon, str(symbol or "").upper()))
        rows, seen = [], set()
        for r in cursor.fetchall():
            key = (r["source"], r["scope"], r["metric"])
            if key in seen:
                continue
            seen.add(key)
            rows.append({"source": r["source"], "scope": r["scope"],
                         "metric": r["metric"], "value": r["value"],
                         "ts": r["ts"]})
        return rows
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass


def human_facts_payload(symbol: str) -> Optional[dict[str, Any]]:
    """Nested numeric payload for the analyst data dict. None when the
    service is off or nothing fresh exists — the caller drops the key."""
    if not human_facts_enabled():
        return None

    def _build():
        try:
            rows = _fresh_rows(symbol)
        except Exception:  # noqa: BLE001
            return None
        if not rows:
            return None
        out: dict[str, Any] = {}
        for r in rows:
            out.setdefault(r["source"], {})[
                f"{r['scope']}::{r['metric']}"] = r["value"]
        return out

    return _cached(f"payload:{str(symbol or '').upper()}", _build)


def human_facts_line(symbol: str, market: str) -> str:
    """One labelled brief line of measured crowd readings. Facts only —
    numbers with sources; no instruction, no verdict word. Empty when the
    service is off or nothing fresh exists, so wiring it costs nothing
    until the owner provisions keys."""
    if not human_facts_enabled():
        return ""

    def _build():
        try:
            rows = _fresh_rows(symbol)
        except Exception:  # noqa: BLE001
            return ""
        if not rows:
            return ""
        bits = []
        for r in rows[:8]:
            scope = r["scope"]
            label = scope.split(":", 1)[-1] if ":" in scope else scope
            try:
                val = (f"{int(r['value']):,}" if float(r["value"]).is_integer()
                       else f"{float(r['value']):.1f}")
            except (TypeError, ValueError):
                continue
            bits.append(f"{r['source']} {label} {r['metric']}={val}")
        if not bits:
            return ""
        return ("\nHUMAN FACTS (measured crowd readings, not advice): "
                + " · ".join(bits)
                + " — what they mean is your call.")

    return _cached(f"line:{str(symbol or '').upper()}", _build)
