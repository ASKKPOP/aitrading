"""Factor snapshots (parameter-upgrade plan Phase 0.4).

Records the live-only decision factors — funding rate, open interest,
long/short account ratio (OKX) and StockTwits crowd tilt — one row per symbol
per refresh. These factors have no vendor history (OKX L/S ≈ 180 days,
liquidations ≈ 24h, StockTwits none), so the confluence conditions built on
them (B4 sentiment, S4 crowding) can only ever be validated live-forward.
This table is that record.

Cheap and keyless; runs regardless of the psych/scanner feature gates.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

from database import get_db_connection

logger = logging.getLogger(__name__)

FACTOR_SYMBOLS = tuple(
    s.strip().upper()
    for s in os.getenv("FACTOR_SNAPSHOT_SYMBOLS", "BTC,ETH,SOL").split(",")
    if s.strip()
)
FACTOR_HISTORY_LIMIT = 5000  # ~1.7 years at 3 symbols × 6h cadence


def _stocktwits_tilt(symbol: str) -> tuple[Optional[float], Optional[int]]:
    try:
        from analysis_sources import fetch_stocktwits_sentiment
        st = fetch_stocktwits_sentiment(f"{symbol}.X")
    except Exception:  # noqa: BLE001
        return None, None
    if not st or not st.get("messages_scored"):
        return None, None
    scored = st["messages_scored"]
    return (st["bullish"] - st["bearish"]) / scored, scored


def _global_factors() -> dict[str, Any]:
    """Once-per-refresh factors that aren't per-symbol: kimchi premium (BTC),
    ETF daily flow (BTC), whale totals (BTC/ETH). All fail-soft to None."""
    out: dict[str, Any] = {"kimchi": None, "etf": None,
                           "whale_btc": None, "whale_eth": None}
    try:
        from cross_market import build_cross_market_payload, cross_market_enabled
        if cross_market_enabled():
            kimchi = (build_cross_market_payload() or {}).get("kimchi")
            if kimchi:
                out["kimchi"] = kimchi.get("premium_pct")
    except Exception as exc:  # noqa: BLE001
        logger.debug("factor snapshot: kimchi unavailable: %s", exc)
    try:
        from market_intel import get_etf_flows_payload
        etf = get_etf_flows_payload()
        summary = etf.get("summary") or {}
        if summary.get("latest_net_inflow_usd") is not None:
            out["etf"] = float(summary["latest_net_inflow_usd"])
    except Exception as exc:  # noqa: BLE001
        logger.debug("factor snapshot: etf unavailable: %s", exc)
    try:
        from whale_feed import get_whale_payload
        whales = get_whale_payload()
        if whales.get("available"):
            totals = whales.get("totals") or {}
            out["whale_btc"] = totals.get("btc_transfer_usd")
            out["whale_eth"] = totals.get("eth_net_flow_usd")
    except Exception as exc:  # noqa: BLE001
        logger.debug("factor snapshot: whales unavailable: %s", exc)
    return out


def record_factor_snapshots(symbols: tuple[str, ...] = FACTOR_SYMBOLS) -> dict[str, Any]:
    """Fetch and persist one factor row per symbol. Fail-soft per factor."""
    from crypto_feed import (fetch_funding_rate, fetch_long_short_ratio,
                             fetch_open_interest, fetch_spot_ticker, fetch_ticker)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    written = 0
    errors: list[str] = []
    global_factors = _global_factors()

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        for symbol in symbols:
            okx = symbol if symbol.endswith("USDT") else f"{symbol}USDT"
            funding = oi_usd = ls_ratio = basis_pct = None
            last = None
            try:
                funding = fetch_funding_rate(okx)["funding_rate"]
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{symbol}:funding:{exc}")
            try:
                oi_ccy = fetch_open_interest(okx)["open_interest_ccy"]
                last = float(fetch_ticker(okx)["last_price"])
                if oi_ccy and last > 0:
                    oi_usd = oi_ccy * last
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{symbol}:oi:{exc}")
            try:
                ls_ratio = fetch_long_short_ratio(okx)["long_short_ratio"]
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{symbol}:ls:{exc}")
            # Basis (swap − spot) / spot — Plan 06 A5
            try:
                if last is None:
                    last = float(fetch_ticker(okx)["last_price"])
                spot = float(fetch_spot_ticker(okx)["last_price"])
                if spot > 0 and last > 0:
                    basis_pct = round((last - spot) / spot * 100, 4)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{symbol}:basis:{exc}")
            tilt, tilt_n = _stocktwits_tilt(symbol)

            base = symbol.replace("USDT", "")
            kimchi = global_factors["kimchi"] if base == "BTC" else None
            etf = global_factors["etf"] if base == "BTC" else None
            whale = (global_factors["whale_btc"] if base == "BTC"
                     else global_factors["whale_eth"] if base == "ETH" else None)

            cursor.execute(
                """INSERT INTO factor_snapshots
                   (symbol, funding_rate, open_interest_usd, long_short_ratio,
                    stocktwits_tilt, stocktwits_n, basis_pct, kimchi_premium_pct,
                    etf_flow_usd, whale_net_flow_usd, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (symbol, funding, oi_usd, ls_ratio, tilt, tilt_n,
                 basis_pct, kimchi, etf, whale, now))
            written += 1

        # prune to a bounded history, mirroring the other snapshot tables
        cursor.execute(
            """SELECT id FROM factor_snapshots
               ORDER BY created_at DESC, id DESC
               LIMIT 1 OFFSET ?""", (FACTOR_HISTORY_LIMIT,))
        cutoff = cursor.fetchone()
        if cutoff:
            cursor.execute("DELETE FROM factor_snapshots WHERE id < ?", (cutoff["id"],))
        conn.commit()
    finally:
        conn.close()

    return {"written": written, "errors": errors, "created_at": now}
