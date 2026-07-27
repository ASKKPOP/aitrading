"""Guide access: members read member docs, owner_only stays owner-only.

Until 2026-07-27 the WHOLE guide was gated on one allowlisted email, so three
of four prod accounts got 403 on every document — including the member guides
written for them — while the page advertised itself as members-only. These
tests pin the split: a logged-in member sees the member documents and cannot
even learn that an owner_only key exists.
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

from fastapi.testclient import TestClient

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
from routes import create_app


def _make_user_token(email):
    from database import get_db_connection
    from services import _create_user_session
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("INSERT INTO users (email, password_hash) VALUES (?, ?)", (email, "x"))
    uid = cur.lastrowid
    conn.commit(); conn.close()
    return _create_user_session(uid)


class GuideRoutesTests(unittest.TestCase):
    """The whole guide is owner-only. Only info@askkpop.com (a USER token whose
    email is on the allowlist) may list or open any doc."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())
        # a non-owner agent token (agents have no email → never an owner)
        resp = self.client.post(
            "/api/claw/agents/selfRegister",
            json={"name": "guide-reader", "password": "pw123", "initial_balance": 1000.0})
        assert resp.status_code == 200, resp.text
        self.agent_token = resp.json()["token"]
        self.owner_token = _make_user_token("info@askkpop.com")

    def tearDown(self):
        self.tmp.cleanup()

    def _h(self, token):
        return {"Authorization": f"Bearer {token}"}

    def test_docs_requires_login(self):
        self.assertEqual(self.client.get("/api/guide/docs").status_code, 401)
        self.assertEqual(
            self.client.get("/api/guide/docs", headers=self._h("claw_not_a_real_token")).status_code,
            401)

    def test_members_get_the_listing_without_owner_only_docs(self):
        for tok in (self.agent_token, _make_user_token("someone@else.com")):
            r = self.client.get("/api/guide/docs", headers=self._h(tok))
            self.assertEqual(r.status_code, 200)
            keys = {d["key"] for d in r.json()["docs"]}
            self.assertIn("guide-ko", keys)
            self.assertIn("decisions-ko", keys)
            self.assertNotIn("api-keys-en", keys)
            self.assertNotIn("architecture-en", keys)

    def test_member_listing_hides_groups_left_with_no_documents(self):
        """An empty group in the sidebar advertises material the member cannot
        open — which is how the old gate produced 'could not load'."""
        r = self.client.get("/api/guide/docs",
                            headers=self._h(_make_user_token("someone@else.com")))
        groups = {g["group"] for g in r.json()["groups"]}
        self.assertIn("decisions", groups)
        self.assertNotIn("ops-keys", groups)
        self.assertNotIn("architecture", groups)

    def test_the_member_guide_is_published_in_every_ui_language(self):
        r = self.client.get("/api/guide/docs",
                            headers=self._h(_make_user_token("someone@else.com")))
        langs = {d["lang"] for d in r.json()["docs"] if d["group"] == "decisions"}
        self.assertEqual(langs, {"ko", "en", "ja", "th", "vi"})

    def test_docs_for_owner(self):
        r = self.client.get("/api/guide/docs", headers=self._h(self.owner_token))
        self.assertEqual(r.status_code, 200)
        keys = {d["key"] for d in r.json()["docs"]}
        self.assertIn("guide-ko", keys)
        self.assertIn("backtest-report-en", keys)
        self.assertIn("api-keys-en", keys)   # owner sees everything

    def test_doc_requires_login_and_serves_members(self):
        self.assertEqual(self.client.get("/api/guide/doc/guide-ko").status_code, 401)
        # a logged-in member now RECEIVES a member document
        r_member = self.client.get("/api/guide/doc/guide-ko",
                                   headers=self._h(self.agent_token))
        self.assertEqual(r_member.status_code, 200)
        self.assertIn("<!doctype html", r_member.text.lower())
        # owner → 200 html
        r = self.client.get("/api/guide/doc/guide-ko", headers=self._h(self.owner_token))
        self.assertEqual(r.status_code, 200)
        self.assertIn("text/html", r.headers["content-type"])
        self.assertIn("<!doctype html", r.text.lower())
        self.assertIn("private", r.headers.get("cache-control", ""))

    def test_owner_only_keys_stay_404_for_members(self):
        """404 rather than 403 — a member must not even learn the key exists."""
        for tok in (self.agent_token, _make_user_token("nope@else.com")):
            for key in ("api-keys-en", "architecture-en", "extension-e1-e2-en"):
                r = self.client.get(f"/api/guide/doc/{key}", headers=self._h(tok))
                self.assertEqual(r.status_code, 404, f"{key} leaked to a member")

    def test_member_keys_are_readable_by_members(self):
        for tok in (self.agent_token, _make_user_token("nope@else.com")):
            for key in ("guide-ko", "decisions-ko", "backtest-report-en"):
                r = self.client.get(f"/api/guide/doc/{key}", headers=self._h(tok))
                self.assertEqual(r.status_code, 200, f"{key} withheld from a member")

    def test_unknown_and_traversal_keys_rejected(self):
        self.assertEqual(
            self.client.get("/api/guide/doc/nope", headers=self._h(self.owner_token)).status_code, 404)
        # An encoded traversal path is URL-normalized by the router and never
        # reaches the guide handler (falls through to the SPA catch-all).
        r = self.client.get("/api/guide/doc/..%2F..%2Fmain", headers=self._h(self.owner_token))
        self.assertNotIn("guide_content", r.text)
        self.assertNotIn("AI 자동매매", r.text)
        # Handler-level whitelist: a hostile key that DOES reach the handler is
        # rejected because it isn't in the manifest — never used as a path.
        from routes_guide import _load_manifest
        manifest = _load_manifest()
        self.assertFalse(any(d["key"] == "../../main" for d in manifest["docs"]))
        r2 = self.client.get("/api/guide/doc/....main", headers=self._h(self.owner_token))
        self.assertEqual(r2.status_code, 404)

    def test_every_manifest_doc_is_built_and_served_for_owner(self):
        manifest = self.client.get("/api/guide/docs", headers=self._h(self.owner_token)).json()
        for doc in manifest["docs"]:
            r = self.client.get(f"/api/guide/doc/{doc['key']}", headers=self._h(self.owner_token))
            self.assertEqual(r.status_code, 200, f"{doc['key']} not served")
            self.assertGreater(len(r.text), 500, f"{doc['key']} suspiciously small")


