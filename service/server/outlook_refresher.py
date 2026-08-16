"""Plan 26 Phase 2 — outlook freshness sweeper (cold path).

The hot path already satisfies the 30-minute freshness floor for open
markets: every fleet run thinks on a ≤30-minute clock and emits its
``outlook`` event inside run_cycle. This sweeper covers only the slots the
cycle does not reach — closed sessions, non-running runs, and
waiting/dormant slots — by emitting a STANDING outlook ("plan for the next
open"). Owner directive (two-author discussion): a deterministic
``algo_candidate`` proposes levels, the desk model DISCUSSES them — adopt,
adjust, or override, with reasons — and the payload records both under
``basis`` so profit can later judge which author picks better targets. The
LLM call copies the ``llm_client.generate_text`` pattern hot_issue_daemon
uses (the provider is resolved inside generate_text — never hand-build an
LlmContext naming user_id/agent_id without a provider, the silent-desk
trap). On ANY LLM trouble — unconfigured, raised, unparseable — the algo
candidate BECOMES the plan (verdict ``algo_fallback``), so the sweeper
still emits on schedule when the LLM is down.

Two writers, one store: an open-market cycling run is never touched here
(the cycle owns it — no double-writing). The standing plan reaches trading
only as prompt context for the desk's own next decision; this module never
writes stop_conditions, orders, or positions — run_events rows only, via
the fail-soft telemetry emitter.

Registry key 'outlook_refresher', role 'settlement'; the loop is gated by
OUTLOOK_ENABLED (default off) and every per-slot failure logs and
continues.
"""

from __future__ import annotations

import json
import logging
import math
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from database import get_db_connection

logger = logging.getLogger(__name__)

TS_FMT = "%Y-%m-%dT%H:%M:%SZ"

# The whole cadence rule (shape copied from liquidation.py's two-tier
# interval): freshness floors in minutes, per market. Everything not named
# here — today futures and prediction — takes the default.
OUTLOOK_CADENCE_MIN = {"us-stock": 30, "crypto": 30, "forex": 30}
OUTLOOK_CADENCE_DEFAULT_MIN = 60

# Slot states whose bound run the cycle will not refresh.
_IDLE_SLOT_STATES = ("waiting", "dormant")


def outlook_enabled() -> bool:
    return os.environ.get("OUTLOOK_ENABLED", "false").strip().lower() in (
        "1", "true", "yes", "on")


def cadence_floor_min(market: Optional[str]) -> int:
    return OUTLOOK_CADENCE_MIN.get(market or "", OUTLOOK_CADENCE_DEFAULT_MIN)


def _num(value: Any) -> Optional[float]:
    """Finite float or None — NaN/inf in a persisted JSON column permanently
    500s reads, so every numeric is scrubbed before the payload is built."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


# ── DB reads ───────────────────────────────────────────────────────────────

def _active_fleets() -> list[dict]:
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM fleets WHERE status = 'active' "
                       "ORDER BY id")
        return [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()


def _slots(fleet_id: int) -> list[dict]:
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM fleet_slots WHERE fleet_id = ? "
                       "ORDER BY slot_index", (fleet_id,))
        return [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()


def _run_row(run_id: int) -> Optional[dict]:
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM trading_runs WHERE id = ?", (run_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _newest_outlook_age_min(run_id: int, now: datetime) -> Optional[float]:
    """Minutes since the run's newest outlook event; None if it has none.

    Ordered by ``ts`` — NEVER created_at (run_events has no such column and
    filtering on it errors silently on prod MySQL)."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT ts FROM run_events WHERE run_id = ? AND "
                       "event_type = 'outlook' ORDER BY ts DESC LIMIT 1",
                       (run_id,))
        row = cursor.fetchone()
    finally:
        conn.close()
    if not row or not row["ts"]:
        return None
    try:
        ts = datetime.strptime(str(row["ts"]), TS_FMT).replace(
            tzinfo=timezone.utc)
    except ValueError:
        return None  # unparseable ⇒ treat as never refreshed
    return max(0.0, (now - ts).total_seconds() / 60.0)


