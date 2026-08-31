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

`ingest_skill_lessons()` — the doctrine the desk is already given, atomised.
The skills catalogue arrives as ~40 whole bodies in every prompt; split into
single claims it becomes a retrievable pool instead, which is what plan 22's
attribution needs before it can rank anything (§7 increment a3).

All four are idempotent (see `desk_memory._sha`), so they are safe to re-run
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
from desk_memory import _sha, forget_superseded, known_shas, remember

logger = logging.getLogger(__name__)

# A run's realized result is only meaningful once it is over.
_TERMINAL = ("stopped", "finished", "failed")


def _f(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def ingest_decisions(limit: int = 5000,
                     known: Optional[set[str]] = None) -> int:
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
                    tags=tags, known=known):
            stored += 1
    return stored


# What ENDED the run, in words, and — the distinction a desk can act on —
# whether the desk chose the exit or the platform imposed it. `desk_retired`
# is the only reason that is the desk's own call; every stop_event and every
# other *_retired rail is forced on it, and `fleet_stop_all` is the user's.
_EXIT_PHRASE: dict[str, str] = {
    "desk_retired": "the desk retired the thesis itself",
    "adapt_retired": ("the adapt rail retired it after repeated losing closes"
                      " — not the desk's own call"),
    "idle_retired": ("the idle rail retired it for never trading"
                     " — not the desk's own call"),
    "no_prospect_switched": ("switched out after the desk saw no profitable"
                             " entry for hours — driven by the desk's own"
                             " flat holds"),
    "fleet_stop_all": "the user stopped the whole fleet — not the desk's own call",
    "stop_event:at_time": "the time stop closed it — not the desk's own call",
    "stop_event:trailing_lock": ("the trailing lock closed it"
                                 " — not the desk's own call"),
    "stop_event:max_loss": "the max-loss rail closed it — not the desk's own call",
    "stop_event:conviction_collapse": ("conviction collapsed and the rail closed"
                                       " it — not the desk's own call"),
    "positions_held": "it ended with positions still held — not the desk's own call",
}


def _outcome_body(r: dict, pnl: float, traded: bool) -> str:
    """Describe a finished run in the vocabulary a live run's recall query is
    actually built from (`run_engine._recall_query`).

    The body was a metadata template — status, an enum and two timestamps —
    and carried none of that vocabulary, so an outcome could never be
    retrieved however relevant it was. Measured on prod 2026-08-15: 0 of 278
    outcomes surfaced in any of the 12 (market x situation) cells, against a
    lesson pool of 147. This is not keyword stuffing: a run that lost while
    giving back a peak IS a losing position that gave back its peak, and that
    is the only sentence a desk in the same situation can learn from."""
    sym, mkt = r.get("symbol"), r.get("market")
    cycles = r.get("cycle_seq")
    exit_phrase = _EXIT_PHRASE.get(str(r.get("status_reason") or ""),
                                   str(r.get("status_reason") or "not recorded"))
    if not traded:
        # 140 of prod's 278 outcomes realized exactly +0.00 because the run
        # never opened a position. "ended stopped with realized P&L +0.00"
        # reads as a flat TRADE, which is a different and far rarer thing.
        return (f"Run {r['id']} on {sym} ({mkt}) never opened a position: "
                f"{cycles} cycles of looking, then {exit_phrase}. Nothing was "
                f"risked and nothing was learned about the entry — the thesis "
                f"never became a trade. Started {r.get('started_at')}, "
                f"stopped {r.get('stopped_at')}.")
    stance = "winning position" if pnl > 0 else (
        "losing position" if pnl < 0 else "position that ended flat")
    bits = [f"Run {r['id']} on {sym} ({mkt}) closed a {stance}: realized P&L "
            f"{pnl:+.2f} over {cycles} cycles."]
    peak = r.get("peak_pnl_usd")
    try:
        peak = float(peak) if peak is not None else None
    except (TypeError, ValueError):
        peak = None
    if peak is not None and peak > 0 and peak > pnl:
        kept = (pnl / peak) if peak else 0.0
        bits.append(f"It gave back a peak of {peak:+.2f} — give-back of "
                    f"{peak - pnl:.2f}, keeping {kept:.0%} of the high-water "
                    f"mark it had already reached.")
    bits.append(f"The exit: {exit_phrase}.")
    bits.append(f"Started {r.get('started_at')}, stopped {r.get('stopped_at')}.")
    return " ".join(bits)


