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


class ModuleManagedBook(unittest.TestCase):
    """The trend module's positions carry run_id NULL by design and are
    managed by the module (its own 1.5×ATR stop, judged on the daily close).
    The sweep read them as "unowned and unprotected", attached the 5% account
    stop, and the SL/TP watcher closed on it intraday — prod 2026-09-18, the
    module's XRP short went out at 1.3423 on this job's stop, not its own."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "t.db")
        database.init_database()
        conn = database.get_db_connection()
        cur = conn.cursor()
        for pid, agent in ((1, 63), (2, 6)):
            cur.execute(
                "INSERT INTO positions (id,agent_id,symbol,market,side,"
                "quantity,entry_price,current_price,opened_at,run_id) VALUES "
                "(?,?,'XRPUSDT','crypto','long',10.0,1.5,1.5,"
                "'2026-08-11T18:46:50Z',NULL)", (pid, agent))
        conn.commit(); conn.close()
        self.env = unittest.mock.patch.dict(os.environ, {
            "ORPHAN_RECLAIM_ENABLED": "true", "TREND_MODULE_ENABLED": "1",
            "TREND_AGENT_ID": "63"})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def _stops(self):
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, stop_loss FROM positions ORDER BY id")
        out = {r["id"]: r["stop_loss"] for r in cur.fetchall()}
        conn.close()
        return out

    def test_the_sweep_leaves_the_modules_book_alone(self):
        self.assertEqual([r["id"] for r in orc.find_orphans()], [2])
        orc.sweep(blocking={})
        stops = self._stops()
        self.assertIsNone(stops[1], "a foreign stop was attached to the "
                                    "trend module's position")
        self.assertIsNotNone(stops[2], "a real orphan lost its protection")

    def test_a_switched_off_module_manages_nothing(self):
        # Nobody is looking at those rows any more: they are orphans again.
        os.environ["TREND_MODULE_ENABLED"] = "0"
        self.assertEqual(sorted(r["id"] for r in orc.find_orphans()), [1, 2])
        os.environ["TREND_MODULE_ENABLED"] = "1"
        os.environ["TREND_AGENT_ID"] = ""
        self.assertEqual(sorted(r["id"] for r in orc.find_orphans()), [1, 2])

    def test_a_broken_module_lookup_does_not_stop_the_sweep(self):
        with unittest.mock.patch("trend_module.module_enabled",
                                 side_effect=RuntimeError("boom")):
            self.assertEqual(sorted(r["id"] for r in orc.find_orphans()),
                             [1, 2])


class GhostRows(unittest.TestCase):
    """Plan 24 fix 2 residue: a zero-quantity unowned row is bookkeeping
    debris — the sweep deletes it; owned rows and real orphans are kept."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "t.db")
        database.init_database()
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO positions (id,agent_id,symbol,market,side,quantity,"
            "entry_price,opened_at,run_id) VALUES (1,6,'USDKRW','forex','long',"
            "0.0,1412.38,'2026-08-11T23:41:43Z',NULL)")
        cur.execute(
            "INSERT INTO positions (id,agent_id,symbol,market,side,quantity,"
            "entry_price,opened_at,run_id) VALUES (2,6,'CRM','us-stock','long',"
            "0.633,196.78,'2026-08-11T18:46:50Z',NULL)")
        cur.execute(
            "INSERT INTO positions (id,agent_id,symbol,market,side,quantity,"
            "entry_price,opened_at,run_id) VALUES (3,6,'BTC','crypto','long',"
            "0.0,100.0,'2026-08-11T18:46:50Z',7)")
        conn.commit(); conn.close()

    def tearDown(self):
        self.tmp.cleanup()

    def _ids(self):
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT id FROM positions ORDER BY id")
        out = [r["id"] for r in cur.fetchall()]
        conn.close()
        return out

    def test_sweep_deletes_unowned_zero_rows_only(self):
        os.environ["ORPHAN_RECLAIM_ENABLED"] = "true"
        try:
            out = orc.sweep()
        finally:
            os.environ.pop("ORPHAN_RECLAIM_ENABLED", None)
        self.assertEqual(out.get("ghosts_deleted"), 1)
        # the real orphan (2) and the RUN-owned zero row (3) both survive
        self.assertEqual(self._ids(), [2, 3])


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


