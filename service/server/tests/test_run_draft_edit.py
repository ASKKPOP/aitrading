"""Editing a draft run (trading_runs.update_draft_run).

The exclusivity rule refuses a second run whose agent+market+symbol+filter_key
matches a live one, and the fix is to change one of the four differentiating
settings. Before editing existed the user had to delete the draft and rebuild
it from scratch; these tests pin the edit path and, more importantly, the
boundary — a run that has started must never be re-configured underneath its
own open book.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
import trading_runs


def _settings(**over) -> dict:
    base = {"symbol": "BTC", "market": "crypto", "market_type": "spot",
            "max_bet_usd": 100.0, "run_budget_usd": None,
            "interval_minutes": 60, "min_confidence": 0.7,
            "provider": "openai", "lang": "ko", "leverage": 1.0}
    base.update(over)
    return base


class DraftEditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO agents (id, name, token, cash, created_at) "
            "VALUES (1, 'editor', 'claw_editor', 100000, '2026-01-01T00:00:00Z')")
        cur.execute(
            "INSERT INTO agents (id, name, token, cash, created_at) "
            "VALUES (2, 'other', 'claw_other', 100000, '2026-01-01T00:00:00Z')")
        conn.commit()
        conn.close()

    def tearDown(self):
        self.tmp.cleanup()

    def _draft(self, agent_id: int = 1, **over) -> int:
        return trading_runs.create_run(
            agent_id, _settings(**over), {"type": "manual"}, {}, True)

    def _row(self, run_id: int) -> dict:
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM trading_runs WHERE id = ?", (run_id,))
        row = dict(cur.fetchone())
        conn.close()
        return row

    # ── the edit itself ────────────────────────────────────────────────

    def test_edit_replaces_the_config_snapshot(self):
        run_id = self._draft()
        trading_runs.update_draft_run(
            run_id, 1, _settings(interval_minutes=15, min_confidence=0.55,
                                 provider="gemini"),
            {"type": "manual"}, {}, True)
        cfg = json.loads(self._row(run_id)["config_snapshot_json"])
        self.assertEqual(cfg["interval_minutes"], 15)
        self.assertEqual(cfg["min_confidence"], 0.55)
        self.assertEqual(cfg["provider"], "gemini")

    def test_edit_can_change_symbol_market_and_type(self):
        """A draft has no book, so even the instrument is still free."""
        run_id = self._draft()
        trading_runs.update_draft_run(
            run_id, 1, _settings(symbol="ETH", market_type="futures"),
            {"type": "manual"}, {}, True)
        row = self._row(run_id)
        self.assertEqual(row["symbol"], "ETH")
        self.assertEqual(row["market_type"], "futures")

    def test_edit_changes_the_filter_key_so_a_clash_can_be_resolved(self):
        """The whole point: same symbol, two runs, once the settings differ."""
        first = self._draft()
        trading_runs.start_run(first, 1)

        second = self._draft()
        with self.assertRaises(trading_runs.StartConflict):
            trading_runs.start_run(second, 1)

        trading_runs.update_draft_run(
            second, 1, _settings(interval_minutes=15), {"type": "manual"}, {}, True)
        trading_runs.start_run(second, 1)   # must no longer collide

        self.assertEqual(self._row(second)["status"], trading_runs.STATUS_RUNNING)
        self.assertNotEqual(self._row(first)["active_key"],
                            self._row(second)["active_key"])

    def test_edit_emits_a_journal_event(self):
        run_id = self._draft()
        trading_runs.update_draft_run(
            run_id, 1, _settings(provider="grok"), {"type": "manual"}, {}, True)
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT event_type FROM run_events WHERE run_id = ?", (run_id,))
        kinds = [dict(r)["event_type"] for r in cur.fetchall()]
        conn.close()
        self.assertIn("run_config", kinds)

    def test_stop_flatten_and_conditions_are_replaced(self):
        run_id = self._draft()
        trading_runs.update_draft_run(
            run_id, 1, _settings(), {"type": "manual"},
            {"take_profit_pct": 5.0}, False)
        row = self._row(run_id)
        self.assertEqual(json.loads(row["stop_conditions_json"]),
                         {"take_profit_pct": 5.0})
        self.assertFalse(row["stop_flatten"])

    # ── the boundary ───────────────────────────────────────────────────

    def test_running_run_cannot_be_edited(self):
        run_id = self._draft()
        trading_runs.start_run(run_id, 1)
        with self.assertRaises(ValueError):
            trading_runs.update_draft_run(
                run_id, 1, _settings(interval_minutes=15),
                {"type": "manual"}, {}, True)
        cfg = json.loads(self._row(run_id)["config_snapshot_json"])
        self.assertEqual(cfg["interval_minutes"], 60, "config must be untouched")

    def test_run_on_its_way_out_cannot_be_edited(self):
        run_id = self._draft()
        trading_runs.start_run(run_id, 1)
        trading_runs.request_stop(run_id, 1, flatten=False)
        self.assertNotEqual(self._row(run_id)["status"], trading_runs.STATUS_DRAFT)
        with self.assertRaises(ValueError):
            trading_runs.update_draft_run(
                run_id, 1, _settings(), {"type": "manual"}, {}, True)

    def test_another_agents_draft_is_not_found(self):
        """Cross-tenant edit is a miss, not a permission error — the same
        ownership predicate every other run endpoint carries."""
        run_id = self._draft(agent_id=2)
        with self.assertRaises(LookupError):
            trading_runs.update_draft_run(
                run_id, 1, _settings(), {"type": "manual"}, {}, True)
        cfg = json.loads(self._row(run_id)["config_snapshot_json"])
        self.assertEqual(cfg["provider"], "openai", "config must be untouched")

    def test_missing_run_is_not_found(self):
        with self.assertRaises(LookupError):
            trading_runs.update_draft_run(
                99999, 1, _settings(), {"type": "manual"}, {}, True)


if __name__ == "__main__":
    unittest.main()
