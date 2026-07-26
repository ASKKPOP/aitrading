"""Fleet supervision (Plan 14 §6.5) — rails, latch, replacement, watchdog.

Runs for EVERY non-terminal fleet regardless of status (active, paused,
warned, held) — the rails never go dark while money is deployed, and a fleet
whose members have all stopped must still replenish (perpetual N).

Drawdown rails, two-tier on MARKED equity (§6.3.0), evaluated TIER-2 FIRST:
- −stop_loss_frac (≤0.40 hard): stop-all flatten + SMS (reserved alert
  budget), fleet → stopped('breaker'). Fires at the first tick OBSERVING the
  breach — inter-tick overshoot is possible and never promised away.
- −warn_loss_frac: episode-latched warning — SMS + running members paused
  with paused_reason='drawdown_warning' (the actual entry-block mechanism)
  + replacements suspended. User resume (ack) sticks; the latch re-arms on
  recovery above warn−5pp, and each additional −5pp leg below the last
  warned level fires ONE fresh SMS and re-pauses.

Equity-evaluation failure (stale marks, incl. positions_held zombies)
FREEZES all equity-derived mutations that tick; K=5 consecutive failures
pause entries fleet-wide.

Replacement per the enumerated per-reason table (fleet_planner.REPLACE_*),
funded sequentially with min(original slot allocation, headroom) where
headroom = marked equity − Σ active member budgets − Σ zombie open basis,
recomputed after each funding within the pass.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import fleet_planner as fp
import trading_runs
from database import begin_write_transaction, get_db_connection

logger = logging.getLogger(__name__)

TS_FMT = "%Y-%m-%dT%H:%M:%SZ"

WARN_LEG_STEP = 0.05          # each additional −5pp below the last warned level
REARM_RECOVERY_STEP = 0.05    # latch clears above warn_loss_frac − 5pp
EVAL_FAIL_LIMIT = 5


def _now_dt() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now_dt().strftime(TS_FMT)


def _update_fleet(fleet_id: int, sets: str, args: tuple) -> None:
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        begin_write_transaction(cursor)
        cursor.execute(f"UPDATE fleets SET {sets} WHERE id = ?",
                       (*args, fleet_id))
        conn.commit()
    finally:
        conn.close()


def _alert(fleet: dict, kind: str, msg_id: str, params: dict, dedupe: str) -> None:
    try:
        from alerts import send_alert
        send_alert(fleet["agent_id"], kind, msg_id, params, dedupe_key=dedupe)
    except Exception:  # noqa: BLE001 — alerting must never wedge supervision
        logger.warning("fleet alert failed (%s, %s)", fleet["id"], kind,
                       exc_info=True)


# ── public: the per-tick entry point ────────────────────────────────────────

def supervise_fleet(fleet: dict) -> dict:
    """One supervision pass. Never raises. Caller holds the fleet lease."""
    out: dict[str, Any] = {"fleet_id": fleet["id"]}
    _update_fleet(fleet["id"], "last_supervise_at = ?", (_now_iso(),))

    members = fp.list_members(fleet["id"])

    # agent deleted ⇒ the whole fleet stops (per-reason table)
    if _agent_deleted(fleet["agent_id"]):
        fp._set_status(fleet["id"], fp._NON_TERMINAL, fp.STATUS_STOPPED,
                       "agent_deleted")
        return {**out, "stopped": "agent_deleted"}

    # stopping ⇒ finalize when every member is terminal
    if fleet["status"] == fp.STATUS_STOPPING:
        if all(m["status"] == trading_runs.STATUS_STOPPED for m in members):
            fp._set_status(fleet["id"], (fp.STATUS_STOPPING,), fp.STATUS_STOPPED,
                           fleet.get("status_reason") or "user_stop")
            out["stopped"] = True
        return out

    eq = fp.marked_equity(fleet)
    if not eq["ok"]:
        # FREEZE: no rails verdict, no funding, no dormancy transitions
        fails = _bump_eval_failures(fleet)
        fp.emit_fleet_event(fleet["id"], "breaker_eval_failed",
                            {"consecutive": fails})
        if fails == EVAL_FAIL_LIMIT:
            _pause_entries(fleet, reason="eval_failed")
            _alert(fleet, "fleet_watchdog", "fleet_watchdog_eval_failed",
                   {"fleet_id": fleet["id"], "fails": fails},
                   dedupe=f"fleet:{fleet['id']}:eval_failed")
        return {**out, "frozen": True, "eval_failures": fails}
    _reset_eval_failures(fleet)

    total = float(fleet["total_budget_usd"])
    loss_frac = max(0.0, (total - eq["equity"]) / total) if total > 0 else 0.0
    out["loss_frac"] = round(loss_frac, 4)

    # ── TIER 2 FIRST: a gap through both thresholds ⇒ one stop-all, one SMS
    if loss_frac >= float(fleet["stop_loss_frac"]):
        _stop_all(fleet, loss_frac)
        return {**out, "breaker": True}

    # ── TIER 1: episode-latched warning
    _warning_tier(fleet, loss_frac)

    # refresh view after possible warning writes
    fleet = fp.get_fleet(fleet["id"]) or fleet

    # ── slot bookkeeping + replacement (suspended while warned/paused/held)
    _slot_pass(fleet, members, eq)
    return out


def ack_warning(fleet_id: int, agent_id: int) -> dict:
    """User resume from the −30% warning ('your responsibility from here').
    Un-pauses ONLY members carrying the drawdown marker (a user-paused member
    stays paused; a master-held member's marker is untouched)."""
    fleet = fp.get_fleet(fleet_id, agent_id)
    if not fleet:
        raise LookupError("fleet not found")
    if not fleet.get("warn_latched_at"):
        raise ValueError("no drawdown warning is active")
    _update_fleet(fleet_id, "warn_acked_at = ?, entry_paused_reason = NULL",
                  (_now_iso(),))
    resumed = []
    for m in fp.list_members(fleet_id):
        if m["status"] == trading_runs.STATUS_PAUSED and \
                (m.get("paused_reason") or "") == "drawdown_warning":
            try:
                trading_runs.resume_run(m["id"], agent_id)
                resumed.append(m["id"])
            except Exception:  # noqa: BLE001
                pass
    fp.emit_fleet_event(fleet_id, "warning_acked",
                        {"resumed_members": resumed})
    return {"resumed": resumed}


def check_watchdog() -> int:
    """Dead-supervision detector — called from the RUNS loop (a different
    coroutine), so a crashed fleet loop still alerts. Fires when a fleet with
    non-terminal members has no supervise stamp within 3 ticks."""
    from fleet_planner import _tick_interval

    stale_before = (_now_dt() - timedelta(
        seconds=3 * _tick_interval())).strftime(TS_FMT)
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """SELECT * FROM fleets
               WHERE status IN ('active','paused','stopping')
                 AND (last_supervise_at IS NULL OR last_supervise_at < ?)""",
            (stale_before,))
        stale = [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()
    for fleet in stale:
        _alert(fleet, "fleet_watchdog", "fleet_watchdog_stalled",
               {"fleet_id": fleet["id"]},
               dedupe=f"fleet:{fleet['id']}:watchdog")
    return len(stale)


# ── rails internals ─────────────────────────────────────────────────────────

def _stop_all(fleet: dict, loss_frac: float) -> None:
    for m in fp.list_members(fleet["id"]):
        if m["status"] in (trading_runs.STATUS_RUNNING, trading_runs.STATUS_PAUSED,
                           trading_runs.STATUS_ARMED):
            try:
                if m["status"] == trading_runs.STATUS_ARMED:
                    # armed → stopped directly (nothing to flatten)
                    trading_runs._transition(m["id"], fleet["agent_id"],
                                             (trading_runs.STATUS_ARMED,),
                                             trading_runs.STATUS_STOPPED,
                                             "fleet_breaker",
                                             clear_active_key=True)
                else:
                    trading_runs.request_stop(m["id"], fleet["agent_id"],
                                              flatten=True)
            except Exception:  # noqa: BLE001
                pass
    fp.emit_fleet_event(fleet["id"], "breaker",
                        {"loss_frac": round(loss_frac, 4),
                         "stop_loss_frac": fleet["stop_loss_frac"]})
    fp._set_status(fleet["id"], fp._NON_TERMINAL, fp.STATUS_STOPPING, "breaker")
    _alert(fleet, "fleet_breaker", "fleet_breaker",
           {"fleet_id": fleet["id"], "loss_pct": f"{loss_frac * 100:.0f}",
            "stop_loss_pct": f"{float(fleet['stop_loss_frac']) * 100:.0f}"},
           dedupe=f"fleet:{fleet['id']}:breaker")


def _warning_tier(fleet: dict, loss_frac: float) -> None:
    warn_frac = float(fleet["warn_loss_frac"])
    latched = fleet.get("warn_latched_at")
    level = float(fleet.get("warn_level_frac") or 0)

    if loss_frac < max(0.0, warn_frac - REARM_RECOVERY_STEP):
        if latched:
            # recovery above warn−5pp ⇒ latch clears; un-pause any members
            # still carrying the marker (episode over)
            _update_fleet(fleet["id"],
                          "warn_latched_at = NULL, warn_acked_at = NULL, "
                          "warn_level_frac = NULL, entry_paused_reason = NULL",
                          ())
            for m in fp.list_members(fleet["id"]):
                if m["status"] == trading_runs.STATUS_PAUSED and \
                        (m.get("paused_reason") or "") == "drawdown_warning":
                    try:
                        trading_runs.resume_run(m["id"], fleet["agent_id"])
                    except Exception:  # noqa: BLE001
                        pass
            fp.emit_fleet_event(fleet["id"], "warning_cleared",
                                {"loss_frac": round(loss_frac, 4)})
        return

    if loss_frac < warn_frac:
        return

    if not latched:
        _fire_warning(fleet, loss_frac, first=True)
        return

    # latched: a fresh −5pp leg below the last warned level fires ONE new
    # warning + re-pause, whether or not the user has acked (round-5 fix).
    if level and loss_frac >= level + WARN_LEG_STEP:
        _fire_warning(fleet, loss_frac, first=False)


def _fire_warning(fleet: dict, loss_frac: float, first: bool) -> None:
    warn_frac = float(fleet["warn_loss_frac"])
    # warned level = the threshold band this warning covers
    import math
    level = warn_frac + math.floor((loss_frac - warn_frac) / WARN_LEG_STEP) \
        * WARN_LEG_STEP
    episode = int(fleet.get("warn_episode") or 0) + 1
    _update_fleet(
        fleet["id"],
        "warn_latched_at = ?, warn_acked_at = NULL, warn_level_frac = ?, "
        "warn_episode = ?, entry_paused_reason = 'drawdown_warning'",
        (_now_iso(), level, episode))
    paused = []
    for m in fp.list_members(fleet["id"]):
        if m["status"] == trading_runs.STATUS_RUNNING:
            try:
                trading_runs.pause_run(m["id"], fleet["agent_id"],
                                       reason="drawdown_warning",
                                       paused_marker="drawdown_warning")
                paused.append(m["id"])
            except Exception:  # noqa: BLE001
                pass
    fp.emit_fleet_event(fleet["id"], "drawdown_warning",
                        {"loss_frac": round(loss_frac, 4), "level": level,
                         "episode": episode, "paused_members": paused})
    _alert(fleet, "fleet_drawdown_warning", "fleet_drawdown_warning",
           {"fleet_id": fleet["id"], "loss_pct": f"{loss_frac * 100:.0f}",
            "stop_loss_pct": f"{float(fleet['stop_loss_frac']) * 100:.0f}"},
           # per-episode dedupe: a fresh leg must not be swallowed by the 1h
           # window, and hovering must not re-send hourly
           dedupe=f"fleet:{fleet['id']}:warn:{episode}")


_EVAL_FAILURES: dict[int, int] = {}


def _bump_eval_failures(fleet: dict) -> int:
    """Consecutive eval-failure counter. In-process is correct here: the
    fleet lease makes supervision single-writer, and a worker restart
    resetting the count merely costs K more (frozen, safe) ticks before the
    escalation — the fail-safe direction. (A cache row was tried first, but
    cache no-ops without Redis and the counter silently never escalated.)"""
    n = _EVAL_FAILURES.get(fleet["id"], 0) + 1
    _EVAL_FAILURES[fleet["id"]] = n
    return n


def _reset_eval_failures(fleet: dict) -> None:
    _EVAL_FAILURES.pop(fleet["id"], None)


def _pause_entries(fleet: dict, reason: str) -> None:
    _update_fleet(fleet["id"], "entry_paused_reason = ?", (reason,))
    for m in fp.list_members(fleet["id"]):
        if m["status"] == trading_runs.STATUS_RUNNING:
            try:
                trading_runs.pause_run(m["id"], fleet["agent_id"],
                                       reason=reason,
                                       paused_marker="drawdown_warning")
            except Exception:  # noqa: BLE001
                pass


def _agent_deleted(agent_id: int) -> bool:
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM agents WHERE id = ?", (agent_id,))
        return cursor.fetchone() is None
    finally:
        conn.close()


# ── slot / replacement pass ─────────────────────────────────────────────────

def _slots(fleet_id: int) -> list[dict]:
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM fleet_slots WHERE fleet_id = ? "
                       "ORDER BY slot_index", (fleet_id,))
        return [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()


def _replacements_suspended(fleet: dict) -> bool:
    """STATE-based (round-5): warn latch fired-and-unacked, fleet paused/held,
    entry-pause, or account master hold."""
    if fleet["status"] != fp.STATUS_ACTIVE:
        return True
    if fleet.get("entry_paused_reason"):
        return True
    if fleet.get("warn_latched_at") and not fleet.get("warn_acked_at"):
        return True
    if fp._master_state(fleet["agent_id"]) == "held":
        return True
    return False


def _slot_pass(fleet: dict, members: list[dict], eq: dict) -> None:
    """Per-slot lifecycle: positions_held handling, dormancy re-evaluation,
    replacement per the per-reason table with sequential funding."""
    by_id = {m["id"]: m for m in members}
    total = float(fleet["total_budget_usd"])
    n = max(int(fleet["n_runs"]), 1)
    floor_usd = total / (2 * n)

    active_budget = 0.0
    for m in members:
        if m["status"] in ("armed", "running", "paused", "stopping"):
            try:
                cfg = json.loads(m.get("config_snapshot_json") or "{}")
                active_budget += float(cfg.get("run_budget_usd") or 0)
            except (ValueError, TypeError):
                pass
    headroom = eq["equity"] - active_budget - float(eq.get("zombie_basis") or 0)

    suspended = _replacements_suspended(fleet)
    replaced = 0
    non_terminal_symbols = {(m["market"], m["symbol"]) for m in members
                            if m["status"] != trading_runs.STATUS_STOPPED}

    for slot in _slots(fleet["id"]):
        state = slot["state"]
        if state == "closed":
            continue
        member = by_id.get(slot.get("current_run_id") or -1)

        # dormancy re-evaluates EVERY tick — never sticky
        if state == "dormant":
            if headroom >= floor_usd:
                fp._bind_slot(fleet["id"], slot["slot_index"],
                              slot.get("current_run_id"), "waiting")
                state = "waiting"
            else:
                continue

        if member is None:
            # E3 back-fill (2026-07-26): a slot that never got a run bound
            # (build-time skip — unpriceable symbol, start conflict) stayed
            # empty forever; "kept at N" must hold for under-fills too.
            if state not in ("active", "waiting"):
                continue
            if suspended:
                if state != "waiting":
                    fp._bind_slot(fleet["id"], slot["slot_index"], None,
                                  "waiting")
                continue
            funding = min(float(slot["original_allocation_usd"]), headroom)
            if funding < floor_usd:
                fp._bind_slot(fleet["id"], slot["slot_index"], None, "dormant")
                fp.emit_fleet_event(fleet["id"], "slot_dormant",
                                    {"slot": slot["slot_index"],
                                     "headroom": round(headroom, 2)})
                continue
            new_run_id = _build_replacement(fleet, slot, funding,
                                            exclude=non_terminal_symbols)
            if new_run_id:
                headroom -= funding
                replaced += 1
                non_terminal_symbols = {(m["market"], m["symbol"])
                                        for m in fp.list_members(fleet["id"])
                                        if m["status"] != trading_runs.STATUS_STOPPED}
            continue
        if member["status"] != trading_runs.STATUS_STOPPED:
            continue  # live member

        reason = member.get("status_reason") or ""

        if reason in fp.REPLACE_NEVER:
            if reason == "user_stop":
                fp._bind_slot(fleet["id"], slot["slot_index"], None, "closed")
                fp.emit_fleet_event(fleet["id"], "slot_closed",
                                    {"slot": slot["slot_index"],
                                     "reason": "user_stop"})
            continue

        if reason == "positions_held":
            # slot stays OCCUPIED: record the unowned-book baseline once;
            # eligible only when the zombie position is gone from the book
            if slot.get("zombie_baseline_qty") is None:
                baseline = _unowned_qty(member)
                zqty = _zombie_open_qty(member)
                fp._bind_slot(fleet["id"], slot["slot_index"], member["id"],
                              "waiting",
                              zombie_baseline_qty=max(0.0, baseline - zqty))
                fp.emit_fleet_event(fleet["id"], "slot_zombie",
                                    {"slot": slot["slot_index"],
                                     "run_id": member["id"]})
                continue
            if _unowned_qty(member) > float(slot["zombie_baseline_qty"]) + 1e-9:
                continue  # zombie still open — occupied, symbol excluded
            # zombie closed ⇒ fall through to replacement

        if reason in fp.REPLACE_DEFERRED:
            if reason == "synthetic_liquidation":
                _ensure_cooldown(member)
            if state != "waiting":
                fp._bind_slot(fleet["id"], slot["slot_index"], member["id"],
                              "waiting")
            if reason == "stop_eval_failed" and not _fresh_batch_exists():
                continue  # wait for a HEALTHY research batch
            # cooldowns exclude the symbol inside select_targets — a liquidated
            # symbol simply won't be picked until its window expires

        if suspended:
            if state != "waiting":
                fp._bind_slot(fleet["id"], slot["slot_index"],
                              member["id"], "waiting")
            continue

        # funding: min(original allocation, headroom), sequential
        funding = min(float(slot["original_allocation_usd"]), headroom)
        if funding < floor_usd:
            fp._bind_slot(fleet["id"], slot["slot_index"], member["id"],
                          "dormant")
            fp.emit_fleet_event(fleet["id"], "slot_dormant",
                                {"slot": slot["slot_index"],
                                 "headroom": round(headroom, 2)})
            continue

        new_run_id = _build_replacement(fleet, slot, funding,
                                        exclude=non_terminal_symbols)
        if new_run_id:
            headroom -= funding  # SEQUENTIAL: recompute within the pass
            replaced += 1
            non_terminal_symbols = {(m["market"], m["symbol"])
                                    for m in fp.list_members(fleet["id"])
                                    if m["status"] != trading_runs.STATUS_STOPPED}

    # E3 under-fill (2026-07-26): research found fewer candidates than N at
    # composition, so slots BEYOND the composed count never existed (fleet 18
    # sat at 1/8, fleet 16 at 4/9, forever). Create the deficit one slot per
    # pass — equal-share allocation, same sequential-headroom discipline —
    # and try to build into it immediately; an unfilled new slot becomes the
    # member-None back-fill case next pass.
    if not suspended:
        while True:
            slots_now = _slots(fleet["id"])
            if len(slots_now) >= n:
                break
            alloc = min(total / n, headroom)
            if alloc < floor_usd:
                break
            next_index = 1 + max((s["slot_index"] for s in slots_now),
                                 default=-1)
            conn = get_db_connection()
            try:
                cursor = conn.cursor()
                begin_write_transaction(cursor)
                cursor.execute(
                    "INSERT INTO fleet_slots (fleet_id, slot_index, "
                    "original_allocation_usd, state, updated_at) "
                    "VALUES (?, ?, ?, 'active', ?)",
                    (fleet["id"], next_index, round(alloc, 2), fp._now_iso()))
                conn.commit()
            finally:
                conn.close()
            fp.emit_fleet_event(fleet["id"], "slot_created",
                                {"slot": next_index,
                                 "allocation": round(alloc, 2),
                                 "reason": "underfill_backfill"})
            new_slot = {"slot_index": next_index,
                        "original_allocation_usd": round(alloc, 2),
                        "current_run_id": None}
            new_run_id = _build_replacement(fleet, new_slot, alloc,
                                            exclude=non_terminal_symbols)
            if not new_run_id:
                break  # no candidates — the waiting slot back-fills next pass
            headroom -= alloc
            replaced += 1
            non_terminal_symbols = {(m["market"], m["symbol"])
                                    for m in fp.list_members(fleet["id"])
                                    if m["status"] != trading_runs.STATUS_STOPPED}

    if replaced:
        _maybe_churn_alert(fleet)

    # status_reason reflects fill state (recomputed every pass — a hold or a
    # partial build must not leave a stale label)
    live = len([m for m in fp.list_members(fleet["id"])
                if m["status"] in ("armed", "running", "paused", "stopping")])
    if fleet["status"] == fp.STATUS_ACTIVE:
        if live < n:
            fp._set_status(fleet["id"], (fp.STATUS_ACTIVE,), fp.STATUS_ACTIVE,
                           f"replenishing:{live}/{n}")
        elif (fleet.get("status_reason") or "").startswith(("replenishing:",
                                                            "partial:")):
            fp._set_status(fleet["id"], (fp.STATUS_ACTIVE,), fp.STATUS_ACTIVE,
                           None)


def _unowned_qty(member: dict) -> float:
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """SELECT COALESCE(SUM(ABS(quantity)), 0) AS q FROM positions
               WHERE agent_id = ? AND market = ? AND symbol = ?
                 AND run_id IS NULL""",
            (member["agent_id"], member["market"], member["symbol"]))
        return float(cursor.fetchone()["q"] or 0)
    finally:
        conn.close()


