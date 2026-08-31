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
import os
import re
import time
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
            reason = fleet.get("status_reason") or "user_stop"
            fp._set_status(fleet["id"], (fp.STATUS_STOPPING,), fp.STATUS_STOPPED,
                           reason)
            out["stopped"] = True
            if reason == "profit_target_hit":
                succ = _spawn_successor(fleet)
                if succ:
                    out["successor_fleet_id"] = succ
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

    # ── GOAL: fleet-level take-profit. A gain shows up as a NEGATIVE
    # loss_frac clamp, so read the equity directly. Checked after the loss
    # rails so a breach can never be mistaken for a gain.
    target = fleet.get("profit_target_frac")
    if target and total > 0:
        gain_frac = (eq["equity"] - total) / total
        if gain_frac >= float(target):
            _harvest(fleet, gain_frac)
            return {**out, "profit_target": True, "gain_frac": round(gain_frac, 4)}

    # ── TIER 1: episode-latched warning
    _warning_tier(fleet, loss_frac)

    # refresh view after possible warning writes
    fleet = fp.get_fleet(fleet["id"]) or fleet

    # ── H-CONSOL (owner 2026-08-27): consolidate toward FLEET_TARGET_SLOTS.
    # Machine lowering only — the existing drain semantics (excess slots
    # retire as they empty, a live position is never touched) are unchanged.
    # OWNER 2026-08-31 ("when user make trading count, must be keep that"):
    # a fleet whose size the user chose (user_size_cap set — every fleet,
    # since creation now pins it) is NEVER consolidated. Kill switch: unset
    # the env.
    tgt = _target_slots()
    if (tgt > 0 and int(fleet["n_runs"]) > tgt
            and fleet.get("user_size_cap") is None):
        try:
            fp.set_fleet_size(fleet["id"], tgt)
            fleet = fp.get_fleet(fleet["id"]) or fleet
            out["consolidated_to"] = tgt
        except Exception:  # noqa: BLE001 — consolidation must never wedge supervision
            logger.exception("consolidation resize failed (fleet %s)",
                             fleet["id"])

    # ── slot bookkeeping + replacement (suspended while warned/paused/held)
    _slot_pass(fleet, members, eq)

    # ── Plan 23 pre-live: swing book-level overnight cap (no-op for short
    # fleets and outside the pre-close window)
    try:
        _swing_overnight_cap_pass(fleet, eq)
    except Exception:  # noqa: BLE001
        logger.exception("overnight cap pass failed (fleet %s)", fleet["id"])
    return out


# ── Plan 23: swing book-level overnight cap ────────────────────────────────
OVERNIGHT_CAP_FRAC = 0.025          # Σ notional_i × G_i ≤ 2.5% of equity
OVERNIGHT_CAP_WEEKEND_FACTOR = 0.6  # entering Fri/holiday close: tighten
OVERNIGHT_CAP_WINDOW_MIN = 20       # act inside the last N session minutes


