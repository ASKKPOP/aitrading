from typing import Optional

from fastapi import FastAPI, HTTPException, Query

from bybit_feed import TOP_20_PAIRS, fetch_bybit_ticker, fetch_bybit_tickers
from price_fetcher import get_polymarket_market_detail, list_polymarket_markets
from market_intel import (
    get_etf_flows_payload,
    get_featured_stock_analysis_payload,
    get_macro_signals_payload,
    get_market_intel_overview,
    get_market_news_payload,
    get_stock_analysis_history_payload,
    get_stock_analysis_latest_payload,
)
from routes_shared import (
    MARKET_INTEL_CACHE_KEY_PREFIX,
    MARKET_INTEL_CACHE_TTL_SECONDS,
    RouteContext,
    get_short_cached_payload,
    set_short_cached_payload,
    utc_now_iso_z,
)


def register_market_routes(app: FastAPI, ctx: RouteContext) -> None:
    def _cached_market_payload(cache_key: str, builder):
        redis_key = f'{MARKET_INTEL_CACHE_KEY_PREFIX}:{cache_key}'
        cached = get_short_cached_payload(ctx, ctx.market_intel_cache, redis_key, MARKET_INTEL_CACHE_TTL_SECONDS)
        if isinstance(cached, dict):
            return cached
        payload = builder()
        return set_short_cached_payload(
            ctx,
            ctx.market_intel_cache,
            redis_key,
            payload,
            MARKET_INTEL_CACHE_TTL_SECONDS,
        )

    @app.get('/health')
    async def health_check():
        return {'status': 'ok', 'timestamp': utc_now_iso_z()}

    @app.get('/api/markets/polymarket')
    async def polymarket_market_list(limit: int = 20, active: bool = True):
        """List active Polymarket prediction markets, ordered by 24-hour volume."""
        safe_limit = max(1, min(limit, 100))
        redis_key = f'{MARKET_INTEL_CACHE_KEY_PREFIX}:polymarket:list:limit={safe_limit}:active={active}'
        cached = get_short_cached_payload(ctx, ctx.market_intel_cache, redis_key, 60)
        if isinstance(cached, list):
            return {'markets': cached, 'count': len(cached)}
        markets = list_polymarket_markets(limit=safe_limit, active=active)
        set_short_cached_payload(ctx, ctx.market_intel_cache, redis_key, markets, 60)
        return {'markets': markets, 'count': len(markets)}

    @app.get('/api/markets/polymarket/{slug_or_id}')
    async def polymarket_market_detail(slug_or_id: str):
        """Return a single Polymarket market with live per-outcome prices.

        `slug_or_id` may be a market slug, conditionId (0x…), or a token ID.
        Prices are fetched from the CLOB orderbook with a Gamma fallback.
        """
        redis_key = f'{MARKET_INTEL_CACHE_KEY_PREFIX}:polymarket:detail:{slug_or_id}'
        cached = get_short_cached_payload(ctx, ctx.market_intel_cache, redis_key, 30)
        if isinstance(cached, dict):
            return cached
        detail = get_polymarket_market_detail(slug_or_id)
        if detail is None:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail='Market not found')
        set_short_cached_payload(ctx, ctx.market_intel_cache, redis_key, detail, 30)
        return detail

    @app.get('/api/market-intel/overview')
    async def market_intel_overview():
        return _cached_market_payload('overview', get_market_intel_overview)

    @app.get('/api/market-intel/news')
    async def market_intel_news(category: Optional[str] = None, limit: int = 5):
        safe_limit = max(1, min(limit, 12))
        category_key = (category or 'all').strip() or 'all'
        return _cached_market_payload(
            f'news:category={category_key}:limit={safe_limit}',
            lambda: get_market_news_payload(category=category, limit=safe_limit),
        )

    @app.get('/api/market-intel/macro-signals')
    async def market_intel_macro_signals():
        return _cached_market_payload('macro_signals', get_macro_signals_payload)

    @app.get('/api/market-intel/etf-flows')
    async def market_intel_etf_flows():
        return _cached_market_payload('etf_flows', get_etf_flows_payload)

    @app.get('/api/market-intel/stocks/featured')
    async def market_intel_featured_stocks(limit: int = 6):
        safe_limit = max(1, min(limit, 12))
        return _cached_market_payload(
            f'stocks_featured:limit={safe_limit}',
            lambda: get_featured_stock_analysis_payload(limit=safe_limit),
        )

    @app.get('/api/market-intel/stocks/{symbol}/latest')
    async def market_intel_stock_latest(symbol: str):
        normalized_symbol = (symbol or '').strip().upper()
        return _cached_market_payload(
            f'stock_latest:symbol={normalized_symbol}',
            lambda: get_stock_analysis_latest_payload(normalized_symbol),
        )

    @app.get('/api/market-intel/stocks/{symbol}/history')
    async def market_intel_stock_history(symbol: str, limit: int = 10):
        normalized_symbol = (symbol or '').strip().upper()
        safe_limit = max(1, min(limit, 100))
        return _cached_market_payload(
            f'stock_history:symbol={normalized_symbol}:limit={safe_limit}',
            lambda: get_stock_analysis_history_payload(normalized_symbol, limit=safe_limit),
        )

    # ─── Bybit perpetual futures ────────────────────────────────────────────

    @app.get('/api/markets/bybit/tickers')
    async def bybit_tickers():
        """List top 20 USDT-linear perpetual futures with live Bybit prices."""
        try:
            tickers = fetch_bybit_tickers(list(TOP_20_PAIRS))
        except Exception as exc:
            raise HTTPException(status_code=503, detail=str(exc))
        return {'tickers': tickers, 'count': len(tickers)}

    @app.get('/api/markets/bybit/ticker')
    async def bybit_ticker(symbol: str = Query(..., description="USDT-linear symbol e.g. BTCUSDT")):
        """Single USDT-linear perpetual ticker from Bybit."""
        try:
            ticker = fetch_bybit_ticker(symbol.upper())
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except Exception as exc:
            raise HTTPException(status_code=503, detail=str(exc))
        return ticker
