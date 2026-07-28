"""Fleet-initiated stops must not be recorded as user actions (2026-07-28).

On prod, 61 of 90 stopped runs read `user_stop` — but only 2 were a person.
The other 59 were fleet stop-alls and rotations, arriving in simultaneous
batches of four, because `request_stop_fleet` and the supervisor's own profit-target
and breaker exits all funnel through `trading_runs.request_stop`, which
hard-coded "user_stop".

Two consequences:
  * every UI surface reported a machine decision as "수동 정지 / Stopped by you"
  * the profit-target and breaker paths DISAGREED WITH THEMSELVES: the
    no-position branch wrote `fleet_profit_target` directly while the
    with-position branch went through request_stop and wrote `user_stop`,
    so the same event was labelled two different ways depending only on
    whether the member happened to be holding.

The dangerous half of the fix is classification. An unclassified reason falls
straight through the supervisor's slot loop to `_build_replacement`, so a new
fleet-wide stop reason that nobody put in REPLACE_NEVER would rebuild every
slot the stop had just torn down.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import fleet_planner as fp
import notifications_i18n as n
import trading_runs

FLEET_REASONS = ("fleet_stop_all", "fleet_profit_target", "fleet_breaker")


class RequestStop(unittest.TestCase):
    """The reason has to survive all three branches of request_stop."""

    def _run(self, status, has_position):
        run = {"id": 7, "agent_id": 6, "status": status,
               "market": "futures", "symbol": "ZC"}
        cur = unittest.mock.MagicMock()
        cur.fetchone.return_value = (1,) if has_position else None
        conn = unittest.mock.MagicMock()
        conn.cursor.return_value = cur
        return run, conn

    def _call(self, status, has_position, **kw):
        run, conn = self._run(status, has_position)
        with patch.object(trading_runs, "get_run", return_value=run), \
                patch.object(trading_runs, "get_db_connection",
                             return_value=conn), \
                patch.object(trading_runs, "_transition") as t:
            trading_runs.request_stop(7, 6, True, **kw)
        return t.call_args[0][4]      # the reason positional

    def test_default_is_still_user_stop(self):
        """A Stop button press must keep meaning what it meant."""
        for status, pos in ((trading_runs.STATUS_ARMED, False),
                            (trading_runs.STATUS_RUNNING, True),
                            (trading_runs.STATUS_RUNNING, False)):
            self.assertEqual(self._call(status, pos), "user_stop")

    def test_the_reason_reaches_every_branch(self):
        """Armed / holding / flat are three separate _transition calls, and
        the original bug was that all three said user_stop."""
        for status, pos in ((trading_runs.STATUS_ARMED, False),
                            (trading_runs.STATUS_RUNNING, True),
                            (trading_runs.STATUS_PAUSED, False)):
            self.assertEqual(self._call(status, pos, reason="fleet_stop_all"),
                             "fleet_stop_all", f"{status}/pos={pos}")


class Classification(unittest.TestCase):
    """The part that can break the fleet rather than just mislabel it."""

    def test_stop_all_never_triggers_replacement(self):
        """Not in REPLACE_NEVER ⇒ falls through to _build_replacement ⇒ the
        fleet rebuilds every slot the user just stopped."""
        self.assertIn("fleet_stop_all", fp.REPLACE_NEVER)

    def test_stop_all_closes_its_slot(self):
        """Same disposition as user_stop: the slot is gone, not waiting."""
        self.assertIn("fleet_stop_all", fp.SLOT_CLOSING)
        self.assertIn("user_stop", fp.SLOT_CLOSING)

    def test_slot_closing_is_a_subset_of_never(self):
        """A closing slot that could also be replaced is a contradiction."""
        self.assertTrue(fp.SLOT_CLOSING <= fp.REPLACE_NEVER)

    def test_the_disposition_sets_stay_disjoint(self):
        for a, b in ((fp.REPLACE_IMMEDIATE, fp.REPLACE_DEFERRED),
                     (fp.REPLACE_IMMEDIATE, fp.REPLACE_NEVER),
                     (fp.REPLACE_DEFERRED, fp.REPLACE_NEVER)):
            self.assertEqual(a & b, set())

    def test_a_fleet_stop_is_not_auto_restartable(self):
        """The restart allowlist is the only thing standing between a stopped
        fleet and a fleet that resurrects itself."""
        import run_engine
        for r in FLEET_REASONS:
            self.assertNotIn(r, run_engine._RESTARTABLE_STOP_REASONS)


class Wiring(unittest.TestCase):

    def test_request_stop_fleet_labels_members_and_the_fleet(self):
        members = [{"id": 11, "status": trading_runs.STATUS_RUNNING},
                   {"id": 12, "status": trading_runs.STATUS_RUNNING}]
        with patch.object(fp, "get_fleet", return_value={"id": 3}), \
                patch.object(fp, "list_members", return_value=members), \
                patch.object(fp, "_set_status") as set_status, \
                patch.object(fp, "emit_fleet_event"), \
                patch.object(trading_runs, "request_stop") as stop:
            fp.request_stop_fleet(3, 6, flatten=True)
        for call in stop.call_args_list:
            self.assertEqual(call.kwargs.get("reason"), "fleet_stop_all")
        self.assertEqual(set_status.call_args[0][3], "fleet_stop_all")

    def test_supervisor_exits_agree_with_themselves(self):
        """The no-position branch already wrote the fleet reason directly;
        the with-position branch must now write the same one."""
        import fleet_supervisor
        src = Path(fleet_supervisor.__file__).read_text()
        for reason in ("fleet_profit_target", "fleet_breaker"):
            self.assertIn(f'reason="{reason}"', src,
                          f"{reason} still falls back to user_stop")


class Localization(unittest.TestCase):
    """A new reason code with no catalogue entry renders as a raw identifier
    inside a translated sentence — the exact bug fixed in #109."""

    def test_every_new_reason_is_translated_everywhere(self):
        for lang in ("en", "ko", "ja", "th", "vi"):
            for reason in FLEET_REASONS:
                with self.subTest(lang=lang, reason=reason):
                    title, body = n.render("run_stop_event", lang, run_id=345,
                                           symbol="ZC", market="futures",
                                           reason=reason, outcome="flatten")
                    self.assertNotIn(reason, body)
                    self.assertNotIn(reason, title)

    def test_the_other_never_reasons_were_missing_too(self):
        for reason in ("agent_deleted", "user_master_remove"):
            _, body = n.render("run_stop_event", "ko", run_id=1, symbol="ZC",
                               market="futures", reason=reason,
                               outcome="flatten")
            self.assertNotIn(reason, body)

    def test_every_classified_reason_has_a_translation(self):
        """The standing trap: classify a reason, forget the catalogue."""
        every = fp.REPLACE_IMMEDIATE | fp.REPLACE_DEFERRED | fp.REPLACE_NEVER
        table = n.TOKENS["reason"]["ko"]
        missing = sorted(r for r in every if r not in table)
        self.assertEqual(missing, [], f"no ko translation for: {missing}")


if __name__ == "__main__":
    unittest.main()
