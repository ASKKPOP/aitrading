"""30-minute desk cycles — the AI Analysis list on the automation page.

Sooppiy AI already analyses every RUN on its own interval and journals the
result into ``run_events``: a ``decision`` row carrying the action, the
confidence/conviction and the desk's WRITTEN report, ``gate_skip`` rows
carrying why a cycle declined to trade, ``equity`` rows carrying realized /
unrealized, and ``run_status`` rows carrying every transition and its reason.

Nothing composed those per-run rows into an account-level cycle, and the UI
rendered a decision as ``buy conf 0.72`` — the report the desk wrote was
stored and never shown. This module is that composition, and only that: it
reads the existing journal and folds it onto a fixed 30-minute grid.

Read-side by design. The daemon journals continuously whether or not anyone
is signed in, so a cycle list built on request is complete retroactively —
no extra LLM call, no new table, no new worker loop.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from database import get_db_connection
from trading_runs import TS_FMT

logger = logging.getLogger(__name__)

CYCLE_MINUTES = 30
DEFAULT_CYCLES = 12
MAX_CYCLES = 48

# Journal rows the cycle view is built from. Anything else in the journal is
# ignored here rather than rendered as an unlabelled blob.
EVENT_TYPES = ("decision", "gate_skip", "equity", "run_status")


def _parse_ts(value: str) -> Optional[datetime]:
    try:
        return datetime.strptime(value, TS_FMT).replace(tzinfo=timezone.utc)
    except Exception:  # noqa: BLE001
        return None


def cycle_start(dt: datetime) -> datetime:
    """Floor a timestamp onto the 30-minute grid (:00 / :30, UTC)."""
    return dt.replace(minute=(dt.minute // CYCLE_MINUTES) * CYCLE_MINUTES,
                      second=0, microsecond=0)


def _payload(raw: Any) -> dict:
    try:
        obj = json.loads(raw or "{}")
        return obj if isinstance(obj, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _num(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _window_runs(cursor, agent_id: int, since_iso: str) -> dict[int, dict]:
    """The agent's runs that have journal activity inside the window."""
    cursor.execute(
        """SELECT r.id, r.symbol, r.market, r.status, r.status_reason,
                  r.peak_pnl_usd, r.realized_pnl_usd
             FROM trading_runs r
            WHERE r.agent_id = ?
              AND EXISTS (SELECT 1 FROM run_events e
                           WHERE e.run_id = r.id AND e.ts >= ?)""",
        (agent_id, since_iso),
    )
    return {int(r["id"]): dict(r) for r in cursor.fetchall()}


def _baseline(cursor, run_id: int, since_iso: str) -> dict:
    """Last known equity for a run BEFORE the window.

    Carried into the first cycle so its delta measures the window, not the
    run's whole life, and so a quiet cycle still reports a running total.
    """
    cursor.execute(
        """SELECT payload FROM run_events
            WHERE run_id = ? AND event_type = 'equity' AND ts < ?
            ORDER BY ts DESC, seq DESC LIMIT 1""",
        (run_id, since_iso),
    )
    row = cursor.fetchone()
    if not row:
        return {}
    p = _payload(row["payload"])
    return {"realized": _num(p.get("realized")) or 0.0,
            "unrealized": _num(p.get("unrealized")) or 0.0}


def _events(cursor, run_ids: list[int], since_iso: str) -> list[dict]:
    if not run_ids:
        return []
    marks = ",".join("?" for _ in run_ids)
    types = ",".join("?" for _ in EVENT_TYPES)
    cursor.execute(
        f"""SELECT run_id, seq, event_type, ts, payload FROM run_events
             WHERE run_id IN ({marks}) AND ts >= ?
               AND event_type IN ({types})
             ORDER BY ts ASC, seq ASC""",
        (*run_ids, since_iso, *EVENT_TYPES),
    )
    return [dict(r) for r in cursor.fetchall()]


def _blank_run_cell(run: dict) -> dict:
    return {"run_id": run["id"], "symbol": run["symbol"], "market": run["market"],
            "action": None, "confidence": None, "conviction": None, "report": None,
            "skips": [], "transitions": [], "decisions": 0,
            "realized": None, "realized_delta": 0.0, "unrealized": None,
            "peak": _num(run.get("peak_pnl_usd")),
            "preservation": None, "status": run.get("status"),
            "status_reason": run.get("status_reason")}


def _fold_event(cell: dict, event: dict) -> None:
    """Fold one journal row into its run's cell for that cycle."""
    kind = event["event_type"]
    p = _payload(event["payload"])
    if kind == "decision":
        cell["decisions"] += 1
        # Latest decision in the cycle wins — it is the desk's current read.
        cell["action"] = p.get("action")
        cell["confidence"] = _num(p.get("confidence"))
        cell["conviction"] = _num(p.get("conviction"))
        report = (p.get("report") or "").strip()
        if report:
            cell["report"] = report
    elif kind == "gate_skip":
        reason = (p.get("reason") or "").strip()
        if not reason:
            return
        stage = (p.get("stage") or "").strip()
        for s in cell["skips"]:
            if s["reason"] == reason and s["stage"] == stage:
                s["count"] += 1
                return
        cell["skips"].append({"stage": stage, "reason": reason, "count": 1})
    elif kind == "equity":
        realized = _num(p.get("realized"))
        if realized is not None:
            cell["realized"] = realized
        unrealized = _num(p.get("unrealized"))
        if unrealized is not None:
            cell["unrealized"] = unrealized
    elif kind == "run_status":
        cell["transitions"].append({"from": p.get("from"), "to": p.get("to"),
                                    "reason": p.get("reason")})


