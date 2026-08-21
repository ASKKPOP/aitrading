"""The desk was told the WRONG deadline (2026-08-21).

`_run_expiry_line` hands the desk `stop_conditions.at_time` — the run's hard
end-of-life — and instructs it to "author horizons and targets against the
REMAINING life". But a never-traded run is collected far earlier by the
idle-retire rail (RUN_IDLE_RETIRE_CYCLES, 12 worked cycles), and NO brief
line carried that deadline.

Live prod, 2026-08-21T08:06Z anchor. Every idle-retired crypto run:

    run 1620 KAITO  cycle_seq 12  at_time budget 23.98h  actual life 5.37h
    run 1619 ETH    cycle_seq 12  at_time budget 24.00h  actual life 5.52h
    run 1612 LTC    cycle_seq 12  at_time budget 47.98h  actual life 5.38h
    run 1569 KAITO  cycle_seq 12  at_time budget 72.00h  actual life 5.05h

The desk read "23h 58m remaining" and published plans with horizon_hours of
24/48/72 (362/126/52 outlooks since 08-17) on a vehicle with ~5.2h of life.
It then held every cycle waiting for a zone the run would never live to see.
196 of 234 runs stopped since 08-18 (83.8%) died `idle_retired` — never
trading once — burning ~1000 desk cycles a day.

This is the same defect class as #244 (the desk could not see the rail that
retired it). Fix: the brief must carry the BINDING deadline, not the loosest
one. Fact + rule; the verb stays the desk's (§7b).
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
import run_engine


class EntryWindowBriefTests(unittest.TestCase):
    """The idle-retire deadline must reach the desk."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "t.db")
        database.init_database()
        self._env = os.environ.get("RUN_IDLE_RETIRE_CYCLES")
        os.environ["RUN_IDLE_RETIRE_CYCLES"] = "12"

    def tearDown(self):
        self.tmp.cleanup()
        if self._env is None:
            os.environ.pop("RUN_IDLE_RETIRE_CYCLES", None)
        else:
            os.environ["RUN_IDLE_RETIRE_CYCLES"] = self._env

    def _trade(self, run_id):
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO run_events (run_id, seq, event_type, ts, payload) "
            "VALUES (?, 1, 'trade', '2026-08-21T00:00:00Z', ?)",
            (run_id, json.dumps({"side": "short", "symbol": "ETHUSDT"})))
        conn.commit()
        conn.close()

    @staticmethod
    def _run(cycle_seq=6, run_id=1619, at_time="2030-01-01T00:00:00Z",
             started="2026-08-21T02:23:05Z", last="2026-08-21T04:53:05Z"):
        return {"id": run_id, "agent_id": 6, "symbol": "ETHUSDT",
                "market": "crypto", "status": "running",
                "cycle_seq": cycle_seq, "started_at": started,
                "last_cycle_at": last,
                "stop_conditions_json": json.dumps({"at_time": at_time})}

    # ---- the defect ----------------------------------------------------

    def test_the_1619_case_the_desk_must_see_the_entry_window(self):
        """Run 1619's exact shape: a 24h at_time on a ~5.2h vehicle."""
        line = run_engine._run_expiry_line(self._run(cycle_seq=6))
        self.assertIn("6 more no-trade cycles", line,
                      "remaining no-trade cycles not stated")
        self.assertIn("entry window", line.lower(),
                      "the idle-retire deadline never reaches the desk")

    def test_it_names_the_idle_rail_as_the_binding_deadline(self):
        """A 24h at_time must not be presented as the operative budget."""
        line = run_engine._run_expiry_line(self._run(cycle_seq=6))
        low = line.lower()
        self.assertTrue("sooner" in low or "before" in low or "binds" in low,
                        "the tighter deadline is not identified as binding")

    def test_a_run_that_already_traded_gets_no_entry_window(self):
        """The idle rail is permanently off once the run has traded."""
        self._trade(1619)
        line = run_engine._run_expiry_line(self._run(cycle_seq=6))
        self.assertNotIn("entry window", line.lower())
        self.assertIn("HARD-ENDS", line, "the at_time fact must survive")

    def test_closed_market_cycles_are_not_charged(self):
        """Same discount the rail itself applies (see _closed_market_cycles)."""
        conn = database.get_db_connection()
        cur = conn.cursor()
        for i in range(4):
            cur.execute(
                "INSERT INTO run_events (run_id, seq, event_type, ts, payload)"
                " VALUES (?, ?, 'gate_skip', ?, ?)",
                (1590, 100 + i, f"2026-08-21T0{i}:00:00Z",
                 json.dumps({"cycle": i + 1, "stage": "pre",
                             "reason": "market closed"})))
        conn.commit()
        conn.close()
        run = self._run(cycle_seq=10, run_id=1590)
        run["market"] = "us-stock"
        line = run_engine._run_expiry_line(run)
        # worked = 10 - 4 = 6 -> 6 cycles left of 12. Asserted as the exact
        # phrase: "6" alone also matches the "~0.6h" pace figure, which let
        # a discount-dropping mutant survive.
        self.assertIn("6 more no-trade cycles", line)
        self.assertNotIn("2 more no-trade cycles", line)

    def test_rail_disabled_renders_no_entry_window(self):
        os.environ["RUN_IDLE_RETIRE_CYCLES"] = "0"
        line = run_engine._run_expiry_line(self._run(cycle_seq=6))
        self.assertNotIn("entry window", line.lower())

    def test_budget_already_spent_renders_no_entry_window(self):
        line = run_engine._run_expiry_line(self._run(cycle_seq=12))
        self.assertNotIn("entry window", line.lower())

    def test_the_window_must_not_read_as_pressure_to_trade(self):
        """A truthful deadline must not become a reason to trade.

        Counterfactual, run 1577 TRUMPUSDT (2026-08-20): it published a
        SHORT zone 1.6796-1.713192 and was idle_retired at 16:30Z. Price
        DID enter that zone afterwards (4 of 8 observations) — but then ran
        to 1.7226, through the plan's own 1.72 stop. The forfeited entry
        would have LOST ~0.6% after fees. Declined entries measure about
        -0.24%/trade gross, below the fee hurdle: the desk's declines are
        approximately right. So this line must offer the decline explicitly
        or it converts a fixed fact into rushed, negative-expectancy fills.
        """
        line = run_engine._run_expiry_line(self._run(cycle_seq=6)).lower()
        self.assertIn("not a reason to trade", line)
        self.assertIn("fee donation", line)
        self.assertIn("let the slot go early", line)

    # ---- it must not regress the at_time line -------------------------

    def test_no_at_time_still_renders_the_entry_window(self):
        """The idle deadline exists whether or not at_time does."""
        run = self._run(cycle_seq=6)
        run["stop_conditions_json"] = "{}"
        line = run_engine._run_expiry_line(run)
        self.assertIn("entry window", line.lower())

    def test_a_run_that_has_not_cycled_renders_nothing_new(self):
        run = self._run(cycle_seq=0)
        run["stop_conditions_json"] = "{}"
        self.assertEqual(run_engine._run_expiry_line(run), "")

    def test_garbage_never_raises(self):
        for bad in ({"id": 1}, {"id": 1, "cycle_seq": "x"},
                    {"id": 1, "cycle_seq": 5, "stop_conditions_json": "nope"}):
            run_engine._run_expiry_line(bad)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
