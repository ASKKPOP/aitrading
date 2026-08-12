"""US-equity positioning snapshots — Plan 23 Phase D.

The v2 crowd-fade needs positioning history and NO vendor sells it
(factor_snapshots.py established the pattern for crypto): record it
live-forward, daily-cadence, starting NOW, so months of self-accrued,
point-in-time data exist by the time the fade's own gate needs them.
Every paper trade can then store the positioning it saw at decision time.

Recorded per symbol (fail-soft per source, a row is written with whatever
resolved):
  putcall_oi_ratio     put OI / call OI over the front expiry, from the
                       Yahoo chain fetch that already exists
                       (price_fetcher._fetch_yahoo_option_chain)
  stocktwits_tilt      (bullish - bearish) / scored, BARE symbol (the
                       crypto recorder's '.X' suffix deliberately dropped)
  short_volume_ratio   FINRA daily consolidated short-sale volume
                       (ShortVolume / TotalVolume), T+1 publication — the
                       fetcher walks back over weekends/holidays and the
                       whole day is cached per process; NULL when FINRA
                       has no row for the symbol

Universe: US_FACTOR_WATCHLIST env (comma list) or a fixed mega-cap default,
plus every symbol with an active us-stock run.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

from database import begin_write_transaction, get_db_connection

logger = logging.getLogger(__name__)

DEFAULT_WATCHLIST = ("AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA",
                     "AVGO", "JPM", "LLY", "V", "XOM")


def watchlist() -> tuple[str, ...]:
    raw = os.getenv("US_FACTOR_WATCHLIST", "").strip()
    base = tuple(s.strip().upper() for s in raw.split(",") if s.strip()) \
        or DEFAULT_WATCHLIST
    extra: list[str] = []
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT symbol FROM trading_runs WHERE market = ?"
                    " AND status IN ('armed', 'running', 'paused')",
                    ("us-stock",))
        extra = [str(r["symbol"]).upper() for r in cur.fetchall()]
        conn.close()
    except Exception:  # noqa: BLE001
        pass
    seen: list[str] = []
    for s in tuple(base) + tuple(extra):
        if s and s not in seen:
            seen.append(s)
    return tuple(seen)


def putcall_oi_ratio(symbol: str) -> Optional[float]:
    """Put OI / call OI over the front expiry; None when the chain is
    unavailable or call OI is zero (a ratio against nothing is not data)."""
    try:
        import price_fetcher
        chain = price_fetcher._fetch_yahoo_option_chain(symbol)
        block = (chain or {}).get("options") or [{}]
        calls = block[0].get("calls") or []
        puts = block[0].get("puts") or []
        call_oi = sum(int(c.get("openInterest") or 0) for c in calls)
        put_oi = sum(int(p.get("openInterest") or 0) for p in puts)
        if call_oi <= 0:
            return None
        return round(put_oi / call_oi, 4)
    except Exception:  # noqa: BLE001
        logger.debug("putcall unavailable (%s)", symbol, exc_info=True)
        return None


def stocktwits_tilt(symbol: str) -> "tuple[Optional[float], Optional[int]]":
    """Bare-symbol StockTwits tilt — the crypto recorder appends '.X'; a
    us-stock symbol must not."""
    try:
        from analysis_sources import fetch_stocktwits_sentiment
        st = fetch_stocktwits_sentiment(symbol)
    except Exception:  # noqa: BLE001
        return None, None
    if not st or not st.get("messages_scored"):
        return None, None
    scored = st["messages_scored"]
    return (st["bullish"] - st["bearish"]) / scored, scored


# FINRA consolidated daily short-sale volume (free, T+1). The fade's honest
# "crowd just acted" read — the biweekly short INTEREST report is context
# only (plan §5). One file per trading day, pipe-delimited:
# Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market
_FINRA_URL = "https://cdn.finra.org/equity/regsho/daily/CNMSshvol{date}.txt"
_finra_cache: dict[str, dict[str, float]] = {}


def finra_short_volume_ratios(lookback_days: int = 5) -> dict[str, float]:
    """symbol -> ShortVolume/TotalVolume for the most recent published file.

    Walks back up to `lookback_days` calendar days (weekends/holidays have no
    file). {} on total failure — null-honest, the recorder writes NULLs."""
    import requests
    from datetime import timedelta
    today = datetime.now(timezone.utc).date()
    for back in range(1, lookback_days + 1):
        day = (today - timedelta(days=back)).strftime("%Y%m%d")
        if day in _finra_cache:
            return _finra_cache[day]
        try:
            resp = requests.get(_FINRA_URL.format(date=day), timeout=30)
            if resp.status_code != 200 or not resp.text.strip():
                continue
            out: dict[str, float] = {}
            for line in resp.text.splitlines()[1:]:
                parts = line.split("|")
                if len(parts) < 5:
                    continue
                try:
                    total = float(parts[4])
                    if total > 0:
                        out[parts[1].strip().upper()] = round(
                            float(parts[2]) / total, 4)
                except (TypeError, ValueError):
                    continue
            if out:
                _finra_cache.clear()          # keep exactly one day cached
                _finra_cache[day] = out
                return out
        except Exception:  # noqa: BLE001
            logger.debug("FINRA short-volume fetch failed (%s)", day,
                         exc_info=True)
    return {}


def record_us_stock_factor_snapshots(symbols: "tuple[str, ...] | None" = None
                                     ) -> dict[str, Any]:
    """One snapshot row per symbol. Fail-soft per source AND per symbol —
    a dead feed writes NULLs, never blocks the sweep."""
    syms = symbols if symbols is not None else watchlist()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        short_ratios = finra_short_volume_ratios()
    except Exception:  # noqa: BLE001
        short_ratios = {}
    written, errors = 0, []
    for sym in syms:
        try:
            pc = putcall_oi_ratio(sym)
            tilt, tilt_n = stocktwits_tilt(sym)
            conn = get_db_connection()
            try:
                cur = conn.cursor()
                begin_write_transaction(cur)
                cur.execute(
                    """INSERT INTO us_stock_factor_snapshots
                       (symbol, putcall_oi_ratio, short_volume_ratio,
                        stocktwits_tilt, tilt_n, created_at)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (sym, pc, short_ratios.get(sym), tilt, tilt_n, now))
                conn.commit()
                written += 1
            finally:
                conn.close()
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{sym}:{type(exc).__name__}")
    return {"written": written, "errors": errors}
