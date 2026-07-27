"""Dead-capital rails (2026-07-27).

Prod evidence these encode: three of seven `running` fleet runs (129 ZC,
130 USDKRW, 131 USDZAR) were each refused by fee_edge on their FIRST cycle and
held $3,399 of allocation between them, because

  * the replacement path applied two of the initial build's three gates — the
    fee gate was missed when E3 ported parity, so retiring a blocked run
    rebuilt the same unpassable symbol (121 ZC -> 129 ZC, 122 USDKRW -> 130);
  * the only rail that collected them was the idle timer, which costs 12
    cycles / ~9h to learn what the frozen thesis already stated; and
  * the API reported `status: running` for all three, so the UI showed seven
    healthy runs.

100% of the 308 forex theses ever generated are in this class, so it is not an
edge case.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
import fleet_planner
import routes_runs
import run_engine


class FeeGateOn(unittest.TestCase):
    """Every pre-existing _build_replacement test sets RUN_FEE_EDGE_MULTIPLE=0
    (their synthetic ~1.5% theses would not clear the hurdle), and those
    writes leak across the process — which is a large part of why the missing
    replacement gate was never caught. Pin the default explicitly so these
    tests mean the same thing whatever ran before them."""

    def setUp(self):
        self._env = {k: os.environ.get(k) for k in
                     ("RUN_FEE_EDGE_MULTIPLE", "RUN_FEE_EDGE_REALIZATION",
                      "RUN_INFEASIBLE_RETIRE")}
        os.environ["RUN_FEE_EDGE_MULTIPLE"] = "3.0"
        os.environ["RUN_FEE_EDGE_REALIZATION"] = "0.25"
        os.environ["RUN_INFEASIBLE_RETIRE"] = "true"

    def tearDown(self):
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _run(expected_move_pct, *, status="running", cycle_seq=1, budget=1000.0,
         market="forex", symbol="USDZAR"):
    cfg = {"symbol": symbol, "market": market, "run_budget_usd": budget}
    if expected_move_pct is not None:
        cfg["thesis"] = {"symbol": symbol, "market": market,
                         "expected_move_pct": expected_move_pct}
    return {"id": 131, "agent_id": 6, "symbol": symbol, "market": market,
            "status": status, "cycle_seq": cycle_seq,
            "config_snapshot_json": json.dumps(cfg),
            "stop_conditions_json": "{}"}


class ThesisExpectedMove(FeeGateOn):
    def test_reads_frozen_snapshot(self):
        self.assertAlmostEqual(
            run_engine.run_thesis_expected_move(_run(1.2466)), 1.2466)

    def test_none_without_a_thesis(self):
        """Manual runs carry no thesis and must never be retired by this rail."""
        self.assertIsNone(run_engine.run_thesis_expected_move(_run(None)))

    def test_none_on_unreadable_snapshot(self):
        run = _run(1.0)
        run["config_snapshot_json"] = "{not json"
        self.assertIsNone(run_engine.run_thesis_expected_move(run))

    def test_bool_is_not_a_number(self):
        run = _run(None)
        run["config_snapshot_json"] = json.dumps(
            {"thesis": {"expected_move_pct": True}})
        self.assertIsNone(run_engine.run_thesis_expected_move(run))


class InfeasibleRetireRail(FeeGateOn):
    """The rail fires on cycle 1 — no samples needed, the input is frozen."""

    def _evaluate(self, run, *, has_position=False, trades=0):
        pnl = {"total": 0.0, "realized": 0.0, "trades": trades,
               "mark_age_ok": True,
               "position": {"quantity": 1 if has_position else 0,
                            "entry_price": 100.0, "current_price": 100.0,
                            "leverage": 1.0} if has_position else None}
        with patch.object(run_engine, "compute_run_pnl", return_value=pnl):
            return run_engine._evaluate_stop(run)

    def test_retires_a_dead_thesis_on_cycle_one(self):
        # USDZAR run 131: 1.2466% * 0.25 = 0.31% < 0.60% hurdle.
        self.assertEqual(self._evaluate(_run(1.2466, cycle_seq=1)),
                         "fee_infeasible_retired")

    def test_leaves_a_feasible_thesis_alone(self):
        # ZEC run 125: 4.79% * 0.25 = 1.20% clears the hurdle.
        self.assertIsNone(self._evaluate(_run(4.7905, cycle_seq=1)))

    def test_never_abandons_an_open_position(self):
        """A dead thesis that somehow opened must still be managed out."""
        self.assertIsNone(
            self._evaluate(_run(1.2466), has_position=True, trades=1))

    def test_leaves_manual_runs_alone(self):
        self.assertIsNone(self._evaluate(_run(None, cycle_seq=1)))

    def test_kill_switch(self):
        with patch.dict("os.environ", {"RUN_INFEASIBLE_RETIRE": "false"}):
            self.assertIsNone(self._evaluate(_run(1.2466, cycle_seq=1)))

    def test_idle_timer_still_collects_feasible_runs(self):
        """The new rail must not shadow the old one."""
        self.assertEqual(self._evaluate(_run(4.7905, cycle_seq=12)),
                         "idle_retired")

    def test_reason_is_classified_for_immediate_replacement(self):
        """An unclassified stop reason silently strands the fleet slot."""
        self.assertIn("fee_infeasible_retired", fleet_planner.REPLACE_IMMEDIATE)


class ReplacementFeeParity(FeeGateOn):
    """The gap that let 129/130/131 be built at all."""

    def test_thesis_fee_infeasible_reads_a_flat_candidate_row(self):
        """select_targets returns research_theses rows verbatim, so the
        candidate IS the thesis. Passing the wrong shape makes the gate a
        silent no-op — the exact failure mode being fixed."""
        candidate = {"symbol": "USDZAR", "market": "forex",
                     "expected_move_pct": 1.2466, "direction": "long"}
        self.assertIsNotNone(fleet_planner._thesis_fee_infeasible(candidate))
        candidate["expected_move_pct"] = 4.7905
        self.assertIsNone(fleet_planner._thesis_fee_infeasible(candidate))

    def test_every_forex_thesis_is_infeasible_at_the_flat_fee(self):
        """Prod: 308/308 forex theses, 0 tradeable. The widest observed FX
        claim was 1.25%; the hurdle needs 2.40%."""
        for claim in (0.443, 0.6578, 0.6623, 1.2466):
            self.assertIsNotNone(
                fleet_planner._thesis_fee_infeasible(
                    {"symbol": "FX", "expected_move_pct": claim}),
                f"{claim}% should be refused")


class ReplacementGateIsWired(FeeGateOn):
    """The predicate existing is not the fix — the bug was that nobody CALLED
    it on the replacement path. These fail if the call is deleted."""

    def setUp(self):
        super().setUp()
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()

    def tearDown(self):
        self.tmp.cleanup()
        super().tearDown()

    def _build(self, candidates):
        import fleet_supervisor as fs
        fleet = {"id": 20, "agent_id": 6}
        slot = {"slot_index": 8, "current_run_id": None}
        built, events = [], []
        with patch.object(fs.fp, "_master_state", return_value="ok"), \
             patch("symbol_research.select_targets", return_value=candidates), \
             patch("backtest_gate.gate_enabled", return_value=False), \
             patch.object(fs, "_try_build",
                          side_effect=lambda f, c, u: built.append(c) or 999), \
             patch.object(fs.fp, "emit_fleet_event",
                          side_effect=lambda fid, kind, p: events.append((kind, p))), \
             patch.object(fs.fp, "_bind_slot"):
            run_id = fs._build_replacement(fleet, slot, 1000.0, set())
        return run_id, built, events

    def test_infeasible_candidate_is_never_built(self):
        """Prod 22:58:55 — USDZAR was built and blocked 11 seconds later."""
        run_id, built, events = self._build(
            [{"symbol": "USDZAR", "market": "forex",
              "expected_move_pct": 1.2466, "direction": "long"}])
        self.assertIsNone(run_id, "a dead thesis must not become a run")
        self.assertEqual(built, [], "_try_build must not be reached")
        self.assertIn("fee_gate", [k for k, _ in events])

    def test_feasible_candidate_still_builds(self):
        """The gate must not swallow good candidates."""
        run_id, built, _ = self._build(
            [{"symbol": "ZECUSDT", "market": "crypto",
              "expected_move_pct": 4.7905, "direction": "short"}])
        self.assertEqual(run_id, 999)
        self.assertEqual([c["symbol"] for c in built], ["ZECUSDT"])

    def test_gate_falls_through_to_the_next_feasible_candidate(self):
        """A dead top pick must not strand the slot — same lesson as E3's
        junk-symbol iteration fix."""
        run_id, built, _ = self._build([
            {"symbol": "USDKRW", "market": "forex",
             "expected_move_pct": 0.6623, "direction": "short"},
            {"symbol": "ZECUSDT", "market": "crypto",
             "expected_move_pct": 4.7905, "direction": "short"},
        ])
        self.assertEqual(run_id, 999)
        self.assertEqual([c["symbol"] for c in built], ["ZECUSDT"])

    def test_all_infeasible_leaves_the_slot_waiting(self):
        run_id, built, events = self._build([
            {"symbol": "USDKRW", "market": "forex", "expected_move_pct": 0.6623},
            {"symbol": "AUDJPY", "market": "forex", "expected_move_pct": 0.443},
        ])
        self.assertIsNone(run_id)
        self.assertEqual(built, [])
        self.assertIn("slot_waiting", [k for k, _ in events])


class CapabilityBlock(FeeGateOn):
    def test_dead_thesis_is_permanent(self):
        cap = routes_runs._capability(_run(1.2466))
        self.assertEqual(cap["state"], "cannot_trade")
        self.assertTrue(cap["permanent"])
        self.assertEqual(cap["reason_code"], "fee_infeasible")
        self.assertEqual(cap["capital_usd"], 1000.0)
        self.assertIn("0.31%", cap["reason"])

    def test_permanent_outranks_a_closed_market(self):
        """A closed market reopening changes nothing for a dead thesis."""
        with patch("markets.is_market_open", return_value=False):
            cap = routes_runs._capability(_run(1.2466))
        self.assertEqual(cap["state"], "cannot_trade")

    def test_closed_market_is_temporary(self):
        with patch("markets.is_market_open", return_value=False):
            cap = routes_runs._capability(_run(4.7905))
        self.assertEqual(cap["state"], "waiting")
        self.assertFalse(cap["permanent"])

    def test_live_run_is_hunting(self):
        with patch("markets.is_market_open", return_value=True):
            cap = routes_runs._capability(_run(4.7905))
        self.assertEqual(cap["state"], "hunting")
        self.assertFalse(cap["permanent"])

    def test_stopped_run_is_inactive(self):
        cap = routes_runs._capability(_run(1.2466, status="stopped"))
        self.assertEqual(cap["state"], "inactive")

    def test_calendar_failure_does_not_blank_the_row(self):
        with patch("markets.is_market_open", side_effect=RuntimeError("boom")):
            cap = routes_runs._capability(_run(4.7905))
        self.assertEqual(cap["state"], "hunting")

    def test_public_carries_capability(self):
        out = routes_runs._public(_run(1.2466))
        self.assertEqual(out["capability"]["state"], "cannot_trade")
        self.assertNotIn("config_snapshot_json", out)


if __name__ == "__main__":
    unittest.main()
