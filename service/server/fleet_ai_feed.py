"""Full Auto — the fleet's AI analysis feed, one message per 30 minutes.

Owner ask (2026-11-20): on the automation page, show every 30 minutes what
the AI did for the fleet — how it found its targets, and its buy and sell
decisions — always the latest 3 messages.

Read-side composition only, in the same spirit as ``desk_cycles``. Both
halves are already journaled:

* target finding: ``fleet_events`` — ``research_ranked`` (the shortlist),
  ``backtest_gate`` (kept / dropped with the reason), ``candidate_skipped``,
  ``research_empty``, ``run_started`` / ``rotation`` (a slot got a TRADING)
  and ``fleet_status`` transitions;
* decisions: ``run_events`` of the fleet's TRADINGs — ``decision`` (action,
  confidence, the desk's written report) and ``trade`` (the actual fill).

They are folded onto the fixed UTC 30-minute grid (:00 / :30). A 30-minute
window with nothing in it is not a message; the feed returns the newest
``limit`` windows that have something, looking back ``LOOKBACK_HOURS``.

Every read is bounded: fleet events newest-first by the ``(fleet_id, seq)``
key with a hard row cap, and run events per run by ``(run_id, seq)``. A
long-lived fleet (fleet 44 journaled 300k+ rows) never costs a full scan.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from database import get_db_connection
from desk_cycles import CYCLE_MINUTES, cycle_start
from trading_runs import TS_FMT

DEFAULT_MESSAGES = 3
MAX_MESSAGES = 12
LOOKBACK_HOURS = 24
# Hard caps on rows read per request — the newest rows win.
FLEET_EVENT_CAP = 3000
# Measured on prod 2026-11-20 (fleets 43/44/53): no cap binds; 848 rows max.
# 300 covers a 5-minute desk for ~24h; a partly-read window is dropped per run.
RUN_EVENT_CAP_PER_RUN = 300
# Open TRADINGs are always read first (a fleet has at most 25 slots), then
# the most recently stopped ones — never "newest by id", which let 60 rotated
# runs hide a long-lived open run's current decision (verifier, 2026-11-20).
MAX_OPEN_RUNS = 25      # largest plan's slot count
MAX_STOPPED_RUNS = 40   # most recently stopped, read separately
# Per message, so one noisy window cannot flood the card. Decisions keep
# one row per TRADING up to the largest plan's slot count; fills keep the
# newest MAX_ITEMS.
MAX_ITEMS = 8
MAX_DECISION_ROWS = 25
# The fleet_events read walks (fleet_id, seq) backwards; seq rises with time,
# so a seq floor bounds the scan even when the newest rows are other types
# (adversarial review: unbounded on a 300k-row fleet).
FLEET_SEQ_SPAN = 20000

FLEET_TYPES = ("research_ranked", "backtest_gate", "candidate_skipped",
               "research_empty", "run_started", "rotation", "fleet_status")
RUN_TYPES = ("decision", "trade")


def _payload(raw: Any) -> dict:
    try:
        obj = json.loads(raw or "{}")
        return obj if isinstance(obj, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _parse_ts(value: Any) -> Optional[datetime]:
    try:
        return datetime.strptime(str(value), TS_FMT).replace(tzinfo=timezone.utc)
    except Exception:  # noqa: BLE001
        return None


def _list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _text(value: Any) -> Optional[str]:
    """LLM-authored fields are not type-checked before they are journaled —
    a non-string must never crash the feed (verifier: {"action": 1} → 500)."""
    return value.strip() or None if isinstance(value, str) else None


def _num(value: Any) -> Optional[float]:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _blank(start: datetime) -> dict:
    return {
        "start": start.strftime(TS_FMT),
        "end": (start + timedelta(minutes=CYCLE_MINUTES)).strftime(TS_FMT),
        "targets": {"ranked": [], "kept": [], "dropped": [], "skipped": [],
                    "opened": [], "research_empty": 0, "status": [],
                    "research": []},
        "decisions": {"counts": {}, "runs": [], "fills": []},
    }


def _add_unique(items: list, item: dict, key: tuple) -> None:
    for existing in items:
        if tuple(existing.get(k) for k in key) == tuple(item.get(k) for k in key):
            existing["count"] = existing.get("count", 1) + 1
            return
    if len(items) < MAX_ITEMS:
        items.append({**item, "count": 1})


def _fold_fleet(msg: dict, kind: str, p: dict) -> None:
    t = msg["targets"]
    if kind == "research_ranked":
        for s in _list(p.get("selected")):
            if isinstance(s, dict) and _text(s.get("symbol")):
                _add_unique(t["ranked"], {"symbol": _text(s.get("symbol")),
                                          "market": _text(s.get("market")),
                                          "score": _num(s.get("final_score"))},
                            ("symbol", "market"))
    elif kind == "backtest_gate":
        kept = p.get("kept")
        for sym in ([kept] if isinstance(kept, str) else _list(kept)):
            if isinstance(sym, str):
                _add_unique(t["kept"], {"symbol": sym}, ("symbol",))
        dropped = p.get("dropped") or {}
        if isinstance(dropped, dict):
            for sym, why in dropped.items():
                if isinstance(sym, str):
                    _add_unique(t["dropped"], {"symbol": sym, "reason": _text(why) or ""},
                                ("symbol",))
    elif kind == "candidate_skipped":
        if _text(p.get("symbol")):
            _add_unique(t["skipped"], {"symbol": _text(p.get("symbol")),
                                       "reason": _text(p.get("reason")) or ""},
                        ("symbol", "reason"))
    elif kind == "research_empty":
        t["research_empty"] += 1
    elif kind in ("run_started", "rotation"):
        if _text(p.get("symbol")):
            _add_unique(t["opened"], {"symbol": _text(p.get("symbol")),
                                      "market": _text(p.get("market")),
                                      "run_id": _num(p.get("run_id")),
                                      "budget": _num(p.get("budget") if kind == "run_started"
                                                     else p.get("funding"))},
                        ("run_id", "symbol"))
    elif kind == "fleet_status":
        if _text(p.get("to")):
            t["status"].append({"to": _text(p.get("to")), "reason": _text(p.get("reason"))})


def _fold_run(msg: dict, kind: str, p: dict, run: dict, ts: str) -> None:
    d = msg["decisions"]
    if kind == "decision":
        # No action = no verdict (error / no-price cycle) — never shown as a
        # deliberate "hold" (verifier, 2026-11-20).
        action = (_text(p.get("action")) or "none").lower()
        d["counts"][action] = d["counts"].get(action, 0) + 1
        # Latest decision per TRADING wins — it is the desk's current read.
        row = next((r for r in d["runs"] if r["run_id"] == run["id"]), None)
        if row is None:
            row = {"run_id": run["id"], "symbol": run["symbol"],
                   "market": run["market"], "ts": None}
            d["runs"].append(row)
        if row["ts"] is None or ts >= row["ts"]:
            row.update({"ts": ts, "action": action,
                        "confidence": _num(p.get("confidence")),
                        "decided_by": _text(p.get("decided_by")),
                        "report": _text(p.get("report"))})
    elif kind == "trade":
        d["fills"].append({"ts": ts, "symbol": _text(p.get("symbol")) or run["symbol"],
                           "side": _text(p.get("side")),
                           "quantity": _num(p.get("quantity")),
                           "price": _num(p.get("price"))})


def _trim(msg: dict) -> None:
    """Keep what matters and say how much was left out, never silently the
    oldest: decision rows put trades (anything but hold / no verdict) first,
    then newest; fills keep the newest."""
    d = msg["decisions"]
    runs = sorted(d["runs"], key=lambda x: str(x.get("ts") or ""), reverse=True)
    runs.sort(key=lambda x: x.get("action") in ("hold", "none"))  # stable
    d["runs_more"] = max(0, len(runs) - MAX_DECISION_ROWS)
    d["runs"] = runs[:MAX_DECISION_ROWS]
    fills = sorted(d["fills"], key=lambda x: str(x.get("ts") or ""), reverse=True)
    d["fills_more"] = max(0, len(fills) - MAX_ITEMS)
    d["fills"] = fills[:MAX_ITEMS]


def _targets_active(msg: dict) -> bool:
    t = msg["targets"]
    return bool(t["ranked"] or t["kept"] or t["dropped"] or t["skipped"]
                or t["opened"] or t["research_empty"])


def _empty(msg: dict) -> bool:
    t, d = msg["targets"], msg["decisions"]
    return not (t["ranked"] or t["kept"] or t["dropped"] or t["skipped"]
                or t["opened"] or t["research_empty"] or t["status"]
                or d["runs"] or d["fills"])


def fleet_feed(fleet_id: int, limit: int = DEFAULT_MESSAGES,
               now: Optional[datetime] = None) -> list[dict]:
    """The fleet's newest ``limit`` non-empty 30-minute messages, newest first."""
    try:
        limit = DEFAULT_MESSAGES if limit is None else int(limit)
    except (TypeError, ValueError):
        limit = DEFAULT_MESSAGES
    limit = max(1, min(limit, MAX_MESSAGES))
    now = now or datetime.now(timezone.utc)
    since = cycle_start(now) - timedelta(hours=LOOKBACK_HOURS)
    since_iso = since.strftime(TS_FMT)

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT last_event_seq, market_scope_json, stopped_at "
                       "FROM fleets WHERE id = ?", (fleet_id,))
        frow = cursor.fetchone()
        if not frow:
            return []
        frow = dict(frow)
        # A fleet that stopped before the lookback has nothing to say.
        if frow.get("stopped_at") and str(frow["stopped_at"]) < since_iso:
            return []
        try:
            scope = json.loads(frow.get("market_scope_json") or "null")
        except Exception:  # noqa: BLE001
            scope = None
        scope = {m for m in scope if isinstance(m, str)} if isinstance(scope, list) and scope else None
        seq_floor = int(frow.get("last_event_seq") or 0) - FLEET_SEQ_SPAN
        marks = ",".join("?" for _ in FLEET_TYPES)
        cursor.execute(
            f"""SELECT seq, ts, event_type, payload FROM fleet_events
                 WHERE fleet_id = ? AND seq > ? AND ts >= ?
                   AND event_type IN ({marks})
                 ORDER BY seq DESC LIMIT ?""",
            (fleet_id, seq_floor, since_iso, *FLEET_TYPES, FLEET_EVENT_CAP + 1))
        fleet_rows = [dict(r) for r in cursor.fetchall()]
        # Windows at or before a read's newest UNREAD row may be incomplete:
        # they are kept and marked partial — never dropped, never shown as
        # complete (verifier rounds 2–3).
        partial_floors: list[str] = []
        partial_all = False
        if len(fleet_rows) > FLEET_EVENT_CAP:
            partial_floors.append(str(fleet_rows[-1]["ts"]))   # newest unread row
            fleet_rows = fleet_rows[:FLEET_EVENT_CAP]
        # Rows at or below the seq floor were not read; the newest of them is
        # row `seq_floor` — if it falls in the lookback, its window and older
        # ones are partial.
        if seq_floor > 0:
            cursor.execute("SELECT ts FROM fleet_events WHERE fleet_id = ? AND seq = ?",
                           (fleet_id, seq_floor))
            row = cursor.fetchone()
            if row and str(row["ts"]) >= since_iso:
                partial_floors.append(str(row["ts"]))
        # TRADINGs that can have journal rows in the window: still open, or
        # stopped inside it. Newest first, capped.
        # Two reads, so stray never-stopped rows (leaked drafts) cannot eat
        # the stopped-run budget (review round 3).
        # Open runs by recent ACTIVITY, so never-stopped stray rows (leaked
        # drafts) cannot outrank the run that is actually trading.
        cursor.execute(
            """SELECT id, symbol, market FROM trading_runs
                WHERE fleet_id = ? AND stopped_at IS NULL
                ORDER BY COALESCE(last_cycle_at, started_at, created_at) DESC, id DESC
                LIMIT ?""",
            (fleet_id, MAX_OPEN_RUNS + 1))
        open_rows = [dict(r) for r in cursor.fetchall()]
        if len(open_rows) > MAX_OPEN_RUNS:
            partial_all = True
            open_rows = open_rows[:MAX_OPEN_RUNS]
        runs = {int(r["id"]): r for r in open_rows}
        cursor.execute(
            """SELECT id, symbol, market, stopped_at FROM trading_runs
                WHERE fleet_id = ? AND stopped_at >= ?
                ORDER BY stopped_at DESC, id DESC LIMIT ?""",
            (fleet_id, since_iso, MAX_STOPPED_RUNS + 1))
        stopped_rows = [dict(r) for r in cursor.fetchall()]
        if len(stopped_rows) > MAX_STOPPED_RUNS:
            # Runs stopped at or before the first unread one are missing —
            # and a stop-time flatten fill can be stamped just AFTER
            # stopped_at, so the floor carries one window of margin.
            unread_stop = _parse_ts(stopped_rows[-1]["stopped_at"])
            if unread_stop is not None:
                partial_floors.append((unread_stop + timedelta(minutes=CYCLE_MINUTES)).strftime(TS_FMT))
            stopped_rows = stopped_rows[:MAX_STOPPED_RUNS]
        runs.update({int(r["id"]): r for r in stopped_rows})
        run_rows: list[dict] = []
        # Per-run caps cut only THAT run's rows (review round 2: one busy
        # TRADING must not drop whole windows for the fleet).
        rmarks = ",".join("?" for _ in RUN_TYPES)
        for rid in runs:
            cursor.execute(
                f"""SELECT run_id, seq, ts, event_type, payload FROM run_events
                     WHERE run_id = ? AND event_type IN ({rmarks})
                     ORDER BY seq DESC LIMIT ?""",
                (rid, *RUN_TYPES, RUN_EVENT_CAP_PER_RUN + 1))
            rows = [dict(r) for r in cursor.fetchall()]
            if len(rows) > RUN_EVENT_CAP_PER_RUN:
                cut = _parse_ts(rows[-1]["ts"])          # first row not read in full
                rows = rows[:RUN_EVENT_CAP_PER_RUN]
                if cut is not None:
                    floor = cycle_start(cut).strftime(TS_FMT)
                    partial_floors.append(floor)
                    rows = [r for r in rows
                            if (_parse_ts(r["ts"]) is not None
                                and cycle_start(_parse_ts(r["ts"])).strftime(TS_FMT) > floor)]
            run_rows.extend(rows)
        # The global research batches in the window (hourly, ~16 rows each;
        # the table is small). Says WHAT the research found — e.g. on
        # 2026-11-20 every batch held only shorts, which is why fleets
        # 51–53 logged research_empty until build_failed.
        cursor.execute(
            """SELECT batch_id, market, direction, created_at FROM research_theses
                WHERE created_at >= ? AND created_at <= ?""",
            (since_iso, now.strftime(TS_FMT)))
        theses = [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()

    buckets: dict[str, dict] = {}

    def _bucket(ts_raw: Any) -> Optional[dict]:
        ts = _parse_ts(ts_raw)
        if ts is None or ts < since or ts > now:
            return None
        start = cycle_start(ts)
        key = start.strftime(TS_FMT)
        if key not in buckets:
            buckets[key] = _blank(start)
        return buckets[key]

    # Oldest first, so "latest decision per TRADING" and status order read
    # in time order inside each window.
    for r in sorted(fleet_rows, key=lambda r: (str(r["ts"]), int(r["seq"]))):
        msg = _bucket(r["ts"])
        if msg is not None:
            _fold_fleet(msg, r["event_type"], _payload(r["payload"]))
    for r in sorted(run_rows, key=lambda r: (str(r["ts"]), int(r["run_id"]), int(r["seq"]))):
        msg = _bucket(r["ts"])
        run = runs.get(int(r["run_id"]))
        if msg is not None and run is not None:
            _fold_run(msg, r["event_type"], _payload(r["payload"]), run, str(r["ts"]))

    # Research counts only annotate a window where the fleet itself was
    # looking for targets — never create a message on their own (a stopped
    # fleet must not keep "reporting" the global hourly research).
    # One batch per window — the LATEST one in it (two hourly batches in a
    # window must not read as doubled counts).
    latest_batch: dict[str, tuple[str, str]] = {}
    for th in theses:
        ts = _parse_ts(th.get("created_at"))
        if ts is None:
            continue
        key = cycle_start(ts).strftime(TS_FMT)
        stamp = (str(th.get("created_at")), str(th.get("batch_id")))
        if key not in latest_batch or stamp > latest_batch[key]:
            latest_batch[key] = stamp
    for th in theses:
        ts = _parse_ts(th.get("created_at"))
        if ts is None:
            continue
        key = cycle_start(ts).strftime(TS_FMT)
        msg = buckets.get(key)
        if msg is None or not _targets_active(msg):
            continue
        if str(th.get("batch_id")) != latest_batch[key][1]:
            continue
        if scope is not None and th.get("market") not in scope:
            continue
        rows = msg["targets"]["research"]
        market = th.get("market") or "?"
        row = next((x for x in rows if x["market"] == market), None)
        if row is None:
            row = {"market": market, "long": 0, "short": 0}
            rows.append(row)
        direction = (th.get("direction") or "").lower()
        if direction in ("long", "short"):
            row[direction] += 1

    out = [m for _, m in sorted(buckets.items(), reverse=True) if not _empty(m)][:limit]
    pfloor = None
    if partial_floors:
        pts = _parse_ts(max(partial_floors))
        pfloor = cycle_start(pts).strftime(TS_FMT) if pts else None
    for m in out:
        _trim(m)
        m["partial"] = bool(partial_all or (pfloor is not None and m["start"] <= pfloor))
    return out


def localize_feed(messages: list[dict], lang: str) -> list[dict]:
    """Free text (desk reports, skip/drop reasons) in the reader's language —
    cache-only, English on a miss, never blocking (same contract as the
    desk-cycles and outlook panels)."""
    import market_i18n
    if market_i18n.normalize_lang(lang) == "en":
        return messages
    slots: list[tuple[dict, str]] = []
    texts: list[str] = []
    for m in messages:
        for item in m["targets"]["dropped"] + m["targets"]["skipped"]:
            if item.get("reason"):
                slots.append((item, "reason")); texts.append(item["reason"])
        for row in m["decisions"]["runs"]:
            if row.get("report"):
                slots.append((row, "report")); texts.append(row["report"])
    if texts:
        for (container, key), value in zip(slots, market_i18n.localize_texts(texts, lang)):
            container[key] = value
    return messages
