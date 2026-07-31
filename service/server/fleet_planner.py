"""Fleet orchestrator (Plan 14 §6) — from "user says N" to N registered runs,
kept at N until the user stops it.

A fleet NEVER trades: it is a research-consume / build / supervise envelope
over ordinary trading_runs (created in-process via trading_runs.create_run /
start_run, so exclusivity, entitlements, stops, P&L and telemetry are reused
verbatim). The LLM proposed upstream (symbol_research); everything here is
deterministic FLEET_BOUNDS clamps — the agent_planner.py philosophy one
level up.

Money-safety spine (the QA-hardened §6.3):
- allocations persisted BY THESIS KEY before any run exists; slots persist in
  fleet_slots and a replacement can never exceed its slot's original
  allocation;
- ONE marked (MTM, fail-closed) equity drives rails, funding, and dormancy;
- within a supervise pass replacements fund sequentially from recomputed
  headroom; positions_held zombies subtract from it;
- an equity-evaluation failure freezes all equity-derived mutations that tick.

State machine: draft → researching → building → active ⇄ paused → stopping →
stopped, lease-claimed exactly like runs (short committed claim transaction).
"""

from __future__ import annotations

import json
import logging
import os
import socket
from datetime import datetime, timedelta, timezone
from typing import Optional

import trading_runs
from database import begin_write_transaction, get_db_connection

logger = logging.getLogger(__name__)

TS_FMT = "%Y-%m-%dT%H:%M:%SZ"

STATUS_DRAFT = "draft"
STATUS_RESEARCHING = "researching"
STATUS_BUILDING = "building"
STATUS_ACTIVE = "active"
STATUS_PAUSED = "paused"
STATUS_STOPPING = "stopping"
STATUS_STOPPED = "stopped"

_NON_TERMINAL = (STATUS_DRAFT, STATUS_RESEARCHING, STATUS_BUILDING,
                 STATUS_ACTIVE, STATUS_PAUSED, STATUS_STOPPING)

# Risk-appetite tiers. The 종목 자동 편성 UI exposes three profit-oriented
# levels (2026-07-23, Henry: "profit is low, make 3 levels"):
#   balanced   → 안정 · Balance          (steady, small positions)
#   aggressive → 수익 · High Profit       (bigger positions, looser gate)
#   extreme    → 고위험 고수익 · Risk&High (largest positions, widest stop)
# 'stable' stays API-valid for backward compat but is no longer featured.
# NOTE: real >1× margin leverage is NOT part of these tiers — leverage is
# pinned to 1 by routes_runs (a fully-funded ledger; real isolated-margin
# leverage + liquidation is a separate deferred engine). The profit lever
# here is bet fraction of run budget + gate + stop width + cycle speed.
FLEET_BOUNDS = {
    "n_runs": (1, 25),
    "total_budget_usd": (50.0, 10_000_000.0),
    "alloc_frac_of_equal": (0.5, 2.0),           # slot ∈ [B/2N, 2B/N], Σ ≤ B
    "max_bet_frac_of_run_budget": {"stable": 0.20, "balanced": 0.30,
                                   "aggressive": 0.45, "extreme": 0.70},
    # Plan 15 P0 (2026-07-22): balanced 0.65 → 0.60. The decision LLM's
    # confidence output is quantized and pins at 0.62 (53% of observed
    # decisions), so a 0.65 gate blocked 76% of actionable calls on noise —
    # see docs/plan/15-run-ai-reading-algorithm-fix.html. P2/P3 replace the
    # scalar entirely; this is the interim mitigation.
    "min_confidence": {"stable": 0.75, "balanced": 0.60,
                       "aggressive": 0.57, "extreme": 0.55},
    "interval_minutes": {"stable": 240, "balanced": 60,
                         "aggressive": 45, "extreme": 30},
    "interval_floor_by_market": {"us-stock": 30},  # Yahoo pressure, not AV
    "interval_floor_default": 15,
    "stop_max_loss_frac": {"stable": 0.05, "balanced": 0.10,
                           "aggressive": 0.20, "extreme": 0.30},
    # Exit management (2026-07-25): the budget-scaled stop above sits ~44%
    # beyond the actual max_bet-sized position, so a loser never cuts and a
    # winner round-trips. Scale the ACTIVE stop to the position (max_bet), and
    # add a peak-tracked trailing lock (run_engine._trailing_lock_hit) that
    # banks the small, mean-reverting moves the far profit_target never reaches.
    "stop_loss_frac_of_bet": {"stable": 0.015, "balanced": 0.02,
                              "aggressive": 0.03, "extreme": 0.04},
    # Arm the lock at a floor of 0.3% of notional — but never below a fraction
    # of what the run is RISKING (trail_activate_rr × max_loss). The old
    # frac-only rule put activation at exactly 1/10th of the stop on every
    # run (arm $6.66 vs stop $66.61), so the desk banked ~$6 wins and took
    # ~$67 losses: a structure needing a 90.9% hit rate to break even, against
    # a measured 35% directional accuracy. At rr=1.0 the lock cannot arm until
    # the position is up as much as it can lose, which drops the breakeven hit
    # rate to ~55%. Reaching breakeven at 35% would need rr≈2.3, but that also
    # slashes how often the lock ever arms — raise it only with measurement.
    "trail_activate_frac_of_bet": 0.003,   # floor: 0.3% of notional
    "trail_activate_rr": 1.0,              # …and ≥ 1.0 × max_loss_usd
    # Giveback cut 0.40 → 0.20 (2026-07-26). At 40% the five prod ZEC winners
    # peaked $6.95–$27.83 and banked $1.98–$7.50: the retrace surrendered up to
    # half the peak and the 0.1%/side round trip took 44–82% of the remainder.
    "trail_giveback_frac": 0.20,           # exit on a >20% retrace from peak
    # …and compress to 15% once the peak proves it is a real winner: 3× the
    # round-trip fee on the position notional (see _trail_config).
    "trail_tighten_giveback_frac": 0.15,
    "trail_tighten_fee_multiple": 3.0,
    # Add-churn guard (2026-07-25, Fleet 17): at most N same-direction adds
    # per open position, with a cooldown between opens — averaging into a
    # loser every 45-min cycle stacked fees for no new information.
    "max_position_adds": 2,
    "add_cooldown_minutes": 90,
    # Higher tiers let winners run further before banking (× the thesis move).
    "profit_target_mult": {"stable": 1.0, "balanced": 1.0,
                           "aggressive": 1.5, "extreme": 2.0},
    # Auto leverage per tier (isolated margin). Used when the fleet does not
    # override it. Extreme trades 3× the notional for the same committed
    # margin; liquidation at entry×(1∓1/L).
    "auto_leverage": {"stable": 1.0, "balanced": 1.0,
                      "aggressive": 2.0, "extreme": 3.0},
    "profit_target_frac_bounds": (0.002, 0.50),   # thesis % / 100 clamps here
    "min_slot_funding_usd_frac": 0.5,             # dormant below B/2N
    # Fleet-level take-profit goal (2026-07-26): "when the fleet reaches my
    # target profit, bank it and start the same trading again". 1% .. 500%.
    "profit_target_goal_bounds": (0.01, 5.0),
    "churn_alert_per_day": 8,
    "equity_eval_fail_limit": 5,                  # K consecutive ⇒ pause entries
}

