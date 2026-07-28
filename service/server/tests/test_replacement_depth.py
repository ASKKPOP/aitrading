"""Replacement candidate depth (2026-07-28).

Live: the fleet sat at 3/10 slots with `no_candidates` while thirteen fresh
AI theses were on the board and ten of them cleared the fee hurdle.

_build_replacement asked select_targets for THREE. The batch's top three were
NG, SOLUSDT and USDKRW:

  * fee gate       dropped USDKRW (1.20% x 0.25 = 0.30% < 0.60%)
  * expectancy gate dropped NG (-140.62 USD/trade over 8 closed)
  * symbol guard    refused SOLUSDT — an unowned position already held it

Nothing built, and SEVEN feasible candidates (ETHUSDT, GM, VZ, T, SPCX,
601288.SS, 601899.SS) sat below the cut and were never looked at.

Asking for 3 assumes the gates reject rarely. They do not — and every gate
downstream only ever REMOVES, so the fetch depth is the ceiling on how many
rejections a slot can absorb and still fill. Same lesson as E3's
junk-top-pick fix, one layer up: deepen the FETCH, not just the retry.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import fleet_supervisor as fs


class Depth(unittest.TestCase):
    def setUp(self):
        self._prev = os.environ.get("FLEET_REPLACEMENT_DEPTH")
        os.environ.pop("FLEET_REPLACEMENT_DEPTH", None)

    def tearDown(self):
        if self._prev is None:
            os.environ.pop("FLEET_REPLACEMENT_DEPTH", None)
        else:
            os.environ["FLEET_REPLACEMENT_DEPTH"] = self._prev

    def test_default_absorbs_the_observed_rejection_rate(self):
        """The live batch rejected 3 of the top 3. A depth of 3 cannot fill a
        slot when that happens; it must reach the feasible tail."""
        self.assertGreaterEqual(fs._replacement_depth(), 10)

    def test_env_override(self):
        os.environ["FLEET_REPLACEMENT_DEPTH"] = "4"
        self.assertEqual(fs._replacement_depth(), 4)

    def test_bad_env_falls_back(self):
        os.environ["FLEET_REPLACEMENT_DEPTH"] = "deep"
        self.assertEqual(fs._replacement_depth(), 10)

    def test_never_below_one(self):
        os.environ["FLEET_REPLACEMENT_DEPTH"] = "0"
        self.assertEqual(fs._replacement_depth(), 1)


class DepthIsActuallyRequested(unittest.TestCase):
    """The constant existing is not the fix — select_targets must receive it."""

    def setUp(self):
        import database
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "t.db")
        database.init_database()

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, candidates):
        asked = {}

        def fake_select(cursor, agent_id, n, exclude=None, markets_scope=None):
            asked["n"] = n
            return candidates

        fleet = {"id": 20, "agent_id": 6}
        slot = {"slot_index": 8, "current_run_id": None}
        built = []
        with patch.object(fs.fp, "_master_state", return_value="ok"), \
             patch("symbol_research.select_targets", side_effect=fake_select), \
             patch("backtest_gate.gate_enabled", return_value=False), \
             patch.object(fs, "_try_build",
                          side_effect=lambda f, c, u: built.append(c["symbol"]) or 7), \
             patch.object(fs.fp, "emit_fleet_event"), \
             patch.object(fs.fp, "_bind_slot"):
            fs._build_replacement(fleet, slot, 1000.0, set())
        return asked.get("n"), built

    def test_asks_for_the_configured_depth_not_three(self):
        n, _ = self._run([{"symbol": "ETHUSDT", "market": "crypto",
                           "expected_move_pct": 3.0}])
        self.assertEqual(n, fs._replacement_depth())
        self.assertNotEqual(n, 3, "the old hard-coded 3 must be gone")

    def test_reaches_a_feasible_candidate_below_infeasible_ones(self):
        """The live shape: infeasible names on top, a good one underneath."""
        _, built = self._run([
            {"symbol": "USDKRW", "market": "forex", "expected_move_pct": 1.20},
            {"symbol": "USDZAR", "market": "forex", "expected_move_pct": 2.00},
            {"symbol": "BTCUSDT", "market": "crypto", "expected_move_pct": 2.00},
            {"symbol": "ETHUSDT", "market": "crypto", "expected_move_pct": 3.00},
        ])
        self.assertEqual(built, ["ETHUSDT"],
                         "must skip the three fee-blocked names and build the fourth")


if __name__ == "__main__":
    unittest.main()