def _zombie_open_qty(member: dict) -> float:
    z = fp._zombie_pnl(member)
    if z is None:
        return 0.0
    # open basis / avg would need avg; reuse replay quickly
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """SELECT side, quantity FROM signals
               WHERE run_id = ? AND message_type = 'operation' ORDER BY id""",
            (member["id"],))
        qty = 0.0
        for r in cursor.fetchall():
            q = float(r["quantity"] or 0)
            if r["side"] == "buy":
                qty += q
            elif r["side"] == "sell":
                qty -= min(q, qty)
            elif r["side"] == "short":
                qty -= q
            elif r["side"] == "cover":
                qty += min(q, -qty)
        return abs(qty)
    finally:
        conn.close()


def _ensure_cooldown(member: dict) -> None:
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        begin_write_transaction(cursor)
        cursor.execute(
            "SELECT id FROM fleet_symbol_cooldowns WHERE agent_id = ? AND "
            "market = ? AND symbol = ? AND source_run_id = ?",
            (member["agent_id"], member["market"], member["symbol"],
             member["id"]))
        if cursor.fetchone() is None:
            until = (_now_dt() + timedelta(
                hours=fp.LIQUIDATION_COOLDOWN_HOURS)).strftime(TS_FMT)
            cursor.execute(
                """INSERT INTO fleet_symbol_cooldowns
                   (agent_id, market, symbol, until_ts, source_run_id)
                   VALUES (?, ?, ?, ?, ?)""",
                (member["agent_id"], member["market"], member["symbol"],
                 until, member["id"]))
        conn.commit()
    finally:
        conn.close()


