"""Card-free 7-day trial: grant at signup, day-4 reminder, expiry shutdown.

The trial holds NO payment method. Nothing converts and nothing is charged —
on day 7 the member's access closes, their daemons are paused, and they are
told. That shapes every test here:

  * the trial is an ordinary active subscription row, so the membership gate,
    entitlements and lazy expiry all work on it unchanged;
  * neither notice may promise or imply a charge;
  * when it lapses, PLAN_LIMITS[None] must zero the member's run allowance so
    subscription_enforcer_tick stops everything they own.

All email delivery is mocked — no live calls.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database  # noqa: E402

TRIAL_DAYS = 7


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def _mk_user(email="trial@t.dev", lang="en") -> int:
    conn = database.get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("INSERT INTO users (email, password_hash, lang) VALUES (?, 'x', ?)",
                    (email, lang))
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def _sub_rows(user_id: int) -> list[dict]:
    conn = database.get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM user_subscriptions WHERE user_id = ? ORDER BY id",
                    (user_id,))
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


class _DbCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()

    def tearDown(self):
        self.tmp.cleanup()


class TrialGrantTests(_DbCase):
    def test_grant_creates_an_active_junior_row_for_seven_days(self):
        import billing_sync
        uid = _mk_user()
        self.assertTrue(billing_sync.grant_trial(uid))
        row = _sub_rows(uid)[0]
        self.assertEqual(row["status"], "active")
        self.assertEqual(row["plan_code"], "junior")
        self.assertEqual(row["method"], "trial")
        started = datetime.fromisoformat(row["started_at"].replace("Z", "+00:00"))
        expires = datetime.fromisoformat(row["expires_at"].replace("Z", "+00:00"))
        self.assertEqual((expires - started).days, TRIAL_DAYS)

    def test_trial_never_looks_like_an_autorenewing_subscription(self):
        """auto_renew=0 matters twice: nothing may imply a recurring charge,
        and active_autorenew() must stay empty so a trialling member can still
        start a real subscription instead of being 409'd."""
        import billing_sync
        uid = _mk_user()
        billing_sync.grant_trial(uid)
        self.assertEqual(int(_sub_rows(uid)[0]["auto_renew"]), 0)
        self.assertIsNone(billing_sync.active_autorenew(uid))

    def test_trial_is_once_per_account(self):
        import billing_sync
        uid = _mk_user()
        self.assertTrue(billing_sync.grant_trial(uid))
        self.assertFalse(billing_sync.grant_trial(uid))
        self.assertEqual(len(_sub_rows(uid)), 1)

    def test_a_lapsed_trial_does_not_earn_a_second_one(self):
        import billing_sync
        uid = _mk_user()
        billing_sync.grant_trial(uid)
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("UPDATE user_subscriptions SET status = 'expired' "
                        "WHERE user_id = ?", (uid,))
            conn.commit()
        finally:
            conn.close()
        self.assertFalse(billing_sync.grant_trial(uid))

    def test_a_paying_member_is_not_given_a_trial(self):
        import billing_sync
        uid = _mk_user()
        billing_sync.upsert_autorenew_subscription(
            provider="stripe", user_id=uid, plan_code="pro", external_id="sub_P")
        self.assertFalse(billing_sync.grant_trial(uid))


class TrialAccessTests(_DbCase):
    """What the trial row means to the rest of the platform."""

    def test_trialling_member_reads_as_an_active_junior_subscriber(self):
        import billing_sync
        from entitlements import plan_code_for_user
        from routes_subscriptions import get_subscription_state
        uid = _mk_user()
        billing_sync.grant_trial(uid)
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            state = get_subscription_state(cur, uid)
            plan = plan_code_for_user(cur, uid)
            conn.commit()
        finally:
            conn.close()
        # App.tsx's membership gate opens on exactly this value
        self.assertEqual(state["status"], "active")
        self.assertEqual(plan, "junior")

    def test_expired_trial_closes_access_and_zeroes_the_run_allowance(self):
        """Day 7: the gate must send the member back to /subscribe, and
        limits must go to zero so subscription_enforcer_tick pauses every
        daemon they own."""
        import billing_sync
        from entitlements import limits_for_user
        from routes_subscriptions import get_subscription_state
        uid = _mk_user()
        billing_sync.grant_trial(uid)
        past = _iso(datetime.now(timezone.utc) - timedelta(minutes=1))
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("UPDATE user_subscriptions SET expires_at = ? WHERE user_id = ?",
                        (past, uid))
            conn.commit()
        finally:
            conn.close()
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            state = get_subscription_state(cur, uid)   # lazy-expires the row
            limits = limits_for_user(cur, uid)
            conn.commit()
        finally:
            conn.close()
        self.assertNotEqual(state["status"], "active")
        self.assertEqual(int(limits["max_concurrent_runs"]), 0)
        self.assertEqual(int(limits["max_fleet_size"]), 0)
        self.assertFalse(limits["sms_allowed"])

    def test_paying_during_the_trial_supersedes_it(self):
        import billing_sync
        uid = _mk_user()
        billing_sync.grant_trial(uid)
        billing_sync.upsert_autorenew_subscription(
            provider="stripe", user_id=uid, plan_code="pro", external_id="sub_X")
        rows = _sub_rows(uid)
        self.assertEqual([r["status"] for r in rows], ["superseded", "active"])
        self.assertEqual(rows[1]["plan_code"], "pro")


