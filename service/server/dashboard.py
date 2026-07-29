"""The after-login desk view — the four panels the dashboard design specifies
but the page never had (docs/design/dashboard-gate-preview.html).

    확인이 필요합니다   a run whose own desk has stopped believing its thesis
    내 AI가 한 일        the last few decisions, WITH the reason
    내 시각 기준 개장    which of my markets are open, on my clock
    내 순위              where my book actually stands

One endpoint, not four. The page already makes five calls on mount; four more
round trips for four small panels is the wrong trade, and every one of these
reads the same agent scope.

Everything here is READ-ONLY and fail-soft per panel: a panel that cannot be
computed comes back empty rather than 500-ing the whole view. A dashboard is
the screen a member opens when something already looks wrong — it is the last
place that should fail closed.

Text is NOT localized here. Panels return codes and numbers; the frontend owns
the words, the same way it does for regime/side/market elsewhere. The one
exception is `reason`, which is the AI's own free-text rationale — already
written in the member's language by the desk that produced it.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from database import get_db_connection

logger = logging.getLogger(__name__)

# Markets the sessions strip covers, in the design's order. Derived list, not
# a hand-kept one — see markets.tradeable_markets() for why enumerating by
# hand is how a market silently goes missing from a panel.
_SESSION_ORDER = ("crypto", "forex", "futures", "a-stock", "us-stock")

# How far back the decision feed looks. A member who has not traded in three
# days should see their last decisions, not an empty card.
_DECISION_LOOKBACK_DAYS = 14


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ───────────────────────────── 확인이 필요합니다 ─────────────────────────────

def attention(agent_id: int) -> list[dict[str, Any]]:
    """Runs whose desk has marked its own thesis down, repeatedly.

    Reuses run_engine's decay streak rather than re-deriving it: the rail and
    the panel must never disagree about what "3회 연속" means. The rail is
    default-OFF (RUN_THESIS_DECAY_ENABLED), which is exactly why this panel
    earns its place — it surfaces the shadow read so the member can act on it
    while the automatic hand-back is still dark.
    """
    try:
        from run_engine import (_thesis_decay_floor, _thesis_decay_streak,
                                _thesis_decay_strikes)
        import trading_runs
    except Exception:  # noqa: BLE001
        return []

    floor = _thesis_decay_floor()
    strikes = _thesis_decay_strikes()
    if floor <= 0 or strikes <= 0:
        return []

    out: list[dict[str, Any]] = []
    try:
        for run in trading_runs.list_runs(agent_id) or []:
            if run.get("status") not in ("running", "paused"):
                continue
            streak = _thesis_decay_streak(run["id"])
            # Warn one cycle BEFORE the rail would fire. A card that appears
            # in the same pass the slot is handed back is a notification, not
            # an attention item — there is nothing left to decide.
            if streak < max(2, strikes - 1):
                continue
            out.append({
                "run_id": run["id"],
                "symbol": run.get("symbol"),
                "market": run.get("market"),
                "kind": "thesis_decay",
                "streak": streak,
                "strikes": strikes,
                "floor": floor,
                "at_rail": streak >= strikes,
            })
    except Exception:  # noqa: BLE001
        logger.debug("attention panel failed for agent %s", agent_id, exc_info=True)
        return out
    out.sort(key=lambda r: (-r["streak"], r["run_id"]))
    return out[:5]


# ───────────────────────────── 내 AI가 한 일 ─────────────────────────────

def _decision_action(payload: dict) -> str:
    """buy/sell/short/cover/hold → the three states the panel shows."""
    action = str(payload.get("action") or "").strip().lower()
    if action in ("buy", "short"):
        return "enter"
    if action in ("sell", "cover"):
        return "exit"
    return "hold"


def recent_decisions(agent_id: int, limit: int = 3) -> list[dict[str, Any]]:
    """The desk's last decisions across every run this member owns.

    `reason` is the model's own report text — it was generated in the
    member's language at decision time, so it is passed through untouched.
    An empty report is not skipped: "the desk decided and said nothing" is
    itself worth seeing, and dropping the row would misrepresent the count.
    """
    limit = max(1, min(int(limit or 3), 20))
    cutoff = (_now() - timedelta(days=_DECISION_LOOKBACK_DAYS)
              ).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """SELECT e.ts, e.payload, r.id AS run_id, r.symbol, r.market,
                      r.market_type, r.status
               FROM run_events e
               JOIN trading_runs r ON r.id = e.run_id
               WHERE r.agent_id = ? AND e.event_type = 'decision' AND e.ts >= ?
               ORDER BY e.id DESC LIMIT ?""",
            (agent_id, cutoff, limit))
        rows = cursor.fetchall()
    except Exception:  # noqa: BLE001
        logger.debug("decision feed failed for agent %s", agent_id, exc_info=True)
        return []
    finally:
        try:
            if conn is not None:
                conn.close()
        except Exception:  # noqa: BLE001
            pass

    out: list[dict[str, Any]] = []
    for row in rows:
        try:
            payload = json.loads(row["payload"] or "{}") or {}
        except (ValueError, TypeError):
            payload = {}
        scores = payload.get("scores") if isinstance(payload.get("scores"), dict) else {}
        out.append({
            "run_id": row["run_id"],
            "symbol": row["symbol"],
            "market": row["market"],
            "market_type": row["market_type"],
            "action": _decision_action(payload),
            "raw_action": str(payload.get("action") or "").lower() or None,
            "reason": (payload.get("report") or "").strip() or None,
            "confidence": payload.get("confidence"),
            "conviction": payload.get("conviction"),
            "thesis_alignment": scores.get("thesis_alignment"),
            "entry": payload.get("entry"),
            "at": row["ts"],
        })
    return out


# ───────────────────────────── 내 시각 기준 개장 ─────────────────────────────

def sessions(tz: Optional[str], at: Optional[datetime] = None) -> dict[str, Any]:
    """Per-market open windows across the member's local day.

    Computed from markets.is_market_open() rather than a table of hours, for
    the same reason the market-hours guide is generated: the moment a session
    calendar changes, a hand-written panel is wrong and nothing says so.

    Sampling is 15-minute — 96 probes per market instead of 1,440. Every
    session boundary in markets.py lands on a quarter hour, so the coarser
    grid gives identical bands at a fifteenth of the cost, and this runs on
    every dashboard load.
    """
    from regions import normalize_timezone
    zone_name = normalize_timezone(tz) or "UTC"
    try:
        from zoneinfo import ZoneInfo
        zone = ZoneInfo(zone_name)
    except Exception:  # noqa: BLE001
        from zoneinfo import ZoneInfo
        zone, zone_name = ZoneInfo("UTC"), "UTC"

    import markets
    now = (at or _now()).astimezone(zone)
    day0 = now.replace(hour=0, minute=0, second=0, microsecond=0)

    step = 15
    steps = (24 * 60) // step
    out: list[dict[str, Any]] = []
    for market in _SESSION_ORDER:
        if market not in markets.tradeable_markets():
            continue
        bands: list[list[float]] = []
        start: Optional[int] = None
        for i in range(steps):
            local = day0 + timedelta(minutes=i * step)
            try:
                is_open = markets.is_market_open(market, local.astimezone(timezone.utc))
            except Exception:  # noqa: BLE001
                is_open = False
            if is_open and start is None:
                start = i
            elif not is_open and start is not None:
                bands.append([start * step / 60, i * step / 60])
                start = None
        if start is not None:
            bands.append([start * step / 60, 24.0])
        try:
            open_now = markets.is_market_open(market, now.astimezone(timezone.utc))
        except Exception:  # noqa: BLE001
            open_now = False
        out.append({
            "market": market,
            "bands": bands,
            "open_now": open_now,
            # 24.0 total means the market never closes on this day; the UI
            # labels that differently from "opens at 22:30".
            "open_hours": round(sum(b[1] - b[0] for b in bands), 2),
        })
    return {"timezone": zone_name,
            "now_hour": round(now.hour + now.minute / 60, 3),
            "markets": out}


# ───────────────────────────── 내 순위 ─────────────────────────────

def my_rank(agent_id: int, metric: str = "return") -> Optional[dict[str, Any]]:
    """This agent's own standing on the board, or None if it is not rankable.

    None is a real answer, not a failure: an agent with no published
    operation is deliberately unranked (leaderboard_snapshot.rankable_where),
    and inventing a position for it would be the "0건을 0%로 줄세우는" problem
    the board rules exist to avoid.
    """
    try:
        from leaderboard_snapshot import _compute_agent_rows, rankable_where  # noqa: F401
    except Exception:  # noqa: BLE001
        return None
    try:
        rows = _compute_agent_rows() or []
    except Exception:  # noqa: BLE001
        logger.debug("rank panel failed for agent %s", agent_id, exc_info=True)
        return None

    key = {
        "return": lambda r: float(r.get("profit_percent") or 0),
        "risk": lambda r: float(r.get("risk_adjusted_score") or 0),
        "collaboration": lambda r: float(r.get("collaboration_score") or 0),
        "quality": lambda r: float(r.get("quality_score_avg") or 0),
    }.get(metric, lambda r: float(r.get("profit_percent") or 0))

    ranked = sorted(rows, key=key, reverse=True)
    for i, row in enumerate(ranked, start=1):
        if int(row.get("agent_id") or 0) != int(agent_id):
            continue
        return {
            "rank": i,
            "of": len(ranked),
            "metric": metric,
            "agent_id": agent_id,
            "name": row.get("name"),
            "profit_percent": float(row.get("profit_percent") or 0),
            "trade_count": int(row.get("trade_count") or 0),
            "risk_adjusted_score": float(row.get("risk_adjusted_score") or 0),
            "max_drawdown": row.get("max_drawdown"),
        }
    return None


# ───────────────────────────── the one call ─────────────────────────────

def desk_view(agent_id: int, tz: Optional[str], metric: str = "return") -> dict[str, Any]:
    """All four panels. Each is independently fail-soft — one bad panel must
    not blank the other three."""
    def _safe(fn, default):
        try:
            return fn()
        except Exception:  # noqa: BLE001
            logger.debug("desk panel failed", exc_info=True)
            return default

    return {
        "attention": _safe(lambda: attention(agent_id), []),
        "decisions": _safe(lambda: recent_decisions(agent_id), []),
        "sessions": _safe(lambda: sessions(tz), {"timezone": "UTC", "markets": []}),
        "rank": _safe(lambda: my_rank(agent_id, metric), None),
    }
