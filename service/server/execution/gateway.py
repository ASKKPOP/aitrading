"""
execution/gateway.py — the bridge between a rule's account_type and the
ExecutionRouter, plus the "is a real gateway actually usable?" check.

The rule's account_type is the ONLY switch that decides where a fill lands:

    simulator — internal ledger only. Never contacts a broker.
    shadow    — internal ledger is authoritative (i.e. run by simulation). If
                the agent has a broker account configured, the same order is
                ALSO sent to that broker's sandbox (Alpaca paper / Binance
                testnet) and the fill drift is journalled. No real money.
    live      — the real order goes to the user's configured trading gateway.
                Requires a usable gateway; otherwise the trade is refused with
                a message telling the user to configure one.

Nothing here silently downgrades live to simulation. A user who selects live
and has no gateway gets a refusal, never a fake fill that looks real.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from execution.base import ExecutionMode, Order, OrderStatus

_logger = logging.getLogger(__name__)

SIMULATOR = "simulator"
SHADOW = ExecutionMode.SHADOW.value
LIVE = ExecutionMode.LIVE.value

ACCOUNT_TYPES = (SIMULATOR, SHADOW, LIVE)

# Refusal shown when the user picked live but there is nothing to route to.
NOT_CONFIGURED = (
    "live trading selected but no trading gateway is configured — "
    "connect a broker account with API credentials before enabling live"
)
NOT_CONFIGURED_NO_CREDS = (
    "live trading selected but the connected gateway has no usable API "
    "credentials — reconnect the broker account"
)
NOT_ACCEPTED_TCS = (
    "live trading selected but the live-trading terms have not been accepted "
    "for this broker — accept them on the Accounts page"
)


def normalize_account_type(value: Optional[str]) -> str:
    """Map stored values onto the three supported modes.

    'real' is the pre-gateway spelling of live and still exists in rows created
    before the gateway landed; treat it as live so those rules behave the way
    their owner asked rather than silently simulating.
    """
    v = (value or SIMULATOR).strip().lower()
    if v == "real":
        return LIVE
    return v if v in ACCOUNT_TYPES else SIMULATOR


def active_broker_account(agent_id: int) -> Optional[dict[str, Any]]:
    """The agent's active broker_accounts row, or None."""
    from execution.router import _get_active_broker_account
    return _get_active_broker_account(agent_id)


def _has_usable_credentials(account: dict[str, Any]) -> bool:
    """True when credentials_enc is present AND decrypts to what the broker needs.

    Decryption is attempted because an EXECUTION_ENCRYPTION_KEY rotation (or a
    dev server's ephemeral key) leaves rows that exist but can never be read.
    Routing a live order at one of those means a rejected order at best.

    What "usable" means is broker-specific: Alpaca and Binance need a key and
    secret, while IBKR's Client Portal API has neither — its gateway session is
    the credential, so it needs a gateway URL and an account id instead.
    """
    blob = account.get("credentials_enc") or ""
    if not blob:
        return False
    try:
        from execution.crypto import decrypt_credentials
        creds = decrypt_credentials(blob)
    except Exception:  # noqa: BLE001 — any failure means "unusable"
        return False
    if (account.get("broker") or "").strip().lower() == "ibkr":
        return bool(creds.get("gateway_url") and creds.get("account_id"))
    return bool(creds.get("key") and creds.get("secret"))


def _has_accepted_live_tcs(agent_id: int, broker: str) -> bool:
    """True when the agent has an immutable live-trading opt-in for *broker*."""
    if not broker:
        return False
    from database import get_db_connection
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id FROM broker_live_optins WHERE agent_id = ? AND broker = ?",
            (agent_id, broker),
        )
        return cursor.fetchone() is not None
    finally:
        conn.close()


def live_refusal_reason(agent_id: int, account_type: Optional[str]) -> Optional[str]:
    """Why a live rule cannot run, or None when it may proceed.

    Only live is gated. simulator and shadow always have somewhere to land.
    """
    if normalize_account_type(account_type) != LIVE:
        return None
    account = active_broker_account(agent_id)
    if not account:
        return NOT_CONFIGURED
    if not _has_usable_credentials(account):
        return NOT_CONFIGURED_NO_CREDS
    # The T&Cs record is the user's explicit "I understand this is real money"
    # step. routes_execution only checks it when switching the ACCOUNT's mode,
    # so routing live off the rule's account_type would otherwise bypass the
    # one place consent is recorded.
    if not _has_accepted_live_tcs(agent_id, account.get("broker") or ""):
        return NOT_ACCEPTED_TCS
    return None


