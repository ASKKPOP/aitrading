"""Encrypt existing plaintext `user_api_settings.api_key` values in place.

Found by monitoring reading #100: provider API keys were stored in plaintext
while broker credentials were AES-GCM encrypted. The code now encrypts on
write and tolerates legacy plaintext on read; this migrates the rows that
already exist.

Safety properties, in order of importance:
  * It NEVER prints, logs or returns a key value — only row ids, targets and
    counts. Anyone reading the output learns nothing they did not already have.
  * It refuses to run without EXECUTION_ENCRYPTION_KEY, because the encryption
    module falls back to an EPHEMERAL key when it is unset, which would render
    every migrated key undecryptable after the next restart.
  * It verifies each ciphertext round-trips back to the exact original BEFORE
    committing, and aborts the whole transaction if any row fails.
  * It is idempotent: already-encrypted rows are skipped.

Dry run by default; pass --apply to commit. Take a DB backup first.

    python scripts/encrypt_user_api_keys.py            # dry run
    python scripts/encrypt_user_api_keys.py --apply    # commit
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "service" / "server"))

from database import get_db_connection  # noqa: E402
from user_secrets import decrypt_secret, encrypt_secret, is_encrypted  # noqa: E402


def main() -> int:
    apply = "--apply" in sys.argv
    if not os.environ.get("EXECUTION_ENCRYPTION_KEY", "").strip():
        print("REFUSING: EXECUTION_ENCRYPTION_KEY is not set. Migrating with "
              "an ephemeral key would make every key undecryptable after the "
              "next restart.")
        return 2

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, user_id, target, api_key FROM "
                       "user_api_settings WHERE api_key IS NOT NULL AND "
                       "api_key <> ''")
        rows = [dict(r) for r in cursor.fetchall()]
        todo = [r for r in rows if not is_encrypted(r["api_key"])]
        print(f"rows with a key: {len(rows)} | already encrypted: "
              f"{len(rows) - len(todo)} | to encrypt: {len(todo)}")
        if not todo:
            print("nothing to do")
            return 0

        for row in todo:
            token = encrypt_secret(row["api_key"])
            # Verify BEFORE writing: a key that cannot be read back is worse
            # than a plaintext one.
            if decrypt_secret(token) != row["api_key"]:
                print(f"ABORT: round-trip mismatch on row id={row['id']} "
                      f"(user {row['user_id']}, target {row['target']})")
                conn.rollback()
                return 1
            cursor.execute("UPDATE user_api_settings SET api_key = ? WHERE "
                           "id = ?", (token, row["id"]))
            print(f"  row id={row['id']} user={row['user_id']} "
                  f"target={row['target']}: encrypted (verified)")

        cursor.execute("SELECT id, api_key FROM user_api_settings WHERE "
                       "api_key IS NOT NULL AND api_key <> ''")
        remaining = [r for r in cursor.fetchall() if not is_encrypted(r["api_key"])]
        if remaining:
            print(f"ABORT: {len(remaining)} row(s) still plaintext after the "
                  "pass")
            conn.rollback()
            return 1

        if apply:
            conn.commit()
            print(f"COMMITTED — {len(todo)} row(s) encrypted, 0 plaintext left")
        else:
            conn.rollback()
            print("DRY RUN — rolled back (pass --apply to commit)")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
