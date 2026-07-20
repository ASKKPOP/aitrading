"""
routes_subscriptions.py — paid membership for human users.

Sooppiy is subscription-gated: a user signs in, and without an active
subscription the frontend routes them to the /subscribe page. Plans are
seeded in subscription_plans (junior $60 / pro $250 / professional $500 /
enterprise = contact us). Three payment paths:

  * USDT     — THE DEFAULT. The user sends to the published address on the
               configured network and submits the transaction hash; the
               subscription sits in 'pending' until an admin verifies the
               transfer on-chain and approves it in the manager console.
               The address and network are REGISTERED IN THE CONSOLE
               (platform_settings), not .env, so they can be rotated without
               a deploy; USDT_ADDRESS/USDT_NETWORK survive as fallbacks. No
               funds move through this service and no keys are held here.
  * Bank     — user submits a transfer reference; same pending → approve path.
  * PayPal   — Orders API v2 redirect flow. Server creates the order and
               returns approve_url; PayPal redirects back to the frontend,
               which calls capture. Subscription activates instantly.
               Needs PAYPAL_CLIENT_ID + PAYPAL_CLIENT_SECRET in .env
               (PAYPAL_API_BASE defaults to the sandbox host).
               HIDDEN from the Subscribe page unless PAYPAL_UI_ENABLED=true —
               the routes stay live so existing orders and captures still work.

  GET  /api/subscriptions/plans               plans + payment availability
  GET  /api/subscriptions/me                  my subscription state
  POST /api/subscriptions/paypal/create-order start PayPal checkout
  POST /api/subscriptions/paypal/capture      finish PayPal checkout
  POST /api/subscriptions/usdt                submit a USDT payment (tx hash)
  POST /api/subscriptions/bank-transfer       submit a bank-transfer claim
  POST /api/subscriptions/contract            enterprise contact request

Subscription rows: status pending → active (30 days) → expired; admins can
reject or extend. Lazy expiry: reads mark stale 'active' rows 'expired'.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import requests
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from database import get_db_connection
from routes_shared import RouteContext
from services import _get_user_by_token
from utils import _extract_token

logger = logging.getLogger("routes_subscriptions")

SUBSCRIPTION_DAYS = 30


def _paypal_base() -> str:
    return os.getenv("PAYPAL_API_BASE", "https://api-m.sandbox.paypal.com").rstrip("/")


def _paypal_configured() -> bool:
    return bool(os.getenv("PAYPAL_CLIENT_ID") and os.getenv("PAYPAL_CLIENT_SECRET"))


def _paypal_ui_enabled() -> bool:
    """PayPal is hidden from the Subscribe page by default — USDT is the
    advertised rail. The ROUTES stay live regardless, so in-flight orders,
    captures and past PayPal subscriptions keep working; flipping this env
    var back to true re-exposes the button without a code change."""
    return os.getenv("PAYPAL_UI_ENABLED", "false").strip().lower() in ("1", "true", "yes")


def _usdt_address() -> str:
    """Registered in the manager console (platform_settings), NOT in .env — an
    address that needs a deploy to rotate is an address nobody rotates. The
    env var remains a fallback so a box configured before this existed keeps
    serving until an admin saves a value."""
    from platform_settings import get_setting
    return get_setting("usdt_address")


def _usdt_network() -> str:
    from platform_settings import get_setting
    return get_setting("usdt_network")


def _frontend_url() -> str:
    return os.getenv("SOOPPIY_FRONTEND_URL", "http://localhost:3000").rstrip("/")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def _paypal_token() -> str:
    resp = requests.post(
        f"{_paypal_base()}/v1/oauth2/token",
        auth=(os.getenv("PAYPAL_CLIENT_ID", ""), os.getenv("PAYPAL_CLIENT_SECRET", "")),
        data={"grant_type": "client_credentials"},
        timeout=20,
    )
    if resp.status_code != 200:
        logger.error("PayPal token request failed: %s %s", resp.status_code, resp.text[:300])
        raise HTTPException(status_code=502, detail="PayPal authentication failed")
    return resp.json()["access_token"]


def _require_user(authorization: Optional[str]) -> dict[str, Any]:
    token = _extract_token(authorization)
    user = _get_user_by_token(token) if token else None
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user


def _load_plan(cursor, plan_code: str) -> dict[str, Any]:
    cursor.execute(
        "SELECT code, name, price_usd, contact_only FROM subscription_plans WHERE code = ? AND active = 1",
        (plan_code,),
    )
    plan = cursor.fetchone()
    if not plan:
        raise HTTPException(status_code=404, detail="Unknown plan")
    if plan["contact_only"]:
        raise HTTPException(status_code=400, detail="Enterprise plans use the contract form")
    return dict(plan)


def get_subscription_state(cursor, user_id: int) -> dict[str, Any]:
    """Lazy-expire stale rows, then report the user's subscription state."""
    now_iso = _iso(_now())
    cursor.execute(
        "UPDATE user_subscriptions SET status = 'expired' "
        "WHERE user_id = ? AND status = 'active' AND expires_at < ?",
        (user_id, now_iso),
    )
    cursor.execute(
        """
        SELECT id, plan_code, status, method, started_at, expires_at, created_at
        FROM user_subscriptions
        WHERE user_id = ? AND status IN ('active', 'pending')
        ORDER BY CASE status WHEN 'active' THEN 0 ELSE 1 END, id DESC
        LIMIT 1
        """,
        (user_id,),
    )
    row = cursor.fetchone()
    if not row:
        return {"status": "none", "subscription": None}
    return {"status": row["status"], "subscription": dict(row)}


