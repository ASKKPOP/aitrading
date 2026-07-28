"""Orphan reclaim (2026-07-28).

Three live consequences of leaving unowned positions alone on prod:

  * position 13 (SOL long) sat with NO stop for eight days at −5.6%;
  * position 67 (SOLUSDT short) sat +$7.29 with no exit plan;
  * both permanently deleted their symbol from the fleet universe — the build
    path refuses a symbol an unowned position holds, so SOLUSDT cleared every
    gate and was still skipped, slot after slot.

The design line these tests defend: the daemon may PROTECT unilaterally
(attaching a stop to a bare position is strictly safer than leaving it bare),
but it may only CLOSE on the desk's own read. An unreadable desk is a hold —
never an exit. We do not close on a guess.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest.mock
import unittest
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
import orphan_reclaim as orc


def _pos(side="long", stop=None, tp=None, entry=100.0, pid=1):
    return {"id": pid, "agent_id": 6, "symbol": "SOL", "market": "crypto",
            "side": side, "quantity": 5.87, "entry_price": entry,
            "stop_loss": stop, "take_profit": tp, "run_id": None,
            "opened_at": "2026-07-20T22:53:52.910Z",
            "first_opened_at": "2026-07-20T22:53:52.910Z"}


class Decide(unittest.TestCase):
    def test_bare_orphan_is_protected(self):
        d = orc.decide(_pos())
        self.assertEqual(d["action"], orc.RECLAIM_PROTECT)

    def test_protected_orphan_is_left_alone(self):
        d = orc.decide(_pos(stop=95.0))
        self.assertEqual(d["action"], orc.RECLAIM_HOLD)

    def test_desk_against_a_long_exits(self):
        d = orc.decide(_pos(stop=95.0), read_desk=lambda p: "sell")
        self.assertEqual(d["action"], orc.RECLAIM_EXIT)

    def test_desk_against_a_short_exits(self):
        d = orc.decide(_pos(side="short", stop=105.0), read_desk=lambda p: "buy")
        self.assertEqual(d["action"], orc.RECLAIM_EXIT)

    def test_desk_agreeing_does_not_exit(self):
        d = orc.decide(_pos(stop=95.0), read_desk=lambda p: "buy")
        self.assertEqual(d["action"], orc.RECLAIM_HOLD)

    def test_unreadable_desk_never_exits(self):
        """The rule that matters: we do not close on a guess."""
        def boom(p):
            raise RuntimeError("desk down")
        self.assertNotEqual(orc.decide(_pos(stop=95.0), read_desk=boom)["action"],
                            orc.RECLAIM_EXIT)
        self.assertNotEqual(orc.decide(_pos(stop=95.0), read_desk=lambda p: None)["action"],
                            orc.RECLAIM_EXIT)

    def test_exit_outranks_protect(self):
        """A bare position the desk has turned against is closed, not merely
        given a stop — the stop would just realize the same loss later."""
        d = orc.decide(_pos(), read_desk=lambda p: "sell")
        self.assertEqual(d["action"], orc.RECLAIM_EXIT)


class Protect(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "t.db")
        database.init_database()
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO positions (id,agent_id,symbol,market,side,quantity,"
            "entry_price,opened_at,run_id) VALUES (1,6,'SOL','crypto','long',"
            "5.87,100.0,'2026-07-20T22:53:52Z',NULL)")
        conn.commit(); conn.close()

    def tearDown(self):
        self.tmp.cleanup()

    def _stop(self):
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT stop_loss FROM positions WHERE id=1")
        v = cur.fetchone()["stop_loss"]
        conn.close()
        return v

    def test_long_stop_is_below_entry(self):
        self.assertTrue(orc.protect(_pos(entry=100.0)))
        self.assertAlmostEqual(self._stop(), 95.0, places=4)

    def test_short_stop_is_above_entry(self):
        self.assertTrue(orc.protect(_pos(side="short", entry=100.0)))
        self.assertAlmostEqual(self._stop(), 105.0, places=4)

    def test_never_overwrites_an_existing_stop(self):
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE positions SET stop_loss = 88.0 WHERE id=1")
        conn.commit(); conn.close()
        orc.protect(_pos(entry=100.0))
        self.assertAlmostEqual(self._stop(), 88.0, places=4,
                               msg="a stop somebody set must never be moved")

    def test_unusable_entry_writes_nothing(self):
        self.assertFalse(orc.protect(_pos(entry=0.0)))
        self.assertFalse(orc.protect(_pos(entry="n/a")))


class Age(unittest.TestCase):
    def test_grace_period_protects_a_just_released_position(self):
        """A run's stop releases run_id BEFORE the replacement builds, so a
        fresh orphan is normal and must not be swept."""
        self.assertLess(
            orc._age_minutes("2026-07-28T05:00:00Z", "2026-07-28T05:10:00Z"),
            orc.min_age_minutes())

    def test_microseconds_and_z_do_not_break_the_parse(self):
        self.assertAlmostEqual(
            orc._age_minutes("2026-07-28T05:00:00.910Z", "2026-07-28T06:00:00Z"),
            60.0, places=3)

    def test_unparseable_stamp_is_zero_not_a_crash(self):
        self.assertEqual(orc._age_minutes("garbage", "2026-07-28T06:00:00Z"), 0.0)
        self.assertEqual(orc._age_minutes(None, "2026-07-28T06:00:00Z"), 0.0)


class Sweep(unittest.TestCase):
    def test_disabled_by_default(self):
        os.environ.pop("ORPHAN_RECLAIM_ENABLED", None)
        self.assertFalse(orc.enabled())
        self.assertTrue(orc.sweep().get("disabled"))

    def test_exit_without_an_executor_is_skipped_not_silently_dropped(self):
        os.environ["ORPHAN_RECLAIM_ENABLED"] = "true"
        try:
            with unittest.mock.patch.object(
                    orc, "find_orphans", return_value=[_pos(stop=95.0)]):
                # blocking is explicit: the desk is only consulted for an
                # orphan that is actually refusing a slot.
                out = orc.sweep(read_desk=lambda p: "sell", blocking={"SOL"})
            self.assertEqual(out["exited"], 0)
            self.assertEqual(out["skipped"], 1)
        finally:
            os.environ.pop("ORPHAN_RECLAIM_ENABLED", None)


if __name__ == "__main__":
    import unittest.mock  # noqa: F401
    unittest.main()


class Wiring(unittest.TestCase):
    """A tested module nothing calls is dead code. These fail if the loop is
    dropped from the registry — which is exactly how it shipped the first time."""

    def test_registered_as_a_background_task(self):
        import tasks
        self.assertIn("orphan_reclaim", tasks.BACKGROUND_TASK_REGISTRY)

    def test_assigned_to_the_settlement_role(self):
        import tasks
        self.assertEqual(tasks.BACKGROUND_TASK_ROLES.get("orphan_reclaim"),
                         "settlement")

    def test_runs_under_the_settlement_worker(self):
        import tasks
        self.assertIn("orphan_reclaim", tasks.tasks_for_role("settlement"))
        self.assertIn("orphan_reclaim", tasks.tasks_for_role("all"))

    def test_interval_has_a_floor(self):
        prev = os.environ.get("ORPHAN_RECLAIM_INTERVAL")
        os.environ["ORPHAN_RECLAIM_INTERVAL"] = "1"
        try:
            self.assertGreaterEqual(orc.sweep_interval_seconds(), 60)
        finally:
            if prev is None:
                os.environ.pop("ORPHAN_RECLAIM_INTERVAL", None)
            else:
                os.environ["ORPHAN_RECLAIM_INTERVAL"] = prev


class BlockingEscalation(unittest.TestCase):
    """A skip that repeats forever is not a decision, it is a question nobody
    asked. Live: SOLUSDT cleared the fee gate AND the expectancy gate on every
    tick and was refused on every tick, holding the fleet at 2/10 for hours."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "t.db")
        database.init_database()

    def tearDown(self):
        self.tmp.cleanup()

    def _skip_event(self, symbol, ts, reason=None):
        import json
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO fleet_events (fleet_id, seq, event_type, ts, payload) "
            "VALUES (20, ?, 'candidate_skipped', ?, ?)",
            (abs(hash((symbol, ts))) % 100000, ts,
             json.dumps({"slot": 9, "symbol": symbol,
                         "reason": reason or (orc.BLOCKING_REASON + " outside any run")})))
        conn.commit(); conn.close()

    def test_finds_the_blocking_symbol(self):
        from run_engine import _now_iso
        self._skip_event("SOLUSDT", _now_iso())
        self.assertIn("SOLUSDT", orc.blocking_symbols())

    def test_ignores_other_skip_reasons(self):
        from run_engine import _now_iso
        self._skip_event("ETHUSDT", _now_iso(), reason="symbol_busy")
        self.assertNotIn("ETHUSDT", orc.blocking_symbols())

    def test_desk_is_only_consulted_for_a_blocking_orphan(self):
        """An LLM call per orphan per sweep would be pure spend. Only an
        orphan with a measurable cost earns one."""
        asked = []
        with unittest.mock.patch.object(
                orc, "find_orphans",
                return_value=[_pos(pid=13, stop=95.0),
                              _pos(pid=67, side="short", stop=105.0)]):
            os.environ["ORPHAN_RECLAIM_ENABLED"] = "true"
            try:
                orc.sweep(read_desk=lambda p: asked.append(p["id"]) or None,
                          blocking=set())
                self.assertEqual(asked, [], "no blocker -> no LLM call")
                orc.sweep(read_desk=lambda p: asked.append(p["id"]) or None,
                          blocking={"SOL"})
                self.assertEqual(asked, [13, 67],
                                 "both fixtures are SOL; a blocker earns the call")
            finally:
                os.environ.pop("ORPHAN_RECLAIM_ENABLED", None)

    def test_closing_is_a_separate_switch_from_protecting(self):
        """Protection has no market consequence; closing does. One flag for
        both would mean turning on protection also turns on liquidation."""
        os.environ.pop("ORPHAN_RECLAIM_EXIT", None)
        self.assertFalse(orc.exit_enabled())
        os.environ["ORPHAN_RECLAIM_ENABLED"] = "true"
        try:
            self.assertTrue(orc.enabled())
            self.assertFalse(orc.exit_enabled(),
                             "enabling the sweep must not enable closing")
        finally:
            os.environ.pop("ORPHAN_RECLAIM_ENABLED", None)