def gateway_health(agent_id: int) -> dict[str, Any]:
    """Is this agent's configured gateway actually usable right now?

    Credentials being on file is not the same as the venue being reachable.
    IBKR in particular holds a session that expires, so a live rule can stop
    filling with nothing on our side having changed. Brokers without a session
    concept report `checked: False` — there is nothing to probe short of
    sending an order, which we will not do to run a health check.
    """
    out: dict[str, Any] = {
        "configured": False, "broker": None, "checked": False,
        "ok": None, "detail": "",
    }
    account = active_broker_account(agent_id)
    if not account:
        out["detail"] = "no trading gateway connected"
        return out

    broker = (account.get("broker") or "").strip().lower()
    out.update({"configured": True, "broker": broker})
    if not _has_usable_credentials(account):
        out["detail"] = "stored credentials are missing or cannot be decrypted"
        out["checked"] = True
        out["ok"] = False
        return out

    if broker != "ibkr":
        out["detail"] = "broker has no session to check; credentials are on file"
        return out

    try:
        from execution.base import ExecutionMode
        adapter = _broker_for(account, ExecutionMode(account.get("execution_mode") or "shadow"))
        status = _run_coro(adapter.session_status())
    except Exception as exc:  # noqa: BLE001 — a health probe must not raise
        out["checked"] = True
        out["ok"] = False
        out["detail"] = f"health check failed: {exc}"
        return out

    out["checked"] = True
    out["ok"] = bool(status.get("ok"))
    out["detail"] = status.get("detail") or ("session authenticated" if status.get("ok") else "")
    out["paper_account"] = status.get("paper")
    out["account_id"] = status.get("account_id")
    return out


