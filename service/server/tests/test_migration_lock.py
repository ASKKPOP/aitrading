"""Migrations must be serialized across the backend and worker containers.

Both processes call `alembic upgrade head` at boot on MySQL, and the deploy
runbook starts them together (`compose up -d backend worker`). Without a
shared lock the two race the same DDL on a deploy that carries a migration.
The lock is a MySQL server-side advisory lock so it works across containers.
"""

import sys
import unittest
from pathlib import Path
from unittest import mock

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database


class RunMigrationsSqliteTests(unittest.TestCase):
    def test_sqlite_uses_init_database_and_never_locks(self) -> None:
        with mock.patch.object(database, "using_mysql", return_value=False), \
             mock.patch.object(database, "init_database") as init, \
             mock.patch.object(database, "_alembic_upgrade_head") as upgrade, \
             mock.patch.object(database, "get_db_connection") as conn:
            database.run_migrations()
        init.assert_called_once()
        upgrade.assert_not_called()
        conn.assert_not_called()


class RunMigrationsMysqlTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cursor = mock.MagicMock()
        self.conn = mock.MagicMock()
        self.conn.cursor.return_value = self.cursor
        # GET_LOCK grants by default
        self.cursor.fetchone.return_value = {"lock_result": 1}

    def _executed_sql(self) -> str:
        return " ".join(str(c.args[0]) for c in self.cursor.execute.call_args_list)

    def test_acquires_lock_runs_upgrade_then_releases(self) -> None:
        with mock.patch.object(database, "using_mysql", return_value=True), \
             mock.patch.object(database, "get_db_connection", return_value=self.conn), \
             mock.patch.object(database, "_alembic_upgrade_head") as upgrade:
            database.run_migrations()

        upgrade.assert_called_once()
        sql = self._executed_sql()
        self.assertIn("GET_LOCK", sql)
        self.assertIn("RELEASE_LOCK", sql)
        self.conn.close.assert_called_once()

    def test_lock_is_acquired_before_upgrade_runs(self) -> None:
        order = []
        self.cursor.execute.side_effect = lambda sql, *a: order.append(str(sql))
        with mock.patch.object(database, "using_mysql", return_value=True), \
             mock.patch.object(database, "get_db_connection", return_value=self.conn), \
             mock.patch.object(database, "_alembic_upgrade_head",
                               side_effect=lambda: order.append("UPGRADE")):
            database.run_migrations()

        get_lock_at = next(i for i, s in enumerate(order) if "GET_LOCK" in s)
        upgrade_at = order.index("UPGRADE")
        release_at = next(i for i, s in enumerate(order) if "RELEASE_LOCK" in s)
        self.assertLess(get_lock_at, upgrade_at, "upgrade ran before acquiring the lock")
        self.assertLess(upgrade_at, release_at, "lock released before the upgrade finished")

    def test_upgrade_is_skipped_when_lock_is_not_granted(self) -> None:
        self.cursor.fetchone.return_value = {"lock_result": 0}
        with mock.patch.object(database, "using_mysql", return_value=True), \
             mock.patch.object(database, "get_db_connection", return_value=self.conn), \
             mock.patch.object(database, "_alembic_upgrade_head") as upgrade:
            with self.assertRaises(RuntimeError):
                database.run_migrations()
        upgrade.assert_not_called()

    def test_lock_is_released_even_if_the_upgrade_fails(self) -> None:
        with mock.patch.object(database, "using_mysql", return_value=True), \
             mock.patch.object(database, "get_db_connection", return_value=self.conn), \
             mock.patch.object(database, "_alembic_upgrade_head",
                               side_effect=RuntimeError("migration blew up")):
            with self.assertRaises(RuntimeError):
                database.run_migrations()

        self.assertIn("RELEASE_LOCK", self._executed_sql())
        self.conn.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
