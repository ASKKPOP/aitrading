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


if __name__ == "__main__":
    unittest.main()
