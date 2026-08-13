"""routes_billing.py — auto-renew billing (Stripe subscriptions).

Hosted Checkout (cards / Apple Pay / Google Pay) + Customer Portal for plan
switches, card updates and cancellation. Needs STRIPE_SECRET_KEY, and
STRIPE_WEBHOOK_SECRET for the webhook.

PayPal was removed on 2026-08-12 — it had never been configured (no plan ids,
sandbox host) and never carried a subscription, so nothing was stranded.

State rule: endpoints here never activate a plan. Activation, renewal, plan
changes and endings arrive via the two webhook endpoints and are applied by
billing_sync (idempotent per provider event id).

  POST /api/subscriptions/stripe/checkout    start Stripe Checkout  → {url}
  POST /api/subscriptions/stripe/portal      manage (portal)        → {url}
  POST /api/webhooks/stripe                  Stripe events (signed)
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from fastapi import FastAPI, Header, HTTPException, Request

import billing_sync
from database import get_db_connection
from routes_shared import RouteContext
from routes_subscriptions import (PlanOrderBody, _alert_new_subscription,
                                  _frontend_url, _load_plan, _require_user)

logger = logging.getLogger("routes_billing")

ALREADY_AUTORENEW = ("An auto-renewing subscription is already active — "
                     "manage or cancel it first")

# Service rules 2026-08-12: a card is collected at sign-up, the first 7 days
# are free, and the subscription then converts automatically. Junior only,
# once per account. Stripe owns the clock — trial_period_days on the Checkout
# Session — so there is no trial state of ours to keep in step.
TRIAL_PLAN_CODE = "junior"
TRIAL_DAYS = 7


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


def _handle_stripe_event(event: dict) -> None:
    etype = event.get("type", "")
    obj = (event.get("data") or {}).get("object") or {}
    if etype == "checkout.session.completed":
        meta = obj.get("metadata") or {}
        user_id = int(obj.get("client_reference_id") or meta.get("user_id") or 0)
        sub_id = obj.get("subscription") or ""
        plan_code = meta.get("plan_code") or ""
        if not (user_id and sub_id and plan_code):
            logger.warning("stripe checkout.session.completed missing fields: %s", obj)
            return
        billing_sync.upsert_autorenew_subscription(
            provider="stripe", user_id=user_id, plan_code=plan_code,
            external_id=sub_id)
        _alert_new_subscription(email=None, plan_code=plan_code, amount=None,
                                method="stripe", status_note="auto-activated",
                                reference=sub_id)
    elif etype == "invoice.paid":
        # Stripe API 2025-03-31.basil moved Invoice.subscription to
        # parent.subscription_details.subscription — accept both shapes so a
        # dashboard-default webhook version can't silently stop renewals.
        sub_id = (obj.get("subscription")
                  or ((obj.get("parent") or {}).get("subscription_details")
                      or {}).get("subscription")
                  or "")
        period_end = None
        lines = ((obj.get("lines") or {}).get("data") or [])
        end_ts = (lines[0].get("period") or {}).get("end") if lines else None
        if end_ts:
            period_end = datetime.fromtimestamp(int(end_ts), tz=timezone.utc)
        if sub_id:
            billing_sync.extend_subscription("stripe", sub_id, period_end)
    elif etype == "customer.subscription.updated":
        sub_id = obj.get("id") or ""
        items = ((obj.get("items") or {}).get("data") or [])
        price_id = ((items[0].get("price") or {}).get("id") or "") if items else ""
        plan_code = billing_sync.plan_for_stripe_price(price_id) if price_id else None
        period_end = None
        if obj.get("current_period_end"):
            period_end = datetime.fromtimestamp(int(obj["current_period_end"]),
                                                tz=timezone.utc)
        billing_sync.apply_subscription_update(
            "stripe", sub_id, plan_code=plan_code,
            cancel_at_period_end=bool(obj.get("cancel_at_period_end")),
            period_end=period_end)
    elif etype == "customer.subscription.deleted":
        if obj.get("id"):
            billing_sync.end_subscription("stripe", obj["id"])
    elif etype == "customer.subscription.trial_will_end":
        _send_trial_reminder(obj)
    # anything else: recorded in billing_events, deliberately ignored


def _send_trial_reminder(obj: dict) -> None:
    """Pre-charge notice before the free trial converts to a paid subscription.

    Stripe fires trial_will_end three days out, which on a 7-day trial lands on
    day 4 — so there is no scheduler of ours to run or to drift.

    Required, not courteous: California's Automatic Renewal Law expects the
    member to be told before the first charge WHEN it lands, HOW MUCH it is and
    HOW to stop it. Delivery failure RAISES so the caller answers 500 and Stripe
    redelivers — a duplicate notice is an annoyance, a missing one is a
    disclosure gap and the most common reason a first charge is disputed as
    fraud. An unknown subscription returns quietly instead: nothing to notify,
    so retrying forever would be pointless.
    """
    sub_id = obj.get("id") or ""
    if not sub_id:
        return
    sub = billing_sync.subscriber_for_external_id("stripe", sub_id)
    if not sub:
        logger.warning("trial_will_end for unknown subscription %s", sub_id)
        return
    trial_end = obj.get("trial_end")
    charge_on = ""
    if trial_end:
        charge_on = datetime.fromtimestamp(int(trial_end),
                                           tz=timezone.utc).strftime("%Y-%m-%d")
    import email_sender
    ok = email_sender.send_trial_reminder_email(
        to_email=sub["email"], lang=sub.get("lang") or "en",
        amount_usd=float(sub.get("price_usd") or 0.0), charge_on=charge_on)
    if not ok:
        raise RuntimeError(f"trial reminder delivery failed for {sub_id}")


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
        # The trial rides on subscription_data ALONGSIDE the metadata — the
        # activation webhook resolves the member from that metadata, so it has
        # to survive rather than be replaced.
        sub_data: dict = {"metadata": {"user_id": str(user["id"]),
                                       "plan_code": plan["code"]}}
        if (plan["code"] == TRIAL_PLAN_CODE
                and not billing_sync.has_prior_subscription(user["id"])):
            sub_data["trial_period_days"] = TRIAL_DAYS
        try:
            session = _stripe().checkout.Session.create(
                mode="subscription",
                customer=customer_id,
                client_reference_id=str(user["id"]),
                line_items=[{"price": price_id, "quantity": 1}],
                metadata={"user_id": str(user["id"]), "plan_code": plan["code"]},
                subscription_data=sub_data,
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

    @app.post('/api/webhooks/stripe')
    async def stripe_webhook(request: Request,
                             stripe_signature: str = Header(None)):
        secret = os.getenv("STRIPE_WEBHOOK_SECRET", "").strip()
        if not secret:
            raise HTTPException(status_code=503, detail="Stripe webhook not configured")
        payload = await request.body()
        import stripe
        try:
            event = stripe.Webhook.construct_event(payload, stripe_signature or "",
                                                   secret)
        except Exception:  # noqa: BLE001 — bad signature or malformed payload
            raise HTTPException(status_code=400, detail="Invalid signature")
        event = event.to_dict()
        event_id = str(event.get("id") or "")
        if not event_id:
            raise HTTPException(status_code=400, detail="Event has no id")
        if not billing_sync.record_billing_event(
                "stripe", event_id, str(event.get("type") or ""),
                payload.decode("utf-8", "replace")):
            return {"ok": True, "duplicate": True}
        try:
            _handle_stripe_event(event)
        except Exception as exc:  # noqa: BLE001
            try:
                billing_sync.delete_billing_event("stripe", event_id)
            except Exception:  # noqa: BLE001 — double fault: the event row may
                # remain recorded, so provider retries would no-op as duplicates.
                # Log loudly; the alert below still fires so an operator can
                # delete the billing_events row and replay the event.
                logger.exception("stripe webhook un-record ALSO failed for %s",
                                 event_id)
            logger.exception("stripe webhook processing failed: %s", exc)
            _alert_webhook_failure("stripe", event_id, exc)
            raise HTTPException(status_code=500, detail="Processing failed")
        return {"ok": True}
