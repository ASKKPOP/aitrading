"""Plan 14 Phase 4 gates — feedback loop + supervision rails.

Anti-martingale ladder property (+ its named mutation), fence-guarded state
saves, Tier-2-first gap behavior, the −30% episode latch (resume sticks,
−5pp legs, oscillation ⇒ no SMS storm), replacement suspension while warned,
per-reason replacement, positions_held slot occupation, sequential same-tick
funding, reserved rail alert budget, retire → cooldown row → symbol excluded.
"""

from __future__ import annotations

import itertools
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
import fleet_supervisor as fs
import run_feedback as rf
import symbol_research as sr
import trading_runs


def _candles(n=60, drift=0.8, volume=5_000_000):
    out, price = [], 100.0
    for i in range(n):
        price *= 1 + drift / 100.0
        out.append({"ts": i, "open": price, "high": price, "low": price,
                    "close": price, "volume": volume})
    return out


class LadderPropertyTests(unittest.TestCase):
    def test_anti_martingale_over_all_sequences(self):
        """For EVERY win/loss sequence of length ≤ 8: size after a loss is
        never above size before it, and size never exceeds 1.0 (the hard
        ceiling). The named mutation target: step-up-on-loss must fail."""
        for length in range(1, 9):
            for seq in itertools.product([True, False], repeat=length):
                state = rf.load_state({"adapt_state_json": None})
                for i, win in enumerate(seq):
                    before = state["size_mult"]
                    rf.ingest_outcomes(state, [{
                        "signal_id": i + 1, "realized": 5.0 if win else -5.0,
                        "direction": "long", "win": win}])
                    after = state["size_mult"]
                    self.assertLessEqual(after, 1.0)
                    if not win:
                        self.assertLessEqual(after, before)
                    else:
                        # wins restore at most one rung
                        ladder = rf.ADAPT_BOUNDS["ladder"]
                        self.assertLessEqual(ladder.index(after),
                                             ladder.index(before) + 1)

    def test_scratch_trade_counts_as_loss(self):
        state = rf.load_state({"adapt_state_json": None})
        rf.ingest_outcomes(state, [{"signal_id": 1, "realized": -0.01,
                                    "direction": "long", "win": False}])
        self.assertEqual(state["consecutive_losses"], 1)
        self.assertLess(state["size_mult"], 1.0)

    def test_corrupt_state_resets_conservative(self):
        state = rf.load_state({"adapt_state_json": "{broken"})
        self.assertEqual(state["size_mult"], 0.5)  # NOT 1.0
        self.assertTrue(state.get("_reset"))

    def test_effective_params_shrink_and_tighten_only(self):
        state = rf.load_state({"adapt_state_json": None})
        state["size_mult"] = 0.5
        state["conf_bump"] = 0.10
        p = rf.effective_gate_params(state, {"max_bet_usd": 100,
                                             "min_confidence": 0.6})
        self.assertEqual(p["size_usd"], 50.0)
        self.assertAlmostEqual(p["min_confidence"], 0.70)

    def test_retire_after_three_consecutive_losses(self):
        state = rf.load_state({"adapt_state_json": None})
        for i in range(3):
            rf.ingest_outcomes(state, [{"signal_id": i + 1, "realized": -5.0,
                                        "direction": "long", "win": False}])
        policy = rf.apply_policy(state, {"stop_conditions_json": "{}"},
                                 {"max_bet_usd": 100},
                                 {"total": -15, "unrealized": 0,
                                  "mark_age_ok": True})
        self.assertTrue(policy["retire"])
        self.assertEqual(policy["reason"], "consecutive_losses")

    def test_reentry_block_same_direction_only(self):
        state = rf.load_state({"adapt_state_json": None})
        state["last_close"] = {"ts": rf._now_iso(), "direction": "long",
                               "win": False}
        self.assertTrue(rf.blocked_reentry(state, "buy"))
        self.assertFalse(rf.blocked_reentry(state, "short"))
        state["last_close"]["win"] = True
        self.assertFalse(rf.blocked_reentry(state, "buy"))


