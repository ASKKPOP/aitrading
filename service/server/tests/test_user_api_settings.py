"""Per-user API target configuration endpoints (settings page)."""

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
from routes import create_app


_FIXED_CODE = 42000
_FIXED_CODE_STR = f"{_FIXED_CODE:06d}"
_EMAIL = "settings@example.com"
_PASSWORD = "hunter2"


class UserApiSettingsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())
        self.token = self._register_and_login()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _register_and_login(self) -> str:
        with patch("secrets.randbelow", return_value=_FIXED_CODE):
            resp = self.client.post("/api/users/send-code", json={"email": _EMAIL})
        assert resp.status_code == 200, resp.text
        resp = self.client.post(
            "/api/users/register",
            json={"email": _EMAIL, "code": _FIXED_CODE_STR, "password": _PASSWORD},
        )
        assert resp.status_code == 200, resp.text
        return resp.json()["token"]

    def _auth(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"}

    # --- GET /api/users/settings ---

    def test_settings_requires_auth(self) -> None:
        resp = self.client.get("/api/users/settings")
        self.assertEqual(resp.status_code, 401)

    def test_settings_lists_full_catalog(self) -> None:
        resp = self.client.get("/api/users/settings", headers=self._auth())
        self.assertEqual(resp.status_code, 200)
        targets = {t["target"]: t for t in resp.json()["targets"]}
        # key-bearing and keyless targets both present
        self.assertIn("llm", targets)
        self.assertIn("alpha_vantage", targets)
        self.assertIn("okx", targets)
        self.assertTrue(targets["llm"]["requires_key"])
        self.assertFalse(targets["okx"]["requires_key"])
        self.assertFalse(targets["llm"]["configured"])

    # --- PUT /api/users/settings/api/{target} ---

    def test_put_and_read_back_masked(self) -> None:
        resp = self.client.put(
            "/api/users/settings/api/llm",
            json={"api_key": "sk-test-1234567890abcd", "config": {"provider": "openai", "model": "gpt-4o"}},
            headers=self._auth(),
        )
        self.assertEqual(resp.status_code, 200)

        resp = self.client.get("/api/users/settings", headers=self._auth())
        llm = next(t for t in resp.json()["targets"] if t["target"] == "llm")
        self.assertTrue(llm["configured"])
        self.assertEqual(llm["masked_key"], "····abcd")
        self.assertEqual(llm["config"], {"provider": "openai", "model": "gpt-4o"})
        # full key never returned
        self.assertNotIn("sk-test", str(resp.json()))

    def test_put_unknown_target_404(self) -> None:
        resp = self.client.put(
            "/api/users/settings/api/nonsense",
            json={"api_key": "x"},
            headers=self._auth(),
        )
        self.assertEqual(resp.status_code, 404)

    def test_put_key_on_keyless_target_400(self) -> None:
        resp = self.client.put(
            "/api/users/settings/api/okx",
            json={"api_key": "should-not-take-a-key"},
            headers=self._auth(),
        )
        self.assertEqual(resp.status_code, 400)

    def test_disable_keyless_target(self) -> None:
        resp = self.client.put(
            "/api/users/settings/api/stocktwits",
            json={"enabled": False},
            headers=self._auth(),
        )
        self.assertEqual(resp.status_code, 200)
        resp = self.client.get("/api/users/settings", headers=self._auth())
        st = next(t for t in resp.json()["targets"] if t["target"] == "stocktwits")
        self.assertFalse(st["enabled"])

    def test_partial_update_keeps_key(self) -> None:
        self.client.put(
            "/api/users/settings/api/alpha_vantage",
            json={"api_key": "AVKEY12345"},
            headers=self._auth(),
        )
        # toggle enabled only — key must survive
        self.client.put(
            "/api/users/settings/api/alpha_vantage",
            json={"enabled": False},
            headers=self._auth(),
        )
        resp = self.client.get("/api/users/settings", headers=self._auth())
        av = next(t for t in resp.json()["targets"] if t["target"] == "alpha_vantage")
        self.assertEqual(av["masked_key"], "····2345")
        self.assertFalse(av["enabled"])

    def test_config_fields_are_whitelisted(self) -> None:
        self.client.put(
            "/api/users/settings/api/llm",
            json={"config": {"provider": "gemini", "evil": "payload"}},
            headers=self._auth(),
        )
        resp = self.client.get("/api/users/settings", headers=self._auth())
        llm = next(t for t in resp.json()["targets"] if t["target"] == "llm")
        self.assertEqual(llm["config"], {"provider": "gemini"})

    # --- DELETE ---

    def test_delete_clears_setting(self) -> None:
        self.client.put(
            "/api/users/settings/api/fred",
            json={"api_key": "FREDKEY99"},
            headers=self._auth(),
        )
        resp = self.client.delete("/api/users/settings/api/fred", headers=self._auth())
        self.assertEqual(resp.status_code, 200)
        resp = self.client.get("/api/users/settings", headers=self._auth())
        fred = next(t for t in resp.json()["targets"] if t["target"] == "fred")
        self.assertFalse(fred["configured"])
        self.assertIsNone(fred["masked_key"])

    def test_settings_isolated_per_user(self) -> None:
        self.client.put(
            "/api/users/settings/api/llm",
            json={"api_key": "sk-user-one-key"},
            headers=self._auth(),
        )
        # second user sees nothing configured
        with patch("secrets.randbelow", return_value=_FIXED_CODE):
            self.client.post("/api/users/send-code", json={"email": "two@example.com"})
        resp = self.client.post(
            "/api/users/register",
            json={"email": "two@example.com", "code": _FIXED_CODE_STR, "password": "pw2pw2"},
        )
        token2 = resp.json()["token"]
        resp = self.client.get(
            "/api/users/settings", headers={"Authorization": f"Bearer {token2}"}
        )
        llm = next(t for t in resp.json()["targets"] if t["target"] == "llm")
        self.assertFalse(llm["configured"])


if __name__ == "__main__":
    unittest.main()
