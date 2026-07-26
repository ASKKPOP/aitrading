"""Fleet-level take-profit + auto-restart (2026-07-26).

Runs already restart on their own profit_target (REPLACE_IMMEDIATE — a banked
member is replaced in its slot). What was missing is the FLEET-level goal:
"when the whole fleet reaches my target profit, bank everything and start the
same trading again". profit_target_frac on the fleet does exactly that:
flatten every member, finalize the fleet as profit_target_hit, then compose a
SUCCESSOR fleet with identical settings (profit harvested — the successor gets
the original budget, not the swollen equity).
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
import fleet_planner as fp
import fleet_supervisor as fs
import trading_runs

from test_fleet_supervision import SupervisionBase


class ProfitTargetTests(SupervisionBase):
    def _fleet_with_target(self, target=0.10, n=2, budget=2000.0):
        return self._built_fleet(n=n, budget=budget, profit_target_frac=target)

    def _equity(self, fleet_id, gain_frac):
        fleet = fp.get_fleet(fleet_id)
        total = float(fleet["total_budget_usd"])
        return patch.object(fs.fp, "marked_equity",
                            return_value={"equity": total * (1 + gain_frac),
                                          "ok": True, "zombie_basis": 0.0,
                                          "pnl": total * gain_frac})

    def _successor(self, fleet_id):
        return fp.get_fleet(fleet_id).get("successor_fleet_id")

    def test_below_target_does_nothing(self):
        fleet_id = self._fleet_with_target(0.10)
        with self._equity(fleet_id, 0.05):
            fs.supervise_fleet(fp.get_fleet(fleet_id))
        self.assertEqual(fp.get_fleet(fleet_id)["status"], fp.STATUS_ACTIVE)
        self.assertIsNone(self._successor(fleet_id))

    def test_target_hit_flattens_and_finalizes(self):
        fleet_id = self._fleet_with_target(0.10)
        with self._equity(fleet_id, 0.12):
            fs.supervise_fleet(fp.get_fleet(fleet_id))
        fleet = fp.get_fleet(fleet_id)
        self.assertIn(fleet["status"], (fp.STATUS_STOPPING, fp.STATUS_STOPPED))
        self.assertEqual(fleet["status_reason"], "profit_target_hit")
        for m in fp.list_members(fleet_id):
            self.assertNotEqual(m["status"], trading_runs.STATUS_RUNNING)

    def test_successor_started_with_same_settings_and_original_budget(self):
        fleet_id = self._fleet_with_target(0.10, n=2, budget=2000.0)
        old = fp.get_fleet(fleet_id)
        with self._equity(fleet_id, 0.12):
            fs.supervise_fleet(fp.get_fleet(fleet_id))       # flatten
            fs.supervise_fleet(fp.get_fleet(fleet_id))       # finalize + spawn
        succ_id = self._successor(fleet_id)
        self.assertIsNotNone(succ_id, "successor fleet not created")
        succ = fp.get_fleet(succ_id)
        self.assertEqual(int(succ["n_runs"]), int(old["n_runs"]))
        self.assertAlmostEqual(float(succ["total_budget_usd"]),
                               float(old["total_budget_usd"]), places=2)
        self.assertEqual(succ["risk_appetite"], old["risk_appetite"])
        self.assertAlmostEqual(float(succ["profit_target_frac"]), 0.10, places=4)
        self.assertNotEqual(succ["status"], fp.STATUS_DRAFT)  # started

    def test_successor_spawn_is_idempotent(self):
        """A re-entrant finalize (racing workers, a re-stopped fleet) must not
        spawn a second successor — _spawn_successor is called directly here
        because a stopped fleet is no longer supervised."""
        fleet_id = self._fleet_with_target(0.10)
        with self._equity(fleet_id, 0.12):
            fs.supervise_fleet(fp.get_fleet(fleet_id))       # flatten
            fs.supervise_fleet(fp.get_fleet(fleet_id))       # finalize + spawn
        first = self._successor(fleet_id)
        self.assertIsNotNone(first)
        # call the spawn path again, exactly as a duplicate finalize would
        again = fs._spawn_successor(fp.get_fleet(fleet_id))
        self.assertIsNone(again, "duplicate finalize spawned another fleet")
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) n FROM fleets WHERE agent_id = ?",
                    (self.agent_id,))
        total = cur.fetchone()["n"]
        conn.close()
        self.assertEqual(total, 2, "spawned more than one successor")
        self.assertEqual(self._successor(fleet_id), first)
        # the guard must SHORT-CIRCUIT: no create attempt, so no error event.
        # (Without it the one-active-fleet UNIQUE would still block the
        # duplicate, but noisily — a raised FleetConflict per finalize.)
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) n FROM fleet_events WHERE fleet_id = ? "
                    "AND event_type = 'successor_failed'", (fleet_id,))
        failures = cur.fetchone()["n"]
        conn.close()
        self.assertEqual(failures, 0, "duplicate finalize raised instead of "
                                      "short-circuiting")

    def test_disabled_when_target_is_none(self):
        fleet_id = self._built_fleet(n=2)                    # no target
        with self._equity(fleet_id, 0.50):
            fs.supervise_fleet(fp.get_fleet(fleet_id))
        self.assertEqual(fp.get_fleet(fleet_id)["status"], fp.STATUS_ACTIVE)

    def test_loss_rail_still_wins_over_gain_path(self):
        """A breach must stop-all as a breaker, never be read as a gain."""
        fleet_id = self._fleet_with_target(0.10)
        with self._equity(fleet_id, -0.45):                  # −45% loss
            fs.supervise_fleet(fp.get_fleet(fleet_id))
        fleet = fp.get_fleet(fleet_id)
        self.assertEqual(fleet["status_reason"], "breaker")

    def test_create_validates_target_bounds(self):
        with self.assertRaises(ValueError):
            fp.create_fleet(self.agent_id, 2, 2000.0, profit_target_frac=0.0)
        with self.assertRaises(ValueError):
            fp.create_fleet(self.agent_id, 2, 2000.0, profit_target_frac=6.0)


if __name__ == "__main__":
    import unittest
    unittest.main()
