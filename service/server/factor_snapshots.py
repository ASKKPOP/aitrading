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


def record_factor_snapshots(symbols: tuple[str, ...] = FACTOR_SYMBOLS) -> dict[str, Any]:
    """Fetch and persist one factor row per symbol. Fail-soft per factor."""
    from crypto_feed import fetch_funding_rate, fetch_long_short_ratio, fetch_open_interest, fetch_ticker

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    written = 0
    errors: list[str] = []

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        for symbol in symbols:
            okx = symbol if symbol.endswith("USDT") else f"{symbol}USDT"
            funding = oi_usd = ls_ratio = None
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
            tilt, tilt_n = _stocktwits_tilt(symbol)

            cursor.execute(
                """INSERT INTO factor_snapshots
                   (symbol, funding_rate, open_interest_usd, long_short_ratio,
                    stocktwits_tilt, stocktwits_n, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (symbol, funding, oi_usd, ls_ratio, tilt, tilt_n, now))
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
