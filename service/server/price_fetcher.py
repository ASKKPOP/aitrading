"""
Stock Price Fetcher for Server

US Stock: 从 Alpha Vantage 获取价格
Crypto: 从 Hyperliquid 获取价格（停止使用 Alpha Vantage crypto 端点）
"""

import os
import random
import requests
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Tuple, Any
import re
import threading
import time
import json

import markets
try:
    from zoneinfo import ZoneInfo
    _ET_ZONEINFO = ZoneInfo("America/New_York")
except ImportError:
    _ET_ZONEINFO = None  # Python < 3.9 fallback: use fixed offset below

# Alpha Vantage API configuration
ALPHA_VANTAGE_API_KEY = os.environ.get("ALPHA_VANTAGE_API_KEY", "demo")

# Yahoo's public chart endpoint fingerprints the User-Agent, and the exact string
# matters far more than it looks. Measured from the production host, 2026-07-20:
#   "Mozilla/5.0"                        -> 200, 12/12 with no delay between requests
#   a full spoofed Chrome UA string      -> 429, 6/6, on the very first request
#   requests' own default UA             -> 429, always
# A detailed browser UA with no matching TLS fingerprint or headers reads as a
# scraper; the bare token reads as a generic HTTP client and is served normally.
# Do not "improve" this into a realistic-looking browser string — that breaks it.
_YAHOO_USER_AGENT = "Mozilla/5.0"
BASE_URL = "https://www.alphavantage.co/query"

# Hyperliquid public info endpoint (no API key required for reads)
HYPERLIQUID_API_URL = os.environ.get("HYPERLIQUID_API_URL", "https://api.hyperliquid.xyz/info").strip()

# Polymarket public endpoints (no API key required for reads)
POLYMARKET_GAMMA_BASE_URL = os.environ.get("POLYMARKET_GAMMA_BASE_URL", "https://gamma-api.polymarket.com").strip()
POLYMARKET_CLOB_BASE_URL = os.environ.get("POLYMARKET_CLOB_BASE_URL", "https://clob.polymarket.com").strip()
PRICE_FETCH_TIMEOUT_SECONDS = float(os.environ.get("PRICE_FETCH_TIMEOUT_SECONDS", "10"))
PRICE_FETCH_MAX_RETRIES = max(0, int(os.environ.get("PRICE_FETCH_MAX_RETRIES", "2")))
PRICE_FETCH_BACKOFF_BASE_SECONDS = max(0.0, float(os.environ.get("PRICE_FETCH_BACKOFF_BASE_SECONDS", "0.35")))
PRICE_FETCH_ERROR_COOLDOWN_SECONDS = max(0.0, float(os.environ.get("PRICE_FETCH_ERROR_COOLDOWN_SECONDS", "20")))
PRICE_FETCH_RATE_LIMIT_COOLDOWN_SECONDS = max(0.0, float(os.environ.get("PRICE_FETCH_RATE_LIMIT_COOLDOWN_SECONDS", "60")))
PRICE_FETCH_VERBOSE = os.environ.get("PRICE_FETCH_VERBOSE", "true").strip().lower() not in {"0", "false", "no", "off"}
HYPERLIQUID_SYMBOL_CACHE_TTL_SECONDS = max(60.0, float(os.environ.get("HYPERLIQUID_SYMBOL_CACHE_TTL_SECONDS", "300")))

# 时区常量
UTC = timezone.utc
# ET_TZ resolves to America/New_York (DST-aware) when zoneinfo is available.
# Falling back to a fixed UTC-5 (EST) offset is conservative — it will be 1 hour
# off during EDT (summer) but at least correct during the longer EST winter period.
# The zoneinfo path is always preferred and available on Python 3.9+.
ET_TZ = _ET_ZONEINFO if _ET_ZONEINFO is not None else timezone(timedelta(hours=-5))

_POLYMARKET_CONDITION_ID_RE = re.compile(r"^0x[a-fA-F0-9]{64}$")
_POLYMARKET_TOKEN_ID_RE = re.compile(r"^\d+$")
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
_provider_cooldowns: Dict[str, float] = {}
_price_fetch_logging_enabled: ContextVar[bool] = ContextVar("price_fetch_logging_enabled", default=True)
_hyperliquid_symbol_cache: Tuple[Optional[set[str]], float] = (None, 0.0)


def _price_log(message: str) -> None:
    if PRICE_FETCH_VERBOSE and _price_fetch_logging_enabled.get():
        print(message)


@contextmanager
def price_fetch_logging(enabled: bool):
    token = _price_fetch_logging_enabled.set(enabled)
    try:
        yield
    finally:
        _price_fetch_logging_enabled.reset(token)

# Polymarket outcome prices are probabilities in [0, 1]. Reject values outside to avoid
# token_id/condition_id or other API noise being interpreted as price (e.g. 1.5e+73).
def _polymarket_price_valid(price: float) -> bool:
    if price is None or not isinstance(price, (int, float)):
        return False
    try:
        p = float(price)
        return 0 <= p <= 1
    except (TypeError, ValueError):
        return False

# In-memory cache for Polymarket reference+outcome -> (token_id, expiry_epoch_s)
_polymarket_token_cache: Dict[str, Tuple[str, float]] = {}
_polymarket_market_cache: Dict[str, Tuple[Optional[dict], float]] = {}
_POLYMARKET_TOKEN_CACHE_TTL_S = 300.0
_POLYMARKET_MARKET_CACHE_TTL_S = 300.0


