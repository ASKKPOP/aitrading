"""H-CONSOL (owner 2026-08-27): FLEET_TARGET_SLOTS consolidates live fleets.

The ZI control (research/zi_control_replay.py, 08-27) showed even long-only
random entries lose after rails+fees at the current per-slot size — the
entry deadlock is structural. The owner ordered slot consolidation to 3–4
bigger slots, executed BY THE DESK'S OWN MACHINERY (the fleet supervisor),
never by a session touching live fleets.

Two behaviors, both env-gated by FLEET_TARGET_SLOTS (default 0 = off):

1. supervise_fleet lowers an active fleet's n_runs toward the target
   (machine call — #437 user_size_cap semantics untouched; the existing
   resize drain then retires excess slots only as they empty).
2. Replacement funding re-anchors to the fleet's CURRENT equal share
   (total / n_runs): the drain alone deletes emptied excess slots but
   never re-anchors survivors, so without this the consolidation is
   cosmetic — 4 slots would keep their old small allocations forever.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import fleet_planner as fp
import fleet_supervisor as fs

from test_fleet_supervision import SupervisionBase


class TargetSlotsEnvTests(unittest.TestCase):
    def tearDown(self):
        os.environ.pop("FLEET_TARGET_SLOTS", None)

    def test_off_by_default(self):
        os.environ.pop("FLEET_TARGET_SLOTS", None)
        self.assertEqual(fs._target_slots(), 0)

    def test_junk_is_off(self):
        os.environ["FLEET_TARGET_SLOTS"] = "banana"
        self.assertEqual(fs._target_slots(), 0)

    def test_set(self):
        os.environ["FLEET_TARGET_SLOTS"] = "4"
        self.assertEqual(fs._target_slots(), 4)


class SlotAnchorTests(unittest.TestCase):
    def tearDown(self):
        os.environ.pop("FLEET_TARGET_SLOTS", None)

    def test_anchor_is_designed_allocation_when_off(self):
        os.environ.pop("FLEET_TARGET_SLOTS", None)
        slot = {"original_allocation_usd": 400.0}
        self.assertEqual(fs._slot_anchor(slot, 10_000.0, 4), 400.0)

    def test_anchor_reanchors_to_equal_share_when_on(self):
        os.environ["FLEET_TARGET_SLOTS"] = "4"
        slot = {"original_allocation_usd": 400.0}
        self.assertEqual(fs._slot_anchor(slot, 10_000.0, 4), 2_500.0)

    def test_anchor_never_shrinks_a_bigger_designed_slot(self):
        os.environ["FLEET_TARGET_SLOTS"] = "4"
        slot = {"original_allocation_usd": 3_000.0}
        self.assertEqual(fs._slot_anchor(slot, 10_000.0, 4), 3_000.0)


class ConsolidationPassTests(SupervisionBase):
    def tearDown(self):
        os.environ.pop("FLEET_TARGET_SLOTS", None)
        super().tearDown()

    def test_supervise_lowers_n_runs_to_target(self):
        fleet_id = self._built_fleet(n=5, budget=5_000.0)
        os.environ["FLEET_TARGET_SLOTS"] = "2"
        fs.supervise_fleet(fp.get_fleet(fleet_id))
        fleet = fp.get_fleet(fleet_id)
        self.assertEqual(int(fleet["n_runs"]), 2)

    def test_supervise_never_raises_n_runs(self):
        fleet_id = self._built_fleet(n=2, budget=2_000.0)
        os.environ["FLEET_TARGET_SLOTS"] = "4"
        fs.supervise_fleet(fp.get_fleet(fleet_id))
        fleet = fp.get_fleet(fleet_id)
        self.assertEqual(int(fleet["n_runs"]), 2,
                         "consolidation lowers only — growth stays with "
                         "the user/auto-tune paths")

    def test_off_leaves_n_runs_alone(self):
        fleet_id = self._built_fleet(n=5, budget=5_000.0)
        os.environ.pop("FLEET_TARGET_SLOTS", None)
        fs.supervise_fleet(fp.get_fleet(fleet_id))
        self.assertEqual(int(fp.get_fleet(fleet_id)["n_runs"]), 5)

    def test_size_changed_event_emitted(self):
        fleet_id = self._built_fleet(n=5, budget=5_000.0)
        os.environ["FLEET_TARGET_SLOTS"] = "2"
        fs.supervise_fleet(fp.get_fleet(fleet_id))
        import database
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT event_type FROM fleet_events "
                        "WHERE fleet_id = ?", (fleet_id,))
            kinds = [r["event_type"] for r in cur.fetchall()]
        finally:
            conn.close()
        self.assertIn("size_changed", kinds)


if __name__ == "__main__":
    unittest.main()
