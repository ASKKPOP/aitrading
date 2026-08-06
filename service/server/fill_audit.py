"""fill_audit.py — how much of the book was transacted at a price that was
not moving?

WHY THIS EXISTS (2026-08-06, cycle 83). The frozen-mark finding started as a
decision-quality problem — the desk reading a tape that had stopped. It is
also a FILL-quality problem: run 977 exited GC at `4320.700195`, the exact
price that symbol had printed for 70+ minutes, and booked +1.65 measured
against that stale number. Every fill takes its price from the same mark, so
a frozen feed does not merely mislead the desk, it prices the trade.

Nothing recorded that. `trade` events carry price and fee and no notion of
whether the price was live, so the day's realized P&L could not be split
into "earned" and "booked against a motionless tape". This module makes that
split reportable, exactly as `pnl_audit` made the ledger/adapt split
reportable and `ratchet_audit` made the retro-arm shape reportable.

THE SIGNATURE, chosen because it needs no reconstruction and no new column:
two fills on the SAME symbol at the SAME price to full float precision,
separated by real time. Live markets do not reprint 4320.700195 three hours
apart. It reads `run_events` only, computes nothing but arithmetic, and
NEVER writes.

⚠️ WHAT THIS DOES NOT CLAIM. A repeat print is evidence the mark was stuck,
not proof the true market price was different — that needs an independent
quote this module deliberately does not fetch. And it cannot see a freeze
that produced only ONE fill, so the count is a FLOOR, never a ceiling.

⚠️ It exits non-zero whenever repeat-price fills exist, and will therefore
stay red until the feed is fixed. That is intended: the condition is live
and unresolved, and a monitor that goes quiet on an ongoing fault is the
failure this whole family of tools was built to stop.

Usage inside the prod container:

    docker exec -w /app/service/server sooppiy-worker \
        python -m fill_audit --since 2026-08-06
"""

from __future__ import annotations

import argparse
import json
from typing import Any, Optional

# Two fills closer together than this can legitimately share a price — a
# quiet minute is not a frozen feed. Beyond it, an identical float is the
# tape repeating itself.
MIN_GAP_SECONDS = 600


def _secs(ts: str) -> Optional[tuple[int, int]]:
    """(yyyymmdd, seconds-past-midnight) from an ISO-ish timestamp."""
    t = str(ts)[:19].replace(" ", "T")
    try:
        d, hms = t.split("T")
        h, m, s = (int(x) for x in hms.split(":"))
        return (int(d.replace("-", "")), h * 3600 + m * 60 + s)
    except (ValueError, TypeError):
        return None


def gap_seconds(a: str, b: str) -> Optional[int]:
    """Absolute gap in seconds, or None across a day boundary or on junk.

    Returning None rather than guessing keeps a midnight-spanning pair OUT
    of the findings — under-reporting, which is the safe direction for a
    tool whose count is already a floor.
    """
    x, y = _secs(a), _secs(b)
    if x is None or y is None or x[0] != y[0]:
        return None
    return abs(y[1] - x[1])


def _rows(cursor, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    cursor.execute(sql, params)
    return [dict(r) for r in cursor.fetchall()]


def repeat_price_fills(since: str, *, conn=None,
                       min_gap: int = MIN_GAP_SECONDS) -> list[dict[str, Any]]:
    """Fills whose price exactly repeats an earlier fill on the same symbol.

    One row per repeat, carrying the symbol, both timestamps, the shared
    price, the gap, and the fill's notional — the number that says how much
    of the book was transacted against a price that was not moving.
    """
    own = conn is None
    if own:
        from database import get_db_connection
        conn = get_db_connection()
    try:
        cursor = conn.cursor()
        trades = _rows(cursor,
                       "SELECT run_id, ts, payload FROM run_events WHERE "
                       "event_type = 'trade' AND ts >= ? ORDER BY seq",
                       (since,))
        first_seen: dict[tuple[str, float], str] = {}
        out: list[dict[str, Any]] = []
        for row in trades:
            try:
                p = json.loads(row["payload"])
                symbol = str(p["symbol"])
                price = float(p["price"])
                qty = abs(float(p.get("quantity") or 0))
            except (KeyError, ValueError, TypeError):
                continue
            if price <= 0:
                continue
            key = (symbol, price)
            prior = first_seen.get(key)
            if prior is None:
                first_seen[key] = str(row["ts"])
                continue
            gap = gap_seconds(prior, str(row["ts"]))
            if gap is None or gap < min_gap:
                continue
            out.append({
                "run_id": row["run_id"],
                "symbol": symbol,
                "price": price,
                "first_at": prior,
                "repeat_at": str(row["ts"]),
                "gap_seconds": gap,
                "notional": qty * price,
            })
        return out
    finally:
        if own:
            conn.close()


def format_report(rows: list[dict[str, Any]]) -> str:
    head = (f"{'run':>6}  {'symbol':<10} {'price':>14}  {'first':<20} "
            f"{'repeat':<20} {'gap':>7}  {'notional':>12}")
    lines = ["FILLS AT A PRICE THAT HAD ALREADY STOPPED MOVING",
             head, "-" * len(head)]
    for r in sorted(rows, key=lambda x: -x["gap_seconds"]):
        lines.append(
            f"{r['run_id']:>6}  {r['symbol']:<10} {r['price']:>14.6f}  "
            f"{r['first_at'][:19]:<20} {r['repeat_at'][:19]:<20} "
            f"{r['gap_seconds'] // 60:>5}m  {r['notional']:>12,.2f}")
    lines.append("-" * len(head))
    if not rows:
        lines.append("no fill repeated an earlier price — the tape was "
                     "moving for every trade in this window.")
        return "\n".join(lines)
    total = sum(r["notional"] for r in rows)
    syms = sorted({r["symbol"] for r in rows})
    lines.append(f"{len(rows)} repeat-price fill(s) across {len(syms)} "
                 f"symbol(s) ({', '.join(syms)}); "
                 f"${total:,.2f} of notional transacted at a stalled price.")
    lines.append("This is a FLOOR: a freeze that produced only one fill "
                 "leaves no repeat to find. It is evidence the mark was "
                 "stuck, not proof of the true market price.")
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--since", default="2026-08-06")
    ap.add_argument("--min-gap", type=int, default=MIN_GAP_SECONDS,
                    help="seconds; below this a shared price is just a quiet "
                         "market, not a frozen one")
    args = ap.parse_args(argv)
    rows = repeat_price_fills(args.since, min_gap=args.min_gap)
    print(format_report(rows))
    return 1 if rows else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
