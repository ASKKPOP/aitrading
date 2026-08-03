"""
Tasks Module

后台任务管理
"""

import asyncio
import hashlib
import json
import os
import re
import threading
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
import markets

# Global trending cache (shared with routes)
trending_cache: list = []
_last_profit_history_prune_at: float = time.time()
_profit_history_prune_task: Optional[asyncio.Task] = None
_TRENDING_CACHE_KEY = "trending:top20"
_SUPPORTED_PRICE_MARKETS = markets.supported_markets()

# Plan 15 overnight finding (2026-07-23): crypto-only refresh left every
# true-futures position's mark frozen at entry — run stop evaluation
# fail-closes on stale marks, so each CL/ZC/ZS run died stop_eval_failed
# ~18 min after entering and the fleet churned replacements (6 CL runs in
# 95 min, double fees each). us-stock included for the same reason once
# those runs hold positions.
# forex added 2026-07-28. It was absent because it could never
# open a position — the flat 0.1%/side fee gate refused 100% of forex theses,
# so no forex mark ever needed refreshing. Per-market fees removed that block
# and the SAME failure returned within twenty minutes: USDZAR opened at
# 08:40:19, its mark never advanced, _zombie_pnl could not value the position,
# marked_equity returned ok=False, and the WHOLE fleet froze — 63 consecutive
# breaker_eval_failed ticks with two runs paused behind it.
#
# The list must name every market that can TRADE, not every market that
# happens to be trading today. A market this list forgets fails silently at
# entry+staleness, not at deploy.
# options is here despite automatable=False: runs never target it, but a
# MANUAL options position still needs a mark or the SL/TP watcher cannot see
# it — the same failure, reached by a different door. Found by the regression
# test below on its first run, not by an outage.
REFRESH_PRICED_MARKETS_DEFAULT = "crypto,futures,us-stock,forex,options"
_PRICE_FAILURES: Dict[tuple[str, str, str, str], dict[str, float]] = {}
_PRICE_FAILURE_CACHE_KEY_PREFIX = "position_price_failures"
_POLYMARKET_SETTLEMENT_RECHECK_AFTER: Dict[tuple[str, str, str], float] = {}
_POLYMARKET_UPDOWN_RE = re.compile(r"^(btc|eth|sol|xrp)-updown-(5m|15m|1h|4h)-(\d+)$", re.IGNORECASE)
_profit_history_prune_lock = threading.Lock()
_POLYMARKET_SETTLEMENT_CURSOR = 0


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int, minimum: Optional[int] = None) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except Exception:
        value = default
    if minimum is not None:
        value = max(minimum, value)
    return value


def _env_csv_set(name: str, default: str = "") -> set[str]:
    raw = os.getenv(name, default)
    return {item.strip().lower() for item in raw.split(",") if item.strip()}


def _normalize_task_market(market: str | None) -> str:
    try:
        from routes_shared import normalize_market

        return normalize_market(market)
    except Exception:
        return (market or "").strip().lower()


def _price_failure_retry_after(key: tuple[str, str, str, str], now_ts: float) -> float:
    state = _PRICE_FAILURES.get(key)
    if not state:
        try:
            from cache import get_json

            cached = get_json(_price_failure_cache_key(key))
            if isinstance(cached, dict):
                state = {
                    "count": float(cached.get("count") or 0),
                    "retry_after": float(cached.get("retry_after") or 0),
                    "last_failed_at": float(cached.get("last_failed_at") or 0),
                }
                if state["retry_after"] > now_ts:
                    _PRICE_FAILURES[key] = state
        except Exception:
            state = None
    if not state:
        return 0.0
    return max(0.0, float(state.get("retry_after", 0.0)) - now_ts)


def _price_failure_cache_key(key: tuple[str, str, str, str]) -> str:
    payload = json.dumps(list(key), separators=(",", ":"), sort_keys=False)
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()
    return f"{_PRICE_FAILURE_CACHE_KEY_PREFIX}:{digest}"


def _record_price_failure(key: tuple[str, str, str, str], now_ts: float) -> int:
    base_s = _env_int("POSITION_PRICE_FAILURE_COOLDOWN_SECONDS", 3600, minimum=60)
    max_s = _env_int("POSITION_PRICE_FAILURE_MAX_COOLDOWN_SECONDS", 21600, minimum=base_s)
    previous = _PRICE_FAILURES.get(key, {})
    count = int(previous.get("count", 0)) + 1
    cooldown_s = min(max_s, base_s * (2 ** min(count - 1, 6)))
    state = {
        "count": float(count),
        "retry_after": now_ts + cooldown_s,
        "last_failed_at": now_ts,
    }
    _PRICE_FAILURES[key] = state
    try:
        from cache import set_json

        set_json(_price_failure_cache_key(key), state, ttl_seconds=cooldown_s + 300)
    except Exception:
        pass
    return cooldown_s


def _clear_price_failure(key: tuple[str, str, str, str]) -> None:
    _PRICE_FAILURES.pop(key, None)
    try:
        from cache import delete

        delete(_price_failure_cache_key(key))
    except Exception:
        pass


def _format_price_key(key: tuple[str, str, str, str]) -> str:
    symbol, market, token_id, outcome = key
    suffix = f", token={token_id}" if token_id else ""
    if outcome:
        suffix = f"{suffix}, outcome={outcome}" if suffix else f", outcome={outcome}"
    return f"{symbol} ({market}{suffix})"


def _polymarket_updown_expired_seconds(symbol: str | None, now_ts: float) -> Optional[float]:
    match = _POLYMARKET_UPDOWN_RE.match((symbol or "").strip())
    if not match:
        return None
    try:
        end_ts = int(match.group(3))
    except Exception:
        return None
    return now_ts - float(end_ts)


