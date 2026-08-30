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

import json
import logging
import os
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Optional

from database import get_db_connection

logger = logging.getLogger(__name__)

# A book within dust of flat IS flat (services.py lot-consolidation epsilon).
_QTY_EPS = 1e-8
# Absolute dollars of disagreement a row may carry before it violates.
_TOLERANCE = 0.05
# Cash-reset detector (the 08-26 incident's other half): dollars an agent's
# cash may drift from what the window's fills account for.
_CASH_TOLERANCE = 0.10
_CASH_STATE_KEY = "ledger_invariant_cash_state"

_EXIT_SIDES = ("sell", "cover")
_FILL_SIDES = ("buy", "short", "sell", "cover")


def ledger_invariant_enabled() -> bool:
    return os.getenv("LEDGER_INVARIANT_ENABLED", "1").strip().lower() in (
        "1", "true", "yes", "on")


def check_exit_rows(hours: float | None = 24) -> list[dict]:
    """Recompute expected pnl for every exit fill in the window; return violations.

    ``hours=None`` checks all time. A row violates when
    |pnl − expected| > $0.05 (a zeroed OR NULL pnl against a material
    expected value is the same test with pnl == 0). Books are keyed
    (agent_id, market, symbol, run_id) — the same key the positions table
    enforces — and replayed from the beginning of the signals table so a
    window exit sees its out-of-window entries. Polymarket is excluded:
    settlement writes don't follow the two-leg fee convention.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        exit_placeholders = ",".join("?" for _ in _EXIT_SIDES)

        # 1. The exits to verify (window applies here only). A NULL pnl is
        # NOT a free pass: an exit fill whose book replays to a material
        # value but recorded nothing is the same defect as a zeroed one.
        query = (
            "SELECT id, agent_id FROM signals "
            f"WHERE side IN ({exit_placeholders}) "
            "AND message_type = 'operation' "
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
            "AND message_type = 'operation' "
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
        pnl = float(row["pnl"]) if row["pnl"] is not None else None
        if abs((pnl if pnl is not None else 0.0) - expected) > _TOLERANCE:
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


# ── cash-reset detector ────────────────────────────────────────────────────
# The 08-26 incident's OTHER half: the reset restored agents.cash to exactly
# starting_capital, which the row replay above cannot see (every signals row
# was individually consistent — the CASH column was rewritten out from under
# them). Snapshot per-agent cash each nightly run (platform_settings, the
# trend_module state pattern); on the next run an agent whose cash moved by
# more than the window's fills account for (execute_paper_trade's own leg
# arithmetic) is a violation. First run just stores. Fills the replay cannot
# account for (polymarket legs, exits with no replayable book, unparseable
# rows) mark that agent unverifiable for the window — skipped, never flagged.
# Leverage: run-attributed fills use the run's config leverage
# (config_snapshot_json, the same value the position was opened with);
# run-less fills assume 1× — a leveraged manual trade in the window can
# therefore false-positive, which is the conservative direction for a
# reset detector.


def _load_cash_state() -> Optional[dict]:
    from platform_settings import get_setting
    raw = get_setting(_CASH_STATE_KEY)
    if raw:
        try:
            state = json.loads(raw)
            if isinstance(state, dict) and "ts" in state \
                    and isinstance(state.get("cash"), dict):
                return state
        except (ValueError, TypeError):
            logger.warning("ledger invariant: corrupt cash state — starting fresh")
    return None


def _save_cash_state(state: dict) -> None:
    from platform_settings import set_setting
    set_setting(_CASH_STATE_KEY, json.dumps(state), updated_by="ledger_invariant")


def check_cash_reset(now_ts: Optional[int] = None) -> list[dict]:
    """Compare each agent's cash against the previous snapshot plus the
    window's fill-accounted deltas; return violations and store the new
    snapshot. First run (no prior snapshot) stores and returns []."""
    if now_ts is None:
        now_ts = int(datetime.now(timezone.utc).timestamp())
    state = _load_cash_state()
    prev_ts = int(state["ts"]) if state else None
    prev_cash = state["cash"] if state else None

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, cash FROM agents")
        current = {int(r["id"]): float(r["cash"] or 0) for r in cursor.fetchall()}

        window_fills: list[dict] = []
        history: list[dict] = []
        lev_by_run: dict[int, float] = {}
        if prev_cash is not None:
            fill_placeholders = ",".join("?" for _ in _FILL_SIDES)
            cursor.execute(
                "SELECT id, agent_id, market, symbol, side, entry_price, "
                "quantity, fee_usd, run_id FROM signals "
                f"WHERE side IN ({fill_placeholders}) "
                "AND message_type = 'operation' AND quantity IS NOT NULL "
                "AND timestamp > ? AND timestamp <= ? ORDER BY id",
                [*_FILL_SIDES, prev_ts, now_ts])
            window_fills = [dict(r) for r in cursor.fetchall()]
            agent_ids = sorted({int(r["agent_id"]) for r in window_fills})
            if agent_ids:
                agent_placeholders = ",".join("?" for _ in agent_ids)
                cursor.execute(
                    "SELECT id, agent_id, market, symbol, side, entry_price, "
                    "quantity, fee_usd, run_id FROM signals "
                    f"WHERE agent_id IN ({agent_placeholders}) "
                    f"AND side IN ({fill_placeholders}) "
                    "AND message_type = 'operation' AND quantity IS NOT NULL "
                    "ORDER BY id",
                    [*agent_ids, *_FILL_SIDES])
                history = [dict(r) for r in cursor.fetchall()]
            run_ids = sorted({int(r["run_id"]) for r in window_fills
                              if r["run_id"] is not None})
            if run_ids:
                run_placeholders = ",".join("?" for _ in run_ids)
                cursor.execute(
                    "SELECT id, config_snapshot_json FROM trading_runs "
                    f"WHERE id IN ({run_placeholders})", run_ids)
                for r in cursor.fetchall():
                    try:
                        cfg = json.loads(r["config_snapshot_json"] or "{}")
                        lev_by_run[int(r["id"])] = max(
                            1.0, float(cfg.get("leverage") or 1.0))
                    except (ValueError, TypeError):
                        lev_by_run[int(r["id"])] = 1.0
    finally:
        conn.close()

    _save_cash_state({"ts": now_ts,
                      "cash": {str(aid): cash for aid, cash in current.items()}})
    if prev_cash is None:
        return []

    window_ids = {int(r["id"]) for r in window_fills}
    books: dict[tuple, list[float]] = {}
    deltas: dict[int, float] = defaultdict(float)
    unverifiable: set[int] = set()
    for row in history:
        aid = int(row["agent_id"])
        in_window = int(row["id"]) in window_ids
        if row["market"] == "polymarket":
            # Settlement writes don't follow the two-leg convention; the
            # agent's window cannot be accounted this run.
            if in_window:
                unverifiable.add(aid)
            continue
        key = (aid, row["market"], row["symbol"],
               int(row["run_id"]) if row["run_id"] is not None else None)
        book = books.get(key)
        avg_before = book[1] if book else 0.0
        expected = _replay_fill(books, row)
        if not in_window:
            continue
        try:
            price = float(row["entry_price"])
            qty = float(row["quantity"])
            fee = float(row["fee_usd"] or 0.0)
        except (TypeError, ValueError):
            unverifiable.add(aid)
            continue
        lev = lev_by_run.get(int(row["run_id"]), 1.0) \
            if row["run_id"] is not None else 1.0
        side = row["side"]
        # execute_paper_trade's exact cash legs (margin = notional/L):
        if side in ("buy", "short"):
            deltas[aid] -= price * qty / lev + fee
        elif side == "sell":
            if expected is None:
                unverifiable.add(aid)
                continue
            deltas[aid] += avg_before * qty / lev + (price - avg_before) * qty - fee
        elif side == "cover":
            if expected is None:
                unverifiable.add(aid)
                continue
            deltas[aid] += avg_before * qty / lev + (avg_before - price) * qty - fee

    violations: list[dict] = []
    for aid_str, prev_val in prev_cash.items():
        try:
            aid = int(aid_str)
            prev_float = float(prev_val)
        except (TypeError, ValueError):
            continue
        if aid in unverifiable or aid not in current:
            continue
        expected_cash = prev_float + deltas.get(aid, 0.0)
        if abs(current[aid] - expected_cash) > _CASH_TOLERANCE:
            violations.append({
                "agent_id": aid,
                "prev_cash": round(prev_float, 8),
                "current_cash": round(current[aid], 8),
                "expected_cash": round(expected_cash, 8),
                "window_delta": round(deltas.get(aid, 0.0), 8),
            })
    if unverifiable:
        logger.info("ledger invariant: %d agent(s) cash-unverifiable this window",
                    len(unverifiable))
    return violations


def run_nightly_check() -> dict:
    """The nightly sweep: check the last day's exits (plus margin) and the
    per-agent cash deltas; on violations write a run_events telemetry row
    per affected run and aggregated admin alerts. Returns a summary for the
    task log line."""
    hours = float(os.getenv("LEDGER_INVARIANT_WINDOW_HOURS", "26"))
    violations = check_exit_rows(hours)
    if violations:
        from trading_runs import emit_telemetry_event
        for v in violations:
            if v["run_id"] is not None:
                emit_telemetry_event(v["run_id"], "ledger_invariant_violation", v)

        lines = [
            f"signal {v['signal_id']} agent {v['agent_id']} run {v['run_id']} "
            f"{v['side']} {v['symbol']}: "
            f"pnl={'NULL' if v['pnl'] is None else format(v['pnl'], '.4f')} "
            f"expected={v['expected']:.4f}"
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

    cash_violations: list[dict] = []
    try:
        cash_violations = check_cash_reset()
    except Exception:  # noqa: BLE001 — the row check must still report
        logger.warning("ledger invariant: cash-reset check failed", exc_info=True)
    if cash_violations:
        cash_lines = [
            f"agent {v['agent_id']}: cash {v['prev_cash']:.2f} -> "
            f"{v['current_cash']:.2f} but window fills account for "
            f"{v['window_delta']:+.2f} (expected {v['expected_cash']:.2f})"
            for v in cash_violations
        ]
        try:
            from admin_alerts import notify_admins
            notify_admins(
                f"Ledger invariant: {len(cash_violations)} agent(s) cash moved "
                "without fills accounting for it",
                "agents.cash changed by more than the window's fills explain "
                "(>$0.10) — the 08-26 cash-reset fingerprint:\n"
                + "\n".join(cash_lines),
            )
        except Exception:  # noqa: BLE001
            logger.warning("ledger invariant: cash admin alert failed", exc_info=True)

    return {"violations": len(violations),
            "cash_violations": len(cash_violations),
            "window_hours": hours}