# Backward-compat: any risk key not in a per-tier dict falls back to balanced.
def _tier(dimension: str, risk: str):
    d = FLEET_BOUNDS[dimension]
    return d.get(risk, d["balanced"])


def _trail_config(max_bet: float, leverage: float,
                  max_loss_usd: float = 0.0) -> dict:
    """Trailing-lock config for a run sized at `max_bet` margin on `leverage`.

    activate_usd is the greater of a notional floor and trail_activate_rr ×
    max_loss_usd — the lock must not bank a win smaller than the loss the run
    is prepared to take. See the FLEET_BOUNDS note: the frac-only rule armed
    at exactly 1/10th of the stop and needed a 90.9% hit rate to break even.

    tighten_usd is the fee-aware "this is a real winner" line: the round trip
    on the position notional costs notional × 2 × TRADE_FEE_RATE, so a peak
    worth several round trips is worth protecting harder than one that merely
    armed. Above it the giveback compresses (run_engine._trailing_lock_hit)."""
    from fees import TRADE_FEE_RATE
    notional = max(0.0, float(max_bet)) * max(1.0, float(leverage or 1.0))
    round_trip_usd = notional * TRADE_FEE_RATE * 2
    activate = max(
        float(max_bet) * FLEET_BOUNDS["trail_activate_frac_of_bet"],
        max(0.0, float(max_loss_usd)) * FLEET_BOUNDS["trail_activate_rr"],
    )
    tighten = round(round_trip_usd * FLEET_BOUNDS["trail_tighten_fee_multiple"], 2)
    # The ratchet only means something above the arming line; with an RR-scaled
    # activation the fee-based tighten can land below it, which would apply the
    # tight band the instant the lock arms and defeat the point of arming late.
    tighten = max(tighten, round(activate * 1.5, 2))
    return {
        "activate_usd": round(activate, 2),
        "giveback_frac": FLEET_BOUNDS["trail_giveback_frac"],
        "tighten_usd": tighten,
        "tighten_giveback_frac": FLEET_BOUNDS["trail_tighten_giveback_frac"],
    }

def _thesis_fee_infeasible(thesis: dict) -> "str | None":
    """Reason a thesis can never pay for its own round trip, or None.

    Mirrors run_engine._fee_edge_skip exactly — same discount, same hurdle —
    but evaluated once at build instead of every cycle, because
    expected_move_pct is frozen in the config snapshot and never changes."""
    try:
        from run_engine import _fee_edge_skip
    except Exception:  # noqa: BLE001 — never block a build on an import
        return None
    skip = _fee_edge_skip(thesis.get("expected_move_pct"),
                          market=thesis.get("market"))
    return f"fee_infeasible: {skip}" if skip else None


def _expectancy_min_trades() -> int:
    """Closed trades in a bucket before its record is allowed to veto. Below
    this the sample says nothing and the bucket is presumed innocent."""
    try:
        return max(3, int(os.getenv("FLEET_EXPECTANCY_MIN_TRADES", "8")))
    except ValueError:
        return 8


def _expectancy_gate_enabled() -> bool:
    return os.getenv("FLEET_EXPECTANCY_GATE", "true").strip().lower() in (
        "1", "true", "yes", "on")


def _bucket_expectancy_block(agent_id: int, thesis: dict) -> "str | None":
    """Reason to refuse a (market, direction) bucket on its own track record.

    The desk's directional accuracy is 35% overall — worse than a coin flip —
    but it is not uniformly bad, and the per-bucket realised record is the
    only evidence about where the edge actually is. A bucket with at least
    FLEET_EXPECTANCY_MIN_TRADES closed runs and negative mean P&L per run has
    demonstrated it loses; stop rebuilding it and let the survivors compete
    for the budget. Fail-open: any error, or too small a sample, allows."""
    if not _expectancy_gate_enabled():
        return None
    direction = (thesis.get("direction") or "").lower()
    side = "short" if direction == "short" else "long"
    market = thesis.get("market")
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        # Runs are the unit of account: realized_pnl_usd is the fee-inclusive
        # book the run itself closed on, already scoped per run.
        cursor.execute(
            """SELECT COUNT(*) AS n, COALESCE(SUM(realized_pnl_usd), 0) AS total
               FROM trading_runs
               WHERE agent_id = ? AND market = ? AND status = 'stopped'
                 AND created_via = 'fleet'
                 AND JSON_EXTRACT(config_snapshot_json, '$.thesis.direction') = ?""",
            (agent_id, market, side))
        row = cursor.fetchone()
    except Exception:  # noqa: BLE001 — evidence is a nicety, never a blocker
        return None
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass
    if not row:
        return None
    n = int(row["n"] or 0)
    total = float(row["total"] or 0.0)
    if n < _expectancy_min_trades() or total >= 0:
        return None
    return (f"negative_expectancy: {market}/{side} is {total:+.2f} over "
            f"{n} closed runs (mean {total / n:+.2f}/run)")


# Replacement disposition per stop reason (Plan 14 §2 — ENUMERATED, never a
# wildcard; a future stop_event:* kind must be classified here before shipping).
REPLACE_IMMEDIATE = frozenset({
    "stop_event:max_loss", "stop_event:profit_target", "stop_event:max_trades",
    "stop_event:at_time", "stop_event:price_cross", "adapt_retired",
    "stop_event:trailing_lock",   # banked winner — replace the slot at once
    "idle_retired",               # never traded — free the slot for a live thesis
    # Arithmetic, not evidence: the frozen thesis cannot clear the fee hurdle,
    # so the run could never have traded. Replace at once — the slot is good,
    # only the thesis was dead, and _build_replacement now applies the same
    # fee gate so the successor cannot inherit the defect.
    "fee_infeasible_retired",
    # The desk kept reading the opposite of the run's own thesis on a book
    # that cannot express it. Replacing immediately is the entire point: the
    # slot should carry a thesis the desk still believes.
    "thesis_invalidated",
    # The desk marked its own thesis down for three straight cycles. The slot
    # is fine, the reason for holding is not — replace it at once.
    "thesis_decayed",
    # The desk read conviction below the floor on a HELD position for N
    # straight cycles (I5). Same disposition as thesis_decayed: the slot is
    # good, the thesis the position rode is gone — replace it at once.
    "stop_event:conviction_collapse",
})
REPLACE_DEFERRED = frozenset({"stop_eval_failed", "synthetic_liquidation",
                              "stop_event:liq_cushion"})
# fleet_stop_all MUST be here. An unclassified reason falls straight through
# to _build_replacement at the bottom of the supervisor's slot loop, so a
# fleet-wide stop would rebuild every slot it had just torn down.
REPLACE_NEVER = frozenset({"user_stop", "fleet_stop_all", "agent_deleted",
                           "user_master_remove"})
