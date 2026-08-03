"""Step-trading feedback loop (Plan 14 §7) — outcome → next-step adaptation.

Runs at the START of every claimed cycle, before pre-gates, before any LLM.
Every closing leg (sell/cover, net of fees) since the last processed signal
is classified win/loss and drives a deterministic policy:

- ANTI-MARTINGALE BY CONSTRUCTION: size_mult ladder (0.25, 0.5, 0.75, 1.0),
  1.0 a HARD ceiling — losses only step down, wins restore at most one rung.
  No code path (including every LLM path) writes size_mult except the two
  ladder steps.
- losses also tighten min_confidence (+0.05 per loss, cap +0.15), impose
  cycle cooldowns (skipped cycles cost zero LLM), and block same-direction
  re-entry for 30 minutes;
- drawdown brake: peak-to-current ≥ 70% of max_loss_usd ⇒ retire; ≥ 35% ⇒
  force size_mult ≤ 0.5; open unrealized loss ≥ 50% of max_bet ⇒ one-rung
  tighten (long-horizon runs with zero closes);
- thesis drift (deterministic, fail-closed on stale marks): after ≥50% of
  horizon, drift < −0.5 counts as ONE synthetic loss — never retirement;
- the ONLY LLM is a thesis-review checkpoint (every 3 closes, ≥6h apart,
  ≤4/day/run, budget-counted via the 'thesis_review' run_event) whose
  verdict is MONOTONE-TIGHTENING: weakened ⇒ one rung; invalidated AND
  P&L ≤ 0 ⇒ retire (a profitable run with a "broken" thesis only tightens);
- retirement: 3 consecutive losing closes / brake / invalidated∧losing ⇒
  STATUS_STOPPING with protective reason 'adapt_retired' (excluded from
  auto-restart) + a fleet_symbol_cooldowns row (24h) in the SAME transaction.

State = trading_runs.adapt_state_json, validated on load (corrupt ⇒ reset to
the conservative 0.5 multiplier + journal). Saves carry the LEASE FENCE
(claimed_by + claim_expires_at) — a zombie claimant must not roll
last_processed_signal_id backwards and double-apply ladder steps.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from database import begin_write_transaction, get_db_connection

logger = logging.getLogger(__name__)

TS_FMT = "%Y-%m-%dT%H:%M:%SZ"

ADAPT_BOUNDS = {
    "ladder": (0.25, 0.5, 0.75, 1.0),
    "conf_bump_step": 0.05,
    "conf_bump_max": 0.15,
    "min_conf_ceiling": 0.95,
    "cooldown_cycles": {1: 1, 2: 2},
    "reentry_block_minutes": 30,
    "retire_consecutive_losses": 3,
    "retire_drawdown_frac": 0.70,
    "brake_drawdown_frac": 0.35,
    "unrealized_tighten_frac": 0.50,
    "thesis_off_track": -0.5,
    "thesis_review_every_closes": 3,
    "review_drawdown_frac": 0.35,
    "thesis_review_min_interval_s": 6 * 3600,
    "thesis_review_max_per_day": 4,
    "symbol_cooldown_hours": 24,
}

_DEFAULT_STATE = {
    "v": 1, "size_mult": 1.0, "conf_bump": 0.0, "cooldown_until": None,
    "consecutive_losses": 0, "consecutive_wins": 0,
    "closes": 0, "wins": 0, "gross_win_usd": 0.0, "gross_loss_usd": 0.0,
    "peak_total_pnl": 0.0, "last_processed_signal_id": 0,
    "last_close": None, "thesis_status": "intact",
    "thesis_reviews_today": 0, "thesis_reviews_day": None,
    "last_thesis_review_at": None, "off_track_flagged": False,
}


def _now_dt() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now_dt().strftime(TS_FMT)


def feedback_enabled(cfg: dict) -> bool:
    """Default ON for fleet-created runs (the builder sets feedback: true);
    existing manual runs are untouched by the deploy."""
    return bool(cfg.get("feedback"))


def load_state(run: dict) -> dict:
    """Validate-or-reset. A corrupt blob resets to CONSERVATIVE defaults
    (size_mult 0.5, not 1.0) and the reset is journaled by the caller."""
    raw = run.get("adapt_state_json")
    if not raw:
        return dict(_DEFAULT_STATE)
    try:
        state = json.loads(raw)
        assert isinstance(state, dict) and int(state.get("v") or 0) == 1
        assert float(state.get("size_mult") or 0) in ADAPT_BOUNDS["ladder"]
        out = dict(_DEFAULT_STATE)
        out.update(state)
        return out
    except Exception:  # noqa: BLE001
        out = dict(_DEFAULT_STATE)
        out["size_mult"] = 0.5
        out["_reset"] = True
        return out


def leg_outcomes(run: dict, after_signal_id: int) -> list[dict[str, Any]]:
    """Per-closing-leg realized contributions (net of fees) — the SAME
    average-cost math as run_engine.compute_run_pnl, tracked per leg.
    Catches SL/TP-watcher and flatten closes that happen outside cycles
    (they carry the run's id on their signals rows)."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """SELECT id, side, entry_price, quantity, fee_usd FROM signals
               WHERE run_id = ? AND message_type = 'operation' ORDER BY id""",
            (run["id"],))
        legs = [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()
    qty = avg = 0.0
    out: list[dict[str, Any]] = []
    for leg in legs:
        side, p = leg["side"], float(leg["entry_price"] or 0)
        q, fee = float(leg["quantity"] or 0), float(leg["fee_usd"] or 0)
        realized = None
        direction = None
        if side == "buy":
            avg = (avg * qty + p * q) / (qty + q) if qty + q > 0 else p
            qty += q
        elif side == "sell":
            realized = (p - avg) * min(q, qty) - fee
            direction = "long"
            qty -= min(q, qty)
        elif side == "short":
            held = -qty
            avg = (avg * held + p * q) / (held + q) if held + q > 0 else p
            qty -= q
        elif side == "cover":
            held = -qty
            realized = (avg - p) * min(q, held) - fee
            direction = "short"
            qty += min(q, held)
        if realized is not None and int(leg["id"]) > int(after_signal_id):
            out.append({"signal_id": int(leg["id"]), "realized": realized,
                        "direction": direction,
                        "win": realized > 0})
    return out


def ingest_outcomes(state: dict, outcomes: list[dict[str, Any]]) -> list[dict]:
    """Apply the ladder per closing leg, in signal-id order. Returns the
    adaptation events to journal. A scratch trade that only paid fees counts
    as a LOSS — at 0.1%/leg, churn IS the failure mode being disciplined."""
    ladder = ADAPT_BOUNDS["ladder"]
    events: list[dict] = []
    for o in outcomes:
        before_mult = state["size_mult"]
        idx = ladder.index(state["size_mult"]) if state["size_mult"] in ladder else 1
        if o["win"]:
            state["consecutive_wins"] += 1
            state["consecutive_losses"] = 0
            state["wins"] += 1
            state["gross_win_usd"] += o["realized"]
            idx = min(idx + 1, len(ladder) - 1)  # restore ≤ 1 rung, ceil 1.0
            state["conf_bump"] = max(0.0, state["conf_bump"]
                                     - ADAPT_BOUNDS["conf_bump_step"])
            trigger = "winning_close"
        else:
            state["consecutive_losses"] += 1
            state["consecutive_wins"] = 0
            state["gross_loss_usd"] += abs(o["realized"])
            idx = max(idx - 1, 0)                # step DOWN one rung, floor
            state["conf_bump"] = min(ADAPT_BOUNDS["conf_bump_max"],
                                     state["conf_bump"]
                                     + ADAPT_BOUNDS["conf_bump_step"])
            cool = ADAPT_BOUNDS["cooldown_cycles"].get(
                min(state["consecutive_losses"], 2), 2)
            state["cooldown_until"] = (
                _now_dt() + timedelta(minutes=cool * 60)).strftime(TS_FMT)
            trigger = "losing_close"
        state["size_mult"] = ladder[idx]
        state["closes"] += 1
        state["last_processed_signal_id"] = max(
            int(state["last_processed_signal_id"] or 0), o["signal_id"])
        state["last_close"] = {"ts": _now_iso(), "direction": o["direction"],
                               "win": o["win"]}
        events.append({"trigger": trigger, "signal_id": o["signal_id"],
                       "realized": round(o["realized"], 4),
                       "size_mult": [before_mult, state["size_mult"]],
                       "conf_bump": state["conf_bump"]})
    return events


def apply_policy(state: dict, run: dict, cfg: dict, pnl: dict) -> dict:
    """Per-cycle checks beyond leg ingestion. Returns {retire: bool,
    reason: str|None, events: [...]}. Pure decision logic — no I/O."""
    events: list[dict] = []
    retire = False
    reason = None
    ladder = ADAPT_BOUNDS["ladder"]

    total = float(pnl.get("total") or 0)
    state["peak_total_pnl"] = max(float(state.get("peak_total_pnl") or 0), total)
    stops = {}
    try:
        stops = json.loads(run.get("stop_conditions_json") or "{}")
    except (ValueError, TypeError):
        pass
    max_loss = float(stops.get("max_loss_usd") or 0)

    drawdown = state["peak_total_pnl"] - total
    if max_loss > 0 and drawdown >= ADAPT_BOUNDS["retire_drawdown_frac"] * max_loss:
        retire, reason = True, "drawdown_brake"
        events.append({"trigger": "drawdown_brake",
                       "drawdown": round(drawdown, 4), "max_loss": max_loss})
    elif max_loss > 0 and drawdown >= ADAPT_BOUNDS["brake_drawdown_frac"] * max_loss:
        if state["size_mult"] > 0.5:
            state["size_mult"] = 0.5
            events.append({"trigger": "drawdown_soft_brake",
                           "size_mult": [1.0, 0.5]})

    # intra-position tighten (long-horizon runs with zero closes)
    max_bet = float(cfg.get("max_bet_usd") or 0)
    unreal = float(pnl.get("unrealized") or 0)
    if max_bet > 0 and unreal <= -ADAPT_BOUNDS["unrealized_tighten_frac"] * max_bet:
        idx = ladder.index(state["size_mult"]) if state["size_mult"] in ladder else 1
        if idx > 0:
            before = state["size_mult"]
            state["size_mult"] = ladder[idx - 1]
            events.append({"trigger": "unrealized_tighten",
                           "size_mult": [before, state["size_mult"]],
                           "unrealized": round(unreal, 4)})

    # thesis drift — deterministic, fail-closed on stale marks
    thesis = cfg.get("thesis") if isinstance(cfg.get("thesis"), dict) else None
    if thesis and not state.get("off_track_flagged") and pnl.get("mark_age_ok", True):
        drift = _thesis_drift(thesis, run, pnl)
        if drift is not None and drift < ADAPT_BOUNDS["thesis_off_track"]:
            state["off_track_flagged"] = True
            state["consecutive_losses"] += 1  # ONE synthetic loss, never retire
            idx = ladder.index(state["size_mult"]) if state["size_mult"] in ladder else 1
            before = state["size_mult"]
            state["size_mult"] = ladder[max(idx - 1, 0)]
            events.append({"trigger": "off_track", "drift": round(drift, 3),
                           "size_mult": [before, state["size_mult"]]})

    if not retire and state["consecutive_losses"] >= \
            ADAPT_BOUNDS["retire_consecutive_losses"]:
        retire, reason = True, "consecutive_losses"
        events.append({"trigger": "retire_consecutive_losses",
                       "losses": state["consecutive_losses"]})

    return {"retire": retire, "reason": reason, "events": events}


def _thesis_drift(thesis: dict, run: dict, pnl: dict) -> Optional[float]:
    """signed actual move ÷ expected move, evaluated after ≥50% of horizon."""
    try:
        ref = float(thesis.get("entry_ref_price") or 0)
        expected = float(thesis.get("expected_move_pct") or 0)
        horizon_h = float(thesis.get("horizon_hours") or 0)
        started = run.get("started_at")
        if not ref or not expected or not horizon_h or not started:
            return None
        then = datetime.strptime(started, TS_FMT).replace(tzinfo=timezone.utc)
        elapsed_h = (_now_dt() - then).total_seconds() / 3600.0
        if elapsed_h < 0.5 * horizon_h:
            return None
        pos = pnl.get("position") or {}
        mark = pos.get("current_price")
        if mark is None:
            return None
        move_pct = (float(mark) / ref - 1.0) * 100.0
        if (thesis.get("direction") or "long") == "short":
            move_pct = -move_pct
        return move_pct / expected
    except Exception:  # noqa: BLE001
        return None


def blocked_reentry(state: dict, action: Optional[str]) -> bool:
    """Same-direction re-entry after a LOSING close, within the block window
    — the whipsaw/fee-churn guard."""
    last = state.get("last_close")
    if not last or last.get("win") or action not in ("buy", "short"):
        return False
    try:
        ts = datetime.strptime(last["ts"], TS_FMT).replace(tzinfo=timezone.utc)
    except (KeyError, ValueError, TypeError):
        return False
    if (_now_dt() - ts).total_seconds() > ADAPT_BOUNDS["reentry_block_minutes"] * 60:
        return False
    entry_dir = "long" if action == "buy" else "short"
    return last.get("direction") == entry_dir


def in_cooldown(state: dict) -> bool:
    until = state.get("cooldown_until")
    if not until:
        return False
    try:
        return datetime.strptime(until, TS_FMT).replace(tzinfo=timezone.utc) > _now_dt()
    except (ValueError, TypeError):
        return False


# ── thesis review (the only LLM in this module) ────────────────────────────

def maybe_review_thesis(state: dict, run: dict, cfg: dict, pnl: dict,
                        generate_text=None) -> Optional[dict]:
    """Budget-gated checkpoint. The verdict can only TIGHTEN. Emits the
    'thesis_review' run_event via the caller (which counts into
    llm_ticks_exhausted — the budget is consumed, not just checked)."""
    thesis = cfg.get("thesis") if isinstance(cfg.get("thesis"), dict) else None
    if not thesis:
        return None
    due_by_closes = state["closes"] > 0 and state["closes"] % \
        ADAPT_BOUNDS["thesis_review_every_closes"] == 0
    # Open-position trigger (Henry 2026-07-21): a run bleeding UNREALIZED
    # drawdown must not wait for a close to get its what-went-wrong pass —
    # review once the drawdown crosses the soft-brake line. The 6h interval
    # and daily cap below bound the extra LLM spend exactly like the
    # close-triggered path.
    due_by_drawdown = False
    if not due_by_closes:
        try:
            stops = json.loads(run.get("stop_conditions_json") or "{}")
            max_loss = float(stops.get("max_loss_usd") or 0)
            total = float(pnl.get("total") or 0)
            peak = max(float(state.get("peak_total_pnl") or 0), total)
            due_by_drawdown = max_loss > 0 and \
                (peak - total) >= ADAPT_BOUNDS["review_drawdown_frac"] * max_loss
        except (ValueError, TypeError):
            due_by_drawdown = False
    if not (due_by_closes or due_by_drawdown):
        return None
    today = _now_dt().strftime("%Y-%m-%d")
    if state.get("thesis_reviews_day") != today:
        state["thesis_reviews_day"] = today
        state["thesis_reviews_today"] = 0
    if state["thesis_reviews_today"] >= ADAPT_BOUNDS["thesis_review_max_per_day"]:
        return None
    last = state.get("last_thesis_review_at")
    if last:
        try:
            then = datetime.strptime(last, TS_FMT).replace(tzinfo=timezone.utc)
            if (_now_dt() - then).total_seconds() < \
                    ADAPT_BOUNDS["thesis_review_min_interval_s"]:
                return None
        except (ValueError, TypeError):
            pass
    # tick budget: pre-check (the emitted thesis_review event draws it down)
    try:
        from entitlements import llm_ticks_exhausted
        conn = get_db_connection()
        try:
            if llm_ticks_exhausted(conn.cursor(), run["agent_id"]):
                return None
        finally:
            conn.close()
    except Exception:  # noqa: BLE001
        return None

    if generate_text is None:
        from llm_client import generate_text as _gt
        generate_text = _gt
    # The verdict here can RETIRE a run, so it must not reason from a level the
    # tape has already walked past. The decision prompt scrubs those (PR #208);
    # this prompt was built separately and missed it — prod run 937 concluded
    # "intact" citing "the price never fell below the $18 invalidation
    # threshold" on an asset near 490, and run 898 concluded "weakened" citing
    # "likely breached the $1,800 invalidation level". Lazy import: run_engine
    # imports this module the same way, so neither is loaded by the other.
    try:
        from run_engine import _usable_thesis
        mark = (pnl.get("position") or {}).get("current_price")
        thesis = _usable_thesis(thesis, float(mark) if mark else None)
    except Exception:  # noqa: BLE001 - a scrub must never break the review
        pass
    prompt = (
        "Review this trading thesis against actual performance. Respond ONLY "
        'with JSON: {"thesis_status": "intact"|"weakened"|"invalidated", '
        '"rationale": "<one sentence>"}\n'
        f"Thesis: {json.dumps(thesis, default=str)[:800]}\n"
        f"Performance: closes={state['closes']}, wins={state['wins']}, "
        f"total_pnl={pnl.get('total')}, unrealized={pnl.get('unrealized')}"
    )
    text = None
    try:
        text = generate_text(prompt, max_tokens=150, temperature=0.2,
                             tier="decision")
    except Exception:  # noqa: BLE001
        text = None
    state["last_thesis_review_at"] = _now_iso()
    state["thesis_reviews_today"] += 1
    if not text:
        return None
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
    except (ValueError, TypeError):
        return None
    status = str(obj.get("thesis_status") or "").strip().lower()
    if status not in ("intact", "weakened", "invalidated"):
        return None
    # MONOTONE-TIGHTENING mapping: intact does nothing (never restores rungs)
    ladder = ADAPT_BOUNDS["ladder"]
    result = {"status": status, "rationale": str(obj.get("rationale") or "")[:500],
              "retire": False}
    if status == "weakened":
        idx = ladder.index(state["size_mult"]) if state["size_mult"] in ladder else 1
        state["size_mult"] = ladder[max(idx - 1, 0)]
    elif status == "invalidated" and float(pnl.get("total") or 0) <= 0:
        result["retire"] = True
    state["thesis_status"] = status
    return result


# ── persistence (lease-fenced) ─────────────────────────────────────────────

def save_state(run: dict, state: dict, events: list[dict],
               worker_identity: str) -> bool:
    """UPDATE adapt_state_json WITH THE FENCE — 0 rows means the lease was
    reclaimed: discard the adaptation and tell the caller to skip the trade
    (a zombie must not roll last_processed_signal_id backwards)."""
    state.pop("_reset", None)
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        begin_write_transaction(cursor)
        cursor.execute(
            """UPDATE trading_runs SET adapt_state_json = ?
               WHERE id = ? AND claimed_by = ? AND claim_expires_at >= ?""",
            (json.dumps(state), run["id"], worker_identity, _now_iso()))
        if cursor.rowcount != 1:
            conn.rollback()
            return False
        from trading_runs import _emit_event
        for ev in events:
            _emit_event(cursor, run["id"], "adapt", ev)
        conn.commit()
        return True
    except Exception:  # noqa: BLE001
        try:
            conn.rollback()
        except Exception:  # noqa: BLE001
            pass
        return False
    finally:
        conn.close()


def retire_run(run: dict, reason: str) -> None:
    """stopping + 'adapt_retired' (protective — excluded from auto-restart),
    honoring stop_flatten; the symbol cooldown row rides the SAME transaction
    as the final adapt event (the round-2 phantom-table fix)."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        begin_write_transaction(cursor)
        cursor.execute(
            """UPDATE trading_runs SET status = 'stopping',
               status_reason = 'adapt_retired'
               WHERE id = ? AND status IN ('running', 'paused')""",
            (run["id"],))
        if cursor.rowcount != 1:
            conn.rollback()
            return
        until = (_now_dt() + timedelta(
            hours=ADAPT_BOUNDS["symbol_cooldown_hours"])).strftime(TS_FMT)
        cursor.execute(
            """INSERT INTO fleet_symbol_cooldowns
               (agent_id, market, symbol, until_ts, source_run_id)
               VALUES (?, ?, ?, ?, ?)""",
            (run["agent_id"], run["market"], run["symbol"], until, run["id"]))
        from trading_runs import _emit_event
        _emit_event(cursor, run["id"], "run_status",
                    {"from": run["status"], "to": "stopping",
                     "reason": "adapt_retired", "detail": reason})
        _emit_event(cursor, run["id"], "adapt",
                    {"trigger": "retired", "reason": reason,
                     "symbol_cooldown_hours": ADAPT_BOUNDS["symbol_cooldown_hours"]})
        conn.commit()
    except Exception:  # noqa: BLE001
        try:
            conn.rollback()
        except Exception:  # noqa: BLE001
            pass
    finally:
        conn.close()


def _recent_decision_values(run_id: int, limit: int = 30) -> list[float]:
    """Gate-relevant values from the run's recent decision events —
    conviction when present (P2), else the legacy scalar. Fail-soft: [] on
    any error (the caller then applies no distribution cap)."""
    try:
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT payload FROM run_events
                   WHERE run_id = ? AND event_type = 'decision'
                   ORDER BY id DESC LIMIT ?""",
                (run_id, int(limit)))
            rows = cursor.fetchall()
        finally:
            conn.close()
        values: list[float] = []
        for row in rows:
            try:
                obj = json.loads(row["payload"] or "{}")
                v = obj.get("conviction")
                if v is None:
                    v = obj.get("confidence")
                if v is not None:
                    values.append(float(v))
            except (ValueError, TypeError):
                continue
        return values
    except Exception:  # noqa: BLE001
        return []


def effective_gate_params(state: dict, cfg: dict,
                          run_id: Optional[int] = None) -> dict:
    """The ONLY interface adaptation has to the money path: modulate the
    gate config — size shrink-only, confidence tighten-only.

    Plan 15 E1: the absolute +0.05/loss bump assumed the model uses the full
    confidence scale; with output pinned near 0.62 one loss pushed the gate
    to 0.65+ and the run went permanently silent (it would never emit above
    the gate again). The tightened gate is therefore capped at the run's own
    recent p90 emitted value − 0.01: the run must beat its own strongest
    recent read to trade — tightened, but never unreachable. Needs ≥8 recent
    decisions; below that (or with no run_id) behavior is unchanged."""
    base_conf = float(cfg.get("min_confidence") or 0)
    base_size = float(cfg.get("max_bet_usd") or 0)
    tightened = min(ADAPT_BOUNDS["min_conf_ceiling"],
                    base_conf + float(state.get("conf_bump") or 0))
    if run_id is not None and float(state.get("conf_bump") or 0) > 0:
        values = _recent_decision_values(run_id)
        if len(values) >= 8:
            ordered = sorted(values)
            p90 = ordered[min(len(ordered) - 1, int(0.9 * len(ordered)))]
            cap = round(p90 - 0.01, 4)
            if cap > base_conf:
                tightened = min(tightened, cap)
    return {
        "min_confidence": tightened,
        "size_usd": max(10.0, base_size * float(state.get("size_mult") or 1.0)),
        "size_mult": float(state.get("size_mult") or 1.0),
    }
