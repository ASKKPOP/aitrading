"""Encryption at rest for user-supplied provider keys (monitoring #100).

The defect: `user_api_settings.api_key` stored provider API keys in plaintext,
so any DB read or full backup exposed them, while broker credentials had been
AES-GCM encrypted since Plan 19. These tests pin the crypto, the legacy
tolerance that lets reads work mid-migration, and — most importantly — that
the write path actually stores ciphertext, which is the only assertion that
would have caught the original defect.
"""

from __future__ import annotations

import base64
import json
import os
import secrets
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
import user_secrets
from routes import create_app

_FIXED_CODE = 42000
_FIXED_CODE_STR = f"{_FIXED_CODE:06d}"
KEY_B64 = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
SAMPLE = "sk-ant-api03-" + "A" * 40


class CryptoTests(unittest.TestCase):
    def setUp(self):
        os.environ["EXECUTION_ENCRYPTION_KEY"] = KEY_B64

    def tearDown(self):
        os.environ.pop("EXECUTION_ENCRYPTION_KEY", None)

    def test_round_trip(self):
        token = user_secrets.encrypt_secret(SAMPLE)
        self.assertTrue(token.startswith(user_secrets.PREFIX))
        self.assertNotIn(SAMPLE, token)
        self.assertEqual(user_secrets.decrypt_secret(token), SAMPLE)

    def test_nonce_is_fresh_per_call(self):
        self.assertNotEqual(user_secrets.encrypt_secret(SAMPLE),
                            user_secrets.encrypt_secret(SAMPLE))

    def test_legacy_plaintext_passes_through(self):
        self.assertEqual(user_secrets.decrypt_secret(SAMPLE), SAMPLE)
        self.assertFalse(user_secrets.is_encrypted(SAMPLE))

    def test_empty_and_none_pass_through(self):
        for value in (None, ""):
            self.assertEqual(user_secrets.encrypt_secret(value), value)
            self.assertEqual(user_secrets.decrypt_secret(value), value)

    def test_double_encryption_is_refused(self):
        once = user_secrets.encrypt_secret(SAMPLE)
        self.assertEqual(user_secrets.encrypt_secret(once), once)
        self.assertEqual(user_secrets.decrypt_secret(once), SAMPLE)

    def test_wrong_key_returns_none_not_ciphertext(self):
        token = user_secrets.encrypt_secret(SAMPLE)
        os.environ["EXECUTION_ENCRYPTION_KEY"] = base64.urlsafe_b64encode(
            secrets.token_bytes(32)).decode()
        got = user_secrets.decrypt_secret(token)
        self.assertIsNone(got)

    def test_tampered_token_returns_none(self):
        token = user_secrets.encrypt_secret(SAMPLE)
        tampered = token[:-4] + ("AAAA" if not token.endswith("AAAA") else "BBBB")
        self.assertIsNone(user_secrets.decrypt_secret(tampered))

    def test_broker_credential_blob_does_not_decrypt_here(self):
        """Domain separation: the AAD must stop a broker token being reused
        in the api_key column."""
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        key = base64.urlsafe_b64decode(KEY_B64 + "==")
        nonce = secrets.token_bytes(12)
        # Same key, no AAD — exactly what execution/crypto.py produces.
        ct = AESGCM(key).encrypt(nonce, b'{"api_key": "broker"}', None)
        foreign = user_secrets.PREFIX + base64.urlsafe_b64encode(
            nonce + ct).decode()
        self.assertIsNone(user_secrets.decrypt_secret(foreign))

    def test_key_is_read_at_call_time(self):
        """A key set after import must be honoured — an import-time cache
        would pin an ephemeral key and silently break every stored secret."""
        os.environ.pop("EXECUTION_ENCRYPTION_KEY", None)
        ephemeral_token = user_secrets.encrypt_secret(SAMPLE)
        os.environ["EXECUTION_ENCRYPTION_KEY"] = KEY_B64
        # Encrypted under a different (ephemeral) key → unreadable now.
        self.assertIsNone(user_secrets.decrypt_secret(ephemeral_token))
        # …but a fresh encrypt under the real key round-trips.
        self.assertEqual(
            user_secrets.decrypt_secret(user_secrets.encrypt_secret(SAMPLE)),
            SAMPLE)


