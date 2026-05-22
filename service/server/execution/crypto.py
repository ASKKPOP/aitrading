"""
execution/crypto.py — AES-GCM encryption for broker credentials.

Credentials (API key + secret) are stored encrypted in broker_accounts.credentials_enc.
The encryption key is 32 raw bytes, base64url-encoded, stored in EXECUTION_ENCRYPTION_KEY.

If the key is not set in development, a random one is generated per-process (credentials
cannot be decrypted across restarts — fine for dev; never acceptable in production).
"""
from __future__ import annotations

import base64
import json
import logging
import os
import secrets

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_logger = logging.getLogger(__name__)
_NONCE_BYTES = 12  # 96-bit nonce for GCM


def _load_key() -> bytes:
    raw = os.environ.get("EXECUTION_ENCRYPTION_KEY", "")
    if raw:
        return base64.urlsafe_b64decode(raw + "==")  # pad-tolerant
    # Dev fallback: ephemeral key — warn loudly
    key = secrets.token_bytes(32)
    _logger.warning(
        "EXECUTION_ENCRYPTION_KEY not set — using ephemeral key. "
        "Set this variable in production or credentials cannot be decrypted after restart."
    )
    return key


# Load once at import time.
_KEY: bytes = _load_key()
_AESGCM = AESGCM(_KEY)


def encrypt_credentials(creds: dict) -> str:
    """
    Encrypt a dict of credentials to a base64url string.
    Format: base64url(nonce || ciphertext).
    """
    plaintext = json.dumps(creds).encode()
    nonce = secrets.token_bytes(_NONCE_BYTES)
    ct = _AESGCM.encrypt(nonce, plaintext, None)
    return base64.urlsafe_b64encode(nonce + ct).decode()


def decrypt_credentials(token: str) -> dict:
    """
    Decrypt a token produced by encrypt_credentials.
    Raises ValueError on invalid / tampered tokens.
    """
    try:
        raw = base64.urlsafe_b64decode(token + "==")
        nonce, ct = raw[:_NONCE_BYTES], raw[_NONCE_BYTES:]
        plaintext = _AESGCM.decrypt(nonce, ct, None)
        return json.loads(plaintext)
    except Exception as exc:
        raise ValueError(f"credential decryption failed: {exc}") from exc


def generate_key_b64() -> str:
    """Generate a fresh 32-byte key, base64url-encoded.  Print and store in EXECUTION_ENCRYPTION_KEY."""
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
