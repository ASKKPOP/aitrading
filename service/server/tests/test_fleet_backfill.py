"""E3 — fleet back-fill: "kept at N until the user stops it" must hold for
UNDER-filled fleets too (2026-07-26 finding on Fleet 18: partial 1/8 stayed
partial forever — _slot_pass skipped member-None slots and slots beyond the
composed count never existed; fleet 16's frozen 4/9 was the same gap).

Also hardens the replacement path to parity with the initial build: the
open-markets scope, the backtest expectancy gate, add_limits, and leverage
were all missing from _build_replacement.
"""

from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
import fleet_planner as fp
import fleet_supervisor as fs
import symbol_research as sr

from test_fleet_supervision import SupervisionBase


def _live(fleet_id):
    return [m for m in fp.list_members(fleet_id)
            if m["status"] in ("running", "armed", "paused")]


class BackfillTests(SupervisionBase):
    def _orphan_slot(self, fleet_id, slot_index=0):
        """Simulate the ALLO case: a slot that never got a run bound."""
        slot_runs = {s["slot_index"]: s.get("current_run_id")
                     for s in fs._slots(fleet_id)}
        run_id = slot_runs[slot_index]
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM trading_runs WHERE id = ?", (run_id,))
        cur.execute("UPDATE fleet_slots SET current_run_id = NULL, "
                    "state = 'active' WHERE fleet_id = ? AND slot_index = ?",
                    (fleet_id, slot_index))
        conn.commit()
        conn.close()

    def test_unbound_slot_backfills(self):
        fleet_id = self._built_fleet(n=2)
        self._orphan_slot(fleet_id, 0)
        self.assertEqual(len(_live(fleet_id)), 1)
        fs.supervise_fleet(fp.get_fleet(fleet_id))
        self.assertEqual(len(_live(fleet_id)), 2,
                         "member-None slot must back-fill")

    def test_missing_slots_created_up_to_n(self):
        """Research found fewer candidates than N at composition — the
        supervisor must create the missing slots later when candidates
        exist (perpetual N)."""
        self._seed_research()
        fleet_id = fp.create_fleet(self.agent_id, 3, 3000.0)
        fp.start_fleet(fleet_id, self.agent_id)
        real_select = sr.select_targets
        # 1 candidate found AND allocation stays a 1/N share (the composer
        # would otherwise hand the whole budget to the lone slot, correctly
        # leaving no headroom to back-fill — money already deployed).
        with patch.object(sr, "select_targets",
                          side_effect=lambda cur, aid, n, **kw:
                          real_select(cur, aid, min(n, 1), **kw)), \
             patch.object(fp, "allocate_budget", return_value=[1000.0]):
            fp._do_research(fp.get_fleet(fleet_id))   # only 1 candidate "found"
            fp._do_build(fp.get_fleet(fleet_id))
        self.assertEqual(len(_live(fleet_id)), 1)
        self.assertEqual(len(fs._slots(fleet_id)), 1)
        fs.supervise_fleet(fp.get_fleet(fleet_id))
        self.assertEqual(len(fs._slots(fleet_id)), 3, "missing slots created")
        self.assertEqual(len(_live(fleet_id)), 3, "…and built to N")

    def test_backfill_respects_expectancy_gate(self):
        import backtest_gate as bg
        fleet_id = self._built_fleet(n=2)
        self._orphan_slot(fleet_id, 0)
        os.environ["BACKTEST_GATE_ENABLED"] = "true"
        try:
            with patch.object(bg, "symbol_expectancy",
                              return_value={"n_trades": 9,
                                            "expectancy_usd": -50.0,
                                            "win_rate": 0.1, "wilson_lb": 0.0}):
                fs.supervise_fleet(fp.get_fleet(fleet_id))
        finally:
            os.environ.pop("BACKTEST_GATE_ENABLED", None)
        self.assertEqual(len(_live(fleet_id)), 1,
                         "all candidates negative-edge → nothing built")
        fs._LAST_EMPTY_ATTEMPT.clear()   # past the retry cooldown
        fs.supervise_fleet(fp.get_fleet(fleet_id))   # gate off → fills
        self.assertEqual(len(_live(fleet_id)), 2)

    def test_backfilled_run_has_build_parity(self):
        """Replacement/backfill runs must carry the same armor as the initial
        build: add_limits and tier leverage (both were missing)."""
        fleet_id = self._built_fleet(n=2, risk_appetite="aggressive")
        self._orphan_slot(fleet_id, 0)
        fs.supervise_fleet(fp.get_fleet(fleet_id))
        live = _live(fleet_id)
        self.assertEqual(len(live), 2)
        newest = max(live, key=lambda m: m["id"])
        cfg = json.loads(newest["config_snapshot_json"])
        self.assertIsInstance(cfg.get("add_limits"), dict)
        self.assertGreaterEqual(float(cfg.get("leverage") or 0), 2.0,
                                "aggressive tier auto-leverage missing")

    def test_no_backfill_while_master_held(self):
        fleet_id = self._built_fleet(n=2)
        self._orphan_slot(fleet_id, 0)
        with patch.object(fp, "_master_state", return_value="held"):
            fs.supervise_fleet(fp.get_fleet(fleet_id))
        self.assertEqual(len(_live(fleet_id)), 1, "held master → no new money")


if __name__ == "__main__":
    unittest.main()