class SupervisionBase(unittest.TestCase):
    def setUp(self):
        # Synthetic theses are ~1.5%, below the build-time fee/edge hurdle
        # (~2.4% claimed). These fixtures are about supervision and replacement, not that gate —
        # test_build_gates.py owns it.
        os.environ["RUN_FEE_EDGE_MULTIPLE"] = "0"
        os.environ["FLEET_EXPECTANCY_GATE"] = "false"
        # module-level retry cache is keyed by (fleet_id, slot_index); every
        # test recreates fleet 1 in the same process, so reset it
        fs._LAST_EMPTY_ATTEMPT.clear()
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO users (email, password_hash, created_at) "
                    "VALUES ('h@x.com', 'x', '2026-01-01T00:00:00Z')")
        self.user_id = cur.lastrowid
        cur.execute(
            "INSERT INTO agents (name, token_hash, cash, user_id, created_at) "
            "VALUES ('sup-agent', 'th', 100000, ?, '2026-01-01T00:00:00Z')",
            (self.user_id,))
        self.agent_id = cur.lastrowid
        conn.commit()
        conn.close()
        self.plan = patch("entitlements.plan_code_for_user",
                          return_value="professional")
        self.plan.start()
        self.probe = patch("routes_runs._probe_price", return_value=100.0)
        self.probe.start()
        self.alerts = []
        self.alert_patch = patch(
            "alerts.send_alert",
            side_effect=lambda agent_id, kind, title, body, **kw:
            self.alerts.append({"kind": kind, "title": title,
                                "dedupe": kw.get("dedupe_key")}))
        self.alert_patch.start()

    def tearDown(self):
        os.environ.pop("RUN_FEE_EDGE_MULTIPLE", None)
        os.environ.pop("FLEET_EXPECTANCY_GATE", None)
        self.plan.stop()
        self.probe.stop()
        self.alert_patch.stop()
        self.tmp.cleanup()

    def _seed_research(self):
        universe = [{"symbol": s, "market": "crypto"}
                    for s in ("AAA", "BBB", "CCC", "DDD", "EEE")]
        with patch.object(sr, "build_universe", return_value=universe), \
             patch.object(sr, "_read_overlays",
                          return_value={"event_window": False,
                                        "regime_blocks_longs": False,
                                        "policy": {}}), \
             patch("cache.acquire_lock", return_value=None):
            sr.refresh_research_batch(
                generate_text=lambda *a, **k: None,
                fetch_candles=lambda s, m: _candles())

    def _built_fleet(self, n=2, budget=2000.0, **kw):
        self._seed_research()
        fleet_id = fp.create_fleet(self.agent_id, n, budget, **kw)
        fp.start_fleet(fleet_id, self.agent_id)
        fp._do_research(fp.get_fleet(fleet_id))
        fp._do_build(fp.get_fleet(fleet_id))
        return fleet_id

    def _set_equity_loss(self, fleet_id, loss_frac):
        """Force marked_equity to report the given loss fraction."""
        fleet = fp.get_fleet(fleet_id)
        total = float(fleet["total_budget_usd"])
        return patch.object(fs.fp, "marked_equity",
                            return_value={"equity": total * (1 - loss_frac),
                                          "ok": True, "zombie_basis": 0.0,
                                          "pnl": -total * loss_frac})