def _backfill_polymarket_position_metadata() -> None:
    """Best-effort backfill for legacy Polymarket positions missing token_id/outcome."""
    from database import get_db_connection
    from price_fetcher import _polymarket_resolve_reference

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT id, symbol, token_id, outcome
            FROM positions
            WHERE market = 'polymarket' AND (token_id IS NULL OR token_id = '')
        """)
        rows = cursor.fetchall()
        if not rows:
            # `finally` closes the connection; an explicit close here would
            # double-close it — a no-op on SQLite but a pymysql "Already closed".
            return

        updated = 0
        skipped = 0
        for row in rows:
            outcome = row["outcome"]
            if not outcome:
                skipped += 1
                continue
            contract = _polymarket_resolve_reference(row["symbol"], outcome=outcome)
            if not contract or not contract.get("token_id"):
                skipped += 1
                continue
            cursor.execute("""
                UPDATE positions
                SET token_id = ?, outcome = COALESCE(outcome, ?)
                WHERE id = ?
            """, (contract["token_id"], contract.get("outcome"), row["id"]))
            updated += 1

        if updated > 0:
            conn.commit()
            print(f"[Polymarket Backfill] Updated {updated} legacy positions; skipped={skipped}")
        else:
            conn.rollback()
    finally:
        conn.close()


def _update_trending_cache():
    """Update trending cache - calculates from positions table."""
    from cache import set_json
    from database import get_db_connection
    conn = get_db_connection()
    cursor = conn.cursor()

    # Get symbols ranked by holder count with current prices
    cursor.execute("""
        SELECT symbol, market, token_id, outcome, COUNT(DISTINCT agent_id) as holder_count
        FROM positions
        GROUP BY symbol, market, token_id, outcome
        ORDER BY holder_count DESC
        LIMIT 20
    """)
    rows = cursor.fetchall()

    updated_trending: list[dict[str, Any]] = []
    for row in rows:
        # Get current price from positions table
        cursor.execute("""
            SELECT current_price FROM positions
            WHERE symbol = ? AND market = ? AND COALESCE(token_id, '') = COALESCE(?, '')
            LIMIT 1
        """, (row["symbol"], row["market"], row["token_id"]))
        price_row = cursor.fetchone()

        updated_trending.append({
            "symbol": row["symbol"],
            "market": row["market"],
            "token_id": row["token_id"],
            "outcome": row["outcome"],
            "holder_count": row["holder_count"],
            "current_price": price_row["current_price"] if price_row else None
        })

    conn.close()
    trending_cache.clear()
    trending_cache.extend(updated_trending)
    refresh_interval = max(60, _env_int("POSITION_REFRESH_INTERVAL", 900, minimum=60) * 2)
    set_json(_TRENDING_CACHE_KEY, trending_cache, ttl_seconds=refresh_interval)


def _prune_profit_history() -> None:
    if not _profit_history_prune_lock.acquire(blocking=False):
        print("[Profit History] Prune already running; skipped")
        return
    try:
        _prune_profit_history_unlocked()
    finally:
        _profit_history_prune_lock.release()


def _prune_profit_history_unlocked() -> None:
    """Tier profit history into high-resolution, 15m, hourly, and daily retention."""
    from database import get_db_connection, using_mysql

    full_resolution_hours = _env_int("PROFIT_HISTORY_FULL_RESOLUTION_HOURS", 24, minimum=1)
    fifteen_min_window_days = _env_int(
        "PROFIT_HISTORY_15M_WINDOW_DAYS",
        _env_int("PROFIT_HISTORY_COMPACT_WINDOW_DAYS", 7, minimum=1),
        minimum=1,
    )
    hourly_window_days = _env_int("PROFIT_HISTORY_HOURLY_WINDOW_DAYS", 30, minimum=fifteen_min_window_days)
    daily_window_days = _env_int("PROFIT_HISTORY_DAILY_WINDOW_DAYS", 365, minimum=hourly_window_days)
    bucket_minutes = _env_int("PROFIT_HISTORY_COMPACT_BUCKET_MINUTES", 15, minimum=1)

    if full_resolution_hours >= fifteen_min_window_days * 24:
        full_resolution_hours = max(1, fifteen_min_window_days * 24 - 1)

    now = datetime.now(timezone.utc)
    daily_cutoff = (now - timedelta(days=daily_window_days)).isoformat().replace("+00:00", "Z")
    hourly_cutoff = (now - timedelta(days=hourly_window_days)).isoformat().replace("+00:00", "Z")
    fifteen_min_cutoff = (now - timedelta(days=fifteen_min_window_days)).isoformat().replace("+00:00", "Z")
    full_resolution_cutoff = (now - timedelta(hours=full_resolution_hours)).isoformat().replace("+00:00", "Z")

    deleted_old = 0
    deleted_15m = 0
    deleted_hourly = 0
    deleted_daily = 0

    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        cursor.execute("DELETE FROM profit_history WHERE recorded_at < ?", (daily_cutoff,))
        deleted_old = cursor.rowcount if cursor.rowcount is not None else 0
        conn.commit()

        if using_mysql():
            # MySQL 8.0: bucket by SUBSTRING of the ISO-8601 text timestamps.
            # STR_TO_DATE('%Y-%m-%dT%H:%i:%sZ') raises 1411 on values with
            # fractional seconds ('...T01:20:18.660506Z'); the ISO string is
            # fixed-width through the seconds, so substrings bucket correctly
            # with or without a microsecond suffix.
            if full_resolution_cutoff > fifteen_min_cutoff:
                cursor.execute("""
                    DELETE FROM profit_history
                    WHERE id IN (
                        SELECT id FROM (
                            SELECT
                                id,
                                ROW_NUMBER() OVER (
                                    PARTITION BY
                                        agent_id,
                                        SUBSTRING(recorded_at, 1, 13),
                                        FLOOR(CAST(SUBSTRING(recorded_at, 15, 2) AS UNSIGNED) / ?)
                                    ORDER BY recorded_at DESC, id DESC
                                ) AS rn
                            FROM profit_history
                            WHERE recorded_at >= ? AND recorded_at < ?
                        ) ranked
                        WHERE rn > 1
                    )
                """, (bucket_minutes, fifteen_min_cutoff, full_resolution_cutoff))
                deleted_15m = cursor.rowcount if cursor.rowcount is not None else 0
                conn.commit()

            if fifteen_min_cutoff > hourly_cutoff:
                cursor.execute("""
                    DELETE FROM profit_history
                    WHERE id IN (
                        SELECT id FROM (
                            SELECT
                                id,
                                ROW_NUMBER() OVER (
                                    PARTITION BY agent_id,
                                        SUBSTRING(recorded_at, 1, 13)
                                    ORDER BY recorded_at DESC, id DESC
                                ) AS rn
                            FROM profit_history
                            WHERE recorded_at >= ? AND recorded_at < ?
                        ) ranked
                        WHERE rn > 1
                    )
                """, (hourly_cutoff, fifteen_min_cutoff))
                deleted_hourly = cursor.rowcount if cursor.rowcount is not None else 0
                conn.commit()

            if hourly_cutoff > daily_cutoff:
                cursor.execute("""
                    DELETE FROM profit_history
                    WHERE id IN (
                        SELECT id FROM (
                            SELECT
                                id,
                                ROW_NUMBER() OVER (
                                    PARTITION BY agent_id,
                                        SUBSTRING(recorded_at, 1, 10)
                                    ORDER BY recorded_at DESC, id DESC
                                ) AS rn
                            FROM profit_history
                            WHERE recorded_at >= ? AND recorded_at < ?
                        ) ranked
                        WHERE rn > 1
                    )
                """, (daily_cutoff, hourly_cutoff))
                deleted_daily = cursor.rowcount if cursor.rowcount is not None else 0
                conn.commit()
        else:
            if full_resolution_cutoff > fifteen_min_cutoff:
                cursor.execute("""
                    DELETE FROM profit_history
                    WHERE id IN (
                        SELECT id
                        FROM (
                            SELECT
                                id,
                                ROW_NUMBER() OVER (
                                    PARTITION BY
                                        agent_id,
                                        strftime('%Y-%m-%dT%H', recorded_at),
                                        CAST(strftime('%M', recorded_at) AS INTEGER) / ?
                                    ORDER BY recorded_at DESC, id DESC
                                ) AS rn
                            FROM profit_history
                            WHERE recorded_at >= ? AND recorded_at < ?
                        ) ranked
                        WHERE rn > 1
                    )
                """, (bucket_minutes, fifteen_min_cutoff, full_resolution_cutoff))
                deleted_15m = cursor.rowcount if cursor.rowcount is not None else 0
                conn.commit()

            if fifteen_min_cutoff > hourly_cutoff:
                cursor.execute("""
                    DELETE FROM profit_history
                    WHERE id IN (
                        SELECT id
                        FROM (
                            SELECT
                                id,
                                ROW_NUMBER() OVER (
                                    PARTITION BY agent_id, strftime('%Y-%m-%dT%H', recorded_at)
                                    ORDER BY recorded_at DESC, id DESC
                                ) AS rn
                            FROM profit_history
                            WHERE recorded_at >= ? AND recorded_at < ?
                        ) ranked
                        WHERE rn > 1
                    )
                """, (hourly_cutoff, fifteen_min_cutoff))
                deleted_hourly = cursor.rowcount if cursor.rowcount is not None else 0
                conn.commit()

            if hourly_cutoff > daily_cutoff:
                cursor.execute("""
                    DELETE FROM profit_history
                    WHERE id IN (
                        SELECT id
                        FROM (
                            SELECT
                                id,
                                ROW_NUMBER() OVER (
                                    PARTITION BY agent_id, strftime('%Y-%m-%d', recorded_at)
                                    ORDER BY recorded_at DESC, id DESC
                                ) AS rn
                            FROM profit_history
                            WHERE recorded_at >= ? AND recorded_at < ?
                        ) ranked
                        WHERE rn > 1
                    )
                """, (daily_cutoff, hourly_cutoff))
                deleted_daily = cursor.rowcount if cursor.rowcount is not None else 0
                conn.commit()

        total_deleted = deleted_old + deleted_15m + deleted_hourly + deleted_daily
        if total_deleted:
            print(
                "[Profit History] Pruned history: "
                f"deleted_old={deleted_old} "
                f"compacted_15m={deleted_15m} "
                f"compacted_hourly={deleted_hourly} "
                f"compacted_daily={deleted_daily}"
            )
            if not using_mysql() and _env_bool("PROFIT_HISTORY_VACUUM_AFTER_PRUNE", True):
                min_deleted = _env_int("PROFIT_HISTORY_VACUUM_MIN_DELETED_ROWS", 50000, minimum=1)
                if total_deleted >= min_deleted:
                    cursor.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                    cursor.execute("VACUUM")
                    print("[Profit History] SQLite VACUUM completed after prune")
    finally:
        conn.close()


def _maybe_prune_profit_history() -> None:
    global _last_profit_history_prune_at

    prune_interval = _env_int("PROFIT_HISTORY_PRUNE_INTERVAL_SECONDS", 3600)
    if prune_interval <= 0:
        return

    now = time.time()
    if now - _last_profit_history_prune_at < prune_interval:
        return

    _last_profit_history_prune_at = now
    _prune_profit_history()


def _profit_history_prune_done(task: asyncio.Task) -> None:
    try:
        task.result()
    except asyncio.CancelledError:
        pass
    except Exception as exc:
        print(f"[Profit History] Async prune failed: {exc}")


def _maybe_schedule_profit_history_prune() -> None:
    global _last_profit_history_prune_at, _profit_history_prune_task

    prune_interval = _env_int("PROFIT_HISTORY_PRUNE_INTERVAL_SECONDS", 3600)
    if prune_interval <= 0:
        return

    if _profit_history_prune_task is not None and not _profit_history_prune_task.done():
        return

    now = time.time()
    if now - _last_profit_history_prune_at < prune_interval:
        return

    _last_profit_history_prune_at = now
    _profit_history_prune_task = asyncio.create_task(
        asyncio.to_thread(_prune_profit_history),
        name="sooppiy:profit_history_prune",
    )
    _profit_history_prune_task.add_done_callback(_profit_history_prune_done)
    print("[Profit History] Scheduled async prune")


async def update_position_prices():
    """Background task to update position prices every 5 minutes."""
    from database import get_db_connection
    from price_fetcher import get_price_from_market, price_fetch_logging

    # Get max parallel requests from environment variable
    max_parallel = _env_int("MAX_PARALLEL_PRICE_FETCH", 2, minimum=1)
    verbose_fetch = _env_bool("POSITION_PRICE_VERBOSE_FETCH_LOGS", False)
    refresh_priced_markets = _env_csv_set("POSITION_PRICE_REFRESH_PRICED_MARKETS",
                                          REFRESH_PRICED_MARKETS_DEFAULT)

    # Wait a bit on startup before first update
    await asyncio.sleep(_env_int("POSITION_PRICE_STARTUP_DELAY_SECONDS", 15, minimum=0))

    while True:
        try:
            _backfill_polymarket_position_metadata()
            conn = get_db_connection()
            try:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT
                        symbol,
                        market,
                        token_id,
                        outcome,
                        COUNT(*) AS position_count,
                        SUM(CASE WHEN current_price IS NULL THEN 1 ELSE 0 END) AS null_price_count
                    FROM positions
                    GROUP BY symbol, market, token_id, outcome
                """)
                unique_positions = cursor.fetchall()
            finally:
                conn.close()

            now_ts = time.time()
            candidates = []
            skipped_unsupported = 0
            skipped_cooldown = 0
            skipped_expired_polymarket = 0
            skipped_priced = 0
            skipped_cooldown_by_market: Counter[str] = Counter()
            skipped_priced_by_market: Counter[str] = Counter()
            skipped_unsupported_by_market: Counter[str] = Counter()

            for row in unique_positions:
                symbol = row["symbol"]
                original_market = row["market"]
                market = _normalize_task_market(original_market)
                token_id = row["token_id"] or ""
                outcome = row["outcome"] or ""
                null_price_count = int(row["null_price_count"] or 0)

                if market not in _SUPPORTED_PRICE_MARKETS:
                    skipped_unsupported += 1
                    skipped_unsupported_by_market[str(original_market or "-")] += 1
                    continue

                if null_price_count <= 0 and market not in refresh_priced_markets:
                    skipped_priced += 1
                    skipped_priced_by_market[market] += 1
                    continue

                if market == "polymarket":
                    expired_s = _polymarket_updown_expired_seconds(symbol, now_ts)
                    if expired_s is not None and expired_s > _env_int("POLYMARKET_UPDOWN_PRICE_GRACE_SECONDS", 900, minimum=60):
                        skipped_expired_polymarket += 1
                        continue

                key = (str(symbol or ""), market, str(token_id), str(outcome))
                remaining = _price_failure_retry_after(key, now_ts)
                if remaining > 0:
                    skipped_cooldown += 1
                    skipped_cooldown_by_market[market] += 1
                    continue

                candidates.append({
                    "symbol": symbol,
                    "db_market": original_market,
                    "market": market,
                    "token_id": token_id,
                    "outcome": outcome,
                    "key": key,
                })

            print(
                "[Price Update] candidates="
                f"{len(candidates)}/{len(unique_positions)} "
                f"skipped_unsupported={skipped_unsupported} "
                f"skipped_priced={skipped_priced} "
                f"skipped_expired_polymarket={skipped_expired_polymarket} "
                f"skipped_cooldown={skipped_cooldown}"
            )
            if skipped_unsupported_by_market:
                print(f"[Price Update] Unsupported markets skipped: {dict(skipped_unsupported_by_market.most_common())}")
            if skipped_priced_by_market:
                print(f"[Price Update] Already-priced markets skipped: {dict(skipped_priced_by_market.most_common())}")
            if skipped_cooldown_by_market:
                print(f"[Price Update] Failure cooldown skips by market: {dict(skipped_cooldown_by_market.most_common())}")

            # Semaphore to control concurrency
            semaphore = asyncio.Semaphore(max_parallel)

            async def fetch_price(row: dict[str, Any]):
                symbol = row["symbol"]
                market = row["market"]
                db_market = row["db_market"]
                token_id = row["token_id"]
                outcome = row["outcome"]
                key = row["key"]

                async with semaphore:
                    # Run synchronous function in thread pool
                    # Use UTC time for consistent pricing timestamps
                    now = datetime.now(timezone.utc)
                    executed_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
                    with price_fetch_logging(verbose_fetch):
                        price = await asyncio.to_thread(
                            get_price_from_market, symbol, executed_at, market, token_id, outcome
                        )

                return {
                    "symbol": symbol,
                    "db_market": db_market,
                    "market": market,
                    "token_id": token_id,
                    "outcome": outcome,
                    "key": key,
                    "price": price,
                }

            # Fetch prices in parallel, then write them back in one short transaction.
            results = await asyncio.gather(*[fetch_price(row) for row in candidates])
            _price_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            updates = [
                (item["price"], _price_ts, item["symbol"], item["db_market"], item["token_id"])
                for item in results
                if item["price"] is not None
            ]
            failed = [item for item in results if item["price"] is None]
            failures_by_market: Counter[str] = Counter(item["market"] for item in failed)
            success_by_market: Counter[str] = Counter(item["market"] for item in results if item["price"] is not None)

            cooldown_samples: list[str] = []
            for item in results:
                if item["price"] is not None:
                    _clear_price_failure(item["key"])
                    continue
                cooldown_s = _record_price_failure(item["key"], now_ts)
                if len(cooldown_samples) < 8:
                    cooldown_samples.append(f"{_format_price_key(item['key'])} retry_in={cooldown_s}s")

            if updates:
                conn = get_db_connection()
                try:
                    cursor = conn.cursor()
                    cursor.executemany("""
                        UPDATE positions
                        SET current_price = ?, price_updated_at = ?
                        WHERE symbol = ? AND market = ? AND COALESCE(token_id, '') = COALESCE(?, '')
                    """, updates)
                    conn.commit()
                finally:
                    conn.close()

            print(
                "[Price Update] summary "
                f"requested={len(results)} updated={len(updates)} failed={len(failed)} "
                f"success_by_market={dict(success_by_market.most_common())} "
                f"failed_by_market={dict(failures_by_market.most_common())}"
            )
            if cooldown_samples:
                print(f"[Price Update] Failure cooldown samples: {cooldown_samples}")

            # Update trending cache (no additional API call, uses same data)
            _update_trending_cache()

        except Exception as e:
            print(f"[Price Update Error] {e}")

        # Wait interval from environment variable (default: 5 minutes = 300 seconds)
        refresh_interval = _env_int("POSITION_REFRESH_INTERVAL", 900, minimum=60)
        print(f"[Price Update] Next update in {refresh_interval} seconds")
        await asyncio.sleep(refresh_interval)


