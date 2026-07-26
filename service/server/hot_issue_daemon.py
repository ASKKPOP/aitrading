"""E2 v1 — hot-issue daemon: hourly watch over every user's RUN symbols.

Three-stage design (2026-07-25, per-user verification is the point):

  1. GLOBAL detection — deterministic, zero-LLM triggers from feeds that
     already ship: macro event window (market_events), crypto liquidation
     shock + panic/euphoria regime (psych_feed / regime), and a large daily
     price move on the symbol itself. A hot issue is a fact about the
     MARKET.
  2. PER-USER verification — whether it matters is a fact about each USER.
     The issue is joined against every affected run's own book: position
     holders get a personalized, direction-aware alert; flat runs get no
     alert (silence is part of the product).
  3. Escalation — every affected run receives a 'hot_issue' run-event and
     the E1 situation classifier routes its next cycle to the FULL analyst
     pipeline, so the final judgment is made with that user's own context.

Costs nothing per quiet symbol (no LLM anywhere in v1); a per-symbol
cooldown (HOT_ISSUE_COOLDOWN_HOURS) stops re-alerting the same state.
Registry key 'hot_issue_daemon', role 'research'; the loop is gated by
HOT_ISSUE_DAEMON_ENABLED (default off) and every signal read is fail-soft.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from database import begin_write_transaction, get_db_connection

logger = logging.getLogger(__name__)

TS_FMT = "%Y-%m-%dT%H:%M:%SZ"


def daemon_enabled() -> bool:
    return os.getenv("HOT_ISSUE_DAEMON_ENABLED", "false").strip().lower() in (
        "1", "true", "yes", "on")


def _interval_seconds() -> int:
    return max(300, int(os.getenv("HOT_ISSUE_INTERVAL", "3600")))


def _cooldown_hours() -> float:
    return max(0.5, float(os.getenv("HOT_ISSUE_COOLDOWN_HOURS", "4")))


def _price_move_pct() -> float:
    return max(1.0, float(os.getenv("HOT_ISSUE_PRICE_MOVE_PCT", "5.0")))


def llm_verify_enabled() -> bool:
    """Stage 2' (E2-B'): one small decision-tier call per MATERIAL user that
    personalizes the verdict for their book. Default off; the deterministic
    verdict ships either way, so this only ever enriches."""
    return os.getenv("HOT_ISSUE_LLM_VERIFY", "false").strip().lower() in (
        "1", "true", "yes", "on")


def _personal_verdict(run: dict[str, Any], side: str,
                      triggers: list[str]) -> str:
    """The alert's {verdict} sentence. Deterministic default; when the LLM
    layer is on, ask for stance/urgency/note for THIS user's book — fail-soft
    back to the default on any trouble."""
    verdict = f"Affects your {side} position."
    if not llm_verify_enabled():
        return verdict
    try:
        from llm_client import generate_text
        prompt = (
            "A market event hit a symbol one specific user is trading. "
            f"Event triggers: {', '.join(triggers)}. Symbol: {run['symbol']} "
            f"({run['market']}). The user's book: a {side.upper()} position "
            "held by an automated run.\n"
            "For THIS user only: is the event for, against, or neutral to "
            "their position, and how urgent is it? A shock/volatility event "
            "with no clear direction raises risk for BOTH sides — treat it "
            "as stance neutral with urgency medium-or-high, and say why in "
            "the note. Never ask for more information.\n"
            "Respond with ONLY the JSON object, no prose before or after: "
            '{"stance": "for"|"against"|"neutral", '
            '"urgency": "low"|"medium"|"high", "note": "<one short sentence>"}')
        text = generate_text(prompt, max_tokens=120, temperature=0.2,
                             tier="decision")
        data = json.loads(text[text.index("{"):text.rindex("}") + 1])
        stance = str(data.get("stance") or "").strip().lower()
        urgency = str(data.get("urgency") or "").strip().lower()
        note = str(data.get("note") or "").strip()[:120]
        if stance in ("for", "against", "neutral"):
            return f"{stance.upper()} your {side} ({urgency or 'medium'}): {note}"
    except Exception:  # noqa: BLE001
        logger.debug("hot-issue LLM verify failed (run %s)", run.get("id"),
                     exc_info=True)
    return verdict


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime(TS_FMT)


# ── stage 1: global detection (zero-LLM, fail-soft per signal) ──────────────

def _market_triggers(market: str) -> list[str]:
    """Market-level triggers shared by every symbol of that market."""
    triggers: list[str] = []
    try:
        from market_events import active_event_window
        if active_event_window():
            triggers.append("event_window")
    except Exception:  # noqa: BLE001
        pass
    if market == "crypto":
        try:
            from psych_feed import get_psych_payload
            psych = get_psych_payload()
            if psych.get("available") and psych.get("shock"):
                triggers.append("psych_shock")
        except Exception:  # noqa: BLE001
            pass
        try:
            from regime import current_regime_state
            state = current_regime_state()
            if state and state.get("regime") in ("event", "panic", "euphoria"):
                triggers.append(f"regime:{state['regime']}")
        except Exception:  # noqa: BLE001
            pass
    return triggers


def _symbol_triggers(market: str, symbol: str) -> list[str]:
    """Per-symbol trigger: an outsized day move on the symbol itself."""
    try:
        import price_fetcher
        candles = price_fetcher.get_daily_candles(symbol, market, days=2)
        if candles and len(candles) >= 2:
            prev = float(candles[-2]["close"] or 0)
            last = float(candles[-1]["close"] or 0)
            if prev > 0 and last > 0:
                move = (last - prev) / prev * 100.0
                if abs(move) >= _price_move_pct():
                    return [f"price_move:{move:+.1f}%"]
    except Exception:  # noqa: BLE001
        pass
    return []


def _recent_issue(cursor, market: str, symbol: str) -> bool:
    since = (datetime.now(timezone.utc)
             - timedelta(hours=_cooldown_hours())).strftime(TS_FMT)
    cursor.execute(
        "SELECT id FROM hot_issues WHERE market = ? AND symbol = ? AND "
        "created_at > ? LIMIT 1", (market, symbol, since))
    return cursor.fetchone() is not None


def recent_hot_issue(market: str, symbol: str) -> bool:
    """Read API for the E1 classifier: a non-expired hot issue exists for the
    tuple. Own connection, fail-soft False."""
    try:
        conn = get_db_connection()
        try:
            return _recent_issue(conn.cursor(), market, symbol)
        finally:
            conn.close()
    except Exception:  # noqa: BLE001
        return False


# ── stage 2 + 3: per-user verification, alert, escalation ───────────────────

def _watch_map(cursor) -> dict[tuple[str, str], list[dict[str, Any]]]:
    """(market, symbol) → the non-terminal runs watching it, across ALL users.
    Distinct symbols are analyzed once; the fan-out is per run/user."""
    cursor.execute(
        """SELECT id, agent_id, market, symbol FROM trading_runs
           WHERE status IN ('armed', 'running', 'paused')""")
    out: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in cursor.fetchall():
        out.setdefault((row["market"], row["symbol"]), []).append(dict(row))
    return out


def _position_side(cursor, run: dict[str, Any]) -> Optional[str]:
    """'long' / 'short' when this run's book holds the symbol, else None."""
    cursor.execute(
        "SELECT quantity FROM positions WHERE agent_id = ? AND market = ? AND "
        "symbol = ? AND run_id = ? AND quantity != 0",
        (run["agent_id"], run["market"], run["symbol"], run["id"]))
    row = cursor.fetchone()
    if not row:
        return None
    return "long" if float(row["quantity"]) > 0 else "short"


