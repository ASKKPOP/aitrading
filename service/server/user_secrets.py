"""AES-GCM encryption for user-supplied secrets stored in the database.

Found in monitoring reading #100 (2026-08-30): `user_api_settings.api_key`
held provider API keys in PLAINTEXT — readable by anything with DB access and
carried verbatim inside every full DB backup — while broker credentials had
been AES-GCM encrypted since Plan 19. This closes that asymmetry.

Key material: the same 32-byte `EXECUTION_ENCRYPTION_KEY` that protects broker
credentials, deliberately rather than a new variable. `execution/crypto.py`
falls back to an EPHEMERAL key when its variable is unset, which silently
makes every stored secret undecryptable after a restart; introducing a second
key would double that footgun for no gain, and the existing one is already
present, deployed and backed up. Domain separation instead comes from the AAD
below, so a broker-credential blob cannot be pasted into an api_key column and
decrypt.

Storage format: "encv1:" + base64url(nonce || ciphertext). Anything without
that prefix is treated as legacy plaintext and returned unchanged, so reads
work before, during and after the migration.
"""
from __future__ import annotations

import base64
import logging
import os
import secrets

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

logger = logging.getLogger(__name__)

PREFIX = "encv1:"
_NONCE_BYTES = 12
_AAD = b"user_api_settings.api_key"


_EPHEMERAL: bytes | None = None


def _key() -> bytes:
    """Read the key at CALL time, not import time — tests and the migration
    script set the variable after import, and an import-time cache would pin
    a dev key for the life of the process.

    The unset case must still be PROCESS-STABLE. Minting a fresh random key
    per call (the first version of this function) made every value
    unreadable on the very next read rather than merely after a restart —
    caught by test_user_api_settings' mask assertions, which run without the
    variable set. Cached ephemeral matches execution/crypto.py's contract:
    usable within a process, gone across restarts, and loudly warned about."""
    raw = os.environ.get("EXECUTION_ENCRYPTION_KEY", "").strip()
    if raw:
        return base64.urlsafe_b64decode(raw + "==")
    global _EPHEMERAL
    if _EPHEMERAL is None:
        _EPHEMERAL = secrets.token_bytes(32)
        logger.warning(
            "EXECUTION_ENCRYPTION_KEY not set — user secrets will use an "
            "ephemeral key and cannot be decrypted after restart.")
    return _EPHEMERAL


def is_encrypted(stored: str | None) -> bool:
    return bool(stored) and str(stored).startswith(PREFIX)


def encrypt_secret(plaintext: str | None) -> str | None:
    """Encrypt a secret for storage. None/empty pass through unchanged (an
    absent key must stay absent, not become an encrypted empty string), and an
    already-encrypted value is returned as-is so a partial update that carries
    the stored value forward cannot double-encrypt it."""
    if not plaintext:
        return plaintext
    if is_encrypted(plaintext):
        return plaintext
    nonce = secrets.token_bytes(_NONCE_BYTES)
    ct = AESGCM(_key()).encrypt(nonce, str(plaintext).encode(), _AAD)
    return PREFIX + base64.urlsafe_b64encode(nonce + ct).decode()


def decrypt_secret(stored: str | None) -> str | None:
    """Return the usable secret for a stored value.

    Legacy plaintext is returned unchanged. A value that fails to decrypt
    (wrong key, tampering, a broker blob in the wrong column) returns None and
    logs — never the raw ciphertext, which would otherwise be handed to a
    provider as if it were a key. Callers then fall back to the server-env
    provider chain, which is the same degradation as an unset key."""
    if not stored:
        return stored
    if not is_encrypted(stored):
        return stored
    try:
        raw = base64.urlsafe_b64decode(stored[len(PREFIX):] + "==")
        nonce, ct = raw[:_NONCE_BYTES], raw[_NONCE_BYTES:]
        return AESGCM(_key()).decrypt(nonce, ct, _AAD).decode()
    except Exception:  # noqa: BLE001 — a bad token must not break a request
        logger.warning("user secret failed to decrypt; treating as unset")
        return None
