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

# When the breakeven ratchet itself (#249) merged to main. Before this the
# rail DID NOT EXIST, so asking "would the anchor have changed the outcome?"
# of an earlier reduce is anachronistic — the first live table answered it
# for eight 08-01/08-02 reduces that no ratchet could ever have judged.
# Deploy was necessarily later than the merge, so this is inclusive; it only
# matters for context rows, never for the post-FIX_TS evidence.
RATCHET_TS = "2026-08-06T01:45"

# A fire is journalled in the same second as the reduce that provoked it, or
# in the NEXT one — run 976 reduced at 05:40:01 and was flattened at
# 05:40:02. Matching on an exact-second equality read 976 as "survived",
# i.e. the tool got the single cell whose answer is known EXACTLY BACKWARDS.
_FIRE_WINDOW_S = 90


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


def reduce_steps(trades: Iterable[dict[str, Any]]
                 ) -> list[dict[str, Any]]:
    """Every trade that SHRANK the book without flattening it.

    Yields `{ts, price, max_book_before, book_after}` per reduce — the four
    numbers the arm arithmetic needs. A leg that closes the position outright
    is not a reduce (nothing is left for an arm to sit under), and neither is
    the forced flatten a fire causes.
    """
    qty = 0.0
    peak_qty = 0.0
    out: list[dict[str, Any]] = []
    for t in trades:
        try:
            side = str(t["side"]).strip().lower()
            q = abs(float(t["quantity"]))
        except (KeyError, TypeError, ValueError):
            continue
        if q <= 0:
            continue
        before = abs(qty)
        direction = 1 if side in _LONGING else -1
        opposing = bool(qty) and (qty > 0) != (direction > 0)
        if opposing:
            closed = min(q, abs(qty))
            qty += direction * closed
            q -= closed
        if q > 1e-12:
            qty += direction * q
        peak_qty = max(peak_qty, abs(qty))
        after = abs(qty)
        if opposing and not _is_flatten(t) \
                and after > 1e-12 and after < before * (1.0 - _SHRINK_EPS):
            try:
                price = float(t.get("price") or 0)
            except (TypeError, ValueError):
                price = 0.0
            out.append({"ts": t.get("ts"), "price": price,
                        "max_book_before": peak_qty, "book_after": after})
    return out


def _arm_usd(qty: float, mark: float) -> float:
    """The breakeven floor's arm threshold for a book of `qty` at `mark`.

    ⚠️ DELIBERATE DUPLICATION of run_engine._breakeven_arm_usd, for the same
    reason this whole module avoids importing run_engine: a checker that
    calls the thing it checks cannot notice that thing changing. Same env
    knobs, same defaults — if they ever drift apart the exposure table goes
    wrong, so keep them in step.
    """
    import os
    if qty <= 0 or mark <= 0:
        return 0.0
    rate = float(os.getenv("BREAKEVEN_FEE_RATE", "0.001"))
    mult = float(os.getenv("BREAKEVEN_ARM_FEES", "1.0"))
    return qty * mark * rate * 2.0 * max(0.0, mult)


def classify_exposure(peak_pnl: "float | None", step: dict[str, Any]
                      ) -> dict[str, Any]:
    """Would the OLD anchor have retro-armed on this reduce, where the new
    one does not?

    That is true in exactly one band: the run's lifetime peak clears the arm
    computed on the SHRUNKEN book but not the arm computed on the LARGEST
    book it ever held. Below the band neither anchor arms; above it both do,
    and the fix changes nothing. Run 976 landed inside it (arm-after 5.68 ≤
    peak 7.22 < arm-full 11.36) and died; run 977's peak of 21.08 cleared
    both arms, so it proves nothing either way — which is precisely the
    distinction this function exists to stop a reader from fudging.
    """
    mark = float(step.get("price") or 0)
    arm_full = _arm_usd(float(step.get("max_book_before") or 0), mark)
    arm_after = _arm_usd(float(step.get("book_after") or 0), mark)
    peak = float(peak_pnl or 0)
    return {
        "arm_full": arm_full,
        "arm_after": arm_after,
        "peak": peak,
        "in_band": bool(arm_after > 0 and arm_after <= peak < arm_full),
    }


def _within(reduce_ts: str, fire_ts: str) -> bool:
    """Did `fire_ts` land in the escalation window just after `reduce_ts`?

    Second-resolution ISO strings, compared as seconds since midnight with a
    day-boundary guard. A fire BEFORE the reduce is never a match.
    """
    def _secs(s: str) -> "int | None":
        t = str(s)[:19].replace(" ", "T")
        try:
            d, hms = t.split("T")
            h, m, sec = (int(x) for x in hms.split(":"))
            return (int(d.replace("-", "")), h * 3600 + m * 60 + sec)
        except (ValueError, TypeError):
            return None
    a, b = _secs(reduce_ts), _secs(fire_ts)
    if a is None or b is None or a[0] != b[0]:
        return False
    return 0 <= b[1] - a[1] <= _FIRE_WINDOW_S


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