# ── due logic ──────────────────────────────────────────────────────────────

def _cold_reason(run: dict, slot_state: str, now: datetime) -> Optional[str]:
    """Why the cycle will NOT refresh this slot before the floor expires.

    None ⇒ the run is cycling on an open market — the cycle owns it and the
    sweeper must not double-write."""
    import markets
    if not markets.is_market_open(run.get("market"), now):
        return "market_closed"
    if (run.get("status") or "") != "running":
        return "run_idle"
    if slot_state in _IDLE_SLOT_STATES:
        return "slot_idle"
    return None


# ── standing outlook (algo candidate ⇄ LLM discussion) ─────────────────────

# Flat-fee breakeven hurdle, percent — a target closer than this cannot pay
# its own round trip (measured, not assumed: dead-capital/fee-hurdle work).
FEE_HURDLE_PCT = 2.4

_VERDICTS = ("adopted", "adjusted", "overridden")


def algo_candidate(direction: Any, ref_price: Any, expected_move_pct: Any,
                   horizon_hours: Any, stop_ref_px: Any,
                   now: Optional[datetime]) -> dict[str, Any]:
    """Pure deterministic candidate plan (other modules import this — keep
    it dependency-free). Fee-hurdle-floored target, pullback entry band,
    horizon time exit. Any missing/non-finite input → the dependent fields
    are None."""
    side = str(direction or "").strip().lower()
    ref = _num(ref_price)
    move = _num(expected_move_pct)
    horizon = _num(horizon_hours)
    out: dict[str, Any] = {"entry_low": None, "entry_high": None,
                           "target_px": None, "stop_ref_px": _num(stop_ref_px),
                           "time_exit": None}
    if ref is not None and ref > 0 and side in ("long", "short"):
        target_pct = max(move or 0.0, FEE_HURDLE_PCT)
        if side == "long":
            out["target_px"] = round(ref * (1.0 + target_pct / 100.0), 8)
            out["entry_low"] = round(ref * (1.0 - 0.25 * target_pct / 100.0), 8)
            out["entry_high"] = round(ref, 8)
        else:
            out["target_px"] = round(ref * (1.0 - target_pct / 100.0), 8)
            out["entry_low"] = round(ref, 8)
            out["entry_high"] = round(ref * (1.0 + 0.25 * target_pct / 100.0), 8)
    if horizon is not None and horizon > 0 and now is not None:
        out["time_exit"] = (now + timedelta(hours=horizon)).strftime(TS_FMT)
    return out


def _thesis_facts(run: dict) -> dict[str, Any]:
    """The run's frozen thesis block + live stop reference, every numeric
    scrubbed. Both the LLM prompt and the fallback build from this."""
    try:
        cfg = json.loads(run.get("config_snapshot_json") or "{}")
    except ValueError:
        cfg = {}
    thesis = cfg.get("thesis") if isinstance(cfg, dict) else None
    thesis = thesis if isinstance(thesis, dict) else {}
    try:
        stops = json.loads(run.get("stop_conditions_json") or "{}")
    except ValueError:
        stops = {}
    direction = str(thesis.get("direction") or "").strip().lower()
    price_cross = stops.get("price_cross") if isinstance(stops, dict) else None
    return {
        "symbol": str(run.get("symbol") or ""),
        "market": str(run.get("market") or ""),
        "bias": direction if direction in ("long", "short") else "flat",
        "entry_ref_price": _num(thesis.get("entry_ref_price")),
        "expected_move_pct": _num(thesis.get("expected_move_pct")),
        "invalidation": str(thesis.get("invalidation") or "").strip()[:300],
        "horizon_hours": _num(thesis.get("horizon_hours")),
        "stop_ref_px": _num(price_cross.get("price"))
        if isinstance(price_cross, dict) else None,
    }


