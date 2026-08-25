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
from datetime import datetime, timezone
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
        # The synthetic research batch yields ~1.5% theses, which the
        # build-time fee/edge gate refuses (hurdle ≈2.4% claimed). Every fleet
        # fixture below is about allocation, leverage, supervision or
        # replacement — not about that gate — so switch it off here and let
        # test_build_gates.py own it. Without this the fixtures would silently
        # assert "no members were built" for the wrong reason.
        os.environ["RUN_FEE_EDGE_MULTIPLE"] = "0"
        os.environ["FLEET_EXPECTANCY_GATE"] = "false"
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
        os.environ.pop("RUN_FEE_EDGE_MULTIPLE", None)
        os.environ.pop("FLEET_EXPECTANCY_GATE", None)
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

    def test_low_vol_slot_is_funded_above_a_high_vol_slot(self):
        """Equal dollars to a 0.3%/day forex pair and a 5%/day coin means the
        forex slot cannot move the account — dead capital under the profit
        mandate. Same confidence ⇒ the quieter instrument gets more notional so
        both slots carry comparable dollar risk."""
        quiet = {"confidence": 0.7,
                 "factor_scores_json": json.dumps({"factors": {"vol_daily_pct": 0.3}})}
        loud = {"confidence": 0.7,
                "factor_scores_json": json.dumps({"factors": {"vol_daily_pct": 5.0}})}
        alloc = fp.allocate_budget(1000.0, [quiet, loud])
        self.assertGreater(alloc[0], alloc[1])
        self.assertLessEqual(sum(alloc), 1000.0 + 1e-6)
        # the existing [B/2N, 2B/N] clamp still bounds the tilt
        for a in alloc:
            self.assertGreaterEqual(a, 250.0 - 1e-6)
            self.assertLessEqual(a, 1000.0 + 1e-6)

    def test_missing_vol_falls_back_to_confidence_only(self):
        """A thesis with no persisted factors must not be penalised — the
        weighting degrades to today's confidence-only split."""
        theses = [{"confidence": 0.9}, {"confidence": 0.9}]
        self.assertEqual(fp.allocate_budget(1000.0, theses),
                         [500.0, 500.0])

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

    def test_stop_and_trail_scale_to_position_not_budget(self):
        """The stop and trailing lock must scale to the POSITION (max_bet),
        not run_budget — a budget-scaled 20% stop sits ~44% beyond the actual
        position, so losers never cut and winners round-trip (2026-07-25)."""
        thesis = {"symbol": "AAA", "market": "crypto", "direction": "short",
                  "confidence": 0.7, "expected_move_pct": 2.0, "horizon_hours": 24}
        settings = fp.compose_run_settings(thesis, 1000.0,
                                           {"risk_appetite": "aggressive",
                                            "lang": "en"})
        sc = settings["stop_conditions"]
        max_bet = float(settings["max_bet_usd"])
        # aggressive: stop_loss_frac_of_bet 0.03
        self.assertAlmostEqual(sc["max_loss_usd"], round(max_bet * 0.03, 2), places=2)
        self.assertIn("trail", sc)
        # 2026-08-25: the 2026-07-26 rr=1.0 pin (activate == max_loss) is
        # SUPERSEDED by measurement — it never armed (0/13 fires, activation
        # $4.18–9.94 vs day-max peak $2.72). The trail now arms fee-anchored
        # at trail_activate_arm_mult × the ratchet arm, capped at half the
        # loss budget, and must sit strictly above the ratchet arm.
        notional = max_bet * 2.0  # aggressive tier auto-leverage 2×
        ratchet_arm = notional * 0.001 * 2.0
        self.assertAlmostEqual(sc["trail"]["activate_usd"],
                               round(ratchet_arm * 2.0, 2), places=2)
        self.assertLess(sc["trail"]["activate_usd"], sc["max_loss_usd"])
        self.assertGreater(sc["trail"]["activate_usd"], round(max_bet * 0.003, 2))
        self.assertEqual(sc["trail"]["giveback_frac"], 0.20)
        # fee-aware ratchet: above 3× the round-trip cost the giveback tightens
        self.assertEqual(sc["trail"]["tighten_giveback_frac"], 0.15)
        # …but never below the arming line, or the tight band would apply the
        # instant the lock arms.
        self.assertGreater(sc["trail"]["tighten_usd"], sc["trail"]["activate_usd"])
        # and it must be MUCH tighter than the old run_budget * 0.20 = $200
        self.assertLess(sc["max_loss_usd"], 200.0)

    def test_trail_tighten_uses_the_market_fee_not_a_flat_rate(self):
        """The ratchet line is "several round trips of profit". A round trip
        costs 0.045% on a perp and 0.008% on a major pair, so one flat rate
        prices one of them wrong by 5.6×. Leverage here is high enough that the
        fee term clears the arming floor and is actually observable.

        FEE_PER_MARKET is what prod runs with (verified on the box); the flag
        defaults off only for an unconfigured environment.

        2026-08-25: pinned under the LEGACY activation flag — the new
        fee-anchored activation (~0.4% of notional) masks the tighten fee
        term at this synthetic 10× leverage, and this test's purpose is the
        per-market fee correctness of the tighten term, not activation."""
        with patch.dict(os.environ, {"FEE_PER_MARKET": "true",
                                     "TRAIL_FEE_ANCHORED_ACTIVATION": "0"}):
            crypto = fp._trail_config(10_000.0, 10.0, 0.0, market="crypto")
            forex = fp._trail_config(10_000.0, 10.0, 0.0, market="forex")
        # 100k notional × rate × 2 legs × 3 round trips
        self.assertAlmostEqual(crypto["tighten_usd"], 270.0, places=2)
        self.assertAlmostEqual(forex["tighten_usd"], 48.0, places=2)

    def test_trail_activation_is_reachable_after_the_0_of_13_fix(self):
        """2026-08-25 (fleet 40, measured): the rr-anchored activation NEVER
        armed — 0 of 13 profit-rail fires, activation $4.18–9.94 against a
        day-max position peak of $2.72, so $4.15 of excursions round-tripped
        to −$0.43 through the breakeven ratchet (whose best case is $0 by
        design). The MFE gate passed (median peak ≈3.3× the round-trip fee,
        n=13), so the trail must arm on the same fee-anchored scale the
        ratchet uses: TRAIL arms at trail_activate_arm_mult × the ratchet's
        own arm (~0.2% of notional), i.e. ~0.4% of notional."""
        cfg = fp._trail_config(124.0, 1.0, 8.0, market="crypto")
        # Old formula: max(124×0.003, 8.0×1.0) = $8.00 — unreachable.
        # New: max(0.37 bet floor, 2 × 124×0.002 ratchet arm) = $0.50.
        self.assertLessEqual(cfg["activate_usd"], 1.0,
                             "activation is still loss-anchored (unreachable)")
        self.assertAlmostEqual(cfg["activate_usd"], 0.50, places=2)

    def test_trail_activation_sits_strictly_above_the_ratchet_arm(self):
        """Tier stack: the breakeven ratchet protects peaks in [1×..2×) of
        its arm at $0; the trail banks (1−giveback)×peak above. If activation
        ever lands at or below the ratchet arm the tiers collapse into one."""
        for max_bet, lev in ((124.0, 1.0), (500.0, 3.0), (2000.0, 2.0)):
            cfg = fp._trail_config(max_bet, lev, max_bet * 0.04,
                                   market="crypto")
            ratchet_arm = max_bet * lev * 0.001 * 2.0
            self.assertGreaterEqual(cfg["activate_usd"],
                                    round(ratchet_arm * 1.2, 2),
                                    f"bet={max_bet} lev={lev}")

    def test_trail_activation_cap_never_collapses_the_tier(self):
        """The half-max-loss cap bounds how long the trail waits to arm, but
        it may never push activation down onto the ratchet arm."""
        # leverage 2 so the bet floor (0.3% of margin) sits BELOW the ratchet
        # arm ×1.2 — otherwise the bet floor masks the cap's tier guarantee.
        cfg = fp._trail_config(124.0, 2.0, 0.5, market="crypto")
        ratchet_arm = 124.0 * 2.0 * 0.001 * 2.0
        self.assertGreaterEqual(cfg["activate_usd"],
                                round(ratchet_arm * 1.2, 2))

    def test_legacy_rr_activation_behind_the_flag(self):
        """One-flag revert: TRAIL_FEE_ANCHORED_ACTIVATION=0 restores the
        rr-anchored formula exactly (the pre-registered falsifier's revert
        path)."""
        with patch.dict(os.environ, {"TRAIL_FEE_ANCHORED_ACTIVATION": "0"}):
            cfg = fp._trail_config(124.0, 1.0, 8.0, market="crypto")
        self.assertAlmostEqual(cfg["activate_usd"], 8.0, places=2)

    def test_trail_fee_term_stays_masked_by_the_arming_floor_at_build(self):
        """Honesty pin: at every tier the built config lands on activate × 1.5,
        so the per-market fee above is a correctness fix with NO behavioural
        change on the build path. If a future tier change lets the fee term
        surface, this test fails and the change is a decision, not a side
        effect."""
        for risk in ("balanced", "aggressive", "extreme"):
            for market in ("crypto", "forex"):
                thesis = {"symbol": "AAA", "market": market, "direction": "long",
                          "confidence": 0.7, "expected_move_pct": 2.0,
                          "horizon_hours": 24}
                sc = fp.compose_run_settings(
                    thesis, 10_000.0,
                    {"risk_appetite": risk, "lang": "en"})["stop_conditions"]
                self.assertAlmostEqual(
                    sc["trail"]["tighten_usd"],
                    round(sc["trail"]["activate_usd"] * 1.5, 2), places=2,
                    msg=f"{risk}/{market}")

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


