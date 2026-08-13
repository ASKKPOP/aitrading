"""Card-at-signup 7-day trial and its pre-charge notice.

Service rules 2026-08-12: a card is registered before the trial starts, the
first 7 days are free, and the subscription then converts automatically. Cancel
any time inside the 7 days and nothing is charged.

Stripe owns the clock (`trial_period_days` on the Checkout Session) and fires
customer.subscription.trial_will_end three days out — day 4 of 7. There is no
trial state of ours and no scheduler of ours, so nothing can drift out of step.

Consequently there is NO free account: signup alone must not create a
subscription row. That is asserted here too, because the previous design did
exactly that and the regression would be invisible.

All external HTTP (Stripe SDK, email) is mocked — no live calls.
"""

from __future__ import annotations

import hashlib
import hmac as hmac_mod
import json
import os
import secrets
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database  # noqa: E402

TRIAL_DAYS = 7


def _mk_user(email="trial@t.dev", lang="en") -> tuple[int, str]:
    conn = database.get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("INSERT INTO users (email, password_hash, lang) VALUES (?, 'x', ?)",
                    (email, lang))
        uid = int(cur.lastrowid)
        token = secrets.token_urlsafe(24)
        cur.execute("INSERT INTO user_tokens (user_id, token, expires_at) VALUES "
                    "(?, ?, '2030-01-01T00:00:00Z')", (uid, token))
        conn.commit()
        return uid, token
    finally:
        conn.close()


def _seed_prices():
    conn = database.get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE subscription_plans SET stripe_price_id='price_jr' WHERE code='junior'")
        cur.execute("UPDATE subscription_plans SET stripe_price_id='price_pro' WHERE code='pro'")
        conn.commit()
    finally:
        conn.close()


class _Db(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        from routes import create_app
        self.client = TestClient(create_app())

    def tearDown(self):
        self.tmp.cleanup()


class TrialOnCheckoutTests(_Db):
    def setUp(self):
        super().setUp()
        os.environ["STRIPE_SECRET_KEY"] = "sk_test_x"
        self.user_id, self.token = _mk_user()
        _seed_prices()

    def tearDown(self):
        os.environ["STRIPE_SECRET_KEY"] = ""
        super().tearDown()

    def _checkout(self, plan_code="junior"):
        with patch("stripe.Customer.create", return_value={"id": "cus_1"}), \
             patch("stripe.checkout.Session.create",
                   return_value={"url": "https://checkout.stripe.com/x"}) as sc:
            r = self.client.post("/api/subscriptions/stripe/checkout",
                                 json={"plan_code": plan_code},
                                 headers={"Authorization": f"Bearer {self.token}"})
        self.assertEqual(r.status_code, 200, r.text)
        return sc.call_args.kwargs

    def test_junior_first_time_gets_the_seven_day_trial(self):
        self.assertEqual(self._checkout("junior")["subscription_data"]
                         .get("trial_period_days"), TRIAL_DAYS)

    def test_trial_does_not_displace_the_metadata(self):
        """The activation webhook resolves the member from this metadata; if
        the trial replaced it instead of joining it, checkout would succeed and
        the subscription would never attach to anyone."""
        self.assertEqual(self._checkout("junior")["subscription_data"]["metadata"],
                         {"user_id": str(self.user_id), "plan_code": "junior"})

    def test_pro_bills_from_day_one(self):
        self.assertNotIn("trial_period_days", self._checkout("pro")["subscription_data"])

    def test_repeat_subscriber_gets_no_second_trial(self):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO user_subscriptions (user_id, plan_code, status, method, "
                "started_at, expires_at) VALUES (?, 'junior', 'expired', 'stripe', "
                "'2026-01-01T00:00:00Z', '2026-02-01T00:00:00Z')", (self.user_id,))
            conn.commit()
        finally:
            conn.close()
        self.assertNotIn("trial_period_days", self._checkout("junior")["subscription_data"])


class NoFreeAccountTests(_Db):
    def test_signup_alone_grants_no_subscription(self):
        """There is no free tier: a new account must reach the paywall with
        nothing granted. The previous design created a trial row here."""
        from datetime import datetime, timedelta, timezone
        stored = {"code": "123456", "attempts": 0,
                  "expires_at": datetime.now(timezone.utc) + timedelta(minutes=5)}
        with patch("routes_users.send_welcome_email", return_value=True), \
             patch("routes_users._load_code", return_value=stored), \
             patch("routes_users._delete_code"):
            r = self.client.post("/api/users/register",
                                 json={"email": "n@t.dev", "password": "pw123456",
                                       "code": "123456"})
        self.assertEqual(r.status_code, 200, r.text)
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) c FROM user_subscriptions WHERE user_id = ?",
                        (int(r.json()["user_id"]),))
            self.assertEqual(int(dict(cur.fetchone())["c"]), 0)
        finally:
            conn.close()


def _sig(payload: bytes, secret: str) -> str:
    ts = str(int(time.time()))
    mac = hmac_mod.new(secret.encode(), f"{ts}.{payload.decode()}".encode(),
                       hashlib.sha256).hexdigest()
    return f"t={ts},v1={mac}"