def _fallback_payload(facts: dict[str, Any], algo: dict[str, Any],
                      reason: str) -> dict[str, Any]:
    """LLM unavailable: the algo candidate BECOMES the plan, verdict
    'algo_fallback'. Same shape the cycle emits (Plan 26 §3.1), source
    'sweeper', cycle null."""
    bias = facts["bias"]
    has_zone = algo["entry_low"] is not None and algo["entry_high"] is not None
    entry: dict[str, Any] = {
        "kind": "zone" if has_zone else "none",
        "low": algo["entry_low"], "high": algo["entry_high"], "trigger": None}
    prefix = ("Market closed — standing plan for next open"
              if reason == "market_closed" else "Slot idle — standing plan")
    narrative = (f"{prefix}: {bias} bias on {facts['symbol']}; "
                 f"{facts['invalidation'] or 'no invalidation on file'}."
                 )[:1000]
    return {
        "cycle": None,
        "symbol": facts["symbol"],
        "market": facts["market"],
        "source": "sweeper",
        "bias": bias,
        "entry": entry,
        "exit": {"target_px": algo["target_px"],
                 "stop_ref_px": facts["stop_ref_px"],
                 "time_exit": algo["time_exit"]},
        "invalidation": facts["invalidation"],
        "horizon_hours": facts["horizon_hours"],
        "narrative": narrative,
        "basis": {"algo": dict(algo), "verdict": "algo_fallback",
                  "discussion": None},
    }


def _llm_payload(facts: dict[str, Any], algo: dict[str, Any], reason: str,
                 base: dict[str, Any]) -> Optional[dict[str, Any]]:
    """The discussion: the desk model receives the algo candidate verbatim
    and adopts, adjusts, or overrides each level with reasons. Call pattern
    copied from hot_issue_daemon._recipient_verdict — generate_text resolves
    its own provider and returns None on any failure. Every model field is
    validated/clamped against the contract; anything invalid keeps the
    fallback value. None ⇒ caller emits the algo fallback wholesale."""
    from llm_client import generate_text
    session_state = ("market closed" if reason == "market_closed"
                     else "run dormant")
    prompt = (
        "You are the trading desk writing the STANDING plan for one "
        f"automated run while it cannot cycle ({session_state}). "
        f"Symbol: {facts['symbol']} ({facts['market']}). Thesis: "
        f"direction={facts['bias']}, "
        f"entry_ref_price={facts['entry_ref_price']}, "
        f"expected_move_pct={facts['expected_move_pct']}, "
        f"invalidation={facts['invalidation'] or 'none'}, "
        f"horizon_hours={facts['horizon_hours']}. "
        f"Stop reference price (fixed, never widen): "
        f"{facts['stop_ref_px']}.\n"
        "An algorithmic candidate plan is provided. Discuss it: adopt, "
        "adjust, or override each level, and justify the final targets. "
        f"Candidate: {json.dumps(algo)}\n"
        "State when this run will buy (entry zone or trigger) and when it "
        "will sell (target, stop reference, time exit) for the next "
        "session. Never ask for more information.\n"
        "Respond with ONLY the JSON object, no prose before or after: "
        '{"bias": "long"|"short"|"flat", '
        '"entry": {"kind": "zone"|"trigger"|"none", "low": <px or null>, '
        '"high": <px or null>, "trigger": "<text or null>"}, '
        '"exit": {"target_px": <px or null>, "stop_ref_px": <px or null>, '
        '"time_exit": "<ISO-8601 or null>"}, '
        '"invalidation": "<one sentence>", '
        '"horizon_hours": <number or null>, '
        '"verdict": "adopted"|"adjusted"|"overridden", '
        '"discussion": "<why these targets beat or match the candidate, '
        'max 300 chars>", '
        '"narrative": "<two sentences, desk voice, max 600 chars>"}')
    text = generate_text(prompt, max_tokens=500, temperature=0.3,
                         tier="decision")
    if not text:
        return None
    try:
        data = json.loads(text[text.index("{"):text.rindex("}") + 1])
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None

    out = dict(base)
    bias = str(data.get("bias") or "").strip().lower()
    if bias in ("long", "short", "flat"):
        out["bias"] = bias
    entry = data.get("entry")
    if isinstance(entry, dict):
        kind = str(entry.get("kind") or "").strip().lower()
        trigger = entry.get("trigger")
        trigger = str(trigger).strip()[:200] if trigger else None
        out["entry"] = {
            "kind": kind if kind in ("zone", "trigger", "none")
            else base["entry"]["kind"],
            "low": _num(entry.get("low")),
            "high": _num(entry.get("high")),
            "trigger": trigger or None,
        }
    exit_ = data.get("exit")
    if isinstance(exit_, dict):
        time_exit = exit_.get("time_exit")
        time_exit = str(time_exit).strip()[:40] if time_exit else None
        out["exit"] = {
            "target_px": _num(exit_.get("target_px")),
            # Display echo of the LIVE stop — the model never moves it
            # (write-once stop rule; a hallucinated wider stop must not
            # even be displayed).
            "stop_ref_px": base["exit"]["stop_ref_px"],
            "time_exit": time_exit or None,
        }
    invalidation = str(data.get("invalidation") or "").strip()[:300]
    if invalidation:
        out["invalidation"] = invalidation
    horizon = _num(data.get("horizon_hours"))
    if horizon is not None:
        out["horizon_hours"] = horizon
    narrative = str(data.get("narrative") or "").strip()[:600]
    if narrative:
        out["narrative"] = narrative
    # The discussion record — both authors, the verdict, the reasons.
    verdict = str(data.get("verdict") or "").strip().lower()
    if verdict not in _VERDICTS:
        verdict = "adjusted"
    discussion = str(data.get("discussion") or "").strip()[:300] or None
    out["basis"] = {"algo": dict(algo), "verdict": verdict,
                    "discussion": discussion}
    return out


