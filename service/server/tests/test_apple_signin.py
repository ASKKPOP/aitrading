"""Apple Sign In — config gate, client secret, identity mapping, handoff.

Every network call is patched. Apple's endpoints are never contacted: a test
that reaches appleid.apple.com is a test that fails in CI and lies locally.
"""
import base64
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

import database
import routes_oauth
from database import get_db_connection
from routes_oauth import (
    _apple_client_secret,
    _apple_configured,
    _apple_display_name,
    _apple_private_key,
    _consume_handoff,
    _find_or_create_user_from_apple,
    _provider_state,
    _store_handoff,
)

APPLE_ENV = {
    "APPLE_TEAM_ID": "TEAM123456",
    "APPLE_CLIENT_ID": "com.sooppiy.web",
    "APPLE_KEY_ID": "KEY7890123",
    "APPLE_REDIRECT_URI": "https://sooppiy.com/api/auth/apple/callback",
}


def _test_p8() -> str:
    """A throwaway EC P-256 key in PKCS#8 PEM — the shape Apple hands out."""
    key = ec.generate_private_key(ec.SECP256R1())
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()


class AppleConfigTests(unittest.TestCase):
    """The provider flag must be all-or-nothing: a half-set env is off."""

    def test_unconfigured_reports_false(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(_apple_configured())
            self.assertFalse(_provider_state()["apple"])

    def test_fully_configured_reports_true(self) -> None:
        with patch.dict(os.environ, {**APPLE_ENV, "APPLE_PRIVATE_KEY": _test_p8()}, clear=True):
            self.assertTrue(_apple_configured())
            self.assertTrue(_provider_state()["apple"])

    def test_each_missing_var_disables_it(self) -> None:
        full = {**APPLE_ENV, "APPLE_PRIVATE_KEY": _test_p8()}
        for missing in full:
            partial = {k: v for k, v in full.items() if k != missing}
            with patch.dict(os.environ, partial, clear=True):
                self.assertFalse(
                    _apple_configured(),
                    f"apple reported configured while {missing} was missing")

    def test_blank_var_counts_as_missing(self) -> None:
        with patch.dict(os.environ, {**APPLE_ENV, "APPLE_TEAM_ID": "   ",
                                     "APPLE_PRIVATE_KEY": _test_p8()}, clear=True):
            self.assertFalse(_apple_configured())


class ApplePrivateKeyTests(unittest.TestCase):
    """The .p8 is multi-line and .env is not — both encodings must work."""

    def test_escaped_newlines_are_restored(self) -> None:
        pem = _test_p8()
        with patch.dict(os.environ, {"APPLE_PRIVATE_KEY": pem.replace("\n", "\\n")}, clear=True):
            self.assertEqual(_apple_private_key().strip(), pem.strip())

    def test_literal_multiline_passes_through(self) -> None:
        pem = _test_p8()
        with patch.dict(os.environ, {"APPLE_PRIVATE_KEY": pem}, clear=True):
            self.assertEqual(_apple_private_key().strip(), pem.strip())

    def test_base64_form_is_decoded(self) -> None:
        pem = _test_p8()
        encoded = base64.b64encode(pem.encode()).decode()
        with patch.dict(os.environ, {"APPLE_PRIVATE_KEY_B64": encoded}, clear=True):
            self.assertEqual(_apple_private_key().strip(), pem.strip())

    def test_garbage_base64_is_empty_not_an_exception(self) -> None:
        with patch.dict(os.environ, {"APPLE_PRIVATE_KEY_B64": "not-base64!!"}, clear=True):
            self.assertEqual(_apple_private_key(), "")


class AppleClientSecretTests(unittest.TestCase):
    """The client secret is a JWT we sign — verify its claims, not just that
    it is a string. Apple rejects a wrong iss/sub/aud silently as 'invalid
    client', which is unreadable from the outside."""

    def setUp(self) -> None:
        self.pem = _test_p8()
        self.env = patch.dict(os.environ, {**APPLE_ENV, "APPLE_PRIVATE_KEY": self.pem}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)

    def _public_key(self):
        return serialization.load_pem_private_key(self.pem.encode(), password=None).public_key()

    def test_claims_match_apple_spec(self) -> None:
        token = _apple_client_secret()
        claims = jwt.decode(token, self._public_key(), algorithms=["ES256"],
                            audience="https://appleid.apple.com")
        self.assertEqual(claims["iss"], APPLE_ENV["APPLE_TEAM_ID"])
        self.assertEqual(claims["sub"], APPLE_ENV["APPLE_CLIENT_ID"])
        self.assertEqual(claims["aud"], "https://appleid.apple.com")

    def test_header_carries_key_id_and_es256(self) -> None:
        header = jwt.get_unverified_header(_apple_client_secret())
        self.assertEqual(header["kid"], APPLE_ENV["APPLE_KEY_ID"])
        self.assertEqual(header["alg"], "ES256")

    def test_expiry_is_short_and_inside_apples_six_month_cap(self) -> None:
        claims = jwt.decode(_apple_client_secret(), self._public_key(),
                            algorithms=["ES256"], audience="https://appleid.apple.com")
        life = claims["exp"] - claims["iat"]
        self.assertGreater(life, 0)
        # 6 months is Apple's hard ceiling; ours is minted per request so it
        # should be minutes. A long-lived secret here would expire silently
        # months later with no deploy to blame.
        self.assertLessEqual(life, 900)
        self.assertGreater(claims["exp"], int(time.time()))


class AppleDisplayNameTests(unittest.TestCase):
    """Apple sends the name once, ever. Parsing must never raise — a crash
    here would turn a first-ever sign-in into a 500."""

    def test_full_name(self) -> None:
        blob = json.dumps({"name": {"firstName": "Ada", "lastName": "Lovelace"}})
        self.assertEqual(_apple_display_name(blob), "Ada Lovelace")

    def test_first_name_only(self) -> None:
        self.assertEqual(
            _apple_display_name(json.dumps({"name": {"firstName": "Ada"}})), "Ada")

    def test_absent_or_malformed_is_empty(self) -> None:
        for bad in ("", "{not json", json.dumps({}), json.dumps({"name": None}),
                    json.dumps({"name": "Ada"}), json.dumps({"name": {}})):
            self.assertEqual(_apple_display_name(bad), "", f"input={bad!r}")


class AppleIdentityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()

    def test_new_user_is_created_and_linked(self) -> None:
        user_id, created = _find_or_create_user_from_apple(
            "apple-sub-1", "ada@example.com", "Ada Lovelace", "ko")
        self.assertTrue(created)
        conn = get_db_connection()
        row = conn.execute(
            "SELECT provider, email, display_name FROM oauth_identities WHERE user_id=?",
            (user_id,)).fetchone()
        user = conn.execute("SELECT email, lang FROM users WHERE id=?", (user_id,)).fetchone()
        conn.close()
        self.assertEqual(row["provider"], "apple")
        self.assertEqual(row["display_name"], "Ada Lovelace")
        self.assertEqual(user["email"], "ada@example.com")
        self.assertEqual(user["lang"], "ko")

    def test_same_sub_returns_same_user_and_does_not_recreate(self) -> None:
        first, created_1 = _find_or_create_user_from_apple("sub-repeat", "a@example.com")
        second, created_2 = _find_or_create_user_from_apple("sub-repeat", "a@example.com")
        self.assertEqual(first, second)
        self.assertTrue(created_1)
        self.assertFalse(created_2)
        conn = get_db_connection()
        count = conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
        conn.close()
        self.assertEqual(count, 1)

    def test_second_signin_without_name_keeps_the_first_one(self) -> None:
        """Apple omits the name on every sign-in after the first. The stored
        name must survive that, or it is lost permanently."""
        user_id, _ = _find_or_create_user_from_apple("sub-name", "n@example.com", "Grace Hopper")
        _find_or_create_user_from_apple("sub-name", "n@example.com", "")
        conn = get_db_connection()
        row = conn.execute(
            "SELECT display_name FROM oauth_identities WHERE provider='apple' "
            "AND provider_user_id=?", ("sub-name",)).fetchone()
        conn.close()
        self.assertEqual(row["display_name"], "Grace Hopper")

    def test_a_later_name_does_not_overwrite_the_stored_one(self) -> None:
        """Once captured, the name is kept. Re-authorizing (the only way Apple
        ever re-sends it) must not silently rewrite stored personal data."""
        _find_or_create_user_from_apple("sub-rename", "r@example.com", "Grace Hopper")
        _find_or_create_user_from_apple("sub-rename", "r@example.com", "Someone Else")
        conn = get_db_connection()
        row = conn.execute(
            "SELECT display_name FROM oauth_identities WHERE provider='apple' "
            "AND provider_user_id=?", ("sub-rename",)).fetchone()
        conn.close()
        self.assertEqual(row["display_name"], "Grace Hopper")

    def test_name_backfills_when_first_capture_was_empty(self) -> None:
        _find_or_create_user_from_apple("sub-late", "l@example.com", "")
        _find_or_create_user_from_apple("sub-late", "l@example.com", "Alan Turing")
        conn = get_db_connection()
        row = conn.execute(
            "SELECT display_name FROM oauth_identities WHERE provider='apple' "
            "AND provider_user_id=?", ("sub-late",)).fetchone()
        conn.close()
        self.assertEqual(row["display_name"], "Alan Turing")

    def test_existing_email_account_is_linked_not_duplicated(self) -> None:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO users (email, password_hash, points, lang) VALUES (?, ?, 0, ?)",
            ("existing@example.com", "hash", "ja"))
        existing_id = int(cur.lastrowid)
        conn.commit()
        conn.close()

        user_id, created = _find_or_create_user_from_apple(
            "sub-link", "existing@example.com", "", "ko")
        self.assertEqual(user_id, existing_id)
        self.assertFalse(created)
        conn = get_db_connection()
        # the pre-existing account keeps its language
        lang = conn.execute("SELECT lang FROM users WHERE id=?", (existing_id,)).fetchone()["lang"]
        count = conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
        conn.close()
        self.assertEqual(lang, "ja")
        self.assertEqual(count, 1)

    def test_private_relay_address_creates_its_own_account(self) -> None:
        """A Hide-My-Email user cannot match an existing real address, so they
        must get their own account rather than being merged into someone."""
        _find_or_create_user_from_apple("sub-real", "real@example.com")
        relay_id, created = _find_or_create_user_from_apple(
            "sub-relay", "xyz@privaterelay.appleid.com")
        self.assertTrue(created)
        conn = get_db_connection()
        count = conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
        conn.close()
        self.assertEqual(count, 2)
        self.assertIsNotNone(relay_id)

    def test_missing_sub_is_rejected(self) -> None:
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as ctx:
            _find_or_create_user_from_apple("", "x@example.com")
        self.assertEqual(ctx.exception.status_code, 502)

    def test_link_to_deleted_user_does_not_mint_a_ghost_session(self) -> None:
        """A stale identity row whose user was deleted must not resolve — it
        would hand back a user_id that every authed endpoint then 401s on."""
        user_id, _ = _find_or_create_user_from_apple("sub-ghost", "ghost@example.com")
        conn = get_db_connection()
        conn.execute("DELETE FROM users WHERE id=?", (user_id,))
        conn.commit()
        conn.close()

        new_id, created = _find_or_create_user_from_apple("sub-ghost", "ghost@example.com")
        self.assertTrue(created)
        self.assertNotEqual(new_id, user_id)


