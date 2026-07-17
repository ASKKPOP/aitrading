"""Live confluence calibration (Plan 06 A2).

Builds the confluence-count → realized hit-rate table from PRODUCTION
telemetry instead of backtests: every automated, executed buy is journaled in
automation_runs with its confluence vector; this module replays the signals
ledger (average-cost basis, same books as risk_engine.trade_stats) and
resolves each tagged buy with the next realizing sell in the same book.

Attribution rule (documented, deterministic): a tagged buy is resolved by the
FIRST sell that realizes P&L on its (agent, market, symbol, token) book after
the buy; all tagged buys pending on that book share that sell's win/loss sign.
This approximates the backtest's per-trade bucketing without full lot
matching.

Advisory only: the resulting per-bucket hit rate (with its Wilson 90% lower
bound) is attached to automation-run telemetry as `calibration_prior` and
served at GET /api/risk/calibration. It changes no execution behavior until
the pre-registered Phase-4 criteria are met.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Optional

from database import get_db_connection

logger = logging.getLogger(__name__)

MAX_REPLAY_SIGNALS = 20000
PRIOR_MIN_TRADES = 5           # below this a bucket is too thin to quote as a prior
_CACHE: dict[str, Any] = {"at": 0.0, "payload": None}
_CACHE_TTL_SECONDS = 600


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _confluence_tags(cursor) -> dict[int, int]:
    """signal_id → buy_confluence for executed automated buys."""
    cursor.execute(
        """SELECT signal_id, confluence_json FROM automation_runs
           WHERE executed = 1 AND signal_id IS NOT NULL AND confluence_json IS NOT NULL""")
    tags: dict[int, int] = {}
    for row in cursor.fetchall():
        try:
            telemetry = json.loads(row["confluence_json"])
            count = telemetry.get("confluence", {}).get("buy_confluence")
            if isinstance(count, int):
                tags[int(row["signal_id"])] = count
        except (TypeError, ValueError):
            continue
    return tags


def build_live_calibration(cursor=None) -> dict[str, Any]:
    """Replay the ledger and bucket resolved tagged buys by confluence count."""
    own = cursor is None
    if own:
        conn = get_db_connection()
        cursor = conn.cursor()
    try:
        tags = _confluence_tags(cursor)
        cursor.execute(
            """SELECT signal_id, agent_id, market, symbol, COALESCE(token_id, '') AS token_id,
                      side, entry_price, quantity, executed_at
               FROM signals
               WHERE executed_at IS NOT NULL AND side IN ('buy', 'sell')
                 AND entry_price IS NOT NULL AND quantity IS NOT NULL
               ORDER BY executed_at DESC, id DESC LIMIT ?""",
            (MAX_REPLAY_SIGNALS,))
        rows = list(reversed(cursor.fetchall()))
    finally:
        if own:
            conn.close()

    books: dict[tuple, dict[str, float]] = {}
    pending: dict[tuple, list[int]] = {}          # book key → tagged confluence counts
    buckets: dict[int, dict[str, int]] = {}

    for row in rows:
        key = (row["agent_id"], row["market"], row["symbol"], row["token_id"])
        price = float(row["entry_price"])
        qty = float(row["quantity"])
        if qty <= 0 or price <= 0:
            continue
        if row["side"] == "buy":
            book = books.setdefault(key, {"qty": 0.0, "avg": 0.0})
            new_qty = book["qty"] + qty
            book["avg"] = (book["qty"] * book["avg"] + qty * price) / new_qty
            book["qty"] = new_qty
            sig_id = row["signal_id"]
            if sig_id is not None and int(sig_id) in tags:
                pending.setdefault(key, []).append(tags[int(sig_id)])
        elif row["side"] == "sell":
            book = books.get(key)
            if not book or book["qty"] <= 0:
                continue
            closed = min(qty, book["qty"])
            pnl = (price - book["avg"]) * closed
            book["qty"] -= closed
            for count in pending.pop(key, []):
                bucket = buckets.setdefault(count, {"trades": 0, "wins": 0})
                bucket["trades"] += 1
                if pnl > 0:
                    bucket["wins"] += 1

    from backtest_strategy import wilson_lower_bound
    out_buckets: dict[str, dict[str, Any]] = {}
    total = 0
    for count in sorted(buckets):
        b = buckets[count]
        total += b["trades"]
        lb = wilson_lower_bound(b["wins"], b["trades"])
        out_buckets[str(count)] = {
            "trades": b["trades"],
            "wins": b["wins"],
            "hit_rate": round(b["wins"] / b["trades"], 4),
            "wilson_lb": round(lb, 4) if lb is not None else None,
        }
    return {
        "available": total > 0,
        "buckets": out_buckets,
        "total_resolved": total,
        "min_trades_for_prior": PRIOR_MIN_TRADES,
        "method": "next-sell attribution over average-cost books (live telemetry)",
        "generated_at": _now_iso(),
    }


def get_calibration(force_refresh: bool = False) -> dict[str, Any]:
    now = time.time()
    if not force_refresh and _CACHE["payload"] is not None and now - _CACHE["at"] < _CACHE_TTL_SECONDS:
        return _CACHE["payload"]
    payload = build_live_calibration()
    _CACHE["payload"] = payload
    _CACHE["at"] = now
    return payload


def calibration_prior(buy_confluence: Optional[int]) -> Optional[dict[str, Any]]:
    """Advisory prior for a decision at this confluence count, or None when
    the bucket is missing/too thin. Fail-soft."""
    if buy_confluence is None:
        return None
    try:
        payload = get_calibration()
        bucket = payload["buckets"].get(str(int(buy_confluence)))
        if not bucket or bucket["trades"] < PRIOR_MIN_TRADES:
            return None
        return {"confluence": int(buy_confluence), "hit_rate": bucket["hit_rate"],
                "wilson_lb": bucket["wilson_lb"], "trades": bucket["trades"]}
    except Exception:  # noqa: BLE001
        return None
