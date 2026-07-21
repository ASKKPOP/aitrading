from typing import Optional

import json as _json
import re

import markets

from fastapi import FastAPI, Header, HTTPException, Query
from starlette.concurrency import run_in_threadpool

_FUSION_SYMBOL_RE = re.compile(r'^[A-Z0-9]{1,12}$')

from crypto_feed import TOP_20_PAIRS, fetch_order_book, fetch_ticker, fetch_tickers
from price_fetcher import get_polymarket_market_detail, list_polymarket_markets
from utils import _extract_token
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

# Curated US tickers for the frontend symbol dropdowns. Alpha Vantage accepts
# any US ticker, but the UI is selection-only, so this list IS the tradable
# stock universe shown to users.
US_STOCK_SYMBOLS: tuple[str, ...] = (
    'AAPL', 'MSFT', 'NVDA', 'AMZN', 'GOOGL', 'META', 'TSLA', 'AVGO', 'BRK.B',
    'LLY', 'JPM', 'V', 'MA', 'UNH', 'XOM', 'CVX', 'COST', 'HD', 'PG', 'WMT',
    'NFLX', 'JNJ', 'ABBV', 'PFE', 'MRK', 'BAC', 'CRM', 'ORCL', 'KO', 'PEP',
    'AMD', 'INTC', 'QCOM', 'TMO', 'CSCO', 'ADBE', 'MCD', 'SBUX', 'NKE', 'IBM',
    'GE', 'CAT', 'BA', 'DIS', 'VZ', 'T', 'F', 'GM', 'PLTR', 'UBER',
    'COIN', 'HOOD', 'MSTR', 'SNOW', 'SHOP', 'PYPL', 'SOFI', 'RIVN', 'LCID',
    # 2026 listings. Screened 2026-07-20 on 1-month average dollar volume: each
    # trades heavier than LCID (~$155M/day), the thinnest name above it. The
    # rest of the 2026 IPO class falls off a cliff below that — the next
    # candidate, BSP, is ~$150M and everything after is under $110M — so this
    # bar is what keeps the dropdown to names a $500 order can actually fill.
    'SPCX',   # SpaceX, Nasdaq 2026-06-12
    'SKHY',   # SK hynix, Nasdaq 2026-07-10
    'CBRS',   # Cerebras Systems, Nasdaq 2026-05-14
    'QNT',    # Quantinuum, Nasdaq 2026-06-04
    'SPY', 'QQQ', 'DIA', 'IWM', 'VTI', 'VOO', 'GLD', 'SLV', 'TLT',
)

# Tradable forex pairs, in the canonical concatenated form (base+quote).
# markets.position_currency() reads the trailing three characters as the settlement
# currency, and price_fetcher._yahoo_symbol() appends '=X' for the provider.
FOREX_SYMBOLS: tuple[str, ...] = (
    'EURUSD', 'USDJPY', 'GBPUSD', 'USDCHF', 'AUDUSD', 'USDCAD', 'NZDUSD',
    'EURJPY', 'EURGBP', 'EURCHF', 'EURAUD', 'EURCAD',
    'GBPJPY', 'GBPCHF', 'GBPAUD', 'GBPCAD',
    'AUDJPY', 'AUDNZD', 'AUDCAD', 'AUDCHF',
    'CADJPY', 'CHFJPY', 'NZDJPY',
    'USDCNH', 'USDHKD', 'USDSGD', 'USDKRW', 'USDMXN', 'USDTRY', 'USDZAR',
)

# Tradable futures, as bare contract roots. Every entry must also appear in
# markets.FUTURES_MULTIPLIERS — an unlisted root silently prices at 1.0, which
# would under-report an ES trade by 50x. test_market_symbols guards that.
# price_fetcher._yahoo_symbol() appends '=F' for the provider.
FUTURES_SYMBOLS: tuple[str, ...] = (
    'ES', 'MES', 'NQ', 'MNQ', 'YM', 'MYM', 'RTY', 'M2K',   # equity index
    'CL', 'MCL', 'NG',                                      # energy
    'GC', 'MGC', 'SI', 'HG',                                # metals
    'ZB', 'ZN', 'ZF',                                       # rates
    'ZC', 'ZS', 'ZW',                                       # grains
)