class AppleHandoffTests(unittest.TestCase):
    """The handoff nonce exists so the session token never rides in a URL."""

    def setUp(self) -> None:
        routes_oauth._inproc_handoffs.clear()
        # Force the in-process path; a configured Redis would make this test
        # depend on an external service.
        patcher = patch("routes_oauth._cache_set", return_value=False)
        patcher.start()
        self.addCleanup(patcher.stop)
        get_patcher = patch("routes_oauth._cache_get", return_value=None)
        get_patcher.start()
        self.addCleanup(get_patcher.stop)

    def test_round_trip_returns_the_payload(self) -> None:
        nonce = _store_handoff({"token": "sess-abc", "user_id": 7,
                                "email": "a@example.com", "created": True})
        payload = _consume_handoff(nonce)
        self.assertEqual(payload["token"], "sess-abc")
        self.assertEqual(payload["user_id"], 7)

    def test_nonce_is_single_use(self) -> None:
        nonce = _store_handoff({"token": "sess-once"})
        self.assertIsNotNone(_consume_handoff(nonce))
        self.assertIsNone(_consume_handoff(nonce), "handoff was redeemable twice")

    def test_unknown_nonce_returns_none(self) -> None:
        self.assertIsNone(_consume_handoff("never-issued"))

    def test_expired_nonce_is_rejected(self) -> None:
        from datetime import datetime, timedelta, timezone
        nonce = _store_handoff({"token": "sess-old"})
        routes_oauth._inproc_handoffs[nonce]["expires_at"] = (
            datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        self.assertIsNone(_consume_handoff(nonce))

    def test_nonce_is_not_guessable(self) -> None:
        nonces = {_store_handoff({"token": f"s{i}"}) for i in range(50)}
        self.assertEqual(len(nonces), 50)
        self.assertTrue(all(len(n) >= 24 for n in nonces))


class AppleRouteTests(unittest.TestCase):
    """End-to-end through the real ASGI app, with Apple's network stubbed.

    Unit tests cannot catch a route that was never registered, a form body
    parsed wrongly, or a redirect pointing at the wrong place — which is
    precisely the wiring that makes or breaks this feature.
    """

    def setUp(self) -> None:
        from fastapi.testclient import TestClient
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        routes_oauth._inproc_handoffs.clear()
        routes_oauth._inproc_oauth_states.clear()

        env = patch.dict(os.environ, {**APPLE_ENV, "APPLE_PRIVATE_KEY": _test_p8()})
        env.start()
        self.addCleanup(env.stop)

        from routes import create_app
        self.client = TestClient(create_app(), follow_redirects=False)

    def test_providers_endpoint_reports_apple_enabled(self) -> None:
        body = self.client.get("/api/auth/providers").json()
        self.assertTrue(body["providers"]["apple"])

    def test_start_redirects_to_apple_with_form_post(self) -> None:
        r = self.client.get("/api/auth/apple/start")
        self.assertEqual(r.status_code, 302)
        location = r.headers["location"]
        self.assertTrue(location.startswith("https://appleid.apple.com/auth/authorize"))
        # form_post is mandatory with a name/email scope — without it Apple
        # sends a GET and the name is never delivered at all.
        self.assertIn("response_mode=form_post", location)
        self.assertIn("scope=name+email", location)
        self.assertIn(f"client_id={APPLE_ENV['APPLE_CLIENT_ID']}", location)

    def test_start_is_503_when_unconfigured(self) -> None:
        with patch.dict(os.environ, {"APPLE_TEAM_ID": ""}):
            self.assertEqual(self.client.get("/api/auth/apple/start").status_code, 503)

    def _start_and_get_state(self) -> str:
        from urllib.parse import parse_qs, urlparse
        location = self.client.get("/api/auth/apple/start").headers["location"]
        return parse_qs(urlparse(location).query)["state"][0]

    def test_full_callback_posts_form_and_hands_off_a_session(self) -> None:
        state = self._start_and_get_state()
        claims = {"sub": "apple-e2e", "email": "e2e@example.com"}
        with patch("routes_oauth._exchange_apple_code", return_value={"id_token": "stub"}), \
             patch("routes_oauth._verify_apple_id_token", return_value=claims), \
             patch("routes_oauth._grant_signup_side_effects") as side_effects:
            r = self.client.post(
                "/api/auth/apple/callback",
                data={"code": "auth-code", "state": state,
                      "user": json.dumps({"name": {"firstName": "Ada", "lastName": "L"}})},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        self.assertEqual(r.status_code, 303)
        location = r.headers["location"]
        self.assertTrue(location.startswith("/auth/apple/callback?handoff="))
        # The session token must never appear in the redirect URL.
        self.assertNotIn("token=", location)
        side_effects.assert_awaited_once()

        handoff = location.split("handoff=", 1)[1]
        session = self.client.post("/api/auth/apple/session", json={"handoff": handoff})
        self.assertEqual(session.status_code, 200)
        body = session.json()
        self.assertTrue(body["token"])
        self.assertTrue(body["created"])
        self.assertEqual(body["email"], "e2e@example.com")

        # and the name Apple sent once actually landed
        conn = get_db_connection()
        row = conn.execute(
            "SELECT display_name FROM oauth_identities WHERE provider_user_id=?",
            ("apple-e2e",)).fetchone()
        conn.close()
        self.assertEqual(row["display_name"], "Ada L")

    def test_handoff_cannot_be_redeemed_twice_over_http(self) -> None:
        state = self._start_and_get_state()
        with patch("routes_oauth._exchange_apple_code", return_value={"id_token": "stub"}), \
             patch("routes_oauth._verify_apple_id_token",
                   return_value={"sub": "apple-twice", "email": "t@example.com"}), \
             patch("routes_oauth._grant_signup_side_effects"):
            r = self.client.post(
                "/api/auth/apple/callback",
                data={"code": "c", "state": state},
                headers={"Content-Type": "application/x-www-form-urlencoded"})
        handoff = r.headers["location"].split("handoff=", 1)[1]
        self.assertEqual(self.client.post("/api/auth/apple/session",
                                          json={"handoff": handoff}).status_code, 200)
        self.assertEqual(self.client.post("/api/auth/apple/session",
                                          json={"handoff": handoff}).status_code, 400)

    def test_replayed_state_is_rejected(self) -> None:
        state = self._start_and_get_state()
        with patch("routes_oauth._exchange_apple_code", return_value={"id_token": "stub"}), \
             patch("routes_oauth._verify_apple_id_token",
                   return_value={"sub": "apple-replay", "email": "r@example.com"}), \
             patch("routes_oauth._grant_signup_side_effects"):
            first = self.client.post(
                "/api/auth/apple/callback", data={"code": "c", "state": state},
                headers={"Content-Type": "application/x-www-form-urlencoded"})
            self.assertEqual(first.status_code, 303)
            replay = self.client.post(
                "/api/auth/apple/callback", data={"code": "c", "state": state},
                headers={"Content-Type": "application/x-www-form-urlencoded"})
        self.assertEqual(replay.status_code, 400)

    def test_unknown_state_is_rejected(self) -> None:
        r = self.client.post(
            "/api/auth/apple/callback", data={"code": "c", "state": "forged"},
            headers={"Content-Type": "application/x-www-form-urlencoded"})
        self.assertEqual(r.status_code, 400)

    def test_user_cancelled_redirects_instead_of_erroring(self) -> None:
        r = self.client.post(
            "/api/auth/apple/callback", data={"error": "user_cancelled_authorize"},
            headers={"Content-Type": "application/x-www-form-urlencoded"})
        self.assertEqual(r.status_code, 303)
        self.assertIn("apple_error=denied", r.headers["location"])

    def test_second_signin_reuses_the_account(self) -> None:
        claims = {"sub": "apple-same", "email": "same@example.com"}
        ids = []
        for _ in range(2):
            state = self._start_and_get_state()
            with patch("routes_oauth._exchange_apple_code", return_value={"id_token": "stub"}), \
                 patch("routes_oauth._verify_apple_id_token", return_value=claims), \
                 patch("routes_oauth._grant_signup_side_effects"):
                r = self.client.post(
                    "/api/auth/apple/callback", data={"code": "c", "state": state},
                    headers={"Content-Type": "application/x-www-form-urlencoded"})
            handoff = r.headers["location"].split("handoff=", 1)[1]
            ids.append(self.client.post("/api/auth/apple/session",
                                        json={"handoff": handoff}).json())
        self.assertEqual(ids[0]["user_id"], ids[1]["user_id"])
        self.assertTrue(ids[0]["created"])
        self.assertFalse(ids[1]["created"], "second sign-in re-created the account")


if __name__ == "__main__":
    unittest.main()
