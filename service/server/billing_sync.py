"""billing_sync.py — auto-renew subscription state, written ONLY by webhooks.

Single owner of user_subscriptions writes for the two auto-renew rails
(method = 'stripe' | 'paypal'). Checkout endpoints never activate anything;
providers' webhooks land here. `expires_at` stays the one field entitlements
reads — each paid period pushes it to period_end + GRACE_DAYS so a slow
webhook or payment retry cannot flicker a member's access off.

Idempotency: record_billing_event() inserts into billing_events first; a
redelivered event returns False and the caller answers 200 without touching
state. On handler failure the caller delete_billing_event()s the row so the
provider's retry is processed, not swallowed as a duplicate.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

from database import get_db_connection

logger = logging.getLogger("billing_sync")

GRACE_DAYS = 3
DEFAULT_PERIOD_DAYS = 30


def stripe_configured() -> bool:
    return bool(os.getenv("STRIPE_SECRET_KEY", "").strip())


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def _expires(period_end: datetime | None) -> str:
    end = period_end or (_now() + timedelta(days=DEFAULT_PERIOD_DAYS))
    return _iso(end + timedelta(days=GRACE_DAYS))


def record_billing_event(provider: str, event_id: str, event_type: str,
                         payload: str) -> bool:
    """True = first delivery, proceed. False = duplicate, answer 200 and stop."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        try:
            cur.execute(
                "INSERT INTO billing_events (provider, event_id, type, payload, processed_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (provider, event_id, (event_type or "")[:80], (payload or "")[:20000],
                 _iso(_now())))
            conn.commit()
            return True
        except Exception as exc:  # noqa: BLE001
            conn.rollback()
            # Only a UNIQUE(provider, event_id) violation means "duplicate".
            # Any other failure must propagate so the webhook answers 500 and
            # the provider retries instead of silently dropping the event.
            if ("IntegrityError" not in type(exc).__name__
                    and "Duplicate" not in str(exc)):
                raise
            return False
    finally:
        conn.close()


def delete_billing_event(provider: str, event_id: str) -> None:
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM billing_events WHERE provider = ? AND event_id = ?",
                    (provider, event_id))
        conn.commit()
    finally:
        conn.close()


def upsert_autorenew_subscription(*, provider: str, user_id: int, plan_code: str,
                                  external_id: str,
                                  period_end: datetime | None = None) -> None:
    """Activate the member's auto-renew subscription (idempotent per external_id).

    One live subscription per member: any other active/pending rows are marked
    'superseded' (get_subscription_state only reads active|pending, so they
    simply drop out)."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id FROM user_subscriptions WHERE method = ? AND external_id = ?",
            (provider, external_id))
        row = cur.fetchone()
        if row:
            row_id = dict(row)["id"]
            cur.execute(
                "UPDATE user_subscriptions SET status = 'superseded' "
                "WHERE user_id = ? AND id != ? AND status IN ('active', 'pending')",
                (user_id, row_id))
            cur.execute(
                "UPDATE user_subscriptions SET status = 'active', plan_code = ?, "
                "expires_at = ?, auto_renew = 1, cancel_at_period_end = 0 WHERE id = ?",
                (plan_code, _expires(period_end), row_id))
        else:
            cur.execute(
                "UPDATE user_subscriptions SET status = 'superseded' "
                "WHERE user_id = ? AND status IN ('active', 'pending')",
                (user_id,))
            cur.execute(
                "INSERT INTO user_subscriptions (user_id, plan_code, status, method, "
                "reference, external_id, auto_renew, started_at, expires_at) "
                "VALUES (?, ?, 'active', ?, ?, ?, 1, ?, ?)",
                (user_id, plan_code, provider, external_id, external_id,
                 _iso(_now()), _expires(period_end)))
        conn.commit()
    finally:
        conn.close()
    logger.info("billing: activated %s sub %s user=%s plan=%s",
                provider, external_id, user_id, plan_code)


def extend_subscription(provider: str, external_id: str,
                        period_end: datetime | None = None) -> None:
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE user_subscriptions SET status = 'active', expires_at = ? "
            "WHERE method = ? AND external_id = ? AND status != 'superseded'",
            (_expires(period_end), provider, external_id))
        conn.commit()
    finally:
        conn.close()


def apply_subscription_update(provider: str, external_id: str, *,
                              plan_code: str | None = None,
                              cancel_at_period_end: bool | None = None,
                              period_end: datetime | None = None) -> None:
    sets, args = [], []
    if plan_code is not None:
        sets.append("plan_code = ?"); args.append(plan_code)
    if cancel_at_period_end is not None:
        sets.append("cancel_at_period_end = ?")
        args.append(1 if cancel_at_period_end else 0)
    if period_end is not None:
        sets.append("expires_at = ?"); args.append(_expires(period_end))
    if not sets:
        return
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            f"UPDATE user_subscriptions SET {', '.join(sets)} "
            "WHERE method = ? AND external_id = ?",
            (*args, provider, external_id))
        conn.commit()
    finally:
        conn.close()


def mark_cancelled(provider: str, external_id: str) -> None:
    """Member cancelled: stop renewing, keep access until expires_at."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE user_subscriptions SET auto_renew = 0, cancel_at_period_end = 1 "
            "WHERE method = ? AND external_id = ?",
            (provider, external_id))
        conn.commit()
    finally:
        conn.close()