def ingest_run_outcomes(known: Optional[set[str]] = None) -> int:
    """Join each finished run to what it actually realized.

    Deliberately reads the run's own terminal state rather than summing
    `adapt realized`, which is known to omit every `run:N:flatten` close — the
    exact closes that happen on the worst days. A corpus built on that query
    would teach the desk from a book that hides its losses."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        placeholders = ", ".join("?" for _ in _TERMINAL)
        # Whether the run ever TRADED cannot be read off the P&L: a run that
        # never opened a position and a run that round-tripped to zero both
        # realize +0.00, and half the corpus is the former.
        cur.execute(
            f"SELECT r.id, r.symbol, r.market, r.status, r.status_reason, "
            f"r.realized_pnl_usd, r.peak_pnl_usd, r.cycle_seq, r.started_at, "
            f"r.stopped_at, "
            f"(SELECT COUNT(*) FROM run_events e WHERE e.run_id = r.id "
            f" AND e.event_type = 'trade') AS trades "
            f"FROM trading_runs r WHERE r.status IN ({placeholders})", _TERMINAL)
        rows = [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()

    stored = 0
    for r in rows:
        pnl = _f(r.get("realized_pnl_usd"))
        traded = int(r.get("trades") or 0) > 0
        verdict = ("profit" if pnl > 0 else ("loss" if pnl < 0 else "flat")
                   ) if traded else "never-traded"
        body = _outcome_body(r, pnl, traded)
        tags = [f"outcome:{verdict}", f"reason:{r.get('status_reason') or 'none'}"]
        if pnl <= -0.99:
            # The owner's floor rule: below this a run is cleaned and rebuilt.
            tags.append("below-loss-floor")
        source = f"run:{r['id']}:outcome"
        if remember("outcome", source,
                    f"Run {r['id']} {r.get('symbol')} {verdict} {pnl:+.2f}",
                    body, ts=r.get("stopped_at"), run_id=r["id"],
                    symbol=r.get("symbol"), market=r.get("market"), tags=tags,
                    known=known):
            stored += 1
        # A finished run has exactly ONE outcome. Without this, every body
        # revision leaves its predecessor in the pool competing for the same
        # two retrieval slots.
        forget_superseded("outcome", source, _sha("outcome", source, body))
    return stored


_SENTENCE = re.compile(r"(?<=[.!?])\s+")
# One claim, one situation, one evidence clause — about the length of a
# monitoring finding, which is what the pool is already made of.
_LESSON_TARGET = 280
_LESSON_MIN = 120


def _atomise(body: str) -> list[str]:
    """Split one skill body into atomic claims.

    Whole sentences only: half a claim is not doctrine, and a splitter that
    dropped a clause would teach the desk something its author never wrote
    (the join of the atoms is asserted equal to the body). A trailing
    fragment below the floor is folded back into the previous claim rather
    than stored on its own — a two-line atom retrieves as noise. A body that
    is short in its ENTIRETY is still kept, unlike a markdown heading with
    two lines under it: a short skill body IS the doctrine."""
    atoms: list[str] = []
    buf = ""
    for sentence in _SENTENCE.split((body or "").strip()):
        sentence = sentence.strip()
        if not sentence:
            continue
        buf = f"{buf} {sentence}".strip()
        if len(buf) >= _LESSON_TARGET:
            atoms.append(buf)
            buf = ""
    if buf:
        if atoms and len(buf) < _LESSON_MIN:
            atoms[-1] = f"{atoms[-1]} {buf}"
        else:
            atoms.append(buf)
    return atoms


def ingest_skill_lessons(known: Optional[set[str]] = None) -> int:
    """Atomise the trading-skills catalogue into `lesson` chunks.

    Plan 22 §7 increment (a3)(i). Recall reads a `monitoring` pool that has
    been frozen at ~560 chunks since 08-08 while `lesson` sat at zero, so
    several situation classes cannot offer the >=3 above-floor candidates
    the attribution model needs. This only FILLS the pool: `_recall_line`
    still searches `kind="monitoring"`, so no prompt, gate, size or order
    changes today.

    A skill scoped to several markets is stored once PER market. The
    candidate filter matches a single `market` column, so one row carrying
    only the first would make a crypto+futures lesson unreachable from
    futures — silently, and only at retrieval time."""
    import trading_skills
    stored = 0
    for skill in trading_skills.all_skills():
        if not skill.get("enabled"):
            continue
        atoms = _atomise(skill.get("body") or "")
        tags = [f"skill:{skill['slug']}"]
        tags += [f"prompt:{p}" for p in (skill.get("prompts") or [])]
        for market in (skill.get("markets") or [None]):
            for i, atom in enumerate(atoms):
                source = f"skill:{skill['slug']}#{i}"
                if market:
                    source = f"{source}:{market}"
                if remember("lesson", source,
                            skill.get("name") or skill["slug"], atom,
                            market=market,
                            tags=tags + ([f"market:{market}"] if market else []),
                            known=known):
                    stored += 1
    return stored


def _lessons_fail_soft(seen: set[str]) -> int:
    """The catalogue is loaded on the trading tick's path; a corpus that
    cannot read it must not cost the tick its other ingests."""
    try:
        return ingest_skill_lessons(known=seen)
    except Exception:  # noqa: BLE001
        logger.warning("desk_memory: skill lesson ingest failed", exc_info=True)
        return 0


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


def ingest_reports(root: str, *, min_chars: int = 120,
                   known: Optional[set[str]] = None) -> int:
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
                            ts=_date_from_name(name), known=known):
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
    # One query for every stored identity, instead of one per chunk. Measured
    # on prod: a no-op ingest took 26-33s of pure round-trips before this.
    seen = known_shas()
    out = {"decisions": ingest_decisions(limit=500, known=seen),
           "outcomes": ingest_run_outcomes(known=seen),
           "lessons": _lessons_fail_soft(seen)}
    # Relative on purpose: both the container and a local checkout run from
    # the project root, so one default works in both without a prod env edit.
    # Absent directory is a no-op, so this is safe wherever it does not apply.
    root = os.environ.get("DESK_MEMORY_REPORTS_DIR", _DEFAULT_REPORTS_DIR)
    if root and os.path.isdir(root):
        out["reports"] = ingest_reports(root, known=seen)
    return out


def ingest_all(reports_root: Optional[str] = None) -> dict[str, int]:
    seen = known_shas()
    out = {"decisions": ingest_decisions(known=seen),
           "outcomes": ingest_run_outcomes(known=seen),
           "lessons": _lessons_fail_soft(seen)}
    if reports_root and os.path.isdir(reports_root):
        out["reports"] = ingest_reports(reports_root, known=seen)
    return out