class RailTests(SupervisionBase):
    def test_tier2_first_gap_one_stop_all_one_sms(self):
        """Equity gapping straight through both tiers ⇒ exactly one stop-all,
        ONE SMS, and no warning SMS."""
        fleet_id = self._built_fleet()
        with self._set_equity_loss(fleet_id, 0.45):
            fs.supervise_fleet(fp.get_fleet(fleet_id))
        kinds = [a["kind"] for a in self.alerts]
        self.assertEqual(kinds.count("fleet_breaker"), 1)
        self.assertEqual(kinds.count("fleet_drawdown_warning"), 0)
        fleet = fp.get_fleet(fleet_id)
        self.assertIn(fleet["status"], (fp.STATUS_STOPPING, fp.STATUS_STOPPED))
        self.assertEqual(fleet["status_reason"], "breaker")

    def test_warning_latch_resume_sticks(self):
        """Warn at −32% ⇒ members paused with the marker; ack ⇒ resumed; the
        NEXT tick at −32% does NOT re-pause (episode latch consumed)."""
        fleet_id = self._built_fleet()
        with self._set_equity_loss(fleet_id, 0.32):
            fs.supervise_fleet(fp.get_fleet(fleet_id))
        members = fp.list_members(fleet_id)
        self.assertTrue(all(m["status"] == "paused" and
                            m["paused_reason"] == "drawdown_warning"
                            for m in members))
        self.assertEqual(len([a for a in self.alerts
                              if a["kind"] == "fleet_drawdown_warning"]), 1)
        fs.ack_warning(fleet_id, self.agent_id)
        members = fp.list_members(fleet_id)
        self.assertTrue(all(m["status"] == "running" for m in members))
        with self._set_equity_loss(fleet_id, 0.32):
            fs.supervise_fleet(fp.get_fleet(fleet_id))
        members = fp.list_members(fleet_id)
        self.assertTrue(all(m["status"] == "running" for m in members),
                        "resume must stick while equity stays in the band")
        self.assertEqual(len([a for a in self.alerts
                              if a["kind"] == "fleet_drawdown_warning"]), 1)

    def test_fresh_leg_after_ack_fires_once(self):
        """Acked −30% then slide to −35% ⇒ exactly one NEW SMS + re-pause."""
        fleet_id = self._built_fleet()
        with self._set_equity_loss(fleet_id, 0.31):
            fs.supervise_fleet(fp.get_fleet(fleet_id))
        fs.ack_warning(fleet_id, self.agent_id)
        with self._set_equity_loss(fleet_id, 0.36):
            fs.supervise_fleet(fp.get_fleet(fleet_id))
        warns = [a for a in self.alerts if a["kind"] == "fleet_drawdown_warning"]
        self.assertEqual(len(warns), 2)
        self.assertNotEqual(warns[0]["dedupe"], warns[1]["dedupe"])
        members = fp.list_members(fleet_id)
        self.assertTrue(all(m["status"] == "paused" for m in members))

    def test_oscillation_no_sms_storm(self):
        """Hovering just below −30% across many ticks ⇒ one SMS total."""
        fleet_id = self._built_fleet()
        for loss in (0.31, 0.32, 0.31, 0.33, 0.31):
            with self._set_equity_loss(fleet_id, loss):
                fs.supervise_fleet(fp.get_fleet(fleet_id))
        warns = [a for a in self.alerts if a["kind"] == "fleet_drawdown_warning"]
        self.assertEqual(len(warns), 1)

    def test_recovery_rearms_latch(self):
        """Warn → recover above −25% (latch clears, members resume) → cross
        again ⇒ a second warning fires."""
        fleet_id = self._built_fleet()
        with self._set_equity_loss(fleet_id, 0.31):
            fs.supervise_fleet(fp.get_fleet(fleet_id))
        with self._set_equity_loss(fleet_id, 0.20):
            fs.supervise_fleet(fp.get_fleet(fleet_id))
        members = fp.list_members(fleet_id)
        self.assertTrue(all(m["status"] == "running" for m in members))
        with self._set_equity_loss(fleet_id, 0.31):
            fs.supervise_fleet(fp.get_fleet(fleet_id))
        warns = [a for a in self.alerts if a["kind"] == "fleet_drawdown_warning"]
        self.assertEqual(len(warns), 2)

    def test_member_paused_at_warning_still_evaluates_stops(self):
        """The engine's own guarantee — pause blocks entries, not stops. Pin
        that the warning uses pause_run (not some entry-only hack)."""
        fleet_id = self._built_fleet()
        with self._set_equity_loss(fleet_id, 0.31):
            fs.supervise_fleet(fp.get_fleet(fleet_id))
        m = fp.list_members(fleet_id)[0]
        self.assertEqual(m["status"], trading_runs.STATUS_PAUSED)

    def test_eval_failure_freezes_and_escalates(self):
        fleet_id = self._built_fleet()
        frozen = {"equity": 0.0, "ok": False, "zombie_basis": 0.0, "pnl": 0.0}
        with patch.object(fs.fp, "marked_equity", return_value=frozen):
            for _ in range(fs.EVAL_FAIL_LIMIT):
                fs.supervise_fleet(fp.get_fleet(fleet_id))
        fleet = fp.get_fleet(fleet_id)
        self.assertEqual(fleet["entry_paused_reason"], "eval_failed")
        # frozen ticks must not have stopped the fleet on garbage equity
        self.assertNotEqual(fleet["status"], fp.STATUS_STOPPED)