def _swing_overnight_cap_pass(fleet: dict, eq: dict) -> None:
    """Near the close, bound the swing book's modeled one-night loss:
    Σ(notionalᵢ × Gᵢ) ≤ 2.5% of marked equity (×0.6 into a Friday close).
    Excess is REDUCED from the largest contributor down — never dumped.
    Idempotent within the window: once under the cap, later passes no-op.
    G comes from each run's frozen thesis (swing_g_frac), floored at the
    build-time 3% so a missing stamp can only OVERSTATE risk, not hide it."""
    if (fleet.get("archetype") or "short") != "swing":
        return
    import markets as _mkts
    left = _mkts.session_minutes_left("us-stock")
    if not (0 < left <= OVERNIGHT_CAP_WINDOW_MIN):
        return
    equity = float((eq or {}).get("equity") or 0)
    if equity <= 0:
        return
    limit = OVERNIGHT_CAP_FRAC * equity
    from datetime import datetime as _dt
    from zoneinfo import ZoneInfo as _zi
    if _dt.now(_zi("America/New_York")).weekday() >= 4:   # Fri (holidays: the
        limit *= OVERNIGHT_CAP_WEEKEND_FACTOR             # calendar shuts them)
    contributions = []
    for m in fp.list_members(fleet["id"]):
        if m["status"] not in (trading_runs.STATUS_RUNNING,
                               trading_runs.STATUS_PAUSED):
            continue
        run = trading_runs.get_run(m["id"], fleet["agent_id"])
        if not run:
            continue
        conn = get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """SELECT quantity, current_price FROM positions
                   WHERE agent_id = ? AND market = ? AND symbol = ?
                     AND run_id = ? AND quantity != 0""",
                (fleet["agent_id"], run["market"], run["symbol"], run["id"]))
            pos = cur.fetchone()
        finally:
            conn.close()
        if not pos or not pos["current_price"]:
            continue
        qty = float(pos["quantity"])
        price = float(pos["current_price"])
        notional = abs(qty) * price
        try:
            g = float(json.loads(run.get("config_snapshot_json") or "{}")
                      .get("thesis", {}).get("swing_g_frac") or 0)
        except (ValueError, TypeError):
            g = 0.0
        g = max(g, fp.SWING_G_FLOOR)
        contributions.append({"run": run, "qty": qty, "price": price,
                              "notional": notional, "g": g,
                              "risk": notional * g})
    total_risk = sum(c["risk"] for c in contributions)
    if total_risk <= limit:
        return
    excess = total_risk - limit
    reduced = []
    from automation import execute_paper_trade
    for c in sorted(contributions, key=lambda x: -x["risk"]):
        if excess <= 0:
            break
        cut_risk = min(c["risk"], excess)
        cut_qty = min(abs(c["qty"]), cut_risk / (c["price"] * c["g"]))
        if cut_qty <= 0:
            continue
        side = "cover" if c["qty"] < 0 else "sell"
        run = c["run"]
        sig, skip = execute_paper_trade(
            fleet["agent_id"], run["symbol"], run["market"], side,
            cut_qty, c["price"],
            content=f"Fleet #{fleet['id']} overnight gap-risk cap: reducing "
                    f"before the close (never dumped)",
            run_id=run["id"],
            client_order_id=f"fleet:{fleet['id']}:overnight-cap:{run['id']}:"
                            f"{_now_iso()[:10]}")
        if sig:
            excess -= cut_qty * c["price"] * c["g"]
            reduced.append({"run_id": run["id"], "symbol": run["symbol"],
                            "cut_qty": round(cut_qty, 6),
                            "side": side})
    if reduced:
        fp.emit_fleet_event(fleet["id"], "overnight_cap",
                            {"limit_usd": round(limit, 2),
                             "risk_before_usd": round(total_risk, 2),
                             "reduced": reduced})


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

def _harvest(fleet: dict, gain_frac: float) -> None:
    """Fleet reached its profit goal: flatten every member and finalize as
    profit_target_hit. The successor is spawned only once every member is
    terminal (one non-terminal fleet per user), from the finalize hook."""
    for m in fp.list_members(fleet["id"]):
        if m["status"] in (trading_runs.STATUS_RUNNING, trading_runs.STATUS_PAUSED,
                           trading_runs.STATUS_ARMED):
            try:
                if m["status"] == trading_runs.STATUS_ARMED:
                    trading_runs._transition(m["id"], fleet["agent_id"],
                                             (trading_runs.STATUS_ARMED,),
                                             trading_runs.STATUS_STOPPED,
                                             "fleet_profit_target",
                                             clear_active_key=True)
                else:
                    trading_runs.request_stop(m["id"], fleet["agent_id"],
                                              flatten=True,
                                              reason="fleet_profit_target")
            except Exception:  # noqa: BLE001
                pass
    fp.emit_fleet_event(fleet["id"], "profit_target",
                        {"gain_frac": round(gain_frac, 4),
                         "profit_target_frac": fleet["profit_target_frac"]})
    fp._set_status(fleet["id"], fp._NON_TERMINAL, fp.STATUS_STOPPING,
                   "profit_target_hit")
    _alert(fleet, "fleet_profit_target", "fleet_profit_target",
           {"fleet_id": fleet["id"], "gain_pct": f"{gain_frac * 100:.1f}"},
           dedupe=f"fleet:{fleet['id']}:profit_target")


