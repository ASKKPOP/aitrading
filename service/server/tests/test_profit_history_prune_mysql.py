"""profit-history prune — MySQL branch must not STR_TO_DATE the stored timestamps.

recorded_at is written by _record_profit_history_once via
datetime.now(timezone.utc).isoformat(), which includes microseconds
('2026-07-21T01:20:18.660506Z'). STR_TO_DATE with '%Y-%m-%dT%H:%i:%sZ' has no
fractional-seconds token, so MySQL 8 raised 1411 on every such row and the
whole prune aborted. The fix buckets by fixed-offset SUBSTRINGs of the ISO
string, which are identical with or without a microsecond suffix.

Like test_connection_execute_mysql_shape.py, this pins the MySQL-branch SQL
with a fake MySQL-shaped connection so the regression is visible to CI without
a live MySQL.
"""

import sys
import unittest
from pathlib import Path
from unittest import mock

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from tasks import _prune_profit_history_unlocked

TS_PLAIN = "2026-07-21T01:20:18Z"
TS_MICROS = "2026-07-21T01:20:18.660506Z"


class _FakeCursor:
    def __init__(self, log):
        self._log = log
        self.rowcount = 0

    def execute(self, sql, params=None):
        self._log.append((sql, params))

    def close(self):
        pass


class _FakeMySQLConnection:
    def __init__(self):
        self.log = []

    def cursor(self):
        return _FakeCursor(self.log)

    def commit(self):
        pass

    def close(self):
        pass


class ProfitHistoryPruneMySQLTests(unittest.TestCase):
    def _run_prune(self) -> list:
        conn = _FakeMySQLConnection()
        with mock.patch("database.get_db_connection", return_value=conn), \
                mock.patch("database.using_mysql", return_value=True):
            _prune_profit_history_unlocked()
        return conn.log

    def test_mysql_branch_never_parses_recorded_at(self) -> None:
        log = self._run_prune()
        # cutoff DELETE + 15m + hourly + daily compaction with default windows
        self.assertEqual(len(log), 4)
        for sql, _params in log:
            self.assertNotIn("STR_TO_DATE", sql.upper())

    def test_mysql_branch_buckets_by_substring(self) -> None:
        log = self._run_prune()
        sql_15m, sql_hourly, sql_daily = log[1][0], log[2][0], log[3][0]
        self.assertIn("SUBSTRING(recorded_at, 1, 13)", sql_15m)
        self.assertIn("SUBSTRING(recorded_at, 15, 2)", sql_15m)
        self.assertIn("SUBSTRING(recorded_at, 1, 13)", sql_hourly)
        self.assertIn("SUBSTRING(recorded_at, 1, 10)", sql_daily)

    def test_substring_buckets_ignore_microsecond_suffix(self) -> None:
        # The ISO string is fixed-width through the seconds, so the bucket
        # keys must be byte-identical for both stored formats.
        import sqlite3

        conn = sqlite3.connect(":memory:")
        for start, length in ((1, 13), (15, 2), (1, 10)):
            plain, micros = (
                conn.execute(
                    "SELECT SUBSTRING(?, ?, ?)", (ts, start, length)
                ).fetchone()[0]
                for ts in (TS_PLAIN, TS_MICROS)
            )
            self.assertEqual(plain, micros)
        self.assertEqual(
            conn.execute("SELECT SUBSTRING(?, 15, 2)", (TS_MICROS,)).fetchone()[0],
            "20",
        )
        conn.close()


if __name__ == "__main__":
    unittest.main()
