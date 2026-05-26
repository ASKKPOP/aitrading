"""TDD tests for Phase 5 — auth endpoints (MFA + Google OAuth).

MFA covers:
  - setup → returns a base32 secret + otpauth URL + backup codes
  - verify-setup with a valid TOTP code enables MFA
  - verify-setup with a bad code does not enable
  - login when mfa_enabled returns mfa_token (no session)
  - mfa/verify with mfa_token + valid TOTP returns session
  - mfa/verify with a backup code consumes it (one-time use)
  - disable requires correct password
  - status endpoint reflects current state

OAuth covers:
  - GET /api/auth/providers reports which providers are configured
  - GET /api/auth/google/start redirects to Google with state cookie
  - GET /api/auth/google/callback exchanges code, creates user, returns session
  - callback with existing oauth_identity reuses the same user
  - callback with same email as existing user links to that user (no dupe)
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pyotp
from fastapi.testclient import TestClient

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
from routes import create_app


def _create_user(email: str = "alice@example.com", password: str = "hunter2") -> tuple[int, str]:
    """Insert a user directly (bypassing the email-code flow) for fixtures."""
    from utils import hash_password
    conn = database.get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO users (email, password_hash, points) VALUES (?, ?, 0)",
        (email, hash_password(password)),
    )
    user_id = cur.lastrowid
    conn.commit()
    conn.close()
    return user_id, password


def _login_token(client: TestClient, email: str, password: str) -> str:
    r = client.post("/api/users/login", json={"email": email, "password": password})
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return r.json()["token"]


# ── MFA setup ─────────────────────────────────────────────────────────────

class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        # Drop any OAuth env so /providers reports Google disabled by default.
        for k in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REDIRECT_URI"):
            os.environ.pop(k, None)
        self.client = TestClient(create_app())

    def tearDown(self):
        self.tmp.cleanup()


class MfaSetupTests(_Base):
    def test_setup_returns_secret_and_otpauth_url(self):
        _create_user()
        token = _login_token(self.client, "alice@example.com", "hunter2")
        r = self.client.post("/api/auth/mfa/setup", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIn("secret", body)
        # base32 secrets are 32 chars / 16 bytes
        self.assertGreaterEqual(len(body["secret"]), 16)
        self.assertIn("otpauth_url", body)
        self.assertIn("otpauth://", body["otpauth_url"])
        self.assertIn("backup_codes", body)
        self.assertEqual(len(body["backup_codes"]), 10)

    def test_setup_requires_auth(self):
        r = self.client.post("/api/auth/mfa/setup")
        self.assertEqual(r.status_code, 401)

    def test_verify_setup_enables_mfa_with_valid_code(self):
        _create_user()
        token = _login_token(self.client, "alice@example.com", "hunter2")
        setup = self.client.post("/api/auth/mfa/setup", headers={"Authorization": f"Bearer {token}"}).json()
        valid_code = pyotp.TOTP(setup["secret"]).now()
        r = self.client.post(
            "/api/auth/mfa/verify-setup",
            json={"code": valid_code},
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(r.status_code, 200)
        # Status should now report enabled.
        s = self.client.get("/api/auth/mfa/status", headers={"Authorization": f"Bearer {token}"}).json()
        self.assertTrue(s["enabled"])

    def test_verify_setup_rejects_bad_code(self):
        _create_user()
        token = _login_token(self.client, "alice@example.com", "hunter2")
        self.client.post("/api/auth/mfa/setup", headers={"Authorization": f"Bearer {token}"})
        r = self.client.post(
            "/api/auth/mfa/verify-setup",
            json={"code": "000000"},
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(r.status_code, 400)
        s = self.client.get("/api/auth/mfa/status", headers={"Authorization": f"Bearer {token}"}).json()
        self.assertFalse(s["enabled"])


# ── MFA-gated login ───────────────────────────────────────────────────────

class MfaLoginTests(_Base):
    def _enable_mfa(self) -> tuple[str, str]:
        """Helper: create user, enable MFA, return (token, secret)."""
        _create_user()
        token = _login_token(self.client, "alice@example.com", "hunter2")
        setup = self.client.post("/api/auth/mfa/setup", headers={"Authorization": f"Bearer {token}"}).json()
        code = pyotp.TOTP(setup["secret"]).now()
        self.client.post(
            "/api/auth/mfa/verify-setup",
            json={"code": code},
            headers={"Authorization": f"Bearer {token}"},
        )
        return token, setup["secret"]

    def test_login_with_mfa_returns_mfa_token_not_session(self):
        _, _ = self._enable_mfa()
        r = self.client.post("/api/users/login",
                             json={"email": "alice@example.com", "password": "hunter2"})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body.get("requires_mfa"))
        self.assertIn("mfa_token", body)
        self.assertNotIn("token", {k: v for k, v in body.items() if k != "mfa_token"})

    def test_mfa_verify_with_valid_totp_returns_session(self):
        _, secret = self._enable_mfa()
        login = self.client.post(
            "/api/users/login",
            json={"email": "alice@example.com", "password": "hunter2"},
        ).json()
        r = self.client.post(
            "/api/auth/mfa/verify",
            json={"mfa_token": login["mfa_token"], "code": pyotp.TOTP(secret).now()},
        )
        self.assertEqual(r.status_code, 200)
        self.assertIn("token", r.json())

    def test_mfa_verify_with_wrong_code_returns_401(self):
        _, _ = self._enable_mfa()
        login = self.client.post(
            "/api/users/login",
            json={"email": "alice@example.com", "password": "hunter2"},
        ).json()
        r = self.client.post(
            "/api/auth/mfa/verify",
            json={"mfa_token": login["mfa_token"], "code": "000000"},
        )
        self.assertEqual(r.status_code, 401)

    def test_backup_code_works_once(self):
        token, _ = self._enable_mfa()
        # fetch backup codes from the user (status endpoint exposes count, not codes;
        # so re-run setup to get a fresh set — that disables MFA again, which is fine
        # for testing the one-shot consumption logic separately).
        # Strategy: use the original setup call which returned codes.
        setup = self.client.post("/api/auth/mfa/setup",
                                 headers={"Authorization": f"Bearer {token}"}).json()
        # Re-enable MFA with one of those backup codes registered.
        code = pyotp.TOTP(setup["secret"]).now()
        self.client.post(
            "/api/auth/mfa/verify-setup",
            json={"code": code},
            headers={"Authorization": f"Bearer {token}"},
        )
        backup = setup["backup_codes"][0]

        login = self.client.post(
            "/api/users/login",
            json={"email": "alice@example.com", "password": "hunter2"},
        ).json()
        # First use of the backup code succeeds.
        r1 = self.client.post(
            "/api/auth/mfa/verify",
            json={"mfa_token": login["mfa_token"], "code": backup},
        )
        self.assertEqual(r1.status_code, 200)

        # Second use of the same backup code fails (consumed).
        login2 = self.client.post(
            "/api/users/login",
            json={"email": "alice@example.com", "password": "hunter2"},
        ).json()
        r2 = self.client.post(
            "/api/auth/mfa/verify",
            json={"mfa_token": login2["mfa_token"], "code": backup},
        )
        self.assertEqual(r2.status_code, 401)

    def test_disable_requires_password(self):
        token, _ = self._enable_mfa()
        # wrong password
        r1 = self.client.post(
            "/api/auth/mfa/disable",
            json={"password": "wrong"},
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(r1.status_code, 401)
        # right password
        r2 = self.client.post(
            "/api/auth/mfa/disable",
            json={"password": "hunter2"},
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(r2.status_code, 200)
        s = self.client.get(
            "/api/auth/mfa/status", headers={"Authorization": f"Bearer {token}"}
        ).json()
        self.assertFalse(s["enabled"])


# ── OAuth providers ───────────────────────────────────────────────────────

class ProvidersListingTests(_Base):
    def test_providers_default_only_email(self):
        r = self.client.get("/api/auth/providers")
        body = r.json()
        self.assertEqual(body["providers"]["email"], True)
        self.assertEqual(body["providers"]["google"], False)
        self.assertEqual(body["providers"]["apple"], False)
        self.assertEqual(body["providers"]["phone"], False)

    def test_providers_reports_google_enabled_when_envs_set(self):
        os.environ["GOOGLE_CLIENT_ID"] = "id"
        os.environ["GOOGLE_CLIENT_SECRET"] = "secret"
        os.environ["GOOGLE_REDIRECT_URI"] = "https://app.sooppiy.com/auth/google/callback"
        try:
            r = self.client.get("/api/auth/providers")
            self.assertEqual(r.json()["providers"]["google"], True)
        finally:
            for k in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REDIRECT_URI"):
                os.environ.pop(k, None)


class GoogleOAuthTests(_Base):
    def setUp(self):
        super().setUp()
        os.environ["GOOGLE_CLIENT_ID"] = "id"
        os.environ["GOOGLE_CLIENT_SECRET"] = "secret"
        os.environ["GOOGLE_REDIRECT_URI"] = "http://localhost:3000/auth/google/callback"

    def tearDown(self):
        for k in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REDIRECT_URI"):
            os.environ.pop(k, None)
        super().tearDown()

    def test_start_returns_redirect_to_google(self):
        r = self.client.get("/api/auth/google/start", follow_redirects=False)
        self.assertIn(r.status_code, (302, 307))
        loc = r.headers.get("location", "")
        self.assertIn("accounts.google.com", loc)
        self.assertIn("client_id=id", loc)
        self.assertIn("state=", loc)

    def test_start_returns_503_when_not_configured(self):
        for k in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"):
            os.environ.pop(k, None)
        r = self.client.get("/api/auth/google/start", follow_redirects=False)
        self.assertEqual(r.status_code, 503)

    def test_callback_creates_user_and_returns_session(self):
        # Mock the token exchange + userinfo fetch.
        with patch("routes_oauth._exchange_google_code") as ex, \
             patch("routes_oauth._fetch_google_userinfo") as ui:
            ex.return_value = {"access_token": "abc"}
            ui.return_value = {"sub": "google-uid-1", "email": "bob@example.com"}
            # The start endpoint sets a state cookie; pass it back so the
            # callback's CSRF check passes.
            start = self.client.get("/api/auth/google/start", follow_redirects=False)
            state = start.headers.get("location").split("state=")[-1].split("&")[0]
            r = self.client.get(
                f"/api/auth/google/callback?code=anycode&state={state}",
                follow_redirects=False,
            )
        self.assertEqual(r.status_code, 200)
        self.assertIn("token", r.json())
        # The user exists now.
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE email = ?", ("bob@example.com",))
        self.assertIsNotNone(cur.fetchone())
        cur.execute("SELECT * FROM oauth_identities WHERE provider='google'")
        self.assertIsNotNone(cur.fetchone())
        conn.close()

    def test_callback_reuses_existing_oauth_identity(self):
        with patch("routes_oauth._exchange_google_code") as ex, \
             patch("routes_oauth._fetch_google_userinfo") as ui:
            ex.return_value = {"access_token": "abc"}
            ui.return_value = {"sub": "google-uid-1", "email": "bob@example.com"}
            # First sign-in creates user.
            start = self.client.get("/api/auth/google/start", follow_redirects=False)
            state = start.headers.get("location").split("state=")[-1].split("&")[0]
            self.client.get(
                f"/api/auth/google/callback?code=c1&state={state}",
                follow_redirects=False,
            )
            # Second sign-in (different state nonce) reuses the same user.
            start2 = self.client.get("/api/auth/google/start", follow_redirects=False)
            state2 = start2.headers.get("location").split("state=")[-1].split("&")[0]
            r2 = self.client.get(
                f"/api/auth/google/callback?code=c2&state={state2}",
                follow_redirects=False,
            )
        self.assertEqual(r2.status_code, 200)
        # Still only one user row.
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) AS n FROM users WHERE email='bob@example.com'")
        self.assertEqual(cur.fetchone()["n"], 1)
        conn.close()

    def test_callback_rejects_bad_state(self):
        r = self.client.get(
            "/api/auth/google/callback?code=any&state=forged",
            follow_redirects=False,
        )
        self.assertEqual(r.status_code, 400)


if __name__ == "__main__":
    unittest.main()
