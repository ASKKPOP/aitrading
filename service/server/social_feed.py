"""Social collection service (Plan 11 F5).

Every SOCIAL_REFRESH_INTERVAL seconds (default 30 min) this collects public
posts about the desk's tracked symbols and turns them into a per-symbol
sentiment snapshot the analysis pipeline can read.

Platform routing is regional, per Henry's spec: South-East Asia is collected
from Facebook, everywhere else from X. Region comes from SOCIAL_REGIONS
(default "sea,global"); each region maps to one platform.

Sourcing rules:
  * Official APIs only — X API v2 recent search (X_BEARER_TOKEN) and the
    Facebook Graph API (FACEBOOK_ACCESS_TOKEN). No scraping and no logged-in
    session reuse: both platforms' terms forbid it, and a scraper would break
    on every markup change anyway.
  * Missing credentials disable that platform quietly; the other still runs.
  * A region whose primary platform has no credentials falls back to the
    keyless public StockTwits stream, so the service produces real signal
    before X (paid plan) and Facebook (app review) are set up. Disable with
    SOCIAL_KEYLESS_FALLBACK=false to collect strictly from FB/X.

Retention: raw posts are kept SOCIAL_RAW_RETENTION_DAYS (default 7) and pruned
at the end of every cycle. The derived snapshots are small and kept longer so
sentiment history survives the raw-data window.

Scoring is deterministic keyword polarity — no LLM call per post. That keeps a
30-minute cycle cheap and the score reproducible; the analysts read the
aggregate, and the LLM reasoning happens once in the analysis pipeline.

Gated by SOCIAL_FEED_ENABLED (default off). Every fetch fails soft: one dead
platform still yields a partial snapshot.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import requests

from database import get_db_connection

logger = logging.getLogger(__name__)

SOCIAL_TIMEOUT = 10
SNAPSHOT_KEY = "social:latest"
_CACHE_KEY = "sooppiy:social:payload"
_CACHE_TTL_SECONDS = 300
MAX_POSTS_PER_QUERY = 50
SNAPSHOT_HISTORY_LIMIT = 500

# Region → platform. SEA reads Facebook, everywhere else reads X.
REGION_PLATFORM: dict[str, str] = {"sea": "facebook", "global": "x"}

# Deterministic polarity lexicon. Small on purpose: it scores retail crypto
# chatter, where the vocabulary is narrow and slang-heavy.
_POSITIVE = {
    "bull", "bullish", "long", "buy", "buying", "moon", "pump", "rally", "breakout",
    "support", "accumulate", "undervalued", "gain", "gains", "profit", "up", "surge",
    "strong", "green", "hold", "hodl", "ath",
}
_NEGATIVE = {
    "bear", "bearish", "short", "sell", "selling", "dump", "crash", "correction",
    "resistance", "overvalued", "loss", "losses", "down", "drop", "weak", "red",
    "liquidated", "rug", "scam", "capitulation", "fear",
}


def social_feed_enabled() -> bool:
    return os.getenv("SOCIAL_FEED_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}


def _regions() -> list[str]:
    raw = os.getenv("SOCIAL_REGIONS", "sea,global")
    return [r.strip().lower() for r in raw.split(",") if r.strip().lower() in REGION_PLATFORM]


def _retention_days() -> int:
    try:
        return max(1, int(os.getenv("SOCIAL_RAW_RETENTION_DAYS", "7")))
    except ValueError:
        return 7


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def tracked_symbols() -> list[str]:
    """Topics to collect: the current top-5 universe, else the majors."""
    try:
        from top_symbols import get_top_symbols
        syms = [t["symbol"].removesuffix("USDT") for t in get_top_symbols()]
        if syms:
            return syms
    except Exception:  # noqa: BLE001
        pass
    return ["BTC", "ETH", "SOL"]


# ── scoring ───────────────────────────────────────────────────────────────────

def score_post(post: dict[str, Any]) -> int:
    """Polarity for one post. A sentiment the author declared explicitly
    (StockTwits Bullish/Bearish tags) beats inferring it from wording."""
    declared = (post.get("declared_sentiment") or "").strip().lower()
    if declared == "bullish":
        return 1
    if declared == "bearish":
        return -1
    return score_text(post.get("text") or "")


def score_text(text: str) -> int:
    """+1 / 0 / -1 polarity for one post."""
    words = {w.strip(".,!?:;()[]#\"'").lower() for w in (text or "").split()}
    pos = len(words & _POSITIVE)
    neg = len(words & _NEGATIVE)
    if pos > neg:
        return 1
    if neg > pos:
        return -1
    return 0


# ── collectors ────────────────────────────────────────────────────────────────

def fetch_x_posts(symbol: str) -> list[dict[str, Any]]:
    """Recent public X posts mentioning the symbol (X API v2 recent search)."""
    bearer = os.getenv("X_BEARER_TOKEN", "").strip()
    if not bearer:
        return []
    resp = requests.get(
        "https://api.x.com/2/tweets/search/recent",
        params={
            "query": f"({symbol} OR #{symbol}) -is:retweet lang:en",
            "max_results": MAX_POSTS_PER_QUERY,
            "tweet.fields": "created_at,public_metrics,lang",
        },
        headers={"Authorization": f"Bearer {bearer}"},
        timeout=SOCIAL_TIMEOUT,
    )
    if resp.status_code != 200:
        logger.warning("X search failed for %s: HTTP %s", symbol, resp.status_code)
        return []
    body = resp.json() or {}
    posts = []
    for item in body.get("data") or []:
        posts.append({
            "platform": "x",
            "post_id": str(item.get("id")),
            "author": None,  # author ids need an expansion; not needed for polarity
            "text": item.get("text") or "",
            "engagement": item.get("public_metrics") or {},
            "posted_at": item.get("created_at"),
        })
    return posts


def fetch_facebook_posts(symbol: str) -> list[dict[str, Any]]:
    """Recent posts from the configured public Facebook pages (Graph API).

    Facebook has no public keyword search, so SOCIAL_FACEBOOK_PAGES lists the
    page ids to read; posts are then filtered for the symbol client-side.
    """
    token = os.getenv("FACEBOOK_ACCESS_TOKEN", "").strip()
    pages = [p.strip() for p in os.getenv("SOCIAL_FACEBOOK_PAGES", "").split(",") if p.strip()]
    if not token or not pages:
        return []
    version = os.getenv("FACEBOOK_API_VERSION", "v21.0").strip()
    needle = symbol.lower()
    posts: list[dict[str, Any]] = []
    for page in pages:
        try:
            resp = requests.get(
                f"https://graph.facebook.com/{version}/{page}/posts",
                params={"fields": "id,message,created_time,shares,comments.summary(true)",
                        "limit": MAX_POSTS_PER_QUERY, "access_token": token},
                timeout=SOCIAL_TIMEOUT,
            )
            if resp.status_code != 200:
                logger.warning("Facebook page %s failed: HTTP %s", page, resp.status_code)
                continue
            for item in (resp.json() or {}).get("data") or []:
                message = item.get("message") or ""
                if needle not in message.lower():
                    continue
                posts.append({
                    "platform": "facebook",
                    "post_id": str(item.get("id")),
                    "author": page,
                    "text": message,
                    "engagement": {
                        "shares": (item.get("shares") or {}).get("count", 0),
                        "comments": ((item.get("comments") or {}).get("summary") or {}).get("total_count", 0),
                    },
                    "posted_at": item.get("created_time"),
                })
        except Exception as exc:  # noqa: BLE001 — one bad page must not kill the cycle
            logger.warning("Facebook page %s errored: %s", page, exc)
    return posts


def fetch_stocktwits_posts(symbol: str) -> list[dict[str, Any]]:
    """Public StockTwits stream — the keyless fallback.

    X's API needs a paid plan and Facebook needs an app review, so until those
    credentials exist a region would collect nothing at all. StockTwits is
    public, needs no auth, and is already trusted elsewhere in this codebase
    (scanner.py mention rates, analysis_sources.py sentiment). Its messages
    also carry an explicit Bullish/Bearish tag, which beats keyword scoring
    when present.
    """
    resp = requests.get(
        f"https://api.stocktwits.com/api/2/streams/symbol/{symbol.upper()}.X.json",
        timeout=SOCIAL_TIMEOUT, headers={"User-Agent": "Sooppiy/1.0"})
    if resp.status_code != 200:
        logger.warning("StockTwits stream failed for %s: HTTP %s", symbol, resp.status_code)
        return []
    posts = []
    for item in (resp.json() or {}).get("messages") or []:
        tag = ((item.get("entities") or {}).get("sentiment") or {}).get("basic")
        posts.append({
            "platform": "stocktwits",
            "post_id": str(item.get("id")),
            "author": ((item.get("user") or {}).get("username")),
            "text": item.get("body") or "",
            "engagement": (item.get("likes") or {}),
            "posted_at": item.get("created_at"),
            # 'Bullish' / 'Bearish' when the poster tagged it, else None
            "declared_sentiment": tag,
        })
    return posts


_COLLECTORS = {"x": fetch_x_posts, "facebook": fetch_facebook_posts,
               "stocktwits": fetch_stocktwits_posts}

# Credentials each platform needs before it can collect anything.
_PLATFORM_CREDS = {
    "x": ("X_BEARER_TOKEN",),
    "facebook": ("FACEBOOK_ACCESS_TOKEN", "SOCIAL_FACEBOOK_PAGES"),
    "stocktwits": (),  # public API, no credentials
}


def platform_configured(platform: str) -> bool:
    return all(os.getenv(env, "").strip() for env in _PLATFORM_CREDS.get(platform, ()))


def _keyless_fallback_enabled() -> bool:
    return os.getenv("SOCIAL_KEYLESS_FALLBACK", "true").strip().lower() in {"1", "true", "yes", "on"}


def platform_for_region(region: str) -> Optional[str]:
    """The platform a region collects from: its configured primary, else the
    keyless fallback, else None (nothing usable)."""
    primary = REGION_PLATFORM.get(region)
    if primary and platform_configured(primary):
        return primary
    return "stocktwits" if _keyless_fallback_enabled() else None


# ── persistence ───────────────────────────────────────────────────────────────

def _store_posts(cursor, region: str, symbol: str, posts: list[dict[str, Any]]) -> int:
    """Insert posts, skipping ones already stored (unique platform+post_id)."""
    stored = 0
    now = _now_iso()
    for post in posts:
        try:
            cursor.execute(
                """INSERT INTO social_posts
                   (platform, region, topic, post_id, author, text, engagement_json,
                    posted_at, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (post["platform"], region, symbol, post["post_id"], post.get("author"),
                 (post.get("text") or "")[:4000],
                 json.dumps(post.get("engagement") or {}, ensure_ascii=False),
                 post.get("posted_at"), now))
            stored += 1
        except Exception:  # noqa: BLE001 — duplicate post_id is the expected case
            continue
    return stored