def _provider_cooldown_remaining(provider: str) -> float:
    return max(0.0, _provider_cooldowns.get(provider, 0.0) - time.time())


def _activate_provider_cooldown(provider: str, duration_s: float, reason: str) -> None:
    if duration_s <= 0:
        return
    until = time.time() + duration_s
    previous_until = _provider_cooldowns.get(provider, 0.0)
    _provider_cooldowns[provider] = max(previous_until, until)
    remaining = _provider_cooldown_remaining(provider)
    _price_log(f"[Price API] {provider} cooldown {remaining:.1f}s ({reason})")


def _retry_delay(attempt: int) -> float:
    if PRICE_FETCH_BACKOFF_BASE_SECONDS <= 0:
        return 0.0
    base = PRICE_FETCH_BACKOFF_BASE_SECONDS * (2 ** attempt)
    return base + random.uniform(0.0, base * 0.25)


def _request_json_with_retry(
    provider: str,
    method: str,
    url: str,
    *,
    params: Optional[dict] = None,
    json_payload: Optional[dict] = None,
    headers: Optional[dict] = None,
    retry_on_rate_limit: bool = True,
) -> object:
    remaining = _provider_cooldown_remaining(provider)
    if remaining > 0:
        raise RuntimeError(f"{provider} cooldown active for {remaining:.1f}s")

    last_exc: Optional[Exception] = None
    attempts = PRICE_FETCH_MAX_RETRIES + 1

    for attempt in range(attempts):
        try:
            if method == "POST":
                resp = requests.post(url, json=json_payload, headers=headers,
                                     timeout=PRICE_FETCH_TIMEOUT_SECONDS)
            else:
                resp = requests.get(url, params=params, headers=headers,
                                    timeout=PRICE_FETCH_TIMEOUT_SECONDS)

            if resp.status_code in _RETRYABLE_STATUS_CODES:
                resp.raise_for_status()

            resp.raise_for_status()
            return resp.json()
        except requests.HTTPError as exc:
            status_code = exc.response.status_code if exc.response is not None else None
            retryable = status_code in _RETRYABLE_STATUS_CODES
            # Retrying a rate-limit response triples the offending load and digs the
            # hole deeper. Providers that throttle by IP (Yahoo) opt out and go
            # straight to cooldown.
            if status_code == 429 and not retry_on_rate_limit:
                retryable = False
            last_exc = exc

            if retryable and attempt < attempts - 1:
                delay = _retry_delay(attempt)
                _price_log(
                    f"[Price API] {provider} retry {attempt + 1}/{attempts - 1} "
                    f"after HTTP {status_code}; sleeping {delay:.2f}s"
                )
                if delay > 0:
                    time.sleep(delay)
                continue

            if status_code == 429:
                _activate_provider_cooldown(
                    provider,
                    PRICE_FETCH_RATE_LIMIT_COOLDOWN_SECONDS,
                    "HTTP 429"
                )
            elif status_code is not None and status_code >= 500:
                _activate_provider_cooldown(
                    provider,
                    PRICE_FETCH_ERROR_COOLDOWN_SECONDS,
                    f"HTTP {status_code}"
                )
            raise
        except (requests.Timeout, requests.ConnectionError) as exc:
            last_exc = exc
            if attempt < attempts - 1:
                delay = _retry_delay(attempt)
                _price_log(
                    f"[Price API] {provider} retry {attempt + 1}/{attempts - 1} "
                    f"after {exc.__class__.__name__}; sleeping {delay:.2f}s"
                )
                if delay > 0:
                    time.sleep(delay)
                continue
            _activate_provider_cooldown(
                provider,
                PRICE_FETCH_ERROR_COOLDOWN_SECONDS,
                exc.__class__.__name__
            )
            raise
        except requests.RequestException as exc:
            last_exc = exc
            raise

    if last_exc is not None:
        raise last_exc
    raise RuntimeError(f"{provider} request failed without response")


def _polymarket_market_title(market: Optional[dict]) -> Optional[str]:
    if not isinstance(market, dict):
        return None
    for key in ("question", "title", "description", "slug"):
        value = market.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def describe_polymarket_contract(reference: str, token_id: Optional[str] = None, outcome: Optional[str] = None) -> Optional[dict]:
    """
    Return human-readable Polymarket metadata for UI/documentation.
    """
    contract = _polymarket_resolve_reference(reference, token_id=token_id, outcome=outcome)
    if not contract:
        return None

    market = contract.get("market")
    resolved_outcome = contract.get("outcome")
    market_title = _polymarket_market_title(market)
    market_slug = market.get("slug") if isinstance(market, dict) else None
    display_title = market_title or market_slug or reference
    if resolved_outcome:
        display_title = f"{display_title} [{resolved_outcome}]"

    return {
        "token_id": contract.get("token_id"),
        "outcome": resolved_outcome,
        "market_title": market_title,
        "market_slug": market_slug,
        "display_title": display_title,
    }

def _parse_executed_at_to_utc(executed_at: str) -> Optional[datetime]:
    """
    Parse executed_at into an aware UTC datetime.
    Accepts:
    - 2026-03-07T14:30:00Z
    - 2026-03-07T14:30:00+00:00
    - 2026-03-07T14:30:00   (treated as UTC)
    """
    try:
        cleaned = executed_at.strip()
        if cleaned.endswith("Z"):
            cleaned = cleaned.replace("Z", "+00:00")
        dt = datetime.fromisoformat(cleaned)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    except Exception:
        return None


