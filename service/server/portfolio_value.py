"""One definition of what an open position is worth to its owner.

WHY (2026-08-07). Profit was computed three different ways and every one of
them was wrong for a leveraged book, because `agents.cash` has only the MARGIN
deducted while the SQL added back the whole NOTIONAL:

    truth                                    +0.51
    public profile   cash - seed            -29.04    (off by -29.55)
    leaderboard SQL  cash + notional - seed +30.09    (off by +29.58)

Both errors are exactly the leverage gap (notional - margin). The same agent
read -2.9% on one page and +3.0% on another while it was in fact +0.05% up.

A position returns its MARGIN plus its unrealized P&L, not its notional. At
leverage 1 that is identical to the old expression, so spot books are
unaffected; only leveraged ones move, and they move to the truth.

The expression lived inline in four places across two files, which is how the
three versions drifted apart. It lives here now.
"""

# Value of the caller's open positions: margin returned + unrealized P&L.
# Expects the positions table aliased `p`. Use inside COALESCE(SUM(...), 0).
POSITION_VALUE_CASE = """
                CASE
                    WHEN p.current_price IS NULL THEN
                        p.entry_price * ABS(p.quantity) / COALESCE(NULLIF(p.leverage, 0), 1)
                    WHEN p.side = 'long' THEN
                        p.entry_price * ABS(p.quantity) / COALESCE(NULLIF(p.leverage, 0), 1)
                        + (p.current_price - p.entry_price) * ABS(p.quantity)
                    ELSE
                        p.entry_price * ABS(p.quantity) / COALESCE(NULLIF(p.leverage, 0), 1)
                        + (p.entry_price - p.current_price) * ABS(p.quantity)
                END
"""

POSITION_VALUE_SUM = f"COALESCE(SUM({POSITION_VALUE_CASE}), 0)"


def position_value(entry_price: float, quantity: float, current_price,
                   side: str, leverage) -> float:
    """Python mirror of POSITION_VALUE_CASE, for callers that already hold
    rows. Kept beside the SQL on purpose: when they drift, profit drifts."""
    entry = float(entry_price or 0)
    qty = abs(float(quantity or 0))
    lev = float(leverage or 1) or 1.0
    margin = entry * qty / lev
    if current_price is None:
        return margin
    mark = float(current_price)
    if str(side) == "long":
        return margin + (mark - entry) * qty
    return margin + (entry - mark) * qty
