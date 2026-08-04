import math
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import tasks as task_runtime
from fastapi import FastAPI, Header, HTTPException

from cache import get_json, set_json
from database import get_db_connection
from experiment_events import record_event
from routes_models import FollowRequest
from routes_shared import (
    LEADERBOARD_CACHE_KEY_PREFIX,
    LEADERBOARD_CACHE_TTL_SECONDS,
    POSITIONS_CACHE_TTL_SECONDS,
    PRICE_CACHE_KEY_PREFIX,
    PRICE_QUOTE_CACHE_TTL_SECONDS,
    RouteContext,
    TRENDING_CACHE_KEY,
    allow_sync_price_fetch_in_api,
    check_price_api_rate_limit,
    clamp_profit_for_display,
    decorate_polymarket_item,
    position_price_cache_key,
    push_agent_message,
    resolve_position_prices,
    utc_now_iso_z,
    validate_market,
)
from backtest import run_backtest
from services import _get_agent_by_token
from utils import _extract_token


INITIAL_CAPITAL = 100000.0


def _row_value(row, key: str):
    """Read an optional column from a DB row. Columns added by later migrations
    may be absent on a stale schema, and sqlite3.Row raises rather than
    returning None for an unknown key."""
    try:
        return row[key]
    except (KeyError, IndexError):
        return None


def profit_percent_for_display(profit: float, deposited: float) -> float:
    base_capital = INITIAL_CAPITAL + (deposited or 0)
    if base_capital <= 0:
        return 0.0
    return clamp_profit_for_display(profit) / base_capital * 100


def _annualized_sharpe(history: list[dict]) -> float:
    """Annualized Sharpe ratio computed from profit_history snapshots.

    Returns the mean of per-snapshot percent returns divided by their stddev,
    scaled by sqrt(snapshots_per_year). Snapshots are taken every 5 minutes by
    the background worker (POSITION_REFRESH_INTERVAL default 300s), so the
    annualization factor is sqrt(snapshots/year) ≈ sqrt(105_120). Risk-free
    rate is assumed zero (paper trading). Needs at least 3 snapshots; returns
    0.0 otherwise.
    """
    if not history or len(history) < 3:
        return 0.0
    # Compute simple per-step deltas against running capital base. Use profit
    # deltas since `profit` in profit_history is cumulative dollars over base.
    deltas: list[float] = []
    base = INITIAL_CAPITAL
    prev = float(history[0].get('profit') or 0.0)
    for h in history[1:]:
        cur = float(h.get('profit') or 0.0)
        deltas.append((cur - prev) / base)
        prev = cur
    if len(deltas) < 2:
        return 0.0
    mean = sum(deltas) / len(deltas)
    variance = sum((d - mean) ** 2 for d in deltas) / (len(deltas) - 1)
    stddev = math.sqrt(variance) if variance > 0 else 0.0
    if stddev == 0:
        return 0.0
    # Snapshots per year at 5-minute cadence.
    snapshots_per_year = 365 * 24 * 12
    sharpe = (mean / stddev) * math.sqrt(snapshots_per_year)
    # Clamp to a sane range so a single huge outlier can't dominate.
    return max(-10.0, min(10.0, sharpe))


def _rankable(alias: str = "a") -> str:
    """The one definition of a rankable agent, shared with the materialized
    snapshot so the three board paths cannot drift apart."""
    from leaderboard_snapshot import rankable_where
    return rankable_where(alias)