def end_subscription(provider: str, external_id: str) -> None:
    """The subscription actually ended (deleted/expired event): close access."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE user_subscriptions SET status = 'expired', auto_renew = 0 "
            "WHERE method = ? AND external_id = ?",
            (provider, external_id))
        conn.commit()
    finally:
        conn.close()


def active_autorenew(user_id: int) -> dict | None:
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, plan_code, method, external_id, expires_at "
            "FROM user_subscriptions WHERE user_id = ? AND status = 'active' "
            "AND auto_renew = 1 ORDER BY id DESC LIMIT 1",
            (user_id,))
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


# LEGACY. The card-free trial that wrote method='trial' rows was replaced on
# 2026-08-12 by the Stripe-native trial (trial_period_days), so nothing creates
# these any more. The constant stays because the rows do: members onboarded
# during that week still hold one, and routes_subscriptions' manual-change guard
# must keep refusing them the proration path — they paid $0, so prorating
# against list price would sell them credit they never bought.
TRIAL_METHOD = "trial"


def has_prior_subscription(user_id: int) -> bool:
    """True if this member has ever had a subscription row, in any state.

    The free trial is once per account, so the guard deliberately counts
    'expired' and 'superseded' rows too — otherwise letting a subscription
    lapse would mint a fresh trial every time.
    """
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM user_subscriptions WHERE user_id = ? LIMIT 1",
                    (user_id,))
        return cur.fetchone() is not None
    finally:
        conn.close()


def subscriber_for_external_id(provider: str, external_id: str) -> dict | None:
    """Member, language and plan price behind a provider subscription id —
    what a billing notice needs to address itself correctly."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT s.user_id, s.plan_code, u.email, u.lang, p.price_usd "
            "FROM user_subscriptions s "
            "JOIN users u ON u.id = s.user_id "
            "LEFT JOIN subscription_plans p ON p.code = s.plan_code "
            "WHERE s.method = ? AND s.external_id = ? AND s.status != 'superseded' "
            "ORDER BY s.id DESC LIMIT 1",
            (provider, external_id))
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _plan_lookup(column: str, value: str) -> str | None:
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            f"SELECT code FROM subscription_plans WHERE {column} = ? AND active = 1",
            (value,))
        row = cur.fetchone()
        return dict(row)["code"] if row else None
    finally:
        conn.close()


def plan_for_stripe_price(price_id: str) -> str | None:
    return _plan_lookup("stripe_price_id", price_id)


def plan_for_paypal_plan(paypal_plan_id: str) -> str | None:
    return _plan_lookup("paypal_plan_id", paypal_plan_id)


def billing_ids_for_plan(plan_code: str) -> dict:
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT stripe_price_id, paypal_plan_id FROM subscription_plans "
            "WHERE code = ?", (plan_code,))
        row = cur.fetchone()
        return dict(row) if row else {"stripe_price_id": None, "paypal_plan_id": None}
    finally:
        conn.close()
