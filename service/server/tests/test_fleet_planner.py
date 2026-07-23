"""Plan 14 Phase 3 gates — fleet build + budget enforcement.

Idempotent creation (one fleet per USER), allocation clamps, the §6.4
percent→fraction unit conversion (with its named mutation target), build
pipeline (skip-on-conflict, no orphan drafts, resume without double-create,
master-hold abort), the run-budget execution cap, light cycle mode, the
no-auto-restart guard, and the admin cascade.
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
import fleet_planner as fp
import symbol_research as sr
import trading_runs


def _candles(n=60, drift=0.8, volume=5_000_000):
    out, price = [], 100.0
    for i in range(n):
        price *= 1 + drift / 100.0
        out.append({"ts": i, "open": price, "high": price, "low": price,
                    "close": price, "volume": volume})
    return out


def _seed_batch(symbols=("AAA", "BBB", "CCC", "DDD", "EEE", "FFF")):
    universe = [{"symbol": s, "market": "crypto"} for s in symbols]
    with patch.object(sr, "build_universe", return_value=universe), \
         patch.object(sr, "_read_overlays",
                      return_value={"event_window": False,
                                    "regime_blocks_longs": False, "policy": {}}), \
         patch("cache.acquire_lock", return_value=None):
        return sr.refresh_research_batch(
            generate_text=lambda *a, **k: None,
            fetch_candles=lambda s, m: _candles())


class FleetTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO users (email, password_hash, created_at) "
            "VALUES ('h@x.com', 'x', '2026-01-01T00:00:00Z')")
        self.user_id = cur.lastrowid
        cur.execute(
            "INSERT INTO agents (name, token_hash, cash, user_id, created_at) "
            "VALUES ('fleet-agent', 'th1', 100000, ?, '2026-01-01T00:00:00Z')",
            (self.user_id,))
        self.agent_id = cur.lastrowid
        cur.execute(
            "INSERT INTO agents (name, token_hash, cash, user_id, created_at) "
            "VALUES ('fleet-agent-2', 'th2', 100000, ?, '2026-01-01T00:00:00Z')",
            (self.user_id,))
        self.agent2_id = cur.lastrowid
        conn.commit()
        conn.close()
        # tier: professional (max_fleet_size 10) without a real subscription row
        self.plan = patch("entitlements.plan_code_for_user",
                          return_value="professional")
        self.plan.start()
        self.probe = patch("routes_runs._probe_price", return_value=100.0)
        self.probe.start()

    def tearDown(self):
        self.plan.stop()
        self.probe.stop()
        self.tmp.cleanup()

    def _fleet(self, n=3, budget=3000.0, **kw):
        return fp.create_fleet(self.agent_id, n, budget, **kw)


class CreationTests(FleetTestBase):
    def test_one_fleet_per_user_across_agents(self):
        """The active_fleet_key is per USER — a second agent of the same user
        cannot open a second fleet (round-5: per-agent contradicted the cost
        model)."""
        self._fleet()
        with self.assertRaises(fp.FleetConflict):
            fp.create_fleet(self.agent2_id, 2, 1000.0)

    def test_idempotency_key_returns_same_fleet(self):
        a = self._fleet(idempotency_key="click-1")
        b = fp.create_fleet(self.agent_id, 3, 3000.0, idempotency_key="click-1")
        self.assertEqual(a, b)

    def test_tier_gate_is_always_on(self):
        """check_fleet_create must deny with no plan even though
        ENTITLEMENTS_ENFORCED is off (conftest default)."""
        assert os.getenv("ENTITLEMENTS_ENFORCED", "false") != "1"
        with patch("entitlements.plan_code_for_user", return_value=None):
            with self.assertRaises(trading_runs.EntitlementDenied):
                self._fleet()

    def test_rails_validation(self):
        with self.assertRaises(ValueError):
            self._fleet(warn_loss_frac=0.5, stop_loss_frac=0.4)  # warn >= stop
        with self.assertRaises(ValueError):
            self._fleet(warn_loss_frac=0.3, stop_loss_frac=0.6)  # stop > 0.40


class AllocationTests(unittest.TestCase):
    def test_sum_never_exceeds_budget_and_clamps(self):
        theses = [{"confidence": c} for c in (0.9, 0.9, 0.9, 0.2)]
        alloc = fp.allocate_budget(1000.0, theses)
        self.assertLessEqual(sum(alloc), 1000.0 + 1e-6)
        equal = 250.0
        for a in alloc:
            self.assertGreaterEqual(a, equal * 0.5 - 1e-6)
            self.assertLessEqual(a, equal * 2.0 + 1e-6)

    def test_degenerate_single_slot(self):
        alloc = fp.allocate_budget(500.0, [{"confidence": 0.7}])
        self.assertEqual(alloc, [500.0])

    def test_profit_target_unit_conversion(self):
        """A 2.0% thesis on a $1,000 slot ⇒ ~$20 target, NOT $500 — the
        round-4 unit-confusion critical (mutation: drop the /100)."""
        thesis = {"symbol": "AAA", "market": "crypto", "direction": "long",
                  "confidence": 0.7, "expected_move_pct": 2.0,
                  "horizon_hours": 48}
        settings = fp.compose_run_settings(thesis, 1000.0,
                                           {"risk_appetite": "balanced",
                                            "lang": "en"})
        self.assertAlmostEqual(
            settings["stop_conditions"]["profit_target_usd"], 20.0, places=2)

    def test_short_thesis_maps_to_futures_book(self):
        thesis = {"symbol": "AAA", "market": "crypto", "direction": "short",
                  "confidence": 0.7, "expected_move_pct": 2.0,
                  "horizon_hours": 24}
        settings = fp.compose_run_settings(thesis, 1000.0,
                                           {"risk_appetite": "balanced",
                                            "lang": "en"})
        self.assertEqual(settings["market_type"], "futures")

    def test_stop_flatten_pinned(self):
        thesis = {"symbol": "AAA", "market": "crypto", "direction": "long",
                  "confidence": 0.7, "expected_move_pct": 2.0,
                  "horizon_hours": 24}
        settings = fp.compose_run_settings(thesis, 1000.0,
                                           {"risk_appetite": "stable",
                                            "lang": "en"})
        self.assertTrue(settings["stop_flatten"])


class BuildTests(FleetTestBase):
    def _build(self, n=3, budget=3000.0):
        _seed_batch()
        fleet_id = self._fleet(n=n, budget=budget)
        fp.start_fleet(fleet_id, self.agent_id)
        fleet = fp.get_fleet(fleet_id)
        fp._do_research(fleet)
        fleet = fp.get_fleet(fleet_id)
        if fleet["status"] == fp.STATUS_BUILDING:
            fp._do_build(fleet)
        return fleet_id

    def test_happy_path_builds_n_members(self):
        fleet_id = self._build(n=3)
        fleet = fp.get_fleet(fleet_id)
        members = fp.list_members(fleet_id)
        self.assertEqual(fleet["status"], fp.STATUS_ACTIVE)
        self.assertEqual(len(members), 3)
        for m in members:
            self.assertEqual(m["created_via"], "fleet")
            self.assertEqual(m["fleet_id"], fleet_id)
            self.assertEqual(m["status"], trading_runs.STATUS_RUNNING)
            cfg = json.loads(m["config_snapshot_json"])
            self.assertIn("thesis", cfg)         # §4.4 top-level storage
            self.assertTrue(cfg.get("feedback"))
        # slots bound
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) AS n FROM fleet_slots WHERE fleet_id = ? "
                    "AND current_run_id IS NOT NULL", (fleet_id,))
        self.assertEqual(int(cur.fetchone()["n"]), 3)
        conn.close()

    def test_sum_of_member_budgets_leq_total(self):
        fleet_id = self._build(n=4, budget=2000.0)
        total = 0.0
        for m in fp.list_members(fleet_id):
            cfg = json.loads(m["config_snapshot_json"])
            total += float(cfg.get("run_budget_usd") or 0)
        self.assertLessEqual(total, 2000.0 + 1e-6)

    def test_busy_symbol_skipped_next_candidate_taken(self):
        """A user run on a selected symbol ⇒ that candidate skips, the fleet
        still builds from the remaining pool (the 6-symbol overfetch)."""
        _seed_batch()
        # user manually runs the top candidate's symbol
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT symbol FROM research_theses ORDER BY final_score DESC")
        top_symbol = cur.fetchone()["symbol"]
        cur.execute(
            "INSERT INTO trading_runs (agent_id, symbol, market, status, created_at)"
            " VALUES (?, ?, 'crypto', 'running', '2026-01-01T00:00:00Z')",
            (self.agent_id, top_symbol))
        conn.commit()
        conn.close()
        fleet_id = self._fleet(n=2, budget=1000.0)
        fp.start_fleet(fleet_id, self.agent_id)
        fp._do_research(fp.get_fleet(fleet_id))
        fp._do_build(fp.get_fleet(fleet_id))
        members = fp.list_members(fleet_id)
        self.assertNotIn(top_symbol, {m["symbol"] for m in members})
        self.assertGreaterEqual(len(members), 1)

    def test_rebuild_does_not_double_create(self):
        """Crash-resume: a second _do_build pass over the same fleet must not
        create duplicate members (allocations consumed by key/state)."""
        fleet_id = self._build(n=3)
        before = len(fp.list_members(fleet_id))
        fleet = fp.get_fleet(fleet_id)
        fleet["status"] = fp.STATUS_BUILDING  # simulate stale claim view
        fp._do_build(fleet)
        self.assertEqual(len(fp.list_members(fleet_id)), before)

    def test_master_hold_aborts_build(self):
        """Hold landing mid-build ⇒ build_aborted, no further runs created."""
        _seed_batch()
        fleet_id = self._fleet(n=3, budget=3000.0)
        fp.start_fleet(fleet_id, self.agent_id)
        fp._do_research(fp.get_fleet(fleet_id))
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE users SET ai_automation_state = 'held' WHERE id = ?",
                    (self.user_id,))
        conn.commit()
        conn.close()
        fp._do_build(fp.get_fleet(fleet_id))
        self.assertEqual(fp.list_members(fleet_id), [])
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT payload FROM fleet_events WHERE fleet_id = ? AND "
                    "event_type = 'build_aborted'", (fleet_id,))
        rows = cur.fetchall()
        conn.close()
        self.assertTrue(rows)

    def test_entitlement_denied_leaves_no_orphan_draft(self):
        """Headroom race mid-build ⇒ partial finish AND no stray draft rows
        (the QA orphan-draft finding)."""
        _seed_batch()
        fleet_id = self._fleet(n=3, budget=3000.0)
        fp.start_fleet(fleet_id, self.agent_id)
        fp._do_research(fp.get_fleet(fleet_id))
        real_start = trading_runs.start_run
        calls = {"n": 0}

        def deny_second(run_id, agent_id):
            calls["n"] += 1
            if calls["n"] >= 2:
                raise trading_runs.EntitlementDenied("plan limit")
            return real_start(run_id, agent_id)

        with patch.object(trading_runs, "start_run", side_effect=deny_second):
            fp._do_build(fp.get_fleet(fleet_id))
        members = fp.list_members(fleet_id)
        self.assertTrue(all(m["status"] != trading_runs.STATUS_DRAFT
                            for m in members))
        fleet = fp.get_fleet(fleet_id)
        self.assertEqual(fleet["status"], fp.STATUS_ACTIVE)
        self.assertTrue((fleet["status_reason"] or "").startswith("partial:"))


class RunEngineFleetTests(FleetTestBase):
    def _member(self):
        _seed_batch()
        fleet_id = self._fleet(n=1, budget=1000.0)
        fp.start_fleet(fleet_id, self.agent_id)
        fp._do_research(fp.get_fleet(fleet_id))
        fp._do_build(fp.get_fleet(fleet_id))
        members = fp.list_members(fleet_id)
        self.assertEqual(len(members), 1)
        return fleet_id, members[0]


    def test_dust_headroom_skips_instead_of_trading(self):
        """Plan 15 overnight: headroom below max($10, 2% of max_bet) must
        skip (budget_headroom_skip), not place a dust add."""
        import json as _j
        import run_engine
        _seed_batch()
        fleet_id = self._fleet(n=1, budget=10000.0)
        fp.start_fleet(fleet_id, self.agent_id)
        fp._do_research(fp.get_fleet(fleet_id))
        fp._do_build(fp.get_fleet(fleet_id))
        member = fp.list_members(fleet_id)[0]
        cfg = _j.loads(member["config_snapshot_json"])
        max_bet = float(cfg["max_bet_usd"])
        floor = max(10.0, 0.02 * max_bet)
        # floor must exceed the flat $10 for this test to bite
        self.assertGreater(floor, 10.0)
        headroom = (10.0 + floor) / 2.0   # between old ($10) and new floor
        basis = float(cfg["run_budget_usd"]) - headroom
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO positions (agent_id, symbol, market, side, quantity, "
            "entry_price, opened_at, run_id) VALUES (?, ?, 'crypto', 'buy', 10, "
            "?, '2026-01-01T00:00:00Z', ?)",
            (self.agent_id, member["symbol"], basis / 10.0, member["id"]))
        conn.commit()
        conn.close()
        with patch("llm_client.generate_text",
                   return_value='{"action": "buy", "confidence": 0.9, "report": "go"}'), \
             patch("price_fetcher.get_price_from_market", return_value=100.0), \
             patch("price_fetcher.get_daily_candles", return_value=[]):
            result = run_engine.run_cycle(member["id"])
        self.assertFalse(result["executed"], result)
        self.assertEqual(result["skip_reason"], "budget_headroom_skip")

    def test_no_auto_restart_for_fleet_members(self):
        """A fleet member stopped on profit_target must NOT clone (the
        round-4 double-deploy critical)."""
        import run_engine
        fleet_id, member = self._member()
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "UPDATE trading_runs SET status='stopped', "
            "status_reason='stop_event:profit_target' WHERE id = ?",
            (member["id"],))
        conn.commit()
        conn.close()
        run = trading_runs.get_run(member["id"], self.agent_id)
        before = len(fp.list_members(fleet_id))
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) AS n FROM trading_runs")
        total_before = int(cur.fetchone()["n"])
        conn.close()
        run_engine._maybe_auto_restart(run)
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) AS n FROM trading_runs")
        total_after = int(cur.fetchone()["n"])
        conn.close()
        self.assertEqual(total_after, total_before)
        self.assertEqual(len(fp.list_members(fleet_id)), before)

    def test_light_mode_one_llm_call_and_budget_cap(self):
        """Light cycle = exactly one generate_text call, the decision event
        still fires for tick accounting, and an exhausted run_budget produces
        budget_headroom_skip with NO trade (the gate/budget path is shared)."""
        import run_engine
        fleet_id, member = self._member()
        cfg = json.loads(member["config_snapshot_json"])
        llm_calls = []

        def fake_llm(prompt, **kw):
            llm_calls.append(1)
            return '{"action": "buy", "confidence": 0.9, "report": "go"}'

        # exhaust the budget: position open basis == run_budget
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO positions (agent_id, symbol, market, side, quantity, "
            "entry_price, opened_at, run_id) VALUES (?, ?, 'crypto', 'buy', 10, "
            "?, '2026-01-01T00:00:00Z', ?)",
            (self.agent_id, member["symbol"],
             float(cfg["run_budget_usd"]) / 10.0, member["id"]))
        conn.commit()
        conn.close()

        with patch("llm_client.generate_text", side_effect=fake_llm), \
             patch("price_fetcher.get_price_from_market", return_value=100.0), \
             patch("price_fetcher.get_daily_candles", return_value=[]):
            result = run_engine.run_cycle(member["id"])

        self.assertEqual(len(llm_calls), 1)
        self.assertFalse(result["executed"])
        self.assertEqual(result["skip_reason"], "budget_headroom_skip")
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT event_type FROM run_events WHERE run_id = ?",
                    (member["id"],))
        types = {r["event_type"] for r in cur.fetchall()}
        conn.close()
        self.assertIn("decision", types)  # tick accounting still fires

    def test_master_hold_pre_gate_blocks_cycle(self):
        import run_engine
        fleet_id, member = self._member()
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE users SET ai_automation_state = 'held' WHERE id = ?",
                    (self.user_id,))
        conn.commit()
        conn.close()
        with patch("llm_client.generate_text",
                   side_effect=AssertionError("LLM under hold")):
            result = run_engine.run_cycle(member["id"])
        self.assertFalse(result["executed"])
        self.assertIn("held", result["skip_reason"] or "")


class AdminCascadeTests(FleetTestBase):
    def test_agent_delete_leaves_no_fleet_orphans(self):
        _seed_batch()
        fleet_id = self._fleet(n=2, budget=1000.0)
        fp.start_fleet(fleet_id, self.agent_id)
        fp._do_research(fp.get_fleet(fleet_id))
        fp._do_build(fp.get_fleet(fleet_id))
        from routes_admin import _delete_agent_cascade
        conn = database.get_db_connection()
        cur = conn.cursor()
        _delete_agent_cascade(cur, self.agent_id)
        conn.commit()
        for table in ("fleets", "fleet_events", "fleet_candidates",
                      "fleet_slots", "fleet_symbol_cooldowns"):
            cur.execute(f"SELECT COUNT(*) AS n FROM {table}")
            self.assertEqual(int(cur.fetchone()["n"]), 0, table)
        conn.close()


if __name__ == "__main__":
    unittest.main()