def _normalize_hyperliquid_symbol(symbol: str) -> str:
    """
    Best-effort normalization for Hyperliquid 'coin' identifiers.
    Examples:
    - 'btc' -> 'BTC'
    - 'BTC-USD' -> 'BTC'
    - 'BTC/USD' -> 'BTC'
    - 'BTC-PERP' -> 'BTC'
    - 'xyz:NVDA' -> 'xyz:NVDA' (keep dex-prefixed builder listings)
    """
    raw = symbol.strip()
    if ":" in raw:
        return raw  # builder/dex symbols are case sensitive upstream; keep as-is

    s = raw.upper()
    for suffix in ("-PERP", "PERP"):
        if s.endswith(suffix):
            s = s[: -len(suffix)]
            break

    for sep in ("-USD", "/USD"):
        if s.endswith(sep):
            s = s[: -len(sep)]
            break

    for sep in ("-USDT", "/USDT"):
        if s.endswith(sep):
            s = s[: -len(sep)]
            break

    if s.endswith("USDT") and len(s) > len("USDT"):
        s = s[: -len("USDT")]

    return s.strip()


def _hyperliquid_post(payload: dict) -> object:
    if not HYPERLIQUID_API_URL:
        raise RuntimeError("HYPERLIQUID_API_URL is empty")
    return _request_json_with_retry(
        "hyperliquid",
        "POST",
        HYPERLIQUID_API_URL,
        json_payload=payload,
    )


def _get_hyperliquid_available_symbols() -> Optional[set[str]]:
    global _hyperliquid_symbol_cache

    cached_symbols, expires_at = _hyperliquid_symbol_cache
    now = time.time()
    if expires_at > now:
        return cached_symbols

    try:
        data = _hyperliquid_post({"type": "meta"})
    except Exception:
        _hyperliquid_symbol_cache = (None, now + 30.0)
        return None

    symbols: set[str] = set()
    if isinstance(data, dict):
        universe = data.get("universe")
        if isinstance(universe, list):
            for asset in universe:
                if isinstance(asset, dict):
                    name = str(asset.get("name") or "").strip()
                    if name:
                        symbols.add(name)

    _hyperliquid_symbol_cache = (symbols or None, now + HYPERLIQUID_SYMBOL_CACHE_TTL_SECONDS)
    return symbols or None


def _hyperliquid_symbol_available(coin: str) -> bool:
    symbols = _get_hyperliquid_available_symbols()
    if symbols is None:
        return True
    return coin in symbols


def _polymarket_get_json(url: str, params: Optional[dict] = None) -> object:
    return _request_json_with_retry(
        "polymarket",
        "GET",
        url,
        params=params,
    )


def _parse_string_array(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(v).strip() for v in value if isinstance(v, (str, int)) and str(v).strip()]
    if isinstance(value, str) and value.strip().startswith("["):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [str(v).strip() for v in parsed if isinstance(v, (str, int)) and str(v).strip()]
        except Exception:
            return []
    return []


def _polymarket_fetch_market(reference: str, token_id: Optional[str] = None) -> Optional[dict]:
    if not POLYMARKET_GAMMA_BASE_URL:
        return None

    ref = (reference or "").strip()
    requested_token_id = (token_id or "").strip()
    if not ref and not requested_token_id:
        return None

    cache_key = f"{ref}::{requested_token_id}"
    now = time.time()
    cached = _polymarket_market_cache.get(cache_key)
    if cached and cached[1] > now:
        return cached[0]

    url = f"{POLYMARKET_GAMMA_BASE_URL.rstrip('/')}/markets"
    params = {"limit": "1"}
    if requested_token_id and _POLYMARKET_TOKEN_ID_RE.match(requested_token_id):
        params["clob_token_ids"] = requested_token_id
    elif _POLYMARKET_CONDITION_ID_RE.match(ref):
        params["conditionId"] = ref
    elif _POLYMARKET_TOKEN_ID_RE.match(ref):
        params["clob_token_ids"] = ref
    else:
        params["slug"] = ref

    try:
        raw = _polymarket_get_json(url, params=params)
    except Exception:
        _polymarket_market_cache[cache_key] = (None, now + 60.0)
        return None

    if not isinstance(raw, list) or not raw or not isinstance(raw[0], dict):
        _polymarket_market_cache[cache_key] = (None, now + _POLYMARKET_MARKET_CACHE_TTL_S)
        return None
    market = raw[0]
    _polymarket_market_cache[cache_key] = (market, now + _POLYMARKET_MARKET_CACHE_TTL_S)
    return market


def _polymarket_extract_tokens(market: dict) -> list[dict[str, Optional[str]]]:
    token_ids = _parse_string_array(market.get("clobTokenIds")) or _parse_string_array(market.get("clob_token_ids"))
    outcomes = _parse_string_array(market.get("outcomes"))
    extracted: list[dict[str, Optional[str]]] = []
    for idx, token_id in enumerate(token_ids):
        if token_id and _POLYMARKET_TOKEN_ID_RE.match(token_id):
            extracted.append({
                "token_id": token_id,
                "outcome": outcomes[idx] if idx < len(outcomes) else None,
            })
    return extracted


