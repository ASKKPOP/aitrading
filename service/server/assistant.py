"""AI Assistant (Plan 06 C3) — the user's own advisor, with full context.

Unlike the per-symbol consultation chat, the assistant is GLOBAL and
persistent: one conversation per agent, available from every page, holding the
complete picture of that user's account:

    identity      agent name, cash, points, age
    portfolio     open positions with live P&L, SL/TP, long/short
    performance   replayed trade stats (win rate, payoff, realized today)
    risk          limits, breaker state, portfolio caps
    automation    every rule (incl. Agent Mode budget + schedule), recent runs
                  with the AI-verify verdicts, Agent-Mode decision log
    personalized  guidelines, watches (with live values), recent alerts
    settings      LLM provider/model, alert channels — keys are NEVER included
    calibration   live confluence -> hit-rate table

Privacy: the profile is assembled per-request for the authenticated agent and
is never persisted into the transcript. API keys are excluded entirely — the
assistant is told only WHETHER a key is configured, never its value.

Boundary: advisory only. The assistant explains, reviews and recommends; it
cannot place orders or change settings. Every action stays the user's, through
the normal UI, behind the deterministic risk gate.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from database import begin_write_transaction, get_db_connection

logger = logging.getLogger(__name__)

MAX_HISTORY_MESSAGES = 24
MAX_MESSAGE_CHARS = 2000
ASSISTANT_MARKET = "assistant"      # marks the singleton session in chat_sessions

SYSTEM_PROMPT = (
    "You are the user's personal AI assistant on Sooppiy, a PAPER-TRADING research "
    "platform. You can see their whole account: positions, performance, automation "
    "rules, risk limits, guidelines, watches, alerts and settings.\n"
    "You ADVISE and EXPLAIN; you never execute. You cannot place orders or change "
    "settings — when something needs doing, tell the user exactly where to do it "
    "(e.g. 'Automation → 완전 위임', 'Settings → AI 지침', 'Monitoring → 내 감시 조건').\n"
    "Ground every claim in the account data you were given. If the data does not "
    "support an answer, say so plainly. Never invent numbers, never promise returns, "
    "and be honest that all trading here is simulated. Answer in the user's language. "
    "Be concise (under 200 words) unless they ask for depth."
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ─────────────────────────── the profile ───────────────────────────

def build_user_profile(agent_id: int) -> dict[str, Any]:
    """Everything the assistant knows about this user. Fail-soft per section:
    a broken section is omitted rather than faked."""
    profile: dict[str, Any] = {"as_of": _now_iso()}
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # identity + cash
        try:
            row = cursor.execute(
                """SELECT a.name, a.cash, a.points, a.created_at, u.email
                   FROM agents a LEFT JOIN users u ON u.id = a.user_id
                   WHERE a.id = ?""", (agent_id,)).fetchone()
            if row:
                profile["identity"] = {"agent": row["name"], "email": row["email"],
                                       "cash_usd": round(float(row["cash"] or 0), 2),
                                       "points": row["points"], "since": row["created_at"]}
        except Exception:  # noqa: BLE001
            pass

        # portfolio
        try:
            rows = cursor.execute(
                """SELECT symbol, market, quantity, entry_price, current_price,
                          stop_loss, take_profit, opened_at
                   FROM positions WHERE agent_id = ? AND quantity != 0""",
                (agent_id,)).fetchall()
            positions = []
            for r in rows:
                qty = float(r["quantity"])
                entry = float(r["entry_price"] or 0)
                cur = float(r["current_price"] or entry)
                pnl = (cur - entry) * qty  # negative qty (short) flips the sign correctly
                positions.append({
                    "symbol": r["symbol"], "market": r["market"],
                    "side": "short" if qty < 0 else "long",
                    "quantity": abs(qty), "entry_price": entry, "current_price": cur,
                    "unrealized_pnl_usd": round(pnl, 2),
                    "stop_loss": r["stop_loss"], "take_profit": r["take_profit"],
                    "opened_at": r["opened_at"],
                })
            profile["portfolio"] = {
                "positions": positions,
                "deployed_usd": round(sum(abs(p["quantity"]) * p["current_price"]
                                          for p in positions), 2),
                "unrealized_pnl_usd": round(sum(p["unrealized_pnl_usd"] for p in positions), 2),
            }
        except Exception:  # noqa: BLE001
            pass

        # automation rules
        try:
            rows = cursor.execute(
                """SELECT id, symbol, market, mode, budget_usd, interval_minutes,
                          min_confidence, size_usd, auto_execute, account_type, enabled,
                          risk_level, schedule_json, last_run_at
                   FROM automation_configs WHERE agent_id = ? ORDER BY id DESC""",
                (agent_id,)).fetchall()
            profile["automation_rules"] = [dict(r) for r in rows]
        except Exception:  # noqa: BLE001
            pass

        # recent runs (with verify verdicts + calibration priors from telemetry)
        try:
            rows = cursor.execute(
                """SELECT ran_at, action, confidence, executed, skip_reason, confluence_json
                   FROM automation_runs WHERE agent_id = ? ORDER BY id DESC LIMIT 15""",
                (agent_id,)).fetchall()
            runs = []
            for r in rows:
                entry = {"ran_at": r["ran_at"], "action": r["action"],
                         "confidence": r["confidence"], "executed": bool(r["executed"]),
                         "skip_reason": r["skip_reason"]}
                try:
                    tel = json.loads(r["confluence_json"] or "{}")
                    if tel.get("verify"):
                        entry["verify"] = {k: tel["verify"].get(k)
                                           for k in ("verdict", "reason", "mode")}
                    if tel.get("confluence"):
                        entry["buy_confluence"] = tel["confluence"].get("buy_confluence")
                except (TypeError, ValueError):
                    pass
                runs.append(entry)
            profile["recent_runs"] = runs
        except Exception:  # noqa: BLE001
            pass

        # agent-mode decisions
        try:
            rows = cursor.execute(
                """SELECT decided_at, params_json, rationale, planner, llm_model
                   FROM agent_mode_decisions WHERE agent_id = ? ORDER BY id DESC LIMIT 5""",
                (agent_id,)).fetchall()
            if rows:
                profile["agent_mode_decisions"] = [
                    {"decided_at": r["decided_at"], "rationale": r["rationale"],
                     "planner": r["planner"], "model": r["llm_model"],
                     "params": json.loads(r["params_json"] or "{}")} for r in rows]
        except Exception:  # noqa: BLE001
            pass

        # watches
        try:
            rows = cursor.execute(
                """SELECT name, metric, symbol, comparator, threshold, enabled, last_fired_at
                   FROM user_watches WHERE agent_id = ?""", (agent_id,)).fetchall()
            profile["watches"] = [dict(r) for r in rows]
        except Exception:  # noqa: BLE001
            pass

        # alerts
        try:
            rows = cursor.execute(
                """SELECT kind, title, body, channels_json, created_at
                   FROM alert_log WHERE agent_id = ? ORDER BY id DESC LIMIT 10""",
                (agent_id,)).fetchall()
            profile["recent_alerts"] = [dict(r) for r in rows]
        except Exception:  # noqa: BLE001
            pass

        # guidelines + settings (NEVER the key itself — only whether one exists)
        try:
            row = cursor.execute(
                """SELECT u.trading_guidelines FROM users u
                   JOIN agents a ON a.user_id = u.id WHERE a.id = ?""", (agent_id,)).fetchone()
            if row and row["trading_guidelines"]:
                profile["guidelines"] = row["trading_guidelines"]
        except Exception:  # noqa: BLE001
            pass
        try:
            rows = cursor.execute(
                """SELECT s.target, s.api_key, s.config_json, s.enabled
                   FROM user_api_settings s JOIN agents a ON a.user_id = s.user_id
                   WHERE a.id = ?""", (agent_id,)).fetchall()
            settings = {}
            for r in rows:
                try:
                    config = json.loads(r["config_json"] or "{}")
                except (TypeError, ValueError):
                    config = {}
                settings[r["target"]] = {
                    "enabled": bool(r["enabled"]),
                    "key_configured": bool(r["api_key"]),   # never the value
                    **{k: v for k, v in config.items() if k != "api_key"},
                }
            if settings:
                profile["settings"] = settings
        except Exception:  # noqa: BLE001
            pass
    finally:
        conn.close()

    # performance + risk (module helpers own their own connections)
    try:
        from risk_engine import get_breaker, get_risk_limits, trade_stats
        stats = trade_stats(agent_id)
        profile["performance"] = {
            "closed_trades": stats["n_trades"], "win_rate": stats["win_rate"],
            "payoff_ratio": stats["payoff_ratio"], "realized_today_usd": stats["realized_today"],
        }
        profile["risk_limits"] = get_risk_limits(agent_id)
        profile["breaker"] = get_breaker(agent_id)
    except Exception:  # noqa: BLE001
        pass
    try:
        from calibration import get_calibration
        cal = get_calibration()
        if cal.get("available"):
            profile["calibration"] = cal["buckets"]
    except Exception:  # noqa: BLE001
        pass
    return profile


# ─────────────────────────── singleton session ───────────────────────────

def get_or_create_session(agent_id: int) -> dict[str, Any]:
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        row = cursor.execute(
            "SELECT * FROM chat_sessions WHERE agent_id = ? AND market = ? ORDER BY id ASC LIMIT 1",
            (agent_id, ASSISTANT_MARKET)).fetchone()
        if row:
            return dict(row)
        begin_write_transaction(cursor)
        cursor.execute(
            """INSERT INTO chat_sessions (agent_id, symbol, market, title, created_at, updated_at)
               VALUES (?, NULL, ?, 'AI Assistant', ?, ?)""",
            (agent_id, ASSISTANT_MARKET, _now_iso(), _now_iso()))
        session_id = cursor.lastrowid
        conn.commit()
        row = cursor.execute("SELECT * FROM chat_sessions WHERE id = ?", (session_id,)).fetchone()
        return dict(row)
    finally:
        conn.close()


def clear_session(agent_id: int) -> bool:
    session = get_or_create_session(agent_id)
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        begin_write_transaction(cursor)
        cursor.execute("DELETE FROM chat_messages WHERE session_id = ?", (session["id"],))
        conn.commit()
        return True
    finally:
        conn.close()


# ─────────────────────────── the turn ───────────────────────────

def assistant_turn(agent_id: int, user_message: str, lang: str = "en") -> dict[str, Any]:
    """One assistant turn with the full user profile in context."""
    from consult import _add_message, get_messages
    from llm_client import active_provider_model, generate_text, llm_configured

    user_message = (user_message or "").strip()[:MAX_MESSAGE_CHARS]
    if not user_message:
        raise ValueError("message is required")

    session = get_or_create_session(agent_id)
    _add_message(session["id"], "user", user_message)

    if not llm_configured():
        reply = ("The assistant is unavailable right now (no AI model configured on this "
                 "server). Your message was saved — everything else on the platform keeps "
                 "working, and your data is unchanged.")
        _add_message(session["id"], "assistant", reply, llm_model=None)
        return {"reply": reply, "llm_model": None, "available": False}

    profile = build_user_profile(agent_id)
    history = get_messages(session["id"], limit=MAX_HISTORY_MESSAGES + 1)[:-1]
    history = history[-MAX_HISTORY_MESSAGES:]
    transcript = "\n".join(f"{m['role'].upper()}: {m['content']}" for m in history)

    prompt = (
        f"USER LANGUAGE: {lang}\n\n"
        f"THIS USER'S FULL ACCOUNT (JSON):\n"
        f"{json.dumps(profile, ensure_ascii=False, default=str)[:12000]}\n\n"
        + (f"CONVERSATION SO FAR:\n{transcript}\n\n" if transcript else "")
        + f"USER: {user_message}\n\nReply as their assistant."
    )
    reply = generate_text(prompt, system=SYSTEM_PROMPT, max_tokens=800,
                          temperature=0.4, tier="decision")
    if not reply:
        reply = ("I couldn't reach the model just now — please try again. Nothing in your "
                 "account was changed.")
        _add_message(session["id"], "assistant", reply, llm_model=None)
        return {"reply": reply, "llm_model": None, "available": False}

    model = active_provider_model(tier="decision")
    _add_message(session["id"], "assistant", reply, llm_model=model)
    return {"reply": reply, "llm_model": model, "available": True}
