"""Per-rule trading schedules (Plan 06 C3).

A rule may carry a schedule window as JSON:

    {"days": [0..6], "start_hour": 0..23, "end_hour": 0..24, "tz": "Asia/Seoul"}

    days       ISO weekday numbers the rule may run on (Mon=0 .. Sun=6).
               Empty/absent -> all days.
    start_hour local-time hour the window opens (inclusive).
    end_hour   local-time hour the window closes (exclusive). end<=start means
               an overnight window that wraps past midnight (e.g. 22->6).
    tz         IANA timezone name; falls back to UTC when unknown.

The automation tick treats an out-of-window rule as NOT due. A rule with no
schedule always passes (unchanged behavior). Fail-soft: any parse/timezone
problem means the rule runs (a broken schedule must never silently freeze
trading — it degrades to always-on, which the user can see in the run log).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

logger = logging.getLogger(__name__)


def parse_schedule(raw: Optional[str]) -> Optional[dict[str, Any]]:
    """Validate/normalize a schedule JSON string. Returns None for empty
    (= no schedule). Raises ValueError on malformed input (for the API)."""
    if raw is None:
        return None
    if isinstance(raw, dict):
        obj = raw
    else:
        raw = raw.strip()
        if not raw:
            return None
        try:
            obj = json.loads(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"schedule must be valid JSON: {exc}")
    if not isinstance(obj, dict):
        raise ValueError("schedule must be a JSON object")

    days = obj.get("days")
    if days is not None:
        if not isinstance(days, list) or any(
                not isinstance(d, int) or d < 0 or d > 6 for d in days):
            raise ValueError("schedule.days must be a list of weekday ints 0..6")
        days = sorted(set(days))

    def _hour(key: str, default: int, hi: int) -> int:
        v = obj.get(key, default)
        try:
            v = int(v)
        except (TypeError, ValueError):
            raise ValueError(f"schedule.{key} must be an integer")
        if v < 0 or v > hi:
            raise ValueError(f"schedule.{key} must be 0..{hi}")
        return v

    start_hour = _hour("start_hour", 0, 23)
    end_hour = _hour("end_hour", 24, 24)
    tz = str(obj.get("tz") or "UTC").strip() or "UTC"
    # validate tz early so the API rejects bad zones
    try:
        ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        raise ValueError(f"schedule.tz is not a valid timezone: {tz}")

    return {"days": days or [], "start_hour": start_hour,
            "end_hour": end_hour, "tz": tz}


def in_window(schedule: Optional[dict[str, Any]], now_utc: Optional[datetime] = None) -> bool:
    """True if `now` falls inside the schedule window. No schedule -> always True.
    Fail-soft: a malformed schedule returns True (degrade to always-on)."""
    if not schedule:
        return True
    try:
        now_utc = now_utc or datetime.now(timezone.utc)
        try:
            local = now_utc.astimezone(ZoneInfo(schedule.get("tz") or "UTC"))
        except Exception:  # noqa: BLE001
            local = now_utc
        days = schedule.get("days") or []
        if days and local.weekday() not in days:
            return False
        start = int(schedule.get("start_hour", 0))
        end = int(schedule.get("end_hour", 24))
        hour = local.hour
        if start == end:
            return True  # degenerate full-day window
        if start < end:
            return start <= hour < end
        # overnight wrap (e.g. 22 -> 6): in-window if after start OR before end
        return hour >= start or hour < end
    except Exception as exc:  # noqa: BLE001
        logger.debug("schedule in_window failed, defaulting to open: %s", exc)
        return True


def schedule_from_config(cfg: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Parse a config row's stored schedule_json, fail-soft to None."""
    try:
        return parse_schedule(cfg.get("schedule_json"))
    except ValueError:
        return None