class OwnerAllowlistTests(unittest.TestCase):
    """Owner-email matching: case-insensitive, env-configurable, no secret leak."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())

    def tearDown(self):
        self.tmp.cleanup()

    def _h(self, tok):
        return {"Authorization": f"Bearer {tok}"}

    def test_owner_email_match_is_case_insensitive(self):
        r = self.client.get("/api/guide/doc/api-keys-en",
                            headers=self._h(_make_user_token("Info@AskKpop.com")))
        self.assertEqual(r.status_code, 200)

    def test_allowlist_is_env_configurable(self):
        with unittest.mock.patch.dict(os.environ, {"DOCS_OWNER_EMAILS": "boss@x.com"}):
            owner = self.client.get("/api/guide/doc/api-keys-en",
                                    headers=self._h(_make_user_token("boss@x.com")))
            self.assertEqual(owner.status_code, 200)
            # the default owner is no longer privileged under the override
            other = self.client.get("/api/guide/doc/api-keys-en",
                                    headers=self._h(_make_user_token("info@askkpop.com")))
            self.assertEqual(other.status_code, 404)

    def test_the_api_keys_doc_never_contains_actual_secret_values(self):
        """Belt and braces: the page shows status/length, never a real key."""
        r = self.client.get("/api/guide/doc/api-keys-en",
                            headers=self._h(_make_user_token("info@askkpop.com")))
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(re.search(r"\b[A-Za-z0-9_\-]{40,}\b", r.text),
                          "a 40+ char token-like string leaked into the owner doc")


if __name__ == "__main__":
    unittest.main()