def list_polymarket_markets(
    limit: int = 20,
    active: bool = True,
    order: str = "volume24hr",
) -> list[dict]:
    """Return a list of Polymarket markets from the Gamma API.

    Fields returned per market: slug, condition_id, title, end_date,
    volume_24hr, liquidity, outcomes, tokens (list of {token_id, outcome}).
    """
    if not POLYMARKET_GAMMA_BASE_URL:
        return []
    url = f"{POLYMARKET_GAMMA_BASE_URL.rstrip('/')}/markets"
    params: dict = {
        "limit": str(max(1, min(limit, 100))),
        "order": order,
        "ascending": "false",
    }
    if active:
        params["active"] = "true"
        params["closed"] = "false"
    try:
        raw = _polymarket_get_json(url, params=params)
    except Exception:
        return []
    if not isinstance(raw, list):
        return []
    result = []
    for m in raw:
        if not isinstance(m, dict):
            continue
        result.append({
            "slug": m.get("slug"),
            "condition_id": m.get("conditionId"),
            "title": _polymarket_market_title(m),
            "end_date": m.get("endDate") or m.get("end_date_iso"),
            "volume_24hr": m.get("volume24hr") or m.get("volumeNum"),
            "liquidity": m.get("liquidityNum") or m.get("liquidity"),
            "outcomes": _parse_string_array(m.get("outcomes")),
            "tokens": _polymarket_extract_tokens(m),
            "active": m.get("active"),
            "closed": m.get("closed"),
        })
    return result


def get_polymarket_market_detail(slug_or_id: str) -> Optional[dict]:
    """Return a single Polymarket market with live prices per outcome token.

    `slug_or_id` may be a market slug, conditionId (0x…), or token ID.
    Returns None when the market cannot be found or the Gamma API is unreachable.
    """
    ref = (slug_or_id or "").strip()
    if not ref:
        return None

    market = _polymarket_fetch_market(ref)
    if not isinstance(market, dict):
        return None

    tokens = _polymarket_extract_tokens(market)

    # Fetch live price for each outcome token.
    priced_tokens = []
    for t in tokens:
        token_id = t.get("token_id")
        outcome = t.get("outcome")
        price: Optional[float] = None
        if token_id:
            price = _get_polymarket_mid_price(ref, token_id=token_id, outcome=outcome)
        priced_tokens.append({
            "token_id": token_id,
            "outcome": outcome,
            "price": price,
        })

    return {
        "slug": market.get("slug"),
        "condition_id": market.get("conditionId"),
        "title": _polymarket_market_title(market),
        "end_date": market.get("endDate") or market.get("end_date_iso"),
        "volume_24hr": market.get("volume24hr") or market.get("volumeNum"),
        "liquidity": market.get("liquidityNum") or market.get("liquidity"),
        "outcomes": _parse_string_array(market.get("outcomes")),
        "tokens": priced_tokens,
        "active": market.get("active"),
        "closed": market.get("closed"),
        "description": market.get("description"),
        "image": market.get("image"),
    }


def _polymarket_resolve_reference(reference: str, token_id: Optional[str] = None, outcome: Optional[str] = None) -> Optional[dict]:
    """
    Resolve a Polymarket reference into an explicit outcome token.

    For ambiguous references (slug/condition with multiple outcomes), caller must provide
    either `token_id` or `outcome`.
    """
    ref = (reference or "").strip()
    if not ref:
        return None

    requested_token_id = (token_id or "").strip()
    requested_outcome = (outcome or "").strip().lower()
    cache_key = f"{ref}::{(token_id or '').strip().lower()}::{(outcome or '').strip().lower()}"
    cached = _polymarket_token_cache.get(cache_key)
    now = time.time()
    if cached and cached[1] > now:
        return {
            "token_id": cached[0],
            "outcome": outcome,
            "market": _polymarket_fetch_market(ref, token_id=requested_token_id),
        }

    market = _polymarket_fetch_market(ref, token_id=requested_token_id)
    if not market:
        return None

    tokens = _polymarket_extract_tokens(market)

    selected = None
    if requested_token_id and _POLYMARKET_TOKEN_ID_RE.match(requested_token_id):
        for candidate in tokens:
            if candidate["token_id"] == requested_token_id:
                selected = candidate
                break
        if selected is None and not tokens:
            selected = {"token_id": requested_token_id, "outcome": outcome}
    if selected is None and _POLYMARKET_TOKEN_ID_RE.match(ref):
        selected = {"token_id": ref, "outcome": outcome}
    if selected is None and requested_outcome:
        for candidate in tokens:
            if (candidate.get("outcome") or "").strip().lower() == requested_outcome:
                selected = candidate
                break
    if selected is None and len(tokens) == 1:
        selected = tokens[0]

    if not selected or not selected.get("token_id"):
        return None

    resolved_token_id = str(selected["token_id"])
    _polymarket_token_cache[cache_key] = (resolved_token_id, now + _POLYMARKET_TOKEN_CACHE_TTL_S)
    return {
        "token_id": resolved_token_id,
        "outcome": selected.get("outcome"),
        "market": market,
    }


