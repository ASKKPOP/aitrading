"""Follow the Big Trader (owner 2026-08-12: "must be follow big trader —
it's key"). Two halves: the catalog skill that teaches the desk to read the
institutional footprint, and the build-time stamp that puts the footprint
numbers (mom_2d_pct, volume_ratio) on every fleet thesis so the desk sees
the flow its symbol was selected FOR at each decision.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import fleet_planner as fp  # noqa: E402
import trading_skills  # noqa: E402

from test_fleet_supervision import SupervisionBase  # noqa: E402


class CatalogTests(unittest.TestCase):
    def test_skill_is_in_the_base_catalog(self):
        slugs = [s["slug"] for s in trading_skills.BASE_SKILLS]
        self.assertIn("follow-the-flow", slugs)

    def test_scoped_to_us_stock_trader_prompt(self):
        skill = next(s for s in trading_skills.BASE_SKILLS
                     if s["slug"] == "follow-the-flow")
        self.assertEqual(skill["markets"], ["us-stock"])
        self.assertIn("trader", skill["prompts"])
        self.assertIn("mom_2d_pct", skill["body"])
        self.assertIn("volume_ratio", skill["body"])


class ThesisFactorTests(unittest.TestCase):
    def test_reads_factor_from_research_row(self):
        row = {"factor_scores_json": json.dumps(
            {"factors": {"mom_2d": 6.213456, "vol_ratio": 2.04}})}
        self.assertAlmostEqual(fp._thesis_factor(row, "mom_2d"), 6.2135)
        self.assertAlmostEqual(fp._thesis_factor(row, "vol_ratio"), 2.04)

    def test_absent_or_broken_reads_none(self):
        self.assertIsNone(fp._thesis_factor({}, "mom_2d"))
        self.assertIsNone(fp._thesis_factor(
            {"factor_scores_json": "{broken", "symbol": "X"}, "mom_2d"))
        self.assertIsNone(fp._thesis_factor(
            {"factor_scores_json": json.dumps({"factors": {}})}, "mom_2d"))


class BuildStampTests(SupervisionBase):
    def test_built_run_thesis_carries_the_footprint(self):
        """End to end through research → build: the run's frozen thesis must
        carry mom_2d_pct and volume_ratio for the desk to read."""
        fleet_id = self._built_fleet(n=1, budget=1000.0)
        member = fp.list_members(fleet_id)[0]
        cfg = json.loads(member["config_snapshot_json"] or "{}")
        thesis = cfg.get("thesis") or {}
        self.assertIn("mom_2d_pct", thesis)
        self.assertIn("volume_ratio", thesis)
        self.assertIsNotNone(thesis["mom_2d_pct"],
                             "seeded candles have 2-day history — the stamp "
                             "must carry a number, not None")


if __name__ == "__main__":
    unittest.main()
