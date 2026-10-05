"""Trading Runs (Plan 10) — lifecycle state machine for AI auto-trading runs.

A run is a DATABASE ROW, never an in-memory task: it survives deploys and
crashes by construction. This module owns row CRUD, strict condition
validation, state transitions, exclusivity, and the run_events journal
writes that ride each transition's transaction. No loop code lives here
(the scheduler is tasks.trading_run_loop, Phase 2).

Lifecycle:

    draft -> armed -> running <-> paused -> stopping -> stopped
                         `--------------------------------^
    (stopped with status_reason='positions_held' is the explicit terminal
     for a flatten that stays blocked — a stop can never wedge in 'stopping')

Conventions this module deliberately enforces (Plan 10 verification round):
  * All timestamps are exactly "%Y-%m-%dT%H:%M:%SZ" — the codebase has a
    second, microseconds ISO format, and lexicographic comparison across the
    two mis-orders at the same second (fatal for claim_expires_at).
  * Start/stop condition JSON is validated STRICTLY and malformed input
    REJECTS — the opposite of schedule.in_window's fail-open convention,
    because a start condition that silently degrades to "start now" moves
    money.
  * Exclusivity (one active run per agent+market+symbol) is a real UNIQUE
    constraint on active_key, not a check-then-insert (which races under
    concurrent starts).
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from database import begin_write_transaction, get_db_connection
import markets
import trend_accounts

logger = logging.getLogger(__name__)

TS_FMT = "%Y-%m-%dT%H:%M:%SZ"

VALID_RUN_MARKETS = markets.automatable_markets()
VALID_MARKET_TYPES = ("spot", "futures")

STATUS_DRAFT = "draft"
STATUS_ARMED = "armed"
STATUS_RUNNING = "running"
STATUS_PAUSED = "paused"
STATUS_STOPPING = "stopping"
STATUS_STOPPED = "stopped"

ACTIVE_STATUSES = (STATUS_ARMED, STATUS_RUNNING, STATUS_PAUSED, STATUS_STOPPING)

# from -> allowed targets. Every write goes through _transition().
_TRANSITIONS = {
    STATUS_DRAFT: {STATUS_ARMED, STATUS_RUNNING},
    STATUS_ARMED: {STATUS_RUNNING, STATUS_STOPPED},
    STATUS_RUNNING: {STATUS_PAUSED, STATUS_STOPPING, STATUS_STOPPED},
    STATUS_PAUSED: {STATUS_RUNNING, STATUS_STOPPING, STATUS_STOPPED},
    STATUS_STOPPING: {STATUS_STOPPED},
    STATUS_STOPPED: set(),
}

START_TYPES = ("manual", "at_time", "window", "price_cross")
STOP_KEYS = ("at_time", "horizon_until", "max_loss_usd",
             "profit_target_usd", "max_trades",
             "price_cross", "trail")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime(TS_FMT)


def _parse_ts(value: str) -> datetime:
    """Strict parse of the pinned timestamp format (raises ValueError)."""
    return datetime.strptime(value, TS_FMT).replace(tzinfo=timezone.utc)


# ── condition validation (strict; malformed REJECTS) ──────────────────────

def _validate_price_cross(obj: Any) -> dict:
    if not isinstance(obj, dict):
        raise ValueError("price_cross must be an object")
    direction = obj.get("direction")
    price = obj.get("price")
    if direction not in ("above", "below"):
        raise ValueError("price_cross.direction must be 'above' or 'below'")
    if not isinstance(price, (int, float)) or isinstance(price, bool) or price <= 0:
        raise ValueError("price_cross.price must be a positive number")
    extra = set(obj) - {"direction", "price"}
    if extra:
        raise ValueError(f"price_cross has unknown keys: {sorted(extra)}")
    return {"direction": direction, "price": float(price)}


def validate_start_condition(obj: Any) -> dict:
    """Normalize/validate a start condition. Malformed input raises ValueError
    — a broken start condition must never default to 'start now'."""
    if obj is None:
        return {"type": "manual"}
    if not isinstance(obj, dict):
        raise ValueError("start_condition must be an object")
    ctype = obj.get("type")
    if ctype not in START_TYPES:
        raise ValueError(f"start_condition.type must be one of {START_TYPES}")
    if ctype == "manual":
        if set(obj) - {"type"}:
            raise ValueError("manual start takes no extra keys")
        return {"type": "manual"}
    if ctype == "at_time":
        at = obj.get("at")
        if not isinstance(at, str):
            raise ValueError("at_time start requires 'at' (ISO-8601 UTC, e.g. 2026-07-20T00:00:00Z)")
        try:
            _parse_ts(at)
        except ValueError:
            raise ValueError(f"at must match {TS_FMT}")
        if at <= _now_iso():
            raise ValueError("at_time start must be in the future")
        return {"type": "at_time", "at": at}
    if ctype == "window":
        from schedule import parse_schedule
        sched = obj.get("schedule")
        if not isinstance(sched, dict):
            raise ValueError("window start requires 'schedule' object")
        parsed = parse_schedule(sched)  # raises ValueError on malformed
        if parsed is None:
            raise ValueError("window start schedule must not be empty")
        return {"type": "window", "schedule": parsed}
    # price_cross
    return {"type": "price_cross", **_validate_price_cross({
        "direction": obj.get("direction"), "price": obj.get("price")})}


def _max_run_loss_ceiling() -> float:
    """Per-run max_loss ceiling in USD (desk-adopted 2026-07-31, item I2).

    0 = OFF, so this ships dark like every other money-path change — behaviour
    is byte-identical until a deliberate flip. When >0, a run's max_loss_usd is
    clamped DOWN to it at validation, so no single run can risk more than the
    ceiling. Only ever reduces, and only NEW runs (existing rows keep their
    config). Deliberate flip: RUN_MAX_LOSS_CEILING_USD=1000."""
    import os
    try:
        return max(0.0, float(os.getenv("RUN_MAX_LOSS_CEILING_USD", "0") or 0))
    except ValueError:
        return 0.0


def validate_stop_conditions(obj: Any) -> dict:
    """Normalize/validate stop conditions. Empty dict is allowed (per-run
    safety rails are layered in separately)."""
    if obj is None:
        return {}
    if not isinstance(obj, dict):
        raise ValueError("stop_conditions must be an object")
    extra = set(obj) - set(STOP_KEYS)
    if extra:
        raise ValueError(f"stop_conditions has unknown keys: {sorted(extra)}")
    out: dict = {}
    at = obj.get("at_time")
    if at is not None:
        if not isinstance(at, str):
            raise ValueError("stop at_time must be a string")
        try:
            _parse_ts(at)
        except ValueError:
            raise ValueError(f"stop at_time must match {TS_FMT}")
        out["at_time"] = at
    # horizon_until (2026-07-30): the desk authors `horizon_hours` on every
    # full-path order and NOTHING read it — prod run 825 declared a 72-hour
    # plan, was re-decided 30 minutes later, and sold the exact low of its own
    # price series. Stored here rather than in a new column because a key the
    # validator does not whitelist is a SILENT no-op, and this file is where
    # that list lives.
    hz = obj.get("horizon_until")
    if hz is not None:
        if not isinstance(hz, str):
            raise ValueError("horizon_until must be a string")
        try:
            _parse_ts(hz)
        except ValueError:
            raise ValueError(f"horizon_until must match {TS_FMT}")
        out["horizon_until"] = hz
    for key in ("max_loss_usd", "profit_target_usd"):
        v = obj.get(key)
        if v is not None:
            if not isinstance(v, (int, float)) or isinstance(v, bool) or v <= 0:
                raise ValueError(f"{key} must be a positive number")
            out[key] = float(v)
    # I2 (2026-07-31): clamp max_loss_usd DOWN to the per-run ceiling so no
    # single run can drive the book the way the $1.3k–$2.6k runs did. Off by
    # default; only reduces.
    _ceiling = _max_run_loss_ceiling()
    if _ceiling > 0 and out.get("max_loss_usd", 0.0) > _ceiling:
        out["max_loss_usd"] = _ceiling
    mt = obj.get("max_trades")
    if mt is not None:
        if not isinstance(mt, int) or isinstance(mt, bool) or mt <= 0:
            raise ValueError("max_trades must be a positive integer")
        out["max_trades"] = mt
    pc = obj.get("price_cross")
    if pc is not None:
        out["price_cross"] = _validate_price_cross(pc)
    tr = obj.get("trail")
    if tr is not None:
        if not isinstance(tr, dict):
            raise ValueError("trail must be an object")
        act = tr.get("activate_usd")
        gb = tr.get("giveback_frac")
        if not isinstance(act, (int, float)) or isinstance(act, bool) or act <= 0:
            raise ValueError("trail.activate_usd must be a positive number")
        if not isinstance(gb, (int, float)) or isinstance(gb, bool) or not (0 < gb < 1):
            raise ValueError("trail.giveback_frac must be between 0 and 1")
        out["trail"] = {"activate_usd": float(act), "giveback_frac": float(gb)}
        # Optional fee-aware ratchet: above tighten_usd of peak P&L the
        # giveback compresses to tighten_giveback_frac. Both must be present
        # and the tightened band must actually be tighter, or neither is
        # stored — a half-specified ratchet would silently do nothing.
        t_at = tr.get("tighten_usd")
        t_gb = tr.get("tighten_giveback_frac")
        if t_at is not None or t_gb is not None:
            if not isinstance(t_at, (int, float)) or isinstance(t_at, bool) or t_at <= 0:
                raise ValueError("trail.tighten_usd must be a positive number")
            if not isinstance(t_gb, (int, float)) or isinstance(t_gb, bool) \
                    or not (0 < t_gb < 1):
                raise ValueError(
                    "trail.tighten_giveback_frac must be between 0 and 1")
            if t_gb >= gb:
                raise ValueError(
                    "trail.tighten_giveback_frac must be tighter than giveback_frac")
            out["trail"]["tighten_usd"] = float(t_at)
            out["trail"]["tighten_giveback_frac"] = float(t_gb)
    return out


def check_tighten_only(old: dict, new: dict) -> None:
    """Raise ValueError unless `new` only tightens `old`. Removing a condition
    loosens; adding one tightens; numeric bounds may only move toward an
    earlier stop. price_cross is not editable while running (its tightness is
    unknowable without a market read)."""
    for key in old:
        if key not in new:
            raise ValueError(f"removing stop condition '{key}' would loosen the stop")
    if "at_time" in old and new["at_time"] > old["at_time"]:
        raise ValueError("stop at_time may only move earlier")
    for key in ("max_loss_usd", "profit_target_usd", "max_trades"):
        if key in old and new[key] > old[key]:
            raise ValueError(f"{key} may only decrease")
    if "price_cross" in old and new["price_cross"] != old["price_cross"]:
        raise ValueError("price_cross stop cannot be changed while the run is active")
    if "price_cross" in new and "price_cross" not in old:
        raise ValueError("price_cross stop cannot be added while the run is active")


# ── run_events journal (transition events ride the SAME transaction) ──────

def _emit_event(cursor, run_id: int, event_type: str, payload: dict) -> int:
    """Insert a run_events row inside the caller's open transaction and bump
    trading_runs.last_event_seq in the same transaction (crash-safe seq
    recovery: a reclaiming worker re-reads last_event_seq, never a stale
    in-memory counter)."""
    # INCREMENT FIRST, then read. The UPDATE takes the row lock, so a second
    # writer on the same run blocks here until this transaction commits.
    #
    # WHY (2026-08-07). This used to SELECT the counter, add one, and INSERT —
    # a plain read with no lock. Two writers on one run read the same value and
    # collided on the unique index:
    #
    #     (1062, "Duplicate entry '981-191' for key uq_run_events_run_seq")
    #     (1062, "Duplicate entry '983-784' for key uq_run_events_run_seq")
    #
    # Twice in one session, in different containers, and the second came only
    # after the fleet grew from 6 runs to 10 — two writers per run (the cycle,
    # and the arm executor firing BETWEEN cycles) make it likelier the busier
    # the desk gets. Impact was contained both times because the loser was a
    # fail-soft telemetry row and trades ride their own transaction — 73 trade
    # events against 73 signals, no seq gaps on any run — but the collision was
    # luck about WHICH writer lost, not design.
    #
    # UPDATE-then-SELECT is dialect-neutral: it takes a row lock on both MySQL
    # and SQLite, unlike `SELECT ... FOR UPDATE`, which SQLite cannot parse.
    cursor.execute(
        "UPDATE trading_runs SET last_event_seq = COALESCE(last_event_seq, 0) + 1"
        " WHERE id = ?", (run_id,))
    cursor.execute("SELECT last_event_seq FROM trading_runs WHERE id = ?", (run_id,))
    row = cursor.fetchone()
    seq = int(row["last_event_seq"]) if row and row["last_event_seq"] else 1
    cursor.execute(
        """INSERT INTO run_events (run_id, seq, event_type, ts, payload)
           VALUES (?, ?, ?, ?, ?)""",
        (run_id, seq, event_type, _now_iso(), json.dumps(payload)),
    )
    return seq


def emit_telemetry_event(run_id: int, event_type: str, payload: dict) -> Optional[int]:
    """Fail-soft standalone emitter for NON-critical telemetry (equity
    snapshots, gate skips). Trade and state-change events must instead ride
    their own transaction via _emit_event — a committed trade may never be
    missing from the journal."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        begin_write_transaction(cursor)
        seq = _emit_event(cursor, run_id, event_type, payload)
        conn.commit()
        return seq
    except Exception:  # noqa: BLE001 — telemetry must never break trading paths
        logger.warning("emit_telemetry_event failed (run %s, %s)", run_id, event_type,
                       exc_info=True)
        try:
            if conn is not None:
                conn.rollback()
        except Exception:  # noqa: BLE001
            pass
        return None
    finally:
        try:
            if conn is not None:
                conn.close()
        except Exception:  # noqa: BLE001
            pass