def _get_polymarket_mid_price(reference: str, token_id: Optional[str] = None, outcome: Optional[str] = None) -> Optional[float]:
    """
    Fetch a mid price for a Polymarket outcome token.
    Price is derived from best bid/ask in the CLOB orderbook.
    """
    if not POLYMARKET_CLOB_BASE_URL:
        return None

    contract = _polymarket_resolve_reference(reference, token_id=token_id, outcome=outcome)
    if not contract:
        return None
    resolved_token_id = contract["token_id"]

    url = f"{POLYMARKET_CLOB_BASE_URL.rstrip('/')}/book"
    data = None
    try:
        data = _polymarket_get_json(url, params={"token_id": resolved_token_id})
    except Exception:
        data = None

    if isinstance(data, dict):
        bids = data.get("bids") if isinstance(data.get("bids"), list) else []
        asks = data.get("asks") if isinstance(data.get("asks"), list) else []

        def _best_px(levels: list) -> Optional[float]:
            if not levels:
                return None
            first = levels[0]
            if isinstance(first, dict) and "price" in first:
                try:
                    return float(first["price"])
                except Exception:
                    return None
            return None

        best_bid = _best_px(bids)
        best_ask = _best_px(asks)
        if best_bid is not None or best_ask is not None:
            mid = (best_bid + best_ask) / 2 if (best_bid is not None and best_ask is not None) else (best_bid if best_bid is not None else best_ask)
            mid = float(f"{mid:.6f}")
            if _polymarket_price_valid(mid):
                return mid
            return None

    # Fallback: use Gamma market fields when CLOB orderbook is missing.
    market = contract.get("market")
    if not isinstance(market, dict):
        return None
    try:
        outcome_prices = _parse_string_array(market.get("outcomePrices"))
        outcomes = _parse_string_array(market.get("outcomes"))
        target_outcome = (contract.get("outcome") or "").strip().lower()
        if target_outcome and outcome_prices and outcomes:
            for idx, label in enumerate(outcomes):
                if label.strip().lower() == target_outcome and idx < len(outcome_prices):
                    p = float(f"{float(outcome_prices[idx]):.6f}")
                    if _polymarket_price_valid(p):
                        return p
        for key in ("lastTradePrice", "outcomePrice"):
            v = market.get(key)
            if isinstance(v, (int, float)):
                p = float(f"{float(v):.6f}")
                if _polymarket_price_valid(p):
                    return p
            if isinstance(v, str) and v.strip():
                try:
                    p = float(f"{float(v):.6f}")
                    if _polymarket_price_valid(p):
                        return p
                except Exception:
                    pass
    except Exception:
        pass

    return None


def _polymarket_resolve(reference: str, token_id: Optional[str] = None, outcome: Optional[str] = None) -> Optional[dict]:
    """
    Resolve a Polymarket market via Gamma.
    Returns dict: { resolved: bool, outcome: Optional[str], settlementPrice: Optional[float] } or None.
    """
    contract = _polymarket_resolve_reference(reference, token_id=token_id, outcome=outcome)
    if not contract:
        return None
    market = contract.get("market")
    if not isinstance(market, dict):
        return None

    resolved_flag = bool(market.get("resolved"))
    resolved_outcome = market.get("outcome") if isinstance(market.get("outcome"), str) else None
    settlement_raw = market.get("settlementPrice")
    settlement_price = None
    if isinstance(settlement_raw, (int, float)):
        settlement_price = float(settlement_raw)
    elif isinstance(settlement_raw, str) and settlement_raw.strip():
        try:
            settlement_price = float(settlement_raw)
        except Exception:
            settlement_price = None
    if settlement_price is not None and not _polymarket_price_valid(settlement_price):
        settlement_price = None

    return {
        "resolved": resolved_flag,
        "token_id": contract.get("token_id"),
        "outcome": contract.get("outcome"),
        "market_slug": market.get("slug"),
        "resolved_outcome": resolved_outcome,
        "settlementPrice": settlement_price,
    }


def _get_hyperliquid_mid_price(symbol: str) -> Optional[float]:
    """
    Fetch mid price from Hyperliquid L2 book.
    This is used for 'now' style queries.
    """
    coin = _normalize_hyperliquid_symbol(symbol)
    if not _hyperliquid_symbol_available(coin):
        _price_log(f"[Price API] Hyperliquid symbol not listed: {symbol} -> {coin}")
        return None

    data = _hyperliquid_post({"type": "l2Book", "coin": coin})
    if not isinstance(data, dict) or "levels" not in data:
        return None
    levels = data.get("levels")
    if not isinstance(levels, list) or len(levels) < 2:
        return None
    bids = levels[0] if isinstance(levels[0], list) else []
    asks = levels[1] if isinstance(levels[1], list) else []
    best_bid = None
    best_ask = None
    if bids and isinstance(bids[0], dict) and "px" in bids[0]:
        try:
            best_bid = float(bids[0]["px"])
        except Exception:
            best_bid = None
    if asks and isinstance(asks[0], dict) and "px" in asks[0]:
        try:
            best_ask = float(asks[0]["px"])
        except Exception:
            best_ask = None
    if best_bid is None and best_ask is None:
        return None
    if best_bid is not None and best_ask is not None:
        return float(f"{((best_bid + best_ask) / 2):.6f}")
    return float(f"{(best_bid if best_bid is not None else best_ask):.6f}")


def _get_hyperliquid_candle_close(symbol: str, executed_at: str) -> Optional[float]:
    """
    Fetch a 1m candle around executed_at via candleSnapshot and return the closest close.
    This approximates "price at time" without requiring any private keys.
    """
    dt = _parse_executed_at_to_utc(executed_at)
    if not dt:
        return None

    # Query a small window around the target time (±10 minutes)
    target_ms = int(dt.timestamp() * 1000)
    start_ms = target_ms - 10 * 60 * 1000
    end_ms = target_ms + 10 * 60 * 1000

    coin = _normalize_hyperliquid_symbol(symbol)
    if not _hyperliquid_symbol_available(coin):
        _price_log(f"[Price API] Hyperliquid symbol not listed: {symbol} -> {coin}")
        return None

    payload = {
        "type": "candleSnapshot",
        "req": {
            "coin": coin,
            "interval": "1m",
            "startTime": start_ms,
            "endTime": end_ms,
        },
    }
    data = _hyperliquid_post(payload)
    if not isinstance(data, list) or len(data) == 0:
        return None

    closest = None
    closest_ts = None
    for candle in data:
        if not isinstance(candle, dict):
            continue
        t = candle.get("t")
        c = candle.get("c")
        if t is None or c is None:
            continue
        try:
            t_ms = int(float(t))
            close = float(c)
        except Exception:
            continue
        if t_ms > target_ms:
            continue
        if closest_ts is None or t_ms > closest_ts:
            closest_ts = t_ms
            closest = close

    if closest is None:
        return None
    return float(f"{closest:.6f}")