class GateCalibrationTests(FleetTestBase):
    """F3's second blind spot (2026-08-04): the gate clamp keys on the THESIS
    writer's confidence, but the gate judges the DESK's cycle confidence — a
    lower distribution. 939/940 carried 0.70+ theses, kept 0.65 gates, and
    idle-retired after ~43 hold cycles while 956 traded through its 0.57
    gate. The builder must cap the gate at the market's own recent p75."""

    def _seed_decisions(self, market, confidences):
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO trading_runs (agent_id, symbol, market, status, "
            "created_at) VALUES (?, 'SEED', ?, 'stopped', ?)",
            (self.agent_id, market, "2026-08-01T00:00:00Z"))
        run_id = cur.lastrowid
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        for i, c in enumerate(confidences):
            cur.execute(
                "INSERT INTO run_events (run_id, seq, event_type, ts, payload) "
                "VALUES (?, ?, 'decision', ?, ?)",
                (run_id, i + 1, ts, json.dumps({"confidence": c})))
        conn.commit()
        conn.close()

    def _compose(self, market="us-stock", thesis_conf=0.75):
        thesis = {"symbol": "NVDA", "market": market, "direction": "long",
                  "confidence": thesis_conf, "expected_move_pct": 3.0,
                  "horizon_hours": 48}
        return fp.compose_run_settings(thesis, 1000.0,
                                       {"risk_appetite": "balanced",
                                        "lang": "en"})

    def test_gate_capped_at_market_p75(self):
        # 40 decisions clustered where us-stock actually lives: p75 = 0.58.
        confs = [0.40] * 10 + [0.52] * 10 + [0.55] * 10 + [0.58] * 6 + [0.62] * 4
        self._seed_decisions("us-stock", confs)
        settings = self._compose(thesis_conf=0.75)
        self.assertAlmostEqual(settings["min_confidence"], 0.58, places=2)

    def test_no_samples_leaves_gate_alone(self):
        settings = self._compose(market="crypto", thesis_conf=0.75)
        # balanced tier gate 0.60, F3 clamp min(0.60, 0.70) = 0.60 — unchanged
        self.assertAlmostEqual(settings["min_confidence"], 0.60, places=2)

    def test_under_min_samples_leaves_gate_alone(self):
        self._seed_decisions("us-stock", [0.30] * 29)  # 29 < 30
        settings = self._compose(thesis_conf=0.75)
        self.assertAlmostEqual(settings["min_confidence"], 0.60, places=2)

    def test_floor_holds_against_a_weak_market(self):
        self._seed_decisions("us-stock", [0.30] * 40)  # p75 = 0.30
        settings = self._compose(thesis_conf=0.75)
        self.assertAlmostEqual(settings["min_confidence"], 0.50, places=2)

    def test_other_markets_decisions_do_not_leak(self):
        self._seed_decisions("crypto", [0.30] * 40)
        settings = self._compose(market="us-stock", thesis_conf=0.75)
        self.assertAlmostEqual(settings["min_confidence"], 0.60, places=2)


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
    # ORDER_DISCUSSION off on purpose: these tests own the light path's
    # budget-cap/dust mechanics, and the owner's order-discussion rule
    # (2026-08-13) would escalate every mocked buy to the full panel and
    # replace the decision under test. Escalation has its own suite
    # (test_order_discussion.py).
    def setUp(self):
        super().setUp()
        os.environ["ORDER_DISCUSSION"] = "0"

    def tearDown(self):
        os.environ.pop("ORDER_DISCUSSION", None)
        super().tearDown()

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