class ReplacementTests(SupervisionBase):
    def _stop_member(self, member, reason):
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "UPDATE trading_runs SET status='stopped', status_reason=?, "
            "active_key=NULL WHERE id = ?", (reason, member["id"]))
        conn.commit()
        conn.close()

    def test_immediate_replacement_on_profit_target(self):
        fleet_id = self._built_fleet(n=2)
        member = fp.list_members(fleet_id)[0]
        self._stop_member(member, "stop_event:profit_target")
        fs.supervise_fleet(fp.get_fleet(fleet_id))
        live = [m for m in fp.list_members(fleet_id)
                if m["status"] in ("running", "armed")]
        self.assertEqual(len(live), 2, "perpetual N: slot must refill")
        # replacement must not reuse the retired symbol tuple concurrently
        symbols = [m["symbol"] for m in live]
        self.assertEqual(len(symbols), len(set(symbols)))

    def test_user_stop_closes_slot_permanently(self):
        fleet_id = self._built_fleet(n=2)
        member = fp.list_members(fleet_id)[0]
        self._stop_member(member, "user_stop")
        fs.supervise_fleet(fp.get_fleet(fleet_id))
        live = [m for m in fp.list_members(fleet_id)
                if m["status"] in ("running", "armed")]
        self.assertEqual(len(live), 1, "user shrink is permanent")
        slots = fs._slots(fleet_id)
        self.assertIn("closed", [s["state"] for s in slots])

    def test_replacement_suspended_while_warning_unacked(self):
        """Member retires below a (tightened) warn rail ⇒ NO replacement;
        ack ⇒ replacement next pass (STATE-based suspension, round-5).
        Rails tightened to 10/20 so equity headroom can still fund the slot
        — at deep losses dormancy would legitimately block funding anyway."""
        universe_fleet = self._built_fleet(n=2, budget=2000.0,
                                           warn_loss_frac=0.10,
                                           stop_loss_frac=0.20)
        member = fp.list_members(universe_fleet)[0]
        self._stop_member(member, "adapt_retired")
        with self._set_equity_loss(universe_fleet, 0.12):
            fs.supervise_fleet(fp.get_fleet(universe_fleet))
        live = [m for m in fp.list_members(universe_fleet)
                if m["status"] in ("running", "paused", "armed")]
        self.assertEqual(len(live), 1, "no fresh money below an unacked warn")
        fs.ack_warning(universe_fleet, self.agent_id)
        with self._set_equity_loss(universe_fleet, 0.12):
            fs.supervise_fleet(fp.get_fleet(universe_fleet))
        live = [m for m in fp.list_members(universe_fleet)
                if m["status"] in ("running", "paused", "armed")]
        self.assertEqual(len(live), 2, "ack re-enables replacement")

    def test_stop_eval_failed_waits_for_healthy_batch(self):
        fleet_id = self._built_fleet(n=2)
        member = fp.list_members(fleet_id)[0]
        self._stop_member(member, "stop_eval_failed")
        with patch.object(fs, "_fresh_batch_exists", return_value=False):
            fs.supervise_fleet(fp.get_fleet(fleet_id))
        live = [m for m in fp.list_members(fleet_id)
                if m["status"] in ("running", "armed")]
        self.assertEqual(len(live), 1, "dead-feed stop must not replace")
        fs.supervise_fleet(fp.get_fleet(fleet_id))  # batch healthy again
        live = [m for m in fp.list_members(fleet_id)
                if m["status"] in ("running", "armed")]
        self.assertEqual(len(live), 2)

    def test_synthetic_liquidation_writes_cooldown(self):
        fleet_id = self._built_fleet(n=2)
        member = fp.list_members(fleet_id)[0]
        self._stop_member(member, "synthetic_liquidation")
        fs.supervise_fleet(fp.get_fleet(fleet_id))
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) AS n FROM fleet_symbol_cooldowns WHERE "
            "agent_id = ? AND symbol = ?", (self.agent_id, member["symbol"]))
        self.assertEqual(int(cur.fetchone()["n"]), 1)
        conn.close()
        # and the replacement (if any) is a different symbol
        live_syms = {m["symbol"] for m in fp.list_members(fleet_id)
                     if m["status"] in ("running", "armed")}
        self.assertNotIn(member["symbol"], live_syms)

    def test_positions_held_keeps_slot_occupied(self):
        """A flatten-timeout zombie: slot occupied, no replacement, symbol
        excluded — until the unowned book clears (round-5 critical)."""
        fleet_id = self._built_fleet(n=2)
        member = fp.list_members(fleet_id)[0]
        conn = database.get_db_connection()
        cur = conn.cursor()
        # the zombie's opening leg (replay source) + the released position row
        cur.execute(
            "INSERT INTO signals (signal_id, agent_id, message_type, market, "
            "symbol, side, entry_price, quantity, run_id, timestamp, created_at) "
            "VALUES (999001, ?, 'operation', 'crypto', ?, 'buy', 100, 5, ?, "
            "'2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')",
            (self.agent_id, member["symbol"], member["id"]))
        cur.execute(
            "INSERT INTO positions (agent_id, symbol, market, side, quantity, "
            "entry_price, current_price, price_updated_at, opened_at, run_id) "
            "VALUES (?, ?, 'crypto', 'buy', 5, 100, 100, ?, "
            "'2026-01-01T00:00:00Z', NULL)",
            (self.agent_id, member["symbol"], rf._now_iso()))
        conn.commit()
        conn.close()
        self._stop_member(member, "positions_held")
        fs.supervise_fleet(fp.get_fleet(fleet_id))
        live = [m for m in fp.list_members(fleet_id)
                if m["status"] in ("running", "armed")]
        self.assertEqual(len(live), 1, "zombie slot must stay occupied")
        # close the zombie in the unowned book ⇒ slot becomes eligible
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM positions WHERE agent_id = ? AND symbol = ? "
                    "AND run_id IS NULL", (self.agent_id, member["symbol"]))
        conn.commit()
        conn.close()
        fs.supervise_fleet(fp.get_fleet(fleet_id))
        live = [m for m in fp.list_members(fleet_id)
                if m["status"] in ("running", "armed")]
        self.assertEqual(len(live), 2, "cleared zombie frees the slot")


