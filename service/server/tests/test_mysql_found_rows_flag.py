"""The MySQL connection must be opened with CLIENT.FOUND_ROWS.

Every ownership/lease fence in the codebase checks `cursor.rowcount == 1`
after an UPDATE. SQLite (which this suite runs on) reports MATCHED rows, but
MySQL's default reports CHANGED rows — an UPDATE that writes values identical
to what is stored returns 0. run_feedback.save_state re-writes an unchanged
adapt state on every quiet cycle, so on prod every fleet member's cycle died
with a silent "adapt state fence lost" after its first trade-free save
(2026-07-21: 11 hours of claimed-but-eventless cycles). FOUND_ROWS aligns
MySQL's rowcount with the semantics the whole suite is written against.

CI has no live MySQL, so this pins the connect() call shape via a mock.
"""
import os
import sys
from unittest.mock import MagicMock, patch

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import pymysql

import database


def test_mysql_connect_passes_found_rows_flag():
    fake_pymysql = MagicMock()
    fake_pymysql.cursors.DictCursor = pymysql.cursors.DictCursor
    fake_pymysql.constants.CLIENT.FOUND_ROWS = \
        pymysql.constants.CLIENT.FOUND_ROWS
    with patch.object(database, "pymysql", fake_pymysql), \
            patch.object(database, "DATABASE_URL",
                         "mysql+pymysql://u:p@dbhost:3306/sooppiy"):
        database.get_db_connection()
    assert fake_pymysql.connect.called, "pymysql.connect was not invoked"
    kwargs = fake_pymysql.connect.call_args.kwargs
    assert kwargs.get("client_flag") == pymysql.constants.CLIENT.FOUND_ROWS, (
        "MySQL connections must set CLIENT.FOUND_ROWS so UPDATE rowcount "
        "means matched rows (SQLite semantics) — every rowcount fence "
        "depends on it")