def prune_old_posts(cursor) -> int:
    """Drop raw posts past the retention window (default 7 days)."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=_retention_days())
              ).strftime("%Y-%m-%dT%H:%M:%SZ")
    cursor.execute("SELECT COUNT(*) AS n FROM social_posts WHERE created_at < ?", (cutoff,))
    row = cursor.fetchone()
    doomed = int((dict(row) if row else {}).get("n", 0) or 0)
    if doomed:
        cursor.execute("DELETE FROM social_posts WHERE created_at < ?", (cutoff,))
    return doomed


def _prune_snapshots(cursor) -> None:
    cursor.execute(
        """SELECT id FROM social_snapshots ORDER BY created_at DESC LIMIT 1 OFFSET ?""",
        (SNAPSHOT_HISTORY_LIMIT,))
    rows = cursor.fetchall()
    if not rows:
        return
    ids = [r["id"] for r in rows]
    cursor.execute(f"DELETE FROM social_snapshots WHERE id IN ({','.join('?' for _ in ids)})", ids)


# ── cycle ─────────────────────────────────────────────────────────────────────

def refresh_social_snapshot() -> dict[str, Any]:
    """One collection cycle: fetch → store → aggregate → snapshot → prune."""
    symbols = tracked_symbols()
    regions = _regions()
    errors: list[str] = []
    per_symbol: dict[str, dict[str, Any]] = {}
    fetched = stored = 0

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        for symbol in symbols:
            scores: list[int] = []
            platforms: dict[str, int] = {}
            done: set[str] = set()
            for region in regions:
                platform = platform_for_region(region)
                # Regions whose primary is unconfigured share one fallback
                # platform — collect it once, not once per region.
                if not platform or platform in done:
                    continue
                done.add(platform)
                try:
                    posts = _COLLECTORS[platform](symbol)
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"{platform}:{symbol}:{exc}")
                    continue
                if not posts:
                    continue
                fetched += len(posts)
                stored += _store_posts(cursor, region, symbol, posts)
                platforms[platform] = platforms.get(platform, 0) + len(posts)
                scores.extend(score_post(p) for p in posts)

            if scores:
                tilt = sum(scores) / len(scores)
                per_symbol[symbol] = {
                    "posts": len(scores),
                    "tilt": round(tilt, 3),
                    "label": "bullish" if tilt > 0.15 else "bearish" if tilt < -0.15 else "neutral",
                    "platforms": platforms,
                }

        summary = {
            "as_of": _now_iso(),
            "regions": regions,
            "symbols": per_symbol,
            "posts_fetched": fetched,
            "posts_stored": stored,
        }
        cursor.execute(
            """INSERT INTO social_snapshots (snapshot_key, summary_json, created_at)
               VALUES (?, ?, ?)""",
            (SNAPSHOT_KEY, json.dumps(summary, ensure_ascii=False), _now_iso()))
        pruned = prune_old_posts(cursor)
        _prune_snapshots(cursor)
        conn.commit()
    finally:
        conn.close()

    try:
        from cache import set_json
        set_json(_CACHE_KEY, summary, _CACHE_TTL_SECONDS)
    except Exception:  # noqa: BLE001
        pass

    summary["posts_pruned"] = pruned
    summary["errors"] = errors
    return summary


def get_social_payload() -> dict[str, Any]:
    """Latest snapshot for the analysis pipeline and API. Fail-soft."""
    try:
        from cache import get_json
        cached = get_json(_CACHE_KEY)
        if isinstance(cached, dict):
            return {"available": True, **cached}
    except Exception:  # noqa: BLE001
        pass
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """SELECT summary_json, created_at FROM social_snapshots
               WHERE snapshot_key = ? ORDER BY created_at DESC LIMIT 1""", (SNAPSHOT_KEY,))
        row = cursor.fetchone()
        conn.close()
        if not row:
            return {"available": False}
        return {"available": True, **json.loads(row["summary_json"] or "{}")}
    except Exception as exc:  # noqa: BLE001
        logger.warning("social payload read failed: %s", exc)
        return {"available": False}


def social_sentiment_for(symbol: str) -> Optional[dict[str, Any]]:
    """The stored social tilt for one symbol, or None when uncollected."""
    payload = get_social_payload()
    if not payload.get("available"):
        return None
    entry = (payload.get("symbols") or {}).get((symbol or "").upper())
    if not entry:
        return None
    return {**entry, "as_of": payload.get("as_of")}
