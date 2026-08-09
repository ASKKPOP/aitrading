"""The alembic chain must provide every column the code writes to.

Prod MySQL's schema comes from `alembic/versions/`. The test suite's schema
comes from `database.init_database()`. Those are two different sources of
truth, and nothing forced them to agree — so a column added only to
`init_database()` (via the idempotent-ALTER pattern) produced a fully green
suite and a 500 on the first real request:

    pymysql.err.OperationalError:
        (1054, "Unknown column 'display_name' in 'field list'")

These tests close that specific gap for the columns the OAuth writer depends
on, and assert the migration itself is idempotent so it stays safe to re-run
against a database that already has the column.
"""
import importlib.util
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

VERSIONS = SERVER_DIR / "alembic" / "versions"

# Columns of oauth_identities that routes_oauth INSERTs or UPDATEs. If the
# writer grows a column, add it here — and to a migration.
OAUTH_WRITTEN_COLUMNS = {
    "user_id", "provider", "provider_user_id", "email", "display_name", "created_at",
}


def _load(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[path.stem] = mod
    return spec, mod


class MigrationChainTests(unittest.TestCase):
    def test_display_name_is_in_a_migration_not_only_init_database(self) -> None:
        """The column must exist in the alembic chain, which is what prod runs."""
        hits = [p.name for p in VERSIONS.glob("*.py")
                if "display_name" in p.read_text() and "oauth_identities" in p.read_text()]
        self.assertTrue(
            hits,
            "oauth_identities.display_name is written by routes_oauth but no "
            "alembic migration adds it — prod MySQL will raise "
            "\"Unknown column 'display_name'\" on the first Apple sign-in.")

    def test_every_oauth_column_the_writer_touches_is_migrated(self) -> None:
        """Guards the whole column set, not just today's regression."""
        chain = "\n".join(p.read_text() for p in VERSIONS.glob("*.py"))
        for column in sorted(OAUTH_WRITTEN_COLUMNS):
            self.assertIn(
                column, chain,
                f"routes_oauth writes oauth_identities.{column}, but no migration "
                f"mentions it — it would not exist on prod MySQL.")

    def test_revision_ids_are_unique_and_chain_is_linear(self) -> None:
        """A duplicate or orphaned down_revision breaks `alembic upgrade head`
        for everyone, and only shows up at deploy time."""
        revs, downs = {}, {}
        for p in VERSIONS.glob("*.py"):
            text = p.read_text()
            r = re.search(r'^revision\s*=\s*["\']([^"\']+)', text, re.M)
            d = re.search(r'^down_revision\s*=\s*["\']([^"\']+)', text, re.M)
            if not r:
                continue
            self.assertNotIn(r.group(1), revs,
                             f"duplicate revision id {r.group(1)} in {p.name} and "
                             f"{revs.get(r.group(1))}")
            revs[r.group(1)] = p.name
            if d:
                self.assertNotIn(
                    d.group(1), downs,
                    f"two migrations both descend from {d.group(1)}: "
                    f"{p.name} and {downs.get(d.group(1))} — the chain has forked")
                downs[d.group(1)] = p.name
        for parent in downs:
            self.assertIn(parent, revs, f"down_revision {parent} has no migration")


class DisplayNameMigrationTests(unittest.TestCase):
    """Run 0047's real upgrade()/downgrade() against SQLite."""

    def setUp(self) -> None:
        path = VERSIONS / "0047_oauth_identity_display_name.py"
        self.assertTrue(path.exists(), "0047 migration is missing")
        self.spec, self.mod = _load(path)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.engine = sa.create_engine(f"sqlite:///{os.path.join(self.tmp.name,'t.db')}")

    def _columns(self, conn):
        return {c["name"] for c in sa.inspect(conn).get_columns("oauth_identities")}

    def _run(self, fn_name, times=1):
        with self.engine.connect() as conn:
            conn.execute(sa.text("""
                CREATE TABLE IF NOT EXISTS oauth_identities (
                    id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL,
                    provider TEXT NOT NULL, provider_user_id TEXT NOT NULL,
                    email TEXT, created_at TEXT NOT NULL)"""))
            conn.commit()
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                self.spec.loader.exec_module(self.mod)
                for _ in range(times):
                    getattr(self.mod, fn_name)()
                    conn.commit()
                return self._columns(conn)

    def test_upgrade_adds_the_column(self) -> None:
        self.assertIn("display_name", self._run("upgrade"))

    def test_upgrade_is_idempotent(self) -> None:
        """Prod may already have the column from a hand-applied hotfix; a blind
        ADD COLUMN would abort the whole deploy's migration step."""
        self.assertIn("display_name", self._run("upgrade", times=3))

    def test_downgrade_is_idempotent(self) -> None:
        with self.engine.connect() as conn:
            conn.execute(sa.text("""
                CREATE TABLE oauth_identities (
                    id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL,
                    provider TEXT NOT NULL, provider_user_id TEXT NOT NULL,
                    email TEXT, created_at TEXT NOT NULL)"""))
            conn.commit()
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                self.spec.loader.exec_module(self.mod)
                self.mod.upgrade(); conn.commit()
                self.mod.downgrade(); conn.commit()
                self.mod.downgrade(); conn.commit()   # must not raise
                self.assertNotIn("display_name", self._columns(conn))


if __name__ == "__main__":
    unittest.main()
