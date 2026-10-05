"""Plan 32 stage B — dedicated trend accounts.

The trend module (trend_module.py) trades one account of its own (the
user-less TREND_AGENT_ID). A *trend account* is a USER's account handed over
to the same rule: enrolled here, traded by nobody else. This file is the
enrolment record and the fence that keeps the account the module's alone;
the trading is still trend_module's.

Enrolment lives in platform_settings (`trend_module_accounts`), written from
the admin console one account at a time:
[{"agent_id": 71, "account_type": "shadow", "risk_usd": 25}].

- `simulator`: the platform ledger only.
- `shadow`: the ledger stays authoritative, and every fill is also sent to
  the account's connected broker as a sandbox / dry-run order
  (execution.gateway.submit_shadow), journalled for drift.
- `live` is refused. Nothing here can send a real order; that is Plan 32
  stage C and the owner's four steps, not a value to type in.

Dedicated, not shared (Plan 32 §0: the shared-account book was built and not
shipped — on a shared account the module does not own its rows). An account
is only enrolled CLEAN (no open position, no active run, no active fleet),
and once enrolled nothing but the module opens a position on it: the fleet
and runs are refused at start, and every other writer — manual order,
copy-trade fill, automation rule, resting order — at the ledger. Closing is
never fenced: nobody is ever locked into a position.

The fence reads the enrolment as STORED, whatever the module switch says: an
account stays dedicated while the module is paused, or pausing it would let
the desk onto an account that still holds the rule's positions.
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

ACCOUNTS_KEY = "trend_module_accounts"
ACCOUNT_TYPES = ("simulator", "shadow")
DEFAULT_RISK_USD = 25.0
# 1% of a $10k account a trade. The replay's worst run of losses is ~20
# trades' worth of risk; above this an account can lose a fifth of itself
# doing exactly what it was tested to do.
MAX_RISK_USD = 100.0
_MAX_AGENT_ID = 2 ** 31 - 1
_ACTIVE_RUNS = ("armed", "running", "paused", "stopping")
_ACTIVE_FLEETS = ("researching", "building", "active", "paused", "stopping")

FENCED = ("this is a dedicated trend account — only the trend rule opens "
          "positions on it")
NO_RUNS = ("this is a dedicated trend account — the trend rule trades it; "
           "runs and fleets cannot start on it")


class AccountError(ValueError):
    """An enrolment that cannot be accepted, with a message for the console."""


def _query(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    """One read on its own connection. Raises on any database failure — every
    caller here decides for itself which way to fail."""
    from database import get_db_connection
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(sql, params)
        return [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()


def _agent_user_id(agent_id: int) -> "int | None":
    """The user who owns this agent; None for a missing or user-less agent.
    Raises on a database failure."""
    rows = _query("SELECT user_id FROM agents WHERE id = ?", (agent_id,))
    if not rows or rows[0]["user_id"] is None:
        return None
    return int(rows[0]["user_id"])


def _agent_id(value: Any) -> int:
    # An id, exactly: `true` is not agent 1 and 6.9 is not agent 6.
    if isinstance(value, bool) or not (
            isinstance(value, int)
            or (isinstance(value, str) and value.strip().isdigit())):
        raise AccountError("agent_id must be a whole number")
    agent_id = int(value)
    if not 0 < agent_id <= _MAX_AGENT_ID:
        raise AccountError("agent_id is out of range")
    return agent_id


def normalize(entries: Any) -> list[dict[str, Any]]:
    """Validate a list of enrolments. Raises AccountError naming the first
    problem; never repairs a bad value into a different one."""
    if not isinstance(entries, list):
        raise AccountError("accounts must be a list")
    out: list[dict[str, Any]] = []
    seen: set[int] = set()
    for raw in entries:
        if not isinstance(raw, dict):
            raise AccountError("each account must be an object")
        agent_id = _agent_id(raw.get("agent_id"))
        if agent_id in seen:
            raise AccountError(f"agent {agent_id} is enrolled twice")
        seen.add(agent_id)
        account_type = str(raw.get("account_type") or "simulator").strip().lower()
        if account_type not in ACCOUNT_TYPES:
            raise AccountError(
                f"account_type '{account_type}' is not available for a trend "
                "account — 'simulator' or 'shadow' (real money is not "
                "switched on here)")
        risk_raw = raw.get("risk_usd", DEFAULT_RISK_USD)
        if isinstance(risk_raw, bool):
            raise AccountError("risk_usd must be a number")
        try:
            risk = float(risk_raw)
        except (TypeError, ValueError):
            raise AccountError("risk_usd must be a number") from None
        if not 0 < risk <= MAX_RISK_USD:      # also refuses NaN and inf
            raise AccountError(
                f"risk_usd must be above 0 and at most {MAX_RISK_USD:g}")
        # Fills up to this signals.id were on the account before the rule
        # was: they are not its record (trend_module.trend_stats).
        since = raw.get("since_signal_id", 0)
        if isinstance(since, bool) or not isinstance(since, int) or since < 0:
            raise AccountError("since_signal_id must be a whole number")
        out.append({"agent_id": agent_id, "account_type": account_type,
                    "risk_usd": risk, "since_signal_id": since})
    return out


def _for_update() -> str:
    """Row lock for a read-then-write inside one transaction. MySQL only:
    SQLite's BEGIN IMMEDIATE already admits one writer at a time."""
    from database import using_mysql
    return " FOR UPDATE" if using_mysql() else ""