def _yahoo_symbol(symbol: str, market: str) -> Optional[str]:
    """Canonical Sooppiy symbol -> Yahoo ticker.

    Forex pairs are stored in the concatenated six-letter form (EURUSD) and Yahoo
    expects the `=X` suffix. Returns None when the symbol does not fit the market's
    shape, so a malformed pair fails fast instead of querying an unrelated ticker.

    Share classes are the other mismatch: we store the SEC form (BRK.B) and Yahoo
    only answers to the dashed one (BRK-B) — measured 2026-07-20, BRK.B 404s while
    BRK-B returns a price.
    """
    cleaned = (symbol or "").strip().upper().replace("/", "")
    if not cleaned:
        return None
    if market == "forex":
        if len(cleaned) != 6 or not cleaned.isalpha():
            return None
        return f"{cleaned}=X"
    if market == "futures":
        # Canonical form is the bare contract root (ES); Yahoo wants the
        # continuous-front-month suffix. Accept an already-suffixed symbol so a
        # round-trip through this helper is idempotent.
        root = cleaned.removesuffix("=F")
        if not root or not root.isalnum():
            return None
        return f"{root}=F"
    if market == "a-stock":
        # Canonical form carries the exchange suffix (600519.SS / 000001.SZ)
        # because the six-digit code alone is ambiguous between Shanghai and
        # Shenzhen. The dot is meaningful here, so the share-class dash
        # rewrite below must not run.
        board, _, venue = cleaned.partition(".")
        if not board.isdigit() or venue not in ("SS", "SZ"):
            return None
        return f"{board}.{venue}"
    return cleaned.replace(".", "-")


def _get_yahoo_chart_price(symbol: str, executed_at: Optional[str], market: str) -> Optional[float]:
    """Spot or historical price from Yahoo's public chart endpoint.

    Serves forex today; futures and A-shares reuse it in later phases (see
    docs/plan/13-market-expansion.md). Yahoo rejects the default requests
    User-Agent with HTTP 429, hence the browser header.
    """
    ticker = _yahoo_symbol(symbol, market)
    if not ticker:
        _price_log(f"[Price API] Invalid {market} symbol for Yahoo: {symbol}")
        return None

    dt = _parse_executed_at_to_utc(executed_at) if executed_at else None
    # A 1m series only reaches ~7 days back; fall back to daily candles beyond that.
    if dt is not None:
        age_days = (datetime.now(timezone.utc) - dt).total_seconds() / 86400
        interval, rng = ("1m", "5d") if age_days <= 5 else ("1d", "1y")
    else:
        interval, rng = "1m", "1d"

    data = _request_json_with_retry(
        "yahoo",
        "GET",
        f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}",
        params={"interval": interval, "range": rng},
        headers={"User-Agent": _YAHOO_USER_AGENT},
        retry_on_rate_limit=False,
    )

    try:
        result = data["chart"]["result"][0]  # type: ignore[index]
    except (TypeError, KeyError, IndexError):
        _price_log(f"[Price API] Yahoo returned no result for {ticker}")
        return None

    # No target time -> use the live quote.
    if dt is None:
        price = (result.get("meta") or {}).get("regularMarketPrice")
        return float(f"{float(price):.6f}") if price is not None else None

    stamps = result.get("timestamp") or []
    try:
        closes = result["indicators"]["quote"][0]["close"]
    except (TypeError, KeyError, IndexError):
        return None

    # Latest candle at or before the target time.
    target_s = int(dt.timestamp())
    closest = None
    closest_ts = None
    for ts, close in zip(stamps, closes):
        if close is None or ts is None or int(ts) > target_s:
            continue
        if closest_ts is None or int(ts) > closest_ts:
            closest_ts, closest = int(ts), float(close)

    if closest is None:
        return None
    return float(f"{closest:.6f}")


# ─── Yahoo options chain ────────────────────────────────────────────────────
# The v7 options endpoint, unlike v8 chart, rejects anonymous callers with
# "Invalid Crumb". The handshake is: hit fc.yahoo.com to be issued an A3
# cookie, exchange it at /v1/test/getcrumb for a token, then send both on
# every chain request. Both halves are session-scoped, so they are cached
# together and re-fetched only when a chain call comes back 401/403.
_YAHOO_CRUMB_TTL_SECONDS = max(60.0, float(os.environ.get("YAHOO_CRUMB_TTL_SECONDS", "1800")))
_yahoo_crumb: Optional[tuple[str, str, float]] = None  # (cookie_header, crumb, fetched_at)
_yahoo_crumb_lock = threading.Lock()

# OCC contract symbol: root + YYMMDD + C/P + strike in thousandths.
_OCC_RE = re.compile(r"^(?P<root>[A-Z]{1,6})(?P<date>\d{6})(?P<right>[CP])(?P<strike>\d{8})$")