def _fresh_batch_exists() -> bool:
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT batch_id, created_at FROM research_batches "
                       "ORDER BY batch_id DESC LIMIT 1")
        row = cursor.fetchone()
        if not row:
            return False
        import symbol_research
        try:
            then = datetime.strptime(row["created_at"], TS_FMT).replace(
                tzinfo=timezone.utc)
        except (ValueError, TypeError):
            return False
        return (_now_dt() - then).total_seconds() < \
            2 * symbol_research.research_interval_seconds()
    finally:
        conn.close()


def _build_replacement(fleet: dict, slot: dict, funding: float,
                       exclude: set) -> Optional[int]:
    """One replacement via the same validated path as the initial build."""
    import symbol_research
    from routes_runs import RunIn, validate_run_payload, _probe_price

    agent_id = fleet["agent_id"]
    if fp._master_state(agent_id) == "held":
        return None
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        # Parity with the initial build (E3): open-markets scope so a slot is
        # never bound to a closed-market symbol overnight, and the expectancy
        # gate so a replacement can't sneak a negative-edge symbol past the
        # bar the composition enforced. Ask for a few, gate, take the best.
        theses = symbol_research.select_targets(
            cursor, agent_id, 3, exclude=exclude,
            markets_scope=fp._open_markets_scope())
    finally:
        conn.close()
    import backtest_gate
    if theses and backtest_gate.gate_enabled():
        kept, dropped = backtest_gate.gate_candidates(theses)
        if dropped:
            fp.emit_fleet_event(fleet["id"], "backtest_gate",
                                {"context": "replacement",
                                 "kept": [t["symbol"] for t in kept],
                                 "dropped": dropped})
        theses = kept
    if not theses:
        fp.emit_fleet_event(fleet["id"], "slot_waiting",
                            {"slot": slot["slot_index"],
                             "reason": "no_candidates"})
        fp._bind_slot(fleet["id"], slot["slot_index"],
                      slot.get("current_run_id"), "waiting")
        return None
    thesis = theses[0]
    settings = fp.compose_run_settings(thesis, funding, fleet)
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
            leverage=settings.get("leverage", 1.0), stop_flatten=True)
        core, start_c, stop_c = validate_run_payload(payload)
        core["thesis"] = dict(settings["thesis"])
        core["thesis"]["entry_ref_price"] = _probe_price(core["symbol"],
                                                         core["market"])
        core["feedback"] = True
        core["add_limits"] = dict(settings.get("add_limits") or {})
        run_id = trading_runs.create_run(agent_id, core, start_c, stop_c, True,
                                         fleet_id=fleet["id"],
                                         created_via="fleet")
        trading_runs.start_run(run_id, agent_id)
    except Exception as exc:  # noqa: BLE001
        if run_id:
            try:
                trading_runs.delete_run(run_id, agent_id)
            except Exception:  # noqa: BLE001
                pass
        fp.emit_fleet_event(fleet["id"], "candidate_skipped",
                            {"slot": slot["slot_index"],
                             "reason": str(exc)[:300]})
        return None
    fp._bind_slot(fleet["id"], slot["slot_index"], run_id, "active")
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        begin_write_transaction(cursor)
        cursor.execute(
            """INSERT INTO fleet_candidates
               (fleet_id, thesis_key, slot_index, allocation_usd, state,
                run_id, created_at) VALUES (?, ?, ?, ?, 'rotated_in', ?, ?)""",
            (fleet["id"],
             f"{thesis.get('batch_id')}:{thesis['market']}:{thesis['symbol']}",
             slot["slot_index"], funding, run_id, _now_iso()))
        conn.commit()
    finally:
        conn.close()
    fp.emit_fleet_event(fleet["id"], "rotation",
                        {"slot": slot["slot_index"], "run_id": run_id,
                         "symbol": thesis["symbol"], "market": thesis["market"],
                         "funding": round(funding, 2)})
    return run_id


def _maybe_churn_alert(fleet: dict) -> None:
    """>8 replacements today per user ⇒ informational alert, never a block."""
    day_start = _now_dt().strftime("%Y-%m-%dT00:00:00Z")
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """SELECT COUNT(*) AS n FROM fleet_events fe
               JOIN fleets f ON f.id = fe.fleet_id
               JOIN agents a ON a.id = f.agent_id
               WHERE a.user_id = (SELECT user_id FROM agents WHERE id = ?)
                 AND fe.event_type = 'rotation' AND fe.ts >= ?""",
            (fleet["agent_id"], day_start))
        n = int(cursor.fetchone()["n"] or 0)
    finally:
        conn.close()
    if n > fp.FLEET_BOUNDS["churn_alert_per_day"]:
        _alert(fleet, "fleet_churn", "fleet_churn",
               {"fleet_id": fleet["id"], "n": n},
               dedupe=f"fleet:{fleet['id']}:churn:{day_start}")
