"""What this desk's own ledger says — measured facts it cannot currently see.

WHY THIS EXISTS (measured on prod 2026-08-24, ten-agent loss analysis).

The desk repeats losing decisions because nothing in its prompt contains its
own outcomes. Four measurements from the week of 2026-08-18, each of which the
desk produced and none of which it was ever shown:

  * SAME SETUP, TWICE. LINK#2 re-shorted LINK 5h23m after LINK#1 lost $4.11,
    at 2.00x the size, on the identical daily-RSI thesis. FIL#2 re-shorted FIL
    23h after FIL#1 lost $5.44, at 2.17x size. Both re-entries lost. There is
    no channel that tells the desk "this exact thesis just cost me $4 on this
    exact symbol" — `_recall_line` is gated behind a held position and the
    flat-cycle path is default-OFF, so 98.6% of cycles get nothing.

  * ONE MECHANISM CLOSED ALMOST EVERYTHING, AND IT NEVER WON. The breakeven
    ratchet fired 8 times in the window for 8 losses and 0 wins (net -$3.17,
    of which $2.26 was fees). Peaks it surrendered: +$1.90 -> -$0.14,
    +$1.78 -> -$0.34, +$1.01 -> +$0.08. The desk authors brackets with no
    knowledge that a rail is closing its book at ~breakeven-minus-a-fee.

  * HOLD TIME SEPARATED WINNERS FROM LOSERS AND NOTHING ELSE DID. Trips held
    <35 min: 0 wins of 8. Trips held >=35 min: 5 of 8, +$4.11. This was the
    only factor whose sign survived stripping the largest contributor on BOTH
    sides. The desk's own conviction score carried zero information (winners
    0.675 vs losers 0.670).

  * IT SHORTED A MELT-UP THIRTEEN TIMES OUT OF SIXTEEN. Every symbol the
    platform slotted rose 3.8-36.7% that week (BTC +22.6%, trend efficiency
    0.91 — the most one-way tape in five weeks). Its sell proposals resolved
    favourably 19% of the time (n=84, z=-5.67); taking them all returned
    -$164 and fading them +$178. Its buy proposals were a coin flip. The desk
    is never shown which direction its own calls have paid in.

  * THE EXITS WERE THE ONLY COMPONENT ADDING VALUE — a correction to an
    earlier reading of this same week. Replayed at their own authored
    brackets, the 16 entries resolve to -$37.24 against an actual -$9.01:
    2 of 16 ever touched target, 11 hit their own stop. The rails did not
    author the loss; the entry direction did, and a stop at ~0.35 sigma
    amplified it. This module therefore reports exit machinery as FACT and
    explicitly says so, rather than inviting the desk to blame the rails.

  * THE FLAT BOOK IS NEVER SHOWN A FEE. `_net_of_fees_line` returns "" when
    `pos_qty` is 0, so a desk considering an ENTRY sees no fee number at all,
    while fees ate 86% of the gross edge on the week's 14 non-blowup trips and
    flipped two gross winners into net losers.

This module states those facts and clamps NOTHING. Which trade to take stays
the desk's call (`trading-decisions-belong-to-sooppiy-ai`); the platform's job
is to stop hiding the desk's own record from it.

LEDGER, NOT MODEL — load-bearing. `fees.fee_rate(market)` is a per-market
CONSTANT behind a flag, not what was charged. This module reads the fee that
was actually booked on `run_events.trade[].fee`, because a desk shown a
constant and told it is a measurement has been misled, not informed. The two
disagreed by 12x in the standing narrative until 2026-08-24.

DELIBERATELY NOT INCLUDED: any threshold, veto, or "you should not" sentence.
`desk_record.py`'s history is the cautionary tale — a measured line shipped
into both prompts and was later measured to be actively harmful in crypto
(+$145 of suppressed entries over 8 days), and had to grow a hardcoded market
exclusion. Facts age better than instructions.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Optional

from database import get_db_connection

logger = logging.getLogger(__name__)

# A record built on a handful of runs is noise wearing a decimal point.
# Per-symbol history is thin by nature, so its floor is lower than the
# market-wide floors — but it is never zero.
_MIN_N_SYMBOL = 2
_MIN_N_MARKET = 6
# These move only when a run CLOSES, so a stale answer is a correct answer.
_TTL_SEC = 900
# Bound every scan. The desk's recent book is the relevant one.
_MAX_RUNS = 300
# Beyond this the record is history, not a lesson about today's tape.
_LOOKBACK_DAYS = 14

_CACHE: dict[str, tuple[float, Any]] = {}


def _cached(key: str, fn):
    """TTL cache with fail-soft semantics: a missing record costs the prompt
    one sentence, a raising one would cost the cycle."""
    try:
        hit = _CACHE.get(key)
        if hit and (time.time() - hit[0]) < _TTL_SEC:
            return hit[1]
        val = fn()
        _CACHE[key] = (time.time(), val)
        return val
    except Exception as exc:  # noqa: BLE001
        logger.warning("desk reference unavailable (%s): %s", key, exc)
        return None


def _median(values: list[float]) -> float:
    s = sorted(values)
    n = len(s)
    if not n:
        return 0.0
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2.0


def _closed_trips(market: str) -> list[dict]:
    """Replay every closed run's trade legs into one row per run.

    Reads the LEDGER: side/qty/price/fee come off `run_events.trade`
    payloads, realized P&L off `trading_runs`. Notional is the peak
    concurrent exposure (the R30 denominator), never the sum of opening
    legs, which shrinks with re-entry churn."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, symbol, realized_pnl_usd, peak_pnl_usd, stopped_at "
            "FROM trading_runs WHERE status = 'stopped' AND market = ? "
            "ORDER BY id DESC LIMIT ?", (market, _MAX_RUNS))
        runs = {}
        for r in cur.fetchall():
            runs[int(r["id"])] = {
                "run_id": int(r["id"]),
                "symbol": str(r["symbol"] or ""),
                "net": float(r["realized_pnl_usd"] or 0.0),
                "peak": (None if r["peak_pnl_usd"] is None
                         else float(r["peak_pnl_usd"])),
                "stopped_at": str(r["stopped_at"] or ""),
                "side": None, "fees": 0.0, "notional": 0.0,
                "first_ts": None, "last_ts": None, "legs": 0,
            }
        if not runs:
            return []
        ids = ",".join("?" for _ in runs)
        cur.execute(
            f"SELECT run_id, ts, payload FROM run_events "
            f"WHERE event_type = 'trade' AND run_id IN ({ids}) "
            f"ORDER BY run_id, id", tuple(runs))
        qty_net: dict[int, float] = {}
        for row in cur.fetchall():
            try:
                p = json.loads(row["payload"] or "{}")
                side = p.get("side")
                if side not in ("buy", "short", "sell", "cover"):
                    continue
                rid = int(row["run_id"])
                rec = runs.get(rid)
                if rec is None:
                    continue
                qty = abs(float(p["quantity"]))
                price = float(p["price"])
                rec["fees"] += abs(float(p.get("fee") or 0.0))
                rec["legs"] += 1
                if rec["side"] is None and side in ("buy", "short"):
                    rec["side"] = "long" if side == "buy" else "short"
                ts = str(row["ts"] or "")
                if rec["first_ts"] is None:
                    rec["first_ts"] = ts
                rec["last_ts"] = ts
                qty_net[rid] = qty_net.get(rid, 0.0) + (
                    qty if side in ("buy", "cover") else -qty)
                rec["notional"] = max(rec["notional"],
                                      abs(qty_net[rid]) * price)
            except (TypeError, ValueError, KeyError):
                continue
    finally:
        conn.close()
    return [r for r in runs.values() if r["legs"] > 0 and r["notional"] > 0]