def _read(cursor=None, lock: bool = False) -> list[dict[str, Any]]:
    """The stored enrolment. Raises on a database failure and on a stored
    value that no longer validates. `lock` (with the caller's write
    transaction) holds the row until that transaction ends."""
    sql = "SELECT setting_value FROM platform_settings WHERE setting_key = ?"
    if lock:
        sql += _for_update()
    if cursor is None:
        rows = _query(sql, (ACCOUNTS_KEY,))
    else:
        cursor.execute(sql, (ACCOUNTS_KEY,))
        rows = [dict(r) for r in cursor.fetchall()]
    raw = (rows[0]["setting_value"] or "").strip() if rows else ""
    return normalize(json.loads(raw)) if raw else []


def stored() -> tuple[list[dict[str, Any]], "str | None"]:
    """(enrolments, problem) exactly as stored, whatever the module switch
    says — what the admin console shows."""
    try:
        return _read(), None
    except (AccountError, ValueError) as exc:
        return [], f"stored enrolment is invalid: {exc}"
    except Exception as exc:  # noqa: BLE001
        return [], f"enrolment could not be read: {exc}"


def accounts() -> list[dict[str, Any]]:
    """The accounts the module TRADES: [] when the module is off, or when
    the enrolment is missing, unreadable or invalid. Never raises — an
    unreadable setting must not open positions."""
    try:
        import trend_module
        if not trend_module.module_enabled():
            return []
        entries, problem = stored()
        if problem:
            logger.warning("trend_accounts: %s — no account runs until it "
                           "is fixed", problem)
        return entries
    except Exception:  # noqa: BLE001
        logger.debug("trend_accounts: enrolment unreadable", exc_info=True)
        return []


def is_trend_account(agent_id: int, cursor=None, lock: bool = False) -> bool:
    """Is this agent enrolled? As STORED — the module switch does not lift
    the fence. Raises on a database failure, so a caller inside a write
    transaction fails with it instead of guessing. A stored value that does
    not validate (the API cannot write one) enrols nobody."""
    try:
        entries = _read(cursor, lock)
    except (AccountError, ValueError):
        return False
    return any(a["agent_id"] == int(agent_id) for a in entries)