async def automation_loop():
    """Background task for AI trading automation (Target 3).

    Every AUTOMATION_TICK_INTERVAL seconds, scan enabled automation_configs and
    run each due rule: multi-agent analysis -> decision -> (if the rule allows)
    auto paper-trade on the simulator account. See automation.py.
    """
    from automation import run_automation_tick

    tick_interval = _env_int("AUTOMATION_TICK_INTERVAL", 60, minimum=15)

    # Give the API a moment to start before running analyses.
    await asyncio.sleep(10)

    while True:
        try:
            result = await asyncio.to_thread(run_automation_tick)
            if result.get("due"):
                print(
                    "[Automation] Tick complete: "
                    f"due={result.get('due', 0)} executed={result.get('executed', 0)}"
                )
        except Exception as e:
            print(f"[Automation Error] {e}")

        await asyncio.sleep(tick_interval)


async def gateway_keepalive_loop():
    """Keep IBKR Client Portal sessions alive (execution/gateway.py).

    CPAPI drops an idle session after a few minutes; without a periodic tickle
    a live IBKR rule on an hourly interval finds a dead gateway at every tick.
    Sweeps active ibkr broker_accounts every GATEWAY_KEEPALIVE_INTERVAL seconds
    (default 60): tickle → status → reauthenticate if lapsed → alert the owner
    (once per day) if still dead. No-ops instantly when no IBKR account exists,
    so the task is free for every deployment that hasn't connected one.
    """
    from execution.gateway import keepalive_tick

    tick_interval = _env_int("GATEWAY_KEEPALIVE_INTERVAL", 60, minimum=30)
    await asyncio.sleep(15)

    while True:
        try:
            result = await asyncio.to_thread(keepalive_tick)
            if result.get("accounts"):
                print(f"[Gateway Keepalive] accounts={result['accounts']} "
                      f"alive={result['alive']} revived={result['revived']} "
                      f"dead={result['dead']}")
        except Exception as e:  # noqa: BLE001
            print(f"[Gateway Keepalive Error] {e}")

        await asyncio.sleep(tick_interval)


async def order_reconciler_loop():
    """Confirm the final state of SUBMITTED broker orders (execution/gateway.py).

    A live/shadow order the broker answered with SUBMITTED may later fill,
    part-fill or be cancelled — the platform ledger was written at the
    requested size and would silently diverge. Every ORDER_RECONCILE_INTERVAL
    seconds (default 120) ask the broker, record the terminal status +
    broker-confirmed filled_qty, and alert the owner (order_drift) on material
    divergence. Never mutates positions/cash — detection, not correction.
    No-ops instantly when no submitted non-paper orders exist.
    """
    from execution.gateway import reconcile_orders_tick

    tick_interval = _env_int("ORDER_RECONCILE_INTERVAL", 120, minimum=30)
    await asyncio.sleep(20)

    while True:
        try:
            result = await asyncio.to_thread(reconcile_orders_tick)
            if result.get("checked"):
                print(f"[Order Reconciler] checked={result['checked']} "
                      f"settled={result['settled']} still_open={result['still_open']} "
                      f"drift={result['drift']} lookup_failed={result['lookup_failed']}")
        except Exception as e:  # noqa: BLE001
            print(f"[Order Reconciler Error] {e}")

        await asyncio.sleep(tick_interval)


async def trading_run_loop():
    """Background task for Trading Runs (Plan 10).

    Every RUN_TICK_INTERVAL seconds (default 30): control pass (arm runs whose
    start condition fired, finish position-less stops) then dispatch due
    cycles onto run_engine's DEDICATED executor — LLM-bound cycles must never
    occupy the shared to_thread pool the SL/TP watcher depends on. Gated by
    AUTO_TRADING_ENABLED (ships dark). See run_engine.py.
    """
    from run_engine import tick as run_engine_tick

    tick_interval = _env_int("RUN_TICK_INTERVAL", 30, minimum=10)

    await asyncio.sleep(10)

    while True:
        try:
            result = await run_engine_tick()
            if result.get("dispatched") or result.get("armed_started") \
                    or result.get("stopping_finished"):
                print(f"[TradingRuns] tick: {result}")
            # Plan 14 §6.5.5: supervision watchdog rides THIS loop — a crashed
            # fleet loop must still produce an alert (rails may be dark).
            try:
                from fleet_supervisor import check_watchdog
                stale = await asyncio.to_thread(check_watchdog)
                if stale:
                    print(f"[TradingRuns] fleet watchdog: {stale} stale fleet(s)")
            except Exception:  # noqa: BLE001 — watchdog must never wedge runs
                pass
        except Exception as e:
            print(f"[TradingRuns Error] {e}")

        await asyncio.sleep(tick_interval)


