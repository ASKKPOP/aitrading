"""Per-fleet performance index (2026-07-28).

The account total answers "am I up?" and cannot answer "is THIS sleeve
working?" — an N-symbol fleet is a distinct bet with its own budget, and on a
six-figure account its result is invisible. Rebasing each fleet to 100 at
launch makes sleeves comparable to each other and to a benchmark regardless of
how much money each was given.

Built on marked_equity so a retired member's P&L stays in the index instead of
disappearing with the run, and fail-closed so an unreadable equity never
becomes a fabricated number.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from routes_fleets import FLEET_INDEX_BASE, fleet_index


def _fleet(budget=10000.0, **kw):
    f = {"id": 20, "total_budget_usd": budget,
         "started_at": "2026-07-27T20:00:00Z",
         "created_at": "2026-07-27T19:00:00Z"}
    f.update(kw)
    return f


def _eq(equity, ok=True):
    return {"equity": equity, "ok": ok, "zombie_basis": 0.0, "detail": {}}


class IndexMath(unittest.TestCase):
    def test_flat_fleet_sits_at_base(self):
        ix = fleet_index(_fleet(), _eq(10000.0))
        self.assertEqual(ix["value"], 100.0)
        self.assertEqual(ix["pnl_usd"], 0.0)
        self.assertEqual(ix["pnl_pct"], 0.0)

    def test_gain(self):
        ix = fleet_index(_fleet(), _eq(10500.0))
        self.assertEqual(ix["value"], 105.0)
        self.assertEqual(ix["pnl_usd"], 500.0)
        self.assertEqual(ix["pnl_pct"], 5.0)

    def test_loss(self):
        ix = fleet_index(_fleet(), _eq(9000.0))
        self.assertEqual(ix["value"], 90.0)
        self.assertEqual(ix["pnl_usd"], -1000.0)
        self.assertEqual(ix["pnl_pct"], -10.0)

    def test_index_is_budget_independent(self):
        """The whole point: a $1k and a $100k sleeve down 3% read the same."""
        small = fleet_index(_fleet(budget=1000.0), _eq(970.0))
        large = fleet_index(_fleet(budget=100000.0), _eq(97000.0))
        self.assertEqual(small["value"], large["value"])
        self.assertEqual(small["pnl_pct"], large["pnl_pct"])
        self.assertNotEqual(small["pnl_usd"], large["pnl_usd"])

    def test_carries_budget_equity_and_start(self):
        ix = fleet_index(_fleet(), _eq(10250.0))
        self.assertEqual(ix["base"], FLEET_INDEX_BASE)
        self.assertEqual(ix["budget_usd"], 10000.0)
        self.assertEqual(ix["equity_usd"], 10250.0)
        self.assertEqual(ix["since"], "2026-07-27T20:00:00Z")

    def test_falls_back_to_created_at_before_launch(self):
        ix = fleet_index(_fleet(started_at=None), _eq(10000.0))
        self.assertEqual(ix["since"], "2026-07-27T19:00:00Z")


class FailClosed(unittest.TestCase):
    """An unreadable equity must never become an invented index — the same
    rule the supervisor freeze uses."""

    def test_equity_not_ok(self):
        self.assertIsNone(fleet_index(_fleet(), _eq(10000.0, ok=False)))

    def test_equity_missing(self):
        self.assertIsNone(fleet_index(_fleet(), None))

    def test_zero_budget_is_not_divided_by(self):
        self.assertIsNone(fleet_index(_fleet(budget=0.0), _eq(0.0)))

    def test_negative_budget(self):
        self.assertIsNone(fleet_index(_fleet(budget=-5.0), _eq(10.0)))

    def test_unparseable_budget(self):
        self.assertIsNone(fleet_index(_fleet(budget="n/a"), _eq(10000.0)))

    def test_total_loss_is_reported_not_suppressed(self):
        """A wiped sleeve is exactly what the index exists to show."""
        ix = fleet_index(_fleet(), _eq(0.0))
        self.assertEqual(ix["value"], 0.0)
        self.assertEqual(ix["pnl_pct"], -100.0)


if __name__ == "__main__":
    unittest.main()
