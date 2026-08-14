"""pnl_audit.py — one trustworthy realized-P&L number, and a self-check.

WHY THIS EXISTS (2026-08-06). The automation-monitoring runbook carried a
hand-written SQL snippet as its "authoritative" realized-P&L query:

    SUM(JSON_EXTRACT(payload,'$.realized')) over adapt events

That snippet was a SECOND, independent implementation of the platform's
accounting, and it drifted. It omitted every forced flatten
(`run:N:flatten` emits a trade event; before #249 it emitted no `adapt`),
so it understated results precisely on the worst days — 08-04 read −20.61
against a true −62.57, 08-05 read +73.21 against a true +8.62. Across all
history it hid **71 flattens worth −166.03**.

The platform itself was never wrong: `realized_pnl_usd` / `compute_run_pnl`
replay SIGNALS, and a flatten IS a signal. No user ever saw a bad number.
The defect lived entirely in the monitoring layer — and nothing was
checking the monitor, so it stayed wrong for weeks.

So this module exists to make that class of failure loud instead of silent:

  * ONE implementation of the ledger replay, unit-tested, importable — not
    a snippet retyped into a runbook.
  * Every result reports BOTH the ledger replay AND the adapt-stream sum
    ALONGSIDE their delta. Agreement is evidence; disagreement is a finding
    that surfaces on the next cycle rather than after weeks.

SCOPE CAVEAT (R13 adversarial pass, 2026-08-14). The fee_asym correction
makes this audit validate pnl-vs-adapt CONSISTENCY, not fee magnitudes:
an error in a trade event's ENTRY-side fee_usd (e.g. a broker adapter
recording 10× fees) is absorbed into fee_asym and invisible here — the
adapt stream carries no entry-fee information to compare against. Fee
integrity needs its own check outside this module.

Usage inside the prod container:

    docker exec -w /app/service/server sooppiy-worker \
        python -m pnl_audit --since 2026-08-06
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from typing import Any, Iterable, Optional

# A day's two figures differ benignly in a KNOWN way: `adapt` nets
# exit-side fees only while the ledger charges both sides, so the expected
# delta is minus the day's entry-side fees — computed per day (fee_asym)
# and subtracted out before judging. The tolerance applies to the RESIDUAL
# after that correction; what remains is a close's adapt lagging a cycle,
# not bookkeeping. On 2026-08-13 ~30 closes' summed entry fees (-7.38)
# tripped a false DRIFT, which is why the correction is explicit.
DEFAULT_TOLERANCE_USD = 5.0

_LONGING = ("buy", "cover")


def replay_realized(trades: Iterable[dict[str, Any]]) -> float:
    """Realized P&L for one run's trades, oldest first. Pure and total.

    ⚠️ THE TRAP THIS FUNCTION EXISTS TO AVOID. A naive replay keeps a
    signed `cost` and does `cost -= avg * closed` on every close. That is
    right for a long and WRONG for a short: a short's cost basis is
    NEGATIVE, so subtracting drives it further from zero instead of toward
    it, and every subsequent close prices off a corrupted average. It
    produced a lifetime figure of +116,756 on a run that actually made
    +13.19, and it does NOT announce itself — small runs look plausible.

    Tracking `avg` (always positive) and signed `qty` separately removes the
    sign question entirely. Validated against the platform's own stored
    `realized_pnl_usd` on all 71 historical flatten runs: 71/71 within two
    cents.
    """
    qty = 0.0          # signed: > 0 long, < 0 short
    avg = 0.0          # average entry price, ALWAYS positive
    realized = 0.0
    for t in trades:
        try:
            side = str(t["side"]).strip().lower()
            q = abs(float(t["quantity"]))
            px = float(t["price"])
            fee = float(t.get("fee_usd") or 0.0)
        except (KeyError, TypeError, ValueError):
            continue
        if q <= 0 or px <= 0:
            continue
        realized -= fee
        direction = 1 if side in _LONGING else -1
        # Closing leg: only when the trade opposes the open position.
        if qty and (qty > 0) != (direction > 0):
            closed = min(q, abs(qty))
            sign = 1.0 if qty > 0 else -1.0
            realized += (px - avg) * closed * sign
            qty += direction * closed
            q -= closed
        # Whatever remains opens or extends a position (a flip lands here).
        if q > 1e-12:
            gross = abs(qty) + q
            avg = (avg * abs(qty) + px * q) / gross
            qty += direction * q
    return realized


def entry_fees(trades: Iterable[dict[str, Any]]) -> float:
    """Cumulative ENTRY-side fees for one run's trades, oldest first.

    The adapt stream's `realized` nets EXIT-side fees only; the ledger
    replay charges both sides. The entry-side fees are therefore the exact
    expected ledger-vs-adapt delta, and this walks the legs with the same
    parsing, same skips, and same open/close split as `replay_realized` so
    the attribution can never diverge from the replay it corrects. A leg
    that both closes and flips prorates its single fee: only the opening
    portion is entry-side.
    """
    qty = 0.0          # signed: > 0 long, < 0 short
    total = 0.0
    for t in trades:
        try:
            side = str(t["side"]).strip().lower()
            q = abs(float(t["quantity"]))
            px = float(t["price"])
            fee = float(t.get("fee_usd") or 0.0)
        except (KeyError, TypeError, ValueError):
            continue
        if q <= 0 or px <= 0:
            continue
        leg_q = q
        direction = 1 if side in _LONGING else -1
        if qty and (qty > 0) != (direction > 0):
            closed = min(q, abs(qty))
            qty += direction * closed
            q -= closed
        if q > 1e-12:
            total += fee * (q / leg_q)
            qty += direction * q
    return total


def _rows(cursor, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    cursor.execute(sql, params)
    return [dict(r) for r in cursor.fetchall()]


def realized_by_day(since: str, *, conn=None,
                    tolerance_usd: float = DEFAULT_TOLERANCE_USD
                    ) -> list[dict[str, Any]]:
    """Per-UTC-day realized P&L by BOTH methods, with the delta.

    `since` is an ISO date/prefix, e.g. "2026-08-06". Returns one row per
    day: ledger (authoritative), adapt (the old runbook snippet), delta,
    fee_asym (the delta EXPECTED from adapt netting exit-side fees only),
    resid (delta - fee_asym), flatten count, and `agrees` — False when the
    residual exceeds tolerance, which is the alarm this module exists to
    raise. Judging the residual, not the raw delta, keeps the known fee
    asymmetry from crying wolf without hiding a real drift behind it.
    """
    close_after = conn is None
    if conn is None:
        from database import get_db_connection
        conn = get_db_connection()
    try:
        cursor = conn.cursor()
        trades = _rows(cursor,
                       "SELECT run_id, ts, payload FROM run_events "
                       "WHERE event_type = 'trade' AND run_id IN ("
                       "  SELECT DISTINCT run_id FROM run_events "
                       "  WHERE event_type = 'trade' AND ts >= ?) "
                       "ORDER BY run_id, seq", (since,))
        adapts = _rows(cursor,
                       "SELECT ts, payload FROM run_events "
                       "WHERE event_type = 'adapt' AND ts >= ?", (since,))
    finally:
        if close_after:
            conn.close()

    # Replay each run from INCEPTION — a window-scoped replay invents a
    # phantom opening leg for any position carried in, which is how an
    # earlier pass produced nonsense on runs that spanned midnight.
    per_run: dict[int, list[dict]] = defaultdict(list)
    for row in trades:
        try:
            payload = json.loads(row["payload"])
        except (ValueError, TypeError):
            continue
        payload["_ts"] = str(row["ts"])[:19]
        per_run[int(row["run_id"])].append(payload)

    ledger: dict[str, float] = defaultdict(float)
    efees: dict[str, float] = defaultdict(float)
    flattens: dict[str, int] = defaultdict(int)
    for legs in per_run.values():
        running = 0.0
        fee_running = 0.0
        for i in range(len(legs)):
            total = replay_realized(legs[: i + 1])
            fee_total = entry_fees(legs[: i + 1])
            day = legs[i]["_ts"][:10]
            if day >= since[:10]:
                ledger[day] += total - running
                efees[day] += fee_total - fee_running
                if "flatten" in str(legs[i].get("client_order_id") or ""):
                    flattens[day] += 1
            running = total
            fee_running = fee_total

    adapt_sum: dict[str, float] = defaultdict(float)
    for row in adapts:
        try:
            payload = json.loads(row["payload"])
        except (ValueError, TypeError):
            continue
        if payload.get("realized") is None:
            continue
        try:
            adapt_sum[str(row["ts"])[:10]] += float(payload["realized"])
        except (TypeError, ValueError):
            continue

    out = []
    for day in sorted(set(ledger) | set(adapt_sum)):
        led = round(ledger.get(day, 0.0), 2)
        ada = round(adapt_sum.get(day, 0.0), 2)
        # Expected delta from the fee asymmetry: the ledger charged the
        # day's entry-side fees, the adapt stream did not.
        asym = round(-efees.get(day, 0.0), 2)
        resid = round(led - ada - asym, 2)
        out.append({"day": day, "ledger": led, "adapt": ada,
                    "delta": round(led - ada, 2),
                    "fee_asym": asym, "resid": resid,
                    "flattens": flattens.get(day, 0),
                    "agrees": abs(resid) <= tolerance_usd})
    return out


def format_report(rows: list[dict[str, Any]]) -> str:
    lines = [f"{'day':12}{'ledger':>10}{'adapt':>10}{'delta':>9}"
             f"{'fee_asym':>10}{'resid':>9}{'flat':>6}  check",
             "-" * 74]
    for r in rows:
        mark = "ok" if r["agrees"] else "*** DRIFT ***"
        lines.append(f"{r['day']:12}{r['ledger']:>10.2f}{r['adapt']:>10.2f}"
                     f"{r['delta']:>9.2f}{r['fee_asym']:>10.2f}"
                     f"{r['resid']:>9.2f}{r['flattens']:>6}  {mark}")
    if rows:
        lines.append("-" * 74)
        lines.append(f"{'TOTAL':12}{sum(r['ledger'] for r in rows):>10.2f}"
                     f"{sum(r['adapt'] for r in rows):>10.2f}")
    lines.append("ledger = authoritative (validated 71/71 vs the platform's "
                 "own stored realized_pnl_usd)")
    lines.append("fee_asym = expected delta from adapt netting exit-side "
                 "fees only; resid = delta - fee_asym is what's judged")
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--since", required=True, help="ISO date, e.g. 2026-08-06")
    ap.add_argument("--tolerance", type=float, default=DEFAULT_TOLERANCE_USD)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    rows = realized_by_day(args.since, tolerance_usd=args.tolerance)
    print(json.dumps(rows, indent=1) if args.json else format_report(rows))
    return 0 if all(r["agrees"] for r in rows) else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
