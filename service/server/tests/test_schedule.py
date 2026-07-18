"""Plan 06 C3 — trading-window schedules."""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from schedule import in_window, parse_schedule


def _utc(y, m, d, h):
    return datetime(y, m, d, h, 0, tzinfo=timezone.utc)


class ParseTests(unittest.TestCase):
    def test_empty_is_none(self):
        self.assertIsNone(parse_schedule(None))
        self.assertIsNone(parse_schedule(""))
        self.assertIsNone(parse_schedule("   "))

    def test_valid_normalized(self):
        s = parse_schedule('{"days":[2,0,0],"start_hour":9,"end_hour":17,"tz":"Asia/Seoul"}')
        self.assertEqual(s["days"], [0, 2])           # deduped + sorted
        self.assertEqual(s["start_hour"], 9)
        self.assertEqual(s["end_hour"], 17)
        self.assertEqual(s["tz"], "Asia/Seoul")

    def test_defaults(self):
        s = parse_schedule('{"tz":"UTC"}')
        self.assertEqual(s["days"], [])
        self.assertEqual(s["start_hour"], 0)
        self.assertEqual(s["end_hour"], 24)

    def test_dict_input(self):
        s = parse_schedule({"days": [1], "start_hour": 8, "end_hour": 20, "tz": "UTC"})
        self.assertEqual(s["days"], [1])

    def test_invalid_rejected(self):
        for bad in ('{"days":[9]}', '{"start_hour":25}', '{"tz":"Mars/Base"}',
                    "not json", '["a","b"]'):
            with self.assertRaises(ValueError):
                parse_schedule(bad)


class WindowTests(unittest.TestCase):
    def test_no_schedule_always_open(self):
        self.assertTrue(in_window(None, _utc(2026, 7, 17, 3)))

    def test_hour_window_utc(self):
        s = {"days": [], "start_hour": 9, "end_hour": 17, "tz": "UTC"}
        self.assertTrue(in_window(s, _utc(2026, 7, 17, 10)))
        self.assertFalse(in_window(s, _utc(2026, 7, 17, 8)))
        self.assertFalse(in_window(s, _utc(2026, 7, 17, 17)))   # end exclusive

    def test_day_filter(self):
        # 2026-07-17 is a Friday (weekday 4)
        fri = _utc(2026, 7, 17, 10)
        self.assertTrue(in_window({"days": [4], "start_hour": 0, "end_hour": 24, "tz": "UTC"}, fri))
        self.assertFalse(in_window({"days": [0, 1], "start_hour": 0, "end_hour": 24, "tz": "UTC"}, fri))

    def test_timezone_shift(self):
        # 03:00 UTC == 12:00 KST (UTC+9)
        s = {"days": [], "start_hour": 9, "end_hour": 18, "tz": "Asia/Seoul"}
        self.assertTrue(in_window(s, _utc(2026, 7, 17, 3)))    # 12:00 KST -> open
        self.assertFalse(in_window(s, _utc(2026, 7, 17, 20)))  # 05:00 KST next day -> closed

    def test_overnight_wrap(self):
        s = {"days": [], "start_hour": 22, "end_hour": 6, "tz": "UTC"}
        self.assertTrue(in_window(s, _utc(2026, 7, 17, 23)))
        self.assertTrue(in_window(s, _utc(2026, 7, 17, 2)))
        self.assertFalse(in_window(s, _utc(2026, 7, 17, 12)))

    def test_malformed_defaults_open(self):
        self.assertTrue(in_window({"start_hour": "bad"}, _utc(2026, 7, 17, 3)))


class TickIntegrationTests(unittest.TestCase):
    """The automation tick treats out-of-window rules as not due."""

    def setUp(self):
        import os
        import tempfile
        import database
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        conn = database.get_db_connection()
        conn.execute(
            "INSERT INTO agents (name, password_hash, token, cash) VALUES ('sch','x','t',100000.0)")
        self.agent_id = conn.execute("SELECT id FROM agents LIMIT 1").fetchone()["id"]
        conn.commit()
        conn.close()
        self._db = database

    def tearDown(self):
        self.tmp.cleanup()

    def _add_rule(self, schedule_json):
        conn = self._db.get_db_connection()
        conn.execute(
            """INSERT INTO automation_configs
               (agent_id, symbol, market, interval_minutes, min_confidence, size_usd,
                auto_execute, account_type, enabled, lang, mode, schedule_json)
               VALUES (?, 'BTC', 'crypto', 60, 0.65, 500, 0, 'simulator', 1, 'en', 'manual', ?)""",
            (self.agent_id, schedule_json))
        conn.commit()
        conn.close()

    def test_out_of_window_rule_not_run(self):
        import json
        from unittest.mock import patch
        import automation
        # Monday-only rule; run the tick on a Friday-equivalent instant.
        self._add_rule(json.dumps({"days": [0], "start_hour": 0, "end_hour": 24, "tz": "UTC"}))
        fri = _utc(2026, 7, 17, 10)  # Friday
        with patch("automation.datetime") as mock_dt:
            mock_dt.now.return_value = fri
            with patch.object(automation, "run_rule") as mock_run:
                result = automation.run_automation_tick()
        mock_run.assert_not_called()
        self.assertEqual(result["due"], 0)

    def test_in_window_rule_runs(self):
        import json
        from unittest.mock import patch
        import automation
        self._add_rule(json.dumps({"days": [4], "start_hour": 0, "end_hour": 24, "tz": "UTC"}))
        fri = _utc(2026, 7, 17, 10)  # Friday (weekday 4)
        with patch("automation.datetime") as mock_dt:
            mock_dt.now.return_value = fri
            with patch.object(automation, "run_rule", return_value={"executed": False}) as mock_run:
                automation.run_automation_tick()
        mock_run.assert_called_once()


if __name__ == "__main__":
    unittest.main()