def own_entry_fence(agent_id: int):
    """The check the MODULE's own entry carries into the ledger transaction
    (execute_paper_trade's `fence`): the account must still be enrolled when
    the fill is written. The module reads the enrolment once a cycle and an
    LLM call sits between that read and the order; an account removed in
    between would be left holding a position nobody exits. The read locks
    the enrolment row, and `remove` takes the same lock before it looks at
    the positions, so one of the two always sees the other."""
    def fence(cursor) -> "str | None":
        if is_trend_account(agent_id, cursor, lock=True):
            return None
        return "account is no longer a trend account"
    return fence


def entry_fence(cursor, agent_id: int, side: str,
                client_order_id: "str | None" = None) -> "str | None":
    """Why this order may not OPEN a position on the agent's account, or
    None. Reductions (sell / cover) are never fenced. The module's own
    orders are known by their order id.

    Sits on every simulated entry on the platform, so it fails OPEN: an
    enrolment that cannot be read fences nobody. A stray fill on one trend
    account is a smaller failure than no account being able to open."""
    if (side or "").strip().lower() not in ("buy", "short"):
        return None
    if (client_order_id or "").startswith(f"trend:{int(agent_id)}:"):
        return None
    try:
        return FENCED if is_trend_account(agent_id, cursor) else None
    except Exception:  # noqa: BLE001
        logger.warning("trend_accounts: enrolment unreadable — entry fence "
                       "skipped for agent %s", agent_id, exc_info=True)
        return None


def _open_positions(agent_id: int, cursor=None) -> list[str]:
    """Symbols the agent holds. With the caller's cursor: a locking read
    inside that transaction, so it sees every committed fill."""
    sql = "SELECT symbol FROM positions WHERE agent_id = ? AND quantity != 0"
    if cursor is None:
        rows = _query(sql, (agent_id,))
    else:
        cursor.execute(sql + _for_update(), (agent_id,))
        rows = [dict(r) for r in cursor.fetchall()]
    return sorted({str(r["symbol"]) for r in rows})


def _count(sql: str, params: tuple) -> int:
    return int(_query(sql, params)[0]["n"])


def _busy(agent_id: int, user_id: int) -> "str | None":
    """Why the account is not clean enough to hand to the rule, or None."""
    held = _open_positions(agent_id)
    if held:
        return (f"holds open positions ({', '.join(held[:6])}) — a trend "
                "account starts flat; the rule does not take over positions "
                "it did not open")
    marks = ",".join("?" for _ in _ACTIVE_RUNS)
    if _count("SELECT COUNT(*) AS n FROM trading_runs WHERE agent_id = ? "
              f"AND status IN ({marks})", (agent_id, *_ACTIVE_RUNS)):
        return "has an active run — stop it first"
    marks = ",".join("?" for _ in _ACTIVE_FLEETS)
    # One fleet per USER (fleet_planner): any of the user's agents counts.
    if _count("SELECT COUNT(*) AS n FROM fleets f JOIN agents a "
              "ON a.id = f.agent_id WHERE a.user_id = ? "
              f"AND f.status IN ({marks})", (user_id, *_ACTIVE_FLEETS)):
        return "has an active fleet — stop it first"
    # An auto-executing rule would keep asking for entries the fence
    # refuses, every interval, with an LLM call each time.
    if _count("SELECT COUNT(*) AS n FROM automation_configs WHERE agent_id = ? "
              "AND enabled = 1 AND auto_execute = 1", (agent_id,)):
        return "has an enabled auto-executing automation rule — disable it first"
    return None