class TrialNoticeTickTests(_DbCase):
    def setUp(self):
        super().setUp()
        import billing_sync
        self.uid = _mk_user("ko@t.dev", "ko")
        billing_sync.grant_trial(self.uid)

    def _set_expiry(self, delta: timedelta):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("UPDATE user_subscriptions SET expires_at = ? WHERE user_id = ?",
                        (_iso(datetime.now(timezone.utc) + delta), self.uid))
            conn.commit()
        finally:
            conn.close()

    def _tick(self, ok=True):
        import billing_sync
        with patch("email_sender.send_trial_notice_email", return_value=ok) as send:
            result = billing_sync.trial_notice_tick()
        return result, send

    def test_nothing_is_sent_early_in_the_trial(self):
        self._set_expiry(timedelta(days=6))
        result, send = self._tick()
        send.assert_not_called()
        self.assertEqual(result, {"reminded": 0, "ended": 0})

    def test_reminder_goes_out_on_day_four(self):
        self._set_expiry(timedelta(days=3) - timedelta(minutes=1))
        result, send = self._tick()
        self.assertEqual(result["reminded"], 1)
        self.assertEqual(send.call_args.kwargs["kind"], "reminder")
        self.assertEqual(send.call_args.kwargs["to_email"], "ko@t.dev")
        self.assertEqual(send.call_args.kwargs["lang"], "ko")

    def test_reminder_quotes_the_entry_price(self):
        self._set_expiry(timedelta(days=2))
        _, send = self._tick()
        self.assertEqual(float(send.call_args.kwargs["amount_usd"]), 60.0)

    def test_expiry_notice_goes_out_once_the_trial_has_lapsed(self):
        self._set_expiry(timedelta(minutes=-1))
        result, send = self._tick()
        self.assertEqual(result["ended"], 1)
        self.assertEqual(send.call_args.kwargs["kind"], "ended")

    def test_each_notice_is_sent_exactly_once(self):
        self._set_expiry(timedelta(days=2))
        self._tick()
        _, send = self._tick()
        send.assert_not_called()

    def test_reminder_and_expiry_are_separate_notices(self):
        """A member who got the day-4 reminder must still get told when the
        trial actually ends — the dedupe is per notice, not per trial."""
        self._set_expiry(timedelta(days=2))
        self._tick()
        self._set_expiry(timedelta(minutes=-1))
        result, send = self._tick()
        self.assertEqual(result["ended"], 1)
        self.assertEqual(send.call_args.kwargs["kind"], "ended")

    def test_failed_send_is_retried_on_the_next_tick(self):
        self._set_expiry(timedelta(days=2))
        result, _ = self._tick(ok=False)
        self.assertEqual(result["reminded"], 0)
        result, send = self._tick(ok=True)
        self.assertEqual(result["reminded"], 1)

    def test_long_lapsed_trials_are_not_mailed(self):
        """Guards the first run against existing data: a trial that ended
        months ago must not generate a 'your trial just ended' email."""
        self._set_expiry(timedelta(days=-90))
        result, send = self._tick()
        send.assert_not_called()
        self.assertEqual(result["ended"], 0)

    def test_paid_subscriptions_are_ignored(self):
        import billing_sync
        billing_sync.upsert_autorenew_subscription(
            provider="stripe", user_id=self.uid, plan_code="pro",
            external_id="sub_Y")
        self._set_expiry(timedelta(minutes=-1))  # only touches the trial row
        _, send = self._tick()
        # the trial row is 'superseded' now, so it is out of scope entirely
        send.assert_not_called()


