"""One-off data migration: copy every row from the SQLite DB into MySQL.

Prereqs:
  * The MySQL schema already exists (run ``alembic upgrade head`` first).
  * DATABASE_URL points at the destination MySQL.
  * DB_PATH (or the first CLI arg) points at the source SQLite file.

Usage:
    DATABASE_URL='mysql+pymysql://user:pw@host:3306/db' \
    DB_PATH='service/server/data/sooppiy.db' \
    python service/server/migrate_sqlite_to_mysql.py

IDs are preserved. Foreign-key checks are disabled for the load and re-enabled
after, so table order does not matter. Identifiers are backticked, so
reserved-word columns (read / rank / signal) copy cleanly. The script is
idempotent-ish only in that it aborts if a destination table is non-empty —
it will not silently double-load. Row counts are verified at the end.
"""

from __future__ import annotations

import os
import sqlite3
import sys
from urllib.parse import urlparse

import pymysql

# alembic's bookkeeping table — never touched by the data copy.
SKIP_TABLES = {"alembic_version"}


def _sqlite_path() -> str:
    return (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("DB_PATH", "")).strip() or (
        os.path.join(os.path.dirname(__file__), "data", "sooppiy.db")
    )


def _mysql_conn():
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        sys.exit("DATABASE_URL is not set — point it at the destination MySQL.")
    p = urlparse(url)
    return pymysql.connect(
        host=p.hostname or "localhost",
        port=p.port or 3306,
        user=p.username or "root",
        password=p.password or "",
        database=p.path.lstrip("/"),
        charset="utf8mb4",
        autocommit=False,
    )


def _sqlite_tables(sconn: sqlite3.Connection) -> list[str]:
    rows = sconn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    return [r[0] for r in rows if r[0] not in SKIP_TABLES]


def migrate() -> int:
    src = _sqlite_path()
    if not os.path.exists(src):
        sys.exit(f"source SQLite file not found: {src}")

    sconn = sqlite3.connect(src)
    sconn.row_factory = sqlite3.Row
    mconn = _mysql_conn()
    mcur = mconn.cursor()

    tables = _sqlite_tables(sconn)
    print(f"source: {src}")
    print(f"tables to copy: {len(tables)}")

    # Refuse to run into a partially-loaded destination.
    for t in tables:
        mcur.execute(f"SELECT COUNT(*) FROM `{t}`")
        if mcur.fetchone()[0]:
            sys.exit(f"destination table `{t}` is not empty — aborting to avoid double-load.")

    totals: dict[str, tuple[int, int]] = {}
    mcur.execute("SET FOREIGN_KEY_CHECKS=0")
    try:
        for t in tables:
            rows = sconn.execute(f"SELECT * FROM {t}").fetchall()
            if not rows:
                totals[t] = (0, 0)
                continue
            cols = rows[0].keys()
            collist = ", ".join(f"`{c}`" for c in cols)
            placeholders = ", ".join(["%s"] * len(cols))
            sql = f"INSERT INTO `{t}` ({collist}) VALUES ({placeholders})"
            mcur.executemany(sql, [tuple(r[c] for c in cols) for r in rows])
            totals[t] = (len(rows), mcur.rowcount)
        mconn.commit()
    finally:
        mcur.execute("SET FOREIGN_KEY_CHECKS=1")
        mconn.commit()

    # Verify row counts match.
    print("\nrow counts (source → dest):")
    mismatches = 0
    for t in tables:
        src_n = sconn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        mcur.execute(f"SELECT COUNT(*) FROM `{t}`")
        dst_n = mcur.fetchone()[0]
        flag = "" if src_n == dst_n else "  ❌ MISMATCH"
        if src_n or dst_n:
            print(f"  {t:35s} {src_n:6d} → {dst_n:6d}{flag}")
        if src_n != dst_n:
            mismatches += 1

    sconn.close()
    mconn.close()
    if mismatches:
        print(f"\n{mismatches} table(s) mismatched.")
        return 1
    print("\nall row counts match. ✅")
    return 0


if __name__ == "__main__":
    raise SystemExit(migrate())
