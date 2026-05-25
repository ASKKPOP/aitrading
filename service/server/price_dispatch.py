"""price_dispatch.py — single write-path for position prices.

Phase 4.5 introduces push-based market data; both the existing polling
loop (tasks.update_position_prices) and the new push subscriber call
this function to persist a price. Centralising the SQL means the two
sources can't drift in semantics (which market columns are matched,
how token_id partitions Polymarket entries, etc.).
"""
from __future__ import annotations

import math

import database


def apply_price_update(
    symbol: str,
    market: str,
    price: float,
    *,
    token_id: str = "",
) -> int:
    """Update `current_price` on every matching position; return rows affected.

    Match keys: (symbol, market, COALESCE(token_id, '')). When the same
    symbol trades in multiple markets, only the explicitly-named market
    is touched.

    Raises ValueError on price < 0 or NaN. Callers should drop or repair
    upstream rather than store nonsense.
    """
    if not isinstance(price, (int, float)) or math.isnan(price) or price < 0:
        raise ValueError(f"Invalid price for {symbol}/{market}: {price!r}")

    conn = database.get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE positions
            SET current_price = ?
            WHERE symbol = ?
              AND market = ?
              AND COALESCE(token_id, '') = COALESCE(?, '')
            """,
            (float(price), symbol, market, token_id or ""),
        )
        conn.commit()
        return int(cur.rowcount or 0)
    finally:
        conn.close()
