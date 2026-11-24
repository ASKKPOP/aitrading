"""Fleet position cap (owner 2026-11-23): "when we make fleet 5 by Full Auto,
always keep 5 (active 3, waiting 2)".

All N members run; at most ceil(60% of N) hold a position at once. A flat
member of a full fleet waits — at the ledger (every opening path) and at the
zero-LLM pre-gate — and those waiting cycles never feed idle-retire.
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
import fleet_position_cap as cap
import run_engine
from automation import execute_paper_trade
from tests.test_fleet_planner import FleetTestBase, _seed_batch


class CapArithmetic(unittest.TestCase):
    def tearDown(self):
        os.environ.pop("FLEET_POSITION_CAP_FRAC", None)

    def test_owner_split_for_any_n(self):
        # N=5 -> 3 active + 2 waiting
        self.assertEqual(cap.cap_for(5), 3)
        self.assertEqual(cap.cap_for(10), 6)
        self.assertEqual(cap.cap_for(3), 2)
        self.assertEqual(cap.cap_for(4), 3)
        self.assertEqual(cap.cap_for(25), 15)

    def test_no_cap_when_it_would_not_bind(self):
        self.assertIsNone(cap.cap_for(1))
        self.assertIsNone(cap.cap_for(2))   # ceil(1.2) = 2 = N

    def test_kill_switch(self):
        os.environ["FLEET_POSITION_CAP_FRAC"] = "0"
        self.assertIsNone(cap.cap_for(5))


class FleetCapLedger(FleetTestBase):
    def setUp(self):
        super().setUp()
        _seed_batch()
        self.fleet_id = self._fleet(n=5, budget=50000.0)
        fp.start_fleet(self.fleet_id, self.agent_id)
        fp._do_research(fp.get_fleet(self.fleet_id))
        fp._do_build(fp.get_fleet(self.fleet_id))
        self.members = fp.list_members(self.fleet_id)
        self.assertEqual(len(self.members), 5)

    def tearDown(self):
        os.environ.pop("FLEET_POSITION_CAP_FRAC", None)
        super().tearDown()

    def _open(self, m, qty=1.0):
        return execute_paper_trade(self.agent_id, m["symbol"], m["market"],
                                   "buy", qty, 100.0, run_id=m["id"])

    def _close(self, m):
        return execute_paper_trade(self.agent_id, m["symbol"], m["market"],
                                   "sell", 1.0, 100.0, run_id=m["id"],
                                   human_initiated=True)

    def _holding(self):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT COUNT(DISTINCT p.run_id) AS n FROM positions p JOIN "
                "trading_runs t ON t.id = p.run_id WHERE t.fleet_id = ? "
                "AND p.quantity != 0", (self.fleet_id,))
            return int(cur.fetchone()["n"])
        finally:
            conn.close()

    def test_three_hold_the_fourth_waits(self):
        for m in self.members[:3]:
            sid, why = self._open(m)
            self.assertIsNotNone(sid, why)
        sid, why = self._open(self.members[3])
        self.assertIsNone(sid)
        self.assertIn("fleet position cap: 3/3", why)
        self.assertEqual(self._holding(), 3)

    def test_a_holder_may_still_add(self):
        for m in self.members[:3]:
            self._open(m)
        sid, why = self._open(self.members[0])
        self.assertIsNotNone(sid, why)

    def test_a_freed_spot_lets_a_waiting_member_in(self):
        for m in self.members[:3]:
            self._open(m)
        sid, why = self._close(self.members[0])
        self.assertIsNotNone(sid, why)
        sid, why = self._open(self.members[4])
        self.assertIsNotNone(sid, why)
        self.assertEqual(self._holding(), 3)

    def test_exits_are_never_capped(self):
        for m in self.members[:3]:
            self._open(m)
        sid, why = self._close(self.members[2])
        self.assertIsNotNone(sid, why)

    def test_kill_switch_restores_all_n(self):
        os.environ["FLEET_POSITION_CAP_FRAC"] = "0"
        for m in self.members:
            sid, why = self._open(m)
            self.assertIsNotNone(sid, why)
        self.assertEqual(self._holding(), 5)

    def test_pre_gate_makes_a_flat_member_wait_before_any_llm(self):
        for m in self.members[:3]:
            self._open(m)
        waiting = dict(self.members[3])
        holder = dict(self.members[0])
        cfg = json.loads(waiting["config_snapshot_json"])
        with patch("routes_shared.is_market_open", return_value=True):
            skip = run_engine._pre_gate_skip(waiting, cfg)
            self.assertIsNotNone(skip)
            self.assertTrue(skip.startswith(cap.SKIP_PREFIX), skip)
            hold_skip = run_engine._pre_gate_skip(
                holder, json.loads(holder["config_snapshot_json"]))
        self.assertFalse((hold_skip or "").startswith(cap.SKIP_PREFIX),
                         "a member already in a position is never told to wait")

    def _event(self, run_id, kind, ts, payload):
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT COALESCE(MAX(seq), 0) + 1 AS s FROM run_events "
                    "WHERE run_id = ?", (run_id,))
        seq = int(cur.fetchone()["s"])
        cur.execute("INSERT INTO run_events (run_id, seq, event_type, ts, payload) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (run_id, seq, kind, ts, json.dumps(payload)))
        conn.commit()
        conn.close()

    def test_waiting_does_not_stretch_a_hold_streak_into_no_prospect(self):
        """Adversarial review 2026-11-24: the no-prospect span runs from the
        oldest flat hold to NOW, so time spent waiting for a spot (when the
        desk cannot act) would retire the member and bench its symbol."""
        from datetime import datetime, timedelta, timezone
        rid = self.members[4]["id"]
        t = lambda h: (datetime.now(timezone.utc) - timedelta(hours=h)
                       ).strftime("%Y-%m-%dT%H:%M:%SZ")
        hold = {"action": "hold", "decided_by": "llm", "report": "flat"}
        self._event(rid, "decision", t(3), hold)
        self._event(rid, "decision", t(2.5), hold)
        span, n = run_engine._flat_hold_span(rid)
        self.assertEqual(n, 2)
        self.assertGreaterEqual(span, 2.5)          # would switch at 1h
        self._event(rid, "gate_skip", t(1), {
            "cycle": 3, "stage": "pre",
            "reason": "fleet position cap: 3/3 TRADINGs already hold a "
                      "position — waiting for a free spot"})
        self.assertEqual(run_engine._flat_hold_span(rid), (None, 0))
        self._event(rid, "decision", t(0.5), hold)
        span, n = run_engine._flat_hold_span(rid)
        self.assertEqual(n, 1, "only holds after the wait count")
        self.assertLess(span, 1.0)

    def test_a_waiting_cycle_spends_no_llm_call(self):
        """Real run_cycle: a flat member of a full fleet skips at the pre
        stage before any model call; once a spot frees it trades."""
        for m in self.members[:3]:
            self._open(m)
        waiting = self.members[3]
        calls = []

        def _llm(*a, **k):
            calls.append(1)
            return '{"action": "buy", "confidence": 0.9, "report": "go"}'
        with patch("llm_client.generate_text", side_effect=_llm), \
             patch("price_fetcher.get_price_from_market", return_value=100.0), \
             patch("price_fetcher.get_daily_candles", return_value=[]), \
             patch("routes_shared.is_market_open", return_value=True):
            result = run_engine.run_cycle(waiting["id"])
        self.assertFalse(result["executed"])
        self.assertTrue((result["skip_reason"] or "").startswith(cap.SKIP_PREFIX),
                        result)
        self.assertEqual(calls, [], "a waiting member must not call the model")
        self.assertEqual(run_engine._fleet_cap_cycles(waiting["id"]), 1)

    def test_api_reports_cap_and_who_is_in_position(self):
        import routes_fleets
        self._open(self.members[1])
        pub = routes_fleets._public_fleet(fp.get_fleet(self.fleet_id))
        self.assertEqual(pub["position_cap"], 3)
        flags = {m["run_id"]: m["in_position"]
                 for m in routes_fleets._members_public(self.fleet_id)}
        self.assertEqual(flags, {m["id"]: m["id"] == self.members[1]["id"]
                                 for m in self.members})

    def test_waiting_cycles_do_not_idle_retire(self):
        m = dict(self.members[4])
        os.environ["RUN_IDLE_RETIRE_CYCLES"] = "12"
        try:
            conn = database.get_db_connection()
            cur = conn.cursor()
            for i in range(12):
                cur.execute(
                    "INSERT INTO run_events (run_id, seq, event_type, ts, payload) "
                    "VALUES (?, ?, 'gate_skip', ?, ?)",
                    (m["id"], 1000 + i, f"2026-11-23T0{i % 10}:00:00Z",
                     json.dumps({"cycle": i + 1, "stage": "pre",
                                 "reason": "fleet position cap: 3/3 TRADINGs "
                                           "already hold a position — waiting "
                                           "for a free spot"})))
            conn.commit()
            conn.close()
            self.assertEqual(run_engine._fleet_cap_cycles(m["id"]), 12)
            m["cycle_seq"] = 12
            pnl = {"total": 0.0, "realized": 0.0, "trades": 0,
                   "mark_age_ok": True, "position": None}
            with patch.object(run_engine, "compute_run_pnl", return_value=pnl), \
                 patch.object(run_engine, "_no_prospect_switch_enabled",
                              return_value=False), \
                 patch.object(run_engine, "_infeasible_retire_enabled",
                              return_value=False):
                self.assertNotEqual(run_engine._evaluate_stop(m), "idle_retired")
                m["cycle_seq"] = 24
                self.assertEqual(run_engine._evaluate_stop(m), "idle_retired")
        finally:
            os.environ.pop("RUN_IDLE_RETIRE_CYCLES", None)


if __name__ == "__main__":
    unittest.main()