def _age_days(ts: str) -> float:
    """Cheap ISO-ish age. Returns +inf when unparseable so a bad timestamp
    excludes the row rather than silently counting as fresh."""
    from datetime import datetime, timezone
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S"):
        try:
            then = datetime.strptime(ts, fmt).replace(tzinfo=timezone.utc)
            return (datetime.now(timezone.utc) - then).total_seconds() / 86400.0
        except (TypeError, ValueError):
            continue
    return float("inf")


def _hold_minutes(rec: dict) -> Optional[float]:
    if not rec.get("first_ts") or not rec.get("last_ts"):
        return None
    a, b = _age_days(rec["first_ts"]), _age_days(rec["last_ts"])
    if a == float("inf") or b == float("inf"):
        return None
    return max(0.0, (a - b) * 1440.0)


# ── the registry ───────────────────────────────────────────────────────────

def symbol_side_record(symbol: str, market: str,
                       side: str) -> Optional[dict[str, Any]]:
    """This desk's own closed record on THIS symbol in THIS direction.

    The gap it closes is concrete: two same-symbol re-entries after a loss in
    one week, both at ~2x the size, both losing, with nothing in the prompt
    naming the prior outcome."""
    sym = (symbol or "").strip().upper()
    want = (side or "").strip().lower()
    if not sym or want not in ("long", "short"):
        return None

    def _fn():
        trips = [t for t in _closed_trips(market)
                 if t["symbol"].upper() == sym and t["side"] == want
                 and _age_days(t["stopped_at"]) <= _LOOKBACK_DAYS]
        if len(trips) < _MIN_N_SYMBOL:
            return None
        trips.sort(key=lambda t: _age_days(t["stopped_at"]))
        nets = [t["net"] for t in trips]
        return {
            "symbol": sym, "market": market, "side": want,
            "n": len(trips),
            "wins": sum(1 for v in nets if v > 0),
            "net": sum(nets),
            "last_net": trips[0]["net"],
            "last_age_h": _age_days(trips[0]["stopped_at"]) * 24.0,
        }

    return _cached(f"sym:{market}:{sym}:{want}", _fn)