class TrialCopyTests(unittest.TestCase):
    LANGS = ("en", "ko", "ja", "th", "vi", "id")
    KINDS = ("reminder", "ended")

    def test_every_kind_and_language_renders(self):
        from email_i18n import trial_email
        for kind in self.KINDS:
            for lang in self.LANGS:
                with self.subTest(kind=kind, lang=lang):
                    subject, html = trial_email(kind, lang, 60.0, "2026-08-12")
                    self.assertTrue(subject.strip())
                    self.assertIn("Sooppiy", html)
                    self.assertIn("2026-08-12", html)
                    self.assertIn("60", html)

    def test_no_unfilled_placeholders(self):
        from email_i18n import trial_email, trial_email_text
        for kind in self.KINDS:
            for lang in self.LANGS:
                with self.subTest(kind=kind, lang=lang):
                    subject, html = trial_email(kind, lang, 60.0, "2026-08-12")
                    text = trial_email_text(kind, lang, 60.0, "2026-08-12")
                    for blob in (subject, html, text):
                        self.assertNotIn("{", blob)

    def test_every_translation_keeps_both_placeholders(self):
        """Checked on the raw copy, not the rendered HTML, on purpose: the
        template also prints the price and date in their own box, so a
        translation that dropped '{date}' from its sentence still rendered a
        date somewhere and passed the output-level checks. Mutation testing
        caught exactly that."""
        from email_i18n import _TRIAL
        for kind in self.KINDS:
            for lang in self.LANGS:
                with self.subTest(kind=kind, lang=lang):
                    copy = _TRIAL[kind][lang]
                    self.assertIn("{date}", copy["body"])
                    self.assertIn("{amount}", copy["body"] + copy["note"])

    def test_every_supported_language_has_copy(self):
        from email_i18n import _TRIAL
        for kind in self.KINDS:
            self.assertEqual(set(_TRIAL[kind]), set(self.LANGS))

    def test_no_notice_claims_a_charge_will_be_taken(self):
        """The trial holds no payment method, so copy asserting that a card
        WILL be charged is false — and false billing copy is the exact thing
        the no-card design exists to avoid.

        Phrased as forbidden affirmative constructions rather than the bare
        word 'charged': the reminder legitimately says "nothing is charged
        automatically", which is the reassurance, not the claim.
        """
        from email_i18n import trial_email_text
        forbidden = ("will be charged", "is charged for", "we will charge",
                     "payment method is charged", "your card is charged",
                     "renews automatically")
        for kind in self.KINDS:
            text = trial_email_text(kind, "en", 60.0, "2026-08-12").lower()
            for phrase in forbidden:
                with self.subTest(kind=kind, phrase=phrase):
                    self.assertNotIn(phrase, text)

    def test_reminder_says_nothing_is_charged_automatically(self):
        from email_i18n import trial_email_text
        text = trial_email_text("reminder", "en", 60.0, "2026-08-12").lower()
        self.assertIn("nothing is charged automatically", text)

    def test_reminder_tells_the_member_how_to_keep_access(self):
        from email_i18n import trial_email_text
        text = trial_email_text("reminder", "en", 60.0, "2026-08-12").lower()
        self.assertIn("choose a plan", text)

    def test_ended_notice_says_automation_stopped(self):
        from email_i18n import trial_email_text
        text = trial_email_text("ended", "en", 60.0, "2026-08-12").lower()
        self.assertIn("stopped", text)

    def test_unknown_language_falls_back_to_english(self):
        from email_i18n import trial_email
        self.assertEqual(trial_email("reminder", "xx", 60.0, "2026-08-12"),
                         trial_email("reminder", "en", 60.0, "2026-08-12"))

    def test_unknown_kind_falls_back_to_the_reminder(self):
        from email_i18n import trial_email
        self.assertEqual(trial_email("nope", "en", 60.0, "2026-08-12"),
                         trial_email("reminder", "en", 60.0, "2026-08-12"))


class TrialGrantedAtSignupTests(_DbCase):
    def test_email_signup_starts_the_trial(self):
        from fastapi.testclient import TestClient
        from routes import create_app
        client = TestClient(create_app())
        stored = {"code": "123456", "attempts": 0,
                  "expires_at": datetime.now(timezone.utc) + timedelta(minutes=5)}
        with patch("routes_users.send_welcome_email", return_value=True), \
             patch("routes_users._load_code", return_value=stored), \
             patch("routes_users._delete_code"):
            r = client.post("/api/users/register",
                            json={"email": "new@t.dev", "password": "pw123456",
                                  "code": "123456"})
        self.assertEqual(r.status_code, 200, r.text)
        rows = _sub_rows(int(r.json()["user_id"]))
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["method"], rows[0]["status"], rows[0]["plan_code"]),
                         ("trial", "active", "junior"))


if __name__ == "__main__":
    unittest.main()
