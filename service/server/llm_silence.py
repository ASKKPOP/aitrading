"""Operator alert when the desk goes mute — the local LLM stops answering.

Found by the 2026-11-07 daily sweep. The desk's decisions are journaled as
`decision` run_events; when the LLM does not answer inside its timeout the
cycle falls back to a scaffold / rule hold (`decided_by: "scaffold"`, or
`decided_by: "rule"` with `fallback_reason: "no llm response"`). Fail-closed is
correct — no order is ever authored on silence — but NOTHING told the operator.
Two outages of the local host in nine days went unannounced:

    2026-10-30T12Z → 2026-11-02T~10Z   ~70 h   (llm_usage 300+/h → 2-10/h)
    2026-11-05T21Z → still mute at 11-07T15Z  42 h+ (255 of 255 agent-6
                                               decisions hold, 251 with no verdict)

The desk cannot be the actor here — a mute desk cannot perceive its own
silence — so this is operator plumbing, not a skill. It reads the last
``LLM_SILENCE_WINDOW_MIN`` minutes of decisions and, when at least
``LLM_SILENCE_MIN_N`` were made and ``LLM_SILENCE_MUTE_FRAC`` of them carried no
verdict, sends ONE admin alert (admin_alerts.notify_admins: the console's
email/phone), repeats it every ``LLM_SILENCE_REALERT_H`` hours while the
silence lasts, and sends one recovery notice when verdicts return. Pure
measurement: reads run_events, never writes the ledger, never touches a run.
``LLM_SILENCE_ALERT=0`` turns it off.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

TS_FMT = "%Y-%m-%dT%H:%M:%SZ"

# Mirrors run_engine._INFRA_RULE_REASONS — the rule-fallback reasons that mean
# "the LLM did not answer", as opposed to a rule the desk chose to apply.
# Pinned by tests/test_llm_silence.py so the two cannot drift apart.
INFRA_RULE_REASONS = ("no llm response", "decision json unparseable")

EVENT_SILENT = "silent"
EVENT_RECOVERED = "recovered"


def enabled() -> bool:
    return os.getenv("LLM_SILENCE_ALERT", "1").strip().lower() in (
        "1", "true", "yes", "on")


def _env_float(name: str, default: float, lo: float, hi: float) -> float:
    try:
        return min(hi, max(lo, float(os.getenv(name, str(default)) or default)))
    except ValueError:
        return default


def window_minutes() -> int:
    return int(_env_float("LLM_SILENCE_WINDOW_MIN", 120, 15, 1440))


def min_n() -> int:
    return int(_env_float("LLM_SILENCE_MIN_N", 10, 1, 10_000))


def mute_frac() -> float:
    return _env_float("LLM_SILENCE_MUTE_FRAC", 0.8, 0.05, 1.0)


def recover_frac() -> float:
    """Below this mute share (same window) the silence is over. Kept well
    under the alert threshold so the alert cannot flap on one hour's noise."""
    return _env_float("LLM_SILENCE_RECOVER_FRAC", 0.5, 0.0, 1.0)


def realert_hours() -> float:
    return _env_float("LLM_SILENCE_REALERT_H", 6.0, 0.25, 168.0)


def is_mute_decision(payload: Any) -> bool:
    """True when a `decision` payload records a cycle the LLM never answered."""
    if not isinstance(payload, dict):
        return False
    decided_by = str(payload.get("decided_by") or "")
    if decided_by == "scaffold":
        return True
    if decided_by == "rule":
        return str(payload.get("fallback_reason") or "") in INFRA_RULE_REASONS
    return False


def _parse_ts(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.strptime(str(value)[:19], "%Y-%m-%dT%H:%M:%S").replace(
            tzinfo=timezone.utc)
    except ValueError:
        return None


def measure(now: Optional[datetime] = None, minutes: Optional[int] = None) -> dict:
    """Count decisions in the trailing window and how many had no verdict.

    run_events.ts is an ISO `YYYY-MM-DDTHH:MM:SSZ` string, so the window bound
    MUST be rendered in that exact form (a space-separated literal silently
    matches the whole day — HANDOFF-automation-monitoring.md §4).
    """
    from database import get_db_connection

    now = now or datetime.now(timezone.utc)
    minutes = int(minutes or window_minutes())
    since = (now - timedelta(minutes=minutes)).strftime(TS_FMT)
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT payload FROM run_events WHERE event_type = 'decision' "
            "AND ts >= ? AND ts <= ?", (since, now.strftime(TS_FMT)))
        rows = cursor.fetchall()
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass
    n = 0
    mute = 0
    for row in rows:
        raw = row["payload"] if isinstance(row, dict) or hasattr(row, "keys") else row[0]
        try:
            payload = json.loads(raw) if isinstance(raw, (str, bytes)) else raw
        except (TypeError, ValueError):
            payload = None
        n += 1
        if is_mute_decision(payload):
            mute += 1
    return {"n": n, "mute": mute, "frac": (mute / n) if n else 0.0,
            "since": since, "window_min": minutes}