# Tradable A-shares, carrying the exchange suffix because a six-digit board
# code alone is ambiguous between Shanghai (.SS) and Shenzhen (.SZ). These are
# the mainland large caps Yahoo serves reliably; all quote in CNY.
A_STOCK_SYMBOLS: tuple[str, ...] = (
    '600519.SS',  # Kweichow Moutai
    '601398.SS',  # ICBC
    '601857.SS',  # PetroChina
    '600036.SS',  # China Merchants Bank
    '601288.SS',  # Agricultural Bank of China
    '600900.SS',  # China Yangtze Power
    '601988.SS',  # Bank of China
    '600028.SS',  # Sinopec
    '601628.SS',  # China Life
    '600030.SS',  # CITIC Securities
    '600276.SS',  # Jiangsu Hengrui Medicine
    '601318.SS',  # Ping An Insurance
    '600887.SS',  # Inner Mongolia Yili
    '601899.SS',  # Zijin Mining
    '600309.SS',  # Wanhua Chemical
    '000001.SZ',  # Ping An Bank
    '000002.SZ',  # China Vanke
    '000333.SZ',  # Midea Group
    '000651.SZ',  # Gree Electric
    '000858.SZ',  # Wuliangye Yibin
    '002594.SZ',  # BYD
    '300750.SZ',  # CATL
    '002415.SZ',  # Hikvision
    '300059.SZ',  # East Money
    '002475.SZ',  # Luxshare Precision
)