def _spawn_successor(fleet: dict) -> Optional[int]:
    """Start the same trading again: a fresh fleet with identical settings.
    Profit is HARVESTED — the successor gets the original budget, so gains
    stay banked as cash instead of silently compounding position size.
    Idempotent via fleets.successor_fleet_id; fail-soft (a spawn problem must
    never leave the harvested fleet in a broken state)."""
    if fleet.get("successor_fleet_id"):
        return None
    try:
        scope = None
        if fleet.get("market_scope_json"):
            scope = json.loads(fleet["market_scope_json"])
    except (ValueError, TypeError):
        scope = None
    try:
        new_id = fp.create_fleet(
            fleet["agent_id"], int(fleet["n_runs"]),
            float(fleet["total_budget_usd"]),
            risk_appetite=fleet.get("risk_appetite") or "balanced",
            market_scope=scope, provider=fleet.get("provider"),
            lang=fleet.get("lang") or "en",
            warn_loss_frac=float(fleet["warn_loss_frac"]),
            stop_loss_frac=float(fleet["stop_loss_frac"]),
            name=fleet.get("name"),
            leverage=fleet.get("leverage"),
            profit_target_frac=fleet.get("profit_target_frac"))
        fp.start_fleet(new_id, fleet["agent_id"])
    except Exception as exc:  # noqa: BLE001
        logger.warning("successor spawn failed for fleet %s: %s",
                       fleet["id"], exc)
        fp.emit_fleet_event(fleet["id"], "successor_failed",
                            {"error": str(exc)[:200]})
        return None
    _update_fleet(fleet["id"], "successor_fleet_id = ?", (new_id,))
    fp.emit_fleet_event(fleet["id"], "successor_started",
                        {"successor_fleet_id": new_id,
                         "budget": float(fleet["total_budget_usd"])})
    return new_id


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
                                              flatten=True,
                                              reason="fleet_breaker")
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
    """Marks are readable again — clear the counter AND release the freeze.

    The release half was missing and it deadlocked live (2026-07-28, fleet 20).
    An eval freeze pauses members with the `drawdown_warning` marker but never
    latches `warn_latched_at`, and BOTH un-pause paths are gated on that latch:
    the automatic one sits inside the drawdown-recovery branch, and
    `ack_warning` refuses outright with "no drawdown warning is active". So a
    fleet frozen for unreadable marks stayed paused after the marks recovered,
    with no path back — automatic or manual. Runs 125/127/128 sat paused for
    ~53 minutes holding a live ZEC short while the fleet itself read `active`.

    Recovery is symmetric with the drawdown branch: clear the flag, un-pause
    only what THIS freeze paused. A member paused by a real drawdown warning
    keeps its latch and is left alone.
    """
    _EVAL_FAILURES.pop(fleet["id"], None)
    if (fleet.get("entry_paused_reason") or "") != "eval_failed":
        return
    _update_fleet(fleet["id"], "entry_paused_reason = NULL", ())
    resumed = []
    for m in fp.list_members(fleet["id"]):
        if m["status"] == trading_runs.STATUS_PAUSED and \
                (m.get("status_reason") or "") == "eval_failed":
            try:
                trading_runs.resume_run(m["id"], fleet["agent_id"])
                resumed.append(m["id"])
            except Exception:  # noqa: BLE001 — one stuck member must not block the rest
                pass
    fp.emit_fleet_event(fleet["id"], "eval_recovered", {"resumed_members": resumed})


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

_EMPTY_SLOT_RETRY_SECONDS = max(60, int(__import__("os").getenv("FLEET_EMPTY_SLOT_RETRY_SECONDS", "300")))


# (fleet_id, slot_index) -> monotonic seconds of the last build attempt that
# found nothing buildable. Keyed on the ATTEMPT, not on slot state: a slot
# waiting for another reason (suspension lifted, batch healthy again) must
# still replace on the very next pass.
_LAST_EMPTY_ATTEMPT: dict[tuple, float] = {}


def _retry_cooling(fleet_id: int, slot_index: int) -> bool:
    """True while a slot whose last build attempt found nothing is inside its
    retry cooldown — re-probing every 60s tick burns feed calls and journal
    rows for a universe that is simply exhausted."""
    last = _LAST_EMPTY_ATTEMPT.get((fleet_id, slot_index))
    if last is None:
        return False
    return (time.monotonic() - last) < _EMPTY_SLOT_RETRY_SECONDS


