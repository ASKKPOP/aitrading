"""Admin console: configuring the Stripe price id per plan.

Without that column populated, checkout 503s ("this plan is not
configured for card payments") no matter how correct the API keys are — and
until now the only way to set them was raw SQL against prod.

Everything is asserted THROUGH THE API, not by writing the columns directly:
the failure mode this guards against is a field that the request model silently
drops, which a direct-DB test would never notice.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database  # noqa: E402
from routes import create_app  # noqa: E402

PRICE = "price_1QabcDEFghiJKL"


class PlanBillingIdTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())
        from admin_auth import create_admin
        create_admin("root@test.com", "rootpass123", "superadmin")
        r = self.client.post("/api/admin/login",
                             json={"email": "root@test.com", "password": "rootpass123"})
        self.admin = {"Authorization": f"Bearer {r.json()['token']}"}

    def tearDown(self):
        self.tmp.cleanup()

    def _plans(self) -> dict:
        r = self.client.get("/api/admin/plans", headers=self.admin)
        self.assertEqual(r.status_code, 200, r.text)
        return {p["code"]: p for p in r.json()["plans"]}

    def _patch(self, code: str, body: dict):
        return self.client.patch(f"/api/admin/plans/{code}", json=body,
                                 headers=self.admin)

    # ── read ────────────────────────────────────────────────────────────
    def test_listing_exposes_both_billing_ids(self):
        junior = self._plans()["junior"]
        self.assertIn("stripe_price_id", junior)

    def test_unconfigured_plan_reports_empty_ids(self):
        junior = self._plans()["junior"]
        self.assertFalse(junior["stripe_price_id"])

    # ── write ───────────────────────────────────────────────────────────
    def test_setting_the_stripe_price_id_persists(self):
        self.assertEqual(self._patch("junior", {"stripe_price_id": PRICE}).status_code, 200)
        self.assertEqual(self._plans()["junior"]["stripe_price_id"], PRICE)

    def test_ids_are_trimmed(self):
        """Copy-paste out of a dashboard brings whitespace with it."""
        self._patch("junior", {"stripe_price_id": f"  {PRICE}\n"})
        self.assertEqual(self._plans()["junior"]["stripe_price_id"], PRICE)

    def test_empty_string_clears_the_id(self):
        self._patch("junior", {"stripe_price_id": PRICE})
        self.assertEqual(self._patch("junior", {"stripe_price_id": ""}).status_code, 200)
        self.assertFalse(self._plans()["junior"]["stripe_price_id"])

    def test_ids_do_not_leak_across_plans(self):
        self._patch("junior", {"stripe_price_id": PRICE})
        self.assertFalse(self._plans()["pro"]["stripe_price_id"])

    # ── validation: the documented footguns ─────────────────────────────
    def test_a_stripe_product_id_is_rejected(self):
        """prod_… is the id Stripe shows most prominently; pasting it instead
        of price_… is the single most likely setup mistake, and it would only
        surface as a 502 at a member's first checkout."""
        r = self._patch("junior", {"stripe_price_id": "prod_QabcDEFghiJKL"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("price_", r.json()["detail"])

    def test_arbitrary_junk_is_rejected(self):
        self.assertEqual(self._patch("junior", {"stripe_price_id": "hello"}).status_code, 400)

    def test_a_rejected_patch_writes_nothing(self):
        self._patch("junior", {"stripe_price_id": PRICE})
        self._patch("junior", {"stripe_price_id": "prod_bad"})
        self.assertEqual(self._plans()["junior"]["stripe_price_id"], PRICE)

    def test_unknown_plan_is_404(self):
        self.assertEqual(self._patch("nope", {"stripe_price_id": PRICE}).status_code, 404)

    def test_requires_admin_auth(self):
        r = self.client.patch("/api/admin/plans/junior",
                              json={"stripe_price_id": PRICE})
        self.assertIn(r.status_code, (401, 403))

    # ── the point of all this ───────────────────────────────────────────
    def test_configuring_via_the_console_makes_checkout_work(self):
        """End-to-end on the gap this closes: with a key set but no price id,
        checkout 503s; after an admin sets the id in the console, it does not."""
        from unittest.mock import patch as mpatch
        import secrets
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("INSERT INTO users (email, password_hash) VALUES ('m@t.dev','x')")
            uid = cur.lastrowid
            token = secrets.token_urlsafe(24)
            cur.execute("INSERT INTO user_tokens (user_id, token, expires_at) "
                        "VALUES (?, ?, '2030-01-01T00:00:00Z')", (uid, token))
            conn.commit()
        finally:
            conn.close()
        os.environ["STRIPE_SECRET_KEY"] = "sk_test_x"
        hdr = {"Authorization": f"Bearer {token}"}
        try:
            before = self.client.post("/api/subscriptions/stripe/checkout",
                                      json={"plan_code": "junior"}, headers=hdr)
            self.assertEqual(before.status_code, 503)

            self._patch("junior", {"stripe_price_id": PRICE})

            with mpatch("stripe.Customer.create", return_value={"id": "cus_1"}), \
                 mpatch("stripe.checkout.Session.create",
                        return_value={"url": "https://checkout.stripe.com/x"}) as sc:
                after = self.client.post("/api/subscriptions/stripe/checkout",
                                         json={"plan_code": "junior"}, headers=hdr)
            self.assertEqual(after.status_code, 200, after.text)
            self.assertEqual(sc.call_args.kwargs["line_items"],
                             [{"price": PRICE, "quantity": 1}])
        finally:
            os.environ["STRIPE_SECRET_KEY"] = ""


if __name__ == "__main__":
    unittest.main()
