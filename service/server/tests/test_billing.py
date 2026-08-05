"""Billing (Stripe + PayPal auto-renew) — schema, state sync, routes, webhooks.

Spec: docs/superpowers/specs/2026-08-04-billing-stripe-paypal-design.md
All external HTTP (Stripe SDK, PayPal requests) is mocked — no live calls.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database


class BillingSchemaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()

    def tearDown(self):
        self.tmp.cleanup()

    def _cols(self, table: str) -> set[str]:
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute(f"PRAGMA table_info({table})")
            return {r["name"] for r in cur.fetchall()}
        finally:
            conn.close()

    def test_new_columns_exist(self):
        self.assertIn("stripe_customer_id", self._cols("users"))
        self.assertLessEqual({"stripe_price_id", "paypal_plan_id"},
                             self._cols("subscription_plans"))
        self.assertLessEqual({"external_id", "auto_renew", "cancel_at_period_end"},
                             self._cols("user_subscriptions"))

    def test_billing_events_unique(self):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO billing_events (provider, event_id, type, payload, processed_at) "
                "VALUES ('stripe', 'evt_1', 'invoice.paid', '{}', '2026-01-01T00:00:00Z')")
            with self.assertRaises(Exception):
                cur.execute(
                    "INSERT INTO billing_events (provider, event_id, type, payload, processed_at) "
                    "VALUES ('stripe', 'evt_1', 'invoice.paid', '{}', '2026-01-01T00:00:00Z')")
        finally:
            conn.close()


from datetime import datetime, timedelta, timezone


class BillingSyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("INSERT INTO users (email, password_hash) VALUES ('b@t.dev', 'x')")
            self.user_id = cur.lastrowid
            cur.execute("UPDATE subscription_plans SET stripe_price_id = 'price_jr', "
                        "paypal_plan_id = 'P-JR' WHERE code = 'junior'")
            cur.execute("UPDATE subscription_plans SET stripe_price_id = 'price_pro', "
                        "paypal_plan_id = 'P-PRO' WHERE code = 'pro'")
            conn.commit()
        finally:
            conn.close()

    def tearDown(self):
        self.tmp.cleanup()

    def _sub_row(self):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM user_subscriptions WHERE user_id = ? "
                        "ORDER BY id DESC LIMIT 1", (self.user_id,))
            row = cur.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def test_record_event_dedupes(self):
        import billing_sync
        self.assertTrue(billing_sync.record_billing_event("stripe", "evt_a", "t", "{}"))
        self.assertFalse(billing_sync.record_billing_event("stripe", "evt_a", "t", "{}"))
        billing_sync.delete_billing_event("stripe", "evt_a")
        self.assertTrue(billing_sync.record_billing_event("stripe", "evt_a", "t", "{}"))

    def test_activate_extend_cancel_lifecycle(self):
        import billing_sync
        from routes_subscriptions import get_subscription_state
        billing_sync.upsert_autorenew_subscription(
            provider="stripe", user_id=self.user_id, plan_code="junior",
            external_id="sub_1")
        row = self._sub_row()
        self.assertEqual(row["status"], "active")
        self.assertEqual(row["method"], "stripe")
        self.assertEqual(int(row["auto_renew"]), 1)

        # renewal pushes expires_at to period_end + grace
        pe = datetime.now(timezone.utc) + timedelta(days=30)
        billing_sync.extend_subscription("stripe", "sub_1", pe)
        expires = self._sub_row()["expires_at"]
        want = (pe + timedelta(days=billing_sync.GRACE_DAYS)).strftime("%Y-%m-%d")
        self.assertTrue(expires.startswith(want))

        # plan switch via subscription.updated
        billing_sync.apply_subscription_update("stripe", "sub_1", plan_code="pro")
        self.assertEqual(self._sub_row()["plan_code"], "pro")

        # cancel-at-period-end keeps access
        billing_sync.mark_cancelled("stripe", "sub_1")
        row = self._sub_row()
        self.assertEqual(row["status"], "active")
        self.assertEqual(int(row["cancel_at_period_end"]), 1)
        self.assertEqual(int(row["auto_renew"]), 0)

        # hard end closes access now
        billing_sync.end_subscription("stripe", "sub_1")
        self.assertEqual(self._sub_row()["status"], "expired")
        conn = database.get_db_connection()
        try:
            state = get_subscription_state(conn.cursor(), self.user_id)
            conn.commit()
        finally:
            conn.close()
        self.assertEqual(state["status"], "none")

    def test_upsert_supersedes_previous_rows(self):
        import billing_sync
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO user_subscriptions (user_id, plan_code, status, method, "
                "started_at, expires_at) VALUES (?, 'junior', 'active', 'usdt', "
                "'2026-08-01T00:00:00Z', '2026-08-30T00:00:00Z')", (self.user_id,))
            conn.commit()
        finally:
            conn.close()
        billing_sync.upsert_autorenew_subscription(
            provider="paypal", user_id=self.user_id, plan_code="pro",
            external_id="I-XYZ")
        row = self._sub_row()
        self.assertEqual((row["method"], row["status"]), ("paypal", "active"))
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) AS c FROM user_subscriptions "
                        "WHERE user_id = ? AND status = 'active'", (self.user_id,))
            self.assertEqual(int(dict(cur.fetchone())["c"]), 1)
        finally:
            conn.close()

    def test_activate_is_idempotent_per_external_id(self):
        import billing_sync
        billing_sync.upsert_autorenew_subscription(
            provider="stripe", user_id=self.user_id, plan_code="junior",
            external_id="sub_dup")
        billing_sync.upsert_autorenew_subscription(
            provider="stripe", user_id=self.user_id, plan_code="junior",
            external_id="sub_dup")
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) AS c FROM user_subscriptions "
                        "WHERE external_id = 'sub_dup'")
            self.assertEqual(int(dict(cur.fetchone())["c"]), 1)
        finally:
            conn.close()

    def test_plan_lookups(self):
        import billing_sync
        self.assertEqual(billing_sync.plan_for_stripe_price("price_pro"), "pro")
        self.assertIsNone(billing_sync.plan_for_stripe_price("price_nope"))
        self.assertEqual(billing_sync.plan_for_paypal_plan("P-JR"), "junior")
        ids = billing_sync.billing_ids_for_plan("junior")
        self.assertEqual(ids["stripe_price_id"], "price_jr")
        self.assertEqual(ids["paypal_plan_id"], "P-JR")

    def test_record_event_reraises_non_duplicate_errors(self):
        import billing_sync
        from unittest.mock import patch
        with patch.object(billing_sync, "get_db_connection",
                          side_effect=RuntimeError("db down")):
            with self.assertRaises(RuntimeError):
                billing_sync.record_billing_event("stripe", "evt_x", "t", "{}")

    def test_reactivation_does_not_break_one_active_invariant(self):
        import billing_sync
        billing_sync.upsert_autorenew_subscription(
            provider="stripe", user_id=self.user_id, plan_code="junior",
            external_id="sub_old")
        billing_sync.upsert_autorenew_subscription(
            provider="paypal", user_id=self.user_id, plan_code="pro",
            external_id="I-new")
        # late event re-activates the old, superseded subscription
        billing_sync.upsert_autorenew_subscription(
            provider="stripe", user_id=self.user_id, plan_code="junior",
            external_id="sub_old")
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) AS c FROM user_subscriptions "
                        "WHERE user_id = ? AND status = 'active'", (self.user_id,))
            self.assertEqual(int(dict(cur.fetchone())["c"]), 1)
        finally:
            conn.close()


from unittest.mock import patch

from fastapi.testclient import TestClient


def _register_user(client: TestClient, db) -> tuple[int, str]:
    """Insert a user + session token directly (register route needs email codes)."""
    import secrets
    conn = db.get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("INSERT INTO users (email, password_hash) VALUES ('pay@t.dev', 'x')")
        user_id = cur.lastrowid
        token = secrets.token_urlsafe(24)
        cur.execute("INSERT INTO user_tokens (user_id, token, expires_at) VALUES (?, ?, "
                    "'2030-01-01T00:00:00Z')", (user_id, token))
        conn.commit()
        return user_id, token
    finally:
        conn.close()


class StripeCheckoutTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        os.environ["STRIPE_SECRET_KEY"] = "sk_test_x"
        from routes import create_app
        self.client = TestClient(create_app())
        self.user_id, self.token = _register_user(self.client, database)
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("UPDATE subscription_plans SET stripe_price_id = 'price_jr' "
                        "WHERE code = 'junior'")
            conn.commit()
        finally:
            conn.close()

    def tearDown(self):
        os.environ["STRIPE_SECRET_KEY"] = ""
        self.tmp.cleanup()

    def _h(self):
        return {"Authorization": f"Bearer {self.token}"}

    def test_checkout_returns_hosted_url_and_saves_customer(self):
        with patch("stripe.Customer.create", return_value={"id": "cus_1"}) as cc, \
             patch("stripe.checkout.Session.create",
                   return_value={"url": "https://checkout.stripe.com/x"}) as sc:
            r = self.client.post("/api/subscriptions/stripe/checkout",
                                 json={"plan_code": "junior"}, headers=self._h())
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["url"], "https://checkout.stripe.com/x")
        cc.assert_called_once()
        kwargs = sc.call_args.kwargs
        self.assertEqual(kwargs["mode"], "subscription")
        self.assertEqual(kwargs["client_reference_id"], str(self.user_id))
        self.assertEqual(kwargs["line_items"], [{"price": "price_jr", "quantity": 1}])
        self.assertEqual(kwargs["metadata"],
                         {"user_id": str(self.user_id), "plan_code": "junior"})
        self.assertEqual(kwargs["subscription_data"],
                         {"metadata": {"user_id": str(self.user_id),
                                       "plan_code": "junior"}})
        cc_kwargs = cc.call_args.kwargs
        self.assertEqual(cc_kwargs["email"], "pay@t.dev")
        self.assertEqual(cc_kwargs["metadata"], {"user_id": str(self.user_id)})
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT stripe_customer_id FROM users WHERE id = ?",
                        (self.user_id,))
            self.assertEqual(dict(cur.fetchone())["stripe_customer_id"], "cus_1")
        finally:
            conn.close()

    def test_checkout_409_when_autorenew_active(self):
        import billing_sync
        billing_sync.upsert_autorenew_subscription(
            provider="paypal", user_id=self.user_id, plan_code="junior",
            external_id="I-1")
        r = self.client.post("/api/subscriptions/stripe/checkout",
                             json={"plan_code": "junior"}, headers=self._h())
        self.assertEqual(r.status_code, 409)

    def test_checkout_503_when_unconfigured(self):
        os.environ["STRIPE_SECRET_KEY"] = ""
        r = self.client.post("/api/subscriptions/stripe/checkout",
                             json={"plan_code": "junior"}, headers=self._h())
        self.assertEqual(r.status_code, 503)

    def test_checkout_503_when_plan_has_no_price(self):
        r = self.client.post("/api/subscriptions/stripe/checkout",
                             json={"plan_code": "pro"}, headers=self._h())
        self.assertEqual(r.status_code, 503)

    def test_portal_returns_url(self):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("UPDATE users SET stripe_customer_id = 'cus_9' WHERE id = ?",
                        (self.user_id,))
            conn.commit()
        finally:
            conn.close()
        with patch("stripe.billing_portal.Session.create",
                   return_value={"url": "https://billing.stripe.com/p"}):
            r = self.client.post("/api/subscriptions/stripe/portal", headers=self._h())
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["url"], "https://billing.stripe.com/p")

    def test_portal_404_without_customer(self):
        r = self.client.post("/api/subscriptions/stripe/portal", headers=self._h())
        self.assertEqual(r.status_code, 404)

    def test_checkout_reuses_saved_customer(self):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("UPDATE users SET stripe_customer_id = 'cus_saved' "
                        "WHERE id = ?", (self.user_id,))
            conn.commit()
        finally:
            conn.close()
        with patch("stripe.Customer.create") as cc, \
             patch("stripe.checkout.Session.create",
                   return_value={"url": "https://checkout.stripe.com/x"}) as sc:
            r = self.client.post("/api/subscriptions/stripe/checkout",
                                 json={"plan_code": "junior"}, headers=self._h())
        self.assertEqual(r.status_code, 200, r.text)
        cc.assert_not_called()
        self.assertEqual(sc.call_args.kwargs["customer"], "cus_saved")

    def test_checkout_502_when_stripe_errors(self):
        with patch("stripe.Customer.create", return_value={"id": "cus_1"}), \
             patch("stripe.checkout.Session.create",
                   side_effect=RuntimeError("stripe down")):
            r = self.client.post("/api/subscriptions/stripe/checkout",
                                 json={"plan_code": "junior"}, headers=self._h())
        self.assertEqual(r.status_code, 502)


import hashlib
import hmac as hmac_mod
import json
import time


def _stripe_sig(payload: bytes, secret: str) -> str:
    ts = str(int(time.time()))
    mac = hmac_mod.new(secret.encode(),
                       f"{ts}.{payload.decode()}".encode(), hashlib.sha256).hexdigest()
    return f"t={ts},v1={mac}"


class StripeWebhookTests(unittest.TestCase):
    SECRET = "whsec_test"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        os.environ["STRIPE_WEBHOOK_SECRET"] = self.SECRET
        from routes import create_app
        self.client = TestClient(create_app())
        self.user_id, self.token = _register_user(self.client, database)
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("UPDATE subscription_plans SET stripe_price_id = 'price_jr' "
                        "WHERE code = 'junior'")
            cur.execute("UPDATE subscription_plans SET stripe_price_id = 'price_pro' "
                        "WHERE code = 'pro'")
            conn.commit()
        finally:
            conn.close()

    def tearDown(self):
        os.environ["STRIPE_WEBHOOK_SECRET"] = ""
        self.tmp.cleanup()

    def _post(self, event: dict, sig: str | None = None):
        # Real Stripe events always carry "object": "event"; the installed
        # stripe SDK's construct_event() reads event.object internally and
        # raises if it's absent, so every fixture needs it set.
        event = {**event, "object": "event"}
        payload = json.dumps(event).encode()
        return self.client.post(
            "/api/webhooks/stripe", content=payload,
            headers={"Stripe-Signature": sig or _stripe_sig(payload, self.SECRET),
                     "Content-Type": "application/json"})

    def _checkout_completed(self, event_id="evt_cs1", sub_id="sub_A"):
        return {"id": event_id, "type": "checkout.session.completed",
                "data": {"object": {"client_reference_id": str(self.user_id),
                                    "subscription": sub_id,
                                    "metadata": {"user_id": str(self.user_id),
                                                 "plan_code": "junior"}}}}

    def test_bad_signature_rejected(self):
        r = self._post(self._checkout_completed(), sig="t=1,v1=deadbeef")
        self.assertEqual(r.status_code, 400)

    def test_checkout_completed_activates(self):
        r = self._post(self._checkout_completed())
        self.assertEqual(r.status_code, 200, r.text)
        import billing_sync
        sub = billing_sync.active_autorenew(self.user_id)
        self.assertIsNotNone(sub)
        self.assertEqual((sub["method"], sub["plan_code"], sub["external_id"]),
                         ("stripe", "junior", "sub_A"))

    def test_duplicate_event_is_noop(self):
        self._post(self._checkout_completed())
        r = self._post(self._checkout_completed())
        self.assertEqual(r.status_code, 200)
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) AS c FROM user_subscriptions "
                        "WHERE external_id = 'sub_A'")
            self.assertEqual(int(dict(cur.fetchone())["c"]), 1)
        finally:
            conn.close()

    def test_invoice_paid_extends(self):
        self._post(self._checkout_completed())
        period_end = int(time.time()) + 30 * 86400
        r = self._post({"id": "evt_inv1", "type": "invoice.paid",
                        "data": {"object": {"subscription": "sub_A",
                                            "lines": {"data": [{"period": {"end": period_end}}]}}}})
        self.assertEqual(r.status_code, 200)
        import billing_sync
        expires = billing_sync.active_autorenew(self.user_id)["expires_at"]
        from datetime import datetime, timedelta, timezone
        want = (datetime.fromtimestamp(period_end, tz=timezone.utc)
                + timedelta(days=billing_sync.GRACE_DAYS)).strftime("%Y-%m-%d")
        self.assertTrue(expires.startswith(want))

    def test_subscription_updated_switches_plan_and_flags_cancel(self):
        self._post(self._checkout_completed())
        r = self._post({"id": "evt_up1", "type": "customer.subscription.updated",
                        "data": {"object": {"id": "sub_A", "cancel_at_period_end": True,
                                            "items": {"data": [{"price": {"id": "price_pro"}}]}}}})
        self.assertEqual(r.status_code, 200)
        row = None
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT plan_code, cancel_at_period_end FROM user_subscriptions "
                        "WHERE external_id = 'sub_A'")
            row = dict(cur.fetchone())
        finally:
            conn.close()
        self.assertEqual(row["plan_code"], "pro")
        self.assertEqual(int(row["cancel_at_period_end"]), 1)

    def test_subscription_deleted_ends_access(self):
        self._post(self._checkout_completed())
        r = self._post({"id": "evt_del1", "type": "customer.subscription.deleted",
                        "data": {"object": {"id": "sub_A"}}})
        self.assertEqual(r.status_code, 200)
        import billing_sync
        self.assertIsNone(billing_sync.active_autorenew(self.user_id))

    def test_unknown_event_stored_and_ignored(self):
        r = self._post({"id": "evt_odd", "type": "charge.refunded",
                        "data": {"object": {}}})
        self.assertEqual(r.status_code, 200)

    def test_handler_failure_unrecords_and_retry_reprocesses(self):
        event = self._checkout_completed(event_id="evt_fail1", sub_id="sub_F")
        with patch("routes_billing.billing_sync.upsert_autorenew_subscription",
                   side_effect=RuntimeError("boom")):
            r = self._post(event)
        self.assertEqual(r.status_code, 500)
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) AS c FROM billing_events "
                        "WHERE provider = 'stripe' AND event_id = 'evt_fail1'")
            self.assertEqual(int(dict(cur.fetchone())["c"]), 0)
        finally:
            conn.close()
        # provider retry with the SAME event id must now be processed
        r = self._post(event)
        self.assertEqual(r.status_code, 200, r.text)
        import billing_sync
        sub = billing_sync.active_autorenew(self.user_id)
        self.assertEqual(sub["external_id"], "sub_F")

    def test_unknown_event_row_is_recorded(self):
        self._post({"id": "evt_odd2", "type": "charge.refunded",
                    "data": {"object": {}}})
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT type FROM billing_events "
                        "WHERE provider = 'stripe' AND event_id = 'evt_odd2'")
            self.assertEqual(dict(cur.fetchone())["type"], "charge.refunded")
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