def audit_exposures(since: str, *, conn=None, fix_ts: str = FIX_TS
                    ) -> list[dict[str, Any]]:
    """One row per IN-BAND reduce — the cases where the anchor actually
    decides something.

    WHY THIS EXISTS (cycle 78, 2026-08-06). `audit_fires` can only alarm on a
    bad fire. It is structurally blind to the fix WORKING: a post-fix sample
    of zero fires reads identically to "the rail never got a chance", which
    is exactly what it printed while run 976 — the textbook instance — sat
    one hour the wrong side of the boundary. Counting the reduces that landed
    in the discriminating band, and whether each was followed by a fire,
    turns an unobservable into an observable.

    ⚠️ `peak_pnl_usd` is read as it stands NOW, not as it stood at the
    reduce. It is a monotone high-water mark, so for a still-running run this
    can only OVERstate the peak, which can only push a case above the band.
    The count therefore under-reports and never invents.
    """
    from database import get_db_connection
    own = conn is None
    conn = conn or get_db_connection()
    try:
        cursor = conn.cursor()
        runs = _rows(cursor,
                     "SELECT DISTINCT run_id FROM run_events WHERE "
                     "event_type = 'trade' AND ts >= ? ORDER BY run_id",
                     (since,))
        out: list[dict[str, Any]] = []
        for r in runs:
            rid = r["run_id"]
            peaks = _rows(cursor,
                          "SELECT peak_pnl_usd FROM trading_runs WHERE id = ?",
                          (rid,))
            if not peaks:
                continue
            trades = _rows(cursor,
                           "SELECT ts, payload FROM run_events WHERE "
                           "run_id = ? AND event_type = 'trade' ORDER BY seq",
                           (rid,))
            parsed = []
            for t in trades:
                try:
                    p = json.loads(t["payload"])
                except (ValueError, TypeError):
                    continue
                p["ts"] = t["ts"]
                parsed.append(p)
            fires = [str(f["ts"]) for f in _rows(
                cursor,
                "SELECT ts FROM run_events WHERE event_type = 'run_status' "
                "AND run_id = ? AND payload LIKE ? AND payload LIKE ?",
                (rid, "%trailing_lock%", '%"to": "stopping"%'))]
            for step in reduce_steps(parsed):
                ts = str(step.get("ts") or "")
                if ts < since or ts < RATCHET_TS:
                    continue
                cls = classify_exposure(peaks[0]["peak_pnl_usd"], step)
                if not cls["in_band"]:
                    continue
                out.append({
                    "run_id": rid,
                    "reduced_at": step["ts"],
                    "post_fix": ts >= fix_ts,
                    "fired": any(_within(ts, f) for f in fires),
                    **cls,
                })
        return out
    finally:
        if own:
            conn.close()


def format_exposures(rows: list[dict[str, Any]]) -> str:
    head = (f"{'run':>6}  {'reduced':<20} {'arm after':>10} {'peak':>8} "
            f"{'arm full':>9}  {'era':<9} {'outcome'}")
    lines = ["", "IN-BAND REDUCES — where the anchor decides the outcome",
             head, "-" * len(head)]
    for r in rows:
        # 4dp, not 2: a book reduced to a sliver has an arm of $0.004, and
        # printing that as "0.00" made the band read as trivially satisfied.
        lines.append(
            f"{r['run_id']:>6}  {str(r['reduced_at'])[:19]:<20} "
            f"{r['arm_after']:>10.4f} {r['peak']:>8.2f} {r['arm_full']:>9.4f}  "
            f"{'post-fix' if r['post_fix'] else 'pre-fix':<9} "
            + ("FLATTENED" if r["fired"] else "survived"))
    lines.append("-" * len(head))
    held = [r for r in rows if r["post_fix"] and not r["fired"]]
    lost = [r for r in rows if r["post_fix"] and r["fired"]]
    if not rows:
        lines.append("no reduce landed in the band — the anchor has not yet "
                     "been asked a question it could get wrong.")
    else:
        lines.append(f"{len(rows)} in-band reduce(s); post-fix "
                     f"{len(held)} survived, {len(lost)} flattened.")
    return "\n".join(lines)


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
    print(format_exposures(audit_exposures(args.since, fix_ts=args.fix_ts)))
    return 1 if any(r["needs_review"] for r in rows) else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
