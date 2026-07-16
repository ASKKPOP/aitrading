"""
market_events.py — Macro event calendar (signal-collection plan, card 07).

Scheduled macro releases (FOMC rate decisions, CPI, jobs report) are the
one signal source that needs no external API at all: the schedules are
published months ahead by the Fed and BLS. This module keeps them as
static data and answers two questions:

  1. What's coming?          -> upcoming_events() / build_events_payload()
  2. Are we inside a window? -> active_event_window()

Event-study evidence (KSE 2020-2025, 42 FOMC + 62 CPI events): abnormal
*volatility* spikes on release day (FOMC +1.03pp, CPI +0.81pp, p<0.001)
but cumulative abnormal *returns* are not significant — these are
amplitude events, not direction events. The actionable use is therefore
an entry-window filter (avoid opening positions right around the release),
which automation applies when EVENT_GUARD_ENABLED=true.

Dates verified 2026-07-15 against federalreserve.gov (FOMC, incl. 2027)
and the BLS release schedule (CPI; jobs report follows the BLS
first-Friday convention — Jul 2 and Aug 7 2026 confirmed individually).
Each FOMC date is "tentative until confirmed at the meeting immediately
preceding it"; refresh this table when the Fed/BLS revise schedules.

No env gate: static data, zero external calls, read-only.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")

# (event_type, local ET date "YYYY-MM-DD", local ET time "HH:MM", title)
# FOMC: decision statement 14:00 ET on day 2 of the meeting.
# CPI / jobs report: 08:30 ET.
_CALENDAR: list[tuple[str, str, str, str]] = [
    # ── FOMC rate decisions (federalreserve.gov, 2026 + 2027) ─────────────
    ("fomc", "2026-01-28", "14:00", "FOMC rate decision"),
    ("fomc", "2026-03-18", "14:00", "FOMC rate decision"),
    ("fomc", "2026-04-29", "14:00", "FOMC rate decision"),
    ("fomc", "2026-06-17", "14:00", "FOMC rate decision"),
    ("fomc", "2026-07-29", "14:00", "FOMC rate decision"),
    ("fomc", "2026-09-16", "14:00", "FOMC rate decision"),
    ("fomc", "2026-10-28", "14:00", "FOMC rate decision"),
    ("fomc", "2026-12-09", "14:00", "FOMC rate decision"),
    ("fomc", "2027-01-27", "14:00", "FOMC rate decision"),
    ("fomc", "2027-03-17", "14:00", "FOMC rate decision"),
    ("fomc", "2027-04-28", "14:00", "FOMC rate decision"),
    ("fomc", "2027-06-09", "14:00", "FOMC rate decision"),
    ("fomc", "2027-07-28", "14:00", "FOMC rate decision"),
    ("fomc", "2027-09-15", "14:00", "FOMC rate decision"),
    ("fomc", "2027-10-27", "14:00", "FOMC rate decision"),
    ("fomc", "2027-12-08", "14:00", "FOMC rate decision"),
    # ── CPI releases (BLS schedule, 2026) ─────────────────────────────────
    ("cpi", "2026-01-13", "08:30", "CPI (Dec 2025)"),
    ("cpi", "2026-02-13", "08:30", "CPI (Jan 2026)"),
    ("cpi", "2026-03-11", "08:30", "CPI (Feb 2026)"),
    ("cpi", "2026-04-10", "08:30", "CPI (Mar 2026)"),
    ("cpi", "2026-05-12", "08:30", "CPI (Apr 2026)"),
    ("cpi", "2026-06-10", "08:30", "CPI (May 2026)"),
    ("cpi", "2026-07-14", "08:30", "CPI (Jun 2026)"),
    ("cpi", "2026-08-12", "08:30", "CPI (Jul 2026)"),
    ("cpi", "2026-09-11", "08:30", "CPI (Aug 2026)"),
    ("cpi", "2026-10-14", "08:30", "CPI (Sep 2026)"),
    ("cpi", "2026-11-10", "08:30", "CPI (Oct 2026)"),
    ("cpi", "2026-12-10", "08:30", "CPI (Nov 2026)"),
    # ── Jobs report / nonfarm payrolls (BLS Employment Situation, 2026) ──
    # Jul 2 + Aug 7 individually confirmed; later months follow the BLS
    # first-Friday convention and should be re-checked as BLS publishes.
    ("nfp", "2026-07-02", "08:30", "Jobs report (Jun 2026)"),
    ("nfp", "2026-08-07", "08:30", "Jobs report (Jul 2026)"),
    ("nfp", "2026-09-04", "08:30", "Jobs report (Aug 2026)"),
    ("nfp", "2026-10-02", "08:30", "Jobs report (Sep 2026)"),
    ("nfp", "2026-11-06", "08:30", "Jobs report (Oct 2026)"),
    ("nfp", "2026-12-04", "08:30", "Jobs report (Nov 2026)"),
    # ── US election days (statutory Tuesday after first Monday of November;
    #    18:00 ET approximates earliest polls close, not a release time) ─────
    ("election", "2026-11-03", "18:00", "US midterm election day"),
]

# Historical 2019–2025 calendar (source-verified) lives in
# market_events_history.py — used by the strategy backtester, not the live feed.

# Entry-block window around a release: default 60 min before -> 60 min after.
# Slippage/whipsaw risk concentrates here (see module docstring).
_WINDOW_BEFORE_MIN = int(os.getenv("EVENT_WINDOW_BEFORE_MINUTES", "60") or 60)
_WINDOW_AFTER_MIN = int(os.getenv("EVENT_WINDOW_AFTER_MINUTES", "60") or 60)


def _events_utc() -> list[dict[str, Any]]:
    out = []
    for event_type, day, hhmm, title in _CALENDAR:
        local = datetime.fromisoformat(f"{day}T{hhmm}").replace(tzinfo=_ET)
        out.append({
            "event_type": event_type,
            "title": title,
            "at": local.astimezone(timezone.utc),
        })
    out.sort(key=lambda e: e["at"])
    return out


def upcoming_events(now: Optional[datetime] = None, limit: int = 8) -> list[dict[str, Any]]:
    now = now or datetime.now(timezone.utc)
    out = []
    for e in _events_utc():
        if e["at"] <= now:
            continue
        delta = e["at"] - now
        out.append({
            "event_type": e["event_type"],
            "title": e["title"],
            "at": e["at"].strftime("%Y-%m-%dT%H:%M:%SZ"),
            "hours_until": round(delta.total_seconds() / 3600, 1),
            "days_until": round(delta.total_seconds() / 86400, 1),
        })
        if len(out) >= limit:
            break
    return out


def recent_events(now: Optional[datetime] = None, limit: int = 3) -> list[dict[str, Any]]:
    now = now or datetime.now(timezone.utc)
    past = [e for e in _events_utc() if e["at"] <= now]
    out = []
    for e in past[-limit:]:
        delta = now - e["at"]
        out.append({
            "event_type": e["event_type"],
            "title": e["title"],
            "at": e["at"].strftime("%Y-%m-%dT%H:%M:%SZ"),
            "hours_ago": round(delta.total_seconds() / 3600, 1),
        })
    return out


def active_event_window(now: Optional[datetime] = None) -> Optional[dict[str, Any]]:
    """The event whose release window contains `now`, or None.

    Window = [at - EVENT_WINDOW_BEFORE_MINUTES, at + EVENT_WINDOW_AFTER_MINUTES].
    """
    now = now or datetime.now(timezone.utc)
    for e in _events_utc():
        start = e["at"] - timedelta(minutes=_WINDOW_BEFORE_MIN)
        end = e["at"] + timedelta(minutes=_WINDOW_AFTER_MIN)
        if start <= now <= end:
            return {
                "event_type": e["event_type"],
                "title": e["title"],
                "at": e["at"].strftime("%Y-%m-%dT%H:%M:%SZ"),
                "window_start": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "window_end": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "minutes_to_release": round((e["at"] - now).total_seconds() / 60, 1),
            }
    return None


def build_events_payload(now: Optional[datetime] = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    return {
        "available": True,
        "next": upcoming_events(now),
        "recent": recent_events(now),
        "event_window": active_event_window(now),
        "window_minutes": {"before": _WINDOW_BEFORE_MIN, "after": _WINDOW_AFTER_MIN},
        "note": ("Scheduled macro releases are volatility events, not direction "
                 "events (event-study: significant abnormal volatility, "
                 "insignificant abnormal returns). Dates static; FOMC dates are "
                 "tentative until confirmed by the preceding meeting."),
        "as_of": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
