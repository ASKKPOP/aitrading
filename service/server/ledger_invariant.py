"""Plan 31 item 1 — row-level ledger invariant for exit fills.

The agent-6 pnl=0 incident (2026-08-26 reset; ``reset6_bak_signals`` holds
the true values) showed a zeroed ``signals.pnl`` can sit unnoticed while
every downstream reader (assets/trades views, desk_reference, adapt) takes
it at face value. This module recomputes each exit fill's expected P&L and
flags rows that disagree with what the ledger recorded.

An exit row CANNOT be checked from its own columns: the write path
(automation.py exit stamp; routes_signals.py mirrors it) stores the FILL
price in both ``entry_price`` and ``exit_price`` on closing legs, so the
book's average entry must be replayed from the run's own entry legs —
buys/shorts average in |qty|-weighted, sells/covers leave the average
untouched (services._update_position_from_signal). The recorded pnl nets
the EXIT leg's fee only, by convention:

    sell : (exit − avg_entry) × qty − fee_usd
    cover: (avg_entry − exit) × qty − fee_usd

Replay validated against 310 real prod exit fills across agents 5/6/59/60
(research/replan30 extraction): worst reconstruction delta 3.1e-7.

Fail-soft everywhere: an unverifiable row (book opened before signals
retention, missing prices) is skipped, never flagged.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

from database import get_db_connection

logger = logging.getLogger(__name__)

# A book within dust of flat IS flat (services.py lot-consolidation epsilon).
_QTY_EPS = 1e-8
# Absolute dollars of disagreement a row may carry before it violates.
_TOLERANCE = 0.05

_EXIT_SIDES = ("sell", "cover")
_FILL_SIDES = ("buy", "short", "sell", "cover")


def ledger_invariant_enabled() -> bool:
    return os.getenv("LEDGER_INVARIANT_ENABLED", "1").strip().lower() in (
        "1", "true", "yes", "on")


def check_exit_rows(hours: float | None = 24) -> list[dict]:
    """Recompute expected pnl for every exit fill in the window; return violations.

    ``hours=None`` checks all time. A row violates when
    |pnl − expected| > $0.05 (a zeroed pnl against a material expected value
    is the same test with pnl == 0). Books are keyed
    (agent_id, market, symbol, run_id) — the same key the positions table
    enforces — and replayed from the beginning of the signals table so a
    window exit sees its out-of-window entries. Polymarket is excluded:
    settlement writes don't follow the two-leg fee convention.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        exit_placeholders = ",".join("?" for _ in _EXIT_SIDES)

        # 1. The exits to verify (window applies here only).
        query = (
            "SELECT id, agent_id FROM signals "
            f"WHERE side IN ({exit_placeholders}) AND pnl IS NOT NULL "
            "AND market != 'polymarket'"
        )
        params: list[Any] = list(_EXIT_SIDES)
        if hours is not None:
            cutoff = int(datetime.now(timezone.utc).timestamp() - hours * 3600)
            query += " AND timestamp >= ?"
            params.append(cutoff)
        cursor.execute(query, params)
        target_rows = cursor.fetchall()
        target_ids = {int(r["id"]) for r in target_rows}
        if not target_ids:
            return []
        agent_ids = sorted({int(r["agent_id"]) for r in target_rows})

        # 2. Full fill history for the affected agents (replay needs the
        # entry legs, which predate the window).
        fill_placeholders = ",".join("?" for _ in _FILL_SIDES)
        agent_placeholders = ",".join("?" for _ in agent_ids)
        cursor.execute(
            "SELECT id, agent_id, market, symbol, side, entry_price, "
            "quantity, pnl, fee_usd, run_id FROM signals "
            f"WHERE agent_id IN ({agent_placeholders}) "
            f"AND side IN ({fill_placeholders}) "
            "AND quantity IS NOT NULL AND market != 'polymarket' "
            "ORDER BY id",
            [*agent_ids, *_FILL_SIDES],
        )
        fills = [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()

    violations: list[dict] = []
    skipped = 0
    # book key -> [signed qty, avg entry]
    books: dict[tuple, list[float]] = {}
    for row in fills:
        expected = _replay_fill(books, row)
        if int(row["id"]) not in target_ids:
            continue
        if expected is None:
            skipped += 1
            continue
        pnl = float(row["pnl"])
        if abs(pnl - expected) > _TOLERANCE:
            violations.append({
                "signal_id": int(row["id"]),  # signals.id primary key
                "agent_id": int(row["agent_id"]),
                "run_id": int(row["run_id"]) if row["run_id"] is not None else None,
                "symbol": row["symbol"],
                "side": row["side"],
                "pnl": pnl,
                "expected": round(expected, 8),
            })
    if skipped:
        logger.info("ledger invariant: %d exit rows unverifiable (no replayable book)",
                    skipped)
    return violations


def _replay_fill(books: dict[tuple, list[float]], row: dict) -> Optional[float]:
    """Apply one fill to its book; return the expected pnl for exit legs.

    Returns None for entry legs and for exits the replay cannot verify
    (missing price, or no matching book on this side).
    """
    try:
        price = float(row["entry_price"])  # the fill price, on every leg
        qty = float(row["quantity"])
        fee = float(row["fee_usd"] or 0.0)
    except (TypeError, ValueError):
        return None
    if qty <= 0:
        return None
    key = (int(row["agent_id"]), row["market"], row["symbol"],
           int(row["run_id"]) if row["run_id"] is not None else None)
    book = books.setdefault(key, [0.0, 0.0])
    side = row["side"]

    if side == "buy":
        if book[0] > _QTY_EPS:
            total = book[0] + qty
            book[1] = (book[0] * book[1] + qty * price) / total
            book[0] = total
        else:
            book[0], book[1] = qty, price
        return None
    if side == "short":
        if book[0] < -_QTY_EPS:
            total_abs = abs(book[0]) + qty
            book[1] = (abs(book[0]) * book[1] + qty * price) / total_abs
            book[0] -= qty
        else:
            book[0], book[1] = -qty, price
        return None
    if side == "sell":
        if book[0] <= _QTY_EPS:
            return None  # no long book to sell against — unverifiable
        expected = (price - book[1]) * qty - fee
        book[0] -= qty
        return expected
    if side == "cover":
        if book[0] >= -_QTY_EPS:
            return None  # no short book to cover — unverifiable
        expected = (book[1] - price) * qty - fee
        book[0] += qty
        return expected
    return None


def run_nightly_check() -> dict:
    """The nightly sweep: check the last day's exits (plus margin), and on
    violations write a run_events telemetry row per affected run and one
    aggregated admin alert. Returns a summary for the task log line."""
    hours = float(os.getenv("LEDGER_INVARIANT_WINDOW_HOURS", "26"))
    violations = check_exit_rows(hours)
    if not violations:
        return {"violations": 0, "window_hours": hours}

    from trading_runs import emit_telemetry_event
    for v in violations:
        if v["run_id"] is not None:
            emit_telemetry_event(v["run_id"], "ledger_invariant_violation", v)

    lines = [
        f"signal {v['signal_id']} agent {v['agent_id']} run {v['run_id']} "
        f"{v['side']} {v['symbol']}: pnl={v['pnl']:.4f} expected={v['expected']:.4f}"
        for v in violations
    ]
    try:
        from admin_alerts import notify_admins
        notify_admins(
            f"Ledger invariant: {len(violations)} exit row(s) disagree with replay",
            "Recomputed exit P&L disagrees with signals.pnl (>$0.05):\n"
            + "\n".join(lines),
        )
    except Exception:  # noqa: BLE001 — alerting must never break the sweep
        logger.warning("ledger invariant: admin alert failed", exc_info=True)
    return {"violations": len(violations), "window_hours": hours}