# Underlyings whose option chains are offered. Kept to the liquid names — an
# illiquid chain is all zero-bid strikes, which prices at a stale last trade.
OPTION_UNDERLYINGS: tuple[str, ...] = (
    'AAPL', 'MSFT', 'NVDA', 'AMZN', 'GOOGL', 'META', 'TSLA', 'AMD', 'NFLX',
    'SPY', 'QQQ', 'IWM', 'GLD', 'COIN', 'MSTR', 'PLTR', 'INTC', 'BAC',
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

    @app.get('/api/market-intel/psych')
    async def market_intel_psych():
        from psych_feed import get_psych_payload
        return await run_in_threadpool(get_psych_payload)

    @app.get('/api/market-intel/shock-history')
    async def market_intel_shock_history(hours: int = 72, symbol: str = ""):
        # The σ series behind the shock tile. shock_history() keeps only
        # breaches (its confluence/regime callers want those); a chart needs
        # the whole line, so this reads the wider series.
        from psych_feed import shock_series
        hours = max(1, min(int(hours or 72), 720))
        return await run_in_threadpool(shock_series, hours, symbol or None)

    @app.get('/api/scanner/candidates')
    async def scanner_candidates():
        from scanner import get_scanner_payload
        return await run_in_threadpool(get_scanner_payload)

    @app.get('/api/social/sentiment')
    async def social_sentiment():
        """Latest per-symbol social tilt (Plan 11 F5). Facebook covers SEA, X
        covers everywhere else; {'available': False} until the first cycle."""
        from social_feed import get_social_payload
        return await run_in_threadpool(get_social_payload)

    @app.get('/api/market-intel/events')
    async def market_intel_events():
        # Card 07 — static macro calendar; pure computation, no cache needed.
        from market_events import build_events_payload
        return build_events_payload()

    @app.get('/api/market-intel/cross')
    async def market_intel_cross():
        # Card 16 — kimchi premium + dollar index. Fans out to Upbit/OKX/FX/FRED,
        # so serve through the shared market-intel cache like fusion does.
        from cross_market import build_cross_market_payload
        return await run_in_threadpool(
            _cached_market_payload, 'cross_market', build_cross_market_payload)

    @app.get('/api/market-intel/fusion')
    async def market_intel_fusion(symbols: str = 'BTC,ETH,SOL'):
        from signal_fusion import fuse_symbols
        # Strict symbol charset — these flow into outbound API URL paths.
        parsed = [s.strip().upper() for s in symbols.split(',')
                  if _FUSION_SYMBOL_RE.fullmatch(s.strip().upper())][:8]
        if not parsed:
            raise HTTPException(status_code=422, detail='no valid symbols (A-Z0-9, 1-12 chars)')
        # Fusion fans out to live OKX/StockTwits calls per symbol — cache the
        # payload like every other market-intel endpoint so open dashboards
        # poll the cache, not the upstream APIs.
        cache_key = f'fusion:{",".join(sorted(parsed))}'

        def _build():
            return {'signals': fuse_symbols(parsed)}

        return await run_in_threadpool(_cached_market_payload, cache_key, _build)

    @app.get('/api/market-intel/regime')
    async def market_intel_regime():
        """Market regime read (parameter-upgrade plan Phase 2, advisory).
        regime: trend | caution | panic | euphoria | event | unknown, with
        reasons, entry policy, and F&G / realized-vol-percentile inputs.
        Bands are unvalidated placeholders pending Phase-4 validation."""
        from regime import evaluate_market_regime
        return await run_in_threadpool(
            _cached_market_payload, 'regime', lambda: evaluate_market_regime())

    @app.get('/api/market-intel/confluence')
    async def market_intel_confluence(symbols: str = 'BTC,ETH,SOL'):
        """Confluence checklist (parameter-upgrade plan Phase 1) — the
        deterministic B1–B6/S1–S6 read per symbol, agent-consumable.

        Contract (stable): per symbol —
          buy_confluence / sell_confluence  int 0–6 (the count IS the score)
          threshold                         int, current CONFLUENCE_MIN
          conditions                        {B1..B6, S1..S6: true|false|null}
          nulls                             {condition: reason} — null never satisfies
          vetoes                            list of veto strings (buy_veto / entry_veto)
          direction_bias                    long | short | none
        No probability-formatted confidence is emitted by design.
        """
        from confluence import evaluate_confluence
        parsed = [s.strip().upper() for s in symbols.split(',')
                  if _FUSION_SYMBOL_RE.fullmatch(s.strip().upper())][:8]
        if not parsed:
            raise HTTPException(status_code=422, detail='no valid symbols (A-Z0-9, 1-12 chars)')
        cache_key = f'confluence:{",".join(sorted(parsed))}'

        def _build():
            return {'symbols': [evaluate_confluence(s, 'crypto') for s in parsed]}

        return await run_in_threadpool(_cached_market_payload, cache_key, _build)

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

    @app.get('/api/markets/symbols')
    async def market_symbols():
        """Symbol option lists for the frontend's selection-only symbol fields.

        crypto: Hyperliquid-listed coins (majors from TOP_20_PAIRS first),
        crypto_pairs: OKX USDT pairs (watch/consult endpoints expect pair form),
        stock: curated US tickers.
        """
        def _build():
            from price_fetcher import _get_hyperliquid_available_symbols
            majors = [p.removesuffix('USDT') for p in TOP_20_PAIRS]
            listed = _get_hyperliquid_available_symbols() or set()
            rest = sorted(s for s in listed if s not in set(majors))
            return {
                'crypto': majors + rest,
                'crypto_pairs': list(TOP_20_PAIRS),
                'stock': list(US_STOCK_SYMBOLS),
                'forex': list(FOREX_SYMBOLS),
                'futures': list(FUTURES_SYMBOLS),
                'a_stock': list(A_STOCK_SYMBOLS),
                'option_underlyings': list(OPTION_UNDERLYINGS),
            }

        return await run_in_threadpool(_cached_market_payload, 'symbol-options', _build)

    @app.get('/api/markets/options/{underlying}')
    async def market_option_chain(underlying: str, expiry: Optional[int] = None):
        """Option chain for one underlying, for the strike/expiry picker.

        `expiry` is a UNIX timestamp from this endpoint's own `expirations`
        list; omitting it returns the nearest expiry. Contracts come back in
        OCC form (AAPL260720C00205000), which is the symbol a position is
        actually booked under.
        """
        root = (underlying or '').strip().upper()
        if root not in OPTION_UNDERLYINGS:
            raise HTTPException(status_code=404, detail=f'No option chain for {root}')

        def _build():
            from price_fetcher import _fetch_yahoo_option_chain, _option_contract_price
            chain = _fetch_yahoo_option_chain(root, expiry)
            if not chain:
                raise HTTPException(status_code=503,
                                    detail='Option chain temporarily unavailable')

            def _row(contract: dict) -> dict:
                return {
                    'symbol': contract.get('contractSymbol'),
                    'strike': contract.get('strike'),
                    'bid': contract.get('bid'),
                    'ask': contract.get('ask'),
                    'last': contract.get('lastPrice'),
                    # The mark a position would actually open at, so the picker
                    # and the ledger cannot disagree about the price.
                    'price': _option_contract_price(contract),
                    'volume': contract.get('volume'),
                    'open_interest': contract.get('openInterest'),
                    'implied_volatility': contract.get('impliedVolatility'),
                    'in_the_money': contract.get('inTheMoney'),
                }

            leg = (chain.get('options') or [{}])[0]
            return {
                'underlying': root,
                'underlying_price': (chain.get('quote') or {}).get('regularMarketPrice'),
                'expirations': chain.get('expirationDates') or [],
                'expiry': leg.get('expirationDate') or expiry,
                'contract_multiplier': markets.contract_multiplier('options'),
                'calls': [_row(c) for c in leg.get('calls', [])],
                'puts': [_row(p) for p in leg.get('puts', [])],
            }

        cache_key = f'option-chain:{root}:{expiry or "front"}'
        return await run_in_threadpool(_cached_market_payload, cache_key, _build)

    @app.get('/api/markets/top-symbols')
    async def market_top_symbols(limit: int = 5):
        """Top symbols by 24h volume + popularity (Plan 11 F1) — the universe
        offered to full-delegation and simple automation modes."""
        safe_limit = max(1, min(limit, 10))

        def _build():
            from top_symbols import get_top_symbols
            items = get_top_symbols(safe_limit)
            return {'symbols': items, 'count': len(items)}

        try:
            return await run_in_threadpool(
                _cached_market_payload, f'top-symbols:limit={safe_limit}', _build)
        except Exception as exc:
            raise HTTPException(status_code=503, detail=str(exc))

    @app.post('/api/markets/suggest-symbol')
    async def suggest_symbol(authorization: str = Header(None)):
        """Let the AI choose which symbol to trade from the ranked candidates.

        ONE brief-tier call, not the 4-analyst pipeline: a symbol picker that
        takes 30-90s is not a symbol picker. The model only ever chooses from
        the candidate list, and a reply naming anything else is discarded in
        favour of the top-ranked candidate — the AI may rank, never invent.

        Metered to the caller (the usage shows up in their AI spend panel), and
        fail-soft: if the LLM is unconfigured or unparseable the ranked leader
        is returned with `by_ai=false` so the button always does something.
        """
        from services import _get_agent_by_token
        token = _extract_token(authorization)
        agent = _get_agent_by_token(token) if token else None
        if not agent:
            raise HTTPException(status_code=401, detail='Agent token required')

        def _build():
            from top_symbols import get_top_symbols
            candidates = get_top_symbols(5)
            if not candidates:
                raise HTTPException(status_code=503, detail='No candidates available')
            fallback = candidates[0]['symbol'].removesuffix('USDT')

            from llm_client import LlmContext, llm_configured, reset_llm_context, set_llm_context
            if not llm_configured():
                return {'symbol': fallback, 'reason': '', 'by_ai': False,
                        'candidates': candidates}

            lines = []
            for c in candidates:
                bits = [f"{c['symbol'].removesuffix('USDT')}",
                        f"price ${c['last_price']}",
                        f"24h volume ${c['volume_24h_usd']:,.0f}"]
                if c.get('mention_rate_per_hour'):
                    bits.append(f"social mentions/hour {c['mention_rate_per_hour']:.1f}")
                lines.append(' · '.join(bits))
            allowed = [c['symbol'].removesuffix('USDT') for c in candidates]
            prompt = (
                "You pick ONE crypto symbol to start an automated trading run on, from "
                "the candidates below. Judge which currently offers the best risk-adjusted "
                "opportunity for a short-horizon systematic strategy — consider liquidity "
                "(volume), whether attention looks like early interest or a crowded late "
                "move, and how stretched the price looks.\n\n"
                + '\n'.join(f"- {ln}" for ln in lines)
                + f"\n\nChoose strictly from: {', '.join(allowed)}\n"
                'Reply with ONLY a JSON object: '
                '{"symbol":"<one of the listed>","reason":"<max 15 words, plain language>"}'
            )
            ctx = LlmContext(source='rule', user_id=agent.get('user_id'), agent_id=agent['id'])
            tok = set_llm_context(ctx)
            try:
                from llm_client import generate_text
                text = generate_text(prompt, max_tokens=120, temperature=0.3, tier='brief')
            finally:
                reset_llm_context(tok)

            symbol, reason = fallback, ''
            try:
                raw = (text or '').strip()
                start, end = raw.find('{'), raw.rfind('}')
                if start >= 0 and end > start:
                    parsed = _json.loads(raw[start:end + 1])
                    picked = str(parsed.get('symbol') or '').strip().upper()
                    # never let the model invent a symbol we cannot price
                    if picked in allowed:
                        symbol = picked
                        reason = str(parsed.get('reason') or '').strip()[:160]
            except Exception:  # noqa: BLE001 — unparseable reply falls back
                pass
            return {'symbol': symbol, 'reason': reason,
                    'by_ai': bool(reason), 'candidates': candidates}

        try:
            return await run_in_threadpool(_build)
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=503, detail=str(exc))

    @app.get('/api/markets/crypto/tickers')
    async def crypto_tickers():
        """List top 20 USDT-margined perpetual futures with live OKX prices."""
        try:
            tickers = fetch_tickers(list(TOP_20_PAIRS))
        except Exception as exc:
            raise HTTPException(status_code=503, detail=str(exc))
        return {'tickers': tickers, 'count': len(tickers)}

    @app.get('/api/markets/crypto/ticker')
    async def crypto_ticker(symbol: str = Query(..., description="USDT-margined symbol e.g. BTCUSDT")):
        """Single USDT-margined perpetual ticker from OKX."""
        # The marketing page (and any open dashboard) polls this every 15s per
        # visitor — short shared cache so N visitors cost one OKX call per window.
        sym = symbol.upper()
        redis_key = f'{MARKET_INTEL_CACHE_KEY_PREFIX}:ticker:{sym}'
        cached = get_short_cached_payload(ctx, ctx.market_intel_cache, redis_key, 10)
        if isinstance(cached, dict):
            return cached
        try:
            ticker = await run_in_threadpool(fetch_ticker, sym)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except Exception as exc:
            raise HTTPException(status_code=503, detail=str(exc))
        return set_short_cached_payload(ctx, ctx.market_intel_cache, redis_key, ticker, 10)

    @app.get('/api/markets/crypto/orderbook')
    async def crypto_orderbook(
        symbol: str = Query(..., description="USDT-margined symbol e.g. BTCUSDT"),
        depth: int = Query(25, ge=1, le=50),
    ):
        """Live order book (OKX) for the spot/futures trade terminals."""
        try:
            return fetch_order_book(symbol.upper(), depth)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except Exception as exc:
            raise HTTPException(status_code=503, detail=str(exc))
