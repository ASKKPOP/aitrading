"""Subscription changes from /account/subscription — the manual-rail work.

Upgrade = pay the plan-price difference now, prorated over the unexpired part
of the 30-day period, admin-approved, expires_at untouched. Downgrade = no
payment, scheduled on the active row, effective at renewal. Trial rows are
NEVER prorated — the member paid $0, so proration against junior's list price
would sell credit they never bought; trials go through the normal
first-purchase flow instead. Stripe/PayPal rows are refused too — those rails
have provider-native flows (portal / change-plan).
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database  # noqa: E402
from routes import create_app  # noqa: E402


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def _mk_user_with_token(email: str) -> tuple[int, str]:
    conn = database.get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("INSERT INTO users (email, password_hash, lang) VALUES (?, 'x', 'en')",
                    (email,))
        uid = int(cur.lastrowid)
        token = f"tok-{uid}-subchange"
        expires = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("INSERT INTO user_tokens (user_id, token, expires_at) VALUES (?, ?, ?)",
                    (uid, token, expires))
        conn.commit()
        return uid, token
    finally:
        conn.close()


def _mk_sub(uid: int, plan: str, *, status: str = "active", method: str = "usdt",
            days_left: float = 15.0, amount: float | None = None,
            auto_renew: int = 0, external_id: str | None = None) -> int:
    now = datetime.now(timezone.utc)
    conn = database.get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO user_subscriptions (user_id, plan_code, status, method, reference, "
            "amount_usd, auto_renew, external_id, started_at, expires_at) "
            "VALUES (?, ?, ?, ?, 'ref', ?, ?, ?, ?, ?)",
            (uid, plan, status, method, amount, auto_renew, external_id,
             _iso(now - timedelta(days=30 - days_left)),
             _iso(now + timedelta(days=days_left))))
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def _sub_row(sub_id: int) -> dict:
    conn = database.get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM user_subscriptions WHERE id = ?", (sub_id,))
        return dict(cur.fetchone())
    finally:
        conn.close()


class _Case(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())
        self.uid, token = _mk_user_with_token("change@t.dev")
        self.auth = {"Authorization": f"Bearer {token}"}

    def tearDown(self):
        self.tmp.cleanup()

    def _preview(self, plan_code: str):
        return self.client.post("/api/subscriptions/change/preview",
                                json={"plan_code": plan_code}, headers=self.auth)


class ProrationMathTests(unittest.TestCase):
    """Pure function — deterministic via an explicit `now`."""

    def _f(self):
        from routes_subscriptions import _prorated_upgrade_usd
        return _prorated_upgrade_usd

    def test_half_period_prices_half_the_difference(self):
        now = datetime(2026, 8, 5, tzinfo=timezone.utc)
        ends = _iso(now + timedelta(days=15))
        self.assertEqual(self._f()(500.0, 250.0, ends, now), 125.0)

    def test_one_day_left(self):
        now = datetime(2026, 8, 5, tzinfo=timezone.utc)
        ends = _iso(now + timedelta(days=1))
        self.assertEqual(self._f()(500.0, 250.0, ends, now), 8.33)

    def test_expired_row_prices_zero_never_credit(self):
        now = datetime(2026, 8, 5, tzinfo=timezone.utc)
        ends = _iso(now - timedelta(days=2))
        self.assertEqual(self._f()(500.0, 250.0, ends, now), 0.0)
        # mis-ordered pair (downgrade fed in) must clamp at 0, not go negative
        self.assertEqual(self._f()(60.0, 250.0, _iso(now + timedelta(days=15)), now), 0.0)

    def test_full_period_prices_the_full_difference(self):
        now = datetime(2026, 8, 5, tzinfo=timezone.utc)
        ends = _iso(now + timedelta(days=30))
        self.assertEqual(self._f()(500.0, 250.0, ends, now), 250.0)

    def test_more_than_a_period_remaining_is_clamped(self):
        # extended/grace rows can exceed 30 days; the upgrade never charges
        # more than the plain price difference
        now = datetime(2026, 8, 5, tzinfo=timezone.utc)
        ends = _iso(now + timedelta(days=45))
        self.assertEqual(self._f()(500.0, 250.0, ends, now), 250.0)

    def test_garbage_expiry_prices_zero(self):
        now = datetime(2026, 8, 5, tzinfo=timezone.utc)
        self.assertEqual(self._f()(500.0, 250.0, "not-a-date", now), 0.0)


class ChangePreviewTests(_Case):
    def test_upgrade_preview_prorates_the_difference(self):
        _mk_sub(self.uid, "junior", days_left=15)
        r = self._preview("pro")
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["kind"], "upgrade")
        self.assertEqual(body["effective"], "immediate")
        # (250 − 60) × 15/30 = 95.00 — allow a cent for test wall-clock skew
        self.assertAlmostEqual(body["prorated_usd"], 95.0, delta=0.02)
        self.assertEqual(body["current_plan"], "junior")
        self.assertEqual(body["target_plan"], "pro")

    def test_downgrade_preview_is_free_and_at_renewal(self):
        _mk_sub(self.uid, "pro", days_left=15)
        r = self._preview("junior")
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["kind"], "downgrade")
        self.assertEqual(body["prorated_usd"], 0.0)
        self.assertEqual(body["effective"], "at_renewal")

    def test_same_plan_is_refused(self):
        _mk_sub(self.uid, "pro", days_left=15)
        self.assertEqual(self._preview("pro").status_code, 400)

    def test_trial_rows_are_never_prorated(self):
        _mk_sub(self.uid, "junior", method="trial", days_left=5, amount=None)
        r = self._preview("pro")
        self.assertEqual(r.status_code, 400)
        self.assertIn("full price", r.json()["detail"])

    def test_stripe_rows_use_the_portal(self):
        _mk_sub(self.uid, "pro", method="stripe", days_left=15,
                auto_renew=1, external_id="sub_123")
        r = self._preview("professional")
        self.assertEqual(r.status_code, 400)
        self.assertIn("portal", r.json()["detail"].lower())

    def test_no_subscription_is_404(self):
        self.assertEqual(self._preview("pro").status_code, 404)

    def test_enterprise_target_routes_to_contract(self):
        _mk_sub(self.uid, "pro", days_left=15)
        self.assertEqual(self._preview("enterprise").status_code, 400)

    def test_unknown_plan_is_404(self):
        _mk_sub(self.uid, "pro", days_left=15)
        self.assertEqual(self._preview("platinum").status_code, 404)

    def test_preview_requires_auth(self):
        r = self.client.post("/api/subscriptions/change/preview",
                             json={"plan_code": "pro"})
        self.assertEqual(r.status_code, 401)

    def test_me_exposes_pending_change_columns(self):
        sub_id = _mk_sub(self.uid, "pro", days_left=15)
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("UPDATE user_subscriptions SET pending_plan_code = 'junior', "
                        "change_kind = 'downgrade' WHERE id = ?", (sub_id,))
            conn.commit()
        finally:
            conn.close()
        r = self.client.get("/api/subscriptions/me", headers=self.auth)
        self.assertEqual(r.status_code, 200, r.text)
        sub = r.json()["subscription"]
        self.assertEqual(sub["pending_plan_code"], "junior")
        self.assertEqual(sub["change_kind"], "downgrade")


class ManualUpgradeSubmitTests(_Case):
    def _upgrade(self, plan_code="pro", method="bank", reference="wire-123"):
        return self.client.post(
            "/api/subscriptions/change/upgrade",
            json={"plan_code": plan_code, "method": method, "reference": reference},
            headers=self.auth)

    def test_upgrade_lands_pending_with_server_computed_amount(self):
        _mk_sub(self.uid, "junior", days_left=15)
        r = self._upgrade("pro")
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["status"], "pending")
        # (250 − 60) × 15/30 — the CLIENT never sends an amount
        self.assertAlmostEqual(body["amount_usd"], 95.0, delta=0.02)
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM user_subscriptions WHERE user_id = ? "
                        "AND status = 'pending'", (self.uid,))
            row = dict(cur.fetchone())
        finally:
            conn.close()
        self.assertEqual(row["plan_code"], "pro")
        self.assertEqual(row["change_kind"], "upgrade")
        self.assertEqual(row["method"], "bank")
        self.assertAlmostEqual(float(row["amount_usd"]), 95.0, delta=0.02)

    def test_duplicate_pending_upgrade_is_refused(self):
        _mk_sub(self.uid, "junior", days_left=15)
        self.assertEqual(self._upgrade().status_code, 200)
        self.assertEqual(self._upgrade().status_code, 400)

    def test_trial_cannot_use_the_upgrade_path(self):
        _mk_sub(self.uid, "junior", method="trial", days_left=5)
        self.assertEqual(self._upgrade().status_code, 400)

    def test_downgrade_direction_is_refused(self):
        _mk_sub(self.uid, "professional", days_left=15)
        r = self._upgrade("pro")
        self.assertEqual(r.status_code, 400)
        self.assertIn("downgrade", r.json()["detail"].lower())

    def test_reference_is_required(self):
        _mk_sub(self.uid, "junior", days_left=15)
        self.assertEqual(self._upgrade(reference="  ").status_code, 400)

    def test_method_must_be_a_manual_rail(self):
        _mk_sub(self.uid, "junior", days_left=15)
        self.assertEqual(self._upgrade(method="paypal").status_code, 400)

    def test_usdt_upgrade_needs_the_rail_configured(self):
        _mk_sub(self.uid, "junior", days_left=15)
        self.assertEqual(self._upgrade(method="usdt").status_code, 503)

    def test_usdt_upgrade_works_once_configured(self):
        import platform_settings
        platform_settings.set_setting("usdt_address", "TTestAddr123")
        _mk_sub(self.uid, "junior", days_left=15)
        self.assertEqual(self._upgrade(method="usdt", reference="0xhash").status_code, 200)


if __name__ == "__main__":
    unittest.main()