class RouteStorageTests(unittest.TestCase):
    """The assertion that would have caught the original defect: what lands
    in the column."""

    def setUp(self):
        os.environ["EXECUTION_ENCRYPTION_KEY"] = KEY_B64
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())
        with patch("secrets.randbelow", return_value=_FIXED_CODE):
            self.client.post("/api/users/send-code",
                             json={"email": "sec@example.com"})
        resp = self.client.post("/api/users/register", json={
            "email": "sec@example.com", "code": _FIXED_CODE_STR,
            "password": "pw123456"})
        assert resp.status_code == 200, resp.text
        self.token = resp.json()["token"]
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT id FROM users WHERE email = ?",
                        ("sec@example.com",))
            self.user_id = cur.fetchone()["id"]
        finally:
            conn.close()

    def tearDown(self):
        os.environ.pop("EXECUTION_ENCRYPTION_KEY", None)
        self.tmp.cleanup()

    def _h(self):
        return {"Authorization": f"Bearer {self.token}"}

    def _stored(self, target="llm"):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT api_key FROM user_api_settings WHERE "
                        "user_id = ? AND target = ?", (self.user_id, target))
            row = cur.fetchone()
            return row["api_key"] if row else None
        finally:
            conn.close()

    def _save_key(self, key):
        return self.client.put(
            "/api/users/settings/api/llm",
            json={"api_key": key,
                  "config": {"provider": "anthropic", "model": "claude-opus-4-8"},
                  "enabled": True},
            headers=self._h())

    def test_saved_key_is_ciphertext_in_the_column(self):
        resp = self._save_key(SAMPLE)
        if resp.status_code == 403:
            self.skipTest("llm target gated by entitlements in this build")
        self.assertEqual(resp.status_code, 200, resp.text)
        stored = self._stored()
        self.assertIsNotNone(stored)
        self.assertTrue(user_secrets.is_encrypted(stored))
        self.assertNotIn(SAMPLE, stored)          # the defect, pinned
        self.assertNotIn("sk-ant", stored)
        self.assertEqual(user_secrets.decrypt_secret(stored), SAMPLE)

    def test_mask_shows_the_keys_last_four_not_the_ciphertexts(self):
        if self._save_key(SAMPLE).status_code == 403:
            self.skipTest("llm target gated by entitlements in this build")
        resp = self.client.get("/api/users/settings", headers=self._h())
        self.assertEqual(resp.status_code, 200, resp.text)
        llm = [t for t in resp.json()["targets"] if t["target"] == "llm"][0]
        self.assertEqual(llm["masked_key"], f"····{SAMPLE[-4:]}")
        self.assertTrue(llm["configured"])

    def test_partial_update_does_not_double_encrypt(self):
        if self._save_key(SAMPLE).status_code == 403:
            self.skipTest("llm target gated by entitlements in this build")
        first = self._stored()
        # Update only the config; the key must survive readable.
        resp = self.client.put(
            "/api/users/settings/api/llm",
            json={"config": {"provider": "anthropic",
                             "model": "claude-sonnet-5"}},
            headers=self._h())
        self.assertEqual(resp.status_code, 200, resp.text)
        second = self._stored()
        self.assertEqual(first, second)
        self.assertEqual(user_secrets.decrypt_secret(second), SAMPLE)

    def test_legacy_plaintext_row_still_resolves(self):
        """Reads must work mid-migration, before the script has run."""
        if self._save_key(SAMPLE).status_code == 403:
            self.skipTest("llm target gated by entitlements in this build")
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("UPDATE user_api_settings SET api_key = ? WHERE "
                        "user_id = ? AND target = 'llm'", (SAMPLE, self.user_id))
            conn.commit()
        finally:
            conn.close()
        resp = self.client.get("/api/users/settings", headers=self._h())
        llm = [t for t in resp.json()["targets"] if t["target"] == "llm"][0]
        self.assertEqual(llm["masked_key"], f"····{SAMPLE[-4:]}")


class MigrationTests(unittest.TestCase):
    def setUp(self):
        os.environ["EXECUTION_ENCRYPTION_KEY"] = KEY_B64
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO user_api_settings (user_id, target, api_key, "
                    "config_json, enabled, updated_at) VALUES "
                    "(1, 'llm', ?, ?, 1, '2026-08-25T00:00:00Z')",
                    (SAMPLE, json.dumps({"provider": "anthropic"})))
        cur.execute("INSERT INTO user_api_settings (user_id, target, api_key, "
                    "config_json, enabled, updated_at) VALUES "
                    "(2, 'alerts', NULL, '{}', 1, '2026-08-25T00:00:00Z')")
        conn.commit()
        conn.close()

    def tearDown(self):
        os.environ.pop("EXECUTION_ENCRYPTION_KEY", None)
        self.tmp.cleanup()

    def _run(self, *args):
        import importlib.util
        path = SERVER_DIR.parents[1] / "scripts" / "encrypt_user_api_keys.py"
        spec = importlib.util.spec_from_file_location("mig", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        with patch.object(sys, "argv", ["mig", *args]):
            return mod.main()

    def _keys(self):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT user_id, api_key FROM user_api_settings "
                        "ORDER BY user_id")
            return {r["user_id"]: r["api_key"] for r in cur.fetchall()}
        finally:
            conn.close()

    def test_dry_run_changes_nothing(self):
        self.assertEqual(self._run(), 0)
        self.assertEqual(self._keys()[1], SAMPLE)

    def test_apply_encrypts_and_is_idempotent(self):
        self.assertEqual(self._run("--apply"), 0)
        stored = self._keys()[1]
        self.assertTrue(user_secrets.is_encrypted(stored))
        self.assertEqual(user_secrets.decrypt_secret(stored), SAMPLE)
        self.assertIsNone(self._keys()[2])          # NULL row untouched
        self.assertEqual(self._run("--apply"), 0)   # second pass: no-op
        self.assertEqual(self._keys()[1], stored)

    def test_refuses_without_the_encryption_key(self):
        os.environ.pop("EXECUTION_ENCRYPTION_KEY", None)
        self.assertEqual(self._run("--apply"), 2)
        self.assertEqual(self._keys()[1], SAMPLE)   # untouched


if __name__ == "__main__":
    unittest.main()