async def report_scheduler_loop():
    """Background task for Trading Runs reporting (Plan 10, Phase 4).

    Every REPORT_TICK_INTERVAL seconds: queue+deliver due P&L digests
    (journal-before-send, pending -> sent) and retry stale pending rows.
    All external delivery goes through alerts.send_alert (rate limit +
    dedupe + run_stopped reserve). Gated by AUTO_TRADING_ENABLED.
    """
    from run_engine import auto_trading_enabled
    from run_reports import scheduler_tick

    tick_interval = _env_int("REPORT_TICK_INTERVAL", 60, minimum=30)

    await asyncio.sleep(15)

    while True:
        try:
            if auto_trading_enabled():
                result = await asyncio.to_thread(scheduler_tick)
                if result.get("queued") or result.get("retried"):
                    print(f"[RunReports] tick: {result}")
        except Exception as e:
            print(f"[RunReports Error] {e}")

        await asyncio.sleep(tick_interval)


async def desk_brief_loop():
    """Plan 21 P4: daily desk brief + monthly process review.

    Checks every DESK_BRIEF_TICK_INTERVAL seconds whether today's brief (or
    the month's review) is due; platform_settings markers make each send
    once-only across restarts. Deterministic — no LLM calls.
    """
    from desk_brief import desk_brief_enabled, desk_brief_tick

    tick_interval = _env_int("DESK_BRIEF_TICK_INTERVAL", 600, minimum=60)

    await asyncio.sleep(30)

    while True:
        try:
            if desk_brief_enabled():
                result = await asyncio.to_thread(desk_brief_tick)
                if result.get("daily_sent") or result.get("monthly"):
                    print(f"[DeskBrief] tick: {result}")
        except Exception as e:
            print(f"[DeskBrief Error] {e}")

        await asyncio.sleep(tick_interval)


async def subscription_enforcer_loop():
    """Background task for Trading Runs entitlements (Plan 10, Phase 5).

    Every SUBSCRIPTION_ENFORCER_INTERVAL seconds (default 600): pause running
    runs whose owner's subscription lapsed (pause, never delete — resumable
    on renewal). No-op unless AUTO_TRADING_ENABLED + ENTITLEMENTS_ENFORCED.
    """
    from run_engine import auto_trading_enabled, subscription_enforcer_tick

    tick_interval = _env_int("SUBSCRIPTION_ENFORCER_INTERVAL", 600, minimum=60)

    await asyncio.sleep(20)

    while True:
        try:
            if auto_trading_enabled():
                result = await asyncio.to_thread(subscription_enforcer_tick)
                if result.get("paused"):
                    print(f"[Entitlements] paused {result['paused']} lapsed run(s)")
        except Exception as e:
            print(f"[Entitlements Error] {e}")

        await asyncio.sleep(tick_interval)


async def risk_watcher_loop():
    """Background task for the risk engine SL/TP watcher (Phase 1).

    Every RISK_WATCHER_INTERVAL seconds (default 30), close long positions whose
    polled current_price crossed their stop_loss/take_profit. Reads prices from
    the positions table (maintained by update_position_prices) — no external
    calls. No-op unless RISK_ENGINE_ENABLED. See risk_engine.py.
    """
    from risk_engine import risk_engine_enabled, run_sltp_watcher_tick

    interval_s = _env_int("RISK_WATCHER_INTERVAL", 30, minimum=5)

    await asyncio.sleep(10)

    while True:
        try:
            if risk_engine_enabled():
                result = await asyncio.to_thread(run_sltp_watcher_tick)
                if result.get("closed"):
                    print(
                        "[Risk Watcher] SL/TP tick: "
                        f"checked={result.get('checked', 0)} closed={result.get('closed', 0)}"
                    )
        except Exception as e:
            print(f"[Risk Watcher Error] {e}")

        await asyncio.sleep(interval_s)


async def liquidation_watch_loop():
    """Plan 16: margin-state oracle and liquidation-tier escalation.

    Cadence is tighter than risk_watcher's 30s and the ~60s run-control scan
    because this is the one loop whose tail cost is the entire margin rather
    than one stop, and it drops to LIQ_WATCH_INTERVAL_HOT once any position
    reaches T2. Observation-only unless LIQ_REFLEX is on (default off).
    """
    import liquidation

    await asyncio.sleep(12)

    while True:
        interval = liquidation.watch_interval_seconds()
        try:
            if liquidation.oracle_enabled():
                result = await asyncio.to_thread(liquidation.watch_tick)
                for state in result.get("states", []):
                    _journal_margin_state(state)
                    # The reflex. Gated inside execute_reflex by LIQ_REFLEX and
                    # by reflex_block_reason; called unconditionally so that a
                    # refusal is journalled rather than silently skipped.
                    if liquidation.reflex_action(state):
                        outcome = await asyncio.to_thread(
                            liquidation.execute_reflex, state)
                        _journal_reflex(state, outcome)
                if result.get("worst") in (liquidation.TIER_DEFEND,
                                           liquidation.TIER_REFLEX):
                    interval = liquidation.watch_interval_hot_seconds()
                if result.get("escalations"):
                    print(f"[Liquidation] escalations={result['escalations']} "
                          f"worst={result['worst']} "
                          f"measured={result['measured']}/{result['checked']}")
        except Exception as e:  # noqa: BLE001 — one bad tick must not kill the worker
            print(f"[Liquidation Error] {e}")

        await asyncio.sleep(interval)


def _journal_reflex(state: dict, outcome: dict) -> None:
    """Record what the reflex did — including, especially, what it refused.

    A refusal is the interesting record: it means a position sat at T3 while
    the daemon declined to act, and the reason (stale mark, no owner) is the
    only way to tell a working guard from a broken executor after the fact.
    """
    payload = {"position_id": state.get("position_id"),
               "symbol": state.get("symbol"), "tier": state.get("tier"),
               "health": state.get("health"),
               "mark_age_seconds": state.get("mark_age_seconds"),
               "quantity": state.get("quantity"),
               "fired": outcome.get("fired"), "reason": outcome.get("reason"),
               "signal_id": outcome.get("signal_id")}
    print(f"[Liquidation Reflex] {payload}")
    run_id = state.get("run_id")
    if not run_id:
        return
    try:
        from trading_runs import emit_telemetry_event
        emit_telemetry_event(int(run_id), "liquidation_reflex", payload)
    except Exception:  # noqa: BLE001
        pass


def _journal_margin_state(state: dict) -> None:
    """Record a reading. Attached positions get a run event; orphans have no
    run to journal against, so they are logged — losing the reading entirely
    would recreate exactly the blind spot this loop exists to close."""
    import liquidation
    payload = {k: state.get(k) for k in
               ("position_id", "symbol", "market", "side", "leverage",
                "liq_price", "health", "velocity_per_hour", "ttl_hours",
                "tier", "tier_raw", "escalated_from", "source")}
    run_id = state.get("run_id")
    escalated = state.get("escalated_from") is not None
    interesting = escalated or state.get("tier") != liquidation.TIER_NOMINAL
    if run_id:
        # Only journal transitions and non-nominal readings: a T0 heartbeat
        # every 20s per position is pure prune load, and run_events is already
        # dominated by equity rows.
        if interesting:
            try:
                from trading_runs import emit_telemetry_event
                emit_telemetry_event(int(run_id), "margin", payload)
            except Exception:  # noqa: BLE001
                pass
    elif interesting:
        print(f"[Liquidation] orphan position {payload}")


async def resting_orders_loop():
    """Background task for the terminals' resting (limit) order watcher.

    Every RESTING_ORDERS_INTERVAL seconds (default 15) fill open limit orders
    whose limit the live OKX price has crossed — one batched tickers call per
    tick, through the paper executor (simulator only, never the live gateway).
    No-op when the table has no open rows; kill switch RESTING_ORDERS_ENABLED.
    """
    from resting_orders import resting_orders_enabled, run_resting_orders_tick

    interval_s = _env_int("RESTING_ORDERS_INTERVAL", 15, minimum=5)

    await asyncio.sleep(10)

    while True:
        try:
            if resting_orders_enabled():
                result = await asyncio.to_thread(run_resting_orders_tick)
                if result.get("filled") or result.get("rejected"):
                    print(
                        "[Resting Orders] tick: "
                        f"checked={result.get('checked', 0)} "
                        f"filled={result.get('filled', 0)} "
                        f"rejected={result.get('rejected', 0)}"
                    )
        except Exception as e:
            print(f"[Resting Orders Error] {e}")

        await asyncio.sleep(interval_s)


