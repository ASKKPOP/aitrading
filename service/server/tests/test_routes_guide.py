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


def _make_user_token(email, plan=None, expires="2099-01-01T00:00:00Z"):
    """Mint a user token; `plan` grants an active subscription of that code
    (the guide library is enterprise-gated since 2026-08-02)."""
    from database import get_db_connection
    from services import _create_user_session
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("INSERT INTO users (email, password_hash) VALUES (?, ?)", (email, "x"))
    uid = cur.lastrowid
    if plan:
        cur.execute(
            "INSERT INTO user_subscriptions (user_id, plan_code, status, expires_at) "
            "VALUES (?, ?, 'active', ?)", (uid, plan, expires))
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
        self.agent_id = resp.json()["agent_id"]
        self.owner_token = _make_user_token("info@askkpop.com")
        # The library is enterprise-gated (2026-08-02): member reads below go
        # through an enterprise subscriber; the plain agent token exercises
        # the blocked path.
        self.ent_token = _make_user_token("ent@member.com", plan="enterprise")

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
        for tok in (self.ent_token,
                    _make_user_token("someone@else.com", plan="enterprise")):
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
        r = self.client.get("/api/guide/docs", headers=self._h(self.ent_token))
        groups = {g["group"] for g in r.json()["groups"]}
        self.assertIn("decisions", groups)
        self.assertNotIn("ops-keys", groups)
        self.assertNotIn("architecture", groups)

    def test_every_member_group_is_published_in_every_ui_language(self):
        """The language set is LANG_NAMES, never a literal.

        This asserted `{"ko","en","ja","th","vi"}` for the `decisions` group
        alone. Both halves were wrong by 2026-07-29: Indonesian had shipped, so
        the literal was a five-language snapshot of a six-language product, and
        checking one group let the other eight stay en/ko — `gateway` was
        Korean ONLY, and DocsPage's `docs[0]` last resort quietly served that
        Korean document to English readers. A member-visible group that cannot
        be read in a language the top bar offers is the bug; check them all.
        """
        from analysis_agents import LANG_NAMES

        r = self.client.get("/api/guide/docs", headers=self._h(self.ent_token))
        payload = r.json()
        member_groups = {g["group"] for g in payload["groups"]}
        by_group: dict[str, set] = {}
        for doc in payload["docs"]:
            by_group.setdefault(doc["group"], set()).add(doc["lang"])
        for group in sorted(member_groups):
            with self.subTest(group=group):
                self.assertEqual(by_group.get(group, set()), set(LANG_NAMES),
                                 f"{group} is missing "
                                 f"{sorted(set(LANG_NAMES) - by_group.get(group, set()))}")

    def test_every_group_nav_label_covers_every_ui_language(self):
        """The rail label is what a member navigates by: a group whose label
        omits their language renders in English even when the document behind
        it is fully translated."""
        from analysis_agents import LANG_NAMES

        r = self.client.get("/api/guide/docs", headers=self._h(self.owner_token))
        for group in r.json()["groups"]:
            with self.subTest(group=group["group"]):
                missing = [x for x in LANG_NAMES if not group.get(x)]
                self.assertFalse(missing, f"{group['group']} label missing {missing}")

    def test_docs_for_owner(self):
        r = self.client.get("/api/guide/docs", headers=self._h(self.owner_token))
        self.assertEqual(r.status_code, 200)
        keys = {d["key"] for d in r.json()["docs"]}
        self.assertIn("guide-ko", keys)
        self.assertIn("backtest-report-en", keys)
        self.assertIn("api-keys-en", keys)   # owner sees everything

    def test_doc_requires_login_and_serves_members(self):
        self.assertEqual(self.client.get("/api/guide/doc/guide-ko").status_code, 401)
        # an ENTERPRISE member receives a member document
        r_member = self.client.get("/api/guide/doc/guide-ko",
                                   headers=self._h(self.ent_token))
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

    def test_member_keys_are_readable_by_enterprise_members(self):
        for tok in (self.ent_token,
                    _make_user_token("nope@else.com", plan="enterprise")):
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

    def test_every_registered_doc_has_its_file_committed(self):
        """The listing above is filtered by what exists, so it cannot notice a
        registered doc whose HTML never shipped — the manifest ON DISK can.

        This is the check that was missing when extension-e1-e2-en reached
        production as a manifest entry with no file: the sidebar offered the
        tab and every click answered 'could not load the document'."""
        from routes_guide import _CONTENT_DIR, _load_manifest
        missing = [d["key"] for d in _load_manifest()["docs"]
                   if not (_CONTENT_DIR / f"{d['key']}.html").exists()]
        self.assertEqual(missing, [], f"registered but not built: {missing}")

    def test_a_registered_doc_with_no_file_is_not_offered(self):
        """Second line of defence for the case above: if the two ever diverge
        again in a shipped image, the reader gets no tab rather than a tab that
        always fails."""
        from routes_guide import _load_manifest
        real = _load_manifest()
        ghost = {"groups": real["groups"] + [{"group": "ghost", "ko": "유령", "en": "Ghost"}],
                 "docs": real["docs"] + [{"key": "never-built-en", "lang": "en",
                                          "group": "ghost", "title": "Ghost"}]}
        with unittest.mock.patch("routes_guide._load_manifest", return_value=ghost):
            r = self.client.get("/api/guide/docs", headers=self._h(self.owner_token))
            self.assertNotIn("never-built-en", {d["key"] for d in r.json()["docs"]})
            self.assertNotIn("ghost", {g["group"] for g in r.json()["groups"]})
            self.assertEqual(
                self.client.get("/api/guide/doc/never-built-en",
                                headers=self._h(self.owner_token)).status_code, 404)


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