class TrialReminderWebhookTests(_Db):
    SECRET = "whsec_test"

    def setUp(self):
        super().setUp()
        os.environ["STRIPE_WEBHOOK_SECRET"] = self.SECRET
        self.user_id, _ = _mk_user("ko@t.dev", "ko")
        _seed_prices()
        import billing_sync
        billing_sync.upsert_autorenew_subscription(
            provider="stripe", user_id=self.user_id, plan_code="junior",
            external_id="sub_T")

    def tearDown(self):
        os.environ["STRIPE_WEBHOOK_SECRET"] = ""
        super().tearDown()

    def _post(self, event: dict):
        event = {**event, "object": "event"}
        payload = json.dumps(event).encode()
        return self.client.post("/api/webhooks/stripe", content=payload,
                                headers={"Stripe-Signature": _sig(payload, self.SECRET),
                                         "Content-Type": "application/json"})

    def _twe(self, sub_id="sub_T", event_id="evt_1"):
        return {"id": event_id, "type": "customer.subscription.trial_will_end",
                "data": {"object": {"id": sub_id,
                                    "trial_end": int(time.time()) + 3 * 86400}}}

    def test_reminder_reaches_the_subscriber_in_their_language(self):
        with patch("email_sender.send_trial_reminder_email", return_value=True) as s:
            r = self._post(self._twe())
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(s.call_args.kwargs["to_email"], "ko@t.dev")
        self.assertEqual(s.call_args.kwargs["lang"], "ko")

    def test_reminder_states_the_amount_and_the_date(self):
        """ARL wants both, not just 'your trial is ending'."""
        with patch("email_sender.send_trial_reminder_email", return_value=True) as s:
            self._post(self._twe())
        self.assertEqual(float(s.call_args.kwargs["amount_usd"]), 60.0)
        self.assertRegex(s.call_args.kwargs["charge_on"], r"^\d{4}-\d{2}-\d{2}$")

    def test_unknown_subscription_is_a_noop_not_a_failure(self):
        with patch("email_sender.send_trial_reminder_email") as s:
            r = self._post(self._twe(sub_id="sub_NOPE"))
        self.assertEqual(r.status_code, 200, r.text)
        s.assert_not_called()

    def test_delivery_failure_returns_500_so_stripe_retries(self):
        """A missed legally-required notice is worse than a duplicate one."""
        with patch("email_sender.send_trial_reminder_email", return_value=False):
            self.assertEqual(self._post(self._twe()).status_code, 500)

    def test_redelivered_event_does_not_send_twice(self):
        with patch("email_sender.send_trial_reminder_email", return_value=True) as s:
            self._post(self._twe())
            self._post(self._twe())
        self.assertEqual(s.call_count, 1)


class TrialCopyTests(unittest.TestCase):
    LANGS = ("en", "ko", "ja", "th", "vi", "id")

    def test_every_language_renders_with_amount_and_date(self):
        from email_i18n import trial_reminder_email
        for lang in self.LANGS:
            with self.subTest(lang=lang):
                subject, html = trial_reminder_email(lang, 60.0, "2026-08-19")
                self.assertTrue(subject.strip())
                self.assertIn("Sooppiy", html)
                self.assertIn("2026-08-19", html)
                self.assertIn("60", html)

    def test_no_unfilled_placeholders(self):
        from email_i18n import trial_reminder_email, trial_reminder_email_text
        for lang in self.LANGS:
            with self.subTest(lang=lang):
                subject, html = trial_reminder_email(lang, 60.0, "2026-08-19")
                text = trial_reminder_email_text(lang, 60.0, "2026-08-19")
                for blob in (subject, html, text):
                    self.assertNotIn("{", blob)

    def test_every_translation_keeps_both_placeholders(self):
        """Checked on the raw copy, not the rendered output: the template also
        prints the amount and date in their own box, so a translation that
        dropped '{date}' from its sentence still rendered a date somewhere and
        passed the output-level checks. Mutation testing caught exactly that."""
        from email_i18n import _TRIAL
        for lang in self.LANGS:
            with self.subTest(lang=lang):
                c = _TRIAL[lang]
                self.assertIn("{date}", c["body"])
                self.assertIn("{amount}", c["body"])
                self.assertIn("{date}", c["note"])

    def test_every_supported_language_has_copy(self):
        from email_i18n import _TRIAL
        self.assertEqual(set(_TRIAL), set(self.LANGS))

    def test_copy_states_that_a_charge_will_happen(self):
        """A card IS held now. Saying otherwise — as the card-free design's
        copy did — would understate what is about to occur."""
        from email_i18n import trial_reminder_email_text
        text = trial_reminder_email_text("en", 60.0, "2026-08-19").lower()
        self.assertIn("charged", text)
        self.assertIn("automatically", text)

    def test_copy_states_how_to_stop_the_charge(self):
        from email_i18n import trial_reminder_email_text
        self.assertIn("cancel",
                      trial_reminder_email_text("en", 60.0, "2026-08-19").lower())

    def test_unknown_language_falls_back_to_english(self):
        from email_i18n import trial_reminder_email
        self.assertEqual(trial_reminder_email("xx", 60.0, "2026-08-19"),
                         trial_reminder_email("en", 60.0, "2026-08-19"))


if __name__ == "__main__":
    unittest.main()