def _note_build_attempt(fleet_id: int, slot_index: int, built: bool) -> None:
    key = (fleet_id, slot_index)
    if built:
        _LAST_EMPTY_ATTEMPT.pop(key, None)
    else:
        _LAST_EMPTY_ATTEMPT[key] = time.monotonic()


# Guarded parse (R12 adversarial pass): an unguarded int() here raised at
# IMPORT time on a garbage env value, and because this module imports inside
# the fleet tick, one typo killed the whole supervision layer — rails,
# brake, breaker, replacement — while the watchdog's own death in the same
# module kept the failure silent. A bad value now falls back like the
# run_engine heartbeat does.
try:
    _STATUS_HEARTBEAT_SECONDS = max(
        60, int(os.getenv("FLEET_STATUS_HEARTBEAT_SECONDS", "1800")))
except (TypeError, ValueError):
    _STATUS_HEARTBEAT_SECONDS = 1800


# fleet_id -> monotonic seconds of the last replenishing status write. The
# fill-state label is recomputed every pass; a CHANGED reason always writes
# through (monitoring reads the transitions), an UNCHANGED one re-stamps at
# most once per heartbeat — fleet 31 wrote `replenishing:16/25` on every
# ~62s pass, 1,385 identical fleet_status rows in a day (R12). Worker
# restart resets the map: the first pass re-stamps once, which is fine.
_LAST_STATUS_EMIT: dict[int, float] = {}


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


def _target_slots() -> int:
    """H-CONSOL (owner 2026-08-27): FLEET_TARGET_SLOTS > 0 makes the
    supervisor consolidate every active fleet DOWN toward this slot count.
    The ZI control (research/zi_control_replay.py) measured that even
    long-only random entries lose after rails+fees at the current per-slot
    size — the entry deadlock is structural, so fewer/bigger slots.
    Kill switch: unset/0. Lowering only — growth stays with the user and
    auto-tune paths."""
    try:
        return int(os.environ.get("FLEET_TARGET_SLOTS", "0") or "0")
    except ValueError:
        return 0