def keepalive_tick() -> dict[str, Any]:
    """One pass of the IBKR session keepalive (worker task gateway_keepalive).

    CPAPI drops an idle session after a few minutes, so a live IBKR rule on an
    hourly interval would find a dead gateway at every tick without this. For
    each ACTIVE ibkr account: tickle → check → (if lapsed) reauthenticate →
    re-check → alert the owner if still dead. Alerting is once per day per
    agent — a session that stays dead all day is one problem, not 24.

    Only IBKR is touched; key/secret brokers have no session to keep alive.
    Returns counters for the worker log line.
    """
    from database import get_db_connection
    from execution.base import ExecutionMode

    out = {"accounts": 0, "alive": 0, "revived": 0, "dead": 0}
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """SELECT * FROM broker_accounts
               WHERE broker = 'ibkr' AND is_active = 1"""
        )
        rows = [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()

    for account in rows:
        out["accounts"] += 1
        if not _has_usable_credentials(account):
            continue
        try:
            mode = ExecutionMode(account.get("execution_mode") or "shadow")
        except ValueError:
            mode = ExecutionMode.SHADOW
        adapter = _broker_for(account, mode)
        try:
            _run_coro(adapter.tickle())
            status = _run_coro(adapter.session_status())
            if not status.get("ok") and status.get("reachable"):
                # Lapsed but the gateway still holds cookies — try a refresh.
                if _run_coro(adapter.reauthenticate()):
                    status = _run_coro(adapter.session_status())
                    if status.get("ok"):
                        out["revived"] += 1
            if status.get("ok"):
                out["alive"] += 1
                continue
            out["dead"] += 1
            _alert_session_down(account["agent_id"], status.get("detail") or "gateway session down")
        except Exception:  # noqa: BLE001 — one bad account must not stop the sweep
            out["dead"] += 1
            _logger.exception("keepalive failed for agent %s", account.get("agent_id"))
    return out


def _alert_session_down(agent_id: int, detail: str) -> None:
    """Once-per-day alert that the IBKR gateway can no longer take orders."""
    try:
        from datetime import datetime, timezone
        from alerts import send_alert
        day = datetime.now(timezone.utc).strftime("%Y%m%d")
        send_alert(agent_id, "gateway_down",
                   "Your IBKR gateway session is down",
                   f"{detail} — live and shadow IBKR orders will not fill until "
                   "you log in to the Client Portal Gateway again.",
                   dedupe_key=f"gateway_session:{agent_id}:{day}")
    except Exception:  # noqa: BLE001
        _logger.debug("session-down alert failed for agent %s", agent_id)


def _run_coro(coro):
    """Run an async broker call from the synchronous automation worker.

    The worker has no running loop of its own, so asyncio.run is correct here.
    If some caller ever does have one, fall back to a private loop rather than
    raising — a broker round-trip must never take down a rule evaluation.
    """
    try:
        return asyncio.run(coro)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()


def _broker_for(account: dict[str, Any], mode: ExecutionMode):
    """Build the broker adapter for *mode*, ignoring the account row's own
    execution_mode.

    This matters more than it looks. router._build_real_broker picks the
    sandbox-vs-live endpoint from account["execution_mode"], so an account the
    user once flipped to live would send a REAL order even when the rule asked
    for shadow. The rule's account_type is the switch, so pin the endpoint to
    the mode we actually intend and never trust the stored row for this.
    """
    from execution.router import _build_real_broker
    return _build_real_broker({**account, "execution_mode": mode.value})


def _build_order(agent_id: int, symbol: str, market: str, side: str,
                 quantity: float, price: float, mode: ExecutionMode,
                 broker_name: str, signal_id: Optional[int] = None) -> Order:
    from routes_shared import utc_now_iso_z
    return Order(
        agent_id=agent_id, symbol=symbol, market=market, side=side,
        quantity=quantity, price=price, execution_mode=mode,
        broker=broker_name, signal_id=signal_id, created_at=utc_now_iso_z(),
    )


def submit_live(agent_id: int, symbol: str, market: str, side: str,
                quantity: float, price: float) -> Order:
    """Send a REAL order to the user's configured gateway and return it.

    The caller must only write the platform ledger when the returned order
    reached the broker (FILLED or SUBMITTED) — the broker is authoritative in
    live mode, so a rejection must not produce a platform position.
    """
    from execution.router import _persist_order

    account = active_broker_account(agent_id) or {}
    broker = _broker_for(account, ExecutionMode.LIVE)
    order = _build_order(agent_id, symbol, market, side, quantity, price,
                         ExecutionMode.LIVE, broker.broker_name)
    try:
        order = _run_coro(broker.submit_order(order))
    except Exception as exc:  # noqa: BLE001 — infrastructure failure
        order.status = OrderStatus.REJECTED
        order.error_message = f"gateway error: {exc}"
        _logger.exception("[live] gateway error for agent %s", agent_id)
    try:
        order.db_id = _persist_order(order)
    except Exception:  # noqa: BLE001 — journalling must not lose the fill
        _logger.exception("[live] could not persist broker order for agent %s", agent_id)
    return order


def submit_shadow(agent_id: int, symbol: str, market: str, side: str,
                  quantity: float, price: float, ledger_quantity: float,
                  signal_id: Optional[int] = None) -> Optional[Order]:
    """Mirror an already-simulated fill into the broker's SANDBOX.

    Called after the platform ledger has been written, which stays
    authoritative. Returns None when the agent has no gateway to compare
    against — shadow without a broker is simply simulation, not an error.
    Never raises: a broker problem must not undo a completed simulated trade.
    """
    from execution.router import _persist_order, _record_reconciliation

    account = active_broker_account(agent_id)
    if not account or not _has_usable_credentials(account):
        return None

    # SHADOW pins the broker to its sandbox even if the stored account row says
    # live — "run by simulation" must never reach a real venue.
    broker = _broker_for(account, ExecutionMode.SHADOW)
    order = _build_order(agent_id, symbol, market, side, quantity, price,
                         ExecutionMode.SHADOW, broker.broker_name, signal_id)
    error_msg = None
    try:
        order = _run_coro(broker.submit_order(order))
    except Exception as exc:  # noqa: BLE001
        error_msg = str(exc)
        order.status = OrderStatus.REJECTED
        order.error_message = error_msg
        _logger.exception("[shadow] broker error for agent %s", agent_id)

    try:
        order.db_id = _persist_order(order)
        # The reconciler compares broker fill against the ledger quantity; it
        # reads .quantity off the "paper" side, so hand it the ledger figure.
        ledger_side = _build_order(agent_id, symbol, market, side,
                                   ledger_quantity, price,
                                   ExecutionMode.SHADOW, "paper", signal_id)
        ledger_side.db_id = signal_id
        _record_reconciliation(agent_id, broker.broker_name, ledger_side,
                               order, error_message=error_msg)
    except Exception:  # noqa: BLE001
        _logger.exception("[shadow] reconciliation failed for agent %s", agent_id)
    return order