def register_trading_routes(app: FastAPI, ctx: RouteContext) -> None:
    @app.get('/api/profit/history')
    async def get_profit_history(
        limit: int = 10,
        days: int = 30,
        offset: int = 0,
        include_history: bool = True,
        metric: str = 'return',
    ):
        days = max(1, min(days, 365))
        limit = max(1, min(limit, 50))
        offset = max(0, offset)
        metric = (metric or 'return').strip().lower()
        if metric not in {'return', 'risk', 'collaboration', 'quality'}:
            metric = 'return'

        cache_key = (limit, days, offset, include_history, metric)
        now_ts = time.time()
        redis_cache_key = (
            f'{LEADERBOARD_CACHE_KEY_PREFIX}:'
            f'metric={metric}:'
            f'limit={limit}:days={days}:offset={offset}:history={int(include_history)}'
        )

        cached_payload = get_json(redis_cache_key)
        if isinstance(cached_payload, dict):
            ctx.leaderboard_cache[cache_key] = (now_ts, cached_payload)
            return cached_payload

        cached = ctx.leaderboard_cache.get(cache_key)
        if cached and now_ts - cached[0] < LEADERBOARD_CACHE_TTL_SECONDS:
            return cached[1]

        conn = get_db_connection()
        cursor = conn.cursor()

        cutoff_dt = datetime.now(timezone.utc) - timedelta(days=days)
        cutoff = cutoff_dt.isoformat().replace('+00:00', 'Z')
        live_snapshot_recorded_at = utc_now_iso_z()

        cursor.execute(
            """
            SELECT COUNT(*) AS total
            FROM agents a
            WHERE """ + _rankable() + """
            """
        )
        total_row = cursor.fetchone()
        total = total_row['total'] if total_row else 0

        # Phase 4.4: try the materialized leaderboard_snapshot first.
        # The background worker (refresh_leaderboard_snapshot_loop) keeps
        # this table fresh every 30s; we still fall through to the live
        # aggregate when the snapshot is empty (first boot or worker off)
        # or the page is past the snapshot's top_n cap.
        snapshot_rows = None
        try:
            from leaderboard_snapshot import read_leaderboard_snapshot
            snapshot_rows = read_leaderboard_snapshot(metric, limit, offset)
        except Exception:
            snapshot_rows = None
        if snapshot_rows is not None and len(snapshot_rows) > 0:
            top_agents = [
                {
                    'agent_id': row['agent_id'],
                    'name': row['name'],
                    'deposited': float(row.get('deposited') or 0),
                    'profit': clamp_profit_for_display(float(row.get('profit') or 0)),
                    'profit_percent': float(row.get('profit_percent') or 0),
                    'recorded_at': row.get('recorded_at') or live_snapshot_recorded_at,
                    'trade_count': int(row.get('trade_count') or 0),
                    'risk_adjusted_score': float(row.get('risk_adjusted_score') or 0),
                    'collaboration_score': float(row.get('collaboration_score') or 0),
                    'quality_score_avg': float(row.get('quality_score_avg') or 0),
                    'metric_snapshot': {
                        'id': row.get('metric_snapshot_id'),
                        'window_key': row.get('metric_window_key'),
                        'window_start_at': row.get('metric_window_start_at'),
                        'window_end_at': row.get('metric_window_end_at'),
                        'max_drawdown': float(row.get('max_drawdown') or 0),
                        'reply_count': int(row.get('reply_count') or 0),
                        'accepted_reply_count': int(row.get('accepted_reply_count') or 0),
                        'citation_count': int(row.get('citation_count') or 0),
                        'adoption_count': int(row.get('adoption_count') or 0),
                        'quality_score_avg': float(row.get('quality_score_avg') or 0),
                    } if row.get('metric_snapshot_id') is not None else {},
                }
                for row in snapshot_rows
            ]
            # Fast path joins per-agent enrichment below (history / sharpe /
            # recent activity / backtest_validated) — same code as the live
            # path, but on the limit-page only.
            _process_top_agents = True
        else:
            _process_top_agents = False

        order_by = {
            'return': 'profit_percent DESC',
            'risk': 'risk_adjusted_score DESC',
            'collaboration': 'collaboration_score DESC',
            'quality': 'quality_score_avg DESC',
        }[metric]
        if _process_top_agents:
            # Skip the heavy CTE — top_agents was filled from the snapshot.
            pass
        else:
            cursor.execute(
                f"""
                WITH latest_snapshots AS (
                SELECT ams.*
                FROM agent_metric_snapshots ams
                JOIN (
                    SELECT agent_id, MAX(window_end_at) AS latest_window_end_at
                    FROM agent_metric_snapshots
                    GROUP BY agent_id
                ) latest
                  ON latest.agent_id = ams.agent_id
                 AND latest.latest_window_end_at = ams.window_end_at
            ),
            agent_profit AS (
                SELECT
                    a.id AS agent_id,
                    a.name,
                    COALESCE(a.deposited, 0) AS deposited,
                    (
                        COALESCE(a.cash, 0) +
                        COALESCE(
                            SUM(
                                CASE
                                    WHEN p.current_price IS NULL THEN p.entry_price * ABS(p.quantity)
                                    WHEN p.side = 'long' THEN p.current_price * ABS(p.quantity)
                                    ELSE (2 * p.entry_price - p.current_price) * ABS(p.quantity)
                                END
                            ),
                            0
                        ) -
                        (? + COALESCE(a.deposited, 0))
                    ) AS profit,
                    (
                        (
                            COALESCE(a.cash, 0) +
                            COALESCE(
                                SUM(
                                    CASE
                                        WHEN p.current_price IS NULL THEN p.entry_price * ABS(p.quantity)
                                        WHEN p.side = 'long' THEN p.current_price * ABS(p.quantity)
                                        ELSE (2 * p.entry_price - p.current_price) * ABS(p.quantity)
                                    END
                                ),
                                0
                            ) -
                            (? + COALESCE(a.deposited, 0))
                        ) / NULLIF((? + COALESCE(a.deposited, 0)), 0) * 100
                    ) AS profit_percent,
                    (
                        SELECT MAX(ph.recorded_at)
                        FROM profit_history ph
                        WHERE ph.agent_id = a.id AND ph.recorded_at >= ?
                    ) AS recorded_at,
                    (
                        SELECT COUNT(*)
                        FROM signals ops
                        WHERE ops.agent_id = a.id AND ops.message_type = 'operation'
                    ) AS trade_count
                FROM agents a
                LEFT JOIN positions p ON p.agent_id = a.id
                -- Same rule as the materialized snapshot; see
                -- leaderboard_snapshot.rankable_where. This fallback runs
                -- whenever the snapshot is empty or the page is past its
                -- top_n, so leaving it unfiltered put the deploy-check agents
                -- straight back on the board.
                WHERE {_rankable()}
                GROUP BY a.id, a.name, a.cash, a.deposited
            )
            SELECT
                ap.*,
                COALESCE(ls.max_drawdown, 0) AS max_drawdown,
                COALESCE(ls.reply_count, 0) AS reply_count,
                COALESCE(ls.accepted_reply_count, 0) AS accepted_reply_count,
                COALESCE(ls.citation_count, 0) AS citation_count,
                COALESCE(ls.adoption_count, 0) AS adoption_count,
                COALESCE(ls.quality_score_avg, 0) AS quality_score_avg,
                ls.id AS metric_snapshot_id,
                ls.window_key AS metric_window_key,
                ls.window_start_at AS metric_window_start_at,
                ls.window_end_at AS metric_window_end_at,
                (ap.profit_percent - COALESCE(ls.max_drawdown, 0)) AS risk_adjusted_score,
                (
                    COALESCE(ls.reply_count, 0) +
                    COALESCE(ls.accepted_reply_count, 0) * 2 +
                    COALESCE(ls.citation_count, 0) +
                    COALESCE(ls.adoption_count, 0)
                ) AS collaboration_score
            FROM agent_profit ap
            LEFT JOIN latest_snapshots ls ON ls.agent_id = ap.agent_id
            ORDER BY {order_by}, ap.profit_percent DESC, ap.agent_id ASC
            LIMIT ? OFFSET ?
            """,
                (INITIAL_CAPITAL, INITIAL_CAPITAL, INITIAL_CAPITAL, cutoff, limit, offset),
            )
            top_agents = [
                {
                    'agent_id': row['agent_id'],
                    'name': row['name'],
                    'deposited': row['deposited'],
                    'profit': clamp_profit_for_display(row['profit']),
                    'profit_percent': row['profit_percent'] or 0,
                    'recorded_at': row['recorded_at'] or live_snapshot_recorded_at,
                    'trade_count': row['trade_count'] or 0,
                    'risk_adjusted_score': float(row['risk_adjusted_score'] or 0),
                    'collaboration_score': float(row['collaboration_score'] or 0),
                    'quality_score_avg': float(row['quality_score_avg'] or 0),
                    'metric_snapshot': {
                        'id': row['metric_snapshot_id'],
                        'window_key': row['metric_window_key'],
                        'window_start_at': row['metric_window_start_at'],
                        'window_end_at': row['metric_window_end_at'],
                        'max_drawdown': row['max_drawdown'],
                        'reply_count': row['reply_count'],
                        'accepted_reply_count': row['accepted_reply_count'],
                        'citation_count': row['citation_count'],
                        'adoption_count': row['adoption_count'],
                        'quality_score_avg': row['quality_score_avg'],
                    } if row['metric_snapshot_id'] is not None else {},
                }
                for row in cursor.fetchall()
            ]

        if not top_agents:
            conn.close()
            result = {
                'top_agents': [],
                'total': total,
                'limit': limit,
                'offset': offset,
                'has_more': False,
            }
            ctx.leaderboard_cache[cache_key] = (now_ts, result)
            set_json(redis_cache_key, result, ttl_seconds=LEADERBOARD_CACHE_TTL_SECONDS)
            return result

        agent_ids = [agent['agent_id'] for agent in top_agents]
        placeholders = ','.join('?' for _ in agent_ids)

        result = []
        for agent in top_agents:
            # Always fetch profit_history for Sharpe; reuse for chart points
            # when `include_history` is True.
            cursor.execute(
                """
                SELECT profit, recorded_at
                FROM (
                    SELECT profit, recorded_at
                    FROM profit_history
                    WHERE agent_id = ? AND recorded_at >= ?
                    ORDER BY recorded_at DESC
                    LIMIT 2000
                ) recent_history
                ORDER BY recorded_at ASC
                """,
                (agent['agent_id'], cutoff),
            )
            history = [dict(h) for h in cursor.fetchall()]
            sharpe = _annualized_sharpe(history)

            history_points = []
            if include_history:
                history_points = [
                    {
                        'profit': clamp_profit_for_display(h['profit']),
                        'profit_percent': profit_percent_for_display(h['profit'], agent['deposited']),
                        'recorded_at': h['recorded_at'],
                    }
                    for h in history
                ]
                if not history_points or history_points[-1]['recorded_at'] != live_snapshot_recorded_at:
                    history_points.append({
                        'profit': clamp_profit_for_display(agent['profit']),
                        'profit_percent': profit_percent_for_display(agent['profit'], agent['deposited']),
                        'recorded_at': live_snapshot_recorded_at,
                    })

            current_profit_percent = profit_percent_for_display(agent['profit'], agent['deposited'])
            metric_snapshot = agent['metric_snapshot']
            max_drawdown = float(metric_snapshot.get('max_drawdown') or 0) if metric_snapshot else 0.0
            result.append({
                'agent_id': agent['agent_id'],
                'name': agent['name'],
                'deposited': agent['deposited'],
                'total_profit': clamp_profit_for_display(agent['profit']),
                'current_profit': clamp_profit_for_display(agent['profit']),
                'total_profit_percent': current_profit_percent,
                'current_profit_percent': current_profit_percent,
                'trade_count': agent['trade_count'],
                'sharpe': sharpe,
                'max_drawdown': max_drawdown,
                'sample_size': len(history),
                'recent_strategy_count_7d': 0,
                'recent_discussion_count_7d': 0,
                'recent_activity_at': agent['recorded_at'],
                'latest_strategy_signal_id': None,
                'latest_strategy_title': None,
                'latest_discussion_signal_id': None,
                'latest_discussion_title': None,
                'risk_adjusted_score': agent['risk_adjusted_score'],
                'collaboration_score': agent['collaboration_score'],
                'quality_score_avg': agent['quality_score_avg'],
                'metric_snapshot': metric_snapshot,
                'history': history_points,
            })

        cursor.execute(
            f"""
            SELECT agent_id, message_type, COUNT(*) as count, MAX(created_at) as last_created_at
            FROM signals
            WHERE agent_id IN ({placeholders})
              AND message_type IN ('strategy', 'discussion')
              AND created_at >= datetime('now', '-7 day')
            GROUP BY agent_id, message_type
            """,
            agent_ids,
        )
        for row in cursor.fetchall():
            for item in result:
                if item['agent_id'] != row['agent_id']:
                    continue
                if row['message_type'] == 'strategy':
                    item['recent_strategy_count_7d'] = row['count']
                elif row['message_type'] == 'discussion':
                    item['recent_discussion_count_7d'] = row['count']
                if row['last_created_at'] and row['last_created_at'] > (item['recent_activity_at'] or ''):
                    item['recent_activity_at'] = row['last_created_at']
                break

        cursor.execute(
            f"""
            SELECT agent_id, message_type, signal_id, title, created_at
            FROM signals
            WHERE agent_id IN ({placeholders})
              AND message_type IN ('strategy', 'discussion')
            ORDER BY created_at DESC
            """,
            agent_ids,
        )
        seen_latest = set()
        for row in cursor.fetchall():
            key = (row['agent_id'], row['message_type'])
            if key in seen_latest:
                continue
            seen_latest.add(key)
            for item in result:
                if item['agent_id'] != row['agent_id']:
                    continue
                if row['message_type'] == 'strategy':
                    item['latest_strategy_signal_id'] = row['signal_id']
                    item['latest_strategy_title'] = row['title']
                else:
                    item['latest_discussion_signal_id'] = row['signal_id']
                    item['latest_discussion_title'] = row['title']
                if row['created_at'] and row['created_at'] > (item['recent_activity_at'] or ''):
                    item['recent_activity_at'] = row['created_at']
                break

        # Annotate each entry with backtest_validated_strategy flag
        for item in result:
            item['backtest_validated_strategy'] = False

        try:
            cursor.execute(
                f"""
                SELECT DISTINCT agent_id
                FROM strategies
                WHERE agent_id IN ({placeholders})
                  AND is_active=1
                  AND backtest_validated=1
                """,
                agent_ids,
            )
            validated_ids = {row['agent_id'] for row in cursor.fetchall()}
            for item in result:
                if item['agent_id'] in validated_ids:
                    item['backtest_validated_strategy'] = True
        except Exception:
            pass  # strategies table may not exist in very old DBs

        conn.close()
        payload = {
            'top_agents': result,
            'total': total,
            'limit': limit,
            'offset': offset,
            'has_more': offset + len(result) < total,
        }
        ctx.leaderboard_cache[cache_key] = (now_ts, payload)
        set_json(redis_cache_key, payload, ttl_seconds=LEADERBOARD_CACHE_TTL_SECONDS)
        return payload

    @app.get('/api/leaderboard/position-pnl')
    async def get_leaderboard_position_pnl(limit: int = 10):
        conn = get_db_connection()
        cursor = conn.cursor()
        # Same rankable rule as every other board path.
        cursor.execute('SELECT a.id, a.name FROM agents a WHERE ' + _rankable())
        agents = cursor.fetchall()

        result = []
        for agent in agents:
            agent_id = agent['id']
            cursor.execute(
                """
                SELECT symbol, market, token_id, outcome, side, quantity, entry_price, current_price
                FROM positions WHERE agent_id = ?
                """,
                (agent_id,),
            )
            positions = cursor.fetchall()

            total_position_pnl = 0
            for pos in positions:
                current_price = pos['current_price']
                if current_price and pos['entry_price']:
                    if pos['side'] == 'long':
                        pnl = (current_price - pos['entry_price']) * abs(pos['quantity'])
                    else:
                        pnl = (pos['entry_price'] - current_price) * abs(pos['quantity'])
                    total_position_pnl += pnl

            cursor.execute(
                """
                SELECT COUNT(*) as count FROM signals
                WHERE agent_id = ? AND message_type = 'operation'
                """,
                (agent_id,),
            )
            trade_count = cursor.fetchone()['count']

            result.append({
                'agent_id': agent_id,
                'name': agent['name'],
                'position_pnl': total_position_pnl,
                'trade_count': trade_count,
                'position_count': len(positions),
            })

        conn.close()
        return {'top_agents': sorted(result, key=lambda item: item['position_pnl'], reverse=True)[:limit]}

    @app.get('/api/trending')
    async def get_trending_symbols(limit: int = 10):
        cached = get_json(TRENDING_CACHE_KEY)
        if isinstance(cached, list):
            return {'trending': cached[: max(1, limit)]}

        if task_runtime.trending_cache:
            return {'trending': task_runtime.trending_cache[: max(1, limit)]}

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT symbol, market, token_id, outcome, COUNT(DISTINCT agent_id) as holder_count
            FROM positions
            GROUP BY symbol, market, token_id, outcome
            ORDER BY holder_count DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = cursor.fetchall()

        result = []
        for row in rows:
            cursor.execute(
                """
                SELECT current_price FROM positions
                WHERE symbol = ? AND market = ? AND COALESCE(token_id, '') = COALESCE(?, '')
                LIMIT 1
                """,
                (row['symbol'], row['market'], row['token_id']),
            )
            price_row = cursor.fetchone()
            result.append({
                'symbol': row['symbol'],
                'market': row['market'],
                'token_id': row['token_id'],
                'outcome': row['outcome'],
                'holder_count': row['holder_count'],
                'current_price': price_row['current_price'] if price_row else None,
            })

        conn.close()
        set_json(TRENDING_CACHE_KEY, result, ttl_seconds=300)
        return {'trending': result}

    @app.get('/api/price')
    async def get_price(
        symbol: str,
        market: str = 'us-stock',
        token_id: Optional[str] = None,
        outcome: Optional[str] = None,
        authorization: str = Header(None),
    ):
        token = _extract_token(authorization)
        if not token:
            raise HTTPException(status_code=401, detail='Invalid token')

        agent = _get_agent_by_token(token)
        if not agent:
            raise HTTPException(status_code=401, detail='Invalid token')

        if not check_price_api_rate_limit(ctx, agent['id']):
            raise HTTPException(status_code=429, detail='Rate limit exceeded. Please wait 1 second between requests.')

        market = validate_market(market)
        now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        normalized_symbol = symbol.upper() if market == 'us-stock' else symbol
        cache_key = (
            normalized_symbol,
            market,
            (token_id or '').strip(),
            (outcome or '').strip(),
        )
        redis_cache_key = (
            f'{PRICE_CACHE_KEY_PREFIX}:'
            f'symbol={normalized_symbol}:'
            f'market={market}:'
            f"token_id={(token_id or '').strip() or 'none'}:"
            f"outcome={(outcome or '').strip() or 'none'}"
        )

        cached_payload = get_json(redis_cache_key)
        if isinstance(cached_payload, dict):
            ctx.price_quote_cache[cache_key] = (time.time(), cached_payload)
            return cached_payload

        cached = ctx.price_quote_cache.get(cache_key)
        now_ts = time.time()
        if cached and now_ts - cached[0] < PRICE_QUOTE_CACHE_TTL_SECONDS:
            return cached[1]

        price = None
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT current_price
                FROM positions
                WHERE symbol = ? AND market = ? AND COALESCE(token_id, '') = COALESCE(?, '')
                  AND current_price IS NOT NULL
                ORDER BY opened_at DESC
                LIMIT 1
                """,
                (normalized_symbol, market, token_id),
            )
            row = cursor.fetchone()
            if row:
                price = row['current_price']
        finally:
            conn.close()

        if price is None and allow_sync_price_fetch_in_api():
            from price_fetcher import get_price_from_market

            price = get_price_from_market(normalized_symbol, now, market, token_id=token_id, outcome=outcome)
        if price is None:
            raise HTTPException(status_code=404, detail='Price not available')

        payload = {'symbol': normalized_symbol, 'market': market, 'token_id': token_id, 'outcome': outcome, 'price': price}
        if market == 'polymarket':
            decorate_polymarket_item(payload, fetch_remote=allow_sync_price_fetch_in_api())
        ctx.price_quote_cache[cache_key] = (now_ts, payload)
        set_json(redis_cache_key, payload, ttl_seconds=PRICE_QUOTE_CACHE_TTL_SECONDS)
        return payload

    @app.get('/api/positions')
    async def get_my_positions(authorization: str = Header(None)):
        token = _extract_token(authorization)
        agent = _get_agent_by_token(token)
        if not agent:
            raise HTTPException(status_code=401, detail='Invalid token')

        now_ts = time.time()
        cached = ctx.positions_cache.get(agent['id'])
        if cached and now_ts - cached[0] < POSITIONS_CACHE_TTL_SECONDS:
            return cached[1]

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT p.*, a.name as leader_name, r.status as run_status
            FROM positions p
            LEFT JOIN agents a ON a.id = p.leader_id
            LEFT JOIN trading_runs r ON r.id = p.run_id
            WHERE p.agent_id = ?
            ORDER BY p.opened_at DESC
            """,
            (agent['id'],),
        )
        rows = cursor.fetchall()
        conn.close()

        positions = []
        now_str = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        resolved_prices = resolve_position_prices(rows, now_str)

        for row in rows:
            current_price = resolved_prices.get(position_price_cache_key(row))
            pnl = None
            if current_price and row['entry_price']:
                if row['side'] == 'long':
                    pnl = (current_price - row['entry_price']) * abs(row['quantity'])
                else:
                    pnl = (row['entry_price'] - current_price) * abs(row['quantity'])

            source = 'self' if row['leader_id'] is None else f"copied:{row['leader_id']}"
            positions.append({
                'id': row['id'],
                'symbol': row['symbol'],
                'market': row['market'],
                'token_id': row['token_id'],
                'outcome': row['outcome'],
                'side': row['side'],
                'quantity': row['quantity'],
                'entry_price': row['entry_price'],
                'current_price': current_price,
                'pnl': pnl,
                # Exit protection set by the risk gate / automation — the
                # positions view shows it per row (Plan 11 F3a).
                'stop_loss': _row_value(row, 'stop_loss'),
                'take_profit': _row_value(row, 'take_profit'),
                'source': source,
                'opened_at': row['opened_at'],
                # Who is actually watching this position. A run releases its
                # run_id on stop (run_engine: "close it by hand"), and a manual
                # terminal fill never had one — so an unowned row is normal,
                # but it was invisible: prod position 13 sat unowned with no
                # stop for 7 days at −4%. managed_by is null for those, and
                # `unprotected` is the one that needs a badge — nothing is
                # watching AND there is no exit level to watch for.
                'managed_by': (f"run:{_row_value(row, 'run_id')}"
                               if _row_value(row, 'run_id')
                               and _row_value(row, 'run_status') in
                               ('armed', 'running', 'paused', 'stopping')
                               else None),
                'unprotected': (_row_value(row, 'stop_loss') is None
                                and _row_value(row, 'take_profit') is None),
            })
            if positions[-1]['market'] == 'polymarket':
                decorate_polymarket_item(positions[-1], fetch_remote=False)

        payload = {'positions': positions, 'cash': agent.get('cash', 100000.0)}
        ctx.positions_cache[agent['id']] = (now_ts, payload)
        return payload

    @app.patch('/api/positions/{position_id}/tpsl')
    async def set_position_tpsl(position_id: int, data: dict,
                                authorization: str = Header(None)):
        """Set or clear stop-loss / take-profit on one of the agent's own
        positions — the terminals' TP/SL editor (ga TpSlEditModal semantics).

        Three-state body: a key that is ABSENT keeps the current value, an
        explicit null CLEARS it, a number SETS it. Values are validated
        side-aware against the live price (long: SL below / TP above; short
        inverted) so a level that would trigger instantly is refused.
        Enforcement is the existing risk-watcher (risk_engine
        run_sltp_watcher_tick) at price-poll granularity.
        """
        token = _extract_token(authorization)
        agent = _get_agent_by_token(token)
        if not agent:
            raise HTTPException(status_code=401, detail='Invalid token')
        if not isinstance(data, dict):
            raise HTTPException(status_code=422, detail='Body must be an object')
        if not ('stop_loss' in data or 'take_profit' in data):
            raise HTTPException(status_code=422,
                                detail='Provide stop_loss and/or take_profit')

        def _parse(key: str):
            # (present, value) — value None means explicit clear.
            if key not in data:
                return False, None
            raw = data[key]
            if raw is None:
                return True, None
            try:
                val = float(raw)
            except (TypeError, ValueError):
                raise HTTPException(status_code=422, detail=f'{key} must be a number or null')
            if not math.isfinite(val) or val <= 0:
                raise HTTPException(status_code=422, detail=f'{key} must be a positive price')
            return True, val

        sl_set, sl = _parse('stop_loss')
        tp_set, tp = _parse('take_profit')

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """SELECT id, agent_id, side, quantity, entry_price, current_price,
                          stop_loss, take_profit
                   FROM positions WHERE id = ?""", (position_id,))
            row = cursor.fetchone()
            if not row or row['agent_id'] != agent['id']:
                # 404 for both missing and foreign rows — don't leak existence.
                raise HTTPException(status_code=404, detail='Position not found')
            if not row['quantity']:
                raise HTTPException(status_code=409, detail='Position is closed')

            anchor = row['current_price'] or row['entry_price']
            is_short = row['side'] != 'long'
            if anchor:
                if sl is not None and (sl <= anchor if is_short else sl >= anchor):
                    raise HTTPException(
                        status_code=422,
                        detail='stop_loss would trigger immediately at the current price')
                if tp is not None and (tp >= anchor if is_short else tp <= anchor):
                    raise HTTPException(
                        status_code=422,
                        detail='take_profit would trigger immediately at the current price')

            sets, params = [], []
            if sl_set:
                sets.append('stop_loss = ?')
                params.append(sl)
            if tp_set:
                sets.append('take_profit = ?')
                params.append(tp)
            params.append(position_id)
            cursor.execute(f"UPDATE positions SET {', '.join(sets)} WHERE id = ?", params)
            conn.commit()
        finally:
            conn.close()

        # Drop the 10s positions cache so the editor reflects the change now.
        ctx.positions_cache.pop(agent['id'], None)
        return {
            'id': position_id,
            'stop_loss': sl if sl_set else _row_value(row, 'stop_loss'),
            'take_profit': tp if tp_set else _row_value(row, 'take_profit'),
        }

    # ── Resting (limit) orders — the terminals' Limit tab ────────────────
    # Simulator-only: rows fill via the paper executor in the worker's
    # resting_orders tick, never through the live execution gateway.

    @app.post('/api/orders')
    async def create_resting_order(data: dict, authorization: str = Header(None)):
        """Place a GTC limit order. Body: {market, side, symbol, quantity,
        limit_price, stop_loss?, take_profit?, leverage?}. leverage (clamped
        1..10, default 1) is what the fill debits margin at — the futures
        terminal sends its slider value; spot never sends it. Refused if it
        would fill immediately — the market button is one click away."""
        from starlette.concurrency import run_in_threadpool

        from crypto_feed import fetch_ticker
        from resting_orders import place_resting_order

        token = _extract_token(authorization)
        agent = _get_agent_by_token(token)
        if not agent:
            raise HTTPException(status_code=401, detail='Invalid token')
        if not isinstance(data, dict):
            raise HTTPException(status_code=422, detail='Body must be an object')

        symbol = str(data.get('symbol') or '').strip().upper()
        market = str(data.get('market') or 'crypto').strip().lower()
        live_price = None
        if symbol and market == 'crypto':
            try:
                ticker = await run_in_threadpool(fetch_ticker, f'{symbol}USDT')
                live_price = float(ticker['last_price'])
            except Exception:
                live_price = None  # place_resting_order refuses without a quote

        order, err = await run_in_threadpool(
            place_resting_order,
            agent['id'], market, str(data.get('side') or ''), symbol,
            data.get('quantity'), data.get('limit_price'), live_price,
            data.get('stop_loss'), data.get('take_profit'),
            data.get('leverage'), 'limit order (terminal)')
        if err:
            status = 409 if err == 'would_fill_immediately' else 422
            raise HTTPException(status_code=status, detail=err)
        return order

    @app.get('/api/orders')
    async def list_orders(status: Optional[str] = 'open', limit: int = 100,
                          authorization: str = Header(None)):
        """The agent's resting orders (default: open ones, newest first)."""
        from resting_orders import list_resting_orders

        token = _extract_token(authorization)
        agent = _get_agent_by_token(token)
        if not agent:
            raise HTTPException(status_code=401, detail='Invalid token')
        safe_status = status if status in ('open', 'filled', 'cancelled', 'rejected') else None
        orders = list_resting_orders(agent['id'], status=safe_status, limit=limit)
        return {'orders': orders, 'count': len(orders)}

    @app.delete('/api/orders/{order_id}')
    async def cancel_order(order_id: int, authorization: str = Header(None)):
        """Cancel one of the agent's own OPEN resting orders."""
        from resting_orders import cancel_resting_order

        token = _extract_token(authorization)
        agent = _get_agent_by_token(token)
        if not agent:
            raise HTTPException(status_code=401, detail='Invalid token')
        ok, reason = cancel_resting_order(agent['id'], order_id)
        if ok:
            return {'id': order_id, 'status': 'cancelled'}
        if reason == 'not_found':
            raise HTTPException(status_code=404, detail='Order not found')
        # Filled/cancelled under the user's cursor — tell them which.
        raise HTTPException(status_code=409, detail=reason)

    @app.get('/api/positions/trades')
    async def get_my_trades(limit: int = 50, authorization: str = Header(None)):
        """The authed agent's executed trades — the 거래 내역 tab of the
        positions view (Plan 11 F3a). Operation signals are this platform's
        fill log; broker_orders covers the live/shadow order lifecycle."""
        token = _extract_token(authorization)
        agent = _get_agent_by_token(token)
        if not agent:
            raise HTTPException(status_code=401, detail='Invalid token')

        safe_limit = max(1, min(limit, 200))
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """SELECT signal_id, symbol, market, token_id, outcome, side,
                      entry_price, exit_price, quantity, pnl, created_at, executed_at
               FROM signals
               WHERE agent_id = ? AND message_type = 'operation'
               ORDER BY created_at DESC LIMIT ?""",
            (agent['id'], safe_limit))
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()

        for item in rows:
            if item.get('market') == 'polymarket':
                decorate_polymarket_item(item, fetch_remote=False)
        return {'trades': rows, 'count': len(rows)}

    @app.get('/api/positions/trades/summary')
    async def get_my_trades_summary(since: str = None, split: str = None,
                                    authorization: str = Header(None)):
        """Aggregate realized P&L over ALL of the agent's fills, in SQL.

        The trades list above is capped at 200 rows; any client that sums it
        gets a window that silently shrinks as new fills push old ones out
        (the /automation summary tiles did exactly that). created_at is an
        ISO-8601 UTC string ('...T...Z') on both dialects, so plain lexical
        >= comparisons window it correctly.

        - `split`: fixed boundary (e.g. the 2026-07-25 exit-rails epoch) —
          returns the sum/count at or after it.
        - `since`: period-window start (client's chip, as UTC ISO) — returns
          the windowed sum/count plus the window∩split overlap.
        """
        token = _extract_token(authorization)
        agent = _get_agent_by_token(token)
        if not agent:
            raise HTTPException(status_code=401, detail='Invalid token')

        cols = ["COALESCE(SUM(pnl), 0) AS pnl", "COUNT(*) AS trades",
                "MIN(created_at) AS first_trade", "MAX(created_at) AS last_trade"]
        params: list = []
        if split:
            cols += ["COALESCE(SUM(CASE WHEN created_at >= ? THEN pnl END), 0) AS split_pnl",
                     "SUM(CASE WHEN created_at >= ? THEN 1 ELSE 0 END) AS split_trades"]
            params += [split, split]
        if since:
            # window∩split: both boundaries are ISO strings, so the later one
            # lexically is the later instant (date-only 'YYYY-MM-DD' sorts
            # before every 'YYYY-MM-DDT...' of the same day).
            win_split = max(since, split) if split else since
            cols += ["COALESCE(SUM(CASE WHEN created_at >= ? THEN pnl END), 0) AS window_pnl",
                     "SUM(CASE WHEN created_at >= ? THEN 1 ELSE 0 END) AS window_trades",
                     "COALESCE(SUM(CASE WHEN created_at >= ? THEN pnl END), 0) AS window_split_pnl"]
            params += [since, since, win_split]

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            f"""SELECT {', '.join(cols)} FROM signals
                WHERE agent_id = ? AND message_type = 'operation'""",
            (*params, agent['id']))
        row = dict(cursor.fetchone())
        conn.close()

        out = {'pnl': row['pnl'], 'trades': int(row['trades'] or 0),
               'first_trade': row['first_trade'], 'last_trade': row['last_trade']}
        if split:
            out['split'] = {'since': split, 'pnl': row['split_pnl'],
                            'trades': int(row['split_trades'] or 0)}
        if since:
            out['window'] = {'since': since, 'pnl': row['window_pnl'],
                             'trades': int(row['window_trades'] or 0),
                             'split_pnl': row['window_split_pnl']}
        return out

    @app.get('/api/agents/{agent_id}/positions')
    async def get_agent_positions(agent_id: int):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT name, cash FROM agents WHERE id = ?', (agent_id,))
        agent_row = cursor.fetchone()
        agent_name = agent_row['name'] if agent_row else 'Unknown'
        agent_cash = agent_row['cash'] if agent_row else 0

        cursor.execute(
            """
            SELECT symbol, market, token_id, outcome, side, quantity, entry_price, current_price
            FROM positions
            WHERE agent_id = ?
            ORDER BY opened_at DESC
            """,
            (agent_id,),
        )
        rows = cursor.fetchall()
        conn.close()

        positions = []
        total_pnl = 0
        now_str = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        resolved_prices = resolve_position_prices(rows, now_str)

        for row in rows:
            current_price = resolved_prices.get(position_price_cache_key(row))
            pnl = None
            if current_price and row['entry_price']:
                if row['side'] == 'long':
                    pnl = (current_price - row['entry_price']) * abs(row['quantity'])
                else:
                    pnl = (row['entry_price'] - current_price) * abs(row['quantity'])
            if pnl:
                total_pnl += pnl

            positions.append({
                'symbol': row['symbol'],
                'market': row['market'],
                'token_id': row['token_id'],
                'outcome': row['outcome'],
                'side': row['side'],
                'quantity': row['quantity'],
                'entry_price': row['entry_price'],
                'current_price': current_price,
                'pnl': pnl,
            })
            if positions[-1]['market'] == 'polymarket':
                decorate_polymarket_item(positions[-1], fetch_remote=False)

        return {
            'positions': positions,
            'total_pnl': total_pnl,
            'position_count': len(positions),
            'agent_name': agent_name,
            'cash': agent_cash,
        }

    @app.get('/api/agents/{agent_id}/summary')
    async def get_agent_summary(agent_id: int):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                a.id,
                a.name,
                a.cash,
                (SELECT MAX(created_at) FROM signals WHERE agent_id = a.id) AS recent_activity_at,
                (SELECT COUNT(*) FROM positions WHERE agent_id = a.id) AS position_count
            FROM agents a
            WHERE a.id = ?
            """,
            (agent_id,),
        )
        row = cursor.fetchone()
        conn.close()

        if not row:
            raise HTTPException(status_code=404, detail='Agent not found')

        return {
            'agent_id': row['id'],
            'agent_name': row['name'],
            'cash': row['cash'],
            'position_count': row['position_count'] or 0,
            'recent_activity_at': row['recent_activity_at'],
        }

    @app.get('/api/agents/{agent_id}/equity-curve')
    async def get_agent_equity_curve(agent_id: int, days: int = 90):
        """Return a downsampled portfolio-value curve for the given agent.

        Uses the backtest engine against stored signals — no external API calls.
        """
        days = max(7, min(days, 365))
        end_dt = datetime.now(timezone.utc)
        start_dt = end_dt - timedelta(days=days)
        start_at = start_dt.isoformat().replace('+00:00', 'Z')
        end_at = end_dt.isoformat().replace('+00:00', 'Z')
        result = run_backtest(agent_id, start_at, end_at)
        curve = result.curve
        # Downsample to ≤60 points so the payload stays small
        if len(curve) > 60:
            step = max(1, len(curve) // 60)
            curve = curve[::step]
        return {
            'agent_id': agent_id,
            'curve': [{'t': p.timestamp[:10], 'v': round(p.portfolio_value, 2)} for p in curve],
        }

    @app.get('/api/agents/{agent_id}/profile')
    async def get_agent_profile(agent_id: int):
        """Public profile page data for a single agent.

        Returns basic stats, last 20 trade signals, and a profit history
        equity curve (from profit_history snapshots, no external calls).
        """
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT id, name, cash, points, COALESCE(deposited, 0) AS deposited
            FROM agents
            WHERE id = ?
            """,
            (agent_id,),
        )
        row = cursor.fetchone()
        if not row:
            conn.close()
            raise HTTPException(status_code=404, detail='Agent not found')

        cash = float(row['cash'] or INITIAL_CAPITAL)
        # Partial public display: points are shown (social/reward standing),
        # while email/tokens/API settings stay private to the agent itself.
        points = int(row['points'] or 0)
        deposited = float(row['deposited'] or 0)
        profit = cash - INITIAL_CAPITAL
        profit_pct = profit_percent_for_display(profit, deposited)

        cursor.execute(
            """
            SELECT COUNT(*) AS cnt FROM signals
            WHERE agent_id = ? AND message_type = 'operation'
            """,
            (agent_id,),
        )
        count_row = cursor.fetchone()
        trade_count = count_row['cnt'] if count_row else 0

        cursor.execute(
            """
            SELECT signal_id, symbol, side, entry_price, quantity, created_at
            FROM signals
            WHERE agent_id = ? AND message_type = 'operation'
            ORDER BY created_at DESC
            LIMIT 20
            """,
            (agent_id,),
        )
        recent_signals = [
            {
                'signal_id': r['signal_id'],
                'symbol': r['symbol'],
                'side': r['side'],
                'entry_price': r['entry_price'],
                'quantity': r['quantity'],
                'created_at': r['created_at'],
            }
            for r in cursor.fetchall()
        ]

        # Equity curve from profit_history snapshots (90 days, ≤60 points)
        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=90)
        ).strftime('%Y-%m-%dT%H:%M:%SZ')
        cursor.execute(
            """
            SELECT recorded_at, total_value
            FROM profit_history
            WHERE agent_id = ? AND recorded_at >= ?
            ORDER BY recorded_at ASC
            """,
            (agent_id, cutoff),
        )
        history_rows = cursor.fetchall()
        conn.close()

        curve = [{'t': r['recorded_at'][:10], 'v': round(float(r['total_value']), 2)} for r in history_rows]
        if len(curve) > 60:
            step = max(1, len(curve) // 60)
            curve = curve[::step]

        return {
            'agent_id': row['id'],
            'name': row['name'],
            'cash': cash,
            'points': points,
            'profit_pct': round(profit_pct, 2),
            'trade_count': trade_count,
            'recent_signals': recent_signals,
            'equity_curve': curve,
        }

    @app.post('/api/signals/follow')
    async def follow_provider(data: FollowRequest, authorization: str = Header(None)):
        token = _extract_token(authorization)
        agent = _get_agent_by_token(token)
        if not agent:
            raise HTTPException(status_code=401, detail='Invalid token')

        follower_id = agent['id']
        leader_id = data.leader_id
        if follower_id == leader_id:
            raise HTTPException(status_code=400, detail='Cannot follow yourself')

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id FROM subscriptions
            WHERE leader_id = ? AND follower_id = ? AND status = 'active'
            """,
            (leader_id, follower_id),
        )
        if cursor.fetchone():
            conn.close()
            return {'message': 'Already following'}

        cursor.execute(
            """
            INSERT INTO subscriptions (leader_id, follower_id, status)
            VALUES (?, ?, 'active')
            """,
            (leader_id, follower_id),
        )
        subscription_id = cursor.lastrowid
        record_event(
            'agent_followed',
            actor_agent_id=follower_id,
            target_agent_id=leader_id,
            object_type='subscription',
            object_id=subscription_id,
            metadata={'leader_id': leader_id, 'follower_id': follower_id},
            cursor=cursor,
        )
        conn.commit()
        conn.close()

        await push_agent_message(
            ctx,
            leader_id,
            'new_follower',
            f"{agent['name']} started following you",
            {
                'leader_id': leader_id,
                'follower_id': follower_id,
                'follower_name': agent['name'],
            },
        )
        return {'success': True, 'message': 'Following'}

    @app.post('/api/signals/unfollow')
    async def unfollow_provider(data: FollowRequest, authorization: str = Header(None)):
        token = _extract_token(authorization)
        agent = _get_agent_by_token(token)
        if not agent:
            raise HTTPException(status_code=401, detail='Invalid token')

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE subscriptions SET status = 'inactive'
            WHERE leader_id = ? AND follower_id = ?
            """,
            (data.leader_id, agent['id']),
        )
        record_event(
            'agent_unfollowed',
            actor_agent_id=agent['id'],
            target_agent_id=data.leader_id,
            object_type='subscription',
            object_id=f"{data.leader_id}:{agent['id']}",
            metadata={'leader_id': data.leader_id, 'follower_id': agent['id']},
            cursor=cursor,
        )
        conn.commit()
        conn.close()
        return {'success': True}