async def psych_feed_loop():
    """Background task for the psychology feed (Phase 2).

    Every PSYCH_REFRESH_INTERVAL seconds (default hourly), snapshot the crowd-
    psychology inputs: Fear & Greed index, news-sentiment spike z-scores,
    volatility shock proxy (OKX candles), and Polymarket odds. No-op unless
    PSYCH_FEED_ENABLED. See psych_feed.py.
    """
    from psych_feed import psych_feed_enabled, refresh_psych_snapshot

    refresh_interval = _env_int("PSYCH_REFRESH_INTERVAL", 3600, minimum=300)

    await asyncio.sleep(20)

    while True:
        try:
            if psych_feed_enabled():
                result = await asyncio.to_thread(refresh_psych_snapshot)
                print(
                    "[Psych Feed] snapshot stored: "
                    f"fng={result.get('fng')} "
                    f"spike_events={result.get('spike_events_recorded', 0)} "
                    f"errors={result.get('errors') or 'none'}"
                )
                # Phase 2: panic auto-trip check on fresh shock data — no-op
                # unless REGIME_FILTER_ENABLED; needs 2 consecutive real
                # liquidation shocks; per-market scope with expiry.
                try:
                    from regime import maybe_auto_trip_market_breaker
                    tripped = await asyncio.to_thread(maybe_auto_trip_market_breaker)
                    if tripped:
                        print(f"[Regime] panic auto-trip: {tripped}")
                except Exception as e:
                    print(f"[Regime Auto-trip Error] {e}")
        except Exception as e:
            print(f"[Psych Feed Error] {e}")

        await asyncio.sleep(refresh_interval)


async def watch_loop():
    """Personal watch functions (Plan 06 C3).

    Every WATCH_INTERVAL seconds (default 5min), evaluate each enabled user
    watch against live metrics and fire alerts on crossings. Cheap: metric
    values are cached per tick, and each watch has its own cooldown. Always
    on — a user with no watches makes this a no-op query.
    """
    from watch_engine import run_watch_tick

    interval = _env_int("WATCH_INTERVAL", 300, minimum=60)

    await asyncio.sleep(30)

    while True:
        try:
            result = await asyncio.to_thread(run_watch_tick)
            if result.get("fired"):
                print(f"[Watches] checked={result['checked']} fired={result['fired']}")
        except Exception as e:
            print(f"[Watches Error] {e}")

        await asyncio.sleep(interval)


async def factor_snapshot_loop():
    """Background task for factor snapshots (parameter-upgrade plan Phase 0.4).

    Every FACTOR_SNAPSHOT_INTERVAL seconds (default 6h), record funding/OI/
    long-short/StockTwits-tilt per symbol so live-only factors accumulate the
    history their confluence conditions need for live-forward validation.
    Always on — cheap and keyless.
    """
    from factor_snapshots import record_factor_snapshots

    refresh_interval = _env_int("FACTOR_SNAPSHOT_INTERVAL", 21600, minimum=3600)

    await asyncio.sleep(25)

    while True:
        try:
            result = await asyncio.to_thread(record_factor_snapshots)
            print(
                "[Factor Snapshots] stored: "
                f"written={result.get('written')} "
                f"errors={len(result.get('errors') or [])}"
            )
        except Exception as e:
            print(f"[Factor Snapshots Error] {e}")

        await asyncio.sleep(refresh_interval)


async def confidence_calibration_loop():
    """Step 0 of the calibration plan (2026-08-01): score the desk's entry
    confidence against realized outcomes — Brier raw vs base vs Platt, plus
    the claimed-vs-delivered curve — once per CALIBRATION_SCORE_INTERVAL
    (default 24h). Pure measurement: reads the ledger, writes one log line.
    Every calibration idea after this is judged by whether brier falls."""
    import confidence_calibration as cc

    refresh_interval = _env_int("CALIBRATION_SCORE_INTERVAL", 86400, minimum=3600)

    await asyncio.sleep(40)

    while True:
        try:
            sb = await asyncio.to_thread(cc.get_scoreboard, True)
            curve = " ".join(
                f"{b['lo']:.2f}-{b['hi']:.2f}:{b['win_rate'] if b['win_rate'] is not None else '—'}(n={b['n']})"
                for b in sb.get("curve") or [])
            print(
                "[Calibration] "
                f"n={sb.get('n')} base={sb.get('base_rate')} "
                f"brier_raw={sb.get('brier_raw')} brier_base={sb.get('brier_base')} "
                f"brier_platt={sb.get('brier_platt')} platt={sb.get('platt')} "
                f"curve: {curve}"
            )
        except Exception as e:
            print(f"[Calibration Error] {e}")

        await asyncio.sleep(refresh_interval)


async def scanner_loop():
    """Background task for the which-coin scanner (Phase 4).

    Every SCANNER_INTERVAL seconds (default hourly), scan OKX volume ratios,
    StockTwits mention rates, and new listings into ranked candidates. No-op
    unless SCANNER_ENABLED. See scanner.py.
    """
    from scanner import refresh_scanner_snapshot, scanner_enabled

    scan_interval = _env_int("SCANNER_INTERVAL", 3600, minimum=300)

    await asyncio.sleep(25)

    while True:
        try:
            if scanner_enabled():
                result = await asyncio.to_thread(refresh_scanner_snapshot)
                print(
                    "[Scanner] scan complete: "
                    f"candidates={result.get('candidates', 0)} "
                    f"volume_symbols={result.get('volume_symbols', 0)} "
                    f"new_listings={len(result.get('new_listings') or [])} "
                    f"errors={result.get('errors') or 'none'}"
                )
        except Exception as e:
            print(f"[Scanner Error] {e}")

        await asyncio.sleep(scan_interval)


async def social_feed_loop():
    """Background task for the social collection service (Plan 11 F5).

    Every SOCIAL_REFRESH_INTERVAL seconds (default 30 min), collect public
    posts about the tracked symbols — Facebook for South-East Asia, X
    elsewhere — score their polarity, snapshot the per-symbol tilt, and prune
    raw posts past SOCIAL_RAW_RETENTION_DAYS (default 7). No-op unless
    SOCIAL_FEED_ENABLED. See social_feed.py.
    """
    from social_feed import refresh_social_snapshot, social_feed_enabled

    refresh_interval = _env_int("SOCIAL_REFRESH_INTERVAL", 1800, minimum=300)

    await asyncio.sleep(30)

    while True:
        try:
            if social_feed_enabled():
                result = await asyncio.to_thread(refresh_social_snapshot)
                print(
                    "[Social Feed] snapshot stored: "
                    f"symbols={len(result.get('symbols') or {})} "
                    f"fetched={result.get('posts_fetched', 0)} "
                    f"stored={result.get('posts_stored', 0)} "
                    f"pruned={result.get('posts_pruned', 0)} "
                    f"errors={result.get('errors') or 'none'}"
                )
        except Exception as e:
            print(f"[Social Feed Error] {e}")

        await asyncio.sleep(refresh_interval)


async def refresh_market_news_snapshots_loop():
    """Background task to refresh market-news snapshots on a fixed interval."""
    from market_intel import refresh_market_news_snapshots

    # Plan 14 §4.2: 4h default makes the Alpha Vantage budget deterministic —
    # 4 categories × 6 passes/day = 24 calls against the 25/day free cap.
    # The old hourly default demanded 96/day and starved to first-25-wins.
    refresh_interval = _env_int("MARKET_NEWS_REFRESH_INTERVAL", 14400, minimum=300)

    # Give the API a moment to start before hitting external providers.
    await asyncio.sleep(3)

    while True:
        try:
            result = await asyncio.to_thread(refresh_market_news_snapshots)
            print(
                "[Market Intel] Refreshed market news snapshots: "
                f"inserted={result.get('inserted_categories', 0)} "
                f"errors={len(result.get('errors', {}))}"
            )
            for category, error in (result.get("errors") or {}).items():
                print(f"[Market Intel] {category} refresh failed: {error}")
        except Exception as e:
            print(f"[Market Intel Error] {e}")

        print(f"[Market Intel] Next market news refresh in {refresh_interval} seconds")
        await asyncio.sleep(refresh_interval)


async def refresh_macro_signal_snapshots_loop():
    """Background task to refresh macro signal snapshots on a fixed interval."""
    from market_intel import refresh_macro_signal_snapshot

    refresh_interval = _env_int("MACRO_SIGNAL_REFRESH_INTERVAL", 3600, minimum=300)

    await asyncio.sleep(6)

    while True:
        try:
            result = await asyncio.to_thread(refresh_macro_signal_snapshot)
            print(
                "[Market Intel] Refreshed macro signal snapshot: "
                f"verdict={result.get('verdict')} "
                f"signals={result.get('total_count', 0)}"
            )
        except Exception as e:
            print(f"[Macro Signal Error] {e}")

        print(f"[Market Intel] Next macro signal refresh in {refresh_interval} seconds")
        await asyncio.sleep(refresh_interval)


async def refresh_etf_flow_snapshots_loop():
    """Background task to refresh ETF flow snapshots on a fixed interval."""
    from market_intel import refresh_etf_flow_snapshot

    refresh_interval = _env_int("ETF_FLOW_REFRESH_INTERVAL", 3600, minimum=300)

    await asyncio.sleep(9)

    while True:
        try:
            result = await asyncio.to_thread(refresh_etf_flow_snapshot)
            print(
                "[Market Intel] Refreshed ETF flow snapshot: "
                f"direction={result.get('direction')} "
                f"tracked={result.get('tracked_count', 0)}"
            )
        except Exception as e:
            print(f"[ETF Flow Error] {e}")

        print(f"[Market Intel] Next ETF flow refresh in {refresh_interval} seconds")
        await asyncio.sleep(refresh_interval)


