"""crawl_monitor.py — bookkeeping for every crawl pass in the swing pipeline.

The admin console previously could only answer "does this upstream URL answer
right now?" (routes_admin_swing_feeds probes). That says nothing about what
our own collectors actually did: whether the last pass ran, how long it took,
how many rows it produced, or why it failed. This module records one
`crawl_runs` row per pass so the console can show the real crawl history.

Usage — wrap a collector pass:

    with crawl_monitor.track("filings") as run:
        rows = collect()
        run.items = len(rows)
        run.detail = {"symbols": symbols}

An exception inside the block is recorded (ok=0, error=...) and re-raised —
`track` never changes the caller's control flow. Bookkeeping failures of its
own are swallowed: monitoring must never break the crawler it monitors.
"""
from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator, Optional

import database

logger = logging.getLogger(__name__)

DEFAULT_RETENTION_DAYS = 14
_ERROR_MAX_CHARS = 500


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


@dataclass
class CrawlRun:
    """Mutable handle a crawler fills in while its pass runs."""

    feed: str
    items: int = 0
    detail: dict[str, Any] = field(default_factory=dict)


def _write(
    feed: str,
    started: datetime,
    finished: datetime,
    ok: bool,
    items: int,
    detail: Optional[dict[str, Any]],
    error: Optional[str],
) -> None:
    duration_ms = int((finished - started).total_seconds() * 1000)
    detail_json = None
    if detail:
        try:
            detail_json = json.dumps(detail, default=str)[:4000]
        except (TypeError, ValueError):
            detail_json = None
    with database.get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO crawl_runs
                (feed, started_at, finished_at, duration_ms, ok, items, detail, error)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                feed,
                _iso(started),
                _iso(finished),
                duration_ms,
                1 if ok else 0,
                int(items or 0),
                detail_json,
                (error or None) if error is None else error[:_ERROR_MAX_CHARS],
            ),
        )
        conn.commit()


@contextmanager
def track(feed: str) -> Iterator[CrawlRun]:
    """Record one crawl pass. Re-raises whatever the block raised."""
    run = CrawlRun(feed=feed)
    started = _utc_now()
    error: Optional[str] = None
    try:
        yield run
    except BaseException as exc:  # noqa: BLE001 — recorded, then re-raised
        error = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        try:
            _write(
                feed=feed,
                started=started,
                finished=_utc_now(),
                ok=error is None,
                items=run.items,
                detail=run.detail,
                error=error,
            )
        except Exception as exc:  # noqa: BLE001 — never break the crawler
            logger.warning("crawl_monitor could not record %s: %s", feed, exc)


def _row_to_dict(row: Any) -> dict[str, Any]:
    detail: dict[str, Any] = {}
    if row["detail"]:
        try:
            detail = json.loads(row["detail"])
        except (TypeError, ValueError):
            detail = {}
    return {
        "id": row["id"],
        "feed": row["feed"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
        "duration_ms": row["duration_ms"],
        "ok": bool(row["ok"]),
        "items": row["items"],
        "detail": detail,
        "error": row["error"],
    }


def recent_runs(feed: Optional[str] = None, limit: int = 50) -> list[dict[str, Any]]:
    """Newest-first crawl history, optionally for one feed."""
    limit = max(1, min(int(limit or 50), 500))
    sql = "SELECT * FROM crawl_runs"
    params: list[Any] = []
    if feed:
        sql += " WHERE feed = ?"
        params.append(feed)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    try:
        with database.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, tuple(params))
            return [_row_to_dict(r) for r in cursor.fetchall()]
    except Exception as exc:  # noqa: BLE001 — a console read must not 500
        logger.warning("crawl_monitor.recent_runs failed: %s", exc)
        return []


def feed_summary(window_hours: int = 24) -> dict[str, dict[str, Any]]:
    """Per-feed health over `window_hours`: last pass, freshness, success rate."""
    cutoff = _iso(_utc_now() - timedelta(hours=window_hours))
    try:
        with database.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT feed,
                       COUNT(*)   AS runs,
                       SUM(ok)    AS oks,
                       SUM(items) AS items
                FROM crawl_runs
                WHERE started_at >= ?
                GROUP BY feed
                """,
                (cutoff,),
            )
            windowed = {
                r["feed"]: {
                    "runs_24h": int(r["runs"] or 0),
                    "ok_24h": int(r["oks"] or 0),
                    "items_24h": int(r["items"] or 0),
                }
                for r in cursor.fetchall()
            }
            cursor.execute(
                """
                SELECT c.* FROM crawl_runs c
                JOIN (SELECT feed, MAX(id) AS last_id FROM crawl_runs GROUP BY feed) m
                  ON c.id = m.last_id
                """
            )
            last_rows = [_row_to_dict(r) for r in cursor.fetchall()]
    except Exception as exc:  # noqa: BLE001
        logger.warning("crawl_monitor.feed_summary failed: %s", exc)
        return {}

    now = _utc_now()
    summary: dict[str, dict[str, Any]] = {}
    for last in last_rows:
        stats = windowed.get(last["feed"], {"runs_24h": 0, "ok_24h": 0, "items_24h": 0})
        started = _parse_iso(last["started_at"])
        runs = stats["runs_24h"]
        summary[last["feed"]] = {
            **stats,
            "success_rate": round(stats["ok_24h"] / runs, 4) if runs else None,
            "last_run_at": last["started_at"],
            "last_ok": last["ok"],
            "last_items": last["items"],
            "last_duration_ms": last["duration_ms"],
            "last_error": last["error"],
            "last_detail": last["detail"],
            "age_seconds": int((now - started).total_seconds()) if started else None,
        }
    return summary


def prune(retention_days: int = DEFAULT_RETENTION_DAYS) -> int:
    """Delete crawl rows older than the retention window. Returns rows deleted."""
    cutoff = _iso(_utc_now() - timedelta(days=max(1, int(retention_days))))
    try:
        with database.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM crawl_runs WHERE started_at < ?", (cutoff,))
            deleted = cursor.rowcount or 0
            conn.commit()
            return int(deleted)
    except Exception as exc:  # noqa: BLE001
        logger.warning("crawl_monitor.prune failed: %s", exc)
        return 0
