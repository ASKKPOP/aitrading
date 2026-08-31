"""No-prospect switch rail (owner 2026-08-31): a FLAT run whose desk keeps
answering `hold` for the configured window (1–5h band) is switched out —
`_evaluate_stop` returns `no_prospect_switched` and the fleet replaces the
slot with a different symbol (vary-cooldown). Applies to traded-then-flat
runs as well as never-traded ones; never to an open position."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
import run_engine


def _iso(hours_ago: float) -> str:
    return (datetime.now(timezone.utc)
            - timedelta(hours=hours_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _run(run_id=901, trades=0):
    return {"id": run_id, "agent_id": 6, "symbol": "NVDA",
            "market": "us-stock", "status": "running",
            # below the idle-retire limit so only the new rail can fire
            "cycle_seq": 3,
            "config_snapshot_json": json.dumps(
                {"symbol": "NVDA", "market": "us-stock",
                 "thesis": {"expected_move_pct": 5.0}}),
            "stop_conditions_json": "{}"}


class NoProspectSwitchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "t.db")
        database.init_database()
        self._seq = 0

    def tearDown(self):
        self.tmp.cleanup()
        for k in ("RUN_NO_PROSPECT_SWITCH", "RUN_NO_PROSPECT_SWITCH_HOURS"):
            os.environ.pop(k, None)

    def _decision(self, run_id, hours_ago, action="hold"):
        conn = database.get_db_connection()
        cur = conn.cursor()
        self._seq += 1
        cur.execute(
            "INSERT INTO run_events (run_id, seq, event_type, ts, payload) "
            "VALUES (?, ?, 'decision', ?, ?)",
            (run_id, self._seq, _iso(hours_ago),
             json.dumps({"action": action, "confidence": 0.6})))
        conn.commit()
        conn.close()

    def _trade(self, run_id, hours_ago):
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO signals (signal_id, agent_id, run_id, message_type, "
            "market, symbol, side, timestamp, created_at, executed_at) "
            "VALUES (?, 6, ?, 'operation', 'us-stock', 'NVDA', 'buy', ?, ?, ?)",
            (7000 + self._seq, run_id, self._seq, _iso(hours_ago),
             _iso(hours_ago)))
        conn.commit()
        conn.close()

    def _evaluate(self, run, trades=0, position=None):
        pnl = {"total": 0.0, "realized": 0.0, "trades": trades,
               "mark_age_ok": True, "position": position}
        with patch.object(run_engine, "compute_run_pnl", return_value=pnl):
            return run_engine._evaluate_stop(run)

    # ── the rail fires ──────────────────────────────────────────────────

    def test_sustained_flat_holds_switch_the_slot(self):
        run = _run()
        for h in (3.5, 2.5, 1.5, 0.5):
            self._decision(run["id"], h)
        self.assertEqual(self._evaluate(run), "no_prospect_switched")

    def test_traded_then_flat_run_is_covered_too(self):
        # The never-traded rails skip a run with trades > 0 — this rail
        # must not (that is the gap the owner named: "each slot").
        run = _run(run_id=902)
        self._trade(run["id"], hours_ago=10)
        for h in (3.5, 2.5, 1.5, 0.5):
            self._decision(run["id"], h)
        self.assertEqual(self._evaluate(run, trades=2), "no_prospect_switched")

    # ── the rail stays quiet ────────────────────────────────────────────

    def test_entry_intent_breaks_the_streak(self):
        run = _run(run_id=903)
        self._decision(run["id"], 3.5)
        self._decision(run["id"], 2.5)
        self._decision(run["id"], 1.5, action="buy")   # desk sees a prospect
        self._decision(run["id"], 0.5)
        self.assertIsNone(self._evaluate(run))

    def test_holds_that_managed_a_position_never_count(self):
        # 4h of holds, but the run's last trade executed 1h ago (the close
        # that made it flat) — every hold before it managed a live book.
        run = _run(run_id=904)
        for h in (4.0, 3.0, 2.0):
            self._decision(run["id"], h)
        self._trade(run["id"], hours_ago=1.0)
        self._decision(run["id"], 0.5)
        self.assertIsNone(self._evaluate(run, trades=2))

    def test_short_span_or_few_decisions_do_not_fire(self):
        run = _run(run_id=905)
        for h in (1.5, 1.0, 0.5):     # 3 holds but only ~1.5h span
            self._decision(run["id"], h)
        self.assertIsNone(self._evaluate(run))
        run2 = _run(run_id=906)
        self._decision(run2["id"], 4.0)   # long span but 2 decisions
        self._decision(run2["id"], 0.5)
        self.assertIsNone(self._evaluate(run2))

    def test_open_position_is_never_switched(self):
        run = _run(run_id=907)
        for h in (4.0, 3.0, 2.0, 1.0):
            self._decision(run["id"], h)
        pos = {"quantity": 1.0, "entry_price": 100.0, "current_price": 101.0,
               "leverage": 1}
        self.assertIsNone(self._evaluate(run, trades=1, position=pos))

    def test_kill_switch(self):
        os.environ["RUN_NO_PROSPECT_SWITCH"] = "0"
        run = _run(run_id=908)
        for h in (4.0, 3.0, 2.0, 1.0):
            self._decision(run["id"], h)
        self.assertIsNone(self._evaluate(run))

    # ── config band ─────────────────────────────────────────────────────

    def test_hours_env_is_clamped_to_the_owner_band(self):
        os.environ["RUN_NO_PROSPECT_SWITCH_HOURS"] = "0.2"
        self.assertEqual(run_engine._no_prospect_switch_hours(), 1.0)
        os.environ["RUN_NO_PROSPECT_SWITCH_HOURS"] = "9"
        self.assertEqual(run_engine._no_prospect_switch_hours(), 5.0)
        os.environ["RUN_NO_PROSPECT_SWITCH_HOURS"] = "junk"
        self.assertEqual(run_engine._no_prospect_switch_hours(), 3.0)

    def test_reason_is_classified_for_replacement_and_vary(self):
        import fleet_planner as fp
        self.assertIn("no_prospect_switched", fp.REPLACE_IMMEDIATE)


if __name__ == "__main__":
    unittest.main()