def direction_record(market: str) -> Optional[dict[str, Any]]:
    """This desk's closed record split by DIRECTION.

    The week of 2026-08-18 is why this exists: the desk was short in 13 of 16
    round trips through a tape where every symbol it slotted rose 3.8-36.7%,
    and its sell proposals resolved favourably 19% of the time (n=84,
    z=-5.67) while its buy proposals were a coin flip. Taking every sell
    proposal returned -$164; fading them returned +$178. Nothing in the
    prompt tells the desk which direction its own calls have paid in."""

    def _fn():
        trips = [t for t in _closed_trips(market)
                 if _age_days(t["stopped_at"]) <= _LOOKBACK_DAYS
                 and t["side"] in ("long", "short")]
        if len(trips) < _MIN_N_MARKET:
            return None
        out = {}
        for want in ("long", "short"):
            nets = [t["net"] for t in trips if t["side"] == want]
            if nets:
                out[want] = {"n": len(nets), "net": sum(nets),
                             "wins": sum(1 for v in nets if v > 0)}
        if len(out) < 2:
            return None
        return {"market": market, "n": len(trips), "by_side": out}

    return _cached(f"dir:{market}", _fn)


def exit_author_record(market: str) -> Optional[dict[str, Any]]:
    """Which machinery actually closes this desk's books, and what it earns.

    The desk authors a bracket every cycle without knowing that a rail — not
    its bracket — resolves most positions."""

    def _fn():
        conn = get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT e.payload FROM run_events e "
                "JOIN trading_runs r ON r.id = e.run_id "
                "WHERE e.event_type = 'stop_mechanism' AND r.market = ? "
                "ORDER BY e.id DESC LIMIT ?", (market, _MAX_RUNS))
            rows = cur.fetchall()
        finally:
            conn.close()
        by: dict[str, list[tuple[float, float]]] = {}
        for row in rows:
            try:
                p = json.loads(row["payload"] or "{}")
                mech = str(p.get("mechanism") or p.get("reason") or "")
                if not mech:
                    continue
                by.setdefault(mech, []).append(
                    (float(p.get("total") or 0.0), float(p.get("peak") or 0.0)))
            except (TypeError, ValueError):
                continue
        out = []
        for mech, pairs in by.items():
            if len(pairs) < _MIN_N_MARKET:
                continue
            totals = [t for t, _ in pairs]
            # Give-back is only defined for fires that HAD a positive peak.
            gb = [(pk - t) / pk for t, pk in pairs if pk > 0]
            out.append({
                "mechanism": mech, "n": len(pairs),
                "positive": sum(1 for v in totals if v > 0),
                "median_total": _median(totals),
                "median_giveback": (_median(gb) if gb else None),
                "n_giveback": len(gb),
            })
        if not out:
            return None
        out.sort(key=lambda d: -d["n"])
        return {"market": market, "mechanisms": out}

    return _cached(f"exit:{market}", _fn)


def holding_period_record(market: str) -> Optional[dict[str, Any]]:
    """Net outcome split by how long the position was actually held.

    Measured 2026-08-24 as the only factor separating winners from losers
    whose sign survived stripping the largest contributor on both sides."""

    def _fn():
        trips = [t for t in _closed_trips(market)
                 if _age_days(t["stopped_at"]) <= _LOOKBACK_DAYS]
        rows = []
        for t in trips:
            m = _hold_minutes(t)
            if m is not None:
                rows.append((m, t["net"]))
        if len(rows) < _MIN_N_MARKET:
            return None
        short = [n for m, n in rows if m < 35.0]
        long_ = [n for m, n in rows if m >= 35.0]
        if not short or not long_:
            return None
        return {
            "market": market, "n": len(rows),
            "short_n": len(short), "short_net": sum(short),
            "short_wins": sum(1 for v in short if v > 0),
            "long_n": len(long_), "long_net": sum(long_),
            "long_wins": sum(1 for v in long_ if v > 0),
            "median_hold_min": _median([m for m, _ in rows]),
        }

    return _cached(f"hold:{market}", _fn)