def _standing_payload(run: dict, reason: str,
                      now: Optional[datetime] = None) -> dict[str, Any]:
    """Algo candidate ⇄ LLM discussion; on any LLM trouble the candidate
    becomes the plan — the sweeper must still emit on schedule when the LLM
    is down."""
    now = now or datetime.now(timezone.utc)
    facts = _thesis_facts(run)
    algo = algo_candidate(facts["bias"], facts["entry_ref_price"],
                          facts["expected_move_pct"], facts["horizon_hours"],
                          facts["stop_ref_px"], now)
    base = _fallback_payload(facts, algo, reason)
    try:
        authored = _llm_payload(facts, algo, reason, base)
    except Exception:  # noqa: BLE001 — any LLM trouble falls back
        logger.debug("outlook_refresher: LLM standing outlook failed "
                     "(run %s)", run.get("id"), exc_info=True)
        authored = None
    return authored or base


# ── sweep ──────────────────────────────────────────────────────────────────

def _sweep_slot(slot: dict, run_id: int, now: datetime) -> bool:
    run = _run_row(run_id)
    if not run:
        return False
    age = _newest_outlook_age_min(run_id, now)
    if age is not None and age <= cadence_floor_min(run.get("market")):
        return False  # still fresh
    reason = _cold_reason(run, str(slot.get("state") or ""), now)
    if reason is None:
        return False  # open market, cycling run: the cycle owns it
    import trading_runs
    payload = _standing_payload(run, reason, now)
    return trading_runs.emit_telemetry_event(run_id, "outlook",
                                             payload) is not None


def outlook_refresher_tick(now: Optional[datetime] = None) -> dict[str, Any]:
    """One sweep over every active fleet's bound slots. Fail-soft per slot:
    one bad slot logs and never stops the rest of the sweep."""
    if not outlook_enabled():
        return {"enabled": False, "checked": 0, "emitted": 0}
    now = now or datetime.now(timezone.utc)
    checked = emitted = 0
    for fleet in _active_fleets():
        for slot in _slots(fleet["id"]):
            run_id = slot.get("current_run_id")
            if not run_id:
                continue
            checked += 1
            try:
                if _sweep_slot(slot, int(run_id), now):
                    emitted += 1
            except Exception:  # noqa: BLE001 — sweep must outlive any slot
                logger.warning("outlook_refresher: slot %s/%s failed",
                               slot.get("fleet_id"), slot.get("slot_index"),
                               exc_info=True)
    return {"enabled": True, "checked": checked, "emitted": emitted}
