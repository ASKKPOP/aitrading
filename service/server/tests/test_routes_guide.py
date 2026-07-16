"""Login-gated guide routes — the gate must be real (no token → no bytes)."""

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

import database
from routes import create_app


class GuideRoutesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())
        resp = self.client.post(
            "/api/claw/agents/selfRegister",
            json={"name": "guide-reader", "password": "pw123", "initial_balance": 1000.0})
        assert resp.status_code == 200, resp.text
        self.token = resp.json()["token"]

    def tearDown(self):
        self.tmp.cleanup()

    def _h(self, token=None):
        return {"Authorization": f"Bearer {token or self.token}"}

    def test_docs_requires_login(self):
        self.assertEqual(self.client.get("/api/guide/docs").status_code, 401)
        self.assertEqual(
            self.client.get("/api/guide/docs", headers=self._h("claw_not_a_real_token")).status_code,
            401)

    def test_docs_with_agent_token(self):
        r = self.client.get("/api/guide/docs", headers=self._h())
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIn("groups", body)
        self.assertIn("docs", body)
        keys = {d["key"] for d in body["docs"]}
        self.assertIn("guide-ko", keys)
        self.assertIn("guide-en", keys)
        self.assertIn("backtest-report-en", keys)

    def test_doc_requires_login_and_serves_html(self):
        self.assertEqual(self.client.get("/api/guide/doc/guide-ko").status_code, 401)
        r = self.client.get("/api/guide/doc/guide-ko", headers=self._h())
        self.assertEqual(r.status_code, 200)
        self.assertIn("text/html", r.headers["content-type"])
        self.assertIn("<!doctype html", r.text.lower())
        self.assertIn("private", r.headers.get("cache-control", ""))

    def test_unknown_and_traversal_keys_rejected(self):
        self.assertEqual(
            self.client.get("/api/guide/doc/nope", headers=self._h()).status_code, 404)
        # An encoded traversal path is URL-normalized by the router and never
        # reaches the guide handler (falls through to the SPA catch-all).
        # The guarantee that matters: no guide/file bytes are served.
        r = self.client.get("/api/guide/doc/..%2F..%2Fmain", headers=self._h())
        self.assertNotIn("guide_content", r.text)
        self.assertNotIn("AI 자동매매", r.text)
        # Handler-level whitelist: a hostile key that DOES reach the handler
        # is rejected because it isn't in the manifest — never used as a path.
        from routes_guide import _load_manifest
        manifest = _load_manifest()
        self.assertFalse(any(d["key"] == "../../main" for d in manifest["docs"]))
        r2 = self.client.get("/api/guide/doc/....main", headers=self._h())
        self.assertEqual(r2.status_code, 404)

    def test_every_manifest_doc_is_built_and_served(self):
        manifest = self.client.get("/api/guide/docs", headers=self._h()).json()
        for doc in manifest["docs"]:
            r = self.client.get(f"/api/guide/doc/{doc['key']}", headers=self._h())
            self.assertEqual(r.status_code, 200, f"{doc['key']} not served")
            self.assertGreater(len(r.text), 500, f"{doc['key']} suspiciously small")


if __name__ == "__main__":
    unittest.main()