class ZombieStalenessTests(SupervisionBase):
    def test_stale_zombie_mark_freezes_supervision(self):
        """A positions_held zombie with a stale (or missing) mark must make
        the equity evaluation FAIL — never contribute unrealized=0 (round-5
        mutation target: drop the reconstruction ⇒ this must fail)."""
        fleet_id = self._built_fleet(n=2)
        member = fp.list_members(fleet_id)[0]
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO signals (signal_id, agent_id, message_type, market, "
            "symbol, side, entry_price, quantity, run_id, timestamp, created_at) "
            "VALUES (999002, ?, 'operation', 'crypto', ?, 'buy', 100, 5, ?, "
            "'2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')",
            (self.agent_id, member["symbol"], member["id"]))
        # unowned zombie position with NO price_updated_at (stale mark)
        cur.execute(
            "INSERT INTO positions (agent_id, symbol, market, side, quantity, "
            "entry_price, current_price, opened_at, run_id) VALUES "
            "(?, ?, 'crypto', 'buy', 5, 100, 100, '2026-01-01T00:00:00Z', NULL)",
            (self.agent_id, member["symbol"]))
        cur.execute(
            "UPDATE trading_runs SET status='stopped', "
            "status_reason='positions_held', active_key=NULL WHERE id = ?",
            (member["id"],))
        conn.commit()
        conn.close()
        out = fs.supervise_fleet(fp.get_fleet(fleet_id))
        self.assertTrue(out.get("frozen"),
                        "stale zombie mark must freeze the pass")
        live = [m for m in fp.list_members(fleet_id)
                if m["status"] in ("running", "armed")]
        self.assertEqual(len(live), 1, "no replacement funded on frozen equity")