class EnterpriseGateTests(unittest.TestCase):
    """Owner decision 2026-08-02: the /docs/guide library is an Enterprise
    perk. Junior/pro/professional members (and agents whose linked user is
    not enterprise) get 403 enterprise_required; the gwsetup connection
    guides on /accounts stay open to every member."""

    setUp = GuideRoutesTests.setUp
    tearDown = GuideRoutesTests.tearDown
    _h = GuideRoutesTests._h

    def _link_agent(self, user_email, plan=None):
        from database import get_db_connection
        _make_user_token(user_email, plan=plan)  # creates the user (+plan)
        conn = get_db_connection(); cur = conn.cursor()
        cur.execute("SELECT id FROM users WHERE email = ?", (user_email,))
        uid = cur.fetchone()["id"]
        cur.execute("UPDATE agents SET user_id = ? WHERE id = ?", (uid, self.agent_id))
        conn.commit(); conn.close()

    def test_non_enterprise_member_gets_403(self):
        for plan in (None, "junior", "pro", "professional"):
            tok = _make_user_token(f"{plan or 'free'}@member.com", plan=plan)
            r = self.client.get("/api/guide/docs", headers=self._h(tok))
            self.assertEqual(r.status_code, 403, f"plan={plan} listed the library")
            self.assertEqual(r.json()["detail"], "enterprise_required")
            r = self.client.get("/api/guide/doc/guide-ko", headers=self._h(tok))
            self.assertEqual(r.status_code, 403, f"plan={plan} read a doc")

    def test_expired_enterprise_gets_403(self):
        tok = _make_user_token("expired@member.com", plan="enterprise",
                               expires="2020-01-01T00:00:00Z")
        r = self.client.get("/api/guide/docs", headers=self._h(tok))
        self.assertEqual(r.status_code, 403)

    def test_plain_agent_token_gets_403(self):
        r = self.client.get("/api/guide/docs", headers=self._h(self.agent_token))
        self.assertEqual(r.status_code, 403)
        r = self.client.get("/api/guide/doc/guide-ko", headers=self._h(self.agent_token))
        self.assertEqual(r.status_code, 403)

    def test_agent_linked_to_enterprise_user_reads(self):
        self._link_agent("agent-owner@ent.com", plan="enterprise")
        r = self.client.get("/api/guide/doc/guide-ko", headers=self._h(self.agent_token))
        self.assertEqual(r.status_code, 200)

    def test_gwsetup_docs_stay_open_to_every_member(self):
        """The /accounts connection guides are operational docs for anyone
        with a gateway — the enterprise gate must not touch them."""
        junior = _make_user_token("junior-gw@member.com", plan="junior")
        for tok in (junior, self.agent_token):
            r = self.client.get("/api/guide/doc/gwsetup-binance-en",
                                headers=self._h(tok))
            self.assertEqual(r.status_code, 200, "gwsetup blocked for a member")

    def test_automation_page_manual_stays_open_to_every_member(self):
        """The /automation page manual opens IN PLACE from that page's guide
        drawer (owner ask 2026-08-10) — every signed-in member and agent can
        fetch it by key, in any language, while the /docs rail (manifest) and
        the rest of the library stay Enterprise."""
        junior = _make_user_token("junior-am@member.com", plan="junior")
        for tok in (junior, self.agent_token):
            for key in ("automation-en", "automation-ko"):
                r = self.client.get(f"/api/guide/doc/{key}", headers=self._h(tok))
                self.assertEqual(r.status_code, 200, f"{key} blocked for a member")
        self.assertEqual(
            self.client.get("/api/guide/docs", headers=self._h(junior)).status_code,
            403, "the /docs rail must stay enterprise-gated")

    def test_gate_is_403_not_404_for_member_keys(self):
        """403 (upgrade) for real member keys, 404 for owner-only keys — the
        owner-only existence-hiding rule survives the gate."""
        junior = _make_user_token("junior2@member.com", plan="junior")
        self.assertEqual(
            self.client.get("/api/guide/doc/guide-ko", headers=self._h(junior)).status_code, 403)
        self.assertEqual(
            self.client.get("/api/guide/doc/api-keys-en", headers=self._h(junior)).status_code, 404)


if __name__ == "__main__":
    unittest.main()