# Reasons whose slot is closed rather than left occupied by a dead member.
SLOT_CLOSING = frozenset({"user_stop", "fleet_stop_all"})

LIQUIDATION_COOLDOWN_HOURS = 24


def _now_dt() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now_dt().strftime(TS_FMT)


def fleet_enabled() -> bool:
    return os.getenv("FLEET_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}


def _session_bias_enabled() -> bool:
    """Default-on kill switch. When on, an unrestricted fleet only composes
    from markets that are open at research time (see _open_markets_scope)."""
    return os.getenv("FLEET_SESSION_BIAS", "true").strip().lower() in {"1", "true", "yes", "on"}


def _min_session_minutes() -> int:
    """Session a market must still have left to be worth composing into.

    Being open is not the same as being usable. Live 2026-07-28: ORCL and CAT
    were composed at 19:56:40 UTC — 3m20s before the NYSE close — got one
    cycle, then spent nine hours on `pre: market closed` until the idle rail
    collected them. is_market_open() was true at that instant and told the
    builder nothing. 0 disables the check."""
    try:
        return max(0, int(os.getenv("FLEET_MIN_SESSION_MINUTES", "60")))
    except ValueError:
        return 60


def _open_markets_scope(now: "datetime | None" = None) -> "list[str] | None":
    """Allowlist of tradeable markets open at `now` (real now by default), used
    to bias an unrestricted fleet away from markets that are closed and would
    idle its slots. Returns None (→ caller leaves scope unrestricted) when the
    kill switch is off or, defensively, when nothing is open (crypto is 24x7 so
    the list is non-empty in practice).

    A market with less than _min_session_minutes() left is treated as closed —
    a slot bound to it now would park before it could act."""
    if not _session_bias_enabled():
        return None
    import markets
    need = _min_session_minutes()
    open_markets = []
    for m in markets.tradeable_markets():
        if not markets.is_market_open(m, now):
            continue
        if need:
            try:
                if markets.session_minutes_left(m, now, horizon_min=need) < need:
                    continue
            except Exception:  # noqa: BLE001 — a calendar problem must not
                pass          # empty the universe; fall back to open/closed
        open_markets.append(m)
    return open_markets or None


def _tick_interval() -> int:
    return max(15, int(os.getenv("FLEET_TICK_INTERVAL", "60")))


def _lease_ttl() -> int:
    return max(60, int(os.getenv("FLEET_LEASE_TTL", "300")))


WORKER_IDENTITY = f"{socket.gethostname()}:{os.getpid()}"


# ── journal (mirrors trading_runs._emit_event) ──────────────────────────────

def _emit_fleet_event(cursor, fleet_id: int, event_type: str, payload: dict) -> int:
    cursor.execute(
        "UPDATE fleets SET last_event_seq = last_event_seq + 1 WHERE id = ?",
        (fleet_id,))
    cursor.execute("SELECT last_event_seq FROM fleets WHERE id = ?", (fleet_id,))
    seq = int(cursor.fetchone()["last_event_seq"])
    cursor.execute(
        "INSERT INTO fleet_events (fleet_id, seq, ts, event_type, payload) "
        "VALUES (?, ?, ?, ?, ?)",
        (fleet_id, seq, _now_iso(), event_type,
         json.dumps(payload, default=str)))
    return seq


def emit_fleet_event(fleet_id: int, event_type: str, payload: dict) -> Optional[int]:
    """Fail-soft standalone variant for telemetry-class events."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        begin_write_transaction(cursor)
        seq = _emit_fleet_event(cursor, fleet_id, event_type, payload)
        conn.commit()
        return seq
    except Exception:  # noqa: BLE001
        logger.warning("fleet event failed (%s, %s)", fleet_id, event_type,
                       exc_info=True)
        try:
            if conn is not None:
                conn.rollback()
        except Exception:  # noqa: BLE001
            pass
        return None
    finally:
        if conn is not None:
            conn.close()


# ── CRUD internals (routes call these) ──────────────────────────────────────

class FleetConflict(Exception):
    """One non-terminal fleet per USER — the active_fleet_key UNIQUE fired."""


def _user_id_for_agent(cursor, agent_id: int) -> Optional[int]:
    cursor.execute("SELECT user_id FROM agents WHERE id = ?", (agent_id,))
    row = cursor.fetchone()
    return row["user_id"] if row else None


def create_fleet(agent_id: int, n_runs: int, total_budget_usd: float,
                 risk_appetite: str = "balanced",
                 market_scope: Optional[list[str]] = None,
                 provider: Optional[str] = None, lang: str = "en",
                 warn_loss_frac: float = 0.30, stop_loss_frac: float = 0.40,
                 idempotency_key: Optional[str] = None,
                 name: Optional[str] = None,
                 leverage: Optional[float] = None,
                 profit_target_frac: Optional[float] = None) -> int:
    """Insert a draft fleet. Raises ValueError on bad inputs, FleetConflict
    when the user already has a non-terminal fleet, EntitlementDenied per the
    ALWAYS-ON tier gate."""
    n_lo, n_hi = FLEET_BOUNDS["n_runs"]
    if not (n_lo <= int(n_runs) <= n_hi):
        raise ValueError(f"n_runs must be between {n_lo} and {n_hi}")
    b_lo, b_hi = FLEET_BOUNDS["total_budget_usd"]
    if not (b_lo <= float(total_budget_usd) <= b_hi):
        raise ValueError(f"total_budget_usd must be between {b_lo:.0f} and {b_hi:.0f}")
    if risk_appetite not in FLEET_BOUNDS["max_bet_frac_of_run_budget"]:
        raise ValueError("risk_appetite must be stable|balanced|aggressive")
    if not (0 < float(warn_loss_frac) < float(stop_loss_frac) <= 0.40):
        raise ValueError("rails must satisfy 0 < warn < stop <= 0.40")
    if profit_target_frac is not None:
        t_lo, t_hi = FLEET_BOUNDS["profit_target_goal_bounds"]
        if not (t_lo <= float(profit_target_frac) <= t_hi):
            raise ValueError(
                f"profit_target_frac must be between {t_lo} and {t_hi}")

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        begin_write_transaction(cursor)
        user_id = _user_id_for_agent(cursor, agent_id)
        if user_id is None:
            raise ValueError("fleets require an agent linked to a user account")
        from entitlements import check_fleet_create
        deny = check_fleet_create(cursor, agent_id, int(n_runs))
        if deny:
            raise trading_runs.EntitlementDenied(deny)
        if idempotency_key:
            cursor.execute(
                "SELECT id FROM fleets WHERE idempotency_key = ? AND agent_id = ?",
                (idempotency_key, agent_id))
            row = cursor.fetchone()
            if row:
                conn.rollback()
                return int(row["id"])
        try:
            lev = None
            if leverage:
                lev = max(1.0, min(10.0, float(leverage)))
            cursor.execute(
                """INSERT INTO fleets
                   (agent_id, name, status, active_fleet_key, idempotency_key,
                    n_runs, total_budget_usd, risk_appetite, market_scope_json,
                    warn_loss_frac, stop_loss_frac, provider, lang, created_at,
                    leverage, profit_target_frac)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (agent_id, name, STATUS_DRAFT, f"user:{user_id}", idempotency_key,
                 int(n_runs), float(total_budget_usd), risk_appetite,
                 json.dumps(market_scope) if market_scope else None,
                 float(warn_loss_frac), float(stop_loss_frac),
                 provider, lang, _now_iso(), lev,
                 float(profit_target_frac) if profit_target_frac else None))
        except trading_runs.EntitlementDenied:
            raise
        except Exception as exc:  # noqa: BLE001 — UNIQUE(active_fleet_key)
            raise FleetConflict(
                "you already have an active fleet — stop it before launching "
                "another (one Full Auto fleet per account)") from exc
        fleet_id = cursor.lastrowid
        _emit_fleet_event(cursor, fleet_id, "fleet_status",
                          {"from": None, "to": STATUS_DRAFT, "reason": "created"})
        conn.commit()
        return fleet_id
    except Exception:
        try:
            conn.rollback()
        except Exception:  # noqa: BLE001
            pass
        raise
    finally:
        conn.close()


