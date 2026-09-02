"""filings_feed.py — SEC EDGAR insider filings (Form 4) -> smart-money score.

Feed #5 of the swing signal stack (research/SWING_SIGNAL_STACK.md §2), which
the stack's `smart_money` processor (w=0.15) had no collector for. Keyless and
official: data.sec.gov requires only a declaring User-Agent.

    submissions/CIK##########.json   the company's recent filing index
    Archives/edgar/data/../*.xml     each Form 4's raw ownership XML

**Only open-market codes count.** Measured live 2026-08-30 across NVDA and
TSLA Form 4s, the code mix was A(grant) / G(gift) / M(option exercise) /
F(tax withholding) / S(sale) / P(purchase). Only P and S are a decision an
insider made with their own money; scoring grants as buying would invert the
signal on any company that pays in stock. Everything else is counted in
`skipped_codes` and scores nothing.

No P/S in the window means **no coverage** (score None), never a neutral 0 —
swing_stack renormalizes a None weight away, while 0 asserts "insiders are
genuinely balanced", which we have not measured.

Env-gated (FILINGS_FEED_ENABLED, default off) and fail-soft throughout: any
upstream problem degrades to less coverage, never an exception to the caller.
"""
from __future__ import annotations

import logging
import os
import time
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

import requests

import cache

logger = logging.getLogger(__name__)

_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
_ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{document}"
_TIMEOUT_S = 15.0
_TICKER_CACHE_KEY = "filings_feed:tickers"
_TICKER_TTL_S = 7 * 24 * 3600
_READ_CACHE_KEY = "filings_feed:read:{symbol}"

# SEC asks every automated client to declare itself; requests without a
# contactable UA get 403.
_DEFAULT_UA = "Sooppiy Research (contact@sooppiy.com)"

OPEN_MARKET_BUY = "P"
OPEN_MARKET_SELL = "S"

_tickers_memo: Optional[dict[str, int]] = None


def enabled() -> bool:
    return os.environ.get("FILINGS_FEED_ENABLED", "false").strip().lower() in {
        "1", "true", "yes", "on",
    }


def lookback_days() -> int:
    try:
        return max(1, int(os.environ.get("FILINGS_LOOKBACK_DAYS", "90")))
    except ValueError:
        return 90


def max_filings_per_symbol() -> int:
    try:
        return max(1, int(os.environ.get("FILINGS_MAX_PER_SYMBOL", "20")))
    except ValueError:
        return 20


def reset_caches() -> None:
    """Drop the in-process ticker map (tests, and after a config change)."""
    global _tickers_memo
    _tickers_memo = None


def _headers() -> dict[str, str]:
    return {"User-Agent": os.environ.get("SEC_USER_AGENT", _DEFAULT_UA)}


def _get_json(url: str) -> Any:
    resp = requests.get(url, headers=_headers(), timeout=_TIMEOUT_S)
    resp.raise_for_status()
    return resp.json()


def _get_text(url: str) -> str:
    resp = requests.get(url, headers=_headers(), timeout=_TIMEOUT_S)
    resp.raise_for_status()
    return resp.text


def _ticker_map() -> dict[str, int]:
    """SYMBOL -> CIK. Cached for a week; the file changes rarely."""
    global _tickers_memo
    if _tickers_memo is not None:
        return _tickers_memo
    cached = cache.get_json(_TICKER_CACHE_KEY)
    if isinstance(cached, dict) and cached:
        _tickers_memo = {k: int(v) for k, v in cached.items()}
        return _tickers_memo
    try:
        raw = _get_json(_TICKERS_URL)
    except Exception as exc:  # noqa: BLE001 — degrade to no coverage
        logger.warning("filings_feed ticker map fetch failed: %s", exc)
        return {}
    mapping: dict[str, int] = {}
    for entry in (raw or {}).values():
        try:
            mapping[str(entry["ticker"]).upper()] = int(entry["cik_str"])
        except (KeyError, TypeError, ValueError):
            continue
    if mapping:
        cache.set_json(_TICKER_CACHE_KEY, mapping, ttl_seconds=_TICKER_TTL_S)
        _tickers_memo = mapping
    return mapping


def cik_for(symbol: str) -> Optional[int]:
    return _ticker_map().get((symbol or "").strip().upper())


def _document_url(cik: int, accession: str, primary_document: str) -> str:
    """Raw ownership XML, not EDGAR's XSL-rendered HTML.

    `primaryDocument` arrives as "xslF345X06/wk-form4_178.xml" — that prefix
    is the human-readable render; the machine-readable XML sits beside it."""
    return _ARCHIVE_URL.format(
        cik=int(cik),
        accession=accession.replace("-", ""),
        document=primary_document.split("/")[-1],
    )


