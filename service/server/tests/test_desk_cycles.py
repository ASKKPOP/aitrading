"""30-minute desk cycles — the AI Analysis list (read-side composition).

The journal is the source: these tests write the same rows Sooppiy AI writes
each cycle (decision / gate_skip / equity / run_status) and assert the grid
folds them the way the automation page reads them.

Covers: bucket alignment; the desk's WRITTEN report reaching the response
(it was stored and never rendered before); per-cycle realized deltas against
a pre-window baseline; carry-forward through a quiet cycle; opened/closed
counted from transitions; another agent's runs never appearing; auth.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
import desk_cycles
import trading_runs
from routes import create_app


def _ts(dt: datetime) -> str:
    return dt.strftime(trading_runs.TS_FMT)


class DeskCycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())
        resp = self.client.post(
            "/api/claw/agents/selfRegister",
            json={"name": "cycle-agent", "password": "pw123",
                  "initial_balance": 100000.0})
        assert resp.status_code == 200, resp.text
        self.token = resp.json()["token"]
        self.agent_id = resp.json()["agent_id"]
        # Anchor "now" INSIDE a cycle (03:00–03:30), which is where it always
        # is in practice: the newest entry is the cycle in progress. Exactly
        # on a boundary the newest entry is a legitimately empty just-opened
        # cycle — correct, but not what these tests are measuring.
        self.now = datetime(2026, 8, 6, 3, 10, 0, tzinfo=timezone.utc)
        self.seq = 0

    def tearDown(self):
        self.tmp.cleanup()

    # ── journal helpers ───────────────────────────────────────────────────
    def _run(self, run_id: int, symbol: str = "BTC", agent_id: int | None = None,
             status: str = "running", peak: float | None = None) -> int:
        conn = database.get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO trading_runs
                       (id, agent_id, symbol, market, status, peak_pnl_usd, created_at)
                   VALUES (?, ?, ?, 'crypto', ?, ?, ?)""",
                (run_id, agent_id or self.agent_id, symbol, status, peak,
                 _ts(self.now - timedelta(days=1))))
            conn.commit()
        finally:
            conn.close()
        return run_id

    def _event(self, run_id: int, kind: str, payload: dict, at: datetime) -> None:
        self.seq += 1
        conn = database.get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO run_events (run_id, seq, event_type, ts, payload)
                   VALUES (?, ?, ?, ?, ?)""",
                (run_id, self.seq, kind, _ts(at), json.dumps(payload)))
            conn.commit()
        finally:
            conn.close()

    def _cycles(self, count: int = 4) -> list[dict]:
        return desk_cycles.agent_cycles(self.agent_id, count, now=self.now)

    # ── the grid ──────────────────────────────────────────────────────────
    def test_cycle_start_floors_onto_the_thirty_minute_grid(self):
        for minute, expected in ((0, 0), (7, 0), (29, 0), (30, 30), (59, 30)):
            got = desk_cycles.cycle_start(
                datetime(2026, 8, 6, 2, minute, 41, tzinfo=timezone.utc))
            self.assertEqual(got.minute, expected)
            self.assertEqual((got.second, got.microsecond), (0, 0))

    def test_every_bucket_in_the_window_is_emitted_newest_first(self):
        self._run(985)
        self._event(985, "decision", {"action": "buy", "confidence": 0.7},
                    self.now - timedelta(minutes=10))
        cycles = self._cycles(4)
        self.assertEqual(len(cycles), 4)
        starts = [c["start"] for c in cycles]
        self.assertEqual(starts, sorted(starts, reverse=True))
        # Only the newest bucket saw activity; the rest are quiet but present.
        self.assertFalse(cycles[0]["quiet"])
        self.assertTrue(all(c["quiet"] for c in cycles[1:]))

    def test_the_desk_written_report_reaches_the_cycle_row(self):
        """The regression this feature exists for: the report was journaled
        every cycle and the UI showed only 'buy conf 0.7'."""
        self._run(985, symbol="ZEC")
        self._event(985, "decision",
                    {"action": "buy", "confidence": 0.72, "conviction": 0.61,
                     "report": "Funding flipped negative while the book held its peak."},
                    self.now - timedelta(minutes=5))
        row = self._cycles(2)[0]["runs"][0]
        self.assertEqual(row["run_id"], 985)
        self.assertEqual(row["symbol"], "ZEC")
        self.assertEqual(row["action"], "buy")
        self.assertAlmostEqual(row["confidence"], 0.72)
        self.assertAlmostEqual(row["conviction"], 0.61)
        self.assertIn("Funding flipped negative", row["report"])

    def test_realized_delta_is_measured_against_the_pre_window_baseline(self):
        self._run(985)
        # Before the window: the run had already realized +1.00.
        self._event(985, "equity", {"realized": 1.0, "unrealized": 0.0},
                    self.now - timedelta(hours=6))
        # Inside the newest cycle it reaches +1.25.
        self._event(985, "equity", {"realized": 1.25, "unrealized": 0.10},
                    self.now - timedelta(minutes=5))
        cycles = self._cycles(2)
        newest = cycles[0]
        self.assertAlmostEqual(newest["realized"], 1.25)
        self.assertAlmostEqual(newest["realized_delta"], 0.25)
        self.assertAlmostEqual(newest["unrealized"], 0.10)
        # The older, quiet cycle carries the baseline and moved nothing.
        self.assertAlmostEqual(cycles[1]["realized"], 1.0)
        self.assertAlmostEqual(cycles[1]["realized_delta"], 0.0)

    def test_a_quiet_cycle_carries_the_book_forward(self):
        self._run(985)
        self._event(985, "equity", {"realized": 2.0, "unrealized": 0.5},
                    self.now - timedelta(minutes=65))   # 3 buckets back
        cycles = self._cycles(4)
        # The newer cycles are quiet but still report the standing book.
        self.assertTrue(cycles[0]["quiet"])
        self.assertAlmostEqual(cycles[0]["realized"], 2.0)
        self.assertAlmostEqual(cycles[0]["unrealized"], 0.5)
        self.assertAlmostEqual(cycles[0]["realized_delta"], 0.0)

    def test_preservation_is_realized_over_the_runs_peak(self):
        self._run(985, peak=0.2806)
        self._event(985, "equity", {"realized": 0.2201, "unrealized": 0.0},
                    self.now - timedelta(minutes=5))
        self._event(985, "decision", {"action": "hold", "confidence": 0.5},
                    self.now - timedelta(minutes=5))
        row = self._cycles(2)[0]["runs"][0]
        self.assertAlmostEqual(row["peak"], 0.2806)
        self.assertAlmostEqual(row["preservation"], 0.7844, places=3)

    def test_preservation_floors_at_zero_when_the_peak_was_given_back(self):
        """Prod run 991: peak +0.0852, realized -0.0045 — -5.3% of peak.

        A negative "preservation rate" is not a rate; the run preserved none
        of its peak, which is 0%. The realized figure beside it still shows
        the loss.
        """
        self._run(991, symbol="GC", peak=0.08518493267322495)
        self._event(991, "equity", {"realized": -0.0045, "unrealized": 0.0},
                    self.now - timedelta(minutes=5))
        self._event(991, "decision", {"action": "hold", "confidence": 0.61},
                    self.now - timedelta(minutes=5))
        row = self._cycles(2)[0]["runs"][0]
        self.assertAlmostEqual(row["realized"], -0.0045)
        self.assertEqual(row["preservation"], 0.0)

    def test_preservation_is_none_when_the_run_never_went_up(self):
        self._run(985, peak=None)
        self._event(985, "decision", {"action": "hold", "confidence": 0.5},
                    self.now - timedelta(minutes=5))
        self.assertIsNone(self._cycles(2)[0]["runs"][0]["preservation"])

    def test_skips_are_grouped_with_a_count(self):
        self._run(985)
        for _ in range(3):
            self._event(985, "gate_skip", {"stage": "fee_edge", "reason": "edge below fee"},
                        self.now - timedelta(minutes=5))
        self._event(985, "gate_skip", {"stage": "risk", "reason": "no cash"},
                    self.now - timedelta(minutes=5))
        cycle = self._cycles(2)[0]
        row = cycle["runs"][0]
        self.assertEqual(len(row["skips"]), 2)
        by_reason = {s["reason"]: s for s in row["skips"]}
        self.assertEqual(by_reason["edge below fee"]["count"], 3)
        self.assertEqual(by_reason["edge below fee"]["stage"], "fee_edge")
        self.assertEqual(by_reason["no cash"]["count"], 1)
        self.assertEqual(cycle["skips"], 4)

    def test_opened_and_closed_come_from_transitions(self):
        self._run(985)
        self._run(977, symbol="SOL", status="stopped")
        self._event(985, "run_status", {"from": "armed", "to": "running", "reason": "start"},
                    self.now - timedelta(minutes=8))
        self._event(977, "run_status",
                    {"from": "running", "to": "stopped", "reason": "loss_floor"},
                    self.now - timedelta(minutes=5))
        cycle = self._cycles(2)[0]
        self.assertEqual(cycle["opened"], 1)
        self.assertEqual(cycle["closed"], 1)
        self.assertEqual(cycle["runs_active"], 2)
        closed = [r for r in cycle["runs"] if r["run_id"] == 977][0]
        self.assertEqual(closed["transitions"][0]["reason"], "loss_floor")

    def test_only_runs_touched_this_cycle_get_a_row(self):
        self._run(985)
        self._run(977, symbol="SOL")
        self._event(985, "decision", {"action": "buy", "confidence": 0.7},
                    self.now - timedelta(minutes=5))
        # 977 has window activity, but in an OLDER bucket.
        self._event(977, "equity", {"realized": 3.0, "unrealized": 0.0},
                    self.now - timedelta(minutes=40))
        newest = self._cycles(3)[0]
        self.assertEqual([r["run_id"] for r in newest["runs"]], [985])
        # ...yet its book is still inside the cycle total.
        self.assertAlmostEqual(newest["realized"], 3.0)

    def test_another_agents_runs_are_never_included(self):
        other = self.client.post(
            "/api/claw/agents/selfRegister",
            json={"name": "other-agent", "password": "pw123",
                  "initial_balance": 1000.0}).json()["agent_id"]
        self._run(985, agent_id=other)
        self._event(985, "decision", {"action": "buy", "confidence": 0.9},
                    self.now - timedelta(minutes=5))
        self.assertEqual(self._cycles(2), [])

    def test_no_activity_returns_no_cycles(self):
        self._run(985)
        self.assertEqual(self._cycles(4), [])

    # ── endpoint ──────────────────────────────────────────────────────────
    def _in_current_cycle(self) -> datetime:
        """A timestamp guaranteed to land in the live cycle.

        The endpoint reads the real clock, so seeding at `now - 2min` puts
        the event in the PREVIOUS bucket whenever the suite runs within two
        minutes of a :00/:30 boundary — a 2-in-30 flake. Anchor on the
        current bucket's own start instead.
        """
        return desk_cycles.cycle_start(datetime.now(timezone.utc)) + timedelta(seconds=1)

    def test_endpoint_requires_a_token(self):
        self.assertEqual(self.client.get("/api/automation/ai-analysis").status_code, 401)

    def test_endpoint_returns_the_grid_for_the_signed_in_agent(self):
        self._run(985)
        self._event(985, "decision",
                    {"action": "sell", "confidence": 0.66, "report": "trimming into strength"},
                    self._in_current_cycle())
        resp = self.client.get("/api/automation/ai-analysis?cycles=2",
                               headers={"Authorization": f"Bearer {self.token}"})
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["cycle_minutes"], 30)
        self.assertEqual(len(body["cycles"]), 2)
        row = body["cycles"][0]["runs"][0]
        self.assertEqual(row["action"], "sell")
        self.assertEqual(row["report"], "trimming into strength")

    def test_cycles_parameter_is_clamped(self):
        self._run(985)
        self._event(985, "decision", {"action": "buy", "confidence": 0.7},
                    self._in_current_cycle())
        auth = {"Authorization": f"Bearer {self.token}"}
        over = self.client.get("/api/automation/ai-analysis?cycles=999", headers=auth)
        self.assertEqual(len(over.json()["cycles"]), desk_cycles.MAX_CYCLES)
        under = self.client.get("/api/automation/ai-analysis?cycles=0", headers=auth)
        self.assertEqual(len(under.json()["cycles"]), 1)


if __name__ == "__main__":
    unittest.main()