def run_daemon_tick() -> dict[str, int]:
    """One sweep: detect per distinct symbol, verify per user, alert + emit.
    Never raises; returns counters for the loop log."""
    out = {"symbols": 0, "hot": 0, "alerts": 0, "events": 0}
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        watch = _watch_map(cursor)
    finally:
        conn.close()
    out["symbols"] = len(watch)
    market_cache: dict[str, list[str]] = {}
    for (market, symbol), runs in watch.items():
        if market not in market_cache:
            market_cache[market] = _market_triggers(market)
        triggers = list(market_cache[market]) + _symbol_triggers(market, symbol)
        if not triggers:
            continue
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            if _recent_issue(cursor, market, symbol):
                continue
            begin_write_transaction(cursor)
            cursor.execute(
                "INSERT INTO hot_issues (market, symbol, triggers_json, "
                "severity, created_at) VALUES (?, ?, ?, ?, ?)",
                (market, symbol, json.dumps(triggers),
                 "high" if "psych_shock" in triggers else "medium", _now_iso()))
            conn.commit()
        except Exception:  # noqa: BLE001
            logger.warning("hot_issues insert failed (%s:%s)", market, symbol,
                           exc_info=True)
            try:
                conn.rollback()
            except Exception:  # noqa: BLE001
                pass
            continue
        finally:
            conn.close()
        out["hot"] += 1

        # per-user fan-out: verify against each run's own book
        for run in runs:
            conn = get_db_connection()
            try:
                side = _position_side(conn.cursor(), run)
            finally:
                conn.close()
            try:
                from trading_runs import emit_telemetry_event
                if emit_telemetry_event(run["id"], "hot_issue",
                                        {"triggers": triggers,
                                         "position_side": side}) is not None:
                    out["events"] += 1
            except Exception:  # noqa: BLE001
                pass
            if side is None:
                continue  # flat run: escalate silently, never alert
            try:
                import alerts
                alerts.send_alert(
                    run["agent_id"], "hot_issue", "hot_issue_position",
                    {"symbol": symbol, "market": market, "side": side,
                     "run_id": run["id"], "triggers": ", ".join(triggers),
                     "verdict": _personal_verdict(run, side, triggers)},
                    dedupe_key=f"hot:{market}:{symbol}:{run['id']}")
                out["alerts"] += 1
            except Exception:  # noqa: BLE001
                logger.warning("hot-issue alert failed (run %s)", run["id"],
                               exc_info=True)
    return out


async def hot_issue_daemon_loop() -> None:
    """Registry key 'hot_issue_daemon', role 'research'. Enabled-gated each
    pass so the flag can flip without a restart."""
    import asyncio

    await asyncio.sleep(11)
    while True:
        try:
            if daemon_enabled():
                stats = run_daemon_tick()
                if stats["hot"]:
                    print(f"[HotIssue] tick: {stats}")
        except Exception as exc:  # noqa: BLE001
            logger.warning("[HotIssue] tick crashed: %s", exc)
        await asyncio.sleep(_interval_seconds())