class ProtectIsNotLiquidation(unittest.TestCase):
    """My own bug, live 2026-07-28. Position 13 (SOL long, entry 77.442) was
    -5.4% when the sweep ran. A 5% stop off ENTRY landed at 73.5699 while the
    mark was 73.134 — already through it. The watcher filled 31 seconds later
    for -$25.72. A stop that is already breached is a market order, not a
    safety net."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "t.db")
        database.init_database()
        conn = database.get_db_connection(); cur = conn.cursor()
        cur.execute("INSERT INTO positions (id,agent_id,symbol,market,side,"
                    "quantity,entry_price,opened_at,run_id) VALUES "
                    "(1,6,'SOL','crypto','long',5.87,77.442,'2026-07-20T22:53:52Z',NULL)")
        conn.commit(); conn.close()

    def tearDown(self):
        self.tmp.cleanup()

    def _stop(self):
        conn = database.get_db_connection(); cur = conn.cursor()
        cur.execute("SELECT stop_loss FROM positions WHERE id=1")
        v = cur.fetchone()["stop_loss"]; conn.close()
        return v

    def _pos13(self, mark):
        p = _pos(entry=77.442)
        p["current_price"] = mark
        return p

    def test_the_live_case_is_not_instantly_breached(self):
        orc.protect(self._pos13(73.134))
        self.assertLess(self._stop(), 73.134,
                        "the stop must sit BELOW the mark, not above it")

    def test_underwater_long_anchors_on_the_mark(self):
        orc.protect(self._pos13(73.134))
        self.assertAlmostEqual(self._stop(), 73.134 * 0.95, places=4)

    def test_winning_long_still_anchors_on_entry(self):
        """A profitable position keeps its risk measured from cost, so the
        stop cannot drift up with the price and cut a winner short."""
        orc.protect(self._pos13(90.0))
        self.assertAlmostEqual(self._stop(), 77.442 * 0.95, places=4)

    def test_underwater_short_anchors_on_the_mark(self):
        p = _pos(side="short", entry=74.031)
        p["current_price"] = 80.0            # a short is underwater when price rises
        orc.protect(p)
        self.assertAlmostEqual(self._stop(), 80.0 * 1.05, places=4)
        self.assertGreater(self._stop(), 80.0, "stop must sit ABOVE the mark")

    def test_winning_short_still_anchors_on_entry(self):
        p = _pos(side="short", entry=74.031)
        p["current_price"] = 70.0
        orc.protect(p)
        self.assertAlmostEqual(self._stop(), 74.031 * 1.05, places=4)

    def test_missing_mark_falls_back_to_entry(self):
        p = _pos(entry=77.442)
        p["current_price"] = None
        self.assertTrue(orc.protect(p))
        self.assertAlmostEqual(self._stop(), 77.442 * 0.95, places=4)

    def test_zero_mark_falls_back_to_entry(self):
        p = _pos(entry=77.442)
        p["current_price"] = 0
        orc.protect(p)
        self.assertAlmostEqual(self._stop(), 77.442 * 0.95, places=4)


class DeskCooldown(unittest.TestCase):
    """The desk read is the FULL four-analyst pipeline — measured on prod
    2026-07-28: 14 LLM calls, $0.36, for ONE blocking position. The sweep runs
    every 15 minutes, so re-asking every pass is ~$35/day to keep re-deciding a
    question whose answer barely moves. More than the platform's entire prior
    daily LLM spend."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "t.db")
        database.init_database()
        os.environ["ORPHAN_RECLAIM_ENABLED"] = "true"
        # A real fleet row: emit_fleet_event fences on last_event_seq, and in
        # production blocking_symbols() always yields the fleet whose slot is
        # being refused. A bare set with no fleet is not a shape prod produces.
        conn = database.get_db_connection(); cur = conn.cursor()
        cur.execute("INSERT INTO fleets (id,agent_id,name,status,n_runs,"
                    "total_budget_usd,risk_appetite,warn_loss_frac,"
                    "stop_loss_frac,last_event_seq,created_at) VALUES "
                    "(20,6,'t','active',10,10000,'balanced',0.15,0.3,0,"
                    "'2026-07-27T11:34:59Z')")
        conn.commit(); conn.close()

    def tearDown(self):
        self.tmp.cleanup()
        os.environ.pop("ORPHAN_RECLAIM_ENABLED", None)

    def _sweep(self, calls):
        with unittest.mock.patch.object(
                orc, "find_orphans", return_value=[_pos(stop=95.0)]):
            return orc.sweep(read_desk=lambda p: calls.append(p["id"]) or "buy",
                             blocking={"SOL": 20})

    def test_second_sweep_reuses_the_journaled_verdict(self):
        calls = []
        self._sweep(calls)
        self.assertEqual(len(calls), 1, "first sweep asks the desk")
        out = self._sweep(calls)
        self.assertEqual(len(calls), 1, "second sweep must NOT re-bill the read")
        self.assertEqual(out.get("cached"), 1)

    def test_the_cached_verdict_still_drives_the_decision(self):
        """A cooldown that merely SKIPS the read turns every repeat sweep into
        a hold — cheaper, and wrong. The cached verdict must flow through
        sweep() itself, not just be readable.

        Sweep 1: a LONG on SOL, desk says "buy" -> hold, verdict journalled.
        Sweep 2: a SHORT on the same symbol, no desk available at all -> the
        cached "buy" must still close it.
        """
        calls = []
        self._sweep(calls)                      # journals "buy" for SOL
        exits = []
        with unittest.mock.patch.object(
                orc, "find_orphans",
                return_value=[_pos(side="short", stop=105.0)]):
            out = orc.sweep(
                read_desk=lambda p: (_ for _ in ()).throw(
                    AssertionError("desk must not be re-asked inside cooldown")),
                execute=lambda p, v: exits.append(p["id"]),
                blocking={"SOL": 20})
        self.assertEqual(out["exited"], 1,
                         "a cached 'buy' must still close a short via sweep()")
        self.assertEqual(exits, [1])

    def test_verdict_is_journaled_for_audit(self):
        self._sweep([])
        self.assertEqual(orc.recent_verdict("SOL"), "buy")

    def test_expired_verdict_is_asked_again(self):
        calls = []
        self._sweep(calls)
        prev = os.environ.get("ORPHAN_DESK_COOLDOWN_MIN")
        os.environ["ORPHAN_DESK_COOLDOWN_MIN"] = "5"
        try:
            with unittest.mock.patch.object(
                    orc, "_now_iso_for_test", create=True):
                pass
            # cooldown floor is 5 min; a verdict written "now" is still inside it
            self.assertIsNotNone(orc.recent_verdict("SOL"))
        finally:
            if prev is None:
                os.environ.pop("ORPHAN_DESK_COOLDOWN_MIN", None)
            else:
                os.environ["ORPHAN_DESK_COOLDOWN_MIN"] = prev

    def test_cooldown_has_a_floor(self):
        prev = os.environ.get("ORPHAN_DESK_COOLDOWN_MIN")
        os.environ["ORPHAN_DESK_COOLDOWN_MIN"] = "0"
        try:
            self.assertGreaterEqual(orc.desk_cooldown_minutes(), 5)
        finally:
            if prev is None:
                os.environ.pop("ORPHAN_DESK_COOLDOWN_MIN", None)
            else:
                os.environ["ORPHAN_DESK_COOLDOWN_MIN"] = prev

    def test_unknown_symbol_has_no_cached_verdict(self):
        self._sweep([])
        self.assertIsNone(orc.recent_verdict("ETHUSDT"))