def _parse_form4(xml_text: str) -> tuple[float, float, int, Counter]:
    """(buy_usd, sell_usd, open_market_count, skipped_code_counts)."""
    root = ET.fromstring(xml_text)
    buy_usd = 0.0
    sell_usd = 0.0
    counted = 0
    skipped: Counter = Counter()
    for tx in root.iter("nonDerivativeTransaction"):
        code = (tx.findtext("./transactionCoding/transactionCode") or "").strip().upper()
        if code not in (OPEN_MARKET_BUY, OPEN_MARKET_SELL):
            if code:
                skipped[code] += 1
            continue
        try:
            shares = float(tx.findtext("./transactionAmounts/transactionShares/value") or 0)
            price = float(
                tx.findtext("./transactionAmounts/transactionPricePerShare/value") or 0
            )
        except (TypeError, ValueError):
            continue
        value = shares * price
        if value <= 0:
            continue
        counted += 1
        if code == OPEN_MARKET_BUY:
            buy_usd += value
        else:
            sell_usd += value
    return buy_usd, sell_usd, counted, skipped


def _empty_read(symbol: str, cik: Optional[int]) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "cik": cik,
        "score": None,
        "buy_usd": 0.0,
        "sell_usd": 0.0,
        "transactions": 0,
        "filings_read": 0,
        "errors": 0,
        "skipped_codes": {},
        "lookback_days": lookback_days(),
    }


def insider_read(symbol: str, today: Optional[str] = None) -> dict[str, Any]:
    """Insider open-market flow for `symbol` over the lookback window.

    Returns a read dict whose `score` is -20..+100 (value-weighted net buy
    ratio, sell side capped at -20 — see the base-rate note at the scoring
    site) or None when the window holds no open-market transaction."""
    symbol = (symbol or "").strip().upper()
    cik = cik_for(symbol)
    read = _empty_read(symbol, cik)
    if cik is None:
        return read

    try:
        submissions = _get_json(_SUBMISSIONS_URL.format(cik=cik))
    except Exception as exc:  # noqa: BLE001
        logger.warning("filings_feed submissions failed for %s: %s", symbol, exc)
        read["errors"] += 1
        return read

    recent = ((submissions or {}).get("filings") or {}).get("recent") or {}
    forms = recent.get("form") or []
    dates = recent.get("filingDate") or []
    accessions = recent.get("accessionNumber") or []
    documents = recent.get("primaryDocument") or []

    ref = (
        datetime.strptime(today, "%Y-%m-%d").date()
        if today
        else datetime.now(timezone.utc).date()
    )
    cutoff = ref - timedelta(days=lookback_days())

    buy_usd = 0.0
    sell_usd = 0.0
    counted = 0
    attempted = 0
    skipped: Counter = Counter()
    cap = max_filings_per_symbol()
    for form, filing_date, accession, document in zip(forms, dates, accessions, documents):
        # Bound ATTEMPTS, not successes: a systematically failing SEC would
        # otherwise cost one request per Form 4 in the whole index.
        if attempted >= cap:
            break
        if str(form).strip() != "4":
            continue
        try:
            filed = date.fromisoformat(str(filing_date))
        except (TypeError, ValueError):
            continue
        if filed < cutoff:
            continue
        attempted += 1
        try:
            xml_text = _get_text(_document_url(cik, accession, document))
            f_buy, f_sell, f_count, f_skipped = _parse_form4(xml_text)
        except Exception as exc:  # noqa: BLE001 — one bad filing, not the read
            logger.debug("filings_feed skipped %s %s: %s", symbol, accession, exc)
            read["errors"] += 1
            continue
        read["filings_read"] += 1
        buy_usd += f_buy
        sell_usd += f_sell
        counted += f_count
        skipped.update(f_skipped)
        time.sleep(_request_pause())

    read["buy_usd"] = round(buy_usd, 2)
    read["sell_usd"] = round(sell_usd, 2)
    read["transactions"] = counted
    read["skipped_codes"] = dict(skipped)
    total = buy_usd + sell_usd
    if counted and total > 0:
        # Insider-sale base-rate floor (measured live 2026-09-02): with the
        # raw net ratio, 225 of 315 pipeline readings sat at EXACTLY -100 —
        # large-cap insiders sell almost continuously for compensation
        # liquidity, so an unbounded negative side carries no information and
        # anchored every composite ~13 points down. Buying is the costly,
        # informative direction (unchanged, up to +100); the sell side is
        # capped at -20 so routine liquidation reads as a mild negative
        # instead of a pinned floor. Replay of the 48h of stored decisions
        # showed the cap changes NO past outcome (0 entries either way).
        read["score"] = round(
            max(-20.0, (buy_usd - sell_usd) / total * 100.0), 2)
    return read


def _request_pause() -> float:
    """SEC asks for <= 10 requests/second; stay well inside it."""
    try:
        return max(0.0, float(os.environ.get("FILINGS_REQUEST_PAUSE_S", "0.12")))
    except ValueError:
        return 0.12


def smart_money_score(symbol: str) -> Optional[float]:
    """Just the score, cached briefly — Form 4s arrive on a T+2 clock."""
    key = _READ_CACHE_KEY.format(symbol=(symbol or "").upper())
    cached = cache.get_json(key)
    if isinstance(cached, dict):
        return cached.get("score")
    read = insider_read(symbol)
    cache.set_json(key, read, ttl_seconds=6 * 3600)
    return read["score"]
