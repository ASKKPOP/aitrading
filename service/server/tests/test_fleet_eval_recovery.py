"""Eval-freeze recovery (2026-07-28).

Live deadlock on prod fleet 20. `marked_equity` went unreadable at 01:11 UTC,
the supervisor froze the fleet and paused runs 125/127/128 with
reason='eval_failed'. Marks recovered minutes later and the fleet returned to
`active` — but the three runs stayed paused for ~53 minutes, one of them
holding a live ZEC short, because BOTH un-pause paths are gated on a drawdown
latch the eval freeze never sets:

  * the automatic resume lives inside the drawdown-recovery branch, reached
    only when warn_latched_at is set (it was NULL);
  * ack_warning raises "no drawdown warning is active" for the same reason.

_pause_entries marks members with paused_marker='drawdown_warning' but latches
nothing, so the freeze was one-way. Recovery now happens where the freeze
clears.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
import fleet_supervisor as fs
import trading_runs


class EvalFreezeReleases(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "t.db")
        database.init_database()
        fs._EVAL_FAILURES.clear()

    def tearDown(self):
        self.tmp.cleanup()

    def _fleet(self, paused_reason="eval_failed"):
        return {"id": 20, "agent_id": 6, "entry_paused_reason": paused_reason}

    def _members(self, *specs):
        return [{"id": i, "status": st, "status_reason": rsn}
                for i, st, rsn in specs]

    def test_recovery_resumes_members_this_freeze_paused(self):
        members = self._members((125, trading_runs.STATUS_PAUSED, "eval_failed"),
                                (127, trading_runs.STATUS_PAUSED, "eval_failed"))
        resumed, updates, events = [], [], []
        with patch.object(fs.fp, "list_members", return_value=members), \
             patch.object(trading_runs, "resume_run",
                          side_effect=lambda rid, aid: resumed.append(rid)), \
             patch.object(fs, "_update_fleet",
                          side_effect=lambda *a: updates.append(a)), \
             patch.object(fs.fp, "emit_fleet_event",
                          side_effect=lambda f, k, p: events.append((k, p))):
            fs._reset_eval_failures(self._fleet())
        self.assertEqual(resumed, [125, 127])
        self.assertTrue(any("entry_paused_reason = NULL" in a[1] for a in updates))
        self.assertIn("eval_recovered", [k for k, _ in events])

    def test_a_drawdown_pause_is_left_alone(self):
        """A real drawdown warning owns its own lifecycle — don't touch it."""
        members = self._members((125, trading_runs.STATUS_PAUSED, "drawdown_warning"))
        resumed = []
        with patch.object(fs.fp, "list_members", return_value=members), \
             patch.object(trading_runs, "resume_run",
                          side_effect=lambda rid, aid: resumed.append(rid)), \
             patch.object(fs, "_update_fleet"), \
             patch.object(fs.fp, "emit_fleet_event"):
            fs._reset_eval_failures(self._fleet())
        self.assertEqual(resumed, [], "drawdown pauses must not be swept up")

    def test_no_freeze_means_no_writes(self):
        """The healthy path runs every tick — it must stay silent."""
        touched = []
        with patch.object(fs.fp, "list_members", return_value=[]), \
             patch.object(fs, "_update_fleet",
                          side_effect=lambda *a: touched.append(a)), \
             patch.object(fs.fp, "emit_fleet_event",
                          side_effect=lambda *a: touched.append(a)):
            fs._reset_eval_failures(self._fleet(paused_reason=None))
        self.assertEqual(touched, [])

    def test_running_members_are_not_resumed(self):
        members = self._members((125, trading_runs.STATUS_RUNNING, None))
        resumed = []
        with patch.object(fs.fp, "list_members", return_value=members), \
             patch.object(trading_runs, "resume_run",
                          side_effect=lambda rid, aid: resumed.append(rid)), \
             patch.object(fs, "_update_fleet"), \
             patch.object(fs.fp, "emit_fleet_event"):
            fs._reset_eval_failures(self._fleet())
        self.assertEqual(resumed, [])

    def test_one_stuck_member_does_not_block_the_others(self):
        members = self._members((125, trading_runs.STATUS_PAUSED, "eval_failed"),
                                (127, trading_runs.STATUS_PAUSED, "eval_failed"))
        resumed = []

        def flaky(rid, aid):
            if rid == 125:
                raise RuntimeError("lease lost")
            resumed.append(rid)

        with patch.object(fs.fp, "list_members", return_value=members), \
             patch.object(trading_runs, "resume_run", side_effect=flaky), \
             patch.object(fs, "_update_fleet"), \
             patch.object(fs.fp, "emit_fleet_event"):
            fs._reset_eval_failures(self._fleet())
        self.assertEqual(resumed, [127])

    def test_counter_is_still_cleared(self):
        fs._EVAL_FAILURES[20] = 3
        with patch.object(fs.fp, "list_members", return_value=[]), \
             patch.object(fs, "_update_fleet"), \
             patch.object(fs.fp, "emit_fleet_event"):
            fs._reset_eval_failures(self._fleet())
        self.assertNotIn(20, fs._EVAL_FAILURES)


if __name__ == "__main__":
    unittest.main()
