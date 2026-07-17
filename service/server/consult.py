"""Consultation chat (Plan 06 C3) — the Personalized-mode advisory loop.

A stateful conversation with the decision-tier model that can see the same
live context the automated pipeline sees (quant snapshot, psychology, regime,
events, whale flows, the user's positions) plus the user's own guidelines.
It ends in an optional handoff: `propose_rule()` asks the model to distill the
conversation into a concrete automation-rule draft, which the UI pre-fills for
a one-click confirm.

Boundaries (deliberate):
  * The chat NEVER places an order. It can only *propose* a rule; creating it
    is a separate, explicit user action through the normal rule API, and every
    resulting order still passes the deterministic risk gate.
  * Proposals are clamped to the same bounds as Agent Mode's planner, so a
    persuasive conversation cannot widen the box.
  * No LLM configured -> the chat honestly reports it is unavailable rather
    than faking an advisor.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional

from database import begin_write_transaction, get_db_connection

logger = logging.getLogger(__name__)

MAX_HISTORY_MESSAGES = 20        # last N turns fed back to the model
MAX_MESSAGE_CHARS = 2000
MAX_SESSIONS_PER_AGENT = 50

SYSTEM_PROMPT = (
    "You are a trading consultant on Sooppiy, a PAPER-TRADING research platform. "
    "You advise; you never execute. Be concrete, quantitative and honest about "
    "uncertainty — say plainly when the evidence is weak or the data is missing. "
    "Never promise returns. Keep answers under 180 words unless asked for depth. "
    "If the user asks you to set up automation, describe the concrete parameters "
    "you would use (symbol, cadence, min confidence, size, risk level) and tell "
    "them they can turn it into a rule with the 'propose rule' action."
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ─────────────────────────── sessions & messages ───────────────────────────

def create_session(agent_id: int, symbol: Optional[str], market: str = "crypto",
                   title: Optional[str] = None) -> int:
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        begin_write_transaction(cursor)
        cursor.execute(
            """INSERT INTO chat_sessions (agent_id, symbol, market, title, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (agent_id, (symbol or "").upper() or None, market, title, _now_iso(), _now_iso()))
        session_id = cursor.lastrowid
        conn.commit()
        return session_id
    finally:
        conn.close()