def _slot_anchor(slot: dict, total: float, n: int) -> float:
    """The dollar figure a slot's funding aims for. The designed allocation,
    unless consolidation is on — then at least the CURRENT equal share
    (total/n): the resize drain deletes emptied excess slots but never
    re-anchors survivors, so without this a consolidation is cosmetic —
    the remaining slots would keep their old small allocations forever."""
    orig = float(slot["original_allocation_usd"])
    if _target_slots() > 0:
        return max(orig, total / max(n, 1))
    return orig


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

    # Resize drain (2026-08-08): when the user lowered n_runs below the
    # current slot count, excess slots retire AS THEY EMPTY — a live
    # position is never touched. Drained slots are DELETED, not closed:
    # 'closed' is the user-stop verdict and deliberately never refills,
    # while a drained slot must be recreatable if the user raises N again.
    open_slots = [s for s in _slots(fleet["id"]) if s["state"] != "closed"]
    drain_excess = max(0, len(open_slots) - n)

    for slot in _slots(fleet["id"]):
        state = slot["state"]
        if state == "closed":
            continue
        member = by_id.get(slot.get("current_run_id") or -1)
        # Vol-parity slots (live 2026-08-12, fleet 32): allocations can sit
        # far below the equal share ($500–$1,580 on a $99,999/10 fleet whose
        # equal-share floor is $5,000) while being fully fundable. The floor
        # a slot must clear is the smaller of the equal-share floor and half
        # its OWN designed allocation — dormancy means "headroom can't fund
        # this slot", never "this slot was designed small".
        slot_floor = min(floor_usd,
                         _slot_anchor(slot, total, n) / 2.0)

        if drain_excess > 0 and (
                member is None
                or (member["status"] == trading_runs.STATUS_STOPPED
                    and (member.get("status_reason") or "") != "positions_held")):
            conn = get_db_connection()
            try:
                cursor = conn.cursor()
                begin_write_transaction(cursor)
                cursor.execute(
                    "DELETE FROM fleet_slots WHERE fleet_id = ? "
                    "AND slot_index = ?",
                    (fleet["id"], slot["slot_index"]))
                conn.commit()
            finally:
                conn.close()
            fp.emit_fleet_event(fleet["id"], "slot_removed",
                                {"slot": slot["slot_index"],
                                 "reason": "fleet_resized"})
            drain_excess -= 1
            continue

        # dormancy re-evaluates EVERY tick — never sticky
        if state == "dormant":
            if headroom >= slot_floor:
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
            if _retry_cooling(fleet["id"], slot["slot_index"]):
                continue
            if suspended:
                if state != "waiting":
                    fp._bind_slot(fleet["id"], slot["slot_index"], None,
                                  "waiting")
                continue
            funding = min(_slot_anchor(slot, total, n), headroom)
            if funding < slot_floor:
                fp._bind_slot(fleet["id"], slot["slot_index"], None, "dormant")
                fp.emit_fleet_event(fleet["id"], "slot_dormant",
                                    {"slot": slot["slot_index"],
                                     "headroom": round(headroom, 2)})
                continue
            new_run_id = _build_replacement(fleet, slot, funding,
                                            exclude=non_terminal_symbols,
                                            already_waiting=(state == "waiting"))
            _note_build_attempt(fleet["id"], slot["slot_index"], bool(new_run_id))
            if new_run_id:
                headroom -= funding
                replaced += 1
                non_terminal_symbols = {(m["market"], m["symbol"])
                                        for m in fp.list_members(fleet["id"])
                                        if m["status"] != trading_runs.STATUS_STOPPED}
            continue
        if member["status"] != trading_runs.STATUS_STOPPED:
            continue  # live member
        if _retry_cooling(fleet["id"], slot["slot_index"]):
            continue  # last attempt found nothing — don't re-probe every tick

        reason = member.get("status_reason") or ""

        if reason in fp.REPLACE_NEVER:
            if reason in fp.SLOT_CLOSING:
                fp._bind_slot(fleet["id"], slot["slot_index"], None, "closed")
                fp.emit_fleet_event(fleet["id"], "slot_closed",
                                    {"slot": slot["slot_index"],
                                     "reason": reason})
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

        # vary-on-idle (2026-08-04): a member that idle-retired NEVER traded —
        # replacing it with the same symbol rebuilds the same idleness (939/
        # 940 held ~43 cycles each and were parity-eligible for rebuild). The
        # cooldown row makes select_targets pick a different name for half a
        # day; replacement itself stays immediate.
        if reason == "idle_retired":
            _ensure_cooldown(member, hours=fp.IDLE_SYMBOL_COOLDOWN_HOURS)

        # vary-on-refusal (2026-08-13): a desk that retires a run it NEVER
        # traded refused the THESIS, not the timing. Live, 11:30Z shoulder:
        # UBER was rebuilt 20 seconds after its desk retired it as
        # unexpressable ("invalidation level sits at the current price") and
        # the rebuild re-reached the identical verdict in 4 minutes — three
        # consecutive desk-retires on one symbol, WMT and SBUX a step
        # behind, each loop burning a build plus LLM decisions. Same class
        # as vary-on-idle, one door over. Gated on zero trade legs so a
        # desk banking out of a traded position never benches its symbol.
        if reason == "desk_retired" and not _ever_traded(member):
            _ensure_cooldown(member, hours=fp.IDLE_SYMBOL_COOLDOWN_HOURS)

        # vary-on-loss (2026-08-07): a member stopped by a LOSS stop-event was
        # wrong on today's tape. Without a cooldown the very next tick rebuilds
        # the same symbol with a fresh loss meter — three consecutive ADBE runs
        # lost -1.30 combined (999 -0.40, 1000 -0.21, 1001 rebuilt 34 seconds
        # later, -0.69) while each stayed inside the per-run -0.99 floor.
        # Gated on realized < 0 so a PROFITABLE stop (a trailing lock banking
        # a win) does not bench its symbol.
        if str(reason).startswith("stop_event:"):
            try:
                lost = float(member.get("realized_pnl_usd") or 0) < 0
            except (TypeError, ValueError):
                lost = False
            if lost:
                _ensure_cooldown(member, hours=fp.LOSS_SYMBOL_COOLDOWN_HOURS)

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
        funding = min(_slot_anchor(slot, total, n), headroom)
        if funding < slot_floor:
            fp._bind_slot(fleet["id"], slot["slot_index"], member["id"],
                          "dormant")
            fp.emit_fleet_event(fleet["id"], "slot_dormant",
                                {"slot": slot["slot_index"],
                                 "headroom": round(headroom, 2)})
            continue

        new_run_id = _build_replacement(fleet, slot, funding,
                                        exclude=non_terminal_symbols,
                                        already_waiting=(state == "waiting"))
        _note_build_attempt(fleet["id"], slot["slot_index"], bool(new_run_id))
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
        prev_reason = fleet.get("status_reason") or ""
        if live < n:
            reason = f"replenishing:{live}/{n}"
            last = _LAST_STATUS_EMIT.get(fleet["id"])
            if (reason != prev_reason or last is None
                    or time.monotonic() - last >= _STATUS_HEARTBEAT_SECONDS):
                fp._set_status(fleet["id"], (fp.STATUS_ACTIVE,),
                               fp.STATUS_ACTIVE, reason)
                _LAST_STATUS_EMIT[fleet["id"]] = time.monotonic()
        elif prev_reason.startswith(("replenishing:", "partial:")):
            fp._set_status(fleet["id"], (fp.STATUS_ACTIVE,), fp.STATUS_ACTIVE,
                           None)
            _LAST_STATUS_EMIT.pop(fleet["id"], None)
        # an under-target fleet grew this pass (markets opened / research
        # qualified) — tell the member, mirroring the partial-build notice
        m = re.match(r"(?:replenishing|partial):(\d+)/", prev_reason)
        if m and live > int(m.group(1)):
            _alert(fleet, "fleet_slots_filled", "fleet_slots_filled",
                   {"fleet_id": fleet["id"], "live": live, "n": n},
                   dedupe=f"fleet:{fleet['id']}:slots_filled")


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