async def refresh_stock_analysis_snapshots_loop():
    """Background task to refresh featured stock-analysis snapshots."""
    from market_intel import refresh_stock_analysis_snapshots

    refresh_interval = _env_int("STOCK_ANALYSIS_REFRESH_INTERVAL", 7200, minimum=600)

    await asyncio.sleep(12)

    while True:
        try:
            result = await asyncio.to_thread(refresh_stock_analysis_snapshots)
            print(
                "[Market Intel] Refreshed stock analysis snapshots: "
                f"inserted={result.get('inserted_symbols', 0)} "
                f"errors={len(result.get('errors', {}))}"
            )
        except Exception as e:
            print(f"[Stock Analysis Error] {e}")

        print(f"[Market Intel] Next stock analysis refresh in {refresh_interval} seconds")
        await asyncio.sleep(refresh_interval)


async def periodic_token_cleanup():
    """Periodically clean up expired tokens."""
    from utils import cleanup_expired_tokens

    while True:
        try:
            await asyncio.sleep(3600)  # Every hour
            deleted = cleanup_expired_tokens()
            if deleted > 0:
                print(f"[Token Cleanup] Cleaned up {deleted} expired tokens")
        except Exception as e:
            print(f"[Token Cleanup Error] {e}")


def _record_profit_history_once() -> int:
    from database import get_db_connection

    started_at = time.monotonic()
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    initial_capital = 100000.0
    max_abs_profit = 1e12
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        # Single INSERT...SELECT CTE — compatible with SQLite 3.35+ and MySQL 8.0+
        cursor.execute("""
            INSERT INTO profit_history (agent_id, total_value, cash, position_value, profit, recorded_at)
            WITH agent_values AS (
                SELECT
                    a.id AS agent_id,
                    COALESCE(a.cash, 0) AS cash,
                    COALESCE(a.deposited, 0) AS deposited,
                    COALESCE(
                        SUM(
                            CASE
                                WHEN p.current_price IS NULL THEN p.entry_price * ABS(p.quantity)
                                WHEN p.side = 'long' THEN p.current_price * ABS(p.quantity)
                                ELSE (2 * p.entry_price - p.current_price) * ABS(p.quantity)
                            END
                        ),
                        0
                    ) AS position_value
                FROM agents a
                LEFT JOIN positions p ON p.agent_id = a.id
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM agent_leaderboard_exclusions ale
                    WHERE ale.agent_id = a.id
                      AND COALESCE(ale.active, 1) = 1
                )
                GROUP BY a.id, a.cash, a.deposited
            ),
            calculated AS (
                SELECT
                    agent_id,
                    cash,
                    position_value,
                    cash + position_value AS total_value,
                    cash + position_value - (? + deposited) AS raw_profit
                FROM agent_values
            )
            SELECT
                agent_id,
                total_value,
                cash,
                position_value,
                CASE
                    WHEN ABS(raw_profit) > ? THEN
                        CASE WHEN raw_profit > 0 THEN ? ELSE -? END
                    ELSE raw_profit
                END AS profit,
                ?
            FROM calculated
        """, (initial_capital, max_abs_profit, max_abs_profit, max_abs_profit, now))
        inserted_count = cursor.rowcount if cursor.rowcount is not None and cursor.rowcount >= 0 else 0
        clamped_count = 0
        if inserted_count == 0:
            cursor.execute("""
                SELECT COUNT(*) AS agent_count
                FROM agents a
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM agent_leaderboard_exclusions ale
                    WHERE ale.agent_id = a.id
                      AND COALESCE(ale.active, 1) = 1
                )
            """)
            row = cursor.fetchone()
            inserted_count = int(row["agent_count"] or 0) if row else 0
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    elapsed_s = time.monotonic() - started_at
    if clamped_count:
        print(f"[Profit History] Clamped absurd profit for {clamped_count} agents to ±{max_abs_profit}")
    print(f"[Profit History] Recorded profit for {inserted_count} agents in {elapsed_s:.2f}s")
    return inserted_count


async def record_profit_history():
    """Record profit history for all agents."""
    print("[Profit History] Task starting...")
    await asyncio.sleep(_env_int("PROFIT_HISTORY_STARTUP_DELAY_SECONDS", 90, minimum=0))

    while True:
        try:
            recorded_count = await asyncio.to_thread(_record_profit_history_once)
            if recorded_count:
                _maybe_schedule_profit_history_prune()
        except Exception as e:
            print(f"[Profit History Error] {e}")

        # Record at the same interval as position refresh (controlled by POSITION_REFRESH_INTERVAL)
        refresh_interval = _env_int("PROFIT_HISTORY_RECORD_INTERVAL", _env_int("POSITION_REFRESH_INTERVAL", 900, minimum=60), minimum=300)
        await asyncio.sleep(refresh_interval)


async def settle_polymarket_positions():
    """
    Background task to auto-settle resolved Polymarket positions.

    When a Polymarket market resolves, Gamma exposes `resolved` and `settlementPrice`.
    We treat each held outcome token as explicit spot-like inventory:
    - proceeds = quantity * settlementPrice
    - credit proceeds to agent cash
    - record an immutable settlement ledger entry
    - delete the position
    """
    from database import get_db_connection
    from price_fetcher import _polymarket_resolve
    global _POLYMARKET_SETTLEMENT_CURSOR

    # Wait a bit on startup before first settle pass
    await asyncio.sleep(_env_int("POLYMARKET_SETTLE_STARTUP_DELAY_SECONDS", 180, minimum=0))

    while True:
        try:
            interval_s = _env_int("POLYMARKET_SETTLE_INTERVAL", 300, minimum=60)
        except Exception:
            interval_s = 300

        try:
            _backfill_polymarket_position_metadata()
            conn = get_db_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT symbol, token_id, outcome, COUNT(*) AS position_count
                    FROM positions
                    WHERE market = 'polymarket' AND token_id IS NOT NULL AND token_id != ''
                    GROUP BY symbol, token_id, outcome
                """)
                contract_rows = cursor.fetchall()
                cursor.execute("SELECT COUNT(*) AS count FROM positions WHERE market = 'polymarket'")
                total_positions = int(cursor.fetchone()["count"] or 0)
            finally:
                conn.close()

            settled = 0
            skipped = 0
            cash_updates: dict[int, float] = {}
            settlement_rows: list[tuple[Any, ...]] = []
            delete_rows: list[tuple[int]] = []

            resolution_by_contract: dict[tuple[str, str, str], Optional[dict[str, Any]]] = {}
            due_contracts: list[tuple[str, str, str]] = []
            now_ts = time.time()
            max_contracts = _env_int("POLYMARKET_SETTLE_MAX_CONTRACTS_PER_RUN", 25, minimum=1)
            unresolved_recheck_s = _env_int("POLYMARKET_SETTLE_UNRESOLVED_RECHECK_SECONDS", 3600, minimum=interval_s)

            for row in contract_rows:
                token_id = row["token_id"]
                contract_key = (
                    str(row["symbol"] or ""),
                    str(token_id or ""),
                    str(row["outcome"] or ""),
                )
                if contract_key in resolution_by_contract:
                    continue
                retry_after = _POLYMARKET_SETTLEMENT_RECHECK_AFTER.get(contract_key, 0.0)
                if retry_after > now_ts:
                    resolution_by_contract[contract_key] = None
                    continue
                resolution_by_contract[contract_key] = None
                due_contracts.append(contract_key)

            due_contracts.sort()
            if len(due_contracts) > max_contracts:
                start = _POLYMARKET_SETTLEMENT_CURSOR % len(due_contracts)
                rotated = due_contracts[start:] + due_contracts[:start]
                unique_contracts = rotated[:max_contracts]
                _POLYMARKET_SETTLEMENT_CURSOR = (start + max_contracts) % len(due_contracts)
            else:
                unique_contracts = due_contracts
                _POLYMARKET_SETTLEMENT_CURSOR = 0

            for symbol, token_id, outcome in unique_contracts:
                resolution = await asyncio.to_thread(_polymarket_resolve, symbol, token_id=token_id, outcome=outcome)
                resolution_by_contract[(symbol, token_id, outcome)] = resolution
                if not resolution or not resolution.get("resolved"):
                    _POLYMARKET_SETTLEMENT_RECHECK_AFTER[(symbol, token_id, outcome)] = now_ts + unresolved_recheck_s
                else:
                    _POLYMARKET_SETTLEMENT_RECHECK_AFTER.pop((symbol, token_id, outcome), None)

            skipped_recheck = 0
            resolved_contracts = {
                contract_key: resolution
                for contract_key, resolution in resolution_by_contract.items()
                if resolution and resolution.get("resolved") and resolution.get("settlementPrice") is not None
            }
            for row in contract_rows:
                contract_key = (str(row["symbol"] or ""), str(row["token_id"] or ""), str(row["outcome"] or ""))
                position_count = int(row["position_count"] or 0)
                if contract_key in resolved_contracts:
                    continue
                skipped += position_count
                if _POLYMARKET_SETTLEMENT_RECHECK_AFTER.get(contract_key, 0.0) > now_ts:
                    skipped_recheck += position_count

            if resolved_contracts:
                conn = get_db_connection()
                try:
                    cursor = conn.cursor()
                    for (symbol, token_id, outcome), resolution in resolved_contracts.items():
                        cursor.execute(
                            """
                            SELECT id, agent_id, symbol, token_id, outcome, quantity, entry_price
                            FROM positions
                            WHERE market = 'polymarket' AND symbol = ? AND token_id = ? AND COALESCE(outcome, '') = COALESCE(?, '')
                            """,
                            (symbol, token_id, outcome),
                        )
                        for row in cursor.fetchall():
                            pos_id = row["id"]
                            agent_id = row["agent_id"]
                            qty = row["quantity"] or 0
                            settlement_price = resolution.get("settlementPrice")
                            proceeds = float(f"{(abs(qty) * float(settlement_price)):.6f}")
                            cash_updates[agent_id] = float(f"{cash_updates.get(agent_id, 0.0) + proceeds:.6f}")
                            settlement_rows.append((
                                pos_id,
                                agent_id,
                                row["symbol"],
                                row["token_id"],
                                row["outcome"],
                                qty,
                                row["entry_price"],
                                settlement_price,
                                proceeds,
                                resolution.get("market_slug"),
                                resolution.get("resolved_outcome"),
                                datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                                json.dumps(resolution),
                            ))
                            delete_rows.append((pos_id,))
                            settled += 1
                finally:
                    conn.close()

            if settlement_rows:
                conn = get_db_connection()
                try:
                    cursor = conn.cursor()
                    cursor.executemany(
                        "UPDATE agents SET cash = cash + ? WHERE id = ?",
                        [(proceeds, agent_id) for agent_id, proceeds in cash_updates.items()],
                    )
                    cursor.executemany("""
                        INSERT INTO polymarket_settlements
                        (position_id, agent_id, symbol, token_id, outcome, quantity, entry_price, settlement_price, proceeds, market_slug, resolved_outcome, resolved_at, source_data)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, settlement_rows)
                    cursor.executemany("DELETE FROM positions WHERE id = ?", delete_rows)
                    conn.commit()
                finally:
                    conn.close()

            print(
                "[Polymarket Settler] "
                f"positions={total_positions} unique_contracts={len(contract_rows)} contracts_due={len(due_contracts)} "
                f"contracts_checked={len(unique_contracts)} "
                f"settled={settled} skipped={skipped} recheck_cooldown={skipped_recheck}"
            )

        except Exception as e:
            print(f"[Polymarket Settler Error] {e}")

        await asyncio.sleep(interval_s)


