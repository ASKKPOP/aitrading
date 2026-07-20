"""Tests for misc routes (skill endpoints, SPA fallback)."""

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


class MiscRoutesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_skill_index_returns_200_or_error_json(self) -> None:
        resp = self.client.get("/skill.md")
        self.assertEqual(resp.status_code, 200)
        # If file not present, endpoint returns JSON error (still 200)
        ct = resp.headers.get("content-type", "")
        self.assertTrue("text/markdown" in ct or "application/json" in ct)

    def test_skill_index_uppercase_alias(self) -> None:
        resp = self.client.get("/SKILL.md")
        self.assertEqual(resp.status_code, 200)

    def test_skill_named_missing_returns_error_json(self) -> None:
        resp = self.client.get("/skill/nonexistent-skill-xyz")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("error", body)

    def test_skill_named_raw_missing_returns_error_json(self) -> None:
        resp = self.client.get("/skill/nonexistent-skill-xyz/raw")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("error", body)

    def test_root_returns_200(self) -> None:
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        # Either SPA html or API message — both are valid
        ct = resp.headers.get("content-type", "")
        self.assertTrue("html" in ct or "json" in ct)

    def test_spa_fallback_returns_200(self) -> None:
        resp = self.client.get("/some/deep/path")
        self.assertEqual(resp.status_code, 200)

    def test_unknown_api_path_returns_json_404_not_spa(self) -> None:
        """An unmatched /api/* path must 404 as JSON.

        Previously the SPA catch-all swallowed these and returned index.html
        with HTTP 200, so a status-code health check could not tell a dead
        backend from a healthy one.
        """
        resp = self.client.get("/api/definitely-not-a-route")
        self.assertEqual(resp.status_code, 404)
        self.assertIn("application/json", resp.headers.get("content-type", ""))
        self.assertNotIn("<!DOCTYPE", resp.text)
        self.assertIn("detail", resp.json())

    def test_unknown_api_path_deep_returns_json_404(self) -> None:
        resp = self.client.get("/api/nested/unknown/route")
        self.assertEqual(resp.status_code, 404)
        self.assertNotIn("<!DOCTYPE", resp.text)

    def test_health_returns_json_ok(self) -> None:
        resp = self.client.get("/api/health")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("application/json", resp.headers.get("content-type", ""))
        body = resp.json()
        self.assertEqual(body.get("status"), "ok")
        self.assertIn("database", body)

    def test_health_is_not_the_spa(self) -> None:
        resp = self.client.get("/api/health")
        self.assertNotIn("<!DOCTYPE", resp.text)

    def test_non_api_paths_still_serve_spa(self) -> None:
        """Client-side routes must keep falling back to index.html."""
        for path in ("/trade", "/settings", "/some/deep/path"):
            with self.subTest(path=path):
                resp = self.client.get(path)
                self.assertEqual(resp.status_code, 200)

    def test_apilike_prefix_is_not_treated_as_api(self) -> None:
        """/apitest is a normal SPA route, not an API path."""
        resp = self.client.get("/apitest")
        self.assertEqual(resp.status_code, 200)


if __name__ == "__main__":
    unittest.main()
