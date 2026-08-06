"""Fill the desk corpus from the two sources that were being lost.

`ingest_decisions()` — the sooppiy AI's own reasoning. Every `decision` event
carries a `report`: the desk's stated case for what it did. That text is the
most valuable thing the platform produces and, until now, was only ever read
once, by nobody, and then buried under the next 200 events.

`ingest_run_outcomes()` — what those decisions actually produced. A decision and
its result are separate rows joined by nothing that says "this is what came of
that", so the desk cannot be asked "when you reasoned like this before, how did
it end?".

`ingest_reports()` — the monitoring analysis: handoff, cycle notes, findings,
traps. Chunked per `##` heading, because a whole day's note is too coarse to
retrieve and a paragraph loses the heading that says what it is about.

All three are idempotent (see `desk_memory._sha`), so they are safe to re-run
on every cycle; an edited chunk stores a new memory rather than keeping a stale
one, which matters because monitoring notes are corrected in place.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any, Optional

from database import get_db_connection
from desk_memory import remember

logger = logging.getLogger(__name__)

# A run's realized result is only meaningful once it is over.
_TERMINAL = ("stopped", "finished", "failed")


def _f(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def ingest_decisions(limit: int = 5000) -> int:
    """Store each decision as the desk's own words plus the numbers behind it."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT e.run_id, e.seq, e.ts, e.payload, r.symbol, r.market "
            "FROM run_events e LEFT JOIN trading_runs r ON r.id = e.run_id "
            "WHERE e.event_type = ? ORDER BY e.id DESC LIMIT ?",
            ("decision", limit))
        rows = [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()

    stored = 0
    for row in rows:
        try:
            p = json.loads(row.get("payload") or "{}")
        except (ValueError, TypeError):
            continue
        report = (p.get("report") or "").strip()
        if not report:
            # A decision with no stated case has nothing to retrieve later.
            continue
        action = str(p.get("action") or "?")
        conf, conv = _f(p.get("confidence")), _f(p.get("conviction"))
        scores = p.get("scores") or {}
        route = (p.get("route") or {}).get("route") or "?"
        body = (
            f"{report}\n\n"
            f"action={action} confidence={conf:.2f} conviction={conv:.2f} "
            f"route={route} gate={p.get('gate_source') or '?'} "
            f"size_scale={_f(p.get('size_scale')):.4f}\n"
            f"scores: " + ", ".join(f"{k}={_f(v):.2f}" for k, v in
                                    sorted(scores.items()))
        )
        tags = [f"action:{action}", f"route:{route}"]
        if conf:
            tags.append("high-confidence" if conf >= 0.7 else "marginal-confidence")
        if remember("decision",
                    f"run:{row['run_id']}:cycle:{p.get('cycle')}:seq:{row['seq']}",
                    f"{row.get('symbol') or '?'} {action} (conf {conf:.2f})",
                    body, ts=row.get("ts"), run_id=row.get("run_id"),
                    symbol=row.get("symbol"), market=row.get("market"),
                    tags=tags):
            stored += 1
    return stored


def ingest_run_outcomes() -> int:
    """Join each finished run to what it actually realized.

    Deliberately reads the run's own terminal state rather than summing
    `adapt realized`, which is known to omit every `run:N:flatten` close — the
    exact closes that happen on the worst days. A corpus built on that query
    would teach the desk from a book that hides its losses."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        placeholders = ", ".join("?" for _ in _TERMINAL)
        cur.execute(
            f"SELECT id, symbol, market, status, status_reason, realized_pnl_usd, "
            f"cycle_seq, started_at, stopped_at FROM trading_runs "
            f"WHERE status IN ({placeholders})", _TERMINAL)
        rows = [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()

    stored = 0
    for r in rows:
        pnl = _f(r.get("realized_pnl_usd"))
        verdict = "profit" if pnl > 0 else ("loss" if pnl < 0 else "flat")
        body = (
            f"Run {r['id']} on {r.get('symbol')} ({r.get('market')}) ended "
            f"{r.get('status')} after {r.get('cycle_seq')} cycles with realized "
            f"P&L {pnl:+.2f}. Reason: {r.get('status_reason') or 'not recorded'}. "
            f"Started {r.get('started_at')}, stopped {r.get('stopped_at')}."
        )
        tags = [f"outcome:{verdict}", f"reason:{r.get('status_reason') or 'none'}"]
        if pnl <= -0.99:
            # The owner's floor rule: below this a run is cleaned and rebuilt.
            tags.append("below-loss-floor")
        if remember("outcome", f"run:{r['id']}:outcome",
                    f"Run {r['id']} {r.get('symbol')} {verdict} {pnl:+.2f}",
                    body, ts=r.get("stopped_at"), run_id=r["id"],
                    symbol=r.get("symbol"), market=r.get("market"), tags=tags):
            stored += 1
    return stored


_HEADING = re.compile(r"^(#{2,3})\s+(.*)$")


def _chunk_markdown(text: str) -> list[tuple[str, str]]:
    """Split on `##`/`###` headings. Content before the first heading is kept
    under the document's own title — dropping it would lose the framing
    paragraph, which in these notes is usually the finding itself."""
    chunks: list[tuple[str, str]] = []
    title, buf = "", []
    for line in text.splitlines():
        m = _HEADING.match(line)
        if m:
            if buf:
                chunks.append((title, "\n".join(buf).strip()))
            title, buf = m.group(2).strip(), []
        else:
            buf.append(line)
    if buf:
        chunks.append((title, "\n".join(buf).strip()))
    return [(t, b) for t, b in chunks if b]


def ingest_reports(root: str, *, min_chars: int = 120) -> int:
    """Chunk the monitoring markdown under `root` (docs/reports, docs/plan)."""
    stored = 0
    for dirpath, _dirs, files in os.walk(root):
        for name in sorted(files):
            if not name.endswith(".md"):
                continue
            path = os.path.join(dirpath, name)
            try:
                with open(path, encoding="utf-8") as fh:
                    text = fh.read()
            except OSError:
                logger.warning("desk_memory: unreadable %s", path, exc_info=True)
                continue
            rel = os.path.relpath(path, root)
            for heading, body in _chunk_markdown(text):
                if len(body) < min_chars:
                    # A heading with two lines under it is a signpost, not a
                    # finding; retrieving it would only dilute the results.
                    continue
                if remember("monitoring", f"{rel}#{heading or 'intro'}",
                            f"{name}: {heading or 'intro'}", body,
                            ts=_date_from_name(name)):
                    stored += 1
    return stored


_DATE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def _date_from_name(name: str) -> Optional[str]:
    m = _DATE.search(name)
    return f"{m.group(1)}T00:00:00Z" if m else None


# ── the daemon ────────────────────────────────────────────────────────────
# Owner asked for a daemon, not a script someone remembers to run. It rides
# the scheduler tick (~30s) and throttles itself, so there is no second loop
# to supervise. It must never be able to break a trading tick: see the guard
# in run_engine.tick().
_INGEST_EVERY_MIN = 30
_DEFAULT_REPORTS_DIR = "docs/reports"
_last_ingest_epoch: float = 0.0


def _ingest_every_min() -> int:
    try:
        return max(1, int(os.environ.get("DESK_MEMORY_INGEST_MIN",
                                         _INGEST_EVERY_MIN)))
    except ValueError:
        return _INGEST_EVERY_MIN


def maybe_ingest(now_epoch: Optional[float] = None) -> Optional[dict[str, int]]:
    """Ingest at most once per interval. Returns None when throttled.

    The decision limit is deliberately small: this runs forever, and a 5000-row
    sweep every half hour would spend its whole life re-checking chunks it
    already stored. One interval's decisions is what is actually new."""
    global _last_ingest_epoch
    now = time.time() if now_epoch is None else now_epoch
    if now - _last_ingest_epoch < _ingest_every_min() * 60:
        return None
    _last_ingest_epoch = now
    out = {"decisions": ingest_decisions(limit=500),
           "outcomes": ingest_run_outcomes()}
    # Relative on purpose: both the container and a local checkout run from
    # the project root, so one default works in both without a prod env edit.
    # Absent directory is a no-op, so this is safe wherever it does not apply.
    root = os.environ.get("DESK_MEMORY_REPORTS_DIR", _DEFAULT_REPORTS_DIR)
    if root and os.path.isdir(root):
        out["reports"] = ingest_reports(root)
    return out


def ingest_all(reports_root: Optional[str] = None) -> dict[str, int]:
    out = {"decisions": ingest_decisions(), "outcomes": ingest_run_outcomes()}
    if reports_root and os.path.isdir(reports_root):
        out["reports"] = ingest_reports(reports_root)
    return out