def fee_reality(market: str) -> Optional[dict[str, Any]]:
    """The round-trip cost this desk has ACTUALLY been charged, from the
    ledger — available on a flat book, which is 98.6% of cycles and the one
    place the existing fee line refuses to render."""

    def _fn():
        trips = [t for t in _closed_trips(market)
                 if _age_days(t["stopped_at"]) <= _LOOKBACK_DAYS
                 and t["notional"] > 0 and t["fees"] > 0]
        if len(trips) < _MIN_N_MARKET:
            return None
        rates = [t["fees"] / t["notional"] * 100.0 for t in trips]
        gross = sum(t["net"] + t["fees"] for t in trips)
        fees = sum(t["fees"] for t in trips)
        return {
            "market": market, "n": len(trips),
            "median_rt_pct": _median(rates),
            "gross": gross, "fees": fees, "net": sum(t["net"] for t in trips),
            "fee_share": (fees / abs(gross) if gross else None),
        }

    return _cached(f"fee:{market}", _fn)


# ── rendering ──────────────────────────────────────────────────────────────

def reference_block(symbol: str, market: str,
                    side: "str | None" = None) -> str:
    """One labelled paragraph of this desk's own ledger, or "".

    `side` is the direction under consideration; when absent the per-symbol
    half is skipped. Every half is independently optional — a thin record
    costs a sentence, never the block."""
    parts: list[str] = []

    if side:
        rec = symbol_side_record(symbol, market, side)
        if rec:
            parts.append(
                f"YOUR OWN RECORD ON {rec['symbol']} {rec['side'].upper()}: "
                f"{rec['n']} closed in the last {_LOOKBACK_DAYS}d, "
                f"{rec['wins']} profitable, net ${rec['net']:+.2f}. Most "
                f"recent closed ${rec['last_net']:+.2f} "
                f"{rec['last_age_h']:.1f}h ago.")

    dirs = direction_record(market)
    if dirs:
        bits = []
        for want in ("long", "short"):
            d = dirs["by_side"].get(want)
            if d:
                bits.append(f"{want} {d['wins']} profitable of {d['n']}, "
                            f"net ${d['net']:+.2f}")
        parts.append(f"YOUR DIRECTIONAL RECORD ({market}, last "
                     f"{_LOOKBACK_DAYS}d): " + "; ".join(bits) + ".")

    exits = exit_author_record(market)
    if exits:
        bits = []
        for m in exits["mechanisms"][:3]:
            gb = ("" if m["median_giveback"] is None
                  else f", median give-back {m['median_giveback'] * 100:.0f}% "
                       f"of peak (n={m['n_giveback']})")
            bits.append(f"{m['mechanism']} closed {m['n']} "
                        f"({m['positive']} at a profit), median result "
                        f"${m['median_total']:+.2f}{gb}")
        parts.append(
            "WHO CLOSES YOUR BOOK (" + market + "): " + "; ".join(bits)
            + ". Stated as fact, not fault: replayed on the week of "
            "2026-08-18, holding those same entries to the brackets you "
            "authored resolved WORSE than the rails did (-$37 vs -$9), so a "
            "rail closing your book early is not by itself evidence it cost "
            "you money.")

    hold = holding_period_record(market)
    if hold:
        parts.append(
            f"HOLD TIME vs OUTCOME ({market}, n={hold['n']} closed): held "
            f"under 35 min — {hold['short_wins']} profitable of "
            f"{hold['short_n']}, net ${hold['short_net']:+.2f}; held 35 min or "
            f"longer — {hold['long_wins']} of {hold['long_n']}, net "
            f"${hold['long_net']:+.2f}. Median hold "
            f"{hold['median_hold_min']:.0f} min.")

    fee = fee_reality(market)
    if fee:
        share = ("" if fee["fee_share"] is None
                 else f" Across those trips fees were "
                      f"{fee['fee_share'] * 100:.0f}% of gross P&L "
                      f"(gross ${fee['gross']:+.2f}, fees ${fee['fees']:.2f}, "
                      f"net ${fee['net']:+.2f}).")
        parts.append(
            f"FEE ACTUALLY CHARGED ({market}, ledger, n={fee['n']}): median "
            f"round trip {fee['median_rt_pct']:.3f}% of notional.{share} "
            f"A move smaller than that is a loss however the call goes.")

    if not parts:
        return ""
    return ("\n[YOUR LEDGER — measured from your own closed book, not a "
            "model. These are facts, not instructions; the trade is your "
            "call.]\n" + "\n".join(parts) + "\n")