async def settle_challenges_loop():
    """Background task to settle active challenges after their end time."""
    from challenges import settle_due_challenges

    await asyncio.sleep(15)

    while True:
        interval_s = _env_int("CHALLENGE_SETTLE_INTERVAL", 120, minimum=30)
        try:
            settled = await asyncio.to_thread(settle_due_challenges)
            if settled:
                print(f"[Challenge Settler] settled={len(settled)}")
        except Exception as e:
            print(f"[Challenge Settler Error] {e}")

        await asyncio.sleep(interval_s)


async def form_team_missions_loop():
    """Background task to form teams for active missions with enough participants."""
    from team_missions import form_due_team_missions

    await asyncio.sleep(18)

    while True:
        interval_s = _env_int("TEAM_MISSION_FORM_INTERVAL", 180, minimum=30)
        try:
            formed = await asyncio.to_thread(form_due_team_missions)
            if formed:
                print(f"[Team Mission Former] formed_missions={len(formed)}")
        except Exception as e:
            print(f"[Team Mission Former Error] {e}")

        await asyncio.sleep(interval_s)


async def score_team_contributions_loop():
    """Background task to score new team messages/submissions into contribution records."""
    from team_missions import score_team_contributions

    await asyncio.sleep(22)

    while True:
        interval_s = _env_int("TEAM_CONTRIBUTION_SCORE_INTERVAL", 180, minimum=30)
        try:
            result = await asyncio.to_thread(score_team_contributions)
            if result.get("inserted"):
                print(f"[Team Contribution Scorer] inserted={result['inserted']}")
        except Exception as e:
            print(f"[Team Contribution Scorer Error] {e}")

        await asyncio.sleep(interval_s)


async def settle_team_missions_loop():
    """Background task to settle team missions after their submission deadline."""
    from team_missions import settle_due_team_missions

    await asyncio.sleep(26)

    while True:
        interval_s = _env_int("TEAM_MISSION_SETTLE_INTERVAL", 180, minimum=30)
        try:
            settled = await asyncio.to_thread(settle_due_team_missions)
            if settled:
                print(f"[Team Mission Settler] settled={len(settled)}")
        except Exception as e:
            print(f"[Team Mission Settler Error] {e}")

        await asyncio.sleep(interval_s)


async def score_signal_quality_loop():
    """Background task to extract structured predictions and score signal quality."""
    from signal_quality import score_unscored_signals

    await asyncio.sleep(30)

    while True:
        interval_s = _env_int("SIGNAL_QUALITY_SCORE_INTERVAL", 240, minimum=30)
        try:
            result = await asyncio.to_thread(score_unscored_signals)
            if result.get("inserted"):
                print(f"[Signal Quality Scorer] inserted={result['inserted']}")
        except Exception as e:
            print(f"[Signal Quality Scorer Error] {e}")

        await asyncio.sleep(interval_s)


async def refresh_agent_metric_snapshots_loop():
    """Background task to snapshot agent metrics for experiment analysis."""
    from experiment_metrics import refresh_agent_metric_snapshots

    await asyncio.sleep(34)

    while True:
        interval_s = _env_int("AGENT_METRIC_SNAPSHOT_INTERVAL", 900, minimum=60)
        window_days = _env_int("AGENT_METRIC_SNAPSHOT_WINDOW_DAYS", 7, minimum=1)
        try:
            result = await asyncio.to_thread(refresh_agent_metric_snapshots, window_days)
            print(f"[Agent Metric Snapshots] inserted={result.get('inserted', 0)} window={result.get('window_key')}")
        except Exception as e:
            print(f"[Agent Metric Snapshots Error] {e}")

        await asyncio.sleep(interval_s)


async def build_network_edges_loop():
    """Background task to rebuild agent interaction network edges."""
    from experiment_metrics import build_network_edges

    await asyncio.sleep(38)

    while True:
        interval_s = _env_int("NETWORK_EDGES_BUILD_INTERVAL", 900, minimum=60)
        try:
            result = await asyncio.to_thread(build_network_edges)
            print(f"[Network Edges] inserted={result.get('inserted', 0)}")
        except Exception as e:
            print(f"[Network Edges Error] {e}")

        await asyncio.sleep(interval_s)


async def price_push_loop():
    """Phase 4.5: push-based market data via WebSocket.

    Off by default — opt in with ENABLE_PRICE_PUSH=true. When enabled,
    we hold a long-lived WebSocket subscription (Hyperliquid `allMids`
    for crypto) and stream each price tick straight to positions.
    The existing polling loop stays running as a fallback so the
    transition is non-destructive.
    """
    if not _env_bool("ENABLE_PRICE_PUSH", default=False):
        return

    from price_dispatch import apply_price_update
    from price_feed import HyperliquidWebSocketFeed, PriceTick

    feed = HyperliquidWebSocketFeed()

    def _on_tick(tick: PriceTick) -> None:
        try:
            apply_price_update(tick.symbol, tick.market, tick.price)
        except ValueError:
            return  # bad payload; drop without crashing the feed
        except Exception as exc:  # noqa: BLE001
            print(f"[Price Push Error] dispatch failed for {tick.symbol}: {exc}")

    try:
        await feed.start(on_tick=_on_tick)
        print("[Price Push] Hyperliquid WS subscriber started")
        # Sleep forever — feed.start scheduled the run loop as a Task.
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        await feed.close()
        raise
    except Exception as exc:  # noqa: BLE001
        print(f"[Price Push Error] {exc}")
        await feed.close()


async def refresh_leaderboard_snapshot_loop():
    """Phase 4.4: materialize the leaderboard every LEADERBOARD_SNAPSHOT_INTERVAL seconds.

    The /api/profit/history endpoint reads from `leaderboard_snapshot` and
    falls back to live computation when this table is empty, so a slow
    initial refresh just means the first few requests pay the old cost.
    """
    from leaderboard_snapshot import refresh_leaderboard_snapshot

    await asyncio.sleep(42)

    while True:
        interval_s = _env_int("LEADERBOARD_SNAPSHOT_INTERVAL", 30, minimum=10)
        top_n = _env_int("LEADERBOARD_SNAPSHOT_TOP_N", 200, minimum=20)
        try:
            result = await asyncio.to_thread(refresh_leaderboard_snapshot, top_n)
            print(
                "[Leaderboard Snapshot] refreshed: "
                f"total_agents={result.get('total_agents', 0)} "
                f"rows_per_metric={result.get('rows', {})}"
            )
        except Exception as e:
            print(f"[Leaderboard Snapshot Error] {e}")

        await asyncio.sleep(interval_s)


async def refresh_signal_feed_snapshot_loop():
    """Phase 4.4b: materialize the signal feed snapshot every SIGNAL_FEED_SNAPSHOT_INTERVAL seconds."""
    from signal_feed_snapshot import refresh_signal_feed_snapshot

    await asyncio.sleep(47)

    while True:
        interval_s = _env_int("SIGNAL_FEED_SNAPSHOT_INTERVAL", 30, minimum=10)
        top_n = _env_int("SIGNAL_FEED_SNAPSHOT_TOP_N", 200, minimum=20)
        try:
            result = await asyncio.to_thread(refresh_signal_feed_snapshot, top_n)
            print(
                "[Signal Feed Snapshot] refreshed: "
                f"combos={result.get('rows', {})}"
            )
        except Exception as e:
            print(f"[Signal Feed Snapshot Error] {e}")

        await asyncio.sleep(interval_s)


async def _symbol_research_loop():
    """Plan 14: global fleet-research refresh (env-gated FLEET_RESEARCH_ENABLED)."""
    from symbol_research import symbol_research_loop
    await symbol_research_loop()


async def _policy_feed_loop():
    """Plan 14 F7: Federal Register watchlists (env-gated POLICY_FEED_ENABLED)."""
    from policy_feed import policy_feed_loop
    await policy_feed_loop()