def _transact(change) -> Any:
    """One read-modify-write of the enrolment in a single write transaction,
    the row locked from the read to the commit: two operations cannot lose
    each other's change. `change(cursor, entries)` returns (result,
    new_entries) or raises AccountError to abandon."""
    from database import begin_write_transaction, get_db_connection
    from platform_settings import _now_iso
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        begin_write_transaction(cursor)
        try:
            entries = _read(cursor, lock=True)
        except (AccountError, ValueError) as exc:
            raise AccountError(f"stored enrolment is invalid: {exc} — fix "
                               "that before changing it") from None
        result, entries, by = change(cursor, entries)
        value = json.dumps(sorted(normalize(entries),
                                  key=lambda a: a["agent_id"]))
        cursor.execute("SELECT setting_key FROM platform_settings "
                       "WHERE setting_key = ?", (ACCOUNTS_KEY,))
        if cursor.fetchone():
            cursor.execute(
                "UPDATE platform_settings SET setting_value = ?, updated_by = ?, "
                "updated_at = ? WHERE setting_key = ?",
                (value, by, _now_iso(), ACCOUNTS_KEY))
        else:
            cursor.execute(
                "INSERT INTO platform_settings (setting_key, setting_value, "
                "updated_by, updated_at) VALUES (?, ?, ?, ?)",
                (ACCOUNTS_KEY, value, by, _now_iso()))
        conn.commit()
        return result
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def enrol(agent_id: Any, account_type: Any = None, risk_usd: Any = None,
          by: "str | None" = None) -> dict[str, Any]:
    """Enrol one account, or change the type / risk of an enrolled one.

    A NEW enrolment needs an agent that belongs to a user and is clean (see
    `_busy`). On an enrolled account a value left out keeps what is stored —
    changing the risk does not quietly change the type — and either can
    change with positions open: risk applies to the next entry, and a shadow
    leg can start or stop at any time (the ledger is the record either way)."""
    agent_id = _agent_id(agent_id)
    current, problem = stored()
    if problem:
        raise AccountError(f"{problem} — fix that before changing it")
    known = next((a for a in current if a["agent_id"] == agent_id), None)

    def merged(base: "dict[str, Any] | None", since: int) -> dict[str, Any]:
        base = base or {}
        return normalize([{
            "agent_id": agent_id,
            "account_type": (account_type if account_type is not None
                             else base.get("account_type", "simulator")),
            "risk_usd": (risk_usd if risk_usd is not None
                         else base.get("risk_usd", DEFAULT_RISK_USD)),
            "since_signal_id": base.get("since_signal_id", since)}])[0]

    since = 0
    if known is None:
        merged(None, 0)                      # a bad value fails before any read
        user_id = _agent_user_id(agent_id)
        if user_id is None:
            raise AccountError(
                f"agent {agent_id} does not exist or belongs to no user — a "
                "trend account is a user's account")
        busy = _busy(agent_id, user_id)
        if busy:
            raise AccountError(f"agent {agent_id} {busy}")
        since = _count("SELECT COALESCE(MAX(id), 0) AS n FROM signals", ())

    def change(cursor, entries):
        base = next((a for a in entries if a["agent_id"] == agent_id), None)
        if base is None and known is not None:
            raise AccountError(
                f"agent {agent_id} was removed while this was being saved — "
                "enrol it again")
        entry = merged(base, since)
        rest = [a for a in entries if a["agent_id"] != agent_id]
        return entry, rest + [entry], by

    return _transact(change)


def remove(agent_id: Any, by: "str | None" = None) -> None:
    """Take one account off the rule. Refused while it holds a position:
    nothing would be left to exit it, and the desk would be let onto an
    account that is not flat. The position check runs inside the same
    transaction that holds the enrolment row (see `own_entry_fence`)."""
    agent_id = _agent_id(agent_id)

    def change(cursor, entries):
        if not any(a["agent_id"] == agent_id for a in entries):
            raise AccountError(f"agent {agent_id} is not a trend account")
        held = _open_positions(agent_id, cursor)
        if held:
            raise AccountError(
                f"agent {agent_id} still holds {', '.join(held[:6])} — close "
                "those positions (or wait for the rule to exit them) before "
                "removing the account")
        return None, [a for a in entries if a["agent_id"] != agent_id], by

    _transact(change)
