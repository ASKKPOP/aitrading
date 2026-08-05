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

import json
import logging
import os
from datetime import datetime, timezone

import requests
from fastapi import FastAPI, Header, HTTPException, Request

import billing_sync
from database import get_db_connection
from routes_shared import RouteContext
from routes_subscriptions import (PlanOrderBody, _alert_new_subscription,
                                  _frontend_url, _load_plan, _paypal_base,
                                  _paypal_configured, _paypal_token,
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
        sub_id = obj.get("subscription") or ""
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
    # anything else: recorded in billing_events, deliberately ignored


def _parse_paypal_time(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:  # noqa: BLE001
        return None


def _handle_paypal_event(event: dict) -> None:
    etype = event.get("event_type", "")
    res = event.get("resource") or {}
    if etype == "BILLING.SUBSCRIPTION.ACTIVATED":
        sub_id = res.get("id") or ""
        user_id = int(res.get("custom_id") or 0)
        plan_code = billing_sync.plan_for_paypal_plan(res.get("plan_id") or "")
        period_end = _parse_paypal_time(
            ((res.get("billing_info") or {}).get("next_billing_time")) or "")
        if not (sub_id and user_id and plan_code):
            logger.warning("paypal ACTIVATED missing fields: %s", res)
            return
        billing_sync.upsert_autorenew_subscription(
            provider="paypal", user_id=user_id, plan_code=plan_code,
            external_id=sub_id, period_end=period_end)
        _alert_new_subscription(email=None, plan_code=plan_code, amount=None,
                                method="paypal", status_note="auto-activated",
                                reference=sub_id)
    elif etype == "PAYMENT.SALE.COMPLETED":
        sub_id = res.get("billing_agreement_id") or ""
        if sub_id:
            billing_sync.extend_subscription("paypal", sub_id)
    elif etype == "BILLING.SUBSCRIPTION.UPDATED":
        sub_id = res.get("id") or ""
        plan_code = billing_sync.plan_for_paypal_plan(res.get("plan_id") or "")
        if sub_id and plan_code:
            billing_sync.apply_subscription_update("paypal", sub_id,
                                                   plan_code=plan_code)
    elif etype in ("BILLING.SUBSCRIPTION.CANCELLED", "BILLING.SUBSCRIPTION.SUSPENDED"):
        if res.get("id"):
            billing_sync.mark_cancelled("paypal", res["id"])
    elif etype == "BILLING.SUBSCRIPTION.EXPIRED":
        if res.get("id"):
            billing_sync.end_subscription("paypal", res["id"])
    # anything else: recorded, ignored


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

    @app.post('/api/subscriptions/paypal/subscribe')
    async def paypal_subscribe(body: PlanOrderBody, authorization: str = Header(None)):
        user = _require_user(authorization)
        if not _paypal_configured():
            raise HTTPException(status_code=503, detail="PayPal is not configured")
        if billing_sync.active_autorenew(user["id"]):
            raise HTTPException(status_code=409, detail=ALREADY_AUTORENEW)
        conn = get_db_connection()
        try:
            plan = _load_plan(conn.cursor(), body.plan_code)
        finally:
            conn.close()
        paypal_plan_id = (billing_sync.billing_ids_for_plan(plan["code"])
                          .get("paypal_plan_id") or "")
        if not paypal_plan_id:
            raise HTTPException(status_code=503,
                                detail="This plan is not configured for PayPal")
        access = _paypal_token()
        resp = requests.post(
            f"{_paypal_base()}/v1/billing/subscriptions",
            headers={"Authorization": f"Bearer {access}"},
            json={
                "plan_id": paypal_plan_id,
                "custom_id": str(user["id"]),
                "application_context": {
                    "return_url": f"{_frontend_url()}/subscribe?paypal=sub-return",
                    "cancel_url": f"{_frontend_url()}/subscribe?paypal=cancel",
                    "user_action": "SUBSCRIBE_NOW",
                },
            },
            timeout=20,
        )
        if resp.status_code not in (200, 201):
            logger.error("PayPal subscribe failed: %s %s", resp.status_code,
                         resp.text[:300])
            raise HTTPException(status_code=502, detail="PayPal subscription failed")
        sub = resp.json()
        approve_url = next((link["href"] for link in sub.get("links", [])
                            if link.get("rel") == "approve"), None)
        if not approve_url:
            raise HTTPException(status_code=502, detail="PayPal returned no approval link")
        conn = get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO user_subscriptions (user_id, plan_code, status, method, "
                "reference, external_id, auto_renew, amount_usd) "
                "VALUES (?, ?, 'pending', 'paypal', ?, ?, 1, ?)",
                (user["id"], plan["code"], sub["id"], sub["id"], plan["price_usd"]))
            conn.commit()
        finally:
            conn.close()
        return {"subscription_id": sub["id"], "approve_url": approve_url}

    @app.post('/api/subscriptions/paypal/change-plan')
    async def paypal_change_plan(body: PlanOrderBody, authorization: str = Header(None)):
        user = _require_user(authorization)
        current = billing_sync.active_autorenew(user["id"])
        if not current or current["method"] != "paypal":
            raise HTTPException(status_code=404, detail="No active PayPal subscription")
        conn = get_db_connection()
        try:
            plan = _load_plan(conn.cursor(), body.plan_code)
        finally:
            conn.close()
        paypal_plan_id = (billing_sync.billing_ids_for_plan(plan["code"])
                          .get("paypal_plan_id") or "")
        if not paypal_plan_id:
            raise HTTPException(status_code=503,
                                detail="This plan is not configured for PayPal")
        access = _paypal_token()
        resp = requests.post(
            f"{_paypal_base()}/v1/billing/subscriptions/{current['external_id']}/revise",
            headers={"Authorization": f"Bearer {access}"},
            json={"plan_id": paypal_plan_id},
            timeout=20,
        )
        if resp.status_code not in (200, 204):
            logger.error("PayPal revise failed: %s %s", resp.status_code, resp.text[:300])
            raise HTTPException(status_code=502, detail="PayPal plan change failed")
        # Plan actually flips on the BILLING.SUBSCRIPTION.UPDATED webhook.
        links = (resp.json().get("links", []) if resp.status_code == 200 else [])
        approve_url = next((link["href"] for link in links
                            if link.get("rel") == "approve"), None)
        return {"ok": True, "approve_url": approve_url}

    @app.post('/api/subscriptions/paypal/cancel')
    async def paypal_cancel(authorization: str = Header(None)):
        user = _require_user(authorization)
        current = billing_sync.active_autorenew(user["id"])
        if not current or current["method"] != "paypal":
            raise HTTPException(status_code=404, detail="No active PayPal subscription")
        access = _paypal_token()
        resp = requests.post(
            f"{_paypal_base()}/v1/billing/subscriptions/{current['external_id']}/cancel",
            headers={"Authorization": f"Bearer {access}"},
            json={"reason": "Member cancelled from the subscribe page"},
            timeout=20,
        )
        if resp.status_code not in (200, 204):
            logger.error("PayPal cancel failed: %s %s", resp.status_code, resp.text[:300])
            raise HTTPException(status_code=502, detail="PayPal cancel failed")
        billing_sync.mark_cancelled("paypal", current["external_id"])
        return {"ok": True}

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

    @app.post('/api/webhooks/paypal')
    async def paypal_webhook(request: Request):
        webhook_id = os.getenv("PAYPAL_WEBHOOK_ID", "").strip()
        if not (_paypal_configured() and webhook_id):
            raise HTTPException(status_code=503, detail="PayPal webhook not configured")
        event = await request.json()
        headers = request.headers
        access = _paypal_token()
        verify = requests.post(
            f"{_paypal_base()}/v1/notifications/verify-webhook-signature",
            headers={"Authorization": f"Bearer {access}"},
            json={
                "auth_algo": headers.get("paypal-auth-algo", ""),
                "cert_url": headers.get("paypal-cert-url", ""),
                "transmission_id": headers.get("paypal-transmission-id", ""),
                "transmission_sig": headers.get("paypal-transmission-sig", ""),
                "transmission_time": headers.get("paypal-transmission-time", ""),
                "webhook_id": webhook_id,
                "webhook_event": event,
            },
            timeout=20,
        )
        if (verify.status_code != 200
                or verify.json().get("verification_status") != "SUCCESS"):
            raise HTTPException(status_code=400, detail="Invalid signature")
        event_id = str(event.get("id") or "")
        if not event_id:
            raise HTTPException(status_code=400, detail="Event has no id")
        if not billing_sync.record_billing_event(
                "paypal", event_id, str(event.get("event_type") or ""),
                json.dumps(event)):
            return {"ok": True, "duplicate": True}
        try:
            _handle_paypal_event(event)
        except Exception as exc:  # noqa: BLE001
            try:
                billing_sync.delete_billing_event("paypal", event_id)
            except Exception:  # noqa: BLE001 — double fault: the event row may
                # remain recorded, so provider retries would no-op as duplicates.
                # Log loudly; the alert below still fires so an operator can
                # delete the billing_events row and replay the event.
                logger.exception("paypal webhook un-record ALSO failed for %s",
                                 event_id)
            logger.exception("paypal webhook processing failed: %s", exc)
            _alert_webhook_failure("paypal", event_id, exc)
            raise HTTPException(status_code=500, detail="Processing failed")
        return {"ok": True}