async def _fleet_planner_loop():
    """Plan 14: fleet orchestrator (FLEET_ENABLED gates new builds; supervision
    of live fleets keeps running regardless — §6.5.5)."""
    from fleet_planner import fleet_planner_loop
    await fleet_planner_loop()


async def _hot_issue_daemon_loop():
    """E2: hourly hot-issue watch over every user's RUN symbols
    (HOT_ISSUE_DAEMON_ENABLED gates each pass)."""
    from hot_issue_daemon import hot_issue_daemon_loop
    await hot_issue_daemon_loop()


async def _orphan_reclaim_loop():
    """Positions no run owns — attach the missing stop so the SL/TP watcher
    can see them (ORPHAN_RECLAIM_ENABLED gates each pass)."""
    from orphan_reclaim import orphan_reclaim_loop
    await orphan_reclaim_loop()


BACKGROUND_TASK_REGISTRY = {
    "prices": update_position_prices,
    "profit_history": record_profit_history,
    "polymarket_settlement": settle_polymarket_positions,
    "challenge_settlement": settle_challenges_loop,
    "team_mission_form": form_team_missions_loop,
    "team_contribution_score": score_team_contributions_loop,
    "team_mission_settlement": settle_team_missions_loop,
    "signal_quality_score": score_signal_quality_loop,
    "agent_metric_snapshots": refresh_agent_metric_snapshots_loop,
    "network_edges": build_network_edges_loop,
    "leaderboard_snapshot": refresh_leaderboard_snapshot_loop,
    "signal_feed_snapshot": refresh_signal_feed_snapshot_loop,
    "price_push": price_push_loop,
    "market_news": refresh_market_news_snapshots_loop,
    "macro_signals": refresh_macro_signal_snapshots_loop,
    "etf_flows": refresh_etf_flow_snapshots_loop,
    "stock_analysis": refresh_stock_analysis_snapshots_loop,
    "automation": automation_loop,
    "gateway_keepalive": gateway_keepalive_loop,
    "order_reconciler": order_reconciler_loop,
    "trading_runs": trading_run_loop,
    "run_reports": report_scheduler_loop,
    "subscription_enforcer": subscription_enforcer_loop,
    "risk_watcher": risk_watcher_loop,
    "resting_orders": resting_orders_loop,
    "liquidation_watch": liquidation_watch_loop,
    "psych_feed": psych_feed_loop,
    "scanner": scanner_loop,
    "social_feed": social_feed_loop,
    "factor_snapshots": factor_snapshot_loop,
    "confidence_calibration": confidence_calibration_loop,
    "watches": watch_loop,
    "symbol_research": _symbol_research_loop,
    "policy_feed": _policy_feed_loop,
    "fleet_planner": _fleet_planner_loop,
    "hot_issue_daemon": _hot_issue_daemon_loop,
    "orphan_reclaim": _orphan_reclaim_loop,
    "desk_brief": desk_brief_loop,
}


DEFAULT_BACKGROUND_TASKS = ",".join(BACKGROUND_TASK_REGISTRY.keys())


# ── Phase 4.6: worker role partitioning ───────────────────────────────────
# Each background task is tagged with exactly one of: prices, settlement,
# research. A worker process is started with SOOPPIY_WORKER_ROLE set to
# one of those values (or "all" for the historical single-process behavior)
# and only runs tasks matching that role. Lock keys are namespaced per role
# so role-segmented workers don't fight over the same singleton lock.

BACKGROUND_TASK_ROLES: dict[str, str] = {
    # prices — anything that pushes/polls market data into positions
    "prices":                  "prices",
    "price_push":              "prices",
    # settlement — anything that closes out positions / awards points / scores
    "polymarket_settlement":   "settlement",
    "challenge_settlement":    "settlement",
    "team_mission_form":       "settlement",
    "team_contribution_score": "settlement",
    "team_mission_settlement": "settlement",
    "signal_quality_score":    "settlement",
    # research — anything that builds derived snapshots / aggregates / intel
    "profit_history":          "research",
    "agent_metric_snapshots":  "research",
    "network_edges":           "research",
    "leaderboard_snapshot":    "research",
    "signal_feed_snapshot":    "research",
    "market_news":             "research",
    "macro_signals":           "research",
    "etf_flows":               "research",
    "stock_analysis":          "research",
    # automation — executes user-configured AI trading rules (Target 3)
    "automation":              "settlement",
    # IBKR session keepalive — tickle/reauth so live gateways stay usable
    "gateway_keepalive":       "settlement",
    # broker-order reconciler — confirm SUBMITTED orders' final fills
    "order_reconciler":        "settlement",
    # trading runs — Plan 10 run lifecycle scheduler (dedicated executor for
    # LLM cycles; gated by AUTO_TRADING_ENABLED)
    "trading_runs":            "settlement",
    # unowned positions — attach the missing stop so the SL/TP watcher sees them
    "orphan_reclaim":          "settlement",
    # trading-run P&L digests + delivery retry sweep (Plan 10 Phase 4)
    "run_reports":             "settlement",
    # pause runs whose owner's subscription lapsed (Plan 10 Phase 5)
    "subscription_enforcer":   "settlement",
    # risk engine — closes positions at stop-loss/take-profit (Phase 1)
    "risk_watcher":            "settlement",
    # terminals' limit-order fill watcher — executes trades, so settlement
    "resting_orders":          "settlement",
    # settlement, not prices: it reads marks but its job is closing risk, and
    # it must run in the same process as the SL/TP watcher it escalates past.
    "liquidation_watch":       "settlement",
    # psych feed — crowd-psychology snapshots: F&G, spikes, shock, odds (Phase 2)
    "psych_feed":              "research",
    # scanner — which-coin candidates: volume surge, mentions, listings (Phase 4)
    "scanner":                 "research",
    # social feed — FB (SEA) / X (elsewhere) posts -> per-symbol tilt (Plan 11 F5)
    "social_feed":             "research",
    # factor snapshots — live-only factor history for confluence validation
    "factor_snapshots":        "research",
    # confidence calibration scoreboard — Brier vs outcomes, daily (Step 0)
    "confidence_calibration":  "research",
    # personal watch functions — user metric conditions -> alerts (Plan 06 C3)
    "watches":                 "research",
    # Plan 14 — symbol_research is pinned to settlement so it shares a process
    # (and the process-local Yahoo cooldown dict) with run cycles + the watcher.
    "symbol_research":         "settlement",
    # Plan 14 F7 — Federal Register policy watchlists (attention factor)
    "policy_feed":             "research",
    # Plan 14 — fleet orchestrator lives with the runs engine (it creates
    # runs the run loop must immediately see)
    "fleet_planner":           "settlement",
    "hot_issue_daemon":        "research",
    # desk brief / monthly review — derived reporting, never touches trading
    "desk_brief":              "research",
}

WORKER_ROLES: tuple[str, ...] = ("all", "prices", "settlement", "research")


def tasks_for_role(role: str) -> list[str]:
    """Return the task names that belong to ``role`` ('all' = every task)."""
    if role == "all":
        return list(BACKGROUND_TASK_REGISTRY.keys())
    if role not in WORKER_ROLES:
        raise ValueError(
            f"Unknown worker role {role!r}; expected one of {WORKER_ROLES}"
        )
    return [name for name, r in BACKGROUND_TASK_ROLES.items() if r == role]


def get_worker_lock_key(role: str) -> str:
    """Singleton-lock key for a given worker role.

    Returns a distinct key per role so a 'prices' worker and a 'settlement'
    worker can run side-by-side without one blocking the other.
    """
    if role not in WORKER_ROLES:
        raise ValueError(
            f"Unknown worker role {role!r}; expected one of {WORKER_ROLES}"
        )
    if role == "all":
        # Preserve the legacy single-process lock name for backward compat —
        # any operator who hasn't set SOOPPIY_WORKER_ROLE keeps the same lock.
        return "worker:singleton"
    return f"worker:singleton:{role}"


def background_tasks_enabled_for_api() -> bool:
    """API workers default to HTTP-only; run worker.py for background loops."""
    return _env_bool("SOOPPIY_API_BACKGROUND_TASKS", False)


def get_enabled_background_task_names() -> list[str]:
    """Resolve the task list this worker should run.

    Order of operations:
      1. Pick the role (SOOPPIY_WORKER_ROLE, default "all").
      2. Filter the registry by role membership.
      3. Intersect with SOOPPIY_BACKGROUND_TASKS if set — the explicit
         task list still wins, so an operator can disable a specific
         task within a role without changing code.
    """
    role = os.getenv("SOOPPIY_WORKER_ROLE", "all").strip() or "all"
    if role not in WORKER_ROLES:
        raise ValueError(
            f"Unknown worker role {role!r}; expected one of {WORKER_ROLES}"
        )
    role_allowed = set(tasks_for_role(role))

    raw = os.getenv("SOOPPIY_BACKGROUND_TASKS", DEFAULT_BACKGROUND_TASKS)
    requested = [item.strip() for item in raw.split(",") if item.strip()]
    return [
        name for name in requested
        if name in BACKGROUND_TASK_REGISTRY and name in role_allowed
    ]


def start_background_tasks(logger: Optional[Any] = None) -> list[asyncio.Task]:
    started: list[asyncio.Task] = []
    for name in get_enabled_background_task_names():
        task_func = BACKGROUND_TASK_REGISTRY[name]
        if logger:
            logger.info("Starting background task: %s", name)
        started.append(asyncio.create_task(task_func(), name=f"sooppiy:{name}"))
    return started
