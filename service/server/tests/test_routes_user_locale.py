"""The locale endpoints — first-run prompt and settings (2026-07-28).

The member is ASKED for region and language on first sign-in, and can change
both at any time. Geolocation only pre-selects; nothing is applied to the
account until the member answers.

The invariant under test everywhere here: an unplaceable member stays
`region = null`. The API must refuse a region it does not serve rather than
substitute one, because a silently-substituted jurisdiction is a regulatory
failure, not a cosmetic one.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
import regions
from routes import create_app


def _create_user(email="alice@example.com", password="hunter2",
                 lang="en", geo=None):
    from utils import hash_password
    conn = database.get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO users (email, password_hash, points, lang, "
                "geo_country) VALUES (?, ?, 0, ?, ?)",
                (email, hash_password(password), lang, geo))
    uid = cur.lastrowid
    conn.commit(); conn.close()
    return uid


class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "t.db")
        database.init_database()
        self.client = TestClient(create_app())

    def tearDown(self):
        self.tmp.cleanup()

    def _token(self, email="alice@example.com", password="hunter2"):
        r = self.client.post("/api/users/login",
                             json={"email": email, "password": password})
        assert r.status_code == 200, r.text
        return r.json()["token"]

    def _auth(self, token):
        return {"Authorization": f"Bearer {token}"}


class FirstRunPrompt(_Base):

    def test_a_new_member_is_flagged_as_unconfirmed(self):
        """This flag is the whole trigger for the prompt."""
        _create_user(geo="KR")
        me = self.client.get("/api/users/me",
                             headers=self._auth(self._token())).json()
        self.assertFalse(me["locale_confirmed"])
        self.assertIsNone(me["region"])
        self.assertIsNone(me["timezone"])

    def test_the_geo_guess_only_preselects(self):
        _create_user(geo="KR")
        o = self.client.get("/api/users/locale/options",
                            headers=self._auth(self._token())).json()
        self.assertEqual(o["suggested_region"], "KR")   # pre-select
        self.assertIsNone(o["region"])                  # but not applied
        self.assertFalse(o["locale_confirmed"])

    def test_a_geo_country_we_do_not_serve_suggests_nothing(self):
        """Better an empty picker than a wrong jurisdiction pre-selected."""
        _create_user(geo="DE")
        o = self.client.get("/api/users/locale/options",
                            headers=self._auth(self._token())).json()
        self.assertIsNone(o["suggested_region"])

    def test_the_picker_is_in_the_members_language(self):
        _create_user(lang="ko")
        o = self.client.get("/api/users/locale/options",
                            headers=self._auth(self._token())).json()
        names = {r["region"]: r["name"] for r in o["regions"]}
        self.assertEqual(names["KR"], "대한민국")
        # Derived, not a literal — adding a region should extend this test's
        # coverage rather than break it.
        self.assertEqual(set(names), set(regions.supported_regions()))
        self.assertTrue(all(names.values()))

    def test_answering_clears_the_prompt(self):
        _create_user(geo="KR")
        tok = self._token()
        r = self.client.put("/api/users/locale", headers=self._auth(tok),
                            json={"region": "KR", "lang": "ko"})
        self.assertEqual(r.status_code, 200, r.text)
        me = self.client.get("/api/users/me", headers=self._auth(tok)).json()
        self.assertTrue(me["locale_confirmed"])
        self.assertEqual(me["region"], "KR")
        self.assertEqual(me["timezone"], "Asia/Seoul")
        self.assertEqual(me["lang"], "ko")


class Changing(_Base):

    def test_a_member_can_change_region_at_any_time(self):
        _create_user()
        tok = self._token()
        self.client.put("/api/users/locale", headers=self._auth(tok),
                        json={"region": "KR", "lang": "ko"})
        r = self.client.put("/api/users/locale", headers=self._auth(tok),
                            json={"region": "SG", "lang": "en"})
        self.assertEqual(r.status_code, 200)
        me = self.client.get("/api/users/me", headers=self._auth(tok)).json()
        self.assertEqual(me["region"], "SG")
        self.assertEqual(me["timezone"], "Asia/Singapore")

    def test_language_stays_independent_of_region(self):
        """A Korean speaker in Singapore. If this case cannot be expressed,
        the two fields have been collapsed into one and the model is wrong."""
        _create_user()
        tok = self._token()
        self.client.put("/api/users/locale", headers=self._auth(tok),
                        json={"region": "SG", "lang": "ko"})
        me = self.client.get("/api/users/me", headers=self._auth(tok)).json()
        self.assertEqual((me["region"], me["lang"]), ("SG", "ko"))

    def test_timezone_can_differ_from_the_region_default(self):
        """Members travel; their clock should follow them."""
        _create_user()
        tok = self._token()
        self.client.put("/api/users/locale", headers=self._auth(tok),
                        json={"region": "KR", "lang": "ko",
                              "timezone": "Europe/Berlin"})
        me = self.client.get("/api/users/me", headers=self._auth(tok)).json()
        self.assertEqual(me["region"], "KR")
        self.assertEqual(me["timezone"], "Europe/Berlin")

    def test_omitting_the_language_takes_the_regions_default(self):
        _create_user(lang="en")
        tok = self._token()
        self.client.put("/api/users/locale", headers=self._auth(tok),
                        json={"region": "JP"})
        me = self.client.get("/api/users/me", headers=self._auth(tok)).json()
        self.assertEqual(me["lang"], "ja")

    def test_a_bad_timezone_falls_back_to_the_region_default(self):
        _create_user()
        tok = self._token()
        self.client.put("/api/users/locale", headers=self._auth(tok),
                        json={"region": "TH", "timezone": "Mars/Olympus"})
        me = self.client.get("/api/users/me", headers=self._auth(tok)).json()
        self.assertEqual(me["timezone"], "Asia/Bangkok")


class RefusesRatherThanGuesses(_Base):

    def test_an_unserved_region_is_rejected(self):
        _create_user()
        tok = self._token()
        for bad in ("DE", "XX", "", "united states"):
            r = self.client.put("/api/users/locale", headers=self._auth(tok),
                                json={"region": bad})
            self.assertEqual(r.status_code, 400, f"{bad!r} -> {r.status_code}")

    def test_a_rejected_answer_leaves_the_account_untouched(self):
        """A 400 that still half-wrote the row would be worse than the bug."""
        _create_user()
        tok = self._token()
        self.client.put("/api/users/locale", headers=self._auth(tok),
                        json={"region": "DE"})
        me = self.client.get("/api/users/me", headers=self._auth(tok)).json()
        self.assertIsNone(me["region"])
        self.assertFalse(me["locale_confirmed"])

    def test_both_endpoints_require_a_token(self):
        self.assertEqual(
            self.client.get("/api/users/locale/options").status_code, 401)
        self.assertEqual(
            self.client.put("/api/users/locale",
                            json={"region": "KR"}).status_code, 401)


class Signup(_Base):

    def test_signup_stores_the_guess_but_grants_no_region(self):
        """Drives the real two-step flow — send-code then register — because
        the geo lookup happens inside it and a hand-written INSERT would test
        nothing about the wiring."""
        sent = {}

        def capture(email, code, lang):
            sent["code"] = code
            return True

        with patch("signup_lang._geo_country", return_value="JP"), \
                patch("routes_users.send_verification_code_email", capture):
            r = self.client.post("/api/users/send-code",
                                 json={"email": "bob@example.com"})
            self.assertEqual(r.status_code, 200, r.text)
            r = self.client.post("/api/users/register",
                                 json={"email": "bob@example.com",
                                       "password": "hunter2",
                                       "code": sent["code"]})
        self.assertIn(r.status_code, (200, 201), r.text)
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT lang, geo_country, region, locale_confirmed_at "
                        "FROM users WHERE email = 'bob@example.com'")
            row = cur.fetchone()
        finally:
            conn.close()
        self.assertIsNotNone(row, "user was not created")
        self.assertEqual(row["lang"], "ja")          # guess drives language
        self.assertEqual(row["geo_country"], "JP")   # ...and is recorded
        self.assertIsNone(row["region"])             # ...but grants nothing
        self.assertIsNone(row["locale_confirmed_at"])


if __name__ == "__main__":
    unittest.main()