class FenceAndRetireTests(SupervisionBase):
    def test_save_state_fence_rejects_stale_claimant(self):
        """A zombie claimant whose lease was reclaimed must NOT write adapt
        state (round-4 fence finding)."""
        fleet_id = self._built_fleet(n=1)
        member = fp.list_members(fleet_id)[0]
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "UPDATE trading_runs SET claimed_by='other:1', "
            "claim_expires_at='2099-01-01T00:00:00Z' WHERE id = ?",
            (member["id"],))
        conn.commit()
        conn.close()
        run = trading_runs.get_run(member["id"], self.agent_id)
        state = rf.load_state(run)
        state["last_processed_signal_id"] = 999
        ok = rf.save_state(run, state, [], worker_identity="me:2")
        self.assertFalse(ok, "fence must reject a non-owner write")

    def test_retire_writes_cooldown_in_same_transaction(self):
        fleet_id = self._built_fleet(n=1)
        member = fp.list_members(fleet_id)[0]
        run = trading_runs.get_run(member["id"], self.agent_id)
        rf.retire_run(run, "consecutive_losses")
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT status, status_reason FROM trading_runs WHERE id = ?",
                    (member["id"],))
        row = cur.fetchone()
        self.assertEqual(row["status"], "stopping")
        self.assertEqual(row["status_reason"], "adapt_retired")
        cur.execute("SELECT COUNT(*) AS n FROM fleet_symbol_cooldowns WHERE "
                    "source_run_id = ?", (member["id"],))
        self.assertEqual(int(cur.fetchone()["n"]), 1)
        conn.close()

    def test_reserved_rail_budget_survives_filler_alerts(self):
        """10 filler external sends this hour must NOT starve the −40% SMS
        (reserved bucket — the round-4 starvation finding)."""
        import alerts
        conn = database.get_db_connection()
        cur = conn.cursor()
        hour = rf._now_iso()
        for i in range(10):
            cur.execute(
                "INSERT INTO alert_log (user_id, agent_id, kind, title, body, "
                "channels_json, dedupe_key, created_at) VALUES "
                "(?, ?, 'custom', 't', 'b', '[\"email\"]', ?, ?)",
                (self.user_id, self.agent_id, f"filler-{i}", hour))
        conn.commit()
        limited_general = alerts._external_rate_limited(self.user_id, cur,
                                                        kind="custom")
        limited_rail = alerts._external_rate_limited(self.user_id, cur,
                                                     kind="fleet_breaker")
        conn.close()
        self.assertTrue(limited_general)
        self.assertFalse(limited_rail, "rail kinds have their own budget")


class WatchdogTests(SupervisionBase):
    def _set_stamp(self, fleet_id, value):
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE fleets SET last_supervise_at = ? WHERE id = ?",
                    (value, fleet_id))
        conn.commit()
        conn.close()

    def _watchdog_alerts(self):
        return [a for a in self.alerts if a["kind"] == "fleet_watchdog"]

    def test_fresh_activation_does_not_trip_watchdog(self):
        """A fleet that just went building→active has never been supervised;
        the watchdog must not read its missing stamp as a 3-tick stall.
        Fleets #22–#26 each false-alerted their owner seconds after
        activation, before the first supervise pass could stamp."""
        fleet_id = self._built_fleet()
        self.assertEqual(fp.get_fleet(fleet_id)["status"], fp.STATUS_ACTIVE)
        self.assertEqual(fs.check_watchdog(), 0)
        self.assertEqual(self._watchdog_alerts(), [])

    def test_stale_stamp_still_fires(self):
        fleet_id = self._built_fleet()
        self._set_stamp(fleet_id, "2026-01-01T00:00:00Z")
        self.assertEqual(fs.check_watchdog(), 1)
        hits = self._watchdog_alerts()
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["dedupe"], f"fleet:{fleet_id}:watchdog")

    def test_null_stamp_still_fires(self):
        """NULL stays stale for rows that predate activation stamping — a
        truly unsupervised fleet must still alert."""
        fleet_id = self._built_fleet()
        self._set_stamp(fleet_id, None)
        self.assertEqual(fs.check_watchdog(), 1)
        self.assertEqual(len(self._watchdog_alerts()), 1)


if __name__ == "__main__":
    unittest.main()