def _yahoo_crumb_pair(force_refresh: bool = False) -> Optional[tuple[str, str]]:
    global _yahoo_crumb
    with _yahoo_crumb_lock:
        cached = _yahoo_crumb
        if (not force_refresh and cached is not None
                and (time.time() - cached[2]) < _YAHOO_CRUMB_TTL_SECONDS):
            return cached[0], cached[1]

        try:
            session = requests.Session()
            session.headers.update({"User-Agent": _YAHOO_USER_AGENT})
            # This request is expected to 404 — it exists only to be issued the cookie.
            session.get("https://fc.yahoo.com", timeout=PRICE_FETCH_TIMEOUT_SECONDS)
            resp = session.get("https://query1.finance.yahoo.com/v1/test/getcrumb",
                               timeout=PRICE_FETCH_TIMEOUT_SECONDS)
            crumb = (resp.text or "").strip()
            # A crumb is a short opaque token; an HTML error page is not one.
            if resp.status_code != 200 or not crumb or "<" in crumb or len(crumb) > 32:
                _price_log(f"[Price API] Yahoo crumb handshake failed (status {resp.status_code})")
                return None
            cookie_header = "; ".join(f"{c.name}={c.value}" for c in session.cookies)
            if not cookie_header:
                _price_log("[Price API] Yahoo crumb handshake returned no cookie")
                return None
        except Exception as exc:
            _price_log(f"[Price API] Yahoo crumb handshake error: {exc}")
            return None

        _yahoo_crumb = (cookie_header, crumb, time.time())
        return cookie_header, crumb


def _fetch_yahoo_option_chain(underlying: str, expiry_epoch: Optional[int] = None) -> Optional[dict]:
    """Raw option chain for an underlying, retrying once on a stale crumb."""
    for attempt in range(2):
        pair = _yahoo_crumb_pair(force_refresh=attempt > 0)
        if pair is None:
            return None
        cookie_header, crumb = pair
        params: dict = {"crumb": crumb}
        if expiry_epoch is not None:
            params["date"] = int(expiry_epoch)
        try:
            data = _request_json_with_retry(
                "yahoo",
                "GET",
                f"https://query1.finance.yahoo.com/v7/finance/options/{underlying}",
                params=params,
                headers={"User-Agent": _YAHOO_USER_AGENT, "Cookie": cookie_header},
                retry_on_rate_limit=False,
            )
        except Exception as exc:
            # An expired crumb comes back as 401/403. Read it off the response
            # rather than matching on the message text — the string form of a
            # requests.HTTPError happens to contain the code today, but that is
            # incidental, and a silent failure here means every option position
            # stops being marked.
            response = getattr(exc, "response", None)
            status = getattr(response, "status_code", None)
            if attempt == 0 and status in (401, 403):
                _price_log(f"[Price API] Yahoo crumb rejected ({status}); re-handshaking")
                continue
            _price_log(f"[Price API] Yahoo option chain error for {underlying}: {exc}")
            return None
        try:
            return data["optionChain"]["result"][0]  # type: ignore[index]
        except (TypeError, KeyError, IndexError):
            _price_log(f"[Price API] Yahoo returned no option chain for {underlying}")
            return None
    return None


def _option_contract_price(contract: dict) -> Optional[float]:
    """Mid of the quoted spread, falling back to last trade.

    Bid/ask is the honest mark: an option's lastPrice can be hours or days
    stale on an illiquid strike, and marking a book to it silently invents PnL.
    Mid is only used when both sides are actually quoted.
    """
    bid, ask = contract.get("bid"), contract.get("ask")
    try:
        if bid is not None and ask is not None and float(bid) > 0 and float(ask) > 0:
            return float(f"{(float(bid) + float(ask)) / 2:.6f}")
    except (TypeError, ValueError):
        pass
    last = contract.get("lastPrice")
    try:
        return float(f"{float(last):.6f}") if last is not None else None
    except (TypeError, ValueError):
        return None


def _get_yahoo_option_price(symbol: str) -> Optional[float]:
    """Price one OCC-form option contract (e.g. AAPL260720C00205000).

    There is no historical endpoint for a single contract, so executed_at is
    deliberately not a parameter — options are marked at the current quote and
    cannot be backfilled the way a chart-series market can.
    """
    parsed = _OCC_RE.match((symbol or "").strip().upper())
    if not parsed:
        _price_log(f"[Price API] Not an OCC option symbol: {symbol}")
        return None

    root = parsed.group("root")
    # Yahoo indexes each contract under its own expiry; requesting the chain
    # without a date returns only the nearest one, so derive the epoch from the
    # symbol rather than paging every expiration.
    try:
        expiry = datetime.strptime(parsed.group("date"), "%y%m%d").replace(tzinfo=UTC)
    except ValueError:
        return None

    chain = _fetch_yahoo_option_chain(root, int(expiry.timestamp()))
    if not chain:
        return None

    wanted = parsed.group(0)
    side = "calls" if parsed.group("right") == "C" else "puts"
    for contract in (chain.get("options") or [{}])[0].get(side, []):
        if str(contract.get("contractSymbol", "")).upper() == wanted:
            return _option_contract_price(contract)

    _price_log(f"[Price API] Contract {wanted} not present in {root} chain")
    return None