def set_profit_target(fleet_id: int, frac: Optional[float]) -> None:
    """Set (or clear with None) the fleet's take-profit goal. Free to change
    while live — it is a goal, not a protective rail."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        begin_write_transaction(cursor)
        cursor.execute("UPDATE fleets SET profit_target_frac = ? WHERE id = ?",
                       (float(frac) if frac else None, fleet_id))
        conn.commit()
    finally:
        conn.close()


def get_fleet(fleet_id: int, agent_id: Optional[int] = None) -> Optional[dict]:
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        if agent_id is None:
            cursor.execute("SELECT * FROM fleets WHERE id = ?", (fleet_id,))
        else:
            cursor.execute("SELECT * FROM fleets WHERE id = ? AND agent_id = ?",
                           (fleet_id, agent_id))
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _set_status(fleet_id: int, from_statuses: tuple, to_status: str,
                reason: Optional[str] = None, extra_sets: str = "",
                extra_args: tuple = ()) -> bool:
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        begin_write_transaction(cursor)
        sets = "status = ?, status_reason = ?"
        args: list = [to_status, reason]
        if to_status == STATUS_STOPPED:
            sets += ", active_fleet_key = NULL, stopped_at = ?"
            args.append(_now_iso())
        if extra_sets:
            sets += ", " + extra_sets
            args.extend(extra_args)
        placeholders = ",".join("?" for _ in from_statuses)
        cursor.execute(
            f"UPDATE fleets SET {sets} WHERE id = ? AND status IN ({placeholders})",
            (*args, fleet_id, *from_statuses))
        ok = cursor.rowcount == 1
        if ok:
            _emit_fleet_event(cursor, fleet_id, "fleet_status",
                              {"to": to_status, "reason": reason})
        conn.commit()
        return ok
    except Exception:  # noqa: BLE001
        try:
            conn.rollback()
        except Exception:  # noqa: BLE001
            pass
        return False
    finally:
        conn.close()


def start_fleet(fleet_id: int, agent_id: int) -> dict:
    fleet = get_fleet(fleet_id, agent_id)
    if not fleet:
        raise LookupError("fleet not found")
    if fleet["status"] != STATUS_DRAFT:
        raise ValueError(f"only a draft fleet can start (status={fleet['status']})")
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        from entitlements import check_fleet_create
        deny = check_fleet_create(cursor, agent_id, int(fleet["n_runs"]))
        if deny:
            raise trading_runs.EntitlementDenied(deny)
    finally:
        conn.close()
    _set_status(fleet_id, (STATUS_DRAFT,), STATUS_RESEARCHING, "start",
                extra_sets="started_at = ?", extra_args=(_now_iso(),))
    return get_fleet(fleet_id, agent_id) or {}


def request_stop_fleet(fleet_id: int, agent_id: int, flatten: bool = True) -> dict:
    """THE kill switch: request_stop on every non-terminal member, fleet →
    stopping. Per-member results reported, never a failed request."""
    fleet = get_fleet(fleet_id, agent_id)
    if not fleet:
        raise LookupError("fleet not found")
    results: dict[int, str] = {}
    for run in list_members(fleet_id):
        if run["status"] in (trading_runs.STATUS_STOPPED,):
            continue
        try:
            if run["status"] == trading_runs.STATUS_DRAFT:
                trading_runs.delete_run(run["id"], agent_id)
                results[run["id"]] = "draft_deleted"
            else:
                trading_runs.request_stop(run["id"], agent_id, flatten,
                                          reason="fleet_stop_all")
                results[run["id"]] = "stopping"
        except Exception as exc:  # noqa: BLE001
            results[run["id"]] = f"error: {exc}"
    _set_status(fleet_id, _NON_TERMINAL, STATUS_STOPPING, "fleet_stop_all")
    emit_fleet_event(fleet_id, "stop_all", {"flatten": flatten, "members": results})
    return {"members": results}


def pause_fleet(fleet_id: int, agent_id: int) -> dict:
    fleet = get_fleet(fleet_id, agent_id)
    if not fleet:
        raise LookupError("fleet not found")
    results: dict[int, str] = {}
    for run in list_members(fleet_id):
        if run["status"] == trading_runs.STATUS_RUNNING:
            try:
                trading_runs.pause_run(run["id"], agent_id, reason="fleet_pause")
                results[run["id"]] = "paused"
            except Exception as exc:  # noqa: BLE001
                results[run["id"]] = f"error: {exc}"
    _set_status(fleet_id, (STATUS_ACTIVE,), STATUS_PAUSED, "user_pause")
    return {"members": results}


def resume_fleet(fleet_id: int, agent_id: int) -> dict:
    fleet = get_fleet(fleet_id, agent_id)
    if not fleet:
        raise LookupError("fleet not found")
    results: dict[int, str] = {}
    for run in list_members(fleet_id):
        if run["status"] == trading_runs.STATUS_PAUSED:
            try:
                trading_runs.resume_run(run["id"], agent_id)
                results[run["id"]] = "running"
            except Exception as exc:  # noqa: BLE001
                results[run["id"]] = f"error: {exc}"
    _set_status(fleet_id, (STATUS_PAUSED,), STATUS_ACTIVE, "user_resume")
    return {"members": results}


def delete_fleet(fleet_id: int, agent_id: int) -> None:
    """draft/stopped only. Children cleaned in-transaction (MySQL FK gap);
    member runs keep their journals — fleet_id is NULLed, never deleted."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        begin_write_transaction(cursor)
        cursor.execute("SELECT status FROM fleets WHERE id = ? AND agent_id = ?",
                       (fleet_id, agent_id))
        row = cursor.fetchone()
        if not row:
            raise LookupError("fleet not found")
        if row["status"] not in (STATUS_DRAFT, STATUS_STOPPED):
            raise ValueError("only a draft or stopped fleet can be deleted")
        cursor.execute("UPDATE trading_runs SET fleet_id = NULL WHERE fleet_id = ?",
                       (fleet_id,))
        cursor.execute("DELETE FROM fleet_events WHERE fleet_id = ?", (fleet_id,))
        cursor.execute("DELETE FROM fleet_candidates WHERE fleet_id = ?", (fleet_id,))
        cursor.execute("DELETE FROM fleet_slots WHERE fleet_id = ?", (fleet_id,))
        cursor.execute("DELETE FROM fleets WHERE id = ?", (fleet_id,))
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:  # noqa: BLE001
            pass
        raise
    finally:
        conn.close()