class ExposureFeasibilityClamp(unittest.TestCase):
    """The build-time exposure gate (2026-08-01). Prod fleet 24: $17k bets at
    5x sized $25-34k orders against a $10k per-symbol cap -> 100% risk-stage
    blocks -> idle-retire -> identical rebuild, an infinite churn loop that
    traded nothing. The full bet must be deployable at build time."""

    THESIS = {"symbol": "SOLUSDT", "market": "crypto", "direction": "long",
              "confidence": 0.7, "expected_move_pct": 4.0, "horizon_hours": 48}

    def test_fleet24_config_is_clamped_to_deployable(self):
        """FAIL-BEFORE/PASS-AFTER: the exact prod shape. run_budget 56,616.67
        at balanced (0.30) composed max_bet 16,985 with 5x leverage — every
        full-size order 84,925 notional vs the 10,000 cap. After the clamp
        max_bet is cap/leverage = 2,000, so the whole bet deploys."""
        settings = fp.compose_run_settings(
            self.THESIS, 56_616.67,
            {"risk_appetite": "balanced", "lang": "en", "leverage": 5})
        self.assertAlmostEqual(settings["max_bet_usd"], 2000.0, places=2)
        self.assertLessEqual(
            settings["max_bet_usd"] * settings["leverage"], 10_000.0)

    def test_stop_scales_to_the_clamped_bet(self):
        """max_loss must size to the bet the run can DEPLOY, not the pre-clamp
        fantasy — otherwise the stop sits miles beyond the real position."""
        settings = fp.compose_run_settings(
            self.THESIS, 56_616.67,
            {"risk_appetite": "balanced", "lang": "en", "leverage": 5})
        expected = round(2000.0 * fp._tier("stop_loss_frac_of_bet",
                                           "balanced"), 2)
        self.assertAlmostEqual(
            settings["stop_conditions"]["max_loss_usd"], expected, places=2)

    def test_sane_fleet_is_untouched(self):
        """Fleet 25's shape (max_bet ~1.4k at 1x) fits the cap — no clamp."""
        settings = fp.compose_run_settings(
            self.THESIS, 4770.0,
            {"risk_appetite": "balanced", "lang": "en", "leverage": 1})
        self.assertAlmostEqual(settings["max_bet_usd"], 1431.0, places=2)

    def test_owner_raised_cap_is_honored(self):
        """A deliberately raised max_symbol_exposure_usd loosens the clamp —
        the gate mirrors the risk engine's number, it does not impose 10k."""
        with patch.object(fp, "_exposure_cap_usd", return_value=50_000.0):
            settings = fp.compose_run_settings(
                self.THESIS, 56_616.67,
                {"risk_appetite": "balanced", "lang": "en", "leverage": 5})
        self.assertAlmostEqual(settings["max_bet_usd"], 10_000.0, places=2)

    def test_cap_zero_disables_the_clamp(self):
        """0 disables the risk-gate check, so it disables the build gate too."""
        with patch.object(fp, "_exposure_cap_usd", return_value=0.0):
            settings = fp.compose_run_settings(
                self.THESIS, 56_616.67,
                {"risk_appetite": "balanced", "lang": "en", "leverage": 5})
        self.assertAlmostEqual(settings["max_bet_usd"], 16_985.0, places=2)

    def test_unreadable_limits_fail_soft_to_default(self):
        """A limits read failure clamps to the engine DEFAULT (10k) — smaller
        is the safe direction; failing open reproduces the churn."""
        self.assertEqual(fp._exposure_cap_usd({"agent_id": None}), 10_000.0)
        self.assertEqual(fp._exposure_cap_usd({}), 10_000.0)
