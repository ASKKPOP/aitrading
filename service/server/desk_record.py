"""What this desk's book has ACTUALLY reached — its own excursion record.

WHY THIS EXISTS (measured on prod 2026-08-18, and it is not a small gap).

Both prompts that ask the desk for a bracket tell it to pick "a level the
move can realistically reach", and neither gives it a single number about
what its own book has ever reached. Measured across 66 closed runs that
opened a position:

    * 42% never had a positive moment at all — their best cumulative P&L
      was still underwater.
    * Among the 58% that did go positive: best moment median 0.17% of
      notional, p75 0.34%, all-time best 0.97%. No closed run has ever
      peaked above 1% of notional.
    * The desk's authored `target_pct` has a median of 4.80%.

So the target is 5-30x anything the book has achieved, and every consumer
downstream — the R:R floor (`target_pct >= 2 x stop_pct`), sizing, and
`outlook.exit.target_px` — runs on that number. An earlier candle replay
(plan 22 backlog, H6/H7) reached the same verdict independently: 0 of 34
legs reached their own target and no target above 2.00% has ever been hit.

This module states the fact; it does NOT clamp anything. Which target to
write stays the desk's call (`trading-decisions-belong-to-sooppiy-ai`) —
the platform's job is to stop hiding the measurement from it.

MEASURED REFUTATION (2026-08-18), and it is why this line has two halves.
The reachability figure alone invites exactly one wrong inference — "my
target is unreachable, so shrink it" — and the shipped 2x R:R floor then
drags the stop to ~0.5%. Replayed on 22 crypto entries against their own
at_time horizons, that is the WORST band measured:

    stop 0.40 / target 0.80   stop-first 14/22   -0.090%/trade
    stop 0.60 / target 1.20   stop-first 15/22   -0.336%/trade
    stop 1.50 / target 3.00   stop-first  6/22   +0.046%/trade
    stop 2.50 / target 5.00   stop-first  2/22   +0.137%/trade

Expectancy improves monotonically as stops WIDEN. Honest limits: n=22, and at
wide stops most entries resolve as NEITHER (18 of 22 at 2.5%), so the wide-band
advantage rests on ~4 resolved trades and is NOT established. What IS
established is that the tighter band is not supported, so the line must never
be read as an argument for it.

UNIT NOTE, load-bearing: pnl / notional IS the % price move, because
pnl = move x qty and notional = price x qty. Any other denominator produces
a number that cannot be compared to `target_pct`, which is what makes this
line meaningful rather than decorative.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Optional

from database import get_db_connection

logger = logging.getLogger(__name__)

# A record built on a handful of runs is noise wearing a decimal point.
_MIN_RUNS = 10
# The record moves only when a run CLOSES, so an hour-stale answer is a
# correct answer — and the query must never be on the per-cycle hot path.
_TTL_SEC = 3600
# Bound the scan: the desk's recent book is the relevant one, and an
# unbounded history would eventually make this expensive.
_MAX_RUNS = 300

_CACHE: dict[str, tuple[float, Optional[dict]]] = {}


def _pct(values: list[float], q: float) -> float:
    return values[min(len(values) - 1, int(q * len(values)))]


def _compute(market: str) -> Optional[dict]:
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, peak_pnl_usd FROM trading_runs WHERE status = 'stopped' "
            "AND market = ? AND peak_pnl_usd IS NOT NULL "
            "ORDER BY id DESC LIMIT ?", (market, _MAX_RUNS))
        runs = {int(r["id"]): float(r["peak_pnl_usd"]) for r in cur.fetchall()}
        if not runs:
            return None
        # Notional from the OPENING legs. Not from `signals`: a closing row
        # overwrites `entry_price` with the exit price, so entry read from a
        # closed leg yields exactly 0.00% every time — a query bug that reads
        # like a clean null result (standing trap, backlog 2026-08-17).
        ids = ",".join("?" for _ in runs)
        cur.execute(
            f"SELECT run_id, payload FROM run_events WHERE event_type = 'trade' "
            f"AND run_id IN ({ids})", tuple(runs))
        notional: dict[int, float] = {}
        for row in cur.fetchall():
            try:
                p = json.loads(row["payload"] or "{}")
                if p.get("side") not in ("buy", "short"):
                    continue
                rid = int(row["run_id"])
                notional[rid] = notional.get(rid, 0.0) + abs(
                    float(p["quantity"]) * float(p["price"]))
            except (TypeError, ValueError, KeyError):
                continue
    finally:
        conn.close()
    # A run that never opened a position has no scale for its peak.
    pcts = sorted(runs[rid] / n * 100.0
                  for rid, n in notional.items() if n > 0 and rid in runs)
    if len(pcts) < _MIN_RUNS:
        return None
    positive = [p for p in pcts if p > 0]
    return {
        "market": market,
        "n": len(pcts),
        "never_positive": (len(pcts) - len(positive)) / len(pcts),
        "median": _pct(pcts, 0.50),
        "p75": _pct(pcts, 0.75),
        "best": max(pcts),
    }


def excursion_record(market: str) -> Optional[dict[str, Any]]:
    """The distribution of best-moment-reached, as a % of entry notional.

    Fail-soft to None: a missing record costs the prompt one sentence, and a
    raising one would cost the cycle."""
    try:
        hit = _CACHE.get(market)
        if hit and (time.time() - hit[0]) < _TTL_SEC:
            return hit[1]
        rec = _compute(market)
        _CACHE[market] = (time.time(), rec)
        return rec
    except Exception as exc:  # noqa: BLE001
        logger.warning("excursion record unavailable (%s): %s", market, exc)
        return None


def record_line(market: str) -> str:
    """Two halves of measured fact for a prompt that asks for a target:
    what this book has reached, AND what happened when the bracket was
    tightened in response. The second half is not optional — see the
    refutation in this module's header.

    Silent below `_MIN_RUNS` — telling the desk a ceiling derived from three
    runs would be worse than telling it nothing."""
    rec = excursion_record(market)
    if not rec:
        return ""
    return (
        f"REACHABILITY (this desk's own closed {market} book, n={rec['n']} "
        f"runs that opened a position): the best moment a run ever reached "
        f"was {rec['best']:.2f}% of entry; the median run's best moment was "
        f"{rec['median']:.2f}%, p75 {rec['p75']:.2f}%, and "
        f"{rec['never_positive'] * 100:.0f}% of runs never had a positive "
        f"moment at all. These are measured lower bounds (marks are sampled, "
        f"not continuous). A target beyond that band has not been reached "
        f"here. BUT DO NOT ANSWER THIS WITH A TIGHTER BRACKET: replayed on "
        f"22 entries against their own horizons, a 0.6% stop with a 1.2% "
        f"target was hit on the STOP first in 15 of 22 and lost 0.34% per "
        f"trade, and expectancy improved monotonically as stops WIDENED. The "
        f"same quiet tape that withholds your target also fails to spare "
        f"your stop — tightening converts no-resolution into stopped-out. "
        f"Judge whether this trade is worth taking at all."
    )
