"""Breakeven-ratchet fire audit — is the #251 anchor actually holding?

WHY THIS EXISTS. PR #251 anchored the breakeven floor's arm threshold to the
LARGEST book a run has ever held, because sizing it off the CURRENT book let
a desk's own `reduce` lower the bar under an already-earned lifetime peak and
instant-fire the floor — escalating a deliberate partial exit into the full
close the desk had just declined (runs 976 and 973, 2026-08-06).

The fix was verified 3x at ship against 976's exact death inputs. But the
FORWARD evidence was n=0: no live fire had yet exercised the new anchor, and
proving it depended on a human remembering to hand-audit every future
`trailing_lock` — the same "watch it manually" arrangement that let the
original defect run for two runs before anyone noticed.

So the watch becomes a tool. For every ratchet fire this replays the run's
own trade events and asks one question: **was the book at the moment of the
fire smaller than the largest book that run ever held?** That is the
retro-arm signature. Post-fix it must never appear again — so a fire with
that shape after the fix timestamp is a REGRESSION and this module exits
non-zero, exactly as `pnl_audit` does on ledger drift.

It reads nothing but `run_events`, computes nothing but arithmetic, and
NEVER writes. Deliberately independent of run_engine: a checker that imports
the thing it checks cannot catch a change in that thing's behaviour.

⚠️ PRECISION LIMIT, stated because the first draft overclaimed. The reason
string `stop_event:trailing_lock` is SHARED by the breakeven ratchet and the
LEGACY trailing lock, and only the ratchet can retro-arm — the legacy trail's
`trail.activate_usd` is a fixed dollar figure written into stop_conditions at
build, so shrinking the book cannot lower its bar. A shrunken-book legacy
fire is therefore perfectly normal (the desk banked some before the trail
caught the rest), and live data shows exactly that: 4 of 8 historical fires
carry the shape, but only the two ratchet-era ones (973, 976) are the defect.
So this module FLAGS FOR REVIEW rather than declaring a regression, and names
the disambiguating step: the worker log line `breakeven ratchet fired`.
"""

from __future__ import annotations

import argparse
import json
from typing import Any, Iterable, Optional

# Sides that build a LONG book; everything else builds a short. Same
# convention as pnl_audit.replay_realized — keep them in step.
_LONGING = ("buy", "cover")

# When #251 (max-book arm anchor) reached prod. Fires at or after this are
# held to the post-fix standard.
FIX_TS = "2026-08-06T06:40"

# Relative slack when comparing book sizes: float replay noise must not be
# read as a reduce.
_SHRINK_EPS = 1e-6


def _is_flatten(trade: dict[str, Any]) -> bool:
    """The forced liquidation the fire itself causes.

    ⚠️ THE TRAP THIS EXISTS TO AVOID (caught by running the first draft
    against live prod). The flatten leg is journalled with the SAME
    timestamp as the fire, so a naive `ts <= fire_ts` snapshot counts the
    liquidation as part of the book that preceded it and every fire reads
    as a flat book — i.e. "shrunken". The first draft scored 15 of 16
    historical fires that way, which post-fix would have made the FIRST
    genuine full-book fire an instant false REGRESSION alarm.
    """
    return "flatten" in str(trade.get("client_order_id") or "").lower()


def book_sizes(trades: Iterable[dict[str, Any]], until_ts: Optional[str] = None
               ) -> tuple[float, float]:
    """(largest abs book ever held, abs book immediately BEFORE `until_ts`).

    `until_ts` is compared against each trade's ISO `ts` string; trades at or
    before it count toward the second figure, EXCEPT the fire's own flatten
    leg (see _is_flatten). Both figures come from the same single pass, so
    they cannot disagree about what a trade meant.
    """
    qty = 0.0
    peak_qty = 0.0
    at_ts = 0.0
    for t in trades:
        try:
            side = str(t["side"]).strip().lower()
            q = abs(float(t["quantity"]))
        except (KeyError, TypeError, ValueError):
            continue
        if q <= 0:
            continue
        direction = 1 if side in _LONGING else -1
        if qty and (qty > 0) != (direction > 0):
            closed = min(q, abs(qty))
            qty += direction * closed
            q -= closed
        if q > 1e-12:
            qty += direction * q
        peak_qty = max(peak_qty, abs(qty))
        if (until_ts is None or str(t.get("ts") or "") <= until_ts) \
                and not _is_flatten(t):
            at_ts = abs(qty)
    return peak_qty, at_ts