class CandidateIterationTests(SupervisionBase):
    def test_unpriceable_first_candidate_falls_through_to_next(self):
        """ALLO case live 2026-07-26: the top-ranked candidate was junk
        (unpriceable) and _build_replacement gave up instead of trying the
        next one — every slot stayed empty while a good candidate waited."""
        import fleet_supervisor as fs2
        fleet_id = self._built_fleet(n=2)
        member = fp.list_members(fleet_id)[0]
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE trading_runs SET status='stopped', "
                    "status_reason='stop_event:profit_target', "
                    "active_key=NULL WHERE id = ?", (member["id"],))
        conn.commit(); conn.close()
        first_symbol = {}

        def probe(symbol, market):
            # the FIRST symbol tried is junk; everything else prices fine
            if not first_symbol:
                first_symbol[symbol] = True
                raise ValueError(f"no price available for {symbol}")
            if symbol in first_symbol:
                raise ValueError(f"no price available for {symbol}")
            return 100.0
        with patch("routes_runs._probe_price", side_effect=probe):
            fs2.supervise_fleet(fp.get_fleet(fleet_id))
        live = _live(fleet_id)
        self.assertEqual(len(live), 2,
                         "junk top candidate must not block the slot")


class RetryCooldownTests(SupervisionBase):
    def test_waiting_empty_slot_not_retried_within_cooldown(self):
        """With no buildable candidates, an empty waiting slot must NOT be
        re-attempted every 60s tick (live 2026-07-26: 7 slots × ~60s = a
        junk-symbol price probe and 3 journal rows per slot per minute)."""
        fleet_id = self._built_fleet(n=2)
        # orphan slot 0 and exhaust the universe (no candidates at all)
        slot_runs = {s["slot_index"]: s.get("current_run_id")
                     for s in fs._slots(fleet_id)}
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM trading_runs WHERE id = ?", (slot_runs[0],))
        cur.execute("UPDATE fleet_slots SET current_run_id = NULL, "
                    "state = 'active' WHERE fleet_id = ? AND slot_index = 0",
                    (fleet_id,))
        conn.commit(); conn.close()
        with patch.object(sr, "select_targets", return_value=[]):
            fs.supervise_fleet(fp.get_fleet(fleet_id))     # attempt 1 → waiting
            with patch.object(fs, "_build_replacement") as br:
                fs.supervise_fleet(fp.get_fleet(fleet_id))  # within cooldown
                self.assertEqual(br.call_count, 0,
                                 "waiting slot retried inside cooldown")
        fs._LAST_EMPTY_ATTEMPT.clear()   # past the retry cooldown
        with patch.object(fs, "_build_replacement", return_value=None) as br2:
            fs.supervise_fleet(fp.get_fleet(fleet_id))
            self.assertGreaterEqual(br2.call_count, 1, "aged slot must retry")


class WaitingJournalNoiseTests(SupervisionBase):
    """slot_waiting must be journaled on STATE CHANGE, not every 60s tick,
    and an already-waiting stopped-member slot must respect the same retry
    cooldown as an empty one (live 2026-07-26: slot 1 alone emitted 38 of 86
    slot_waiting rows in 30 min because the replacement path had no cooldown)."""

    def _waiting_events(self, fleet_id):
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) n FROM fleet_events WHERE fleet_id = ? "
                    "AND event_type = 'slot_waiting'", (fleet_id,))
        n = cur.fetchone()["n"]
        conn.close()
        return n

    def test_stopped_member_slot_respects_retry_cooldown(self):
        fleet_id = self._built_fleet(n=2)
        member = fp.list_members(fleet_id)[0]
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE trading_runs SET status='stopped', "
                    "status_reason='stop_event:profit_target', active_key=NULL "
                    "WHERE id = ?", (member["id"],))
        conn.commit(); conn.close()
        with patch.object(sr, "select_targets", return_value=[]):
            fs.supervise_fleet(fp.get_fleet(fleet_id))      # attempt 1 → waiting
            with patch.object(fs, "_build_replacement") as br:
                fs.supervise_fleet(fp.get_fleet(fleet_id))  # inside cooldown
                self.assertEqual(br.call_count, 0,
                                 "waiting stopped-member slot retried too soon")

    def test_fresh_stop_replaces_immediately(self):
        """A member that JUST stopped must not wait out a cooldown."""
        fleet_id = self._built_fleet(n=2)
        member = fp.list_members(fleet_id)[0]
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE trading_runs SET status='stopped', "
                    "status_reason='stop_event:profit_target', active_key=NULL "
                    "WHERE id = ?", (member["id"],))
        conn.commit(); conn.close()
        fs.supervise_fleet(fp.get_fleet(fleet_id))
        self.assertEqual(len(_live(fleet_id)), 2, "immediate replacement lost")

    def test_no_duplicate_waiting_events_while_unchanged(self):
        fleet_id = self._built_fleet(n=2)
        # orphan a slot so it genuinely enters the waiting path
        slot_runs = {s["slot_index"]: s.get("current_run_id")
                     for s in fs._slots(fleet_id)}
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM trading_runs WHERE id = ?", (slot_runs[0],))
        cur.execute("UPDATE fleet_slots SET current_run_id = NULL, "
                    "state = 'active' WHERE fleet_id = ? AND slot_index = 0",
                    (fleet_id,))
        conn.commit(); conn.close()
        # empty every slot's candidate supply
        with patch.object(sr, "select_targets", return_value=[]):
            fs.supervise_fleet(fp.get_fleet(fleet_id))
            first = self._waiting_events(fleet_id)
            fs._LAST_EMPTY_ATTEMPT.clear()   # retry happens, state unchanged
            fs.supervise_fleet(fp.get_fleet(fleet_id))
            second = self._waiting_events(fleet_id)
        self.assertEqual(second, first,
                         "unchanged waiting state re-journaled")