def list_members(fleet_id: int) -> list[dict]:
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM trading_runs WHERE fleet_id = ? ORDER BY id",
                       (fleet_id,))
        return [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()


def _update_master_hold(fleet_id: int, held: bool) -> None:
    """§6.7: the fleet's hold marker lives in its OWN field — status_reason
    (e.g. a live 'partial:3/5') is untouched and recomputed by supervise."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        begin_write_transaction(cursor)
        cursor.execute("UPDATE fleets SET held_by_master = ? WHERE id = ?",
                       (1 if held else 0, fleet_id))
        conn.commit()
    finally:
        conn.close()


# ── budget math (pure) ──────────────────────────────────────────────────────

def allocate_budget(total: float, theses: list[dict]) -> list[float]:
    """Confidence-weighted allocations, clamped to [B/2N, 2B/N], Σ ≤ B."""
    n = len(theses)
    if n == 0:
        return []
    equal = total / n
    lo_f, hi_f = FLEET_BOUNDS["alloc_frac_of_equal"]
    lo, hi = equal * lo_f, equal * hi_f
    weights = [max(0.2, min(1.0, float(t.get("confidence") or 0.5))) for t in theses]
    wsum = sum(weights) or 1.0
    raw = [total * w / wsum for w in weights]
    alloc = [max(lo, min(hi, r)) for r in raw]
    # Σ may exceed B after clamping; a plain scale-down would push small slots
    # BELOW the floor. Feasible because n×lo = B/2 ≤ B: eat the excess out of
    # each slot's above-floor slack, proportionally.
    excess = sum(alloc) - total
    if excess > 0:
        slack = [a - lo for a in alloc]
        slack_sum = sum(slack) or 1.0
        alloc = [a - excess * s / slack_sum for a, s in zip(alloc, slack)]
    # floor to cents — plain round() can push Σ a cent past the user's budget
    import math as _math
    return [_math.floor(a * 100) / 100 for a in alloc]


def compose_run_settings(thesis: dict, run_budget: float, fleet: dict) -> dict:
    """Thesis + slot budget → the run-creation payload. Deterministic clamps
    only — including the §6.4 percent→fraction unit conversion (a 2.5% thesis
    on $1,000 must produce a ~$25 target, not $500)."""
    risk = fleet.get("risk_appetite") or "balanced"
    market = thesis["market"]
    direction = (thesis.get("direction") or "long").strip().lower()
    market_type = "futures" if (direction == "short" and market == "crypto") else \
        thesis.get("market_type") or "spot"
    interval = max(_tier("interval_minutes", risk),
                   FLEET_BOUNDS["interval_floor_by_market"].get(
                       market, FLEET_BOUNDS["interval_floor_default"]))
    g_lo, g_hi = FLEET_BOUNDS["profit_target_frac_bounds"]
    # Higher tiers bank later: multiply the thesis move, then re-clamp so a
    # 2× on a big expected move can't exceed the 50% run-budget target cap.
    gain_frac = float(thesis.get("expected_move_pct") or 0) / 100.0
    gain_frac = max(g_lo, min(g_hi, gain_frac * _tier("profit_target_mult", risk)))
    horizon_h = max(4.0, min(24.0 * 14, float(thesis.get("horizon_hours") or 48)))
    max_bet = round(run_budget * _tier("max_bet_frac_of_run_budget", risk), 2)
    max_bet = min(max_bet, 1_000_000.0)
    at_time = (_now_dt() + timedelta(hours=horizon_h)).strftime(TS_FMT)
    # Plan 15 P1 (F3): a run whose gate exceeds its own thesis confidence is
    # born unable to trade (fleet 6 built ZC at thesis 0.539 against a 0.65
    # gate — every cycle skipped). The gate never exceeds thesis_conf − 0.05,
    # floored at 0.50 so weak theses still gate meaningfully.
    thesis_conf = float(thesis.get("confidence") or 0.5)
    min_conf = min(_tier("min_confidence", risk),
                   max(0.50, round(thesis_conf - 0.05, 2)))
    # Leverage: the fleet's explicit setting wins ("set"); None/0 ⇒ auto by
    # tier ("auto"). Clamp to the 1–10× the run route accepts.
    fleet_lev = fleet.get("leverage")
    leverage = float(fleet_lev) if fleet_lev else _tier("auto_leverage", risk)
    leverage = max(1.0, min(10.0, leverage))
    # Hoisted: the trailing lock arms against this, so it must exist before
    # the stop_conditions literal is built.
    max_loss_usd = round(max_bet * _tier("stop_loss_frac_of_bet", risk), 2)
    return {
        "symbol": thesis["symbol"], "market": market, "market_type": market_type,
        "max_bet_usd": max_bet,
        "run_budget_usd": round(float(run_budget), 2),
        "interval_minutes": int(interval),
        "min_confidence": min_conf,
        "leverage": leverage,
        "provider": fleet.get("provider"), "lang": fleet.get("lang") or "en",
        "stop_conditions": {
            # Active stop scaled to the POSITION (max_bet), not run_budget —
            # cuts a real adverse move instead of sitting ~44% beyond it.
            "max_loss_usd": max_loss_usd,
            # Far thesis-move target kept as a secondary cap; the trailing lock
            # below is the primary profit-realiser for intraday moves.
            "profit_target_usd": round(run_budget * gain_frac, 2),
            # Lock arms against the STOP, not just notional — see _trail_config.
            "trail": _trail_config(max_bet, leverage, max_loss_usd),
            "at_time": at_time,
        },
        # Plan 14: stop_flatten pinned True on the builder path (the API-route
        # default does not apply to internal create_run), feedback on, light
        # cycle default, thesis stored at TOP level of the snapshot.
        "stop_flatten": True,
        "add_limits": {"max_adds": FLEET_BOUNDS["max_position_adds"],
                       "cooldown_minutes": FLEET_BOUNDS["add_cooldown_minutes"]},
        "thesis": {
            "symbol": thesis["symbol"], "market": market, "market_type": market_type,
            "direction": direction,
            "confidence": float(thesis.get("confidence") or 0.5),
            "expected_move_pct": float(thesis.get("expected_move_pct") or 0),
            "horizon_hours": horizon_h,
            "entry_ref_price": None,  # stamped at build from the probe price
            "rationale": (thesis.get("thesis") or "")[:1000],
            "invalidation": (thesis.get("invalidation") or "")[:300],
            "batch_id": thesis.get("batch_id"),
            "planner": thesis.get("planner"),
        },
        "feedback": True,
    }


# ── marked equity (§6.3.0 — the ONE equity) ─────────────────────────────────

def marked_equity(fleet: dict) -> dict:
    """total_budget + Σ P&L over ALL runs ever attributed, fail-closed.

    Non-terminal members replay compute_run_pnl (live unrealized +
    mark_age_ok); cleanly-stopped members use the stamped realized_pnl_usd;
    positions_held zombies reconstruct open qty/basis from the run's own
    signals replay and mark against the agent's unowned book row (the engine
    released positions.run_id at that terminal — round-5 critical).

    Returns {equity, ok, zombie_basis, detail}; ok=False ⇒ the caller must
    FREEZE all equity-derived mutations this tick.
    """
    from run_engine import compute_run_pnl

    total = float(fleet["total_budget_usd"])
    pnl_sum = 0.0
    zombie_basis = 0.0
    ok = True
    for run in list_members(fleet["id"]):
        status = run["status"]
        reason = run.get("status_reason") or ""
        if status == trading_runs.STATUS_STOPPED and reason == "positions_held":
            z = _zombie_pnl(run)
            if z is None:
                ok = False
                continue
            pnl_sum += z["pnl"]
            zombie_basis += z["open_basis"]
            continue
        if status == trading_runs.STATUS_STOPPED:
            pnl_sum += float(run.get("realized_pnl_usd") or 0)
            continue
        if status == trading_runs.STATUS_DRAFT:
            continue
        pnl = compute_run_pnl(run)
        if not pnl.get("mark_age_ok", True) and pnl.get("position"):
            ok = False
        pnl_sum += float(pnl.get("total") or 0)
    return {"equity": total + pnl_sum, "ok": ok, "zombie_basis": zombie_basis,
            "pnl": pnl_sum}


def _zombie_pnl(run: dict) -> Optional[dict]:
    """positions_held reconstruction: realized from the leg replay
    (signals.run_id survives), open qty/basis from the same replay, marked
    against the agent's UNOWNED book row for the tuple. None ⇒ mark missing
    or stale ⇒ rail-evaluation FAILURE (never unrealized=0)."""
    from run_engine import _age_seconds, _mark_staleness_max

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """SELECT side, entry_price, quantity, fee_usd FROM signals
               WHERE run_id = ? AND message_type = 'operation' ORDER BY id""",
            (run["id"],))
        legs = [dict(r) for r in cursor.fetchall()]
        cursor.execute(
            """SELECT current_price, price_updated_at FROM positions
               WHERE agent_id = ? AND market = ? AND symbol = ?
                 AND run_id IS NULL AND quantity != 0""",
            (run["agent_id"], run["market"], run["symbol"]))
        pos = cursor.fetchone()
    finally:
        conn.close()

    qty, avg, realized = 0.0, 0.0, 0.0
    for leg in legs:
        side, p = leg["side"], float(leg["entry_price"] or 0)
        q, fee = float(leg["quantity"] or 0), float(leg["fee_usd"] or 0)
        if side == "buy":
            avg = (avg * qty + p * q) / (qty + q) if qty + q > 0 else p
            qty += q
            realized -= fee
        elif side == "sell":
            realized += (p - avg) * min(q, qty) - fee
            qty -= min(q, qty)
        elif side == "short":
            held = -qty
            avg = (avg * held + p * q) / (held + q) if held + q > 0 else p
            qty -= q
            realized -= fee
        elif side == "cover":
            held = -qty
            realized += (avg - p) * min(q, held) - fee
            qty += min(q, held)
    open_basis = abs(qty) * avg
    if abs(qty) < 1e-12:
        return {"pnl": realized, "open_basis": 0.0}
    if not pos:
        # zombie closed via the unowned book — the closing legs did not carry
        # our run_id, so replay realized is the best attribution we have
        return {"pnl": realized, "open_basis": 0.0}
    mark = pos["current_price"]
    updated = pos["price_updated_at"]
    if mark is None or not updated or _age_seconds(updated) > _mark_staleness_max():
        return None  # stale zombie mark == equity evaluation failure
    unrealized = (float(mark) - avg) * qty if qty > 0 else (avg - float(mark)) * (-qty)
    return {"pnl": realized + unrealized, "open_basis": open_basis}


# ── lease (run protocol copied) ─────────────────────────────────────────────

def _claim_fleet(fleet_id: int) -> Optional[dict]:
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        begin_write_transaction(cursor)
        now = _now_iso()
        expires = (_now_dt() + timedelta(seconds=_lease_ttl())).strftime(TS_FMT)
        cursor.execute(
            """UPDATE fleets SET claimed_by = ?, claim_expires_at = ?
               WHERE id = ? AND status IN ('researching','building','active',
                                           'paused','stopping')
                 AND (claim_expires_at IS NULL OR claim_expires_at < ?
                      OR claimed_by = ?)""",
            (WORKER_IDENTITY, expires, fleet_id, now, WORKER_IDENTITY))
        ok = cursor.rowcount == 1
        conn.commit()
        if not ok:
            return None
    finally:
        conn.close()
    return get_fleet(fleet_id)


def _release_fleet(fleet_id: int) -> None:
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        begin_write_transaction(cursor)
        cursor.execute(
            "UPDATE fleets SET claimed_by = NULL, claim_expires_at = NULL "
            "WHERE id = ? AND claimed_by = ?", (fleet_id, WORKER_IDENTITY))
        conn.commit()
    except Exception:  # noqa: BLE001
        pass
    finally:
        conn.close()


# ── research-consume + build ────────────────────────────────────────────────

def _master_state(agent_id: int) -> str:
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT u.ai_automation_state AS s FROM users u "
            "JOIN agents a ON a.user_id = u.id WHERE a.id = ?", (agent_id,))
        row = cursor.fetchone()
        return (row["s"] or "active") if row else "active"
    finally:
        conn.close()


def _do_research(fleet: dict) -> None:
    """Consume the global batch: select N theses, allocate by key, bind slots.
    Zero LLM — research is the platform loop's job."""
    import symbol_research

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        scope = None
        if fleet.get("market_scope_json"):
            try:
                scope = json.loads(fleet["market_scope_json"])
            except (ValueError, TypeError):
                scope = None
        if not scope:
            # Auto session-bias: an unrestricted fleet composed while a market
            # is closed would bind slots to symbols that idle until the next
            # session (e.g. us-stock overnight sits dead until ~13:30Z). Narrow
            # the universe to markets open right now so every slot works
            # immediately. Explicit market_scope is honoured verbatim — this
            # only fills the None case.
            scope = _open_markets_scope()
        theses = symbol_research.select_targets(
            cursor, fleet["agent_id"], int(fleet["n_runs"]), markets_scope=scope)
    finally:
        conn.close()
    # Expectancy gate (plan #1-D): candidates with a measured non-positive
    # net edge never get a slot. Fail-open by construction — a gate problem
    # must not stop the fleet from composing.
    import backtest_gate
    if theses and backtest_gate.gate_enabled():
        kept, dropped = backtest_gate.gate_candidates(theses)
        if dropped or len(kept) != len(theses):
            emit_fleet_event(fleet["id"], "backtest_gate",
                             {"kept": [t["symbol"] for t in kept],
                              "dropped": dropped})
        theses = kept
    if not theses:
        # stay in researching; supervise/status shows replenishing-style state
        emit_fleet_event(fleet["id"], "research_empty",
                         {"reason": "no eligible candidates in the latest batch"})
        attempts = int(fleet.get("build_attempts") or 0) + 1
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            begin_write_transaction(cursor)
            cursor.execute("UPDATE fleets SET build_attempts = ? WHERE id = ?",
                           (attempts, fleet["id"]))
            conn.commit()
        finally:
            conn.close()
        if attempts >= 20:
            _set_status(fleet["id"], (STATUS_RESEARCHING,), STATUS_STOPPED,
                        "build_failed")
        return

    allocations = allocate_budget(float(fleet["total_budget_usd"]), theses)
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        begin_write_transaction(cursor)
        for idx, (thesis, alloc) in enumerate(zip(theses, allocations)):
            thesis_key = f"{thesis.get('batch_id')}:{thesis['market']}:{thesis['symbol']}"
            cursor.execute(
                """INSERT INTO fleet_slots
                   (fleet_id, slot_index, original_allocation_usd, state,
                    updated_at) VALUES (?, ?, ?, 'active', ?)""",
                (fleet["id"], idx, alloc, _now_iso()))
            cursor.execute(
                """INSERT INTO fleet_candidates
                   (fleet_id, thesis_key, slot_index, allocation_usd, state,
                    created_at) VALUES (?, ?, ?, ?, 'selected', ?)""",
                (fleet["id"], thesis_key, idx, alloc, _now_iso()))
        _emit_fleet_event(cursor, fleet["id"], "allocation",
                          {"allocations": {
                              f"{t.get('batch_id')}:{t['market']}:{t['symbol']}": a
                              for t, a in zip(theses, allocations)},
                           "total": float(fleet["total_budget_usd"])})
        _emit_fleet_event(cursor, fleet["id"], "research_ranked",
                          {"selected": [{"symbol": t["symbol"], "market": t["market"],
                                         "final_score": t.get("final_score")}
                                        for t in theses]})
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:  # noqa: BLE001
            pass
        raise
    finally:
        conn.close()
    _set_status(fleet["id"], (STATUS_RESEARCHING,), STATUS_BUILDING, None)