def _finish_cell(cell: dict, carried: dict) -> None:
    """Carry a run's last known equity forward and settle its deltas."""
    if cell["realized"] is None:
        cell["realized"] = carried.get("realized")
    if cell["unrealized"] is None:
        cell["unrealized"] = carried.get("unrealized")
    prev = carried.get("realized")
    if cell["realized"] is not None and prev is not None:
        cell["realized_delta"] = round(cell["realized"] - prev, 6)
    peak, realized = cell["peak"], cell["realized"]
    # Preservation only means something on a run that actually went up.
    if peak and peak > 0 and realized is not None:
        cell["preservation"] = round(realized / peak, 4)
    if cell["realized"] is not None:
        carried["realized"] = cell["realized"]
    if cell["unrealized"] is not None:
        carried["unrealized"] = cell["unrealized"]


def _opened(cell: dict) -> bool:
    return any(t.get("to") == "running" and t.get("from") != "running"
               for t in cell["transitions"])


def _closed(cell: dict) -> bool:
    return any(t.get("to") in ("stopped", "finished") for t in cell["transitions"])


def agent_cycles(agent_id: int, cycles: int = DEFAULT_CYCLES,
                 now: Optional[datetime] = None) -> list[dict]:
    """The agent's last ``cycles`` 30-minute desk cycles, newest first.

    Every bucket in the window is emitted, quiet ones included — the grid is
    the point. A quiet cycle carries the running totals and ``quiet: true``.
    """
    # Explicit clamp: `cycles or DEFAULT` would read 0 as "give me 12".
    try:
        cycles = DEFAULT_CYCLES if cycles is None else int(cycles)
    except (TypeError, ValueError):
        cycles = DEFAULT_CYCLES
    cycles = max(1, min(cycles, MAX_CYCLES))
    now = now or datetime.now(timezone.utc)
    latest = cycle_start(now)
    starts = [latest - timedelta(minutes=CYCLE_MINUTES * i)
              for i in range(cycles - 1, -1, -1)]
    since_iso = starts[0].strftime(TS_FMT)

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        runs = _window_runs(cursor, agent_id, since_iso)
        if not runs:
            return []
        events = _events(cursor, list(runs.keys()), since_iso)
        carried = {rid: _baseline(cursor, rid, since_iso) for rid in runs}
    finally:
        conn.close()

    # Bucket the journal once, then walk the grid in order so each run's
    # carry-forward advances cycle by cycle.
    by_bucket: dict[str, list[dict]] = {}
    for event in events:
        ts = _parse_ts(event["ts"])
        if ts is None:
            continue
        by_bucket.setdefault(cycle_start(ts).strftime(TS_FMT), []).append(event)

    out: list[dict] = []
    for start in starts:
        key = start.strftime(TS_FMT)
        cells: dict[int, dict] = {}
        for event in by_bucket.get(key, []):
            run = runs.get(int(event["run_id"]))
            if not run:
                continue
            cell = cells.setdefault(run["id"], _blank_run_cell(run))
            _fold_event(cell, event)
        touched = set(cells)
        # Runs with no row this cycle still hold their book; keep the totals
        # honest by carrying every known run forward, not just active ones.
        for rid, run in runs.items():
            if rid not in cells:
                cells[rid] = _blank_run_cell(run)
        for rid, cell in cells.items():
            _finish_cell(cell, carried.setdefault(rid, {}))

        active = [c for rid, c in cells.items() if rid in touched]
        realized = [c["realized"] for c in cells.values() if c["realized"] is not None]
        unrealized = [c["unrealized"] for c in cells.values() if c["unrealized"] is not None]
        out.append({
            "start": key,
            "end": (start + timedelta(minutes=CYCLE_MINUTES)).strftime(TS_FMT),
            "quiet": not active,
            "realized": round(sum(realized), 6) if realized else None,
            "unrealized": round(sum(unrealized), 6) if unrealized else None,
            "realized_delta": round(sum(c["realized_delta"] for c in cells.values()), 6),
            "decisions": sum(c["decisions"] for c in active),
            "skips": sum(s["count"] for c in active for s in c["skips"]),
            "opened": sum(1 for c in active if _opened(c)),
            "closed": sum(1 for c in active if _closed(c)),
            "runs_active": len(active),
            # Only runs the desk actually touched this cycle get a row —
            # the carried-forward ones are in the totals, not the table.
            "runs": sorted(active, key=lambda c: c["run_id"], reverse=True),
        })
    out.reverse()
    return out