class PlanOrderBody(BaseModel):
    plan_code: str


class PaypalCaptureBody(BaseModel):
    order_id: str


class BankTransferBody(BaseModel):
    plan_code: str
    reference: str


class UsdtPaymentBody(BaseModel):
    plan_code: str
    tx_hash: str


class ContractBody(BaseModel):
    name: str
    email: str
    company: str = ""
    phone: str = ""
    message: str = ""


def register_subscription_routes(app: FastAPI, ctx: RouteContext) -> None:

    @app.get('/api/subscriptions/plans')
    async def subscription_plans():
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT code, name, price_usd, contact_only FROM subscription_plans "
                "WHERE active = 1 ORDER BY sort_order")
            plans = [dict(r) for r in cursor.fetchall()]
        finally:
            conn.close()
        return {
            "plans": plans,
            # paypal_available now means "show the PayPal button": configured
            # AND not hidden. The capture route stays reachable either way.
            "paypal_available": _paypal_configured() and _paypal_ui_enabled(),
            "bank_transfer_info": os.getenv("BANK_TRANSFER_INFO", ""),
            "usdt_available": bool(_usdt_address()),
            "usdt_address": _usdt_address(),
            "usdt_network": _usdt_network(),
        }

    @app.get('/api/subscriptions/me')
    async def subscription_me(authorization: str = Header(None)):
        user = _require_user(authorization)
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            state = get_subscription_state(cursor, user["id"])
            conn.commit()
        finally:
            conn.close()
        return state

    @app.post('/api/subscriptions/paypal/create-order')
    async def paypal_create_order(body: PlanOrderBody, authorization: str = Header(None)):
        user = _require_user(authorization)
        if not _paypal_configured():
            raise HTTPException(status_code=503, detail="PayPal is not configured")
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            plan = _load_plan(cursor, body.plan_code)
        finally:
            conn.close()

        access = _paypal_token()
        resp = requests.post(
            f"{_paypal_base()}/v2/checkout/orders",
            headers={"Authorization": f"Bearer {access}"},
            json={
                "intent": "CAPTURE",
                "purchase_units": [{
                    "reference_id": f"user-{user['id']}-{plan['code']}",
                    "description": f"Sooppiy {plan['name']} — {SUBSCRIPTION_DAYS} days",
                    "amount": {"currency_code": "USD", "value": f"{plan['price_usd']:.2f}"},
                }],
                "application_context": {
                    "return_url": f"{_frontend_url()}/subscribe?paypal=return",
                    "cancel_url": f"{_frontend_url()}/subscribe?paypal=cancel",
                    "user_action": "PAY_NOW",
                    "shipping_preference": "NO_SHIPPING",
                },
            },
            timeout=20,
        )
        if resp.status_code not in (200, 201):
            logger.error("PayPal create order failed: %s %s", resp.status_code, resp.text[:300])
            raise HTTPException(status_code=502, detail="PayPal order creation failed")
        order = resp.json()
        approve_url = next(
            (l["href"] for l in order.get("links", []) if l.get("rel") == "approve"), None)
        if not approve_url:
            raise HTTPException(status_code=502, detail="PayPal returned no approval link")

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO user_subscriptions (user_id, plan_code, status, method, reference, amount_usd) "
                "VALUES (?, ?, 'pending', 'paypal', ?, ?)",
                (user["id"], plan["code"], order["id"], plan["price_usd"]),
            )
            conn.commit()
        finally:
            conn.close()
        return {"order_id": order["id"], "approve_url": approve_url}

    @app.post('/api/subscriptions/paypal/capture')
    async def paypal_capture(body: PaypalCaptureBody, authorization: str = Header(None)):
        user = _require_user(authorization)
        if not _paypal_configured():
            raise HTTPException(status_code=503, detail="PayPal is not configured")
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT id, plan_code, status FROM user_subscriptions "
                "WHERE user_id = ? AND method = 'paypal' AND reference = ?",
                (user["id"], body.order_id),
            )
            row = cursor.fetchone()
        finally:
            conn.close()
        if not row:
            raise HTTPException(status_code=404, detail="Unknown PayPal order")
        if row["status"] == "active":
            return {"ok": True, "status": "active"}

        access = _paypal_token()
        resp = requests.post(
            f"{_paypal_base()}/v2/checkout/orders/{body.order_id}/capture",
            headers={"Authorization": f"Bearer {access}"},
            json={},
            timeout=20,
        )
        if resp.status_code not in (200, 201):
            logger.error("PayPal capture failed: %s %s", resp.status_code, resp.text[:300])
            raise HTTPException(status_code=502, detail="PayPal capture failed")
        if resp.json().get("status") != "COMPLETED":
            raise HTTPException(status_code=402, detail="Payment not completed")

        started = _now()
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE user_subscriptions SET status = 'active', started_at = ?, expires_at = ? WHERE id = ?",
                (_iso(started), _iso(started + timedelta(days=SUBSCRIPTION_DAYS)), row["id"]),
            )
            conn.commit()
        finally:
            conn.close()
        logger.info("PayPal subscription activated: user=%s plan=%s order=%s",
                    user["id"], row["plan_code"], body.order_id)
        return {"ok": True, "status": "active"}

    def _submit_manual_payment(authorization: str, plan_code: str, reference: str,
                               method: str, empty_msg: str, duplicate_msg: str) -> dict:
        """Shared path for the two operator-approved rails (bank, usdt): record
        a pending subscription carrying the user's proof of payment, which an
        admin approves in the console. Identical in every respect except the
        method tag and the wording of the two refusals."""
        user = _require_user(authorization)
        reference = reference.strip()
        if not reference:
            raise HTTPException(status_code=400, detail=empty_msg)
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            plan = _load_plan(cursor, plan_code)
            state = get_subscription_state(cursor, user["id"])
            if state["status"] == "pending" and state["subscription"]["method"] == method:
                raise HTTPException(status_code=400, detail=duplicate_msg)
            cursor.execute(
                "INSERT INTO user_subscriptions (user_id, plan_code, status, method, reference, amount_usd) "
                "VALUES (?, ?, 'pending', ?, ?, ?)",
                (user["id"], plan["code"], method, reference[:500], plan["price_usd"]),
            )
            conn.commit()
        finally:
            conn.close()
        logger.info("%s subscription submitted: user=%s plan=%s", method, user["id"], plan_code)
        return {"ok": True, "status": "pending"}

    @app.post('/api/subscriptions/bank-transfer')
    async def bank_transfer(body: BankTransferBody, authorization: str = Header(None)):
        return _submit_manual_payment(
            authorization, body.plan_code, body.reference, "bank",
            "Transfer reference required",
            "A bank transfer is already awaiting approval")

    @app.post('/api/subscriptions/usdt')
    async def usdt_payment(body: UsdtPaymentBody, authorization: str = Header(None)):
        """USDT is the default rail. Settlement is operator-verified: the user
        sends to the published address and submits the transaction hash, which
        an admin checks on-chain before approving. No funds move through this
        service and no key material is held here."""
        if not _usdt_address():
            raise HTTPException(status_code=503, detail="USDT payment is not configured")
        return _submit_manual_payment(
            authorization, body.plan_code, body.tx_hash, "usdt",
            "Transaction hash required",
            "A USDT payment is already awaiting approval")

    @app.post('/api/subscriptions/contract')
    async def contract_request(body: ContractBody, authorization: str = Header(None)):
        email = body.email.strip().lower()
        if not email or "@" not in email:
            raise HTTPException(status_code=400, detail="Valid email required")
        token = _extract_token(authorization)
        user = _get_user_by_token(token) if token else None
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO contract_requests (user_id, name, email, company, phone, message) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (user["id"] if user else None, body.name.strip()[:200], email,
                 body.company.strip()[:200], body.phone.strip()[:50], body.message.strip()[:4000]),
            )
            conn.commit()
        finally:
            conn.close()
        return {"ok": True}
