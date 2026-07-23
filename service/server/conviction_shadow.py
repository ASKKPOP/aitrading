"""Plan 15 rec-1 — the P3 flip test, computed instead of eyeballed.

Joins each run's executed legs back to the decision events that opened them
(trade events carry client_order_id "run:{id}:cyc:{seq}" → the cycle's
decision holds confidence, conviction, scores) and cuts the leg stream into
EPISODES (flat → flat). Per episode: realized P&L (fees included, same leg
math as compute_run_pnl) and the open-notional-weighted mean of the scalar
confidence and the computed conviction.

The flip question is then mechanical: across closed episodes, which metric
ranks winners above losers more often (pairwise rank agreement — a small-N
AUC)? Run inside the worker container:

    python -c "import conviction_shadow, json; \
               print(json.dumps(conviction_shadow.shadow_report(), indent=2))"
"""

from __future__ import annotations

import json
from typing import Any, Optional

from database import get_db_connection


def build_episodes(legs: list[dict], cycle_metrics: dict[int, dict]) -> list[dict]:
    """Pure episode cutter. legs: ordered [{side, quantity, entry_price,
    fee_usd, cycle}] (cycle None for flattens). cycle_metrics: {cycle:
    {confidence, conviction}}. Returns closed episodes only."""
    episodes: list[dict] = []
    qty = 0.0
    avg = 0.0
    realized = 0.0
    ep_start_realized = 0.0
    opens: list[dict] = []
    in_episode = False
    for leg in legs:
        side = leg["side"]
        p = float(leg["entry_price"] or 0)
        q = float(leg["quantity"] or 0)
        fee = float(leg["fee_usd"] or 0)
        if side in ("buy", "short") and not in_episode:
            in_episode = True
            ep_start_realized = realized
            opens = []
        if side == "buy":
            avg = (avg * qty + p * q) / (qty + q) if qty + q > 0 else p
            qty += q
            realized -= fee
            opens.append({"cycle": leg.get("cycle"), "notional": p * q})
        elif side == "sell":
            realized += (p - avg) * min(q, qty) - fee
            qty -= min(q, qty)
        elif side == "short":
            held = -qty
            avg = (avg * held + p * q) / (held + q) if held + q > 0 else p
            qty -= q
            realized -= fee
            opens.append({"cycle": leg.get("cycle"), "notional": p * q})
        elif side == "cover":
            held = -qty
            realized += (avg - p) * min(q, held) - fee
            qty += min(q, held)
        if in_episode and abs(qty) < 1e-12:
            in_episode = False
            metrics = {"confidence": None, "conviction": None}
            wsum = 0.0
            csum = 0.0
            cvsum = 0.0
            cv_ok = True
            for o in opens:
                m = cycle_metrics.get(o["cycle"]) if o["cycle"] is not None else None
                if not m or m.get("confidence") is None:
                    continue
                w = float(o["notional"] or 0)
                wsum += w
                csum += w * float(m["confidence"])
                if m.get("conviction") is None:
                    cv_ok = False
                else:
                    cvsum += w * float(m["conviction"])
            if wsum > 0:
                metrics["confidence"] = round(csum / wsum, 4)
                if cv_ok:
                    metrics["conviction"] = round(cvsum / wsum, 4)
            episodes.append({
                "pnl": round(realized - ep_start_realized, 6),
                "opens": len(opens),
                **metrics,
            })
            avg = 0.0
    return episodes


def _rank_agreement(episodes: list[dict], key: str) -> Optional[float]:
    """Fraction of (winner, loser) pairs the metric orders correctly —
    ties count half. None when either class is empty or metric missing."""
    wins = [e[key] for e in episodes if e["pnl"] > 0 and e.get(key) is not None]
    losses = [e[key] for e in episodes if e["pnl"] <= 0 and e.get(key) is not None]
    if not wins or not losses:
        return None
    good = 0.0
    for w in wins:
        for lo in losses:
            if w > lo:
                good += 1.0
            elif w == lo:
                good += 0.5
    return round(good / (len(wins) * len(losses)), 4)


def _cycle_from_coid(coid: Optional[str]) -> Optional[int]:
    """Parse the cycle out of a signals.client_order_id ('run:{id}:cyc:{seq}';
    'run:{id}:flatten' and other close forms carry no cycle → None)."""
    coid = str(coid or "")
    if ":cyc:" not in coid:
        return None
    try:
        return int(coid.rsplit(":", 1)[1])
    except (ValueError, TypeError):
        return None


def _run_episodes(cursor, run_id: int) -> list[dict]:
    # The signals row carries client_order_id directly — read the cycle from
    # it, NOT via the trade-event signal_id (that id is a separate counter
    # and does not equal signals.id; joining on it silently dropped every
    # open's metrics — caught on fleet 9, 2026-07-23).
    cursor.execute(
        """SELECT side, quantity, entry_price, fee_usd, client_order_id
           FROM signals
           WHERE run_id = ? AND message_type = 'operation' ORDER BY id""",
        (run_id,))
    sig_rows = [dict(r) for r in cursor.fetchall()]
    cursor.execute(
        """SELECT payload FROM run_events
           WHERE run_id = ? AND event_type = 'decision' ORDER BY id""", (run_id,))
    cycle_metrics: dict[int, dict] = {}
    for row in cursor.fetchall():
        try:
            obj = json.loads(row["payload"] or "{}")
            cycle_metrics[int(obj.get("cycle"))] = {
                "confidence": obj.get("confidence"),
                "conviction": obj.get("conviction"),
            }
        except (ValueError, TypeError):
            continue
    legs = [{"side": s["side"], "quantity": s["quantity"],
             "entry_price": s["entry_price"], "fee_usd": s["fee_usd"],
             "cycle": _cycle_from_coid(s["client_order_id"])} for s in sig_rows]
    eps = build_episodes(legs, cycle_metrics)
    for e in eps:
        e["run_id"] = run_id
    return eps


def shadow_report(min_run_id: int = 44) -> dict[str, Any]:
    """Episodes + rank agreement across every run since the conviction
    shadow went live (default: fleet-8 onward, 2026-07-22)."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM trading_runs WHERE id >= ? ORDER BY id",
                       (min_run_id,))
        run_ids = [int(r["id"]) for r in cursor.fetchall()]
        episodes: list[dict] = []
        for rid in run_ids:
            episodes.extend(_run_episodes(cursor, rid))
    finally:
        conn.close()
    # churn flattens carry no outcome signal: drop |pnl| < $0.50 episodes
    informative = [e for e in episodes if abs(e["pnl"]) >= 0.50]
    wins = sum(1 for e in informative if e["pnl"] > 0)
    return {
        "episodes_total": len(episodes),
        "episodes_informative": len(informative),
        "wins": wins,
        "losses": len(informative) - wins,
        "rank_agreement_confidence": _rank_agreement(informative, "confidence"),
        "rank_agreement_conviction": _rank_agreement(informative, "conviction"),
        "flip_ready": len(informative) >= 20,
        "episodes": informative,
    }