# ── row access ─────────────────────────────────────────────────────────────

def get_run(run_id: int, agent_id: int) -> Optional[dict]:
    """Fetch a run WITH the ownership predicate — every read path goes
    through agent_id (cross-tenant reads 404 at the route layer)."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM trading_runs WHERE id = ? AND agent_id = ?",
                       (run_id, agent_id))
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_run_user_scoped(run_id: int, agent_id: int) -> Optional[dict]:
    """The run when it belongs to the calling agent OR to a sibling agent of
    the same linked user. Fleets are user-scoped (PR #36) and the fleet
    monitor opens member runs from any of the user's agents, so the run
    read/control surface follows the same boundary. Unlinked agents stay
    strictly agent-scoped (user_id NULL never matches another NULL)."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """SELECT r.* FROM trading_runs r
               JOIN agents owner ON owner.id = r.agent_id
               JOIN agents caller ON caller.id = ?
               WHERE r.id = ? AND (r.agent_id = caller.id
                     OR (owner.user_id IS NOT NULL
                         AND owner.user_id = caller.user_id))""",
            (agent_id, run_id))
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_runs_user_scoped(agent_id: int, limit: int = 50) -> list[dict]:
    """list_runs widened to every agent of the caller's linked user — the
    /automation grid (and its WS subscriptions) must include fleet member
    runs that a sibling agent's fleet created."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """SELECT r.* FROM trading_runs r
               JOIN agents owner ON owner.id = r.agent_id
               JOIN agents caller ON caller.id = ?
               WHERE r.agent_id = caller.id
                  OR (owner.user_id IS NOT NULL
                      AND owner.user_id = caller.user_id)
               ORDER BY r.id DESC LIMIT ?""",
            (agent_id, max(1, min(limit, 200))))
        return [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()


def filter_key(market_type: Optional[str], cfg: dict) -> str:
    """Short stable digest of what makes two runs on one symbol genuinely
    different strategies: the instrument type plus the decision parameters
    (how often it looks, how sure it must be, which model decides).

    Runs matching on all four are duplicates — same symbol, same behaviour,
    two books racing the same signal — and are still refused. Differ in any
    one and both may run: they hold separate `positions` rows (run_id) so
    P&L, stops and flatten stay attributable per run.
    """
    parts = (
        (market_type or "spot").strip().lower(),
        str(int(cfg.get("interval_minutes") or 60)),
        f"{float(cfg.get('min_confidence') or 0):.4f}",
        (cfg.get("provider") or "-").strip().lower(),
    )
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:10]


def is_futures_book(market: Optional[str], market_type: Optional[str]) -> bool:
    """Whether a run's positions behave as a futures book — a 'sell' with no
    long open opens a short rather than being a no-op.

    Two independent axes converge here, which is exactly the naming collision
    plan 13 phase 3 called out. `market_type` ('spot' | 'futures') separates
    crypto spot from crypto perpetuals and predates the CME market entirely;
    `market` now has a genuinely-futures member of its own. Either one makes
    the book short-capable, so this is a named predicate rather than a string
    compare scattered across the engine.
    """
    return ((market_type or "spot").strip().lower() == "futures"
            or (market or "").strip().lower() == "futures")


def _active_key(agent_id: int, market: str, symbol: str, fkey: str) -> str:
    return f"{agent_id}:{market}:{symbol}:{fkey}"


def run_filter_key(run: dict) -> str:
    """filter_key() for a run row, tolerating an unparseable snapshot."""
    try:
        cfg = json.loads(run.get("config_snapshot_json") or "{}")
    except Exception:  # noqa: BLE001
        cfg = {}
    return filter_key(run.get("market_type"), cfg)


# ── lifecycle operations ───────────────────────────────────────────────────

def create_run(agent_id: int, settings: dict, start_condition: dict,
               stop_conditions: dict, stop_flatten: bool,
               fleet_id: Optional[int] = None, created_via: str = "user") -> int:
    """Insert a draft run. `settings` is the already-validated config payload
    (max_bet_usd, run_budget_usd, interval_minutes, min_confidence, provider,
    lang, leverage) — snapshotted verbatim at start time.

    Plan 14: fleet_id/created_via are columns ON THE INSERT — a separate
    stamp step would leave a crash window producing unattributed drafts."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        begin_write_transaction(cursor)
        cursor.execute(
            """INSERT INTO trading_runs
               (agent_id, symbol, market, market_type, status,
                config_snapshot_json, start_condition_json, stop_conditions_json,
                stop_flatten, fleet_id, created_via, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (agent_id, settings["symbol"], settings["market"], settings["market_type"],
             STATUS_DRAFT, json.dumps(settings), json.dumps(start_condition),
             json.dumps(stop_conditions), 1 if stop_flatten else 0,
             fleet_id, created_via, _now_iso()),
        )
        run_id = cursor.lastrowid
        _emit_event(cursor, run_id, "run_status",
                    {"from": None, "to": STATUS_DRAFT, "reason": "created"})
        conn.commit()
        return run_id
    finally:
        conn.close()


def update_draft_run(run_id: int, agent_id: int, settings: dict,
                     start_condition: dict, stop_conditions: dict,
                     stop_flatten: bool) -> None:
    """Replace a draft's configuration wholesale.

    Draft-only by design. A draft has never traded: no positions carry its
    run_id, no active_key reserves its slot, so every field is still free to
    change and there is nothing to reconcile. The moment a run starts, the
    same edit would be rewriting the terms of a book that is already open —
    which is why an active run gets only the tighten-only stop-conditions
    endpoint instead.

    Editing exists so that hitting the exclusivity refusal at start does not
    cost the user the draft: they change the instrument type, interval,
    confidence or provider here and start it alongside the existing run.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        begin_write_transaction(cursor)
        cursor.execute("SELECT status FROM trading_runs WHERE id = ? AND agent_id = ?",
                       (run_id, agent_id))
        row = cursor.fetchone()
        if not row:
            raise LookupError("run not found")
        status = dict(row)["status"]
        if status != STATUS_DRAFT:
            raise ValueError(f"only a draft run can be edited (status={status})")

        cursor.execute(
            """UPDATE trading_runs
               SET symbol = ?, market = ?, market_type = ?,
                   config_snapshot_json = ?, start_condition_json = ?,
                   stop_conditions_json = ?, stop_flatten = ?
               WHERE id = ? AND agent_id = ? AND status = ?""",
            (settings["symbol"], settings["market"], settings["market_type"],
             json.dumps(settings), json.dumps(start_condition),
             json.dumps(stop_conditions), 1 if stop_flatten else 0,
             run_id, agent_id, STATUS_DRAFT),
        )
        if cursor.rowcount != 1:
            # Started or deleted between the SELECT and here.
            raise ValueError("run changed concurrently — retry")
        _emit_event(cursor, run_id, "run_config",
                    {"reason": "edited", "symbol": settings["symbol"],
                     "market": settings["market"],
                     "market_type": settings["market_type"]})
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:  # noqa: BLE001
            pass
        raise
    finally:
        conn.close()


class StartConflict(Exception):
    """Raised when exclusivity or a conflicting writer blocks a start.
    `conflicts` (when present) is the list_start_conflicts() dict so the API
    can tell the client exactly what is resolvable."""

    def __init__(self, message: str, conflicts: Optional[dict] = None):
        super().__init__(message)
        self.conflicts = conflicts or {}


def list_start_conflicts(cursor, agent_id: int, market: str, symbol: str) -> dict:
    """User-resolvable conflicts blocking a run start on agent+market+symbol:
    the open position in the UNOWNED book (if any) and enabled auto-executing
    automation rules. Shape: {"position": {...}|None, "rule_ids": [int, ...]}.

    `run_id IS NULL` is deliberate: positions opened by other runs are their
    own rows and never commingle with this one, so they are not a conflict.
    Only the book that manual signals and automation rules write is."""
    cursor.execute(
        """SELECT id, side, quantity, entry_price, current_price FROM positions
           WHERE agent_id = ? AND market = ? AND symbol = ? AND quantity != 0
             AND run_id IS NULL""",
        (agent_id, market, symbol),
    )
    row = cursor.fetchone()
    position = None
    if row:
        row = dict(row)
        position = {
            "id": row["id"], "side": row["side"],
            "quantity": float(row["quantity"]),
            "entry_price": float(row["entry_price"] or 0),
            "current_price": (float(row["current_price"])
                              if row["current_price"] is not None else None),
        }
    cursor.execute(
        """SELECT id FROM automation_configs
           WHERE agent_id = ? AND market = ? AND symbol = ?
             AND enabled = 1 AND auto_execute = 1""",
        (agent_id, market, symbol),
    )
    rule_ids = [r["id"] for r in cursor.fetchall()]
    return {"position": position, "rule_ids": rule_ids}


def resolve_start_conflicts(run_id: int, agent_id: int) -> dict:
    """One-click, explicitly-consented resolution of a draft run's start
    conflicts: disable enabled auto-executing automation rules on the tuple
    FIRST (so nothing re-opens the book), then close the shared open position
    at the current mark via the canonical simulator exit path. The position is
    closed into the shared ledger (no run attribution — it predates the run).
    Returns {"closed_position": bool, "disabled_rule_ids": [...]}."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM trading_runs WHERE id = ? AND agent_id = ?",
                       (run_id, agent_id))
        run = cursor.fetchone()
        if not run:
            raise LookupError("run not found")
        run = dict(run)
        if run["status"] != STATUS_DRAFT:
            raise ValueError(f"only a draft run can start (status={run['status']})")
        # Plan 32: "resolving" would close the trend rule's own position.
        if trend_accounts.is_trend_account(agent_id, cursor):
            raise EntitlementDenied(trend_accounts.NO_RUNS)
        market, symbol = run["market"], run["symbol"]
        conflicts = list_start_conflicts(cursor, agent_id, market, symbol)
    finally:
        conn.close()

    disabled: list[int] = []
    if conflicts["rule_ids"]:
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            begin_write_transaction(cursor)
            placeholders = ",".join("?" * len(conflicts["rule_ids"]))
            cursor.execute(
                f"""UPDATE automation_configs SET enabled = 0
                    WHERE id IN ({placeholders}) AND agent_id = ?""",
                (*conflicts["rule_ids"], agent_id),
            )
            conn.commit()
            disabled = list(conflicts["rule_ids"])
        finally:
            conn.close()

    closed = False
    pos = conflicts["position"]
    if pos:
        price = pos["current_price"]
        if price is None:
            try:
                from price_fetcher import get_price_from_market
                price = get_price_from_market(symbol, None, market)
            except Exception:  # noqa: BLE001
                price = None
        if price is None:
            raise StartConflict(
                "cannot close the open position — no current price for "
                f"{symbol} ({market})", conflicts)
        from automation import execute_paper_trade
        qty = pos["quantity"]
        side = "cover" if qty < 0 else "sell"
        signal_id, skip = execute_paper_trade(
            agent_id, symbol, market, side, abs(qty), float(price),
            content=f"position closed to start trading run #{run_id}")
        if signal_id:
            closed = True
        elif skip in ("no long position to sell", "no short position to cover"):
            closed = True  # already flat (concurrent close) — that's the goal
        else:
            raise StartConflict(
                f"could not close the open position: {skip}", conflicts)

    if disabled or closed:
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            begin_write_transaction(cursor)
            _emit_event(cursor, run_id, "conflicts_resolved",
                        {"closed_position": closed, "disabled_rule_ids": disabled})
            conn.commit()
        finally:
            conn.close()
    return {"closed_position": closed, "disabled_rule_ids": disabled}


class EntitlementDenied(Exception):
    """Raised when the owning user's plan does not allow the start (403)."""


def start_run(run_id: int, agent_id: int) -> dict:
    """draft -> armed|running. Enforces, inside one write transaction:
      1. DB-level exclusivity — active_key UNIQUE on
         agent+market+symbol+filter_key. Several runs may share a symbol as
         long as they are different strategies (see filter_key); an exact
         duplicate collides here, as do concurrent double-starts;
      2. no pre-existing position in the *unowned* book on the tuple (manual
         or rule-owned; a run never adopts a book it did not open — other
         runs' positions are their own rows and do not block);
      3. no enabled auto-executing automation rule on the tuple (it trades
         the unowned book this run would otherwise have to reconcile with).
    Manual start goes straight to running; every other start condition arms.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        begin_write_transaction(cursor)
        cursor.execute("SELECT * FROM trading_runs WHERE id = ? AND agent_id = ?",
                       (run_id, agent_id))
        run = cursor.fetchone()
        if not run:
            raise LookupError("run not found")
        run = dict(run)
        if run["status"] != STATUS_DRAFT:
            raise ValueError(f"only a draft run can start (status={run['status']})")
        # Plan 32: a dedicated trend account is traded by the trend rule only.
        if trend_accounts.is_trend_account(agent_id, cursor):
            raise EntitlementDenied(trend_accounts.NO_RUNS)

        # Plan 10 D9: server-side tier gate (env-gated until PLAN_LIMITS is
        # confirmed). Same gate family as the automation engine's — the two
        # engines must never diverge on entitlements.
        # Plan 14: serialize the count-then-start per USER first. On MySQL,
        # plain BEGIN gives REPEATABLE READ over disjoint rows, so two
        # concurrent starts at limit−1 both count active=k and both commit —
        # the FOR UPDATE on the owning user row is the serialization point.
        # SQLite's BEGIN IMMEDIATE already serializes all writers (no-op).
        from database import using_mysql
        if using_mysql():
            cursor.execute(
                "SELECT u.id FROM users u JOIN agents a ON a.user_id = u.id "
                "WHERE a.id = ? FOR UPDATE", (agent_id,))
        from entitlements import check_run_start
        try:
            cfg = json.loads(run.get("config_snapshot_json") or "{}")
        except Exception:  # noqa: BLE001
            cfg = {}
        deny = check_run_start(cursor, agent_id, float(cfg.get("max_bet_usd") or 0))
        if deny:
            raise EntitlementDenied(deny)

        market, symbol = run["market"], run["symbol"]
        conflicts = list_start_conflicts(cursor, agent_id, market, symbol)
        if conflicts["position"]:
            raise StartConflict(
                "an open position already exists for this symbol outside any run — "
                "close it first (runs never adopt a book they did not open; "
                "attribution would be wrong)",
                conflicts)
        if conflicts["rule_ids"]:
            raise StartConflict(
                f"auto-executing automation rule #{conflicts['rule_ids'][0]} targets "
                "the same symbol — disable it first", conflicts)

        start_condition = json.loads(run["start_condition_json"] or '{"type":"manual"}')
        target = STATUS_RUNNING if start_condition.get("type") == "manual" else STATUS_ARMED
        now = _now_iso()
        try:
            cursor.execute(
                """UPDATE trading_runs
                   SET status = ?, status_reason = NULL, active_key = ?, started_at = ?
                   WHERE id = ? AND status = ?""",
                (target, _active_key(agent_id, market, symbol, run_filter_key(run)),
                 now, run_id, STATUS_DRAFT),
            )
        except Exception as exc:  # noqa: BLE001 — UNIQUE(active_key) collision
            raise StartConflict(
                "another active run on this symbol already uses these exact settings "
                "— change the instrument type, interval, minimum confidence or AI "
                "provider to run a second strategy alongside it") from exc
        if cursor.rowcount != 1:
            raise StartConflict("run was started concurrently")
        _emit_event(cursor, run_id, "run_status",
                    {"from": STATUS_DRAFT, "to": target, "reason": "start"})
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:  # noqa: BLE001
            pass
        raise
    finally:
        conn.close()
    return get_run(run_id, agent_id) or {}


def _transition(run_id: int, agent_id: int, allowed_from: tuple, target: str,
                reason: str, clear_active_key: bool = False,
                extra_sets: str = "", extra_args: tuple = ()) -> dict:
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        begin_write_transaction(cursor)
        cursor.execute("SELECT * FROM trading_runs WHERE id = ? AND agent_id = ?",
                       (run_id, agent_id))
        run = cursor.fetchone()
        if not run:
            raise LookupError("run not found")
        run = dict(run)
        if run["status"] not in allowed_from:
            raise ValueError(
                f"cannot go {run['status']} -> {target} (allowed from {allowed_from})")
        if target not in _TRANSITIONS[run["status"]]:
            raise ValueError(f"illegal transition {run['status']} -> {target}")
        sets = "status = ?, status_reason = ?"
        args: list = [target, reason]
        if clear_active_key:
            sets += ", active_key = NULL, stopped_at = ?"
            args.append(_now_iso())
            # Release any position the run still holds (stop-with-hold) back to
            # the unowned book. run_id on a position means "an ACTIVE run owns
            # this"; leaving a finished run's stamp on it would hide the
            # position from manual selling and from the automation rules,
            # since both read `run_id IS NULL`.
            cursor.execute(
                "UPDATE positions SET run_id = NULL WHERE run_id = ? AND agent_id = ?",
                (run_id, agent_id))
        if extra_sets:
            sets += ", " + extra_sets
            args.extend(extra_args)
        cursor.execute(f"UPDATE trading_runs SET {sets} WHERE id = ? AND status = ?",
                       (*args, run_id, run["status"]))
        if cursor.rowcount != 1:
            raise ValueError("run changed concurrently — retry")
        _emit_event(cursor, run_id, "run_status",
                    {"from": run["status"], "to": target, "reason": reason})
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:  # noqa: BLE001
            pass
        raise
    finally:
        conn.close()
    return get_run(run_id, agent_id) or {}


def pause_run(run_id: int, agent_id: int, reason: str = "user_pause",
              paused_marker: Optional[str] = None) -> dict:
    """Pause gates ENTRIES only — stop conditions and the clock keep
    evaluating every scheduler scan (Plan 10 D3).

    Plan 14: `paused_marker` lands in the paused_reason COLUMN (not
    status_reason) so marker-disciplined resumes (master hold, drawdown
    warning) can restore exactly the set they paused — the engine's own
    stop_eval_failed auto-resume filter is the precedent."""
    if paused_marker:
        return _transition(run_id, agent_id, (STATUS_RUNNING,), STATUS_PAUSED, reason,
                           extra_sets="paused_reason = ?", extra_args=(paused_marker,))
    return _transition(run_id, agent_id, (STATUS_RUNNING,), STATUS_PAUSED, reason)


def resume_run(run_id: int, agent_id: int) -> dict:
    return _transition(run_id, agent_id, (STATUS_PAUSED,), STATUS_RUNNING, "user_resume",
                       extra_sets="paused_reason = NULL", extra_args=())


def request_stop(run_id: int, agent_id: int, flatten: bool,
                 reason: str = "user_stop") -> dict:
    """Stop a run. An armed run (no entries yet) stops immediately. A
    running/paused run with a run-owned open position moves to `stopping`
    (the scheduler completes the flatten, Phase 3); with nothing to flatten
    it stops immediately.

    `reason` defaults to user_stop, which is what a Stop button or an API
    stop request means. Machine-initiated stops MUST pass their own reason:
    this function is also the fleet's stop path, and 59 of 61 "user_stop"
    runs on prod were fleet stop-alls and rotations, not anyone clicking
    anything. Anything new here needs a REPLACE_* classification in
    fleet_planner and an entry in the notifications reason table."""
    run = get_run(run_id, agent_id)
    if not run:
        raise LookupError("run not found")
    if run["status"] == STATUS_ARMED:
        return _transition(run_id, agent_id, (STATUS_ARMED,), STATUS_STOPPED,
                           reason, clear_active_key=True)
    if run["status"] in (STATUS_RUNNING, STATUS_PAUSED):
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT id FROM positions
                   WHERE agent_id = ? AND market = ? AND symbol = ?
                     AND run_id = ? AND quantity != 0""",
                (agent_id, run["market"], run["symbol"], run_id),
            )
            has_position = cursor.fetchone() is not None
        finally:
            conn.close()
        if has_position:
            return _transition(
                run_id, agent_id, (STATUS_RUNNING, STATUS_PAUSED), STATUS_STOPPING,
                reason, extra_sets="stop_flatten = ?, stopped_at = ?",
                extra_args=(1 if flatten else 0, _now_iso()))
        return _transition(run_id, agent_id, (STATUS_RUNNING, STATUS_PAUSED),
                           STATUS_STOPPED, reason, clear_active_key=True)
    raise ValueError(f"cannot stop a {run['status']} run")


def update_stop_conditions(run_id: int, agent_id: int, new_conditions: dict) -> dict:
    """Free edit while draft; TIGHTEN-ONLY while active (a stop is a safety
    device — mid-run edits may only make it fire earlier)."""
    validated = validate_stop_conditions(new_conditions)
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        begin_write_transaction(cursor)
        cursor.execute("SELECT * FROM trading_runs WHERE id = ? AND agent_id = ?",
                       (run_id, agent_id))
        run = cursor.fetchone()
        if not run:
            raise LookupError("run not found")
        run = dict(run)
        if run["status"] == STATUS_STOPPED:
            raise ValueError("run is stopped")
        if run["status"] != STATUS_DRAFT:
            old = json.loads(run["stop_conditions_json"] or "{}")
            check_tighten_only(old, validated)
        cursor.execute(
            "UPDATE trading_runs SET stop_conditions_json = ? WHERE id = ?",
            (json.dumps(validated), run_id),
        )
        if run["status"] != STATUS_DRAFT:
            _emit_event(cursor, run_id, "run_status",
                        {"from": run["status"], "to": run["status"],
                         "reason": "stop_conditions_tightened"})
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:  # noqa: BLE001
            pass
        raise
    finally:
        conn.close()
    return get_run(run_id, agent_id) or {}


def delete_run(run_id: int, agent_id: int) -> None:
    """Only draft/stopped runs are deletable; their journal rows go with them."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        begin_write_transaction(cursor)
        cursor.execute(
            "SELECT status FROM trading_runs WHERE id = ? AND agent_id = ?",
            (run_id, agent_id))
        run = cursor.fetchone()
        if not run:
            raise LookupError("run not found")
        if run["status"] not in (STATUS_DRAFT, STATUS_STOPPED):
            raise ValueError("only draft or stopped runs can be deleted")
        cursor.execute("DELETE FROM run_events WHERE run_id = ?", (run_id,))
        cursor.execute("DELETE FROM run_reports WHERE run_id = ?", (run_id,))
        cursor.execute("DELETE FROM trading_runs WHERE id = ? AND agent_id = ?",
                       (run_id, agent_id))
        conn.commit()
    finally:
        conn.close()


def list_runs(agent_id: int, limit: int = 50) -> list[dict]:
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM trading_runs WHERE agent_id = ? ORDER BY id DESC LIMIT ?",
            (agent_id, max(1, min(limit, 200))))
        return [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()


def list_events(run_id: int, agent_id: int, after_seq: int = 0,
                limit: int = 200) -> Optional[list[dict]]:
    """Journal replay feed (ownership-checked; None = not the caller's run)."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM trading_runs WHERE id = ? AND agent_id = ?",
                       (run_id, agent_id))
        if not cursor.fetchone():
            return None
        cursor.execute(
            """SELECT seq, event_type, ts, payload FROM run_events
               WHERE run_id = ? AND seq > ? ORDER BY seq ASC LIMIT ?""",
            (run_id, after_seq, max(1, min(limit, 500))))
        return [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()