def _rows(cursor, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    cursor.execute(sql, params)
    return [dict(r) for r in cursor.fetchall()]


def audit_fires(since: str, *, conn=None, fix_ts: str = FIX_TS
                ) -> list[dict[str, Any]]:
    """One row per breakeven/trailing-lock fire at or after `since`.

    Each row carries the run, the fire timestamp, the largest book the run
    ever held, the book at the fire, the verdict (`full-book` or
    `shrunken`), and `needs_review` — True only for a shrunken-book fire
    after the fix went live. That is a CANDIDATE retro-arm, not a proven
    one (see the precision limit in the module docstring): confirm against
    the `breakeven ratchet fired` log line before calling it a regression.
    """
    from database import get_db_connection
    own = conn is None
    conn = conn or get_db_connection()
    try:
        cursor = conn.cursor()
        # A stop emits TWO run_status rows (running->stopping, then
        # stopping->stopped) and both mention "stopping". Match only the
        # transition INTO stopping, or every fire is counted twice.
        fires = _rows(cursor,
                      "SELECT run_id, ts FROM run_events "
                      "WHERE event_type = 'run_status' AND ts >= ? "
                      "AND payload LIKE ? AND payload LIKE ? "
                      "ORDER BY ts",
                      (since, "%trailing_lock%", '%"to": "stopping"%'))
        out: list[dict[str, Any]] = []
        for f in fires:
            trades = _rows(cursor,
                           "SELECT ts, payload FROM run_events WHERE "
                           "run_id = ? AND event_type = 'trade' ORDER BY seq",
                           (f["run_id"],))
            parsed = []
            for t in trades:
                try:
                    p = json.loads(t["payload"])
                except (ValueError, TypeError):
                    continue
                p["ts"] = t["ts"]
                parsed.append(p)
            peak_qty, at_fire = book_sizes(parsed, until_ts=f["ts"])
            shrunken = at_fire < peak_qty * (1.0 - _SHRINK_EPS)
            out.append({
                "run_id": f["run_id"],
                "fired_at": f["ts"],
                "max_book": peak_qty,
                "book_at_fire": at_fire,
                "verdict": "shrunken" if shrunken else "full-book",
                "post_fix": str(f["ts"]) >= fix_ts,
                "needs_review": bool(shrunken and str(f["ts"]) >= fix_ts),
            })
        return out
    finally:
        if own:
            conn.close()


def format_report(rows: list[dict[str, Any]]) -> str:
    head = (f"{'run':>6}  {'fired':<20} {'max book':>12} {'at fire':>12}  "
            f"{'verdict':<10} {'era':<9}")
    lines = [head, "-" * len(head)]
    for r in rows:
        lines.append(
            f"{r['run_id']:>6}  {str(r['fired_at'])[:19]:<20} "
            f"{r['max_book']:>12.6f} {r['book_at_fire']:>12.6f}  "
            f"{r['verdict']:<10} "
            f"{'post-fix' if r['post_fix'] else 'pre-fix':<9}"
            + ("  *** REVIEW ***" if r["needs_review"] else ""))
    lines.append("-" * len(head))
    regs = sum(1 for r in rows if r["needs_review"])
    post = sum(1 for r in rows if r["post_fix"])
    lines.append(f"{len(rows)} fire(s); {post} post-fix; {regs} to review")
    if not post:
        lines.append("post-fix sample is EMPTY — the anchor is untested live.")
    elif not regs:
        lines.append("every post-fix fire was on a full book — anchor holding.")
    else:
        lines.append("REVIEW: a shrunken book post-fix is a CANDIDATE "
                     "retro-arm, not proof — the legacy trail shares this "
                     "reason string and cannot retro-arm. Confirm against "
                     "the worker log line 'breakeven ratchet fired'.")
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--since", default="2026-08-01")
    ap.add_argument("--fix-ts", default=FIX_TS)
    args = ap.parse_args(argv)
    rows = audit_fires(args.since, fix_ts=args.fix_ts)
    print(format_report(rows))
    return 1 if any(r["needs_review"] for r in rows) else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
