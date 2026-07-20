"""LLM usage aggregation: per-service grouping and the month-end projection
that feed the top-bar AI spend pill."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
from llm_usage import project_month_end, record_usage, usage_summary


class ProjectionTests(unittest.TestCase):
    """The projection is a straight-line run rate, and it must refuse to
    extrapolate from a few minutes of data — otherwise the first call of the
    month reads as a four-figure forecast."""

    def test_halfway_through_the_month_doubles_the_spend(self):
        # 30-day month, exactly 15 days elapsed
        now = datetime(2026, 6, 16, 0, 0, tzinfo=timezone.utc)
        self.assertAlmostEqual(project_month_end(10.0, now), 20.0, places=2)

    def test_three_quarters_through_scales_by_four_thirds(self):
        now = datetime(2026, 6, 23, 0, 0, tzinfo=timezone.utc)  # 22/30 days
        self.assertAlmostEqual(project_month_end(22.0, now), 30.0, places=1)

    def test_first_hour_of_the_month_is_not_extrapolated(self):
        now = datetime(2026, 6, 1, 0, 20, tzinfo=timezone.utc)
        self.assertEqual(project_month_end(5.0, now), 5.0)

    def test_december_rolls_into_the_next_year_without_crashing(self):
        now = datetime(2026, 12, 16, 12, 0, tzinfo=timezone.utc)  # 31-day month
        self.assertGreater(project_month_end(10.0, now), 10.0)

    def test_zero_spend_projects_zero(self):
        now = datetime(2026, 6, 16, 0, 0, tzinfo=timezone.utc)
        self.assertEqual(project_month_end(0.0, now), 0.0)


class ServiceBreakdownTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()

    def tearDown(self):
        self.tmp.cleanup()

    def _usage(self, tier: str, model: str, user_id: int, out_tokens: int):
        record_usage(provider="anthropic", model=model, tier=tier, key_source="system",
                     user_id=user_id, agent_id=None,
                     prompt_tokens=1000, completion_tokens=out_tokens)

    def test_costs_split_by_service_and_by_model(self):
        self._usage("decision", "claude-opus-4-8", 1, 1000)
        self._usage("decision", "claude-opus-4-8", 1, 1000)
        self._usage("brief", "claude-sonnet-5", 1, 1000)

        s = usage_summary(user_id=1)
        by_service = {x["service"]: x for x in s["services"]}
        self.assertEqual(set(by_service), {"decision", "brief"})
        self.assertEqual(by_service["decision"]["calls"], 2)
        self.assertEqual(by_service["brief"]["calls"], 1)
        # opus is far pricier than sonnet, so decision must dominate the spend
        self.assertGreater(by_service["decision"]["cost_usd"], by_service["brief"]["cost_usd"])
        # the two views of the same rows agree on the total
        self.assertAlmostEqual(sum(x["cost_usd"] for x in s["services"]),
                               s["total_cost_usd"], places=3)
        self.assertAlmostEqual(sum(m["cost_usd"] for m in s["models"]),
                               s["total_cost_usd"], places=3)

    def test_a_users_summary_excludes_other_users(self):
        self._usage("decision", "claude-opus-4-8", 1, 1000)
        self._usage("decision", "claude-opus-4-8", 2, 1000)
        self.assertEqual(usage_summary(user_id=1)["total_calls"], 1)
        self.assertEqual(usage_summary(user_id=2)["total_calls"], 1)
        # user_id None is the system-wide roll-up (owner-gated at the route)
        self.assertEqual(usage_summary()["total_calls"], 2)

    def test_summary_carries_a_projection(self):
        self._usage("decision", "claude-opus-4-8", 1, 1000)
        s = usage_summary(user_id=1)
        self.assertIn("projected_cost_usd", s)
        self.assertGreaterEqual(s["projected_cost_usd"], s["total_cost_usd"])

    def test_empty_month_is_all_zeros_not_an_error(self):
        s = usage_summary(user_id=99)
        self.assertEqual(s["total_calls"], 0)
        self.assertEqual(s["total_cost_usd"], 0)
        self.assertEqual(s["services"], [])
        self.assertEqual(s["projected_cost_usd"], 0)


if __name__ == "__main__":
    unittest.main()
