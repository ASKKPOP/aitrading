"""routes_billing.py — auto-renew billing rails (Stripe + PayPal subscriptions).

Stripe:   hosted Checkout (cards / Apple Pay / Google Pay) + Customer Portal
          for plan switches, card updates and cancellation. Needs
          STRIPE_SECRET_KEY (+ STRIPE_WEBHOOK_SECRET for the webhook).
PayPal:   Subscriptions API (v1/billing) — replaces the one-time Orders flow
          for NEW purchases; the legacy capture route in routes_subscriptions
          stays for in-flight orders. Needs PAYPAL_WEBHOOK_ID too.

State rule: endpoints here never activate a plan. Activation, renewal, plan
changes and endings arrive via the two webhook endpoints and are applied by
billing_sync (idempotent per provider event id).

  POST /api/subscriptions/stripe/checkout    start Stripe Checkout  → {url}
  POST /api/subscriptions/stripe/portal      manage (portal)        → {url}
  POST /api/subscriptions/paypal/subscribe   start PayPal approval  → {approve_url}
  POST /api/subscriptions/paypal/change-plan revise (next cycle)
  POST /api/subscriptions/paypal/cancel      stop renewing
  POST /api/webhooks/stripe                  Stripe events (signed)
  POST /api/webhooks/paypal                  PayPal events (verified)
"""
from __future__ import annotations

import logging
import os

from fastapi import FastAPI, Header, HTTPException

import billing_sync
from database import get_db_connection
from routes_shared import RouteContext
from routes_subscriptions import (PlanOrderBody, _frontend_url, _load_plan,
                                  _require_user)

logger = logging.getLogger("routes_billing")

ALREADY_AUTORENEW = ("An auto-renewing subscription is already active — "
                     "manage or cancel it first")


def _alert_webhook_failure(provider: str, event_id: str, exc: Exception) -> None:
    """Spec §4: processing failure → 500 (provider retries) + owner alert.
    Fail-soft — alerting must never mask the original failure."""
    try:
        from admin_alerts import notify_admins
        notify_admins("Billing webhook processing failed",
                      f"provider: {provider}\nevent: {event_id}\nerror: {exc}")
    except Exception:  # noqa: BLE001
        logger.warning("billing webhook failure alert failed", exc_info=True)


def _stripe():
    import stripe
    stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "").strip()
    return stripe


def _stripe_customer_id(user: dict) -> str:
    """Reuse the saved Stripe customer or create one (saved for next time)."""
    existing = (user.get("stripe_customer_id") or "").strip()
    if existing:
        return existing
    try:
        customer = _stripe().Customer.create(
            email=user.get("email"), metadata={"user_id": str(user["id"])})
    except Exception as exc:  # noqa: BLE001
        logger.error("Stripe customer create failed: %s", exc)
        raise HTTPException(status_code=502, detail="Card processor error")
    customer_id = customer["id"]
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE users SET stripe_customer_id = ? WHERE id = ?",
                    (customer_id, user["id"]))
        conn.commit()
    finally:
        conn.close()
    return customer_id


def register_billing_routes(app: FastAPI, ctx: RouteContext) -> None:

    @app.post('/api/subscriptions/stripe/checkout')
    async def stripe_checkout(body: PlanOrderBody, authorization: str = Header(None)):
        user = _require_user(authorization)
        if not billing_sync.stripe_configured():
            raise HTTPException(status_code=503, detail="Card payments are not configured")
        if billing_sync.active_autorenew(user["id"]):
            raise HTTPException(status_code=409, detail=ALREADY_AUTORENEW)
        conn = get_db_connection()
        try:
            plan = _load_plan(conn.cursor(), body.plan_code)
        finally:
            conn.close()
        price_id = (billing_sync.billing_ids_for_plan(plan["code"])
                    .get("stripe_price_id") or "")
        if not price_id:
            raise HTTPException(status_code=503,
                                detail="This plan is not configured for card payments")
        customer_id = _stripe_customer_id(user)
        try:
            session = _stripe().checkout.Session.create(
                mode="subscription",
                customer=customer_id,
                client_reference_id=str(user["id"]),
                line_items=[{"price": price_id, "quantity": 1}],
                metadata={"user_id": str(user["id"]), "plan_code": plan["code"]},
                subscription_data={"metadata": {"user_id": str(user["id"]),
                                                "plan_code": plan["code"]}},
                success_url=f"{_frontend_url()}/subscribe?stripe=success",
                cancel_url=f"{_frontend_url()}/subscribe?stripe=cancel",
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Stripe checkout session failed: %s", exc)
            raise HTTPException(status_code=502, detail="Card processor error")
        return {"url": session["url"]}

    @app.post('/api/subscriptions/stripe/portal')
    async def stripe_portal(authorization: str = Header(None)):
        user = _require_user(authorization)
        if not billing_sync.stripe_configured():
            raise HTTPException(status_code=503, detail="Card payments are not configured")
        customer_id = (user.get("stripe_customer_id") or "").strip()
        if not customer_id:
            raise HTTPException(status_code=404, detail="No card subscription on file")
        try:
            session = _stripe().billing_portal.Session.create(
                customer=customer_id, return_url=f"{_frontend_url()}/subscribe")
        except Exception as exc:  # noqa: BLE001
            logger.error("Stripe portal session failed: %s", exc)
            raise HTTPException(status_code=502, detail="Card processor error")
        return {"url": session["url"]}