def get_price_from_market(
    symbol: str,
    executed_at: str,
    market: str,
    token_id: Optional[str] = None,
    outcome: Optional[str] = None,
) -> Optional[float]:
    """
    根据市场获取价格

    Args:
        symbol: 股票代码
        executed_at: 执行时间 (ISO 8601 格式)
        market: 市场类型 (us-stock, crypto)

    Returns:
        查询到的价格，如果失败返回 None
    """
    try:
        try:
            from routes_shared import normalize_market

            market = normalize_market(market)
        except Exception:
            market = (market or "").strip().lower()

        # Provider is declared on the market spec (markets.py) rather than branched on
        # the market name, so a new market only needs a registry entry plus a helper.
        provider = markets.get_spec(market)
        provider_key = provider.price_provider if provider else None

        if provider_key == "hyperliquid":
            # Try historical candle (when executed_at is provided), then fall back to mid price.
            price = _get_hyperliquid_candle_close(symbol, executed_at) or _get_hyperliquid_mid_price(symbol)
        elif provider_key == "polymarket":
            # Polymarket pricing uses public Gamma + CLOB endpoints.
            # We use the current orderbook mid price (paper trading).
            price = _get_polymarket_mid_price(symbol, token_id=token_id, outcome=outcome)
        elif provider_key == "alphavantage":
            if not ALPHA_VANTAGE_API_KEY or ALPHA_VANTAGE_API_KEY == "demo":
                _price_log("Warning: ALPHA_VANTAGE_API_KEY not set, using agent-provided price")
                return None
            price = _get_us_stock_price(symbol, executed_at)
        elif provider_key == "yahoo":
            price = _get_yahoo_chart_price(symbol, executed_at, market)
        elif provider_key == "yahoo-options":
            price = _get_yahoo_option_price(symbol)
        else:
            _price_log(f"[Price API] Unsupported market for server price fetch: {market}")
            return None

        if price is None:
            _price_log(f"[Price API] Failed to fetch {symbol} ({market}) price for time {executed_at}")
        else:
            _price_log(f"[Price API] Successfully fetched {symbol} ({market}): ${price}")

        return price
    except Exception as e:
        _price_log(f"[Price API] Error fetching {symbol} ({market}): {e}")
        try:
            from metrics import price_fetch_errors_total
            price_fetch_errors_total.labels(provider=market or "unknown").inc()
        except Exception:
            pass
        return None


def _get_us_stock_price(symbol: str, executed_at: Optional[str]) -> Optional[float]:
    """获取美股价格 — executed_at=None means "price it now"."""
    # Alpha Vantage TIME_SERIES_INTRADAY 返回美国东部时间 (ET)
    if executed_at is None:
        # Every sibling provider treats a missing timestamp as the current price
        # (yahoo takes Optional[str]; a hyperliquid candle miss falls through to
        # the mid price), and callers rely on it: routes_runs._probe_price,
        # run_engine and trading_runs all pass None to mean "now". This branch
        # used to be absent, so None hit .replace() below and raised
        # AttributeError — which the ValueError guard does not catch — making
        # EVERY us-stock lookup fail regardless of API key or quota.
        dt_et = datetime.now(UTC).astimezone(ET_TZ)
    else:
        try:
            # 先解析为 UTC
            dt_utc = datetime.fromisoformat(executed_at.replace('Z', '')).replace(tzinfo=UTC)
            # 转换为东部时间 (ET)
            dt_et = dt_utc.astimezone(ET_TZ)
        except ValueError:
            return None

    month = dt_et.strftime("%Y-%m")

    params = {
        "function": "TIME_SERIES_INTRADAY",
        "symbol": symbol,
        "interval": "1min",
        "month": month,
        "outputsize": "compact",
        "entitlement": "realtime",
        "apikey": ALPHA_VANTAGE_API_KEY
    }

    try:
        data = _request_json_with_retry(
            "alphavantage",
            "GET",
            BASE_URL,
            params=params,
        )

        if "Error Message" in data:
            _price_log(f"[Price API] Error: {data.get('Error Message')}")
            return None
        if "Note" in data:
            _activate_provider_cooldown(
                "alphavantage",
                PRICE_FETCH_RATE_LIMIT_COOLDOWN_SECONDS,
                "body rate limit note"
            )
            _price_log(f"[Price API] Rate limit: {data.get('Note')}")
            return None

        time_series_key = "Time Series (1min)"
        if time_series_key not in data:
            _price_log(f"[Price API] No time series data for {symbol}")
            return None

        time_series = data[time_series_key]
        # 使用东部时间进行比较
        target_datetime = dt_et.strftime("%Y-%m-%d %H:%M:%S")

        # 精确匹配
        if target_datetime in time_series:
            return float(time_series[target_datetime].get("4. close", 0))

        # 找最接近的之前的数据
        min_diff = float('inf')
        closest_price = None

        for time_key, values in time_series.items():
            time_dt = datetime.strptime(time_key, "%Y-%m-%d %H:%M:%S").replace(tzinfo=ET_TZ)
            if time_dt <= dt_et:
                diff = (dt_et - time_dt).total_seconds()
                if diff < min_diff:
                    min_diff = diff
                    closest_price = float(values.get("4. close", 0))

        if closest_price:
            _price_log(f"[Price API] Found closest price for {symbol}: ${closest_price} ({int(min_diff)}s earlier)")
        return closest_price

    except Exception as e:
        _price_log(f"[Price API] Exception while fetching {symbol}: {e}")
        return None


def _get_crypto_price(symbol: str, executed_at: str) -> Optional[float]:
    """
    Backwards-compat shim.
    Sooppiy 已停止使用 Alpha Vantage 的 crypto 端点；此函数保留仅为避免旧代码引用时报错。
    """
    return _get_hyperliquid_candle_close(symbol, executed_at) or _get_hyperliquid_mid_price(symbol)