def evaluate(sample: dict, state: Optional[dict], now: datetime) -> tuple[Optional[str], dict]:
    """Pure decision: (event, new_state).

    state = {"silent": bool, "alerted_at": iso|None}. Emits ``silent`` when the
    window is both big enough and mute enough and no alert went out in the
    last realert window; ``recovered`` once, when a previously-alerted silence
    ends; None otherwise. A window too small to judge changes nothing.
    """
    state = dict(state or {"silent": False, "alerted_at": None})
    n = int(sample.get("n") or 0)
    frac = float(sample.get("frac") or 0.0)
    if n < min_n():
        return None, state
    if frac >= mute_frac():
        last = _parse_ts(state.get("alerted_at"))
        due = last is None or (now - last) >= timedelta(hours=realert_hours())
        state["silent"] = True
        if due:
            state["alerted_at"] = now.strftime(TS_FMT)
            return EVENT_SILENT, state
        return None, state
    if state.get("silent") and frac < recover_frac():
        had_alert = bool(state.get("alerted_at"))
        state["silent"] = False
        state["alerted_at"] = None
        # A recovery nobody's SILENT preceded (every delivery failed) is noise.
        return (EVENT_RECOVERED if had_alert else None), state
    return None, state


def _format(event: str, sample: dict) -> tuple[str, str]:
    pct = round(100.0 * float(sample.get("frac") or 0.0))
    n = int(sample.get("n") or 0)
    mute = int(sample.get("mute") or 0)
    window = int(sample.get("window_min") or window_minutes())
    if event == EVENT_SILENT:
        return (f"Desk LLM silent — {pct}% of decisions had no verdict",
                f"{mute} of {n} desk decisions in the last {window} min ended as "
                f"scaffold/rule holds because the LLM did not answer "
                f"(since {sample.get('since')}). No orders are being authored. "
                f"Check the local LLM host / LOCAL_LLM_BASE_URL.")
    return (f"Desk LLM recovered — {pct}% no-verdict",
            f"{mute} of {n} desk decisions in the last {window} min had no "
            f"verdict; the desk is deciding again.")


STATE_KEY = "llm_silence_state"

_EMPTY_STATE: dict = {"silent": False, "alerted_at": None}


def load_state() -> dict:
    """Persisted state (platform_settings) so a worker restart mid-outage
    neither re-alerts on boot nor loses the recovery notice (adversarial
    review 2026-11-07 #1). Fail-soft: unreadable → fresh state."""
    try:
        from platform_settings import get_setting
        raw = get_setting(STATE_KEY)
        if raw:
            d = json.loads(raw)
            if isinstance(d, dict):
                return {"silent": bool(d.get("silent")),
                        "alerted_at": d.get("alerted_at") or None}
    except Exception as exc:  # noqa: BLE001
        logger.warning("llm_silence: state read failed: %s", exc)
    return dict(_EMPTY_STATE)


def save_state(state: dict) -> bool:
    try:
        from platform_settings import set_setting
        set_setting(STATE_KEY, json.dumps(
            {"silent": bool(state.get("silent")), "alerted_at": state.get("alerted_at")}),
            updated_by="llm_silence")
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("llm_silence: state write failed: %s", exc)
        return False


def tick(now: Optional[datetime] = None,
         notify: Optional[Callable[[str, str], Any]] = None,
         state: Optional[dict] = None) -> dict:
    """One pass: measure → evaluate → alert → persist. Fail-soft: never raises.

    ``state`` None means the persisted state (load_state / save_state); tests
    pass their own dict. A SILENT alert that reached no channel does not stamp
    ``alerted_at`` (adversarial review 2026-11-07 #2), so the next tick retries
    instead of going quiet for the re-alert window. While silent, a window too
    small to judge (every run retired) freezes the state by design.
    """
    now = now or datetime.now(timezone.utc)
    persist = state is None
    st = load_state() if persist else state
    try:
        sample = measure(now)
    except Exception as exc:  # noqa: BLE001 — a measurement failure is not an outage
        logger.warning("llm_silence: measure failed: %s", exc)
        return {"event": None, "error": str(exc)[:200]}
    before = dict(st)
    event, new_state = evaluate(sample, st, now)
    result = {"event": event, **sample}
    if event:
        subject, body = _format(event, sample)
        try:
            send = notify
            if send is None:
                from admin_alerts import notify_admins
                send = notify_admins
            result["sent"] = send(subject, body)
        except Exception as exc:  # noqa: BLE001
            logger.warning("llm_silence: notify failed: %s", exc)
            result["sent"] = {"channels": [], "error": str(exc)[:200]}
        if event == EVENT_SILENT and not (result.get("sent") or {}).get("channels"):
            new_state["alerted_at"] = None   # nobody reached: retry next tick
    st.clear()
    st.update(new_state)
    if persist and new_state != before:
        result["persisted"] = save_state(new_state)
    return result
