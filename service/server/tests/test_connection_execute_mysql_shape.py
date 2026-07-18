"""DatabaseConnection.execute must work on a MySQL-shaped connection.

sqlite3.Connection has an .execute() convenience shim; pymysql.connections.Connection
does not. DatabaseConnection.__getattr__ forwards unknown attributes to the wrapped
driver connection, so `conn.execute(...)` used to work locally and raise AttributeError
in production. It also bypassed DatabaseCursor.execute, which is the only place
_adapt_sql_for_mysql runs — so '?' placeholders were never rewritten to '%s' either.

These tests pin both halves down using a fake connection with the pymysql shape (no
.execute attribute), so the whole class of bug is visible to CI without a live MySQL.
"""
import os
import sqlite3
import sys

import pytest

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from database import DatabaseConnection


class _MySQLShapedCursor:
    """Records what the driver was asked to run.

    Rows are dicts because production configures pymysql with DictCursor, which
    is what DatabaseCursor._demote_decimals expects.
    """

    def __init__(self, log):
        self._log = log
        self.lastrowid = 7
        self.description = None
        self._rows = [{"id": 1}]

    def execute(self, sql, params=None):
        self._log.append((sql, params))
        return None

    def executemany(self, sql, seq):
        self._log.append((sql, list(seq)))
        return None

    def fetchone(self):
        return self._rows[0]

    def fetchall(self):
        return list(self._rows)

    def close(self):
        pass


class _MySQLShapedConnection:
    """Mimics pymysql.connections.Connection: a cursor() factory and NO .execute."""

    def __init__(self):
        self.log = []

    def cursor(self):
        return _MySQLShapedCursor(self.log)

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


def test_pymysql_connection_really_has_no_execute():
    """Guards the premise: if pymysql ever grows .execute, these tests are moot."""
    pymysql = pytest.importorskip("pymysql")
    assert not hasattr(pymysql.connections.Connection, "execute")
    # ...while sqlite3 does, which is exactly why the bug hid locally.
    assert hasattr(sqlite3.Connection, "execute")


def test_connection_execute_works_on_mysql_shaped_connection():
    raw = _MySQLShapedConnection()
    conn = DatabaseConnection(raw, "mysql")

    # Used to raise AttributeError: 'connection' object has no attribute 'execute'
    row = conn.execute("SELECT id FROM users WHERE id = ?", (1,)).fetchone()

    assert row == {"id": 1}
    assert len(raw.log) == 1


def test_connection_execute_adapts_sql_for_mysql():
    """The forwarding path skipped _adapt_sql_for_mysql entirely."""
    raw = _MySQLShapedConnection()
    conn = DatabaseConnection(raw, "mysql")

    conn.execute("UPDATE users SET trading_guidelines = ? WHERE id = ?", ("x", 1))

    sql, params = raw.log[0]
    assert "?" not in sql, "'?' placeholders must be rewritten for MySQL"
    assert sql.count("%s") == 2
    assert params == ("x", 1)


def test_connection_executemany_works_on_mysql_shaped_connection():
    raw = _MySQLShapedConnection()
    conn = DatabaseConnection(raw, "mysql")

    conn.executemany("INSERT INTO t (a, b) VALUES (?, ?)", [(1, 2), (3, 4)])

    sql, seq = raw.log[0]
    assert "?" not in sql
    assert seq == [(1, 2), (3, 4)]


def test_connection_execute_still_works_on_sqlite(tmp_path):
    raw = sqlite3.connect(str(tmp_path / "t.db"))
    conn = DatabaseConnection(raw, "sqlite")

    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("INSERT INTO t (id, name) VALUES (?, ?)", (1, "a"))

    assert conn.execute("SELECT name FROM t WHERE id = ?", (1,)).fetchone()[0] == "a"


def test_connection_execute_returns_cursor_exposing_lastrowid():
    """Call sites do conn.execute(...).fetchone(); lastrowid must survive too."""
    raw = _MySQLShapedConnection()
    conn = DatabaseConnection(raw, "mysql")

    cur = conn.execute("INSERT INTO t (a) VALUES (?)", (1,))

    assert cur.fetchone() == {"id": 1}
    assert cur.lastrowid == 7