def get_session(session_id: int, agent_id: int) -> Optional[dict[str, Any]]:
    conn = get_db_connection()
    try:
        row = conn.execute("SELECT * FROM chat_sessions WHERE id = ? AND agent_id = ?",
                           (session_id, agent_id)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_sessions(agent_id: int, limit: int = 20) -> list[dict[str, Any]]:
    """Consultation sessions only — the global AI Assistant shares this table
    but is its own surface and must not appear in the consultation list."""
    from assistant import ASSISTANT_MARKET
    conn = get_db_connection()
    try:
        rows = conn.execute(
            """SELECT s.*, (SELECT COUNT(*) FROM chat_messages m WHERE m.session_id = s.id) AS n_messages
               FROM chat_sessions s WHERE s.agent_id = ? AND s.market != ?
               ORDER BY s.id DESC LIMIT ?""", (agent_id, ASSISTANT_MARKET, limit)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_messages(session_id: int, limit: int = 100) -> list[dict[str, Any]]:
    conn = get_db_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM chat_messages WHERE session_id = ? ORDER BY id ASC LIMIT ?",
            (session_id, limit)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _add_message(session_id: int, role: str, content: str,
                 llm_model: Optional[str] = None) -> None:
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        begin_write_transaction(cursor)
        cursor.execute(
            """INSERT INTO chat_messages (session_id, role, content, llm_model, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (session_id, role, content[:8000], llm_model, _now_iso()))
        cursor.execute("UPDATE chat_sessions SET updated_at = ? WHERE id = ?",
                       (_now_iso(), session_id))
        conn.commit()
    finally:
        conn.close()


def delete_session(session_id: int, agent_id: int) -> bool:
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        begin_write_transaction(cursor)
        cursor.execute("SELECT id FROM chat_sessions WHERE id = ? AND agent_id = ?",
                       (session_id, agent_id))
        if not cursor.fetchone():
            conn.rollback()
            return False
        cursor.execute("DELETE FROM chat_messages WHERE session_id = ?", (session_id,))
        cursor.execute("DELETE FROM chat_sessions WHERE id = ?", (session_id,))
        conn.commit()
        return True
    finally:
        conn.close()


# ─────────────────────────── context ───────────────────────────

def build_context(agent_id: int, symbol: Optional[str], market: str) -> dict[str, Any]:
    """The same live picture the automated pipeline sees. Fail-soft per source."""
    ctx: dict[str, Any] = {}
    if symbol and market == "crypto":
        try:
            from quant_crypto import build_crypto_analysis, quant_crypto_enabled
            if quant_crypto_enabled():
                a = build_crypto_analysis(symbol) or {}
                ctx["quant"] = {k: a.get(k) for k in
                                ("current_price", "rsi", "signal", "signal_score",
                                 "sigma_daily_pct", "funding_rate", "basis_pct")}
        except Exception:  # noqa: BLE001
            pass
    try:
        from psych_feed import get_psych_payload
        p = get_psych_payload()
        if p.get("available"):
            ctx["psych"] = {"fear_greed": p.get("fear_greed"),
                            "shock": [s for s in p.get("shock", []) if s.get("shock")],
                            "whales": (p.get("whales") or {}).get("totals")}
    except Exception:  # noqa: BLE001
        pass
    try:
        from regime import evaluate_market_regime
        r = evaluate_market_regime()
        ctx["regime"] = {k: r.get(k) for k in ("regime", "reasons")}
    except Exception:  # noqa: BLE001
        pass
    try:
        from market_events import active_event_window, upcoming_events
        ctx["event_window"] = active_event_window()
        nxt = upcoming_events(limit=1)
        ctx["next_event"] = {"title": nxt[0].get("title"), "at": nxt[0].get("at")} if nxt else None
    except Exception:  # noqa: BLE001
        pass
    try:
        conn = get_db_connection()
        rows = conn.execute(
            """SELECT symbol, quantity, entry_price, current_price FROM positions
               WHERE agent_id = ? AND quantity != 0""", (agent_id,)).fetchall()
        conn.close()
        ctx["my_positions"] = [dict(r) for r in rows]
    except Exception:  # noqa: BLE001
        pass
    return ctx


# ─────────────────────────── the turn ───────────────────────────

def chat_turn(agent_id: int, session: dict[str, Any], user_message: str) -> dict[str, Any]:
    """One conversational turn. Persists both sides; returns the reply."""
    from llm_client import active_provider_model, generate_text, llm_configured

    user_message = (user_message or "").strip()[:MAX_MESSAGE_CHARS]
    if not user_message:
        raise ValueError("message is required")

    _add_message(session["id"], "user", user_message)

    if not llm_configured():
        reply = ("The AI consultant is unavailable right now (no model configured on this "
                 "server). Your message was saved — the deterministic signals on the "
                 "Signals Board and your automation rules keep working.")
        _add_message(session["id"], "assistant", reply, llm_model=None)
        return {"reply": reply, "llm_model": None, "available": False}

    guidelines = None
    try:
        from services import guidelines_for_agent
        guidelines = guidelines_for_agent(agent_id)
    except Exception:  # noqa: BLE001
        pass

    context = build_context(agent_id, session.get("symbol"), session.get("market") or "crypto")
    history = get_messages(session["id"], limit=MAX_HISTORY_MESSAGES + 1)[:-1]
    history = history[-MAX_HISTORY_MESSAGES:]
    transcript = "\n".join(f"{m['role'].upper()}: {m['content']}" for m in history)

    guide_block = (f"USER GUIDELINES (honor them; they may make you more cautious but "
                   f"never override risk limits):\n{guidelines}\n\n") if guidelines else ""
    prompt = (
        guide_block +
        (f"Focus asset: {session['symbol']} ({session['market']})\n" if session.get("symbol") else "") +
        f"LIVE CONTEXT (JSON):\n{json.dumps(context, ensure_ascii=False, default=str)[:5000]}\n\n" +
        (f"CONVERSATION SO FAR:\n{transcript}\n\n" if transcript else "") +
        f"USER: {user_message}\n\nReply as the consultant."
    )
    reply = generate_text(prompt, system=SYSTEM_PROMPT, max_tokens=700,
                          temperature=0.4, tier="decision")
    if not reply:
        reply = ("I couldn't reach the model for that answer — please try again. "
                 "(Nothing was executed; this chat never places orders.)")
        _add_message(session["id"], "assistant", reply, llm_model=None)
        return {"reply": reply, "llm_model": None, "available": False}

    model = active_provider_model(tier="decision")
    _add_message(session["id"], "assistant", reply, llm_model=model)
    return {"reply": reply, "llm_model": model, "available": True}


# ─────────────────────────── rule handoff ───────────────────────────

def _parse_rule_json(text: str) -> Optional[dict[str, Any]]:
    if not text:
        return None
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except Exception:  # noqa: BLE001
        return None


def propose_rule(agent_id: int, session: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Distill the conversation into an automation-rule DRAFT.

    Returns a draft the UI pre-fills — it does NOT create the rule. Values are
    clamped to Agent Mode's PLAN_BOUNDS so a persuasive chat can't widen the box.
    """
    from llm_client import generate_text, llm_configured
    if not llm_configured():
        return None
    history = get_messages(session["id"], limit=MAX_HISTORY_MESSAGES)
    if not history:
        return None
    transcript = "\n".join(f"{m['role'].upper()}: {m['content']}" for m in history)
    prompt = (
        "Distill the consultation below into ONE concrete paper-trading automation rule. "
        "Use only what the conversation supports; prefer caution when it is ambiguous.\n"
        "Respond with ONLY a JSON object:\n"
        '{"symbol":"BTCUSDT","market":"crypto","interval_minutes":15-1440,'
        '"min_confidence":0.55-0.9,"size_usd":number,"risk_level":"stable|balanced|aggressive",'
        '"rationale":"1-2 sentences tying this to the conversation"}\n\n'
        f"CONSULTATION:\n{transcript}\n"
    )
    raw = _parse_rule_json(generate_text(prompt, max_tokens=400, temperature=0.2,
                                         tier="decision") or "")
    if not raw:
        return None

    # Clamp with Agent Mode's bounds — one source of truth for the box.
    from agent_planner import PLAN_BOUNDS
    lo_i, hi_i = PLAN_BOUNDS["interval_minutes"]
    lo_c, hi_c = PLAN_BOUNDS["min_confidence"]

    def _num(key, default):
        try:
            return float(raw.get(key))
        except (TypeError, ValueError):
            return default

    symbol = str(raw.get("symbol") or session.get("symbol") or "BTCUSDT").upper()
    risk = str(raw.get("risk_level") or "").lower()
    if risk not in PLAN_BOUNDS["risk_levels"]:
        risk = "balanced"
    market = str(raw.get("market") or session.get("market") or "crypto").lower()
    if market not in ("crypto", "us-stock"):
        market = "crypto"
    return {
        "symbol": symbol,
        "market": market,
        "interval_minutes": int(min(hi_i, max(lo_i, _num("interval_minutes", 60)))),
        "min_confidence": round(min(hi_c, max(lo_c, _num("min_confidence", 0.65))), 2),
        "size_usd": round(min(10000.0, max(10.0, _num("size_usd", 500))), 2),
        "risk_level": risk,
        "rationale": str(raw.get("rationale") or "")[:500],
        "auto_execute": False,   # the user opts in explicitly; never pre-armed
        "account_type": "simulator",
    }