def _ever_traded(member: dict) -> bool:
    """One trade event is enough. Fails CLOSED to True — a query problem can
    only skip the cooldown, never bench a symbol the desk actually traded."""
    try:
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM run_events WHERE run_id = ? AND "
                           "event_type = 'trade' LIMIT 1", (member["id"],))
            return cursor.fetchone() is not None
        finally:
            conn.close()
    except Exception:  # noqa: BLE001
        return True


def _ensure_cooldown(member: dict, hours: float | None = None) -> None:
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
                hours=hours or fp.LIQUIDATION_COOLDOWN_HOURS)).strftime(TS_FMT)
            cursor.execute(
                """INSERT INTO fleet_symbol_cooldowns
                   (agent_id, market, symbol, until_ts, source_run_id)
                   VALUES (?, ?, ?, ?, ?)""",
                (member["agent_id"], member["market"], member["symbol"],
                 until, member["id"]))
        conn.commit()
    finally:
        conn.close()


def _cooldown_blocked_symbol(agent_id: int, market: str, symbol: str,
                             hours: float = 6.0) -> None:
    """Retire a symbol the builder cannot use for a durable reason (e.g. an
    open position outside any run blocks it). Without this the replacement
    loop re-picks the same blocked name every tick forever — fleet 23 spent
    an hour at 6/10 retrying SOLUSDT (2026-07-31). No source_run_id: the
    block belongs to no run."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        begin_write_transaction(cursor)
        cursor.execute(
            "SELECT id FROM fleet_symbol_cooldowns WHERE agent_id = ? AND "
            "market = ? AND symbol = ? AND until_ts > ?",
            (agent_id, market, symbol, _now_iso()))
        if cursor.fetchone() is None:
            until = (_now_dt() + timedelta(hours=hours)).strftime(TS_FMT)
            cursor.execute(
                """INSERT INTO fleet_symbol_cooldowns
                   (agent_id, market, symbol, until_ts, source_run_id)
                   VALUES (?, ?, ?, ?, NULL)""",
                (agent_id, market, symbol, until))
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


def _replacement_depth() -> int:
    """How many candidates a replacement considers before giving up.

    Every gate downstream only ever REMOVES, so this is the ceiling on how
    many rejections a slot can absorb and still fill."""
    try:
        return max(1, int(os.getenv("FLEET_REPLACEMENT_DEPTH", "10")))
    except ValueError:
        return 10


# fleet_id -> (candidate-pool fingerprint, monotonic-enough wall time of the
# last attempt that gated to nothing). Process-local by design: a worker
# restart simply re-gates once, which is the safe direction.
_REGATE_MEMO: dict[int, tuple[tuple, float]] = {}


def _regate_backoff_min() -> float:
    try:
        return float(os.environ.get("REPLACEMENT_REGATE_MIN", "15"))
    except ValueError:
        return 15.0


def _build_replacement(fleet: dict, slot: dict, funding: float,
                       exclude: set, already_waiting: bool = False) -> Optional[int]:
    """One replacement via the same validated path as the initial build."""
    import symbol_research

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
        #
        # Depth (2026-07-28): asking for 3 assumed the gates reject rarely.
        # They do not. Live: the batch's top three were NG, SOLUSDT, USDKRW —
        # the fee gate dropped USDKRW, the expectancy gate dropped NG, and
        # SOLUSDT was refused because an unowned position already held the
        # symbol. Nothing built, while SEVEN feasible candidates (ETHUSDT, GM,
        # VZ, T, SPCX, 601288.SS, 601899.SS) sat below the cut and were never
        # looked at. Same lesson as E3's junk-top-pick fix, one layer up: the
        # FETCH has to be deeper than the rejection rate, not just the retry.
        #
        # Scope (live 2026-08-12, fleet 31): the fleet's explicit market
        # scope is part of the mandate. Passing only the open-markets bias
        # offered a us-stock fleet crypto/forex candidates every tick — all
        # rejected downstream, 2/25 forever. Explicit scope is honoured
        # VERBATIM, exactly like the initial build (owner 2026-08-12: the
        # fleet keeps its defined slot count even while its market is
        # closed) — a run built overnight is safe by design: idle-retire
        # counts only open-market cycles (_closed_market_cycles), stops go
        # dormant on frozen marks, and flattens queue to the next open. The
        # open-markets bias applies only to unrestricted fleets.
        scope = None
        if fleet.get("market_scope_json"):
            try:
                scope = json.loads(fleet["market_scope_json"]) or None
            except (ValueError, TypeError):
                scope = None
        theses = symbol_research.select_targets(
            cursor, agent_id, _replacement_depth(), exclude=exclude,
            markets_scope=scope or fp._open_markets_scope())
    finally:
        conn.close()
    # Regate back-off (live 2026-08-13, fleet 31): the per-slot
    # _LAST_EMPTY_ATTEMPT cooldown holds, but nine empty slots each
    # re-asked the IDENTICAL per-pool question every 300s — 1,342 repeat
    # gate events in six hours (9 slots × 72 cooldown expiries × 2 events).
    # The verdict is a function of (pool, gate config), not of the slot, so
    # it is memoized per fleet: an unchanged pool that gated to nothing is
    # skipped silently until the window expires or the fingerprint changes.
    # A new research batch, an expired thesis, a freed symbol, or a gate
    # being switched re-gates immediately.
    import backtest_gate
    pool_key = (tuple(sorted(
        f"{t.get('thesis_key') or t.get('id')}" for t in theses)),
        bool(backtest_gate.gate_enabled()))
    memo = _REGATE_MEMO.get(fleet["id"])
    if (memo and memo[0] == pool_key
            and time.time() - memo[1] < _regate_backoff_min() * 60.0):
        fp._bind_slot(fleet["id"], slot["slot_index"],
                      slot.get("current_run_id"), "waiting")
        return None
    # Fee feasibility, the third gate the initial build applies
    # (fleet_planner._do_build). It was missed when E3 ported parity, and the
    # replacement path shipped with only two of three: prod runs 129/130/131
    # were each built into a permanent fee_edge block and held $3,399 between
    # them. The expectancy gate below cannot catch this class — it needs
    # FLEET_EXPECTANCY_MIN_TRADES closed runs, so a fresh symbol like USDZAR is
    # presumed innocent. This one is pure arithmetic on the frozen thesis.
    # select_targets returns research_theses rows verbatim, so the candidate
    # IS the thesis — expected_move_pct sits at the top level, same shape
    # _thesis_fee_infeasible reads on the build path.
    if theses:
        feasible, infeasible = [], {}
        for t in theses:
            why = fp._thesis_fee_infeasible(t)
            if why:
                infeasible[t["symbol"]] = why
            else:
                feasible.append(t)
        if infeasible:
            fp.emit_fleet_event(fleet["id"], "fee_gate",
                                {"context": "replacement",
                                 "kept": [t["symbol"] for t in feasible],
                                 "dropped": infeasible})
        theses = feasible
    # Plan 23 Phase C: swing universe + gap gate (no-op for short fleets).
    if theses:
        theses, sw_dropped = fp.swing_gate_candidates(fleet, theses)
        if sw_dropped:
            fp.emit_fleet_event(fleet["id"], "swing_gate",
                                {"context": "replacement",
                                 "dropped": sw_dropped})
    # Maturity gate (2026-08-13, SPCX class): young listings out of every
    # non-swing us-stock replacement — see fp.usstock_maturity_gate.
    if theses:
        theses, my_dropped = fp.usstock_maturity_gate(fleet, theses)
        if my_dropped:
            fp.emit_fleet_event(fleet["id"], "maturity_gate",
                                {"context": "replacement",
                                 "dropped": my_dropped})
    if theses and backtest_gate.gate_enabled():
        kept, dropped = backtest_gate.gate_candidates(theses)
        if dropped:
            fp.emit_fleet_event(fleet["id"], "backtest_gate",
                                {"context": "replacement",
                                 "kept": [t["symbol"] for t in kept],
                                 "dropped": dropped})
        theses = kept
    if not theses:
        # Everything gated away — remember the pool so the next attempts
        # (this pass's other slots, and every tick inside the window) skip
        # the identical re-gate instead of re-emitting the same verdict.
        _REGATE_MEMO[fleet["id"]] = (pool_key, time.time())
        if not already_waiting:      # journal the transition, not every tick
            fp.emit_fleet_event(fleet["id"], "slot_waiting",
                                {"slot": slot["slot_index"],
                                 "reason": "no_candidates"})
        fp._bind_slot(fleet["id"], slot["slot_index"],
                      slot.get("current_run_id"), "waiting")
        return None
    _REGATE_MEMO.pop(fleet["id"], None)
    # E3: iterate candidates — a junk top pick (unpriceable ALLO, live
    # 2026-07-26) must not block the slot while a buildable one waits below.
    thesis = run_id = None
    last_exc = None
    for candidate in theses:
        try:
            run_id = _try_build(fleet, candidate, funding)
            thesis = candidate
            break
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            reason = str(exc)
            # A position outside any run blocks this symbol until a human or
            # the desk closes it — durable, not transient. Cool it down so
            # the next pass surfaces other names instead of re-picking it
            # every tick.
            cooled = "outside any run" in reason
            if cooled:
                _cooldown_blocked_symbol(fleet["agent_id"],
                                         candidate.get("market") or "",
                                         candidate.get("symbol") or "")
            fp.emit_fleet_event(fleet["id"], "candidate_skipped",
                                {"slot": slot["slot_index"],
                                 "symbol": candidate.get("symbol"),
                                 "cooldown": cooled,
                                 "reason": reason[:300]})
    if run_id is None:
        if not already_waiting:      # journal the transition, not every tick
            fp.emit_fleet_event(fleet["id"], "slot_waiting",
                                {"slot": slot["slot_index"],
                                 "reason": "all_candidates_failed",
                                 "last_error": str(last_exc)[:200] if last_exc else None})
        fp._bind_slot(fleet["id"], slot["slot_index"],
                      slot.get("current_run_id"), "waiting")
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


def _try_build(fleet: dict, thesis: dict, funding: float) -> int:
    """Create+start one run for a candidate thesis (raises on any failure —
    unpriceable symbol, validation, start conflict; caller iterates)."""
    from routes_runs import RunIn, validate_run_payload, _probe_price

    agent_id = fleet["agent_id"]
    settings = fp.compose_run_settings(thesis, funding, fleet)
    # R15 bracket feasibility — parity with the initial build (the fee gate
    # was once missed on this path and shipped three permanently-blocked
    # runs). Raising here feeds _build_replacement's normal candidate loop:
    # candidate_skipped is journaled and the slot tries the next name.
    bracket = fp.bracket_infeasible(thesis, settings)
    if bracket:
        raise ValueError(bracket)
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
        fp.carry_snapshot_stamps(core, settings)
        run_id = trading_runs.create_run(agent_id, core, start_c, stop_c, True,
                                         fleet_id=fleet["id"],
                                         created_via="fleet")
        trading_runs.start_run(run_id, agent_id)
        return run_id
    except Exception:
        if run_id:
            try:
                trading_runs.delete_run(run_id, agent_id)
            except Exception:  # noqa: BLE001
                pass
        raise


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
