"""TDD tests for Phase 4.6 — worker role partitioning.

Goals:
  - Every task in BACKGROUND_TASK_REGISTRY belongs to exactly one role.
  - Roles are exhaustive: "all" covers every task; the three specialised
    roles (prices / settlement / research) partition the registry.
  - SOOPPIY_WORKER_ROLE filters get_enabled_background_task_names().
  - Default behaviour (no env var) keeps every task enabled — backwards
    compat with single-process deployment.
  - Unknown role names raise ValueError so a typo doesn't silently start
    zero tasks.
  - Lock key namespacing: get_worker_lock_key(role) returns distinct
    keys per role so workers don't fight over the same lock.
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from tasks import (
    BACKGROUND_TASK_REGISTRY,
    BACKGROUND_TASK_ROLES,
    WORKER_ROLES,
    get_enabled_background_task_names,
    get_worker_lock_key,
    tasks_for_role,
)


# ── role taxonomy is exhaustive + non-overlapping ─────────────────────────

class RoleTaxonomyTests(unittest.TestCase):
    def test_every_registered_task_has_a_role(self):
        missing = set(BACKGROUND_TASK_REGISTRY) - set(BACKGROUND_TASK_ROLES)
        self.assertEqual(missing, set(),
                         f"Tasks missing a role mapping: {missing}")

    def test_role_map_does_not_reference_unknown_task(self):
        unknown = set(BACKGROUND_TASK_ROLES) - set(BACKGROUND_TASK_REGISTRY)
        self.assertEqual(unknown, set(),
                         f"BACKGROUND_TASK_ROLES has unknown tasks: {unknown}")

    def test_three_specialised_roles_partition_the_registry(self):
        # 'all' is the catch-all role; prices / settlement / research
        # must partition the registry between them.
        unique_roles = set(BACKGROUND_TASK_ROLES.values())
        self.assertEqual(unique_roles, {"prices", "settlement", "research"})

    def test_worker_roles_constant_includes_all_plus_specialised(self):
        self.assertIn("all", WORKER_ROLES)
        self.assertIn("prices", WORKER_ROLES)
        self.assertIn("settlement", WORKER_ROLES)
        self.assertIn("research", WORKER_ROLES)

    def test_tasks_for_role_returns_only_that_roles_tasks(self):
        for role in ("prices", "settlement", "research"):
            for name in tasks_for_role(role):
                self.assertEqual(BACKGROUND_TASK_ROLES[name], role)

    def test_tasks_for_role_all_returns_every_task(self):
        self.assertEqual(set(tasks_for_role("all")), set(BACKGROUND_TASK_REGISTRY))

    def test_tasks_for_role_unknown_raises(self):
        with self.assertRaises(ValueError):
            tasks_for_role("oops")


# ── env-driven filtering ──────────────────────────────────────────────────

class EnvFilteringTests(unittest.TestCase):
    def setUp(self):
        # Snapshot env so each test can mutate freely.
        self._snap = {
            "SOOPPIY_WORKER_ROLE":      os.environ.pop("SOOPPIY_WORKER_ROLE", None),
            "SOOPPIY_BACKGROUND_TASKS": os.environ.pop("SOOPPIY_BACKGROUND_TASKS", None),
        }

    def tearDown(self):
        for k, v in self._snap.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_default_starts_every_task(self):
        names = get_enabled_background_task_names()
        self.assertEqual(set(names), set(BACKGROUND_TASK_REGISTRY))

    def test_role_prices_only_starts_prices_tasks(self):
        os.environ["SOOPPIY_WORKER_ROLE"] = "prices"
        names = set(get_enabled_background_task_names())
        # Must include exactly the price-role tasks
        expected = {n for n, r in BACKGROUND_TASK_ROLES.items() if r == "prices"}
        self.assertEqual(names, expected)

    def test_role_settlement_only_starts_settlement_tasks(self):
        os.environ["SOOPPIY_WORKER_ROLE"] = "settlement"
        names = set(get_enabled_background_task_names())
        expected = {n for n, r in BACKGROUND_TASK_ROLES.items() if r == "settlement"}
        self.assertEqual(names, expected)

    def test_role_research_only_starts_research_tasks(self):
        os.environ["SOOPPIY_WORKER_ROLE"] = "research"
        names = set(get_enabled_background_task_names())
        expected = {n for n, r in BACKGROUND_TASK_ROLES.items() if r == "research"}
        self.assertEqual(names, expected)

    def test_role_all_is_explicit_alias_for_default(self):
        os.environ["SOOPPIY_WORKER_ROLE"] = "all"
        names = set(get_enabled_background_task_names())
        self.assertEqual(names, set(BACKGROUND_TASK_REGISTRY))

    def test_unknown_role_raises(self):
        os.environ["SOOPPIY_WORKER_ROLE"] = "nonsense"
        with self.assertRaises(ValueError):
            get_enabled_background_task_names()

    def test_explicit_task_list_still_honored_when_role_set(self):
        # If both SOOPPIY_BACKGROUND_TASKS and SOOPPIY_WORKER_ROLE are
        # set, the intersection wins (role-filter then task-list filter).
        # This lets you say "prices role, but disable price_push for now".
        os.environ["SOOPPIY_WORKER_ROLE"] = "prices"
        os.environ["SOOPPIY_BACKGROUND_TASKS"] = "prices,leaderboard_snapshot"
        names = set(get_enabled_background_task_names())
        # 'prices' task is in the prices role → kept.
        # 'leaderboard_snapshot' is in the research role → dropped.
        self.assertEqual(names, {"prices"})


# ── lock key namespacing ──────────────────────────────────────────────────

class LockKeyTests(unittest.TestCase):
    def test_lock_keys_differ_per_role(self):
        keys = {get_worker_lock_key(role) for role in ("all", "prices", "settlement", "research")}
        self.assertEqual(len(keys), 4)

    def test_lock_key_contains_role(self):
        for role in ("prices", "settlement", "research"):
            self.assertIn(role, get_worker_lock_key(role))

    def test_lock_key_for_unknown_role_raises(self):
        with self.assertRaises(ValueError):
            get_worker_lock_key("oops")


if __name__ == "__main__":
    unittest.main()
