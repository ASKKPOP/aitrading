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


def reconcile_orders_tick(limit: int = 200) -> dict[str, Any]:
    """One pass of the broker-order reconciler (worker task order_reconciler).

    A live/shadow order the broker answered with SUBMITTED has no final state
    on our side: it may later fill, part-fill, or be cancelled by the market,
    and the platform ledger — written at the requested size on submit — would
    silently diverge. This sweep asks the broker what actually happened and:

      - records the terminal status + broker-confirmed filled_qty on the
        broker_orders row (the requested `quantity` is left untouched), and
      - when the outcome materially differs from what the ledger assumed
        (cancelled/rejected after submit, or a fill size mismatch), journals a
        position_reconciliations drift row and alerts the owner (order_drift).

    Deliberately NOT done here: mutating positions/cash. Correcting money math
    post-hoc from a background sweep is how ledgers get corrupted twice; this
    surfaces the divergence loudly and leaves the correction to a human.
    """
    from database import get_db_connection
    from execution.base import ExecutionMode, OrderStatus
    from routes_shared import utc_now_iso_z

    out = {"checked": 0, "settled": 0, "still_open": 0, "drift": 0, "lookup_failed": 0}
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """SELECT id, agent_id, symbol, side, quantity, broker,
                      broker_order_id, execution_mode
               FROM broker_orders
               WHERE status IN ('submitted', 'partial_fill') AND broker != 'paper'
                     AND broker_order_id IS NOT NULL
               ORDER BY id LIMIT ?""",
            (limit,),
        )
        rows = [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()

    accounts: dict[int, Optional[dict[str, Any]]] = {}
    for row in rows:
        out["checked"] += 1
        agent_id = row["agent_id"]
        if agent_id not in accounts:
            accounts[agent_id] = active_broker_account(agent_id)
        account = accounts[agent_id]
        # The order remembers which venue it went to; the CURRENT account row
        # may have changed broker since — only reconcile against the same one.
        if not account or (account.get("broker") or "") != row["broker"]:
            out["lookup_failed"] += 1
            continue
        try:
            mode = ExecutionMode(row.get("execution_mode") or "shadow")
        except ValueError:
            mode = ExecutionMode.SHADOW
        # LIVE stays LIVE and SHADOW stays sandbox — same endpoint-pinning rule
        # as submission, or the lookup asks the wrong venue about the order.
        adapter = _broker_for(account, mode if mode in (ExecutionMode.LIVE,)
                              else ExecutionMode.SHADOW)
        # EVERYTHING that reads the broker's answer stays inside this try. A
        # malformed payload from ONE broker must never abort the sweep and
        # starve every later order in the batch of reconciliation.
        try:
            status = _run_coro(adapter.get_order_status(row["broker_order_id"],
                                                        symbol=row["symbol"]))
            if not status:
                out["lookup_failed"] += 1
                continue

            final = status.get("status")
            if not isinstance(final, OrderStatus):
                # Adapter contract violation — treat as "couldn't read it" and
                # leave the row for the next sweep rather than settling wrong.
                out["lookup_failed"] += 1
                _logger.warning("order %s: broker status not an OrderStatus (%r)",
                                row["id"], final)
                continue
            if final in (OrderStatus.SUBMITTED, OrderStatus.PENDING):
                out["still_open"] += 1
                continue

            filled_qty = _coerce_float(status.get("filled_qty"))
        except Exception:  # noqa: BLE001 — one bad lookup must not stop the sweep
            out["lookup_failed"] += 1
            _logger.exception("order status lookup failed for broker_order %s", row["id"])
            continue

        # A PARTIAL_FILL is not really terminal: keep it pollable so an eventual
        # full fill is still recorded. It is scanned back in via the query's
        # partial_fill clause, and drift dedup (per order id) prevents re-spam.
        still_working = final is OrderStatus.PARTIAL_FILL
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """UPDATE broker_orders
                   SET status = ?, filled_qty = ?, filled_at = ?
                   WHERE id = ? AND status IN ('submitted', 'partial_fill')""",
                (final.value, filled_qty,
                 utc_now_iso_z() if final is OrderStatus.FILLED else None,
                 row["id"]),
            )
            conn.commit()
        finally:
            conn.close()
        if still_working:
            out["still_open"] += 1
        else:
            out["settled"] += 1

        # Material divergence from what the ledger assumed at submit time?
        requested = float(row["quantity"] or 0)
        mismatch = (
            final in (OrderStatus.CANCELLED, OrderStatus.REJECTED)
            or final is OrderStatus.PARTIAL_FILL
            or (final is OrderStatus.FILLED and filled_qty is not None
                and abs(filled_qty - requested) > max(1e-9, requested * 0.001))
        )
        if mismatch and mode is ExecutionMode.LIVE:
            out["drift"] += 1
            _alert_order_drift(agent_id, row, final.value, filled_qty, requested)
    return out


def _coerce_float(value: Any) -> Optional[float]:
    """Broker payloads report quantities as float, str, or omit them; normalise
    to float or None so the ledger and drift math never choke on a string."""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _alert_order_drift(agent_id: int, row: dict[str, Any], final: str,
                       filled_qty: Optional[float], requested: float) -> None:
    """The broker's final answer disagrees with what the ledger assumed."""
    try:
        from alerts import send_alert
        # filled_qty can be None on a partial the broker didn't quantify — the
        # alert MUST still fire (this is the divergence-surfacing mechanism), so
        # never let string formatting of None swallow it.
        filled_txt = "an unknown amount" if filled_qty is None else f"{filled_qty:g}"
        if final in ("cancelled", "rejected"):
            body = (f"{row['symbol']}: your {row['side']} order was {final} by the "
                    f"broker AFTER submission — the platform recorded it at the "
                    f"requested size ({requested:g}). Review the position on your "
                    "broker and correct manually if needed.")
        else:
            body = (f"{row['symbol']}: broker confirmed {filled_txt} of the "
                    f"requested {requested:g} {row['side']} — the platform ledger "
                    "recorded the requested size. Review and correct manually.")
        send_alert(agent_id, "order_drift",
                   "Broker fill differs from platform record", body,
                   dedupe_key=f"order_drift:{row['id']}")
    except Exception:  # noqa: BLE001
        _logger.debug("order drift alert failed for broker_order %s", row.get("id"))


def _alert_session_down(agent_id: int, detail: str) -> None:
    """Alert that the IBKR gateway can no longer take orders.

    alerts._is_duplicate suppresses within a 1-HOUR window, so the day-scoped
    key means a gateway that stays dead re-alerts roughly hourly — a deliberate
    reminder cadence, not a single daily ping. (Do not read this as once-a-day.)
    """
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

    The worker has no running loop of its own. Decide up front whether one is
    running rather than catching RuntimeError from asyncio.run — a RuntimeError
    raised BY the coroutine itself would otherwise be mistaken for "no loop" and
    trigger a retry of an already-consumed coroutine, masking the real error.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        # No running loop (the normal worker case) — asyncio.run is correct and
        # any exception from the coroutine propagates unwrapped to the caller.
        return asyncio.run(coro)
    # A loop is already running on this thread; use a private one so we never
    # reuse a consumed coroutine or fight the outer loop.
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