def _selected_candidates(fleet_id: int) -> list[dict]:
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """SELECT * FROM fleet_candidates WHERE fleet_id = ?
               AND state = 'selected' ORDER BY slot_index""", (fleet_id,))
        return [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()


def _thesis_for_key(cursor, thesis_key: str) -> Optional[dict]:
    try:
        batch_id, market, symbol = thesis_key.rsplit(":", 2)
    except ValueError:
        return None
    cursor.execute(
        """SELECT * FROM research_theses WHERE batch_id = ? AND market = ?
           AND symbol = ?""", (batch_id, market, symbol))
    row = cursor.fetchone()
    return dict(row) if row else None


def _mark_candidate(fleet_id: int, cand_id: int, state: str,
                    run_id: Optional[int] = None) -> None:
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        begin_write_transaction(cursor)
        cursor.execute(
            "UPDATE fleet_candidates SET state = ?, run_id = ? WHERE id = ? "
            "AND fleet_id = ?", (state, run_id, cand_id, fleet_id))
        conn.commit()
    finally:
        conn.close()


def _bind_slot(fleet_id: int, slot_index: int, run_id: Optional[int],
               state: str = "active",
               zombie_baseline_qty: Optional[float] = None) -> None:
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        begin_write_transaction(cursor)
        if zombie_baseline_qty is None:
            cursor.execute(
                "UPDATE fleet_slots SET current_run_id = ?, state = ?, "
                "updated_at = ? WHERE fleet_id = ? AND slot_index = ?",
                (run_id, state, _now_iso(), fleet_id, slot_index))
        else:
            cursor.execute(
                "UPDATE fleet_slots SET current_run_id = ?, state = ?, "
                "zombie_baseline_qty = ?, updated_at = ? "
                "WHERE fleet_id = ? AND slot_index = ?",
                (run_id, state, zombie_baseline_qty, _now_iso(),
                 fleet_id, slot_index))
        conn.commit()
    finally:
        conn.close()


def _tuple_busy(cursor, agent_id: int, market: str, symbol: str) -> bool:
    """Per-candidate (agent, market, symbol) recheck — active_key alone is
    strategy-level since 0027 and will NOT block a differing fleet config."""
    cursor.execute(
        """SELECT id FROM trading_runs WHERE agent_id = ? AND market = ?
           AND symbol = ? AND status IN ('armed','running','paused','stopping')
           LIMIT 1""", (agent_id, market, symbol))
    return cursor.fetchone() is not None


def _do_build(fleet: dict) -> None:
    """Create + start member runs from selected candidates. Resume-safe:
    progress is the candidates' states, allocations consumed BY KEY."""
    from routes_runs import RunIn, validate_run_payload, _probe_price

    agent_id = fleet["agent_id"]
    built = skipped = 0
    for cand in _selected_candidates(fleet["id"]):
        # Per-candidate abort checks: a stop/hold landing mid-build must not
        # keep creating runs.
        live = get_fleet(fleet["id"])
        if not live or live["status"] != STATUS_BUILDING:
            emit_fleet_event(fleet["id"], "build_aborted",
                             {"reason": "fleet_status_changed"})
            return
        if _master_state(agent_id) == "held":
            emit_fleet_event(fleet["id"], "build_aborted",
                             {"reason": "master_hold"})
            return

        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            thesis = _thesis_for_key(cursor, cand["thesis_key"])
            busy = thesis and _tuple_busy(cursor, agent_id, thesis["market"],
                                          thesis["symbol"])
        finally:
            conn.close()
        if not thesis:
            _mark_candidate(fleet["id"], cand["id"], "skipped")
            emit_fleet_event(fleet["id"], "candidate_skipped",
                             {"thesis_key": cand["thesis_key"],
                              "reason": "thesis_expired"})
            skipped += 1
            continue
        if busy:
            _mark_candidate(fleet["id"], cand["id"], "skipped")
            emit_fleet_event(fleet["id"], "candidate_skipped",
                             {"thesis_key": cand["thesis_key"],
                              "reason": "symbol_busy"})
            skipped += 1
            continue
        # Fee/edge feasibility, checked HERE rather than per cycle
        # (2026-07-26). expected_move_pct is frozen into the config snapshot at
        # build, so a thesis that cannot clear the round-trip hurdle can never
        # clear it — prod run 114 (ZS, 1.31%) was refused on every cycle and
        # would have burned ~60 LLM calls over 7h before idle-retire collected
        # it. Deterministic input, so decide once, before the run exists.
        infeasible = _thesis_fee_infeasible(thesis)
        if infeasible:
            _mark_candidate(fleet["id"], cand["id"], "skipped")
            emit_fleet_event(fleet["id"], "candidate_skipped",
                             {"thesis_key": cand["thesis_key"],
                              "reason": infeasible})
            skipped += 1
            continue
        # Proven-negative expectancy: refuse to rebuild a (market, direction)
        # the desk has already demonstrated it loses on. Directional accuracy
        # measured 35% overall (long 32% / short 40%) over 40 runs, so the
        # per-bucket record is the only honest input we have about edge.
        negative = _bucket_expectancy_block(agent_id, thesis)
        if negative:
            _mark_candidate(fleet["id"], cand["id"], "skipped")
            emit_fleet_event(fleet["id"], "candidate_skipped",
                             {"thesis_key": cand["thesis_key"],
                              "reason": negative})
            skipped += 1
            continue

        settings = compose_run_settings(thesis, float(cand["allocation_usd"] or 0),
                                        fleet)
        run_id = None
        try:
            payload = RunIn(
                symbol=settings["symbol"], market=settings["market"],
                market_type=settings["market_type"],
                max_bet_usd=settings["max_bet_usd"],
                run_budget_usd=settings["run_budget_usd"],
                interval_minutes=settings["interval_minutes"],
                min_confidence=settings["min_confidence"],
                provider=settings["provider"], lang=settings["lang"],
                stop_conditions=settings["stop_conditions"],
                leverage=settings.get("leverage", 1.0),
                stop_flatten=True)
            core, start_c, stop_c = validate_run_payload(payload)
            # thesis + fleet flags ride the config snapshot (§4.4 top-level)
            core["thesis"] = dict(settings["thesis"])
            core["thesis"]["entry_ref_price"] = _probe_price(core["symbol"],
                                                             core["market"])
            core["feedback"] = True
            core["add_limits"] = dict(settings.get("add_limits") or {})
            run_id = trading_runs.create_run(agent_id, core, start_c, stop_c,
                                             True, fleet_id=fleet["id"],
                                             created_via="fleet")
            trading_runs.start_run(run_id, agent_id)
        except trading_runs.StartConflict as exc:
            if run_id:
                try:
                    trading_runs.delete_run(run_id, agent_id)
                except Exception:  # noqa: BLE001
                    pass
            _mark_candidate(fleet["id"], cand["id"], "skipped")
            emit_fleet_event(fleet["id"], "candidate_skipped",
                             {"thesis_key": cand["thesis_key"],
                              "reason": f"start_conflict: {exc}"})
            skipped += 1
            continue
        except trading_runs.EntitlementDenied as exc:
            if run_id:
                try:
                    trading_runs.delete_run(run_id, agent_id)
                except Exception:  # noqa: BLE001
                    pass
            _mark_candidate(fleet["id"], cand["id"], "skipped")
            emit_fleet_event(fleet["id"], "candidate_skipped",
                             {"thesis_key": cand["thesis_key"],
                              "reason": f"entitlement: {exc}"})
            skipped += 1
            break  # headroom exhausted — partial-finish, don't loop the rest
        except Exception as exc:  # noqa: BLE001 — unpriceable / invalid
            if run_id:
                try:
                    trading_runs.delete_run(run_id, agent_id)
                except Exception:  # noqa: BLE001
                    pass
            _mark_candidate(fleet["id"], cand["id"], "skipped")
            emit_fleet_event(fleet["id"], "candidate_skipped",
                             {"thesis_key": cand["thesis_key"],
                              "reason": str(exc)[:300]})
            skipped += 1
            continue

        _mark_candidate(fleet["id"], cand["id"], "built", run_id)
        _bind_slot(fleet["id"], int(cand["slot_index"] or 0), run_id)
        emit_fleet_event(fleet["id"], "run_started",
                         {"run_id": run_id, "symbol": core["symbol"],
                          "market": core["market"],
                          "slot_index": cand["slot_index"],
                          "budget": settings["run_budget_usd"]})
        built += 1

    n = int(fleet["n_runs"])
    total_built = len([m for m in list_members(fleet["id"])
                       if m["status"] not in (trading_runs.STATUS_DRAFT,)])
    if total_built == 0:
        _set_status(fleet["id"], (STATUS_BUILDING,), STATUS_STOPPED, "build_failed")
    elif total_built < n:
        _set_status(fleet["id"], (STATUS_BUILDING,), STATUS_ACTIVE,
                    f"partial:{total_built}/{n}")
    else:
        _set_status(fleet["id"], (STATUS_BUILDING,), STATUS_ACTIVE, None)


# ── tick ────────────────────────────────────────────────────────────────────

def due_fleet_ids() -> list[int]:
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """SELECT id FROM fleets
               WHERE status IN ('researching','building','active','paused',
                                'stopping')""")
        return [int(r["id"]) for r in cursor.fetchall()]
    finally:
        conn.close()


