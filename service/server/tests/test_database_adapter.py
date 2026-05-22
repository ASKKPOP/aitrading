import os
import sys


SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from database import _adapt_sql_for_mysql


def test_mysql_adapter_escapes_like_percent_literals():
    query = _adapt_sql_for_mysql(
        "SELECT * FROM signals WHERE content LIKE '%@%' AND title LIKE '%source%' AND id = ?"
    )

    assert "content LIKE '%%@%%'" in query
    assert "title LIKE '%%source%%'" in query
    assert query.endswith("id = %s")


def test_mysql_adapter_preserves_existing_escaped_percent_literals():
    # %% is treated as a single already-escaped literal: output stays %%
    query = _adapt_sql_for_mysql("SELECT * FROM signals WHERE content LIKE '%%引用%%'")

    assert "LIKE '%%引用%%'" in query


def test_mysql_adapter_replaces_autoincrement():
    query = _adapt_sql_for_mysql(
        "CREATE TABLE t (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT)"
    )
    assert "INT AUTO_INCREMENT PRIMARY KEY" in query
    assert "AUTOINCREMENT" not in query


def test_mysql_adapter_replaces_datetime_now():
    query = _adapt_sql_for_mysql(
        "CREATE TABLE t (id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT DEFAULT (datetime('now')))"
    )
    assert "UTC_TIMESTAMP()" in query
    assert "datetime('now')" not in query


def test_mysql_adapter_replaces_question_marks():
    query = _adapt_sql_for_mysql("SELECT * FROM t WHERE id = ? AND name = ?")
    assert "%s" in query
    assert "?" not in query
