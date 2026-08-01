"""The qa-* leaderboard filter, and the escape-char regression that 500'd
/api/profit/history on prod (2026-08-01): ESCAPE '\\' is legal SQLite but a
1064 syntax error inside a MySQL string literal. The predicate must contain
no backslash at all, and must actually EXECUTE — not just read plausibly."""
import importlib
import sqlite3
import unittest
from unittest.mock import patch

import leaderboard_snapshot as lb


class EscapeRegression(unittest.TestCase):
    def test_predicate_contains_no_backslash(self):
        """Backslash inside a quoted SQL literal means MySQL and SQLite parse
        the SAME text differently — the exact prod 500. Zero tolerance."""
        sql = lb._not_test_agent("a")
        self.assertNotIn("\\", sql)

    def test_predicate_executes_and_filters(self):
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE agents (id INTEGER, name TEXT, user_id INTEGER)")
        rows = [(1, "qa-oi-live-1", 5), (2, "info", 5), (3, "alice", 9),
                (4, "qantas-fan", 7)]  # 'qa' prefix but not 'qa-' — must stay
        conn.executemany("INSERT INTO agents VALUES (?,?,?)", rows)
        kept = {r[0] for r in conn.execute(
            f"SELECT name FROM agents a WHERE {lb._not_test_agent('a')}")}
        self.assertEqual(kept, {"info", "alice", "qantas-fan"})

    def test_wildcards_in_prefix_are_literal(self):
        """A configured prefix containing % or _ must not become a wildcard."""
        with patch.object(lb, "_EXCLUDE_NAME_PREFIXES", ["q_%"]):
            conn = sqlite3.connect(":memory:")
            conn.execute("CREATE TABLE agents (id INTEGER, name TEXT)")
            conn.executemany("INSERT INTO agents VALUES (?,?)",
                             [(1, "q_%bot"), (2, "qXbot")])
            kept = {r[0] for r in conn.execute(
                f"SELECT name FROM agents a WHERE {lb._not_test_agent('a')}")}
            # only the literal 'q_%' prefix drops; 'qXbot' survives
            self.assertEqual(kept, {"qXbot"})

    def test_empty_config_is_inert(self):
        with patch.object(lb, "_EXCLUDE_NAME_PREFIXES", []):
            self.assertEqual(lb._not_test_agent("a"), "1=1")

    def test_rankable_where_embeds_the_filter(self):
        self.assertIn("NOT LIKE 'qa-%'", lb.rankable_where("a"))

    def test_env_override_reloads(self):
        with patch.dict("os.environ",
                        {"LEADERBOARD_EXCLUDE_NAME_PREFIXES": "test-,demo-"}):
            importlib.reload(lb)
            sql = lb._not_test_agent("a")
        importlib.reload(lb)  # restore default for other tests
        self.assertIn("test-", sql)
        self.assertIn("demo-", sql)
        self.assertNotIn("qa-", sql)


if __name__ == "__main__":
    unittest.main()