def fleet_tick() -> dict:
    """One pass over every claimable fleet. Never raises."""
    out = {"claimed": 0, "researched": 0, "built": 0, "supervised": 0}
    for fleet_id in due_fleet_ids():
        fleet = _claim_fleet(fleet_id)
        if fleet is None:
            continue
        out["claimed"] += 1
        try:
            status = fleet["status"]
            if status == STATUS_RESEARCHING:
                _do_research(fleet)
                out["researched"] += 1
            elif status == STATUS_BUILDING:
                _do_build(fleet)
                out["built"] += 1
            elif status in (STATUS_ACTIVE, STATUS_PAUSED, STATUS_STOPPING):
                # Supervision (rails, replacement, watchdog stamp) — Phase 4
                # module; imported lazily so Phase 3 ships without it.
                try:
                    from fleet_supervisor import supervise_fleet
                    supervise_fleet(fleet)
                    out["supervised"] += 1
                except ImportError:
                    pass
        except Exception as exc:  # noqa: BLE001
            logger.exception("fleet tick failed (fleet %s): %s", fleet_id, exc)
        finally:
            _release_fleet(fleet_id)
    return out


async def fleet_planner_loop() -> None:
    """Registry key 'fleet_planner', role 'settlement'. Double-gated:
    AUTO_TRADING_ENABLED + FLEET_ENABLED. NOTE (§6.5.5): when FLEET_ENABLED
    is off, supervision of fleets with non-terminal members KEEPS RUNNING —
    the flag only refuses NEW research/builds."""
    import asyncio

    from run_engine import auto_trading_enabled

    await asyncio.sleep(7)
    while True:
        try:
            if auto_trading_enabled():
                if fleet_enabled():
                    result = fleet_tick()
                else:
                    # supervision-only pass: rails never go dark
                    result = {"supervise_only": 0}
                    for fleet_id in due_fleet_ids():
                        fleet = _claim_fleet(fleet_id)
                        if fleet is None:
                            continue
                        try:
                            if fleet["status"] in (STATUS_ACTIVE, STATUS_PAUSED,
                                                   STATUS_STOPPING):
                                try:
                                    from fleet_supervisor import supervise_fleet
                                    supervise_fleet(fleet)
                                    result["supervise_only"] += 1
                                except ImportError:
                                    pass
                        finally:
                            _release_fleet(fleet_id)
                if any(result.values()):
                    print(f"[FleetPlanner] tick: {result}")
        except Exception as exc:  # noqa: BLE001
            logger.warning("[FleetPlanner] tick crashed: %s", exc)
        await asyncio.sleep(_tick_interval())
