"""
create_admin.py — bootstrap (or reset) an admin account for the manager console.

The console has no self-signup: the first superadmin is created here, then
manages other admins from the Admins tab. Run from the project root so the
SQLite path resolves the same way as the server:

    .venv/bin/python service/server/scripts/create_admin.py admin@example.com 'password' [superadmin|operator]

If the email already exists, its password (and role, when given) is reset.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from database import get_db_connection, init_database  # noqa: E402
from utils import hash_password  # noqa: E402


def main() -> None:
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    email = sys.argv[1].strip().lower()
    password = sys.argv[2]
    role = sys.argv[3] if len(sys.argv) > 3 else "superadmin"
    if role not in ("superadmin", "operator"):
        print(f"Invalid role: {role} (use superadmin or operator)")
        sys.exit(1)
    if len(password) < 8:
        print("Password must be at least 8 characters")
        sys.exit(1)

    init_database()
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id FROM admin_users WHERE email = ?", (email,))
        row = cursor.fetchone()
        if row:
            cursor.execute(
                "UPDATE admin_users SET password_hash = ?, role = ?, status = 'active' WHERE id = ?",
                (hash_password(password), role, row["id"]),
            )
            cursor.execute("DELETE FROM admin_tokens WHERE admin_id = ?", (row["id"],))
            conn.commit()
            print(f"Updated existing admin {email} (id={row['id']}, role={role})")
        else:
            cursor.execute(
                "INSERT INTO admin_users (email, password_hash, role) VALUES (?, ?, ?)",
                (email, hash_password(password), role),
            )
            conn.commit()
            print(f"Created admin {email} (id={cursor.lastrowid}, role={role})")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
