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


if __name__ == "__main__":
    unittest.main()
